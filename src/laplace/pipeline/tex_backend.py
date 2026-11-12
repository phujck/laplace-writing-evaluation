"""Stage G — the LaTeX backend under a typography profile (mandate §10).

LaTeX is a constrained backend for settled semantic objects. The profile
(``profiles/typography/*.json``) owns the physical form — document class,
packages, figure and table conventions, label and bibliography conventions —
and this module is the one producer of:

- the assembled ``main.tex`` (preamble + title block + abstract + ``\\input``
  order from the plan + backend-emitted figure environments + appendix split
  + bibliography);
- per-figure environment files ``figures_tex/<fid>.tex``, rendered from the
  stage-B figure SPECS (caption settled at the spec, the no-titles law held
  by construction — prose fragments only ever ``\\ref`` a figure).

Deterministic: same plan + spec + profile → byte-identical output
(golden-testable). Prose never decides typography; typography never touches
prose.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from laplace.pipeline import pathsafe, projection_spec, registry, schema, tex_template

DEFAULT_PROFILE = "profiles/typography/prx-revtex4-2.json"


def load_profile(path: str | Path | None = None,
                 repo_root: Path | None = None) -> dict[str, Any]:
    rr = Path(repo_root) if repo_root else registry._repo_root()
    p = rr / (path or DEFAULT_PROFILE)
    return json.loads(p.read_text(encoding="utf-8"))


def render_preamble(profile: dict, record: dict) -> str:
    """Emit the documentclass + package preamble from the profile.

    When the profile declares a ``house_layer`` (e.g. ``"eigen-revtex"``), the
    layer is emitted as ``\\usepackage{<layer>}`` and every package it already
    provides (``tex_template.LAYER_PROVIDES``, the single trim source) is DROPPED
    from the individual ``\\usepackage`` lines. This makes the emitted preamble
    agree with :func:`tex_template.check_template`: documentclass + the house
    layer + only the packages the layer does not provide. Without a ``house_layer``
    the full package list is emitted verbatim (legacy behaviour)."""
    opts = ",".join(profile.get("documentclass_options") or [])
    lines = [f"\\documentclass[{opts}]{{{profile.get('documentclass', 'revtex4-2')}}}"]
    layer = profile.get("house_layer")
    if layer:
        lines.append(f"\\usepackage{{{layer}}}")
    for pkg in profile.get("packages") or []:
        name = pkg[0] if isinstance(pkg, (list, tuple)) else pkg
        if layer and name in tex_template.LAYER_PROVIDES:
            continue                         # provided transitively by the layer
        if isinstance(pkg, (list, tuple)):
            _, opt = pkg
            lines.append(f"\\usepackage[{opt}]{{{name}}}")
        else:
            lines.append(f"\\usepackage{{{pkg}}}")
    for macro in (profile.get("macros") or []) + (record.get("macros") or []):
        lines.append(macro)
    return "\n".join(lines)


def render_title_block(record: dict) -> str:
    lines = [f"\\title{{{record.get('working_title', 'Untitled')}}}"]
    for author in record.get("authors") or []:
        name = author.get("name", "")
        orcid = author.get("orcid", "")
        lines.append(f"\\author{{{name}"
                     + (f"\\orcidlink{{{orcid}}}" if orcid else "") + "}")
        for aff in author.get("affiliations") or []:
            lines.append(f"\\affiliation{{{aff}}}")
        if author.get("email"):
            lines.append(f"\\email{{{author['email']}}}")
    abstract = record.get("abstract", "")
    if record.get("abstract_fragment"):
        abstract = f"\\input{{{record['abstract_fragment']}}}"
    if abstract:
        lines += ["", "\\begin{abstract}", abstract, "\\end{abstract}", ""]
    lines.append("\\maketitle")
    return "\n".join(lines)


# --- caption-projection reduction (the scaffold-wipe on the caption surface) --
# The stage-B spec caption is settled under the four-question caption law:
#   Q1 what is shown   Q2 how it was made   Q3 what claim it supports
#   Q4 what it does NOT establish.
# Q1/Q2 are what the READER of the finished object needs; Q3/Q4 are construction
# scaffold. At the emit boundary the caption is reduced to the reader-facing
# fields (what-shown / how / the one observation) plus at most ONE qualification;
# the Q3 claim-support content migrates to the BODY (a routed finding for the
# prose stage, never silently dropped) and surplus Q4 non-claims fall to metadata.
# The FULL spec caption stays in the spec (the substrate); only the RENDERED
# caption is reduced. `check_caption_scaffold` in ``scaffold_wipe`` is the
# conjugate verify pass, and shares this one classifier.

_CAPTION_ABBR = frozenset(
    "fig figs eq eqs sec secs app apps ref refs cf e.g i.e vs al no dr tab tabs "
    "pp ch st".split()
)
#: Q3 — the sentence's job is to say what claim the figure supports.
_CAPTION_Q3_RE = re.compile(
    r"\b(support(?:s|ing)?|establish(?:es|ing)?|demonstrat(?:es|ing)?|"
    r"confirm(?:s|ing)?|is\s+evidence)\b[^.]*\bclaim\b"
    r"|\bthe\s+figure\s+supports\b", re.IGNORECASE)
#: Q4 — the sentence's job is to fence what the figure does NOT establish.
_CAPTION_Q4_RE = re.compile(
    r"\bestablish(?:es)?\s+nothing\b|\bdoes\s+not\s+"
    r"(?:establish|show|prove|assert|claim|imply|demonstrate)\b"
    r"|\bmakes?\s+no\s+claim\b|\bcannot\s+be\s+(?:read|taken)\s+as\b"
    r"|\bis\s+not\s+(?:a\s+claim|evidence)\b", re.IGNORECASE)


def _split_sentences(text: str) -> list[str]:
    """Sentence split that survives inline math and the house abbreviations
    (Fig./Eq./Sec./e.g./i.e.), so the caption reducer classifies real sentences,
    not fragments broken at ``$c_k(s,\\tau)$.`` or ``Eqs.``."""
    text = " ".join((text or "").split())
    parts = re.split(r"(?<=[.!?])\s+", text)
    out: list[str] = []
    for p in parts:
        if out:
            tail = out[-1].rstrip()
            last = re.findall(r"[A-Za-z.]+", tail)
            lw = (last[-1].lower().rstrip(".") if last else "")
            # merge back if the previous chunk ended on an abbreviation or a
            # single-letter initial (``H.``), i.e. the split was spurious.
            if lw in _CAPTION_ABBR or re.search(r"\b[A-Za-z]\.$", tail):
                out[-1] = out[-1] + " " + p
                continue
        out.append(p)
    return [s for s in out if s.strip()]


def _reduce_caption(caption: str) -> dict:
    """Project a settled four-question caption to its reader-facing reduction.

    Returns ``{reduced, to_body, to_metadata}``: the rendered caption keeps the
    what-shown / how-made / observation sentences plus at most one qualification;
    ``to_body`` are the Q3 claim-support sentences (route to the prose stage);
    ``to_metadata`` are the surplus Q4 non-claim sentences beyond the one kept.
    A caption with no reader-facing sentence is left whole (never emptied)."""
    sentences = _split_sentences(caption)
    reader, q3, q4 = [], [], []
    for s in sentences:
        if _CAPTION_Q3_RE.search(s):
            q3.append(s)
        elif _CAPTION_Q4_RE.search(s):
            q4.append(s)
        else:
            reader.append(s)
    if not reader:                      # safeguard: never emit an empty caption
        return {"reduced": " ".join(sentences).strip(), "to_body": [],
                "to_metadata": []}
    kept_qual = q4[:1]
    reduced = " ".join(reader + kept_qual).strip()
    return {"reduced": reduced, "to_body": q3, "to_metadata": q4[1:]}


#: characters that must be escaped before a spec's plain-prose field (a question,
#: a function line) can be set as LaTeX body text inside the absence float.
_TEX_ESCAPES = ((chr(92), r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
                ("}", r"\}"), ("~", r"$\sim$"), ("^", r"\^{}"))


#: design-voice SHOUTED emphasis (``What IS a ...``) that must not reach the page.
#: Restricted to function words, so real short acronyms (SVD, QRC, NMSE) survive.
_SHOUTED_FUNCTION_WORDS = frozenset(
    {"IS", "ARE", "WAS", "NOT", "AND", "THE", "ALL", "ANY", "DO", "DOES", "CAN",
     "WHY", "HOW", "MUST", "NEVER", "ONLY", "NO"})


def _tex_plain(text: str) -> str:
    """A spec plain-prose field made safe to typeset as body text: LaTeX-escaped,
    with the spec's shouted design-voice emphasis erased at the emit boundary."""
    words = [(w.lower() if w in _SHOUTED_FUNCTION_WORDS else w)
             for w in (text or "").split()]
    out = " ".join(words)
    for ch, rep in _TEX_ESCAPES:
        out = out.replace(ch, rep)
    return out


