"""The dials conjugate — the WRITE path over the pipeline calibration overlay.

Pure, tmp_path everywhere, no server: the profile dir is monkeypatched to a tmp
copy of the SHIPPED dials-v1.yaml, so the fold, the gate, and the round-trip are
exercised against the real defaults schema while the checked-in YAML is never
touched. Mirrors tests/test_storyboard.py's deterministic-core discipline.
"""
from __future__ import annotations

import json

import pytest

from laplace.web import dials_surface as ds
from laplace.pipeline import dials

pytestmark = pytest.mark.unit

_REAL_V1 = ds._REPO_ROOT / "profiles" / "pipeline" / "dials-v1.yaml"


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """A tmp copy of the shipped dials-v1.yaml, with the profile dir redirected to
    tmp. Returns the profile NAME (allowlist logic in dials.profile_path stays live)."""
    (tmp_path / "dials-v1.yaml").write_bytes(_REAL_V1.read_bytes())
    monkeypatch.setattr(dials, "profile_dir", lambda: tmp_path)
    return "dials-v1.yaml"


def _pdir(name="dials-v1.yaml"):
    return dials.profile_path(name)


# ---------------------------------------------------------------------------
# the fold — reduce_overlay / _apply_op (pure, no disk)
# ---------------------------------------------------------------------------

def test_set_materialises_an_absent_path():
    # empty base; set a leaf whose parents don't exist in the overlay yet
    over = ds.reduce_overlay({}, [{"kind": "set-leaf",
                                   "path": "loop.harnessed.max_passes", "value": 5}])
    assert over == {"loop": {"harnessed": {"max_passes": 5}}}


def test_set_overwrites_existing_leaf():
    base = {"loop": {"max_rounds": 4}}
    over = ds.reduce_overlay(base, [{"kind": "set-leaf",
                                     "path": "loop.max_rounds", "value": 9}])
    assert over == {"loop": {"max_rounds": 9}}


def test_reset_removes_and_prunes_empty_parents():
    base = {"loop": {"harnessed": {"max_passes": 6}}}
    over = ds.reduce_overlay(base, [{"kind": "reset-leaf",
                                     "path": "loop.harnessed.max_passes"}])
    # the leaf goes, then the now-empty harnessed dict, then the now-empty loop dict
    assert over == {}


def test_reset_keeps_non_empty_parents():
    base = {"loop": {"max_rounds": 4, "harnessed": {"max_passes": 6}}}
    over = ds.reduce_overlay(base, [{"kind": "reset-leaf",
                                     "path": "loop.harnessed.max_passes"}])
    assert over == {"loop": {"max_rounds": 4}}


def test_reset_absent_leaf_is_a_noop():
    base = {"loop": {"max_rounds": 4}}
    over = ds.reduce_overlay(base, [{"kind": "reset-leaf",
                                     "path": "loop.harnessed.max_passes"}])
    assert over == {"loop": {"max_rounds": 4}}


def test_malformed_op_is_skipped_not_raised():
    base = {"loop": {"max_rounds": 4}}
    ops = [
        {"kind": "bogus", "path": "loop.max_rounds", "value": 1},   # unknown kind
        {"kind": "set-leaf"},                                        # no path
        {"kind": "set-leaf", "path": "loop.max_rounds"},            # no value
        {"path": "loop.max_rounds", "value": 1},                    # no kind
    ]
    assert ds.reduce_overlay(base, ops) == base


def test_set_refuses_a_path_that_is_a_dict_in_defaults():
    # 'loop' is a dict in defaults, not a settable leaf -> the fold skips it
    assert ds.reduce_overlay({}, [{"kind": "set-leaf", "path": "loop", "value": 1}]) == {}


def test_reduce_is_deterministic_and_base_immutable():
    base = {"loop": {"max_rounds": 4}}
    seq = [{"kind": "set-leaf", "path": "loop.max_rounds", "value": 6},
           {"kind": "set-leaf", "path": "loop.verify_votes", "value": 3}]
    assert ds.reduce_overlay(base, seq) == ds.reduce_overlay(base, seq)
    assert base == {"loop": {"max_rounds": 4}}          # never mutated


