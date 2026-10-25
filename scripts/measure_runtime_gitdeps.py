#!/usr/bin/env python3
"""Read-only cost/hash audit of broad Runtime GitDependencies coverage."""
from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

EXCLUDED = {value.lower() for value in ("Win32", "Win64", "Mac", "Android", "IOS", "TVOS", "LinuxArm64", "HoloLens")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--paths-output", type=Path, help="write exact selected paths relative to Engine/Source for targeted cache copies")
    args = parser.parse_args()
    root = ET.parse(args.engine_root / "Engine/Build/Commit.gitdeps.xml").getroot()
    blobs = {node.attrib["Hash"]: node.attrib for node in root.find("Blobs")}
    packs = {node.attrib["Hash"]: node.attrib for node in root.find("Packs")}
    entries, excluded, grouped, needed_packs = [], [], defaultdict(lambda: {"files": 0, "declared_bytes": 0, "needed_files": 0, "needed_bytes": 0}), set()
    for node in root.find("Files"):
        name, expected = node.attrib["Name"], node.attrib["Hash"]
        if not name.startswith("Engine/Source/Runtime/"):
            continue
        blob = blobs[expected]
        record = {"path": name, "expected_sha1": expected, "declared_bytes": int(blob["Size"])}
        if any(part.lower() in EXCLUDED for part in Path(name).parts):
            excluded.append(record)
            continue
        local = args.engine_root / name
        if local.is_file():
            digest = hashlib.sha1()
            with local.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            record.update(actual_bytes=local.stat().st_size, actual_sha1=digest.hexdigest())
            record["status"] = "matched" if record["actual_sha1"] == expected else "mismatch"
        else:
            record["status"] = "missing"
        component = name[len("Engine/Source/Runtime/"):].split("/", 1)[0]
        group = grouped[component]
        group["files"] += 1
        group["declared_bytes"] += record["declared_bytes"]
        if record["status"] != "matched":
            group["needed_files"] += 1
            group["needed_bytes"] += record["declared_bytes"]
            if "PackHash" in blob:
                needed_packs.add(blob["PackHash"])
        entries.append(record)
    pack_records = [packs[value] for value in sorted(needed_packs)]
    compressed = sum(int(item.get("CompressedSize", item.get("Size", "0"))) for item in pack_records)
    report = {"scope": "read-only estimate; no GitDependencies execution or allowlist changes",
              "filter": "all Engine/Source/Runtime paths minus the same eight exact platform directory segments; platform-specific filenames can still remain",
              "selected_files": len(entries), "selected_file_bytes": sum(item["declared_bytes"] for item in entries),
              "needed_files": sum(item["status"] != "matched" for item in entries),
              "needed_uncompressed_file_bytes": sum(item["declared_bytes"] for item in entries if item["status"] != "matched"),
              "excluded_files": len(excluded), "component_totals": dict(sorted(grouped.items())),
              "uncached_needed_pack_download_upper_bound_bytes": compressed,
              "download_estimate_limit": "whole unique missing-file packs, without subtracting already cached packs; actual network can be smaller. Blob bytes are final file bytes, not compressed download bytes.",
              "needed_packs": pack_records, "files": entries,
              "needed_files_over_500mb": [item for item in entries if item["status"] != "matched" and item["declared_bytes"] > 500_000_000]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.paths_output:
        args.paths_output.parent.mkdir(parents=True, exist_ok=True)
        args.paths_output.write_text("".join(item["path"][len("Engine/Source/"):] + "\n" for item in entries), encoding="utf-8", newline="\n")
        report["cache_sync_paths"] = str(args.paths_output)
        report["cache_sync_paths_base"] = "Engine/Source"
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in ("files", "needed_packs")}, indent=2))


if __name__ == "__main__":
    main()
