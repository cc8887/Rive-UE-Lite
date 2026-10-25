"""Read the user's NuGet cache and copy nupkg files to an isolated local feed."""
from pathlib import Path
import shutil
import json
root = Path(__file__).resolve().parents[1]
feed = root / "dependencies/nuget-feed"
feed.mkdir(parents=True, exist_ok=True)
files = list((Path.home() / ".nuget/packages").glob("*/*/*.nupkg"))
size = 0
for src in files:
    dst = feed / src.name
    if not dst.exists():
        shutil.copy2(src, dst)
    size += dst.stat().st_size
print(json.dumps({"packages": len(files), "bytes": size, "feed": str(feed)}))
