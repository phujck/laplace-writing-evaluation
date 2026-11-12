#!/usr/bin/env python3
"""Structural deslop gate — the first consumer of the growth adjudicator.

His mandate: *"many of the conceptrics you start from are fundamentally thin, and
soaked in slogan slop."* This gate is the mechanical half of the fix. It reads a
conceptric (a ``corpus_friction/<name>.jsonl`` ledger of node essences, or a
projection ``.tex``/plan) and detects slop CANDIDATES mechanically — it never
decides and never edits. Every candidate becomes a growth-decision packet
(``kind:"deslop-keep-kill-rewrite"``) via
:mod:`laplace.pipeline.growth_adjudicator`, and the gate writes the dispatch
manifest the JUDGE leg consumes. The keep/kill/rewrite call is the author-proxy's,
not the gate's — the gate only surfaces.

Three detectors (the dead deslop-v2 design, rebuilt from its four names):

  (a) public-jargon lexicon — hits against a committed seed of slogan shapes,
      grown by the corpus's own deprecated-vocabulary set where a corpus is named.
      The lexicon is a DATA FILE (``deslop_lexicon.json``) the proxy's rulings can
      grow; allowlist entries carry a ``decays`` date, and an EXPIRED allowlist
      re-flags (allowlist-decay).
  (b) oracle-shape — absolute/claim-shaped sentences with no grounding edge in
      reach (no \\cite / [@ / \\ref): assertion presented as oracle truth.
  (c) antithesis-density — slogan tells ("not X but Y", "X, not Y", punchy copula
      aphorisms) above a per-unit density threshold.

VERDICT=PASS when no unit trips a detector, WARN when candidates are found. Exit
code is always 0 — v1 is advisory (report + manifest), never blocking, never editing.

Run:
  python3 scripts/deslop_gate.py --ledger corpus_friction/eigenengine.jsonl
  python3 scripts/deslop_gate.py --tex eigenengine/manuscript/Introducing-EigenEngine.tex
  python3 scripts/deslop_gate.py --ledger corpus_friction/eigenengine.jsonl --corpus eigenengine
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.engine import author_proxy  # noqa: E402
from laplace.pipeline import growth_adjudicator  # noqa: E402

# ------------------------------------------------------------------ the lexicon data
#: the data file the proxy's rulings grow. Seeded on first run from _SEED_JARGON.
DESLOP_LEXICON_NAME = "deslop_lexicon.json"

#: a small committed seed of slogan / AI-slop shapes — the public-jargon tells the
#: eigenengine page was "soaked in". Multi-word phrases match as substrings; single
#: tokens match on word boundaries. The proxy grows this list; it is not exhaustive.
_SEED_JARGON: tuple[str, ...] = (
    "leverage", "unlock", "seamless", "seamlessly", "robust", "cutting-edge",
    "state-of-the-art", "paradigm", "paradigm shift", "game-changer", "game changer",
    "synergy", "empower", "revolutionary", "revolutionize", "holistic", "disrupt",
    "disruptive", "at scale", "north star", "first-class", "delve", "tapestry",
    "testament to", "in the realm of", "ever-evolving", "landscape", "harness",
    "unleash", "supercharge", "next-generation", "best-in-class", "frictionless",
    "turnkey", "bleeding-edge", "world-class", "mission-critical", "deep dive",
    "low-hanging fruit", "move the needle", "boil the ocean", "double down",
    "value-add", "actionable insight", "thought leadership", "the power of",
)

#: a starter allowlist demonstrating decay. An entry suppresses its term ONLY while
#: unexpired; past ``decays`` it re-flags. The proxy's KEEP rulings append here.
_SEED_ALLOWLIST: tuple[dict, ...] = ()


def load_lexicon(repo_root: Path) -> dict:
    """Load (seeding on first run) the deslop lexicon data file. Shape:
    ``{"jargon": [...], "allowlist": [{"term","decays"}...]}``. Seeded from the
    committed constants when absent so the file is real, on disk, and growable."""
    path = repo_root / DESLOP_LEXICON_NAME
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        data.setdefault("jargon", list(_SEED_JARGON))
        data.setdefault("allowlist", list(_SEED_ALLOWLIST))
        return data
    data = {"jargon": list(_SEED_JARGON), "allowlist": list(_SEED_ALLOWLIST)}
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return data


def _active_allowset(lexicon: dict, today: str) -> set[str]:
    """The terms currently suppressed by a non-expired allowlist entry. An entry with
    ``decays`` <= today has DECAYED — it no longer suppresses, so the term re-flags."""
    active: set[str] = set()
    for entry in lexicon.get("allowlist", []):
        term = str(entry.get("term", "")).strip().lower()
        decays = str(entry.get("decays", "")).strip()
        if not term:
            continue
        # unexpired (future decay date, or no date at all) → suppress; else re-flag
        if not decays or decays > today:
            active.add(term)
    return active


# ------------------------------------------------------------------ the allowlist writer
# The reader (:func:`load_lexicon` / :func:`_active_allowset`) and its decay were built
# first, expecting a consumer that would GROW the allowlist from the proxy's KEEP
# rulings. This is that consumer — the named-but-unbuilt other half. It only APPENDS
# (with a decay date); a contest is a later decay, never an in-place delete.

def _ruling_is_keep(row: dict) -> bool:
    """A verdict row rules KEEP — tolerant of a bare ``"KEEP"`` or a ``"KEEP: ..."``
    lead in the ``ruling`` field."""
    ruling = str(row.get("ruling", "")).strip().upper()
    return ruling == "KEEP" or ruling.startswith("KEEP")


def _terms_kept(row: dict) -> list[str]:
    """The judge's echoed kept terms. Two shapes accepted (his StructuredOutput may
    carry either): a top-level ``terms_kept`` list on the ruling row, or one nested
    under the row's ``decision``. Empty when neither is a list."""
    for holder in (row, row.get("decision")):
        if isinstance(holder, dict) and isinstance(holder.get("terms_kept"), list):
            return [str(t).strip() for t in holder["terms_kept"] if str(t).strip()]
    return []


