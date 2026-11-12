import json

from laplace.research import concepts as cs, corpus_ingest


def test_focused_relations_preserve_analogy_and_evidence_without_dependency_upgrade(monkeypatch, tmp_path):
    net={"nodes":{"a":{"kind":"claim","essence":"Claim A"},"b":{"kind":"definition","essence":"Definition B","projection":{"term":"B"}},"c":{"kind":"result","essence":"Result C"}},"edge_index":{"a":["b","c"],"b":["b"],"c":["c"]},"spine":[]}
    monkeypatch.setattr(cs,"_network",lambda *args:net)
    from laplace.research import corpus_ingest
    monkeypatch.setattr(corpus_ingest,"rewire_list",lambda *args:[{"kind":"add-edge","node":"a","target":"b","rel":"analogy"},{"kind":"add-edge","node":"a","target":"c","rel":"validated_by"}])
    out=cs.state("fixture","a",root=tmp_path)
    assert {r["rel"] for r in out["relations"]}=={"analogy","validated_by"}
    assert {r["direction"] for r in out["relations"]}=={"lateral","evidence"}
    assert out["glossary"]==[{"id":"b","term":"B","label":"Definition B"}]


def test_legacy_edge_is_explicitly_unknown(monkeypatch,tmp_path):
    monkeypatch.setattr(cs,"_network",lambda *args:{"nodes":{"a":{"essence":"A"},"b":{"essence":"B"}},"edge_index":{"a":["b"],"b":["b"]},"spine":[]})
    from laplace.research import corpus_ingest
    monkeypatch.setattr(corpus_ingest,"rewire_list",lambda *args:[])
    assert cs.state("x","a",root=tmp_path)["relations"][0]["rel"]=="unknown"


def test_add_node_born_prerequisite_survives_focus_and_action_identity(tmp_path):
    _nested_fixture(tmp_path)
    _change(tmp_path,operation='add_node',node='def:base',node_kind='definition',essence='Base',parent='paper://')
    _change(tmp_path,operation='add_node',node='def:step',node_kind='definition',essence='Step',parent='paper://',target='def:base',rel='prerequisite')
    focused=cs.state('graph','def:step',root=tmp_path)
    assert focused['relations'][0]['target']=='def:base' and focused['relations'][0]['rel']=='prerequisite'
    from laplace.native.tools import _action_summary
    summary=_action_summary('graph','concept_change',{'node':'def:step','target':'def:base'},{'record':{'id':'RW-receipt','node':'def:step','target':'def:base'}})
    assert summary['identities'][:2]==['def:step','def:base'] and 'RW-receipt' in summary['receipts']


def _nested_fixture(root):
    manuscript=root/"graph/manuscript";manuscript.mkdir(parents=True)
    (manuscript/"main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}Graph.\\end{document}\n")
    (root/"registry_projects.json").write_text(json.dumps({"projects":[{
        "name":"graph","project_dir":"graph","tex_root":"graph/manuscript",
        "manifest":{"document":{"root":"graph/manuscript/main.tex"}}}]}))
    return manuscript


def _change(root, **payload):
    current=cs.state("graph",root=root)
    status,result=cs.change({"project":"graph","base_revision":current["revision"],
                             "by":"author",**payload},root=root)
    assert status==200,result
    return result


def test_neighborhood_read_does_not_mutate_cached_concept_revision(tmp_path):
    _nested_fixture(tmp_path)
    _change(tmp_path, operation="add_node", node="def:base", node_kind="definition",
            essence="Base", parent="paper://")
    _change(tmp_path, operation="add_node", node="res:derived", node_kind="result",
            essence="Derived", parent="paper://", target="def:base", rel="prerequisite")
    before = cs.state("graph", node="res:derived", root=tmp_path)["revision"]
    net = corpus_ingest.corpus_network(corpus_ingest.resolve_corpus(tmp_path, "graph"),
                                       repo_root=tmp_path, name="graph")

    corpus_ingest.neighborhood(net, "res:derived")

    assert all("dep_depth" not in node for node in net["nodes"].values())
    assert cs.state("graph", node="res:derived", root=tmp_path)["revision"] == before


