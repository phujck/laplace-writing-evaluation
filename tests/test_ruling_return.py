"""THE TASTE FLYWHEEL'S RETURN LEG — his banked rulings read back into the frames.

The forward leg was always real (a fork is framed, a judge rules, the ruling is banked
append-only to ``proxy_verdicts.jsonl``). The return leg was dead: nothing read a banked
ruling back into the frame of the NEXT piece of work, while ``gap_ledger``'s ranking
docstring named "then his PRIOR RULINGS" and no caller ever passed one.

These tests prove the leg, at its three ends:

* :mod:`laplace.engine.ruling_recall` returns TYPED ROWS (id / date / ruling / ref), never a
  prose paraphrase, and never a retired ruling;
* a frame assembled where rulings bear CARRIES them
  (:func:`author_proxy.assemble_decision_frame`, and the builder packet's
  ``STANDING-RULINGS`` fence);
* a frame assembled where none bear SAYS SO — the honest absence rides in the packet
  with the ledger it was read against. No silent empty at either end.

Hermetic: every test builds its own ledger in a tmp tree. No model, no network, no
embedding — the leg is deliberately dependency-light and the tests hold it to that.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.engine import author_proxy, ruling_recall


# --------------------------------------------------------------------------- fixtures
def _ruling(rid: str, question: str, ruling: str, *, date: str = "2026-07-20",
            kind: str = "fork-adjudication", supersedes: list | None = None,
            contested=None, confidence: str = "HIGH") -> dict:
    return {
        "id": rid, "date": date, "kind": kind, "question": question, "ruling": ruling,
        "evidence": [], "confidence": confidence, "supersedes": supersedes or [],
        "unlocks": "", "contested": contested,
    }


def _bank(root: Path, rows: list[dict]) -> None:
    (root / author_proxy.LEDGER_NAME).write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    """A small ledger whose rulings speak two clearly separated subjects, so relevance
    is decidable by reading rather than by trusting the scorer."""
    _bank(tmp_path, [
        _ruling("PV-20260701T000000Z-appendix-derivations",
                "Where do explicit derivations belong in a manuscript?",
                "Derivations belong explicitly in appendices; the body carries the "
                "argument and the appendix carries the derivation.",
                date="2026-07-01", kind="author-taste"),
        _ruling("PV-20260702T000000Z-compression-citation",
                "When may a derivation step be compressed?",
                "Compression of a derivation step is licensed only by an apposite "
                "citation that genuinely carries the step.",
                date="2026-07-02"),
        _ruling("PV-20260703T000000Z-turbine-blade-alloy",
                "Which alloy for the turbine blade coating experiment?",
                "Use the nickel superalloy coating; the titanium blade variant "
                "corrodes under the turbine steam loop.",
                date="2026-07-03"),
    ])
    return tmp_path


# --------------------------------------------------------------------------- typed rows
def test_recall_returns_typed_rows_not_prose(ledger: Path):
    """The leg's shape law: what rides back is TYPED ROWS — a ruling id, its date, the
    ruling itself, and the source ref a reader descends. A paraphrase would be the
    engine speaking for him; a row is his call with its handle attached."""
    out = ruling_recall.recall(
        ledger, "Should the explicit derivation for this section be compressed "
                "inline, or moved to the appendix?")

    assert out["rows"], "his rulings on derivations must be recalled for this context"
    for row in out["rows"]:
        assert set(row) >= {"id", "date", "kind", "ruling", "ref", "score"}
        assert row["id"].startswith("PV-")
        assert row["ref"] == f"{ruling_recall.LEDGER_NAME}#{row['id']}"
        assert row["date"]
        assert row["ruling"].strip()

    ids = [r["id"] for r in out["rows"]]
    assert "PV-20260701T000000Z-appendix-derivations" in ids
    assert "PV-20260702T000000Z-compression-citation" in ids
    # the unrelated subject is not dragged in by house vocabulary alone
    assert "PV-20260703T000000Z-turbine-blade-alloy" not in ids


def test_recall_provenance_always_states_what_was_scanned(ledger: Path):
    """No silent empty, in either direction: every recall reports the ledger it read,
    how much was live, how much was retired, and the heuristic that chose."""
    for context in ("derivations and appendices", "no subject in this ledger at all"):
        p = ruling_recall.recall(ledger, context)["provenance"]
        assert p["ledger"] == ruling_recall.LEDGER_NAME
        assert p["heuristic"] == ruling_recall.HEURISTIC
        assert p["scanned"] == 3
        assert p["live"] == 3
        assert p["retired"] == 0
        assert "matched" in p and "returned" in p


def test_recall_is_deterministic_and_capped(ledger: Path):
    """Two calls, byte-identical rows — the leg carries no model and no randomness, so
    a frame assembled twice is the same frame."""
    ctx = "derivation compression citation appendix"
    a = ruling_recall.recall(ledger, ctx, cap=2)
    b = ruling_recall.recall(ledger, ctx, cap=2)
    assert a == b
    assert len(a["rows"]) <= 2


# --------------------------------------------------------------------------- the live law
def test_a_superseded_ruling_never_steers(tmp_path: Path):
    """Correction is retrospective through the ledger (the proxy's own law), so the READ
    side must honour it. A ruling a later ruling supersedes is dead and must not appear
    in any frame — otherwise a retracted call keeps steering work forever."""
    _bank(tmp_path, [
        _ruling("PV-20260701T000000Z-old-appendix-call",
                "Where do derivations belong?",
                "Derivations belong inline in the body, never in an appendix.",
                date="2026-07-01"),
        _ruling("PV-20260705T000000Z-new-appendix-call",
                "Where do derivations belong?",
                "Derivations belong explicitly in appendices; the body carries the "
                "argument.",
                date="2026-07-05",
                supersedes=["PV-20260701T000000Z-old-appendix-call"]),
    ])
    out = ruling_recall.recall(tmp_path, "where do the derivations belong, body or "
                                         "appendix")
    ids = [r["id"] for r in out["rows"]]
    assert "PV-20260705T000000Z-new-appendix-call" in ids
    assert "PV-20260701T000000Z-old-appendix-call" not in ids
    assert out["provenance"]["retired"] == 1


def test_a_contested_ruling_never_steers(tmp_path: Path):
    """The same law through the other door: a ``kind:"contest"`` record retires its
    target, and a row whose own ``contested`` field is set retires itself."""
    _bank(tmp_path, [
        _ruling("PV-20260701T000000Z-contested-by-record",
                "Should the derivation appendix be cut?",
                "Cut the derivation appendix entirely.", date="2026-07-01"),
        _ruling("PV-20260702T000000Z-contested-in-place",
                "Should the derivation appendix be cut?",
                "Cut the derivation appendix entirely, second call.",
                date="2026-07-02", contested="he disagreed at the desk"),
        {"id": "PV-20260703T000000Z-contest-1", "kind": "contest", "date": "2026-07-03",
         "contests": "PV-20260701T000000Z-contested-by-record", "reason": "no",
         "by": "author"},
    ])
    out = ruling_recall.recall(tmp_path, "should the derivation appendix be cut")
    assert out["rows"] == []
    assert out["provenance"]["retired"] == 2


def test_live_rulings_can_be_narrowed_to_the_adjudicator_lanes(ledger: Path):
    """The fork/growth lanes are addressable on their own — the arming's literal ask
    ("wire FORK-RULINGS into the proxy frame") is a filter this leg supports."""
    forks = ruling_recall.live_rulings(ledger, kinds=("fork-adjudication",))
    assert {r["id"] for r in forks} == {
        "PV-20260702T000000Z-compression-citation",
        "PV-20260703T000000Z-turbine-blade-alloy"}
    assert all(r["kind"] == "fork-adjudication" for r in forks)


# --------------------------------------------------------------------------- the proxy frame
def test_proxy_frame_carries_the_recalled_rulings(ledger: Path):
    """The decision frame a dispatched judge consumes now carries the RECALLED slice
    beside the flat ledger dump — ranked, typed, with its provenance."""
    frame = author_proxy.assemble_decision_frame(
        ledger, "Should this section's derivation be compressed or moved to an appendix?")

    assert "relevant_rulings" in frame
    assert "relevant_rulings_provenance" in frame
    ids = [r["id"] for r in frame["relevant_rulings"]]
    assert "PV-20260701T000000Z-appendix-derivations" in ids
    # the flat dump is still there for the callers that audit the whole ledger
    assert len(frame["prior_verdicts"]) == 3


def test_proxy_frame_with_no_relevant_ruling_says_so(ledger: Path):
    """The honest-absence half: a question his ledger is silent on carries an EMPTY
    recall whose provenance still names what was scanned. A judge can tell 'he has
    ruled nothing here' from 'nobody looked'."""
    frame = author_proxy.assemble_decision_frame(
        ledger, "Which hexadecimal palette should the sparkline widget use?")

    assert frame["relevant_rulings"] == []
    p = frame["relevant_rulings_provenance"]
    assert p["scanned"] == 3 and p["live"] == 3
    assert p["heuristic"] == ruling_recall.HEURISTIC


# --------------------------------------------------------------------------- the fence
def test_rendered_fence_carries_rows_when_rulings_bear(ledger: Path):
    """The builder-facing render: typed rows as JSON, each with its ref."""
    out = ruling_recall.recall(
        ledger, "Should the explicit derivation be compressed inline or moved to "
                "the appendix?")
    text = ruling_recall.render_rows(out, "WHAT HE HAS RULED")
    assert "WHAT HE HAS RULED" in text
    payload = json.loads(text[text.index("{"):])
    assert payload["rulings"] and payload["provenance"]["heuristic"] == ruling_recall.HEURISTIC
    assert all(r["ref"].startswith(ruling_recall.LEDGER_NAME) for r in payload["rulings"])


def test_rendered_fence_states_the_absence_rather_than_going_quiet(ledger: Path):
    """The anti-overclaim clause, in the one place it is read: when nothing matches the
    fence still says NONE and names the ledger and heuristic it read. A builder is never
    left to infer that a silent channel means an unconsulted one."""
    out = ruling_recall.recall(ledger, "hexadecimal palette for the sparkline widget")
    text = ruling_recall.render_rows(out, "WHAT HE HAS RULED")
    assert "NONE" in text
    assert ruling_recall.LEDGER_NAME in text
    assert ruling_recall.HEURISTIC in text
    assert "truthful absence" in text


# --------------------------------------------------------------------------- the gap boost
def test_rulings_boost_is_bounded_and_keyed(ledger: Path):
    """``gap_ledger.rank_gaps``'s third ranking term, finally supplied. The boost is
    bounded by MAX_BOOST so it re-orders within a spine tier and can never invert the
    spine law, and it is keyed by the caller's own key."""
    boost = ruling_recall.rulings_boost(ledger, {
        "GAP-derivation": "the derivation step was compressed without a citation",
        "GAP-turbine": "the turbine blade alloy coating claim lost its support",
    })
    assert set(boost) <= {"GAP-derivation", "GAP-turbine"}
    assert boost, "his rulings speak to both of these subjects"
    assert all(0.0 <= v <= ruling_recall.MAX_BOOST for v in boost.values())


def test_rulings_boost_is_empty_when_nothing_bears(ledger: Path):
    """An empty map is a real reading — no live ruling names this subject — not a
    uniform nudge that pretends to consult him."""
    assert ruling_recall.rulings_boost(
        ledger, {"GAP-widget": "hexadecimal palette sparkline widget"}) == {}


def test_gap_ledger_accepts_the_boost_and_reorders_within_the_tier():
    """The wire proved at its far end: the boost re-orders equally-severe gaps, and
    never lifts an off-spine gap above a spine-critical one."""
    from laplace.pipeline import gap_ledger as GL

    gaps = [
        GL.Gap(id="GAP-a", gap_class="ungrounded", where="s1", section="s1",
               kind="source-argument-lost", issue="x", severity=0.5),
        GL.Gap(id="GAP-b", gap_class="ungrounded", where="s2", section="s2",
               kind="source-argument-lost", issue="y", severity=0.5),
        GL.Gap(id="GAP-spine", gap_class="thin", where="s3", section="s3",
               kind="source-argument-lost", issue="z", severity=0.1,
               spine_critical=True),
    ]
    ranked = GL.rank_gaps(gaps, {"GAP-b": ruling_recall.MAX_BOOST})
    assert [g.id for g in ranked] == ["GAP-spine", "GAP-b", "GAP-a"]


def test_string_supersedes_is_one_id_never_characters(tmp_path):
    """The census's worst finding pinned: a bare-string supersedes (the shape half the
    live store carries) must retire one id, not shed characters into the dead set."""
    import json
    from laplace.engine import ruling_recall
    store = tmp_path / "proxy_verdicts.jsonl"
    rows = [
        {"id": "PV-20260801T000000Z-alpha-ruling", "ruling": "the first call", "supersedes": []},
        {"id": "PV-20260802T000000Z-beta-ruling", "ruling": "the second call",
         "supersedes": "PV-20260801T000000Z-alpha-ruling"},
        {"id": "PV-20260803T000000Z-gamma-ruling", "ruling": "the third call", "supersedes": ""},
    ]
    store.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    live = ruling_recall.live_rulings(tmp_path)
    ids = {r["id"] for r in live}
    assert "PV-20260801T000000Z-alpha-ruling" not in ids   # genuinely superseded
    assert "PV-20260802T000000Z-beta-ruling" in ids        # never char-poisoned
    assert "PV-20260803T000000Z-gamma-ruling" in ids       # empty string retires nothing
