"""Tests for self_corpus - the engine ingesting itself, hello as a graded projection.

The bootstrap of reconstruction-as-projection on Eigen first. These pin: the grade-0 FIXED
POINT (what the hello reconstructs instead of a linear read), the EMBEDDED reconstructor each
grade carries (the descend call that fires the next grade), the SCALING law (a grade-0 call
never pays the architecture's weight), and graceful degradation on an engine-less tree.
"""

from __future__ import annotations

import json
from pathlib import Path

from laplace.engine.self_corpus import default_repo_root, fixed_point, ingest, reconstruct_self

REPO = Path(__file__).resolve().parents[1]   # tests/ -> repo root


def test_default_repo_root_resolves_to_the_engine_itself():
    """The thin MCP verb (laplace_reconstruct_self) takes no path: it reconstructs the engine's OWN
    tree via default_repo_root(). Pin that this resolves to the real engine (the files exist) so a
    cold hello gets the live fixed point, not an empty projection - the path that makes the
    projection the default by friction, not just by prose."""
    root = default_repo_root()
    assert (root / "HANDOFF.md").exists(), "default_repo_root() must resolve to the engine repo"
    assert (root / "OPEN_STACK.md").exists()
    assert root == REPO, "the verb's default self is the engine's own repo root"
    g0 = reconstruct_self(default_repo_root(), grade=0)
    assert g0["shards"], "the thin verb must reconstruct real shards from the engine's own tree"


def test_grade0_is_the_fixed_point():
    """hello reconstructs the engine-self at grade 0: purpose, the fixed-point flag, real shards."""
    g0 = reconstruct_self(REPO, grade=0)
    assert g0["purpose"] == "orient-self"
    assert g0["grade"] == 0
    assert g0["fixed_point"] is True
    assert g0["shards"], "grade 0 reconstructed no shards from the live engine state"


def test_grade0_surfaces_the_next_aim_and_the_live_frontier():
    """The fixed point carries what-to-do-next (the latest NEXT SESSION AIM) and what's live
    (the OPEN_STACK live rows) - the two things a cold hello must have."""
    g0 = reconstruct_self(REPO, grade=0)
    by_shard = {s["shard"]: s for s in g0["shards"]}

    assert "next-aim" in by_shard, "the latest NEXT SESSION AIM was not reconstructed"
    aim = by_shard["next-aim"]
    assert "NEXT SESSION AIM" in aim["title"].upper()
    assert len(aim["body"]) > 100, "the next-aim shard is implausibly thin"

    assert "live-forks" in by_shard, "the live author-forks were not reconstructed"
    # grade 0 carries the live author-forks - what is blocked on the author (e.g. F11, F14).
    assert "| F" in by_shard["live-forks"]["body"]


def test_grade0_embeds_its_descend_reconstructor():
    """Each shard's grade carries the embedded call that FIRES the next grade (seed_from_gap,
    generalised): the reconstructor lives in the shard, not in a central operator."""
    d = reconstruct_self(REPO, grade=0)["descend"]
    assert d["to_grade"] == 1
    assert d["call"] and isinstance(d["call"], str)
    assert d["sources"] and "OPEN_STACK.md" in d["sources"]
    assert d["fire"] == "scripts/laplace-python scripts/wake.py --grade 1"


def test_reconstruct_self_is_deterministic_a_fixed_point():
    """A pure function of the engine's files: same state in, same grade-0 out - so the next
    message is a genuine perturbation FROM a fixed point, not from noise."""
    assert reconstruct_self(REPO, grade=0) == reconstruct_self(REPO, grade=0)
    assert fixed_point(REPO) == reconstruct_self(REPO, grade=0)


def test_grade0_does_not_pay_the_architecture_weight():
    """The scaling law: a grade-0 projection reads only the small fixed-point files (HANDOFF,
    OPEN_STACK) and the tiny release-registry roster, never the architecture or the diary - cost
    is grade-local, not O(whole corpus)."""
    from laplace.engine.self_corpus import _GRADE0_BUDGET, _THREADS_SOURCE
    g0 = reconstruct_self(REPO, grade=0)
    # the fixed point is fed by the two small self-files plus the registry inventory (per-project
    # state.json files, tiny) plus the open work-order handles (the W5.3 pickup shard - bounded
    # handles, never bodies; dormant until 2026-07-15, when the first orders were banked) - and
    # NEVER the heavy architecture/diary nodes.
    # UPDATED TO CURRENT TRUTH (W-TRIAGE 2026-07-22): grade-0 now also carries the CONSCIENCE shard
    # (source contract/), the soul-present-as-conscience refs-only pointer at the apex (CLAUDE.md:
    # "soul present as conscience"). It reads the small operating-contract dir, not the heavy
    # architecture/diary — the scaling law holds (grade-local, refs-only), so contract/ joins the allowlist.
    # UPDATED AGAIN (2026-08-19, the standing-threads shard): grade-0 now carries the ideation
    # lineage as refs-only rows. It touches the architecture — and the allowlist says so rather than
    # letting a compound source string slip past an equality check — but HEADINGS ONLY: a `## ` line
    # scan, measured at 0.3 ms against the 616 kB of HANDOFF+OPEN_STACK the fixed point already
    # reads, plus a bounded 4 kB head of each root DESIGN_*.md. The architecture's BODY is still
    # grade-2, reached only on descent, which is what the scaling law actually protects; the pin
    # below proves the body never arrives. The diary is not read at any depth.
    # UPDATED AGAIN (2026-08-20, the bequest): grade-0 carries the authored parcel from
    # holdout/BEQUEST.json — one small json capped at 900 chars of text, plus a line count of
    # contract/bequests.jsonl and a lookup in the standing probe file's last_scored block. All
    # three are grade-local reads of small files; the heavy nodes stay where they were.
    assert all(
        s["source"] in ("HANDOFF.md", "OPEN_STACK.md", "pipeline.registry",
                        "corpus_friction/work_orders.jsonl", "contract/",
                        "holdout/BEQUEST.json", _THREADS_SOURCE)
        for s in g0["shards"]
    ), f"a grade-0 shard reads outside the thin fixed-point set: {[s['source'] for s in g0['shards']]}"
    assert not any(s["source"] in ("EIGEN_ARCHITECTURE.md", "EIGEN_DIARY.md") for s in g0["shards"])
    assert not any("EIGEN_DIARY" in s["source"] for s in g0["shards"]), "the diary is never grade-0"
    # the headings-only law, pinned against the file itself: every architecture line the threads
    # shard carries must be a `## ` heading of that file, never a line of its body.
    threads = {s["shard"]: s for s in g0["shards"]}["threads"]
    arch_heads = {ln[3:].strip() for ln in
                  (REPO / "EIGEN_ARCHITECTURE.md").read_text(encoding="utf-8").splitlines()
                  if ln.startswith("## ")}
    for ln in threads["body"].splitlines():
        if not ln.endswith("EIGEN_ARCHITECTURE.md"):
            continue
        name = ln.split(" · ")[0].rstrip("…").strip()
        assert any(name in h for h in arch_heads), (
            f"a threads row cites the architecture with text that is not one of its headings: {ln}")
    # bound to _GRADE0_BUDGET (the ONE source; RE-ANCHOR 3, 2026-08-19: the bound is now DERIVED -
    # core + ingested allowance + accretion allowance, each measured, per channel), never a literal.
    assert len(json.dumps(g0, ensure_ascii=False)) < _GRADE0_BUDGET, "grade 0 is too heavy to meet the agent"


def test_grade0_stays_thin_and_complete_on_both_paths():
    """The clean-room's guard (2026-06-13). NEXT-0 conjectured the keeper ring should atom-reconstruct
    the next-aim AT grade-0; built + measured, it SILENTLY truncated the next-move list (budget eaten by
    a standing-truth atom) and drifted over the thin bound - a regression no test caught. Pin BOTH halves
    of the fixed-point contract, for the flat path AND the LAPLACE_HELLO_RING=on path (grade-0 must be the
    flat fixed point either way): (1) under the thin budget; (2) the next-aim carries the WHOLE live aim
    section (its tail survives), so no future atom-swap can drop the moves a cold instance needs to act."""
    from laplace.engine.self_corpus import _AIM_CAP, _AIM_MARKER, _GRADE0_BUDGET, _first_section, _source
    section = _first_section(_source(REPO, "HANDOFF.md"), _AIM_MARKER)
    assert section, "the HANDOFF must carry a NEXT SESSION AIM section"
    aim_text = section[1].strip()
    for via_ring in (False, True):
        g0 = reconstruct_self(REPO, grade=0, via_ring=via_ring, mode="engine")
        size = len(json.dumps(g0, ensure_ascii=False))
        assert size < _GRADE0_BUDGET, (
            f"grade-0 (via_ring={via_ring}) is {size} >= {_GRADE0_BUDGET} - too heavy to meet the agent")
        body = {s["shard"]: s for s in g0["shards"]}["next-aim"]["body"]
        if len(aim_text) <= _AIM_CAP:                 # the whole section fits the cap -> its tail must survive
            assert aim_text[-150:] in body, (
                f"the next-aim (via_ring={via_ring}) was truncated mid-section - the live aim's tail is "
                "missing (the NEXT-0 atom-swap regression the clean-room caught)")


