#!/usr/bin/env python3
"""Collecte l'activité de la maison sur 7 jours (lecture seule) et écrit du JSON sur stdout."""
import json, os, re, sqlite3, subprocess
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Paris")
NOW = datetime.now(TZ)
TODAY = NOW.replace(hour=0, minute=0, second=0, microsecond=0)
DAYS = [TODAY - timedelta(days=6 - i) for i in range(7)]
PREV = [TODAY - timedelta(days=13 - i) for i in range(7)]
DAY_SHORT = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
DAY_FULL = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MON_ABBR = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
MON_FULL = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def bounds(days):
    return [(d.timestamp(), min((d + timedelta(days=1)).timestamp(), NOW.timestamp())) for d in days]


B, PB = bounds(DAYS), bounds(PREV)
W0, W1 = B[0][0], NOW.timestamp()
P0 = PB[0][0]


def day_index(ts, bl):
    for i, (a, b) in enumerate(bl):
        if a <= ts < b + 1e-6:
            return i
    return None


def ro(path):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def safe(fn, default):
    try:
        return fn()
    except Exception as e:  # une source en panne ne doit pas bloquer le résumé
        print(f"[collect] {fn.__name__}: {e}", flush=True, file=__import__("sys").stderr)
        return default


def fr_h(hours):
    m = round(hours * 60)
    return f"{m // 60} h {m % 60:02d}"


def fr_list(nums):
    nums = [str(x) for x in nums]
    return nums[0] if len(nums) == 1 else ", ".join(nums[:-1]) + " et " + nums[-1]


def short_day(d):
    return f"{d.day if d.day > 1 else '1er'} {MON_ABBR[d.month - 1]}"


# ---------- Home Assistant ----------
HA = ro("/opt/docker/home-assistant/config/home-assistant_v2.db")


def intervals(eid, t0, t1):
    mid = HA.execute("select metadata_id from states_meta where entity_id=?", (eid,)).fetchone()
    if not mid:
        return []
    mid = mid[0]
    seq = []
    pre = HA.execute("select state,last_updated_ts from states where metadata_id=? and last_updated_ts<? order by last_updated_ts desc limit 1", (mid, t0)).fetchone()
    if pre:
        seq.append((pre[0], t0))
    seq += HA.execute("select state,last_updated_ts from states where metadata_id=? and last_updated_ts>=? and last_updated_ts<? order by last_updated_ts", (mid, t0, t1)).fetchall()
    return [(st, t, seq[i + 1][1] if i + 1 < len(seq) else t1) for i, (st, t) in enumerate(seq)]


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def per_day_hours(eid, target, bl):
    iv = intervals(eid, bl[0][0], bl[-1][1])
    return [round(sum(overlap(t0, t1, d0, d1) for st, t0, t1 in iv if st == target) / 3600, 2) for d0, d1 in bl]


def transitions(eid, targets, bl, exclude_prev=None):
    iv = intervals(eid, bl[0][0], bl[-1][1])
    counts, last, prev = [0] * len(bl), None, None
    for st, t0, _ in iv:
        if st in targets and prev is not None and prev not in (exclude_prev or targets):
            i = day_index(t0, bl)
            if i is not None:
                counts[i] += 1
                last = t0
        prev = st
    return counts, last


def presence():
    out = {"people": ["Christelle", "Damien"], "hours": []}
    for eid in ("person.christelle", "person.wifsimster"):
        out["hours"].append([min(24, round(h)) if h >= 10 else round(h, 1) for h in per_day_hours(eid, "home", B)])
    return out


def daily_mean(eid):
    iv = intervals(eid, W0, W1)
    vals = []
    for d0, d1 in B:
        num = den = 0.0
        for st, t0, t1 in iv:
            try:
                v = float(st)
            except ValueError:
                continue
            o = overlap(t0, t1, d0, d1)
            num, den = num + v * o, den + o
        vals.append(round(num / den, 1) if den else None)
    known = [v for v in vals if v is not None]
    if not known:
        return None
    last = next(v for v in vals if v is not None)
    filled = []
    for v in vals:
        last = v if v is not None else last
        filled.append(last)
    return filled


def temps():
    i, o = daily_mean("sensor.temperature_interieure_moyenne"), daily_mean("sensor.temperature_exterieure_validee")
    return {"inside": i, "outside": o} if i and o else None


def week_sum(fn):
    return sum(fn(B)), sum(fn(PB))


def gate():
    return lambda bl: transitions("cover.portail", ("opening", "open"), bl)[0]


def music_players():
    return {"Salon": "media_player.sonos_salon", "Chambre de Léo": "media_player.sonos_chambre_leo"}


def music_hours(bl):
    per = {n: per_day_hours(e, "playing", bl) for n, e in music_players().items()}
    return per


# ---------- Immich ----------
def photos():
    sql = ("select (\"createdAt\" at time zone 'Europe/Paris')::date, type, count(*) from asset "
           "where \"createdAt\" >= now() - interval '15 days' and \"deletedAt\" is null group by 1,2")
    out = subprocess.check_output(["docker", "exec", "immich_postgres", "psql", "-U", "postgres", "-d", "immich", "-At", "-F", "|", "-c", sql], text=True)
    per, imgs, vids, prev = {d.date().isoformat(): 0 for d in DAYS}, 0, 0, 0
    prev_days = {d.date().isoformat() for d in PREV}
    for line in out.strip().splitlines():
        day, typ, n = line.split("|")
        n = int(n)
        if day in per:
            per[day] += n
            imgs, vids = (imgs + n, vids) if typ == "IMAGE" else (imgs, vids + n)
        elif day in prev_days:
            prev += n
    return {"perDay": [per[d.date().isoformat()] for d in DAYS], "images": imgs, "videos": vids, "prev": prev}


