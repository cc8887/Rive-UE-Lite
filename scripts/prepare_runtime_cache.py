from pathlib import Path
import subprocess
root = Path(__file__).resolve().parents[1]
changed = subprocess.check_output(["git", "-C", str(root / "engine"), "diff", "--name-only", "HEAD", "--", "Engine/Source/Runtime"], text=True)
target = root / "artifacts/setup/runtime-cache-updates.txt"
target.write_text(changed, encoding="utf-8", newline="\n")
print(f"Runtime cache updates: {len(changed.splitlines())} files")
