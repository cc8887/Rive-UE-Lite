"""Stage only the audited Windows Rive-only runtime and a native cooked archive."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def validate_shader(path):
    m=json.loads(Path(str(path)+'.manifest.json').read_text(encoding='utf-8-sig'))
    expected={'complete':True,'kind':'ue_engine_canonical','target_platform':'Windows',
              'shader_platform':'VULKAN_SM5','target_has_editor_only_data':False,
              'type_filter':'','loads_lite_archive':False,'failed_jobs':0}
    if any(m.get(k)!=v for k,v in expected.items()) or m.get('submitted_jobs',0)<=0 or m.get('succeeded_jobs')!=m.get('submitted_jobs') or m.get('archive_bytes')!=path.stat().st_size:
        raise RuntimeError('Require complete native Windows Vulkan SM5 cooker evidence')
    return m

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--shader-archive',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    validate_shader(a.shader_archive)
    receipt=ROOT/'Binaries/Win64/RiveRhiLite.target'
    binary=ROOT/'Binaries/Win64/RiveRhiLite.exe'
    boundary=json.loads((ROOT/'artifacts/windows/boundary.json').read_text())
    if boundary['status']!='passed' or boundary['receipt_sha256']!=sha(receipt) or boundary['executable_sha256']!=sha(binary):
        raise RuntimeError('Re-run audit_windows_boundary.py for the current executable')
    out=a.output.resolve()
    if out.exists(): raise RuntimeError('Use a fresh package directory')
    if not out.is_relative_to(ROOT): raise RuntimeError('Package must stay inside this prototype')
    engine=ROOT/'engine/Engine'
    pending=[]
    data=json.loads(receipt.read_text())
    for item in data['BuildProducts']+data['RuntimeDependencies']:
        if item['Type'] in ['SymbolFile','MapFile','DebugNonUFS','BuildResource']: continue
        src=Path(item['Path'].replace('$(EngineDir)',str(engine)).replace('$(ProjectDir)',str(ROOT))).resolve()
        if src.suffix.lower() in ['.lib','.exp','.pdb','.map','.objpaths']: continue
        if not src.is_file(): raise RuntimeError('Missing receipt dependency: '+str(src))
        if src.is_relative_to(engine): dest=Path('Engine')/src.relative_to(engine)
        elif src.is_relative_to(ROOT/'Binaries/Win64'): dest=Path('Engine/Binaries/Win64')/src.relative_to(ROOT/'Binaries/Win64')
        else: dest=src.relative_to(ROOT)
        if any(x in dest.parts for x in ['UMG','Slate','SlateCore','VerseCompiler','RiveUmgHost','RiveVerseWorker']):
            raise RuntimeError('Unexpected optional dependency: '+str(src))
        pending.append((src,dest))
    for sub in ['', 'Windows']:
        pending += [(src,Path('Engine/Config')/sub/src.name) for src in (engine/'Config'/sub).glob('*.ini')]
    pending += [(src,src.relative_to(ROOT)) for src in (ROOT/'Config').rglob('*.ini')]
    pending += [(ROOT/'fixtures/bankcard.riv',Path('fixtures/input.riv')),
                (a.shader_archive,Path('shaders/global.bin')),
                (Path(str(a.shader_archive)+'.manifest.json'),Path('shaders/global.bin.manifest.json')),
                (ROOT/'prototype/runtime/render_windows.ps1',Path('render.ps1'))]
    # App-local Microsoft runtime from the verified toolchain payload; no VS install needed at runtime.
    redist=ROOT/'dependencies/windows-msvc/Redist'
    pending += [(src,Path('Engine/Binaries/Win64')/src.name) for src in redist.rglob('*.dll') if 'Microsoft.VC145.CRT' in src.parts]
    out.mkdir(parents=True)
    for src,dest in pending:
        (out/dest).parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(src,out/dest)
    (out/'Engine/Shaders').mkdir(parents=True,exist_ok=True)
    files=[{'path':p.relative_to(out).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.rglob('*')) if p.is_file()]
    report={'platform':'Windows x64','rhi':'UE Vulkan RHI/RDG','default':'Rive-only',
            'raw_bytes':sum(p['bytes'] for p in files),'executable_sha256':sha(binary),'files':files,
            'system_dependencies':['Windows x64 (validated on Windows 11 26100)','Vulkan-capable graphics driver'],
            'excluded':['UMG','Engine runtime module','Renderer runtime module','Verse worker','cooker','SDK','PDB'],
            'runtime_validation':'Recorded separately in release windows-validation.json; staging alone is not runtime acceptance'}
    (out/'package-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'files':len(files),'raw_bytes':report['raw_bytes']}))

if __name__=='__main__': main()
