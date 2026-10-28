#!/bin/bash
set -euo pipefail
scratch=/var/tmp/saas-c4-c5
repo='/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c4-c5'
mkdir -p "$scratch/pg" "$scratch/socket" "$scratch/tmp"
chmod 755 "$scratch" "$scratch/tmp"
chown postgres:postgres "$scratch/pg" "$scratch/socket"
if [ ! -f "$scratch/pg/PG_VERSION" ]; then
  runuser -u postgres -- /usr/lib/postgresql/18/bin/initdb -D "$scratch/pg" -A trust >/dev/null
fi
runuser -u postgres -- /usr/lib/postgresql/18/bin/pg_ctl -D "$scratch/pg" -l "$scratch/pg/server.log" -o "-k $scratch/socket -p 55455 -c listen_addresses=''" start
trap 'runuser -u postgres -- /usr/lib/postgresql/18/bin/pg_ctl -D "$scratch/pg" stop -m fast' EXIT
if ! runuser -u postgres -- psql -h "$scratch/socket" -p 55455 -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='many_test_c4_c5'" | /usr/bin/grep -qx 1; then
  runuser -u postgres -- createdb -h "$scratch/socket" -p 55455 many_test_c4_c5
fi
unshare --net bash "$repo/implementation/c4-c5-evidence/test-api-inner.sh"
