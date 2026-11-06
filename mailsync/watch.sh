#!/usr/bin/env bash
# watch.sh — alerte Discord #infra si la collecte du mail pro s'arrête.
# Lancé par cron en semaine à 18:30 (Paris). Silencieux quand tout va bien.
# Vérifie : conteneur mailsync sain, au moins un mail reçu aujourd'hui,
# et (si codedev a déjà fait une reprise) une reprise de moins de 3 h.
set -uo pipefail

MAILDIR=/srv/mailsync/Maildir
PICKUP_STAMP=/srv/mailsync-state/last-pickup
ENV_FILE=/opt/docker/discord-bridge/.env
TODAY=$(TZ=Europe/Paris date +%F)
problems=()

state=$(docker inspect -f '{{.State.Health.Status}}' mailsync 2>/dev/null || echo absent)
case "$state" in healthy|starting) ;; *) problems+=("conteneur mailsync : ${state}") ;; esac

received_today=$(find "$MAILDIR/cur" -maxdepth 1 -type f -newermt "$TODAY 00:00" 2>/dev/null | wc -l)
sent_today=$(find "$MAILDIR/.Sent/cur" -maxdepth 1 -type f -newermt "$TODAY 00:00" 2>/dev/null | wc -l)
[ "$received_today" -gt 0 ] || problems+=("aucun mail reçu collecté aujourd'hui (flux Power Automate « Outlook reçus -> mailsync » arrêté ?)")

if [ -e "$PICKUP_STAMP" ]; then
    age_h=$(( ( $(date +%s) - $(stat -c %Y "$PICKUP_STAMP") ) / 3600 ))
    [ "$age_h" -lt 3 ] || problems+=("pas de reprise par codedev depuis ${age_h} h (attendue toutes les heures)")
fi

echo "$(date -Is) reçus=${received_today} envoyés=${sent_today} état=${state} problèmes=${#problems[@]}"
[ "${#problems[@]}" -eq 0 ] && exit 0

token=$(grep -E '^DISCORD_BOT_TOKEN=' "$ENV_FILE" | cut -d= -f2-)
channel=$(grep -E '^CHANNEL_INFRA=' "$ENV_FILE" | cut -d= -f2-)
text="⚠️ **mailsync** (mail pro Dedalus)"
for p in "${problems[@]}"; do text+=$'\n'"• ${p}"; done
payload=$(python3 -c 'import json,sys; print(json.dumps({"content": sys.argv[1]}))' "$text")
curl -fsS -o /dev/null -X POST "https://discord.com/api/v10/channels/${channel}/messages" \
    -H "Authorization: Bot ${token}" -H 'Content-Type: application/json' \
    -d "$payload" || echo "$(date -Is) échec de l'envoi Discord"
