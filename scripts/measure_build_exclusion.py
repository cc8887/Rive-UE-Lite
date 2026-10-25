#!/usr/bin/env python3
"""Audit actual build/link receipts independently of rendering acceptance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from compare_png import sha256
from measure_ue_lite import inspect_build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--receipt", action="append", type=Path, required=True)
    parser.add_argument("--link-map", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = inspect_build(args.receipt, args.link_map, args.executable)
    report.update(scope="Engine/Renderer module linkage exclusion only; no pixel rendering or Rive completion acceptance",
                  is_rive_rendering_evidence=False,
                  executable={"path": str(args.executable.resolve()), "bytes": args.executable.stat().st_size,
                              "sha256": sha256(args.executable)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "recognized_modules": report["recognized_modules"],
                      "forbidden_modules": report["forbidden_modules"], "output": str(args.output)}, indent=2))
    return {"passed": 0, "failed": 1, "incomplete": 2}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
