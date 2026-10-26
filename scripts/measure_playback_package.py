#!/usr/bin/env python3
"""Inventory/compress the updated playback package, without reusing old timings."""
import argparse
import json
from pathlib import Path

from compare_png import sha256
from measure_ue_lite import inspect_package


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--with-umg", action="store_true")
    args = parser.parse_args()
    package, output = args.package.resolve(), args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("use a fresh evidence directory")
    output.mkdir(parents=True, exist_ok=True)
    manifest = package / "package-manifest.json"
    declared = json.loads(manifest.read_text())
    target = "RiveUmgHost" if args.with_umg else "RiveRhiLite"
    if declared.get("target", "RiveRhiLite") != target:
        parser.error("Package flavor differs from the selected measurement flavor")
    errors = []
    for entry in declared["files"]:
        path = package / entry["path"]
        if not path.is_file() or path.stat().st_size != entry["bytes"] or sha256(path) != entry["sha256"]:
            errors.append(entry["path"])
    declared_names = {entry["path"] for entry in declared["files"]} | {manifest.name}
    actual_names = {path.relative_to(package).as_posix() for path in package.rglob("*") if path.is_file()}
    errors.extend(sorted(actual_names ^ declared_names))
    executable = package / "Engine/Binaries/Linux" / target
    report = inspect_package(package, executable, output / "deploy-package.tar.gz")
    report.update(scope="updated playback application package and ELF DT_NEEDED only; no new performance timings or independent-cooker pixel acceptance",
                  target=target,
                  package_manifest_sha256=sha256(manifest), manifest_errors=errors,
                  playback_scenario_manifest_sha256=sha256(package / "fixtures/playback/scenarios.json"))
    if errors:
        report["status"] = "failed"
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "logical_file_bytes", "executable_bytes", "archive", "manifest_errors")}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
