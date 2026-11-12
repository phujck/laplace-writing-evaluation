"""check_durable_refs.py (the ephemeral-path lint, friction 400005 --
corpus_friction/laplace_engine.jsonl RW-20260711-104316-400005: a task brief banked to a
session scratchpad vanished when the container died). Built on a synthetic fixture root
(never the live repo -- the live durable surfaces are multi-hundred-KB and change every
session) so hit/twin/clean cases and their VERDICT+rc are exercised exactly, byte for byte.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "check_durable_refs", ROOT / "scripts" / "check_durable_refs.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("check_durable_refs", mod)
    spec.loader.exec_module(mod)
    return mod


cdr = _load()


def _write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# --- durable_surfaces: which files get scanned ------------------------------------------

def test_durable_surfaces_picks_newest_three_session_handoffs(tmp_path):
    _write(tmp_path, "OPEN_STACK.md", "stack\n")
    _write(tmp_path, "HANDOFF.md", "handoff\n")
    _write(tmp_path, "EIGEN_PROTOCOL.md", "protocol\n")
    _write(tmp_path, "SESSION_HANDOFF_2026-07-09_oldest.md", "old\n")
    _write(tmp_path, "SESSION_HANDOFF_2026-07-10_second.md", "b\n")
    _write(tmp_path, "SESSION_HANDOFF_2026-07-11_third.md", "c\n")
    _write(tmp_path, "SESSION_HANDOFF_2026-07-12_newest.md", "d\n")
    _write(tmp_path, "corpus_friction/x.jsonl", "{}\n")

    names = {p.name for p in cdr.durable_surfaces(tmp_path)}
    assert "SESSION_HANDOFF_2026-07-09_oldest.md" not in names
    assert {
        "SESSION_HANDOFF_2026-07-10_second.md",
        "SESSION_HANDOFF_2026-07-11_third.md",
        "SESSION_HANDOFF_2026-07-12_newest.md",
    } <= names
    assert "OPEN_STACK.md" in names and "HANDOFF.md" in names
    assert "EIGEN_PROTOCOL.md" in names
    assert "corpus_friction/x.jsonl" in {
        str(p.relative_to(tmp_path)) for p in cdr.durable_surfaces(tmp_path)}


def test_durable_surfaces_skips_missing_files(tmp_path):
    # an empty root: nothing crashes, nothing is scanned
    assert cdr.durable_surfaces(tmp_path) == []


# --- scan: the three cases (clean / hit-with-twin / hit-without-twin) ------------------

def test_scan_clean_root_has_no_hits(tmp_path):
    _write(tmp_path, "OPEN_STACK.md",
           "N50: brief still lost with the old scratchpad (friction 400005).\n")
    hits = cdr.scan(tmp_path)
    assert hits == []


def test_scan_flags_scratchpad_reference_without_twin(tmp_path):
    _write(tmp_path, "OPEN_STACK.md",
           "Full brief banked: `scratchpad/disclosure_editorial_review.md` (task #36).\n")
    hits = cdr.scan(tmp_path)
    assert len(hits) == 1
    h = hits[0]
    assert h.file == "OPEN_STACK.md"
    assert h.line == 1
    assert h.kind == "scratchpad"
    assert h.path == "scratchpad/disclosure_editorial_review.md"
    assert h.twin is None
    ok, failing = cdr._verdict(hits)
    assert not ok and failing == [h]


def test_scan_flags_reference_with_durable_twin_as_warn(tmp_path):
    _write(tmp_path, "OPEN_STACK.md",
           "Full brief banked: `scratchpad/disclosure_editorial_review.md` (task #36).\n")
    # the durable twin: same basename, living in-repo (e.g. copied in at close)
    _write(tmp_path, "briefs/disclosure_editorial_review.md", "the recovered brief\n")

    hits = cdr.scan(tmp_path)
    assert len(hits) == 1
    h = hits[0]
    assert h.twin == "briefs/disclosure_editorial_review.md"
    ok, failing = cdr._verdict(hits)
    assert ok and failing == []


def test_scan_matches_tmp_root_claude_home_and_task_output(tmp_path):
    _write(tmp_path, "HANDOFF.md",
           "Plan: `/root/.claude/plans/tender-mixing-adleman.md`; all on PR #43.\n"
           "cache at /tmp/claude-0/abc/scratchpad/report.md, dead now.\n"
           "see task-output/run7/verdict.json for the judge call.\n")
    hits = cdr.scan(tmp_path)
    kinds = {h.kind for h in hits}
    assert "claude_home" in kinds
    assert "tmp_path" in kinds
    assert "task_output" in kinds
    # the /tmp path also contains the substring "scratchpad/" -- must not double-count
    tmp_hits = [h for h in hits if h.kind == "tmp_path"]
    assert len(tmp_hits) == 1
    assert tmp_hits[0].path == "/tmp/claude-0/abc/scratchpad/report.md"
    assert all(h.twin is None for h in hits)  # nothing durable backs any of these


def test_scan_strips_trailing_markdown_punctuation(tmp_path):
    _write(tmp_path, "EIGEN_PROTOCOL.md",
           "see (scratchpad/notes.md) for detail, or `/tmp/x/y.md`.\n")
    hits = cdr.scan(tmp_path)
    paths = {h.path for h in hits}
    assert "scratchpad/notes.md" in paths
    assert "/tmp/x/y.md" in paths


def test_scan_covers_corpus_friction_jsonl(tmp_path):
    _write(tmp_path, "corpus_friction/laplace_engine.jsonl",
           '{"id": "x", "target": "scratchpad/disclosure_editorial_review.md (task #36)"}\n')
    hits = cdr.scan(tmp_path)
    assert len(hits) == 1
    assert hits[0].file == "corpus_friction/laplace_engine.jsonl"


# --- main(): rc + VERDICT sentinel, matching the paper_gates.py convention -------------

def test_main_rc0_verdict_pass_on_clean_root(tmp_path, capsys):
    _write(tmp_path, "OPEN_STACK.md", "nothing ephemeral here.\n")
    rc = cdr.main(["--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip().splitlines()[-1] == "VERDICT=PASS hits=0 warn=0"


def test_main_rc0_verdict_pass_when_only_warns(tmp_path, capsys):
    _write(tmp_path, "OPEN_STACK.md", "banked: `scratchpad/x.md`\n")
    _write(tmp_path, "briefs/x.md", "twin\n")
    rc = cdr.main(["--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip().splitlines()[-1] == "VERDICT=PASS hits=1 warn=1"


def test_main_rc1_verdict_fail_on_untwinned_hit(tmp_path, capsys):
    _write(tmp_path, "OPEN_STACK.md", "banked: `scratchpad/x.md`, no twin.\n")
    rc = cdr.main(["--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc == 1
    last = out.strip().splitlines()[-1]
    assert last.startswith("VERDICT=FAIL")
    assert "fail=1" in last


def test_main_json_flag_emits_hit_records(tmp_path, capsys):
    _write(tmp_path, "OPEN_STACK.md", "banked: `scratchpad/x.md`\n")
    rc = cdr.main(["--root", str(tmp_path), "--json"])
    out = capsys.readouterr().out
    assert rc == 1
    import json
    body = "\n".join(out.strip().splitlines()[:-1])
    records = json.loads(body)
    assert records[0]["path"] == "scratchpad/x.md"
    assert records[0]["twin"] is None
