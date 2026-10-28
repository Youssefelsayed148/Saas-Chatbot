"""Count chronological evidence without claiming it is a single green suite."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent
attempts = ["setup-failure", "attempt-1", "attempt-2", "attempt-3", "attempt-4", "attempt-5", "attempt-6", "attempt-7", "tests"]
latest = {}
summary = {}
for label in attempts:
    cases = list(ET.parse(root / f"{label}.xml").getroot().iter("testcase"))
    counts = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for case in cases:
        status = ("failed" if case.find("failure") is not None else
                  "errors" if case.find("error") is not None else
                  "skipped" if case.find("skipped") is not None else "passed")
        counts[status] += 1
        key = case.get("classname", "") + "::" + case.get("name", "")
        latest[key] = {"status": status, "evidence": label}
    summary[label] = {"tests": len(cases), **counts}
assert len(latest) == 78, len(latest)
assert all(row["status"] == "passed" for row in latest.values())
result = {"note": "Latest outcome per test across attempts; NOT a single green 78-test run.",
          "attempts": summary, "latest_unique_tests": len(latest), "latest": latest}
(root / "evidence-summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"attempts": summary, "latest_unique_tests": len(latest), "latest_all_passed": True}, indent=2))
