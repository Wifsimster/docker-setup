#!/bin/bash
# =============================================================================
# disk-guard.sh — hourly guard. Runs the full cleanup ONLY when disk usage
# exceeds the threshold, so the server never drifts up to a critical level
# between the daily runs. Threshold is set above the ~90% in-use baseline so
# it only reacts to genuine spikes (not the normal steady state).
# =============================================================================
THRESHOLD=92
USED=$(df / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
if [ "${USED}" -gt "${THRESHOLD}" ]; then
    echo "[disk-guard $(date '+%Y-%m-%d %H:%M')] Usage ${USED}% > ${THRESHOLD}% -> running disk-cleanup.sh"
    /opt/docker/disk-cleanup.sh
fi
