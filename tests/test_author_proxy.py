"""Scoped tests for src/laplace/engine/author_proxy.py — the author-proxy adjudicator.

A tmp fixture repo (the four profile organs, an OPEN_STACK with BOTH live fork
formats, a prior verdict ledger) proves: the frame gathers all four channels; a
bank validates its schema and only ever APPENDS (never edits a prior record); a
contest is itself an appended record. No model is ever called.
"""
import json
from pathlib import Path

import pytest

from laplace.engine import author_proxy

RED = "\U0001f534"  # 🔴 OPEN_STACK live marker


def _fixture(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "profiles").mkdir(parents=True)
    (repo / "EIGEN_AUTHOR.md").write_text(
        "# Working with the author\n"
        "- Terse, warm, fast, British.\n"
        "- you had to want (his, 2026-06-08 the wanting is standing law)\n",
        encoding="utf-8",
    )
    (repo / "profiles" / "gerard_mini_conceptric_v1.json").write_text(
        json.dumps({"nodes": [{"id": "honesty-over-polish"}]}), encoding="utf-8")
    (repo / "profiles" / "GERARD_PSYCH_PROFILE_2026-07-11_v1.md").write_text(
        "# Psych profile\nhonesty over polish; evidence-or-open\n", encoding="utf-8")
    (repo / "DESIGN_2026-07-09_gerard-technical-voice-profile-v1.md").write_text(
        "# Voice profile\nBritish spelling is house style (his, 2026-07-09)\n",
        encoding="utf-8")
    # OPEN_STACK with BOTH live fork formats naming F14
    (repo / "OPEN_STACK.md").write_text(
        "# open stack\n\n## Stratum 1 — author-forks\n\n"
        "| F14 | **derive the fates codebook** | 2026-07-01 | 2 | " + RED + " | notes tail |\n"
        f"- **F14 fates codebook — live {RED} (2026-07-01)**: derive from the banked batch\n"
        f"- **F99 unrelated — live {RED}**: a different fork\n",
        encoding="utf-8",
    )
    # a prior verdict already banked
    prior = {
        "id": "PV-20260711-prior-call", "date": "2026-07-11",
        "question": "a settled prior", "ruling": "settled", "evidence": ["x"],
        "confidence": "HIGH", "supersedes": [], "unlocks": "y", "contested": None,
    }
    (repo / "proxy_verdicts.jsonl").write_text(
        json.dumps(prior, ensure_ascii=False) + "\n", encoding="utf-8")
    return repo


@pytest.fixture
def repo(tmp_path):
    return _fixture(tmp_path)


# ------------------------------------------------------------------ frame assembly
def test_frame_gathers_all_four_channels(repo):
    frame = author_proxy.assemble_decision_frame(repo, "should F14 derive?", fork_id="F14")
    assert frame["question"] == "should F14 derive?"
    assert frame["fork_id"] == "F14"

    refs = frame["profile_refs"]
    for role in ("eigen_author", "mini_conceptric", "psych_profile", "voice_profile"):
        assert refs[role]["path"] is not None, role
        assert refs[role]["excerpt"], role

    assert frame["ruling_corpus"], "no (his, <date>) lines harvested"
    assert any("wanting" in e["text"] for e in frame["ruling_corpus"])

    assert len(frame["prior_verdicts"]) == 1
    assert frame["prior_verdicts"][0]["id"] == "PV-20260711-prior-call"


def test_fork_text_carries_both_formats(repo):
    frame = author_proxy.assemble_decision_frame(repo, "q", fork_id="F14")
    ft = frame["fork_text"]
    assert any(r.startswith("| F14") for r in ft), "table row missing"
    assert any(r.startswith("- **F14") for r in ft), "bullet row missing"
    # the unrelated fork must not bleed in
    assert not any("F99" in r for r in ft)


def test_frame_never_needs_a_fork(repo):
    frame = author_proxy.assemble_decision_frame(repo, "a general question")
    assert frame["fork_id"] is None
    assert frame["fork_text"] == []


# ------------------------------------------------------------------ bank + validate
def _valid_ruling() -> dict:
    return {
        "id": author_proxy.make_ruling_id("close-the-fork"),
        "date": "2026-07-12", "question": "close it?", "ruling": "closed",
        "evidence": ["he stated it"], "confidence": "GENUINELY-HIS",
        "supersedes": [], "unlocks": "the next tranche", "contested": None,
    }


def test_bank_appends_and_returns(repo):
    ledger = repo / "proxy_verdicts.jsonl"
    before = ledger.read_text(encoding="utf-8")
    rec = author_proxy.bank_ruling(repo, _valid_ruling())
    after = ledger.read_text(encoding="utf-8")
    assert after.startswith(before), "prior content must be untouched (append-only)"
    assert rec["id"] in after
    assert len(author_proxy.load_verdicts(repo)) == 2


