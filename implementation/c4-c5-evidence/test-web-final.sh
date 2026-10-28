#!/bin/bash
set -euo pipefail
scratch=/var/tmp/saas-c4-c5-e2e
repo='/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c4-c5'
mkdir -p "$scratch/pg" "$scratch/socket" "$scratch/tmp"
chmod 755 "$scratch" "$scratch/tmp"
chown postgres:postgres "$scratch/pg" "$scratch/socket"
if [ ! -f "$scratch/pg/PG_VERSION" ]; then
  runuser -u postgres -- /usr/lib/postgresql/18/bin/initdb -D "$scratch/pg" -A trust >/dev/null
fi
unshare --net bash "$repo/implementation/c4-c5-evidence/test-web-final-inner.sh" "$@"
