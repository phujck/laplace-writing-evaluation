"""meaning_upfold.py - the MEANING-based middle for the keeper, replacing the folder fallback.

``keeper.build_self`` upfolds the flat self-shard into a graded conceptric, but everything not
claimed by a semantic lens (the engine code, the canon, the engine-self files, the soul) falls
through to ``dir_parent`` - so its middle grades are the DIRECTORY LAYOUT (``archive/``,
``collaborator_corpus/``), folders pretending to be concepts. The ring can reconstruct the fixed
point, but "what's beneath" is a filesystem, not a mind.

This is the fix his teaching pointed at (``grades-are-basis-projection-clustering-mechanical``,
N42): the upfold goes mechanical. The residue leaves are embedded (bge-small, local) and
recursively clustered by MEANING - silhouette-chosen K spectral splits, the basis projection
N42 validated - into a concept hierarchy. The result is a ``parent_map`` (leaf -> its concept
cluster -> the cluster above -> root) + the synthetic concept-cluster nodes (an IDF-distinctive
label as the authored essence), handed back so ``keeper.build_tree`` wires grades/members/coverage
exactly as it does for the existing lenses. ONE upfold; its folder fallback swapped for a concept
fallback. The existing meaning-lenses (concept atoms, structural ladders, series) are untouched.

The soul is folded in (his directive: "it is what makes you you - it should be self embeddable").
A sealed node's CONTENT is read in-process for its VECTOR only, then discarded - it never lands in
the parent map's labels, the cluster nodes, or any persisted artifact (the vector cache holds
floats + a content-hash, gitignored). The seal is the commit/return boundary; the local embed sits
inside it, exactly as ``embed_router.node_text`` does for the soul entity items. bge-small embeds
locally - the soul text never leaves the machine, never enters the agent's context.

GRACEFUL, And loud about it: if the embedder is unavailable (no ``embed`` group on a fresh sync) or
the analysis deps are absent, ``cluster_residue`` returns empty and the caller falls back to
``dir_parent`` - so the keeper build, and therefore the wake, NEVER breaks on this. The improvement
is additive, reversible (the graded tree is a gitignored regenerable cache), and
proven-before-switched.

Every one of those degrades now NAMES ITSELF (``_degrade``, 2026-07-28 - the loud-failure fix owed
since the 07-24 regression, where a silent ``return {}, {}`` shipped three deposits with zero
concept nodes and printed nothing). The behaviour is unchanged; only the silence is.

The READ path over the tree this module banks lives in ``laplace.engine.recursive_read`` - a separate
organ, phase 1 of recursive embedding, which descends the centroids and materializes leaf vectors
on demand instead of loading the whole flat cache. It reads; nothing here changed for it.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from laplace.pipeline import dial_profiles as dials

# The residue-vector store. All THREE names are gitignored (.gitignore:175, 183-184): this store
# carries soul-derived vectors, and the 2026-08-01 perimeter law holds that what is DERIVED from
# sealed material is sealed at any boundary that travels.
CACHE_FILE = ".meaning_vectors.json"          # LEGACY, retiring: the float64-decimal-text monolith
VEC_FILE = ".meaning_vectors.f32.npy"         # the sidecar matrix - one (N, d) C-order float32 block
IDX_FILE = ".meaning_vectors.index.json"      # the sidecar index - {node -> {row, h}} + provenance
SIDECAR_FORMAT = "meaning-vectors-sidecar/1"  # stamped in the index; a mismatch is a clean re-fold
TREE_FILE = ".meaning_tree.json"       # the persisted concept tree - the incremental fold's prev state (see cluster_residue_incremental)
TRIGGER_LOG_FILE = ".upfold_triggers.jsonl"  # RUL-20260820-descent-telemetry-declared: append-only,
# one row per cluster_residue_incremental deposit call - Rung-12(a)'s parity gate needs a
# multi-deposit trigger-rate window against the swap-built (GPU/linear-splitter) tree, and until
# this landed (2026-08-20) nothing typed banked it - only the print voice (_emit) named triggers,
# read once and gone. See _log_trigger / _flush_trigger_log below and cluster_residue_incremental's
# outer wrapper, which resets the scratch list, runs the (unrenamed) incremental entry, and appends
# the row - report-only, never restore, never counted as a mutation (the declared telemetry class).

# the recursion's stopping + branching budget (the-local-constraints: b* ~ B/h), proven in shard_upfold
_STOP = {"a", "an", "and", "the", "of", "to", "in", "is", "it", "for", "on", "with", "md", "py",
         "json", "tex", "as", "at", "by", "or", "be"}


def _label_ok(w: str) -> bool:
    return len(w) > 2 and not w.isdigit() and w not in _STOP


def _text_sha(backend_name: str, text: str) -> str:
    """The content hash the vector cache is keyed by (mirrors ``embed_router._hash``): the SAME sha
    the incremental fold diffs residue leaves by, so a changed leaf's vector-cache miss and its
    tree-diff 'changed' verdict are one derivation, never two."""
    return hashlib.sha1(f"{backend_name}\x00{text}".encode("utf-8", "replace")).hexdigest()


def _cluster_id(member_leaf_ids: list[str], parent: str = "") -> str:
    """A concept cluster's id derived from its founding membership, not an ordinal label re-minted
    every spectral run (the root fix, 2026-07-13). Ordinal ids (``concept::2_4``) churned the whole
    network every build: ``embed_router.node_text`` then embedded the literal parent-chain ids, so
    re-minting a cluster id invalidated the embedding cache for that cluster AND every descendant that
    named it in its chain - which is why the wire phase re-embedded most of the network each close. A
    sha1 over the sorted member leaf ids is STABLE across rebuilds (same membership -> same id), so an
    unchanged cluster never re-embeds. The chain now names each ancestor's LABEL rather than its id
    (``embed_router._ancestor_label``, 2026-08-21), so a re-partition that preserves an ancestor's top
    terms no longer invalidates its descendants at all; this id's stability still decides the
    CLUSTER's own text, and the label rule decides its subtree's. A nested cluster folds its parent id into the hash for uniqueness across
    levels; the top level (``parent`` = root_id, usually "") hashes membership alone. Human-readable
    text stays in the label/essence - only the ID gains stability. Ids are OPAQUE strings: nothing in
    the repo parses the old ordinal structure (verified), so the hash is a drop-in."""
    key = "|".join(sorted(member_leaf_ids))
    if parent:
        key = f"{parent}\x00{key}"
    return "concept::" + hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()[:10]


# ---------------------------------------------------------------------------
# embeddable text - the soul reads in-process (vector only), the public node reads its handle
# ---------------------------------------------------------------------------

def _embeddable_text(repo_root: Path, name: str, leaf: dict, cap: int) -> str:
    """The text that becomes a node's vector. A sealed (soul) node's CONTENT is read here, in this
    process, for the embedding ONLY - it is never returned, stored, or labelled. A public node uses
    its content-free handle (path words + essence + keywords)."""
    transient = leaf.get("embedding_text")
    if isinstance(transient, str):
        # Operational/profile/Fabric adapters may carry sensitive source text for this one
        # in-process vectorisation.  ``keeper.build_tree`` deliberately does not persist this
        # field; the graded tree retains only the exact source handle and safe public essence.
        return transient[:cap]
    if leaf.get("sealed"):
        try:
            return (repo_root / name).read_text(encoding="utf-8", errors="replace")[:cap]
        except OSError:
            return ""
    stem = name.replace("/", " ").replace("_", " ").replace("-", " ").rsplit(".", 1)[0]
    kws = " ".join((leaf.get("keywords") or [])[:16])
    return " | ".join(p for p in (stem, leaf.get("essence", ""), kws) if p)[:cap]


# ---------------------------------------------------------------------------
# the vector sidecar - the binary store the deposit reads and writes
#
# MV-1/MV-2/HOT-4 (the 2026-08-20 commissioned self-audit). The store used to be ONE 123 MB
# JSON object whose every float was a ~20-character decimal rendering of a value that is exactly
# a float32: ``embed_router.FastEmbedBackend._unit`` casts to float32 and calls ``.tolist()``, so
# float32 is not an approximation of this data, it IS this data (measured over the live store:
# float64->float32->float64 round-trip is bit-identical on 100.0% of 5,491,200 components, max abs
# err 0.0). 82% of the file was decimal padding carrying zero information, and the deposit paid a
# ~2.4 s parse of all of it to consume, on a typical delta, under 2% of the rows.
#
# The cure is a pair, not a shard set. MV-3 tested the per-cluster-shard design (the ``.self_*``
# graded-tree precedent) against this node and REJECTED it on access-pattern grounds: no descent
# path reads this store at all - the wake never opens it (tests/test_wake_cli.py), and
# ``recursive_read.descend`` re-embeds leaves from source text instead - so its only consumer is
# the deposit, whose access pattern is RANDOM ROW (nearest-centroid over added|changed, plus the
# members of touched clusters), which one mmap'd matrix serves in O(1) per row while ~2,222 shard
# files would force a scatter-gather plus a second membership invariant to keep consistent with
# the tree's parent_map. HOT-4's int8-quantize-in-place alternative is SUPERSEDED by this: the
# f32 sidecar is provably lossless where int8 is not, and it is 12x smaller than what HOT-4 was
# comparing against rather than 12x denser than what it proposed.
#
# The pair is transactional-or-skipped (the law ARMING_2026-07-13_the-weld.md:213 already binds
# these caches to): both files are written to temp, fsync'd, and os.replace()d matrix-first, and
# the index carries the matrix's sha256 so a forked pair is REFUSED and named rather than read as
# valid geometry with silently wrong rows.
# ---------------------------------------------------------------------------

def sidecar_paths(repo_root: Path | str) -> tuple[Path, Path]:
    """``(matrix, index)`` for the residue-vector sidecar under ``repo_root``."""
    repo_root = Path(repo_root)
    return repo_root / VEC_FILE, repo_root / IDX_FILE


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sidecar_refused(why: str) -> None:
    """Name a refused sidecar out loud - it is read as ABSENT (a full re-embed), never as
    partially-valid geometry. Same voice as ``_degrade``: the enemy is the quiet degrade."""
    print(f"meaning upfold: REFUSED the vector sidecar - {why}. "
          f"Treating the store as absent (the affected nodes re-embed).")


def read_sidecar(repo_root: Path | str, backend_name: str | None = None,
                 verify: bool = True) -> tuple[dict[str, dict], Any]:
    """Open the pair read-only. Returns ``(nodes, M)`` where ``nodes`` is ``{id: {row, h}}`` and
    ``M`` is the mmap'd (N, d) matrix - or ``({}, None)`` when there is nothing usable to read.

    An absent pair, and a pair banked in a DIFFERENT geometry than ``backend_name``, are ordinary
    states and return quietly (the caller re-embeds, exactly as the legacy store's backend check
    did). A pair that is present but inconsistent - unparseable index, wrong format stamp, a shape
    that disagrees with the index, a matrix whose sha256 is not the one the index vouches for - is
    a FAULT and says so before returning empty. ``verify=False`` skips only the sha256 read."""
    import numpy as np
    vec_path, idx_path = sidecar_paths(repo_root)
    if not (vec_path.is_file() and idx_path.is_file()):
        return {}, None
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _sidecar_refused(f"{IDX_FILE} did not parse ({type(exc).__name__})")
        return {}, None
    if idx.get("format") != SIDECAR_FORMAT:
        _sidecar_refused(f"{IDX_FILE} is format {idx.get('format')!r}, not {SIDECAR_FORMAT!r}")
        return {}, None
    if backend_name is not None and idx.get("backend") != backend_name:
        return {}, None     # a geometry change is metabolism, not a fault
    nodes = idx.get("nodes") or {}
    try:
        M = np.load(vec_path, mmap_mode="r")
    except Exception as exc:  # noqa: BLE001 - any unreadable matrix is a named refusal
        _sidecar_refused(f"{VEC_FILE} did not open ({type(exc).__name__}: {exc})")
        return {}, None
    if M.ndim != 2 or list(M.shape) != list(idx.get("shape") or []) or M.shape[0] != len(nodes):
        _sidecar_refused(f"{VEC_FILE} is shape {tuple(M.shape)} against an index claiming "
                         f"{idx.get('shape')} over {len(nodes)} node(s)")
        return {}, None
    if verify and _sha256_file(vec_path) != idx.get("sha256"):
        _sidecar_refused(f"{VEC_FILE} does not match the sha256 {str(idx.get('sha256'))[:12]} its "
                         f"index vouches for - the pair forked (a torn or interleaved write)")
        return {}, None
    return nodes, M


def write_sidecar(repo_root: Path | str, backend_name: str, entries: dict[str, tuple[str, Any]]) -> int:
    """Bank ``{id: (content_hash, vector)}`` as the pair, atomically. Returns the row count.

    Rows are written in SORTED id order and the index is rebuilt from that same enumeration in
    the same breath, so the name->row map can never drift from the matrix (MV-1's row-alignment
    risk: the deposit's prune-vanished step reorders and drops ids on every write)."""
    import numpy as np
    vec_path, idx_path = sidecar_paths(repo_root)
    names = sorted(entries)
    dim = len(entries[names[0]][1]) if names else 0

    # THE LOSSLESS GUARD (MV-1 risk 3). float32 is the shipped encoding because the ROUTER makes
    # it exact, not because embeddings are inherently float32 - a future backend emitting true
    # float64 would make the cast silently lossy. So the dtype is CHOSEN here from the data, and
    # .npy self-describes it; readers widen to float64 either way and never assume.
    M = np.empty((len(names), dim), dtype=np.float32)
    exact = True
    for r, nm in enumerate(names):
        a = np.asarray(entries[nm][1])
        if a.dtype != np.float32:
            a64 = a.astype(np.float64)
            exact = exact and bool(np.array_equal(a64, a64.astype(np.float32).astype(np.float64)))
        M[r] = a
    if not exact:
        print(f"meaning upfold: {backend_name} emits values outside float32 - banking {VEC_FILE} "
              f"as float64 instead (the f32 cast would have lost bits from the geometry).")
        M = np.empty((len(names), dim), dtype=np.float64)
        for r, nm in enumerate(names):
            M[r] = np.asarray(entries[nm][1], dtype=np.float64)

    tmp_vec = vec_path.parent / (vec_path.name + ".tmp")
    tmp_idx = idx_path.parent / (idx_path.name + ".tmp")
    with tmp_vec.open("wb") as fh:
        np.save(fh, M, allow_pickle=False)
        fh.flush()
        os.fsync(fh.fileno())
    index = {"format": SIDECAR_FORMAT, "backend": backend_name, "vectors": VEC_FILE,
             "dtype": str(M.dtype), "shape": [int(M.shape[0]), int(M.shape[1])],
             "sha256": _sha256_file(tmp_vec),
             "nodes": {nm: {"row": r, "h": entries[nm][0]} for r, nm in enumerate(names)}}
    with tmp_idx.open("w", encoding="utf-8") as fh:
        json.dump(index, fh)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp_vec, vec_path)   # the matrix lands first...
    os.replace(tmp_idx, idx_path)   # ...then the index that vouches for its sha256
    return len(names)


