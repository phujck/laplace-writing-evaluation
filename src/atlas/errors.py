"""errors.py - the refusal vocabulary. Every degrade in this package is one of these.

The loud-degrade law (the engine's 07-24 regression: a silent ``return {}, {}`` shipped three
empty deposits with no line printed). Here the rule is stronger than "log it": there is no
degrade path at all. A condition the code cannot honour raises an ``AtlasError`` subclass
carrying a stable machine-readable ``reason`` plus a detail mapping, and callers that must
survive it catch the NAMED class - never ``Exception``.

``reason`` is the identity a test asserts against; the message is for a human reading a
traceback. New refusals get a new subclass and a new reason string, never a reused one with a
different message.
"""

from __future__ import annotations

from typing import Any


class AtlasError(Exception):
    """Base of every atlas refusal. Subclasses set ``reason``; detail travels as keywords."""

    reason = "atlas-error"

    def __init__(self, message: str, **detail: Any) -> None:
        super().__init__(message)
        self.message = message
        self.detail: dict[str, Any] = detail

    def __str__(self) -> str:
        if not self.detail:
            return f"[{self.reason}] {self.message}"
        pairs = ", ".join(f"{k}={v!r}" for k, v in sorted(self.detail.items()))
        return f"[{self.reason}] {self.message} ({pairs})"


class SnapshotRegenerationRefused(AtlasError):
    reason = "snapshot-regeneration-refused"


# --- ids ------------------------------------------------------------------

class IdError(AtlasError):
    reason = "id-error"


class NotCanonicalizable(IdError):
    """A value the canonical-JSON encoder refuses: it has no stable, sorted representation."""

    reason = "id-not-canonicalizable"


# --- schema ---------------------------------------------------------------

class SchemaError(AtlasError):
    reason = "schema-error"


class SchemaVersionMismatch(SchemaError):
    """A record's ``schema_version`` is not the version this code reads."""

    reason = "schema-version-mismatch"


class SchemaFieldMissing(SchemaError):
    """A required field is absent from a serialized record."""

    reason = "schema-field-missing"


# --- store ----------------------------------------------------------------

class StoreError(AtlasError):
    reason = "store-error"


class StoreLockTimeout(StoreError):
    """The cross-process authority lock was not acquired before its deadline.

    The protected body has not run, so callers may retry an idempotent act.  Keeping this
    distinct from generic store faults prevents a bridge from replaying writes after an
    ambiguous disk, projection, or transaction failure.
    """

    reason = "store-lock-timeout"


class BlobMissing(StoreError):
    """A content-addressed blob named by a record is not in the store."""

    reason = "store-blob-missing"


class BlobHashMismatch(StoreError):
    """A blob's bytes do not hash to the key it is filed under."""

    reason = "store-blob-hash-mismatch"


class HistoryError(StoreError):
    """The canonical event history cannot be trusted or applied."""

    reason = "store-history-error"


class HistoryChainMismatch(HistoryError):
    """A stored event row does not verify against its sequence or predecessor."""

    reason = "store-history-chain-mismatch"


class StateTransitionRefused(HistoryError):
    """An event is well formed but unlawful from the materialized state."""

    reason = "state-transition-refused"


class StaleOwner(StateTransitionRefused):
    reason = "stale-owner"


class RuntimePolicyRefused(AtlasError):
    """Atlas was entered through an interpreter forbidden by the runtime policy."""

    reason = "runtime-policy-refused"


# --- snapshot -------------------------------------------------------------

class SnapshotError(AtlasError):
    reason = "snapshot-error"


class SnapshotIncomplete(SnapshotError):
    """A bundle is missing a file the layout requires."""

    reason = "snapshot-incomplete"


class SnapshotIdMismatch(SnapshotError):
    """The manifest's ``snapshot_id`` is not the hash of its own hashed fields."""

    reason = "snapshot-id-mismatch"


class ContentHashMismatch(SnapshotError):
    """A node's stored bytes do not hash to its recorded ``content_hash``."""

    reason = "snapshot-content-hash-mismatch"


