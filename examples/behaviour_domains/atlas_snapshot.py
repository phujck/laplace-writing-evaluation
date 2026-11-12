"""Small exact-byte snapshot with sealed placeholder and corruption controls.
Bundle construction is scoped from atlas/tests/test_snapshot.py, no test imports.
"""
from __future__ import annotations
import dataclasses
import json
import shutil
from datetime import datetime, timezone

def run(root, rec):
    from atlas.ids import canonical_json, hash_bytes, chash
    from atlas.schema import REFS_ONLY, RecordSnapshot, SnapshotNode, Span
    from atlas.snapshot import load_snapshot
    from atlas.store import BlobStore, sha256_file, write_atomic, write_jsonl
    from atlas.errors import SealedRead, SnapshotIncomplete, BlobHashMismatch
    base=root/"atlas-example"/"snapshot"
    base.mkdir(parents=True)
    body=b"first\nsecond\n"
    key=hash_bytes(body)
    BlobStore(base/"blobs").put(body)
    node=SnapshotNode(node_id="example.txt",path="example.txt",kind="txt",sealed=False,
        is_text=True,read_policy="text",content_hash=key,content_blob=key,size_bytes=len(body))
    sealed=SnapshotNode(node_id="sealed/placeholder.txt",path="sealed/placeholder.txt",
        kind="placeholder",sealed=True,is_text=False,read_policy="sealed-refs-only",
        content_hash=REFS_ONLY,content_blob=None,size_bytes=0)
    spans=[]
    for start,end in ((0,6),(6,len(body))):
        spans.append(Span(span_id=Span.compute_id(key,start,end,"example-lines/1","seg/1"),
            node_id=node.node_id,source_content_hash=key,segmenter_id="example-lines/1",
            seg_version="seg/1",start=start,end=end,est_tokens=2,is_leaf=True,
            parent_span=None,kind="authored-line"))
    write_jsonl(base/"nodes.jsonl",[n.to_dict() for n in (node,sealed)])
    write_jsonl(base/"spans.jsonl",[s.to_dict() for s in spans])
    seal={"soul_paths_with_content":0,"sealed_spans":0,"sealed_nodes":1,
          "bytes_read_from_sealed":0,"sealed_prefixes":["sealed/"],"nodes_scanned":2}
    write_atomic(base/"seal_report.json",(canonical_json(seal)+"\n").encode())
    man=RecordSnapshot(snapshot_id="",created_ts=datetime.now(timezone.utc).isoformat(),
        atlas_schema_version="1",exporter_version="1",source_repo="authored-example",
        commit_sha="not-a-git-export",node_count=2,text_node_count=1,sealed_node_count=1,
        asset_node_count=0,total_content_bytes=len(body),
        nodes_sha256=sha256_file(base/"nodes.jsonl"),
        seal_report_sha256=sha256_file(base/"seal_report.json"),
        sealed_prefixes=["sealed/"],sealed_paths=[],excluded_prefixes=[],
        text_extensions=[".txt"],node_limit=None,tree_dirty=False,
        dirty_node_count=0,dirty_nodes_hash=chash([]))
    man=dataclasses.replace(man,snapshot_id=man.computed_id())
    write_atomic(base/"manifest.json",(json.dumps(man.to_dict(),sort_keys=True,indent=2)+"\n").encode())
    snap=load_snapshot(base)
    verified=rec.call("atlas-snapshot-verify",snap.verify)
    assert snap.read_node_bytes(node.node_id)==body
    assert snap.read_span_bytes(spans[0].span_id)==b"first\n"
    rec.save("atlas-span",{"span":spans[0].to_dict(),"bytes_utf8":snap.read_span_bytes(spans[0].span_id).decode()})
    rec.refuses("atlas-sealed-read",SealedRead,snap.read_node_bytes,sealed.node_id)
    rec.refuses("atlas-missing-span",SnapshotIncomplete,snap.read_span_bytes,"sha256:"+"f"*64)
    damaged=base.with_name("damaged-snapshot")
    shutil.copytree(base,damaged)
    BlobStore(damaged/"blobs").key_path(key).write_bytes(b"deliberate corruption")
    rec.refuses("atlas-snapshot-corruption",BlobHashMismatch,load_snapshot(damaged).verify)
    assert snap.read_node_bytes(node.node_id)==body
    return {"status":"EXECUTED","snapshot":man.snapshot_id,
        "path":str(base.relative_to(root)),"span":spans[0].span_id,
        "qualification":"Synthetic bundle built here, no repository export or private sealed bytes read",
        "verification":verified}
