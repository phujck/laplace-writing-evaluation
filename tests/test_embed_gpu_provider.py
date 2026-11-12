"""tests/test_embed_gpu_provider.py - the CUDA embedding path, guarded (WO-20260820 deps-hygiene lane).

Phase-A audit finding ``no-regression-test-for-gpu-embed-path``: zero tests referenced ``.gpu``
or ``CUDAExecutionProvider`` anywhere, despite this being a measured high-throughput path
(embed_router.py's FastEmbedBackend; on this box 2026-08-21, 1024 texts of 480 chars: 32.5/s
CPU at threads=8, 484.3/s on the CUDA EP -- 14.9x; 10.8/s at threads=1 -- 44.8x. Evidence:
evidence/EMBED_GPU_2026-08-21/). Those figures REPLACE the "274/s vs 3372/s (12.3x)" pair this
docstring carried from the 2026-08-19 pilot, which stated neither its text length nor its thread
posture and so could not be compared with anything (WO-20260820-embed-rate-record-discrepancy).
The module's own comments record the exact silent-regression shape this file closes -- "missing
libcublasLt -> CPU, embeds fine" -- a fallback that is functionally correct and structurally
invisible.

THE SKIP GATE WAS VACUOUS IN EXACTLY THE STATE IT GUARDED (found 2026-08-21). Both tests below
hung off ``_CUDA_AVAILABLE``, so when a plain-onnxruntime install overwrote onnxruntime-gpu's
``capi/`` in place -- which is what had happened on this box, the CPU wheel's
``onnxruntime_pybind11_state.so`` sitting beside the GPU wheel's 229MB
``libonnxruntime_providers_cuda.so`` -- ``get_available_providers()`` dropped CUDA, the gate
skipped the whole file, and the guard reported nothing. ``test_gpu_distribution_implies_cuda``
now runs off the DISTRIBUTION rather than the capability, so the install-order regression fails
loudly instead of silently skipping.

Skip posture mirrors scripts/standup.sh's own GPU-by-capability gate (nvidia-smi answering ->
the gpu extra is installed -> CUDA is expected to actually bind), NOT scripts/container_proof.py
-- that file's parity install line deliberately omits the gpu extra and carries no GPU-conditional
logic at all (phase-A's finder cited it as the pattern to mirror; phase-A's verifier confirmed
that citation wrong and pointed at standup.sh instead -- corrected here).
"""

from __future__ import annotations

import importlib.metadata as md
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    import onnxruntime as _ort
except Exception:
    _ort = None

_CUDA_AVAILABLE = bool(_ort) and "CUDAExecutionProvider" in _ort.get_available_providers()
_ORT_DISTS = {d.name for d in md.distributions() if d.name and "onnxruntime" in d.name.lower()}
_GPU_DIST_INSTALLED = "onnxruntime-gpu" in _ORT_DISTS


@pytest.mark.skipif(
    not _GPU_DIST_INSTALLED,
    reason="onnxruntime-gpu is not installed -- a CPU-only box is a lawful posture, not a failure",
)
def test_gpu_distribution_implies_cuda():
    """THE INSTALL-ORDER GUARD, gated on the DISTRIBUTION rather than the capability -- so it
    cannot skip itself into silence the way the file's original blanket gate did.

    If onnxruntime-gpu is a registered distribution, the CUDA provider MUST be available. It was
    not on this box on 2026-08-21: plain onnxruntime had been installed over onnxruntime-gpu into
    the same user site, overwriting exactly three files (``build_and_package_info.py``,
    ``libonnxruntime.so``, ``onnxruntime_pybind11_state.so``) while leaving the GPU wheel's
    provider libraries in place. Both dist-infos were registered, so the file's other guard --
    which only asserts onnxruntime-gpu is registered -- would have passed had it run at all,
    while the whole file was being skipped for want of the very provider that install broke.
    That is the ``dual-dist-info-fragile-install-order`` finding, realised."""
    assert _ort is not None, (
        f"onnxruntime-gpu is installed (dists: {sorted(_ORT_DISTS)}) but onnxruntime does not import"
    )
    assert _CUDA_AVAILABLE, (
        f"onnxruntime-gpu is installed (dists: {sorted(_ORT_DISTS)}) but "
        f"get_available_providers() = {_ort.get_available_providers()} carries no "
        f"CUDAExecutionProvider -- the environment is incoherent. Rebuild the declared GPU "
        f"profile so fastembed-gpu and onnxruntime-gpu are the only providers; do not repair "
        f"shared files by install ordering"
    )


# A DECORATOR, NOT A MODULE-LEVEL ``pytestmark``: a module-level mark applies to every test in
# the file no matter where it is defined, which would have swallowed
# ``test_gpu_distribution_implies_cuda`` above -- the one test that must run precisely when CUDA
# has gone missing. The capability gate belongs only on the tests that need a live device.
needs_cuda = pytest.mark.skipif(
    not _CUDA_AVAILABLE,
    reason="no CUDAExecutionProvider available (GPU-less box, or onnxruntime without the gpu "
    "extra) -- mirrors scripts/standup.sh's nvidia-smi gate: the gpu extra is opt-in by "
    "capability, so its absence here is expected, not a failure",
)


