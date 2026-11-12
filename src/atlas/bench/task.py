"""task.py - BenchTask v2 and BenchTaskBundle: ground truth anchored to the corpus that holds it.

The v1 defect, stated as a schema. A v1 task was a question plus answer atoms plus a source FILE
NAME; the corpus it was scored against was whatever the working tree held that minute. The two
had no shared identity, so the corpus could move and the task file could not tell. Half the
headline arm's correct answers were gone the next day and the instrument reported the drop as a
result rather than as decay.

v2 fixes it with two moves:

  1. **Anchors.** Every atom names the span it lives in: ``{node_id, span_id,
     span_content_hash, atom_index}``. ``span_content_hash`` hashes the SPAN'S bytes, not the
     file's - so an atom whose paragraph was rewritten is detected even when the file around it
     is otherwise intact. ``freeze.py`` refuses to mint a bundle unless every atom resolves,
     post-normalizer, inside its declared anchor, READ FROM THE SNAPSHOT and never from the repo.
  2. **One hash over both.** ``bundle_id`` covers snapshot_id + segmentation_id + universe_id +
     tasks + scoring version. Corpus and ground truth are one identity. A run against a different
     snapshot cannot claim this bundle's id, and a re-anchoring that moved one atom mints a new
     bundle rather than quietly editing the old one.

``re_derived`` is how a decayed task stays honest. When an atom no longer resolves - the record
moved on, which is the normal case for a live corpus - the task's INTENT is re-derived against
the current record, the new atoms are anchored, and the old atom is kept in
``re_derived_from`` so the change is a visible diff rather than a silent substitution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..errors import SchemaFieldMissing, SchemaVersionMismatch
from ..ids import chash
from .scoring import SCORING_VERSION, flatten_atoms


@dataclass(frozen=True)
class Anchor:
    """One atom's home in the snapshot: which span holds it, and what that span hashed to."""

    SCHEMA_VERSION = "bench-anchor/1"

    node_id: str
    span_id: str
    span_content_hash: str
    atom_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION, "node_id": self.node_id,
            "span_id": self.span_id, "span_content_hash": self.span_content_hash,
            "atom_index": self.atom_index,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Anchor":
        missing = [k for k in ("node_id", "span_id", "span_content_hash", "atom_index")
                   if k not in d]
        if missing:
            raise SchemaFieldMissing("Anchor record is missing required fields", fields=missing)
        return cls(node_id=d["node_id"], span_id=d["span_id"],
                   span_content_hash=d["span_content_hash"], atom_index=int(d["atom_index"]))


@dataclass(frozen=True)
class BenchTask:
    """One question, its must-atoms, its proximity window, and where each atom is anchored."""

    SCHEMA_VERSION = "bench-task/2"

    task_id: str
    task_class: str
    question: str
    atoms: list
    window: int | None
    anchors: list[Anchor]
    source: str
    truth_date: str | None
    re_derived: bool = False
    re_derived_from: dict[str, Any] | None = None
    intent: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "task_id": self.task_id,
            "task_class": self.task_class,
            "question": self.question,
            "atoms": self.atoms,
            "window": self.window,
            "anchors": [a.to_dict() for a in self.anchors],
            "source": self.source,
            "truth_date": self.truth_date,
            "re_derived": self.re_derived,
            "re_derived_from": self.re_derived_from,
            "intent": self.intent,
        }

    def hashed_dict(self) -> dict[str, Any]:
        """Everything except the prose. ``intent`` and ``source`` describe; they do not define."""
        d = self.to_dict()
        d.pop("intent", None)
        d.pop("source", None)
        return d

    @property
    def atom_strings(self) -> list[str]:
        return flatten_atoms(self.atoms)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BenchTask":
        if d.get("schema_version") != cls.SCHEMA_VERSION:
            raise SchemaVersionMismatch("BenchTask record carries an unknown schema version",
                                        expected=cls.SCHEMA_VERSION, got=d.get("schema_version"))
        missing = [k for k in ("task_id", "task_class", "question", "atoms", "window",
                               "anchors", "source", "truth_date") if k not in d]
        if missing:
            raise SchemaFieldMissing("BenchTask record is missing required fields", fields=missing)
        return cls(
            task_id=d["task_id"], task_class=d["task_class"], question=d["question"],
            atoms=d["atoms"], window=d["window"],
            anchors=[Anchor.from_dict(a) for a in d["anchors"]],
            source=d["source"], truth_date=d["truth_date"],
            re_derived=bool(d.get("re_derived", False)),
            re_derived_from=d.get("re_derived_from"), intent=d.get("intent", ""),
        )


