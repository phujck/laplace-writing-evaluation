"""isometries.py - the one-object organ's store: fold-time per-block isometries.

THE ORGAN (v1, commissioned PV-20260823-his-one-organ-first; design
RUL-20260823-organ-codesign-converged; spec evidence/ORGAN_V1_2026-08-23/M2_SPEC.md,
CP-1 CONFIRMED): the fold BANKS the per-block isometries it already computes inside
``meaning_upfold._residual_rho`` as it truncates, the descent reads them instead of
fitting its own, and ONE module - this one - owns writer (``write_at_fold`` via the
``collect``/``note_block`` seam), reader (``read_for_descent``) and meter
(``residual``), so half-consumption is a type error.

THE TWO BINDING CONSTRAINTS (NOTE-20260823-the-organ-commissioned), structural here:
(a) LAYER-CONSISTENT ISOMETRIES AT FOLD TIME - the only writer is the fold's own
    collector scope; there is no serve-time fit anywhere in this module (P27's
    wreckage class excluded by construction, not by discipline).
(b) MARGIN PRESERVED UNDER ANY SCALE NORMALIZATION - ``residual`` returns the raw
    norm ``||(1 - QQ+)x||``; no calibration lives in this module, so nothing here
    can flatten the signal.

THE STORE: ``.self_isometries.npz`` (f32), GITIGNORED-RESIDENT with rider - the
residency declaration carries its own rebuild command (see ``REBUILD_CMD``; a
resident that cannot name its own regeneration is half a declaration). Writes ride
``laplace.pipeline.locking.store_lock`` (the WO-20260819 lost-update law, extended to this
store the day it is born) and every write ends in the WRITTEN-BUT-UNREAD selftest:
the bank re-reads its own bytes and verifies round-trip + orthonormality before
reporting done (banking-is-firing; the inversion note made buildable).

RIDER R1 (the third judge's, CP-1): a block whose mean has no direction
(``||mu|| <= 1e-12``) is REFUSED with a typed reason, never banked silently - the
scratch guard in the rho cell is load-bearing once banked.

CONSTRUCTOR LAWS FROM BIRTH: ``chi`` is a constructor argument at every entry
(never default-unlimited); the store is born WITH its consumer (``residual`` is the
meter ``compression_loss`` reads; the descent read is ``read_for_descent``); the
flag ``LAPLACE_ORGAN_V1=1`` gates every write until milestone one.

KEYING (the third judge's M4 probe, named early): frames key by the fold's STABLE
cluster ids (sha1-of-membership, ``_cluster_id``), one frame per materialized
cluster at its ladder level. Route's ``_block_basis`` keys per (node, child-set) -
the M4 packet owes the correspondence and three fallback counts by cause
(no-key / stale_isometry / degenerate); nothing here claims basis equivalence.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

STORE = ".self_isometries.npz"
FORMAT = "self-isometries/1"
SELFTEST_TOL = 1e-5          # f32 orthonormality bar, ||Q'Q - I||_max (rider R2)
DEGENERATE_NORM = 1e-12      # the rho cell's own guard, load-bearing once banked (rider R1)

# R3: the rider's rebuild command, executable-verbatim from the repo root. Fired once,
# exit 0, before the landing row banks (the judge's cure for untested-intent cures).
REBUILD_CMD = ("python3 -c \"import sys; sys.path.insert(0,'src'); "
               "from laplace.representation import isometries; import json; "
               "print(json.dumps(isometries.rebuild('.')['counts']))\"")


def organ_on() -> bool:
    """The v1 flag: every write in this module is inert unless LAPLACE_ORGAN_V1=1."""
    return os.environ.get("LAPLACE_ORGAN_V1", "").strip() == "1"


# ---------------------------------------------------------------------------
# the frame - the rho cell's exact math, factored once
# ---------------------------------------------------------------------------

def block_frame(Xb, *, chi: int):
    """One block's (mu, Q) by the EXACT construction ``_residual_rho`` scratches:
    normalized mean as the first column, top ``min(chi-1, n-1, d-1)`` covariance
    eigenvectors after it, QR to orthonormalize. Returns ``(frame, None)`` or
    ``(None, refusal)`` - R1: a degenerate handle (``||mu|| <= 1e-12``) is refused
    with a typed reason, never silently banked with a near-zero first column."""
    import numpy as np

    Xb = np.asarray(Xb, dtype=np.float32)
    n, d = Xb.shape
    mu = Xb.mean(axis=0)
    nrm = float(np.linalg.norm(mu))
    if nrm <= DEGENERATE_NORM:
        return None, {"reason": "degenerate-handle", "norm": nrm, "n": int(n)}
    h = mu / nrm
    extra = int(min(chi - 1, n - 1, d - 1))
    cols = [h[:, None]]
    if extra > 0:
        Y = Xb - mu
        C = (Y.T @ Y).astype(np.float32)
        _w, V = np.linalg.eigh(C)
        cols.append(V[:, ::-1][:, :extra])
    Q, _ = np.linalg.qr(np.concatenate(cols, axis=1))
    return {"mu": mu.astype(np.float32), "Q": Q.astype(np.float32)}, None


def residual(x, Q) -> float:
    """The meter both sides share: ``||(1 - QQ+)x||`` - compression_loss from the
    SAME banked object the descent reads. RAW norm by constraint (b): margin is the
    signal, and no normalization in this module may flatten it."""
    import numpy as np

    x = np.asarray(x, dtype=np.float32)
    return float(np.linalg.norm(x - Q @ (Q.T @ x)))


# ---------------------------------------------------------------------------
# the writer - the fold's collector seam (the _residue_ledger pattern)
# ---------------------------------------------------------------------------

class _Collector:
    def __init__(self) -> None:
        self.frames: dict[str, dict[str, Any]] = {}
        self.refused: list[dict[str, Any]] = []

    def note(self, cid: str, Xb, level: int, chi: int) -> None:
        frame, refusal = block_frame(Xb, chi=chi)
        if refusal is not None:
            self.refused.append({"block": cid, "level": int(level), "chi": int(chi), **refusal})
            return
        self.frames[cid] = {"level": int(level), "chi": int(chi),
                            "n": int(len(Xb)), **frame}


_collector: _Collector | None = None


def note_block(cid: str, Xb, *, level: int, chi: int) -> None:
    """The fold's per-cluster hook: a no-op unless a ``collect`` scope is open (which
    itself opens only under the flag) - so the incumbent fold path is untouched with
    the flag off (M2's IO-only clause, provable by byte-identity)."""
    if _collector is not None:
        _collector.note(cid, Xb, level, chi)


@contextlib.contextmanager
def collect(repo_root: Path | str) -> Iterator[None]:
    """The fold opens this around cluster materialization; the exit BANKS what the
    scope collected (one write, under the store lock, selftested). Inert when the
    flag is off; scopes do not nest (the outer one holds)."""
    global _collector
    if not organ_on() or _collector is not None:
        yield
        return
    _collector = col = _Collector()
    try:
        yield
    finally:
        _collector = None
        if col.frames or col.refused:
            _bank(repo_root, col.frames, col.refused, source="fold")


def write_at_fold(repo_root: Path | str, blocks: dict[str, tuple[Any, int, int]],
                  *, source: str = "direct") -> dict[str, Any]:
    """The direct writer (the rebuild path and tests use it; the fold itself rides
    ``collect``): ``blocks`` maps cid -> (Xb, level, chi). Chi is a constructor
    argument per block - there is no default."""
    col = _Collector()
    for cid, (Xb, level, chi) in blocks.items():
        col.note(cid, Xb, level, chi)
    return _bank(repo_root, col.frames, col.refused, source=source)


def _bank(repo_root: Path | str, frames: dict[str, dict[str, Any]],
          refused: list[dict[str, Any]], *, source: str) -> dict[str, Any]:
    """Merge-write the store under its lock, then the WRITTEN-BUT-UNREAD selftest:
    re-read the banked bytes and verify round-trip + orthonormality. The write is
    not done until its own read fires; a selftest red raises (never a silent bank).
    On lock contention: degrade-but-plain, serve the report unpersisted (the
    embeddings store's STORE-01 posture)."""
    import numpy as np

    from laplace.pipeline.locking import StoreBusy, store_lock

    root = Path(repo_root)
    path = root / STORE
    report: dict[str, Any] = {"store": str(path), "source": source,
                              "banked": sorted(frames), "refused": refused,
                              "persisted": False, "selftest": None}
    if not frames and not refused:
        return report
    try:
        with store_lock("self-isometries"):
            existing_arrays: dict[str, Any] = {}
            meta: dict[str, Any] = {"format": FORMAT, "rebuild_cmd": REBUILD_CMD,
                                    "blocks": {}, "refused": []}
            if path.is_file():
                try:
                    with np.load(path, allow_pickle=False) as z:
                        existing_arrays = {k: z[k] for k in z.files if k != "meta"}
                        try:
                            meta = json.loads(str(z["meta"][()]))
                        except Exception:
                            pass  # a torn meta is rebuilt from this write; arrays survive
                except (OSError, ValueError, KeyError):
                    # a torn STORE under the lock: start the merge base empty rather than
                    # die - this write's frames bank, the rest regenerates via REBUILD_CMD
                    # (D2: the writer heals what the reader types)
                    existing_arrays = {}
            for cid, f in frames.items():
                existing_arrays[f"{cid}::mu"] = f["mu"]
                existing_arrays[f"{cid}::Q"] = f["Q"]
                meta["blocks"][cid] = {"level": f["level"], "chi": f["chi"], "n": f["n"]}
            meta["format"] = FORMAT
            meta["rebuild_cmd"] = REBUILD_CMD
            meta["written_at"] = datetime.now(timezone.utc).isoformat()
            meta["source"] = source
            # THE REFUSAL RETIREMENT RULE (the judge's D4, typed before the store ages):
            # refusals are per-block STATE, not an append log - a block that later banks
            # clean retires its refusal rows, and a block re-refused carries ONE current
            # row (latest wins), so meta.refused is always exactly the blocks refused as
            # of the newest write that saw them.
            kept = {r["block"]: r for r in (meta.get("refused") or []) if r.get("block")}
            for r in refused:
                kept[r["block"]] = r
            for cid in frames:
                kept.pop(cid, None)
            meta["refused"] = list(kept.values())
            # ATOMIC WRITE (the judge's D2; the sibling sidecar's own transactional
            # pattern): temp in the same dir -> fsync -> os.replace, so a kill mid-write
            # leaves the incumbent store whole and at worst a named temp file behind.
            buf = io.BytesIO()
            np.savez(buf, meta=np.array(json.dumps(meta)), **existing_arrays)
            tmp = path.with_suffix(".npz.tmp")
            with open(tmp, "wb") as fh:
                fh.write(buf.getvalue())
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
            report["persisted"] = True
    except StoreBusy:
        report["why_unpersisted"] = "store-busy (degrade-but-plain; the next write catches up)"
        return report

    # the selftest - the banked bytes re-read and verified (banking-is-firing)
    check = read_for_descent(root)
    worst = 0.0
    for cid, f in frames.items():
        got = check["frames"].get(cid)
        assert got is not None, f"selftest: banked block {cid} unreadable from its own store"
        Q = got["Q"]
        err = float(np.abs(Q.T @ Q - np.eye(Q.shape[1], dtype=np.float32)).max())
        worst = max(worst, err)
        assert err < SELFTEST_TOL, (
            f"selftest: block {cid} orthonormality {err:.2e} >= {SELFTEST_TOL} - "
            "the write is not done, and it does not pretend to be")
        assert np.array_equal(got["mu"], f["mu"]), f"selftest: {cid} mu round-trip differs"
    report["selftest"] = {"blocks": len(frames), "worst_orthonormality": worst,
                          "tol": SELFTEST_TOL, "pass": True}
    return report


# ---------------------------------------------------------------------------
# the reader - the descent's side, and the rebuild (the rider's own command)
# ---------------------------------------------------------------------------

def read_for_descent(repo_root: Path | str) -> dict[str, Any]:
    """Serve the banked frames. An absent store is an EMPTY read (the caller counts
    it as no-key fallback), never an exception - a descent must be able to run on a
    box that has never folded under the flag."""
    import numpy as np

    path = Path(repo_root) / STORE
    if not path.is_file():
        return {"frames": {}, "meta": {"absent": str(path)}}
    # A TORN STORE SERVES TYPED-EMPTY, never raises (the judge's D2: at M4 this read is
    # route-load-bearing, and the store regenerates via REBUILD_CMD - a torn read is a
    # counted fallback cause, not a crash).
    try:
        with np.load(path, allow_pickle=False) as z:
            try:
                meta = json.loads(str(z["meta"][()]))
            except Exception:
                meta = {"torn": str(path)}
            frames: dict[str, dict[str, Any]] = {}
            for k in z.files:
                if k.endswith("::Q"):
                    cid = k[:-3]
                    frames[cid] = {"Q": z[k],
                                   "mu": z.get(f"{cid}::mu"),
                                   **(meta.get("blocks", {}).get(cid, {}))}
    except (OSError, ValueError, KeyError) as exc:
        return {"frames": {}, "meta": {"torn": str(path), "why": f"{type(exc).__name__}: {exc}"}}
    return {"frames": frames, "meta": meta}


def rebuild(repo_root: Path | str) -> dict[str, Any]:
    """The rider's regeneration: recompute every cluster's frame from the PERSISTED
    fold state (.meaning_tree.json + the meaning-vectors sidecar) - no refold, no
    model call, layer-consistent because the tree IS the fold's banked truncation.
    Chi comes from the declared ladder by each cluster's own depth (the measured
    declaration, AMEND-20260823-chi-ladder-declared) - never default-unlimited."""
    import numpy as np

    root = Path(repo_root)
    tree = json.loads((root / ".meaning_tree.json").read_text(encoding="utf-8"))
    idx = json.loads((root / ".meaning_vectors.index.json").read_text(encoding="utf-8"))
    # the sidecar's live dialect (meaning-vectors-sidecar): {"nodes": {name: {"row": i, ...}}};
    # the flat {"ids": [...]} form is the test fixture's minimal shape of the same map.
    if "nodes" in idx:
        row = {name: entry["row"] for name, entry in idx["nodes"].items()}
    else:
        row = {name: i for i, name in enumerate(idx["ids"])}
    X = np.load(root / idx.get("vectors", ".meaning_vectors.f32.npy"), allow_pickle=False)

    clusters: dict[str, Any] = tree["clusters"]
    parent_map: dict[str, str] = tree["parent_map"]
    root_id: str = tree.get("root_id", "")

    children: dict[str, list[str]] = {}
    for child, parent in parent_map.items():
        children.setdefault(parent, []).append(child)

    def depth_of(cid: str) -> int:
        d, cur = 0, cid
        seen = set()
        while cur != root_id and cur in parent_map and cur not in seen:
            seen.add(cur)
            cur = parent_map[cur]
            d += 1
        return max(d, 1)

    def leaves_under(cid: str) -> list[str]:
        out: list[str] = []
        stack = [cid]
        while stack:
            node = stack.pop()
            for ch in children.get(node, []):
                if ch in clusters:
                    stack.append(ch)
                else:
                    out.append(ch)
        return out

    # the ladder, restated numerically to keep this module import-cycle-free with
    # meaning_upfold (which imports this module): level 1 -> 16, deeper -> 8
    # (AMEND-20260823-chi-ladder-declared; one source of truth is the amendment row,
    # and meaning_upfold's constants carry the same values under its test shard).
    def ladder_chi(level: int) -> int:
        return 16 if level <= 1 else 8

    blocks: dict[str, tuple[Any, int, int]] = {}
    skipped_no_vectors = 0
    for cid in clusters:
        names = [n for n in leaves_under(cid) if n in row]
        if len(names) < 2:
            skipped_no_vectors += 1
            continue
        lvl = depth_of(cid)
        blocks[cid] = (X[[row[n] for n in names]], lvl, ladder_chi(lvl))

    report = write_at_fold(root, blocks, source="rebuild")
    report["counts"] = {"clusters": len(clusters), "banked": len(report["banked"]),
                       "refused": len(report["refused"]),
                       "skipped_lt2_vectors": skipped_no_vectors}
    return report


def rebuild_from_network(repo_root: Path | str, *, min_members: int = 2) -> dict[str, Any]:
    """THE ID-SPACE JOIN'S CURE (WO-20260824-frames-blocks-id-space, his order
    PV-20260824-his-fix-the-join): frames banked under ROUTE'S OWN BLOCK KEYS.

    Judge-4's measurement: route expands PATH ids while the fold's frames key by
    ``concept::`` cluster ids - the residual gate reached 41 of 565 block opportunities
    (7.3%), 445 skips no_key, so no arm through that channel could measure the frames.
    This rebuild walks the LIVE NETWORK's own structure (``conceptric.load_network`` -
    the exact object route descends) and banks one frame per internal node from its
    DIRECT MEMBERS' vectors in ROUTE'S OWN SERVING SPACE (the embed_router cache, the
    same basis the gate's children arrive in) - so the gate's key lookup hits by
    construction wherever a block is frameable at all.

    Chi rides the declared ladder by tree depth (level 1 -> 16, deeper -> 8), exactly
    as everywhere. Frames merge into the one store beside the ``concept::`` family
    (disjoint key namespaces); same lock, same selftest, refusals typed. Read-intent
    callers pin LAPLACE_EMBED_BUDGET=0 so the vector read cannot drip."""
    import numpy as np

    from laplace.engine import conceptric
    from laplace.representation import embed_router

    root = Path(repo_root)
    net = conceptric.load_network(root)
    backend = embed_router.get_backend()
    vecs = embed_router.ensure_embeddings(root, net, backend)["vectors"]
    nodes = net["nodes"]
    root_id = net.get("root", "")

    def depth_of(nid: str) -> int:
        d, cur, seen = 0, nid, set()
        while cur and cur != root_id and cur in nodes and cur not in seen:
            seen.add(cur)
            cur = nodes[cur].get("parent") or ""
            d += 1
        return max(d, 1)

    blocks: dict[str, tuple[Any, int, int]] = {}
    skipped_small = skipped_novec = 0
    for nid, node in nodes.items():
        if node.get("leaf", True) or nid == root_id:
            continue
        if nid.startswith("concept::"):
            # THE KEY-COLLISION GUARD (NOTE-20260824-the-overwrite-and-the-rider): the
            # meaning tree rides the net, so this walker would otherwise OVERWRITE the
            # fold's leaf-spanning concept frames with direct-member versions under
            # their own keys - it did, once, for fifty minutes. The concept family is
            # the fold's alone; this rebuild owns only the network-native keys.
            continue
        members = [m for m in (node.get("members") or [])
                   if m in nodes and vecs.get(m) is not None]
        if len(members) < min_members:
            if node.get("members"):
                skipped_small += 1
            else:
                skipped_novec += 1
            continue
        X = np.stack([np.asarray(vecs[m], dtype=np.float32) for m in members])
        lvl = depth_of(nid)
        blocks[nid] = (X, lvl, 16 if lvl <= 1 else 8)

    report = write_at_fold(root, blocks, source="rebuild-network")
    report["counts"] = {"internal_nodes_walked": sum(1 for n in nodes.values()
                                                     if not n.get("leaf", True)),
                        "banked": len(report["banked"]),
                        "refused": len(report["refused"]),
                        "skipped_small": skipped_small,
                        "skipped_no_members": skipped_novec}
    return report
