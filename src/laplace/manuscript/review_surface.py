"""The REVIEW VIEWER (G-2) - review the real rendered artefact with node-precise findings.

The conjugate of the storyboard: where the storyboard edits the projection's
NARRATIVE STRUCTURE, this surface reviews the projection's COMPILED ARTEFACT - the
real PDF - with every finding anchored to the node it is about, on the page and rect
where that node actually landed. It is a sibling surface (like the storyboard was),
NOT a mode bolted onto the tex-centric projection viewer: it reuses that viewer's
pdf.js producer (``/projection/pdf`` + ``/projection/pdfinfo``) and the shared UI
atoms (``/shared/hymn.css`` + ``/shared/pdfjs/*``), and adds the review-specific data
layer here.

The anchor truth is the G-1 NODEMAP (:mod:`laplace.pipeline.nodemap`), never synctex:
a stuck ``figure*`` defers past its source line and synctex's reverse map then answers
the wrong page (the G-0 spike, ``experiments/g0_savepos_spike/README.md``). synctex
exists in the codebase but is NOT wired as a fallback here - a missing or stale map
shows the LOUD banner and offers a one-click instrumented rebuild (ruling 4), it never
silently degrades.

Pure handler module, same contract as ``projection_viewer`` / ``storyboard``: the
scanner owns the HTTP server and dispatches ``/review*`` here via :func:`handle`. This
module never starts a server. It is READ-ONLY this phase (G-2): it reads the one
feedback door (``feedback/feedback.jsonl``) and the current judge round, and it can
REBUILD the map (the one write it makes, into the manuscript tree, per ruling 4). The
adjudication verbs (confirm / dismiss / defer, the fingerprinted suppression writes)
land on this same surface in G-3 - the per-finding action slot is left as a clean seam.

The manuscript is located two ways, both fenced inside the repo root:
``corpus=`` resolves through the one project registry to the plan's ``target_dir``
(the production path); ``dir=`` names a manuscript directory directly (repo-relative),
so a scratch copy can be reviewed without touching the live tree.
"""
from __future__ import annotations

import datetime as _dt
import difflib
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Optional

from laplace.pipeline import schema as _schema
from laplace.pipeline import suppress as _suppress
from laplace.pipeline import adjudicate as _adj
from laplace.pipeline import edits as _edits
from laplace.pipeline.ledger import read_jsonl, append_jsonl
from laplace.core import identity_doors
# The dispatch table is the editor door's (laplace.web.review_http): this owner types no (verb, concept).

_HTML = Path(__file__).resolve().parent / "review_surface.html"
_JSON = "application/json; charset=utf-8"

#: the H-run dials profile is the active calibration surface (the plan): its
#: routing.defer_kinds is the class-grain deferral the findings panel renders as
#: 'deferred pending adjudication'. Absent -> code defaults (empty defer set).
_DEFAULT_DIALS = "profiles/pipeline/dials-h.yaml"

#: kind-prefixes of a real conceptric node (def:, res:, thm:, ...) - used to pull the
#: node id out of a judge flag's ``where`` (which may be ``<section>:<node>`` or a bare
#: node list). Citations and section slugs carry no such prefix and stay node-less.
_NODE_IN_WHERE = re.compile(
    r"(?:^|[:\s,])((?:def|res|thm|irf|goal|fork|ds|sup|lem|cor|prop|obs|"
    r"fig|eq|tab|nf):[a-z0-9][\w-]*)")

#: finding KINDS that hold a HARD contract dimension unclean (block lock) when NOT
#: deferred. The deferred set (dials) takes precedence over this classification.
_HARD_KINDS = frozenset({
    "missing-derivation", "missing-simulation", "missing-node", "missing-content",
    "unsupported-claim", "naked-claim", "refute", "legacy-notation", "legacy-term",
    "matter-scaffold", "meta-leak", "eq-duplicate", "notation-inconsistent",
})
#: round panels whose findings hold a HARD contract dimension (meta_leak ->
#: no_meta_leak, apparatus -> technical_support, claims -> semantic_identity,
#: visual -> artefact_integrity). caption/house_style are soft dimensions.
_HARD_PANELS = frozenset({"meta_leak", "apparatus", "claims", "visual"})

#: ledger ``record`` types that are ACTIONS on findings (adjudications /
#: suppressions / the txn journal), never findings themselves. The findings board
#: excludes these so an author's dismiss/confirm/defer never reads back as a new
#: finding (mirrors the fixedpoint_route findings filter).
_NON_FINDING_RECORDS = frozenset(_adj.ADJ_RECORD_KINDS
                                 | {_suppress.RECORD_KIND, _suppress.REVOKE_KIND,
                                    _edits.RECORD_KIND, "txn"})


# ---------------------------------------------------------------------------
# small helpers (the storyboard / projection_viewer contract)
# ---------------------------------------------------------------------------

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


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(_repo_root().resolve()).as_posix()
    except (ValueError, OSError):
        return str(p)


# ---------------------------------------------------------------------------
# locating the manuscript - corpus (registry) or dir (repo-relative), both fenced
# ---------------------------------------------------------------------------

def _fence(p: Path) -> Path | None:
    """Resolve ``p`` inside the repo root, or None if it escapes (the same
    containment fence the projection viewer uses)."""
    root = _repo_root().resolve()
    try:
        q = (p if p.is_absolute() else root / p).resolve()
        q.relative_to(root)
    except (ValueError, OSError):
        return None
    return q


def manuscript_dir(corpus: str = "", dir_param: str = "") -> Path | None:
    """The writable manuscript directory for a corpus or direct directory.

    A project may retain a historical projection target whose ``main.tex`` is
    absent or a scaffold.  In that case the shared source selection supplies
    the writable current tree (unless that source is foreign/read-only).  A
    healthy target remains the existing review home.
    """
    if dir_param:
        p = _fence(Path(dir_param))
        return p if (p is not None and p.is_dir()) else None
    if not corpus:
        return None
    from laplace.manuscript import manuscript_plan
    from laplace.manuscript import manuscript_versions
    payload = manuscript_plan.plan_payload(corpus)
    target = (payload or {}).get("target_dir")
    if not target:
        # A plan-less project (foreign artefact: the tex tree is read-only and
        # no projection_plan.json exists) still needs a deposit home: fall back
        # to the registry's manuscript_dir so /review can land comments there.
        from laplace.pipeline import registry
        proj = registry.resolve(corpus)
        target = proj.manuscript_dir if proj is not None else ""
    p = _fence(Path(target)) if target else None
    target_ok = p is not None and p.is_dir()
    try:
        from laplace.manuscript import manuscript_source
        source = manuscript_source.resolve(corpus, repo_root=_repo_root())
        selected_dir = _fence(Path(source["manuscript_dir"])) if source.get("manuscript_dir") else None
        if source.get("status") == "resolved" and not source.get("read_only") and selected_dir is not None:
            return selected_dir
        root_rel = source.get("root")
        source_path = _fence(Path(root_rel)) if isinstance(root_rel, str) else None
        source_dir = source_path.parent if source_path is not None and source_path.is_file() else None
        target_main = (p / "main.tex") if target_ok else None
        target_has_content = bool(target_main and manuscript_source.is_substantive(target_main))
        if source_dir is not None and not source.get("read_only") and not target_has_content:
            return source_dir
    except Exception:
        pass
    return p if target_ok else None


def manuscript_mapping(corpus: str) -> dict:
    """Expose the source/read-only/writable split without a second path policy."""
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve(corpus, repo_root=_repo_root())
    writable = manuscript_dir(corpus)
    return {"source": source,
            "writable_dir": _rel(writable) if writable is not None else None,
            "read_only": bool(source.get("read_only"))}


def _project_name(corpus: str, md: Path) -> str:
    return corpus or md.name


def _visit_key(corpus: str, dir_param: str = "") -> str:
    """The .cockpit.json last-visit key for a review target (W2.4): the corpus name
    when addressed by ``?corpus=``, else a ``dir:``-prefixed path for a dir-based
    review. Mirrors the old localStorage ``review:seen:<corpus||dir>`` basis so a
    corpus and a dir addressing the same tree never collide on one cursor."""
    corpus = (corpus or "").strip()
    if corpus:
        return corpus
    dir_param = (dir_param or "").strip()
    return f"dir:{dir_param}" if dir_param else ""




# ---------------------------------------------------------------------------
# the nodemap - the anchor truth (freshness-gated, coverage a visible gate)
# ---------------------------------------------------------------------------

def _main_tex(md: Path) -> Path:
    return md / "main.tex"


