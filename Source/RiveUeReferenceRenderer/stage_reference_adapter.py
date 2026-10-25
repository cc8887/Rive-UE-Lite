#!/usr/bin/env python3
"""Stage an Engine-enabled reference with upstream Engine texture wrappers."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

MODULE = Path(__file__).resolve().parent
ROOT = MODULE.parents[1]
sys.path.insert(0, str(ROOT / "Source/RiveLiteRenderer"))
from stage_adapter import FILES, git_head, remove_braced, replace_once


def main() -> None:
    source = ROOT / "vendor/rive-unreal"
    manifest = {"source_commit": git_head(source), "runtime_commit": git_head(source / "submodules/rive-runtime"),
                "scope": "Engine/Renderer-linked offscreen reference; no Editor viewport or UMG composition",
                "engine_texture_wrappers": "preserved", "ore_enabled": False, "files": [], "invariants": {}}
    for original, relative in FILES.items():
        original_data = (source / original).read_bytes()
        original_text = original_data.decode("utf-8-sig").replace("\r\n", "\n")
        text = original_text
        if relative == "Private/Platform/RenderContextRHIImpl.cpp":
            text = replace_once(text, '#include "RenderContextRHIImpl.hpp"', '#include "Platform/RenderContextRHIImpl.hpp"')
            for include in ("Ore/OrePlatformRHI.h", "Ore/ore_context_rhi.hpp"):
                text = replace_once(text, f'#include "{include}"\n')
            text = remove_braced(text, "void RenderContextRHIImpl::ensureCanvasBacking(rive::gpu::RenderCanvas* canvas)", '''// Same explicit feature exclusion as the lite adapter.
void RenderContextRHIImpl::ensureCanvasBacking(rive::gpu::RenderCanvas* canvas)
{
  UE_LOG(LogRiveRenderer, Error, TEXT("Rive UE reference: GPU Canvas/Ore is disabled."));
}
''')
            text = replace_once(text, "  return OreContextRHI::make();", "  return nullptr;")
            anchor = "void RenderContextRHIImpl::flush(const FlushDescriptor& desc)"
            expected = original_text[original_text.index(anchor):]
            actual = text[text.index(anchor):]
            if expected != actual:
                raise RuntimeError("The original 2D RHI/RDG flush must remain unchanged")
            manifest["invariants"]["flush_implementation_sha256"] = hashlib.sha256(actual.encode()).hexdigest()
        if relative == "Private/RenderGraphHelpers/RivePassFunctions.cpp":
            if text != original_text:
                raise RuntimeError("The original 2D RDG pass functions must remain unchanged")
            manifest["invariants"]["pass_functions_sha256"] = hashlib.sha256(text.encode()).hexdigest()
        text = text.replace("RIVERENDERER_API", "RIVEUEREFERENCERENDERER_API").replace("RIVESHADERS_API", "RIVEUEREFERENCERENDERER_API")
        text = text.replace("<RiveShaders/Public/RiveShaderTypes.h>", '"RiveShaderTypes.h"')
        output = MODULE / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8", newline="\n")
        manifest["files"].append({"upstream": original, "output": str(output.relative_to(ROOT)).replace("\\", "/"),
                                  "source_sha256": hashlib.sha256(original_data).hexdigest(), "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest()})
    lite = json.loads((ROOT / "Source/RiveLiteRenderer/upstream-manifest.json").read_text())
    if manifest["invariants"] != lite["invariants"]:
        raise RuntimeError("Lite/reference draw algorithms differ")
    manifest["shared_shader_manifest_sha256"] = hashlib.sha256((ROOT / "Source/RiveLiteRenderer/upstream-manifest.json").read_bytes()).hexdigest()
    (MODULE / "upstream-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"staged_sources": len(FILES), "draw_implementations_identical_to_lite": True, "engine_texture_wrappers_preserved": True}))


if __name__ == "__main__":
    main()
