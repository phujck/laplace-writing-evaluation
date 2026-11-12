"""Medium-general voice linter for the Laplace voice.

One voice, many media (canon://aesthetics/voice_and_style). ``latex_forge`` lints
LaTeX manuscripts; this lints the rest - markdown, HTML, Slidev/Vue decks, plain
prose - for the same no-slop voice. It supersedes the archived ``html_mechanic``.

The hard part is not the rules, it is *where they apply*. A semicolon in a code
fence, ``color`` in a CSS block, an em-dash inside ``$...$`` KaTeX, a ``%`` in a
LaTeX comment - none of those are prose, and flagging them is noise. So the linter
first blanks every non-prose region (length-preserving, so line numbers hold),
extension-aware: code fences and inline code everywhere; HTML ``<script>`` /
``<style>`` / ``<pre>`` / ``<code>`` / comments / tags for HTML and Vue; LaTeX
math, environments, ``tikzpicture`` and ``%`` comments for ``.tex``; KaTeX ``$...$``
for markdown and decks. It then runs the voice checks on what remains.

Checks: AI slop and the forced ``X, not Y`` / ``not X, it is Y`` antithesis
(advisory review); plus two RECORDED FORKS demoted to advisory 2026-07-09 (Phase
I1) - F34 punctuation (semicolons / em- / en-dashes; his stated preference, NOT
corpus-derived) and F33 orthography (British/American; the corpus is mixed).
Gnomic subtitles are too context-bound to catch mechanically - the report ends
with a manual-review reminder instead of a noisy guess.

Exit contract: 2 on an unreadable target (operational failure, never a silent
pass); 0 on a completed run (flagging slop is the skill working). ``--strict``
exits 1 only on NON-fork flags - the F33/F34 advisory forks never hard-fail a
gating caller such as ``talk_ledger`` (his own papers legitimately mix spellings
and use semicolons).

Usage:
    python lint_voice.py <file-or-dir> [--strict] [--json]
"""

from __future__ import annotations

import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# Region masking - blank everything that is not prose, length-preserving.
# ---------------------------------------------------------------------------

_TEXT_EXTS = {".md", ".markdown", ".html", ".htm", ".vue", ".tex", ".txt", ".mdx"}


def _blank(m: "re.Match[str]") -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


# Always blanked, any medium: fenced + inline code.
_FENCE = re.compile(r"```.*?```", re.DOTALL)
_FENCE_TILDE = re.compile(r"~~~.*?~~~", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")

# HTML/Vue/markdown-with-html regions.
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_SCRIPT = re.compile(r"<script\b.*?</script>", re.DOTALL | re.IGNORECASE)
_STYLE = re.compile(r"<style\b.*?</style>", re.DOTALL | re.IGNORECASE)
_PRE = re.compile(r"<pre\b.*?</pre>", re.DOTALL | re.IGNORECASE)
_CODE_TAG = re.compile(r"<code\b.*?</code>", re.DOTALL | re.IGNORECASE)
_HTML_TAG = re.compile(r"<[^>\n]+>")
_FRONTMATTER = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)  # Slidev/Jekyll YAML

