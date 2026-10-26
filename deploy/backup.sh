#!/bin/sh
# Daily backup loop: database dump + uploaded files, pruned after BACKUP_KEEP_DAYS.
set -eu
KEEP="${BACKUP_KEEP_DAYS:-14}"
while true; do
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  if pg_dump --format=custom --no-owner -f "/backups/db-$stamp.dump.tmp"; then
    mv "/backups/db-$stamp.dump.tmp" "/backups/db-$stamp.dump"
    tar -czf "/backups/files-$stamp.tar.gz" -C /data . || echo "files backup failed"
    echo "backup $stamp ok"
  else
    rm -f "/backups/db-$stamp.dump.tmp"
    echo "backup $stamp FAILED" >&2
  fi
  find /backups -type f \( -name 'db-*.dump' -o -name 'files-*.tar.gz' \) -mtime "+$KEEP" -delete
  sleep 86400
done