def nodemap_state(md: Path) -> dict:
    """The nodemap payload + its freshness verdict. ``present`` False -> no map on
    disk; ``fresh`` False -> the map's source fingerprint no longer equals the tree's
    (a LOUD banner, ruling 4 - never a silent synctex fallback). When present, carries
    ``entries`` (node -> rects), ``coverage`` (the visible gate) and ``unmapped``."""
    from laplace.pipeline import nodemap as nm
    main = _main_tex(md)
    jp = md / (main.stem + ".nodemap.json")
    out: dict[str, Any] = {"present": jp.is_file(), "fresh": False,
                           "path": _rel(jp) if jp.is_file() else None}
    try:
        out["source_fingerprint_now"] = nm.source_fingerprint(md)
    except Exception:
        out["source_fingerprint_now"] = None
    if not jp.is_file():
        out["stale_reason"] = "no instrumented map on disk - build one to anchor findings"
        return out
    try:
        data = json.loads(jp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        out["stale_reason"] = f"map unreadable ({e})"
        return out
    out["fresh"] = data.get("source_fingerprint") == out["source_fingerprint_now"]
    if not out["fresh"]:
        out["stale_reason"] = ("the map describes an older source tree "
                               "(fingerprint mismatch) - rebuild the instrumented map")
    for k in ("entries", "coverage", "unmapped", "built", "tiers",
              "page_count", "gate", "source_fingerprint", "main_tex"):
        if k in data:
            out[k] = data[k]
    return out


def rebuild(md: Path, dials_path: str | None = None) -> dict:
    """Build the instrumented node->region map for the manuscript (ruling 4's
    one-click action). Writes ``<md>/main.nodemap.json``. Plain failure surface: a
    :class:`nodemap.LayoutDriftError` returns its message + the drift report; any
    other failure returns the exception text - never a silent degrade to synctex."""
    from laplace.pipeline import nodemap as nm
    try:
        res = nm.build_nodemap(_main_tex(md), dials=_load_dials(dials_path))
        return {"ok": True, "coverage": res.get("coverage"), "gate": res.get("gate"),
                "page_count": res.get("page_count"), "built": res.get("built"),
                "unmapped": res.get("unmapped", [])}
    except nm.LayoutDriftError as e:
        return {"ok": False, "error": str(e), "drift": e.report,
                "kind": "LayoutDriftError"}
    except FileNotFoundError as e:
        return {"ok": False, "error": f"{e}", "kind": "FileNotFoundError"}
    except Exception as e:                       # noqa: BLE001 - the surface reports, never raises
        return {"ok": False, "error": f"{type(e).__name__}: {e}", "kind": "error"}


# ---------------------------------------------------------------------------
# the artefacts - working candidate (main.pdf), the clean named PDF, the incumbent
# ---------------------------------------------------------------------------

def _clean_artefact(md: Path) -> Optional[dict]:
    """The CLEAN named PDF (ruling 2), when a release/finalize product exists: the
    finalize record's slug PDF (with its banked title/pdftitle check) or a slug PDF on
    disk (title check computed from source, no recompile). None when only ``main.pdf``
    exists - the clean tab appears only for a real finalize product."""
    from laplace.pipeline import release as rel
    rec = rel._finalize_record(md)
    if rec and rec.get("pdf_path") and (md / rec["pdf_path"]).is_file():
        return {"pdf": _rel(md / rec["pdf_path"]), "name": Path(rec["pdf_path"]).name,
                "title": rec.get("title"), "slug": rec.get("slug"),
                "title_check": rec.get("title_check"), "source": "finalize.json"}
    # no finalize record: is there a slug PDF for the resolved title? (no recompile)
    try:
        assembled = rel.assembled_text(md)
        title = rel._resolve_title(md, None, assembled)
        slug = rel._slugify(title)
    except Exception:
        return None
    cand = md / f"{slug}.pdf"
    if not slug or not cand.is_file():
        return None
    doc_title, title_macro = rel._extract_doc_title(assembled)
    pdftitle = rel._extract_pdftitle(assembled)
    norm = rel._norm_title(title)
    title_check = {
        "resolved_title": title, "title_macro": title_macro,
        "title_macro_value": doc_title, "pdftitle_value": pdftitle,
        "title_present": doc_title is not None,
        "title_agrees": (doc_title is not None and rel._norm_title(doc_title) == norm),
        "pdftitle_present": pdftitle is not None,
        "pdftitle_agrees": (pdftitle is not None and rel._norm_title(pdftitle) == norm),
    }
    return {"pdf": _rel(cand), "name": cand.name, "title": title, "slug": slug,
            "title_check": title_check, "source": "slug-pdf"}


def _incumbent(md: Path) -> Optional[dict]:
    """The latest ``rounds/incumbent_r<N>/`` snapshot with a compiled PDF - the
    challenger's baseline for the side-by-side (ruling: incumbent vs challenger)."""
    rd = md / "rounds"
    if not rd.is_dir():
        return None
    best_n, best = 0, None
    for d in rd.glob("incumbent_r*"):
        m = re.match(r"incumbent_r(\d+)$", d.name)
        if m and (md / "rounds" / d.name / "main.pdf").is_file():
            n = int(m.group(1))
            if n >= best_n:
                best_n, best = n, d
    if best is None:
        return None
    snap = best / "SNAPSHOT.json"
    meta = {}
    if snap.is_file():
        try:
            meta = json.loads(snap.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
    return {"round": best_n, "pdf": _rel(best / "main.pdf"),
            "ts": meta.get("ts"), "dir": _rel(best)}


def artefacts(md: Path) -> dict:
    """The artefact tabs: the working candidate (always, ``main.pdf`` served through
    the projection viewer's producer), the CLEAN named PDF when a release product
    exists (with its title check + a download name), the incumbent when a round
    snapshot exists, and the release state (the finalize lifecycle position)."""
    from laplace.pipeline import release as rel
    main_pdf = md / "main.pdf"
    candidate = None
    if main_pdf.is_file():
        candidate = {"pdf": _rel(main_pdf), "name": "main.pdf",
                     "main_tex": _rel(_main_tex(md))}
    return {
        "manuscript_dir": _rel(md),
        "candidate": candidate,
        "clean": _clean_artefact(md),
        "incumbent": _incumbent(md),
        "release_state": rel.current_state(md),
    }


# ---------------------------------------------------------------------------
# the findings - node-precise, grouped by node, badged hard/soft/deferred
# ---------------------------------------------------------------------------

def _load_dials(dials_path: str | None) -> dict:
    from laplace.pipeline import dials as _d
    try:
        if dials_path:
            return _d.load_dials(dials_path)
        p = _repo_root() / _DEFAULT_DIALS
        return _d.load_dials(p) if p.is_file() else _d.defaults()
    except Exception:
        return _d.defaults()


def _defer_kinds(dials: dict) -> set[str]:
    return set((dials.get("routing") or {}).get("defer_kinds") or [])


def _nodes_in_where(where: str) -> list[str]:
    """The conceptric node ids named in a judge flag's ``where`` (a section slug, a
    ``<section>:<node>`` pair, or a bare node list). Empty when the flag is about a
    section or a citation, not a node - such findings list under 'unanchored'."""
    return sorted({m.group(1) for m in _NODE_IN_WHERE.finditer(where or "")})


def _classify(kind: str, panel: str | None, defer: set[str]) -> str:
    """A finding's class: 'deferred' (a dials defer_kind - reported, not dispatched),
    else 'hard' (holds a hard contract dimension unclean), else 'soft'."""
    if kind in defer:
        return "deferred"
    if kind in _HARD_KINDS or (panel in _HARD_PANELS):
        return "hard"
    return "soft"


def _feedback_findings(md: Path, project: str) -> list[dict]:
    """The one feedback door (``feedback/feedback.jsonl``), as findings. Each record
    carries node_id / kind / anchor / comment - the mech-panel round deposits AND the
    author's own node-precise notes ride the same ledger."""
    from laplace.manuscript import manuscript_bridge as mb
    from laplace.pipeline.ledger import live_findings as _live
    ledger = md / "feedback" / "feedback.jsonl"
    if not ledger.is_file():
        return []
    out = []
    # THE SCOPE-LATER FOLD. A row banked unscoped is scoped afterwards by an APPENDED
    # scoping record (the ``scope`` verb), never by rewriting the banked line, so the
    # altitude a reader sees is the LATEST scoping record for that id when one exists and
    # the row's own field otherwise. Built once here, so every consumer of this board
    # reads one altitude and no surface has to re-derive it.
    scoped: dict[str, dict] = {}
    for rec in mb.feedback_list(_repo_root(), project,
                                ledger=ledger).get("records", []):
        if rec.get("record") != _adj.SCOPING:
            continue
        tgt = str(rec.get("target") or "").strip()
        if not tgt:
            continue
        prev = scoped.get(tgt)
        if prev is None or str(rec.get("ts") or "") >= str(prev.get("ts") or ""):
            scoped[tgt] = rec
    # the LIVE view (ledger.py's one definition, every consumer): only the latest
    # panel round is live; older rounds are history. Serving raw history here is what
    # put eleven hundred stale rows in his rail (his catch, 2026-07-22 night).
    # …and the SUPERSEDE view on top of it (``adjudicate.live``): a row named by a
    # later record's ``supersedes`` is retired — the ledger's one correction mechanism,
    # already honoured by propagate and the intake. Without it a revoked deposit (an
    # exemplar row withdrawn through the revoke door) kept reading back as live here.
    for rec in _adj.live(
            _live(mb.feedback_list(_repo_root(), project,
                                   ledger=ledger).get("records", []))):
        if rec.get("record") in _NON_FINDING_RECORDS:
            continue                                  # an action ON a finding, not a finding
        # the anchor is a DICT on every row this surface mints, but the author's own
        # hand-written calibration rows carry a plain STRING anchor ("whole-artefact",
        # "handover", "sec:r2_intro+discussion" — FB-20260808-gm-001…gm-009). A string
        # anchor is a REF, not a structure: it is carried through as `anchor_ref` and the
        # structured lookups below run against an empty dict rather than raising (the
        # board crashed outright on his live ledger before this).
        anc = rec.get("anchor")
        anchor_ref = anc.strip() if isinstance(anc, str) else ""
        if not isinstance(anc, dict):
            anc = {}
        # honour node_id only when it is a real conceptric node id; a section-title
        # node_id (some early judge deposits) is a section-level finding, not a node.
        raw = (rec.get("node_id") or "").strip()
        grade = (anc.get("grade") or "").strip()
        # a region-grade comment (B13.3) is a page-region fallback, NEVER a conceptric
        # node — surface its rect + page, force node None so it lists honestly unanchored
        # even though its pseudo node_id (region:p<page>) is syntactically node-shaped.
        # The span and whole-paper grades ride the same rule: several sections is not one
        # node, and a whole-paper deposit has no local anchor at all.
        is_region = grade == "region" or raw.startswith("region:")
        unanchored_grade = (grade in _UNANCHORED_GRADES or is_region
                            or raw.startswith("span:")
                            or raw in _ARTEFACT_PSEUDO_ID.values())
        node = None if unanchored_grade else (
            raw if _schema.NODE_ID_RE.match(raw) else None)
        out.append({
            "source": "feedback", "id": rec.get("id"),
            "node": node,
            "kind": rec.get("kind") or "note",
            "section": anc.get("section") or ("" if (node or unanchored_grade) else raw),
            "sections": anc.get("sections") or None,     # the span deposit's row list
            "quote": anc.get("quote") or anc.get("text") or "",
            "comment": rec.get("comment") or rec.get("text") or "",
            "ts": rec.get("ts") or "",
            "by": rec.get("by") or "",
            # the row's own provenance string (his hand-written calibration rows carry
            # "gerard:…" here); kept distinct from this finding's `source` ("feedback").
            "row_source": rec.get("source") or None,
            "status": rec.get("status") or "open",
            "panel": None, "crop": anc.get("crop"),
            "grade": grade or None,
            "anchor_ref": anchor_ref or None,
            # THE ALTITUDE: the row's own field, unless a later SCOPING record moved it
            # (the scope-later door — an append, folded here). Absent stays absent (None),
            # which is the UNSCOPED state the composer banks and the band shows as such.
            "scope": ((scoped.get(str(rec.get("id") or "")) or {}).get("scope")
                      or rec.get("scope") or None),
            "scope_source": ((scoped.get(str(rec.get("id") or "")) or {}).get("scope_source")
                             if scoped.get(str(rec.get("id") or ""))
                             else rec.get("scope_source")) or None,
            "suggested_scope": rec.get("suggested_scope") or None,
            "region": anc.get("region") if is_region else None,
            "figure": anc.get("figure") or (raw if raw.startswith("fig:") else None),
            # THE RULING (WRITING-CONSOLIDATION-W1), read off the anchor where the door
            # banked it. Published here because this is the read every consumer of the
            # ledger already uses --- the walk's history door, the artefact findings board,
            # the summary strata --- so a keep/cut ruling is visible after a refresh without
            # a second read, and `None` keeps every pre-existing row exactly as it reads now.
            "disposition": anc.get("disposition") or None,
            "altitude": anc.get("altitude") or None,
            # a record that carries a composed block serves it through, so the editor tray's
            # composed-glance branch renders its authored account rather than a terse comment.
            "composed": rec.get("composed"),
        })
    return out


def _round_int(name: str) -> int:
    """Round ordinal from a round-record filename (``*_round7.json``, ``mech_r7.json``)
    — the integer, so r10 beats r2 (lexical sort would not)."""
    m = re.search(r"(?:round|_r)(\d+)", name)
    return int(m.group(1)) if m else -1


def _round_findings(md: Path) -> tuple[Optional[dict], list[dict]]:
    """The current judge round parsed to findings, plus a small round summary. The
    newest record — by round INTEGER — from ``judge_rounds/*round*.json`` or the
    harnessed layout ``rounds/harnessed/mech_r*.json`` (at the manuscript dir or its
    parent). Each panel flag becomes a finding; its node(s) are pulled from ``where``
    (a flag naming several nodes fans out to one finding per node)."""
    rp = None
    for cand in (md / "judge_rounds", md.parent / "judge_rounds",
                 md / "rounds" / "harnessed", md.parent / "rounds" / "harnessed"):
        if not cand.is_dir():
            continue
        files = list(cand.glob("*round*.json")) + list(cand.glob("mech_r*.json"))
        if files:
            rp = max(files, key=lambda p: _round_int(p.name))
            break
    if rp is None:
        return None, []
    try:
        data = json.loads(rp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, []

    findings: list[dict] = []
    for panel in data.get("panel") or []:
        label = panel.get("label")
        for flag in panel.get("flags") or []:
            if "dismissed_n" in flag:
                continue      # the machine-adjudication counter is an honesty trail, not a finding
            where = flag.get("where") or ""
            base = {"source": "round", "panel": label, "kind": flag.get("kind") or label,
                    "issue": flag.get("issue") or "", "quote": flag.get("quote") or "",
                    "status": "open", "by": "judge-panel", "crop": flag.get("crop")}
            nodes = _nodes_in_where(where)
            if nodes:
                for nid in nodes:
                    fid = f"RF:{label}:{nid}:{base['kind']}"   # deterministic, adjudicable
                    findings.append({**base, "node": nid, "section": where, "id": fid})
            else:
                fid = f"RF:{label}:{where}:{base['kind']}"
                findings.append({**base, "node": None, "section": where, "id": fid})

    contract = data.get("contract") or {}
    summary = {
        "file": _rel(rp), "round": data.get("round"), "date": data.get("date"),
        "hard_failing": data.get("hard_failing"),
        "lock_eligible": data.get("lock_eligible"),
        "lock_reasons": data.get("lock_reasons") or [],
        "contract": contract,
        "drift": data.get("drift") or {},
        "panels": [{"label": p.get("label"), "clean": p.get("clean"),
                    "failed": p.get("failed", False),
                    "n_flags": len(p.get("flags") or [])}
                   for p in (data.get("panel") or [])],
    }
    return summary, findings


def _node_text_map(md: Path) -> dict[str, str]:
    """Section-id -> CURRENT comment-stripped text, the SAME map fixedpoint_route
    feeds ``suppress.filter_findings`` (``gather_manuscript_files`` keyed by file
    stem). Sharing the one resolver is what makes a dismiss deposited HERE agree
    with the fingerprint the route confirms next round."""
    from laplace.pipeline.graph import gather_manuscript_files
    out: dict[str, str] = {}
    main = _main_tex(md)
    if not main.is_file():
        return out
    try:
        for fp, content in gather_manuscript_files(main):
            out[fp.stem] = content
    except Exception:                                # noqa: BLE001 - best-effort resolver
        pass
    return out


def _match_key(f: dict) -> str:
    """A finding's node/section key for suppression matching (real node id first,
    else the section stem the suppression was ruled on)."""
    return (f.get("node") or f.get("section") or "").strip()


def _adjudication_for(f: dict, by_target: dict, active_supps: list[dict],
                      node_text: dict[str, str]) -> dict | None:
    """The finding's current adjudication state (or None): the LATEST of an
    explicit per-target ruling (confirm/defer/route) and a matching suppression
    (dismiss/widen), by ts. A suppression whose fingerprint no longer matches the
    node's current content is STALE -> the finding is REBORN (live again, shown
    but not greyed). A revoked suppression is already absent from ``active_supps``
    (load_suppressions drops it), so a revoke returns the finding to live."""
    fid = str(f.get("id") or "")
    explicit = by_target.get(fid)                    # {state, ts, record_id, intent}
    key, kind = _match_key(f), str(f.get("kind") or "")
    matches = [s for s in active_supps
               if _suppress._matches_node_kind(s, key, kind)]
    dismissal = None
    if matches:
        s = max(matches, key=lambda x: x.get("ts") or "")
        widen = str(s.get("kind")) == _suppress.WILDCARD
        stale = False
        if key in node_text:
            cur = _suppress.content_fingerprint(node_text[key])
            stale = _suppress._supp_fingerprint(s) != cur
        dismissal = {"state": "reborn" if stale else "dismissed",
                     "ts": s.get("ts") or "", "suppression_id": s.get("id"),
                     "widen": widen, "reason": (s.get("provenance") or {}).get("reason")}
    if explicit and dismissal:
        return explicit if explicit["ts"] >= dismissal["ts"] else dismissal
    return explicit or dismissal


def _adjudicate_index(records: list[dict]) -> dict[str, dict]:
    """finding-id -> the LATEST explicit per-target ruling (confirm/defer/route),
    by ts. Superseded rulings are dropped (revoke applies here too)."""
    idx: dict[str, dict] = {}
    state_of = {_adj.CONFIRM: "confirmed", _adj.DEFER: "deferred",
                _adj.CONCEPTRIC_INTENT: "routed"}
    for r in _adj.live(records):
        rk = r.get("record")
        if rk not in state_of:
            continue
        tgt = str(r.get("target") or "")
        if not tgt:
            continue
        ts = r.get("ts") or ""
        if tgt not in idx or ts >= idx[tgt]["ts"]:
            idx[tgt] = {"state": state_of[rk], "ts": ts, "record_id": r.get("id"),
                        "intent": r.get("intent")}
    return idx


def findings(md: Path, project: str, dials_path: str | None = None,
             since: str = "") -> dict:
    """The node-precise findings board: the feedback door + the current round, grouped
    by node, badged by class (hard / soft / deferred), and (G-3) each carrying its
    ADJUDICATION state (confirmed / dismissed / deferred / routed / reborn) read from
    the same append-only ledger. A finding whose node has a nodemap entry is ANCHORED
    (it can jump to the node's page + rect); a finding with no node, or a node absent
    from the map, lists under 'unanchored' - plain, never hidden. The rail also
    surfaces the META-SIGNAL: kinds dismissed >= the recalibration threshold."""
    dials = _load_dials(dials_path)
    defer = _defer_kinds(dials)
    nm = nodemap_state(md)
    entries = nm.get("entries") or {}

    ledger = md / "feedback" / "feedback.jsonl"
    records = read_jsonl(ledger) if ledger.is_file() else []
    active_supps = _suppress.load_suppressions(ledger) if ledger.is_file() else []
    node_text = _node_text_map(md)
    by_target = _adjudicate_index(records)
    # the TERMINAL author-edit protection (B4): the (section, paragraph) units the
    # author hand-edited — locked against the pipeline, shown locked on the surface.
    protected = _edits.protected_units(records)
    prot_sections = {s for (s, p) in protected}      # whole-section locks (p == "")

    all_findings = _feedback_findings(md, project)
    round_summary, round_findings = _round_findings(md)
    all_findings += round_findings
    if since:
        # the STATELESS "new since last visit" cursor (scout hole 2): the client
        # holds the baseline (localStorage ONLY — Fork 7: the server writes no
        # visit record, ever); the server just filters by record ts. A finding
        # with no ts (a judge round-file panel record, regenerated each round)
        # cannot prove it is new, so it drops out of a since-view honestly.
        all_findings = [f for f in all_findings if (f.get("ts") or "") > since]
    for f in all_findings:
        f["adjudication"] = _adjudication_for(f, by_target, active_supps, node_text)

    # the meta-signal: finding-KINDS dismissed at/above the recalibration threshold
    threshold = int((dials.get("routing") or {}).get(
        "dismissal_recalibrate_threshold") or 5)
    dcounts = _adj.dismissal_counts(records)
    calibrated = _adj.calibrated_kinds(records)
    meta_signals = [{"kind": k, "count": c, "threshold": threshold,
                     "deposited": k in calibrated}
                    for k, c in sorted(dcounts.items()) if c >= threshold]

    by_node: dict[str, dict] = {}
    unanchored: list[dict] = []
    counts = {"hard": 0, "soft": 0, "deferred": 0}
    for f in all_findings:
        f["cls"] = _classify(f.get("kind", ""), f.get("panel"), defer)
        counts[f["cls"]] += 1
        node = f.get("node")
        anchored = bool(node and node in entries)
        if anchored:
            grp = by_node.setdefault(node, {
                "node": node, "anchored": True,
                "rects": entries.get(node) or [],
                "page": (entries.get(node) or [{}])[0].get("page"),
                "protected": _node_protected(node, protected, prot_sections,
                    str((entries.get(node) or [{}])[0].get("section") or "")),
                "findings": [], "kind_counts": {"hard": 0, "soft": 0, "deferred": 0}})
            grp["findings"].append(f)
            grp["kind_counts"][f["cls"]] += 1
        else:
            # C1 section-grain fallback: a finding with a section but no node-precise
            # anchor gets the section's BEAT (its first mapped paragraph) so the rail
            # can point at WHERE it is (coarse), never fail or mis-anchor.
            sect = (f.get("section") or "").strip()
            if sect and sect not in entries:
                beat = _section_first_para(entries, sect)
                if beat:
                    f["section_anchor"] = {"node": beat, "coarse": True,
                                           "page": (entries.get(beat) or [{}])[0].get("page")}
            unanchored.append(f)

    node_list = sorted(by_node.values(),
                       key=lambda g: (g["page"] if g["page"] is not None else 1e9,
                                      g["node"]))
    # unanchored: node-carrying-but-unmapped first (a coverage gap), then node-less
    unanchored.sort(key=lambda f: (f.get("node") is None, f.get("node") or "",
                                   f.get("section") or ""))
    return {
        "by_node": node_list,
        "unanchored": unanchored,
        "counts": {**counts, "total": len(all_findings),
                   "nodes_anchored": len(node_list),
                   "n_unanchored": len(unanchored)},
        "round": round_summary,
        "defer_kinds": sorted(defer),
        "map_present": nm.get("present"), "map_fresh": nm.get("fresh"),
        "meta_signals": meta_signals,
        "recalibrate_threshold": threshold,
        # the terminal author-edit locks, surfaced so the page shows what the
        # pipeline may never touch (B13.2 protection state).
        "protected_units": [[s, p] for (s, p) in sorted(protected)],
        "since": since or None,
    }


def _board_head(board: dict, cls: str = "", limit: int = 0,
                offset: int = 0) -> dict:
    """The rail's ≤N-row HEAD over a built findings board (motivated by the
    2026-07-11 incident, when a 2053-finding board rendered a ~254,273px scroll
    wall in a 788px pane — a historical figure, not a live count): an
    optional class FACET (``hard``/``soft``/``deferred``) plus head pagination,
    applied server-side so the client renders only what it shows. The overall
    ``counts`` stay those of the FULL board (the facet chips must stay plain);
    ``matched``/``shown``/``truncated`` describe the slice. Order is the rail's:
    anchored groups (page order) first, then unanchored."""
    cls = (cls or "").strip()
    limit = max(0, int(limit or 0))
    offset = max(0, int(offset or 0))
    if not cls and not limit and not offset:
        board["matched"] = board["counts"]["total"]
        board["shown"] = board["counts"]["total"]
        board["truncated"] = False
        return board

    def _keep(f: dict) -> bool:
        return not cls or f.get("cls") == cls

    matched = shown = skipped = 0
    groups: list[dict] = []
    for g in board["by_node"]:
        fs = [f for f in g["findings"] if _keep(f)]
        matched += len(fs)
        take: list[dict] = []
        for f in fs:
            if skipped < offset:
                skipped += 1
                continue
            if limit and shown >= limit:
                continue
            take.append(f)
            shown += 1
        if take:
            g2 = dict(g)
            g2["findings"] = take
            g2["kind_counts"] = {k: sum(1 for f in take if f.get("cls") == k)
                                 for k in ("hard", "soft", "deferred")}
            groups.append(g2)
    un: list[dict] = []
    for f in board["unanchored"]:
        if not _keep(f):
            continue
        matched += 1
        if skipped < offset:
            skipped += 1
            continue
        if limit and shown >= limit:
            continue
        un.append(f)
        shown += 1
    board["by_node"] = groups
    board["unanchored"] = un
    board["matched"] = matched
    board["shown"] = shown
    board["truncated"] = (offset + shown) < matched
    board["cls"] = cls or None
    board["limit"] = limit or None
    board["offset"] = offset or None
    return board


# ---------------------------------------------------------------------------
# W2.4 - the DELTAS-FIRST strata summary. First paint ships this (bounded), never
# the finding bodies: the 8-tray rail becomes strata + on-demand trays, so the
# 2367-finding board stops riding the wire on load. THE FAILURE SIGNAL RIDES THE
# BADGE - a failing/red stratum is never hidden behind a neutral count.
# ---------------------------------------------------------------------------

#: the golden-payload law for the summary route: ≤16KB, enforced at the tail (not
#: asserted) so an adversarial fixture (many over-threshold dismissal kinds) can
#: never blow the first-paint budget.
_SUMMARY_MAX_BYTES = 16 * 1024
#: the meta-signal head the summary carries inline (the calibration tray fetches
#: the full list on demand); capped so the strata summary stays bounded.
_SUMMARY_MAX_META = 12
#: per-class severity: hard is the RED class (a failure), soft is a warning,
#: deferred is informational (reported, not dispatched).
_CLASS_SEVERITY = {"hard": "fail", "soft": "warn", "deferred": "info"}


def _iter_board(board: dict):
    """Every finding on a built board, anchored groups then unanchored - the one
    walk the summary reduces to counts (never shipping a body)."""
    for g in board.get("by_node", []):
        for f in g.get("findings", []):
            yield f
    for f in board.get("unanchored", []):
        yield f


def summary(md: Path, project: str, dials_path: str | None = None,
            since: str = "", corpus: str = "") -> dict:
    """W2.4 - the strata summary the review rail paints on FIRST LOAD: counts by
    class/severity plus new-since-last-visit deltas, per stratum, WITHOUT a single
    finding body. The trays (findings / learned / substrate / dismissals /
    calibration) fetch their own slice on demand; this route is bounded to the
    golden-payload law (:data:`_SUMMARY_MAX_BYTES`), enforced at the tail.

    The failure signal rides the badge (his W2.4 law): a failing/red stratum is
    never hidden behind a neutral count - every stratum carries ``severity``
    (``fail`` / ``warn`` / ``info``) and a ``failing`` bool, and the new-since delta
    is split (``new`` + ``new_failing``) so a NEW failure reads red, never as a
    neutral "N new". ``since`` is the last-visit cursor (server-held now, in
    ``.cockpit.json`` - W2.4 supersedes the localStorage-only baseline for this
    surface); a record newer than it counts as new. ``max_ts`` is the newest record
    the board carries - the client banks it as the next cursor once it has painted."""
    board = findings(md, project, dials_path)          # full board, server-side only
    c = board["counts"]

    max_ts = since or ""
    new_cls = {"hard": 0, "soft": 0, "deferred": 0}
    for f in _iter_board(board):
        ts = f.get("ts") or ""
        if ts > max_ts:
            max_ts = ts
        if since and ts > since:
            k = f.get("cls") or ""
            if k in new_cls:
                new_cls[k] += 1

    strata: list[dict] = []
    for k in ("hard", "soft", "deferred"):
        cnt = int(c.get(k, 0))
        new = new_cls[k]
        strata.append({
            "id": k, "kind": "class", "label": k,
            "count": cnt, "new": new,
            "severity": _CLASS_SEVERITY[k],
            # the RED signal: a hard stratum with any finding is failing; a new hard
            # finding is a NEW failure the badge must carry, never a neutral count.
            "failing": bool(k == "hard" and cnt > 0),
            "new_failing": bool(k == "hard" and new > 0),
            "tray": "findings", "facet": k,
        })

    # unanchored - a coverage gap, honest, its own stratum (warns, never fails)
    n_un = int(c.get("n_unanchored", 0))
    strata.append({
        "id": "unanchored", "kind": "class", "label": "unanchored",
        "count": n_un, "new": 0,
        "severity": "warn" if n_un else "info",
        "failing": False, "new_failing": False,
        "tray": "findings", "facet": "",
    })

    # the meta-signal: kinds dismissed at/above the recalibrate threshold - a
    # calibration FAILURE the summary surfaces red (the full list rides the tray).
    ms = board.get("meta_signals") or []
    if ms:
        strata.append({
            "id": "calibration", "kind": "signal", "label": "calibration",
            "count": len(ms), "new": 0,
            "severity": "fail", "failing": True, "new_failing": False,
            "tray": "calibration",
        })

    # the tray strata - COUNTS only; the trays fetch bodies on demand. Each is
    # wrapped fail-closed so a broken tray-count never blows the bounded summary.
    try:
        sub = substrate_queue(md, corpus=corpus)
        q = sub.get("queue") or []
        snew = sum(1 for it in q if since and (it.get("ts") or "") > since)
        strata.append({
            "id": "substrate", "kind": "tray", "label": "substrate",
            "count": int(sub.get("count") or 0), "new": snew,
            "severity": "warn" if q else "info",
            "failing": False, "new_failing": False, "tray": "substrate",
        })
    except Exception:
        pass
    try:
        ln = learned(since=since)
        lnew = int(ln.get("rows_matched") or 0) + int(ln.get("forks_total") or 0)
        flagged = int(ln.get("flagged") or 0)
        open_total = int((ln.get("open") or {}).get("total") or 0)
        strata.append({
            "id": "learned", "kind": "tray", "label": "learned",
            "count": open_total, "new": lnew,
            # flagged = evidence-less resolutions REFUSED, their targets stay open:
            # a real failure the badge must carry red.
            "severity": "fail" if flagged else ("warn" if open_total else "info"),
            "failing": bool(flagged), "new_failing": False,
            "flagged": flagged, "tray": "learned",
        })
    except Exception:
        pass
    try:
        dm = dismissal_audit(md, dials_path)
        dc = dm.get("counts") or {}
        drows = dm.get("rows") or []
        dnew = sum(1 for r in drows if since and (r.get("ts") or "") > since)
        stale = int(dc.get("stale") or 0)
        strata.append({
            "id": "dismissals", "kind": "tray", "label": "dismissals",
            "count": int(dc.get("classes") or 0), "new": dnew,
            # a STALE dismissal = the silenced content changed, the finding is
            # already reborn: a failure of the silence, surfaced red.
            "severity": "fail" if stale else ("warn" if drows else "info"),
            "failing": bool(stale), "new_failing": False,
            "stale": stale, "tray": "dismissals",
        })
    except Exception:
        pass

    total_new = sum(int(s.get("new") or 0) for s in strata if s.get("tray") == "findings")
    out = {
        "corpus": project,
        "strata": strata,
        "counts": {"hard": int(c.get("hard", 0)), "soft": int(c.get("soft", 0)),
                   "deferred": int(c.get("deferred", 0)),
                   "total": int(c.get("total", 0)),
                   "nodes_anchored": int(c.get("nodes_anchored", 0)),
                   "n_unanchored": n_un},
        "meta_signals": ms[:_SUMMARY_MAX_META],
        # the top-level roll-up: any red stratum, and any NEW failure since the visit.
        "failing": any(s.get("failing") for s in strata),
        "new_failing": any(s.get("new_failing") for s in strata),
        "new": total_new,
        "map_present": board.get("map_present"), "map_fresh": board.get("map_fresh"),
        "round": board.get("round"),
        "since": since or None, "max_ts": max_ts or None,
        "budget": {"max_bytes": _SUMMARY_MAX_BYTES},
    }
    # the byte half of the golden law, ENFORCED not asserted: shed the inline
    # meta-signal detail (still reachable via the calibration tray) before the
    # strata, until the summary fits - the strata skeleton is never dropped.
    def _size(o: dict) -> int:
        return len(json.dumps(o, ensure_ascii=False).encode("utf-8"))
    while out["meta_signals"] and _size(out) > _SUMMARY_MAX_BYTES:
        out["meta_signals"].pop()
    if _size(out) > _SUMMARY_MAX_BYTES:
        # pathological: even the skeleton is over - drop the round echo, then trim
        # tray extras. The class strata (the point of the view) always survive.
        out.pop("round", None)
        out["truncated"] = True
    return out


# ---------------------------------------------------------------------------
# the adjudication verbs (G-3) - each ONE append-only ledger action, idempotent
# ---------------------------------------------------------------------------

def _widen_scope(md: Path, project: str, node: str) -> int:
    """The count the widen gesture shows before it silences: OPEN, not-yet-dismissed
    findings on ``node`` (across anchored + unanchored). 'silences N open finding(s)
    on this node'."""
    board = findings(md, project)
    n = 0
    for g in board["by_node"]:
        if g["node"] == node:
            n += sum(1 for f in g["findings"]
                     if (f.get("status") or "open") == "open"
                     and (f.get("adjudication") or {}).get("state") != "dismissed")
    for f in board["unanchored"]:
        if (f.get("node") or f.get("section")) == node \
                and (f.get("status") or "open") == "open" \
                and (f.get("adjudication") or {}).get("state") != "dismissed":
            n += 1
    return n


# the same `% <SEC>-pN` unit markers the route reads (fixedpoint_route
# ._paragraph_units); an edit-in-place scoped to a paragraph splices only inside
# that unit's line span so the `before` search cannot stray into a neighbour.
from laplace.pipeline.schema import PARA_MARKER_RE as _EDIT_MARK_RE


def _fragment_path(md: Path, section: str, file: str = "") -> Path | None:
    """The on-disk fragment an edit-in-place targets. An explicit ``file`` (repo-
    relative or md-relative) wins, fenced inside the manuscript dir; otherwise the
    fragment is resolved by its section STEM through the one manuscript gatherer
    (the same reading-order resolver the route + suppression share). None when the
    file escapes the manuscript, the main tex is absent, or no fragment matches."""
    mdr = md.resolve()
    if file:
        p = Path(file)
        cand = (p if p.is_absolute() else mdr / p).resolve()
        try:
            cand.relative_to(mdr)
        except ValueError:
            return None
        return cand if cand.is_file() else None
    main = _main_tex(md)
    if not main.is_file():
        return None
    try:
        from laplace.pipeline.graph import gather_manuscript_files
        for fp, _ in gather_manuscript_files(main):
            if fp.stem == section:
                return fp
    except Exception:                                # noqa: BLE001 - best-effort resolver
        return None
    return None


def _fragment_rel(md: Path, fp: Path) -> str:
    """A fragment's MANUSCRIPT-relative posix path — the one addressing vocabulary shared
    by the walk's block model (``walk.doc`` emits it as ``src.file``) and this door's
    ``file`` parameter. Falls back to the bare name for a path outside the manuscript
    (which ``_fragment_path`` already refuses), never to a silent absolute."""
    try:
        return fp.resolve().relative_to(md.resolve()).as_posix()
    except (ValueError, OSError):
        return fp.name


def _paragraph_char_span(raw: str, paragraph_id: str) -> tuple[int, int] | None:
    """The ``[lo, hi)`` character span of the ``% <SEC>-pN`` unit named by
    ``paragraph_id`` (e.g. ``"N1-p3"``) — from its marker line to the line before
    the next unit marker (or EOF), mirroring the route's ``_paragraph_units``. None
    when the fragment carries no such marker."""
    from laplace.manuscript.projection_viewer import parse_paragraphs
    matches = [span for span in parse_paragraphs(raw) if paragraph_id in span['spec_ids']]
    if len(matches) != 1:
        # A split logical unit has several physical occurrences. The scalar
        # compatibility door cannot select one by guessing its first marker.
        return None
    lines = raw.splitlines(keepends=True)
    span = matches[0]
    return sum(map(len, lines[:span['start_line'] - 1])), sum(map(len, lines[:span['end_line']]))


# a `% <SEC>-p<N>` pid decomposes into its section stem + ordinal; the prefix IS
# the fragment stem (N1-p3 -> N1), which is why a paragraph id resolves its section
# with no extra map (the C1 section-grain fallback rides this).
_SECTION_OF_PID = re.compile(r"^(.+)-p(\d+)$")


def _section_first_para(entries: dict, section: str) -> str | None:
    """The section's ANCHOR BEAT (C1 fallback): its lowest-numbered paragraph node
    among the nodemap ``entries``, or None when the section has no mapped paragraph.
    An escalation / selection that carries a section but no node-precise anchor falls
    back to THIS — a coarse anchor, marked as such, never a silent wrong anchor and
    never a hard fail."""
    candidates = []
    for ident, rectangles in (entries or {}).items():
        for rectangle in rectangles or []:
            if rectangle.get('section') == section and isinstance(rectangle.get('page'), (int, float)):
                candidates.append((rectangle['page'], rectangle.get('y', rectangle.get('y0', 0)), ident))
    # Old maps without explicit source location remain inspectable, but an ID
    # prefix or numeric suffix is neither current placement nor document order.
    return min(candidates)[2] if candidates else None


def _node_protected(node: str, protected: set, prot_sections: set, section: str = "") -> bool:
    """Whether a nodemap node is under an author-edit terminal lock — either the
    (section, paragraph) unit itself was hand-edited, or its whole section was. A
    paragraph node ``N1-p3`` protects under ``("N1", "N1-p3")`` or ``("N1", "")``."""
    # A stable logical unit retains author protection if it moves sections.
    # Whole-section protection still uses the explicitly supplied section tuple.
    return any(paragraph == node for _section, paragraph in protected) or bool(section and (section, "") in protected)


def fragment_view(md: Path, section: str, paragraph: str, project: str = "") -> dict:
    """The SOURCE bytes an edit-in-place editor edits + the unit's protection state —
    the READ half of B13.2 (the write half is the ``edit-in-place`` verb; this route
    never mutates). Given a paragraph pid (NODE grain) or just a section (COARSE,
    section-grain — falls back to the section's first marker, its beat), resolve the
    fragment and return the CURRENT prose (markers EXCLUDED — machine-owned, so they
    never enter the editor nor the before/after), the exact ``before`` the splice will
    match, the file, and whether the unit is already author-protected (terminal).
    Never raises: an unresolvable anchor returns ``{ok: False, reason, ...}`` so the
    surface degrades plainly rather than mis-anchoring."""
    section = (section or "").strip()
    paragraph = (paragraph or "").strip()
    coarse = False
    # section-grain: fall back to the section's FIRST marker (its anchor beat).
    if not paragraph and section:
        fp0 = _fragment_path(md, section)
        if fp0 is None:
            return {"ok": False, "reason": "no-fragment", "section": section,
                    "coarse": True}
        try:
            raw0 = fp0.read_text(encoding="utf-8")
        except OSError as exc:
            return {"ok": False, "reason": "read-failed", "error": str(exc),
                    "section": section, "coarse": True}
        for ln in raw0.splitlines():
            m = _EDIT_MARK_RE.match(ln.rstrip("\n"))
            if m:
                paragraph = m.group(1)
                coarse = True
                break
        # a markerless fragment stays whole-fragment (coarse), paragraph == ""
        coarse = True
    if paragraph and not section:
        return {"ok": False, "reason": "explicit-source-section-required", "paragraph": paragraph}
    if not section:
        return {"ok": False, "reason": "no-anchor"}
    fp = _fragment_path(md, section)
    if fp is None:
        return {"ok": False, "reason": "no-fragment", "section": section,
                "paragraph": paragraph, "coarse": coarse}
    try:
        raw = fp.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "reason": "read-failed", "error": str(exc),
                "section": section, "paragraph": paragraph, "coarse": coarse}
    rel_file = _rel(fp)
    ledger = md / "feedback" / "feedback.jsonl"
    records = read_jsonl(ledger) if ledger.is_file() else []
    prot = _edits.protected_units(records)
    protected = _node_protected(paragraph, prot, {row[0] for row in prot}, section)
    if paragraph:
        span = _paragraph_char_span(raw, paragraph)
        if span is None:
            return {"ok": False, "reason": "no-paragraph", "file": rel_file,
                    "section": section, "paragraph": paragraph, "coarse": coarse}
        lo, hi = span
        region = raw[lo:hi]
        body_lines = region.split("\n")
        first = raw.count("\n", 0, lo) + 1             # the region's first 1-based line
        while body_lines and (not body_lines[0].strip() or _EDIT_MARK_RE.match(body_lines[0].rstrip())):
            body_lines = body_lines[1:]
            first += 1
        before = "\n".join(body_lines).strip()
        # THE SPAN IS THE BODY'S OWN LINES (WRITING-CONSOLIDATION-W1): blank lines trimmed
        # from both ends, marker excluded, which is the SAME convention the canvas's block
        # model uses (`walk.py`'s `blk["src"]`, measured: a one-line paragraph under `% N1-p1`
        # is addressed `5-5`, not `4-5`). One addressing convention across both reads, or the
        # token one read publishes names a home the other read's span never addresses.
        while body_lines and not body_lines[0].strip():
            body_lines, first = body_lines[1:], first + 1
        while body_lines and not body_lines[-1].strip():
            body_lines = body_lines[:-1]
        line_start = first
        line_end = first + max(len(body_lines) - 1, 0)
    else:
        before = raw.strip()                          # whole markerless fragment
        line_start, line_end = 1, len(raw.split("\n"))
    # THE IDENTITIES THIS READ PUBLISHES (WRITING-CONSOLIDATION-W1). The editor sends a token
    # it READ; it never derives one from bytes it happens to hold, because a second producer
    # of the same digest is the twenty-names defect with the names hidden inside two
    # functions. `identities` keys by home, so the field name says which home the value is
    # the identity of (`identity_doors.identities`), and the three homes a ruling can name at
    # this anchor ride together: the addressed span (paragraph altitude) and the file
    # (section and chapter altitude). The LINE SPAN is published beside them, because the
    # `prose` home's id IS the span and a caller cannot re-address what it was not told.
    # `file` is REPO-relative here (`_rel`) and the splice doors address a fragment
    # MANUSCRIPT-relative (`_fragment_rel`, "the vocabulary the rewrite door consumes" ---
    # `walk.doc`'s own words). A token minted over the repo-relative spelling names a home id
    # no door ever compares, so the identities are keyed on the door's spelling and that
    # spelling is RETURNED beside them: a caller cannot send the right token if it was never
    # told which of the two addresses the home is.
    rel_md = _fragment_rel(md, fp)
    all_lines = raw.split("\n")
    # The exact bytes the published `prose` token digests and the splice door compares ---
    # served, not described, so this read is self-sufficient: the span, its bytes and its token
    # are one consistent triple. `before` stays exactly what it was (the EDITABLE text, markers
    # excluded and stripped) so every existing consumer of this read is untouched.
    span_text = "\n".join(all_lines[line_start - 1:line_end]) \
        if 0 < line_start <= line_end <= len(all_lines) else ""
    from laplace.manuscript.projection_viewer import parse_paragraphs
    physical = [row for row in parse_paragraphs(raw) if row['start_line'] <= line_start <= row['end_line']]
    return {"ok": True, "section": section, "paragraph": paragraph,
            "spec_ids": physical[0]['spec_ids'] if len(physical) == 1 else [],
            "source_section": physical[0]['section'] if len(physical) == 1 else None,
            "file": rel_file, "manuscript_file": rel_md,
            "grain": "section" if coarse else "node",
            "coarse": coarse, "protected": protected,
            "line_start": line_start, "line_end": line_end, "span_text": span_text,
            "identities": _span_identities(md, project or _project_name("", md), rel_md,
                                           raw, line_start, line_end),
            "before": before, "text": before}


# ---------------------------------------------------------------------------
# THE COMPILE-LOG READ (the honest-badge seam). The recompile loop returns only a
# 60-line log_tail; the commonest recoverable error - an undefined macro early in a
# long paper - scrolls past that tail, so latexmk exits with a written pdf and the
# surface reads a green "compiled" over a broken source. The full main.log keeps the
# error; this read lifts its problem blocks so the surface can badge the truth even
# when the exit code is clean. Read-only; it never compiles a byte.
# ---------------------------------------------------------------------------
_LOG_BANG = re.compile(r"^! (.+)")
_LOG_LNO = re.compile(r"^l\.(\d+)(.*)")
_LOG_WARN = re.compile(r"(?:LaTeX|Package [\w@-]+|pdfTeX|Class [\w@-]+) Warning: (.+)")
_LOG_BOX = re.compile(r"^(Overfull|Underfull) \\[hv]box")
_LOG_INPUTLINE = re.compile(r"(?:input line|at lines?) (\d+)")


def parse_tex_log(text: str) -> dict:
    """Lift the problem blocks out of a raw TeX .log: each ``! message`` error with
    its following ``l.NN`` source line + context, and the warning lines (LaTeX/Package
    warnings, over/underfull boxes). Returns the error + warning lists, the counts, a
    flat ``signal`` list (error rows first, then warnings) for the surface's rows, and
    a bounded tail for a full-log fold. Package-load paths are not signal - they stay
    in the tail only."""
    lines = text.splitlines()
    errors: list[dict] = []
    warnings: list[dict] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        mb = _LOG_BANG.match(ln)
        if mb:
            msg = mb.group(1).strip().rstrip(".")
            src_line = None
            context = ""
            for j in range(i + 1, min(i + 8, len(lines))):
                ml = _LOG_LNO.match(lines[j])
                if ml:
                    src_line = int(ml.group(1))
                    context = (ml.group(2) or "").strip()
                    break
            errors.append({"message": msg, "line": src_line, "context": context})
            i += 1
            continue
        mw = _LOG_WARN.search(ln)
        if mw:
            wl = _LOG_INPUTLINE.search(ln)
            warnings.append({"message": mw.group(1).strip()[:160],
                             "line": int(wl.group(1)) if wl else None})
        elif _LOG_BOX.match(ln):
            wl = _LOG_INPUTLINE.search(ln)
            warnings.append({"message": ln.strip()[:160],
                             "line": int(wl.group(1)) if wl else None, "box": True})
        i += 1
    signal: list[dict] = []
    for e in errors:
        tail = (" - l." + str(e["line"]) + " " + e["context"]) if e["line"] else ""
        signal.append({"sev": "error", "line": e["line"],
                       "text": ("! " + e["message"] + tail).strip()})
    for w in warnings[:12]:                          # the head of the warnings (counts stay full)
        signal.append({"sev": "warn", "line": w.get("line"), "text": w["message"]})
    problems = len(errors) + len(warnings)
    return {"present": True,
            "errors": errors, "warnings": warnings,
            "counts": {"errors": len(errors), "warnings": len(warnings),
                       "problems": problems},
            "signal": signal,
            "full_tail": "\n".join(lines[-160:])}


def compile_log_view(md: Path, file_param: str) -> dict:
    """Read the paper's main ``.log`` and lift its problems (:func:`parse_tex_log`).
    Resolves the ROOT tex (a fragment's log is its paper's log), then reads the sibling
    ``.log``. Absent log -> ``{present: false, reason}``. Read-only; never compiles."""
    from laplace.manuscript import projection_viewer as _pv
    p = _pv._safe_path(file_param) if file_param else None
    if p is None:
        cand = md / "main.tex"
        p = cand if cand.is_file() else None
    if p is None:
        return {"present": False, "reason": "no tex file to resolve a log for"}
    root = _pv.resolve_root(p) if p.suffix.lower() == ".tex" else p
    log = root.with_suffix(".log")
    if not log.is_file():
        return {"present": False, "reason": "no compile log on disk yet"}
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"present": False, "reason": f"log unreadable: {exc}"}
    return parse_tex_log(text)


#: the one verb roster, mechanically (the executor docstring below is the
#: canonical prose). Checked BEFORE the actor guard so a bogus verb still reads
#: back as "unknown adjudication verb" (it mints nothing either way).
_ADJ_VERBS = frozenset({
    "confirm", "defer", "dismiss", "widen", "revoke", "route-conceptric",
    "route-plan", "calibrate", "revoke-intent", "edit-in-place", "comment",
    "rewrite", "scope",
})

#: THE MARKER LAW, one producer: the structural comment lines the grain machinery anchors
#: on (``% <SEC>-pN`` / ``% NODES:`` / ``% PLAN:``) are MACHINE-OWNED. Any splice door
#: (edit-in-place, rewrite) compares these before and after and refuses a write that would
#: add, remove, or alter one — an edit that deletes its own paragraph marker silently
#: destroys the unit its protection record names, and the route then regenerates over the
#: author's hand (proved end-to-end by the judge).
#:
#: The marker dialect is the PRODUCER's, not a second guess at it: the paragraph form
#: mirrors ``projection_viewer._PARA_RE`` (``%<sid>-p<N>``, any section id) exactly. The
#: prior spelling here hard-coded ``N<...>-p<N>``, which matched the synthetic ``N1-p1``
#: fixtures and NOT the live paper's ``% sec:r2_comb-p04`` — so the guard was silently
#: inert on the very manuscript the redline walk rewrites. Widening it can only ever
#: refuse more writes, never permit one.
_STRUCT_LINE_RE = re.compile(
    r"^[ \t]*%+[ \t]*(?:\S+-p\d+|NODES\s*:.*|PLAN\s*:.*)[ \t]*$", re.MULTILINE)

#: the rewrite door's row kinds. An applied rewrite banks the SAME kind the exemplar door
#: banks (``bank_exemplar``'s ``_EXEMPLAR_KIND``), so the calibration pool consumes the
#: author's replacement prose from either gesture with no adapter. A rewrite whose source
#: bytes no longer match banks the pending kind instead — never a guessed splice.
_REWRITE_KIND = "author-rewrite"
_PENDING_REWRITE_KIND = "pending-rewrite"
#: The Writing editor's own typed edits (walk-editing.mjs commitEdit sets `source`, walk-source-client.mjs
#: sourceRequest sets `surface: "walk"`). For these the author is authoritative (wave 14a, his ruling 1 of
#: 9 November 2026): his text is applied over the span as it is now and the bytes it replaces are kept in
#: the applied row's anchor as `superseded`. Every other caller (agent tools, proposal application,
#: rollbacks, the TeX pane's block flip) keeps the identity gate, the pending row and the merge refusal.
_AUTHOR_EDITOR_SOURCES = frozenset({"click-type", "paragraph-split"})


def _author_editor_write(payload: dict) -> bool:
    return payload.get("surface") == "walk" and payload.get("source") in _AUTHOR_EDITOR_SOURCES


def _relocated_span(lines: list[str], before: str) -> tuple[int, int] | None:
    """The one 1-based line span whose bytes equal ``before`` exactly, or None when there is none or
    more than one. A span the author edited that moved because lines were added or removed above it
    is found again here, so his text replaces his own paragraph and not the lines now at its old numbers."""
    width = before.count("\n") + 1
    hits = [i for i in range(len(lines) - width + 1) if "\n".join(lines[i:i + width]) == before]
    return (hits[0] + 1, hits[0] + width) if len(hits) == 1 else None


#: A paragraph whose bytes another writer changed is found again by its words: the one paragraph of the
#: file that shares at least this share of the text he typed against (Dice over word multisets) ...
_AUTHOR_LIKENESS_FLOOR = 0.6
#: ... and leads every other paragraph by at least this much. Anything less is not located, and nothing is
#: written: his line numbers alone never choose the paragraph his text replaces (judge-r1 D2, the probe
#: where a paragraph inserted above moved his own to other lines).
_AUTHOR_LIKENESS_MARGIN = 0.2


def _prose_runs(lines: list[str], lo: int = 1, hi: int | None = None) -> list[tuple[int, int]]:
    """The 1-based (start, end) of each blank-line-delimited run of lines in ``[lo, hi]``, with the
    comment-only lines at its edges (paragraph markers, plan lines) left out."""
    hi = len(lines) if hi is None else min(hi, len(lines))
    runs, i = [], lo
    while i <= hi:
        if not lines[i - 1].strip():
            i += 1
            continue
        j = i
        while j + 1 <= hi and lines[j].strip():
            j += 1
        start, end = i, j
        while start <= end and lines[start - 1].lstrip().startswith("%"):
            start += 1
        while end >= start and lines[end - 1].lstrip().startswith("%"):
            end -= 1
        if start <= end:
            runs.append((start, end))
        i = j + 1
    return runs


def _word_likeness(a: str, b: str) -> float:
    from collections import Counter
    wa, wb = Counter(re.findall(r"\w+", a.lower())), Counter(re.findall(r"\w+", b.lower()))
    total = sum(wa.values()) + sum(wb.values())
    return 2 * sum((wa & wb).values()) / total if total else 0.0


def _author_paragraph(lines: list[str], before: str, paragraph_id: str, line_start: int = 0) -> tuple[int, int] | None:
    """Where the author's own paragraph stands now, when its exact bytes are found nowhere: the one prose
    run of its ``% <SEC>-pN`` unit when the walk named a paragraph id and that unit holds a single run;
    otherwise the one paragraph whose words are clearly his (``_AUTHOR_LIKENESS_FLOOR`` and
    ``_AUTHOR_LIKENESS_MARGIN``). When several paragraphs are that like his (a manuscript of near-repeated
    paragraphs), the one that still stands at his line is his, provided its own words reach the floor and
    the best by less than the margin: his line numbers break a tie of words, they never choose alone.
    None when nothing locates it: the door then writes nothing."""
    if paragraph_id:
        from laplace.manuscript.projection_viewer import parse_paragraphs
        units = [u for u in parse_paragraphs("\n".join(lines)) if paragraph_id in u["spec_ids"]]
        if len(units) == 1:
            runs = _prose_runs(lines, units[0]["start_line"], units[0]["end_line"])
            if len(runs) == 1:
                return runs[0]
    scored = sorted(((_word_likeness(before, "\n".join(lines[s - 1:e])), (s, e)) for s, e in _prose_runs(lines)),
                    reverse=True)
    if not scored or scored[0][0] < _AUTHOR_LIKENESS_FLOOR:
        return None
    if len(scored) == 1 or scored[0][0] - scored[1][0] >= _AUTHOR_LIKENESS_MARGIN:
        return scored[0][1]
    at_line = [(score, span) for score, span in scored if span[0] <= line_start <= span[1]
               and score >= _AUTHOR_LIKENESS_FLOOR and scored[0][0] - score < _AUTHOR_LIKENESS_MARGIN]
    return at_line[0][1] if at_line else None


def _insertion_line(lines: list[str], line_start: int) -> int:
    """Where the author's paragraph goes back when nothing in the file locates it (wave 14b): at his line,
    moved to a paragraph boundary. A blank line at his place moves forward to the next paragraph; a line
    inside a paragraph moves back to that paragraph's first line, so his paragraph never splits another
    or lands between a paragraph marker and its prose. ``len(lines) + 1`` means after the last paragraph."""
    i = min(max(line_start, 1), len(lines) + 1)
    while i <= len(lines) and not lines[i - 1].strip():
        i += 1
    if i > len(lines):
        return len(lines) + 1
    while i > 1 and lines[i - 2].strip():
        i -= 1
    return i


def _with_inserted_paragraph(lines: list[str], at: int, paragraph: list[str]) -> tuple[list[str], int]:
    """``lines`` with ``paragraph`` as a paragraph of its own before line ``at`` (after the last paragraph
    when ``at`` is past the end), one blank line between it and its neighbours; and its first line."""
    if at <= len(lines):
        return lines[:at - 1] + paragraph + [""] + lines[at - 1:], at
    last = max((k for k, line in enumerate(lines) if line.strip()), default=-1) + 1
    gap = [""] if last else []
    return lines[:last] + gap + paragraph + lines[last:], last + len(gap) + 1


def _walk_paragraph_id(payload: dict) -> str:
    """The ``% <SEC>-pN`` id the walk's block names (``<file>#<pid>``, walk.py's block id), or ''. A block
    id with an occurrence suffix (a split unit's later part) or an ordinal (``#b7``) names no unit."""
    named = (payload.get("paragraph") or "").strip()
    if not named:
        block = (payload.get("block") or payload.get("block_id") or "").strip()
        named = block.split("#", 1)[1] if "#" in block else ""
    return named if _SECTION_OF_PID.match(named) and not re.match(r"^.+-p\d+-\d+$", named) else ""

_REWRITE_RETRY_SCHEMA = "laplace.rewrite-retry/1"


def rewrite_retry_contract():
    """The same optional receipt witness in flat HTTP and grammar/native payloads."""
    return {"type":"object","required":["schema_version","pending_id","intent_sha256"],
            "properties":{"schema_version":{"const":_REWRITE_RETRY_SCHEMA},
                          "pending_id":{"type":"string","minLength":1},
                          "intent_sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},
            "additionalProperties":False}


def _rewrite_retry_intent(project, md, actor, anchor, note, reason, source, scope):
    # Closed owner normalization: guards/delivery are excluded, source bytes are exact.
    value={"schema_version":"laplace.rewrite-intent/1","operation":"rewrite",
           "project":project,"manuscript":str(md.resolve()),"actor":actor,
           "anchor":anchor,"note":note,"reason":reason,
           "source":source if isinstance(source,str) else None,"scope":scope}
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
                                    separators=(",",":")).encode("utf-8")).hexdigest()


