#!/usr/bin/env python3
"""Run a CPU-only Linux prototype and record evidence without guessing results.

Example (output must be outside the package directory):
  python3 scripts/measure_ue_lite.py --executable package/RiveLite \
    --package-dir package --output-dir artifacts/measurement \
    --run-arg=-RenderOffScreen --run-arg=-AllowCPUDevices \
    --run-arg=-Output={output} --reference artifacts/ue-reference.png \
    --receipt build/RiveLite.target --link-map build/RiveLite.rsp

Repeated runs are separate processes with potentially warm OS caches. They are
never labelled as warmed, in-process rendering. Runtime device selection and a
matching UE reference remain separate acceptance gates.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import re
import shlex
import shutil
import signal
import statistics
import subprocess
import sys
import tarfile
import time
import struct
import zlib
from pathlib import Path

from compare_png import compare_images, read_png, sha256


def capture(command: list[str], env: dict | None = None, timeout: int = 30) -> dict:
    try:
        result = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout, check=False)
        return {"command": command, "exit_code": result.returncode, "output": result.stdout}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": command, "error": str(error)}


def summarize_status(gates: dict) -> str:
    statuses = [gate["status"] for gate in gates.values()]
    return "failed" if "failed" in statuses else "incomplete" if "incomplete" in statuses else "passed"


def apply_cpu_profile(cpu_limit: int | None, lp_threads: int | None, env: dict) -> dict:
    before = sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    if cpu_limit is not None:
        if cpu_limit < 1 or before is None or cpu_limit > len(before):
            raise ValueError("cpu-limit must fit the current Linux process affinity")
        os.sched_setaffinity(0, set(before[:cpu_limit]))
    if lp_threads is not None:
        if lp_threads < 1:
            raise ValueError("lp-num-threads must be positive")
        env["LP_NUM_THREADS"] = str(lp_threads)
    return {"host_logical_cpu_count": os.cpu_count(), "affinity_before": before,
            "affinity_effective": sorted(os.sched_getaffinity(0)) if before is not None else None,
            "requested_cpu_limit": cpu_limit, "LP_NUM_THREADS": env.get("LP_NUM_THREADS"),
            "scope": "process affinity and Mesa thread setting; WSL shares its host, not an actual dedicated VM with this CPU count"}


def directory_inventory(path: Path) -> dict:
    entries = {}
    if path.is_dir():
        for file in path.rglob("*"):
            if file.is_file():
                stat = file.stat()
                entries[file.relative_to(path).as_posix()] = {"bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    return entries


def parse_link_modules(text: str) -> set[str]:
    modules = set(re.findall(r"\bModule\.([A-Za-z0-9_]+)(?:\.[0-9]+)?\.(?:cpp|c|mm|cc)\.(?:o|obj)\b", text))
    modules.update(re.findall(r"(?:lib)?Unreal(?:Editor|Game|Server)?-([A-Za-z0-9_]+)\.(?:so|a|lib|dll)\b", text))
    # Non-unity objects are emitted under configuration/module-name directories.
    modules.update(re.findall(r"[/\\](?:Development|Shipping|Debug|DebugGame|Test)[/\\]([A-Za-z0-9_]+)[/\\][^\s\"<>]+\.(?:o|obj)\b", text))
    return modules


def inspect_build(receipts: list[Path], link_maps: list[Path], executable: Path) -> dict:
    evidence, errors, modules = [], [], set()
    product_match = False
    for receipt in receipts:
        try:
            data = json.loads(receipt.read_text(encoding="utf-8-sig"))
            evidence.append({"kind": "UBT receipt", "path": str(receipt.resolve()), "sha256": sha256(receipt)})
            for product in data.get("BuildProducts", []):
                product_path = str(product.get("Path", "")).replace("\\", "/")
                if product_path.rsplit("/", 1)[-1] == executable.name:
                    product_match = True
        except (OSError, ValueError) as error:
            errors.append(f"{receipt}: {error}")
    visited = set()

    def visit(link_map: Path, referenced_by: Path | None = None):
        canonical = link_map.resolve()
        if canonical in visited:
            return
        visited.add(canonical)
        try:
            text = link_map.read_text(encoding="utf-8-sig", errors="replace")
            found = parse_link_modules(text)
            modules.update(found)
            evidence.append({"kind": "link input/map", "path": str(link_map.resolve()), "sha256": sha256(link_map),
                             "referenced_by": str(referenced_by.resolve()) if referenced_by else None,
                             "recognized_modules": sorted(found)})
            # UE's clang driver response commonly delegates all object inputs
            # to a second response via -Wl,@"Target.rsp". Inspect both layers.
            for quoted, single, bare in re.findall(r'''(?:^|[\s,])@(?:"([^"]+)"|'([^']+)'|([^\s,]+))''', text):
                value = quoted or single or bare
                if os.name == "nt" and re.match(r"^/mnt/[a-z]/", value):
                    value = value[5].upper() + ":/" + value[7:]
                nested = Path(value)
                visit(nested if nested.is_absolute() else link_map.parent / nested, link_map)
        except OSError as error:
            errors.append(f"{link_map}: {error}")
    for link_map in link_maps:
        visit(link_map)
    forbidden = sorted(modules & {"Engine", "Renderer"})
    if forbidden:
        status, reason = "failed", "forbidden module occurs in link input/map"
    elif not receipts or not link_maps or not product_match or not {"Core", "RHI", "RenderCore"} <= modules:
        status, reason = "incomplete", "need matching UBT product receipt and complete linker input/map recognizing Core, RHI and RenderCore"
    elif errors:
        status, reason = "incomplete", "some supplied build evidence is unreadable"
    else:
        status, reason = "passed", "supplied link input/map contains rendering core and no Engine/Renderer module"
    return {"status": status, "reason": reason, "forbidden_modules": forbidden,
            "recognized_modules": sorted(modules), "receipt_product_name_matches": product_match,
            "evidence": evidence, "errors": errors,
            "limitation": "receipt product-name match is not cryptographic build provenance; retain original build log and link command with this report"}


def inspect_package(package: Path, executable: Path, archive: Path) -> dict:
    files, symlinks, total, allocated = [], [], 0, 0
    for path in sorted(package.rglob("*")):
        if path.is_symlink():
            symlinks.append({"path": path.relative_to(package).as_posix(), "target": os.readlink(path),
                             "resolves_inside_package": path.resolve().is_relative_to(package)})
        elif path.is_file():
            stat = path.stat()
            total += stat.st_size
            allocated += getattr(stat, "st_blocks", 0) * 512
            files.append({"path": path.relative_to(package).as_posix(), "bytes": stat.st_size})
    with tarfile.open(archive, "w:gz", dereference=False) as stream:
        stream.add(package, arcname=package.name, recursive=True)
    elf = capture(["readelf", "-h", "-d", str(executable)])
    dynamic = capture(["ldd", str(executable)])
    dependencies = []
    for line in dynamic.get("output", "").splitlines():
        match = re.search(r"^\s*(\S+)\s+=>\s+(not found|/[^\s]+)", line)
        if match:
            name, resolved = match.groups()
        else:
            direct = re.search(r"^\s*(/[^\s]+)\s+\(", line)
            if not direct:
                continue
            resolved, name = direct.group(1), Path(direct.group(1)).name
        target = Path(resolved) if resolved != "not found" else None
        dependencies.append({"name": name, "resolved": resolved,
                             "packaged": bool(target and target.resolve().is_relative_to(package)),
                             "resolved_bytes": target.stat().st_size if target and target.exists() else None})
    missing = [dep["name"] for dep in dependencies if dep["resolved"] == "not found"]
    outside = [dep["name"] for dep in dependencies if not dep["packaged"] and dep["resolved"] != "not found"]
    external_symlinks = [entry["path"] for entry in symlinks if not entry["resolves_inside_package"]]
    with executable.open("rb") as stream:
        is_elf = stream.read(4) == b"\x7fELF"
    executable_packaged = executable.is_relative_to(package)
    static_binary = "not a dynamic executable" in dynamic.get("output", "") or "statically linked" in dynamic.get("output", "")
    inspection_complete = elf.get("exit_code") == 0 and (dynamic.get("exit_code") == 0 or static_binary)
    status = "failed" if missing or external_symlinks or not is_elf or not executable_packaged else "incomplete" if not inspection_complete else "passed"
    return {"status": status, "package_dir": str(package), "file_count": len(files),
            "logical_file_bytes": total, "allocated_file_bytes": allocated if sys.platform.startswith("linux") else None,
            "executable_bytes": executable.stat().st_size, "executable_sha256": sha256(executable),
            "executable_is_elf": is_elf, "executable_inside_package": executable_packaged,
            "archive": {"path": str(archive), "bytes": archive.stat().st_size,
            "sha256": sha256(archive), "format": "tar.gz; observed compression output, not a deterministic archive"},
            "files": files, "symlinks": symlinks, "elf_inspection": elf, "ldd_inspection": dynamic,
            "dynamic_dependencies": dependencies, "missing_dependencies": missing,
            "system_dependencies": outside, "external_symlinks": external_symlinks,
            "closure_limit": "ldd covers ELF DT_NEEDED only; Vulkan ICD, dlopen plugins, fonts and shader data must be separately inventoried"}


def reference_provenance(path: Path | None, reference: Path | None, actual: Path | None) -> dict:
    """Bind both captures to caller-provided matching engine/fixture/config metadata.

    This checks consistency and hashes; it does not authenticate the supplied
    capture metadata. Keep UE logs and commands beside this machine report.
    """
    if not path or not reference or not actual:
        return {"status": "incomplete", "reason": "need both PNGs and --reference-evidence"}
    required = ("engine_commit", "rive_unreal_commit", "rive_runtime_commit", "fixture_sha256", "shader_archive_sha256",
                "width", "height", "render_path", "color_space", "alpha_mode", "sample_count",
                "frame_index", "time_seconds", "clear_color")
    try:
        metadata = json.loads(path.read_text(encoding="utf-8-sig"))
        ref, prototype = metadata.get("reference", {}), metadata.get("prototype", {})
        missing = [f"{side}.{key}" for side, values in (("reference", ref), ("prototype", prototype))
                   for key in (*required, "png_sha256") if key not in values or values[key] is None]
        if missing:
            return {"status": "incomplete", "reason": "capture metadata fields missing", "missing_fields": missing}
        different = [key for key in required if ref[key] != prototype[key]]
        hash_matches = ref["png_sha256"] == sha256(reference) and prototype["png_sha256"] == sha256(actual)
        native_reference = ref.get("host_kind") in ("UE editor", "UE Engine program", "UE game")
        path_matches = ref["render_path"] == "UE RHI/RDG"
        status = "failed" if different or not hash_matches or not path_matches else "passed" if native_reference else "incomplete"
        return {"status": status, "metadata": metadata, "metadata_sha256": sha256(path),
                "different_fields": different, "capture_hashes_match": hash_matches,
                "native_ue_reference_host_declared": native_reference,
                "reason": "checked metadata consistency and capture hashes; preserve originating UE logs and commands to audit these declarations"}
    except (OSError, ValueError) as error:
        return {"status": "incomplete", "reason": str(error)}


def cpu_devices(output: str) -> dict:
    types = re.findall(r"deviceType\s*=\s*(?:VK_)?PHYSICAL_DEVICE_TYPE_([A-Z_]+)", output)
    names = re.findall(r"deviceName\s*=\s*(.+)", output)
    return {"status": "incomplete" if not types else "passed" if all(value == "CPU" for value in types) else "failed",
            "device_types": types, "device_names": [value.strip() for value in names]}


def inspect_vulkan_dependencies(icd: Path | None, package: Path, package_report: dict) -> dict:
    """Inventory system loader + ICD + their ELF dependencies separately.

    These bytes must not be hidden in a claim that the application tarball is a
    self-contained deployment. A base-image installation can provide them, but
    the report always exposes that dependency and its observed disk size.
    """
    known = {}
    found, unknown, probes = {}, [], []
    # setpriv --reset-env intentionally installs a regular user's PATH, which
    # commonly omits sbin. Reading the loader cache needs no root privileges.
    tool_path = os.pathsep.join((os.environ.get("PATH", os.defpath), "/sbin", "/usr/sbin"))
    ldconfig_program = shutil.which("ldconfig", path=tool_path) or "ldconfig"
    ldconfig = capture([ldconfig_program, "-p"])
    if ldconfig.get("exit_code") != 0:
        unknown.append({"path": ldconfig_program, "role": "loader cache inspection failed",
                        "error": ldconfig.get("error", ldconfig.get("output", ""))})
    for line in ldconfig.get("output", "").splitlines():
        match = re.search(r"^\s*(\S+)\s+\([^)]*\)\s+=>\s+(/\S+)", line)
        if match and match.group(1) not in known:
            known[match.group(1)] = match.group(2)
    def include(path: Path, role: str):
        if not path.is_file():
            unknown.append({"path": str(path), "role": role})
            return
        resolved = path.resolve()
        key = str(resolved)
        if key not in found:
            found[key] = {"path": key, "roles": [], "bytes": resolved.stat().st_size,
                          "sha256": sha256(resolved), "packaged": resolved.is_relative_to(package.resolve())}
        if role not in found[key]["roles"]:
            found[key]["roles"].append(role)

    app_ldd = package_report.get("ldd_inspection", {})
    app_static = any(marker in app_ldd.get("output", "") for marker in ("statically linked", "not a dynamic executable"))
    if app_ldd.get("exit_code") != 0 and not app_static:
        unknown.append({"path": package_report.get("package_dir"), "role": "application ELF dependency inspection failed",
                        "error": app_ldd.get("error", app_ldd.get("output", "missing ldd inspection evidence"))})
    for dep in package_report.get("dynamic_dependencies", []):
        if dep["resolved"] != "not found":
            include(Path(dep["resolved"]), "application ELF dependency")
        else:
            unknown.append({"path": dep["name"], "role": "application ELF missing dependency"})
    roots = []
    if "libvulkan.so.1" in known:
        roots.append((Path(known["libvulkan.so.1"]), "Vulkan loader"))
    else:
        unknown.append({"path": "libvulkan.so.1", "role": "Vulkan loader not found in ldconfig cache"})
    if icd and icd.is_file():
        try:
            library = json.loads(icd.read_text()).get("ICD", {}).get("library_path")
            if library:
                library_path = Path(library)
                if not library_path.is_absolute():
                    library_path = icd.parent / library_path if "/" in library else Path(known.get(library, library))
                roots.append((library_path, "selected Vulkan ICD"))
            else:
                unknown.append({"path": str(icd), "role": "ICD JSON has no ICD.library_path"})
        except (OSError, ValueError) as error:
            unknown.append({"path": str(icd), "role": str(error)})
    else:
        unknown.append({"path": None, "role": "selected Vulkan ICD not supplied"})
    for library_path, role in roots:
        include(library_path, role)
        probe = capture(["ldd", str(library_path)])
        probe["role"] = role
        probes.append(probe)
        if probe.get("exit_code") != 0:
            unknown.append({"path": str(library_path), "role": f"{role} ELF dependency inspection failed",
                            "error": probe.get("error", probe.get("output", ""))})
        for line in probe.get("output", "").splitlines():
            match = re.search(r"=>\s+(/\S+)", line)
            if not match:
                match = re.search(r"^\s*(/\S+)\s+\(", line)
            if match:
                include(Path(match.group(1)), f"{role} ELF dependency")
            elif "not found" in line:
                unknown.append({"path": line.strip(), "role": f"{role} missing dependency"})
    external = [entry for entry in found.values() if not entry["packaged"]]
    return {"status": "incomplete" if unknown else "passed", "libraries": list(found.values()),
            "loader_cache_probe": ldconfig,
            "icd_manifest": {"path": str(icd.resolve()), "sha256": sha256(icd)} if icd and icd.is_file() else None,
            "inventory_complete": not unknown,
            "external_dependencies_required": bool(external),
            "external_library_bytes_deduplicated": sum(entry["bytes"] for entry in external),
            "package_plus_external_library_bytes": package_report["logical_file_bytes"] + sum(entry["bytes"] for entry in external),
            "standalone_bundle": not external and not unknown,
            "deployment_kind": "self-contained for inventoried ELF libraries" if not external else "application bundle requiring listed host ELF libraries",
            "unresolved": unknown, "dependency_probes": probes,
            "scope": "application DT_NEEDED plus Vulkan loader/selected ICD and their ldd closure; application-specific dlopen, fonts, shaders and other assets need host/package manifest review"}


def runtime_device(log: str) -> dict:
    # Require selected-device evidence rather than an enumeration-only llvmpipe mention.
    selected = re.findall(r"(?im)^.*(?:selected|using|chosen|active).*(?:device|adapter).*$", log)
    capture_adapter_lines = []
    for line in log.splitlines():
        for marker in ("RIVE_LITE_CAPTURE ", "RIVE_UE_REFERENCE_CAPTURE "):
            if marker not in line:
                continue
            try:
                fields = dict(token.split("=", 1) for token in shlex.split(line.split(marker, 1)[1]) if "=" in token)
            except ValueError:
                continue
            # Both source-reviewed capture hosts print GRHIAdapterName here,
            # after their real draw/readback. This identifies the selected RHI
            # device, rather than merely an enumerated adapter.
            if fields.get("render_path") == "UE_RHI_RDG" and fields.get("adapter"):
                capture_adapter_lines.append(line)
    selected.extend(capture_adapter_lines)
    cpu = [line for line in selected if re.search(r"\bCPU\b|llvmpipe|lavapipe|llvm software", line, re.I)]
    gpu = [line for line in selected if re.search(r"DISCRETE_GPU|INTEGRATED_GPU", line)]
    return {"status": "failed" if gpu else "passed" if cpu else "incomplete",
            "selected_device_lines": selected, "cpu_selected_lines": cpu,
            "capture_adapter_source": "GRHIAdapterName after actual capture" if capture_adapter_lines else None,
            "reason": "requires the runtime's selected device identity in its log"}


def rive_draw_evidence(log: str, actual: Path, png: dict | None) -> dict:
    """Require a capture marker bound to this PNG after an actual Rive draw.

    Marker fields are caller declarations whose placement is source-reviewed;
    an image, an exit code, or a clear-only RHI probe cannot replace them.
    """
    lines = [line.split("RIVE_LITE_CAPTURE ", 1)[1] for line in log.splitlines() if "RIVE_LITE_CAPTURE " in line]
    report = {"status": "incomplete", "capture_markers": lines,
              "required_marker_fields": {"path": "absolute PNG path", "width": "PNG width", "height": "PNG height",
                                         "probe_only": "0", "render_path": "UE_RHI_RDG", "RiveDrawCompleted": "1"},
              "scope": "source-reviewed host completion marker plus PNG identity; not independent GPU command tracing"}
    if not lines:
        report["reason"] = "no RIVE_LITE_CAPTURE marker; PNG presence does not prove a Rive draw"
        return report
    parsed = []
    for line in lines:
        try:
            fields = dict(token.split("=", 1) for token in shlex.split(line) if "=" in token)
            parsed.append({key.lower(): value for key, value in fields.items()})
        except ValueError as error:
            report["reason"] = f"malformed capture marker: {error}"
            return report
    # Explicit probe output is always diagnostic, even if a future refactor
    # accidentally appends a Rive completion token to its log.
    if any(fields.get("probe_only") == "1" for fields in parsed):
        report.update(status="failed", reason="probe_only=1 is a clear/readback bootstrap capture, not a Rive draw")
        return report
    matching = [fields for fields in parsed if fields.get("path") and Path(fields["path"]).is_absolute()
                and Path(fields["path"]).resolve() == actual.resolve()]
    if not matching:
        report.update(status="failed", reason="capture marker is not bound to the current absolute output PNG path")
        return report
    fields = matching[-1]
    report["matched_marker"] = fields
    missing = [key for key in ("probe_only", "render_path", "rivedrawcompleted", "width", "height") if key not in fields]
    if missing:
        report.update(reason="Rive draw completion evidence is missing", missing_fields=missing)
        return report
    if fields["probe_only"] != "0" or fields["render_path"] != "UE_RHI_RDG" or fields["rivedrawcompleted"] != "1":
        report.update(status="failed", reason="capture does not declare a completed non-probe Rive UE RHI/RDG draw")
        return report
    if not png:
        report["reason"] = "draw marker exists but no valid emitted PNG was decoded"
        return report
    try:
        dimensions_match = (int(fields["width"]), int(fields["height"])) == (png["width"], png["height"])
    except ValueError:
        dimensions_match = False
    report.update(status="passed" if dimensions_match else "failed",
                  reason="completed Rive UE RHI/RDG draw declared for this PNG" if dimensions_match else "capture marker dimensions differ from decoded PNG")
    return report


def png_complete(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            if stream.read(8) != b"\x89PNG\r\n\x1a\n":
                return False
            stream.seek(-12, os.SEEK_END)
            return stream.read() == b"\x00\x00\x00\x00IEND\xaeB`\x82"
    except (OSError, ValueError):
        return False


def run_once(executable: Path, arguments: list[str], output: Path, index: int,
             directory: Path, env: dict, timeout: float, working_dir: Path) -> dict:
    log_path, time_path = directory / f"run-{index:03d}.log", directory / f"run-{index:03d}.time.txt"
    command = [str(executable)] + [arg.replace("{output}", str(output)).replace("{iteration}", str(index)) for arg in arguments]
    timed_command = ["/usr/bin/time", "-v", "-o", str(time_path), "--", *command]
    record = {"command": command, "output_png": str(output), "log": str(log_path),
              "time_report": str(time_path), "sampling_interval_seconds": 0.01,
              "first_png_wall_seconds": None, "peak_rss_kib": None}
    if output.exists():
        record.update(status="incomplete", reason="refusing to attribute a pre-existing PNG to this run")
        return record
    started, observed = time.perf_counter(), None
    try:
        with log_path.open("wb") as log:
            process = subprocess.Popen(timed_command, env=env, cwd=working_dir, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            while process.poll() is None:
                if observed is None and png_complete(output):
                    observed = time.perf_counter() - started
                if time.perf_counter() - started > timeout:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                    record["timed_out"] = True
                    break
                time.sleep(0.01)
            wall = time.perf_counter() - started
            if observed is None and png_complete(output):
                observed = wall
            record.update(exit_code=process.returncode, process_wall_seconds=wall, first_png_wall_seconds=observed)
        if time_path.exists():
            match = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", time_path.read_text(errors="replace"))
            if match:
                record["peak_rss_kib"] = int(match.group(1))
        log = log_path.read_text(errors="replace")
        record["runtime_device"] = runtime_device(log)
        if output.exists():
            try:
                image = read_png(output)
                record["png"] = {key: value for key, value in image.items() if key != "rgba"}
                record["png"].update(sha256=sha256(output), bytes=output.stat().st_size)
            except (OSError, ValueError, zlib.error, struct.error) as error:
                record["png_error"] = str(error)
        record["rive_draw"] = rive_draw_evidence(log, output, record.get("png"))
        record["status"] = "passed" if process.returncode == 0 and "png" in record and observed is not None and record["peak_rss_kib"] is not None else "failed"
        record["measurement_scope"] = "Rive UE RHI/RDG capture" if record["rive_draw"]["status"] == "passed" else "capture/process metrics only; actual Rive draw not verified"
    except OSError as error:
        record.update(status="incomplete", reason=str(error))
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--package-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--working-dir", type=Path)
    parser.add_argument("--run-arg", action="append", default=[])
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reference-evidence", type=Path, help="JSON with reference/prototype objects: engine_commit, rive_unreal_commit, rive_runtime_commit, fixture_sha256, shader_archive_sha256, width, height, render_path='UE RHI/RDG', color_space, alpha_mode, sample_count, frame_index, time_seconds, clear_color, png_sha256; reference also has host_kind='UE editor'/'UE Engine program'/'UE game'")
    parser.add_argument("--mask", type=Path)
    parser.add_argument("--channel-tolerance", type=int, default=0)
    parser.add_argument("--max-different-fraction", type=float, default=0)
    parser.add_argument("--receipt", action="append", type=Path, default=[])
    parser.add_argument("--link-map", action="append", type=Path, default=[])
    parser.add_argument("--icd", type=Path)
    parser.add_argument("--repeat", type=int, default=3, help="total number of independent process runs")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--cpu-limit", type=int, help="inherit only the first N CPUs from this process's current affinity")
    parser.add_argument("--lp-num-threads", type=int, help="explicit Mesa LP_NUM_THREADS; recorded separately from CPU affinity")
    parser.add_argument("--driver-cache-dir", type=Path, help="fresh, empty Mesa shader disk cache directory; default output-dir/driver-cache")
    args = parser.parse_args()
    executable, package, directory = args.executable.resolve(), args.package_dir.resolve(), args.output_dir.resolve()
    if not executable.is_file() or not package.is_dir():
        parser.error("executable and package-dir must exist")
    if directory.is_relative_to(package):
        parser.error("output-dir must be outside package-dir so archives do not include themselves")
    if args.repeat < 1 or args.timeout <= 0:
        parser.error("repeat and timeout must be positive")
    directory.mkdir(parents=True, exist_ok=True)
    report_path = directory / "report.json"
    report = {"schema_version": 1, "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "host": {"platform": platform.platform(), "machine": platform.machine(), "python": sys.version},
              "gates": {}, "runs": []}
    gates = report["gates"]
    gates["linux_host"] = {"status": "passed" if sys.platform.startswith("linux") else "failed"}
    env = dict(os.environ, LC_ALL="C", LANG="C")
    try:
        report["cpu_execution_profile"] = apply_cpu_profile(args.cpu_limit, args.lp_num_threads, env)
    except ValueError as error:
        parser.error(str(error))
    driver_cache = (args.driver_cache_dir or directory / "driver-cache").resolve()
    if driver_cache.exists() and any(driver_cache.iterdir()):
        parser.error("driver-cache-dir must be new or empty; do not label a previously populated Mesa disk cache as fresh")
    if driver_cache.is_relative_to(package):
        parser.error("driver-cache-dir must be outside the package")
    driver_cache.mkdir(parents=True, exist_ok=True)
    env["MESA_SHADER_CACHE_DIR"] = str(driver_cache)
    report["cache_policy"] = {"MESA_SHADER_CACHE_DIR": str(driver_cache), "fresh_before_preflight": True,
                              "MESA_SHADER_CACHE_DISABLE": env.get("MESA_SHADER_CACHE_DISABLE"),
                              "MESA_DISK_CACHE_SINGLE_FILE": env.get("MESA_DISK_CACHE_SINGLE_FILE"),
                              "first_process": "fresh Mesa shader disk cache; OS page cache state is uncontrolled",
                              "subsequent_processes": "same Mesa disk cache; fresh processes; cache reuse permitted, hits not assumed",
                              "preflight_scope": "Vulkan instance/physical-device enumeration only; no reference render uses this cache"}
    execution_args = list(args.run_arg)
    if not any(value.lower().startswith("-userdir=") for value in execution_args):
        execution_args.append(f"-UserDir={directory / 'ue-user'}/")
    if not any(value.lower().startswith("-abslog=") for value in execution_args):
        execution_args.append(f"-abslog={directory}/run-{{iteration}}.ue.log")
    report["requested_application_output_paths"] = [value for value in execution_args if value.lower().startswith(("-userdir=", "-abslog="))]
    for name in ("DISPLAY", "WAYLAND_DISPLAY"):
        env.pop(name, None)
    icd = args.icd
    if not icd:
        candidates = sorted(Path("/usr/share/vulkan/icd.d").glob("*lvp*.json"))
        icd = candidates[0] if candidates else None
    if icd and icd.is_file():
        env["VK_ICD_FILENAMES"] = env["VK_DRIVER_FILES"] = str(icd.resolve())
        report["software_vulkan_environment"] = {"icd": str(icd.resolve()), "icd_sha256": sha256(icd),
                                                  "icd_json": json.loads(icd.read_text()), "DISPLAY": None, "WAYLAND_DISPLAY": None}
    else:
        gates["software_icd_isolation"] = {"status": "incomplete", "reason": "no Lavapipe ICD found; provide --icd"}
    probe = capture(["vulkaninfo", "--summary"], env)
    report["vulkan_probe"] = probe
    gates["cpu_vulkan_enumeration"] = cpu_devices(probe.get("output", ""))
    if probe.get("exit_code") != 0:
        gates["cpu_vulkan_enumeration"]["status"] = "incomplete"
        # Minimal Linux machines may have the Vulkan loader and Lavapipe but
        # omit vulkan-tools. Query the real Vulkan ABI using the stdlib probe.
        fallback = Path(__file__).with_name("measure_vulkan_probe.py")
        if fallback.is_file() and icd and icd.is_file():
            fallback_output = directory / "vulkan-cpu-probe.json"
            result = capture([sys.executable, str(fallback), "--icd", str(icd), "--output", str(fallback_output)], env)
            report["vulkan_probe_fallback_execution"] = result
            if fallback_output.is_file():
                try:
                    direct = json.loads(fallback_output.read_text(encoding="utf-8"))
                    report["vulkan_probe_fallback"] = direct
                    gates["cpu_vulkan_enumeration"] = {
                        "status": direct.get("status", "incomplete"), "source": "ctypes Vulkan API enumeration",
                        "device_types": [device["device_type"] for device in direct.get("physical_devices", [])],
                        "device_names": [device["device_name"] for device in direct.get("physical_devices", [])]}
                except (OSError, ValueError, KeyError) as error:
                    gates["cpu_vulkan_enumeration"] = {"status": "incomplete", "reason": str(error)}
    if icd and icd.is_file():
        gates["software_icd_isolation"] = {"status": gates["cpu_vulkan_enumeration"]["status"],
                                             "reason": "both Vulkan loader ICD override variables set; CPU enumeration required"}
    gates["engine_renderer_excluded"] = inspect_build(args.receipt, args.link_map, executable)
    package_before = directory_inventory(package)
    gates["package_measurement"] = inspect_package(package, executable, directory / "deploy-package.tar.gz")
    report["runtime_dependency_inventory"] = inspect_vulkan_dependencies(icd, package, gates["package_measurement"])
    gates["runtime_dependency_inventory"] = {
        "status": report["runtime_dependency_inventory"]["status"],
        "reason": "application/loader/ICD ELF closure must be fully inspected; external host libraries are listed separately from the bundle",
        "standalone_bundle": report["runtime_dependency_inventory"]["standalone_bundle"],
        "unresolved": report["runtime_dependency_inventory"]["unresolved"]}
    prohibited_flags = [value for value in args.run_arg if re.search(r"(?:^|\s)-nullrhi(?:\s|$)", value, re.I)]
    gates["real_rendering_requested"] = {"status": "failed" if prohibited_flags else "passed", "prohibited_flags": prohibited_flags}
    has_placeholder = any("{output}" in value for value in args.run_arg)
    if not has_placeholder:
        gates["render_runs"] = {"status": "incomplete", "reason": "pass a --run-arg containing {output}; every run must write its unique PNG"}
    elif not sys.platform.startswith("linux"):
        gates["render_runs"] = {"status": "incomplete", "reason": "measurement requires Linux /usr/bin/time"}
    else:
        for index in range(args.repeat):
            record = run_once(executable, execution_args, directory / f"run-{index:03d}.png", index,
                              directory, env, args.timeout, (args.working_dir or executable.parent).resolve())
            record["cache_phase"] = "first_process_fresh_mesa_disk_cache" if index == 0 else "subsequent_process_reusing_mesa_disk_cache"
            cache_files = directory_inventory(driver_cache)
            record["mesa_cache_after_run"] = {"file_count": len(cache_files), "file_bytes": sum(item["bytes"] for item in cache_files.values())}
            report["runs"].append(record)
        gates["render_runs"] = {"status": summarize_status({str(i): row for i, row in enumerate(report["runs"])})}
    if report["runs"]:
        gates["cpu_vulkan_runtime"] = {"status": summarize_status({str(i): row.get("runtime_device", {"status": "incomplete"}) for i, row in enumerate(report["runs"])})}
        gates["rive_actual_draw"] = {"status": summarize_status({str(i): row.get("rive_draw", {"status": "incomplete"}) for i, row in enumerate(report["runs"])})}
        samples = [row["first_png_wall_seconds"] for row in report["runs"][1:] if row["first_png_wall_seconds"] is not None]
        report["timing"] = {"first_run_png_wall_seconds": report["runs"][0]["first_png_wall_seconds"],
                            "repeated_run_png_wall_seconds": samples,
                            "repeated_run_median_seconds": statistics.median(samples) if samples else None,
                            "cache_policy": "first process starts with fresh Mesa disk cache; later processes reuse that cache; OS page cache is not flushed or claimed cold",
                            "first_image_definition": "time from spawning /usr/bin/time wrapper until complete PNG IEND observed; includes startup, rendering, encoding and file write",
                            "rss_definition": "/usr/bin/time -v maximum resident set size in KiB per process invocation"}
        report["timing"]["rive_draw_verified"] = gates["rive_actual_draw"]["status"] == "passed"
        report["timing"]["measurement_scope"] = "Rive UE RHI/RDG capture" if report["timing"]["rive_draw_verified"] else "capture/process measurements only; not Rive rendering performance evidence"
    else:
        gates["cpu_vulkan_runtime"] = {"status": "incomplete", "reason": "no runtime evidence"}
        gates["rive_actual_draw"] = {"status": "incomplete", "reason": "no runtime evidence"}
    if args.reference and report["runs"] and "png" in report["runs"][0]:
        comparison = compare_images(args.reference, Path(report["runs"][0]["output_png"]),
                                    args.mask, args.channel_tolerance, args.max_different_fraction)
        if gates["rive_actual_draw"]["status"] == "passed":
            gates["ue_reference_pixels"] = comparison
        else:
            report["diagnostic_capture_pixel_comparison"] = comparison
            gates["ue_reference_pixels"] = {"status": "incomplete", "reason": "actual Rive draw gate did not pass; diagnostic capture comparison is not Rive equivalence evidence"}
    else:
        gates["ue_reference_pixels"] = {"status": "incomplete", "reason": "need rendered PNG and corresponding UE reference PNG"}
    actual = Path(report["runs"][0]["output_png"]) if report["runs"] and "png" in report["runs"][0] else None
    gates["ue_reference_provenance"] = reference_provenance(args.reference_evidence, args.reference, actual)
    package_after = directory_inventory(package)
    report["package_execution_mutations"] = {
        "archive_captured_before_application_execution": True,
        "created_files": [{"path": path, **package_after[path]} for path in sorted(package_after.keys() - package_before.keys())],
        "changed_files": [path for path in sorted(package_before.keys() & package_after.keys()) if package_before[path] != package_after[path]],
        "removed_files": sorted(package_before.keys() - package_after.keys()),
        "scope": "generated Saved/log/cache files are reported separately from the pre-execution deployment archive"}
    report["status"] = summarize_status(gates)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(report_path),
                      "gates": {name: value["status"] for name, value in gates.items()}}, indent=2))
    return {"passed": 0, "failed": 1, "incomplete": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
