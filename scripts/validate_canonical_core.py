#!/usr/bin/env python3
"""Verify native shader environment/serialization code against the pinned UE commit."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "engine"
FILES = (
    "Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderCompiler.cpp",
    "Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderCompilerEditor.cpp",
    "Engine/Source/Runtime/Engine/Public/ShaderCompiler.h",
    "Engine/Source/Runtime/Engine/Private/SceneView.cpp",
    "Engine/Source/Runtime/RenderCore/Private/GlobalShader.cpp",
    "Engine/Source/Runtime/RenderCore/Private/Shader.cpp",
    "Engine/Source/Runtime/RenderCore/Private/ShaderCore.cpp",
    "Engine/Source/Runtime/RenderCore/Public/GlobalShader.h",
)


def git(*args):
    return subprocess.check_output(["git", "-C", str(ENGINE), *args], text=True).strip()


def main():
    entries = []
    for name in FILES:
        expected = git("rev-parse", "HEAD:" + name)
        actual = git("hash-object", "--path=" + name, name)
        entries.append({"path": name, "pinned_git_blob": expected, "actual_git_blob": actual,
                        "actual_file_sha256": hashlib.sha256((ENGINE / name).read_bytes()).hexdigest(),
                        "status": "passed" if expected == actual else "failed"})
    report = {"status": "passed" if all(entry["status"] == "passed" for entry in entries) else "failed",
              "engine_commit": git("rev-parse", "HEAD"), "files": entries,
              "scope": "native Engine compile entry/environment, View metadata and global map serialization remain the pinned source; not a claim that every compiler dependency is unmodified",
              "shared_preprocessor_change": "0006 fixes the pinned stb multiline token-paste regression for both independently executed cookers"}
    output = ROOT / "artifacts/playback/canonical-core-source-audit-01.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "files": len(entries), "output": str(output)}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
