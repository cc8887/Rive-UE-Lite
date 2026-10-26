#!/usr/bin/env python3
"""Paired startup/first-image/RSS measurement of deployed native worker builds.

Use isolated_widget_worker.sh: development resources and GPU nodes are hidden.
One warmup per case, then interleaved runs; fresh user/Mesa caches each time.
This is an OS-cache-warm observation on a shared WSL host, not a cold boot test.
"""
from pathlib import Path
import argparse
import json
import os
import re
import signal
import statistics
import subprocess
import threading
import time

from compare_png import compare_images, sha256

ROOT = Path(__file__).resolve().parents[1]
ERROR = re.compile(r'Ensure condition failed:|Fatal error:|Log\w+: Error:')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--animated', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--runs', type=int, default=5)
    p.add_argument('--textured-content', type=Path, help='Optional image/texture workload instead of the legacy animation-only third case')
    p.add_argument('--textured-asset', default='/Game/UI/WBP_Textured')
    a = p.parse_args(); out = a.output_dir.resolve()
    if out.exists(): p.error('Use a fresh directory')
    if os.environ.get('RIVE_UE_LITE_GPU_DEVICES_HIDDEN') != '1' or (ROOT/'engine/Engine/Config/Base.ini').exists():
        p.error('Run under isolated_widget_worker.sh, with GPU/build resources hidden')
    if a.runs < 3: p.error('Use at least 3 measured runs')
    out.mkdir(parents=True)
    cpus = sorted(os.sched_getaffinity(0))[:2]; os.sched_setaffinity(0, cpus)
    last_case = 'new_textured' if a.textured_content else 'new_animation'
    packages = {'baseline_static': a.baseline.resolve(), 'new_static': a.animated.resolve(), last_case: a.animated.resolve()}
    for package in set(packages.values()):
        manifest = json.loads((package/'package-manifest.json').read_text())
        assert manifest['status'] == 'staged' and not manifest['missing']
        assert all(sha256(package/f['path']) == f['sha256'] for f in manifest['files'])
    cases = list(packages)
    report = {'status': 'incomplete', 'scope': 'deployed source WBP worker startup and first CPU Vulkan PNG; no UEFN/full Editor UI',
        'paired_input_policy': 'baseline_static and new_static read identical source bytes; third case is a different workload, not code overhead',
        'cpu_affinity': cpus, 'cpu_count': 2, 'gpu_nodes': {p: Path(p).exists() for p in ['/dev/dxg', '/dev/dri']},
        'cache_policy': 'One excluded warmup per case; OS cache may be warm. Separate fresh user/Mesa cache for every invocation.',
        'host_scope': 'WSL Ubuntu shared host; affinity limited, no dedicated CPU/cgroup or cold-boot control',
        'runs': [], 'groups': {}, 'comparisons': []}
    assert not any(report['gpu_nodes'].values())
    env = dict(os.environ, SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy', LP_NUM_THREADS='2',
        VK_ICD_FILENAMES='/usr/share/vulkan/icd.d/lvp_icd.json', VK_DRIVER_FILES='/usr/share/vulkan/icd.d/lvp_icd.json')

    def save(): (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    def run(case, index):
        directory = out/(case+'-'+str(index)); directory.mkdir()
        package = packages[case]
        # Static cases read the exact same original source bytes. Playback reads
        # the authored animation package, including both source and native clone.
        content = (a.textured_content.resolve() if a.textured_content else a.animated.resolve()/'Content') if case == last_case else a.baseline.resolve()/'Content'
        asset = a.textured_asset if case == 'new_textured' else '/Game/UI/WBP_Card'
        png = directory/'output.png'; metadata = directory/'asset.json'
        command = ['bash', str(package/'worker.sh'), '-Mode=render', '-vulkan', '-sm5', '-AllowCPUDevices',
            '-AllowCommandletRendering', '-RenderOffscreen', '-norhithread', f'-ContentDir={content}',
            f'-Asset={asset}', f'-ShaderArchive={package}/shaders/global.bin', f'-Output={png}',
            f'-Metadata={metadata}', f'-UserDir={directory}/user/', f'-abslog={directory}/ue.log']
        if case == 'new_animation': command += ['-Animation=Intro', '-AnimationTime=0.5']
        if case == 'new_textured': command += ['-Animation=FadeImage', '-AnimationTime=0.5']
        times = {}; text_lines = []; maps = set(); start = time.monotonic()
        process = subprocess.Popen(['/usr/bin/time','-v','-o',str(directory/'time.txt'),'--',*command], cwd='/tmp',
            env=dict(env, MESA_SHADER_CACHE_DIR=str(directory/'mesa-cache')),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', start_new_session=True)

        def read_log():
            with (directory/'worker.log').open('w') as log:
                for line in process.stdout:
                    now = time.monotonic()-start; text_lines.append(line); log.write(line)
                    for marker, key in [('UMG_BP_WORKER_READY','ready_seconds'),('UMG_BP_ANIMATION','animation_log_seconds'),('UMG_BP_COMPLETE','complete_seconds')]:
                        if marker in line and key not in times: times[key] = now
                    if 'UMG_BP_WORKER_READY' in line:
                        try:
                            children = Path(f'/proc/{process.pid}/task/{process.pid}/children').read_text().split()
                            for pid in children:
                                maps.update(Path(f'/proc/{pid}/maps').read_text().splitlines())
                                status = Path(f'/proc/{pid}/status').read_text()
                                ready_rss = re.search(r'VmRSS:\s*(\d+)', status)
                                if ready_rss: times['ready_rss_kib'] = int(ready_rss[1])
                        except (OSError, ProcessLookupError): pass

        reader = threading.Thread(target=read_log); reader.start()
        try:
            while process.poll() is None:
                if 'first_png_seconds' not in times and png.is_file():
                    # A complete PNG ends with IEND, avoiding a partial-write marker.
                    try:
                        data = png.read_bytes()
                        if data.endswith(b'IEND\xaeB`\x82'): times['first_png_seconds'] = time.monotonic()-start
                    except OSError: pass
                if time.monotonic()-start > 180: raise TimeoutError('Worker timed out')
                time.sleep(.002)
        except Exception:
            os.killpg(process.pid, signal.SIGKILL); process.wait(); reader.join(); raise
        reader.join(); times['wall_seconds'] = time.monotonic()-start
        if 'first_png_seconds' not in times and png.is_file(): times['first_png_seconds'] = times['wall_seconds']
        text = ''.join(text_lines); timing = (directory/'time.txt').read_text()
        rss = re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)', timing)
        meta = json.loads(metadata.read_text()) if metadata.is_file() else {}
        mapped_paths = sorted({line.split()[-1] for line in maps if '/' in line})
        forbidden = [path for path in mapped_paths if path.startswith('/') and not path.startswith(('/usr/','/lib/','/lib64/')) and
            not path.startswith(str(directory/'mesa-cache')+'/') and
            not any(path.startswith(str(pkg)+'/') for pkg in set(packages.values()))]
        passed = (process.returncode == 0 and 'UMG_BP_TEARDOWN complete' in text and not ERROR.search(text) and
            png.is_file() and meta.get('using_null_rhi') is False and 'llvmpipe' in meta.get('adapter','').lower() and
            'ready_seconds' in times and rss and mapped_paths and not forbidden)
        result = {'case':case,'index':index,'warmup':index==0,'status':'passed' if passed else 'failed','command':command,
            'exit_code':process.returncode, **times, 'peak_rss_kib':int(rss[1]) if rss else None,
            'metadata_elapsed_ms':meta.get('elapsed_ms'),'native_ready_ms':meta.get('worker_ready_ms'),
            'animation_owner_ms':meta.get('animation_playback',{}).get('owner_manager_init_ms'),
            'animation_evaluation_ms':meta.get('animation_playback',{}).get('evaluation_ms'),
            'worker_sha256':sha256(package/'Engine/Binaries/Linux/RiveUmgBlueprintWorker'),
            'mapped_paths_at_ready':mapped_paths,'forbidden_development_mappings':forbidden,
            'generated_cache_mappings':[path for path in mapped_paths if path.startswith(str(directory/'mesa-cache')+'/')],
            'output':str(png),'source_sha256':sha256(content/(asset.removeprefix('/Game/')+'.uasset'))}
        report['runs'].append(result); save()
        print(json.dumps({'case':case,'index':index,'status':result['status'], 'ready_seconds':times.get('ready_seconds'),
            'first_png_seconds':times.get('first_png_seconds')}), flush=True)
        assert passed, str(directory)

    try:
        for case in cases: run(case,0)
        for index in range(1,a.runs+1):
            for case in cases if index%2 else list(reversed(cases)): run(case,index)
        for case in cases:
            runs = [run for run in report['runs'] if run['case']==case and not run['warmup']]
            report['groups'][case] = {key:{'median':statistics.median(run[key] for run in runs),
                'min':min(run[key] for run in runs),'max':max(run[key] for run in runs)} for key in
                ['ready_seconds','first_png_seconds','complete_seconds','wall_seconds','peak_rss_kib','ready_rss_kib']}
        baseline = report['groups']['baseline_static']; new_static = report['groups']['new_static']; animated = report['groups'][last_case]
        report['deltas'] = {label:{key:right[key]['median']-left[key]['median'] for key in baseline} for label,left,right in
            [('code_only_vs_baseline',baseline,new_static),
             ('different_textured_workload_vs_baseline' if a.textured_content else 'animated_first_image_vs_baseline',baseline,animated),
             ('different_textured_workload_vs_new_static' if a.textured_content else 'animation_eval_vs_new_static',new_static,animated)]}
        for index in range(1,a.runs+1):
            comparison = compare_images(out/f'baseline_static-{index}/output.png',out/f'new_static-{index}/output.png')
            report['comparisons'].append({'name':f'static-regression-{index}',**comparison}); assert comparison['different_pixels']==0
        animated_hashes = {sha256(out/f'{last_case}-{i}/output.png') for i in range(1,a.runs+1)}
        assert len(animated_hashes)==1
        report['animated_output_repeatable'] = True
        report['status']='passed'
    except Exception as error: report['status']='failed'; report['error']=repr(error)
    save(); print(json.dumps({'status':report['status'],'deltas':report.get('deltas'),'error':report.get('error')},indent=2))
    return int(report['status']!='passed')


if __name__=='__main__': raise SystemExit(main())
