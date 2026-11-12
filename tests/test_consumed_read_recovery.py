"""Currentness observations survive refusal formatting without a second read pass."""
import json
import pytest
from laplace.web import authoring as surface
from laplace.manuscript import manuscript_proposals as proposals
from laplace.native import tools as writing_tools
from laplace.writing import operations
from laplace.projects import artifacts as writing_artifacts
from laplace.manuscript import source_application
from laplace.writing import records as writing_records
from laplace.manuscript import proposal_currentness
from laplace.writing import session_reads
from laplace.writing.records import _fold as records_fold
from laplace.core import checkout
from test_proposal_lifecycle import setup, RAW
from test_writing_controller import _bind_rewrite_fixture


def seed_reads(root, monkeypatch, count):
    md,turn,changes,context=setup(root)
    calls=_bind_rewrite_fixture(monkeypatch,md)
    project=writing_artifacts.project_root(root,'fixture')
    paths=[]
    for i in range(count):
        path=project/f'evidence-{i}.txt';path.write_text('Retained evidence.')
        paths.append(path)
        writing_tools.execute(root,'fixture','revise','read_artifact',
            {'path':path.name,'scope':'project'},turn_id=turn)
    writing_records.bank(root,{'record':'writing-proposal','id':'PROP-read-recovery',
        'turn_id':turn,'project':'fixture','proposal':{'answer':'Exact consumed evidence.','edits':changes}})
    version=session_reads._records(root)['turns'][turn]['pending_proposal_version']
    return md,turn,version,paths,calls


@pytest.mark.parametrize('count',[1,8,39])
def test_changed_last_read_leads_and_diagnostics_do_not_replay_or_rebase(tmp_path,monkeypatch,count):
    md,turn,version,paths,calls=seed_reads(tmp_path,monkeypatch,count)
    paths[-1].write_text('Changed evidence.')
    before=(tmp_path/'contract/talk.jsonl').read_bytes()
    actual=operations._execute;observed=[]
    def execute(*args,**kwargs):
        observed.append((args[3],args[4]));return actual(*args,**kwargs)
    monkeypatch.setattr(operations,'_execute',execute)
    monkeypatch.setattr(operations, '_execute', execute)   # the owner call of every replay (the one operation table)
    with pytest.raises(proposal_currentness.ProposalBasisRefused) as refused:
        source_application.apply_proposal(tmp_path,{'turn_id':turn,'proposal_version':version})
    assert len(observed)==count
    diagnostic=writing_tools.failure_response(tmp_path,'fixture','revise','apply_revision',
        {'turn_id':turn,'proposal_version':version},refused.value,turn)
    assert len(observed)==count, 'Formatter must not repeat validation reads'
    recovery=diagnostic['consumed_read_recovery']
    assert recovery['observed_changed_read_count']==1
    assert recovery['changed_reads'][0]['currentness']=='CHANGED'
    assert diagnostic['next_reads'][0]=={'operation':'read_artifact','payload':{'path':paths[-1].name,'scope':'project'}}
    assert recovery['changed_reads'][0]['read_detail']['payload']['id'].startswith('activity:journal:READ-')
    assert not calls and (md/'main.tex').read_text()==RAW
    assert (tmp_path/'contract/talk.jsonl').read_bytes()==before


def test_multiple_changes_and_unavailable_are_reported_together_and_http_keeps_owner_observations(tmp_path,monkeypatch):
    md,turn,version,paths,calls=seed_reads(tmp_path,monkeypatch,3)
    paths[0].write_text('Changed one.');paths[2].unlink()
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    status,ctype,body=surface.handle('/authoring/apply',{},'POST',json.dumps({'project':'fixture','turn_id':turn,'proposal_version':version}).encode())
    result=json.loads(body);recovery=result['consumed_read_recovery']
    assert status==409 and recovery['observed_changed_read_count']==2
    assert [r['currentness'] for r in recovery['changed_reads']]==['CHANGED','UNAVAILABLE']
    assert not calls and (md/'main.tex').read_text()==RAW
    assert all('content' not in r for r in recovery['changed_reads'])


def test_oversized_and_omitted_reads_have_exact_retained_handles_not_broader_queries():
    reads={str(i):{'id':'READ-'+str(i),'operation':'repository','payload':{'action':'read','path':'p'*2000+str(i)}} for i in range(10)}
    observations=[{'read_id':r['id'],'operation':'repository','currentness':'CHANGED',
        'consumed_output_sha256':'old','observed_output_sha256':'new'} for r in reads.values()]
    recovery=proposal_currentness.consumed_read_recovery({'id':'WT-fixture'},
        {'record_id':'PROP-exact','tool_reads':reads},observations)
    assert recovery['observed_changed_read_count']==10 and recovery['changed_reads_omitted']==2
    assert len(recovery['changed_reads'])==8 and len(recovery['next_reads'])==8
    assert recovery['next_reads'][0]=={'operation':'author_history','payload':{'view':'record','id':'activity:journal:READ-0'}}
    assert all(r['payload_omitted'] for r in recovery['changed_reads'])
    assert recovery['basis_detail']['payload']['id']=='activity:journal:PROP-exact'
    assert len(json.dumps(recovery))<6500


