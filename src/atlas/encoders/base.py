"""base.py - the Encoder contract and the normalisation law.

An encoder is a disposable, replaceable projection of the record (design §3). It is identified,
never assumed: ``encoder_id`` travels in every derived identity, so swapping bge-small for
anything else creates a new generation with a parent instead of silently rewriting the meaning
of existing coordinates.

The normalisation contract, single-sourced here so every backend obeys the same one:

  * ``embed`` returns one vector per input text, in input order, each of length ``dim``.
  * every vector is L2-unit, so a dot product IS a cosine and no consumer needs to know which
    backend produced it.
  * an empty or all-zero input yields the zero vector - the one non-unit case, allowed because
    normalising it would invent a direction. Consumers scoring against it get 0.0, which is the
    honest answer.
  * ``query`` may differ from ``embed`` (bge has a retrieval prefix for queries); it returns one
    vector under the same contract.

``check_contract`` is the mechanical form of the paragraph above, used by the encoder tests.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..errors import EncoderContractViolation
from ..ids import chash


@dataclass(frozen=True)
class EncoderSpec:
    """Complete identity of one vector space, excluding runtime placement.

    Provider and device deliberately do not appear here: CUDA and CPU may serve the same
    specification when their observed drift remains inside ``determinism_tolerance``.  Model or
    tokenizer bytes, pooling, prefixes, dimension, or normalization moving creates a different
    ``spec_id`` and therefore a different generation.
    """

    encoder_id: str
    model_artifact_digest: str
    tokenizer_artifact_digest: str
    pooling: str
    dim: int
    normalization: str
    document_prefix: str
    query_prefix: str
    determinism_metric: str
    determinism_tolerance: float

    def __post_init__(self) -> None:
        for name in ("encoder_id", "pooling", "normalization", "determinism_metric"):
            if not str(getattr(self, name)).strip():
                raise EncoderContractViolation(f"encoder specification {name} is empty")
        for name in ("model_artifact_digest", "tokenizer_artifact_digest"):
            value = str(getattr(self, name))
            if re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None:
                raise EncoderContractViolation(
                    "encoder specification artifact digest is not canonical sha256",
                    field=name,
                    value=value,
                )
        if isinstance(self.dim, bool) or not isinstance(self.dim, int) or self.dim < 1:
            raise EncoderContractViolation(
                "encoder specification dimension must be a positive integer", dim=self.dim
            )
        if not math.isfinite(self.determinism_tolerance) or self.determinism_tolerance < 0.0:
            raise EncoderContractViolation(
                "encoder specification determinism tolerance is invalid",
                tolerance=self.determinism_tolerance,
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "atlas.encoder-spec/1",
            "encoder_id": self.encoder_id,
            "model_artifact_digest": self.model_artifact_digest,
            "tokenizer_artifact_digest": self.tokenizer_artifact_digest,
            "pooling": self.pooling,
            "dim": self.dim,
            "normalization": self.normalization,
            "document_prefix": self.document_prefix,
            "query_prefix": self.query_prefix,
            "determinism_metric": self.determinism_metric,
            "determinism_tolerance": self.determinism_tolerance,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "EncoderSpec":
        expected = {
            "schema_version",
            "encoder_id",
            "model_artifact_digest",
            "tokenizer_artifact_digest",
            "pooling",
            "dim",
            "normalization",
            "document_prefix",
            "query_prefix",
            "determinism_metric",
            "determinism_tolerance",
        }
        if set(raw) != expected or raw.get("schema_version") != "atlas.encoder-spec/1":
            raise EncoderContractViolation("encoder specification schema is unknown")
        string_fields = (
            "encoder_id",
            "model_artifact_digest",
            "tokenizer_artifact_digest",
            "pooling",
            "normalization",
            "document_prefix",
            "query_prefix",
            "determinism_metric",
        )
        if not all(isinstance(raw[field], str) for field in string_fields):
            raise EncoderContractViolation("encoder specification string field is malformed")
        if isinstance(raw["dim"], bool) or not isinstance(raw["dim"], int):
            raise EncoderContractViolation("encoder specification dimension is malformed")
        tolerance = raw["determinism_tolerance"]
        if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)):
            raise EncoderContractViolation("encoder specification tolerance is malformed")
        return cls(
            raw["encoder_id"],  # type: ignore[arg-type]
            raw["model_artifact_digest"],  # type: ignore[arg-type]
            raw["tokenizer_artifact_digest"],  # type: ignore[arg-type]
            raw["pooling"],  # type: ignore[arg-type]
            raw["dim"],  # type: ignore[arg-type]
            raw["normalization"],  # type: ignore[arg-type]
            raw["document_prefix"],  # type: ignore[arg-type]
            raw["query_prefix"],  # type: ignore[arg-type]
            raw["determinism_metric"],  # type: ignore[arg-type]
            float(tolerance),
        )

    @property
    def spec_id(self) -> str:
        return chash(self.to_dict())


@dataclass(frozen=True)
class EncoderRuntimeEvidence:
    """Measured warrant that named providers served one encoder spec inside tolerance."""

    encoder_spec_id: str
    probe_set_id: str
    providers: tuple[str, ...]
    metric: str
    observed_max_drift: float
    tolerance: float

    def __post_init__(self) -> None:
        if not self.encoder_spec_id.strip() or not self.probe_set_id.strip():
            raise EncoderContractViolation("encoder runtime evidence identity is empty")
        if not self.providers or not all(provider.strip() for provider in self.providers):
            raise EncoderContractViolation("encoder runtime evidence providers are empty")
        if not self.metric.strip():
            raise EncoderContractViolation("encoder runtime evidence metric is empty")
        if not math.isfinite(self.observed_max_drift) or self.observed_max_drift < 0.0:
            raise EncoderContractViolation("encoder runtime evidence drift is invalid")
        if not math.isfinite(self.tolerance) or self.tolerance < 0.0:
            raise EncoderContractViolation("encoder runtime evidence tolerance is invalid")

    @classmethod
    def exact_single_provider(
        cls,
        spec: EncoderSpec,
        provider: str,
        probe_set_id: str,
    ) -> "EncoderRuntimeEvidence":
        if spec.determinism_tolerance != 0.0:
            raise EncoderContractViolation(
                "single-provider exact evidence requires a zero-tolerance encoder spec"
            )
        return cls(
            spec.spec_id,
            probe_set_id,
            (provider,),
            spec.determinism_metric,
            0.0,
            0.0,
        )

    @property
    def within_tolerance(self) -> bool:
        return self.observed_max_drift <= self.tolerance

    @property
    def receipt_id(self) -> str:
        return chash(self.hashed_dict())

    def hashed_dict(self) -> dict[str, object]:
        return {
            "schema_version": "atlas.encoder-runtime-evidence/1",
            "encoder_spec_id": self.encoder_spec_id,
            "probe_set_id": self.probe_set_id,
            "providers": list(self.providers),
            "metric": self.metric,
            "observed_max_drift": self.observed_max_drift,
            "tolerance": self.tolerance,
            "within_tolerance": self.within_tolerance,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.hashed_dict(), "receipt_id": self.receipt_id}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "EncoderRuntimeEvidence":
        expected = {
            "schema_version",
            "receipt_id",
            "encoder_spec_id",
            "probe_set_id",
            "providers",
            "metric",
            "observed_max_drift",
            "tolerance",
            "within_tolerance",
        }
        if set(raw) != expected or raw.get("schema_version") != "atlas.encoder-runtime-evidence/1":
            raise EncoderContractViolation("encoder runtime evidence schema is unknown")
        providers = raw["providers"]
        if not isinstance(providers, list) or not all(isinstance(item, str) for item in providers):
            raise EncoderContractViolation("encoder runtime evidence providers are malformed")
        for field in ("observed_max_drift", "tolerance"):
            if isinstance(raw[field], bool) or not isinstance(raw[field], (int, float)):
                raise EncoderContractViolation(
                    "encoder runtime evidence numeric field is malformed", field=field
                )
        for field in ("encoder_spec_id", "probe_set_id", "metric", "receipt_id"):
            if not isinstance(raw[field], str):
                raise EncoderContractViolation(
                    "encoder runtime evidence string field is malformed", field=field
                )
        result = cls(
            raw["encoder_spec_id"],
            raw["probe_set_id"],
            tuple(providers),
            raw["metric"],
            float(raw["observed_max_drift"]),
            float(raw["tolerance"]),
        )
        if not isinstance(raw["within_tolerance"], bool) or \
                raw["within_tolerance"] != result.within_tolerance:
            raise EncoderContractViolation("encoder runtime evidence verdict does not verify")
        if raw["receipt_id"] != result.receipt_id:
            raise EncoderContractViolation("encoder runtime evidence receipt id does not verify")
        return result


@runtime_checkable
class Encoder(Protocol):
    encoder_id: str
    dim: int
    max_tokens: int
    spec: EncoderSpec

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    def query(self, text: str) -> list[float]:
        ...


def unit(vec: list[float]) -> list[float]:
    """L2-normalise. The zero vector stays zero - see the contract above."""
    norm = sum(x * x for x in vec) ** 0.5
    if norm == 0.0:
        return list(vec)
    return [x / norm for x in vec]


def check_contract(encoder: Encoder, vectors: list[list[float]], tol: float = 1e-9) -> None:
    """Refuse vectors that break the declared dim or the unit-norm law. Named, never a warning."""
    for i, vec in enumerate(vectors):
        if len(vec) != encoder.dim:
            raise EncoderContractViolation(
                "vector length does not match the declared dim",
                encoder_id=encoder.encoder_id, index=i, got=len(vec), dim=encoder.dim,
            )
        norm = sum(x * x for x in vec) ** 0.5
        if norm == 0.0:
            continue
        if abs(norm - 1.0) > tol:
            raise EncoderContractViolation(
                "vector is not unit-normalised",
                encoder_id=encoder.encoder_id, index=i, norm=norm,
            )
