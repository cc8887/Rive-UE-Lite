#!/usr/bin/env python3
"""Native texture/brush asset roundtrip, semantic pixels and fresh UE reference.

The shipped CLI decodes images using UE ImageWrapper. Test fixtures are small
deterministic RGBA/gray images; screenshot inspection uses the stdlib PNG reader.
"""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

from compare_png import compare_images, read_png, sha256

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = '/Game/UI/WBP_Textured'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--toolkit', type=Path, help='Exercise the unified packaged CLI rather than source entry')
    p.add_argument('--skip-references', action='store_true', help='Portable test with development sources hidden; reference is tested separately')
    a = p.parse_args()
    out = a.output_dir.resolve()
    if out.exists(): p.error('Use a fresh output directory')
    if os.environ.get('RIVE_UE_LITE_GPU_DEVICES_HIDDEN') != '1': p.error('Run under measure_no_gpu.sh')
    out.mkdir(parents=True)
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', LP_NUM_THREADS='2')
    ws = out/'workspace with spaces'; content = ws/'Content'; ws.mkdir()
    toolkit = a.toolkit.resolve() if a.toolkit else None
    report = {'status': 'incomplete', 'scope': 'native source Texture2D, Image/Border brushes and direct texture dependency ZIP; not UI materials/UEFN',
              'gpu_devices_absent': not any(Path(x).exists() for x in ['/dev/dxg', '/dev/dri']),
              'reference_validation_skipped': a.skip_references, 'runs': [], 'gates': {}, 'references': []}
    native_hashes = {name: sha256(ROOT/f'Binaries/Linux/{name}') for name in ['RiveRhiLite', 'RiveUmgHost', 'RiveVerseWorker']
                     if (ROOT/f'Binaries/Linux/{name}').is_file()}

    def save(): (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    def gate(name, ok):
        report['gates'][name] = bool(ok); save(); assert ok, name
    def call(name, command, asset=PACKAGE, *extra, expected=True, mount=content):
        argv = [*command.split(), '--asset', asset, '--content-dir', str(mount), *map(str, extra)]
        if toolkit:
            cmd = ['bash', str(toolkit/'rive-tool'), '--workspace', str(ws), 'widget', *argv]
        else:
            cmd = [sys.executable, '-B', str(ROOT/'scripts/widget_bp.py'), '--workspace-root', str(out),
                   *argv, '--report-dir', str(out/name)]
        process = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        (out/(name+'.stdout.json')).write_text(process.stdout)
        (out/(name+'.stderr.log')).write_text(process.stderr)
        data = json.loads(process.stdout)
        result = data.get('data', {}).get('native', data)
        if not expected and toolkit: result = {'status': 'failed', 'error': data.get('error')}
        report['runs'].append({'name': name, 'exit_code': process.returncode, 'command': cmd,
            'report': data.get('report', str(out/name/'report.json')), 'wall_seconds': result.get('wall_seconds')})
        save()
        assert (process.returncode == 0) == expected, (name, data)
        assert result['status'] == ('passed' if expected else 'failed'), (name, result)
        if not expected:
            job = Path(data.get('report', str(out/name/'report.json'))).parent
            native_log = (job/'native/worker.log') if toolkit else job/'worker.log'
            if native_log.is_file():
                assert not re.search(r'Assertion failed:|Ensure condition failed:|Fatal error:', native_log.read_text(errors='replace'))
        print(json.dumps({'case': name, 'status': 'passed'}), flush=True)
        return result
    def widgets(result): return {w['name']: w for w in result['metadata']['widgets']}
    def preview(name, mount=content):
        path = (ws/'renders' if toolkit else out)/(name+'.png')
        result = call(name, 'preview', PACKAGE, '--output', path, mount=mount)
        gate(name+'-cpu', not result['metadata']['using_null_rhi'] and 'llvmpipe' in result['metadata']['adapter'].lower())
        return path
    def reference(name, host_png, animation=None, time=0):
        if a.skip_references: return
        archive = ROOT/'artifacts/umg-blueprint/shaders-reference/global.bin'
        host_archive = ROOT/'artifacts/umg-blueprint/shaders-host/global.bin'
        cooks = [json.loads((path.parent/'provenance/provenance.json').read_text())['cook_execution']['execution_id']
                 for path in [host_archive, archive]]
        assert len(set(cooks)) == 2 and not archive.samefile(host_archive)
        dest = out/(name+'-reference'); dest.mkdir()
        cmd = [str(ROOT/'Binaries/Linux/RiveUmgBlueprintWorker'), '-unattended', '-stdout', '-vulkan', '-sm5',
               '-AllowCPUDevices', '-AllowCommandletRendering', '-RenderOffscreen', '-norhithread',
               '-Mode=render', '-NativeDesignerReference', f'-ProjectDir={ROOT}/', f'-ContentDir={content}',
               f'-Asset={PACKAGE}', f'-UserDir={dest}/user/', f'-Output={dest}/output.png',
               f'-Metadata={dest}/asset.json', f'-ShaderArchive={archive}']
        if animation: cmd += [f'-Animation={animation}', f'-AnimationTime={time}']
        ref_env = dict(env, VK_DRIVER_FILES='/usr/share/vulkan/icd.d/lvp_icd.json',
                       VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/lvp_icd.json')
        with (dest/'worker.log').open('wb') as log:
            proc = subprocess.run(cmd, cwd='/tmp', env=ref_env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        text = (dest/'worker.log').read_text(errors='replace')
        assert proc.returncode == 0 and 'UMG_BP_TEARDOWN complete' in text, text[-2500:]
        assert not re.search(r'Ensure condition failed:|Fatal error:|Log\w+: Error:', text)
        meta = json.loads((dest/'asset.json').read_text())
        assert not meta['using_null_rhi'] and 'llvmpipe' in meta['adapter'].lower()
        comparison = compare_images(host_png, dest/'output.png')
        report['references'].append({'state': name, 'cook_execution_ids': cooks, 'comparison': comparison,
                                     'host': str(host_png), 'reference': str(dest/'output.png')})
        gate(name+'-native-reference', comparison['different_pixels'] == 0)

    try:
        gate('gpu-hidden', report['gpu_devices_absent'])
        fixtures = toolkit/'examples/widget' if toolkit else ROOT/'fixtures/widget-blueprint'
        png, jpg, replacement = ws/'alpha image.png', ws/'gray image.jpg', ws/'replacement.jpg'
        for src, dst in [('alpha-test.png',png), ('gray-test.jpg',jpg), ('replacement-test.jpg',replacement)]:
            shutil.copy2(fixtures/src, dst)
        tex = call('01-import-png', 'texture import', '/Game/Textures/T_Icon', '--input', png, '--filter', 'nearest')
        gate('native-png-source', tex['metadata']['source_texture'] and tex['metadata']['width'] == 64 and
             tex['metadata']['height'] == 37 and not tex['metadata']['cooked'])
        call('02-import-jpeg', 'texture import', '/Game/Textures/T_Photo', '--input', jpg)
        call('03-import-linear', 'texture import', '/Game/Textures/T_Linear', '--input', jpg, '--linear')
        compressed = call('03-import-compressed', 'texture import', '/Game/Textures/T_Compressed', '--input', jpg, '--compression', 'default')
        gate('native-platform-compression-setting', compressed['metadata']['compression'] == 'default')
        read = call('04-texture-fresh-read', 'texture read', '/Game/Textures/T_Icon')
        gate('source-texture-reload', read['metadata']['srgb'] and read['metadata']['filter'] == 'nearest')
        spec = (toolkit/'examples/widget/textured.json') if toolkit else ROOT/'fixtures/widget-blueprint/textured.json'
        created = call('05-create-image-widget', 'create', PACKAGE, '--spec', spec)
        gate('four-direct-texture-dependencies', len(created['metadata']['texture_dependencies']) == 4)
        original = content/'UI/WBP_Textured.uasset'; stable = sha256(original)
        reloaded = call('06-blueprint-fresh-read', 'read')
        gate('brush-source-roundtrip', widgets(reloaded) == widgets(created) and sha256(original) == stable)
        before = preview('07-before')
        pixels = read_png(before)
        def pixel(pos):
            start = (pos[1]*pixels['width']+pos[0])*4
            return list(pixels['rgba'][start:start+4])
        report['semantic_pixels'] = {str(p): pixel(p) for p in [(48,96),(128,96),(48,176),(128,176),(224,112),(384,112)]}
        red, green, blue, transparent = [pixel(p) for p in [(48,96),(128,96),(48,176),(128,176)]]
        gate('png-rgb-and-alpha-visible', red[0] > 240 and red[1] < 5 and blue[2] > 240 and blue[0] < 5 and
             110 <= green[1] <= 140 and green[0] < 5 and max(transparent[:3]) < 5)
        srgb, linear = pixel((224,112))[0], pixel((384,112))[0]
        gate('srgb-vs-linear-sampling', 45 <= srgb <= 65 and 120 <= linear <= 135)
        gate('native-compressed-texture-visible', 40 <= pixel((544,112))[0] <= 70)
        reference('before', before)
        patch = ws/'image.patch.json'
        patch.write_text(json.dumps({'widgets': [
            {'name':'Logo','brush':{'texture':'/Game/Textures/T_Photo','image_size':[48,48]}, 'color':[1,.5,1,.8]},
            {'name':'Frame','color':[.5,1,.5,1], 'brush':{'tiling':'Both'}}]})+'\n')
        changed = call('08-patch-existing-images', 'patch', PACKAGE, '--patch', patch, '--expected-sha256', stable)
        w = widgets(changed)
        gate('border-tint-preserves-texture', w['Frame']['brush']['texture'] == '/Game/Textures/T_Icon.T_Icon')
        gate('brush-partial-edit-preserves-margin', w['Frame']['brush']['margin'] == [.25]*4)
        gate('explicit-image-size-order-independent', w['Logo']['brush']['image_size'] == [48,48])
        after = preview('09-after')
        gate('image-patch-changes-pixels', compare_images(before, after)['different_pixels'] > 1000)
        reference('after', after)
        asset_hash = sha256(original)
        texture = content/'Textures/T_Photo.uasset'; old_texture = sha256(texture)
        call('10-reimport-texture', 'texture import', '/Game/Textures/T_Photo', '--input', replacement,
             '--replace', '--expected-sha256', old_texture)
        gate('reimport-preserves-blueprint-and-object-path', sha256(original) == asset_hash and sha256(texture) != old_texture)
        replaced = preview('11-reimport-preview')
        gate('texture-reimport-changes-pixels', compare_images(after, replaced)['different_pixels'] > 1000)
        reference('reimport', replaced)
        exported = (ws if toolkit else out)/'WBP_Textured.zip'
        result = call('12-export-with-textures', 'export', PACKAGE, '--output', exported)
        with zipfile.ZipFile(exported) as archive:
            index = json.loads(archive.read('assets.json'))
            gate('export-includes-native-texture-assets', len(index['files']) == 5 and
                 all(entry['path'].endswith('.uasset') for entry in index['files']))
        imported_content = ws/'reimported/Content'
        call('13-import-self-contained-zip', 'import', PACKAGE, '--input', exported, mount=imported_content)
        imported = preview('14-imported-preview', imported_content)
        gate('zip-import-renders-exactly', compare_images(replaced, imported)['different_pixels'] == 0)
        # Existing native texture asset import also retains source bytes.
        copied = call('15-import-native-texture', 'texture import', '/Game/Textures/T_Photo', '--input', texture,
                      mount=ws/'texture-copy/Content')
        gate('existing-texture-source-unchanged', copied['import_source']['unchanged'])
        invalid = ws/'missing.patch.json'
        invalid.write_text(json.dumps({'widgets':[{'name':'Title','text':'MUST NOT SAVE'},
            {'name':'Logo','brush':{'texture':'/Game/Textures/Missing'}}]})+'\n')
        call('16-reject-missing-texture', 'patch', PACKAGE, '--patch', invalid, expected=False)
        gate('invalid-brush-is-atomic', sha256(original) == asset_hash)
        stable_texture = sha256(texture)
        call('17-reject-texture-overwrite', 'texture import', '/Game/Textures/T_Photo', '--input', jpg, expected=False)
        call('18-reject-stale-reimport', 'texture import', '/Game/Textures/T_Photo', '--input', jpg,
             '--replace', '--expected-sha256', '0'*64, expected=False)
        gate('rejected-texture-writes-preserve-source', sha256(texture) == stable_texture)
        bad = ws/'not-an-image.txt'; bad.write_text('not an image')
        call('19-reject-invalid-image', 'texture import', '/Game/Textures/T_Bad', '--input', bad, expected=False)
        gate('failed-import-leaves-no-partial-asset', not (content/'Textures/T_Bad.uasset').exists())
        # Native animation must continue to address the new Image widget.
        animation = ws/'image.animation.json'
        animation.write_text(json.dumps({'name':'FadeImage','fps':60,'duration_frames':60,'tracks':[
            {'widget':'Photo','property':'opacity','interpolation':'linear',
             'keys':[{'frame':0,'value':1},{'frame':60,'value':0}]}]})+'\n')
        call('20-image-animation', 'animation create', PACKAGE, '--spec', animation)
        animated = (ws/'renders' if toolkit else out)/'animated.png'
        call('21-image-animation-preview', 'preview', PACKAGE, '--animation', 'FadeImage', '--time', '.5', '--output', animated)
        gate('image-animation-changes-pixels', compare_images(replaced, animated)['different_pixels'] > 1000)
        reference('image-animation', animated, 'FadeImage', .5)
        if native_hashes:
            gate('runtime-hosts-unchanged', all(sha256(ROOT/f'Binaries/Linux/{n}') == digest for n,digest in native_hashes.items()))
        else: report['runtime_host_hash_check'] = 'not applicable: development binaries hidden'
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'; report['error'] = repr(error)
    finally:
        if toolkit:
            subprocess.run(['bash', str(toolkit/'rive-tool'), '--workspace', str(ws), 'stop'], env=env,
                           capture_output=True, timeout=30)
    save()
    print(json.dumps({'status':report['status'], 'runs':len(report['runs']), 'gates':len(report['gates']), 'error':report.get('error')}, indent=2))
    return int(report['status'] != 'passed')


if __name__ == '__main__': raise SystemExit(main())
