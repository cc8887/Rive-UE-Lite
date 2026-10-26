#!/usr/bin/env python3
"""Execute native UMG/Rive captures from a deployed host and an independent UE reference."""
from pathlib import Path
import argparse
import json
import os
import platform
import re

from compare_png import compare_images, sha256
from measure_ue_lite import run_once, apply_cpu_profile

ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', type=Path, required=True)
    p.add_argument('--native-archive', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--cpu-limit', type=int, default=2)
    a = p.parse_args()
    if platform.system() != 'Linux' or os.environ.get('RIVE_UE_LITE_GPU_DEVICES_HIDDEN') != '1':
        p.error('Execute under scripts/measure_no_gpu.sh')
    out, package, native_archive = a.output_dir.resolve(), a.package.resolve(), a.native_archive.resolve()
    if out.exists() and any(out.iterdir()): p.error('Use a fresh output directory')
    out.mkdir(parents=True, exist_ok=True)
    report = {'status':'incomplete', 'scope':'native worldless UMG Program, Rive custom Slate element, CPU Vulkan; not Editor viewport or UI materials',
        'gpu_namespace':os.environ['RIVE_UE_LITE_MOUNT_NAMESPACE'], 'gpu_nodes': {n:Path(n).exists() for n in ['/dev/dxg','/dev/dri']},
        'host_archive':{'path':str(package/'shaders/global.bin'), 'sha256':sha256(package/'shaders/global.bin')},
        'reference_archive':{'path':str(native_archive), 'sha256':sha256(native_archive)}, 'runs':[], 'pairs':[]}
    assert native_archive != (package/'shaders/global.bin').resolve()
    env = dict(os.environ, VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/lvp_icd.json', VK_DRIVER_FILES='/usr/share/vulkan/icd.d/lvp_icd.json',
        SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', LC_ALL='C', LANG='C')
    report['cpu_profile'] = apply_cpu_profile(a.cpu_limit, a.cpu_limit, env)
    cases = [
        ('bounce-0','ball_test.riv',0.,False),
        ('bounce-075','ball_test.riv',.75,False),
        ('bounce-hidden','ball_test.riv',.75,True),
        ('bankcard','input.riv',0.,False),
        ('rocket-idle','rocket.riv',0.,False),
        ('rocket-pressed','rocket.riv',1.,False),
    ]
    try:
        for name, fixture, time, hidden in cases:
            images = {}
            for side in ['host','reference']:
                dest=out/name/side;dest.mkdir(parents=True)
                png=dest/'output.png'
                meta=dest/'playback.json'
                runenv=dict(env, MESA_SHADER_CACHE_DIR=str(dest/'mesa-cache'))
                common=['-Ui=umg','-Width=512','-Height=512']
                if fixture in ('ball_test.riv','rocket.riv'):
                    scenario_name='bounce_animation' if fixture=='ball_test.riv' else 'rocket_bool'
                    common += [f'-Scenario={package}/fixtures/playback/{scenario_name}.json']
                    scenario=json.loads((package/f'fixtures/playback/{scenario_name}.json').read_text())
                    scenario['target_time']=time
                    (dest/'scenario.json').write_text(json.dumps(scenario)+'\n')
                    common[-1]=f'-Scenario={dest}/scenario.json'
                else: common += [f'-Seconds={time}']
                if hidden: common += ['-HideRive']
                else: common += [f'-PlaybackMetadata={meta}']
                if side=='host':
                    exe=Path('/bin/bash')
                    args=[str(package/'render.sh'),str(package/'fixtures'/fixture),'{output}',*common]
                else:
                    exe=ROOT/'Binaries/Linux/RiveUeReference'
                    args=['-vulkan','-sm5','-AllowCPUDevices','-RenderOffscreen','-norhithread','-unattended','-stdout',
                        f'-ProjectDir={ROOT}/',f'-UserDir={dest}/user/',f'-Input={package}/fixtures/{fixture}',
                        '-Output={output}',f'-ShaderArchive={native_archive}',f'-ShaderDirectory={ROOT}/Shaders',*common]
                result=run_once(exe,args,png,0,dest,runenv,180,Path('/tmp'))
                result.update(case=name,side=side)
                text=(dest/'run-000.log').read_text(errors='replace')
                result['umg_completion_marker'] = 'umg_composite=1' in text
                result['native_widget_tree'] = 'root=CanvasPanel button=Button rive_host=NativeWidgetHost' in text
                result['runtime_errors'] = re.findall(r'^.*(?:Log\w+: Error:|Ensure condition failed:|Fatal error:).*$',text,re.M)
                result['scope']='actual UMG FWidgetRenderer capture, includes native Rive draw unless hidden'
                if (not result['umg_completion_marker'] or not result['native_widget_tree'] or result['runtime_errors']
                    or result['runtime_device']['status']!='passed'): result['status']='failed'
                report['runs'].append(result)
                images[side]=png
                if result['status']!='passed': raise RuntimeError(f'{name}/{side} failed; see {dest}')
            comparison=compare_images(images['reference'],images['host'])
            report['pairs'].append({'case':name,**comparison})
            if comparison['status']!='passed': raise RuntimeError(f'Pixel mismatch: {name}')
            if not hidden:
                hm=json.loads((out/name/'host/playback.json').read_text())
                rm=json.loads((out/name/'reference/playback.json').read_text())
                if hm!=rm: raise RuntimeError(f'Playback metadata differs: {name}')
        report['animation_difference']=compare_images(out/'bounce-0/host/output.png',out/'bounce-075/host/output.png')
        report['rive_visibility_difference']=compare_images(out/'bounce-075/host/output.png',out/'bounce-hidden/host/output.png')
        report['state_machine_difference']=compare_images(out/'rocket-idle/host/output.png',out/'rocket-pressed/host/output.png')
        assert report['animation_difference']['different_pixels']>0
        assert report['rive_visibility_difference']['different_pixels']>0
        assert report['state_machine_difference']['different_pixels']>0
        report['status']='passed'
    except Exception as e:
        report['status']='failed'; report['error']=str(e)
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'runs':len(report['runs']),'pairs':len(report['pairs']),'error':report.get('error')},indent=2))
    return 0 if report['status']=='passed' else 1

if __name__=='__main__': raise SystemExit(main())
