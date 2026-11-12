"""arms - the Tier-1 baselines. Every one of them reads the SNAPSHOT, never the repository.

That is the sentence the whole phase turns on. The v1 arms read live files, so the corpus under
them moved between the freeze and the next morning and the instrument reported the movement as a
result. Here an arm is handed a ``SnapshotView`` and a ``SpanReader`` and has no other way to
obtain text: the view refuses anything the declared universe excludes, and the reader counts
every byte that reaches a scoring context.

Tier 1 - four arms, where the fifth entry is a variant rather than an arm:

    flat_read (B)     the orientation set CLAUDE.md itself names, read whole
    flat_read (B+)    the same plus STANDING_LAW.md and OPEN_STACK.md - the charitable set
    grep_skilled      v1 arm C: a pattern derived from the QUESTION STRING ONLY, two rounds
    bm25              Okapi BM25 over leaf spans, pure python, k1=1.5 b=0.75
    dense_flat        bge-small over leaf spans, cosine top-k

Tier 2 - Phase 3, the two comparators the study exists to produce:

    raptor            RAPTOR-class collapsed-tree retrieval at a declared summary budget; the one
                      arm that pays a MODEL bill at fold time, counted call by call
    incumbent_arch    the engine's own architecture rebuilt over the snapshot - v1-title node
                      digests, spectral tree, beam descent, arm-A read protocol

The optional atlas arm measures stored-face retrieval with exact frozen-span reads.
It is explicitly selected with a read-only store; other atlas ablations remain absent.

The two Tier-2 arms are NOT exported into a default arm list. Both need a constructor argument
(a banked fold directory, a projection store) and ``raptor`` refuses to exist without a fold that
cost money to build; a default list that silently included them would turn "run the bench" into a
command whose failure mode is a bill.
"""

from __future__ import annotations

from .atlas_arm import AtlasArm
from .base import Arm, ArmAnswer
from .bm25 import Bm25Arm
from .dense_flat import DenseFlatArm
from .flat_read import FlatReadArm
from .grep_skilled import GrepSkilledArm
from .incumbent_arch import IncumbentArchArm
from .raptor import RaptorArm

#: The Tier-1 set in report order: the two flat variants, then the two retrieval arms.
TIER_1 = ("flat_read:B", "flat_read:B+", "grep_skilled", "bm25", "dense_flat")

#: Phase 3's additions, in report order after Tier 1.
TIER_2 = ("raptor", "incumbent_arch")

#: The full fair table, in the order the summary renders it.
SEVEN_ARM_TABLE = TIER_1 + TIER_2

__all__ = ["TIER_1", "TIER_2", "SEVEN_ARM_TABLE", "Arm", "ArmAnswer", "Bm25Arm", "DenseFlatArm",
           "FlatReadArm", "GrepSkilledArm", "IncumbentArchArm", "RaptorArm"]

# Applicability describes what the implemented readers can consume, before scoring.
APPLICABLE_KINDS = {
    "flat_read:B": ("md",), "flat_read:B+": ("md",),
    "grep_skilled": ("md", "py", "jsonl"),
    "bm25": ("tex", "md", "py", "jsonl", "json", "txt", "js", "ts", "html", "css"),
    "dense_flat": ("tex", "md", "py", "jsonl", "json", "txt", "js", "ts", "html", "css"),
    "incumbent_arch": ("tex", "md", "py", "jsonl", "json", "txt", "yaml", "yml", "bib"),
    "raptor": ("tex", "md", "py", "jsonl", "json", "txt", "js", "ts", "html", "css"),
    "atlas": ("tex", "md", "py", "jsonl", "json", "txt", "js", "ts", "html", "css"),
}
