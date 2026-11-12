"""The storyboard: plan-edit reducer, op classification, and the cheap \\input
rewrite. Pure-logic tests - no corpus, no browser, no LaTeX. The integration
paths (plan_write gate, dirty_report, rebuild manifest) are exercised live over
the running scanner; here we pin the deterministic core the board depends on.
"""

from __future__ import annotations

import pytest

from laplace.manuscript import storyboard as sb

pytestmark = pytest.mark.unit


def _base():
    return {
        "sections": [
            {"id": "S1", "title": "Intro", "job": "open",
             "nodes_in_order": ["a", "b", "c"], "beats": ["a"], "figures": [], "refs": []},
            {"id": "S2", "title": "Body", "job": "develop",
             "nodes_in_order": ["d", "e"], "beats": ["d"], "figures": [], "refs": []},
        ],
        "appendices": [
            {"id": "A1", "title": "App", "nodes_in_order": ["z"], "beats": [], "figures": [], "refs": []},
        ],
    }


def _nodes(plan, sid):
    return sb._find_section(plan, sid)["nodes_in_order"]


# ---------------------------------------------------------------------------
# reduce_plan / _apply_op - the drag verbs
# ---------------------------------------------------------------------------

def test_reorder_sections():
    p = sb.reduce_plan(_base(), [{"kind": "reorder-sections", "order": ["S2", "S1"]}])
    assert [s["id"] for s in p["sections"]] == ["S2", "S1"]


def test_reorder_never_drops_an_omitted_section():
    # an order that names only S2 keeps S1 too (never silently drop content)
    p = sb.reduce_plan(_base(), [{"kind": "reorder-sections", "order": ["S2"]}])
    assert {s["id"] for s in p["sections"]} == {"S1", "S2"}


def test_move_node_between_sections():
    p = sb.reduce_plan(_base(), [{"kind": "move-node", "node": "d", "from": "S2", "to": "S1"}])
    assert "d" in _nodes(p, "S1") and "d" not in _nodes(p, "S2")


def test_move_node_at_index():
    p = sb.reduce_plan(_base(), [{"kind": "move-node", "node": "e", "from": "S2", "to": "S1", "index": 1}])
    assert _nodes(p, "S1") == ["a", "e", "b", "c"]


def test_toggle_beat_on_and_off():
    on = sb.reduce_plan(_base(), [{"kind": "toggle-beat", "node": "b", "section": "S1", "on": True}])
    assert "b" in sb._find_section(on, "S1")["beats"]
    off = sb.reduce_plan(_base(), [{"kind": "toggle-beat", "node": "a", "section": "S1", "on": False}])
    assert "a" not in sb._find_section(off, "S1")["beats"]


def test_toggle_beat_requires_node_in_section():
    # a node not pinned in the section cannot become a beat
    p = sb.reduce_plan(_base(), [{"kind": "toggle-beat", "node": "zzz", "section": "S1", "on": True}])
    assert "zzz" not in sb._find_section(p, "S1")["beats"]


def test_add_node_at_index_and_dedup():
    p = sb.reduce_plan(_base(), [{"kind": "add-node", "node": "x", "section": "S1", "index": 1}])
    assert _nodes(p, "S1") == ["a", "x", "b", "c"]
    # adding a node already present is a no-op
    p2 = sb.reduce_plan(_base(), [{"kind": "add-node", "node": "a", "section": "S1"}])
    assert _nodes(p2, "S1") == ["a", "b", "c"]


def test_remove_node_clears_beats_too():
    p = sb.reduce_plan(_base(), [{"kind": "remove-node", "node": "a", "section": "S1"}])
    assert _nodes(p, "S1") == ["b", "c"]
    assert "a" not in sb._find_section(p, "S1")["beats"]


def test_reorder_nodes_within_section():
    p = sb.reduce_plan(_base(), [{"kind": "reorder-nodes", "section": "S1", "order": ["c", "a", "b"]}])
    assert _nodes(p, "S1") == ["c", "a", "b"]


def test_retitle_and_edit_job():
    p = sb.reduce_plan(_base(), [
        {"kind": "retitle", "section": "S1", "title": "New"},
        {"kind": "edit-job", "section": "S1", "job": "J2"},
    ])
    s = sb._find_section(p, "S1")
    assert s["title"] == "New" and s["job"] == "J2"


def test_ops_target_appendices_too():
    p = sb.reduce_plan(_base(), [{"kind": "add-node", "node": "q", "section": "A1"}])
    assert _nodes(p, "A1") == ["z", "q"]


