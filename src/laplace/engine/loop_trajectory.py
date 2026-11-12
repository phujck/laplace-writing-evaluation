"""loop_trajectory.py — the reader organ behind /analytics, rebuilt as THE LOOP'S
INTERROGATION SURFACE (ARMING_2026-07-16 · TRAJECTORY SURFACE).

Reads the banked LOOP_TRAJECTORY records — the numerical spine
(``evidence/LOOP_TRAJECTORY_<date>.jsonl``) plus the per-round semantic channel
(``evidence/LOOP_TRAJECTORY_<date>_round<N>.md``), the reader ledgers, and the form-lens
retrieval sidecars — and returns ONE structured payload the surface renders. It is a PURE
READER: no writes, no model, no re-derivation of the loop. It is the organ, not the paint —
``analytics.py`` routes to it, ``analytics.html`` renders what it returns, and rerunning it
mints the same payload from the same banked records (the infrastructure law).

The honesty law, mechanised (the round-1 law wearing a face): every number carries its
DOOR — the primary-record path it was read from, tagged ``exists`` — and a claimed count
with no banked record is surfaced as ``absent`` alongside what IS banked, never narrated to
one clean figure. The census row (:func:`census`) totals banked-vs-absent so the surface
can say it plainly.
"""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import re
from pathlib import Path
from typing import Any, Optional


# ------------------------------------------------------------------ repo / records
def _repo_root(start: Optional[Path] = None) -> Path:
    """The repo root — the nearest ancestor carrying ``evidence/`` (where the trajectory
    records bank). Falls back to this file's grandparent-of-src."""
    here = (start or Path(__file__)).resolve()
    for p in [here, *here.parents]:
        if (p / "evidence").is_dir() and (p / "CLAUDE.md").is_file():
            return p
    # src/laplace/engine/loop_trajectory.py -> repo is parents[2]
    return source_tree()


def _jsonl_path(repo: Path) -> Optional[Path]:
    """The newest ``LOOP_TRAJECTORY_<date>.jsonl`` under ``evidence/`` (the numerical spine).
    Newest by filename so a later night's run supersedes without a code change."""
    cands = sorted((repo / "evidence").glob("LOOP_TRAJECTORY_*.jsonl"))
    # exclude the _round<N>.md siblings (different suffix) — glob already excludes .md
    cands = [p for p in cands if p.suffix == ".jsonl"]
    return cands[-1] if cands else None


def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def load_rounds(repo: Optional[Path] = None) -> tuple[list[dict], Optional[Path]]:
    """The raw round records (numerical spine), round-int ordered, plus the source path."""
    repo = repo or _repo_root()
    jp = _jsonl_path(repo)
    if jp is None:
        return [], None
    rounds = _read_jsonl(jp)
    rounds.sort(key=lambda r: int(r.get("round") or 0))
    return rounds, jp


# ------------------------------------------------------------------ the door primitive
def _door(repo: Path, relpath: Optional[str], label: str = "") -> dict:
    """A DOOR — the primary-record a number opens onto. ``exists`` is checked so an
    absent record reads ``absent``, never a live-looking link to nothing. ``relpath`` is
    repo-relative; ``None`` means the payload names no primary record (itself a finding)."""
    if not relpath:
        return {"path": None, "exists": False, "label": label or "no primary record on disk"}
    # a door may name a file plus an in-file anchor "path#anchor" — check the file half
    filepart = relpath.split("#", 1)[0]
    exists = (repo / filepart).exists()
    return {"path": relpath, "exists": exists, "label": label or filepart}


# ------------------------------------------------------------------ semantic channel (md)
_F_HEAD_RE = re.compile(r"^\*\*(F\d+)\s*·\s*(.+?)\*\*", re.M)
_LOCUS_HEAD_RE = re.compile(r"^\*\*(Locus [A-Z])\s*—\s*(.+?)\.\*\*", re.M)


def _md_path(repo: Path, jsonl_path: Optional[Path], rnd: int) -> Optional[Path]:
    """The per-round semantic md sibling of the jsonl (``..._round<N>.md``)."""
    if jsonl_path is None:
        return None
    p = jsonl_path.with_name(jsonl_path.stem + f"_round{rnd}.md")
    return p if p.is_file() else None


