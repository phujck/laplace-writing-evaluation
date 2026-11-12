"""The figures organ — the text's figure PROMISES matched to corpus generators,
the generators RUN, their outputs placed as real figure floats at the owning
sites, and a manifest banked; every unmatched promise typed as a
computation-class research intent and given a plain TODO float, never a silent
gap.

The guard gap this closes (PV-20260717T005612Z, "does it look like a paper?"):
every mechanical gate checks what *exists*; nothing checked what the text
*promises but does not contain*. A resource-estimates paper that names a
"sweep-tradeoff plot" and a "witness-scaling plot" and renders neither fails
before any prose judgement. This organ enumerates those promises mechanically,
runs the generators that already sit on disk (``numerics/falqon_figures.py``),
and either places the rendered artefact or bank a typed research intent — the
three-class fork of the arming doc, computation branch.

Design discipline (the asset_model idiom):

* **filesystem-first + plain.** :func:`enumerate_promises` parses the section
  ``.tex`` for named-plot promise phrases; :func:`discover_generators` parses the
  generator script for its ``fig_*`` producers. No token is spent, no compile is
  run, at enumeration time.
* **run is explicit.** :func:`run_generators` subprocesses the generator script
  (deterministic — it reads committed ``*_readings.json``) and returns the real
  artefacts it produced. :func:`run` only mutates the tree when ``apply=True``.
* **plain when unmatched.** A promise with no generator becomes a
  :class:`ResearchIntent` of class ``computation`` plus a visible TODO float at
  the owning site — the promise is never dropped, and the manifest records the
  gap as a first-class row.
* **idempotent placement.** A float is inserted only when its ``\\label`` is not
  already present; a reference sentence only when its ``\\ref`` is absent.
  Re-running the organ mints the same tree.
* **pure at import.** No module-level filesystem or network work.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FigurePromise:
    """A figure the text CLAIMS. ``phrase`` is the named-plot modifier as written
    (``sweep-tradeoff``), ``keywords`` its tokens for matching, ``site`` the
    ``file:line`` where the claim is made."""

    phrase: str
    keywords: tuple[str, ...]
    site_file: str
    site_line: int
    quote: str


@dataclass(frozen=True)
class Generator:
    """A corpus figure generator on disk. ``script`` is the file that produces
    it; ``output`` the basename it ``save``\\ s (``fig_witness``); ``keywords``
    the tokens harvested from its name + docstring line."""

    name: str
    script: str
    output: str
    keywords: tuple[str, ...]


@dataclass
class ResearchIntent:
    """A typed intent banked when a promise has no generator. ``cls`` is one of
    the arming doc's three doors; the figures organ mints only ``computation``
    (a claim needing a generated asset no organ produces)."""

    id: str
    cls: str
    promise: str
    site: str
    note: str
    status: str = "open"
    record: str = "research-intent"


@dataclass
class PlacedFigure:
    """One manifest row: promise -> generator -> artefact -> placed_at."""

    promise: str
    generator: str | None
    artefact: str | None
    placed_at: str | None
    label: str
    matched: bool
    intent_id: str | None = None
    asset_id: str | None = None


@dataclass(frozen=True)
class FigureSpec:
    """An authored identity/placement declaration for one figure output.

    The old ``PLACEMENT`` map remains historical compatibility for manuscripts
    that have not declared a spec.  A supplied spec is the authoritative owner,
    label and public asset id; matching words only select a generator when no
    declaration exists.
    """
    output: str
    section: str
    label: str
    asset_id: str | None = None
    caption: str = ""
    ref_sentence: str = ""

    @classmethod
    def from_dict(cls, value: dict) -> "FigureSpec":
        return cls(output=str(value["output"]), section=str(value["section"]),
                   label=str(value["label"]), asset_id=value.get("asset_id"),
                   caption=str(value.get("caption") or ""),
                   ref_sentence=str(value.get("ref_sentence") or ""))


# --------------------------------------------------------------------------- #
# The placement spec — code, not improvisation. Where each generator's output
# belongs (the OWNING section, not the appendix that merely names it), how it is
# framed, and the reference clause that hooks it into prose. Keyed by generator
# output basename so a re-run is byte-stable.
# --------------------------------------------------------------------------- #

PLACEMENT: dict[str, dict[str, str]] = {
    "fig_witness": {
        "section": "s8.tex",
        "float": "figure*",
        "label": "fig:witness",
        "caption": (
            "The mid-circuit Trotter-error witness, regenerated from "
            "\\texttt{witness\\_readings.json}. Left: the measured flag "
            "probability $P(\\mathrm{flag})$ against the leading-order "
            "$dt^4\\langle K^\\dagger K\\rangle/4$ commutator prediction across "
            "step sizes. Right: infidelity to the exact step for bare Trotter "
            "versus the quiet-branch witnessed protocol."
        ),
        "ref_sentence": (
            "Figure~\\ref{fig:witness} shows the flag-probability scaling "
            "against the commutator prediction and the quiet-branch error "
            "cancellation, both regenerated from \\texttt{witness\\_readings.json}."
        ),
    },
    "fig_resources": {
        "section": "s6.tex",
        "float": "figure*",
        "label": "fig:resources",
        "caption": (
            "The resource estimates and their levers, regenerated from "
            "\\texttt{resource\\_readings.json}. Left: headline wall-clock per "
            "strategy on a log scale. Right: the feedback-precision "
            "$\\varepsilon_{\\mathrm{fb}}$ sweep for the SQL and fully coherent "
            "strategies at $L=500$."
        ),
        "ref_sentence": (
            "Figure~\\ref{fig:resources} plots the headline wall-clock per "
            "strategy and the feedback-precision sweep, regenerated from "
            "\\texttt{resource\\_readings.json}."
        ),
    },
}

# --------------------------------------------------------------------------- #
# Enumeration
# --------------------------------------------------------------------------- #

#: a named plot promise: a hyphenated compound modifier immediately before
#: ``plot``. This is the high-precision signal — ``sweep-tradeoff plot``,
#: ``witness-scaling plot`` — and deliberately does NOT match bare ``figure``
#: (which collides with adjectival compounds like ``first-order figure`` and
#: ``coherent-overhead figure`` that name a numeral, not a graphic).
_NAMED_PLOT_RE = re.compile(r"\b([a-z]+(?:-[a-z]+)+)\s+plots?\b")

#: section source files, in reading order — the body + appendices. Front matter
#: (abstract) is scanned too so an abstract promise is not missed.
_SECTION_GLOBS = ("s*.tex", "appendix_*.tex", "abstract.tex")


def _section_files(manuscript_dir: Path) -> list[Path]:
    seen: list[Path] = []
    for g in _SECTION_GLOBS:
        seen.extend(sorted(manuscript_dir.glob(g)))
    # de-dup while preserving order
    out: list[Path] = []
    for p in seen:
        if p not in out:
            out.append(p)
    return out


def enumerate_promises(manuscript_dir: str | Path) -> list[FigurePromise]:
    """Every named-plot figure promise the text makes, deduped by phrase.

    Filesystem-first: reads the section ``.tex`` off disk, extracts each
    ``<modifier> plot`` phrase with its ``file:line``, and returns one promise
    per distinct phrase (first occurrence wins for the site)."""
    mdir = Path(manuscript_dir)
    promises: dict[str, FigurePromise] = {}
    for f in _section_files(mdir):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, start=1):
            for m in _NAMED_PLOT_RE.finditer(line):
                phrase = m.group(1)
                if phrase in promises:
                    continue
                kws = tuple(t for t in phrase.split("-") if t)
                promises[phrase] = FigurePromise(
                    phrase=phrase,
                    keywords=kws,
                    site_file=f.name,
                    site_line=i,
                    quote=line.strip()[:240],
                )
    return list(promises.values())


# --------------------------------------------------------------------------- #
# Generator discovery
# --------------------------------------------------------------------------- #

_DEF_RE = re.compile(r"^def\s+(fig_\w+)\s*\(", re.MULTILINE)
_SAVE_RE = re.compile(r'save\(\s*fig\s*,\s*"([^"]+)"')
#: the docstring keyword lines: ``fig_witness   - the protocol's verification...``
_DOCLINE_HEAD_RE = re.compile(r"^(fig_\w+)\s+-\s+(.*)$")

_STOP = {
    "the", "and", "a", "an", "of", "to", "for", "in", "on", "at", "by", "its",
    "per", "vs", "left", "right", "with", "that", "this", "each", "both",
}


def _keywords(text: str) -> set[str]:
    toks = re.findall(r"[a-z]+", text.lower())
    return {t for t in toks if len(t) > 2 and t not in _STOP}


def _doclines(src: str) -> dict[str, str]:
    """Map ``fig_x`` -> its full docstring description, joining continuation
    lines. Generator docstrings wrap a single ``fig_x - ...`` entry across
    several indented lines (``... (left,\\n    log scale) and the ... sweep``);
    a single-line regex drops every keyword past the wrap (the ``sweep`` that
    matches the ``sweep-tradeoff`` promise). This walks the docstring, opening a
    buffer at each ``fig_x -`` head and appending continuation lines until the
    next head, a blank line, the closing ``\"\"\"``, or a ``def``."""
    out: dict[str, str] = {}
    cur: str | None = None
    buf: list[str] = []
    for raw in src.splitlines():
        line = raw.strip()
        m = _DOCLINE_HEAD_RE.match(line)
        if m:
            if cur is not None:
                out[cur] = " ".join(buf).strip()
            cur = m.group(1)
            buf = [m.group(2)]
        elif cur is not None:
            if not line or line.startswith('"""') or line.startswith("def "):
                out[cur] = " ".join(buf).strip()
                cur = None
                buf = []
            else:
                buf.append(line)
    if cur is not None:
        out[cur] = " ".join(buf).strip()
    return out