def test_remove_and_restore_section_preserve_exact_membership_and_position():
    base = _base()
    removed = sb.reduce_plan(base, [{"kind": "remove-section", "section": "S1"}])
    assert [row["id"] for row in removed["sections"]] == ["S2"]
    restored = sb.reduce_plan(base, [
        {"kind": "remove-section", "section": "S1"},
        {"kind": "restore-section", "entries": [{"section": base["sections"][0],
         "collection": "sections", "index": 0}]},
    ])
    assert restored == base


def test_determinism_and_base_immutability():
    base = _base()
    seq = [{"kind": "move-node", "node": "e", "from": "S2", "to": "S1"},
           {"kind": "reorder-sections", "order": ["S2", "S1"]}]
    assert sb.reduce_plan(base, seq) == sb.reduce_plan(base, seq)
    # the authored base is never mutated by a reduction
    assert _nodes(base, "S2") == ["d", "e"]


def test_undo_is_prefix_replay():
    base = _base()
    seq = [{"kind": "retitle", "section": "S1", "title": "One"},
           {"kind": "retitle", "section": "S1", "title": "Two"}]
    full = sb.reduce_plan(base, seq)
    undone = sb.reduce_plan(base, seq[:-1])
    assert sb._find_section(full, "S1")["title"] == "Two"
    assert sb._find_section(undone, "S1")["title"] == "One"


def test_malformed_op_is_skipped_not_raised():
    # a bad record must never poison the reduction
    p = sb.reduce_plan(_base(), [{"kind": "move-node"}, {"kind": "retitle", "section": "S1", "title": "ok"}])
    assert sb._find_section(p, "S1")["title"] == "ok"


# ---------------------------------------------------------------------------
# op classification + the dirty-diff id filter
# ---------------------------------------------------------------------------

def test_rebuild_class_for():
    assert sb.rebuild_class_for({"kind": "reorder-sections"}) == "cheap"
    assert sb.rebuild_class_for({"kind": "retitle"}) == "cheap"
    assert sb.rebuild_class_for({"kind": "move-node"}) == "expensive"
    assert sb.rebuild_class_for({"kind": "edit-job"}) == "expensive"


def test_clean_ids_keeps_real_nodes_drops_noise():
    # clean_ids filters the STALENESS-POOL grammar (schema.POOL_ID_RE): kind-prefixed
    # OR bare, since a node pool holds bare ids too (RQ-CLM-043, ridge_lambda) — the
    # row-7 fix. fig:/ref: ride \ref/\cite and are filtered by namespace; punctuation
    # noise ('(the', '(evidence)') is rejected by the charset. A bare token that is
    # syntactically a valid id is KEPT: clean_ids sees an already-extracted id set, not
    # the marker context, so it cannot tell a bare node (ridge_lambda) from a bare
    # citation-key-shaped token (chan2025shadow) — and the diff's job is to notice any
    # pool member that moved, so keeping it is correct (a stray citation in a NODES
    # marker is rare and a false-positive-toward-detection, never a missed change).
    raw = {"def:filtered-mean", "res:x", "fig:f1-staircase", "ref:mccaul2025",
           "(the", "(evidence)", "chan2025shadow", "irf:budget"}
    assert sb._clean_ids(raw) == {"def:filtered-mean", "res:x", "irf:budget",
                                  "chan2025shadow"}


def test_unknown_op_kind_rejected_before_disk():
    # the kind guard fires before any filesystem access, so a fake corpus is safe
    res = sb.plan_write("no-such-corpus", {"kind": "frobnicate", "section": "S1"})
    assert res["ok"] is False and "unknown op kind" in res["error"]


# ---------------------------------------------------------------------------
# the cheap-path core: main.tex \input reorder
# ---------------------------------------------------------------------------

