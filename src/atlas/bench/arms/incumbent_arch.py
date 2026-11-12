"""incumbent_arch.py - the engine's ARCHITECTURE, rebuilt over the snapshot and measured fairly.

WHAT THIS ARM IS. The live engine answers a question by descending a banked concept tree: one
node per file, each carrying a one-line digest; the digests are embedded; the nodes are clustered
by meaning into a hierarchy; a query descends that hierarchy with a level-synchronous beam and
returns top-k leaves; the reader then skims every hit's digest and opens the top few files whole.
This arm reproduces exactly that shape over the frozen snapshot, so that "the engine's retrieval"
appears in the comparison table as a MEASUREMENT on the same corpus, the same tasks and the same
scorer as every other arm - rather than as a claim quoted from a different day's instrument.

WHY IT REBUILDS INSTEAD OF READING WHAT THE ENGINE ALREADY BUILT, which is the important part.
The engine has a banked ``.meaning_tree.json`` and a banked essence per node. This arm uses
NEITHER, and could not: those are SEALED DERIVED STORES under the author's ratified perimeter
principle - the soul is folded into the live tree vector-only, so the banked tree is inside the
seal even though its floats carry no text, and ``atlas/tests/test_seal.py`` forbids the import
that would reach them regardless. Everything here is therefore derived MECHANICALLY FROM SNAPSHOT
BLOBS: the digest recipe is re-implemented from the engine's ``self_shard._essence`` idiom, the
vectors are built by the vendored encoder from those digests, and the tree is built by this
package's own spectral clusterer.

That constraint is also what makes the comparison FAIR rather than flattering. The arm sees the
same universe every other arm sees, pays a fold bill that is counted in the same five dimensions,
and cannot reach one byte the bench-filtered view excludes. What it therefore does NOT reproduce
is the live system's advantages that come from outside this universe - the soul vectors folded
into the live geometry, the banked essences refined over many sessions, and the wake payload that
a real session reads before it descends anything. Those are real and they are why the separate
``incumbent-live`` reference row exists; they are not part of this arm, and this arm's number
should never be quoted as "the deployed system's number".

THE DIGEST RECIPE, ``v1-title``, ported as an idiom and not as code. The engine's ``_essence``
takes a file's first heading (markdown ``# ``), or its module docstring's first line (python), or
its title/section (tex), or its key inventory (json/yaml), or its first non-empty line; caps it;
and the router then presents that beside the node's path. This arm's digest is
``"<path> | <essence>"``. It is a TITLE-grade digest, which the engine's own 2026-07-29 oracle
gate measured as the weak link (a content-grade digest moved one carrier's rank 829 -> 10). That
weakness is inherited on purpose: v1-title is what the live system actually runs today, and an
arm that quietly used the better recipe would be measuring a system nobody has deployed.

THE READ PROTOCOL is v1 arm A's, ported with its constants: descend at beam 8 and then at beam 16
(two bounded rounds), skim the digest of every one of the top-k hits, then open at most three hit
files WHOLE under a 32 KB per-file cap, stopping as soon as the atoms are present. Every one of
those bytes goes through the counting reader.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import numpy as np

from ...encoders.bge_onnx import BgeOnnxEncoder, resolve_model_dir
from ...errors import ArmUnavailable
from ...ids import chash, hash_bytes
from ...segment import SEGMENTATION_RECIPE_VERSION
from ...store import write_atomic
from ..cluster import BRANCH_MAX, best_split
from ..cost import FoldCost, ModelCounter, SpanReader
from ..protocol import NO_MODEL, ArmProtocol
from ..scoring import score
from ..task import BenchTask
from ..universe import SnapshotView
from .base import ArmAnswer, BaseArm

#: v1 arm A's constants, ported verbatim from ``scripts/reconstruction_bench.py``.
DEFAULT_K = 10
DEFAULT_BEAM = 8
FILE_READ_CAP = 32 * 1024        # A_FILE_READ_CAP: one question's read of one file
MAX_WHOLE_READS = 3
ROUNDS = 2                       # round 1 at beam, round 2 at beam*2

#: The engine's own tree budget (``meaning_upfold``): a cluster of <= LEAF_MAX is not split, K is
#: silhouette-chosen and clamped to [2, BRANCH_MAX], recursion is bounded by MAX_DEPTH.
LEAF_MAX = 10
MAX_DEPTH = 6

#: The digest cap the engine's ``_essence`` uses for its title forms.
ESSENCE_CAP = 160

INPUT_RECIPE_VERSION = "v1-title-digest/1"

#: Read budget. Three whole files at 32 KB plus ten digests cannot approach this; declared anyway,
#: because an undeclared budget is the seam J6 hole.
READ_BUDGET_BYTES = 1 * 1024 * 1024

DEFAULT_STORE = Path(__file__).resolve().parents[4] / "atlas" / "stores" / "projections"   # the container's stores (R2)

#: Compiled out of the f-string it used to live in: a brace-bearing pattern inside an f-string is
#: the kind of quoting the reader has to decode rather than read.
_BIB_ENTRY = re.compile(r"^@\w+\{", re.M)


# ---------------------------------------------------------------------------
# the digest recipe - the engine's _essence idiom, re-implemented over snapshot bytes
# ---------------------------------------------------------------------------

def essence(path: str, text: str) -> str:
    """One line saying what the object IS. Deterministic per file type; the engine's idiom."""
    ext = ("." + path.rsplit(".", 1)[-1].lower()) if "." in path.rsplit("/", 1)[-1] else ""
    if ext == ".py":
        m = re.search(r'^\s*[ru]?"""(.*?)(?:"""|$)', text, re.S | re.M)
        if m:
            head = [ln.strip() for ln in m.group(1).strip().splitlines() if ln.strip()]
            if head:
                return head[0][:ESSENCE_CAP]
        m = re.search(r"^(?:async\s+def|def|class)\s+\w+", text, re.M)
        return m.group(0).strip() if m else "python module"
    if ext in (".md", ".markdown"):
        m = re.search(r"^#\s+(.+)$", text, re.M)
        if m:
            return m.group(1).strip()[:ESSENCE_CAP]
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith(("---", "<!--", "#")):
                return s[:ESSENCE_CAP]
        return "markdown document"
    if ext == ".tex":
        m = re.search(r"\\title\{(.+?)\}", text, re.S)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()[:ESSENCE_CAP]
        m = re.search(r"\\(?:sub)*section\*?\{(.+?)\}", text)
        if m:
            return m.group(1).strip()[:ESSENCE_CAP]
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("%"):
                return s[:ESSENCE_CAP]
        return "latex source"
    if ext == ".json":
        try:
            data = json.loads(text)
        except (ValueError, RecursionError):
            return "json document"
        if isinstance(data, dict):
            keys = list(data.keys())
            return ("keys: " + ", ".join(map(str, keys[:8]))) if keys else "json object"
        if isinstance(data, list):
            return f"json array [{len(data)}]"
        return "json scalar"
    if ext in (".yaml", ".yml"):
        keys = list(dict.fromkeys(re.findall(r"^([A-Za-z_][\w-]*):", text, re.M)))
        return ("keys: " + ", ".join(keys[:8])) if keys else "yaml document"
    if ext == ".bib":
        return f"{len(_BIB_ENTRY.findall(text))} bib reference(s)"
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first[:ESSENCE_CAP] if first else f"{ext.lstrip('.') or 'data'} file"


