from pathlib import Path
import os
scratch=Path(__file__).resolve().parent.joinpath("scratch-path.txt").read_text().strip()
root=Path(scratch).resolve()
assert root.parent==Path("/var/tmp") and root.name.startswith("saas-full-")
old=root/"source"/("node_modules"+chr(13))
new=root/"source"/"node_modules"
assert old.is_dir() and not new.exists()
old.rename(new)
print("Corrected dependency destination line ending; application source unchanged.")
