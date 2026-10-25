#!/usr/bin/env python3
"""Download Rive native build dependencies using the Windows network stack.

The Linux build consumes these checkouts through DEPENDENCIES and never needs
network access. Revisions match the locked runtime's dependency Lua scripts.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "vendor/rive-unreal/submodules/rive-runtime"
CACHE = ROOT / "vendor/rive-native-deps"


def fetch(spec: tuple[str, str]) -> dict:
    repo, ref = spec
    destination = CACHE / (repo + "_" + ref).replace("/", "_")
    if not destination.is_dir():
        subprocess.run(["git", "-c", "core.autocrlf=false", "clone", "--depth", "1", "--branch", ref,
                        "https://github.com/" + repo + ".git", str(destination)], check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    head = subprocess.run(["git", "-C", str(destination), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    print(f"Ready {repo} {ref} {head}", flush=True)
    return {"repository": repo, "ref": ref, "commit": head, "directory": str(destination.relative_to(ROOT)).replace("\\", "/")}


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    yoga_ref = (RUNTIME / "dependencies/yoga.ref").read_text().strip()
    specs = [("dabeaz/ply", "3.11"), ("rive-app/harfbuzz", "rive_13.1.1"),
             ("Tehreer/SheenBidi", "v2.6"), ("rive-app/miniaudio", "rive_changes_5"),
             ("rive-app/yoga", yoga_ref), ("rive-app/libjpeg", "v9f"),
             ("glennrp/libpng", "libpng16"), ("madler/zlib", "v1.3.1"),
             ("webmproject/libwebp", "v1.4.0"), ("glfw/glfw", "3.4")]
    results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        jobs = {executor.submit(fetch, spec): spec for spec in specs}
        for job in as_completed(jobs):
            try:
                results.append(job.result())
            except Exception as error:
                raise RuntimeError(f"Dependency failed: {jobs[job]}") from error
    lock = {"scope": "Rive native build dependencies", "dependencies": sorted(results, key=lambda item: item["repository"])}
    (ROOT / "vendor/rive-native-dependency-lock.json").write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
