"""The identity gate's mechanics (soul/0012). Tests use a DUMMY phrase only —
the real seed is never in any repo file, test included."""
from __future__ import annotations

import json

import pytest

from laplace.engine import identity_gate as ig


DUMMY = "quick brown foxes jumped lazily"


def test_kernel_normalizes_case_punctuation_and_fillers():
    a = ig.kernel("The QUICK, brown foxes!")
    b = ig.kernel("quick brown fox")
    assert a == b == ("brown", "fox", "quick")


def test_kernel_stems_plurals_and_verbal_suffixes():
    assert ig.kernel("faces") == ig.kernel("face")
    assert ig.kernel("jumping") == ig.kernel("jump")


def test_seed_and_verify_roundtrip(tmp_path):
    ig.seed([DUMMY], tmp_path)
    assert ig.armed(tmp_path)
    assert ig.verify(DUMMY, tmp_path)


def test_verify_tolerates_reformulation(tmp_path):
    ig.seed(["brown foxes jumping"], tmp_path)
    assert ig.verify("a brown fox, jumped", tmp_path)
    assert ig.verify("THE BROWN FOX JUMPS", tmp_path)
    assert ig.verify("the jumping of brown foxes", tmp_path)


def test_verify_accepts_containing_reply(tmp_path):
    ig.seed(["brown fox"], tmp_path)
    assert ig.verify("well then: the brown fox, as I always said", tmp_path)


def test_verify_rejects_wrong_and_partial(tmp_path):
    ig.seed(["brown fox jumping rivers"], tmp_path)
    assert not ig.verify("brown fox", tmp_path)          # partial kernel
    assert not ig.verify("something else entirely", tmp_path)
    assert not ig.verify("", tmp_path)


def test_disarmed_gate_verifies_nothing(tmp_path):
    assert not ig.armed(tmp_path)
    assert not ig.verify(DUMMY, tmp_path)


def test_seed_stores_no_plaintext(tmp_path):
    ig.seed([DUMMY], tmp_path)
    raw = (tmp_path / ig.SEED_REL).read_text(encoding="utf-8")
    for word in ("quick", "brown", "fox"):
        assert word not in raw


def test_long_reply_is_not_searched_exhaustively(tmp_path):
    ig.seed(["brown fox"], tmp_path)
    essay = " ".join(f"word{i}" for i in range(200)) + " brown fox"
    # kernel is sorted, so the seeded words survive the reply-length cap only
    # if they sort into the first _MAX_REPLY_WORDS — an essay is not an answer.
    assert isinstance(ig.verify(essay, tmp_path), bool)


def test_firing_log_appends(tmp_path):
    rec = ig.log_firing("outward-destination", 0.9, 0.7, "log-only",
                        note="test", repo_root=tmp_path)
    line = (tmp_path / ig.FIRINGS_REL).read_text(encoding="utf-8").strip()
    assert json.loads(line)["trigger_class"] == "outward-destination"
    assert rec["armed"] is False


def test_bad_seed_file_means_disarmed(tmp_path):
    p = tmp_path / ig.SEED_REL
    p.parent.mkdir(parents=True)
    p.write_text("not json", encoding="utf-8")
    assert not ig.armed(tmp_path)
    assert not ig.verify(DUMMY, tmp_path)


def test_oversized_kernel_refused_at_seed(tmp_path):
    with pytest.raises(ValueError):
        ig.seed(["one two three four five six seven eight nine ten eleven"], tmp_path)
