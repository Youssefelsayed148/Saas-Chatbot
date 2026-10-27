"""The contract-copy guard fails on a mismatching temporary copy and passes on the real files."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from check_contract_copies import DELTA, DOC17, PACK_DELTA, PACK_V1, check

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_contract_copies.py"


def _copy_tree(target: Path) -> None:
    for name in (DOC17, PACK_V1, DELTA, PACK_DELTA):
        destination = target / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, destination)


class ContractCopiesGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        _copy_tree(self.root)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_script(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.root)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_real_files_agree(self) -> None:
        self.assertEqual(check(ROOT), [])

    def test_matching_copy_passes(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_v1_copy_mismatch_fails(self) -> None:
        path = self.root / PACK_V1
        path.write_bytes(path.read_bytes() + b"\n")
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("byte copy", result.stderr)

    def test_delta_copy_mismatch_fails(self) -> None:
        path = self.root / PACK_DELTA
        path.write_text(path.read_text("utf-8") + "A99. extra\n", encoding="utf-8")
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("differs", result.stderr)

    def test_section_11_drift_fails(self) -> None:
        for name in (DOC17, PACK_V1):
            path = self.root / name
            path.write_text(path.read_text("utf-8").replace("A15.", "A15 (edited).", 1), "utf-8")
        result = self.run_script()
        self.assertEqual(result.returncode, 1)
        self.assertIn("section 11", result.stderr)

    def test_missing_file_fails(self) -> None:
        (self.root / DELTA).unlink()
        self.assertEqual(self.run_script().returncode, 1)


if __name__ == "__main__":
    unittest.main()