def test_undo_is_prefix_replay():
    base = {"loop": {"max_rounds": 4}}
    seq = [{"kind": "set-leaf", "path": "loop.max_rounds", "value": 6},
           {"kind": "set-leaf", "path": "loop.max_rounds", "value": 8}]
    assert ds.reduce_overlay(base, seq)["loop"]["max_rounds"] == 8
    assert ds.reduce_overlay(base, seq[:-1])["loop"]["max_rounds"] == 6


# ---------------------------------------------------------------------------
# the gate — rejects touch NOTHING on disk
# ---------------------------------------------------------------------------

def test_unknown_path_rejected_before_disk(profile):
    pp = _pdir()
    before = pp.read_bytes()
    res = ds.dials_write(profile, {"kind": "set-leaf",
                                   "path": "loop.no_such_dial", "value": 1})
    assert res["ok"] is False and "unknown dial path" in res["error"]
    # the YAML is byte-identical and no ledger was written
    assert pp.read_bytes() == before
    assert not ds._ledger_path(pp, profile).exists()
    assert not ds._candidate_path(pp, profile).exists()


def test_version_leaf_is_refused(profile):
    res = ds.dials_write(profile, {"kind": "set-leaf",
                                   "path": "version", "value": "dials-v2"})
    assert res["ok"] is False and "version" in res["error"]
    assert not ds._ledger_path(_pdir(), profile).exists()


def test_enum_reject(profile):
    res = ds.dials_write(profile, {"kind": "set-leaf",
                                   "path": "loop.fix_mode", "value": "yolo"})
    assert res["ok"] is False and "fix_mode" in res["error"]
    assert not ds._ledger_path(_pdir(), profile).exists()


def test_type_reject(profile):
    res = ds.dials_write(profile, {"kind": "set-leaf",
                                   "path": "loop.max_rounds", "value": "banana"})
    assert res["ok"] is False and "expected int" in res["error"]


def test_bool_before_int_family(profile):
    # loop.max_rounds default is int -> a bool must NOT pass as an int
    res = ds.dials_write(profile, {"kind": "set-leaf",
                                   "path": "loop.max_rounds", "value": True})
    assert res["ok"] is False and "got bool" in res["error"]


def test_min_one_bound(profile):
    res = ds.dials_write(profile, {"kind": "set-leaf",
                                   "path": "loop.max_rounds", "value": 0})
    assert res["ok"] is False and ">= 1" in res["error"]


def test_fraction_bound(profile):
    res = ds.dials_write(profile, {"kind": "set-leaf",
                                   "path": "regen_grain.paragraph_max_fraction",
                                   "value": 1.5})
    assert res["ok"] is False and "(0, 1]" in res["error"]


def test_no_candidate_left_behind_on_reject(profile):
    ds.dials_write(profile, {"kind": "set-leaf", "path": "loop.fix_mode",
                             "value": "nope"})
    assert not ds._candidate_path(_pdir(), profile).exists()


# ---------------------------------------------------------------------------
# accepted writes — base banking, round-trip, list leaves, reset shrink
# ---------------------------------------------------------------------------

def test_first_write_banks_base_and_archive(profile):
    pp = _pdir()
    original = pp.read_bytes()
    ds.dials_write(profile, {"kind": "set-leaf", "path": "loop.max_rounds", "value": 6})
    bp = ds._base_path(pp, profile)
    assert bp.is_file()
    # the base is the ORIGINAL parsed overlay (max_rounds still 4, not 6)
    banked = json.loads(bp.read_text())
    assert banked["loop"]["max_rounds"] == 4
    # the pre-board YAML is archived byte-for-byte (header preserved)
    arch = pp.parent / "archive"
    copies = list(arch.glob(f"{profile}.preboard_*.yaml"))
    assert len(copies) == 1 and copies[0].read_bytes() == original


def test_accepted_write_round_trips(profile):
    res = ds.dials_write(profile, {"kind": "set-leaf",
                                   "path": "loop.max_rounds", "value": 6})
    assert res["ok"] is True
    assert res["round_trip"] == {"path": "loop.max_rounds", "requested": 6,
                                 "effective": 6, "source": "overlay", "ok": True}
    # an INDEPENDENT load of the rewritten profile shows the value
    fresh = dials.load_dials(_pdir())
    assert fresh["loop"]["max_rounds"] == 6


