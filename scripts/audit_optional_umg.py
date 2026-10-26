#!/usr/bin/env python3
"""Check real Lite compile inputs, UHT manifest, link inputs, package and CLI capabilities."""
from pathlib import Path
import argparse
import json
import re
import subprocess

from compare_png import sha256
from measure_ue_lite import inspect_build

ROOT=Path(__file__).resolve().parents[1]
FORBIDDEN={'Engine','Renderer','UMG','UMGEditor','Slate','SlateCore','SlateRHIRenderer','SlateBaseRenderer',
    'MovieScene','MovieSceneTracks','RiveUmgBridge','RiveUmgHost','UnrealEd'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    package=a.package.resolve()
    target='RiveRhiLite'
    exe=ROOT/'Binaries/Linux'/target
    receipt=ROOT/'Binaries/Linux'/f'{target}.target'
    build=ROOT/'Intermediate/Build/Linux/x64'/target/'Development'
    linkage=inspect_build([receipt],[build/f'{target}.link.rsp'],exe)
    # Include nested shared response files as well as each translation unit.
    rsp_files=sorted(path for path in build.rglob('*.rsp') if path.name.endswith(('.o.rsp','.Shared.rsp')))
    violations=[]
    compile_inputs=[]
    for path in rsp_files:
        text=path.read_text(errors='replace')
        modules=set(re.findall(r'/Runtime/([^/\s"]+)/|/Development/([^/\s"]+)/',text))
        flat={s for pair in modules for s in pair if s}
        leaked=sorted(flat & FORBIDDEN)
        if leaked: violations.append({'response':str(path),'modules':leaked})
        compile_inputs.append({'path':str(path),'sha256':sha256(path)})
    uht=ROOT/f'Intermediate/Build/Linux/{target}/{target}.uhtmanifest'
    uhtdata=json.loads(uht.read_text())
    uhtmodules=[m['Name'] for m in uhtdata['Modules']]
    leaked_files=[str(f.relative_to(package)) for f in package.rglob('*') if f.is_file() and
        any(x in {'Slate','SlateDebug','UMG','UMGEditor','Renderer'} for x in f.relative_to(package).parts)]
    manifest=json.loads((package/'package-manifest.json').read_text())
    caps=subprocess.run([str(exe),'-Capabilities'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    reject=subprocess.run([str(exe),'-Ui=umg'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    report={'status':'incomplete','scope':'actual Lite build inputs/link/UHT/package and CLI only; UMG runtime parity is a separate gate',
        'linkage':linkage,'forbidden_modules':sorted(FORBIDDEN),'leaked_link_modules':sorted(set(linkage['recognized_modules'])&FORBIDDEN),
        'compile_response_files':compile_inputs,'compile_input_violations':violations,
        'uht_manifest_sha256':sha256(uht),'uht_modules':uhtmodules,'leaked_uht_modules':sorted(set(uhtmodules)&FORBIDDEN),
        'leaked_package_files':leaked_files,'package_capabilities':manifest.get('capabilities'),
        'capability_query':{'exit_code':caps.returncode,'output':caps.stdout},
        'umg_request_rejection':{'exit_code':reject.returncode,'output':reject.stdout}}
    report['status']='passed' if (linkage['status']=='passed' and rsp_files and not violations and not report['leaked_link_modules']
        and not report['leaked_uht_modules'] and not leaked_files and manifest.get('capabilities')=={'rive':True,'umg':False}
        and caps.returncode==0 and '"umg":false' in caps.stdout and reject.returncode==9 and 'UMG_NOT_COMPILED' in reject.stdout) else 'failed'
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'compile_response_files':len(rsp_files),'link_modules':len(linkage['recognized_modules']),
        'uht_modules':len(uhtmodules),'package_files':len(manifest['files'])},indent=2))
    return 0 if report['status']=='passed' else 1

if __name__=='__main__': raise SystemExit(main())