def test_cached_human_merge_refuses_with_same_consumed_read_diagnostic(tmp_path,monkeypatch):
    md,turn,version,paths,calls=seed_reads(tmp_path,monkeypatch,1)
    opened=proposals.preview(tmp_path,'fixture',turn,version)
    row=opened['edits'][0];token=row['review_token']
    paths[0].write_text('Changed evidence after comparison opened.')
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    status,_,body=surface.handle('/authoring/proposal-decision',{},'POST',json.dumps({
        'project':'fixture','turn_id':turn,'proposal_version':version,'edit_id':row['edit_id'],
        'decision':'merge','review_token':token,'merged_after':'Retained author draft.'}).encode())
    recovery=json.loads(body)['consumed_read_recovery']
    assert status==409 and recovery['observed_changed_read_count']==1
    assert recovery['next_reads'][0]['payload']['path']==paths[0].name
    assert not calls and (md/'main.tex').read_text()==RAW


@pytest.mark.parametrize('wrappers',[1,3])
def test_opaque_nested_refusal_preserves_native_and_http_owner_metadata(tmp_path,monkeypatch,wrappers):
    md,turn,version,paths,calls=seed_reads(tmp_path,monkeypatch,39)
    paths[-1].write_text('Changed last evidence.')
    before=(tmp_path/'contract/talk.jsonl').read_bytes()
    actual=operations._execute;checks=[]
    def execute(*a,**k):
        checks.append(a[3]);return actual(*a,**k)
    monkeypatch.setattr(operations,'_execute',execute)
    monkeypatch.setattr(operations, '_execute', execute)   # the owner call of every replay (the one operation table)
    with pytest.raises(proposal_currentness.ProposalBasisRefused) as refusal:
        source_application.apply_proposal(tmp_path,{'turn_id':turn,'proposal_version':version})
    assert len(checks)==39
    wrapped=refusal.value
    for _ in range(wrappers):
        try:raise ValueError('Authoring action refused.') from wrapped
        except ValueError as error:wrapped=error
    owned=proposal_currentness.proposal_refusal_details(wrapped)
    assert owned==refusal.value.details
    response=writing_tools.failure_response(tmp_path,'fixture','revise','apply_revision',{},wrapped,turn)
    assert response['error']=='Authoring action refused.'
    assert response['consumed_read_recovery']==owned['consumed_read_recovery']
    assert response['next_reads'][0]=={'operation':'read_artifact','payload':{'path':'evidence-38.txt','scope':'project'}}
    # No turn lookup is needed to preserve the carried exact read envelope.
    without_turn=writing_tools.failure_response(tmp_path,'fixture','revise','apply_revision',{},wrapped)
    assert without_turn['consumed_read_recovery']==response['consumed_read_recovery']
    assert without_turn['next_reads']==owned['consumed_read_recovery']['next_reads']
    def apply_wrapped(*a,**k):raise wrapped
    monkeypatch.setattr(source_application,'apply_proposal',apply_wrapped);monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    status,_,body=surface.handle('/authoring/apply',{},'POST',json.dumps({'project':'fixture','turn_id':turn,'proposal_version':version}).encode())
    http=json.loads(body)
    assert status==409 and http['error']=='Authoring action refused.'
    assert http['consumed_read_recovery']==owned['consumed_read_recovery']
    assert len(checks)==39 and not calls and (md/'main.tex').read_text()==RAW
    assert (tmp_path/'contract/talk.jsonl').read_bytes()==before