def _is_deslop_keep(row: dict) -> bool:
    """A growth ruling that KEPT terms on a deslop keep/kill/rewrite decision. Tolerant:
    the decision kind may be absent on older rows — a KEEP verdict plus a ``terms_kept``
    echo is taken as the deslop-keep signal — but when a decision kind IS present it must
    be ``"deslop-keep-kill-rewrite"``."""
    if row.get("kind") != "growth":
        return False
    dec = row.get("decision")
    dkind = dec.get("kind") if isinstance(dec, dict) else None
    if dkind is not None and dkind != "deslop-keep-kill-rewrite":
        return False
    return _ruling_is_keep(row) and bool(_terms_kept(row))


def apply_keep_rulings(repo_root: Path, rulings: list[dict] | None = None,
                       today: str | None = None, decay_days: int = 90) -> dict:
    """WRITE the proxy's KEEP rulings back into the lexicon's allowlist — the consumer
    the reader was built to expect.

    Reads ``proxy_verdicts.jsonl`` (or an explicit ``rulings`` list) for qualifying
    rows: ``kind=="growth"``, a KEEP verdict on a ``deslop-keep-kill-rewrite`` decision,
    carrying a ``terms_kept`` list (see :func:`_is_deslop_keep` / :func:`_terms_kept`
    for the tolerated shapes). Each kept term earns an allowlist entry
    ``{term, decays: <today+decay_days ISO>, ruling_id: <PV id>}``. IDEMPOTENT: a term
    already suppressed by an UNEXPIRED entry is skipped, never duplicated. The ``jargon``
    list is NEVER touched; a contest is a later decay, never an in-place delete here.
    Returns a summary ``{added, skipped, terms, decays}``."""
    import datetime as _dt
    today = today or _dt.date.today().isoformat()
    decays = (_dt.date.fromisoformat(today)
              + _dt.timedelta(days=decay_days)).isoformat()

    if rulings is None:
        from laplace.engine import author_proxy
        rulings = author_proxy.load_verdicts(repo_root)

    lexicon = load_lexicon(repo_root)              # seeds the file on first run
    allowlist = list(lexicon.get("allowlist", []))
    active = _active_allowset(lexicon, today)      # terms already live-suppressed

    added: list[str] = []
    skipped: list[str] = []
    for row in rulings:
        if not _is_deslop_keep(row):
            continue
        rid = str(row.get("id", ""))
        for term in _terms_kept(row):
            t = term.strip().lower()
            if not t:
                continue
            if t in active:                        # unexpired entry already holds it
                skipped.append(term)
                continue
            allowlist.append({"term": term, "decays": decays, "ruling_id": rid})
            active.add(t)                          # a later row for the same term dedups
            added.append(term)

    lexicon["allowlist"] = allowlist
    (repo_root / DESLOP_LEXICON_NAME).write_text(
        json.dumps(lexicon, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"added": len(added), "skipped": len(skipped),
            "terms": added, "decays": decays}


def corpus_deprecated_terms(corpus_name: str | None) -> list[str]:
    """The corpus's own retired-vocabulary set, folded into the jargon lexicon when a
    corpus is named — reuses the ONE public accessor ``verify.deprecated_vocabulary``.
    Empty on any failure (an unregistered corpus is not an error here)."""
    if not corpus_name:
        return []
    try:
        from laplace.pipeline.verify import deprecated_vocabulary
        return sorted(deprecated_vocabulary(corpus_name).keys())
    except Exception:
        return []


# ------------------------------------------------------------------ text extraction
def _strip_tex_commands(text: str) -> str:
    """Blank latex control sequences to bare prose, but PRESERVE a citation marker so
    the oracle-shape detector can see a grounding edge. \\cite{...} → ' [CITE] '."""
    text = re.sub(r"\\(?:cite[a-z]*|ref|eqref|autoref|footcite)\s*\{[^}]*\}", " [CITE] ",
                  text)
    text = re.sub(r"~\\cite[a-z]*\{[^}]*\}", " [CITE] ", text)
    text = re.sub(r"%.*", "", text)                       # comments
    text = re.sub(r"\\[a-zA-Z@]+\*?(\[[^\]]*\])?(\{[^}]*\})?", " ", text)  # other cmds
    text = re.sub(r"[{}$&]", " ", text)
    return text


def units_from_ledger(path: Path) -> list[dict]:
    """A conceptric ledger → one text unit per node essence. Each unit carries the
    node id so a candidate names its node."""
    units: list[dict] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        essence = (row.get("essence") or "").strip()
        node = row.get("node") or row.get("id") or "?"
        if not essence:
            continue
        key = f"{node} {essence}"
        if key in seen:
            continue
        seen.add(key)
        units.append({"where": str(node), "text": essence})
    return units


def units_from_tex(path: Path) -> list[dict]:
    """A projection .tex/plan → one text unit per blank-line-separated paragraph of
    prose (latex stripped, citation edges preserved). The paragraph is the natural
    'section' the antithesis-density threshold applies over."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    # drop the preamble up to \begin{document} if present
    m = re.search(r"\\begin\{document\}", raw)
    if m:
        raw = raw[m.end():]
    units: list[dict] = []
    for i, block in enumerate(re.split(r"\n\s*\n", raw)):
        prose = _strip_tex_commands(block).strip()
        prose = re.sub(r"\s+", " ", prose)
        if len(prose.split()) < 6:            # skip headings, stubs, float scaffolding
            continue
        units.append({"where": f"{path.name}#p{i}", "text": prose})
    return units


# ------------------------------------------------------------------ the detectors
# a grounding edge: a citation marker, a measured numeral, or an equation token. A
# claim standing on a number or a reference is grounded — only the UNgrounded absolute
# is oracle-shape. (This is what keeps measured technical prose — "77.9 d at 1 factory
# (111,840 physical qubits)" — from tripping as slop, while "safety is theatre" stays.)
_CITE_EDGE = re.compile(
    r"\[CITE\]|\[@|\\cite|\\ref|\(his[,\s]|\d|=|≈|≤|≥|\bI\(|β", re.I)
_ABSOLUTE = re.compile(
    r"\b(?:all|every|none|no one|nothing|always|never|only|any|the whole|"
    r"cannot|can only|must|will not|is not|are not|nobody|everything)\b", re.I)
_CLAIM_VERB = re.compile(
    r"\b(?:is|are|was|were|means|proves|shows|demonstrates|forbids?|makes?|"
    r"runs? on|does not|do not|will|cannot|must)\b", re.I)
_ANTITHESIS = (
    re.compile(r"\bnot\b[^.,;:]{1,50}?\bbut\b", re.I),   # "not X but Y"
    re.compile(r",\s*not\s+\w", re.I),                    # "X, not Y"
    re.compile(r"\bnot\s+\w+\s+problems?\s+but\b", re.I), # "not three problems but one"
)


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in parts if s.strip()]


def detect_jargon(text: str, jargon: list[str], allowset: set[str]) -> list[str]:
    low = text.lower()
    hits: list[str] = []
    for term in jargon:
        t = term.lower()
        if t in allowset:                     # suppressed by a live allowlist entry
            continue
        if " " in t or "-" in t:
            if t in low:
                hits.append(term)
        elif re.search(rf"\b{re.escape(t)}\b", low):
            hits.append(term)
    return hits


def detect_oracle(text: str) -> list[str]:
    """Absolute/claim-shaped sentences with NO grounding edge in reach — assertion as
    oracle truth. Requires an absolute quantifier AND a claim verb AND no citation."""
    out: list[str] = []
    for s in _sentences(text):
        if _CITE_EDGE.search(s):
            continue
        if _ABSOLUTE.search(s) and _CLAIM_VERB.search(s):
            out.append(s[:160])
    return out


def detect_antithesis(text: str) -> tuple[int, float, list[str]]:
    """Slogan-antithesis hits, plus density (hits per sentence). Returns
    ``(count, density, examples)``."""
    examples: list[str] = []
    count = 0
    for pat in _ANTITHESIS:
        for m in pat.finditer(text):
            count += 1
            if len(examples) < 4:
                examples.append(m.group(0).strip()[:80])
    n_sent = max(1, len(_sentences(text)))
    return count, count / n_sent, examples


# ------------------------------------------------------- ruled-essence suppression
# The dread metric: a gate that re-flags an essence the proxy has ALREADY adjudicated,
# and that has not changed since, makes every intervention cost again — the author pays
# to re-rule a settled line forever. Suppression is the fix. During a scan a unit that
# would fire is held back when a banked growth ruling already covers its node AND its
# CURRENT essence still matches the text that was ruled. Change the essence and the
# adjudication no longer covers it, so it flags again.
#
# WHAT THE BASIS IS (keyed against the real 23 eigenengine rulings). A growth ruling
# banks its subject as ``conceptric[<corpus>]:<node_id> :: <essence prefix>`` — but the
# subject carries only a LEADING SLICE of the essence (120 chars), and the row's
# question/context carry only truncated detector fragments; no field holds the full
# ruled essence. So the reliable ruled basis is:
#   * a REWRITE's ``rewrite_text`` (the FULL replacement line — once applied by
#     scripts/apply_growth_rulings it IS the new essence, matched in full); else
#   * the subject's `` :: `` essence prefix (the exact leading slice ruled at the time).
# An unchanged head is therefore the strongest "ruled and unchanged" signal the bank
# affords, and it is what suppression keys on.

class ScanResult(list):
    """The scan's candidate list, additively carrying ``suppressed_ruled`` — the count
    of units NOT emitted because a banked growth ruling already adjudicated their
    unchanged essence. It is a plain list to every existing consumer; the tally rides
    alongside."""
    suppressed_ruled: int = 0


def _ruled_node_id(subject: str, corpus_name: str) -> str | None:
    prefix = f"conceptric[{corpus_name}]:"
    if not subject.startswith(prefix):
        return None
    return subject[len(prefix):].split(" :: ", 1)[0].strip() or None


def load_ruled_essences(repo_root: Path, corpus_name: str | None,
                        rulings: list[dict] | None = None) -> dict[str, str]:
    """``{node_id: ruled_basis}`` from the banked growth rulings for this corpus's
    conceptric (subject prefix ``conceptric[<corpus_name>]:``). The basis is the full
    ``rewrite_text`` for a REWRITE, else the subject's `` :: `` essence prefix (see the
    section note). Empty when no corpus is named — so the scan is unchanged wherever no
    growth ruling applies."""
    if not corpus_name:
        return {}
    if rulings is None:
        rulings = author_proxy.load_verdicts(repo_root)
    prefix = f"conceptric[{corpus_name}]:"
    ruled: dict[str, str] = {}
    for row in rulings:
        if row.get("kind") != "growth":
            continue
        dec = row.get("decision")
        subject = dec.get("subject") if isinstance(dec, dict) else None
        if not (isinstance(subject, str) and subject.startswith(prefix)):
            continue
        nid = _ruled_node_id(subject, corpus_name)
        if not nid:
            continue
        is_rewrite = str(row.get("ruling", "")).strip().upper().startswith("REWRITE")
        rewrite = row.get("rewrite_text")
        if is_rewrite and isinstance(rewrite, str) and rewrite.strip():
            basis = rewrite.strip()
        else:
            basis = subject.split(" :: ", 1)[1].strip() if " :: " in subject else ""
        if basis:
            ruled[nid] = basis
    return ruled


def _essence_unchanged_since_ruling(current: str, basis: str) -> bool:
    """Unchanged-since-ruling ⇔ the current essence still LEADS with the ruled basis
    (full for a REWRITE, a leading slice for KEEP/KILL). A changed head means the
    adjudication no longer covers the text — it flags again."""
    b = basis.strip()
    return bool(b) and current.strip().startswith(b)


# ------------------------------------------------------------------ the gate
def scan(repo_root: Path, units: list[dict], corpus_name: str | None,
         today: str, antithesis_min: int, density_min: float,
         rulings: list[dict] | None = None) -> ScanResult:
    """Run the three detectors over every unit; return one candidate record per unit
    that trips at least one detector AND is not already ruled-and-unchanged. A unit that
    would fire is SUPPRESSED (counted in ``ScanResult.suppressed_ruled``) when a banked
    growth ruling covers its node and its current essence still matches the ruled basis;
    an essence that changed since the ruling flags normally."""
    lexicon = load_lexicon(repo_root)
    jargon = list(dict.fromkeys(list(lexicon.get("jargon", []))
                                + corpus_deprecated_terms(corpus_name)))
    allowset = _active_allowset(lexicon, today)
    ruled = load_ruled_essences(repo_root, corpus_name, rulings)

    candidates: list[dict] = []
    suppressed = 0
    for unit in units:
        text = unit["text"]
        jargon_hits = detect_jargon(text, jargon, allowset)
        oracle_hits = detect_oracle(text)
        ant_count, ant_density, ant_ex = detect_antithesis(text)
        antithesis_flag = ant_count >= antithesis_min or ant_density >= density_min

        tells: list[str] = []
        if jargon_hits:
            tells.append("public-jargon")
        if oracle_hits:
            tells.append("oracle-shape")
        if antithesis_flag:
            tells.append("antithesis-density")
        if not tells:
            continue

        basis = ruled.get(str(unit["where"]))
        if basis is not None and _essence_unchanged_since_ruling(text, basis):
            suppressed += 1                       # already adjudicated, unchanged → hold
            continue

        candidates.append({
            "where": unit["where"],
            "text": text[:400],
            "tells": tells,
            "jargon_hits": jargon_hits,
            "oracle_examples": oracle_hits[:3],
            "antithesis": {"count": ant_count, "density": round(ant_density, 2),
                           "examples": ant_ex},
        })
    result = ScanResult(candidates)
    result.suppressed_ruled = suppressed
    return result


def _candidate_decision(cand: dict, subject_prefix: str) -> dict:
    """One slop candidate → its growth-decision payload (kind + subject + candidates +
    the detector context). Shared by the framed and lite packet builders."""
    context = f"tells={','.join(cand['tells'])}"
    if cand["jargon_hits"]:
        context += f"; jargon={cand['jargon_hits']}"
    if cand["oracle_examples"]:
        context += f"; oracle={cand['oracle_examples']}"
    if cand["antithesis"]["count"]:
        context += f"; antithesis={cand['antithesis']}"
    return {
        "kind": "deslop-keep-kill-rewrite",
        "subject": f"{subject_prefix}:{cand['where']} :: {cand['text'][:120]}",
        "candidates": ["KEEP", "KILL", "REWRITE"],
        "context": context,
    }


def candidate_to_packet(repo_root: Path, cand: dict, subject_prefix: str) -> dict:
    """One slop candidate → one FRAMED growth-decision packet ``{frame, decision, bank}``
    (the single-decision path — the frame is rebuilt for this one packet)."""
    return growth_adjudicator.adjudicate_growth(
        repo_root, _candidate_decision(cand, subject_prefix))


def candidate_to_lite_packet(cand: dict, subject_prefix: str) -> dict:
    """One slop candidate → one FRAME-LESS packet ``{decision, bank}`` for the manifest
    path, where the wave's frame is hoisted to the manifest top-level ONCE rather than
    duplicated into every packet (the flatten reflex; see ``growth_adjudicator``)."""
    return growth_adjudicator.adjudicate_growth_lite(
        _candidate_decision(cand, subject_prefix))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Structural deslop gate (advisory, v1).")
    src = ap.add_mutually_exclusive_group(required=False)
    src.add_argument("--ledger", help="corpus_friction/<name>.jsonl conceptric ledger")
    src.add_argument("--tex", help="a projection .tex / plan file")
    ap.add_argument("--apply-keeps", action="store_true",
                    help="write the proxy's KEEP rulings into the lexicon allowlist "
                         "(the writer half) and report the summary; no scan")
    ap.add_argument("--corpus", default=None,
                    help="registered corpus name → fold its deprecated-vocabulary in")
    ap.add_argument("--root", default=str(ROOT), help="repo root")
    ap.add_argument("--manifest", default=None,
                    help="manifest out path (default: <root>/corpus_friction/"
                         "deslop_manifest_<stem>.json)")
    ap.add_argument("--antithesis-min", type=int, default=2)
    ap.add_argument("--density-min", type=float, default=0.5)
    ap.add_argument("--today", default=None, help="YYYY-MM-DD, for allowlist-decay")
    ap.add_argument("--max-packets", type=int, default=40)
    ap.add_argument("--examples", type=int, default=5)
    args = ap.parse_args(argv)

    repo_root = Path(args.root).resolve()
    import datetime as _dt
    today = args.today or _dt.date.today().isoformat()

    # ---- the writer mode: grow the allowlist from the proxy's KEEP rulings, then stop
    if args.apply_keeps:
        summary = apply_keep_rulings(repo_root, today=today)
        print(f"apply_keep_rulings — added={summary['added']} "
              f"skipped={summary['skipped']} decays={summary['decays']}")
        if summary["terms"]:
            print(f"  terms: {summary['terms']}")
        return 0

    if not (args.ledger or args.tex):
        ap.error("one of --ledger / --tex is required (or --apply-keeps)")

    if args.ledger:
        target = (repo_root / args.ledger) if not Path(args.ledger).is_absolute() \
            else Path(args.ledger)
        units = units_from_ledger(target)
        subject_prefix = f"conceptric[{target.stem}]"
    else:
        target = (repo_root / args.tex) if not Path(args.tex).is_absolute() \
            else Path(args.tex)
        units = units_from_tex(target)
        subject_prefix = f"projection[{target.stem}]"

    candidates = scan(repo_root, units, args.corpus, today,
                      args.antithesis_min, args.density_min)

    # lite packets (no per-packet frame) + the ONE manifest-level frame they share,
    # assembled once here — not rebuilt per candidate (the flatten reflex).
    packets = [candidate_to_lite_packet(c, subject_prefix)
               for c in candidates[:args.max_packets]]
    manifest_question = (
        f"DESLOP wave over {subject_prefix} — rule each packet KEEP/KILL/REWRITE "
        f"in his register.")
    frame = growth_adjudicator.assemble_manifest_frame(repo_root, manifest_question)

    if args.manifest:
        manifest_path = Path(args.manifest)
        if not manifest_path.is_absolute():
            manifest_path = repo_root / manifest_path
    else:
        manifest_path = repo_root / "corpus_friction" / f"deslop_manifest_{target.stem}.json"
    manifest = growth_adjudicator.emit_dispatch_manifest(
        packets, manifest_path, frame=frame)

    # ---- report
    by_tell: dict[str, int] = {}
    for c in candidates:
        for t in c["tells"]:
            by_tell[t] = by_tell.get(t, 0) + 1
    suppressed_ruled = getattr(candidates, "suppressed_ruled", 0)
    print(f"deslop_gate — target={target.name} units={len(units)} "
          f"candidates={len(candidates)} suppressed_ruled={suppressed_ruled}")
    print(f"  by tell: {by_tell}")
    print(f"  manifest: {manifest_path.relative_to(repo_root) if manifest_path.is_relative_to(repo_root) else manifest_path} "
          f"(packets={manifest['count']})")
    for c in candidates[:args.examples]:
        print(f"  - [{','.join(c['tells'])}] {c['where']}: {c['text'][:110]!r}")
        if c["jargon_hits"]:
            print(f"      jargon: {c['jargon_hits']}")
        if c["oracle_examples"]:
            print(f"      oracle: {c['oracle_examples'][0]!r}")
        if c["antithesis"]["examples"]:
            print(f"      antithesis: {c['antithesis']['examples']}")

    verdict = "WARN" if candidates else "PASS"
    print(f"VERDICT={verdict} candidates={len(candidates)} units={len(units)} "
          f"suppressed_ruled={suppressed_ruled} packets={manifest['count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