def test_bank_never_edits_prior_record(repo):
    prior_before = author_proxy.load_verdicts(repo)[0]
    author_proxy.bank_ruling(repo, _valid_ruling())
    prior_after = author_proxy.load_verdicts(repo)[0]
    assert prior_after == prior_before


@pytest.mark.parametrize("mutate", [
    lambda r: r.pop("unlocks"),                     # missing required key
    lambda r: r.update(confidence="MAYBE"),         # bad confidence
    lambda r: r.update(id="X-not-a-pv"),            # wrong id shape
    lambda r: r.update(evidence="a string"),        # evidence not a list
])
def test_bank_rejects_malformed(repo, mutate):
    bad = _valid_ruling()
    mutate(bad)
    with pytest.raises(ValueError):
        author_proxy.bank_ruling(repo, bad)


# ------------------------------------------------------------------ contest appends
def test_contest_is_an_appended_record_not_an_edit(repo):
    target = "PV-20260711-prior-call"
    n_before = len(author_proxy.load_verdicts(repo))
    prior_before = author_proxy.load_verdicts(repo)[0]

    con = author_proxy.contest_ruling(repo, target, "on reflection, reopen")
    verdicts = author_proxy.load_verdicts(repo)

    assert len(verdicts) == n_before + 1
    assert con["kind"] == "contest"
    assert con["contests"] == target
    # the contested original is still present and byte-identical
    assert verdicts[0] == prior_before


def test_no_veto_field_on_a_banked_ruling(repo):
    rec = author_proxy.bank_ruling(repo, _valid_ruling())
    assert "veto" not in rec
    assert rec["contested"] is None


# --------------------------------------------------- the fusion organ: third input
REPO = Path(__file__).resolve().parents[1]


def _stores_ready() -> bool:
    for store in ("section_architecture", "spine_chain"):
        if not (REPO / "corpus_stores" / store / "gate_verdict.json").is_file():
            return False
    try:
        from laplace.representation.embed_router import get_backend
        return get_backend() is not None
    except Exception:
        return False


def _enabled_dials() -> dict:
    from laplace.pipeline.dials import defaults
    d = defaults()
    d["stores"]["section_architecture"]["enabled"] = True
    d["stores"]["spine_chain"]["enabled"] = True
    return d


def test_frame_carries_form_exemplars_key(repo):
    """The frame gains the THIRD input for every question — its shape is stable
    (structural flag + per-store served/note), present even on the tmp fixture."""
    frame = author_proxy.assemble_decision_frame(repo, "should F14 derive?", fork_id="F14")
    fe = frame["form_exemplars"]
    assert set(fe) >= {"structural", "stores", "served_count", "query_digest"}
    for store in ("section_architecture", "spine_chain"):
        assert store in fe["stores"]
        assert "served" in fe["stores"][store] and "note" in fe["stores"][store]


def test_non_structural_question_carries_no_form(repo):
    """A pure taste call (naming) is NOT structural: no retrieval, honest note."""
    fe = author_proxy.build_form_exemplars(
        repo, "is this register his own coinage or borrowed jargon?")
    assert fe["structural"] is False
    assert fe["served_count"] == 0
    for store in ("section_architecture", "spine_chain"):
        assert fe["stores"][store]["note"] == "not-a-structural-question"


def test_structural_question_is_detected():
    for q in ("does he respine s4?", "demote the estimates section",
              "reorder these sections", "restructure the spine ladder"):
        assert author_proxy.is_structural_question(q), q
    for q in ("is this term his coinage?", "deslop this slogan line",
              "give the truer essence"):
        assert not author_proxy.is_structural_question(q), q


def test_structural_question_dial_off_notes_absence(repo):
    """Structural question, default dials (both stores OFF): served=0, each store's
    absence noted honestly as dial-off — the inert default, not a crash."""
    fe = author_proxy.build_form_exemplars(
        repo, "does he respine section s4?")
    assert fe["structural"] is True
    assert fe["served_count"] == 0
    for store in ("section_architecture", "spine_chain"):
        assert fe["stores"][store]["served"] is False
        assert fe["stores"][store]["note"].startswith("dial-off")


@pytest.mark.skipif(not _stores_ready(),
                    reason="requires corpus_stores + the vendored embed backend")
def test_structural_question_dial_on_serves_form(repo):
    """Structural question + enabled dials against the real repo: both stores serve
    the FORM-EXEMPLARS envelope, and NO prose (embed_text) leaks into it."""
    fe = author_proxy.build_form_exemplars(
        REPO, "reorder and demote the estimates section", dials=_enabled_dials())
    assert fe["structural"] is True
    assert fe["served_count"] == 2
    for store in ("section_architecture", "spine_chain"):
        env = fe["stores"][store]["envelope"]
        assert env and "FORM-EXEMPLARS" in env
        assert "embed_text" not in env
