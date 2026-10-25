#!/usr/bin/env python3
"""Record the single-define correction and verify the native cook is unchanged."""
import difflib
import hashlib
import json
import os
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def local(path):
    if os.name == "nt" and path.startswith("/mnt/"):
        return Path(path[5].upper() + ":/" + path[7:])
    return Path(path)


root = Path(__file__).resolve().parents[2]
before = root / "artifacts/playback/diagnostics/lite-compiler-before-dxc-02"
current_cpp = root / "Source/RiveLiteShaderCompiler/Private/RiveLiteShaderCompiler.cpp"
native_provenance = root / "artifacts/shaders-canonical/full-01/provenance/provenance.json"
native = json.loads(native_provenance.read_text(encoding="utf-8"))
records = [native["compiler"], *native["source_inputs"], *native["build_logs"],
           native["cook_execution"]["output"], native["cook_execution"]["log"],
           native["archive_manifest"]]
checks = []
for item in records:
    path = local(item["path"])
    actual = digest(path) if path.is_file() else None
    checks.append({"path": str(path), "expected_sha256": item["sha256"],
                   "actual_sha256": actual, "passed": actual == item["sha256"]})
old_cpp = before / "RiveLiteShaderCompiler.cpp"
delta = list(difflib.unified_diff(old_cpp.read_text().splitlines(),
    current_cpp.read_text().splitlines(), fromfile="before", tofile="after", lineterm=""))
report = {
    "scope": "Compiler identity correction only; original Rive shaders and native environment unchanged",
    "before": {"source_sha256": digest(old_cpp), "compiler_sha256": digest(before / "RiveLiteShaderCompiler")},
    "after_source_sha256": digest(current_cpp), "source_delta": delta,
    "native_cook_preserved": all(item["passed"] for item in checks),
    "native_identity_checks": checks,
    "source_chain": [
        "Engine ShaderCompiler.cpp sets COMPILER_DXC=1 for the native Vulkan DXC backend",
        "Lite SetupInput previously omitted COMPILER_DXC; Platform.ush defaults it to 0",
        "Rive rhi.minified.ush selects opposite CLOCKWISE_FROM_FRONT_FACE expansions",
        "render_atlas signed_fill_coverage negates coverage for the opposite face",
        "Atlas fill blends signed coverage additively; feather atlas sampling clamps to [0,1], without abs",
        "Atlas stroke does not depend on CLOCKWISE_FROM_FRONT_FACE",
    ],
    "causality_status": "Source-backed hypothesis; the independent paired render must establish the visible result",
}
output = root / "artifacts/playback/diagnostics/lite-dxc-identity-02.json"
output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"native_cook_preserved": report["native_cook_preserved"],
                  "checked_files": len(checks), "report": str(output)}))
raise SystemExit(0 if report["native_cook_preserved"] else 1)