@needs_cuda
def test_fastembed_backend_binds_cuda_provider():
    """When CUDAExecutionProvider is available at all, FastEmbedBackend must actually bind it
    (``.gpu is True``), not silently fall back to CPU -- the exact regression this file exists
    to catch, per embed_router.py's own comment about the observed live fallback."""
    from laplace.representation.embed_router import FastEmbedBackend

    backend = FastEmbedBackend()
    assert backend.gpu is True, (
        "CUDAExecutionProvider is available on this box but FastEmbedBackend.gpu is False -- "
        "the embedding session silently fell back to CPU (14.9x throughput regression measured "
        "2026-08-21, unmonitored until this test)"
    )
    # Mirrors embed_router.py's own access path (FastEmbedBackend.__init__, "fastembed ->
    # OnnxTextModel -> ort.InferenceSession") rather than inventing a new one, so this test
    # breaks alongside the code it guards if fastembed ever changes that shape.
    session = backend._model.model.model
    assert "CUDAExecutionProvider" in session.get_providers()
    assert backend.providers == list(session.get_providers())   # the recorded fact is the real one


@needs_cuda
def test_no_gpu_dial_names_cpu_rather_than_omitting_providers(tmp_path, monkeypatch):
    """LAPLACE_EMBED_NO_GPU must be honoured BY CONSTRUCTION, not by luck.

    Before 2026-08-21 the dial merely skipped setting ``providers``, and fastembed then built its
    own list and attempted CUDA anyway -- observed live, emitting "Attempt to set
    CUDAExecutionProvider failed". The dial landed on CPU only because the CUDA libs were off the
    loader path at that moment; with the preload bridge now in place that accident is gone, so the
    dial has to name ``CPUExecutionProvider`` itself. This test runs on a CUDA-capable box
    precisely because that is the only place the difference is observable."""
    from laplace.representation.embed_router import FastEmbedBackend

    monkeypatch.setenv("LAPLACE_ROOT", str(tmp_path))   # the CPU landing leaves a row; a test
    monkeypatch.setenv("LAPLACE_EMBED_NO_GPU", "1")     # must never append to the live store
    backend = FastEmbedBackend()
    assert backend.gpu is False
    assert backend._model.model.model.get_providers() == ["CPUExecutionProvider"], (
        "LAPLACE_EMBED_NO_GPU is set but the session still carries a non-CPU provider -- the "
        "dial is being honoured by accident of library visibility, not by the provider list"
    )


@needs_cuda
def test_cpu_landing_leaves_a_device_row(tmp_path, monkeypatch):
    """No organ degrades quietly (his ruling, 2026-08-21). A CPU landing -- even a DIALED one --
    appends a typed row to ``.fallback_events.jsonl``; a GPU landing records nothing, because the
    GPU is the ruled home for this organ and the ruled default is not an event."""
    import json

    from laplace.representation import device_policy
    from laplace.representation.embed_router import FastEmbedBackend

    # this test exercises the LAPLACE_ROOT door, so the suite-wide LAPLACE_FALLBACK_LOG isolation
    # (tests/conftest.py, added with the 2026-08-21 census) is stood down - it wins by design
    monkeypatch.delenv(device_policy.LOG_OVERRIDE, raising=False)
    monkeypatch.setenv("LAPLACE_ROOT", str(tmp_path))
    monkeypatch.setenv("LAPLACE_EMBED_NO_GPU", "1")
    FastEmbedBackend()
    log = tmp_path / ".fallback_events.jsonl"
    assert log.exists(), "a CPU embed landing left no device row"
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    assert rows and rows[-1]["organ"] == "embed_router"
    assert rows[-1]["choice"] == "cpu"
    assert rows[-1]["dialed"] is True          # asked for, so lawful and quiet -- but still a row

    monkeypatch.delenv("LAPLACE_EMBED_NO_GPU")
    log.unlink()
    backend = FastEmbedBackend()
    assert backend.gpu is True
    assert not log.exists(), "a GPU landing wrote a fallback row -- the ruled default is not an event"


def test_onnxruntime_gpu_distribution_is_what_loaded():
    """The converse of ``test_gpu_distribution_implies_cuda``: CUDA being available is only
    meaningful if the onnxruntime-gpu distribution -- not a stray plain-onnxruntime reinstall --
    is what actually supplied it. Gated on the capability, since a CPU-only box has nothing to
    say here; its partner above covers the case where the capability is the thing that vanished."""
    if not _CUDA_AVAILABLE:
        pytest.skip("no CUDAExecutionProvider -- test_gpu_distribution_implies_cuda owns that case")
    assert _ort is not None
    assert "onnxruntime-gpu" in _ORT_DISTS, (
        f"CUDA is available but no onnxruntime-gpu distribution is registered "
        f"(found: {sorted(_ORT_DISTS)}) -- unexpected install shape"
    )
