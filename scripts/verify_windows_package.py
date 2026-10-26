"""Run a fresh Windows package with development engine/vendor paths hidden."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from compare_png import compare_images
from verify_windows import capture

ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    package=a.package.resolve(); out=a.output.resolve()
    if not package.is_relative_to(ROOT) or not out.is_relative_to(ROOT): raise RuntimeError('Stay inside independent prototype')
    if out.exists(): raise RuntimeError('Use a fresh verification directory')
    out.mkdir(parents=True)
    (out/'temp').mkdir()
    env={**os.environ,'PATH':os.environ['SystemRoot']+'\\System32','TEMP':str(out/'temp'),'TMP':str(out/'temp')}
    for name in ['UE_SDKS_ROOT','RIVE_LITE_NATIVE_LIB_DIR','RIVE_LITE_INCLUDE_DIR']: env.pop(name,None)
    moved=[]; captures=[]; checks={}
    try:
        for name in ['engine','vendor']:
            src=(ROOT/name).resolve(); hidden=(ROOT/('.windows-package-hidden-'+name)).resolve()
            if not src.is_relative_to(ROOT) or not hidden.is_relative_to(ROOT) or hidden.exists():
                raise RuntimeError('Unsafe or occupied temporary hide path')
            src.rename(hidden); moved.append((src,hidden))
        binary=package/'Engine/Binaries/Win64/RiveRhiLite.exe'
        for n in range(3):
            png=out/f'run-{n}.png'
            result=capture(binary,package,package/'shaders/global.bin',package/'fixtures/input.riv',png,
                           shader_directory=package/'Engine/Shaders',env=env)
            result['comparison']=compare_images(a.reference,png) if png.exists() else {'status':'incomplete'}
            captures.append(result)
            if not result['passed'] or result['comparison']['status']!='passed': break
        caps=subprocess.run([str(binary),'-Capabilities'],capture_output=True,text=True,env=env,timeout=30,cwd=package)
        umg=subprocess.run([str(binary),'-Ui=umg'],capture_output=True,text=True,env=env,timeout=30,cwd=package)
        checks={'capabilities':caps.returncode==0 and json.loads(caps.stdout)=={'rive':True,'umg':False},
                'umg_rejected':umg.returncode==9 and 'UMG_NOT_COMPILED' in umg.stderr}
        launcher_png=out/'launcher.png'
        powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
        with (out/'launcher.log').open('wb') as log:
            launched=subprocess.run([str(powershell),'-NoProfile','-ExecutionPolicy','Bypass',
                '-File',str(package/'render.ps1'),'-Output',str(launcher_png)],
                stdout=log,stderr=subprocess.STDOUT,env=env,cwd=package,timeout=180)
        checks['public_launcher']=launched.returncode==0 and launcher_png.exists() and compare_images(a.reference,launcher_png)['status']=='passed'
    finally:
        for src,hidden in reversed(moved): hidden.rename(src)
    passed=len(captures)==3 and all(x['passed'] and x['comparison']['status']=='passed' for x in captures) and all(checks.values())
    report={'status':'passed' if passed else 'failed','checks':checks,'captures':captures,
            'hidden_development_directories':['engine','vendor'],'path_only_system32':True,
            'timing_scope':'Three separate processes, OS/driver caches may be warm; not a cold-machine benchmark'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'checks':checks}))
    return 0 if passed else 1

if __name__=='__main__': raise SystemExit(main())
