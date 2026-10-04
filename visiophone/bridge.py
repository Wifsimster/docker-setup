#!/usr/bin/env python3
"""Pont entre la platine de rue Dahua VTO2202F et Home Assistant, via MQTT.

La platine n'expose l'appel sur aucune intégration native : l'ONVIF déjà en place
ne remonte que la caméra et les entrées digitales. Les événements d'appel ne
sortent que du flux `eventManager.cgi?action=attach`, qu'on branche ici sur MQTT
avec découverte automatique.

Entités créées côté HA :
  - event.visiophone_appel          (device_class doorbell)
  - binary_sensor.visiophone_appel_en_cours
  - button.visiophone_ouvrir_la_porte
"""
import json
import logging
import os
import threading
import time

import paho.mqtt.client as mqtt
import requests
from requests.auth import HTTPDigestAuth

VTO_HOST = os.environ["VTO_HOST"]
VTO_USER = os.environ["VTO_USER"]
VTO_PASS = os.environ["VTO_PASS"]
MQTT_HOST = os.environ["MQTT_HOST"]
MQTT_PORT = int(os.environ.get("MQTT_PORT", 1883))
MQTT_USER = os.environ["MQTT_USER"]
MQTT_PASS = os.environ["MQTT_PASS"]

BASE = "visiophone"
T_EVENT = f"{BASE}/evenement"
T_CALL = f"{BASE}/appel_en_cours"
T_RAW = f"{BASE}/brut"
T_AVAIL = f"{BASE}/status"
T_CMD_DOOR = f"{BASE}/commande/ouvrir_porte"

# Au-delà, on considère l'appel terminé même si la platine n'a rien dit :
# un Stop manquant laisserait le binary_sensor coincé sur "on" indéfiniment.
CALL_TIMEOUT = 120

