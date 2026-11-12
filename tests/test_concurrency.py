"""Concurrency safety for canon mutation under multiple agents.

Three agents (Claude, Codex, Gemini-on-Antigravity) may drive the engine at
once. These tests pin the two guarantees that makes safe:

* the canon write lock serialises a critical section *across processes* (not
  just threads), so no mutation clobbers another;
* lifecycle writes are atomic AND the swap window is safe both ways, so the
  lock-free canon loader never sees torn YAML and never crashes on the transient
  Windows os.replace PermissionError/FileNotFoundError;
* a contended lock returns a clean busy result fast, never hangs.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Cross-process serialisation. Real subprocesses (sys.executable -c ...) drive
# the same lock - this sidesteps the multiprocessing/pickling/import-name
# fragility of pytest workers on Windows `spawn`, while genuinely testing the
# cross-process guarantee against the installed package.
# ---------------------------------------------------------------------------
_WORKER = """
import os, sys
state, counter, iters = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.environ["LAPLACE_STATE"] = state
from pathlib import Path
from laplace.pipeline.locking import canon_lock
p = Path(counter)
for _ in range(iters):
    with canon_lock(timeout=120):
        n = int(p.read_text(encoding="utf-8") or "0")
        p.write_text(str(n + 1), encoding="utf-8")
"""


def test_canon_lock_serialises_across_processes(tmp_path):
    """N processes each do a non-atomic read-modify-write under the lock.

    Without mutual exclusion the interleaved increments lose updates and the
    total is < N*M. With the cross-process lock it is exactly N*M.
    """
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    counter = tmp_path / "counter.txt"
    counter.write_text("0", encoding="utf-8")

    n_procs, iters = 4, 25
    procs = [
        subprocess.Popen([sys.executable, "-c", _WORKER, str(state_dir), str(counter), str(iters)])
        for _ in range(n_procs)
    ]
    for p in procs:
        assert p.wait(timeout=180) == 0, "worker process failed"

    assert int(counter.read_text(encoding="utf-8")) == n_procs * iters


# ---------------------------------------------------------------------------
# Atomic lifecycle writes under contention: the PRODUCTION lock-free loader
# (Canon._load_lifecycle), run in a tight loop while writers swap the overlay in
# via os.replace, must never raise and never see invalid YAML. Two failure modes
# are covered at once: a torn read (mid-write content - surfaces as a YAMLError)
# and, on Windows, the transient PermissionError/FileNotFoundError a lock-free
# open hits during the os.replace swap window. Driving the real loader (not a
# bespoke reader) is what makes this prove the production fix, not just test-local
# tolerance: revert the retry in canon._read_text_lockfree and this goes red.
# ---------------------------------------------------------------------------
def test_save_lifecycle_atomic_never_torn(tmp_path, monkeypatch):
    # Production faithful: writers serialise on the canon lock, readers stay
    # lock-free. The atomic os.replace guarantees no torn overlay; the read-side
    # retry guarantees the swap window never crashes a lock-free read.
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import dreamer
    from laplace.pipeline.canon import Canon
    from laplace.pipeline.locking import canon_lock

    canon = SimpleNamespace(root=tmp_path)
    dreamer._save_lifecycle(canon, {"skills": {}})

    stop = threading.Event()
    errors: list[str] = []

    def writer(i: int) -> None:
        # A chunky payload so a torn read would be obvious as a YAML error.
        data = {"skills": {f"s{i}": {"status": "experimental", "history": [{"at": str(k)} for k in range(60)]}}}
        while not stop.is_set():
            with canon_lock(timeout=30):
                dreamer._save_lifecycle(canon, data)

    def reader() -> None:
        # The exact production lock-free read path. A swap churns the canon
        # fingerprint every write, so in production each load re-reads - this tight
        # loop is faithful to constant canon churn, the worst case for the race.
        while not stop.is_set():
            try:
                data = Canon._load_lifecycle(canon.root)
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))  # PermissionError or torn YAML - both are bugs
                return
            if not isinstance(data, dict) or "skills" not in data:
                errors.append(f"bad overlay shape: {data!r}")
                return

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(3)]
    threads += [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    time.sleep(1.0)
    stop.set()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"lock-free reader raised under contention: {errors}"
    assert Canon._load_lifecycle(canon.root)["skills"] is not None


# ---------------------------------------------------------------------------
# The read-side retry mechanism in isolation: deterministic, no timing, so it
# pins the fix independent of whether the threaded race happens to fire on a
# given machine/run. These go red the instant the retry is removed.
# ---------------------------------------------------------------------------
def test_read_text_lockfree_retries_then_succeeds(tmp_path, monkeypatch):
    """A transient PermissionError (the Windows os.replace window) is retried."""
    from laplace.pipeline import canon as canon_mod

    p = tmp_path / "f.txt"
    p.write_text("real-content", encoding="utf-8")

    real_read = Path.read_text
    calls = {"n": 0}

    def flaky(self, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] <= 3:  # three sub-millisecond swap collisions, then it clears
            raise PermissionError(13, "Permission denied")
        return real_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky)
    monkeypatch.setattr(canon_mod.time, "sleep", lambda *_: None)  # no real waiting

    assert canon_mod._read_text_lockfree(p) == "real-content"
    assert calls["n"] == 4  # 3 transient failures, then the successful read


def test_read_text_lockfree_gives_up_on_persistent_error(tmp_path, monkeypatch):
    """A PermissionError that never clears is re-raised (bounded, not a livelock)."""
    from laplace.pipeline import canon as canon_mod

    p = tmp_path / "f.txt"
    p.write_text("real-content", encoding="utf-8")

    def always_fail(self, *args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "read_text", always_fail)
    monkeypatch.setattr(canon_mod.time, "sleep", lambda *_: None)

    with pytest.raises(PermissionError):
        canon_mod._read_text_lockfree(p)


# ---------------------------------------------------------------------------
# A contended lock returns a structured busy result fast, never hangs.
# ---------------------------------------------------------------------------
def test_lock_busy_returns_fast(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path))
    from laplace.pipeline.locking import CanonBusy, canon_lock

    with canon_lock(timeout=5):
        start = time.monotonic()
        raised = False
        try:
            with canon_lock(timeout=0.5):
                pass
        except CanonBusy:
            raised = True
        elapsed = time.monotonic() - start

    assert raised, "second acquisition should have raised CanonBusy"
    assert elapsed < 3.0, f"busy-return took {elapsed:.1f}s, should be ~0.5s"
