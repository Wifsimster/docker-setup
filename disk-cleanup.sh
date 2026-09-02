#!/bin/bash
# =============================================================================
# disk-cleanup.sh — Periodic disk space optimizer for docker-server
# =============================================================================
# Cron (daily at 03:00) + hourly guard via disk-guard.sh:
#   0 3 * * *   /opt/docker/disk-cleanup.sh >> /var/log/disk-cleanup.log 2>&1
#   30 * * * *  /opt/docker/disk-guard.sh   >> /var/log/disk-cleanup.log 2>&1
# =============================================================================

set -euo pipefail

LOG_PREFIX="[disk-cleanup $(date '+%Y-%m-%d %H:%M')]"
RUNNER_BASE="/opt/actions-runner"
# Baseline in-use data keeps this server near ~90%, so thresholds sit ABOVE that
# floor: the safe daily prune always runs; the aggressive branch (which wipes
# runner _work) only fires on a genuine spike, never at the normal baseline.
THRESHOLD_WARN=90   # % used: log a warning
THRESHOLD_CRIT=94   # % used: aggressive cleanup (last resort)

log()  { echo "${LOG_PREFIX} $*"; }
warn() { echo "${LOG_PREFIX} [WARN] $*"; }

# --- Espace initial ---
USED_PCT=$(df / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
AVAIL_BEFORE=$(df -h / | awk 'NR==2 {print $4}')
RECLAIMED=0

log "Disk usage: ${USED_PCT}% (${AVAIL_BEFORE} available)"

# =============================================================================
# 1. Docker: images et containers inutilises
# =============================================================================
log "Docker prune..."
DOCKER_OUT=$(docker container prune --force 2>&1 | grep "Total reclaimed" || echo "0B")
log "  containers: ${DOCKER_OUT}"

# Remove ALL images not used by a running container and older than 48h.
# (-a catches old tagged deployment/watchtower images; until=48h keeps recent for rollback)
DOCKER_OUT=$(docker image prune -a --force --filter "until=48h" 2>&1 | grep "Total reclaimed" || echo "0B")
log "  images: ${DOCKER_OUT}"

# Build cache from CI image builds (older than 48h)
DOCKER_OUT=$(docker builder prune -a --force --filter "until=48h" 2>&1 | grep "Total reclaimed" || echo "0B")
log "  build cache: ${DOCKER_OUT}"

DOCKER_OUT=$(docker volume prune --force 2>&1 | grep "Total reclaimed" || echo "0B")
log "  volumes: ${DOCKER_OUT}"

# Images Docker sans tag (dangling) restantes
docker images --filter "dangling=true" -q | xargs -r docker rmi 2>/dev/null || true

# =============================================================================
# 2. Logs Docker containers (max 50Mo par container)
# =============================================================================
log "Truncating large container logs (>50Mo)..."
find /var/lib/docker/containers -name "*-json.log" -size +50M 2>/dev/null | while read f; do
    size=$(du -sh "$f" | cut -f1)
    truncate -s 0 "$f"
    log "  Truncated ${f} (was ${size})"
done

# =============================================================================
# 3. Journal systemd (garder 14 jours / 500Mo max)
# =============================================================================
log "Vacuuming systemd journal..."
journalctl --vacuum-time=14d --vacuum-size=500M 2>&1 | grep -E "freed|Vacuuming" | while read l; do log "  $l"; done

# =============================================================================
# 4. APT cache
# =============================================================================
log "Cleaning APT cache..."
apt-get clean -y 2>/dev/null
apt-get autoremove -y 2>/dev/null | tail -1

# =============================================================================
# 5. Logs systeme rotatifs (garder max 4 versions)
# =============================================================================
log "Cleaning old rotated logs..."
find /var/log -name "*.log.[5-9]" -o -name "*.log.[1-9][0-9]" 2>/dev/null | xargs -r rm -f
find /var/log -name "*.gz" -mtime +30 2>/dev/null | xargs -r rm -f

# apport.log peut grossir enormement
if [[ -f /var/log/apport.log ]] && [[ $(du -sm /var/log/apport.log | cut -f1) -gt 50 ]]; then
    truncate -s 0 /var/log/apport.log
    log "  apport.log truncated"
fi

# =============================================================================
# 6. Runners GitHub Actions: artefacts de build et doublons _update
# =============================================================================
log "Cleaning GitHub Actions runner artifacts..."

if [[ -d "${RUNNER_BASE}" ]]; then
    # Trim old runner diagnostic logs (keep last 3 days) — these grow every CI run
    find "${RUNNER_BASE}" -path "*/_diag/*" -type f -mtime +3 -delete 2>/dev/null || true

    # Supprimer node_modules, .next, dist dans les _work (regenérés au prochain build)
    find "${RUNNER_BASE}" -path "*/_work/*/*/node_modules" -type d -prune -exec rm -rf {} \; 2>/dev/null || true
    find "${RUNNER_BASE}" -path "*/_work/*/*/.next" -type d -prune -exec rm -rf {} \; 2>/dev/null || true
    find "${RUNNER_BASE}" -path "*/_work/*/*/dist" -type d -prune -exec rm -rf {} \; 2>/dev/null || true

    # _work/_update: garder uniquement dans le runner source (copro-pilot)
    for d in personal-blog toko resume wawptn x-ai-weekly-bot; do
        update_dir="${RUNNER_BASE}/${d}/_work/_update"
        if [[ -d "${update_dir}" ]] && [[ $(du -sm "${update_dir}" 2>/dev/null | cut -f1) -gt 10 ]]; then
            rm -rf "${update_dir}"
            mkdir -p "${update_dir}"
            log "  ${d}/_work/_update cleared"
        fi
    done

    # Anciennes versions de binaires runner (garder seulement la plus recente).
    # Enumere les runners presents au lieu d'une liste en dur : une liste figee
    # ratait les runners ajoutes depuis (the-box, racontine, printcast,
    # birthday-invitation, battistella-pro), qui avaient accumule 3,3 Go de
    # bin.*/externals.* obsoletes. La version gardee est calculee PAR runner,
    # chacun pouvant s'auto-mettre a jour a son rythme.
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

# =============================================================================
# 7. Cleanup agressif si seuil critique depasse
# =============================================================================
USED_PCT_NOW=$(df / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')

if [[ ${USED_PCT_NOW} -ge ${THRESHOLD_CRIT} ]]; then
    warn "CRITICAL threshold (${USED_PCT_NOW}% >= ${THRESHOLD_CRIT}%). Aggressive cleanup..."

    # Images: remove all unused now (no age filter)
    DOCKER_OUT=$(docker image prune -a --force 2>&1 | grep "Total reclaimed" || echo "0B")
    log "  [aggressive] images: ${DOCKER_OUT}"

    # Logs Docker containers: truncate tout > 10Mo
    find /var/lib/docker/containers -name "*-json.log" -size +10M 2>/dev/null | while read f; do
        truncate -s 0 "$f"
        log "  [aggressive] Truncated ${f}"
    done

    # Journal: garder seulement 3 jours
    journalctl --vacuum-time=3d 2>&1 | grep freed | while read l; do log "  $l"; done

    # Vider les _work completement (sauf _update du runner source)
    for d in personal-blog toko resume wawptn x-ai-weekly-bot; do
        find "${RUNNER_BASE}/${d}/_work" -mindepth 1 -maxdepth 1 \
            -not -name "_update" -not -name "_PipelineMapping" -not -name "_temp" -not -name "_tool" \
            -type d -exec rm -rf {} \; 2>/dev/null || true
    done
    log "  [aggressive] Runner _work repos cleared"
fi

# =============================================================================
# Rapport final
# =============================================================================
AVAIL_AFTER=$(df -h / | awk 'NR==2 {print $4}')
USED_PCT_FINAL=$(df / | awk 'NR==2 {gsub(/%/,"",$5); print $5}')

log "Done. Disk usage: ${USED_PCT_FINAL}% (${AVAIL_AFTER} available, was ${AVAIL_BEFORE})"

if [[ ${USED_PCT_FINAL} -ge ${THRESHOLD_WARN} ]]; then
    warn "Disk still above ${THRESHOLD_WARN}% threshold. Manual review recommended."
fi
