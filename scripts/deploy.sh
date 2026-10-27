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

mkdir -p backups
"${DC[@]}" config --quiet
"${DC[@]}" build
# Back up before migrating an existing database.
if "${DC[@]}" ps --status running db 2>/dev/null | grep -q db; then
  "${DC[@]}" exec -T backup sh -c 'pg_dump --format=custom --no-owner -f /backups/pre-deploy-'"$RELEASE"'.dump' \
    || echo "WARNING: pre-deploy backup failed" >&2
fi
"${DC[@]}" up -d --wait --remove-orphans

DOMAIN="$(grep -E '^DOMAIN=' "$ENV_FILE" | cut -d= -f2-)"
echo "Verifying https://$DOMAIN ..."
for i in $(seq 1 20); do
  if curl -fsS -o /dev/null "https://$DOMAIN/login"; then echo "OK: https://$DOMAIN is serving release $RELEASE"; exit 0; fi
  sleep 3
done
echo "Deploy finished but https://$DOMAIN did not respond; check: docker compose -f compose.prod.yaml logs caddy web api" >&2
exit 1
