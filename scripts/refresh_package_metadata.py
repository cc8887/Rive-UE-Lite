"""Refresh the launcher and metadata; never change the compiled executable/archive."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package_dir", type=Path)
    args = parser.parse_args()
    package = args.package_dir.resolve()
    if not package.is_relative_to(ROOT / "package"):
        raise RuntimeError("Only a staged package inside this prototype can be refreshed")
    path = package / "package-manifest.json"
    manifest = json.loads(path.read_text())
    source = ROOT / "prototype/runtime/render.sh"
    target = package / "render.sh"
    shutil.copy2(source, target)
    for item in manifest["files"]:
        if item["path"] == "render.sh":
            item.update(bytes=target.stat().st_size, sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    manifest["scope"] = "application payload includes the fallback Vulkan loader; selected system loader, CPU ICD and their host dependency closure are inventoried separately"
    manifest["empty_shader_mapping_directories"] = ["Engine/Shaders"]
    manifest["payload_bytes_excluding_manifest"] = sum(item["bytes"] for item in manifest["files"])
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(path)


if __name__ == "__main__":
    main()
