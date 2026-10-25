#!/usr/bin/env python3
"""Audit package_linux.py inputs without staging or archiving any package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from compare_png import sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--shader-archive", type=Path)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    engine = (root / "engine/Engine").resolve()
    receipt = json.loads(args.receipt.read_text(encoding="utf-8-sig"))
    files, missing = {}, []

    def add(source: Path, destination: Path, role: str):
        if not source.is_file():
            missing.append({"source": str(source), "destination": destination.as_posix(), "role": role})
            return
        files[destination.as_posix()] = {"source": str(source.resolve()), "destination": destination.as_posix(),
                                       "role": role, "source_bytes_before_strip": source.stat().st_size}

    for entry in receipt.get("BuildProducts", []) + receipt.get("RuntimeDependencies", []):
        kind = entry.get("Type")
        if kind in ("SymbolFile", "MapFile", "DebugNonUFS"):
            continue
        value = entry["Path"].replace("$(EngineDir)", str(engine)).replace("$(ProjectDir)", str(root))
        source = Path(value)
        if "..." in value or "$(" in value:
            missing.append({"source": value, "role": kind, "reason": "unexpanded receipt pattern/token"})
            continue
        if source.suffix in (".debug", ".sym", ".map"):
            continue
        if kind == "Executable":
            destination = Path("Engine/Binaries/Linux") / source.name
        elif source.resolve().is_relative_to(engine):
            destination = Path("Engine") / source.resolve().relative_to(engine)
        elif source.resolve().is_relative_to(root):
            destination = source.resolve().relative_to(root)
        else:
            missing.append({"source": value, "role": kind, "reason": "outside prototype root"})
            continue
        add(source, destination, kind)
    for directory in (Path("Config"), Path("Config/Unix"), Path("Config/Linux")):
        for source in sorted((engine / directory).glob("*.ini")):
            add(source, Path("Engine") / directory / source.name, "engine config")
    for source in sorted((root / "Config").rglob("*.ini")):
        add(source, source.relative_to(root), "project config")
    if args.shader_archive:
        add(args.shader_archive, Path("shaders/global.bin"), "compiled shader archive")
    if args.fixture:
        add(args.fixture, Path("fixtures/input.riv"), "Rive fixture")
    add(root / "prototype/runtime/render.sh", Path("render.sh"), "server launcher")
    supplied = {"shader_archive": str(args.shader_archive) if args.shader_archive else None,
                "fixture": str(args.fixture) if args.fixture else None}
    report = {"scope": "pre-stage source/receipt audit only; no package built, no deployment or Rive rendering acceptance",
              "receipt": str(args.receipt.resolve()), "receipt_sha256": sha256(args.receipt),
              "target": receipt.get("TargetName"), "planned_files": list(files.values()),
              "planned_source_bytes_before_strip": sum(item["source_bytes_before_strip"] for item in files.values()),
              "planned_empty_directories": ["Engine/Shaders"],
              "missing": missing, "supplied_render_inputs": supplied,
              "receipt_sources_ready": not any(item["role"] not in ("compiled shader archive", "Rive fixture") for item in missing),
              "staging_inputs_ready": not missing and all(supplied.values()),
              "deployment_acceptance": "incomplete",
              "unproven_dependencies": ["ELF and dlopen shared library closure", "Vulkan loader/CPU ICD compatibility",
                                        "whether empty Shaders mapping directory suffices for cached-shader bootstrap",
                                        "fonts/images/default assets required by selected fixture/host", "startup from staged layout without source tree fallback"],
              "status": "ready_for_staging" if not missing and all(supplied.values()) else "incomplete"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "planned_files"}, indent=2))
    return 0 if report["staging_inputs_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
