"""The locator law's mechanical half: coverage measured (never patched), locators parsed into
window tokens, coupling read off shared substrate via ``keeper_ring`` - and the upstream half,
the provenance rule riding every intelligent brief ``soul_dream`` hands out.

Fixtures are synthetic (no soul content): a fake folded tranche with one pre-law entity (bare
strings) and one post-law entity (locator-carrying), sharing one substrate window.
"""

from __future__ import annotations

import json

import pytest

from laplace.engine import soul_provenance
from laplace.engine.soul_dream import SHARD, _brief


def test_people_census_names_and_masses_only(tmp_path):
    """The rewiring sweep's gate: chat sources vs promoted entities - names, sizes, item counts,
    NEVER content. A promoted chat partner reads 'promoted'; an unpromoted mass is the sweep's
    candidate; an entity with no chat dir still rides (entity-only)."""
    shard = tmp_path / SHARD
    folded = shard / "t_folded"
    folded.mkdir(parents=True)
    (folded / "jane_doe.json").write_text(json.dumps(
        {"name": "Jane Doe", "voice": [{"trait": "wry", "note": "SECRET", "locator": "c1"}]}),
        encoding="utf-8")
    chats = tmp_path / soul_provenance.CHAT_LOGS
    (chats / "Jane_Doe").mkdir(parents=True)
    (chats / "Jane_Doe" / "chat.txt").write_text("x" * 2048, encoding="utf-8")
    (chats / "Old_Friend").mkdir()
    (chats / "Old_Friend" / "chat.txt").write_text("y" * 4096, encoding="utf-8")

    c = soul_provenance.people_census(tmp_path)
    rows = {r["source"]: r for r in c["rows"]}
    assert rows["Jane_Doe"]["promoted"] is True and rows["Jane_Doe"]["items"] == 1
    assert rows["Jane_Doe"]["stem"] == "jane_doe"
    assert rows["Old_Friend"]["promoted"] is False and rows["Old_Friend"]["kb"] == 4
    assert c["n_missing"] == 1 and c["n_sources"] == 2
    assert c["rows"][0]["source"] == "Old_Friend"        # biggest waiting mass first
    assert "SECRET" not in json.dumps(c)                 # names + masses only, never content


@pytest.fixture()
def folded_repo(tmp_path):
    """A minimal sealed layer: tranche dir + two entities + one apex + one non-entity map."""
    shard = tmp_path / SHARD
    folded = shard / "scaled_tranche9_folded"
    folded.mkdir(parents=True)

    # Pre-law shape: bare-string voice, history with locators (the floor that never dropped them).
    (folded / "ada.json").write_text(json.dumps({
        "name": "Ada",
        "voice": ["pattern one", "pattern two"],
        "history": [
            {"fact": "met at the workshop", "locator": "win_7:10-22", "confidence": "high"},
            {"fact": "moved cities", "locator": "win_9:1-4, file_2.txt:8-9", "confidence": "high"},
        ],
        "relations": [{"with": "Bo", "nature": "collaborator"}],
    }), encoding="utf-8")

    # Post-law shape: every field locator-carrying; shares window win_7 with Ada; one honest-null.
    (folded / "bo.json").write_text(json.dumps({
        "name": "Bo",
        "voice": [
            {"trait": "dry humour", "locator": "win_7:30-41"},
            {"trait": "unplaceable", "locator": None},
        ],
        "generator": [{"statement": "prefers the long game", "locator": "win_11:2-6"}],
    }), encoding="utf-8")

    # An apex at the shard top level is walked too.
    (shard / "_APEX_TEST.json").write_text(json.dumps({
        "name": "apex", "voice": [{"trait": "hub", "locator": "win_11:1-1"}],
    }), encoding="utf-8")

    # Shape-excluded: no 'name' key (a plan/map, not an entity).
    (shard / "_dream_plan.json").write_text(json.dumps({"frontier": []}), encoding="utf-8")
    return tmp_path


def test_iter_entities_selects_by_shape(folded_repo):
    stems = {p.stem for p, _ in soul_provenance.iter_entities(folded_repo)}
    assert stems == {"ada", "bo", "_APEX_TEST"}


def test_item_locator_honest_null():
    assert soul_provenance.item_locator("bare string") is None
    assert soul_provenance.item_locator({"trait": "x", "locator": None}) is None
    assert soul_provenance.item_locator({"trait": "x", "locator": "  "}) is None
    assert soul_provenance.item_locator({"trait": "x", "locator": "win_7:1-2"}) == "win_7:1-2"


def test_locator_tokens_window_ids():
    assert soul_provenance.locator_tokens("win_9:1-4, file_2.txt:8-9") == {"win_9", "file_2.txt"}
    assert soul_provenance.locator_tokens("282:100-114") == {"282"}


def test_coverage_counts_and_rates(folded_repo):
    cov = soul_provenance.coverage(folded_repo)
    assert cov["n_entities"] == 3
    # Ada: voice 0/2 bare, history 2/2 locatored, relations 0/1.
    assert cov["files"]["ada"]["voice"] == {"n": 2, "with_locator": 0}
    assert cov["files"]["ada"]["history"] == {"n": 2, "with_locator": 2}
    # Bo: voice 1/2 (the honest-null does not count), generator 1/1.
    assert cov["files"]["bo"]["voice"] == {"n": 2, "with_locator": 1}
    assert cov["totals"]["history"] == {"n": 2, "with_locator": 2}
    assert cov["rates"]["history"] == 1.0
    assert cov["rates"]["voice"] == pytest.approx(0.4)   # 2 of 5 voice items locatored
    assert cov["rates"]["conjectural"] is None           # no items anywhere -> no rate


