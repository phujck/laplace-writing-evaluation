"""The next handoff takes its name from today's newest design, including drafts."""
import os
import subprocess

import pytest

from laplace.engine import handoff_render


@pytest.mark.parametrize("newest_tracked", [False, True])
def test_next_render_uses_newest_design_today(tmp_path, newest_tracked):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    names = [
        "ARMING_2026-08-28_provider-attention-generation.md",
        "DESIGN_2026-09-14_z-older-design.md",
        "DESIGN_2026-09-14_the-atlas-container.md",
        "DESIGN_2026-09-15_future-design.md",
    ]
    for index, name in enumerate(names):
        path = tmp_path / name
        path.write_text("# Design\n", encoding="utf-8")
        os.utime(path, (100 + index, 100 + index))
    tracked = names if newest_tracked else [name for name in names if name != names[2]]
    subprocess.run(["git", "add", "--", *tracked], cwd=tmp_path, check=True)
    historical = tmp_path / "SESSION_HANDOFF_2026-09-14_provider-attention-generation.md"
    historical.write_text("historical handoff\n", encoding="utf-8")

    result = handoff_render.render_close(
        tmp_path, date="2026-09-14", since="2026-08-28T00:00:00Z",
        dry_run=True, scratch=tmp_path / "preview",
    )
    assert result["slug"] == "the-atlas-container"
    assert result["slug_source"] == names[2]
    assert historical.read_text() == "historical handoff\n"


def test_no_design_today_preserves_old_class_and_window_rule(tmp_path):
    for name in (
        "ARMING_2026-08-27_outside-window.md",
        "ARMING_2026-08-28_session-opening.md",
        "ARMING_2026-09-13_refinement.md",
        "DESIGN_2026-09-13_prior-design.md",
    ):
        (tmp_path / name).touch()
    assert handoff_render.session_slug(
        tmp_path, since="2026-08-28T00:00:00Z", date="2026-09-14",
    ) == ("session-opening", "ARMING_2026-08-28_session-opening.md")


def test_no_naming_document_uses_default(tmp_path):
    slug, _ = handoff_render.session_slug(tmp_path, since=None, date="2026-09-14")
    assert slug == handoff_render.SLUG_FALLBACK


def test_same_day_authored_versions_survive_retry_and_failed_pair_write(tmp_path, monkeypatch):
    from pathlib import Path
    from laplace.engine import self_corpus

    live = tmp_path / "HANDOFF.md"
    live.write_text("# Current handoff\n\n## System map\nLaplace and Atlas.\n")
    args = {"date": "2026-09-19", "slug": "repair", "since": None}
    first = handoff_render.render_close(tmp_path, authored="First measured result.", **args)
    first_path = tmp_path / first["dated"]
    first_bytes = first_path.read_bytes()
    second = handoff_render.render_close(tmp_path, authored="Second measured result; next recover it.", **args)
    second_path = tmp_path / second["dated"]
    assert first["ok"] and second["ok"] and first_path != second_path
    assert first_path.read_bytes() == first_bytes
    opening = self_corpus._handoff_opening(second_path.read_text())
    assert "Second measured result; next recover it." in opening[:700]
    assert opening.startswith("**Authored checkpoint; publication recorded separately:**")

    before = {path: path.read_bytes() for path in (first_path, second_path, live)}
    previous_mtime = second_path.stat().st_mtime_ns
    # A real source change makes the repeated render different before the second write fails.
    (tmp_path / "DESIGN_2026-09-19_retry.md").write_text("# Retry evidence\nA new result.\n")
    replace = Path.replace

    def refuse_live_replace(path, target):
        if Path(target) == live:
            raise OSError("planted HANDOFF replacement failure")
        return replace(path, target)

    with monkeypatch.context() as context:
        context.setattr(Path, "replace", refuse_live_replace)
        failed = handoff_render.render_close(
            tmp_path, authored="Second measured result; next recover it.", **args)
    assert failed["ok"] is False and "rolled back" in failed["error"]
    assert all(path.read_bytes() == expected for path, expected in before.items())
    assert second_path.stat().st_mtime_ns == previous_mtime
    assert not list(tmp_path.glob(".*.tmp"))

    # A plain retry follows the current HANDOFF pointer, not the earlier unsuffixed record.
    retried = handoff_render.render_close(tmp_path, **args)
    assert retried["ok"] and retried["dated"] == second["dated"]
    assert "Second measured result; next recover it." in retried["dated_text"]
    assert len(list(tmp_path.glob("SESSION_HANDOFF_*.md"))) == 2