DEVICE = {
    "identifiers": ["visiophone_vto2202f"],
    "name": "Visiophone",
    "manufacturer": "Dahua",
    "model": "VTO2202F",
    "configuration_url": f"http://{VTO_HOST}/",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("visiophone")


def discovery_payloads():
    avail = {"availability_topic": T_AVAIL, "payload_available": "online", "payload_not_available": "offline"}
    return [
        (
            "homeassistant/event/visiophone/appel/config",
            {
                "name": "Appel",
                "unique_id": "visiophone_vto2202f_appel",
                "state_topic": T_EVENT,
                "device_class": "doorbell",
                "event_types": ["sonnerie", "sans_reponse", "decroche", "raccroche", "ouverture_porte"],
                "device": DEVICE,
                **avail,
            },
        ),
        (
            "homeassistant/binary_sensor/visiophone/appel_en_cours/config",
            {
                "name": "Appel en cours",
                "unique_id": "visiophone_vto2202f_appel_en_cours",
                "state_topic": T_CALL,
                "payload_on": "ON",
                "payload_off": "OFF",
                "icon": "mdi:bell-ring",
                "device": DEVICE,
                **avail,
            },
        ),
        (
            "homeassistant/button/visiophone/ouvrir_porte/config",
            {
                "name": "Ouvrir la porte",
                "unique_id": "visiophone_vto2202f_ouvrir_porte",
                "command_topic": T_CMD_DOOR,
                "payload_press": "PRESS",
                "icon": "mdi:door-open",
                "device": DEVICE,
                **avail,
            },
        ),
    ]


class Bridge:
    def __init__(self):
        self.call_since = None
        self.lock = threading.Lock()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="visiophone-bridge")
        self.client.username_pw_set(MQTT_USER, MQTT_PASS)
        self.client.will_set(T_AVAIL, "offline", retain=True)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    # -- MQTT ---------------------------------------------------------------
    def on_connect(self, client, userdata, flags, reason_code, properties=None):
        log.info("MQTT connecté (%s)", reason_code)
        for topic, payload in discovery_payloads():
            client.publish(topic, json.dumps(payload, ensure_ascii=False), retain=True)
        client.publish(T_AVAIL, "online", retain=True)
        client.publish(T_CALL, "OFF", retain=True)
        client.subscribe(T_CMD_DOOR)

    def on_message(self, client, userdata, msg):
        if msg.topic == T_CMD_DOOR:
            self.open_door()

    def fire(self, event_type, data=None):
        payload = {"event_type": event_type}
        if data:
            payload.update(data)
        log.info("événement HA : %s", event_type)
        self.client.publish(T_EVENT, json.dumps(payload, ensure_ascii=False))

    def set_call(self, active):
        with self.lock:
            self.call_since = time.time() if active else None
        self.client.publish(T_CALL, "ON" if active else "OFF", retain=True)

    # -- Platine ------------------------------------------------------------
    def open_door(self, channel=1):
        url = (
            f"http://{VTO_HOST}/cgi-bin/accessControl.cgi"
            f"?action=openDoor&channel={channel}&UserID=101&Type=Remote"
        )
        try:
            r = requests.get(url, auth=HTTPDigestAuth(VTO_USER, VTO_PASS), timeout=10)
            log.info("ouverture porte -> HTTP %s %s", r.status_code, r.text.strip()[:80])
            if r.ok:
                self.fire("ouverture_porte", {"source": "home_assistant"})
        except Exception as exc:  # noqa: BLE001
            log.error("ouverture porte échouée : %s", exc)

    def handle(self, code, action, data):
        self.client.publish(T_RAW, json.dumps({"Code": code, "action": action, "data": data}, ensure_ascii=False))

        if code == "Invite":
            self.fire("sonnerie", {"call_id": data.get("CallID")})
            self.set_call(True)
        elif code == "CallNoAnswered":
            self.set_call(action == "Start")
        elif code == "_CallNoAnswer_":
            self.fire("sans_reponse")
            self.set_call(False)
        elif code == "_DoTalkAction_":
            state = str(data.get("Action") or data.get("State") or "").lower()
            if state in ("invite", "talking", "start"):
                self.fire("decroche")
                self.set_call(True)
            else:
                self.fire("raccroche")
                self.set_call(False)
        elif code in ("AccessControl", "DoorStatus"):
            self.fire("ouverture_porte", {"source": "platine"})

    def watchdog(self):
        while True:
            time.sleep(10)
            with self.lock:
                stuck = self.call_since and (time.time() - self.call_since) > CALL_TIMEOUT
            if stuck:
                log.warning("appel bloqué depuis >%ss, remise à OFF", CALL_TIMEOUT)
                self.set_call(False)

    def stream(self):
        url = (
            f"http://{VTO_HOST}/cgi-bin/eventManager.cgi"
            "?action=attach&codes=%5BAll%5D&heartbeat=30"
        )
        while True:
            try:
                with requests.get(
                    url, auth=HTTPDigestAuth(VTO_USER, VTO_PASS), stream=True, timeout=(10, 60)
                ) as r:
                    r.raise_for_status()
                    log.info("flux d'événements attaché à %s", VTO_HOST)
                    header, buf = None, []
                    # decode_unicode=True ne sert à rien ici : la réponse est un
                    # multipart sans charset, donc requests renverrait des bytes.
                    for raw in r.iter_lines():
                        line = (raw or b"").decode("utf-8", "replace").strip()
                        if header is not None:
                            buf.append(line)
                            if line == "}":
                                try:
                                    data = json.loads("\n".join(buf))
                                except json.JSONDecodeError:
                                    data = {}
                                self.handle(header[0], header[1], data)
                                header, buf = None, []
                            continue
                        if not line.startswith("Code="):
                            continue
                        parts = dict(p.split("=", 1) for p in line.split(";") if "=" in p)
                        code, action = parts.get("Code", ""), parts.get("action", "")
                        if line.rstrip().endswith("data={"):
                            header, buf = (code, action), ["{"]
                        else:
                            self.handle(code, action, {})
            except Exception as exc:  # noqa: BLE001
                log.warning("flux interrompu (%s), reconnexion dans 5 s", exc)
                time.sleep(5)

    def run(self):
        self.client.connect(MQTT_HOST, MQTT_PORT, 60)
        self.client.loop_start()
        threading.Thread(target=self.watchdog, daemon=True).start()
        self.stream()


if __name__ == "__main__":
    Bridge().run()