def _rewrite_retry_check(records, witness, intent, project, actor):
    if (not isinstance(witness,dict) or set(witness)!={"schema_version","pending_id","intent_sha256"}
            or witness.get("schema_version")!=_REWRITE_RETRY_SCHEMA
            or not isinstance(witness.get("pending_id"),str) or not witness["pending_id"]
            or not isinstance(witness.get("intent_sha256"),str)
            or not re.fullmatch(r"[a-f0-9]{64}",witness["intent_sha256"])):
        return "Rewrite retry witness does not match its owner schema."
    rows=[row for row in records if row.get("id")==witness["pending_id"]]
    if len(rows)!=1:return "Rewrite retry pending ID is missing or ambiguous."
    prior=rows[0]
    if (prior.get("kind")!=_PENDING_REWRITE_KIND or prior.get("status")!="open"
            or prior.get("project")!=project or prior.get("by")!=actor):
        return "Rewrite retry does not name an open pending intent in this project and actor."
    stored=(prior.get("anchor") or {}).get("rewrite_intent_sha256")
    if not stored or stored!=intent or witness["intent_sha256"]!=intent:
        return "Rewrite retry changed its original scope or intent, or the old row has no retained witness."
    if any(row.get("kind")==_REWRITE_KIND and
           isinstance((row.get("anchor") or {}).get("rewrite_retry"),dict) and
           row["anchor"]["rewrite_retry"].get("pending_id")==witness["pending_id"]
           for row in records):
        return "This rewrite retry was already attempted; inspect its exact banked/applied receipt instead of repeating the effect."
    return ""

#: the altitude a rewrite banks at when the composer names none. His dominant gesture is a
#: sentence-level replacement; the ledger's own vocabulary already types it.
#:
#: IT IS NAMED AS THE DOOR'S, NEVER AS HIS. The default used to be applied silently — the
#: row carried ``scope="sentence"`` with no ``scope_source``, byte-identical to an altitude
#: he had picked with a digit, so no consumer could separate the machine's lean from his
#: hand and the contract's own mechanical test ("a rule whose override rate exceeds ~1/3 is
#: retired, not tuned") had nothing to count. Every defaulted row now carries
#: ``scope_source="default"``, and the walk's routing line states the same sentence BEFORE
#: Enter, so the pre-Enter promise and the banked row are one truth.
_REWRITE_DEFAULT_SCOPE = "sentence"
_REWRITE_DEFAULT_SCOPE_SOURCE = "default"

#: the body a MARK-ONLY deposit banks (selection + Enter, empty composer). The
#: ledger door requires a comment string, so the mark says what it is in words
#: rather than banking an empty row that reads back as a lost comment.
_MARK_ONLY_TEXT = "(mark only — no text)"

#: the pseudo node_ids the whole-paper grades key on. Deliberately NOT node-shaped
#: (``schema.NODE_ID_RE`` wants ``prefix:rest``), so no consumer can read one as a
#: conceptric node — the anchor grade carries the truth.
_ARTEFACT_PSEUDO_ID = {"artefact": "whole-artefact", "handover": "handover"}

#: anchor grades that are NOT node-precise: the findings board forces ``node: None``
#: for these and never leaks their pseudo id into the section field.
_UNANCHORED_GRADES = frozenset({"region", "span", "artefact", "handover"})


def _scope_fields(payload: dict) -> tuple[dict, str]:
    """The comment door's ALTITUDE fields, validated: ``scope`` / ``suggested_scope``
    against :data:`schema.FEEDBACK_SCOPES`, ``scope_source`` against
    :data:`schema.SCOPE_SOURCES`. Returns ``({field: value, …}, "")`` — the dict holds
    ONLY the fields actually supplied, so an absent scope banks UNSCOPED (first-class:
    scope is required downstream, optional at capture, and this door never guesses
    one). A value outside the vocabulary returns ``({}, message)`` and the caller
    refuses the whole deposit rather than banking an altitude nothing can group by."""
    out: dict[str, str] = {}
    for field, roster in (("scope", _schema.FEEDBACK_SCOPES),
                          ("suggested_scope", _schema.FEEDBACK_SCOPES),
                          ("scope_source", _schema.SCOPE_SOURCES)):
        raw = payload.get(field)
        val = raw.strip() if isinstance(raw, str) else ("" if raw is None else raw)
        if not val:
            continue
        if val not in roster:
            return {}, (f"{field} must be one of {list(roster)}; got {val!r}")
        out[field] = val
    return out, ""


#: THE KEEP/CUT RULING (WRITING-CONSOLIDATION-W1). A ruling on a passage is
#: ``create note@<altitude>`` --- `comment` is not a verb (GRAMMAR.md section 3 removed it as
#: "the object wearing a verb's clothes") --- and the ruling itself is SPECIALISATION, so it
#: lives in the payload and nowhere else (GRAMMAR.md section 4, the specialisation rule).
#:
#: Three values, and they are the three the author's own gesture makes: keep this passage,
#: cut it, rework it. ``rework`` is not a synonym for a bare comment: a bare comment says
#: something ABOUT a passage and leaves its fate open, and that remains the default (no
#: disposition at all, exactly as every existing caller banks today).
DISPOSITIONS = ("keep", "cut", "rework")


def _ruling_fields(payload: dict) -> tuple[dict, str]:
    """The ruling's two payload keys, validated: ``disposition`` against
    :data:`DISPOSITIONS` and ``altitude`` against the three grains a passage has
    (``identity_doors.COMMENT_CONTAINER``). Returns ``({field: value, ...}, "")`` holding
    ONLY what was supplied, or ``({}, message)``.

    NEITHER IS GUESSED AND NEITHER IS DEFAULTED. A comment with no disposition is a comment,
    which is what every row in the author's ledger already is; an altitude the caller did not
    name is derived from what the gesture itself addressed (:func:`_comment_altitude`).
    HOW it was arrived at is NOT recorded (WRITING-CONSOLIDATION-W1): an earlier draft banked
    an ``altitude_source`` beside it by analogy with ``scope_source``, and the analogy does not
    hold --- a scope the author chose and a scope the door guessed are two different rulings,
    while an altitude is the grain itself and the row carries the grain. Nothing read the
    field, and its value is reproducible from the row's own ``altitude``, ``file``,
    ``line_start``/``line_end`` and ``section`` by this very module."""
    out: dict[str, str] = {}
    raw = payload.get("disposition")
    val = raw.strip().lower() if isinstance(raw, str) else ""
    if val:
        if val not in DISPOSITIONS:
            return {}, f"disposition must be one of {list(DISPOSITIONS)}; got {val!r}"
        out["disposition"] = val
    raw = payload.get("altitude")
    val = raw.strip().lower() if isinstance(raw, str) else ""
    if val:
        if val not in identity_doors.COMMENT_CONTAINER:
            return {}, ("altitude must be one of "
                        f"{list(identity_doors.COMMENT_CONTAINER)}; got {val!r}")
        out["altitude"] = val
    return out, ""


def _comment_altitude(payload: dict, supplied: dict) -> str:
    """The altitude one comment rules at: the grain its container has.

    The caller's own, when it named one --- which the editor always does, because the
    altitude is half of its concept. Otherwise the grain the gesture ADDRESSED: a line span
    in a file is a paragraph by construction (the ``prose`` home is "the exact bytes of the
    addressed block, whole lines"), and a section with no span is a section. ``""`` --- a
    whole-paper or span deposit, which has no single container and therefore no altitude.

    ONE VALUE, not a pair (WRITING-CONSOLIDATION-W1). This returned ``(altitude, source)``
    and the source was banked; the key is removed, so the second half had no reader and the
    one caller discarded it at the call. A function that answers half a question nobody asks
    is the mechanism left standing beside its replacement."""
    if supplied.get("altitude"):
        return supplied["altitude"]
    try:
        start, end = int(payload.get("line_start") or 0), int(payload.get("line_end") or 0)
    except (TypeError, ValueError):
        start = end = 0
    if (payload.get("file") or payload.get("source_file")) and 0 < start <= end:
        return "paragraph"
    if (payload.get("section") or "").strip():
        return "section"
    return ""