def test_recursive_tree_create_move_open_back_preserves_object_and_bounds_response(tmp_path):
    _nested_fixture(tmp_path)
    _change(tmp_path,operation="add_node",node="goal:group",node_kind="goal",
            essence="Grouped argument",parent="paper://",ref={"file":"main.tex","line":1})
    _change(tmp_path,operation="add_node",node="def:child",node_kind="definition",
            essence="Child definition",parent="goal:group",ref="main.tex#child")
    _change(tmp_path,operation="add_node",node="res:leaf",node_kind="result",
            essence="Nested result",parent="def:child",ref={"file":"main.tex","line":2})
    _change(tmp_path,operation="set_projection",node="res:leaf",
            value={"term":"Nested result term"})
    _change(tmp_path,operation="add_node",node="support:outside",node_kind="support",
            essence="Outside support",parent="paper://")

    opened=cs.tree("graph","res:leaf",root=tmp_path)
    assert [row["id"] for row in opened["ancestors"]]==[
        "paper://","goal:group","def:child"]
    assert opened["current"]["source"]=={"file":"main.tex","line":2}
    stale_up_query=opened["navigation"]["ascent"]["query"]
    assert opened["navigation"]["ascent"]["resolved_parent"]=="def:child"
    assert opened["semantic_return"]["status"]=="NOT_RUN"
    assert opened["atlas_conjugate"]["status"]=="UNAVAILABLE"
    child=cs.tree("graph","def:child",root=tmp_path)
    assert child["current"]["id"]==opened["current"]["parent"]
    assert child["children"][0]["id"]=="res:leaf"
    assert child["current"]["grade"]>child["children"][0]["grade"]

    moved=_change(tmp_path,operation="move_node",node="res:leaf",target="goal:group")
    assert moved["record"]["kind"]=="move-node"
    _change(tmp_path,operation="add_edge",node="res:leaf",target="def:child",rel="support")
    _change(tmp_path,operation="add_edge",node="def:child",target="support:outside",rel="analogy")
    group=cs.tree("graph","goal:group",limit=1,root=tmp_path)
    from laplace.engine import conceptric
    net=corpus_ingest.corpus_network(corpus_ingest.resolve_corpus(tmp_path,"graph"),
                                     repo_root=tmp_path,name="graph")
    canonical_chain=conceptric.identity_chain(net,"goal:group")
    assert [(row["id"],row["share"]) for row in group["ancestors"]]==[
        (row["id"],row["share"]) for row in canonical_chain]
    assert group["children_total"]==2 and len(group["children"])==1
    assert group["children_omitted"]==1 and group["children_next_offset"]==1
    assert {edge["rel"] for edge in group["dependencies"]["internal"]}=={"support"}
    assert {edge["rel"] for edge in group["dependencies"]["boundary"]}=={"analogy"}
    leaf=cs.tree("graph","res:leaf",root=tmp_path)["current"]
    assert leaf["parent"]=="goal:group" and leaf["grade"]==0
    assert leaf["summary"]=="Nested result"
    assert leaf["source"]=={"file":"main.tex","line":2}
    assert leaf["projection"]["term"]=="Nested result term"
    assert "nodes" not in group and "glossary" not in group and "search" not in group

    # Following the pre-move UP handle names the child, not its old parent. The
    # server re-derives the live identity chain and returns the new enclosing group.
    up_query={key:[str(value)] for key,value in stale_up_query.items()}
    status,_,raw=cs.handle("/concepts/tree",up_query,"GET",b"",repo_root=tmp_path)
    returned=json.loads(raw)
    assert status==200 and returned["request"]["kind"]=="containment-ascent"
    assert returned["request"]["resolved_node"]=="goal:group"
    assert returned["current"]["id"]=="goal:group"
    assert returned["revision"]!=opened["revision"]

    descent_query=group["children"][0]["descent"]["query"]
    status,_,raw=cs.handle("/concepts/tree",{key:[str(value)] for key,value in descent_query.items()},
                           "GET",b"",repo_root=tmp_path)
    descended=json.loads(raw)
    assert status==200 and descended["request"]["authority"]=="conceptric.children_view"
    assert descended["current"]["id"]==group["children"][0]["id"]

    status,_,raw=cs.handle("/concepts/tree",{"project":["graph"],
        "node":["support:outside"],"direction":["dependency"],"from":["def:child"]},
        "GET",b"",repo_root=tmp_path)
    followed=json.loads(raw)
    assert status==200 and followed["request"]["kind"]=="typed-dependency-follow"
    assert followed["request"]["conjugate_up"] is False
    reconstructed=cs.tree("graph","goal:group",goal="explain nested result",root=tmp_path)
    assert reconstructed["semantic_return"]["status"]=="LIVE_BOUNDED"
    assert reconstructed["semantic_return"]["authority"].startswith("keeper_ring.reconstruct")
    assert reconstructed["semantic_return"]["visited"]<=15

    status,_,raw=cs.handle("/concepts/tree",{"project":["graph"],"node":["goal:group"],
        "offset":["1"],"limit":["1"]},"GET",b"",repo_root=tmp_path)
    http=json.loads(raw)
    assert status==200 and http["children"][0]["id"]=="res:leaf"
    assert http["children_next_offset"] is None


