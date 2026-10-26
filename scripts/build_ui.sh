#!/usr/bin/env bash
# Build exactly one runtime flavor. Shader cooking and packaging are explicit.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
# Mac keeps the same default lightweight target. Its cooker/reference are explicit
# development commands, and optional Linux hosts are not silently enabled there.
PLATFORM="$(uname -s)"
FORWARD=()
for ARG in "$@"; do
    case "$ARG" in
        --platform=macos) PLATFORM=Darwin ;;
        --platform=linux) PLATFORM=Linux ;;
        *) FORWARD+=("$ARG") ;;
    esac
done
if [[ "$PLATFORM" == Darwin ]]; then
    exec bash "$TASK_ROOT/scripts/build_macos.sh" "${FORWARD[@]}"
fi
set -- "${FORWARD[@]}"
TARGET=RiveRhiLite
FLAVOR=rive
PLAN_ONLY=0
WITH_VERSE=0
WITH_WIDGET_BP=0
ALL_TOOLS=0
ARGS=()
for ARG in "$@"; do
    case "$ARG" in
        --with-umg) TARGET=RiveUmgHost; FLAVOR=umg ;;
        --with-verse) WITH_VERSE=1 ;;
        --with-widget-blueprint) WITH_WIDGET_BP=1 ;;
        --all-tools) ALL_TOOLS=1 ;;
        --plan) PLAN_ONLY=1 ;;
        --help|-h) echo 'Usage: build_ui.sh [--platform=linux|macos] [--with-umg] [--with-verse] [--with-widget-blueprint] [--all-tools] [--plan] [UBT arguments]'; exit 0 ;;
        --*) echo "Unknown option: $ARG" >&2; exit 2 ;;
        *) ARGS+=("$ARG") ;;
    esac
done
if [[ "$ALL_TOOLS" == 1 ]]; then
    TARGET=RiveUmgHost; FLAVOR=umg; WITH_VERSE=1; WITH_WIDGET_BP=1
    printf 'RIVE_TOOLKIT_BUILD target=RiveRhiLite target=RiveUmgHost target=RiveVerseWorker target=RiveUmgBlueprintWorker\n'
fi
printf 'RIVE_UI_BUILD flavor=%s target=%s umg=%s\n' "$FLAVOR" "$TARGET" "$([[ "$FLAVOR" == umg ]] && echo 1 || echo 0)"
[[ "$WITH_VERSE" == 0 ]] || printf 'RIVE_VERSE_BUILD target=RiveVerseWorker backend=VerseVM process=separate\n'
[[ "$WITH_WIDGET_BP" == 0 ]] || printf 'WIDGET_BP_BUILD target=RiveUmgBlueprintWorker editor=1 process=separate\n'
[[ "$PLAN_ONLY" == 0 ]] || exit 0
if [[ "$FLAVOR" == umg || "$WITH_WIDGET_BP" == 1 ]]; then
    python3 "$TASK_ROOT/scripts/prepare_umg_content.py"
fi
# Preserve the isolation/cache location authorized by AGENTS.md.
export RIVE_LITE_CACHE_ROOT="${RIVE_LITE_CACHE_ROOT:-/home/yuchencui/.cache/rive-ue-lite-20261024}"
if [[ "$WITH_VERSE" == 1 ]]; then
    python3 "$TASK_ROOT/scripts/prepare_verse_vm.py"
fi
if [[ "$WITH_VERSE" == 1 || "$WITH_WIDGET_BP" == 1 ]]; then
    if [[ "$ALL_TOOLS" == 1 ]]; then
        bash "$TASK_ROOT/scripts/build_linux_cached.sh" RiveRhiLite "${ARGS[@]}"
    fi
    bash "$TASK_ROOT/scripts/build_linux_cached.sh" "$TARGET" "${ARGS[@]}"
    if [[ "$WITH_VERSE" == 1 ]]; then
        bash "$TASK_ROOT/scripts/build_linux_cached.sh" RiveVerseWorker "${ARGS[@]}"
    fi
    if [[ "$WITH_WIDGET_BP" == 1 ]]; then
        exec bash "$TASK_ROOT/scripts/build_linux_cached.sh" RiveUmgBlueprintWorker -NoDebugInfo -NoDumpSyms "${ARGS[@]}"
    fi
    exit 0
fi
exec bash "$TASK_ROOT/scripts/build_linux_cached.sh" "$TARGET" "${ARGS[@]}"
