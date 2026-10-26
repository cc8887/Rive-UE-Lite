# Default Slate content size anchor

Read-only audit of existing `engine/Engine/Build/Commit.gitdeps.xml`, pinned to engine HEAD `62d7c1a7125b52b10ee1b714838f515f3563f795`. The current manifest's normalized Git blob equals the HEAD blob `02a5d3f93d5b595d8338d9eddb8c910e25d84e3b`. The Git tree contains no `Engine/Content/Slate` entries; these files are GitDependencies payloads, not Git LFS pointers. No assets were downloaded or materialized, and Git lazy fetching was disabled for the bounded tree/provenance checks.

`Slate.Build.cs:51-58` stages these four extensions under `Engine/Content/Slate` when bUsesSlate is true:

| File family | Files | Expected extracted bytes | MiB |
|---|---:|---:|---:|
| TTF | 15 | 6,014,148 | 5.7355 |
| PNG | 426 | 1,722,304 | 1.6425 |
| SVG | 355 | 298,609 | 0.2848 |
| TPS | 3 | 1,740 | 0.0017 |
| Total Linux UFS content from these stock rules | 799 | 8,036,801 | 7.6645 |

All 799 file entries have matching Blob Size metadata; none of these 799 files exists in the isolated working tree. The total is path-based logical bytes before filesystem or package deduplication. It does not include source art such as PSD files, which the quoted runtime dependencies do not stage.

The default composite font in `SlateCore/Private/Fonts/LegacySlateFontInfoCache.cpp:94-148` references 13 unique runtime files totaling 5,811,572 bytes (5.5423 MiB); that set is already included in the 7.6645 MiB total. Its largest file is DroidSansFallback.ttf at 3,939,852 bytes (3.7573 MiB). A custom English-only regular font style could restrict font data to Roboto-Regular.ttf, 158,604 bytes (0.1513 MiB), but that would not preserve the default font styles or multilingual coverage.

Separate scope totals, which must not be automatically added as mandatory runtime payload:

- `Engine/Content/SlateDebug`: 2 files, 5,395,968 bytes (5.1460 MiB). The stock rule stages these as DebugNonUFS; a release estimate may explicitly omit them.
- `Engine/Content/Editor/Slate/Fonts`: 17 files, 25,214,140 bytes (24.0461 MiB). These support editor-only font choices, including additional East Asian/emoji fonts; they are not part of the ordinary runtime Slate content subtotal.
- `Engine/Content/EngineFonts`: 16 files, 5,169,838 bytes (4.9303 MiB). This includes uncooked font `.uasset` data and related files. The actual references and cooked result need separate asset closure; this is not a mandatory additive size or a cooked-size measurement.

These are expected raw asset lengths from GitDependencies `Blob Size` metadata, not verified extracted bytes or the size of a compressed deployment archive. `Pack CompressedSize` includes whole CDN packs and cannot be used as per-asset gzip size. Without downloading those actual bytes, no measured compressed increment is available.

A useful raw-content anchor for a stock staged native UMG host is therefore **the existing Reference runtime package proxy plus approximately 7.66 MiB of default Slate UFS resources**, before new Slate shader families, used UI-material shader maps, cooked Widget Blueprint data, project textures/fonts or any other required Engine defaults. It remains a capacity estimate, not a complete usable or rendered UMG package.

Machine-readable inventory: [slate-content-metadata.json](F:/Github/Rive-UE-Lite/artifacts/umg-assessment/slate-content-metadata.json). Reproduce without fetching: `python artifacts/umg-assessment/audit_slate_content_metadata.py`.
