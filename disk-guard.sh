#!/bin/bash
THRESHOLD=92
USED=$(df / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
if [ "${USED}" -gt "${THRESHOLD}" ]; then
    echo "[disk-guard $(date '+%Y-%m-%d %H:%M')] Usage ${USED}% > ${THRESHOLD}% -> running disk-cleanup.sh"
    /opt/docker/disk-cleanup.sh
fi
