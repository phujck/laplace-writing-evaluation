"""The formal house-style layer — a MECHANICAL, corpus-derived presentation sweep.

Phase I1 of the final manuscript-convergence build. This is the conjugate of the
scaffold-wipe on the *presentation* surface: where meta_leak scrubs construction
scaffolding out of the rendered object, ``check_house_style`` checks that the
rendered object wears the author's own house conventions — cross-reference
abbreviation (``Eq. (x)``/``Fig.``/``Sec.``/``App.``), numeric bracketed
citations, cite-before-punctuation, grammar-driven equation punctuation — all
DERIVED by mechanical count over the 9 authored exemplars (see the profile at
``profiles/house_style/gerard-manuscript-v1.yaml`` for the evidence).

It runs at the CANDIDATE-LOCK tier, mechanically, before the judge panel (like
meta_leak). It composes with — and does not duplicate — ``tex_template``:
``check_template`` owns the documentclass/preamble; ``lint_typography`` owns
overfull/undefined boxes; this owns the cross-ref / citation / equation-punct /
dash / orthography layer neither covers.

TWO forks are RECORDED, never auto-resolved (his ratification):

* **F33 British/American orthography** — the corpus is MIXED, even within a single
  file, so British-only is not corpus-derived. Emitted as ``orthography-fork``,
  report-only (route ``None``), never a fix.
* **F34 punctuation surface** — the corpus USES semicolons and spaced en-dashes;
  his STATED going-forward preference (``schema.VOICE_FAILURE_PATTERNS
  ['surface-invariant']``) bans them. Emitted as ``dash-surface``, marked as a
  stated-preference fork.

The whole sweep is a PURE REPORTER: it returns findings and writes nothing, so
"reported, not auto-edited" holds by construction for every finding, forks
included.

Finding shape (the standard ``{where, issue, fix, kind}``, plus context)::

    {"where": "line 42",        # location in the scanned source
     "issue": "...",            # what deviates
     "fix":   "...",            # the house form (None for report-only forks)
     "kind":  "xref-style",     # one of FINDING_KINDS
     "rule":  "xref.equation",  # the profile rule id
     "status":"enforced",       # enforced | advisory | fork
     "route": "prose",          # Phase-F owning stage (documentation; wired there)
     "line":  42,
     "match": "equation~\\ref{...}"}
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import re
from pathlib import Path
from typing import Any, Iterable, Optional, Union

# ---------------------------------------------------------------------------
# The finding-kinds manifest (mirrors the profile's `finding_kinds`). The
# owning-stage routes are WIRED into schema.KIND_TO_WORK in Phase F — declared
# here for the reader and for the standalone sweep, NOT wired by this module.
# ---------------------------------------------------------------------------
FINDING_KINDS: tuple[str, ...] = (
    "xref-style",
    "citation-style",
    "equation-punct",
    "dash-surface",
    "orthography-fork",
)

#: Phase-F routing intent. ``None`` == report-only (no work item). These land in
#: schema.KIND_TO_WORK during Phase F; this module never edits that registry.
KIND_ROUTES: dict[str, Optional[str]] = {
    "xref-style": "prose",
    "citation-style": "prose",
    "equation-punct": "prose",     # or 'render' for pure spacing
    "dash-surface": "render",
    "orthography-fork": None,       # report-only fork (F33)
}

DEFAULT_PROFILE_PATH = (
    source_tree()
    / "profiles" / "house_style" / "gerard-manuscript-v1.yaml"
)

# ---------------------------------------------------------------------------
# Orthography minimal pairs (F33). Curated so both spellings of the SAME lemma
# are recognised — the point is to REPORT the split, never to correct it.
# ---------------------------------------------------------------------------
_ORTHO_PAIRS: tuple[tuple[str, str], ...] = (
    (r"colour", r"color"), (r"behaviour", r"behavior"), (r"favour", r"favor"),
    (r"neighbour", r"neighbor"), (r"centre", r"center"), (r"fibre", r"fiber"),
    (r"modelling", r"modeling"), (r"modelled", r"modeled"),
    (r"labelled", r"labeled"), (r"labelling", r"labeling"),
    (r"analyse", r"analyze"), (r"analysed", r"analyzed"), (r"analysing", r"analyzing"),
    (r"generalis(e|ed|ing|ation)", r"generaliz(e|ed|ing|ation)"),
    (r"realis(e|ed|ing|ation)", r"realiz(e|ed|ing|ation)"),
    (r"normalis(e|ed|ing|ation)", r"normaliz(e|ed|ing|ation)"),
    (r"optimis(e|ed|ing|ation)", r"optimiz(e|ed|ing|ation)"),
    (r"characteris(e|ed|ing|ation)", r"characteriz(e|ed|ing|ation)"),
    (r"initialis(e|ed|ing|ation)", r"initializ(e|ed|ing|ation)"),
    (r"parametris(e|ed|ing|ation)", r"parameteriz(e|ed|ing|ation)"),
    (r"randomis(e|ed|ing|ation)", r"randomiz(e|ed|ing|ation)"),
)

# Cross-reference abbreviations that must carry a non-breaking space (~).
_XREF_ABBREVS = ("Eq", "Eqs", "Fig", "Figs", "Sec", "App", "Ref", "Table", "Tab")


# ---------------------------------------------------------------------------
# Profile loading
# ---------------------------------------------------------------------------
def load_profile(profile: Union[dict, str, Path, None] = None) -> dict[str, Any]:
    """Resolve ``profile`` to a dict. ``None`` loads the default YAML; a str/Path
    loads that file; a dict is returned as-is."""
    if isinstance(profile, dict):
        return profile
    path = Path(profile) if profile is not None else DEFAULT_PROFILE_PATH
    import yaml  # local import: yaml is only needed when a file profile is used

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data or {}


def _rule_index(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """id -> rule dict, so a detector can read its status/route from the profile."""
    return {r["id"]: r for r in profile.get("rules", []) if "id" in r}


def _status(rules: dict[str, dict[str, Any]], rule_id: str, default: str) -> str:
    return rules.get(rule_id, {}).get("status", default)


# ---------------------------------------------------------------------------
# Non-prose masking — blank comments and math, length-preserving so that line
# numbers hold. Semicolons, dashes and English-shaped tokens inside $...$,
# display math, environments and % comments are NOT prose and must not fire.
# ---------------------------------------------------------------------------
_MASKS = [
    re.compile(r"(?<!\\)%[^\n]*"),                                   # line comments
    re.compile(r"\\begin\{(equation|align|gather|multline|displaymath|"
               r"eqnarray|flalign|alignat|tikzpicture|verbatim|lstlisting)\*?\}"
               r".*?\\end\{\1\*?\}", re.DOTALL),                     # math/verbatim envs
    re.compile(r"\$\$.*?\$\$", re.DOTALL),                            # display $$...$$
    re.compile(r"\\\[.*?\\\]", re.DOTALL),                            # display \[...\]
    re.compile(r"(?<!\\)\$[^$\n]+\$"),                               # inline $...$
    re.compile(r"\\\([^\n]*?\\\)"),                                  # inline \(...\)
]


def _blank(m: "re.Match[str]") -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


def _mask_nonprose(src: str) -> str:
    for pat in _MASKS:
        src = pat.sub(_blank, src)
    return src


def _strip_comments(src: str) -> str:
    """Blank only % comments (keep math) — cross-ref/citation commands live in
    prose, not math, so masking math would only hide legitimate structure."""
    return re.compile(r"(?<!\\)%[^\n]*").sub(_blank, src)


def _line_of(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


def _finding(where: str, issue: str, fix: Optional[str], kind: str,
             rule: str, status: str, line: int, match: str) -> dict[str, Any]:
    return {
        "where": where, "issue": issue, "fix": fix, "kind": kind,
        "rule": rule, "status": status, "route": KIND_ROUTES.get(kind),
        "line": line, "match": match,
    }


# ---------------------------------------------------------------------------
# The detectors. Each takes the (masked or comment-stripped) source and yields
# findings; the caller stamps status from the profile.
# ---------------------------------------------------------------------------
def _detect_xref(prose: str, rules: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def emit(m, issue, fix, rule, status):
        out.append(_finding(f"line {_line_of(prose, m.start())}", issue, fix,
                            "xref-style", rule, status,
                            _line_of(prose, m.start()), m.group(0).strip()))

    # CR6 — cleveref/autoref is banned (0 in corpus).
    st = _status(rules, "xref.no_cleveref", "enforced")
    for m in re.finditer(r"\\(?:cref|Cref|autoref)\b", prose):
        emit(m, "cleveref/autoref used; the corpus never uses it (0 occurrences)",
             r"hand-written Eq./Fig./Sec./App. + \ref/\eqref", "xref.no_cleveref", st)

    # CR1 — spelled-out 'equation \ref' / 'equation (' in the body.
    st = _status(rules, "xref.equation", "enforced")
    for m in re.finditer(r"\b(equations?)~?\\(?:ref|eqref)\{", prose):
        emit(m, "equation cross-ref spelled out in body",
             r"abbreviate: Eq.~\eqref{...} / Eqs.~(\ref{a}, \ref{b})", "xref.equation", st)
    for m in re.finditer(r"(?<![.\w])(equations?)\s+\((?=\s*\\ref|\s*\d)", prose):
        emit(m, "equation number written as spelled-out 'equation (…)'",
             r"abbreviate: Eq.~(\ref{...})", "xref.equation", st)

    # CR2 — spelled-out 'Section \ref'.
    st = _status(rules, "xref.section", "enforced")
    for m in re.finditer(r"\b(Sections?)~?\\ref\{", prose):
        emit(m, "section cross-ref spelled 'Section'; body uses 'Sec.'",
             r"Sec.~\ref{sec:...}", "xref.section", st)

    # CR3 — spelled-out 'Figure \ref' mid-sentence (advisory; 'Figure' allowed at sentence start).
    st = _status(rules, "xref.figure", "advisory")
    for m in re.finditer(r"(?<=[a-z,;:] )(Figures?)~?\\ref\{", prose):
        emit(m, "figure cross-ref spelled 'Figure' mid-sentence (corpus abbreviates ~13.6:1)",
             r"Fig.~\ref{fig:...} (spell 'Figure' only at a sentence start)", "xref.figure", st)

    # CR1/CR3 — a cross-ref word written with a HARD-CODED number ("Figure 3",
    # "Equation 5", "Section 2") instead of an abbreviation + semantic \ref. Both a
    # house-style deviation (abbreviate) and a provisional-number smell. Advisory.
    for m in re.finditer(
            r"(?<=[a-z,;:] )(Figures?|Equations?|Sections?|Appendix|Appendices|Tables?)"
            r"~?\s(\d+|[A-Z]|[IVX]+)\b", prose):
        emit(m, f"cross-ref '{m.group(1)} {m.group(2)}' hard-codes a number instead of "
             "abbreviation + semantic \\ref",
             r"use Fig.~\ref{} / Eq.~\eqref{} / Sec.~\ref{} / App.~\ref{}", "xref.figure", st)

    # CR4 — spelled-out 'Appendix \ref'.
    st = _status(rules, "xref.appendix", "enforced")
    for m in re.finditer(r"\b(Appendix|Appendices)~?\\ref\{", prose):
        emit(m, "appendix cross-ref spelled out; body uses 'App.'",
             r"App.~\ref{app:...}", "xref.appendix", st)

    # CR7 — non-breaking space before a ref/eqref or parenthesised number. ADVISORY:
    # the corpus is nbsp-MAJORITY after the abbreviations (Eq.~( 161, Eq.( 31, Eq. ( 26;
    # ~\eqref 165 vs 19) but plain-space and no-space forms are real minority practice,
    # so this flags-for-review rather than blocking. \cite is DELIBERATELY EXCLUDED:
    # the corpus uses a plain space before \cite 435:76 over ~, so CR7 does NOT apply
    # to citations (flagging ' \cite' would flag his own dominant habit).
    st = _status(rules, "xref.nbsp", "advisory")
    abbr = "|".join(_XREF_ABBREVS)
    for m in re.finditer(rf"\b({abbr})\.(?!~)( ?)(\(|\\(?:ref|eqref))", prose):
        sep = "no space (Eq.( form)" if m.group(2) == "" else "a breakable space"
        emit(m, f"'{m.group(1)}.' followed by {sep} before a reference/number",
             "use a non-breaking space '~' (corpus nbsp-majority: Eq.~(...) / Fig.~\\ref{...})",
             "xref.nbsp", st)

    return out


def _detect_citation(prose: str, full_src: str,
                     rules: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def emit(m, issue, fix, rule, status):
        out.append(_finding(f"line {_line_of(prose, m.start())}", issue, fix,
                            "citation-style", rule, status,
                            _line_of(prose, m.start()), m.group(0).strip()))

    # CI1 — \citet is banned (author-year never used; 0 in corpus).
    st = _status(rules, "cite.style", "enforced")
    for m in re.finditer(r"\\citet\b", prose):
        emit(m, "\\citet (author-year) used; the corpus is numeric bracketed \\cite (0 \\citet)",
             r"use numeric \cite{...}", "cite.style", st)

    # CI1 — \citep only permitted under a non-REVTeX venue class.
    is_revtex = "revtex" in full_src.lower()
    if is_revtex:
        for m in re.finditer(r"\\citep\b", prose):
            emit(m, "\\citep under a REVTeX documentclass (natbib author-year); corpus uses \\citep only in svjour/sn-jnl",
                 r"use numeric \cite{...} under REVTeX", "cite.style", "advisory")

    # CI3 — the cite should PRECEDE terminal punctuation, not follow it. The
    # abbreviation-dot lookbehinds keep "Ref.~\cite"/"Refs. \cite" (the correct
    # works-as-noun form, where the dot is an abbreviation not a sentence end) from
    # false-firing; the corpus has ZERO genuine sentence-period-then-cite cases.
    st = _status(rules, "cite.pre_punct", "enforced")
    for m in re.finditer(
            r"(?<!Ref)(?<!Refs)(?<!Eq)(?<!Eqs)(?<!Fig)(?<!Figs)(?<!Sec)(?<!App)"
            r"(?<!Tab)(?<!,)(?<!\d)\.\s+\\cite\{", prose):
        emit(m, "citation placed AFTER a sentence period",
             r"place \cite{...} before the terminal period", "cite.pre_punct", st)

    return out


def _detect_equation_punct(src: str,
                           rules: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """EQ1 — grammar-driven equation terminal punctuation, mechanised
    CONSERVATIVELY: a display equation whose last content char is not a
    sentence-punctuation mark, immediately followed by a lowercase continuation
    word ('where'/'with'/'and'/'which'/'so'), suggests a missing comma. Advisory
    only — sentence grammar is not a fixed character."""
    out: list[dict[str, Any]] = []
    st = _status(rules, "eq.terminal_punct", "advisory")
    env = re.compile(
        r"\\begin\{(equation|align|gather|multline|flalign|alignat)\*?\}"
        r"(?P<body>.*?)\\end\{\1\*?\}", re.DOTALL)
    cont = re.compile(r"^\s*(where|with|and|which|so that|for which|in which)\b")
    for m in env.finditer(src):
        body = m.group("body").rstrip()
        # strip a trailing label/notag so the real last token is examined
        body = re.sub(r"(\\label\{[^}]*\}|\\notag|\\nonumber|\\\\|\s)+$", "", body)
        if not body:
            continue
        last = body.rstrip()[-1:]
        tail = src[m.end():m.end() + 60]
        if last not in ".,:;" and cont.match(tail):
            line = _line_of(src, m.start())
            out.append(_finding(
                f"line {line}", "display equation runs into a continuation clause "
                "('where'/'with'/…) with no terminal comma", "add the grammar-driven "
                "comma before the clause (advisory — verify against the sentence)",
                "equation-punct", "eq.terminal_punct", st, line,
                f"\\end{{...}} -> {tail.strip()[:24]}"))
    return out


def _detect_dash_surface(prose: str,
                         rules: dict[str, dict[str, Any]],
                         forks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """F34 — his RATIFIED STATED preference bans semicolons, em-dashes and
    en-dashes (spaced hyphen instead). RECORDED as a stated-preference fork:
    emitted so the surface is visible, but marked stated-not-corpus-derived and
    never auto-edited. Math and comments are already masked out of ``prose``."""
    out: list[dict[str, Any]] = []
    status = forks.get("F34.punctuation_surface", {}).get("status", "fork")
    note = ("his stated preference (F34); NOT corpus-derived — the corpus USES "
            "these; a spaced hyphen ' - ' is the stated house form")

    def emit(line, issue, match):
        out.append(_finding(f"line {line}", issue, "replace with a spaced hyphen "
                            f"' - ' ({note})", "dash-surface", "F34.punctuation_surface",
                            status, line, match))

    for m in re.finditer(r";", prose):
        emit(_line_of(prose, m.start()), "semicolon (F34 stated-preference ban)", ";")
    for m in re.finditer(r"(?<!-)---(?!-)", prose):
        emit(_line_of(prose, m.start()), "em-dash '---' (F34 stated-preference ban)", "---")
    for m in re.finditer(r"(?<!-) -- (?!-)", prose):
        emit(_line_of(prose, m.start()), "spaced en-dash ' -- ' (F34 stated-preference ban)", " -- ")
    for m in re.finditer(r"[—–]", prose):
        emit(_line_of(prose, m.start()), "unicode em/en-dash (F34 stated-preference ban)", m.group(0))
    return out


def _detect_orthography(prose: str,
                        forks: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """F33 — British/American is a RECORDED FORK: the corpus is mixed, even within
    one file. REPORT-ONLY (route None), never a fix. Findings are emitted so the
    split is visible per manuscript; they never fail the sweep and never carry an
    auto-edit."""
    out: list[dict[str, Any]] = []
    status = forks.get("F33.orthography", {}).get("status", "fork")
    for br, am in _ORTHO_PAIRS:
        for label, pat in (("British", br), ("American", am)):
            for m in re.finditer(rf"(?<![\\A-Za-z])({pat})\b", prose, re.IGNORECASE):
                line = _line_of(prose, m.start())
                out.append(_finding(
                    f"line {line}", f"{label} spelling '{m.group(0)}' — orthography is "
                    "a recorded fork (F33); corpus is MIXED, even within one file", None,
                    "orthography-fork", "F33.orthography", status, line, m.group(0)))
    return out


# ---------------------------------------------------------------------------
# The public entry point.
# ---------------------------------------------------------------------------
def _detect_identity(src: str, rules: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """AF1 — his standing word (2026-07-18, banked in proxy_verdicts): the
    Loughborough affiliation never appears on a produced artefact. Ever. Swept over
    the RAW source (front matter lives outside the prose mask; a commented-out line
    still reintroduces it on the next careless uncomment)."""
    out: list[dict[str, Any]] = []
    st = _status(rules, "identity.no_loughborough_affiliation", "enforced")
    # Scope (his ruling 2026-08-06, the six-author foreign artefact): the ban is on
    # HIS affiliation line, not on the string. Coauthors who are genuinely at
    # Loughborough keep their real affiliation; the rule fires only when the
    # nearest preceding \author is McCaul (or when no author block precedes at
    # all — loose text still flags).
    author_spans = [(m.start(), m.group(1)) for m in
                    re.finditer(r"\\author\{([^}]*)\}", src)]
    # The rule is about the AFFILIATION, which lives in the front matter: scan
    # only up to \maketitle when one exists. Body mentions (acknowledged
    # institutions, cited groups) are facts about others, not his affiliation.
    cut = src.find(r"\maketitle")
    scan = src if cut == -1 else src[:cut]
    for m in re.finditer(r"(?i)loughborough", scan):
        owner = ""
        for start, name in author_spans:
            if start < m.start():
                owner = name
            else:
                break
        if owner and "mccaul" not in owner.lower():
            continue
        out.append(_finding(
            f"line {_line_of(src, m.start())}",
            "the Loughborough affiliation appears on HIS author block "
            "(his standing word: never as his affiliation)",
            r"delete the \affiliation line — no replacement is implied",
            "identity", "identity.no_loughborough_affiliation", st,
            _line_of(src, m.start()), m.group(0)))
    return out


def check_house_style(tex_source: str,
                      profile: Union[dict, str, Path, None] = None,
                      *, include_orthography: bool = True) -> dict[str, Any]:
    """Mechanically sweep rendered ``.tex`` for house-style deviations.

    Parameters
    ----------
    tex_source : str
        The rendered LaTeX source (a single fragment, or the whole manuscript
        concatenated in ``\\input`` order — see ``check_house_style_manuscript``).
    profile : dict | str | Path | None
        The house-style profile. ``None`` loads the default versioned YAML.
    include_orthography : bool
        Emit the F33 orthography-fork findings (report-only). Default True.

    Returns
    -------
    dict with keys ``pass`` (no ENFORCED findings), ``findings`` (list in the
    ``{where, issue, fix, kind, ...}`` shape), ``count``, ``by_kind``,
    ``by_status`` and ``profile``. Advisory and fork findings NEVER fail ``pass``
    (forks are reported, not enforced); only ``enforced`` deviations do.
    """
    prof = load_profile(profile)
    rules = _rule_index(prof)
    forks = {f["id"]: f for f in prof.get("forks", []) if "id" in f}

    comment_stripped = _strip_comments(tex_source)   # refs/cites live in prose
    prose = _mask_nonprose(tex_source)               # dashes/spelling: mask math too

    findings: list[dict[str, Any]] = []
    findings += _detect_xref(comment_stripped, rules)
    findings += _detect_citation(comment_stripped, tex_source, rules)
    findings += _detect_equation_punct(tex_source, rules)
    findings += _detect_dash_surface(prose, rules, forks)
    findings += _detect_identity(tex_source, rules)
    if include_orthography:
        findings += _detect_orthography(prose, forks)

    findings.sort(key=lambda f: (f["line"], f["kind"]))
    by_kind: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for f in findings:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1
        by_status[f["status"]] = by_status.get(f["status"], 0) + 1

    enforced = [f for f in findings if f["status"] == "enforced"]
    return {
        "pass": not enforced,
        "findings": findings,
        "count": len(findings),
        "enforced_count": len(enforced),
        "by_kind": by_kind,
        "by_status": by_status,
        "profile": prof.get("profile", "unknown"),
    }


def check_house_style_manuscript(main_tex: Union[str, Path],
                                 profile: Union[dict, str, Path, None] = None,
                                 **kw: Any) -> dict[str, Any]:
    """Convenience: gather a manuscript in ``\\input`` order (the same gatherer the
    conceptric and crossref check use) and sweep the concatenation. Each finding's
    ``where`` is prefixed with its source file."""
    from laplace.pipeline.graph import gather_manuscript_files

    gathered = list(gather_manuscript_files(main_tex))
    # One newline joins each fragment, so a fragment of N lines occupies N lines
    # and the next fragment starts on the following line.
    joined = "\n".join(content for _, content in gathered)
    spans: list[tuple[int, str]] = []   # (1-indexed start line, filename)
    off = 1
    for fp, content in gathered:
        spans.append((off, fp.name))
        off += content.count("\n") + 1

    result = check_house_style(joined, profile, **kw)

    def owner(line: int) -> str:
        name = spans[0][1] if spans else "?"
        for start, fname in spans:
            if line >= start:
                name = fname
            else:
                break
        return name

    for f in result["findings"]:
        f["where"] = f"{owner(f['line'])}:line {f['line']}"
    return result
