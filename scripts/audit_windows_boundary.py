"""Audit the actual Windows Rive-only executable and MSVC link inputs."""
import hashlib
import json
from pathlib import Path
import re
from measure_ue_lite import inspect_build

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {'Engine','Renderer','UMG','Slate','SlateCore','RiveUmgHost','VerseCompiler',
             'VerseNative','VerseVMCodeGen','Solaris','MetalRHI','D3D11RHI','D3D12RHI'}

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def audit():
    receipt = ROOT/'Binaries/Win64/RiveRhiLite.target'
    binary = ROOT/'Binaries/Win64/RiveRhiLite.exe'
    intermediate = ROOT/'Intermediate/Build/Win64/x64/RiveRhiLite/Development'
    link = intermediate/'RiveRhiLite.exe.rsp'
    data = json.loads(receipt.read_text(encoding='utf-8-sig'))
    linkage = inspect_build([receipt], [link], binary)
    modules = set(linkage['recognized_modules'])
    seen = {}
    def read(p):
        p=p.resolve()
        if p in seen: return
        text=p.read_text(encoding='utf-8-sig',errors='replace')
        seen[p]=text
        for child in re.findall(r'(?:@|/FI)"([^"]+)"',text):
            path=Path(child)
            read(path if path.is_absolute() else p.parent/path)
    for p in intermediate.rglob('*.obj.rsp'): read(p)
    definitions={name:sorted({value for text in seen.values()
        for value in re.findall(rf'(?:#define\s+{name}\s+|/D{name}=)([01])\b',text)})
        for name in ['WITH_ENGINE','WITH_VERSE_VM','WITH_VERSE_COMPILER']}
    checks={'receipt':data['TargetName']=='RiveRhiLite' and data['Platform']=='Win64',
            'linkage':linkage['status']=='passed','vulkan_linked':'VulkanRHI' in modules,
            'heavy_modules_excluded':not bool(modules & FORBIDDEN),
            'compile_definitions':definitions=={k:['0'] for k in definitions},
            'compile_responses_present':bool(seen), 'pe_binary':binary.read_bytes()[:2]==b'MZ'}
    return {'status':'passed' if all(checks.values()) else 'failed','checks':checks,
            'executable_sha256':sha(binary),'receipt_sha256':sha(receipt),'linkage':linkage,
            'definitions':definitions,
            'platform_baseline_note':'Pinned Windows Core unconditionally links the external libpas allocator; this is not optional VerseVM or VerseCompiler activation.',
            'compile_evidence':[{'path':str(p.relative_to(ROOT)), 'sha256':sha(p)} for p in seen]}

if __name__=='__main__':
    result=audit()
    (ROOT/'artifacts/windows/boundary.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['checks'],indent=2))
    raise SystemExit(result['status']!='passed')