def test_list_leaf_set_and_reset(profile):
    pp = _pdir()
    val = ["R1", "R2"]
    res = ds.dials_write(profile, {"kind": "set-leaf",
                                   "path": "loop.lock.readers", "value": val})
    assert res["ok"] is True
    assert dials.load_dials(pp)["loop"]["lock"]["readers"] == val
    # reset returns the code default roster
    res2 = ds.dials_write(profile, {"kind": "reset-leaf",
                                    "path": "loop.lock.readers"})
    assert res2["ok"] is True
    assert dials.load_dials(pp)["loop"]["lock"]["readers"] == \
        dials.defaults()["loop"]["lock"]["readers"]


def test_list_leaf_rejects_non_str_elements(profile):
    res = ds.dials_write(profile, {"kind": "set-leaf",
                                   "path": "loop.lock.readers", "value": [1, 2]})
    assert res["ok"] is False and "list of str" in res["error"]


def test_reset_returns_default_and_shrinks_yaml(profile):
    pp = _pdir()
    # loop.harnessed.max_passes is NOT in the shipped v1 subset: set then reset
    ds.dials_write(profile, {"kind": "set-leaf",
                             "path": "loop.harnessed.max_passes", "value": 6})
    grown = pp.stat().st_size
    assert dials.load_dials(pp)["loop"]["harnessed"]["max_passes"] == 6

    res = ds.dials_write(profile, {"kind": "reset-leaf",
                                   "path": "loop.harnessed.max_passes"})
    assert res["ok"] is True
    assert res["round_trip"]["source"] == "default"
    # the code default (2) rules again, and the file shrank back
    assert dials.load_dials(pp)["loop"]["harnessed"]["max_passes"] == \
        dials.defaults()["loop"]["harnessed"]["max_passes"] == 2
    assert pp.stat().st_size < grown
    # the leaf is gone from the reduced overlay
    assert "harnessed" not in res["overlay"].get("loop", {})


def test_ledger_grows_by_one_per_accepted_write(profile):
    pp = _pdir()
    # THE ACTOR LAW: the actor is caller-supplied, never a default. A direct writer
    # attributes itself explicitly (here a named probe).
    ds.dials_write(profile, {"kind": "set-leaf", "path": "loop.max_rounds", "value": 6,
                             "by": "gerard"})
    ds.dials_write(profile, {"kind": "set-leaf", "path": "loop.verify_votes", "value": 2,
                             "by": "gerard"})
    from laplace.pipeline import ledger
    ops = ledger.read_jsonl(ds._ledger_path(pp, profile))
    assert len(ops) == 2
    assert all("ts" in o and o.get("by") == "gerard" for o in ops)


def test_undo_route(profile):
    pp = _pdir()
    ds.dials_write(profile, {"kind": "set-leaf", "path": "loop.max_rounds", "value": 6})
    ds.dials_write(profile, {"kind": "set-leaf", "path": "loop.verify_votes", "value": 3})
    res = ds.dials_undo(profile)
    assert res["ok"] is True and res["undone"] is True
    # the last op is dropped: verify_votes back to default, max_rounds still 6
    merged = dials.load_dials(pp)
    assert merged["loop"]["verify_votes"] == dials.defaults()["loop"]["verify_votes"]
    assert merged["loop"]["max_rounds"] == 6
    assert len(res["ops"]) == 1


def test_state_shape(profile):
    ds.dials_write(profile, {"kind": "set-leaf", "path": "loop.max_rounds", "value": 6})
    st = ds.dials_state(profile)
    assert set(st) == {"profile", "defaults", "overlay", "merged", "ops",
                       "base_present", "pending_runflip"}
    assert st["pending_runflip"] is None      # no run-flip armed = no recovery owed
    assert st["base_present"] is True
    assert st["merged"]["loop"]["max_rounds"] == 6
    assert st["overlay"]["loop"]["max_rounds"] == 6


# ---------------------------------------------------------------------------
# the handler
# ---------------------------------------------------------------------------

def test_handler_bad_json_400(profile):
    st, ct, body = ds.handle("/dials/op", {}, "POST", b"{not json")
    assert st == 400 and b"bad json" in body


