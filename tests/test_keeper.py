"""Tests for keeper (Stage 1) - the mechanical graded build (the upward operator's container).

Synthetic leaf maps, no real content. Contracts: grades are height by containment; keywords that
RECUR across siblings ascend (and unique ones do not); handles are bidirectional (members down,
parent up); the gate is LOCAL (sampled); a wide node is reshape-flagged; the paper_* version family
folds into ONE node (F22); and a sealed subtree stays sealed without leaking content."""

from __future__ import annotations

from laplace.engine import concept_lens, keeper, record_shard, self_shard


def _leaf(kind, keywords, sealed=False, essence="x"):
    return {"kind": kind, "essence": essence, "keywords": keywords, "sealed": sealed}


def test_grades_by_containment():
    leaves = {"a/b.py": _leaf("py", ["x"]), "a/c.py": _leaf("py", ["y"]), "d.md": _leaf("md", ["z"])}
    nodes = keeper.build_tree(leaves)
    assert nodes["a"]["grade"] == 1 and nodes["a"]["members"] == ["a/b.py", "a/c.py"]
    assert nodes[""]["grade"] == 2                       # root = 1 + max(a=1, d.md=0)
    assert sorted(nodes[""]["members"]) == ["a", "d.md"]


def test_recurrence_promotion():
    leaves = {"p/x.py": _leaf("py", ["shared", "only_x"]),
              "p/y.py": _leaf("py", ["shared", "only_y"])}
    nodes = keeper.build_tree(leaves)
    assert "shared" in nodes["p"]["keywords"]            # recurs across 2 children -> ascends
    assert "only_x" not in nodes["p"]["keywords"]        # unique to one child -> stays below


def test_promote_keywords_tie_order_is_deterministic():
    # W6.2 REPAIR (2026-07-14): equal-count keywords must not ride set()/most_common insertion
    # order (PYTHONHASHSEED-dependent) - that flipped promoted handles across process loads and
    # made node_text re-embed ~7 top-level nodes on every cold boot (warm-arrival churn). Tie-break
    # is now count DESC then keyword ASC, so the output is identical regardless of input ordering.
    a = keeper.promote_keywords([["b", "a"], ["a", "b"], ["d", "c"], ["c", "d"]])
    b = keeper.promote_keywords([["d", "c"], ["b", "a"], ["c", "d"], ["a", "b"]])
    assert a == b == ["a", "b", "c", "d"]                 # all count 2, alphabetical within the tie
    # the fallback branch (nothing clears min_count) is deterministic too
    f1 = keeper.promote_keywords([["z"], ["a"], ["m"]])
    f2 = keeper.promote_keywords([["m"], ["z"], ["a"]])
    assert f1 == f2 == ["a", "m", "z"]


def test_leaf_token_sources_are_process_stable():
    text = "spectral routing fidelity routing mutation custody"
    expected = sorted({"spectral", "routing", "fidelity", "mutation", "custody"})
    assert concept_lens._tokens(text) == expected
    assert record_shard._tokens(text) == expected


def test_bidirectional_handles():
    leaves = {"a/b.py": _leaf("py", ["x"])}
    nodes = keeper.build_tree(leaves)
    assert nodes["a/b.py"]["parent"] == "a"              # up-pointer
    assert "a/b.py" in nodes["a"]["members"]             # down-pointer
    assert nodes["a"]["parent"] == ""                    # and on up to root


def test_local_gate_passes_and_samples():
    leaves = {f"a/f{i}.py": _leaf("py", ["common", f"u{i}"]) for i in range(10)}
    nodes = keeper.build_tree(leaves)
    gate = keeper.local_faithfulness(nodes, k=3)
    assert gate["pass"] is True
    # O(internal * k) + the promoted-keyword checks - nowhere near O(N^2) over 10 leaves
    assert gate["checked"] < 40


def test_width_flag():
    leaves = {f"a/f{i}.py": _leaf("py", ["k"]) for i in range(5)}
    nodes = keeper.build_tree(leaves)
    stats = keeper.grade_stats(nodes, width_bound=2)     # force a flag
    assert any(f["node"] == "a" for f in stats["reshape_flags"])


