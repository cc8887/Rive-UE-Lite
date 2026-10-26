#!/usr/bin/env python3
"""Compare public CLI previews to native source-tree previews with a separate cook."""
from pathlib import Path
import argparse
import json
import os
import re
import shutil
import subprocess

from compare_png import compare_images, sha256

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--roundtrip', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    a = p.parse_args()
    if os.environ.get('RIVE_UE_LITE_GPU_DEVICES_HIDDEN') != '1': p.error('Use measure_no_gpu.sh')
    out, run = a.output_dir.resolve(), a.roundtrip.resolve()
    if out.exists(): p.error('Use a fresh directory')
    out.mkdir(parents=True)
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    original = out/'original/Content/UI/WBP_Card.uasset'
    original.parent.mkdir(parents=True)
    shutil.copy2(run/'04-patch/backup/WBP_Card.uasset', original)
    host_archive = ROOT/'artifacts/umg-blueprint/shaders-host/global.bin'
    reference_archive = ROOT/'artifacts/umg-blueprint/shaders-reference/global.bin'
    executions = [json.loads((path.parent/'provenance/provenance.json').read_text())['cook_execution']['execution_id']
        for path in [host_archive, reference_archive]]
    assert len(set(executions)) == 2
    env = dict(os.environ, VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/lvp_icd.json',
        VK_DRIVER_FILES='/usr/share/vulkan/icd.d/lvp_icd.json', SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', LP_NUM_THREADS='2')
    report = {'status': 'incomplete', 'scope': 'source-tree designer API vs saved generated-class instance, two independent native shader cooks; not a complete editor or UEFN screenshot',
        'native_cook_execution_ids': executions, 'pairs': [], 'archive_sha256': {str(p): sha256(p) for p in [host_archive, reference_archive]}}
    try:
        for name, content, png in [('before', out/'original/Content', run/'before.png'), ('after', run/'new/Content', run/'after.png')]:
            dest = out/name; dest.mkdir()
            command = [str(ROOT/'Binaries/Linux/RiveUmgBlueprintWorker'), '-unattended', '-stdout', '-vulkan', '-sm5', '-AllowCPUDevices',
                '-AllowCommandletRendering', '-RenderOffscreen', '-norhithread', '-Mode=render', '-NativeDesignerReference',
                f'-ProjectDir={ROOT}/', f'-ContentDir={content}', '-Asset=/Game/UI/WBP_Card', f'-UserDir={dest}/user/',
                f'-Output={dest}/output.png', f'-Metadata={dest}/asset.json', f'-ShaderArchive={reference_archive}']
            with (dest/'worker.log').open('wb') as log:
                result = subprocess.run(command, cwd='/tmp', env=env, stdout=log, stderr=subprocess.STDOUT, timeout=120)
            text = (dest/'worker.log').read_text(errors='replace')
            meta = json.loads((dest/'asset.json').read_text())
            assert result.returncode == 0 and 'UMG_BP_TEARDOWN complete' in text
            assert not re.search(r'Ensure condition failed:|Fatal error:|Log\w+: Error:', text)
            assert not meta['using_null_rhi'] and 'llvmpipe' in meta['adapter'].lower()
            comparison = compare_images(dest/'output.png', png)
            report['pairs'].append({'state': name, 'command': command, 'comparison': comparison})
            assert comparison['different_pixels'] == 0
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'; report['error'] = repr(error)
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'status': report['status'], 'pairs': len(report['pairs']), 'error': report.get('error')}))
    return 0 if report['status'] == 'passed' else 1

if __name__ == '__main__': raise SystemExit(main())