def test_logical_history_projects_four_level_child_impact_without_unrelated_invalidation(tmp_path):
    _nested_fixture(tmp_path)
    _change(tmp_path,operation="add_node",node="goal:top",node_kind="goal",
            essence="Authored top interpretation",parent="paper://")
    _change(tmp_path,operation="add_node",node="def:level-one",node_kind="definition",
            essence="Level one",parent="goal:top")
    _change(tmp_path,operation="add_node",node="lemma:level-two",node_kind="lemma",
            essence="Level two",parent="def:level-one")
    _change(tmp_path,operation="add_node",node="res:leaf",node_kind="result",
            essence="Original leaf",parent="lemma:level-two")
    _change(tmp_path,operation="add_node",node="thm:dependent",node_kind="theorem",
            essence="Depends on leaf",parent="paper://",target="res:leaf",rel="prerequisite")
    _change(tmp_path,operation="add_node",node="res:unrelated",node_kind="result",
            essence="Unrelated",parent="paper://")
    changed=_change(tmp_path,operation="edit_node",node="res:leaf",value="Revised exact leaf")

    value=cs.history("graph","goal:top",root=tmp_path,limit=20)
    event=next(row for row in value["history"]
               if row["operation"]["id"]==changed["record"]["id"])

    assert value["basis"]["status"]=="REPROJECTED_ON_CURRENT_SOURCE"
    assert event["operation"]["kind"]=="edit-essence"
    assert event["subject"]["changes"]==[{
        "field":"essence","before":"Original leaf","after":"Revised exact leaf"}]
    assert event["containment"]["before_ancestors"][-3:]==[
        "def:level-one","goal:top","paper://"]
    ancestors={row["id"]:row for row in event["containment"]["ancestor_effects"]}
    assert ancestors["goal:top"]["posture"]=="SEMANTIC_REVIEW_REQUIRED"
    assert ancestors["lemma:level-two"]["posture"]=="SEMANTIC_REVIEW_REQUIRED"
    assert event["affected_dependents"][0]["id"]=="thm:dependent"
    assert event["affected_dependents"][0]["posture"]=="SEMANTIC_REVIEW_REQUIRED"
    assert event["guarantees"]=={"proof_rechecked":False,"manuscript_rewritten":False,
                                  "scientific_validity_reassessed":False}
    impacted={row["id"] for row in value["impact"]["objects"]}
    assert "res:leaf" in impacted and "thm:dependent" in impacted
    assert "res:unrelated" not in impacted
    status,_,raw=cs.handle("/concepts/history",{"project":["graph"],"node":["goal:top"],
        "record":[changed["record"]["id"]]},"GET",b"",repo_root=tmp_path)
    assert status==200 and json.loads(raw)["history"][0]["operation"]["id"]==changed["record"]["id"]
    from laplace.native import tools as writing_tools
    through_tool=writing_tools.execute(tmp_path,"graph","work","concept_history",{
        "node":"goal:top","record":changed["record"]["id"]})
    assert through_tool["history"][0]["subject"]["id"]=="res:leaf"
    help_value=writing_tools.execute(tmp_path,"graph","work","help",{
        "operation":"concept_history"})["action"]
    assert help_value["input"]["required"]==["node"]


