#!/usr/bin/env python3
"""Run one adapter syntax check using existing UBT response files, without UBT.

Outputs/dependency files from the response are removed, so this cannot overwrite
objects that the active UBT build owns. Use only after UBT generated the module's
response files. This is diagnostic evidence, not a successful build/link gate.
"""
from pathlib import Path
import os
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
source_rsp = root / "Intermediate/Build/Linux/x64/RiveLiteShaderCompiler/Development/RiveLiteRenderer"
destination = root / "Source/RiveLiteRenderer/syntax-check"
destination.mkdir(exist_ok=True)
shared = (source_rsp / "RiveLiteRenderer.Shared.rsp").read_text()
shared = "\n".join(line for line in shared.splitlines() if line != "-c")
shared_response = destination / "Shared.syntax.rsp"
shared_response.write_text(shared + "\n")
cache_root = Path(os.environ.get("RIVE_LITE_CACHE_ROOT", Path.home() / ".cache/rive-ue-lite"))
toolchain = Path(os.environ.get(
    "UE_LINUX_CLANG",
    cache_root / "native/engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu/bin/clang++",
))
failed = False
for name in sys.argv[1:] or ["RiveShaderTypes", "RenderContextRHIImpl", "RivePassFunctions", "TextureRHIImpl"]:
    text = (source_rsp / (name + ".cpp.o.rsp")).read_text()
    lines = [line for line in text.splitlines() if not line.startswith(("-MD", "-o "))]
    text = "\n".join(lines).replace("-std=c++20", "-std=c++23")
    text = re.sub(r'^@"[^\"]+"', '@"' + str(shared_response) + '"', text)
    text += f'\n-I"{root / "engine/Engine/Shaders/Shared"}"\n-fsyntax-only\n-fno-color-diagnostics\n'
    response = destination / (name + ".rsp")
    response.write_text(text)
    result = subprocess.run([str(toolchain), "@" + str(response)], cwd=root / "engine/Engine/Source", capture_output=True, text=True)
    (destination / (name + ".log")).write_text(result.stdout + result.stderr)
    print(f"{name}: exit={result.returncode}", flush=True)
    if result.returncode:
        failed = True
        print(result.stderr, flush=True)
raise SystemExit(1 if failed else 0)
