"""The ledger to pool fold (src/laplace/pipeline/writing_organ/pool_fold.py).

What is pinned: his rows fold and machine rows do not; process wrappers, flag stubs and
duplicates are declined and counted; a measurable length change picks a side and
everything else pends; two ledgers sharing one pool never mask each other; the second
fold is a no-op; a verdict carrying characters outside Latin-1 survives the round trip
through the pool file; the panel compiles legacy strings, folded objects and pending
entries alike and stays bounded; and the feedback ledger is byte-identical after every
fold.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from laplace.pipeline.writing_organ import panel, pool_fold  # noqa: E402


LONG_BEFORE = (
    "It is worth noting at this point that the readout, which is sampled at a rate that "
    "the experiment fixes in advance, carries a set of features whose count is itself a "
    "quantity that the budget determines and which therefore cannot move freely."
)
SHORT_AFTER = "At matched budget the feature count never moves."

TERSE_BEFORE = "An added qubit buys time."
BREATHING_AFTER = (
    "An added qubit buys time. Before the next step, note what that means for a reader "
    "coming to this cold: the window the device can integrate over grows, while the "
    "number of numbers it reports does not."
)


def _pool() -> dict:
    """A pool with the real shape: prose provenance string, the real element pairs, one
    legacy string exemplar per relevant side."""
    return {
        "provenance": "the two-sided exemplar pool (hand-written prose).",
        "elements": [
            {"pair": "register", "law": "Physics, all physics."},
            {"pair": "economy_vs_orientation", "law": "Density against breath."},
            {"pair": "precision_vs_force", "law": "Cadence must not outrun content."},
            {"pair": "structure_vs_flow", "law": "The beat order serves reading."},
            {"pair": "part_vs_whole", "law": "The enemy is local optimisation."},
        ],
        "exemplars": {
            "against_emptiness": ["too many empty sentences (2026-08-07)"],
            "against_starvation": ["it doesn't breathe (2026-08-08)"],
        },
        "standing_laws": ["THE ONE-IN-FIVE LAW: at most one sentence in five memorable."],
    }


ROWS = [
    # his cut: after materially shorter -> the compression-favouring side
    {"id": "FB-A-001", "project": "p", "ts": "2026-08-10T09:00:00",
     "source": "gerard:the-walk", "kind": "rewrite", "scope": "sentence",
     "anchor": "sec:intro", "before": LONG_BEFORE, "after": SHORT_AFTER,
     "note": "cash it or cut it"},
    # his breath: after materially longer -> the orientation side
    {"id": "FB-A-002", "project": "p", "ts": "2026-08-10T09:05:00",
     "by": "gerard", "kind": "author-exemplar", "scope": "paragraph",
     "anchor": {"section": "sec:results"}, "before": TERSE_BEFORE,
     "after": BREATHING_AFTER},
    # his comment: no measurable side -> pending
    {"id": "FB-A-003", "project": "p", "ts": "2026-08-10T09:10:00",
     "source": "gerard:first-read", "kind": "comment", "anchor": "whole-artefact",
     "note": "it's hard to feel the through line, the one thing the text embeds in me"},
    # his edit, but too small to carry a direction -> pending
    {"id": "FB-A-004", "project": "p", "ts": "2026-08-10T09:15:00",
     "by": "gerard", "kind": "rewrite", "scope_source": "the schedule is chosen",
     "before": "", "after": "the drive is chosen", "note": "schedule isn't a physics word"},
    # a machine detection -> never folds
    {"id": "FB-M-001", "project": "p", "ts": "2026-08-10T09:20:00",
     "source": "mech-panel:round3:meta_leak", "kind": "meta-leak",
     "text": "construction vocabulary surfaced in prose", "status": "open"},
    # a visitor -> not the author, never folds
    {"id": "FB-V-001", "project": "p", "ts": "2026-08-10T09:25:00",
     "by": "visitor:sam", "kind": "comment", "comment": "I found this section hard"},
]


@pytest.fixture()
def bench(tmp_path: Path):
    led = tmp_path / "manuscript" / "feedback" / "feedback.jsonl"
    led.parent.mkdir(parents=True)
    led.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ROWS),
                   encoding="utf-8")
    pool_path = tmp_path / "calibration_pool.json"
    pool_path.write_text(json.dumps(_pool(), ensure_ascii=False, indent=1),
                         encoding="utf-8")
    return led, pool_path


def _read(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ the first fold


def test_first_fold_places_pends_and_records_provenance(bench):
    led, pool_path = bench
    r = pool_fold.fold(led, pool_path)

    assert r["ok"] is True
    assert r["folded"] == 4          # four author rows; machine and visitor excluded
    assert r["placed"] == 2
    assert r["pending"] == 2
    assert r["position"] == "2026-08-10T09:15:00"   # the newest row folded, not scanned

    pool = _read(pool_path)
    shorter = pool["exemplars"]["against_emptiness"]
    longer = pool["exemplars"]["against_starvation"]
    assert len(shorter) == 2 and len(longer) == 2          # legacy string kept + one folded
    assert shorter[0] == "too many empty sentences (2026-08-07)"
    assert shorter[1]["from"] == ["FB-A-001"]
    assert shorter[1]["ts"] == "2026-08-10T09:00:00"
    assert SHORT_AFTER in shorter[1]["text"] and "cash it or cut it" in shorter[1]["text"]
    assert longer[1]["from"] == ["FB-A-002"]
    assert "sec:results" in longer[1]["text"]

    pending = pool["pending_exemplars"]
    assert [e["from"][0] for e in pending] == ["FB-A-003", "FB-A-004"]
    assert "through line" in pending[0]["text"]
    # the small edit keeps his quote and his replacement verbatim
    assert "the schedule is chosen" in pending[1]["text"]
    assert "the drive is chosen" in pending[1]["text"]

    prov = pool["provenance"]
    assert prov["note"].startswith("the two-sided exemplar pool")   # his prose survives
    assert len(prov["folds"]) == 1
    fold_rec = prov["folds"][0]
    assert fold_rec["rows"] == 4
    assert fold_rec["max_row_ts"] == "2026-08-10T09:15:00"
    assert fold_rec["row_ids"] == ["FB-A-001", "FB-A-002", "FB-A-003", "FB-A-004"]
    # the ledger is identified by its path, never by a file name every project shares
    assert fold_rec["ledger"] == pool_fold.ledger_id(led) != "feedback.jsonl"
    assert shorter[1]["ledger"] == fold_rec["ledger"]


def test_machine_and_visitor_rows_never_fold(bench):
    led, pool_path = bench
    pool_fold.fold(led, pool_path)
    blob = pool_path.read_text(encoding="utf-8")
    assert "FB-M-001" not in blob and "FB-V-001" not in blob
    assert "construction vocabulary" not in blob
    assert pool_fold.is_author_row(ROWS[4]) is False
    assert pool_fold.is_author_row(ROWS[5]) is False
    # the relay form he writes in the real ledger is still his
    assert pool_fold.is_author_row({"source": "barry-via-gerard (row 8; he endorses:)"})


# ------------------------------------------------------------------ idempotence


def test_second_fold_is_a_no_op(bench):
    led, pool_path = bench
    pool_fold.fold(led, pool_path)
    first = pool_path.read_bytes()

    again = pool_fold.fold(led, pool_path)
    assert again["ok"] is True
    assert (again["folded"], again["placed"], again["pending"]) == (0, 0, 0)
    assert again["position"] == "2026-08-10T09:15:00"
    assert pool_path.read_bytes() == first        # nothing rewritten, nothing appended


def test_a_new_row_folds_and_leaves_the_folded_ones_alone(bench):
    led, pool_path = bench
    pool_fold.fold(led, pool_path)
    before_entries = _read(pool_path)["exemplars"]["against_emptiness"]

    with led.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "FB-A-005", "ts": "2026-08-10T10:00:00",
                             "source": "gerard:the-walk", "kind": "comment",
                             "note": "the abstract still apologises for a proved claim"},
                            ensure_ascii=False) + "\n")
    r = pool_fold.fold(led, pool_path)
    assert (r["folded"], r["placed"], r["pending"]) == (1, 0, 1)

    pool = _read(pool_path)
    assert pool["exemplars"]["against_emptiness"] == before_entries   # append-only
    assert [e["from"][0] for e in pool["pending_exemplars"]][-1] == "FB-A-005"
    assert len(pool["provenance"]["folds"]) == 2


def test_two_ledgers_sharing_one_pool_do_not_mask_each_other(tmp_path):
    """Every project's ledger is named feedback.jsonl and they all fold into the one
    pool. The older project must still fold after the newer one has - the failure this
    pins is folding project A and permanently losing every unfolded row of project B
    whose timestamp runs behind A's newest."""
    def _ledger(name: str, rows: list[dict]) -> Path:
        p = tmp_path / name / "manuscript" / "feedback" / "feedback.jsonl"
        p.parent.mkdir(parents=True)
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                     encoding="utf-8")
        return p

    a = _ledger("paper_a", [{"id": "A1", "by": "gerard", "ts": "2026-08-10T11:00:00",
                             "note": "paper A: the padding round the theorem has to go"}])
    b = _ledger("paper_b", [{"id": "B1", "by": "gerard", "ts": "2026-08-10T10:00:00",
                             "note": "paper B: this section does not breathe at all"}])
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(json.dumps(_pool(), ensure_ascii=False), encoding="utf-8")

    assert pool_fold.fold(a, pool_path)["folded"] == 1
    rb = pool_fold.fold(b, pool_path)
    assert rb["folded"] == 1                       # the older project still folds
    texts = [e["text"] for e in _read(pool_path)["pending_exemplars"]]
    assert any("paper A" in t for t in texts) and any("paper B" in t for t in texts)

    # and each ledger keeps its own position, so neither re-folds
    assert pool_fold.fold(a, pool_path)["folded"] == 0
    assert pool_fold.fold(b, pool_path)["folded"] == 0
    ledgers = [f["ledger"] for f in _read(pool_path)["provenance"]["folds"]]
    assert len(set(ledgers)) == 2


