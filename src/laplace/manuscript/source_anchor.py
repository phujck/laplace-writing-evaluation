"""Content-stable source anchors — the ref grammar a builder stores instead of an offset.

THE DEFECT THIS KILLS. A conceptric node carries a ``ref`` into the prose that backs it.
The builders LOCATE that ref honestly (a needle is searched for, exactly one hit or a hard
failure) and then STORE the located LINE NUMBER. A line number is a property of the whole
file, not of the anchored content: insert one line anywhere above the anchor and every ref
below it changes, the emitted artefact's bytes change, and the byte-stability probe goes red
while nothing a reader would call the source has moved. One compiled overlay in this repo
broke that way twice in a single day (once at ``ef4b6f2f``, once on an insertion into
``OPEN_STACK.md``), which is what this module is the cure for. No project is named here on
purpose: the grammar is engine-level and the defect belongs to every builder that stores an
offset, not to whichever artefact happened to go red first.

THE CURE. The stored locator names the CONTENT, not the offset:

    <path>:<line>                 legacy — an offset (still parsed; drifts by construction)
    <path>:<line>-<line>          legacy span
    <path>:@<digest>              a content anchor: one line, keyed by its own text
    <path>:@<digest>+<n>          a content anchor spanning ``n`` lines

``<digest>`` is the first 12 hex characters of the SHA-256 of the anchored lines joined by
``\\n``. The line number is DERIVED at read time (``resolve`` / ``display``), never stored.
A pure line shift therefore leaves the stored bytes untouched; a change to the anchored text
changes them, which is what byte-stability should have meant all along.

The floor does NOT move. Minting an anchor still requires the content to be present and
UNIQUE in the file (``anchor`` verifies its own digest resolves to exactly one window), and
resolving one still fails loudly when the content is gone or has become ambiguous. What was a
located-then-typed ref becomes a located-and-stays-located ref.

    python3 -m laplace.manuscript.source_anchor 'OPEN_STACK.md:@1f4a…'    # -> OPEN_STACK.md:1381
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Sequence

#: the digest length: 12 hex chars of SHA-256. Short enough to read in a ledger essence,
#: long enough that a collision inside one file is not a thing that happens.
DIGEST_LEN = 12

_ANCHOR_RX = re.compile(r"^@(?P<digest>[0-9a-f]{%d})(?:\+(?P<span>\d+))?$" % DIGEST_LEN)
_LINE_RX = re.compile(r"^(?P<start>\d+)(?:-(?P<end>\d+))?$")
_REF_RX = re.compile(
    r"^(?P<path>.+?):(?P<locator>@[0-9a-f]{%d}(?:\+\d+)?|\d+(?:-\d+)?)$" % DIGEST_LEN)


class AnchorError(Exception):
    """A ref that does not parse, or an anchor whose content is gone or ambiguous."""


# ---------------------------------------------------------------------------
# minting
# ---------------------------------------------------------------------------

def digest(lines: Sequence[str]) -> str:
    """The content key of an anchored span: SHA-256 over the lines joined by newlines."""
    blob = "\n".join(lines).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:DIGEST_LEN]


def anchor(lines: Sequence[str], start: int, end: int | None = None) -> str:
    """The stored locator for ``lines[start-1:end]`` (1-indexed, inclusive).

    Verifies its own product: an anchor that would not resolve back to exactly this span is
    refused here rather than written into an artefact and discovered by a reader."""
    end = start if end is None else end
    if not (1 <= start <= end <= len(lines)):
        raise AnchorError(f"span {start}-{end} outside a {len(lines)}-line source")
    span = end - start + 1
    dig = digest(lines[start - 1:end])
    loc = f"@{dig}" if span == 1 else f"@{dig}+{span}"
    try:
        got = locate(lines, loc)
    except AnchorError as e:
        raise AnchorError(
            f"anchor for lines {start}-{end} is not unique in this source ({e}); anchor a "
            f"span that is") from None
    if got != (start, end):
        raise AnchorError(
            f"anchor for lines {start}-{end} resolves to {got[0]}-{got[1]} — the anchored "
            f"content is not unique in this source; anchor a span that is")
    return loc


# ---------------------------------------------------------------------------
# reading
# ---------------------------------------------------------------------------

def parse_ref(ref: str) -> tuple[str, str]:
    """``'<path>:<locator>'`` -> ``(path, locator)``; raises on anything else."""
    m = _REF_RX.match((ref or "").strip())
    if not m:
        raise AnchorError(
            f"ref {ref!r} is not '<path>:<line>[-<line>]' or '<path>:@<digest>[+<n>]'")
    return m.group("path"), m.group("locator")


def is_content_anchor(locator: str) -> bool:
    return bool(_ANCHOR_RX.match(locator))


def locate(lines: Sequence[str], locator: str) -> tuple[int, int]:
    """``(start, end)`` — 1-indexed, inclusive — for a locator against these lines.

    An offset locator is checked for existence only (that is all an offset can promise). A
    content anchor is SEARCHED FOR: missing content and ambiguous content both fail here."""
    m = _ANCHOR_RX.match(locator)
    if m:
        span = int(m.group("span") or 1)
        want = m.group("digest")
        hits = [i + 1 for i in range(len(lines) - span + 1)
                if digest(lines[i:i + span]) == want]
        if not hits:
            raise AnchorError(
                f"anchored content @{want} is no longer in this source ({span} line(s)) — "
                f"the text the ref names has changed, so the ref must be re-minted")
        if len(hits) > 1:
            raise AnchorError(f"anchored content @{want} is ambiguous (starts {hits})")
        return hits[0], hits[0] + span - 1
    m = _LINE_RX.match(locator)
    if not m:
        raise AnchorError(f"locator {locator!r} is neither an offset nor a content anchor")
    start = int(m.group("start"))
    end = int(m.group("end") or m.group("start"))
    if not (1 <= start <= end <= len(lines)):
        raise AnchorError(f"lines {start}-{end} fall outside a {len(lines)}-line source")
    return start, end


def read_lines(repo: Path, path: str) -> list[str]:
    p = repo / path
    if not p.is_file():
        raise AnchorError(f"ref names a missing file {path!r}")
    return p.read_text(encoding="utf-8").splitlines()


def resolve(ref: str, repo: Path) -> tuple[str, int, int]:
    """``(path, start, end)`` for a ref against the tree at ``repo``."""
    path, locator = parse_ref(ref)
    start, end = locate(read_lines(repo, path), locator)
    return path, start, end


def display(ref: str, repo: Path) -> str:
    """The human form: ``path:line`` / ``path:start-end``, derived at READ time."""
    path, start, end = resolve(ref, repo)
    return f"{path}:{start}" if start == end else f"{path}:{start}-{end}"


def _main(argv: list[str]) -> int:
    if not argv:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: python3 -m laplace.manuscript.source_anchor <ref> [<ref> ...]", file=sys.stderr)
        return 2
    repo = Path.cwd()
    rc = 0
    for ref in argv:
        try:
            print(display(ref, repo))
        except AnchorError as e:
            print(f"ANCHOR: {ref}: {e}", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
