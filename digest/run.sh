#!/bin/bash
# Résumé de la maison du dimanche : collecte (lecture seule) puis publication
# des pages /s/<jeton>/ et envoi des courriels. Options passées à publish.py
# (--no-mail, --only damien|christelle). Envoi le dimanche à 20:00 (Paris).
# La VM est en UTC, d'où le double créneau et le contrôle de l'heure de Paris :
# 0 18,19 * * 0 [ "$(TZ=Europe/Paris date +\%H)" = 20 ] && /opt/docker/digest/run.sh >> /var/log/digest.log 2>&1
set -euo pipefail
cd /opt/docker/digest
DATA="$(./collect.py)"
printf '%s' "${DATA}" | ./publish.py "$@"
