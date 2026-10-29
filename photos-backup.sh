#!/bin/bash
set -euo pipefail

ENV_FILE="/root/.borg-photos.env"
SRC_DIR="/mnt/media/photos"
SENTINEL="${SRC_DIR}/.backup-sentinel"
STAGING="/var/tmp/photos-backup-staging"
WEBHOOK_FILE="/root/.borg-discord-webhook"
PG_CONTAINER="immich_postgres"
PG_USER="postgres"

LOG_PREFIX="[photos-backup $(date '+%Y-%m-%d %H:%M')]"
log() { echo "${LOG_PREFIX} $*"; }

notify() {
    local colour="$1" title="$2" msg="$3" url=""
    [ "${colour}" = 3066993 ] && return 0
    local h; h="$(TZ=Europe/Paris date +%-H)"
    { [ "${h}" -ge 23 ] || [ "${h}" -lt 8 ]; } && return 0
    [ -r "${WEBHOOK_FILE}" ] && url="$(cat "${WEBHOOK_FILE}" 2>/dev/null)"
    [ -z "${url}" ] && return 0
    local payload
    payload="$(python3 -c 'import json,sys;print(json.dumps({"embeds":[{"title":sys.argv[1],"description":sys.argv[2],"color":int(sys.argv[3]),"footer":{"text":"photos-backup.sh"}}]}))' \
        "${title}" "${msg}" "${colour}" 2>/dev/null)" || return 0
    curl -s -m 15 --retry 2 -o /dev/null \
        -H "Content-Type: application/json" -d "${payload}" "${url}" || true
}

FAILED_STEP="startup"
on_error() {
    log "[ERROR] failed during: ${FAILED_STEP}"
    notify 15158332 "🔴 Backup photos — ÉCHEC" \
        "Échec pendant : **${FAILED_STEP}**"$'\n'"Log : \`/var/log/photos-backup.log\`"
}
trap on_error ERR

FAILED_STEP="lecture de ${ENV_FILE}"
if [ ! -r "${ENV_FILE}" ]; then
    log "[ERROR] ${ENV_FILE} missing or unreadable."
    exit 1
fi
RATE_LIMIT_OVERRIDE="${RATE_LIMIT_KIBS:-}"

# shellcheck source=/dev/null
source "${ENV_FILE}"
[ -n "${RATE_LIMIT_OVERRIDE}" ] && RATE_LIMIT_KIBS="${RATE_LIMIT_OVERRIDE}"
: "${BORG_REPO:?BORG_REPO not set in ${ENV_FILE}}"
: "${BORG_PASSPHRASE:?BORG_PASSPHRASE not set in ${ENV_FILE}}"
export BORG_REPO BORG_PASSPHRASE
export BORG_RSH="${BORG_RSH:-ssh -i /root/.ssh/hetzner_borg -p 23 -o BatchMode=yes}"
export BORG_REMOTE_PATH="${BORG_REMOTE_PATH:-borg-1.2}"
RATE_LIMIT_KIBS="${RATE_LIMIT_KIBS:-0}"

FAILED_STEP="vérification du montage NFS"
if ! mountpoint -q /mnt/media; then
    log "[ERROR] /mnt/media not mounted - aborting before borg sees an empty tree."
    exit 1
fi
if ! head -c 1 "${SENTINEL}" >/dev/null 2>&1; then
    log "[ERROR] sentinel ${SENTINEL} unreadable (stale NFS handle?) - aborting."
    exit 1
fi
if [ ! -d "${SRC_DIR}/upload" ]; then
    log "[ERROR] ${SRC_DIR}/upload missing - aborting."
    exit 1
fi
log "NFS mount verified."

FAILED_STEP="pg_dumpall de ${PG_CONTAINER}"
rm -rf "${STAGING}"
mkdir -p "${STAGING}"
docker exec -t "${PG_CONTAINER}" pg_dumpall --clean --if-exists --username="${PG_USER}" \
    | gzip > "${STAGING}/immich-db.sql.gz"
if [ ! -s "${STAGING}/immich-db.sql.gz" ]; then
    log "[ERROR] immich-db.sql.gz is empty - aborting rather than archiving a useless dump."
    exit 1
fi
log "Immich DB dumped ($(du -h "${STAGING}/immich-db.sql.gz" | cut -f1))."

FAILED_STEP="borg create"
ARCHIVE="photos-{now:%Y%m%d-%H%M}"
RATE_ARG=()
[ "${RATE_LIMIT_KIBS}" -gt 0 ] && RATE_ARG=(--upload-ratelimit "${RATE_LIMIT_KIBS}")

borg create \
    --stats --show-rc \
    --compression auto,zstd,3 \
    --exclude-caches \
    --noxattrs \
    --lock-wait 600 \
    "${RATE_ARG[@]}" \
    --exclude "${SRC_DIR}/thumbs" \
    --exclude "${SRC_DIR}/encoded-video" \
    "::${ARCHIVE}" \
    "${SRC_DIR}" \
    "${STAGING}"
log "Archive created."

rm -rf "${STAGING}"

FAILED_STEP="borg prune"
borg prune --list --show-rc \
    --glob-archives 'photos-*' \
    --keep-weekly 8 \
    --keep-monthly 12 \
    --keep-yearly 5
log "Prune applied (8 weekly, 12 monthly, 5 yearly)."

FAILED_STEP="borg compact"
borg compact
log "Compact done."

FAILED_STEP="rapport final"
trap - ERR
SIZE="$(borg info --json 2>/dev/null | python3 -c 'import json,sys;s=json.load(sys.stdin)["cache"]["stats"];print("%.1f Go uniques, %.1f Go bruts" % (s["unique_csize"]/1e9, s["total_size"]/1e9))' 2>/dev/null || echo "taille indisponible")"
COUNT="$(borg list --short 2>/dev/null | wc -l)"
log "Done. ${COUNT} archives, ${SIZE}."
notify 3066993 "🟢 Backup photos — OK" \
    "**${COUNT}** archives sur Hetzner Storage Box"$'\n'"Occupation : ${SIZE}"
