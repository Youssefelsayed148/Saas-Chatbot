import os, pathlib, shutil, hashlib, json
e=pathlib.Path(__file__).resolve().parent
repo=e.parent
scratch=pathlib.Path(os.environ["SCRATCH"])
source=scratch/"source"
source.mkdir()
records=[]
for rel in (e/"source-files.txt").read_text(encoding="utf-8-sig").splitlines():
    p=repo/rel
    if p.suffix.lower() not in {".py",".ts",".tsx",".js",".mjs",".cjs",".json",".md",".yaml",".yml",".toml",".ini",".txt",".lock",".css",".svg",".csv",".html",".sh",".sha256",".pdf",".docx",".jsonl",".mako",".ico",".woff2",".gitkeep"} and not p.name.startswith((".env","Dockerfile")):
        continue
    dest=source/rel
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(p,dest)
    records.append({"file":rel,"sha256":hashlib.sha256(dest.read_bytes()).hexdigest()})
(e/"snapshot-manifest.json").write_text(json.dumps(records,indent=2)+"\n")
(e/"scratch-path.txt").write_text(str(scratch)+"\n")
print(f"Fresh snapshot: {len(records)} allowlisted source files")
