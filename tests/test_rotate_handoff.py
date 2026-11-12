"""Unit tests for scripts/rotate_handoff.py — the HANDOFF.md rotation mechanism.

The defect (corpus_friction/laplace_engine.jsonl, RW-...-400003): HANDOFF.md grows
every close and crosses the ~256KB tool read ceiling, so the wake fallback can't
read it whole. rotate_handoff.py moves older dated session sections verbatim into
a dated archive, leaving a pointer, never deleting anything.

These tests run entirely against a synthetic mini-HANDOFF fixture built in
tmp_path — the real repo HANDOFF.md is read-only tonight (dry-run only, exercised
separately as a manual report, not as a destructive test).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_MOD_PATH = _REPO / "scripts" / "rotate_handoff.py"


def _load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = mod
    spec.loader.exec_module(mod)
    return mod


rh = _load(_MOD_PATH)


PREAMBLE = (
    "# Mini Handoff — handoff (live entry point)\n\n"
    "**Read this first.** Kept current.\n\n"
)


def _section(date: str, label: str, arrow: bool = True, body_lines: int = 30) -> str:
    header = f"## ⟶ NEXT SESSION AIM ({date} — {label})\n" if arrow else f"## {label} ({date})\n"
    body = "".join(f"some session narrative line {i} for {date} {label}\n" for i in range(body_lines))
    return header + body + "\n"


def _session_section(
    date: str,
    label: str,
    glyph: str = "⟶",
    kind: str = "NEXT SESSION AIM",
    body_lines: int = 30,
) -> str:
    """A session-log section in any of the three header idioms: ⟶-prefixed,
    ⟵-prefixed, or bare label (glyph dropped, glyph="")."""
    prefix = f"{glyph} " if glyph else ""
    header = f"## {prefix}{kind} ({date} — {label})\n"
    body = "".join(f"session narrative line {i} for {date} {label}\n" for i in range(body_lines))
    return header + body + "\n"


def _marker(superseded_by: str, kept: str, glyph: str = "↓") -> str:
    """A bare "## superseded ..." marker line — a header with no body, which
    annotates the section written below it."""
    return f"## superseded {superseded_by} {glyph} ({kept}, kept verbatim)\n\n"


def _tail() -> str:
    return (
        "## The spirit (how to work here)\n"
        "1. Build the smallest real thing, then look at it.\n"
        "2. Ask, don't assert.\n\n"
        "## Handoff discipline (standing)\n"
        "HANDOFF.md is the single live entry point.\n\n"
    )


def make_fixture(n_sections: int = 8, body_lines: int = 40) -> str:
    """A synthetic HANDOFF.md: preamble + n dated arrow sections (newest first,
    each large enough that rotation is forced well before all of them) + a fixed
    non-arrow tail."""
    sections = []
    # dates descending so section 0 is "newest"
    for i in range(n_sections):
        day = 20 - i  # 2026-07-20, 19, 18, ...
        date = f"2026-07-{day:02d}"
        sections.append(_section(date, f"session {n_sections - i}", body_lines=body_lines))
    return PREAMBLE + "".join(sections) + _tail()


@pytest.fixture()
def handoff_file(tmp_path: Path) -> Path:
    p = tmp_path / "HANDOFF.md"
    p.write_text(make_fixture(), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. Rotation math
# ---------------------------------------------------------------------------


def test_parses_expected_number_of_sections(handoff_file: Path):
    parsed = rh.load(handoff_file)
    rh.validate_grammar(parsed)
    assert len(parsed.arrow_sections) == 8
    assert len(parsed.tail_sections) == 2


def test_rotation_keeps_newest_and_rolls_oldest_contiguously(handoff_file: Path):
    parsed = rh.load(handoff_file)
    rh.validate_grammar(parsed)
    archive_dir = handoff_file.parent / "archive" / "handoffs"

    # Pick a target small enough that only some sections fit.
    total = len(parsed.raw)
    target = total - 3000  # force rolling roughly the oldest few sections
    plan = rh.compute_plan(parsed, target_bytes=target, archive_dir=archive_dir)

    assert len(plan.kept) + len(plan.rolled) == len(parsed.arrow_sections)
    assert len(plan.rolled) > 0, "test target should force at least one section to roll"
    # kept must be the newest (topmost) contiguous prefix
    assert plan.kept == parsed.arrow_sections[: len(plan.kept)]
    # rolled must be the oldest (bottommost) contiguous suffix
    assert plan.rolled == parsed.arrow_sections[len(plan.kept) :]
    # projected size should respect the budget plus the fixed tail/pointer overhead
    assert plan.total_after <= total


def test_min_keep_always_honored_even_under_tiny_budget(handoff_file: Path):
    parsed = rh.load(handoff_file)
    rh.validate_grammar(parsed)
    archive_dir = handoff_file.parent / "archive" / "handoffs"

    plan = rh.compute_plan(parsed, target_bytes=1, archive_dir=archive_dir, min_keep=2)
    assert len(plan.kept) == 2
    assert len(plan.rolled) == len(parsed.arrow_sections) - 2


def test_no_rotation_needed_when_already_under_budget(handoff_file: Path):
    parsed = rh.load(handoff_file)
    rh.validate_grammar(parsed)
    archive_dir = handoff_file.parent / "archive" / "handoffs"

    plan = rh.compute_plan(parsed, target_bytes=len(parsed.raw) + 1_000_000, archive_dir=archive_dir)
    assert plan.rolled == []
    assert plan.kept == parsed.arrow_sections


# ---------------------------------------------------------------------------
# 2. --dry-run writes nothing
# ---------------------------------------------------------------------------


def test_dry_run_writes_nothing(handoff_file: Path, capsys):
    original_bytes = handoff_file.read_bytes()
    archive_dir = handoff_file.parent / "archive" / "handoffs"

    rc = rh.main(
        [
            "--file",
            str(handoff_file),
            "--archive-dir",
            str(archive_dir),
            "--target-bytes",
            str(len(original_bytes) - 3000),
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry run" in out.lower()
    assert "sections to roll" in out.lower()

    # nothing written anywhere
    assert handoff_file.read_bytes() == original_bytes
    assert not archive_dir.exists()


# ---------------------------------------------------------------------------
# 3. Refusal on malformed structure
# ---------------------------------------------------------------------------


def test_refuses_when_arrow_section_follows_non_arrow(tmp_path: Path):
    bad = (
        PREAMBLE
        + _section("2026-07-20", "session A")
        + "## Standing note (not arrow)\nsome text\n\n"
        + _section("2026-07-19", "session B")  # arrow AFTER non-arrow: illegal
    )
    p = tmp_path / "HANDOFF.md"
    p.write_text(bad, encoding="utf-8")

    with pytest.raises(rh.GrammarError):
        parsed = rh.load(p)
        rh.validate_grammar(parsed)


def test_tolerates_known_label_missing_its_arrow_glyph(tmp_path: Path):
    """Real HANDOFF.md has exactly one header with the arrow glyph dropped:
    "## NEXT SESSION AIM (...)" instead of "## ⟶ NEXT SESSION AIM (...)",
    sitting inside the otherwise-contiguous arrow block. That's a one-glyph
    slip, not a structural break, so it must not trigger a refusal."""
    ok = (
        PREAMBLE
        + _section("2026-07-20", "session A")
        + "## NEXT SESSION AIM (2026-07-19 — session B, arrow glyph dropped)\nbody text here\n\n"
        + _section("2026-07-18", "session C")
        + _tail()
    )
    p = tmp_path / "HANDOFF.md"
    p.write_text(ok, encoding="utf-8")

    parsed = rh.load(p)
    rh.validate_grammar(parsed)  # must not raise
    assert len(parsed.arrow_sections) == 3
    assert len(parsed.tail_sections) == 2


def test_refuses_when_first_section_is_not_arrow(tmp_path: Path):
    bad = PREAMBLE + "## Some non-arrow heading (2026-07-20)\nbody\n\n"
    p = tmp_path / "HANDOFF.md"
    p.write_text(bad, encoding="utf-8")

    with pytest.raises(rh.GrammarError):
        parsed = rh.load(p)
        rh.validate_grammar(parsed)


def test_left_arrow_headers_are_session_sections(tmp_path: Path):
    """Recent closes write already-handed-back sections with ⟵ ("⟵ PRIOR AIM",
    "⟵ ADDENDUM"). They sit inside the session block between ⟶ sections, so the
    grammar must count them as members, not as the start of the fixed tail."""
    ok = (
        PREAMBLE
        + _session_section("2026-08-07", "latest")
        + _session_section("2026-08-05", "prior", glyph="⟵", kind="PRIOR AIM")
        + _session_section("2026-08-04", "addendum", glyph="⟵", kind="ADDENDUM")
        + _session_section("2026-08-03", "back to right arrow")
        + _tail()
    )
    p = tmp_path / "HANDOFF.md"
    p.write_text(ok, encoding="utf-8")

    parsed = rh.load(p)
    rh.validate_grammar(parsed)  # must not raise
    assert len(parsed.arrow_sections) == 4
    assert len(parsed.tail_sections) == 2


def test_bare_addendum_label_is_a_session_section(tmp_path: Path):
    """Same label vocabulary with the glyph dropped."""
    ok = (
        PREAMBLE
        + _session_section("2026-08-07", "latest")
        + _session_section("2026-08-05", "addendum", glyph="", kind="ADDENDUM")
        + _tail()
    )
    p = tmp_path / "HANDOFF.md"
    p.write_text(ok, encoding="utf-8")

    parsed = rh.load(p)
    rh.validate_grammar(parsed)
    assert len(parsed.arrow_sections) == 2


def test_superseded_marker_folds_into_the_section_below_it(tmp_path: Path):
    """A bare "## superseded ... (kept verbatim)" line describes the section
    under it. It must not parse as a section of its own — its bytes belong to
    the span of the section it introduces."""
    text = (
        PREAMBLE
        + _session_section("2026-08-07", "latest")
        + _marker("2026-08-05", "2026-08-04")
        + _session_section("2026-08-04", "the superseded one")
        + _tail()
    )
    p = tmp_path / "HANDOFF.md"
    p.write_text(text, encoding="utf-8")

    parsed = rh.load(p)
    rh.validate_grammar(parsed)

    assert len(parsed.arrow_sections) == 2, "the marker must not become a third section"
    marked = parsed.arrow_sections[1]
    assert marked.header.startswith("## ⟶ NEXT SESSION AIM (2026-08-04")
    assert marked.has_marker
    assert marked.date == "2026-08-04", "date comes from the real header, not the marker"

    # the marker line is the first thing in that section's byte span
    span = parsed.raw[marked.start : marked.end].decode("utf-8")
    assert span.startswith("## superseded 2026-08-05 ↓ (2026-08-04, kept verbatim)")


def test_consecutive_markers_fold_into_the_same_section(tmp_path: Path):
    text = (
        PREAMBLE
        + _session_section("2026-08-07", "latest")
        + _marker("2026-08-06", "2026-08-05")
        + _marker("same day", "2026-08-04 morning")
        + _session_section("2026-08-04", "the superseded one")
        + _tail()
    )
    p = tmp_path / "HANDOFF.md"
    p.write_text(text, encoding="utf-8")

    parsed = rh.load(p)
    rh.validate_grammar(parsed)
    assert len(parsed.arrow_sections) == 2
    span = parsed.raw[parsed.arrow_sections[1].start : parsed.arrow_sections[1].end].decode("utf-8")
    assert span.count("## superseded ") == 2
    assert span.index("## superseded 2026-08-06") < span.index("## superseded same day")


def test_superseded_marker_carrying_its_own_body_is_its_own_section(tmp_path: Path):
    """The other live shape: the marker heads the kept-verbatim text directly,
    with no separate session header under it. Then it is the section header,
    and it is a session-log member like its neighbours."""
    text = (
        PREAMBLE
        + _session_section("2026-08-07", "latest")
        + "## superseded same day ↓ (2026-08-07 morning block, kept verbatim)\n\n"
        + "the morning block's narrative, kept whole\nsecond line\n\n"
        + _session_section("2026-08-05", "older")
        + _tail()
    )
    p = tmp_path / "HANDOFF.md"
    p.write_text(text, encoding="utf-8")

    parsed = rh.load(p)
    rh.validate_grammar(parsed)

    assert len(parsed.arrow_sections) == 3
    marker_section = parsed.arrow_sections[1]
    assert marker_section.header.startswith("## superseded same day")
    span = parsed.raw[marker_section.start : marker_section.end].decode("utf-8")
    assert "the morning block's narrative, kept whole" in span
    assert "2026-08-05" not in span, "the marker must not swallow the section below it"


def test_sections_tile_the_file_with_no_lost_bytes(tmp_path: Path):
    """Marker folding rewrites span boundaries, so assert the sections still
    tile the body exactly: no gap, no overlap, nothing dropped."""
    text = (
        PREAMBLE
        + _session_section("2026-08-07", "latest")
        + _marker("2026-08-07", "2026-08-05")
        + _session_section("2026-08-05", "prior", glyph="⟵", kind="PRIOR AIM")
        + "## superseded same day ↓ (2026-08-05 morning, kept verbatim)\n\nbody kept whole\n\n"
        + _session_section("2026-08-04", "older")
        + _tail()
    )
    p = tmp_path / "HANDOFF.md"
    p.write_text(text, encoding="utf-8")

    parsed = rh.load(p)
    rh.validate_grammar(parsed)

    assert parsed.sections[0].start == parsed.preamble_end
    for a, b in zip(parsed.sections, parsed.sections[1:]):
        assert a.end == b.start, f"gap/overlap between {a.header!r} and {b.header!r}"
    assert parsed.sections[-1].end == len(parsed.raw)


def test_trailing_marker_with_nothing_below_it_keeps_its_bytes(tmp_path: Path):
    """Degenerate shape — a marker at the very end has no section to fold into.
    The bytes must still be owned by a section rather than silently dropped."""
    text = (
        PREAMBLE
        + _session_section("2026-08-07", "latest")
        + _marker("2026-08-07", "nothing follows")
    )
    p = tmp_path / "HANDOFF.md"
    p.write_text(text, encoding="utf-8")

    parsed = rh.load(p)
    assert parsed.sections[-1].end == len(parsed.raw)
    assert parsed.sections[-1].header.startswith("## superseded")


def test_refuses_when_no_preamble(tmp_path: Path):
    bad = "## ⟶ NEXT SESSION AIM (2026-07-20 — session A)\nbody\n\n"
    p = tmp_path / "HANDOFF.md"
    p.write_text(bad, encoding="utf-8")

    with pytest.raises(rh.GrammarError):
        parsed = rh.load(p)
        rh.validate_grammar(parsed)


@pytest.mark.parametrize(
    "tail_header",
    [
        "## The spirit (how to work here)",
        "## DONE (2026-06-02, prior session): v3 deck polish",
        "## The live agenda (2026-06-04)",
        "## Deferred decision",
    ],
)
def test_real_tail_headers_still_break_the_session_block(tmp_path: Path, tail_header: str):
    """Widening the grammar for ⟵ and superseded must not make it permissive.
    A genuine tail header with a session section under it is still structural
    corruption, and rotation still refuses rather than guessing the cut."""
    bad = (
        PREAMBLE
        + _session_section("2026-08-07", "latest")
        + tail_header
        + "\nsome standing text\n\n"
        + _session_section("2026-08-05", "session below the tail: illegal")
    )
    p = tmp_path / "HANDOFF.md"
    p.write_text(bad, encoding="utf-8")

    with pytest.raises(rh.GrammarError):
        parsed = rh.load(p)
        rh.validate_grammar(parsed)


def test_cli_refusal_exits_2_and_does_not_write(tmp_path: Path, capsys):
    bad = (
        PREAMBLE
        + _section("2026-07-20", "session A")
        + "## Standing note (not arrow)\nsome text\n\n"
        + _section("2026-07-19", "session B")
    )
    p = tmp_path / "HANDOFF.md"
    p.write_text(bad, encoding="utf-8")
    original = p.read_bytes()

    rc = rh.main(["--file", str(p), "--target-bytes", "10"])
    assert rc == 2
    assert p.read_bytes() == original
    err = capsys.readouterr().err
    assert "refusing to rotate" in err.lower()


# ---------------------------------------------------------------------------
# 4. Byte-identity of moved sections
# ---------------------------------------------------------------------------


def test_archived_content_is_byte_identical_to_original_sections(handoff_file: Path):
    original = handoff_file.read_bytes()
    parsed = rh.load(handoff_file)
    rh.validate_grammar(parsed)
    archive_dir = handoff_file.parent / "archive" / "handoffs"
    target = len(original) - 3000
    plan = rh.compute_plan(parsed, target_bytes=target, archive_dir=archive_dir)
    assert plan.rolled

    expected_rolled_bytes = original[plan.rolled[0].start : plan.rolled[-1].end]

    rh.apply_plan(parsed, plan, dry_run=False)

    archived = plan.archive_path.read_bytes()
    idx = archived.find(rh.BEGIN_MARKER)
    assert idx != -1
    moved_back = archived[idx + len(rh.BEGIN_MARKER) :]
    assert moved_back == expected_rolled_bytes


def test_verification_runs_before_handoff_is_truncated(handoff_file: Path, monkeypatch):
    """If the post-write verification would fail, HANDOFF.md must be untouched."""
    original = handoff_file.read_bytes()
    parsed = rh.load(handoff_file)
    rh.validate_grammar(parsed)
    archive_dir = handoff_file.parent / "archive" / "handoffs"
    plan = rh.compute_plan(parsed, target_bytes=len(original) - 3000, archive_dir=archive_dir)
    assert plan.rolled

    def _corrupting_banner(archive_path, rolled, now):
        # simulate a corrupted write: banner without the real marker semantics
        return b"<!-- corrupted, no real marker -->\n"

    monkeypatch.setattr(rh, "_render_archive_banner", _corrupting_banner)

    with pytest.raises(RuntimeError):
        rh.apply_plan(parsed, plan, dry_run=False)

    # HANDOFF.md must be exactly as before; a failed archive write must not
    # cascade into a truncated live entry point.
    assert handoff_file.read_bytes() == original


# ---------------------------------------------------------------------------
# 5. Pointer line present
# ---------------------------------------------------------------------------


def test_pointer_line_present_after_rotation(handoff_file: Path):
    parsed = rh.load(handoff_file)
    rh.validate_grammar(parsed)
    archive_dir = handoff_file.parent / "archive" / "handoffs"
    plan = rh.compute_plan(parsed, target_bytes=len(parsed.raw) - 3000, archive_dir=archive_dir)
    assert plan.rolled

    rh.apply_plan(parsed, plan, dry_run=False)

    new_content = handoff_file.read_text(encoding="utf-8")
    assert rh.POINTER_HEADER in new_content
    assert "the conceptric atomises them" in new_content
    assert "reconstruct, don't read" in new_content
    assert str(plan.archive_path.as_posix()) in new_content or plan.archive_path.name in new_content

    # nothing deleted: every rolled section's narrative text still exists
    # somewhere (in the archive), byte for byte.
    archived = plan.archive_path.read_text(encoding="utf-8")
    for s in plan.rolled:
        assert s.header.strip("# ").strip() in archived


# ---------------------------------------------------------------------------
# 6. The cut never separates a marker from the section it describes
# ---------------------------------------------------------------------------


MARKER_LINE = "## superseded 2026-08-06 ↓ (2026-08-05, kept verbatim)"


def _marked_fixture() -> str:
    """Four session sections; the third is introduced by a bare marker."""
    return (
        PREAMBLE
        + _session_section("2026-08-07", "s1")
        + _session_section("2026-08-06", "s2", glyph="⟵", kind="PRIOR AIM")
        + MARKER_LINE
        + "\n\n"
        + _session_section("2026-08-05", "s3")
        + _session_section("2026-08-04", "s4")
        + _tail()
    )


def test_cut_at_a_marker_rolls_the_marker_with_its_section(tmp_path: Path):
    """min_keep=2 puts the cut exactly at the marker boundary: the marked
    section is the first to roll, so the marker travels with it and no dangling
    marker is left behind in HANDOFF.md."""
    p = tmp_path / "HANDOFF.md"
    p.write_text(_marked_fixture(), encoding="utf-8")
    archive_dir = tmp_path / "archive" / "handoffs"

    parsed = rh.load(p)
    rh.validate_grammar(parsed)
    plan = rh.compute_plan(parsed, target_bytes=1, archive_dir=archive_dir, min_keep=2)
    assert len(plan.kept) == 2
    assert plan.rolled[0].date == "2026-08-05"

    rh.apply_plan(parsed, plan, dry_run=False)

    archived = plan.archive_path.read_text(encoding="utf-8")
    remaining = p.read_text(encoding="utf-8")
    assert MARKER_LINE in archived
    assert MARKER_LINE not in remaining, "marker left behind without its section"
    # marker immediately precedes the header it introduces, unchanged
    assert MARKER_LINE + "\n\n## ⟶ NEXT SESSION AIM (2026-08-05" in archived


def test_cut_below_a_marker_keeps_the_marker_with_its_section(tmp_path: Path):
    """The mirror case — min_keep=3 keeps the marked section, so the marker
    stays in HANDOFF.md and does not leak into the archive."""
    p = tmp_path / "HANDOFF.md"
    p.write_text(_marked_fixture(), encoding="utf-8")
    archive_dir = tmp_path / "archive" / "handoffs"

    parsed = rh.load(p)
    rh.validate_grammar(parsed)
    plan = rh.compute_plan(parsed, target_bytes=1, archive_dir=archive_dir, min_keep=3)
    assert len(plan.rolled) == 1

    rh.apply_plan(parsed, plan, dry_run=False)

    remaining = p.read_text(encoding="utf-8")
    archived = plan.archive_path.read_text(encoding="utf-8")
    assert MARKER_LINE in remaining
    assert MARKER_LINE not in archived
    assert MARKER_LINE + "\n\n## ⟶ NEXT SESSION AIM (2026-08-05" in remaining


def test_marked_fixture_rotation_loses_no_bytes(tmp_path: Path):
    """Preamble + kept + pointer + tail, plus the archived span, must account
    for every byte of the original apart from the pointer text rotation adds."""
    p = tmp_path / "HANDOFF.md"
    p.write_text(_marked_fixture(), encoding="utf-8")
    original = p.read_bytes()
    archive_dir = tmp_path / "archive" / "handoffs"

    parsed = rh.load(p)
    rh.validate_grammar(parsed)
    plan = rh.compute_plan(parsed, target_bytes=1, archive_dir=archive_dir, min_keep=2)
    rolled_span = original[plan.rolled[0].start : plan.rolled[-1].end]

    rh.apply_plan(parsed, plan, dry_run=False)

    archived = plan.archive_path.read_bytes()
    idx = archived.find(rh.BEGIN_MARKER)
    moved = archived[idx + len(rh.BEGIN_MARKER) :]
    assert moved == rolled_span

    # what stays behind is the original with the rolled span excised, plus the
    # pointer section rotation inserts at the cut
    remaining = p.read_bytes()
    pointer = rh._render_new_pointer_section(plan.archive_path)
    excised = original[: plan.rolled[0].start] + original[plan.rolled[-1].end :]
    assert remaining.replace(pointer, b"") == excised


# ---------------------------------------------------------------------------
# 7. The live HANDOFF.md parses under this grammar
# ---------------------------------------------------------------------------


def test_live_handoff_parses_read_only():
    """Read-only regression guard. The ⟵ and superseded idioms entered the live
    file at recent closes and rotation refused on grammar for several closes
    before anyone noticed. This fails the moment a new header idiom appears,
    which is the signal to teach the grammar rather than to hand-cut the file."""
    live = _REPO / "HANDOFF.md"
    if not live.exists():
        pytest.skip("no live HANDOFF.md in this checkout")
    before = live.read_bytes()
    parsed = rh.load(live)
    rh.validate_grammar(parsed)
    assert parsed.arrow_sections, "no session sections found in the live HANDOFF.md"
    assert live.read_bytes() == before, "this test must not write to HANDOFF.md"


def test_rotation_is_idempotent(handoff_file: Path):
    parsed = rh.load(handoff_file)
    rh.validate_grammar(parsed)
    archive_dir = handoff_file.parent / "archive" / "handoffs"
    target = len(parsed.raw) - 3000

    plan = rh.compute_plan(parsed, target_bytes=target, archive_dir=archive_dir)
    rh.apply_plan(parsed, plan, dry_run=False)

    # second pass: reparse the now-rotated file and confirm it's stable
    parsed2 = rh.load(handoff_file)
    rh.validate_grammar(parsed2)
    plan2 = rh.compute_plan(parsed2, target_bytes=target, archive_dir=archive_dir)
    assert plan2.rolled == []  # already under budget, nothing left to roll
