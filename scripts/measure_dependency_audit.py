#!/usr/bin/env python3
"""Refresh dependency evidence in existing reports without rerunning captures.

This is an audit-only repair: original inventory/status and report hash are
retained. Render timing, captured PNGs and measured tar archives are not changed.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path

from compare_png import sha256
from measure_ue_lite import inspect_vulkan_dependencies, summarize_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--icd", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    audit = {"timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
             "scope": "dependency inventory repair only; no executable invocation or performance rerun",
             "script_sha256": sha256(Path(__file__)),
             "mount_namespace": os.readlink("/proc/self/ns/mnt"),
             "gpu_device_nodes_absent": not Path("/dev/dxg").exists() and not Path("/dev/dri").exists(),
             "reports": []}
    for path in args.report:
        original_hash = sha256(path)
        report = json.loads(path.read_text())
        package = report["gates"]["package_measurement"]
        if sha256(args.executable) != package["executable_sha256"]:
            raise ValueError("executable differs from the measured ELF")
        measured_archive = Path(package["archive"]["path"])
        if sha256(measured_archive) != package["archive"]["sha256"]:
            raise ValueError("archive differs from the measured tar.gz")
        inventory = inspect_vulkan_dependencies(args.icd, Path(package["package_dir"]), package)
        report.setdefault("dependency_inventory_audit_history", []).append({
            "timestamp_utc": audit["timestamp_utc"],
            "report_sha256_before_audit": original_hash,
            "overall_status_before_audit": report["status"],
            "previous_inventory": report.get("runtime_dependency_inventory"),
            "reason": "resolve ldconfig outside regular-user PATH and require successful ELF dependency probes",
            "performance_rerun": False,
            "timings_pngs_and_archive_unchanged": True,
            "audit_script_sha256": audit["script_sha256"]})
        report["runtime_dependency_inventory"] = inventory
        report["gates"]["runtime_dependency_inventory"] = {
            "status": inventory["status"], "unresolved": inventory["unresolved"],
            "standalone_bundle": inventory["standalone_bundle"],
            "reason": "complete inventory required; listed external libraries are supplied by the measured Linux image"}
        report["status"] = summarize_status(report["gates"])
        path.write_text(json.dumps(report, indent=2) + "\n")
        audit["reports"].append({"path": str(path.resolve()), "sha256": sha256(path),
                                 "status": report["status"], "inventory": inventory})
    audit["status"] = summarize_status({str(index): item for index, item in enumerate(audit["reports"])})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps({"status": audit["status"], "output": str(args.output),
                      "external_library_bytes": [row["inventory"]["external_library_bytes_deduplicated"] for row in audit["reports"]],
                      "unresolved": [row["inventory"]["unresolved"] for row in audit["reports"]]}, indent=2))
    return {"passed": 0, "failed": 1, "incomplete": 2}[audit["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
