"""Scoped tests for src/laplace/pipeline/fork_adjudicator.py — the standing DRIVER that
closes parked forks instead of warning about them (his steer PV-20260716T151557Z).

A tmp fixture repo (profile organs + OPEN_STACK forks + corpus_friction fork records + a
prior verdict ledger) proves: the shared enumeration matches close_checklist's PASS/WARN
split (one enumeration, two consumers); a GENUINELY-HIS route is FAIL-CLOSED (no frame /
no reason -> rejected); the dry-run writes ZERO ledger bytes; bank validates the required
spine; and the manifest matches the growth dispatch idiom (hoisted-frame schema 2). No
model is ever called.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from laplace.engine import author_proxy
from laplace.pipeline import fork_adjudicator as fa

REPO = Path(__file__).resolve().parents[1]
_SCRIPT = REPO / "scripts" / "close_checklist.py"
_spec = importlib.util.spec_from_file_location("close_checklist", _SCRIPT)
close_checklist = importlib.util.module_from_spec(_spec)
sys.modules["close_checklist"] = close_checklist
_spec.loader.exec_module(close_checklist)

RED = "\U0001f534"  # 🔴


def _fixture(tmp_path: Path, *, with_friction: bool = True) -> Path:
    repo = tmp_path / "repo"
    (repo / "profiles").mkdir(parents=True)
    (repo / "EIGEN_AUTHOR.md").write_text(
        "# Working with the author\n- earned simplicity not slop (his, 2026-06-08)\n",
        encoding="utf-8")
    (repo / "profiles" / "gerard_mini_conceptric_v1.json").write_text(
        json.dumps({"nodes": [{"id": "honesty-over-polish"}]}), encoding="utf-8")
    # two OPEN_STACK forks: F10 referenced by a verdict, F20 parked
    (repo / "OPEN_STACK.md").write_text(
        "# open stack\n\n## Stratum 1 — author-forks\n\n"
        f"- **F10 a decided fork — live {RED} (2026-07-16)**: already ruled\n"
        f"- **F20 a parked fork — live {RED} (2026-07-16)**: derivable, undecided\n",
        encoding="utf-8")
    (repo / "proxy_verdicts.jsonl").write_text(
        json.dumps({"id": "PV-20260716T000000Z-f10", "date": "2026-07-16",
                    "question": "F10 — close it?", "ruling": "closed",
                    "evidence": ["e"], "confidence": "HIGH", "supersedes": [],
                    "unlocks": "", "contested": None}) + "\n", encoding="utf-8")
    if with_friction:
        cf = repo / "corpus_friction"
        cf.mkdir()
        # one open fork record (parked), one non-fork friction (ignored), one open fork
        (cf / "a.jsonl").write_text(
            json.dumps({"id": "RW-1", "kind": "fork", "status": "open",
                        "node": "n1", "value": "a friction fork parked"}) + "\n"
            + json.dumps({"id": "RW-2", "kind": "friction", "status": "open",
                          "node": "n2", "value": "not a fork"}) + "\n", encoding="utf-8")
    return repo


# --------------------------------------------------------------- enumeration parity
def test_enumeration_parity_with_check_fork_adjudication(tmp_path):
    repo = _fixture(tmp_path)
    checks = close_checklist.check_fork_adjudication(repo)
    warn_keys = {c.detail.split()[0] for c in checks if c.status == "WARN"}
    pass_keys = {c.detail.split(":")[0] for c in checks if c.status == "PASS"}

    parked = {f.key for f in fa.enumerate_parked_forks(repo)}
    referenced = {f.key for f in fa.enumerate_forks(repo) if f.referenced}

    # the DRIVER's parked set is exactly the close's WARN set; the referenced set its PASS
    assert parked == warn_keys, (parked, warn_keys)
    assert referenced == pass_keys, (referenced, pass_keys)
    # both stores are covered: F20 (open_stack) and RW-1 (corpus_friction) are parked
    assert {"F20", "RW-1"} <= parked
    assert "F10" in referenced


def test_referenced_fork_is_not_parked(tmp_path):
    repo = _fixture(tmp_path)
    parked = {f.key for f in fa.enumerate_parked_forks(repo)}
    assert "F10" not in parked  # a verdict names it


def test_enumeration_survives_missing_corpus_friction(tmp_path):
    repo = _fixture(tmp_path, with_friction=False)
    keys = {f.key for f in fa.enumerate_parked_forks(repo)}
    assert keys == {"F20"}


# ---------------------------------------------------- GENUINELY-HIS is fail-closed
def _base_ruling(conf="HIGH", **extra):
    r = {"id": author_proxy.make_ruling_id("t"), "date": "2026-07-16",
         "question": "q", "ruling": "r", "evidence": ["e"], "confidence": conf,
         "supersedes": [], "unlocks": "", "contested": None}
    r.update(extra)
    return r


def test_genuinely_his_route_rejected_without_reason(tmp_path):
    repo = _fixture(tmp_path)
    fork = fa.enumerate_parked_forks(repo)[0]
    with pytest.raises(ValueError, match="non_derivable_reason"):
        fa.route_genuinely_his(repo, fork, {"confidence": "GENUINELY-HIS"})


def test_genuinely_his_bank_rejected_without_frame(tmp_path):
    repo = _fixture(tmp_path)
    r = _base_ruling("GENUINELY-HIS", non_derivable_reason="his person")
    # no frame attached -> fail-closed at bank
    with pytest.raises(ValueError, match="complete decision frame"):
        fa.bank_fork_ruling(repo, r)


def test_genuinely_his_bank_rejected_without_reason(tmp_path):
    repo = _fixture(tmp_path)
    frame = author_proxy.assemble_decision_frame(repo, "q", "F20")
    r = _base_ruling("GENUINELY-HIS", frame=frame)
    with pytest.raises(ValueError, match="non_derivable_reason"):
        fa.bank_fork_ruling(repo, r)


def test_routed_item_carries_the_whole_frame(tmp_path):
    repo = _fixture(tmp_path)
    fork = fa.enumerate_parked_forks(repo)[0]
    routed = fa.route_genuinely_his(
        repo, fork, {"confidence": "GENUINELY-HIS", "non_derivable_reason": "his call"})
    # everything to decide in seconds: the profile organs + corpus + verdicts + fork rows
    assert routed["frame"]["profile_refs"]
    assert routed["non_derivable_reason"] == "his call"


def test_genuinely_his_bank_strips_frame_to_digest(tmp_path):
    repo = _fixture(tmp_path)
    frame = author_proxy.assemble_decision_frame(repo, "q", "F20")
    r = _base_ruling("GENUINELY-HIS", non_derivable_reason="his person, his name", frame=frame)
    banked = fa.bank_fork_ruling(repo, r)
    assert "frame" not in banked                 # the megabyte frame is NOT in the ledger
    assert "frame_digest" in banked              # a bounded receipt is
    assert banked["frame_digest"]["profile_organs"]
    assert banked["kind"] == "fork-adjudication"


# ------------------------------------------------------ dry-run writes zero ledger bytes
def test_dry_run_writes_zero_ledger_bytes(tmp_path, monkeypatch):
    repo = _fixture(tmp_path)
    ledger_before = (repo / "proxy_verdicts.jsonl").read_bytes()

    def _boom(*a, **k):
        raise AssertionError("dry-run must not append to the ledger")

    monkeypatch.setattr(author_proxy, "_append_jsonl", _boom)
    scratch = tmp_path / "scratch"
    summary = fa.drive(repo, mode="dry-run", scratch_dir=scratch)

    assert summary["parked"] == 2
    assert Path(summary["manifest_path"]).is_file()
    # the ledger is byte-for-byte unchanged
    assert (repo / "proxy_verdicts.jsonl").read_bytes() == ledger_before


def test_drive_refuses_live_mode(tmp_path):
    repo = _fixture(tmp_path)
    with pytest.raises(ValueError, match="dry-run only"):
        fa.drive(repo, mode="live")


# ------------------------------------------------------ bank validates required spine
@pytest.mark.parametrize("drop", list(author_proxy.REQUIRED_KEYS))
def test_bank_validates_required_keys(tmp_path, drop):
    repo = _fixture(tmp_path)
    r = _base_ruling()
    r.pop(drop)
    with pytest.raises(ValueError):
        fa.bank_fork_ruling(repo, r)


def test_bank_derivable_ruling_appends_and_is_seen_by_the_close(tmp_path):
    repo = _fixture(tmp_path)
    fork = next(f for f in fa.enumerate_parked_forks(repo) if f.key == "F20")
    r = _base_ruling(id=author_proxy.make_ruling_id("f20-decide"), question="F20 — decide",
                     ruling="decided: do X")
    fa.bank_fork_ruling(repo, r)
    # the loop closes: F20 now references a verdict, so the close PASSes it
    parked = {f.key for f in fa.enumerate_parked_forks(repo)}
    assert "F20" not in parked


# ------------------------------------------------------ manifest matches the growth idiom
def test_manifest_shape_matches_the_growth_idiom(tmp_path):
    repo = _fixture(tmp_path)
    parked = fa.enumerate_parked_forks(repo)
    frame = fa.assemble_manifest_frame(repo)
    packets = [fa.build_lite_packet(f) for f in parked]
    out = tmp_path / "m.json"
    manifest = fa.emit_dispatch_manifest(packets, out, frame=frame)

    # the storyboard/growth self-describing spine
    for key in ("kind", "count", "cut_at", "bank_contract", "packets", "invocation"):
        assert key in manifest
    assert manifest["kind"] == "fork-adjudication"
    assert manifest["count"] == len(parked)
    assert manifest["bank_contract"]["function"].endswith("bank_fork_ruling")
    # the fail-closed route contract travels in the manifest a judge reads
    assert "route_to_him_is_fail_closed" in manifest["bank_contract"]
    # the file is the same content
    assert json.loads(out.read_text())["count"] == manifest["count"]


# ------------------------------------------------------ desk surfaces drafts honestly
def test_desk_proxy_drafts_are_honest_about_dry_run_vs_banked(tmp_path):
    from laplace.web import desk
    repo = _fixture(tmp_path)
    # a dry-run frames forks to scratch and banks NOTHING -> the desk shows no new draft
    fa.drive(repo, mode="dry-run", scratch_dir=tmp_path / "s")
    before = desk._desk_proxy(repo)["count"]

    # a supervised bank -> the fork ruling surfaces as a contestable proxy-draft, honestly
    r = _base_ruling(id=author_proxy.make_ruling_id("f20"), question="F20 — decide")
    fa.bank_fork_ruling(repo, r)
    after = desk._desk_proxy(repo)
    assert after["count"] == before + 1
    row = next(x for x in after["rows"] if x["title"].startswith("F20"))
    assert row["class"] == "proxy-drafts"
    assert row["verbs"] == ["confirm", "amend", "reject"]


def test_manifest_hoists_exactly_one_frame(tmp_path):
    repo = _fixture(tmp_path)
    parked = fa.enumerate_parked_forks(repo)
    frame = fa.assemble_manifest_frame(repo)
    packets = [fa.build_lite_packet(f) for f in parked]
    out = tmp_path / "m.json"
    manifest = fa.emit_dispatch_manifest(packets, out, frame=frame)

    assert manifest["schema"] == 2
    assert "frame" in manifest                      # hoisted once at the top
    assert manifest["frame"]["profile_refs"]
    for p in manifest["packets"]:                   # no packet re-carries the frame
        assert "frame" not in p
        assert "question" in p and "fork_text" in p
