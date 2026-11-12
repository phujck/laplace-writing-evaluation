"""Mechanical pre-filter for the blind read (canon://skills/blind_reader).

This is NOT the oracle. The oracle is a context-starved subagent that reads the
rendered artifact and reports where it stops being able to follow. This script is a
cheap, high-precision pre-pass that catches two things a machine can flag without
understanding meaning, so the human reader's attention lands on the rest:

1. **Leaked operational / meta-prose.** An instruction to the drafter, or a note
   about the writing, that was rendered into the manuscript as a sentence. The case
   that forged the skill: the abstract literally read "we are explicit about what is
   new here" - an operational instruction, not a result. High-precision phrase list.

2. **Define-before-use census.** For a supplied glossary of specialist terms, the
   line where each term first appears versus the first line that *grounds* it (a
   definition cue, or a citation on the same line). A term used before it is grounded
   is a candidate "undefined on first use" - the failure two referees hit on every
   term in the operatorial-loss abstract.

Non-prose regions (math, environments, comments, inline code) are masked
length-preserving so line numbers hold and a `%` comment or `$...$` is never read as
prose. The .tex masking mirrors ``voice_linter``'s.

The script flags candidates; the subagent adjudicates. It can prove a term appears
before its citation. It cannot judge whether the prose around it makes the idea land.

Exit contract: 2 on an unreadable target (operational failure, never a silent pass);
0 on a completed run (flagging is the skill working); 1 under ``--strict`` when any
flag is found, for a gating caller.

Usage:
    python blind_read.py <file-or-dir> [--terms a,b,c] [--glossary path]
                                       [--window N] [--strict] [--json]

A glossary may also be supplied as a sidecar ``blind_terms.txt`` next to the target
(one term per line, ``#`` comments allowed). Without any glossary the census is
skipped and only the leaked-meta pass runs (with a note).
"""

from __future__ import annotations

import json
import os
import re
import sys

_TEXT_EXTS = {".tex", ".md", ".markdown", ".mdx", ".txt"}


# ---------------------------------------------------------------------------
# Region masking - blank non-prose, length-preserving (line numbers hold).
# ---------------------------------------------------------------------------

def _blank(m: "re.Match[str]") -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_TEX_DISPLAY = re.compile(r"\\\[.*?\\\]", re.DOTALL)
_TEX_INLINE = re.compile(r"\\\([^\n]*?\\\)")
_DISPLAY_MATH = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_INLINE_MATH = re.compile(r"(?<!\\)\$[^$\n]+\$")
_MATH_ENV = re.compile(
    r"\\begin\{(equation|align|gather|multline|displaymath|eqnarray|flalign|tikzpicture)\*?\}"
    r".*?\\end\{\1\*?\}",
    re.DOTALL,
)
_TEX_COMMENT = re.compile(r"(?<!\\)%[^\n]*")


def mask_regions(text: str, ext: str) -> str:
    """Blank non-prose regions for the extension, preserving length."""
    text = _FENCE.sub(_blank, text)
    if ext == ".tex":
        text = _TEX_DISPLAY.sub(_blank, text)
        text = _MATH_ENV.sub(_blank, text)
        text = _DISPLAY_MATH.sub(_blank, text)
        text = _TEX_COMMENT.sub(_blank, text)
        text = _INLINE_MATH.sub(_blank, text)
        text = _TEX_INLINE.sub(_blank, text)
    else:
        text = _DISPLAY_MATH.sub(_blank, text)
        text = _INLINE_MATH.sub(_blank, text)
    text = _INLINE_CODE.sub(_blank, text)
    return text


# ---------------------------------------------------------------------------
# 1. Leaked operational / meta-prose.
# ---------------------------------------------------------------------------
# Phrases that are instructions to the drafter, or commentary on the writing,
# masquerading as content. Kept high-precision: each is a thing no author writes
# in a result sentence. ``message`` says why it is a leak.

