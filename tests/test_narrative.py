"""load_section: corrupt-vs-absent (P4) - a corrupt file warns, an absent one is silent."""

from __future__ import annotations

import logging

from laplace.pipeline import narrative


def test_load_section_corrupt_file_warns_and_returns_none(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(narrative, "narrative_dir", lambda project, repo_root=None: tmp_path)
    p = tmp_path / "s1.json"
    p.write_text("{not json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        result = narrative.load_section("whatever", "s1")

    assert result is None
    assert any(str(p) in r.getMessage() for r in caplog.records)


def test_load_section_absent_file_returns_none_silently(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(narrative, "narrative_dir", lambda project, repo_root=None: tmp_path)
    p = tmp_path / "s1.json"
    assert not p.exists()

    with caplog.at_level(logging.WARNING):
        result = narrative.load_section("whatever", "s1")

    assert result is None
    assert caplog.records == []