def discover_generators(script: str | Path) -> list[Generator]:
    """Parse a generator script for its ``fig_*`` producers.

    Each ``def fig_x`` becomes a :class:`Generator`; its ``save(fig, "name")``
    call names the output basename; keywords are harvested from the function
    name plus the module docstring's ``fig_x - ...`` line when present."""
    path = Path(script)
    try:
        src = path.read_text(encoding="utf-8")
    except OSError:
        return []
    doclines = _doclines(src)
    # split the source per-function so each save() attaches to its own def
    defs = list(_DEF_RE.finditer(src))
    gens: list[Generator] = []
    for idx, dm in enumerate(defs):
        name = dm.group(1)
        start = dm.end()
        end = defs[idx + 1].start() if idx + 1 < len(defs) else len(src)
        body = src[start:end]
        sm = _SAVE_RE.search(body)
        output = sm.group(1) if sm else name
        kw = _keywords(name.replace("fig_", ""))
        kw |= _keywords(doclines.get(name, ""))
        kw |= _keywords(output.replace("fig_", ""))
        gens.append(Generator(
            name=name, script=str(path), output=output,
            keywords=tuple(sorted(kw)),
        ))
    return gens


# --------------------------------------------------------------------------- #
# Matching
# --------------------------------------------------------------------------- #


