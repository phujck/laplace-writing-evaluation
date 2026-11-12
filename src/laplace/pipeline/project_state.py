"""the truth layer — one typed verdict per project, a JOIN of existing readers.

ACT 1, ``DESIGN_2026-07-21_the-ui-overhaul.md`` (E4b/E6): the desk, the cockpit,
the storyboard run tab, and the dashboard cards each computed their own story and
disagreed ("finalized · NEVER_RUN · round 7"). This module is the one server-side
composition every surface should read instead — it invents no number: every field
is read from a reader that already owns it.

Readers composed (never re-implemented):
  * :func:`registry.project_states` / :func:`registry.project_context` — the
    release-machine position, rounds count, current-artefact fact.
  * :func:`selection_sheet.read_selection` — the generation-by-generation debt
    trajectory (30→20→3→0 for paper_falqon; already computed there).
  * :func:`generation_ledger.read_generations` — the generation ledger (GEN-N).
  * :mod:`release` (``_finalize_record``) — the release-side minted artefact
    (name/path/date), the SAME private accessor ``review_surface`` already
    imports across the module boundary.
  * :func:`evolution_consumer.open_projection_intents` — the open plan-altitude
    intents (RESPINE and siblings), scoped to the project's own feedback ledger.
  * :mod:`open_stack_store` — the typed author-fork store, scoped to this
    project via a ``corpus`` field on the row (a project-scoped fork names its
    own corpus; an engine-wide fork like F37/F38 carries none and is correctly
    excluded from any one project's owed list).
  * ``<manuscript>/rounds/harnessed/detect_*.json`` — the harnessed round count
    (a direct, plain file count; no reader owns this specific glob elsewhere).

Declared absence (P7): every reader call is guarded — a missing store, an
unregistered project, or a corrupt sidecar degrades the affected field to an
declared absence (``None`` / ``[]`` / ``"not started"``), never a crash and never
a fabricated number. ``position_evidence`` labels pre-machine-era history
plainly ("N rounds + <artefact> — predate the release machine") instead of
collapsing a paper with 9 real rounds and a minted PDF into bare "never run".

Public API:
    project_verdict(repo_root, project) -> dict
        {present, project, position, position_evidence[], artefact{name,path,
         minted_at} | None, generations{present,gen,debt_trajectory,
         respine_intent}, rounds{n,last}, growth{present,state,goal_version,bar,
         pre_ladder,reason}, next_act{verb,target,label,href,cost_class,psu},
         owed_to_author[]}
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from laplace.pipeline import registry

#: a minted slug's trailing revision tag ("...-r2" -> "r2") — the honest label
#: for "which release" without re-deriving the release machine's own vocabulary.
_MINTED_SLUG_REV_RE = re.compile(r"-r(\d+)$")

#: a harnessed round file's ordinal ("detect_pre_r7.json" -> 7) — mirrors
#: generation_ledger._round_int / convergence_ledger._round_int (the shared
#: idiom; each module keeps its own tiny copy rather than a cross-import for
#: one regex).
_ROUND_INT_RE = re.compile(r"_r(\d+)\b")


def _relposix(p: Path, root: Path) -> str:
    """A repo-relative POSIX path for ``p`` under ``root``, else the absolute
    string (a path outside root is never silently mis-rendered as relative)."""
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(p)


def _storyboard_href(name: str, anchor: str = "") -> str:
    """A deep-link into ``/storyboard`` for corpus ``name`` (mirrors
    ``desk._storyboard_href`` — the same composition, kept local so this reader
    has no dependency on the desk module)."""
    href = "/storyboard?corpus=" + quote(name, safe="")
    if anchor:
        href += "#" + quote(str(anchor), safe="")
    return href


def _artefact_href(name: str) -> str:
    """A deep-link into ``/artefact`` for corpus ``name`` (mirrors
    ``dashboard._artefact_href``)."""
    return "/artefact?corpus=" + quote(name, safe="")


def _first_clause(text: str) -> str:
    """The first sentence of ``text`` — up to the first ``.``/``!``/``?``
    followed by whitespace-or-end, stripped. The legible-title law: a banked
    finding's ``payload.note`` is often several sentences; the title carries
    only the first clause, never the whole paragraph."""
    text = (text or "").strip()
    if not text:
        return ""
    m = re.search(r"[.!?](?:\s|$)", text)
    return text[: m.start()].strip() if m else text.rstrip(".")


# ---------------------------------------------------------------------------
# rounds — <manuscript>/rounds/harnessed/detect_*.json (E6's round count)
# ---------------------------------------------------------------------------

def _rounds(ctx: "registry.ProjectContext | None") -> dict[str, Any]:
    """The harnessed round count: every ``detect_*.json`` under
    ``rounds/harnessed`` (pre-round and post-round both count — the plain
    "how many detect passes ran" read), plus the newest round ordinal found in
    any of their names. Absent dir → plainly ``{n: 0, last: None}``.

    TARGET-AWARE (the two-root repair, mirroring :func:`pipeline_surface.chain`
    and :func:`registry.project_states`' rounds_n): the harnessed rounds live
    under whichever base actually holds ``rounds/harnessed`` — a project whose
    ``target != manuscript`` (subset-sum-itqde: the rounds sit under the target,
    not the manuscript dir) read a false ``0`` when only the manuscript dir was
    consulted. Probe target-first, then manuscript; the first base that carries
    a non-empty harnessed dir wins (an empty dir under the target never masks a
    populated one under the manuscript)."""
    if ctx is None:
        return {"n": 0, "last": None}
    bases: list[Path] = []
    for cand in (getattr(ctx, "target_dir", None), getattr(ctx, "manuscript_dir", None)):
        if cand is not None and cand not in bases:
            bases.append(cand)
    for base in bases:
        h = base / "rounds" / "harnessed"
        try:
            if not h.is_dir():
                continue
            files = list(h.glob("detect_*.json"))
        except OSError:
            continue
        if not files:
            continue
        last: int | None = None
        for f in files:
            m = _ROUND_INT_RE.search(f.name)
            if m:
                r = int(m.group(1))
                last = r if last is None else max(last, r)
        return {"n": len(files), "last": last}
    return {"n": 0, "last": None}


# ---------------------------------------------------------------------------
# artefact — the minted name/path/date (release-side first), else the
# resolved current-artefact fact honestly labeled "never formally minted"
# ---------------------------------------------------------------------------

def _pdf_exists(p: Path) -> bool:
    """Whether the resolved artefact PDF is actually on disk. Declared absence
    (P7): a finalize.json can record a mint that was later superseded/removed (a
    reopened project past its old r1) — the reader must not present a recorded
    name as a live artefact when the bytes are gone."""
    try:
        return p.is_file()
    except OSError:
        return False


def _artefact(ctx: registry.ProjectContext | None, root: Path) -> dict[str, Any] | None:
    md = ctx.manuscript_dir if ctx is not None else None
    fin = None
    if md is not None:
        try:
            from laplace.pipeline import release
            fin = release._finalize_record(md)     # the same cross-module private
        except Exception:  # noqa: BLE001 — a corrupt/absent finalize.json degrades honestly
            fin = None
    if fin and fin.get("pdf_path"):
        pdf_path = md / fin["pdf_path"]
        return {"name": fin.get("slug") or Path(fin["pdf_path"]).stem,
                "path": _relposix(pdf_path, root), "minted_at": fin.get("created"),
                "exists": _pdf_exists(pdf_path)}
    art = (ctx.current_artefact if ctx is not None else None) or {}
    if art.get("pdf"):
        return {"name": art.get("version_id") or Path(art["pdf"]).stem,
                "path": art["pdf"], "minted_at": None,
                "exists": _pdf_exists(root / art["pdf"])}
    return None


# ---------------------------------------------------------------------------
# generations — the ledger's GEN-N + the debt trajectory (selection_sheet
# already computes debt_before/debt_after per generation; this only threads
# the chain into the one series E6 says is "materialized nowhere")
# ---------------------------------------------------------------------------

def _respine_intent(project: str, root: Path) -> dict[str, Any] | None:
    """THE open RESPINE-verb projection-intent (the field's own name: this is
    the RESPINE go/no-go, not a generic "any open plan-op" fallback — a CUT or
    other-verb open intent must never render as "the RESPINE"). The oldest
    open RESPINE row when several exist; ``None`` when none is open. Title
    built per the legible-title law: verb + object.key + first clause of the
    note (the RESPINE row PI-20260721-142526-161107's exact shape). Scoped to
    THIS project's own feedback ledger — never a cross-project leak."""
    proj = registry.resolve(project)
    if proj is None or not proj.feedback_ledger:
        return None
    fp = proj.path(proj.feedback_ledger, root)
    if fp is None or not fp.is_file():
        return None
    try:
        from laplace.pipeline.ledger import read_jsonl
        from laplace.pipeline import evolution_consumer as ec
        records = read_jsonl(fp)
        open_ops = ec.open_projection_intents(records)
    except Exception:  # noqa: BLE001 — an unreadable ledger degrades to "no open intent"
        return None
    respine = [r for r in open_ops if (r.get("verb") or "").upper() == "RESPINE"]
    if not respine:
        return None
    pick = sorted(respine, key=lambda r: str(r.get("ts") or ""))[0]
    obj = pick.get("object") or {}
    verb = pick.get("verb") or ""
    key = obj.get("key") or obj.get("kind") or ""
    note = (pick.get("payload") or {}).get("note") or ""
    clause = _first_clause(note)
    head = " ".join(x for x in (verb, key) if x)
    title = f"{head}: {clause}" if (head and clause) else (head or clause or pick.get("id") or "")
    anchor = (obj.get("sid") or obj.get("section") or "").strip()
    return {"id": pick.get("id"), "verb": verb, "object_key": key, "title": title,
            "href": _storyboard_href(project, anchor)}


def _generations(project: str, md: Path | None, root: Path) -> dict[str, Any]:
    gens: list[dict] = []
    if md is not None:
        try:
            from laplace.pipeline import generation_ledger
            gens = generation_ledger.read_generations(md)
        except Exception:  # noqa: BLE001 — an unreadable ledger is honestly absent
            gens = []

    gen_label = None
    ns = [g.get("n") for g in gens if isinstance(g.get("n"), int)]
    if ns:
        gen_label = f"GEN-{max(ns)}"

    debt_trajectory: list[int] = []
    try:
        from laplace.pipeline import selection_sheet
        sheet = selection_sheet.read_selection(project, root)
        if sheet.get("present"):
            ordered = sorted(sheet.get("generations", []),
                             key=lambda g: (g.get("n") if isinstance(g.get("n"), int) else 0))
            for g in ordered:
                if not debt_trajectory and isinstance(g.get("debt_before"), int):
                    debt_trajectory.append(g["debt_before"])
                if isinstance(g.get("debt_after"), int):
                    debt_trajectory.append(g["debt_after"])
    except Exception:  # noqa: BLE001 — a selection-sheet hiccup never breaks the verdict
        debt_trajectory = []

    return {"present": bool(gens), "gen": gen_label,
            "debt_trajectory": debt_trajectory,
            "respine_intent": _respine_intent(project, root)}


# ---------------------------------------------------------------------------
# position + position_evidence — the honest label (P7): a real release-machine
# state renders as-is; a NEVER_RUN project with real rounds/generations/a
# minted artefact renders "pre-release", never bare "never run"; a project
# untouched by every reader renders "not started" (no fabricated activity).
# ---------------------------------------------------------------------------

def _position(row: dict[str, Any], artefact: dict[str, Any] | None,
             generations: dict[str, Any]) -> tuple[str, list[str]]:
    state = row.get("state") or "NEVER_RUN"
    rounds = int(row.get("rounds_n") or 0)

    if state != "NEVER_RUN":
        evidence = [f"release state machine: {state}"
                    + (f" (updated {row['updated']})" if row.get("updated") else "")]
        if rounds:
            evidence.append(f"{rounds} harnessed rounds")
        return state, evidence

    art_name = (artefact or {}).get("name")
    minted_at = (artefact or {}).get("minted_at")
    gen_label = generations.get("gen")
    gens_present = bool(generations.get("present"))

    # a bare candidate PDF with no rounds/generations/formal mint is a stray
    # build, not pipeline history — "not started" stays honest rather than
    # promoting it to "pre-release" on artefact-presence alone.
    has_history = bool(rounds) or gens_present or minted_at is not None
    if not has_history:
        return "not started", ["no release-machine run, no rounds, no minted artefact"]

    evidence: list[str] = []
    # ROUNDS VOCABULARY (ruled R2): every rounds count NAMES its mechanic in plain
    # words — this is the HARNESSED count (the dashboard/cockpit number), distinct
    # from the BANKED count analytics reports; naming it keeps the two from reading
    # as a contradiction across surfaces.
    if rounds and art_name:
        evidence.append(f"{rounds} harnessed rounds + {art_name} — predate the release machine")
    elif rounds:
        evidence.append(f"{rounds} harnessed rounds — predate the release machine")
    if minted_at:
        evidence.append(f"{art_name} minted {str(minted_at)[:10]} (release/finalize.json)")
    if gen_label:
        evidence.append(f"generation ledger: {gen_label}")

    rev = None
    if art_name:
        m = _MINTED_SLUG_REV_RE.search(art_name)
        rev = ("r" + m.group(1)) if m else None
    date_str = str(minted_at)[:10] if minted_at else None
    if rev and date_str:
        rev_part = f"{rev} minted {date_str}"
    elif rev:
        rev_part = rev
    elif date_str:
        rev_part = f"minted {date_str}"
    else:
        rev_part = None
    label_parts = [p for p in (gen_label, rev_part) if p]
    position = "pre-release" + (" — " + ", ".join(label_parts) if label_parts else "")
    return position, evidence


# ---------------------------------------------------------------------------
# next_act — the RESPINE ratify when it is the open intent, else the release
# machine's own next_action (registry already computes it; never re-derived)
# ---------------------------------------------------------------------------

def _generation_open(project: str, root: Path) -> dict[str, Any] | None:
    """An announced-but-unstamped generation: the newest ``generation-open`` record in
    this project's feedback ledger whose generation number exceeds the last stamped
    row in generations.jsonl. The stamp closes the window (stamp_generation writes the
    ``generation`` record; ``read_generations`` filters to it), so an open resolves to
    ``None`` the moment the reprojection completes — no manual retirement needed."""
    proj = registry.resolve(project)
    if proj is None or not proj.feedback_ledger:
        return None
    fp = proj.path(proj.feedback_ledger, root)
    if fp is None or not fp.is_file():
        return None
    try:
        from laplace.pipeline.ledger import read_jsonl
        opens = [r for r in read_jsonl(fp) if r.get("record") == "generation-open"]
    except Exception:  # noqa: BLE001 — an unreadable ledger degrades to "no open generation"
        return None
    if not opens:
        return None
    pick = sorted(opens, key=lambda r: str(r.get("ts") or ""))[-1]
    gen_n = pick.get("generation") or pick.get("gen") or pick.get("n")
    try:
        from laplace.pipeline import generation_ledger
        ctx = registry.project_context(project, root)
        stamped = generation_ledger.read_generations(ctx.manuscript_dir) if ctx else []
        last_n = max((g.get("n") or 0) for g in stamped) if stamped else 0
    except Exception:  # noqa: BLE001 — an unreadable stamp ledger keeps the open visible
        last_n = 0
    if isinstance(gen_n, int) and gen_n <= last_n:
        return None
    return {"id": pick.get("id"), "generation": gen_n,
            "brief": pick.get("brief"), "ts": pick.get("ts")}


def _next_act(row: dict[str, Any], respine: dict[str, Any] | None,
              gen_open: dict[str, Any] | None = None) -> dict[str, Any]:
    if respine is not None:
        return {"verb": "ratify", "target": respine.get("id"),
                "label": "ratify the RESPINE — " + (respine.get("title") or respine.get("id") or ""),
                "href": respine.get("href"), "cost_class": "cheap", "psu": "none"}
    if gen_open is not None:
        gen_word = f"gen-{gen_open['generation']}" if gen_open.get("generation") else "a new generation"
        brief = gen_open.get("brief")
        # gen_word + brief ride as their own fields so a caller can phrase a door face
        # (the verb) and drop the raw brief path to audit depth; the composed label keeps
        # the path for the plain readers that render it as one sentence.
        return {"verb": "reproject", "target": gen_open.get("id"),
                "label": f"reproject — {gen_word} is open" + (f" (brief: {brief})" if brief else ""),
                "gen_word": gen_word, "brief": brief,
                "href": None, "cost_class": "model-heavy", "psu": "banks a work order"}
    return {"verb": None, "target": None, "label": row.get("next_action"),
            "href": None, "cost_class": None, "psu": None}


# ---------------------------------------------------------------------------
# owed_to_author — the RESPINE intent (when open) + this project's own
# author-gated open-stack-forks (scoped by the row's ``corpus`` field — an
# engine-wide fork carrying none is correctly excluded, never leaked in)
# ---------------------------------------------------------------------------

def _owed_to_author(root: Path, project: str,
                    respine: dict[str, Any] | None) -> list[dict[str, Any]]:
    owed: list[dict[str, Any]] = []
    if respine is not None:
        owed.append({"id": respine.get("id"), "kind": "projection-intent",
                     "title": respine.get("title"), "href": respine.get("href")})
    try:
        from laplace.engine import open_stack_store
        # the OPEN frontier, not the raw live set: a fork a worded desk ruling retired must
        # not stay counted here — the badge and the desk listing read the same store the
        # same way, or "1 decision waits" points at a desk that shows nothing (the 07-23
        # F39 mismatch).
        forks = open_stack_store.open_forks(root)
    except Exception:  # noqa: BLE001 — an unreadable fork store is honestly empty
        forks = []
    for f in forks:
        if f.get("corpus") != project:
            continue
        title = (f.get("title") or f.get("id") or "").replace("**", "").strip()
        owed.append({"id": f.get("id"), "kind": "open-stack-fork",
                     "title": title, "href": _artefact_href(project)})
    return owed


# ---------------------------------------------------------------------------
# THE COMPOSITION
# ---------------------------------------------------------------------------

def project_verdict(repo_root: Path | str, project: str) -> dict[str, Any]:
    """The one typed verdict for ``project`` — a JOIN of the readers named at
    module top, never a parallel computation. An unregistered project (or any
    reader raising outside its own guard) yields ``{present: False, project}``
    rather than propagating — the truth layer degrades plainly, it never 500s
    a card."""
    root = Path(repo_root).resolve()
    try:
        row = next((r for r in registry.project_states(root) if r["name"] == project), None)
    except Exception:  # noqa: BLE001 — a roster-wide hiccup still yields one honest verdict
        row = None
    if row is None:
        return {"present": False, "project": project}

    try:
        ctx = registry.project_context(project, root)
    except Exception:  # noqa: BLE001 — context resolution never blocks the rest of the verdict
        ctx = None
    md = ctx.manuscript_dir if ctx is not None else None

    artefact = _artefact(ctx, root)
    generations = _generations(project, md, root)
    respine = generations.get("respine_intent")
    rounds = _rounds(ctx)
    position, position_evidence = _position(row, artefact, generations)
    next_act = _next_act(row, respine, _generation_open(project, root))
    owed_to_author = _owed_to_author(root, project, respine)
    # G2 — the growth ladder rung, joined through the ONE growth producer
    # (growth.growth_state) exactly as every other field is joined from the reader that
    # owns it. A project on the ladder carries its rung; a released/converged paper with
    # no sidecar renders the plain pre-ladder null (never a fake SEEDED).
    try:
        from laplace.pipeline import growth
        growth_row = growth.growth_state(root, project)
    except Exception:  # noqa: BLE001 — the growth field degrades to absent, never 500s a card
        growth_row = {"present": False, "state": None, "pre_ladder": False,
                      "reason": "growth read unavailable"}

    return {
        "present": True,
        "project": project,
        "position": position,
        "position_evidence": position_evidence,
        "artefact": artefact,
        "generations": generations,
        "rounds": rounds,
        "growth": growth_row,
        "next_act": next_act,
        "owed_to_author": owed_to_author,
    }
