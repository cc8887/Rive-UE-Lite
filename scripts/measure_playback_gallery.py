#!/usr/bin/env python3
"""Render a local HTML index of original PNGs in a playback matrix report.

No images are decoded, rewritten, composited or generated. All acceptance
labels come from the retained report; this gallery does not change any gate.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
from urllib.parse import quote


def escaped(value) -> str:
    return html.escape(str(value), quote=True)


def render_gallery(report: dict, report_path: Path, output_path: Path) -> str:
    def link(path: str) -> str:
        return escaped(quote(Path(os.path.relpath(Path(path), output_path.parent)).as_posix(), safe="/"))

    def badge(status: str) -> str:
        return f'<span class="badge {escaped(status)}">{escaped(status)}</span>'

    def input_text(result: dict) -> str:
        metadata = result.get("gates", {}).get("playback", {}).get("metadata", {})
        events = metadata.get("events_applied", [])
        if not events:
            return "无已应用输入"
        values = []
        for event in events:
            detail = event.get("name", f"({event.get('x', '')}, {event.get('y', '')})")
            value = f"={json.dumps(event['value'], ensure_ascii=False)}" if "value" in event else ""
            values.append(f"t={event.get('time')} {event.get('type')} {detail}{value}")
        return "; ".join(values)

    def image_card(side: str, result: dict) -> str:
        run = result.get("run", {})
        path = run.get("output_png")
        image = run.get("png", {})
        label = "Reference" if side == "reference" else "Lite"
        src = link(path) if path else ""
        figure = (f'<a href="{src}" title="打开原始 PNG"><img src="{src}" '
                  f'width="{escaped(image.get("width", 512))}" height="{escaped(image.get("height", 512))}" '
                  f'alt="{label} 原始截图" loading="lazy"></a>' if path else '<p class="missing">没有 PNG</p>')
        return (f'<section class="capture"><h4>{label} {badge(result.get("status", "incomplete"))}</h4>'
                f'<div class="pixels">{figure}</div><p class="inputs">{escaped(input_text(result))}</p>'
                f'<details><summary>driver / 证据</summary><pre>{escaped(json.dumps(result.get("gates", {}), ensure_ascii=False, indent=2))}</pre></details></section>')

    def frame_row(frame: dict, control: bool = False) -> str:
        pixels = frame.get("pixels", {})
        diff = f'RGBA 不同像素 {pixels.get("different_pixels", "缺失")}；alpha 不同像素 {pixels.get("alpha_different_pixels", "缺失")}'
        label = "无输入控制组" if control else "完整 timeline"
        cards = "".join(image_card(side, frame.get("hosts", {}).get(side, {})) for side in ("reference", "lite"))
        effect = ""
        if control:
            entries = []
            for side in ("reference", "lite"):
                value = frame.get("hosts", {}).get(side, {}).get("input_effect", {})
                entries.append(f'{side}: 事件图与同刻无输入图不同像素 {value.get("pixels", {}).get("different_pixels", "缺失")}；'
                               f'状态差异字段 {", ".join(value.get("state_evidence_different_fields", [])) or "缺失"}')
            effect = f'<p>{escaped(" | ".join(entries))}</p>'
        return (f'<article class="frame"><h3>t={escaped(frame.get("target_time"))}s · {label} '
                f'{badge(frame.get("status", "incomplete"))}</h3><p>{escaped(diff)}</p>{effect}<div class="pair">{cards}</div></article>')

    sections, nav = [], []
    for case in [*report.get("static_fixtures", []), *report.get("scenarios", [])]:
        identifier = case["id"]
        nav.append(f'<a href="#{quote(identifier, safe="")}">{escaped(identifier)}</a>')
        frames = "".join(frame_row(frame) for frame in case.get("frames", []))
        controls = "".join(frame_row(control, True) for control in case.get("input_effect_controls", []))
        changes = [{"host": item["host"], "from": item["required_change"]["from"], "to": item["required_change"]["to"],
                    "status": item["status"], "different_pixels": item["comparison"].get("different_pixels")}
                   for item in case.get("changes", [])]
        sections.append(f'<section id="{escaped(identifier)}"><h2>{escaped(identifier)} {badge(case.get("status", "incomplete"))}</h2>'
                        f'<p>{escaped(case.get("scope", "真实播放与输入时间线"))}</p>'
                        f'<p>fixture SHA-256: <code>{escaped(case.get("fixture", {}).get("sha256", "缺失"))}</code></p>'
                        f'<details><summary>关键帧内容变化</summary><pre>{escaped(json.dumps(changes, ensure_ascii=False, indent=2))}</pre></details>'
                        f'{frames}{controls}</section>')
    cook = report.get("gates", {}).get("independent_shader_cooks", {})
    provenance_rows = []
    for side in ("lite", "reference"):
        evidence = cook.get(side, {})
        provenance = evidence.get("provenance")
        anchor = f'<a href="{link(provenance)}">provenance JSON</a>' if provenance else "缺失 provenance"
        provenance_rows.append(f'<li>{escaped(side)} {badge(evidence.get("status", "incomplete"))}: {anchor}; '
                               f'archive SHA-256 <code>{escaped(evidence.get("archive", {}).get("sha256", "缺失"))}</code></li>')
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rive 独立 shader cook 多帧对照</title><style>
body{font:15px/1.5 system-ui,sans-serif;color:#17212b;background:#eef2f5;margin:0;padding:24px}
main{max-width:1160px;margin:auto}h1,h2,h3,h4{line-height:1.3}h2{margin-top:36px}h4{margin:0 0 10px}
nav{display:flex;gap:14px;flex-wrap:wrap}a{color:#1459a3}.frame{background:white;border:1px solid #ccd5df;border-radius:8px;margin:18px 0;padding:18px}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}.capture{min-width:0}.pixels{overflow:auto;background-color:#fff;background-image:conic-gradient(#e4e4e4 25%,transparent 0 50%,#e4e4e4 0 75%,transparent 0);background-size:16px 16px}
img{display:block;max-width:none}.badge{font-size:12px;font-weight:600;padding:2px 7px;border-radius:5px;background:#fff0c2;color:#715409}.passed{background:#d7efdf;color:#145d2c}.failed{background:#ffe0df;color:#942727}
pre{overflow:auto;max-height:350px;font-size:12px;background:#f6f8fa;padding:10px}code{word-break:break-all;font-size:12px}.inputs{overflow-wrap:anywhere;font-size:13px}.notice{border-left:4px solid #52748e;padding:10px 14px;background:white}.missing{color:#942727}
@media(max-width:850px){body{padding:12px}.pair{grid-template-columns:1fr}}
</style></head><body><main>''' + (
        f'<h1>Rive 独立 shader cook 多帧对照 {badge(report.get("status", "incomplete"))}</h1>'
        f'<p><a href="{link(str(report_path.resolve()))}">完整机器报告</a></p>'
        '<p class="notice">直接引用原始 PNG，未生成拼接图、缩略图或修改像素。图片按原始尺寸显示，可滚动并点击查看原文件。棋盘格仅用于显示透明背景。'
        '门槛为全图编码 RGBA8/alpha 精确相同；选择场景的结论不扩展到整个 Rive 库、Editor 视口或 UMG 合成。</p>'
        f'<ul>{"".join(provenance_rows)}</ul><nav>{"".join(nav)}</nav>{"".join(sections)}</main></body></html>')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = (args.output or args.summary.with_name("gallery.html")).resolve()
    report = json.loads(args.summary.read_text())
    output.write_text(render_gallery(report, args.summary, output), encoding="utf-8")
    print(json.dumps({"status_from_report": report.get("status", "incomplete"), "output": str(output),
                      "scenarios": len(report.get("scenarios", [])), "static_fixtures": len(report.get("static_fixtures", [])),
                      "images_modified": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
