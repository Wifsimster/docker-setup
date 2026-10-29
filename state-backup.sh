#!/bin/bash
set -euo pipefail

ENV_FILE="/root/.borg-photos.env"
WEBHOOK_FILE="/root/.borg-discord-webhook"
STAGING="/var/tmp/state-backup-staging"
PG_DUMP_DIR="/opt/docker/pg-backup/backups"
LOCAL_TARBALLS="/home/wifsimster/backups"
DOCS_DIR="/mnt/media/documents"
BIRTHDAY_SNAPSHOTS="/var/lib/docker/volumes/birthday-invitation_birthday_backups/_data"
RACONTINE_UPLOADS="/opt/docker/racontine/uploads"
NAS_PG_DIR="/mnt/media/data/backups/postgres"
NAS_KEEP_DAYS=14

LOG_PREFIX="[state-backup $(date '+%Y-%m-%d %H:%M')]"
log() { echo "${LOG_PREFIX} $*"; }

notify() {
    local colour="$1" title="$2" msg="$3" url=""
    [ "${colour}" = 3066993 ] && return 0
    local h; h="$(TZ=Europe/Paris date +%-H)"
    { [ "${h}" -ge 23 ] || [ "${h}" -lt 8 ]; } && return 0
    [ -r "${WEBHOOK_FILE}" ] && url="$(cat "${WEBHOOK_FILE}" 2>/dev/null)"
    [ -z "${url}" ] && return 0
    local payload
    payload="$(python3 -c 'import json,sys;print(json.dumps({"embeds":[{"title":sys.argv[1],"description":sys.argv[2],"color":int(sys.argv[3]),"footer":{"text":"state-backup.sh"}}]}))' \
        "${title}" "${msg}" "${colour}" 2>/dev/null)" || return 0
    curl -s -m 15 --retry 2 -o /dev/null \
        -H "Content-Type: application/json" -d "${payload}" "${url}" || true
}

FAILED_STEP="startup"
on_error() {
    log "[ERROR] failed during: ${FAILED_STEP}"
    notify 15158332 "🔴 Backup state — ÉCHEC" \
        "Échec pendant : **${FAILED_STEP}**"$'\n'"Log : \`/var/log/state-backup.log\`"
    rm -rf "${STAGING}"
}
trap on_error ERR

WARNINGS=""
warn() { log "[WARN] $*"; WARNINGS="${WARNINGS}• $*"$'\n'; }

FAILED_STEP="lecture de ${ENV_FILE}"
[ -r "${ENV_FILE}" ] || { log "[ERROR] ${ENV_FILE} missing"; exit 1; }
# shellcheck source=/dev/null
source "${ENV_FILE}"
: "${BORG_REPO:?BORG_REPO not set}"
: "${BORG_PASSPHRASE:?BORG_PASSPHRASE not set}"
export BORG_REPO BORG_PASSPHRASE
export BORG_RSH="${BORG_RSH:-ssh -i /root/.ssh/hetzner_borg -p 23 -o BatchMode=yes}"
export BORG_REMOTE_PATH="${BORG_REMOTE_PATH:-borg-1.2}"

FAILED_STEP="vérification du montage NFS"
mountpoint -q /mnt/media || { log "[ERROR] /mnt/media not mounted - aborting."; exit 1; }
[ -d "${DOCS_DIR}" ] || { log "[ERROR] ${DOCS_DIR} missing - stale mount? aborting."; exit 1; }
log "NFS mount verified."

FAILED_STEP="contrôle de fraîcheur des dumps pg"
NEWEST="$(find "${PG_DUMP_DIR}" -name '*.dump' -mmin -1560 2>/dev/null | wc -l)"
if [ "${NEWEST}" -eq 0 ]; then
    warn "Aucun dump Postgres de moins de 26 h — pg-backup ne tourne plus ?"
fi

FAILED_STEP="snapshots SQLite"
rm -rf "${STAGING}"
mkdir -p "${STAGING}/sqlite"

snapshot_sqlite() {
    local name="$1" src="$2"
    if [ ! -f "${src}" ]; then
        warn "SQLite ${name} introuvable (${src}) — ignoré."
        return 0
    fi
    if sqlite3 "${src}" ".backup '${STAGING}/sqlite/${name}.sqlite3'" 2>/dev/null; then
        if sqlite3 "${STAGING}/sqlite/${name}.sqlite3" 'PRAGMA quick_check;' 2>/dev/null | head -1 | grep -q '^ok$'; then
            log "  ${name}: $(du -h "${STAGING}/sqlite/${name}.sqlite3" | cut -f1) (quick_check ok)"
        else
            warn "SQLite ${name}: quick_check ÉCHOUÉ sur le snapshot."
        fi
    else
        warn "SQLite ${name}: .backup a échoué."
    fi
}

