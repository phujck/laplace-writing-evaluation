"""protocol.py - ArmProtocol: what an arm is, declared before it reads anything.

Design §3: "A bench arm IS that tuple plus an explicit read protocol." That is what turns
"schema v1 vs v2" or "encoder A vs B" from an opinion into a measurement, and it is what stops
seam J6 - an arm quietly reading deeper than its competitors and winning on spend.

An ``ArmProtocol`` carries four kinds of field and nothing else:

  the four version axes      segmentation_recipe_version, input_recipe_version, encoder_id,
                             schema_version. Present on every arm, ``null`` where an arm has no
                             encoder or extracts no typed structure - null is a statement.
  the read protocol          k, max_spans_read, max_whole_file_reads, read_budget_bytes, rounds,
                             beam, max_materialized, granularity. Enforced by ``SpanReader``.
  the declared model bill    fold_model_calls and query_model_calls, DECLARED here and CHECKED
                             against the counted observation by the runner. A declaration that
                             does not survive the count is ``ProtocolViolation``.
  identity                   arm_id, variant, model_stamp, seed.

THE SEED LAW (``evidence/ATLAS_PHASE0_2026-08-01_agreement-gate.md``). The seed is part of the
arm definition, not a runtime flag: the Phase 0 gate measured that agreement moves with the query
seed, so a threshold means nothing without one. Gate thresholds are evaluated AT THE REGISTERED
SEED ONLY, and a number produced at any other seed is a different measurement that must say so.

``model_stamp`` is explicit on every arm, never inherited. The Tier-1 arms are mechanical and
stamp ``"none"``; a stamp of ``"none"`` with a nonzero declared model call count refuses at
construction, because that combination is the shape of an unstamped model call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..errors import ProtocolViolation, SchemaFieldMissing, SchemaVersionMismatch
from ..ids import chash

#: Legal values of ``granularity``. "span" is the design's unit of retrieval; "node" is the
#: whole-file read, kept as a legal declaration so the chunking confound can be MEASURED by
#: running an arm both ways rather than argued about.
GRANULARITIES = ("span", "node")

#: The stamp a mechanical arm carries. Not the empty string: an empty stamp reads as forgotten.
NO_MODEL = "none"


@dataclass(frozen=True)
class ArmProtocol:
    """One arm's complete declaration. Immutable, hashable, and printed verbatim in every run."""

    SCHEMA_VERSION = "arm-protocol/1"

    arm_id: str
    variant: str

    # --- the four version axes (design §3) --------------------------------
    segmentation_recipe_version: str
    input_recipe_version: str
    encoder_id: str | None
    schema_version: str | None

    # --- the explicit read protocol (design §5) ---------------------------
    k: int
    max_spans_read: int
    max_whole_file_reads: int
    read_budget_bytes: int
    rounds: int
    beam: int | None
    max_materialized: int | None
    granularity: str

    # --- the declared model bill, checked against the count ---------------
    fold_model_calls: int
    query_model_calls: int

    # --- identity ---------------------------------------------------------
    model_stamp: str
    seed: int
    note: str = ""

    def __post_init__(self) -> None:
        if self.granularity not in GRANULARITIES:
            raise ProtocolViolation("unknown read granularity",
                                    arm=self.arm_id, granularity=self.granularity,
                                    legal=list(GRANULARITIES))
        for name in ("k", "max_spans_read", "max_whole_file_reads", "read_budget_bytes",
                     "rounds"):
            if getattr(self, name) < 0:
                raise ProtocolViolation("read protocol field is negative",
                                        arm=self.arm_id, field=name, value=getattr(self, name))
        if self.model_stamp == NO_MODEL and (self.fold_model_calls or self.query_model_calls):
            raise ProtocolViolation(
                "an arm declaring model calls must carry an explicit model stamp",
                arm=self.arm_id, fold_model_calls=self.fold_model_calls,
                query_model_calls=self.query_model_calls,
            )
        if not self.model_stamp:
            raise ProtocolViolation("model_stamp is empty; a mechanical arm stamps 'none'",
                                    arm=self.arm_id)

    @property
    def full_id(self) -> str:
        return self.arm_id if not self.variant else f"{self.arm_id}:{self.variant}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "arm_id": self.arm_id,
            "variant": self.variant,
            "segmentation_recipe_version": self.segmentation_recipe_version,
            "input_recipe_version": self.input_recipe_version,
            "encoder_id": self.encoder_id,
            "schema_version_extracted": self.schema_version,
            "k": self.k,
            "max_spans_read": self.max_spans_read,
            "max_whole_file_reads": self.max_whole_file_reads,
            "read_budget_bytes": self.read_budget_bytes,
            "rounds": self.rounds,
            "beam": self.beam,
            "max_materialized": self.max_materialized,
            "granularity": self.granularity,
            "fold_model_calls": self.fold_model_calls,
            "query_model_calls": self.query_model_calls,
            "model_stamp": self.model_stamp,
            "seed": self.seed,
            "note": self.note,
        }

    def hashed_dict(self) -> dict[str, Any]:
        """Identity excludes the prose note and nothing else. The seed IS identity."""
        d = self.to_dict()
        d.pop("note", None)
        return d

    @property
    def protocol_id(self) -> str:
        return chash(self.hashed_dict())

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ArmProtocol":
        if d.get("schema_version") != cls.SCHEMA_VERSION:
            raise SchemaVersionMismatch("ArmProtocol record carries an unknown schema version",
                                        expected=cls.SCHEMA_VERSION, got=d.get("schema_version"))
        required = ("arm_id", "variant", "segmentation_recipe_version", "input_recipe_version",
                    "encoder_id", "schema_version_extracted", "k", "max_spans_read",
                    "max_whole_file_reads", "read_budget_bytes", "rounds", "beam",
                    "max_materialized", "granularity", "fold_model_calls", "query_model_calls",
                    "model_stamp", "seed")
        missing = [key for key in required if key not in d]
        if missing:
            raise SchemaFieldMissing("ArmProtocol record is missing required fields",
                                     fields=missing)
        return cls(
            arm_id=d["arm_id"], variant=d["variant"],
            segmentation_recipe_version=d["segmentation_recipe_version"],
            input_recipe_version=d["input_recipe_version"], encoder_id=d["encoder_id"],
            schema_version=d["schema_version_extracted"], k=int(d["k"]),
            max_spans_read=int(d["max_spans_read"]),
            max_whole_file_reads=int(d["max_whole_file_reads"]),
            read_budget_bytes=int(d["read_budget_bytes"]), rounds=int(d["rounds"]),
            beam=d["beam"], max_materialized=d["max_materialized"],
            granularity=d["granularity"], fold_model_calls=int(d["fold_model_calls"]),
            query_model_calls=int(d["query_model_calls"]), model_stamp=d["model_stamp"],
            seed=int(d["seed"]), note=d.get("note", ""),
        )