def _render_absence_float(fid: str, fs: dict, star: str, conv: dict) -> list[str]:
    """The Declared-absence float for a figure whose asset is not banked.

    The house idiom (``figure_runner._todo_block``): rather than omit the float —
    which silently turns the prose's promise into an unfulfilled one and prints
    every ``\\ref`` to it as ``??`` — emit a numbered, labelled, visibly framed
    float that names the question the asset would answer and states plainly that
    no generator produces it yet. The gap is then On the page, where a reader and
    a referee can both see it, and the document's cross-reference graph stays
    whole. The spec's own deferral reason is kept as substrate (a comment), never
    typeset: it is build-side bookkeeping, not reader-facing prose."""
    # the QUESTION is the only reader-facing field a deferred spec reliably has:
    # ``function`` is design-side voice and may carry a hardcoded figure number
    # that would contradict the float's real one, so it stays substrate.
    question = _tex_plain(fs.get("question_answered", ""))
    label = fs.get("figure_id", fid)
    placement = "t" if star else fs.get("placement_hint", conv.get("placement", "tb"))
    body = [f"\\begin{{figure{star}}}[{placement}]",
            "    \\centering",
            "    \\fbox{\\parbox{0.92\\linewidth}{\\centering\\vspace{1ex}",
            "    \\textbf{Figure pending.}\\\\[0.6ex]",
            "    This figure is promised by the text, but no generator produces "
            "it yet.",
            "    \\vspace{1ex}}}"]
    cap = "Promised figure, not yet generated."
    if question:
        tail = question if question[-1] in ".?!" else question + "."
        cap = f"{cap} It would answer: {tail}"
    body += [f"    \\caption{{{cap}}}",
             f"    \\label{{{label}}}"]
    reason = " ".join((fs.get("deferred_reason") or "").split())
    if reason:
        body.append(f"    % DEFERRAL (substrate, never typeset): {reason}")
    caption = " ".join((fs.get("caption") or "").split())
    if caption:
        body.append(f"    % CAPTION-METADATA: the settled caption is held in the "
                    f"{fid} figure spec until the asset exists")
    body.append(f"\\end{{figure{star}}}")
    return body