def test_coupling_is_read_off_shared_windows(folded_repo):
    reach = soul_provenance.entity_reach(folded_repo)
    # Ada and Bo share exactly win_7; Bo and the apex share win_11; Ada and the apex share nothing.
    pairs = {(a, b): c for c, a, b in soul_provenance.top_couplings(reach)}
    assert pairs[("_APEX_TEST", "bo")] == 1
    assert pairs[("ada", "bo")] == 1
    assert ("_APEX_TEST", "ada") not in pairs            # zero-couplings dropped


def test_report_rich_sealed_and_summary_content_free(folded_repo):
    out = soul_provenance.write_report(folded_repo)
    assert out.is_file()
    rich = json.loads(out.read_text(encoding="utf-8"))
    assert any(c["a"] == "ada" and c["b"] == "bo" for c in rich["couplings"])

    s = soul_provenance.summary(folded_repo)
    assert s["n_entities"] == 3
    assert s["n_nonzero_couplings"] == 2
    assert s["max_coupling"] == 1
    blob = json.dumps(s).lower()
    for name in ("ada", "bo", "win_7"):                  # content-free: no names, no windows
        assert name not in blob


def test_scan_value_axis_producer(folded_repo):
    from laplace.engine.soul_dream import scan_value_axis

    items = scan_value_axis(folded_repo)
    by_kind = {}
    for it in items:
        by_kind.setdefault(it["kind"], []).append(it)

    # Ada (voice 0/2 locatored) and Bo (voice 1/2) need trait-provenance re-folds; the apex
    # (voice 1/1) is already covered and gets none.
    targets = {it["target"] for it in by_kind["trait_provenance"]}
    assert targets == {"ada", "bo"}
    # The cluster item rides as soon as ANY locator-carrying trait substrate exists (here 3:
    # bo's locatored voice + generator, the apex's voice) - no imposed threshold.
    assert len(by_kind["value_axis_cluster"]) == 1
    cluster = by_kind["value_axis_cluster"][0]
    assert "3 currently" in cluster["directive"]
    assert cluster["priority"] == 3
    assert all(it["priority"] == 2 for it in by_kind["trait_provenance"])


def test_value_axis_rides_assess(folded_repo):
    from laplace.engine.soul_dream import assess_soul

    assessment = assess_soul(folded_repo, grade=0)
    kinds = assessment["by_kind"]
    assert kinds.get("trait_provenance") == 2
    assert kinds.get("value_axis_cluster") == 1
    # Every value-axis item carries a sealed brief with the locator law in it.
    for it in assessment["frontier"]:
        if it["kind"] in ("trait_provenance", "value_axis_cluster"):
            assert "PROVENANCE (the locator law" in it["brief"]


def test_parse_wiring_retires_resolved_bullets(tmp_path):
    """A wire bullet drops from the frontier on its OWN '> RE-WIRED' marker (the conjugate of the
    friction ledger's per-block retirement) - not only when the whole file is resolved."""
    from laplace.engine.soul_dream import SHARD, parse_wiring

    folded = tmp_path / SHARD / "scaled_trancheW_folded"
    folded.mkdir(parents=True)
    (folded / "_WIRING_NOTES.md").write_text(
        "# wiring notes\n\n"
        "- **Open wire A → somewhere.** still to do\n\n"
        "- **Done wire B → elsewhere.** was executed\n"
        "> RE-WIRED 2026-06-10: B resolved into the standing world.\n\n"
        "- **Rejected merge C == D.** the author said no\n"
        "> AUTHOR-REJECTED: not the same person.\n",
        encoding="utf-8",
    )
    items = parse_wiring(tmp_path)
    targets = [i["target"] for i in items]
    assert any(t.startswith("Open wire A") for t in targets)        # open: stays
    assert not any(t.startswith("Done wire B") for t in targets)    # RE-WIRED: retired
    assert not any(t.startswith("Rejected merge C") for t in targets)  # rejected: dropped
    assert len(items) == 1


def test_briefs_carry_the_locator_law():
    for op, kind in (("reconsolidate", "author_correction"), ("wire", "cross_link"),
                     ("fold", "deferred_group")):
        brief = _brief({"op": op, "kind": kind, "directive": "d", "target": "t"})
        assert "PROVENANCE (the locator law" in brief
        assert "NEVER invent a locator" in brief
    # reshape stays advisory - no sealed wave, no locator demand.
    assert "PROVENANCE" not in _brief({"op": "reshape", "kind": "too_wide", "directive": "d"})


def test_render_entity_profile_is_mechanical_and_traceable():
    # reconstruction is a MECHANICAL render of the fold - no model, deterministic, every line
    # traced to its locator (his correction 2026-06-10: a model per reconstruction holds nothing)
    from laplace.engine import soul_provenance as sp
    data = {"name": "Jane Doe", "summary": "A test soul.",
            "voice": [{"trait": "dry wit", "locator": "c3.txt"}],
            "history": [{"event": "moved to NOLA", "locator": "c1.txt"}],
            "relations": [{"who": "Gerard", "note": "old friend", "locator": "c2.txt"}]}
    md = sp.render_entity_profile(data)
    assert md == sp.render_entity_profile(data)              # deterministic
    assert md.startswith("# Jane Doe")
    assert "A test soul." in md and "no model" in md
    assert "## Voice" in md and "## History" in md and "## Relations" in md
    assert "dry wit" in md and "_(c3.txt)_" in md            # traced to its source
    assert "**" not in md.split("##")[0]                     # no invented emphasis in the header
    # honest-null: a missing field yields no section, never an invented one
    assert "## Relations" not in sp.render_entity_profile({"name": "X", "voice": []})
