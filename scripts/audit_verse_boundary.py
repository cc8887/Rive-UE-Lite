#!/usr/bin/env python3
"""Audit actual optional-worker and default-Rive build/package boundaries."""
from pathlib import Path
import argparse
import json
import re
import subprocess

from compare_png import sha256
from measure_ue_lite import inspect_build

ROOT = Path(__file__).resolve().parents[1]

def inspect(target):
    folder = ROOT/f'Intermediate/Build/Linux/x64/{target}/Development'
    link = folder/f'{target}.link.rsp'
    linkage = inspect_build([ROOT/f'Binaries/Linux/{target}.target'], [link], ROOT/f'Binaries/Linux/{target}')
    # Follow the actual compile response files and their shared includes;
    # do not infer modules from stale generated directories from failed builds.
    responses, headers = {}, {}
    def expand(path):
        if path in responses: return
        text = path.read_text(errors='replace'); responses[path] = text
        for nested in re.findall(r'@"([^"]+)"', text): expand(Path(nested))
        for header in re.findall(r'-include(?:-pch)?\s+"([^"]+)"', text):
            path = Path(header.removesuffix('.gch'))
            if path.is_file(): headers[path] = path.read_text(errors='replace')
    for rsp in folder.rglob('*.o.rsp'): expand(rsp)
    definitions = {}
    for name in ['WITH_ENGINE', 'WITH_VERSE_VM', 'WITH_VERSE_BPVM', 'WITH_VERSE_COMPILER']:
        values = set()
        for text in [*responses.values(), *headers.values()]:
            values.update(re.findall(rf'(?:#define\s+{name}\s+|-D{name}=)([01])\b', text))
        definitions[name] = sorted(values)
    return {'linkage': linkage, 'definitions': definitions,
        'compile_response_files': [{'path': str(p), 'sha256': sha256(p)} for p in responses],
        'included_headers': [{'path': str(p), 'sha256': sha256(p)} for p in headers]}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--default-package', type=Path, default=ROOT/'package/ui-rive-01')
    p.add_argument('--verse-package', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    default, worker = inspect('RiveRhiLite'), inspect('RiveVerseWorker')
    default_forbidden = {'Engine', 'Renderer', 'UMG', 'Slate', 'SlateCore', 'VerseCompiler',
        'VerseNative', 'Verse', 'VerseVMCodeGen', 'Solaris', 'libpas', 'RiveVerseWorker'}
    worker_forbidden = {'Engine', 'Renderer', 'UMG', 'Slate', 'SlateCore', 'RHI', 'VulkanRHI'}
    default['leaked_modules'] = sorted(default_forbidden & set(default['linkage']['recognized_modules']))
    worker['leaked_modules'] = sorted(worker_forbidden & set(worker['linkage']['recognized_modules']))
    default_manifest = json.loads((a.default_package/'package-manifest.json').read_text())
    default_files = [str(f.relative_to(a.default_package)) for f in a.default_package.rglob('*') if f.is_file()]
    leaked_files = [name for name in default_files if any(part in {'RiveVerseWorker', 'VerseNative', 'VerseVM', 'UMG', 'Slate'} for part in Path(name).parts)]
    worker_path = a.verse_package/'worker/Binaries/Linux/RiveVerseWorker'
    plans = {}
    for name, flags in [('default', []), ('verse', ['--with-verse']), ('umg_verse', ['--with-umg', '--with-verse'])]:
        plans[name] = subprocess.check_output(['bash', str(ROOT/'scripts/build_ui.sh'), *flags, '--plan'], text=True)
    before = json.loads((ROOT/'artifacts/verse-vm/render-binaries-before-default.json').read_text(encoding='utf-8-sig'))
    preserved = {target: digest == sha256(ROOT/f'Binaries/Linux/{target}') for target, digest in before.items()}
    expected_default = {'WITH_ENGINE': ['0'], 'WITH_VERSE_VM': ['0'], 'WITH_VERSE_BPVM': ['1'], 'WITH_VERSE_COMPILER': ['0']}
    expected_worker = {'WITH_ENGINE': ['0'], 'WITH_VERSE_VM': ['1'], 'WITH_VERSE_BPVM': ['0'], 'WITH_VERSE_COMPILER': ['1']}
    gates = {
        'default_actual_modules_excluded': not default['leaked_modules'],
        'default_compile_flags': default['definitions'] == expected_default,
        'worker_actual_modules_excluded': not worker['leaked_modules'],
        'worker_compile_flags': worker['definitions'] == expected_worker,
        'default_package_excludes_optional_content': not leaked_files and default_manifest['capabilities'] == {'rive': True, 'umg': False},
        'packaged_rive_matches_default_binary': sha256(a.verse_package/'Engine/Binaries/Linux/RiveRhiLite') == sha256(ROOT/'Binaries/Linux/RiveRhiLite'),
        'packaged_worker_matches_built_worker': sha256(worker_path) == sha256(ROOT/'Binaries/Linux/RiveVerseWorker'),
        'render_binaries_preserved': all(preserved.values()),
        'default_plan_has_no_worker': 'RIVE_VERSE_BUILD' not in plans['default'] and 'target=RiveRhiLite' in plans['default'],
        'optional_plans': 'target=RiveVerseWorker' in plans['verse'] and 'target=RiveUmgHost' in plans['umg_verse']}
    report = {'status': 'passed' if all(gates.values()) else 'failed', 'gates': gates,
        'default': default, 'worker': worker, 'plans': plans, 'preserved_binaries': preserved,
        'default_package_leaked_files': leaked_files,
        'note': 'Existing default CoreUObject BPVM foundation is not a usable Verse environment; new Verse runtime/compiler/worker are excluded.'}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'status': report['status'], 'gates': gates, 'default_flags': default['definitions'], 'worker_flags': worker['definitions']}, indent=2))
    return 0 if report['status'] == 'passed' else 1

if __name__ == '__main__':
    raise SystemExit(main())