# ------------------------------------------------------------------ the encoding

def test_a_verdict_outside_latin1_survives_into_the_panel(tmp_path):
    """The fold writes UTF-8; the panel must read UTF-8. One character outside the
    platform default encoding otherwise mojibakes every folded verdict, or raises and
    takes the whole tension panel down with it."""
    led = tmp_path / "feedback" / "feedback.jsonl"
    led.parent.mkdir(parents=True)
    led.write_text(json.dumps(
        {"id": "X1", "by": "gerard", "ts": "2026-08-10T09:00:00",
         "note": "the Tōhoku citation reads as eponymy - name the result, not the man"},
        ensure_ascii=False) + "\n", encoding="utf-8")
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(json.dumps(_pool(), ensure_ascii=False), encoding="utf-8")

    assert pool_fold.fold(led, pool_path)["folded"] == 1
    pool = panel.load_pool(pool_path)                     # reads the file, not a dict
    assert "Tōhoku" in pool["pending_exemplars"][0]["text"]
    assert "Tōhoku" in panel.compile_panel("PROSE", pool=pool)


def test_missing_ledger_is_named_not_silent(tmp_path):
    r = pool_fold.fold(tmp_path, tmp_path / "nope.json")
    assert r["ok"] is False and "no feedback ledger" in r["error"]