def test_handler_profile_traversal_reject():
    # no fixture: the allowlist must reject a traversal shape before any disk touch
    res = ds.handle("/dials/state",
                    {"profile": ["../../etc/passwd"]}, "GET", b"")
    st, ct, body = res
    assert st == 400 and b"allowlist" in body


def test_handler_op_and_undo_roundtrip(profile):
    body = json.dumps({"profile": profile, "by": "gerard", "kind": "set-leaf",
                       "path": "loop.max_rounds", "value": 6}).encode()
    st, ct, out = ds.handle("/dials/op", {}, "POST", body)
    assert st == 200 and json.loads(out)["ok"] is True
    # the confirmed act is attributed to the CALLER-SUPPLIED actor, not a default
    assert ds.dials_state(profile)["ops"][-1]["by"] == "gerard"

    st2, _, out2 = ds.handle("/dials/undo", {},
                             "POST", json.dumps({"profile": profile}).encode())
    assert st2 == 200 and json.loads(out2)["ok"] is True


def test_handler_reject_is_422(profile):
    body = json.dumps({"profile": profile, "by": "gerard", "kind": "set-leaf",
                       "path": "loop.fix_mode", "value": "yolo"}).encode()
    st, ct, out = ds.handle("/dials/op", {}, "POST", body)
    assert st == 422 and json.loads(out)["ok"] is False


# THE ACTOR LAW (orchestrator ruling 2026-07-22) — the /dials/op door defaults
# nowhere: an unattributed POST is a 422, zero delta, his name never a default. The
# same guard as the desk's /desk/act. A probe/walk/audit-drive must identify itself.
def test_handler_op_missing_actor_is_422_zero_delta(profile):
    pp = _pdir()
    before = pp.read_bytes()
    body = json.dumps({"profile": profile, "kind": "set-leaf",
                       "path": "mech.overfull_floor_pt", "value": 8.0}).encode()
    st, ct, out = ds.handle("/dials/op", {}, "POST", body)
    assert st == 422, "an unattributed dial write must be refused (422)"
    j = json.loads(out)
    assert "by (explicit actor) is required" in j["error"]
    # zero delta: the YAML is byte-identical and NO ledger row was forged
    assert pp.read_bytes() == before
    assert not ds._ledger_path(pp, profile).exists()


def test_handler_op_blank_actor_is_422(profile):
    body = json.dumps({"profile": profile, "by": "   ", "kind": "set-leaf",
                       "path": "loop.max_rounds", "value": 6}).encode()
    st, ct, out = ds.handle("/dials/op", {}, "POST", body)
    assert st == 422 and "by (explicit actor)" in json.loads(out)["error"]


def test_run_flip_attributes_ops_to_the_run_not_a_default(profile):
    # a run's temporary flip attributes to the RUN identity, never his name by default
    ds.dials_run_flip(profile, _FLIP_OPS, "run-actor-t")
    last = ds.dials_state(profile)["ops"][-1]
    assert last["by"] == "run:run-actor-t", last
    ds.dials_run_restore(profile)


def test_handler_unknown_path_returns_none(profile):
    # the bare GET /dials path is owned by the SCANNER, not this module: it stays
    # unowned here -> None. W6: the scanner now 301s /dials -> /pipeline (the dials
    # editor rehoused in place per organ); this module still owns only /dials/*.
    assert ds.handle("/dials", {}, "GET", b"") is None
    assert ds.handle("/other", {}, "GET", b"") is None


# ---------------------------------------------------------------------------
# the editor — W6: dials.html DELETED (his ruling: "dials are useful but they need
# to be integrated into the pipeline"). THE PIPELINE SURFACE re-houses the editor IN
# PLACE per organ over the SAME wire endpoints; the dials-in-place logic lives in
# static_shared/pipeline-panes.mjs. The standalone page must be GONE and the pipeline
# editor must speak this module's contract (/dials/state + /dials/op + /dials/undo).
# ---------------------------------------------------------------------------

