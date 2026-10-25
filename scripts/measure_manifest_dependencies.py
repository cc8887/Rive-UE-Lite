#!/usr/bin/env python3
"""Audit exact GitDependencies files, declared sizes and actual content hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

REFERENCE_FILES = [
    "Engine/Source/Runtime/BinkAudioDecoder/SDK/BinkAudio/Lib/libbinka_ue_decode_lnx64_static.a",
    "Engine/Source/Runtime/RadAudioCodec/SDK/Lib/libradaudio_decoder_linux64.a",
    "Engine/Content/Renderer/TessellationTable.bin",
    "Engine/Source/ThirdParty/Ogg/libogg-1.2.2/lib/Unix/x86_64-unknown-linux-gnu/libogg.a",
    "Engine/Source/ThirdParty/libOpus/opus-1.1/Unix/x86_64-unknown-linux-gnu/libopus.a",
    "Engine/Source/ThirdParty/libOpus/opus-1.1/Unix/x86_64-unknown-linux-gnu/libresampler.a",
    "Engine/Source/ThirdParty/Vorbis/libvorbis-1.3.2/lib/Unix/x86_64-unknown-linux-gnu/libvorbis.a",
    "Engine/Source/ThirdParty/Vorbis/libvorbis-1.3.2/lib/Unix/x86_64-unknown-linux-gnu/libvorbisfile.a",
    "Engine/Source/ThirdParty/Vorbis/libvorbis-1.3.2/lib/Unix/x86_64-unknown-linux-gnu/libvorbisenc.a",
]


def file_hash(path, algorithm):
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-root", type=Path, required=True, help="checkout root containing Engine/")
    parser.add_argument("--path", action="append", default=[])
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = args.engine_root / "Engine/Build/Commit.gitdeps.xml"
    document = ET.parse(manifest).getroot()
    files = {node.attrib["Name"]: node.attrib for node in document.find("Files")}
    blobs = {node.attrib["Hash"]: node.attrib for node in document.find("Blobs")}
    entries = []
    for name in dict.fromkeys(args.path + (REFERENCE_FILES if args.reference else [])):
        record = {"path": name, "status": "incomplete"}
        metadata = files.get(name)
        if not metadata:
            record["reason"] = "not declared by current GitDependencies manifest"
        else:
            expected = metadata["Hash"]
            record.update(expected_sha1=expected, declared_bytes=int(blobs.get(expected, {}).get("Size", "0")))
            local = args.engine_root / name
            if local.is_file():
                record.update(actual_bytes=local.stat().st_size, actual_sha1=file_hash(local, "sha1"))
                record["status"] = "passed" if record["actual_sha1"] == expected else "failed"
            else:
                record["reason"] = "file missing"
        entries.append(record)
    report = {"scope": "exact dependency size/hash audit; not build or rendering acceptance",
              "manifest_sha256": file_hash(manifest, "sha256"), "files": entries,
              "declared_total_bytes": sum(entry.get("declared_bytes", 0) for entry in entries),
              "new_files_over_500mb": [entry for entry in entries if entry["status"] != "passed" and entry.get("declared_bytes", 0) > 500_000_000]}
    report["status"] = "passed" if entries and all(entry["status"] == "passed" for entry in entries) else "incomplete"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