# Math: KaTeX in decks/markdown, full LaTeX in .tex.
_DISPLAY_MATH = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_INLINE_MATH = re.compile(r"(?<!\\)\$[^$\n]+\$")
_TEX_DISPLAY = re.compile(r"\\\[.*?\\\]", re.DOTALL)
_TEX_INLINE = re.compile(r"\\\([^\n]*?\\\)")
_MATH_ENV = re.compile(
    r"\\begin\{(equation|align|gather|multline|displaymath|eqnarray|flalign|tikzpicture)\*?\}"
    r".*?\\end\{\1\*?\}",
    re.DOTALL,
)
_TEX_COMMENT = re.compile(r"(?<!\\)%[^\n]*")
# Slidev / markdown per-slide frontmatter: a ``---`` separator, a block of yaml-ish
# directive lines (key:, #comment, - item, blank), then a closing ``---``. This is
# config between slides, not prose - blank it so ``layout: center`` and the slide
# separators themselves are never read as ``centre`` or em-dashes.
_SLIDEV_FM = re.compile(
    r"(?m)^---[ \t]*$\n"
    r"(?:[ \t]*(?:[\w.-]+[ \t]*:[^\n]*|#[^\n]*|-[ \t][^\n]*|)\n)+?"
    r"^---[ \t]*$"
)
# A standalone rule / Slidev separator line is dashes only - never an em-dash.
_HR_LINE = re.compile(r"^\s*-{3,}\s*$")
# HTML entities (&nbsp; &amp; &#8594; &#x2190;) carry a terminating ``;`` that is
# not a prose semicolon. Blank them so the Vonnegut check does not fire on markup.
_HTML_ENTITY = re.compile(r"&(?:#\d+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);")


def mask_regions(text: str, ext: str) -> str:
    """Blank the non-prose regions for the given file extension, preserving length
    (and therefore line numbers) by replacing each region with spaces."""
    # Frontmatter is config, not prose.
    text = _FRONTMATTER.sub(_blank, text)
    # Slidev / markdown per-slide frontmatter between slide separators.
    if ext in {".md", ".markdown", ".mdx"}:
        text = _SLIDEV_FM.sub(_blank, text)
    # Code, every medium.
    for pat in (_FENCE, _FENCE_TILDE):
        text = pat.sub(_blank, text)
    # Markdown and decks may embed HTML + KaTeX.
    if ext in {".html", ".htm", ".vue", ".md", ".markdown", ".mdx"}:
        for pat in (_HTML_COMMENT, _SCRIPT, _STYLE, _PRE, _CODE_TAG):
            text = pat.sub(_blank, text)
    if ext in {".md", ".markdown", ".mdx", ".vue", ".html", ".htm"}:
        text = _DISPLAY_MATH.sub(_blank, text)
    # LaTeX: math, environments, comments. Only .tex blanks ``%`` (a literal in
    # other media - blanking it there would eat the rest of a prose line).
    if ext == ".tex":
        text = _TEX_DISPLAY.sub(_blank, text)
        text = _MATH_ENV.sub(_blank, text)
        text = _DISPLAY_MATH.sub(_blank, text)
        text = _TEX_COMMENT.sub(_blank, text)
    # Inline code last among blocks, then inline math, then residual HTML tags.
    text = _INLINE_CODE.sub(_blank, text)
    if ext in {".md", ".markdown", ".mdx", ".vue", ".html", ".htm"}:
        text = _INLINE_MATH.sub(_blank, text)
    if ext == ".tex":
        text = _INLINE_MATH.sub(_blank, text)
        text = _TEX_INLINE.sub(_blank, text)
    if ext in {".html", ".htm", ".vue", ".md", ".markdown", ".mdx"}:
        text = _HTML_TAG.sub(_blank, text)
        text = _HTML_ENTITY.sub(_blank, text)
    return text


# ---------------------------------------------------------------------------
# The voice rules.
# ---------------------------------------------------------------------------

