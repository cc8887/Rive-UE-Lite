"""Header syntax check with genuine generated UE flags; no shared object writes."""
from pathlib import Path
import os
import re
import subprocess

root = Path(__file__).resolve().parents[2]
out = root / 'artifacts/playback/syntax'
out.mkdir(parents=True, exist_ok=True)
module = root / 'Intermediate/Build/Linux/x64/RiveRhiLite/Development/RiveRhiLite'
shared = (module / 'RiveRhiLite.Shared.rsp').read_text()
shared = '\n'.join(line for line in shared.splitlines() if line != '-c')
(out / 'Shared.rsp').write_text(shared + '\n')
(out / 'Check.cpp').write_text('#include "RivePlayback.h"\n')
text = (module / 'Main.cpp.o.rsp').read_text()
lines = [line for line in text.splitlines() if not line.startswith(('-MD', '-o ', '-include-pch '))]
text = '\n'.join(lines)
text = re.sub(r'^@"[^\"]+"', '@"' + str(out / 'Shared.rsp') + '"', text)
text = text.replace(str(root / 'Source/RiveRhiLite/Private/Main.cpp'), str(out / 'Check.cpp'))
text += f'\n-I"{root / "Source/RivePlayback/Public"}"\n-I"{root / "engine/Engine/Source/Runtime/Json/Public"}"\n-fsyntax-only\n-fno-color-diagnostics\n'
(out / 'Check.rsp').write_text(text)
cache_root = Path(os.environ.get('RIVE_LITE_CACHE_ROOT', Path.home() / '.cache/rive-ue-lite'))
compiler = os.environ.get(
    'UE_LINUX_CLANG',
    str(cache_root / 'native/engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu/bin/clang++'),
)
result = subprocess.run([compiler, '@' + str(out / 'Check.rsp')], cwd=root / 'engine/Engine/Source', capture_output=True, text=True)
(out / 'check.log').write_text(result.stdout + result.stderr)
print(result.stdout + result.stderr)
raise SystemExit(result.returncode)