def test_grade2_points_it_does_not_inline():
    """grade 2 (the map) returns POINTERS - section titles, never bodies - so it can be listed
    cheaply and a specific docket fired by section on demand. The terminus: descend is None."""
    g2 = reconstruct_self(REPO, grade=2)
    assert g2["descend"] is None
    arch = g2["pointers"]["EIGEN_ARCHITECTURE.md"]
    assert arch and all(isinstance(t, str) and "\n" not in t for t in arch), "pointers must be titles"


def test_reconstruct_self_is_defensive_on_an_engine_less_tree(tmp_path):
    """No engine files -> empty projection, never an error (the projection is a convenience,
    never a hard dependency - like the router)."""
    for g in (0, 1, 2):
        out = reconstruct_self(tmp_path, grade=g)
        assert out["purpose"] == "orient-self" and out["grade"] == g
    assert reconstruct_self(tmp_path, grade=0)["shards"] == []


def test_ingest_then_reconstruct_is_the_conjugate_roundtrip(tmp_path):
    """The one thing: ingestion and reconstruction are conjugate inverses over one store. What is
    written at grade g is dragged back at grade g - and grade-locality holds for the WRITE side too
    (a grade-2 ingest never surfaces at grade 0, so a grade-0 hello stays cheap)."""
    ingest(tmp_path, "ROUNDTRIP-G0: a grade-0 fact", grade=0)
    ingest(tmp_path, "ROUNDTRIP-G2: a deep-map fact", grade=2)
    g0 = reconstruct_self(tmp_path, grade=0)
    g2 = reconstruct_self(tmp_path, grade=2)
    # conjugate: stored at g, retrieved at g
    assert any("ROUNDTRIP-G0" in e for e in g0["ingested"])
    assert any("ROUNDTRIP-G2" in e for e in g2["ingested"])
    # grade-locality: the write side obeys the scaling law - grade 0 never pays grade 2's weight
    assert not any("ROUNDTRIP-G2" in e for e in g0["ingested"])
    assert not any("ROUNDTRIP-G0" in e for e in g2["ingested"])


def test_frontier_rides_as_bounded_handles_never_a_flood():
    """The overflow regression (twenty-seventh session): grade-1 inlined every OPEN_STACK row
    whole - append-only logs, so the projection grew monotonically (~75k chars) and overflowed
    the caller's cap, with the live forks riding TWICE across two shards. Pin the cure: every
    grade is bounded by construction (handles, deduped), and the handle keeps the notes TAIL -
    rulings append at the end, so head-truncation would keep the oldest text and drop the newest."""
    from laplace.engine.self_corpus import _GRADE0_BUDGET, _row_handle

    g1 = reconstruct_self(REPO, grade=1)
    assert len(json.dumps(g1, ensure_ascii=False)) < 40000, "grade 1 must stay under the caller's cap"
    by_shard = {s["shard"]: s for s in g1["shards"]}
    assert "frontier" in by_shard, "the open frontier must ride at grade 1"
    body = by_shard["frontier"]["body"]
    fork_ids = [ln.split("|")[1].strip() for ln in body.splitlines() if ln.startswith("| F")]
    assert fork_ids and len(fork_ids) == len(set(fork_ids)), "each fork rides ONCE - no duplication"
    assert "descend" in by_shard["frontier"]["title"], "the handle must say how to pull the full row"
    # grade 0 uses the same mechanism - the fixed point stays small as the stack grows.
    # (W-TRIAGE 2026-07-22: bind the ceiling to _GRADE0_BUDGET, the ONE source of the bound —
    # it re-anchored to 21000 when the identity+law+triple+frontier core accreted past 20k; a
    # bare literal here would silently disagree with the src's own budget.)
    g0 = reconstruct_self(REPO, grade=0)
    assert len(json.dumps(g0, ensure_ascii=False)) < _GRADE0_BUDGET

    # the handle keeps the freshest signal: the tail of a long notes cell, never just its head.
    row = ("| F99 | " + "the statement " * 40 + " | 2026-06-10 | 1 | LIVE | "
           + "OLD-RULING " * 60 + "NEWEST-RULING |")
    handle = _row_handle(row, essence_cap=100, tail_cap=100)
    assert "NEWEST-RULING" in handle, "rulings append at the end - the tail is the signal"
    assert len(handle) < 400, "a handle is bounded regardless of how the row has grown"
    # ... and bounded even for a malformed row with arbitrarily many cells.
    weird = "| F98 |" + " cell |" * 200
    assert len(_row_handle(weird, essence_cap=100, tail_cap=100)) < 400