def test_root_tree_pages_explicit_uncontained_objects_without_treating_root_children_as_orphans(tmp_path):
    _nested_fixture(tmp_path)
    _change(tmp_path,operation="add_node",node="goal:contained",node_kind="goal",
            essence="Contained",parent="paper://")
    _change(tmp_path,operation="add_node",node="question:orphan-a",node_kind="question",
            essence="First uncontained question")
    _change(tmp_path,operation="add_node",node="result:orphan-b",node_kind="result",
            essence="Second uncontained result")

    first=cs.tree("graph",root=tmp_path,limit=1,uncontained_offset=0)
    second=cs.tree("graph",root=tmp_path,limit=1,uncontained_offset=1)

    assert first["uncontained_total"]==2 and len(first["uncontained"])==1
    assert first["uncontained_next_offset"]==1
    assert second["uncontained_next_offset"] is None
    assert {first["uncontained"][0]["id"],second["uncontained"][0]["id"]}=={
        "question:orphan-a","result:orphan-b"}
    assert "goal:contained" not in {row["id"] for row in first["uncontained"]+second["uncontained"]}
    assert all("child_count" in row and "grade" in row for row in first["uncontained"]+second["uncontained"])


def test_recursive_move_cycle_and_dangling_parent_refuse_before_ledger(tmp_path):
    _nested_fixture(tmp_path)
    _change(tmp_path,operation="add_node",node="goal:group",node_kind="goal",
            essence="Group",parent="paper://")
    _change(tmp_path,operation="add_node",node="def:child",node_kind="definition",
            essence="Child",parent="goal:group")
    _change(tmp_path,operation="add_node",node="res:leaf",node_kind="result",
            essence="Leaf",parent="def:child")
    before=len(corpus_ingest.rewire_list(tmp_path,"graph"))
    current=cs.state("graph",root=tmp_path)
    status,cycle=cs.change({"project":"graph","operation":"move_node",
        "node":"goal:group","target":"res:leaf","base_revision":current["revision"],
        "by":"author"},root=tmp_path)
    assert status==422 and "containment cycle" in cycle["error"]
    assert len(corpus_ingest.rewire_list(tmp_path,"graph"))==before
    status,dangling=cs.change({"project":"graph","operation":"add_node",
        "node":"res:orphan","node_kind":"result","essence":"Orphan",
        "parent":"missing:parent","base_revision":current["revision"],
        "by":"author"},root=tmp_path)
    assert status==422 and "parent is not live" in dangling["error"]
    assert len(corpus_ingest.rewire_list(tmp_path,"graph"))==before
    _change(tmp_path,operation="add_node",node="goal:detached",node_kind="goal",
            essence="A detached draft group")
    before_root_move=len(corpus_ingest.rewire_list(tmp_path,"graph"))
    current=cs.state("graph",root=tmp_path)
    status,root_move=cs.change({"project":"graph","operation":"move_node",
        "node":"paper://","target":"goal:detached","base_revision":current["revision"],
        "by":"author"},root=tmp_path)
    assert status==422 and "root cannot be moved" in root_move["error"]
    assert len(corpus_ingest.rewire_list(tmp_path,"graph"))==before_root_move


