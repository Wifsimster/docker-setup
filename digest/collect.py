#!/usr/bin/env python3
"""Collecte l'activité de la maison sur 7 jours (lecture seule) et écrit du JSON sur stdout."""
import json, os, re, sqlite3, subprocess
from datetime import datetime, timedelta, timezone
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


def disk_meters():
    out = []
    for label, path in (("Disque du serveur Docker", "/"), ("Stockage Unraid", "/mnt/media")):
        try:
            st = os.statvfs(path)
            out.append({"l": label, "p": round(100 * (1 - st.f_bavail / st.f_blocks))})
        except OSError:
            pass
    return out


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
        "tech": {"warnings": warnings, "rows": rows, "meters": safe(disk_meters, [])},
        "status": {"ok": not warnings, "text": "Tout est en ordre" if not warnings else f"{warnings} point{'s' if warnings > 1 else ''} à surveiller"},
    }
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
