"""Snapshot only tracked API source plus assigned C2 additions; never dotenv."""
from pathlib import Path
import subprocess
import zipfile

root = Path(__file__).resolve().parents[2]
names = subprocess.check_output(["git", "ls-files", "-z", "apps/api"], cwd=root).decode().split("\0")
names += ["apps/api/app/channels/erasure.py", "apps/api/alembic/versions/0031_contact_erasure.py",
          "apps/api/tests/test_channel_erasure.py"]
with zipfile.ZipFile(Path(__file__).with_name("snapshot.zip"), "w", zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(set(names)):
        path = root / name
        if name and path.is_file() and not path.name.startswith(".env"):
            archive.write(path, name)
print("C2 API snapshot prepared; no env files.")
