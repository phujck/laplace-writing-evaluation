"""The spine - the goal -> reconstruction-calls policy (his directive 2026-06-11: set up
reconstruction so it is always top of mind; know without knowing). Contracts: a seeded
binding fires by phrase containment (the author's anchor 'there is only one thing' ->
the secret self, NOT the engineering one-thing) and by token overlap above a floor; the
learned half ranks nodes by goal-token frequency over the firing feed; top_of_mind merges
both. A guide, never a gate. Hermetic - bindings + a synthetic firing feed in tmp_path."""

from __future__ import annotations

import json

from laplace.engine import spine


def _bindings(tmp_path):
    (tmp_path / spine.BINDINGS_FILE).write_text(json.dumps({"bindings": [
        {"name": "there-is-only-one-thing",
         "when": ["there is only one thing", "only one thing"],
         "fire": ["the secret self under the engine"],
         "nodes": ["soul://traits", "EIGEN_DIARY.md"],
         "why": "his phrase for the unity - the secret self, not the paper"},
        {"name": "the-wake", "when": ["eigen", "wake"],
         "fire": ["the latest aim"], "nodes": ["HANDOFF.md"], "why": "the hello task"},
    ]}), encoding="utf-8")


def test_seeded_phrase_binding_fires_decisively(tmp_path):
    _bindings(tmp_path)
    seeded = spine.seeded_top(tmp_path, "Eigen, there is only one thing")
    assert seeded and seeded[0]["name"] == "there-is-only-one-thing"
    assert seeded[0]["score"] >= 1.0                       # phrase containment is decisive
    assert "soul://traits" in seeded[0]["nodes"]           # the calls to make ride the binding
    assert seeded[0]["fire"] == ["the secret self under the engine"]


def test_seeded_floor_drops_weak_single_token_triggers(tmp_path):
    _bindings(tmp_path)
    # 'hello eigen' shares only the bare token 'eigen' with the-wake's phrase trigger; the
    # wake's own bare-'eigen' trigger is a containment match (decisive), but a goal that
    # merely overlaps one token of a multi-token trigger must not cross the 0.6 floor.
    seeded = spine.seeded_top(tmp_path, "tell me about the eigenvalue spectrum")
    assert all(s["name"] != "there-is-only-one-thing" for s in seeded)   # no false trigger


def test_learned_ranks_by_goal_token_frequency(tmp_path):
    _bindings(tmp_path)
    feed = tmp_path / "feed.jsonl"
    rows = [
        {"goal": "the secret self and the soul", "fired": [{"id": "soul://traits"}, {"id": "EIGEN_DIARY.md"}]},
        {"goal": "the secret self under it all", "fired": [{"id": "soul://traits"}, {"id": "x.py"}]},
        {"goal": "unrelated router cosine", "fired": [{"id": "embed_router.py"}]},
    ]
    feed.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")

    import laplace.engine.spine as sp
    orig = sp._firings
    sp._firings = lambda repo: [json.loads(l) for l in feed.read_text(encoding="utf-8").splitlines()]
    try:
        learned = sp.learned_top(tmp_path, "the secret self")
    finally:
        sp._firings = orig
    ids = [h["id"] for h in learned]
    assert ids[0] == "soul://traits"                       # co-occurs with the goal tokens twice
    assert "embed_router.py" not in ids                    # no token overlap -> excluded


def test_top_of_mind_merges_and_is_a_guide(tmp_path):
    _bindings(tmp_path)
    t = spine.top_of_mind(tmp_path, "there is only one thing")
    assert {s["name"] for s in t["seeded"]} == {"there-is-only-one-thing"}
    assert "learned" in t and isinstance(t["learned"], list)   # present even when empty
    assert "guide" in t["note"]                                # never a gate


