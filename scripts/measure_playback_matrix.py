#!/usr/bin/env python3
"""Compare deterministic Rive playback using separately cooked shader archives.

Each sampled frame starts a new process and replays the complete scenario from
zero, including every prior input. Existing static benchmark reports are never
updated. Pixel thresholds are fixed at exact RGBA8 equality, including alpha.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import json
import math
import os
import re
import struct
import subprocess
import sys
import zlib
from pathlib import Path

from compare_png import compare_images, read_png, sha256
from measure_pair import reference_capture_evidence, reference_linkage, source_pins
from measure_ue_lite import apply_cpu_profile, inspect_build, run_once, summarize_status


def inspect_cook_provenance(path: Path, archive: Path, expected_kind: str, pins: dict) -> dict:
    errors, missing = [], []
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        return {"status": "incomplete", "reason": str(error)}
    if not isinstance(data, dict):
        return {"status": "incomplete", "reason": "cook provenance must be a JSON object"}

    def verify(record: dict | None, label: str):
        if not isinstance(record, dict) or not record.get("path") or not record.get("sha256"):
            missing.append(label)
            return
        target = Path(record["path"])
        if not target.is_file():
            missing.append(f"{label}: {target}")
        elif sha256(target) != record["sha256"]:
            errors.append(f"{label} hash differs: {target}")

    if data.get("kind") != expected_kind:
        errors.append("cooker kind differs from requested independent pipeline")
    declared_pins = data.get("source_pins", {}).get("pins", data.get("source_pins", {}))
    if not all(declared_pins.get(key) == value and value for key, value in pins.items()):
        errors.append("cooker source pins differ from current validated engine/Rive pins")
    compiler = data.get("compiler", {})
    verify(compiler, "compiler")
    for label in ("build_logs", "source_inputs"):
        records = data.get(label, [])
        if not records:
            missing.append(label)
        for index, record in enumerate(records):
            verify(record, f"{label}[{index}]")
    execution = data.get("cook_execution", {})
    for field in ("execution_id", "started_utc", "finished_utc", "command"):
        if not execution.get(field):
            missing.append(f"cook_execution.{field}")
    if execution.get("executed") is not True or execution.get("archive_absent_before_invocation") is not True:
        errors.append("independent invocation into an absent output is not recorded")
    if execution.get("exit_code") != 0 or data.get("status") != "passed":
        errors.append("actual cooker process did not complete successfully")
    command = execution.get("command", [])
    if not command or not compiler.get("path") or Path(command[0]).resolve() != Path(compiler["path"]).resolve():
        errors.append("declared compiler is not the directly executed program")
    if not any(str(archive.resolve()) in value for value in command):
        errors.append("cook command does not name the expected output archive")
    verify(execution.get("log"), "cook log")
    verify(execution.get("output"), "cook output")
    output = execution.get("output", {})
    if not output.get("path") or Path(output["path"]).resolve() != archive.resolve():
        errors.append("cook output path differs from selected archive")
    if not archive.is_file():
        missing.append("selected archive")
    elif output.get("sha256") != sha256(archive):
        errors.append("selected archive hash differs from actual cook output")
    verify(data.get("archive_manifest"), "archive manifest")
    manifest = {}
    manifest_record = data.get("archive_manifest", {})
    if manifest_record.get("path") and Path(manifest_record["path"]).is_file():
        try:
            manifest = json.loads(Path(manifest_record["path"]).read_text())
            if not isinstance(manifest, dict):
                raise ValueError("archive manifest must be an object")
        except (OSError, ValueError) as error:
            missing.append(f"archive manifest: {error}")
            manifest = {}
    if not manifest:
        missing.append("nonempty completed archive manifest")
    domain, rive_domain = set(), {}
    if manifest:
        if manifest.get("complete") is not True or manifest.get("type_filter", "") or manifest.get("list_only", False):
            errors.append("full unfiltered completed cook required; diagnostic/list-only/partial domain rejected")
        if manifest.get("with_engine") is not (expected_kind == "ue_engine_canonical") or manifest.get("with_editor") is not True:
            errors.append("manifest compiler Engine/editor contract differs")
        if "VULKAN_SM5" not in str(manifest.get("shader_platform", "")):
            errors.append("manifest shader platform differs from Vulkan SM5")
        rows = manifest.get("jobs" if expected_kind == "lite_helper" else "types", [])
        if not isinstance(rows, list) or not rows:
            missing.append("complete compiled permutation domain")
            rows = []
        seen_types = set()
        for row in rows:
            name, source = row.get("type"), row.get("source", "")
            if not isinstance(name, str) or not name:
                errors.append("compiled shader type identity missing")
                continue
            if expected_kind == "lite_helper":
                ids = [row.get("permutation")]
                if row.get("compiled") is not True:
                    errors.append(f"failed/uncompiled helper permutation: {name}")
            else:
                ids = row.get("permutation_ids")
                if name in seen_types:
                    errors.append(f"duplicate canonical type: {name}")
                seen_types.add(name)
                if not isinstance(ids, list):
                    missing.append(f"actual canonical permutation_ids: {name}")
                    continue
                if row.get("permutations") != len(ids):
                    errors.append(f"canonical permutation count differs: {name}")
            for identity in ids:
                if not isinstance(identity, int) or isinstance(identity, bool) or identity < 0:
                    errors.append(f"invalid compiled permutation id: {name}")
                    continue
                key = (name, identity)
                if key in domain:
                    errors.append(f"duplicate compiled permutation: {name}/{identity}")
                domain.add(key)
                if source.startswith("/Plugin/Rive/"):
                    rive_domain.setdefault(name, []).append(identity)
        if not rive_domain:
            errors.append("no actual compiled Rive shader domain")
        if expected_kind == "lite_helper":
            if manifest.get("compiled_permutations") != len(domain):
                errors.append("helper compiled permutation count does not match successful unique jobs")
        else:
            if manifest.get("target_platform") != "Linux" or manifest.get("loads_lite_archive") is not False:
                errors.append("canonical Linux target / independent archive-input contract differs")
            for key in ("selected_permutations", "submitted_jobs", "succeeded_jobs"):
                if manifest.get(key) != len(domain):
                    errors.append(f"canonical {key} does not match actual successful domain")
            if manifest.get("failed_jobs") != 0:
                errors.append("canonical failed job count is absent or nonzero")
        for values in rive_domain.values():
            values.sort()
    source = "\n".join(Path(record["path"]).read_text(errors="replace")
                       for record in data.get("source_inputs", [])
                       if record.get("path") and Path(record["path"]).is_file()
                       and Path(record["path"]).suffix in (".cpp", ".h", ".inl"))
    # These are source-review aids, not independent compiler instrumentation.
    checks = ({"BeginCompileShader_call": bool(re.search(r"FGlobalShaderTypeCompiler\s*::\s*BeginCompileShader\s*\(", source)),
               "FShaderCompilingManager_path": "FShaderCompilingManager" in source}
              if expected_kind == "ue_engine_canonical" else
              {"permutation_environment": "SetupCompileEnvironment" in source,
               "shader_compilation": "CompileShader" in source})
    if not all(checks.values()):
        missing.append("source-reviewed expected shader compiler API path")
    return {"status": "failed" if errors else "incomplete" if missing else "passed",
            "provenance": str(path.resolve()), "provenance_sha256": sha256(path), "kind": expected_kind,
            "archive": output, "compiler": compiler, "execution_id": execution.get("execution_id"),
            "cook_log": execution.get("log"), "source_path_checks": checks,
            "archive_manifest": manifest_record,
            "compiled_permutation_count": len(domain), "rive_permutation_count": sum(map(len, rive_domain.values())),
            "rive_domain_by_type": dict(sorted(rive_domain.items())),
            "errors": errors, "missing": missing,
            "scope": "hashed inputs/build logs and actual independent cook invocation; canonical path still bounded by source-reviewed cooker shader domain"}


def inspect_independent_cooks(lite: dict, reference: dict, lite_archive: Path, reference_archive: Path) -> dict:
    errors = []
    if lite_archive.resolve() == reference_archive.resolve():
        errors.append("both hosts select the same archive path")
    elif lite_archive.exists() and reference_archive.exists() and os.path.samefile(lite_archive, reference_archive):
        errors.append("both archive paths identify the same file/inode")
    if lite.get("execution_id") and lite.get("execution_id") == reference.get("execution_id"):
        errors.append("cook execution identifiers are shared")
    if lite.get("compiler", {}).get("path") == reference.get("compiler", {}).get("path"):
        errors.append("both cooks use the same program path")
    if lite.get("cook_log", {}).get("path") == reference.get("cook_log", {}).get("path"):
        errors.append("both cooks use the same execution log")
    if lite.get("rive_domain_by_type") != reference.get("rive_domain_by_type"):
        errors.append("independent cooks do not cover the same actual Rive shader type/permutation domain")
    status = "failed" if errors else summarize_status({"lite": lite, "reference": reference})
    return {"status": status, "errors": errors, "lite": lite, "reference": reference,
            "equal_archive_sha256_allowed": True,
            "scope": "distinct real cook outputs/commands/logs/programs; equal bytes alone neither prove nor refute independent cooking"}


def validate_scenario(case: dict) -> None:
    playback = case["playback"]
    mode = playback.get("mode")
    if mode not in ("animation", "state_machine") or not playback.get("artboard") or not playback.get(mode):
        raise ValueError("scenario must explicitly select a named artboard and animation or state machine")
    if playback.get("animation") and playback.get("state_machine"):
        raise ValueError("animation and state machine are mutually exclusive")
    delta = playback.get("fixed_delta", 0)
    times = case.get("sample_times", [])
    if not isinstance(delta, (int, float)) or not math.isfinite(delta) or delta <= 0:
        raise ValueError("fixed_delta must be positive and finite")
    if len(times) < 2 or times != sorted(set(times)):
        raise ValueError("sample_times must contain at least two sorted distinct times")
    events = playback.get("events", [])
    if mode == "state_machine" and not events:
        raise ValueError("state machine validation needs actual input events")
    ordered = [event["time"] for event in events]
    if ordered != sorted(ordered):
        raise ValueError("events must be sorted; same-tick order is preserved")
    for point in [*times, *ordered]:
        if not isinstance(point, (int, float)) or not math.isfinite(point) or point < 0 or abs(point - round(point / delta) * delta) > 1e-6:
            raise ValueError("sample/event times must be nonnegative fixed_delta ticks")
    for change in case.get("required_changes", [{"from": times[0], "to": times[-1]}]):
        if change["from"] not in times or change["to"] not in times or change["from"] >= change["to"]:
            raise ValueError("required_changes must reference ordered distinct sampled frames")
    if mode == "state_machine":
        effect_times = case.get("event_effect_sample_times", [times[-1]])
        if not effect_times or any(point not in times or not any(event["time"] <= point for event in events) for point in effect_times):
            raise ValueError("state machine input-effect checks need sampled times with at least one prior input")


def playback_evidence(path: Path, scenario: dict) -> dict:
    # Final helper metadata contract is checked here; never infer playback from
    # a different image, a requested command line, or a successful process exit.
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        return {"status": "incomplete", "reason": str(error)}
    if not isinstance(data, dict):
        return {"status": "incomplete", "reason": "playback metadata must be a JSON object"}
    errors, missing = [], []
    for key in ("mode", "artboard", scenario["mode"]):
        if data.get(key) != scenario.get(key):
            errors.append(f"selected {key} differs")
    for key in ("target_time", "fixed_delta"):
        if not isinstance(data.get(key), (int, float)) or abs(data[key] - scenario[key]) > 1e-6:
            errors.append(f"{key} differs")
    if data.get("schema_version") != 1 or data.get("status") != "completed":
        missing.append("completed real playback API evidence")
    for key in ("artboard_index", "selected_index"):
        if not isinstance(data.get(key), int) or data[key] < 0:
            missing.append(f"actual {key}")
    ticks = round(scenario["target_time"] / scenario["fixed_delta"])
    if data.get("advance_count") != ticks or data.get("initialization_advance_count") != 1:
        errors.append("actual replay step count differs from fixed timeline")
    if not isinstance(data.get("advanced_time"), (int, float)) or abs(data["advanced_time"] - scenario["target_time"]) > 1e-6:
        errors.append("actual accumulated advancement differs from capture time")
    api = data.get("api_calls", {})
    events = [event for event in scenario.get("events", []) if event["time"] <= scenario["target_time"] + 1e-6]
    settle_count = len({round(event["time"] / scenario["fixed_delta"]) for event in events if event["time"] > 1e-6}) if scenario["mode"] == "state_machine" else 0
    if data.get("event_settle_advance_count") != settle_count:
        errors.append("event boundary settling count differs from actual event ticks")
    required_api = (["animation_advance", "animation_apply", "artboard_advance"] if scenario["mode"] == "animation"
                    else ["state_machine_advance_and_apply"])
    for key in required_api:
        expected_count = ticks + 1 + (settle_count if key == "state_machine_advance_and_apply" else 0)
        if not isinstance(api.get(key), int) or api[key] != expected_count:
            missing.append(f"real {key} calls covering initialization and every tick")
    applied = data.get("events_applied")
    if not isinstance(applied, list) or len(applied) != len(events):
        errors.append("number of applied events differs from requested history")
    else:
        for index, (requested, actual) in enumerate(zip(events, applied)):
            if actual.get("tick") != round(requested["time"] / scenario["fixed_delta"]):
                errors.append(f"event {index} applied at wrong tick")
            for key, value in requested.items():
                actual_value = actual.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    same = isinstance(actual_value, (int, float)) and not isinstance(actual_value, bool) and abs(actual_value - value) <= 1e-6
                elif isinstance(value, bool):
                    same = isinstance(actual_value, bool) and actual_value == value
                else:
                    same = actual_value == value
                if not same:
                    errors.append(f"event {index} {key} differs")
    expected_values, fires, event_api = {}, {}, {}
    for event in events:
        kind = event["type"]
        if kind in ("bool", "number"):
            expected_values[event["name"]] = (kind, event["value"])
        elif kind == "trigger":
            fires[event["name"]] = fires.get(event["name"], 0) + 1
        api_name = {"bool": "bool_set", "number": "number_set", "trigger": "trigger_fire"}.get(kind, kind)
        event_api[api_name] = event_api.get(api_name, 0) + 1
    for key, value in event_api.items():
        if api.get(key) != value:
            errors.append(f"actual input API count {key} differs")
    final = {value.get("name"): value for value in data.get("final_inputs", [])}
    for name, (kind, value) in expected_values.items():
        actual = final.get(name, {})
        actual_value = actual.get("value")
        same = (isinstance(actual_value, bool) and actual_value == value if kind == "bool" else
                isinstance(actual_value, (int, float)) and not isinstance(actual_value, bool) and abs(actual_value - value) <= 1e-6)
        if actual.get("type") != kind or not same:
            errors.append(f"final input value {name} differs")
    for name, count in fires.items():
        actual = final.get(name, {})
        if actual.get("type") != "trigger" or actual.get("fire_count") != count:
            errors.append(f"trigger fire evidence {name} differs")
    if scenario["mode"] == "state_machine":
        for key in ("state_changes", "current_animations"):
            if not isinstance(data.get(key), list):
                missing.append(f"real {key} API evidence")
    if scenario["mode"] == "animation" and (not isinstance(data.get("animation_duration_seconds"), (int, float)) or data["animation_duration_seconds"] <= 0):
        missing.append("real selected animation duration")
    return {"status": "failed" if errors else "incomplete" if missing else "passed",
            "path": str(path.resolve()), "sha256": sha256(path), "metadata": data,
            "errors": errors, "missing": missing}


def input_effect_evidence(event_png: Path, control_png: Path, event_metadata: dict, control_metadata: dict) -> dict:
    pixels = compare_images(control_png, event_png)
    pixel_change = pixels.get("different_pixels", 0) > 0 and pixels.get("color_metadata_equal") is True
    state_differences = [key for key in ("state_changes", "current_animations")
                         if key in event_metadata and key in control_metadata and event_metadata[key] != control_metadata[key]]
    status = ("incomplete" if pixels["status"] == "incomplete" or not event_metadata or not control_metadata
              else "passed" if pixel_change and state_differences else "failed")
    return {"status": status, "pixel_content_changed": pixel_change, "state_evidence_different_fields": state_differences,
            "pixels": pixels,
            "scope": "same target time and fixed timeline, full inputs versus no inputs; both visible pixels and real state/animation evidence must differ"}


def legacy_playback_evidence(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as error:
        return {"status": "incomplete", "reason": str(error)}
    if not isinstance(data, dict):
        return {"status": "incomplete", "reason": "legacy metadata must be a JSON object"}
    errors = []
    if data.get("schema_version") != 1 or data.get("status") != "completed" or data.get("mode") != "legacy":
        errors.append("completed legacy/default-artboard API evidence missing")
    if data.get("target_time") != 0 or not isinstance(data.get("artboard"), str) or not data["artboard"]:
        errors.append("default artboard identity or time-zero evidence missing")
    calls = data.get("api_calls", {})
    if calls.get("artboard_advance") != 1 or any(value != 0 for key, value in calls.items() if key != "artboard_advance"):
        errors.append("legacy path must advance default artboard exactly once and select no playback driver/input API")
    return {"status": "failed" if errors else "passed", "path": str(path.resolve()), "sha256": sha256(path),
            "metadata": data, "errors": errors}


def pixel_content_evidence(path: Path, empty_allowed: bool) -> dict:
    try:
        image = read_png(path)
        rgba = image["rgba"]
        nontransparent = sum(alpha != 0 for alpha in rgba[3::4])
        unique = len(set(zip(rgba[0::4], rgba[1::4], rgba[2::4], rgba[3::4])))
        visible = nontransparent > 0 and unique >= 2
        return {"status": "passed" if visible or empty_allowed else "failed", "nontransparent_pixels": nontransparent,
                "unique_rgba_colors": unique, "visible_nonuniform_content": visible,
                "empty_initial_state_allowed": empty_allowed,
                "scope": "transparent initial clip_tests is allowed and does not verify a visible clipping result" if empty_allowed
                else "require nontransparent content and at least two distinct encoded RGBA values"}
    except (OSError, ValueError, zlib.error, struct.error) as error:
        return {"status": "incomplete", "reason": str(error)}


def coverage_evidence(cases: list[dict], static_fixtures: list[Path], profile: str, root: Path) -> dict:
    dynamic = sum(len(case["sample_times"]) for case in cases)
    controls = sum(len(case.get("event_effect_sample_times", [case["sample_times"][-1]]))
                   for case in cases if case["playback"]["mode"] == "state_machine")
    observed = {"static_pairs": len(static_fixtures), "dynamic_pairs": dynamic, "control_pairs": controls,
                "planned_capture_count": 2 * (len(static_fixtures) + dynamic + controls)}
    missing = []
    if profile == "independent-60-v1":
        expected_ids = {"bounce_animation", "rocket_bool", "number_transitions", "trigger_transitions", "pointer_toggle"}
        expected_static = {str((root / f"fixtures/{name}.riv").resolve()) for name in
                           ("fix_rectangle", "blend_test", "clip_tests", "bankcard", "circle_clips")}
        if {case["id"] for case in cases} != expected_ids:
            missing.append("the five agreed animation/state-machine scenarios")
        if len(static_fixtures) != 5 or {str(path.resolve()) for path in static_fixtures} != expected_static:
            missing.append("the original five distinct static fixtures")
        if (dynamic, controls, observed["planned_capture_count"]) != (19, 6, 60):
            missing.append("19 dynamic pairs + 6 control pairs + 5 static pairs / 60 captures")
        modes = [case["playback"]["mode"] for case in cases]
        if modes.count("animation") != 1 or modes.count("state_machine") != 4:
            missing.append("one named animation and four named state machines")
        event_types = {event["type"] for case in cases for event in case["playback"].get("events", [])}
        if not {"bool", "number", "trigger", "pointer_down", "pointer_up"} <= event_types:
            missing.append("bool/number/trigger/pointer input coverage")
    return {"status": "incomplete" if missing else "passed", "profile": profile, "planned": observed, "missing": missing,
            "scope": "agreed independent 60-capture validation" if profile == "independent-60-v1" else "explicit custom selection only; not the agreed full 60-capture matrix"}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    for side in ("lite", "reference"):
        parser.add_argument(f"--{side}-executable", type=Path, required=True)
        parser.add_argument(f"--{side}-archive", type=Path, required=True)
        parser.add_argument(f"--{side}-cook-provenance", type=Path, required=True)
        parser.add_argument(f"--{side}-shader-directory", type=Path, required=True)
        parser.add_argument(f"--{side}-project-dir", type=Path, default=root)
    parser.add_argument("--scenario-manifest", type=Path, required=True)
    parser.add_argument("--static-fixture", type=Path, action="append", help="default: the original five fixtures; identities must match source-state.json")
    parser.add_argument("--coverage-profile", choices=("independent-60-v1", "custom-selected"), default="independent-60-v1")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--cpu-limit", type=int)
    parser.add_argument("--lp-num-threads", type=int)
    parser.add_argument("--icd", type=Path, default=Path("/usr/share/vulkan/icd.d/lvp_icd.json"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    directory = args.output_dir.resolve()
    if directory.exists() and any(directory.iterdir()):
        parser.error("use a fresh output directory; prior evidence is never overwritten")
    directory.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "status": "incomplete", "executed": False, "gates": {}, "scenarios": [], "static_fixtures": [],
              "scope": "animation/state-machine correctness using independent shader cooks; not an update to prior package/performance benchmark",
              "reference_scope": "Engine Program FRenderTarget RHI/RDG; not Editor viewport/UMG composite",
              "pixel_policy": "full image exact encoded RGBA8 including alpha; no mask or tolerance",
              "playback_policy": "each frame starts from zero and deterministically replays all prior events at fixed_delta ticks"}
    output = directory / "summary.json"

    def save():
        report["status"] = summarize_status(report["gates"]) if report["gates"] else "incomplete"
        output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"status": report["status"], "executed": report["executed"], "output": str(output)}, indent=2))
        return {"passed": 0, "failed": 1, "incomplete": 2}[report["status"]]

    try:
        manifest = json.loads(args.scenario_manifest.read_text())
        cases = manifest["scenarios"]
        if not cases or len({case["id"] for case in cases}) != len(cases):
            raise ValueError("scenario ids must be distinct and nonempty")
        for case in cases:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", case["id"]):
                raise ValueError("scenario id must be a safe single directory name")
            validate_scenario(case)
    except (OSError, ValueError, KeyError, TypeError) as error:
        report["gates"]["scenario_manifest"] = {"status": "incomplete", "reason": str(error)}
        return save()
    report["scenario_manifest"] = {"path": str(args.scenario_manifest.resolve()), "sha256": sha256(args.scenario_manifest)}
    static_fixtures = args.static_fixture or [root / f"fixtures/{name}.riv" for name in
                                             ("fix_rectangle", "blend_test", "clip_tests", "bankcard", "circle_clips")]
    report["planned_static_fixtures"] = [str(path.resolve()) for path in static_fixtures]
    report["gates"]["requested_coverage"] = coverage_evidence(cases, static_fixtures, args.coverage_profile, root)
    report["planned_inputs"] = {side: {key: str(getattr(args, f"{side}_{key}").resolve())
                                      for key in ("executable", "archive", "cook_provenance", "shader_directory", "project_dir")}
                                for side in ("lite", "reference")}
    if not args.execute:
        report["gates"]["execution_requested"] = {"status": "incomplete", "reason": "prepared only; pass --execute when both independent cooks and playback hosts are ready"}
        return save()
    fixtures = []
    for case in cases:
        fixture = Path(case["fixture"])
        fixtures.append(fixture if fixture.is_absolute() else args.scenario_manifest.resolve().parent / fixture)
    required_files = [args.lite_executable, args.reference_executable, args.lite_archive, args.reference_archive,
                      args.lite_cook_provenance, args.reference_cook_provenance, args.icd, root / "artifacts/source-state.json", *fixtures, *static_fixtures]
    missing = [str(path) for path in required_files if not path.is_file()]
    missing.extend(str(path) for path in (args.lite_shader_directory, args.reference_shader_directory) if not path.is_dir())
    report["gates"]["runtime_inputs_present"] = {"status": "incomplete" if missing else "passed", "missing": missing}
    if missing:
        return save()
    identities = [{"fixture": str(path.resolve()), "declared_sha256": case.get("fixture_sha256"), "actual_sha256": sha256(path)}
                  for case, path in zip(cases, fixtures)]
    report["gates"]["fixture_identity"] = {"status": "incomplete" if any(not item["declared_sha256"] for item in identities)
                                           else "passed" if all(item["declared_sha256"] == item["actual_sha256"] for item in identities) else "failed",
                                           "fixtures": identities}
    source_state = json.loads((root / "artifacts/source-state.json").read_text())
    pinned_fixtures = {str((root / item["path"]).resolve()): item["sha256"] for item in source_state.get("fixtures", [])}
    static_identities = [{"fixture": str(path.resolve()), "declared_sha256": pinned_fixtures.get(str(path.resolve())), "actual_sha256": sha256(path)}
                         for path in static_fixtures]
    report["gates"]["static_fixture_identity"] = {"status": "incomplete" if any(not item["declared_sha256"] for item in static_identities)
                                                  else "passed" if all(item["declared_sha256"] == item["actual_sha256"] for item in static_identities) else "failed",
                                                  "source_state_sha256": sha256(root / "artifacts/source-state.json"), "fixtures": static_identities}
    report["gates"]["linux_no_gpu"] = {
        "status": "passed" if sys.platform.startswith("linux") and os.environ.get("RIVE_UE_LITE_GPU_DEVICES_HIDDEN") == "1"
        and not Path("/dev/dxg").exists() and not Path("/dev/dri").exists() else "incomplete",
        "dxg_present": Path("/dev/dxg").exists(), "dri_present": Path("/dev/dri").exists(),
        "mount_namespace": os.readlink("/proc/self/ns/mnt") if sys.platform.startswith("linux") else None}
    pins = source_pins(root)
    report["gates"]["source_pins"] = pins
    cooks = {}
    for side, kind in (("lite", "lite_helper"), ("reference", "ue_engine_canonical")):
        cooks[side] = inspect_cook_provenance(getattr(args, f"{side}_cook_provenance"), getattr(args, f"{side}_archive"), kind, pins["pins"])
        target = "RiveRhiLite" if side == "lite" else "RiveUeReference"
        receipt = root / f"Binaries/Linux/{target}.target"
        link = root / f"Intermediate/Build/Linux/x64/{target}/Development/{target}.link.rsp"
        function = inspect_build if side == "lite" else reference_linkage
        report["gates"][f"{side}_linkage"] = (function([receipt], [link], args.lite_executable) if side == "lite"
                                                          else function(receipt, link, args.reference_executable))
    report["gates"]["independent_shader_cooks"] = inspect_independent_cooks(cooks["lite"], cooks["reference"], args.lite_archive, args.reference_archive)
    if summarize_status(report["gates"]) != "passed":
        return save()
    env = dict(os.environ, VK_ICD_FILENAMES=str(args.icd.resolve()), VK_DRIVER_FILES=str(args.icd.resolve()), LC_ALL="C", LANG="C")
    for key in ("DISPLAY", "WAYLAND_DISPLAY"):
        env.pop(key, None)
    report["cpu_profile"] = apply_cpu_profile(args.cpu_limit, args.lp_num_threads, env)
    report["driver_cache_policy"] = {
        "directories": {side: str(directory / f"{side}-driver-cache") for side in ("lite", "reference")},
        "directories_absent_before_captures": all(not (directory / f"{side}-driver-cache").exists() for side in ("lite", "reference")),
        "reuse_policy": "each host starts with a distinct fresh Mesa directory; subsequent frames of that host reuse it",
        "MESA_SHADER_CACHE_DISABLE": env.get("MESA_SHADER_CACHE_DISABLE"),
        "MESA_DISK_CACHE_SINGLE_FILE": env.get("MESA_DISK_CACHE_SINGLE_FILE"),
        "timing_scope": "correctness diagnostic process times only; not cold-start performance or an OS page-cache cold claim"}
    probe_path = directory / "vulkan-environment.json"
    probe = subprocess.run([sys.executable, str(Path(__file__).with_name("measure_vulkan_probe.py")), "--icd", str(args.icd), "--output", str(probe_path)],
                           env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    (directory / "vulkan-environment.stdout.log").write_text(probe.stdout)
    enumeration = json.loads(probe_path.read_text()) if probe_path.is_file() else {"status": "incomplete"}
    report["gates"]["cpu_vulkan_enumeration"] = {"status": enumeration["status"], "path": str(probe_path)}
    if enumeration["status"] != "passed":
        return save()
    immutable_inputs = [*required_files, args.scenario_manifest]
    immutable_inputs.extend(path for folder in (root / "Source/RiveRhiLite", root / "Source/RiveUeReference", root / "Source/RivePlayback",
                                               root / "Source/RiveLiteRenderer", root / "Source/RiveUeReferenceRenderer")
                            for path in folder.rglob("*") if path.is_file() and path.suffix in (".cpp", ".h", ".cs", ".json"))
    immutable_inputs.extend(Path(item["path"]) for item in pins.get("evidence", [])
                            if item.get("path") and Path(item["path"]).is_file())
    initial = {str(path.resolve()): sha256(path) for path in sorted(set(immutable_inputs))}
    report["immutable_input_hashes_before"] = initial
    report["host_executables"] = {side: {"path": str(getattr(args, f"{side}_executable").resolve()),
                                         "bytes": getattr(args, f"{side}_executable").stat().st_size,
                                         "sha256": sha256(getattr(args, f"{side}_executable"))} for side in ("lite", "reference")}

    def capture_host(side: str, run_dir: Path, fixture: Path, scenario_path: Path | None, scenario: dict | None) -> dict:
        run_dir.mkdir(parents=True)
        png, metadata = run_dir / "output.png", run_dir / "playback.json"
        command = ["-vulkan", "-sm5", "-RenderOffScreen", "-AllowCPUDevices", "-unattended", "-norhithread",
                   "-NoSplash", "-NoCrashDialog", "-stdout", "-FullStdOutLogOutput",
                   f"-Input={fixture.resolve()}", f"-ShaderArchive={getattr(args, f'{side}_archive').resolve()}",
                   f"-ShaderDirectory={getattr(args, f'{side}_shader_directory').resolve()}",
                   f"-ProjectDir={getattr(args, f'{side}_project_dir').resolve()}/",
                   f"-Width={args.width}", f"-Height={args.height}",
                   f"-PlaybackMetadata={metadata}", f"-UserDir={run_dir / 'user'}/", f"-abslog={run_dir / 'ue.log'}", "-Output={output}"]
        command.append(f"-Scenario={scenario_path}" if scenario_path else "-Seconds=0")
        run_env = dict(env, MESA_SHADER_CACHE_DIR=str(directory / f"{side}-driver-cache"))
        run = run_once(getattr(args, f"{side}_executable").resolve(), command, png, 0, run_dir, run_env, args.timeout, root)
        log = Path(run["log"]).read_text(errors="replace") if Path(run["log"]).is_file() else ""
        draw = run.get("rive_draw", {"status": "incomplete", "reason": "process did not provide draw evidence"}) if side == "lite" else reference_capture_evidence(log, png, run.get("png"), args.width, args.height, False)
        playback = playback_evidence(metadata, scenario) if scenario else legacy_playback_evidence(metadata)
        gates = {"process": {"status": "failed" if run.get("timed_out") else run["status"]}, "draw": draw, "playback": playback,
                 "cpu_vulkan_runtime": run.get("runtime_device", {"status": "incomplete", "reason": "no selected device evidence"})}
        return {"status": summarize_status(gates), "gates": gates, "run": run}

    report["executed"] = True
    for fixture in static_fixtures:
        identifier = f"static_{fixture.stem}"
        frame = {"target_time": 0, "mode": "legacy", "hosts": {}}
        for side in ("reference", "lite"):
            result = capture_host(side, directory / identifier / side, fixture, None, None)
            content = pixel_content_evidence(Path(result["run"]["output_png"]), fixture.stem == "clip_tests")
            result["gates"]["pixel_content"] = content
            result["status"] = summarize_status(result["gates"])
            frame["hosts"][side] = result
        frame["pixels"] = compare_images(Path(frame["hosts"]["reference"]["run"]["output_png"]), Path(frame["hosts"]["lite"]["run"]["output_png"]))
        equal = frame["hosts"]["reference"]["gates"]["playback"].get("metadata") == frame["hosts"]["lite"]["gates"]["playback"].get("metadata")
        frame["playback_metadata_equal"] = {"status": "passed" if equal else "failed"}
        frame["status"] = summarize_status({"pixels": frame["pixels"], "playback_metadata_equal": frame["playback_metadata_equal"], **frame["hosts"]})
        report["static_fixtures"].append({"id": identifier, "fixture": {"path": str(fixture.resolve()), "sha256": sha256(fixture)},
                                          "status": frame["status"], "frames": [frame], "changes": [],
                                          "scope": "default artboard/time0; transparent initial clip_tests, no visible clipping claim" if fixture.stem == "clip_tests"
                                          else "default artboard/time0; nontransparent content and at least two RGBA colors required"})
        report["gates"][identifier] = {"status": frame["status"]}
        output.write_text(json.dumps(report, indent=2) + "\n")
    for case in cases:
        case_dir = directory / case["id"]
        case_dir.mkdir()
        fixture = Path(case["fixture"])
        fixture = fixture if fixture.is_absolute() else args.scenario_manifest.resolve().parent / fixture
        case_report = {"id": case["id"], "fixture": {"path": str(fixture.resolve()), "sha256": sha256(fixture)}, "frames": [], "changes": []}
        frame_paths = {"lite": {}, "reference": {}}
        for index, point in enumerate(case["sample_times"]):
            scenario = dict(copy.deepcopy(case["playback"]), target_time=point)
            scenario_path = case_dir / f"scenario-{index:03d}.json"
            scenario_path.write_text(json.dumps(scenario, indent=2) + "\n")
            frame = {"target_time": point, "scenario": {"path": str(scenario_path), "sha256": sha256(scenario_path)}, "hosts": {}}
            for side in ("reference", "lite"):
                run_dir = case_dir / side / f"frame-{index:03d}"
                frame["hosts"][side] = capture_host(side, run_dir, fixture, scenario_path, scenario)
                frame_paths[side][point] = run_dir / "output.png"
            frame["pixels"] = compare_images(frame_paths["reference"][point], frame_paths["lite"][point])
            metadata_equal = frame["hosts"]["reference"]["gates"]["playback"].get("metadata") == frame["hosts"]["lite"]["gates"]["playback"].get("metadata")
            frame["playback_metadata_equal"] = {"status": "passed" if metadata_equal else "failed"}
            frame["status"] = summarize_status({"pixels": frame["pixels"], "playback_metadata_equal": frame["playback_metadata_equal"], **frame["hosts"]})
            case_report["frames"].append(frame)
        if case["playback"]["mode"] == "state_machine":
            case_report["input_effect_controls"] = []
            for control_index, point in enumerate(case.get("event_effect_sample_times", [case["sample_times"][-1]])):
                control_scenario = dict(copy.deepcopy(case["playback"]), target_time=point, events=[])
                control_path = case_dir / f"no-events-{control_index:03d}.json"
                control_path.write_text(json.dumps(control_scenario, indent=2) + "\n")
                event_frame = next(frame for frame in case_report["frames"] if frame["target_time"] == point)
                control = {"target_time": point, "scenario": {"path": str(control_path), "sha256": sha256(control_path)}, "hosts": {}}
                for side in ("reference", "lite"):
                    result = capture_host(side, case_dir / side / f"no-events-{control_index:03d}", fixture, control_path, control_scenario)
                    event_metadata = event_frame["hosts"][side]["gates"]["playback"].get("metadata", {})
                    control_metadata = result["gates"]["playback"].get("metadata", {})
                    result["input_effect"] = input_effect_evidence(frame_paths[side][point], Path(result["run"]["output_png"]),
                                                                  event_metadata, control_metadata)
                    result["status"] = summarize_status({"control_capture": {"status": result["status"]}, "input_effect": result["input_effect"]})
                    control["hosts"][side] = result
                control["pixels"] = compare_images(Path(control["hosts"]["reference"]["run"]["output_png"]),
                                                   Path(control["hosts"]["lite"]["run"]["output_png"]))
                equal = control["hosts"]["reference"]["gates"]["playback"].get("metadata") == control["hosts"]["lite"]["gates"]["playback"].get("metadata")
                control["playback_metadata_equal"] = {"status": "passed" if equal else "failed"}
                control["status"] = summarize_status({"pixels": control["pixels"], "playback_metadata_equal": control["playback_metadata_equal"], **control["hosts"]})
                case_report["input_effect_controls"].append(control)
        for change in case.get("required_changes", [{"from": case["sample_times"][0], "to": case["sample_times"][-1]}]):
            for side in ("lite", "reference"):
                comparison = compare_images(frame_paths[side][change["from"]], frame_paths[side][change["to"]])
                changed = comparison.get("different_pixels", 0) > 0 and comparison.get("color_metadata_equal") is True
                case_report["changes"].append({"status": "passed" if changed else "failed", "host": side,
                                                "required_change": change, "comparison": comparison,
                                                "scope": "same-host content must actually change between these sampled frames"})
        case_report["status"] = summarize_status({**{f"frame-{i}": row for i, row in enumerate(case_report["frames"])},
                                                  **{f"change-{i}": row for i, row in enumerate(case_report["changes"])},
                                                  **{f"input-control-{i}": row for i, row in enumerate(case_report.get("input_effect_controls", []))}})
        if case.get("require_state_changes_after_events"):
            first_event = case["playback"]["events"][0]["time"]
            for side in ("lite", "reference"):
                changes = [change for frame in case_report["frames"]
                           for change in frame["hosts"][side]["gates"]["playback"].get("metadata", {}).get("state_changes", [])
                           if change.get("time", -1) >= first_event]
                state_gate = {"status": "passed" if changes else "failed", "host": side, "first_event_time": first_event,
                              "actual_post_input_state_changes": changes}
                case_report.setdefault("state_transition_evidence", []).append(state_gate)
            case_report["status"] = summarize_status({"frames_and_changes": {"status": case_report["status"]},
                                                       **{f"state-{i}": value for i, value in enumerate(case_report["state_transition_evidence"])}})
        report["scenarios"].append(case_report)
        report["gates"][f"scenario_{case['id']}"] = {"status": case_report["status"]}
        output.write_text(json.dumps(report, indent=2) + "\n")
    final = {str(path.resolve()): sha256(path) if path.is_file() else None for path in sorted(set(immutable_inputs))}
    report["gates"]["render_inputs_and_binaries_unchanged"] = {"status": "passed" if initial == final else "failed", "before": initial, "after": final}
    all_frames = [frame for group in [*report["static_fixtures"], *report["scenarios"]]
                  for frame in [*group["frames"], *group.get("input_effect_controls", [])]]
    captures = [result for frame in all_frames for result in frame["hosts"].values()]
    completed = sum(result.get("run", {}).get("exit_code") == 0 and "png" in result.get("run", {}) for result in captures)
    expected = report["gates"]["requested_coverage"]["planned"]["planned_capture_count"]
    report["gates"]["completed_capture_coverage"] = {"status": "passed" if len(captures) == completed == expected else "incomplete",
                                                    "expected": expected, "invoked": len(captures), "normal_exit_with_png": completed,
                                                    "profile": args.coverage_profile}
    return save()


if __name__ == "__main__":
    raise SystemExit(main())
