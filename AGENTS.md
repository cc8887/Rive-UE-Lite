# Prototype scope

All implementation, downloaded dependencies, builds and evidence for this experiment belong under this independent directory. Never modify G:/Github/UnrealEngine, F:/Github/rive-unreal, or existing Unreal projects.

Performance exception: isolated disposable Linux build staging is permitted under /home/yuchencui/.cache/rive-ue-lite-20261024 only. Copy sources/dependencies there; never link writable build paths to original projects. Keep its total disk use below 8 GiB initially, record provenance, and return deliverables/evidence to this directory. This exception addresses slow NTFS header I/O and does not relax the isolation of existing projects.

Preserve Rive's UE RHI/RDG rendering algorithm and shaders. Do not substitute native Rive Vulkan, Skia, Canvas, or NullRHI as evidence that the UE rendering path works.

Required validation: no Engine/Renderer in the actual build/link receipt, Linux CPU-only Vulkan device evidence, a rendered PNG, an equivalent UE reference capture, a measured deployable package, peak RSS and first-image time. Distinguish blocked or incomplete measurements from passed gates.

Ownership: the root agent owns environment setup, host program and integration; rive_adapter_audit owns Source/RiveLiteRenderer and its isolated shader staging; ue_lite_bootstrap owns patches to engine/Engine/Source/Runtime/VulkanRHI only; a metrics agent may own scripts/measure and scripts/compare.
