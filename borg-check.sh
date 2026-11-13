#!/bin/bash
set -euo pipefail

ENV_FILE="/root/.borg-photos.env"
WEBHOOK_FILE="/root/.borg-discord-webhook"
LOG_PREFIX="[borg-check $(date '+%Y-%m-%d %H:%M')]"
log() { echo "${LOG_PREFIX} $*"; }

notify() {
    local colour="$1" title="$2" msg="$3" url=""
    [ "${colour}" = 3066993 ] && return 0
    local h; h="$(TZ=Europe/Paris date +%-H)"
    { [ "${h}" -ge 23 ] || [ "${h}" -lt 8 ]; } && return 0
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
