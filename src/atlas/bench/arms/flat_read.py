"""flat_read.py - the orientation set CLAUDE.md itself names, read whole, FROM THE SNAPSHOT.

v1 arms B and B+, ported. The set is not chosen here; it is quoted from the engine's own ambient
instruction, which names the linear read as the fallback for a failed reconstruction:
``HANDOFF.md``, the latest ``SESSION_HANDOFF_*``, the ``EIGEN_DIARY.md`` tail,
``EIGEN_ARCHITECTURE.md`` - plus the two files any session loads ambiently
(``CLAUDE.md``, ``AGENTS.md``). The B+ variant adds ``STANDING_LAW.md`` and ``OPEN_STACK.md``:
the charitable set, which answers more and costs more, and which the v1 run showed was the
honest comparator rather than the strawman.

The diary is read as a TAIL, because the instruction's own word is tail. Reading the whole 540 KB
file was the definitional error that inflated the v1 headline before the run corrected it; the
correction is banked at ``evidence/reconstruction_bench_2026-07-28/README.md`` and the tail is
what this arm reads. The open is still an open: the whole file's remaining bytes are recorded as
``scan_bytes``, reported beside the bill and never inside it.

ONE PORTED BEHAVIOUR CHANGED, DELIBERATELY. v1 found "the latest SESSION_HANDOFF" by asking git
for each file's last commit time. A frozen snapshot has no working tree and no git, so the rule
here is the LEXICOGRAPHIC MAXIMUM of the handoff node ids. The names are ISO-date-prefixed
(``SESSION_HANDOFF_2026-07-30_the-founding-night.md``), so the two rules agree on this corpus and
the snapshot rule is the one that stays reproducible when the repository is gone.

This arm retrieves nothing: ``retrieved`` is empty, and the planted-bad control reads its context
instead of its ranking. An arm with a fixed read set cannot rank a planted span - and cannot be
protected from one either, which is itself the measurement.
"""

from __future__ import annotations

import re

from ...segment import SEGMENTATION_RECIPE_VERSION
from ..cost import ModelCounter, SpanReader
from ..protocol import NO_MODEL, ArmProtocol
from ..task import BenchTask
from ..universe import SnapshotView
from .base import ArmAnswer, BaseArm

#: The two files any session loads before it does anything.
AMBIENT = ("CLAUDE.md", "AGENTS.md")
#: The linear read, quoted from the ambient instruction.
NAMED = ("HANDOFF.md", "EIGEN_ARCHITECTURE.md")
#: What the charitable variant adds.
BPLUS_EXTRA = ("STANDING_LAW.md", "OPEN_STACK.md")
#: The instruction says "tail"; v1 fixed it at five entries and this port keeps that number.
DIARY_NODE = "EIGEN_DIARY.md"
DIARY_TAIL_ENTRIES = 5
HANDOFF_GLOB_PREFIX = "SESSION_HANDOFF_"

#: Read budget: the charitable set is ~1.2 MB and the cap must not bind. It is declared anyway,
#: because an undeclared budget is the seam J6 hole - a cap that never fires is still a cap.
READ_BUDGET_BYTES = 8 * 1024 * 1024


def latest_session_handoff(view: SnapshotView) -> str | None:
    """The lexicographic maximum SESSION_HANDOFF node id in the view. ISO names sort by date."""
    names = [n for n in view.node_ids
             if n.startswith(HANDOFF_GLOB_PREFIX) and n.endswith(".md") and "/" not in n]
    return max(names) if names else None


def diary_tail(text: str, entries: int = DIARY_TAIL_ENTRIES) -> str:
    """The last ``entries`` ``## `` sections. Ported from v1 unchanged."""
    heads = [m.start() for m in re.finditer(r"(?m)^## ", text)]
    return text[heads[-entries]:] if len(heads) >= entries else text


class FlatReadArm(BaseArm):
    """The flat orientation read. ``variant`` is ``B`` (quoted set) or ``B+`` (charitable set)."""

    def __init__(self, variant: str = "B", seed: int = 20260801) -> None:
        if variant not in ("B", "B+"):
            raise ValueError(f"flat_read variant must be B or B+, got {variant!r}")
        self.variant = variant
        extra = len(BPLUS_EXTRA) if variant == "B+" else 0
        self.protocol = ArmProtocol(
            arm_id="flat_read", variant=variant,
            segmentation_recipe_version=SEGMENTATION_RECIPE_VERSION,
            input_recipe_version="flat-read/1", encoder_id=None, schema_version=None,
            k=0, max_spans_read=0,
            max_whole_file_reads=len(AMBIENT) + len(NAMED) + 1 + 1 + extra,
            read_budget_bytes=READ_BUDGET_BYTES, rounds=1, beam=None, max_materialized=None,
            granularity="node", fold_model_calls=0, query_model_calls=0,
            model_stamp=NO_MODEL, seed=seed,
            note=("the orientation set the ambient instruction names, read whole from the "
                  "snapshot; the diary is read as a tail, per the instruction's own word"),
        )

    def _set(self, view: SnapshotView) -> list[str]:
        names = [n for n in AMBIENT + NAMED if view.has_node(n)]
        latest = latest_session_handoff(view)
        if latest:
            names.append(latest)
        if self.variant == "B+":
            names.extend(n for n in BPLUS_EXTRA if view.has_node(n))
        return names

    def answer(self, task: BenchTask, reader: SpanReader, models: ModelCounter) -> ArmAnswer:
        parts: list[str] = []
        read: list[str] = []
        for node_id in self._set(reader.view):
            parts.append(reader.read_node(node_id))
            read.append(node_id)
        if reader.view.has_node(DIARY_NODE):
            whole = reader.view.node_text(DIARY_NODE)
            parts.append(reader.read_node_excerpt(DIARY_NODE, diary_tail(whole)))
            read.append(f"{DIARY_NODE} (tail {DIARY_TAIL_ENTRIES})")
        return ArmAnswer(
            context="\n".join(parts), rounds=1, retrieved=[],
            note=f"set={len(read)} files",
            detail={"files": read},
        )
