#!/usr/bin/env python3
"""Stage exact centrally pinned NuGet packages via Windows networking.

This writes only the isolated feed and an explicit JSON report. It does not
modify csproj/props, user NuGet caches, package version pins, or engine source.
NuGet remains responsible for actual dependency resolution on Linux.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def tag(element):
    return element.tag.rsplit("}", 1)[-1]


def central_versions(path: Path) -> dict:
    root = ET.parse(path).getroot()
    properties = {tag(element): element.text or "" for group in root if tag(group) == "PropertyGroup" for element in group}

    def expand(value):
        for _ in range(20):
            expanded = re.sub(r"\$\(([^)]+)\)", lambda match: properties.get(match.group(1), match.group(0)), value)
            if expanded == value:
                return value
            value = expanded
        raise ValueError("property expansion cycle")

    result = {}
    for element in root.iter():
        if tag(element) == "PackageVersion" and "Include" in element.attrib:
            name, value = element.attrib["Include"], expand(element.attrib["Version"])
            if "$(" in value:
                raise ValueError(f"unresolved package version: {name}={value}")
            result[name.lower()] = {"id": name, "version": value}
    return result


def project_packages(project: Path) -> tuple[set[str], list[str]]:
    pending, visited, packages = [project.resolve()], set(), set()
    while pending:
        path = pending.pop()
        if path in visited or not path.is_file():
            continue
        visited.add(path)
        root = ET.parse(path).getroot()
        for element in root.iter():
            kind = tag(element)
            if kind == "PackageReference" and element.attrib.get("Include"):
                packages.add(element.attrib["Include"].lower())
            if kind in ("ProjectReference", "Import"):
                value = element.attrib.get("Include") if kind == "ProjectReference" else element.attrib.get("Project")
                if value and "$(" not in value:
                    imported = path.parent / value.replace("\\", "/")
                    if imported.suffix in (".props", ".targets", ".csproj"):
                        pending.append(imported.resolve())
        # MSBuild loads the nearest Directory.Build.props. Dynamic ancestor imports
        # in that file are left to MSBuild; StyleCop is directly pinned in UBT too.
        for parent in path.parents:
            candidate = parent / "Directory.Build.props"
            if candidate.is_file():
                pending.append(candidate)
                break
    return packages, sorted(str(path) for path in visited)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stage(package: dict, feed: Path, download: bool) -> dict:
    name, version = package["id"], package["version"]
    filename = f"{name.lower()}.{version.lower()}.nupkg"
    destination = feed / filename
    report = dict(package, path=str(destination), status="present" if destination.exists() else "missing")
    if not destination.exists() and download:
        temporary = feed / (filename + ".partial")
        url = f"https://globalcdn.nuget.org/packages/{filename}"
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            report.update(status="failed", reason="curl executable unavailable")
            return report
        command = [curl, "--silent", "--show-error", "--fail", "--location", "--retry", "2", "--connect-timeout", "15", "--max-time", "180", "--output", str(temporary), url]
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        report.update(source_url=url, download_exit_code=result.returncode, download_output=result.stdout)
        if result.returncode:
            temporary.unlink(missing_ok=True)
            report["status"] = "failed"
            return report
        try:
            with zipfile.ZipFile(temporary) as archive:
                if not any(path.endswith(".nuspec") for path in archive.namelist()):
                    raise ValueError("downloaded archive has no nuspec")
                bad = archive.testzip()
                if bad:
                    raise ValueError(f"archive CRC error: {bad}")
            temporary.replace(destination)
            report["status"] = "downloaded"
        except (OSError, ValueError, zipfile.BadZipFile) as error:
            temporary.unlink(missing_ok=True)
            report.update(status="failed", reason=str(error))
            return report
    if destination.exists():
        report.update(bytes=destination.stat().st_size, sha256=sha256(destination))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--central", type=Path, required=True)
    parser.add_argument("--feed", type=Path, required=True)
    parser.add_argument("--project", type=Path)
    parser.add_argument("--from-log", type=Path, action="append", default=[])
    parser.add_argument("--package", action="append", default=[], help="ID or ID@exact-version; exact explicit versions for transitive restore errors")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()
    versions = central_versions(args.central)
    names, projects = project_packages(args.project) if args.project else (set(), [])
    explicit = {}
    for text in args.package:
        if "@" in text:
            name, value = text.split("@", 1)
            if name.lower() in versions and versions[name.lower()]["version"].lower() != value.lower():
                parser.error(f"explicit version would override central pin: {name}@{value}")
            explicit[name.lower()] = {"id": name, "version": value}
        else:
            names.add(text.lower())
    for path in args.from_log:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        names.update(name.lower().rstrip(".") for name in re.findall(r"Unable to find package ([A-Za-z0-9_.-]+)", text))
        for name, value in re.findall(r"Unable to find package ([A-Za-z0-9_.-]+) with version \(>= ([^ )]+)\)", text):
            if name.lower() not in versions:
                explicit[name.lower()] = {"id": name, "version": value,
                                           "version_source": "NuGet restore's required transitive dependency lower bound"}
    missing_pins = sorted(name for name in names if name not in versions and name not in explicit)
    packages = {name: versions[name] for name in names if name in versions}
    packages.update(explicit)
    args.feed.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(lambda package: stage(package, args.feed, args.download), packages.values()))
    report = {"central_manifest": str(args.central.resolve()), "central_manifest_sha256": sha256(args.central),
              "projects_scanned": projects, "scope": "direct package references and explicit restore-error requests; NuGet performs transitive resolution",
              "unpinned_requests": missing_pins, "packages": sorted(results, key=lambda value: value["id"].lower())}
    report["status"] = "passed" if not missing_pins and all(value["status"] in ("present", "downloaded") for value in results) else "incomplete"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "requested": len(results), "downloaded": sum(value["status"] == "downloaded" for value in results),
                      "missing": [{"id": value["id"], "version": value["version"], "status": value["status"]} for value in results if value["status"] in ("missing", "failed")],
                      "unpinned_requests": missing_pins, "report": str(args.report)}, indent=2))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    sys.exit(main())