@dataclass(frozen=True)
class BenchTaskBundle:
    """A frozen task set bound to exactly one corpus. ONE hash covers both.

    ``created_ts`` and ``frozen_ts`` are recorded and excluded from the id - the clock never
    enters a hash (ids.py). ``frozen_ts`` is nevertheless load-bearing evidence: the run manifest
    proves the freeze happened BEFORE the first scored run by comparing the two timestamps, which
    is the mechanical form of "pre-registered".
    """

    SCHEMA_VERSION = "bench-task-bundle/2"

    bundle_id: str
    created_ts: str
    frozen_ts: str
    snapshot_id: str
    segmentation_id: str
    universe: dict[str, Any]
    scoring_version: str
    bench_version: str
    tasks: list[BenchTask]
    notes: str = ""
    planted: list[dict[str, Any]] = field(default_factory=list)

    HASH_EXCLUDED = ("bundle_id", "created_ts", "frozen_ts", "notes")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "bundle_id": self.bundle_id,
            "created_ts": self.created_ts,
            "frozen_ts": self.frozen_ts,
            "snapshot_id": self.snapshot_id,
            "segmentation_id": self.segmentation_id,
            "universe": self.universe,
            "scoring_version": self.scoring_version,
            "bench_version": self.bench_version,
            "tasks": [t.to_dict() for t in self.tasks],
            "notes": self.notes,
            "planted": list(self.planted),
        }

    def hashed_dict(self) -> dict[str, Any]:
        d = self.to_dict()
        for key in self.HASH_EXCLUDED:
            d.pop(key, None)
        d["tasks"] = [t.hashed_dict() for t in self.tasks]
        return d

    def computed_id(self) -> str:
        return chash(self.hashed_dict())

    @property
    def classes(self) -> list[str]:
        seen: list[str] = []
        for t in self.tasks:
            if t.task_class not in seen:
                seen.append(t.task_class)
        return seen

    def task(self, task_id: str) -> BenchTask | None:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BenchTaskBundle":
        if d.get("schema_version") != cls.SCHEMA_VERSION:
            raise SchemaVersionMismatch("BenchTaskBundle carries an unknown schema version",
                                        expected=cls.SCHEMA_VERSION, got=d.get("schema_version"))
        missing = [k for k in ("bundle_id", "created_ts", "frozen_ts", "snapshot_id",
                               "segmentation_id", "universe", "scoring_version", "bench_version",
                               "tasks") if k not in d]
        if missing:
            raise SchemaFieldMissing("BenchTaskBundle is missing required fields", fields=missing)
        return cls(
            bundle_id=d["bundle_id"], created_ts=d["created_ts"], frozen_ts=d["frozen_ts"],
            snapshot_id=d["snapshot_id"], segmentation_id=d["segmentation_id"],
            universe=d["universe"], scoring_version=d["scoring_version"],
            bench_version=d["bench_version"],
            tasks=[BenchTask.from_dict(t) for t in d["tasks"]],
            notes=d.get("notes", ""), planted=list(d.get("planted", [])),
        )


def scoring_version() -> str:
    """Re-exported so a bundle writer never hard-codes the string it must agree with."""
    return SCORING_VERSION
