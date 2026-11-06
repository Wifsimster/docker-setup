import email.utils
import hashlib
import hmac
import json
import os
import re
import sys
import time
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TOKEN = os.environ.get("MAILSYNC_TOKEN", "")
SPOOL = Path(os.environ.get("MAILSYNC_SPOOL", "/spool"))
MAX_BYTES = int(os.environ.get("MAILSYNC_MAX_BYTES", str(512 * 1024)))
MAX_ITEMS = 500
MAILDIR = SPOOL / "Maildir"

ALLOWED = {
    "direction", "from", "to", "cc", "subject", "date",
    "internetMessageId", "conversationId", "importance", "hasAttachments",
}
REQUIRED = {"direction", "from", "date", "internetMessageId"}
FORBIDDEN_HINTS = ("body", "preview", "attachment", "content")


def log(event, **fields):
    print(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, **fields}), flush=True)


def as_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [p.strip() for p in re.split(r"[;,]", value) if p.strip()]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return [v.strip() for v in value if v.strip()]
    raise ValueError("adresse invalide")


def clean(text, limit):
    if not isinstance(text, str):
        raise ValueError("texte attendu")
    return re.sub(r"[\r\n\x00]+", " ", text).strip()[:limit]


def validate(item):
    if not isinstance(item, dict):
        raise ValueError("objet attendu")
    keys = set(item)
    for key in keys:
        if any(h in key.lower() for h in FORBIDDEN_HINTS) and key != "hasAttachments":
            raise ValueError(f"champ de contenu refusé : {key}")
    unknown = keys - ALLOWED
    if unknown:
        raise ValueError(f"champs inconnus : {sorted(unknown)}")
    missing = REQUIRED - keys
    if missing:
        raise ValueError(f"champs manquants : {sorted(missing)}")
    if item["direction"] not in ("received", "sent"):
        raise ValueError("direction : received ou sent")
    parsed = email.utils.parsedate_to_datetime(item["date"]) if not re.match(r"\d{4}-", str(item["date"])) else None
    if parsed is None:
        from datetime import datetime
        parsed = datetime.fromisoformat(str(item["date"]).replace("Z", "+00:00"))
    return {
        "direction": item["direction"],
        "from": clean(item["from"], 320),
        "to": [clean(a, 320) for a in as_list(item.get("to"))][:100],
        "cc": [clean(a, 320) for a in as_list(item.get("cc"))][:100],
        "subject": clean(item.get("subject", ""), 500),
        "date": parsed,
        "internetMessageId": clean(item["internetMessageId"], 998),
        "conversationId": clean(item.get("conversationId", ""), 500),
        "importance": clean(item.get("importance", ""), 20),
        "hasAttachments": bool(item.get("hasAttachments", False)),
    }


def write_eml(h):
    msg = EmailMessage()
    msg["From"] = h["from"]
    if h["to"]:
        msg["To"] = ", ".join(h["to"])
    if h["cc"]:
        msg["Cc"] = ", ".join(h["cc"])
    msg["Subject"] = h["subject"]
    msg["Date"] = email.utils.format_datetime(h["date"])
    msg["Message-ID"] = h["internetMessageId"]
    msg["X-Mailsync-Direction"] = h["direction"]
    if h["conversationId"]:
        msg["X-Mailsync-Conversation"] = h["conversationId"]
    if h["importance"]:
        msg["Importance"] = h["importance"]
    msg["X-Mailsync-Has-Attachments"] = "yes" if h["hasAttachments"] else "no"
    msg.set_content("")
    digest = hashlib.sha256(h["internetMessageId"].encode()).hexdigest()[:32]
    box = MAILDIR / ".Sent" if h["direction"] == "sent" else MAILDIR
    for sub in ("cur", "new", "tmp"):
        (box / sub).mkdir(parents=True, exist_ok=True)
    name = f"{int(h['date'].timestamp())}.{digest}.mailsync"
    path = box / "cur" / f"{name}:2,S"
    if path.exists():
        return False
    tmp = box / "tmp" / name
    tmp.write_bytes(bytes(msg))
    os.utime(tmp, (h["date"].timestamp(), h["date"].timestamp()))
    tmp.rename(path)
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "mailsync"
    sys_version = ""

    def log_message(self, *args):
        pass

    def reply(self, code, payload):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/healthz":
            return self.reply(200, {"ok": True})
        return self.reply(404, {"error": "introuvable"})

    def do_POST(self):
        if self.path != "/v1/headers":
            return self.reply(404, {"error": "introuvable"})
        auth = self.headers.get("Authorization", "")
        if not TOKEN or not hmac.compare_digest(auth.encode(), f"Bearer {TOKEN}".encode()):
            log("refused", reason="token")
            return self.reply(401, {"error": "jeton invalide"})
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BYTES:
            return self.reply(413, {"error": "taille refusée"})
        try:
            data = json.loads(self.rfile.read(length))
            items = data if isinstance(data, list) else [data]
            if len(items) > MAX_ITEMS:
                raise ValueError("trop d'éléments")
            headers = [validate(i) for i in items]
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            log("rejected", reason=str(exc))
            return self.reply(400, {"error": str(exc)})
        written = sum(write_eml(h) for h in headers)
        log("accepted", items=len(headers), written=written)
        return self.reply(200, {"accepted": len(headers), "written": written})


if __name__ == "__main__":
    if not TOKEN or len(TOKEN) < 32:
        sys.exit("MAILSYNC_TOKEN manquant ou trop court")
    os.umask(0o027)
    for sub in ("cur", "new", "tmp"):
        (MAILDIR / sub).mkdir(parents=True, exist_ok=True)
    log("start", maildir=str(MAILDIR))
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
