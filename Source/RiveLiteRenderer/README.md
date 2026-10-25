# Rive UE RHI/RDG slice

The ordinary 2D `flush` implementation and RDG pass implementation are copied
from the pinned Rive UE plugin and checked by `stage_adapter.py`. Their hashes
are recorded in `upstream-manifest.json`. Only the Engine texture wrappers and
Ore/GPU Canvas entry points are excluded from this module.

Native Linux inputs are built by `build_native_ext4.sh` using the isolated
v26 clang 20.1.8 SDK, libc++, C++20, no scripting and no LTO. The UE6 adapter uses
C++23 because the current UE Core headers require `if consteval`. Native library
compiler, sysroot, source pin, flags, ELF/archive checks and hashes are recorded
in `native-build-result.json`; those archive sizes are not an app package size.

All shader generation must use the upstream `--raw_shaders` option, which invokes
the minifier with `--human-readable`. UE's generated uniform metadata uses the
original `uniforms` and field names; default variable mangling produces names
such as `j.P8` that cannot bind to that metadata. The same mode is used by
upstream `build/rebuild_shaders.sh`. `generate_native_shaders.py` reproduces this
step without rebuilding native code. After changing token mode, regenerate all
headers/shaders, rebuild native libraries, and rebuild both UE adapters before
cooking their shader archive.

`validate_source_slice.py` checks source provenance, forbidden module headers,
registered shader include closure and preserved uniform names. It does not
establish successful compilation, a Vulkan draw, image parity or deployable size.
The Engine-enabled reference and its validation boundaries are documented in
`../RiveUeReference/README.md`.