def digest_of(node_id: str, text: str) -> str:
    """``"<path> | <essence>"`` - the single travelling handle, node-grade, never span-grade."""
    return f"{node_id} | {essence(node_id, text)}"


# ---------------------------------------------------------------------------
# the tree - the engine's shape, this package's clusterer
# ---------------------------------------------------------------------------

def build_tree(X: np.ndarray, seed: int) -> dict[str, Any]:
    """Recursive silhouette-spectral clustering of node vectors, engine budget.

    Returns ``{"children": {...}, "members": {...}, "centroid": {...}}`` keyed by cluster id. A
    cluster of at most ``LEAF_MAX`` members is a leaf and its members hang off it directly, which
    is what ``meaning_upfold`` does and what makes the descent's last level a real read set rather
    than a single node.
    """
    children: dict[str, list[str]] = {}
    members: dict[str, np.ndarray] = {"r": np.arange(len(X), dtype=np.int64)}
    centroid: dict[str, np.ndarray] = {}

    def centroid_of(rows: np.ndarray) -> np.ndarray:
        vec = np.asarray(X[rows], dtype=np.float32).mean(axis=0)
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm > 1e-12 else vec

    stack = [("r", 0)]
    centroid["r"] = centroid_of(members["r"])
    while stack:
        cid, depth = stack.pop()
        rows = members[cid]
        if len(rows) <= LEAF_MAX or depth >= MAX_DEPTH or len(rows) < 4:
            children[cid] = []
            continue
        split = best_split(X[rows], seed=seed + depth * 977 + len(members),
                           branch_max=BRANCH_MAX)
        groups = [rows[split.labels == j] for j in range(split.k)]
        groups = [g for g in groups if len(g)]
        if len(groups) < 2:
            children[cid] = []
            continue
        kids: list[str] = []
        for j, rows_j in enumerate(groups):
            kid = f"{cid}.{j}"
            members[kid] = rows_j
            centroid[kid] = centroid_of(rows_j)
            kids.append(kid)
            stack.append((kid, depth + 1))
        children[cid] = kids
    return {"children": children, "members": members, "centroid": centroid}


