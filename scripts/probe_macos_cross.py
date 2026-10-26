#!/usr/bin/env python3
"""Attempt real UBT and a Rive source cross compile on Linux; record failures too."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", choices=["arm64", "x64"], default="arm64")
    parser.add_argument("--sdk", type=Path, help="Optional existing Mac SDK; never downloaded implicitly")
    parser.add_argument("--zig", type=Path, help="Optional existing Zig compiler, including Windows zig.exe through WSL interop")
    parser.add_argument("--target", choices=['RiveLiteRhiProbe', 'RiveRhiLite'], default='RiveLiteRhiProbe')
    parser.add_argument("--output-dir", type=Path, help="Fresh evidence directory under this prototype")
    args = parser.parse_args()
    if platform.system() != "Linux":
        parser.error("Run inside WSL/Linux")
    output = args.output_dir.resolve() if args.output_dir else ROOT / "artifacts/macos" / ("cross-" + args.arch)
    if not output.resolve().is_relative_to(ROOT): parser.error('Keep evidence inside this prototype')
    if args.output_dir and output.exists(): parser.error('Use a fresh output directory')
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(DOTNET_ROOT=str(ROOT/'engine/Engine/Binaries/ThirdParty/DotNet/10.0/linux-x64'),
               DOTNET_CLI_HOME=str(ROOT/'build/dotnet-home'), DOTNET_CLI_TELEMETRY_OPTOUT='1')
    results = {}
    def run(name, command, extra_env=None):
        start = time.monotonic()
        try:
            result = subprocess.run(list(map(str, command)), cwd=ROOT, env={**env, **(extra_env or {})},
                                    capture_output=True, text=True, timeout=180)
            code, log = result.returncode, result.stdout+result.stderr
        except (OSError, subprocess.TimeoutExpired) as error:
            code, log = -1, str(error)
        (output/(name+'.log')).write_text(log)
        results[name] = {'command': list(map(str, command)), 'exit_code': code,
                         'elapsed_seconds': time.monotonic()-start, 'log': str(output/(name+'.log'))}
        print(name, 'exit_code='+str(code), '\n'+log[-3000:], flush=True)
    run('ubt', [Path(env['DOTNET_ROOT'])/'dotnet', ROOT/'engine/Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.dll',
                args.target, 'Mac', 'Development', '-architecture='+args.arch,
                '-Project='+str(ROOT/'RiveRhiLite.uproject'), '-NoUBA', '-NoUbaLocal',
                '-Log='+str(output/'ubt-detail.log')])
    allowed = re.search(r'under (/home/[^ /]+/\.cache/rive-ue-lite-20261024) only', (ROOT/'AGENTS.md').read_text())
    cache = Path(allowed.group(1))/'native/engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu' if allowed else ROOT/'dependencies/missing-native-cache'
    candidates = [ROOT/'engine/Engine/Extras/ThirdPartyNotUE/SDKs/HostLinux/Linux_x64/v26_clang-20.1.8-rockylinux8/x86_64-unknown-linux-gnu/bin/clang++', cache/'bin/clang++']
    compiler = next((p for p in candidates if p.is_file()), Path(shutil.which('clang++') or '/missing/clang++'))
    runtime = ROOT/'vendor/rive-unreal/submodules/rive-runtime'
    triple = ('arm64' if args.arch == 'arm64' else 'x86_64')+'-apple-macos15.0'
    # Prove what the LLVM backend can actually emit, separately from a complete
    # UE/Metal application. No SDK-free object is labelled a runnable package.
    smoke = output/'backend.cpp'
    smoke.write_text('extern "C" int cross_backend_probe(int value) { return value + 1; }\n')
    run('compiler-backend', [compiler, '-target', triple, '-ffreestanding', '-c', smoke, '-o', output/'backend.o'])
    run('object-format', ['file', output/'backend.o'])
    command = [compiler, '-target', triple, '-std=c++20', '-c', runtime/'src/math/aabb.cpp',
               '-I'+str(runtime/'include'), '-o', output/'rive-aabb.o']
    if args.sdk:
        command += ['-isysroot', args.sdk.resolve()]
    run('rive-source', command)
    if args.zig:
        zig = args.zig.resolve()
        def zig_path(path):
            return subprocess.check_output(['wslpath', '-w', str(path)], text=True).strip() if zig.suffix.lower() == '.exe' else str(path)
        for folder in ['zig-global-cache', 'zig-local-cache', 'tmp']:
            (output/folder).mkdir()
        zig_env = {'ZIG_GLOBAL_CACHE_DIR': zig_path(output/'zig-global-cache'),
                   'ZIG_LOCAL_CACHE_DIR': zig_path(output/'zig-local-cache'),
                   'TEMP': zig_path(output/'tmp'), 'TMP': zig_path(output/'tmp')}
        zig_target = ('aarch64' if args.arch == 'arm64' else 'x86_64')+'-macos.15.0'
        run('zig-version', [zig, 'version'], zig_env)
        run('zig-rive-source', [zig, 'c++', '-target', zig_target, '-std=c++20', '-c',
            zig_path(runtime/'src/math/aabb.cpp'), '-I'+zig_path(runtime/'include'),
            '-o', zig_path(output/'zig-rive-aabb.o')], zig_env)
        run('zig-rive-object-format', ['file', output/'zig-rive-aabb.o'])
        metal_probe = output/'metal-sdk.cpp'
        metal_probe.write_text('#include <Metal/Metal.h>\n')
        run('zig-metal-sdk', [zig, 'c++', '-target', zig_target, '-x', 'objective-c++', '-c',
            zig_path(metal_probe), '-o', zig_path(output/'metal-sdk.o')], zig_env)
    # Even successful object generation is not a linked or runnable UE program.
    report = {'host': platform.platform(), 'target': 'Mac', 'architecture': args.arch,
              'results': results, 'mac_runtime_validated': False,
              'status': 'compile_steps_passed_runtime_unverified' if all(r['exit_code'] == 0 for r in results.values()) else 'blocked',
              'ue_target': args.target, 'sdk_supplied': bool(args.sdk), 'metal_screenshot': None,
              'compiler_backend_object_generated': (output/'backend.o').is_file(),
              'zig_rive_object_generated': (output/'zig-rive-aabb.o').is_file(),
              'full_ue_program_linked': results['ubt']['exit_code'] == 0 and (ROOT/'Binaries/Mac'/args.target).is_file(),
              'sdk_candidates': [str(path) for root in [ROOT/'dependencies', Path('/opt/osxcross/target/SDK'), Path('/usr/local/osxcross/target/SDK'), Path('/opt/SDKs'), Path('/Applications')]
                  if root.is_dir() for path in root.glob('MacOSX*.sdk')],
              'limitation': 'Portable non-SDK-dependent objects are separate from a complete UE Metal executable and Metal shader cook.'}
    (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    return 0 if report['status'].startswith('compile_steps_passed') else 2


if __name__ == '__main__':
    raise SystemExit(main())
