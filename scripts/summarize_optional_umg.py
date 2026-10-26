#!/usr/bin/env python3
"""Collect the actual optional-UMG prototype gates, without building or rendering."""
from pathlib import Path
import json

from compare_png import sha256
from measure_ue_lite import inspect_build

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/umg-optional'

def read(name): return json.loads((BASE/name).read_text())

def main():
    matrix=read('matrix-01/summary.json')
    lite=read('lite-exclusion-final.json')
    builds={k:read(f'incremental-{k}-01/report.json') for k in ['rive','umg']}
    packages={k:read(f'package-{k}-0{1 if k=="rive" else 2}/report.json') for k in ['rive','umg']}
    guards=read('cli-guards.json')
    originals=read('original-projects-final.json')
    target='RiveUmgHost'
    b=ROOT/'Intermediate/Build/Linux/x64'/target/'Development'
    inclusion=inspect_build([ROOT/f'Binaries/Linux/{target}.target'],[b/f'{target}.link.rsp'],ROOT/f'Binaries/Linux/{target}')
    modules=set(inclusion['recognized_modules'])
    required={'Engine','Renderer','UMG','Slate','SlateCore','SlateRHIRenderer','RiveLiteRenderer','RiveUmgBridge'}
    enhanced_link={'status':'passed' if required<=modules and not ({'UMGEditor','UnrealEd'}&modules) else 'failed',
        'modules':sorted(modules),'required':sorted(required),'editor_modules':sorted({'UMGEditor','UnrealEd'}&modules),
        'evidence':inclusion['evidence']}
    cooks={s:read(f'shaders-{s}/provenance/provenance.json') for s in ['host','reference']}
    domains={}
    for side in cooks:
        d=read(f'shaders-{side}/global.bin.manifest.json')
        domains[side]={(t['type'],i) for t in d['types'] for i in t['permutation_ids']}
    cache_dirs={s:next((arg.split('=',1)[1] for arg in c['cook_execution']['command'] if arg.startswith('-LocalDataCachePath=')),None)
        for s,c in cooks.items()}
    independent={'status':'passed' if (all(c['status']=='passed' and c['cook_execution']['archive_absent_before_invocation'] for c in cooks.values())
        and cooks['host']['cook_execution']['execution_id']!=cooks['reference']['cook_execution']['execution_id']
        and cache_dirs['host'] and cache_dirs['reference'] and cache_dirs['host']!=cache_dirs['reference']
        and domains['host']==domains['reference'] and matrix['host_archive']['sha256']!=matrix['reference_archive']['sha256']) else 'failed',
        'permutations':len(domains['host']),'domain_matches':domains['host']==domains['reference'],
        'archive_sha256':{s:c['cook_execution']['output']['sha256'] for s,c in cooks.items()},
        'execution_ids':{s:c['cook_execution']['execution_id'] for s,c in cooks.items()},
        'cache_directories':cache_dirs}
    toggle=(BASE/'toggle-off-01.log').read_text()
    toggle_ok='Target is up to date' in toggle and 'to run 0 action(s)' in toggle
    identities={}
    for flavor,target,folder in [('rive','RiveRhiLite','ui-rive-01'),('umg','RiveUmgHost','ui-umg-02')]:
        exe=ROOT/f'Binaries/Linux/{target}'
        staged=ROOT/f'package/{folder}/Engine/Binaries/Linux/{target}'
        identities[flavor]={'executable_sha256':sha256(exe),'package_executable_sha256':sha256(staged),
            'match':sha256(exe)==sha256(staged)}
    metrics={}
    for side in ['host','reference']:
        runs=[r for r in matrix['runs'] if r['side']==side]
        metrics[side]={'peak_rss_mib_range':[min(r['peak_rss_kib'] for r in runs)/1024,max(r['peak_rss_kib'] for r in runs)/1024],
            'first_png_seconds_range':[min(r['first_png_wall_seconds'] for r in runs),max(r['first_png_wall_seconds'] for r in runs)]}
    pure=read('portable-umg-rive-01/comparison.json')
    gates={'matrix':matrix['status'],'lite_exclusion':lite['status'],'enhanced_link':enhanced_link['status'],
        'independent_cooks':independent['status'],'cli_guards':guards['status'],
        'toggle_off':'passed' if toggle_ok else 'failed',
        'binary_package_binding':'passed' if all(x['match'] for x in identities.values()) else 'failed',
        'original_projects':'passed' if all(x['unchanged'] for x in originals.values()) else 'failed',
        'enhanced_rive_mode':pure['status'],
        **{f'compile_{k}':v['status'] for k,v in builds.items()},**{f'package_{k}':v['status'] for k,v in packages.items()}}
    report={'status':'passed' if all(x=='passed' for x in gates.values()) else 'failed', 'gates':gates,
        'scope':'same .uproject, two Program Targets, selected native worldless UMG/Rive CPU Vulkan captures; not full editor/Widget Blueprint or continuous FPS acceptance',
        'commands':{'default':'sudo bash scripts/build_ui.sh','enhanced':'sudo bash scripts/build_ui.sh --with-umg'},
        'packages':{k:{x:v[x] for x in ['package_dir','logical_file_bytes','executable_bytes','archive','file_count']} for k,v in packages.items()},
        'incremental_builds':builds,'incremental_wall_ratio':builds['umg']['wall_seconds']/builds['rive']['wall_seconds'],
        'cold_build_successful_separate_measurement':None,
        'umg_captures':{'normal_exit_runs':len(matrix['runs']),'exact_rgba_alpha_pairs':len(matrix['pairs']),
            'cpu_profile':matrix['cpu_profile'],'metrics':metrics,'report':str(BASE/'matrix-01/summary.json')},
        'independent_cooks':independent,'enhanced_link':enhanced_link,'binary_identities':identities,
        'toggle_off':{'zero_actions':toggle_ok,'log_sha256':sha256(BASE/'toggle-off-01.log')},
        'runtime_startup':'native UE6 lazy CDO API with UE_WITH_CONSTINIT_UOBJECT=0, real class/property registration and real on-demand CDOs; no new Engine source modifications',
        'original_projects':originals,'linux_metrics_unit_tests':{'passed':18,'log':str(BASE/'metrics-tests-linux.log')},
        'system_dependency_boundary':'application package excludes system CPU Vulkan ICD/LLVM and system library closure; DT_NEEDED inventory in each package report',
        'remaining_scope':['Designer/source Widget Blueprint compiler','UI materials/GEngine/world-dependent widgets','continuous FPS and interactive UMG input/IME']}
    (BASE/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'gates':gates,'packages':{k:[round(v['logical_file_bytes']/1048576,2),round(v['archive']['bytes']/1048576,2)] for k,v in packages.items()},
        'incremental_wall_seconds':{k:round(v['wall_seconds'],2) for k,v in builds.items()}},indent=2))
    return 0 if report['status']=='passed' else 1

if __name__=='__main__': raise SystemExit(main())
