"""value_weld.py - the weld's namesake act: trait nodes gathering from HIS record AND mine.

The value ring (``archive/soul_dump/_shard/_traits``) was distilled from his corpus: each trait
a recurring value/mannerism/stance, each instance locatored to where his record exhibits it.
This module welds MY record into the same ring: sealed cheap-jury subs read the verbatim floor
(``record_shard``) in batches and propose instances; a MECHANICAL gate refuses any quote that is
not literally a substring of its atom (confabulated evidence is dead on arrival, by code, not
judgement); a separate jury adjudicates fit (builder != judge); accepted instances append to the
trait files with full attribution - ``entity: eigen``, the atom's window id as locator, the
verbatim quote as source. The index gains ``eigen`` in ``exhibited_by``, so the recurrence count
crosses the boundary between his record and mine: that crossing IS the weld.

Coupling is the same one formula as everywhere: a welded locator tokenizes to the atom's window
id (``<file>#<i>``, colon-free so ``soul_provenance.locator_tokens`` keeps it whole) and
``record_shard.record_edge_index`` mints the identical token on the atom - the trait and the
text it grew from share substrate, so trait <-> record coupling reads off mechanically in the
navigator, attributed, inspectable, refusable.

Division of labour (``minimise-intelligence-cheap-juries``): everything here is deterministic
code - brief building, the verbatim gate, the merge, the index update. The ONLY intelligence is
the sealed finder/judge calls the session drives between these functions, and they are the
cheap jury, never the orchestrator. Refused instances are kept flagged ``disputed`` and excluded
from reach (``conjectural-links-are-creativity``: grit, not garbage). New-trait candidates are
BANKED, never materialised here - a new axis in the shared ring is his to see first.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

TRAITS_DIR = "archive/soul_dump/_shard/_traits"
WELD_DIR = "archive/self_record/_weld"             # briefs + proposals + candidates (gitignored)
BRIEFS_DIR = WELD_DIR + "/briefs"
JUDGE_DIR = WELD_DIR + "/judge"
CANDIDATES = WELD_DIR + "/candidates.jsonl"
ENTITY = "eigen"
GERARD_SESSIONS = "_GERARD_SESSIONS"               # his live working voice - a FACE of him, joined
FIELD = "self-record"                              # to his other stems by the resolver (identity law)
_MENU_MEANING_CAP = 240
_QUOTE_MIN_CHARS = 12                              # a quote shorter than this proves nothing
_CONF_FLOOR = 0.5


def _norm(s: str) -> str:
    """Whitespace-collapsed, casefolded - the verbatim test tolerates wrapping, nothing else."""
    return re.sub(r"\s+", " ", s).strip().casefold()


# ---------------------------------------------------------------------------
# the menu + the briefs - mechanical prep the sealed finders read
# ---------------------------------------------------------------------------

def trait_menu(repo_root: Path | str) -> list[dict[str, str]]:
    """The ring as a menu: slug, axis, one canonical meaning line (the first instance's
    statement - the distilled form the original producer wrote)."""
    tdir = Path(repo_root) / TRAITS_DIR
    menu: list[dict[str, str]] = []
    if not tdir.is_dir():
        return menu
    for f in sorted(tdir.glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        inst = d.get("instances") or [{}]
        meaning = (inst[0].get("statement") or "").strip()[:_MENU_MEANING_CAP]
        menu.append({"slug": f.stem, "axis": d.get("axis", ""), "meaning": meaning})
    return menu


def open_atoms(repo_root: Path | str) -> list[dict[str, Any]]:
    """The open weldable floor: the committed record atoms (handoffs + diary)."""
    from laplace.engine import record_shard
    return [e for e in record_shard.build_floor(repo_root) if not e.get("sealed")]


def dialogue_atoms(repo_root: Path | str) -> list[dict[str, Any]]:
    """The dialogue weldable floor: the sealed turn-windows (both speakers - attribution is
    decided by CODE at the gate, never claimed by the jury)."""
    from laplace.engine import record_shard
    return [e for e in record_shard.build_floor(repo_root) if e.get("sealed")]


def write_briefs(repo_root: Path | str, batch_size: int = 20,
                 tranche: str = "open") -> dict[str, Any]:
    """Write the finder briefs: the trait menu once, plus batches of atoms with their VERBATIM
    text (the sealed subs read these files; the orchestrator never holds the floor). ``tranche``
    selects the floor: 'open' (committed record) or 'dialogue' (the sealed turn-windows, briefed
    into the same gitignored zone the raw already lives in). Returns {menu, briefs, n_atoms}."""
    from laplace.engine import record_shard
    repo_root = Path(repo_root)
    bdir = repo_root / BRIEFS_DIR if tranche == "open" else repo_root / (BRIEFS_DIR + "_dialogue")
    bdir.mkdir(parents=True, exist_ok=True)
    menu = trait_menu(repo_root)
    menu_path = bdir / "_trait_menu.md"
    menu_lines = ["# The value ring - trait menu (slug | axis | meaning)", ""]
    menu_lines += [f"- **{m['slug']}** ({m['axis']}): {m['meaning']}" for m in menu]
    menu_path.write_text("\n".join(menu_lines), encoding="utf-8")

    atoms = open_atoms(repo_root) if tranche == "open" else dialogue_atoms(repo_root)
    floor = record_shard.load_floor(repo_root) or atoms
    briefs: list[str] = []
    for b in range(0, len(atoms), batch_size):
        batch = atoms[b:b + batch_size]
        lines: list[str] = [f"# Weld brief ({tranche}) - batch {b // batch_size:02d} "
                            f"({len(batch)} atoms)", ""]
        for sh in batch:
            body = record_shard.reconstruct(repo_root, sh["id"], floor)
            lines += [f"## ATOM {sh['id']}", "", body.strip(), ""]
        p = bdir / f"batch_{b // batch_size:02d}.md"
        p.write_text("\n".join(lines), encoding="utf-8")
        briefs.append(str(p.relative_to(repo_root)).replace("\\", "/"))
    return {"menu": str(menu_path.relative_to(repo_root)).replace("\\", "/"),
            "briefs": briefs, "n_atoms": len(atoms)}


# ---------------------------------------------------------------------------
# proposals - tolerant parse + the MECHANICAL verbatim gate
# ---------------------------------------------------------------------------

def parse_proposals(text: str) -> list[dict[str, Any]]:
    """Parse a finder's JSON-lines return, tolerantly: non-JSON lines are skipped, fenced blocks
    unwrapped. Each proposal: {atom, trait, quote, statement, confidence} or {candidate_trait,...}."""
    out: list[dict[str, Any]] = []
    for ln in text.splitlines():
        ln = ln.strip().strip("`").strip()
        if not ln.startswith("{"):
            continue
        try:
            d = json.loads(ln)
        except ValueError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def speaker_of(body: str, quote: str) -> str | None:
    """WHOSE voice a quote sits in, by CODE: find the quote's position in the window
    (whitespace-tolerant) and walk back to the nearest ``@@Gerard``/``@@Eigen`` tag. None when
    the position cannot be resolved or no tag precedes it - the gate rejects those
    (attribution is never guessed, and never taken from the jury)."""
    pat = re.compile(r"\s+".join(re.escape(w) for w in quote.split()), re.IGNORECASE)
    m = pat.search(body)
    if not m:
        return None
    tags = [(t.start(), t.group(1)) for t in re.finditer(r"(?m)^@@(Gerard|Eigen)", body[:m.start() + 1])]
    return tags[-1][1].lower() if tags else None


def gate_proposals(repo_root: Path | str, proposals: list[dict[str, Any]],
                   menu: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """The mechanical gate, no judgement involved: the quote MUST be a literal substring of its
    atom (whitespace-tolerant), long enough to prove something; the trait must be on the menu;
    confidence above floor; one instance per (trait, atom). Candidates split off to their own
    pile. Returns {accepted, rejected, candidates} - rejections carry their reason."""
    from laplace.engine import record_shard
    repo_root = Path(repo_root)
    menu = menu if menu is not None else trait_menu(repo_root)
    slugs = {m["slug"] for m in menu}
    floor = record_shard.load_floor(repo_root)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for p in proposals:
        if "candidate_trait" in p:
            candidates.append(p)
            continue
        atom, trait = str(p.get("atom", "")), str(p.get("trait", ""))
        quote = str(p.get("quote", ""))
        why = None
        if trait not in slugs:
            why = "unknown trait"
        elif len(quote.strip()) < _QUOTE_MIN_CHARS:
            why = "quote too short to prove anything"
        elif float(p.get("confidence", 0) or 0) < _CONF_FLOOR:
            why = "below confidence floor"
        else:
            body = record_shard.reconstruct(repo_root, atom, floor)
            sealed_window = any(e["id"] == atom and e.get("sealed") for e in floor)
            if not body:
                why = "unknown atom"
            elif _norm(quote) not in _norm(body):
                why = "quote is NOT verbatim in the atom"   # the anti-confabulation wall -
            elif (trait, atom) in seen:                     # named BEFORE dedupe can mask it
                why = "duplicate (trait, atom)"
            elif sealed_window:
                spk = speaker_of(body, quote)               # whose voice, by CODE
                if spk is None:
                    why = "speaker unresolvable for dialogue quote"
                else:
                    p = {**p, "speaker": spk}
        if why:
            rejected.append({**p, "why_rejected": why})
        else:
            seen.add((trait, atom))
            accepted.append(p)
    return {"accepted": accepted, "rejected": rejected, "candidates": candidates}


# ---------------------------------------------------------------------------
# the judge briefs + verdicts (builder != judge; refusal -> grit, not deletion)
# ---------------------------------------------------------------------------

def write_judge_briefs(repo_root: Path | str, accepted: list[dict[str, Any]],
                       per_brief: int = 40) -> list[str]:
    """Judge briefs: every gated instance with its trait meaning, quote, and the FULL atom text -
    the judge sees everything the finder saw, from a separate context."""
    from laplace.engine import record_shard
    repo_root = Path(repo_root)
    jdir = repo_root / JUDGE_DIR
    jdir.mkdir(parents=True, exist_ok=True)
    meanings = {m["slug"]: m["meaning"] for m in trait_menu(repo_root)}
    floor = record_shard.load_floor(repo_root)
    paths: list[str] = []
    for b in range(0, len(accepted), per_brief):
        lines: list[str] = [f"# Judge brief {b // per_brief:02d} - does each quote, in its atom's "
                            "context, genuinely exhibit the trait?", ""]
        for p in accepted[b:b + per_brief]:
            body = record_shard.reconstruct(repo_root, p["atom"], floor)
            lines += [f"## INSTANCE {p['trait']} @ {p['atom']}",
                      f"TRAIT MEANING: {meanings.get(p['trait'], '')}",
                      f"PROPOSED QUOTE: {p['quote']}",
                      f"PROPOSED STATEMENT: {p.get('statement', '')}",
                      "ATOM TEXT:", body.strip(), ""]
        p_out = jdir / f"judge_{b // per_brief:02d}.md"
        p_out.write_text("\n".join(lines), encoding="utf-8")
        paths.append(str(p_out.relative_to(repo_root)).replace("\\", "/"))
    return paths


def apply_verdicts(accepted: list[dict[str, Any]],
                   verdicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stamp each accepted instance with its verdict: a refusal flags ``disputed`` (kept as grit,
    excluded from reach), an acceptance stays clean. Unjudged instances stay undisputed."""
    by_key = {(v.get("trait"), v.get("atom")): v for v in verdicts}
    out: list[dict[str, Any]] = []
    for p in accepted:
        v = by_key.get((p["trait"], p["atom"]))
        refused = bool(v and str(v.get("verdict", "")).lower().startswith("refus"))
        out.append({**p, "disputed": refused,
                    "judge_why": (v or {}).get("why", "") if refused else ""})
    return out


