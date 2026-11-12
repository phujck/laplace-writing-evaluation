"""Literature search backend for the conceptric editor.

Wraps ``scholarly`` (the unofficial Google Scholar client) into a small, predictable surface:
:func:`query` takes a free-text query and returns top-``k`` candidate publications, each shaped
for the editor's bulk-stage picker (bibkey, title, authors, year, venue, abstract snippet,
scholar URL). Results are cached in-memory keyed by the query string so a click that lands on a
list and a click that wires that list in don't double-hit Scholar.

Rate-limiting is the chronic risk: Scholar will start serving CAPTCHAs after a handful of fast
queries. The wrapper catches the failure modes (``MaxTriesExceededException``, generic network
errors) and returns ``{"error": ..., "candidates": []}`` so the picker can show "couldn't fetch
— try again later" rather than crash. Standing permission (his, 2026-06-08) covers acting as
the author for Scholar paper-fetching.
"""

from __future__ import annotations

import re
import threading
from typing import Any

# in-memory cache: (query, k) -> list of candidates. Resets on process restart.
_CACHE: dict[tuple[str, int], list[dict]] = {}
_CACHE_LOCK = threading.Lock()


def _bibkey(first_author: str, year: str, title: str, taken: set[str]) -> str:
    """``LastnameYearFirstword`` — the BibTeX-ish key the editor mints for ``ref:`` nodes."""
    last = re.split(r"\s+", (first_author or "").strip())[-1] or "Anon"
    last = re.sub(r"[^A-Za-z]", "", last) or "Anon"
    yr = re.search(r"\b(19|20)\d{2}\b", str(year or ""))
    yr = yr.group(0) if yr else "ND"
    firstword = re.search(r"[A-Za-z]{4,}", title or "")
    firstword = firstword.group(0).lower() if firstword else ""
    base = f"{last}{yr}{firstword[:8].capitalize()}"
    if base not in taken:
        return base
    # collision: append letters
    for c in "abcdefghijklmnopqrstuvwxyz":
        cand = base + c
        if cand not in taken:
            return cand
    return base + "X"


def _shape(pub: Any, taken: set[str]) -> dict:
    """One scholarly ``Publication`` (or its dict) -> the editor's candidate shape."""
    bib = pub.get("bib", {}) if isinstance(pub, dict) else getattr(pub, "bib", {}) or {}
    authors = bib.get("author") or []
    if isinstance(authors, str):
        authors = [a.strip() for a in re.split(r"\s+and\s+|,", authors) if a.strip()]
    title = (bib.get("title") or "").strip()
    year = bib.get("pub_year") or bib.get("year") or ""
    venue = bib.get("venue") or bib.get("journal") or bib.get("booktitle") or ""
    abstract = (bib.get("abstract") or "").strip()
    pub_url = pub.get("pub_url") if isinstance(pub, dict) else getattr(pub, "pub_url", "")
    eprint = pub.get("eprint_url") if isinstance(pub, dict) else getattr(pub, "eprint_url", "")
    key = _bibkey(authors[0] if authors else "", year, title, taken)
    taken.add(key)
    return {
        "bibkey": key,
        "title": title[:300],
        "authors": authors[:10],
        "year": str(year),
        "venue": venue[:160],
        "abstract": abstract[:600],
        "url": pub_url or eprint or "",
        "n_cites": (pub.get("num_citations") if isinstance(pub, dict)
                    else getattr(pub, "num_citations", 0)) or 0,
    }


_LATEX_RESIDUE = {
    # common LaTeX commands whose bare names survive a naive strip and become Scholar noise
    "frac", "binom", "sum", "prod", "int", "lim", "log", "exp", "sin", "cos", "tan",
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa",
    "lambda", "mu", "nu", "xi", "omicron", "pi", "rho", "sigma", "tau", "upsilon",
    "phi", "chi", "psi", "omega", "Delta", "Gamma", "Lambda", "Omega", "Phi", "Pi",
    "Psi", "Sigma", "Theta", "Xi", "langle", "rangle", "cdot", "cdots", "ldots", "vdots",
    "leq", "geq", "neq", "approx", "equiv", "sim", "to", "rightarrow", "leftarrow",
    "infty", "partial", "nabla", "hat", "bar", "tilde", "dot", "ddot", "mathbb",
    "mathcal", "mathrm", "mathbf", "mathit", "text", "textbf", "textit",
    "begin", "end", "left", "right", "big", "Big", "ket", "bra", "operatorname",
    "label", "eqref", "cref", "ref", "cite", "citep", "citet",
}


def _strip_latex(s: str) -> str:
    """LaTeX -> something Scholar can parse: drop math, commands, residue command-names."""
    s = re.sub(r"\$[^$]*\$", " ", s or "")
    s = re.sub(r"\\[a-zA-Z]+\*?\s*", " ", s)
    s = re.sub(r"[{}^_$&|\\]", " ", s)
    # drop bare residue tokens (command names that survived the backslash strip via keyword pass)
    tokens = [t for t in re.split(r"\s+", s) if t and t not in _LATEX_RESIDUE]
    # also drop bare node-id-like tokens (eq:foo, def:bar, ref:Key — never useful in a Scholar query)
    tokens = [t for t in tokens if not re.match(r"^[a-z]{2,8}:[A-Za-z0-9_\-]+$", t)]
    return " ".join(tokens).strip()


def build_query(parts: list[str], cap: int = 220) -> str:
    """Build a Scholar-friendly query from a list of strings (essence/ctx/keywords). LaTeX +
    residue tokens stripped; result capped (Scholar's parser truncates aggressively)."""
    cleaned = [_strip_latex(p) for p in parts if p]
    joined = " ".join(c for c in cleaned if c)
    return joined[:cap].strip()


def query(text: str, k: int = 10) -> dict:
    """Run a Scholar query. Returns ``{"candidates": [...], "query": "..."}`` on success or
    ``{"error": "...", "candidates": []}`` on failure. Cached in-memory by (text, k)."""
    text = (text or "").strip()
    if not text:
        return {"candidates": [], "query": "", "error": "empty query"}
    cache_key = (text, k)
    with _CACHE_LOCK:
        if cache_key in _CACHE:
            return {"candidates": _CACHE[cache_key], "query": text, "cached": True}
    try:
        from scholarly import scholarly
    except ImportError as e:
        return {"candidates": [], "query": text, "error": f"scholarly not installed: {e}"}
    try:
        search = scholarly.search_pubs(text)
        taken: set[str] = set()
        out: list[dict] = []
        for _ in range(k):
            try:
                pub = next(search)
            except StopIteration:
                break
            out.append(_shape(pub, taken))
        with _CACHE_LOCK:
            _CACHE[cache_key] = out
        return {"candidates": out, "query": text}
    except Exception as e:  # noqa: BLE001 - Scholar's failure modes are many; surface honestly
        return {"candidates": [], "query": text,
                "error": f"scholar query failed ({type(e).__name__}): {e}"}


def query_for_node(node: dict, k: int = 10) -> dict:
    """Convenience: build a Scholar query from a node's content + run it. Drops the keywords
    list — for math-heavy nodes it's mostly LaTeX-command residue (frac, binom, langle, ...)
    that drowns out the real signal in essence + ctx."""
    parts = [node.get("essence", ""), node.get("ctx", "")]
    return query(build_query(parts), k=k)
