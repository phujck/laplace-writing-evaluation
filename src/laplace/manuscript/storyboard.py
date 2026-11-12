"""The STORYBOARD - edit the projection's NARRATIVE STRUCTURE as a board, then rebuild.

The projection viewer lets you review the compiled paper's prose and trace each span
back to its source nodes, but it gives no way to see or edit the paper's *narrative
structure* - the section spine, each section's job, and which nodes each section pins.
That structure lives in ``projection_plan.json`` (the content+order contract), which
until now was hand-edited JSON and blind-rebuilt. The storyboard is that plan's face:
sections as columns, pinned nodes as chips, the un-projected pool as a tray, the
conceptric spine as a rail. Drag to respine; rebuild only what changed.

Design principle (his): "there is one thing - treat the interface as a projection of a
single underlying object." A section is a spine segment plus its node pool; a node
carries the spine tag, the ``projection.term`` handle, and (Stage B) its section_ref.
Stage A edits the plan-object; the plan stays the store. The plan write is an
append-only ledger reducing to JSON (mirroring ``corpus_ingest.rewire_add``), so the
later move to a *derived* plan is a change of reducer input, not a surface rewrite.

Pure handler module, same contract as ``projection_viewer`` / ``shared_ui``: the scanner
owns the HTTP server and dispatches ``/storyboard*`` here via :func:`handle`. This module
never starts a server and never spends tokens - it prepares briefs and a dispatch
manifest the local projection skill consumes for the LLM leg.
"""

from __future__ import annotations
from laplace.core.checkout import package_root
from laplace.core import observe
from laplace.pipeline import registry

import importlib.util
import hashlib
import os
import json
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

_HTML = package_root() / "web" / "storyboard.html"   # the page is the HTTP adapter's resource
_JSON = "application/json; charset=utf-8"

# plan writes are serialised in-process (the scanner is a threading server, one
# process): append-to-ledger + reduce + write is one critical section per corpus.
_PLAN_LOCK = threading.Lock()

# the ops the board emits (the drag verbs). CHEAP ops leave every section's node
# SET unchanged, so the prose is still valid and only the \input order / a title
# string moves; EXPENSIVE ops change a section's substrate, so its builder must
# re-run. The authoritative dirty check (A2) is the per-section % NODES diff; this
# per-op class is the fast preliminary the board shows the instant an edit lands.
# The vocabulary lives in the ONE schema module; local names kept for readers.
from laplace.engine import engine_ledger
from laplace.pipeline import pathsafe as _pathsafe
from laplace.pipeline.schema import (CHEAP_OPS as _CHEAP_OPS,
                                     EXPENSIVE_OPS as _EXPENSIVE_OPS,
                                     PLAN_OP_KINDS as _OP_KINDS)


def _repo_root() -> Path:
    from laplace.core.checkout import repo_root as rr   # the serving checkout's owner (the server module held the same object under an old name)
    return rr()


def _q1(query: dict, key: str, default: str = "") -> str:
    v = query.get(key, default)
    if isinstance(v, (list, tuple)):
        v = v[0] if v else default
    return (v or default).strip()


