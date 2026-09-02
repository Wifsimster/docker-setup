#!/bin/bash
# =============================================================================
# state-backup.sh — daily OFFSITE backup of everything that is not photos.
#
# photos-backup.sh already puts /mnt/media/photos on the Hetzner Storage Box.
# This script covers the rest of the irreplaceable state, which until now lived
# in exactly one place:
#
#   SQLite databases      pg_dump can't see these; they had NO backup at all.
#     vaultwarden           the password manager — the single least
#                           recoverable thing on this host
#     solopilot bot.db      CRM, invoices, accounting
#     birthday rsvp.db      (its sidecar snapshots; the sidecar writes to a
#                           local docker volume that never left the disk)
#     zigbee.db             ZHA network — losing it means re-pairing the fleet
#
#   Postgres dumps        /opt/docker/pg-backup/backups sat on the SAME disk as
#                         the databases it protects. One dead disk lost both.
#
#   Service configs       every /opt/docker/*/.env + compose.yml. The .env files
#                         hold secrets and are (correctly) gitignored, so the
#                         docker-setup repo does NOT protect them.
#
#   Weekly tarballs       /home/wifsimster/backups (gramps + HA config), which
#                         previously only ever reached the NAS — i.e. the LAN,
#                         not offsite.
#
#   Paperless documents   /mnt/media/documents, scanned admin/legal papers. NAS
#                         only until now, despite being as irreplaceable as the
#                         photos and 0.3% of their size.
#
# SQLITE CONSISTENCY: every SQLite DB here is in WAL mode with an active -wal
# file. `cp` of a live WAL database yields a torn, possibly unopenable copy, so
# each one goes through `sqlite3 .backup`, which takes a proper read lock and
# checkpoints into a standalone file. That is also why the archive contains a
# *snapshot* of zigbee.db rather than the live one.
#
# WHY IMMICH'S DUMP IS EXCLUDED: photos-backup.sh already pg_dumpall's immich
# into the weekly photos archive. Its dump is ~115 MB of incompressible,
# poorly-deduplicating data that changes every night; archiving it daily here
# would add ~40 GB/year to the repo to duplicate something already offsite —
# and restoring photos + DB from the same Sunday is more consistent anyway.
#
# SEPARATE ARCHIVE PREFIX: archives are named data-* and pruned with
# --glob-archives 'data-*'. photos-backup.sh prunes 'photos-*'. Neither can
# retire the other's archives, so the two schedules stay independent while
# sharing one repo, one key, and one dedup pool.
#
# Config + secrets are read from /root/.borg-photos.env (same repo/passphrase).
# Installed via root crontab: 45 4 * * * (daily 04:45, after pg-backup at 03:00),
# wrapped in `flock -n /var/lock/state-backup.lock`.
# =============================================================================
set -euo pipefail

ENV_FILE="/root/.borg-photos.env"
WEBHOOK_FILE="/root/.borg-discord-webhook"
STAGING="/var/tmp/state-backup-staging"
PG_DUMP_DIR="/opt/docker/pg-backup/backups"
LOCAL_TARBALLS="/home/wifsimster/backups"
DOCS_DIR="/mnt/media/documents"
BIRTHDAY_SNAPSHOTS="/var/lib/docker/volumes/birthday-invitation_birthday_backups/_data"
NAS_PG_DIR="/mnt/media/data/backups/postgres"
NAS_KEEP_DAYS=14

LOG_PREFIX="[state-backup $(date '+%Y-%m-%d %H:%M')]"
log() { echo "${LOG_PREFIX} $*"; }

