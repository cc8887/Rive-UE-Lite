#!/usr/bin/env python3
"""Fail closed unless actual Mac Lite link/compile evidence excludes heavy modules."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from measure_ue_lite import inspect_build

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {'Engine', 'Renderer', 'UMG', 'Slate', 'SlateCore', 'RiveUmgHost',
             'VerseCompiler', 'VerseNative', 'VerseVMCodeGen', 'Solaris', 'libpas', 'VulkanRHI'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(arch, receipt_path, link_path):
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('TargetName') != 'RiveRhiLite' or receipt.get('Platform') != 'Mac':
        raise RuntimeError('Need a Mac RiveRhiLite receipt')
    def expand(name):
        return Path(name.replace('$(EngineDir)', str(ROOT/'engine/Engine')).replace('$(ProjectDir)', str(ROOT)))
    binaries = [expand(p['Path']) for p in receipt['BuildProducts'] if p['Type'] == 'Executable']
    if len(binaries) != 1 or not binaries[0].is_file():
        raise RuntimeError('Need the actual built Mac executable')
    executable = binaries[0]
    linkage = inspect_build([receipt_path], [link_path], executable)
    modules = set(linkage['recognized_modules'])
    intermediates = ROOT/f'Intermediate/Build/Mac/{arch}/RiveRhiLite/Development'
    evidence, seen, errors = {}, set(), []
    def read(path):
        path = path.resolve()
        if path in seen: return
        seen.add(path)
        if not path.is_file():
            errors.append('Missing referenced response/header: '+str(path)); return
        text = path.read_text(errors='replace')
        evidence[path] = text
        for nested in re.findall(r'@"([^"]+)"', text):
            child = Path(nested)
            read(child if child.is_absolute() else path.parent/child)
        for header in re.findall(r'-include(?:-pch)?\s+"([^"]+)"', text):
            child = Path(header.removesuffix('.gch').removesuffix('.pch'))
            read(child if child.is_absolute() else path.parent/child)
    for rsp in intermediates.rglob('*.o.rsp'):
        read(rsp)
    definitions = {}
    for name in ['WITH_ENGINE', 'WITH_VERSE_VM', 'WITH_VERSE_COMPILER']:
        definitions[name] = sorted({m for text in evidence.values()
            for m in re.findall(rf'(?:#define\s+{name}\s+|-D{name}=)([01])\b', text)})
    arch_text = subprocess.check_output(['xcrun', 'lipo', '-archs', str(executable)], text=True).strip()
    checks = {'linkage': linkage['status'] == 'passed', 'metal_linked': 'MetalRHI' in modules,
              'heavy_modules_excluded': not (modules & FORBIDDEN),
              'compile_definitions': definitions == {'WITH_ENGINE': ['0'], 'WITH_VERSE_VM': ['0'], 'WITH_VERSE_COMPILER': ['0']},
              'responses_present': bool(evidence) and not errors,
              'architecture': arch_text == ('arm64' if arch == 'arm64' else 'x86_64')}
    return {'status': 'passed' if all(checks.values()) else 'failed', 'checks': checks,
            'architecture': arch, 'executable': str(executable), 'executable_sha256': sha(executable),
            'receipt_sha256': sha(receipt_path), 'linkage': linkage, 'definitions': definitions,
            'errors': errors, 'compile_evidence': [{'path': str(p), 'sha256': sha(p)} for p in evidence],
            'scope': 'actual binary and build boundary; Metal pixels require separate runtime comparison'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arch', choices=['arm64', 'x64'], default='arm64')
    parser.add_argument('--receipt', type=Path, default=ROOT/'Binaries/Mac/RiveRhiLite.target')
    parser.add_argument('--link-response', type=Path)
    args = parser.parse_args()
    link = args.link_response or ROOT/f'Intermediate/Build/Mac/{args.arch}/RiveRhiLite/Development/RiveRhiLite.rsp'
    report = audit(args.arch, args.receipt, link)
    output = ROOT/f'artifacts/macos/boundary-{args.arch}.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report['checks'], indent=2))
    raise SystemExit(0 if report['status'] == 'passed' else 1)
