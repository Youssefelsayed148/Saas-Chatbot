#!/bin/bash
set -euo pipefail
ip link set lo up
e="$(cd "$(dirname "$0")" && pwd)"
export SCRATCH="$(mktemp -d /var/tmp/saas-full-XXXXXXXX)"
chmod 755 "$SCRATCH"
export PATH=/var/tmp/saas-closeout-tools/venv/bin:/var/tmp/saas-closeout-tools/node-v24.22.1-linux-x64/bin:/usr/sbin:/usr/bin:/sbin:/bin
python "$e/snapshot.py"
mkdir "$SCRATCH/pg" "$SCRATCH/socket" "$SCRATCH/tmp"
chown postgres:postgres "$SCRATCH/pg" "$SCRATCH/socket"
pg=/usr/lib/postgresql/18/bin
trap 'runuser -u postgres -- "$pg/pg_ctl" -D "$SCRATCH/pg" -m fast stop >"$e/cluster-stop.log" 2>&1 || true' EXIT
runuser -u postgres -- "$pg/initdb" -D "$SCRATCH/pg" -A trust --encoding=UTF8 --locale=C.UTF-8 >"$e/cluster-init.log"
runuser -u postgres -- "$pg/pg_ctl" -D "$SCRATCH/pg" -l "$SCRATCH/pg/server.log" -o "-k $SCRATCH/socket -p 55587 -c listen_addresses='127.0.0.1'" start >"$e/cluster-start.log"
runuser -u postgres -- "$pg/createdb" -h "$SCRATCH/socket" -p 55587 saas_full_test
export APP_ENV=test ENVIRONMENT=test PGHOST="$SCRATCH/socket" PGPORT=55587 PGUSER=postgres
export TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55587/saas_full_test DATABASE_URL=postgresql://postgres@127.0.0.1:55587/saas_full_test
export CHAT_STUB_MODEL=1 EMBEDDING_TEST_STUB=1 WORKER_ALLOW_ONLY_TEST_DB=1
export OPENAI_API_KEY='' CHAT_OPENAI_API_KEY='' CHAT_OPENROUTER_API_KEY=''
export TMPDIR="$SCRATCH/tmp" NEXT_TELEMETRY_DISABLED=1 NO_PROXY='*'
export PLAYWRIGHT_BROWSERS_PATH=/var/tmp/saas-closeout-tools/playwright
export E2E_PYTHON=/var/tmp/saas-closeout-tools/venv/bin/python E2E_API_PORT=8187 E2E_WEB_PORT=3287
export API_PROXY_TARGET=http://127.0.0.1:8187 PLATFORM_GUARD_ORIGIN=http://127.0.0.1:8187
printf 'DB host=127.0.0.1:55587 database=saas_full_test; loopback-only namespace\n'
cd "$SCRATCH/source/apps/api"
python - <<'PY'
import os, pathlib, psycopg, app
from tests.conftest import _base_database_url,disposable_url
assert pathlib.Path(app.__file__).resolve().is_relative_to(pathlib.Path.cwd())
assert _base_database_url()==os.environ["TEST_DATABASE_URL"]
assert disposable_url(_base_database_url(),"saas_full_test_test").endswith("/saas_full_test_test")
with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c:
 assert c.execute("select current_database()").fetchone()[0]=="saas_full_test"
PY
run() {
 name="$1"; shift
 printf '%s START %s\n' "$(date -u +%FT%TZ)" "$name"
 printf 'cwd=%q APP_ENV=test ENVIRONMENT=test TEST_DATABASE_URL=%q ' "$PWD" "$TEST_DATABASE_URL" >>"$e/commands.log"
 printf '%q ' "$@" >>"$e/commands.log"; printf '\n' >>"$e/commands.log"
 start=$(date +%s)
 set +e
 APP_ENV=test ENVIRONMENT=test TEST_DATABASE_URL="$TEST_DATABASE_URL" "$@" >"$e/$name.log" 2>&1
 rc=$?
 set -e
 printf '%s\t%s\t%s\n' "$name" "$rc" "$(( $(date +%s)-start ))" >>"$e/results.tsv"
 tail -8 "$e/$name.log"
 printf '%s END %s exit=%s duration=%ss\n' "$(date -u +%FT%TZ)" "$name" "$rc" "$(( $(date +%s)-start ))"
}
run api python -m pytest tests -q --junitxml="$e/saas-api.xml"
run ruff python -m ruff check .
run format python -m ruff format --check .
run mypy-app python -m mypy app
run mypy-full python -m mypy
cd "$SCRATCH/source"
run scripts python -m unittest discover -s scripts -p 'test_*.py' -v
run contracts python scripts/check_contract_copies.py
run hashes python "$e/hash-check.py"
cd "$SCRATCH/source/apps/api"
run migrations env PYTHONPATH=. python "$e/migrations.py"
cd "$SCRATCH/source/apps/web"
cp -a "$e/../../c4-c5/node_modules" "$SCRATCH/source/node_modules"
cp -a "$e/../../c4-c5/apps/web/node_modules" ./node_modules
run typecheck npm run typecheck
run lint npm run lint
run node-unit node --test tests/channel-delivery.unit.mjs tests/insights.unit.mjs
run build npm run build
export PLAYWRIGHT_JUNIT_OUTPUT_FILE="$e/playwright.xml" PLAYWRIGHT_HTML_OPEN=never
run playwright npm test -- --reporter=line,junit
printf 'Completed. Runtime/source remain private at %s\n' "$SCRATCH"
