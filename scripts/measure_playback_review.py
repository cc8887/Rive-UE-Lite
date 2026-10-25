#!/usr/bin/env python3
"""Summarize a completed playback matrix and audit its original PNG gallery.

This reads retained evidence only. It never renders, edits pixels, or changes
the matrix's acceptance gates. A failed matrix stays failed in the summary.
"""
from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from compare_png import sha256


class GalleryLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images, self.links = [], []

    def handle_starttag(self, tag, attrs):
        fields = dict(attrs)
        if tag == "img":
            self.images.append(fields.get("src", ""))
        if tag == "a" and fields.get("href") and not fields["href"].startswith("#"):
            self.links.append(fields["href"])


def review(report: dict, summary: Path, gallery: Path) -> tuple[dict, dict]:
    groups = [*report.get("static_fixtures", []), *report.get("scenarios", [])]
    frames = [frame for group in groups for frame in [*group.get("frames", []), *group.get("input_effect_controls", [])]]
    captures = [capture for frame in frames for capture in frame.get("hosts", {}).values()]
    errors = []
    links = GalleryLinks()
    if gallery.is_file():
        links.feed(gallery.read_text(encoding="utf-8"))
    else:
        errors.append("gallery file missing")
    bad_links = [value for value in [*links.images, *links.links]
                 if not value or urlparse(value).scheme or not (gallery.parent / unquote(value)).is_file()]
    changed_pngs = []
    expected_images = set()
    for capture in captures:
        run = capture.get("run", {})
        path = Path(run.get("output_png", ""))
        expected_images.add(str(path.resolve()))
        expected = run.get("png", {}).get("sha256")
        if not expected or not path.is_file() or sha256(path) != expected:
            changed_pngs.append(str(path))
    if not captures:
        errors.append("no retained captures")
    if len(links.images) != len(captures) or len(set(links.images)) != len(captures):
        errors.append("gallery must directly reference each retained original PNG exactly once")
    referenced_images = {str((gallery.parent / unquote(value)).resolve()) for value in links.images if not urlparse(value).scheme}
    if referenced_images != expected_images:
        errors.append("gallery image paths differ from original PNG paths in the retained report")
    audit = {
        "status": "failed" if errors or bad_links or changed_pngs else "passed",
        "gallery": str(gallery.resolve()),
        "gallery_sha256": sha256(gallery) if gallery.is_file() else None,
        "img_elements": len(links.images), "original_png_files": len(set(links.images)),
        "local_links_checked": len(links.images) + len(links.links),
        "bad_links": bad_links, "pngs_missing_or_changed": changed_pngs, "errors": errors,
        "original_png_path_sets_equal": referenced_images == expected_images,
        "images_modified": False, "report_status": report.get("status", "incomplete"),
        "scope": "HTML relative references and original raw PNG hashes only; does not change matrix acceptance"}
    failed_pairs = [{"case": group["id"], "time": frame.get("target_time"),
                     "different_pixels": frame.get("pixels", {}).get("different_pixels"),
                     "alpha_different_pixels": frame.get("pixels", {}).get("alpha_different_pixels"),
                     "max_channel_error": frame.get("pixels", {}).get("max_channel_error")}
                    for group in groups for frame in [*group.get("frames", []), *group.get("input_effect_controls", [])]
                    if frame.get("pixels", {}).get("status") != "passed"]
    controls = [capture["input_effect"] for group in report.get("scenarios", [])
                for frame in group.get("input_effect_controls", []) for capture in frame.get("hosts", {}).values()
                if "input_effect" in capture]
    changes = [change for group in report.get("scenarios", []) for change in group.get("changes", [])]
    cook = report.get("gates", {}).get("independent_shader_cooks", {})
    compact = {
        "status": report.get("status", "incomplete"), "summary_sha256": sha256(summary),
        "normal_exit_with_png": sum(capture.get("run", {}).get("exit_code") == 0 and "png" in capture.get("run", {}) for capture in captures),
        "capture_count": len(captures), "pair_count": len(frames),
        "exact_rgba_alpha_passed_pairs": sum(frame.get("pixels", {}).get("status") == "passed" for frame in frames),
        "failed_pairs": failed_pairs,
        "all_host_draw_playback_cpu_gates_passed": bool(captures) and all(capture.get("status") == "passed" for capture in captures),
        "required_image_changes": {"passed": sum(change.get("status") == "passed" for change in changes), "total": len(changes)},
        "same_time_input_effect_checks": {"passed": sum(control.get("status") == "passed" for control in controls), "total": len(controls)},
        "all_inputs_unchanged": report.get("gates", {}).get("render_inputs_and_binaries_unchanged", {}).get("status", "incomplete"),
        "source_pins": report.get("gates", {}).get("source_pins", {}).get("pins", {}),
        "host_executables": report.get("host_executables", {}),
        "independent_cooks": {side: {"status": cook.get(side, {}).get("status", "incomplete"),
                                      "archive": cook.get(side, {}).get("archive", {}),
                                      "execution_id": cook.get(side, {}).get("execution_id"),
                                      "total_permutations": cook.get(side, {}).get("compiled_permutation_count"),
                                      "rive_permutations": cook.get(side, {}).get("rive_permutation_count")}
                              for side in ("lite", "reference")},
        "driver_cache_policy": report.get("driver_cache_policy", {}),
        "gallery": str(gallery.resolve()), "gallery_audit_status": audit["status"],
        "measurement_scope": "correctness only; prior package/performance reports remain separate",
        "failure_policy": "exact RGBA8 and alpha without tolerance or mask; failed evidence retained unchanged"}
    return compact, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--gallery", type=Path)
    args = parser.parse_args()
    summary = args.summary.resolve()
    compact, audit = review(json.loads(summary.read_text()), summary, (args.gallery or summary.with_name("gallery.html")).resolve())
    for name, value in (("review-summary.json", compact), ("gallery-audit.json", audit)):
        summary.with_name(name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report_status": compact["status"], "gallery_audit": audit["status"],
                      "captures": compact["capture_count"], "exact_pairs": compact["exact_rgba_alpha_passed_pairs"],
                      "summary": str(summary.with_name("review-summary.json"))}, indent=2))
    return 0 if compact["status"] == audit["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
