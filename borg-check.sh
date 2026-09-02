#!/bin/bash
# =============================================================================
# borg-check.sh — monthly integrity check of the Hetzner borg repository.
#
# A backup you cannot read is not a backup. borg detects silent corruption
# (bit-rot on the remote, a truncated upload) only if something actually reads
# the chunks back, which no normal `borg create` run does.
#
# --verify-data is deliberately NOT used: it re-downloads every chunk (~230 GB)
# and would take hours on a home uplink every month. The repository + archive
# structural check catches the realistic failure modes; the annual proof that
# the data itself is good is the restore drill (see docs/backups.md).
#
# Shares /var/lock/state-backup.lock with state-backup.sh so the two never hold
# the repo at once. Installed via root crontab: 30 5 1 * *.
# =============================================================================
set -euo pipefail

ENV_FILE="/root/.borg-photos.env"
WEBHOOK_FILE="/root/.borg-discord-webhook"
LOG_PREFIX="[borg-check $(date '+%Y-%m-%d %H:%M')]"
log() { echo "${LOG_PREFIX} $*"; }

notify() {
    local colour="$1" title="$2" msg="$3" url=""
    [ -r "${WEBHOOK_FILE}" ] && url="$(cat "${WEBHOOK_FILE}" 2>/dev/null)"
    [ -z "${url}" ] && return 0
    local payload
    payload="$(python3 -c 'import json,sys;print(json.dumps({"embeds":[{"title":sys.argv[1],"description":sys.argv[2],"color":int(sys.argv[3]),"footer":{"text":"borg-check.sh"}}]}))' \
        "${title}" "${msg}" "${colour}" 2>/dev/null)" || return 0
    curl -s -m 15 --retry 2 -o /dev/null -H "Content-Type: application/json" -d "${payload}" "${url}" || true
}

# shellcheck source=/dev/null
source "${ENV_FILE}"
export BORG_REPO BORG_PASSPHRASE
export BORG_RSH="${BORG_RSH:-ssh -i /root/.ssh/hetzner_borg -p 23 -o BatchMode=yes}"
export BORG_REMOTE_PATH="${BORG_REMOTE_PATH:-borg-1.2}"

log "Starting repository check..."
if borg check --show-rc --lock-wait 3600 2>&1; then
    COUNT="$(borg list --short 2>/dev/null | wc -l)"
    log "Check PASSED (${COUNT} archives)."
    notify 3066993 "🟢 Borg check — OK" "Dépôt Hetzner sain, **${COUNT}** archives."
else
    log "[ERROR] Check FAILED."
    notify 15158332 "🔴 Borg check — ÉCHEC" \
        "Le dépôt Hetzner a échoué au contrôle d'intégrité."$'\n'"Log : \`/var/log/state-backup.log\`"
    exit 1
fi
