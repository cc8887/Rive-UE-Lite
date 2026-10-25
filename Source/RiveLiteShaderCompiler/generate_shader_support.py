#!/usr/bin/env python3
"""Extract only UE's View uniform declarations and stereo source generator.

The offline compiler needs these because RenderCore utility shaders include Common.ush.
No Engine object code or game/scene rendering implementation is copied or linked.
The extracted declarations and generation algorithm remain tied to the exact engine commit.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def function(text: str, start: str) -> str:
    begin = text.index(start)
    opening = text.index("{", begin)
    depth = 1
    i = opening + 1
    # The selected generator contains braces in string literals; skip strings/comments.
    while depth:
        token = re.match(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/', text[i:])
        if token:
            i += len(token[0])
            continue
        depth += (text[i] == "{") - (text[i] == "}")
        i += 1
    return text[begin:i]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", type=Path, default=Path(__file__).resolve().parents[2] / "engine")
    args = parser.parse_args()
    engine = args.engine.resolve()
    output = Path(__file__).resolve().parent / "Private/Generated"
    output.mkdir(parents=True, exist_ok=True)
    view_path = engine / "Engine/Source/Runtime/Engine/Public/SceneView.h"
    compiler_path = engine / "Engine/Source/Runtime/Engine/Private/ShaderCompiler/ShaderCompiler.cpp"
    rectangle_path = engine / "Engine/Source/Runtime/Renderer/Private/PostProcess/SceneFilterRendering.h"
    view = view_path.read_text(encoding="utf-8-sig")
    compiler = compiler_path.read_text(encoding="utf-8-sig")
    begin = view.index("#define VIEW_UNIFORM_BUFFER_MEMBER_TABLE")
    instanced = view.index("BEGIN_GLOBAL_SHADER_PARAMETER_STRUCT_WITH_CONSTRUCTOR(FInstancedViewUniformShaderParameters", begin)
    end = view.index("#undef VIEW_UNIFORM_BUFFER_MEMBER_ARRAY_PER_VIEW", instanced)
    end = view.index("\n", end)
    declarations = view[begin:end].replace("ENGINE_API", "")
    atmosphere = (engine / "Engine/Source/Runtime/Engine/Public/EngineDefines.h").read_text(encoding="utf-8-sig")
    shared = (engine / "Engine/Shaders/Shared/ViewDefinitions.h").read_text(encoding="utf-8-sig")
    distance = (engine / "Engine/Source/Runtime/Renderer/Public/GlobalDistanceFieldConstants.h").read_text(encoding="utf-8-sig")
    constants = {
        "MAX_PHYSICS_FIELD_TARGETS": int(re.search(r"#define MAX_PHYSICS_FIELD_TARGETS\s+(\d+)", view)[1]),
        "NUM_ATMOSPHERE_LIGHTS": int(re.search(r"#define NUM_ATMOSPHERE_LIGHTS\s+(\d+)", atmosphere)[1]),
        "SKY_IRRADIANCE_ENVIRONMENT_MAP_VEC4_COUNT": int(re.search(r"#define SKY_IRRADIANCE_ENVIRONMENT_MAP_VEC4_COUNT\s+(\d+)", shared)[1]),
    }
    max_clipmaps = int(re.search(r"MaxClipmaps\s*=\s*(\d+)", distance)[1])
    # No renderer header is included: preserve its source constant in the extracted table.
    declarations = declarations.replace("GlobalDistanceField::MaxClipmaps", str(max_clipmaps))
    header = "// Generated from Epic UE source; Copyright Epic Games, Inc. All Rights Reserved.\n#pragma once\n"
    header += '#include "CoreMinimal.h"\n#include "ShaderParameterStruct.h"\n#include "ShaderParameterMacros.h"\n'
    header += "inline constexpr int TVC_MAX = 2; // SceneView.h ETranslucencyVolumeCascade\n"
    header += "".join(f"#define {key} {value}\n" for key, value in constants.items())
    header += declarations + "\n#undef VIEW_UNIFORM_BUFFER_MEMBER_TABLE\n"
    (output / "LiteViewUniforms.generated.h").write_text(header, encoding="utf-8")
    # OneColorVS<false, *> includes DrawRectangle's three-vector data buffer.
    # Extract only its declaration, without any Renderer headers or implementation.
    rectangle = rectangle_path.read_text(encoding="utf-8-sig")
    rectangle_begin = rectangle.index("BEGIN_GLOBAL_SHADER_PARAMETER_STRUCT( FDrawRectangleParameters,")
    rectangle_end = rectangle.index("END_GLOBAL_SHADER_PARAMETER_STRUCT()", rectangle_begin)
    rectangle_end += len("END_GLOBAL_SHADER_PARAMETER_STRUCT()")
    (output / "LiteDrawRectangleUniforms.generated.h").write_text(
        "// Generated from Epic UE source; Copyright Epic Games, Inc. All Rights Reserved.\n#pragma once\n"
        + rectangle[rectangle_begin:rectangle_end] + "\n", encoding="utf-8")
    functions = function(compiler, "static void GenerateUniformBufferStructMember(") + "\n\n"
    functions += function(compiler, "void GenerateInstancedStereoCode(")
    functions = functions.replace("LogShaderCompilers", "LogRiveLiteShaderCompiler")
    functions = functions.replace("void GenerateInstancedStereoCode(", "static void GenerateInstancedStereoCode(")
    (output / "LiteInstancedStereo.generated.inl").write_text(
        "// Generated from Epic UE source; Copyright Epic Games, Inc. All Rights Reserved.\n" + functions + "\n", encoding="utf-8")
    commit = subprocess.check_output(["git", "-C", str(engine), "rev-parse", "HEAD"], text=True).strip()
    manifest = {"engine_commit": commit, "scope": "Offline shader declarations/generator only; no Engine/Renderer object code", "constants": {**constants, "GlobalDistanceField::MaxClipmaps": max_clipmaps}, "source_files": []}
    for path in (view_path, compiler_path, rectangle_path):
        manifest["source_files"].append({"path": path.relative_to(engine).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest["outputs"] = [{"path": p.name, "bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(output.glob("*.generated.*"))]
    (output / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