def _changed_region(base: str, side: str) -> tuple[int, int, str]:
    """``(start, end, replacement)``: the one region of ``base`` that ``side`` replaces.

    The common prefix and the common suffix are peeled off, which is the same minimal-region
    reduction the walk's own composer makes when it turns a keystroke into a span
    (``walk.mjs``'s ``commitEdit``). One region, because one gesture is one edit; two distant
    edits in one request are one region spanning both, which the merge below then treats as
    touching everything between them --- conservative, and conservative in the direction of
    writing nothing."""
    pre = 0
    while pre < len(base) and pre < len(side) and base[pre] == side[pre]:
        pre += 1
    suf = 0
    while (suf < len(base) - pre and suf < len(side) - pre
           and base[len(base) - 1 - suf] == side[len(side) - 1 - suf]):
        suf += 1
    return pre, len(base) - suf, side[pre:len(side) - suf]


def _merge_edits(base: str, mine: str, theirs: str) -> str | None:
    """``mine``'s edit replayed onto ``theirs``, or ``None`` when the two touch one region.

    A three-way merge over one span, and it is the whole answer to the question `expected`
    opens: a caller holding the current identity and stale text has made an edit against bytes
    that have moved, and the only honest thing to apply is ITS EDIT, not its result. Base is
    the text it read, `mine` is what it wants, `theirs` is what the file says now.

    Non-overlapping regions compose, with the offsets shifted by the other edit's own length
    change. Overlapping regions return ``None``: two edits over one region cannot both be
    meant, and guessing which wins is how an author loses a sentence. This is deliberately a
    CHARACTER-region merge and not a line merge, because the author's gesture is a keystroke
    inside a paragraph, and a line merge would call every edit to one paragraph a conflict.
    """
    if base == theirs:
        return mine
    p1, q1, r1 = _changed_region(base, mine)
    p2, q2, r2 = _changed_region(base, theirs)
    if q1 <= p2:                                  # the caller's edit is wholly before theirs
        return theirs[:p1] + r1 + theirs[q1:]
    if p1 >= q2:                                  # ... or wholly after it, shifted by its delta
        delta = len(r2) - (q2 - p2)
        return theirs[:p1 + delta] + r1 + theirs[q1 + delta:]
    return None


def _container_home(md: Path, project: str, altitude: str, payload: dict,
                    section: str) -> tuple[str, str, Any] | None:
    """The home a ``create note@<altitude>`` gate proves: the container, with its own bytes.

    ``create``'s gate is the CONTAINER's token (GRAMMAR.md section 3's verb table), and the
    container of a ruling is the passage it rules on --- not the note, which is the home that
    did not exist yet. All three are recipe ``B`` homes, so the value handed to the gate is
    the exact bytes and the token is ``grammar.digest_bytes`` over them: the same sha256 over
    the same bytes the rewrite door already compares at ``review_surface.py:1890``. No new
    digest is invented for any of the three (GRAMMAR.md section 1's parity constraint).

    ``None`` when this gesture addresses no single container --- the artefact and span tiers,
    which rule on the whole paper or several sections and have no one home."""
    kind = identity_doors.COMMENT_CONTAINER.get(altitude)
    if not kind:
        return None
    file_hint = str(payload.get("file") or payload.get("source_file") or "").strip()
    fp = _fragment_path(md, section, file_hint)
    if fp is None or not fp.is_file():
        return None
    rel_file = _fragment_rel(md, fp)
    try:
        raw = fp.read_text(encoding="utf-8")
    except OSError:
        return None
    if kind != "prose":
        # `section` and `chapter` are both one source file's exact bytes (GRAMMAR.md
        # section 2); the altitude says which grain the ruling is AT, the bytes are the file's.
        return (kind, "%s::%s" % (project, rel_file), raw.encode("utf-8"))
    try:
        start, end = int(payload.get("line_start") or 0), int(payload.get("line_end") or 0)
    except (TypeError, ValueError):
        return None
    lines = raw.split("\n")
    if not (0 < start <= end <= len(lines)):
        return None
    span = "\n".join(lines[start - 1:end])
    return ("prose", "%s::%s:%d-%d" % (project, rel_file, start, end), span.encode("utf-8"))


def _span_identities(md: Path, project: str, rel_file: str, raw: str,
                     start: int, end: int) -> dict[str, str]:
    """``{home: token}`` for the homes one addressed span HAS --- the read half of the gate.

    Published by ``/review/fragment`` (and by ``walk.doc`` per block) so the editor SENDS a
    token it read rather than deriving one: the twenty-names cure is that one read publishes
    one name per value (``identity_doors.identities``), and a surface that recomputed the
    digest from bytes it happened to hold would be a second producer of the same identity.

    All three homes ride together on purpose: a paragraph ruling needs the ``prose`` span and
    a section or chapter ruling needs the whole file, and a caller that has to ask twice is a
    caller that will send the wrong one.

    ``section`` and ``chapter`` carry the SAME digest here, and that is the grammar's own
    shape rather than a second name for one value: section 2 declares both kinds over one
    source file's bytes with one read (``source {files:[path]}``) --- the only pair in
    ``HOME_KINDS`` that does --- so a read that published only one of them would leave the
    other altitude ungated. The key is the HOME, so each name says which home it is the
    identity of, and a request carries exactly one of them, chosen by its altitude. That
    those two kinds should be one is a finding for the grammar, recorded as a residual, not
    something this door may decide."""
    lines = raw.split("\n")
    homes: list[tuple[str, str, Any]] = [
        ("section", "%s::%s" % (project, rel_file), raw.encode("utf-8")),
        ("chapter", "%s::%s" % (project, rel_file), raw.encode("utf-8"))]
    if 0 < start <= end <= len(lines):
        homes.append(("prose", "%s::%s:%d-%d" % (project, rel_file, start, end),
                      "\n".join(lines[start - 1:end]).encode("utf-8")))
    return identity_doors.identities(*homes)


#: the per-side cap on an anchor's context snapshot. The composer sends ~200 characters
#: each side of the quote; this is the ceiling the ledger will hold, so a pathological
#: client cannot grow a feedback row without bound.
_CONTEXT_CAP = 400


def _context_fields(payload: dict) -> dict:
    """The anchor snapshot's CONTEXT — the characters each side of the quote, read from
    the same rendered text the author selected in. An anchor is PROVISIONAL: the quote
    alone cannot always be relocated after an edit (a repeated phrase, a re-flowed
    paragraph), and the surrounding text is what lets a later reader place it — or say
    plainly that it no longer resolves, rather than silently dropping it.

    Both fields are OPTIONAL and each is written ONLY when supplied, so every existing
    caller mints exactly the anchor shape it already gets. Each side is capped at
    :data:`_CONTEXT_CAP`, keeping the side NEAREST the quote (the tail of ``before``,
    the head of ``after``) — the part that does the placing."""
    out: dict[str, str] = {}
    before = payload.get("context_before")
    if isinstance(before, str) and before.strip():
        out["context_before"] = before.strip()[-_CONTEXT_CAP:]
    after = payload.get("context_after")
    if isinstance(after, str) and after.strip():
        out["context_after"] = after.strip()[:_CONTEXT_CAP]
    return out


def _span_sections(payload: dict) -> tuple[list[str], str]:
    """The section list of a SPAN deposit — ``{"span": {"sections": [...]}}`` (a list
    of section ids is also accepted). Returns ``([], "")`` when the payload carries no
    span at all, ``([], message)`` when it carries one that is malformed or empty (a
    span naming no section would otherwise bank as a fabricated anchor)."""
    span = payload.get("span")
    if span in (None, "", [], {}):
        return [], ""
    if isinstance(span, dict):
        sections = span.get("sections")
    elif isinstance(span, (list, tuple)):
        sections = span
    else:
        return [], "span must be {sections: [...]} or a list of section ids"
    if not isinstance(sections, (list, tuple)):
        return [], "span.sections must be a list of section ids"
    out = [str(s).strip() for s in sections if str(s).strip()]
    if not out:
        return [], "span.sections must name at least one section"
    return out, ""


def _artefact_grade(payload: dict) -> str:
    """The whole-paper grade a deposit asks for: ``"artefact"``, ``"handover"``, or
    ``""`` (not a whole-paper deposit). Read from an explicit ``grade``/``anchor_grade``
    or the ``artefact: true`` flag the composer's whole-paper key sets."""
    raw = (payload.get("grade") or payload.get("anchor_grade") or "").strip().lower()
    if raw in _ARTEFACT_PSEUDO_ID:
        return raw
    if payload.get("artefact") or payload.get("whole_artefact"):
        return "artefact"
    return ""


def mirror_source_changes(project: str, changes: list, root: Path | None = None, *, expected_selection=None) -> dict:
    """Compatibility delegate; source effect owners migrate to writing.source_effects."""
    from laplace.manuscript.source_effects import mirror_headings
    return mirror_headings(project, changes, Path(root) if root else _repo_root(), expected_selection=expected_selection)


def adjudicate(md: Path, project: str, payload: dict, *, source_changes: list | None = None, repo_root=None) -> dict:
    """The adjudication owner leases physical source before fresh guards/effect.

    Batch parents pass a transient ``source_changes`` collector and explicitly
    call ``mirror_source_changes`` after their outermost effect/rollback lease.
    No optional projection runs while a nested source lease remains held.
    """
    identity_doors.admit_expected(payload, "apply_revision")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    # RD-EDITOR-ROOT: ONE owning root is admitted here, at the public boundary, and every inner adapter
    # (rewrite, retry, feedback, versions, source effect) uses it; nothing below re-reads the ambient root.
    root = Path(repo_root).resolve() if repo_root is not None else _repo_root().resolve()
    verb = (payload.get("verb") or "").strip()
    if verb not in {"rewrite", "edit-in-place"} or not (payload.get("by") or "").strip():
        return _adjudicate(md, project, payload, repo_root=root)
    from laplace.manuscript import manuscript_source
    path = _fragment_path(md, (payload.get("section") or "").strip(), (payload.get("file") or "").strip())
    if path is None:
        return _adjudicate(md, project, payload, repo_root=root)
    refused = _outside_owning_root(path, root)
    if refused is not None:
        return refused
    from laplace.pipeline import registry
    from contextlib import nullcontext
    scoped = registry.resolve(project, root) is not None
    changes = []
    try:
        if not scoped:
            manuscript_source.require_unregistered_source(path, root)
        with (manuscript_source.selection_mutation(project, root) if scoped else nullcontext()), manuscript_source.source_mutation([path]) as lease:
            access = manuscript_source.source_access(project, path, root, writable=True,
                expected_selection=payload.get('expected_selection')) if scoped else None
            before = path.read_bytes()
            result = _adjudicate(md, project, payload, source_path=lease.paths[0], source_changes=changes, repo_root=root)
            if result.get('ok') and not result.get('pending'):
                from laplace.manuscript import source_effects
                intended = changes[-1][2].encode('utf-8') if changes else before
                result['source_effect'] = source_effects.receipt(project,
                    access['selection_identity'] if access else None,
                    [source_effects.observed_file(root, path, before, intended)])
            if access:result['selection_identity'] = access['selection_identity']
    except manuscript_source.SourceAccessError as exc:
        return dict(exc.response)
    except manuscript_source.SourceLeaseError as exc:
        return {"error": str(exc), "reason": "source-lease-refused"}
    if changes and not lease.outermost:
        if source_changes is not None:
            source_changes.extend(changes)
        result.setdefault("receipt", {})["plan_sync"] = {"status": "DEFERRED", "reason": "parent source effect has not settled"}
    elif changes:
        try:
            result.setdefault("receipt", {})["plan_sync"] = mirror_source_changes(project, changes, root, expected_selection=access["selection_identity"] if access else None)
        except (OSError, ValueError, manuscript_source.SourceLeaseError) as exc:
            result.setdefault("receipt", {})["plan_sync"] = {"status": "UNPROVED", "reason": str(exc)}
        if result["receipt"]["plan_sync"]["status"] not in {"CURRENT", "NOT_NEEDED"}:
            result["receipt"]["plan_sync_note"] = result["receipt"]["plan_sync"].get("reason", "heading projection unavailable")
    if isinstance(result.get('source_effect'), dict):
        from laplace.manuscript import source_effects
        legacy_receipt = result.get('receipt') or {}
        for key in ('version_note', 'retry_warning'):
            if legacy_receipt.get(key):
                result.setdefault('maintenance_warnings', []).append({'operation':key, 'reason':legacy_receipt[key]})
        source_effects.finish(result, project, root, result['source_effect'], changes=changes,
            heading_sync=legacy_receipt.get('plan_sync'))
    return result


def _outside_owning_root(path: Path, root: Path) -> dict | None:
    """The source a rewrite names must lie inside its admitted owning root -- after symlinks are resolved
    -- before any lease, read, staging, feedback or effect. The strict receipt fence
    (laplace.core.receipts.file_receipt) stays; this refusal comes first, so a foreign path never changes bytes."""
    try:
        resolved = Path(path).resolve()
    except (OSError, RuntimeError):
        resolved = None
    if resolved is not None and resolved.is_relative_to(Path(root).resolve()):
        return None
    return {"error": "This source is outside the checkout that owns this request; nothing was read or written. "
                     "Address a file of this project's selected manuscript.",
            "reason": "source-outside-owning-root", "refused_before_effect": True}