def render_figure_env(fid: str, fs: dict, profile: dict) -> str:
    """One figure environment from its stage-B spec. The caption is the spec's
    settled caption, REDUCED at the emit boundary to its reader-facing projection
    (:func:`_reduce_caption`): the four-question construction caption keeps
    what-shown / how / one observation / one qualification, while the Q3
    claim-support content migrates to the body as a routed finding and surplus Q4
    non-claims fall to metadata — nothing is silently deleted, and the full spec
    caption stays in the spec. A deferred figure renders as the DECLARED-ABSENCE
    FLOAT — the house honest-absence idiom (``figure_runner._todo_block``): a
    visible, numbered, labelled placeholder that names the question the asset
    would answer and why no asset exists, so the gap is On the page and every
    ``\\ref`` to it still resolves. Never a broken include, and never a silent
    omission either: an omitted float is what makes the prose's promise read as
    absent and its cross-references print as ``??``."""
    conv = profile.get("figures") or {}
    star = "*" if fs.get("width") in {"double", "double-column"} else ""
    width = conv.get("double_width" if star else "single_width", r"\linewidth")
    label = fs.get("figure_id", fid)
    asset = fs.get("asset") or ""
    lines = [f"% figure environment generated by tex_backend from the figure spec",
             f"% spec: {fid} (status: {fs.get('status', 'unknown')})"]
    if fs.get("status") != "banked" or not asset:
        lines += [f"% DEFERRED: {fs.get('question_answered', '')}"]
        lines += _render_absence_float(fid, fs, star, conv)
        return "\n".join(lines) + "\n"
    caption = fs.get("caption", "")
    red = _reduce_caption(caption)
    lines += [f"\\begin{{figure{star}}}[{fs.get('placement_hint', conv.get('placement', 'tb'))}]",
              "    \\centering",
              f"    \\includegraphics[width={width}]{{{asset}}}",
              f"    \\caption{{{red['reduced']}}}",
              f"    \\label{{{label}}}"]
    # the erased scaffold is KEPT in the substrate (comments never render into the
    # PDF): Q3 routed to the prose stage, surplus Q4 parked as metadata.
    for s in red["to_body"]:
        lines.append(f"    % ROUTED-FINDING kind=caption-scaffold owning_stage=prose: {s}")
    for s in red["to_metadata"]:
        lines.append(f"    % CAPTION-METADATA (non-claim, erased from emit): {s}")
    if red["reduced"] != " ".join(_split_sentences(caption)).strip():
        lines.append(f"    % CAPTION-METADATA: full spec caption retained in the {fid} figure spec")
    lines.append(f"\\end{{figure{star}}}")
    return "\n".join(lines) + "\n"