def test_context_and_multiple_read_families_survive_one_validation_pass(tmp_path,monkeypatch):
    md,turn,version,paths,calls=seed_reads(tmp_path,monkeypatch,1)
    original=session_reads._records(tmp_path)['turns'][turn]
    basis=original['proposal_bases'][version]
    # A synthetic immutable second family tests this reducer without a provider.
    source_read={'id':'READ-semantic-fixture','operation':'logical_plan','payload':{'node':'target:Y'},'output_sha256':'old'}
    basis={**basis,'tool_reads':{**basis['tool_reads'],'semantic-fixture':source_read}}
    basis.update(read_ids=[r['id'] for r in basis['tool_reads'].values()],
        read_receipts_sha256=records_fold._read_basis_digest(basis['tool_reads']))
    original={**original,'proposal_bases':{version:basis}}
    paths[0].write_text('Changed evidence.')
    actual=operations._execute
    def execute(*args,**kwargs):
        return {'node':'Changed Y.'} if args[3]=='logical_plan' else actual(*args,**kwargs)
    monkeypatch.setattr(operations,'_execute',execute)
    monkeypatch.setattr(operations, '_execute', execute)   # the owner call of every replay (the one operation table)
    from laplace.pipeline import authoring
    monkeypatch.setattr(authoring,'inspect',lambda *a,**k:{'staleness_scope':{'receipts_checked':1},
        'stale':[{'context_id':basis['context_id'],'reasons':['argument-or-framing-changed']}]})
    checked=proposal_currentness._proposal_validation_basis(tmp_path,original,version,proposals.saved_proposals(original)[version])
    assert checked['currentness']=='STALE'
    recovery=checked['consumed_read_recovery']
    assert recovery['changed_read_families']==['read_artifact','logical_plan']
    assert recovery['context_reasons']==['argument-or-framing-changed']
    assert not calls and (md/'main.tex').read_text()==RAW


def _with_reads(original,version,extra):
    basis=original['proposal_bases'][version]
    reads={**basis['tool_reads'],**extra}
    basis={**basis,'tool_reads':reads}
    basis.update(read_ids=[r['id'] for r in reads.values()],read_receipts_sha256=records_fold._read_basis_digest(reads))
    return {**original,'proposal_bases':{version:basis}}


def test_unrelated_coordination_reads_are_review_obligations_while_changed_evidence_still_refuses(tmp_path,monkeypatch):
    # The original apply refusals named dispatch_status, session_settings, materials and Work project reads that
    # moved with unrelated activity. They stay replayed and reported as obligations; consumed evidence still refuses.
    md,turn,version,paths,calls=seed_reads(tmp_path,monkeypatch,1)
    original=session_reads._records(tmp_path)['turns'][turn]
    coordination={
        'coord-dispatch':{'id':'READ-coord-dispatch','operation':'dispatch_status','payload':{'id':'DISPATCH-public'},'output_sha256':'old'},
        'coord-session':{'id':'READ-coord-session','operation':'session_settings','payload':{},'output_sha256':'old'},
        'coord-materials':{'id':'READ-coord-materials','operation':'materials','payload':{},'output_sha256':'old'},
        'coord-work':{'id':'READ-coord-work','operation':'project','payload':{'view':'detail','id':'WORK-public'},'output_sha256':'old'}}
    record=_with_reads(original,version,coordination)
    moved={'dispatch_status','session_settings','materials','project'}
    actual=operations._execute
    def execute(*args,**kwargs):
        return {'unrelated':'activity moved this read'} if args[3] in moved else actual(*args,**kwargs)
    monkeypatch.setattr(operations,'_execute',execute)
    proposal=proposals.saved_proposals(record)[version]
    checked=proposal_currentness._proposal_validation_basis(tmp_path,record,version,proposal)
    assert checked['currentness']=='CURRENT',checked
    assert sorted(row['detail']['operation'] for row in checked['review_obligations'])==sorted(moved)
    assert checked['semantic_currentness']=='REVIEW_REQUIRED'
    paths[0].write_text('Changed evidence.')
    stale=proposal_currentness._proposal_validation_basis(tmp_path,record,version,proposal)
    assert stale['currentness']=='STALE'
    assert stale['consumed_read_recovery']['changed_read_families']==['read_artifact']
    paths[0].write_text('Retained evidence.')
    # The default project read (argument and framing) and a logical plan read remain consumed inputs.
    for ident,operation,payload in (('READ-default-project','project',{}),('READ-plan-node','logical_plan',{'node':'target:Y'})):
        guarded=_with_reads(original,version,{**coordination,ident:{'id':ident,'operation':operation,'payload':payload,'output_sha256':'old'}})
        moved_now=moved|{operation}
        monkeypatch.setattr(operations,'_execute',lambda *a,**k:{'changed':a[3]} if a[3] in moved_now else actual(*a,**k))
        refused=proposal_currentness._proposal_validation_basis(tmp_path,guarded,version,proposals.saved_proposals(guarded)[version])
        assert refused['currentness']=='STALE'
        assert refused['consumed_read_recovery']['changed_read_families']==[operation]
    assert not calls and (md/'main.tex').read_text()==RAW