def match_promises(
    promises: list[FigurePromise], generators: list[Generator]
) -> tuple[list[tuple[FigurePromise, Generator]], list[FigurePromise]]:
    """Match each promise to its best generator by keyword overlap.

    Returns ``(matched, unmatched)``. A promise matches the generator with the
    greatest keyword-overlap score; a zero-overlap promise is unmatched (its
    declared-absence branch fires)."""
    matched: list[tuple[FigurePromise, Generator]] = []
    unmatched: list[FigurePromise] = []
    for p in promises:
        best: Generator | None = None
        best_score = 0
        for g in generators:
            score = len(set(p.keywords) & set(g.keywords))
            if score > best_score:
                best_score, best = score, g
        if best is not None and best_score > 0:
            matched.append((p, best))
        else:
            unmatched.append(p)
    return matched, unmatched


# --------------------------------------------------------------------------- #
# Running the generators (remote-lawful: a local, deterministic subprocess)
# --------------------------------------------------------------------------- #


def run_generators(script: str | Path, timeout: int = 180) -> tuple[bool, str, list[Path]]:
    """Run the generator script and return ``(ok, log, artefacts)``.

    The script is deterministic — it reads committed ``*_readings.json`` and
    writes ``figures/fig_*.{png,pdf}`` beside the manuscript. Artefacts are the
    ``.pdf`` files found under the sibling ``figures/`` dir after the run."""
    path = Path(script).resolve()
    out_dir = path.parent.parent / "figures"
    try:
        proc = subprocess.run(
            [sys.executable, path.name],
            cwd=str(path.parent), capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as e:  # pragma: no cover
        return False, f"{type(e).__name__}: {e}", []
    ok = proc.returncode == 0
    arts = sorted(out_dir.glob("*.pdf")) if out_dir.exists() else []
    return ok, (proc.stdout + proc.stderr)[-2000:], arts


# --------------------------------------------------------------------------- #
# Placement — idempotent float insertion + reference hook
# --------------------------------------------------------------------------- #

_NODES_ANCHOR_RE = re.compile(r"^% NODES:.*$", re.MULTILINE)


def _float_block(spec: dict[str, str], graphic: str) -> str:
    env = spec.get("float", "figure")
    return (
        f"\n\\begin{{{env}}}\n"
        f"\\centering\n"
        f"\\includegraphics[width=\\linewidth]{{{graphic}}}\n"
        f"\\caption{{{spec['caption']}}}\n"
        f"\\label{{{spec['label']}}}\n"
        f"\\end{{{env}}}\n"
    )


def _todo_block(label: str, promise: str, intent_id: str) -> str:
    """The declared-absence float: a visible placeholder that names the intent, so
    the gap is on the page, not silent."""
    return (
        f"\n\\begin{{figure}}[t]\n\\centering\n"
        f"\\fbox{{\\parbox{{0.9\\linewidth}}{{\\centering\\textbf{{Figure pending.}} "
        f"The \\emph{{{promise}}} is promised by the text but no generator "
        f"produces it. Computation-class research intent \\texttt{{{intent_id}}} "
        f"is banked.}}}}\n"
        f"\\caption{{Promised \\emph{{{promise}}} — not yet generated "
        f"(intent \\texttt{{{intent_id}}}).}}\n"
        f"\\label{{{label}}}\n\\end{{figure}}\n"
    )


def place_figure(section_path: Path, block: str, label: str,
                 ref_sentence: str | None) -> bool:
    """Insert ``block`` into ``section_path`` after its ``% NODES:`` anchor, and
    ensure a ``\\ref{label}`` reference exists. Idempotent: does nothing when the
    label is already present. Returns True when the file was modified."""
    text = section_path.read_text(encoding="utf-8")
    if f"\\label{{{label}}}" in text:
        return False  # already placed
    m = _NODES_ANCHOR_RE.search(text)
    if m:
        cut = m.end()
        new = text[:cut] + "\n" + block + text[cut:]
    else:
        new = block + text
    # ensure the reference hook exists in prose
    if ref_sentence and f"\\ref{{{label}}}" not in new:
        new = new.rstrip() + "\n\n" + ref_sentence + "\n"
    section_path.write_text(new, encoding="utf-8")
    return True


# --------------------------------------------------------------------------- #
# Promise-site reconciliation — the fulfilled promise CLOSED at its claim site
#
# Placement puts the rendered float in the OWNING section (s6/s8); it does not
# touch the PROMISE SITE where the text called the plot a "registered TODO" /
# "not rendered". Left alone, the post-run artefact self-contradicts: s6 renders
# the sweep-tradeoff plot while the appendix still says it is "not rendered in
# this version". This leg neutralises that stale promise prose, idempotently and
# byte-stably, so a fulfilled promise reads as fulfilled everywhere.
#
# Two stale shapes, both keyed off the fulfilled manifest — code, not
# improvisation; a re-run mints the same bytes:
#   * the NAMED-PLOT claim sentence — a sentence naming one or more fulfilled
#     ``<phrase> plot``s AND marked not-rendered is rewritten to a fulfilled
#     restatement that ``\\ref``s the placed floats;
#   * the AGGREGATE residue tally — ``... and N unrendered figures`` inside an
#     ``M items remain open`` list is dropped and the item count decremented,
#     but ONLY when every promised figure is truly rendered (no honest-absence
#     TODO survives); a surviving TODO leaves the tally honest and untouched.
# --------------------------------------------------------------------------- #

#: a fulfilled promise phrase named as ``<phrase> plot`` in prose.
_PLOT_PHRASE_RE = re.compile(r"\b([a-z]+(?:-[a-z]+)+)\s+plots?\b")

#: the tells that a float promise is described as NOT kept.
_NOT_RENDERED_RE = re.compile(
    r"registered TODOs?|neither rendered|not (?:yet )?rendered|"
    r"none rendered|unrendered",
    re.IGNORECASE)

#: the aggregate residue tally's lead count (``Eight items remain open``) and its
#: trailing unrendered-figures clause (``, and two unrendered figures``).
_CARDINALS = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
)
_CARD_INDEX = {w: i for i, w in enumerate(_CARDINALS)}
_TALLY_LEAD_RE = re.compile(
    r"\b(" + "|".join(_CARDINALS) + r")(\s+items?\s+remain\s+open)",
    re.IGNORECASE)