# ---------- Sonarr / Radarr ----------
def parse_utc(s):
    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def media():
    eps, films = {}, []
    per, per_prev = [0] * 7, 0
    seen = set()
    con = ro("/opt/docker/sonarr/data/sonarr.db")
    cutoff = (NOW - timedelta(days=15)).astimezone(timezone.utc).strftime("%Y-%m-%d")
    for date, title, season, ep, eid in con.execute(
            "select h.Date,s.Title,e.SeasonNumber,e.EpisodeNumber,h.EpisodeId from History h join Series s on s.Id=h.SeriesId left join Episodes e on e.Id=h.EpisodeId where h.EventType=3 and h.Date>=?", (cutoff,)):
        if eid in seen:
            continue
        seen.add(eid)
        ts = parse_utc(date).timestamp()
        i = day_index(ts, B)
        if i is not None:
            per[i] += 1
            eps.setdefault(title, []).append((season, ep))
        elif P0 <= ts < W0:
            per_prev += 1
    con = ro("/opt/docker/radarr/data/radarr.db")
    seen = set()
    for date, title, year, mid in con.execute(
            "select h.Date,m.Title,m.Year,h.MovieId from History h join Movies mv on mv.Id=h.MovieId join MovieMetadata m on m.Id=mv.MovieMetadataId where h.EventType=3 and h.Date>=?", (cutoff,)):
        if mid in seen:
            continue
        seen.add(mid)
        ts = parse_utc(date).timestamp()
        i = day_index(ts, B)
        if i is not None:
            per[i] += 1
            films.append((title, year))
        elif P0 <= ts < W0:
            per_prev += 1
    items = []
    for title, lst in sorted(eps.items(), key=lambda kv: -len(kv[1])):
        lst = sorted(set(lst), key=lambda x: (x[0] or 0, x[1] or 0))
        seasons = sorted({s for s, _ in lst if s is not None})
        if len(seasons) == 1:
            n = [e for _, e in lst]
            s = f"Saison {seasons[0]} · épisode{'s' if len(n) > 1 else ''} {fr_list(n)}"
        else:
            s = f"{len(lst)} épisodes"
        items.append({"t": title, "s": s, "r": str(len(lst))})
    items += [{"t": t, "s": f"Film · {y}", "r": "1"} for t, y in films]
    return {"items": items, "perDay": per, "total": sum(per), "prev": per_prev}


# ---------- Pi-hole ----------
def dns():
    con = ro("/opt/docker/pihole/pihole/pihole-FTL.db")
    total, blocked = con.execute("select count(*), coalesce(sum(status in (1,4,5,6,7,8,9,10,11,15,16,17)),0) from queries where timestamp>=?", (W0,)).fetchone()
    return {"total": total, "blocked": int(blocked)}


# ---------- Uptime Kuma ----------
def kuma_rows():
    con = ro("/opt/docker/uptime-kuma/data/kuma.db")
    rows = []
    for mid, name in con.execute("select id,name from monitor where active=1"):
        last = con.execute("select status,time from heartbeat where monitor_id=? order by id desc limit 1", (mid,)).fetchone()
        if last and last[0] == 0:
            up = con.execute("select max(time) from heartbeat where monitor_id=? and status=1", (mid,)).fetchone()[0]
            since = ""
            if up:
                days = (datetime.now(timezone.utc) - parse_utc(up)).days
                since = f"Ne répond plus depuis {days} jour{'s' if days > 1 else ''}" if days >= 1 else "Ne répond plus depuis quelques heures"
            rows.append({"ok": False, "t": f"Site « {name} » hors ligne", "s": since or "Ne répond pas"})
    return rows


# ---------- Sauvegardes (journaux des jobs cron, voir backup-watch.sh) ----------
LOG_LINE = re.compile(r"^\[(\S+) (\d{4}-\d\d-\d\d \d\d:\d\d)\] (.*)$")
BACKUP_JOBS = [  # libellé, journal, réussite, attendu par semaine
    ("état des services", "state-backup", lambda m: m.startswith("Done"), 7),
    ("photos", "photos-backup", lambda m: m.startswith("Done"), 1),
    ("arbre Gramps", "gramps-backup", lambda m: m.endswith("Done."), 1),
    ("configuration Home Assistant", "ha-config-backup", lambda m: m.endswith("Done."), 1),
]


