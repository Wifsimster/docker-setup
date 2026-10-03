#!/bin/bash
# Résumé de la maison du dimanche : collecte (lecture seule) puis publication
# des pages /s/<jeton>/ et envoi des courriels. Options passées à publish.py
# (--no-mail, --only damien|christelle). Cron root : 0 8 * * 0 (VM en UTC).
set -euo pipefail
cd /opt/docker/digest
DATA="$(./collect.py)"
printf '%s' "${DATA}" | ./publish.py "$@"
