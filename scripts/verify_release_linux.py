#!/usr/bin/env python3
"""Extract the actual Linux release archives and qualify their rendered pixels."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tarfile

from compare_png import compare_images
from prepare_release import ROOT, sha, sanitize


def execute(command, log):
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('wb') as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=300)
    if result.returncode:
        raise RuntimeError(f'Exit {result.returncode}: {log}')
    text = log.read_text(errors='replace')
    if any(item in text for item in ['Ensure condition failed', 'Fatal error:', 'Assertion failed:',
                                    'LogRiveLiteHost: Error:', 'LogRiveUmgHost: Error:']):
        raise RuntimeError(f'Runtime error: {log}')
    return text


def reference(package, kind, dest, fixture='input.riv', scenario=None):
    png = dest / 'reference.png'
    command = ['bash', str(ROOT/'scripts/measure_no_gpu.sh'), '--', 'env',
        'VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json',
        'VK_DRIVER_FILES=/usr/share/vulkan/icd.d/lvp_icd.json', 'LP_NUM_THREADS=2',
        str(ROOT/'Binaries/Linux/RiveUeReference'), '-vulkan', '-sm5', '-AllowCPUDevices',
        '-RenderOffscreen', '-norhithread', '-unattended', '-stdout', f'-Ui={kind}',
        f'-ProjectDir={ROOT}/', f'-UserDir={dest}/native-user/', f'-Input={package}/fixtures/{fixture}',
        f'-Output={png}', '-Width=512', '-Height=512',
        f'-ShaderArchive={ROOT}/artifacts/umg-optional/shaders-reference/global.bin',
        f'-ShaderDirectory={ROOT}/Shaders', f'-PlaybackMetadata={dest}/reference-playback.json']
    if scenario:
        command.append(f'-Scenario={scenario}')
    text = execute(command, dest/'reference.log')
    assert 'dxg=absent dri=absent' in text and 'llvmpipe' in text and 'RIVE_UE_REFERENCE_CAPTURE' in text
    return png


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-dir', type=Path, required=True)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run as root for private namespaces; UE processes run as uid 1000')
    release = args.release_dir.resolve()
    if not release.is_relative_to(ROOT/'artifacts/release'):
        parser.error('Use an independent prototype release directory')
    state = json.loads((release/'release-status.json').read_text())
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    report = {'source_commit': state['source_commit'], 'status': 'incomplete', 'assets': [],
              'scope': 'Extracted Linux release assets; GPU and development paths hidden; exact RGBA8 comparisons'}
    try:
        for asset in state['assets']:
            if asset['platform'] != 'linux-x86_64':
                continue
            archive = release/'assets'/asset['file']
            assert sha(archive) == asset['sha256']
            extraction = ROOT/'package/release-extracted'/state['tag']/asset['flavor']
            if extraction.exists():
                raise RuntimeError(f'Use a fresh extraction: {extraction}')
            extraction.mkdir(parents=True)
            with tarfile.open(archive) as stream:
                stream.extractall(extraction, filter='data')
            folders = list(extraction.iterdir())
            assert len(folders) == 1
            package = folders[0]
            for name in ['release-manifest.json', 'package-manifest.json']:
                manifest = json.loads((package/name).read_text())
                for item in manifest['files']:
                    path = package/item['path']
                    assert path.stat().st_size == item['bytes'] and sha(path) == item['sha256'], item['path']
            current = {'flavor': asset['flavor'], 'archive_sha256': asset['sha256'], 'cases': []}
            report['assets'].append(current)
            if asset['flavor'] in ['rive', 'umg']:
                dest = release/'validation'/asset['flavor']
                png = dest/'output.png'
                text = execute(['bash', str(ROOT/'scripts/check_portable_linux.sh'), str(package), str(png),
                    f'-Ui={asset["flavor"]}', f'-PlaybackMetadata={dest}/playback.json'], dest/'capture.log')
                assert 'development_engine=hidden development_vendor=hidden' in text and 'dxg=absent dri=absent' in text
                assert 'llvmpipe' in text and 'render_path=UE_RHI_RDG' in text
                comparison = compare_images(png, reference(package, asset['flavor'], dest))
                assert comparison['status'] == 'passed' and comparison['different_pixels'] == 0
                current['cases'].append({'mode': asset['flavor'], 'comparison': comparison, 'png_sha256': sha(png)})
            elif asset['flavor'] == 'verse':
                for mode in ['pressed', 'idle']:
                    dest = release/'validation'/f'verse-{mode}'
                    execute(['bash', str(ROOT/'scripts/check_verse_portable.sh'), str(package), str(dest), '--mode', mode],
                            release/'validation'/f'verse-{mode}.log')
                    run = json.loads((dest/'report.json').read_text())
                    assert run['status'] == 'passed'
                    png = dest/'run/output.png'
                    comparison = compare_images(png, reference(package, 'rive', dest, 'rocket.riv', dest/'run/scenario.json'))
                    assert comparison['status'] == 'passed' and comparison['different_pixels'] == 0
                    assert run['worker']['ui_commands'] == ['true' if mode == 'pressed' else 'false']
                    current['cases'].append({'mode': mode, 'comparison': comparison,
                        'verse_tests': run['worker']['markers'], 'ui_commands': run['worker']['ui_commands'], 'png_sha256': sha(png)})
            elif asset['flavor'] == 'widget-authoring':
                dest = release/'validation/widget-authoring'
                execute(['bash', str(ROOT/'scripts/isolated_widget_worker.sh'), '--', 'python3',
                    str(ROOT/'scripts/verify_widget_worker_package.py'), '--package', str(package),
                    '--animation', 'Intro', '--output-dir', str(dest)], release/'validation/widget-authoring.log')
                run = json.loads((dest/'summary.json').read_text())
                assert run['status'] == 'passed'
                comparison = compare_images(dest/'frame.png', ROOT/'artifacts/umg-animation/acceptance-03/11-frame-2.png')
                assert comparison['status'] == 'passed' and comparison['different_pixels'] == 0
                current['cases'].append({'mode': 'Intro at 0.5 seconds', 'gates': run['gates'], 'comparison': comparison,
                    'reference_scope': 'Frozen same-build native source/compiled-class independent-cooker acceptance suite',
                    'png_sha256': sha(dest/'frame.png')})
            else:
                raise RuntimeError(f'Unqualified release flavor: {asset["flavor"]}')
            current['status'] = 'passed'
            print(json.dumps({'flavor': asset['flavor'], 'status': 'passed'}), flush=True)
        assert report['assets']
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
    (release/'linux-validation.json').write_text(json.dumps(sanitize(report), indent=2)+'\n')
    print(json.dumps({'status': report['status'], 'error': report.get('error')}))
    return int(report['status'] != 'passed')


if __name__ == '__main__':
    raise SystemExit(main())
