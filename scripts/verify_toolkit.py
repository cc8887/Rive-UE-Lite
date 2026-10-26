#!/usr/bin/env python3
"""Exercise the public combined CLI against real native workers, then compare UE references."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time
import zipfile

from compare_png import compare_images, sha256

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolkit', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--references', action='store_true', help='Run after isolated CLI acceptance, with development reference binaries visible')
    parser.add_argument('--verify-manifest', action='store_true')
    args = parser.parse_args()
    toolkit, out = args.toolkit.resolve(), args.output_dir.resolve()
    if not toolkit.is_relative_to(ROOT/'package') or not out.is_relative_to(ROOT/'artifacts'):
        parser.error('Keep evidence and packages inside the independent prototype')
    if args.references:
        return references(toolkit, out)
    if out.exists(): parser.error('Use a fresh output directory')
    if os.environ.get('RIVE_UE_LITE_GPU_DEVICES_HIDDEN') != '1' or (ROOT/'engine/Engine/Config/Base.ini').exists():
        parser.error('Run under isolated_widget_worker.sh (GPU/development resources hidden)')
    out.mkdir(parents=True)
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    ws = out/'Workspace with spaces'
    base = ['bash', str(toolkit/'rive-tool'), '--workspace', str(ws)]
    report = {'status': 'incomplete', 'scope': 'Public JSON CLI and persistent coordinator using real packaged native workers; not UEFN/full Editor',
        'toolkit': str(toolkit), 'workspace': str(ws), 'runs': [], 'gates': {}, 'renders': []}
    def save(): (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    def gate(name, passed):
        report['gates'][name] = bool(passed)
        save()
        assert passed, name
    def cli(name, *argv, expected=0):
        command = [*base, *map(str, argv)]
        started = time.perf_counter()
        process = subprocess.run(command, capture_output=True, text=True, timeout=480, cwd='/tmp')
        (out/(name+'.stdout.json')).write_text(process.stdout)
        (out/(name+'.stderr.log')).write_text(process.stderr)
        data = json.loads(process.stdout)
        report['runs'].append({'name': name, 'command': command, 'exit_code': process.returncode,
            'expected_exit_code': expected, 'ok': data['ok'], 'client_wall_ms': (time.perf_counter()-started)*1000})
        save()
        assert process.returncode == expected and data['ok'] == (expected == 0), (name, data)
        print(json.dumps({'case': name, 'status': 'passed'}), flush=True)
        return data
    try:
        gate('gpu_nodes_hidden', not any(Path(p).exists() for p in ['/dev/dxg', '/dev/dri']))
        gate('development_hidden', all(not (ROOT/name).joinpath(child).exists() for name, child in
            [('engine', 'Engine/Config/Base.ini'), ('vendor', 'rive-unreal'), ('Binaries', 'Linux/RiveRhiLite'), ('Source', 'RiveRhiLite')]))
        caps = cli('01-capabilities', 'capabilities')['data']
        gate('all_four_components_present', all(item['available'] for item in caps['components'].values()))
        widget_caps = cli('01-widget-capabilities', 'widget', 'capabilities')['data']
        gate('agent_can_discover_widget_schema', widget_caps['read_existing_source_blueprint'] and 'Button' in widget_caps['create_widget_types'])
        cli('01-widget-create-help', 'widget', 'create', '--help')
        cli('02-doctor', 'doctor', *(['--verify'] if args.verify_manifest else []))
        cli('03-init', 'init')
        started = cli('04-start', 'start')
        report['coordinator_start_ms'] = started.get('coordinator_start_ms')
        proc_status = Path(f'/proc/{started["pid"]}/status').read_text()
        report['coordinator_ready_rss_kib'] = int(__import__('re').search(r'VmRSS:\s*(\d+)', proc_status)[1])
        gate('start_without_ue', started['native_workers_started'] == 0 and started['active_job'] is None)
        gate('reuse_coordinator', cli('05-start-again', 'start')['pid'] == started['pid'])
        for ui in ['rive', 'umg']:
            result = cli('06-render-'+ui, 'render', '--ui', ui, '--input', 'examples/bankcard.riv', '--output', f'renders/{ui}.png')
            gate(ui+'-cpu-rhi', result['data']['device']['status'] == 'passed' and result['data']['draw']['status'] == 'passed')
            report['renders'].append({'name': ui, 'ui': ui, 'input': str(ws/'examples/bankcard.riv'),
                'png': result['data']['output']['path'], 'metrics': result['data']['metrics']})
        hello = cli('07-verse-source', 'verse', 'run', '--source', 'examples/verse/hello.verse')
        gate('real_verse_compile_execute', 'Hello from the bundled VerseVM' in hello['data']['stdout'] and len(hello['data']['phases']) == 3)
        edit = ws/'examples/verse/hello.verse'
        edit.write_text(edit.read_text().replace('Hello from the bundled VerseVM', 'Agent edited this Verse source'))
        modified = cli('08-verse-edit-run', 'verse', 'run', '--source', 'examples/verse/hello.verse')
        gate('agent_can_edit_verse', 'Agent edited this Verse source' in modified['data']['stdout'] and hello['data']['source_sha256'] != modified['data']['source_sha256'])
        invalid = ws/'examples/verse/invalid.verse'
        invalid.write_text('Main(Args:[]string, Env:[string]string)<suspends>:void =\n    UnknownFunction()\n')
        failed = cli('09-verse-compile-error', 'verse', 'run', '--source', str(invalid), expected=1)
        logs = cli('09-read-failure-logs', 'jobs', '--id', failed['job_id'], '--logs')['data']['logs']
        gate('agent_can_read_compiler_diagnostics', any('UnknownFunction' in text for text in logs.values()))
        tested = cli('10-verse-tests', 'verse', 'test')['data']
        gate('event_suspend_cancel_rollback', {'event_resume', 'event_no_sticky_replay', 'suspended', 'race_cancel_defer_no_late_resume', 'failure_rollback', 'all'} <= set(tested['tests']))
        for ui in ['rive', 'umg']:
            paths = []
            for mode in ['pressed', 'idle']:
                result = cli('11-verse-'+ui+'-'+mode, 'verse', 'ui', '--ui', ui, '--mode', mode, '--output', f'renders/verse-{ui}-{mode}.png')
                data = result['data']
                gate(ui+'-'+mode+'-command', data['ui_commands'] == ['true' if mode == 'pressed' else 'false'])
                paths.append(data['render']['output']['path'])
                report['renders'].append({'name': 'verse-'+ui+'-'+mode, 'ui': ui,
                    'input': str(toolkit/'components/verse/fixtures/rocket.riv'), 'png': paths[-1],
                    'scenario': str(Path(result['report']).parent/'scenario.json'), 'metrics': data['render']['metrics']})
            gate(ui+'-verse-visible-effect', compare_images(Path(paths[0]), Path(paths[1]))['different_pixels'] > 0)
        asset = '/Game/UI/WBP_Card'
        created = cli('12-widget-create', 'widget', 'create', '--asset', asset, '--spec', 'examples/widget/card.json')
        gate('real_blueprint_created', created['data']['native']['metadata']['asset_class'] == '/Script/UMGEditor.WidgetBlueprint')
        read = cli('13-widget-read', 'widget', 'read', '--asset', asset)
        gate('read_is_readonly', read['data']['native']['sha256_before'] == read['data']['native']['sha256_after'])
        source_file = ws/'Content/UI/WBP_Card.uasset'
        before = sha256(source_file)
        bad_patch = ws/'examples/widget/bad.patch.json'
        bad_patch.write_text(json.dumps({'widgets': [{'name': 'Title', 'text': 'MUST NOT PERSIST'}, {'name': 'Unknown', 'text': 'reject'}]}))
        cli('14-widget-reject-atomic-edit', 'widget', 'patch', '--asset', asset, '--patch', str(bad_patch), expected=1)
        gate('failed_edit_preserves_asset', sha256(source_file) == before)
        cli('15-animation-create', 'widget', 'animation', 'create', '--asset', asset, '--spec', 'examples/widget/intro.animation.json')
        listed = cli('16-animation-list', 'widget', 'animation', 'list', '--asset', asset)
        gate('native_animation_read', listed['data']['native']['metadata']['animations'][0]['name'] == 'Intro')
        cli('17-animation-patch', 'widget', 'animation', 'patch', '--asset', asset, '--patch', 'examples/widget/intro.animation.patch.json')
        command = [*base, 'widget', 'preview', '--asset', asset, '--animation', 'Intro', '--time', '0.5', '--output', 'renders/intro.png']
        with (out/'18-preview.stdout.json').open('w') as stdout, (out/'18-preview.stderr.log').open('w') as stderr:
            process = subprocess.Popen(command, cwd='/tmp', stdout=stdout, stderr=stderr)
            for _ in range(100):
                status = cli('18-status', 'status')
                if status.get('active_job'): break
                time.sleep(.05)
            gate('status_while_native_job_runs', bool(status.get('active_job')))
            cli('18-busy-operation', 'render', expected=75)
            cli('18-busy-stop', 'stop', expected=75)
            assert process.wait(timeout=480) == 0
        preview = json.loads((out/'18-preview.stdout.json').read_text())
        meta = preview['data']['native']['metadata']
        gate('native_animation_preview', meta['animation_playback']['world_is_null'] and not meta['using_null_rhi'] and 'llvmpipe' in meta['adapter'])
        report['widget_preview'] = {'png': str(ws/'renders/intro.png'), 'asset': asset, 'content': str(ws/'Content'),
                                    'animation': 'Intro', 'time': .5, 'metrics': preview['data']['metrics']}
        import_source = toolkit/'components/widget/Content/UI/WBP_Card.uasset'
        import_before = sha256(import_source)
        imported = cli('19-import-existing', 'widget', 'import', '--asset', asset, '--input', str(import_source), '--content-dir', 'imported/Content')
        original = imported['data']['native']['metadata']
        patched = cli('20-patch-existing', 'widget', 'patch', '--asset', asset, '--content-dir', 'imported/Content', '--patch', 'examples/widget/card.patch.json')
        current = patched['data']['native']['metadata']
        gate('existing_graphs_preserved', original['graphs'] == current['graphs'] and original['variables'] == current['variables'])
        gate('external_source_unchanged', sha256(import_source) == import_before)
        exported = cli('21-export', 'widget', 'export', '--asset', asset, '--output', 'exports/widget.zip')
        with zipfile.ZipFile(ws/'exports/widget.zip') as archive:
            gate('real_asset_export', archive.read('Content/UI/WBP_Card.uasset')[:4] == source_file.read_bytes()[:4])
        jobs = cli('22-jobs', 'jobs')['data']
        gate('jobs_persisted', len(jobs) >= 10)
        cli('23-job-read', 'jobs', '--id', exported['job_id'])
        status = cli('24-status', 'status')
        gate('same_coordinator_after_all_operations', status['pid'] == started['pid'] and status['completed_jobs'] >= 15)
        cli('25-stop', 'stop')
        gate('stopped', not cli('26-status-stopped', 'status')['running'])
        report['status'] = 'passed_scoped'
    except Exception as error:
        report['status'], report['error'] = 'failed', str(error)
    finally:
        with __import__('contextlib').suppress(Exception):
            subprocess.run([*base, 'stop'], capture_output=True, timeout=10)
        save()
    print(json.dumps({'status': report['status'], 'gates': report['gates'], 'error': report.get('error')}), flush=True)
    return int(report['status'] != 'passed_scoped')


def references(toolkit, out):
    report = json.loads((out/'summary.json').read_text())
    assert report['status'] == 'passed_scoped'
    results = []
    for item in report['renders']:
        dest = out/'native-references'/item['name']
        dest.mkdir(parents=True)
        command = ['bash', str(ROOT/'scripts/measure_no_gpu.sh'), '--', 'env',
            'VK_DRIVER_FILES=/usr/share/vulkan/icd.d/lvp_icd.json', 'VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json', 'LP_NUM_THREADS=2',
            str(ROOT/'Binaries/Linux/RiveUeReference'), '-vulkan', '-sm5', '-AllowCPUDevices', '-RenderOffscreen', '-norhithread', '-unattended', '-stdout',
            f'-Ui={item["ui"]}', f'-ProjectDir={ROOT}/', f'-UserDir={dest}/user/', f'-Input={item["input"]}', f'-Output={dest}/frame.png',
            '-Width=512', '-Height=512', f'-ShaderArchive={ROOT}/artifacts/umg-optional/shaders-reference/global.bin', f'-ShaderDirectory={ROOT}/Shaders']
        if item.get('scenario'): command.append('-Scenario='+item['scenario'])
        with (dest/'native.log').open('wb') as log: result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        assert result.returncode == 0
        comparison = compare_images(Path(item['png']), dest/'frame.png')
        assert comparison['different_pixels'] == 0
        results.append({'name': item['name'], 'comparison': comparison})
        print(json.dumps({'reference': item['name'], 'different_pixels': 0}), flush=True)
    item = report['widget_preview']
    dest = out/'native-references/widget-animation'
    dest.mkdir(parents=True)
    command = ['bash', str(ROOT/'scripts/measure_no_gpu.sh'), '--', 'env',
        'VK_DRIVER_FILES=/usr/share/vulkan/icd.d/lvp_icd.json', 'VK_ICD_FILENAMES=/usr/share/vulkan/icd.d/lvp_icd.json', 'LP_NUM_THREADS=2',
        str(ROOT/'Binaries/Linux/RiveUmgBlueprintWorker'), '-unattended', '-stdout', '-vulkan', '-sm5', '-AllowCPUDevices', '-AllowCommandletRendering',
        '-RenderOffscreen', '-norhithread', '-Mode=render', '-NativeDesignerReference', f'-ProjectDir={ROOT}/', f'-ContentDir={item["content"]}',
        f'-Asset={item["asset"]}', f'-UserDir={dest}/user/', f'-Output={dest}/frame.png', f'-Metadata={dest}/metadata.json',
        f'-ShaderArchive={ROOT}/artifacts/umg-blueprint/shaders-reference/global.bin', '-Animation=Intro', '-AnimationTime=0.5']
    with (dest/'native.log').open('wb') as log: result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=240)
    assert result.returncode == 0
    comparison = compare_images(Path(item['png']), dest/'frame.png')
    assert comparison['different_pixels'] == 0
    results.append({'name': 'widget-animation', 'comparison': comparison})
    (out/'reference-comparisons.json').write_text(json.dumps({'status': 'passed', 'independent_reference_archives': True,
        'scope': 'Native Engine offscreen hosts and native source-tree animation preview; not UEFN/full Editor viewport', 'pairs': results}, indent=2)+'\n')
    print(json.dumps({'status': 'passed', 'pairs': len(results)}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
