"""Explicit separate local CUDA toy. Never run by the default driver."""
from __future__ import annotations

def run(root,rec):
    try:
        import torch
    except ImportError:
        return {"status":"UNAVAILABLE_OPTIONAL","reason":"Existing local torch is absent. No installation attempted."}
    if not torch.cuda.is_available():
        return {"status":"UNAVAILABLE_OPTIONAL","reason":"CUDA owner prerequisite unavailable. No CPU numeric fallback or GPU wheel installation."}
    from atlas.record.ingest import toy
    fixture=toy.load_fixture()
    built=toy.ingest()
    assert built.local_row_ids==tuple(row["row_id"] for row in fixture.ROWS)
    assert len(built.ingestion.store.table("toy_row"))==10
    assert built.ingestion.store.table("toy_row").duplicate_rows()==0
    planted=dict(fixture.ROW_BY_ID["r8"])
    planted.update(row_id="r9-planted",object="Manchester",entity="Manchester",
                   place="Manchester",claim_id="c9")
    refused=toy.ingest(extra_rows=[planted])
    assert "r9-planted" not in refused.local_row_ids
    assert len(refused.ingestion.store.refused)==1
    assert refused.ingestion.store.refused[0].predicate_id=="surfaces_located@v1"
    return {"status":"EXECUTED","qualification":"Existing explicitly synthetic toy STORE/CHECK on local CUDA, no scientific or extraction benchmark claim.",
        "fixture_path":str(toy.FIXTURE_PATH),"fixture_sha256":rec.digest(toy.FIXTURE_PATH),
        "head_hash":built.ingestion.record_head_hash(),
        "generation_id":built.ingestion.generation_id(),
        "rows":built.local_row_ids,"receipt":built.ingestion.store.receipt(),
        "device":torch.cuda.get_device_name(),"refused":len(refused.ingestion.store.refused)}
