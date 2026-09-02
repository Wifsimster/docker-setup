#!/bin/bash
# =============================================================================
# gramps-backup.sh — weekly backup of Gramps Web data to the Unraid NAS (NFS).
# Creates a timestamped tar.gz of /opt/docker/gramps, copies it to the NAS,
# verifies the checksum, and keeps only the most recent N copies.
# Installed via root crontab: 0 2 * * 0 (Sundays 02:00).
# =============================================================================
set -euo pipefail

SRC_DIR="/opt/docker/gramps"
LOCAL_DIR="/home/wifsimster/backups"
NAS_DIR="/mnt/media/data/backups/gramps"
KEEP_LOCAL=4
KEEP_NAS=8

TS="$(date +%Y%m%d-%H%M)"
NAME="gramps-backup-${TS}.tar.gz"
LOCAL_FILE="${LOCAL_DIR}/${NAME}"
LOG_PREFIX="[gramps-backup $(date '+%Y-%m-%d %H:%M')]"
log() { echo "${LOG_PREFIX} $*"; }

mkdir -p "${LOCAL_DIR}"

# 1. Create the local archive
tar -czf "${LOCAL_FILE}" -C "$(dirname "${SRC_DIR}")" "$(basename "${SRC_DIR}")"
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
ls -1t "${LOCAL_DIR}"/gramps-backup-*.tar.gz 2>/dev/null | tail -n +$((KEEP_LOCAL+1)) | xargs -r rm -f
ls -1t "${NAS_DIR}"/gramps-backup-*.tar.gz 2>/dev/null | tail -n +$((KEEP_NAS+1)) | xargs -r rm -f
log "Retention applied (local keep ${KEEP_LOCAL}, NAS keep ${KEEP_NAS}). Done."
