from __future__ import annotations
from laplace.representation import writing_bodies as bodies

import hashlib
import json
from pathlib import Path

import pytest

from laplace.native import tools as writing_tools
from laplace.writing import session_reads
from laplace.writing import records as writing_records
from laplace.writing.records import _fold as records_fold
from laplace.core.records import journal
from laplace.projects import artifacts


def _project(root):
    (root / "contract").mkdir()
    project = root / "proj"
    project.mkdir()
    (root / "registry_projects.json").write_text(json.dumps({"projects":[{
        "name":"p","kind":"conceptric","project_dir":"proj","tex_root":"proj/main.tex"}]}),
        encoding="utf-8")
    (project / "main.tex").write_bytes(b"\\documentclass{article}\n\\begin{document}\nText.\n\\end{document}\n")
    return project


def _artifact_rows(root):
    path=root / "contract" / "talk.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if json.loads(line).get("record")=="writing-artifact"] if path.is_file() else []


def test_catalogue_reuses_metadata_cut_and_one_basis_without_custody_or_unrelated_paths(tmp_path,monkeypatch):
    project=_project(tmp_path)
    created=[]
    for number in range(3):
        created.append(artifacts.store(tmp_path,'p',{'path':f'note{number}.md',
            'before':None,'content':'Exact result'}))
    newer=artifacts.store(tmp_path,'p',{'path':'note0.md','before':'Exact result','content':'Updated'})
    for number in range(40):
        journal.bank_row('contract/talk.jsonl',{'record':'writing-artifact',
            'id':f'ART-other-{number}','project':'other','path':'outside/path',
            'artifact_path':'../../escape','scope':'project','after':'body'*5000},root=tmp_path)
    journal.bank_row('contract/talk.jsonl',{'record':'writing-artifact','id':'ART-gap',
        'project':'p','path':'outside/path','artifact_path':'../escape','scope':'project'},root=tmp_path)
    journal.bank_row('contract/talk.jsonl',{'record':'writing-artifact',
        'project':'p','path':'proj/legacy.md','artifact_path':'legacy.md','scope':'project'},root=tmp_path)
    context=artifacts._artifact_context;seen=[]
    monkeypatch.setattr(artifacts,'_artifact_context',lambda *a,**k:(seen.append(1),context(*a,**k))[1])
    monkeypatch.setattr(session_reads,'_records',lambda *a,**k:pytest.fail('rich journal hydration'))
    monkeypatch.setattr(bodies,'resolve_fields',lambda *a,**k:pytest.fail('custody body hydration'))
    result=artifacts.catalogue(tmp_path,'p',{'limit':2})
    assert seen==[1] and result['pagination']=={'offset':0,'limit':2,'total':3,'next_offset':2}
    assert result['materials'][0]['id']==newer['id']
    assert result['materials'][0]['currentness']=='NOT_CHECKED'
    assert result['gaps_total']==2 and {row['id'] for row in result['gaps']}=={'ART-gap',None}
    assert artifacts.catalogue(tmp_path,'p',{'offset':2})['materials'][0]['id']==created[2]['id']


def test_artifact_declaration_scopes_shift_decoy_and_refuses_missing_ambiguous_or_changed_owner():
    from laplace.writing import operations
    tools=Path(operations.__file__).read_text();owner=Path(artifacts.__file__).read_text()   # the one operation table
    sites=artifacts.declaration_sites(tools,owner)
    # A normal permission guard and nearby comment must not be the dispatch.
    shifted='\n\n# if operation == "store_artifact":\n'+tools
    shifted_sites=artifacts.declaration_sites(shifted,owner)
    assert int(shifted_sites['store_artifact']['handler'].rsplit(':',1)[1])==int(sites['store_artifact']['handler'].rsplit(':',1)[1])+3
    call='return artifacts.store(root, project, payload, turn_id)'
    with pytest.raises(ValueError,match='differs'):
        artifacts.declaration_sites(tools.replace(call,'return artifacts.read(root, project, payload)'),owner)
    with pytest.raises(ValueError,match='declared owner directly'):
        artifacts.declaration_sites(tools.replace('from laplace.projects import artifacts','from another_package import artifacts'),owner)
    with pytest.raises(ValueError,match='missing or ambiguous'):
        artifacts.declaration_sites(tools.replace('if operation == "store_artifact":','if operation == "other":'),owner)
    duplicate='    if operation == "store_artifact":\n        from laplace.projects import artifacts\n        '+call+'\n'
    with pytest.raises(ValueError,match='missing or ambiguous'):
        artifacts.declaration_sites(tools.replace('    if operation == "read_artifact":',duplicate+'    if operation == "read_artifact":'),owner)