def test_a_manuscript_directory_resolves_to_its_ledger(bench):
    led, pool_path = bench
    r = pool_fold.fold(led.parent.parent, pool_path)     # the manuscript dir
    assert r["ok"] is True and r["folded"] == 4
    assert Path(r["ledger"]) == led


# ------------------------------------------------------------------ the ledger is read-only


def test_the_feedback_ledger_is_untouched_byte_for_byte(bench):
    led, pool_path = bench
    original = led.read_bytes()
    pool_fold.fold(led, pool_path)
    pool_fold.fold(led, pool_path)
    assert led.read_bytes() == original


# ------------------------------------------------------------------ the panel compile


def test_panel_renders_strings_objects_and_pending(bench):
    led, pool_path = bench
    pool_fold.fold(led, pool_path)
    pool = _read(pool_path)

    prompt = panel.compile_panel("SOME PROSE", pool=pool)
    assert "[against_emptiness] too many empty sentences (2026-08-07)" in prompt  # legacy
    folded = pool["exemplars"]["against_emptiness"][1]["text"]
    assert f"[against_emptiness] {panel._excerpt(folded)}" in prompt   # folded, bounded
    assert SHORT_AFTER in prompt                       # his replacement survives the cut
    assert f"[{panel.UNPLACED_TAG}] " in prompt
    assert "through line" in prompt                       # the pending verdict is visible
    assert "SOME PROSE" in prompt
    assert "{'text'" not in prompt and '"text"' not in prompt   # objects render as words


