# Shared Rive playback driver

`Public/RivePlayback.h` is a header-only Core + Json helper used by both
`RiveRhiLite` and `RiveUeReference`. It uses the pinned native runtime API. The
artboard returned from `Execute` is drawn by each host's existing UE RHI/RDG
path; no draw, flush, blend, clipping, or shader algorithm is changed here.

Host integration:

```cpp
RivePlayback::FScenario Scenario;
FString Error;
if (!RivePlayback::LoadScenario(FCommandLine::Get(), Scenario, Error)) { /* fail */ }
std::unique_ptr<rive::ArtboardInstance> Artboard;
TSharedPtr<FJsonObject> Metadata;
if (!RivePlayback::Execute(*File, Scenario, Seconds, Artboard, Metadata, Error)) { /* fail */ }
// Existing contain-center Artboard->draw, RDG flush, readback, and PNG save.
if (!RivePlayback::SaveMetadata(*Metadata, MetadataPath, Error)) { /* fail */ }
```

Use `-Scenario=/absolute/case.json -PlaybackMetadata=/absolute/output.json`.
Absent `-Scenario` retains the host's previous default-artboard/Seconds command
and reports `mode=legacy`; this is explicitly not named animation playback.
Supplying an invalid scenario, missing/ambiguous artboard or playback name,
unknown input, or wrong input type fails. Complete timelines are validated,
including events later than the selected frame; invalid names never fall back
to another animation or artboard.

## Timeline semantics

Each process imports once, creates one selected artboard and one actual
`LinearAnimationInstance` or `StateMachineInstance`, then replays from zero to
`target_time` using `fixed_delta`. Sampling does not reset an instance within
the replay. Target and event times must align to integer ticks within 1e-6
seconds; floating-point seconds passed into the runtime are the same float
delta in both hosts. Up to 360000 ticks and 10000 events are accepted.

At t=0, events at zero are applied in JSON order, then an initialization
advance(0) runs. For each subsequent tick the instance advances by delta to
reach the tick's timestamp **before** that timestamp's events are applied.
If the timestamp has events, one extra state-machine advanceAndApply(0) settles
immediate input effects without consuming or borrowing simulation time. Events
with equal timestamps retain JSON order; later events are validated but not
applied to this sample. There is no extra advance just for taking a screenshot.

Animations call `animation.advance(delta)`, `animation.apply(1)`, and
`artboard.advance(delta)` for every step, including initialization. State
machines call `stateMachine.advanceAndApply(delta)`; that method already
advances/applies its artboard, so the helper does not double-advance it. The
animation's real authored loop, speed, and range are retained. `target_time`
means elapsed replay time, while `animation_time` reports the actual runtime
animation-local time.

Bool and number events call the matching typed input's `value()`, and trigger
events call `fire()`. Pointer events use real pointerDown/Up/Move/Exit methods;
coordinates are in the authored artboard coordinate system, not the 512-pixel
output viewport. Pointer-up/down use the primary button. No wall clock,
external input service, or host-side random choice drives these selected cases.

## Auditable metadata

`status=completed` means driver execution finished; hosts save this metadata
only after successful PNG output. `artboard_index` and `selected_index` identify
the actual imported objects. API counters include initialization. For animation,
all three advance/apply counters are `advance_count + 1`. For state machines,
`state_machine_advance_and_apply` equals `advance_count + 1 +
event_settle_advance_count`. `advance_count` counts positive-delta ticks only.

`events_applied` preserves timestamp, integer tick, type, name and value (or
pointer position/id). `final_inputs` reads real bool/number values. A trigger's
production API exposes `fire()` but not its transient fired flag, so it reports
the observed helper call count as `fire_count`, not an invented boolean value.

`state_changes` comes from public `stateChangedCount/stateChangedByIndex` after
each advance, mapped by pointer identity to the real machine layer/state
indices and core type. Animation states include the actual animation name.
The native public API does not expose an authored name for every state; the
helper does not invent names. It reports the final changed state per layer per
advance, not an exhaustive internal transition callback stream. Multiple
transitions inside one native advance can be collapsed by the native reporting
API. `current_animations` reports the public runtime's active animation names
and times; blend states can legitimately have no single current animation.

## Selected cases and evidence boundary

Run `prepare_fixtures.py` to copy exact bytes from the pinned runtime's
`tests/unit_tests/assets` into `fixtures/`, and generate the five cases and
`fixtures/playback/scenarios.json`. This manifest includes fixture SHA256,
named API selections, upstream unit-test locations, sample times, visible-change
requirements and no-events control times. It covers `Bounce`, rocket bool
Hover/Press, numbered rectangle/ellipse transitions, repeated trigger state
changes, and a pointer-driven boolean switch. Repeated samples use separate
processes replaying the same full history, which keeps the one-PNG host simple.

`inspect_fixtures.sh` builds a small native inspector with `NoOpFactory` only
to enumerate actual imported artboards, animations and inputs. It supplies no
rendering evidence. `check_syntax.py` uses real generated UE flags to check the
header without writing shared object outputs. Final acceptance requires the
actual two-host RHI screenshot comparisons and no-events visual controls.

These are five finite examples, not whole-library animation/state-machine
acceptance. Scripting, GPU Canvas/Ore, arbitrary external assets, dynamic view
model binding, arbitrary input devices, random transitions, and editor/UMG
composition are outside this playback experiment. The independent canonical
UE shader archive experiment is a separate evidence gate.

## First actual Lite diagnostic

`artifacts/playback/lite-smoke-01/summary.json` records 19 actual Lite keyframe
captures plus six same-time no-events controls, all with normal process exit.
The GPU-free namespace hides both `/dev/dxg` and `/dev/dri`; the host logs select
llvmpipe and report `render_path=UE_RHI_RDG RiveDrawCompleted=1`. All required
within-case changes and input-effect controls have nonzero pixel differences:
Bounce 57136 pixels, Hover 614, Press 4825, number control 21484/57555,
trigger 16248, and pointer switch 26576. Actual state/animation metadata changes
alongside those input effects. The fixture inspector reports zero
Random-transition state flags in all selected machines.

This diagnostic uses the independently invoked Lite shader helper archive and
does not establish canonical UE cooking equivalence or paired native archive
acceptance. The final paired harness owns those additional gates.

The later full independent run is now recorded in
`artifacts/playback-independent-02/review-summary.json`. All 30 pairs passed
exact RGBA/alpha comparison across 60 fresh no-GPU processes, including all
19 dynamic keyframes and six no-events control pairs. Actual metadata matched;
all 16 required within-case picture changes and 12 per-host input effects
passed. Both archives were separately cooked and cover the same 11,360 Rive
permutations. The first independent failure exposed a missing DXC identity in
the Lite offline compiler's feather branch; that compiler-only correction did
not change this playback header or either host's simulation/rendering algorithm.
The selected-case and per-screenshot replay limits above still apply.
