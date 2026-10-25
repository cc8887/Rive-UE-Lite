#!/usr/bin/env python3
"""Stage the existing Rive Unreal RHI/RDG backend without touching its checkout.

Only resource and host adapters are removed. The 2D flush implementation,
pass functions, shader classes and shader sources remain the upstream ones.
Generated shader includes must come from the *same* native runtime build.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


MODULE = Path(__file__).resolve().parent
ROOT = MODULE.parent.parent
FILES = {
    "Source/RiveRenderer/Private/Platform/RenderContextRHIImpl.hpp": "Public/Platform/RenderContextRHIImpl.hpp",
    "Source/RiveRenderer/Private/Platform/RenderContextRHIImpl.cpp": "Private/Platform/RenderContextRHIImpl.cpp",
    "Source/RiveRenderer/Public/TextureRHIImpl.hpp": "Public/TextureRHIImpl.hpp",
    "Source/RiveRenderer/Private/TextureRHIImpl.cpp": "Private/TextureRHIImpl.cpp",
    "Source/RiveRenderer/Private/RenderGraphHelpers/RivePassFunctions.h": "Private/RenderGraphHelpers/RivePassFunctions.h",
    "Source/RiveRenderer/Private/RenderGraphHelpers/RivePassFunctions.cpp": "Private/RenderGraphHelpers/RivePassFunctions.cpp",
    "Source/RiveRenderer/Public/PlatformRHI.h": "Public/PlatformRHI.h",
    "Source/RiveRenderer/Private/PlatformRHI.cpp": "Private/PlatformRHI.cpp",
    "Source/RiveRenderer/Public/Logs/RiveRendererLog.h": "Public/Logs/RiveRendererLog.h",
    "Source/RiveRenderer/Private/Logs/RiveRendererLog.cpp": "Private/Logs/RiveRendererLog.cpp",
    "Source/RiveShaders/Public/RiveShaderTypes.h": "Public/RiveShaderTypes.h",
    "Source/RiveShaders/Private/RiveShaderTypes.cpp": "Private/RiveShaderTypes.cpp",
    "Source/RiveStats/Public/RiveStats.h": "Public/RiveStats.h",
}


def replace_once(text: str, old: str, new: str = "") -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"Expected one occurrence, found {text.count(old)}: {old!r}")
    return text.replace(old, new, 1)


def replace_pattern(text: str, pattern: str, new: str = "") -> str:
    result, count = re.subn(pattern, new, text, flags=re.S)
    if count != 1:
        raise RuntimeError(f"Expected one regex match, found {count}: {pattern}")
    return result


def remove_braced(text: str, start: str, replacement: str = "", expected: int = 1) -> str:
    """Remove one known function or branch, checking balanced source braces."""
    if text.count(start) != expected:
        raise RuntimeError(f"Ambiguous removal anchor: {start!r}")
    begin = text.index(start)
    brace = text.index("{", begin)
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[:begin] + replacement + text[index + 1:]
    raise RuntimeError(f"Unbalanced block at {start!r}")


def patch_context_header(text: str) -> str:
    text = replace_once(text, '#include "UnrealClient.h"\n')
    text = replace_once(text, "class UTexture;\nclass UTexture2D;\n")
    text = replace_once(text, "  RenderTargetRHI(\n      FRHICommandList& RHICmdList,\n      const RHICapabilities& Capabilities,\n      FRenderTarget* InTextureTarget);\n")
    text = remove_braced(text, "  void updateTargetTexture(FRenderTarget* InTextureTarget)")
    text = replace_once(text, "  FRenderTarget* m_renderTarget = nullptr;\n")
    text = replace_once(text, "  static rive::rcp<rive::RenderImage> MakeExternalRenderImage(\n      UTexture* InTargetTexture);\n")
    text = replace_once(text, "  rive::rcp<RenderTargetRHI> makeRenderTarget(\n      FRHICommandListImmediate& RHICmdList,\n      FRenderTarget* InTargetTexture);\n")
    return text


def patch_context_cpp(text: str) -> str:
    for include in ("TextureResource.h", "ScreenPass.h", "Engine/TextureRenderTarget2D.h", "Engine/Texture.h", "Engine/Texture2D.h", "Ore/OrePlatformRHI.h", "Ore/ore_context_rhi.hpp"):
        text = replace_once(text, f'#include "{include}"\n')
    text = replace_once(text, '#include "RenderContextRHIImpl.hpp"', '#include "Platform/RenderContextRHIImpl.hpp"')
    text = remove_braced(text, "RenderTargetRHI::RenderTargetRHI(\n    FRHICommandList& RHICmdList,\n    const RHICapabilities& Capabilities,\n    FRenderTarget* InTextureTarget)")
    text = remove_braced(text, "  if (m_renderTarget)\n")
    old_check = "check(m_rdgTextureTarget || m_textureTarget || m_renderTarget);"
    if text.count(old_check) != 2:
        raise RuntimeError("The two raw/rdg texture validity checks changed upstream")
    text = text.replace(old_check, "check(m_rdgTextureTarget || m_textureTarget);")
    text = remove_braced(text, "  else if (m_renderTarget)\n", expected=2)
    text = remove_braced(text, "  else if (m_renderTarget)\n")
    text = remove_braced(text, "rive::rcp<rive::RenderImage> RenderContextRHIImpl::MakeExternalRenderImage(\n    UTexture* InTargetTexture)")
    text = remove_braced(text, "rive::rcp<RenderTargetRHI> RenderContextRHIImpl::makeRenderTarget(\n    FRHICommandListImmediate& RHICmdList,\n    FRenderTarget* InTargetTexture)")
    text = remove_braced(text, "void RenderContextRHIImpl::ensureCanvasBacking(rive::gpu::RenderCanvas* canvas)", '''// GPU Canvas/Ore is deliberately outside the first prototype's feature set.
// Returning an unbacked canvas lets the runtime report unsupported Canvas.
void RenderContextRHIImpl::ensureCanvasBacking(rive::gpu::RenderCanvas* canvas)
{
  UE_LOG(LogRiveRenderer, Error,
      TEXT("RiveLite: GPU Canvas/Ore is disabled in this prototype."));
}
''')
    text = replace_once(text, "  return OreContextRHI::make();", "  // Ordinary 2D artboards retain the original RHI/RDG renderer.\n  return nullptr;")
    return text


def patch_texture_header(text: str) -> str:
    for include in ("UnrealClient.h", "Engine/Texture.h", "Engine/Texture2D.h", "Engine/TextureRenderTarget2D.h"):
        text = replace_once(text, f'#include "{include}"\n')
    text = replace_once(text, "  // Variants for data binding render targets.\n  TextureRHIImpl(UTextureRenderTarget2D* InTexture);\n\n  // Variant for data binding utextures\n  TextureRHIImpl(UTexture2D* InTexture);\n")
    return replace_once(text, "  TStrongObjectPtr<UTexture> m_UTexture;\n")


def patch_texture_cpp(text: str) -> str:
    text = replace_once(text, '#include "TextureResource.h"\n')
    text = remove_braced(text, "TextureRHIImpl::TextureRHIImpl(UTextureRenderTarget2D* InTexture)")
    text = remove_braced(text, "TextureRHIImpl::TextureRHIImpl(UTexture2D* InTexture)")
    return replace_once(text, "  return m_UTexture.IsValid()\n             ? FTextureRHIRef(m_UTexture->GetResource()->GetTexture2DRHI())\n             : m_texture;", "  return m_texture;")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_head(directory: Path) -> str | None:
    result = subprocess.run(["git", "-C", str(directory), "rev-parse", "HEAD"], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "vendor/rive-unreal")
    parser.add_argument("--generated-include-root", type=Path, help="Native runtime out/<arch>/release/include after shader generation")
    args = parser.parse_args()
    source = args.source.resolve()
    if source == ROOT or ROOT in source.parents and source == MODULE:
        raise RuntimeError("The source must be a Rive Unreal checkout, not the generated module")
    patches = {
        "Public/Platform/RenderContextRHIImpl.hpp": patch_context_header,
        "Private/Platform/RenderContextRHIImpl.cpp": patch_context_cpp,
        "Public/TextureRHIImpl.hpp": patch_texture_header,
        "Private/TextureRHIImpl.cpp": patch_texture_cpp,
    }
    manifest = {"source_commit": git_head(source), "runtime_commit": git_head(source / "submodules/rive-runtime"), "ore_enabled": False, "files": [], "invariants": {}}
    for original, relative in FILES.items():
        original_path = source / original
        original_data = original_path.read_bytes()
        text = original_data.decode("utf-8-sig").replace("\r\n", "\n")
        if relative in patches:
            text = patches[relative](text)
        text = text.replace("RIVERENDERER_API", "RIVELITERENDERER_API").replace("RIVESHADERS_API", "RIVELITERENDERER_API")
        text = text.replace("<RiveShaders/Public/RiveShaderTypes.h>", '"RiveShaderTypes.h"')
        if relative == "Private/RiveShaderTypes.cpp":
            text = replace_once(text, '#include "Interfaces/IPluginManager.h"\n')
        original_text = original_data.decode("utf-8-sig").replace("\r\n", "\n")
        if relative == "Private/Platform/RenderContextRHIImpl.cpp":
            anchor = "void RenderContextRHIImpl::flush(const FlushDescriptor& desc)"
            original_flush = original_text[original_text.index(anchor):]
            output_flush = text[text.index(anchor):]
            if original_flush != output_flush:
                raise RuntimeError("The original 2D RHI/RDG flush implementation must remain identical")
            manifest["invariants"]["flush_implementation_sha256"] = sha(output_flush.encode())
        if relative == "Private/RenderGraphHelpers/RivePassFunctions.cpp":
            if original_text != text:
                raise RuntimeError("The original RHI/RDG pass functions must remain identical")
            manifest["invariants"]["pass_functions_sha256"] = sha(text.encode())
        output = MODULE / relative
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8", newline="\n")
        manifest["files"].append({"upstream": original, "output": str(output.relative_to(ROOT)).replace("\\", "/"), "source_sha256": sha(original_data), "output_sha256": sha(output.read_bytes())})

    # Copy wrappers/assets verbatim. Runtime-generated replacements are staged
    # below if supplied; stale generated files cannot satisfy the preflight.
    for path in sorted((source / "Shaders").rglob("*")):
        if path.is_file():
            output = ROOT / "Shaders" / path.relative_to(source / "Shaders")
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output)
    if args.generated_include_root:
        generated = args.generated_include_root.resolve() / "generated/shaders"
        if not (generated / "rhi.glsl.exports.h").is_file():
            raise RuntimeError(f"Required generated export header is missing: {generated / 'rhi.glsl.exports.h'}")
        for path in sorted(generated.iterdir()):
            if path.is_file() and "minified" in path.name:
                filename = path.stem + ".ush" if path.suffix == ".glsl" else path.name + ".ush"
                output = ROOT / "Shaders/Private/Rive/Generated" / filename
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, output)
        # The native include root remains in the isolated vendor checkout.
        manifest["generated_include_root"] = str(args.generated_include_root.resolve())
    manifest["shaders"] = [{"path": str(path.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(path.read_bytes())} for path in sorted((ROOT / "Shaders").rglob("*")) if path.is_file()]
    (MODULE / "upstream-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"staged_sources": len(FILES), "staged_shaders": len(manifest["shaders"]), "ore_enabled": False, "source_commit": manifest["source_commit"]}))


if __name__ == "__main__":
    main()