def log_rows(name, log=None):
    rows, log = [], log or name
    for f in (f"/var/log/{log}.log.1", f"/var/log/{log}.log"):
        if os.path.exists(f):
            with open(f, errors="replace") as fh:
                for line in fh:
                    m = LOG_LINE.match(line.rstrip("\n"))
                    if m and m.group(1) == name:
                        ts = datetime.strptime(m.group(2), "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp()
                        rows.append((ts, m.group(3)))
    return rows


def backups():
    """Bilan hebdo des sauvegardes. Les échecs restent signalés tout de suite par backup-watch.sh."""
    parts, bad = [], []
    for label, name, ok, expected in BACKUP_JOBS:
        rows = [r for r in log_rows(name) if W0 <= r[0] <= W1]
        done = sum(1 for _, m in rows if ok(m))
        errors = sum(1 for _, m in rows if "[ERROR]" in m)
        parts.append(f"{label} {done}/{expected}" + (f" ({errors} erreur{'s' if errors > 1 else ''})" if errors else ""))
        if done < expected or errors:
            bad.append(label)
    check = [m for _, m in log_rows("borg-check", "state-backup") if "PASSED" in m or "FAILED" in m]
    if check:
        parts.append("vérification mensuelle " + ("en échec" if "FAILED" in check[-1] else "OK"))
        if "FAILED" in check[-1]:
            bad.append("vérification")
    return {"ok": not bad, "t": "Sauvegardes" + (f" — à vérifier : {', '.join(bad)}" if bad else ""), "s": " · ".join(parts)}


# ---------- Notifications Home Assistant de la semaine ----------
def notifications():
    """Notifications envoyées par HA (pushs et notifications persistantes), regroupées par titre.
    Lu dans les événements call_service ; un envoi au groupe all_mobiles et sa copie par téléphone comptent une fois."""
    sql = ("select e.time_fired_ts, json_extract(d.shared_data,'$.domain'), json_extract(d.shared_data,'$.service'), "
           "json_extract(d.shared_data,'$.service_data.title') from events e "
           "join event_types t on t.event_type_id=e.event_type_id join event_data d on d.data_id=e.data_id "
           "where t.event_type='call_service' and e.time_fired_ts>=? and e.time_fired_ts<? "
           "and json_extract(d.shared_data,'$.domain') in ('notify','persistent_notification')")
    seen, per = set(), {}
    for ts, dom, svc, title in HA.execute(sql, (W0, W1)):
        if dom == "persistent_notification" and svc != "create":
            continue
        title = re.sub(r"^[^\wÀ-ÿ]+", "", (title or "Sans titre")).strip() or "Sans titre"
        key = (title, int(ts // 5))
        if key in seen:
            continue
        seen.add(key)
        per[title] = per.get(title, 0) + 1
    return sorted(per.items(), key=lambda kv: -kv[1])


# ---------- Piles faibles (publiées par HA le dimanche à 7h, événement piles_hebdo) ----------
def piles():
    import time
    sql = ("select json_extract(d.shared_data,'$.message') from events e "
           "join event_types t on t.event_type_id=e.event_type_id join event_data d on d.data_id=e.data_id "
           "where t.event_type='piles_hebdo' and e.time_fired_ts>=? order by e.time_fired_ts desc limit 1")
    row = HA.execute(sql, (time.time() - 2 * 86400,)).fetchone()
    return (row[0] or "").strip() if row else ""


DEV_JOURNAL = "/opt/docker/digest/dev-journal.md"  # copié chaque matin depuis codedev (birthday-push.sh)


def dev_journal():
    """Jardinier verify + repro Koe : lignes « - AAAA-MM-JJ — dépôt : résultat — phrase (lien) » des 7 derniers jours."""
    out = []
    with open(DEV_JOURNAL, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^- (\d{4}-\d\d-\d\d) [—-] ([^:]+?) : (.+)$", line.strip())
            if m and DAYS[0].date().isoformat() <= m.group(1) <= TODAY.date().isoformat():
                out.append((m.group(2).strip(), m.group(3).strip()))
    return out


def disk_meters():
    out = []
    for label, path in (("Disque du serveur Docker", "/"), ("Stockage Unraid", "/mnt/media")):
        try:
            st = os.statvfs(path)
            out.append({"l": label, "p": round(100 * (1 - st.f_bavail / st.f_blocks))})
        except OSError:
            pass
    return out


# ---------- Orbite (entourage) et agenda Jarvis ----------
AGENDA_AUTO = "/opt/docker/digest/agenda-auto.md"  # copié chaque matin depuis codedev (birthday-push.sh)


def entourage():
    """Anniversaires à venir (14 j), proches qui s'éloignent. Lecture seule d'Orbite."""
    import orbite
    con = orbite.connect()
    rows = []
    for b in orbite.birthdays(con):
        d = date.fromisoformat(b["date"])
        when = "aujourd'hui" if b["inDays"] == 0 else "demain" if b["inDays"] == 1 else f"{DAY_FULL[d.weekday()]} {short_day(datetime(d.year, d.month, d.day))}"
        rows.append({"icon": "cake", "t": b["name"], "s": f"{when.capitalize()} · {b['circle']}", "r": f"{b['turning']} ans" if b["turning"] else ""})
    drift = [{"icon": "drift", "t": x["name"], "s": f"{x['recent']} échanges ces 3 derniers mois, d'habitude ~{x['usual']}", "r": ""}
             for x in orbite.drifting(con)]
    return rows, drift


def agenda_auto():
    """Événements ajoutés automatiquement par Jarvis ces 7 derniers jours (lignes « - AAAA-MM-JJ — texte »)."""
    out = []
    with open(AGENDA_AUTO, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^- (\d{4}-\d\d-\d\d) [—-] (.+)$", line.strip())
            if m and DAYS[0].date().isoformat() <= m.group(1) <= TODAY.date().isoformat():
                text = m.group(2).split(" — ")[0]
                out.append({"icon": "calendar", "t": text, "s": f"Ajouté le {short_day(datetime.fromisoformat(m.group(1)))}", "r": ""})
    return out


PROJETS = "/opt/docker/digest/projets-maison-journal.md"  # copié chaque matin depuis codedev (birthday-push.sh)


def projets():
    """Journal des projets maison des 7 derniers jours + échéances à 30 j (section « ## Échéances »)."""
    journal, due, in_due = [], [], False
    with open(PROJETS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line.startswith("## "):
                in_due = line[3:].strip().lower().startswith("échéance")
                continue
            m = re.match(r"^- (\d{4}-\d\d-\d\d) [—-] (.+)$", line)
            if not m:
                continue
            d = date.fromisoformat(m.group(1))
            if in_due:
                days = (d - TODAY.date()).days
                if 0 <= days <= 30:
                    due.append((days, {"icon": "calendar", "t": m.group(2), "s": f"Échéance {DAY_FULL[d.weekday()]} {short_day(datetime(d.year, d.month, d.day))}",
                                       "r": "aujourd'hui" if days == 0 else f"dans {days} j"}))
            elif DAYS[0].date() <= d <= TODAY.date():
                journal.append({"icon": "check", "t": m.group(2), "s": f"Le {short_day(datetime(d.year, d.month, d.day))}", "r": ""})
    return [x for _, x in sorted(due, key=lambda t: t[0])] + journal[::-1]


ENTOURAGE_JOURNAL = "/opt/docker/digest/entourage-journal.md"  # copié chaque matin depuis codedev (birthday-push.sh)


def fiches():
    """Fiches Orbite mises à jour par Jarvis ces 7 derniers jours (« - AAAA-MM-JJ — personne : champ mis à jour (source) »)."""
    out = []
    with open(ENTOURAGE_JOURNAL, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^- (\d{4}-\d\d-\d\d) [—-] ([^:]+?) : (.+)$", line.strip())
            if m and DAYS[0].date().isoformat() <= m.group(1) <= TODAY.date().isoformat():
                d = datetime.fromisoformat(m.group(1))
                out.append({"icon": "check", "t": m.group(2), "s": f"{m.group(3)} · {short_day(d)}", "r": ""})
    return out[::-1]


# ---------- Détails techniques et services Battistella (page de Damien seulement, voir publish.py) ----------
# Chaque section : {"h": titre, "sub": sous-titre, "rows": [{"ok", "t", "s", "r"}]} ; une source en panne retire sa section.
DIGEST = "/opt/docker/digest"
KUMA_DB = "/opt/docker/uptime-kuma/data/kuma.db"
TRAEFIK_LOGS = ("/opt/docker/traefik/logs/access.json.1", "/opt/docker/traefik/logs/access.json")  # 4xx/5xx seulement
ACME = "/opt/docker/traefik/acme/letsencrypt.json"
EXTRA_PRODUCTS = ("wawptn.battistella.ovh", "copro-pilot.battistella.ovh")  # produits sans site Umami


def sh(*cmd, timeout=60):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=True).stdout


def pct(a, b):
    return f"{100 * a / b:.2f}".rstrip("0").rstrip(".").replace(".", ",") + " %" if b else "—"


def evo(now, prev):
    if not prev:
        return "nouveau" if now else ""
    d = round(100 * (now - prev) / prev)
    return f"{'+' if d > 0 else '−' if d < 0 else ''}{abs(d)} %"


def host_of(url):
    m = re.match(r"https?://([^/:]+)", url or "")
    return m.group(1) if m else ""


def kuma_week():
    """Par sonde : disponibilité, incidents, durée hors ligne, latence moyenne sur 7 jours."""
    con = ro(KUMA_DB)
    since = datetime.fromtimestamp(W0, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    out = []
    for mid, name, url in con.execute("select id,name,url from monitor where active=1"):
        hb = [(s, parse_utc(t).timestamp(), p) for s, t, p in
              con.execute("select status,time,ping from heartbeat where monitor_id=? and time>=? and status in (0,1) order by time", (mid, since))]
        if not hb:
            continue
        up = sum(1 for s, _, _ in hb if s == 1)
        incidents = sum(1 for i, (s, _, _) in enumerate(hb) if s == 0 and (i == 0 or hb[i - 1][0] == 1))
        down = sum(hb[i + 1][1] - t for i, (s, t, _) in enumerate(hb[:-1]) if s == 0)
        if hb[-1][0] == 0:
            down += W1 - hb[-1][1]
        pings = [p for s, _, p in hb if s == 1 and p]
        out.append({"name": name, "host": host_of(url), "up": up, "n": len(hb), "incidents": incidents, "down": down,
                    "ping": round(sum(pings) / len(pings)) if pings else None})
    return out


def fr_dur(sec):
    m = round(sec / 60)
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d}"


def kuma_ok(k):
    return k["n"] and k["up"] / k["n"] >= 0.999  # moins de 10 min hors ligne sur la semaine


def kuma_section(kw):
    long_ = sorted((k for k in kw if k["down"] > 300), key=lambda k: k["up"] / k["n"])
    short = [k for k in kw if 0 < k["down"] <= 300 or (k["incidents"] and k["down"] <= 300)]
    rows = [{"ok": kuma_ok(k), "t": k["name"], "r": pct(k["up"], k["n"]),
             "s": f"{k['incidents']} incident{'s' if k['incidents'] > 1 else ''}, {fr_dur(k['down'])} hors ligne"
                  + (f" · {k['ping']} ms en moyenne" if k["ping"] else "")} for k in long_]
    if short:
        rows.append({"ok": True, "t": "Coupures de moins de 5 min", "r": str(len(short)), "s": ", ".join(k["name"] for k in short)})
    good = [k for k in kw if not k["incidents"] and not k["down"]]
    if good:
        slow = sorted((k for k in good if k["ping"]), key=lambda k: -k["ping"])[:3]
        rows.append({"ok": True, "t": f"{len(good)} services sans coupure", "r": str(len(good)),
                     "s": ("Les plus lents : " + ", ".join(f"{k['name']} {k['ping']} ms" for k in slow)) if slow else ""})
    return {"h": "Services (Uptime Kuma)", "sub": "Disponibilité sur 7 jours, incidents, temps de réponse", "rows": rows}


def plural(n, word):
    return f"{n:,} {word}{'s' if n > 1 else ''}".replace(",", " ")


def last_line(name, pred):
    rows = [r for r in log_rows(name) if pred(r[1])]
    return rows[-1] if rows else None


def backups_section():
    rows = []
    for label, name, ok, expected in BACKUP_JOBS:
        week = [r for r in log_rows(name) if W0 <= r[0] <= W1]
        done = sum(1 for _, m in week if ok(m))
        errors = [m for _, m in week if "[ERROR]" in m]
        last = last_line(name, ok)
        size = last_line(name, lambda m: m.startswith("Created "))
        detail = last[1] if last else "Aucune exécution réussie trouvée"
        if size and name.endswith(("gramps-backup", "ha-config-backup")):
            m = re.search(r"\(([^)]+)\)\s*$", size[1])
            detail = f"Archive {m.group(1)} vérifiée sur le NAS" if m else detail
        when = datetime.fromtimestamp(last[0], TZ) if last else None
        rows.append({"ok": done >= expected and not errors, "t": label[0].upper() + label[1:], "r": f"{done}/{expected}",
                     "s": (f"{DAY_FULL[when.weekday()]} {when:%H:%M} · " if when else "") + detail
                          + (f" · dernière erreur : {errors[-1][:90]}" if errors else "")})
    check = [r for r in log_rows("borg-check", "state-backup") if "PASSED" in r[1] or "FAILED" in r[1]]
    if check:
        d = datetime.fromtimestamp(check[-1][0], TZ)
        rows.append({"ok": "FAILED" not in check[-1][1], "t": "Vérification Borg mensuelle", "r": "OK" if "FAILED" not in check[-1][1] else "échec",
                     "s": f"{d.day} {MON_ABBR[d.month - 1]} · {check[-1][1][:110]}"})
    return {"h": "Sauvegardes", "sub": "Dernière exécution réussie de chaque tâche", "rows": rows}


def disks_section():
    hist_path = f"{DIGEST}/disk-history.json"
    try:
        hist = json.load(open(hist_path, encoding="utf-8"))
    except (OSError, ValueError):
        hist = {}
    today, rows, snap = TODAY.date().isoformat(), [], {}
    old = max((d for d in hist if d <= (TODAY - timedelta(days=6)).date().isoformat()), default=None)
    for label, path in (("Disque du serveur Docker", "/"), ("Stockage Unraid", "/mnt/media")):
        try:
            st = os.statvfs(path)
        except OSError:
            continue
        total, free = st.f_blocks * st.f_frsize / 1e9, st.f_bavail * st.f_frsize / 1e9
        used = total - free
        snap[label] = round(used, 1)
        p = round(100 * (1 - st.f_bavail / st.f_blocks))
        delta = used - hist[old][label] if old and label in hist.get(old, {}) else None
        rows.append({"ok": p < 85, "t": label, "r": f"{p} %",
                     "s": f"{used:,.0f} Go utilisés sur {total:,.0f} Go · {free:,.0f} Go libres".replace(",", " ")
                          + (f" · {'+' if delta >= 0 else '−'}{abs(delta):,.1f} Go en 7 jours".replace(",", " ").replace(".", ",") if delta is not None else "")})
    hist[today] = snap
    hist = dict(sorted(hist.items())[-60:])
    with open(hist_path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(hist, fh)
    os.replace(hist_path + ".tmp", hist_path)
    return {"h": "Disques", "sub": "Occupation et évolution sur la semaine", "rows": rows}


def docker_section():
    rows = []
    states = [l.split("|", 2) for l in sh("docker", "ps", "-a", "--format", "{{.Names}}|{{.State}}|{{.Status}}").splitlines() if l]
    broken = [(n, st) for n, s, st in states if s not in ("running", "created") and not st.startswith("Exited (0)")]
    unhealthy = [n for n, s, st in states if "(unhealthy)" in st]
    for n, st in broken:
        rows.append({"ok": False, "t": f"Conteneur {n} arrêté", "s": st, "r": ""})
    for n in unhealthy:
        rows.append({"ok": False, "t": f"Conteneur {n} en mauvaise santé", "s": "Healthcheck en échec", "r": ""})
    ids = sh("docker", "ps", "-q").split()
    restarts = []
    for l in sh("docker", "inspect", "--format", "{{.Name}}|{{.RestartCount}}", *ids).splitlines() if ids else []:
        n, c = l.lstrip("/").split("|")
        if int(c):
            restarts.append((n, int(c)))
    if restarts:
        restarts.sort(key=lambda x: -x[1])
        rows.append({"ok": False, "t": "Redémarrages automatiques", "r": str(sum(c for _, c in restarts)),
                     "s": ", ".join(f"{n} ×{c}" for n, c in restarts[:8])})
    logs = subprocess.run(["docker", "logs", "--since", "168h", "watchtower"], capture_output=True, text=True, timeout=60)
    found = re.findall(r'msg="Found new (\S+) image', logs.stdout + logs.stderr)
    failed = sum(int(x) for x in re.findall(r"Failed=(\d+)", logs.stdout + logs.stderr))
    names = sorted({f.split("/")[-1].split(":")[0] for f in found})
    rows.append({"ok": not failed, "t": "Mises à jour d'images (Watchtower)", "r": str(len(found)),
                 "s": (", ".join(names[:10]) + (f" + {len(names) - 10}" if len(names) > 10 else "") if names else "Aucune cette semaine")
                      + (f" · {failed} échec{'s' if failed > 1 else ''}" if failed else "")})
    running = sum(1 for _, s, _ in states if s == "running")
    rows.append({"ok": not broken and not unhealthy, "t": f"{running} conteneurs en marche", "r": str(running),
                 "s": f"{len(states)} au total · {sum(1 for *_, st in states if '(healthy)' in st)} avec healthcheck OK"})
    return {"h": "Docker", "sub": "État des conteneurs, redémarrages, mises à jour", "rows": rows}


def certs_section():
    import base64
    acme = json.load(open(ACME, encoding="utf-8"))
    certs = []
    for resolver in acme.values():
        for c in (resolver or {}).get("Certificates") or []:
            pem = base64.b64decode(c["certificate"])
            end = subprocess.run(["openssl", "x509", "-noout", "-enddate"], input=pem, capture_output=True, timeout=10).stdout.decode()
            m = re.search(r"notAfter=(.+)", end)
            if m:
                exp = datetime.strptime(m.group(1).strip(), "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
                certs.append((c["domain"]["main"], (exp - datetime.now(timezone.utc)).days))
    certs.sort(key=lambda x: x[1])
    rows = [{"ok": False, "t": d, "r": f"{n} j", "s": "Expire bientôt (Traefik renouvelle à 30 j : à vérifier)"} for d, n in certs if n < 21]
    if certs:
        rows.append({"ok": True, "t": f"{len(certs)} certificats Let's Encrypt", "r": str(len(certs)),
                     "s": "Les plus proches : " + ", ".join(f"{d} {n} j" for d, n in certs[:3])})
    return {"h": "Certificats", "sub": "Expiration des certificats HTTPS", "rows": rows}


def dns_section():
    con = ro("/opt/docker/pihole/pihole/pihole-FTL.db")
    blocked = "status in (1,4,5,6,7,8,9,10,11,15,16,17)"
    top_b = con.execute(f"select domain,count(*) c from queries where timestamp>=? and {blocked} group by domain order by c desc limit 5", (W0,)).fetchall()
    top_c = con.execute("select client,count(*) c, sum(" + blocked + ") from queries where timestamp>=? group by client order by c desc limit 5", (W0,)).fetchall()
    names = dict(con.execute("select ip,name from network_addresses where name is not null and name<>''").fetchall())
    names.update({ip: n for ip, n in con.execute("select ip,name from client_by_id where name is not null and name<>''")})
    rows = [{"ok": True, "t": "Domaines les plus bloqués", "r": "",
             "s": " · ".join(f"{d} {c:,}".replace(",", " ") for d, c in top_b)}] if top_b else []
    for ip, c, b in top_c:
        rows.append({"ok": True, "t": names.get(ip, ip) + (f" ({ip})" if ip in names else ""), "r": f"{c:,}".replace(",", " "),
                     "s": f"{pct(b or 0, c)} bloquées"})
    return {"h": "DNS (Pi-hole)", "sub": "Domaines bloqués et appareils les plus actifs", "rows": rows}


def dev_section():
    rows = []
    for repo, txt in safe(dev_journal, []):
        rows.append({"ok": not txt.startswith(("bloqué", "reproduit")), "t": repo, "s": txt, "r": ""})
    try:
        jw = json.load(open(f"{DIGEST}/jarvis-weekly.json", encoding="utf-8"))
    except (OSError, ValueError):
        jw = {}
    if jw and jw.get("generated", "") >= (TODAY - timedelta(days=1)).date().isoformat():
        prs = jw.get("prs") or {}
        total = sum(len(v) for v in prs.values())
        if total:
            rows.append({"ok": True, "t": "PR fusionnées", "r": str(total),
                         "s": " · ".join(f"{r} {len(v)}" for r, v in prs.items())})
            for r, v in list(prs.items())[:4]:
                rows.append({"ok": True, "t": r, "r": str(len(v)),
                             "s": " · ".join(f"#{p['n']} {p['t']}" for p in v[:4]) + (f" · + {len(v) - 4}" if len(v) > 4 else "")})
        for f in jw.get("cronFailures") or []:
            rows.append({"ok": False, "t": f"Cron Jarvis « {f['name']} »", "r": f"{f['fails']}/{f['runs']}",
                         "s": f"Dernier échec {f['last']} · {f['msg']}"})
        if not jw.get("cronFailures"):
            rows.append({"ok": True, "t": "Crons Jarvis", "r": "", "s": "Aucun échec cette semaine"})
    return {"h": "Dev et Jarvis", "sub": "Jardinier, repro Koe, PR fusionnées, crons Jarvis", "rows": rows}


def umami_week():
    """Visiteurs, visites et pages vues par site, semaine en cours et précédente."""
    q = ("select w.name, w.domain,"
         " count(distinct e.session_id) filter (where e.created_at >= to_timestamp({w0})),"
         " count(distinct e.visit_id) filter (where e.created_at >= to_timestamp({w0})),"
         " count(*) filter (where e.created_at >= to_timestamp({w0}) and e.event_type = 1),"
         " count(distinct e.session_id) filter (where e.created_at < to_timestamp({w0})),"
         " count(*) filter (where e.created_at < to_timestamp({w0}) and e.event_type = 1)"
         " from website w left join website_event e on e.website_id = w.website_id and e.created_at >= to_timestamp({p0})"
         " where w.deleted_at is null group by w.name, w.domain order by 3 desc").format(w0=int(W0), p0=int(P0))
    out = {}
    for l in sh("docker", "exec", "umami-db", "psql", "-U", "umami", "-d", "umami", "-AtF", "|", "-c", q).splitlines():
        name, dom, vis, visits, pv, pvis, ppv = l.split("|")
        out[dom] = {"name": name, "visitors": int(vis), "visits": int(visits), "pv": int(pv), "pvisitors": int(pvis), "ppv": int(ppv)}
    refq = ("select w.domain, e.referrer_domain, count(distinct e.visit_id) c from website_event e join website w using (website_id)"
            f" where e.created_at >= to_timestamp({int(W0)}) and e.referrer_domain <> '' and e.referrer_domain <> w.domain"
            " group by 1, 2 order by 1, 3 desc")
    for l in sh("docker", "exec", "umami-db", "psql", "-U", "umami", "-d", "umami", "-AtF", "|", "-c", refq).splitlines():
        dom, ref, c = l.split("|")
        if dom in out:
            out[dom].setdefault("refs", []).append((ref, int(c)))
    return out


def traefik_errors():
    """Erreurs 5xx et 4xx (hors 401/404) par hôte sur 7 jours, d'après le journal d'accès Traefik."""
    since = datetime.fromtimestamp(W0, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    out = {}
    for path in TRAEFIK_LOGS:
        if not os.path.exists(path):
            continue
        with open(path, errors="replace") as fh:
            for line in fh:
                if '"DownstreamStatus":5' not in line and '"DownstreamStatus":40' not in line and '"DownstreamStatus":42' not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("StartUTC", "")[:19] < since:
                    continue
                code = r.get("DownstreamStatus", 0)
                h = out.setdefault(r.get("RequestHost", ""), {"5xx": 0, "4xx": 0})
                if code >= 500:
                    h["5xx"] += 1
                elif code not in (401, 404):
                    h["4xx"] += 1
    return out


def battistella_section(kw):
    um = safe(umami_week, {})
    errs = safe(traefik_errors, {})
    kuma_by_host = {k["host"]: k for k in kw}
    hosts = list(um) + [h for h in EXTRA_PRODUCTS if h not in um]
    rows = []
    for host in hosts:
        u, k, e = um.get(host), kuma_by_host.get(host), errs.get(host, {})
        parts = []
        if u:
            parts.append(f"{plural(u['visitors'], 'visiteur')} ({evo(u['visitors'], u['pvisitors']) or '='}) · {plural(u['visits'], 'visite')} · {plural(u['pv'], 'page')} vue{'s' if u['pv'] > 1 else ''}")
            if u.get("refs"):
                parts.append("Sources : " + ", ".join(f"{r} {c}" for r, c in u["refs"][:3]))
        if k:
            parts.append(f"Dispo {pct(k['up'], k['n'])}" + (f", {k['incidents']} incident{'s' if k['incidents'] > 1 else ''}" if k["incidents"] else "")
                         + (f" · {k['ping']} ms" if k["ping"] else ""))
        if e.get("5xx") or e.get("4xx"):
            parts.append(f"Erreurs : {e.get('5xx', 0)} en 5xx, {e.get('4xx', 0)} en 4xx (hors 401/404)")
        ok = (not k or kuma_ok(k)) and not e.get("5xx")
        rows.append({"ok": ok, "t": (u or {}).get("name") or (k or {}).get("name") or host, "r": str(u["visitors"]) if u else "",
                     "s": " · ".join(parts) or "Aucune donnée"})
    return {"h": "Services Battistella", "sub": "Fréquentation (Umami), disponibilité (Kuma) et erreurs (Traefik) sur 7 jours", "rows": rows}


def details():
    """Sections de la page de Damien. Chacune est indépendante : une source en panne n'efface que la sienne."""
    kw = safe(kuma_week, [])
    sections = [safe(lambda: battistella_section(kw), None)]
    tech = [safe(lambda: kuma_section(kw), None) if kw else None, safe(backups_section, None), safe(disks_section, None),
            safe(docker_section, None), safe(certs_section, None), safe(dns_section, None), safe(dev_section, None)]
    return {"services": sections[0], "tech": [s for s in tech if s and s["rows"]]}


def main():
    kpis, events = [], []

    gate_now, gate_prev = week_sum(gate())
    gate_days = gate()(B)
    if gate_now or gate_prev:
        kpis.append({"k": "Ouvertures du portail", "v": gate_now, "unit": "", "delta": gate_now - gate_prev, "spark": gate_days})
        if gate_now:
            events.append({"icon": "gate", "t": "Portail", "s": f"Ouvert {gate_now} fois cette semaine", "r": str(gate_now)})

    mus = safe(lambda: music_hours(B), {})
    mus_prev = safe(lambda: music_hours(PB), {})
    tot = sum(sum(v) for v in mus.values())
    tot_prev = sum(sum(v) for v in mus_prev.values())
    if tot or tot_prev:
        diff = tot - tot_prev
        sign = "+" if diff > 0.01 else "−" if diff < -0.01 else ""
        kpis.append({"k": "Musique écoutée", "v": fr_h(tot), "unit": "", "delta": (sign + fr_h(abs(diff))) if sign else "0", "dir": 1 if sign == "+" else -1 if sign else 0,
                     "spark": [round(sum(mus[n][i] for n in mus), 2) for i in range(7)]})
        parts = [f"{n} {fr_h(sum(v))}" for n, v in mus.items() if sum(v) > 0.05]
        if parts:
            events.append({"icon": "music", "t": "Musique", "s": " · ".join(parts), "r": fr_h(tot)})

    med = safe(media, {"items": [], "perDay": [0] * 7, "total": 0, "prev": 0})
    if med["total"] or med["prev"]:
        kpis.append({"k": "Épisodes et films", "v": med["total"], "unit": "", "delta": med["total"] - med["prev"], "spark": med["perDay"]})

    vol, _ = safe(lambda: transitions("cover.tous_les_volets", ("open", "closed"), B, exclude_prev=None), ([0] * 7, None))
    if sum(vol):
        events.append({"icon": "blinds", "t": "Volets", "s": "Ouvertures et fermetures groupées", "r": str(sum(vol))})

    cams = {"portail": "binary_sensor.camera_portail_person_detected", "garage": "binary_sensor.camera_garage_person_detected", "extérieur": "binary_sensor.g5_bullet_personne_detectee"}
    total_cam, last_cam = 0, None
    for name, eid in cams.items():
        c, last = safe(lambda eid=eid: transitions(eid, ("on",), B), ([0] * 7, None))
        total_cam += sum(c)
        if last and (last_cam is None or last > last_cam[0]):
            last_cam = (last, name)
    if total_cam:
        d = datetime.fromtimestamp(last_cam[0], TZ)
        events.append({"icon": "camera", "t": "Caméras", "s": f"Dernière personne détectée {DAY_FULL[d.weekday()]} à {d:%H:%M} ({last_cam[1]})", "r": str(total_cam)})

    photos_d = safe(photos, {"perDay": [0] * 7, "images": 0, "videos": 0, "prev": 0})
    dns_d = safe(dns, {"total": 0, "blocked": 0})
    pres = safe(presence, None)
    temp = safe(temps, None)
    extra = safe(kuma_rows, [])
    rows = extra + [safe(backups, {"ok": False, "t": "Sauvegardes", "s": "Bilan illisible (journaux absents ?)"})]
    warnings = sum(1 for r in rows if not r["ok"])

    notes = safe(notifications, [])
    if notes:
        total = sum(n for _, n in notes)
        events.append({"icon": "bell", "t": "Notifications de la maison",
                       "s": " · ".join(f"{t} {n}" for t, n in notes[:6]) + (f" · + {len(notes) - 6} autres" if len(notes) > 6 else ""),
                       "r": str(total)})

    pil = safe(piles, "")
    if pil:
        events.append({"only": "damien", "icon": "bell", "t": "Piles à changer", "s": pil, "r": str(sum(len(x.split(":", 1)[1].split(",")) for x in pil.rstrip(".").split(". ") if ":" in x))})

    dev = safe(dev_journal, [])
    if dev:
        bad = [r for r, t in dev if t.startswith(("bloqué", "corrigé", "reproduit"))]
        events.append({"only": "damien", "icon": "check", "t": "Code (jardinier, repro Koe)",
                       "s": " · ".join(f"{r} : {t.split(' — ')[0]}" for r, t in dev[-8:]),
                       "r": str(len(dev))})

    bdays, drift = safe(entourage, ([], []))
    agenda = safe(agenda_auto, [])
    projects = safe(projets, [])
    fiches_maj = safe(fiches, [])

    first, last = DAYS[0], DAYS[-1]
    rng = f"Semaine du {first.day if first.day > 1 else '1er'} {MON_FULL[first.month - 1] if first.month != last.month else ''}".rstrip() + f" au {last.day if last.day > 1 else '1er'} {MON_FULL[last.month - 1]} {last.year}"

    out = {
        "range": rng,
        "generated": f"{DAY_FULL[NOW.weekday()]} {NOW.day} {MON_FULL[NOW.month - 1]} à {NOW:%H:%M}",
        "isoDate": TODAY.date().isoformat(),
        "days": DAY_SHORT[:0] + [DAY_SHORT[d.weekday()] for d in DAYS],
        "daysLong": [f"{DAY_FULL[d.weekday()]} {short_day(d)}" for d in DAYS],
        "photos": photos_d,
        "kpis": kpis,
        "presence": pres,
        "temps": temp,
        "events": events,
        "media": med["items"][:5],
        "mediaMore": f"+ {len(med['items']) - 5} autres" if len(med["items"]) > 5 else "",
        "dns": dns_d,
        "birthdays": bdays,
        "drifting": drift,  # retiré des pages autres que celle de Damien (publish.py)
        "agenda": agenda,
        "projects": projects,
        "fiches": fiches_maj,  # retiré des pages autres que celle de Damien (publish.py)
        "tech": {"warnings": warnings, "rows": rows, "meters": safe(disk_meters, [])},
        "detail": details(),  # retiré des pages autres que celle de Damien (publish.py)
        "status": {"ok": not warnings, "text": "Tout est en ordre" if not warnings else f"{warnings} point{'s' if warnings > 1 else ''} à surveiller"},
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
