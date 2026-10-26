#!/usr/bin/env python3
"""Apply the pinned Metal offscreen patch to this prototype's engine only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PIN = "62d7c1a7125b52b10ee1b714838f515f3563f795"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Require patch already applied")
    parser.add_argument("--with-tools", action="store_true", help="Also apply the existing native cooker patch stack")
    args = parser.parse_args()
    engine = ROOT / "engine"
    def git(*options, env=None):
        return subprocess.run(["git", "-C", str(engine), *options], capture_output=True, text=True, encoding='utf-8', env=env)
    head = git("rev-parse", "HEAD")
    if head.returncode or head.stdout.strip() != PIN:
        raise SystemExit("Mac patch requires the prototype's pinned UE checkout; refusing another revision")
    patches = sorted((ROOT/'prototype/patches').glob('[0-9][0-9][0-9][0-9]-*.patch')) if args.with_tools else [ROOT/'prototype/patches/0008-metalrhi-offscreen-without-engine.patch']
    entries = [{'patch': p.name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in patches]
    paths = sorted({m for p in patches for m in re.findall(r'^\+\+\+ b/(.+)$', p.read_text(encoding='utf-8'), re.M)})
    output = ROOT / 'artifacts/macos/prepare.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    changes = []
    # Later patches overlap earlier hunks. Reconstruct the final stack in a
    # private index instead of reverse-checking each old patch against that tree.
    with tempfile.TemporaryDirectory(prefix='patch-index-', dir=output.parent) as folder:
        env = {**os.environ, 'GIT_INDEX_FILE': str(Path(folder)/'index')}
        result = git('read-tree', 'HEAD', env=env)
        if result.returncode: raise SystemExit(result.stderr)
        for patch in patches:
            result = git('apply', '--cached', str(patch), env=env)
            if result.returncode: raise SystemExit('Patch stack mismatch: '+patch.name+'\n'+result.stderr)
        for name in paths:
            path = (engine/name).resolve()
            if not path.is_relative_to(engine.resolve()): raise SystemExit('Patch escapes prototype engine')
            base, desired = git('show', 'HEAD:'+name), git('show', ':'+name, env=env)
            if desired.returncode: raise SystemExit('Cannot read patch source: '+name)
            current = path.read_text(encoding='utf-8') if path.is_file() else None
            if current == desired.stdout: continue
            if current != (base.stdout if base.returncode == 0 else None):
                raise SystemExit('Preserving conflicting local source: '+name)
            changes.append((path, desired.stdout))
        if args.check and changes:
            raise SystemExit('Required patch stack is not applied: '+', '.join(str(p.relative_to(engine)) for p, _ in changes))
        for path, text in changes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8', newline='\n')
    report = {"engine_commit": PIN, 'patches': entries, 'status': 'applied' if changes else 'already_applied',
              'changed_files': [str(p.relative_to(engine)) for p, _ in changes],
              "scope": "source adaptation only; not Mac compile/runtime acceptance"}
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
