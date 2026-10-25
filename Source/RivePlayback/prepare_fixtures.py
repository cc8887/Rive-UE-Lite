"""Stage exact pinned bytes and named playback cases; never edits vendor inputs."""
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / 'vendor/rive-unreal/submodules/rive-runtime'
OUT = ROOT / 'fixtures/playback'
OUT.mkdir(parents=True, exist_ok=True)
DELTA = 1 / 60


def event(time, kind, name=None, value=None, **extra):
    result = {'time': time, 'type': kind}
    if name is not None:
        result['name'] = name
    if value is not None:
        result['value'] = value
    return result | extra


cases = [
    dict(id='bounce_animation', fixture='ball_test.riv', mode='animation', artboard='Nested Artboard 2', animation='Bounce',
         events=[], sample_times=[0, .25, .5, .75],
         required_changes=[{'from': 0, 'to': .25, 'reason': 'Real Bounce animation applies a different ball pose'}],
         require_state_changes=False, source_test='tests/unit_tests/runtime/async_work_host_test.cpp:150'),
    dict(id='rocket_bool', fixture='rocket.riv', mode='state_machine', artboard='New Artboard', state_machine='Button',
         events=[event(.25, 'bool', 'Hover', True), event(.75, 'bool', 'Press', True),
                 event(1.25, 'bool', 'Press', False), event(1.5, 'bool', 'Hover', False)],
         sample_times=[0, .5, 1, 1.75],
         required_changes=[{'from': 0, 'to': .5, 'reason': 'Hover moves from idle to Roll_over'},
                           {'from': .5, 'to': 1, 'reason': 'Press selects the Press animation'}],
         require_state_changes=True, require_state_changes_after_events=True, event_effect_sample_times=[.5, 1],
         source_test='tests/unit_tests/runtime/state_machine_test.cpp:30'),
    dict(id='number_transitions', fixture='animation_reset_cases.riv', mode='state_machine', artboard='transitions', state_machine='transitions-state-machine',
         events=[event(.25, 'number', 'Number 1', 1), event(1.75, 'number', 'Number 1', 2)],
         sample_times=[0, .75, 1.5, 3],
         required_changes=[{'from': 0, 'to': .75, 'reason': 'Number 1=1 starts the rectangle 2.5-second position transition'},
                           {'from': 1.5, 'to': 3, 'reason': 'Number 1=2 starts the ellipse position transition'}],
         require_state_changes=True, require_state_changes_after_events=True, event_effect_sample_times=[.75, 3],
         source_test='tests/unit_tests/runtime/state_machine_test.cpp:368'),
    dict(id='trigger_transitions', fixture='state_machine_triggers.riv', mode='state_machine', artboard='main', state_machine='State Machine 1',
         events=[event(.25, 'trigger', 'Trigger 1'), event(.75, 'trigger', 'Trigger 1')],
         sample_times=[0, .5, 1, 1.5],
         required_changes=[{'from': 0, 'to': .5, 'reason': 'Trigger 1 switches to the second animation state and advances its animation'}],
         require_state_changes=True, require_state_changes_after_events=True, event_effect_sample_times=[.5],
         source_test='tests/unit_tests/runtime/state_machine_test.cpp:444'),
    dict(id='pointer_toggle', fixture='light_switch.riv', mode='state_machine', artboard='New Artboard', state_machine='Switch',
         events=[event(.25, 'pointer_down', x=150, y=258, pointer_id=0), event(.25, 'pointer_up', x=150, y=258, pointer_id=0),
                 event(1.25, 'pointer_down', x=150, y=258, pointer_id=0), event(1.25, 'pointer_up', x=150, y=258, pointer_id=0)],
         sample_times=[0, .75, 1.75],
         required_changes=[{'from': 0, 'to': .75, 'reason': 'Real pointer listeners toggle On from true to false'},
                           {'from': .75, 'to': 1.75, 'reason': 'Second real pointer click toggles On back to true'}],
         require_state_changes=True, require_state_changes_after_events=True, event_effect_sample_times=[.75],
         source_test='tests/unit_tests/runtime/state_machine_event_test.cpp:99'),
]

manifest = {'schema_version': 1, 'runtime_commit': '47d1cd54ccefd468db7cb26ecc4699ae1723dd85',
            'scope': 'Five selected deterministic fixtures only; not whole-library acceptance', 'scenarios': []}
for case in cases:
    source = RUNTIME / 'tests/unit_tests/assets' / case['fixture']
    destination = ROOT / 'fixtures' / case['fixture']
    shutil.copyfile(source, destination)
    assert source.read_bytes() == destination.read_bytes()
    scenario = {key: case[key] for key in ('mode', 'artboard', 'animation', 'state_machine', 'events') if key in case}
    scenario |= {'fixed_delta': DELTA, 'target_time': case['sample_times'][-1]}
    (OUT / (case['id'] + '.json')).write_text(json.dumps(scenario, indent=2) + '\n', encoding='utf-8')
    entry = {key: value for key, value in case.items() if key not in ('mode', 'artboard', 'animation', 'state_machine', 'events')}
    entry['fixture'] = '../' + case['fixture']
    entry |= {'playback': scenario, 'fixture_sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
    manifest['scenarios'].append(entry)
(OUT / 'scenarios.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'staged': len(cases), 'manifest': str(OUT / 'scenarios.json')}))