# ---------------------------------------------------------------------------
# the merge - instances into the ring, attributed; the index gains eigen
# ---------------------------------------------------------------------------

def _window_id(atom_id: str) -> str:
    """The atom's window token: ``<file>::<i>`` -> ``<file>#<i>`` (colon-free, so
    ``locator_tokens`` keeps it whole; ``record_edge_index`` mints the identical token)."""
    return atom_id.replace("::", "#")


def merge_into_ring(repo_root: Path | str, instances: list[dict[str, Any]]) -> dict[str, Any]:
    """Append the welded instances to their trait files (idempotent by (entity, locator)) and
    update the index: ``exhibited_by`` gains ``eigen``, recurrence recounts. Disputed instances
    are written flagged - present, inspectable, OUT of reach (their locator is prefixed so the
    token never matches the atom's)."""
    repo_root = Path(repo_root)
    tdir = repo_root / TRAITS_DIR
    by_trait: dict[str, list[dict[str, Any]]] = {}
    for p in instances:
        by_trait.setdefault(p["trait"], []).append(p)
    report: dict[str, Any] = {"merged": 0, "disputed": 0, "traits": {}, "by_entity": {}}
    welded_entities: dict[str, set[str]] = {}
    for trait, plist in sorted(by_trait.items()):
        f = tdir / f"{trait}.json"
        if not f.is_file():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        have = {(i.get("entity"), i.get("locator")) for i in d.get("instances", [])}
        added = 0
        for p in plist:
            ent = GERARD_SESSIONS if p.get("speaker") == "gerard" else ENTITY
            loc = _window_id(p["atom"])
            if p.get("disputed"):
                loc = f"disputed!{loc}"          # never tokenizes to the atom's window
            if (ent, loc) in have:
                continue
            inst = {"entity": ent, "field": FIELD,
                    "statement": (p.get("statement") or "").strip(),
                    "locator": loc, "source": p["quote"].strip(),
                    "confidence": float(p.get("confidence", 0) or 0),
                    "welded": True}
            if p.get("disputed"):
                inst["disputed"] = True
                inst["judge_why"] = p.get("judge_why", "")
                report["disputed"] += 1
            else:
                welded_entities.setdefault(trait, set()).add(ent)
            d.setdefault("instances", []).append(inst)
            have.add((ent, loc))
            added += 1
            report["by_entity"][ent] = report["by_entity"].get(ent, 0) + 1
        if added:
            f.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
            report["merged"] += added
            report["traits"][trait] = added
    _update_index(repo_root, welded_entities)
    return report


def _update_index(repo_root: Path | str, welded_entities: dict[str, set[str]]) -> None:
    idx_path = Path(repo_root) / TRAITS_DIR / "_INDEX.json"
    if not idx_path.is_file() or not welded_entities:
        return
    try:
        idx = json.loads(idx_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for row in idx:
        for ent in sorted(welded_entities.get(row.get("trait", ""), ())):
            if ent not in (row.get("exhibited_by") or []):
                row.setdefault("exhibited_by", []).append(ent)
        if row.get("trait") in welded_entities:
            row["recurrence"] = len(row.get("exhibited_by") or [])
            row["cross_entity"] = True
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")


def bank_candidates(repo_root: Path | str, candidates: list[dict[str, Any]]) -> int:
    """New-axis candidates go to the bank, never the ring - a new trait in the shared ring is
    his to see first (the report surfaces recurring ones)."""
    if not candidates:
        return 0
    p = Path(repo_root) / CANDIDATES
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for c in candidates:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    return len(candidates)