_LEAKED_META = [
    (r"\bwe are (?:deliberately )?explicit about what(?:'s| is) new\b",
     "operational instruction ('be explicit about novelty') rendered as prose - state the contribution, do not narrate that you are stating it"),
    (r"\bas (?:requested|instructed|noted in the prompt)\b",
     "instruction-to-self leaked into the text"),
    (r"\bin this (?:section|paper|subsection) we will\b",
     "table-of-contents narration - say the thing, not that you are about to"),
    (r"\bthe (?:purpose|goal) of this section is to\b",
     "meta-narration of structure - lead with the content's motivation instead"),
    (r"\bas (?:mentioned|noted|stated) (?:above|earlier|previously),?\s+we\b",
     "back-reference narration - the reader does not need the scaffolding"),
    (r"\bnote that we (?:now|will|here)\b",
     "process narration - describe the object, not your act of describing it"),
    (r"\b(?:TODO|FIXME|XXX|placeholder|to be (?:filled|written|added))\b",
     "drafting placeholder left in the artifact"),
    (r"\bwe are (?:careful|deliberate|precise) (?:to|about|in)\b.*\bnovelty\b",
     "narrating editorial care rather than making the claim"),
]
_LEAKED_META = [(re.compile(p, re.IGNORECASE), msg) for p, msg in _LEAKED_META]


def _normalise_with_linemap(masked: str) -> tuple[str, list[int]]:
    """Collapse runs of whitespace (incl. newlines) to a single space, recording the
    source line of every character in the normalised stream. Prose wraps across source
    lines, so a meta-phrase must be matched across newlines, then reported at the line
    where it begins."""
    out: list[str] = []
    line_of: list[int] = []
    line = 1
    prev_ws = False
    for ch in masked:
        if ch == "\n":
            line += 1
            ws = True
        else:
            ws = ch.isspace()
        if ws:
            if not prev_ws:
                out.append(" ")
                line_of.append(line)
            prev_ws = True
        else:
            out.append(ch)
            line_of.append(line)
            prev_ws = False
    return "".join(out), line_of


def find_leaked_meta(masked: str) -> list[dict]:
    norm, line_of = _normalise_with_linemap(masked)
    flags = []
    for pat, msg in _LEAKED_META:
        for m in pat.finditer(norm):
            ln = line_of[m.start()] if m.start() < len(line_of) else 1
            flags.append({"line": ln, "kind": "leaked-meta", "message": msg})
    return flags


# ---------------------------------------------------------------------------
# 2. Define-before-use census.
# ---------------------------------------------------------------------------
# A term is "grounded" on a line when that line either cites or carries a
# definition cue near the term. Heuristic, conservative: we want to catch the
# blatant case (term used in the abstract, defined nowhere or only much later),
# not adjudicate prose quality.

_DEF_CUES = re.compile(
    r"\b(?:we define|is defined|defined (?:as|by|to be)|denote[sd]?|we (?:call|write|take)\b"
    r"|stands for|that is,|i\.e\.|namely|we mean by|is the\b|are the\b|is a\b|is simply\b"
    r"|refers? to|means? that)",
    re.IGNORECASE,
)
_CITE = re.compile(r"\\cite[a-zA-Z]*\{")


def _term_pattern(term: str) -> "re.Pattern[str]":
    # Word-ish boundaries, case-insensitive, internal whitespace flexible.
    parts = [re.escape(w) for w in term.split()]
    body = r"\s+".join(parts)
    return re.compile(r"(?<![\w-])" + body + r"(?![\w-])", re.IGNORECASE)


def census_terms(text_lines: list[str], masked_lines: list[str], terms: list[str],
                 window: int) -> list[dict]:
    """For each term: first prose use, and first line that grounds it.

    Citation grounding is read from the RAW line (``\\cite`` lives in the source,
    not the masked prose). Use and definition-cue are read from the MASKED prose so
    a term inside math or a comment is not counted.
    """
    flags = []
    for term in terms:
        pat = _term_pattern(term)
        first_use = None
        first_ground = None
        for i, (raw, masked) in enumerate(zip(text_lines, masked_lines), start=1):
            used_here = pat.search(masked) is not None
            if used_here and first_use is None:
                first_use = i
            # Grounded if, near this use, a definition cue (masked prose) or a
            # citation (raw line) appears.
            if used_here:
                if _CITE.search(raw) or _DEF_CUES.search(masked):
                    if first_ground is None:
                        first_ground = i
            if first_use is not None and first_ground is None:
                # look ahead within the window from first use for a grounding line
                pass
        if first_use is None:
            continue  # term never appears - not this document's problem
        if first_ground is None:
            flags.append({
                "line": first_use, "kind": "undefined-term", "term": term,
                "message": f"'{term}' is used (first at line {first_use}) and never grounded "
                           "by a definition cue or citation in this file",
            })
        elif first_ground > first_use + window:
            flags.append({
                "line": first_use, "kind": "use-before-define", "term": term,
                "message": f"'{term}' is used at line {first_use} but first grounded at line "
                           f"{first_ground} (> {window} lines later) - define it on first use",
            })
    return flags


