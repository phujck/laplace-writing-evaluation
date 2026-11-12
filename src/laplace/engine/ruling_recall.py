"""The taste flywheel's RETURN LEG — his banked rulings read BACK into the frames
that steer work.

The forward leg was always real: a fork or a growth call is framed
(:func:`author_proxy.assemble_decision_frame`), a dispatched judge rules, and the
ruling is banked append-only to ``proxy_verdicts.jsonl``
(:func:`author_proxy.bank_ruling`, via ``fork_adjudicator.bank_fork_ruling`` /
``growth_adjudicator.bank_growth_ruling``). The RETURN leg was dead: nothing read a
banked ruling back into the frame of the NEXT piece of work.

Two ends, precisely (the state this module changes):

- the builder prompt (``pipeline/dispatch.py`` ``_compile_dispatch_core``) carried
  DERIVED taste only — the ``AUTHOR-ARCHITECTURE`` profile fence, measured off what he
  DID — and not one banked ruling of what he RULED;
- ``gap_ledger.rank_gaps`` accepted a ``prior_rulings`` boost and its docstring named
  "then his PRIOR RULINGS" in the ranking, but no production caller ever passed one —
  the parameter was decorative, and the docstring was an overclaim.

What rides back. Typed rows, never a prose paraphrase: each recalled ruling travels as
``{id, date, kind, confidence, question, ruling, ref, score, why}`` where ``ref`` is
``proxy_verdicts.jsonl#<id>`` — the handle the reader descends. Refs-only holds: the
quote is the ruling's own words, bounded; the frame carries the relevant SLICE with
provenance, never the ledger.

THE HEURISTIC — **live-and-distinctive-lexical, recency-tiebroken**. The cheapest thing
that is truthful, and named so nobody mistakes it for a taste model:

1. **live** — a ruling superseded by a later ruling's ``supersedes``, contested by a
   ``kind:"contest"`` record, or carrying a non-null ``contested`` field is DEAD and
   never steers work. Correction is retrospective through the ledger (the proxy's own
   law), so the read side must honour it or a retracted call keeps steering.
2. **distinctive-lexical** — score a live ruling by how many DISTINCTIVE content tokens
   it shares with the context. A token is distinctive when it appears in at most
   :data:`_DF_CEILING` of the live ledger; the ubiquitous engine vocabulary (section,
   ruling, engine …) therefore earns nothing, so a ruling rides on subject overlap, not
   on house register. Floor: :data:`_SCORE_FLOOR` shared distinctive tokens.
3. **recency-tiebroken** — equal scores order newest first, then by id. Fully
   deterministic; no model call, no embedding, no numpy.

No silent empty. Every call returns ``provenance`` — how many rows were scanned, how
many were live, how many were dropped dead, how many matched, and the heuristic's name.
A caller that finds nothing SAYS it found nothing against a ledger of N; a frame that
carries no ruling is a truthful absence on the record, never a missing channel.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

#: the ledger this leg reads back (owned by :mod:`laplace.engine.author_proxy`).
LEDGER_NAME = "proxy_verdicts.jsonl"

#: the named retrieval heuristic — carried in every provenance block so a reader of a
#: frame knows exactly how the rows in front of them were chosen.
HEURISTIC = "live-and-distinctive-lexical, recency-tiebroken"

#: a token counts as DISTINCTIVE when it appears in at most this fraction of the live
#: ledger. Above it the token is house vocabulary and scores nothing — the bar that
#: keeps "the section ruling on the engine" from matching every ruling ever banked.
_DF_CEILING = 0.40

#: the ABSOLUTE floor under that fraction. A token appearing in three or fewer rulings
#: is rare on any corpus, so it stays distinctive however small the ledger is. Without
#: this the fraction inverts on a young ledger — at four banked rulings the ceiling is
#: one, and a word shared by two of them is discarded as "house vocabulary" when it is
#: in fact the subject. The leg must work from the first ruling banked, not only once
#: the ledger is large.
_DF_FLOOR = 3

#: the minimum number of shared distinctive tokens a ruling must carry to ride. One
#: shared token is a coincidence; two is a subject.
_SCORE_FLOOR = 2

#: the bound on a recalled ruling's quote — refs-only: the ref is the descent, the
#: quote is the only free text.
_QUOTE_CAP = 400

#: the bound on the CONTEXT a caller may match against. Lexical overlap degrades with
#: context size — a whole manuscript record shares distinctive tokens with nearly every
#: ruling ever banked, so an unbounded context ranks by breadth instead of subject. The
#: bound is structural rather than per-caller so no call site can flood the channel by
#: passing more; the provenance reports when it bit.
_CONTEXT_CAP = 1200

#: content tokens only: four characters or more, letter-initial. Short tokens carry no
#: subject and would drag the whole ledger in.
_TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{3,}")

#: the small closed stoplist — connective and engine-generic words that survive the
#: length filter but name no subject. The document-frequency ceiling does most of this
#: work; the list is the belt for a context short enough that df cannot speak.
_STOP: frozenset[str] = frozenset({
    "that", "this", "with", "from", "have", "here", "there", "then", "than", "when",
    "what", "which", "whose", "into", "onto", "over", "under", "does", "must", "never",
    "always", "every", "each", "some", "only", "also", "just", "more", "most", "less",
    "such", "same", "other", "another", "still", "would", "could", "should", "shall",
    "been", "being", "were", "will", "they", "them", "their", "your", "yours", "ours",
    "about", "against", "between", "through", "during", "before", "after", "above",
    "below", "because", "while", "where", "whether", "these", "those", "make", "makes",
    "made", "take", "takes", "give", "gives", "keep", "keeps", "come", "goes", "gone",
    "want", "need", "like", "used", "using", "note", "true", "false", "none", "null",
})


# ------------------------------------------------------------------ the live set
def _rows(repo_root: Path | str) -> list[dict]:
    """Every banked row through the proxy's own tolerant read (a poisoned line is
    skipped, never fatal)."""
    from laplace.engine import author_proxy
    rows = author_proxy.load_verdicts(repo_root)
    return [r for r in rows if isinstance(r, dict)]


def dead_ids(rows: Iterable[dict]) -> set[str]:
    """The ids a later record RETIRED — superseded by another ruling's ``supersedes``,
    or named by a ``kind:"contest"`` record. Correction is retrospective through the
    ledger, so this is the read side of that law: a retired ruling never steers work
    again. A ``kind:"confirm"`` record is the opposite sign and retires nothing."""
    dead: set[str] = set()
    for r in rows:
        sup = r.get("supersedes") or []
        # both shapes live in the store: a list of ids AND a bare string (possibly "").
        # Iterating a string yields CHARACTERS, and the substring rule below amplified
        # each one into a ledger-wide kill - recall() returned 0 of 241 rulings with
        # green tests (the faithfulness census's worst finding, 2026-08-21). A string
        # is ONE id, never a sequence.
        if isinstance(sup, str):
            sup = [sup] if sup.strip() else []
        for s in sup:
            s = str(s).strip()
            if s:
                dead.add(s)
        if str(r.get("kind") or "") == "contest":
            c = str(r.get("contests") or "").strip()
            if c:
                dead.add(c)
    return dead


def live_rulings(repo_root: Path | str, kinds: Iterable[str] | None = None) -> list[dict]:
    """The LIVE ruling set: every row carrying ruling text, minus the retired ones.

    A row without a ``ruling`` is not a ruling (a ``contest`` / ``confirm`` record is a
    correction, not a call). A row whose own ``contested`` field is non-null is retired
    by its own record. ``kinds`` optionally narrows to a lane — e.g.
    ``("fork-adjudication", "growth")`` for the adjudicator lanes specifically."""
    rows = _rows(repo_root)
    dead = dead_ids(rows)
    want = set(kinds) if kinds else None
    out: list[dict] = []
    for r in rows:
        rid = str(r.get("id") or "").strip()
        if not rid or not str(r.get("ruling") or "").strip():
            continue
        if r.get("contested"):
            continue
        # a retired id may be named in full or by the slug tail an older row used;
        # the containment test requires a real token (>=8 chars) so a short stray
        # entry can never retire the whole ledger by substring accident
        if rid in dead or any(len(d) >= 8 and (d in rid or rid in d) for d in dead):
            continue
        if want is not None and str(r.get("kind") or "") not in want:
            continue
        out.append(r)
    return out


# ------------------------------------------------------------------ the scoring
def _tokens(text: str) -> set[str]:
    """The distinct content tokens of a text — lowercased, four-plus characters,
    letter-initial, stoplist removed."""
    return {t for t in _TOKEN_RE.findall(str(text).lower()) if t not in _STOP}


def _ruling_text(row: dict) -> str:
    return f"{row.get('question', '')} {row.get('ruling', '')}"


def _distinctive(docs: list[set[str]]) -> set[str]:
    """The tokens that name a SUBJECT rather than the house register: those appearing
    in at most :data:`_DF_CEILING` of the live ledger. Computed from the ledger itself,
    so the bar moves with the corpus instead of being a hardcoded vocabulary."""
    if not docs:
        return set()
    ceiling = max(_DF_FLOOR, int(len(docs) * _DF_CEILING))
    df: dict[str, int] = {}
    for d in docs:
        for t in d:
            df[t] = df.get(t, 0) + 1
    return {t for t, n in df.items() if n <= ceiling}


def _similarity(shared: int, n_ctx: int, n_doc: int) -> float:
    """Set cosine — ``shared / sqrt(|context| * |ruling|)``.

    Raw overlap count is LENGTH-BIASED: a long banked verdict shares more tokens with
    anything than a two-line taste call does, so ranking by count promotes verbosity over
    relevance. The cosine normalises it away with no dependency and no tuning. The
    ``_SCORE_FLOOR`` still applies to the raw count — a strong cosine off one shared token
    is a coincidence, not a subject."""
    if not n_ctx or not n_doc:
        return 0.0
    return shared / ((n_ctx * n_doc) ** 0.5)


def _row(row: dict, score: float, shared: int, why: list[str]) -> dict[str, Any]:
    """One recalled ruling as a TYPED ROW — id, date, the ruling, its source ref. The
    shape a frame carries; never a prose paraphrase of what he decided."""
    rid = str(row.get("id") or "")
    return {
        "id": rid,
        "date": str(row.get("date") or ""),
        "kind": str(row.get("kind") or ""),
        "confidence": str(row.get("confidence") or ""),
        "question": " ".join(str(row.get("question") or "").split())[:_QUOTE_CAP],
        "ruling": " ".join(str(row.get("ruling") or "").split())[:_QUOTE_CAP],
        "ref": f"{LEDGER_NAME}#{rid}",
        "score": round(score, 4),
        "shared": shared,
        "why": why,
    }


# ------------------------------------------------------------------ the recall
def recall(repo_root: Path | str, context: str, cap: int = 6,
           kinds: Iterable[str] | None = None) -> dict[str, Any]:
    """Recall the banked rulings relevant to ``context`` as typed rows + provenance.

    ``context`` is whatever names the work in hand — a goal line, a question, a target
    id, the OBJECT channel of a builder packet. Returns
    ``{"rows": [...], "provenance": {...}}``; ``rows`` is bounded by ``cap`` and may be
    empty, in which case the provenance still states what was scanned (no silent empty).

    Deterministic and dependency-light: no model, no embedding, no numpy — the ledger
    read plus set arithmetic. See the module docstring for the heuristic."""
    rows = _rows(repo_root)
    live = live_rulings(repo_root, kinds=kinds)
    # count the rows ACTUALLY dropped as retired — not the size of the retired-id set,
    # which can name ids no live row carries (an older slug, a record since rewritten).
    # The absence line quotes these numbers, so they must be the real ones.
    live_ids = {str(r.get("id") or "") for r in live}
    retired_n = sum(1 for r in rows
                    if str(r.get("ruling") or "").strip()
                    and str(r.get("id") or "") not in live_ids
                    and (kinds is None or str(r.get("kind") or "") in set(kinds)))
    docs = [_tokens(_ruling_text(r)) for r in live]
    distinctive = _distinctive(docs)
    full = " ".join(str(context or "").split())
    ctx = _tokens(full[:_CONTEXT_CAP]) & distinctive

    scored: list[tuple[float, str, str, dict, list[str]]] = []
    for r, toks in zip(live, docs):
        shared = sorted(ctx & toks)
        if len(shared) < _SCORE_FLOOR:
            continue
        # sort key: similarity desc, date desc, id asc — reverse-lex on date sorts
        # newest first without reversing the whole order (the taste_retrieval idiom).
        scored.append((_similarity(len(shared), len(ctx), len(toks)),
                       str(r.get("date") or ""), str(r.get("id") or ""), r, shared))
    scored.sort(key=lambda s: (-round(s[0], 6), _desc(s[1]), s[2]))

    out = [_row(r, sim, len(why), why[:6])
           for sim, _d, _i, r, why in scored[:max(0, cap)]]
    provenance = {
        "channel": "ruling-return-leg",
        "ledger": LEDGER_NAME,
        "heuristic": HEURISTIC,
        "scanned": len(rows),
        "live": len(live),
        # the three ways a scanned row is not a live candidate, counted apart so the
        # absence line can never blur "he retracted it" with "it was never a ruling".
        "retired": retired_n,
        "not_a_ruling": sum(1 for r in rows if not str(r.get("ruling") or "").strip()),
        "kinds_filter": sorted(kinds) if kinds else None,
        "matched": len(scored),
        "returned": len(out),
        "cap": cap,
        "score_floor": _SCORE_FLOOR,
        "df_ceiling": _DF_CEILING,
        "context_tokens": len(ctx),
        "context_chars": min(len(full), _CONTEXT_CAP),
        "context_truncated": len(full) > _CONTEXT_CAP,
    }
    return {"rows": out, "provenance": provenance}


def _desc(s: str) -> tuple:
    """A reverse-lexicographic sort key for a date string — newest first inside an
    otherwise ascending sort."""
    return tuple(-ord(ch) for ch in s)


# ------------------------------------------------------------------ the rendered fence
def render_rows(result: dict[str, Any], intro: str) -> str:
    """Render a :func:`recall` result as the body of a prompt fence — the typed rows as
    JSON, or the truthful ABSENCE when nothing matched. A frame never silently omits the
    channel: the absence names the ledger it was read against, so a builder can tell
    "he has ruled nothing here" from "nobody looked"."""
    import json
    p = result["provenance"]
    if not result["rows"]:
        return (intro + "\nNONE — no banked ruling of his matches this context. "
                f"({p['live']} live rulings scanned in {p['ledger']}, "
                f"{p['retired']} retired; heuristic: {p['heuristic']}.) "
                "This is a truthful absence, not an unread channel: proceed on the "
                "specification and the profiles, and return a typed issue if a call "
                "is needed that only he can make.")
    return (intro + "\n" + json.dumps(
        {"rulings": result["rows"], "provenance": p}, ensure_ascii=False, indent=1))


# ------------------------------------------------------------------ the gap-ledger boost
#: the ceiling on a prior-ruling boost in :func:`gap_ledger.rank_gaps`. Severity lives
#: in [0,1] and spine-criticality is a separate, earlier slot in the sort key, so a
#: boost re-orders gaps WITHIN a spine tier and can never invert the spine law.
MAX_BOOST = 0.5


def rulings_boost(repo_root: Path | str, keys: Iterable[str] | dict[str, str],
                  kinds: Iterable[str] | None = None) -> dict[str, float]:
    """The ``prior_rulings`` map :func:`gap_ledger.rank_gaps` has always accepted and
    never been given: ``{gap kind or id -> boost in [0, MAX_BOOST]}``.

    ``keys`` is either an iterable of keys (each key is its own match context) or a
    MAPPING ``{key: context text}``. Prefer the mapping: a gap KIND like
    ``source-argument-lost`` is engine vocabulary and matches his rulings on almost
    nothing, whereas the gap's own ISSUE text names the subject he actually ruled about.
    Keying by gap id with the issue as context is what makes this boost carry signal
    rather than a tidy empty.

    Each context is scored against the live ledger by the module heuristic; the boost is
    the best match normalised against the strongest in this call, so the map is
    scale-free and a round with no relevant ruling produces an EMPTY map rather than a
    uniform nudge. Hyphens and underscores are read as word separators."""
    live = live_rulings(repo_root, kinds=kinds)
    docs = [_tokens(_ruling_text(r)) for r in live]
    distinctive = _distinctive(docs)
    pairs = (keys.items() if isinstance(keys, dict)
             else [(k, k) for k in keys])

    raw: dict[str, float] = {}
    for key, context in pairs:
        k = str(key or "").strip()
        if not k:
            continue
        text = " ".join(str(context or k).split())[:_CONTEXT_CAP]
        ctx = _tokens(text.replace("-", " ").replace("_", " ")) & distinctive
        if not ctx:
            continue
        best = 0.0
        for toks in docs:
            shared = len(ctx & toks)
            if shared >= _SCORE_FLOOR:
                best = max(best, _similarity(shared, len(ctx), len(toks)))
        if best > 0:
            raw[k] = best
    if not raw:
        return {}
    top = max(raw.values())
    return {k: round(MAX_BOOST * n / top, 4) for k, n in raw.items()}