snapshot_sqlite vaultwarden  /opt/docker/vaultwarden/data/db.sqlite3
snapshot_sqlite solopilot    /var/lib/docker/volumes/solopilot_bot-data/_data/bot.db
snapshot_sqlite zigbee       /opt/docker/home-assistant/config/zigbee.db
snapshot_sqlite birthday     /var/lib/docker/volumes/birthday-invitation_birthday_db/_data/rsvp.db
snapshot_sqlite actual       /opt/docker/actual/data/server-files/account.sqlite
snapshot_sqlite orbite       /var/lib/docker/volumes/orbite-data/_data/orbite.sqlite

if [ -d /opt/docker/actual/data/user-files ]; then
    tar -czf "${STAGING}/sqlite/actual-user-files.tar.gz" \
        -C /opt/docker/actual/data user-files 2>/dev/null || \
        warn "tar des user-files actual a échoué."
fi

cp -a /opt/docker/vaultwarden/data/rsa_key.pem "${STAGING}/sqlite/vaultwarden-rsa_key.pem" 2>/dev/null || \
    warn "vaultwarden rsa_key.pem introuvable."
if [ -d /opt/docker/vaultwarden/data/attachments ]; then
    tar -czf "${STAGING}/sqlite/vaultwarden-attachments.tar.gz" \
        -C /opt/docker/vaultwarden/data attachments 2>/dev/null || \
        warn "tar des attachments vaultwarden a échoué."
fi

FAILED_STEP="archive des configs"
find /opt/docker -mindepth 2 -maxdepth 2 \( -name '.env' -o -name '.env.*' -o -name 'compose.yml' \) \
    -printf '%P\n' 2>/dev/null | sort > "${STAGING}/config-list.txt"
tar -czf "${STAGING}/configs.tar.gz" -C /opt/docker -T "${STAGING}/config-list.txt"
log "Configs archived ($(wc -l < "${STAGING}/config-list.txt") files, $(du -h "${STAGING}/configs.tar.gz" | cut -f1))."

FAILED_STEP="copie des dumps pg vers le NAS"
mkdir -p "${NAS_PG_DIR}"
cp -u "${PG_DUMP_DIR}"/*.dump "${NAS_PG_DIR}/" 2>/dev/null || warn "copie NAS des dumps incomplète."
find "${NAS_PG_DIR}" -name '*.dump' -mtime +${NAS_KEEP_DAYS} -delete 2>/dev/null || true
log "PG dumps mirrored to NAS ($(ls -1 "${NAS_PG_DIR}"/*.dump 2>/dev/null | wc -l) files)."

FAILED_STEP="borg create"
ARCHIVE="data-{now:%Y%m%d-%H%M}"
borg create \
    --stats --show-rc \
    --compression auto,zstd,3 \
    --exclude-caches \
    --noxattrs \
    --lock-wait 1800 \
    --exclude "${PG_DUMP_DIR}/immich_*.dump" \
    "::${ARCHIVE}" \
    "${STAGING}" \
    "${PG_DUMP_DIR}" \
    "${LOCAL_TARBALLS}" \
    "${BIRTHDAY_SNAPSHOTS}" \
    "${RACONTINE_UPLOADS}" \
    "${DOCS_DIR}"
log "Archive created."

rm -rf "${STAGING}"

FAILED_STEP="borg prune"
borg prune --list --show-rc \
    --glob-archives 'data-*' \
    --keep-daily 14 \
    --keep-weekly 8 \
    --keep-monthly 12 \
    --keep-yearly 3
log "Prune applied (14 daily, 8 weekly, 12 monthly, 3 yearly)."

FAILED_STEP="borg compact"
borg compact
log "Compact done."

FAILED_STEP="rapport final"
trap - ERR
COUNT="$(borg list --short --glob-archives 'data-*' 2>/dev/null | wc -l)"
SIZE="$(borg info --json 2>/dev/null | python3 -c 'import json,sys;s=json.load(sys.stdin)["cache"]["stats"];print("%.1f Go uniques" % (s["unique_csize"]/1e9))' 2>/dev/null || echo "taille indisponible")"

if [ -n "${WARNINGS}" ]; then
    log "Done WITH WARNINGS. ${COUNT} archives data-*, ${SIZE}."
    notify 16776960 "🟠 Backup state — OK avec avertissements" \
        "**${COUNT}** archives \`data-*\`, dépôt : ${SIZE}"$'\n\n'"${WARNINGS}"
else
    log "Done. ${COUNT} archives data-*, ${SIZE}."
    notify 3066993 "🟢 Backup state — OK" \
        "**${COUNT}** archives \`data-*\` sur Hetzner"$'\n'"Dépôt : ${SIZE}"
fi
