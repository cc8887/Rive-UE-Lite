#!/usr/bin/env python3
"""Validate two staged captures after a completed independent 60-capture gate."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from compare_png import compare_images, sha256


def inventory(directory):
    return {path.relative_to(directory).as_posix(): sha256(path)
            for path in sorted(directory.rglob("*")) if path.is_file()}


def evidence(path):
    return {"path": str(path.resolve()), "bytes": path.stat().st_size,
            "sha256": sha256(path)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--package", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--acceptance-report", type=Path, required=True)
    p.add_argument("--native-bankcard-reference", type=Path, required=True)
    p.add_argument("--previous-bounce-reference", type=Path, required=True)
    a = p.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0:
        p.error("run in Linux as root; existing namespace wrappers drop the renderer to uid 1000")
    root = Path(__file__).resolve().parents[1]
    package, output = a.package.resolve(), a.output_dir.resolve()
    acceptance = json.loads(a.acceptance_report.read_text())
    coverage = acceptance.get("gates", {}).get("requested_coverage", {})
    if not (acceptance.get("executed") and acceptance.get("status") == "passed"
            and coverage.get("profile") == "independent-60-v1"
            and coverage.get("planned", {}).get("planned_capture_count") == 60):
        p.error("the actual independent full 60-capture report must already have passed")
    if output.is_relative_to(package) or (output.exists() and any(output.iterdir())):
        p.error("use a fresh evidence directory outside the staged package")
    for reference in (a.native_bankcard_reference, a.previous_bounce_reference):
        if not reference.is_file():
            p.error(f"reference PNG is missing: {reference}")
    manifest = json.loads((package / "package-manifest.json").read_text())
    before = inventory(package)
    declared = {item["path"]: item["sha256"] for item in manifest["files"]}
    if any(before.get(path) != value for path, value in declared.items()):
        p.error("the package differs from its declared manifest")
    if set(before) != set(declared) | {"package-manifest.json"}:
        p.error("undeclared or missing files in the package")
    previous_package = root / "package/playback-01"
    previous_before = inventory(previous_package)
    output.mkdir(parents=True, exist_ok=True)
    cases = [
        ("bankcard", ["bash", str(root / "scripts/check_portable_linux.sh"),
                       str(package), str(output / "bankcard/output.png"),
                       "-PlaybackMetadata=" + str(output / "bankcard/playback.json")],
         output / "bankcard/output.png", a.native_bankcard_reference),
        ("bounce", ["bash", str(root / "scripts/check_portable_playback.sh"),
                     str(package), str(output / "bounce")],
         output / "bounce/bounce.png", a.previous_bounce_reference),
    ]
    report = {"schema_version": 1, "status": "incomplete",
              "scope": "Portable staged application captures and exact PNG comparison; no new RSS or startup-performance benchmark",
              "acceptance_report": evidence(a.acceptance_report),
              "package_manifest": evidence(package / "package-manifest.json"),
              "runtime_launcher": evidence(package / "render.sh"),
              "shader_archive": evidence(package / "shaders/global.bin"),
              "executable": evidence(package / "Engine/Binaries/Linux/RiveRhiLite"),
              "cases": []}
    for name, command, png, reference in cases:
        directory = output / name
        directory.mkdir(parents=True, exist_ok=True)
        log = directory / "capture.log"
        with log.open("wb") as stream:
            try:
                code = subprocess.run(command, cwd="/tmp", stdout=stream,
                    stderr=subprocess.STDOUT, timeout=180, check=False).returncode
            except subprocess.TimeoutExpired:
                code = None
        text = log.read_text(errors="replace")
        comparison = compare_images(reference.resolve(), png)
        (directory / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
        gates = {
            "normal_exit": code == 0,
            "development_trees_hidden": "development_engine=hidden development_vendor=hidden cwd=/tmp" in text,
            "gpu_device_nodes_hidden": "dxg=absent dri=absent uid=1000 gid=1000" in text,
            "actual_cpu_vulkan_device": "Type=VK_PHYSICAL_DEVICE_TYPE_CPU" in text and "DeviceName: llvmpipe" in text,
            "actual_rive_rhi_rdg_draw": "render_path=UE_RHI_RDG RiveDrawCompleted=1" in text,
            "exact_rgba_and_alpha": comparison.get("status") == "passed"
                and comparison.get("different_pixels") == 0
                and comparison.get("alpha_different_pixels") == 0,
        }
        metadata = directory / "playback.json"
        if name == "bounce":
            data = json.loads(metadata.read_text()) if metadata.is_file() else {}
            gates["actual_bounce_at_point75"] = (data.get("status") == "completed"
                and data.get("animation") == "Bounce" and data.get("target_time") == 0.75
                and data.get("advance_count") == 45)
        report["cases"].append({"name": name, "command": command,
            "shell_command": shlex.join(command), "exit_code": code,
            "log": evidence(log), "png": evidence(png) if png.is_file() else None,
            "playback_metadata": evidence(metadata) if metadata.is_file() else None,
            "comparison": comparison, "gates": gates,
            "status": "passed" if all(gates.values()) else "failed"})
    after = inventory(package)
    report["package_unchanged"] = before == after
    report["previous_package_unchanged"] = previous_before == inventory(previous_package)
    report["status"] = ("passed" if report["package_unchanged"]
        and report["previous_package_unchanged"]
        and all(case["status"] == "passed" for case in report["cases"]) else "failed")
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "summary": str(output / "summary.json"),
                      "cases": [{"name": c["name"], "exit_code": c["exit_code"],
                                 "gates": c["gates"]} for c in report["cases"]]}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