def _block_quote_after(text: str, start: int) -> str:
    """The contiguous ``> `` block-quote beginning at/after ``start`` (one exemplar span),
    joined to one line. Empty when none follows before a blank/non-quote line."""
    lines = text[start:].splitlines()
    got: list[str] = []
    seen = False
    for ln in lines:
        s = ln.rstrip()
        if s.startswith(">"):
            seen = True
            got.append(s.lstrip("> ").rstrip())
        elif seen:
            break
    return " ".join(g for g in got if g).strip()


def _parse_semantic(md_text: str) -> dict:
    """Verbatim exemplar findings (section 1) + before/ruled-target loci (section 2) from
    the semantic md. Structural parse (the ``**F<n> ·**`` + ``> quote`` idiom the record
    authors to); degrades to empty lists when a section is shaped differently."""
    findings: list[dict] = []
    for m in _F_HEAD_RE.finditer(md_text):
        quote = _block_quote_after(md_text, m.end())
        findings.append({"tag": m.group(1), "label": m.group(2).strip(), "quote": quote})
    loci: list[dict] = []
    for m in _LOCUS_HEAD_RE.finditer(md_text):
        before = _block_quote_after(md_text, m.end())
        tail = md_text[m.end():]
        rt = re.search(r"RULED TARGET:\s*(.+?)(?:\n\n|\n\*\*|\Z)", tail, re.S)
        after = None
        am = re.search(r"AFTER(?:\s*\(applied\))?:\s*", tail)
        if am:
            after = _block_quote_after(tail, am.end())
        loci.append({
            "locus": m.group(1), "label": m.group(2).strip(),
            "before": before,
            "ruled_target": (rt.group(1).strip().replace("\n", " ") if rt else None),
            "after": after,
        })
    return {"findings": findings, "loci": loci}


# ------------------------------------------------------------------ reader exemplars
def _reader_ledger(repo: Path, corpus: str, rnd: int) -> tuple[Optional[dict], str]:
    rel = f"{corpus}/manuscript/feedback/reader_ledger_r{rnd}.json"
    p = repo / rel
    if not p.is_file():
        return None, rel
    try:
        return json.loads(p.read_text(encoding="utf-8", errors="replace")), rel
    except (OSError, json.JSONDecodeError):
        return None, rel


# ------------------------------------------------------------------ lens retrieval sidecars
def _lens_sidecars(repo: Path, corpus: str) -> tuple[list[dict], str]:
    """The form-lens retrieval sidecars banked beside the dispatches — one per section the
    lens fired on, each carrying the exemplar rows it served (row_id + cosine). This is the
    'drill a round -> its retrieval sidecars -> the exemplar rows served' provenance leg."""
    rel_dir = f"{corpus}/manuscript/dispatches"
    d = repo / rel_dir
    out: list[dict] = []
    if not d.is_dir():
        return out, rel_dir
    for p in sorted(d.glob("_form_retrieval.*.json")):
        try:
            sc = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        # filename: _form_retrieval.<store>.<section>.json
        parts = p.stem.split(".")
        store = parts[1] if len(parts) > 1 else sc.get("store", "?")
        section = parts[-1] if len(parts) > 2 else "?"
        out.append({
            "store": store, "section": section,
            "k": sc.get("k"), "n_exemplars": sc.get("n_exemplars"),
            "query_digest": sc.get("query_digest"),
            "exemplars": [{"row_id": e.get("row_id"), "cos": e.get("cos")}
                          for e in (sc.get("exemplars") or [])],
            "door": {"path": f"{rel_dir}/{p.name}", "exists": True, "label": p.name},
        })
    return out, rel_dir


# ------------------------------------------------------------------ verdict / contest join
def _load_verdicts(repo: Path) -> list[dict]:
    p = repo / "proxy_verdicts.jsonl"
    return _read_jsonl(p) if p.is_file() else []


def _contest_for(verdicts: list[dict], ruling_id: str) -> list[dict]:
    """Any banked ``kind:contest`` record that names this ruling — the contest DOOR made
    real (his 'veto retrospective via contest records'). Empty list = uncontested."""
    out = []
    for v in verdicts:
        if v.get("kind") == "contest" and (
                ruling_id in json.dumps(v, ensure_ascii=False)):
            out.append({"id": v.get("id"), "date": v.get("date"),
                        "note": (v.get("ruling") or v.get("question") or "")[:200]})
    return out


