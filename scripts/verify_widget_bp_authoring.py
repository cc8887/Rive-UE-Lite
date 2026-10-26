#!/usr/bin/env python3
"""Exercise the public CLI, including existing binary assets and graph preservation."""
from pathlib import Path
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import zipfile

from compare_png import compare_images, sha256

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    out = a.output_dir.resolve()
    if out.exists(): p.error('Use a fresh directory')
    if os.environ.get('RIVE_UE_LITE_GPU_DEVICES_HIDDEN') != '1': p.error('Run under measure_no_gpu.sh')
    out.mkdir(parents=True)
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', LP_NUM_THREADS='2')
    report = {'status': 'incomplete', 'scope': 'native source WBP CLI, typed widget creation/properties and existing graph/variable preservation; no arbitrary graph editing or UEFN acceptance', 'runs': []}
    before_binaries = {n: sha256(ROOT/f'Binaries/Linux/{n}') for n in ['RiveRhiLite', 'RiveUmgHost', 'RiveVerseWorker']}
    def save(): (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    def cli(name, command, content, asset, *extra, expected=True):
        dest = out/name
        cmd = [sys.executable, '-B', str(ROOT/'scripts/widget_bp.py'), command, '--content-dir', str(content),
            '--asset', asset, '--report-dir', str(dest), *map(str, extra)]
        with (out/f'{name}.console.log').open('wb') as log:
            process = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        result = json.loads((dest/'report.json').read_text())
        report['runs'].append({'name': name, 'exit_code': process.returncode, 'status': result['status'], 'report': str(dest/'report.json')})
        save()
        assert (process.returncode == 0) == expected, (name, result.get('error'))
        assert result['status'] == ('passed' if expected else 'failed')
        return result
    def widgets(result): return {x['name']: x for x in result['metadata']['widgets']}
    try:
        # Create an arbitrary typed WidgetTree through the same public entry.
        content = out/'new/Content'; package = '/Game/UI/WBP_Card'
        created = cli('01-create', 'create', content, package, '--spec', ROOT/'fixtures/widget-blueprint/card.json')
        assert created['metadata']['asset_class'] == '/Script/UMGEditor.WidgetBlueprint'
        assert len(widgets(created)) == 7 and widgets(created)['ConfirmLabel']['parent'] == 'Confirm'
        original = content/'UI/WBP_Card.uasset'
        first_hash = sha256(original)
        read = cli('02-read', 'read', content, package)
        assert sha256(original) == first_hash
        cli('03-preview', 'preview', content, package, '--output', out/'before.png')
        changed = cli('04-patch', 'patch', content, package, '--patch', ROOT/'fixtures/widget-blueprint/card.patch.json', '--expected-sha256', first_hash)
        assert sha256(original) != first_hash
        assert widgets(changed)['Title']['text'] == 'Loaded, edited and saved'
        assert widgets(changed)['Title']['font_size'] == 28
        after = cli('05-read-reload', 'read', content, package)
        assert widgets(after) == widgets(changed)
        cli('06-preview-reload', 'preview', content, package, '--output', out/'after.png')
        report['visible_edit'] = compare_images(out/'before.png', out/'after.png')
        assert report['visible_edit']['different_pixels'] > 0
        # Seed a source asset with real nonempty graphs, connected pins and a
        # member variable. Import that binary; do not rebuild it from JSON.
        seed = out/'existing-source/Content'; seed.mkdir(parents=True)
        seed_meta = out/'seed.json'
        seed_cmd = [str(ROOT/'Binaries/Linux/RiveUmgBlueprintWorker'), '-unattended', '-stdout', '-Mode=create',
            f'-ProjectDir={ROOT}/', f'-ContentDir={seed}', '-Asset=/Game/UI/WBP_Existing', '-PreservationFixture', f'-Metadata={seed_meta}']
        with (out/'seed.log').open('wb') as log:
            process = subprocess.run(seed_cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        assert process.returncode == 0
        source = seed/'UI/WBP_Existing.uasset'; source_hash = sha256(source)
        imported_content = out/'imported/Content'; existing = '/Game/UI/WBP_Existing'
        imported = cli('07-import-existing', 'import', imported_content, existing, '--input', source)
        assert imported['import_source']['unchanged'] and sha256(source) == source_hash
        inspected = cli('08-read-existing', 'read', imported_content, existing)
        graph_before = inspected['metadata']['graphs']; variables_before = inspected['metadata']['variables']
        assert sum(len(g['nodes']) for g in graph_before) >= 2
        assert sum(len(pin['links']) for g in graph_before for n in g['nodes'] for pin in n['pins']) >= 2
        assert any(v['name'] == 'PreservedCounter' and v['default'] == '41' for v in variables_before)
        existing_patch = out/'existing.patch.json'
        existing_patch.write_text(json.dumps({'widgets': [
            {'name': 'Title', 'text': 'Edited existing source Blueprint', 'font_size': 23, 'position': [72, 36], 'size': [500, 44], 'color': [.6,.9,.8,1], 'is_variable': True},
            {'name': 'Badge', 'padding': [8,4,8,4], 'color': [.3,.15,.4,1], 'opacity': .8}
        ]})+'\n')
        patched = cli('09-edit-existing', 'patch', imported_content, existing, '--patch', existing_patch)
        reloaded = cli('10-reload-existing', 'read', imported_content, existing)
        assert patched['metadata']['graphs'] == graph_before == reloaded['metadata']['graphs']
        assert patched['metadata']['variables'] == variables_before == reloaded['metadata']['variables']
        old, new = widgets(inspected), widgets(reloaded)
        for name in old.keys()-{'Title','Badge'}: assert old[name] == new[name], name
        assert new['Title']['text'] == 'Edited existing source Blueprint' and new['Title']['is_variable']
        assert new['Badge']['padding'] == [8,4,8,4]
        report['existing_asset'] = {'source_unchanged': sha256(source) == source_hash, 'graphs_preserved': True,
            'node_count': sum(len(g['nodes']) for g in graph_before), 'variables_preserved': True, 'untouched_widgets_preserved': True}
        exported = cli('11-export', 'export', imported_content, existing, '--output', out/'WBP_Existing-edited.zip')
        asset = imported_content/'UI/WBP_Existing.uasset'
        with zipfile.ZipFile(out/'WBP_Existing-edited.zip') as archive:
            assert hashlib.sha256(archive.read('Content/UI/WBP_Existing.uasset')).hexdigest() == sha256(asset)
        # Complete request validation must prevent partial disk edits.
        rejected_patch = out/'invalid.patch.json'
        rejected_patch.write_text(json.dumps({'widgets': [{'name':'Title','text':'MUST NOT SAVE'}, {'name':'NoSuchWidget','text':'invalid'}]})+'\n')
        stable = sha256(asset)
        cli('12-reject-atomic', 'patch', imported_content, existing, '--patch', rejected_patch, expected=False)
        assert sha256(asset) == stable
        cli('13-reject-stale', 'patch', imported_content, existing, '--patch', existing_patch, '--expected-sha256', '0'*64, expected=False)
        assert sha256(asset) == stable
        cli('14-reject-overwrite', 'create', content, package, '--spec', ROOT/'fixtures/widget-blueprint/card.json', expected=False)
        assert widgets(cli('15-read-after-rejections', 'read', imported_content, existing))['Title']['text'] == 'Edited existing source Blueprint'
        # Unicode metadata must remain UTF-8, independent of FileHelper's auto mode.
        unicode_patch = out/'unicode.patch.json'
        unicode_patch.write_text(json.dumps({'widgets':[{'name':'Title','text':'读取并修改蓝图'}]}, ensure_ascii=False)+'\n')
        cli('16-unicode-write', 'patch', imported_content, existing, '--patch', unicode_patch)
        assert widgets(cli('17-unicode-read', 'read', imported_content, existing))['Title']['text'] == '读取并修改蓝图'
        report['unicode_source_roundtrip'] = True
        report['render_binaries_unchanged'] = all(sha256(ROOT/f'Binaries/Linux/{n}') == digest for n, digest in before_binaries.items())
        assert report['render_binaries_unchanged']
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'; report['error'] = str(error)
    save()
    print(json.dumps({'status': report['status'], 'runs': len(report['runs']), 'error': report.get('error')}, indent=2))
    return 0 if report['status'] == 'passed' else 1

if __name__ == '__main__': raise SystemExit(main())
