"""Real Atlas event chain, projection reconstruction and read-only refusal.
Synthetic authored control events, never a provider conversation or scientific review.
"""
from __future__ import annotations
from datetime import datetime, timezone

def run(root, rec):
    from atlas.history import (AtlasEvent, ConceptricObject, EventKind, LifecycleAction,
        LifecyclePhase, LifecycleTransition, ProducerRef, Residual, ResidualStatus,
        SeatRole, SourceRef, Validity)
    from atlas.ids import hash_bytes
    from atlas.runtime import collect_runtime_receipt
    from atlas.state import CONTROL_AXIS_CONTRACT
    from atlas.store import ConceptricStore
    from atlas.errors import StoreError
    base=root/"atlas-example"/"event-history"
    base.mkdir(parents=True)
    data=b"Explicit synthetic control example: ordered input 1, 2, 3.\n"
    original=base/"input.txt"
    original.write_bytes(data)
    provenance=(SourceRef("authored-control-input",hash_bytes(data),str(original)),)
    now=datetime.now(timezone.utc).isoformat()
    runtime=collect_runtime_receipt(root,observed_at=now)
    residual=Residual(ResidualStatus.WITHIN_BOUND,0.0,0.0,
                      "structural-violations","Synthetic control-envelope example only")
    def event(kind,subject,payload,actor=SeatRole.SYSTEM):
        return AtlasEvent.create(occurred_at=now,kind=kind,producer=SeatRole.SYSTEM,
            actor=actor,subject=subject,assumption=None,fibre=None,
            correlation_id="authored-behaviour-example",causation_ids=(),
            provenance=provenance,residual=residual,runtime=runtime,
            producer_ref=ProducerRef("local-python-example","deterministic","control-example"),
            validity=Validity.VALID,payload=payload)
    wake=event(EventKind.LIFECYCLE,"lifecycle:example",
        LifecycleTransition(LifecycleAction.COLD_WAKE,LifecyclePhase.SLEEPING,
                            LifecyclePhase.AWAKE,"cold:example").to_dict())
    store_root=base/"store"
    role="public-behaviour-fixture"
    # Actual owner-generated roots, not placeholders. The existing no-Git
    # exception is explicitly confined to this non-production fixture role.
    authority=ConceptricStore.authority_context_manifest(
        store_root,store_role=role,allow_git_unavailable=True)
    rec.save("atlas-fixture-authority",{"store_role":role,"roots":authority,
        "qualification":"Explicit non-production installed-package fixture only"})
    def open_store(**kwargs):
        return ConceptricStore(store_root,expected_store_role=role,
                               authority_context=authority,**kwargs)
    store=open_store()
    first=store.append(wake)
    again=store.append(wake)
    assert again.event.event_id==first.event.event_id
    content=store.hive.put(data)
    item=ConceptricObject(object_id="object:example-input",kind="authored-example",
        content_handle=content,assumption=None,fibre=None,
        grade_contract_id=CONTROL_AXIS_CONTRACT.contract_id,grade_coordinate="content",
        provenance=provenance,attributes={"synthetic":True,"values":[1,2,3]})
    declared=event(EventKind.OBJECT,item.object_id,item.to_dict(),SeatRole.AUTHOR)
    second=store.append(declared)
    state=store.replay()
    assert state.event_count==2
    assert state.graph_objects[item.object_id].content_handle==content
    assert store.hive.get(content)==data
    rec.save("atlas-events",[e.to_dict() for e in store.events()])
    rec.save("atlas-query",{"object":state.graph_objects[item.object_id].to_dict(),
        "qualification":"Exact addressed object lookup, not a semantic search or spectral reconstruction benchmark."})
    cold=open_store()
    assert cold.replay()==state
    # Remove only the disposable derived index. Ledger and hives stay intact.
    cold.projection_path.unlink()
    rebuilt=open_store()
    assert rebuilt.replay()==state
    reader=open_store(read_only=True)
    rec.refuses("atlas-read-only-append",StoreError,reader.append,wake)
    return {"status":"EXECUTED","events":state.event_count,
        "first_event":first.event.event_id,"head_event":second.event.event_id,
        "record_digest":second.record_digest,"object":item.object_id,
        "store":str(base.relative_to(root)/"store"),
        "reconstruction":"Cold event replay and disposable index rebuild observed",
        "spectral_reconstruction":"NOT_YET_EXERCISED",
        "qualification":"Genuine Atlas owner records from explicit synthetic control input, not model history."}
