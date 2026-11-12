"""span_encoder.py - the DECLARED MEASUREMENT INTERFACE of a content axis, per span.

LIFTED, NOT RE-AUTHORED. The loader, the fp16-graph preference, the length-sorted batching and
the token-budgeted batch sizing are ``synthetics papers/corpus-as-a-state/numerics/common.py``
lines 36-97 (``Encoder.__init__``, ``Encoder.embed``), and the content-addressed cache is the
same file's ``embed_cached`` at :105-116 with ONE change that D.11 forces: that cache is keyed on
``sha256("\\n".join(texts))`` - the whole corpus in one key - and this one is keyed PER SPAN, on
the digest of that span's own recipe output, so inserting a span encodes one text and editing a
row re-encodes exactly the spans it addresses. ``atlas.encoders.base.EncoderSpec`` is reused for
identity (D.10) rather than a second identity being invented beside it.

WHAT THIS IS ALLOWED TO BE. D.1 admits E in exactly two roles: an OBSERVABLE of one authored
channel, and a COMPRESSION inside an accepted section's frame. It is never the affinity another
fibre's generator is built from (D.1(a)), never the final score of a fibre whose generator it
built (D.1(b)), and no record identity is a function of it (D.1(c), B.6). This module therefore
returns unit rows and their stored quantised form and NOTHING ELSE - it holds no index, computes
no similarity and ranks nothing. D.2's five classes (polarity, time and order, quantity,
identity, authority) are the typed rows' work and are never asked of a vector here.

THE CANDIDATES ARE THE ONES THIS MACHINE HOLDS, with the requirement clause each is admitted or
excluded by; the choice is recorded in ``CANDIDATES`` below and measured by
``evidence/ATLAS_PROGRAMME/waves/P1-the-leaf/encoder_choice.py``, never inherited (lean L9).

Complexity: ``embed`` is O(total tokens) of device work in a bounded number of batches, plus one
host sort of the texts by length; the cache makes a repeat call O(1) per already-seen span.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..errors import EncoderUnavailable
from .base import EncoderSpec

__all__ = ["CANDIDATES", "Candidate", "SpanEncoder", "span_encoder", "quantise", "dequantise",
           "survey", "STORED_FORM_DOC"]

#: Where the encoders this machine holds live. The same directory
#: ``synthetics papers/corpus-as-a-state/numerics/common.py:24`` names; read only.
MODELS = Path("/home/phujck/VScodeProjects/eigenengine-v2/models")
#: The fp16 ONNX graph fetched 2026-09-17 and measured there as identical embeddings (min cosine
#: 1.00000) at 1.3-1.9x the fp32 throughput; preferred on CUDA exactly as common.py:47-52 does.
FP16_GRAPHS = (Path(__file__).resolve().parents[3]
               / "synthetics papers/corpus-as-a-state/numerics/models")

#: The token budget of one ONNX batch. LIFTED from common.py:70-72 with its measurement: the
#: fused attention kernel's workspace grows with batch x L^2 and 64 texts at 512 tokens asked for
#: 1.2 GB on this card. It is a DEVICE capacity bound (D.8: the encoder must be evictable from a
#: 3.7 GiB card), not a quality dial - no output depends on it.
ONNX_TOKEN_BUDGET = 24576
ONNX_MAX_BATCH = 64


@dataclass(frozen=True, slots=True)
class Candidate:
    """One encoder this machine holds, with the contract clause that admits or excludes it."""

    encoder_id: str
    kind: str                     # 'onnx' | 'st'
    model_dir: str
    dim: int
    max_tokens: int
    doc_prefix: str
    query_prefix: str
    matryoshka: bool
    licence: str
    admitted_by: str
    excluded_by: str = ""

    @property
    def available(self) -> bool:
        return (MODELS / self.model_dir).is_dir()


#: THE SURVEY, as rows. D.15 names four finalists; three of them are not on this machine and no
#: network is available to this packet, so the survey is over what IS here and each row carries
#: the clause that admits it. The excluded rows are excluded by a clause, never by a score.
CANDIDATES: tuple[Candidate, ...] = (
    Candidate("bge-small-en-v1.5/onnx-fp16/1", "onnx", "bge-small-en-v1.5", 384, 512, "",
              "Represent this sentence for searching relevant passages: ", False, "MIT",
              admitted_by="D.4 second sentence: not Matryoshka-trained, so admitted at its "
                          "NATIVE dimension only and priced as a fixed-rank instrument "
                          "(r* = d_native = 384); D.8: 128 MB of weights on a 3.7 GiB card"),
    Candidate("multilingual-e5-small/st/1", "st", "multilingual-e5-small", 384, 512,
              "passage: ", "query: ", False, "MIT",
              admitted_by="D.4 second sentence, as above",
              excluded_by="L11 (the orchestrator's decided author-card item, 2026-09-21): "
                          "ENGLISH-ONLY NOW. A multilingual instrument spends capacity on "
                          "distinctions this corpus does not contain."),
    Candidate("qwen3-embedding-0.6b/st/1", "st", "qwen3-embedding-0.6b", 1024, 512, "",
              "", True, "Apache-2.0",
              admitted_by="D.4 first sentence: MRL-trained, so a rank ladder is readable from "
                          "one stored vector"),
)

STORED_FORM_DOC = (
    "D.7's ladder. int8 is the DEFAULT store and may carry a certificate: the code is "
    "round(v * 127 / peak) with peak = max|v| per row, the row scale is peak/127, and "
    "eps_j = ||dequant(code_j) - v_j||_2 is COMPUTED AND STORED per row at encode time so the "
    "D.7 bound can be published under the stored form. f32 stores the exact row and eps is "
    "identically zero; f16 rounds and stores its own measured eps."
)


def quantise(vectors: np.ndarray, dtype: str) -> dict[str, np.ndarray]:
    """One declared stored form of a unit matrix, with D.7's per-row eps MEASURED, not assumed.

    Whole-array: one pass for the peak, one for the code, one for the error norm. No Python loop
    over a row and no per-element tensor. Complexity: O(n d). Returns the arrays a segment holds.
    """
    exact = np.ascontiguousarray(vectors, dtype=np.float32)
    if dtype == "f32":
        return {"code": exact, "scale": np.ones(exact.shape[0], dtype=np.float32),
                "eps": np.zeros(exact.shape[0], dtype=np.float32)}
    if dtype == "f16":
        code = exact.astype(np.float16)
        eps = np.linalg.norm(code.astype(np.float32) - exact, axis=1).astype(np.float32)
        return {"code": code, "scale": np.ones(exact.shape[0], dtype=np.float32), "eps": eps}
    peak = np.maximum(np.abs(exact).max(axis=1), 1e-12).astype(np.float32)
    scale = (peak / 127.0).astype(np.float32)
    code = np.clip(np.rint(exact / scale[:, None]), -127, 127).astype(np.int8)
    eps = np.linalg.norm(code.astype(np.float32) * scale[:, None] - exact,
                         axis=1).astype(np.float32)
    return {"code": code, "scale": scale, "eps": eps}


def dequantise(code: np.ndarray, scale: np.ndarray, dtype: str) -> np.ndarray:
    """The stored form back to float32 rows - what every read actually scores against (D.7)."""
    if dtype in ("f32", "f16"):
        return np.ascontiguousarray(code, dtype=np.float32)
    scales = np.asarray(scale, dtype=np.float32)
    return np.ascontiguousarray(code, dtype=np.float32) * scales[:, None]


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


class SpanEncoder:
    """One encoder, loaded once, embedding spans in batches and caching by content address."""

    def __init__(self, candidate: Candidate, device: str = "cuda") -> None:
        self.candidate = candidate
        self.encoder_id = candidate.encoder_id
        self.dim = candidate.dim
        self.max_tokens = candidate.max_tokens
        self.device = device
        self._session: Any = None
        self._model: Any = None
        self._tokenizer: Any = None
        self._inputs: list[str] = []
        self._cache: dict[str, np.ndarray] = {}
        self.counters: dict[str, Any] = {
            "texts_encoded": 0, "cache_hits": 0, "tokens_encoded": 0, "batches": 0,
            "encode_seconds": 0.0, "load_seconds": 0.0}

    # ------------------------------------------------------------------ loading
    @property
    def model_dir(self) -> Path:
        path = MODELS / self.candidate.model_dir
        if not path.is_dir():
            raise EncoderUnavailable("no local model directory for this encoder",
                                     encoder_id=self.encoder_id, path=str(path))
        return path

    @property
    def spec(self) -> EncoderSpec:
        """D.10's named, hashed identity, bound to the ACTUAL local bytes. O(model bytes)."""
        graph, tokenizer = self._artifacts()
        return EncoderSpec(self.encoder_id, _digest(graph), _digest(tokenizer),
                           "cls-pooling/1" if self.candidate.kind == "onnx"
                           else "sentence-transformers-pooling/1",
                           self.dim, "l2-unit-except-zero/1", self.candidate.doc_prefix,
                           self.candidate.query_prefix, "max-absolute-component-drift/1", 1e-4)

    def _artifacts(self) -> tuple[Path, Path]:
        base = self.model_dir
        if self.candidate.kind == "onnx":
            fp16 = FP16_GRAPHS / f"{self.candidate.model_dir}-fp16" / "model_fp16.onnx"
            graph = (fp16 if (self.device == "cuda" and fp16.is_file())
                     else base / "model_optimized.onnx")
            return graph, base / "tokenizer.json"
        weights = sorted(base.glob("*.safetensors")) or sorted(base.glob("*.bin"))
        if not weights:
            raise EncoderUnavailable("no weight file in the model directory",
                                     encoder_id=self.encoder_id, path=str(base))
        return weights[0], base / "tokenizer.json"

    def _load(self) -> None:
        if self._session is not None or self._model is not None:
            return
        started = time.perf_counter()
        if self.candidate.kind == "onnx":
            import onnxruntime as ort
            from tokenizers import Tokenizer
            graph, tokenizer_path = self._artifacts()
            self._tokenizer = Tokenizer.from_file(str(tokenizer_path))
            self._tokenizer.enable_truncation(self.max_tokens)
            self._tokenizer.enable_padding()
            providers = (["CUDAExecutionProvider", "CPUExecutionProvider"]
                         if self.device == "cuda" else ["CPUExecutionProvider"])
            self._session = ort.InferenceSession(str(graph), providers=providers)
            self._inputs = [item.name for item in self._session.get_inputs()]
        else:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(str(self.model_dir), device=self.device,
                                              trust_remote_code=False)
            self._model.max_seq_length = self.max_tokens
            if self.device == "cuda":
                self._model.half()
            self._tokenizer = self._model.tokenizer
        self.counters["load_seconds"] = float(self.counters["load_seconds"]) + (
            time.perf_counter() - started)

    def close(self) -> None:
        """Release the device. D.8: the encoder must be EVICTABLE from a 3.7 GiB card."""
        self._session = None
        self._model = None
        self._tokenizer = None
        import gc
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:                                  # pragma: no cover - device only
            pass

    # ------------------------------------------------------------------ measuring
    def token_lengths(self, texts: Sequence[str]) -> np.ndarray:
        """Untruncated token counts, from the encoder's OWN tokenizer (D.6(3)). O(total bytes).

        This is what makes the window honest: the recipe records tokens_emitted and
        tokens_dropped per span against these counts rather than guessing from bytes.
        """
        self._load()
        if not len(texts):
            return np.zeros(0, dtype=np.int64)
        if self.candidate.kind == "onnx":
            from tokenizers import Tokenizer
            _graph, tokenizer_path = self._artifacts()
            plain = Tokenizer.from_file(str(tokenizer_path))
            plain.no_truncation()
            plain.no_padding()
            encoded = plain.encode_batch(list(texts))
            return np.fromiter((len(item.ids) for item in encoded),  # loop-ok: one len() per text
                               dtype=np.int64, count=len(encoded))
        encoded = self._tokenizer(list(texts), add_special_tokens=True)["input_ids"]
        return np.fromiter((len(ids) for ids in encoded),  # loop-ok: one len() per text
                           dtype=np.int64, count=len(encoded))

    # ------------------------------------------------------------------ embedding
    def embed(self, texts: Sequence[str], *, role: str = "doc") -> np.ndarray:
        """Unit float32 rows, one per text, in input order. LIFTED from common.py:60-89.

        Length-sorted batching (neighbours in a batch have similar token counts, so padding waste
        is small) and, for the ONNX graph, token-budgeted batch sizes - both measured there on
        2026-09-16 as the two levers after fp16. The original order is restored before returning.
        """
        if not len(texts):
            return np.zeros((0, self.dim), dtype=np.float32)
        self._load()
        prefix = self.candidate.doc_prefix if role == "doc" else self.candidate.query_prefix
        prepared = [prefix + (text or "") for text in texts]  # loop-ok: one string join per text
        lengths = np.fromiter((len(text) for text in prepared),  # loop-ok: one len() per text
                              dtype=np.int64, count=len(prepared))
        order = np.argsort(lengths, kind="stable")
        order_list = order.tolist()
        ordered = [prepared[index] for index in order_list]  # loop-ok: one host gather per text
        started = time.perf_counter()
        blocks = (self._embed_onnx(ordered) if self.candidate.kind == "onnx"
                  else self._embed_st(ordered))
        self.counters["encode_seconds"] = float(self.counters["encode_seconds"]) + (
            time.perf_counter() - started)
        self.counters["texts_encoded"] = int(self.counters["texts_encoded"]) + len(prepared)
        matrix = np.concatenate(blocks, axis=0).astype(np.float32)
        inverse = np.empty_like(order)
        inverse[order] = np.arange(order.size, dtype=np.int64)
        matrix = matrix[inverse]
        return matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-12)

    def _embed_onnx(self, ordered: list[str]) -> list[np.ndarray]:
        out: list[np.ndarray] = []
        position = 0
        while position < len(ordered):             # loop-ok: one step per BATCH, never per text
            window = ordered[position:position + ONNX_MAX_BATCH]
            longest = max(len(text) for text in window)  # loop-ok: one len() per text of a batch
            estimate = max(16, min(self.max_tokens, longest // 4))
            size = int(max(8, min(ONNX_MAX_BATCH, ONNX_TOKEN_BUDGET // estimate)))
            encoded = self._tokenizer.encode_batch(ordered[position:position + size])
            position += size
            ids = np.array([item.ids for item in encoded],  # loop-ok: one row per text of a batch
                           dtype=np.int64)
            mask = np.array([item.attention_mask for item in encoded],  # loop-ok: as above
                            dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self._inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            hidden = self._session.run(None, feed)[0]
            out.append((hidden[:, 0, :] if hidden.ndim == 3 else hidden).astype(np.float32))
            self.counters["batches"] = int(self.counters["batches"]) + 1
            self.counters["tokens_encoded"] = int(self.counters["tokens_encoded"]) \
                + int(mask.sum())
        return out

    def _embed_st(self, ordered: list[str]) -> list[np.ndarray]:
        batch = 8 if self.dim > 512 else 32
        out: list[np.ndarray] = []
        for position in range(0, len(ordered), batch):    # loop-ok: one step per BATCH
            vectors = self._model.encode(ordered[position:position + batch], batch_size=batch,
                                         convert_to_numpy=True, normalize_embeddings=False,
                                         show_progress_bar=False)
            out.append(np.asarray(vectors, dtype=np.float32))
            self.counters["batches"] = int(self.counters["batches"]) + 1
        return out

    # ------------------------------------------------------------------ D.11's cache
    def embed_cached(self, keys: Sequence[str], texts: Sequence[str],
                     *, role: str = "doc") -> np.ndarray:
        """D.11: one vector per SPAN, cached by that span's own content address.

        ``keys`` are the spans' content addresses (the recipe output's digest, which is what D.11
        names). A repeat span costs a lookup; a new one is the only thing encoded. The distinct
        keys and one representative text each come out of ONE ``np.unique``, and the misses are
        embedded in ONE call - so the cache never turns a batched encode into a per-row one.
        Complexity: O(k log k) host, O(misses) device.
        """
        if not len(keys):
            return np.zeros((0, self.dim), dtype=np.float32)
        addresses = np.asarray(keys, dtype=object)
        unique, first, inverse = np.unique(addresses, return_index=True, return_inverse=True)
        inverse = inverse.reshape(-1)
        distinct = unique.tolist()
        held = np.fromiter((key in self._cache for key in distinct),  # loop-ok: one dict lookup
                           dtype=bool, count=len(distinct))           # per DISTINCT span
        self.counters["cache_hits"] = int(self.counters["cache_hits"]) + int(held.sum())
        missing = np.flatnonzero(~held).tolist()
        if missing:
            representative = first[missing].tolist()
            fresh = self.embed([texts[index] for index in representative],  # loop-ok: one host
                               role=role)                                   # gather per MISS
            for row, index in enumerate(missing):     # loop-ok: one dict store per MISSED span;
                self._cache[distinct[index]] = fresh[row]      # no array work in the body
        table = np.stack([self._cache[key] for key in distinct],  # loop-ok: one row view per
                         axis=0)                                  # DISTINCT span
        return table[inverse]


def span_encoder(encoder_id: str, *, device: str = "cuda") -> SpanEncoder:
    """The declared encoder of that id. An unknown id is a named refusal, never a default."""
    for candidate in CANDIDATES:                   # loop-ok: the declared candidate roster
        if candidate.encoder_id == encoder_id:
            return SpanEncoder(candidate, device=device)
    raise EncoderUnavailable("no span encoder declared under that id", encoder_id=encoder_id,
                             declared=[c.encoder_id for c in CANDIDATES])


def survey() -> list[Mapping[str, Any]]:
    """The candidate survey as rows, each with its admitting or excluding clause. O(candidates)."""
    return [{"encoder_id": c.encoder_id, "dim": c.dim, "max_tokens": c.max_tokens,
             "matryoshka": c.matryoshka, "licence": c.licence, "available_on_disk": c.available,
             "admitted_by": c.admitted_by, "excluded_by": c.excluded_by}
            for c in CANDIDATES]  # loop-ok: the declared candidate roster


# Counter view only; session loading, model selection, cache and embedding are unchanged.

# The inert closed receipt contract; numeric execution remains owned here.
from ..receipt_diagnostics import encoder_counter_parts
