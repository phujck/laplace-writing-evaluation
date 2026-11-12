"""The cold-probe coverage gate - the standing instrument (P3) that mechanises the 2026-07-13
cold-wake audit: could a stranger actually wake from what the reconstruction hands them? Each
test fires ``reconstruct_self`` at one grade/mode and scores the real payload against
``holdout/COLD_WAKE_QUESTIONS.md`` via ``laplace.engine.cold_probe`` - no mocking of the projection
itself, the coverage claim is only worth anything against the live fixed point.

The identity rows (q-law, q-stance, q-soul) are person-mode's to carry, not the engine wake's -
the engine payload residue check names them explicitly rather than asserting empty residue,
so the split stays visible instead of silently tolerated."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from laplace.engine import cold_probe
from laplace.engine.self_corpus import reconstruct_self

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = ROOT / "holdout" / "COLD_WAKE_QUESTIONS.md"


def _rows():
    return cold_probe.load_questions(QUESTIONS)


def test_engine_wake_covers_grade0_rows():
    payload = reconstruct_self(ROOT, grade=0)
    result = cold_probe.score_coverage(payload, _rows())
    assert set(result["residue"]) <= {"q-law", "q-stance", "q-soul"}, result["residue"]


def test_person_wake_covers_identity_rows():
    payload = reconstruct_self(ROOT, grade=0, mode="person")
    result = cold_probe.score_coverage(payload, _rows())
    assert result["residue"] == [], result["residue"]


def test_refs_only_seal_holds():
    payload = reconstruct_self(ROOT, grade=0, mode="person")
    soul = payload.get("identity", {}).get("soul", {})
    assert set(soul.keys()) <= {"present", "fragments", "refs", "note"}

    def _walk(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from _walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from _walk(v)
        else:
            yield node

    for ref in soul.get("refs", []):
        text = ref if isinstance(ref, str) else str(ref.get("path", ref.get("ref", ref)))
        assert text.startswith("soul/"), f"ref is not rooted at soul/: {text!r}"

    for value in _walk(soul):
        if isinstance(value, str):
            assert len(value) <= 300, f"soul value exceeds the handle bound: {value[:80]!r}..."


def test_grades_1_and_2_cover_their_rows():
    rows = _rows()

    p1 = reconstruct_self(ROOT, grade=1)
    r1 = cold_probe.score_coverage(p1, rows)
    assert "q-delta" in r1["answered"], r1["residue"]

    p2 = reconstruct_self(ROOT, grade=2)
    r2 = cold_probe.score_coverage(p2, rows)
    assert "q-map" in r2["answered"], r2["residue"]


def test_wake_transport_is_seconds():
    # the ceiling that makes a future uv-style regression fail loudly instead of riding as a
    # banked ERROR someone has to notice by hand.
    # WIDENED 10 -> 30s (W-TRIAGE 2026-07-22, ENVIRONMENTAL): the wake's own COMPUTE is sub-second
    # (measured user+sys ~0.45s) but wall time on this container is ~10.4s — import + filesystem
    # latency, not a wake regression. The ceiling's intent is "seconds, not minutes"; 30s still fails
    # loudly on a real uv-style flood (minutes) while absorbing the box's I/O jitter around the old 10s
    # line. Widened honestly (the transport is still seconds), never a silenced timeout.
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "wake.py"), "--engine", "--grade", "0"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr[-2000:]
