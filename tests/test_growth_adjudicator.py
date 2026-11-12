"""Scoped tests for src/laplace/pipeline/growth_adjudicator.py — the bridge that makes
the author-proxy the taste authority inside conceptric growth.

A tmp fixture repo (the proxy's profile organs + a prior verdict ledger) proves: a
growth decision assembles a full frame and returns a well-shaped packet; every growth
kind produces a question; an unknown kind is refused; the manifest is written in the
storyboard idiom; and a growth ruling banks with ``kind:"growth"`` through the proxy's
append-only ledger — no model is ever called.
"""
import json
from pathlib import Path

import pytest

from laplace.engine import author_proxy
from laplace.pipeline import growth_adjudicator as ga


def _fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "profiles").mkdir(parents=True)
    (repo / "EIGEN_AUTHOR.md").write_text(
        "# Working with the author\n- Terse, warm, British.\n"
        "- earned simplicity not slogan slop (his, 2026-06-08)\n", encoding="utf-8")
    (repo / "profiles" / "gerard_mini_conceptric_v1.json").write_text(
        json.dumps({"nodes": [{"id": "honesty-over-polish"}]}), encoding="utf-8")
    (repo / "OPEN_STACK.md").write_text("# open stack\n", encoding="utf-8")
    return repo


@pytest.fixture
def repo(tmp_path):
    return _fixture(tmp_path)


def test_adjudicate_growth_packet_shape(repo):
    decision = {
        "kind": "deslop-keep-kill-rewrite",
        "subject": "d_node :: EigenEngine unlocks a seamless paradigm",
        "candidates": ["KEEP", "KILL", "REWRITE"],
        "context": "tells=public-jargon; jargon=['unlock','seamless','paradigm']",
    }
    packet = ga.adjudicate_growth(repo, decision)

    assert set(packet) == {"frame", "decision", "bank"}
    # the frame is the proxy's real frame — all four channels present
    frame = packet["frame"]
    assert set(frame) >= {"question", "profile_refs", "ruling_corpus",
                          "prior_verdicts", "fork_text"}
    assert "DESLOP" in frame["question"]
    assert "d_node" in frame["question"]
    # the decision travels verbatim; the bank slot is the callable-shape contract
    assert packet["decision"] == decision
    assert packet["bank"]["kind"] == "growth"
    assert packet["bank"]["function"].endswith("bank_growth_ruling")
    assert set(author_proxy.REQUIRED_KEYS) <= set(packet["bank"]["required_keys"])


def test_every_growth_kind_builds_a_question(repo):
    for kind in ga.GROWTH_KINDS:
        packet = ga.adjudicate_growth(
            repo, {"kind": kind, "subject": "sub", "context": "ctx"})
        assert packet["frame"]["question"]           # non-empty
        assert packet["decision"]["kind"] == kind


def test_unknown_kind_refused(repo):
    with pytest.raises(ValueError):
        ga.adjudicate_growth(repo, {"kind": "not-a-kind", "subject": "x"})


def test_fork_id_threads_into_frame(repo):
    RED = "\U0001f534"
    (repo / "OPEN_STACK.md").write_text(
        f"# open stack\n- **F14 deslop — live {RED}**: kill the slogans\n",
        encoding="utf-8")
    packet = ga.adjudicate_growth(
        repo, {"kind": "deepen-which-node", "subject": "sec", "fork_id": "F14"})
    assert packet["frame"]["fork_id"] == "F14"
    assert any("F14" in row for row in packet["frame"]["fork_text"])


def test_emit_dispatch_manifest(repo, tmp_path):
    packets = [ga.adjudicate_growth(repo, {"kind": "essence-edit", "subject": f"n{i}"})
               for i in range(3)]
    out = tmp_path / "out" / "growth_manifest.json"
    manifest = ga.emit_dispatch_manifest(packets, out)

    assert out.is_file()
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == manifest
    assert manifest["kind"] == "growth-adjudication"
    assert manifest["count"] == 3
    assert manifest["bank_contract"]["kind"] == "growth"
    assert "growth_manifest.json" in manifest["invocation"]
    assert len(manifest["packets"]) == 3


