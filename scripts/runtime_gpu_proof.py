#!/usr/bin/env python3
"""Execute the development GPU stack and emit a read-only JSON receipt."""

from __future__ import annotations

import json
import os
import platform
import tempfile
from importlib import metadata


PROBED_DISTRIBUTIONS = (
    "fastembed",
    "fastembed-gpu",
    "onnxruntime",
    "onnxruntime-gpu",
    "cupy-cuda12x",
    "cupy-cuda13x",
    "cuda-toolkit",
)

# One distribution per shared import namespace. Both members of a pair collide on disk; zero
# members is a profile that cannot embed or cannot fold.
SHARED_NAMESPACES = (
    ("fastembed", ("fastembed", "fastembed-gpu")),
    ("cupy", ("cupy-cuda12x", "cupy-cuda13x")),
)


def _version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def check_distributions(distributions: dict[str, str | None]) -> None:
    """Refuse a layout that cannot bind CUDA, and ONLY such a layout.

    REWRITTEN 2026-09-15, after this gate spent nineteen days refusing a working device. Its
    2026-08-27 form demanded the exact distribution NAMES ``fastembed-gpu``,
    ``onnxruntime-gpu``, ``cupy-cuda13x`` and the exact absence of ``fastembed``,
    ``onnxruntime``, ``cupy-cuda12x``. Two of the three required names were never installed
    here, so the script raised ``GPU profile is incomplete`` in 0.37s and exited 1 without
    ever touching the GPU - while the GPU underneath it embedded at dim 384 and ran real
    float64 GEMMs. The receipt said the stack was broken; the stack was fine; the gate was
    wrong. A proof that dies before the proof is not a proof.

    The rule now matches the actual hazard rather than a remembered package list. The engine's
    own policy already says it: "prove execution, never infer from package presence"
    (runtime_profiles.toml [gpu]). So presence checks are reduced to the minimum that a real
    execution proof cannot cover, and everything else is left to the device:

      * ``onnxruntime-gpu`` must be installed - nothing else supplies CUDAExecutionProvider.
      * ``onnxruntime`` (the CPU wheel) must NOT be installed. This is the one condition the
        execution proof genuinely cannot be trusted on: the CPU wheel overwrites the GPU
        wheel's ``libonnxruntime.so`` and ``onnxruntime_pybind11_state.so`` IN PLACE while
        leaving the 229MB CUDA provider library on disk, so both dist-infos stay registered
        and the EP dies with no error (2026-08-21). Caught here it is one line; uncaught it is
        a night of silent CPU embedding.
      * exactly one distribution per shared import namespace (``fastembed``, ``cupy``).

    Deliberately NOT required: a particular CUDA package family, or the GPU-named fastembed
    and cupy builds. Measured on this box, ONNX Runtime GPU 1.29 binds family 13 and CuPy 14.2
    binds family 12 side by side, both passing their own execution proof - see
    runtime_profiles.toml [gpu].cuda_families. Whether the module came from ``fastembed`` or
    ``fastembed-gpu`` is answered by the embedding it actually performs below, not by a name.
    """
    if distributions.get("onnxruntime-gpu") is None:
        raise RuntimeError(
            f"GPU profile is incomplete: onnxruntime-gpu is not installed, and nothing else "
            f"supplies CUDAExecutionProvider: {distributions}"
        )
    if distributions.get("onnxruntime") is not None:
        raise RuntimeError(
            f"CPU/GPU distributions overlap: the CPU onnxruntime wheel is installed beside "
            f"onnxruntime-gpu and shares its import namespace, which kills the CUDA execution "
            f"provider silently: {distributions}"
        )
    for namespace, pair in SHARED_NAMESPACES:
        installed = [name for name in pair if distributions.get(name) is not None]
        if len(installed) != 1:
            raise RuntimeError(
                f"the `{namespace}` import namespace needs exactly one installed "
                f"distribution, found {installed}: {distributions}"
            )


def main() -> int:
    distributions = {name: _version(name) for name in PROBED_DISTRIBUTIONS}
    check_distributions(distributions)

    os.environ["LAPLACE_REQUIRE_GPU"] = "1"
    with tempfile.TemporaryDirectory(prefix="laplace-gpu-proof-") as tmp:
        os.environ["LAPLACE_FALLBACK_LOG"] = os.path.join(tmp, "fallbacks.jsonl")

        from laplace.representation import cuda_libs

        preloaded = cuda_libs.preload()

        import onnxruntime as ort

        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls(directory="")
        providers = ort.get_available_providers()
        if "CUDAExecutionProvider" not in providers:
            raise RuntimeError(f"CUDAExecutionProvider absent: {providers}")

        import cupy as cp
        import numpy as np

        source = np.arange(64, dtype=np.float32).reshape(8, 8)
        device_source = cp.asarray(source)
        device_result = device_source @ device_source.T
        cp.cuda.Stream.null.synchronize()
        result = cp.asnumpy(device_result)
        if not np.array_equal(result, source @ source.T):
            raise RuntimeError("CuPy GEMM did not match the NumPy reference")

        from laplace.representation.embed_router import FastEmbedBackend

        backend = FastEmbedBackend()
        vectors = backend.embed(["stage zero runtime proof", "closure and liveness"])
        if not backend.gpu or backend.providers[0] != "CUDAExecutionProvider":
            raise RuntimeError(f"FastEmbed landed on {backend.providers}")
        if len(vectors) != 2 or any(len(vector) != 384 for vector in vectors):
            raise RuntimeError("FastEmbed returned an unexpected embedding shape")

        device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
        if isinstance(device_name, bytes):
            device_name = device_name.decode("utf-8", errors="replace")
        receipt = {
            "schema": "laplace-runtime-gpu-proof/1",
            "status": "PASS",
            "python": platform.python_version(),
            "distributions": distributions,
            "preloaded_libraries": preloaded,
            "onnxruntime_providers": providers,
            "cupy_device": device_name,
            "cupy_gemm_checksum": float(result.sum()),
            "fastembed_providers": backend.providers,
            "embedding_shape": [len(vectors), len(vectors[0])],
            "embedding_norms": [sum(value * value for value in vector) ** 0.5 for vector in vectors],
        }
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
