"""Record source pins and read-only checks of the existing repositories."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def main():
    fixtures = []
    runtime = ROOT / "vendor/rive-unreal/submodules/rive-runtime"
    # The staged runtime path is recorded by the adapter, rather than inferred
    # from the plugin's older .rive_head text file.
    for fixture in sorted((ROOT / "fixtures").glob("*.riv")):
        upstream = runtime / "tests/unit_tests/assets" / fixture.name
        if fixture.read_bytes() != upstream.read_bytes():
            raise RuntimeError(f"Fixture differs from pinned source: {fixture}")
        fixtures.append({"path": fixture.relative_to(ROOT).as_posix(),
                         "upstream_path": "tests/unit_tests/assets/" + fixture.name,
                         "bytes": fixture.stat().st_size,
                         "sha256": hashlib.sha256(fixture.read_bytes()).hexdigest()})
    report = {
        "engine_commit": git(ROOT / "engine", "rev-parse", "HEAD"),
        "rive_unreal_commit": "8461a2dc90924aeadc1f7eed99e6ae2de1b490f0",
        "rive_runtime_gitlink": "47d1cd54ccefd468db7cb26ecc4699ae1723dd85",
        "fixtures": fixtures,
        "existing_repositories": [],
        "isolation_scope": "Existing repository status is checked read-only; no reset, checkout, build or patch is issued there. The four pre-existing Lyra modifications are preserved.",
    }
    for path in (Path("G:/Github/UnrealEngine"), Path("F:/Github/rive-unreal")):
        report["existing_repositories"].append({"path": str(path),
            "head": git(path, "rev-parse", "HEAD"),
            "tracked_status": git(path, "status", "--short", "--untracked-files=no")})
    output = ROOT / "artifacts/source-state.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
