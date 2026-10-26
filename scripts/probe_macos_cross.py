#!/usr/bin/env python3
"""Attempt real UBT and a Rive source cross compile on Linux; record failures too."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=["arm64", "x64"], default="arm64")
    parser.add_argument("--sdk", type=Path, help="Optional existing Mac SDK; never downloaded implicitly")
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("Run inside WSL/Linux")
    output = ROOT / "artifacts/macos" / ("cross-" + args.arch)
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(DOTNET_ROOT=str(ROOT/'engine/Engine/Binaries/ThirdParty/DotNet/10.0/linux-x64'),
               DOTNET_CLI_HOME=str(ROOT/'build/dotnet-home'), DOTNET_CLI_TELEMETRY_OPTOUT='1')
    results = {}
    def run(name, command):
        start = time.monotonic()
        try:
            result = subprocess.run(list(map(str, command)), cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=180)
            code, log = result.returncode, result.stdout+result.stderr
        except (OSError, subprocess.TimeoutExpired) as error:
            code, log = -1, str(error)
        (output/(name+'.log')).write_text(log)
        results[name] = {'command': list(map(str, command)), 'exit_code': code,
                         'elapsed_seconds': time.monotonic()-start, 'log': str(output/(name+'.log'))}
        print(name, 'exit_code='+str(code), '\n'+log[-3000:], flush=True)
    run('ubt', [Path(env['DOTNET_ROOT'])/'dotnet', ROOT/'engine/Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll',
                'RiveLiteRhiProbe', 'Mac', 'Development', '-architecture='+args.arch,
                '-Project='+str(ROOT/'RiveRhiLite.uproject'), '-NoUBA', '-NoUbaLocal',
                '-Log='+str(output/'ubt-detail.log')])
    cache = Path('/home/yuchencui/.cache/rive-ue-lite-20261024/native/engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu')
    candidates = [ROOT/'engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu/bin/clang++', cache/'bin/clang++']
    compiler = next((p for p in candidates if p.is_file()), Path(shutil.which('clang++') or '/missing/clang++'))
    runtime = ROOT/'vendor/rive-unreal/submodules/rive-runtime'
    triple = ('arm64' if args.arch == 'arm64' else 'x86_64')+'-apple-macos15.0'
    command = [compiler, '-target', triple, '-std=c++20', '-c', runtime/'src/math/aabb.cpp',
               '-I'+str(runtime/'include'), '-o', output/'rive-aabb.o']
    if args.sdk:
        command += ['-isysroot', args.sdk.resolve()]
    run('rive-source', command)
    # Even successful object generation is not a linked or runnable UE program.
    report = {'host': platform.platform(), 'target': 'Mac', 'architecture': args.arch,
              'results': results, 'mac_runtime_validated': False,
              'status': 'compile_steps_passed_runtime_unverified' if all(r['exit_code'] == 0 for r in results.values()) else 'blocked',
              'sdk_supplied': bool(args.sdk), 'metal_screenshot': None}
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return 0 if report['status'].startswith('compile_steps_passed') else 2


if __name__ == '__main__':
    raise SystemExit(main())
