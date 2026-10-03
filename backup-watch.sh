#!/bin/bash
# =============================================================================
# backup-watch.sh — the only voice of the backup jobs in Discord #backups.
#
# Since 2026-10-03 the jobs themselves (state-backup, photos-backup, borg-check)
# no longer post a 🟢 on every success and stay silent during quiet hours
# (23:00-08:00 Europe/Paris) — they all run in that window. This script reads
# their logs once a day, outside quiet hours, and:
#   - posts 🔴 if a job failed or MISSED its run (no success in the expected
#     window: state 26 h, weekly jobs 8 days), with the last error line;
#   - posts 🟠 if the last state-backup run logged warnings;
#   - posts one 🟢 weekly summary on Sunday when everything is fine;
#   - otherwise says nothing.
#
# Read-only on the logs. Installed via root crontab: 15 7 * * * (07:15 UTC =
# 08:15/09:15 Paris, after borg-check's 05:30 slot).
# =============================================================================
set -uo pipefail

WEBHOOK_FILE="/root/.borg-discord-webhook"

notify() {
    local colour="$1" title="$2" msg="$3" url=""
    [ -r "${WEBHOOK_FILE}" ] && url="$(cat "${WEBHOOK_FILE}" 2>/dev/null)"
    [ -z "${url}" ] && return 0
    local payload
    payload="$(python3 -c 'import json,sys;print(json.dumps({"embeds":[{"title":sys.argv[1],"description":sys.argv[2],"color":int(sys.argv[3]),"footer":{"text":"backup-watch.sh"}}]}))' \
        "${title}" "${msg}" "${colour}" 2>/dev/null)" || return 0
    curl -s -m 15 --retry 2 -o /dev/null \
        -H "Content-Type: application/json" -d "${payload}" "${url}" || true
}

# Prints "<colour>\t<title>\t<message>" or nothing. Log timestamps are UTC (VM TZ).
REPORT="$(python3 - <<'PY'
import re, os
from datetime import datetime, timezone

NOW = datetime.now(timezone.utc).replace(tzinfo=None)
PAT = re.compile(r"^\[(\S+) (\d{4}-\d\d-\d\d \d\d:\d\d)\] (.*)$")

def lines(name):
    out = []
    for f in (f"/var/log/{name}.log.1", f"/var/log/{name}.log"):
        if os.path.exists(f):
            with open(f, errors="replace") as fh:
                for l in fh:
                    m = PAT.match(l.rstrip("\n"))
                    if m:
                        out.append((m.group(1), datetime.strptime(m.group(2), "%Y-%m-%d %H:%M"), m.group(3)))
    return out

def last(rows, tag, test):
    hit = [r for r in rows if r[0] == tag and test(r[2])]
    return hit[-1] if hit else None

def age(r):
    return (NOW - r[1]).total_seconds() / 3600 if r else None

def fmt(r):
    return r[1].strftime("%d/%m %H:%M UTC") if r else "jamais (logs)"

state = lines("state-backup")
jobs = [
    # label, log, tag, success test, max age (h)
    ("State (quotidien)", state, "state-backup", lambda m: m.startswith("Done"), 26),
    ("Photos (hebdo)", lines("photos-backup"), "photos-backup", lambda m: m.startswith("Done"), 192),
    ("Gramps (hebdo)", lines("gramps-backup"), "gramps-backup", lambda m: m.endswith("Done."), 192),
    ("HA config (hebdo)", lines("ha-config-backup"), "ha-config-backup", lambda m: m.endswith("Done."), 192),
]

red, summary = [], []
for label, rows, tag, ok, max_h in jobs:
    s = last(rows, tag, ok)
    e = last(rows, tag, lambda m: "[ERROR]" in m)
    a = age(s)
    if a is None or a > max_h or (e and (not s or e[1] > s[1])):
        msg = f"**{label}** : dernier succès {fmt(s)}"
        if e and (not s or e[1] > s[1]):
            msg += f"\n↳ {e[2]} ({fmt(e)})"
        red.append(msg)
    else:
        summary.append(f"{label} : OK {fmt(s)}")

# borg-check is monthly: only its latest verdict matters.
c = last(state, "borg-check", lambda m: "PASSED" in m or "FAILED" in m)
if c and "FAILED" in c[2]:
    red.append(f"**Borg check** : ÉCHEC le {fmt(c)}")
elif c:
    summary.append(f"Borg check : OK {fmt(c)}")

# Warnings of the latest state-backup run only (they repeat until fixed).
start = None
for i, r in enumerate(state):
    if r[0] == "state-backup" and r[2].startswith("Done"):
        start = i
warns = []
if start is not None:
    run_time = state[start][1]
    warns = [r[2].replace("[WARN] ", "") for r in state if r[0] == "state-backup" and r[1] == run_time and "[WARN]" in r[2]]

if red:
    print("15158332\t🔴 Backups — action requise\t" + "\n".join(red).replace("\t", " ").replace("\n", "\\n"))
elif warns:
    print("16776960\t🟠 Backup state — avertissements\t" + "\\n".join("• " + w for w in warns).replace("\t", " "))
elif NOW.weekday() == 6:
    print("3066993\t🟢 Backups — bilan de la semaine\t" + "\\n".join(summary).replace("\t", " "))
PY
)"

[ -z "${REPORT}" ] && { echo "[backup-watch $(date '+%Y-%m-%d %H:%M')] RAS"; exit 0; }
IFS=$'\t' read -r COLOUR TITLE MSG <<< "${REPORT}"
MSG="${MSG//\\n/$'\n'}"
echo "[backup-watch $(date '+%Y-%m-%d %H:%M')] ${TITLE}"
notify "${COLOUR}" "${TITLE}" "${MSG}"
