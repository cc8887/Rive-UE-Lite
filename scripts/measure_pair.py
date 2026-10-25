#!/usr/bin/env python3
"""Plan or execute a same-input UE Engine Program / lite capture benchmark.

Default is plan-only. --execute requires Linux inside measure_no_gpu.sh, a
staged lite package and a successfully built real Engine reference executable.
It never builds or stages a package, and never accepts a bootstrap probe.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

from compare_png import sha256
from measure_ue_lite import apply_cpu_profile, inspect_build, reference_provenance, run_once, summarize_status


def reference_capture_evidence(log: str, actual: Path, image: dict | None, width: int, height: int, utexture: bool) -> dict:
    lines = [line.split("RIVE_UE_REFERENCE_CAPTURE ", 1)[1] for line in log.splitlines() if "RIVE_UE_REFERENCE_CAPTURE " in line]
    if not lines:
        return {"status": "incomplete", "reason": "real Engine Program completion marker absent"}
    try:
        fields = dict(token.split("=", 1) for token in shlex.split(lines[-1]) if "=" in token)
    except ValueError as error:
        return {"status": "incomplete", "reason": str(error)}
    requirements = {"render_path": "UE_RHI_RDG", "engine_linked": "1", "renderer_linked": "1",
                    "engine_frender_target": "1", "utexture_target": str(int(utexture)),
                    "editor_viewport": "0", "umg_composite": "0", "width": str(width), "height": str(height)}
    failures = [key for key, value in requirements.items() if fields.get(key) != value]
    path = Path(fields.get("path", ""))
    if not path.is_absolute() or path.resolve() != actual.resolve():
        failures.append("path")
    if not image or (image["width"], image["height"]) != (width, height):
        failures.append("decoded_png")
    return {"status": "failed" if failures else "passed", "marker": fields, "mismatches": failures,
            "scope": "source-reviewed Engine FRenderTarget completion marker; not an Editor viewport or UMG composite"}


def reference_linkage(receipt: Path, link_map: Path, executable: Path) -> dict:
    inspection = inspect_build([receipt], [link_map], executable)
    modules = set(inspection["recognized_modules"])
    required = {"Core", "RHI", "RenderCore", "Engine", "Renderer", "RiveUeReference", "RiveUeReferenceRenderer"}
    valid = required <= modules and inspection["receipt_product_name_matches"] and not inspection["errors"]
    return {"status": "passed" if valid else "incomplete", "required_modules": sorted(required),
            "recognized_modules": sorted(modules), "missing_modules": sorted(required - modules),
            "evidence": inspection["evidence"], "errors": inspection["errors"]}


def revision(path: Path) -> str | None:
    if not path.is_dir():
        return None
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel", "HEAD"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    values = result.stdout.strip().splitlines()
    if result.returncode or len(values) != 2 or Path(values[0]).resolve() != path.resolve():
        return None
    return values[1] if len(values[1]) == 40 and all(value in "0123456789abcdef" for value in values[1]) else None


def source_pins(root: Path) -> dict:
    """Use exact repository roots or cross-checked recorded manifests, never a parent repository HEAD."""
    candidates = {"engine_commit": [], "rive_unreal_commit": [], "rive_runtime_commit": []}
    git_paths = {"engine_commit": root / "engine", "rive_unreal_commit": root / "vendor/rive-unreal",
                 "rive_runtime_commit": root / "vendor/rive-unreal/submodules/rive-runtime"}
    evidence = []
    for key, path in git_paths.items():
        value = revision(path)
        if value:
            candidates[key].append(value)
            evidence.append({"pin": key, "value": value, "origin": "git rev-parse with exact repository toplevel check", "path": str(path)})
    sources = [
        (root / "artifacts/source-state.json", {"engine_commit": "engine_commit", "rive_unreal_commit": "rive_unreal_commit", "rive_runtime_commit": "rive_runtime_gitlink"}),
        (root / "Source/RiveLiteRenderer/upstream-manifest.json", {"rive_unreal_commit": "source_commit", "rive_runtime_commit": "runtime_commit"}),
        (root / "Source/RiveUeReferenceRenderer/upstream-manifest.json", {"rive_unreal_commit": "source_commit", "rive_runtime_commit": "runtime_commit"}),
        (root / "Source/RiveLiteRenderer/native-build-result.json", {"rive_runtime_commit": "runtime_commit"}),
    ]
    errors = []
    for path, fields in sources:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            for key, field in fields.items():
                value = data.get(field)
                if isinstance(value, str) and len(value) == 40 and all(char in "0123456789abcdef" for char in value):
                    candidates[key].append(value)
                    evidence.append({"pin": key, "value": value, "origin": "recorded provenance manifest", "path": str(path), "manifest_sha256": sha256(path), "field": field})
        except (OSError, ValueError) as error:
            errors.append(f"{path}: {error}")
    pins = {}
    for key, values in candidates.items():
        unique = sorted(set(values))
        pins[key] = unique[0] if len(unique) == 1 else None
        if len(unique) > 1:
            errors.append(f"conflicting {key}: {unique}")
    return {"status": "failed" if errors else "passed" if all(pins.values()) else "incomplete", "pins": pins,
            "evidence": evidence, "errors": errors,
            "scope": "source revision identity and declared native inputs; preserves manifest origins when copied directories have no valid Git metadata"}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lite-executable", type=Path, required=True)
    parser.add_argument("--lite-package-dir", type=Path, required=True)
    parser.add_argument("--lite-receipt", type=Path, default=root / "Binaries/Linux/RiveRhiLite.target")
    parser.add_argument("--lite-link-map", type=Path, default=root / "Intermediate/Build/Linux/x64/RiveRhiLite/Development/RiveRhiLite.link.rsp")
    parser.add_argument("--reference-executable", type=Path, default=root / "Binaries/Linux/RiveUeReference")
    parser.add_argument("--reference-receipt", type=Path, default=root / "Binaries/Linux/RiveUeReference.target")
    parser.add_argument("--reference-link-map", type=Path, default=root / "Intermediate/Build/Linux/x64/RiveUeReference/Development/RiveUeReference.link.rsp")
    parser.add_argument("--reference-project-dir", type=Path, default=root)
    parser.add_argument("--fixture", type=Path, required=True, help="use the staged package fixtures/input.riv for both programs")
    parser.add_argument("--shader-archive", type=Path, required=True, help="use the staged package shaders/global.bin for both programs")
    parser.add_argument("--shader-directory", type=Path, required=True, help="identical virtual shader mapping source directory for both programs")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--icd", type=Path, default=Path("/usr/share/vulkan/icd.d/lvp_icd.json"))
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--seconds", type=float, default=0)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--cpu-limit", type=int)
    parser.add_argument("--lp-num-threads", type=int)
    parser.add_argument("--utexture-target", action="store_true", help="reference uses genuine UTextureRenderTarget2D; may require additional real Engine default assets")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    directory = args.output_dir.resolve()
    if directory.exists() and any(directory.iterdir()):
        parser.error("use a fresh output directory; evidence is never overwritten")
    directory.mkdir(parents=True, exist_ok=True)
    package = args.lite_package_dir.resolve()
    common = ["-vulkan", "-sm5", "-RenderOffScreen", "-AllowCPUDevices", "-unattended", "-norhithread",
              "-NoSplash", "-NoCrashDialog", "-stdout", "-FullStdOutLogOutput",
              f"-Input={args.fixture.resolve()}", f"-ShaderArchive={args.shader_archive.resolve()}",
              f"-ShaderDirectory={args.shader_directory.resolve()}", f"-Width={args.width}",
              f"-Height={args.height}", f"-Seconds={args.seconds}"]
    reference_dir = directory / "reference"
    reference_png = reference_dir / "run-000.png"
    reference_args = common + [f"-ProjectDir={args.reference_project_dir.resolve()}/", "-Output={output}",
                               f"-UserDir={directory / 'reference-user'}/", f"-abslog={reference_dir}/run-{{iteration}}.ue.log"]
    if args.utexture_target:
        reference_args.append("-UTextureTarget")
    lite_args = common + [f"-ProjectDir={package}/", "-Output={output}"]
    measure_command = [sys.executable, str(Path(__file__).with_name("measure_ue_lite.py")),
                       "--executable", str(args.lite_executable.resolve()), "--package-dir", str(package),
                       "--output-dir", str(directory / "lite"), "--receipt", str(args.lite_receipt.resolve()),
                       "--link-map", str(args.lite_link_map.resolve()), "--reference", str(reference_png),
                       "--icd", str(args.icd.resolve()), "--repeat", str(args.repeat), "--timeout", str(args.timeout),
                       "--driver-cache-dir", str(directory / "lite-driver-cache")]
    if args.cpu_limit is not None:
        measure_command.extend(["--cpu-limit", str(args.cpu_limit)])
    if args.lp_num_threads is not None:
        measure_command.extend(["--lp-num-threads", str(args.lp_num_threads)])
    measure_command += [f"--run-arg={value}" for value in lite_args]
    plan = {"status": "prepared", "acceptance": "incomplete", "scope": "real Engine Program reference versus lite UE RHI/RDG; not Editor/UMG parity",
            "reference_command": [str(args.reference_executable.resolve()), *reference_args],
            "lite_measure_command": measure_command,
            "shared_fixture": str(args.fixture.resolve()), "shared_shader_archive": str(args.shader_archive.resolve()),
            "shared_shader_directory": str(args.shader_directory.resolve()),
            "output_placeholder": "run_once substitutes each unique absolute PNG path",
            "not_run": not args.execute,
            "requested_cpu_profile": {"cpu_limit": args.cpu_limit, "LP_NUM_THREADS": args.lp_num_threads},
            "cache_policy": {"reference": str(directory / "reference-driver-cache"), "lite": str(directory / "lite-driver-cache"),
                             "independent_fresh_mesa_disk_caches": True, "os_page_cache_claimed_cold": False}}
    (directory / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    inputs = [args.lite_executable, args.lite_receipt, args.lite_link_map, args.reference_executable,
              args.reference_receipt, args.reference_link_map, args.fixture, args.shader_archive, args.icd]
    missing = [str(path) for path in inputs if not path.is_file()]
    if not args.shader_directory.is_dir():
        missing.append(str(args.shader_directory))
    gpu_visible = Path("/dev/dxg").exists() or any(Path("/dev/dri").glob("*"))
    external_assets = [str(path) for path in (args.fixture, args.shader_archive, args.shader_directory)
                       if not path.resolve().is_relative_to(package)]
    if not sys.platform.startswith("linux") or missing or gpu_visible or external_assets:
        plan.update(status="incomplete", missing_files=missing, gpu_device_nodes_visible=gpu_visible,
                    render_inputs_outside_staged_package=external_assets,
                    reason="execute requires Linux/no-GPU namespace, complete build inputs, and fixture/archive/shader-directory inside the staged lite package")
        (directory / "execution.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(plan, indent=2))
        return 2
    env = dict(os.environ, VK_ICD_FILENAMES=str(args.icd.resolve()), VK_DRIVER_FILES=str(args.icd.resolve()), LC_ALL="C", LANG="C")
    try:
        profile = apply_cpu_profile(args.cpu_limit, args.lp_num_threads, env)
    except ValueError as error:
        parser.error(str(error))
    for key in ("DISPLAY", "WAYLAND_DISPLAY"):
        env.pop(key, None)
    reference_dir.mkdir()
    initial_inputs = {"fixture_sha256": sha256(args.fixture), "shader_archive_sha256": sha256(args.shader_archive)}
    pins = source_pins(root)
    (directory / "source-provenance.json").write_text(json.dumps(pins, indent=2) + "\n", encoding="utf-8")
    reference_env = dict(env, MESA_SHADER_CACHE_DIR=str(directory / "reference-driver-cache"))
    lite_env = dict(env, MESA_SHADER_CACHE_DIR=str(directory / "lite-driver-cache"))
    linkage = reference_linkage(args.reference_receipt, args.reference_link_map, args.reference_executable)
    if linkage["status"] != "passed":
        (directory / "reference-linkage.json").write_text(json.dumps(linkage, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(linkage, indent=2))
        return 2
    reference_run = run_once(args.reference_executable.resolve(), reference_args, reference_png, 0, reference_dir,
                             reference_env, args.timeout, args.reference_executable.resolve().parent)
    reference_log = Path(reference_run["log"]).read_text(errors="replace") if Path(reference_run["log"]).is_file() else ""
    completion = reference_capture_evidence(reference_log, reference_png, reference_run.get("png"), args.width, args.height, args.utexture_target)
    (directory / "reference-capture.json").write_text(json.dumps({"linkage": linkage, "run": reference_run, "draw": completion}, indent=2) + "\n", encoding="utf-8")
    measured = subprocess.run(measure_command, env=lite_env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    (directory / "lite-measure.log").write_text(measured.stdout, encoding="utf-8")
    report_path = directory / "lite/report.json"
    if not report_path.is_file():
        print(json.dumps({"status": "incomplete", "reason": "lite measurement did not produce report", "log": str(directory / "lite-measure.log")}))
        return 2
    report = json.loads(report_path.read_text())
    gates = report["gates"]
    gates["ue_reference_linkage"] = linkage
    gates["ue_reference_draw"] = completion
    gates["ue_reference_process"] = {"status": reference_run["status"]}
    gates["ue_reference_cpu_vulkan"] = reference_run.get("runtime_device", {"status": "incomplete"})
    gates["gpu_device_nodes_hidden"] = {"status": "passed", "dxg_present": False, "dri_nodes": []}
    gates["source_revision_provenance"] = {"status": pins["status"], "report": str(directory / "source-provenance.json"), "errors": pins["errors"]}
    final_inputs = {"fixture_sha256": sha256(args.fixture), "shader_archive_sha256": sha256(args.shader_archive)}
    gates["shared_render_inputs_unchanged"] = {"status": "passed" if initial_inputs == final_inputs else "failed", "before": initial_inputs, "after": final_inputs}
    report["paired_cpu_profile"] = profile
    report["paired_cache_policy"] = plan["cache_policy"]
    actual = Path(report["runs"][0]["output_png"]) if report.get("runs") and "png" in report["runs"][0] else None
    if actual and reference_png.is_file():
        configuration = {**pins["pins"],
                         "fixture_sha256": sha256(args.fixture), "shader_archive_sha256": sha256(args.shader_archive),
                         "width": args.width, "height": args.height, "render_path": "UE RHI/RDG",
                         "color_space": "linear RGBA8 target, no SRGB flag, SetLinearToGamma(false), PNG EGammaSpace::Linear",
                         "alpha_mode": "raw RGBA readback; no alpha conversion", "sample_count": 1,
                         "frame_index": 0, "time_seconds": args.seconds, "clear_color": [0, 0, 0, 0]}
        evidence = {"reference": dict(configuration, host_kind="UE Engine program", png_sha256=sha256(reference_png)),
                    "prototype": dict(configuration, png_sha256=sha256(actual)),
                    "evidence_scope": "reference Engine FRenderTarget branch; editor_viewport=0; umg_composite=0",
                    "capture_commands": {"reference": reference_run["command"], "prototype": report["runs"][0]["command"]}}
        evidence_path = directory / "reference-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
        report["status_before_post_capture_hash_binding"] = report["status"]
        gates["ue_reference_provenance"] = reference_provenance(evidence_path, reference_png, actual)
    report["paired_reference_report"] = str(directory / "reference-capture.json")
    report["status"] = summarize_status(gates)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(report_path), "reference": str(directory / "reference-capture.json")}, indent=2))
    return {"passed": 0, "failed": 1, "incomplete": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