_TALLY_FIG_CLAUSE_RE = re.compile(
    r",\s+and\s+\w+\s+unrendered\s+figures?(?=[.\s])", re.IGNORECASE)

#: split ONE prose line into sentences at ``. `` before a capital or a ``\``
#: macro, keeping the separators so a rejoin is byte-exact. Reconciliation is
#: strictly line-scoped (each manuscript paragraph is a single physical line):
#: splitting the whole file would let a chunk span a paragraph/comment boundary
#: and a rewrite would then swallow unrelated prose.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.])(\s+)(?=[A-Z\\])")

#: a LaTeX comment line — never reconciled (a ``% NODES:`` / ``% appendix-p15``
#: marker must survive verbatim).
_COMMENT_LINE_RE = re.compile(r"^\s*%")


def _decrement_cardinal(word: str) -> str:
    """``Eight`` -> ``Seven``, preserving the leading-capital case. Unknown words
    (out of the small tally range) are returned unchanged."""
    n = _CARD_INDEX.get(word.lower())
    if n is None or n - 1 < 0:
        return word
    out = _CARDINALS[n - 1]
    return out.capitalize() if word[:1].isupper() else out


def _fulfilled_sentence(ordered: list[tuple[str, str]]) -> str:
    """The fulfilled restatement for one or more now-rendered named plots:
    ``The <phrase> plot (Figure~\\ref{<label>}) and ... are rendered in this
    version from the committed readings JSONs.``"""
    parts = [f"the {ph} plot (Figure~\\ref{{{label}}})" for ph, label in ordered]
    if len(parts) == 1:
        subj, verb = parts[0], "is"
    else:
        subj = ", ".join(parts[:-1]) + " and " + parts[-1]
        verb = "are"
    subj = subj[:1].upper() + subj[1:]
    return (f"{subj} {verb} rendered in this version from the committed "
            f"readings JSONs.")


