"""Integration coverage for exact research/visual owner mutation receipts."""
from __future__ import annotations

import json
import hashlib
import time
from pathlib import Path

from laplace.research import concepts as concepts_surface, corpus_ingest
from laplace.manuscript import project_structure
from laplace.native import tools as writing_tools
from laplace.writing import turn_reads
from laplace.writing import records as writing_records
from laplace.writing import mutation_attribution


def _project(root:Path)->Path:
    (root/'contract').mkdir()
    manuscript=root/'book'/'manuscript';manuscript.mkdir(parents=True)
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{
        'name':'book','kind':'conceptric','project_dir':'book',
        'tex_root':'book/manuscript','manifest':{'document':{'root':'book/manuscript/main.tex'}}}]}))
    (manuscript/'main.tex').write_text(
        '\\documentclass{article}\n\\begin{document}\n\\input{section}\n\\end{document}\n')
    (manuscript/'section.tex').write_text('Measured section.\n')
    (manuscript/'projection_plan.json').write_text(json.dumps({'meta':{'project':'book'},
        'sections':[{'id':'S1','title':'Measured section','file':'section.tex',
                     'beats':['res:measured'],'nodes_in_order':['res:measured'],'refs':[]}],
        'appendices':[]}))
    assert not corpus_ingest.rewire_add(root,'book',{'kind':'add-node','node':'res:measured',
        'node_kind':'result','essence':'A measured result','by':'fixture'}).get('error')
    (root/'book'/'data.csv').write_text('x,y\n1,2\n2,4\n')
    (root/'book'/'producer.py').write_text(
        "import argparse,json\nfrom pathlib import Path\n"
        "p=argparse.ArgumentParser();p.add_argument('--mode');p.add_argument('--args-json');p.add_argument('--result');a=p.parse_args()\n"
        "Path(a.result).write_text(json.dumps({'slope':2,'unit':'m/s'}))\n")
    return manuscript


def _before(root:Path,operation:str="")->dict:
    return {'mutation_project':'book',
            'mutation_operation':operation,
            'mutation_files':mutation_attribution._mutation_file_snapshot(root,'book',operation),
            'mutation_rewire_records':corpus_ingest.rewire_list(root,'book')}


def _assert_exact(root:Path,before:dict,operation:str,result:dict)->None:
    if operation in {'research_producer','experiment_run'}:
        from laplace.work import author_history_metrics
        action=result['action_receipt']
        row,_meta=author_history_metrics.exact_record('book',action['id'],root)
        assert (row['record'],row['project'],row['turn_id'],row['operation'])==(
            'writing-tool-action','book','WT-chain',operation)
        assert row['outcome']['mutation_attribution']==action['mutation_attribution']
        assert action['mutation_attribution']['exact'] is True
        assert action['views']==result['changed']['views']
        evidence=action['owner_evidence']
        assert evidence['schema_version']=='laplace.owner-evidence/1'
        assert evidence['files'] and evidence['files_omitted']==0
        for file in evidence['files']:
            assert file['before_sha256']==before['mutation_files'].get(file['path'])
            observed='sha256:'+hashlib.sha256((root/file['path']).read_bytes()).hexdigest()
            assert file['after_sha256']==file['observed_after_sha256']==observed
        return
    receipt=result.get('owned_changes') or writing_tools._implicit_owned_changes(operation,result)
    assert mutation_attribution._owned_changes_exact(root,before,receipt)==(
        True,'exact owner receipts match captured before and observed after identities')


