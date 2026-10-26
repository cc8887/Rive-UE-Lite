#!/usr/bin/env bash
# Build exactly one runtime flavor. Shader cooking and packaging are explicit.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
TARGET=RiveRhiLite
FLAVOR=rive
PLAN_ONLY=0
WITH_VERSE=0
ARGS=()
for ARG in "$@"; do
    case "$ARG" in
        --with-umg) TARGET=RiveUmgHost; FLAVOR=umg ;;
        --with-verse) WITH_VERSE=1 ;;
        --plan) PLAN_ONLY=1 ;;
        --help|-h) echo 'Usage: build_ui.sh [--with-umg] [--with-verse] [--plan] [UBT arguments]'; exit 0 ;;
        --*) echo "Unknown option: $ARG" >&2; exit 2 ;;
        *) ARGS+=("$ARG") ;;
    esac
done
printf 'RIVE_UI_BUILD flavor=%s target=%s umg=%s\n' "$FLAVOR" "$TARGET" "$([[ "$FLAVOR" == umg ]] && echo 1 || echo 0)"
[[ "$WITH_VERSE" == 0 ]] || printf 'RIVE_VERSE_BUILD target=RiveVerseWorker backend=VerseVM process=separate\n'
[[ "$PLAN_ONLY" == 0 ]] || exit 0
if [[ "$FLAVOR" == umg ]]; then
    python3 "$TASK_ROOT/scripts/prepare_umg_content.py"
fi
# Preserve the isolation/cache location authorized by AGENTS.md.
export RIVE_LITE_CACHE_ROOT="${RIVE_LITE_CACHE_ROOT:-/home/yuchencui/.cache/rive-ue-lite-20261024}"
if [[ "$WITH_VERSE" == 1 ]]; then
    python3 "$TASK_ROOT/scripts/prepare_verse_vm.py"
    bash "$TASK_ROOT/scripts/build_linux_cached.sh" "$TARGET" "${ARGS[@]}"
    exec bash "$TASK_ROOT/scripts/build_linux_cached.sh" RiveVerseWorker "${ARGS[@]}"
fi
exec bash "$TASK_ROOT/scripts/build_linux_cached.sh" "$TARGET" "${ARGS[@]}"