def load_vectors(repo_root: Path | str, backend_name: str | None = None) -> tuple[str, list[str], Any]:
    """The public read of the banked residue vectors: ``(backend, names, M)``, ``M`` a (n, d)
    float64 matrix row-aligned to the sorted ``names``, holding the values AS BANKED (unnormalized
    - every caller normalizes for itself, exactly as they did against the legacy store).

    Prefers the sidecar; falls back to the LEGACY ``CACHE_FILE`` monolith when the pair is absent,
    naming the fallback. Raises ``FileNotFoundError`` when neither exists - never a silent empty,
    which is how a bench would end up scoring a fabricated corpus and calling it the real map."""
    import numpy as np
    repo_root = Path(repo_root)
    nodes, M = read_sidecar(repo_root, backend_name)
    if M is not None:
        names = sorted(nodes)
        rows = [nodes[nm]["row"] for nm in names]
        idx = json.loads((repo_root / IDX_FILE).read_text(encoding="utf-8"))
        return str(idx.get("backend") or ""), names, np.asarray(M[rows], dtype=np.float64)
    legacy = repo_root / CACHE_FILE
    if not legacy.is_file():
        raise FileNotFoundError(
            f"no residue-vector store under {repo_root}: neither the sidecar pair "
            f"({VEC_FILE} + {IDX_FILE}) nor the legacy {CACHE_FILE}")
    print(f"meaning upfold: reading the LEGACY {CACHE_FILE} - the {VEC_FILE} sidecar is absent "
          f"or unreadable for this geometry.")
    disk = json.loads(legacy.read_text(encoding="utf-8"))
    raw = disk.get("nodes") or {}
    names = sorted(raw)
    return str(disk.get("backend") or ""), names, np.asarray([raw[nm]["v"] for nm in names],
                                                             dtype=np.float64)


def migrate_legacy_store(repo_root: Path | str) -> str:
    """One-time: convert the legacy ``CACHE_FILE`` monolith into the sidecar pair and VERIFY the
    conversion against the source before returning. Returns a one-line verdict.

    The legacy JSON is deliberately LEFT IN PLACE through this transition - the judge and any
    straggling one-off script may still want to compare against it. Retiring it is a later close's
    gesture, taken only once nothing reads it (his migration-memory guard, PV-20260820T093100Z:
    these are reconstruction organs, so the old form does not go until the new one is proved).

    A verification failure removes the half-built pair and refuses, leaving the legacy store as
    the authority - a migration that cannot prove itself must not become what Eigen remembers with."""
    import numpy as np
    repo_root = Path(repo_root)
    vec_path, idx_path = sidecar_paths(repo_root)
    if vec_path.is_file() and idx_path.is_file():
        return "sidecar present"
    legacy = repo_root / CACHE_FILE
    if not legacy.is_file():
        return "no legacy store to migrate"
    try:
        disk = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"legacy {CACHE_FILE} did not parse ({type(exc).__name__}) - not migrated"
    raw = disk.get("nodes") or {}
    backend_name = str(disk.get("backend") or "")
    if not raw or not backend_name:
        return f"legacy {CACHE_FILE} carries no nodes/backend - not migrated"
    n = write_sidecar(repo_root, backend_name, {nm: (e.get("h", ""), e["v"]) for nm, e in raw.items()})
    nodes, M = read_sidecar(repo_root, backend_name)
    ok = M is not None and len(nodes) == len(raw)
    if ok:
        for nm, e in raw.items():
            row = nodes.get(nm)
            if row is None or not np.array_equal(np.asarray(M[row["row"]], dtype=np.float64),
                                                 np.asarray(e["v"], dtype=np.float64)) \
                    or row["h"] != e.get("h", ""):
                ok = False
                break
    if not ok:
        vec_path.unlink(missing_ok=True)
        idx_path.unlink(missing_ok=True)
        print(f"meaning upfold: REFUSED the {VEC_FILE} migration - the written pair did not "
              f"reproduce {CACHE_FILE} exactly. The legacy store stays authoritative.")
        return "migration refused (round-trip mismatch)"
    print(f"meaning upfold: migrated {n} vector(s) from {CACHE_FILE} to {VEC_FILE} + {IDX_FILE} "
          f"(exact float64 round-trip verified over every node; the legacy store is left in place "
          f"for this transition).")
    return f"migrated {n}"