def _rewrite_named_plot_line(line: str, fulfilled: dict[str, str]) -> str:
    """Within ONE prose line, rewrite each sentence that names ONLY fulfilled
    ``<phrase> plot``s and marks them not-rendered into a fulfilled restatement.
    A sentence naming a plot that is NOT fulfilled is left untouched (mixed state
    stays plain); the rewrite never crosses the line."""
    parts = _SENTENCE_SPLIT_RE.split(line)
    # parts alternates sentence, separator, sentence, separator, ...
    for i in range(0, len(parts), 2):
        sent = parts[i]
        phrases = [m.group(1) for m in _PLOT_PHRASE_RE.finditer(sent)]
        if not phrases or not _NOT_RENDERED_RE.search(sent):
            continue
        if any(ph not in fulfilled for ph in phrases):
            continue  # a not-yet-fulfilled plot shares the sentence — leave it
        seen: list[str] = []
        for ph in phrases:  # order by appearance, de-duped
            if ph not in seen:
                seen.append(ph)
        leading = sent[:len(sent) - len(sent.lstrip())]
        parts[i] = leading + _fulfilled_sentence(
            [(ph, fulfilled[ph]) for ph in seen])
    return "".join(parts)


def _neutralise_residue_tally_line(line: str) -> str:
    """Within ONE prose line, drop a ``, and N unrendered figures`` clause from
    an ``M items remain open`` list and decrement the item count. The clause and
    the lead count sit in the same paragraph (one physical line), so decrement
    only when the clause was actually dropped on this line."""
    new, n = _TALLY_FIG_CLAUSE_RE.subn("", line)
    if n == 0:
        return line
    for _ in range(n):  # one residue ITEM removed per dropped clause
        new = _TALLY_LEAD_RE.sub(
            lambda m: _decrement_cardinal(m.group(1)) + m.group(2), new, count=1)
    return new


