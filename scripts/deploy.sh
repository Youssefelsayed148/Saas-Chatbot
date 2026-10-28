#!/usr/bin/env bash
# Pull, build, migrate, start and verify the production stack on the VPS.
#   ./scripts/deploy.sh            deploy the current checkout (after `git pull`)
#   ./scripts/deploy.sh --pull     git pull --ff-only first
#   ./scripts/deploy.sh --rollback <git-sha>   redeploy a previous commit
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env.production"
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE (copy .env.production.example and fill it in)." >&2; exit 1; }
[ "$(stat -c %a "$ENV_FILE" 2>/dev/null || echo 600)" -le 640 ] || echo "WARNING: chmod 600 $ENV_FILE" >&2

if [ "${1:-}" = "--pull" ]; then
  git pull --ff-only
elif [ "${1:-}" = "--rollback" ]; then
  [ -n "${2:-}" ] || { echo "Usage: $0 --rollback <git-sha>" >&2; exit 1; }
  git checkout "$2"
fi

RELEASE="$(git rev-parse --short HEAD)"
export RELEASE
DC=(docker compose -f compose.prod.yaml --env-file "$ENV_FILE")
echo "Deploying release $RELEASE"

umask 077
mkdir -p backups
"${DC[@]}" config --quiet
# A failed status query must stop the script, not look like a first deploy.
database_container="$("${DC[@]}" ps --status running --quiet db)"
if [ -n "$database_container" ]; then
  # Use the database container directly; the scheduled backup service may be down.
  # A failed dump/archive check aborts before build or migration (set -e).
  backup_path="backups/pre-deploy-${RELEASE}-$(date -u +%Y%m%dT%H%M%SZ).dump"
  (
    set -o noclobber
    "${DC[@]}" exec -T db sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --no-owner' >"${backup_path}.partial"
  )
  test -s "${backup_path}.partial"
  "${DC[@]}" exec -T db pg_restore --list <"${backup_path}.partial" >/dev/null
  mv -- "${backup_path}.partial" "$backup_path"
  echo "Verified pre-deploy archive: $backup_path"
else
  echo "No running database to back up. For an existing deployment, stop and start its database before rebuilding." >&2
  # First installs require a separate explicit path; a stopped existing database
  # must never be mistaken for an empty installation and migrated without a dump.
  exit 1
fi
"${DC[@]}" build
"${DC[@]}" up -d --wait --remove-orphans

DOMAIN="$(grep -E '^DOMAIN=' "$ENV_FILE" | cut -d= -f2-)"
echo "Verifying https://$DOMAIN ..."
for i in $(seq 1 20); do
  if curl -fsS -o /dev/null "https://$DOMAIN/login"; then echo "OK: https://$DOMAIN is serving release $RELEASE"; exit 0; fi
  sleep 3
done
echo "Deploy finished but https://$DOMAIN did not respond; check: docker compose -f compose.prod.yaml logs caddy web api" >&2
exit 1
