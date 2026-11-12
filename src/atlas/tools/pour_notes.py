"""Pour the week's design record into the greenfield and demonstrate ingest -> reconstruct.

The terminal claude session's lane under the council perimeter (2026-08-24): consumes the
updown kernel READ-ONLY at its stable API (commit 375d26fa), writes only its own store root
and evidence tree. The demonstration the author set as the finish line: the bare atlas
system ingesting a real corpus and reconstructing goal-conditioned content at measured
fidelity, with the scalability story instrumented.

The laws this binds, each bought by the previous campaign (grounds in
evidence/ATLAS_REBUILD_IMBIBE_2026-08-24/):
  - spans are the unit of retrieval, segmented under coverage/cap/structure laws
    (DESIGN_2026-08-01 §2/§5; atlas.segment enforces them at the one entry point);
  - CONTENT ENTERS THE OBSERVATION as multiple typed handles per span, each resolving to a
    readable span with context — the handle-grade defect's cure shape (his goal statement,
    NOTE-20260824-his-goal-statement-handles-that-find; mechanism at self_shard.py:346-353);
    the validated carrier is the 240-char first-occurrence term window
    (WO-20260819-deep-term-window-handles; opening-claim prepending measurably REGRESSED);
  - raw-content embedding is the CEILING CONTROL, never the product arm (his ruling);
  - rank-aware scoring only — atom presence is provably blind (the planted-bad control);
  - fold cost declared and counted apart from query cost; zero LLM calls anywhere;
  - GPU use demonstrated per act, never claimed (charter §3a; the refuted close-GPU claim);
  - content-derived ids everywhere; a re-run reproduces ids byte-for-byte (determinism is
    an instrument precondition); the vector sidecar keeps the shape read float-free;
  - loud degrade: refusal over thin results; a probe whose anchor does not resolve in its
    expected source is REFUSED at mint, never scored (freeze-refuses-on-mismatch);
  - the flat oracle is printed beside the descent (hierarchy is a bargain only where the
    corpus does not fit — the beam-bench honesty at 12k leaves).

Scale posture, named: at this corpus (~10^3 spans) flat exact scan is the cheaper read and
the demonstration says so; the hierarchy's claim here is structure + measured residuals +
the crossover story, not a speed win. The dense splitter is licensed at this n only; the
sampled/landmark splitter is MANDATORY at client scale (the gauntlet).

Runtime law: /usr/bin/python3, system + user site; refuses the repo .venv by construction
(no activation path exists here). Model: the repo-vendored bge-small ONNX.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

import numpy as np

from ..bench.cluster import best_split
from ..segment import SEGMENTATION_RECIPE_VERSION, segment_bytes
from ..updown import ChildLeaf, UpInputs, down, up

#: repo root by filesystem position — discovery, never a path mutation (the seal law:
#: atlas code touches neither sys.path nor laplace; run me as
#: PYTHONPATH=src /usr/bin/python3 -m atlas.tools.pour_notes)
ROOT = Path(__file__).resolve().parents[3]   # the checkout: src/atlas/tools/pour_notes.py (R2)

SCHEMA_VERSION = "updown-notes-pour/1"
INPUT_RECIPE_VERSION = "handles/span-head+term-window-240/1"

POUR_MODEL = os.environ.get("LAPLACE_POUR_MODEL", "BAAI/bge-small-en-v1.5")
ENCODER_TAG = POUR_MODEL.split("/")[-1]
ENCODER_ID = f"{ENCODER_TAG}/onnx/1"
METRIC_VERSION = ENCODER_ID
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

AXIS = "updown-routing"
GRADE_CONTRACT_ID = "axis:updown-routing/notes-v0"
COARSE_TO_FINE: tuple[int, ...] = tuple(range(9, -1, -1))  # 9 coarse ... 0 = handles
CHI = 4          # declared retained rank — the explicit dial; auto-chi is HOLD (selector bench)
PHI = 0.85       # declared residual dial — UNCALIBRATED, named so; calibration is his (F23)
LEAF_BLOCK_CAP = 12   # promote directly at or under this fan-out (RAPTOR dilution lesson:
                      # ~229 spans/cluster bought nothing; small blocks are the ruled posture)
SEED = 20260824
TERM_WINDOW = 240
MAX_TERM_HANDLES = 5
CONTEXT_CHARS = 300
BEAM = 4
TOP_K = 10

STORE_ROOT = ROOT / "atlas" / "stores" / "updown-notes"
EVIDENCE = ROOT / "evidence" / "ATLAS_UPDOWN_V0_2026-08-24"

#: The week's record — "integrate all the benchmarks and notes over the last week" resolved
#: to files. The atlas packets ride as structured sources (the JSON segmenter owns them).
CORPUS_FILES = [
    "ARMING_2026-08-19_the-pilot-night.md",
    "ARMING_2026-08-20_the-audit-day-close.md",
    "ARMING_2026-08-20_the-pilot-night-brief.md",
    "ARMING_2026-08-21_stage-one-becomes-the-marriage.md",
    "ATLAS_MATHEMATICS.md",
    "AUDIT_2026-08-23_implementation.md",
    "CHARTER_2026-08-23_the-ego-seat.md",
    "CHARTER_2026-08-23_the-interface-seat.md",
    "CHARTER_2026-08-23_the-superego-seat.md",
    "CHARTER_2026-08-24_the-atlas-rebuild.md",
    "DESIGN_2026-08-18_the-foundations-shelf.md",
    "DESIGN_2026-08-19_the-renormalized-atlas.md",
    "DESIGN_2026-08-20_the-conjugate-interface.md",
    "DESIGN_2026-08-23_the-organ-and-the-margin.md",
    "SESSION_HANDOFF_2026-08-20_the-audit-day-close.md",
    "SESSION_HANDOFF_2026-08-20_the-pilot-night.md",
    "SESSION_HANDOFF_2026-08-21_the-audit-day-close.md",
    "SESSION_HANDOFF_2026-08-23_stage-one-becomes-the-marriage.md",
    "SESSION_HANDOFF_2026-08-23_the-close.md",
    "SESSION_HANDOFF_2026-08-23_the-organ-and-the-margin.md",
    "SESSION_HANDOFF_2026-08-24_the-atlas-at-the-join.md",
    "SESSION_HANDOFF_2026-08-24_the-organ-and-the-margin.md",
    "atlas/packets/ego/ATLAS-S0-HANDOFF.md",
    "atlas/packets/ego/ATLAS-S0-INTEGRATION.json",
    "atlas/packets/ego/ATLAS-S0-reconstruction.json",
    "atlas/packets/integration/ATLAS-M0-SEAT-BUS-HANDOFF.json",
    "atlas/packets/sensorium/ATLAS-S0.json",
]

#: Probes minted with a verbatim anchor in a named source. A probe whose anchor fails to
#: resolve is REFUSED and listed — never silently dropped, never scored. The first two are
#: the 2026-08-19 reconstruction bench's measured MISSES, re-asked of the greenfield.
PROBES = [
    ("DMRG hierarchicalisation of clustering and distillation",
     "DESIGN_2026-08-19_the-renormalized-atlas.md", "DMRG"),
    ("orthogonality catastrophe in the embedding space",
     "DESIGN_2026-08-19_the-renormalized-atlas.md", "orthogonality catastrophe"),
    ("what does the closure residual measure and guarantee",
     "DESIGN_2026-08-19_the-renormalized-atlas.md", "closure residual"),
    ("how does an assumption force the join between the two faces",
     "CHARTER_2026-08-24_the-atlas-rebuild.md", "forces"),
    ("do we carry old implementations or rewrite them on the substrate",
     "CHARTER_2026-08-24_the-atlas-rebuild.md", "carry contracts and tests; rewrite implementations"),
    ("why was the eigengap rejected for choosing the cluster count",
     "ATLAS_MATHEMATICS.md", "eigengap"),
    ("what does the silhouette criterion select and where is it computed",
     "ATLAS_MATHEMATICS.md", "silhouette"),
    ("which organs are dead or relic in the implementation audit",
     "AUDIT_2026-08-23_implementation.md", "coactivation"),
    ("when does a seat message count as delivered",
     "atlas/packets/ego/ATLAS-S0-INTEGRATION.json", "accepted acknowledgement"),
    ("what happened at the atlas join session close",
     "SESSION_HANDOFF_2026-08-24_the-atlas-at-the-join.md", "ATLAS-S0"),
    ("what is the incremental deposit's honest receipt",
     "SESSION_HANDOFF_2026-08-24_the-atlas-at-the-join.md", "incremental"),
    ("the interface exposes the causal ledger not chain of thought",
     "CHARTER_2026-08-24_the-atlas-rebuild.md", "causal ledger"),
]

_WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]{3,}")
_STOP = set("this that with from have been were will would their there which about "
            "into over under after before never every their them then than when what "
            "where the and for are not its his her our your one two also only".split())


def _h(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False)
                  .encode("utf-8")).hexdigest()


@dataclass
class Span:
    span_id: str
    path: str
    source_sha: str
    start: int
    end: int
    text: str


@dataclass
class Handle:
    handle_id: str
    kind: str          # span-head | term-window
    term: str
    text: str          # the content-bearing window that EMBEDS — content enters here
    span_id: str


@dataclass
class GpuReceipt:
    device: str = ""
    providers_requested: tuple[str, ...] = ()
    providers_observed: str = "introspection-unavailable"
    util_peak_pct: int = 0
    mem_peak_mib: int = 0
    samples: int = 0
    wall_s: float = 0.0
    texts: int = 0
    demonstrated: bool = False
    note: str = ""


class GpuBgeEncoder:
    """The vendored bge-small on the CUDA execution provider, receipted.

    fastembed's ``query_embed`` is a pass-through for this model (WO-20260819), so the bge
    retrieval prefix is applied EXPLICITLY here and named in the input recipe. GPU use is
    demonstrated per act: providers are requested in-list, nvidia-smi is sampled during the
    batch, and the receipt records what was OBSERVED — a 0% peak is reported, never hidden.
    """

    @staticmethod
    def _preload_cuda() -> list[str]:
        """Use the shared interpreter-aware Atlas CUDA loader."""
        from ..runtime import preload_cuda_libraries
        return preload_cuda_libraries()["loaded"]

    def __init__(self) -> None:
        self.cuda_preloaded = self._preload_cuda()
        from fastembed import TextEmbedding
        self.providers_requested = ("CUDAExecutionProvider", "CPUExecutionProvider")
        if POUR_MODEL == "BAAI/bge-small-en-v1.5":
            vendored = ROOT / "models" / "fastembed" / "fast-bge-small-en-v1.5"
            if not (vendored / "model_optimized.onnx").is_file():
                raise RuntimeError(f"vendored model missing at {vendored} — extract the tarball")
            self._model = TextEmbedding(POUR_MODEL, specific_model_path=str(vendored),
                                        providers=list(self.providers_requested))
        else:
            # bake-off candidates load from fastembed's own cache (already on this box);
            # a NEW encoder is a NEW projection generation, never a rewrite (version algebra)
            self._model = TextEmbedding(POUR_MODEL,
                                        cache_dir=str(Path.home() / ".cache" / "fastembed"),
                                        providers=list(self.providers_requested))
        self.receipts: list[GpuReceipt] = []

    def _observed_providers(self) -> str:
        obj = self._model
        for chain in (("model", "model", "get_providers"),):
            cur: object = obj
            try:
                for name in chain[:-1]:
                    cur = getattr(cur, name)
                return ",".join(getattr(cur, chain[-1])())
            except Exception:  # noqa: BLE001 - introspection is best-effort by design
                continue
        return "introspection-unavailable"

    def embed(self, texts: list[str], *, label: str) -> np.ndarray:
        peak = {"util": 0, "mem": 0, "n": 0}
        stop = threading.Event()

        def sample() -> None:
            while not stop.is_set():
                try:
                    out = subprocess.run(
                        ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
                         "--format=csv,noheader,nounits"],
                        capture_output=True, text=True, timeout=2)
                    u, m = (int(x.strip()) for x in out.stdout.split(","))
                    peak["util"] = max(peak["util"], u)
                    peak["mem"] = max(peak["mem"], m)
                    peak["n"] += 1
                except Exception:  # noqa: BLE001 - sampling never breaks the embed
                    pass
                time.sleep(0.12)

        t = threading.Thread(target=sample, daemon=True)
        t0 = time.time()
        t.start()
        try:
            # batch for the 4GB A2000: 512-token sequences at fastembed's default batch
            # asked the arena for 7GB (measured OOM, 2026-08-24); 24 fits with headroom
            vecs = np.asarray([list(v) for v in self._model.embed(texts, batch_size=24)],
                              dtype=np.float64)
        finally:
            stop.set()
            t.join(timeout=1)
        wall = time.time() - t0
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vecs = vecs / norms
        rec = GpuReceipt(
            device="NVIDIA RTX A2000 Laptop GPU",
            providers_requested=self.providers_requested,
            providers_observed=self._observed_providers(),
            util_peak_pct=peak["util"], mem_peak_mib=peak["mem"], samples=peak["n"],
            wall_s=round(wall, 3), texts=len(texts),
            demonstrated=peak["util"] > 0,
            note=(f"{label}: GPU utilization observed" if peak["util"] > 0 else
                  f"{label}: NO GPU utilization observed during the batch — treat as a "
                  f"CPU run until cured; the claim is refused, not softened"),
        )
        self.receipts.append(rec)
        return vecs

    def query(self, text: str) -> np.ndarray:
        return self.embed([BGE_QUERY_PREFIX + text], label="query")[0]


def load_corpus() -> tuple[list[Span], dict[str, str], list[dict]]:
    spans: list[Span] = []
    source_sha: dict[str, str] = {}
    seg_receipts: list[dict] = []
    for rel in CORPUS_FILES:
        data = (ROOT / rel).read_bytes()
        sha = sha256(data).hexdigest()
        source_sha[rel] = sha
        result = segment_bytes(f"node:{rel}", rel, f"sha256:{sha}", data)
        leaves = [s for s in result.spans if s.is_leaf]
        for s in leaves:
            text = data[s.start:s.end].decode("utf-8", errors="replace")
            if not text.strip():
                continue
            spans.append(Span(
                span_id=_h({"src": sha, "start": s.start, "end": s.end}),
                path=rel, source_sha=sha, start=s.start, end=s.end, text=text))
        seg_receipts.append({"path": rel, "bytes": len(data), "leaf_spans": len(leaves),
                             "oversize": len(result.oversize or [])})
    if not spans:
        raise RuntimeError("segmentation produced zero spans — refusing a thin pour")
    return spans, source_sha, seg_receipts


def mint_handles(spans: list[Span]) -> list[Handle]:
    df: dict[str, int] = {}
    span_terms: list[list[str]] = []
    for sp in spans:
        terms = sorted({w.lower() for w in _WORD.findall(sp.text)} - _STOP)
        span_terms.append(terms)
        for t in terms:
            df[t] = df.get(t, 0) + 1
    n = len(spans)
    handles: list[Handle] = []
    for sp, terms in zip(spans, span_terms, strict=True):
        head = sp.text[:TERM_WINDOW]
        handles.append(Handle(
            handle_id=_h({"span": sp.span_id, "kind": "span-head"}),
            kind="span-head", term="", text=head, span_id=sp.span_id))
        # distinctive = rare across the corpus but present here; deterministic order
        scored = sorted((df[t], t) for t in terms if 1 <= df[t] <= max(2, n // 20))
        for _, term in scored[:MAX_TERM_HANDLES]:
            m = re.search(re.escape(term), sp.text, re.IGNORECASE)
            if not m:
                continue
            lo = max(0, m.start() - TERM_WINDOW // 3)
            window = sp.text[lo:lo + TERM_WINDOW]
            handles.append(Handle(
                handle_id=_h({"span": sp.span_id, "kind": "term-window", "term": term}),
                kind="term-window", term=term, text=window, span_id=sp.span_id))
    return handles


@dataclass
class Fold:
    registry: dict[str, dict] = field(default_factory=dict)   # node_handle -> node record
    roots: list[str] = field(default_factory=list)
    level_receipts: list[dict] = field(default_factory=list)
    up_calls: int = 0


def fold_up(handles: list[Handle], vecs: np.ndarray, assumption: str, fibre: str) -> Fold:
    fold = Fold()
    frontier: list[ChildLeaf] = [
        ChildLeaf(handle=h.handle_id, text=h.text, vector=tuple(float(x) for x in vecs[i]))
        for i, h in enumerate(handles)
    ]
    grade = 0
    while True:
        to_grade = grade + 1
        if to_grade >= len(COARSE_TO_FINE):
            raise RuntimeError("fold exceeded the declared grade contract — refuse, do not wrap")
        blocks: list[list[ChildLeaf]]
        if len(frontier) <= LEAF_BLOCK_CAP:
            blocks = [frontier]
        else:
            X = np.asarray([c.vector for c in frontier], dtype=np.float64)
            split = best_split(X, SEED + grade)
            if split.k <= 1:
                ordered = sorted(frontier, key=lambda c: c.handle)
                blocks = [ordered[i:i + LEAF_BLOCK_CAP]
                          for i in range(0, len(ordered), LEAF_BLOCK_CAP)]
            else:
                by_label: dict[int, list[ChildLeaf]] = {}
                for c, lab in zip(frontier, split.labels, strict=True):
                    by_label.setdefault(int(lab), []).append(c)
                blocks = []
                for lab in sorted(by_label):
                    grp = by_label[lab]
                    if len(grp) > LEAF_BLOCK_CAP * 4:
                        # keep every promotion small-fan-out at EVERY grade: the kernel's
                        # dense eigensolve is licensed for block-sized inputs only, and the
                        # dilution lesson (RAPTOR at ~229/cluster) rules giant blocks out
                        grp = sorted(grp, key=lambda c: c.handle)
                        blocks.extend(grp[i:i + LEAF_BLOCK_CAP * 2]
                                      for i in range(0, len(grp), LEAF_BLOCK_CAP * 2))
                    else:
                        blocks.append(grp)
        next_frontier: list[ChildLeaf] = []
        residuals: list[float] = []
        insufficient = 0
        for blk in blocks:
            res = up(UpInputs(
                assumption=assumption, fibre=fibre, axis=AXIS,
                from_grade=grade, to_grade=to_grade,
                metric_version=METRIC_VERSION, grade_contract_id=GRADE_CONTRACT_ID,
                chi=min(CHI, max(1, len(blk) - 1)) if len(blk) > 1 else 1,
                phi=PHI, coarse_to_fine=COARSE_TO_FINE,
                children=tuple(blk),
            ))
            fold.up_calls += 1
            node = res.node
            assert node is not None
            fold.registry[node.node_handle] = {
                "grade": to_grade,
                "centroid": list(node.centroid),
                "face": node.semantic_face,
                "members": list(node.member_handles),
                "member_kinds": "routing" if grade > 0 else "handle",
                "residual": res.residual_value,
                "representation_sufficient": res.representation_sufficient,
                "forced_descent": res.forced_descent,
            }
            residuals.append(res.residual_value)
            if not res.representation_sufficient:
                insufficient += 1
            next_frontier.append(ChildLeaf(
                handle=node.node_handle, text=node.semantic_face,
                vector=node.centroid))
        fold.level_receipts.append({
            "from_grade": grade, "to_grade": to_grade,
            "blocks": len(blocks), "children": len(frontier),
            "mean_truncation_residual": round(float(np.mean(residuals)), 4),
            "max_truncation_residual": round(float(np.max(residuals)), 4),
            "insufficient_blocks": insufficient,
            "chi": CHI, "phi": PHI,
        })
        frontier = next_frontier
        grade = to_grade
        if len(frontier) == 1:
            fold.roots = [frontier[0].handle]
            return fold


def verify_round_trips(fold: Fold, handles: list[Handle], vecs: np.ndarray,
                       sample: int = 6) -> list[dict]:
    """Sampled kernel-down verification: prolong from retained state, measure against the
    complete originals — the unverified path stays None by kernel law."""
    hv = {h.handle_id: (h, i) for i, h in enumerate(handles)}
    out: list[dict] = []
    leaf_nodes = [(nh, rec) for nh, rec in fold.registry.items()
                  if rec["member_kinds"] == "handle"]
    rng = np.random.default_rng(SEED)
    for nh, rec in (leaf_nodes if len(leaf_nodes) <= sample else
                    [leaf_nodes[i] for i in
                     rng.choice(len(leaf_nodes), size=sample, replace=False)]):
        node_children = {}
        ok = True
        for mh in rec["members"]:
            if mh not in hv:
                ok = False
                break
            h, i = hv[mh]
            node_children[mh] = ChildLeaf(handle=mh, text=h.text,
                                          vector=tuple(float(x) for x in vecs[i]))
        if not ok:
            continue
        # re-run the promotion to obtain the framed node (registry stores no floats beyond
        # the centroid; the kernel is pure so identity reproduces)
        res = up(UpInputs(
            assumption="verify", fibre="verify", axis=AXIS,
            from_grade=0, to_grade=1, metric_version=METRIC_VERSION,
            grade_contract_id=GRADE_CONTRACT_ID,
            chi=min(CHI, max(1, len(node_children) - 1)) if len(node_children) > 1 else 1,
            phi=PHI, coarse_to_fine=COARSE_TO_FINE,
            children=tuple(node_children[mh] for mh in rec["members"]),
        ))
        assert res.node is not None
        d = down(res.node, children=node_children)
        out.append({"node": nh[:16], "members": len(rec["members"]),
                    "verified": d.verified,
                    "round_trip_residual": (round(d.round_trip_residual, 4)
                                            if d.round_trip_residual is not None else None)})
    return out


def descend(fold: Fold, qvec: np.ndarray, handles_by_id: dict[str, int],
            hvecs: np.ndarray) -> tuple[list[tuple[str, float]], list[str]]:
    """Beam descent root -> handles. Returns ranked (handle_id, score) and the route."""
    def score(vec: list[float]) -> float:
        v = np.asarray(vec)
        n = np.linalg.norm(v) or 1.0
        return float(qvec @ (v / n))

    frontier = [(fold.registry[r], r) for r in fold.roots]
    route: list[str] = list(fold.roots)
    leaf_scores: dict[str, float] = {}
    while frontier:
        nxt: list[tuple[float, str]] = []
        for rec, _ in frontier:
            for mh in rec["members"]:
                if rec["member_kinds"] == "handle":
                    i = handles_by_id[mh]
                    leaf_scores[mh] = float(qvec @ hvecs[i])
                else:
                    nxt.append((score(fold.registry[mh]["centroid"]), mh))
        if not nxt:
            break
        nxt.sort(key=lambda t: -t[0])
        keep = nxt[:BEAM]
        route.extend(mh for _, mh in keep)
        frontier = [(fold.registry[mh], mh) for _, mh in keep]
    ranked = sorted(leaf_scores.items(), key=lambda t: -t[1])
    return ranked, route


def resolve_span(sp: Span) -> str:
    """Read the span's bytes from source and VERIFY against the recorded digest — the
    freshness law: disagreement refuses rather than serving stale content."""
    data = (ROOT / sp.path).read_bytes()
    if sha256(data).hexdigest() != sp.source_sha:
        raise RuntimeError(f"source moved since pour: {sp.path} — refusing stale resolution")
    text = data[sp.start:sp.end].decode("utf-8", errors="replace")
    lo = max(0, sp.start - CONTEXT_CHARS)
    hi = min(len(data), sp.end + CONTEXT_CHARS)
    ctx = data[lo:hi].decode("utf-8", errors="replace")
    assert text in ctx
    return ctx


def spans_ranked_from_handles(ranked: list[tuple[str, float]],
                              handle_span: dict[str, str]) -> list[str]:
    seen: list[str] = []
    for hid, _ in ranked:
        sid = handle_span[hid]
        if sid not in seen:
            seen.append(sid)
    return seen


def first_hit_rank(span_order: list[str], span_by_id: dict[str, Span],
                   expected_path: str, anchor: str) -> int | None:
    pat = re.compile(re.escape(anchor), re.IGNORECASE)
    for r, sid in enumerate(span_order, start=1):
        sp = span_by_id[sid]
        if sp.path == expected_path and pat.search(sp.text):
            return r
    return None


def _ensure_cuda_loader_path() -> None:
    """Re-exec with LD_LIBRARY_PATH covering the user-site CUDA wheels BEFORE glibc reads
    it — the ctypes preload alone cannot cover the provider's full dependency closure
    (cufft/curand/cudnn sublibraries). The libs were always on this box; only the loader
    path was ever missing (his third ask, 2026-08-24)."""
    # Probe FIRST: when /etc/ld.so.conf.d/laplace-cuda.conf covers these libs (the
    # durable home for repeatedly-used native runtimes — his ruling 2026-08-24), this
    # whole function no-ops and the env hack retires itself.
    import ctypes
    try:
        ctypes.CDLL("libcublasLt.so.13")
        return
    except OSError:
        pass
    nv = Path.home() / ".local" / "lib" / "python3.12" / "site-packages" / "nvidia"
    want = [str(nv / "cu13" / "lib"), str(nv / "cudnn" / "lib")]
    want = [w for w in want if Path(w).is_dir()]
    if not want:
        return
    cur = os.environ.get("LD_LIBRARY_PATH", "")
    if all(w in cur.split(":") for w in want):
        return
    os.environ["LD_LIBRARY_PATH"] = ":".join([*want, cur] if cur else want)
    os.environ["PYTHONPATH"] = str(ROOT / "src")
    os.execv(sys.executable, [sys.executable, "-m", "atlas.tools.pour_notes", *sys.argv[1:]])


def main() -> int:
    _ensure_cuda_loader_path()
    t_start = time.time()
    assumption = ("the week's design record (2026-08-18..24) is the corpus; goals are "
                  "content-aspect queries under the atlas-rebuild assumption")
    fibre = "updown-v0-week-notes"

    spans, source_sha, seg_receipts = load_corpus()
    span_by_id = {s.span_id: s for s in spans}
    handles = mint_handles(spans)
    handle_span = {h.handle_id: h.span_id for h in handles}
    corpus_bytes = sum(r["bytes"] for r in seg_receipts)
    handle_bytes = sum(len(h.text.encode("utf-8")) for h in handles)

    enc = GpuBgeEncoder()
    t0 = time.time()
    hvecs = enc.embed([h.text for h in handles], label="handles")
    embed_wall = time.time() - t0

    t0 = time.time()
    fold = fold_up(handles, hvecs, assumption, fibre)
    fold_wall = time.time() - t0
    round_trips = verify_round_trips(fold, handles, hvecs)

    # ceiling control: raw span content embedded flat — the findability upper bound
    svecs = enc.embed([s.text[:2000] for s in spans], label="content-ceiling")

    handles_by_id = {h.handle_id: i for i, h in enumerate(handles)}
    span_ids = [s.span_id for s in spans]

    probe_rows: list[dict] = []
    refused: list[dict] = []
    for query, expected, anchor in PROBES:
        src_text = (ROOT / expected).read_text(encoding="utf-8", errors="replace")
        if not re.search(re.escape(anchor), src_text, re.IGNORECASE):
            refused.append({"query": query, "expected": expected, "anchor": anchor,
                            "why": "anchor does not resolve in the expected source"})
            continue
        qv = enc.query(query)
        t0 = time.time()
        ranked, route = descend(fold, qv, handles_by_id, hvecs)
        descent_ms = (time.time() - t0) * 1000
        descent_spans = spans_ranked_from_handles(ranked[:TOP_K * 4], handle_span)[:TOP_K]

        t0 = time.time()
        flat_order = np.argsort(-(hvecs @ qv))
        flat_ms = (time.time() - t0) * 1000
        flat_ranked = [(handles[i].handle_id, float(hvecs[i] @ qv)) for i in flat_order[:TOP_K * 4]]
        flat_spans = spans_ranked_from_handles(flat_ranked, handle_span)[:TOP_K]

        c_order = np.argsort(-(svecs @ qv))
        ceiling_spans = [span_ids[i] for i in c_order[:TOP_K]]

        row = {
            "query": query, "expected": expected, "anchor": anchor,
            "descent_rank": first_hit_rank(descent_spans, span_by_id, expected, anchor),
            "flat_handle_rank": first_hit_rank(flat_spans, span_by_id, expected, anchor),
            "content_ceiling_rank": first_hit_rank(ceiling_spans, span_by_id, expected, anchor),
            "descent_ms": round(descent_ms, 1), "flat_ms": round(flat_ms, 2),
            "route_nodes": len(route),
            "tokens_touched_topk": sum(len(span_by_id[s].text) for s in descent_spans[:3]) // 4,
        }
        if row["descent_rank"] == 1:
            row["resolved_head"] = resolve_span(span_by_id[descent_spans[0]])[:200]
        probe_rows.append(row)

    def hits(key: str, bound: int) -> int:
        return sum(1 for r in probe_rows if r[key] is not None and r[key] <= bound)

    n_p = len(probe_rows)
    report = {
        "schema_version": SCHEMA_VERSION,
        "generation": _h({"sources": source_sha, "seg": SEGMENTATION_RECIPE_VERSION,
                          "recipe": INPUT_RECIPE_VERSION, "encoder": ENCODER_ID,
                          "chi": CHI, "phi": PHI})[:16],
        "version_axes": {"segmentation_recipe_version": SEGMENTATION_RECIPE_VERSION,
                          "input_recipe_version": INPUT_RECIPE_VERSION,
                          "encoder_id": ENCODER_ID, "schema_version": SCHEMA_VERSION},
        "assumption": assumption, "fibre": fibre,
        "corpus": {"files": len(CORPUS_FILES), "bytes": corpus_bytes,
                    "spans": len(spans), "handles": len(handles),
                    "handle_bytes": handle_bytes,
                    "handle_bytes_per_doc": handle_bytes // len(CORPUS_FILES),
                    "handle_to_corpus_ratio": round(handle_bytes / corpus_bytes, 4)},
        "fold": {"up_calls": fold.up_calls, "levels": fold.level_receipts,
                  "roots": fold.roots, "wall_s": round(fold_wall, 2),
                  "llm_calls": 0, "chi": CHI, "phi": PHI,
                  "chi_phi_status": "DECLARED, uncalibrated — calibration is the author's "
                                    "dial (F23); auto-chi is HOLD per the selector bench"},
        "embed": {"wall_s": round(embed_wall, 2), "texts": len(handles),
                   "gpu_receipts": [vars(r) for r in enc.receipts]},
        "round_trip_verification": round_trips,
        "probes": probe_rows,
        "probes_refused": refused,
        "headline": {
            "probes": n_p,
            "descent_hit_at_1": hits("descent_rank", 1),
            "descent_hit_at_3": hits("descent_rank", 3),
            "flat_handle_hit_at_3": hits("flat_handle_rank", 3),
            "content_ceiling_hit_at_3": hits("content_ceiling_rank", 3),
            "historic_misses_reasked": [
                {"query": r["query"], "descent_rank": r["descent_rank"]}
                for r in probe_rows[:2]],
        },
        "scale_posture": ("flat exact scan is cheaper at this n and the numbers above show "
                          "it; the hierarchy's claim is structure + measured residuals + "
                          "the crossover at corpus sizes that do not fit a flat scan. The "
                          "dense splitter is licensed at this n only (gauntlet: sampled "
                          "splitter MANDATORY at client scale)."),
        "query_time_model_calls": {"llm": 0, "encoder_per_probe": 1},
        "wall_total_s": round(time.time() - t_start, 1),
    }

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    gen_dir = STORE_ROOT / report["generation"]
    gen_dir.mkdir(parents=True, exist_ok=True)
    np.save(gen_dir / "handle_vectors.npy", hvecs.astype(np.float32))
    with (gen_dir / "handles.jsonl").open("w", encoding="utf-8") as fh:
        for i, h in enumerate(handles):
            fh.write(json.dumps({"row": i, "handle_id": h.handle_id, "kind": h.kind,
                                 "term": h.term, "span_id": h.span_id,
                                 "text_sha": sha256(h.text.encode()).hexdigest()}) + "\n")
    with (gen_dir / "spans.jsonl").open("w", encoding="utf-8") as fh:
        for s in spans:
            fh.write(json.dumps({"span_id": s.span_id, "path": s.path,
                                 "source_sha": s.source_sha,
                                 "start": s.start, "end": s.end}) + "\n")
    with (gen_dir / "registry.json").open("w", encoding="utf-8") as fh:
        json.dump({"roots": fold.roots, "nodes": fold.registry}, fh)
    (EVIDENCE / f"REPORT_{ENCODER_TAG}.json").write_text(json.dumps(report, indent=1, ensure_ascii=False),
                                          encoding="utf-8")

    lines = [
        "# ATLAS updown v0 — the week's record, poured and reconstructed\n",
        f"Generation `{report['generation']}` · {len(CORPUS_FILES)} files · "
        f"{len(spans)} spans · {len(handles)} handles "
        f"({report['corpus']['handle_to_corpus_ratio']:.1%} of corpus bytes)\n",
        f"Fold: {fold.up_calls} promotions, {len(fold.level_receipts)} levels, "
        f"{fold_wall:.1f}s, 0 LLM calls · Embed: {embed_wall:.1f}s on "
        f"{report['embed']['gpu_receipts'][0]['device']} "
        f"(peak {report['embed']['gpu_receipts'][0]['util_peak_pct']}% GPU)\n",
        "| probe | descent | flat | ceiling |", "|---|---|---|---|",
    ]
    for r in probe_rows:
        lines.append(f"| {r['query'][:58]} | {r['descent_rank']} | "
                     f"{r['flat_handle_rank']} | {r['content_ceiling_rank']} |")
    lines.append(f"\nHit@3 — descent {hits('descent_rank', 3)}/{n_p} · flat-handle "
                 f"{hits('flat_handle_rank', 3)}/{n_p} · content-ceiling "
                 f"{hits('content_ceiling_rank', 3)}/{n_p}\n")
    lines.append(report["scale_posture"])
    (EVIDENCE / f"REPORT_{ENCODER_TAG}.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({"generation": report["generation"],
                      "headline": report["headline"],
                      "gpu": report["embed"]["gpu_receipts"][0]["note"],
                      "fold_levels": len(fold.level_receipts),
                      "refused_probes": len(refused),
                      "report": str((EVIDENCE / f"REPORT_{ENCODER_TAG}.json").relative_to(ROOT))},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