def test_source_to_result_binding_visual_and_placement_have_exact_owner_receipts(tmp_path):
    manuscript=_project(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-session','id':'WS-chain',
        'project':'book','provider':'codex','model':'','effort':'low'})
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-chain',
        'session_id':'WS-chain','project':'book','mode':'work',
        'selection':{'files':['section.tex']}})
    def write(operation,payload):
        before=_before(tmp_path,operation)
        result=writing_tools.execute(tmp_path,'book','work',operation,payload,turn_id='WT-chain')
        _assert_exact(tmp_path,before,operation,result)
        assert result['action_receipt']['mutation_attribution']['exact'] is True, result['action_receipt']['mutation_attribution']
        return result
    source=writing_tools.execute(tmp_path,'book','work','source',{'files':['section.tex']},
                                 turn_id='WT-chain')
    assert source['sources'][0]['expected_source_digest']

    producer=write('research_producer',{
        'id':'measurement','scope':'project','executable':'producer.py','modes':['smoke'],
        'allowed_args':{},'dependencies':['data.csv']})

    launched=write('experiment_run',{
        'producer_id':'measurement','mode':'smoke','args':{}})
    assert launched['action_receipt']['views']==['research-run-request']
    assert launched['next_read']=={'operation':'run_status','payload':{'id':launched['run']['id']}}
    assert producer['next_read']=={'operation':'research','payload':{}}
    for _ in range(100):
        run=writing_tools.execute(tmp_path,'book','work','run_status',{'id':launched['run']['id']},
                                  turn_id='WT-chain')
        if run['state']!='RUNNING':break
        time.sleep(.025)
    assert run['state']=='COMPLETE' and run['result_provenance']['sha256']

    recorded=write('research_record',{
        'kind':'result','id':'result:measurement','run_id':run['id'],
        'result':run['result_path'],'question':'What slope is measured?',
        'summary':'The measured slope is 2 m/s.'})

    structure=project_structure.state('book',tmp_path)
    concept_revision=concepts_surface.state('book',node='res:measured',root=tmp_path)['revision']
    bound=write('structure_change',{
        'operation':'bind_results','node':'res:measured',
        'results':[{'id':'result:measurement','revision':recorded['record']['revision']}],
        'expected_revision':structure['revision'],'expected_concept_revision':concept_revision})

    spec={'id':'measurement-plot','title':'Measured slope','question':'Does the value rise?',
          'kind':'plot','caption':'Measured output across the declared inputs.',
          'source_data':'data.csv','x':'x','series':['y'],'result_ids':['result:measurement']}
    created=write('visual_create',{'spec':spec})
    rendered=write('visual_render',{'id':'measurement-plot'})
    placed=write('visual_place',{
        'id':'measurement-plot','file':'section.tex','after_line':1})
    assert '\\label{fig:measurement-plot}' in (manuscript/'section.tex').read_text()


def test_unrelated_canonical_change_is_not_blessed_by_visual_receipt(tmp_path):
    _project(tmp_path)
    before=_before(tmp_path)
    assert before['mutation_files']['corpus_friction/work_orders.jsonl'] is None
    (tmp_path/'book'/'manuscript'/'document_style.json').write_text('{"voice":"external"}\n')
    created=writing_tools.execute(tmp_path,'book','work','visual_create',{'spec':{
        'id':'later','title':'Later','question':'What changed?','kind':'plot',
        'caption':'Later plot.','source_data':'data.csv','x':'x','series':['y']}})
    exact,reason=mutation_attribution._owned_changes_exact(tmp_path,before,created['owned_changes'])
    assert exact is False and 'unowned canonical files changed' in reason


def test_cancel_receipt_covers_only_request_and_requires_status_read(tmp_path):
    manuscript=_project(tmp_path)
    runs=manuscript/'research_runs';runs.mkdir()
    (runs/'run-live.json').write_text(json.dumps({'id':'run-live','state':'RUNNING'}))
    before=_before(tmp_path)
    cancelled=writing_tools.execute(tmp_path,'book','work','run_cancel',{'id':'run-live'})
    _assert_exact(tmp_path,before,'run_cancel',cancelled)
    assert cancelled['effects']==['research-run-request']
    assert 'read run_status' in cancelled['note']


def _run_fixture(root):
    manuscript=_project(root)
    producer=root/'book'/'producer.py'
    producer.write_text(producer.read_text().replace('import argparse,json',
        'import argparse,json,time\ntime.sleep(.25)'))
    writing_tools.execute(root,'book','work','research_producer',{
        'id':'measurement','scope':'project','executable':'producer.py',
        'modes':['smoke'],'allowed_args':{},'dependencies':['data.csv']})
    return manuscript,{'producer_id':'measurement','mode':'smoke','args':{}}


def _wait_runs(manuscript,ids):
    from laplace.research import research_runs
    for ident in ids:
        for _ in range(160):
            row=research_runs._run_status(manuscript,ident)
            if row['state']!='RUNNING':break
            time.sleep(.025)
        assert row['state']=='COMPLETE',row


