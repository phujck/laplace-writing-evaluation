"""base.py - the Arm contract: declare, fold once, answer under the reader.

An arm is three things and nothing else:

    ``protocol``   an ``ArmProtocol``, complete before the arm reads anything (seam J6)
    ``fold``       whatever it pays ONCE over the view, returning a ``FoldCost``. Mechanical arms
                   still fold - BM25 builds postings, dense_flat builds vectors - and the bill is
                   recorded whether or not a model was involved.
    ``answer``     one task, under a ``SpanReader`` that counts and a ``ModelCounter`` that
                   counts. Returns an ``ArmAnswer``.

``ArmAnswer.retrieved`` is a RANKED list of span ids. It is not used for scoring - scoring reads
the context - but it is what the planted-bad control needs: a false positive is a planted span
appearing at rank <= k, which is a question about the ranking and not about the prose. Phase 3's
rank columns read it too.

``ArmAnswer.retrieved_texts`` is the OPTIONAL text of each retrieved item, in rank order. The
span-level arms leave it empty, because the runner can resolve a span id against the view. The
arms that rank something which is NOT a leaf span have to supply it: RAPTOR ranks cluster
summaries that exist only in its fold store, and the incumbent ranks whole nodes. Without it the
rank columns would score those arms against empty strings and report them as never retrieving
their own evidence - an instrument bug that would read as a result.

Determinism is a property of the arms, not of the runner. Nothing here reads a clock, a random
source or an environment-dependent ordering; where an arm needs a tie-break it uses the span id,
which is a content hash. The seed lives in the protocol so that an arm which later acquires a
random component has a declared place to take it from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..cost import FoldCost, ModelCounter, SpanReader
from ..protocol import ArmProtocol
from ..task import BenchTask
from ..universe import SnapshotView


@dataclass
class ArmAnswer:
    """What one arm produced for one task. ``context`` is the only thing scoring reads."""

    context: str
    rounds: int
    retrieved: list[str] = field(default_factory=list)
    retrieved_texts: list[str] = field(default_factory=list)
    note: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


class Arm(Protocol):
    protocol: ArmProtocol

    def fold(self, view: SnapshotView, segmentation_id: str = "") -> FoldCost:
        ...

    def answer(self, task: BenchTask, reader: SpanReader, models: ModelCounter) -> ArmAnswer:
        ...


class BaseArm:
    """Shared plumbing: a no-op fold and the protocol accessors. Arms override what they need.

    ``segmentation_id`` is on the signature for every arm, not only the ones that use it: a fold
    is a projection of a (snapshot, segmentation) pair, and an arm that ignores the segmentation
    id should ignore it visibly rather than have a different shape from the ones that do not.
    """

    protocol: ArmProtocol

    def fold(self, view: SnapshotView, segmentation_id: str = "") -> FoldCost:
        return FoldCost()

    @property
    def arm_id(self) -> str:
        return self.protocol.full_id

    def answer(self, task: BenchTask, reader: SpanReader,
               models: ModelCounter) -> ArmAnswer:      # pragma: no cover - contract only
        raise NotImplementedError