def reconcile_promise_prose(manuscript_dir: str | Path,
                            fulfilled: dict[str, str],
                            *, all_fulfilled: bool) -> list[str]:
    """Neutralise stale "not rendered" promise prose for the FULFILLED figures.

    ``fulfilled`` maps each placed-and-matched promise phrase to its float label.
    ``all_fulfilled`` is True only when NO promise was typed as a declared-absence
    TODO — the guard that lets the aggregate residue tally be decremented safely.

    Line-scoped by construction: every manuscript paragraph is one physical line
    and comment lines are skipped, so a rewrite can never swallow an adjacent
    paragraph or a ``% ...`` marker. Returns the sorted list of section files
    modified. Idempotent: once a stale sentence is rewritten it no longer carries
    a not-rendered marker, so a re-run is a byte-stable no-op."""
    mdir = Path(manuscript_dir)
    if not fulfilled:
        return []
    changed: list[str] = []
    for f in _section_files(mdir):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        out_lines: list[str] = []
        for line in text.splitlines(keepends=True):
            if _COMMENT_LINE_RE.match(line):
                out_lines.append(line)
                continue
            new_line = _rewrite_named_plot_line(line, fulfilled)
            if all_fulfilled:
                new_line = _neutralise_residue_tally_line(new_line)
            out_lines.append(new_line)
        new = "".join(out_lines)
        if new != text:
            f.write_text(new, encoding="utf-8")
            changed.append(f.name)
    return sorted(changed)


# --------------------------------------------------------------------------- #
# The orchestration — the organ's run() entrypoint
# --------------------------------------------------------------------------- #


