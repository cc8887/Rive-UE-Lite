#!/usr/bin/env python3
"""Check adapter provenance and source/shader closure, without claiming a build."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

MODULE = Path(__file__).resolve().parent
ROOT = MODULE.parents[1]


def main() -> None:
    include_expression = re.compile(r'^\s*#\s*include\s+["<]([^">]+)', re.M)
    forbidden = []
    for path in MODULE.rglob("*"):
        if path.suffix not in (".h", ".hpp", ".cpp"):
            continue
        for include in include_expression.findall(path.read_text(encoding="utf-8")):
            if include.startswith(("Engine/", "Ore/")) or include in ("UnrealClient.h", "TextureResource.h", "ScreenPass.h"):
                forbidden.append({"file": str(path.relative_to(ROOT)), "include": include})

    shaders = ROOT / "Shaders"
    missing_shader_includes = []
    engine_shader_includes = set()
    local_edges = 0
    registered = sorted(set(re.findall(r'"(/Plugin/Rive/[^\"]+\.usf)"', (MODULE / "Private/RiveShaderTypes.cpp").read_text())))
    pending = [shaders / path.removeprefix("/Plugin/Rive/") for path in registered]
    visited = set()
    while pending:
        path = pending.pop()
        if path in visited:
            continue
        visited.add(path)
        if not path.exists():
            missing_shader_includes.append({"file": str(path.relative_to(ROOT)), "include": "registered shader source"})
            continue
        for include in include_expression.findall(path.read_text(encoding="utf-8")):
            if include.startswith("/Engine/"):
                engine_shader_includes.add(include)
                continue
            if include.startswith("/Plugin/Rive/"):
                target = shaders / include.removeprefix("/Plugin/Rive/")
            elif include.startswith("/"):
                continue
            else:
                target = path.parent / include
            local_edges += 1
            if not target.exists():
                missing_shader_includes.append({"file": str(path.relative_to(ROOT)), "include": include})
            else:
                pending.append(target)

    manifest = json.loads((MODULE / "upstream-manifest.json").read_text())
    source_hash_failures = []
    for record in manifest["files"]:
        if hashlib.sha256((ROOT / record["output"]).read_bytes()).hexdigest() != record["output_sha256"]:
            source_hash_failures.append(record["output"])
    native_include = ROOT / "vendor/rive-unreal/Source/ThirdParty/RiveLibrary/Includes"
    export_header_present = (native_include / "rive/generated/shaders/rhi.glsl.exports.h").is_file()
    uniforms = (shaders / "Private/Rive/Generated/flush_uniforms.minified.ush").read_text()
    uniform_tokens_preserved = all(token in uniforms for token in (
        "UNIFORM_BLOCK_END(uniforms)", "DECLARE_UNIFORM_FLOAT(gradTextureYScale)",
        "DECLARE_UNIFORM_UINT(renderTargetWidth)"))
    result = {
        "passed": export_header_present and uniform_tokens_preserved and not (forbidden or missing_shader_includes or source_hash_failures),
        "scope": "static source slice only; no compile, link, pixels or Linux measurements",
        "forbidden_module_includes": forbidden,
        "local_shader_include_edges": local_edges,
        "registered_shader_entrypoints": registered,
        "reachable_local_shader_files": len(visited),
        "missing_local_shader_includes": missing_shader_includes,
        "required_engine_shader_includes": sorted(engine_shader_includes),
        "source_hash_failures": source_hash_failures,
        "generated_rhi_export_header_present": export_header_present,
        "shader_uniform_tokens_preserved": uniform_tokens_preserved,
        "original_draw_invariants": manifest["invariants"],
        "ore_enabled": False,
    }
    (MODULE / "source-validation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
