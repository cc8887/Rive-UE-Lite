#!/usr/bin/env python3
"""Record real CPU-only Vulkan enumeration without a GPU or third-party Python.

This is environment evidence only: it does not load UE or Rive, render a pixel,
measure a renderer, or establish equivalence with a UE reference screenshot.
"""
from __future__ import annotations

import argparse
import ctypes as C
import ctypes.util
import datetime
import hashlib
import json
import os
import platform
import re
import stat
import subprocess
import sys
import time
from pathlib import Path


class ApplicationInfo(C.Structure):
    _fields_ = [("sType", C.c_uint32), ("pNext", C.c_void_p),
                ("pApplicationName", C.c_char_p), ("applicationVersion", C.c_uint32),
                ("pEngineName", C.c_char_p), ("engineVersion", C.c_uint32),
                ("apiVersion", C.c_uint32)]


class InstanceCreateInfo(C.Structure):
    _fields_ = [("sType", C.c_uint32), ("pNext", C.c_void_p), ("flags", C.c_uint32),
                ("pApplicationInfo", C.POINTER(ApplicationInfo)),
                ("enabledLayerCount", C.c_uint32), ("ppEnabledLayerNames", C.POINTER(C.c_char_p)),
                ("enabledExtensionCount", C.c_uint32), ("ppEnabledExtensionNames", C.POINTER(C.c_char_p))]


class AlignedPropertyStorage(C.Union):
    # VkPhysicalDeviceProperties is larger than the fixed prefix used below and
    # includes 64-bit members. Reserve enough aligned storage for the whole ABI.
    _fields_ = [("alignment", C.c_uint64), ("data", C.c_ubyte * 4096)]


class DriverProperties(C.Structure):
    _fields_ = [("sType", C.c_uint32), ("pNext", C.c_void_p), ("driverID", C.c_uint32),
                ("driverName", C.c_char * 256), ("driverInfo", C.c_char * 256),
                ("conformanceVersion", C.c_ubyte * 4)]


class Properties2(C.Structure):
    _fields_ = [("sType", C.c_uint32), ("pNext", C.c_void_p), ("properties", AlignedPropertyStorage)]


class QueueFamilyProperties(C.Structure):
    _fields_ = [("queueFlags", C.c_uint32), ("queueCount", C.c_uint32),
                ("timestampValidBits", C.c_uint32), ("minImageTransferGranularity", C.c_uint32 * 3)]


def version(value: int) -> dict:
    return {"raw": value, "variant": value >> 29, "major": (value >> 22) & 127,
            "minor": (value >> 12) & 1023, "patch": value & 4095,
            "text": f"{(value >> 22) & 127}.{(value >> 12) & 1023}.{value & 4095}"}


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def capture(command: list[str]) -> dict:
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, check=False, timeout=30, env=dict(os.environ, LC_ALL="C"))
        return {"command": command, "exit_code": result.returncode, "output": result.stdout}
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": command, "error": str(error)}


def device_node(path: Path) -> dict:
    try:
        info = path.stat()
        return {"path": str(path), "exists": True, "mode": stat.filemode(info.st_mode),
                "is_character_device": stat.S_ISCHR(info.st_mode), "readable": os.access(path, os.R_OK),
                "writable": os.access(path, os.W_OK)}
    except OSError as error:
        return {"path": str(path), "exists": False, "reason": str(error)}


def mapped_libraries() -> list[str]:
    try:
        result = set()
        for line in Path("/proc/self/maps").read_text().splitlines():
            fields = line.split(maxsplit=5)
            if len(fields) == 6 and fields[5].startswith("/") and not fields[5].endswith(" (deleted)"):
                path = Path(fields[5])
                if path.is_file() and ".so" in path.name:
                    result.add(str(path.resolve()))
        return sorted(result)
    except OSError:
        return []


def inventory(roots: list[str]) -> dict:
    libraries, probes, missing = {}, [], []

    def include(path: str):
        actual = Path(path).resolve()
        if actual.is_file():
            libraries[str(actual)] = {"path": str(actual), "bytes": actual.stat().st_size, "sha256": digest(actual)}
        else:
            missing.append(path)

    for root in sorted(set(roots)):
        include(root)
        result = capture(["ldd", root])
        probes.append(result)
        if result.get("exit_code") != 0:
            missing.append(f"ldd did not complete: {root}")
        for line in result.get("output", "").splitlines():
            match = re.search(r"=>\s+(/\S+)", line) or re.search(r"^\s*(/\S+)\s+\(", line)
            if match:
                include(match.group(1))
            elif "not found" in line:
                missing.append(line.strip())
    return {"status": "passed" if roots and not missing else "incomplete",
            "root_libraries": sorted(set(roots)), "libraries": list(libraries.values()),
            "deduplicated_file_bytes": sum(entry["bytes"] for entry in libraries.values()),
            "missing": missing, "ldd": probes,
            "scope": "observed Vulkan loader/ICD roots plus their ELF ldd closure; host OS runtime disk bytes, not a Rive package measurement"}