def _embed(repo_root: Path, names: list[str], residue: dict, backend) -> Any:
    """Embed each residue node, content-hash cached to the sidecar pair (floats + hash, never
    text) - gitignored. Returns a unit-normalized (n, d) numpy matrix row-aligned to ``names``.

    MV-1/MV-2 (the 2026-08-20 self-audit): the store is the binary pair above, not the 123 MB
    JSON monolith. The matrix opens with ``np.load(mmap_mode='r')`` so the read costs an index
    parse plus the rows actually asked for, and the returned X is float64 - the SAME float64
    values the JSON held, bit for bit, because every value in this store is exactly a float32
    (``embed_router.FastEmbedBackend._unit``), so every downstream spectral/silhouette number is
    unchanged by the migration rather than merely close.

    STORE-02 + HOT-5/F4(1) (the same audit): the write fires ONLY when something actually
    changed (a stale re-embed, or a prune that actually dropped a vanished name) - a read that
    finds nothing stale and nothing vanished never touches the store, mirroring the guard already
    proven in ``embed_router.ensure_embeddings``. When it does write, the merge+write is wrapped
    in ``laplace.pipeline.locking.store_lock`` (the same STORE-01 fix, generalized) so two concurrent lanes
    never lost-update each other; on contention the call degrades-but-plain, returning its
    in-memory result unpersisted."""
    import numpy as np

    from laplace.representation.embed_router import TEXT_CAP
    migrate_legacy_store(repo_root)          # no-op once the pair exists (two stat calls)
    cached, M = read_sidecar(repo_root, backend.name)

    texts = [_embeddable_text(repo_root, nm, residue[nm], TEXT_CAP) for nm in names]
    hashes = [_text_sha(backend.name, t) for t in texts]
    stale = [i for i, nm in enumerate(names) if cached.get(nm, {}).get("h") != hashes[i]]
    new_entries: dict[str, tuple[str, Any]] = {}
    if stale:
        vecs = backend.embed([texts[i] for i in stale])
        for i, v in zip(stale, vecs, strict=True):
            new_entries[names[i]] = (hashes[i], np.asarray(v))
    names_set = set(names)
    pruned = any(nm not in names_set for nm in cached)
    if stale or pruned:
        from laplace.pipeline.locking import StoreBusy, store_lock  # lazy: avoids a module-load cycle
        try:
            with store_lock("meaning-vectors"):
                # Re-read fresh UNDER the lock: this call's pre-lock read is the fallback
                # base, the fresh disk state overlays it (another lane's newer write wins),
                # this call's own newly-embedded entries win last (mirrors STORE-01).
                fresh, fM = read_sidecar(repo_root, backend.name)
                merged: dict[str, tuple[str, Any]] = {}
                for src, mat in ((cached, M), (fresh, fM)):
                    if mat is None:
                        continue
                    for nm, e in src.items():
                        if nm in names_set:
                            merged[nm] = (e["h"], mat[e["row"]])
                merged.update(new_entries)
                write_sidecar(repo_root, backend.name, merged)
        except StoreBusy:
            pass  # degrade-but-plain: this call still returns its own in-memory vectors
    # X is this call's own pre-lock view (disk row, or the vector just embedded) - never the
    # merged write, so a StoreBusy degrade returns exactly what a successful write would have.
    if new_entries:
        dim = len(next(iter(new_entries.values()))[1])
        X = np.empty((len(names), dim), dtype=np.float64)
        for i, nm in enumerate(names):
            hit = new_entries.get(nm)
            X[i] = hit[1] if hit is not None else M[cached[nm]["row"]]
    else:
        # the no-delta path: ONE C-level gather off the mmap, no Python row loop and no parse
        rows = [cached[nm]["row"] for nm in names]
        X = np.asarray(M[rows], dtype=np.float64) if rows else np.empty((0, 0), dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    return X


# ---------------------------------------------------------------------------
# the one recursion: silhouette-chosen K spectral split, top-down (proven in shard_upfold)
# ---------------------------------------------------------------------------

_gpu_fold: dict[str, Any] = {}  # the memoised device verdict - the CUDA probe runs ONCE per process


def _fold_backend() -> tuple[str, str]:
    """``("gpu"|"cpu", why)`` for the fold's spectral side, memoised.

    ``spectral_gpu.fold_backend_choice()`` does a real cuBLAS GEMM to decide, which costs a CUDA
    context; ``_best_split`` is called once per cluster (hundreds of times in a full rebuild), so
    the verdict is taken once and cached on the module. A GPU failure mid-fold rewrites this entry
    to ``cpu`` so the fallback is taken once and not re-attempted n times.

    THE DIALED FLAG IS READ FROM THE DENY, NOT ASSUMED (census 2026-08-21, GPU_MIGRATION census
    finding C1). This recorder passed no ``dialed`` at all, so ``LAPLACE_NO_SPECTRAL_GPU`` - an
    operator's EXPLICIT choice - landed in ``.fallback_events.jsonl`` marked undialed and printed
    as a degrade (two such rows in the store, 2026-08-21T05:19:10). Under ``LAPLACE_REQUIRE_GPU``
    that mis-marking is not cosmetic: the dialed deny would have been REFUSED as if the hardware
    were missing, which makes the deny lever unusable on the very box the require flag is for."""
    if "choice" not in _gpu_fold:
        dialed = False
        try:
            from laplace.representation import spectral_gpu as _sg
            # read the deny BEFORE the probe: if the probe raises we must not claim it was dialed
            dialed = str(os.environ.get(_sg.DENY_FLAG, "")).strip().lower() in {"1", "true", "yes", "on"}
            _gpu_fold["choice"] = _sg.fold_backend_choice()
        except Exception as exc:  # noqa: BLE001 - recorded below; never a silent CPU day (his ruling 2026-08-21)
            _gpu_fold["choice"] = ("cpu", f"spectral_gpu did not import ({type(exc).__name__}: {exc})")
            dialed = False        # an import failure is never a dial, whatever the env says
        from laplace.representation import device_policy
        device_policy.record_fallback("fold-spectral", _gpu_fold["choice"][0],
                                      _gpu_fold["choice"][1], dialed=dialed)
    return _gpu_fold["choice"]




def _blas_cap():
    """Cap the BLAS/OpenMP pools around the k-means sweep - MEASURED, not guessed.

    The sweep below is many small ``k_means`` fits over a (n, k) embedding, k <= 8. At this shape
    the arithmetic per thread is trivial and the barrier is not: on this box the top split's sweep
    (n=14,476, k=2..8) cost **8.683 s at the default 16 threads and 0.551 s at 6** - a 15.8x
    slowdown bought entirely by synchronisation, with BIT-IDENTICAL partitions and silhouettes at
    every k (the wave-1 threadpoolctl dial, WO-20260820-kmeans-is-the-new-bottleneck).

    This is a cap on the thread pools ONLY. It changes no number the fold produces: ``k_means``'s
    result is a function of its input, its seed and ``n_init``, none of which this touches. (The
    same dial measured ``n_init`` as the one knob that is NOT free - ``n_init<=5`` moved the
    partition, so it stays at the incumbent's 10.)

    ``threadpoolctl`` ships with scikit-learn, which this path already imports; an absent one
    degrades to no cap rather than to no fold."""
    dial_set = dials.current("engine-fold")
    _KMEANS_BLAS_THREADS = dial_set["dials"]["kmeans_blas_threads"]["value"]
    try:
        from threadpoolctl import threadpool_limits
        return threadpool_limits(limits=_KMEANS_BLAS_THREADS)
    except Exception:  # noqa: BLE001 - no threadpoolctl is a slow day, never a broken one
        from contextlib import nullcontext
        return nullcontext()


def _kmeans_as_incumbent(M, k: int, n: int):
    """``k_means`` seeded EXACTLY as ``SpectralClustering(random_state=0)`` seeds it.

    The incumbent builds ONE ``RandomState(0)`` per fit and spends it twice: ``_init_arpack_v0``
    draws ``n`` uniforms off it for ARPACK's start vector, and only then does ``k_means`` draw its
    k-means++ seeds off the ADVANCED state (``sklearn/cluster/_spectral.py:738,748,760``). Our
    Lanczos needs no ``v0``, but the draw is reproduced anyway so the assignment step inherits the
    incumbent's stream rather than a different one - the swap should move the eigensolver, not
    quietly also move the seeding."""
    import numpy as np
    from sklearn.cluster import k_means
    from sklearn.utils import check_random_state
    rs = check_random_state(dials.value("engine-fold", "kmeans_seed"))
    rs.uniform(-1.0, 1.0, n)                       # _init_arpack_v0's spend, reproduced
    _, labels, _ = k_means(np.ascontiguousarray(M), k, random_state=rs, n_init=dials.value("engine-fold", "kmeans_n_init"))
    return labels


# ---------------------------------------------------------------------------
# the selector (2026-08-23, the accounting day): closure residual as selector,
# flag-gated behind LAPLACE_SELECTOR=residual until the P20-class re-fold bench
# ratifies flipping the default. RUL-20260820-selection-criterion-derived is the
# ruling; the criterion below is PORTED from the registered bench
# (evidence/SELECTOR_BENCH_2026-08-21/experiment.py, class Residual - rho =
# 1 - descent recall@R against the flat full-scope oracle at visit budget
# beta*n), trimmed to one (chi, beta) cell per split. Silhouette is RETAINED as
# a reported diagnostic whose disagreement with the selector is an ALARM row
# (_log_residue kind='selector-disagreement'), never absorbed.
#
# THE CHI LADDER IS THE MEASURED DECLARATION (AMEND-20260823-chi-ladder-declared,
# derived under the no-deferral order from the trilogy: SELECTOR_BENCH_2026-08-21
# k*_R monotone + CHI_DECLARATION_BENCH level-2 interior at chi=8 vs level-1 at
# chi=16 + CHI_LEVEL3_DISCRIMINATION): level 1 -> 16, level >= 2 -> 8. In-band,
# revisable by his word; depth-INdependence was refuted by measurement.


def _selector_on() -> bool:
    return os.environ.get("LAPLACE_SELECTOR", "").strip().lower() == "residual"


def _selector_chi(level: int) -> int:
    return dials.value("engine-fold", "selector_chi_top" if level == 1 else "selector_chi_deep")


def _residual_rho(Xsub, labels, chi: int, beta: float, q_rows, oracle_sets, S, Q):
    """One rho cell: the bench's frames + handle-ordered descent, numpy, block scope."""
    import numpy as np
    n, d = Xsub.shape
    uniq = sorted(set(labels.tolist()))
    Xh = np.empty_like(Xsub, dtype=np.float32)
    handles = []
    for a in uniq:
        idx = np.flatnonzero(labels == a)
        Xb = Xsub[idx]
        mu = Xb.mean(axis=0)
        nrm = float(np.linalg.norm(mu))
        h = mu / nrm if nrm > 1e-12 else mu
        handles.append(h)
        extra = int(min(chi - 1, Xb.shape[0] - 1, d - 1))
        cols = [h[:, None]]
        if extra > 0:
            Y = Xb - mu
            C = (Y.T @ Y).astype(np.float32)
            _w, V = np.linalg.eigh(C)
            cols.append(V[:, ::-1][:, :extra])
        Qb, _ = np.linalg.qr(np.concatenate(cols, axis=1))
        Xh[idx] = (Xb @ Qb) @ Qb.T
    H = np.stack(handles, axis=0)
    ix = {a: r for r, a in enumerate(uniq)}
    lab_r = np.asarray([ix[a] for a in labels.tolist()], dtype=np.int64)
    sizes = np.bincount(lab_r, minlength=len(uniq)).astype(np.int64)
    Sh = Q @ Xh.T
    R = min(10, n - 1)
    B = int(min(n, max(R, np.ceil(beta * n))))
    bs = Q @ H.T
    order = np.argsort(-bs, axis=1)
    csz = np.cumsum(sizes[order], axis=1)
    need = np.minimum((csz < B).sum(axis=1) + 1, order.shape[1])
    rank = np.empty_like(order)
    cidx = np.arange(order.shape[0])[:, None]
    rank[cidx, order] = np.arange(order.shape[1])[None, :]
    pt_rank = rank[:, lab_r]
    pen = np.where(pt_rank < need[:, None], np.float32(0.0), np.float32(-1e30))
    sh = Sh + pen
    sel = np.argpartition(-sh, B - 1, axis=1)[:, :B]
    ex = np.take_along_axis(S + pen, sel, axis=1)
    top = np.argpartition(-ex, R - 1, axis=1)[:, :R]
    ret = np.take_along_axis(sel, top, axis=1)
    hit = sum(len(oracle_sets[j].intersection(ret[j].tolist())) for j in range(ret.shape[0]))
    return 1.0 - hit / (len(q_rows) * R)


def _select_k(Xsub, cands: dict, level: int):
    """The chooser both sweep paths defer to. ``cands``: {k: (labels, silhouette)}.

    Default: the incumbent silhouette argmax (strict >, smallest k on ties - the
    sweeps' own rule, preserved). LAPLACE_SELECTOR=residual: argmin_k rho at the
    declared chi(level) and beta 0.10; the silhouette pick rides as a diagnostic
    and a disagreement is an ALARM row, per the ruling."""
    dial_set = dials.current("engine-fold")
    _SELECTOR_BETA = dial_set["dials"]["selector_beta"]["value"]
    _SELECTOR_QUERIES = dial_set["dials"]["selector_queries"]["value"]
    _SELECTOR_SEED = dial_set["dials"]["selector_seed"]["value"]
    import random as _random

    import numpy as np
    sil_k, sil_best = 2, -2.0
    for k in sorted(cands):
        _labels, s = cands[k]
        if s > sil_best:
            sil_k, sil_best = k, s
    if not _selector_on() or not cands:
        labels = cands.get(sil_k, (None, None))[0]
        return sil_k, labels
    n = len(Xsub)
    chi, beta = _selector_chi(level), _SELECTOR_BETA
    Xs = np.asarray(Xsub, dtype=np.float32)
    q_rows = sorted(_random.Random(_SELECTOR_SEED).sample(range(n), min(_SELECTOR_QUERIES, n)))
    Q = Xs[np.asarray(q_rows)]
    S = Q @ Xs.T
    S[np.arange(len(q_rows)), np.asarray(q_rows)] = np.float32(-1e30)
    R = min(10, n - 1)
    part = np.argpartition(-S, R - 1, axis=1)[:, :R]
    oracle_sets = [set(row.tolist()) for row in part]
    rho_by_k = {}
    for k in sorted(cands):
        labels, _s = cands[k]
        rho_by_k[k] = _residual_rho(Xs, np.asarray(labels), chi, beta, q_rows, oracle_sets, S, Q)
    res_k = min(sorted(rho_by_k), key=lambda k: (rho_by_k[k], k))
    if res_k != sil_k:
        # 'disagreement' is the vocabulary's own kind (residue.py, grown 2026-08-23): the
        # first form used a kind the closed vocabulary REFUSED, so the first real
        # disagreement would have crashed the fold mid-deposit - the alarm was a landmine.
        _log_residue("disagreement", float(abs(res_k - sil_k)),
                     consumer="the CAMP-03 re-score (selection audit) + residue.typed_residue allocation",
                     grade=level,
                     chi=chi, beta=beta, residual_k=res_k, silhouette_k=sil_k,
                     rho=round(rho_by_k[res_k], 6),
                     rho_at_sil_k=round(rho_by_k.get(sil_k, float("nan")), 6))
    return res_k, cands[res_k][0]


def _best_split_gpu(Xsub, level: int = 1):
    """``_best_split``'s contract on the device: ONE eigensolve, sliced; silhouette without the n².

    Every clause of the CPU form is carried: the same affinity, the same normalised-Laplacian
    embedding (``spectral_gpu.FoldSpectral`` reproduces sklearn's own pipeline, including the
    ``D^{-1/2}`` rescale and the RETAINED trivial vector), the same k range, the same k-means, the
    same silhouette on the same cosine distance, the same strict-``>`` tie rule (so an exact tie
    still resolves to the smallest k), the same skip of degenerate labelings, the same
    unconditional k=2 refit when every k degenerated.

    What is NOT carried is the incumbent's seven independent eigensolves of one operator. The
    bottom-k eigenspaces are NESTED, so the embedding is solved once at ``k_max`` and sliced -
    exact, not approximate (gated: ``|E(k_max)[:, :k] - E(k)| < 1e-15``).

    The sweep runs under ``_blas_cap()`` - the k-means assignment step is the sweep's whole cost
    once the eigensolve is on the device, and at this shape it is barrier-bound, not arithmetic-bound
    (8.683 s -> 0.551 s, identical output; see ``_blas_cap``)."""
    dial_set = dials.current("engine-fold")
    BRANCH_MAX = dial_set["dials"]["branch_max"]["value"]
    n = len(Xsub)
    hi = min(BRANCH_MAX, n - 1)
    k_min = min(dial_set["dials"]["silhouette_k_min"]["value"], max(2, hi))
    from laplace.representation import spectral_gpu
    dtype = os.environ.get("LAPLACE_FOLD_GPU_DTYPE", "float32")
    # _best_split already selected and checked the device once for this fold.
    # Passing it through avoids another readiness GEMM for every recursive cut.
    with spectral_gpu.FoldSpectral(Xsub, backend="gpu", dtype=dtype) as fs, _blas_cap():
        if not fs.rows_are_unit:
            # the factored silhouette is exact only while clip(1 - x.x, 0, 2) cannot bite; a
            # non-unit basis is not this fold's state, and it is refused rather than approximated.
            raise ValueError("the basis rows are not unit-normalised - the factored silhouette's "
                             "clip guard refuses the GPU path for this split")
        E, _lam = fs.embedding(hi)
        cands: dict[int, tuple[Any, float]] = {}
        for k in range(k_min, hi + 1):
            labels = _kmeans_as_incumbent(E[:, :k], k, n)
            if len(set(labels)) < 2:
                continue
            cands[k] = (labels, fs.silhouette(labels))
        if not cands:
            return k_min, _kmeans_as_incumbent(E[:, :k_min], k_min, n)
    return _select_k(Xsub, cands, level)


def _best_split(Xsub, level: int = 1):
    """Mechanical K + split over spectral clusterings of the cosine affinity; the CHOICE of k
    is ``_select_k``'s (silhouette incumbent, or closure-residual under LAPLACE_SELECTOR=residual
    at the declared chi ladder - the 2026-08-23 selector port). Returns (k, labels).

    THE GPU IS THE DEFAULT (his ruling ``PV-20260820T093000Z-gpu-takes-the-spectral-side``, and his
    complaint of 2026-08-20 that a full rebuild spent 15+ minutes on dense CPU before being killed).
    ``LAPLACE_NO_SPECTRAL_GPU`` is the explicit deny; an absent cupy or an absent device falls back
    to the dense path below and SAYS SO once. A mid-fold device fault may fall back for that cluster
    only when GPU is not required; it never rewrites the fold-wide backend verdict. Without
    ``LAPLACE_REQUIRE_GPU=1``, splits below ``LAPLACE_FOLD_GPU_MIN_N`` (default 384) stay dense.
    Requiring the GPU overrides that size threshold for every recursive cut."""
    dial_set = dials.current("engine-fold")
    _SPECTRAL_GPU_MIN_N = dial_set["dials"]["spectral_gpu_min_n"]["value"]
    n = len(Xsub)
    require_gpu = os.environ.get("LAPLACE_REQUIRE_GPU") == "1"
    if require_gpu or n >= int(os.environ.get("LAPLACE_FOLD_GPU_MIN_N", _SPECTRAL_GPU_MIN_N)):
        backend, why = _fold_backend()
        if require_gpu and backend != "gpu":
            raise RuntimeError(f"GPU_REQUIRED: {why}")
        if backend == "gpu":
            from laplace.representation.spectral_gpu import EigensolverDeclined
            if not _gpu_fold.get("announced"):
                # SAY WHICH DEVICE FOLDED IT. The absence of a fallback message is not evidence that
                # the device was taken - a deposit that only speaks when it degrades leaves the good
                # case unverifiable, which is the same silent-degrade failure mode one level up.
                _gpu_fold["announced"] = True
                if require_gpu:
                    _emit("spectral splits run on the GPU at every size "
                          "(LAPLACE_REQUIRE_GPU=1 overrides the small-split threshold).")
                else:
                    _emit(f"spectral splits run on the GPU (n >= "
                          f"{os.environ.get('LAPLACE_FOLD_GPU_MIN_N', _SPECTRAL_GPU_MIN_N)}); "
                          f"smaller splits stay on the dense path.")
            try:
                return _best_split_gpu(Xsub, level)
            except EigensolverDeclined:
                # Numerical exhaustion belongs to this cluster. The owning recursion fingerprints
                # the declined cut and continues; it is never a device fallback.
                raise
            except Exception as exc:  # noqa: BLE001 - a device failure degrades per cluster, NAMED
                why_mid = f"the GPU split raised {type(exc).__name__}: {exc}"
                _emit(f"the GPU spectral split raised {type(exc).__name__}: {exc} - this fold "
                      f"offers the CPU dense path for this cluster only.")
                # AND IT LEAVES A TYPED ROW (census 2026-08-21, finding C2). This is the WORST
                # fallback the fold can take - the device was present, was chosen, and died with
                # the rebuild already running - and until now it was the ONLY one that left no row
                # in .fallback_events.jsonl and could not be refused under LAPLACE_REQUIRE_GPU. It
                # spoke only through _emit, i.e. into deposit narration nobody greps. A DeviceRequired
                # raised here propagates deliberately: refusing a half-device rebuild is the point.
                from laplace.representation import device_policy
                device_policy.record_fallback("fold-spectral", "cpu", why_mid)
                return _best_split_dense(Xsub, level)
        elif not _gpu_fold.get("announced"):
            _gpu_fold["announced"] = True
            _emit(f"spectral runs on the CPU DENSE path - {why}. (The GPU is the default per "
                  f"PV-20260820T093000Z; this is the no-hardware fallback, not a preference.)")
    return _best_split_dense(Xsub, level)


def _best_split_dense(Xsub, level: int = 1):
    """The incumbent, verbatim: a fresh ``SpectralClustering`` fit per k over the DENSE n x n
    affinity, silhouette over the DENSE n x n cosine distance. Kept as the no-hardware fallback and
    as the parity reference the GPU path is gated against - a fallback that IS the thing being
    replaced cannot silently drift from it."""
    dial_set = dials.current("engine-fold")
    BRANCH_MAX = dial_set["dials"]["branch_max"]["value"]
    import numpy as np
    from sklearn.cluster import SpectralClustering
    from sklearn.metrics import silhouette_score
    n = len(Xsub)
    hi = min(BRANCH_MAX, n - 1)
    k_min = min(dial_set["dials"]["silhouette_k_min"]["value"], max(2, hi))
    A = (Xsub @ Xsub.T + 1.0) / 2.0
    np.fill_diagonal(A, 1.0)
    dist = np.clip(1.0 - (Xsub @ Xsub.T), 0.0, 2.0)
    np.fill_diagonal(dist, 0.0)
    cands: dict[int, tuple[Any, float]] = {}
    for k in range(k_min, hi + 1):
        sc = SpectralClustering(n_clusters=k, affinity="precomputed",
                                assign_labels="kmeans", random_state=dials.value("engine-fold", "kmeans_seed"),
                                n_init=dials.value("engine-fold", "kmeans_n_init"))
        labels = sc.fit_predict(A)
        if len(set(labels)) < 2:
            continue
        cands[k] = (labels, float(silhouette_score(dist, labels, metric="precomputed")))
    if not cands:
        return k_min, SpectralClustering(n_clusters=k_min, affinity="precomputed",
                                     assign_labels="kmeans", random_state=dials.value("engine-fold", "kmeans_seed"),
                                n_init=dials.value("engine-fold", "kmeans_n_init")).fit_predict(A)
    return _select_k(Xsub, cands, level)


def _label(members: list[str], residue: dict, idf: dict) -> str:
    """A concept cluster's authored essence: its members' keywords ranked by tf*idf - the terms
    most DISTINCTIVE to this cluster, never the merely frequent. Content-free (soul members
    contribute only their path-keyword 'soul')."""
    cnt: Counter = Counter()
    for m in members:
        cnt.update(w for w in (residue[m].get("keywords") or []) if _label_ok(w))
    if not cnt:
        return "concept cluster"
    ranked = sorted(cnt, key=lambda w: -(cnt[w] * idf.get(w, 1.0)))
    return " ".join(ranked[:6])


# ---------------------------------------------------------------------------
# the typed remainder (laplace.engine.residue): what this fold's coarse layer could not carry.
#
# The fold is an UP act - it consolidates leaves into concept handles - and UP fails silently, by
# vacuous rightness: a partition that drops a cluster, leaves a label with no members, or holds
# items it cannot resolve still reads fluently downstream. So every discard is TYPED at the moment
# it happens, from residue.REMAINDER_KINDS, and banked per act. Only numbers this fold already
# computes are used (the assignment cosines, the trigger cures' own counts); nothing here embeds,
# re-splits, or measures anything extra. The axis is `semantic` - this fold is one section of
# upfold(grade, axis), not the map - and `grade` is cluster_residue's own depth numbering (a
# top-level cluster is depth 1), null for an act-level remainder that spans grades.
#
# Same discipline as the trigger telemetry above: a module scratch list, one flush per act, and
# never a gate - residue.bank swallows its own failures.
# ---------------------------------------------------------------------------

RESIDUE_AXIS = "semantic"
# The fold's representation runs at chi=1 (a cluster keeps a centroid, no retained directions -
# WO-20260821-fold-chi-undeclared's measured fact). Stamped on every row so a consumer reading
# magnitudes as fitness knows the truncation they were measured under
# (WO-20260821-residual-saturates-at-low-chi); the depth ladder the benches measured (16 at
# level 1, 8 below) is the RECOMMENDED representation, not this fold's current one.
RESIDUE_CHI = 1
_residue_ledger: Any = None      # the active laplace.engine.residue.ResidueLedger, or None outside an act


def _log_residue(kind: str, magnitude: float, **fields: Any) -> None:
    """Type one remainder onto the active act's ledger; a no-op outside a ``_residue_scope``."""
    if _residue_ledger is not None:
        _residue_ledger.add(kind, magnitude, **fields)


def _organ_note(cid: str, Xb, level: int) -> None:
    """The v1 organ's per-cluster hook (RUL-20260823-organ-codesign-converged): bank the
    frame this truncation already scratches, at the declared ladder chi for the split's
    level. A no-op unless an ``isometries.collect`` scope is open, which itself opens
    only under LAPLACE_ORGAN_V1=1 - the incumbent path is byte-identical with the flag
    off (M2's IO-only clause). Chi is passed explicitly from the caller's ladder: the
    constructor law, never default-unlimited."""
    from laplace.representation import isometries
    isometries.note_block(cid, Xb, level=level, chi=_selector_chi(level))


def _residue_handle(name: str, leaf: dict) -> str:
    """The id a leaf rides a residue row under. A sealed node's PATH is itself soul-derived, and
    this store travels (the sibling ledgers' rule), so a sealed leaf appears as a stable opaque
    handle instead - the counts and magnitudes are unaffected, and nothing sealed crosses the
    boundary. Cluster ids need no such treatment: they are already sha1s of membership."""
    if leaf.get("sealed"):
        return "sealed::" + hashlib.sha1(name.encode("utf-8", "replace")).hexdigest()[:10]
    return name


@contextmanager
def _residue_scope(repo_root: Path | str, up_act: str):
    """Open a ledger for one UP act, bank it on the way out. Yields ``(ledger, nested)``.

    Scopes nest - a full rebuild inside an incremental deposit is its own act with its own act_id -
    and ``nested`` says which one this is, so a whole-act verdict (the degenerate row) is banked by
    the outermost scope only and the same failure is not typed twice."""
    from laplace.engine.residue import ResidueLedger
    global _residue_ledger
    saved = _residue_ledger
    ledger = _residue_ledger = ResidueLedger(up_act, axis=RESIDUE_AXIS, chi=RESIDUE_CHI)
    try:
        yield ledger, saved is not None
    finally:
        _residue_ledger = saved
        ledger.bank(repo_root)


# ---------------------------------------------------------------------------
# the public operator: residue -> (parent_map, cluster_nodes)
# ---------------------------------------------------------------------------

def cluster_residue(repo_root: Path | str, residue: dict[str, dict[str, Any]],
                    root_id: str = "") -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Outer wrapper over ``_cluster_residue_body`` (the typed-remainder scope, 2026-08-21): runs
    the full fold unchanged, banks the act's typed residue rows on the way out, and adds the one
    verdict only a whole act can give - a fold that returned no concept nodes at all consolidated
    nothing, which is ``degenerate`` over its whole input. Return value unchanged."""
    from laplace.representation import isometries
    with _residue_scope(repo_root, "meaning_upfold.full") as (ledger, nested):
        # the organ's collector (v1, LAPLACE_ORGAN_V1=1; inert otherwise): the fold banks
        # the per-block isometries it materializes, at the scope's exit, one write.
        with isometries.collect(repo_root):
            parent_map, cluster_nodes = _cluster_residue_body(repo_root, residue, root_id)
        if not cluster_nodes and not nested:
            ledger.add("degenerate", float(len(residue)), n=len(residue))
        return parent_map, cluster_nodes


def _cluster_residue_body(repo_root: Path | str, residue: dict[str, dict[str, Any]],
                          root_id: str = "") -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Cluster the residue leaves (those that would otherwise fall to ``dir_parent``) into a meaning
    hierarchy. Returns ``(parent_map, cluster_nodes)``:

      * ``parent_map``: {node_id -> parent_id} for every residue leaf and every synthetic cluster
        (a leaf -> its concept cluster; a cluster -> the cluster above; a top cluster -> ``root_id``).
      * ``cluster_nodes``: {cluster_id -> leaf-like dict} the caller adds to ``leaves`` so build_tree
        treats them as authored coarse handles (kept essence = the IDF label).

    Empty on any unavailability (no embedder / no analysis deps / <2 nodes) - the caller then keeps
    ``dir_parent``, so the build never breaks. The soul is embedded vector-only (see _embeddable_text)."""
    dial_set = dials.current("engine-fold")
    LEAF_MAX = dial_set["dials"]["leaf_max"]["value"]
    MAX_DEPTH = dial_set["dials"]["max_depth"]["value"]
    repo_root = Path(repo_root)
    names = sorted(residue)
    minimum = dials.value("engine-triggers", "minimum_leaf_multiple") * LEAF_MAX
    if len(names) < minimum:
        _degrade(f"residue is {len(names)} node(s), under the {minimum} needed to split")
        return {}, {}
    # Local is a full compute home (his ruling 2026-08-20, PV-20260820T090500Z-psu-restrictions-scrubbed:
    # "we're on a new machine so please also scrub all PSU restrictions now. Local can do everything") -
    # the PSU-era ceiling on this N*N eigendecomposition is retired as a DEFAULT (it superseded the
    # 2026-06-14 guard this comment used to cite). Unbounded by default (the working re-embed is
    # unchanged); LAPLACE_MAX_UPFOLD_N remains as an opt-in limiter for anyone who wants a graceful
    # fall-back to dir_parent above a chosen size, not because the box demands it.
    import os
    _cap = os.environ.get("LAPLACE_MAX_UPFOLD_N")
    if _cap and len(names) > int(_cap):
        _degrade(f"residue is {len(names)} node(s), over the LAPLACE_MAX_UPFOLD_N cap of {_cap}")
        return {}, {}
    try:
        from laplace.representation.embed_router import get_backend
        backend = get_backend()
        if backend is None:
            _degrade("no embedding backend (fastembed absent, or the model could not load)")
            return {}, {}
        if backend.name.startswith("hash"):
            _degrade(f"the router returned {backend.name} - the hash backend carries no semantics "
                     f"and is never a clustering fallback")
            return {}, {}
        X = _embed(repo_root, names, residue, backend)
    except Exception as exc:  # noqa: BLE001 - any embed/dep failure degrades to dir_parent, never breaks the build
        _degrade(f"the embed step raised {type(exc).__name__}: {exc}")
        return {}, {}

    from laplace.representation.embed_router import TEXT_CAP
    from laplace.representation.spectral_gpu import EigensolverDeclined
    leaf_sha = {name: _text_sha(
        backend.name, _embeddable_text(repo_root, name, residue[name], TEXT_CAP)) for name in names}

    # keyword IDF over the residue, for distinctive cluster labels
    df: Counter = Counter()
    for lf in residue.values():
        df.update(set(w for w in (lf.get("keywords") or []) if _label_ok(w)))
    ndoc = max(1, len(residue))
    idf = {w: math.log(ndoc / c) for w, c in df.items()}

    parent_map: dict[str, str] = {}
    cluster_nodes: dict[str, dict[str, Any]] = {}

    def attach_leaf(i: int, cid: str):
        parent_map[names[i]] = cid

    def make_cluster(cid: str, sub_idx: list[int], parent_id: str):
        members = [names[i] for i in sub_idx]
        cluster_nodes[cid] = {
            "kind": "concept", "essence": _label(members, residue, idf),
            "keywords": _label(members, residue, idf).split(),
            "sealed": all(residue[m].get("sealed") for m in members),
            "leaf": True,   # arrives as a leaf-with-essence -> build_tree marks it AUTHORED, keeps the label
        }
        parent_map[cid] = parent_id

    def decline_cluster(cid: str, sub_idx: list[int], depth: int,
                        exc: EigensolverDeclined) -> None:
        members = [names[i] for i in sub_idx]
        detail = {
            "type": "cut_decline", "reason": "eigensolver-declined",
            "held": len(members), "leaf_max": LEAF_MAX, "max_depth": MAX_DEPTH,
            "dial_set_id": dial_set["dial_set_id"],
            "members_sha256": _member_fingerprint(members, leaf_sha),
            "attempts": exc.attempts,
        }
        cluster_nodes[cid]["split_decline"] = detail
        for i in sub_idx:
            attach_leaf(i, cid)
        _log_residue("overflow", float(max(0, len(members) - LEAF_MAX)), grade=depth,
                     n=max(0, len(members) - LEAF_MAX), ids=[cid], **detail)
        _emit(f"spectral cut DECLINED: {cid} held {len(members)}; "
              f"reason=eigensolver-declined; fingerprint={detail['members_sha256']}")

    def split(idxs: list[int], depth: int, cid: str):
        block = X[idxs]
        reason = recursive_split_stop(len(idxs), depth, leaf_max=LEAF_MAX, max_depth=MAX_DEPTH,
            indistinguishable=all((block[0] == vector).all() for vector in block))
        if reason is None:
            try:
                _k, labels = _best_split(block, level=depth + 1)
            except EigensolverDeclined as exc:
                decline_cluster(cid, idxs, depth, exc)
                return
            reason = recursive_split_stop(len(idxs), depth, leaf_max=LEAF_MAX, max_depth=MAX_DEPTH,
                                          chosen_k=_k, distinct_labels=len(set(labels)))
        if reason:
            for i in idxs:
                attach_leaf(i, cid)
            if reason != "leaf_max":
                _log_residue("overflow", float(len(idxs) - LEAF_MAX), grade=depth,
                             n=len(idxs) - LEAF_MAX, ids=[cid], reason=reason,
                             held=len(idxs), leaf_max=LEAF_MAX, max_depth=MAX_DEPTH)
            return
        for c in sorted(set(labels)):
            sub = [idxs[j] for j in range(len(idxs)) if labels[j] == c]
            if len(sub) == 1:
                attach_leaf(sub[0], cid)        # a singleton attaches directly, no 1-child cluster
                continue
            child = _cluster_id([names[i] for i in sub], parent=cid)   # content-derived, stable across rebuilds
            make_cluster(child, sub, cid)
            _organ_note(child, X[sub], depth + 1)   # v1 organ: bank what this truncation scratches
            split(sub, depth + 1, child)

    # top level: split the whole residue into facets, each a concept child of the root
    all_idx = list(range(len(names)))
    try:
        _k, labels = _best_split(X[all_idx], level=1)
    except EigensolverDeclined as exc:
        top = _cluster_id(names, parent=root_id)
        make_cluster(top, all_idx, root_id)
        decline_cluster(top, all_idx, 0, exc)
        return parent_map, cluster_nodes
    unplaced: list[str] = []
    for c in sorted(set(labels)):
        sub = [all_idx[j] for j in range(len(all_idx)) if labels[j] == c]
        if len(sub) == 1:
            attach_leaf(sub[0], root_id)
            # a top-level singleton hangs from the root: no concept handle claims it, so the
            # coarse layer carries no representation of it at all (a singleton one level DOWN
            # attaches into its parent cluster and is carried, so it is not typed here)
            unplaced.append(_residue_handle(names[sub[0]], residue[names[sub[0]]]))
            continue
        top = _cluster_id([names[i] for i in sub], parent=root_id)   # content-derived (parent="" -> membership alone)
        make_cluster(top, sub, root_id)
        _organ_note(top, X[sub], 1)                 # v1 organ: the level-1 block
        split(sub, 1, top)

    if unplaced:
        _log_residue("unplaced", float(len(unplaced)), grade=0, n=len(unplaced), ids=unplaced)

    return parent_map, cluster_nodes


# ---------------------------------------------------------------------------
# the incremental fold: changed leaves re-embed, touched lineages re-fold, full
# spectral rebuild ONLY on a structural move (his W4 steer). The prev tree is a
# persisted, regenerable projection of one full cluster_residue - the same node
# dict shape, carried across a build so a bounded delta costs cosine, not eigen.
# ---------------------------------------------------------------------------

def _emit(msg: str) -> None:
    """ONE plain line naming the fold mode + why (the module's print voice - lowercase, colon)."""
    print(f"meaning upfold: {msg}")


def _degrade(why: str) -> None:
    """Name a degrade-to-empty out loud (2026-07-28, the loud-failure fix owed since the 07-24
    regression). Every ``return {}, {}`` in this module used to be SILENT: the caller fell back to
    ``dir_parent`` and the deposit carried on with the folder layout standing in for meaning, with
    nothing printed and nothing recorded. That is how three deposits shipped with ZERO concept
    nodes before anyone noticed.

    This does NOT change behaviour - the degrade is still graceful, the build still never breaks,
    which is the property the wake depends on. It changes only whether the degrade is VISIBLE. The
    line names what was unavailable, so a fold that quietly stopped folding says so at the moment it
    stops."""
    print(f"meaning upfold: DEGRADED to the folder middle - {why}. "
          f"No concept clusters this build (the deposit continues; the residue falls to dir_parent).")


def _node_dict(label: str, sealed: bool) -> dict[str, Any]:
    """The concept-cluster leaf dict cluster_residue hands the caller, rebuilt from a persisted label
    + sealed flag. Byte-for-byte the shape make_cluster emits (keywords = the label's own words)."""
    return {"kind": "concept", "essence": label, "keywords": label.split(),
            "sealed": bool(sealed), "leaf": True}


def _idf(residue: dict) -> dict:
    """Keyword IDF over the residue (mirrors cluster_residue's inline idf) - for distinctive labels
    when a touched cluster is re-labelled."""
    df: Counter = Counter()
    for lf in residue.values():
        df.update(set(w for w in (lf.get("keywords") or []) if _label_ok(w)))
    ndoc = max(1, len(residue))
    return {w: math.log(ndoc / c) for w, c in df.items()}


def load_tree(repo_root: Path | str) -> dict[str, Any] | None:
    """Load the persisted concept tree (the incremental prev state), or None when absent/corrupt -
    a None prev is the cold path and forces the full rebuild, output unchanged."""
    p = Path(repo_root) / TREE_FILE
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _over_cap_clusters(clusters: dict, leaf_max: int) -> list[str]:
    """Direct-member overflow, shared by the figure and deposit sweep."""
    return sorted((cid for cid, c in clusters.items() if len(c["members"]) > leaf_max),
                  key=lambda cid: (-len(clusters[cid]["members"]), cid))


def _member_fingerprint(members: list[str], leaf_sha: dict) -> str:
    raw = json.dumps([(m, leaf_sha[m]) for m in sorted(members)], separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def _unchanged_decline(cluster: dict, leaf_sha: dict) -> bool:
    declined = cluster.get("split_decline")
    return bool(declined and declined["members_sha256"] ==
                _member_fingerprint(cluster["members"], leaf_sha))


def depth_cap_figure(tree: dict[str, Any]) -> dict[str, Any]:
    """Measure direct-leaf overflow in one tree snapshot, without loading vectors.

    Corpus mass is the number of distinct leaves in ``leaf_sha``, including root
    singletons. A top-level cluster has depth 1; the stopping floor is depth >=
    MAX_DEPTH. Reject inconsistent membership or ancestry instead of rendering a
    plausible figure from a broken tree. Counts never include descendant clusters
    as direct members, or count a leaf twice.
    """
    dial_set = dials.current("engine-fold")
    LEAF_MAX = dial_set["dials"]["leaf_max"]["value"]
    MAX_DEPTH = dial_set["dials"]["max_depth"]["value"]
    clusters, parents = tree["clusters"], tree["parent_map"]
    leaves, root = set(tree["leaf_sha"]), tree["root_id"]
    if root in clusters or leaves.intersection(clusters):
        raise ValueError("depth-cap-figure: overlapping root/cluster/leaf identities")
    depths = {root: 0}
    for cid in clusters:
        chain, seen, node = [], set(), cid
        while node not in depths:
            if node in seen or node not in clusters or node not in parents:
                raise ValueError("depth-cap-figure: cyclic or incomplete cluster ancestry")
            seen.add(node)
            chain.append(node)
            node = parents[node]
        depth = depths[node]
        for node in reversed(chain):
            depth += 1
            depths[node] = depth
    assigned: set[str] = set()
    over_cap = set(_over_cap_clusters(clusters, LEAF_MAX))
    overflow = floor = beyond = mass = floor_mass = 0
    for cid, cluster in clusters.items():
        members = cluster["members"]
        for member in members:
            if member not in leaves or member in assigned or parents.get(member) != cid:
                raise ValueError("depth-cap-figure: inconsistent direct-leaf membership")
            assigned.add(member)
        n = len(members)
        if cid in over_cap:
            overflow += 1
            mass += n
            if depths[cid] >= MAX_DEPTH:
                floor += 1
                floor_mass += n
            if depths[cid] > MAX_DEPTH:
                beyond += 1
    root_members = leaves - assigned
    if any(member not in parents or parents[member] != root for member in root_members):
        raise ValueError("depth-cap-figure: unaccounted corpus leaves")
    return {
        "schema_version": "laplace.depth-cap-figure/1",
        "dial_set_id": dial_set["dial_set_id"],
        "leaf_max": LEAF_MAX, "max_depth": MAX_DEPTH,
        "clusters": len(clusters), "corpus_members": len(leaves),
        "cluster_direct_members": len(assigned), "root_direct_members": len(root_members),
        "over_cap_clusters": overflow, "over_cap_at_depth_floor": floor,
        "declined_count": sum(_unchanged_decline(clusters[cid], tree["leaf_sha"])
                              for cid in over_cap),
        "over_cap_beyond_depth_floor": beyond,
        "over_cap_members": mass, "depth_floor_members": floor_mass,
        "over_cap_corpus_fraction": mass / len(leaves) if leaves else 0.0,
        "depth_floor_corpus_fraction": floor_mass / len(leaves) if leaves else 0.0,
    }


def _persist_tree(repo_root: Path | str, tree: dict[str, Any]) -> None:
    """Write the persisted concept tree. STORE-02 (2026-08-20 self-audit): the write itself is
    wrapped in ``laplace.pipeline.locking.store_lock`` so two concurrent lanes' writes can never interleave
    into a corrupt file; :class:`~laplace.pipeline.locking.StoreBusy` on contention propagates to the
    caller unchanged (every path into ``_persist_tree`` runs under ``keeper.build_self``'s broad
    ``except Exception: meaning_map = {}``, so a busy lock degrades to the folder fallback exactly
    like any other embed/dep failure - never a crash, never a hang)."""
    from laplace.pipeline.locking import store_lock  # lazy: avoids a module-load cycle
    with store_lock("meaning-tree"):
        (Path(repo_root) / TREE_FILE).write_text(json.dumps(tree), encoding="utf-8")


def _tree_return(tree: dict[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Rebuild ``(parent_map, cluster_nodes)`` - the exact cluster_residue return - from a tree."""
    parent_map = dict(tree["parent_map"])
    cluster_nodes = {cid: _node_dict(c["label"], c.get("sealed", False))
                     for cid, c in tree["clusters"].items()}
    return parent_map, cluster_nodes


def _build_tree_from_full(repo_root: Path, residue: dict, backend, root_id: str,
                          lens_hash: str | None, parent_map: dict, cluster_nodes: dict,
                          lens_pairs: list[str] | None = None) -> dict:
    """Project a completed full cluster_residue into a persistable tree: per cluster its DIRECT leaf
    members (parent_map value == cid), a unit-normalized centroid of those members' vectors, its
    label + sealed flag; plus the full parent_map and the leaf shas the diff keys on. The embed is
    cache-warm here (cluster_residue just wrote the same vectors), so this is cheap."""
    from laplace.representation.embed_router import TEXT_CAP
    names = sorted(residue)
    X = _embed(repo_root, names, residue, backend)
    row = {nm: i for i, nm in enumerate(names)}
    direct: dict[str, list[str]] = {cid: [] for cid in cluster_nodes}
    for nm in names:
        p = parent_map.get(nm)
        if p in direct:
            direct[p].append(nm)
    clusters: dict[str, dict] = {}
    for cid, node in cluster_nodes.items():
        members = direct.get(cid, [])
        clusters[cid] = {"members": members, "label": node.get("essence", ""),
                         "centroid": _centroid(X, row, members),
                         "sealed": bool(node.get("sealed"))}
        if node.get("split_decline"):
            clusters[cid]["split_decline"] = dict(node["split_decline"])
    texts = {nm: _embeddable_text(repo_root, nm, residue[nm], TEXT_CAP) for nm in names}
    leaf_sha = {nm: _text_sha(backend.name, texts[nm]) for nm in names}
    return {"version": backend.name, "root_id": root_id, "lens_hash": lens_hash,
            "lens_pairs": list(lens_pairs or []),
            "clusters": clusters, "parent_map": dict(parent_map), "leaf_sha": leaf_sha}


def _cluster_depth(parent_map: dict[str, str], cid: str, root_id: str) -> int:
    """How deep ``cid`` sits in the persisted tree, in ``cluster_residue``'s own numbering: a
    top-level cluster (a child of the root) is depth 1, which is the depth ``cluster_residue``
    passes to ``split`` for it. The walk is cycle-guarded - a corrupt parent_map must not hang the
    deposit, and a broken chain reads as 'deep', which declines the re-split rather than looping."""
    dial_set = dials.current("engine-fold")
    MAX_DEPTH = dial_set["dials"]["max_depth"]["value"]
    depth, node, seen = 0, cid, set()
    while node and node != root_id and node not in seen and depth <= MAX_DEPTH + 2:
        seen.add(node)
        depth += 1
        node = parent_map.get(node, root_id)
    return depth



def recursive_split_stop(n, depth, *, leaf_max, max_depth, indistinguishable=False,
                         chosen_k=None, distinct_labels=None):
    """Sealed lift of meaning_upfold's measured _resplit_into stopping law.

    A depth cap is safety residue, never a refused cut. Keep both copies equivalent
    with the cross-boundary law test; neither package imports the other.
    """
    if n <= leaf_max:
        return "leaf_max"
    if indistinguishable:
        return "indistinguishable_members"
    if depth >= max_depth:
        return "depth_cap"
    if chosen_k is not None and chosen_k < 2:
        return "silhouette_refused"
    if distinct_labels is not None and distinct_labels < 2:
        return "chosen_k_collapsed"
    return None


def _resplit_into(cid: str, members: list[str], depth: int, clusters: dict, parent_map: dict,
                  X, row: dict, minted: list[str], leaf_sha: dict | None = None) -> None:
    """``cluster_residue``'s ``split`` recursion, run over the PERSISTED tree's shapes.

    Same stopping rule (``LEAF_MAX`` / ``MAX_DEPTH``), same ``_best_split``, same singleton rule (a
    one-member child attaches directly instead of minting a 1-child cluster), same
    ``_cluster_id(members, parent=cid)`` so every minted id is membership-derived and stable across
    rebuilds. Labels, sealed flags and centroids are NOT set here - every cluster it touches is
    added to ``touched``, and the caller's existing re-label pass gives them exactly the same
    treatment as any other touched cluster, so there is one producer of those fields, not two."""
    dial_set = dials.current("engine-fold")
    LEAF_MAX = dial_set["dials"]["leaf_max"]["value"]
    MAX_DEPTH = dial_set["dials"]["max_depth"]["value"]
    import numpy as np

    def stop(reason: str | None, **extra):
        clusters[cid]["members"] = list(members)
        for m in members:
            parent_map[m] = cid
        if reason:
            detail = dict(reason=reason, held=len(members), leaf_max=LEAF_MAX,
                          max_depth=MAX_DEPTH, dial_set_id=dial_set["dial_set_id"])
            detail.update(extra)
            if reason == "eigensolver-declined":
                detail["type"] = "cut_decline"
            if leaf_sha is not None:
                detail["members_sha256"] = _member_fingerprint(members, leaf_sha)
            # A safety bound is not evidence that the cut declined. Only actual
            # cut refusals suppress unchanged retries across deposits.
            if reason != "depth_cap" and leaf_sha is not None:
                clusters[cid]["split_decline"] = detail
            _log_residue("overflow", float(len(members) - LEAF_MAX), grade=depth,
                         n=len(members) - LEAF_MAX, ids=[cid], **detail)
            _log_trigger("scoped_resplit_declined", cluster=cid, depth=depth, **detail)
            _emit(f"scoped re-split DECLINED: {cid} held {len(members)}; "
                  f"reason={reason}; MAX_DEPTH={MAX_DEPTH}; overflow STANDS")

    clusters[cid].pop("split_decline", None)
    idxs = [row[m] for m in members]
    block = X[idxs]
    reason = recursive_split_stop(len(members), depth, leaf_max=LEAF_MAX, max_depth=MAX_DEPTH,
        indistinguishable=bool(len(block)) and np.array_equal(block, np.broadcast_to(block[0], block.shape)))
    if reason:
        stop(None if reason == "leaf_max" else reason)
        return
    try:
        _k, labels = _best_split(block, level=depth + 1)
    except Exception as exc:
        from laplace.representation.spectral_gpu import EigensolverDeclined
        if not isinstance(exc, EigensolverDeclined):
            raise
        stop("eigensolver-declined", attempts=exc.attempts)
        return
    reason = recursive_split_stop(len(members), depth, leaf_max=LEAF_MAX, max_depth=MAX_DEPTH,
                                  chosen_k=_k, distinct_labels=len(set(labels)))
    if reason:
        stop(reason)
        return
    direct: list[str] = []
    for c in sorted(set(labels)):
        sub = [members[j] for j in range(len(members)) if labels[j] == c]
        if len(sub) == 1:
            direct.append(sub[0])           # a singleton attaches here, no 1-child cluster
            parent_map[sub[0]] = cid
            continue
        child = _cluster_id(sub, parent=cid)
        clusters.setdefault(child, {"members": [], "label": "", "centroid": None, "sealed": False})
        parent_map[child] = cid
        minted.append(child)
        _organ_note(child, X[[row[m] for m in sub]], depth + 1)   # v1 organ: minted block banks
        _resplit_into(child, sub, depth + 1, clusters, parent_map, X, row, minted, leaf_sha)
    clusters[cid]["members"] = direct


def _centroid(X, row: dict, members: list[str]):
    """Unit-normalized mean of the members' vectors, or None for a member-less (pure-branch) cluster."""
    import numpy as np
    rows = [X[row[m]] for m in members if m in row]
    if not rows:
        return None
    cen = np.mean(np.asarray(rows, dtype=np.float64), axis=0)
    n = float(np.linalg.norm(cen))
    return (cen / n).tolist() if n else cen.tolist()


def _full(repo_root: Path, residue: dict, backend, root_id: str, lens_hash: str | None,
          reason: str, lens_pairs: list[str] | None = None,
          ) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """The full-rebuild fallback: the existing cluster_residue verbatim, then (re)persist the tree."""
    parent_map, cluster_nodes = cluster_residue(repo_root, residue, root_id)
    if not cluster_nodes:                       # cluster_residue degraded internally (no split) - behave as today
        return parent_map, cluster_nodes
    _emit(f"full rebuild ({reason})")
    _persist_tree(repo_root, _build_tree_from_full(
        repo_root, residue, backend, root_id, lens_hash, parent_map, cluster_nodes, lens_pairs))
    return parent_map, cluster_nodes


def _spectral_allowed() -> bool:
    """The analysis-deps gate for the FULL SPECTRAL rebuild. Local is a full compute home (his ruling
    2026-08-20, PV-20260820T090500Z-psu-restrictions-scrubbed: "we're on a new machine so please also
    scrub all PSU restrictions now. Local can do everything") - this retires the 2026-07-13 PSU ruling's
    ``LAPLACE_ALLOW_SPECTRAL`` / ``CLAUDE_CODE_REMOTE`` opt-in requirement. ``cluster_residue`` now runs
    whenever the analysis deps (scikit-learn + scipy) are importable; ``LAPLACE_NO_SPECTRAL`` remains as
    a trivial explicit opt-out (the codebase's existing ``LAPLACE_NO_*`` convention, e.g.
    ``LAPLACE_NO_NAVIGATOR``) for anyone who wants the degrade-to-prior-tree path without uninstalling
    anything. Missing deps deny the spectral branch the SAME way a thin PSU did (his ruling: "missing
    analysis deps only block the spectral branch, not the whole deposit"), so a demanded rebuild keeps
    the prior tree rather than crash on ImportError. The INCREMENTAL fold (cosine over a bounded delta)
    never routes through here - only a structural-move full rebuild does. Single-sourced at this trigger
    point - reembed.py's deposit narration reads this same function rather than re-deriving the verdict
    (the seam chosen so the guard needs no change to build_self's signature - the module already reads
    LAPLACE_MAX_UPFOLD_N / LAPLACE_REEMBED_FULL_FRACTION at its trigger points, so this is idiomatic)."""
    import os
    if os.environ.get("LAPLACE_NO_SPECTRAL"):
        # THE DIAL LEAVES A ROW TOO (census 2026-08-21, finding C3). The deps-missing branch below
        # has recorded since his 2026-08-21 ruling, but the EXPLICIT opt-out returned in silence -
        # so the one landing an operator actually chose was the one the store could not see, and a
        # deposit that skipped spectral by dial was indistinguishable from one that never tried.
        # dialed=True: visible and lawful, never a print and never a refusal.
        from laplace.representation import device_policy
        device_policy.record_fallback("spectral-clustering", "cpu",
                                      "LAPLACE_NO_SPECTRAL is set (the explicit opt-out)",
                                      dialed=True)
        return False
    try:
        import scipy  # noqa: F401
        import sklearn  # noqa: F401
    except ImportError as exc:
        from laplace.representation import device_policy
        # "disabled", NOT "cpu" (census 2026-08-21, finding C5). A missing scikit-learn is a
        # CPU-side capability gap; calling it a cpu LANDING made LAPLACE_REQUIRE_GPU refuse it as
        # "the GPU is unavailable" on a box whose GPU was perfect - measured. The row still lands
        # and still prints; only the GPU flag's false jurisdiction is removed.
        device_policy.record_fallback("spectral-clustering", "disabled",
                                      f"scipy/sklearn missing ({exc}) - spectral split disabled")
        return False
    return True


# --- Rung-12(a) trigger-rate telemetry: one scratch list per cluster_residue_incremental call,
# flushed to TRIGGER_LOG_FILE by that function's outer wrapper (below). _log_trigger is a no-op
# safe append (a list.append can't raise on these arg shapes); never gates the deposit.
_trigger_events: list[dict[str, Any]] = []


def _log_trigger(kind: str, **fields: Any) -> None:
    _trigger_events.append({"kind": kind, **fields})


def _full_or_deny(repo_root: Path, residue: dict, backend, root_id: str, lens_hash: str | None,
                  reason: str, prev: dict[str, Any] | None,
                  allow_spectral: bool, lens_pairs: list[str] | None = None,
                  ) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """A full spectral rebuild is DEMANDED (``reason``). Run it when allowed; otherwise SKIP it LOUDLY
    and keep the prior concept tree in place - a stale-but-present tree beats an absent one (his ruling
    2026-07-13). With no usable prior tree (cold/incompatible) the residue falls to the caller's folder
    fallback, named plainly. The incremental deposit around this continues either way - only the
    spectral branch is gated, never the whole deposit."""
    _log_trigger("full_rebuild_demanded", reason=reason, allowed=bool(allow_spectral))
    if allow_spectral:
        return _full(repo_root, residue, backend, root_id, lens_hash, reason, lens_pairs)
    have_prev = isinstance(prev, dict) and "parent_map" in prev and "clusters" in prev
    kept = ("keeping the prior concept tree (stale but present)" if have_prev
            else "no prior tree - the residue falls to the folder middle this build")
    _emit(f"Full spectral rebuild skipped ({reason}) - spectral gated off (the analysis deps "
          f"[scikit-learn + scipy] are missing, or LAPLACE_NO_SPECTRAL is set); "
          f"{kept}. The rest of the deposit runs on regardless.")
    if have_prev:
        return _tree_return(prev)
    return {}, {}


def cluster_residue_incremental(
        repo_root: Path | str, residue: dict[str, dict[str, Any]], prev: dict[str, Any] | None,
        root_id: str = "", lens_hash: str | None = None, allow_spectral: bool | None = None,
        lens_pairs: list[str] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Outer wrapper over ``_cluster_residue_incremental_body`` (Rung-12(a) telemetry, 2026-08-20):
    resets the module's trigger-event scratch list, runs the real deposit body unchanged, then
    appends ONE row to ``TRIGGER_LOG_FILE`` naming the triggers that fired this call - the
    multi-deposit trigger-rate window Rung-12(a) needs against the swap-built tree, previously
    unbanked (only the print voice named a trigger, read once and gone). Best-effort: any write
    failure is swallowed - the telemetry is report-only and must never gate or break a deposit."""
    import time as _time
    global _trigger_events
    saved, _trigger_events = _trigger_events, []
    try:
        from laplace.representation import isometries
        with _residue_scope(repo_root, "meaning_upfold.incremental") as (ledger, nested):
            with isometries.collect(repo_root):   # v1 organ: resplit-minted blocks bank too
                result = _cluster_residue_incremental_body(
                    repo_root, residue, prev, root_id=root_id, lens_hash=lens_hash,
                    allow_spectral=allow_spectral, lens_pairs=lens_pairs)
            if not result[1] and not nested:
                # no concept nodes at all: the deposit consolidated nothing over this residue
                ledger.add("degenerate", float(len(residue)), n=len(residue))
        return result
    finally:
        events, _trigger_events = _trigger_events, saved
        try:
            deposits_since_swap = 0
            p = Path(repo_root) / TRIGGER_LOG_FILE
            if p.is_file():
                with p.open("r", encoding="utf-8") as fh:
                    deposits_since_swap = sum(1 for _ in fh)
            row = {"ts": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                   "deposit_act_id": os.environ.get("LAPLACE_DEPOSIT_ACT_ID"),
                   "gate": "rung-12a", "deposits_since_swap": deposits_since_swap,
                   "residue_n": len(residue), "events": events}
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
        except Exception:  # noqa: BLE001 - telemetry never gates or breaks a deposit
            pass


def _cluster_residue_incremental_body(
        repo_root: Path | str, residue: dict[str, dict[str, Any]], prev: dict[str, Any] | None,
        root_id: str = "", lens_hash: str | None = None, allow_spectral: bool | None = None,
        lens_pairs: list[str] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """The incremental entry (his W4 steer: changed nodes re-embed, touched lineages re-fold, a full
    spectral rebuild ONLY on a structural move). Returns the SAME ``(parent_map, cluster_nodes)`` as
    cluster_residue.

    Falls back to the full path (cluster_residue verbatim, then re-persist) when: (a) no/incompatible
    persisted ``prev`` tree (missing/corrupt/version or backend mismatch); (b) the lens-membership
    shape RESHUFFLED - fractional, not binary (the first in-anger close caught the binary form firing
    on every close, because every close mints a new lens-claimed handoff file): when ``lens_hash``
    differs, the symmetric difference of ``lens_pairs`` against the tree's banked pairs is compared to
    the same ``LAPLACE_REEMBED_FULL_FRACTION`` threshold - a few drifted pairs proceed incrementally
    (named out loud), a genuine reshuffle forces full; a hash mismatch with NO banked pairs (a
    pre-pairs tree) forces full once, banking the pairs; (c) dirty fraction
    (new+changed+removed)/max(len(residue),1) exceeds ``LAPLACE_REEMBED_FULL_FRACTION`` (default 0.20).
    NEITHER half of trigger (d) demands the full path any more: (d2) - an accreted cluster breaching
    LEAF_MAX - is cured by a SCOPED RE-SPLIT of that cluster alone (2026-08-20), and (d1) - a
    leaf-bearing cluster emptying out - by DROPPING that cluster in place (2026-08-21). Both cures
    are at the trigger, with the volume measurement that forced them. Cold (``prev`` None) = the full
    path, output unchanged. The no-embedder / too-small degrade returns empty exactly as cluster_residue does, and
    prints nothing (behave as today).

    ``allow_spectral`` gates ONLY the full-rebuild branch: None (the default, every existing caller incl.
    build_self) consults ``_spectral_allowed()`` - the analysis deps (scikit-learn + scipy; local is a
    full compute home per his 2026-08-20 ruling, no env opt-in needed); True/False overrides it (the test
    seam). When a full rebuild is demanded but denied, the prior tree is kept in place and the skip is
    named out loud; the incremental path and the rest of the deposit are never gated."""
    dial_set = dials.current("engine-fold")
    LEAF_MAX = dial_set["dials"]["leaf_max"]["value"]
    repo_root = Path(repo_root)
    names = sorted(residue)
    # the degrade gates, identical to cluster_residue's - empty, no tree, and NAMED (see _degrade)
    minimum = dials.value("engine-triggers", "minimum_leaf_multiple") * LEAF_MAX
    if len(names) < minimum:
        _degrade(f"residue is {len(names)} node(s), under the {minimum} needed to split")
        return {}, {}
    import os
    _cap = os.environ.get("LAPLACE_MAX_UPFOLD_N")
    if _cap and len(names) > int(_cap):
        _degrade(f"residue is {len(names)} node(s), over the LAPLACE_MAX_UPFOLD_N cap of {_cap}")
        return {}, {}
    try:
        from laplace.representation.embed_router import get_backend
        backend = get_backend()
        if backend is None:
            _degrade("no embedding backend (fastembed absent, or the model could not load)")
            return {}, {}
        if backend.name.startswith("hash"):
            _degrade(f"the router returned {backend.name} - the hash backend carries no semantics "
                     f"and is never a clustering fallback")
            return {}, {}
    except Exception as exc:  # noqa: BLE001 - any embed/dep failure degrades to empty, exactly as today
        _degrade(f"the backend lookup raised {type(exc).__name__}: {exc}")
        return {}, {}

    allow = _spectral_allowed() if allow_spectral is None else bool(allow_spectral)

    # --- full-rebuild triggers (a) + (b): tree compatibility + lens shape ---
    if not isinstance(prev, dict) or not all(k in prev for k in ("clusters", "parent_map", "leaf_sha")):
        return _full_or_deny(repo_root, residue, backend, root_id, lens_hash, "no compatible tree", prev, allow, lens_pairs)
    if prev.get("version") != backend.name:
        return _full_or_deny(repo_root, residue, backend, root_id, lens_hash, "tree version/backend mismatch", prev, allow, lens_pairs)
    if lens_hash is not None and prev.get("lens_hash") != lens_hash:
        # (b) FRACTIONAL, not binary (the first in-anger close: every close mints a lens-claimed
        # handoff file, so a binary trigger fires every close). A few drifted pairs are a close's
        # ordinary metabolism; a reshuffle is a structural move.
        prev_pairs = prev.get("lens_pairs")
        if not prev_pairs or lens_pairs is None:
            return _full_or_deny(repo_root, residue, backend, root_id, lens_hash,
                                 "lens membership changed (no banked pairs to grade the drift)",
                                 prev, allow, lens_pairs)
        import os as _os
        thr = float(_os.environ.get("LAPLACE_REEMBED_FULL_FRACTION", dials.value("engine-triggers", "full_fraction")))
        drift = len(set(prev_pairs) ^ set(lens_pairs)) / max(len(prev_pairs), 1)
        if drift > thr:
            return _full_or_deny(repo_root, residue, backend, root_id, lens_hash,
                                 f"lens reshuffle {drift:.0%} > {thr:.0%}", prev, allow, lens_pairs)
        _emit(f"lens drift {drift:.1%} within {thr:.0%} - proceeding incrementally")

    return _incremental(repo_root, residue, prev, backend, root_id, lens_hash, allow, lens_pairs)


def _incremental(repo_root: Path, residue: dict, prev: dict, backend, root_id: str,
                 lens_hash: str | None, allow_spectral: bool = True,
                 lens_pairs: list[str] | None = None,
                 ) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    dial_set = dials.current("engine-fold")
    LEAF_MAX = dial_set["dials"]["leaf_max"]["value"]
    import os

    import numpy as np

    from laplace.representation.embed_router import TEXT_CAP
    names = sorted(residue)
    prev_sha: dict[str, str] = prev.get("leaf_sha", {})
    clusters: dict[str, dict] = {cid: {**c, "members": list(c.get("members", []))}
                                 for cid, c in prev["clusters"].items()}
    parent_map: dict[str, str] = dict(prev["parent_map"])

    texts = {nm: _embeddable_text(repo_root, nm, residue[nm], TEXT_CAP) for nm in names}
    cur_sha = {nm: _text_sha(backend.name, texts[nm]) for nm in names}
    prev_leaves, cur_leaves = set(prev_sha), set(names)
    removed = prev_leaves - cur_leaves
    added = cur_leaves - prev_leaves
    changed = {nm for nm in (cur_leaves & prev_leaves) if cur_sha[nm] != prev_sha[nm]}

    # --- trigger (c): dirty fraction over the residue ---
    thr = float(os.environ.get("LAPLACE_REEMBED_FULL_FRACTION", dials.value("engine-triggers", "full_fraction")))
    frac = (len(added) + len(changed) + len(removed)) / max(len(residue), 1)
    _log_trigger("delta_measured", added=len(added), changed=len(changed), removed=len(removed),
                 dirty_fraction=round(frac, 8), full_rebuild_fraction=thr)
    if frac > thr:
        return _full_or_deny(repo_root, residue, backend, root_id, lens_hash,
                             f"churn {frac:.0%} > {thr:.0%}", prev, allow_spectral, lens_pairs)

    leaf_cluster = {m: cid for cid, c in clusters.items() for m in c["members"]}
    touched: set[str] = set()

    # removed + changed leaves leave their cluster (changed ones will be re-embedded + reassigned)
    for nm in removed | changed:
        cid = leaf_cluster.get(nm)
        if cid is not None and nm in clusters[cid]["members"]:
            clusters[cid]["members"].remove(nm)
            touched.add(cid)
        parent_map.pop(nm, None)

    # --- trigger (d), part 1: a leaf-bearing cluster empties out -> DROPPED IN PLACE ---
    # This used to demand a global spectral rebuild, and it is the same category error (d2) carried
    # until 2026-08-20: a whole-tree re-partition to close one local hole. The cost is not the
    # rebuild's seconds. A re-partition re-mints the cluster ids of everything it moves, and
    # embed_router.node_text names each ancestor in the leaf's own embedded text, so one emptied
    # cluster (0.04% of the tree) turned into 12,642 stale leaf embeddings of which 99.1% had
    # unchanged content (evidence/DEPOSIT_VOLUME_AUDIT_2026-08-21/embed_volume.json). The hole is
    # closed where it is: a childless emptied cluster leaves the tree, and one still carrying child
    # clusters becomes what the full build mints for a branch - a member-less pure branch keeping its
    # banked label and sealed flag, its centroid dropped with its members. Dropping a cluster can
    # empty its parent in turn, so the drop walks up; every id outside that chain is untouched.
    # A cluster emptied by CHANGED (not removed) leaves dissolves the same way: those leaves are
    # still in the residue and the assignment step below places them on their nearest surviving
    # centroid, which is what the re-partition would have done to them at a cost of the whole tree.
    children_of: Counter = Counter(parent_map.values())
    pending = sorted(cid for cid in touched if not clusters[cid]["members"])
    while pending:
        cid = pending.pop()
        if cid not in clusters:
            continue
        if children_of.get(cid):
            clusters[cid]["centroid"] = None
            touched.discard(cid)          # a pure branch has no members to re-label or re-centroid
            _emit(f"cluster {cid} lost its last direct leaf but still carries "
                  f"{children_of[cid]} child cluster(s) - it stands as a member-less pure branch. "
                  f"No global rebuild (the rest of the tree is untouched).")
            _log_trigger("emptied_cluster_kept_as_branch", cluster=cid, children=children_of[cid])
            # the cluster's LABEL is deliberately not banked: a sealed cluster's label is derived
            # from sealed members' keywords, and this store travels. The id resolves against
            # .meaning_tree.json, which does not.
            _log_residue("emptied_handle", 1.0, grade=_cluster_depth(parent_map, cid, root_id),
                         n=1, ids=[cid], children=children_of[cid],
                         sealed=bool(clusters[cid].get("sealed")))
            continue
        depth = _cluster_depth(parent_map, cid, root_id)   # read before the id leaves parent_map
        parent = parent_map.pop(cid, None)
        dropped_sealed = bool(clusters[cid].get("sealed"))
        clusters.pop(cid, None)
        touched.discard(cid)
        if parent is not None:
            children_of[parent] -= 1
            if (parent in clusters and not clusters[parent]["members"]
                    and not children_of.get(parent)):
                pending.append(parent)
        _emit(f"cluster {cid} emptied out and carries no children - dropped in place. "
              f"No global rebuild (the rest of the tree is untouched).")
        _log_trigger("emptied_cluster_dropped", cluster=cid, parent=parent)
        _log_residue("dropped_handle", 1.0, grade=depth, n=1, ids=[cid], parent=parent,
                     sealed=dropped_sealed)

    # embed all current leaves (cache-warm except new/changed), assign new/changed to nearest centroid
    X = _embed(repo_root, names, residue, backend)
    row = {nm: i for i, nm in enumerate(names)}
    cand = [(cid, np.asarray(c["centroid"], dtype=np.float64))
            for cid, c in clusters.items() if c.get("centroid") and c["members"]]
    if not cand:
        return _full_or_deny(repo_root, residue, backend, root_id, lens_hash,
                             "no leaf-bearing clusters", prev, allow_spectral, lens_pairs)
    cand_cids = [c for c, _ in cand]
    cand_mat = np.asarray([v for _, v in cand], dtype=np.float64)
    # The assignment's own cosine IS the fibre residual: what the winning centroid does not
    # reproduce about the leaf it now stands for. The max is read off the same product argmax
    # already scans, so typing it costs a float, not a second pass.
    placed_gap = 0.0
    worst: tuple[float, str] | None = None
    for nm in sorted(added | changed):
        sims = cand_mat @ X[row[nm]]
        j = int(np.argmax(sims))
        gap = float(1.0 - sims[j])
        placed_gap += gap
        if worst is None or gap > worst[0]:
            worst = (gap, nm)
        best = cand_cids[j]
        clusters[best]["members"].append(nm)
        parent_map[nm] = best
        touched.add(best)
    n_placed = len(added | changed)
    if n_placed:
        _log_residue("uncarried_mass", placed_gap, n=n_placed,
                     mean=round(placed_gap / n_placed, 6),
                     worst=round(worst[0], 6) if worst else None,
                     worst_id=_residue_handle(worst[1], residue[worst[1]]) if worst else None)

    # --- trigger (d), part 2: an accreted cluster breaches LEAF_MAX -> a SCOPED RE-SPLIT ---
    # This USED to demand a global spectral rebuild, and that was a category error: a global
    # sledgehammer for a local overflow. Read current counts with depth_cap_figure(load_tree(root))
    # or /usr/bin/python3 -m laplace.engine.meaning_upfold --depth-cap-figure. Full-rebuild comparisons
    # belong in .reembed_timing.jsonl (mode full-rebuild-measured), not a static claim here.
    # The scoped operation re-splits THAT cluster's direct leaf
    # members, at its own depth, under its own id - which is exactly what the top-down build would
    # have done to it had it arrived that size. Everything above and beside it is untouched, so the
    # ids outside the re-split subtree are bit-identical and the churn is bounded to the subtree
    # that actually moved (his ruling, 2026-08-20).
    #
    attempted: set[str] = set()

    def repair(cid: str, source: str):
        depth = _cluster_depth(parent_map, cid, root_id)
        before = len(clusters[cid]["members"])
        minted: list[str] = []
        _resplit_into(cid, list(clusters[cid]["members"]), depth, clusters,
                      parent_map, X, row, minted, cur_sha)
        attempted.add(cid)
        attempted.update(minted)
        touched.add(cid)
        touched.update(minted)
        if minted:
            _emit(f"scoped re-split: {cid} held {before} direct member(s) over LEAF_MAX={LEAF_MAX} "
                  f"at depth {depth} - re-split into {len(minted)} new cluster(s).")
            _log_trigger("scoped_resplit_fired", cluster=cid, depth=depth, before=before,
                         after=len(clusters[cid]["members"]), minted=len(minted), source=source)

    for cid in _over_cap_clusters(clusters, LEAF_MAX):
        if cid in touched and not _unchanged_decline(clusters[cid], cur_sha):
            repair(cid, "touch")

    # Snapshot AFTER touch repairs. New children already underwent recursion;
    # each candidate gets at most one attempt in this deposit.
    candidates = [cid for cid in _over_cap_clusters(clusters, LEAF_MAX)
                  if cid not in attempted and not _unchanged_decline(clusters[cid], cur_sha)]
    budget = dial_set["dials"]["repair_sweep_per_deposit"]["value"]
    selected = candidates[:budget]
    for cid in selected:
        repair(cid, "sweep")
    _log_trigger("repair_sweep", eligible=len(candidates), attempted=len(selected),
                 clusters=selected, budget=budget, dial_set_id=dial_set["dial_set_id"])
    _emit(f"repair sweep: {len(selected)}/{len(candidates)} eligible clusters; budget={budget}")

    # re-label + recompute centroid ONLY on touched clusters (leaf clusters: direct == descendants)
    idf = _idf(residue)
    for cid in touched:
        members = clusters[cid]["members"]
        clusters[cid]["label"] = _label(members, residue, idf)
        clusters[cid]["sealed"] = all(residue[m].get("sealed") for m in members)
        clusters[cid]["centroid"] = _centroid(X, row, members)

    tree = {"version": backend.name, "root_id": root_id, "lens_hash": lens_hash,
            "lens_pairs": list(lens_pairs if lens_pairs is not None else prev.get("lens_pairs", [])),
            "clusters": clusters, "parent_map": parent_map,
            "leaf_sha": {nm: cur_sha[nm] for nm in names}}
    _persist_tree(repo_root, tree)
    _log_trigger("incremental_applied", touched_clusters=len(touched), placed=n_placed,
                 kept=len(cur_leaves) - len(added) - len(changed))
    _emit(f"incremental ({len(added)} new, {len(changed)} changed, {len(removed)} removed; "
          f"{len(cur_leaves) - len(added) - len(changed)} kept)")
    return _tree_return(tree)


def _main(argv: list[str] | None = None) -> int:
    """Read-only command door; absent or malformed snapshots are explicit failures."""
    import argparse
    import time

    parser = argparse.ArgumentParser(description="Read the meaning tree's depth-cap figure")
    parser.add_argument("--depth-cap-figure", action="store_true", required=True)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    started = time.perf_counter()
    path = args.repo_root / TREE_FILE
    try:
        raw = path.read_bytes()
        figure = depth_cap_figure(json.loads(raw))
    except dials.DialRefusal as exc:
        print(json.dumps({"status": exc.code, "scope": "engine-fold", "error": str(exc)}, sort_keys=True))
        return 1
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(json.dumps({"status": "INVALID_TREE", "tree_path": str(path),
                          "error": str(exc)}, sort_keys=True))
        return 1
    figure.update(tree_path=str(path), tree_sha256=hashlib.sha256(raw).hexdigest(),
                  elapsed_seconds=round(time.perf_counter() - started, 6))
    print(json.dumps(figure, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
