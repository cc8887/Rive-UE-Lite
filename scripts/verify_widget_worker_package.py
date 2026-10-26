#!/usr/bin/env python3
"""Run an actual package with native development resources/GPU hidden."""
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
from compare_png import sha256

ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--animation')
    a=p.parse_args(); package=a.package.resolve(); out=a.output_dir.resolve()
    if out.exists(): p.error('Use a fresh directory')
    if os.environ.get('RIVE_UE_LITE_GPU_DEVICES_HIDDEN')!='1' or (ROOT/'engine/Engine/Config/Base.ini').exists():
        p.error('Run under isolated_widget_worker.sh')
    out.mkdir(parents=True); os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:2])
    manifest=json.loads((package/'package-manifest.json').read_text())
    before={f['path']:sha256(package/f['path']) for f in manifest['files']}
    assert all(before[f['path']]==f['sha256'] for f in manifest['files'])
    env=dict(os.environ,LP_NUM_THREADS='2',MESA_SHADER_CACHE_DIR=str(out/'mesa-cache'))
    command=['bash',str(package/'worker.sh'),'-Mode=render','-vulkan','-sm5','-AllowCPUDevices','-AllowCommandletRendering',
        '-RenderOffscreen','-norhithread',f'-ContentDir={package}/Content','-Asset=/Game/UI/WBP_Card',
        f'-ShaderArchive={package}/shaders/global.bin',f'-Output={out}/frame.png',f'-Metadata={out}/asset.json',f'-UserDir={out}/user/']
    if a.animation: command+=['-Animation='+a.animation,'-AnimationTime=0.5']
    with (out/'worker.log').open('wb') as log:
        result=subprocess.run(command,env=env,cwd='/tmp',stdout=log,stderr=subprocess.STDOUT,timeout=240)
    text=(out/'worker.log').read_text(errors='replace')
    meta=json.loads((out/'asset.json').read_text()) if (out/'asset.json').is_file() else {}
    gates={'normal_exit':result.returncode==0 and 'UMG_BP_TEARDOWN complete' in text,
        'no_runtime_errors':not re.search(r'Ensure condition failed:|Fatal error:|Log\w+: Error:',text),
        'cpu_vulkan':meta.get('using_null_rhi') is False and 'llvmpipe' in meta.get('adapter','').lower(),
        'gpu_nodes_hidden':not any(Path(p).exists() for p in ['/dev/dxg','/dev/dri']),
        'development_engine_hidden':not (ROOT/'engine/Engine/Config/Base.ini').exists(),
        'actual_png':(out/'frame.png').is_file(),
        'declared_payload_unchanged':all(sha256(package/rel)==digest for rel,digest in before.items())}
    if a.animation:
        play=meta.get('animation_playback',{}); snapshots=play.get('snapshots',[])
        gates['actual_animation_evaluated']=bool(snapshots and any(abs(w['opacity']-.5)<1e-4 for w in snapshots[-1]['widgets']))
        gates['worldless']=play.get('world_is_null') is True
    report={'status':'passed' if all(gates.values()) else 'failed','gates':gates,'command':command,
        'exit_code':result.returncode,'package_manifest_sha256':sha256(package/'package-manifest.json'),
        'png_sha256':sha256(out/'frame.png') if (out/'frame.png').is_file() else None}
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2))
    return int(report['status']!='passed')


if __name__=='__main__': raise SystemExit(main())
