#!/usr/bin/env python3
"""Generate the UE RHI shader names/strings with the pinned Rive minifier.

This uses the upstream `--raw_shaders` / rebuild_shaders.sh human-readable
mode. UE's generated uniform metadata requires the original token names. It
does not compile Vulkan shaders: final UE cooking still requires UE's compiler.
All output remains inside the standalone prototype and its vendor checkout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def copy_tree(source: Path, target: Path) -> int:
    count = 0
    for path in sorted(source.rglob("*")):
        if path.is_file():
            output = target / path.relative_to(source)
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, output)
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor", type=Path, default=ROOT / "vendor/rive-unreal")
    parser.add_argument("--ply", type=Path, default=ROOT / "vendor/ply-3.11")
    parser.add_argument("--output", type=Path, help="Default: vendor runtime/out/linux/release/include")
    args = parser.parse_args()
    vendor = args.vendor.resolve()
    if ROOT not in vendor.parents:
        raise RuntimeError("Only a vendor checkout inside this standalone prototype may be modified")
    runtime = vendor / "submodules/rive-runtime"
    source = runtime / "renderer/src/shaders"
    output = (args.output or runtime / "out/linux/release/include").resolve()
    if ROOT not in output.parents:
        raise RuntimeError("Generated output must remain inside this prototype")
    generated = output / "generated/shaders"
    generated.mkdir(parents=True, exist_ok=True)
    # Exact GNU Make wildcard ordering: sorted GLSL, then vert, then frag.
    inputs = [path.name for suffix in ("*.glsl", "*.vert", "*.frag") for path in sorted(source.glob(suffix))]
    subprocess.run([sys.executable, "minify.py", "--human-readable", "-p", str(args.ply.resolve()), "-o", str(generated), *inputs], cwd=source, check=True)
    required = generated / "rhi.glsl.exports.h"
    if not required.is_file():
        raise RuntimeError(f"Minifier did not produce {required}")

    includes = vendor / "Source/ThirdParty/RiveLibrary/Includes"
    staged_headers = sum(copy_tree(runtime / relative, includes) for relative in ("include", "renderer/include", "decoders/include"))
    shader_includes = includes / "rive/shaders"
    shader_includes.mkdir(parents=True, exist_ok=True)
    for filename in ("constants.glsl", "flush_uniforms.glsl"):
        shutil.copyfile(source / filename, shader_includes / filename)
    for path in sorted(generated.iterdir()):
        if path.is_file() and "minified" not in path.name:
            destination = includes / "rive/generated/shaders" / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
    wrappers = vendor / "Shaders/Private/Rive"
    staged_wrappers = copy_tree(source / "unreal", wrappers)
    for path in sorted(generated.iterdir()):
        if path.is_file() and "minified" in path.name:
            filename = path.stem + ".ush" if path.suffix == ".glsl" else path.name + ".ush"
            destination = wrappers / "Generated" / filename
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            # The wrappers' non-generated-uniform fallback includes this one
            # file from their own directory rather than from Generated/.
            if filename == "flush_uniforms.minified.ush":
                shutil.copyfile(path, wrappers / filename)
    subprocess.run([sys.executable, str(Path(__file__).with_name("stage_adapter.py")), "--source", str(vendor), "--generated-include-root", str(output)], check=True)
    print(json.dumps({"minified_input_count": len(inputs), "shader_token_names_preserved": True, "generated_export_header": str(required), "staged_headers": staged_headers, "staged_wrappers": staged_wrappers, "ue_shader_bytecode_compiled": False}))


if __name__ == "__main__":
    main()