def _json_resp(status: int, obj: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(obj, ensure_ascii=False).encode("utf-8")


# ---------------------------------------------------------------------------
# the plan, located through the ONE registry (pipeline.registry.plan_path_for), read raw
# ---------------------------------------------------------------------------

def _load_plan(corpus: str, repo_root: Path | str | None = None) -> tuple[Path, dict] | None:
    """The authored plan for a corpus: (path, dict), or None when unknown/missing.
    The path is registry-fenced by pipeline.registry.plan_path_for - an unknown corpus name
    (including traversal shapes) never touches the filesystem."""
    p = registry.plan_path_for(corpus, repo_root)
    if p is None:
        return None
    try:
        return p, json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _section_out(s: dict) -> dict:
    """One plan section (or appendix) normalised for the board. Every field the
    columns render, defaulted so a thin section never breaks the layout."""
    return {
        "id": s.get("id"),
        "title": s.get("title") or s.get("id") or "",
        "kind": s.get("kind") or "section",
        "parent_id": s.get("parent_id"),
        "source_file": s.get("source_file"),
        "job": s.get("job") or "",
        "notes": s.get("notes") or "",
        "refs": list(s.get("refs") or []),
        "beats": list(s.get("beats") or []),
        "nodes_in_order": list(s.get("nodes_in_order") or s.get("nodes") or []),
        "figures": list(s.get("figures") or []),
        "spec": s.get("spec"),
    }


def enriched_plan(corpus: str, repo_root: Path | str | None = None) -> dict[str, Any] | None:
    """The board payload: the plan's sections + appendices with full jobs/refs/notes,
    plus per-node handles (term, kind, grade, retired/missing) so chips render, the
    conceptric spine rail, the residue (un-projected) summary, and coverage numbers.
    One round-trip fills the whole board. Built over the SAME corpus_network the
    navigator/viewer use - never a parallel data layer."""
    loaded = _load_plan(corpus, repo_root)
    if loaded is None:
        return None
    _, plan = loaded
    rr = Path(repo_root).resolve() if repo_root is not None else _repo_root()

    from laplace.research import corpus_ingest as ci
    troot = ci.resolve_corpus(rr, corpus)
    net = ci.corpus_network(troot, repo_root=rr, name=corpus) if troot else {"nodes": {}}
    nodes = net.get("nodes", {})

    sections = [_section_out(s) for s in (plan.get("sections") or [])]
    appendices = [_section_out(s) for s in (plan.get("appendices") or [])]

    # per-node handle for every id referenced anywhere on the board (chip label + colour)
    ref_ids: set[str] = set()
    for s in sections + appendices:
        ref_ids.update(s["nodes_in_order"])
        ref_ids.update(s["beats"])
        ref_ids.update(s["figures"])

    def node_meta(nid: str) -> dict:
        nd = nodes.get(nid)
        if nd is None:
            return {"id": nid, "term": None, "kind": None, "grade": None,
                    "retired": False, "missing": True, "section_ref": None}
        proj = nd.get("projection") or {}
        return {"id": nid, "term": proj.get("term"), "kind": nd.get("kind"),
                "grade": nd.get("grade"),
                "retired": bool(nd.get("retired") or proj.get("retired")),
                "missing": False,
                # the substrate side of the beat<->section anchoring: the spine
                # BEAT this node's projection points at (B1's mirror), so the
                # board can light the anchored chips when a beat is hovered
                "section_ref": proj.get("section_ref")}

    node_meta_map = {nid: node_meta(nid) for nid in sorted(ref_ids)}

    # the conceptric spine rail - the ordered beats with their one-line term handle
    spine = [{**b, "term": (nodes.get(b["id"], {}).get("projection") or {}).get("term")}
             for b in net.get("spine", [])]

    # residue (the un-projected pool) + coverage - degrade gracefully if the paper is
    # not yet compiled / walkable (residue reports an error rather than raising)
    meta = plan.get("meta") or {}
    target = (meta.get("target_dir") or "").rstrip("/")
    residue: dict | None = None
    if target and repo_root is None:
        from laplace.manuscript import projection_viewer as pv
        try:
            r = pv.residue(target + "/main.tex", corpus)
            residue = None if "error" in r else r
        except Exception:  # a walk/parse hiccup must never blank the board
            residue = None

    planned = {n for s in sections + appendices for n in s["nodes_in_order"]}
    # B1/C precondition: a BODY section with no live spine beat has no anchor for its
    # nodes' section_ref mirror (and can't be re-derived if the plan goes derived).
    # Appendices are legitimately beatless (their nodes resolve via anchor theorems,
    # not the narrative spine), so only body sections are flagged. Cheap to enforce
    # early, expensive to discover late.
    without_beats = [s["id"] for s in sections
                     if _anchor_beat(plan, net, s["id"]) is None]
    # spine drift (B2): where the plan's beats[] and the node-side spine tag disagree.
    # Exposed, never auto-resolved - reconciling the two axes is the C-stage's job.
    plan_beats = {b for s in sections + appendices for b in s["beats"]}
    spine_tagged = {b["id"] for b in spine}
    spine_drift = {
        "untagged_beats": sorted(plan_beats - spine_tagged),   # plan claims a beat the graph doesn't tag
        "orphan_spine": sorted(spine_tagged - plan_beats),     # spine node no section's beats[] claims
    }
    coverage = {
        "planned": len(planned),
        "n_live": (residue or {}).get("n_live"),
        "n_residue": (residue or {}).get("n_residue"),
        "sections_without_beats": without_beats,
        "spine_drift": spine_drift,
    }

    out_meta = {k: meta.get(k) for k in ("project", "artefact", "form", "target_dir")}
    # meta.contribution_rank (2026-07-13, the return-path push): the ONE authored
    # judgement the return path pivots on - additive (present only when the plan
    # carries it). W-SB (2026-07-22): the board's rank is no longer a raw string the
    # client regexes {#id} off with one global invite - each card is GROUNDED
    # server-side (source nodes + the why), composed by _ground_contribution_rank so
    # the client renders per-card grounding verbatim and reconstructs nothing (the
    # weighting-card-grounding-visible floor). node-side owners + terms are read here
    # over the SAME net the board already built.
    owners = _section_owner_index(sections, appendices)
    # the contribution home: the section a goal-grounded claim lands in (the abstract,
    # where the top-line contribution is stated), so its rank chip lights a board tile.
    goal_home = next((s.get("id") for s in sections if s.get("id") == "abstract"),
                     (sections[0].get("id") if sections else None))
    rank = _ground_contribution_rank(meta, nodes, owners, goal_home=goal_home)
    if rank is not None:
        out_meta["contribution_rank"] = rank

    from laplace.manuscript.bindings import spine_snapshot
    return {
        "corpus": corpus,
        "meta": out_meta,
        "sections": sections,
        "appendices": appendices,
        "node_meta": node_meta_map,
        "spine": spine,
        "spine_revision": spine_snapshot(corpus, rr, network=net)[1],
        "residue": residue,
        "coverage": coverage,
    }


# ---------------------------------------------------------------------------
# W-SB — THE GROUNDING + THE BRIEF (2026-07-22, his ruling: the storyboard is
# "the place where I can most easily see the thing that's going to be projected").
# The surface joins the one instrument (engine.mjs): it RESTS at a composed brief
# and materialises cards on focus. Two read-model additions carry that:
#   · _ground_contribution_rank — each weighting card carries its SOURCE NODES + the
#     WHY, composed here (the client renders, never reconstructs);
#   · storyboard_brief — the DELTA-AND-ASK brief: what MOVED since he last looked and
#     what is ASKED of him now (never inventory prose), plus one-line counts + the
#     grounded section cards + weighting cards the materialise doors render.
# ---------------------------------------------------------------------------

def _section_owner_index(sections: list[dict], appendices: list[dict]) -> dict[str, str]:
    """node id -> its FIRST owning section id (document order), for the grounding
    doors. Beats and pool nodes both resolve; first owner wins (deterministic)."""
    owners: dict[str, str] = {}
    for s in list(sections) + list(appendices):
        sid = s.get("id")
        for key in ("beats", "nodes_in_order"):
            for nid in s.get(key) or []:
                owners.setdefault(nid, sid)
    return owners


def _node_term(nodes: dict, nid: str) -> str:
    """A node's plain handle: its projection.term, else the head of its essence, else
    the id tail. Never a raw kind-prefixed id above the fold (the register law)."""
    nd = nodes.get(nid) or {}
    proj = nd.get("projection") or {}
    term = proj.get("term")
    if term:
        return str(term)
    ess = (nd.get("essence") or "").strip()
    if ess:
        head = ess.split(". ")[0]
        return head[:70] + ("…" if len(head) > 70 else "")
    tail = nid.split(":", 1)[-1]
    return tail.replace("-", " ")


def _goal_node(nodes: dict) -> str | None:
    """The corpus goal node — every contribution is a contribution TO it, so it is the
    universal grounding anchor when a claim resolves no sharper source."""
    for nid, nd in nodes.items():
        if nid.startswith("goal:") or (nd.get("kind") == "goal"):
            return nid
    return None


_RANK_ID_RE = re.compile(r"\b(?:res|thm|derivation|eq|lem|def|goal|fig|irf|ires|cluster|readings):[a-z0-9_\-]+", re.I)
_RANK_LINK_RE = re.compile(r"link-[a-z0-9\-]+")
_RANK_TAG_RE = re.compile(r"\s*\{#([^}]+)\}\s*$")
_RANK_NUM_RE = re.compile(r"^(\d+)\.\s*(.*)$", re.S)
_RANK_ROLE_RE = re.compile(r"\s*\[([^\]]+)\]\s*$")
_RANK_PAREN_ROLE_RE = re.compile(r"\s*\(([^)]+)\)\s*$")

# a served display line must never shout: a run of 3+ consecutive all-caps words is
# the register breach scripts/audit_register.py forbids. Such a run is sentence-cased
# wherever it appears; a lone acronym (SQL, FALQON, LCU) is left intact.
_SHOUT_RUN_RE = re.compile(r"[A-Z]{2,}(?:[ -][A-Z]{2,}){2,}")
# a coded node handle carrying no authored term (fal_clm_001) — masked to a legible
# section-anchored label rather than shown raw (a retire/beat target stays readable).
_OPAQUE_HANDLE_RE = re.compile(r"^[a-z]{2,}_[a-z]{2,}_\d+$|^[a-z]+_\d{3,}$", re.I)
# a leading connective that buries the claim's subject ("from X ..., that <subject>").
_PREAMBLE_RE = re.compile(
    r"^(?:from|because|since|given|by|under|for|with|in|to|of|as)\b.*?,\s+that\s+(.+)$",
    re.I | re.S)


def _deshout(s: str) -> str:
    """Sentence-case any run of 3+ consecutive all-caps words (the register law),
    leaving lone acronyms untouched."""
    return _SHOUT_RUN_RE.sub(lambda m: m.group(0)[:1] + m.group(0)[1:].lower(), s or "")


# ── math notation at glance altitude ──────────────────────────────────────────────
# A title/headline must never carry ascii-math soup (``L^2``, ``<K^dag K>``, ``eps_fb^2``)
# at rest — the raw form stays at audit depth (the claim field, the open). This normalises
# the common notation to legible Unicode: digit exponents to superscripts, expectation /
# angle brackets to ⟨⟩, a dagger, greek spellings to their letters, digit subscripts
# lowered, subscript-letter soup de-underscored — and GUARANTEES no residual ``^ < >``
# survives the glance (the register/glance law the storyboard walk asserts).
_SUP_MAP = str.maketrans("0123456789+-n", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ")
_SUB_MAP = str.maketrans("0123456789+-", "₀₁₂₃₄₅₆₇₈₉₊₋")
_GREEK = {
    "epsilon": "ε", "eps": "ε", "delta": "δ", "Delta": "Δ", "lambda": "λ", "mu": "μ",
    "nu": "ν", "theta": "θ", "Theta": "Θ", "pi": "π", "sigma": "σ", "Sigma": "Σ",
    "tau": "τ", "phi": "φ", "psi": "ψ", "rho": "ρ", "kappa": "κ", "alpha": "α",
    "beta": "β", "gamma": "γ", "Gamma": "Γ", "omega": "ω", "Omega": "Ω", "chi": "χ",
}
# match a greek spelling as a token or a subscript-prefixed base (``eps`` in ``eps_fb``),
# never mid-word (``especially`` stays intact): the tail must be a non-letter or end.
_GREEK_RE = re.compile(r"\b(" + "|".join(sorted(_GREEK, key=len, reverse=True)) +
                       r")(?=[^A-Za-z]|$)")
_ALLNUM = "0123456789+-n"


def _plainify_math(s: str) -> str:
    """Normalise ascii-math to legible Unicode for a glance-altitude title/headline,
    guaranteeing no raw ``^``/``<``/``>``/``_``-subscript soup survives. Idempotent on
    already-clean prose; the raw string stays at audit depth (this is display-only)."""
    text = s or ""
    if not text:
        return text
    # expectation / angle brackets FIRST (before caret handling): <K^dag K> → ⟨K^dag K⟩
    text = re.sub(r"<\s*([^<>]{1,80}?)\s*>", r"⟨\1⟩", text)
    # greek spellings → letters (eps → ε), before subscripts fold the underscore away
    text = _GREEK_RE.sub(lambda m: _GREEK[m.group(1)], text)
    # dagger exponent: ^dag / ^{dagger} / ^† → †
    text = re.sub(r"\^\s*\{?\s*(?:dagger|dag|†)\s*\}?", "†", text, flags=re.I)
    # grouped exponents ^{2n} and token exponents ^2 → superscript (digit-like only)
    text = re.sub(r"\^\{([^{}]{1,12})\}",
                  lambda m: (m.group(1).translate(_SUP_MAP)
                             if all(c in _ALLNUM for c in m.group(1)) else m.group(1)), text)
    text = re.sub(r"\^([0-9]+)", lambda m: m.group(1).translate(_SUP_MAP), text)
    # subscripts: _{ab}/_2 → lowered digits; _fb (letters) → underscore dropped (no soup)
    text = re.sub(r"_\{([^{}]{1,12})\}",
                  lambda m: (m.group(1).translate(_SUB_MAP)
                             if all(c in "0123456789+-" for c in m.group(1)) else m.group(1)), text)
    text = re.sub(r"_([0-9]+)", lambda m: m.group(1).translate(_SUB_MAP), text)
    text = re.sub(r"_([A-Za-z]{1,5})", r"\1", text)
    # the guarantee: no residual glance-forbidden character survives (rare exotic exponents)
    text = text.replace("^", "").replace("<", "⟨").replace(">", "⟩")
    return text


def _compose_display(claim: str) -> str:
    """A short, sentence-cased headline of a ranked claim for the board's rank strip.
    The leading claim-handle prefix ("D1 (link-x, derived):") masks to audit depth; a
    subject buried behind a connective preamble is promoted to the front; the trailing
    audit-depth descriptor ("... — the X derivation.") is dropped; any shouting run is
    sentence-cased; and the line leads capitalised with the claim's subject. The raw
    ``claim`` stays as data (the open reads it in full)."""
    text = re.sub(r"^[A-Z]\d{1,3}\s*\([^)]*\)\s*:\s*", "", claim or "")
    text = _deshout(text).strip()
    m = _PREAMBLE_RE.match(text)
    if m:
        text = m.group(1).strip()
    else:
        text = re.sub(r"^that\s+", "", text, flags=re.I).strip()
    head = text.split("—", 1)[0].strip().rstrip(" ,;:")
    text = (head or text).strip().rstrip(" ,;:")
    if text:
        text = text[:1].upper() + text[1:]
    text = _deshout(text)
    text = _plainify_math(text)     # no ascii-math soup at glance; the raw claim stays as data
    limit = 120
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:(-") + "…"
    return text


def _resolve_rank_sources(claim: str, nodes: dict) -> list[str]:
    """The source nodes a ranked claim draws from, resolved mechanically from the claim
    text: explicit kind-prefixed node ids first, then ``link-<token>`` derivation
    references matched to a ``derivation:`` node by shared token. Deduped, order-kept."""
    src: list[str] = []
    seen: set[str] = set()
    for nid in _RANK_ID_RE.findall(claim):
        if nid in nodes and nid not in seen:
            seen.add(nid)
            src.append(nid)
    for tok in _RANK_LINK_RE.findall(claim):
        core = tok[len("link-"):].split("-")[0]
        if not core:
            continue
        for nid in nodes:
            if nid.startswith("derivation:") and core in nid and nid not in seen:
                seen.add(nid)
                src.append(nid)
                break
    return src


def _ground_contribution_rank(meta: dict, nodes: dict,
                              owners: dict[str, str],
                              goal_home: str | None = None) -> dict[str, list[dict]] | None:
    """The board's GROUNDED contribution rank: each primary/excluded card as a dict
    carrying (claim, role, rank, id, source NODES, the WHY) — composed server-side so
    the client renders each card's grounding in place and never regexes it back out.

    Reuses the single parse (schema.contribution_rank_lines) over the authored rank, then
    grounds each line: source nodes resolved from the claim text (a derivation/result
    id it names, else its ``link-`` reference), falling back to the goal node (every
    contribution grounds in the goal) and, last, the claim's own stable content-id — so
    every card names a non-empty source with a working door. Returns None for a
    rank-less plan (the additive floor: absent rank changes nothing)."""
    from laplace.pipeline import schema
    # the respine {value, projection_ruling} envelope is unwrapped inside the ONE
    # decode (schema.contribution_rank_lines -> unwrap_contribution_rank); no second
    # copy of the shape logic lives here.
    raw = meta.get("contribution_rank")
    primary_lines, excluded_lines = schema.contribution_rank_lines(raw)
    if not primary_lines and not excluded_lines:
        return None
    goal = _goal_node(nodes)

    def node_entry(nid: str) -> dict:
        # the board tile a claim's source node LANDS in, so hovering the claim lights
        # it (the highlight bus keys on section). Resolved from where the node is
        # pinned; else its own reconciled section anchor (projection.section_ref →
        # sec:<id> or an owned beat); else, for the goal, the contribution home (the
        # abstract) — every goal-grounded contribution is stated there. Left null when
        # nothing resolves (absence stated: the lens then shows no landing line).
        nd = nodes.get(nid) or {}
        sec = owners.get(nid)
        if not sec:
            sr = (nd.get("projection") or {}).get("section_ref") or ""
            if isinstance(sr, str) and sr.startswith("sec:"):
                sec = sr[4:]
            elif sr:
                sec = owners.get(sr)
        if not sec and (nid.startswith("goal:") or nd.get("kind") == "goal"):
            sec = goal_home
        return {"id": nid, "term": _node_term(nodes, nid),
                "kind": nd.get("kind"), "section": sec}

    def ground(line: str, excluded: bool) -> dict:
        text, cid = line, None
        tm = _RANK_TAG_RE.search(text)
        if tm:
            cid = tm.group(1)
            text = text[:tm.start()]
        rank_n = None
        if not excluded:
            nm = _RANK_NUM_RE.match(text)
            if nm:
                rank_n = int(nm.group(1))
                text = nm.group(2)
        role = ""
        rm = (_RANK_ROLE_RE.search(text) if not excluded else _RANK_PAREN_ROLE_RE.search(text))
        if rm:
            role = rm.group(1).strip()
            text = text[:rm.start()]
        claim = text.strip()

        source_ids = _resolve_rank_sources(claim, nodes)
        resolved = bool(source_ids)
        if not source_ids and goal:
            source_ids = [goal]
        source_nodes = [node_entry(n) for n in source_ids]
        if not source_nodes:                       # last-resort: the claim's own handle
            source_nodes = [{"id": cid or "contribution", "term": claim[:60],
                             "kind": "contribution", "section": None}]

        first_term = source_nodes[0]["term"]
        if excluded:
            why = ("Deliberately NOT claimed — the paper's honesty contract. It states "
                   "what the work does not promise, so a reader is not misled"
                   + (f"; nearest stock: {first_term}." if resolved else "."))
        elif rank_n == 1:
            why = ("The primary defended contribution — the whole argument must earn it. "
                   f"It grounds in {first_term}"
                   + ("." if resolved else " (the paper's goal — this claim names no sharper node yet)."))
        else:
            why = (f"A derived step on the load path (position #{rank_n or '?'}); it inherits "
                   f"from the claims above and rests on {first_term}"
                   + ("." if resolved else " (the goal — no sharper source node named yet)."))
        # the display line speaks plainly at glance altitude: a short sentence-cased
        # headline of the claim (subject-first, shouting runs cooled, prefix + audit
        # tail dropped) — never the goal body. The raw claim stays as data.
        disp = _compose_display(claim)
        return {"id": cid or f"rank-{rank_n or 'x'}", "rank": rank_n, "claim": claim,
                "display": disp,
                "role": role, "excluded": excluded, "resolved": resolved,
                "nodes": source_nodes, "why": why}

    return {"primary": [ground(l, False) for l in primary_lines],
            "excluded": [ground(l, True) for l in excluded_lines]}


# ---------------------------------------------------------------------------
# the plan-write LEDGER - append-only ops reduced over an authored base to the
# projection_plan.json every downstream script reads. This is the C-hinge: the
# derived-plan future swaps the reducer's INPUT (node-side facts for the ledger),
# never this write surface. Mirrors corpus_ingest.rewire_add's friction->regrow.
# ---------------------------------------------------------------------------

def _sidecar(corpus: str, suffix: str, repo_root: Path | str | None = None) -> Path | None:
    """A file beside the plan (base snapshot / ledger), registry-fenced by the
    same resolver the plan uses."""
    p = registry.plan_path_for(corpus, repo_root)
    return None if p is None else p.with_name("projection_plan" + suffix)


def _find_section(plan: dict, sid: str) -> dict | None:
    for key in ("sections", "appendices"):
        for s in plan.get(key) or []:
            if s.get("id") == sid:
                return s
    return None


def _apply_op(plan: dict, op: dict) -> None:
    """Fold one ledger op into the plan dict IN PLACE. Unknown/malformed ops are
    skipped rather than raising, so one bad record never poisons the reduction."""
    kind = op.get("kind")

    if kind == "set-meta":
        # merge, never replace - the same semantics as L1's set-projection, so a
        # later set-meta can add a typed field without clobbering earlier ones
        if isinstance(op.get("value"), dict):
            plan.setdefault("meta", {}).update(op["value"])
        return

    if kind == "reorder-sections" or kind == "reorder-appendices":
        key = "sections" if kind == "reorder-sections" else "appendices"
        order = op.get("order") or []
        cur = {s.get("id"): s for s in plan.get(key) or []}
        # keep the requested order; append any id the op omitted (never drop a section)
        plan[key] = [cur[i] for i in order if i in cur] + \
            [s for s in plan.get(key) or [] if s.get("id") not in set(order)]
        return

    if kind == "add-section":
        ident = str(op.get("section") or "").strip()
        title = str(op.get("title") or "").strip()
        collection = "appendices" if op.get("collection") == "appendices" else "sections"
        if (not ident or not title or _find_section(plan, ident) is not None
                or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]{0,79}", ident)):
            return
        entry = {"id": ident, "title": title,
            "kind": op.get("outline_kind", "section"), "parent_id": op.get("parent_id"),
            "job": str(op.get("job") or ""), "notes": str(op.get("notes") or ""),
            "refs": list(op.get("refs") or []), "beats": list(op.get("beats") or []),
            "nodes_in_order": list(op.get("nodes_in_order") or []),
            "figures": list(op.get("figures") or [])}
        for key in ("source_file", "source_label", "source_title", "source_plan_title"):
            if op.get(key) is not None:
                entry[key] = op[key]
        rows = plan.setdefault(collection, [])
        before = next((i for i, row in enumerate(rows) if row.get("id") == op.get("before_section")), None)
        after = next((i for i, row in enumerate(rows) if row.get("id") == op.get("after_section")), None)
        rows.insert(before if before is not None else after + 1 if after is not None else len(rows), entry)
        return

    if kind == "remove-section":
        ident = str(op.get("section") or "")
        for collection in ("sections", "appendices"):
            rows = list(plan.get(collection) or [])
            doomed = {ident}
            while True:
                children = {str(item.get("id")) for item in rows
                            if item.get("parent_id") in doomed}
                if children <= doomed:
                    break
                doomed.update(children)
            plan[collection] = [item for item in rows if item.get("id") not in doomed]
        return

    if kind == "restore-section":
        entries = op.get("entries")
        if not isinstance(entries, list):
            return
        for entry in sorted((item for item in entries if isinstance(item, dict)),
                            key=lambda item: (item.get("collection") == "appendices",
                                              item.get("index", 10**9))):
            value = entry.get("section")
            collection = ("appendices" if entry.get("collection") == "appendices"
                          else "sections")
            if (not isinstance(value, dict) or not value.get("id")
                    or _find_section(plan, str(value.get("id"))) is not None):
                continue
            rows = list(plan.get(collection) or [])
            index = entry.get("index")
            rows.insert(index if isinstance(index, int) and 0 <= index <= len(rows)
                        else len(rows), value.copy())
            plan[collection] = rows
        return

    sec = _find_section(plan, op.get("section", ""))
    if kind == "set-outline" and sec is not None:
        sec["kind"] = op["outline_kind"]
        sec["parent_id"] = op.get("parent_id")
    elif kind == "bind-source" and sec is not None:
        for key in ("source_file", "source_label", "source_title", "source_plan_title", "source_heading", "source_anchor"):
            if key in op:
                sec[key] = op[key]
    elif kind == "retitle" and sec is not None:
        sec["title"] = op.get("title", sec.get("title"))
        # Source-mirror operations retain the exact title they last represented;
        # an ordinary planning retitle leaves that provenance untouched.
        for key in ("source_title", "source_plan_title", "source_heading", "source_anchor"):
            if key in op:
                sec[key] = op[key]
    elif kind == "edit-job" and sec is not None:
        sec["job"] = op.get("job", "")
    elif kind == "edit-notes" and sec is not None:
        sec["notes"] = op.get("notes", "")
    elif kind == "set-refs" and sec is not None:
        sec["refs"] = list(op.get("refs") or [])
    elif kind == "set-serves" and sec is not None:
        # C3.1 section ownership: pin the contribution(s) this section earns — a
        # contribution content-id or 1-based rank number (or a list of them),
        # resolved against meta.contribution_rank by validate's check_serves.
        # Mirrors set-refs' shape. None / [] CLEARS the declaration (a section may
        # withdraw what it earns); a scalar is normalised to a one-element list so
        # the stored plan keeps a uniform serves shape.
        serves = op.get("serves")
        if serves is None or serves == []:
            sec.pop("serves", None)
        elif isinstance(serves, list):
            sec["serves"] = list(serves)
        else:
            sec["serves"] = [serves]
    elif kind == "reorder-nodes" and sec is not None:
        order = op.get("order") or []
        have = set(sec.get("nodes_in_order") or [])
        sec["nodes_in_order"] = [n for n in order if n in have] + \
            [n for n in sec.get("nodes_in_order") or [] if n not in set(order)]
    elif kind == "set-nodes" and sec is not None:
        # replace the whole pool (C - derive): the plan section's node pool becomes a
        # projection of the node graph. Validated in plan_write like any other op.
        order = op.get("order")
        if isinstance(order, list):
            sec["nodes_in_order"] = list(order)
    elif kind == "toggle-beat" and sec is not None:
        node = op.get("node")
        beats = list(sec.get("beats") or [])
        on = op.get("on", node not in beats)
        if on and node not in beats and node in (sec.get("nodes_in_order") or []):
            beats.append(node)
        elif not on and node in beats:
            beats.remove(node)
        sec["beats"] = beats
    elif kind == "add-node" and sec is not None:
        node = op.get("node")
        nio = list(sec.get("nodes_in_order") or [])
        if node and node not in nio:
            idx = op.get("index")
            nio.insert(idx if isinstance(idx, int) and 0 <= idx <= len(nio) else len(nio), node)
            sec["nodes_in_order"] = nio
    elif kind == "remove-node" and sec is not None:
        node = op.get("node")
        for f in ("nodes_in_order", "beats", "figures"):
            sec[f] = [n for n in sec.get(f) or [] if n != node]
    elif kind == "move-node":
        node = op.get("node")
        src = _find_section(plan, op.get("from", ""))
        dst = _find_section(plan, op.get("to", ""))
        if src is not None:
            for f in ("nodes_in_order", "beats"):
                src[f] = [n for n in src.get(f) or [] if n != node]
        if dst is not None and node:
            nio = [n for n in (dst.get("nodes_in_order") or []) if n != node]
            idx = op.get("index")
            nio.insert(idx if isinstance(idx, int) and 0 <= idx <= len(nio) else len(nio), node)
            dst["nodes_in_order"] = nio


def reduce_plan(base: dict, ops: list[dict]) -> dict:
    """The current plan = the authored base with the ledger folded over it, in order.
    Pure: a deep copy is mutated, the base is never touched. Mechanics live in the
    ONE ledger engine; the fold (what an op MEANS) stays here in ``_apply_op``."""
    from laplace.pipeline import ledger as _ledger
    return _ledger.reduce(base, ops, _apply_op)


def _read_ledger(corpus: str, repo_root: Path | str | None = None) -> list[dict]:
    from laplace.pipeline import ledger as _ledger
    lp = _sidecar(corpus, ".friction.jsonl", repo_root)
    return [] if lp is None else _ledger.read_jsonl(lp)


def _ensure_base(corpus: str, repo_root: Path | str | None = None) -> dict | None:
    """The immutable authored base. On first write we snapshot the current plan
    (and archive it) so the ledger always reduces from a fixed origin."""
    bp = _sidecar(corpus, ".base.json", repo_root)
    loaded = _load_plan(corpus, repo_root)
    if loaded is None:
        return None
    plan_path, plan = loaded
    if bp is not None and not bp.is_file():
        bp.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        # a coarse rollback even if the ledger is lost: archive the pre-edit plan once
        arch = plan_path.parent / "archive"
        try:
            arch.mkdir(exist_ok=True)
            stamp = time.strftime("%Y-%m-%d_%H%M%S")
            (arch / f"projection_plan.preboard_{stamp}.json").write_text(
                json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
    try:
        return json.loads(bp.read_text(encoding="utf-8")) if bp and bp.is_file() else plan
    except (OSError, json.JSONDecodeError):
        return plan


def _validate_reduced(reduced: dict, corpus: str, repo_root: Path | str | None = None) -> dict:
    """Run the one plan validator (scripts/validate_projection_plan.py) against the
    reduced-but-not-yet-written plan, via a temp file so we never touch disk until
    it passes. Reused, not reimplemented, so the board's gate can never drift from
    the build's gate."""
    rr = Path(repo_root).resolve() if repo_root is not None else _repo_root()
    vp = rr / "scripts" / "validate_projection_plan.py"
    try:
        spec = importlib.util.spec_from_file_location("_sb_validate", vp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as e:  # validator itself unavailable - do not block, report
        return {"pass": True, "validator_error": f"validator unavailable: {e}"}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as tf:
        json.dump(reduced, tf, ensure_ascii=False)
        tmp = tf.name
    try:
        return mod.validate(tmp, corpus, repo_root=rr)
    except Exception as e:
        return {"pass": True, "validator_error": f"validate() raised: {e}"}
    finally:
        try:
            Path(tmp).unlink()
        except OSError:
            pass


def _append_ledger(corpus: str, op: dict, repo_root: Path | str | None = None) -> None:
    from laplace.pipeline import ledger as _ledger
    lp = _sidecar(corpus, ".friction.jsonl", repo_root)
    if lp is not None:
        _ledger.append_jsonl(lp, op)


def _write_plan_json(corpus: str, plan: dict, repo_root: Path | str | None = None) -> None:
    loaded = _load_plan(corpus, repo_root)  # resolves + fences the path
    p = registry.plan_path_for(corpus, repo_root)
    if p is not None:
        # newline="" so the payload round-trips byte-exact across platforms
        from laplace.core.receipts import file_receipt
        before = p.read_bytes() if p.is_file() else None
        intended = (json.dumps(plan, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        p.write_bytes(intended)
        return file_receipt(Path(repo_root).resolve() if repo_root is not None else _repo_root(), p, before, intended)


def rebuild_class_for(op: dict) -> str:
    return "cheap" if op.get("kind") in _CHEAP_OPS else "expensive"


# ---------------------------------------------------------------------------
# B1 - the dual face. A section-membership edit on the board also mirrors into the
# conceptric NODE GRAPH so verify.py, conceptric2, and the navigator see it. The
# key correction: projection.section_ref is a node -> spine-BEAT edge (verify.py:429
# folds it only if it resolves to a node), NOT a section id. So a section-change
# translates to the section's ANCHOR BEAT. The plan stays primary; section_ref is a
# one-way, idempotent, DERIVED mirror (never read back into the plan), so a lost
# co-emit only lags until the next reconcile - no divergence loop, no rollback.
# ---------------------------------------------------------------------------

def _net(corpus: str, repo_root: Path | str | None = None):
    from laplace.research import corpus_ingest as ci
    rr = Path(repo_root).resolve() if repo_root is not None else _repo_root()
    troot = ci.resolve_corpus(rr, corpus)
    return ci.corpus_network(troot, repo_root=rr, name=corpus) if troot else {"nodes": {}, "spine": []}


def _anchor_beat(plan: dict, net: dict, section_id: str) -> str | None:
    """A section's representative beat: its ``beats`` that carry a spine tag, ordered
    by ``spine_ord``, first one wins. ``None`` when the section names no live spine
    beat - the divergence case the mirror cannot bridge (and the C-hinge precondition)."""
    sec = _find_section(plan, section_id)
    if sec is None:
        return None
    ord_of = {b["id"]: b.get("ord", 0) for b in net.get("spine", [])}
    candidates = [b for b in (sec.get("beats") or []) if b in ord_of]
    if not candidates:
        return None
    return min(candidates, key=lambda b: ord_of[b])


def _node_first_section(plan: dict, node: str) -> str | None:
    """The FIRST section (document order: sections then appendices) whose
    ``nodes_in_order`` contains the node. 30 nodes here live in several sections, but
    ``section_ref`` is a single node->beat edge - so the mirror is deterministic:
    first section wins. Deterministic => idempotent reconcile."""
    # DOCUMENT order is the outline order (`schema.plan_sections`: parents before children,
    # then appendices), the same order `project_structure.state` judges a mirror by.  Walking
    # the raw lists put a child section after every top-level sibling, so a node placed in a
    # child and in a later chapter was reconciled to the chapter's anchor and then judged a
    # mirror gap forever (reproduced 2026-10-14; the live res:main-support-cycle case).
    from laplace.pipeline import schema
    try:
        rows = list(schema.plan_sections(plan))
    except ValueError:
        rows = (plan.get("sections") or []) + (plan.get("appendices") or [])
    for sec in rows:
        if node in (sec.get("nodes_in_order") or sec.get("nodes") or []):
            return sec.get("id")
    return None


def _desired_section_ref(plan: dict, net: dict, node: str) -> str | None:
    """Where a node's ``section_ref`` should point: the anchor beat of its first
    section. ``None`` when the node is in no section, or that section has no beat, or
    the node IS its own anchor (a beat needn't anchor to itself)."""
    sec_id = _node_first_section(plan, node)
    if sec_id is None:
        return None
    anchor = _anchor_beat(plan, net, sec_id)
    return None if (anchor is None or anchor == node) else anchor


def _coemit_membership(corpus: str, plan: dict, op: dict,
                       repo_root: Path | str | None = None) -> dict | None:
    """Mirror a membership op into the node graph via /corpus/rewire set-projection.
    Fires for move/add/remove-node. Recomputes the node's DESIRED section_ref from the
    (already-reduced) plan - so add-into-an-earlier-section, move, and remove all
    resolve correctly for multi-section nodes. Returns a small advisory or None."""
    kind = op.get("kind")
    if kind not in ("move-node", "add-node", "remove-node"):
        return None
    from laplace.research import corpus_ingest as ci
    node = op.get("node")
    if not node:
        return None
    try:
        rr = Path(repo_root).resolve() if repo_root is not None else _repo_root()
        net = _net(corpus, rr)
        desired = _desired_section_ref(plan, net, node)   # None if orphaned/beatless/self
        written = ci.rewire_add(rr, corpus, {"kind": "set-projection", "node": node,
                                             "value": {"section_ref": desired}, "by": "storyboard"})
        if written.get("error"):
            return {"node": node, "mirror_lag": True, "why": written["error"]}
        adv = {"node": node, "section_ref": desired}
        if desired is None and _node_first_section(plan, node) and kind != "remove-node":
            adv["mirror_lag"] = True
            adv["why"] = "the node's first section names no live spine beat to anchor to"
        return adv
    except Exception as e:                        # the mirror is derived - never fail the plan write
        return {"node": node, "mirror_lag": True, "why": f"rewire failed: {e}"}


def _coemit_beat(corpus: str, plan: dict, op: dict,
                 repo_root: Path | str | None = None) -> dict | None:
    """toggle-beat is a plan op (edits ``beats[]``); mirror it to the node-side spine
    tag so the rail (built from net['spine']) and the plan agree. ON -> set-spine
    (tag + next free ord); OFF -> unset-spine. This is the plan-beats <-> node-spine
    reconciliation (B2)."""
    if op.get("kind") != "toggle-beat":
        return None
    from laplace.research import corpus_ingest as ci
    node = op.get("node")
    if not node:
        return None
    try:
        rr = Path(repo_root).resolve() if repo_root is not None else _repo_root()
        net = _net(corpus, rr)
        tagged = {b["id"] for b in net.get("spine", [])}
        if op.get("on"):
            if node not in tagged:
                nxt = max([b.get("ord", 0) for b in net.get("spine", [])], default=-1) + 1
                written = ci.rewire_add(rr, corpus, {"kind": "set-spine", "node": node,
                                                     "ord": nxt, "by": "storyboard"})
                if written.get("error"):
                    return {"node": node, "mirror_lag": True, "why": written["error"]}
                return {"node": node, "spine": "tagged", "ord": nxt}
        else:
            if any(node in (section.get("beats") or []) for section in schema.plan_sections(plan)):
                return {"node": node, "spine": "retained", "reason": "Another reader section still places this beat."}
            if node in tagged:
                written = ci.rewire_add(rr, corpus, {"kind": "unset-spine", "node": node,
                                                     "by": "storyboard"})
                if written.get("error"):
                    return {"node": node, "mirror_lag": True, "why": written["error"]}
                return {"node": node, "spine": "untagged"}
        return {"node": node, "spine": "unchanged"}
    except Exception as e:
        return {"node": node, "mirror_lag": True, "why": f"spine mirror failed: {e}"}


def _coemit(corpus: str, plan: dict, op: dict,
            repo_root: Path | str | None = None) -> dict | None:
    """Dispatch a plan op's node-graph mirror: membership -> section_ref, beat -> spine tag."""
    return (_coemit_membership(corpus, plan, op, repo_root)
            or _coemit_beat(corpus, plan, op, repo_root))


def spine_write(corpus: str, op: dict, repo_root: Path | str | None = None) -> dict:
    """Existing rewire producer with an exact ordered-spine admission/result basis."""
    from laplace.research import corpus_ingest as ci
    from laplace.manuscript.bindings import spine_snapshot
    from laplace.core.receipts import bundle
    root = Path(repo_root).resolve() if repo_root is not None else _repo_root()
    kind = op.get('kind')
    with _PLAN_LOCK:
        net = _net(corpus, root)
        before, revision = spine_snapshot(corpus, root, network=net)
        compact = lambda rows: [{key: row.get(key) for key in ('id', 'ord', 'narrative')} for row in rows]
        before = compact(before)
        if op.get('expected_spine_revision') != revision:
            return {'ok': False, 'error': 'CHANGED_INPUT: narrative spine changed; read the current spine before writing.',
                    'next_read': {'operation': 'structure', 'payload': {'view': 'full'}}}
        ids = [row['id'] for row in before]
        operations = []
        desired = [dict(row) for row in before]
        if kind == 'reorder-spine':
            order = op.get('order') or []
            if not isinstance(order, list) or len(order) != len(set(order)) or set(order) != set(ids):
                return {'ok': False, 'error': 'reorder-spine requires an exact duplicate-free permutation of current live spine membership'}
            by_id = {row['id']: row for row in before}
            desired = [{**by_id[ident], 'ord': index} for index, ident in enumerate(order)]
            operations = [{'kind': 'set-spine', 'node': row['id'], 'ord': row['ord'],
                           'narrative': row['narrative'], 'by': 'storyboard'} for row in desired]
        elif kind in {'set-narrative', 'unset-spine'}:
            ident = op.get('node')
            if ident not in ids:
                return {'ok': False, 'error': kind + ' requires a current live spine node'}
            current = next(row for row in before if row['id'] == ident)
            if kind == 'set-narrative':
                updated = {**current, 'ord': op.get('ord', current['ord']), 'narrative': op.get('narrative', '')}
                desired = [updated if row['id'] == ident else row for row in desired]
                desired.sort(key=lambda row: (row['ord'], row['id']))
                operations = [{'kind': 'set-spine', 'node': ident, 'ord': updated['ord'],
                               'narrative': updated['narrative'], 'by': 'storyboard'}]
            else:
                desired = [row for row in desired if row['id'] != ident]
                operations = [{'kind': 'unset-spine', 'node': ident, 'by': 'storyboard'}]
        else:
            return {'ok': False, 'error': 'unknown spine op ' + repr(kind)}
        if desired == before:
            return {'ok': True, 'applied': True, 'changed': False, 'status': 'CURRENT',
                    'plan_publication': reader_publication('reader-spine', 'UNCHANGED', True, 0)}
        receipts, error = [], None
        for operation in operations:
            try:
                written = ci.rewire_add(root, corpus, operation)
                if written.get('error'):
                    error = str(written['error'])
                    break
                receipts.append(written.get('record') or written)
            except Exception as exc:
                error = str(exc)
                break
        try:
            observed, after_revision = spine_snapshot(corpus, root, network=_net(corpus, root))
            observed = compact(observed)
            status = ('COMMITTED' if observed == desired else 'PARTIAL' if observed != before
                      else 'UNPROVED' if receipts else None)
        except Exception as exc:
            observed, after_revision, status = None, None, 'UNPROVED'
            error = error or str(exc)
        if status is None:
            return {'ok': False, 'error': error or 'Spine change refused without an observed effect.'}
        complete = status == 'COMMITTED' and error is None
        publication = reader_publication('reader-spine', status, complete, len(receipts))
        publication.update(before_revision=revision, observed_revision=after_revision,
                           intended_order=[row['id'] for row in desired],
                           observed_order=[row['id'] for row in observed] if observed is not None else None)
        return {'ok': complete, 'applied': bool(receipts) or observed != before,
                'changed': observed != before, 'status': 'CURRENT' if complete else status,
                'error': error, 'spine_deltas': receipts, 'plan_publication': publication,
                'owned_changes': bundle(objects=[{'owner': 'reader-spine', 'id': corpus,
                    'before_revision': revision, 'after_revision': after_revision}], views=['structure']),
                'recovery': None if complete else 'Inspect the observed remaining spine and submit a new guarded operation; do not replay completed rewires.'}


def reconcile_section_refs(corpus: str, repo_root: Path | str | None = None) -> dict:
    """Recompute every planned node's desired section_ref (its FIRST section's anchor
    beat) and emit only the deltas. The drift-repair tool, the one-shot backfill for
    pre-B1 corpora, and the reconciler-of-record. Deterministic => idempotent: a
    second run emits nothing."""
    rr = Path(repo_root).resolve() if repo_root is not None else _repo_root()
    loaded = _load_plan(corpus, rr)
    if loaded is None:
        return {"ok": False, "error": f"no plan for corpus {corpus!r}"}
    _, plan = loaded
    from laplace.research import corpus_ingest as ci
    net = _net(corpus, rr)
    nodes = net.get("nodes", {})
    planned: list[str] = []
    seen: set[str] = set()
    for sec in (plan.get("sections") or []) + (plan.get("appendices") or []):
        for nid in sec.get("nodes_in_order") or sec.get("nodes") or []:
            if nid not in seen:
                seen.add(nid)
                planned.append(nid)
    emitted, unanchored = [], 0
    for nid in planned:
        desired = _desired_section_ref(plan, net, nid)
        if desired is None:
            # in a beatless first section (vs a legit self/no-anchor) -> count the gap
            if _anchor_beat(plan, net, _node_first_section(plan, nid) or "") is None:
                unanchored += 1
            continue
        cur = ((nodes.get(nid) or {}).get("projection") or {}).get("section_ref")
        if cur != desired:
            written = ci.rewire_add(rr, corpus, {"kind": "set-projection", "node": nid,
                                       "value": {"section_ref": desired}, "by": "storyboard-reconcile"})
            if written.get("error"):
                return {"ok": False, "error": written["error"], "emitted": len(emitted),
                        "deltas": emitted, "unanchored": unanchored}
            emitted.append({"node": nid, "section_ref": desired, "was": cur})
    return {"ok": True, "emitted": len(emitted), "deltas": emitted[:50],
            "unanchored": unanchored,
            "note": ("nodes whose first section names no spine beat can't be mirrored - "
                     "give each section a beat to close the gap") if unanchored else ""}


def reconcile_plan_mirrors(corpus: str, repo_root: Path | str | None = None) -> dict:
    """Repair required plan-beat/spine membership, then section_ref mirrors."""
    rr = Path(repo_root).resolve() if repo_root is not None else _repo_root()
    loaded = _load_plan(corpus, rr)
    if loaded is None:
        return {"ok": False, "error": f"no plan for corpus {corpus!r}"}
    _, plan = loaded
    from laplace.research import corpus_ingest as ci
    with _PLAN_LOCK:
        net = _net(corpus, rr)
        nodes = set((net.get("nodes") or {}).keys())
        tagged = {beat["id"] for beat in net.get("spine", [])}
        next_ord = max([beat.get("ord", 0) for beat in net.get("spine", [])], default=-1) + 1
        spine_deltas = []
        for section in (plan.get("sections") or []) + (plan.get("appendices") or []):
            for beat in section.get("beats") or []:
                if beat not in nodes:
                    return {"ok": False, "error": f"plan beat is not a live node: {beat}"}
                if beat not in tagged:
                    written = ci.rewire_add(rr, corpus, {"kind": "set-spine", "node": beat,
                        "ord": next_ord, "by": "storyboard-reconcile"})
                    if written.get("error"):
                        return {"ok": False, "error": written["error"], "spine_deltas": spine_deltas}
                    spine_deltas.append({"node": beat, "spine": "tagged", "ord": next_ord})
                    tagged.add(beat); next_ord += 1
    refs = reconcile_section_refs(corpus, rr)
    return {"ok": bool(refs.get("ok")), "spine_deltas": spine_deltas,
            "section_refs": refs, "error": refs.get("error")}


def _violations(val: dict) -> set[tuple[str, str]]:
    """Flatten a validation report into a comparable set of (kind, detail) pairs."""
    out: set[tuple[str, str]] = set()
    for key in ("missing_nodes", "retired_used", "missing_refs", "fig_defects"):
        for item in val.get(key) or []:
            detail = json.dumps(item, sort_keys=True) if isinstance(item, (list, dict)) else str(item)
            out.add((key, detail))
    return out


_PLAN_PROJECTIONS = {}  # Disposable reductions, never a second durable plan.


def reader_publication(owner, status, complete, ledger_append_count):
    """One disposition contract for reader-plan and narrative-spine publication."""
    if status not in {'COMMITTED', 'UNCHANGED', 'PARTIAL', 'COMPENSATED', 'UNPROVED'}:
        raise ValueError('Unsupported reader publication status')
    if complete and status not in {'COMMITTED', 'UNCHANGED'}:
        raise ValueError('Incomplete reader publication cannot be acknowledged')
    return {'owner': owner, 'status': status, 'complete': bool(complete),
            'ledger_append_count': ledger_append_count,
            'next_reads': [{'operation': 'structure', 'payload': {'view': 'full'}}]}


def plan_publication_contract():
    return {'field': 'plan_publication',
            'statuses': ['COMMITTED', 'UNCHANGED', 'PARTIAL', 'COMPENSATED', 'UNPROVED'],
            'completion': 'complete:true requires COMMITTED or proved UNCHANGED. COMPENSATED/UNPROVED are always incomplete. A committed plan with pending graph mirror remains COMMITTED complete:false.',
            'no_op': 'Proved bind no-op is UNCHANGED complete:true, changed:false, ledger_append_count:0. It appends no plan operation.',
            'receipt': 'Exact physical plan pins remain in owned_changes. Metadata publication is separate from source_effect; source bytes were not written by this plan owner.',
            'recovery': 'Do not repeat committed or unproved plan publication. Re-read exact plan/source before an explicit follow-up. Compensated tail removes only verified attempted bytes; unrelated concurrent appends defeat compensation.'}


class PlanPublicationFailure(ValueError):
    """Exact plan/ledger publication fate; source fate remains its own receipt."""
    def __init__(self, error, project, recovery):
        super().__init__(str(error))
        self.details = {'plan_publication': recovery,
            'next_reads': [{'operation': 'structure', 'payload': {'view': 'summary'}},
                           {'operation': 'source', 'payload': {}}],
            'recovery': 'Inspect source and reader plan; use guarded plan retitle/bind_source for unfinished heading follow-through. Do not repeat a committed source edit.'}


def plan_failure_details(error):
    """Bounded metadata publication facts for HTTP/native/saved-failure adapters."""
    for _ in range(8):
        if error is None:
            break
        details = getattr(error, 'details', None)
        if isinstance(details, dict) and isinstance(details.get('plan_publication'), dict):
            return {key: details[key] for key in ('plan_publication', 'next_reads', 'recovery') if key in details}
        error = error.__cause__ or error.__context__
    return {}


def _compensate_plan_publication(index, count, offset, operations, path, before, intended):
    """Undo only our byte-exact appended tail under the ledger's append lease.

    Full prefix verification is a failure-only cost. An unrelated append or
    unexpected plan bytes defeats compensation instead of being discarded.
    """
    from filelock import FileLock
    from laplace.writing import records
    expected = ''.join(json.dumps(op, ensure_ascii=False) + os.linesep for op in operations).encode('utf-8')
    with FileLock(str(index.path) + '.lock', timeout=15):
        observed = path.read_bytes() if path.is_file() else None
        suffix = b''
        if index.path.is_file():
            with index.path.open('rb') as stream:
                stream.seek(offset)
                suffix = stream.read()
        if not expected.startswith(suffix) or observed not in (before, intended):
            return {'status': 'UNPROVED', 'complete': False, 'reason': 'Plan bytes or appended tail include an unproved concurrent effect.',
                    'ledger_offset_before': offset, 'ledger_tail_bytes': len(suffix)}
        for meta in index.rows[:count]:
            records.raw_indexed_record(index, meta)
        if observed != before:
            import uuid
            pending = path.with_name(path.name + '.' + uuid.uuid4().hex + '.compensating')
            pending.write_bytes(before)
            pending.replace(path)
        # The exact original prefix and complete attempted suffix were proved
        # while holding the same append lock. No unrelated row is truncated.
        if index.path.is_file():
            with index.path.open('r+b') as stream:
                stream.truncate(offset)
        return {'status': 'COMPENSATED', 'complete': False,
                'ledger_offset_before': offset, 'removed_tail_bytes': len(suffix),
                'plan_sha256': 'sha256:' + hashlib.sha256(before).hexdigest()}


def _plan_row_metadata(row, offset, end, order, line_hash):
    return {"record": row.get("record"), "id": row.get("id"),
            "kind": row.get("kind"), "section": row.get("section"),
            "source_title": row.get("source_title"),
            "source_plan_title": row.get("source_plan_title"),
            "_offset": offset, "_end": end, "_order": order, "_hash": line_hash}


def _plan_projection(corpus, root):
    """Reduce an exact indexed tail, invalidating on base/ledger replacement.

    This is the existing base+operation semantics with an in-memory checkpoint,
    not trust in projection_plan.json. Cold reconstruction is explicit O(history);
    warm source edits open only appended operation rows. The metadata index owns
    offsets, suffix observation, replacement detection and exact-row validation.
    """
    from laplace.writing import records
    import copy
    base_path = _sidecar(corpus, ".base.json", root)
    ledger_path = _sidecar(corpus, ".friction.jsonl", root)
    if (base_path is None or not base_path.is_file()) and ledger_path and ledger_path.is_file() and ledger_path.stat().st_size:
        raise ValueError("Reader-plan historical base is missing; current materialized bytes cannot prove the replay origin.")
    if base_path and base_path.is_file():
        base = json.loads(base_path.read_text(encoding='utf-8'))
        if not isinstance(base, dict):
            raise ValueError("Reader-plan historical base must be an object.")
    else:
        base = _ensure_base(corpus, root)
    if base is None:
        raise ValueError("No canonical reader plan is available.")
    path = _sidecar(corpus, ".friction.jsonl", root)
    if path is None:
        raise ValueError("Reader-plan ledger path is unavailable.")
    idx = records.index(root, path.relative_to(root).as_posix(), _plan_row_metadata)
    if idx.path.exists() and idx.path.stat().st_size != idx.offset:
        raise ValueError('Reader-plan ledger has an incomplete trailing record; publication is refused.')
    if idx.malformed_rows:
        raise ValueError("Reader-plan ledger contains malformed rows; canonical replay is unproved.")
    base_digest = hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    key = (str(root), corpus)
    cached = _PLAN_PROJECTIONS.get(key)
    valid = (cached and cached['generation'] is idx._generation
             and cached['base_digest'] == base_digest and cached['count'] <= len(idx.rows))
    plan = copy.deepcopy(cached['plan'] if valid else base)
    start = cached['count'] if valid else 0
    titles = dict(cached['titles']) if valid else {}
    for meta in idx.rows[start:]:
        operation = records.raw_indexed_record(idx, meta)
        _apply_op(plan, operation)
        if operation.get('section') and operation.get('source_title') and operation.get('source_plan_title'):
            titles[(operation['section'], operation['source_title'])] = operation['source_plan_title']
    entry = {'generation': idx._generation, 'base_digest': base_digest,
             'count': len(idx.rows), 'plan': copy.deepcopy(plan), 'titles': titles}
    _PLAN_PROJECTIONS[key] = entry
    while len(_PLAN_PROJECTIONS) > 16:
        _PLAN_PROJECTIONS.pop(next(iter(_PLAN_PROJECTIONS)))
    return plan, titles, idx


def prior_source_titles(corpus, root):
    """Historical title spelling from the same verified plan reduction."""
    with _PLAN_LOCK:
        _plan, titles, _index = _plan_projection(corpus, Path(root).resolve())
        return dict(titles)


def plan_write(corpus: str, op: dict, repo_root: Path | str | None = None) -> dict:
    """Compatibility single-op door; all plan publication uses the same batch owner."""
    return plan_write_batch(corpus, [op], repo_root)


def plan_write_batch(corpus: str, operations: list[dict], repo_root=None, *, _source_binding=False) -> dict:
    """Validate/publish one ordered plan batch under the existing domain lease.

    Source-heading follow-through uses this once, not one historical fold for
    each title. Public plan writes keep their one-op semantics and coemit rules.
    A rejected or unproved projection is never overwritten using a fresh guard.
    """
    from filelock import FileLock
    from laplace.core.receipts import bundle
    if not operations:
        return {'ok': True, 'applied': True, 'changed': False, 'status': 'CURRENT'}
    for operation in operations:
        if operation.get('kind') == 'bind-source' and not _source_binding:
            return {'ok': False, 'error': 'Use structure_change bind_source with inspected source and plan guards.'}
        if operation.get('kind') not in _OP_KINDS:
            return {'ok': False, 'error': 'unknown op kind ' + repr(operation.get('kind')),
                    'allowed': sorted(_OP_KINDS)}
    root = Path(repo_root).resolve() if repo_root is not None else _repo_root()
    plan_path = registry.plan_path_for(corpus, root)
    if plan_path is None:
        return {'ok': False, 'error': 'No canonical reader plan is available.'}
    # The outer caller may hold selected-source/physical-source leases. This
    # domain lease is last; it never acquires a source lease in the reverse order.
    with FileLock(str(plan_path) + '.publication.lock', timeout=15), _PLAN_LOCK:
        current, _titles, index = _plan_projection(corpus, root)
        physical = plan_path.read_bytes()
        if json.loads(physical) != current:
            return {'ok': False, 'rejected': True, 'status': 'PROJECTION_DIVERGED',
                    'error': 'Reader-plan file differs from its recorded base and operations; inspect both before reconciliation.'}
        expected = {str(op.get('expected_plan_digest') or '').removeprefix('sha256:')
                    for op in operations if op.get('expected_plan_digest')}
        actual = hashlib.sha256(physical).hexdigest()
        if expected and expected != {actual}:
            return {'ok': False, 'rejected': True, 'error': 'projection plan changed during the guarded write'}
        stamped = [{**op, 'ts': time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'by': op.get('by', 'gerard')} for op in operations]
        reduced = reduce_plan(current, stamped)
        from laplace.manuscript.book_outline import validate_plan
        try:
            validate_plan(reduced)
        except ValueError as exc:
            return {'ok': False, 'rejected': True, 'error': str(exc)}
        validation = _validate_reduced(reduced, corpus, root)
        inherited = []
        if not validation.get('pass', True) and any(validation.get(key) for key in
                ('missing_nodes', 'retired_used', 'missing_refs', 'fig_defects')):
            previous = _validate_reduced(current, corpus, root)
            added = _violations(validation) - _violations(previous)
            if added:
                return {'ok': False, 'rejected': True, 'validation': validation,
                        'new_violations': sorted(added), 'note': 'op not banked - it would break the plan structurally'}
            inherited = sorted(_violations(validation))
        initial_count, initial_offset = len(index.rows), index.offset
        intended = (json.dumps(reduced, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
        try:
            for operation in stamped:
                _append_ledger(corpus, operation, root)
            owned_plan = _write_plan_json(corpus, reduced, root)
        except Exception as exc:
            _PLAN_PROJECTIONS.pop((str(root), corpus), None)
            try:
                recovery = _compensate_plan_publication(index, initial_count, initial_offset,
                    stamped, plan_path, physical, intended)
            except Exception as repair:
                recovery = {'status': 'UNPROVED', 'complete': False, 'reason': str(repair)}
            raise PlanPublicationFailure(exc, corpus, recovery) from exc
        # Coemit remains operation-aware; it is a derived mirror, not the plan.
        mirrors = []
        for operation in stamped:
            try:
                mirrors.append(_coemit(corpus, reduced, operation, root))
            except Exception as exc:
                mirrors.append({'mirror_lag': True, 'why': str(exc)})
        _plan_projection(corpus, root)  # Advance only the exact appended suffix.
    pending = next((value for value in mirrors if isinstance(value, dict) and value.get('mirror_lag')), None)
    return {'ok': not bool(pending), 'applied': True, 'changed': reduced != current,
            'status': 'MIRROR_PENDING' if pending else 'CURRENT',
            'error': pending.get('why') if pending else None,
            'validation': validation, 'rebuild_class': 'expensive' if any(
                rebuild_class_for(op) == 'expensive' for op in operations) else 'cheap',
            'inherited_defects': inherited, 'mirror': pending or mirrors[-1],
            'plan': reduced,
            'plan_publication': reader_publication('reader-plan', 'COMMITTED', not bool(pending), len(stamped)),
            'owned_changes': bundle(files=[owned_plan] if owned_plan else [], views=['structure'])}


def plan_undo(corpus: str) -> dict:
    """Drop the last ledger op and re-reduce - undo is truncate + replay."""
    with _PLAN_LOCK:
        lp = _sidecar(corpus, ".friction.jsonl")
        base = _ensure_base(corpus)
        if base is None or lp is None or not lp.is_file():
            return {"ok": False, "error": "nothing to undo"}
        ops = _read_ledger(corpus)
        if not ops:
            return {"ok": False, "error": "nothing to undo"}
        ops = ops[:-1]
        lp.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in ops),
                      encoding="utf-8")
        _write_plan_json(corpus, reduce_plan(base, ops))
    return {"ok": True, "undone": True, "remaining_ops": len(ops),
            "plan": enriched_plan(corpus)}


# ---------------------------------------------------------------------------
# A2 - the incremental rebuild. The % NODES markers are the JOIN KEY: a section
# is dirty iff its plan node-set differs from the set its compiled fragment
# actually discharges, so only changed sections re-dispatch. CHEAP edits recompile
# (re-\input order) with zero token spend; EXPENSIVE edits emit a dispatch manifest
# the LOCAL projection skill consumes - the server prepares briefs and gates, it
# never spends tokens itself.
# ---------------------------------------------------------------------------

_INPUT_RE = re.compile(r"^\s*\\input\{([^}]+)\}\s*$")
# the diff compares POOL ids — kind-prefixed OR bare (goal:x, def:y, RQ-CLM-043,
# ridge_lambda), the grammar of a conceptric node pool (schema.POOL_ID_RE). This is
# distinct from schema.NODE_ID_RE, the strict kind-prefixed IDENTITY guard used where a
# free-text reference must be proven a node (citation_direction, review_surface); a bare
# id is a real pool member here but not an identity match there. Figures ride \ref (not
# % NODES) and are tracked in figures[]; citations ride \cite; blind-builder markers
# occasionally trail prose tokens that must not read as node changes. The id grammar and
# the support-namespace filter live in the ONE schema module.
from laplace.pipeline.schema import clean_ids as _clean_ids


def _section_tex_nodes(target: str, sec_id: str) -> tuple[set[str], bool]:
    """The node ids a compiled fragment actually discharges, read from its
    ``% NODES`` markers (via the viewer's own parser, sidecar-preferred). Returns
    (clean_nodes, has_markers); a fragment with no markers can't be diffed, so it
    is treated as always-dirty by the caller."""
    rr = _repo_root()
    p = (rr / target / f"{_pathsafe.encode_sid_for_path(sec_id)}.tex")
    if not p.is_file():
        return set(), False
    from laplace.manuscript import projection_viewer as pv
    spans = pv.load_map(p)
    nodes: set[str] = set()
    for span in spans:
        nodes.update(span.get("nodes") or [])
    return _clean_ids(nodes), bool(spans)


def dirty_report(corpus: str) -> list[dict]:
    """Per section/appendix: the plan's desired node-set vs the fragment's realised
    set (real node ids only), and whether they differ. A missing/marker-less
    fragment is always dirty (fail safe toward rebuild)."""
    loaded = _load_plan(corpus)
    if loaded is None:
        return []
    _, plan = loaded
    target = ((plan.get("meta") or {}).get("target_dir") or "").rstrip("/")
    out = []
    for is_app, sec in ([(False, s) for s in plan.get("sections") or []]
                        + [(True, s) for s in plan.get("appendices") or []]):
        sid = sec.get("id")
        plan_nodes = _clean_ids(sec.get("nodes_in_order") or sec.get("nodes") or [])
        tex_nodes, has_markers = _section_tex_nodes(target, sid)
        dirty = (not has_markers) or (plan_nodes != tex_nodes)
        out.append({
            "id": sid, "appendix": is_app, "dirty": dirty, "has_markers": has_markers,
            "added": sorted(plan_nodes - tex_nodes),
            "removed": sorted(tex_nodes - plan_nodes),
            "n_plan": len(plan_nodes), "n_tex": len(tex_nodes),
        })
    return out


def _rewrite_inputs(main_path: Path, section_ids: list[str], appendix_ids: list[str]) -> bool:
    """Cheap recompile's mechanical half: rewrite the \\input order in main.tex to
    match the plan's section (then, after \\appendix, appendix) order, preserving
    every other line byte-for-byte. Returns True if the file changed."""
    from laplace.manuscript.manuscript_source import source_mutation
    with source_mutation([main_path]):
        return _rewrite_inputs_locked(main_path, section_ids, appendix_ids)


def _rewrite_inputs_locked(main_path: Path, section_ids: list[str], appendix_ids: list[str]) -> bool:
    # Caller holds the exact source target; compilation is an outer follow-through.
    if not main_path.is_file():
        return False
    lines = main_path.read_text(encoding="utf-8").splitlines()
    app_at = next((i for i, l in enumerate(lines)
                   if l.strip().startswith("\\appendix")), len(lines))

    def rewrite(lo: int, hi: int, order: list[str]) -> list[str]:
        # sids are RAW plan ids; on-disk \input targets are path-encoded stems
        # (the migration). Match and re-emit through the encoder so a colon sid
        # matches its sec_*.tex stem and is never re-banked raw.
        stems = [_pathsafe.encode_sid_for_path(sid) for sid in order]
        want = set(stems)
        moved = [i for i in range(lo, hi)
                 if _INPUT_RE.match(lines[i]) and _INPUT_RE.match(lines[i]).group(1) in want]
        if not moved:
            return lines[lo:hi]
        block = [f"\\input{{{stem}}}" for stem in stems]
        moved_set = set(moved)
        out, inserted = [], False
        for i in range(lo, hi):
            if i in moved_set:
                if not inserted:
                    out.extend(block)
                    inserted = True
            else:
                out.append(lines[i])
        return out

    new = rewrite(0, app_at, section_ids) + rewrite(app_at, len(lines), appendix_ids)
    if new == lines:
        return False
    from laplace.manuscript.manuscript_source import stage_source
    staged = stage_source(main_path, ("\n".join(new) + "\n").encode("utf-8"))
    try:
        staged.replace(main_path)
    finally:
        staged.unlink(missing_ok=True)
    return True


def _staged_prep(corpus: str, dirty: list[str]) -> tuple[Path | None, list[str], list[str], str]:
    """The staged rebuild's headless leg (pure, no tokens — the 2026-07-09
    rebuild): classify each dirty section by narrative freshness (the §7.2
    validator doubles as the staleness check — a plan change breaks coverage
    mechanically), and compile prose dispatches for the sections whose
    narrative specification still covers the plan. Returns
    (dispatch_dir, narrative_stale, dispatch_files, log)."""
    from laplace.pipeline import dispatch as _dispatch
    from laplace.pipeline import narrative as _narrative
    from laplace.pipeline import registry as _registry
    proj = _registry.resolve(corpus)
    if proj is None:
        return None, [], [], "unknown project"
    dp = proj.stage_path("dispatches")
    stale, ready = [], []
    for sid in dirty:
        r = _narrative.validate_narrative(corpus, sid)
        (ready if r.get("pass") else stale).append(sid)
    files: list[str] = []
    if ready:
        files = [p.relative_to(_repo_root()).as_posix()
                 for p in _dispatch.compile_section_dispatches(corpus, sections=ready)]
    return dp, stale, files, (f"{len(files)} dispatch(es) compiled, "
                              f"{len(stale)} narrative(s) stale")


def _try_compile(corpus: str, *, target: str | None = None) -> dict:
    """Best-effort compile of the reordered paper. Wire-only where LaTeX is absent
    (e.g. the remote): the result carries the toolchain's own error rather than
    raising, so the cheap path still reports plainly."""
    if target is None:
        loaded = _load_plan(corpus)
        if loaded is None:
            return {"ok": False, "error": "no plan"}
        target = ((loaded[1].get("meta") or {}).get("target_dir") or "").rstrip("/")
    from laplace.manuscript import projection_viewer as pv
    try:
        return pv.compile_tex(target + "/main.tex")
    except Exception as e:
        return {"ok": False, "error": f"compile unavailable: {e}"}


def _derived_target_refusal(corpus: str, target: Path, root: Path, *, plan=None) -> dict | None:
    """Legacy regeneration cannot bypass selected-source admission.

    Call while holding this project's selection lease. The source owner proves
    membership; a filename or a plan's output label is not mutation authority.
    """
    from laplace.manuscript.manuscript_source import SourceAccessError, source_access, require_unregistered_source

    loaded = _load_plan(corpus) if plan is None else None
    plan = plan if plan is not None else loaded[1] if loaded else {}
    declared = (plan.get("meta") or {}).get("target_dir")
    if (
        not isinstance(declared, str)
        or not declared.strip()
        or (root / declared / "main.tex").resolve() != target.resolve()
    ):
        return {
            "ok": False,
            "reason": "derived-target-unproved",
            "error": "The actual write target is not the projection plan's declared derived output. No source was changed; use the guarded manuscript or references workflow.",
            "recovery": {"operation": "document", "payload": {}},
        }
    if not target.resolve().is_relative_to(root.resolve()):
        return {
            "ok": False,
            "reason": "derived-target-outside-workspace",
            "error": "The derived output target is outside this workspace. No source was changed.",
        }
    try:
        source_access(corpus, target, root)
    except SourceAccessError as exc:
        if exc.response.get("reason") != "source-outside-selection":

            if registry.resolve(corpus, repo_root=root) is None:
                try:
                    require_unregistered_source(target, root)
                except SourceAccessError:
                    pass
                else:
                    return (
                        None  # Declared derived output in a genuine unregistered legacy namespace.
                    )
            return {
                "ok": False,
                "reason": "derived-target-unproved",
                "error": "Current source membership could not be established. No source was changed; inspect the document before preparing derived output.",
                "recovery": {"operation": "document", "payload": {}},
            }
        try:
            require_unregistered_source(target, root, exclude_project=corpus)
        except SourceAccessError:
            return {
                "ok": False,
                "reason": "canonical-source-rebuild-refused",
                "error": "The target belongs to another registered manuscript. No source was changed; existing plan edits remain.",
                "recovery": {"operation": "document", "payload": {}},
            }
        return None
    return {
        "ok": False,
        "reason": "canonical-source-rebuild-refused",
        "error": "This target is current manuscript source or a consumed dependency. Legacy regeneration cannot replace it. Existing plan edits are retained; review and apply source or bibliography changes through the guarded manuscript and references workflow.",
        "recovery": {"operation": "document", "payload": {}},
    }


def rebuild(corpus: str, mode: str = "expensive", only: list[str] | None = None) -> dict:
    """The rebuild orchestrator. CHEAP: reorder \\input + recompile, no tokens.
    EXPENSIVE: gate on validation, build the dirty sections' briefs, and return a
    dispatch manifest for the local LLM leg. Never spawns an LLM."""
    loaded = _load_plan(corpus)
    if loaded is None:
        return {"ok": False, "error": f"no plan for corpus {corpus!r}"}
    plan_path, plan = loaded
    rr = _repo_root()
    target = ((plan.get("meta") or {}).get("target_dir") or "").rstrip("/")
    report = dirty_report(corpus)
    dirty = [d["id"] for d in report if d["dirty"]]
    if only:
        dirty = [s for s in dirty if s in only]

    if mode == "cheap":
        main_path = rr / target / "main.tex"
        from laplace.manuscript.manuscript_source import SourceLeaseError, source_mutation, selection_mutation
        try:
            with selection_mutation(corpus, rr), source_mutation([main_path]):
                refusal = _derived_target_refusal(corpus, main_path, rr, plan=plan)
                if refusal:
                    return {**refusal, 'mode':'cheap'}
                # Existing plan writers are metadata leaves. Source comes first;
                # the separate finite plan wait does not extend the source-set
                # acquisition deadline into a claimed whole-operation budget.
                if not _PLAN_LOCK.acquire(timeout=15):
                    return {"ok":False, "reason":"plan-lock-unavailable", "error":"Another plan mutation is still active; inspect and retry."}
                try:
                    current = _load_plan(corpus)
                    if current is None or current[0] != plan_path or current[1] != plan:
                        return {"ok":False, "reason":"plan-revision-conflict", "error":"Plan changed while waiting for source; inspect the current storyboard before retrying."}
                    sec_ids = [s.get("id") for s in current[1].get("sections") or []]
                    app_ids = [s.get("id") for s in current[1].get("appendices") or []]
                    reordered = _rewrite_inputs(main_path, sec_ids, app_ids)
                finally:
                    _PLAN_LOCK.release()
        except SourceLeaseError as exc:
            return {"ok":False, "mode":"cheap", "reason":"source-lease-unavailable", "error":str(exc),
                    "recovery":"Inspect storyboard and source, then explicitly retry the existing cheap rebuild."}
        return {"ok": True, "mode": "cheap", "reordered": reordered,
                "compile": _try_compile(corpus, target=target), "dirty": dirty, "report": report}

    # expensive: gate, then prepare briefs + manifest (no token spend on the server)
    gate = _validate_reduced(plan, corpus)
    # fail-safe: a gate that reports defects but omits an explicit `pass` no
    # longer slips through (was `gate.get("pass", True) OR not defects`, so a
    # missing key passed regardless of defects). Now: `pass` must not be
    # explicitly False AND no defect category may be populated. Validator-
    # unavailable still fails OPEN by design (_validate_reduced sets pass=True on
    # error, no defect keys). (2026-07-09 harden.)
    gate_ok = (gate.get("pass") is not False) and not (
        gate.get("missing_nodes") or gate.get("retired_used")
        or gate.get("missing_refs") or gate.get("fig_defects"))
    if not gate_ok:
        return {"ok": False, "mode": "expensive", "gate": gate, "dirty_sections": dirty,
                "note": "validation failed - fix the flagged nodes before rebuilding"}
    dispatch_dir, narrative_stale, dispatch_files, log = _staged_prep(corpus, dirty)
    est_chars = 0
    for rel in dispatch_files:
        p = rr / rel
        if p.is_file():
            est_chars += len(p.read_text(encoding="utf-8"))
    # rough: chars/4 = input tokens, x3 covers realiser generation + weld + detector read
    est_tokens = int(est_chars / 4 * 3)
    manifest = {"corpus": corpus, "sections": dirty,
                "narrative_stale": narrative_stale,
                "dispatches": dispatch_files,
                "estimated_tokens": est_tokens, "gate": {"validation_passed": True},
                # freshness key: a consumer checks the plan hasn't moved since this
                # manifest was cut - one producer (this function), self-invalidating
                "plan_mtime_ns": plan_path.stat().st_mtime_ns,
                "target_dir": target,
                "cut_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    manifest_path = None
    if dispatch_dir is not None:
        dispatch_dir.mkdir(parents=True, exist_ok=True)
        mp = dispatch_dir / "dispatch_manifest.json"
        mp.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                      encoding="utf-8")
        manifest_path = mp.relative_to(rr).as_posix()
    invocation = (f'/project-staged --manifest "{manifest_path}"'
                  if manifest_path else None)
    return {
        "ok": True, "mode": "expensive", "dirty_sections": dirty, "report": report,
        "staged_log": log,
        "manifest": manifest, "manifest_path": manifest_path, "invocation": invocation,
        "note": ("headless leg done (narrative freshness checked + prose dispatches "
                 "compiled). The LLM leg - narrative planners for stale sections, "
                 "prose realisers, detectors, weld - runs via the local staged "
                 "workflow from this manifest; the server never spends tokens."),
    }


# ---------------------------------------------------------------------------
# C - the hinge: the plan's node pool DERIVED from node-side facts. A section's
# nodes_in_order becomes a projection of (authored beats[]) + (node->beat section_ref
# graph) + grade order, rather than hand-pinned. Sections/titles/jobs/beats stay
# authored; only the tedious supporting pool is generated. Non-destructive preview +
# a reversible apply through the plan ledger (undo works). This is the moment the
# plan stops being a parallel store and becomes a view of the one substrate.
# ---------------------------------------------------------------------------

def _derived_pool(plan: dict, net: dict) -> dict:
    """Per body section: the node pool derived from the graph. For each authored beat
    (spine-ordered), emit the beat then the nodes whose section_ref points at it
    (grade order). Deterministic; figures/citations excluded (they ride figures[]/\\cite)."""
    nodes = net.get("nodes", {})
    ord_of = {b["id"]: b.get("ord", 0) for b in net.get("spine", [])}
    children: dict[str, list[str]] = {}
    for nid, nd in nodes.items():
        sr = (nd.get("projection") or {}).get("section_ref")
        if sr:
            children.setdefault(sr, []).append(nid)

    def grade_of(nid):
        g = (nodes.get(nid) or {}).get("grade")
        return g if isinstance(g, int) else 99

    def keep(nid):
        return ":" in nid and not nid.startswith(("fig:", "ref:"))

    out = {}
    for sec in plan.get("sections") or []:
        beats = sorted([b for b in (sec.get("beats") or []) if b in ord_of], key=lambda b: ord_of[b])
        if not beats:
            out[sec["id"]] = {"beatless": True}
            continue
        derived, seen = [], set()
        for b in beats:
            if b not in seen and keep(b):
                derived.append(b); seen.add(b)
            for c in sorted(children.get(b, []), key=lambda n: (grade_of(n), n)):
                if c not in seen and keep(c):
                    derived.append(c); seen.add(c)
        out[sec["id"]] = {"beatless": False, "derived": derived}
    return out


def derive_plan(corpus: str) -> dict:
    """Non-destructive preview: what each section's pool WOULD be if derived from the
    node graph, diffed against the current authored pool."""
    loaded = _load_plan(corpus)
    if loaded is None:
        return {"ok": False, "error": f"no plan for corpus {corpus!r}"}
    _, plan = loaded
    pool = _derived_pool(plan, _net(corpus))
    sections = []
    for sec in plan.get("sections") or []:
        cur = [n for n in (sec.get("nodes_in_order") or []) if ":" in n and not n.startswith(("fig:", "ref:"))]
        p = pool.get(sec["id"], {})
        if p.get("beatless"):
            sections.append({"id": sec["id"], "beatless": True, "current": cur})
            continue
        der = p.get("derived", [])
        sections.append({"id": sec["id"], "beatless": False, "current": cur, "derived": der,
                         "added": [n for n in der if n not in cur],
                         "removed": [n for n in cur if n not in der]})
    changed = [s for s in sections if not s.get("beatless") and (s.get("added") or s.get("removed"))]
    return {"ok": True, "sections": sections, "n_changed": len(changed),
            "n_beatless": sum(1 for s in sections if s.get("beatless"))}


def derive_apply(corpus: str) -> dict:
    """Apply the derivation: write each body section's derived pool via a set-nodes plan
    op (validated + ledgered + undoable). Beatless sections keep their authored pool."""
    d = derive_plan(corpus)
    if not d.get("ok"):
        return d
    applied, rejected = [], []
    for s in d["sections"]:
        if s.get("beatless") or not s.get("derived"):
            continue
        res = plan_write(corpus, {"kind": "set-nodes", "section": s["id"], "order": s["derived"]})
        (applied if res.get("ok") else rejected).append(s["id"])
    return {"ok": True, "applied": applied, "rejected": rejected,
            "beatless_kept": d["n_beatless"], "plan": enriched_plan(corpus)}


# ---------------------------------------------------------------------------
# the capability endpoints - the pipeline operators (restructure P5, propagate
# P3, dispatch P4) surfaced as board routes. The operators stay the ONE
# implementation (laplace.pipeline.*); these wrappers only shape the lifecycle:
# preview NEVER mutates, apply runs inside ledger.transaction, and the response
# is board-sized (sequences and verdicts, never a plan/bundle dump).
# ---------------------------------------------------------------------------

def _rel(p: Path) -> str:
    """Repo-relative posix path when inside the repo; absolute otherwise (the
    endpoint tests run the surface over isolated trees)."""
    try:
        return p.relative_to(_repo_root()).as_posix()
    except ValueError:
        return p.as_posix()


def _restructure_summary(report: dict) -> dict:
    """The board-sized view of a restructure.execute() report: the new section
    sequence with node counts, the validation verdict, the dirty classes, the
    spine payload COUNT and per-section prose-bundle sizes - with stray/refusal
    errors passed through verbatim. The full new_plan/prose_bundles stay
    server-side; apply materialises them, preview only decides."""
    out = {k: report.get(k) for k in ("ok", "applied", "project")
           if k in report}
    if report.get("error"):
        out["error"] = report["error"]          # refusals verbatim, never summarised
    new_plan = report.get("new_plan")
    if new_plan:
        def seq(key: str) -> list[dict]:
            return [{"id": s.get("id"), "title": s.get("title"),
                     "n_nodes": len(s.get("nodes_in_order") or s.get("nodes") or []),
                     "n_beats": len(s.get("beats") or []),
                     "n_refs": len(s.get("refs") or []),
                     "n_figures": len(s.get("figures") or [])}
                    for s in new_plan.get(key) or []]
        out["sections"], out["appendices"] = seq("sections"), seq("appendices")
    if "validation" in report:
        out["validation"] = report["validation"]
    if "dirty" in report:
        out["dirty"] = report["dirty"]
    if "spine_payloads" in report:
        out["n_spine_payloads"] = len(report["spine_payloads"] or [])
    if "prose_bundles" in report:
        out["prose_bundles"] = {sid: len(spans) for sid, spans
                                in (report["prose_bundles"] or {}).items()}
    for k in ("parked", "inert_overrides", "freeze_dir", "reconcile",
              "reconcile_after", "spine_applied", "rolled_back"):
        if k in report:
            out[k] = report[k]
    return out


class _ApplyFailed(Exception):
    """Carries a not-ok report OUT of the transaction body, so the L1 suffix
    written before the failure truncates back (both ledgers or neither)."""

    def __init__(self, report: dict):
        self.report = report
        super().__init__(report.get("error") or "apply failed")


def current_arc(corpus: str) -> dict[str, Any] | None:
    """The IDENTITY target_arc for a corpus — the current section/appendix arc as a
    restructure ``target_arc`` (each new section seeded from its own old id). It is
    the editable STARTING POINT the board's restructure door pre-fills: dry-running
    it reproduces the plan (0 moved), and the author edits ids/titles/seed_from to
    propose an N→M reshape. Pure read; None when the corpus has no plan."""
    loaded = _load_plan(corpus)
    if loaded is None:
        return None
    _, plan = loaded

    def _seed(secs):
        return [{"id": s.get("id"), "title": s.get("title") or s.get("id") or "",
                 "seed_from": [s.get("id")]}
                for s in secs if s.get("id")]

    return {"corpus": corpus,
            "sections": _seed(plan.get("sections") or []),
            "appendices": _seed(plan.get("appendices") or [])}


def restructure_run(corpus: str, arc: dict, apply: bool = False) -> dict:
    """The restructure operator behind POST /storyboard/restructure.

    Dry-run (the default) is the operator's own pure preview, summarised.
    Apply wires the full lifecycle in the canon order: the arc's spine payloads
    into L1 FIRST via corpus_ingest.rewire_add (they are EMITTED by the
    operator, never self-applied), then execute(apply) - freeze, plan+base
    regeneration, its own reconcile - then a SECOND reconcile_section_refs
    (idempotent; catches anchors the fresh spine order moved). The whole apply
    sits inside ONE ledger.transaction over the L1 ledger, so any failure
    truncates the endpoint's own suffix back and the ledgers stay byte-identical."""
    from laplace.pipeline import restructure as _restructure
    if not apply:
        return _restructure_summary(_restructure.execute(corpus, arc, dry_run=True))

    from laplace.research import corpus_ingest as ci
    from laplace.pipeline import ledger as _ledger
    from laplace.pipeline import registry as _registry
    proj = _registry.resolve(corpus)
    if proj is None or not proj.plan_path:
        return {"ok": False, "error": f"unknown or plan-less project {corpus!r}"}
    rr = _repo_root()
    l1 = proj.path(proj.ledger, rr)
    with _PLAN_LOCK:
        try:
            with _ledger.transaction(l1, by="storyboard-restructure",
                                     note=f"restructure {corpus} via /storyboard/restructure"):
                applied_spine = 0
                for payload in _restructure.spine_payloads(arc):
                    res = ci.rewire_add(rr, corpus, {**payload, "by": "storyboard-restructure"})
                    if not res.get("ok"):
                        raise _ApplyFailed({"ok": False, "error":
                                            f"spine payload refused: {res.get('error')}"})
                    applied_spine += 1
                report = _restructure.execute(corpus, arc, dry_run=False)
                if not report.get("ok"):
                    raise _ApplyFailed(report)
                report["spine_applied"] = applied_spine
                report["reconcile_after"] = reconcile_section_refs(corpus)
        except _ApplyFailed as e:
            return _restructure_summary({**e.report, "rolled_back": True})
        except Exception as e:  # noqa: BLE001 - any failure must report the rollback
            return {"ok": False, "rolled_back": True,
                    "error": f"apply failed - L1 suffix rolled back: {e}"}
    return _restructure_summary(report)


def dispatch_report(corpus: str, dials_profile: str | None = None) -> dict:
    """The dispatch leg behind POST /storyboard/dispatch: ensure the manifest is
    fresh (rebuild expensive when the plan moved past it), ensure briefs exist
    and prose dispatches are compiled for the worklist's sections, and return
    the orchestrator's surface - manifest + invocation + every typed work item
    with its dispatch availability. ``dials_profile`` threads the per-run dials
    override into the compiled prose dispatches (BLOCKER-A).

    Prose items compile from their section's brief (the materialised
    ``<sid>_dispatch.md``); derive/figure/simulate/mint items are listed with
    their worker ROUTES plus the exact compile_dispatch call (worker = the
    item's KIND, target = the node id) - the orchestrator compiles those
    node-local frames on demand, this endpoint never burns them eagerly."""
    loaded = _load_plan(corpus)
    if loaded is None:
        return {"ok": False, "error": f"no projection plan for corpus {corpus!r}"}
    plan_path, _ = loaded
    dispatches_dir = plan_path.parent / "dispatches"
    manifest_path = dispatches_dir / "dispatch_manifest.json"

    manifest, fresh = None, False
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            fresh = manifest.get("plan_mtime_ns") == plan_path.stat().st_mtime_ns
        except (OSError, json.JSONDecodeError):
            manifest = None
    rebuilt = False
    if not fresh:
        rb = rebuild(corpus, "expensive")
        if not rb.get("ok"):
            return {**rb, "corpus": corpus}     # the gate report, verbatim
        manifest, rebuilt = rb.get("manifest"), True

    from laplace.pipeline import dispatch as _dispatch
    from laplace.pipeline import propagate as _propagate
    try:
        prop = _propagate.propagate(corpus)     # pure read - the typed worklist
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    worklist = prop.get("worklist") or []

    # the prose leg: dispatches compile FROM a section's narrative packet (the
    # staged rebuild); a section whose narrative is stale simply yields no
    # dispatch here and surfaces as a 'narrative' item for the planner leg
    prose_secs = sorted({it["section"] for it in worklist
                         if it.get("kind") == "prose" and it.get("section")})
    if prose_secs:
        _dispatch.compile_section_dispatches(corpus, sections=prose_secs,
                                             dials_profile=dials_profile)

    items = []
    for it in worklist:
        entry = dict(it)
        if it.get("kind") == "prose" and it.get("section"):
            dp = dispatches_dir / f"{_pathsafe.encode_sid_for_path(it['section'])}_dispatch.md"
            entry["dispatch_available"] = dp.is_file()
            entry["dispatch"] = _rel(dp) if dp.is_file() else None
        else:
            entry["dispatch_available"] = False
            entry["dispatch"] = None
            entry["compile_with"] = {"target": it.get("target"), "goal": it.get("goal"),
                                     "worker": it.get("kind"), "project": corpus}
        items.append(entry)

    mp_rel = _rel(manifest_path) if manifest_path.is_file() else None
    return {
        "ok": True, "corpus": corpus, "rebuilt": rebuilt,
        "manifest": manifest, "manifest_path": mp_rel,
        "invocation": (f'/project-staged --manifest "{mp_rel}"' if mp_rel else None),
        "minimum_dispatch": prop.get("minimum_dispatch") or [],
        "comments_routed": prop.get("comments_routed", 0),
        "n_items": len(items), "items": items,
    }


def refs_payload(corpus: str) -> dict | None:
    """The global bib key list for the per-section refs picker, plus where each
    key is already used across the plan. None when the corpus has no plan."""
    loaded = _load_plan(corpus)
    if loaded is None:
        return None
    _, plan = loaded
    from laplace.pipeline import registry as _registry
    from laplace.pipeline.schema import bib_keys
    proj = _registry.resolve(corpus)
    bib_path = proj.path(proj.bib, _repo_root()) if proj else None
    keys: list[str] = []
    if bib_path is not None and bib_path.is_file():
        try:
            keys = sorted(bib_keys(bib_path.read_text(encoding="utf-8")))
        except OSError:
            keys = []
    used: dict[str, list[str]] = {}
    for sec in (plan.get("sections") or []) + (plan.get("appendices") or []):
        for r in sec.get("refs") or []:
            used.setdefault(r, []).append(sec.get("id"))
    return {"corpus": corpus, "keys": keys, "n": len(keys), "used": used}


# ---------------------------------------------------------------------------
# THE COVERAGE INVERSE (spine §3 link 4) — prose WITHOUT stock, made a COUNT on
# the board. Two failure modes, distinct and both mechanical:
#   prose_by_plan — a narrative BEAT (a paragraph plan, stage D) with an EMPTY
#                   ``input_nodes`` set: unsupported prose-BY-PLAN (the plan itself
#                   asks for prose no node backs). Source: narrative/<sid>.json.
#   prose_by_fact — a REALISED paragraph whose ``prose_provenance`` traces to
#                   nothing (``nodes_realised`` empty): unsupported prose-BY-FACT
#                   (the desk-rejection mode, "JUDGE SILENCE IS NOT MANUSCRIPT
#                   QUALITY"). Source: prose_provenance/<sid>.json.
# Both read the SAME stores the staged pipeline already writes — NO new pipeline;
# the surface only renders the mismatch. Each offender carries (section,
# paragraph) so the board doors one click deep into /artefact. THE CLAUSE (spine
# §6, suite-side): these counts NEVER under-report the stores' own truth.
# ---------------------------------------------------------------------------

def coverage_inverse(corpus: str) -> dict[str, Any]:
    """The two prose-without-stock counts + their offenders (spine §4 link 4).
    Pure reads over the narrative + prose_provenance stores; declared empty when a
    store is absent (a never-narrated / never-realised section contributes 0, never
    an error). The board renders the counts and each offender's door."""
    loaded = _load_plan(corpus)
    if loaded is None:
        return {"ok": False, "error": f"no projection plan for corpus {corpus!r}"}
    _, plan = loaded
    from laplace.pipeline import narrative as _narrative
    from laplace.pipeline import document_model as _dm
    from laplace.pipeline import schema as _schema
    by_plan: list[dict] = []
    by_fact: list[dict] = []
    n_narr = 0
    n_prov = 0
    for sec in _schema.plan_sections(plan):          # sections + appendices, doc order
        sid = sec.get("id")
        if not sid:
            continue
        nspec = _narrative.load_section(corpus, sid)
        for i, para in enumerate((nspec or {}).get("paragraphs") or []):
            n_narr += 1
            if not (para.get("input_nodes") or []):
                by_plan.append({"section": sid,
                                "paragraph": para.get("paragraph_id") or f"{sid}-p{i + 1}",
                                "function": para.get("function") or ""})
        for rec in (_dm.load_provenance(corpus, sid) or []):
            n_prov += 1
            if not (rec.get("nodes_realised") or []):
                by_fact.append({"section": sid,
                                "paragraph": (rec.get("spec_id")
                                              or rec.get("paragraph_id") or sid)})
    return {
        "ok": True, "corpus": corpus,
        "prose_by_plan": {
            "count": len(by_plan), "offenders": by_plan,
            "what": "narrative beats with an empty input-node set — "
                    "unsupported prose-by-plan"},
        "prose_by_fact": {
            "count": len(by_fact), "offenders": by_fact,
            "what": "realised paragraphs whose provenance traces to nothing — "
                    "unsupported prose-by-fact"},
        "n_narrative_paragraphs": n_narr,
        "n_provenance_records": n_prov,
    }


# ---------------------------------------------------------------------------
# W5.1 — THE RUN PANEL read model.  ``GET /storyboard/run?corpus=`` derives a
# corpus's current/most-recent round's LIVE state ENTIRELY from the run's own
# artifacts on disk — no orchestrator mediation, no subprocess, no daemon, PURE
# READS (the author's must-have verbatim: "WATCHING a run must not stay
# orchestrator-mediated — the panel is pure file reads over the run's own
# artifacts"). Polling this DURING a live run *is* watching it: each artifact a
# round writes advances ``last_mtime``; the derived ``phase`` climbs the harnessed
# ladder as the evidence lands.
#
# HONESTY (repair F9, the W6.2-landed world): round evidence genuinely absent from
# the tree reports ``not-yet-travelled`` — never a spinner, never a fabricated
# phase; a project the release machine never touched reports ``never-run``. The
# panel never implies a live remote watch it cannot deliver: it reads only what the
# normal converge organ banked locally (and W6.2 travels remote rounds AS banked
# artifacts, so a travelled remote round renders like any local one).
#
# BOUNDED (the golden law): ≤16KB, ENFORCED at the tail (gates compacted, then
# panels shed) with a LOUD ``truncated`` flag — never a silent drop.
# ---------------------------------------------------------------------------

_RUN_MAX_BYTES = 16 * 1024

#: the harnessed ladder — the phase each artifact-kind proves the round reached.
#: Detect (mech/detect_pre/adjudicate/fix_brief) -> Fix (incumbent) -> Verify
#: (detect_post) -> Lock (lock_r) -> Finalize (finalize.json / minted pdf). Terminal
#: wins: the highest rung whose evidence exists is the phase.
_PHASE_ORDER = ("detecting", "fixing", "verified", "locked", "finalized")


def _release_state(md: Path) -> str:
    """The release state the way the registry inventory reads it: ``NEVER_RUN`` when
    NO state sidecar FILE exists (the machine never touched this project), else
    ``release.current_state``. A corrupt sidecar reads as ``STAGED`` (never crashes)."""
    state_file = md / "release" / "state.json"
    if not state_file.is_file():
        return "NEVER_RUN"
    try:
        from laplace.pipeline import release
        return release.current_state(md)
    except Exception:
        return "STAGED"


def _round_artifacts(md: Path, n: int, layout: str, root: Path) -> list[dict]:
    """Every evidence file/dir the CURRENT round left on disk, repo-relative, with its
    mtime — the round's own artifacts (the watch surface). Top-level only: the lock
    tier's crop images and the incumbent's section files are NOT walked (bound payload,
    the round record is the evidence, not its pixels)."""
    h = md / "rounds" / "harnessed"
    rd = md / "rounds"
    cands: list[tuple[str, Path]] = []
    if layout == "harnessed":
        cands += [
            ("mech", h / f"mech_r{n}.json"),
            ("detect_pre", h / f"detect_pre_r{n}.json"),
            ("fix_brief", h / f"fix_brief_r{n}.md"),
            ("adjudicate", rd / f"adjudicate_r{n}"),
            ("incumbent", rd / f"incumbent_r{n}"),
            ("detect_post", h / f"detect_post_r{n}.json"),
            ("lock", rd / f"lock_r{n}.json"),
            ("lock_tier", rd / f"lock_r{n}"),
        ]
        cands += [("economics_round", f) for f in sorted(h.glob(f"economics_r{n}_*.json"))]
    elif layout == "judge_rounds":
        from laplace.pipeline.convergence_ledger import _round_int
        for jr in (md / "judge_rounds", md.parent / "judge_rounds"):
            if jr.is_dir():
                cands += [("judge_round", f) for f in sorted(jr.glob("*round*.json"))
                          if _round_int(f.name) == n]
                break
    # run-level terminal evidence (not per-round, but the run's final state)
    cands += [
        ("economics", rd / "economics.json"),
        ("finalize", md / "release" / "finalize.json"),
    ]
    for pdf in sorted(md.glob("*.pdf")):
        if registry.MINTED_PDF_RE.match(pdf.name):
            cands.append(("minted_pdf", pdf))
    out: list[dict] = []
    for kind, p in cands:
        if p.exists():
            out.append({"kind": kind, "path": observe.relative(p, root),
                        "mtime": observe.iso_utc(observe.mtime(p))})
    return out


def _derive_phase(kinds: set[str], layout: str) -> str:
    """The current round's phase from WHICH artifacts exist — terminal wins. A round
    with only ``mech`` (detect_post absent) reads the plain in-flight ``detecting``;
    a round carrying ``finalize``/a minted pdf reads its final ``finalized``."""
    if "finalize" in kinds or "minted_pdf" in kinds:
        return "finalized"
    if "lock" in kinds:
        return "locked"
    if "detect_post" in kinds:
        return "verified"
    if "incumbent" in kinds:
        return "fixing"
    if kinds & {"mech", "detect_pre", "fix_brief", "adjudicate"}:
        return "detecting"
    return "recorded"          # judge_rounds / a bare round record: no ladder to climb


def _compact_gates(gates: dict) -> dict:
    """The round's gate transitions in a bounded form: per dim ``{value, changed}``
    (the ``from`` provenance is dropped — the panel wants the live state, not the
    diff the version rail already carries)."""
    out: dict[str, dict] = {}
    for grp in ("hard", "soft", "panels"):
        g = gates.get(grp) or {}
        out[grp] = {k: {"value": t.get("value"), "changed": bool(t.get("changed"))}
                    for k, t in g.items()}
    return out


def _enforce_run_budget(out: dict) -> None:
    """The byte half of the golden law, ENFORCED not asserted: shed the panel gate
    dims (the widest, least-critical field) until ≤16KB, LOUDLY (``truncated`` +
    ``gates_omitted``). ``hard``/``soft`` gate dims and every other field stay."""
    def _size(o: dict) -> int:
        return len(json.dumps(o, ensure_ascii=False).encode("utf-8"))
    panels = out.get("gates", {}).get("panels")
    if isinstance(panels, dict):
        for lab in sorted(panels, key=lambda k: str(k), reverse=True):
            if _size(out) <= _RUN_MAX_BYTES:
                break
            del panels[lab]
            out["truncated"] = True
            out["gates_omitted"] += 1


def run_panel(md: Path, root: Path) -> dict:
    """The run panel read model over a manuscript dir: the current/most-recent round's
    live state derived ENTIRELY from the run's own artifacts. Pure reads — the core the
    ``?corpus=`` endpoint wraps and the tests drive. Declared on absence (never-run vs
    not-yet-travelled), bounded to the golden law."""
    from laplace.pipeline import convergence_ledger as cl

    release_state = _release_state(md) if md.is_dir() else "NEVER_RUN"
    led = cl.assemble_ledger(str(md), root)
    layout = led.get("layout") or ""
    all_rounds = led.get("rounds") or []
    real = [r for r in all_rounds if not r.get("econ_only")]

    base = {
        "dir": observe.relative(md, root),
        "release_state": release_state,
        "layout": layout,
        "rounds_so_far": len(real),
        "budget": {"max_bytes": _RUN_MAX_BYTES},
        "truncated": False,
        "gates_omitted": 0,
        "generated_ts": observe.iso_utc(time.time()),
    }

    if not real:
        # F9: round evidence genuinely absent. never-run ONLY when the release machine
        # never touched it AND no rounds tree exists; otherwise a run posture exists but
        # its round records have not travelled here.
        never_touched = (release_state == "NEVER_RUN") and not (md / "rounds").is_dir()
        base.update({
            "phase": "never-run" if never_touched else "not-yet-travelled",
            "in_flight": False,
            "never_run": never_touched,
            "current_round": None,
            "open_findings": None,
            "gates": {"hard": {}, "soft": {}, "panels": {}},
            "artifacts": [],
            "last_mtime": None,
        })
        return base

    rec = max(real, key=lambda r: r.get("round", -1))
    n = rec.get("round")
    artifacts = _round_artifacts(md, n, layout, root)
    kinds = {a["kind"] for a in artifacts}
    phase = _derive_phase(kinds, layout)
    last_mtime = max((a["mtime"] for a in artifacts if a["mtime"]), default=None)

    base.update({
        "phase": phase,
        "in_flight": phase in ("detecting", "fixing", "verified", "locked"),
        "never_run": False,
        "current_round": n,
        "open_findings": rec.get("open_findings"),
        "gates": _compact_gates(rec.get("gates") or {}),
        "artifacts": artifacts,
        "last_mtime": last_mtime,
    })
    _enforce_run_budget(base)
    return base


def _verdict_position(corpus: str, root: Path) -> dict:
    """The one truth every surface reads — :func:`project_state.project_verdict`'s
    ``position`` + ``position_evidence`` (the SAME composition the dashboard cards and
    the cockpit render). Joined server-side so the run tray consumes it instead of
    inventing a parallel state word: a panel can never say 'finalized' beside
    'NEVER_RUN' when the single authoritative position ('pre-release …' / the release
    machine's own state) is the only state pill it renders. Guarded — an unreadable
    truth layer degrades to an empty position (declared absence, never a crash)."""
    try:
        from laplace.pipeline import project_state
        v = project_state.project_verdict(root, corpus)
    except Exception:  # noqa: BLE001 — the truth layer never blocks the run read
        return {"position": None, "position_evidence": []}
    if not v.get("present"):
        return {"position": None, "position_evidence": []}
    return {"position": v.get("position"),
            "position_evidence": v.get("position_evidence") or []}


def run_payload(corpus: str, repo_root: Path | None = None) -> dict | None:
    """The ``?corpus=`` run panel: resolve the corpus through the one registry to its
    FULL context (:func:`registry.project_context`, W0.3's one authority) and derive
    TARGET-FIRST — the two-root repair. ``release.py`` writes ``<target>/release/``
    and the fixedpoint loop banks harnessed rounds under ``<target>/rounds/`` (the
    same roots :func:`registry.project_states` already reads); a project whose target
    differs from its manuscript dir (subset-sum-itqde's ``whitepaper/``) used to be
    walked manuscript-first here and reported NEVER_RUN / a judge-rounds-only round
    forever — one screen from the pipeline ladder's correctly target-rooted
    UNDER_CONVERGENCE. The manuscript dir's OWN ``judge_rounds`` (the older layout,
    still real evidence) JOINS in rather than drops (the ``shared_ui.versions_join``
    precedent: both layouts are real evidence, never a silent pick-one) — its own
    latest round's artifacts ride alongside the target's harnessed ones and its round
    count folds into ``rounds_so_far``; the PRIMARY phase/current_round/gates stay the
    target's harnessed ladder (the modern convergence evidence) when it has rounds,
    falling back whole to the manuscript's own reading otherwise (a project with no
    harnessed evidence at target yet). ``None`` for an unknown (or path-shaped)
    corpus, or a project with no declared manuscript dir. Plain never-run /
    not-yet-travelled only when NEITHER root has ever been touched. A project whose
    target dir IS its manuscript dir (eigenengine) is a NO-OP through this: the join
    never fires when the two roots are the same dir."""
    from laplace.pipeline import convergence_ledger as cl

    root = (repo_root or _repo_root()).resolve()
    ctx = registry.project_context(corpus, root)
    if ctx is None or ctx.manuscript_dir is None:
        return None
    md = ctx.manuscript_dir
    td = ctx.target_dir if ctx.target_dir is not None else md
    joined = td.resolve() != md.resolve()

    # release state: TARGET-FIRST, else manuscript (registry._release_state's own
    # fallback — the ONE authority :func:`registry.project_states` reads from).
    _base_dir, release_state = registry._release_state(td, md)

    led_t = cl.assemble_ledger(str(td), root)
    real_t = [r for r in (led_t.get("rounds") or []) if not r.get("econ_only")]
    led_m = cl.assemble_ledger(str(md), root) if joined else {"rounds": [], "layout": ""}
    real_m = [r for r in (led_m.get("rounds") or []) if not r.get("econ_only")]

    layout = "+".join(dict.fromkeys(
        l for l in (led_t.get("layout"), led_m.get("layout")) if l))

    base = {
        "dir": observe.relative(md, root),
        "release_state": release_state,
        "layout": layout,
        "rounds_so_far": len(real_t) + len(real_m),
        "budget": {"max_bytes": _RUN_MAX_BYTES},
        "truncated": False,
        "gates_omitted": 0,
        "generated_ts": observe.iso_utc(time.time()),
        # THE ONE TRUTH (fix wave): the release position the dashboard/cockpit render,
        # joined here so the run tray renders a SINGLE authoritative state word instead
        # of a phase pill contradicting a release_state pill (the critic's blocking find).
        **_verdict_position(corpus, root),
    }

    if not real_t and not real_m:
        # F9, joined: never-run only when NEITHER root shows a release touch or even
        # an empty rounds/ shell; otherwise a posture exists somewhere and the honest
        # read is not-yet-travelled, never never-run.
        never_touched = (release_state == "NEVER_RUN") and not (
            (td.is_dir() and (td / "rounds").is_dir()) or
            (joined and md.is_dir() and (md / "rounds").is_dir())
        )
        base.update({
            "phase": "never-run" if never_touched else "not-yet-travelled",
            "in_flight": False,
            "never_run": never_touched,
            "current_round": None,
            "open_findings": None,
            "gates": {"hard": {}, "soft": {}, "panels": {}},
            "artifacts": [],
            "last_mtime": None,
        })
        return {"corpus": corpus, **base}

    if real_t:
        prime_dir, prime_layout, prime_real = td, (led_t.get("layout") or ""), real_t
        other_dir, other_layout, other_real = md, (led_m.get("layout") or ""), real_m
    else:
        prime_dir, prime_layout, prime_real = md, (led_m.get("layout") or ""), real_m
        other_dir, other_layout, other_real = td, (led_t.get("layout") or ""), real_t

    rec = max(prime_real, key=lambda r: r.get("round", -1))
    n = rec.get("round")
    artifacts = _round_artifacts(prime_dir, n, prime_layout, root)

    if other_real:                                       # THE JOIN — never dropped.
        orec = max(other_real, key=lambda r: r.get("round", -1))
        oarts = _round_artifacts(other_dir, orec.get("round"), other_layout, root)
        seen = {a["path"] for a in artifacts}
        artifacts = artifacts + [a for a in oarts if a["path"] not in seen]

    kinds = {a["kind"] for a in artifacts}
    phase = _derive_phase(kinds, prime_layout)
    last_mtime = max((a["mtime"] for a in artifacts if a["mtime"]), default=None)

    base.update({
        "phase": phase,
        "in_flight": phase in ("detecting", "fixing", "verified", "locked"),
        "never_run": False,
        "current_round": n,
        "open_findings": rec.get("open_findings"),
        "gates": _compact_gates(rec.get("gates") or {}),
        "artifacts": artifacts,
        "last_mtime": last_mtime,
    })
    _enforce_run_budget(base)
    return {"corpus": corpus, **base}


# ---------------------------------------------------------------------------
# W5.2 — THE LAUNCH SPLIT (Fork 6, RULED). The run panel's launch side, split by
# COST CLASS into two disjoint rosters — because a run panel that could spend
# tokens from a button click would break the storyboard dispatch-manifest law (the
# server NEVER spends tokens).
#
#   LOCAL-SAFE (cheap, deterministic, ZERO model calls) — each fires its REAL
#   executor through the EXISTING door, behind an EXPLICIT gesture (POST + ``by``;
#   arm-to-fire where the action overwrites a primary artifact). No new heavy
#   machinery: the compile action rides the W4.4 recompile MUTEX, so a double-fire
#   can never launch two latexmk runs against one manuscript.
#     storyboard-rebuild  → rebuild()                        (dispatch manifest / cheap reorder)
#     dispatch-compile    → dispatch_report()                (compile the worklist's briefs)
#     projection-compile  → projection_viewer.recompile()    (the W4.4 mutex door)
#     nodemap-rebuild     → review_surface.rebuild()          (the G-1 nodemap)
#
#   MODEL-HEAVY (a harnessed round, a re-projection, a dream) — the button banks
#   EXACTLY ONE ``kind="work-order"`` record into the friction channel and spawns
#   NOTHING (no subprocess, no agent); a LATER session (W5.3's pickup loop) is the
#   actor that actually runs it. The record IS the whole act.
#
# EVERY launch is actor-attributed: an unattributed gesture (no ``by``) is refused
# 422 — a work-order with no requester, or a local write with no author, is exactly
# the un-provenanced act this door closes.
# ---------------------------------------------------------------------------

#: the work-order store — a typed sibling in the ONE friction channel dir. Its
#: distinct ``kind`` is one the friction/recurrence scanners already SKIP (they
#: filter to friction/fork), so it never pollutes the drain; W5.3 surfaces it on the
#: desk + at wake.
_WORK_ORDER_STORE = "corpus_friction/work_orders.jsonl"

#: model-heavy actions → the honest ``what`` note banked with the work-order. The
#: server runs NONE of these; the button only ever records the request.
_MODEL_HEAVY: dict[str, str] = {
    "harnessed-round":
        "a harnessed converge round (mechanical detect → adjudicate → one strong "
        "fixing pass → re-detect → revert-on-regression → lock)",
    "re-projection":
        "a full re-projection from the conceptric (narrative planners + prose "
        "realisers + weld across the manuscript)",
    "dream":
        "a dream pass (consolidation over the corpus)",
    # THE CONJUGATE WAVE (SCOUT_2026-07-17) — the night-organs whose fire compiles
    # the tex or spends a model, banked for a later session's pickup (never on the
    # server): the detect phase, the figure materialize leg, the literature door.
    "detector-run":
        "the detector organs over a fresh compile (gap-ledger + meta-leak-scrub + "
        "source-delta + promise-audit → rounds/detector_organs_<date>.json)",
    "figure-materialize":
        "materialize the promised figures (run the generators, place the floats, "
        "reconcile the promise prose) → figure_manifest.json",
    "citation-direction-run":
        "the citation-direction organ (directed arXiv retrieval + entailment judge "
        "packets) over the dangling/unverified cites",
}

#: local-safe actions and, of them, the ones that OVERWRITE a primary on-disk
#: artifact ⇒ arm-to-fire (the first gesture previews and fires NOTHING; only an
#: explicit ``armed:true`` re-POST executes).
_LOCAL_SAFE = ("storyboard-rebuild", "dispatch-compile",
               "projection-compile", "nodemap-rebuild",
               # THE CONJUGATE WAVE — the two token-free night-organ fires: the
               # bibliography resolution (wires + resolves, no model call) and the
               # structural-conformance read leg (retrieval + conjecture, no model).
               "bibliography-run", "structural-conformance-run")
_ARM_REQUIRED = {"storyboard-rebuild", "projection-compile", "nodemap-rebuild",
                 # bibliography-run edits the root main.tex (\\bibliography) + banks
                 # intents — it overwrites a primary artifact, so it arms first.
                 "bibliography-run",
                 # structural-conformance-run OVERWRITES dispatches/structural_conformance_
                 # manifest.json (write=True) — a primary artifact — so it arms first too
                 # (the roster's own law: a local-safe action that overwrites a primary
                 # artifact must arm-to-fire; without this a bare click overwrites the
                 # banked verdict with an empty-patch under the current dial-off state).
                 "structural-conformance-run"}

#: per-action, the plain-language description the arm preview shows before firing.
_ARM_WHAT = {
    "storyboard-rebuild": "prepares storyboard work and dirty briefs; cheap mode may reorder derived output only",
    "projection-compile": "recompiles the projection pdf (+ synctex)",
    "nodemap-rebuild": "rebuilds the G-1 nodemap over the compiled pdf",
    "bibliography-run": "prepares a derived bibliography only; selected manuscript source is refused. Resolves the cite "
                        "keys, runs the render probe, and banks a literature intent "
                        "per dangling key",
    "structural-conformance-run": "overwrites the structural-conformance manifest "
                                  "(dispatches/structural_conformance_manifest.json) "
                                  "with a fresh read under the LIVE store dials — with "
                                  "the stores off this banks an empty-patch, replacing "
                                  "any prior patched verdict",
}


def launch_roster() -> dict:
    """GET /storyboard/run/launch — the launch split as a pure read model (executes
    nothing): the two cost-class rosters the panel renders, and which local-safe
    actions arm-to-fire. This is the menu, never a door."""
    return {
        "local_safe": [
            {"action": a, "arm_to_fire": a in _ARM_REQUIRED,
             "what": _ARM_WHAT.get(a, "regenerates a derived artifact")}
            for a in _LOCAL_SAFE
        ],
        "model_heavy": [
            {"action": a, "cost_class": "model-heavy", "what": what,
             "banks": "work-order", "spends_tokens": False}
            for a, what in sorted(_MODEL_HEAVY.items())
        ],
        "law": ("local-safe fires its real executor (mutex where it compiles); "
                "model-heavy banks a work-order and the server spends no tokens"),
    }


def bank_work_order(corpus: str, action: str, requested_by: str,
                    root: Path | None = None,
                    profile: str | None = None) -> dict:
    """Bank EXACTLY ONE ``kind=work-order`` record for a model-heavy launch and
    return it. Spends no tokens, spawns nothing — the record IS the whole act (the
    storyboard dispatch-manifest law); a later session runs it. The record is plain
    about WHAT, WHY, WHO, WHEN, and its COST CLASS. A per-run dials ``profile``
    rides the record so the worker session runs with the launcher's dials, not a
    hand-edit (BLOCKER-A)."""
    import datetime as _dt
    root = (root or _repo_root()).resolve()
    rec = {
        "id": _dt.datetime.now().strftime("WO-%Y%m%d-%H%M%S-%f"),
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "record": "work-order",
        "kind": "work-order",
        "action": action,
        "corpus": corpus,
        "what": _MODEL_HEAVY[action],
        "why": f"launched from the run panel for {corpus!r}",
        "requested_by": requested_by,
        "cost_class": "model-heavy",
        "status": "open",
    }
    if profile:
        rec["dials_profile"] = profile
    from laplace.pipeline import composed as _composed
    try:
        rec["composed"] = _composed.compose_work_order(
            wo_id=rec["id"], action=action, corpus=corpus, what=rec["what"],
            why=rec["why"], cost_class=rec["cost_class"],
            minted_by="bank_work_order", ts=rec["ts"])
    except ValueError:
        pass  # the fallback law: bank the order even when its account cannot compose
    from laplace.pipeline.ledger import append_jsonl
    append_jsonl(root / _WORK_ORDER_STORE, rec)
    return rec


# ---------------------------------------------------------------------------
# E4.5 — THE AXIS-GAP ROUTER (his placement: the storyboard stage, feeding the
# conceptric). The demand stops being a report. A coverage axis reading a gap
# (0/N literature, validation, or figure-demonstration) is routed to a banked,
# model-heavy work order through the SAME store + shape bank_work_order uses — and
# the server BANKS, never fires (PSU discipline; a later session runs it). The
# order's what/why names the feedback-to-conceptric leg: acceptance writes the
# named nodes and edges (a figure node + demonstrates edge; a derivation node +
# validates edge; a grounding node + supports edge). The planner consumes that
# order; this router does not build the planner.
# ---------------------------------------------------------------------------

#: outer coverage-axis name → (the model-heavy action a routed order carries, the plain
#: WHAT it banks). The WHAT names what acceptance writes back into the conceptric — the
#: feedback leg his placement ruling asks for.
_AXIS_GAP_ACTION: dict[str, tuple[str, str]] = {
    "literature": ("mint-literature",
                   "mine the literature and run the entailment judge for the claims that "
                   "ground nothing yet, so acceptance writes a grounding node and a supports "
                   "edge per claim back into the conceptric"),
    "validation": ("derive-validation",
                   "derive or simulate the validation the named claims lack, so acceptance "
                   "writes a derivation node and a validates edge per claim back into the "
                   "conceptric"),
    "demonstration": ("figure-from-evidence",
                      "propose and materialise the figures the named results demand — the "
                      "evidence-first planner's door — so acceptance writes a figure node and "
                      "a demonstrates edge per result back into the conceptric"),
}


def route_axis_gap(corpus: str, axis: str, node_ids: list | None = None,
                   requested_by: str = "", root: Path | None = None,
                   note: str = "") -> tuple[int, dict]:
    """Route a coverage-axis gap to a banked, model-heavy work order — the demand stops
    being a report. Banks EXACTLY ONE ``kind=work-order`` record (the same store + shape
    :func:`bank_work_order` uses, so it carries a composed block) and fires nothing: a
    later session runs it. The record carries the ``axis`` and its ``target_node_ids``
    typed (additive fields), and a composed ``what`` that names what acceptance writes back
    into the conceptric. Returns ``(status, obj)``: an unknown axis refuses 400, a covered
    axis (or a real zero) refuses 409 in plain words, and a routed gap returns 200 with the
    banked order and its composed glance. ``node_ids`` names a subset of the uncovered set;
    absent, the whole uncovered set is the target."""
    import datetime as _dt
    root = (root or _repo_root()).resolve()
    axis = (axis or "").strip()
    if axis not in _AXIS_GAP_ACTION:
        return 400, {"ok": False, "error": f"unknown axis {axis!r} — the routable axes are "
                     "literature, validation, and demonstration"}
    action, what = _AXIS_GAP_ACTION[axis]

    from laplace.pipeline import demand as _demand
    try:
        cov = _demand.coverage_vector(root, corpus)
    except Exception:  # noqa: BLE001 — an unresolvable corpus refuses, never crashes
        return 404, {"ok": False, "error": f"no coverage vector for corpus {corpus!r}"}
    ax = cov.get(axis)
    if not isinstance(ax, dict):
        return 400, {"ok": False, "error": f"the {axis} axis is not measured on {corpus!r}"}
    uncovered = [str(n) for n in (ax.get("uncovered") or [])]
    total = int(ax.get("total") or 0)
    if not uncovered:
        if total:
            return 409, {"ok": False, "error": f"the {axis} axis is already covered on "
                         f"{corpus!r} — every claim that raises it carries it, so there is "
                         "nothing to route"}
        return 409, {"ok": False, "error": f"nothing raises the {axis} axis on {corpus!r} yet "
                     "— the count is a real zero, so there is no gap to route"}

    # duplicate discipline (the e45 adversary's must-fix): one OPEN order per
    # (corpus, action) — re-routing an already-routed gap refuses instead of piling
    # identical open orders (the silent-accumulation class his ruling names).
    standing = [o for o in open_work_orders(load_work_orders(root))
                if (o.get("corpus") or "") == corpus and o.get("action") == action]
    if standing:
        return 409, {"ok": False, "error": f"this gap is already routed — order "
                     f"{standing[0].get('id')} is open for the {axis} axis on {corpus!r}; "
                     "resolve or drop it before banking another",
                     "open_order_id": standing[0].get("id")}

    named = [str(n) for n in (node_ids or []) if str(n).strip()]
    targets = named or uncovered
    n = len(targets)
    what_full = f"{what} ({n} uncovered node(s))"
    why = f"routed from the {axis} coverage gap for {corpus!r} — the demand banked as work"

    rec = {
        "id": _dt.datetime.now().strftime("WO-%Y%m%d-%H%M%S-%f"),
        "ts": _dt.datetime.now().isoformat(timespec="seconds"),
        "record": "work-order",
        "kind": "work-order",
        "action": action,
        "corpus": corpus,
        "what": what_full,
        "why": why,
        "requested_by": requested_by,
        "cost_class": "model-heavy",
        "status": "open",
        # additive, typed: the axis this order closes and the nodes it targets.
        "axis": axis,
        "target_node_ids": targets,
    }
    if note:
        rec["note"] = note
    from laplace.pipeline import composed as _composed
    try:
        rec["composed"] = _composed.compose_work_order(
            wo_id=rec["id"], action=action, corpus=corpus, what=what_full,
            why=why, cost_class=rec["cost_class"], minted_by="route_axis_gap",
            ts=rec["ts"])
    except ValueError:
        pass  # the fallback law: bank the order even when its account cannot compose
    from laplace.pipeline.ledger import append_jsonl
    append_jsonl(root / _WORK_ORDER_STORE, rec)
    glance = (rec.get("composed") or {}).get("glance", "")
    return 200, {"ok": True, "cost_class": "model-heavy", "spawned": False,
                 "axis": axis, "targets": targets, "work_order": rec, "glance": glance,
                 "note": ("banked a work order — the server spends no tokens; a later "
                          "session runs it, and acceptance feeds the conceptric")}


def run_launch(corpus: str, action: str, by: str | None, *,
               armed: bool = False, mode: str | None = None,
               profile: str | None = None) -> tuple[int, dict]:
    """The launch door behind POST /storyboard/run/launch — split by cost class
    (Fork 6). Returns ``(http_status, obj)``.

    LOCAL-SAFE fires the real executor exactly once (the compile action rides the
    W4.4 mutex, so a double-fire coalesces); MODEL-HEAVY banks one work-order and
    spawns nothing. An unattributed launch (no ``by``) is refused 422 for EITHER
    class. An arm-required local action fired without ``armed:true`` previews and
    executes nothing.

    ``profile`` is the per-run DIALS PROFILE (BLOCKER-A closed, 2026-07-19):
    allowlist-validated at the door (an unlawful name refuses 422, never a silent
    v1 fallback), threaded into the dials-consuming executors, and carried on a
    model-heavy work-order so the worker session runs with it — the lawful
    replacement for hand-edit-v1-then-restore."""
    by = (by or "").strip()
    if not by:
        return 422, {"ok": False,
                     "error": "by required (a launch must be actor-attributed)"}

    profile = (profile or "").strip() or None
    if profile is not None:
        from laplace.pipeline import dials as _ds
        try:
            _ds.profile_path(profile)       # the SAME allowlist/traversal fence
        except _ds.DialsProfileError as e:
            return 422, {"ok": False, "error": f"profile refused: {e}"}

    # MODEL-HEAVY: the server never spends tokens — bank one work-order, spawn nothing.
    if action in _MODEL_HEAVY:
        rec = bank_work_order(corpus, action, by, profile=profile)
        return 200, {"ok": True, "cost_class": "model-heavy", "spawned": False,
                     "work_order": rec,
                     "note": ("banked a work-order — the server spends no tokens; a "
                              "later session runs it (the pickup loop, W5.3)")}

    if action not in _LOCAL_SAFE:
        return 400, {"ok": False, "error": f"unknown launch action {action!r}",
                     "local_safe": list(_LOCAL_SAFE),
                     "model_heavy": sorted(_MODEL_HEAVY)}

    # LOCAL-SAFE: resolve the plan once, fail-closed on absence.
    loaded = _load_plan(corpus,_repo_root())
    if loaded is None:
        return 404, {"ok": False,
                     "error": f"no projection plan for corpus {corpus!r}"}

    if action in _ARM_REQUIRED and not armed:
        return 200, {"ok": False, "needs_arming": True, "armed": False,
                     "action": action, "corpus": corpus,
                     "what": _ARM_WHAT[action],
                     "note": ("this overwrites a primary artifact — re-POST with "
                              '"armed": true to fire')}

    if action == "storyboard-rebuild":
        res = rebuild(corpus, mode or "expensive")
        return (200 if res.get("ok") else 422), {"cost_class": "local-safe",
                                                  "action": action, "by": by, **res}

    if action == "dispatch-compile":
        res = dispatch_report(corpus, dials_profile=profile)
        return (200 if res.get("ok") else 422), {"cost_class": "local-safe",
                                                  "action": action, "by": by, **res}

    if action == "projection-compile":
        from laplace.manuscript import projection_viewer as pv
        from laplace.manuscript import build_targets
        try:
            target = build_targets.issue(corpus,_repo_root())
            st, row = pv.recompile(target['root'],corpus,by,build_target=target)
        except (build_targets.TargetRefused,pv.CompileRootRefused) as error:
            return 409,{'ok':False,'error':str(error),**build_targets.error_details(error)}
        return st, {"cost_class": "local-safe", "action": action, "by": by, **row}

    if action == "bibliography-run":
        # THE CONJUGATE WAVE — the References made to render: wire + resolve + probe +
        # bank literature intents (no model call → local-safe). The reader the /pipeline
        # bibliography card renders is bibliography_stage.read_manifest.
        from laplace.pipeline import bibliography_stage as _bib
        proj = registry.resolve(corpus, repo_root=_repo_root())
        md = (proj.path(proj.manuscript_dir, _repo_root())
              if (proj and proj.manuscript_dir) else None)
        if md is None:
            return 404, {"ok": False,
                         "error": f"no manuscript dir for corpus {corpus!r}"}
        from laplace.manuscript.manuscript_source import SourceLeaseError, selection_mutation
        try:
            with selection_mutation(corpus, _repo_root()):
                refusal = _derived_target_refusal(corpus, md / 'main.tex', _repo_root(), plan=loaded[1])
                if refusal:
                    return 409, {**refusal, 'action':action, 'by':by}
                res = _bib.run(md, apply=True)
        except SourceLeaseError as exc:
            return 409, {"ok":False, "reason":"source-lease-unavailable", "error":str(exc),
                         "recovery":"Inspect the current root source, then explicitly retry bibliography-run."}
        return 200, {"ok": True, "cost_class": "local-safe", "action": action,
                     "by": by, "cited": len(res.cited), "resolved": len(res.resolved),
                     "dangling": len(res.dangling), "wired": res.wired,
                     "renders": res.probe.get("renders"),
                     "intents_banked": len(res.intents)}

    if action == "structural-conformance-run":
        # THE CONJUGATE WAVE — the pre-projection conformance read leg: retrieve the
        # authored manifolds, conjecture candidate structural patches, bank the dispatch
        # manifest (no model call, applies NOTHING → local-safe). The dry-run preview is
        # the write=False path; the fire writes the manifest (write=True default).
        from laplace.pipeline import structural_conformance as _sc
        _sc_dials = None
        if profile is not None:
            from laplace.pipeline import dispatch as _dp
            _sc_dials = _dp._resolve_dials(profile)
        man = _sc.build_conformance_manifest(corpus, dials=_sc_dials)
        if man.get("error"):
            return 404, {"ok": False, "cost_class": "local-safe", "action": action,
                         "by": by, "error": man["error"]}
        return 200, {"ok": True, "cost_class": "local-safe", "action": action,
                     "by": by, "patch_count": man.get("count", 0),
                     "conformant": len(man.get("conformant") or []),
                     "unscored": len(man.get("unscored") or []),
                     "stores": man.get("stores", {}),
                     "manifest_path": man.get("manifest_path")}

    # nodemap-rebuild
    from laplace.manuscript import review_surface
    proj = registry.resolve(corpus)
    md = (proj.path(proj.manuscript_dir, _repo_root())
          if (proj and proj.manuscript_dir) else None)
    if md is None:
        return 404, {"ok": False,
                     "error": f"no manuscript dir for corpus {corpus!r}"}
    res = review_surface.rebuild(md)
    return (200 if res.get("ok") else 422), {"cost_class": "local-safe",
                                             "action": action, "by": by, **res}


# ---------------------------------------------------------------------------
# W5.3 — THE PICKUP LOOP. W5.2 banks model-heavy launches as ``kind=work-order``
# records the server never runs; W5.3 closes the loop:
#
#   SURFACE  — open work-orders ride the WAKE (self_corpus._grade0) and the DESK
#              (guide work-orders class) as bounded, refs-only HANDLES: count +
#              (id, what, cost class, requested ts). NO bodies (the wake budget
#              law); the full record is one descend into the store away.
#
#   CONSUME  — a work-order closes ONLY through an EVIDENCE-carrying resolution:
#              a RESOLUTION record (the adjudicate maker, verbatim — a wiring
#              choice, not new machinery) whose ``supersedes`` names the order and
#              whose ``evidence`` carries refs to what the run actually produced
#              (its artifacts / a commit / round evidence). An evidence-less
#              close is REFUSED and the order stays OPEN (mirrors
#              friction_consumer's consumption contract). No auto-consumption, no
#              server-side firing — a LATER session that ran the work is the actor,
#              through an actor-attributed door (the desk act door, W2.1).
#
# An unconsumed order stays open and rides the NEXT wake — that is the loop.
# ---------------------------------------------------------------------------

#: the wake budget law: at most this many handles ride the wake/desk; the rest is a
#: count behind a descend into the store. ``what`` is a label, capped — never a body.
_WO_WAKE_CAP = 12
_WO_WHAT_CAP = 90


def load_work_orders_diagnosed(root: Path | None = None
                               ) -> tuple[list[dict], list[dict]]:
    """Every readable work-order row plus exact store-integrity residuals.

    Rows remain available after a poisoned line so read-only views can serve the
    known lower bound.  Callers that mutate or certify completeness must inspect
    the diagnostics and fail closed.  This is the typed work-order face of the one
    JSONL reader in :mod:`laplace.pipeline.ledger`.
    """
    root = (root or _repo_root()).resolve()
    p = root / _WORK_ORDER_STORE
    from laplace.pipeline.ledger import read_jsonl_diagnosed
    rows, diagnostics = read_jsonl_diagnosed(
        p, store=_WORK_ORDER_STORE, required=True)
    diagnostics.extend(engine_ledger.resolution_link_diagnostics(
        rows, store=_WORK_ORDER_STORE, path=p))
    return rows, diagnostics


def load_work_orders(root: Path | None = None) -> list[dict]:
    """Compatibility projection of :func:`load_work_orders_diagnosed`.

    The tolerant row list is useful for read-only reductions; integrity-sensitive
    code must use the diagnosed form rather than mistaking a partial list for the
    whole append-only store.
    """
    rows, _diagnostics = load_work_orders_diagnosed(root)
    return rows


def _wo_evidence_refs(rec: dict) -> list[str]:
    """The evidence refs on a resolution, normalised to a non-empty-string list —
    accepts a single string or a list. This IS the fail-closed test: an empty list
    means no evidence, which refuses the consumption."""
    return engine_ledger.evidence_refs(rec)


def invalid_work_order_resolutions(records: list[dict]) -> list[dict]:
    """Resolutions that try to close a work-order WITHOUT evidence refs. Each is
    REFUSED: it does not consume, its target stays OPEN (the friction_consumer
    contract, applied to the work-order kind)."""
    recs = [r for r in records if isinstance(r, dict)]
    by_id = {r.get("id"): r for r in recs if r.get("id")}
    out: list[dict] = []
    for r in recs:
        targets = engine_ledger.resolution_targets(r)
        if not targets:
            continue
        touches_order = any(engine_ledger.is_work_order(by_id.get(t) or {})
                            for t in targets)
        if touches_order and not _wo_evidence_refs(r):
            out.append(r)
    return out


def open_work_orders(records: list[dict]) -> list[dict]:
    """The live, OPEN work-orders: work-order kind, ``status == "open"``, not retired
    by an EVIDENCE-carrying resolution. An evidence-less resolution retires nothing
    (:func:`invalid_work_order_resolutions`), so its order rides the next wake — the
    pickup loop's whole point.

    The kind test goes through :func:`laplace.engine.engine_ledger.is_work_order`
    (WO-20260820-ledger-semantics-hardening cure c): the corpus carries the same token
    in two spellings and two fields, and a literal ``kind == "work-order"`` test hid 17
    rows written as ``record: "work_order"`` with no ``kind`` at all — 6 of them open
    and live at the moment this was fixed. Read-time normalization only; no writer
    changed, no history rewritten."""
    partitions = work_order_partitions(records)
    return _work_order_rows_for_ids(records, {r["id"] for r in partitions["open_rows"]})


def _work_order_rows_for_ids(records: list[dict], ids: set[str]) -> list[dict]:
    """Latest own row for each selected id, retaining first-mint order."""
    latest: dict[str, dict] = {}
    for row in records:
        if isinstance(row, dict) and row.get("id") and engine_ledger.is_work_order(row):
            latest[str(row["id"])] = row
    return [row for oid, row in latest.items() if oid in ids]


def work_order_partitions(records: list[dict]) -> dict:
    """The account's one open/deferred/closed fold over caller-supplied rows."""
    from laplace.engine import wake
    recs = [r for r in records if isinstance(r, dict)]
    return wake.ledger_account(recs, "work_order", "work_orders")


def live_work_orders(records: list[dict]) -> list[dict]:
    """Open plus deferred orders: both are owed; only open orders are actionable."""
    partitions = work_order_partitions(records)
    ids = {r["id"] for key in ("open_rows", "deferred_rows")
           for r in partitions[key]}
    return _work_order_rows_for_ids(records, ids)


def consumed_work_orders(records: list[dict]) -> list[dict]:
    """Work-orders retired by an EVIDENCE-carrying resolution — the one mechanical
    meaning of "consumed" (the evidence is banked with the resolution)."""
    recs = [r for r in records if isinstance(r, dict)]
    by_id = {r.get("id"): r for r in recs if r.get("id")}
    out: list[dict] = []
    seen: set[str] = set()
    refused = {r.get("id") for r in invalid_work_order_resolutions(recs)}
    for r in recs:
        if r.get("id") in refused or not _wo_evidence_refs(r):
            continue
        body = f"{r.get('status', '')} {r.get('text', '')} {r.get('action', '')}"
        if (str(r.get("status", "")).lower() == "open"
                or re.search(r"HELD OPEN|\[open\]", body)):
            continue
        for target_id in engine_ledger.resolution_targets(r):
            target = by_id.get(target_id)
            if (target is not None and engine_ledger.is_work_order(target)
                    and target_id not in seen):
                out.append(target)
                seen.add(target_id)
    return out


def make_work_order_resolution(target_id: str, *, evidence_refs, by: str,
                               verb: str = "ran", reason: str = "") -> dict:
    """The close-the-loop record: the EXISTING adjudicate maker (a wiring choice,
    not new machinery) pointed at a work-order, with ``evidence`` REQUIRED — refs to
    what the run produced (artifacts / a commit / round evidence). Raises
    :class:`ValueError` on empty refs: an evidence-less resolution would leave the
    order OPEN anyway, so the door refuses to mint one."""
    refs = _wo_evidence_refs({"evidence": evidence_refs})
    if not refs:
        raise ValueError("evidence refs required: a work-order closed without "
                         "evidence (the run's artifacts / a commit / round "
                         "evidence) leaves its target OPEN")
    from laplace.pipeline import adjudicate as _adj
    rec = _adj.make_resolution(target_id, verb=verb, reason=reason, actor=by,
                               project="laplace_engine")
    rec["evidence"] = refs                       # the banked evidence, refs-list
    # The writer pays the compatibility cost once; readers never have to guess which
    # historical link spelling this generation chose.
    rec["target"] = rec["supersedes"] = rec["consumes"] = target_id
    return rec


def resolve_work_order(order_id: str, *, evidence_refs, by: str | None,
                       reason: str = "", root: Path | None = None) -> tuple[int, dict]:
    """Consume a work-order through the evidence door. Returns ``(status, obj)``.

    FAIL-CLOSED: an unattributed consumption (no ``by``) → 422; an evidence-less
    consumption → 422 and the order STAYS OPEN; consuming a missing order → 404; a
    re-consume of an already-closed order → 409. Only an attributed, evidence-
    carrying consumption appends the resolution and closes the order."""
    root = (root or _repo_root()).resolve()
    by = (by or "").strip()
    if not by:
        return 422, {"ok": False,
                     "error": "by required (a consumption is actor-attributed)"}
    records, residuals = load_work_orders_diagnosed(root)
    if residuals:
        # Appending a disposition to a partial history can retire the wrong order
        # or make the poisoned row impossible to place.  Serve the known rows, but
        # never mutate until the exact physical wound has been repaired.
        from laplace.pipeline.ledger import integrity_projection
        return 409, {"ok": False, "error": "work-order ledger is wounded; "
                     "repair its residuals before consuming any order",
                     "ledger": _WORK_ORDER_STORE, "still_open": None,
                     **integrity_projection(residuals)}
    order = next((r for r in records if r.get("id") == order_id
                  and engine_ledger.is_work_order(r)), None)
    if order is None:
        return 404, {"ok": False, "error": f"no work-order {order_id!r}"}
    if order_id not in {o.get("id") for o in live_work_orders(records)}:
        return 409, {"ok": False,
                     "error": f"work-order {order_id!r} is not open (already consumed?)"}
    try:
        res = make_work_order_resolution(order_id, evidence_refs=evidence_refs,
                                         by=by, reason=reason)
    except ValueError as e:
        # the order stays OPEN — no record written on the evidence-less path.
        return 422, {"ok": False, "error": str(e), "order": order_id,
                     "still_open": True}
    from laplace.pipeline.ledger import append_jsonl
    append_jsonl(root / _WORK_ORDER_STORE, res)
    return 200, {"ok": True, "consumed": order_id, "resolution": res,
                 "evidence": res["evidence"], "by": by}


def open_work_order_handles(root: Path | None = None,
                            cap: int = _WO_WAKE_CAP) -> dict:
    """Bounded, refs-only handles for the OPEN work-orders — the one reader the wake
    and the desk share. Each handle carries (id, what, cost class, requested ts) +
    (corpus, action) for the pickup; NEVER a body (why / provenance / any prose stay
    in the store). Returns ``{count, handles, truncated}``."""
    records, residuals = load_work_orders_diagnosed(root)
    orders = open_work_orders(records)
    # newest-first under the cap: handles[:cap] on append order let the OLDEST
    # three orders hold the wake slots forever while every fresh obligation shed
    # silently (found 2026-07-15: a just-banked pull-back order never surfaced).
    # The count + truncated flag stay loud; the SELECTION now favors recency.
    orders = sorted(orders, key=lambda o: o.get("ts") or "", reverse=True)
    handles = [{"id": o.get("id"), "action": o.get("action") or "",
                "corpus": o.get("corpus") or "",
                "what": (o.get("what") or "")[:_WO_WHAT_CAP],
                "cost_class": o.get("cost_class") or "model-heavy",
                "requested": o.get("ts") or ""}
               for o in orders]
    from laplace.pipeline.ledger import integrity_projection
    return {"count": len(handles), "handles": handles[:cap],
            "truncated": len(handles) > cap,
            **integrity_projection(residuals)}


# ---------------------------------------------------------------------------
# W-SB — THE STORYBOARD BRIEF (GET /storyboard/brief). The resting altitude of the
# surface-in-the-engine: a DELTA-AND-ASK composition (what MOVED since he last
# looked + what is ASKED of him now, never inventory prose), one-line counts for
# everything summonable, and the grounded cards the materialise doors render. Minted
# server-side; the client renders it verbatim (the counts law: each chip equals the
# rows its door returns).
# ---------------------------------------------------------------------------

_MOVE_VERB = {
    "retitle": "a section was retitled", "edit-job": "a section's job was rewritten",
    "edit-notes": "a section's notes changed", "set-refs": "a section's references changed",
    "reorder-nodes": "a section's node order changed", "set-nodes": "a section's pool was re-derived",
    "toggle-beat": "a beat was toggled", "add-node": "a node was pinned into a section",
    "remove-node": "a node was unpinned", "move-node": "a node moved between sections",
    "reorder-sections": "the section order changed", "reorder-appendices": "the appendix order changed",
    "set-meta": "the plan's framing was re-authored (contribution rank / goal)",
}


def _last_movement(corpus: str) -> dict:
    """What changed on the plan since he last looked, read from the plan-write ledger
    tail (the append-only friction ledger). Declared on absence: an empty ledger says the
    plan has not moved since it was authored (the delta-and-ask law forbids inventing a
    delta)."""
    ops = _read_ledger(corpus)
    if not ops:
        return {"changed": False,
                "what": "Nothing has moved on the plan since it was authored."}
    last = ops[-1]
    kind = last.get("kind") or ""
    ts = (last.get("ts") or "")
    who = last.get("by") or "you"
    what = _MOVE_VERB.get(kind, f"a {kind or 'plan'} edit landed")
    n = len(ops)
    tail = f" ({n} plan edit{'s' if n != 1 else ''} banked in all)"
    when = ts.split("T")[0] if "T" in ts else ts
    return {"changed": True, "kind": kind, "ts": ts,
            "what": f"Since you last looked, {what}" + (f" — {who}, {when}" if when else "")
                    + "." + tail}


def _generation_state(corpus: str) -> dict:
    """The run's generation posture for the brief: the single authoritative position
    (project_verdict, joined server-side) + the current converge round, phrased plainly.
    Degrades to a declared 'no run yet' rather than a spinner or a fabricated phase."""
    run = run_payload(corpus) or {}
    position = run.get("position") or run.get("release_state") or "no run recorded"
    rnd = run.get("current_round")
    rounds = run.get("rounds_so_far") or 0
    phase = run.get("phase") or ""
    if rnd is not None:
        label = f"round {rnd} · {phase or position}"
        sentence = (f"Generation is at round {rnd} ({phase or 'recorded'}); the surface reads "
                    f"the run's own artifacts as they land.")
    elif rounds:
        label = f"{rounds} round(s) · {position}"
        sentence = f"{rounds} converge round(s) recorded; {position}."
    else:
        label = str(position)
        sentence = (f"No converge round has been recorded yet ({position}) — the build has "
                    "not run against this plan.")
    return {"position": position, "round": rnd, "rounds": rounds,
            "label": label, "sentence": sentence}


def _section_card(sec: dict, is_app: bool, node_meta: dict, dirty_row: dict | None,
                  corpus: str) -> dict:
    """One GROUNDED section card for the materialised board: its authored job (the why),
    its real source nodes (id + plain term, working doors), its beats, its plan→prose
    freshness, and the two doors carrying the selection. Grounding composed server-side."""
    nodes = sec.get("nodes_in_order") or []
    beats = sec.get("beats") or []

    kseen: dict = {}

    def _legible(nid: str, m: dict) -> str:
        # a legible handle for every chip/retire target: the authored term when it
        # exists, else a coded handle (fal_clm_001) masked to a section-anchored label
        # ("s1 · result 1"); a readable slug id is kept as-is.
        term = m.get("term")
        if term:
            return str(term)
        tail = nid.split(":", 1)[-1]
        if _OPAQUE_HANDLE_RE.match(tail):
            k = m.get("kind") or "node"
            kseen[k] = kseen.get(k, 0) + 1
            return f"{sec.get('id')} · {k} {kseen[k]}"
        return tail.replace("-", " ")

    def entry(nid: str) -> dict:
        m = node_meta.get(nid) or {}
        return {"id": nid, "term": _legible(nid, m),
                "kind": m.get("kind"), "grade": m.get("grade"),
                "missing": bool(m.get("missing")), "beat": nid in beats}

    dirty = bool(dirty_row and dirty_row.get("dirty"))
    n_plan = (dirty_row or {}).get("n_plan")
    n_tex = (dirty_row or {}).get("n_tex")
    job = (sec.get("job") or "").strip()
    fresh = ("prose is stale for this section — a rebuild is owed" if dirty
             else "prose matches the plan" if dirty_row else "staleness not yet read")
    why = ((job + " ") if job else "") + (
        f"It pins {len(nodes)} node(s) across {len(beats)} beat(s); {fresh}.")
    spine_sel = (beats[0] if beats else (nodes[0] if nodes else f"sec:{sec.get('id')}"))
    src_entries = [entry(n) for n in nodes]
    term_by_id = {e["id"]: e["term"] for e in src_entries}
    return {
        "id": sec.get("id"),
        # the title at glance altitude carries no ascii-math soup (L^2, <K^dag K>); the
        # plan's raw title is normalised for display, the raw form staying in the plan.
        "title": _plainify_math(sec.get("title") or sec.get("id")),
        "appendix": is_app, "job": job, "why": why,
        "n_nodes": len(nodes), "n_beats": len(beats),
        "n_refs": len(sec.get("refs") or []), "n_figs": len(sec.get("figures") or []),
        "dirty": dirty, "n_plan": n_plan, "n_tex": n_tex,
        "source_nodes": src_entries,
        "beats": [{"id": b, "term": term_by_id.get(b) or _legible(b, node_meta.get(b) or {})}
                  for b in beats],
        "spine_sel": spine_sel,
        "doors": {
            "artefact": f"/artefact?corpus={corpus}&section={sec.get('id')}",
            "conceptric": (f"/conceptric?corpus={corpus}&node={spine_sel}"
                           f"&section={sec.get('id')}"),
        },
    }


def storyboard_brief(corpus: str) -> dict | None:
    """The composed BRIEF the storyboard rests at — delta-and-ask, never inventory. None
    when the corpus has no plan. Carries the grounded section cards + weighting cards
    (the materialise doors render these; the counts law holds — each count equals the
    rows its door returns)."""
    ep = enriched_plan(corpus)
    if ep is None:
        return None
    meta = ep.get("meta") or {}
    sections = ep.get("sections") or []
    appendices = ep.get("appendices") or []
    node_meta = ep.get("node_meta") or {}
    rank = meta.get("contribution_rank") or {}
    weighting = list(rank.get("primary") or []) + list(rank.get("excluded") or [])

    dmap = {d.get("id"): d for d in dirty_report(corpus)}
    cards = ([_section_card(s, False, node_meta, dmap.get(s.get("id")), corpus) for s in sections]
             + [_section_card(a, True, node_meta, dmap.get(a.get("id")), corpus) for a in appendices])

    cov = coverage_inverse(corpus)
    findings = (((cov.get("prose_by_plan") or {}).get("count") or 0)
                + ((cov.get("prose_by_fact") or {}).get("count") or 0)) if cov.get("ok") else 0

    movement = _last_movement(corpus)
    gen = _generation_state(corpus)
    wo = open_work_order_handles()
    stale = [c["id"] for c in cards if c["dirty"]]

    # THE ONE ASK (at most one decision surfaces here): stale prose > banked launches
    # awaiting a session > prose tracing to no stock > nothing waiting.
    decision = None
    if stale:
        decision = {"kind": "rebuild",
                    "glance": (f"{len(stale)} section(s) drifted from their prose "
                               f"({', '.join(stale[:4])}{'…' if len(stale) > 4 else ''}) — a rebuild "
                               "is owed before the next projection reads true."),
                    "summon": "sections"}
    elif wo.get("count"):
        # machine-waiting work is never HIS ask — it renders as information, not as
        # the one thing that needs him (the perfectionist pass: the wrong class of
        # need in the decision seat misdirects his attention).
        decision = {"kind": "work-orders", "his": False,
                    "glance": (f"{wo['count']} banked launch(es) wait for a machine session — "
                               "nothing here needs your hand; a later run picks them up."),
                    "summon": "run"}
    elif findings:
        decision = {"kind": "findings",
                    "glance": (f"{findings} paragraph(s) trace to no stock — prose the plan or the "
                               "compile leaves ungrounded."),
                    "summon": "findings"}

    # de-dup: a surfaced decision renders as its OWN element (the accented ask-card, or
    # the quiet machine-owed line) — so the glance prose does not also carry it (the
    # machine-waiting sentence was printing twice: glance tail + the quiet line). Only
    # the no-decision resting line rides the glance tail.
    glance = (f"{movement['what']} {gen['sentence']}" if decision else
              f"{movement['what']} {gen['sentence']} "
              "Nothing is waiting on you — the plan, its prose, and its stock read in sync.")
    nxt = ("Open " + decision["summon"] + " to act on it." if decision
           else "Summon a card to inspect what will be projected.")

    return {
        "corpus": corpus,
        "brief": {"glance": glance, "next": nxt},
        "movement": movement,
        "generation": gen,
        "decision": decision,
        # A malformed obligation row cannot disappear behind a plausible count.
        # The run/orders door carries the same residuals in full; the brief carries
        # the congruent integrity state so the resting surface cannot call the
        # lower-bound projection complete.
        "work_order_integrity": {
            "cracked": wo["cracked"],
            "count_is_lower_bound": wo["count_is_lower_bound"],
            "residual_count": wo["residual_count"],
            "residuals": wo["residuals"],
            "residuals_truncated": wo["residuals_truncated"],
            "residuals_omitted": wo["residuals_omitted"],
            "residual_handle": wo["residual_handle"],
        },
        "run_label": gen["label"],
        "counts": {
            "sections": len(cards),
            "weighting": len(weighting),
            "findings": findings,
        },
        "cards": cards,
        "weighting": weighting,
        "meta": meta,
    }


# ---------------------------------------------------------------------------
# routing.
# ---------------------------------------------------------------------------

def handle(path: str, query: dict, method: str, body: bytes) -> tuple[int, str, bytes] | None:
    """Route one ``/storyboard*`` request. Returns (status, content_type, body) or
    None when the path is not ours (the scanner falls through to its own routing)."""
    if path != "/storyboard" and not path.startswith("/storyboard/"):
        return None
    method = (method or "GET").upper()

    if path == "/storyboard" and method == "GET":
        return 200, "text/html; charset=utf-8", _HTML.read_bytes()

    if path == "/storyboard/brief" and method == "GET":
        # W-SB THE BRIEF: the resting altitude of the surface-in-the-engine. A
        # delta-and-ask composition + one-line counts + the grounded cards the
        # materialise doors render. Minted server-side; the client renders verbatim.
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        out = storyboard_brief(corpus)
        if out is None:
            return _json_resp(404, {"error": f"no projection plan for corpus {corpus!r}"})
        return _json_resp(200, out)

    if path == "/storyboard/plan" and method == "GET":
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        out = enriched_plan(corpus)
        if out is None:
            return _json_resp(404, {"error": f"no projection plan for corpus {corpus!r}"})
        return _json_resp(200, out)

    if path == "/storyboard/stage" and method == "GET":
        # the staged-pipeline read surface (2026-07-09): one substrate, rising
        # altitudes - plan (above) -> contracts -> narrative -> provenance ->
        # document model, each stage's artifact inspectable where it lives.
        corpus, key, sid = _q1(query, "corpus"), _q1(query, "key"), _q1(query, "sid")
        if not corpus or not key:
            return _json_resp(400, {"error": "corpus= and key= required"})
        from laplace.pipeline import registry as _registry
        proj = _registry.resolve(corpus)
        base = proj.stage_path(key) if proj else None
        if base is None:
            return _json_resp(404, {"error": f"unknown stage key {key!r}"})
        p = (base / f"{_pathsafe.encode_sid_for_path(sid)}.json") if (sid and base.is_dir()) else base
        if not p.is_file():
            if base.is_dir() and not sid:
                listing = sorted(f.stem for f in base.glob("*.json"))
                return _json_resp(200, {"corpus": corpus, "key": key,
                                        "sections": listing})
            return _json_resp(404, {"error": "stage artifact absent: "
                                             f"{key}{'/' + sid if sid else ''}"})
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _json_resp(500, {"error": "unreadable artifact"})
        out = {"corpus": corpus, "key": key, "artifact": payload}
        if sid:
            out["sid"] = sid
        return _json_resp(200, out)

    if path == "/storyboard/plan" and method == "POST":
        try:
            op = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return _json_resp(400, {"error": "bad json"})
        corpus = op.get("corpus") or _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        res = plan_write(corpus, op)
        return _json_resp(200 if res.get("ok") else 422, res)

    if path == "/storyboard/plan/undo" and method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            payload = {}
        corpus = payload.get("corpus") or _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        res = plan_undo(corpus)
        return _json_resp(200 if res.get("ok") else 400, res)

    if path == "/storyboard/spine" and method == "POST":
        try:
            op = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return _json_resp(400, {"error": "bad json"})
        corpus = op.get("corpus") or _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        res = spine_write(corpus, op)
        return _json_resp(200 if res.get("ok") else 422, res)

    if path == "/storyboard/plan/reconcile" and method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            payload = {}
        corpus = payload.get("corpus") or _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        with _PLAN_LOCK:
            res = reconcile_section_refs(corpus)
        return _json_resp(200 if res.get("ok") else 422, res)

    if path == "/storyboard/derive" and method == "GET":
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        return _json_resp(200, derive_plan(corpus))

    if path == "/storyboard/derive/apply" and method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            payload = {}
        corpus = payload.get("corpus") or _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        return _json_resp(200, derive_apply(corpus))

    if path == "/storyboard/dirty" and method == "GET":
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        return _json_resp(200, {"corpus": corpus, "report": dirty_report(corpus)})

    if path == "/storyboard/rebuild" and method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return _json_resp(400, {"error": "bad json"})
        corpus = payload.get("corpus") or _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        mode = payload.get("mode", "expensive")
        if mode not in ("cheap", "expensive"):
            return _json_resp(400, {"error": "mode must be cheap|expensive"})
        res = rebuild(corpus, mode, payload.get("sections"))
        return _json_resp(200 if res.get("ok") else 422, res)

    if path == "/storyboard/restructure" and method == "POST":
        # body = the target_arc JSON (restructure.TARGET_ARC_FIELDS); ?apply=1
        # executes, anything else is the pure dry-run preview
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        if _load_plan(corpus) is None:
            return _json_resp(404, {"error": f"no projection plan for corpus {corpus!r}"})
        try:
            arc = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return _json_resp(400, {"error": "bad json"})
        if not isinstance(arc, dict):
            return _json_resp(400, {"error": "body must be a target_arc object"})
        res = restructure_run(corpus, arc, apply=_q1(query, "apply") in ("1", "true"))
        return _json_resp(200 if res.get("ok") else 422, res)

    if path == "/storyboard/propagate" and method == "GET":
        # the propagate operator's full report - PURE READ, never a write
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        if _load_plan(corpus) is None:
            return _json_resp(404, {"error": f"no projection plan for corpus {corpus!r}"})
        from laplace.pipeline import propagate as _propagate
        try:
            rep = _propagate.propagate(corpus, since=_q1(query, "since") or None)
        except ValueError as e:                 # a bad mark, named - never a guess
            return _json_resp(400, {"error": str(e)})
        return _json_resp(200, rep)

    if path == "/storyboard/dispatch" and method == "POST":
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            payload = {}
        corpus = payload.get("corpus") or _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        if _load_plan(corpus) is None:
            return _json_resp(404, {"error": f"no projection plan for corpus {corpus!r}"})
        res = dispatch_report(corpus)
        return _json_resp(200 if res.get("ok") else 422, res)

    if path == "/storyboard/refs" and method == "GET":
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        out = refs_payload(corpus)
        if out is None:
            return _json_resp(404, {"error": f"no projection plan for corpus {corpus!r}"})
        return _json_resp(200, out)

    if path == "/storyboard/coverage" and method == "GET":
        # THE COVERAGE INVERSE (spine §4 link 4): prose-without-stock, two counts
        # (prose_by_plan / prose_by_fact) + each offender's (section, paragraph).
        # PURE READS over the narrative + prose_provenance stores; the numbers never
        # under-report (the suite clause).
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        res = coverage_inverse(corpus)
        return _json_resp(200 if res.get("ok") else 404, res)

    if path == "/storyboard/arc" and method == "GET":
        # the editable STARTING POINT for the restructure door — the identity arc.
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        out = current_arc(corpus)
        if out is None:
            return _json_resp(404, {"error": f"no projection plan for corpus {corpus!r}"})
        return _json_resp(200, out)

    if path == "/storyboard/run" and method == "GET":
        # W5.1 THE RUN PANEL: the current/most-recent round's live state derived
        # ENTIRELY from the run's own artifacts on disk. Polling this DURING a live
        # run watches it — pure reads, no orchestrator, no subprocess. Honest on
        # absence (never-run vs not-yet-travelled, F9); bounded to the golden law.
        corpus = _q1(query, "corpus")
        if not corpus:
            return _json_resp(400, {"error": "corpus= required"})
        out = run_payload(corpus)
        if out is None:
            return _json_resp(404, {"error": f"no project for corpus {corpus!r}"})
        return _json_resp(200, out)

    if path == "/storyboard/run/launch" and method == "GET":
        # W5.2 the launch split as a PURE READ: the two cost-class rosters the panel
        # renders. Executes nothing (a GET is always pure, the W1.2 law).
        return _json_resp(200, launch_roster())

    if path == "/storyboard/run/orders" and method == "GET":
        # the OPEN work orders the run panel shows (the banked model-heavy launches
        # awaiting a later session's pickup). Bounded, refs-only handles — the ONE
        # reader the wake + desk already share (open_work_order_handles). Pure read.
        return _json_resp(200, open_work_order_handles())

    if path == "/storyboard/run/launch" and method == "POST":
        # W5.2 THE LAUNCH DOOR: split by cost class (Fork 6). LOCAL-SAFE fires the
        # real executor once (mutex where it compiles); MODEL-HEAVY banks EXACTLY one
        # work-order and spawns nothing. Unattributed (no by) → 422.
        try:
            payload = json.loads(body or b"{}")
        except (ValueError, TypeError):
            return _json_resp(400, {"error": "bad json"})
        corpus = payload.get("corpus") or _q1(query, "corpus")
        action = (payload.get("action") or "").strip()
        if not corpus:
            return _json_resp(400, {"error": "corpus required"})
        if not action:
            return _json_resp(400, {"error": "action required"})
        st, obj = run_launch(corpus, action, payload.get("by"),
                             armed=bool(payload.get("armed")),
                             mode=payload.get("mode"),
                             profile=payload.get("profile"))
        return _json_resp(st, obj)

    return _json_resp(404, {"error": f"unknown storyboard route {path!r}"})