def test_rewrite_inputs_reorders_sections_and_preserves_the_rest(tmp_path):
    main = tmp_path / "main.tex"
    main.write_text(
        "\\begin{document}\n"
        "\\input{S1}\n\\input{S2}\n\\input{S3}\n"
        "\\appendix\n"
        "\\input{A1}\n\\input{A2}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    changed = sb._rewrite_inputs(main, ["S3", "S1", "S2"], ["A2", "A1"])
    assert changed is True
    text = main.read_text(encoding="utf-8")
    # section block reordered, appendix block reordered, structure preserved
    body = [l for l in text.splitlines() if l.strip()]
    assert body == ["\\begin{document}", "\\input{S3}", "\\input{S1}", "\\input{S2}",
                    "\\appendix", "\\input{A2}", "\\input{A1}", "\\end{document}"]


def test_rewrite_inputs_noop_when_order_unchanged(tmp_path):
    main = tmp_path / "main.tex"
    main.write_text("\\input{S1}\n\\input{S2}\n\\appendix\n\\input{A1}\n", encoding="utf-8")
    assert sb._rewrite_inputs(main, ["S1", "S2"], ["A1"]) is False


def test_rewrite_inputs_matches_colon_sids_against_encoded_stems(tmp_path):
    # class-lock (RW-20260713-203140-001240): plan carries REAL colon sids, but
    # the migrated main.tex holds path-ENCODED stems on disk (':' -> '_'). The
    # rewrite must match colon sids to their sec_*.tex stems, re-emit the block
    # through the encoder, and never bank a raw colon back into the file.
    main = tmp_path / "main.tex"
    main.write_text(
        "\\begin{document}\n"
        "\\input{sec_intro}\n\\input{sec_abstract-style}\n\\input{sec_methods}\n"
        "\\appendix\n"
        "\\input{app_data}\n\\input{app_proofs}\n"
        "\\end{document}\n",
        encoding="utf-8",
    )
    changed = sb._rewrite_inputs(
        main,
        ["sec:methods", "sec:abstract-style", "sec:intro"],
        ["app:proofs", "app:data"],
    )
    # (a) colon sids MATCHED the encoded stems, so the reorder took effect
    assert changed is True
    text = main.read_text(encoding="utf-8")
    body = [l for l in text.splitlines() if l.strip()]
    # (b) the emitted \input block carries the ENCODED stems in plan order
    assert body == ["\\begin{document}",
                    "\\input{sec_methods}", "\\input{sec_abstract-style}",
                    "\\input{sec_intro}",
                    "\\appendix",
                    "\\input{app_proofs}", "\\input{app_data}",
                    "\\end{document}"]
    # (c) NO raw colon survives anywhere — nothing was re-banked as a sid
    assert ":" not in text


def test_assemble_main_tex_emits_encoded_input_lines_for_colon_sids(monkeypatch):
    # sibling class-lock at the assembler seam: a plan of colon sids must emit
    # path-encoded \input lines and never a raw colon. Isolates the emission
    # logic — heavy deps (profile/spec/preamble/title) stubbed to nothing.
    from types import SimpleNamespace
    from laplace.pipeline import tex_backend as tb
    from laplace.pipeline import projection_spec as ps

    plan = {
        "sections": [{"id": "sec:intro"}, {"id": "sec:abstract-style"}],
        "appendices": [{"id": "app:proofs"}],
    }
    fake_proj = SimpleNamespace(read_plan=lambda repo_root=None: plan)
    monkeypatch.setattr(tb.registry, "resolve", lambda name: fake_proj)
    monkeypatch.setattr(ps, "load_spec", lambda project, repo_root=None: {})
    monkeypatch.setattr(tb, "load_profile", lambda *a, **k: {})
    monkeypatch.setattr(tb, "render_preamble", lambda profile, record: "")
    monkeypatch.setattr(tb, "render_title_block", lambda record: "")

    text = tb.assemble_main_tex("whatever", write=False)
    assert "\\input{sec_intro}" in text
    assert "\\input{sec_abstract-style}" in text
    assert "\\input{app_proofs}" in text
    # no raw colon leaks into an \input target
    assert ":" not in text


# ---------------------------------------------------------------------------
# B1 - the dual face: section_ref is a node->beat edge; the mirror is deterministic
# ---------------------------------------------------------------------------

def test_anchor_beat_lowest_spine_ord_wins():
    plan = {"sections": [{"id": "S1", "beats": ["res:a", "def:b"]}], "appendices": []}
    net = {"spine": [{"id": "def:b", "ord": 5}, {"id": "res:a", "ord": 2}]}
    assert sb._anchor_beat(plan, net, "S1") == "res:a"          # ord 2 < 5
    # a beat with no spine tag is ignored
    plan2 = {"sections": [{"id": "S1", "beats": ["res:a", "def:untagged"]}], "appendices": []}
    assert sb._anchor_beat(plan2, net, "S1") == "res:a"
    # a beatless section has no anchor
    assert sb._anchor_beat({"sections": [{"id": "S9", "beats": []}]}, net, "S9") is None


def test_node_first_section_deterministic_first_wins():
    plan = {"sections": [{"id": "S1", "nodes_in_order": ["a", "b"]},
                         {"id": "S2", "nodes_in_order": ["b", "c"]}], "appendices": []}
    assert sb._node_first_section(plan, "b") == "S1"            # b in both -> first
    assert sb._node_first_section(plan, "c") == "S2"
    assert sb._node_first_section(plan, "z") is None


def test_desired_section_ref_is_first_sections_anchor():
    plan = {"sections": [{"id": "S1", "beats": ["res:a"], "nodes_in_order": ["res:a", "sup:x"]},
                         {"id": "S2", "beats": [], "nodes_in_order": ["def:y", "sup:x"]}],
            "appendices": []}
    net = {"spine": [{"id": "res:a", "ord": 1}]}
    assert sb._desired_section_ref(plan, net, "sup:x") == "res:a"   # first section (S1) anchor
    assert sb._desired_section_ref(plan, net, "res:a") is None      # self-anchor -> None
    assert sb._desired_section_ref(plan, net, "def:y") is None      # first section beatless -> None
    assert sb._desired_section_ref(plan, net, "orphan") is None     # in no section -> None


# ---------------------------------------------------------------------------
# C - the hinge: the plan pool derived from node facts
# ---------------------------------------------------------------------------

def test_derived_pool_beats_then_children_by_grade():
    plan = {"sections": [{"id": "S1", "beats": ["res:a", "res:b"]}]}
    net = {"spine": [{"id": "res:a", "ord": 0}, {"id": "res:b", "ord": 1}],
           "nodes": {
               "res:a": {"grade": 0}, "res:b": {"grade": 0},
               "def:x": {"grade": 2, "projection": {"section_ref": "res:a"}},
               "sup:y": {"grade": 1, "projection": {"section_ref": "res:a"}},
               "irf:z": {"grade": 1, "projection": {"section_ref": "res:b"}},
               "fig:f": {"projection": {"section_ref": "res:a"}},   # figures excluded
           }}
    pool = sb._derived_pool(plan, net)["S1"]
    # beat res:a, then its children by grade (sup:y g1 before def:x g2), then res:b, then irf:z
    assert pool["derived"] == ["res:a", "sup:y", "def:x", "res:b", "irf:z"]
    assert "fig:f" not in pool["derived"]


def test_derived_pool_beatless_section_flagged():
    plan = {"sections": [{"id": "S9", "beats": []}]}
    net = {"spine": [], "nodes": {}}
    assert sb._derived_pool(plan, net)["S9"] == {"beatless": True}


def test_set_nodes_op_replaces_pool():
    base = _base()
    p = sb.reduce_plan(base, [{"kind": "set-nodes", "section": "S1", "order": ["x", "y", "z"]}])
    assert _nodes(p, "S1") == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# set-serves - the C3.1 section-ownership producer (mirrors set-refs)
# ---------------------------------------------------------------------------

def test_set_serves_op_is_in_the_op_vocabulary():
    # the producer must be a recognised plan op or plan_write refuses it before disk
    from laplace.pipeline.schema import PLAN_OP_KINDS, EXPENSIVE_OPS
    assert "set-serves" in PLAN_OP_KINDS
    assert "set-serves" in EXPENSIVE_OPS          # a declaration edit the %NODES diff can't see


def test_set_serves_op_writes_a_list_and_normalises_a_scalar():
    base = _base()
    # a list of contribution refs (id | rank number) is stored verbatim
    p = sb.reduce_plan(base, [{"kind": "set-serves", "section": "S1", "serves": [1, "cabc123"]}])
    assert sb._find_section(p, "S1")["serves"] == [1, "cabc123"]
    # a scalar ref is normalised to a one-element list (uniform stored shape)
    p2 = sb.reduce_plan(base, [{"kind": "set-serves", "section": "S2", "serves": 2}])
    assert sb._find_section(p2, "S2")["serves"] == [2]
    # appendices are targetable too
    p3 = sb.reduce_plan(base, [{"kind": "set-serves", "section": "A1", "serves": 1}])
    assert sb._find_section(p3, "A1")["serves"] == [1]


def test_set_serves_none_or_empty_clears_the_declaration():
    base = _base()
    seeded = sb.reduce_plan(base, [{"kind": "set-serves", "section": "S1", "serves": [1]}])
    assert sb._find_section(seeded, "S1")["serves"] == [1]
    # withdrawing: None and [] both remove the field (a section may un-declare)
    cleared_none = sb.reduce_plan(seeded, [{"kind": "set-serves", "section": "S1", "serves": None}])
    assert "serves" not in sb._find_section(cleared_none, "S1")
    cleared_empty = sb.reduce_plan(seeded, [{"kind": "set-serves", "section": "S1", "serves": []}])
    assert "serves" not in sb._find_section(cleared_empty, "S1")


# ---------------------------------------------------------------------------
# _violations - the inherited-defect delta gate (plan_write repair path)
# ---------------------------------------------------------------------------

def test_violations_flattens_report_comparably():
    val = {"missing_nodes": ["def:gone"], "retired_used": [["S1", "def:old"]],
           "missing_refs": [], "fig_defects": None}
    v = sb._violations(val)
    assert ("missing_nodes", "def:gone") in v
    assert any(k == "retired_used" for k, _ in v)
    assert len(v) == 2


def test_violations_delta_isolates_the_new_defect():
    # a plan already carrying a retired-node defect gains one missing node: the
    # delta names ONLY the addition, so a repair op (delta empty) can land while
    # a worsening op is still rejected.
    before = {"retired_used": [["S1", "def:old"]]}
    after = {"retired_used": [["S1", "def:old"]], "missing_nodes": ["def:new-typo"]}
    delta = sb._violations(after) - sb._violations(before)
    assert delta == {("missing_nodes", "def:new-typo")}
    # and a shrinking edit has an empty delta
    assert sb._violations(before) - sb._violations(after) == set()


def test_cheap_root_reorder_waits_for_the_same_physical_source_owner(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from laplace.manuscript import manuscript_source
    main = tmp_path / 'main.tex'
    before = '\\input{S2}\n\\input{S1}\n'
    main.write_text(before)
    lease = manuscript_source.source_mutation
    monkeypatch.setattr(manuscript_source, 'source_mutation', lambda paths, **kw: lease(paths, timeout=0))
    with lease([main]):
        with ThreadPoolExecutor(max_workers=1) as pool:
            refused = pool.submit(sb._rewrite_inputs, main, ['S1','S2'], [])
            with pytest.raises(manuscript_source.SourceLeaseTimeout): refused.result()
        assert main.read_text() == before
    assert sb._rewrite_inputs(main, ['S1','S2'], [])
    assert main.read_text() == '\\input{S1}\n\\input{S2}\n'


def test_cheap_rebuild_refuses_plan_changed_while_waiting_for_source(tmp_path, monkeypatch):
    import copy, threading
    from concurrent.futures import ThreadPoolExecutor
    from laplace.manuscript import manuscript_source
    main = tmp_path/'main.tex'; main.write_text('\\input{S2}\n\\input{S1}\n')
    plan = {'meta':{'target_dir':'.'},'sections':[{'id':'S1'},{'id':'S2'}]}
    plan_path = tmp_path/'projection_plan.json'
    monkeypatch.setattr(sb,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(sb,'_load_plan',lambda corpus:(plan_path,copy.deepcopy(plan)))
    monkeypatch.setattr(sb,'dirty_report',lambda corpus:[])
    monkeypatch.setattr(sb,'_try_compile',lambda *a,**kw:pytest.fail('refused reorder compiled'))
    original = manuscript_source.source_mutation; waiting=threading.Event()
    def notified(paths,**kw):
        waiting.set();return original(paths,**kw)
    monkeypatch.setattr(manuscript_source,'source_mutation',notified)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with original([main]):
            future=pool.submit(sb.rebuild,'fixture','cheap')
            assert waiting.wait(3)
            plan['sections'].reverse()
        result=future.result(timeout=3)
    assert not result['ok'] and result['reason']=='plan-revision-conflict'
    assert main.read_text()=='\\input{S2}\n\\input{S1}\n'


def test_cheap_rebuild_compile_follows_exact_target_after_both_locks_release(tmp_path,monkeypatch):
    from laplace.manuscript import manuscript_source
    main=tmp_path/'main.tex';main.write_text('\\input{S2}\n\\input{S1}\n')
    plan={'meta':{'target_dir':'.'},'sections':[{'id':'S1'},{'id':'S2'}]}
    monkeypatch.setattr(sb,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(sb,'_load_plan',lambda corpus:(tmp_path/'plan.json',plan))
    monkeypatch.setattr(sb,'dirty_report',lambda corpus:[])
    def compile(corpus,*,target):
        assert target=='.' and not manuscript_source.source_mutation_active()
        assert sb._PLAN_LOCK.acquire(blocking=False)
        sb._PLAN_LOCK.release()
        return {'ok':True}
    monkeypatch.setattr(sb,'_try_compile',compile)
    result=sb.rebuild('fixture','cheap')
    assert result['ok'] and result['compile']['ok']
