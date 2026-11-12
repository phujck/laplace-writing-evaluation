"""Real public Source-contract custody and kernel preparation, CPU/model-free.
Scoped from test_source_kernel_bridge.sample, no test imports or fake output seam.
"""
from __future__ import annotations
import json
from pathlib import Path

PROJECT="source-kernel-example"

def run(root,rec):
    from laplace import sdk
    from laplace.projects import library
    from laplace.work import source_contracts as SC, source_kernel as K
    from laplace.work import project_work as W, project_work_review as R, owner_discovery as O
    from laplace.native import tools
    from laplace.web import project_work_surface as H
    status,created=rec.call("kernel-project-create",library.create,{
        "name":PROJECT,"title":"Source kernel example","kind":"general",
        "purpose":"Follow a public source contract through exact retained custody, not a model."},root)
    assert status==201,created
    relative="src/laplace/work/project_work_review.py"
    target=root/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes(Path(R.__file__).read_bytes())
    binding={"owner":"domain.work","operation":"work_review.followup",
             "consumer":K.CONSUMER,"segments":["authority"]}
    rec.call("kernel-work-create",W.task,PROJECT,{"id":"WORK-kernel-example",
        "title":"Inspect exact public Source meaning","goal":"Retain and recover the declared authority segment.",
        "review_obligations":[{"id":"kernel","label":"Source kernel facts","scope":"source",
            "inputs":[relative],"source_contract":binding}]},root)
    detail=W.read(PROJECT,{"view":"detail","id":"WORK-kernel-example"},root)
    handoff=rec.call("kernel-handoff",R.record,PROJECT,{
        "id":"WORK-kernel-example","phase":"handoff","request_id":"example-kernel-handoff",
        "expected_work_revision":detail["task"]["work_revision"],
        "object":{"kind":"source"},"pins":{relative:rec.digest(target)}},root)
    payload={"facet":"source-kernel","reference":SC.reference("domain.work","work_review.followup"),
        "selection":{"namespace":PROJECT,"work_id":"WORK-kernel-example",
            "handoff_id":handoff["phase"]["id"],"obligation_id":"kernel"},"view":"prepare"}
    prepared=rec.call("kernel-sdk-prepare",sdk.request,payload,root=root)
    native=rec.call("kernel-native-read",tools.execute,root,PROJECT,"work","project",
                    {"view":"discovery","request":payload})
    issued=prepared["read"]["request"]
    query={k:[json.dumps(v) if isinstance(v,(dict,list)) else str(v)] for k,v in issued.items()}
    code,mime,body=rec.call("kernel-http-read",H.handle,"/work/discovery",query,"GET",repo_root=root)
    assert code==200,body
    human=json.loads(body)
    assert native["leaves"]==human["leaves"]==prepared["leaves"]
    scope=O.owned_workspace("sdk")
    precise=rec.call("kernel-owner-prepare",K.prepare,root,scope,payload)
    leaf=next(iter(precise["leaves"].values()))
    descent=json.loads(leaf["projection"]["exact_descent"]["reference"])
    facts=rec.call("kernel-exact-descent",K.descend,root,O.project_scope(PROJECT,"native"),descent)
    assert facts==json.loads(leaf["embedding_text"])
    rec.refuses("kernel-foreign-scope",ValueError,K.prepare,root,O.project_scope("foreign","native"),payload)
    request={"reference":prepared["reference"],"selection":prepared["selection"],"segments":["authority"]}
    packet=rec.call("kernel-publication-inputs",K.prepare_publication_inputs,root,scope,[request])
    validated=rec.call("kernel-validate-inputs",K.validate_publication_inputs,root,scope,packet["packet"])
    assert validated==packet
    rec.save("kernel-selected-request",request)
    return {"status":"EXECUTED","project":PROJECT,"request":request,
        "handoff_id":handoff["phase"]["id"],"kernel_state":prepared["kernel"]["state"],
        "prepared_basis":prepared.get("prepared_basis"),
        "publication":"NOT_RUN: active publication requires a separate real retained base and existing local GPU backend",
        "qualification":"Actual Source/kernel owners and retained exact meaning. A handoff/preparation is not a review, publication, model execution or completed Work."}
