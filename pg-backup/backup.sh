#!/bin/sh
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
infisical-db|infisical|infisical|INFISICAL_DB_PASSWORD
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