def _native_research_candidate(root, monkeypatch):
    from test_writing_controller import _import_project, _seed_revision
    from test_research_surface import _consumption_project
    from laplace.research import research_context, research_catalogue
    from laplace.manuscript import review_surface
    md,_=_import_project(root,files={"main.tex":RAW})
    home=research_context.project("fixture",root)[1]
    _consumption_project(root,home)
    changes=[{"file":"main.tex","line_start":3,"line_end":3,
              "before":"First premise.","after":"An exactly guarded premise.","reason":"Copyedit fixture."}]
    turn=_seed_revision(root,"fixture",changes,selection={"files":["main.tex"]},suffix="research-basis")
    # This only selects the real owner's fixture root, not a stub adjudication.
    monkeypatch.setattr(review_surface,"_repo_root",lambda:root)
    monkeypatch.setattr(checkout,"repo_root",lambda:root)
    research_catalogue.state_cache_clear()
    first=writing_tools.execute(root,"fixture","revise","research",{"view":"summary"},turn_id=turn)
    second=writing_tools.execute(root,"fixture","revise","research",{"view":"summary"},turn_id=turn)
    writing_records.bank(root,{"record":"writing-proposal","id":"PROP-new-research","turn_id":turn,
        "project":"fixture","proposal":{"answer":"Fresh read, fresh candidate.","edits":changes}})
    state=session_reads._records(root)["turns"][turn]
    return md,home,turn,state["pending_proposal_version"],first,second


def test_native_research_capture_seal_replay_and_real_guarded_source_effect(tmp_path,monkeypatch):
    from laplace.writing import reads
    from laplace.manuscript import proposal_navigation
    from laplace.representation import writing_bodies
    md,home,turn,version,first,second=_native_research_candidate(tmp_path,monkeypatch)
    warm=session_reads._records(tmp_path)["turns"][turn]
    basis=warm["proposal_bases"][version]
    read=next(r for r in basis["tool_reads"].values() if r["operation"]=="research")
    assert first["producers"]!=second["producers"]
    assert read["consumption"]["schema_version"]==reads.RESEARCH_RECEIPT
    rows=[json.loads(x) for x in (tmp_path/"contract/talk.jsonl").read_text().splitlines()]
    banked=next(r for r in rows if r.get("id")==read["id"])
    from laplace.core import bodies
    assert bodies.is_reference(banked["research_raw"])
    raw=writing_bodies.resolve_fields(banked,tmp_path)["research_raw"]
    assert raw["producers"]==second["producers"] and raw["read_basis"]==second["read_basis"]
    cold=proposal_navigation.selected_records(tmp_path,"fixture",turn,version)
    assert records_fold._read_basis_digest(cold["turns"][turn]["proposal_bases"][version]["tool_reads"])==basis["read_receipts_sha256"]
    journal_before=(tmp_path/"contract/talk.jsonl").read_bytes()
    observed=operations.replay_read(tmp_path,"fixture","revise",read,turn)
    assert reads.comparison_digest("research",observed,read,root=tmp_path)==reads.consumed_digest(read)
    assert (tmp_path/"contract/talk.jsonl").read_bytes()==journal_before
    applied=source_application.apply_proposal(tmp_path,{"turn_id":turn,"proposal_version":version})
    assert applied["complete"] and applied["receipts"]
    assert "An exactly guarded premise." in (md/"main.tex").read_text()
    assert applied["validation_basis"]["currentness"]=="CURRENT"
    assert applied["owned_changes"]["files"]
    assert list((md/"feedback").glob("*")), "the actual rewrite owner retains its receipt"


@pytest.mark.parametrize("change",["code","helper","result","source"])
def test_native_research_substance_or_source_change_refuses_before_write(tmp_path,monkeypatch,change):
    md,home,turn,version,_,_=_native_research_candidate(tmp_path,monkeypatch)
    path={"code":home/"source.py","helper":home/"helper.py",
          "result":home/"result.json","source":md/"main.tex"}[change]
    path.write_text(path.read_text()+"\n")
    if change=="result":path.write_text('{"score":9}')
    before=(md/"main.tex").read_bytes()
    with pytest.raises(proposal_currentness.ProposalBasisRefused):
        source_application.apply_proposal(tmp_path,{"turn_id":turn,"proposal_version":version})
    assert (md/"main.tex").read_bytes()==before


