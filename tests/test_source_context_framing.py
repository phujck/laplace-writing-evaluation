"""Source capability changes presentation, never roles or source admission."""
import inspect,json,hashlib,subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
from laplace.writing import operating as wo
from laplace.writing import records as writing_records
from laplace.writing import provider as writing_provider
from laplace.writing import turn_jobs
from laplace.writing import turn_admission
from laplace.pipeline import authoring


def seed(root,state):
    md=root/'writing_projects/p/manuscript';md.mkdir(parents=True)
    voice=root/'profiles/voice';voice.mkdir(parents=True)
    (voice/'gerard-technical-v1.md').write_text('# Neutral\n\n## Current runtime prompt\nUse precise language.\n')
    manifest={'writing':{'kind':'general'}}
    if state=='missing':manifest['document']={'root':'missing.tex'}
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'project','project_dir':'writing_projects/p','manifest':manifest}]}))
    (root/'writing-portability.json').write_text('{"schema":"laplace.writing-portability/1","source_aliases":{},"directory_aliases":{}}')
    (root/'profiles/writing_sources.json').write_text('{"repositories":{}}')
    blank=authoring._blank('p');blank.update(argument='Exact recorded context.',framing={'purpose':'Exact purpose.','audience':'Python programmer.','question':''})
    (md/'authoring.json').write_text(json.dumps(blank))
    if state=='manuscript':(md/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nExact manuscript.\n\\end{document}\n')
    if state=='ambiguous':
        for name in ['one.tex','two.tex']:(md/name).write_text('\\documentclass{article}\n\\begin{document}\nExact manuscript.\n\\end{document}\n')
    return md


def prepared(root,state,provider,mode,monkeypatch):
    seed(root,state);captured={};bank=writing_records.bank
    class StopBeforeTurn(Exception):pass
    def capture(target,row,**kwargs):
        if row.get('record')=='writing-turn':
            values=inspect.currentframe().f_back.f_locals
            captured.update(prompt=values['prompt'],context=values['context'],brief=values['operating_brief'],row=row)
            raise StopBeforeTurn()
        return bank(target,row,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(writing_records,'bank',capture)
        patch.setattr(writing_provider,'WritingTurn',lambda *args,**kwargs:pytest.fail('provider constructor'))
        patch.setattr(subprocess,'Popen',lambda *args,**kwargs:pytest.fail('process launch'))
        with pytest.raises(StopBeforeTurn):turn_admission._start_turn(root,{'project':'p','provider':provider,'model':'gpt-6.1-sol' if provider=='codex' else 'opus[1m]','effort':'high','mode':mode,'text':'Exact author request.'})
    assert not turn_jobs._JOBS
    captured['frame']=wo.frame(captured['brief'])
    return captured


@pytest.mark.parametrize('provider',['codex','claude'])
@pytest.mark.parametrize('mode',['work','discuss','review'])
@pytest.mark.parametrize('state',['general','manuscript','missing','ambiguous'])
def test_actual_prepared_blocks_follow_observed_source(tmp_path,monkeypatch,provider,mode,state):
    value=prepared(tmp_path,state,provider,mode,monkeypatch);prompt=value['prompt'];context=value['context']
    assert 'Exact author request.' in prompt and value['row']['text']=='Exact author request.'
    assert value['brief']['mode']==mode
    assert value['brief']['permissions']==wo.tool_contract()['role_permissions'][mode]
    assert context['prompt_framing']['kind']=={'general':'project','manuscript':'manuscript'}.get(state,'unresolved')
    if state=='manuscript':
        # Actual main457 owner-prepared task hashes, both providers; no copied
        # prompt implementation or fabricated transport observation.
        expected='4a34163f63176c05341a7afd1c7cfb51a9b151fcd61594a409e2d9a8771b5257' if mode=='review' else '71674095e8cb879d0947fdf6ffd5ac5e13549015159eaf7ac06bb18ff373db42'
        assert hashlib.sha256(prompt.encode()).hexdigest()==expected
        assert 'continuing one coherent manuscript argument' in prompt
        assert 'Whole-manuscript framing:' in prompt and 'Sustained argument:' in prompt
        assert 'neighbouring prose' in prompt
    else:
        assert 'Project purpose:' in prompt and 'Project context:' in prompt
        assert 'Whole-manuscript framing:' not in prompt and 'Sustained argument:' not in prompt
        assert 'neighbouring prose' not in prompt and 'continuing writer' not in prompt
        if mode=='review':assert 'Inspect the actual project artifacts and evidence' in prompt
        if state!='general':
            assert 'manuscript source is unresolved' in prompt
            assert context['document']['status']==state
            assert all(str(item) in prompt for item in context['document']['diagnostics'])


def test_general_to_manuscript_changes_part_tokens_reusing_document_observation(tmp_path,monkeypatch):
    md=seed(tmp_path,'general');source=authoring._source;calls=[]
    def observed(*args):
        frame=inspect.currentframe().f_back
        calls.append((frame.f_code.co_name,frame.f_back.f_code.co_name))
        return source(*args)
    monkeypatch.setattr(authoring,'_source',observed)
    initial=authoring.build_context('p',repo_root=tmp_path)
    assert ('_state_path','build_context') not in calls
    assert len(calls)==4  # Existing inspect/read/reference observations; framing adds none.
    before={row['key']:row['token'] for row in initial['parts']}
    (md/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nNow selected manuscript.\n\\end{document}\n')
    calls.clear();current=authoring.build_context('p',repo_root=tmp_path)
    assert ('_state_path','build_context') not in calls and current['document']['status']=='resolved'
    assert len(calls)==4
    after={row['key']:row['token'] for row in current['parts']}
    assert all(before[key]!=after[key] for key in ['preamble','framing','sustained_argument'])


def test_unproved_source_never_defaults_to_manuscript_or_free_project():
    assert authoring.prompt_framing(None)['kind']=='unresolved'
    for declared in [{'root':'expected.tex'},{'manuscript_dir':'expected'},{'edition':'expected'}]:
        project=SimpleNamespace(kind='project',manifest={'document':declared},external_root='')
        assert authoring.prompt_framing({'status':'missing','root':None,'diagnostics':['no TeX document root found']},project)['kind']=='unresolved'
