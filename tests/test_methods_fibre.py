"""The methods fibre reaches the packet (WO-20260820-methods-fibre-compile-dispatch).

corpus_friction/methods.jsonl banks house style and working standards as typed
law/forbids rows. A fibre nothing consumes is a fibre that does not exist, so the seam
under test is the consumption one: compile_dispatch reads the task class of the item it
is compiling and attaches that class's rows — plus the class-agnostic ones — to the
packet, law + forbids with refs-only evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from laplace.pipeline import dispatch
from laplace.pipeline.dispatch import compile_dispatch, method_rows_for

ROOT = Path(__file__).resolve().parents[1]

_ROW_KEYS = {"id", "task_class", "law", "forbids", "refs", "amended", "amendment_refs"}


def test_manuscript_packet_carries_its_methods(monkeypatch):
    # mint is project-light and prompt-bearing: the simplest manuscript-class dispatch
    from laplace.representation import custody_mode
    monkeypatch.setattr(custody_mode, "is_off", lambda _root: True)
    content = "fixture reconstruction"
    reconstruction = {
        "kind": "node", "reference": "whole", "goal": "mint the manuscript object",
        "content": content, "content_handle": "sha256:" + hashlib.sha256(content.encode()).hexdigest(),
        "content_status": "COMPLETE", "content_truncated": False, "read_only": True,
        "transition_claim": "none", "authority_write": "none",
    }
    out = compile_dispatch("whole", "mint the manuscript object", worker="mint",
                           project="paper_falqon", reconstruction=reconstruction)
    assert "error" not in out, out
    rows = out["methods"]
    assert rows, "a manuscript-class packet compiled with no method rows"
    classes = {r["task_class"] for r in rows}
    assert "manuscript" in classes, classes
    assert "all" in classes, "the class-agnostic rows ride every non-prose packet"
    assert "meta" not in classes, "M-README documents the wiring; it is not builder law"
    # and the prompt actually carries them — the packet field alone is not carriage
    assert "<!-- METHODS -->" in out["prompt"]
    assert rows[0]["id"] in out["prompt"]


def test_rows_ride_as_law_and_forbids_with_refs_only():
    rows = method_rows_for("manuscript", ROOT)
    assert rows
    for r in rows:
        assert set(r) <= _ROW_KEYS, set(r) - _ROW_KEYS
        assert r["law"].strip()
        assert isinstance(r["refs"], list)
        # the store's own bookkeeping never rides the packet
        assert "status" not in r and "evidence" not in r and "record" not in r


def test_class_projection_is_a_projection():
    everything = {r["id"] for r in method_rows_for("manuscript", ROOT)}
    scoped = {r["id"] for r in method_rows_for("manuscript", ROOT, include_all=False)}
    verification = {r["id"] for r in method_rows_for("verification", ROOT)}
    assert scoped < everything, "include_all=False must drop the class-agnostic rows"
    assert scoped and verification
    assert not (scoped & verification), "a manuscript row leaked into verification"


def test_prose_packet_is_context_isolated_from_the_engine_rows():
    # §13: the prose worker carries its craft law, not the engine-framed `all` rows
    assert dispatch.WORKER_TASK_CLASS["prose"] == "manuscript"
    rows = method_rows_for("manuscript", ROOT, include_all=False)
    assert {r["task_class"] for r in rows} == {"manuscript"}


def test_amendment_rides_with_the_row_it_moves(tmp_path):
    store = tmp_path / "corpus_friction"
    store.mkdir()
    (store / "methods.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"id": "M-x", "task_class": "figures", "law": "a  law", "forbids": "a forbid",
         "evidence": "evidence/one · evidence/two", "status": "seeded"},
        {"record": "amendment", "id": "AMEND-x", "target": "M-x", "note": "moved here"},
        {"id": "M-y", "task_class": "outward", "law": "unrelated", "forbids": ""},
    ]) + "\n", encoding="utf-8")
    rows = method_rows_for("figures", tmp_path, include_all=False)
    assert [r["id"] for r in rows] == ["M-x"], "an amendment must not ride as a row"
    assert rows[0]["law"] == "a law"            # register law: whitespace normalised
    assert rows[0]["refs"] == ["evidence/one", "evidence/two"]
    assert rows[0]["amended"] == ["AMEND-x: moved here"]


def test_missing_or_broken_store_is_silent(tmp_path):
    assert method_rows_for("manuscript", tmp_path) == []
    (tmp_path / "corpus_friction").mkdir()
    (tmp_path / "corpus_friction" / "methods.jsonl").write_text(
        "not json\n\n{\"no\": \"id\"}\n", encoding="utf-8")
    assert method_rows_for("manuscript", tmp_path) == []


def test_the_wake_names_the_fibre():
    from laplace.engine import self_corpus
    line = self_corpus._methods_fibre_line(ROOT)
    assert len(line) == 1
    assert "corpus_friction/methods.jsonl" in line[0]
    assert self_corpus._methods_fibre_line(Path("/nonexistent-tree")) == []
