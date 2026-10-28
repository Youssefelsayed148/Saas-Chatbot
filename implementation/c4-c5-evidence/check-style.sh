#!/bin/bash
set -euo pipefail
ip link set lo up
export PATH=/var/tmp/saas-closeout-tools/node-v24.22.1-linux-x64/bin:/var/tmp/saas-closeout-tools/venv/bin:$PATH
repo='/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c4-c5'
cd "$repo"
npx prettier --write .github/workflows/ci.yml apps/web/app/privacy/page.tsx apps/web/app/terms/page.tsx apps/web/app/login/page.tsx apps/web/lib/page-title.tsx apps/web/tests/group-c-polish.spec.ts apps/web/tests/widget-streaming.spec.ts apps/web/tests/privacy-terms.spec.ts apps/web/tests/knowledge.spec.ts apps/web/tests/overview.spec.ts 'apps/web/app/app/[tenant]/bots/[botId]/knowledge/page.tsx'
python scripts/check_contract_copies.py
cd apps/web
npx eslint app/privacy/page.tsx app/terms/page.tsx app/login/page.tsx lib/page-title.tsx tests/group-c-polish.spec.ts tests/widget-streaming.spec.ts tests/privacy-terms.spec.ts tests/knowledge.spec.ts tests/overview.spec.ts 'app/app/[tenant]/bots/[botId]/knowledge/page.tsx'
cd ../api
ruff check app/db/models/core.py tests/test_tone_prompt.py tests/test_trace_context.py tests/test_closeout_schema_drift.py
ruff format --check app/db/models/core.py tests/test_tone_prompt.py tests/test_trace_context.py tests/test_closeout_schema_drift.py
