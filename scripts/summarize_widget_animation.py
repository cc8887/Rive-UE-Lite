#!/usr/bin/env python3
"""Bind animation acceptance, deployment packages and paired startup evidence."""
from pathlib import Path
import argparse
import json
import statistics
import subprocess
from compare_png import compare_images, sha256
from measure_ue_lite import parse_link_modules

ROOT=Path(__file__).resolve().parents[1]


def read(path): return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=ROOT/'artifacts/umg-animation/summary.json')
    a=p.parse_args(); base=ROOT/'artifacts/umg-animation'
    acceptance=read(base/'acceptance-03/summary.json'); startup=read(base/'startup-03/summary.json')
    before=read(ROOT/'package/widget-static-baseline-02.metrics.json'); after=read(ROOT/'package/widget-animation-01.metrics.json')
    before_manifest=read(ROOT/'package/widget-static-baseline-02/package-manifest.json')
    after_manifest=read(ROOT/'package/widget-animation-01/package-manifest.json')
    old_files={f['path']:f for f in before_manifest['files']}; new_files={f['path']:f for f in after_manifest['files']}
    changed=[{'path':key,'before_bytes':old_files[key]['bytes'],'after_bytes':new_files[key]['bytes'],
        'delta_bytes':new_files[key]['bytes']-old_files[key]['bytes']} for key in old_files.keys()&new_files.keys()
        if old_files[key]['sha256']!=new_files[key]['sha256']]
    old_rsp=base/'baseline/RiveUmgBlueprintWorker.rsp'
    new_rsp=ROOT/'Intermediate/Build/Linux/x64/RiveUmgBlueprintWorker/Development/RiveUmgBlueprintWorker.rsp'
    old_modules=parse_link_modules(old_rsp.read_text()); new_modules=parse_link_modules(new_rsp.read_text())
    windows=read(base/'windows-preview-01/report.json'); windows_list=read(base/'windows-list-01/report.json')
    win_diff=compare_images(base/'Windows animation preview.png',base/'acceptance-03/11-frame-2.png')
    package_diff=compare_images(base/'animated-portable-01/frame.png',base/'acceptance-03/11-frame-2.png')
    lite=read(base/'lite-exclusion.json'); default=read(base/'default-runtime/summary.json')
    runtime_paths=['Source/RiveRhiLite','Source/RiveLiteRenderer','Source/RiveUmgHost','Source/RiveUmgBridge','Source/RiveVerseWorker']
    git=subprocess.run(['git','-c',f'safe.directory={ROOT}','-C',str(ROOT),'diff','--name-only','--',*runtime_paths],text=True,capture_output=True)
    measured=[r for r in startup['runs'] if r['case']=='new_animation' and not r['warmup']]
    gates={
        'native_animation_suite':acceptance['status']=='passed_scoped' and all(acceptance['gates'].values()),
        'cpu_native_reference_exact':len(acceptance['comparisons'])==6 and all(c['different_pixels']==0 for c in acceptance['comparisons']),
        'paired_startup':startup['status']=='passed' and len(startup['runs'])==18,
        'portable_baseline':read(base/'baseline-portable-01/summary.json')['status']=='passed',
        'portable_animation':read(base/'animated-portable-01/summary.json')['status']=='passed' and package_diff['different_pixels']==0,
        'packages_complete_for_scope':before['status']==after['status']=='staged' and not before_manifest['missing'] and not after_manifest['missing'],
        'no_new_link_modules':old_modules==new_modules and {'MovieScene','MovieSceneTracks','UMGEditor'}<=new_modules,
        'actual_source_binary_packaged':after_manifest['worker_source_sha256']==sha256(ROOT/'Binaries/Linux/RiveUmgBlueprintWorker'),
        'windows_nested_cli_and_preview':windows['status']==windows_list['status']=='passed' and win_diff['different_pixels']==0,
        'default_dependency_exclusion':lite['status']=='passed',
        'default_build_noop':'run 0 action(s)' in (base/'default-noop.console.log').read_text(),
        'default_runtime_regression':default['status']=='passed',
        'runtime_source_paths_unmodified':git.returncode==0 and not git.stdout.strip(),
    }
    result={'status':'passed_scoped' if all(gates.values()) else 'failed','date':'2026-10-26',
        'engine_commit':'62d7c1a7125b52b10ee1b714838f515f3563f795','gates':gates,
        'native_cli_cases':len(acceptance['runs']),'native_checks':len(acceptance['gates']),
        'package_before':before,'package_after':after,
        'added_bytes':{key:after[key]-before[key] for key in ['logical_bytes','payload_bytes','tar_gz_bytes','worker_bytes']},
        'package_changed_files':sorted(changed,key=lambda f:f['path']),
        'package_added_files':sorted(new_files.keys()-old_files.keys()),'package_removed_files':sorted(old_files.keys()-new_files.keys()),
        'link_module_count_before':len(old_modules),'link_module_count_after':len(new_modules),
        'added_link_modules':sorted(new_modules-old_modules),'removed_link_modules':sorted(old_modules-new_modules),
        'startup_groups':startup['groups'],'startup_deltas':startup['deltas'],
        'native_animation_instrumentation_medians_ms':{
            'owner_systems_manager':statistics.median(r['animation_owner_ms'] for r in measured),
            'first_evaluation':statistics.median(r['animation_evaluation_ms'] for r in measured),
            'sum':statistics.median(r['animation_owner_ms']+r['animation_evaluation_ms'] for r in measured)},
        'timing_interpretation':'5 interleaved measured processes per case after one warmup; 2 CPUs, ext4, fresh user/Mesa cache; OS cache may be warm. Shared WSL host. Ready is before asset/animation load; first PNG includes it. Ranges overlap: median deltas are observations, not fixed startup penalties or improvements.',
        'default_binary_note':{'pre_task_sha256':default['pre_task_exe_sha256'],'current_sha256':default['exe_sha256'],
            'same_sha256':default['pre_task_exe_sha256']==default['exe_sha256'],
            'reason':'Build verification switched debug flags then restored original build options, rebuilding the default binary. No animation/runtime source edits; same pre-task Rive PNG. Historical runtime packages remain frozen, not repacked or globally requalified.'},
        'asset_sizes':acceptance['asset_sizes'],'windows_comparison':win_diff,'portable_comparison':package_diff,
        'evidence':{'acceptance':str(base/'acceptance-03/summary.json'),'startup':str(base/'startup-03/summary.json'),
            'native_build':str(base/'build-07.log'),'default_runtime':str(base/'default-runtime/summary.json'),
            'lite_boundary':str(base/'lite-exclusion.json')},
        'remaining_scope':['UEFN asset/version compatibility and View Bindings/Verse triggers','Full Editor viewport or arbitrary project/animation library qualification',
            'Color/material/slot/event animation authoring; structural animation rename/delete/graph edits']}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['status','gates','added_bytes','link_module_count_before','link_module_count_after','native_animation_instrumentation_medians_ms']},indent=2))
    return int(result['status']!='passed_scoped')


if __name__=='__main__': raise SystemExit(main())
