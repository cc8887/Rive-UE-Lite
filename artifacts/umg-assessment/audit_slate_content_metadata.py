"""Read existing GitDependencies metadata; never fetch/materialize dependencies."""

from pathlib import Path
from collections import Counter
import hashlib
import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "engine"
MANIFEST = ENGINE / "Engine/Build/Commit.gitdeps.xml"
FONT_SOURCE = ENGINE / "Engine/Source/Runtime/SlateCore/Private/Fonts/LegacySlateFontInfoCache.cpp"
PREFIXES = ("Engine/Content/Slate/", "Engine/Content/SlateDebug/", "Engine/Content/EngineFonts/", "Engine/Content/Editor/Slate/Fonts/")
git_env = dict(os.environ, GIT_NO_LAZY_FETCH="1")
def git(*args):
    return subprocess.check_output(["git", "-C", str(ENGINE), *args], env=git_env, text=True).strip()

git_provenance = {
    "head": git("rev-parse", "HEAD"),
    "manifest_head_blob": git("rev-parse", "HEAD:Engine/Build/Commit.gitdeps.xml"),
    "manifest_worktree_blob": git("hash-object", "--path", "Engine/Build/Commit.gitdeps.xml", "Engine/Build/Commit.gitdeps.xml"),
    "slate_tree_entries": len(git("ls-tree", "-r", "HEAD", "--", "Engine/Content/Slate").splitlines()),
    "lazy_fetch_disabled": True,
}
assert git_provenance["manifest_head_blob"] == git_provenance["manifest_worktree_blob"]
files = []
blobs = {}
needed_hashes = set()

for _, node in ET.iterparse(MANIFEST, events=("end",)):
    if node.tag == "File" and node.attrib["Name"].startswith(PREFIXES):
        files.append(dict(node.attrib))
        needed_hashes.add(node.attrib["Hash"])
    elif node.tag == "Blob" and node.attrib["Hash"] in needed_hashes:
        blobs[node.attrib["Hash"]] = dict(node.attrib)
    node.clear()

for item in files:
    blob = blobs.get(item["Hash"])
    item["expected_bytes"] = int(blob["Size"]) if blob else None
    item["materialized"] = (ENGINE / item["Name"]).is_file()

def summarize(selected):
    return {
        "files": len(selected),
        "expected_bytes": sum(i["expected_bytes"] or 0 for i in selected),
        "expected_mib": round(sum(i["expected_bytes"] or 0 for i in selected) / 1048576, 6),
        "missing_size_records": sum(i["expected_bytes"] is None for i in selected),
        "materialized_files": sum(i["materialized"] for i in selected),
        "unique_hashes": len({i["Hash"] for i in selected}),
    }

slate = [i for i in files if i["Name"].startswith(PREFIXES[0])]
staged = [i for i in slate if Path(i["Name"]).suffix.lower() in {".ttf", ".png", ".svg", ".tps"}]
font_names = set(re.findall(r'APPEND_FONT\([^\n]*?,\s*"[^\"]+",\s*"([^\"]+)"', FONT_SOURCE.read_text(encoding="utf-8")))
default_fonts = [i for i in slate if i["Name"].removeprefix("Engine/Content/Slate/Fonts/") in font_names]
by_extension = {ext: summarize([i for i in staged if Path(i["Name"]).suffix.lower() == ext]) for ext in sorted({Path(i["Name"]).suffix.lower() for i in staged})}
report = {
    "scope": "Existing Commit.gitdeps.xml file->blob Size metadata only; no asset download, cook, compression or render execution",
    "asset_sizes_are_not_lfs_pointer_sizes": True,
    "git_provenance": git_provenance,
    "size_semantics": "GitDependencies Blob Size is expected extracted file length; Pack CompressedSize is not per-file package size",
    "manifest": {"path": str(MANIFEST), "sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest()},
    "font_source": {"path": str(FONT_SOURCE), "sha256": hashlib.sha256(FONT_SOURCE.read_bytes()).hexdigest()},
    "stock_bUsesSlate_linux_staged_extensions": summarize(staged),
    "stock_bUsesSlate_linux_by_extension": by_extension,
    "slate_all_files": summarize(slate),
    "slate_fonts_all": summarize([i for i in slate if "/Fonts/" in i["Name"]]),
    "native_default_font_unique_files": summarize(default_fonts),
    "native_default_font_files": default_fonts,
    "custom_english_regular_font_only": summarize([i for i in slate if i["Name"].endswith("/Roboto-Regular.ttf")]),
    "english_font_warning": "One regular font is a custom restricted style, not full default FCoreStyle or Unicode/font-style equivalence",
    "slate_debug_nonufs_separate": summarize([i for i in files if i["Name"].startswith(PREFIXES[1])]),
    "engine_font_uncooked_uasset_separate": summarize([i for i in files if i["Name"].startswith(PREFIXES[2])]),
    "editor_fonts_not_runtime_default_separate": summarize([i for i in files if i["Name"].startswith(PREFIXES[3])]),
    "stock_stage_files": staged,
    "largest_slate_files": sorted(slate, key=lambda i: i["expected_bytes"] or 0, reverse=True)[:15],
    "limitations": [
        "Expected raw asset lengths come from pinned metadata, not downloaded or hash-verified contents",
        "No compressed increment can be measured without the actual bytes",
        "Does not include new Slate global shaders, used UI-material shader maps, cooked WidgetBlueprint/referenced content or runtime defaults outside these prefixes",
        "SlateDebug is DebugNonUFS and can be excluded from a release estimate explicitly; it is not in the UFS subtotal",
        "Source tree lookup had no Engine/Content/Slate entries; assets are GitDependencies payloads rather than Git/LFS pointers",
    ],
}
output = Path(__file__).with_name("slate-content-metadata.json")
output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k.endswith("separate") or k in {"stock_bUsesSlate_linux_staged_extensions", "stock_bUsesSlate_linux_by_extension", "slate_fonts_all", "native_default_font_unique_files", "custom_english_regular_font_only"}}, ensure_ascii=False, indent=2))
