#!/bin/sh
# =============================================================================
# pg-backup — nightly pg_dump of every Postgres database on the host (03:00).
#
# Dumps land in /backups (-> /opt/docker/pg-backup/backups on the host). That
# directory sits on the SAME disk as the databases it protects, so it is only
# half a backup: /opt/docker/state-backup.sh runs at 04:45 and pushes the
# dumps to the NAS and to the Hetzner borg repo. If you add a database here,
# you get the offsite copy for free.
#
# NOT covered here (SQLite, handled by state-backup.sh): vaultwarden,
# solopilot, birthday-invitation, home-assistant zigbee.db.
# =============================================================================
set -e

DATE=$(date +%Y-%m-%d_%H%M%S)
BACKUP_DIR="/backups"
RETENTION_DAYS=7
ERRORS=""

# Database definitions: host|user|dbname|password_env_var
DATABASES="
paperless-db|paperless|paperless|PAPERLESS_DB_PASSWORD
immich_postgres|postgres|immich|IMMICH_DB_PASSWORD
the-box-postgres|thebox|thebox|THEBOX_DB_PASSWORD
copro-pilot-postgres|copro_pilot|copro_pilot|COPROPILOT_DB_PASSWORD
n8n-db|n8n|n8n|N8N_DB_PASSWORD
toko-postgres|toko|toko|TOKO_DB_PASSWORD
wawptn-postgres|wawptn|wawptn|WAWPTN_DB_PASSWORD
koe-db|koe|koe|KOE_DB_PASSWORD
yamtrack-postgres|yamtrack|yamtrack|YAMTRACK_DB_PASSWORD
racontine-db|racontine|racontine|RACONTINE_DB_PASSWORD
umami-db|umami|umami|UMAMI_DB_PASSWORD
ghostfolio-postgres|ghostfolio|ghostfolio-db|GHOSTFOLIO_DB_PASSWORD
infisical-db|infisical|infisical|INFISICAL_DB_PASSWORD
litellm-db|litellm|litellm|LITELLM_DB_PASSWORD
"

echo "=== PostgreSQL backup started at $(date) ==="

for entry in $DATABASES; do
  HOST=$(echo "$entry" | cut -d'|' -f1)
  USER=$(echo "$entry" | cut -d'|' -f2)
  DB=$(echo "$entry" | cut -d'|' -f3)
  PASS_VAR=$(echo "$entry" | cut -d'|' -f4)

  PASS=$(eval echo "\$$PASS_VAR")
  DUMP_FILE="${BACKUP_DIR}/${DB}_${DATE}.dump"

  echo "--- Backing up ${DB} from ${HOST}..."

  if PGPASSWORD="$PASS" pg_dump -h "$HOST" -U "$USER" -Fc "$DB" > "$DUMP_FILE" 2>&1; then
    SIZE=$(du -h "$DUMP_FILE" | cut -f1)
    echo "    OK: ${DUMP_FILE} (${SIZE})"
  else
    echo "    FAILED: ${DB} from ${HOST}"
    ERRORS="${ERRORS}${DB} (${HOST})\n"
    rm -f "$DUMP_FILE"
  fi
done

# Cleanup old backups
echo "--- Removing backups older than ${RETENTION_DAYS} days..."
find "$BACKUP_DIR" -name "*.dump" -mtime +${RETENTION_DAYS} -delete

echo "=== PostgreSQL backup finished at $(date) ==="

# Send Discord alert on failure
if [ -n "$ERRORS" ] && [ -n "$DISCORD_WEBHOOK_URL" ]; then
  PAYLOAD=$(printf '{"content":"⚠️ **pg-backup failure** — %s\\nFailed databases:\\n%s"}' "$(date +%Y-%m-%d)" "$ERRORS")
  wget -q --header="Content-Type: application/json" --post-data="$PAYLOAD" "$DISCORD_WEBHOOK_URL" -O /dev/null 2>&1 || echo "    WARNING: Failed to send Discord alert"
fi
