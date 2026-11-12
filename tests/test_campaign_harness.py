"""The campaign harness's mechanical organs, tested without any model in the loop."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from campaign.harness.arms import MockArm
from campaign.harness.coverage import run_coverage
from campaign.harness.economics import crossover_k, cumulative_curve
from campaign.harness.grading import make_blind_bundle, unblind
from campaign.harness.manifest import build_manifest, verify
from campaign.harness.meter import Meter, MeterError
from campaign.harness.questions import contamination_check, load_questions, seal


def _write_questions(tmp_path):
    qf = tmp_path / "questions.jsonl"
    rows = [
        {"id": "q1", "text": "Which three transcripts discuss the admission control design decision?",
         "ground_truth": "t1,t4,t9", "class": "join"},
        {"id": "q2", "text": "What did the second interviewee conclude about dosage thresholds overall?",
         "ground_truth": "raise", "class": "join"},
    ]
    qf.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return qf, rows


def test_meter_refuses_estimated_tokens(tmp_path):
    m = Meter(tmp_path / "meter.jsonl", "run-1")
    with pytest.raises(MeterError):
        m.record(arm="A", question_id="q1", tokens_in=None, tokens_out=5, latency_ms=1)
    m.record(arm="A", question_id="q1", tokens_in=10, tokens_out=5, latency_ms=1,
             cost_gbp=0.01)
    assert len(m.rows("A")) == 1 and m.rows("B") == []


def test_question_seal_and_contamination(tmp_path):
    qf, rows = _write_questions(tmp_path)
    qs = load_questions(qf)
    digest = seal(qf)
    assert len(digest) == 64
    clean_root = tmp_path / "fold"
    clean_root.mkdir()
    (clean_root / "doc.md").write_text("nothing to see", encoding="utf-8")
    assert contamination_check(qs, clean_root) == []
    (clean_root / "leak.md").write_text(rows[0]["text"], encoding="utf-8")
    hits = contamination_check(qs, clean_root)
    assert hits and hits[0]["question_id"] == "q1"


def test_coverage_math():
    rep = run_coverage(["u1", "u2", "u3", "u4"], probe=lambda u: u != "u3")
    assert rep["total"] == 4 and rep["passed"] == 3
    assert rep["failed_units"] == ["u3"]
    assert abs(rep["coverage"] - 0.75) < 1e-9


def test_crossover():
    # A pays 1.0/query; B pays 10 up front then 0.1/query -> crossover at k=11
    rows_a = [{"question_id": f"q{i}", "cost_gbp": 1.0} for i in range(20)]
    rows_b = [{"question_id": f"q{i}", "cost_gbp": 0.1} for i in range(20)]
    a = cumulative_curve(rows_a)
    b = cumulative_curve(rows_b, fold_cost=10.0)
    assert crossover_k(a, b) == 12  # 12*1.0=12.0 >= 10+12*0.1=11.2; at k=11: 11.0 < 11.1
    assert crossover_k(a, cumulative_curve(rows_b, fold_cost=1000.0)) is None


def test_blind_bundle_strips_and_unblinds(tmp_path):
    answers = [{"question_id": f"q{i}", "arm": "A" if i % 2 else "B",
                "answer_text": f"ans{i}"} for i in range(6)]
    bundle_p, key_p = tmp_path / "bundle.jsonl", tmp_path / "key.jsonl"
    make_blind_bundle(answers, seed=7, bundle_path=bundle_p, key_path=key_p)
    bundle = [json.loads(l) for l in bundle_p.read_text(encoding="utf-8").splitlines()]
    assert all("arm" not in r for r in bundle)  # labels stripped
    # deterministic shuffle: same seed -> same order
    make_blind_bundle(answers, seed=7, bundle_path=tmp_path / "b2.jsonl",
                      key_path=tmp_path / "k2.jsonl")
    assert (tmp_path / "b2.jsonl").read_text(encoding="utf-8") == \
           bundle_p.read_text(encoding="utf-8")
    grades = [{"opaque_id": r["opaque_id"], "score": 1.0} for r in bundle]
    restored = unblind(grades, key_p)
    assert sorted(r["arm"] for r in restored).count("A") == 3


def test_manifest_verify_detects_drift(tmp_path):
    art = tmp_path / "artifact.txt"
    art.write_text("original", encoding="utf-8")
    mp = tmp_path / "manifest.json"
    build_manifest("run-x", [art], mp)
    assert verify(mp) == []
    art.write_text("tampered", encoding="utf-8")
    problems = verify(mp)
    assert problems and problems[0].startswith("DRIFT")


def test_mock_arm_end_to_end_metering(tmp_path):
    """The wiring MockArm exists for: arms -> meter -> curves, no model needed."""
    qf, _ = _write_questions(tmp_path)
    qs = load_questions(qf)
    cheap = MockArm("mock-b", per_query_cost=0.1)
    dear = MockArm("mock-a", per_query_cost=1.0)
    m = Meter(tmp_path / "meter.jsonl", "run-mock")
    for arm in (dear, cheap):
        for q in qs:
            r = arm.run_query(q)
            m.record(arm=arm.name, question_id=q["id"], tokens_in=r["tokens_in"],
                     tokens_out=r["tokens_out"], latency_ms=r["latency_ms"],
                     cost_gbp=r["cost_gbp"])
    a = cumulative_curve(m.rows("mock-a"))
    b = cumulative_curve(m.rows("mock-b"), fold_cost=0.5)
    assert crossover_k(a, b) == 1  # 1.0 >= 0.6 at k=1
