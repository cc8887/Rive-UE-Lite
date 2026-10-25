"""Extract build-tool configurations from the exact isolated Git commit."""
from pathlib import Path
import subprocess
import hashlib
import json
root = Path(__file__).resolve().parents[1]
engine = root / "engine"
paths = subprocess.check_output(["git", "-C", str(engine), "ls-tree", "-r", "--name-only", "HEAD", "Engine/Programs"], text=True).splitlines()
entries = []
for name in paths:
    if not name.endswith(".ini"):
        continue
    data = subprocess.check_output(["git", "-C", str(engine), "show", f"HEAD:{name}"])
    target = engine / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    entries.append({"path": name, "sha256": hashlib.sha256(data).hexdigest()})
out = root / "artifacts/setup/program-configs.json"
out.write_text(json.dumps({"commit": subprocess.check_output(["git", "-C", str(engine), "rev-parse", "HEAD"], text=True).strip(), "files": entries}, indent=2) + "\n")
print(json.dumps({"configs": len(entries), "report": str(out)}))