@pytest.mark.parametrize("corrupt",["version","descriptor","dropped","raw","missing-raw","missing-blob","corrupt-blob","scope","projection","alias","duplicate"])
def test_sealed_research_descriptor_and_raw_custody_tamper_refuse(tmp_path,monkeypatch,corrupt):
    md,home,turn,version,_,_=_native_research_candidate(tmp_path,monkeypatch)
    path=tmp_path/"contract/talk.jsonl";rows=[json.loads(x) for x in path.read_text().splitlines()]
    for row in rows:
        if row.get("record")=="writing-tool-read" and row.get("operation")=="research":
            if corrupt=="version":row["consumption"]["schema_version"]="future"
            elif corrupt=="descriptor":row["consumption"]["semantic_sha256"]="0"*64
            elif corrupt=="dropped":row.pop("consumption")
            elif corrupt=="raw":row["research_raw"]={"altered":True}
            elif corrupt in {"missing-blob","corrupt-blob"}:
                from laplace.representation import writing_bodies
                data=writing_bodies.read_bytes(row["research_raw"],tmp_path)
                blob=next(p for p in (tmp_path/"contract/writing_bodies").rglob("*")
                          if p.is_file() and p.read_bytes()==data)
                if corrupt=="missing-blob":blob.unlink()
                else:blob.write_bytes(b"corrupt raw bytes")
            elif corrupt=="scope":row["consumption"]["scope"]["project"]="foreign"
            elif corrupt=="projection":row["projection"]={"unsupported":True}
            elif corrupt=="alias":row["payload"]["view"]="result"
            elif corrupt=="missing-raw":row.pop("research_raw")
    if corrupt=="duplicate":
        rows.append(next(dict(r) for r in reversed(rows) if r.get("operation")=="research" and r.get("record")=="writing-tool-read"))
    path.write_text("".join(json.dumps(r)+"\n" for r in rows))
    before=(md/"main.tex").read_bytes()
    with pytest.raises((proposal_currentness.ProposalBasisRefused,ValueError)):
        source_application.apply_proposal(tmp_path,{"turn_id":turn,"proposal_version":version})
    assert (md/"main.tex").read_bytes()==before


def test_research_prewrite_capture_and_owned_baseline_keep_version_and_old_seal(tmp_path,monkeypatch):
    from laplace.writing import turn_reads, reads
    md,home,turn,version,_,_=_native_research_candidate(tmp_path,monkeypatch)
    original=session_reads._records(tmp_path)["turns"][turn]["proposal_bases"][version]
    sealed=json.dumps(original,sort_keys=True,default=str)
    before=turn_reads.capture_turn_read_baselines(tmp_path,"fixture",turn,"research_record")
    assert before["conflicts"]==0 and before["baselines"]
    read=next(r for r in original["tool_reads"].values() if r["operation"]=="research")
    from laplace.representation import writing_bodies
    raw=writing_bodies.resolve_fields(read,tmp_path)["research_raw"]
    expected=next(r["revision"] for r in raw["results"] if r["id"]=="basis:result")
    writing_tools.execute(tmp_path,"fixture","revise","research_record",{
        "record":{"kind":"result","id":"basis:result","result":"result.json","source":"analysis.py",
                  "summary":"A deliberately renewed interpretation."},
        "expected_revision":expected},turn_id=turn)
    current=session_reads._records(tmp_path)["turns"][turn]
    assert json.dumps(current["proposal_bases"][version],sort_keys=True,default=str)==sealed
    new=next(r for r in current["tool_reads"].values() if r["operation"]=="research")
    from laplace.core import bodies
    retained=next(json.loads(line) for line in (tmp_path/"contract/talk.jsonl").read_text().splitlines()
                  if json.loads(line).get("id")==new["id"])
    assert new["record"]=="writing-tool-read-baseline"
    assert bodies.is_reference(new["research_raw"])
    assert new["research_raw"]==retained["research_raw"]
    assert new["consumption"]["schema_version"]==read["consumption"]["schema_version"]
    assert new["consumption"]["semantic_sha256"]!=read["consumption"]["semantic_sha256"]
    assert reads.comparison_digest("research",operations.replay_read(tmp_path,"fixture","revise",new,turn),new,root=tmp_path)==reads.consumed_digest(new)
    before_source=(md/"main.tex").read_bytes()
    with pytest.raises(proposal_currentness.ProposalBasisRefused):
        source_application.apply_proposal(tmp_path,{"turn_id":turn,"proposal_version":version})
    assert (md/"main.tex").read_bytes()==before_source