def test_revision_update_preserves_unicode_newline_and_exact_client_handles(tmp_path):
    project=_project(tmp_path);initial="Gerard's result — exact UTF-8.\n";updated="Gerard’s result — exact UTF-8.\n"
    created=writing_tools.execute(tmp_path,"p","work","store_artifact",{
        "path":"research/note.md","before":None,"content":initial,"reason":"create"})
    expected=hashlib.sha256(initial.encode("utf-8")).hexdigest()
    assert created["revision"]==expected
    assert created["read_more"]==created["read_handle"]=={
        "operation":"read_artifact","payload":{"id":created["id"]}}
    assert created["update_handle"]["payload"]=={
        "path":"research/note.md","scope":"project","expected_revision":expected,
        "artifact_id":created["id"]}

    read=writing_tools.execute(tmp_path,"p","work",**created["read_more"])
    assert read["content"]==initial and read["recorded_id"]==created["id"]
    assert read["recorded_revision"]==read["current_revision"]==read["revision"]==expected
    saved=writing_tools.execute(tmp_path,"p","work","store_artifact",{
        **read["update_handle"]["payload"],"content":updated,"reason":"typography"})
    assert (project / "research/note.md").read_bytes()==updated.encode("utf-8")
    assert saved["revision"]==hashlib.sha256(updated.encode("utf-8")).hexdigest()
    receipt=saved["owned_changes"]["files"][0]
    assert receipt["before_sha256"]=="sha256:"+expected
    assert receipt["after_sha256"]==receipt["observed_after_sha256"]=="sha256:"+saved["revision"]

    reread=writing_tools.execute(tmp_path,"p","work","read_artifact",{"id":created["id"]})
    assert reread["recorded_revision"]==expected
    assert reread["current_revision"]==saved["revision"]!=reread["recorded_revision"]


def test_revision_conflict_and_create_collision_write_no_artifact_receipt(tmp_path):
    project=_project(tmp_path)
    created=writing_tools.execute(tmp_path,"p","work","store_artifact",{
        "path":"research/note.md","before":None,"content":"first\n","reason":"create"})
    count=len(_artifact_rows(tmp_path))
    with pytest.raises(ValueError,match="changed or already exists"):
        writing_tools.execute(tmp_path,"p","work","store_artifact",{
            "path":"research/note.md","before":None,"content":"collision\n","reason":"create"})
    (project / "research/note.md").write_bytes(b"external\n")
    with pytest.raises(ValueError,match="revision changed"):
        writing_tools.execute(tmp_path,"p","work","store_artifact",{
            "path":"research/note.md","expected_revision":created["revision"],
            "content":"overwrite\n","reason":"stale"})
    assert (project / "research/note.md").read_bytes()==b"external\n"
    assert len(_artifact_rows(tmp_path))==count


def test_exact_before_update_remains_compatible(tmp_path):
    project=_project(tmp_path)
    writing_tools.execute(tmp_path,"p","work","store_artifact",{
        "path":"research/note.md","before":None,"content":"before\n","reason":"create"})
    saved=writing_tools.execute(tmp_path,"p","work","store_artifact",{
        "path":"research/note.md","before":"before\n","content":"after\n","reason":"legacy guard"})
    assert (project / "research/note.md").read_bytes()==b"after\n"
    assert saved["revision"]==hashlib.sha256(b"after\n").hexdigest()


