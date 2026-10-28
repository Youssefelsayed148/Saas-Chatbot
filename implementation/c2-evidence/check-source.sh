#!/bin/bash
set -euo pipefail
cd '/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c2/apps/api'
tool=/var/tmp/saas-closeout-tools/venv/bin
files=(app/channels/erasure.py app/channels/inbound.py app/channels/outbound.py app/channels/events.py app/db/models/channels.py app/db/models/chat.py alembic/versions/0031_contact_erasure.py tests/test_channel_erasure.py tests/test_channel_migrations.py tests/test_channel_outbound.py tests/test_channel_health.py)
"$tool/ruff" format --no-cache "${files[@]}"
"$tool/ruff" check --no-cache "${files[@]}" --fix
"$tool/mypy" app/channels/erasure.py app/channels/inbound.py app/channels/outbound.py
