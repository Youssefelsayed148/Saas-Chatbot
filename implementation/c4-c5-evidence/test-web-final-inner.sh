#!/bin/bash
set -euo pipefail
ip link set lo up
scratch=/var/tmp/saas-c4-c5-e2e
repo='/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c4-c5'
runuser -u postgres -- /usr/lib/postgresql/18/bin/pg_ctl -D "$scratch/pg" -l "$scratch/pg/server.log" -o "-k $scratch/socket -p 55456 -c listen_addresses='127.0.0.1'" start
trap 'runuser -u postgres -- /usr/lib/postgresql/18/bin/pg_ctl -D "$scratch/pg" stop -m fast' EXIT
export PATH=/var/tmp/saas-closeout-tools/node-v24.22.1-linux-x64/bin:/var/tmp/saas-closeout-tools/venv/bin:$PATH
export TMPDIR="$scratch/tmp"
export APP_ENV=test ENVIRONMENT=test NEXT_TELEMETRY_DISABLED=1
export TEST_DATABASE_URL='postgresql://postgres@127.0.0.1:55456/many_test_c4_c5_e2e_test'
export DATABASE_URL="$TEST_DATABASE_URL"
export E2E_PYTHON=/var/tmp/saas-closeout-tools/venv/bin/python
export E2E_API_PORT=8115 E2E_WEB_PORT=3215
export API_PROXY_TARGET=http://127.0.0.1:8115 PLATFORM_GUARD_ORIGIN=http://127.0.0.1:8115
export PLAYWRIGHT_BROWSERS_PATH=/var/tmp/saas-closeout-tools/playwright
export CHAT_STUB_MODEL=1 EMBEDDING_TEST_STUB=1
export OPENAI_API_KEY='' CHAT_OPENAI_API_KEY='' CHAT_OPENROUTER_API_KEY=''
export NO_PROXY='*' HTTP_PROXY='' HTTPS_PROXY='' ALL_PROXY=''
cd "$repo/apps/web"
test ! -e .env && test ! -e .env.local && test ! -e "$repo/.env"
printf 'External network disabled; explicit disposable DB host=127.0.0.1:55456 db=many_test_c4_c5_e2e_test; APP_ENV=test; ENVIRONMENT=test\n'
APP_ENV=test TEST_DATABASE_URL="$TEST_DATABASE_URL" npx playwright test tests/knowledge.spec.ts:204 tests/overview.spec.ts tests/privacy-terms.spec.ts --reporter=line >"$repo/implementation/c4-c5-evidence/web-tests-final.log" 2>&1
cat "$repo/implementation/c4-c5-evidence/web-tests-final.log"