def test_research_basis_does_not_invalidate_proven_owned_sibling_source_transitions(tmp_path,monkeypatch):
    md,home,turn,_,_,_=_native_research_candidate(tmp_path,monkeypatch)
    from laplace.manuscript import proposal_preflight
    original=(md/"main.tex").read_text()
    edits=[{"file":"main.tex","line_start":line,"line_end":line,"before":before,"after":after,
            "reason":"Exact sibling copyedit.","source_anchor":proposal_preflight.source_anchor(original,line,line)}
           for line,before,after in [(3,"First premise.","First guarded sibling."),
                                     (5,"Second conclusion.","Second guarded sibling.")]]
    writing_records.bank(tmp_path,{"record":"writing-proposal","id":"PROP-research-siblings",
        "turn_id":turn,"project":"fixture","proposal":{"answer":"Two independently guarded hunks.","edits":edits}})
    state=session_reads._records(tmp_path)["turns"][turn];version=state["pending_proposal_version"]
    first=proposals.preview(tmp_path,"fixture",turn,version)
    selected=first["edits"][0]
    proposals.decide(tmp_path,"fixture",{"turn_id":turn,"proposal_version":version,
        "edit_id":selected["edit_id"],"decision":"accept"})
    second=proposals.preview(tmp_path,"fixture",turn,version)
    pending=next(e for e in second["edits"] if e["edit_id"]!=selected["edit_id"])
    assert pending["basis_currentness"]=="CURRENT"
    result=proposals.decide(tmp_path,"fixture",{"turn_id":turn,"proposal_version":version,
        "edit_id":pending["edit_id"],"decision":"accept"})
    assert result["remaining"]==0
    assert "First guarded sibling." in (md/"main.tex").read_text()
    assert "Second guarded sibling." in (md/"main.tex").read_text()



@pytest.mark.parametrize("scientific_role",["producer-project-input","record-manuscript-analysis"])
def test_selected_manuscript_declared_scientific_dependency_invalidates_research_after_owned_edit(
        tmp_path,monkeypatch,scientific_role):
    """Selection identity must not exempt the SAME file's explicit scientific bytes."""
    import hashlib
    from test_research_surface import _project
    from test_writing_controller import _seed_revision
    from laplace.research import research_context, research_catalogue, research_records, research_runs
    from laplace.manuscript import manuscript_source, proposal_preflight, review_surface
    from laplace.writing import reads

    md=_project(tmp_path)
    selected=md/"main.tex";selected.write_text(RAW)
    (md/"result.json").write_text('{"score":1}')
    item,home=research_context.project("fixture",tmp_path)
    selection=manuscript_source.resolve("fixture",repo_root=tmp_path)
    physical=(tmp_path/selection["root"]).resolve()
    assert home==md.resolve() and physical.samefile(selected)
    project=research_context.project_root(item,tmp_path)
    relative=physical.relative_to(project).as_posix()
    spec={"id":"overlap","scope":"project","executable":"manuscript/source.py",
          "modes":["smoke"],"allowed_args":{},
          "dependencies":[relative] if scientific_role=="producer-project-input" else []}
    assert research_runs.register_producer("fixture",spec,tmp_path)[0]==201
    source="main.tex" if scientific_role=="record-manuscript-analysis" else "source.py"
    status,created=research_records.record("fixture",{
        "kind":"result","id":"overlap:result","result":"result.json","source":source,
        "summary":"Local dependency-overlap fixture, not a scientific validation."},tmp_path)
    assert status==201
    expected=hashlib.sha256(physical.read_bytes()).hexdigest()
    if scientific_role=="producer-project-input":
        declared=research_runs.producer_dependencies(project,spec)
        fact=next(row for row in declared if row["path"]==relative)
        assert (project/fact["path"]).samefile(physical)
    else:
        fact=next(row for row in created["record"]["provenance"]["dependencies"]
                  if row["path"]=="main.tex")
        assert (home/fact["path"]).samefile(physical)
    assert fact["status"]=="PRESENT" and fact["sha256"]==expected

    changes=[{"file":"main.tex","line_start":line,"line_end":line,"before":before,"after":after,
              "reason":"Owned sibling changes a deliberately declared scientific dependency.",
              "source_anchor":proposal_preflight.source_anchor(RAW,line,line)}
             for line,before,after in [(3,"First premise.","Changed scientific-input bytes."),
                                       (5,"Second conclusion.","Must await fresh scientific basis.")]]
    turn=_seed_revision(tmp_path,"fixture",changes,selection={"files":["main.tex"]},
                        suffix="scientific-overlap")
    monkeypatch.setattr(review_surface,"_repo_root",lambda:tmp_path)
    monkeypatch.setattr(checkout,"repo_root",lambda:tmp_path)
    research_catalogue.state_cache_clear()
    captured=writing_tools.execute(tmp_path,"fixture","revise","research",
                                  {"view":"summary"},turn_id=turn)
    assert captured["producer_runs"]==[]
    assert not (home/"research_runs/index.json").exists(), "literal zero runs, not a failed run"
    assert next(r for r in captured["results"] if r["id"]=="overlap:result")["currentness"]=="CURRENT"
    writing_records.bank(tmp_path,{"record":"writing-proposal","id":"PROP-scientific-overlap",
        "turn_id":turn,"project":"fixture","proposal":{"answer":"Fresh declared dependency basis.","edits":changes}})
    state=session_reads._records(tmp_path)["turns"][turn];version=state["pending_proposal_version"]
    read=next(r for r in state["proposal_bases"][version]["tool_reads"].values()
              if r["operation"]=="research")
    assert read["consumption"]["status"]=="AVAILABLE"
    unchanged=operations.replay_read(tmp_path,"fixture","revise",read,turn)
    assert reads.comparison_digest("research",unchanged,read,root=tmp_path)==reads.consumed_digest(read)

    preview=proposals.preview(tmp_path,"fixture",turn,version)
    first_id=preview["edits"][0]["edit_id"]
    applied=proposals.decide(tmp_path,"fixture",{"turn_id":turn,"proposal_version":version,
        "edit_id":first_id,"decision":"accept"})
    assert applied["application"]["complete"] and applied["application"]["receipts"]
    assert "Changed scientific-input bytes." in physical.read_text()
    before_second=physical.read_bytes()
    # Prove the Research receipt itself changed, independently of source-text guard refusal.
    reobserved=operations.replay_read(tmp_path,"fixture","revise",read,turn)
    assert reads.comparison_digest("research",reobserved,read,root=tmp_path)!=reads.consumed_digest(read)
    assert reobserved["consumption_basis"]["provenance_sha256"]!=captured["consumption_basis"]["provenance_sha256"]
    if scientific_role=="record-manuscript-analysis":
        assert next(r for r in reobserved["results"] if r["id"]=="overlap:result")["currentness"]=="STALE"
    current=session_reads._records(tmp_path)["turns"][turn]
    basis=proposal_currentness._proposal_validation_basis(tmp_path,current,version,
                                                         proposals.saved_proposals(current)[version])
    assert basis["currentness"]=="STALE"
    assert "research" in basis["consumed_read_recovery"]["changed_read_families"]
    pending=next(e for e in changes if proposals.edit_id(e)!=first_id)
    with pytest.raises(ValueError):
        proposals.decide(tmp_path,"fixture",{"turn_id":turn,"proposal_version":version,
            "edit_id":proposals.edit_id(pending),"decision":"accept"})
    assert physical.read_bytes()==before_second
    assert "Must await fresh scientific basis." not in physical.read_text()


