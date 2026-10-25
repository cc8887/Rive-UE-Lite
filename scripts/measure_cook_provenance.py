#!/usr/bin/env python3
"""Record an actual independent shader cook into a previously absent archive.

The command must invoke the declared compiler directly. This runner does not
claim that naming a program canonical makes its shader pipeline canonical;
source/build evidence remains mandatory and is audited by the paired harness.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from compare_png import sha256
from measure_pair import source_pins


def file_evidence(path: Path) -> dict:
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256(path)}


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("lite_helper", "ue_engine_canonical"), required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--build-log", action="append", type=Path, required=True)
    parser.add_argument("--source-input", action="append", type=Path, required=True)
    parser.add_argument("--env", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--timeout", type=float, default=1800)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or Path(command[0]).resolve() != args.compiler.resolve():
        parser.error("command must invoke --compiler directly, without a shell wrapper")
    if not any(str(args.archive.resolve()) in value for value in command):
        parser.error("command must explicitly name the new absolute --archive output")
    if args.archive.exists():
        parser.error("archive already exists; cannot attribute a reused output to an independent cook")
    directory = args.output_dir.resolve()
    if directory.exists() and any(directory.iterdir()):
        parser.error("use a fresh provenance output directory")
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for source in args.source_input:
        paths.extend(sorted(path for path in source.rglob("*") if path.is_file()) if source.is_dir() else [source])
    pins = source_pins(root)
    report = {"schema_version": 1, "kind": args.kind, "source_pins": pins,
              "compiler": file_evidence(args.compiler),
              "build_logs": [file_evidence(path) for path in args.build_log],
              "source_inputs": [file_evidence(path) for path in sorted(set(paths))],
              "cook_execution": {"execution_id": str(uuid.uuid4()), "command": command,
                                 "archive_absent_before_invocation": True, "executed": False},
              "scope": "recorded independent process invocation and artifact identity; pipeline semantics require source review",
              "status": "incomplete"}
    env = dict(os.environ, LC_ALL="C", LANG="C")
    for value in args.env:
        if "=" not in value:
            parser.error("--env must be KEY=VALUE")
        key, setting = value.split("=", 1)
        env[key] = setting
    report["environment_overrides"] = dict(value.split("=", 1) for value in args.env)
    if args.execute:
        if pins["status"] != "passed":
            parser.error("source revision identity is incomplete or conflicting")
        args.archive.parent.mkdir(parents=True, exist_ok=True)
        log_path = directory / "cook.log"
        execution = report["cook_execution"]
        execution["started_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        start = time.perf_counter()
        try:
            with log_path.open("wb") as log:
                result = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
                                        timeout=args.timeout, check=False)
            execution["exit_code"] = result.returncode
        except subprocess.TimeoutExpired:
            execution.update(exit_code=None, timed_out=True)
        execution.update(executed=True, finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                         wall_seconds=time.perf_counter() - start, log=file_evidence(log_path))
        if args.archive.is_file():
            execution["output"] = file_evidence(args.archive)
        manifest = args.archive.with_name(args.archive.name + ".manifest.json")
        manifest_complete = False
        if manifest.is_file():
            report["archive_manifest"] = file_evidence(manifest)
            try:
                manifest_data = json.loads(manifest.read_text())
                manifest_complete = isinstance(manifest_data, dict) and manifest_data.get("complete") is True
                report["formal_unfiltered_domain"] = bool(manifest_complete and not manifest_data.get("type_filter", "") and not manifest_data.get("list_only", False))
            except (OSError, ValueError) as error:
                report["manifest_error"] = str(error)
        report["archive_manifest_complete"] = manifest_complete
        report["status"] = ("failed" if execution.get("exit_code") != 0 else
                            "passed" if execution.get("output") and manifest_complete else "incomplete")
    output = directory / "provenance.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "kind": args.kind, "output": str(output)}, indent=2))
    return {"passed": 0, "failed": 1, "incomplete": 2}[report["status"]] if args.execute else 0


if __name__ == "__main__":
    raise SystemExit(main())
