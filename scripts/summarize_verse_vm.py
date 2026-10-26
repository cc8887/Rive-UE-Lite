#!/usr/bin/env python3
"""Bind final optional VerseVM delivery to measured artifacts and explicit limits."""
from pathlib import Path
import json

from compare_png import sha256

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'artifacts/verse-vm'

def read(relative):
    return json.loads((OUT/relative).read_text())

def main():
    runtime, package = read('runtime-02/report.json'), read('package-02/report.json')
    direct, wrapper = read('cpp-incremental-01/report.json'), read('cpp-wrapper-incremental-01/report.json')
    boundary = read('boundary-01.json')
    portable = [read('portable-02/report.json'), read('portable-idle-02/report.json')]
    optional = (OUT/'optional-build.console.log').read_text()
    default = (OUT/'after-verse-default.console.log').read_text()
    package_dir = ROOT/'package/verse-ui-02'
    manifest = json.loads((package_dir/'package-manifest.json').read_text())
    declared = {item['path'] for item in manifest['files']} | {'package-manifest.json'}
    modified = [item['path'] for item in manifest['files']
        if not (package_dir/item['path']).is_file() or sha256(package_dir/item['path']) != item['sha256']]
    generated = [{'path': p.relative_to(package_dir).as_posix(), 'bytes': p.stat().st_size}
        for p in package_dir.rglob('*') if p.is_file() and p.relative_to(package_dir).as_posix() not in declared]
    source_match = all(sha256(ROOT/'fixtures/verse'/name) == sha256(package_dir/'fixtures/verse'/name)
        for name in ['ui_controller.verse', 'worker_main.verse'])
    gates = {
        'real_vm_and_ui_chain': runtime['status'] == 'passed_scoped' and len(runtime['runs']) == 6,
        'runtime_fault_injection': len(runtime['negative_tests']) == 3 and all(x['rejected_as_expected'] for x in runtime['negative_tests']),
        'verse_source_edits_executed_without_cpp_rebuild': len(runtime['verse_edit_runs']) == 3 and runtime['binaries_unchanged_during_verse_edits'],
        'native_ue_two_pixel_pairs': len(runtime['native_pairs']) == 2 and all(x['comparison']['different_pixels'] == 0 and x['playback_equal'] for x in runtime['native_pairs']),
        'visible_ui_state_changed': runtime['visible_state_difference']['different_pixels'] > 0,
        'cpu_only_device_namespace': not any(runtime['gpu_nodes'].values()) and bool(runtime['namespace']),
        'packaged_portable_two_states': all(x['status'] == 'passed' for x in portable),
        'default_and_worker_boundary': boundary['status'] == 'passed',
        'default_after_worker_zero_actions': 'run 0 action(s)' in default and 'target=RiveRhiLite' in default,
        'actual_optional_build_entry': optional.count('Result: Succeeded') == 2 and 'RiveVerseWorker' in optional and 'RiveRhiLite' in optional,
        'cpp_actual_incremental_builds': direct['status'] == wrapper['status'] == 'passed',
        'package_inventory_and_elf': package['status'] == 'passed' and not modified and source_match,
        'archive_unchanged': sha256(Path(package['archive']['path'])) == package['archive']['sha256']}
    report = {'status': 'minimal_chain_passed_uefn_unverified' if all(gates.values()) else 'failed',
        'gates': gates, 'scope': runtime['scope'], 'engine_commit': '62d7c1a7125b52b10ee1b714838f515f3563f795',
        'default_command': 'sudo bash scripts/build_ui.sh',
        'optional_command': 'sudo bash scripts/build_ui.sh --with-verse',
        'deployment': {'directory': str(package_dir), 'logical_bytes': package['logical_file_bytes'],
            'archive': package['archive'], 'added_logical_bytes': package['added_logical_bytes'],
            'worker_elf_bytes': package['executable_bytes'], 'payload_modified_files': modified,
            'runtime_generated_files_not_in_deploy_archive': generated,
            'runtime_generated_bytes': sum(x['bytes'] for x in generated),
            'runtime_requirements': 'Python3, GNU time (/usr/bin/time), Mesa CPU Vulkan and Linux system libraries; base-image bytes excluded'},
        'metrics': {**runtime['metrics'], 'cpp_direct_incremental_seconds': direct['wall_seconds'],
            'cpp_full_entry_incremental_seconds': wrapper['wall_seconds'],
            'cpp_measurement_scope': 'single cached TU and full link, not cold build; full entry includes optional dependency preparation and default target check'},
        'not_passed': {'inprocess_hot_reload': runtime['hot_reload'], 'uefn': runtime['uefn_comparison']},
        'source_files': [{'path': str(p.relative_to(ROOT)), 'sha256': sha256(p)} for p in sorted((ROOT/'Source/RiveVerseWorker').rglob('*')) if p.is_file()],
        'evidence': {name: sha256(OUT/name) for name in ['runtime-02/report.json', 'package-02/report.json',
            'cpp-incremental-01/report.json', 'cpp-wrapper-incremental-01/report.json', 'boundary-01.json',
            'portable-02/report.json', 'portable-idle-02/report.json']}}
    (OUT/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'status': report['status'], 'gates': gates, 'metrics': report['metrics']}, indent=2))
    return 0 if all(gates.values()) else 1

if __name__ == '__main__':
    raise SystemExit(main())
