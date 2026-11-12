"""W2.3 — OPEN_STACK's author-fork stratum ledgerized: the markdown is a render.

Fail-closed contract:
  * round-trip: store -> render -> parse == store (the render-owned rows).
  * a store edit APPEARS in the render.
  * a hand-edit to a rendered row is DETECTED (the drift check, close idiom).
  * the desk reads the STORE: empty the store => the fork class drops.
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

ros = importlib.import_module("scripts.render_open_stack") if False else None


def _load_render_module():
    """Import scripts/render_open_stack.py by path (scripts/ is not a package)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "render_open_stack", ROOT / "scripts" / "render_open_stack.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ros = _load_render_module()


# --------------------------------------------------------------------------- #
# A tmp repo fixture: a minimal OPEN_STACK.md carrying the Stratum-1 table frame
# plus prose above and below, and a seeded store.
# --------------------------------------------------------------------------- #
_PROSE_ABOVE = "# The open stack\n\nSome header prose.\n\n**Sweep note.** A bullet:\n\n"
_PROSE_BELOW = "\n\n## Cleared / killed log\n\n- a tombstone stays put.\n"
_SWEEP_BULLET = ("- **FQ7 grow — ARMED " + ros._LIVE_MARKER
                 + " his adjudications**: the consumer runs clean.\n")


def _write_md(repo: Path, rows: list[str]) -> None:
    body = (_PROSE_ABOVE + _SWEEP_BULLET + "\n"
            + ros.S1_HEADER + "\n" + ros.S1_SEP + "\n"
            + "\n".join(rows) + "\n" + _PROSE_BELOW)
    (repo / "OPEN_STACK.md").write_text(body, encoding="utf-8")


def _seed(repo: Path, records: list[dict]) -> None:
    (repo / "corpus_friction").mkdir(parents=True, exist_ok=True)
    (repo / ros.STORE_REL).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
        encoding="utf-8")


def _rec(fid, title, opened="2026-06-01", rec="1", status="⚪", trig="a trigger."):
    return {"id": fid, "kind": "open-stack-fork", "stratum": 1, "render_owned": True,
            "title": title, "opened": opened, "recurrence": rec,
            "status": status, "trigger": trig}


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    rows = ["| F1 | first fork | 2026-06-01 | ~9 | ⚪ | the center. |",
            "| F23 | second fork | 2026-06-08 | 2 | " + ros._LIVE_MARKER + " | his. |"]
    _write_md(tmp_path, rows)
    _seed(tmp_path, [
        _rec("F1", "first fork", "2026-06-01", "~9", "⚪", "the center."),
        _rec("F23", "second fork", "2026-06-08", "2", ros._LIVE_MARKER, "his."),
        # desk-only rows (not render-owned): must NOT appear in the render.
        {"id": "F27", "kind": "open-stack-fork", "stratum": 2, "render_owned": False,
         "title": "protection", "status": ros._LIVE_MARKER, "context": "| F27 | … |"},
    ])
    return tmp_path


def _parse_owned(repo: Path) -> list[dict]:
    """Parse the rendered Stratum-1 table back into the render-owned record shape."""
    lines = ros.render(repo).split("\n")
    return ros._parse_s1_table(lines)


def test_round_trip_store_render_parse_equals_store(repo: Path):
    """store -> render -> parse == the render-owned records of the store."""
    owned = ros._render_owned(ros.load_forks(repo))
    reparsed = _parse_owned(repo)
    # compare the 1:1 cell fields (round-trip identity on what the table carries).
    keys = ("id", "title", "opened", "recurrence", "status", "trigger")
    assert [{k: r[k] for k in keys} for r in reparsed] == \
           [{k: r[k] for k in keys} for r in owned]


def test_a_store_edit_appears_in_the_render(repo: Path):
    forks = ros.load_forks(repo)
    for f in forks:
        if f["id"] == "F1":
            f["trigger"] = "EDITED-IN-THE-STORE"
    _seed(repo, forks)
    out = ros.render(repo)
    assert "EDITED-IN-THE-STORE" in out
    # and the render is now what a fresh --check accepts.
    (repo / "OPEN_STACK.md").write_text(out, encoding="utf-8")
    assert _check(repo) == 0


def test_desk_only_rows_are_not_rendered(repo: Path):
    """F27 (render_owned=false) lives elsewhere in the md; the render never emits it."""
    out = ros.render(repo)
    # only the two Stratum-1 rows are in the table; F27 is not a table row.
    assert out.count("\n| F") == 2
    assert "| F27 |" not in out


def _check(repo: Path) -> int:
    rendered = ros.render(repo)
    current = (repo / "OPEN_STACK.md").read_text(encoding="utf-8")
    return 0 if current == rendered else 1


def test_a_hand_edit_to_a_rendered_row_is_detected(repo: Path):
    # first make the file clean (write the render), then hand-edit a rendered row.
    (repo / "OPEN_STACK.md").write_text(ros.render(repo), encoding="utf-8")
    assert _check(repo) == 0
    md = (repo / "OPEN_STACK.md").read_text(encoding="utf-8")
    tampered = md.replace("first fork", "HAND-EDITED fork")
    assert tampered != md
    (repo / "OPEN_STACK.md").write_text(tampered, encoding="utf-8")
    assert _check(repo) == 1  # drift detected


def test_render_leaves_prose_and_sweep_logs_untouched(repo: Path):
    (repo / "OPEN_STACK.md").write_text(ros.render(repo), encoding="utf-8")
    md = (repo / "OPEN_STACK.md").read_text(encoding="utf-8")
    assert "Some header prose." in md
    assert "## Cleared / killed log" in md
    assert "a tombstone stays put." in md
    assert _SWEEP_BULLET.strip() in md  # the FQ7 sweep bullet stays put
    assert ros.BANNER in md  # the render carries its banner


def test_migrate_is_idempotent_without_force(repo: Path):
    # store already seeded by the fixture -> migrate refuses without --force.
    assert ros.migrate(repo, force=False) == 1
    assert ros.migrate(repo, force=True) == 0


# --------------------------------------------------------------------------- #
# The desk reads the STORE (desk._desk_forks — W5: rehoused from guide), not the markdown.
# --------------------------------------------------------------------------- #
def _desk_mod():
    import importlib
    desk = importlib.import_module("laplace.web.desk")
    return importlib.reload(desk)


def test_desk_fork_class_reads_the_store(repo: Path):
    desk = _desk_mod()
    out = desk._desk_forks(repo)
    ids = {r["id"] for r in out["rows"]}
    # the three 🔴 store records surface (F23 render-owned, F27 desk-only); F1 is ⚪.
    assert "F23" in ids
    assert "F27" in ids
    assert "F1" not in ids
    assert len(desk._live_open_stack_forks(repo)) == 2  # F23 + F27 are the live pair


def test_emptying_the_store_drops_the_fork_class(repo: Path):
    desk = _desk_mod()
    # empty the store in place.
    (repo / ros.STORE_REL).write_text("", encoding="utf-8")
    out = desk._desk_forks(repo)
    assert out["count"] == 0
    assert desk._live_open_stack_forks(repo) == []


def test_absent_store_is_honestly_empty(tmp_path: Path):
    desk = _desk_mod()
    assert desk._live_open_stack_forks(tmp_path) == []
    assert desk._desk_forks(tmp_path)["count"] == 0
