#!/usr/bin/env python3
"""Build pinned Rive libraries in a Mac-only staging tree, preserving Linux inputs."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

from check_macos_archives import validate

ROOT = Path(__file__).resolve().parents[1]
PIN = '47d1cd54ccefd468db7cb26ecc4699ae1723dd85'


def main():
    if platform.system() != 'Darwin':
        raise SystemExit('Native Rive Mac build requires Xcode on macOS; use probe_macos_cross.py on WSL.')
    subprocess.run(['xcrun', '--sdk', 'macosx', '--find', 'clang++'], check=True)
    source = ROOT/'vendor/rive-unreal/submodules/rive-runtime'
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != PIN:
        raise SystemExit('Unexpected Rive revision; refusing an ABI mismatch')
    work = ROOT/'build/macos'
    runtime = work/'rive-runtime'
    work.mkdir(parents=True, exist_ok=True)
    if not runtime.exists():
        archive = subprocess.check_output(['git', '-C', str(source), 'archive', 'HEAD'])
        runtime.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(runtime, filter='data')
        (runtime/'.rive-prototype-pin').write_text(PIN)
    elif not (runtime/'.rive-prototype-pin').is_file() or (runtime/'.rive-prototype-pin').read_text() != PIN:
        raise SystemExit('Unrecognized Mac native staging tree; preserve and inspect it before rebuilding')
    # A separate upstream driver also isolates its copy_includes/shader outputs.
    driver = work/'native-driver/Scripts/build-rive'
    shutil.copytree(ROOT/'vendor/rive-unreal/Scripts/build-rive', driver, dirs_exist_ok=True)
    script = driver/'build-rive.py'
    text = script.read_text(encoding='utf-8')
    old = 'if not do_mac(rive_runtime_path, True) or not do_mac(rive_runtime_path, False):\n                return'
    if text.count(old) != 1:
        raise SystemExit('Upstream Mac failure-propagation anchor changed')
    script.write_text(text.replace(old, old.replace('return', 'raise SystemExit("Rive Mac native build failed")')), encoding='utf-8')
    for path in driver.glob('*.sh'):
        path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
    env = os.environ.copy()
    env.update(RIVE_UNREAL_ENGINE=str(ROOT/'engine'), DEPENDENCIES=str(ROOT/'vendor/rive-native-deps'))
    subprocess.run([sys.executable, str(script), '--rive_runtime_path', str(runtime),
                    '--disable_scripting', '--release_only', '--disable_lto', '--raw_shaders', 'Mac'],
                   cwd=driver, env=env, check=True)
    native = work/'native-driver/Source/ThirdParty/RiveLibrary'
    results = [validate(native/'Libraries/Mac'/name, arch) for name, arch in [('Mac', 'arm64'), ('Intel', 'x64')]]
    # Generated UE shader strings must remain identical; no platform silently
    # regenerates or overwrites the already validated tracked RHI/RDG shaders.
    for arch in ['arm64', 'x64']:
        generated = runtime/f'out/mac/{arch}/release/include/generated/shaders'
        if not (generated/'rhi.glsl.exports.h').is_file():
            raise SystemExit('Missing generated RHI shader exports: '+str(generated))
        for file in generated.iterdir():
            if file.is_file() and 'minified' in file.name:
                name = file.stem+'.ush' if file.suffix == '.glsl' else file.name+'.ush'
                expected = ROOT/'Shaders/Private/Rive/Generated'/name
                if not expected.is_file() or expected.read_bytes() != file.read_bytes():
                    raise SystemExit('Generated shader differs from tracked UE adapter: '+str(file))
    report = {'runtime_commit': PIN, 'archives': results, 'generated_shader_strings_match': True,
              'headers': str(native/'Includes'), 'driver_sha256': hashlib.sha256(script.read_bytes()).hexdigest(),
              'metal_runtime_validated': False}
    output = ROOT/'artifacts/macos/native-build.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
