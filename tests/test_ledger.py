"""read_jsonl_counted — the honest read that surfaces the poison-line drop count
instead of swallowing it (read_jsonl still swallows, for existing callers)."""

import logging

from laplace.pipeline import ledger


def test_read_jsonl_counted_reports_drops(tmp_path):
    lp = tmp_path / "l.jsonl"
    lp.write_text('{"a": 1}\nnot json\n{"b": 2}\n', encoding="utf-8")
    records, dropped_n = ledger.read_jsonl_counted(lp)
    assert records == [{"a": 1}, {"b": 2}]
    assert dropped_n == 1


def test_read_jsonl_still_discards_the_count(tmp_path):
    lp = tmp_path / "l.jsonl"
    lp.write_text('{"a": 1}\nnot json\n{"b": 2}\n', encoding="utf-8")
    assert ledger.read_jsonl(lp) == [{"a": 1}, {"b": 2}]


def test_read_jsonl_counted_warns_on_drop(tmp_path, caplog):
    lp = tmp_path / "l.jsonl"
    lp.write_text('{"a": 1}\nnot json\n{"b": 2}\n', encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        ledger.read_jsonl_counted(lp)
    assert len(caplog.records) == 1
    msg = caplog.records[0].getMessage()
    assert str(lp) in msg
    assert "2" in msg                                 # the poisoned line number
