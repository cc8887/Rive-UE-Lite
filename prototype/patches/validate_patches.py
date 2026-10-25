#!/usr/bin/env python3
"""Validate the isolated engine patch bundle without changing its worktree/index."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def main() -> int:
    patch_dir = Path(__file__).resolve().parent
    root = patch_dir.parent.parent
    engine = root / "engine"
    patches = sorted(patch_dir.glob("[0-9][0-9][0-9][0-9]-*.patch"))
    git_env = os.environ.copy()

    def git(*args: str, env: dict[str, str] | None = None) -> dict[str, object]:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args], cwd=engine,
            env=env, text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        return {"exit_code": result.returncode, "diagnostic": result.stdout.strip()}

    report: dict[str, object] = {
        "base_commit": git("rev-parse", "HEAD")["diagnostic"],
        "patches": [],
    }
    with tempfile.TemporaryDirectory(prefix="patch-index-", dir=root / "artifacts" / "setup") as temporary:
        git_env["GIT_INDEX_FILE"] = str(Path(temporary) / "index")
        baseline = git("read-tree", "HEAD", env=git_env)
        if baseline["exit_code"]:
            raise RuntimeError(baseline)
        for patch in patches:
            item = {
                "patch": patch.name,
                "sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
                "bytes": patch.stat().st_size,
                "prefix_apply_check": git("apply", "--cached", "--check", str(patch), env=git_env),
            }
            item["prefix_apply"] = git("apply", "--cached", str(patch), env=git_env)
            item["prefix_reverse_check"] = git("apply", "--cached", "--reverse", "--check", str(patch), env=git_env)
            report["patches"].append(item)
        report["bundle_forward_tree"] = git("write-tree", env=git_env)
        # Snapshot tracked working files in a separate index. Reversing in order
        # handles patches that intentionally build on an earlier patch's hunk.
        git("read-tree", "HEAD", env=git_env)
        patch_paths = sorted({match.group(1) for patch in patches for match in
            re.finditer(r"^diff --git a/(.+) b/.+$", patch.read_text(encoding="utf-8"), re.MULTILINE)})
        report["patch_paths"] = patch_paths
        report["worktree_snapshot"] = git("add", "-A", "-f", "--", *patch_paths, env=git_env)
        report["bundle_reverse"] = []
        for patch in reversed(patches):
            item = {"patch": patch.name}
            item["check"] = git("apply", "--cached", "--reverse", "--check", str(patch), env=git_env)
            item["apply"] = git("apply", "--cached", "--reverse", str(patch), env=git_env)
            report["bundle_reverse"].append(item)
        report["reversed_equals_base"] = git("diff", "--cached", "--exit-code", "HEAD", env=git_env)
    report["worktree_diff_check"] = git("diff", "--check", "HEAD")
    report["modified_tracked_files"] = git("diff", "--name-only", "HEAD")["diagnostic"].splitlines()
    report["uncovered_tracked_changes"] = sorted(set(report["modified_tracked_files"]) - set(report["patch_paths"]))
    checks = [report["bundle_forward_tree"], report["worktree_snapshot"], report["reversed_equals_base"], report["worktree_diff_check"]]
    for item in report["patches"]:
        checks.extend([item["prefix_apply_check"], item["prefix_apply"], item["prefix_reverse_check"]])
    for item in report["bundle_reverse"]:
        checks.extend([item["check"], item["apply"]])
    report["all_passed"] = not report["uncovered_tracked_changes"] and all(item["exit_code"] == 0 for item in checks)
    report["validation_mode"] = "ordered stack from HEAD; reverse current tracked worktree to HEAD using an isolated index"
    destination = patch_dir / "all-patches-validation.json"
    previous = patch_dir / "all-patches-validation-pre-canonical.json"
    if destination.exists() and not previous.exists():
        previous.write_bytes(destination.read_bytes())
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_passed": report["all_passed"], "patch_count": len(patches), "report": str(destination)}))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
