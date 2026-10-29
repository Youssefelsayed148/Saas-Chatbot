from pathlib import Path
import hashlib
root=Path.cwd()
many=Path("/mnt/d/Projects/Work Projects/The Osiris Labs/ManyOsirisChat")
for repository, manifest in (
 (root,"implementation/PHASE-06-V2/CONTRACT.sha256"),
 (many,"docs/saas-delegation/CONTRACT.sha256"),
):
 for line in (repository/manifest).read_text().splitlines():
  if not line or line.startswith(("#","source:")): continue
  expected,rel=line.split(None,1)
  actual=hashlib.sha256((repository/rel.strip()).read_bytes().replace(b"\r\n",b"\n")).hexdigest()
  assert actual==expected,rel
  print("hash OK:",rel)
for saas, other in (
 ("implementation/PHASE-06-V2/many-pack/CONTRACT-V1.md","docs/saas-delegation/CONTRACT-V1.md"),
 ("implementation/PHASE-06-V2/CONTRACT-V1.1-DELTA.md","docs/saas-delegation/CONTRACT-V1.1-DELTA.md"),
 ("apps/api/tests/fixtures/contract/signing_vectors.json","backend/tests/fixtures/contract/signing_vectors.json"),
):
 assert (root/saas).read_bytes().replace(b"\r\n",b"\n") == (many/other).read_bytes().replace(b"\r\n",b"\n")
 print("cross-repository copy OK:",saas)