def run(manuscript_dir: str | Path, script: str | Path,
        apply: bool = False, run_gen: bool = True,
        figure_specs: list[FigureSpec | dict] | None = None) -> dict:
    """Enumerate promises, match generators, (optionally run + place), bank the
    manifest and any computation-class research intents.

    ``apply=False`` is a dry run: promises/matches are computed and returned but
    the tree is not mutated. ``apply=True`` runs the generators (unless
    ``run_gen=False``), copies artefacts into ``manuscript/figures/``, places the
    floats, and writes the manifest + intents under ``manuscript/``.

    Returns a dict manifest: ``{promises, matched, placed[], intents[],
    generator_run}``."""
    mdir = Path(manuscript_dir)
    promises = enumerate_promises(mdir)
    generators = discover_generators(script)
    matched, unmatched = match_promises(promises, generators)
    declared_specs: dict[str, FigureSpec] = {}
    for value in figure_specs or []:
        try:
            spec = value if isinstance(value, FigureSpec) else FigureSpec.from_dict(value)
        except (KeyError, TypeError, ValueError):
            continue
        declared_specs[spec.output] = spec

    gen_ok, gen_log, artefacts = (True, "not-run", [])
    if apply and run_gen and matched:
        gen_ok, gen_log, artefacts = run_generators(script)

    fig_dir = mdir / "figures"
    placed: list[PlacedFigure] = []
    intents: list[ResearchIntent] = []

    # matched promises -> real floats
    for promise, gen in matched:
        declared = declared_specs.get(gen.output)
        if declared:
            # Identity and owning site are declared.  Historic display prose is
            # only a compatibility fallback, never a way to choose the site.
            legacy = PLACEMENT.get(gen.output, {})
            spec = {
                "section": declared.section, "label": declared.label,
                "float": legacy.get("float", "figure"),
                "caption": declared.caption or legacy.get("caption", ""),
                "ref_sentence": declared.ref_sentence or legacy.get("ref_sentence", ""),
            }
        else:
            spec = PLACEMENT.get(gen.output)
        label = spec["label"] if spec else f"fig:{gen.output}"
        section = spec["section"] if spec else None
        artefact_src = None
        if apply and gen_ok:
            src = (Path(script).resolve().parent.parent / "figures"
                   / f"{gen.output}.pdf")
            if src.exists():
                fig_dir.mkdir(parents=True, exist_ok=True)
                dst = fig_dir / src.name
                shutil.copy2(src, dst)
                artefact_src = f"figures/{src.name}"
        placed_at = None
        if apply and spec and section and artefact_src:
            spath = mdir / section
            if spath.exists():
                did = place_figure(
                    spath, _float_block(spec, f"figures/{gen.output}"),
                    label, spec.get("ref_sentence"),
                )
                placed_at = f"{section}" if did or (
                    f"\\label{{{label}}}" in spath.read_text(encoding="utf-8")
                ) else None
        placed.append(PlacedFigure(
            promise=promise.phrase, generator=gen.name,
            artefact=artefact_src or (f"figures/{gen.output}.pdf" if not apply else None),
            placed_at=placed_at or (section if not apply else placed_at),
            label=label, matched=True,
            asset_id=(declared.asset_id if declared else None),
        ))
        # Retain the explicit identity alongside the historical placed row.
        # Readers which only know ``placed`` remain compatible.

    # unmatched promises -> computation-class research intents + TODO floats
    for i, promise in enumerate(unmatched):
        intent_id = f"RI-COMP-{promise.phrase}"
        intent = ResearchIntent(
            id=intent_id, cls="computation", promise=promise.phrase,
            site=f"{promise.site_file}:{promise.site_line}",
            note=(f"The text promises a '{promise.phrase} plot' at "
                  f"{promise.site_file}:{promise.site_line} but no corpus "
                  f"generator produces it. Computation-class: needs a generated "
                  f"asset. Banked as the figures organ's honest-absence branch."),
        )
        intents.append(intent)
        label = f"fig:todo-{promise.phrase}"
        placed_at = None
        if apply:
            spath = mdir / promise.site_file
            if spath.exists():
                did = place_figure(
                    spath, _todo_block(label, promise.phrase, intent_id),
                    label, None)
                placed_at = promise.site_file if did else None
        placed.append(PlacedFigure(
            promise=promise.phrase, generator=None, artefact=None,
            placed_at=placed_at or (promise.site_file if not apply else placed_at),
            label=label, matched=False, intent_id=intent_id,
        ))

    # close every fulfilled promise at ITS claim site: the stale "not rendered"
    # prose is neutralised so the post-run artefact does not contradict s6/s8.
    reconciled: list[str] = []
    if apply:
        fulfilled = {p.promise: p.label for p in placed
                     if p.matched and p.placed_at}
        reconciled = reconcile_promise_prose(
            mdir, fulfilled, all_fulfilled=(len(unmatched) == 0))

    manifest = {
        "organ": "figure_runner",
        "manuscript": str(mdir),
        "generator_script": str(script),
        "promises": [asdict(p) for p in promises],
        "generators": [asdict(g) for g in generators],
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
        "generator_run": {"attempted": apply and run_gen and bool(matched),
                          "ok": gen_ok, "artefacts": [str(a) for a in artefacts],
                          "log_tail": gen_log if apply else "not-run"},
        "placed": [asdict(p) for p in placed],
        "figure_specs": [asdict(spec) for _, spec in sorted(declared_specs.items())],
        "intents": [asdict(i) for i in intents],
        "reconciled_sites": reconciled,
    }

    if apply:
        (mdir / "figure_manifest.json").write_text(
            json.dumps(manifest, indent=1), encoding="utf-8")
        if intents:
            _bank_intents(mdir, intents)
    return manifest


def _bank_intents(mdir: Path, intents: list[ResearchIntent]) -> None:
    """Append the computation-class intents to the research-intent ledger
    (JSONL, one live record per line — the gap ledger's substrate-absent door)."""
    ledger = mdir / "research_intents.jsonl"
    existing = set()
    if ledger.exists():
        for line in ledger.read_text(encoding="utf-8").splitlines():
            try:
                existing.add(json.loads(line).get("id"))
            except json.JSONDecodeError:
                pass
    with ledger.open("a", encoding="utf-8") as fh:
        for it in intents:
            if it.id in existing:
                continue
            fh.write(json.dumps(asdict(it)) + "\n")


# --------------------------------------------------------------------------- #
# The lawful reader — the banked manifest read back as facts, zero re-execution
#
# view=mechanism: the /pipeline figures sub-card reads its state THROUGH this
# function, never by re-parsing ``figure_manifest.json`` itself and never by
# re-running :func:`run` on the GET path (that would compile the tex and
# subprocess the generators — a boom on a pure read). The reader does exactly
# one filesystem read (``read_text``) and one ``json.loads``; no subprocess, no
# compile, no network, no write. Honest-absence is a first-class return, never a
# raise: a NEVER_RUN project has no manifest, and the card must render "no banked
# run · N promised-but-absent" from a ``present: False`` payload, not from an
# exception.
# --------------------------------------------------------------------------- #

