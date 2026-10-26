#!/usr/bin/env python3
"""Real source .uasset -> CPU UE preview -> patch/save -> fresh reload -> native reference."""
from pathlib import Path
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import time
import zipfile

from compare_png import compare_images, sha256
from measure_ue_lite import apply_cpu_profile, run_once

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = '/Game/UI/WBP_RoundTrip'
RELATIVE_ASSET = Path('UI/WBP_RoundTrip.uasset')
PATCH = {'widgets': [
    {'name': 'Title', 'text': 'Saved Blueprint preview', 'position': [84, 44], 'size': [440, 52]},
    {'name': 'Badge', 'position': [96, 266], 'size': [240, 42]},
]}
ERROR = re.compile(r'^.*(?:Ensure condition failed:|Fatal error:|Log\w+: Error:).*$', re.M)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', type=Path, default=ROOT/'Binaries/Linux/RiveUmgBlueprintWorker')
    parser.add_argument('--host-archive', type=Path, required=True)
    parser.add_argument('--reference-archive', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--cpu-limit', type=int, default=2)
    args = parser.parse_args()
    if platform.system() != 'Linux' or os.environ.get('RIVE_UE_LITE_GPU_DEVICES_HIDDEN') != '1':
        parser.error('Run inside scripts/measure_no_gpu.sh')
    out = args.output_dir.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error('Use a fresh output directory')
    out.mkdir(parents=True, exist_ok=True)
    host_archive, reference_archive = args.host_archive.resolve(), args.reference_archive.resolve()
    if host_archive == reference_archive or host_archive.samefile(reference_archive):
        parser.error('Use distinct, independently cooked shader archive files')
    # Deterministic independent cooks may legitimately produce identical bytes.
    provenances = []
    for archive in (host_archive, reference_archive):
        provenance = json.loads((archive.parent/'provenance/provenance.json').read_text())
        manifest = json.loads(Path(str(archive)+'.manifest.json').read_text())
        execution = provenance['cook_execution']
        if (provenance['status'] != 'passed' or not execution['archive_absent_before_invocation'] or
                not execution['executed'] or execution['output']['sha256'] != sha256(archive) or
                not manifest['complete'] or not manifest['target_has_editor_only_data'] or
                any(t['source'].startswith('/Plugin/Rive/') for t in manifest['types'])):
            parser.error(f'Invalid independent native Slate Editor cook: {archive}')
        provenances.append(execution['execution_id'])
    if len(set(provenances)) != 2:
        parser.error('Each archive requires a separate recorded native cooker invocation')
    report = {
        'status': 'incomplete',
        'scope': 'Real uncooked WidgetBlueprint, CanvasPanel/TextBlock/Border, native UE compiler/save/load; '
                 'CPU Vulkan offscreen comparison with native source-tree preview, not the full Editor viewport',
        'engine_commit': '62d7c1a7125b52b10ee1b714838f515f3563f795',
        'gpu_namespace': os.environ.get('RIVE_UE_LITE_MOUNT_NAMESPACE'),
        'gpu_nodes': {p: Path(p).exists() for p in ['/dev/dxg', '/dev/dri']},
        'worker': {'path': str(args.worker.resolve()), 'sha256': sha256(args.worker), 'bytes': args.worker.stat().st_size},
        'shader_archives': {k: {'path': str(p), 'sha256': sha256(p)}
                            for k, p in [('host', host_archive), ('reference', reference_archive)]},
        'native_cook_execution_ids': provenances,
        'runs': [], 'comparisons': [],
    }
    env = dict(os.environ, VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/lvp_icd.json',
               VK_DRIVER_FILES='/usr/share/vulkan/icd.d/lvp_icd.json',
               SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', LC_ALL='C', LANG='C')
    report['cpu_profile'] = apply_cpu_profile(args.cpu_limit, args.cpu_limit, env)

    def run(name, mode, content, *, reference=False, extra=()):
        dest = out/name
        dest.mkdir()
        metadata = dest/'metadata.json'
        png = dest/'output.png'
        common = ['-unattended', '-stdout', '-NoSplash', '-NoCrashDialog',
                  f'-ProjectDir={ROOT}/', f'-UserDir={dest}/user/', f'-abslog={dest}/ue.log',
                  f'-Mode={mode}', f'-ContentDir={content}', f'-Asset={PACKAGE}', f'-Metadata={metadata}', *extra]
        runenv = dict(env, MESA_SHADER_CACHE_DIR=str(dest/'mesa-cache'))
        if mode == 'render':
            common += ['-vulkan', '-sm5', '-AllowCPUDevices', '-AllowCommandletRendering',
                       '-RenderOffscreen', '-norhithread', '-Output={output}',
                       f'-ShaderArchive={reference_archive if reference else host_archive}']
            if reference:
                common.append('-NativeDesignerReference')
            result = run_once(args.worker.resolve(), common, png, 0, dest, runenv, 240, Path('/tmp'))
            result['measurement_scope'] = 'Real source UMG Blueprint load and native Slate RHI capture; no Rive in this fixture'
            log = (dest/'run-000.log').read_text(errors='replace')
        else:
            logfile, timefile = dest/'run-000.log', dest/'run-000.time.txt'
            command = [str(args.worker.resolve()), *common]
            started = time.monotonic()
            with logfile.open('w') as stream:
                completed = subprocess.run(['/usr/bin/time', '-v', '-o', str(timefile), '--', *command],
                                           cwd='/tmp', env=runenv, stdout=stream,
                                           stderr=subprocess.STDOUT, timeout=240)
            log = logfile.read_text(errors='replace')
            timing = timefile.read_text()
            rss = re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)', timing)
            result = {'status': 'passed' if completed.returncode == 0 else 'failed',
                      'command': command, 'exit_code': completed.returncode, 'log': str(logfile),
                      'wall_seconds': time.monotonic()-started, 'peak_rss_kib': int(rss[1]) if rss else None}
        result.update(name=name, mode=mode, runtime_errors=ERROR.findall(log))
        if result['runtime_errors'] or 'UMG_BP_COMPLETE' not in log or not metadata.is_file():
            result['status'] = 'failed'
        report['runs'].append(result)
        (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
        if result['status'] != 'passed':
            raise RuntimeError(f'{name} failed; see {dest}')
        meta = json.loads(metadata.read_text())
        result['worker_pid'] = meta['pid']
        assert meta['asset_class'] == '/Script/UMGEditor.WidgetBlueprint'
        assert meta['source_blueprint'] and not meta['cooked']
        assert meta['slate_window_count'] == 0, 'A visual Editor window was opened'
        if mode == 'render':
            assert not meta['using_null_rhi'], 'A screenshot used NullRHI'
            assert re.search(r'llvmpipe|lavapipe', meta['adapter'], re.I), meta['adapter']
        return png, meta

    def widgets(meta):
        return {entry['name']: entry for entry in meta['widgets']}

    try:
        assert not any(report['gpu_nodes'].values())
        edited = out/'edited/Content'
        expected_before = out/'native-before/Content'
        expected_after = out/'native-after/Content'
        for content in (edited, expected_before, expected_after):
            content.mkdir(parents=True)
        _, created = run('01-create-real-source', 'create', edited)
        original_asset = edited/RELATIVE_ASSET
        original_hash = sha256(original_asset)
        original_copy = out/'original/Content'/RELATIVE_ASSET
        original_copy.parent.mkdir(parents=True)
        shutil.copy2(original_asset, original_copy)
        run('02-create-native-before', 'create', expected_before)
        run('03-create-native-after', 'create', expected_after, extra=['-ModifiedFixture'])
        before_png, before = run('04-load-original', 'render', edited)
        assert sha256(original_asset) == original_hash, 'Preview changed the source package'
        native_before_png, _ = run('05-native-original', 'render', expected_before, reference=True)
        patch_path = out/'patch.json'
        patch_path.write_text(json.dumps(PATCH, indent=2)+'\n')
        run('06-patch-and-save', 'patch', edited, extra=[f'-Patch={patch_path}'])
        after_hash = sha256(original_asset)
        assert after_hash != original_hash
        after_png, after = run('07-reload-edited', 'render', edited)
        native_after_png, _ = run('08-native-edited', 'render', expected_after, reference=True)
        repeat_png, repeat = run('09-second-fresh-reload', 'render', edited)
        assert sha256(original_asset) == after_hash, 'Reload changed the edited source package'
        for name, left, right in [('original_vs_native', native_before_png, before_png),
                                  ('edited_vs_native', native_after_png, after_png),
                                  ('fresh_reload_stable', after_png, repeat_png)]:
            comparison = {'name': name, **compare_images(left, right)}
            report['comparisons'].append(comparison)
            assert comparison['status'] == 'passed', name
        difference = compare_images(before_png, after_png)
        report['edit_difference'] = difference
        assert difference['different_pixels'] > 0
        bw, aw, rw = widgets(before), widgets(after), widgets(repeat)
        assert set(bw) == set(aw) == set(rw)
        for edit in PATCH['widgets']:
            actual = aw[edit['name']]
            for field in ('text', 'position', 'size'):
                if field in edit:
                    assert actual[field] == edit[field], (field, actual)
                    rendered_field = {'text': 'rendered_text', 'position': 'rendered_position', 'size': 'rendered_size'}[field]
                    assert actual[rendered_field] == edit[field], (rendered_field, actual)
                    assert rw[edit['name']][field] == edit[field]
        edited_names = {edit['name'] for edit in PATCH['widgets']}
        for name in set(bw)-edited_names:
            authored = lambda widget: {k: v for k, v in widget.items() if not k.startswith('rendered_')}
            assert authored(bw[name]) == authored(aw[name]), name
        # BadgeLabel is nested inside Badge: native layout must follow its parent.
        assert bw['BadgeLabel']['rendered_position'] != aw['BadgeLabel']['rendered_position']
        assert bw['BadgeLabel']['rendered_size'] != aw['BadgeLabel']['rendered_size']
        report['nested_layout_propagation'] = 'passed'
        report['property_persistence'] = 'passed'
        report['unmodified_widgets_preserved'] = 'passed'
        pids = [run['worker_pid'] for run in report['runs']]
        assert len(set(pids)) == len(pids), pids
        report['assets'] = {'original': {'path': str(original_copy), 'sha256': original_hash},
                            'edited': {'path': str(original_asset), 'sha256': after_hash,
                                       'bytes': original_asset.stat().st_size}}
        download = out/'WBP_RoundTrip-edited.zip'
        with zipfile.ZipFile(download, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.write(original_asset, 'Content/'+str(RELATIVE_ASSET))
            archive.write(patch_path, 'patch.json')
            archive.writestr('README.txt', 'Real uncooked UE Widget Blueprint. Copy Content/UI/WBP_RoundTrip.uasset '
                             'into a project using compatible UE source commit '+report['engine_commit']+'.\n')
        report['download'] = {'path': str(download), 'bytes': download.stat().st_size, 'sha256': sha256(download)}
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', error=str(error))
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'status': report['status'], 'runs': len(report['runs']),
                      'comparisons': len(report['comparisons']), 'error': report.get('error')}, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
