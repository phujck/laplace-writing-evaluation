"""Honest runtime and device receipts for canonical Atlas events.

Atlas never activates a repository-local virtual environment implicitly.  The lexical executable
path is checked before resolution so a symlink into ``.venv`` cannot erase the evidence.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import platform
import site
import sys
import sysconfig
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import TypedDict

from .errors import AtlasError, RuntimePolicyRefused
from .history import DeviceFallback, DeviceReceipt, RuntimeReceipt
from .ids import canonical_json

SYSTEM_INTERPRETER = Path("/usr/bin/python3")


class CudaLibraryReceipt(TypedDict):
    loaded: list[str]
    missing: list[str]
    searched: list[str]


class CudaLibraryMissing(AtlasError):
    reason = "cuda-library-missing"


# Mirror laplace.cuda_libs' dependency order, including its cu*/lib wheel layout.
# cublasLt must precede cublas; auxiliary installed libraries are loaded too because
# cuDNN and NVRTC open some of them lazily by soname.
_CUDA_FAMILIES = (
    ("nvjitlink", ("libnvJitLink",)),
    ("cuda_runtime", ("libcudart",)),
    ("cublas", ("libcublasLt", "libcublas", "libnvblas")),
    ("cufft", ("libcufft", "libcufftw")),
    ("curand", ("libcurand",)),
    ("cusparse", ("libcusparse",)),
    ("cusolver", ("libcusolver", "libcusolverMg")),
    ("cudnn", ("libcudnn",)),
    ("cuda_nvrtc", ("libnvrtc-builtins", "libnvrtc")),
)
_CUDA_REQUIRED = (
    "libnvJitLink", "libcudart", "libcublasLt", "libcublas",
    "libcusparse", "libcusolver", "libcudnn",
)
_CUDA_HANDLES: dict[str, ctypes.CDLL] = {}
_CUDA_RECEIPT: CudaLibraryReceipt | None = None
_CUDA_LOCK = RLock()


def _cuda_site_dirs() -> list[Path]:
    paths = sysconfig.get_paths()
    user = site.getusersitepackages()
    roots = [Path(p) for p in ([user] if isinstance(user, str) else user)]
    roots.extend(Path(paths[key]) for key in ("purelib", "platlib") if paths.get(key))
    roots.extend(Path(p) for p in site.getsitepackages())
    # site and sysconfig already name every site-packages root; the seal forbids the atlas touching
    # the interpreter path at all, even to read it (atlas/tests/test_seal.py::test_no_sys_path_mutation).
    return list(dict.fromkeys(roots))


def _load_cuda_libraries() -> CudaLibraryReceipt:
    searched: list[str] = []
    candidates: list[Path] = []
    roots = _cuda_site_dirs()
    for family, stems in _CUDA_FAMILIES:
        for root in roots:
            nv = root / "nvidia"
            dirs = [nv / family / "lib", *sorted(nv.glob(f"cu*/{family}/lib")),
                    *sorted(nv.glob("cu*/lib"))]
            for directory in dirs:
                if str(directory) not in searched:
                    searched.append(str(directory))
            for stem in stems:
                for directory in dirs:
                    candidates.extend(sorted(directory.glob(f"{stem}.so*")))
            if family == "cudnn":
                for directory in dirs:
                    candidates.extend(sorted(directory.glob("libcudnn_*.so*")))
    pending = list(dict.fromkeys(path.resolve() for path in candidates))
    loaded: list[str] = []
    # Dependencies within a wheel can require a second pass. A failed dlopen is
    # never counted as a load, and only actual successes are cached.
    while pending:
        failed = []
        for path in pending:
            name = str(path)
            try:
                if name not in _CUDA_HANDLES:
                    _CUDA_HANDLES[name] = ctypes.CDLL(name, mode=ctypes.RTLD_GLOBAL)
                loaded.append(name)
            except OSError:
                failed.append(path)
        if len(failed) == len(pending):
            break
        pending = failed
    missing = [f"{stem}.so" for stem in _CUDA_REQUIRED
               if not any(Path(path).name.startswith(f"{stem}.so") for path in loaded)]
    missing.extend(path.name for path in pending if path.name not in missing)
    return {"loaded": loaded, "missing": missing, "searched": searched}


def preload_cuda_libraries() -> CudaLibraryReceipt:
    """Load NVIDIA wheel libraries before GPU imports, without linker env changes.

    Successful calls are idempotent and keep the CDLL handles alive. An incomplete
    load is retried on the next call; GPU-required callers receive a named refusal
    with the complete receipt, even if an earlier optional caller saw the absence.
    """
    global _CUDA_RECEIPT
    with _CUDA_LOCK:
        receipt = _CUDA_RECEIPT or _load_cuda_libraries()
        if not receipt["missing"]:
            _CUDA_RECEIPT = receipt
        result: CudaLibraryReceipt = {key: list(value) for key, value in receipt.items()}
        if result["missing"] and os.environ.get("LAPLACE_REQUIRE_GPU", "").strip().lower() in {
            "1", "true", "yes", "on",
        }:
            raise CudaLibraryMissing(
                "required CUDA libraries could not be loaded: " + ", ".join(result["missing"]),
                **result,
            )
        return result


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def collect_runtime_receipt(
    repo_root: Path,
    *,
    requested_device: str = "cpu",
    observed_devices: tuple[str, ...] | None = None,
    selected_device: str | None = None,
    utilization: dict[str, float | None] | None = None,
    fallback_reason: str | None = None,
    executable: str | Path | None = None,
    observed_at: str | None = None,
) -> RuntimeReceipt:
    """Observe interpreter/device truth, refusing a lexical or resolved repo ``.venv``.

    The dependency-free caller may leave ``observed_devices`` unset, preserving the S0 CPU
    probe.  A device-aware organ supplies what its own runtime actually observed; the selected
    accelerator and utilization then ride the same canonical receipt instead of being trapped
    in an unrelated benchmark file.
    """

    repo_root = Path(repo_root).resolve()
    lexical = Path(sys.executable if executable is None else executable).absolute()
    resolved = lexical.resolve()
    forbidden = repo_root / ".venv"
    if _within(lexical, forbidden) or _within(resolved, forbidden):
        raise RuntimePolicyRefused(
            "repository .venv is not a lawful Atlas runtime",
            executable=str(lexical),
            resolved=str(resolved),
            forbidden=str(forbidden),
        )

    fallbacks: tuple[DeviceFallback, ...] = ()
    available = observed_devices or ("cpu",)
    selected = selected_device or (
        "cpu" if observed_devices is None and requested_device != "cpu" else requested_device
    )
    if selected not in available:
        raise RuntimePolicyRefused(
            "selected device was not observed available",
            selected=selected,
            available=available,
        )
    if requested_device != selected:
        fallbacks = (
            DeviceFallback(
                from_device=requested_device,
                to_device=selected,
                reason=fallback_reason or "requested device was unavailable to the observed runtime",
                acknowledged=True,
            ),
        )
    device = DeviceReceipt(
        requested=requested_device,
        selected=selected,
        available=available,
        utilization=utilization or {device_name: None for device_name in available},
        fallbacks=fallbacks,
    )
    stamp = observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    identity = {
        "executable": str(lexical),
        "expected_executable": str(SYSTEM_INTERPRETER),
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "prefix": sys.prefix,
        "base_prefix": sys.base_prefix,
        "repo_root": str(repo_root),
        "repo_venv_refused": True,
        "device": device.to_dict(),
    }
    receipt_id = "sha256:" + hashlib.sha256(canonical_json(identity).encode()).hexdigest()
    return RuntimeReceipt(
        receipt_id=receipt_id,
        observed_at=stamp,
        executable=str(lexical),
        expected_executable=str(SYSTEM_INTERPRETER),
        implementation=platform.python_implementation(),
        version=platform.python_version(),
        prefix=sys.prefix,
        base_prefix=sys.base_prefix,
        repo_root=str(repo_root),
        repo_venv_refused=True,
        device=device,
    )


__all__ = ["SYSTEM_INTERPRETER", "CudaLibraryMissing", "CudaLibraryReceipt",
           "preload_cuda_libraries", "collect_runtime_receipt"]
