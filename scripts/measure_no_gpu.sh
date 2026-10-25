#!/usr/bin/env bash
# Hide GPU device nodes in a private mount namespace, then drop root privileges.
# The global WSL /dev is never changed. Run with sudo or `wsl -u root`.
set -euo pipefail

if [[ "${1:-}" != "--inside" ]]; then
    if [[ "$(id -u)" != 0 ]]; then
        echo 'Run this namespace wrapper as root; the measured command runs as uid/gid 1000 by default.' >&2
        exit 2
    fi
    RUN_UID="${RIVE_LITE_RUN_UID:-1000}"
    RUN_GID="${RIVE_LITE_RUN_GID:-1000}"
    [[ "${1:-}" == -- ]] && shift
    if [[ "$#" == 0 ]]; then
        echo 'Usage: measure_no_gpu.sh -- command [args...]' >&2
        exit 2
    fi
    ORIGIN_NAMESPACE="$(readlink /proc/self/ns/mnt)"
    exec unshare --mount --fork -- bash "$0" --inside "$ORIGIN_NAMESPACE" "$RUN_UID" "$RUN_GID" -- "$@"
fi

shift
ORIGIN_NAMESPACE="$1"
RUN_UID="$2"
RUN_GID="$3"
shift 3
[[ "$1" == -- ]] || exit 2
shift
PRIVATE_NAMESPACE="$(readlink /proc/self/ns/mnt)"
if [[ "$PRIVATE_NAMESPACE" == "$ORIGIN_NAMESPACE" || "$ORIGIN_NAMESPACE" != mnt:\[*\] ]]; then
    echo 'Refusing to alter /dev without proof that unshare created a separate mount namespace.' >&2
    exit 2
fi
mount --make-rprivate /
mount -t tmpfs -o nosuid,mode=0755,size=1M rive-lite-private-dev /dev
mknod -m 666 /dev/null c 1 3
mknod -m 666 /dev/zero c 1 5
mknod -m 666 /dev/random c 1 8
mknod -m 666 /dev/urandom c 1 9
mkdir -m 1777 /dev/shm
mount -t tmpfs -o nosuid,nodev,mode=1777,size=256M rive-lite-private-shm /dev/shm
ln -s /proc/self/fd /dev/fd
ln -s /proc/self/fd/0 /dev/stdin
ln -s /proc/self/fd/1 /dev/stdout
ln -s /proc/self/fd/2 /dev/stderr
[[ ! -e /dev/dxg && ! -e /dev/dri ]]
echo "RIVE_LITE_NO_GPU_NAMESPACE origin=$ORIGIN_NAMESPACE private=$PRIVATE_NAMESPACE dxg=absent dri=absent uid=$RUN_UID gid=$RUN_GID" >&2
export RIVE_UE_LITE_GPU_DEVICES_HIDDEN=1
export RIVE_UE_LITE_MOUNT_NAMESPACE="$PRIVATE_NAMESPACE"
unset DISPLAY WAYLAND_DISPLAY
exec setpriv --reuid="$RUN_UID" --regid="$RUN_GID" --init-groups --reset-env \
    --inh-caps=-all --ambient-caps=-all --bounding-set=-all --no-new-privs -- \
    env RIVE_UE_LITE_GPU_DEVICES_HIDDEN=1 RIVE_UE_LITE_MOUNT_NAMESPACE="$PRIVATE_NAMESPACE" "$@"