@pytest.mark.parametrize("damage",["delete","same-length-corrupt"])
def test_warm_research_raw_cas_loss_refuses_without_journal_or_cache_reset(tmp_path,monkeypatch,damage):
    """The retained CAS reference, not its warmed hydration, remains admission evidence."""
    import hashlib
    from laplace.core import bodies
    from laplace.manuscript import proposal_navigation
    from laplace.representation import writing_bodies
    from laplace.writing.records import _index

    md,home,turn,version,_,_=_native_research_candidate(tmp_path,monkeypatch)
    journal=tmp_path/"contract/talk.jsonl"
    warm=writing_records.fold_records(tmp_path)
    current=warm["turns"][turn]
    proposal=proposals.saved_proposals(current)[version]
    sealed=current["proposal_bases"][version]
    read=next(r for r in sealed["tool_reads"].values() if r["operation"]=="research")
    rows=[json.loads(line) for line in journal.read_text().splitlines()]
    retained=next(r for r in rows if r.get("id")==read["id"])
    reference=json.loads(json.dumps(retained["research_raw"]))
    assert bodies.is_reference(reference)
    assert read["research_raw"]==reference, "warm fold must preserve physical custody identity"
    data=writing_bodies.read_bytes(reference,tmp_path)
    assert reference["content_handle"]=="sha256:"+hashlib.sha256(data).hexdigest()
    blobs=[p for p in (tmp_path/"contract/writing_bodies").rglob("*")
           if p.is_file() and p.read_bytes()==data]
    assert len(blobs)==1
    blob=blobs[0]
    assert proposal_currentness._proposal_validation_basis(
        tmp_path,current,version,proposal,records=warm)["currentness"]=="CURRENT"

    # Everything below is read-only except this ONE physical blob mutation.
    # No native execute/bank call, cache clear, journal rewrite or fixture setup follows warming.
    journal_bytes=journal.read_bytes()
    stat=journal.stat()
    journal_stat=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
    generation=_index.index(tmp_path,"contract/talk.jsonl")._generation
    cache_generation=warm["generation"]
    assert generation is cache_generation
    seal=json.dumps(sealed,sort_keys=True)
    source=(md/"main.tex").read_bytes()
    feedback=sorted((p.relative_to(md).as_posix(),hashlib.sha256(p.read_bytes()).hexdigest())
                    for p in (md/"feedback").rglob("*") if p.is_file())
    if damage=="delete":
        blob.unlink()
    else:
        corrupt=bytes([data[0]^1])+data[1:]
        assert len(corrupt)==len(data) and hashlib.sha256(corrupt).digest()!=hashlib.sha256(data).digest()
        blob.write_bytes(corrupt)

    def unchanged_journal_and_cache():
        now=journal.stat()
        assert journal.read_bytes()==journal_bytes
        assert (now.st_dev,now.st_ino,now.st_size,now.st_mtime_ns,now.st_ctime_ns)==journal_stat
        assert _index.index(tmp_path,"contract/talk.jsonl")._generation is generation
        assert writing_records.fold_records(tmp_path) is warm
        assert warm["generation"] is cache_generation
        assert json.dumps(sealed,sort_keys=True)==seal

    unchanged_journal_and_cache()
    warm_result=proposal_currentness._proposal_validation_basis(
        tmp_path,current,version,proposal,records=warm)
    unchanged_journal_and_cache()
    from laplace.writing import turn_reads
    capture=turn_reads.capture_turn_read_baselines(tmp_path,"fixture",turn,"research_record")
    unchanged_journal_and_cache()
    try:
        cold=proposal_navigation.selected_records(tmp_path,"fixture",turn,version)
        cold_turn=cold["turns"][turn]
        cold_result=proposal_currentness._proposal_validation_basis(tmp_path,cold_turn,version,
            proposals.saved_proposals(cold_turn)[version],records=cold)
    except ValueError as error:
        cold_result={"currentness":"UNKNOWN","reason":str(error)}
    unchanged_journal_and_cache()
    refused=None
    try:
        applied=source_application.apply_proposal(tmp_path,{"turn_id":turn,"proposal_version":version})
    except ValueError as error:
        refused=str(error)
        applied=None
    observation={"damage":damage,"retained_reference":reference,
        "raw_bytes":len(data),"same_length_corrupt":damage=="same-length-corrupt",
        "journal_and_cache_unchanged_before_apply":True,
        "warm_currentness":warm_result["currentness"],"cold_currentness":cold_result["currentness"],
        "apply_refused":refused,"source_unchanged":(md/"main.tex").read_bytes()==source,
        "application_receipts":(applied or {}).get("receipts")}
    print("WARM_RAW_CUSTODY_OBSERVATION "+json.dumps(observation,sort_keys=True))
    assert warm_result["currentness"]!="CURRENT",observation
    assert cold_result["currentness"]!="CURRENT",observation
    assert capture["conflicts"]>0 and not capture["baselines"]
    assert refused and applied is None,observation
    assert (md/"main.tex").read_bytes()==source
    assert sorted((p.relative_to(md).as_posix(),hashlib.sha256(p.read_bytes()).hexdigest())
                  for p in (md/"feedback").rglob("*") if p.is_file())==feedback
    unchanged_journal_and_cache()


