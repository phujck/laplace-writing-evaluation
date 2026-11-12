"""The cross-lens TECHNIQUE resolver - the conjugate of ``identity_lens`` (his build, 2026-06-13).
Where ``identity_lens`` fuses an entity's per-lens portraits into one ``person://`` apex by NAME
tokens, this fuses the same TECHNIQUE across authors and research programs into one
``technique://`` apex by the MEANING of its description. A technique is never named consistently -
``magann`` calls it ``lyapunov-feedback-combinatorial-optimization``, another corpus calls it
``measurement-conditioned-descent`` - so the name-token rule the identity resolver leans on is
blind here. The resolution rides the SEMANTICS instead: each rung-instance (the confirmed
mid-grade of one author's program, a technique seen once) is embedded (bge-small, local, the same
fold-time embedder N42 validated) and clustered by cosine geometry; a cluster that spans >=2
research programs is one technique, wielded in several places.

The half-built transfer graph is already in the data: each generator (theme) carries ``moves`` -
the papers that carried a technique from theme A to theme B, with the author's own ``why``. Those
91 edges are lifted here to CONJECTURAL theme<->theme couplings (the creativity seed,
``conjectural-links-are-creativity``: a technique crossing programs is exactly the grit a wide
ideation pull should surface, and a narrow recall pull should not).

Like the identity overlay, this runs as a build-time sibling in ``conceptric.load_network`` (after
the identity overlay), so every ``interesting``/``sew up`` re-resolves and the apexes enrich
themselves - automatic, no hand in the loop. For each resolved technique it:

  1. emits a ``technique://<key>`` apex whose MEMBERS are the per-author/per-theme rung instances
     and whose REACH is their union - a hot hub a broad pull surfaces, descending to every author
     who wields it (the expertise-routing ring-down: who does technique X across the graph);
  2. injects ONE synthetic ``technique::<key>`` atom into every member's reach, so the instances
     couple to one another through the EXISTING coupling formula - no new coupling logic. This is
     the load-bearing move (identity_lens's trick): the unification rides the SAME ``reach`` the
     recall / navigator / GENERATION pull reads, so a piece firing to generate from one author's
     rung reaches the cross-author correlates - generation-pull-by-technique, not a recall-only
     field;
  3. stamps each member with ``techniques = [technique://<key>]`` - the ring-UP handle from a rung
     to its technique apex, surfaced by ``reconstruct_node`` (the rung's own ``parent`` - its
     generator - is left untouched, so the program ladder is intact; the technique apex is an
     ADDITIONAL uplink, the conjugate axis to the author tree).

The clustering is mechanical and its granularity is ONE knob - ``tau``, the cosine-distance
ceiling for the complete-linkage merge (the author's to bless; technique granularity is fuzzier
than person-names, so the resolution quality is the whole game - clean-room it with
``scripts/technique_cluster.py``). High-precision: a cluster is fused only when it spans >=2
distinct THEMES (a technique that recurs across programs, not one program's idiosyncratic step),
and the overlay is recoverable - it writes nothing to the floor (the vectors cache to a gitignored
floats-only file, exactly as ``meaning_upfold`` does)."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from laplace.engine import structural_lens
from laplace.engine.keeper_ring import CONJECTURE_PREFIX

TECHNIQUE_PREFIX = "technique://"
_TECHNIQUE_ATOM = "technique::"                 # the synthetic shared-reach atom that couples instances
_MOVE_ATOM = CONJECTURE_PREFIX + "move::"       # the lifted transfer edge - conjectural (ideation, not recall)
TECHNIQUE_LENS = "technique"
CACHE_FILE = ".technique_vectors.json"          # gitignored: floats + content-hash, never text
LABEL_CACHE_FILE = ".technique_labels.json"     # gitignored: the clustering VERDICT (ints + one fingerprint)
_LABEL_CACHE_VERSION = 1                        # bump when the clustering itself changes meaning
_LABEL_CACHE_KEEP = 8                           # verdicts retained (a tau sweep must not evict the build's)

DEFAULT_TAU = 0.30          # cosine-distance ceiling for the complete-linkage merge - HIS knob to bless
MIN_THEMES = 2              # a technique apex needs instances from >=2 research programs (cross-program)

_STOP = frozenset({
    "a", "an", "and", "the", "of", "to", "in", "is", "it", "for", "on", "with", "as", "at", "by",
    "or", "be", "via", "from", "into", "based", "using", "use", "general", "method", "methods",
    "approach", "scheme", "rung", "technique", "this", "that", "its", "their", "than", "which",
})


def _toks(s: str) -> list[str]:
    """A rung's content tokens for keying - alphabetic, de-hyphenated, stopword-dropped."""
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if len(t) > 2 and not t.isdigit()
            and t not in _STOP]