def render_table_env(tid: str, ts: dict, profile: dict) -> str:
    """One table environment from its stage-B spec: caption above (the house
    convention), ruledtabular body, literal row cells settled at the spec."""
    columns = ts.get("columns") or []
    rows = ts.get("rows") or []
    star = "*" if ts.get("width") == "double" else ""
    label = ts.get("table_id", tid)
    lines = [f"% table environment generated by tex_backend from the table spec",
             f"% spec: {tid}"]
    if not (columns and rows):
        lines += [f"% DEFERRED: {ts.get('question_answered', '')} (no row cells settled)"]
        return "\n".join(lines) + "\n"
    colspec = "l" * len(columns)
    lines += [f"\\begin{{table{star}}}[t]",
              f"\\caption{{{ts.get('caption', '')}}}",
              f"\\label{{{label}}}",
              "\\begin{ruledtabular}",
              f"\\begin{{tabular}}{{{colspec}}}",
              " & ".join(f"\\textbf{{{c}}}" for c in columns) + r" \\ \hline"]
    lines += [" & ".join(cell for cell in row) + r" \\" for row in rows]
    lines += ["\\end{tabular}", "\\end{ruledtabular}", f"\\end{{table{star}}}"]
    return "\n".join(lines) + "\n"


def write_tables_tex(project: str, repo_root: Path | None = None) -> list[Path]:
    proj = registry.resolve(project, repo_root=repo_root) if repo_root is not None else registry.resolve(project)
    if proj is None:
        return []
    spec = projection_spec.load_spec(project, repo_root) or {}
    profile = load_profile((spec.get("manuscript") or {}).get("typography_profile"),
                           repo_root)
    tex_dir = proj.resolved_target_dir(repo_root)
    if tex_dir is None:
        return []
    out_dir = tex_dir / "tables_tex"
    written: list[Path] = []
    tables = spec.get("tables") or {}
    if tables:
        out_dir.mkdir(parents=True, exist_ok=True)
    for tid, ts in sorted(tables.items()):
        p = out_dir / f"{pathsafe.encode_sid_for_path(tid)}.tex"
        p.write_text(render_table_env(tid, ts, profile), encoding="utf-8")
        written.append(p)
    return written


def write_figures_tex(project: str, repo_root: Path | None = None) -> list[Path]:
    proj = registry.resolve(project, repo_root=repo_root) if repo_root is not None else registry.resolve(project)
    if proj is None:
        return []
    spec = projection_spec.load_spec(project, repo_root) or {}
    profile = load_profile((spec.get("manuscript") or {}).get("typography_profile"),
                           repo_root)
    tex_dir = proj.resolved_target_dir(repo_root)
    if tex_dir is None:
        return []
    out_dir = tex_dir / "figures_tex"
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fid, fs in sorted((spec.get("figures") or {}).items()):
        p = out_dir / f"{pathsafe.encode_sid_for_path(fid)}.tex"
        p.write_text(render_figure_env(fid, fs, profile), encoding="utf-8")
        written.append(p)
    return written


