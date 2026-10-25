#!/usr/bin/env python3
"""Summarize retained real measurement reports; never launch render processes."""
from __future__ import annotations

import argparse
import datetime
import json
from pathlib import Path

from compare_png import compare_images, sha256
from measure_ue_lite import summarize_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", type=Path, required=True)
    parser.add_argument("--build-exclusion", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build = json.loads(args.build_exclusion.read_text())
    summary = {"schema_version": 1, "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
               "scope": "retained Linux CPU Vulkan Rive UE RHI/RDG fresh-process captures; no performance rerun",
               "reference_scope": "UE Engine Program / Engine FRenderTarget with same Rive/RHI/RDG; editor_viewport=0, umg_composite=0",
               "timing_scope": "external spawn-to-complete-PNG including startup/render/readback/encoding/write; 10ms polling",
               "cache_scope": "first lite process uses new Mesa disk cache; later processes reuse it; no OS page-cache flush or cold claim",
               "machine_scope": "WSL2 on shared host; process CPU affinity limit is not a dedicated small VM",
               "build_exclusion": {"path": str(args.build_exclusion.resolve()), "sha256": sha256(args.build_exclusion),
                                   "status": build["status"], "executable": build["executable"],
                                   "recognized_modules": build["recognized_modules"], "forbidden_modules": build["forbidden_modules"]},
               "profiles": []}
    for path in args.report:
        report = json.loads(path.read_text())
        package = report["gates"]["package_measurement"]
        inventory = report["runtime_dependency_inventory"]
        reference = Path(report["gates"]["ue_reference_pixels"]["reference"]["path"])
        comparisons = []
        for run in report["runs"]:
            comparison = compare_images(reference, Path(run["output_png"]))
            comparison["recorded_png_sha256_matches"] = run["png"]["sha256"] == sha256(Path(run["output_png"]))
            if not comparison["recorded_png_sha256_matches"]:
                comparison["status"] = "failed"
            comparisons.append(comparison)
        gates = {name: {"status": value["status"]} for name, value in report["gates"].items()}
        gates["all_repeated_capture_pixels"] = {"status": summarize_status({str(i): value for i, value in enumerate(comparisons)})}
        gates["final_elf_matches_build_exclusion"] = {"status": "passed" if package["executable_sha256"] == build["executable"]["sha256"] else "failed"}
        archive = Path(package["archive"]["path"])
        gates["measured_archive_unchanged"] = {"status": "passed" if sha256(archive) == package["archive"]["sha256"] else "failed"}
        profile = {"name": path.parent.parent.name, "report": str(path.resolve()), "report_sha256": sha256(path),
                   "status": summarize_status(gates), "gate_statuses": {name: value["status"] for name, value in gates.items()},
                   "cpu_profile": report["cpu_execution_profile"],
                   "first_process_png_wall_seconds": report["timing"]["first_run_png_wall_seconds"],
                   "repeat_process_png_wall_seconds": report["timing"]["repeated_run_png_wall_seconds"],
                   "repeat_process_png_wall_median_seconds": report["timing"]["repeated_run_median_seconds"],
                   "peak_rss_kib_per_run": [run["peak_rss_kib"] for run in report["runs"]],
                   "png_wall_seconds_per_run": [run["first_png_wall_seconds"] for run in report["runs"]],
                   "process_wall_seconds_per_run": [run["process_wall_seconds"] for run in report["runs"]],
                   "mesa_cache_after_each_run": [run["mesa_cache_after_run"] for run in report["runs"]],
                   "package": {"file_count": package["file_count"], "raw_file_bytes": package["logical_file_bytes"],
                               "tar_gzip_bytes": package["archive"]["bytes"], "tar_gzip_sha256": package["archive"]["sha256"],
                               "executable_bytes": package["executable_bytes"], "executable_sha256": package["executable_sha256"]},
                   "runtime_dependency_inventory": {"status": inventory["status"], "unresolved": inventory["unresolved"],
                                                    "library_count": len(inventory["libraries"]),
                                                    "external_library_bytes_deduplicated": inventory["external_library_bytes_deduplicated"],
                                                    "package_plus_external_library_bytes": inventory["package_plus_external_library_bytes"],
                                                    "standalone_bundle": inventory["standalone_bundle"]},
                   "cpu_device_names": report["gates"]["cpu_vulkan_enumeration"]["device_names"],
                   "device_exposure": report.get("vulkan_probe_fallback", {}).get("device_exposure"),
                   "package_execution_mutations": report["package_execution_mutations"],
                   "pixel_comparisons_all_runs": comparisons}
        summary["profiles"].append(profile)
    summary["status"] = summarize_status({str(i): value for i, value in enumerate(summary["profiles"])})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"status": summary["status"], "profiles": [row["name"] for row in summary["profiles"]],
                      "output": str(args.output)}, indent=2))
    return {"passed": 0, "failed": 1, "incomplete": 2}[summary["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
