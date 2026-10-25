#!/usr/bin/env python3
"""Stop only this prototype's mounted-filesystem native build process tree."""
import json
import os
from pathlib import Path
import signal
import time

target_suffix = b"/Source/RiveLiteRenderer/build_native_linux.sh"
processes = {}
roots = []
for directory in Path("/proc").iterdir():
    if not directory.name.isdecimal():
        continue
    try:
        pid = int(directory.name)
        args = (directory / "cmdline").read_bytes().split(b"\0")
        status = (directory / "status").read_text()
        parent = int(next(line for line in status.splitlines() if line.startswith("PPid:")).split()[1])
    except (OSError, StopIteration):
        continue
    processes[pid] = parent
    if any(arg.endswith(target_suffix) for arg in args):
        roots.append(pid)
targets = set(roots)
while True:
    children = {pid for pid, parent in processes.items() if parent in targets}
    if children <= targets:
        break
    targets |= children
for pid in sorted(targets, reverse=True):
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
time.sleep(0.3)
print(json.dumps({"root_pids": roots, "terminated_pids": sorted(targets)}))
