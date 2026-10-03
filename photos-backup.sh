#!/bin/bash
# =============================================================================
# photos-backup.sh — weekly OFFSITE backup of the Immich photo library to a
# Hetzner Storage Box, using BorgBackup (client-side encrypted, deduplicated).
#
# This is the only copy that survives the house burning down. The NAS holds the
# primary; borg holds the offsite. Restores are free and instant on Hetzner, so
# the restore drill is actually testable — that was the whole point of picking
# it over Glacier.
#
# WHAT GOES IN (~340 GB on first run, a few GB per week after):
#   /mnt/media/photos          Immich originals (upload/), Léo/, albums, zips
#   staging/immich-db.sql.gz   pg_dumpall of immich_postgres
#
# WHAT IS EXCLUDED (~44 GB, regenerable by Immich after a restore):
#   photos/thumbs              12 GB of generated thumbnails
#   photos/encoded-video       32 GB of transcodes
#
# WHY THE DB DUMP MATTERS: without it a restore gives back ~20k loose files
# with no albums, no faces, no favourites, no shared links. The bytes are the
# easy part; the organisation is what is painful to recreate.
#
# NFS GUARD: /mnt/media drops often enough that nas-watchdog.timer exists for
# it. A borg run against a silently-empty mount would record an archive where
# every photo "disappeared", and prune would eventually retire the good ones.
# So the run aborts unless the mount is live AND the sentinel file reads back.
#
# Config + secrets live in /root/.borg-photos.env (chmod 600), never here.
# Installed via root crontab: 30 2 * * 0 (Sundays 02:30, after ha-config-backup),
# wrapped in `flock -n /var/lock/photos-backup.lock`. A run that overruns a week
# is skipped rather than queued: two borg clients on one repo means the second
# blocks on the lock, then fails and pages for a problem that does not exist.
# =============================================================================
set -euo pipefail

ENV_FILE="/root/.borg-photos.env"
SRC_DIR="/mnt/media/photos"
SENTINEL="${SRC_DIR}/.backup-sentinel"
STAGING="/var/tmp/photos-backup-staging"
WEBHOOK_FILE="/root/.borg-discord-webhook"   # Discord #backups, catégorie Homelab
PG_CONTAINER="immich_postgres"
PG_USER="postgres"

LOG_PREFIX="[photos-backup $(date '+%Y-%m-%d %H:%M')]"
log() { echo "${LOG_PREFIX} $*"; }

# notify <colour> <title> <message> — best-effort Discord push (never fails the run).
# colour is a decimal RGB int: 3066993 green (success), 15158332 red (failure).
# Sent as an embed rather than plain content so a failure is visible at a glance
# in the channel list, and so the message survives Discord's markdown mangling.
notify() {
    local colour="$1" title="$2" msg="$3" url=""
    # 2026-10-03 : succès muets et rien la nuit (23h-08h Paris) ; backup-watch.sh
    # (07:15 UTC) signale échecs, retards et avertissements + bilan du dimanche.
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

# Any unexpected exit is a failed backup — say so loudly rather than fail silently.
FAILED_STEP="startup"
on_error() {
    log "[ERROR] failed during: ${FAILED_STEP}"
    notify 15158332 "🔴 Backup photos — ÉCHEC" \
        "Échec pendant : **${FAILED_STEP}**"$'\n'"Log : \`/var/log/photos-backup.log\`"
}
trap on_error ERR

# -----------------------------------------------------------------------------
# 0. Config
# -----------------------------------------------------------------------------
FAILED_STEP="lecture de ${ENV_FILE}"
if [ ! -r "${ENV_FILE}" ]; then
    log "[ERROR] ${ENV_FILE} missing or unreadable."
    exit 1
fi
# A value passed on the command line must win over the env file, not the other
# way round — otherwise a one-off `RATE_LIMIT_KIBS=... photos-backup.sh` is
# silently ignored. Note `sudo` strips the environment unless you use `sudo -E`.
RATE_LIMIT_OVERRIDE="${RATE_LIMIT_KIBS:-}"

# shellcheck source=/dev/null
source "${ENV_FILE}"
[ -n "${RATE_LIMIT_OVERRIDE}" ] && RATE_LIMIT_KIBS="${RATE_LIMIT_OVERRIDE}"
: "${BORG_REPO:?BORG_REPO not set in ${ENV_FILE}}"
: "${BORG_PASSPHRASE:?BORG_PASSPHRASE not set in ${ENV_FILE}}"
export BORG_REPO BORG_PASSPHRASE
export BORG_RSH="${BORG_RSH:-ssh -i /root/.ssh/hetzner_borg -p 23 -o BatchMode=yes}"
# Hetzner exposes several server-side borg binaries (borg, borg-1.2, borg-1.4).
# Pin 1.2 to match the client: the bare `borg` path is a moving target and a
# silent switch to 1.4 would break the repo format mid-life.
export BORG_REMOTE_PATH="${BORG_REMOTE_PATH:-borg-1.2}"
RATE_LIMIT_KIBS="${RATE_LIMIT_KIBS:-0}"

# -----------------------------------------------------------------------------
# 1. NFS guard — refuse to back up a mount that is present but not readable
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# 2. Dump the Immich database into the staging dir
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# 3. Create the archive
# -----------------------------------------------------------------------------
FAILED_STEP="borg create"
ARCHIVE="photos-{now:%Y%m%d-%H%M}"
RATE_ARG=()
[ "${RATE_LIMIT_KIBS}" -gt 0 ] && RATE_ARG=(--upload-ratelimit "${RATE_LIMIT_KIBS}")

# auto,zstd,3: borg probes each chunk and skips compression when it does not
# pay off. JPEG and H.264 are already compressed; the DB dump is not.
# --noxattrs: the only xattr on this tree is system.nfs4_acl, which the NFS
# client synthesises from the mode bits rather than reading from the NAS. Storing
# it buys nothing and makes every restore to a non-NFS target spew "Operation not
# supported" warnings that would bury a real error in the log.
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

# -----------------------------------------------------------------------------
# 4. Retention — dedup means old archives cost only what actually changed
# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
# 5. Report
# -----------------------------------------------------------------------------
FAILED_STEP="rapport final"
trap - ERR
SIZE="$(borg info --json 2>/dev/null | python3 -c 'import json,sys;s=json.load(sys.stdin)["cache"]["stats"];print("%.1f Go uniques, %.1f Go bruts" % (s["unique_csize"]/1e9, s["total_size"]/1e9))' 2>/dev/null || echo "taille indisponible")"
COUNT="$(borg list --short 2>/dev/null | wc -l)"
log "Done. ${COUNT} archives, ${SIZE}."
notify 3066993 "🟢 Backup photos — OK" \
    "**${COUNT}** archives sur Hetzner Storage Box"$'\n'"Occupation : ${SIZE}"