def test_panel_still_compiles_a_pool_with_no_pending_key():
    prompt = panel.compile_panel("PROSE", pool=_pool())
    assert panel.UNPLACED_TAG not in prompt
    assert "[against_starvation] it doesn't breathe (2026-08-08)" in prompt


def test_the_shipped_pool_still_compiles():
    """The live calibration_pool.json compiles through the widened reader unchanged."""
    prompt = panel.compile_panel("PROSE")
    assert "THE ELEMENTS IN TENSION" in prompt and "PROSE" in prompt


# ------------------------------------------------------------------ the placement rule


@pytest.mark.parametrize("before,after,expected", [
    (LONG_BEFORE, SHORT_AFTER, pool_fold.SIDE_SHORTER),
    (TERSE_BEFORE, BREATHING_AFTER, pool_fold.SIDE_LONGER),
    ("the schedule is chosen", "the drive is chosen", None),      # too small a delta
    (LONG_BEFORE, "", pool_fold.SIDE_SHORTER),                    # an outright cut
])
def test_place_side_rule(before, after, expected):
    assert pool_fold.place_side(
        {"kind": "rewrite", "before": before, "after": after}) == expected


def test_a_quoted_passage_without_a_replacement_is_not_a_deletion():
    """scope_source carries the passage a comment sits on; with no after field the row
    is a comment, never a cut."""
    rec = {"kind": "comment", "scope_source": LONG_BEFORE, "note": "this reads composed"}
    assert pool_fold.place_side(rec) is None
    assert pool_fold.has_substance(rec) is True


def test_his_bookkeeping_records_are_not_judgement(bench):
    """Deferrals, ratified operations and intent revokes carry his actor but
    machine-composed process language. An author-edit is his rewrite and still folds."""
    led, pool_path = bench
    assert pool_fold.has_substance(
        {"record": "ratified-operation", "source": "gerard",
         "text": "applied RESPINE meta:contribution_rank via set-meta"}) is False
    assert pool_fold.has_substance(
        {"record": "defer", "source": "gerard", "text": "deferred finding 'CI-1'"}) is False
    assert pool_fold.has_substance(
        {"record": "author-edit", "by": "gerard", "before": LONG_BEFORE,
         "after": SHORT_AFTER}) is True

    with led.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"id": "ROP-1", "record": "ratified-operation",
                             "ts": "2026-08-10T11:00:00", "source": "gerard",
                             "text": "applied RESPINE via set-meta"}) + "\n")
    r = pool_fold.fold(led, pool_path)
    assert r["folded"] == 4                      # the four judgement rows, not the ROP
    assert "ROP-1" not in pool_path.read_text(encoding="utf-8")


WRAPPER_NOTE = (
    "HIS READ OF R2, VERBATIM: 'despite everything that's been done has produced a "
    "genuinely unreadable article.' CONFIRMED by the orchestrator's own first-chair read "
    "(evidence/FIRST_CHAIR_2026-07-21_r2-read.md): provenance meta-commentary written "
    "into prose at every number."
)
STUB_NOTE = "reader flag · ¶ s1-p4"


def test_process_records_and_flag_stubs_are_not_his_verdict():
    """Three shapes carry his actor without carrying a judgement about the text: a kind
    that records an interaction, the orchestrator's wrapper around a quote of his, and
    the review surface's flag text with nothing typed into it."""
    assert pool_fold.decline_reason(
        {"kind": "ratification-grant", "by": "gerard",
         "note": "Scope: the open projection-intents"}) == "process-kind"
    assert pool_fold.decline_reason(
        {"kind": "note", "by": "gerard", "note": WRAPPER_NOTE}) == "wrapper"
    assert pool_fold.decline_reason(
        {"kind": "note", "by": "gerard", "comment": STUB_NOTE,
         "anchor": {"section": "s1", "paragraph": "s1-p4"}}) == "stub"
    # his own terse verdicts still read as judgement when they carry a sentence
    assert pool_fold.decline_reason(
        {"by": "gerard", "note": "figure metrics belong in captions, not the text"}) is None
    # and a rewrite of two words is still a rewrite, whatever its note says
    assert pool_fold.decline_reason(
        {"by": "gerard", "before": "the schedule", "after": "the drive"}) is None


