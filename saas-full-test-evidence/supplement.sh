#!/bin/bash
set -euo pipefail
e="$(cd "$(dirname "$0")" && pwd)"
export PATH=/var/tmp/saas-closeout-tools/venv/bin:/var/tmp/saas-closeout-tools/node-v24.22.1-linux-x64/bin:/usr/sbin:/usr/bin:/sbin:/bin
export APP_ENV=test ENVIRONMENT=test TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55587/saas_full_test DATABASE_URL=postgresql://postgres@127.0.0.1:55587/saas_full_test
export PGHOST=/var/tmp/saas-full-FdwKr60F/socket PGPORT=55587 PGUSER=postgres
export CHAT_STUB_MODEL=1 EMBEDDING_TEST_STUB=1 WORKER_ALLOW_ONLY_TEST_DB=1
printf 'DB host=127.0.0.1:55587 database=saas_full_test\n'
python - <<'PY'
import psycopg,os,json,subprocess
with psycopg.connect(os.environ["TEST_DATABASE_URL"]) as c:
 assert c.execute("select current_database()").fetchone()[0]=="saas_full_test"
assert {link["ifname"] for link in json.loads(subprocess.check_output(["ip","-j","link","show"]))}=={"lo"}
PY
run() {
 name="$1"; shift
 printf 'cwd=%q APP_ENV=test ENVIRONMENT=test TEST_DATABASE_URL=%q ' "$PWD" "$TEST_DATABASE_URL" >>"$e/commands.log"
 printf '%q ' "$@" >>"$e/commands.log"; printf '\n' >>"$e/commands.log"
 start=$(date +%s)
 set +e
 APP_ENV=test ENVIRONMENT=test TEST_DATABASE_URL="$TEST_DATABASE_URL" "$@" >"$e/$name.log" 2>&1
 rc=$?
 set -e
 printf '%s\t%s\t%s\n' "$name" "$rc" "$(( $(date +%s)-start ))" >>"$e/results.tsv"
 cat "$e/$name.log"
}
cd /var/tmp/saas-full-FdwKr60F/source/apps/web
run public-asset npm run check:public-asset
run provenance python "$e/verify-provenance.py"
run s10 python -c 'from pathlib import Path; import re; p=Path("../../implementation/PHASE-06-V2/SAAS-REBUILD-PROMPT.md"); assert not re.search(r"\bS10\b",p.read_text()); print("Current rebuild prompt has no S10 reference")'
run versions bash -c 'python --version; node --version; npm --version; /usr/lib/postgresql/18/bin/postgres --version'
cd ../api
run heads python -m alembic heads
