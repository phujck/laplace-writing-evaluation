"""embed_router.py - the embedding router: recall as mechanical geometry (mind sharding, slice 1).

The lexical ring (``keeper.recall``) routed by token overlap and failed the navigator's hello
check 1/5 while visiting 620/1389 nodes - reach without sharpness (E8, quantified). This module
replaces the descent CRITERION, not the descent: every node is embedded once at fold time
(label + essence + keywords, content-hashed so an unchanged node never re-embeds), and recall
descends the SAME graded tree choosing children by cosine - mechanical geometry, no model call
in the traversal. Each level's candidates are pooled and the top of the pool expands ("fire the
grades in parallel"); leaves accumulate into the hit pool; the return is salience-merged
(min-max over everything the pull touched, so salience stays "closeness to the pull's centre").

The embedding model is OPEN-WEIGHT and LOCAL (``couple-down-to-open-weights``): bge-small via
fastembed/ONNX - the first weights-first component at the conjugate boundary. The ONLY model
calls are embedding calls; they happen at fold time and once per query. When the model is
unavailable (no install, no cache, offline first run) ``route`` returns None and the caller
falls back to the lexical ring, MARKED - the view must show which router fired.

Seal: node texts are built from HANDLES (label/essence/keywords) - for soul nodes those are the
content-free handles the overlay already carries. The vector cache lives in
``.self_embeddings.json`` - TRACKED, not gitignored: since 2026-07-14 (W6.2 banked-what-travels)
the vector cache is stored as per-vector int8 (base64 + scale, ~8M under GitHub's 100MB blob wall)
and TRAVELS tracked, so a fresh pull arrives warm and the boot pre-warm never bulk-embeds cold (the
PSU crash class, RW-20260713-211452-731008; AUDIT_2026-07-13 claim row 8). The stored form is the
content-free text hash + quantized floats, never the text - the seal holds by construction.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import base64
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The refusal type must be nameable in get_backend's except clause without importing the
# optional embedding stack.
from laplace.representation.device_policy import DeviceRequired

CACHE_FILE = ".self_embeddings.json"
CACHE_FORMAT = "int8"                                # the on-disk vector encoding: per-vector int8 + float
                                                     # scale, base64-packed (W6.2 banked-what-travels). The raw
                                                     # float JSON was ~96M (against the 100MB blob wall); the int8
                                                     # pack is ~8M and TRAVELS tracked. Legacy {"v":[float,...]}
                                                     # entries still load (see _dequantize_entry), so an old float
                                                     # cache is adopted in place with no re-embed.
METRIC_FILE = ".metric_M.npz"                        # the trained bilinear metric (metric_distill writes it; travels per THE UNSEAL)
PROPOSALS_FILE = ".wire_proposals.jsonl"             # geometric-only finds banked for the dream's audit (TRACKED - it travels; probe/bench callers revert their dirt, WO-20260820-wire-proposals-bench-dirt)
MODEL_NAME = "BAAI/bge-small-en-v1.5"

# ---------------------------------------------------------------------------
# failure-shaped query expansion (the dream audit 2026-07-11, "the voice that
# didn't surface" - DREAM_AUDIT_2026-07-11_the-voice-that-didnt-surface.md).
# Measured defect: the router CAN reach a rebuildable-store fact - the neutral
# phrasing ("where do voice exemplars live") ranks it 1st - but the queries a
# FAILING agent actually issues ("voice store missing", "voice wash
# unavailable") rank it 16th-or-nowhere, because sibling EVIDENCE of past
# failures (other washes' own error records) shares the distress vocabulary
# with the query and outscores the substrate on those tokens. This is a
# structural ranking fragility, not a missing wire - one per-incident spine
# binding was already laid for this specific case; this is the general fix.
#
# Conservative and additive: a regex over common distress vocabulary. It
# fires ONLY on literal failure-shaped phrasing - it is not a sentiment
# model, it does not fire on words like "error-correcting" mid-token (word
# boundaries), and it never touches route()'s behaviour when it doesn't fire.
_FAILURE_SHAPE_RE = re.compile(
    r"\b(missing|unavailable|refused?|failed?|no\s+store|not\s+found|broken|error)\b",
    re.IGNORECASE,
)


def _failure_shaped_rephrase(goal: str) -> str | None:
    """Mechanical, not semantic: strip the distress tokens the regex matched, keep whatever
    content tokens survive, and wrap them in provisioning-shaped framing ("where does X live /
    how is X provisioned") - the phrasing that the audit found already ranks the substrate
    correctly. Returns None when the detector doesn't fire, or when nothing survives the strip
    (an all-distress query has no subject to rephrase, so there is nothing conservative to do)."""
    if not _FAILURE_SHAPE_RE.search(goal):
        return None
    stripped = _FAILURE_SHAPE_RE.sub(" ", goal)
    content = [t for t in re.findall(r"[A-Za-z0-9_]+", stripped) if t]
    if not content:
        return None
    subject = " ".join(content)
    return f"where does {subject} live / how is {subject} provisioned"


MODEL_CACHE = Path.home() / ".cache" / "fastembed"   # fastembed's own cache (HF/GCS layout), the fallback
_VENDOR_DIR = source_tree() / "models" / "fastembed"
_VENDOR_TARBALL = _VENDOR_DIR / "fast-bge-small-en-v1.5.tar.gz"
_VENDOR_EXTRACT = Path.home() / ".cache" / "laplace" / "fastembed"  # extracted-on-load (ephemeral ok)


def _vendored_model_path() -> Path | None:
    """The model VENDORED in the repo, so a fresh ephemeral container reconstructs with
    ZERO network under any egress policy (``couple-down-to-open-weights``; the seal needs
    no phone-home). The repo carries the COMPRESSED tarball (under the 100MB blob limit,
    no git-lfs); extract it once to a local cache and load via fastembed's
    ``specific_model_path``. ``LAPLACE_FASTEMBED_MODEL`` overrides. None when absent.
    """
    import os
    import tarfile

    env = os.environ.get("LAPLACE_FASTEMBED_MODEL")
    if env and (Path(env) / "model_optimized.onnx").exists():
        return Path(env)
    model_dir = _VENDOR_EXTRACT / "fast-bge-small-en-v1.5"
    if (model_dir / "model_optimized.onnx").exists():
        return model_dir
    if _VENDOR_TARBALL.exists():
        _VENDOR_EXTRACT.mkdir(parents=True, exist_ok=True)
        with tarfile.open(_VENDOR_TARBALL) as tf:
            tf.extractall(_VENDOR_EXTRACT)
        if (model_dir / "model_optimized.onnx").exists():
            return model_dir
    return None


TEXT_CAP = 480                                       # bge's 512-token window, with headroom
BEAM = 8                                             # internal nodes expanded per level (the pull width of the descent)
PER_BRANCH_WIDTH = 12                                # top-k PER SHARD per grade (the survey pull width - mind sharding's merge)
PATH_DECAY = 0.9                                     # the handle speaks for its members, attenuated one step at a time
PROPOSAL_FLOOR = 0.5                                 # a wire-proposal needs geometric CONFIDENCE (salience) + symbolic silence

_BACKEND: Any = None
_BACKEND_FAILED = False


# ---------------------------------------------------------------------------
# backends - the open-weight model, and a deterministic geometry for tests
# ---------------------------------------------------------------------------

def _device_row(organ: str, *, gpu: bool, why: str, dialed: bool) -> None:
    """Hand the embed session's landing to ``device_policy`` - the one recorder every organ
    shares. Import-local and best-effort on everything EXCEPT ``DeviceRequired``: a refusal
    under ``LAPLACE_REQUIRE_GPU`` is the point of the mechanism and must reach the caller."""
    try:
        from laplace.representation.device_policy import DeviceRequired, record_fallback
    except Exception:                                    # noqa: BLE001 - recorder absent, organ lives
        return
    try:
        record_fallback(organ, "gpu" if gpu else "cpu", why, dialed=dialed)
    except DeviceRequired:
        raise
    except Exception:                                    # noqa: BLE001 - logging never kills the organ
        pass


class FastEmbedBackend:
    """bge-small-en-v1.5 over ONNX. Queries take the bge retrieval prefix (``query_embed``);
    documents embed plain. Vectors are unit-normalized at the boundary so dot = cosine.

    ``LAPLACE_EMBED_THREADS`` caps the ONNX intra-op threads: an uncapped batch embed loads
    every core at once, and on the author's local box that power spike hard-crashes the PSU
    (two Kernel-Power 41 losses, 2026-07-13). The offline launcher sets it for the local
    scanner; unset means onnxruntime's default (all cores) - the remote box's posture."""

    def __init__(self) -> None:
        import os

        from fastembed import TextEmbedding
        kw: dict[str, Any] = {}
        raw = (os.environ.get("LAPLACE_EMBED_THREADS") or "").strip()
        if raw.isdigit() and int(raw) > 0:
            kw["threads"] = int(raw)
        # GPU BY CAPABILITY, NEVER BY KNOB (2026-08-19, the laptop pilot; fills the
        # ATLAS_MATHEMATICS §8.3 gap "no GPU embedding path for the engine's own fold").
        # If onnxruntime reports a usable CUDA provider, ask for it with the CPU
        # provider as in-list fallback; fastembed itself falls back to CPU with a
        # RuntimeWarning when the CUDA libs fail to load (observed live: missing
        # libcublasLt -> CPU, embeds fine). LAPLACE_EMBED_NO_GPU=1 opts out entirely
        # (the same class of honest env override as LAPLACE_EMBED_THREADS above).
        # GPU offload also retires the PSU concern that motivated the thread cap:
        # the crash class was an all-core CPU power spike, not a GPU load.
        #
        # THE RATE, MEASURED ON THIS BOX 2026-08-21 (RTX A2000 Laptop 4GB, ort 1.29.0,
        # 1024 texts of 480 chars - the router's own TEXT_CAP - drawn from repo prose,
        # identical batch across arms; evidence/EMBED_GPU_2026-08-21/):
        #     CPU threads=1   10.8 texts/s   (the offline launcher's posture)
        #     CPU threads=8   32.5 texts/s   (the suite's proven-safe posture)
        #     GPU (CUDA EP)  484.3 texts/s   -> 14.9x over CPU@8, 44.8x over CPU@1
        # These SUPERSEDE the "274/s CPU vs 3372/s GPU (12.3x)" pair this comment carried
        # from the 2026-08-19 pilot: that pair recorded neither its text length nor its
        # thread posture, so its absolute rates were never comparable to anything and were
        # quoted onward as if they were (WO-20260820-embed-rate-record-discrepancy). The
        # RATIO is the portable number; the absolutes belong to their stated batch.
        # Batch size is saturated at this text length (32: 492/s, 64: 482/s, 128: 450/s),
        # so the 64 cap below costs nothing and the OOM headroom it buys is free.
        #
        # THE DIAL IS A PROVIDER LIST, NOT AN ABSENCE (2026-08-21). Leaving `providers`
        # unset does NOT mean CPU: fastembed builds its own list and attempts CUDA
        # anyway (measured tonight - LAPLACE_EMBED_NO_GPU=1 still emitted fastembed's
        # "Attempt to set CUDAExecutionProvider failed" warning, and landed on CPU only
        # because the libs happened to be off the loader path). The dial must therefore
        # NAME CPUExecutionProvider, or it is honoured by luck.
        self._why = ""                                  # why this landing, for the device row
        no_gpu = bool((os.environ.get("LAPLACE_EMBED_NO_GPU") or "").strip())
        if no_gpu:
            kw["providers"] = ["CPUExecutionProvider"]
            self._why = "LAPLACE_EMBED_NO_GPU is set"
        else:
            try:
                import onnxruntime as _ort

                # pip-shipped NVIDIA libs live at site-packages/nvidia/*/lib, OFF the
                # loader path, and glibc reads LD_LIBRARY_PATH once at process start -
                # so the bridge must be a dlopen-by-absolute-path, before the EP asks
                # for anything by soname. TWO bridges, both measured on this box
                # 2026-08-21 and each sufficient ALONE: cuda_libs.preload() (the repo's
                # own, the one cupy already rides, and the only one that finds this
                # box's mixed nvidia/cu13/lib layout) and ORT's preload_dlls(). Without
                # either, the CUDA EP dies on libcublasLt.so.13 and fastembed falls back
                # to CPU with a warning nobody reads - the exact silent-regression shape
                # device_policy now records.
                from laplace.representation import cuda_libs
                cuda_libs.preload()                      # idempotent, silent on a CPU box
                if hasattr(_ort, "preload_dlls"):
                    try:
                        _ort.preload_dlls()
                    except Exception:
                        pass
                avail = _ort.get_available_providers()
                if "CUDAExecutionProvider" in avail:
                    kw["providers"] = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                else:
                    self._why = (f"onnxruntime reports no CUDAExecutionProvider "
                                 f"(available: {avail}) - check that onnxruntime-gpu, not "
                                 f"plain onnxruntime, is what supplied capi/")
            except Exception as exc:                     # noqa: BLE001
                self._why = f"onnxruntime introspection failed ({exc.__class__.__name__}: {exc})"
        vendored = _vendored_model_path()
        if vendored is not None:
            self._model = TextEmbedding(MODEL_NAME, specific_model_path=str(vendored), **kw)
        else:
            MODEL_CACHE.mkdir(parents=True, exist_ok=True)
            self._model = TextEmbedding(MODEL_NAME, cache_dir=str(MODEL_CACHE), **kw)
        # The name is IDENTITY: it rides every embedding's content hash (§1.5 of
        # ATLAS_MATHEMATICS / _hash below), so it must not vary with the execution
        # provider - CUDA and CPU produce the same geometry from the same model.
        # The provider fact lives on .gpu (telemetry/timing rows), never the name.
        self.gpu = False
        self.providers: list[str] = []
        if kw.get("providers"):
            try:
                sess = self._model.model.model  # fastembed -> OnnxTextModel -> ort.InferenceSession
                self.providers = list(sess.get_providers())
                self.gpu = any("CUDA" in p for p in self.providers)
            except Exception:
                self.gpu = False
        # NO ORGAN DEGRADES QUIETLY (his ruling 2026-08-21). The embed session's landing
        # is a DECISION with a typed row, never a default with silence: a GPU landing is
        # the ruled home and records nothing; a CPU landing prints loudly and appends to
        # .fallback_events.jsonl, marked `dialed` when LAPLACE_EMBED_NO_GPU asked for it
        # and refused outright under LAPLACE_REQUIRE_GPU when it did not. This is the
        # organ the 2026-08-19 comment above describes falling back "silently" - it no
        # longer can.
        if not self.gpu and not self._why:
            self._why = ("the CUDA provider was requested but the session bound "
                         f"{self.providers or ['CPUExecutionProvider']} - the EP failed to "
                         "load (fastembed warns and continues; see the preload note above)")
        _device_row("embed_router", gpu=self.gpu, why=self._why, dialed=no_gpu)
        self.name = f"fastembed:{MODEL_NAME}"

    @staticmethod
    def _unit(v: Any) -> list[float]:
        import numpy as np
        a = np.asarray(v, dtype="float32")
        n = float(np.linalg.norm(a))
        return (a / n).tolist() if n else a.tolist()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        fn = getattr(self._model, "passage_embed", self._model.embed)
        # GPU batch cap (2026-08-19, the pilot fold): fastembed's default internal
        # batch (256) built a 1.24 GB attention buffer mid-bulk-fold and OOM'd the
        # 4 GB A2000 (BFCArena allocate fail, Attention_0). The September Writing
        # close also exhausted available memory at 64 while the desktop was live;
        # the complete retry succeeded at 16. Keep that measured conservative
        # default; LAPLACE_EMBED_BATCH overrides for larger available budgets.
        # CPU keeps fastembed's own default.
        if getattr(self, "gpu", False):
            import os
            raw = (os.environ.get("LAPLACE_EMBED_BATCH") or "").strip()
            bs = int(raw) if raw.isdigit() and int(raw) > 0 else 16
            return [self._unit(v) for v in fn(texts, batch_size=bs)]
        return [self._unit(v) for v in fn(texts)]

    def query(self, text: str) -> list[float]:
        fn = getattr(self._model, "query_embed", None)
        vec = next(iter(fn([text]))) if fn else next(iter(self._model.embed([text])))
        return self._unit(vec)

    def close(self) -> None:
        """Release the owned ONNX session before another GPU organ takes custody.

        FastEmbed exposes no public close operation. Its CUDA allocation lifetime
        follows the nested model/session object's lifetime, so dropping the sole
        wrapper reference and collecting it is the supported local teardown seam.
        """
        import gc
        model=getattr(self,"_model",None)
        self._model=None
        del model
        gc.collect()


class HashBackend:
    """Deterministic char-3gram hashing into a small unit sphere - NO semantics, NEVER a routing
    fallback (worse than lexical). Exists so tests exercise cache + descent mechanics offline."""

    name = "hash:3gram-256"
    dim = 256

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        t = text.lower()
        for i in range(max(0, len(t) - 2)):
            h = int.from_bytes(hashlib.sha1(t[i:i + 3].encode()).digest()[:4], "big")
            v[h % self.dim] += 1.0
        n = sum(x * x for x in v) ** 0.5
        return [x / n for x in v] if n else v

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def query(self, text: str) -> list[float]:
        return self._vec(text)


def get_backend() -> Any:
    """The process-wide model, loaded once; None when unavailable (the caller's signal to fall
    back to the lexical ring, marked). A failure is remembered - no retry storm per query."""
    global _BACKEND, _BACKEND_FAILED
    if _BACKEND is not None:
        return _BACKEND
    if _BACKEND_FAILED:
        return None
    try:
        _BACKEND = FastEmbedBackend()
        return _BACKEND
    except DeviceRequired:                             # a named refusal is not a missing model
        raise                                          # (LAPLACE_REQUIRE_GPU; never swallowed
                                                       #  into the lexical-fallback signal)
    except Exception:                                  # noqa: BLE001 - no model is a supported state
        _BACKEND_FAILED = True
        return None


def release_backend(backend:Any|None=None) -> dict[str,Any]:
    """Release one process-owned embed backend without changing fallback policy."""
    import gc
    global _BACKEND
    target=backend if backend is not None else _BACKEND
    if target is None:return {"released":False,"reason":"no loaded backend"}
    providers=list(getattr(target,"providers",[]) or [])
    gpu=bool(getattr(target,"gpu",False))
    if target is _BACKEND:_BACKEND=None
    close=getattr(target,"close",None)
    if callable(close):close()
    del target
    gc.collect()
    return {"released":True,"gpu":gpu,"providers":providers}


def predicted_backend_name() -> str:
    """The name ``get_backend()`` will report IF it constructs successfully - without paying for
    that construction (HOT-2, 2026-08-20 self-audit). ``FastEmbedBackend.name`` is set at
    ``f"fastembed:{MODEL_NAME}"`` (see its ``__init__``, near the top of this file) - a static
    format over a compile-time constant, deliberately never varying with the execution provider
    (GPU/CPU) or any other runtime state, because the name is IDENTITY: it rides every cached
    embedding's content hash, and CUDA vs CPU must hash the same. ``get_backend()`` itself only
    ever returns a ``FastEmbedBackend`` or ``None`` (a failed/unavailable model) - there is no
    third outcome with a different name - so this prediction is EXACT whenever a real backend
    would succeed, never a guess. A caller that hashes against this name and finds nothing stale
    can skip constructing the model entirely; one that finds something stale still calls
    ``get_backend()`` for the real embed, and should treat ``None`` (construction failed) as the
    fallback signal it always was."""
    return f"fastembed:{MODEL_NAME}"


# ---------------------------------------------------------------------------
# the node text - the handle, never the content (the seal holds by construction)
# ---------------------------------------------------------------------------

# How many of a concept ancestor's LABEL terms its chain rung carries. 0 = the rung is dropped
# entirely, which is what ships; see _ancestor_label for the three arms this was measured over.
CHAIN_LABEL_TERMS = 0


def _ancestor_label(nodes: dict[str, Any], nid: str) -> str:
    """One ancestor's contribution to the parent chain. A concept cluster contributes the head of its
    LABEL - nothing at all at the shipped ``CHAIN_LABEL_TERMS = 0``. Every other ancestor contributes
    its id tail, unchanged: that tail is already a word and already stable.

    WHY THE CLUSTER ID LEFT THIS TEXT. A cluster's id is a sha1 over its member leaf ids
    (``meaning_upfold._cluster_id``), so naming it here drew a leaf's staleness at the REBUILD
    boundary rather than at the delta: one emptied cluster forced a re-partition, the re-partition
    re-minted the ids its subtrees name here, and 12,642 leaf embeddings went stale of which 99.1%
    had unchanged content (``evidence/DEPOSIT_VOLUME_AUDIT_2026-08-21/embed_volume.json``). Replayed
    on the live network: re-minting all 2,332 concept ids with labels and shape held fixed re-stales
    15,485 of 18,717 file leaves under the old rule and 0 under this one.

    WHY THE LABEL DID NOT SIMPLY REPLACE IT. ``WO-20260821-embed-rebuild-boundary`` proposed carrying
    the ancestor's label, which reads as a free upgrade - a concept word where hex sat. Measured
    against its own named regression bars over one migration re-embed each (2026-08-21): the whole
    six-term label moved the skills-fibre residual R 0.4466 -> 0.5982 (rank-1 91/187 -> 67/187) and
    the two-term head 0.4514 -> 0.5305, while dropping the rung read 0.4465 against a matched 0.4514
    baseline. The chain is a signal SHARED by everything under an ancestor, and the residue's cluster
    labels are largely path words, so a label rung pulls a block's members together against their own
    queries instead of apart - the same degeneracy ``evidence/ROUTE_MASS_TERM_2026-08-21`` measured
    for skill leaves, fed from a second direction. The 25-paper bench held 25/25 on all three arms.
    The constant is the dial: raise it if a later cure gives cluster labels task vocabulary of their
    own (``WO-20260821-skill-essence-is-its-own-name`` is that cure for the skills block), and
    re-read the bars, because the arms above are the record of what it cost when they had none."""
    node = nodes.get(nid) or {}
    if node.get("kind") == "concept":
        essence = (node.get("essence") or "").split()
        if essence:
            return " ".join(essence[:CHAIN_LABEL_TERMS])   # "" at 0 - the rung is dropped
    return nid.rstrip("/").split("/")[-1] or "(root)"


# --- the essence join: a served digest's claim rides the text the fold EMBEDS ----------------
#
# RUL-20260823-essence-side-ratified. `digest_lens` wires a served digest's OBJECT REFERENTS into
# `reach`, which the coupling reads - but `route()` scores COSINE over the node vectors built here,
# and reach never enters that dot. P24 measured the gap and named it: wired-is-not-routed. The cure
# is to join the claim to the one text whose embedding route actually scores, so wired-is-routed
# holds BY CONSTRUCTION rather than by a second wire that has to be kept in step.
#
# WHY HERE AND NOT IN THE FOLD'S OWN STORES. `digest_lens`' standing law: a digest never enters a
# leaf store. Write the claim into `.self_graded.json` (keeper.build_self) or into the clustering
# text (meaning_upfold._embeddable_text) and the next fold RECLUSTERS the engine's own summaries as
# content. This composition is the third place - transient, embedded, never stored - and it is
# exactly where the sealed soul-entity text already rides for the same reason: the text transits
# this process only and lands as a gitignored vector.
DIGEST_MARKER = " [digest] "     # condition (i): provenance VISIBLE in the embedded surface, so a
                                 # served claim never masquerades as the node's own prose. Verified
                                 # absent from the corpus before it was minted (2026-08-23).
DIGEST_ESSENCE_ENV = "LAPLACE_DIGEST_ESSENCE"   # condition (iv)'s lever: the null arm's switch


def digest_essence_on() -> bool:
    """Is the essence join armed? DEFAULT OFF UNTIL P25'S VERDICT BANKS - the judge's confound
    guard (a): no cure becomes the incumbent mid-experiment. The builder's first form defaulted
    ON and the live serving basis re-embedded 35 joined texts before any arm ran, contaminating
    a P26 control (discarded, named in the P26 packet). The single string ``"1"`` ARMS the join
    (the essence arm's lever); anything else - unset included - serves the incumbent. Read at
    CALL time so an arm can be flipped inside one process. Off, ``node_text`` returns the
    pre-change composition BYTE-IDENTICALLY: no marker, no block, no store read, and the content
    hashes - hence the whole vector cache - are unmoved. The default flips to ON as the landing's
    own act, only after both P25 arms score and the judge's verdict banks."""
    import os
    return (os.environ.get(DIGEST_ESSENCE_ENV) or "").strip() == "1"


def digest_store_stamp(repo_root: Path | str) -> tuple[int, int]:
    """``.digests.jsonl``'s ``(mtime_ns, size)``, or ``(-1, -1)`` when there is no store. The join
    makes that file a ``node_text`` INPUT ON DISK - the second one, alongside the folded soul shard
    - so ``_basis_key`` has to stat it or a fresh mint would serve through a memo built before it."""
    try:
        from laplace.engine import digest_mint
        st = (Path(repo_root) / digest_mint.DIGEST_STORE).stat()
        return (st.st_mtime_ns, st.st_size)
    except (OSError, ImportError):
        return (-1, -1)


_DIGEST_MEMO: dict[str, Any] = {}


def digest_essences(repo_root: Path | str, net: dict[str, Any]) -> dict[str, str]:
    """``node id -> the digest block its served row contributes`` - the map ``node_text`` joins.

    ONE DERIVATION, the read-side law unchanged. The block is ``digest_mint.digest_text(row)``, the
    same single line the meter's retrieval arm queries with and ``digest_lens`` mints referents from
    - so the thing measured, the thing wired and the thing embedded are one string, not three that
    drift. Membership is judged by ``digest_lens.serve`` and the contract by its ``conformance``:
    only SERVING (``exact`` / ``inherited-with-drift``) AND conforming rows join. A stale row, a
    synthetic ``composed`` row with no pointers, a row with an empty claim - none of them reach the
    embedded surface, for exactly the reasons that gate the wire.

    THE CAPS ARE THE ROW'S OWN (condition ii, G5). No second cut is taken here: the claim was cut at
    ``digest_mint.MAX_SENT`` and the objects at ``N_OBJECTS`` when the row was minted, and those
    walls are stamped on the row's ``caps``. So the block is bounded by construction (<= ~MAX_SENT +
    the banked token list; 705 chars is the live store's longest), and ``TEXT_CAP + len(marker) +
    that`` sits near 1200 characters - roughly 300 tokens, inside bge's 512-token window with room.
    The base half is NOT re-cut to make space: it stays byte-for-byte the string it is today, so the
    join only ever ADDS, which is the same additivity discipline ``digest_lens``' guard holds to.

    Empty when the switch is off, when there is no store, and when nothing serves.

    THE MEMO is the single-slot shape :func:`basis` already uses, and for the same reason - the
    derivation walks every served node's leaf descendants (~100 ms on the live network) and a
    per-node caller would pay it per node. It is keyed on the store stat, the switch, the node
    count AND the ``net`` OBJECT, so two networks can never share a slot. The vector-producing path
    (:func:`ensure_embeddings`) derives FRESH and passes the map down explicitly, so no vector is
    ever hashed against a memoised map."""
    if not digest_essence_on():
        return {}
    key = (str(repo_root), digest_store_stamp(repo_root), len(net.get("nodes") or {}))
    slot = _DIGEST_MEMO.get("slot")
    if slot is not None and slot["net"] is net and slot["key"] == key:
        return slot["map"]
    from laplace.engine import digest_lens, digest_mint
    rows = digest_mint.load_rows(repo_root)
    out: dict[str, str] = {}
    if rows:
        nodes = net.get("nodes") or {}
        for nid, verdict in digest_lens.serve(nodes, rows).items():
            if verdict["status"] not in digest_lens.SERVING:
                continue
            block = digest_mint.digest_text(verdict["row"]).strip()
            if block:
                out[nid] = block
    _DIGEST_MEMO["slot"] = {"key": key, "net": net, "map": out}
    return out


def node_text(repo_root: Path | str, net: dict[str, Any], nid: str,
              digests: dict[str, str] | None = None) -> str:
    """What a node IS, as one bounded line: label, where it sits, its lenses, its essence, its
    keywords. Internal nodes add a coverage sample (what is findable below - the descent signal,
    now embedded). Soul nodes contribute only their overlay handles - content-free - EXCEPT the
    sealed entity ITEMS, whose disk text is read here at fold time so a specific query about a
    person can reach the right item by MEANING: the text transits this process only, lands as a
    gitignored vector (hash + floats, never the text), and every handle that can travel stays
    content-free. The seal is the commit/return boundary (his posture), and this is inside it.

    THE ESSENCE JOIN rides the tail: a node whose banked digest SERVES and CONFORMS gets
    ``DIGEST_MARKER`` and its claim+objects appended, so ``route``'s cosine has claim-grade content
    to meet (see :func:`digest_essences`). ``digests`` is that map, precomputed by the caller - pass
    it from any loop, because deriving it costs a walk of every served node's descendants. Omitted,
    it is derived (memoised) here. With ``LAPLACE_DIGEST_ESSENCE=0`` this function returns the
    pre-join string byte-for-byte."""
    base = _node_base_text(repo_root, net, nid)
    if not digest_essence_on():
        return base                                   # the null arm: byte-identical, no store read
    if digests is None:
        digests = digest_essences(repo_root, net)
    block = digests.get(nid)
    return f"{base}{DIGEST_MARKER}{block}" if block else base


def _node_base_text(repo_root: Path | str, net: dict[str, Any], nid: str) -> str:
    """The pre-join composition, unchanged and unsplittable from its cap - lifted out of
    :func:`node_text` so the join has ONE base to extend and the null arm has one string to be
    identical to. Every behavioural comment on this text lives on ``node_text``'s docstring."""
    if nid.startswith("soul://entities/"):
        rest = [s for s in nid[len("soul://entities/"):].split("/") if s]
        if len(rest) >= 3 and rest[2].isdigit():
            from laplace.engine import soul_provenance
            txt = soul_provenance.item_text(Path(repo_root), rest[0], rest[1], int(rest[2]))
            if txt:
                return txt[:TEXT_CAP]
    nodes = net["nodes"]
    node = nodes.get(nid, {})
    label = nid.replace("mind://", "mind/").rstrip("/").split("/")[-1] or "(root)"
    chain: list[str] = []
    cur = node.get("parent")
    for _ in range(3):                        # three rungs of WALK; an empty rung is dropped, not skipped-over
        if not cur:
            break
        rung = _ancestor_label(nodes, cur)
        if rung:
            chain.append(rung)
        cur = nodes.get(cur, {}).get("parent")
    ess = node.get("essence") or ""
    if not ess:
        from laplace.engine import conceptric
        ess = conceptric.essence(repo_root, net, nid)
    kws = " ".join((node.get("keywords") or [])[:16])
    lens = " ".join(net.get("lenses", {}).get(nid, []))
    parts = [label, " > ".join(reversed(chain)), lens, ess, kws]
    if not node.get("leaf", True):
        parts.append(" ".join((node.get("coverage") or [])[:40]))
    return " | ".join(p for p in parts if p)[:TEXT_CAP]


# ---------------------------------------------------------------------------
# embed at fold time - content-hashed, incremental, gitignored
# ---------------------------------------------------------------------------

def _hash(backend_name: str, text: str) -> str:
    return hashlib.sha1(f"{backend_name}\x00{text}".encode("utf-8", "replace")).hexdigest()


def _quantize_vec(vec: list[float]) -> dict[str, Any]:
    """A vector -> ``{"q": base64(int8 bytes), "s": scale}`` (W6.2). The per-vector scale is
    peak/127 so the full int8 range is used per row (the components of a 384-d unit vector are
    small, ~1/sqrt(dim); a fixed global scale would waste most of the range). Dequant is
    ``q*scale``; the round-trip cosine error is <1e-3 on bge-small rows - tolerable for the
    routing dot. The content hash ``"h"`` is over the TEXT, never the vector, so quantization
    never perturbs staleness detection."""
    import numpy as np
    a = np.asarray(vec, dtype="float32")
    peak = float(np.max(np.abs(a))) if a.size else 0.0
    scale = peak / 127.0 if peak > 0.0 else 1.0
    q = np.clip(np.round(a / scale), -127, 127).astype("int8")
    return {"q": base64.b64encode(q.tobytes()).decode("ascii"), "s": scale}


def _dequantize_entry(ent: dict[str, Any]) -> list[float]:
    """A stored cache entry -> a float vector. Self-describing so both loaders adopt whichever
    form the committed cache carries: a legacy ``{"v": [...]}`` entry returns its floats
    unchanged (an old float cache still loads); a quantized ``{"q","s"}`` entry is base64-decoded
    to int8 and scaled back."""
    v = ent.get("v")
    if v is not None:
        return v
    import numpy as np
    raw = base64.b64decode(ent["q"])
    return (np.frombuffer(raw, dtype="int8").astype("float32") * float(ent["s"])).tolist()


def _env_budget() -> int:
    """Ordinary reads never warm the persistent basis unless explicitly requested.

    Positive LAPLACE_EMBED_BUDGET opts into a bounded producer drip. Full deposits use
    bulk=True and ignore this budget. Missing or malformed settings are read-only.
    """
    import os
    try:
        return max(int(os.environ.get("LAPLACE_EMBED_BUDGET", "0")), 0)
    except ValueError:
        return 0



# --- the loud lines: any embed on the LOCAL serving path is visible (WALK_2026-07-15 F1) -------

_OFF_ANNOUNCED = False


def _log_drip_off() -> None:
    """Announce the OFF posture ONCE per process. The first serving-path call under budget=0 IS
    startup (the scanner pre-warm fires ensure_embeddings before the first request), so this reads
    as a startup line. The stale nodes serve as-is; the staleness is named in the UI's degraded
    chip (`vectors stale - semantic rank off`), never swallowed here."""
    global _OFF_ANNOUNCED
    if _OFF_ANNOUNCED:
        return
    _OFF_ANNOUNCED = True
    print("embed_router: embed drip OFF (budget=0) - vectors serve as-is; "
          "staleness named in the UI", flush=True)


def _log_drip_batch(n_embedded: int, budget: int | None, elapsed: float) -> None:
    """the loud line for a serving-path drip that DID embed (budget>0 or unlimited): one line per
    batch so an embed on the local box is never silent again (WALK_2026-07-15 F1 -- the 128-node
    drip starved the box for a minute and nothing said so). Carries the exact numbers the F1 probe
    asked for (`a scanner-side timing line on the drip`): timestamp, node count, budget, the ONNX
    thread cap, and the wall elapsed. ASCII dashes only (cross-platform console safety)."""
    import os
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    threads = (os.environ.get("LAPLACE_EMBED_THREADS") or "").strip() or "unset"
    shown = "unlimited" if budget is None else budget
    print(f"embed_router: DRIP {ts} embedded={n_embedded} budget={shown} threads={threads} "
          f"elapsed={elapsed:.3f}s (serving-path embed - loud by law, WALK F1)", flush=True)


def _drip_order(net: dict[str, Any], stale: list[str]) -> list[str]:
    """THE NAMED ORDERER (WO-20260820-graded-serving-drip): the drip budget spends apex-first,
    lens-first - BFS depth from the root, so the nodes a descent touches earliest earn their
    vectors first (the root, then its members - the mind's lenses - then each deeper ring).
    The flat lexicographic prefix this replaces spent the budget by node-id sort order, which
    let a cold cache starve the apex while alphabetically-early leaves warmed. Ties inside a
    ring break by node id and unreachable nodes sort last (still by id), so the order stays
    fully deterministic - successive budgeted calls still drip the cache toward fresh with no
    node embedded twice. Renaming this symbol requires amending the row's probe with it
    (AMEND-20260823-evidence-WO-20260820-graded-serving-drip declares the converse hazard)."""
    nodes = net.get("nodes", {})
    depth: dict[str, int] = {}
    root = net.get("root", "")
    if root in nodes:
        frontier, d = [root], 0
        while frontier:
            nxt: list[str] = []
            for nid in frontier:
                if nid in depth:
                    continue
                depth[nid] = d
                nxt.extend(m for m in (nodes[nid].get("members") or [])
                           if m in nodes and m not in depth)
            frontier, d = nxt, d + 1
    far = len(nodes) + 1                       # unreachable-from-root sorts after every ring
    return sorted(stale, key=lambda n: (depth.get(n, far), n))


def ensure_embeddings(repo_root: Path | str, net: dict[str, Any],
                      backend: Any, *, bulk: bool = False) -> dict[str, Any]:
    """The fold-time embed: every network node gets a vector, keyed by content hash - unchanged
    nodes are never re-embedded, vanished nodes are pruned. Returns {vectors: {nid: vec},
    n_embedded, n_cached, n_deferred, n_total} - the build report is part of the mechanism,
    not a log line.

    ``bulk=False`` (every SERVING caller: the scanner pre-warm, ``route``) honors the
    ``LAPLACE_EMBED_BUDGET`` guard: at most budget-many stale nodes are embedded per call
    (apex-first lens-first via ``_drip_order``, deterministic, so successive calls DRIP the
    cache toward fresh) and the remainder
    is DEFERRED LOUDLY - reported in ``n_deferred``, never silently computed. A budget of ``0``
    is the OFF posture (the LOCAL launcher's default since WO-20260715-233320-psu-embed-off): the
    serving path embeds NOTHING, defers every stale node, and announces it once (`embed drip
    OFF`). Every real drip (budget>0 / unlimited) emits one LOUD per-batch timing line. ``route``
    skips unvectored nodes, so a partial (or empty) cache serves degraded-but-plain. ``bulk=True``
    is the deliberate producer posture (``metric_distill``, the ``main()`` explicit fold, the close
    deposit): unlimited, budget-free, exactly the pre-guard behavior.

    STORE-01 (the 2026-08-20 self-audit, WO-20260819-embeddings-store-write-lock): the final
    merge+write is wrapped in ``laplace.pipeline.locking.store_lock`` so two concurrent lanes never
    lost-update each other's embeddings - the lock is taken only around the read-fresh+merge+write
    (never the read at the top of this function, never the model call), so the constant-traffic
    ``route`` caller is never serialized against another lane except for that one short write. On
    contention (:class:`~laplace.pipeline.locking.StoreBusy`) this call degrades-but-plain: it serves its
    own in-memory result unpersisted rather than blocking, and the next successful call's write
    catches up whatever this one embedded."""
    repo_root = Path(repo_root)
    cache_path = repo_root / CACHE_FILE

    def _read_cache() -> dict[str, Any]:
        if not cache_path.is_file():
            return {}
        try:
            disk = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return disk.get("nodes", {}) if disk.get("backend") == backend.name else {}

    cached: dict[str, Any] = _read_cache()
    nodes = net["nodes"]
    # the essence join's map is derived ONCE here and passed down - this is the vector-producing
    # path, so it reads the digest store fresh rather than through the memo (RUL-20260823-
    # essence-side-ratified). Empty dict when the switch is off or nothing serves.
    digests = digest_essences(repo_root, net)
    texts: dict[str, str] = {nid: node_text(repo_root, net, nid, digests) for nid in nodes}
    hashes = {nid: _hash(backend.name, t) for nid, t in texts.items()}
    stale = _drip_order(net, [nid for nid in nodes
                              if cached.get(nid, {}).get("h") != hashes[nid]])
    deferred = 0
    budget = None if bulk else _env_budget()
    if stale and not bulk:
        if budget == 0:
            # PSU-class OFF (WO-20260715-233320-psu-embed-off; F1 escalated freeze->PSU,
            # WALK_2026-07-15; local-numerics-trip-the-psu): the LOCAL serving path embeds
            # NOTHING. Every stale node is deferred; the vectors serve as-is (route skips the
            # unvectored) and the staleness is named in the UI. The warm rides the next remote
            # fold or the supervised close deposit (bulk=True, which ignores the budget).
            deferred = len(stale)
            stale = []
            _log_drip_off()
        elif budget is not None and len(stale) > budget:
            deferred = len(stale) - budget
            stale = stale[:budget]
            print(f"embed_router: DEFERRED {deferred} stale nodes (LAPLACE_EMBED_BUDGET="
                  f"{budget}, embedded {len(stale)} this call) - the serving path never "
                  f"bulk-embeds; the warm cache rides the next remote close or an explicit "
                  f"`python -m laplace.representation.embed_router` fold", flush=True)
    new_entries: dict[str, Any] = {}
    if stale:
        t0 = time.monotonic()
        embedded = backend.embed([texts[n] for n in stale])
        for nid, vec in zip(stale, embedded, strict=True):
            new_entries[nid] = {"h": hashes[nid], **_quantize_vec(vec)}
        cached.update(new_entries)
        if not bulk:
            # THE LOUD LINE: a serving-path drip actually embedded (budget>0 / unlimited). One
            # unmissable line per batch so any embed on the local serving path is visible.
            _log_drip_batch(len(stale), budget, time.monotonic() - t0)
    if stale:
        from laplace.representation.metric_distill import record_embedding_changes
        record_embedding_changes(repo_root, stale)
    pruned = len(cached) - sum(1 for nid in cached if nid in nodes)
    cached = {nid: e for nid, e in cached.items() if nid in nodes}
    # Serving (non-bulk) writes ONLY when it actually embedded: a prune-only rewrite
    # from the serving path dirties the tracked cache and blocks the next pull; prunes
    # persist at the next bulk fold (the producer posture).
    if stale or (bulk and (pruned or not cache_path.is_file())):
        from laplace.pipeline.locking import StoreBusy, store_lock  # lazy: avoids a module-load cycle
        try:
            with store_lock("self-embeddings"):
                # Re-read fresh UNDER the lock so a concurrent writer's update is never
                # clobbered: this call's own pre-lock read is the fallback base (a name it
                # knew about survives even if a race dropped it from the fresh read), the
                # fresh disk state overlays it (another lane's newer write wins), and this
                # call's own newly-embedded entries win last (STORE-01).
                merged = {**cached, **_read_cache(), **new_entries}
                merged = {nid: e for nid, e in merged.items() if nid in nodes}
                cache_path.write_text(
                    json.dumps({"backend": backend.name, "format": CACHE_FORMAT, "nodes": merged}),
                    encoding="utf-8")
                cached = merged
        except StoreBusy:
            pass  # degrade-but-plain: serve this call's result unpersisted, never block route()
    # ``entries`` is the merged, pruned cache in its STORED (quantized) form - additive, so every
    # existing caller reads exactly what it read before. ``basis`` below decodes it in one numpy
    # pass instead of re-materializing the per-node float lists this function already built.
    return {"vectors": {nid: _dequantize_entry(e) for nid, e in cached.items()},
            "entries": cached,
            "changed_ids": list(stale),
            "n_embedded": len(stale), "n_cached": len(cached) - len(stale),
            "n_deferred": deferred, "n_pruned": pruned, "n_total": len(cached)}


# ---------------------------------------------------------------------------
# the basis - the whole store as one float32 matrix, memoised per process
# ---------------------------------------------------------------------------

_BASIS_MEMO: dict[str, Any] = {}      # one slot; the key and its refusals are documented in basis()


def _dequantize_matrix(entries: dict[str, Any]) -> tuple[list[str], Any]:
    """Every stored entry as ONE ``(n, dim)`` float32 matrix plus the id list its rows are keyed
    by (row ``i`` is ``ids[i]``). The quantized rows decode in a single numpy pass - the base64
    payloads are concatenated, viewed as int8, reshaped and scaled row-wise - where the per-entry
    :func:`_dequantize_entry` loop spends its time building one small array and one Python list
    per node. A legacy ``{"v": [...]}`` entry carries no payload and is written into its row
    afterwards; a store whose rows disagree on width (only reachable mid-backend-change) falls
    back to the per-entry path."""
    import numpy as np
    ids = list(entries)
    payloads: list[bytes] = []
    rows: list[int] = []
    scales: list[float] = []
    floats: list[tuple[int, list[float]]] = []
    for i, nid in enumerate(ids):
        ent = entries[nid]
        v = ent.get("v")
        if v is not None:
            floats.append((i, list(v)))
        else:
            payloads.append(base64.b64decode(ent["q"]))
            rows.append(i)
            scales.append(float(ent["s"]))
    widths = {len(p) for p in payloads} | {len(v) for _, v in floats}
    if len(widths) != 1:
        dim = max(widths) if widths else 0
        M = np.zeros((len(ids), dim), dtype="float32")
        for i, nid in enumerate(ids):
            row = _dequantize_entry(entries[nid])
            M[i, :len(row)] = row
        return ids, M
    M = np.zeros((len(ids), widths.pop()), dtype="float32")
    if payloads:
        q = np.frombuffer(b"".join(payloads), dtype="int8").reshape(len(payloads), M.shape[1])
        M[rows] = q.astype("float32") * np.asarray(scales, dtype="float32")[:, None]
    for i, v in floats:
        M[i] = np.asarray(v, dtype="float32")
    return ids, M


def _net_stamp(repo_root: Path, net: dict[str, Any]) -> int:
    """A content fingerprint over exactly what :func:`node_text` reads out of ``net``: per node its
    id, parent, kind, stored essence, leaf-ness, keywords, coverage sample and lenses.

    THE STAMP REACHES UPWARD, WHICH IS WHY ``kind`` IS HERE. A node's text is not a function of its
    own fields alone: ``node_text`` walks three rungs of parents and asks :func:`_ancestor_label`
    for each, and that function branches on the ANCESTOR's ``kind`` (a ``concept`` rung is dropped
    at ``CHAIN_LABEL_TERMS = 0``; any other kind contributes its id tail) and reads the ANCESTOR's
    essence. So an edit to one internal node's ``kind`` or ``essence`` moves the text of every
    descendant within three rungs. That is covered here without any ancestor walk because EVERY
    node is stamped - the ancestor's own entry carries the fields its descendants' text depends on,
    so the mutation lands in the accumulator whichever end you look from.

    A node with NO stored essence has its text derived instead (``essence()``, which may compose or
    read), so that node's ``node_text`` rides the stamp in full - on the live network that set is
    empty of non-soul nodes, so this costs nothing there and still closes the class.
    ``soul://entities/`` items are excluded: their text comes off the folded shard, which the shard
    stamp covers.

    15 ms over 23,721 nodes - sixty times cheaper than the ``node_text`` pass it stands in for,
    because it hashes the fields rather than formatting them. XOR-accumulated so dict order never
    enters, and every entry carries its own id so two nodes cannot cancel."""
    nodes = net["nodes"]
    lenses = net.get("lenses") or {}
    digests: dict[str, str] | None = None
    h = 0
    for nid, n in nodes.items():
        ess = n.get("essence")
        derived = None
        if not ess and not nid.startswith("soul://entities/"):
            # LAZY, and that is the point: the essence-join map costs a descendant walk per served
            # node, and this branch is empty of non-soul nodes on the live network - so the stamp
            # pays for the join only where it already pays for a derived text.
            if digests is None:
                digests = digest_essences(repo_root, net)
            derived = node_text(repo_root, net, nid, digests)
        h ^= hash((nid, n.get("parent"), n.get("kind"), ess, n.get("leaf", True),
                   tuple(n.get("keywords") or ()), tuple(n.get("coverage") or ()),
                   tuple(lenses.get(nid) or ()), derived))
    return h


def _basis_key(repo_root: Path, net: dict[str, Any], backend_name: str) -> tuple:
    """The memo's invalidation key: everything :func:`ensure_embeddings` draws staleness from.

      * the STORE on disk - ``(mtime_ns, size, inode)`` of the vector cache. Another lane's write,
        this process's own drip write, a restored backup: any of them moves the stamp.
      * the FOLDED SHARD - ``(count, newest mtime_ns)``, a ``node_text`` input on disk that is
        neither the store nor ``net`` (the sealed entity items).
      * the DIGEST STORE - ``(mtime_ns, size)`` of ``.digests.jsonl``, the SECOND such input since
        the essence join (RUL-20260823-essence-side-ratified): a fresh mint changes the embedded
        text of every node it serves while ``net`` and the vector store sit still, so without this
        stat the memo would serve pre-mint vectors as fresh. The join's SWITCH rides too - flipping
        ``LAPLACE_DIGEST_ESSENCE`` moves every joined node's text, and the null arm is measured by
        flipping it, so the two arms must never share a memo slot.
      * the NETWORK - the content fingerprint above, so a ``net`` mutated in place between two
        calls invalidates exactly as a re-loaded one does. It stamps every node's own fields AND,
        by stamping every node, the ancestor fields (``kind``, ``essence``) that ``node_text``
        reaches three rungs up for; see :func:`_net_stamp` for why that suffices without a walk.
      * the BACKEND NAME, which rides every content hash, and the EMBED BUDGET, which decides
        whether a stale node is embedded or deferred.
    """
    cache = repo_root / CACHE_FILE
    try:
        st = cache.stat()
        store = (st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        store = None
    return (str(repo_root), backend_name, store, soul_shard_stamp(repo_root),
            digest_store_stamp(repo_root), digest_essence_on(),
            len(net["nodes"]), net.get("root", ""), _net_stamp(repo_root, net), _env_budget())


def soul_shard_stamp(repo_root: Path) -> tuple[int, int]:
    """The folded-entity shard's ``(count, newest mtime_ns)``, or ``(-1, -1)`` when there is no
    shard to stamp. Delegates to ``soul_provenance.shard_stamp`` - names and stat()s, no read."""
    try:
        from laplace.engine import soul_provenance
        return soul_provenance.shard_stamp(repo_root)
    except Exception:                    # noqa: BLE001 - no shard is a supported state
        return (-1, -1)


def basis(repo_root: Path | str, net: dict[str, Any], backend: Any, *,
          bulk: bool = False) -> dict[str, Any]:
    """The embedding basis as ``{ids, matrix, vectors, ...the ensure_embeddings report}``, built
    once per process per generation. ``matrix`` is ``(n, dim)`` float32 and ``vectors[nid]`` is
    that matrix's row for ``nid`` - a view, not a copy, so the dict costs rows not vectors.

    WHY THIS EXISTS (WO-20260821-route-basis-memo). ``route`` called ``ensure_embeddings`` per
    fire, and that call re-read the 16 MB store, re-derived ``node_text`` for all 23,721 nodes,
    re-hashed them, dequantized the whole cache into Python lists and handed ``route`` a dict it
    then re-materialized as numpy - 1.54 s of the 1.61 s a route cost, with the descent itself at
    0.05 s and nothing stale. Fourteen thread probes paid it fourteen times.

    THE ONE FORBIDDEN FAILURE IS STALE-CLAIMING-FRESH, and the memo is built to refuse it twice
    over. :func:`_basis_key` covers every input ``ensure_embeddings`` draws staleness from (store,
    shard, network content, backend, budget) - including the UPWARD reach, since a node's text is
    built from three rungs of its ancestors' ``kind`` and ``essence`` and every node is stamped, so
    an ancestor edit moves the key from the ancestor's own entry. The memo ADDITIONALLY requires
    the caller's ``net`` to be the same OBJECT, so two networks can never share a slot whatever their
    fingerprints. The key is computed AFTER the ensure call, so a call that wrote the store keys
    its result to the post-write state rather than to a stamp it has already invalidated.

    A DRIP IS NEVER MEMOISED. Under ``LAPLACE_EMBED_BUDGET > 0`` a serving call embeds part of the
    stale set and leaves the rest deferred; memoising that would freeze the cache mid-walk instead
    of letting successive calls drip it toward fresh. So the result is stored only when nothing is
    left to do - ``n_deferred == 0``, or the budget is ``0``, the OFF posture under which the
    serving path embeds nothing ever and a re-run is bit-identical by contract. ``bulk=True`` (the
    producer path: ``metric_distill``, the close deposit, the explicit fold) is never memoised and
    never reads the memo: it is the call that WRITES the store, it runs once, and it must always
    re-derive.

    The report keys carried over from ``ensure_embeddings`` describe the BASIS - the build that
    produced it - not the call that re-served it, so a caller that needs per-call embed counts
    reads ``ensure_embeddings`` directly.

    THE RESIDUAL, NAMED: a node whose essence is derived rather than stored rides the memo through
    its full ``node_text`` (see :func:`_net_stamp`), but if that derivation reads a file, an edit
    to that file mid-process is invisible until the store, the shard, or the network moves. On the
    live network no non-soul node takes that path."""
    repo_root = Path(repo_root)
    slot = _BASIS_MEMO.get("slot")
    if not bulk and slot is not None and slot["net"] is net \
            and slot["key"] == _basis_key(repo_root, net, backend.name):
        return slot["basis"]
    rep = ensure_embeddings(repo_root, net, backend, bulk=bulk)
    ids, matrix = _dequantize_matrix(rep["entries"])
    out: dict[str, Any] = {"ids": ids, "matrix": matrix,
                           "vectors": {nid: matrix[i] for i, nid in enumerate(ids)}}
    out.update({k: v for k, v in rep.items() if k not in ("vectors", "entries")})
    if not bulk and (rep["n_deferred"] == 0 or _env_budget() == 0):
        _BASIS_MEMO["slot"] = {"key": _basis_key(repo_root, net, backend.name),
                               "net": net, "basis": out}
    return out


# ---------------------------------------------------------------------------
# the trained metric - the coupling wire distilled into the geometry (optional)
# ---------------------------------------------------------------------------

_METRIC: dict[str, Any] = {}
_METRIC_DIGESTS: dict[str, Any] = {}


class MetricGenerationMismatch(RuntimeError):
    """A present metric cannot be used against a different or unverified basis."""


def _file_digest(path: Path) -> str | None:
    import hashlib
    if not path.is_file():
        return None
    st = path.stat()
    key = (st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
    name = str(path.resolve())
    cached = _METRIC_DIGESTS.get(name)
    if cached and cached[0] == key:
        return cached[1]
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    digest = "sha256:" + h.hexdigest()
    _METRIC_DIGESTS[name] = (key, digest)
    return digest


def metric_status(repo_root: Path | str) -> dict[str, Any]:
    """One content-based compatibility rule for geometric and taste retrieval.

    Timestamps do not establish a generation: copied files can retain or acquire arbitrary
    mtimes. A receipt binds the metric, sidecar and embedding bytes. Digests are memoised
    against inode/size/mtime/ctime so warm reads only stat the same three files.
    """
    root = Path(repo_root)
    if not (root / METRIC_FILE).is_file():
        return {"state": "absent", "file": METRIC_FILE, "reason": "no metric; raw cosine"}
    try:
        state = json.loads((root / ".metric_M.receipt.json").read_text(encoding="utf-8"))
        banked = state["banked"]
        if not isinstance(banked, dict) or not banked.get("shipped"):
            raise ValueError("no published metric receipt")
        if state.get("pending"):
            raise ValueError("embedding changes await metric publication")
        checks = {METRIC_FILE: banked.get("metric_hash"),
                  ".metric_pairs.json": banked.get("pairs_handle")}
        checks.update(banked.get("render_artifacts", {}))
        if (root / CACHE_FILE).exists():
            checks[CACHE_FILE] = banked.get("store_after", {}).get(CACHE_FILE)
        for name, expected in checks.items():
            if not expected or _file_digest(root / name) != expected:
                raise ValueError(name + " differs from the published metric generation")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {"state": "generation-mismatch", "file": METRIC_FILE, "reason": str(exc),
                "recovery": "scripts/laplace-python scripts/reembed.py --full-metric"}
    return {"state": "applied-fresh", "file": METRIC_FILE,
            "reason": "receipt matches metric, pairs and basis; applied as q'Mv"}


def load_metric(repo_root: Path | str) -> Any:
    """Load only a compatible published metric; a mismatch is a visible refusal."""
    import numpy as np
    status = metric_status(repo_root)
    if status["state"] == "absent":
        return None
    if status["state"] != "applied-fresh":
        raise MetricGenerationMismatch(status["reason"] + "; " + status.get("recovery", ""))
    p = Path(repo_root) / METRIC_FILE
    key = (str(p.resolve()), _file_digest(p))
    if _METRIC.get("key") != key:
        try:
            with np.load(p, allow_pickle=False) as artifact:
                M = artifact["M"].astype("float32")
            if M.ndim != 2 or M.shape[0] != M.shape[1] or not np.isfinite(M).all():
                raise ValueError("metric must be a finite square matrix")
            _METRIC.update(key=key, M=M)
        except (OSError, KeyError, ValueError) as exc:
            raise MetricGenerationMismatch(str(exc)) from exc
    return _METRIC.get("M")


# ---------------------------------------------------------------------------
# the frontier mass term - swept, and the row's own two candidates REFUTED
# ---------------------------------------------------------------------------
#
# WO-20260821-route-frontier-mass-term asked for a term against nested lens-claimed sub-node mass:
# "per-parent mass normalization, or ``_absorbed`` extended so a ``::`` sub-node yields to its
# handle unless it out-pulls it", swept over the 25 paper-slug queries plus derivative-tree
# controls, bar = route >= 24/25 with zero controls inverting and zero landed regressions.
#
# BOTH WERE BUILT AND BOTH LANDED THE INCUMBENT, EXACTLY (evidence/ROUTE_MASS_TERM_2026-08-21/
# sweep.json, one pinned store, 14 policies x 41 queries): ``handle``, ``ancestor``, ``quota``,
# ``handle_quota``, ``sibling_decay`` and ``handle_decay`` every one landed 23 of 25 - the
# incumbent's own number, to the paper. They are kept below as named modes so the refutation
# replays instead of being re-proposed.
#
# WHY THEY COULD NOT HAVE WORKED, and it is a lesson about where a term has to act: a POOLING term
# can only re-rank what the descent already REACHED. The anatomy run (anatomy_before.json) shows
# the misses never reached their families at all - 1 of 27 and 1 of 34 family members in the pool.
# The predecessor lane read "~71% of the mass above the hit is `::` nested" as rank dilution; on a
# re-measure that mass is above a single SHARED connectome node, while the paper's own pdf/tex/
# store members are absent from the pool entirely. It is starvation, and it is at the frontier.
#
# THE FRONTIER, MEASURED (apex.json). Heat is path-inherited: g = max(own, PATH_DECAY * g_parent).
# Every candidate whose own cosine is below the inherited floor lands on EXACTLY that floor. The
# apex has NINE lens branches against a beam of EIGHT, so one is dropped on every query - and on
# all 25 bench queries the dropped branch was one of those exact ties, decided by `(-heat, id)`,
# i.e. by SPELLING: ``mind://standing`` (last in ascending id order) dropped 16/25,
# ``mind://lens/substrate`` (13,698 nodes) 5/25, ``mind://lens/world`` (23,467 nodes) 3/25. Eight
# of free-snacks' nine family members are reachable only through substrate or world.
#
# THE RULED CURE is not a mass term at all: the apex is entered WHOLE (``apex: "whole"``, see
# ``_descend``). 23/25 -> 25/25, zero regressions, zero derivative-tree inversions, +16% wall
# (0.598 -> 0.694 s/query). ``beam=9`` buys the same 25/25 by paying width at EVERY level; the
# apex rule buys it at level zero only, which is where the defect is. Shrinking the beam to 4 on
# top of the apex rule keeps 25/25 but inverts three derivative controls - so the apex rule is a
# fix, never a licence to narrow the beam.
SIBLING_DECAY = 0.75              # the lateral attenuation per additional member of the same parent
MASS_POLICY: dict[str, Any] = {"mode": "incumbent", "apex": "whole", "tie_break": "id"}


def _handle_of(nid: str) -> str:
    """The FILE a `::`-nested sub-node belongs to (`a/b.json::topic//sub` -> `a/b.json`). For a
    node with no `::` this is the node itself - the handle of a plain node is the node."""
    return nid.split("::", 1)[0]


def frontier_order(candidates: set[str] | list[str], own: dict[str, float],
                   heat: dict[str, float], policy: dict[str, Any] | None = None,
                   *, inherited: dict[str, float] | None = None) -> list[str]:
    """Sort one level's internal candidates best-first, and BREAK THE TIE ON EVIDENCE.

    THE DEGENERACY THIS EXISTS FOR (measured 2026-08-21,
    ``evidence/ROUTE_MASS_TERM_2026-08-21/apex.json``). Heat is path-inherited:
    ``g = max(own, PATH_DECAY * g_parent)``. Every candidate whose OWN cosine falls below the
    inherited floor therefore lands on EXACTLY that floor - bit-identical, not merely close. At
    the apex the network has 9 lens branches against a beam of 8, so one is always dropped; on all
    25 paper-slug bench queries the dropped branch was one of these ties, and with
    ``key=(-heat, id)`` the ALPHABET decided which. ``mind://standing`` (last in the ascending id
    order) was dropped on 16 of 25, ``mind://lens/substrate`` (13,698 nodes) on 5, and
    ``mind://lens/world`` (23,467 nodes) on 3 - a whole lens of the mind lost per query, by
    spelling.

    ``tie_break: "own"`` breaks that tie on ``own[m]`` instead - a signal already computed, which
    ``max`` discards only for the ordering. It is NOT the ruled default, and the reason is a
    number, not a preference: on the sweep it landed the incumbent's 23/25 AND regressed
    ``polaron-imposters``, which the incumbent ordering lands. With the apex rule in place it is
    exactly neutral (25/25 either way). So it stays reachable and unruled: the apex, not the
    ordering, was the defect, and a knob that only ever costs is not a cure. ``id`` is the default
    here so that any policy which does not name the key gets the incumbent ordering.

    ``inherited`` is the QUANTILE POOL's rider (i), and is passed by nothing else: under
    within-block quantile calibration every block's top child maps to exactly 1.0, so a level's
    beam meets a k-way tie at the top and the alphabet would decide it again. The named tiebreak
    is the descent's own inherited path heat (``path_decay * g_parent`` along the winning path) -
    a term the loop already computes, ranked ahead of the id and behind the served heat. Absent
    (every unarmed call), the key is the incumbent's, element for element.
    """
    policy = policy or MASS_POLICY
    own_tie = policy.get("tie_break", "id") != "id"

    def key(m: str) -> tuple:
        k: tuple = (-heat.get(m, 0.0),)
        if inherited is not None:
            k += (-inherited.get(m, 0.0),)   # rider (i), and it is NOT a new dial: the g-term the
        if own_tie:                          # descent already computed, read as the tiebreak
            k += (-own.get(m, 0.0),)
        return k + (m,)

    return sorted(candidates, key=key)


def frontier_select(nodes: dict[str, Any], internal: list[str], heat: dict[str, float],
                    beam: int, policy: dict[str, Any] | None = None) -> list[str]:
    """Choose which internal nodes of one scored level the descent EXPANDS - the beam, with the
    mass term applied where it can still change what is REACHED rather than only what is ranked.

    ``internal`` arrives already sorted best-first. ``frontier_decay`` (1.0 = off, the incumbent
    ``internal[:beam]``) attenuates each candidate by ``decay ** n``, where n counts the candidates
    ALREADY TAKEN that share its ``frontier_key`` - ``handle`` (the file, the default) or
    ``parent``. So a single file's ladder can take the first beam slot at full strength and the
    second at ``decay``, and a rival branch with an independent handle wins the third.

    This is the half that matters. The pooling term (``frontier_mass_rank``) can only re-rank what
    the descent already reached; a family whose members were never reached cannot be re-ranked into
    the answer - and on three of route's four misses the family node was never in the pool at all
    (evidence/ROUTE_MASS_TERM_2026-08-21/anatomy.json). The beam is where the mass is actually
    spent, so that is where a mass term has to act to change reach."""
    policy = policy or MASS_POLICY
    decay = float(policy.get("frontier_decay", 1.0))
    width = max(1, int(beam))
    if decay >= 1.0 or not internal:
        return internal[:width]
    by_parent = policy.get("frontier_key", "handle") == "parent"

    def key_of(m: str) -> str:
        return (nodes.get(m, {}).get("parent") or m) if by_parent else _handle_of(m)

    # anchored at the level's own floor, exactly as the pooling term is anchored at the pool's:
    # a pure contraction of the margin above the coldest candidate, so a negative cosine can never
    # be PROMOTED by being attenuated (which a bare multiply would do).
    base = min((heat.get(m, 0.0) for m in internal), default=0.0)
    taken: dict[str, int] = {}
    kept: list[str] = []
    remaining = list(internal)
    while remaining and len(kept) < width:
        best_i, best_s = 0, None
        for i, m in enumerate(remaining):
            h = heat.get(m, 0.0)
            s = base + (h - base) * (decay ** taken.get(key_of(m), 0))
            if best_s is None or s > best_s:
                best_i, best_s = i, s
        m = remaining.pop(best_i)
        taken[key_of(m)] = taken.get(key_of(m), 0) + 1
        kept.append(m)
    return kept


def frontier_mass_rank(nodes: dict[str, Any], pool: dict[str, float], own: dict[str, float],
                       heat: dict[str, float], policy: dict[str, Any] | None = None,
                       *, floor: float | None = None,
                       pool_rank: dict[str, float] | None = None) -> list[tuple[str, float, float]]:
    """Rank the hit pool with a mass term: ``[(nid, ranking_score, raw_heat)]``, best first.

    Every mode first applies the ABSORPTION rule (a node yields when something above it already
    speaks for it), then optionally a LATERAL term over the survivors. The modes:

      * ``incumbent``      - parent-absorption only; exactly the pre-2026-08-21 behaviour.
      * ``handle``         - parent-absorption, plus: a ``::`` sub-node also yields to its FILE
                             handle when its own cosine did not beat the handle's heat.
      * ``ancestor``       - a node yields to ANY reached ancestor that out-heats its own cosine.
      * ``quota``          - parent-absorption, then at most ``quota`` survivors per tree parent.
      * ``handle_quota``   - parent-absorption, then at most ``quota`` survivors per FILE handle.
      * ``sibling_decay``  - parent-absorption, then the n-th best survivor of a parent is
                             attenuated by ``decay**n`` toward the pool floor.
      * ``handle_decay``   - the same attenuation, keyed on the FILE handle rather than the parent,
                             so a whole ``::`` ladder counts as one file's evidence.

    EVERY ONE OF THESE IS A REFUTED CANDIDATE, KEPT REACHABLE. The row proposed the last four; the
    sweep built them and they all landed 23 of 25 - the incumbent's own number, at decays 0.95 to
    0.25 and quotas 1 to 3 (``evidence/ROUTE_MASS_TERM_2026-08-21/sweep.json``). The reason is
    structural and worth keeping in front of the next lane: this function runs AFTER the descent,
    so it can only re-rank what was reached, and the misses were never reached. ``incumbent`` is
    the ruled mode. The attenuation, where a caller does want it, is anchored at ``floor`` (the
    pool minimum) so it is a pure contraction of the margin above the floor: rank 0 is untouched,
    the ordering inside a parent is preserved, and nothing is pushed below the coldest thing the
    pull touched.
    """
    policy = policy or MASS_POLICY
    mode = policy.get("mode", "incumbent")

    def absorbed(m: str) -> bool:
        p = nodes.get(m, {}).get("parent")
        if p in pool and own.get(m, 0.0) <= heat.get(p, -1.0):
            return True
        if mode == "handle" and "::" in m:
            h = _handle_of(m)
            if h in pool and own.get(m, 0.0) <= heat.get(h, -1.0):
                return True
        if mode == "ancestor":
            cur, hops = nodes.get(m, {}).get("parent"), 0
            while cur and hops < 12:
                if cur in pool and own.get(m, 0.0) <= heat.get(cur, -1.0):
                    return True
                cur, hops = nodes.get(cur, {}).get("parent"), hops + 1
        return False

    # THE POOL-RANK TERM (the geomean ruling, 2026-08-23): under the calibration lever the
    # heat saturates at 1.0 and this sort degenerated to the alphabet (measured: 19/24/25 of
    # 25 tied on the three deep probes). ``pool_rank`` - the geomean of the winning path's
    # per-level calibrated scores - ranks between heat and id; the trailing id is DETERMINISM,
    # not ranking (it breaks only exact geomean ties). Absent (every unarmed call), the key is
    # the incumbent's, element for element.
    if pool_rank is not None:
        survivors = sorted(((m, g) for m, g in pool.items() if not absorbed(m)),
                           key=lambda kv: (-kv[1], -pool_rank.get(kv[0], 0.0), kv[0]))
    else:
        survivors = sorted(((m, g) for m, g in pool.items() if not absorbed(m)),
                           key=lambda kv: (-kv[1], kv[0]))
    if mode in ("incumbent", "handle", "ancestor"):
        return [(m, g, g) for m, g in survivors]

    def key_of(m: str) -> str:
        # a parentless node keys on ITSELF, never on a shared empty string - otherwise every root
        # would count as one another's sibling and a quota of 1 would delete all but one of them.
        if mode in ("handle_quota", "handle_decay"):
            return _handle_of(m)
        return nodes.get(m, {}).get("parent") or m

    seen: dict[str, int] = {}
    out: list[tuple[str, float, float]] = []
    if mode in ("quota", "handle_quota"):
        cap = max(1, int(policy.get("quota", 2)))
        for m, g in survivors:
            k = key_of(m)
            seen[k] = seen.get(k, 0) + 1
            if seen[k] <= cap:
                out.append((m, g, g))
        return out
    if mode in ("sibling_decay", "handle_decay"):
        decay = float(policy.get("decay", SIBLING_DECAY))
        base = floor if floor is not None else (min(pool.values()) if pool else 0.0)
        for m, g in survivors:
            k = key_of(m)
            n = seen.get(k, 0)
            seen[k] = n + 1
            out.append((m, base + (g - base) * (decay ** n), g))
        out.sort(key=lambda t: (-t[1], t[0]))
        return out
    return [(m, g, g) for m, g in survivors]          # an unknown mode degrades to the incumbent


# --- P27: block-local reduced bases + query renormalization down the descent -----------------
# THE MECHANISM (AMEND-20260823-p27-mechanism-pinned, confirmed on all five decisions by
# RUL-20260823-p27-design-confirmed). Inside a block - one expanded node's candidate children -
# the shared component that makes everything look equidistant IS the block mean. Removing it is
# the renormalization: the residual-decides law applied to the metric itself. What survives the
# mean is projected into the block's OWN retained subspace (the top principal directions of the
# mean-centred child vectors) and the overlap is scored there. The descent borrows the UP side's
# declared bond dimension rather than inventing a second one - see :func:`_block_chi`.
#
# THE FIVE DECISIONS, AS BUILT.
#   D1  the block's density matrix is the CANDIDATE CHILDREN's own vectors, read as rows of the
#       basis matrix - never reached deeper into a leaf's members, and never a new embedding.
#   D2  rank = min(chi(level), n_children - 1, d)  (:func:`_block_rank`).
#   D3  PROJECTED COSINE in that subspace. No block whitening, and the global metric M NEVER
#       enters a projected block - the block scores the RAW query, mean-removed and rotated.
#   D4  a block too small to carry a basis (n < 3) or clamped to rank 0 takes NO projection: it
#       scores exactly as the incumbent (global cosine, M applied), and is counted.
#   D5  one flag-gated branch. Heat inheritance, the beam, per-branch width and path decay are
#       untouched - the renormalization changes what a local overlap IS, never which overlaps
#       compute. With the flag unset the descent below is the incumbent, line for line.
#
# THE SEAM R2 NAMES, AND THIS COUNTS: D4's fallback makes a level's pool able to rank projected
# cosines against global q'Mv in one comparison - incommensurable distributions, accepted rather
# than blunted, and reported as ``mixed_levels`` so it is the FIRST candidate explanation for any
# red or eviction this arm produces.
#
# THE INTERPRETIVE BOUND (R3, banked before any run): the block basis is fit on INCUMBENT HANDLE
# VECTORS - path-token soup in, path-token directions out. Mean-removal only reveals contrast the
# vectors already carry, so a red here types as "renormalization under incumbent handles" and
# does not speak for renormalized descent over content-grade vectors.

_BLOCK_MIN_CHILDREN = 3          # D4: below this a block cannot carry a basis worth the name


def _block_renorm_on() -> bool:
    """The arm flag, READ AT CALL TIME - never captured at import. Only the exact string ``1``
    arms it; unset, empty, ``true`` and ``0`` all leave the incumbent descent bit-identical
    (guard (a): an arm flag is never a serving default)."""
    import os
    return os.environ.get("LAPLACE_BLOCK_RENORM", "") == "1"


def _organ_residual_on() -> bool:
    """The fork arm (NOTE-20260824-organ-residual-arm-prereg, graded per
    AMEND-20260824-fork-vs-cure-graded-apart): banked frames act ONLY through a
    margin-preserving channel - incumbent global-cosine scores untouched, one bounded
    within-block residual demotion in the block's own units. Requires LAPLACE_ORGAN_V1=1
    (the frames must serve); orthogonal to the renorm arm. Same guard (a): never a
    serving default, read at call time, exact string ``1`` only."""
    import os
    return os.environ.get("LAPLACE_ORGAN_RESIDUAL", "") == "1"


def _organ_bmatched_on() -> bool:
    """AMENDMENT 6's decisive arm (judge-4's grade of AB_RUN_3): the incumbent SERVE-TIME
    basis (_block_basis, NO frames) applied to EXACTLY the blocks where a concept::
    frame exists - coverage-matched to C_PRIME by construction, global cosine elsewhere.
    The banked frames serve ONLY as the mask; their geometry never scores. Separates
    'basis matters' from 'only coverage matters' - nothing else in the design does.
    Requires LAPLACE_ORGAN_V1=1 (the mask must read); guard (a) as ever."""
    import os
    return os.environ.get("LAPLACE_ORGAN_BMATCHED", "") == "1"


def _organ_cprime_on() -> bool:
    """THE SEAL'S DECISIVE ARM (NOTE-20260824-the-seal-opened; the unsealed derivation's
    C-PRIME): where a banked frame serves a block, the frame REPLACES the scoring
    functional - the child scores by projected cosine in the BANKED shared layer basis
    (calibration off, patches off, no demotion). The falsifier the seal declared: if
    C-prime still evicts or reads 0 with the patches off, the frames themselves are
    implicated - MEANINGFUL only post-join (gate reach 67.9%; the potency floor catches
    residual inertness). Requires LAPLACE_ORGAN_V1=1; the fair-test harness enforces
    posture exclusivity with ORGAN_RESIDUAL and BLOCK_RENORM. Guard (a) as ever."""
    import os
    return os.environ.get("LAPLACE_ORGAN_CPRIME", "") == "1"


def _block_chi(level: int) -> int:
    """The FOLD's own declared bond dimension, borrowed by the descent - never a second copy of
    the ladder. ``RES-20260823-chi-declared-by-measurement`` banks it in-band at
    ``meaning_upfold._SELECTOR_CHI_LADDER`` (level 1 -> 16, level >= 2 -> 8; a level past the
    last declared rung inherits the last declared value). Reading that one home is what makes
    his dial move both sides of the engine at once."""
    from laplace.engine.meaning_upfold import _selector_chi
    return int(_selector_chi(int(level)))


def _block_rank(n_children: int, dim: int, chi: int) -> int:
    """D2's clamp: ``min(chi(level), n_children - 1, d)``, floored at 0. ``n - 1`` because the
    block mean is SPENT - n mean-centred vectors span at most n-1 directions, so any rank above
    that is numerical noise dressed as a retained direction."""
    return max(0, min(int(chi), int(n_children) - 1, int(dim)))


_ORGAN_MEMO: dict[tuple[str, int, int], dict[str, Any]] = {}


def _organ_frames(repo_root: Path | str) -> dict[str, Any] | None:
    """M4 (RUL-20260823-organ-codesign-converged): the BANKED fold-time frames, served to
    the descent so the serve-time SVD retires where a frame exists. ``None`` when the v1
    flag is off - the incumbent path is untouched. KEY CORRESPONDENCE, named per the
    judge's probe: the fold banks per CLUSTER ID (sha1-of-membership, spanning the
    cluster's descendant leaves); route's block is (node, direct-child-set) - the ids
    match where the expanded node IS a fold cluster, and the two bases are NOT claimed
    equivalent (fold Qb: handle + covariance eigvecs over leaves; _block_basis: centred
    PCA over children) - the A/B adjudicates, never argument.

    STALENESS (v1, store-level, named plainly): the store's ``written_at`` is compared
    against the meaning tree file's mtime - a tree newer than its frames marks EVERY
    frame stale (per-block staleness is later work; all-or-nothing is honest and cheap).
    The read is memoized per (store mtime_ns, size) - a rebuild or refold invalidates by
    key, and a torn store serves typed-empty (isometries D2), counted, never raised."""
    import os

    from laplace.representation import isometries

    if not isometries.organ_on():
        return None
    root = Path(repo_root)
    store = root / isometries.STORE
    try:
        st = store.stat()
        key = (str(store), st.st_mtime_ns, st.st_size)
    except OSError:
        key = (str(store), 0, 0)
    # THE FAMILY FILTER (VERDICT-20260824-custody-refused-object-substitution): the store
    # holds two frame families - concept:: (the fold's leaf-spanning frames, THE FORK'S
    # OBJECT) and network-keyed (direct-member frames, its own separate question).
    # LAPLACE_ORGAN_FAMILY = concept | network | all (default all) scopes which family
    # serves this fire; the scope is part of the arm's posture and rides the memo key.
    family = os.environ.get("LAPLACE_ORGAN_FAMILY", "all").strip() or "all"
    key = (*key, family)
    hit = _ORGAN_MEMO.get(key)
    if hit is None:
        got = isometries.read_for_descent(root)
        if family == "concept":
            got["frames"] = {k: v for k, v in got["frames"].items()
                             if k.startswith("concept::")}
        elif family == "network":
            got["frames"] = {k: v for k, v in got["frames"].items()
                             if not k.startswith("concept::")}
        meta = got["meta"]
        torn = "torn" in meta
        stale = False
        if not torn and got["frames"]:
            tree = root / ".meaning_tree.json"
            written = str(meta.get("written_at") or "")
            try:
                import datetime as _dt
                tree_m = _dt.datetime.fromtimestamp(tree.stat().st_mtime,
                                                    _dt.timezone.utc)
                stale = (not written) or tree_m > _dt.datetime.fromisoformat(written)
            except (OSError, ValueError):
                stale = True   # no tree / unparseable stamp: frames grounded on nothing readable
        hit = {"frames": got["frames"],
               "refused": {r.get("block") for r in (meta.get("refused") or [])},
               "stale": stale, "torn": torn}
        _ORGAN_MEMO.clear()      # one store, one live key - a moved store evicts its past
        _ORGAN_MEMO[key] = hit
    return hit


_ORGAN_RES_MIN_CHILDREN = 4     # below this a q90 over children residuals is noise, not a gate


def _organ_residual_gate(nid: str, assigned: list[str], vecs: dict[str, Any],
                         raw_l: dict[str, float], organ_res: dict[str, Any],
                         report: dict[str, Any]) -> None:
    """THE FORK ARM's one act (NOTE-20260824-organ-residual-arm-prereg): a bounded
    within-block coherence demotion over UNTOUCHED incumbent scores.

    The banked frame's residual ``||(1-QQ+)v||`` is computed per child THIS block scored;
    children above the block's own q90 (its children's own residual distribution - no
    cross-block comparison, no calibration, nothing flattened) demote to just below the
    block's kept children, preserving their relative order among themselves. The margin
    carrier (the global cosine) survives verbatim for every kept child; the only act is
    a bounded reorder in the banked geometry's own units. Skips count by cause exactly as
    M4's consumption does (torn / degenerate / stale_isometry / no_key / too_small)."""
    import numpy as np

    if organ_res["torn"]:
        report["skipped_by_cause"]["torn"] += 1
        return
    if nid in organ_res["refused"]:
        report["skipped_by_cause"]["degenerate"] += 1
        return
    if nid not in organ_res["frames"]:
        report["skipped_by_cause"]["no_key"] += 1
        return
    if organ_res["stale"]:
        report["skipped_by_cause"]["stale_isometry"] += 1
        return
    scorable = [m for m in assigned if vecs.get(m) is not None]
    if len(scorable) < _ORGAN_RES_MIN_CHILDREN:
        report["skipped_by_cause"]["too_small"] += 1
        return
    f = organ_res["frames"][nid]
    Q = f["Q"]
    res = {m: float(np.linalg.norm(vecs[m] - Q @ (Q.T @ vecs[m]))) for m in scorable}
    q90 = float(np.quantile(np.asarray(list(res.values()), dtype=np.float64), 0.90))
    demoted = [m for m in scorable if res[m] > q90]
    if not demoted:
        report["blocks_gated"] += 1
        return
    kept_lo = min(raw_l[m] for m in scorable if m not in demoted)
    # order among the demoted preserved (least-incoherent first), all strictly below kept
    for i, m in enumerate(sorted(demoted, key=lambda m: res[m])):
        raw_l[m] = kept_lo - 1e-4 * (i + 1)
    report["blocks_gated"] += 1
    report["children_demoted"] += len(demoted)


def _organ_cprime_score(nid: str, assigned: list[str], vecs: dict[str, Any],
                        raw_l: dict[str, float], qraw: Any, organ_cp: dict[str, Any],
                        report: dict[str, Any]) -> None:
    """C-PRIME's one act (the seal's decisive arm): where a banked frame serves, the
    frame REPLACES the scoring functional for the block's newly-assigned children -
    projected cosine in the BANKED basis span(Q) (the mean direction is Q's first
    column, so no separate centering; judge-4's confirmed geometry), RAW query side
    (the renorm arm's D3 convention: the metric never enters a rotated subspace).
    Zero-norm projections score 0.0 rather than dividing (_block_cosines' own rule).
    Skips count by the same five causes as the residual gate."""
    import numpy as np

    if organ_cp["torn"]:
        report["skipped_by_cause"]["torn"] += 1
        return
    if nid in organ_cp["refused"]:
        report["skipped_by_cause"]["degenerate"] += 1
        return
    if nid not in organ_cp["frames"]:
        report["skipped_by_cause"]["no_key"] += 1
        return
    if organ_cp["stale"]:
        report["skipped_by_cause"]["stale_isometry"] += 1
        return
    scorable = [m for m in assigned if vecs.get(m) is not None]
    if not scorable:
        report["skipped_by_cause"]["too_small"] += 1
        return
    Q = organ_cp["frames"][nid]["Q"]
    q = np.asarray(qraw, dtype="float32")
    qp = Q.T @ q
    qn = float(np.linalg.norm(qp))
    # the zero-guard is RELATIVE, not absolute (the unit witness's catch): f32 roundoff
    # leaves ~1e-6 of norm in a numerically-orthogonal vector, and a ratio of two tiny
    # numbers is noise wearing a cosine - the margin-destroying class this arm tests
    # against. A component under 1e-5 of the vector's own norm scores 0.0, plainly.
    q_floor = 1e-5 * float(np.linalg.norm(q))
    for m in scorable:
        if qn <= q_floor:
            raw_l[m] = 0.0
            continue
        v = np.asarray(vecs[m], dtype="float32")
        cp = Q.T @ v
        cn = float(np.linalg.norm(cp))
        raw_l[m] = (float(qp @ cp) / (qn * cn)
                    if cn > 1e-5 * float(np.linalg.norm(v)) else 0.0)
    report["blocks_scored"] += 1
    report["children_scored"] += len(scorable)


def _organ_bmatched_score(nid: str, assigned: list[str], members_vecs, vecs: dict[str, Any],
                          raw_l: dict[str, float], qraw: Any, mask: dict[str, Any],
                          chi: int, report: dict[str, Any]) -> None:
    """B_MATCHED's one act: where the MASK (a concept:: frame exists for nid) says the
    functional applies, fit the INCUMBENT serve-time basis over the block's members and
    score the newly-assigned children by its projected cosine - the same _block_basis /
    _block_cosines math as arm B, at C_PRIME's exact coverage. The frames' geometry is
    never consulted; only their keys. Skips count by the same causes."""
    import numpy as np

    if mask["torn"]:
        report["skipped_by_cause"]["torn"] += 1
        return
    if nid in mask["refused"]:
        report["skipped_by_cause"]["degenerate"] += 1
        return
    if nid not in mask["frames"]:
        report["skipped_by_cause"]["no_key"] += 1
        return
    if mask["stale"]:
        report["skipped_by_cause"]["stale_isometry"] += 1
        return
    scorable = [m for m in assigned if vecs.get(m) is not None]
    if not scorable:
        report["skipped_by_cause"]["too_small"] += 1
        return
    entry = _block_basis(members_vecs, chi)
    if entry is None:
        report["skipped_by_cause"]["degenerate"] += 1
        return
    mu, proj, _coords, _cn = entry
    q = np.asarray(qraw, dtype="float32")
    qp = proj @ (q - mu)
    qn = float(np.linalg.norm(qp))
    q_floor = 1e-5 * float(np.linalg.norm(q))
    for m in scorable:
        if qn <= q_floor:
            raw_l[m] = 0.0
            continue
        v = np.asarray(vecs[m], dtype="float32")
        cp = proj @ (v - mu)
        cn = float(np.linalg.norm(cp))
        raw_l[m] = (float(qp @ cp) / (qn * cn)
                    if cn > 1e-5 * float(np.linalg.norm(v)) else 0.0)
    report["blocks_scored"] += 1
    report["children_scored"] += len(scorable)


def _block_basis(mat: Any, chi: int) -> tuple[Any, Any, Any, Any] | None:
    """One block's reduced basis and its children's coordinates in it - or ``None`` when the
    block FALLS BACK (D4: fewer than three children, or a rank clamped to 0).

    Returns ``(mu, proj, coords, coord_norms)``: the block mean, the ``(rank, d)`` retained
    directions, the ``(n, rank)`` projected child coordinates and their row norms. Every piece is
    query-INDEPENDENT, which is what makes the memo worth having - one small SVD per (node,
    child-set) per process, after which each query pays one ``(rank, d)`` matvec and one
    ``(n, rank)`` matvec instead of a PCA."""
    import numpy as np
    n, d = mat.shape
    rank = _block_rank(n, d, chi)
    if n < _BLOCK_MIN_CHILDREN or rank <= 0:
        return None
    mu = mat.mean(axis=0)
    centred = mat - mu
    try:
        _u, _s, vt = np.linalg.svd(centred, full_matrices=False)
    except np.linalg.LinAlgError:
        return None                  # a block that will not decompose falls back, and is counted
    proj = np.ascontiguousarray(vt[:rank])
    coords = centred @ proj.T
    cnorm = np.linalg.norm(coords, axis=1)
    if not bool((cnorm > 1e-12).any()):
        return None  # a fully degenerate block (identical children) FALLS BACK to the incumbent
        # score - zero-scoring every child would erase real global cosines (the P27 verify's
        # degenerate-block finding, cured narrow as found)
    return mu, proj, coords, cnorm


def _block_cosines(entry: tuple[Any, Any, Any, Any], qraw: Any) -> Any:
    """D3: the projected cosine of the RAW query against every child of one block, inside that
    block's own subspace. The query is mean-removed by the BLOCK's mean before rotation - the
    renormalization is applied to both sides or it is not a renormalization. A zero-norm
    projection (a query, or a child, with no component in the retained subspace) scores 0.0
    rather than dividing."""
    import numpy as np
    mu, proj, coords, cnorm = entry
    qp = proj @ (qraw - mu)
    qn = float(np.linalg.norm(qp))
    out = np.zeros(coords.shape[0], dtype="float32")
    if qn > 1e-12:
        den = cnorm * qn
        live = den > 1e-12
        if live.any():
            out[live] = (coords[live] @ qp) / den[live]
    return out


# --- the pooling cure: within-block quantile calibration of the level pool --------------------
# RUL-20260823-quantile-pool-confirmed, and it exists because of ONE measured disease
# (SCORE-20260823-P27-run1): the level pool is a comparison ACROSS BLOCKS, and the scores it
# compares are not commensurable. A projected block's cosines run 0.95-0.999 - low-rank projection
# inflates overlap mechanically, and mean-removal of a tight child set leaves shared directions
# near unity - while a fallback block's global cosines run 0.64-0.76. Pooled together at 3-5 mixed
# levels per query the beam took the projected branch nearly always and the descent renormalized
# itself into the wrong subtree wholesale: 8 of 9 incumbent hits destroyed.
#
# THE CURE IS SCALE-FREE AND MINTS NO DIAL. Each block's children are mapped to their QUANTILE
# POSITION inside their own block before the pool ranks them: order-preserving within a block,
# commensurable across blocks by construction, and forward-compatible with the organ era's
# per-grade scoring forms (whatever a form's scale, its quantiles are the same object). The
# alternatives were dismissed with ratification - all-projected-or-none is blunt exactly where the
# seam is sharpest, and concentration-rescaling mints the dial class the retired global metric M
# was killed to be rid of.
#
# THE TWO RIDERS THAT BIND (both built here, neither optional):
#   (i)  TIE DEGENERACY. Within-block quantiles at small n are coarse and EVERY block's top child
#        maps to 1.0, so the beam meets a k-way tie at the top. The tiebreak is named and is not a
#        new dial: inherited path heat, the incumbent's own g-term (see :func:`frontier_order`'s
#        ``inherited``). The run row serves a tie count per level.
#   (ii) each block's raw score RANGE (max - min) rides the result as a DIAGNOSTIC list - it says
#        how much dynamic range the calibration was handed, and it never enters a score.
#
# THE HEAT DECISION, PINNED. Heat inherits from the CALIBRATED score when armed, because the
# calibrated score IS the serving score at that level - inheriting the raw score would re-import
# the incommensurability one level down, which is the disease this cures. The raw score still
# rides every served row as ``own_cos_raw``, so nothing is hidden by being calibrated.

def _pool_quantile_on() -> bool:
    """The calibration lever, READ AT CALL TIME - never captured at import. Only the exact string
    ``1`` arms it (guard (a): an arm flag is never a serving default), and unarmed the descent is
    the incumbent's, line for line."""
    import os
    return os.environ.get("LAPLACE_POOL_QUANTILE", "") == "1"


def _block_quantiles(scores: list[float]) -> list[float]:
    """One block's scores mapped to their within-block quantile positions, in the input's order.

    ``midrank / (n - 1)`` over the ascending order, midrank 0-based: the block's best child lands
    on 1.0, its
    worst on 0.0, and TIES SHARE THEIR MIDRANK quantile so the mapping never invents an ordering
    the scores did not carry. ``n == 1`` is 1.0 - a lone child IS its block's top, and the
    alternative (0.0, or a division by zero) would silently bury every childless-but-one block
    under every block that has siblings to be ranked against."""
    n = len(scores)
    if n == 1:
        return [1.0]
    # the quantile-wave verify's NaN finding: a NaN sorts arbitrarily and defeats the
    # exact-equality tie grouping - it pins to the bottom DETERMINISTICALLY instead,
    # scored 0.0 like any worst child (no live armed descent has produced one; the
    # guard exists so the first that does cannot serve an invented quantile).
    scores = [(-float("inf") if s != s else s) for s in scores]
    order = sorted(range(n), key=lambda i: scores[i])
    out = [0.0] * n
    denom = float(n - 1)
    i = 0
    while i < n:
        j = i
        while j + 1 < n and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        q = ((i + j) / 2.0) / denom          # the tie's shared 0-based midrank, normalized
        for k in range(i, j + 1):
            out[order[k]] = q
        i = j + 1
    return out


# ---------------------------------------------------------------------------
# the route - cosine-guided descent, level-pooled, salience-merged
# ---------------------------------------------------------------------------

def route(repo_root: Path | str, net: dict[str, Any], goal: str, limit: int = 10,
          beam: int = BEAM, per_branch_width: int = PER_BRANCH_WIDTH,
          path_decay: float = PATH_DECAY, use_metric: bool = True,
          backend: Any = None, expand_failure_shaped: bool = True,
          mass_policy: dict[str, Any] | None = None,
          metric_override: Any = None, record_proposals: bool = False) -> dict[str, Any] | None:
    """The ring with geometry as the criterion: descend from the apex; at each level score ALL
    candidate children by cosine (one dot product each - the wire was laid at fold time), pool
    the level, expand the top ``beam`` internal nodes, accumulate every leaf into the hit pool.

    A node's heat is PATH-INHERITED: ``g = max(own cosine, path_decay * g(reached-through))`` -
    a coarse handle that matches the pull speaks for what it holds (the conceptric's bet), so a
    member of a hot cluster is recovered at near the cluster's heat, not its bare leaf cosine
    (``recall-through-reconstruction-not-grep``: descent scoring, not flat scoring with pruning).
    Salience = min-max over everything the pull touched; the reported path is the DESCENT trace
    (how the pull actually reached the hit). Returns the recall shape (files/visited/total) +
    per_grade_direct (each grade's own top hits, for the merge) - or None when no model is
    available (the caller falls back to the lexical ring, marked).

    ``beam`` / ``per_branch_width`` / ``path_decay`` ARE the reconstruction geometry - the pull's
    depth appetite, its survey width per shard, and how far a handle speaks for its members. The
    module constants are the standing defaults; a caller (the cockpit's live controls) may turn
    them per fire, so tuning the geometry is the SAME call the engine makes - never view math.

    THE PROVENANCE QUESTION, RULED BY MEASUREMENT (WO-20260820-route-descent-provenance, 2026-08-20).
    ``recursive_read``'s frontier was cured of provenance starvation with ``SELECT_POLICY``
    (``canonical_boost`` 0.08, ``evidence/DESCENT_PROVENANCE_2026-08-20/``), and the row asked
    whether the same term belongs on THIS descent, which inherits heat down the path and carries no
    provenance term at all. Measured on the same 25 paper slug queries against the live network
    (25 x ``route(limit=10)``, then the four misses re-pulled at ``limit=4000`` to rank the whole
    pool): route lands 21 of 25. The two findings that decide it:

      * THE SHAPE IS NOT THE SAME ONE. Derivative roots take 21 of the 250 returned hits;
        ``collaborator_corpus`` takes 90, and the mass immediately above a miss is largely ``::``
        nested lens-claimed sub-nodes.
      * SO THE RULED TERM WOULD MAKE IT WORSE, NOT BETTER. ``CANONICAL_ROOTS`` includes
        ``collaborator_corpus/`` and ``concept_corpus/``, so ``canonical_boost`` lifts precisely the
        nodes that are doing the crowding here. Transplanting it is not a cure pointing the same
        way; it is the disease amplified.

    RULING (unchanged): the second descent is DESIGN - it fires only on distress-shaped phrasing
    (0 of the 25 bench queries triggered ``_failure_shaped_rephrase``), and its merge is
    max-per-candidate, so it can only add. ``SELECT_POLICY`` does not belong here.

    SUPERSEDED IN ONE PART, 2026-08-21 (WO-20260821-route-frontier-mass-term). That lane read the
    ``::`` mass above the misses as RANK DILUTION and rowed a mass term for it. Built and swept,
    the mass term is refuted: every variant lands the incumbent exactly, because the misses were
    never REACHED - 1 of 27 and 1 of 34 family members in the pool, and the one that was there is a
    connectome node shared with other families, not the paper's own. The real defect was one level
    up and is now fixed: the apex is 9 lens branches against a beam of 8, every drop was a
    path-inheritance TIE, and the alphabet chose. See ``MASS_POLICY`` above and
    ``evidence/ROUTE_MASS_TERM_2026-08-21/``.

    ``expand_failure_shaped`` (default on) is the dream-audit fix: when ``goal`` matches
    ``_FAILURE_SHAPE_RE`` (distress vocabulary - "missing", "unavailable", "refused", ...), the
    descent ALSO runs a mechanically-derived provisioning-shaped rephrase of the same query, and
    the two candidate pools merge by max-score-per-candidate (a node keeps whichever query
    surfaced it hotter). Every merged hit's ``why`` carries which variant won it. When the
    detector doesn't fire, this is a no-op - the single-query descent below runs unchanged.

    THE P27 ARM (``LAPLACE_BLOCK_RENORM=1``, default OFF). Under the flag every expanded node's
    candidate children are scored by BLOCK-LOCAL RENORMALIZED overlap instead of global cosine:
    the block mean is removed from children and query, both are rotated into the block's own
    retained subspace at the fold's declared chi, and the projected cosine decides. Small blocks
    fall back to the incumbent score. The mechanism, its five ruled decisions and the mixed-level
    seam it accepts are documented at ``_block_renorm_on`` above; under the flag the result gains
    a ``block_renorm`` report and nothing else about the descent moves.

    THE QUANTILE POOL (``LAPLACE_POOL_QUANTILE=1``, default OFF) is the CURE for the seam that arm
    measured. Armed, every expanded node's children are mapped to their within-block quantile
    before the level pool ranks them, projected and fallback blocks alike, so the pooled comparison
    and the beam run on commensurable numbers; heat inherits the calibrated score and the raw one
    rides each row as ``own_cos_raw``. The mechanism and its two riders are documented at
    :func:`_pool_quantile_on` above; under the flag the result gains a ``pool_quantile`` report.
    The two levers are INDEPENDENT and compose - that composition is the whole point, since it is
    what makes a projected block and a fallback block poolable in one comparison."""
    import numpy as np
    backend = backend or get_backend()
    if backend is None:
        return None
    # the basis, not a rebuild: `basis` memoises the whole store per process on a key covering
    # every input staleness is drawn from, and hands back rows of one float32 matrix - so the
    # second and later fires in a process pay a stamp check instead of a 16 MB re-read
    # (WO-20260821-route-basis-memo).
    bas = basis(repo_root, net, backend)
    vecs = bas["vectors"]
    M = (metric_override if metric_override is not None else load_metric(repo_root)) if use_metric else None
    nodes = net["nodes"]
    policy = dict(mass_policy) if mass_policy is not None else dict(MASS_POLICY)
    root = net.get("root", "")
    renorm = _block_renorm_on()                # the P27 arm flag, read once per fire, at call time
    poolq = _pool_quantile_on()                # the calibration lever, same posture, independent
    # THE BLOCK-BASIS MEMO rides the BASIS dict itself rather than a module slot of its own. That
    # is what makes it per-process (the basis is memoised per process) AND unable to outlive the
    # vectors it was fit on: a basis re-derived on a moved store brings an empty memo with it, so
    # no block can ever be scored in a subspace fit on vectors the router has moved past. The key
    # is (node id, its exact candidate-child tuple) - an exact key, which a digest could not be.
    block_memo: dict[tuple[str, tuple[str, ...]], Any] = \
        bas.setdefault("_block_renorm_memo", {}) if renorm else {}
    renorm_report = {"blocks_projected": 0, "blocks_fallback": 0, "mixed_levels": 0}
    # M4: the banked-frame read (organ v1). None unless BOTH flags arm - the organ rides
    # the renorm arm's seam and changes nothing about arming semantics (defaults are M6's).
    organ_residual_armed = _organ_residual_on()
    frames_read = (_organ_frames(repo_root)
                   if (renorm or organ_residual_armed or _organ_cprime_on()
                       or _organ_bmatched_on()) else None)
    organ = frames_read if renorm else None
    organ_report: dict[str, Any] = {"served": 0, "fallback_by_cause": {
        "no_key": 0, "stale_isometry": 0, "degenerate": 0, "torn": 0}}
    if organ is not None:
        renorm_report["organ"] = organ_report   # the counts ride the served report (the
        # judge's bar: three causes plus torn, BY CAUSE, never one folded number)
    # THE FORK ARM (organ-residual): frames as a within-block coherence gate over untouched
    # incumbent scores. Its own report, its own venue mark; every skip counted by cause.
    organ_res = frames_read if organ_residual_armed else None
    organ_res_report: dict[str, Any] = {"blocks_gated": 0, "children_demoted": 0,
                                        "skipped_by_cause": {"no_key": 0, "stale_isometry": 0,
                                                             "degenerate": 0, "torn": 0,
                                                             "too_small": 0}}
    # C-PRIME (the seal's arm): posture-exclusive with the residual gate - the harness
    # enforces it and this belt makes a double-arm serve plainly as residual-only.
    organ_bmatched_armed = _organ_bmatched_on() and not (_organ_cprime_on()
                                                          or organ_residual_armed)
    organ_cprime_armed = (_organ_cprime_on() and not organ_residual_armed
                          and not organ_bmatched_armed)
    if _organ_cprime_on() and organ_residual_armed:
        print("embed_router: ORGAN_CPRIME ignored - ORGAN_RESIDUAL is armed (postures are "
              "exclusive; the fair-test harness owns arm composition)", flush=True)
    if (organ_cprime_armed or organ_bmatched_armed) and frames_read is None:
        frames_read = _organ_frames(repo_root)
    organ_cp = frames_read if organ_cprime_armed else None
    organ_bm = frames_read if organ_bmatched_armed else None
    organ_bm_report: dict[str, Any] = {"blocks_scored": 0, "children_scored": 0,
                                       "skipped_by_cause": {"no_key": 0, "stale_isometry": 0,
                                                            "degenerate": 0, "torn": 0,
                                                            "too_small": 0}}
    organ_cp_report: dict[str, Any] = {"blocks_scored": 0, "children_scored": 0,
                                       "skipped_by_cause": {"no_key": 0, "stale_isometry": 0,
                                                            "degenerate": 0, "torn": 0,
                                                            "too_small": 0}}
    # both reports ACCUMULATE across the descents one fire runs (the failure-shaped expansion runs
    # a second one), exactly as the renorm report does - a per-level entry is per level PER DESCENT.
    pool_report: dict[str, Any] = {"blocks_calibrated": 0, "tie_count_per_level": [],
                                   "block_ranges": [],
                                   "rank_term": "geomean_path_q (pool rank; trailing id is determinism, not ranking)"}

    def _embed_query(text: str) -> tuple[Any, str, Any]:
        v = np.asarray(backend.query(text), dtype="float32")
        if M is not None and M.shape[0] == v.shape[0]:    # variant of the comparison fire
            return v @ M, backend.name + "+M", v          # s(q,v) = q'Mv - the trained metric
        return v, backend.name, v                         # (third: the RAW query - D3's block side)

    def _descend(qv: Any, qraw: Any) -> tuple[dict[str, float], dict[str, float],
                                              dict[str, str], dict[str, float],
                                              dict[str, float]]:
        """One query's cosine-guided descent - own cosine, path-inherited heat, descent trace.
        Factored out so the failure-shaped expansion below can run it a second time, on the
        rephrase, without duplicating the frontier mechanics.

        ``qv`` is the SERVING query (``q'M`` when the metric is on); ``qraw`` is the same query
        before the metric, and is what a projected block scores against - D3 bars M from the
        rotated subspace. With the arm disarmed ``qraw`` is never read.

        Returns ``(own, heat, came, raw)``. ``own`` is the SERVING score - the within-block
        quantile under the calibration lever, the raw overlap otherwise - and ``raw`` is the
        uncalibrated overlap that fed it. Unarmed the two are THE SAME DICT, so the incumbent pays
        nothing for a distinction it does not have."""
        own_l: dict[str, float] = {}
        raw_l: dict[str, float] = {} if poolq else own_l   # aliased when unarmed: one dict, one law
        heat_l: dict[str, float] = {}
        came_l: dict[str, str] = {}
        inh_l: dict[str, float] = {}     # rider (i): the inherited g-term along the winning path
        pq_l: dict[str, tuple[float, int]] = {}  # the pool-rank ruling: (product, count) of the
        # winning path's per-level CALIBRATED scores - the geomean's accumulator; the apex
        # contributes no factor (it has no block above it, the ruled apex seam)
        expanded_l: set[str] = set()
        rv = vecs.get(root)
        heat_l[root] = own_l[root] = float(qv @ rv) if rv is not None else 0.0
        raw_l[root] = own_l[root]        # a no-op when aliased; the apex has no block above it
        if poolq:
            pq_l[root] = (1.0, 0)
        frontier = [root]
        depth = 0

        def block_of(nid: str, cands: list[str], level: int) -> dict[str, float] | None:
            """One block's projected child scores, or ``None`` when the block falls back (D4).
            The basis is query-independent, so the memo makes the second query in a process pay
            two matvecs where the first paid an SVD.

            M4 (organ v1, behind LAPLACE_ORGAN_V1=1 riding the renorm arm): the BANKED
            fold-time frame serves first when one exists for this node; every miss falls
            back to the incumbent serve-time SVD with its CAUSE counted (no_key /
            stale_isometry / degenerate / torn - the judge's bar). No equivalence between
            the two bases is claimed here; the A/B adjudicates with the churn stamp."""
            key = (nid, level, tuple(cands), organ is not None)  # the arm rides the key: an
            # organ-served entry and an SVD entry are different objects even for the same
            # block (LEVEL rides it too: chi(1)=16 vs deep=8, and 15,926 multi-parent edges
            # make the same block reachable at two depths in one process - without level,
            # whichever rank built first would serve both; the P27 verify's latent defect).
            if key in block_memo:
                entry = block_memo[key]
            else:
                entry = None
                if organ is not None:
                    cause = None
                    if organ["torn"]:
                        cause = "torn"
                    elif nid in organ["refused"]:
                        cause = "degenerate"
                    elif nid not in organ["frames"]:
                        cause = "no_key"
                    elif organ["stale"]:
                        cause = "stale_isometry"
                    if cause is None:
                        f = organ["frames"][nid]
                        Qb, mu_b = f["Q"], f["mu"]
                        centred = np.stack([vecs[c] for c in cands]) - mu_b
                        coords = centred @ Qb
                        cnorm = np.linalg.norm(coords, axis=1)
                        if bool((cnorm > 1e-12).any()):
                            entry = (mu_b, np.ascontiguousarray(Qb.T), coords, cnorm)
                            organ_report["served"] += 1
                        else:   # the live guard _block_basis applies to its own fits,
                            cause = "degenerate"   # applied equally to a banked frame
                    if entry is None:
                        organ_report["fallback_by_cause"][cause] += 1
                if entry is None:
                    entry = _block_basis(np.stack([vecs[c] for c in cands]), _block_chi(level))
                block_memo[key] = entry
            if entry is None:
                return None
            return dict(zip(cands, _block_cosines(entry, qraw).tolist(), strict=True))

        while frontier:
            level: list[str] = []
            lvl_projected = lvl_fallback = 0
            for nid in frontier:
                expanded_l.add(nid)
                g_par = heat_l.get(nid, 0.0)
                members = nodes.get(nid, {}).get("members", [])
                block: dict[str, float] | None = None
                if renorm:
                    # D1: the block IS this node's candidate children, read off the basis matrix -
                    # nothing deeper, nothing new. `depth + 1` is the children's level, the same
                    # rung the fold calls level 1 when it splits the root.
                    cands = [m for m in members if m in nodes and vecs.get(m) is not None]
                    if cands:                     # a childless expansion is no block at all
                        block = block_of(nid, cands, depth + 1)
                        if block is None:
                            lvl_fallback += 1
                            renorm_report["blocks_fallback"] += 1
                        else:
                            lvl_projected += 1
                            renorm_report["blocks_projected"] += 1
                # PASS ONE - score this block's children. Split from the heat pass below because
                # a quantile is a property of the WHOLE block: no child's calibrated score exists
                # until every child's raw score does. Unarmed the split is invisible - scoring one
                # child never touched another child's heat, and the order is unchanged.
                kids: list[str] = []
                assigned_here: list[str] = []
                for m in members:
                    if m not in nodes:
                        continue
                    if m not in raw_l:
                        if block is not None and m in block:
                            raw_l[m] = block[m]   # the local overlap, renormalized (D3)
                        else:
                            v = vecs.get(m)
                            if v is None:
                                continue
                            raw_l[m] = float(qv @ v)
                        assigned_here.append(m)   # first-score-wins: only this block's own
                    kids.append(m)                # assignments are demotable by its frame
                if organ_res is not None and assigned_here:
                    _organ_residual_gate(nid, assigned_here, vecs, raw_l,
                                         organ_res, organ_res_report)
                if organ_cp is not None and assigned_here:
                    _organ_cprime_score(nid, assigned_here, vecs, raw_l, qraw,
                                        organ_cp, organ_cp_report)
                if organ_bm is not None and assigned_here:
                    bm_members = [m for m in members
                                  if m in nodes and vecs.get(m) is not None]
                    if bm_members:
                        _organ_bmatched_score(
                            nid, assigned_here,
                            np.stack([vecs[m] for m in bm_members]), vecs, raw_l,
                            qraw, organ_bm, _block_chi(depth + 1), organ_bm_report)
                if poolq and kids:
                    # the calibration, applied to EVERY block this level expands - projected and
                    # fallback alike, which is the composition's whole point. First-score-wins
                    # holds for the calibrated score exactly as it holds for the raw one: a node
                    # already reached keeps the score its own first block gave it.
                    uniq = list(dict.fromkeys(kids))
                    raws = [raw_l[m] for m in uniq]
                    pool_report["blocks_calibrated"] += 1
                    pool_report["block_ranges"].append(round(max(raws) - min(raws), 6))
                    for m, q in zip(uniq, _block_quantiles(raws), strict=True):
                        if m not in own_l:
                            own_l[m] = q
                # PASS TWO - the heat, from the SERVING score (calibrated when armed, per the
                # pinned decision: inheriting a raw score under calibration would re-import the
                # incommensurability one level down).
                for m in kids:
                    g = max(own_l[m], path_decay * g_par)
                    if g > heat_l.get(m, -1.0):
                        heat_l[m] = g
                        came_l[m] = nid
                        if poolq:             # the tiebreak's term, banked only where it is read
                            inh_l[m] = path_decay * g_par
                            pp, pn = pq_l.get(nid, (1.0, 0))
                            pq_l[m] = (pp * own_l[m], pn + 1)
                    level.append(m)
            if lvl_projected and lvl_fallback:
                # R2's seam, counted where it actually happens: this level's pool ranks projected
                # cosines against global scores in ONE comparison. Named, not blunted.
                renorm_report["mixed_levels"] += 1
            internal = frontier_order(
                {m for m in level if not nodes[m].get("leaf", True)} - expanded_l,
                own_l, heat_l, policy, inherited=inh_l if poolq else None)
            if poolq:
                # rider (i)'s meter, read where the tie actually costs: how many of THIS level's
                # ranked candidates share their served heat with another candidate. Exact equality
                # is the right test - the degeneracy is bit-identical (every block's top child is
                # 1.0), never merely close.
                seen_h: dict[float, int] = {}
                for m in internal:
                    h = heat_l.get(m, 0.0)
                    seen_h[h] = seen_h.get(h, 0) + 1
                pool_report["tie_count_per_level"].append(
                    sum(c for c in seen_h.values() if c > 1))
            # LEVEL ZERO HAS NO HANDLE ABOVE IT TO PRUNE ON. The apex members are the mind's
            # LENSES, not candidates inside a topic - dropping one does not narrow a search, it
            # removes a projection of the self from the query's world. ``recursive_read.descend``
            # already states this law for the root's direct LEAVES ("they are level zero and have
            # no handle above them to prune on"); this is the same law for the root's CLUSTERS.
            width = len(internal) if (depth == 0 and policy.get("apex", "whole") == "whole") \
                else beam
            frontier = frontier_select(nodes, internal, heat_l, width, policy)
            depth += 1
        geo_l = ({m: (p ** (1.0 / n) if n else 0.0) for m, (p, n) in pq_l.items()}
                 if poolq else {})
        return own_l, heat_l, came_l, raw_l, geo_l

    qv, router_name, qraw = _embed_query(goal)
    if renorm:
        # the P27 verify's run-row hazard: an armed run whose served scores are metric-free
        # projected cosines must not label itself a plain +M serving - the router field is
        # what run rows bank, and a mislabeled venue is the referent-class disease again.
        router_name += "+blockR"
        if organ is not None:
            router_name += "+organV1"   # banked frames MAY serve this fire: the venue says so
            # (the same run-row law; the organ counts in block_renorm.organ say how much)
    if organ_res is not None:
        router_name += "+organR"        # the fork arm is armed: the venue says so (same law)
    if organ_cp is not None:
        router_name += "+organC"        # the seal's arm is armed: the venue says so
    if organ_bm is not None:
        router_name += "+organBM"       # amendment 6's arm: coverage-matched serve-time basis
    if poolq:
        # the same run-row hazard the P27 verify banked: an armed run's served scores are
        # calibrated quantiles, not cosines, and the router field is what run rows bank. A
        # mislabeled venue is the referent-class disease again.
        router_name += "+poolQ"
    own, heat, came, raw, geo = _descend(qv, qraw)

    # the expansion: fires only on distress-shaped phrasing, merges by max-score-per-candidate,
    # and marks every node the rephrase actually won with which variant surfaced it. A node only
    # the original query reached (or reached hotter) keeps its original attribution untouched -
    # this can only ADD candidates/heat relative to the un-expanded pool, never remove them.
    rephrase = _failure_shaped_rephrase(goal) if expand_failure_shaped else None
    surfaced_by: dict[str, str] = {}
    if rephrase is not None:
        qv2, _, qraw2 = _embed_query(rephrase)
        own2, heat2, came2, raw2, geo2 = _descend(qv2, qraw2)
        # sorted(): the union's iteration order must not depend on PYTHONHASHSEED - a venue
        # whose whole-result digest varies by hash seed cannot serve reproducible run rows
        # for distress-shaped queries (WO-20260823-route-merge-determinism, the quantile
        # verifier's three-seed measurement).
        for nid in sorted(set(heat) | set(heat2)):
            if nid == root:
                continue
            h1, h2 = heat.get(nid), heat2.get(nid)
            if h2 is not None and (h1 is None or h2 > h1):
                heat[nid], own[nid] = heat2[nid], own2.get(nid, own.get(nid, 0.0))
                if poolq:
                    geo[nid] = geo2.get(nid, geo.get(nid, 0.0))
                if poolq:      # the raw score travels WITH the serving score it produced, always
                    raw[nid] = raw2.get(nid, raw.get(nid, 0.0))
                came[nid] = came2.get(nid, came.get(nid, ""))
                surfaced_by[nid] = "expanded"
            else:
                surfaced_by[nid] = "original"

    scored = {m: g for m, g in heat.items() if m != root}
    if not scored:
        empty = {"query": goal, "router": router_name, "visited": 0, "total": len(nodes),
                  "files": [], "per_grade_direct": {}, "proposals": [],
                  "geometry": {"beam": int(beam), "per_branch_width": int(per_branch_width),
                               "path_decay": float(path_decay), "limit": int(limit),
                               "mass_policy": dict(mass_policy or MASS_POLICY)}}
        if rephrase is not None:
            empty["failure_shape_expansion"] = rephrase
        if renorm:                    # under the flag only; the incumbent result shape is untouched
            empty["block_renorm"] = dict(renorm_report)
        if organ_res is not None:     # the fork arm's counts: served under its flag only
            empty["organ_residual"] = dict(organ_res_report)
        if organ_cp is not None:
            empty["organ_cprime"] = dict(organ_cp_report)
        if organ_bm is not None:
            empty["organ_bmatched"] = dict(organ_bm_report)
        if poolq:
            empty["pool_quantile"] = dict(pool_report)
        return empty
    lo, hi = min(scored.values()), max(scored.values())
    span = (hi - lo) or 1.0

    def norm(s: float) -> float:
        return round((s - lo) / span, 4)

    def path_of(nid: str) -> list[str]:
        chain = [nid]
        while chain[-1] in came and came[chain[-1]] not in chain:
            chain.append(came[chain[-1]])
        return list(reversed(chain))

    # The hit pool is ACT-SUFFICIENT (reconstruction-descends-never-into-substrate): every reached
    # node below the mind overlay competes at its own handle, and a node YIELDS to its tree parent
    # when its own cosine did not beat the parent's heat - by the router's own evidence the handle
    # already speaks for it (the converse of path inheritance). A node that out-pulls its parent
    # earns substrate recovery; a generic pull recovers handles. The same rule at every grade -
    # no kinds, no caps, no special cases (the N28 fold's principle, recursive). Leaf-only pooling
    # died the day the verbatim floor landed: 398 record atoms flooded the standing recall and the
    # hello gate caught it at 1/5 - this collapse is the general cure.
    pool = {m: g for m, g in scored.items() if not m.startswith("mind://")}
    ranked = frontier_mass_rank(nodes, pool, own, heat, policy, floor=lo,
                                pool_rank=geo if poolq else None)
    top = ranked[:limit]

    # the why-handle: GEOMETRY MAY FIND, THE GRAPH MUST EXPLAIN (his invariant, 2026-06-10).
    # Every hit carries its own evidence: bare cosine vs inherited heat vs the lexical overlap
    # the symbolic layer can show. A hit the graph cannot explain is a GEOMETRIC-ONLY find -
    # surfaced, and banked as a wire-proposal for the dream's audit (a missing wire to lay, or
    # a confabulated association to refuse - never silently trusted).
    from laplace.pipeline.canon import _tokenize
    q_tok = _tokenize(goal)
    ql = goal.lower().strip()

    def why_of(nid: str, g: float, raw_heat: float) -> dict[str, Any]:
        node = nodes.get(nid, {})
        sym = set(node.get("keywords") or []) | set(node.get("coverage") or [])
        lex = sorted(q_tok & sym)[:8]
        via = came.get(nid)
        why: dict[str, Any] = {"own_cos": round(own.get(nid, 0.0), 4), "heat": round(raw_heat, 4),
                               "via": via, "via_heat": round(heat.get(via, 0.0), 4) if via else None,
                               "lexical": lex,
                               "geometric_only": not lex and not (ql and ql in nid.lower())}
        if poolq:               # rider: the uncalibrated overlap is never hidden by being calibrated
            why["own_cos_raw"] = round(raw.get(nid, 0.0), 4)
        if g != raw_heat:       # the lateral attenuation actually moved this hit - show the mechanism
            why["mass_adjusted"] = round(g, 4)
        if rephrase is not None:                        # additive: only present when expansion ran
            why["surfaced_by"] = surfaced_by.get(nid, "original")
        return why

    files = [{"file": nid, "score": norm(g), "cos": round(own.get(nid, 0.0), 4),
              "path": path_of(nid), "why": why_of(nid, g, raw_g)} for nid, g, raw_g in top]
    # only a CONFIDENT unexplained find is a proposal - a low-salience stray is just the tail
    # of the pull, not evidence of a missing wire.
    proposals = [{"query": goal, "id": f["file"], "cos": f["cos"], "heat": f["why"]["heat"],
                  "via": f["why"]["via"]}
                 for f in files if f["why"]["geometric_only"] and f["score"] >= PROPOSAL_FLOOR]
    if proposals and record_proposals:
        try:
            with (Path(repo_root) / PROPOSALS_FILE).open("a", encoding="utf-8") as fh:
                for p in proposals:
                    p.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
                    fh.write(json.dumps(p, ensure_ascii=False) + "\n")
        except OSError:
            pass                                     # the ledger is best-effort; the payload still carries them

    # mind sharding's merge: every SHARD (apex branch) returns its own top-w per grade, and the
    # merge keeps each shard's local best even when another shard outshines it globally - the
    # standing shard's floor is never drowned by a richer shard's mass. w is the survey width.
    # Attribution: an apex member's DIRECT members belong to it by MEMBERSHIP, in apex order
    # (standing first - his ruling), never by the hottest path: max-heat attribution let the
    # self-record branch claim the standing five the day the verbatim floor landed, and the
    # hello gate caught their buckets stolen. Deeper nodes keep the descent-trace attribution
    # (they belong to whoever genuinely reached them).
    direct_of: dict[str, str] = {}
    for am in nodes.get(root, {}).get("members", []):
        for m in nodes.get(am, {}).get("members", []):
            direct_of.setdefault(m, am)

    def branch_of(nid: str) -> str:
        if nid in direct_of:
            return direct_of[nid]
        cur = nid
        while came.get(cur) is not None and came[cur] != root:
            cur = came[cur]
        return cur

    shards: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for nid, g in scored.items():
        gr = str(nodes[nid].get("grade", 0))
        shards.setdefault(gr, {}).setdefault(branch_of(nid), []).append(
            {"id": nid, "salience": norm(g)})
    per_grade_direct: dict[str, list[dict[str, Any]]] = {}
    for gr, branches in shards.items():
        merged: list[dict[str, Any]] = []
        for entries in branches.values():
            entries.sort(key=lambda x: -x["salience"])
            merged.extend(entries[:max(1, int(per_branch_width))])
        per_grade_direct[gr] = sorted(merged, key=lambda x: -x["salience"])
    result = {"query": goal, "router": router_name, "visited": len(scored),
              "total": len(nodes), "files": files, "per_grade_direct": per_grade_direct,
              "proposals": proposals,
              # the geometry this fire actually ran with - echoed so a view shows the mechanism's
              # own numbers, never its assumption of the defaults (view-equals-mechanism).
              "geometry": {"beam": int(beam), "per_branch_width": int(per_branch_width),
                           "path_decay": float(path_decay), "limit": int(limit),
                           "mass_policy": dict(policy)}}
    if rephrase is not None:                # additive: absent entirely when expansion didn't fire
        result["failure_shape_expansion"] = rephrase
    if renorm:                              # R1/R2's counts: served under the flag only
        result["block_renorm"] = dict(renorm_report)
    if organ_res is not None:               # the fork arm's counts: served under its flag only
        result["organ_residual"] = dict(organ_res_report)
    if organ_cp is not None:                # the seal's arm: same law
        result["organ_cprime"] = dict(organ_cp_report)
    if organ_bm is not None:                # amendment 6's arm: same law
        result["organ_bmatched"] = dict(organ_bm_report)
    if poolq:                               # the riders' meters: served under the lever only
        result["pool_quantile"] = dict(pool_report)
    return result


# ---------------------------------------------------------------------------
# the wire audit - the dream's adjudication of the geometric-only finds (N29)
# ---------------------------------------------------------------------------

VERDICTS_FILE = ".wire_verdicts.jsonl"          # every judgment banked (wire / grit / noise)
LEARNED_KEYWORDS_FILE = ".learned_keywords.json"  # accepted wires: node -> learned query tokens
# the one-operator gate: the wire-drain IS the route coefficient (validated AUC 0.978 wire>noise
# on the banked verdicts). These thresholds are zero-corruption on the 118 (0 noise->wire,
# 0 wire dropped); they are an F1 knob, tunable. The ambiguous middle escalates to a cheap jury.
WIRE_HI = 0.70
NOISE_LO = 0.50


def proposal_pairs(repo_root: Path | str) -> list[dict[str, Any]]:
    """Dedupe the proposal ledger to unique (query, id) pairs, max cos kept - exploratory play
    re-banks the same find on every fire, so the audit target is the pair set, never the raw
    line count (327 lines were 110 pairs from 15 queries on first count, 2026-06-11). Each pair
    also carries the EARLIEST ts seen across every line that ever proposed it (first-proposed
    time) - tracked independently of which line's cos wins the dedupe, so the winning entry
    never inherits a later re-fire's ts. bank_verdicts rewrites the frontier straight from this
    view, so a ts dropped here would be a ts erased on every drain; a ts-less legacy line simply
    leaves the pair without a ts key, never a fabricated one."""
    ledger = Path(repo_root) / PROPOSALS_FILE
    if not ledger.is_file():
        return []
    pairs: dict[tuple[str, str], dict[str, Any]] = {}
    earliest_ts: dict[tuple[str, str], str] = {}
    for ln in ledger.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            p = json.loads(ln)
        except ValueError:
            continue
        key = (p.get("query", ""), p.get("id", ""))
        ts = p.get("ts")
        if ts and (key not in earliest_ts or ts < earliest_ts[key]):
            earliest_ts[key] = ts
        cur = pairs.get(key)
        if cur is None or (p.get("cos") or 0) > (cur.get("cos") or 0):
            pairs[key] = {"query": key[0], "id": key[1], "cos": p.get("cos"),
                          "heat": p.get("heat"), "via": p.get("via")}
    out = [{**entry, "ts": earliest_ts[key]} if key in earliest_ts else entry
           for key, entry in pairs.items()]
    return sorted(out, key=lambda x: (x["query"], x["id"]))


def audit_briefs(repo_root: Path | str, net: dict[str, Any],
                 pairs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """One judgment brief per pair - a RECONSTRUCTION of the atom's local environment at its
    grade, not a flat handle (his correction 2026-06-13: the juror is a sealed sub-Eigen and must
    reconstruct itself - see the local frame, or it cannot tell a real miss from a surface
    accident). Each brief carries: the node's own essence + keywords, its ANCESTRY (identity_chain
    - which generators/clusters it belongs to, the grade above) and its NEIGHBOURS (lateral
    siblings - the cluster-mates around it). The juror then judges whether the query belongs in
    THIS neighbourhood. Sealed nodes contribute only content-free essences by construction - the
    local frame never holds soul content. ``pairs`` overrides the frontier (for re-judging banked
    pairs against the richer brief)."""
    from laplace.engine import conceptric
    nodes = net["nodes"]
    briefs = []
    for p in (pairs if pairs is not None else proposal_pairs(repo_root)):
        nid = p["id"]
        node = nodes.get(nid)
        local: dict[str, Any] = {}
        if node is not None:
            chain = conceptric.identity_chain(net, nid)
            local["ancestry"] = [{"id": a["id"], "grade": a["grade"],
                                  "essence": conceptric.essence(repo_root, net, a["id"])}
                                 for a in chain[:4] if a["id"] in nodes]
            sibs = conceptric.lateral(net, nid, width=6, conjectural=True, scope="siblings")
            local["neighbours"] = [{"id": s["id"],
                                    "essence": conceptric.essence(repo_root, net, s["id"])}
                                   for s in sibs]
        briefs.append({**p,
                       "known": node is not None,
                       "grade": node.get("grade") if node else None,
                       "essence": conceptric.essence(repo_root, net, nid) if node else "(gone)",
                       "keywords": sorted(node.get("keywords") or [])[:12] if node else [],
                       "via_essence": conceptric.essence(repo_root, net, p["via"])
                       if p.get("via") in nodes else None,
                       "local": local})
    return briefs


def _brief_source_ids(brief: dict[str, Any]) -> list[str]:
    """The exact local frame whose rows produced one jury brief."""
    local = brief.get("local") or {}
    ids = {str(brief.get("id") or "")}
    if brief.get("via"):
        ids.add(str(brief["via"]))
    for section in ("ancestry", "neighbours"):
        ids.update(str(row.get("id") or "") for row in local.get(section) or [])
    return sorted(i for i in ids if i)


def _brief_fingerprint(pair: dict[str, Any], source_ids: list[str],
                       node_hashes: dict[str, str]) -> str:
    """Hash the pair and every canonical node row its local reconstruction consumed."""
    fields = {k: pair.get(k) for k in ("query", "id", "cos", "heat", "via", "ts")}
    payload = {"pair": fields,
               "sources": [(nid, node_hashes.get(nid, "(missing)")) for nid in source_ids]}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def audit_briefs_incremental(repo_root: Path | str, net: dict[str, Any],
                             cached: list[dict[str, Any]] | None = None,
                             pairs: list[dict[str, Any]] | None = None,
                             ) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Rebuild only jury briefs whose pair or reconstructed local frame moved.

    ``.escalate_briefs.json`` is a projection, never a store.  Its prior rows may
    therefore be reused only with a source receipt: the pair fields plus hashes
    of the node, via, ancestry, and neighbour rows that produced the brief.  A
    parent membership change changes the parent row hash; a re-parenting changes
    the leaf row hash.  Old briefs without a receipt are rebuilt once.
    """
    current = pairs if pairs is not None else proposal_pairs(repo_root)
    prior = {(b.get("query"), b.get("id")): b for b in (cached or [])}
    nodes = net.get("nodes") or {}

    # Hash only dependencies claimed by reusable candidates.  Rebuilt briefs add
    # their new dependencies below.  One node hash is shared across every brief.
    wanted = {nid for brief in prior.values() for nid in (brief.get("_source_ids") or [])}
    node_hashes = {
        nid: hashlib.sha256(json.dumps(nodes.get(nid), sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":"), default=str).encode()).hexdigest()
        for nid in wanted
    }
    reused: dict[tuple[str, str], dict[str, Any]] = {}
    rebuild_pairs: list[dict[str, Any]] = []
    for pair in current:
        key = (pair.get("query"), pair.get("id"))
        old = prior.get(key)
        source_ids = list((old or {}).get("_source_ids") or [])
        if (old and source_ids
                and old.get("_source_fingerprint")
                == _brief_fingerprint(pair, source_ids, node_hashes)):
            reused[key] = old
        else:
            rebuild_pairs.append(pair)

    rebuilt = audit_briefs(repo_root, net, pairs=rebuild_pairs) if rebuild_pairs else []
    for brief in rebuilt:
        source_ids = _brief_source_ids(brief)
        for nid in source_ids:
            if nid not in node_hashes:
                node_hashes[nid] = hashlib.sha256(
                    json.dumps(nodes.get(nid), sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), default=str).encode()).hexdigest()
        brief["_source_ids"] = source_ids
        brief["_source_fingerprint"] = _brief_fingerprint(brief, source_ids, node_hashes)

    by_key = {**reused, **{(b.get("query"), b.get("id")): b for b in rebuilt}}
    ordered = [by_key[(p.get("query"), p.get("id"))] for p in current]
    return ordered, {"total": len(current), "reused": len(reused), "rebuilt": len(rebuilt),
                     "dropped": max(0, len(prior) - len(reused) - len(rebuilt))}


def bank_verdicts(repo_root: Path | str, verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    """Bank the jury's verdicts and APPLY them mechanically. ``wire``: the association is real
    and the symbols missed it -> teach the symbols (the query's tokens join the node's learned
    keywords, so the graph explains the find forever after and it stops re-banking). ``grit``:
    interesting-but-unconfirmed -> kept in the verdict ledger, surfaced on ideation, never
    wired into recall (conjectural-links-are-creativity). ``noise``: a string accident -> the
    verdict is the record, nothing wired. The judged proposals leave the proposals ledger."""
    from laplace.pipeline.canon import _tokenize
    repo_root = Path(repo_root)
    counts = {"wire": 0, "grit": 0, "noise": 0}
    learned: dict[str, list[str]] = {}
    lk_path = repo_root / LEARNED_KEYWORDS_FILE
    if lk_path.is_file():
        try:
            learned = json.loads(lk_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            learned = {}
    with (repo_root / VERDICTS_FILE).open("a", encoding="utf-8") as fh:
        for v in verdicts:
            verdict = v.get("verdict")
            if verdict not in counts:
                continue
            counts[verdict] += 1
            v.setdefault("ts", datetime.now(timezone.utc).isoformat(timespec="seconds"))
            fh.write(json.dumps(v, ensure_ascii=False) + "\n")
            if verdict == "wire" and v.get("id"):
                toks = sorted(set(learned.get(v["id"], [])) | _tokenize(v.get("query", "")))
                if toks:
                    learned[v["id"]] = toks
    lk_path.write_text(json.dumps(learned, ensure_ascii=False, indent=1), encoding="utf-8")
    # the judged pairs leave the proposals ledger (it holds only the unjudged frontier)
    judged = {(v.get("query", ""), v.get("id", "")) for v in verdicts}
    remaining = [p for p in proposal_pairs(repo_root)
                 if (p["query"], p["id"]) not in judged]
    (repo_root / PROPOSALS_FILE).write_text(
        "".join(json.dumps(p, ensure_ascii=False) + "\n" for p in remaining), encoding="utf-8")
    return {**counts, "n_learned_nodes": len(learned), "n_remaining": len(remaining)}


def mechanical_gate(cos: float, hi: float = WIRE_HI, lo: float = NOISE_LO) -> str | None:
    """The wire-drain recurred as the one operator. A wire-proposal is a (query, node) edge the
    symbols could not explain; the route coefficient cos(query, node) that surfaced it also
    DECIDES it - it separates real edges from accidents at AUC 0.978 on the 118 banked verdicts.
    Returns 'wire' (cos>=hi, zero false positives in validation), 'noise' (cos<=lo, zero real
    edges lost), or None - the ambiguous middle, escalated to the jury. No model call: the
    coefficient is already banked in the proposal, so the gate is recoverable from the ledger."""
    if cos >= hi:
        return "wire"
    if cos <= lo:
        return "noise"
    return None


def _frontier_vectors(repo_root: Path | str, net: dict[str, Any], backend: Any,
                      ids: set[str]) -> dict[str, list[float]]:
    """Vectors for JUST the frontier-referenced node ids - the Gate-B narrowing (his ruling
    2026-07-13: the close pays only for what moved). The old ``mechanical_verdicts`` called the
    network-wide ``ensure_embeddings`` unconditionally, re-embedding most of ~11k nodes at fold
    cost even for an empty/tiny frontier; the wire phase was almost entirely that re-embed. Here
    the cache is read once, the ids that hit (content-hash match) are served from it, and the
    misses are batched into ONE ``backend.embed`` call (generalizing the old per-node fallback at
    the tail of mechanical_verdicts). READ-ONLY on the cache: it never rewrites .self_embeddings.json
    (a partial write keyed only by the frontier would clobber the whole network), so the vanished-node
    PRUNE is NOT performed here - it stays with ``ensure_embeddings``, called lazily by ``route()``
    (its other caller). Returned rows: a cache HIT is dequantized via ``_dequantize_entry`` (an
    approx-unit float vector, per-vector int8 round-trip; W6.2), a MISS is the backend's freshly
    embedded unit row - either way the caller unit-normalizes before the dot, exactly as the old
    path did."""
    repo_root = Path(repo_root)
    cache_path = repo_root / CACHE_FILE
    cached: dict[str, Any] = {}
    if cache_path.is_file():
        try:
            disk = json.loads(cache_path.read_text(encoding="utf-8"))
            if disk.get("backend") == backend.name:
                cached = disk.get("nodes", {})
        except (OSError, json.JSONDecodeError):
            cached = {}
    nodes = net["nodes"]
    digests = digest_essences(repo_root, net)   # once for the loop, not per frontier id
    out: dict[str, list[float]] = {}
    miss_ids: list[str] = []
    miss_texts: list[str] = []
    for nid in ids:
        txt = node_text(repo_root, net, nid, digests) if nid in nodes else nid
        ent = cached.get(nid)
        if ent is not None and ent.get("h") == _hash(backend.name, txt):
            out[nid] = _dequantize_entry(ent)
        else:
            miss_ids.append(nid)
            miss_texts.append(txt)
    if miss_ids:
        for nid, vec in zip(miss_ids, backend.embed(miss_texts), strict=True):
            out[nid] = vec
    return out


def mechanical_verdicts(repo_root: Path | str, net: dict[str, Any] | None = None,
                        hi: float = WIRE_HI, lo: float = NOISE_LO) -> list[dict[str, Any]]:
    """Apply the gate to the unjudged frontier. The route coefficient is RECOMPUTED against the
    current node embeddings, not read from the proposal's banked cos - the conceptric grows, so
    the fire-time cos drifts stale (~0.12 low), and the gate must use the same current signal the
    thresholds were validated on. The embedder is local + deterministic (no LLM); the recomputed
    cos is banked in each verdict, so the decision is frozen and replayable from .wire_verdicts.
    The None (escalate) pairs are left in the frontier for the jury.

    Gate B (his ruling 2026-07-13): only the node ids the frontier references are embedded/looked up
    - NOT the whole network. ``ensure_embeddings`` (and its network-wide prune) is no longer called
    here; the prune stays with ``route()``'s lazy call. For the same vectors the verdicts are
    byte-identical to the old path (only the set of vectors materialized narrowed)."""
    import numpy as np
    backend = get_backend()
    if backend is None:
        return []
    if net is None:
        from laplace.engine import conceptric
        net = conceptric.load_network(repo_root)
    pairs = proposal_pairs(repo_root)
    if not pairs:                                  # empty frontier -> nothing to embed, nothing to judge
        return []
    vecs = _frontier_vectors(repo_root, net, backend, {p["id"] for p in pairs})
    qcache: dict[str, np.ndarray] = {}

    def qv(q: str) -> "np.ndarray":
        if q not in qcache:
            qcache[q] = np.asarray(backend.query(q), dtype=np.float64)
        return qcache[q]

    out: list[dict[str, Any]] = []
    for p in pairs:
        nid = p["id"]
        nv = np.asarray(vecs[nid], dtype=np.float64)
        n = np.linalg.norm(nv)
        if n:
            nv = nv / n
        c = float(qv(p["query"]) @ nv)
        g = mechanical_gate(c, hi, lo)
        if g:
            rel, thr = (">=", hi) if g == "wire" else ("<=", lo)
            out.append({"query": p["query"], "id": nid, "verdict": g,
                        "method": "mechanical", "cos": round(c, 4),
                        "why": f"route coefficient {c:.3f} {rel} {thr:.2f} (one-operator gate)"})
    return out


def rebuild_learned_keywords(repo_root: Path | str, *, persist: bool = True) -> dict[str, list[str]]:
    """Reconstruct .learned_keywords.json as a PURE PROJECTION of the verdict ledger - replay
    every banked 'wire' verdict. The applied wire-state is a render of the recoverable trace, not
    a primary store (reconstruction-is-mechanical-render): the whole drain is mechanically
    recoverable by construction. Idempotent; the repair path if the index and the ledger drift."""
    from laplace.pipeline.canon import _tokenize
    repo_root = Path(repo_root)
    # LATEST verdict per (query, id) wins - a re-judgment supersedes the earlier one, so the index
    # is the projection of the ledger's final state (re-grading the jury on a richer brief cleanly
    # overrides a stale flat-brief verdict). The ledger keeps the full history; the index is now.
    final: dict[tuple[str, str], str] = {}
    led = repo_root / VERDICTS_FILE
    if led.is_file():
        for ln in led.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                v = json.loads(ln)
            except ValueError:
                continue
            if v.get("id"):
                final[(v.get("query", ""), v["id"])] = v.get("verdict")
    learned: dict[str, list[str]] = {}
    for (query, nid), verdict in final.items():
        if verdict == "wire":
            toks = sorted(set(learned.get(nid, [])) | _tokenize(query))
            if toks:
                learned[nid] = toks
    if persist:
        (repo_root / LEARNED_KEYWORDS_FILE).write_text(
            json.dumps(learned, ensure_ascii=False, indent=1), encoding="utf-8")
    return learned


def load_learned_keywords(repo_root: Path | str) -> dict[str, list[str]]:
    """The accepted wires: node id -> learned tokens. Merged into the network at load so the
    why-handle, the lexical channel and the embedding text all see them - the wire becomes
    symbol AND geometry (the node re-embeds, content-hashed).

    SELF-HEALING AT THE CONSUMER (WO-20260817-learned-keywords-selfheal, the thin-systems audit
    2026-08-17). The projection is gitignored, so on a fresh clone it is simply absent; nothing
    rebuilt it at load, and the close's own deposit skips the wire-drain in exactly the
    fresh-clone case (the frontier is empty because every proposal is already judged). So the
    accepted verdicts - which DO travel, in the tracked .wire_verdicts.jsonl - never reached the
    built network: the wire was banked and invisible. The repair belongs here, at the one
    consumer, because ``rebuild_learned_keywords`` is a PURE projection of that tracked ledger:
    offline, deterministic, idempotent, and it covers every entry point (wake, route, the ring,
    a local clone) instead of one producer's happy path."""
    p = Path(repo_root) / LEARNED_KEYWORDS_FILE
    if not p.is_file():
        if (Path(repo_root) / VERDICTS_FILE).is_file():
            try:
                return rebuild_learned_keywords(repo_root, persist=False)
            except (OSError, ValueError):
                return {}
        return {}
    try:
        out = json.loads(p.read_text(encoding="utf-8"))
        return out if isinstance(out, dict) else {}
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# entry - the explicit fold (the scanner and the ring call ensure/route lazily)
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    from laplace.engine import conceptric
    root = source_tree()
    backend = get_backend()
    if backend is None:
        print(json.dumps({"error": "no embedding backend (install the embed extra)"}))
        return 1
    net = conceptric.load_network(root)
    rep = ensure_embeddings(root, net, backend, bulk=True)  # the explicit fold IS the producer
    out = {"backend": backend.name, "n_embedded": rep["n_embedded"],
           "n_cached": rep["n_cached"], "n_total": rep["n_total"]}

    # LAW RIDER (WO-20260721-222252): a fresh-basis re-embed and the metric re-distill are ONE
    # producer act. The 2026-07-21 breach was a cold re-embed (d2843432) that left .metric_M.npz
    # predating the new basis - a stale metric the taste channel then had to skip. So whenever
    # THIS explicit fold actually changed the basis (new vectors embedded), re-distill M through
    # its OWN gate here, in the same producer step. Never fatal to the fold (the basis is already
    # written); the distill's gate decides shipping, and its verdict rides the output.
    if rep["n_embedded"] > 0:
        import contextlib
        import io

        from laplace.representation import metric_distill
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                metric_distill.main([])
            verdict = json.loads(buf.getvalue() or "{}")
            out["metric_redistill"] = {
                "ran": True, "shipped": bool(verdict.get("shipped")),
                "auc_identity": verdict.get("auc_identity"),
                "auc_trained": verdict.get("auc_trained"),
                "hello_gate": verdict.get("hello_gate")}
        except Exception as exc:                    # the basis fold already succeeded - never fatal
            out["metric_redistill"] = {"ran": False, "error": str(exc)}
    else:
        out["metric_redistill"] = {"ran": False, "reason": "basis unchanged - nothing re-embedded"}

    if argv:
        out["route"] = route(root, net, " ".join(argv))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
