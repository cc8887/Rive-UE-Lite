#!/usr/bin/env python3
"""Record completed isolated UBT dependency/bootstrap provenance."""
from __future__ import annotations

import datetime
import hashlib
import json
import subprocess
from pathlib import Path


def fingerprint(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha.hexdigest()}


def main():
    root = Path(__file__).resolve().parents[1]
    setup = root / "artifacts/setup"
    engine = root / "engine"
    reports = sorted(setup.glob("ubt-build-local-packages-*.log"))
    packages = {}
    for path in reports:
        for item in json.loads(path.read_text(encoding="utf-8"))["packages"]:
            if item["status"] == "downloaded":
                packages[f"{item['id'].lower()}@{item['version']}"] = item
    build_log = setup / "ubt-build-local-07.log"
    build_text = build_log.read_text(encoding="utf-8")
    output = engine / "Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll"
    source = engine / "Engine/Source/Programs/UnrealBuildTool/bin/Development/net10.0/UnrealBuildTool.dll"
    feed_packages = list((root / "dependencies/nuget-feed").glob("*.nupkg"))
    result = {"timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "scope": "build tool bootstrap and dependency provenance only; not deployable application package, Rive rendering, or renderer performance",
              "engine_commit": subprocess.check_output(["git", "-C", str(engine), "rev-parse", "HEAD"], text=True).strip(),
              "central_manifest": fingerprint(engine / "Directory.Packages.props"),
              "gitdependencies_manifest": fingerprint(engine / "Engine/Build/Commit.gitdeps.xml"),
              "isolation": {"feed": str(root / "dependencies/nuget-feed"), "packages_cache": str(root / "dependencies/nuget"),
                            "dotnet_cli_home": str(root / "build/dotnet-home"), "user_cache_modified": False},
              "restore_options": {"NuGetAudit": False, "NUGET_CERT_REVOCATION_MODE": "offline",
                                  "package_signature_verification_disabled": False, "sources": [str(root / "dependencies/nuget-feed")]},
              "downloaded_exact_packages": sorted(packages.values(), key=lambda item: item["id"].lower()),
              "downloaded_exact_package_count": len(packages),
              "local_feed_nupkg_count": len(feed_packages), "local_feed_nupkg_bytes": sum(path.stat().st_size for path in feed_packages),
              "ubt_build": {"configuration": "Development", "framework": "net10.0", "log": fingerprint(build_log),
                            "succeeded": "Build succeeded." in build_text and "0 Warning(s)" in build_text and "0 Error(s)" in build_text},
              "published_ubt": fingerprint(output), "build_output_ubt": fingerprint(source)}
    result["published_matches_build_output"] = result["published_ubt"]["sha256"] == result["build_output_ubt"]["sha256"]
    destination = setup / "ubt-build-local-provenance.log"
    destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(destination), "build_succeeded": result["ubt_build"]["succeeded"],
                      "published_matches_build_output": result["published_matches_build_output"],
                      "downloaded_exact_package_count": len(packages)}))


if __name__ == "__main__":
    main()
