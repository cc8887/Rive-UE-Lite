#!/usr/bin/env python3
"""Verify every selected Runtime GitDependencies payload against its pin."""
from pathlib import Path
import hashlib
import json

root = Path(__file__).resolve().parents[2]
staging = json.loads((root / 'artifacts/setup/dependency-staging.json').read_text())
files = []
for entry in staging['files']:
    if not entry['path'].startswith('Engine/Source/Runtime/'):
        continue
    path = root / 'engine' / entry['path']
    actual = hashlib.sha1(path.read_bytes()).hexdigest() if path.is_file() else None
    files.append({'path': entry['path'], 'expected_sha1': entry['expected_sha1'],
                  'actual_sha1': actual, 'bytes': path.stat().st_size if path.is_file() else 0,
                  'passed': actual == entry['expected_sha1']})
report = {'scope': 'selected Runtime GitDependencies file closure, not runtime rendering acceptance',
          'status': 'passed' if files and all(f['passed'] for f in files) else 'failed',
          'selected_files': len(files), 'actual_total_bytes': sum(f['bytes'] for f in files),
          'files': files}
path = root / 'artifacts/setup/reference-runtime-dependencies.json'
path.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'files'}))
raise SystemExit(0 if report['status'] == 'passed' else 1)
