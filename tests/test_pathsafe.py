"""Scoped tests for laplace.pipeline.pathsafe — the ONE sid->filename encoder.

Covers: the ':' -> '_' projection (the ruled encoding), determinism +
idempotence on already-clean stems, every NTFS-illegal char, the empty-sid
raise, and the injectivity guard (encode_sids_for_dir raises on collision,
passes on a clean set). All hermetic — pure function calls, no filesystem.
"""
from __future__ import annotations

import pytest

from laplace.pipeline import pathsafe


def test_colon_becomes_underscore():
    # the proposal's own example: ids are kind:slug with hyphens
    assert pathsafe.encode_sid_for_path("sec:abstract") == "sec_abstract"
    assert pathsafe.encode_sid_for_path("sec:what-now") == "sec_what-now"


def test_idempotent_on_clean_stem():
    # a reader handed the clean sid, or the encoded stem itself, resolves alike
    once = pathsafe.encode_sid_for_path("sec:abstract")
    assert pathsafe.encode_sid_for_path(once) == once
    assert pathsafe.encode_sid_for_path("sec_abstract") == "sec_abstract"


def test_deterministic():
    assert (pathsafe.encode_sid_for_path("sec:results")
            == pathsafe.encode_sid_for_path("sec:results"))


@pytest.mark.parametrize("ch", list(':*?"<>|'))
def test_every_illegal_char_encoded(ch):
    out = pathsafe.encode_sid_for_path(f"sec{ch}x")
    assert ch not in out
    assert out == "sec_x"


def test_clean_id_untouched():
    # no illegal char -> byte-for-byte the same (hyphens/underscores are legal)
    assert pathsafe.encode_sid_for_path("goal-3_final") == "goal-3_final"


@pytest.mark.parametrize("bad", ["", None, 123, []])
def test_empty_or_nonstr_raises(bad):
    with pytest.raises(ValueError):
        pathsafe.encode_sid_for_path(bad)  # type: ignore[arg-type]


def test_encode_sids_for_dir_maps_all():
    sids = ["sec:abstract", "sec:gaps", "sec:what"]
    got = pathsafe.encode_sids_for_dir(sids)
    assert got == {"sec:abstract": "sec_abstract",
                   "sec:gaps": "sec_gaps",
                   "sec:what": "sec_what"}


def test_encode_sids_for_dir_raises_on_collision():
    # two DISTINCT ids projecting to one filename is a hard error
    with pytest.raises(ValueError, match="collision"):
        pathsafe.encode_sids_for_dir(["sec:abstract", "sec_abstract"])


def test_encode_sids_for_dir_repeated_same_id_ok():
    # the SAME id twice is not a collision (same file, idempotent)
    got = pathsafe.encode_sids_for_dir(["sec:abstract", "sec:abstract"])
    assert got == {"sec:abstract": "sec_abstract"}
