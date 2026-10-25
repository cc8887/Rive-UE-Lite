"""Stage the runtime receipt, not the SDK/build tree, into a measurable package."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]

def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--shader-archive", type=Path)
    p.add_argument("--fixture", type=Path)
    p.add_argument("--playback-manifest", type=Path,
                   help="Also stage selected playback fixtures and their deterministic scenarios")
    p.add_argument("--output", type=Path, default=ROOT / "package")
    p.add_argument("--strip", type=Path)
    a = p.parse_args()
    receipt = json.loads(a.receipt.read_text())
    engine = (ROOT / "engine/Engine").resolve()
    output = a.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError("Use a fresh package output directory; existing packages are never deleted")
    output.mkdir(parents=True, exist_ok=True)
    entries, missing = {}, []

    def expand(name):
        return Path(name.replace("$(EngineDir)", str(engine)).replace("$(ProjectDir)", str(ROOT)))

    def stage(src, dest):
        if not src.is_file():
            missing.append(str(src))
            return
        target = output / dest
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        if a.strip and target.read_bytes()[:4] == b"\x7fELF":
            subprocess.run([str(a.strip), "--strip-unneeded", str(target)], check=True)
        entries[dest.as_posix()] = {"path": dest.as_posix(), "bytes": target.stat().st_size, "sha256": sha256(target), "source": str(src)}

    for item in receipt.get("BuildProducts", []) + receipt.get("RuntimeDependencies", []):
        if item.get("Type") in ("SymbolFile", "MapFile", "DebugNonUFS"):
            continue
        src = expand(item["Path"])
        if "..." in str(src):
            missing.append(str(src))
            continue
        if src.suffix in (".debug", ".sym", ".map"):
            continue
        try:
            dest = Path("Engine") / src.resolve().relative_to(engine)
        except ValueError:
            try:
                dest = src.resolve().relative_to(ROOT)
            except ValueError:
                raise RuntimeError(f"Receipt path outside isolated prototype: {src}")
        if item.get("Type") == "Executable":
            # UE's portable default ../../../Engine resolves from this layout.
            # A project/Binaries/Linux layout bakes a development engine-relative path.
            dest = Path("Engine/Binaries/Linux") / src.name
        stage(src, dest)
    for src in sorted((engine / "Config").glob("*.ini")):
        stage(src, Path("Engine/Config") / src.name)
    # Linux DDPI explicitly inherits Unix; retain the platform's real config chain.
    for platform_config in ("Unix", "Linux"):
        for src in sorted((engine / "Config" / platform_config).glob("*.ini")):
            stage(src, Path("Engine/Config") / platform_config / src.name)
    for src in sorted((ROOT / "Config").rglob("*.ini")):
        stage(src, src.relative_to(ROOT))
    if a.shader_archive:
        stage(a.shader_archive, Path("shaders/global.bin"))
    if a.fixture:
        stage(a.fixture, Path("fixtures/input.riv"))
    if a.playback_manifest:
        playback_manifest = a.playback_manifest.resolve()
        fixture_root = (ROOT / "fixtures").resolve()
        playback_manifest.relative_to(fixture_root)
        playback = json.loads(playback_manifest.read_text())
        for case in playback["scenarios"]:
            src = (playback_manifest.parent / case["fixture"]).resolve()
            src.relative_to(fixture_root)
            if sha256(src) != case["fixture_sha256"]:
                raise RuntimeError(f"Playback fixture identity differs: {src}")
            # The manifest and per-case files keep their original relative layout.
            dest = Path("fixtures/playback") / case["fixture"]
            normalized = Path(os.path.normpath(dest))
            if normalized.parent != Path("fixtures"):
                raise RuntimeError(f"Unexpected playback fixture layout: {dest}")
            stage(src, normalized)
            scenario = playback_manifest.parent / (case["id"] + ".json")
            scenario.relative_to(fixture_root)
            if json.loads(scenario.read_text()) != case["playback"]:
                raise RuntimeError(f"Playback scenario differs from manifest: {scenario}")
            stage(scenario, Path("fixtures/playback") / scenario.name)
        stage(playback_manifest, Path("fixtures/playback/scenarios.json"))
    stage(ROOT / "prototype/runtime/render.sh", Path("render.sh"))
    for empty_directory in ("Engine/Shaders",):
        (output / empty_directory).mkdir(parents=True, exist_ok=True)
    report = {
        "status": "incomplete" if missing or not a.shader_archive or not a.fixture else "staged",
        "scope": "application payload includes the fallback Vulkan loader; selected system loader, CPU ICD and their host dependency closure are inventoried separately",
        "engine_commit": subprocess.check_output(["git", "-C", str(ROOT / "engine"), "rev-parse", "HEAD"], text=True).strip(),
        "receipt_sha256": sha256(a.receipt),
        "stripped_by_packager": bool(a.strip), "debug_symbol_products_excluded": True,
        "empty_shader_mapping_directories": ["Engine/Shaders"],
        "playback_manifest_sha256": sha256(a.playback_manifest) if a.playback_manifest else None,
        "missing": missing, "files": list(entries.values()),
        "payload_bytes_excluding_manifest": sum(e["bytes"] for e in entries.values()),
    }
    (output / "package-manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "files"}, indent=2))
    return int(report["status"] == "incomplete")

if __name__ == "__main__":
    raise SystemExit(main())
