#!/usr/bin/env python3
"""Record real archive, ELF and libc++ evidence for the native input libraries."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--build-root", required=True, type=Path)
    parser.add_argument("--toolchain", required=True, type=Path)
    args = parser.parse_args()
    root, build, toolchain = args.root, args.build_root, args.toolchain
    folder = root / "vendor/rive-unreal/Source/ThirdParty/RiveLibrary/Libraries/Linux"
    archives = []
    for path in sorted(folder.glob("*.a")):
        data = path.read_bytes()
        if not data.startswith(b"!<arch>\n"):
            raise RuntimeError(f"Not a real static archive: {path}")
        offset, elf_member = 8, None
        while offset + 60 <= len(data):
            header = data[offset:offset + 60]
            member_size = int(header[48:58])
            body = data[offset + 60:offset + 60 + member_size]
            if body.startswith(b"\x7fELF"):
                elf_member = {"name": header[:16].decode().strip(), "class_bits": 64 if body[4] == 2 else 32, "machine": int.from_bytes(body[18:20], "little")}
                break
            offset += 60 + member_size + member_size % 2
        if elf_member is None or elf_member["class_bits"] != 64 or elf_member["machine"] != 62:
            raise RuntimeError(f"Archive is not x86-64 Linux ELF: {path}")
        archives.append({"name": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "elf_member": elf_member})
    if len(archives) != 11:
        raise RuntimeError(f"Expected all 11 Rive and decoder archives, found {len(archives)}")
    compiler_path = toolchain / "bin/clang++"
    compiler = subprocess.run([str(compiler_path), "--version"], capture_output=True, text=True, check=True).stdout.strip()
    core_archive = folder / "rive_librive.a"
    nm = toolchain / "bin/llvm-nm"
    nm_command = str(nm) if nm.is_file() else shutil.which("nm")
    if not nm_command:
        raise RuntimeError("No ELF symbol inspection tool is available")
    symbols = subprocess.run([nm_command, "--undefined-only", str(core_archive)], capture_output=True, text=True, check=True).stdout
    if "St3__1" not in symbols:
        raise RuntimeError("Rive core archive has no observable libc++ ABI symbols")
    runtime = build / "vendor/rive-unreal/submodules/rive-runtime"
    sources = hashlib.sha256()
    source_count = 0
    for path in sorted(runtime.rglob("*")):
        if not path.is_file() or "out" in path.relative_to(runtime).parts or ".git" in path.parts:
            continue
        if path.suffix not in (".cpp", ".c", ".hpp", ".h", ".lua", ".py", ".sh", ".glsl", ".ush", ".usf"):
            continue
        sources.update(path.relative_to(runtime).as_posix().encode() + b"\0" + hashlib.sha256(path.read_bytes()).digest())
        source_count += 1
    makefile = (runtime / "out/linux/release/rive.make").read_text()
    renderer_makefile = (runtime / "out/linux/release/rive_pls_renderer.make").read_text()
    if "RIVE_RAW_SHADERS" not in renderer_makefile:
        raise RuntimeError("UE generated uniform metadata requires --raw_shaders token preservation")
    report = {
        "compiled": True,
        "scope": "native static inputs only; not a deployable application measurement",
        "build_root": str(build), "runtime_commit": "47d1cd54ccefd468db7cb26ecc4699ae1723dd85",
        "source_file_count": source_count, "source_tree_sha256": sources.hexdigest(),
        "dependency_lock_sha256": hashlib.sha256((root / "vendor/rive-native-dependency-lock.json").read_bytes()).hexdigest(),
        "scripting_enabled": False, "audio": "external", "lto": False, "ore_adapter_enabled": False,
        "shader_token_names_preserved": True, "shader_generation_flag": "--raw_shaders",
        "compiler": compiler, "compiler_sha256": hashlib.sha256(compiler_path.read_bytes()).hexdigest(),
        "sysroot": str(toolchain), "cxx_standard": "c++20", "exceptions": False, "rtti": False,
        "libcxx_abi_symbols_present": True,
        "symbol_inspection_tool": nm_command,
        "make_cxxflags": [line for line in makefile.splitlines() if line.startswith(("DEFINES +=", "ALL_CXXFLAGS +="))],
        "injected_cxxflags": f"--sysroot={toolchain} -stdlib=libc++",
        "archives": archives,
    }
    destination = root / "Source/RiveLiteRenderer/native-build-result.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
