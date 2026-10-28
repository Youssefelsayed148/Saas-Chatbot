#!/bin/bash
set -euo pipefail
ip link set lo up
export PATH=/var/tmp/saas-closeout-tools/venv/bin:$PATH
export TMPDIR=/var/tmp/saas-c4-c5/tmp
export APP_ENV=test ENVIRONMENT=test
export PGHOST=/var/tmp/saas-c4-c5/socket
export TEST_DATABASE_URL='postgresql://postgres@/many_test_c4_c5?port=55455'
export DATABASE_URL="$TEST_DATABASE_URL"
export CHAT_STUB_MODEL=1 EMBEDDING_TEST_STUB=1
export OPENAI_API_KEY='' CHAT_OPENAI_API_KEY='' CHAT_OPENROUTER_API_KEY=''
export NO_PROXY='*' HTTP_PROXY='' HTTPS_PROXY='' ALL_PROXY=''
repo='/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c4-c5'
cd "$repo/apps/api"
test ! -e .env && test ! -e "$repo/.env"
printf 'APP_ENV=test ENVIRONMENT=test TEST_DATABASE_URL explicit host=/var/tmp/saas-c4-c5/socket db=many_test_c4_c5 (pytest creates many_test_c4_c5_test)\n'
APP_ENV=test TEST_DATABASE_URL="$TEST_DATABASE_URL" pytest tests/test_tone_prompt.py tests/test_trace_context.py tests/test_contacts_export_safety.py tests/test_closeout_schema_drift.py -q --junitxml="$repo/implementation/c4-c5-evidence/api-tests.xml" >"$repo/implementation/c4-c5-evidence/api-tests.log" 2>&1
cat "$repo/implementation/c4-c5-evidence/api-tests.log"
DATABASE_URL='postgresql://postgres@/many_test_c4_c5_test?port=55455' alembic check >"$repo/implementation/c4-c5-evidence/alembic-check.log" 2>&1
cat "$repo/implementation/c4-c5-evidence/alembic-check.log"
ruff check app/db/models/core.py tests/test_tone_prompt.py tests/test_trace_context.py tests/test_closeout_schema_drift.py
ruff format --check app/db/models/core.py tests/test_tone_prompt.py tests/test_trace_context.py tests/test_closeout_schema_drift.py