def test_inline_retained_research_raw_remains_valid_without_a_cas_requirement(tmp_path,monkeypatch):
    from laplace.core import bodies
    from laplace.representation import writing_bodies
    actual_put=writing_bodies._put
    def unavailable_research_store(root):
        put=actual_put(root)
        def retain(raw):
            value=json.loads(raw)
            if isinstance(value,dict) and "consumption_basis" in value and "producers" in value:
                raise OSError("Disposable fixture: Research raw retention unavailable")
            return put(raw)
        return retain
    monkeypatch.setattr(writing_bodies,"_put",unavailable_research_store)
    md,_,turn,version,_,_=_native_research_candidate(tmp_path,monkeypatch)
    current=writing_records.fold_records(tmp_path)["turns"][turn]
    read=next(r for r in current["proposal_bases"][version]["tool_reads"].values()
              if r["operation"]=="research")
    retained=next(json.loads(line) for line in (tmp_path/"contract/talk.jsonl").read_text().splitlines()
                  if json.loads(line).get("id")==read["id"])
    assert not bodies.is_reference(retained["research_raw"])
    assert retained["custody_degradation"]["status"]=="INLINE_RETAINED"
    assert retained["custody_degradation"]["failed_attempts"]>0
    assert read["research_raw"]==retained["research_raw"]
    assert read["consumption"]["status"]=="AVAILABLE"
    applied=source_application.apply_proposal(tmp_path,{"turn_id":turn,"proposal_version":version})
    assert applied["complete"] and applied["receipts"]
    assert "An exactly guarded premise." in (md/"main.tex").read_text()