# ---------------------------------------------------------------------------
# The reusable per-reader floor (the sealed-subagent organ's every-round pass).
# ---------------------------------------------------------------------------
# One composition point for the mechanical floor, shared by this CLI and the
# Phase-E reader suite (``laplace.pipeline.readers.sealed``): mask the text for the
# extension, run the leaked-meta pass, and — when a glossary is supplied — the
# define-before-use census. The suite applies this to each reader's own input
# slice (whole text / truncated skim-path / prose-only); the CLI applies it to a
# file. Returns the flat flag list both callers stamp with their own attribution.

def reader_floor(text: str, ext: str = ".tex", terms: "list[str] | None" = None,
                 window: int = 0) -> list[dict]:
    """The mechanical floor for a sealed reader: leaked-meta (always) + a
    define-before-use census (when ``terms`` are given). ``ext`` selects the mask
    (``.tex`` masks math/environments/comments; anything else masks only math and
    inline code). The returned flags are the same shape :func:`scan_file` emits —
    ``{line, kind, message, [term]}`` — sorted by (line, kind)."""
    masked = mask_regions(text, ext)
    flags = find_leaked_meta(masked)
    if terms:
        flags += census_terms(text.split("\n"), masked.split("\n"), terms, window)
    flags.sort(key=lambda f: (f["line"], f["kind"]))
    return flags


# ---------------------------------------------------------------------------
# Driver.
# ---------------------------------------------------------------------------

def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
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


def _load_terms(target: str, terms_arg: str | None, glossary_arg: str | None) -> list[str]:
    terms: list[str] = []
    if terms_arg:
        terms += [t.strip() for t in terms_arg.split(",") if t.strip()]
    path = glossary_arg
    if not path:
        base = target if os.path.isdir(target) else os.path.dirname(target)
        sidecar = os.path.join(base or ".", "blind_terms.txt")
        if os.path.isfile(sidecar):
            path = sidecar
    if path and os.path.isfile(path):
        for line in _read(path).splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                terms.append(line)
    # de-dup, preserve order
    seen, out = set(), []
    for t in terms:
        if t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out


def scan_file(path: str, terms: list[str], window: int) -> list[dict]:
    ext = os.path.splitext(path)[1].lower()
    return reader_floor(_read(path), ext, terms, window)


def main(argv: list[str]) -> int:
    pos = [a for a in argv if not a.startswith("--")]
    strict = "--strict" in argv
    as_json = "--json" in argv

    def _opt(name: str) -> str | None:
        for a in argv:
            if a.startswith(name + "="):
                return a.split("=", 1)[1]
        if name in argv:
            i = argv.index(name)
            if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
                return argv[i + 1]
        return None

    if not pos:
        print("Usage: python blind_read.py <file-or-dir> [--terms a,b,c] "
              "[--glossary path] [--window N] [--strict] [--json]", file=sys.stderr)
        return 2
    target = pos[0]
    if not os.path.exists(target):
        print(f"Error: {target} does not exist.", file=sys.stderr)
        return 2
    window = int(_opt("--window") or 0)
    terms = _load_terms(target, _opt("--terms"), _opt("--glossary"))

    results, total = {}, 0
    for path in _iter_targets(target):
        try:
            flags = scan_file(path, terms, window)
        except (OSError, UnicodeError) as e:
            print(f"Error: cannot read {path}: {e}", file=sys.stderr)
            return 2
        if flags:
            results[path] = flags
            total += len(flags)

    if as_json:
        print(json.dumps({"total": total, "terms": terms, "files": results}, indent=2))
        return 1 if (strict and total) else 0

    print("# Blind-Read Pre-Filter (NOT the read - run the context-starved reader next)")
    print("*" * 60)
    if not terms:
        print("Note: no glossary supplied - census skipped, leaked-meta pass only.")
        print("      Pass --terms or add blind_terms.txt for the define-before-use census.")
    if not total:
        print("PASS (pre-filter): no leaked meta-prose, no ungrounded glossary terms.")
        print("This is NOT a clean bill - the oracle is the context-starved reader.")
    else:
        for path, flags in results.items():
            print(f"\n## {path}  ({len(flags)} flag(s))")
            for fl in flags:
                tag = f" [{fl['term']}]" if "term" in fl else ""
                print(f"- **Line {fl['line']}** [{fl['kind']}]{tag}: {fl['message']}")
        print(f"\nPRE-FILTER: {total} candidate(s) across {len(results)} file(s).")
        print("Now run the blind read: a subagent that reads the rendered artifact and "
              "nothing else (no laplace_orient, no canon, no substrate).")
    return 1 if (strict and total) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