def test_dials_editor_rehoused_into_the_pipeline_surface():
    assert not (ds._REPO_ROOT / "src" / "laplace" / "dials.html").is_file(), \
        "dials.html must be DELETED — the dials editor rehoused into /pipeline (W6)"
    panes = ds._REPO_ROOT / "src" / "laplace" / "web" / "static_shared" / "pipeline-panes.mjs"
    assert panes.is_file(), "pipeline-panes.mjs (the dials-in-place editor) is missing on disk"
    text = panes.read_text(encoding="utf-8")
    assert "/dials/op" in text, "the pipeline editor must POST edits to /dials/op"
    assert "/dials/undo" in text, "the pipeline editor must offer undo via /dials/undo"


# ---------------------------------------------------------------------------
# the run-flip transaction — crash-safe replacement for flip + finally-restore
# (the voiced-run hazard: a session-resume kill before the restore leg left the
# global live profile flipped, dials restored by hand — C06/C14, 2026-07-19)
# ---------------------------------------------------------------------------

_FLIP_OPS = [{"kind": "set-leaf", "path": "loop.harnessed.max_passes", "value": 5}]


def _managed(profile):
    """Normalize a virgin profile into managed form (one write + undo) so
    byte-parity assertions compare managed-to-managed — first-ever write
    legitimately rewrites the hand-written YAML into the managed rendering."""
    ds.dials_write(profile, {"kind": "set-leaf", "path": "loop.max_rounds", "value": 6})
    ds.dials_undo(profile)


def test_run_flip_applies_and_banks_the_intent_record(profile):
    _managed(profile)
    before = _pdir(profile).read_bytes()
    res = ds.dials_run_flip(profile, _FLIP_OPS, "run-t1")
    assert res["ok"] and res["applied"] == 1
    assert _pdir(profile).read_bytes() != before          # the flip is live
    rec = ds._read_runflip(_pdir(profile), profile)
    assert rec and rec["run_id"] == "run-t1" and rec["ledger_len_before"] == 0
    # the pending flip surfaces on every state read — the recovery door visible
    assert ds.dials_state(profile)["pending_runflip"]["run_id"] == "run-t1"


def test_run_restore_pops_to_the_banked_mark_and_is_idempotent(profile):
    _managed(profile)
    before = _pdir(profile).read_bytes()
    ds.dials_run_flip(profile, _FLIP_OPS, "run-t2")
    res = ds.dials_run_restore(profile)
    assert res["ok"] and res["restored"] == 1
    assert _pdir(profile).read_bytes() == before          # byte-parity via the ledger
    assert ds.dials_state(profile)["pending_runflip"] is None
    # idempotent: a second restore (the recovery wake calling it again) is a no-op
    res2 = ds.dials_run_restore(profile)
    assert res2["ok"] and res2["restored"] == 0 and res2["pending"] is False


def test_run_restore_recovers_after_a_kill_at_any_point(profile):
    """Simulate the orphaned-runner kill: flip applied, restore leg never ran, a
    NEW session calls restore cold — the banked mark is enough."""
    _managed(profile)
    before = _pdir(profile).read_bytes()
    ds.dials_run_flip(profile, _FLIP_OPS, "run-killed")
    # (the runner dies here; nothing else happens until the next session)
    res = ds.dials_run_restore(profile)
    assert res["ok"] and res["restored"] == 1 and _pdir(profile).read_bytes() == before


def test_run_flip_refuses_a_second_flip_while_pending(profile):
    ds.dials_run_flip(profile, _FLIP_OPS, "run-a")
    res = ds.dials_run_flip(profile, _FLIP_OPS, "run-b")
    assert not res["ok"] and "pending" in res["error"]
    ds.dials_run_restore(profile)


def test_run_flip_refused_op_reverts_the_whole_flip(profile):
    """Gate honesty: one refused op = the whole flip reverts (refuse-and-revert),
    no record left pending, the profile byte-identical."""
    _managed(profile)
    before = _pdir(profile).read_bytes()
    ops = _FLIP_OPS + [{"kind": "set-leaf", "path": "not.a.real.dial", "value": 1}]
    res = ds.dials_run_flip(profile, ops, "run-bad")
    assert not res["ok"] and res.get("rejected")
    assert _pdir(profile).read_bytes() == before
    assert ds._read_runflip(_pdir(profile), profile) is None