def test_declined_rows_are_counted_not_silently_dropped(bench):
    led, pool_path = bench
    with led.open("a", encoding="utf-8") as fh:
        for r in ({"id": "FB-A-006", "ts": "2026-08-10T12:00:00", "by": "gerard",
                   "kind": "author-read", "note": WRAPPER_NOTE},
                  {"id": "FB-A-007", "ts": "2026-08-10T12:01:00", "by": "gerard",
                   "kind": "note", "comment": STUB_NOTE}):
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    r = pool_fold.fold(led, pool_path)
    assert r["folded"] == 4                       # the same four judgement rows
    assert r["skipped"] == {"process-kind": 1, "stub": 1}
    blob = pool_path.read_text(encoding="utf-8")
    assert "reader flag" not in blob and "VERBATIM" not in blob


def test_the_same_verdict_logged_twice_folds_once(bench):
    """A flag raised on the same paragraph on two days is one sample of his judgement."""
    led, pool_path = bench
    twice = {"ts": "2026-08-10T13:00:00", "by": "gerard", "kind": "comment",
             "anchor": "abstract",
             "note": "the abstract still apologises for a claim the paper proves"}
    with led.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**twice, "id": "FB-A-008"}, ensure_ascii=False) + "\n")
        fh.write(json.dumps({**twice, "id": "FB-A-009",
                             "ts": "2026-08-10T13:05:00"}, ensure_ascii=False) + "\n")

    r = pool_fold.fold(led, pool_path)
    assert r["folded"] == 5 and r["skipped"].get("duplicate") == 1
    texts = [e["text"] for e in _read(pool_path)["pending_exemplars"]]
    assert sum("still apologises" in t for t in texts) == 1


# ------------------------------------------------------------------ the panel budget


def test_the_panel_stays_bounded_as_the_pool_grows():
    """A folded row can be a page. The curated one-liners must not drown in it: every
    line enters at one width, and only the most recent unplaced verdicts enter at all."""
    p = _pool()
    p["pending_exemplars"] = [
        {"text": f"verdict {i}. " + "this paragraph runs on and on. " * 40,
         "from": [f"R{i}"], "ts": f"2026-08-10T{i:02d}:00:00"}
        for i in range(12)]
    prompt = panel.compile_panel("PROSE", pool=p)

    unplaced = [l for l in prompt.splitlines() if l.startswith(f"[{panel.UNPLACED_TAG}]")]
    assert len(unplaced) == panel.MAX_PENDING           # the most recent, and only those
    assert "verdict 11." in prompt and "verdict 0." not in prompt
    tag = len(f"[{panel.UNPLACED_TAG}] ")
    assert max(len(l) - tag for l in unplaced) <= panel.MAX_EXEMPLAR_CHARS + len(panel.ELISION)
    assert all(panel.ELISION in l for l in unplaced)
    # the curated samples are untouched and still outnumber the unplaced block
    assert "[against_emptiness] too many empty sentences (2026-08-07)" in prompt


def test_placement_pends_when_the_pool_lacks_the_sides(tmp_path):
    """No pool sides, no invented keys: everything pends."""
    led = tmp_path / "feedback" / "feedback.jsonl"
    led.parent.mkdir(parents=True)
    led.write_text(json.dumps(ROWS[0], ensure_ascii=False) + "\n", encoding="utf-8")
    p = _pool()
    p["elements"] = [e for e in p["elements"] if e["pair"] != "economy_vs_orientation"]
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")

    r = pool_fold.fold(led, pool_path)
    assert (r["folded"], r["placed"], r["pending"]) == (1, 0, 1)
    assert len(_read(pool_path)["exemplars"]["against_emptiness"]) == 1   # legacy only
