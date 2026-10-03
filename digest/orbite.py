#!/usr/bin/env python3
"""Lecture seule de la base Orbite (CRM perso) pour le résumé du dimanche et le
rappel d'anniversaire du matin. Aucun nom ni date n'est versionné : tout est lu
à l'exécution.

Règles reprises d'Orbite (apps/api/src/domain/people.ts, interactions.ts) :
- anniversaire : prochaine occurrence de MM-JJ (29/02 fêté le 28 les années non
  bissextiles), horizon 14 jours, âge si l'année est connue (AAAA-MM-JJ ; --MM-JJ
  = année inconnue) ;
- « s'éloigne » : sur les 12 mois (monthly_stat_cache), les 3 derniers mois
  complets comparés au rythme des 8 précédents ramené à 3 mois : rythme habituel
  >= 6, récent <= 40 % de l'habituel, mois en cours < habituel / 3.

Usage autonome : orbite.py today [db] -> JSON des anniversaires du jour (rappel).
"""
import json, sqlite3, sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DB = "/var/lib/docker/volumes/orbite-data/_data/orbite.sqlite"
TZ = ZoneInfo("Europe/Paris")
BIRTHDAY_CIRCLES = ("famille", "amis", "ecole", "voisins")
CLOSE_CIRCLES = ("famille", "amis")
BIRTHDAY_HORIZON_DAYS = 14
DRIFT_MIN_USUAL, DRIFT_RATIO, DRIFTING_MAX = 6, 0.4, 8


def connect(path=DB):
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _people(con):
    """Personnes actives avec leurs cercles : {id: (nom, anniversaire, {cercle: proximité})}."""
    out = {}
    for pid, name, bday, circle, close in con.execute(
            "select p.id, p.display_name, p.birthday, m.circle_key, m.closeness from person p "
            "join membership m on m.person_id = p.id join circle c on c.key = m.circle_key "
            "where p.archived_at is null order by c.ring_order"):
        out.setdefault(pid, (name, bday, {}))[2][circle] = close
    return out


def _next_birthday(bday, today):
    mmdd = bday[-5:]
    def on(year):
        if mmdd == "02-29":
            try:
                return date(year, 2, 29)
            except ValueError:
                return date(year, 2, 28)
        return date(year, int(mmdd[:2]), int(mmdd[3:]))
    nxt = on(today.year)
    return nxt if nxt >= today else on(today.year + 1)


def birthdays(con, today=None, horizon=BIRTHDAY_HORIZON_DAYS):
    today = today or datetime.now(TZ).date()
    labels = dict(con.execute("select key, label from circle"))
    out = []
    for name, bday, circles in _people(con).values():
        keep = [c for c in circles if c in BIRTHDAY_CIRCLES]
        if not bday or not keep:
            continue
        try:
            nxt = _next_birthday(bday, today)
        except ValueError:
            continue
        days = (nxt - today).days
        if days <= horizon:
            year = int(bday[:4]) if bday[:4].isdigit() else None
            out.append({"name": name, "date": nxt.isoformat(), "inDays": days,
                        "turning": nxt.year - year if year else None,
                        "circle": labels.get(keep[0], keep[0]),
                        "close": "famille" in keep or max(circles[c] for c in keep) >= 4})
    return sorted(out, key=lambda b: (b["inDays"], b["name"]))


def _last12_months(today):
    out, y, m = [], today.year, today.month
    for i in range(11, -1, -1):
        yy, mm = divmod((y * 12 + m - 1) - i, 12)
        out.append(f"{yy}-{mm + 1:02d}")
    return out


def drift(series):
    if len(series) != 12:
        return None
    usual = round(sum(series[:8]) / 8 * 3)
    recent, current = sum(series[8:11]), series[11]
    if usual < DRIFT_MIN_USUAL or recent > usual * DRIFT_RATIO or current >= usual / 3:
        return None
    return {"recent": recent, "usual": usual}


def drifting(con, today=None):
    """Proches (famille/amis, proximité >= 4) dont les échanges sont en net recul."""
    today = today or datetime.now(TZ).date()
    months = _last12_months(today)
    monthly = {}
    for pid, month, n in con.execute(
            "select person_id, month, sum(count) from monthly_stat_cache where month >= ? group by 1, 2", (months[0],)):
        monthly.setdefault(pid, {})[month] = n
    last = dict(con.execute("select person_id, last_contact_at from activity_cache"))
    out = []
    for pid, (name, _, circles) in _people(con).items():
        if not any(circles.get(c, 0) >= 4 for c in CLOSE_CIRCLES):
            continue
        d = drift([monthly.get(pid, {}).get(m, 0) for m in months])
        if d:
            out.append({"name": name, **d, "lastContact": (last.get(pid) or "")[:10] or None})
    out.sort(key=lambda x: (x["recent"] / x["usual"], -x["usual"]))
    return out[:DRIFTING_MAX]


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "today":
        raise SystemExit(__doc__)
    con = connect(sys.argv[2] if len(sys.argv) > 2 else DB)
    print(json.dumps([b for b in birthdays(con, horizon=0) if b["close"]], ensure_ascii=False))