def assemble_main_tex(project: str, repo_root: Path | None = None,
                      write: bool = True) -> str:
    """The whole document from plan + spec + profile. Figure environments are
    injected AFTER the ``\\input`` of the section their spec places them in —
    floats find their own page; prose stays free of environments."""
    proj = registry.resolve(project, repo_root=repo_root) if repo_root is not None else registry.resolve(project)
    if proj is None:
        raise ValueError(f"unknown project {project!r}")
    plan = proj.read_plan(repo_root) or {}
    spec = projection_spec.load_spec(project, repo_root) or {}
    record = spec.get("manuscript") or {}
    profile = load_profile(record.get("typography_profile"), repo_root)

    figs_by_section: dict[str, list[str]] = {}
    for fid, fs in (spec.get("figures") or {}).items():
        # EVERY spec figure is inputted, banked or not: a banked one renders its
        # asset, a deferred one renders the declared-absence float. Skipping the
        # deferred ones is what left the prose promising a figure the artefact
        # never showed and its \ref printing as ``??``.
        figs_by_section.setdefault(fs.get("placement", ""), []).append(fid)
    tables_by_section: dict[str, list[str]] = {}
    for tid, ts in (spec.get("tables") or {}).items():
        if ts.get("rows"):
            tables_by_section.setdefault(ts.get("placement", ""), []).append(tid)

    parts = [render_preamble(profile, record), "", r"\begin{document}", "",
             render_title_block(record), ""]
    def _env_inputs(sid: str) -> list[str]:
        out = [f"\\input{{figures_tex/{pathsafe.encode_sid_for_path(fid)}}}"
               for fid in sorted(figs_by_section.get(sid, []))]
        out += [f"\\input{{tables_tex/{pathsafe.encode_sid_for_path(tid)}}}"
                for tid in sorted(tables_by_section.get(sid, []))]
        return out

    for sec in plan.get("sections") or []:
        sid = sec["id"]
        parts.append(f"\\input{{{pathsafe.encode_sid_for_path(sid)}}}")
        parts.extend(_env_inputs(sid))
    apps = plan.get("appendices") or []
    if apps:
        parts += ["", r"\appendix"]
        for app in apps:
            parts.append(f"\\input{{{pathsafe.encode_sid_for_path(app['id'])}}}")
            parts.extend(_env_inputs(app["id"]))
    acknowledgements = record.get("acknowledgements", "")
    if acknowledgements:
        parts += [
            "",
            r"\begin{acknowledgments}",
            acknowledgements,
            r"\end{acknowledgments}",
        ]
    bib = profile.get("bibliography", {})
    bib_file = record.get("bibliography") or bib.get("file", "literature")
    parts += ["", f"\\bibliography{{{bib_file}}}", "", r"\end{document}", ""]
    text = "\n".join(parts)

    if write:
        tex_dir = proj.resolved_target_dir(repo_root)
        if tex_dir is not None:
            tex_dir.mkdir(parents=True, exist_ok=True)
            (tex_dir / "main.tex").write_text(text, encoding="utf-8")
    return text


def render_report(project: str, repo_root: Path | None = None) -> dict[str, Any]:
    """The stage's contract face: profile loads, figure envs render, assembly
    returns a document — without writing anything."""
    try:
        proj = registry.resolve(project, repo_root=repo_root) if repo_root is not None else registry.resolve(project)
        spec = projection_spec.load_spec(project, repo_root) or {}
        profile = load_profile((spec.get("manuscript") or {}).get("typography_profile"),
                               repo_root)
        text = assemble_main_tex(project, repo_root, write=False) if proj else ""
        return {"pass": bool(text) and text.startswith("\\documentclass"),
                "documentclass": profile.get("documentclass"),
                "n_lines": text.count("\n")}
    except Exception as e:  # the contract face reports, never raises
        return {"pass": False, "error": f"{type(e).__name__}: {e}"}
