#!/usr/bin/env python3
"""Check real hosts reject invalid named playback instead of capturing a fallback."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario-manifest", type=Path, required=True)
    parser.add_argument("--lite-archive", type=Path, required=True)
    parser.add_argument("--reference-archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("RIVE_UE_LITE_GPU_DEVICES_HIDDEN") != "1" or Path("/dev/dxg").exists() or Path("/dev/dri").exists():
        parser.error("run through measure_no_gpu.sh in a GPU-free namespace")
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("use a fresh evidence directory")
    output.mkdir(parents=True, exist_ok=True)
    cases = json.loads(args.scenario_manifest.read_text())["scenarios"]
    animation = next(case for case in cases if case["playback"]["mode"] == "animation")
    machine = next(case for case in cases if case["playback"]["mode"] == "state_machine"
                   and any(event["type"] in ("bool", "number", "trigger") for event in case["playback"]["events"]))
    tests = []
    for identifier, case, field in (("missing-artboard", animation, "artboard"),
                                    ("missing-animation", animation, "animation"),
                                    ("missing-state-machine", machine, "state_machine")):
        scenario = dict(copy.deepcopy(case["playback"]), target_time=0)
        scenario[field] = "__missing_rive_playback_object__"
        tests.append((identifier, case, scenario, 5))
    scenario = dict(copy.deepcopy(machine["playback"]), target_time=0)
    scenario["events"] = [{"time": 1, "type": "trigger", "name": "__missing_future_input__"}]
    tests.append(("missing-future-input", machine, scenario, 5))
    scenario = dict(copy.deepcopy(machine["playback"]), target_time=0)
    original = next(event for event in scenario["events"] if event["type"] in ("bool", "number", "trigger"))
    kind = "number" if original["type"] != "number" else "bool"
    scenario["events"] = [{"time": 0, "name": original["name"], "type": kind, "value": 1.0 if kind == "number" else True}]
    tests.append(("wrong-input-type", machine, scenario, 5))
    scenario = dict(copy.deepcopy(animation["playback"]), target_time=-1)
    tests.append(("negative-time", animation, scenario, 2))
    env = dict(os.environ, VK_ICD_FILENAMES="/usr/share/vulkan/icd.d/lvp_icd.json",
               VK_DRIVER_FILES="/usr/share/vulkan/icd.d/lvp_icd.json")
    for key in ("DISPLAY", "WAYLAND_DISPLAY"):
        env.pop(key, None)
    report = {"scope": "actual invalid-playback process rejection; no fallback PNG or metadata", "tests": []}
    for identifier, case, scenario, expected_exit in tests:
        fixture = args.scenario_manifest.resolve().parent / case["fixture"]
        for side, target in (("lite", "RiveRhiLite"), ("reference", "RiveUeReference")):
            directory = output / identifier / side
            directory.mkdir(parents=True)
            scenario_path, png, metadata = (directory / name for name in ("scenario.json", "output.png", "playback.json"))
            scenario_path.write_text(json.dumps(scenario, indent=2) + "\n")
            command = [str(root / "Binaries/Linux" / target), "-vulkan", "-sm5", "-RenderOffScreen", "-AllowCPUDevices",
                       "-norhithread", "-unattended", "-stdout", "-NoCrashDialog", f"-ProjectDir={root}/",
                       f"-UserDir={directory / 'user'}/", f"-Input={fixture.resolve()}", f"-Output={png}",
                       f"-ShaderDirectory={root / 'Shaders'}", f"-ShaderArchive={getattr(args, side + '_archive').resolve()}",
                       f"-Scenario={scenario_path}", f"-PlaybackMetadata={metadata}", f"-abslog={directory / 'ue.log'}"]
            with (directory / "stdout.log").open("wb") as log:
                result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=90)
            passed = result.returncode == expected_exit and not png.exists() and not metadata.exists()
            report["tests"].append({"case": identifier, "host": side, "command": command,
                                    "expected_exit": expected_exit, "actual_exit": result.returncode,
                                    "png_present": png.exists(), "metadata_present": metadata.exists(),
                                    "status": "passed" if passed else "failed"})
    report["status"] = "passed" if all(test["status"] == "passed" for test in report["tests"]) else "failed"
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "tests": len(report["tests"]), "output": str(output / "summary.json")}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
