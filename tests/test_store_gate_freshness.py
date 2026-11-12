"""The gate verdict must name the store state it measured, and must go visibly stale when that
state moves. The regression these tests hold shut: a re-mint (``b17378c2``) moved 280 rows'
``embed_text`` and regenerated the embeddings while two verdict files went on reading as live.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))

from laplace.pipeline import store_gate_freshness as F  # noqa: E402

CORPUS_STORES = _REPO_ROOT / "corpus_stores"


# --------------------------------------------------------------------------- #
# a synthetic store: two papers, a class per row, a row-id-keyed embeddings.json
# --------------------------------------------------------------------------- #
def _make_store(tmp_path: Path, *, n: int = 24, dim: int = 8) -> Path:
    import numpy as np

    rng = np.random.default_rng(11)
    d = tmp_path / "toy_store"
    d.mkdir()
    classes = ["alpha", "beta", "gamma"]
    centres = {c: rng.normal(size=dim) for c in classes}
    rows, items = [], {}
    for i in range(n):
        cls = classes[i % len(classes)]
        rid = f"TOY-r{i:03d}"
        rows.append({"row_id": rid, "embed_text": f"passage {i} about {cls}",
                     "form": {"normalized_role": cls}, "provenance": {"paper_id": f"p{i % 2}"}})
        v = centres[cls] + 0.35 * rng.normal(size=dim)
        items[rid] = (v / np.linalg.norm(v)).tolist()
    for pid in ("p0", "p1"):
        mine = [r for r in rows if r["provenance"]["paper_id"] == pid]
        (d / f"{pid}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in mine), encoding="utf-8")
    (d / "embeddings.json").write_text(
        json.dumps({"backend": "toy", "dim": dim, "items": items}), encoding="utf-8")
    (d / "_index.json").write_text(json.dumps({"store": "toy", "row_count": n}), encoding="utf-8")
    return d


def _remint(store_dir: Path, *, row_id: str = "TOY-r000") -> None:
    """What ``b17378c2`` did: rewrite a row's embed_text in place."""
    p = store_dir / "p0.jsonl"
    out = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        r = json.loads(ln)
        if r["row_id"] == row_id:
            r["embed_text"] = r["embed_text"] + " (re-minted)"
        out.append(json.dumps(r))
    p.write_text("\n".join(out) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- #
# the fingerprint
# --------------------------------------------------------------------------- #
def test_fingerprint_moves_on_remint(tmp_path):
    d = _make_store(tmp_path)
    before = F.store_fingerprint(d)
    _remint(d)
    after = F.store_fingerprint(d)
    assert before["rows_sha256"] != after["rows_sha256"], "a re-minted embed_text must move the hash"
    assert before["n_rows"] == after["n_rows"]
    assert before["embeddings_sha256"] == after["embeddings_sha256"]


def test_fingerprint_moves_when_embeddings_regenerate(tmp_path):
    d = _make_store(tmp_path)
    before = F.store_fingerprint(d)
    cache = json.loads((d / "embeddings.json").read_text(encoding="utf-8"))
    cache["items"]["TOY-r000"] = [0.0] * cache["dim"]
    (d / "embeddings.json").write_text(json.dumps(cache), encoding="utf-8")
    assert F.store_fingerprint(d)["embeddings_sha256"] != before["embeddings_sha256"]


def test_fingerprint_ignores_residue_and_underscore_artifacts(tmp_path):
    d = _make_store(tmp_path)
    before = F.store_fingerprint(d)
    (d / "p0.residue.jsonl").write_text(json.dumps({"row_id": "TOY-r000"}) + "\n", encoding="utf-8")
    (d / "_role_taxonomy.jsonl").write_text(json.dumps({"x": 1}) + "\n", encoding="utf-8")
    assert F.store_fingerprint(d)["rows_sha256"] == before["rows_sha256"]


# --------------------------------------------------------------------------- #
# freshness: the whole point — a stale verdict must SAY it is stale
# --------------------------------------------------------------------------- #
def test_unstamped_verdict_is_not_fresh(tmp_path):
    """Silence is not freshness: the pre-organ verdicts carried no fingerprint at all."""
    d = _make_store(tmp_path)
    (d / "gate_verdict.json").write_text(json.dumps({"schema": "toy/0.1", "gate": {"score": 1.0}}),
                                         encoding="utf-8")
    row = F.freshness(d)
    assert row["status"] == F.UNSTAMPED
    assert row["status"] in F.UNTRUSTWORTHY


def test_missing_verdict_reports_missing(tmp_path):
    assert F.freshness(_make_store(tmp_path))["status"] == F.MISSING


def test_stamped_verdict_is_fresh_then_stale_after_remint(tmp_path):
    d = _make_store(tmp_path)
    v = F.stamp_verdict({"schema": "toy/0.1", "gate": {"score": 1.0}}, d)
    (d / "gate_verdict.json").write_text(json.dumps(v), encoding="utf-8")
    assert F.freshness(d)["status"] == F.FRESH
    assert v["gated_at"].endswith("Z")

    _remint(d)
    row = F.freshness(d)
    assert row["status"] == F.STALE
    assert any("rows_sha256" in msg for msg in row["drift"])


def test_regate_restores_freshness_after_remint(tmp_path):
    """The RE-DERIVE exit: gate-only, and the verdict is fresh again."""
    d = _make_store(tmp_path)
    F.rewrite_gate_verdict(d, "normalized_role")
    assert F.freshness(d)["status"] == F.FRESH
    _remint(d)
    assert F.freshness(d)["status"] == F.STALE
    v = F.rewrite_gate_verdict(d, "normalized_role")
    assert F.freshness(d)["status"] == F.FRESH
    assert v["regated"]["previous_gate"] is not None, "the superseded measurement is carried, not lost"


def test_regate_reads_rows_and_embeddings_without_writing_them(tmp_path):
    """A re-gate must never re-derive rows or re-embed: that is what would destroy folded residue."""
    d = _make_store(tmp_path)
    rows_before = {p.name: p.read_bytes() for p in F.canonical_row_files(d)}
    emb_before = (d / "embeddings.json").read_bytes()
    F.rewrite_gate_verdict(d, "normalized_role")
    assert {p.name: p.read_bytes() for p in F.canonical_row_files(d)} == rows_before
    assert (d / "embeddings.json").read_bytes() == emb_before


def test_regate_refuses_when_a_row_has_no_committed_embedding(tmp_path):
    """A missing vector means store and embeddings disagree — refuse loudly, never invent one."""
    d = _make_store(tmp_path)
    cache = json.loads((d / "embeddings.json").read_text(encoding="utf-8"))
    cache["items"].pop("TOY-r000")
    (d / "embeddings.json").write_text(json.dumps(cache), encoding="utf-8")
    with pytest.raises(ValueError, match="no committed embedding"):
        F.regate(d, "normalized_role")


def test_invalidate_retires_without_touching_the_measurement(tmp_path):
    """The INVALIDATE exit: the numbers stay exactly as measured; the file stops reading as live."""
    d = _make_store(tmp_path)
    original = {"schema": "toy/0.1", "class_key": "job",
                "gate": {"score": 0.704545, "baseline": 0.732955, "passed": False}}
    (d / "corpus_verdict.json").write_text(json.dumps(original), encoding="utf-8")
    F.invalidate(d, "corpus_verdict.json", reason="the class key was overwritten by the merge",
                 superseded_by="gate_verdict.json")
    back = json.loads((d / "corpus_verdict.json").read_text(encoding="utf-8"))
    assert back["gate"] == original["gate"], "an invalidation must not re-run a number"
    assert back["superseded"]["superseded_by"] == "gate_verdict.json"
    row = F.freshness(d, "corpus_verdict.json")
    assert row["status"] == F.SUPERSEDED
    assert row["status"] in F.UNTRUSTWORTHY


def test_prose_number_drift_catches_a_render_left_behind(tmp_path):
    """Rows before renders: prose quoting a score is a render of the gate blocks."""
    v = {"schema": "toy/0.2", "gate": {"score": 0.687729, "baseline": 0.671245},
         "finding": "the store scored 0.687729 against 0.671245",
         "stale_finding": "the store scored 0.564103 against 0.676740"}
    drift = F.prose_number_drift(v)
    assert [d.split(":")[0] for d in drift] == ["stale_finding"]
    assert not F.prose_number_drift(v, skip=("stale_finding",))


def test_regate_rerenders_prose_and_reports_no_drift(tmp_path):
    d = _make_store(tmp_path)
    (d / "gate_verdict.json").write_text(json.dumps({
        "schema": "paragraph-plan-gate-verdict/0.2",
        "baseline_finding": "the planted-bad PASSES (score=0.111111 vs base=0.222222)",
    }), encoding="utf-8")
    v = F.rewrite_gate_verdict(d, "normalized_role")
    assert "0.111111" not in v["baseline_finding"]
    assert v["regated"]["prose_number_drift"] == []


def test_noop_regate_keeps_the_real_predecessor(tmp_path):
    """A second re-gate over an unmoved store must not overwrite the superseded measurement with a
    copy of the incumbent."""
    d = _make_store(tmp_path)
    F.rewrite_gate_verdict(d, "normalized_role")
    _remint(d)
    first = F.rewrite_gate_verdict(d, "normalized_role")
    prev = first["regated"]["previous_gate"]
    again = F.rewrite_gate_verdict(d, "normalized_role")
    assert again["regated"]["previous_gate"] == prev


def test_gate_eligible_excludes_defective_and_null_class(tmp_path):
    rows = [{"row_id": "a", "form": {"k": "x"}},
            {"row_id": "b", "form": {"k": None}},
            {"row_id": "c", "form": {"k": "y"}, "defective": True},
            {"row_id": "d", "form": {"k": "x"}, "caveat": True}]
    c = F.gate_eligible(rows, "k")
    assert c["n_eligible"] == 2 and c["n_defective_excluded"] == 1
    assert c["n_null_class_excluded"] == 1 and c["n_caveat_flagged_kept"] == 1
    assert c["classes_present"] == ["x"]


# --------------------------------------------------------------------------- #
# the live stores — the WO's own acceptance condition
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("store", ["section_architecture", "paragraph_plan"])
def test_live_store_verdicts_are_not_silently_stale(store):
    """Every verdict in the two re-minted stores must be FRESH or explicitly SUPERSEDED — never
    STALE, never UNSTAMPED. This is the row the WO's accept condition reads."""
    d = CORPUS_STORES / store
    if not d.is_dir():
        pytest.skip(f"{store} not present")
    rows = F.store_freshness(d)
    assert rows, f"{store} carries no verdict file"
    bad = [r for r in rows if r["status"] in (F.STALE, F.UNSTAMPED)]
    assert not bad, f"stale/unstamped verdicts in {store}: {bad}"


@pytest.mark.parametrize("store", ["section_architecture", "paragraph_plan"])
def test_live_gate_verdict_names_the_post_remint_embeddings(store):
    d = CORPUS_STORES / store
    if not (d / "gate_verdict.json").exists():
        pytest.skip(f"{store} has no gate_verdict.json")
    v = json.loads((d / "gate_verdict.json").read_text(encoding="utf-8"))
    fp = v["store_fingerprint"]
    live = F.store_fingerprint(d)
    assert fp["embeddings_sha256"] == live["embeddings_sha256"]
    assert fp["rows_sha256"] == live["rows_sha256"]
    assert v["gated_at"].endswith("Z")
    assert v["embeddings"]["recomputed"] == 0
    assert F.prose_number_drift(v) == [], "a verdict's prose must not quote a superseded score"