# ------------------------------------------------------------------ per-round detail
def _int(v: Any) -> Optional[int]:
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def _classes(raw: dict) -> dict:
    mech = (raw.get("findings") or {}).get("mechanical_open") or {}
    return dict(mech.get("classes") or {})


def _mech_total(raw: dict) -> Optional[int]:
    mech = (raw.get("findings") or {}).get("mechanical_open") or {}
    return _int(mech.get("total"))


def round_detail(repo: Optional[Path], rnd: int) -> dict:
    """The full drill for one round: classes (with the banked source door), reader
    exemplars (verbatim + ruling ref + door), lens retrieval sidecars (exemplar rows +
    door), the semantic before/after loci, intents, revision loci, recurring basins, gate
    scores, rulings joined with contest doors, and the GENUINELY-HIS residue — each figure
    a door, banked-or-absent."""
    repo = repo or _repo_root()
    rounds, jp = load_rounds(repo)
    raw = next((r for r in rounds if int(r.get("round") or 0) == rnd), None)
    if raw is None:
        return {"error": f"no banked round {rnd} in the trajectory record"}
    corpus = raw.get("corpus") or "paper_falqon"
    jp_rel = str(jp.relative_to(repo)) if jp else None
    verdicts = _load_verdicts(repo)

    mech = (raw.get("findings") or {}).get("mechanical_open") or {}
    mech_source = mech.get("banked_source")
    classes = _classes(raw)
    prev = next((r for r in rounds if int(r.get("round") or 0) < rnd), None)
    prev_classes = _classes(prev) if prev else {}
    class_rows = []
    for cls in sorted(set(classes) | set(prev_classes), key=lambda c: -(classes.get(c, 0))):
        now = classes.get(cls)
        was = prev_classes.get(cls)
        delta = (now or 0) - (was or 0) if (prev is not None) else None
        class_rows.append({"cls": cls, "count": now, "prev": was, "delta": delta})

    # reader exemplars (verbatim, banked) + the honest claimed-vs-banked gap
    led, led_rel = _reader_ledger(repo, corpus, rnd)
    reader = {
        "door": _door(repo, led_rel, "reader ledger"),
        "claimed": (led or {}).get("claimed_total"),
        "banked_verbatim": (led or {}).get("banked_verbatim"),
        "gap_note": (led or {}).get("gap_note") or (led or {}).get("note"),
        "findings": [
            {"reader": f.get("reader"), "where": f.get("where"), "kind": f.get("kind"),
             "quote": f.get("quote"), "ruling_ref": f.get("ruling_ref")}
            for f in ((led or {}).get("findings") or [])
        ],
    }
    reader_jsonl = (raw.get("findings") or {}).get("reader_new") or {}
    if reader["claimed"] is None:
        reader["claimed"] = reader_jsonl.get("claimed_total")
    if reader["banked_verbatim"] is None:
        reader["banked_verbatim"] = reader_jsonl.get("banked_verbatim")

    # lens retrieval sidecars (the exemplar rows served this run)
    sidecars, sc_dir = _lens_sidecars(repo, corpus)
    gen = raw.get("generation_lens") or {}
    lens = {
        "run": gen,
        "sidecars_on_disk": len(sidecars),
        "sidecars": sidecars,
        "sidecar_dir": sc_dir,
        "run_door": _door(repo, _lens_run_doc(repo), "lens-run record"),
    }

    # detector organs (THE CONJUGATE WAVE, Lane 1): the round-scoped detect census
    # (``<corpus>/rounds/detector_organs_<date>.json``) joins the round drill through
    # the organ's OWN pure reader — ``read_detector_organs`` does no compile / no
    # subprocess on the read (WIRING LAW 2), and this join re-parses nothing (RISK 1).
    # The census is DATE-keyed, so ``matches_round`` marks whether the newest banked
    # census IS this round's (its date == the round's date): a round with no detect run
    # of its own reads the newest census but ``matches_round`` False — never attributing
    # another round's detectors to this one (the same honesty-law door-tagging).
    from laplace.engine import detector_organs as _det
    dcen = _det.read_detector_organs(corpus, repo)
    detectors = {
        "present": bool(dcen.get("present")),
        "date": dcen.get("date", ""),
        "matches_round": bool(dcen.get("present")) and dcen.get("date") == raw.get("date"),
        "gaps": (dcen.get("gaps") or {}).get("gaps", 0),
        "meta_leak": (dcen.get("meta_leak") or {}).get("n", 0),
        "source_delta": (dcen.get("source_delta") or {}).get("n", 0),
        "promise": (dcen.get("promise") or {}).get("n", 0),
        "by_gap_class": (dcen.get("gaps") or {}).get("by_gap_class") or {},
        "promise_by_class": (dcen.get("promise") or {}).get("by_class") or {},
        "door": _door(repo, dcen.get("path"), "detector-organs census"),
    }

    # semantic before/after
    md = _md_path(repo, jp, rnd)
    if md is not None:
        semantic = _parse_semantic(md.read_text(encoding="utf-8", errors="replace"))
        semantic["door"] = {"path": str(md.relative_to(repo)), "exists": True,
                            "label": md.name}
        semantic["present"] = True
    else:
        semantic = {"present": False, "findings": [], "loci": [],
                    "door": _door(repo, None, "no semantic md banked for this round")}

    # rulings joined with contest doors
    rd = raw.get("rulings_drafted") or {}
    rulings = {
        "count": rd.get("count"),
        "by_confidence": rd.get("by_confidence"),
        "disposition": rd.get("disposition"),
        "provenance": rd.get("provenance"),
        "draft_door": _door(repo, rd.get("draft_path"), "rulings draft"),
        # each named GENUINELY-HIS residue joined to any contest record naming it
        "his_residue": [
            {"name": nm, "contests": _contest_for(verdicts, nm)}
            for nm in (raw.get("genuinely_his_names") or [])
        ],
    }

    gate = raw.get("gate_scores") or {}
    return {
        "round": rnd,
        "corpus": corpus,
        "date": raw.get("date"),
        "artefact": raw.get("artefact"),
        "spine_door": _door(repo, jp_rel, "numerical spine (jsonl)"),
        "findings": {
            "mech_total": _mech_total(raw),
            "mech_delta": ((_mech_total(raw) or 0) - (_mech_total(prev) or 0)
                           if (prev is not None and _mech_total(raw) is not None
                               and _mech_total(prev) is not None) else None),
            "classes": class_rows,
            "families": mech.get("families"),
            "note": mech.get("note"),
            "banked_source_door": _door(repo, _first_path(mech_source), "banked source"),
            "banked_source_text": mech_source,
        },
        "reader": reader,
        "lens": lens,
        "detectors": detectors,
        "semantic": semantic,
        "intents": raw.get("intents"),
        "revision_loci": raw.get("revision_loci"),
        "recurring_basins": raw.get("recurring_intents_basins"),
        "gate": {
            "hard": gate.get("contract_hard"),
            "soft": gate.get("contract_soft"),
            "panel": gate.get("panel"),
            "net_axis": gate.get("net_axis"),
            "hard_failing": gate.get("hard_failing"),
            "hard_fail_reason": gate.get("hard_fail_reason"),
            "open_findings": gate.get("open_findings", gate.get("open_findings_panel")),
        },
        "rulings": rulings,
        "genuinely_his_parked": raw.get("genuinely_his_parked"),
        "mint_proof": raw.get("mint_proof"),
        "held_out_prediction": raw.get("held_out_prediction_tracking"),
        "cost": {
            "tokens": raw.get("cost_tokens"),
            "wall_clock_min": raw.get("wall_clock_min_approx"),
            "mechanical": raw.get("mechanical_cost"),
        },
    }


