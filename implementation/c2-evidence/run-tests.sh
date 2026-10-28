#!/bin/bash
set -euo pipefail
evidence='/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat/.closeout-worktrees/c2/implementation/c2-evidence'
scratch=/var/tmp/saas-c2-20261028
mkdir -p "$scratch/source" "$scratch/socket"
python3 - "$evidence/snapshot.zip" "$scratch/source" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    assert not any('/.env' in name for name in archive.namelist())
    archive.extractall(sys.argv[2])
PY
if [ ! -d "$scratch/pg" ]; then
    install -d -o postgres -g postgres "$scratch/pg" "$scratch/socket"
    runuser -u postgres -- /usr/lib/postgresql/18/bin/initdb -D "$scratch/pg" -A trust >"$scratch/initdb.log"
fi
runuser -u postgres -- /usr/lib/postgresql/18/bin/pg_ctl -D "$scratch/pg" -l "$scratch/pg/server.log" -o "-k $scratch/socket -p 55443 -c listen_addresses=''" start
trap 'runuser -u postgres -- /usr/lib/postgresql/18/bin/pg_ctl -D "$scratch/pg" stop -m fast' EXIT
# This private worker database contains synthetic fixtures only. Recreate it
# when testing an expanded, still-unshipped migration instead of stamping it.
runuser -u postgres -- dropdb -h "$scratch/socket" -p 55443 --if-exists many_test_c2_test
unshare --net bash "$evidence/test-inner.sh" "$@"