def test_first_and_second_actual_run_capture_selected_index_without_run_body_scan(tmp_path,monkeypatch):
    manuscript,payload=_run_fixture(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-runs',
        'session_id':'WS-runs','project':'book','mode':'work'})
    runs=manuscript/'research_runs';runs.mkdir()
    unrelated=runs/'run-unrelated.json';unrelated.write_text('{"unrelated":"body"}')
    read_bytes=Path.read_bytes;read_text=Path.read_text
    def check_read(path,*args,**kwargs):
        assert path!=unrelated,'snapshot hydrated an unrelated run body'
        return read_bytes(path,*args,**kwargs)
    def check_text(path,*args,**kwargs):
        assert path!=unrelated,'snapshot hydrated an unrelated run body'
        return read_text(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_bytes',check_read)
    monkeypatch.setattr(Path,'read_text',check_text)
    index_key='book/manuscript/research_runs/index.json'
    snapshot=mutation_attribution._mutation_file_snapshot(tmp_path,'book','experiment_run')
    assert index_key in snapshot and snapshot[index_key] is None
    ids=[]
    for _ in range(2):
        result=writing_tools.execute(tmp_path,'book','work','experiment_run',payload,turn_id='WT-runs')
        assert result['action_receipt']['mutation_attribution']['exact'] is True
        ids.append(result['run']['id'])
        _wait_runs(manuscript,[ids[-1]])
    assert json.loads((runs/'index.json').read_text())['runs']==ids


def test_run_index_intervening_mutation_is_proven_mismatch_not_missing_capture(tmp_path):
    from laplace.research import research_runs
    manuscript,payload=_run_fixture(tmp_path)
    before=_before(tmp_path,'experiment_run')
    runs=manuscript/'research_runs';runs.mkdir()
    (runs/'index.json').write_text('{"runs":["run-external"]}')
    status,result=research_runs.launch('book',payload,tmp_path)
    assert status==202
    exact,reason=mutation_attribution._owned_changes_exact(tmp_path,before,result['owned_changes'])
    assert not exact and 'before its mutation lock' in reason
    uncaptured={**before,'mutation_files':{}}
    exact,reason=mutation_attribution._owned_changes_exact(tmp_path,uncaptured,result['owned_changes'])
    assert not exact and 'preimage was not captured' in reason
    _wait_runs(manuscript,[result['run']['id']])


def test_public_launch_retains_success_but_does_not_refresh_after_index_drift(tmp_path,monkeypatch):
    manuscript,payload=_run_fixture(tmp_path)
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-drift',
        'session_id':'WS-drift','project':'book','mode':'work'})
    capture=turn_reads.capture_turn_read_baselines
    def intervening(*args,**kwargs):
        before=capture(*args,**kwargs)
        runs=manuscript/'research_runs';runs.mkdir()
        (runs/'index.json').write_text('{"runs":["run-external"]}')
        return before
    monkeypatch.setattr(turn_reads,'capture_turn_read_baselines',intervening)
    result=writing_tools.execute(tmp_path,'book','work','experiment_run',payload,turn_id='WT-drift')
    assert result['ok'] is True and result['run']['state']=='RUNNING'
    action=result['action_receipt']
    assert action['mutation_attribution']['exact'] is False
    assert 'before its mutation lock' in action['mutation_attribution']['reason']
    assert action['refreshed_read_baselines']==0 and not action['context_refreshed']
    assert json.loads((manuscript/'research_runs'/'index.json').read_text())['runs']==[
        'run-external',result['run']['id']]
    _wait_runs(manuscript,[result['run']['id']])


def test_concurrent_actual_launches_retain_both_ids_in_owner_index(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from laplace.research import research_runs
    manuscript,payload=_run_fixture(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda _:research_runs.launch('book',payload,tmp_path),range(2)))
    assert [status for status,_ in results]==[202,202]
    ids={result['run']['id'] for _,result in results}
    assert len(ids)==2
    assert set(json.loads((manuscript/'research_runs'/'index.json').read_text())['runs'])==ids
    _wait_runs(manuscript,ids)
