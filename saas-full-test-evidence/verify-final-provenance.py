from pathlib import Path
import json, hashlib
e=Path(__file__).resolve().parent
repo=e.parent
allowed={
"apps/api/tests/eval/offline/test_gate_trace.py",
"apps/api/tests/eval/offline/test_h4_terms_and_diagnosis.py",
"apps/api/tests/test_channel_erasure.py",
"apps/api/tests/test_channel_health.py",
"apps/api/tests/test_channels.py",
"apps/api/tests/test_closeout_schema_drift.py",
"apps/api/tests/test_r19_index_migration.py",
"apps/api/tests/test_tenant_route_matrix.py",
"apps/api/tests/test_channel_ingest_hardening.py",
"apps/api/tests/test_startup_guard.py",
"apps/api/tests/test_tenant_data.py",
"scripts/test_dev_compose.py",
"apps/web/tests/widget-domain.spec.ts",
}
changed=[]
for item in json.loads((e/"snapshot-manifest.json").read_text()):
 rel=item["file"]
 actual=hashlib.sha256((repo/rel).read_bytes()).hexdigest()
 if actual!=item["sha256"]:
  assert rel in allowed, rel
  changed.append(rel)
print("Production source unchanged from full-suite snapshot; reviewed test-only differences:")
print("\n".join(changed))
assert set(changed)==allowed