def _adjudicate(md: Path, project: str, payload: dict, *, source_path: Path | None = None,
                source_changes: list | None = None, repo_root=None) -> dict:
    """Execute one adjudication verb as ONE append-only ledger action (validate,
    check idempotency, append through the one door). Verbs: ``confirm`` / ``dismiss``
    / ``defer`` / ``widen`` / ``revoke`` / ``route-conceptric`` / ``calibrate`` /
    ``edit-in-place`` (the TERMINAL rung — splice the prose by hand + bank the
    capture in one write). Returns ``{ok, verb, record, ...}`` or ``{error}`` (the
    route maps error -> 422). Every write is an append; a past line is never
    rewritten (the edit-in-place fragment splice is the one exception — it edits
    the manuscript bytes, then banks its capture append-only)."""
    owning_root = Path(repo_root).resolve() if repo_root is not None else _repo_root().resolve()   # RD-EDITOR-ROOT
    verb = (payload.get("verb") or "").strip()
    if verb not in _ADJ_VERBS:
        return {"error": f"unknown adjudication verb {verb!r}"}
    # THE ACTOR GUARD (RW-20260711-103301-400002 — the scout's live incident:
    # unauthenticated click-enumeration minted author-attributed records). Every
    # adjudication record is actor-attributed, so the door takes an EXPLICIT
    # ``by`` and defaults NOWHERE server-side: the UI supplies its actor, a
    # machine caller names itself, and an unattributed write is refused (422 at
    # the route) BEFORE any ledger append.
    actor = (payload.get("by") or "").strip()
    if not actor:
        return {"error": "by (explicit actor) is required: adjudication records "
                         "are actor-attributed and this door defaults nowhere — "
                         "an unattributed request must never mint a verdict"}
    ledger = md / "feedback" / "feedback.jsonl"
    records = read_jsonl(ledger) if ledger.is_file() else []
    round_no = int(payload.get("round") or 0)
    note = (payload.get("note") or "").strip()
    reason = (payload.get("reason") or note or "").strip()
    node = (payload.get("node") or "").strip()
    kind = (payload.get("kind") or "").strip()
    section = (payload.get("section") or "").strip()
    finding_id = (payload.get("finding_id") or "").strip()

    def _find(pred):
        return next((r for r in _adj.live(records) if pred(r)), None)

    if verb == "confirm":
        if not finding_id:
            return {"error": "finding_id is required to confirm"}
        if finding_id in _adj.confirmed_ids(records):
            ex = _find(lambda r: r.get("record") == _adj.CONFIRM
                       and str(r.get("target")) == finding_id)
            return {"ok": True, "idempotent": True, "verb": verb, "record": ex}
        rec = _adj.make_confirmation(finding_id, node_id=node, kind=kind,
                                     section=section, actor=actor, round=round_no,
                                     project=project)
        append_jsonl(ledger, rec)
        return {"ok": True, "verb": verb, "record": rec}

    if verb == "defer":
        if not finding_id:
            return {"error": "finding_id is required to defer"}
        if finding_id in _adj.deferred_ids(records):
            ex = _find(lambda r: r.get("record") == _adj.DEFER
                       and str(r.get("target")) == finding_id)
            return {"ok": True, "idempotent": True, "verb": verb, "record": ex}
        rec = _adj.make_defer(finding_id, node_id=node, kind=kind, section=section,
                              note=note, actor=actor, round=round_no, project=project)
        append_jsonl(ledger, rec)
        return {"ok": True, "verb": verb, "record": rec}

    if verb == "dismiss":
        if not node or not kind:
            return {"error": "node and kind are required to dismiss"}
        node_text = _node_text_map(md)
        text = node_text.get(node, "")
        cur_fp = _suppress.content_fingerprint(text)
        for s in _suppress.load_suppressions(ledger):
            if _suppress._matches_node_kind(s, node, kind) \
                    and str(s.get("kind")) == kind \
                    and _suppress._supp_fingerprint(s) == cur_fp:
                return {"ok": True, "idempotent": True, "verb": verb, "record": s}
        rec = _suppress.make_suppression(node, kind, text, reason=reason,
                                         actor=actor, round=round_no, project=project,
                                         section=section)
        _suppress.append_suppression(ledger, rec)
        return {"ok": True, "verb": verb, "record": rec}

    if verb == "widen":
        if not node:
            return {"error": "node is required to widen"}
        scope = _widen_scope(md, project, node)
        node_text = _node_text_map(md)
        text = node_text.get(node, "")
        cur_fp = _suppress.content_fingerprint(text)
        for s in _suppress.load_suppressions(ledger):
            if _suppress._finding_node(s) == node \
                    and str(s.get("kind")) == _suppress.WILDCARD \
                    and _suppress._supp_fingerprint(s) == cur_fp:
                return {"ok": True, "idempotent": True, "verb": verb,
                        "record": s, "scope_count": scope}
        rec = _suppress.make_suppression(
            node, _suppress.WILDCARD, text,
            reason=reason or "widen: silence all kinds on the node",
            actor=actor, round=round_no, project=project, section=section)
        _suppress.append_suppression(ledger, rec)
        return {"ok": True, "verb": verb, "record": rec, "scope_count": scope}

    if verb == "scope":
        # THE SCOPE-LATER DOOR (the redline walk's band). Scope is optional at capture
        # and required downstream, so the cheapest deposit — select, Enter, no digit —
        # banks UNSCOPED and stays first-class. This is the reach back to it: an APPEND
        # naming the row and the altitude, never a rewrite of the banked line. The
        # composer's own promise ("scope it later from the band") is only true with a
        # door behind it, so the door exists rather than the sentence being deleted.
        if not finding_id:
            return {"error": "finding_id is required to scope a row"}
        scope_fields, scope_err = _scope_fields(payload)
        if scope_err:
            return {"error": scope_err}
        new_scope = scope_fields.get("scope") or ""
        if not new_scope:
            return {"error": "scope is required to scope a row: this door sets an "
                             f"altitude and never guesses one (one of "
                             f"{list(_schema.FEEDBACK_SCOPES)})"}
        row = next((r for r in _adj.live(records)
                    if r.get("id") == finding_id and not r.get("record")), None)
        if row is None:
            return {"error": f"no live ledger row {finding_id!r} to scope: this door "
                             "addresses a banked deposit by id and mints nothing for an "
                             "id it cannot find",
                    "reason": "no-such-row", "finding_id": finding_id}
        # THE ALTITUDE AS IT NOW READS, not as the banked line spells it. The row's own
        # field never moves (this door appends), so a second scoping must compare against
        # the LATEST scoping record for this id — the same fold `_feedback_findings` does.
        # Comparing the raw field instead made every re-scope to the current altitude
        # append another identical record and read back as a change.
        scopings = [r for r in records
                    if r.get("record") == _adj.SCOPING
                    and str(r.get("target") or "") == finding_id]
        latest = max(scopings, key=lambda r: str(r.get("ts") or "")) if scopings else None
        previous = ((latest or {}).get("scope") or row.get("scope") or "").strip()
        if previous == new_scope:
            # already at that altitude: appending a second identical scoping record
            # would say nothing the ledger does not already say.
            return {"ok": True, "idempotent": True, "verb": verb, "record": None,
                    "finding_id": finding_id, "scope": new_scope,
                    "previous_scope": previous}
        rec = _adj.make_scoping(
            finding_id, new_scope,
            scope_source=scope_fields.get("scope_source") or "chosen",
            previous_scope=previous,
            suggested_scope=(scope_fields.get("suggested_scope")
                             or (row.get("suggested_scope") or "")),
            note=note, kind=row.get("kind") or kind,
            section=(section or row.get("section")
                     or ((row.get("anchor") or {}).get("section")
                         if isinstance(row.get("anchor"), dict) else "") or ""),
            actor=actor, round=round_no, project=project)
        append_jsonl(ledger, rec)
        return {"ok": True, "verb": verb, "record": rec, "finding_id": finding_id,
                "scope": new_scope, "previous_scope": previous,
                "scope_source": rec.get("scope_source"),
                "receipt": {"banked": True, "row_id": rec.get("id"),
                            "target": finding_id, "destination": _rel(ledger),
                            "words": (f"{finding_id} now reads at {new_scope} altitude; "
                                      "the scoping record is an append and the deposit "
                                      "itself is untouched")}}

    if verb == "revoke":
        supp_id = (payload.get("supersedes") or payload.get("suppression_id")
                   or "").strip()
        if not supp_id:
            return {"error": "supersedes (suppression id) is required to revoke"}
        if supp_id not in {s.get("id") for s in _suppress.load_suppressions(ledger)}:
            # not a suppression: it may name a plain LEDGER ROW — a banked comment or
            # the exemplar row the editor-save door mints. The undo door is one verb, so
            # revoke retires that row too, append-only, through the existing superseding
            # resolution record (``adjudicate.make_resolution``). Records carrying their
            # own ``record`` discriminator are excluded: an INTENT has its own withdrawal
            # (revoke-intent) and a suppression was handled above.
            row = next((r for r in _adj.live(records)
                        if r.get("id") == supp_id and not r.get("record")), None)
            if row is None:
                return {"ok": True, "idempotent": True, "verb": verb,
                        "supersedes": supp_id}      # already revoked / unknown -> no-op
            rec = _adj.make_resolution(
                supp_id, verb="revoke", reason=reason, kind=row.get("kind") or "",
                section=(row.get("section")
                         or ((row.get("anchor") or {}).get("section")
                             if isinstance(row.get("anchor"), dict) else "") or ""),
                actor=actor, round=round_no, project=project)
            append_jsonl(ledger, rec)
            return {"ok": True, "verb": verb, "record": rec, "revoked": "ledger-row",
                    "supersedes": supp_id}
        rec = _suppress.make_revocation(supp_id, reason=reason, actor=actor,
                                        round=round_no, project=project)
        append_jsonl(ledger, rec)
        return {"ok": True, "verb": verb, "record": rec}

    if verb == "route-conceptric":
        if not node:
            return {"error": "node is required to route to the conceptric"}
        intent = (payload.get("intent") or "other").strip()
        ex = _find(lambda r: r.get("record") == _adj.CONCEPTRIC_INTENT
                   and (r.get("node") or r.get("node_id")) == node
                   and r.get("intent") == intent
                   and (not finding_id or str(r.get("target")) == finding_id))
        if ex is not None:
            return {"ok": True, "idempotent": True, "verb": verb, "record": ex}
        rec = _adj.make_conceptric_intent(node, intent, note=note,
                                          finding_id=finding_id, kind=kind,
                                          section=section, actor=actor,
                                          round=round_no, project=project)
        append_jsonl(ledger, rec)
        return {"ok": True, "verb": verb, "record": rec}

    if verb == "route-plan":
        # the PLAN door (2026-07-13): a whole-artefact/plan-altitude finding types
        # to the PLAN, not a node — the altitude that owns a CUT / DEMOTE / … of a
        # meta key or a whole section. Mirrors route-conceptric (the one locked
        # door, append-only, idempotent), but keys on the finding + the plan verb +
        # object rather than a node. No node is required (a plan finding may not be
        # node-anchored). Draft-only downstream: the evolution consumer proposes,
        # nothing auto-applies.
        if not finding_id:
            return {"error": "finding_id is required to route to the plan"}
        plan_verb = (payload.get("plan_verb") or "").strip().upper()
        if plan_verb not in _adj.PROJECTION_VERBS:
            return {"error": f"plan_verb must be one of {list(_adj.PROJECTION_VERBS)}"}
        obj = payload.get("object") or {}
        object_kind = (obj.get("kind") or "meta").strip()
        object_key = (obj.get("sid") or obj.get("key") or "").strip()
        finding_kind = (payload.get("finding_kind") or kind).strip()
        ex = _find(lambda r: r.get("record") == _adj.PROJECTION_INTENT
                   and str(r.get("target")) == finding_id
                   and r.get("verb") == plan_verb
                   and (r.get("object") or {}).get("kind") == object_kind
                   and ((r.get("object") or {}).get("sid")
                        or (r.get("object") or {}).get("key") or "") == object_key)
        if ex is not None:
            return {"ok": True, "idempotent": True, "verb": verb, "record": ex}
        rec = _adj.make_projection_intent(
            finding_id, plan_verb, object_kind=object_kind, object_key=object_key,
            note=note, finding_kind=finding_kind, section=section, actor=actor,
            round=round_no, project=project)
        append_jsonl(ledger, rec)
        return {"ok": True, "verb": verb, "record": rec}

    if verb == "calibrate":
        fkind = (payload.get("finding_kind") or kind).strip()
        if not fkind:
            return {"error": "finding_kind is required to calibrate"}
        if fkind in _adj.calibrated_kinds(records):
            ex = _find(lambda r: r.get("record") == _adj.CALIBRATION_INTENT
                       and r.get("finding_kind") == fkind)
            return {"ok": True, "idempotent": True, "verb": verb, "record": ex}
        count = _adj.dismissal_counts(records).get(fkind, 0)
        rec = _adj.make_calibration_intent(fkind, dismissal_count=count, note=note,
                                           actor=actor, round=round_no, project=project)
        append_jsonl(ledger, rec)
        return {"ok": True, "verb": verb, "record": rec}

    if verb == "revoke-intent":
        # the substrate-queue revoke (G-4): supersede an OPEN conceptric/calibration
        # /projection intent so the queued deposit never vanishes silently and can be
        # withdrawn append-only (mirrors the suppression revoke). The projection-intent
        # door (C3.6) gives the AUTHOR the same retire the C3.5 apply path writes
        # programmatically. No-op if already gone.
        intent_id = (payload.get("supersedes") or payload.get("intent_id") or "").strip()
        if not intent_id:
            return {"error": "supersedes (intent id) is required to revoke an intent"}
        live_intent_ids = {r.get("id") for r in _adj.live(records)
                           if r.get("record") in (_adj.CONCEPTRIC_INTENT,
                                                   _adj.CALIBRATION_INTENT,
                                                   _adj.PROJECTION_INTENT)}
        if intent_id not in live_intent_ids:
            return {"ok": True, "idempotent": True, "verb": verb,
                    "supersedes": intent_id}       # already revoked / unknown -> no-op
        rec = _adj.make_intent_revocation(intent_id, reason=reason, actor=actor,
                                          round=round_no, project=project)
        append_jsonl(ledger, rec)
        return {"ok": True, "verb": verb, "record": rec}

    if verb == "edit-in-place":
        # THE TERMINAL RUNG (B4): the author edits the prose by hand. Applying the
        # splice and BANKING the capture are ONE write — capture is the write path,
        # not optional. The splice is refused (structured error, NO ledger record)
        # unless `before` occurs EXACTLY ONCE in the target span; we never guess.
        if not section:
            return {"error": "section is required to edit in place"}
        paragraph = (payload.get("paragraph") or "").strip()
        before = payload.get("before")
        after = payload.get("after")
        if not isinstance(before, str) or not isinstance(after, str):
            return {"error": "before and after (strings) are required to edit in place"}
        if not before:
            return {"error": "before must be non-empty to locate the splice"}
        file = (payload.get("file") or "").strip()
        edit_kind = (payload.get("kind") or "").strip() or "unspecified"
        fp = source_path or _fragment_path(md, section, file)
        if fp is None:
            return {"error": f"cannot resolve fragment for section {section!r}"
                             + (f" / file {file!r}" if file else ""),
                    "reason": "no-fragment", "file": file or section,
                    "section": section, "paragraph": paragraph}
        # the file the refusal names — resolved BEFORE any refusal so every
        # organ refusal below carries file+reason (never a bare error).
        rel_file = file or _rel(fp)
        try:
            raw = fp.read_text(encoding="utf-8")
        except OSError as exc:
            return {"error": f"cannot read fragment {section!r}: {exc}",
                    "reason": "read-failed", "file": rel_file,
                    "section": section, "paragraph": paragraph}
        if paragraph:
            span = _paragraph_char_span(raw, paragraph)
            if span is None:
                return {"error": f"paragraph {paragraph!r} not found in section {section!r}",
                        "reason": "no-paragraph", "file": rel_file,
                        "section": section, "paragraph": paragraph}
            lo, hi = span
        else:
            lo, hi = 0, len(raw)                       # whole-fragment edit
        region = raw[lo:hi]
        count = region.count(before)
        if count != 1:
            return {"error": f"`before` occurs {count} time(s) in the target span; "
                             "the splice requires exactly one",
                    "reason": "absent" if count == 0 else "ambiguous",
                    "count": count, "file": rel_file,
                    "section": section, "paragraph": paragraph}
        abs_start = lo + region.index(before)
        new_raw = raw[:abs_start] + after + raw[abs_start + len(before):]
        # The splice must never mutate the structural comment lines the grain
        # machinery anchors on (% <SEC>-pN / % NODES: / % PLAN:) — an edit that
        # deletes its own paragraph marker silently destroys the very unit its
        # protection record names, and the route then regenerates over the
        # author's hand (the judge proved this end-to-end). Whole-fragment
        # structural lines must be byte-identical before and after.
        if _STRUCT_LINE_RE.findall(raw) != _STRUCT_LINE_RE.findall(new_raw):
            return {"error": "the edit would add, remove, or alter a "
                             "% <SEC>-pN / % NODES: / % PLAN: structural line — "
                             "markers are machine-owned; edit the prose only",
                    "reason": "marker-mutation", "file": rel_file,
                    "section": section, "paragraph": paragraph}
        start_line = raw[:abs_start].count("\n") + 1
        end_line = raw[:abs_start + len(before)].count("\n") + 1
        from laplace.manuscript.projection_viewer import parse_paragraphs
        rec = _edits.make_author_edit(
            section, paragraph, rel_file, before, after, kind=edit_kind,
            lines=[start_line, end_line], round=round_no, project=project,
            actor=actor, spec_ids=list(dict.fromkeys(ident
                for span in parse_paragraphs(raw)
                if span["start_line"] <= end_line and start_line <= span["end_line"]
                for ident in span["spec_ids"])))
        # CRASH-SAFE ordering (C1): STAGE the spliced bytes to a temp sibling,
        # BANK the protection record, THEN atomically swap the fragment into
        # place. Apply now happens strictly AFTER the bank, and the swap is a
        # single atomic rename — so a hard kill can only ever leave a
        # banked-but-unapplied edit (benign over-protection: the paragraph is
        # simply held at its pre-edit bytes and a re-issue completes it), NEVER
        # the old write-then-bank hazard of a spliced-but-unbanked hand edit that
        # the route could regenerate over (the author's hand silently lost).
        try:
            from laplace.manuscript.manuscript_source import stage_source
            tmp = stage_source(fp, new_raw.encode("utf-8"), suffix=".editswap")
        except OSError as exc:
            return {"error": f"cannot stage fragment write {section!r}: {exc}"}
        append_jsonl(ledger, rec)                  # bank BEFORE the apply-swap
        try:
            from laplace.manuscript.source_effects import publish
            publish(tmp, fp)  # atomic, after the required protection record
        except OSError as exc:
            # banked but not swapped: benign over-protection. Surface it loud so
            # the caller can re-issue; the protection record already holds.
            try:
                tmp.unlink()
            except OSError:
                pass
            return {"error": f"edit banked but fragment swap failed {section!r}: {exc}",
                    "reason": "swap-failed", "record": rec,
                    "applied": None}
        if source_changes is not None:
            source_changes.append((fp, raw, new_raw))
        return {"ok": True, "verb": verb, "record": rec,
                "applied": {"section": section, "paragraph": paragraph,
                            "file": rel_file, "lines": [start_line, end_line]}}

    if verb == "rewrite":
        # THE REWRITE DOOR (DESIGN_2026-08-10 §"The block model" / §"The rewrite-first
        # composer"): the author's dominant gesture. He selects a block on the walk's
        # content-faithful canvas, types over it, and Enter banks. The canvas hands the
        # deposit the block's PROVENANCE ({file, line_start, line_end}) and the verbatim
        # source it rendered from, so this door needs no fuzzy quote match:
        #
        #   1. THE BYTE GUARD — the lines still on disk must equal `before` EXACTLY. The
        #      canvas and this door split the file the same way (``raw.split("\n")``), so
        #      the comparison is an identity, not a heuristic.
        #   2. THE SPLICE — those lines become `after`, staged and swapped atomically.
        #   3. THE VERSION — banked through the ONE editor-save store
        #      (``projection_viewer.bank_editor_save``), so a walk rewrite joins the same
        #      version rail the editor pane's saves join, diffable and restorable.
        #   4. THE ROW — one feedback row, kind ``author-rewrite`` (the SAME kind the
        #      exemplar door banks, so the calibration pool consumes it with no adapter),
        #      COMPOUND when a `note` rides along: replacement prose + the rationale, which
        #      is the calibration-gold shape. Scope defaults to ``sentence`` AND says so
        #      (``scope_source="default"``) — never disguised as an altitude he chose.
        #   5. THE RECEIPT — row id, version id, destination, in plain outcome words, so
        #      the echo law is served from the server's own truth.
        #
        # A BYTE MISMATCH NEVER GUESSES. It banks a ``pending-rewrite`` row carrying his
        # before and after and says so in words; the fix pass applies it. The deposit is
        # never lost and the file is never edited on a guess.
        file = (payload.get("file") or "").strip()
        if not file:
            return {"error": "file is required to rewrite: the walk addresses a block by "
                             "its source provenance, and this door never guesses one"}
        # `before_content` is the grammar's uniform spelling of a TEXT guard
        # (`writing_verbs.CARRIERS["text"]`, GRAMMAR.md section 2). It is also the key this
        # door's own refusal serves the current span under, so a caller's retry is literally
        # `{**request, **refused.needed}` --- one spelling of the bytes, in and out. `before`
        # remains the owner's spelling and every existing caller is untouched.
        before = payload.get("before_content")
        if not isinstance(before, str):
            before = payload.get("before")
        after = payload.get("after")
        if not isinstance(before, str) or not isinstance(after, str):
            return {"error": "before and after (strings) are required to rewrite"}
        if not before.strip():
            return {"error": "before must be non-empty: it is the byte guard"}
        try:
            line_start = int(payload.get("line_start") or 0)
            line_end = int(payload.get("line_end") or 0)
        except (TypeError, ValueError):
            return {"error": "line_start and line_end must be integers"}
        if line_start < 1 or line_end < line_start:
            return {"error": "line_start and line_end must be a 1-based inclusive span "
                             "with line_start <= line_end"}
        scope_fields, scope_err = _scope_fields(payload)
        if scope_err:
            return {"error": scope_err}
        if not scope_fields.get("scope"):
            # the door's own default, SAID: `scope_source` distinguishes it from a digit he
            # pressed, so the override rate stays derivable from the ledger alone.
            scope_fields["scope"] = _REWRITE_DEFAULT_SCOPE
            scope_fields["scope_source"] = _REWRITE_DEFAULT_SCOPE_SOURCE
        fp = source_path or _fragment_path(md, section, file)
        if fp is None:
            return {"error": f"cannot resolve fragment {file!r} inside the manuscript",
                    "reason": "no-fragment", "file": file, "section": section}
        rel_file = _fragment_rel(md, fp)
        paragraph = (payload.get("paragraph") or "").strip()
        block = (payload.get("block") or payload.get("block_id") or "").strip()
        try:
            raw = fp.read_text(encoding="utf-8")
        except OSError as exc:
            return {"error": f"cannot read fragment {rel_file}: {exc}",
                    "reason": "read-failed", "file": rel_file, "section": section}
        from laplace.manuscript import manuscript_bridge as _mb

        # the anchor every row on this door carries — the provenance the gesture named,
        # plus his own before/after, so the row is self-sufficient for a later applier.
        # THE PASSAGE, when the gesture had one. `before`/`after` are the SOURCE at the
        # block's line span — the byte guard. `passage_before`/`passage_after` are the
        # words he actually selected and typed over, in his reading register: the walk's
        # composer sends both, so the banked row keeps the (before, after) pair at the
        # grain of his gesture and the calibration pool reads a sentence-level sample
        # rather than a whole-block diff. Absent (the block-flip door, a machine caller)
        # the anchor simply carries the source pair, exactly as before.
        passage_before = payload.get("passage_before")
        passage_after = payload.get("passage_after")
        # THE VERIFIED SOURCE IDENTITY, RETAINED. `fp` is the physical path this door
        # validated and leased; `rel_file` is its manuscript-relative spelling, the
        # addressing vocabulary the block model shares. A row that kept only `rel_file`
        # left History to guess which checkout file a basename meant (an UNPROVED target
        # even for a save made a minute ago, root B1/B6 2026-10-12). The checkout-relative
        # path is banked beside it, on applied and pending rows alike, and only when the
        # validated path really lies inside the checkout; it is never inferred for old rows.
        try:
            repo_file = fp.resolve().relative_to(owning_root).as_posix()
        except (ValueError, OSError):
            repo_file = None

        def _anchor(grade: str, **extra) -> dict:
            a = {"section": section, "paragraph_id": paragraph, "file": rel_file,
                 "lines": [line_start, line_end], "grade": grade,
                 "quote": before, "before": before, "after": after,
                 "coarse": False}
            if repo_file:
                a["repo_file"] = repo_file
            if isinstance(passage_before, str) and passage_before.strip():
                a["passage_before"] = passage_before
                a["quote"] = passage_before
            if isinstance(passage_after, str):
                a["passage_after"] = passage_after
            if block:
                a["block"] = block
            a.update(extra)
            return a

        intent = _rewrite_retry_intent(project,md,actor,_anchor("rewrite"),note,reason,
                                       payload.get("source"),scope_fields)
        retry = payload.get("rewrite_retry")
        if "rewrite_retry" in payload:
            retry_error = _rewrite_retry_check(records,retry,intent,project,actor)
            if retry_error:return {"error":retry_error,"reason":"rewrite-retry-refused"}

        lines = raw.split("\n")                 # the canvas's own split — one producer
        current = "\n".join(lines[line_start - 1:line_end]) \
            if line_end <= len(lines) else None

        # The `prose` home: the exact bytes of the addressed span, whole lines.  This door
        # compared the span's TEXT against the caller's `before` and then banked a pending
        # rewrite whose receipt said which file and which lines but never which identity, so
        # the four open `pending-rewrite` rows carry no value a caller can retry with.  The
        # comparison is now the same one every other door makes -- `grammar.require` over a
        # token of the span's bytes, equal exactly when the texts are equal -- and the
        # refusal it produces travels into the pending receipt below as `refused`, with the
        # span's CURRENT token.  The decision itself is unchanged, so replay sees the same
        # applied/pending split.
        stale = None
        if current is not None:
            try:
                identity_doors.gate(
                    # The payload, with the RESOLVED byte guard: `before` is the owner's own
                    # spelling and `before_content` is the grammar's carrier for the same
                    # bytes, so the gate is handed the one value both names mean and a
                    # `prose` token in `expected` reaches it unchanged.
                    "apply_revision", supplied={**payload, "before": before},
                    homes=[("prose", "%s::%s:%d-%d" % (project, rel_file, line_start, line_end),
                            current.encode("utf-8"))],
                    required=["before"], bytes_guards=["before"],
                    said=(f"the source at {rel_file}:{line_start}-{line_end} is no longer the "
                          "text you edited"))
            except identity_doors.IdentityRefused as refused:
                stale = refused

        # ── THE SERVED RETRY, AND THE CLOBBER IT PREVENTS (WRITING-CONSOLIDATION-W1) ─────
        # `expected` opens a second way through the gate: a caller holding the CURRENT `prose`
        # token passes without its `before` text being compared at all (that is what a token
        # is for, and `identity_doors.gate` skips a guard whose home is already covered). So
        # from the moment this door accepts tokens there is a state it never had before --- the
        # identity is current and the TEXT is not --- and splicing the caller's `after` over
        # the current span in that state would overwrite bytes it never read. That is the one
        # thing the author's standing rule forbids.
        #
        # It needs no marker field, which is the point: the state IS the condition. The caller
        # is retrying with what this door's own `needed` served it (the current token and the
        # current bytes), so the thing to apply is the author's OWN passage ---
        # `passage_before` -> `passage_after`, the pair the walk's composer already sends ---
        # re-spliced into the bytes THIS DOOR reads now. 90 of the author's 129 ledger rows are
        # whole-file `author-rewrite` pairs and four `pending-rewrite` rows are open with no
        # value a caller could retry with; this is what closes them without a bigger row.
        #
        # And it refuses rather than guesses in the one case that matters: a passage that does
        # not occur exactly once in the current span cannot be placed, so nothing is written.
        # `state-not-reached` is the grammar's kind for a refusal a fresher token cannot cure,
        # and this is one --- the identity is already current and the passage still has
        # nowhere to go, so the resolver is a different read, not a newer token.
        superseded = None
        inserted_at = None
        if _author_editor_write(payload) and (current is None or stale is not None or before != current):
            # THE AUTHOR'S OWN EDIT (wave 14a): applied over the span as it is NOW. A span that moved is
            # found again by its exact bytes; otherwise the bytes at his span are replaced and kept in the
            # applied row as `superseded`. No identity refusal, no pending row and no merge refusal for
            # him; the only refusal left is a span that cannot be located at all (out of range).
            # Located by its exact bytes first, then by its paragraph id or its words (_author_paragraph),
            # never by his line numbers alone: text that now stands at those lines may be someone else's.
            moved = _relocated_span(lines, before) if before != current else None
            if moved is not None:
                line_start, line_end = moved
                current = before
            elif before != current:
                found = _author_paragraph(lines, before, _walk_paragraph_id(payload), line_start)
                if found is None and payload.get("placement") == "insert":
                    # HIS PARAGRAPH PUT BACK (wave 14b, the record's item 1): nothing in the file locates
                    # it, he pressed Keep my text and save it after this door said so, and his paragraph
                    # goes back at its own place as a paragraph of its own. Nothing is overwritten, so
                    # nothing is superseded; the applied row records `placement: inserted` and his basis.
                    inserted_at = _insertion_line(lines, line_start)
                    found = (inserted_at, inserted_at + after.count("\n"))
                if found is None:
                    return {"error": "your paragraph at %s:%d-%d could not be located in the file any more, so "
                                     "nothing was written; your text is kept in the editor" % (rel_file, line_start, line_end),
                            "reason": "passage-not-located",
                            "refused": {"kind": "unknown-home", "homes": [],
                                        "needed": {"read": "GET /walk/doc", "until": "the paragraph is placed again"},
                                        "said": "neither its bytes, its paragraph id nor its words locate one paragraph of the file"},
                            "file": rel_file, "section": section, "lines": [line_start, line_end]}
                line_start, line_end = found
                if inserted_at is not None:
                    current = before        # nothing in the file is replaced; his basis stays on the row
                else:
                    current = "\n".join(lines[line_start - 1:line_end])
                    if before != current:
                        superseded = current
            stale = None
            before = current
        if current is not None and stale is None and before != current:
            merged = _merge_edits(before, after, current)
            if merged is None:
                return {"error": "the source at %s:%d-%d changed where you were editing, so "
                                 "nothing was written: your edit and the other one touch the "
                                 "same characters" % (rel_file, line_start, line_end),
                        "refused": {
                            "kind": "state-not-reached", "homes": [],
                            "needed": {"read": "GET /review/fragment {section, paragraph}",
                                       "until": "your edit and the span's own change do not "
                                                "touch the same characters"},
                            "said": "a request carrying the current identity and different "
                                    "text has its own edit replayed onto the current bytes; "
                                    "two edits over one region cannot both be meant, so this "
                                    "door writes neither"},
                        "file": rel_file, "section": section,
                        "lines": [line_start, line_end]}
            before, after = current, merged
        if current is None or stale is not None:
            # THE PENDING PATH — said in words, never a guess and never a lost deposit.
            found = "" if current is None else current
            words = (f"the source at {rel_file}:{line_start}-{line_end} is no longer the "
                     "text you edited, so nothing was spliced; your replacement is banked "
                     "as a pending rewrite and the fix pass applies it")
            res = _mb.feedback_add(owning_root, project, {
                "node_id": section or rel_file, "kind": _PENDING_REWRITE_KIND,
                "comment": note or words,
                "anchor": _anchor("rewrite", pending=True, found=found,
                                  out_of_range=current is None,rewrite_intent_sha256=intent),
                "by": actor, **scope_fields}, ledger=ledger)
            if not res.get("ok"):
                return {"error": res.get("error")
                        or "the pending rewrite could not be banked"}
            rec = res.get("record") or {}
            return {"ok": True, "verb": verb, "pending": True, "applied": None,
                    "record": rec, "compound": bool(note),
                    "receipt": {"banked": True, "pending": True,
                                "row_id": rec.get("id"), "version_id": None,
                                "rewrite_retry":{"schema_version":_REWRITE_RETRY_SCHEMA,
                                                 "pending_id":rec.get("id"),"intent_sha256":intent},
                                "file": rel_file, "lines": [line_start, line_end],
                                "destination": _rel(ledger), "words": words,
                                # The identity the pending row was banked against, so the row
                                # can be retired by a caller that retries with
                                # `{**request, **refused.needed}` and nothing else.
                                #
                                # AND NOT THE BYTES, WHICH IS A RULING, NOT AN OMISSION. An
                                # earlier version of this packet served the current span here
                                # as `before_content`, on the grammar's own argument that a
                                # TEXT guard has no token to serve. The browser proof then
                                # showed what that buys: the retry arrives with `before` EQUAL
                                # to the current span, the byte guard is satisfied, and the
                                # caller's `after` --- computed against bytes that are gone ---
                                # is spliced over another writer's sentence. Measured: the
                                # other writer's line was lost
                                # (wave1/editor-doors/proof, step `no_clobber`).
                                #
                                # So this door serves the TOKEN and the READ, and nothing a
                                # mechanical retry can use to overwrite: with its own `before`
                                # still stale, the retry takes the re-splice branch above and
                                # the author's passage is placed into the bytes that are there
                                # now. A caller with no passage to place is told which read
                                # serves the span (`homes[].read`) and has to decide what its
                                # replacement should be, which is the honest requirement ---
                                # nobody can splice on its behalf.
                                **({"refused": stale.refused}
                                   if stale is not None else {})},
                    **scope_fields}

        if inserted_at is not None:
            new_lines, line_start = _with_inserted_paragraph(lines, inserted_at, after.split("\n"))
            line_end = line_start + after.count("\n")
        else:
            new_lines = lines[:line_start - 1] + after.split("\n") + lines[line_end:]
        new_raw = "\n".join(new_lines)
        if _STRUCT_LINE_RE.findall(raw) != _STRUCT_LINE_RE.findall(new_raw):
            return {"error": "the rewrite would add, remove, or alter a "
                             "% <SEC>-pN / % NODES: / % PLAN: structural line — "
                             "markers are machine-owned; rewrite the prose only",
                    "reason": "marker-mutation", "file": rel_file,
                    "section": section, "paragraph": paragraph}
        data = new_raw.encode("utf-8")
        # CRASH-SAFE ordering, the edit-in-place idiom exactly: STAGE the spliced bytes,
        # BANK the row, THEN swap. A hard kill can only ever leave a banked-but-unapplied
        # rewrite (benign: re-issuing completes it), never a spliced-but-unbanked one.
        try:
            from laplace.manuscript.manuscript_source import stage_source
            tmp = stage_source(fp, data, suffix=".rewriteswap")
        except OSError as exc:
            return {"error": f"cannot stage the rewrite of {rel_file}: {exc}",
                    "reason": "stage-failed", "file": rel_file}
        words = ((f"put your paragraph back at {rel_file}:{line_start}-{line_end}" if inserted_at is not None
                  else f"rewrote {rel_file}:{line_start}-{line_end}")
                 + (" with your note" if note else ""))
        res = _mb.feedback_add(owning_root, project, {
            "node_id": section or rel_file, "kind": _REWRITE_KIND,
            "comment": note or words,
            "anchor": _anchor("rewrite", applied=True, compound=bool(note),
                                  **({"rewrite_retry":dict(retry)} if retry else {}),
                                  **({"superseded": superseded} if superseded is not None else {}),
                                  **({"placement": "inserted", "before": "", "basis": before}
                                     if inserted_at is not None else {})),
            "by": actor, **scope_fields}, ledger=ledger)
        if not res.get("ok"):
            try:
                tmp.unlink()
            except OSError:
                pass
            return {"error": res.get("error") or "the rewrite row could not be banked",
                    "reason": "bank-failed", "file": rel_file}
        rec = res.get("record") or {}
        try:
            from laplace.manuscript.source_effects import publish
            publish(tmp, fp)  # atomic, after the required source feedback record
        except OSError as exc:
            try:
                tmp.unlink()
            except OSError:
                pass
            return {"error": f"rewrite banked but the fragment swap failed "
                             f"({rel_file}): {exc}",
                    "reason": "swap-failed", "record": rec, "applied": None}
        if source_changes is not None:
            source_changes.append((fp, raw, new_raw))
        version_id, version_note = None, ""
        try:
            from laplace.manuscript import projection_viewer as _pv
            version_id = _pv.bank_editor_save(md, fp, data, author=actor,
                                              surface="walk", source="rewrite"
                                              )["version_id"]
        except Exception as exc:                # noqa: BLE001 — the splice already landed
            version_note = (f"the rewrite applied, but the version store refused it "
                            f"({exc}); the row and the file both hold")
        receipt = {"banked": True, "pending": False, "row_id": rec.get("id"),
                   "version_id": version_id, "file": rel_file,
                   "lines": [line_start, line_end], "destination": _rel(ledger),
                   "compound": bool(note),
                   **({"superseded": superseded} if superseded is not None else {}),
                   **({"inserted": True} if inserted_at is not None else {}),
                   "words": (f"{words} — banked as {rec.get('id')}"
                             + (f", version {version_id}" if version_id else "")
                             + f", in {_rel(ledger)}")}
        if retry:
            # Settlement is after the source swap. Failure cannot revoke the effect
            # ACK or invite a repeat; the exact pending ID stays inspectable.
            settlement={"schema_version":_REWRITE_RETRY_SCHEMA,"pending_id":retry["pending_id"],
                        "applied_record_id":rec.get("id"),"status":"UNRESOLVED"}
            try:
                if not isinstance(rec.get("id"),str) or not rec["id"]:
                    raise ValueError("successful rewrite has no exact applied feedback ID")
                resolved=_mb.feedback_resolve(owning_root,project,retry["pending_id"],
                    ledger=ledger,by=actor,expected_status="open",applied_record_id=rec.get("id"),
                    note="Exact served retry applied as "+str(rec.get("id")))
                if not resolved.get("ok"):raise ValueError(resolved.get("error") or "pending status was not resolved")
                settlement["status"]="RESOLVED"
            except Exception as exc:  # Source applied; status maintenance is separate.
                settlement["reason"]=str(exc)
                receipt["retry_warning"]="Rewrite applied; pending "+retry["pending_id"]+" could not resolve: "+str(exc)+". Inspect it; do not repeat the source effect."
                receipt["words"] += " — " + receipt["retry_warning"]
            receipt["retry_settlement"]=settlement
        if version_note:
            receipt["version_note"] = version_note
        return {"ok": True, "verb": verb, "pending": False, "record": rec,
                "compound": bool(note), "version_id": version_id,
                "applied": {"section": section, "paragraph": paragraph,
                            "file": rel_file, "lines": [line_start, line_end],
                            "block": block},
                "receipt": receipt, **scope_fields}

    if verb == "comment":
        # COMMENT-ANYWHERE (B13.3 + B13.5): a free-text page comment banked through the
        # EXISTING feedback door (:func:`manuscript_bridge.feedback_add`) — the SAME
        # ledger, the SAME record shape the node-precise notes ride. Every comment carries
        # an explicit ANCHOR GRADE so the surface never pretends a coarse anchor is
        # node-precise. Six honest tiers, in precedence:
        #   artefact — the whole-paper deposit (the redline walk's `0` key): anchor grade
        #             'artefact' (or 'handover'), matching his own highest-value rows.
        #             No local anchor is invented for a structural thought.
        #   span    — a span-select across spine section rows: anchor grade 'span'
        #             carrying the section list. Never a node anchor.
        #   figure  — the selection sits on a `fig:` labelled block (its region or its
        #             caption). Banked as the F31-consumed 'figure-standard' review kind,
        #             keyed by the figure's label. The re-authoring session runs off
        #             exactly these figure-standard-kind comments (B13.5).
        #   node    — the selection lands on a nodemap node (paragraph/float/equation).
        #   section — no node under it, resolved to the section beat (coarse, marked).
        #   region  — NO nodemap anchor at all (margin, whitespace, the PDF pane, an
        #             unmapped figure): banked HONESTLY as region-grade {page, rect,
        #             nearest section} rather than a fabricated node anchor (B13.3). The
        #             map's law: an honest region bank beats a wrong node anchor.
        #
        # THE ALTITUDE FIELDS: `scope` (one of the six), `scope_source`, and
        # `suggested_scope` are each OPTIONAL. Absent scope banks UNSCOPED — first-class,
        # not a defect: scope is required downstream, optional at capture, and the door
        # never guesses one. Present values are validated here (the gesture door) and
        # persisted by ``feedback_add``; a value outside the vocabulary is refused rather
        # than banked as an altitude no consumer can group by.
        text = (payload.get("comment") or note or "").strip()
        scope_fields, scope_err = _scope_fields(payload)
        if scope_err:
            return {"error": scope_err}
        # ── THE RULING AND ITS GATE (WRITING-CONSOLIDATION-W1) ──────────────────────────
        # `create note@<altitude>`: the ruling is specialisation and lives in the payload,
        # and the gate is the CONTAINER's token --- the passage being ruled on. Three things
        # follow and each is stated rather than hoped:
        #   * a stale ruling is REFUSED with `needed`, not banked against a passage that has
        #     already moved (the author would be ruling on text he never read);
        #   * a caller that sends no token banks exactly as it does today, so every existing
        #     caller (the artefact panes, the walk's own comment path before this build) is
        #     unchanged and differential replay over the recorded corpus is untouched;
        #   * the refusal is `grammar.require`'s, so `needed` exists on this path by
        #     construction and cannot be dropped at the formatter.
        ruling, ruling_err = _ruling_fields(payload)
        if ruling_err:
            return {"error": ruling_err}
        # The altitude is derived ONLY for a request that is doing something with it: a ruling,
        # a named altitude, or a token to compare. A caller that knows nothing about this
        # packet banks the row it has always banked, byte for byte --- proved as a measurement
        # in `tests/test_editor_doors.py` rather than claimed here --- which is also why the
        # recorded corpus replays unchanged through this branch.
        # NO `altitude_source` (WRITING-CONSOLIDATION-W1, the synthesis's stored-key audit).
        # The editor-doors lane banked one beside the altitude, by analogy with
        # `scope_source`. It had no reader in the product --- only an assertion in its own
        # test --- and it did not record what it was described as recording: the editor's own
        # gesture NAMES an altitude on every comment it sends (`walk.mjs`'s `commentRequest`
        # puts it in the concept), so the field read `named` on every row the one caller that
        # matters produces. A stored key with no reader whose value is reproducible from the
        # row's own `altitude`, `file`, `line_start`/`line_end` and `section` by this very
        # function is a key the campaign's rule removes rather than keeps. `_comment_altitude`
        # no longer computes it either: a key nobody stores needs no producer.
        altitude = (_comment_altitude(payload, ruling)
                    if (ruling or payload.get("expected")) else "")
        if altitude:
            ruling["altitude"] = altitude
        container = _container_home(md, project, altitude, payload, section) \
            if altitude else None
        if container is None and payload.get("expected"):
            # The caller holds a token for a home this gesture does not address. Saying so is
            # the point: `unknown-home` is the grammar's own kind for it, and the refusal
            # names the altitude the door resolved so the caller can see WHY.
            return {"error": "this comment addresses no single passage, so there is no "
                             "container identity to compare",
                    "refused": {"kind": "unknown-home", "homes": [],
                                "needed": {"expected": [],
                                           "unresolved": [str(altitude or "(no altitude)")]},
                                "said": "a keep/cut ruling at paragraph, section or chapter "
                                        "altitude names a file and (at paragraph altitude) a "
                                        "line span; a whole-paper or span deposit has no one "
                                        "container"}}
        if container is not None:
            try:
                identity_doors.gate(
                    "comment@" + altitude, supplied=payload, homes=[container],
                    said=("the %s you are ruling on is no longer the text you read"
                          % altitude))
            except identity_doors.IdentityRefused as refused:
                return {"error": str(refused), "refused": refused.refused, **ruling}
        # the anchor snapshot's context, frozen at the moment of the gesture (see
        # :func:`_context_fields`). Rides the anchor of every tier that carries a quote.
        ctx_fields = _context_fields(payload)
        if not text and not payload.get("mark_only"):
            return {"error": "comment text is required"}
        if not text:
            # THE ZERO-TEXT PATH: selection + Enter with an empty body banks a
            # mark-only deposit (most real annotation is wordless). The ledger door
            # requires a comment string, so the mark says what it is in plain words
            # rather than banking an empty row that reads as a lost comment.
            text = _MARK_ONLY_TEXT
        paragraph = (payload.get("paragraph") or "").strip()
        quote = (payload.get("quote") or "").strip()
        coarse = bool(payload.get("coarse"))
        page = payload.get("page")
        region = payload.get("region")
        figure = (payload.get("figure") or "").strip()
        # the provenance-pane enrichment: a comment banked AT a rendered object (a tex
        # label, an asset id, a paragraph spec) carries that object ref on its anchor, so
        # the ledger row records exactly what the reader was looking at (node_id + anchor).
        obj_ref = (payload.get("object") or "").strip()
        # the LINE-PRECISE anchor (his commission): a comment left on a line of the projected
        # artefact carries the synctex-resolved source file+line (the SAME join the follow
        # feature uses), so the anchor points at exactly where on the paper it was provoked.
        src_file = (payload.get("source_file") or "").strip()
        src_line = payload.get("source_line")
        try:
            src_line = int(src_line) if src_line not in (None, "") else None
        except (TypeError, ValueError):
            src_line = None
        # THE BLOCK-PRECISE PROVENANCE, when the caller has it. The redline walk addresses
        # a content-faithful BLOCK ("<fragment>#<paragraph-id>") over a line SPAN, not a
        # single line; both ride the anchor so a later reader can go straight back to the
        # bytes he was looking at. Each is written ONLY when supplied, so every existing
        # caller mints exactly the anchor shape it already gets.
        src_block = (payload.get("block") or payload.get("block_id") or "").strip()
        src_line_end = payload.get("line_end")
        try:
            src_line_end = int(src_line_end) if src_line_end not in (None, "") else None
        except (TypeError, ValueError):
            src_line_end = None
        prov_fields: dict[str, Any] = {}
        if src_block:
            prov_fields["block"] = src_block
        if src_line is not None and src_line_end is not None \
                and src_line_end >= src_line:
            prov_fields["source_lines"] = [src_line, src_line_end]
        # THE RULING RIDES THE ANCHOR, ON THE EXISTING ROW KIND. `kind` stays `comment`
        # (`figure-standard` on the figure tier) and no stored key is added at the top level:
        # a keep/cut ruling is a property of the anchored passage, and the anchor is where
        # this ledger already keeps a gesture's own provenance (grade, lines, block, applied,
        # pending). A new row kind would partition the author's ledger in two and every
        # existing consumer --- the board, the live view, the corrections projection, his own
        # calibration pool --- would read only half of it.
        if 'spec_ids' in payload:
            spec_ids = payload['spec_ids']
            if (not isinstance(spec_ids, list) or not 1 <= len(spec_ids) <= 32
                    or any(not isinstance(ident, str) or not ident for ident in spec_ids)
                    or len(set(spec_ids)) != len(spec_ids)):
                return {'error': 'spec_ids must be 1..32 distinct observed logical paragraph IDs.'}
            exact_file = src_file or str(payload.get('file') or '')
            low, high = src_line or payload.get('line_start'), src_line_end or payload.get('line_end')
            physical = _fragment_path(md, section, exact_file) if exact_file else None
            if physical is None or not isinstance(low, int) or not isinstance(high, int) or low < 1 or high < low:
                return {'error': 'Logical paragraph attachments require an exact observed physical file and line range.'}
            from laplace.manuscript.projection_viewer import parse_paragraphs
            spans = [span for span in parse_paragraphs(physical.read_bytes().decode('utf-8'))
                     if span['start_line'] <= high and low <= span['end_line']]
            observed_ids = list(dict.fromkeys(ident for span in spans for ident in span['spec_ids']))
            if paragraph and paragraph not in spec_ids:
                return {'error': 'The scalar paragraph attachment must belong to the complete observed spec_ids set.'}
            if observed_ids != spec_ids:
                return {'error': 'Paragraph occurrence changed; inspect its current source before attaching this comment.', 'code': 'CHANGED_INPUT'}
            source_sections = set(span['section'] for span in spans)
            if payload.get('source_section') is not None and source_sections != {payload['source_section']}:
                return {'error': 'The supplied physical section does not match the observed source occurrence.', 'code': 'CHANGED_INPUT'}
            prov_fields['spec_ids'] = spec_ids
            if len(source_sections) == 1:
                prov_fields['source_section'] = next(iter(source_sections))
        prov_fields.update(ruling)
        from laplace.manuscript import manuscript_bridge as _mb

        # ── artefact tier — the whole-paper deposit (no local anchor exists) ──────────
        # Forcing a local anchor on a structural thought is the failure this closes: the
        # deposit is banked at ARTEFACT grade (or HANDOVER, the delivery-boundary grade
        # his own gm-009 row uses), keyed by a pseudo id that is not node-shaped, so no
        # consumer can mistake it for a conceptric node.
        artefact_grade = _artefact_grade(payload)
        if artefact_grade:
            anchor = {"section": section, "quote": quote, "grade": artefact_grade,
                      "coarse": True, **ruling}
            if page is not None:
                anchor["page"] = page
            if obj_ref:
                anchor["object"] = obj_ref
            res = _mb.feedback_add(owning_root, project, {
                "node_id": _ARTEFACT_PSEUDO_ID[artefact_grade],
                "kind": kind or "comment", "comment": text,
                "anchor": anchor, "by": actor, **scope_fields}, ledger=ledger)
            if not res.get("ok"):
                return {"error": res.get("error")
                        or f"{artefact_grade} comment could not be banked"}
            return {"ok": True, "verb": verb, "record": res.get("record"),
                    "grade": artefact_grade, "coarse": True, **scope_fields}

        # ── span tier — a span-select across spine section rows (structural deposits) ──
        # The anchor names the sections it spans, honestly graded "span": several
        # sections is not one node, and the spine IS the structural surface.
        span_sections, span_err = _span_sections(payload)
        if span_err:
            return {"error": span_err}
        if span_sections:
            anchor = {"section": section or span_sections[0], "sections": span_sections,
                      "quote": quote, "grade": "span", "coarse": True, **ruling}
            if page is not None:
                anchor["page"] = page
            res = _mb.feedback_add(owning_root, project, {
                "node_id": "span:" + "+".join(span_sections),
                "kind": kind or "comment", "comment": text,
                "anchor": anchor, "by": actor, **scope_fields}, ledger=ledger)
            if not res.get("ok"):
                return {"error": res.get("error") or "span comment could not be banked"}
            return {"ok": True, "verb": verb, "record": res.get("record"),
                    "grade": "span", "sections": span_sections, "coarse": True,
                    **scope_fields}

        # ── figure tier — a `fig:` block (explicit affordance, or a fig-labelled node) ──
        fig_label = ""
        if figure:
            fig_label = figure if figure.startswith("fig:") else "fig:" + figure
        elif node.startswith("fig:"):
            fig_label = node
        if fig_label:
            anchor = {"section": section, "figure": fig_label, "quote": quote,
                      "grade": "figure", "coarse": coarse, "page": page,
                      **ctx_fields, **prov_fields}
            if src_file:
                anchor["source_file"] = src_file
            if src_line is not None:
                anchor["source_line"] = src_line
            if obj_ref:
                anchor["object"] = obj_ref
            res = _mb.feedback_add(owning_root, project, {
                "node_id": fig_label, "kind": "figure-standard", "comment": text,
                "anchor": anchor, "by": actor, **scope_fields}, ledger=ledger)
            if not res.get("ok"):
                return {"error": res.get("error") or "figure comment could not be banked"}
            return {"ok": True, "verb": verb, "record": res.get("record"),
                    "grade": "figure", "review_kind": "figure-standard",
                    "figure": fig_label, **scope_fields}

        # ── node / paragraph / section tier — precise anchor, or the section beat ──
        # node_id precedence mirrors the surface: a real conceptric node when the
        # selection lands on one, else the SECTION (a prose paragraph is section-keyed
        # with its precise pid riding the anchor), else the paragraph id. The GRADE names
        # the true precision so the surface never shows a coarse beat as node-precise.
        anchor_node = node or section or paragraph or obj_ref
        if anchor_node:
            if node:
                grade = "node"                       # a real conceptric node id
            elif paragraph and not coarse:
                grade = "paragraph"                  # a precise paragraph pid (keyed by section)
            elif section:
                grade = "section"                    # the coarse section beat
            else:
                grade = "object"                     # keyed only by the provenance object ref
            anchor = {"section": section, "paragraph_id": paragraph,
                      "quote": quote, "coarse": coarse, "grade": grade,
                      **ctx_fields, **prov_fields}
            if obj_ref:
                anchor["object"] = obj_ref
            if page is not None:
                anchor["page"] = page
            if src_file:
                anchor["source_file"] = src_file
            if src_line is not None:
                anchor["source_line"] = src_line
            res = _mb.feedback_add(owning_root, project, {
                "node_id": anchor_node, "kind": "comment", "comment": text,
                "anchor": anchor, "by": actor, **scope_fields}, ledger=ledger)
            if not res.get("ok"):
                return {"error": res.get("error") or "comment could not be banked"}
            return {"ok": True, "verb": verb, "record": res.get("record"),
                    "grade": grade, "coarse": coarse, **scope_fields}

        # ── region tier — no nodemap anchor: bank the page region, honestly coarse ──
        if isinstance(region, dict):
            rp = region.get("page") if region.get("page") is not None else page
            rect = {k: region.get(k) for k in ("page", "x0", "y0", "x1", "y1")}
            if rect.get("page") is None and rp is not None:
                rect["page"] = rp
            # a non-empty node_id is required by the door; with no section the honest key
            # is a page-region pseudo-id (region:p<page>), NEVER a fabricated node id.
            pseudo = "region:p" + str(rp) if rp not in (None, "") else "region:page"
            anchor = {"section": section, "region": rect, "page": rp,
                      "quote": quote, "grade": "region", "coarse": True,
                      **ctx_fields, **ruling}
            res = _mb.feedback_add(owning_root, project, {
                "node_id": section or pseudo, "kind": "comment", "comment": text,
                "anchor": anchor, "by": actor, **scope_fields}, ledger=ledger)
            if not res.get("ok"):
                return {"error": res.get("error") or "region comment could not be banked"}
            return {"ok": True, "verb": verb, "record": res.get("record"),
                    "grade": "region", "coarse": True, **scope_fields}

        return {"error": "a node, section, paragraph, figure, page region, span, or "
                         "whole-artefact deposit is required to comment"}

    return {"error": f"unknown adjudication verb {verb!r}"}


