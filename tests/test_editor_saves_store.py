"""W8/J4 EDITOR-SAVE STORE — the W8-judge amendments (A2 monotonic mint, A3 the lock, A4
the pruned 404), unit-level against ``projection_viewer``'s store functions directly
(no scanner, no browser — the playwright walk (``tests/j4_editor_history.playwright.mjs``)
covers the real end-to-end surface).

The contract these tests fail-close on:
  * A2 — a name freed by pruning can NEVER re-mint: uniqueness rides a monotonic ``seq``
    counter persisted in ``index.json``, never the ``while (dir).exists()`` disk-probe the
    judge broke live (proof: one id present in BOTH ``dropped[]`` and ``saves[]``).
  * A3 — the index read-modify-write + id mint + dir write is ONE locked critical section:
    a contention hammer (2 threads x 20 reps) must never lose a row or mint a duplicate id.
  * A4 — restoring a version_id retired into ``index['dropped']`` reads DISTINCT from one
    that never existed: the 404 body names the bound, the drop time, and the reason.
"""
from __future__ import annotations

import threading
import time
import hashlib
import json
from pathlib import Path

import pytest

from laplace.manuscript import projection_viewer as pv

pytestmark = pytest.mark.unit


def _bank(md: Path, data: bytes = b"x", **kw) -> dict:
    return pv.bank_editor_save(md, Path("main.tex"), data,
                               author=kw.get("author", "author"),
                               surface=kw.get("surface", "editor"),
                               source=kw.get("source", "save"))


def test_raw_source_observation_guards_exact_physical_bytes_and_stale_save(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "_repo_root", lambda: tmp_path)
    live = tmp_path / "main.tex"
    original = b"\xef\xbb\xbfA\r\nB\r\n"
    live.write_bytes(original)
    query = {"file": ["main.tex"], "view": ["source"]}
    status, _, encoded = pv.handle("/projection/tex", query, "GET", b"")
    observed = json.loads(encoded)
    assert status == 200 and observed["content"].encode() == original
    assert observed["expected_source_digest"] == "sha256:" + hashlib.sha256(original).hexdigest()
    live.write_bytes(b"external newer source")
    post = {"file": ["main.tex"], "bank": ["editor"], "expected_source_digest": [observed["expected_source_digest"]]}
    monkeypatch.setattr(pv, "bank_editor_save", lambda *a, **k: pytest.fail("stale save banked"))
    status, _, encoded = pv.handle("/projection/tex", post, "POST", b"stale draft")
    assert status == 409 and json.loads(encoded)["recovery"]["query"]["view"] == "source"
    assert live.read_bytes() == b"external newer source"


def test_raw_save_missing_guard_refuses_and_acknowledged_basis_allows_next_save(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "_repo_root", lambda: tmp_path)
    live = tmp_path / "main.tex"; live.write_bytes(b"A")
    query = {"file": ["main.tex"]}
    assert pv.handle("/projection/tex", query, "POST", b"B")[0] == 409
    guard = pv._source_observation(live)["expected_source_digest"]
    for after in (b"B", b"C"):
        status, _, body = pv.handle("/projection/tex", {**query, "expected_source_digest": [guard]}, "POST", after)
        assert status == 200 and live.read_bytes() == after
        guard = json.loads(body)["expected_source_digest"]
        assert guard == "sha256:" + hashlib.sha256(after).hexdigest()


def test_restore_binds_saved_file_version_body_and_separate_live_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(pv, "_repo_root", lambda: tmp_path)
    md = tmp_path / "ms"; md.mkdir()
    monkeypatch.setattr(pv, "_manuscript_dir_for", lambda corpus: md)
    live = md / "main.tex"; live.write_bytes(b"historical")
    saved = pv.bank_editor_save(md, live, b"historical", author="author", surface="editor")
    live.write_bytes(b"current")
    assert pv.restore_editor_save("p", str(live), saved["version_id"], "sha256:" + saved["sha"])["status"] == 409
    assert live.read_bytes() == b"current" and pv._load_saves_index(md)["seq"] == 1
    other = md / "nested" / "main.tex"; other.parent.mkdir(); other.write_bytes(b"different")
    assert not pv.restore_editor_save("p", str(other), saved["version_id"], pv._source_observation(other)["expected_source_digest"]).get("ok")
    assert other.read_bytes() == b"different"
    restored = pv.restore_editor_save("p", str(live), saved["version_id"], pv._source_observation(live)["expected_source_digest"])
    assert restored["ok"] and restored["restored_from"] == saved["version_id"] and restored["version_id"] != saved["version_id"]
    assert live.read_bytes() == b"historical"
    (pv._editor_saves_dir(md) / saved["version_id"] / "main.tex").write_bytes(b"corrupt")
    assert not pv.restore_editor_save("p", str(live), saved["version_id"], restored["expected_source_digest"]).get("ok")


