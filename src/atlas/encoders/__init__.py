"""encoders - the registry. Deterministic encoders load eagerly; the real one does not.

``get_encoder`` is the only construction site, so ``encoder_id`` and the model-loading policy
live in one place. ``bge_onnx`` is imported INSIDE the lookup, not at module import: importing
this package must not pull the ONNX stack into a unit run, and a test asserts fastembed stays
out of ``sys.modules``.

An unknown name is a named refusal, not a default. Silently handing back a hash encoder when a
caller asked for bge would produce numbers that look like retrieval and are not.
"""

from __future__ import annotations

from ..errors import EncoderUnavailable
from .base import Encoder, EncoderRuntimeEvidence, EncoderSpec, check_contract, unit
from .deterministic import HashEncoder, SyntheticEncoder

#: Names the rest of the package uses. "bge" resolves through a lazy import.
ENCODER_NAMES = ("hash", "synthetic", "bge")


def get_encoder(name: str, **kwargs) -> Encoder:
    if name == "hash":
        return HashEncoder()
    if name == "synthetic":
        return SyntheticEncoder()
    if name == "bge":
        from .bge_onnx import BgeOnnxEncoder  # lazy: keeps fastembed out of a unit run
        return BgeOnnxEncoder(**kwargs)
    raise EncoderUnavailable("no encoder registered under that name", name=name,
                             known=list(ENCODER_NAMES))


__all__ = ["ENCODER_NAMES", "Encoder", "EncoderRuntimeEvidence", "EncoderSpec", "HashEncoder",
           "SyntheticEncoder", "check_contract", "get_encoder", "unit"]
