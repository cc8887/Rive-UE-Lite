"""Stage only build dependencies into the isolated checkout; source is read-only."""
from pathlib import Path
import argparse
import json
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ALLOW = [
    "Directory.*", "global.json", "Engine/Source/ThirdParty/**",
    "Engine/Source/Programs/**", "Engine/Build/**",
    "Engine/Binaries/ThirdParty/DotNet/10.0/linux-x64/**",
    "Engine/Binaries/ThirdParty/ICU/**", "Engine/Binaries/ThirdParty/OpenSSL/**",
    "Engine/Binaries/ThirdParty/Vulkan/Linux/libvulkan.so",
    "Engine/Binaries/ThirdParty/ShaderConductor/Linux/x86_64-unknown-linux-gnu/libdxcompiler.so",
    "Engine/Binaries/ThirdParty/ShaderConductor/Linux/x86_64-unknown-linux-gnu/libShaderConductor.so",
    "Engine/Binaries/Linux/dump_syms",
    "Engine/Binaries/Linux/BreakpadSymbolEncoder",
    "Engine/Binaries/Linux/UnrealBuildAccelerator/**",
    "Engine/Binaries/DotNET/EpicGames.Perforce.Native/**",
    "Engine/Source/Runtime/**",
    "Engine/Content/Renderer/TessellationTable.bin",
]
EXCLUDE = ["Win32", "Win64", "Mac", "Android", "IOS", "TVOS", "LinuxArm64", "HoloLens"]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("G:/Github/UnrealEngine"))
    args = parser.parse_args()
    engine = ROOT / "engine"
    (engine / ".gitdepsignore").write_text("# Isolated Linux prototype dependencies\n**\n" + "".join("!" + s + "\n" for s in ALLOW), encoding="utf-8")
    manifest = ET.parse(engine / "Engine/Build/Commit.gitdeps.xml").getroot()
    import fnmatch
    files = []
    copied = 0
    for node in manifest.find("Files"):
        name = node.attrib["Name"]
        if not any(fnmatch.fnmatchcase(name, a) for a in ALLOW):
            continue
        if any(p.lower() in {x.lower() for x in EXCLUDE} for p in Path(name).parts):
            continue
        src, dst = args.source / name, engine / name
        if src.is_file() and not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
        files.append({"path": name, "expected_sha1": node.attrib["Hash"], "present": dst.is_file()})
    out = ROOT / "artifacts/setup/dependency-staging.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    runtime_prefix = "Engine/Source/Runtime/"
    runtime_files = [f["path"].removeprefix(runtime_prefix) for f in files if f["path"].startswith(runtime_prefix)]
    (out.parent / "runtime-dependency-cache.txt").write_text("".join(name + "\n" for name in runtime_files), encoding="utf-8", newline="\n")
    out.write_text(json.dumps({"source_read_only": str(args.source), "copied": copied, "files": files}, indent=2), encoding="utf-8")
    print(json.dumps({"selected": len(files), "copied": copied, "present": sum(x["present"] for x in files), "report": str(out)}))

if __name__ == "__main__":
    main()
