"""nBDM — the SuperARC complexity measure, over the vendored pybdm surface.

The benchmark's score is built from ``tanh(nBDM(sequence) / nBDM(model))``, where
nBDM is pybdm's *normalized* block decomposition method, ``(BDM - minBDM) /
(maxBDM - minBDM)``, computed with ``ndim=1`` and the ``recursive`` boundary over
the CTM-B2-D12 reference table.

Two conventions in :py:func:`nbdm` are load-bearing and are the paper's, not ours:

* the input is the **8-bit ASCII expansion of the literal string** — the sequence
  as ``1,1,0,0,0,1,0,0,0,0,1,0`` (commas, no spaces) and the candidate model as
  stored, never the raw 12 bits. Change the separator or add a space after the
  comma and every ratio moves.
* the partition is ``PartitionRecursive``. The default ``PartitionIgnore`` drops
  every block shorter than the 12-bit shape, so it raises "Computed BDM is 0" on
  short inputs and silently disagrees on long ones; ``PartitionCorrelated`` raises
  ``NotImplementedError`` on the normalized path. The engine asserts its own
  partition at construction rather than trusting the call site.

pybdm is vendored, not installed (``models/ctm/``, ``scripts/vendor_ctm_tables.py``):
the 2019 wheel imports ``pkg_resources``, gone from setuptools >= 81 and absent
from uv venvs, so ``import pybdm`` fails on this interpreter even when installed.
The vendored directory is loaded by path under a private module name — it is not
on ``sys.path`` and never shadows a real ``pybdm``.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import importlib.util
import os
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType

import numpy as np

_REPO = source_tree()
_VENDOR_PKG = "laplace._vendored_ctm"

CTM_DIR = Path(os.environ.get("LAPLACE_CTM_DIR") or _REPO / "models" / "ctm")


def _vendored() -> ModuleType:
    """Import ``models/ctm/`` as a package, by path, exactly once."""
    cached = sys.modules.get(_VENDOR_PKG)
    if cached is not None:
        return cached
    init = CTM_DIR / "__init__.py"
    if not init.is_file():
        raise RuntimeError(
            f"vendored BDM surface missing at {CTM_DIR}; "
            "run `python scripts/vendor_ctm_tables.py` (or set LAPLACE_CTM_DIR)"
        )
    spec = importlib.util.spec_from_file_location(
        _VENDOR_PKG, init, submodule_search_locations=[str(CTM_DIR)]
    )
    module = importlib.util.module_from_spec(spec)
    # Registered before exec so the package's own relative imports resolve.
    sys.modules[_VENDOR_PKG] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(_VENDOR_PKG, None)
        raise
    return module


@lru_cache(maxsize=1)
def bdm_engine():
    """The one configured BDM instance; loading the CTM table costs ~24 kB of pickle."""
    vendored = _vendored()
    engine = vendored.BDM(ndim=1, partition=vendored.PartitionRecursive)
    if not isinstance(engine.partition, vendored.PartitionRecursive):
        raise RuntimeError(f"nBDM requires the recursive partition, got {engine.partition!r}")
    return engine


def ascii_to_binary_list(text: str) -> np.ndarray:
    """Expand a string to its bit array, 8 bits per character.

    Codepoints above 255 widen past 8 bits, as in the published scorer — the
    expansion follows ``format(ord(char), '08b')`` verbatim so our bits equal
    theirs on every answer they scored.
    """
    return np.array(
        [int(bit) for char in text for bit in format(ord(char), "08b")], dtype=np.int8
    )


def nbdm(text: str) -> float:
    """Normalized BDM of a string, over its 8-bit ASCII expansion.

    Raises ``ValueError`` on an empty string (BDM 0 means malformed input, and
    the benchmark never scores one).
    """
    return float(bdm_engine().nbdm(ascii_to_binary_list(text)))
