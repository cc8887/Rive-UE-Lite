"""Compare Windows UE RHI/RDG pixels using two independently cooked archives."""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import subprocess
import time
from compare_png import compare_images
from package_windows import validate_shader, sha

ROOT=Path(__file__).resolve().parents[1]
class MemoryCounters(ctypes.Structure):
    _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in
        ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
         'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]

def capture(binary, root, archive, fixture, png, scenario=None, shader_directory=None, env=None):
    log=png.with_suffix('.log')
    cmd=[str(binary),'-vulkan','-sm5','-RenderOffscreen','-norhithread','-DisableAsyncCompute','-VulkanSingleQueue','-unattended','-stdout','-NoSplash',
         '-ProjectDir='+str(root)+'/', '-Input='+str(fixture),'-Output='+str(png),
         '-ShaderArchive='+str(archive),'-ShaderDirectory='+str(shader_directory or root/'Shaders'),'-abslog='+str(log)]
    if scenario: cmd+=['-Scenario='+str(scenario),'-PlaybackMetadata='+str(png.with_suffix('.playback.json'))]
    start=time.monotonic(); peak=0
    with png.with_suffix('.console.log').open('wb') as console:
        proc=subprocess.Popen(cmd,stdout=console,stderr=subprocess.STDOUT,cwd=root,env=env)
        while proc.poll() is None:
            counters=MemoryCounters(); counters.cb=ctypes.sizeof(counters)
            if ctypes.windll.psapi.GetProcessMemoryInfo(wintypes.HANDLE(int(proc._handle)),ctypes.byref(counters),counters.cb):
                peak=max(peak,counters.PeakWorkingSetSize)
            if time.monotonic()-start>180:
                proc.kill(); proc.wait(); raise RuntimeError('Capture timed out')
            time.sleep(.01)
    text=log.read_text(encoding='utf-8-sig',errors='replace') if log.exists() else ''
    marker='RiveDrawCompleted=1' if binary.stem=='RiveRhiLite' else 'engine_frender_target=1'
    passed=proc.returncode==0 and png.is_file() and marker in text and 'render_path=UE_RHI_RDG' in text and 'LogVulkanRHI:' in text
    passed=passed and not any(s in text for s in ['Ensure condition failed','Fatal error:','Assertion failed:'])
    first=re.search(r'first_image_ms=([\d.]+)',text)
    adapter=re.search(r'adapter="([^"]+)"',text)
    playback=None
    if scenario:
        path=png.with_suffix('.playback.json')
        playback=json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else None
        passed=passed and playback is not None and playback.get('status')=='completed'
    return {'passed':passed,'exit_code':proc.returncode,'wall_seconds':time.monotonic()-start,
            'peak_working_set_bytes':peak,'first_image_ms':float(first[1]) if first else None,
            'adapter':adapter[1] if adapter else None,'executable_sha256':sha(binary),'shader_sha256':sha(archive),
            'png_sha256':sha(png) if png.exists() else None,'playback':playback,'command':cmd}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--lite-shaders',type=Path,required=True)
    p.add_argument('--reference-shaders',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if os.name!='nt': p.error('Run on native Windows')
    archives=[a.lite_shaders.resolve(),a.reference_shaders.resolve()]
    for path in archives: validate_shader(path)
    if os.path.samefile(*archives): raise RuntimeError('Independent archives required')
    out=a.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    cases=[('bankcard',ROOT/'fixtures/bankcard.riv',None),
           ('animation',ROOT/'fixtures/ball_test.riv',ROOT/'fixtures/playback/bounce_animation.json'),
           ('state-machine',ROOT/'fixtures/state_machine_triggers.riv',ROOT/'fixtures/playback/trigger_transitions.json')]
    # Use the event-effect samples already specified by the shared fixture suite.
    for index,target_time in [(1,.25),(2,.5)]:
        name,fixture,scenario=cases[index]
        sample=json.loads(scenario.read_text()); sample['target_time']=target_time
        sample_path=out/(name+'-sample.json'); sample_path.write_text(json.dumps(sample))
        cases[index]=(name,fixture,sample_path)
    for name,fixture,scenario in list(cases[1:]):
        initial=json.loads(scenario.read_text()); initial['target_time']=0
        initial_path=out/(name+'-initial.json')
        initial_path.write_text(json.dumps(initial))
        cases.append((name+'-initial',fixture,initial_path))
    reports=[]
    for name,fixture,scenario in cases:
        pair=[]
        for target,archive in zip(['RiveRhiLite','RiveUeReference'],archives):
            png=out/(name+'-'+target+'.png')
            result=capture(ROOT/f'Binaries/Win64/{target}.exe',ROOT,archive,fixture,png,scenario)
            pair.append(result)
            if not result['passed']: break
        comparison=compare_images(out/(name+'-RiveUeReference.png'),out/(name+'-RiveRhiLite.png')) if len(pair)==2 and all(x['passed'] for x in pair) else {'status':'incomplete'}
        reports.append({'case':name,'captures':pair,'comparison':comparison})
        if scenario and len(pair)==2 and pair[0]['playback']!=pair[1]['playback']:
            comparison['status']='failed'; comparison['reason']='Playback metadata differs'
        if comparison['status']!='passed': break
    passed=len(reports)==len(cases) and all(x['comparison']['status']=='passed' for x in reports)
    visible_changes={}
    if passed:
        for name in ['animation','state-machine']:
            change=compare_images(out/(name+'-initial-RiveRhiLite.png'),out/(name+'-RiveRhiLite.png'))
            visible_changes[name]=change.get('different_pixels',0)>0
        passed=passed and all(visible_changes.values())
    report={'status':'passed' if passed else 'failed','cases':reports,'independent_archives':True,'visible_changes':visible_changes,
            'scope':'Windows Vulkan on recorded adapter; static, one animation and one trigger state machine; no CPU-only Windows, UMG or Verse claim'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'cases':len(reports)}))
    return 0 if passed else 1

if __name__=='__main__': raise SystemExit(main())
