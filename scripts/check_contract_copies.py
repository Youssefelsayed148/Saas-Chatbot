"""Fail when the channel-contract copies drift apart.

Checks (stdlib only; never touches the network or the app):
- ``many-pack/CONTRACT-V1.md`` equals docs/17.
- The two ``CONTRACT-V1.1-DELTA.md`` copies are equal.
- "Equal" ignores line endings: a CRLF checkout (Windows ``core.autocrlf``) matches its LF original.
- The A-clauses of the delta (from ``A1.`` to the end) equal docs/17 section 11
  (from ``A1.`` to the next ``## `` heading or the end).

Usage: ``python scripts/check_contract_copies.py [--root DIR]``
"""

import argparse
import sys
from pathlib import Path

DOC17 = "docs/17-MANYOSIRISCHAT-CHANNEL-INTEGRATION.md"
PACK_V1 = "implementation/PHASE-06-V2/many-pack/CONTRACT-V1.md"
DELTA = "implementation/PHASE-06-V2/CONTRACT-V1.1-DELTA.md"
PACK_DELTA = "implementation/PHASE-06-V2/many-pack/CONTRACT-V1.1-DELTA.md"


def _normalised(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def _clauses_from_delta(text: str) -> str:
    start = text.find("\nA1.")
    return text[start:].strip() if start >= 0 else ""


def _clauses_from_section_11(text: str) -> str:
    heading = text.find("\n## 11.")
    if heading < 0:
        return ""
    section = text[heading + 1 :]
    start = section.find("\nA1.")
    if start < 0:
        return ""
    section = section[start:]
    end = section.find("\n## ")
    return (section if end < 0 else section[:end]).strip()


def check(root: Path) -> list[str]:
    problems: list[str] = []
    files: dict[str, bytes] = {}
    for name in (DOC17, PACK_V1, DELTA, PACK_DELTA):
        path = root / name
        if not path.is_file():
            problems.append(f"missing: {name}")
        else:
            files[name] = _normalised(path.read_bytes())
    if problems:
        return problems
    if files[PACK_V1] != files[DOC17]:
        problems.append(f"{PACK_V1} is not a copy of {DOC17}")
    if files[PACK_DELTA] != files[DELTA]:
        problems.append(f"{PACK_DELTA} differs from {DELTA}")
    section = _clauses_from_section_11(files[DOC17].decode("utf-8"))
    delta = _clauses_from_delta(files[DELTA].decode("utf-8"))
    if not section or not delta:
        problems.append("could not find the A1... clauses in docs/17 section 11 or the delta")
    elif section != delta:
        problems.append(f"{DOC17} section 11 clauses differ from {DELTA}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    problems = check(args.root)
    for problem in problems:
        print(f"contract copies: {problem}", file=sys.stderr)
    if not problems:
        print("contract copies OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
