#!/usr/bin/env python3
"""Syntax-check the real cooker TU with copied UBT flags, without object writes."""
from pathlib import Path
import os
import re
import subprocess

root = Path(__file__).resolve().parents[2]
output = root / "artifacts/setup/canonical-syntax"
output.mkdir(parents=True, exist_ok=True)
module = root / "Intermediate/Build/Linux/x64/RiveUeShaderCooker/Development/RiveUeShaderCooker"
shared = (module / "RiveUeShaderCooker.Shared.rsp").read_text()
shared = "\n".join(line for line in shared.splitlines() if line != "-c")
(output / "Shared.rsp").write_text(shared + "\n")
text = (module / "Main.cpp.o.rsp").read_text()
text = "\n".join(line for line in text.splitlines() if not line.startswith(("-MD", "-o ", "-include-pch ")))
text = re.sub(r'^@"[^\"]+"', '@"' + str(output / "Shared.rsp") + '"', text)
text += "\n-fsyntax-only\n-fno-color-diagnostics\n"
(output / "Check.rsp").write_text(text)
cache_root = Path(os.environ.get("RIVE_LITE_CACHE_ROOT", Path.home() / ".cache/rive-ue-lite"))
compiler = os.environ.get(
    "UE_LINUX_CLANG",
    str(cache_root / "native/engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu/bin/clang++"),
)
result = subprocess.run([compiler, "@" + str(output / "Check.rsp")], cwd=root / "engine/Engine/Source", capture_output=True, text=True)
(output / "check.log").write_text(result.stdout + result.stderr)
print(result.stdout + result.stderr)
raise SystemExit(result.returncode)
