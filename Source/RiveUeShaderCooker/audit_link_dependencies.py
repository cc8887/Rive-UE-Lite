#!/usr/bin/env python3
"""Read existing UBT linker inputs; never build or download dependencies."""
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]
rsp = root / "Intermediate/Build/Linux/x64/RiveUeShaderCooker/Development/RiveUeShaderCooker.rsp"
text = rsp.read_text()
libraries = sorted(set(re.findall(r'"([^"\n]+\.(?:a|so(?:\.[0-9.]+)?))"', text)))
source_root = root / "engine/Engine/Source"
def resolve(path):
    value = Path(path)
    return value if value.is_absolute() else source_root / value
missing = [str(resolve(path)) for path in libraries if not resolve(path).is_file()]
modules = sorted(set(re.findall(r'/Development/([^/]+)/[^/]+\.o', text)))
report = {"rsp": str(rsp), "library_count": len(libraries), "missing": missing,
          "libraries": libraries, "modules": modules, "unreal_ed_linked": "UnrealEd" in modules}
destination = root / "artifacts/setup/canonical-link-inputs-audit.json"
destination.write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps({"libraries": len(libraries), "modules": len(modules), "missing": missing,
                  "unreal_ed_linked": report["unreal_ed_linked"]}))
