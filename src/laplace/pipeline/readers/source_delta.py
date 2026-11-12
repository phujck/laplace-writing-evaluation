"""The SOURCE-DELTA reader — a roster organ that reads the SOURCE document against
the projection and types what the projection LOST (his 00:50 desk ruling, banked
ARMING_2026-07-16 / PV-20260717T005139Z: *the projection loses to his own V1
draft* — the decisive datum that the re-projection dropped the connective tissue,
the motivation, the argumentative moves that were never "concepts" and so never
became nodes).

This is a MECHANICAL reader (the ``apparatus`` cadence: runs every round, calls no
model). It reads the source prose (``paper_falqon/PAPER_FALQON_V1.md`` or any true
source) and the projection's flattened manuscript text, extracts the source's
ARGUMENTATIVE UNITS — sentences that carry a connective, motivational, or
argument-move marker (the load-bearing prose that is *reasoning*, not *fact*) — and
tests each for survival in the projection by content-word overlap. A source unit
whose reasoning does not survive as a coherent sentence anywhere in the projection
is emitted as a reader finding carrying the VERBATIM source span as its primary
record (the arming's demand: *findings with verbatim primary records*).

Why content-word Jaccard, not a model: the re-projection re-uses the source's
vocabulary almost everywhere (the numbers, the parameter names, the physics nouns
all survive), so a global word-presence test finds nothing lost. What is lost is
the SENTENCE AS A REASONING UNIT — the specific linking of a claim to its
motivation. That survives only if some projection sentence carries the same
distinctive content-word cluster. The per-sentence max-Jaccard against the source
unit is therefore the survival signal, and its floor (``jaccard_floor``, a dial) is
the one calibration point.

The three kinds (folded into ``schema.KIND_TO_WORK`` via
``register_component_kinds``; each feeds GROWTH as a first-class gap — the missing
substrate is argumentative, not conceptual):

* ``source-motivation-lost``  — a source sentence that says WHY (because / the
    reason / to see why / intuition) whose reasoning the projection dropped;
    route ``prose`` (the motivation is re-established in prose).
* ``source-argument-lost``    — a source sentence making an argument MOVE (implies /
    it follows / this means / so that / consequently) the projection dropped;
    route ``narrative`` (an argumentative-arc fault, re-planned).
* ``source-connective-lost``  — a source transition (however / therefore / in
    contrast / which means / leads to) the projection dropped, flattening the
    argument's joints; route ``prose``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Union

# --- the kinds this organ owns -> owning stage (the schema-wire manifest) ----
FINDING_KIND_STAGE: dict[str, str] = {
    "source-motivation-lost": "prose",
    "source-argument-lost": "narrative",
    "source-connective-lost": "prose",
}

#: the reader id and the convergence dimension it feeds (reader_reconstruction: a
#: cold reader rebuilds the argument from the page — exactly what lost connective
#: tissue defeats). Verdict soft-blends via ``convergence.soft_score`` on its label.
READER_ID = "source_delta"
DIMENSION = "reader_reconstruction"
PANEL_LABEL = "source_delta"

#: default survival floor: a source reasoning unit whose best-matching projection
#: sentence shares fewer than this fraction of its content words has NOT survived
#: as a coherent reasoning unit. Calibrated so the falqon V1 read surfaces the
#: dropped argumentative moves without drowning in near-duplicates.
DEFAULT_JACCARD_FLOOR = 0.34

#: a unit must carry at least this many content words to be judged — a two-word
#: fragment cannot be reliably matched and is not worth a finding.
_MIN_CONTENT_WORDS = 5

# --- markers that make a sentence a REASONING unit (not a bare fact) ----------
# ordered by kind; the FIRST kind whose marker matches types the unit.
_MOTIVATION_RE = re.compile(
    r"\b(?:because|since(?!\s+the)|the reason|to see why|to understand why|"
    r"intuit\w*|the point (?:is|being)|this is why|which is why|motivat\w*|"
    r"the idea (?:is|being)|so that (?:the|it|we|this))\b",
    re.IGNORECASE)
_ARGUMENT_RE = re.compile(
    r"\b(?:implies|it follows|follows that|this means|means that|"
    r"consequently|as a result|therefore(?=,?\s)|hence|thus(?=,?\s)|"
    r"shows that|establishes that|forces|guarantees that|"
    r"leaving|so the|so no|eliminat\w*|collaps\w*)\b",
    re.IGNORECASE)
_CONNECTIVE_RE = re.compile(
    r"\b(?:however|in contrast|on the other hand|by contrast|whereas|"
    r"which means|leads to|gives rise to|in turn|rather than|"
    r"instead of|not because|only if|as long as|provided that)\b",
    re.IGNORECASE)

# tokens that are content words for the overlap test: alphabetic, length >= 4,
# minus a small stoplist of high-frequency connectives (so the OVERLAP measures
# substance, not shared connectives — else every sentence matches on "which").
_STOP = frozenset("""
that this these those which where when what with from have will been being were
those there here their they them then than also into onto upon such more most
each both some many other another about above below over under again once only
very much such same both then thus hence into onto because since while whereas
however therefore consequently rather instead given provided within without
paper section every this these those value point value figure table above below
""".split())

_WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")
# a projection sentence boundary in flattened LaTeX/markdown prose
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\\$])")


def _content_words(text: str) -> frozenset[str]:
    return frozenset(
        w for w in (m.group(0).lower() for m in _WORD_RE.finditer(text))
        if len(w) >= 4 and w not in _STOP)


def _strip_markup(text: str) -> str:
    """Reduce markdown/LaTeX to prose for sentence splitting + word extraction:
    drop math, macros, comments, headings, code fences and table pipes — the
    content words that survive are what the overlap test compares."""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"\$[^$]*\$", " ", text)                 # inline math
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?(?:\{[^{}]*\})?", " ", text)  # macros
    text = re.sub(r"[{}\\]", " ", text)
    text = re.sub(r"\[@?[^\]]*\]", " ", text)              # [@cite] / [ledger]
    text = "\n".join(
        ln for ln in text.splitlines()
        if not ln.lstrip().startswith("#") and not ln.lstrip().startswith("|"))
    return text


def _sentences(prose: str) -> list[str]:
    out: list[str] = []
    for para in re.split(r"\n\s*\n", prose):
        para = " ".join(para.split())
        if not para:
            continue
        out.extend(s.strip() for s in _SENT_SPLIT_RE.split(para) if s.strip())
    return out


def _kind_of(sentence: str) -> Optional[str]:
    """The reasoning kind of a sentence, or None if it carries no reasoning
    marker. Motivation is checked first (it is the scarcest and most load-bearing),
    then argument-move, then bare connective."""
    if _MOTIVATION_RE.search(sentence):
        return "source-motivation-lost"
    if _ARGUMENT_RE.search(sentence):
        return "source-argument-lost"
    if _CONNECTIVE_RE.search(sentence):
        return "source-connective-lost"
    return None


def _best_survival(unit_words: frozenset[str],
                   proj_word_sets: list[frozenset[str]]) -> float:
    """Max Jaccard of the unit's content words against any single projection
    sentence — the survival-as-a-coherent-unit signal. 1.0 for an empty unit
    (never lost); 0.0 when no projection sentence overlaps at all."""
    if not unit_words:
        return 1.0
    best = 0.0
    for pw in proj_word_sets:
        if not pw:
            continue
        inter = len(unit_words & pw)
        if inter == 0:
            continue
        j = inter / len(unit_words | pw)
        if j > best:
            best = j
    return best


def read_source_delta(source: Union[str, Path],
                      projection: Union[str, Path],
                      *, jaccard_floor: float = DEFAULT_JACCARD_FLOOR,
                      source_is_text: bool = False,
                      projection_is_text: bool = False) -> dict[str, Any]:
    """Read the SOURCE against the PROJECTION and type what the projection lost.

    ``source`` is his source document (a path to ``PAPER_FALQON_V1.md``, or the raw
    text with ``source_is_text=True``). ``projection`` is the main ``.tex`` (its
    fragments are gathered) or the raw flattened text with ``projection_is_text``.
    Returns ``{pass, findings, counts, present}`` — ``present`` is the census the
    diff was taken against (source reasoning-unit counts + projection sentence
    count), the primary record a reviewer audits the verdict by.

    Each finding carries the VERBATIM source sentence as ``primary`` (the arming's
    demand) plus ``survival`` (its best projection Jaccard) so the floor call is
    auditable per-finding."""
    src_text = str(source) if source_is_text else _read(source)
    if projection_is_text:
        proj_text = str(projection)
    else:
        proj_text = _gather_projection(projection)

    src_sents = _sentences(_strip_markup(src_text))
    proj_sents = _sentences(_strip_markup(proj_text))
    proj_word_sets = [_content_words(s) for s in proj_sents]

    findings: list[dict[str, Any]] = []
    n_units = 0
    for sent in src_sents:
        kind = _kind_of(sent)
        if kind is None:
            continue
        words = _content_words(sent)
        if len(words) < _MIN_CONTENT_WORDS:
            continue
        n_units += 1
        survival = _best_survival(words, proj_word_sets)
        if survival < jaccard_floor:
            findings.append({
                "where": "source-vs-projection",
                "kind": kind,
                "route": FINDING_KIND_STAGE[kind],
                "issue": _issue_for(kind, survival),
                "fix": _fix_for(kind),
                "primary": sent[:400],           # VERBATIM source span (primary record)
                "quote": sent[:240],
                "survival": round(survival, 3),
                "reader": READER_ID,
            })

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    return {
        "pass": not findings,
        "present": {
            "source_sentences": len(src_sents),
            "source_reasoning_units": n_units,
            "projection_sentences": len(proj_sents),
            "jaccard_floor": jaccard_floor,
        },
        "findings": findings,
        "counts": counts,
    }


def _issue_for(kind: str, survival: float) -> str:
    what = {
        "source-motivation-lost": "the source states WHY this holds (a motivation "
            "the reader needs); the projection dropped it",
        "source-argument-lost": "the source makes an argument MOVE (a claim linked "
            "to its consequence); the projection dropped the linkage",
        "source-connective-lost": "the source carries a transition that joins two "
            "steps of the argument; the projection flattened it",
    }[kind]
    return f"{what} (best projection overlap {survival:.2f} < floor)"


def _fix_for(kind: str) -> str:
    return {
        "source-motivation-lost": "re-establish the motivation in prose, "
            "conditioned on the source sentence (never re-invented)",
        "source-argument-lost": "restore the argumentative move at re-planning — "
            "this is a missing beat, not a missing concept",
        "source-connective-lost": "restore the transition so the argument's joints "
            "read; the connective tissue is substrate, not decoration",
    }[kind]


def _read(path: Union[str, Path]) -> str:
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _gather_projection(main_tex: Union[str, Path]) -> str:
    """Flatten a projection: the gatherer when the target is a real .tex tree,
    else read the file directly (a raw prose source with no \\input structure)."""
    p = Path(main_tex)
    try:
        from laplace.pipeline.graph import _gather_manuscript_text
        return _gather_manuscript_text(p)
    except Exception:
        return _read(p)


def finding_kinds_manifest() -> list[dict[str, str]]:
    """kind -> owning stage, the row shape ``register_component_kinds`` folds into
    ``schema.KIND_TO_WORK``."""
    return [{"kind": k, "stage": s} for k, s in FINDING_KIND_STAGE.items()]