# ---------------------------------------------------------------------------
# the rung instances - the technique-instances, ids matching structural_lens exactly
# ---------------------------------------------------------------------------

def _rung_instances(repo_root: Path | str) -> list[tuple[str, dict[str, Any]]]:
    """Every rung across every regraded ladder as ``(rung_id, meta)``. The ``rung_id`` is built the
    same way ``structural_lens.structural_leaves`` builds it, so each is a LIVE network node the
    overlay can fuse. ``meta`` carries the author (corpus key), the theme (generator) it sits under,
    and the technique TEXT to embed - the rung NAME + ESSENCE only (the prose describing the
    technique), never the author or theme, so the geometry reads the technique itself, not its
    filing."""
    out: list[tuple[str, dict[str, Any]]] = []
    for relpath, rec in structural_lens._records(repo_root):
        key = rec.get("_key", "")
        for g in rec.get("generators", []):
            gid = f"{relpath}::{structural_lens._slug(g.get('label', ''))}"
            theme = (g.get("label") or "").strip()
            for r in g.get("rungs", []):
                name = (r.get("name") or "").strip()
                if not name:
                    continue
                rid = f"{gid}{structural_lens.NEST_SEP}{name}"
                text = f"{name}. {(r.get('essence') or '').strip()}".strip()
                out.append((rid, {"author": key, "theme": theme, "theme_id": gid,
                                  "name": name, "text": text}))
    return out


