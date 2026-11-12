"""cuda_libs.py - preload pip-shipped NVIDIA libraries by absolute path.

The CUDA runtime libraries arrive as pip wheels (`nvidia-*` packages, the [gpu]
extra) whose .so files live under site-packages/nvidia/*/lib - directories the
dynamic linker never searches on its own, and LD_LIBRARY_PATH set after process
start does not reach dlopen (glibc reads it once). cupy's own wheel-discovery
missed this box's mixed cu12/cu13 layout (measured 2026-08-21: gpu_ready False on
libcublas.so.12 with the wheels installed and importable). The robust cure is the
one cupy itself uses when its discovery works: dlopen each library by ABSOLUTE
path with RTLD_GLOBAL before anything asks for it by soname - once loaded, later
dlopen-by-soname resolves from the process image.

Idempotent, silent on absence (a CPU box preloads nothing), never raises.
"""

from __future__ import annotations

import ctypes
import site
import sys
from pathlib import Path

_DONE = False

# Load order matters loosely (dependencies before dependents); nvjitlink before
# cusolver/cusparse, cublas before cusolver. Families not present are skipped.
_FAMILIES = ("nvjitlink", "cuda_runtime", "cublas", "cufft", "curand",
             "cusparse", "cusolver", "cudnn", "cuda_nvrtc")


def _site_dirs() -> list[Path]:
    dirs = []
    # Respect the interpreter boundary: an isolated Laplace launcher must not
    # borrow native libraries from a disabled user site.
    if site.ENABLE_USER_SITE:
        try:
            dirs.append(Path(site.getusersitepackages()))
        except Exception:
            pass
    for d in site.getsitepackages() if hasattr(site, "getsitepackages") else []:
        dirs.append(Path(d))
    for p in sys.path:
        if p and p.endswith("site-packages"):
            dirs.append(Path(p))
    seen, out = set(), []
    for d in dirs:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def preload() -> int:
    """dlopen every nvidia wheel library found; returns the count loaded."""
    global _DONE
    if _DONE:
        return 0
    _DONE = True
    n = 0
    for sp in _site_dirs():
        nv = sp / "nvidia"
        if not nv.is_dir():
            continue
        lib_dirs = []
        for fam in _FAMILIES:
            lib_dirs += sorted(nv.glob(f"{fam}/lib")) + sorted(nv.glob(f"cu*/{fam}/lib")) \
                        + sorted(nv.glob(f"cu*/lib"))
        for lib_dir in dict.fromkeys(lib_dirs):
            for so in sorted(lib_dir.glob("lib*.so*")):
                try:
                    ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
                    n += 1
                except OSError:
                    pass
    return n