class SealViolation(SnapshotError):
    """Sealed material reached a travelling bundle. The absolute refusal.

    Fires on a sealed node carrying content, a ``soul/`` path carrying content, a span over a
    sealed node, or a nonzero count in ``seal_report.json``.
    """

    reason = "snapshot-seal-violation"


class SealedRead(SnapshotError):
    """A caller asked for the bytes of a sealed node. Refused at the read boundary too."""

    reason = "snapshot-sealed-read"


# --- segmentation ---------------------------------------------------------

class SegmentationError(AtlasError):
    reason = "segmentation-error"


class SegmenterMissing(SegmentationError):
    """No segmenter is registered for a node and the fallback was not reachable."""

    reason = "segmentation-segmenter-missing"


class CoverageViolation(SegmentationError):
    """Leaf spans do not partition a node's bytes. Silent truncation, caught structurally."""

    reason = "segmentation-coverage-violation"


class CapViolation(SegmentationError):
    """A leaf span exceeds the hard cap without being named as unsplittable."""

    reason = "segmentation-cap-violation"


class StructureViolation(SegmentationError):
    """A structured source (JSON/JSONL) reached the raw-window fallback."""

    reason = "segmentation-structure-violation"


class NestingViolation(SegmentationError):
    """A span's declared parent does not contain it, or names a span that is not present."""

    reason = "segmentation-nesting-violation"


# --- encoders -------------------------------------------------------------

class EncoderError(AtlasError):
    reason = "encoder-error"


class EncoderUnavailable(EncoderError):
    """A real encoder was asked for and its model or its dependency is not present."""

    reason = "encoder-unavailable"


class EncoderContractViolation(EncoderError):
    """An encoder returned vectors that break the declared dim or normalisation contract."""

    reason = "encoder-contract-violation"


# --- bench ----------------------------------------------------------------

class BenchError(AtlasError):
    reason = "bench-error"


class AnchorUnresolved(BenchError):
    """A task atom does not appear, post-normalizer, inside its declared anchor span."""

    reason = "bench-anchor-unresolved"


class AnchorHashMismatch(BenchError):
    """An anchor's stored span content hash is not the hash of the span's bytes in the snapshot."""

    reason = "bench-anchor-hash-mismatch"


class BundleIdMismatch(BenchError):
    """A frozen task bundle's ``bundle_id`` is not the hash of its own hashed fields."""

    reason = "bench-bundle-id-mismatch"


class ProtocolViolation(BenchError):
    """An arm's DECLARED budget or model-call count disagrees with the COUNTED observation."""

    reason = "bench-protocol-violation"


class LeakageDetected(BenchError):
    """A derived pattern carries a word from an answer atom that is absent from the question.

    The ported ``assert_no_leak``. The v1 script raised ``SystemExit``; here it is a named
    refusal so a test can assert the identity rather than the exit code. Detection is unchanged.
    """

    reason = "bench-leakage-detected"


class UniverseViolation(BenchError):
    """An arm asked for a node or span the declared view excludes. Views are enforced, not asked."""

    reason = "bench-universe-violation"


class SummaryDisagreement(BenchError):
    """A recomputed summary number disagrees with the banked one. The recompute-and-assert law."""

    reason = "bench-summary-disagreement"


class ArmUnavailable(BenchError):
    """An arm cannot run: its encoder, its index or its model directory is absent. Never a degrade."""

    reason = "bench-arm-unavailable"


class ContaminationDetected(BenchError):
    """A node in the view carries so many of the bundle's answers that it reads as an answer key.

    The freeze-time tripwire (``contamination.py``). Raised at mint, naming the node and its
    measured density, so a contaminated bundle costs nothing rather than costing a scored run and
    a judge's re-derivation. It is a TRIPWIRE and says so: density flags a candidate, the author
    or the judge rules on it, and the ruling becomes a universe exclusion.
    """

    reason = "bench-contamination-detected"