def _moves(repo_root: Path | str, nodes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The generators' ``moves`` lifted to directed theme->theme transfer edges (the half-built
    transfer graph). Each move names its FROM/TO themes by LABEL within one corpus; we map the
    label to its generator node id and keep only edges whose endpoints are both live nodes and
    distinct (a self-move is a no-op). The author's ``why`` rides along - it IS the conjectural
    rationale."""
    out: list[dict[str, Any]] = []
    for relpath, rec in structural_lens._records(repo_root):
        label_to_id = {(g.get("label") or "").strip():
                       f"{relpath}::{structural_lens._slug(g.get('label', ''))}"
                       for g in rec.get("generators", [])}
        for g in rec.get("generators", []):
            src = f"{relpath}::{structural_lens._slug(g.get('label', ''))}"
            for mv in g.get("moves", []) or []:
                from_id = label_to_id.get((mv.get("from") or "").strip(), src)
                to_id = label_to_id.get((mv.get("to") or "").strip())
                if not to_id or to_id == from_id:
                    continue
                if from_id not in nodes or to_id not in nodes:
                    continue
                out.append({"from": from_id, "to": to_id,
                            "paper": (mv.get("paper") or "").strip(),
                            "why": (mv.get("why") or "").strip()})
    return out


# ---------------------------------------------------------------------------
# embed + cluster - the bge geometry (cached), agglomerated under the one knob
# ---------------------------------------------------------------------------

def _embed(repo_root: Path, names: list[str], texts: list[str], get_backend) -> Any:
    """Embed each rung text, content-hash cached to the gitignored CACHE_FILE (floats + hash, never
    text). Returns a unit-normalized (n, d) numpy matrix row-aligned to ``names``, or ``None`` when
    something is stale and no backend is available to embed it. Mirrors ``meaning_upfold._embed`` -
    the fold-time intelligence paid once, then read.

    HOT-5/F4(1) (the 2026-08-20 self-audit): the write fires ONLY when something actually changed
    (a stale re-embed, or a prune that actually dropped a vanished name) - a read that finds
    nothing stale and nothing vanished never touches the store.

    HOT-2 (2026-08-20 self-audit): ``get_backend`` is a zero-arg THUNK (typically
    ``embed_router.get_backend`` itself), not a live backend - the ONNX/CUDA session build
    (1.5-3.1s) is real work that a fully-cached call (0 stale, the common case: 0/1055 rungs stale
    at last measurement) has no reason to pay. Staleness is checked FIRST against the backend's
    PREDICTED name (``embed_router.predicted_backend_name()`` - a static format string, exact
    whenever a real backend would succeed, see its docstring) - only when that check finds a
    stale row does this call ``get_backend()`` and pay for the session."""
    import numpy as np

    from laplace.representation.embed_router import TEXT_CAP, predicted_backend_name
    cache_path = repo_root / CACHE_FILE
    name = predicted_backend_name()
    cached: dict[str, dict] = {}
    if cache_path.is_file():
        try:
            disk = json.loads(cache_path.read_text(encoding="utf-8"))
            if disk.get("backend") == name:
                cached = disk.get("nodes", {})
        except (OSError, json.JSONDecodeError):
            cached = {}
    capped = [t[:TEXT_CAP] for t in texts]
    hashes = [hashlib.sha1(f"{name}\x00{t}".encode("utf-8", "replace")).hexdigest()
              for t in capped]
    stale = [i for i, nm in enumerate(names) if cached.get(nm, {}).get("h") != hashes[i]]
    if stale:
        # Only NOW does the model get built - the expensive part, paid only when it buys
        # something. backend.name is IDENTITY and always equals `name` above whenever
        # construction succeeds (predicted_backend_name's docstring); a mismatch or an
        # unavailable backend both carry no technique layer this round, same as before.
        backend = get_backend()
        if backend is None or backend.name.startswith("hash"):
            return None
        vecs = backend.embed([capped[i] for i in stale])
        for i, v in zip(stale, vecs, strict=True):
            cached[names[i]] = {"h": hashes[i], "v": list(v)}
    names_set = set(names)
    pruned = any(nm not in names_set for nm in cached)
    cached = {nm: cached[nm] for nm in names}       # prune vanished
    if stale or pruned:
        cache_path.write_text(json.dumps({"backend": name, "nodes": cached}), encoding="utf-8")
    X = np.asarray([cached[nm]["v"] for nm in names], dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    return X


def _cluster(X, tau: float) -> list[int]:
    """Agglomerative COMPLETE-linkage over the cosine-distance matrix, cut at ``tau``. Complete
    linkage is the load-bearing choice (clean-roomed 2026-06-13): the bge geometry is dense, so
    average/single linkage CHAINS - the merge runs away into one 270-rung blob that lumps half the
    corpus by shared 'quantum' vocabulary (the same eigengap degeneracy ``meaning_upfold`` met).
    Complete linkage caps a cluster's diameter, so a technique only absorbs a rung that is close to
    EVERY member - tight, technique-sized groups, no runaway. The threshold (not a fixed K) IS the
    granularity knob: K - the number of distinct techniques - is unknown, so the author tunes the
    merge ceiling, not a count. Deterministic; no random seed. Returns a label per row."""
    import numpy as np
    from sklearn.cluster import AgglomerativeClustering
    n = len(X)
    if n < 2:
        return [0] * n
    dist = np.clip(1.0 - (X @ X.T), 0.0, 2.0)
    np.fill_diagonal(dist, 0.0)
    ac = AgglomerativeClustering(n_clusters=None, metric="precomputed", linkage="complete",
                                 distance_threshold=tau)
    return ac.fit_predict(dist).tolist()


def _fingerprint(rids: list[str], texts: list[str], tau: float, backend: str) -> str:
    """The one hash that says "this clustering is still the answer": the backend identity, the
    knob, and the exact (rung id, capped content) pairs the labels were cut from - the SAME
    ``name\\x00text`` digest ``_embed`` stales its vectors on, so a text edit, a vanished rung, a
    new rung, a re-tuned ``tau`` or a changed embedder all miss, and nothing else does."""
    from laplace.representation.embed_router import TEXT_CAP
    h = hashlib.sha1()
    h.update(f"{_LABEL_CACHE_VERSION}\x00{tau!r}\x00{backend}".encode())
    for rid, text in zip(rids, texts, strict=True):
        h.update(b"\x00")
        h.update(hashlib.sha1(f"{backend}\x00{text[:TEXT_CAP]}".encode("utf-8", "replace")).digest())
        h.update(rid.encode("utf-8", "replace"))
    return h.hexdigest()


def _labels_cached(repo_root: Path, rids: list[str], texts: list[str], tau: float,
                   get_backend) -> list[int] | None:
    """The clustering VERDICT, content-hash cached to the gitignored ``LABEL_CACHE_FILE`` - the
    conjugate of ``_embed``'s vector cache, one level up.

    The technique layer is NOT lazy-able the way its work order first read it (see the resolution
    row): ``technique_overlay`` injects a shared ``technique::`` atom into every member's ``reach``,
    so the layer is already inside the coupling every recall / navigator / generation pull computes,
    not only behind ``nodes[nid]["techniques"]``. Deferring the overlay would silently change what
    every OTHER caller measures. What IS defensible is that a build whose rungs did not move should
    not re-cut a clustering it already cut: on a hit nothing here reads the 9MB vector cache and
    nothing imports sklearn (~2.2-3.8s of the ~4.9s a warm ``load_network`` was paying), and the
    labels - hence the whole overlay and every coupling downstream of it - are byte-identical.
    A miss (any rung text, id, tau or embedder moved) pays the full embed + cluster, as before.

    The store holds the last few verdicts, not one, so ``scripts/technique_cluster.py``'s tau sweep
    (which resolves the same corpus at eight knob settings in a row) cannot evict the default-tau
    verdict the next build wants."""
    from laplace.representation.embed_router import predicted_backend_name
    fp = _fingerprint(rids, texts, tau, predicted_backend_name())
    cache_path = repo_root / LABEL_CACHE_FILE
    entries: list[dict[str, Any]] = []
    if cache_path.is_file():
        try:
            disk = json.loads(cache_path.read_text(encoding="utf-8"))
            entries = [e for e in disk.get("entries", []) if isinstance(e, dict)]
        except (OSError, ValueError, TypeError):
            entries = []                            # a corrupt cache is a miss, never a failure
    for e in entries:
        labels = e.get("labels")
        if e.get("fingerprint") == fp and isinstance(labels, list) and len(labels) == len(rids):
            try:
                return [int(x) for x in labels]
            except (TypeError, ValueError):
                break
    # HOT-2 (2026-08-20 self-audit) held below: ``get_backend`` stays a THUNK all the way down.
    X = _embed(repo_root, rids, texts, get_backend)
    if X is None:
        return None
    labels = _cluster(X, tau)
    keep = [{"fingerprint": fp, "labels": labels}]
    keep += [e for e in entries if e.get("fingerprint") != fp][:_LABEL_CACHE_KEEP - 1]
    try:
        cache_path.write_text(json.dumps({"entries": keep}), encoding="utf-8")
    except OSError:
        pass                                        # an unwritable cache costs speed, never truth
    return labels


def _key(members_meta: list[dict[str, Any]], idf: dict[str, float]) -> str:
    """A technique's key from its members' NAME tokens, ranked by tf*idf - the terms most
    DISTINCTIVE to this cluster, never the merely frequent. ``feedback-lyapunov-measurement``, not
    ``quantum-control-method``."""
    cnt: Counter = Counter()
    for m in members_meta:
        cnt.update(_toks(m["name"]))
    if not cnt:
        return "technique"
    ranked = sorted(cnt, key=lambda w: (-(cnt[w] * idf.get(w, 1.0)), w))
    return "-".join(ranked[:4]) or "technique"


# ---------------------------------------------------------------------------
# resolve - the pure grouping/gating (testable apart from the mutation)
# ---------------------------------------------------------------------------

def resolve(repo_root: Path | str, nodes: dict[str, dict[str, Any]],
            reach: dict[str, set[str]], lenses: dict[str, list[str]],
            tau: float = DEFAULT_TAU, *, _labels: dict[str, int] | None = None) -> list[dict[str, Any]]:
    """Cluster the live rung-instances by technique meaning, keep the clusters spanning >=2 themes,
    and return one descriptor per technique: ``{key, technique_id, members, authors, themes,
    cross_author}``. Pure - the caller mutates the network (so resolution is testable apart from the
    mutation). ``_labels`` injects a precomputed clustering (tests / a blessed cache), bypassing the
    embedder. Empty on any embedder/dep unavailability - the build then carries no technique layer,
    never breaks."""
    repo_root = Path(repo_root)
    records = [(rid, m) for rid, m in _rung_instances(repo_root) if rid in nodes]
    if len(records) < 2 * MIN_THEMES:
        return []
    rids = [rid for rid, _ in records]
    metas = [m for _, m in records]

    if _labels is not None:
        labels = [_labels.get(rid, -(i + 1)) for i, rid in enumerate(rids)]
    else:
        try:
            # HOT-2 (2026-08-20 self-audit): pass the THUNK, never a live backend - _embed only
            # calls it if a hash actually comes up stale (see its docstring). Eagerly building the
            # backend here, before staleness is even checked, is exactly the defect being cured.
            from laplace.representation.embed_router import get_backend
            labels = _labels_cached(repo_root, rids, [m["text"] for m in metas], tau, get_backend)
            if labels is None:
                return []
        except Exception:               # noqa: BLE001 - any embed/dep failure carries no technique layer
            return []

    # IDF over rung-name tokens, for distinctive keys
    df: Counter = Counter()
    for m in metas:
        df.update(set(_toks(m["name"])))
    ndoc = max(1, len(metas))
    idf = {w: math.log(ndoc / c) for w, c in df.items()}

    groups: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        groups.setdefault(lab, []).append(i)

    persons: list[dict[str, Any]] = []
    used_keys: dict[str, int] = {}
    for _lab, idxs in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        members = sorted(rids[i] for i in idxs)
        mm = [metas[i] for i in idxs]
        themes = sorted({m["theme_id"] for m in mm})
        if len(themes) < MIN_THEMES:                # not cross-program - not a transferable technique
            continue
        authors = sorted({m["author"] for m in mm})
        base = _key(mm, idf)
        key = base
        if key in used_keys:                        # disambiguate a colliding distinctive-token key
            used_keys[base] += 1
            key = f"{base}-{used_keys[base]}"
        else:
            used_keys[base] = 1
        persons.append({"key": key, "technique_id": TECHNIQUE_PREFIX + key,
                        "members": members, "authors": authors, "themes": themes,
                        "cross_author": len(authors) >= 2})
    return persons


# ---------------------------------------------------------------------------
# the overlay - attach the technique apexes + the lifted transfer edges IN PLACE
# ---------------------------------------------------------------------------

def technique_overlay(repo_root: Path | str, nodes: dict[str, dict[str, Any]],
                      reach: dict[str, set[str]], lenses: dict[str, list[str]],
                      tau: float = DEFAULT_TAU, *, _labels: dict[str, int] | None = None
                      ) -> list[dict[str, Any]]:
    """Attach the resolved technique apexes + the lifted move-edges to the network IN PLACE (the
    build-time hook, sibling of ``identity_lens.identity_overlay``). For each technique: emit
    ``technique://<key>`` (members = rung instances, reach = union + the technique atom), inject the
    technique atom into every member's reach (the cross-author coupling), stamp every member's
    ``techniques`` uplink. Then lift the generators' ``moves`` to conjectural theme<->theme
    couplings + a ``transfers`` render handle. Returns the technique descriptors for logging/tests.
    Guarded: a failure here must never break the network build."""
    try:
        techniques = resolve(repo_root, nodes, reach, lenses, tau, _labels=_labels)
    except Exception:                                       # noqa: BLE001 - the overlay is enrichment
        return []
    root_id = "" if "" in nodes else next((k for k, v in nodes.items() if v.get("parent") is None), "")
    for t in techniques:
        key, tid, members = t["key"], t["technique_id"], t["members"]
        tatom = _TECHNIQUE_ATOM + key
        name_kw = sorted(set(_toks(key)))
        member_grades = [nodes[m].get("grade", 0) for m in members if m in nodes]
        grade = (max(member_grades) + 1) if member_grades else 1
        union: set[str] = {tatom}
        member_lenses: set[str] = set()
        for m in members:
            if m not in nodes:
                continue
            reach[m] = set(reach.get(m, set())) | {tatom}   # the shared atom -> instances now couple
            union |= reach[m]
            member_lenses |= set(lenses.get(m, []))
            tech = list(nodes[m].get("techniques") or [])
            if tid not in tech:
                tech.append(tid)
            nodes[m]["techniques"] = tech                   # the ring-UP handle (parent left intact)
            nodes[m]["keywords"] = sorted(set(nodes[m].get("keywords") or []) | set(name_kw))
        span = (f"{len(t['authors'])} authors" if t["cross_author"]
                else f"{len(t['themes'])} programs (one author)")
        nodes[tid] = {"id": tid, "grade": grade, "parent": root_id, "leaf": False,
                      "members": members, "coverage": name_kw, "keywords": name_kw,
                      "technique_apex": True, "cross_author": t["cross_author"],
                      "resolved_authors": t["authors"], "resolved_themes": t["themes"],
                      "essence": (f"{key.replace('-', ' ')} - one technique across {span}; "
                                  "the cross-program technique apex, members are the per-author/"
                                  "per-theme rung instances that wield it")}
        reach[tid] = union
        # the apex wears the technique badge AND its members' lenses, so a lens-local navigation
        # (the physics view) still surfaces it - the cross-program unification is visible from
        # inside the lens it spans, not only from a dedicated technique view.
        lenses[tid] = [TECHNIQUE_LENS] + sorted(member_lenses)
        if root_id in nodes and tid not in nodes[root_id].get("members", []):
            nodes[root_id].setdefault("members", []).append(tid)

    # lift the 91 moves: the technique-transfer graph as CONJECTURAL theme<->theme couplings (the
    # creativity seed - a technique crossing programs surfaces on a wide ideation pull, not recall),
    # plus a `transfers` handle the navigator/reconstruct render reads.
    try:
        moves = _moves(repo_root, nodes)
    except Exception:                                       # noqa: BLE001 - moves are enrichment too
        moves = []
    for mv in moves:
        frm, to, paper = mv["from"], mv["to"], mv["paper"]
        atom = _MOVE_ATOM + (paper or f"{frm}->{to}")
        reach[frm] = set(reach.get(frm, set())) | {atom}    # both ends share the conjectural atom
        reach[to] = set(reach.get(to, set())) | {atom}
        outs = list(nodes[frm].get("transfers") or [])
        outs.append({"to": to, "paper": paper, "why": mv["why"]})
        nodes[frm]["transfers"] = outs                      # directed: this theme sent the technique
        ins = list(nodes[to].get("transferred_into") or [])
        ins.append({"from": frm, "paper": paper})
        nodes[to]["transferred_into"] = ins
    return techniques
