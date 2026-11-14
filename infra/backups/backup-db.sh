#!/usr/bin/env bash
# Daily database backup for the ETIKE server.
#
# Saves a compressed pg_dump named etike-YYYY-MM-DD.sql.gz and keeps the
# newest 7. Run it from cron on the server, e.g. every night at 02:30:
#
#   30 2 * * * /home/DEPLOY_USER/etike/infra/backups/backup-db.sh >> /home/DEPLOY_USER/backups/backup.log 2>&1
#
# Restore steps are in docs/deployment.md.

set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/etike}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups}"
KEEP="${KEEP:-7}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"

cd "$APP_DIR"
# Read POSTGRES_USER and POSTGRES_DB from the server's .env.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi
: "${POSTGRES_USER:?POSTGRES_USER is not set}"
: "${POSTGRES_DB:?POSTGRES_DB is not set}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"  # backups contain personal data: owner only
file="$BACKUP_DIR/etike-$(date +%F).sql.gz"
tmp="$file.part"

# Write to a temporary file first, so a failed dump never replaces a good one.
docker compose -f "$COMPOSE_FILE" exec -T db \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists \
  | gzip > "$tmp"
mv "$tmp" "$file"
chmod 600 "$file"
echo "$(date '+%F %T') saved $file ($(du -h "$file" | cut -f1))"

# Keep only the newest $KEEP backups.
ls -1t "$BACKUP_DIR"/etike-*.sql.gz | tail -n +"$((KEEP + 1))" | while read -r old; do
  rm -f -- "$old"
  echo "$(date '+%F %T') removed $old"
done
