"""test_bench_leakage.py - THE TUNING-LEAKAGE TRIPWIRE (Phase 2 control).

The rule, from design §6: no frozen must-atom may appear in atlas source. An answer sitting in
the code that produces the answers is how a benchmark quietly tunes itself, and it is invisible
in every summary because the leak is upstream of every number.

The tripwire walks every frozen bundle under ``atlas/bench/tasks/`` and every ``.py`` file under
``src/atlas``, and fails on any atom of four characters or more that appears in source.

FOUR CHARACTERS IS THE THRESHOLD AND IT HAS A CONSEQUENCE, stated because the consequence is the
interesting part: an atom that is a bare common word ('record', 'engine', 'graph') collides with
ordinary source prose and fires this tripwire. That is not a false positive to be tuned away - it
means the ATOM is not a distinctive string, and an atom that is not distinctive is not evidence
that an arm found the right passage. The v1 task T11 carried five such atoms; the Phase 2
re-derivation replaced them, and its ``re_derived_from`` record says exactly this. The rule stays
strict and the tasks are what move.

Atoms of three characters or fewer are exempt (a task may legitimately need a fork id like 'f23'
or a bare count); the exemption is declared here rather than discovered.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atlas.bench.scoring import flatten_atoms

ATLAS_ROOT = Path(__file__).resolve().parents[1]
ATLAS_SRC = ATLAS_ROOT.parent / "src" / "atlas"   # the source home since R2
TASKS_DIR = ATLAS_ROOT / "bench" / "tasks"

#: Atoms shorter than this are exempt: they cannot carry an answer on their own.
MIN_ATOM_LEN = 4


def frozen_bundles() -> list[Path]:
    return sorted(TASKS_DIR.glob("*/tasks.json"))


def source_files() -> list[Path]:
    return sorted(ATLAS_SRC.rglob("*.py"))


def test_there_is_at_least_one_frozen_bundle_to_check():
    assert frozen_bundles(), f"no frozen task bundle under {TASKS_DIR}"


def test_no_frozen_atom_appears_in_atlas_source():
    sources = {p: p.read_text(encoding="utf-8").casefold() for p in source_files()}
    offenders: list[str] = []
    checked = 0
    for bundle_path in frozen_bundles():
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        for task in bundle["tasks"]:
            for atom in flatten_atoms(task["atoms"]):
                if len(atom) < MIN_ATOM_LEN:
                    continue
                checked += 1
                needle = atom.casefold()
                for path, text in sources.items():
                    if needle in text:
                        offenders.append(
                            f"{task['task_id']} atom {atom!r} appears in "
                            f"{path.relative_to(ATLAS_ROOT)}")
    assert checked > 0, "no atoms were checked - the tripwire is not wired to anything"
    assert offenders == [], (
        f"{len(offenders)} frozen answer atom(s) appear in atlas source. Either the source was "
        f"tuned to the bench, or the atom is not a distinctive string and the TASK must be "
        f"re-derived: {offenders[:5]}")


def test_the_tripwire_would_actually_fire():
    """A tripwire that cannot fire is decoration. This proves the comparison works."""
    sources = {Path("fake.py"): "the answer is run the widget sweep, obviously"}
    atom = "run the widget sweep"
    hits = [p for p, t in sources.items() if atom.casefold() in t]
    assert hits, "the substring comparison the tripwire relies on is broken"


def test_predictions_were_registered_beside_every_frozen_bundle():
    """A frozen bundle with no prediction table is a run with no pre-registration."""
    for bundle_path in frozen_bundles():
        pred = bundle_path.parent / "predictions.json"
        assert pred.is_file(), f"no predictions.json beside {bundle_path}"
        data = json.loads(pred.read_text(encoding="utf-8"))
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        assert data["bundle_id"] == bundle["bundle_id"]
        classes = {t["task_class"] for t in bundle["tasks"]}
        assert set(data["per_class"]) == classes, (
            "every class must carry a registered prediction, and no class may be invented after "
            "the fact")
        for cl, row in data["per_class"].items():
            assert row.get("predicted_winner"), cl
            assert row.get("reason"), cl


@pytest.mark.parametrize("bundle_path", frozen_bundles(), ids=lambda p: p.parent.name)
def test_the_prediction_table_is_bound_by_the_freeze_record(bundle_path):
    """The D4 repair: ``freeze.json`` records the hash of the predictions that existed at freeze.

    Being NEXT TO the bundle is not a check - a prediction table edited between the freeze and
    the run would look identical on disk. The hash is deliberately NOT folded into ``bundle_id``:
    the bundle's identity covers the corpus and the ground truth, and folding a prediction table
    into it would retroactively invalidate every id already banked.
    """
    from atlas.ids import hash_bytes

    freeze = bundle_path.parent / "freeze.json"
    assert freeze.is_file(), f"no freeze.json beside {bundle_path}"
    record = json.loads(freeze.read_text(encoding="utf-8"))
    pred = bundle_path.parent / "predictions.json"
    assert record["predictions_sha256"] == hash_bytes(pred.read_bytes()), (
        "the prediction table on disk is not the one registered at freeze time")
    assert record["tasks_sha256"] == hash_bytes(bundle_path.read_bytes())


def test_the_runner_refuses_an_edited_prediction_table(tmp_path):
    """The runner's own check, triggered: an edited table stops the run, it does not annotate it."""
    from atlas.errors import ProtocolViolation
    from atlas.ids import hash_bytes
    from atlas.tools.run_bench import check_predictions_binding

    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    tasks = bundle_dir / "tasks.json"
    tasks.write_text("{}", encoding="utf-8")
    pred = bundle_dir / "predictions.json"
    pred.write_text('{"per_class": {}}\n', encoding="utf-8")
    (bundle_dir / "freeze.json").write_text(
        json.dumps({"predictions_sha256": hash_bytes(pred.read_bytes())}), encoding="utf-8")

    # Intact: the check passes and hands back both hashes, which agree.
    frozen, actual = check_predictions_binding(tasks)
    assert frozen == actual and frozen is not None

    # Edited after the freeze: refused by name, before any run work happens.
    pred.write_text('{"per_class": {"invented-after-the-fact": {}}}\n', encoding="utf-8")
    with pytest.raises(ProtocolViolation) as exc:
        check_predictions_binding(tasks)
    assert exc.value.reason == "bench-protocol-violation"
    assert "not the one registered at freeze time" in exc.value.message