def _first_path(text: Any) -> Optional[str]:
    """The first repo-relative path token inside a banked-source prose string (the source
    field is often 'path (n flags) + other'). None when no path-shaped token is present."""
    if not isinstance(text, str):
        return None
    m = re.search(r"[\w./-]+\.(?:json|jsonl|md|tex)", text)
    return m.group(0) if m else None


def _lens_run_doc(repo: Path) -> Optional[str]:
    cands = sorted((repo / "evidence").glob("LENS_RUN_*.md"))
    return str(cands[-1].relative_to(repo)) if cands else None


# ------------------------------------------------------------------ the board (cards)
def board(repo: Optional[Path] = None) -> dict:
    """The board payload: rounds as cards (finding total + the derivative visible, class
    mix, gate hard-fail, rulings, his-residue count, cost) + the census row + the top-level
    doors. The derivative (round-over-round Δ in the finding count) is the whole point —
    surfaced per card, computed from the banked totals, never narrated."""
    repo = repo or _repo_root()
    rounds, jp = load_rounds(repo)
    jp_rel = str(jp.relative_to(repo)) if jp else None
    cards = []
    prev_total: Optional[int] = None
    for raw in rounds:
        rnd = int(raw.get("round") or 0)
        total = _mech_total(raw)
        delta = (total - prev_total) if (total is not None and prev_total is not None) else None
        gate = raw.get("gate_scores") or {}
        rd = raw.get("rulings_drafted") or {}
        classes = _classes(raw)
        cards.append({
            "round": rnd,
            "corpus": raw.get("corpus"),
            "date": raw.get("date"),
            "mech_total": total,
            "mech_delta": delta,
            "top_classes": sorted(classes.items(), key=lambda kv: -kv[1])[:4],
            "n_classes": len(classes),
            "hard_failing": gate.get("hard_failing"),
            "hard_fail_reason": gate.get("hard_fail_reason"),
            "rulings_count": rd.get("count"),
            "rulings_by_confidence": rd.get("by_confidence"),
            "his_parked": raw.get("genuinely_his_parked"),
            "wall_clock_min": raw.get("wall_clock_min_approx"),
            "cost_tokens": raw.get("cost_tokens"),
            "semantic_present": _md_path(repo, jp, rnd) is not None,
        })
        prev_total = total if total is not None else prev_total
    return {
        "spine_door": _door(repo, jp_rel, "numerical spine (jsonl)"),
        "arming_door": _door(repo, _arming_doc(repo), "arming"),
        "rounds": cards,
        "census": census(repo, rounds),
    }


