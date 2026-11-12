"""raptor.py - RAPTOR-class collapsed-tree retrieval at a declared budget.

RAPTOR (Sarthi et al., 2024) clusters a corpus, has a language model write a summary of every
cluster, recurses on the summaries, and then retrieves from the COLLAPSED TREE: every summary and
every leaf in one flat pool, ranked together by one cosine. The paper's own finding is that the
collapsed form beats tree traversal, so that is what this arm implements.

The fold - clustering, dispatching the summaries, embedding them, and recording every model call -
lives in ``atlas.bench.raptor_fold`` and is driven by ``atlas.tools.raptor_fold``. This file is
only the arm: it LOADS a banked fold and retrieves against it.

THE ARM NEVER FOLDS. If the fold is absent it refuses by name. A benchmark that can spend a model
bill by being run is a benchmark whose costs nobody counted, and the whole point of the five cost
dimensions is that the fold bill is visible BEFORE the correctness number is read (the Phase 3
gate: "RAPTOR's fold bill recorded before its correctness is read"). So the bill is incurred by an
explicit tool invocation, banked as an artifact, and merely reported here.

WHAT IS COUNTED, AND HOW IT IS PREVENTED FROM DRIFTING. ``fold_model_calls`` is DECLARED in the
protocol from the fold manifest's summary field, and the ``FoldCost`` this arm returns RECOUNTS it
from the manifest's per-call rows. The runner then asserts the two are equal. So a manifest whose
headline number was edited without editing its evidence raises ``ProtocolViolation`` instead of
serving a cheaper-looking fold. ``query_model_calls`` is zero and is counted by the wrapper like
every other arm's: the collapsed-tree read is pure arithmetic, which is the claim - intelligence
paid once at fold time, structure queried mechanically.

THE READ PROTOCOL IS ``dense_flat``'S, deliberately unchanged: same k, same byte budget, same
counting reader. RAPTOR differs from that arm in exactly one respect - what is in the pool - so
the comparison isolates the structure. A summary served into context is charged its bytes through
``read_text`` (it is text the arm assembled, not a span of the record); a leaf span is charged
through ``read_span`` exactly as ``dense_flat`` charges it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from ...encoders.bge_onnx import BgeOnnxEncoder, resolve_model_dir
from ...errors import ArmUnavailable
from ...segment import SEGMENTATION_RECIPE_VERSION
from ..cost import FoldCost, ModelCounter, SpanReader
from ..protocol import ArmProtocol
from ..raptor_fold import RAPTOR_RECIPE_VERSION, load_fold
from ..task import BenchTask
from ..universe import SnapshotView
from .base import ArmAnswer, BaseArm

DEFAULT_K = 10
READ_BUDGET_BYTES = 1 * 1024 * 1024

#: Summary ids are prefixed so that nothing downstream can mistake a model-written paragraph for
#: a span of the record - in the rows, in the planted control, or in a reader's eye.
SUMMARY_PREFIX = "raptor:"


class RaptorArm(BaseArm):
    """Collapsed-tree retrieval over a banked fold: cluster summaries + leaf spans, one cosine."""

    def __init__(self, fold_dir: Path, projection_store: Path, k: int = DEFAULT_K,
                 seed: int = 20260801, model_dir: str | Path | None = None) -> None:
        self.k = k
        self.fold_dir = Path(fold_dir)
        self.projection_store = Path(projection_store)
        self.model_dir = model_dir
        self.encoder = BgeOnnxEncoder(model_dir=model_dir)

        loaded = load_fold(self.fold_dir)
        self.manifest: dict[str, Any] = loaded["manifest"]
        self.summaries: list[dict[str, Any]] = loaded["summaries"]
        declared_calls = int(self.manifest.get("model_calls", 0))

        self.protocol = ArmProtocol(
            arm_id="raptor", variant="",
            segmentation_recipe_version=SEGMENTATION_RECIPE_VERSION,
            input_recipe_version=RAPTOR_RECIPE_VERSION,
            encoder_id=self.encoder.encoder_id, schema_version=None,
            k=k, max_spans_read=k, max_whole_file_reads=0,
            read_budget_bytes=READ_BUDGET_BYTES, rounds=1, beam=None, max_materialized=k,
            granularity="span",
            fold_model_calls=declared_calls, query_model_calls=0,
            model_stamp=self.manifest.get("model_requested", "sonnet"), seed=seed,
            note=(f"collapsed-tree retrieval over {len(self.summaries)} cluster summaries written "
                  f"by dispatched agents at an explicit model stamp, plus every leaf span, in one "
                  f"cosine pool; the read protocol is dense_flat's unchanged"),
        )
        self._matrix: np.ndarray | None = None
        self._ids: list[str] = []
        self._is_summary: np.ndarray | None = None
        self._summary_text: dict[str, str] = {
            SUMMARY_PREFIX + row["cluster_id"]: row["summary"] for row in self.summaries
        }
        self._folded_universe: str | None = None

    # --- the fold (loading it; it was paid for elsewhere) ------------------

    def fold(self, view: SnapshotView, segmentation_id: str = "") -> FoldCost:
        # PROVENANCE FIRST, encoder second. Both refuse, but the order is deliberate: a fold from
        # the wrong corpus is wrong whether or not an encoder happens to be installed, and the
        # specific refusal is more use to a reader than "no model weights". It also means the two
        # provenance refusals have unit tests that need no model.
        generation = self.manifest.get("generation", {})
        # The fold is keyed by UNIVERSE as well as snapshot, because a tree is a property of a set
        # of spans. Refusing a mismatch is what stops a fold built over a view that contains the
        # answer key from ever serving the headline view.
        if generation.get("snapshot_id") != view.snapshot_id:
            raise ArmUnavailable("the banked RAPTOR fold was built over a different snapshot",
                                 fold=generation.get("snapshot_id"), view=view.snapshot_id)
        if generation.get("universe_id") != view.universe_id:
            raise ArmUnavailable(
                "the banked RAPTOR fold was built over a different universe - a cluster tree is a "
                "property of the SET of spans, so a fold from another view is another instrument",
                fold_universe=generation.get("universe"), view_universe=view.universe.name)
        if not BgeOnnxEncoder.available(self.model_dir):
            raise ArmUnavailable(
                "the bge encoder is not available: set LAPLACE_EMBED_MODEL_DIR to the extracted "
                "vendored model. Never a quiet degrade to a hash encoder",
                arm="raptor", model_dir=str(resolve_model_dir(self.model_dir)),
            )

        summary_vectors = np.load(self.fold_dir / "vectors.npy")
        if summary_vectors.shape[0] != len(self.summaries):
            raise ArmUnavailable("fold vectors and summaries disagree in count",
                                 vectors=int(summary_vectors.shape[0]),
                                 summaries=len(self.summaries))
        leaf = self._leaf_matrix(generation.get("projection_generation_id", ""), view)

        self._matrix = np.vstack([np.asarray(summary_vectors, dtype=np.float32), leaf])
        self._ids = ([SUMMARY_PREFIX + row["cluster_id"] for row in self.summaries]
                     + [s.span_id for s in view.leaf_spans])
        flags = np.zeros(len(self._ids), dtype=bool)
        flags[: len(self.summaries)] = True
        self._is_summary = flags
        self._folded_universe = view.universe_id

        # RECOUNTED from the per-call rows, never taken from the manifest's headline. The runner
        # compares this against the protocol's DECLARED number, which does come from the headline.
        calls = self.manifest.get("calls") or []
        return FoldCost(
            wall_seconds=float(self.manifest.get("fold_wall_seconds", 0.0)),
            wall_seconds_this_call=0.0,
            model_calls=len(calls),
            model_tokens=int(self.manifest.get("prompt_tokens_estimate_bytes_over_4", 0)),
            vectors_built=int(self.manifest.get("summary_vectors_built", 0)),
            bytes_stored=int(self.manifest.get("vector_bytes", 0)),
            cached=True,
        )

    def _leaf_matrix(self, generation_id: str, view: SnapshotView) -> np.ndarray:
        """The leaf vectors ``dense_flat`` banked, by span content hash. Record spans never re-embed.

        ONE class of span is legitimately absent from the banked projection and is embedded here:
        the planted-bad control's synthetic spans. They exist only in a COPY of the view, they are
        new text, and their whole purpose is to be rankable - refusing them would silently exempt
        this arm from the control that catches confident wrong answers. They are embedded exactly
        as ``dense_flat`` embeds them (a cache miss is a miss, not a stale hit), and the count is
        asserted to be only the planted set: a real record span missing from the projection means
        the fold was built over a different corpus, and that still refuses.
        """
        import json

        gen_dir = self.projection_store / generation_id.split(":", 1)[-1]
        keys_path, vec_path = gen_dir / "keys.json", gen_dir / "vectors.npy"
        if not keys_path.is_file() or not vec_path.is_file():
            raise ArmUnavailable("the dense projection this fold was built on is not banked",
                                 generation=generation_id, path=str(gen_dir))
        keys = json.loads(keys_path.read_text(encoding="utf-8"))
        matrix = np.load(vec_path)
        index = {key: i for i, key in enumerate(keys)}
        planted_ids = {p.planted_id for p in view.planted}

        rows: list[int | None] = []
        misses: list[str] = []
        for span in view.leaf_spans:
            row = index.get(view.span_content_hash(span))
            if row is None:
                if span.span_id not in planted_ids:
                    raise ArmUnavailable(
                        "the banked projection does not cover a RECORD span of this view - the "
                        "fold was built over a different corpus",
                        span_id=span.span_id, generation=generation_id)
                misses.append(span.span_id)
            rows.append(row)

        out = np.zeros((len(rows), matrix.shape[1]), dtype=np.float32)
        known = [i for i, row in enumerate(rows) if row is not None]
        out[known] = matrix[[rows[i] for i in known]]
        if misses:
            unknown = [i for i, row in enumerate(rows) if row is None]
            texts = [view.span_text(view.leaf_spans[i]) for i in unknown]
            out[unknown] = np.asarray(self.encoder.embed(texts), dtype=np.float32)
        return out

    # --- the query --------------------------------------------------------

    def answer(self, task: BenchTask, reader: SpanReader, models: ModelCounter) -> ArmAnswer:
        view = reader.view
        if self._matrix is None or self._folded_universe != view.universe_id:
            raise ArmUnavailable("the RAPTOR pool was not folded over this universe",
                                 folded=self._folded_universe, asked=view.universe_id)
        qvec = np.asarray(self.encoder.query(task.question), dtype=np.float32)
        sims = self._matrix @ qvec
        # Ties break on the id, as in dense_flat, so the ranking is a property of the pool.
        order = sorted(range(len(sims)), key=lambda i: (-float(sims[i]), self._ids[i]))

        parts: list[str] = []
        retrieved: list[str] = []
        retrieved_texts: list[str] = []
        top = order[: self.k]
        summaries_served = 0
        for index in top:
            item_id = self._ids[index]
            if self._is_summary[index]:
                text = reader.read_text(self._summary_text[item_id])
                summaries_served += 1
            else:
                span = view.span_by_id(item_id)
                if span is None:
                    continue
                text = reader.read_span(span)
            parts.append(text)
            retrieved.append(item_id)
            retrieved_texts.append(text)
        return ArmAnswer(
            context="\n".join(parts), rounds=1, retrieved=retrieved,
            retrieved_texts=retrieved_texts,
            note=f"collapsed tree top-{self.k}: {summaries_served} summaries, "
                 f"{len(retrieved) - summaries_served} leaf spans",
            detail={"scores": [round(float(sims[i]), 4) for i in top],
                    "fold_id": self.manifest.get("fold_id")},
        )