def test_model_concept_tree_read_uses_same_contract_and_navigation_producer(tmp_path):
    _nested_fixture(tmp_path)
    _change(tmp_path,operation="add_node",node="goal:group",node_kind="goal",
            essence="Group",parent="paper://")
    _change(tmp_path,operation="add_node",node="res:leaf",node_kind="result",
            essence="Leaf",parent="goal:group")
    from laplace.native import tools as writing_tools
    help_value=writing_tools.execute(tmp_path,"graph","discuss","help",
                                     {"operation":"concept_tree"})
    # `requested_payload_contract` is gone: it returned the owner's whole contract a
    # SECOND time beside the copy inside `action`, which was 75.3 per cent of
    # help structure_change. The property that mattered is unchanged and asserted
    # here instead: every variant help serves is BUILT from the owner's own
    # contract, so the owner is still the one source.
    owner=cs.tree_contract()
    from laplace.native import declarations as writing_declarations
    schema=writing_declarations.variants("concept_tree")["navigate"]
    assert set(schema["properties"])=={key for key in owner["properties"] if key!="project"}
    assert set(schema["required"])=={key for key in owner["required"] if key!="project"}
    # D2: the default help names its input by section; the exact schema is that section read
    assert "input" in help_value["action"]["sections"]["chars"]
    assert writing_tools.execute(tmp_path,"graph","discuss","help",
                                 {"operation":"concept_tree","section":"input"})["action"]["value"]==schema
    opened=writing_tools.execute(tmp_path,"graph","discuss","concept_tree",
                                 {"node":"goal:group","limit":20},turn_id="WT-tree")
    assert opened["current"]["id"]=="goal:group"
    assert opened["children"][0]["descent"]["authority"]=="conceptric.children_view"
    descended=writing_tools.execute(tmp_path,"graph","discuss","concept_tree",
                                    opened["children"][0]["descent"]["query"])
    assert descended["current"]["id"]=="res:leaf"
    returned=writing_tools.execute(tmp_path,"graph","discuss","concept_tree",
                                   descended["navigation"]["ascent"]["query"])
    assert returned["current"]["id"]=="goal:group"
    assert returned["request"]["authority"]=="conceptric.identity_chain"
    # A guessed `parent` key is refused by the closed declared shape BEFORE the owner: the structured shape
    # refusal names it and points at this operation's help, and neither the concept owner nor the journal is
    # touched (M5 S3: the consumer used to expect the retired owner wording "unknown query keys").
    journal=tmp_path/"contract"/"talk.jsonl"
    before=journal.read_bytes() if journal.exists() else None
    reached=[]
    original=cs.handle
    import functools
    @functools.wraps(original)   # keep the owner signature the dispatcher reads (repo_root)
    def trapped(*args,**kwargs):
        reached.append(args)
        return original(*args,**kwargs)
    cs.handle=trapped
    try:
        writing_tools.execute(tmp_path,"graph","discuss","concept_tree",
                              {"node":"goal:group","parent":"paper://"})
    except writing_declarations.PayloadAdmissionError as exc:
        refused=exc.response()
        assert refused["refused"]["kind"]=="shape" and "'parent' was unexpected" in refused["refused"]["said"]
        assert refused["help"]=={"operation":"help","payload":{"operation":"concept_tree"}}
    except BaseException:
        cs.handle=original
        raise
    else:
        raise AssertionError("guessed concept_tree parent key was accepted")
    try:
        assert reached==[],"the malformed request never reached the concept owner"
        assert (journal.read_bytes() if journal.exists() else None)==before,"and wrote nothing"
        # the same request without the guessed key reaches the one producer, once (so the trap is live)
        exact=writing_tools.execute(tmp_path,"graph","discuss","concept_tree",{"node":"goal:group","limit":20})
        assert exact["current"]["id"]=="goal:group" and len(reached)==1
    finally:
        cs.handle=original


def test_history_impact_assesses_each_selected_existing_node_once_within_the_bounds(tmp_path, monkeypatch):
    """RD-HISTORY: the impact helper owns its bounded selection (deduplicated, first 80) and assesses source
    support once per selected EXISTING node over one literature-input read; a missing id stays unavailable
    without a guessed identity. (The helper used logical_plan's unbound local `hydrate_ids`.)"""
    _nested_fixture(tmp_path)
    _change(tmp_path, operation="add_node", node="goal:top", node_kind="goal", essence="Top", parent="paper://")
    _change(tmp_path, operation="add_node", node="res:leaf", node_kind="result", essence="Leaf", parent="goal:top")
    supported, literature = [], []
    original_support, original_literature = cs._source_support, cs._literature_inputs
    monkeypatch.setattr(cs, "_source_support", lambda project, ident, *a, **k: supported.append(ident) or original_support(project, ident, *a, **k))
    monkeypatch.setattr(cs, "_literature_inputs", lambda *a, **k: literature.append(1) or original_literature(*a, **k))
    ids = ["res:leaf", "goal:top", "res:leaf", "missing:gone"] + ["filler:%03d" % n for n in range(90)]
    rows = cs._history_current_impact("graph", tmp_path, ids)
    assert len(rows) == 80 and [row["id"] for row in rows[:3]] == ["res:leaf", "goal:top", "missing:gone"]
    assert sorted(supported) == ["goal:top", "res:leaf"] and len(literature) == 1     # once each, one shared read
    by_id = {row["id"]: row for row in rows}
    support = by_id["res:leaf"]["source_support"]
    assert by_id["res:leaf"]["available"] and support.get("status") != "NOT_ASSESSED" and "omission" in support   # assessed, not a placeholder
    assert by_id["missing:gone"] == {**by_id["missing:gone"], "available": False, "source_support": None, "label": "missing:gone"}
    # the history page stays bounded and an unrelated sibling change does not enter this node's impact
    _change(tmp_path, operation="add_node", node="res:sibling", node_kind="result", essence="Sibling", parent="paper://")
    value = cs.history("graph", "goal:top", root=tmp_path, limit=20)
    assert len(value["history"]) <= 20 and len(value["impact"]["objects"]) <= 80
    assert "res:sibling" not in {row["id"] for row in value["impact"]["objects"]}