def test_concurrent_raw_saves_admit_only_one_exact_inspected_preimage(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr(pv, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(pv, "_manuscript_dir_for", lambda corpus: tmp_path)
    live = tmp_path / "main.tex"; live.write_bytes(b"A")
    guard = pv._source_observation(live)["expected_source_digest"]
    start = threading.Barrier(2)
    def save(after):
        start.wait()
        return pv.handle("/projection/tex", {"file": ["main.tex"], "bank": ["fixture"],
            "expected_source_digest": [guard]}, "POST", after)[0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(save, b"B"); second = pool.submit(save, b"C")
        assert sorted([first.result(), second.result()]) == [200, 409]
    assert live.read_bytes() in {b"B", b"C"}
    assert pv._load_saves_index(tmp_path)["seq"] == 1


def test_nested_saved_source_metadata_reaches_rail_and_restore_legacy_is_unproved(tmp_path, monkeypatch):
    from laplace.web import shared_ui
    from laplace.manuscript import manuscript_versions
    monkeypatch.setattr(pv, "_repo_root", lambda: tmp_path)
    md = tmp_path / "ms"; (md/'chapters').mkdir(parents=True)
    monkeypatch.setattr(pv, "_manuscript_dir_for", lambda corpus: md)
    live = md/'chapters'/'one.tex'; live.write_bytes(b"old nested source")
    saved = pv.bank_editor_save(md, live, live.read_bytes(), author="author", surface="editor")
    rows, _ = manuscript_versions._editor_save_rows(md, tmp_path)
    assert rows[0]['source_file'] == 'ms/chapters/one.tex'
    live.write_bytes(b"current nested source")
    result = pv.restore_editor_save('p', rows[0]['source_file'], saved['version_id'], pv._source_observation(live)['expected_source_digest'])
    assert result['ok'] and live.read_bytes() == b"old nested source"
    manifest_path = pv._editor_saves_dir(md)/saved['version_id']/'VERSION.json'
    manifest = json.loads(manifest_path.read_text()); manifest.pop('source_file'); manifest_path.write_text(json.dumps(manifest))
    # Historical entries predate the new independent target/body pins.
    index = pv._load_saves_index(md)
    original = next(row for row in index['saves'] if row['version_id'] == saved['version_id'])
    original.pop('source_file'); original.pop('bytes'); pv._write_saves_index(md, index)
    result = pv.restore_editor_save('p', str(live), saved['version_id'], pv._source_observation(live)['expected_source_digest'])
    assert result['status'] == 409 and result['reason'] == 'saved-source-target-unproved'
    assert (manifest_path.parent/'one.tex').read_bytes() == b"old nested source"


@pytest.mark.parametrize('writer', ['raw', 'restore', 'reorder', 'bibliography'])
def test_lock_free_source_reader_sees_complete_old_then_complete_new_publication(tmp_path, monkeypatch, writer):
    from concurrent.futures import ThreadPoolExecutor
    from laplace.manuscript import manuscript_source, storyboard
    from laplace.pipeline import bibliography_stage
    monkeypatch.setattr(pv, '_repo_root', lambda:tmp_path)
    monkeypatch.setattr(pv, '_manuscript_dir_for', lambda corpus:tmp_path)
    live = tmp_path/'main.tex'
    before = b'\\documentclass{article}\n\\begin{document}\n\\input{S2}\n\\input{S1}\n\\end{document}\n'
    live.write_bytes(before)
    guard = pv._source_observation(live)['expected_source_digest']
    saved = pv.bank_editor_save(tmp_path, live, b'Complete selected historical source', author='fixture',surface='editor')
    staged, release = threading.Event(), threading.Event()
    original = manuscript_source.stage_source
    def pause(*a, **kw):
        pending = original(*a, **kw)
        staged.set()
        assert release.wait(3)
        return pending
    monkeypatch.setattr(manuscript_source, 'stage_source', pause)
    def publish():
        if writer == 'raw': return pv.handle('/projection/tex', {'file':['main.tex'],'expected_source_digest':[guard]}, 'POST', b'Complete new authored source')
        if writer == 'restore': return pv.restore_editor_save('p','main.tex',saved['version_id'],guard)
        if writer == 'reorder': return storyboard._rewrite_inputs(live,['S1','S2'],[])
        return bibliography_stage.ensure_wired(live)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(publish)
        try:
            assert staged.wait(3), 'actual writer did not use atomic source staging'
            assert live.read_bytes() == before  # reader deliberately takes no lease
        finally: release.set()
        future.result(timeout=3)
    after = live.read_bytes()
    assert after != before and after
    if writer == 'raw': assert after == b'Complete new authored source'
    if writer == 'restore': assert after == b'Complete selected historical source'
    if writer == 'reorder': assert after.index(b'\\input{S1}') < after.index(b'\\input{S2}')
    if writer == 'bibliography': assert b'\\bibliography{refs}' in after


@pytest.mark.parametrize('writer', ['raw', 'restore'])
def test_version_bank_failure_retains_exact_committed_source_ack(tmp_path, monkeypatch, writer):
    monkeypatch.setattr(pv, '_repo_root', lambda:tmp_path)
    monkeypatch.setattr(pv, '_manuscript_dir_for', lambda corpus:tmp_path)
    live = tmp_path/'main.tex'; live.write_bytes(b'before')
    saved = pv.bank_editor_save(tmp_path, live, b'historical',author='fixture',surface='editor')
    guard = pv._source_observation(live)['expected_source_digest']
    def unavailable(*a, **kw): raise OSError('controlled snapshot failure')
    monkeypatch.setattr(pv,'bank_editor_save',unavailable)
    if writer == 'raw':
        status,_,encoded = pv.handle('/projection/tex',{'file':['main.tex'],'bank':['fixture'],'expected_source_digest':[guard]},'POST',b'after')
        result=json.loads(encoded);assert status==200
        assert live.read_bytes()==b'after'
    else:
        result=pv.restore_editor_save('p','main.tex',saved['version_id'],guard)
        assert live.read_bytes()==b'historical' and result['restored_from']==saved['version_id']
    assert result['ok'] and result['source_committed'] and result['snapshot_status']=='UNPROVED'
    assert result['consumed_source_digest']==guard and result['expected_source_digest']==pv._source_observation(live)['expected_source_digest']
    assert 'version_id' not in result and result['maintenance_warnings'][0]['operation']=='bank_editor_save'


# ---------------------------------------------------------------------------
# A2 — MONOTONIC ID MINT: a name freed by pruning can never re-mint.
# ---------------------------------------------------------------------------

def test_same_second_burst_past_the_bound_never_reuses_a_dropped_id(tmp_path, monkeypatch):
    md = tmp_path / "manuscript"
    md.mkdir()
    # freeze the wall clock — every mint in this test shares ONE base timestamp, the
    # exact shape the old existence-check loop mishandled once pruning freed a dir name.
    monkeypatch.setattr(pv.time, "strftime", lambda *a, **k: "2026-07-15_120000")

    for i in range(40):                      # > the 32-bound: the earliest 8 prune
        _bank(md, data=f"v{i}".encode())

    idx = pv._load_saves_index(md)
    dropped_ids = {r["version_id"] for r in idx["dropped"]}
    saved_ids = {r["version_id"] for r in idx["saves"]}
    assert len(dropped_ids) == 8 and len(saved_ids) == 32
    assert not (dropped_ids & saved_ids), "burst 1: no id straddles both ledgers"

    # a SECOND same-second burst: the old ``while (dir).exists()`` loop would restart its
    # -N probe from 1 and re-mint an id already retired into dropped[] once its dir was
    # removed — the judge's live proof (one id present in BOTH dropped[] and saves[]).
    for i in range(40):
        _bank(md, data=f"w{i}".encode())

    idx2 = pv._load_saves_index(md)
    dropped_ids2 = {r["version_id"] for r in idx2["dropped"]}
    saved_ids2 = {r["version_id"] for r in idx2["saves"]}
    assert not (dropped_ids2 & saved_ids2), "burst 2: no id straddles both ledgers"
    assert len(dropped_ids2) + len(saved_ids2) == len(dropped_ids2 | saved_ids2), (
        "every id ever minted is globally unique")
    assert idx2["seq"] == 80, "the counter climbs monotonically — pruning never resets it"


def test_seq_persists_across_a_fresh_index_load(tmp_path):
    md = tmp_path / "manuscript"
    md.mkdir()
    for _ in range(5):
        _bank(md)
    assert pv._load_saves_index(md)["seq"] == 5
    # a fresh load (no in-memory state carried over) still sees the persisted counter.
    idx = pv._load_saves_index(md)
    vid = pv._next_version_id(idx)
    assert vid.endswith("-6"), vid
    assert idx["seq"] == 6


def test_a_legacy_index_with_no_seq_field_starts_clean_at_zero(tmp_path):
    """An index.json banked before A2 (no ``seq`` key) must not crash the mint — it
    setdefaults to 0 and climbs from there, same as a brand-new store."""
    md = tmp_path / "manuscript"
    d = md / "editor_saves"
    d.mkdir(parents=True)
    (d / "index.json").write_text('{"saves": [], "dropped": []}', encoding="utf-8")
    man = _bank(md, data=b"legacy-compat")
    idx = pv._load_saves_index(md)
    assert idx["seq"] == 1
    assert man["version_id"].endswith("-1")


# ---------------------------------------------------------------------------
# A3 — THE LOCK: the index RMW + id mint + dir write is ONE critical section.
# ---------------------------------------------------------------------------

def test_concurrent_double_bank_is_lock_safe(tmp_path, monkeypatch):
    md = tmp_path / "manuscript"
    md.mkdir()

    # inject a delay INSIDE the critical section (between the RMW load and the final
    # index write) so two threads are overwhelmingly likely to actually overlap in wall
    # time — a bare hammer can get lucky and never interleave; this makes the race the
    # lock must prevent DETERMINISTIC to provoke (the judge's contention hammer, made
    # reliable for CI rather than left to chance).
    real_write = pv._write_saves_index

    def slow_write(md_, index):
        time.sleep(0.01)
        real_write(md_, index)

    monkeypatch.setattr(pv, "_write_saves_index", slow_write)

    errors: list[Exception] = []

    def worker(tag):
        for i in range(20):
            try:
                _bank(md, data=f"{tag}-{i}".encode(), author=tag)
            except Exception as exc:  # noqa: BLE001 — surfaced via `errors`, not swallowed
                errors.append(exc)

    t1 = threading.Thread(target=worker, args=("A",))
    t2 = threading.Thread(target=worker, args=("B",))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errors, f"concurrent banks raised: {errors}"
    idx = pv._load_saves_index(md)
    all_ids = [r["version_id"] for r in idx["saves"]] + [r["version_id"] for r in idx["dropped"]]
    assert len(all_ids) == 40, f"the RMW race lost a row: {len(all_ids)} of 40 survive in the ledger"
    assert len(all_ids) == len(set(all_ids)), "no duplicate-minted id under contention"
    assert len(idx["saves"]) == 32, "the bound holds after 40 concurrent banks"
    on_disk = {p.name for p in (md / "editor_saves").iterdir() if p.is_dir()}
    assert on_disk == {r["version_id"] for r in idx["saves"]}, "index == disk, no orphan/missing dirs"


def test_lockfile_is_a_dot_lock_sidecar_beside_index_json(tmp_path):
    """The lockfile lives beside index.json and matches the ``*.lock`` gitignore glob —
    a transient sidecar, never content that should ever be committed."""
    md = tmp_path / "manuscript"
    md.mkdir()
    _bank(md)
    lockfile = pv._editor_saves_lockfile(md)
    assert lockfile.parent == pv._editor_saves_dir(md)
    assert lockfile.name.endswith(".lock")


# ---------------------------------------------------------------------------
# A4 — THE PRUNED 404 NAMES THE DROP, distinct from never-existed.
# ---------------------------------------------------------------------------

def test_restore_of_a_dropped_save_names_the_bound_distinct_from_never_existed(tmp_path, monkeypatch):
    md = tmp_path / "manuscript"
    md.mkdir()
    monkeypatch.setattr(pv, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(pv, "_manuscript_dir_for", lambda corpus: md)
    live = tmp_path / "main.tex"
    live.write_text("original", encoding="utf-8")

    for i in range(40):                      # > the 32-bound: the earliest 8 prune
        pv.bank_editor_save(md, live, f"v{i}".encode(), author="a", surface="editor")

    idx = pv._load_saves_index(md)
    dropped_id = idx["dropped"][0]["version_id"]

    out = pv.restore_editor_save("corpus", str(live), dropped_id)
    assert out["status"] == 404
    assert str(pv._EDITOR_SAVES_KEEP) in out["error"], out["error"]
    assert "dropped" in out["error"].lower(), out["error"]
    assert out["dropped"]["version_id"] == dropped_id

    never = pv.restore_editor_save("corpus", str(live), "save-never-existed-0")
    assert never["status"] == 404
    assert "dropped" not in never
    assert "no banked save" in never["error"], never["error"]
    assert never["error"] != out["error"], "the two 404s are textually distinct"