def test_paper_version_family_folds():
    # F22: many version snapshots under one work -> ONE coarse node, versions as members (not flat)
    leaves = {
        "paper_x/v7/m.tex": _leaf("tex", ["loss"]),
        "paper_x/v8/m.tex": _leaf("tex", ["loss"]),
        "paper_x/v9/m.tex": _leaf("tex", ["loss"]),
    }
    nodes = keeper.build_tree(leaves)
    assert "paper_x" in nodes
    assert sorted(nodes["paper_x"]["members"]) == ["paper_x/v7", "paper_x/v8", "paper_x/v9"]
    assert sum(1 for nid in nodes if nid == "paper_x") == 1          # one node, family folded
    assert nodes["paper_x"]["grade"] == 2                            # work(2) -> version(1) -> file(0)


def test_sealed_subtree_stays_sealed():
    leaves = {"soul/a.md": _leaf("soul", ["soul"], sealed=True, essence="(sealed)"),
              "soul/b.md": _leaf("soul", ["soul"], sealed=True, essence="(sealed)")}
    nodes = keeper.build_tree(leaves)
    assert nodes["soul"]["sealed"] is True                # all-sealed members -> sealed coarse node
    # the coarse essence is synthesised from child KINDS only, never content
    assert "sealed" not in nodes["soul"]["essence"].lower() or "item" in nodes["soul"]["essence"]


def test_mixed_dir_not_sealed():
    leaves = {"m/s.md": _leaf("soul", ["soul"], sealed=True), "m/p.py": _leaf("py", ["code"])}
    nodes = keeper.build_tree(leaves)
    assert nodes["m"]["sealed"] is False                  # one unsealed member -> not a sealed node


def test_recall_routes_through_grades_and_prunes():
    # two areas; a query for area A's term returns A's leaf and does NOT walk B's subtree
    leaves = {"alpha/one.py": _leaf("py", ["widget", "alpha"]),
              "alpha/two.py": _leaf("py", ["widget", "alpha"]),
              "beta/three.py": _leaf("py", ["gadget", "beta"]),
              "beta/four.py": _leaf("py", ["gadget", "beta"])}
    nodes = keeper.build_tree(leaves)
    res = keeper.recall(nodes, "widget")
    files = {f["file"] for f in res["files"]}
    assert files == {"alpha/one.py", "alpha/two.py"}        # found A
    assert not any("beta" in f for f in files)              # pruned B
    assert res["visited"] < res["total"]                   # grade-local, not a flat scan


def test_recall_finds_unique_term_via_coverage():
    # a term in exactly ONE leaf is filtered out of the promoted handle (others recur), but coverage
    # still carries it up so the ring can route to it
    leaves = {"a/b1.py": _leaf("py", ["needle", "common"]),
              "a/b2.py": _leaf("py", ["common", "x"]),
              "a/b3.py": _leaf("py", ["common", "y"])}
    nodes = keeper.build_tree(leaves)
    assert nodes["a"]["keywords"] == ["common"]            # only the recurrent term is promoted
    assert "needle" not in nodes["a"]["keywords"]          # unique -> not in the handle
    assert "needle" in nodes["a"]["coverage"]              # but coverage carries it up
    res = keeper.recall(nodes, "needle")
    assert [f["file"] for f in res["files"]] == ["a/b1.py"]
    assert res["files"][0]["path"][0] == "" and res["files"][0]["path"][-1] == "a/b1.py"


def test_build_self_integration(tmp_path):
    # self_shard -> keeper end to end on a tiny tmp tree (no git -> shard_repo walks)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text('"""A module."""\ndef f():\n    return 1\n', encoding="utf-8")
    (tmp_path / "README.md").write_text("# Title\n\nbody\n", encoding="utf-8")
    leaves = self_shard.shard_repo(tmp_path)
    nodes = keeper.build_tree(leaves)
    assert keeper.local_faithfulness(nodes)["pass"] is True
    assert nodes[""]["grade"] >= 1 and not nodes[""]["leaf"]