def test_bounded_reads_keep_full_revision_and_round_trip_utf8_continuations(tmp_path):
    _project(tmp_path);content=("αβγ—line\n"*3000);raw=content.encode("utf-8")
    created=writing_tools.execute(tmp_path,"p","work","store_artifact",{
        "path":"research/large.md","before":None,"content":content,"reason":"large fixture"})
    first=writing_tools.execute(tmp_path,"p","work","read_artifact",{
        "id":created["id"],"limit":16001})
    assert first["complete"] is False and first["next_offset"]>0
    assert first["revision"]==hashlib.sha256(raw).hexdigest()
    parts=[first["content"]];current=first
    while not current["complete"]:
        current=writing_tools.execute(tmp_path,"p","work",**current["read_handle"])
        parts.append(current["content"])
        assert current["revision"]==first["revision"]
    assert "".join(parts)==content
    with pytest.raises(ValueError,match="1-40000"):
        writing_tools.execute(tmp_path,"p","work","read_artifact",{
            "path":"research/large.md","limit":40001})


def test_legacy_art_id_uses_its_recorded_path_without_guessing_from_id(tmp_path):
    project=_project(tmp_path);target=project / "research/legacy.md";target.parent.mkdir();target.write_bytes(b"legacy\n")
    journal.bank_row("contract/talk.jsonl",{"record":"writing-artifact","id":"ART-legacy",
        "project":"p","path":"proj/research/legacy.md","sha256":hashlib.sha256(b"legacy\n").hexdigest()},root=tmp_path)
    read=writing_tools.execute(tmp_path,"p","work","read_artifact",{"id":"ART-legacy"})
    assert read["artifact_path"]=="research/legacy.md" and read["content"]=="legacy\n"
    with pytest.raises(ValueError,match="never infer a path"):
        writing_tools.execute(tmp_path,"p","work","read_artifact",{"id":"ART-unknown"})


def test_oversized_artifact_is_refused_before_materialising_bytes(tmp_path, monkeypatch):
    from pathlib import Path
    project = _project(tmp_path)
    target = project / "large.txt"
    target.write_bytes(b"x" * 2_000_001)
    original = Path.read_bytes
    def checked_read(path):
        if path == target:
            raise AssertionError("oversized artifact was materialised")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", checked_read)
    with pytest.raises(ValueError, match="up to 2 MB"):
        writing_tools.execute(tmp_path, "p", "work", "read_artifact", {"path": "large.txt"})


def test_read_by_id_guarded_update_advances_its_turn_baseline(tmp_path):
    _project(tmp_path)
    created=writing_tools.execute(tmp_path,"p","work","store_artifact",{
        "path":"research/note.md","before":None,"content":"before\n","reason":"create"})
    writing_records.bank(tmp_path,{"record":"writing-session","id":"WS-art","project":"p",
        "provider":"codex","model":"m","effort":"high"})
    writing_records.bank(tmp_path,{"record":"writing-turn","id":"WT-art","session_id":"WS-art",
        "project":"p","text":"Update the artifact.","mode":"work"})
    read=writing_tools.execute(tmp_path,"p","work","read_artifact",{"id":created["id"]},turn_id="WT-art")
    update={**read["update_handle"]["payload"],"content":"after\n","reason":"update"}
    saved=writing_tools.execute(tmp_path,"p","work","store_artifact",update,turn_id="WT-art")
    assert saved["action_receipt"]["refreshed_read_baselines"]==1
    assert saved["action_receipt"]["mutation_attribution"]=={
        "exact":True,"reason":"exact owner receipts match captured before and observed after identities"}

    # The resolved path banked with the read also covers a caller that copies
    # the revision and path but omits the optional receipt association.
    reread=writing_tools.execute(tmp_path,"p","work","read_artifact",{"id":saved["id"]},turn_id="WT-art")
    payload={key:value for key,value in reread["update_handle"]["payload"].items() if key!="artifact_id"}
    saved_again=writing_tools.execute(tmp_path,"p","work","store_artifact",{
        **payload,"content":"final\n","reason":"second update"},turn_id="WT-art")
    assert saved_again["action_receipt"]["refreshed_read_baselines"]==1