def checked(result: int, operation: str):
    if result != 0:
        raise RuntimeError(f"{operation}: VkResult={result}")


def enumerate_vulkan(report: dict) -> None:
    loader_name = ctypes.util.find_library("vulkan") or "libvulkan.so.1"
    loader = C.CDLL(loader_name)
    loader_version = C.c_uint32(1 << 22)
    if hasattr(loader, "vkEnumerateInstanceVersion"):
        loader.vkEnumerateInstanceVersion.argtypes = [C.POINTER(C.c_uint32)]
        loader.vkEnumerateInstanceVersion.restype = C.c_int32
        checked(loader.vkEnumerateInstanceVersion(C.byref(loader_version)), "vkEnumerateInstanceVersion")
    requested = min(loader_version.value, (1 << 22) | (3 << 12))
    app = ApplicationInfo(0, None, b"RiveUELiteEnvironmentProbe", 1, b"NoEngineProbe", 1, requested)
    create = InstanceCreateInfo(1, None, 0, C.pointer(app), 0, None, 0, None)
    instance = C.c_void_p()
    loader.vkCreateInstance.argtypes = [C.POINTER(InstanceCreateInfo), C.c_void_p, C.POINTER(C.c_void_p)]
    loader.vkCreateInstance.restype = C.c_int32
    loader.vkDestroyInstance.argtypes = [C.c_void_p, C.c_void_p]
    loader.vkDestroyInstance.restype = None
    start = time.perf_counter()
    checked(loader.vkCreateInstance(C.byref(create), None, C.byref(instance)), "vkCreateInstance")
    report["probe_instance_creation_seconds"] = time.perf_counter() - start
    report["loader"] = {"library_name": loader_name, "supported_api_version": version(loader_version.value),
                         "requested_api_version": version(requested), "enabled_layers": [], "enabled_extensions": []}
    try:
        loader.vkEnumeratePhysicalDevices.argtypes = [C.c_void_p, C.POINTER(C.c_uint32), C.POINTER(C.c_void_p)]
        loader.vkEnumeratePhysicalDevices.restype = C.c_int32
        count = C.c_uint32()
        checked(loader.vkEnumeratePhysicalDevices(instance, C.byref(count), None), "vkEnumeratePhysicalDevices(count)")
        devices = (C.c_void_p * count.value)()
        checked(loader.vkEnumeratePhysicalDevices(instance, C.byref(count), devices), "vkEnumeratePhysicalDevices(devices)")
        loader.vkGetPhysicalDeviceProperties.argtypes = [C.c_void_p, C.c_void_p]
        loader.vkGetPhysicalDeviceProperties.restype = None
        loader.vkGetPhysicalDeviceQueueFamilyProperties.argtypes = [C.c_void_p, C.POINTER(C.c_uint32), C.POINTER(QueueFamilyProperties)]
        loader.vkGetPhysicalDeviceQueueFamilyProperties.restype = None
        report["physical_devices"] = []
        kinds = {0: "OTHER", 1: "INTEGRATED_GPU", 2: "DISCRETE_GPU", 3: "VIRTUAL_GPU", 4: "CPU"}
        for index, handle in enumerate(devices[:count.value]):
            raw = AlignedPropertyStorage()
            loader.vkGetPhysicalDeviceProperties(handle, C.byref(raw))
            prefix = bytes(raw.data)
            values = [int.from_bytes(prefix[offset:offset + 4], sys.byteorder) for offset in (0, 4, 8, 12, 16)]
            api, driver, vendor, identity, kind = values
            device = {"index": index, "api_version": version(api), "driver_version_raw": driver,
                      "vendor_id": vendor, "vendor_id_hex": f"0x{vendor:04x}", "device_id": identity,
                      "device_id_hex": f"0x{identity:04x}", "device_type": kinds.get(kind, "UNKNOWN"),
                      "device_type_raw": kind, "device_name": prefix[20:276].split(b"\0", 1)[0].decode(errors="replace"),
                      "pipeline_cache_uuid_hex": prefix[276:292].hex()}
            if api >= (1 << 22) | (2 << 12) and hasattr(loader, "vkGetPhysicalDeviceProperties2"):
                driver_properties = DriverProperties()
                driver_properties.sType = 1000196000  # VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES
                props2 = Properties2()
                props2.sType = 1000059001  # VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2
                props2.pNext = C.addressof(driver_properties)
                loader.vkGetPhysicalDeviceProperties2.argtypes = [C.c_void_p, C.POINTER(Properties2)]
                loader.vkGetPhysicalDeviceProperties2.restype = None
                loader.vkGetPhysicalDeviceProperties2(handle, C.byref(props2))
                device["driver_properties"] = {"driver_id": driver_properties.driverID,
                                                "driver_name": driver_properties.driverName.decode(errors="replace"),
                                                "driver_info": driver_properties.driverInfo.decode(errors="replace"),
                                                "conformance_version": list(driver_properties.conformanceVersion)}
            queues = C.c_uint32()
            loader.vkGetPhysicalDeviceQueueFamilyProperties(handle, C.byref(queues), None)
            queue_array = (QueueFamilyProperties * queues.value)()
            loader.vkGetPhysicalDeviceQueueFamilyProperties(handle, C.byref(queues), queue_array)
            device["queue_families"] = [{"index": i, "queue_count": queue.queueCount, "flags": queue.queueFlags,
                                          "graphics": bool(queue.queueFlags & 1), "compute": bool(queue.queueFlags & 2),
                                          "transfer": bool(queue.queueFlags & 4)} for i, queue in enumerate(queue_array)]
            report["physical_devices"].append(device)
        report["mapped_shared_libraries"] = mapped_libraries()
        roots = [path for path in report["mapped_shared_libraries"] if re.search(r"libvulkan(?:_|\.)", Path(path).name)]
        report["driver_elf_dependency_closure"] = inventory(roots)
        report["cpu_only_enumeration"] = bool(report["physical_devices"]) and all(device["device_type"] == "CPU" for device in report["physical_devices"])
        report["status"] = "passed" if report["cpu_only_enumeration"] else "failed"
    finally:
        loader.vkDestroyInstance(instance, None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--icd", type=Path, default=Path("/usr/share/vulkan/icd.d/lvp_icd.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"schema_version": 1, "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "status": "incomplete", "scope": "environment Vulkan instance/enumeration probe only",
              "is_ue_rive_rendering_evidence": False, "rendered_pixels": False,
              "renderer_performance_measured": False,
              "host": {"platform": platform.platform(), "kernel": platform.release(), "machine": platform.machine(),
                       "python": sys.version, "logical_cpu_count": os.cpu_count(),
                       "uid": os.getuid() if hasattr(os, "getuid") else None,
                       "effective_uid": os.geteuid() if hasattr(os, "geteuid") else None,
                       "gid": os.getgid() if hasattr(os, "getgid") else None},
              "device_exposure": {"wsl_dxg": device_node(Path("/dev/dxg")),
                                  "dri_nodes": [device_node(path) for path in sorted(Path("/dev/dri").glob("*"))]},
              "environment_before": {name: os.environ.get(name) for name in ("VK_ICD_FILENAMES", "VK_DRIVER_FILES", "DISPLAY", "WAYLAND_DISPLAY")}}
    for source, field in (("/etc/os-release", "os_release"), ("/proc/meminfo", "meminfo")):
        try:
            report["host"][field] = Path(source).read_text()
        except OSError as error:
            report["host"][field] = str(error)
    try:
        cpu = Path("/proc/cpuinfo").read_text()
        report["host"]["cpu_model_names"] = sorted(set(re.findall(r"^model name\s*:\s*(.+)$", cpu, re.M)))
        report["host"]["mount_namespace"] = os.readlink("/proc/self/ns/mnt")
        process_status = Path("/proc/self/status").read_text()
        report["host"]["process_restrictions"] = dict(re.findall(r"^(CapEff|CapBnd|CapAmb|NoNewPrivs):\s*(\S+)", process_status, re.M))
        report["host"]["namespace_device_hiding_requested"] = os.environ.get("RIVE_UE_LITE_GPU_DEVICES_HIDDEN") == "1"
    except OSError:
        pass
    try:
        if not sys.platform.startswith("linux"):
            raise RuntimeError("run the probe on Linux")
        icd = args.icd.resolve(strict=True)
        report["icd"] = {"path": str(icd), "sha256": digest(icd), "json": json.loads(icd.read_text())}
        os.environ["VK_ICD_FILENAMES"] = os.environ["VK_DRIVER_FILES"] = str(icd)
        os.environ.pop("DISPLAY", None)
        os.environ.pop("WAYLAND_DISPLAY", None)
        report["environment_effective"] = {name: os.environ.get(name) for name in ("VK_ICD_FILENAMES", "VK_DRIVER_FILES", "DISPLAY", "WAYLAND_DISPLAY")}
        report["isolation"] = "Vulkan loader forced to the sole specified ICD; WSL /dev/dxg exposure does not mean hardware GPU was used"
        enumerate_vulkan(report)
    except (OSError, ValueError, RuntimeError) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return {"passed": 0, "failed": 1, "incomplete": 2}[report["status"]]


if __name__ == "__main__":
    sys.exit(main())
