#!/usr/bin/env bash
# Namespace-local bind of an isolated ext4 source cache avoids slow NTFS header IO.
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "$0")/.." && pwd)"
export RIVE_LITE_CACHE_ROOT="${RIVE_LITE_CACHE_ROOT:-/home/yuchencui/.cache/rive-ue-lite-20261024}"
CACHE_ROOT="$RIVE_LITE_CACHE_ROOT/engine-source"
if [[ -n "${UE_GIT_OBJECTS:-}" ]]; then
    export GIT_ALTERNATE_OBJECT_DIRECTORIES="$UE_GIT_OBJECTS"
fi
if [[ "${1:-}" != --inside ]]; then
    [[ "$(id -u)" == 0 ]] || { echo 'Use wsl -u root for the private mount namespace' >&2; exit 2; }
    mkdir -p "$CACHE_ROOT"
    if [[ ! -f "$CACHE_ROOT/.extracted" ]]; then
        tar -xf "$TASK_ROOT/dependencies/engine-runtime.tar" -C "$CACHE_ROOT"
        touch "$CACHE_ROOT/.extracted"
        chown -R 1000:1000 "$CACHE_ROOT"
    fi
    # Subsequent source fixes remain authored in the independent Windows checkout.
    while IFS= read -r CHANGED; do
        RELATIVE="${CHANGED#Engine/Source/Runtime/}"
        SOURCE="$TASK_ROOT/engine/$CHANGED"
        [[ -f "$SOURCE" ]] || continue
        mkdir -p "$(dirname "$CACHE_ROOT/Runtime/$RELATIVE")"
        cp -p "$SOURCE" "$CACHE_ROOT/Runtime/$RELATIVE"
        chown 1000:1000 "$CACHE_ROOT/Runtime/$RELATIVE"
    done < "$TASK_ROOT/artifacts/setup/runtime-cache-updates.txt"
    # Include every selected GitDependencies Runtime payload, even ignored .hh,
    # SDK headers/libraries and data files absent from the tracked source tar.
    rsync -a --files-from="$TASK_ROOT/artifacts/setup/runtime-dependency-cache.txt" \
        "$TASK_ROOT/engine/Engine/Source/Runtime/" "$CACHE_ROOT/Runtime/"
    export RIVE_LITE_ORIGIN_MNT="$(readlink /proc/self/ns/mnt)"
    exec unshare --mount --fork -- bash "$0" --inside "$@"
fi
shift
[[ "$(readlink /proc/self/ns/mnt)" != "$RIVE_LITE_ORIGIN_MNT" ]] || exit 2
mount --make-rprivate /
mount --bind "$CACHE_ROOT/Runtime" "$TASK_ROOT/engine/Engine/Source/Runtime"
exec setpriv --reuid=1000 --regid=1000 --init-groups --reset-env -- \
    env RIVE_LITE_CACHE_ROOT="$RIVE_LITE_CACHE_ROOT" \
    bash "$TASK_ROOT/scripts/build_linux.sh" "$@"