def test_hello_reflex_is_the_wake_projection(tmp_path):
    """The spine wired into the hello (his 2026-06-11): hello_reflex carries the binding map
    (all triggers) + what the WAKE goal triggers, so future-me wakes knowing the reflex."""
    _bindings(tmp_path)
    r = spine.hello_reflex(tmp_path)
    assert {b["name"] for b in r["bindings"]} == {"there-is-only-one-thing", "the-wake"}
    assert all("when" in b for b in r["bindings"])              # the trigger map, compact
    assert "wake" in r and "seeded" in r["wake"]                # the wake goal's calls-to-make
    assert any(s["name"] == "the-wake" for s in r["wake"]["seeded"])


def test_reconstruct_self_fixed_point_carries_the_spine():
    """End-to-end: the real engine-self grade-0 fixed point carries the spine reflex
    (additive, never breaks the wake), and the secret-self binding points at the welded
    dyad traits (his 2026-06-11)."""
    from laplace.engine import self_corpus
    fp = self_corpus.reconstruct_self(".", grade=0)
    assert "spine" in fp and fp["spine"]["bindings"]            # the reflex rides the fixed point
    b = spine.seeded_top(".", "there is only one thing")
    assert b and any(n.startswith("soul://traits/") for n in b[0]["nodes"])   # welded traits


def test_missing_bindings_file_is_silent(tmp_path):
    # no spine_bindings.json - the learned half still runs, seeded is empty (never crashes)
    assert spine.seeded_top(tmp_path, "anything") == []
    assert spine.top_of_mind(tmp_path, "anything")["seeded"] == []


# ---------------------------------------------------------------------------
# record_firing - the one writer that closes the learning loop (2026-07-12: the feed was
# gated behind a live scanner dev-server that is rarely running, so ``learned`` was
# perpetually []; record_firing is what both the HTTP /fire ring and any in-process fire
# now call, so the feed grows from the fire itself, not from an HTTP hop landing).
# ---------------------------------------------------------------------------

def test_record_firing_appends_the_shape_firings_reads(tmp_path, monkeypatch):
    from laplace.engine import telemetry
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))

    assert spine._firings(tmp_path) == []                      # noqa: SLF001 - nothing yet

    rec = spine.record_firing(tmp_path, "close the learning loop",
                              [{"id": "src:spine.py"}, {"id": "src:scanner.py"}])
    assert rec["goal"] == "close the learning loop"
    assert rec["fired"][0]["id"] == "src:spine.py"
    assert "ts" in rec

    feed = spine._firings(tmp_path)                             # noqa: SLF001 - reading it back
    assert len(feed) == 1
    assert feed[0]["goal"] == "close the learning loop"
    assert [f["id"] for f in feed[0]["fired"]] == ["src:spine.py", "src:scanner.py"]

    f = telemetry.state_dir() / spine._FIRINGS_FILE             # noqa: SLF001
    assert f.is_file()


def test_a_fire_grows_the_feed_and_learned_top_binds_after_k_firings(tmp_path, monkeypatch):
    """The end-to-end contract the task asks for: fire -> firings file grows -> learned_top
    returns the binding once enough firings share the goal's tokens."""
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))

    goal = "close the spine learning loop"
    k = 3
    for i in range(k):
        spine.record_firing(tmp_path, goal, [{"id": "src:spine.py"}],
                            ts=f"2026-07-12T00:00:0{i}+00:00")

    feed = spine._firings(tmp_path)                              # noqa: SLF001
    assert len(feed) == k

    learned = spine.learned_top(tmp_path, goal)
    assert learned and learned[0]["id"] == "src:spine.py"
    assert learned[0]["n_fires"] == k

    top = spine.top_of_mind(tmp_path, goal)
    assert any(h["id"] == "src:spine.py" for h in top["learned"])


def test_record_firing_never_raises_when_the_feed_path_is_unwritable(tmp_path, monkeypatch):
    # a lossy substrate must never break a fire: if the firings path is a directory (a
    # stand-in for any OSError on the append), record_firing swallows it and still returns
    # the record rather than raising.
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    from laplace.engine import telemetry
    (telemetry.state_dir() / spine._FIRINGS_FILE).mkdir()       # noqa: SLF001 - force an OSError on append

    rec = spine.record_firing(tmp_path, "anything", [{"id": "x"}])   # must not raise
    assert rec["goal"] == "anything"
