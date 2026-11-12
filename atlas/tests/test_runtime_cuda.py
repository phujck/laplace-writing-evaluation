"""CUDA loader consumers and planted failures; no linker or device env overrides."""

import os
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from atlas import runtime
from atlas.errors import AtlasError


def test_installed_libraries_load_once_and_receipt_is_defensive(monkeypatch):
    receipt = runtime.preload_cuda_libraries()
    assert not receipt["missing"]
    for stem in runtime._CUDA_REQUIRED:
        assert any(Path(path).name.startswith(stem + ".so") for path in receipt["loaded"])
    assert all(Path(path).is_absolute() for path in receipt["loaded"])
    monkeypatch.setattr(runtime.ctypes, "CDLL", lambda *a, **kw: pytest.fail("loaded twice"))
    assert runtime.preload_cuda_libraries() == receipt
    receipt["loaded"].clear()
    assert runtime.preload_cuda_libraries()["loaded"]


def _plant(monkeypatch, tmp_path, *, omit=None):
    monkeypatch.setattr(runtime, "_CUDA_RECEIPT", None)
    monkeypatch.setattr(runtime, "_CUDA_HANDLES", {})
    monkeypatch.setattr(runtime, "_cuda_site_dirs", lambda: [tmp_path])
    library_dir = tmp_path / "nvidia" / "cu99" / "lib"
    library_dir.mkdir(parents=True)
    for stem in runtime._CUDA_REQUIRED:
        if stem != omit:
            (library_dir / (stem + ".so.99")).touch()
    calls = []

    def load(path, *, mode):
        assert mode == runtime.ctypes.RTLD_GLOBAL
        calls.append(Path(path).name)
        return object()

    monkeypatch.setattr(runtime.ctypes, "CDLL", load)
    return calls


def test_mixed_wheel_layout_loads_dependencies_before_consumers(monkeypatch, tmp_path):
    calls = _plant(monkeypatch, tmp_path)
    receipt = runtime.preload_cuda_libraries()
    assert not receipt["missing"]
    assert calls == [stem + ".so.99" for stem in runtime._CUDA_REQUIRED]
    assert str(tmp_path / "nvidia" / "cu99" / "lib") in receipt["searched"]


def test_planted_missing_library_is_typed_refusal(monkeypatch, tmp_path):
    _plant(monkeypatch, tmp_path, omit="libcusolver")
    if os.environ.get("LAPLACE_REQUIRE_GPU", "").lower() not in {"1", "true", "yes", "on"}:
        assert runtime.preload_cuda_libraries()["missing"] == ["libcusolver.so"]
        return
    with pytest.raises(AtlasError) as caught:
        runtime.preload_cuda_libraries()
    assert caught.value.reason == "cuda-library-missing"
    assert caught.value.detail["missing"] == ["libcusolver.so"]
    assert "libcusolver.so" in str(caught.value)
    assert runtime._CUDA_RECEIPT is None
    print(json.dumps({"reason": caught.value.reason, "missing": caught.value.detail["missing"]}))


def test_present_but_unloadable_library_is_not_counted(monkeypatch, tmp_path):
    calls = _plant(monkeypatch, tmp_path)
    original = runtime.ctypes.CDLL

    def fail_solver(path, *, mode):
        if Path(path).name == "libcusolver.so.99":
            raise OSError("planted unresolved dependency")
        return original(path, mode=mode)

    monkeypatch.setattr(runtime.ctypes, "CDLL", fail_solver)
    receipt = runtime._load_cuda_libraries()
    assert "libcusolver.so.99" in receipt["missing"]
    assert "libcusolver.so.99" not in calls
    assert not any(Path(path).name == "libcusolver.so.99" for path in receipt["loaded"])


def test_site_discovery_uses_interpreter_paths(monkeypatch):
    monkeypatch.setattr(runtime.sysconfig, "get_paths", lambda: {
        "purelib": "/planted/pure", "platlib": "/planted/plat"})
    monkeypatch.setattr(runtime.site, "getusersitepackages", lambda: "/planted/user")
    monkeypatch.setattr(runtime.site, "getsitepackages", lambda: ["/planted/pure"])
    monkeypatch.setattr(runtime.sys, "path", [])
    assert runtime._cuda_site_dirs() == [
        Path("/planted/user"), Path("/planted/pure"), Path("/planted/plat")]


def test_gpu_entry_preserves_loader_refusal(monkeypatch):
    from atlas.bench.arms.atlas_arm import AtlasArm
    from atlas.bench.arms.dense_flat import DenseFlatArm
    from atlas.encoders import bge_onnx
    from atlas.spectral_pour import _spectral_coordinates
    from atlas.tools.pour_notes import GpuBgeEncoder
    from atlas.updown import _sym_eig

    def refuse():
        raise runtime.CudaLibraryMissing("planted missing libcublas.so", missing=["libcublas.so"])

    monkeypatch.setattr(runtime, "preload_cuda_libraries", refuse)
    monkeypatch.setattr(bge_onnx, "resolve_model_dir", lambda *a, **kw: Path("/planted/model"))
    entries = [
        lambda: bge_onnx.BgeOnnxEncoder(providers=("CUDAExecutionProvider",))._load(),
        lambda: bge_onnx.BgeOnnxEncoder(providers=())._load(),
        lambda: AtlasArm(Path("/planted/store")),
        lambda: DenseFlatArm(store_root=Path("/planted/store")),
        GpuBgeEncoder,
    ]
    if os.environ.get("LAPLACE_REQUIRE_GPU") == "1":
        entries.extend([lambda: _spectral_coordinates([], 2), lambda: _sym_eig([[1.0]])])
    for enter in entries:
        with pytest.raises(AtlasError) as caught:
            enter()
        assert caught.value.reason == "cuda-library-missing"


@pytest.mark.skipif(os.environ.get("LAPLACE_REQUIRE_GPU") != "1", reason="GPU-required host probe")
def test_gpu_split_observed_by_nvidia_smi(monkeypatch):
    from atlas.spectral_pour import _spectral_coordinates

    runtime.preload_cuda_libraries()
    import cupy as cp

    eigh = cp.linalg.eigh
    observed = []

    def measured_eigh(matrix):
        assert isinstance(matrix, cp.ndarray)
        result = eigh(matrix)
        cp.cuda.get_current_stream().synchronize()
        observed.append(matrix.shape)
        print("GPU split: cupy.linalg.eigh, matrix=" + str(matrix.shape))
        command = ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used",
                   "--format=csv,noheader"]
        print(" ".join(command))
        print(subprocess.run(command, check=True, capture_output=True, text=True).stdout, end="")
        return result

    monkeypatch.setattr(cp.linalg, "eigh", measured_eigh)
    leaves = [SimpleNamespace(vector=vector) for vector in
              [(1., 0.), (.9, .1), (0., 1.), (.1, .9)]]
    coordinates = _spectral_coordinates(leaves, 2)
    assert observed == [(4, 4)]
    assert len(coordinates) == 4
    assert all(len(row) == 2 for row in coordinates)