class IncumbentArchArm(BaseArm):
    """Node digests, embedded, clustered, descended at beam 8/16, read under arm A's protocol."""

    def __init__(self, k: int = DEFAULT_K, beam: int = DEFAULT_BEAM, seed: int = 20260801,
                 store_root: Path | None = None, model_dir: str | Path | None = None) -> None:
        self.k = k
        self.beam = beam
        self.seed = seed
        self.store_root = Path(store_root) if store_root else DEFAULT_STORE
        self.model_dir = model_dir
        self.encoder = BgeOnnxEncoder(model_dir=model_dir)
        self.protocol = ArmProtocol(
            arm_id="incumbent_arch", variant="",
            segmentation_recipe_version=SEGMENTATION_RECIPE_VERSION,
            input_recipe_version=INPUT_RECIPE_VERSION,
            encoder_id=self.encoder.encoder_id, schema_version=None,
            k=k, max_spans_read=0, max_whole_file_reads=MAX_WHOLE_READS,
            read_budget_bytes=READ_BUDGET_BYTES, rounds=ROUNDS, beam=beam,
            max_materialized=None, granularity="node",
            fold_model_calls=0, query_model_calls=0,
            model_stamp=NO_MODEL, seed=seed,
            note=("the engine's architecture over the snapshot: v1-title node digests, embedded, "
                  "silhouette-spectral tree, level-synchronous beam descent, v1 arm-A read "
                  "protocol. Builds its own tree - the engine's banked tree and essences are "
                  "sealed derived stores and are never read"),
        )
        self._tree: dict[str, Any] | None = None
        self._node_ids: list[str] = []
        self._digests: list[str] = []
        self._matrix: np.ndarray | None = None
        self._folded_universe: str | None = None
        self.generation_id: str | None = None

    # --- the fold ---------------------------------------------------------

    def generation(self, view: SnapshotView) -> dict[str, Any]:
        return {
            "kind": "incumbent-digest-generation/1",
            "snapshot_id": view.snapshot_id,
            "input_recipe_version": INPUT_RECIPE_VERSION,
            "encoder_id": self.encoder.encoder_id,
            "dim": self.encoder.dim,
            "normalisation": "l2-unit",
            "granularity": "node-digest",
            "essence_cap": ESSENCE_CAP,
        }

    def fold(self, view: SnapshotView, segmentation_id: str = "") -> FoldCost:
        if not BgeOnnxEncoder.available(self.model_dir):
            raise ArmUnavailable(
                "the bge encoder is not available: set LAPLACE_EMBED_MODEL_DIR to the extracted "
                "vendored model. Never a quiet degrade to a hash encoder",
                arm="incumbent_arch", model_dir=str(resolve_model_dir(self.model_dir)),
            )
        gen = self.generation(view)
        self.generation_id = chash(gen)
        out_dir = self.store_root / self.generation_id.split(":", 1)[-1]
        keys_path, vec_path = out_dir / "keys.json", out_dir / "vectors.npy"
        manifest_path = out_dir / "manifest.json"

        node_ids = list(view.node_ids)
        digests = [digest_of(nid, view.node_text(nid)) for nid in node_ids]
        # Content-keyed exactly as dense_flat is: a digest whose bytes are unchanged re-uses its
        # vector across views and across runs, and a changed digest is a MISS, never a stale hit.
        digest_keys = [hash_bytes(d.encode("utf-8")) for d in digests]

        prior_build_seconds = 0.0
        if manifest_path.is_file():
            prior_build_seconds = float(json.loads(
                manifest_path.read_text(encoding="utf-8")).get("build_wall_seconds", 0.0))
        cache: dict[str, int] = {}
        matrix: np.ndarray | None = None
        keys: list[str] = []
        if keys_path.is_file() and vec_path.is_file():
            keys = json.loads(keys_path.read_text(encoding="utf-8"))
            matrix = np.load(vec_path)
            if matrix.shape[0] != len(keys):
                raise ArmUnavailable("digest cache is inconsistent: rows and keys disagree",
                                     rows=int(matrix.shape[0]), keys=len(keys))
            cache = {key: i for i, key in enumerate(keys)}

        started = time.perf_counter()
        wanted: list[str] = []
        seen: set[str] = set()
        text_of: dict[str, str] = {}
        for key, digest in zip(digest_keys, digests, strict=True):
            if key in cache or key in seen:
                continue
            seen.add(key)
            wanted.append(key)
            text_of[key] = digest
        built = 0
        if wanted:
            out_dir.mkdir(parents=True, exist_ok=True)
            rows = self.encoder.embed([text_of[key] for key in wanted])
            block = np.asarray(rows, dtype=np.float32)
            matrix = block if matrix is None else np.vstack([matrix, block])
            keys = keys + wanted
            cache = {key: i for i, key in enumerate(keys)}
            built = len(wanted)
            np.save(vec_path, matrix)
            write_atomic(keys_path, (json.dumps(keys) + "\n").encode("utf-8"))
        embed_seconds = time.perf_counter() - started
        if matrix is None:
            raise ArmUnavailable("incumbent fold produced no vectors", arm="incumbent_arch")

        self._node_ids = node_ids
        self._digests = digests
        self._matrix = np.asarray(matrix[[cache[key] for key in digest_keys]], dtype=np.float32)

        tree_started = time.perf_counter()
        self._tree = build_tree(self._matrix, seed=self.seed)
        tree_seconds = time.perf_counter() - tree_started
        self._folded_universe = view.universe_id

        build_seconds = prior_build_seconds + (embed_seconds if built else 0.0)
        write_atomic(manifest_path, (json.dumps(
            {**gen, "generation_id": self.generation_id,
             "vector_count": int(matrix.shape[0]),
             "build_wall_seconds": round(build_seconds, 4)},
            sort_keys=True, indent=2) + "\n").encode("utf-8"))
        # The TREE is rebuilt every fold and its seconds are charged every time: unlike the
        # vectors it is not cached, so reporting it as free would be the seam J7 error in the
        # other direction. ``wall_seconds`` therefore carries the cumulative embed bill plus
        # THIS run's clustering.
        return FoldCost(
            wall_seconds=build_seconds + tree_seconds,
            wall_seconds_this_call=embed_seconds + tree_seconds,
            model_calls=0, model_tokens=0, vectors_built=built,
            bytes_stored=int(matrix.nbytes), cached=(built == 0),
        )

    # --- the descent ------------------------------------------------------

    def descend(self, qvec: np.ndarray) -> tuple[list[int], int, list[str]]:
        """Level-synchronous beam descent. Returns ``(ranked rows, materialized, visited)``.

        The engine's shape (``recursive_read.Descender.descend``): score this level's clusters by
        cosine against their centroids, expand the top ``beam``, materialize the direct leaf
        members of every expanded cluster, and take the expanded clusters' children as the next
        level. ``materialized`` is the count of node vectors actually scored - the arm's compute,
        reported as an outcome rather than fixed in advance.
        """
        tree = self._tree
        assert tree is not None
        children, members, centroid = tree["children"], tree["members"], tree["centroid"]
        materialized: dict[int, float] = {}
        visited: list[str] = []
        level = list(children.get("r", []))
        if not level:
            level = ["r"]
        while level:
            scored = sorted(
                ((float(centroid[c] @ qvec), c) for c in level),
                key=lambda pair: (-pair[0], pair[1]),
            )
            expanded = [c for _s, c in scored[: self.beam]]
            visited.extend(expanded)
            nxt: list[str] = []
            for cid in expanded:
                kids = children.get(cid, [])
                if kids:
                    nxt.extend(kids)
                else:
                    # A leaf cluster: its members are materialized and scored individually.
                    for row in members[cid]:
                        r = int(row)
                        if r not in materialized:
                            materialized[r] = float(self._matrix[r] @ qvec)
            level = nxt
        ranked = sorted(materialized, key=lambda r: (-materialized[r], self._node_ids[r]))
        return ranked, len(materialized), visited

    def answer(self, task: BenchTask, reader: SpanReader, models: ModelCounter) -> ArmAnswer:
        view = reader.view
        if self._matrix is None or self._folded_universe != view.universe_id:
            raise ArmUnavailable("incumbent tree was not folded over this universe",
                                 folded=self._folded_universe, asked=view.universe_id)
        qvec = np.asarray(self.encoder.query(task.question), dtype=np.float32)

        context_parts: list[str] = []
        retrieved: list[str] = []
        retrieved_texts: list[str] = []
        packets: list[dict[str, Any]] = []
        opened = 0
        # Two bounded rounds at beam then beam*2, exactly as v1 arm A.
        for round_no in range(1, ROUNDS + 1):
            self_beam = self.beam * (2 ** (round_no - 1))
            saved, self.beam = self.beam, self_beam
            try:
                ranked, materialized, visited = self.descend(qvec)
            finally:
                self.beam = saved
            hits = ranked[: self.k]
            packets.append({"round": round_no, "beam": self_beam, "k": self.k,
                            "materialized": materialized, "visited": len(visited),
                            "top_hits": [self._node_ids[r] for r in hits[:5]]})
            # THE SKIM: every hit's digest. Charged - the digests are text that reached context.
            for row in hits:
                node_id = self._node_ids[row]
                if node_id in retrieved:
                    continue
                context_parts.append(reader.read_text(self._digests[row]))
                retrieved.append(node_id)
                retrieved_texts.append(self._digests[row])
            # THE OPENS: top hits whole under the per-file cap, stopping once the atoms are there.
            for row in hits[:MAX_WHOLE_READS]:
                if opened >= MAX_WHOLE_READS:
                    break
                if score("\n".join(context_parts), task.atoms, task.window)[0]:
                    break
                node_id = self._node_ids[row]
                whole = view.node_text(node_id)
                encoded = whole.encode("utf-8")
                excerpt = (encoded[:FILE_READ_CAP].decode("utf-8", errors="replace")
                           if len(encoded) > FILE_READ_CAP else whole)
                context_parts.append(reader.read_node_excerpt(node_id, excerpt))
                # The opened file's text REPLACES its digest as this rank's evidence: what the
                # arm actually put in front of the scorer at that rank is the file, not the line.
                if node_id in retrieved:
                    retrieved_texts[retrieved.index(node_id)] = excerpt
                opened += 1
            if score("\n".join(context_parts), task.atoms, task.window)[0]:
                break

        return ArmAnswer(
            context="\n".join(context_parts), rounds=len(packets),
            retrieved=retrieved, retrieved_texts=retrieved_texts,
            note=f"beam {self.beam}/{self.beam * 2}, {opened} whole opens, {len(retrieved)} digests",
            detail={"packets": packets, "generation_id": self.generation_id},
        )
