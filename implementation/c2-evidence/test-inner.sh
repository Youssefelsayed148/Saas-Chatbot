#!/bin/bash
set -euo pipefail
ip link set lo up
export PATH=/var/tmp/saas-closeout-tools/venv/bin:$PATH
export APP_ENV=test ENVIRONMENT=test CHAT_STUB_MODEL=1 EMBEDDING_TEST_STUB=1
export OPENAI_API_KEY='' CHAT_OPENAI_API_KEY='' CHAT_OPENROUTER_API_KEY=''
export PGHOST=/var/tmp/saas-c2-20261028/socket PGPORT=55443
export TEST_DATABASE_URL='postgresql://postgres@/many_test_c2'
export DATABASE_URL="$TEST_DATABASE_URL"
export HTTP_PROXY='' HTTPS_PROXY='' ALL_PROXY='' NO_PROXY='*'
scratch=/var/tmp/saas-c2-20261028
evidence='/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c2/implementation/c2-evidence'
cd "$scratch/source/apps/api"
printf 'APP_ENV=test; TEST_DATABASE_URL explicit; DB host=%s db=many_test_c2 (fixture derives many_test_c2_test); network loopback only\n' "$scratch/socket"
test ! -e .env && test ! -e ../../.env
python - <<'PY'
import os, psycopg
from sqlalchemy import make_url
url=make_url(os.environ['TEST_DATABASE_URL'])
assert url.host is None and url.database == 'many_test_c2'
assert os.environ['PGHOST'] == '/var/tmp/saas-c2-20261028/socket'
with psycopg.connect(url.set(database='postgres').render_as_string(hide_password=False)) as db:
    assert db.execute("SHOW listen_addresses").fetchone()[0] == ''
print('Disposable private cluster and explicit URL verified; no external network interface.')
PY
tests=(tests/test_channel_erasure.py tests/test_channel_events.py tests/test_channel_outbound.py tests/test_channel_redrive.py tests/test_channel_migrations.py)
if [ "$#" -gt 0 ]; then tests=("$@"); fi
set +e
APP_ENV=test TEST_DATABASE_URL="$TEST_DATABASE_URL" pytest "${tests[@]}" -q --junitxml="$evidence/tests.xml" >"$evidence/tests.log" 2>&1
status=$?
set -e
tail -n 70 "$evidence/tests.log"
printf 'PYTEST_EXIT=%s\n' "$status"
exit "$status"