def test_a_bundle_with_no_prediction_table_is_not_an_error(tmp_path):
    """Absence is legitimate; disagreement is not. The check distinguishes them."""
    from atlas.tools.run_bench import check_predictions_binding

    bundle_dir = tmp_path / "bare"
    bundle_dir.mkdir()
    tasks = bundle_dir / "tasks.json"
    tasks.write_text("{}", encoding="utf-8")
    assert check_predictions_binding(tasks) == (None, None)


@pytest.mark.parametrize("bundle_path", frozen_bundles(), ids=lambda p: p.parent.name)
def test_every_frozen_bundle_has_seven_classes_of_three(bundle_path):
    """The seven-classes-of-three law is the phase-3 bench universe's law. A bundle frozen under
    another declared sampling kind (a hand-authored SEED bundle, or the random-query instrument's
    draw, 2026-09-14) carries its own law and must say so in freeze.json so it can never be quoted
    as the bench: kind named, random_query_instrument stated. Found red by the cold verbs
    instrument when blk2-B's seed bundle entered atlas/bench/tasks (FIND-20260914-the-seed-bundle-
    turned-the-leakage-test-red-at-head)."""
    freeze_path = bundle_path.parent / "freeze.json"
    sampling = {}
    if freeze_path.is_file():
        sampling = json.loads(freeze_path.read_text(encoding="utf-8")).get("sampling") or {}
    kind = sampling.get("kind")
    if kind in ("seed", "random-query"):
        assert "random_query_instrument" in sampling, (
            f"{bundle_path.parent.name}: a {kind} bundle must state random_query_instrument")
        assert sampling["random_query_instrument"] is (kind == "random-query"), (
            f"{bundle_path.parent.name}: a {kind} bundle mislabels itself as the instrument")
        return
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    counts: dict[str, int] = {}
    for task in bundle["tasks"]:
        counts[task["task_class"]] = counts.get(task["task_class"], 0) + 1
    assert len(counts) == 7, counts
    assert set(counts.values()) == {3}, counts


@pytest.mark.parametrize("bundle_path", frozen_bundles(), ids=lambda p: p.parent.name)
def test_every_re_derived_task_records_what_it_replaced(bundle_path):
    """A re-derivation is a visible diff or it is a silent substitution."""
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    for task in bundle["tasks"]:
        if task.get("re_derived"):
            record = task.get("re_derived_from")
            assert record, task["task_id"]
            assert "why" in record and record["why"], task["task_id"]
            assert "v1_task" in record and "v1_atoms" in record, task["task_id"]
