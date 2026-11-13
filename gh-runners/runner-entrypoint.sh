#!/usr/bin/env bash
# Enveloppe du point d'entrée myoung34 : un runner = un job (EPHEMERAL), puis le
# conteneur sort et `restart: unless-stopped` le relance. Comme le conteneur est
# relancé et non recréé, on repart ici d'un état propre avant chaque job.
set -euo pipefail

TOKEN_FILE=/run/gh-runner-token/token

# 1. Démon DinD prêt.
for _ in $(seq 1 60); do docker info >/dev/null 2>&1 && break; sleep 2; done
docker info >/dev/null 2>&1 || { echo "runner: DinD injoignable sur $DOCKER_HOST" >&2; exit 1; }

# 2. Restes du job précédent : workspace, identifiants registre, conteneurs,
#    volumes et réseaux du démon isolé. Les images de moins de 72 h et le cache
#    BuildKit récent sont gardés pour accélérer les builds.
rm -rf /_work/* /_work/.[!.]* /root/.docker /tmp/* 2>/dev/null || true
docker ps -aq | xargs -r docker rm -f >/dev/null
docker volume prune -af >/dev/null
docker network prune -f >/dev/null
docker image prune -af --filter "until=72h" >/dev/null
docker builder prune -af --filter "until=72h" >/dev/null 2>&1 || true

# 3. Token d'enregistrement fourni par le broker (jamais le PAT).
for _ in $(seq 1 60); do [[ -s "$TOKEN_FILE" ]] && break; sleep 5; done
[[ -s "$TOKEN_FILE" ]] || { echo "runner: pas de token d'enregistrement (broker ?)" >&2; exit 1; }

RUNNER_TOKEN=$(<"$TOKEN_FILE") exec /entrypoint.sh "$@"