def test_build_self_hands_back_the_raw_shards_it_already_computed(tmp_path):
    """``shards_out`` (2026-08-20): the caller catches build_self's OWN ``shard_repo`` result so the
    deposit's re-index reuses it instead of re-deriving the whole tree a second time.

    Two contracts: it equals a standalone ``shard_repo`` (so ``write_index`` gets exactly what its
    default would have derived), and it is a COPY taken before the lens leaves merge on top - the
    flat file index must never carry lens atoms or synthetic concept clusters."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text('"""A module."""\ndef f():\n    return 1\n', encoding="utf-8")
    (tmp_path / "README.md").write_text("# Title\n\nbody\n", encoding="utf-8")

    # taken BEFORE the build: build_self drops its own scratch files (the record floor, the
    # trigger log) into the tree, so a shard_repo taken after would legitimately see more.
    expected = self_shard.shard_repo(tmp_path)

    caught: dict = {}
    nodes = keeper.build_self(tmp_path, shards_out=caught)

    assert caught == expected
    assert set(caught) == {"src/mod.py", "README.md"}
    assert not any("::" in k for k in caught)          # no lens atoms leaked in
    assert "" not in caught                            # no synthetic root/cluster leaked in
    assert set(caught) <= set(nodes)                   # every file still reached the graded tree

    # the default is untouched - every existing caller passes nothing and still gets its tree
    # (the node SET is not re-asserted here: the build above drops its own scratch files into the
    # tree, so a second build legitimately sees more files than the first)
    assert set(caught) <= set(keeper.build_self(tmp_path))


def test_semantic_input_excludes_its_outputs_but_keeps_them_in_the_name_index(tmp_path):
    """A fold may name its outputs after the act; it may not consume mutable post bytes as pre."""

    (tmp_path / "README.md").write_text("# Source\n", encoding="utf-8")
    (tmp_path / ".meaning_tree.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".self_graded.json").write_text("{}", encoding="utf-8")
    shadow = tmp_path / "evidence" / "shadow"
    shadow.mkdir(parents=True)
    (shadow / ".meaning_tree.json").write_text("{}", encoding="utf-8")
    (tmp_path / "SELF_SHARD_INDEX.md").write_text("generated", encoding="utf-8")

    raw: dict = {}
    leaves, _parent, _residue, _lens_hash, _pairs = keeper.semantic_input_frame(
        tmp_path, shards_out=raw
    )

    assert "README.md" in leaves
    assert ".meaning_tree.json" not in leaves
    assert ".self_graded.json" not in leaves
    assert "evidence/shadow/.meaning_tree.json" not in leaves
    assert "SELF_SHARD_INDEX.md" not in leaves
    assert {
        ".meaning_tree.json",
        ".self_graded.json",
        "evidence/shadow/.meaning_tree.json",
        "SELF_SHARD_INDEX.md",
    } <= set(raw), "the exact by-name index still carries the operator artifacts"


def test_read_frontier_and_edges_leave_record_floor_unpublished(tmp_path):
    from laplace.engine import conceptric

    source = tmp_path / "HANDOFF.md"
    source.write_text("# State\nThe old checkpoint.\n", encoding="utf-8")
    floor = tmp_path / record_shard.FLOOR_INDEX
    keeper.semantic_input_frame(tmp_path)
    assert not floor.exists(), "a cold frontier read must not create a floor"

    record_shard.floor_leaves(tmp_path)
    before = (floor.read_bytes(), floor.stat().st_mtime_ns)
    source.write_text("# State\nThe newer checkpoint.\n\n## Next\nContinue here.\n", encoding="utf-8")
    leaves, *_ = keeper.semantic_input_frame(tmp_path)
    assert "HANDOFF.md::1" in leaves, "freshness inspection still sees the current source"
    conceptric._self_edge_index(tmp_path)
    assert (floor.read_bytes(), floor.stat().st_mtime_ns) == before

    keeper.semantic_input_frame(tmp_path, persist_record_floor=True)
    assert floor.read_bytes() != before[0], "the producer still publishes the new locators"
    assert "Continue here." in record_shard.reconstruct(tmp_path, "HANDOFF.md::1")


def test_session_handoff_series_folds():
    # N28: the dated handoffs are ONE semantic object - they grade under the series node
    # (self-record -> series -> dated files), never as N top-level leaves flooding the root.
    # My own record gets no self-exemption (F22's version-series precedent, first person).
    leaves = {
        "SESSION_HANDOFF_2026-06-08_eating-the-dump.md": _leaf("md", ["soul", "dump"]),
        "SESSION_HANDOFF_2026-06-10_the-loop-closed.md": _leaf("md", ["router", "loop"]),
        "HANDOFF.md": _leaf("md", ["aim"]),
    }
    nodes = keeper.build_tree(leaves, lambda nid: keeper.series_parent(nid) or keeper.dir_parent(nid))
    series = nodes[keeper.HANDOFF_SERIES]
    assert series["grade"] == 1 and series["parent"] == "" and series["leaf"] is False
    assert sorted(series["members"]) == [
        "SESSION_HANDOFF_2026-06-08_eating-the-dump.md",
        "SESSION_HANDOFF_2026-06-10_the-loop-closed.md",
    ]
    assert all(nodes[m]["parent"] == keeper.HANDOFF_SERIES for m in series["members"])
    assert nodes["HANDOFF.md"]["parent"] == ""             # the live entry point stays at root
    assert keeper.local_faithfulness(nodes)["pass"] is True


def test_series_parent_scope():
    # dated handoffs fold by BASENAME wherever they stray; deliberate archives and atoms do not
    assert keeper.series_parent("SESSION_HANDOFF_2026-06-09_x.md") == keeper.HANDOFF_SERIES
    assert keeper.series_parent("src/laplace/SESSION_HANDOFF_2026-05-31_x.md") == keeper.HANDOFF_SERIES
    assert keeper.series_parent("HANDOFF.md") is None
    assert keeper.series_parent("archive/SESSION_HANDOFF_2026-06-09_x.md") is None
    assert keeper.series_parent("SESSION_HANDOFF_2026-06-09_x.md::3") is None   # an atom is not a file
    assert keeper.series_parent(keeper.HANDOFF_SERIES) is None   # the series ascends to root


def test_authored_file_becomes_internal_keeps_essence():
    # a SEMANTIC parent (a lens) can make a real FILE-leaf the parent of other leaves: it becomes an
    # internal coarse node but KEEPS its own authored essence (the adjudicated handle beats a summary),
    # ascends the recurrences, and the gate checks only the ASCENT (its own file-read terms are exempt).
    leaves = {"themes/T.md": _leaf("md", ["koopman", "classical"], essence="The theme, authored."),
              "atoms/p1.md": _leaf("md", ["shared", "p1only"]),
              "atoms/p2.md": _leaf("md", ["shared", "p2only"])}
    parent = {"atoms/p1.md": "themes/T.md", "atoms/p2.md": "themes/T.md"}
    nodes = keeper.build_tree(leaves, lambda nid: parent.get(nid) or keeper.dir_parent(nid))
    t = nodes["themes/T.md"]
    assert t["leaf"] is False and t["grade"] == 1 and t["authored"] is True
    assert sorted(t["members"]) == ["atoms/p1.md", "atoms/p2.md"]
    assert t["essence"] == "The theme, authored."          # authored essence PRESERVED, not summarised
    assert "koopman" in t["keywords"]                       # own terms kept (they route to the node)
    assert "shared" in t["ascended"] and "koopman" not in t["ascended"]   # only the recurrence is "ascended"
    assert "shared" in t["coverage"] and "koopman" in t["coverage"]       # both findable below/here
    assert t["route_handle"] == {"essence": "The theme, authored.",
                                 "keywords": ["koopman", "classical"], "sealed": False}
    assert keeper.local_faithfulness(nodes)["pass"] is True               # own term exempt; ascent clean