# ---------------------------------------------------------------------------
# G-4 — the upward view: provenance (minting trace + conceptric upstream),
# the substrate queue (open evolution intents), and the storyboard join
# ---------------------------------------------------------------------------

#: the friction-ledger op kinds, each rendered as a one-line minting summary. The
#: friction ledger (``corpus_friction/<corpus>.jsonl``) is the append-only
#: minting/rewiring trace: every node's provenance is the records that name it.
_FRICTION_OPS = frozenset({
    "add-node", "edit-essence", "add-edge", "remove-edge", "set-spine",
    "unset-spine", "set-kind", "set-projection",
})


def _snippet(text: str, n: int = 120) -> str:
    s = " ".join((text or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _friction_summary(rec: dict) -> str:
    """A one-line, human-facing summary of one friction record — what this op did
    to the node, so the minting trace reads as a history, not a blob of JSON."""
    kind = rec.get("kind")
    if kind == "add-node":
        nk = rec.get("node_kind") or "node"
        ess = _snippet(rec.get("essence") or "")
        return f"minted · {nk}" + (f" — {ess}" if ess else "")
    if kind == "edit-essence":
        return "re-essenced" + (f" — {_snippet(rec.get('value') or '')}"
                                if rec.get("value") else "")
    if kind == "add-edge":
        return f"+ edge → {rec.get('target') or '?'}"
    if kind == "remove-edge":
        return f"− edge → {rec.get('target') or '?'}"
    if kind == "set-spine":
        nar = _snippet(rec.get("narrative") or "")
        return f"placed on the spine (#{rec.get('ord')})" + (f" — {nar}" if nar else "")
    if kind == "unset-spine":
        return "removed from the spine"
    if kind == "set-kind":
        return f"kind → {rec.get('value') or '?'}"
    if kind == "set-projection":
        val = rec.get("value") or {}
        keys = ", ".join(sorted(val.keys())) if isinstance(val, dict) else ""
        return "projection set" + (f" ({keys})" if keys else "")
    return kind or "record"


def _friction_dir() -> Path:
    return _repo_root() / "corpus_friction"


def _friction_path(corpus: str, friction_dir: Path | None = None) -> Path | None:
    """The friction ledger for ``corpus``, fenced under ``corpus_friction/`` so a
    crafted corpus name can never escape. None when no corpus / no ledger on disk."""
    if not corpus:
        return None
    base = (friction_dir or _friction_dir()).resolve()
    cand = (base / f"{corpus}.jsonl").resolve()
    try:
        cand.relative_to(base)
    except ValueError:
        return None
    return cand if cand.is_file() else None


def _upstream(corpus: str, node: str) -> dict | None:
    """The node's UPSTREAM face from the one conceptric store the shared inspector
    reads (:mod:`corpus_ingest`): essence + grade + typed edges (depends-on /
    used-by). None when there is no corpus, the corpus does not resolve, or the
    node is absent — read-only, best-effort, and cheap (the corpus net is cached)."""
    if not corpus or not node:
        return None
    try:
        from laplace.research import corpus_ingest as _ci
        rr = _repo_root()
        troot = _ci.resolve_corpus(rr, corpus)
        if troot is None:
            return None
        net = _ci.corpus_network(troot, repo_root=rr, name=corpus)
        if node not in (net.get("nodes") or {}):
            return None
        nb = _ci.neighborhood(net, node)
        n = nb.get("node") or {}
        proj = (net["nodes"].get(node) or {}).get("projection") or {}

        def _edge(d: dict) -> dict:
            return {"id": d.get("id"), "kind": d.get("kind"),
                    "essence": _snippet(d.get("essence") or "", 140)}

        return {
            "id": node, "kind": n.get("kind"), "grade": n.get("grade"),
            "essence": n.get("essence") or "", "term": proj.get("term"),
            "postulate": bool(n.get("postulate")),
            "depends_on": [_edge(d) for d in nb.get("below") or []],
            "used_by": [_edge(d) for d in nb.get("above") or []],
            "n_below": n.get("n_below"), "n_above": n.get("n_above"),
            "truncated": nb.get("truncated") or {},
        }
    except Exception:                                # noqa: BLE001 - the panel degrades, never raises
        return None


def provenance(corpus: str, node: str, friction_dir: Path | None = None) -> dict:
    """The provenance panel's data — the UPWARD view at the point of adjudication:
    the node's current UPSTREAM (essence/grade/edges from the conceptric store) and
    its MINTING HISTORY (the ``corpus_friction/<corpus>.jsonl`` records that
    created/rewired/re-essenced it, newest first). Read-only: the trace exists; this
    filters and dates it. A dir-only review (no corpus) has no minting trace — the
    panel says so rather than hiding it."""
    out: dict[str, Any] = {"node": node, "corpus": corpus, "history": [],
                           "count": 0, "ledger": None, "present": False,
                           "upstream": _upstream(corpus, node)}
    out["in_conceptric"] = out["upstream"] is not None
    lp = _friction_path(corpus, friction_dir)
    if lp is None:
        out["reason"] = ("this review has no corpus, so no minting trace"
                         if not corpus else
                         f"no friction ledger on disk for corpus {corpus!r}")
        return out
    out["ledger"] = _rel(lp)
    out["present"] = True
    hist = []
    for r in read_jsonl(lp):
        if not isinstance(r, dict) or (r.get("node") or "") != node:
            continue
        if r.get("kind") not in _FRICTION_OPS:
            continue
        hist.append({"id": r.get("id"), "ts": r.get("ts"), "kind": r.get("kind"),
                     "by": r.get("by") or r.get("source") or "",
                     "summary": _friction_summary(r), "target": r.get("target")})
    hist.sort(key=lambda h: (h.get("ts") or "", h.get("id") or ""), reverse=True)
    out["history"] = hist
    out["count"] = len(hist)
    return out


def substrate_queue(md: Path, corpus: str = "", since: str = "",
                    friction_dir: Path | None = None) -> dict:
    """The queued work for the evolution machinery — the OPEN conceptric-intent,
    calibration-intent and projection-intent deposits (the G-3 substrate door plus
    the plan altitude), surfaced so they never vanish into the ledger.
    Revoked/superseded intents drop out via :func:`adjudicate.live`; each entry
    carries the id a ``revoke-intent`` supersedes — including the projection-intent
    (C3.6), whose author-side retire is the same verb the C3.5 apply path writes
    programmatically.

    Extended per the scout's hole 3 (fold, don't build): open ``kind: "fork"``
    records — author decisions the machine cannot make — from the corpus' own L1
    friction ledger (``corpus_friction/<corpus>.jsonl``) fold in BESIDE the
    intents, so a substrate-minted fork never hides in its ledger. Read through
    :func:`friction_consumer.open_frictions`, so retirement-by-evidence-carrying-
    resolution applies here exactly as in the drain. ``since`` is the stateless
    "new since last visit" cursor (client-held baseline, Fork 7: no server-side
    visit record)."""
    ledger = md / "feedback" / "feedback.jsonl"
    records = read_jsonl(ledger) if ledger.is_file() else []
    items: list[dict] = []
    for r in _adj.live(records):
        rk = r.get("record")
        if rk == _adj.CONCEPTRIC_INTENT:
            payload = r.get("payload") or {}
            items.append({"id": r.get("id"), "kind": "conceptric-intent",
                          "node": r.get("node") or r.get("node_id") or "",
                          "intent": r.get("intent") or "other",
                          "note": payload.get("note") or "",
                          "finding_kind": payload.get("finding_kind") or "",
                          "target": r.get("target") or "", "ts": r.get("ts") or "",
                          "by": r.get("source") or ""})
        elif rk == _adj.CALIBRATION_INTENT:
            payload = r.get("payload") or {}
            items.append({"id": r.get("id"), "kind": "calibration-intent",
                          "node": "", "intent": "recalibrate-check",
                          "finding_kind": r.get("finding_kind") or "",
                          "note": payload.get("note") or "",
                          "count": payload.get("dismissal_count"),
                          "target": "", "ts": r.get("ts") or "",
                          "by": r.get("source") or ""})
        elif rk == _adj.PROJECTION_INTENT:
            payload = r.get("payload") or {}
            obj = r.get("object") or {}
            items.append({"id": r.get("id"), "kind": "projection-intent",
                          "node": "", "intent": r.get("verb") or "",
                          "object_kind": obj.get("kind") or "",
                          "object_key": obj.get("sid") or obj.get("key") or "",
                          "note": payload.get("note") or "",
                          "finding_kind": payload.get("finding_kind") or "",
                          "target": r.get("target") or "", "ts": r.get("ts") or "",
                          "by": r.get("source") or ""})
    lp = _friction_path(corpus, friction_dir)
    if lp is not None:
        from laplace.pipeline import friction_consumer as _fc
        for r in _fc.open_frictions(read_jsonl(lp)):
            if r.get("kind") != "fork":
                continue
            items.append({"id": r.get("id"), "kind": "fork",
                          "node": r.get("node") or "",
                          "intent": "author-fork",
                          "note": _snippet(str(r.get("value") or ""), 200),
                          "owning_layer": r.get("owning_layer") or "",
                          "target": r.get("target") or "",
                          "ts": r.get("ts") or "", "by": r.get("by") or "",
                          "ledger": _rel(lp)})
    if since:
        items = [it for it in items if (it.get("ts") or "") > since]
    items.sort(key=lambda x: (x.get("ts") or "", x.get("id") or ""), reverse=True)
    return {"queue": items, "count": len(items), "since": since or None}


def dismissal_audit(md: Path, dials_path: str | None = None) -> dict:
    """The DISMISSAL AUDIT, STRATIFIED by (kind, fingerprint): every ACTIVE
    suppression (a machine or author dismissal that :func:`suppress.load_suppressions`
    still holds live — a revoked one is already dropped) folded into per-CLASS rows
    keyed by ``(kind, content-fingerprint)``. Each row is one dismissal-class the
    author rules on ONCE, both verbs banked through the EXISTING adjudicate door — no
    new semantics:

      * AGREE  → ``calibrate`` the row's kind (affirm the class: the check over-fires,
        recalibrate it — the trust boundary). Idempotent; a row whose kind is already
        calibration-queued shows ``calibrated`` and needs no re-ask.
      * OVERRULE → ``revoke`` the row's suppression(s) (the dismissed finding(s) reborn
        live). One append per suppression id, the same ``suppression-revoke`` the widen
        undo writes.

    A row carries the nodes/sections it silences, its representative reason and source
    (machine vs author), whether the class is a dials ``defer_kind`` (a deferred class
    the author already accepted ``may_dismiss`` on — surfaced, never re-asked), whether
    it is a ``widen`` (WILDCARD) silence (no AGREE — a kind-less class cannot be
    recalibrated, only overruled), and whether its fingerprint is now STALE (the
    dismissed content has since changed, so the finding is already reborn — the edge
    case surfaced plainly). Read-only: the audit reduces the append-only ledger; the
    verbs are the writes."""
    dials = _load_dials(dials_path)
    defer = _defer_kinds(dials)
    ledger = md / "feedback" / "feedback.jsonl"
    if not ledger.is_file():
        return {"rows": [], "counts": {"classes": 0, "dismissals": 0, "stale": 0,
                                       "machine": 0, "author": 0}, "defer_kinds": sorted(defer)}
    supps = _suppress.load_suppressions(ledger)
    node_text = _node_text_map(md)
    calibrated = _adj.calibrated_kinds(read_jsonl(ledger))

    groups: dict[tuple[str, str], dict] = {}
    for s in supps:
        kind = str(s.get("kind") or "")
        fp = _suppress._supp_fingerprint(s)
        node = _suppress._finding_node(s)
        section = str(s.get("section") or "")
        source = str(s.get("source") or (s.get("provenance") or {}).get("actor") or "")
        reason = str((s.get("provenance") or {}).get("reason") or "")
        ts = s.get("ts") or ""
        cur = _suppress.content_fingerprint(node_text[node]) if node in node_text else None
        stale = bool(cur is not None and cur != fp)
        widen = (kind == _suppress.WILDCARD)
        key = (kind, fp)
        g = groups.get(key)
        if g is None:
            g = groups[key] = {
                "kind": kind, "fingerprint": fp, "widen": widen,
                "deferred": kind in defer, "calibrated": kind in calibrated,
                "reason": reason, "nodes": [], "suppression_ids": [],
                "sources": set(), "stale": False, "ts": ts}
        g["nodes"].append({"node": node, "section": section, "stale": stale,
                           "suppression_id": s.get("id"), "ts": ts, "source": source})
        g["suppression_ids"].append(s.get("id"))
        g["sources"].add(source)
        g["stale"] = g["stale"] or stale
        if ts > (g["ts"] or ""):
            g["ts"] = ts
        if not g["reason"] and reason:
            g["reason"] = reason

    rows = []
    n_machine = n_author = n_stale = 0
    for g in groups.values():
        srcs = g.pop("sources")
        g["source"] = ("machine" if srcs == {"machine"}
                       else "author" if "machine" not in srcs
                       else "mixed")
        g["count"] = len(g["suppression_ids"])
        g["nodes"].sort(key=lambda n: (n.get("section") or "", n.get("node") or ""))
        n_machine += sum(1 for n in g["nodes"] if n["source"] == "machine")
        n_author += sum(1 for n in g["nodes"] if n["source"] != "machine")
        n_stale += sum(1 for n in g["nodes"] if n["stale"])
        rows.append(g)
    # biggest classes first, then the deferred/calibrated ones, then kind — the
    # author reads the largest dismissal-classes (the systemic ones) at the top.
    rows.sort(key=lambda r: (-r["count"], r["kind"], r["fingerprint"]))
    return {
        "rows": rows,
        "counts": {"classes": len(rows), "dismissals": sum(r["count"] for r in rows),
                   "stale": n_stale, "machine": n_machine, "author": n_author},
        "defer_kinds": sorted(defer),
        "calibrated_kinds": sorted(calibrated),
    }


# ---------------------------------------------------------------------------
# the LEARNED rollup (scout hole 1 / 2026-07-11 learning-loop design §2) — what
# the loop CONSUMED, by owning layer, with the resolution evidence; plus the
# open counts. Repo-scoped: the §1b friction ledgers are repo files, not
# manuscript files, so this view needs no manuscript dir.
# ---------------------------------------------------------------------------

#: Law I's mechanical budget (the design memo §2a): a cockpit view renders ≤40
#: rows and ≤16KB of payload — the golden test enforces the numbers, not the
#: adjective. A view over budget must project harder, never paginate the flood.
_LEARNED_MAX_ROWS = 40
_LEARNED_MAX_BYTES = 16 * 1024
#: open forks are the queue-head slice (Law II: decisions first) — a handful,
#: never the inventory; the rest is the open COUNT.
_LEARNED_MAX_FORKS = 8


def _learned_ledgers(friction_dir: Path | None = None) -> list[Path]:
    """Every §1b friction ledger this rollup reduces: the engine's
    (``laplace_engine.jsonl``) plus each registered project's L1 ledger, deduped
    by file (ssg-disclosure shares its parent's) and fenced under the friction
    dir. Keyed by ledger BASENAME under ``friction_dir`` so a fixture dir serves
    tests exactly like the live ``corpus_friction/``."""
    base = (friction_dir or _friction_dir()).resolve()
    names = ["laplace_engine.jsonl"]
    try:
        from laplace.pipeline import registry
        for pname in sorted(registry.all_projects()):
            led = registry.all_projects()[pname].ledger
            if led:
                names.append(Path(led).name)
    except Exception:                                # noqa: BLE001 - registry enrichment, never fatal
        pass
    seen: set[Path] = set()
    out: list[Path] = []
    for name in names:
        p = (base / name).resolve()
        try:
            p.relative_to(base)
        except ValueError:
            continue
        if p in seen or not p.is_file():
            continue
        seen.add(p)
        out.append(p)
    return out


def learned(friction_dir: Path | None = None, since: str = "") -> dict:
    """The "what the loop learned" rollup — the one view the scout found
    genuinely missing: CONSUMED friction/fork records (retired by an
    evidence-carrying resolution, :func:`friction_consumer.consumed_frictions`
    semantics) grouped by ``owning_layer``, each row carrying its resolution
    evidence (commit hash / evolution dir / OPEN_STACK row); the OPEN-FORK queue
    head (decisions first, Law II); and the open COUNTS per kind and per layer
    (counts, never lists). Read-only over every §1b ledger.

    Law I is enforced MECHANICALLY: ≤ :data:`_LEARNED_MAX_ROWS` rows and
    ≤ :data:`_LEARNED_MAX_BYTES` of JSON — over-budget tails are dropped (oldest
    first) and ``truncated`` says so; the full totals stay in the counts.
    ``since`` filters to resolutions/forks newer than the client-held baseline
    (localStorage only — Fork 7: the server records no visit)."""
    from laplace.pipeline import friction_consumer as _fc
    ledgers = _learned_ledgers(friction_dir)
    rows: list[dict] = []
    fork_rows: list[dict] = []
    open_friction = open_fork = flagged = 0
    open_by_layer: dict[str, int] = {}
    consumed_total = 0
    for lp in ledgers:
        recs = [r for r in read_jsonl(lp) if isinstance(r, dict)]
        by_id = {r.get("id"): r for r in recs if r.get("id")}
        flagged += len(_fc.invalid_resolutions(recs))
        for r in recs:                               # consumed = evidence-carrying resolution
            if (r.get("record") != _adj.RESOLUTION or not r.get("supersedes")
                    or not str(r.get("evidence") or "").strip()):
                continue
            tgt = by_id.get(r["supersedes"])
            if tgt is None or tgt.get("kind") not in _schema.FRICTION_KINDS:
                continue
            consumed_total += 1
            if since and (r.get("ts") or "") <= since:
                continue
            rows.append({
                "id": tgt.get("id"), "kind": tgt.get("kind"),
                "node": tgt.get("node") or "",
                "layer": str(tgt.get("owning_layer") or "(unassigned)"),
                "summary": _snippet(str(tgt.get("value") or ""), 160),
                "evidence": _snippet(str(r.get("evidence") or ""), 200),
                "resolution": r.get("id"), "ts": r.get("ts") or "",
                "by": ((r.get("provenance") or {}).get("actor")
                       or r.get("source") or ""),
                "ledger": _rel(lp),
            })
        for o in _fc.open_frictions(recs):
            layer = str(o.get("owning_layer") or "(unassigned)")
            open_by_layer[layer] = open_by_layer.get(layer, 0) + 1
            if o.get("kind") == "fork":
                open_fork += 1
                if not since or (o.get("ts") or "") > since:
                    fork_rows.append({
                        "id": o.get("id"), "node": o.get("node") or "",
                        "layer": layer,
                        "summary": _snippet(str(o.get("value") or ""), 160),
                        "ts": o.get("ts") or "", "by": o.get("by") or "",
                        "ledger": _rel(lp),
                    })
            else:
                open_friction += 1
    fork_rows.sort(key=lambda r: (r.get("ts") or "", r.get("id") or ""),
                   reverse=True)
    forks_total = len(fork_rows)
    fork_rows = fork_rows[:_LEARNED_MAX_FORKS]
    # layers ordered by their NEWEST resolution (the delta reads first, Law II);
    # rows inside a layer newest first. The flat list carries `layer` on every
    # row so the tray groups client-side and the byte-trim stays a tail pop.
    newest = {}
    for r in rows:
        lay = r["layer"]
        if (r.get("ts") or "") > newest.get(lay, ""):
            newest[lay] = r.get("ts") or ""
    rows.sort(key=lambda r: (newest.get(r["layer"], ""), r["layer"],
                             r.get("ts") or "", r.get("id") or ""), reverse=True)
    rows_matched = len(rows)
    rows = rows[:max(0, _LEARNED_MAX_ROWS - len(fork_rows))]
    out = {
        "rows": rows, "forks": fork_rows,
        "consumed_total": consumed_total, "rows_matched": rows_matched,
        "forks_total": forks_total,
        "shown": len(rows) + len(fork_rows),
        "truncated": (len(rows) < rows_matched
                      or len(fork_rows) < forks_total),
        "open": {"friction": open_friction, "fork": open_fork,
                 "total": open_friction + open_fork,
                 "by_layer": dict(sorted(open_by_layer.items(),
                                         key=lambda kv: (-kv[1], kv[0]))[:20])},
        "flagged": flagged,
        "ledgers": [_rel(p) for p in ledgers],
        "since": since or None,
        "budget": {"max_rows": _LEARNED_MAX_ROWS,
                   "max_bytes": _LEARNED_MAX_BYTES},
    }
    # the byte half of the Law I budget, enforced not asserted: drop the oldest
    # learned rows (the flat list's tail) until the payload fits.
    def _size(o: dict) -> int:
        return len(json.dumps(o, ensure_ascii=False).encode("utf-8"))
    while out["rows"] and _size(out) > _LEARNED_MAX_BYTES:
        out["rows"].pop()
        out["truncated"] = True
        out["shown"] = len(out["rows"]) + len(out["forks"])
    while out["forks"] and _size(out) > _LEARNED_MAX_BYTES:
        out["forks"].pop()
        out["truncated"] = True
        out["shown"] = len(out["rows"]) + len(out["forks"])
    return out


def storyboard_focus_url(corpus: str, node: str) -> str:
    """The storyboard link that joins the tower upward at a node: the board focused
    on that node's section (scroll + flash + inspect). Empty when there is no corpus
    (a dir-only review cannot address the corpus-keyed board)."""
    if not corpus:
        return ""
    from urllib.parse import quote
    url = "/storyboard?corpus=" + quote(corpus, safe="")
    if node:
        url += "&focus=" + quote(node, safe="")
    return url


# ---------------------------------------------------------------------------
# B13.4 — VERSION COMPARISON: banked-state enumeration + section/paragraph diff
# ---------------------------------------------------------------------------
# First-class comparison (the author's ruling 6): any two BANKED states aligned at
# SECTION/PARAGRAPH grain via the fragment-stem + `% <SEC>-pN` marker idiom (the same
# anchor the edit-in-place surface rides), NOT a full-PDF pixel diff (out of scope —
# pdf.js stays the viewer). The version sources are on disk: B5's per-round-accept git
# commits (``loop: <label> accepted incumbent``), the ``candidate_lock`` snapshot store
# (``rounds/incumbent_r<N>/``), the release finalize record, and git tags. Enumeration
# is LAZY (re-run every request, never cached) so a loop commit landing mid-session
# from a running A6 flow appears on the next call rather than being missed.

#: a loop-commit subject -> its round label ("loop: <label> accepted incumbent").
_LOOP_MSG_RE = re.compile(r"^loop:\s+(.*?)\s+accepted incumbent\s*$")
#: a state is VOICED when its provenance marks a voice pass — a loop label naming
#: voice, or an incumbent snapshot flagged is_voice (convergence's voice
#: burden-of-proof: the accepted candidate dominated the neutral surface).
_VOICE_LABEL_RE = re.compile(r"voice", re.I)
#: manuscript sub-directories NEVER treated as source fragments (snapshot store,
#: evolution scratch) — they would collide section stems and pollute the diff.
_FRAG_SKIP_DIRS = frozenset({"rounds", "evolutions"})


def _git(*args: str) -> subprocess.CompletedProcess:
    """Run one git command from the repo root, capturing text. Never raises — a
    git-absent / non-repo environment returns a non-zero result so the state
    enumeration degrades to 'no git states' plainly rather than 500-ing."""
    try:
        return subprocess.run(["git", *args], cwd=str(_repo_root()),
                              capture_output=True, text=True, check=False)
    except (OSError, ValueError) as e:                # noqa: BLE001 — degrade, never raise
        return subprocess.CompletedProcess(args, 1, "", str(e))


def _nat_key(stem: str) -> list:
    """A natural-sort key so ``N9`` precedes ``N10`` and ``NA1`` groups sanely."""
    return [int(t) if t.isdigit() else t
            for t in re.findall(r"\d+|\D+", stem or "")]


def _changed_summary(paths: list[str], md_rel: str) -> dict:
    """Fold a commit's repo-relative changed paths into a manuscript-scoped summary:
    the fragment files touched, which section stems, and whether the PDF moved."""
    pre = md_rel + "/"
    frag = [p[len(pre):] for p in paths if p.startswith(pre)]
    tex = [f for f in frag if f.endswith(".tex")]
    sections = sorted({Path(f).stem for f in tex}, key=_nat_key)
    return {"files": frag, "sections": sections,
            "pdf": any(f.endswith("main.pdf") for f in frag), "n_files": len(frag)}


def _loop_states(md: Path) -> list[dict]:
    """The B5 per-round-accept git commits touching this manuscript, newest first.
    One combined ``git log`` call (record-separated) — the changed-file list rides
    the same call so the endpoint is one subprocess, not one-per-commit."""
    rel = _rel(md)
    r = _git("log", "-E", "--grep=^loop:", "--format=%x1e%H%x1f%cI%x1f%s",
             "--name-only", "--", rel)
    if r.returncode != 0 or not (r.stdout or "").strip():
        return []
    out: list[dict] = []
    for rec in r.stdout.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        lines = rec.split("\n")
        head = lines[0]
        parts = head.split("\x1f")
        if len(parts) < 3:
            continue
        sha, when, subj = parts[0], parts[1], parts[2]
        paths = [ln for ln in lines[1:] if ln.strip()]
        m = _LOOP_MSG_RE.match(subj)
        label = (m.group(1) if m else subj).strip()
        out.append({
            "id": sha, "kind": "loop-pass", "when": when, "label": label,
            "sha": sha, "short": sha[:9], "ref": {"kind": "git", "sha": sha},
            "resolvable": True, "voiced": bool(_VOICE_LABEL_RE.search(label)),
            "what_changed": _changed_summary(paths, rel),
        })
    return out


def _incumbent_states(md: Path) -> list[dict]:
    """The ``candidate_lock`` snapshot store: every ``rounds/incumbent_r<N>/`` snapshot
    with a manifest, newest round first. Each resolves its tex from the snapshot dir
    (git-independent — the transactional truth). ``is_voice`` in the manifest marks a
    voiced snapshot."""
    rd = md / "rounds"
    if not rd.is_dir():
        return []
    out: list[dict] = []
    for d in rd.glob("incumbent_r*"):
        m = re.match(r"incumbent_r(\d+)$", d.name)
        if not m or not (d / "SNAPSHOT.json").is_file():
            continue
        n = int(m.group(1))
        meta: dict = {}
        try:
            meta = json.loads((d / "SNAPSHOT.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        voiced = bool(meta.get("is_voice") or meta.get("voice"))
        out.append({
            "id": f"incumbent-r{n}", "kind": "incumbent", "when": meta.get("ts") or "",
            "label": f"incumbent r{n}", "round": n,
            "ref": {"kind": "snapshot", "dir": _rel(d)}, "resolvable": True,
            "voiced": voiced, "has_pdf": (d / "main.pdf").is_file(),
        })
    out.sort(key=lambda s: s["round"], reverse=True)
    return out


def _tag_states(md: Path) -> list[dict]:
    """Git tags whose commit touches this manuscript — each a named banked state,
    resolvable at tex grain through its commit. Empty when the repo has no tags."""
    r = _git("tag", "--format=%(refname:short)%09%(creatordate:iso-strict)")
    if r.returncode != 0 or not (r.stdout or "").strip():
        return []
    rel = _rel(md)
    out: list[dict] = []
    for ln in r.stdout.splitlines():
        name = ln.split("\t")[0].strip()
        when = (ln.split("\t")[1].strip() if "\t" in ln else "")
        if not name:
            continue
        sha_r = _git("rev-list", "-n", "1", name)
        sha = (sha_r.stdout or "").strip()
        if not sha:
            continue
        # FND-2: test whether the TAGGED COMMIT ITSELF touches the manuscript, via the
        # files it changed (``git show --name-only``), NOT ``git log <sha> -- <rel>``.
        # The latter is ANCESTRY-based: it walks back from the tag to the nearest commit
        # that touched the manuscript, so a later docs-only tag whose history merely
        # CONTAINS a manuscript commit was wrongly enumerated as a manuscript version.
        # The touched-file test names only tags whose own commit changed a file under
        # the manuscript dir — the honest reading of the docstring.
        touches = _git("show", "--name-only", "--format=", sha)
        pre = rel + "/"
        changed = [ln.strip() for ln in (touches.stdout or "").splitlines() if ln.strip()]
        if not any(f == rel or f.startswith(pre) for f in changed):
            continue                                  # tag's commit does not touch this manuscript
        out.append({"id": f"tag:{name}", "kind": "tag", "when": when,
                    "label": name, "sha": sha, "short": sha[:9],
                    "ref": {"kind": "git", "sha": sha}, "resolvable": True,
                    "voiced": bool(_VOICE_LABEL_RE.search(name))})
    return out


def _release_states(md: Path) -> list[dict]:
    """The release finalize record(s) — the CLEAN named artefact (ruling 2). A release
    is listed as a banked state plainly, but it is PDF-only: the finalize record names
    a shipped PDF, not a tex tree, so it resolves at tex grain only when a git tag/commit
    snapshots that state. Absent such a ref it renders resolvable=False with the reason,
    never a silent wrong alignment."""
    from laplace.pipeline import release as rel
    rec = rel._finalize_record(md)
    if not rec:
        return []
    slug = rec.get("slug") or "release"
    when = rec.get("created") or ""
    # a tag or commit that snapshots this release's tex, if one exists on disk
    ref, resolvable, reason, sha = None, False, None, None
    tag_r = _git("rev-list", "-n", "1", slug)
    if tag_r.returncode == 0 and (tag_r.stdout or "").strip():
        sha = tag_r.stdout.strip()
        ref, resolvable = {"kind": "git", "sha": sha}, True
    else:
        reason = ("release is PDF-only — its finalize record names a shipped PDF, "
                  "not a git-snapshotted tex tree, so no section/paragraph alignment "
                  "is possible (pdf.js stays the viewer; no pixel diff)")
    out = {"id": f"release:{slug}", "kind": "release", "when": when,
           "label": f"release · {slug}" + (f" r{rec['revision']}" if rec.get("revision") else ""),
           "slug": slug, "revision": rec.get("revision"), "pdf": rec.get("pdf_path"),
           "ref": ref, "resolvable": resolvable, "voiced": False}
    if not resolvable:
        out["unresolvable_reason"] = reason
    elif sha:
        out["short"] = sha[:9]
    return [out]


def _working_state(md: Path) -> dict:
    """The live working candidate — the current tree bytes (``main.pdf`` + the tex on
    disk). Always present, always the newest, resolvable directly from the worktree."""
    return {"id": "working", "kind": "working", "when": None,
            "label": "working candidate", "ref": {"kind": "worktree"},
            "resolvable": True, "voiced": False,
            "has_pdf": (md / "main.pdf").is_file()}


def banked_states(md: Path) -> list[dict]:
    """Every banked state for the manuscript, the working candidate pinned first and
    the rest newest-first by timestamp. LAZY: re-derived on every call (git + disk),
    never cached — a loop commit landing between two requests appears on the next."""
    rest = _loop_states(md) + _incumbent_states(md) + _tag_states(md) + _release_states(md)
    rest.sort(key=lambda s: (s.get("when") or ""), reverse=True)
    return [_working_state(md)] + rest


def _state_before(states: list[dict], target: dict) -> Optional[dict]:
    """The banked state chronologically just before ``target`` (its neutral
    predecessor) among the resolvable, non-working states — the list is newest-first,
    so it is the next resolvable state after target's index."""
    try:
        i = next(k for k, s in enumerate(states) if s["id"] == target["id"])
    except StopIteration:
        return None
    for s in states[i + 1:]:
        if s.get("resolvable") and s.get("kind") != "working":
            return s
    return None


def _presets(states: list[dict]) -> dict:
    """The two ruled presets, resolved against the states that actually exist:
    candidate-vs-incumbent and neutral-vs-voiced. Each preset is either AVAILABLE
    (one-click, carrying the two state ids it compares) or disabled-with-reason when
    its states are not banked in this corpus — plain, never a dead button."""
    avail: list[dict] = []
    disabled: list[dict] = []
    working = next((s for s in states if s["kind"] == "working"), None)
    snaps = [s for s in states if s["kind"] == "incumbent"]
    loops = [s for s in states if s["kind"] == "loop-pass"]

    # candidate-vs-incumbent: the challenger (working tree) against its baseline. The
    # incumbent is the newest snapshot if one exists, else the newest loop-pass commit
    # (each B5 loop commit IS an accepted incumbent banked to git).
    incumbent = snaps[0] if snaps else (loops[0] if loops else None)
    if working and incumbent:
        # baseline (incumbent) on the LEFT / A, candidate on the RIGHT / B — diff
        # convention old→new, so the candidate's additions read as inserts.
        avail.append({"id": "candidate-vs-incumbent", "a": incumbent["id"],
                      "b": working["id"], "label": "candidate vs incumbent",
                      "a_label": incumbent["label"], "b_label": working["label"]})
    else:
        disabled.append({"id": "candidate-vs-incumbent", "label": "candidate vs incumbent",
                         "reason": "no incumbent snapshot or loop-pass commit is banked "
                                   "yet — nothing to compare the candidate against"})

    # neutral-vs-voiced: a voiced state (voice pass) against its neutral predecessor.
    voiced = [s for s in states if s.get("voiced") and s.get("resolvable")]
    if voiced:
        v = voiced[0]
        neutral = _state_before(states, v)
        if neutral:
            avail.append({"id": "neutral-vs-voiced", "a": neutral["id"], "b": v["id"],
                          "label": "neutral vs voiced", "a_label": neutral["label"],
                          "b_label": v["label"]})
        else:
            disabled.append({"id": "neutral-vs-voiced", "label": "neutral vs voiced",
                             "reason": "a voiced state is banked but no neutral "
                                       "predecessor exists to compare it against"})
    else:
        disabled.append({"id": "neutral-vs-voiced", "label": "neutral vs voiced",
                         "reason": "no voiced state is banked in this corpus — no "
                                   "loop-pass is labelled a voice pass and no snapshot "
                                   "is marked is_voice"})
    return {"available": avail, "disabled_with_reason": disabled}


def states(md: Path) -> dict:
    """The banked-state enumeration + the resolved presets — the compare surface's
    read model. Lazy and uncached (tolerates the live corpus mutating mid-session)."""
    sts = banked_states(md)
    return {"manuscript_dir": _rel(md), "states": sts, "presets": _presets(sts)}


# ── resolving a state's tex, and aligning two states at section/paragraph grain ──

def _frag_skip(rel_path: str) -> bool:
    """Whether a manuscript-relative tex path is a non-source fragment (under the
    snapshot store or evolution scratch) — excluded from the diff."""
    return any(part in _FRAG_SKIP_DIRS for part in Path(rel_path).parts)


def _git_tex(sha: str, md: Path) -> dict[str, str]:
    """Every ``*.tex`` fragment of the manuscript at commit ``sha``, keyed by section
    stem (shallowest path wins a stem collision). ``git show`` per file — the tex of
    each side of the diff comes straight from the object store, no checkout."""
    rel = _rel(md)
    ls = _git("ls-tree", "-r", "--name-only", sha, "--", rel)
    if ls.returncode != 0:
        return {}
    paths = [p for p in ls.stdout.splitlines()
             if p.endswith(".tex") and not _frag_skip(p[len(rel) + 1:] if p.startswith(rel + "/") else p)]
    paths.sort(key=lambda p: (p.count("/"), p))       # shallow first
    out: dict[str, str] = {}
    for p in paths:
        stem = Path(p).stem
        if stem in out:
            continue
        show = _git("show", f"{sha}:{p}")
        if show.returncode == 0:
            out[stem] = show.stdout
    return out


def _dir_tex(base: Path) -> dict[str, str]:
    """Every ``*.tex`` under ``base`` (a worktree manuscript dir or a snapshot dir),
    keyed by section stem, snapshot/evolution sub-trees excluded (shallowest wins)."""
    if not base.is_dir():
        return {}
    files = [f for f in base.rglob("*.tex")
             if not _frag_skip(f.relative_to(base).as_posix())]
    files.sort(key=lambda f: (len(f.relative_to(base).parts), f.as_posix()))
    out: dict[str, str] = {}
    for f in files:
        if f.stem in out:
            continue
        try:
            out[f.stem] = f.read_text(encoding="utf-8")
        except OSError:
            continue
    return out


def _side_tex(md: Path, state: dict) -> dict[str, str]:
    """Resolve a state to ``{section-stem: raw tex}`` via its ref: the worktree, a git
    commit/tag (from the object store), or a snapshot dir. Empty when unresolvable."""
    ref = state.get("ref") or {}
    kind = ref.get("kind")
    if kind == "worktree":
        return _dir_tex(md)
    if kind == "git" and ref.get("sha"):
        return _git_tex(ref["sha"], md)
    if kind == "snapshot" and ref.get("dir"):
        p = _fence(Path(ref["dir"]))
        return _dir_tex(p) if p is not None else {}
    return {}


def _split_units(raw: str) -> list[tuple[str, str]]:
    """Split a fragment into ordered ``(pid, body)`` units by the ``% <SEC>-pN``
    markers — the SAME grain the edit-in-place surface anchors on. The pre-marker
    preamble (``% PLAN`` / ``% NODES`` / ``\\section``) is one ``§preamble`` unit; each
    paragraph is its marker's pid with the machine-owned marker line EXCLUDED from the
    compared body (so the diff shows prose, exactly as the editor does). A markerless
    fragment (a figure/table) is one ``§whole`` unit."""
    lines = raw.splitlines(keepends=True)
    marks: list[int] = []
    for i, ln in enumerate(lines):
        if _EDIT_MARK_RE.match(ln.rstrip("\n")):
            marks.append(i)
    if not marks:
        return [("§whole", raw.strip())]
    units: list[tuple[str, str]] = []
    preamble = "".join(lines[:marks[0]]).strip()
    if preamble:
        units.append(("§preamble", preamble))
    for j, i in enumerate(marks):
        m = _EDIT_MARK_RE.match(lines[i].rstrip("\n"))
        pid = m.group(1) if m else f"unit{j}"
        end = marks[j + 1] if j + 1 < len(marks) else len(lines)
        body = "".join(lines[i + 1:end]).strip()      # drop the marker line
        units.append((pid, body))
    return units


def _word_diff(a: str, b: str) -> list[dict]:
    """A word/whitespace-grained diff of two paragraph bodies as ordered segments
    ``{op, a, b}`` (op ∈ equal/insert/delete/replace) — tokens keep their whitespace
    so each side reconstructs exactly. The renderer paints delete/insert spans."""
    ta = re.findall(r"\s+|\S+", a or "")
    tb = re.findall(r"\s+|\S+", b or "")
    segs: list[dict] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ta, tb, autojunk=False).get_opcodes():
        segs.append({"op": op, "a": "".join(ta[i1:i2]), "b": "".join(tb[j1:j2])})
    return segs


def _reading_order(main_raw: str | None) -> list[str]:
    """The section stems in ``\\input`` order from a main.tex — the manuscript's own
    reading order, so the comparison navigates top-to-bottom as the paper reads."""
    if not main_raw:
        return []
    return [Path(m.group(1)).stem
            for m in re.finditer(r"\\input\{([^}]+)\}", main_raw)]


def _align_units(unitsA: list[tuple[str, str]],
                 unitsB: list[tuple[str, str]]) -> tuple[list[dict], dict]:
    """Align two fragments' paragraph units by pid (the fragment-stem idiom keeps pids
    stable across versions), via a sequence match over the pid streams so reorders and
    add/remove read sensibly. Returns the per-unit rows + a change tally.

    Bodies are indexed POSITIONALLY, never through a ``dict(units)`` keyed by pid: a
    fragment can legitimately carry a DUPLICATE ``% <SEC>-pN`` marker (a stray copy, a
    hand edit that cloned a unit), and a pid-keyed dict silently drops the first body
    so the diff shows the wrong (last) text for that pid. The SequenceMatcher already
    runs over the pid STREAMS (dupes and all); pairing bodies by the matcher's own
    indices keeps every occurrence's real text (FND-1)."""
    pidsA = [p for p, _ in unitsA]
    pidsB = [p for p, _ in unitsB]
    bodiesA = [b for _, b in unitsA]
    bodiesB = [b for _, b in unitsB]
    rows: list[dict] = []
    tally = {"changed": 0, "added": 0, "removed": 0, "same": 0}
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
            None, pidsA, pidsB, autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                pid = pidsA[i1 + k]
                a, b = bodiesA[i1 + k], bodiesB[j1 + k]
                if a == b:
                    rows.append({"pid": pid, "status": "same", "a": a, "b": b})
                    tally["same"] += 1
                else:
                    rows.append({"pid": pid, "status": "changed", "a": a, "b": b,
                                 "diff": _word_diff(a, b)})
                    tally["changed"] += 1
        else:  # delete / insert / replace → removed (A side) + added (B side)
            for k in range(i1, i2):
                rows.append({"pid": pidsA[k], "status": "removed",
                             "a": bodiesA[k], "b": None})
                tally["removed"] += 1
            for k in range(j1, j2):
                rows.append({"pid": pidsB[k], "status": "added",
                             "a": None, "b": bodiesB[k]})
                tally["added"] += 1
    return rows, tally


def compare(md: Path, a_id: str, b_id: str) -> dict:
    """Align two banked states at SECTION/PARAGRAPH grain. Resolves each state's tex
    (worktree / git object store / snapshot), aligns fragment-by-fragment and, inside a
    fragment, paragraph-by-paragraph on the ``% <SEC>-pN`` idiom, word-diffing a changed
    paragraph. Unchanged sections carry ``changed=False`` (the surface collapses them).
    Never raises: an unknown or unresolvable state returns ``{error, reason}`` (→ 422)."""
    sts = banked_states(md)
    byid = {s["id"]: s for s in sts}
    A, B = byid.get(a_id), byid.get(b_id)
    if A is None:
        return {"error": f"unknown state {a_id!r}", "reason": "unknown-a"}
    if B is None:
        return {"error": f"unknown state {b_id!r}", "reason": "unknown-b"}
    for side, st in (("a", A), ("b", B)):
        if not st.get("resolvable"):
            return {"error": f"state {st['id']!r} has no tex to align at "
                             "section/paragraph grain",
                    "reason": f"unresolvable-{side}",
                    "detail": st.get("unresolvable_reason") or "no resolvable ref"}
    texA, texB = _side_tex(md, A), _side_tex(md, B)
    order = _reading_order(texB.get("main")) or _reading_order(texA.get("main"))
    stems = set(texA) | set(texB)
    ordered = [s for s in order if s in stems]
    ordered += sorted((stems - set(ordered)), key=_nat_key)

    sections: list[dict] = []
    counts = {"sections": 0, "sections_changed": 0,
              "paragraphs_changed": 0, "added": 0, "removed": 0}
    for stem in ordered:
        counts["sections"] += 1
        rawA, rawB = texA.get(stem), texB.get(stem)
        if rawA is None or rawB is None:
            rows, tally = _align_units(
                _split_units(rawA) if rawA is not None else [],
                _split_units(rawB) if rawB is not None else [])
            status = "added" if rawA is None else "removed"
        else:
            rows, tally = _align_units(_split_units(rawA), _split_units(rawB))
            status = "unchanged" if not (tally["changed"] or tally["added"]
                                         or tally["removed"]) else "changed"
        changed = status != "unchanged"
        if changed:
            counts["sections_changed"] += 1
        counts["paragraphs_changed"] += tally["changed"]
        counts["added"] += tally["added"]
        counts["removed"] += tally["removed"]
        sections.append({"stem": stem, "status": status, "changed": changed,
                         "units": rows, "tally": tally})

    def _face(s: dict) -> dict:
        return {"id": s["id"], "kind": s["kind"], "label": s.get("label") or s["id"],
                "when": s.get("when"), "short": s.get("short")}

    return {"a": _face(A), "b": _face(B), "sections": sections, "counts": counts}


# ---------------------------------------------------------------------------
# THE HIS-HAND LAYER — the author's own edited ranges in a source file.
#
# Ground truth is the version rail's ACTOR ATTRIBUTION (``shared_ui.versions_payload``),
# never a style heuristic: every save is one of the rail's kinds, and ``editor-save`` is
# HIS door (the interactive editor) while ``round`` / ``release`` / ``snapshot`` are the
# machine's mints. His hand in a file = the diff of that file on disk against the newest
# MACHINE-minted version that carries it (the machine never writes between its own mints,
# so every line changed since the last machine baseline is his). Honest about every empty
# case; when the rail cannot attribute a baseline it SAYS SO rather than inventing one.
# ---------------------------------------------------------------------------

def _hishand_baseline(rows: list[dict], file_rel: str, root: Path):
    """Newest applicable recorded occurrence, or no proved attribution.

    An invalid/ambiguous newest baseline cannot be replaced by an older success.
    Metadata filters unrelated targets before any saved source body is opened.
    """
    from laplace.manuscript.projection_viewer import read_editor_save
    from laplace.projects.writing_portability import source_path
    target = (root / file_rel).resolve()
    machine = [r for r in rows if r.get('kind') == 'editor-save' and
               str(r.get('author') or '').startswith(('eigen','machine','pipeline','author:accepted-model'))]
    if (not machine or any(type(r.get('archive_order')) is not int for r in machine) or
            len({r['archive_order'] for r in machine}) != len(machine)):
        return None
    newest = None
    for r in sorted(machine, key=lambda r: r['archive_order'], reverse=True):
        if not isinstance(r.get('source_file'), str) or not r['source_file']:
            return None
        try:
            declared = source_path(r['source_file'], root)
        except (KeyError, TypeError, ValueError):
            return None                       # applicability itself is unproved
        if declared != target:
            continue
        if not r.get('archive_order_proven'):
            return None                       # no occurrence fallback for this target
        newest = r
        break
    if newest is None:
        return None
    directories = [root / value for value in newest.get('paths') or []
                   if (root / value).name == newest.get('id') and (root / value).parent.name == 'editor_saves']
    if len(directories) != 1 or newest.get('source_binding') != 'BOUND':
        return None
    try:
        observed = read_editor_save(directories[0].parent.parent, str(newest['id']), repo_root=root)
        if observed['live_file'] == target:
            return observed['data'].decode('utf-8', errors='replace'), newest
    except (OSError, ValueError):
        pass                                  # newest failure remains unproved
    return None


def hand_hunks(corpus: str, file_rel: str, root: Path | None = None) -> dict:
    """THE baseline diff, once: the author's own passages in ``file_rel`` against the
    newest machine-minted version that carries it, as HUNKS — each ``{start, end,
    before, after}`` with the replaced and current line lists, 1-based inclusive
    current-file lines.

    Two consumers read this one producer, so the attribution rule is stated once:
    :func:`his_hand` (the your-hand ranges the surface tints) projects the hunks to
    bare ranges, and :func:`bank_exemplar` (the editor-save exemplar door) banks their
    before/after text. Never guesses attribution; states every empty case in words."""
    import difflib
    from laplace.manuscript import manuscript_plan
    from laplace.manuscript import manuscript_versions
    root = (root or _repo_root()).resolve()
    if not file_rel:
        return {"ok": False, "reason": "file is required", "file": ""}
    cur = root / file_rel
    if not cur.is_file():
        return {"ok": False, "reason": "file not found", "file": file_rel}
    cur_lines = cur.read_text(encoding="utf-8", errors="replace").splitlines()
    v = manuscript_versions.versions_payload(corpus, root) or {}
    rows = v.get("rows") or []
    if v.get("truncated"):
        return {"ok":True,"file":file_rel,"attributed":False,"whole_file":False,
                "baseline":None,"hunks":[],"counts":{"passages":0,"lines":0},
                "note":"The inspected history projection is incomplete; the newest applicable baseline is unproved."}
    if v.get("never_run") or not rows:
        return {"ok": True, "file": file_rel, "attributed": False, "whole_file": False,
                "baseline": None, "hunks": [], "counts": {"passages": 0, "lines": 0},
                "note": "the version rail has no history yet — no hand can be attributed."}
    base = _hishand_baseline(rows, file_rel, root)
    if base is None:
        return {"ok":True,"file":file_rel,"attributed":False,"whole_file":False,
                "baseline":None,"hunks":[],"counts":{"passages":0,"lines":0},
                "note":"No exact source-bound machine-labelled baseline is available; authorship is unproved."}
    base_text, base_row = base
    base_lines = base_text.splitlines()
    sm = difflib.SequenceMatcher(a=base_lines, b=cur_lines, autojunk=False)
    hunks: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("insert", "replace") and j2 > j1:
            hunks.append({"start": j1 + 1, "end": j2,          # 1-based inclusive current
                          "before": base_lines[i1:i2], "after": cur_lines[j1:j2]})
    n_lines = sum(h["end"] - h["start"] + 1 for h in hunks)
    kind = base_row.get("kind") or "machine"
    if not hunks:
        note = f"no edits of your hand since the {kind} baseline."
    else:
        note = (f"{len(hunks)} passage" + ("" if len(hunks) == 1 else "s")
                + f" of your hand since the {kind} baseline.")
    return {"ok": True, "file": file_rel, "attributed": True, "whole_file": False,
            "baseline": {"id": base_row.get("id"), "kind": kind, "ts": base_row.get("ts")},
            "hunks": hunks, "counts": {"passages": len(hunks), "lines": n_lines},
            "note": note}


def his_hand(corpus: str, file_rel: str, root: Path | None = None) -> dict:
    """The author's own edited line-ranges in ``file_rel`` — :func:`hand_hunks` with the
    hunk text projected away, so the surface gets the ranges it tints and nothing else.
    Ranges are 1-based inclusive current-file lines."""
    out = hand_hunks(corpus, file_rel, root)
    if not out.get("ok"):
        return out
    hunks = out.pop("hunks", [])
    out["ranges"] = [{"start": h["start"], "end": h["end"]} for h in hunks]
    return out


# ---------------------------------------------------------------------------
# THE EXEMPLAR DOOR — an editor save banks one exemplar row, with a loud receipt.
#
# The rewrite gesture (`e` on a paragraph → Ctrl-S) is the ONE commit the author makes
# without a deposit gesture, so it is the one place the bank must announce itself and
# the one place a real undo is mandatory. The save banks ONE row per save carrying the
# server-derived hunks against the newest machine baseline (:func:`hand_hunks` — the
# same producer the your-hand tint reads), shaped to MIRROR his own calibration rows
# (FB-20260808-gm-001…gm-009: source / anchor / scope / kind / text on a plain ledger
# row) so the calibration pool consumes it with no adapter. The receipt names the row
# id, the passage and line counts, and where it landed; the row is withdrawn through
# the existing ``revoke`` verb (it carries no ``record`` discriminator, so revoke
# retires it with a superseding resolution record).
# ---------------------------------------------------------------------------

#: the exemplar row's finding kind and altitude. An author rewrite of his own prose is
#: a VOICE-altitude sample (his gm-006 exemplar row types the same way); the kind names
#: the gesture that produced it, so a pool consumer can select exactly these rows.
_EXEMPLAR_KIND = "author-rewrite"
_EXEMPLAR_SCOPE = "voice"


def _exemplar_ledger(corpus: str, root: Path) -> Path | None:
    """The feedback ledger an exemplar row lands in — resolved through the one
    server-canonical authority (``registry.project_context``), never a local guess.
    ``None`` for an unknown / path-shaped corpus (the registry fence)."""
    if not corpus:
        return None
    try:
        from laplace.pipeline import registry
        ctx = registry.project_context(corpus, root)
    except Exception:  # noqa: BLE001 — a resolver hiccup degrades to no store, never a crash
        return None
    if ctx is None:
        return None
    return ctx.feedback_ledger


def bank_exemplar(corpus: str, file_rel: str, *, author: str, project: str = "",
                  root: Path | None = None, surface: str = "editor",
                  before: bytes | None = None, after: bytes | None = None) -> dict:
    """Bank ONE exemplar row for an editor save of ``file_rel``, and return the receipt
    ``{banked, exemplar_id, passages, lines, destination}``.

    Banks only when the save actually differs from the newest machine-minted baseline —
    a save with no hunks banks nothing and says so, rather than filling the pool with
    rows that hold no author hand. The actor law: ``author`` is required and defaults
    NOWHERE; an unattributed save banks no exemplar (the save itself is unaffected)."""
    root = (root or _repo_root()).resolve()
    author = (author or "").strip()
    if not author:
        return {"banked": False,
                "reason": "by (explicit actor) is required: an exemplar row is "
                          "actor-attributed and this door defaults nowhere"}
    if not file_rel:
        return {"banked": False, "reason": "file is required"}
    ledger = _exemplar_ledger(corpus, root)
    if ledger is None:
        return {"banked": False,
                "reason": "no feedback ledger for the corpus — nothing banked"}
    if before is not None or after is not None:
        if not isinstance(before, bytes) or not isinstance(after, bytes):
            raise ValueError("captured save before/after must be exact bytes")
        old_lines, new_lines = before.decode('utf-8',errors='replace').splitlines(), after.decode('utf-8',errors='replace').splitlines()
        hunks = [{"start":j1+1,"end":j2,"before":old_lines[i1:i2],"after":new_lines[j1:j2]}
                 for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(a=old_lines,b=new_lines,autojunk=False).get_opcodes()
                 if tag != 'equal']
        hand = {'ok':True,'hunks':hunks,'counts':{'passages':len(hunks),'lines':sum(max(0,h['end']-h['start']+1) for h in hunks)},
                'baseline':{'kind':'guarded-save-preimage','source_file':file_rel,
                            'before_sha256':hashlib.sha256(before).hexdigest(),'after_sha256':hashlib.sha256(after).hexdigest()}}
    else:
        hand = hand_hunks(corpus, file_rel, root)
    if not hand.get("ok"):
        return {"banked": False, "reason": hand.get("reason") or "no hand diff"}
    hunks = hand.get("hunks") or []
    if not hunks:
        return {"banked": False, "reason": hand.get("note") or "no hunks in this save"}
    counts = hand.get("counts") or {}
    passages, lines = int(counts.get("passages") or 0), int(counts.get("lines") or 0)
    baseline = hand.get("baseline") or {}
    base_kind = baseline.get("kind") or "machine"
    now = _dt.datetime.now()
    rec = {
        # the gm calibration-row shape, field for field
        "id": now.strftime("FB-%Y%m%d-%H%M%S-ex"),
        "project": project or corpus,
        "ts": now.isoformat(timespec="seconds"),
        "source": f"{author}:editor-save ({surface})",
        "anchor": file_rel,                    # a STRING ref, as his own rows carry
        "supersedes": "",
        "scope": _EXEMPLAR_SCOPE,
        "kind": _EXEMPLAR_KIND,
        "node_id": "",
        "section": "",
        "text": (f"Recorded save delta by {author} in {file_rel}: {passages} hunk(s), {lines} retained after-line(s), against the guarded preimage."
                 if before is not None else f"{passages} passage" + ("" if passages == 1 else "s")
                 + f" of the author's hand in {file_rel} ({lines} line"
                 + ("" if lines == 1 else "s") + f") against the {base_kind} baseline"
                 + (f" {baseline.get('id')}" if baseline.get("id") else "") + "."),
        # the engine fields beside them: the actor law's attribution, the open state
        # every ledger consumer reads, and the derived hunks themselves.
        "by": author,
        "status": "open",
        "file": file_rel,
        "baseline": baseline or None,
        "counts": {"passages": passages, "lines": lines},
        "hunks": hunks,
    }
    from laplace.manuscript.manuscript_bridge import append_feedback_record
    append_feedback_record(ledger, rec)
    try:
        destination = ledger.resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        destination = str(ledger)
    return {"banked": True, "exemplar_id": rec["id"],
            "passages": passages, "lines": lines,
            "destination": destination, "scope": _EXEMPLAR_SCOPE,
            "kind": _EXEMPLAR_KIND}


# ---------------------------------------------------------------------------
# routing
# ---------------------------------------------------------------------------

def _resolve(query: dict) -> tuple[Path | None, str, str]:
    corpus, dir_param = _q1(query, "corpus"), _q1(query, "dir")
    if not corpus and not dir_param:
        # bare route (W0.2): open the ACTIVE PROJECT, never an empty shell. The
        # author's persisted active_corpus (.cockpit.json) wins, else the newest
        # ledger — one door, corpus_ingest.default_corpus.
        from laplace.research import corpus_ingest as _ci
        corpus = _ci.default_corpus(_repo_root())
    md = manuscript_dir(corpus, dir_param)
    return md, corpus, dir_param


