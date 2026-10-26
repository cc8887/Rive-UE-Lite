#!/usr/bin/env python3
"""Real native UMG animation authoring/reload/playback and CPU screenshot gates."""
from pathlib import Path
import argparse
import copy
import json
import math
import os
import re
import shutil
import subprocess
import sys

from compare_png import compare_images, sha256

ROOT = Path(__file__).resolve().parents[1]
ERROR = re.compile(r'Ensure condition failed:|Fatal error:|Log\w+: Error:')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args(); out = a.output_dir.resolve()
    if out.exists(): p.error('Use a fresh directory')
    if os.environ.get('RIVE_UE_LITE_GPU_DEVICES_HIDDEN') != '1': p.error('Run under measure_no_gpu.sh')
    out.mkdir(parents=True)
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', LP_NUM_THREADS='2',
        VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/lvp_icd.json', VK_DRIVER_FILES='/usr/share/vulkan/icd.d/lvp_icd.json')
    report = {'status': 'incomplete', 'scope': 'native source WBP/UMG animation worker; not UEFN or full Editor viewport',
        'gpu_nodes': {p: Path(p).exists() for p in ['/dev/dxg', '/dev/dri']}, 'runs': [], 'gates': {}, 'comparisons': []}
    content = out/'editable/Content'; asset = '/Game/UI/WBP_Card'; asset_file = content/'UI/WBP_Card.uasset'
    fixtures = ROOT/'fixtures/widget-blueprint'; worker = ROOT/'Binaries/Linux/RiveUmgBlueprintWorker'

    def save(): (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    def gate(name, passed):
        report['gates'][name] = bool(passed); save(); assert passed, name
    def cli(name, cmd, *flags, expected=True, folder=content, package=asset):
        dest = out/name
        command = [sys.executable, '-B', str(ROOT/'scripts/widget_bp.py'), *cmd.split(),
            '--content-dir', str(folder), '--asset', package, '--report-dir', str(dest), *map(str, flags)]
        with (out/(name+'.console.log')).open('wb') as log:
            result = subprocess.run(command, cwd='/tmp', env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        data = json.loads((dest/'report.json').read_text())
        report['runs'].append({'name': name, 'command': command, 'exit_code': result.returncode,
            'status': data['status'], 'report': str(dest/'report.json')}); save()
        assert (result.returncode == 0) == expected, (name, data.get('error'))
        return data
    def meta(result): return result['metadata']
    def animations(result): return {x['name']: x for x in meta(result)['animations']}
    def widget(snapshot, name='Title'): return next(w for w in snapshot['widgets'] if w['name'] == name)
    def close(actual, expected): return math.isclose(actual, expected, rel_tol=0, abs_tol=1e-4)
    def script(name, ops, *, animation='Intro'):
        file = out/(name+'.json'); file.write_text(json.dumps({'operations': ops})+'\n')
        result = cli(name, 'preview', '--animation', animation, '--playback-script', file, '--output', out/(name+'.png'))
        playback = meta(result)['animation_playback']
        gate(name+'-worldless', playback['world_is_null'] and playback['owns_minimal_engine'] and not playback['engine_initialized'])
        return playback['snapshots']
    def native_reference(name, target_png, time):
        dest = out/name; dest.mkdir()
        reference_archive = ROOT/'artifacts/umg-blueprint/shaders-reference/global.bin'
        command = [str(worker), '-unattended', '-stdout', '-vulkan', '-sm5', '-AllowCPUDevices', '-AllowCommandletRendering',
            '-RenderOffscreen', '-norhithread', '-Mode=render', '-NativeDesignerReference',
            f'-ProjectDir={ROOT}/', f'-ContentDir={content}', f'-Asset={asset}', f'-UserDir={dest}/user/',
            f'-Output={dest}/frame.png', f'-Metadata={dest}/asset.json', f'-ShaderArchive={reference_archive}',
            '-Animation=Intro', f'-AnimationTime={time}']
        with (dest/'worker.log').open('wb') as log:
            process = subprocess.run(command, cwd='/tmp', env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        text = (dest/'worker.log').read_text(errors='replace')
        assert process.returncode == 0 and 'UMG_BP_TEARDOWN complete' in text and not ERROR.search(text), name
        reference = json.loads((dest/'asset.json').read_text())
        assert 'source WidgetTree' in reference['preview_path'] and not reference['using_null_rhi']
        comparison = compare_images(target_png, dest/'frame.png')
        report['comparisons'].append({'name': name, 'command': command, **comparison}); save()
        assert comparison['different_pixels'] == 0, name

    try:
        gate('gpu_nodes_hidden', not any(report['gpu_nodes'].values()))
        created = cli('01-create', 'create', '--spec', fixtures/'card.json')
        base_file = out/'static/Content/UI/WBP_Card.uasset'; base_file.parent.mkdir(parents=True); shutil.copy2(asset_file, base_file)
        base_sha = sha256(base_file)
        empty = cli('02-list-empty', 'animation list')
        gate('list_existing_empty', not animations(empty))
        added = cli('03-animation-create', 'animation create', '--spec', fixtures/'intro.animation.json')
        reloaded = cli('04-animation-reload', 'animation list')
        gate('native_animation_roundtrip', animations(added) == animations(reloaded) and len(animations(reloaded)['Intro']['tracks']) == 2)
        gate('correct_tick_conversion', animations(reloaded)['Intro']['tick_numerator'] == 240000 and
            animations(reloaded)['Intro']['tracks'][0]['sections'][0]['channels']['value']['keys'][1]['tick'] == 240000)
        keep_spec = {'name': 'Keep', 'fps': 30, 'duration_frames': 30, 'tracks': [
            {'widget': 'Body', 'property': 'opacity', 'interpolation': 'constant', 'keys': [{'frame': 0, 'value': .3}, {'frame': 30, 'value': .9}]}]}
        keep = out/'keep.json'; keep.write_text(json.dumps(keep_spec))
        before_patch = cli('05-second-animation', 'animation create', '--spec', keep)
        changed = cli('06-animation-patch', 'animation patch', '--patch', fixtures/'intro.animation.patch.json', '--expected-sha256', sha256(asset_file))
        after = cli('07-patch-reload', 'read')
        before_anims, after_anims = animations(before_patch), animations(after)
        gate('patch_roundtrip', animations(changed) == after_anims)
        gate('other_animation_preserved', before_anims['Keep'] == after_anims['Keep'])
        old_transform = next(t for t in before_anims['Intro']['tracks'] if t['property'] == 'RenderTransform')
        new_transform = next(t for t in after_anims['Intro']['tracks'] if t['property'] == 'RenderTransform')
        gate('unmodified_transform_binding_channels_preserved', old_transform == new_transform and before_anims['Intro']['bindings'] == after_anims['Intro']['bindings'])
        gate('widget_source_properties_preserved', meta(created)['widgets'] == meta(after)['widgets'])
        old_hash = sha256(asset_file)
        invalid = copy.deepcopy(json.loads((fixtures/'intro.animation.patch.json').read_text())); invalid['tracks'][0]['keys'][1]['frame'] = 61
        invalid_file = out/'invalid.json'; invalid_file.write_text(json.dumps(invalid))
        cli('08-invalid-key-rejected', 'animation patch', '--patch', invalid_file, expected=False)
        cli('09-stale-rejected', 'animation patch', '--patch', fixtures/'intro.animation.patch.json', '--expected-sha256', '0'*64, expected=False)
        cli('10-overwrite-rejected', 'animation create', '--spec', fixtures/'intro.animation.json', expected=False)
        gate('failed_edits_atomic', sha256(asset_file) == old_hash)
        scale_patch = out/'scale.patch.json'
        scale_patch.write_text(json.dumps({'name':'Intro', 'tracks':[{'widget':'Title','property':'render_scale','interpolation':'linear',
            'keys':[{'frame':0,'value':[.8,.8]},{'frame':60,'value':[1.2,1.1]}]}]}))
        scale_edit = cli('10b-scale-channel-patch', 'animation patch', '--patch', scale_patch)
        scale_transform = next(t for t in animations(scale_edit)['Intro']['tracks'] if t['property']=='RenderTransform')
        preserved_channels = ['translation_x','translation_y','angle','shear_x','shear_y']
        gate('patch_inside_transform_preserves_other_channels', all(new_transform['sections'][0]['channels'][k] ==
            scale_transform['sections'][0]['channels'][k] for k in preserved_channels))
        old_hash = sha256(asset_file)
        # Two native code paths, two independently executed native Slate cooks.
        archives = [ROOT/f'artifacts/umg-blueprint/shaders-{side}/global.bin' for side in ['host', 'reference']]
        ids = [json.loads((archive.parent/'provenance/provenance.json').read_text())['cook_execution']['execution_id'] for archive in archives]
        gate('independent_shader_cooks', len(set(ids)) == 2)
        report['native_cook_execution_ids'] = ids
        hashes = []
        for index, time in enumerate([0, .25, .5, 1]):
            name = f'11-frame-{index}'
            result = cli(name, 'preview', '--animation', 'Intro', '--time', str(time), '--output', out/(name+'.png'))
            play = meta(result)['animation_playback']; actual = widget(play['snapshots'][-1])
            gate(name+'-evaluated-properties', close(actual['opacity'], .2+.6*time) and
                close(actual['translation'][0], 80*time) and close(actual['translation'][1], 32*(1-time)) and
                close(actual['scale'][0], .8+.4*time) and close(actual['scale'][1], .8+.3*time) and close(actual['angle'], -8+16*time))
            gate(name+'-worldless', play['world_is_null'] and not play['engine_initialized'])
            hashes.append(sha256(out/(name+'.png')))
            native_reference(name+'-native-reference', out/(name+'.png'), time)
        gate('visible_animation', len(set(hashes)) == 4)
        samples = []
        for hz in [30, 60, 120]:
            name = '12-forward-'+str(hz)
            snapshots = script(name, [{'op': 'play', 'loops': 0}, {'op': 'tick', 'seconds': .5, 'hz': hz}])
            gate(name+'-midpoint', close(widget(snapshots[-1])['opacity'], .5) and close(widget(snapshots[-1])['translation'][0], 40))
            samples.append(out/(name+'.png'))
        for index, file in enumerate(samples[1:]):
            comparison = compare_images(samples[0], file); report['comparisons'].append({'name': 'hz-parity-'+str(index), **comparison})
            gate('hz-parity-'+str(index), comparison['different_pixels'] == 0)
        snapshots = script('13-native-controls', [
            {'op':'play', 'loops':0}, {'op':'tick', 'seconds':.25}, {'op':'pause'}, {'op':'tick', 'seconds':.25},
            {'op':'resume'}, {'op':'seek', 'time':.75}, {'op':'reverse'}, {'op':'tick', 'seconds':.25},
            {'op':'stop'}, {'op':'tick', 'seconds':.5}, {'op':'stop'}])
        gate('pause_holds', widget(snapshots[2]) == widget(snapshots[3]) and close(snapshots[2]['time_seconds'], snapshots[3]['time_seconds']))
        gate('seek_evaluates', close(widget(snapshots[5])['opacity'], .65))
        gate('reverse_evaluates', close(widget(snapshots[7])['opacity'], .5))
        gate('stop_restores', close(widget(snapshots[8])['opacity'], 1) and widget(snapshots[8])['translation'] == [0, 0] and widget(snapshots[8])['scale'] == [1, 1])
        gate('cancel_no_late_write_or_duplicate_callback', widget(snapshots[8]) == widget(snapshots[9]) == widget(snapshots[10]) and
            snapshots[8]['finished_events'] == snapshots[9]['finished_events'] == snapshots[10]['finished_events'] == 1)
        snapshots = script('14-reverse-start', [{'op':'play', 'direction':'reverse', 'loops':0}, {'op':'tick', 'seconds':.25}])
        gate('reverse_from_end', close(widget(snapshots[-1])['opacity'], .65))
        snapshots = script('15-loop-and-finish', [{'op':'play', 'loops':2}, {'op':'tick', 'seconds':1.25}, {'op':'tick', 'seconds':1}, {'op':'tick', 'seconds':.25}])
        gate('loop_boundary', close(widget(snapshots[1])['opacity'], .35))
        gate('natural_finish_restores_once', snapshots[2]['finished_events'] == snapshots[3]['finished_events'] == 1 and close(widget(snapshots[2])['opacity'], 1))
        snapshots = script('16-constant-interpolation', [{'op':'play', 'loops':0}, {'op':'tick', 'seconds':.5}], animation='Keep')
        gate('constant_key_evaluates', close(widget(snapshots[-1], 'Body')['opacity'], .3))
        # Repeat play/stop in one process exercises native state lifetime/teardown.
        ops = []
        for _ in range(10): ops += [{'op':'play','loops':0}, {'op':'tick','seconds':.01}, {'op':'stop'}]
        snapshots = script('17-repeated-lifetime', ops)
        gate('repeated_state_lifetime', snapshots[-1]['finished_events'] == 10 and close(widget(snapshots[-1])['opacity'], 1))
        # Existing binary WBP with nonempty graph and actual CDO defaults.
        original = out/'existing-original/Content'; original.mkdir(parents=True)
        command = [str(worker), '-unattended', '-stdout', '-Mode=create', '-PreservationFixture',
            f'-ProjectDir={ROOT}/', f'-ContentDir={original}', '-Asset=/Game/UI/WBP_Existing', f'-UserDir={out}/seed-user/']
        with (out/'existing-seed.log').open('wb') as log:
            result = subprocess.run(command, cwd='/tmp', env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        assert result.returncode == 0
        existing = out/'existing-edit/Content'; source = original/'UI/WBP_Existing.uasset'; source_sha = sha256(source)
        imported = cli('18-import-existing', 'import', '--input', source, folder=existing, package='/Game/UI/WBP_Existing')
        cli('19-existing-animation', 'animation create', '--spec', fixtures/'intro.animation.json', folder=existing, package='/Game/UI/WBP_Existing')
        cli('20-existing-patch', 'animation patch', '--patch', fixtures/'intro.animation.patch.json', folder=existing, package='/Game/UI/WBP_Existing')
        existing_after = cli('21-existing-reload', 'read', folder=existing, package='/Game/UI/WBP_Existing')
        gate('existing_graph_variables_preserved', meta(imported)['graphs'] == meta(existing_after)['graphs'] and
            meta(imported)['variables'] == meta(existing_after)['variables'] and
            any(v['name'] == 'PreservedCounter' and v['default'] == '41' for v in meta(existing_after)['variables']))
        gate('original_import_unchanged', sha256(source) == source_sha and sha256(base_file) == base_sha)
        opaque_spec = out/'opaque.json'; opaque_data = json.loads((fixtures/'intro.animation.json').read_text()); opaque_data['name']='Opaque'
        opaque_spec.write_text(json.dumps(opaque_data))
        command = [str(worker), '-unattended', '-stdout', '-Mode=animation-create', '-AnimationOpaqueFixture',
            f'-ProjectDir={ROOT}/', f'-ContentDir={existing}', '-Asset=/Game/UI/WBP_Existing', f'-Spec={opaque_spec}', f'-UserDir={out}/opaque-user/']
        with (out/'opaque-seed.log').open('wb') as log:
            result = subprocess.run(command, cwd='/tmp', env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        assert result.returncode == 0 and not ERROR.search((out/'opaque-seed.log').read_text(errors='replace'))
        opaque_before = cli('21b-read-opaque', 'animation list', folder=existing, package='/Game/UI/WBP_Existing')
        opaque_patch = out/'opaque.patch.json'; opaque_patch.write_text(json.dumps({'name':'Opaque', 'tracks':
            json.loads((fixtures/'intro.animation.patch.json').read_text())['tracks']}))
        cli('21c-patch-opaque', 'animation patch', '--patch', opaque_patch, folder=existing, package='/Game/UI/WBP_Existing')
        opaque_after = cli('21d-reload-opaque', 'read', folder=existing, package='/Game/UI/WBP_Existing')
        unknown = lambda r: [t for t in animations(r)['Opaque']['tracks'] if t['read_only']]
        gate('unknown_native_track_preserved', len(unknown(opaque_before)) == 1 and unknown(opaque_before) == unknown(opaque_after))
        gate('other_animation_and_graph_preserved_with_unknown_track', animations(opaque_before)['Intro'] == animations(opaque_after)['Intro'] and
            meta(opaque_before)['graphs'] == meta(opaque_after)['graphs'] and meta(opaque_before)['variables'] == meta(opaque_after)['variables'])
        cli('21e-opaque-preview-rejected', 'preview', '--animation', 'Opaque', '--output', out/'opaque-denied.png', expected=False,
            folder=existing, package='/Game/UI/WBP_Existing')
        gate('readonly_playback_source_unchanged', sha256(asset_file) == old_hash)
        cli('22-export', 'export', '--output', out/'WBP_Card-animated.zip')
        report['asset_sizes'] = {'base_bytes': base_file.stat().st_size, 'animated_bytes': asset_file.stat().st_size,
            'added_bytes': asset_file.stat().st_size-base_file.stat().st_size, 'base_sha256': base_sha, 'animated_sha256': sha256(asset_file)}
        report['status'] = 'passed_scoped'
    except Exception as error:
        report['status'] = 'failed'; report['error'] = repr(error)
    save(); print(json.dumps({'status': report['status'], 'gates': report['gates'], 'error': report.get('error')}, indent=2))
    return int(report['status'] != 'passed_scoped')


if __name__ == '__main__': raise SystemExit(main())