def _arming_doc(repo: Path) -> Optional[str]:
    cands = sorted(repo.glob("ARMING_2026-07-16_the-whole-loop.md"))
    return str(cands[-1].relative_to(repo)) if cands else None


# ------------------------------------------------------------------ the census row
def census(repo: Optional[Path] = None, rounds: Optional[list[dict]] = None) -> dict:
    """The honesty census: banked-vs-absent totals across the trajectory. Every count the
    surface shows rolls up here so 'banked-or-absent, never narrated' is a number, not a
    slogan — reader findings claimed vs banked, semantic records present vs absent, rulings
    banked, his-residue parked."""
    repo = repo or _repo_root()
    if rounds is None:
        rounds, _ = load_rounds(repo)
    n_rounds = len(rounds)
    mech_banked = sum((_mech_total(r) or 0) for r in rounds)
    reader_claimed = reader_banked = 0
    semantic_present = semantic_absent = 0
    rulings_banked = his_parked = 0
    _, jp = load_rounds(repo)
    for r in rounds:
        rn = int(r.get("round") or 0)
        led, _ = _reader_ledger(repo, r.get("corpus") or "paper_falqon", rn)
        rj = (r.get("findings") or {}).get("reader_new") or {}
        reader_claimed += (led or {}).get("claimed_total") or rj.get("claimed_total") or 0
        reader_banked += (led or {}).get("banked_verbatim") or rj.get("banked_verbatim") or 0
        if _md_path(repo, jp, rn) is not None:
            semantic_present += 1
        else:
            semantic_absent += 1
        rulings_banked += (r.get("rulings_drafted") or {}).get("count") or 0
        his_parked += r.get("genuinely_his_parked") or 0
    return {
        "rounds": n_rounds,
        "mech_findings_banked": mech_banked,
        "reader_claimed": reader_claimed,
        "reader_banked": reader_banked,
        "reader_absent": max(0, reader_claimed - reader_banked),
        "semantic_records_present": semantic_present,
        "semantic_records_absent": semantic_absent,
        "rulings_banked": rulings_banked,
        "genuinely_his_parked": his_parked,
    }
