#!/bin/bash
# =============================================================================
# ha-config-backup.sh — weekly backup of Home Assistant CONFIG to the Unraid NAS.
# Creates a timestamped tar.gz of /opt/docker/home-assistant/config, copies it
# to the NAS, verifies the checksum, and keeps only the most recent N copies.
#
# Deliberately EXCLUDES transient/regenerable data to keep the archive small
# and focused on what is painful to recreate:
#   - backups/                 HA's own internal snapshots (~840 MB)
#   - home-assistant_v2.db*     recorder history DB + WAL/SHM (~760 MB)
#   - home-assistant.log*       logs
#   - tts/ deps/ __pycache__    caches / regenerable
# KEEPS the important state: .storage (registries, auth, integrations),
# all *.yaml, packages/, custom_components/, blueprints/, zigbee.db (ZHA
# network — very painful to lose), www/, esphome/, image/, secrets.yaml.
#
# ZIGBEE.DB IS SNAPSHOTTED, NOT COPIED LIVE. HA holds it open in WAL mode, so
# tar used to read it mid-write and log "file changed as we read it" — which
# means the archived copy could be torn exactly where it matters. `sqlite3
# .backup` takes a read lock and writes a standalone, checkpointed file. The
# archive therefore contains `zigbee.db.snapshot` instead of zigbee.db/-wal/-shm.
# TO RESTORE: rename zigbee.db.snapshot -> zigbee.db with HA stopped.
#
# Installed via root crontab: 0 2 * * 0 (Sundays 02:00), after gramps-backup.
# =============================================================================
set -euo pipefail

SRC_DIR="/opt/docker/home-assistant/config"
LOCAL_DIR="/home/wifsimster/backups"
NAS_DIR="/mnt/media/data/backups/home-assistant"
KEEP_LOCAL=4
KEEP_NAS=8

TS="$(date +%Y%m%d-%H%M)"
NAME="ha-config-backup-${TS}.tar.gz"
LOCAL_FILE="${LOCAL_DIR}/${NAME}"
LOG_PREFIX="[ha-config-backup $(date '+%Y-%m-%d %H:%M')]"
log() { echo "${LOG_PREFIX} $*"; }

mkdir -p "${LOCAL_DIR}"

# 1a. Consistent snapshot of the ZHA network database (see header).
SNAPSHOT="${SRC_DIR}/zigbee.db.snapshot"
rm -f "${SNAPSHOT}"
if [ -f "${SRC_DIR}/zigbee.db" ]; then
    if sqlite3 "${SRC_DIR}/zigbee.db" ".backup '${SNAPSHOT}'" 2>/dev/null \
       && sqlite3 "${SNAPSHOT}" 'PRAGMA quick_check;' 2>/dev/null | head -1 | grep -q '^ok$'; then
        log "zigbee.db snapshot OK ($(du -h "${SNAPSHOT}" | cut -f1))"
    else
        # Better to fail loudly than to ship an archive whose ZHA network is
        # silently unusable — that only surfaces on the day you need it.
        log "[ERROR] zigbee.db snapshot failed or corrupt - aborting."
        rm -f "${SNAPSHOT}"
        exit 1
    fi
fi
# The snapshot lives inside config/ only for the duration of the tar; drop it
# again however the script exits so HA never sees a stray file.
trap 'rm -f "${SNAPSHOT}"' EXIT

# 1b. Create the local archive (exclude transient/regenerable data)
tar -czf "${LOCAL_FILE}" \
    --exclude='config/backups' \
    --exclude='config/zigbee.db' \
    --exclude='config/zigbee.db-wal' \
    --exclude='config/zigbee.db-shm' \
    --exclude='config/home-assistant_v2.db' \
    --exclude='config/home-assistant_v2.db-wal' \
    --exclude='config/home-assistant_v2.db-shm' \
    --exclude='config/home-assistant.log' \
    --exclude='config/home-assistant.log.*' \
    --exclude='config/tts' \
    --exclude='config/deps' \
    --exclude='config/__pycache__' \
    --exclude='*/__pycache__' \
    -C "$(dirname "${SRC_DIR}")" "$(basename "${SRC_DIR}")"
chown wifsimster:wifsimster "${LOCAL_FILE}" 2>/dev/null || true
log "Created ${LOCAL_FILE} ($(du -h "${LOCAL_FILE}" | cut -f1))"

# 2. Ensure the NAS is mounted before copying
if ! mountpoint -q /mnt/media; then
    log "[ERROR] /mnt/media not mounted - NAS copy skipped, local backup kept."
    exit 1
fi

mkdir -p "${NAS_DIR}"
cp "${LOCAL_FILE}" "${NAS_DIR}/"

# 3. Verify integrity (checksum match)
SUM_LOCAL="$(sha256sum "${LOCAL_FILE}" | awk '{print $1}')"
SUM_NAS="$(sha256sum "${NAS_DIR}/${NAME}" | awk '{print $1}')"
if [ "${SUM_LOCAL}" = "${SUM_NAS}" ]; then
    log "Verified OK on NAS (sha256 ${SUM_LOCAL})"
else
    log "[ERROR] Checksum mismatch! local=${SUM_LOCAL} nas=${SUM_NAS}"
    exit 1
fi

# 4. Retention: keep only the most recent N in each location
ls -1t "${LOCAL_DIR}"/ha-config-backup-*.tar.gz 2>/dev/null | tail -n +$((KEEP_LOCAL+1)) | xargs -r rm -f
ls -1t "${NAS_DIR}"/ha-config-backup-*.tar.gz 2>/dev/null | tail -n +$((KEEP_NAS+1)) | xargs -r rm -f
log "Retention applied (local keep ${KEEP_LOCAL}, NAS keep ${KEEP_NAS}). Done."
