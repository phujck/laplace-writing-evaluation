"""dense_flat.py - flat dense retrieval: bge-small over leaf spans, cosine top-k.

The dense RAG baseline the comparative study needs, and the one that pays a real fold bill. It
is deliberately FLAT: one vector per leaf span, one cosine ranking, no hierarchy and no descent.
Whatever the atlas eventually claims over it has to be claimed against this.

THE CACHE IS CONTENT-KEYED. A vector is stored under the hash of the SPAN'S BYTES, not under its
position or its span id, so:

  * re-running the same view re-uses every vector and folds in zero model seconds;
  * the FULL-universe control re-uses every vector the filtered view already built, and pays only
    for the spans the filter had excluded;
  * a span whose bytes changed cannot silently serve a stale vector - its key is different, and a
    different key is a miss, not a match. This is the design's rule that a vector whose source
    hash disagrees with the snapshot refuses rather than re-embedding in place.

Layout, under ``atlas/stores/projections/<generation_id>/``: ``vectors.npy`` (float32, N x dim,
L2-unit rows), ``keys.json`` (the content hashes in row order) and ``manifest.json`` (the
generation metadata). The vectors are gitignored and regenerable; the manifest is committed, so
what was built is in the record even though the floats are not.

``generation_id`` folds all four version axes plus the snapshot, the universe and the encoder's
declared dim and normalisation - so an encoder swap or a re-segmentation is a NEW generation with
its own directory, never a silent rewrite of the coordinates already banked.

``LAPLACE_EMBED_THREADS`` is read from the environment and passed to the encoder. It exists
because an uncapped ONNX batch embed starves this box; the engine respects it and so does this.
Reading an environment variable is the whole of the coupling - the seal forbids the import, and
nothing here knows what laplace does with the same name.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import numpy as np

from ...encoders.bge_onnx import BgeOnnxEncoder, resolve_model_dir
from ...errors import ArmUnavailable
from ...ids import chash
from ...segment import SEGMENTATION_RECIPE_VERSION
from ...store import write_atomic
from ..cost import FoldCost, ModelCounter, SpanReader
from ..protocol import NO_MODEL, ArmProtocol
from ..task import BenchTask
from ..universe import SnapshotView
from .base import ArmAnswer, BaseArm

DEFAULT_K = 10
READ_BUDGET_BYTES = 1 * 1024 * 1024
EMBED_BATCH = 64
#: Cache checkpoint cadence, in batches. A repo-scale fold is hours of CPU on this box; writing
#: every ~6,400 vectors bounds what one interruption costs without making the write the job.
CHECKPOINT_EVERY_BATCHES = 100
THREADS_ENV = "LAPLACE_EMBED_THREADS"

#: THE INPUT RECIPE, and it is a version axis because it is an input decision.
#:
#: Span text is truncated to ``MAX_INPUT_CHARS`` before it reaches the encoder. The truncation is
#: PROVABLY INERT on the vectors: bge-small truncates its own input at 512 tokens, which is at
#: most ~2,048 characters even for the worst tokenization (roughly four characters a token on
#: pathological content), so 4,096 characters is strictly above the point the encoder itself cuts.
#: No span's vector changes. What it removes is TOKENIZER work on pathological spans - this
#: corpus's segmentation carries 902 oversize spans that could not be split, the largest 984,764
#: bytes, and tokenizing a megabyte to then discard all but 512 tokens dominated the fold's wall
#: clock. Measured before and after on a seeded 512-span sample: 5.3 -> 11.8 texts/second.
#: Declared in the recipe version anyway, because an input decision that is not in a version axis
#: is an unmeasured one.
MAX_INPUT_CHARS = 4096
INPUT_RECIPE_VERSION = "dense-span-head4k/1"

#: The default projection store. Vectors gitignored, manifest committed (see .gitignore).
DEFAULT_STORE = Path(__file__).resolve().parents[4] / "atlas" / "stores" / "projections"   # the container's stores (R2)


def _threads() -> int | None:
    raw = (os.environ.get(THREADS_ENV) or "").strip()
    if not raw:
        return None
    try:
        n = int(raw)
    except ValueError:
        raise ArmUnavailable(f"{THREADS_ENV} is set but is not an integer", value=raw) from None
    return n if n > 0 else None


class DenseFlatArm(BaseArm):
    """One vector per leaf span; cosine top-k; the fold cached by span content hash."""

    def __init__(self, k: int = DEFAULT_K, seed: int = 20260801,
                 store_root: Path | None = None, model_dir: str | Path | None = None,
                 progress=None) -> None:
        self.k = k
        self.store_root = Path(store_root) if store_root else DEFAULT_STORE
        self.model_dir = model_dir
        #: Optional ``(built, wanted, seconds) -> None`` called at each cache checkpoint. A fold
        #: measured in hours that prints nothing is indistinguishable from a fold that hung.
        self.progress = progress
        from ...runtime import preload_cuda_libraries
        preload_cuda_libraries()
        self.encoder = BgeOnnxEncoder(model_dir=model_dir, threads=_threads())
        self.protocol = ArmProtocol(
            arm_id="dense_flat", variant="",
            segmentation_recipe_version=SEGMENTATION_RECIPE_VERSION,
            input_recipe_version=INPUT_RECIPE_VERSION,
            encoder_id=self.encoder.encoder_id, schema_version=None,
            k=k, max_spans_read=k, max_whole_file_reads=0,
            read_budget_bytes=READ_BUDGET_BYTES, rounds=1, beam=None, max_materialized=k,
            granularity="span", fold_model_calls=0, query_model_calls=0,
            model_stamp=NO_MODEL, seed=seed,
            note=("flat dense retrieval; the encoder is a vectoriser, not a generative model - "
                  "fold and query model calls are both zero and both counted"),
        )
        self._matrix: np.ndarray | None = None
        self._span_ids: list[str] = []
        self._folded_universe: str | None = None
        self.generation_id: str | None = None

    # --- the generation ---------------------------------------------------

    def generation(self, view: SnapshotView, segmentation_id: str) -> dict[str, Any]:
        """All four version axes plus the corpus and the encoder contract, in one record."""
        return {
            "kind": "projection-generation/1",
            "snapshot_id": view.snapshot_id,
            "segmentation_id": segmentation_id,
            "segmentation_recipe_version": SEGMENTATION_RECIPE_VERSION,
            "input_recipe_version": INPUT_RECIPE_VERSION,
            "encoder_id": self.encoder.encoder_id,
            "schema_version": None,
            "dim": self.encoder.dim,
            "normalisation": "l2-unit",
            "granularity": "leaf-span",
        }

    def store_dir(self, generation_id: str) -> Path:
        return self.store_root / generation_id.split(":", 1)[-1]

    # --- the fold ---------------------------------------------------------

    def fold(self, view: SnapshotView, segmentation_id: str = "") -> FoldCost:
        if not BgeOnnxEncoder.available(self.model_dir):
            raise ArmUnavailable(
                "the bge encoder is not available: set LAPLACE_EMBED_MODEL_DIR to the extracted "
                "vendored model (the directory holding model_optimized.onnx) and install the "
                "'encoders' extra. Never a quiet degrade to a hash encoder - a silent swap of "
                "geometry is what encoder_id exists to prevent",
                arm="dense_flat", model_dir=str(resolve_model_dir(self.model_dir)),
            )
        gen = self.generation(view, segmentation_id)
        # The universe is NOT part of the generation: vectors are a property of spans, and a
        # filtered view and the full view share every span they both contain. Keying the cache by
        # universe would rebuild 68,000 identical vectors for the control run.
        self.generation_id = chash(gen)
        out_dir = self.store_dir(self.generation_id)
        keys_path, vec_path = out_dir / "keys.json", out_dir / "vectors.npy"

        cache: dict[str, int] = {}
        matrix: np.ndarray | None = None
        # THE BILL SO FAR. The seconds already spent building the vectors in this cache, carried
        # in the generation manifest so a cached fold reports what the index COST rather than what
        # reloading it cost. Seam J7: a fold bill that vanishes when the cache is warm is a fold
        # bill hidden inside a query-time win.
        prior_build_seconds = 0.0
        manifest_path = out_dir / "manifest.json"
        if manifest_path.is_file():
            prior = json.loads(manifest_path.read_text(encoding="utf-8"))
            prior_build_seconds = float(prior.get("build_wall_seconds", 0.0))
        if keys_path.is_file() and vec_path.is_file():
            keys = json.loads(keys_path.read_text(encoding="utf-8"))
            matrix = np.load(vec_path)
            if matrix.shape[0] != len(keys):
                raise ArmUnavailable("projection cache is inconsistent: rows and keys disagree",
                                     rows=int(matrix.shape[0]), keys=len(keys),
                                     path=str(out_dir))
            cache = {key: i for i, key in enumerate(keys)}
        else:
            keys = []

        started = time.perf_counter()
        wanted: list[str] = []
        span_keys: list[str] = []
        seen: set[str] = set()
        texts: dict[str, str] = {}
        for span in view.leaf_spans:
            key = view.span_content_hash(span)
            span_keys.append(key)
            if key in cache or key in seen:
                continue
            seen.add(key)
            wanted.append(key)
            texts[key] = view.span_text(span)[:MAX_INPUT_CHARS]

        # Batch by LENGTH, not by corpus order. A batch pads to its longest member, so a mixed
        # batch spends most of its arithmetic on padding; sorting makes batches homogeneous.
        # It changes which vectors share a batch, never which text produces which vector, and the
        # cache is keyed by content hash - so the fold's OUTPUT is order-independent. Measured on
        # a seeded 512-span sample: 5.3 -> 10.0 texts/second from sorting alone.
        wanted.sort(key=lambda key: (len(texts[key]), key))

        built = 0
        if wanted:
            base = matrix
            base_keys = list(keys)
            new_rows: list[list[float]] = []
            out_dir.mkdir(parents=True, exist_ok=True)

            def checkpoint() -> np.ndarray:
                """Write the cache as it stands. Keys and rows are written in lockstep, so a
                crash mid-fold leaves a smaller VALID cache and the next run resumes from it -
                a fold over a repo-scale corpus is tens of minutes, and losing all of it to one
                interruption is the difference between a cache and a gamble."""
                block = np.asarray(new_rows, dtype=np.float32)
                whole = block if base is None else np.vstack([base, block])
                # ATOMIC, like every other write in this package. ``np.save`` writes in place, so
                # a crash - or a reader arriving mid-write - sees a truncated .npy whose header
                # still parses. Temp file, then replace: a reader sees the old cache or the new
                # one, never half of one.
                tmp = vec_path.with_name(vec_path.name + ".tmp")
                with open(tmp, "wb") as fh:
                    np.save(fh, whole)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp, vec_path)
                write_atomic(keys_path,
                             (json.dumps(base_keys + wanted[:len(new_rows)]) + "\n")
                             .encode("utf-8"))
                return whole

            for index, start in enumerate(range(0, len(wanted), EMBED_BATCH)):
                batch = wanted[start:start + EMBED_BATCH]
                new_rows.extend(self.encoder.embed([texts[key] for key in batch]))
                if (index + 1) % CHECKPOINT_EVERY_BATCHES == 0:
                    checkpoint()
                    if self.progress is not None:
                        self.progress(len(new_rows), len(wanted),
                                      time.perf_counter() - started)
            built = len(new_rows)
            matrix = checkpoint()
            keys = base_keys + wanted
            cache = {key: i for i, key in enumerate(keys)}
        wall = time.perf_counter() - started

        if matrix is None:
            raise ArmUnavailable("dense fold produced no vectors", arm="dense_flat")
        build_seconds = prior_build_seconds + (wall if built else 0.0)
        write_atomic(manifest_path,
                     (json.dumps({**gen, "generation_id": self.generation_id,
                                  "vector_count": int(matrix.shape[0]),
                                  "dim": int(matrix.shape[1]),
                                  "build_wall_seconds": round(build_seconds, 4),
                                  "max_input_chars": MAX_INPUT_CHARS,
                                  "embed_batch": EMBED_BATCH},
                                 sort_keys=True, indent=2) + "\n").encode("utf-8"))

        rows = [cache[key] for key in span_keys]
        self._matrix = matrix[rows] if rows else np.zeros((0, self.encoder.dim), dtype=np.float32)
        self._span_ids = [s.span_id for s in view.leaf_spans]
        self._folded_universe = view.universe_id
        return FoldCost(
            wall_seconds=build_seconds, wall_seconds_this_call=wall, model_calls=0,
            model_tokens=0, vectors_built=built, bytes_stored=int(matrix.nbytes),
            cached=(built == 0),
        )

    # --- the query --------------------------------------------------------

    def answer(self, task: BenchTask, reader: SpanReader, models: ModelCounter) -> ArmAnswer:
        view = reader.view
        if self._matrix is None or self._folded_universe != view.universe_id:
            raise ArmUnavailable("dense index was not folded over this universe",
                                 folded=self._folded_universe, asked=view.universe_id)
        qvec = np.asarray(self.encoder.query(task.question), dtype=np.float32)
        sims = self._matrix @ qvec
        # Ties break on the span id - a content hash - so the ranking is a property of the corpus.
        order = sorted(range(len(sims)), key=lambda i: (-float(sims[i]), self._span_ids[i]))
        parts: list[str] = []
        retrieved: list[str] = []
        top = order[: self.k]
        for index in top:
            span = view.span_by_id(self._span_ids[index])
            if span is None:
                continue
            parts.append(reader.read_span(span))
            retrieved.append(span.span_id)
        return ArmAnswer(
            context="\n".join(parts), rounds=1, retrieved=retrieved,
            note=f"top-{self.k} spans, cosine",
            detail={"scores": [round(float(sims[i]), 4) for i in top],
                    "generation_id": self.generation_id},
        )
