from pathlib import Path
import xml.etree.ElementTree as ET
import json
e=Path(__file__).resolve().parent
summaries={}
for p in sorted(e.rglob("*.xml")):
 root=ET.parse(p).getroot()
 cases=list(root.iter("testcase"))
 failures=[c for c in cases if c.find("failure") is not None]
 errors=[c for c in cases if c.find("error") is not None]
 skipped=[c for c in cases if c.find("skipped") is not None]
 summaries[str(p.relative_to(e))]={
 "tests":len(cases),"passed":len(cases)-len(failures)-len(errors)-len(skipped),
 "failures":len(failures),"errors":len(errors),"skipped":len(skipped),
 "suite_time_seconds":root.attrib.get("time"),
 "reported_suite_times":[s.attrib.get("time") for s in root.iter("testsuite")],
 "failed_cases":[c.attrib for c in failures+errors],
 }
(e/"counts.json").write_text(json.dumps(summaries,indent=2)+"\n")
for name,v in summaries.items():
 print(name, {k:v[k] for k in ("tests","passed","failures","errors","skipped")})