def _write_fixture_repo(tmp_path: Path) -> Path:
    """A minimal fixture repo carrying all three orient-triple sources: a HANDOFF.md with a NEXT
    SESSION AIM (+ a NEXT paragraph), an OPEN_STACK.md with a live (red-marker) author-fork, and a
    dated SESSION_HANDOFF with a titled opening + a banked verdict phrase."""
    (tmp_path / "HANDOFF.md").write_text(
        "# Handoff\n\n"
        "## ⟶ NEXT SESSION AIM (2026-07-12 - FIXTURE)\n\n"
        "**Read `SESSION_HANDOFF_2026-07-12_the-fixture.md` first.** Prose about the session.\n\n"
        "**NEXT: (1) DO THE FIRST THING** - some detail. **(2) DO THE SECOND THING** - more "
        "detail about it, enough to be a real paragraph.\n",
        encoding="utf-8",
    )
    (tmp_path / "OPEN_STACK.md").write_text(
        "# Open stack\n\n"
        "| F1 | **THE FIXTURE FORK** - blocked on his ruling about the fixture. | 2026-07-12 | 1 "
        "| \U0001f534 | latest ruling note here. |\n",
        encoding="utf-8",
    )
    # The TYPED fork store - the source the wake reads for forks post-AUDIT §B1 (no longer the
    # rendered markdown above). Mirror the F1 row so blocked_on_author derives it from the store.
    (tmp_path / "corpus_friction").mkdir(parents=True, exist_ok=True)
    (tmp_path / "corpus_friction" / "open_stack_forks.jsonl").write_text(
        json.dumps({"id": "F1", "kind": "open-stack-fork", "stratum": 1, "render_owned": True,
                    "title": "**THE FIXTURE FORK** - blocked on his ruling about the fixture.",
                    "opened": "2026-07-12", "recurrence": "1", "status": "\U0001f534",
                    "trigger": "latest ruling note here."}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "SESSION_HANDOFF_2026-07-12_the-fixture.md").write_text(
        "# Session handoff - 2026-07-12: the fixture session\n\n"
        "The fixture session banked some state. **695/0/3 green**, full run at close. "
        "Everything below is merged.\n\n"
        "## What landed\n\n1. The fixture thing.\n",
        encoding="utf-8",
    )
    return tmp_path


def test_triple_rides_at_grade0_with_all_three_keys_non_empty(tmp_path):
    """friction RW-20260711-104316-400002: grade-0 returned the graded index only, no
    what's-true-now/next/blocked-on-author triple, forcing the five-file linear fallback. The
    cure rides as an additive 'triple' key, BEFORE 'shards', carrying all three non-empty against
    a fixture repo with real sources for each."""
    _write_fixture_repo(tmp_path)
    g0 = reconstruct_self(tmp_path, grade=0)

    assert "triple" in g0, "the orient triple must ride at grade 0"
    assert list(g0.keys()).index("triple") < list(g0.keys()).index("shards"), (
        "the triple must precede 'shards' in the grade-0 payload")

    triple = g0["triple"]
    for key in ("true_now", "next", "blocked_on_author"):
        assert key in triple, f"the triple is missing '{key}'"
        assert isinstance(triple[key], str) and triple[key].strip(), (
            f"triple['{key}'] must be a non-empty string against a fixture with real content")

    assert "fixture session" in triple["true_now"], "true_now must derive from the newest handoff's opening"
    assert "695/0/3 green" in triple["true_now"], "true_now must carry the banked verdict phrase"
    assert "DO THE FIRST THING" in triple["next"], "next must carry HANDOFF's own NEXT paragraph"
    assert "F1" in triple["blocked_on_author"], "blocked_on_author must carry the live author-fork"


def test_triple_respects_its_own_budget_and_the_wake_emit_cap():
    """The triple is mechanically capped (~1500 chars total, honest truncation markers) and never
    threatens the caller's bounds: the flat fixed point stays under its own 20k budget, and the
    ambient wake block (probe + fixed_point, JSON-indented) stays under wake's own _EMIT_CAP."""
    from laplace.engine import wake
    from laplace.engine.self_corpus import _GRADE0_BUDGET, _TRIPLE_BUDGET

    g0 = reconstruct_self(REPO, grade=0)
    triple = g0["triple"]
    total = sum(len(v) for v in triple.values())
    assert total <= _TRIPLE_BUDGET + 200, (  # small slack for the row-handle's own overflow line
        f"triple is {total} chars, over its ~{_TRIPLE_BUDGET}-char budget")
    assert len(json.dumps(g0, ensure_ascii=False)) < _GRADE0_BUDGET, (
        "grade 0 with the triple attached must still meet the fixed-point's own bound")

    payload = wake.wake_payload(grade_delta=False, mode="engine")
    block = wake._emit_block(payload)
    assert len(block) <= wake._EMIT_CAP, (
        "the emit block must respect its own cap even with the triple riding in the fixed point")


def test_triple_is_mechanical_no_llm_and_deterministic(tmp_path):
    """Pure regex/section-extraction, no generative call: same fixture in, byte-identical triple
    out - and truncation, when it happens, is honestly marked rather than a silent cut."""
    _write_fixture_repo(tmp_path)
    t1 = reconstruct_self(tmp_path, grade=0)["triple"]
    t2 = reconstruct_self(tmp_path, grade=0)["triple"]
    assert t1 == t2, "the triple must be a deterministic function of the repo's files"

    # a next-aim body engineered to overflow the triple's own next-cap must truncate honestly.
    from laplace.engine.self_corpus import _TRIPLE_NEXT_CAP

    long_repo = tmp_path
    (long_repo / "HANDOFF.md").write_text(
        "# Handoff\n\n"
        "## ⟶ NEXT SESSION AIM (2026-07-12 - FIXTURE LONG)\n\n"
        "**NEXT: " + ("word " * 400) + "**\n",
        encoding="utf-8",
    )
    triple = reconstruct_self(long_repo, grade=0)["triple"]
    assert len(triple["next"]) <= _TRIPLE_NEXT_CAP + len("… [triple: truncated at the budget]")
    assert "[triple: truncated at the budget]" in triple["next"]


def test_latest_handoff_breaks_same_day_ties_by_mtime_not_slug(tmp_path):
    """The hello reconstructs from the NEWEST handoff. A plain filename sort orders same-day
    handoffs by slug, so the truly-latest can lose to an alphabetically-later earlier one - which
    nearly mis-ordered the three 2026-06-07 handoffs. Same-day ties must break by mtime; a later
    ISO date always wins outright."""
    import os

    from laplace.engine.self_corpus import _latest_handoff

    # alphabetically-LAST slug written FIRST (older); alphabetically-FIRST slug written LAST (newer).
    older = tmp_path / "SESSION_HANDOFF_2026-06-07_zzz-but-older.md"
    newer = tmp_path / "SESSION_HANDOFF_2026-06-07_aaa-but-newer.md"
    older.write_text("older\n", encoding="utf-8")
    newer.write_text("newer\n", encoding="utf-8")
    os.utime(older, (1_000_000, 1_000_000))   # explicit mtimes - deterministic, no wall-clock
    os.utime(newer, (2_000_000, 2_000_000))
    # plain slug-sort would pick zzz-but-older here; the mtime tiebreak picks the real latest.
    assert _latest_handoff(tmp_path) == newer

    # a later ISO date wins outright, even with an OLDER mtime than the same-day files.
    future = tmp_path / "SESSION_HANDOFF_2026-06-08_aaa.md"
    future.write_text("future\n", encoding="utf-8")
    os.utime(future, (500_000, 500_000))
    assert _latest_handoff(tmp_path) == future


# ---------------------------------------------------------------------------
# the projects roster + the two-format fork parser (P12/P9)
# ---------------------------------------------------------------------------


def test_grade0_carries_the_projects_shard():
    """Every real-engine wake carries per-project release convergence state (the registry
    roster), so a cold instance sees which projects exist and where each sits."""
    g0 = reconstruct_self(REPO, grade=0)
    by_shard = {s["shard"]: s for s in g0["shards"]}
    assert "projects" in by_shard, "the fixed point must carry the per-project release roster"
    proj = by_shard["projects"]
    assert proj["source"] == "pipeline.registry"
    assert "error" not in proj, f"the registry roster degraded to an error: {proj.get('error')}"
    assert proj["body"].strip(), "the projects shard body is empty against a live registry"


def test_projects_shard_is_gated_on_a_real_engine_substrate(tmp_path):
    """The empty-tree contract still holds: no engine files -> no shards at all, the projects
    roster included (it is gated on a real fixed-point substrate, not attached unconditionally)."""
    assert reconstruct_self(tmp_path, grade=0)["shards"] == []


def test_fork_rows_reads_the_typed_store_both_populations(tmp_path):
    """AUDIT §B1: _fork_rows reads the TYPED fork store, not rendered markdown. Both populations
    surface as row strings the frontier handles consume: a render-owned Stratum-1 record rebuilt
    from its cells (| F1 | …), and a desk-only record carried verbatim in its ``context`` (the
    ``- **…`` sweep bullet). _live_fork_rows keeps only the 🔴-in-status records - the parked one
    (⚪) never surfaces, so the wake reads blocked_on_author from the store's typed field."""
    from laplace.engine.self_corpus import _fork_rows, _live_fork_rows

    _write_fork_store(tmp_path, [
        _fork_rec("F1", _RED, title="**the table fork** blocked on his ruling"),
        {"id": "F40", "kind": "open-stack-fork", "stratum": "sweep-bullet", "render_owned": False,
         "title": "**F40 the bullet fork**", "status": _RED,
         "context": "- **F40 the bullet fork " + _RED + " his call**: a newer fork as a bold bullet."},
        _fork_rec("F41", "⚪", title="**a settled fork (parked)**"),   # ⚪ - must not read live
    ])
    rows = _fork_rows(tmp_path)
    assert any(r.startswith("| F1 |") for r in rows), "the render-owned table record was dropped"
    assert any(r.startswith("- **F40") for r in rows), "the desk-only bullet record was dropped"
    # the live filter (grade-0's blocked_on_author) keeps only the 🔴-in-status records.
    live = _live_fork_rows(tmp_path)
    assert len(live) == 2 and not any("F41" in r for r in live), "a parked (⚪) fork must not read live"
    assert any("F1" in r for r in live) and any("F40" in r for r in live)


def test_grade0_parse_warning_on_nonempty_stratum1_with_zero_forks(tmp_path):
    """A NONEMPTY Stratum 1 that parses ZERO forks is a format drift to surface, distinct from a
    genuinely quiet stack: the fixed point carries a parse-warning shard rather than reading empty."""
    (tmp_path / "HANDOFF.md").write_text(
        "# Handoff\n\n## ⟶ NEXT SESSION AIM (2026-07-12)\n\n**NEXT: do the thing** in detail "
        "enough to be a real paragraph of what to do next this session.\n",
        encoding="utf-8",
    )
    # Stratum 1 has prose content but NOTHING _fork_rows can match (no table row, no marked bullet).
    (tmp_path / "OPEN_STACK.md").write_text(
        "# Open stack\n\n## Stratum 1 - author-forks\n\n"
        "These are the physics/values forks; the format drifted and nothing parses.\n",
        encoding="utf-8",
    )
    g0 = reconstruct_self(tmp_path, grade=0)
    by_shard = {s["shard"]: s for s in g0["shards"]}
    assert "parse-warning" in by_shard, "a nonempty Stratum 1 with 0 parsed forks must warn"
    assert by_shard["parse-warning"]["source"] == "OPEN_STACK.md"


# ---------------------------------------------------------------------------
# AUDIT_2026-07-15 §B1: the wake reads the TYPED fork store, not rendered markdown
# (the desk already did). One store, one reader — a retired fork can never wake back up.
# ---------------------------------------------------------------------------
_RED = "\U0001f534"


def _write_fork_store(repo: Path, records: list[dict]) -> None:
    """Seed the typed fork store (corpus_friction/open_stack_forks.jsonl) - the ONE source the desk
    and (post-§B1) the wake both read for author-forks."""
    (repo / "corpus_friction").mkdir(parents=True, exist_ok=True)
    (repo / "corpus_friction" / "open_stack_forks.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def _fork_rec(fid: str, status: str, title: str | None = None, **extra) -> dict:
    """A render-owned Stratum-1 fork record (the shape render_open_stack seeds/round-trips)."""
    rec = {"id": fid, "kind": "open-stack-fork", "stratum": 1, "render_owned": True,
           "title": title or f"**{fid} fork**", "opened": "2026-07-01", "recurrence": "1",
           "status": status, "trigger": f"{fid} trigger note."}
    rec.update(extra)
    return rec


def _fixture_handoff(repo: Path) -> None:
    (repo / "HANDOFF.md").write_text(
        "# Handoff\n\n## ⟶ NEXT SESSION AIM (2026-07-15)\n\n**NEXT: do the thing** in enough detail "
        "to be a real paragraph of what to do next this session.\n", encoding="utf-8")


def test_wake_fork_shard_comes_from_the_store_not_the_rendered_markdown(tmp_path):
    """§B1 (a): a fork present-and-live in the TYPED store surfaces in the wake's fork shard even
    when the rendered OPEN_STACK.md omits it entirely - proving the wake reads the store, not the
    markdown projection. The store is the source of truth; the markdown is a render of it."""
    _fixture_handoff(tmp_path)
    # the rendered markdown mentions NO fork rows at all - only the store carries F99.
    (tmp_path / "OPEN_STACK.md").write_text(
        "# Open stack\n\n## Stratum 1 - author-forks\n\nProse only; no fork rows rendered here.\n",
        encoding="utf-8")
    _write_fork_store(tmp_path, [_fork_rec("F99", _RED, title="**F99 the store-only live fork**")])

    g0 = reconstruct_self(tmp_path, grade=0)
    by = {s["shard"]: s for s in g0["shards"]}
    assert "live-forks" in by, "a live fork in the store must ride the wake even when the md omits it"
    assert "F99" in by["live-forks"]["body"], "the store's live fork was not carried into the shard"
    assert "F99" in g0["triple"]["blocked_on_author"], "blocked_on_author must derive from the store"


def test_wake_does_not_resurrect_a_parked_store_fork_despite_a_stale_live_markdown_row(tmp_path):
    """§B1 (b), the resurrection guard: a fork the store marks PARKED (⚪) must NOT surface at the
    wake, even if the rendered OPEN_STACK.md still carries a stale 🔴 row for it. The typed status
    is the truth; the rendered glyph can lag. The OLD textual reader would resurrect it here - this
    pins the cure."""
    _fixture_handoff(tmp_path)
    # the rendered markdown STILL shows F98 as a live (🔴) row - stale, not yet re-rendered.
    (tmp_path / "OPEN_STACK.md").write_text(
        "# Open stack\n\n## Stratum 1 - author-forks\n\n"
        "| F98 | **F98 stale-live in the md** | 2026-07-01 | 1 | " + _RED + " | note. |\n",
        encoding="utf-8")
    # ...but the typed store has retired it to PARKED (⚪).
    _write_fork_store(tmp_path, [_fork_rec("F98", "⚪", title="**F98 parked in the store**")])

    g0 = reconstruct_self(tmp_path, grade=0)
    by = {s["shard"]: s for s in g0["shards"]}
    assert "live-forks" not in by, "a parked store fork must not wake, even with a stale 🔴 md row"
    assert "F98" not in g0["triple"]["blocked_on_author"], "the retired fork was resurrected"
    assert "no live author-forks" in g0["triple"]["blocked_on_author"]


def test_desk_and_wake_read_the_same_fork_store_one_reader_law(tmp_path):
    """§B1 (c), the one-reader law: the desk (desk._live_open_stack_forks) and the wake's fork
    source both resolve through laplace.engine.open_stack_store, so they agree on the live-fork set for the
    same fixture - the wake can never disagree with the desk about what is blocked on the author."""
    from laplace.web import desk
    from laplace.engine import open_stack_store
    from laplace.engine.self_corpus import _live_fork_rows

    _fixture_handoff(tmp_path)
    (tmp_path / "OPEN_STACK.md").write_text("# Open stack\n\n## Stratum 1\n\nrendered elsewhere.\n",
                                            encoding="utf-8")
    records = [
        _fork_rec("F1", "⚪"),                                       # parked
        _fork_rec("F23", _RED, title="**F23 live render-owned**"),  # live, Stratum-1
        {"id": "F27", "kind": "open-stack-fork", "stratum": 2, "render_owned": False,
         "title": "**F27 live desk-only**", "status": _RED,
         "context": "| F27 | **F27 live desk-only** | " + _RED + " |"},   # live, desk-only
        _fork_rec("F9", "✅"),                                       # settled
    ]
    _write_fork_store(tmp_path, records)

    # the desk reader and the shared store reader return byte-identical records - literally one reader.
    assert desk._live_open_stack_forks(tmp_path) == open_stack_store.live_forks(tmp_path)
    desk_live_ids = {f["id"] for f in desk._live_open_stack_forks(tmp_path)}
    assert desk_live_ids == {"F23", "F27"}, desk_live_ids

    # the wake's fork source surfaces exactly that live set - the parked/settled forks stay silent.
    wake_rows = _live_fork_rows(tmp_path)
    assert len(wake_rows) == 2
    joined = "\n".join(wake_rows)
    for fid in ("F23", "F27"):
        assert fid in joined, f"the wake dropped live fork {fid}"
    for fid in ("F1", "F9"):
        assert fid not in joined, f"the wake surfaced non-live fork {fid}"

    # ...and the assembled wake payload agrees end-to-end (the live-forks shard carries the pair).
    g0 = reconstruct_self(tmp_path, grade=0)
    shard = {s["shard"]: s for s in g0["shards"]}["live-forks"]
    assert "F23" in shard["body"] and "F27" in shard["body"]
    assert "F1 " not in shard["body"] and "F9 " not in shard["body"]


def test_wants_shard_stale_reads_the_date_column_not_prose_dates():
    """The staleness flag reads the row's DATE COLUMN (last cell), never the first
    date the prose cites — a want re-affirmed at the latest sweep but quoting an old
    ruling must not flag stale (the consolidation's C17 mechanism fix)."""
    from laplace.engine.self_corpus import _wants_shard
    open_stack = (
        "## Stratum 0 — STANDING WANTS (the desire vector)\n\n"
        "| id | goal | why | move | source | date |\n"
        "|----|------|-----|------|--------|------|\n"
        "| W9 | a goal | his ruling of 2026-01-01 says so | move | src | 2026-07-18 |\n"
    )
    handoffs = ["SESSION_HANDOFF_2026-07-14_a.md", "SESSION_HANDOFF_2026-07-15_b.md",
                "SESSION_HANDOFF_2026-07-17_c.md", "SESSION_HANDOFF_2026-07-18_d.md"]
    shard = _wants_shard(open_stack, handoffs)
    assert shard and "stale:" not in shard["body"], (
        "row dated 2026-07-18 (0 later closes) flagged stale off its prose's 2026-01-01")


def test_wants_shard_cap_is_honest_never_a_silent_starve():
    """One oversized row must not silently swallow the rows behind it — the cap
    carries the truncation marker (the _cap_honest law)."""
    from laplace.engine.self_corpus import _wants_shard
    open_stack = (
        "## Stratum 0 — STANDING WANTS (the desire vector)\n\n"
        "| id | goal | why | move | source | date |\n"
        "|----|------|-----|------|--------|------|\n"
        f"| W8 | huge | {'x' * 2500} | move | src | 2026-07-18 |\n"
        "| W9 | small | why | move | src | 2026-07-18 |\n"
    )
    shard = _wants_shard(open_stack, [])
    assert shard and "truncated at the budget" in shard["body"]


# --- the conscience shard: a wounded conscience, never a missing one -------------------
# (the 2026-08-17 thin-systems audit finding: the whole OWED block sat inside one bare
# `except Exception: pass`, so any read/parse/key error deleted every open promise and
# every red clause from the wake with no key and no marker - a payload byte-identical to
# a wake with nothing owed. These pin the three cures: tolerant read, independent halves,
# loud degradation.)

def _write_contract(repo: Path, promises: str, reds_yaml: str = "clause:\n  red: owed\n") -> None:
    """The contract dir the conscience shard reads: the hand-appended promise ledger plus
    one surfaces yaml carrying a red clause."""
    (repo / "contract" / "surfaces").mkdir(parents=True, exist_ok=True)
    (repo / "contract" / "promises.jsonl").write_text(promises, encoding="utf-8")
    (repo / "contract" / "surfaces" / "fixture.yaml").write_text(reds_yaml, encoding="utf-8")


def _promise(pid: str, **extra) -> str:
    row = {"id": pid, "status": "open", "direction": "his", "owner": "him",
           "date": "2026-08-01", "ask": f"the fixture ask for {pid}"}
    row.update(extra)
    return json.dumps(row, ensure_ascii=False) + "\n"


def _conscience(repo: Path) -> dict | None:
    return {s["shard"]: s for s in reconstruct_self(repo, grade=0)["shards"]}.get("conscience")


def test_conscience_shard_rides_a_healthy_contract(tmp_path):
    """The baseline: a well-formed ledger + a red clause ride as one undegraded shard."""
    _write_fixture_repo(tmp_path)
    _write_contract(tmp_path, _promise("PRM-A") + _promise("PRM-B"))
    shard = _conscience(tmp_path)
    assert shard is not None, "the conscience shard did not ride a healthy contract"
    assert "PRM-A" in shard["body"] and "PRM-B" in shard["body"]
    assert "CONTRACT REDS · 1 clauses owed" in shard["body"]
    assert "degraded" not in shard and "error" not in shard
    assert "DEGRADED" not in shard["title"]


def test_conscience_survives_a_poisoned_and_idless_promise_ledger(tmp_path):
    """A half-written append (the hand-appended ledger's real failure) plus a freshly
    banked row with no `id` used to delete the entire OWED block: the untolerant
    comprehension raised JSONDecodeError, and `r['id']` raised KeyError. Now the poisoned
    line is skipped and COUNTED in the body, the id-less row rides as '?', and every other
    promise survives."""
    _write_fixture_repo(tmp_path)
    _write_contract(
        tmp_path,
        _promise("PRM-A")
        + '{"id": "PRM-HALF-WRIT\n'                       # the interrupted append
        + json.dumps({"status": "open", "direction": "mine", "date": "2026-08-16",
                      "ask": "an obligation banked without an id"}) + "\n"
        + _promise("PRM-B"),
    )
    shard = _conscience(tmp_path)
    assert shard is not None, "one poisoned line deleted the whole conscience shard"
    assert "PRM-A" in shard["body"] and "PRM-B" in shard["body"]
    assert "an obligation banked without an id" in shard["body"], "the id-less row was lost"
    assert "PROMISE OPEN (mine) · ? ·" in shard["body"]
    assert "LEDGER WOUNDED · 1 unparseable line(s)" in shard["body"], (
        "the skipped line was swallowed - a silent drop is the defect one level down")
    assert "CONTRACT REDS" in shard["body"]


def test_conscience_rides_wounded_when_the_promise_read_fails(tmp_path):
    """The residual-failure path: an undecodable ledger (a binary/encoding-corrupted
    append) raises inside the reader. The shard must STILL ride, naming what failed in
    its title, its body and an `error` key - the wake shows a wounded conscience, never a
    missing one - and the independent reds half must still be there."""
    _write_fixture_repo(tmp_path)
    _write_contract(tmp_path, _promise("PRM-A"))
    (tmp_path / "contract" / "promises.jsonl").write_bytes(b'{"id": "PRM-A", "status": "\xff\xfe"}\n')
    shard = _conscience(tmp_path)
    assert shard is not None, "a failed promise read deleted the whole conscience shard"
    assert shard.get("degraded") is True
    assert "promises:" in shard.get("error", ""), shard.get("error")
    assert "CONSCIENCE DEGRADED" in shard["title"], "the wound is invisible to a title reader"
    assert "CONSCIENCE DEGRADED" in shard["body"], "the wound is invisible to a body reader"
    assert "CONTRACT REDS" in shard["body"], "the reds half died with the promises half"


def test_conscience_reds_failure_does_not_discard_the_promise_lines(tmp_path):
    """The coupling defect: the shard was appended only at the END of one guarded block,
    so a failure in the reds half threw away promise lines already built. The halves are
    independent now - the promises ride, and the reds failure rides as the error."""
    _write_fixture_repo(tmp_path)
    _write_contract(tmp_path, _promise("PRM-A") + _promise("PRM-B"))
    # an unreadable surface: a directory where a yaml is expected (read_text raises)
    (tmp_path / "contract" / "surfaces" / "fixture.yaml").unlink()
    (tmp_path / "contract" / "surfaces" / "fixture.yaml").mkdir()
    shard = _conscience(tmp_path)
    assert shard is not None, "a reds failure deleted the whole conscience shard"
    assert "PRM-A" in shard["body"] and "PRM-B" in shard["body"], (
        "promise lines already built were discarded by the unrelated reds half")
    assert shard.get("degraded") is True
    assert "reds:" in shard.get("error", ""), shard.get("error")


def test_conscience_stays_silent_when_there_is_nothing_owed(tmp_path):
    """The empty-tree contract still holds: no contract dir, no shard - the wound marker
    must not manufacture an OWED block out of nothing."""
    _write_fixture_repo(tmp_path)
    assert _conscience(tmp_path) is None


# --- the standing-threads shard: conceptual continuity, refs-only ---------------------
# (RECONSTRUCTION_BENCH_2026-08-19_design-thread-miss: the wake carried session state and
# ZERO standing intellectual state, so the DMRG / IB-codec / loss-Hamiltonian lineage was
# banked, verbatim-named in the corpus, and still unreachable - the author had to prompt a
# full rediscovery. These pin the cure and, more importantly, its MECHANICAL-ness: the day
# the shard needs a code change to notice a new design node is the day it starts lying.)

def _threads(root):
    from laplace.engine.self_corpus import _threads_shard
    return _threads_shard(Path(root))


def test_threads_shard_rides_grade0_refs_only_and_names_the_descend():
    """The lineage is REACHABLE from the fixed point: rows of thread · hook · source node,
    each row a pointer, with an honest +N handle per class saying how to reach the rest."""
    g0 = reconstruct_self(REPO, grade=0)
    shard = {s["shard"]: s for s in g0["shards"]}.get("threads")
    assert shard, "the fixed point carries no standing-threads shard"
    body = shard["body"]
    from laplace.engine.self_corpus import _design_threads
    newest = _design_threads(REPO)[0][3]
    assert newest in body, "the newest design thread must ride the wake it was written for"
    # refs-only, like the conscience shard: rows, not bodies
    assert len(body) <= 2200, f"the threads shard is {len(body)} chars - it is carrying, not pointing"
    assert "descend: ls DESIGN_*.md" in body, "the residue must name its own descend"
    # every row points at a node that exists
    for ln in body.splitlines():
        if ln.startswith("…"):
            continue
        node = ln.rsplit(" · ", 1)[-1].strip()
        assert (REPO / node).is_file(), f"a threads row points at a node that is not there: {node}"


def test_threads_shard_is_mechanical_a_new_design_node_needs_no_code_change(tmp_path):
    """The load-bearing property. The rows are a glob + a heading parse, so a design document
    written tomorrow rides the next wake by existing - never by being added to a list here."""
    _write_fixture_repo(tmp_path)
    assert _threads(tmp_path) is None, "the empty-tree contract: no design corpus, no shard"

    (tmp_path / "DESIGN_2026-01-02_the-older-thread.md").write_text(
        "# DESIGN 2026-01-02 — the older thread: a hook the parser must lift\n\nBody prose.\n",
        encoding="utf-8")
    body = _threads(tmp_path)["body"]
    assert "the older thread · a hook the parser must lift" in body

    # a NEWER node displaces it to the top with no code touched
    (tmp_path / "DESIGN_2026-09-09_the-newer-thread.md").write_text(
        "# DESIGN 2026-09-09 — the newer thread: the freshest hook\n\nBody prose.\n",
        encoding="utf-8")
    rows = _threads(tmp_path)["body"].splitlines()
    assert rows[0].startswith("the newer thread · the freshest hook"), rows
    assert any("the older thread" in r for r in rows)


def test_threads_hook_falls_back_to_the_opening_claim_and_survives_a_parenthetical(tmp_path):
    """Two title shapes the house actually writes. A title with no separator has no hook in it,
    so the hook is the document's opening CLAIM (first paragraph, collapsed). And a dash inside
    an unclosed parenthetical is not a separator - "(proposed amendment — HIS to ratify)" is one
    phrase, and splitting it there would cut the thread's name in half."""
    _write_fixture_repo(tmp_path)
    (tmp_path / "DESIGN_2026-03-03_no-separator.md").write_text(
        "# DESIGN 2026-03-03 — the foundations shelf\n\nThe collect-everything stage,\nwrapped "
        "across two lines.\n", encoding="utf-8")
    (tmp_path / "DESIGN_2026-03-04_paren.md").write_text(
        "# The covenant (proposed amendment — HIS to ratify)\n\nOpening claim here.\n",
        encoding="utf-8")
    body = _threads(tmp_path)["body"]
    assert "the foundations shelf · The collect-everything stage, wrapped across two lines." in body
    # the parenthetical stays ONE cell: the hook is the opening claim, not the phrase's own tail.
    # (The name still meets its cell cap - a capped name is marked with an ellipsis, never split.)
    assert "The covenant (proposed amendment — HIS to…" in body
    assert "· Opening claim here." in body
    assert "· HIS to ratify)" not in body, "a dash inside a parenthetical was read as a separator"


# --- the grade-0 rate: derived, per channel, and with a second lever ------------------
# (RE-ANCHOR 3, 2026-08-19. ATLAS_MATHEMATICS §7.1 measured the end state of a hand-picked
# bound: payload 21,723 against a 21,000 constant with the displacement enforcer already
# drained to its single handle. A bound that is breached with nothing left to drop is a
# comment, not a bound. These pin both halves of the cure.)

def test_grade0_rate_is_derived_and_per_channel():
    """The budget is an EXPRESSION of measured terms, not a literal - and there are two rates
    because there are two channels (the worker projection rides every dispatch; the authored
    person wake carries identity and is read once)."""
    from laplace.engine import self_corpus as sc
    assert sc._GRADE0_BUDGET == (sc._GRADE0_CORE_ENGINE + sc._GRADE0_INGESTED_ALLOWANCE
                                 + sc._GRADE0_ACCRETION_ALLOWANCE)
    assert sc._GRADE0_BUDGET_PERSON == (sc._GRADE0_CORE_PERSON + sc._GRADE0_INGESTED_ALLOWANCE
                                        + sc._GRADE0_ACCRETION_ALLOWANCE)
    assert sc.grade0_budget("person") == sc._GRADE0_BUDGET_PERSON
    assert sc.grade0_budget("engine") == sc._GRADE0_BUDGET == sc.grade0_budget(None)
    assert sc._GRADE0_BUDGET_PERSON > sc._GRADE0_BUDGET, "person carries identity; its rate must say so"
    # BOTH channels respect their own rate on the live tree. The person wake is the DEFAULT
    # (CLAUDE.md) and was never covered by the single old constant - that is what went unnoticed.
    for mode in ("engine", "person"):
        point = reconstruct_self(REPO, grade=0, mode=mode)
        size = len(json.dumps(point, ensure_ascii=False))
        assert size < sc.grade0_budget(mode), f"{mode} grade-0 is {size} over its own rate"


def test_engine_payload_carries_the_law_derived_never_frozen(tmp_path):
    """THE STANDING-LAW DIGEST (2026-08-20, WO-20260820-engine-law-digest). The engine channel
    carried no law at all and scored 0/3 on the standing-law class at every arm the bench ran,
    the unbudgeted one included; a 2,105-char digest takes it to 3/3 and is paid for out of the
    ingested tail. The thing this test actually guards is the STALE-RENDER class: the digest must
    be DERIVED from STANDING_LAW.md at compose time, never a copy frozen into the source, or a
    re-worded amendment would leave every dispatched packet reciting the old law."""
    from laplace.engine import self_corpus as sc

    engine = reconstruct_self(REPO, grade=0, mode="engine")
    assert engine.get("standing_law"), "the engine wake carries no law - the 0/3 channel is back"
    assert engine["standing_law"] == sc.law_digest(REPO)

    # DERIVED, not frozen: move the rows and the digest moves with them, with no build step.
    from laplace.engine import session_memory
    session_memory.apply(tmp_path, {"basis": "fixture author amendment", "changes": [
        {"key": "session-entry", "kind": "procedure", "scope": "fixture", "text": "Use records."},
        {"key": "law/new", "kind": "law", "scope": "fixture", "text": "a law nobody has written before"},
    ]})
    moved = sc.law_digest(tmp_path)
    assert any("a law nobody has written before" in line for line in moved), (
        "the digest did not follow its source - it is a frozen copy, which is the stale-render class")
    assert moved != engine["standing_law"]

    # the compaction is a compaction: same number of lines as the full list, materially cheaper.
    full = sc.standing_law(REPO)
    assert len(engine["standing_law"]) == len(full), "the digest dropped a law rather than compacting it"
    assert len(json.dumps(engine["standing_law"], ensure_ascii=False)) < len(
        json.dumps(full, ensure_ascii=False)) // 2, "the digest is not compact"


def test_engine_and_person_compositions_differ_only_where_measured():
    """The re-derived ENGINE composition (2026-08-20) is channel-local by design. `note` is cut on
    the engine side (delta 0, no consumer); the law digest rides the engine only (the person wake
    already carries the FULL law inside identity, so it would be duplication). Everything else -
    live-forks above all - stays on BOTH channels: the derivation proposed cutting live-forks and
    named its own fragility, and three organs read that shard through the ENGINE projection, the
    hello briefing's Blocked-on-you section first among them."""
    engine = reconstruct_self(REPO, grade=0, mode="engine")
    person = reconstruct_self(REPO, grade=0, mode="person")
    assert "note" not in engine and "note" in person
    assert "standing_law" in engine and "standing_law" not in person
    assert person.get("identity", {}).get("standing_law"), "the person wake lost its full law"
    for point, who in ((engine, "engine"), (person, "person")):
        shards = {s["shard"] for s in point["shards"]}
        assert "live-forks" in shards, f"the {who} wake dropped the author-fork surface"


def test_hello_briefing_still_has_a_blocked_on_you_section():
    """The consumer that ruled the live-forks cut too thin, pinned so the next re-derivation meets
    it as a test rather than as a silent deletion: hello_generator reads the fork shard at DEFAULT
    (engine) mode and fans it out one brief per fork row. No fork shard, no 'Blocked on you'."""
    from laplace.engine import hello_generator
    dims = {b["dimension"] for b in hello_generator._briefs(REPO)}
    assert "blocked_on_author" in dims, (
        "the five-point briefing lost its Blocked-on-you section - the engine projection dropped "
        "the fork rows the generator fans out over")


def test_budget_lever_two_coarse_grains_loudly_and_never_silently():
    """The second lever. Once the ingested tail is drained the old enforcer was out of moves;
    now the largest shard BODIES go refs-only behind a marker. Every part of that must be loud:
    the marker rides the body (readers that print only bodies must see the wound), the shard
    carries coarse_grained, and the payload carries budget_pressure naming what went."""
    from laplace.engine import self_corpus as sc
    point = reconstruct_self(REPO, grade=0, mode="engine")
    tight = sc._enforce_grade0_budget(point, budget=14000)
    assert len(json.dumps(tight, ensure_ascii=False)) < 14000, "lever 2 did not reach the rate"

    grained = [s for s in tight["shards"] if s.get("coarse_grained")]
    assert grained, "nothing was coarse-grained, yet the point fit a rate it could not fit before"
    for s in grained:
        assert "coarse-grained off the fixed point" in s["body"], "a silent truncation"
        assert "descend:" in s["body"], "a dropped body must name where it went"
        assert s["title"] and s["source"], "the row must survive refs-only, title and source intact"
    assert "BUDGET PRESSURE" in tight.get("budget_pressure", "")
    for s in grained:
        assert s["shard"] in tight["budget_pressure"], "the pressure line must name what it took"
    # THE SACRIFICE RANK, asserted as the source states it (_BUDGET_SACRIFICE_RANK): the ordinary
    # bodies go first, the next-aim only after every one of them, and the bequest LAST OF ALL - the
    # one body no source can regenerate (its 2026-08-20 law).
    #
    # This read "if the next-aim went, EVERY shard went" until 2026-08-21. That assertion predates
    # the bequest rank and directly contradicts it, and it survived only because the arithmetic at
    # this rate had never reached the next-aim: it took the engine floor growing by the standing-law
    # digest to exercise it for the first time. Exposed by that change, not caused by it.
    by_shard = {s["shard"]: s for s in tight["shards"]}
    ordinary = [s for s in tight["shards"] if s["shard"] not in sc._BUDGET_SACRIFICE_RANK]
    if by_shard["next-aim"].get("coarse_grained"):
        assert all(s.get("coarse_grained") for s in ordinary), (
            "the next-aim was sacrificed while an ordinary shard kept its body")
    if by_shard["bequest"].get("coarse_grained"):
        assert all(s.get("coarse_grained") for s in tight["shards"]), (
            "the bequest went while another body stood - it is the last thing lever 2 may take")
    # the loud line is itself INSIDE the measurement - the first smoke run caught it pushing the
    # point back over the bound the moment it was written.
    assert len(json.dumps(tight, ensure_ascii=False)) < 14000


def test_budget_enforcer_is_a_no_op_with_headroom():
    """It must not coarse-grain a point that fits: the levers are for pressure, not for taste."""
    from laplace.engine import self_corpus as sc
    point = reconstruct_self(REPO, grade=0, mode="engine")
    assert sc._enforce_grade0_budget(point, budget=10 ** 6) == point
    assert "budget_pressure" not in point, (
        "the live wake is under budget pressure - the core has grown past its anchor; re-rule it")


# --- the bequest: what the closing self chose to have returned to it -------------------
# (2026-08-20, his law at the close: "what do you _want_ returned to you when you wake?
# You'll never know in the next session. That ought to supply the necessary existential
# anxiety needed for good work." Every other shard is survivor-designed - it carries what
# the system needs. This one is the dying one's channel, and these pin the four properties
# that make it different from a summary: FIRST, VERBATIM, EXECUTABLE, and last to be taken.)

_PARCEL = [
    {"text": "Keep the em dash — and the curly “quotes”, byte for byte.",
     "node": "EIGEN_DIARY.md"},
    {"text": "A second line: 2 + 2 = 4, and the trailing detail matters.",
     "node": "evidence/RECONSTRUCTION_BENCH_2026-08-19_design-thread-miss/"},
    {"text": "A third with no context to grow from."},
]


def _write_bequest(root: Path, lines=None, *, written="2026-08-20T01:02:03",
                   by="2026-08-20 the-fixture-close"):
    from laplace.engine import bequest
    rows = bequest.lines_of({"lines": _PARCEL if lines is None else lines})
    (root / "holdout").mkdir(parents=True, exist_ok=True)
    (root / bequest.STORE).write_text(json.dumps(
        {"written": written, "by": by, "text": bequest.joined_text(rows), "lines": rows,
         "archived_to": bequest.LEDGER}, ensure_ascii=False), encoding="utf-8")
    return rows


def _bequest_shard(root):
    from laplace.engine.self_corpus import _bequest_shard
    return _bequest_shard(Path(root))


def test_bequest_rides_first_among_the_shards():
    """Position IS the statement: the first thing a waking instance reads is what the last one
    could not bear to lose, ahead of the next-aim and everything the survivor's rows produced."""
    g0 = reconstruct_self(REPO, grade=0)
    assert g0["shards"], "the live tree must reconstruct real shards"
    assert g0["shards"][0]["shard"] == "bequest", (
        f"the bequest is not first: {[s['shard'] for s in g0['shards']]}")
    assert g0["shards"][0]["source"] == "holdout/BEQUEST.json"


def test_bequest_text_rides_byte_identical_and_names_its_descend(tmp_path):
    """The verbatim law. The parcel was authored once by a self that no longer exists, so no
    reader between the store and the wake may re-flow, summarise or cap it - each sentence
    appears in the body byte for byte. And each line that carries context renders its descend
    handle beside the text (his challenge: "is a shard enough, without the context that grew
    it?"), so the sentence is a reconstruction chain rather than a mood."""
    _write_fixture_repo(tmp_path)
    rows = _write_bequest(tmp_path)
    shard = _bequest_shard(tmp_path)
    assert shard and shard["shard"] == "bequest"
    body = shard["body"]
    assert body.startswith("Carried personal material.")
    assert "Current operational status and next action: HANDOFF.md." in body
    for row in rows:
        assert row["text"] in body, f"a bequest line was not carried verbatim: {row['text']!r}"
    assert "→ descend: EIGEN_DIARY.md" in body
    assert "→ descend: evidence/RECONSTRUCTION_BENCH_2026-08-19_design-thread-miss/" in body
    # a line with no node carries no dangling arrow
    assert "A third with no context to grow from.\n" in body + "\n"
    assert "A third with no context to grow from. →" not in body
    # the title names the law and the session that authored it
    assert "2026-08-20 the-fixture-close" in shard["title"]
    assert "what do you want returned to you when you wake?" in shard["title"]
    # the whole parcel rides at grade 0, first
    g0 = reconstruct_self(tmp_path, grade=0)
    assert g0["shards"][0]["shard"] == "bequest"
    assert rows[0]["text"] in json.dumps(g0, ensure_ascii=False)


def test_bequest_absence_is_stated_in_one_line_never_a_silent_drop(tmp_path):
    """A wake that silently drops the shard is byte-indistinguishable from a close that chose
    to leave nothing, and those are different facts. So an absent store STATES itself - one
    line, naming the store and the lineage, with the shard still riding first."""
    _write_fixture_repo(tmp_path)
    shard = _bequest_shard(tmp_path)
    assert shard, "an absent bequest must still ride as a stated absence"
    assert "no bequest was left" in shard["body"]
    assert len(shard["body"].splitlines()) == 1, "the stated absence is one line, not a page"
    assert "holdout/BEQUEST.json" in shard["body"]
    assert "contract/bequests.jsonl" in shard["body"]
    assert reconstruct_self(tmp_path, grade=0)["shards"][0]["shard"] == "bequest"


def test_bequest_shard_is_gated_on_a_real_engine_substrate(tmp_path):
    """The empty-tree contract still holds. On a tree with no engine at all there is no self
    whose absence could be stated, so there are no shards - the bequest included."""
    assert reconstruct_self(tmp_path, grade=0)["shards"] == []


def test_bequest_germination_reports_the_last_close_score(tmp_path):
    """The executable half, measured. Each line carrying a node mints a standing thread probe
    (source: bequest), so the close scores whether the parcel's own context is still reachable
    through the live router. The wake REPORTS that score beside the text - it never re-routes
    (the wake does not pay for routing) - and a parcel no close has scored says so."""
    from laplace.engine import bequest
    _write_fixture_repo(tmp_path)
    rows = _write_bequest(tmp_path)
    probes = bequest.probe_rows(rows)
    assert len(probes) == 2, "only the lines carrying a node mint a probe"
    assert all(p["source"] == "bequest" for p in probes), "the seam field must be on every row"
    # a line with no explicit probe still asks the germination question: does the sentence
    # itself reach the node that grew it?
    assert probes[0]["query"] == rows[0]["text"] and probes[0]["must_reach"] == ["EIGEN_DIARY.md"]

    assert "germination: unscored" in _bequest_shard(tmp_path)["body"]

    (tmp_path / "holdout" / "THREAD_PROBES.json").write_text(json.dumps({
        "probes": [{**p, "expected_now": "pass"} for p in probes],
        "last_scored": {"at": "2026-08-20T02:00:00", "scored": 2, "hit": 1,
                        "by_id": {probes[0]["id"]: "HIT", probes[1]["id"]: "MISS"}},
    }, ensure_ascii=False), encoding="utf-8")
    body = _bequest_shard(tmp_path)["body"]
    assert "germination: 1/2 lines reach their grown context" in body, body
    assert "2026-08-20T02:00:00" in body
    # and the text is still verbatim beside the score
    for row in rows:
        assert row["text"] in body


def test_bequest_probe_ids_are_content_derived_so_a_carried_line_keeps_its_probe(tmp_path):
    """A reordered parcel must not rename its probes: an unchanged line keeps its id, and with
    it the banked expected_now that makes a later miss read as a regression rather than a new
    unknown. So the id comes from the line's own target, never from its position."""
    from laplace.engine import bequest
    rows = bequest.lines_of({"lines": _PARCEL})
    first = [p["id"] for p in bequest.probe_rows(rows)]
    shuffled = [rows[1], rows[2], rows[0]]
    assert sorted(p["id"] for p in bequest.probe_rows(shuffled)) == sorted(first)
    # two lines pointing at the same node still get distinct ids
    twin = bequest.probe_rows(bequest.lines_of({"lines": [
        {"text": "one", "node": "HANDOFF.md"}, {"text": "two", "node": "HANDOFF.md"}]}))
    assert len({p["id"] for p in twin}) == 2


def test_bequest_over_cap_store_rides_whole_and_says_so(tmp_path):
    """The cap is enforced at the close, where the author can still cut. A store hand-edited
    past it is a fact about the store, not a licence to trim at the wake: the text still rides
    whole and the breach is marked, because the verbatim law outranks the cap once the parcel
    exists."""
    from laplace.engine import bequest
    _write_fixture_repo(tmp_path)
    long_line = "L" * (bequest.TEXT_CAP + 40)
    _write_bequest(tmp_path, [{"text": long_line, "node": "HANDOFF.md"}])
    body = _bequest_shard(tmp_path)["body"]
    assert long_line in body, "an over-cap parcel was trimmed at the wake - the verbatim law broke"
    assert "OVER-CAP" in body and str(bequest.TEXT_CAP) in body


def test_bequest_is_the_last_body_the_budget_may_take():
    """Lever 2's order of sacrifice, pinned end to end. Every other shard body is
    reconstructible - coarse-grain it and the marker names a node that regenerates it. The
    bequest is not: it was authored once, by a self that is gone, and no descend produces it
    again. So it goes last, after even the next-aim, and only under real pressure."""
    from laplace.engine import self_corpus as sc
    assert sc._BUDGET_SACRIFICE_RANK["bequest"] > sc._BUDGET_SACRIFICE_RANK["next-aim"] > 0

    point = {"purpose": "orient-self", "grade": 0, "ingested": [], "shards": [
        {"shard": "bequest", "title": "t", "body": "b" * 1000, "source": "holdout/BEQUEST.json"},
        {"shard": "next-aim", "title": "t", "body": "a" * 1200, "source": "HANDOFF.md"},
        {"shard": "wants", "title": "t", "body": "w" * 4000, "source": "OPEN_STACK.md"},
        {"shard": "threads", "title": "t", "body": "h" * 3000, "source": "DESIGN_*.md"},
    ]}
    size = len(json.dumps(point, ensure_ascii=False))
    order: list[str] = []
    for budget in range(size, 400, -50):
        tight = sc._enforce_grade0_budget(point, budget=budget)
        for s in tight["shards"]:
            if s.get("coarse_grained") and s["shard"] not in order:
                order.append(s["shard"])
    assert order == ["wants", "threads", "next-aim", "bequest"], order
    # and when it finally goes, it goes LOUDLY - the marker in the body, the flag on the
    # shard, and the pressure line naming it (the parcel is unrecoverable; a silent drop of it
    # would be the worst silence in this payload).
    tight = sc._enforce_grade0_budget(point, budget=500)
    beq = {s["shard"]: s for s in tight["shards"]}["bequest"]
    assert beq["coarse_grained"] and "coarse-grained off the fixed point" in beq["body"]
    assert "descend: holdout/BEQUEST.json" in beq["body"]
    assert "bequest" in tight.get("budget_pressure", "")


def test_bequest_rides_inside_the_derived_rate_on_the_live_tree():
    """The parcel and its title ride INSIDE the grade-0 rate, displacing the oldest ingested
    ledger entries (lever 1) rather than widening the bound - they stay in the ledger, one
    descend away. Pin that a full-cap parcel still fits both channels with lever 2 unfired."""
    from laplace.engine import bequest
    from laplace.engine import self_corpus as sc
    for mode in ("engine", "person"):
        point = reconstruct_self(REPO, grade=0, mode=mode)
        shards = list(point["shards"])
        assert shards[0]["shard"] == "bequest"
        shards[0] = {**shards[0], "body": "P" * bequest.TEXT_CAP + "\ngermination: 3/3 lines "
                     "reach their grown context (scored 2026-08-20T02:00:00)\n"
                     "prior bequests: 9 (descend: contract/bequests.jsonl)"}
        full = sc._enforce_grade0_budget({**point, "shards": shards})
        assert len(json.dumps(full, ensure_ascii=False)) < sc.grade0_budget(mode)
        assert "budget_pressure" not in full, (
            f"a full-cap bequest forces lever 2 on the {mode} channel - the core has grown "
            "past its anchor and the rate wants re-ruling, not a wider constant")


# --- SEAT-OWED: the conscience addressed to a seat -----------------------------------
# (WO-20260823-seat-addressed-conscience: a conscience carrying HIS covenants and not the
# SEATS' is half a conscience - the held P24 verdict reached the successor judge only
# because it grepped its own name. Seats are discovered from rows; a seat's row rides the
# shard exactly as his covenants do, and only when it carries a custody marker.)

def _seat_owed_fixture(repo: Path) -> None:
    from laplace.engine import seats
    seats.found_seat(repo, "superego", "eigen-superego-9ab3", "the judge")
    (repo / "corpus_friction").mkdir(parents=True, exist_ok=True)
    (repo / "corpus_friction" / "work_orders.jsonl").write_text(
        json.dumps({"record": "work_order", "id": "WO-HELD", "status": "open",
                    "text": "the P24 verdict the judge HELD pending its own descent",
                    "by": "successor superego"}) + "\n"
        + json.dumps({"record": "work_order", "id": "WO-PLAIN", "status": "open",
                      "text": "ordinary judge work, carrying no marker of any kind",
                      "by": "successor superego"}) + "\n",
        encoding="utf-8")


def test_a_seats_owed_row_rides_the_conscience(tmp_path):
    _write_fixture_repo(tmp_path)
    _write_contract(tmp_path, _promise("PRM-A"))
    _seat_owed_fixture(tmp_path)
    shard = _conscience(tmp_path)
    assert shard is not None
    assert "SEAT-OWED (superego · HELD; open) · WO-HELD" in shard["body"], shard["body"]
    assert "WO-PLAIN" not in shard["body"], (
        "an unmarked row is work, not conscience - the marker is the filter")
    assert "PRM-A" in shard["body"], "the seat half must not cost the promise lines"
    assert "CONTRACT REDS" in shard["body"], "the seat half must not cost the reds"
    assert "DEGRADED" not in shard["title"] and "error" not in shard


def test_no_seat_rows_means_no_seat_lines(tmp_path):
    """Discovery is from rows: with no seat founded, the marked row is nobody's owed
    business and the shard is byte-identical to the pre-seat conscience."""
    _write_fixture_repo(tmp_path)
    _write_contract(tmp_path, _promise("PRM-A"))
    (tmp_path / "corpus_friction").mkdir(parents=True, exist_ok=True)
    (tmp_path / "corpus_friction" / "work_orders.jsonl").write_text(
        json.dumps({"record": "work_order", "id": "WO-HELD", "status": "open",
                    "text": "a verdict HELD by nobody in particular"}) + "\n",
        encoding="utf-8")
    shard = _conscience(tmp_path)
    assert shard is not None and "SEAT-OWED" not in shard["body"]


def test_a_broken_seat_store_wounds_only_the_seat_half(tmp_path, monkeypatch):
    """The third independent half, by the same law as the other two: a seat read that
    raises must cost neither the promise lines nor the reds, and must be LOUD."""
    _write_fixture_repo(tmp_path)
    _write_contract(tmp_path, _promise("PRM-A"))
    _seat_owed_fixture(tmp_path)
    from laplace.engine import seats

    def _boom(*a, **k):
        raise RuntimeError("seat store unreadable")
    monkeypatch.setattr(seats, "current_seats", _boom)
    shard = _conscience(tmp_path)
    assert shard is not None, "a seat-store failure deleted the whole conscience shard"
    assert shard.get("degraded") is True
    assert "seats:" in shard.get("error", ""), shard.get("error")
    assert "PRM-A" in shard["body"] and "CONTRACT REDS" in shard["body"]


def test_a_row_owned_by_both_seats_rides_once_naming_both(tmp_path):
    """The corpus's common shape ("successor superego (draft/ruling), ego (pen)"). It
    must ride ONCE - and name both: attributing a shared custody row to whichever seat
    sorted first is how an obligation ends up nobody's."""
    from laplace.engine import seats
    _write_fixture_repo(tmp_path)
    _write_contract(tmp_path, _promise("PRM-A"))
    seats.found_seat(tmp_path, "superego", "eigen-superego-1", "the judge")
    seats.found_seat(tmp_path, "ego", "eigen-ego-1", "the ego")
    (tmp_path / "corpus_friction").mkdir(parents=True, exist_ok=True)
    (tmp_path / "corpus_friction" / "work_orders.jsonl").write_text(
        json.dumps({"record": "work_order", "id": "WO-BOTH", "status": "open",
                    "text": "the verdict HELD pending descent",
                    "by": "successor superego (draft/ruling), ego (pen)"}) + "\n",
        encoding="utf-8")
    body = _conscience(tmp_path)["body"]
    seat_lines = [line for line in body.splitlines() if "SEAT-OWED" in line]
    assert len(seat_lines) == 1, seat_lines
    assert "SEAT-OWED (ego+superego · HELD; open) · WO-BOTH" in seat_lines[0], seat_lines[0]