#: the absent-shape facts, every count zeroed and every list empty. Returned
#: verbatim when the manifest is missing OR unreadable/corrupt — a boom-guard so
#: a truncated artifact still yields the honest-absence card, not a 500.
_EMPTY_MANIFEST_FACTS: dict = {
    "present": False,
    "manuscript": "",
    "generator_script": "",
    "figures_placed": 0,
    "promises_total": 0,
    "promises_matched": 0,
    "promises_absent": 0,
    "intents_banked": 0,
    "generator_run": {"attempted": False, "ok": None, "artefacts": 0,
                      "log_tail": ""},
    "placed": [],
    "intents": [],
    "reconciled_sites": [],
}


def read_manifest(manuscript_dir: str | Path) -> dict:
    """Read the banked ``figure_manifest.json`` back as the figures organ's
    facts. Pure read: one ``read_text`` + one ``json.loads``, no subprocess, no
    compile, no network, no write.

    The dict ALWAYS carries ``present``. When the manifest is absent (a
    NEVER_RUN project) or unreadable/corrupt, returns the declared-absence shape —
    ``present: False`` with every count zeroed and every list empty — never
    raises and never returns ``None``. When present, ``present: True`` plus:

    * ``figures_placed`` — matched promises rendered as real floats at an owning
      site (``placed`` rows with ``matched`` and a ``placed_at``);
    * ``promises_total`` / ``promises_matched`` / ``promises_absent`` — the
      text's named-plot claims, how many a generator serves, and how many are
      promised-but-absent (the declared-absence / computation-class branch);
    * ``intents_banked`` — computation-class research intents banked for the
      absent promises;
    * ``generator_run`` — whether the last fire ran the generators, its ok flag,
      the artefact count and log tail;
    * ``placed`` / ``intents`` / ``reconciled_sites`` — the raw manifest rows the
      card renders per-figure, passed through as the organ wrote them.
    """
    path = Path(manuscript_dir) / "figure_manifest.json"
    # ONE boom-guard over json.loads AND the whole field extraction (the
    # detector_organs.read_detector_organs exemplar): a valid-JSON-but-wrong-typed
    # manifest (e.g. ``placed`` an int, ``promises`` an int) must degrade to the
    # honest-absence facts, never raise a 500 on this GET path.
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {**_EMPTY_MANIFEST_FACTS,
                    "generator_run": dict(_EMPTY_MANIFEST_FACTS["generator_run"])}
        placed = [p for p in (raw.get("placed") or []) if isinstance(p, dict)]
        intents = [i for i in (raw.get("intents") or []) if isinstance(i, dict)]
        figures_placed = sum(
            1 for p in placed if p.get("matched") and p.get("placed_at"))
        intents_banked = sum(1 for i in intents if i.get("cls") == "computation")
        gen_run = raw.get("generator_run") if isinstance(
            raw.get("generator_run"), dict) else {}
        arts = gen_run.get("artefacts")
        return {
            "present": True,
            "manuscript": raw.get("manuscript", ""),
            "generator_script": raw.get("generator_script", ""),
            "figures_placed": figures_placed,
            "promises_total": len(raw.get("promises") or []),
            "promises_matched": int(raw.get("matched_count") or 0),
            "promises_absent": int(raw.get("unmatched_count") or 0),
            "intents_banked": intents_banked,
            "generator_run": {
                "attempted": bool(gen_run.get("attempted", False)),
                "ok": gen_run.get("ok"),
                "artefacts": len(arts) if isinstance(arts, list) else 0,
                "log_tail": str(gen_run.get("log_tail", "")),
            },
            "placed": placed,
            "intents": intents,
            "reconciled_sites": raw.get("reconciled_sites") or [],
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        # missing, unreadable, malformed JSON, or valid-JSON-but-wrong-typed fields
        return {**_EMPTY_MANIFEST_FACTS,
                "generator_run": dict(_EMPTY_MANIFEST_FACTS["generator_run"])}


if __name__ == "__main__":  # pragma: no cover
    import argparse
    ap = argparse.ArgumentParser(description="the figures organ")
    ap.add_argument("manuscript")
    ap.add_argument("script")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    out = run(a.manuscript, a.script, apply=a.apply)
    print(json.dumps({k: v for k, v in out.items()
                      if k not in ("promises", "generators")}, indent=1))
