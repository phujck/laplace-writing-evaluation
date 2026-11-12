#!/usr/bin/env python3
"""rotate_handoff.py — keep HANDOFF.md under the tool read ceiling.

The defect this fixes (corpus_friction/laplace_engine.jsonl, RW-...-400003):
HANDOFF.md is the live entry point read by the wake fallback, but it grows
every close and eventually crosses the ~256KB tool read ceiling — at which
point the agent that most needs it cannot read it whole.

The mechanism: HANDOFF.md's body (after the preamble) is a sequence of
"## "-headed sections. The newest ones are session-log sections and
accumulate at the TOP as a contiguous block, newest first. Below that
block sits a fixed tail of standing/reference sections (older legacy
history + the always-relevant "spirit"/"handoff discipline" material) that
this tool never touches.

Three header idioms mark a session-log section, all equivalent here:
  - "## ⟶ ..." — the session handed forward (NEXT SESSION AIM, PRIOR AIM).
  - "## ⟵ ..." — the session handed back, written at recent closes
    (PRIOR AIM, ADDENDUM).
  - a bare label from that same vocabulary, for headers written with the
    glyph dropped.
A fourth header form, "## superseded <date> ↓ (..., kept verbatim)", is a
marker rather than a section: it annotates whatever sits below it. A bare
marker line is folded into the following section's byte span, so a rotation
cut can never land between a marker and the section it describes.

Rotation keeps the newest arrow sections that fit under a byte budget and
moves the older (bottom of the arrow block) sections VERBATIM into a dated
archive file under archive/handoffs/, leaving a pointer section behind.
Nothing is ever deleted — rotation is a move with a pointer, and the move
is verified byte-identical before HANDOFF.md is touched.

Safety properties (see tests/test_rotate_handoff.py):
  - --dry-run prints the plan and writes nothing.
  - Refuses to run (raises GrammarError, exit code 2) if HANDOFF.md's
    structure doesn't match the expected section grammar, rather than
    guessing and mangling the live entry point.
  - Writes the archive file BEFORE truncating HANDOFF.md, and verifies the
    archived bytes are byte-identical to what was read out of HANDOFF.md
    before ever touching the source file. Both writes are atomic
    (write to a .tmp path, then os.replace).
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

# The documented tool read ceiling (corpus_friction RW-...-400003 says
# HANDOFF.md at 267.7KB is over the ~256KB ceiling). The default rotation
# target is *computed* off that ceiling with headroom, not a bare literal:
# comfortably under 200KB means enough slack for a session or two of
# growth before the next rotation is needed.
READ_CEILING_BYTES = 256 * 1024
DEFAULT_TARGET_BYTES = int(READ_CEILING_BYTES * 0.7)  # ~179.2KB

HEADER_RE = re.compile(rb"(?m)^## (?!#)")
# Both arrows mark a session-log section. ⟶ is the older idiom (the session
# handed forward); ⟵ appears on sections written at recent closes as already
# handed back ("⟵ PRIOR AIM", "⟵ ADDENDUM"). Rotation treats them alike.
ARROW_PREFIXES = ("## ⟶", "## ⟵")
POINTER_HEADER = "## ROLLED SESSIONS (older history)"
DATE_RE = re.compile(r"(20\d{2}-\d{2}-\d{2})")

# One real anomaly found auditing the live HANDOFF.md while building this tool:
# "## NEXT SESSION AIM (2026-07-02, FORTY-SIXTH session ...)" is missing its ⟶
# glyph (a one-character slip from a past close), sitting positionally inside
# the otherwise-contiguous session block. Rather than refuse rotation over a
# single dropped glyph on an otherwise-unambiguous session-log header, treat
# the same fixed label vocabulary the arrow sections themselves use as an
# equivalent match. This is intentionally narrow — it does NOT match the
# legacy tail headers ("The spirit...", "DONE (...)", "The live agenda...",
# etc.), which use none of these labels, so contiguity checking still catches
# genuine structural breaks.
_FALLBACK_LABEL_RE = re.compile(
    r"^## (NEXT SESSION AIM|PRIOR AIM|PREVIOUS AIM|PARALLEL AIM|CARRIED FROM"
    r"|PRIOR MAIN TRACK|ADDENDUM)\b"
)

# "## superseded 2026-08-03 ↓ (2026-08-01, kept verbatim)" and friends. The
# glyph varies (↓, ⇓) and the date is sometimes absent, so the marker is
# recognised by its opening word alone.
_SUPERSEDED_MARKER_RE = re.compile(r"^## superseded\b", re.IGNORECASE)


def _is_session_header(header: str) -> bool:
    """True when a '## ' header names a session-log section."""
    return header.startswith(ARROW_PREFIXES) or bool(_FALLBACK_LABEL_RE.match(header))


class GrammarError(RuntimeError):
    """Raised when HANDOFF.md's structure doesn't match the expected grammar.

    Refusing beats guessing: a mangled live entry point is worse than a
    rotation that didn't happen tonight.
    """


@dataclass
class Section:
    start: int
    end: int
    header: str
    is_arrow: bool
    is_pointer: bool
    date: Optional[str]
    # True when this section's byte span opens with a "## superseded ..."
    # marker line — either one folded in ahead of `header`, or `header` itself.
    has_marker: bool = False

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclass
class ParsedHandoff:
    raw: bytes
    preamble_end: int
    sections: List[Section]

    @property
    def preamble(self) -> bytes:
        return self.raw[: self.preamble_end]

    @property
    def arrow_sections(self) -> List[Section]:
        return [s for s in self.sections if s.is_arrow]

    @property
    def tail_sections(self) -> List[Section]:
        return [s for s in self.sections if not s.is_arrow]


@dataclass
class Plan:
    kept: List[Section]
    rolled: List[Section]
    tail: List[Section]
    preamble_end: int
    tail_start: int
    total_before: int
    kept_bytes: int
    tail_bytes: int
    pointer_bytes: int
    archive_path: Path
    archive_body_size: int
    existing_pointer: Optional[Section]

    @property
    def total_after(self) -> int:
        return self.kept_bytes + self.pointer_bytes + self.tail_bytes


def _extract_date(header: str) -> Optional[str]:
    m = DATE_RE.search(header)
    return m.group(1) if m else None


def parse_handoff(raw: bytes) -> ParsedHandoff:
    matches = list(HEADER_RE.finditer(raw))
    if not matches:
        raise GrammarError("no '## ' section headers found — nothing to rotate")

    preamble_end = matches[0].start()
    if preamble_end == 0:
        raise GrammarError(
            "no preamble before the first '## ' section — expected a live-entry-point "
            "header/intro block first"
        )

    spans = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        eol = raw.find(b"\n", start)
        header_end = eol if eol != -1 else end
        header = raw[start:header_end].decode("utf-8")
        body = raw[header_end:end]
        spans.append((start, end, header, body))

    sections: List[Section] = []
    marker_start: Optional[int] = None
    for start, end, header, body in spans:
        is_marker = bool(_SUPERSEDED_MARKER_RE.match(header))
        if is_marker and not body.strip():
            # A marker line with no body of its own annotates the section
            # below it ("kept verbatim"). Hold its offset and hand it to that
            # section, so the two roll together or stay together. Consecutive
            # markers all fold into the same following section.
            if marker_start is None:
                marker_start = start
            continue
        if marker_start is not None:
            start = marker_start
            marker_start = None
            has_marker = True
        else:
            has_marker = False
        # A marker that carries its own body already heads the text it
        # describes; it is a session-log member in its own right.
        is_arrow = is_marker or _is_session_header(header)
        sections.append(
            Section(
                start,
                end,
                header,
                is_arrow,
                header.startswith(POINTER_HEADER),
                _extract_date(header),
                has_marker or is_marker,
            )
        )

    if marker_start is not None:
        # Markers run to the end of the file with no section under them —
        # nothing to fold into. Keep the bytes as a section of their own so
        # rotation never drops them, and let validate_grammar judge the shape.
        _, last_end, last_header, _ = spans[-1]
        sections.append(
            Section(
                marker_start,
                last_end,
                last_header,
                True,
                False,
                _extract_date(last_header),
                True,
            )
        )

    return ParsedHandoff(raw=raw, preamble_end=preamble_end, sections=sections)


def validate_grammar(parsed: ParsedHandoff) -> None:
    sections = parsed.sections
    if not sections:
        raise GrammarError("no sections parsed")

    if not sections[0].is_arrow:
        raise GrammarError(
            "expected the first section after the preamble to be a session-log "
            f"section ({' or '.join(ARROW_PREFIXES)} ...); "
            f"found: {sections[0].header!r}"
        )

    seen_non_arrow = False
    for s in sections:
        if s.is_arrow:
            if seen_non_arrow:
                raise GrammarError(
                    "session-log sections must form a contiguous block at "
                    f"the top; found a session section after a non-session one: {s.header!r}"
                )
        else:
            seen_non_arrow = True

    for s in sections:
        if s.size <= 0:
            raise GrammarError(f"degenerate zero/negative-length section: {s.header!r}")

    # sanity: preamble should look like the live entry point, not noise
    preamble_text = parsed.preamble.decode("utf-8", errors="replace")
    if not re.search(r"(?m)^# ", preamble_text):
        raise GrammarError(
            "preamble does not contain a top-level '# ' title — doesn't look like "
            "HANDOFF.md's expected header block"
        )


def compute_plan(
    parsed: ParsedHandoff,
    target_bytes: int,
    archive_dir: Path,
    min_keep: int = 1,
    now: Optional[datetime] = None,
) -> Plan:
    arrow = parsed.arrow_sections
    tail = parsed.tail_sections
    tail_start = tail[0].start if tail else (arrow[-1].end if arrow else parsed.preamble_end)
    tail_bytes = len(parsed.raw) - tail_start

    existing_pointer = tail[0] if tail and tail[0].is_pointer else None

    # Existing pointer section (if any) is logically part of the "fixed tail"
    # for byte-budget purposes but we may rewrite its first bytes to add a
    # bullet; treat its bytes as fixed overhead like the rest of the tail.
    fixed_bytes = parsed.preamble_end + tail_bytes

    kept: List[Section] = []
    cum = 0
    budget = max(target_bytes - fixed_bytes, 0)
    for s in arrow:
        if len(kept) < min_keep or cum + s.size <= budget:
            kept.append(s)
            cum += s.size
        else:
            break

    rolled = arrow[len(kept) :]

    if rolled:
        newest_date = next((s.date for s in rolled if s.date), None)
        oldest_date = next((s.date for s in reversed(rolled) if s.date), None)
        newest_date = newest_date or "undated"
        oldest_date = oldest_date or "undated"
        archive_path = archive_dir / f"HANDOFF_ROLLED_{oldest_date}_{newest_date}.md"
    else:
        archive_path = archive_dir / "HANDOFF_ROLLED_none.md"

    if existing_pointer is not None:
        pointer_bytes_estimate = existing_pointer.size + _new_bullet_len(archive_path)
    else:
        pointer_bytes_estimate = len(_render_new_pointer_section(archive_path)) if rolled else 0

    archive_body_size = rolled[-1].end - rolled[0].start if rolled else 0

    return Plan(
        kept=kept,
        rolled=rolled,
        tail=tail,
        preamble_end=parsed.preamble_end,
        tail_start=tail_start,
        total_before=len(parsed.raw),
        kept_bytes=sum(s.size for s in kept),
        tail_bytes=tail_bytes,
        pointer_bytes=pointer_bytes_estimate,
        archive_path=archive_path,
        archive_body_size=archive_body_size,
        existing_pointer=existing_pointer,
    )


def _new_bullet_line(archive_path: Path) -> str:
    rel = archive_path.as_posix()
    return (
        f"- older sessions rolled to `{rel}`; the conceptric atomises them — "
        "reconstruct, don't read.\n"
    )


def _new_bullet_len(archive_path: Path) -> int:
    return len(_new_bullet_line(archive_path).encode("utf-8"))


def _render_new_pointer_section(archive_path: Path) -> bytes:
    text = f"{POINTER_HEADER}\n" + _new_bullet_line(archive_path) + "\n"
    return text.encode("utf-8")


def _render_archive_banner(archive_path: Path, rolled: List[Section], now: datetime) -> bytes:
    first_line = rolled[0].header
    last_line = rolled[-1].header
    banner = (
        "<!-- rotate_handoff.py archive — verbatim content follows BEGIN VERBATIM; "
        "do not hand-edit below that marker -->\n"
        f"<!-- source: HANDOFF.md, {len(rolled)} section(s), rotated "
        f"{now.isoformat()} -->\n"
        f"<!-- newest rolled section: {first_line} -->\n"
        f"<!-- oldest rolled section: {last_line} -->\n"
        "<!-- BEGIN VERBATIM -->\n"
    )
    return banner.encode("utf-8")


BEGIN_MARKER = b"<!-- BEGIN VERBATIM -->\n"


def apply_plan(parsed: ParsedHandoff, plan: Plan, dry_run: bool, now: Optional[datetime] = None) -> None:
    if not plan.rolled:
        return  # nothing to do — idempotent no-op

    now = now or datetime.now(timezone.utc)
    raw = parsed.raw
    rolled_bytes = raw[plan.rolled[0].start : plan.rolled[-1].end]

    banner = _render_archive_banner(plan.archive_path, plan.rolled, now)
    archive_content = banner + rolled_bytes

    if dry_run:
        return

    plan.archive_path.parent.mkdir(parents=True, exist_ok=True)

    if plan.archive_path.exists():
        # extremely unlikely (rerun with identical rolled date bounds); make the
        # path unique rather than silently clobbering a prior archive.
        n = 2
        base = plan.archive_path
        while plan.archive_path.exists():
            plan.archive_path = base.with_name(base.stem + f"_{n}" + base.suffix)
            n += 1

    tmp_archive = plan.archive_path.with_suffix(plan.archive_path.suffix + ".tmp")
    tmp_archive.write_bytes(archive_content)

    # Verify byte-identity BEFORE touching HANDOFF.md.
    written = tmp_archive.read_bytes()
    idx = written.find(BEGIN_MARKER)
    if idx == -1:
        tmp_archive.unlink(missing_ok=True)
        raise RuntimeError("archive verification failed: BEGIN VERBATIM marker missing after write")
    moved_back = written[idx + len(BEGIN_MARKER) :]
    if moved_back != rolled_bytes:
        tmp_archive.unlink(missing_ok=True)
        raise RuntimeError(
            "archive verification failed: moved content is not byte-identical to the "
            "original HANDOFF.md sections — refusing to touch HANDOFF.md"
        )

    tmp_archive.replace(plan.archive_path)

    # Build the new HANDOFF.md content.
    kept_bytes = raw[plan.preamble_end : plan.rolled[0].start]
    tail_bytes = raw[plan.tail_start :]

    if plan.existing_pointer is not None:
        # Merge: prepend a new bullet under the existing pointer header.
        p = plan.existing_pointer
        pointer_section_text = raw[p.start : p.end].decode("utf-8")
        header_line, _, rest = pointer_section_text.partition("\n")
        new_bullet = _new_bullet_line(plan.archive_path)
        merged = header_line + "\n" + new_bullet + rest
        # tail_bytes currently starts at the pointer section; replace just
        # that section, keep everything after it untouched.
        after_pointer = raw[p.end :]
        new_tail = merged.encode("utf-8") + after_pointer
        new_content = raw[: plan.preamble_end] + kept_bytes + new_tail
    else:
        pointer_section = _render_new_pointer_section(plan.archive_path)
        new_content = raw[: plan.preamble_end] + kept_bytes + pointer_section + tail_bytes

    handoff_path = parsed.__dict__.get("_source_path")
    assert handoff_path is not None, "internal: source path not attached to ParsedHandoff"
    tmp_handoff = handoff_path.with_suffix(handoff_path.suffix + ".tmp")
    tmp_handoff.write_bytes(new_content)
    tmp_handoff.replace(handoff_path)


def load(path: Path) -> ParsedHandoff:
    raw = path.read_bytes()
    parsed = parse_handoff(raw)
    parsed.__dict__["_source_path"] = path
    return parsed


def format_plan(plan: Plan, path: Path) -> str:
    lines = []
    lines.append(f"HANDOFF.md rotation plan for {path}")
    lines.append(f"  current size:        {plan.total_before:>9,} bytes")
    lines.append(f"  preamble:            {plan.preamble_end:>9,} bytes (untouched)")
    lines.append(f"  fixed tail:          {plan.tail_bytes:>9,} bytes, {len(plan.tail)} section(s) (untouched)")
    lines.append(f"  arrow sections kept: {len(plan.kept)} ({plan.kept_bytes:,} bytes)")
    lines.append(f"  arrow sections roll: {len(plan.rolled)} ({plan.archive_body_size:,} bytes)")
    if plan.rolled:
        lines.append(f"  archive target:      {plan.archive_path}")
        lines.append(f"  pointer added:       ~{plan.pointer_bytes:,} bytes "
                      f"({'merged into existing' if plan.existing_pointer else 'new section'})")
        lines.append(f"  projected new size:  {plan.total_after:,} bytes "
                      f"(was {plan.total_before:,})")
        lines.append("")
        lines.append("  sections to roll (newest first):")
        for s in plan.rolled:
            head = s.header if len(s.header) <= 100 else s.header[:97] + "..."
            lines.append(f"    [{s.size:>7,}B] {head}")
    else:
        lines.append("  nothing to roll — HANDOFF.md already fits the target; no-op.")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Rotate old dated session sections out of HANDOFF.md into a verbatim "
            "dated archive, keeping the live entry point under the tool read "
            "ceiling. Nothing is ever deleted."
        )
    )
    p.add_argument(
        "--file",
        type=Path,
        default=Path("HANDOFF.md"),
        help="path to HANDOFF.md (default: ./HANDOFF.md)",
    )
    p.add_argument(
        "--archive-dir",
        type=Path,
        default=None,
        help=(
            "directory for rolled archives (default: <dir of --file>/archive/handoffs)"
        ),
    )
    p.add_argument(
        "--target-bytes",
        type=int,
        default=DEFAULT_TARGET_BYTES,
        help=(
            "byte budget for the rotated HANDOFF.md, computed off the documented "
            f"~{READ_CEILING_BYTES:,}-byte tool read ceiling with headroom "
            f"(default: {DEFAULT_TARGET_BYTES:,} bytes, ~70%% of the ceiling)"
        ),
    )
    p.add_argument(
        "--min-keep",
        type=int,
        default=1,
        help="always keep at least this many newest arrow sections regardless of budget (default: 1)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan without writing the archive or modifying HANDOFF.md",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_arg_parser().parse_args(argv)

    archive_dir = args.archive_dir or (args.file.resolve().parent / "archive" / "handoffs")

    try:
        parsed = load(args.file)
        validate_grammar(parsed)
        plan = compute_plan(parsed, args.target_bytes, archive_dir, min_keep=args.min_keep)
    except GrammarError as e:
        print(f"refusing to rotate {args.file}: {e}", file=sys.stderr)
        return 2

    print(format_plan(plan, args.file))

    if args.dry_run:
        print("\n(dry run — nothing written)")
        return 0

    apply_plan(parsed, plan, dry_run=False)
    if plan.rolled:
        print(f"\nrotated {len(plan.rolled)} section(s) to {plan.archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