def test_artifact_receipt_index_reads_only_new_suffix_and_tracks_scope_duplicates_and_truncation(tmp_path,monkeypatch):
    _project(tmp_path);records_fold._CACHE.clear();talk=tmp_path / "contract/talk.jsonl"
    journal.bank_row("contract/talk.jsonl",{"record":"writing-artifact","id":"ART-old",
        "project":"p","path":"proj/research/old.md","artifact_path":"research/old.md",
        "scope":"project","sha256":"old-sha","before":"x"*100_000,"after":"large body"},root=tmp_path)
    # Simulate the old live cache schema already parked at EOF when this code is
    # deployed. The first artifact lookup must backfill once rather than miss it.
    records_fold._CACHE[str(talk)]={"offset":talk.stat().st_size,"sessions":{},
        "turns":{},"orders":{},"sequence":0}
    first=session_reads.artifact_record(tmp_path,"p","ART-old")
    assert first["path"]=="proj/research/old.md"
    assert "before" not in first and "after" not in first
    from laplace.work import author_history_metrics
    state=author_history_metrics.index(tmp_path);old_offset=state.offset
    # Artifact lookup owns metadata now; the parked rich cache is not hydrated.
    assert "artifact_records" not in records_fold._CACHE[str(talk)]

    journal.bank_row("contract/talk.jsonl",{"record":"writing-artifact","id":"ART-new",
        "project":"p","path":"proj/research/new.md","artifact_path":"research/new.md",
        "scope":"project","sha256":"new-sha"},root=tmp_path)
    journal.bank_row("contract/talk.jsonl",{"record":"writing-artifact","id":"ART-old",
        "project":"other","path":"other/research/old.md","artifact_path":"research/old.md",
        "scope":"project","sha256":"other-sha"},root=tmp_path)
    appended=talk.stat().st_size-old_offset;seeks=[];read_bytes=0;anchor_bytes=0;raw_reads=[];real_open=Path.open

    class Observed:
        def __init__(self,stream):self.stream=stream
        def __enter__(self):return self
        def __exit__(self,*args):return self.stream.__exit__(*args)
        def __getattr__(self,name):return getattr(self.stream,name)
        def seek(self,offset,*args):seeks.append(offset);return self.stream.seek(offset,*args)
        def readline(self,*args):
            nonlocal read_bytes
            value=self.stream.readline(*args);read_bytes+=len(value);return value
        def read(self,*args):
            nonlocal anchor_bytes
            offset=self.stream.tell();value=self.stream.read(*args);anchor_bytes+=len(value);raw_reads.append((offset,len(value)));return value

    def observed_open(path,*args,**kwargs):
        stream=real_open(path,*args,**kwargs)
        return Observed(stream) if Path(path)==talk and args and args[0]=="rb" else stream

    monkeypatch.setattr(Path,"open",observed_open)
    assert session_reads.artifact_record(tmp_path,"p","ART-old")["sha256"]=="old-sha"
    assert session_reads.artifact_record(tmp_path,"other","ART-old")["sha256"]=="other-sha"
    # Only the suffix is parsed. Replacement-detection windows are bounded even
    # though the historical boundary row itself contains a 100 KB source body.
    assert old_offset in seeks and read_bytes==appended
    # Each admitted ART metadata lookup now proves its exact row bytes; these
    # reads are charged, not mistaken for another whole-ledger scan.
    selected=[row for row in state.rows if row.get("id")=="ART-old"]
    selected_bytes=sum(row["_end"]-row["_offset"] for row in selected)
    assert all((row["_offset"],row["_end"]-row["_offset"]) in raw_reads for row in selected)
    assert anchor_bytes-selected_bytes<=8192 and state.offset==old_offset+appended
    assert state.stats["scans"]==1

    before_duplicate=state.offset
    journal.bank_row("contract/talk.jsonl",{"record":"writing-artifact","id":"ART-old",
        "project":"p","path":"proj/research/collision.md","artifact_path":"research/collision.md",
        "scope":"project","sha256":"collision"},root=tmp_path)
    with pytest.raises(ValueError,match="ambiguous"):
        session_reads.artifact_record(tmp_path,"p","ART-old")
    assert seeks[-1]==before_duplicate
    assert session_reads.artifact_record(tmp_path,"other","ART-old")["sha256"]=="other-sha"

    replacement={"record":"writing-artifact","id":"ART-reset","project":"p",
        "path":"proj/research/reset.md","artifact_path":"research/reset.md","scope":"project",
        "sha256":"reset"}
    talk.write_text(json.dumps(replacement)+"\n",encoding="utf-8")
    assert session_reads.artifact_record(tmp_path,"p","ART-reset")["sha256"]=="reset"
    assert session_reads.artifact_record(tmp_path,"p","ART-old") is None
