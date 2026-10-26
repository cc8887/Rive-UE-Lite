#!/usr/bin/env python3
"""Force a native failure after SavePackage and verify the CLI restores the asset."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import time

from compare_png import sha256

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--content-dir', type=Path, required=True)
    p.add_argument('--asset', required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--texture-input', type=Path, help='Test native Texture2D save instead of Blueprint patch')
    p.add_argument('--create-texture', action='store_true', help='Test cleanup of a newly created texture after a post-save failure')
    a = p.parse_args()
    out, content = a.output_dir.resolve(), a.content_dir.resolve()
    if out.exists(): p.error('Use a fresh directory')
    if not content.is_relative_to(ROOT) or not out.is_relative_to(ROOT): p.error('Keep the test inside this prototype')
    out.mkdir(parents=True)
    asset = content/(a.asset.removeprefix('/Game/')+'.uasset')
    if a.create_texture and not a.texture_input: p.error('--create-texture requires --texture-input')
    if a.create_texture and asset.exists(): p.error('New texture must not already exist')
    before = sha256(asset) if asset.is_file() else None
    patch = out/'patch.json'; patch.write_text(json.dumps({'widgets': [{'name':'Title','text':'POST-SAVE FAILURE MUST BE RESTORED'}]})+'\n')
    job = out/'job'
    operation = ['texture', 'import', '--input', str(a.texture_input.resolve())] if a.texture_input else ['patch', '--patch', str(patch)]
    if a.texture_input and not a.create_texture: operation += ['--replace']
    command = [sys.executable, '-B', str(ROOT/'scripts/widget_bp.py'), *operation, '--content-dir', str(content),
        '--asset', a.asset, '--report-dir', str(job)]
    with (out/'console.log').open('wb') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        deadline = time.monotonic()+20
        while not job.is_dir() and process.poll() is None and time.monotonic() < deadline: time.sleep(.01)
        assert job.is_dir()
        # The native operation saves the source first and writes metadata last.
        # A directory at the metadata filename makes that final write fail.
        (job/'asset.json').mkdir()
        process.wait(timeout=180)
    result = json.loads((job/'report.json').read_text())
    text = (job/'worker.log').read_text(errors='replace')
    assert process.returncode != 0 and result['status'] == 'failed'
    assert ('UMG_TEXTURE_SAVE' if a.texture_input else 'UMG_BP_SAVE ok=1') in text and result.get('exit_code') == 8
    assert (not asset.exists()) if a.create_texture else (result.get('restored_backup') and sha256(asset) == before)
    report = {'status':'passed','scope':'real successful native save followed by metadata write failure; backup restored or new asset removed',
        'native_exit_code':result['exit_code'],'original_sha256':before,'restored_sha256':sha256(asset) if asset.exists() else None,
        'new_asset_removed':a.create_texture and not asset.exists(),
        'source_asset':str(asset),'evidence':str(job/'report.json')}
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__': main()
