#!/usr/bin/env python3
"""Check reference host/adapter from generated UBT arguments without building.

Requires a successful -SkipBuild pass including real Engine UHT generation.
All object/dependency/PCH output options are removed; existing UBT outputs and
active builds are never written. This does not establish a link/runtime gate.
"""
from pathlib import Path
import os
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
target = root / "Intermediate/Build/Linux/x64/RiveUeReference/Development"
destination = root / "Source/RiveUeReference/syntax-check"
destination.mkdir(exist_ok=True)
cache_root = Path(os.environ.get("RIVE_LITE_CACHE_ROOT", Path.home() / ".cache/rive-ue-lite"))
toolchain = Path(os.environ.get(
    "UE_LINUX_CLANG",
    cache_root / "native/engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu/bin/clang++",
))
failed = False
for name in sys.argv[1:] or ["Main", "RenderContextRHIImpl", "RivePassFunctions", "TextureRHIImpl"]:
    module = "RiveUeReference" if name == "Main" else "RiveUeReferenceRenderer"
    folder = target / module
    shared = (folder / (module + ".Shared.rsp")).read_text()
    shared = "\n".join(line for line in shared.splitlines() if line != "-c")
    shared_path = destination / (module + ".Shared.syntax.rsp")
    shared_path.write_text(shared + "\n")
    source = (folder / (name + ".cpp.o.rsp")).read_text()
    lines = [line for line in source.splitlines() if not line.startswith(("-MD", "-o ", "-include-pch "))]
    source = re.sub(r'^@"[^\"]+"', '@"' + str(shared_path) + '"', "\n".join(lines))
    source += "\n-fsyntax-only\n-fno-color-diagnostics\n"
    response = destination / (name + ".rsp")
    response.write_text(source)
    result = subprocess.run([str(toolchain), "@" + str(response)], cwd=root / "engine/Engine/Source", capture_output=True, text=True)
    (destination / (name + ".log")).write_text(result.stdout + result.stderr)
    print(f"{name}: exit={result.returncode}", flush=True)
    if result.returncode:
        failed = True
        print(result.stderr, flush=True)
raise SystemExit(1 if failed else 0)