def test_bank_growth_ruling_stamps_kind_and_appends(repo):
    ruling = {
        "id": author_proxy.make_ruling_id("kill-the-slogan"),
        "date": "2026-07-12",
        "question": "DESLOP — keep/kill/rewrite 'seamless paradigm'?",
        "ruling": "KILL",
        "evidence": ["public-jargon x3", "his: earned simplicity not slogan slop"],
        "confidence": "GENUINELY-HIS",
        "supersedes": [],
        "unlocks": "the essence rewrite",
        "contested": None,
    }
    banked = ga.bank_growth_ruling(repo, ruling)
    assert banked["kind"] == "growth"

    verdicts = author_proxy.load_verdicts(repo)
    assert len(verdicts) == 1
    assert verdicts[0]["kind"] == "growth"
    assert verdicts[0]["ruling"] == "KILL"
    # append-only: a second bank never edits the first
    ga.bank_growth_ruling(repo, {**ruling, "id": author_proxy.make_ruling_id("second"),
                                 "ruling": "REWRITE"})
    assert len(author_proxy.load_verdicts(repo)) == 2


def test_bank_growth_ruling_validates(repo):
    # missing the required spine → the proxy's validator rejects it
    with pytest.raises(ValueError):
        ga.bank_growth_ruling(repo, {"id": "PV-x", "ruling": "KILL"})


# ------------------------------------------------------ the manifest-frame hoist (0a)
def test_adjudicate_growth_lite_is_frameless():
    decision = {
        "kind": "deslop-keep-kill-rewrite",
        "subject": "d_node :: EigenEngine unlocks a seamless paradigm",
        "candidates": ["KEEP", "KILL", "REWRITE"],
        "context": "tells=public-jargon",
    }
    packet = ga.adjudicate_growth_lite(decision)
    # the lite packet keeps ONLY its own decision + the bank contract — no frame
    assert set(packet) == {"decision", "bank"}
    assert "frame" not in packet
    # the question is folded into the packet's own decision — its task statement travels
    assert "DESLOP" in packet["decision"]["question"]
    assert "d_node" in packet["decision"]["question"]
    assert packet["bank"]["kind"] == "growth"


def test_adjudicate_growth_lite_refuses_unknown_kind():
    with pytest.raises(ValueError):
        ga.adjudicate_growth_lite({"kind": "not-a-kind", "subject": "x"})


def test_manifest_hoists_exactly_one_frame(repo, tmp_path):
    frame = ga.assemble_manifest_frame(repo, "DESLOP wave — rule each packet.")
    packets = [ga.adjudicate_growth_lite(
        {"kind": "deslop-keep-kill-rewrite", "subject": f"n{i}"}) for i in range(5)]
    out = tmp_path / "hoist" / "manifest.json"
    manifest = ga.emit_dispatch_manifest(packets, out, frame=frame)

    assert manifest["schema"] == 2
    assert manifest["frame"] == frame
    # exactly ONE frame in the whole manifest: NO packet carries its own
    assert all("frame" not in p for p in manifest["packets"])
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk == manifest
    assert on_disk["frame"]["question"].startswith("DESLOP wave")


def test_manifest_legacy_shape_unchanged_without_frame(repo, tmp_path):
    packets = [ga.adjudicate_growth(repo, {"kind": "essence-edit", "subject": f"n{i}"})
               for i in range(2)]
    manifest = ga.emit_dispatch_manifest(packets, tmp_path / "legacy.json")
    # the pre-0a shape is untouched: no frame / no schema, same key set as before
    assert "frame" not in manifest
    assert "schema" not in manifest
    assert set(manifest) == {"kind", "count", "cut_at", "bank_contract",
                             "packets", "invocation"}


def test_manifest_grows_linear_not_frame_times_n(repo, tmp_path):
    """For N synthetic candidates the lite manifest grows in decision text only — one
    frame is banked, not one-per-packet. Contrast the framed manifest, which pays a
    whole frame per packet (the flatten reflex the hoist repairs)."""
    frame = ga.assemble_manifest_frame(repo, "DESLOP wave — rule each packet.")
    frame_bytes = len(json.dumps(frame))

    def lite_size(n):
        packets = [ga.adjudicate_growth_lite(
            {"kind": "deslop-keep-kill-rewrite", "subject": f"n{i} :: slop to grow"})
            for i in range(n)]
        return len(json.dumps(
            ga.emit_dispatch_manifest(packets, tmp_path / f"lite{n}.json", frame=frame)))

    def framed_size(n):
        packets = [ga.adjudicate_growth(
            repo, {"kind": "deslop-keep-kill-rewrite", "subject": f"n{i} :: slop to grow"})
            for i in range(n)]
        return len(json.dumps(
            ga.emit_dispatch_manifest(packets, tmp_path / f"framed{n}.json")))

    lite_marginal = lite_size(10) - lite_size(1)
    framed_marginal = framed_size(10) - framed_size(1)
    # the 9 extra packets cost the framed manifest ~9 whole frames more than the lite
    assert framed_marginal - lite_marginal > 5 * frame_bytes
