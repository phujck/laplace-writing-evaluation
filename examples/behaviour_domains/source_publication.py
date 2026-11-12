"""Explicit optional active Source publication on an authored public retained base.
Scoped algorithm: tests/test_source_publication.public_base. No test import,
monkeypatch, fake model reply, retired-F seam or final-verifier substitution.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import copy
from pathlib import Path

def run(root,rec):
    if importlib.util.find_spec("numpy") is None:
        return {"status":"UNAVAILABLE_OPTIONAL","reason":"Existing numpy is absent. No install attempted."}
    import numpy as np
    from laplace import sdk
    from laplace.core import identity
    from laplace.core.records import journal
    from laplace.engine import keeper, meaning_upfold
    from laplace.representation import source_publication as P, embed_router as E
    from laplace.work import owner_discovery as O, source_kernel as K
    # Require the separately generated exact public Source/kernel request.
    selected=rec.root/"evidence"/"kernel-selected-request.json"
    if not selected.is_file():
        raise ValueError("Run source_kernel earlier in this NEW workspace")
    request=json.loads(selected.read_text())
    profile=root/"runtime_profiles.toml"
    template=rec.candidate_root/"runtime_profiles.toml"
    if not profile.is_file() and template.is_file():
        profile.write_bytes(template.read_bytes())
    if not profile.is_file():
        return {"status":"UNAVAILABLE_OPTIONAL","reason":"Candidate runtime_profiles.toml is not packaged. Dependency closure belongs to coordinator."}
    backend=E.get_backend()
    if not backend or not backend.gpu or "CUDAExecutionProvider" not in backend.providers:
        if backend:E.release_backend(backend)
        return {"status":"UNAVAILABLE_OPTIONAL","reason":"Real existing local CUDA embedding backend is unavailable. No CPU substitution or network model acquisition."}
    try:
        leaves={"retained-example.txt":{"name":"retained-example.txt","kind":"text",
            "essence":"Explicit authored public retained fixture. Not a live fold or scientific fact.",
            "keywords":["retained","example"],"sealed":False}}
        nodes=keeper.build_tree(leaves)
        keeper.write_tree_local(root,nodes)
        keeper.write_skeleton(root,nodes,keeper.grade_stats(nodes))
        (root/"SELF_SHARD_INDEX.md").write_text("# Authored public retained fixture\nretained-example.txt\n")
        texts={n:E.node_text(root,{"nodes":nodes,"lenses":{}},n,{}) for n in nodes}
        vectors=dict(zip(texts,backend.embed(list(texts.values())),strict=True))
        cache={"backend":backend.name,"format":E.CACHE_FORMAT,
            "nodes":{n:{"h":E._hash(backend.name,texts[n]),**E._quantize_vec(vectors[n])} for n in texts}}
        (root/E.CACHE_FILE).write_bytes(identity.canonical_bytes(cache))
        meaning_upfold.write_sidecar(root,backend.name,{"retained-example.txt":(
            hashlib.sha1(texts["retained-example.txt"].encode()).hexdigest(),vectors["retained-example.txt"])})
        (root/".meaning_tree.json").write_bytes(identity.canonical_bytes({
            "backend":backend.name,"parent_map":{"retained-example.txt":""},"clusters":{},"leaf_sha":{}}))
        np.savez(root/".metric_M.npz",M=np.eye(len(vectors["retained-example.txt"]),dtype="float32"))
        (root/".metric_M.receipt.json").write_text(json.dumps({
            "fixture":"Authored identity metric. NOT metric-distill, AUC or quality evidence."}))
        (root/".metric_pairs.json").write_text('{"pairs":[]}')
        (root/".self_record_floor.jsonl").write_bytes(b"")
        act=journal.act_begin("authored-public-retained-base-example",["keeper","local-embedding"],root=root)
        row={"act":"deposit","act_id":act,"mode":"full-rebuild","full_requested":True,
            "ts":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "fixture":"Explicit synthetic retained base before Source inputs. NOT a live fold or authored close.",
            "embedding_counts":{"embedded":len(nodes),"cached":0,"deferred":0,"total":len(nodes)},
            "device":{"embedding_backend":"gpu","embedding_providers":list(backend.providers),"required":True}}
        row["publication"]=P.full_publication_receipt(root,row,None,nodes,None)
        (root/P.TIMING).write_bytes(identity.canonical_bytes(row)+b"\n")
        journal.act_end(act,"pass",root=root,summary="Actual authored-fixture construction with local GPU vectors. No generative provider call or quality evaluation.")
    finally:
        E.release_backend(backend)
    parent=rec.call("publication-retained-base",P.current,root)
    prepared=rec.call("publication-prepare",sdk.source_publication,
        {"action":"prepare","inputs":[request]},root=root)
    assert prepared["expected_publication_basis"]==parent["publication_handle"]
    wire={"action":"commit","request_id":"example-active-source-publication",
        "prepared":prepared["prepared"],"expected_publication_basis":prepared["expected_publication_basis"]}
    scope=O.owned_workspace("sdk")
    project=request["selection"]["namespace"]
    before=P.artifact_rows(root)
    retained_node=P._json(root/keeper.GRADED_LOCAL)["retained-example.txt"]
    retained_embedding=P._json(root/E.CACHE_FILE)["nodes"]["retained-example.txt"]
    before_journal=(root/"contract/journal.jsonl").read_bytes()
    def refuses(name,contains,fn,*args,**kwargs):
        receipt=rec.refuses(name,ValueError,fn,*args,**kwargs)
        assert contains in json.loads((rec.root/receipt).read_text())["message"]
    refuses("publication-native-authority-refusal","TRUSTED_OPERATOR_ONLY",
            P.request,root,O.project_scope(project,"native"),wire)
    wrong=copy.deepcopy(wire)
    wrong["expected_publication_basis"]="sha256:"+"0"*64
    refuses("publication-wrong-parent-refusal","PARENT_CHANGED",sdk.source_publication,wrong,root=root)
    index=root/"SELF_SHARD_INDEX.md"
    saved_index=index.read_bytes()
    try:
        index.write_bytes(saved_index+b"Changed authored example base\n")
        refuses("publication-changed-base-refusal","ARTIFACTS_CHANGED",sdk.source_publication,wire,root=root)
    finally:
        index.write_bytes(saved_index)
    assert (root/"contract/journal.jsonl").read_bytes()==before_journal
    result=rec.call("publication-commit",sdk.source_publication,wire,root=root)
    assert result["state"]=="RECORDED" and result["current"],result
    current=P.current(root)
    assert current["coverage"]["complete_world"] is False
    after=P.artifact_rows(root)
    assert {p for p in before if before[p]!=after[p]}=={
        ".self_graded.json","SELF_GRADED_INDEX.md",".self_embeddings.json"}
    assert P._json(root/keeper.GRADED_LOCAL)["retained-example.txt"]==retained_node
    assert P._json(root/E.CACHE_FILE)["nodes"]["retained-example.txt"]==retained_embedding
    counterpart=rec.call("publication-counterpart",K.read,root,scope,
                        {"facet":"source-kernel","view":"counterpart",**request})
    assert counterpart["kernel"]["state"]=="PUBLISHED",counterpart
    item=counterpart["kernel"]["counterparts"][0]
    recovered=rec.call("publication-recovered",K.read,root,scope,item["read"]["request"])
    assert recovered["state"]=="RECOVERED"
    from laplace.engine import descent as D
    # The dedicated installed example uses a real source-layout target in this
    # synthetic workspace. No source_tree or final verifier is substituted.
    typed=item["typed_descent"]
    typed_read=rec.call("publication-engine-descent",D.descend,kind=typed["kind"],
        reference=typed["reference"],read_scope=O.project_scope(project,"native"))
    assert typed_read["content_handle"]==item["content_handle"]
    rec.refuses("publication-engine-foreign-scope",D.DescentRefused,D.descend,
        kind=typed["kind"],reference=typed["reference"],
        read_scope=O.project_scope("foreign","native"))
    wrong_read=copy.deepcopy(item["read"]["request"])
    wrong_read["publication_handle"]="sha256:"+"0"*64
    refuses("publication-wrong-history-refusal","HISTORICAL_BYTES_UNAVAILABLE",
            K.read,root,scope,wrong_read)
    timing=(root/P.TIMING).read_bytes()
    journal_bytes=(root/"contract/journal.jsonl").read_bytes()
    replay=rec.call("publication-completed-replay",sdk.source_publication,wire,root=root)
    assert replay["publication"]==result["publication"]
    assert (root/P.TIMING).read_bytes()==timing
    assert (root/"contract/journal.jsonl").read_bytes()==journal_bytes
    source=root/"src/laplace/work/project_work_review.py"
    source.write_bytes(source.read_bytes()+b"\n# Public example: bytes moved, declared consumed meaning unchanged.\n")
    moved_replay=rec.call("publication-replay-after-source-move",sdk.source_publication,wire,root=root)
    moved_read=rec.call("publication-retained-read-after-source-move",K.read,root,scope,item["read"]["request"])
    moved=rec.call("publication-carried-meaning",K.prepare,root,scope,
        {"facet":"source-kernel","view":"prepare",**request})
    assert moved_replay["publication"]==result["publication"]
    assert moved_read["facts"]==recovered["facts"]
    assert {r["state"] for r in moved["currentness"].values()}=={"CARRIED"}
    assert (root/P.TIMING).read_bytes()==timing
    assert (root/"contract/journal.jsonl").read_bytes()==journal_bytes
    assert not (root/"contract/close_receipt.json").exists()
    return {"status":"EXECUTED","publication_handle":current["publication_handle"],
        "counterpart":item,"recovered":recovered,"typed_descent":typed_read,
        "completed_replay_no_effect":True,"retained_read_after_source_move":True,
        "moved_meaning_currentness":"CARRIED","unselected_retained_values_unchanged":True,
        "device":current.get("device"),
        "refusals":["native operator authority","wrong publication parent","changed base artifacts",
                    "foreign read scope","wrong historical publication"],"complete_world":False,
        "qualification":"Real active Source prepare/commit/final-verifier/recovery over an explicitly authored retained base using actual local GPU vectors. NOT a full-world fold, scientific benchmark, private corpus or model transcript."}
