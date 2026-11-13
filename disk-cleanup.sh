#!/bin/bash

set -euo pipefail

LOG_PREFIX="[disk-cleanup $(date '+%Y-%m-%d %H:%M')]"
RUNNER_BASE="/opt/actions-runner"
THRESHOLD_WARN=90
THRESHOLD_CRIT=94

log()  { echo "${LOG_PREFIX} $*"; }
warn() { echo "${LOG_PREFIX} [WARN] $*"; }

USED_PCT=$(df / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
AVAIL_BEFORE=$(df -h / | awk 'NR==2 {print $4}')
RECLAIMED=0

log "Disk usage: ${USED_PCT}% (${AVAIL_BEFORE} available)"

log "Docker prune..."
DOCKER_OUT=$(docker container prune --force 2>&1 | grep "Total reclaimed" || echo "0B")
log "  containers: ${DOCKER_OUT}"

DOCKER_OUT=$(docker image prune -a --force --filter "until=48h" 2>&1 | grep "Total reclaimed" || echo "0B")
log "  images: ${DOCKER_OUT}"

DOCKER_OUT=$(docker builder prune -a --force --filter "until=48h" 2>&1 | grep "Total reclaimed" || echo "0B")
log "  build cache: ${DOCKER_OUT}"

DOCKER_OUT=$(docker volume prune --force 2>&1 | grep "Total reclaimed" || echo "0B")
log "  volumes: ${DOCKER_OUT}"

docker images --filter "dangling=true" -q | xargs -r docker rmi 2>/dev/null || true

log "Truncating large container logs (>50Mo)..."
find /var/lib/docker/containers -name "*-json.log" -size +50M 2>/dev/null | while read f; do
    size=$(du -sh "$f" | cut -f1)
    truncate -s 0 "$f"
    log "  Truncated ${f} (was ${size})"
done

log "Vacuuming systemd journal..."
journalctl --vacuum-time=14d --vacuum-size=500M 2>&1 | grep -E "freed|Vacuuming" | while read l; do log "  $l"; done

log "Cleaning APT cache..."
apt-get clean -y 2>/dev/null
apt-get autoremove -y 2>/dev/null | tail -1

log "Cleaning old rotated logs..."
find /var/log -name "*.log.[5-9]" -o -name "*.log.[1-9][0-9]" 2>/dev/null | xargs -r rm -f
find /var/log -name "*.gz" -mtime +30 2>/dev/null | xargs -r rm -f

if [[ -f /var/log/apport.log ]] && [[ $(du -sm /var/log/apport.log | cut -f1) -gt 50 ]]; then
    truncate -s 0 /var/log/apport.log
    log "  apport.log truncated"
fi

log "Cleaning GitHub Actions runner artifacts..."

if [[ -d "${RUNNER_BASE}" ]]; then
    find "${RUNNER_BASE}" -path "*/_diag/*" -type f -mtime +3 -delete 2>/dev/null || true

    find "${RUNNER_BASE}" -path "*/_work/*/*/node_modules" -type d -prune -exec rm -rf {} \; 2>/dev/null || true
    find "${RUNNER_BASE}" -path "*/_work/*/*/.next" -type d -prune -exec rm -rf {} \; 2>/dev/null || true
    find "${RUNNER_BASE}" -path "*/_work/*/*/dist" -type d -prune -exec rm -rf {} \; 2>/dev/null || true

    for d in personal-blog toko resume wawptn x-ai-weekly-bot; do
        update_dir="${RUNNER_BASE}/${d}/_work/_update"
        if [[ -d "${update_dir}" ]] && [[ $(du -sm "${update_dir}" 2>/dev/null | cut -f1) -gt 10 ]]; then
            rm -rf "${update_dir}"
            mkdir -p "${update_dir}"
            log "  ${d}/_work/_update cleared"
        fi
    done

    for rdir in "${RUNNER_BASE}"/*/; do
        [[ -d "${rdir}" ]] || continue
        LATEST=$(ls -d "${rdir}bin."* 2>/dev/null | sort -V | tail -1 | xargs -r basename)
        [[ -n "${LATEST}" ]] || continue
        VER="${LATEST#bin.}"
        for old in "${rdir}bin."* "${rdir}externals."*; do
            [[ -d "${old}" ]] || continue
            base=$(basename "${old}")
            [[ "${base#*.}" == "${VER}" ]] && continue
            rm -rf "${old}"
            log "  Removed stale runner version $(basename "${rdir%/}")/${base}"
        done
    done
fi

USED_PCT_NOW=$(df / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')

if [[ ${USED_PCT_NOW} -ge ${THRESHOLD_CRIT} ]]; then
    warn "CRITICAL threshold (${USED_PCT_NOW}% >= ${THRESHOLD_CRIT}%). Aggressive cleanup..."

    DOCKER_OUT=$(docker image prune -a --force 2>&1 | grep "Total reclaimed" || echo "0B")
    log "  [aggressive] images: ${DOCKER_OUT}"

    find /var/lib/docker/containers -name "*-json.log" -size +10M 2>/dev/null | while read f; do
        truncate -s 0 "$f"
        log "  [aggressive] Truncated ${f}"
    done

    journalctl --vacuum-time=3d 2>&1 | grep freed | while read l; do log "  $l"; done

    for d in personal-blog toko resume wawptn x-ai-weekly-bot; do
        find "${RUNNER_BASE}/${d}/_work" -mindepth 1 -maxdepth 1 \
            -not -name "_update" -not -name "_PipelineMapping" -not -name "_temp" -not -name "_tool" \
            -type d -exec rm -rf {} \; 2>/dev/null || true
    done
    log "  [aggressive] Runner _work repos cleared"
fi

AVAIL_AFTER=$(df -h / | awk 'NR==2 {print $4}')
USED_PCT_FINAL=$(df / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')

log "Done. Disk usage: ${USED_PCT_FINAL}% (${AVAIL_AFTER} available, was ${AVAIL_BEFORE})"

if [[ ${USED_PCT_FINAL} -ge ${THRESHOLD_WARN} ]]; then
    warn "Disk still above ${THRESHOLD_WARN}% threshold. Manual review recommended."
fi