_AMERICANISMS = {
    r"\banalyze\b": "analyse", r"\banalyzed\b": "analysed", r"\banalyzing\b": "analysing",
    r"\bbehavior\b": "behaviour", r"\bbehaviors\b": "behaviours", r"\bbehavioral\b": "behavioural",
    r"\bcolor\b": "colour", r"\bcolors\b": "colours", r"\bcolored\b": "coloured",
    r"\bparameterize\b": "parametrise", r"\bparameterized\b": "parametrised",
    r"\bmodeling\b": "modelling", r"\bmodeled\b": "modelled",
    r"\boptimize\b": "optimise", r"\boptimized\b": "optimised", r"\boptimizing\b": "optimising",
    r"\borganize\b": "organise", r"\brecognize\b": "recognise", r"\bnormalize\b": "normalise",
    r"\bgeneralize\b": "generalise", r"\bvisualize\b": "visualise", r"\bsummarize\b": "summarise",
    r"\bminimize\b": "minimise", r"\bmaximize\b": "maximise", r"\bcharacterize\b": "characterise",
    r"\bcenter\b": "centre", r"\bcentered\b": "centred", r"\bfiber\b": "fibre",
    r"\bfavor\b": "favour", r"\bneighbor\b": "neighbour", r"\bneighbors\b": "neighbours",
    r"\bcatalog\b": "catalogue", r"\bgray\b": "grey", r"\bdefense\b": "defence",
    r"\blabeled\b": "labelled", r"\blabeling\b": "labelling", r"\btraveled\b": "travelled",
}

_AI_SLOP = {
    r"\bdelve\b": "delve", r"\btapestry\b": "tapestry", r"\btestament\b": "testament",
    r"\bcrucial\b": "crucial", r"\bnot merely\b": "not merely", r"\bbut rather\b": "but rather",
    r"\bin summary\b": "in summary", r"\bin conclusion\b": "in conclusion",
    r"\bit'?s worth noting\b": "it's worth noting",
    r"\b(?:it is|it'?s) important to note\b": "important to note",
    r"\bseamless(?:ly)?\b": "seamless", r"\bshowcase\b": "showcase",
    r"\bunderscore[sd]?\b": "underscore(s)", r"\bpivotal\b": "pivotal",
    r"\brich tapestry\b": "rich tapestry", r"\btreasure trove\b": "treasure trove",
    r"\bplays a (?:vital|key|crucial|pivotal) role\b": "plays a ... role",
    r"\bat the end of the day\b": "at the end of the day",
    r"\bneedless to say\b": "needless to say",
    r"\bnavigate the (?:complex )?landscape\b": "navigate the landscape",
}

# The forced antithesis: kept conservative, flagged for review (intent matters).
_ANTITHESIS = [
    r"\bnot\s+[a-z]+(?:\s+[a-z]+){0,3},\s+(?:but|it'?s|it\s+is|they'?re|they\s+are)\b",
    r"\b(?:isn'?t|aren'?t|is\s+not|are\s+not)\s+[a-z]+(?:\s+[a-z]+){0,3},\s+(?:it'?s|they'?re|it\s+is)\b",
]

_EM_DASH = "—"
_EN_DASH = "–"

# 2026-07-09 (Phase I1) recalibration. Two classes are RECORDED FORKS, not hard
# rules, and are advisory-only - they must not hard-fail even under --strict:
#   * F34 punctuation - his STATED preference (spaced hyphen; no semicolons /
#     em- / en-dashes). The corpus USES semicolons + spaced en-dashes, so this is
#     a stated editorial override, NOT a corpus derivation.
#   * F33 orthography - British/American is MIXED across the corpus and within a
#     single file, so British-only is not corpus-derived; his own papers fail it.
# (The weld voice floor, schema.VOICE_FAILURE_PATTERNS['surface-invariant'], keeps
# the punctuation surface ENFORCED on freshly generated prose; this general linter
# no longer hard-fails his own historical practice.)
_KIND_PUNCT_FORK = "Punctuation F34 (advisory)"
_KIND_ORTHO_FORK = "Orthography F33 (advisory)"
_FORK_KINDS = frozenset({_KIND_PUNCT_FORK, _KIND_ORTHO_FORK})