# Best-effort Discord push; never fails the run. Mirrors photos-backup.sh.
notify() {
    local colour="$1" title="$2" msg="$3" url=""
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

# -----------------------------------------------------------------------------
# 0. Config
# -----------------------------------------------------------------------------
FAILED_STEP="lecture de ${ENV_FILE}"
[ -r "${ENV_FILE}" ] || { log "[ERROR] ${ENV_FILE} missing"; exit 1; }
# shellcheck source=/dev/null
source "${ENV_FILE}"
: "${BORG_REPO:?BORG_REPO not set}"
: "${BORG_PASSPHRASE:?BORG_PASSPHRASE not set}"
export BORG_REPO BORG_PASSPHRASE
export BORG_RSH="${BORG_RSH:-ssh -i /root/.ssh/hetzner_borg -p 23 -o BatchMode=yes}"
export BORG_REMOTE_PATH="${BORG_REMOTE_PATH:-borg-1.2}"

# -----------------------------------------------------------------------------
# 1. NFS guard — the NAS copy and the documents tree both depend on it
# -----------------------------------------------------------------------------
FAILED_STEP="vérification du montage NFS"
mountpoint -q /mnt/media || { log "[ERROR] /mnt/media not mounted - aborting."; exit 1; }
[ -d "${DOCS_DIR}" ] || { log "[ERROR] ${DOCS_DIR} missing - stale mount? aborting."; exit 1; }
log "NFS mount verified."

# -----------------------------------------------------------------------------
# 2. Dead-man's switch for pg-backup
#
# pg-backup runs on crond INSIDE its own container. If that container dies or
# its crond wedges, nothing dumps and nothing complains — the failure alert
# only fires for a dump that ran and failed. Checking dump freshness from a
# different process on a different scheduler is what actually catches that.
# -----------------------------------------------------------------------------
FAILED_STEP="contrôle de fraîcheur des dumps pg"
NEWEST="$(find "${PG_DUMP_DIR}" -name '*.dump' -mmin -1560 2>/dev/null | wc -l)"
if [ "${NEWEST}" -eq 0 ]; then
    warn "Aucun dump Postgres de moins de 26 h — pg-backup ne tourne plus ?"
fi

# -----------------------------------------------------------------------------
# 3. Consistent SQLite snapshots
# -----------------------------------------------------------------------------
FAILED_STEP="snapshots SQLite"
rm -rf "${STAGING}"
mkdir -p "${STAGING}/sqlite"

snapshot_sqlite() {
    local name="$1" src="$2"
    if [ ! -f "${src}" ]; then
        warn "SQLite ${name} introuvable (${src}) — ignoré."
        return 0
    fi
    # .backup is an online backup: it takes a read lock and produces a
    # standalone, checkpointed file. Never `cp` a live WAL database.
    if sqlite3 "${src}" ".backup '${STAGING}/sqlite/${name}.sqlite3'" 2>/dev/null; then
        # An unreadable snapshot is worse than no snapshot, because it looks
        # like success. Prove it opens and passes a structural check.
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

# Vaultwarden's attachments and RSA signing key live beside the DB and are just
# as required for a working restore as the database itself.
cp -a /opt/docker/vaultwarden/data/rsa_key.pem "${STAGING}/sqlite/vaultwarden-rsa_key.pem" 2>/dev/null || \
    warn "vaultwarden rsa_key.pem introuvable."
if [ -d /opt/docker/vaultwarden/data/attachments ]; then
    tar -czf "${STAGING}/sqlite/vaultwarden-attachments.tar.gz" \
        -C /opt/docker/vaultwarden/data attachments 2>/dev/null || \
        warn "tar des attachments vaultwarden a échoué."
fi

# -----------------------------------------------------------------------------
# 4. Service configs — .env files are gitignored, so the repo does not save them
# -----------------------------------------------------------------------------
FAILED_STEP="archive des configs"
find /opt/docker -mindepth 2 -maxdepth 2 \( -name '.env' -o -name '.env.*' -o -name 'compose.yml' \) \
    -printf '%P\n' 2>/dev/null | sort > "${STAGING}/config-list.txt"
tar -czf "${STAGING}/configs.tar.gz" -C /opt/docker -T "${STAGING}/config-list.txt"
log "Configs archived ($(wc -l < "${STAGING}/config-list.txt") files, $(du -h "${STAGING}/configs.tar.gz" | cut -f1))."

# -----------------------------------------------------------------------------
# 5. Second on-site copy of the pg dumps (NAS), so a dead host disk is survivable
#    without reaching for the offsite repo
# -----------------------------------------------------------------------------
FAILED_STEP="copie des dumps pg vers le NAS"
mkdir -p "${NAS_PG_DIR}"
cp -u "${PG_DUMP_DIR}"/*.dump "${NAS_PG_DIR}/" 2>/dev/null || warn "copie NAS des dumps incomplète."
find "${NAS_PG_DIR}" -name '*.dump' -mtime +${NAS_KEEP_DAYS} -delete 2>/dev/null || true
log "PG dumps mirrored to NAS ($(ls -1 "${NAS_PG_DIR}"/*.dump 2>/dev/null | wc -l) files)."

# -----------------------------------------------------------------------------
# 6. Offsite archive
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# 7. Report
# -----------------------------------------------------------------------------
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
