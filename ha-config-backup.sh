#!/bin/bash
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

SNAPSHOT="${SRC_DIR}/zigbee.db.snapshot"
rm -f "${SNAPSHOT}"
if [ -f "${SRC_DIR}/zigbee.db" ]; then
    if sqlite3 "${SRC_DIR}/zigbee.db" ".backup '${SNAPSHOT}'" 2>/dev/null \
       && sqlite3 "${SNAPSHOT}" 'PRAGMA quick_check;' 2>/dev/null | head -1 | grep -q '^ok$'; then
        log "zigbee.db snapshot OK ($(du -h "${SNAPSHOT}" | cut -f1))"
    else
        log "[ERROR] zigbee.db snapshot failed or corrupt - aborting."
        rm -f "${SNAPSHOT}"
        exit 1
    fi
fi
trap 'rm -f "${SNAPSHOT}"' EXIT

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

if ! mountpoint -q /mnt/media; then
    log "[ERROR] /mnt/media not mounted - NAS copy skipped, local backup kept."
    exit 1
fi

mkdir -p "${NAS_DIR}"
cp "${LOCAL_FILE}" "${NAS_DIR}/"

SUM_LOCAL="$(sha256sum "${LOCAL_FILE}" | awk '{print $1}')"
SUM_NAS="$(sha256sum "${NAS_DIR}/${NAME}" | awk '{print $1}')"
if [ "${SUM_LOCAL}" = "${SUM_NAS}" ]; then
    log "Verified OK on NAS (sha256 ${SUM_LOCAL})"
else
    log "[ERROR] Checksum mismatch! local=${SUM_LOCAL} nas=${SUM_NAS}"
    exit 1
fi

ls -1t "${LOCAL_DIR}"/ha-config-backup-*.tar.gz 2>/dev/null | tail -n +$((KEEP_LOCAL+1)) | xargs -r rm -f
ls -1t "${NAS_DIR}"/ha-config-backup-*.tar.gz 2>/dev/null | tail -n +$((KEEP_NAS+1)) | xargs -r rm -f
log "Retention applied (local keep ${KEEP_LOCAL}, NAS keep ${KEEP_NAS}). Done."