def _check_line(ln: int, line: str) -> list[dict]:
    flags = []

    def add(kind, msg):
        flags.append({"line": ln, "kind": kind, "message": msg})

    if _EM_DASH in line:
        add(_KIND_PUNCT_FORK, "Em-dash - his stated preference is a spaced hyphen ( - ) (advisory).")
    if _EN_DASH in line and not re.search(r"\d\s*" + _EN_DASH + r"\s*\d", line):
        add(_KIND_PUNCT_FORK, "En-dash - his stated preference is a spaced hyphen ( - ) (advisory).")
    if "---" in line and not _HR_LINE.match(line):
        add(_KIND_PUNCT_FORK, "Triple-hyphen (em-dash) - his stated preference is a spaced hyphen ( - ) (advisory).")
    if ";" in line:
        add(_KIND_PUNCT_FORK, "Semicolon - his stated preference is a spaced hyphen ( - ); the corpus uses semicolons (advisory).")
    for pat, repl in _AMERICANISMS.items():
        if re.search(pat, line, re.IGNORECASE):
            add(_KIND_ORTHO_FORK, f"Found `{pat.strip(chr(92)+'b')}` - British/American is a recorded fork; corpus is mixed (advisory, not corrected).")
    for pat, label in _AI_SLOP.items():
        if re.search(pat, line, re.IGNORECASE):
            add("AI slop", f"Found `{label}` - eradicate filler.")
    for pat in _ANTITHESIS:
        if re.search(pat, line, re.IGNORECASE):
            add("Antithesis - review", "Possible forced `X, not Y` antithesis - state the claim directly.")
    return flags


def lint_text(text: str, ext: str) -> list[dict]:
    masked = mask_regions(text, ext)
    flags = []
    for i, line in enumerate(masked.split("\n"), start=1):
        flags.extend(_check_line(i, line))
    # Dedupe identical (line, kind, message) - two antithesis patterns can match
    # the same clause, and a repeated token on a line need only be reported once.
    seen, deduped = set(), []
    for f in flags:
        key = (f["line"], f["kind"], f["message"])
        if key not in seen:
            seen.add(key)
            deduped.append(f)
    return deduped


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="utf-16") as fh:
            return fh.read()


def _iter_targets(target: str):
    if os.path.isfile(target):
        yield target
        return
    skip = {".git", "node_modules", "dist", ".venv", "__pycache__", "build"}
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in skip]
        for f in sorted(files):
            if os.path.splitext(f)[1].lower() in _TEXT_EXTS:
                yield os.path.join(root, f)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    strict = "--strict" in argv
    as_json = "--json" in argv
    if not args:
        print("Usage: python lint_voice.py <file-or-dir> [--strict] [--json]", file=sys.stderr)
        return 2
    target = args[0]
    if not os.path.exists(target):
        print(f"Error: {target} does not exist.", file=sys.stderr)
        return 2

    results = {}
    total = 0
    for path in _iter_targets(target):
        try:
            text = _read(path)
        except (OSError, UnicodeError) as e:
            print(f"Error: cannot read {path}: {e}", file=sys.stderr)
            return 2
        ext = os.path.splitext(path)[1].lower()
        flags = lint_text(text, ext)
        if flags:
            results[path] = flags
            total += len(flags)

    if as_json:
        print(json.dumps({"total": total, "files": results}, indent=2))
    else:
        print("# Voice Linter Report")
        print("*" * 50)
        if not total:
            print("PASS: no voice violations detected in prose regions.")
        else:
            for path, flags in results.items():
                print(f"\n## {path}  ({len(flags)} flag(s))")
                for fl in flags:
                    print(f"- **Line {fl['line']}** [{fl['kind']}]: {fl['message']}")
            print(f"\nVOICE: {total} flag(s) across {len(results)} file(s).")
            print(
                "\n*Manual check (not mechanised):* gnomic subtitles - a portentous "
                "fragment under a title, or a line narrating what a figure already shows. "
                "A title is a title; a visual needs no caption restating it."
            )
    # --strict fails only on NON-fork flags. F33 orthography and F34 punctuation
    # are recorded advisory forks and must not hard-fail a gating caller (his own
    # papers legitimately mix spellings and use semicolons).
    strict_total = sum(1 for flags in results.values()
                       for f in flags if f["kind"] not in _FORK_KINDS)
    return 1 if (strict and strict_total) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
