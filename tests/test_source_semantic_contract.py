"""One source identity and typed examples; isolated owners, no providers."""
from pathlib import Path
import json
import pytest
from laplace.manuscript import proposal_preflight as p
from laplace.native import declarations as d, verbs as v, tools as writing_tools
from laplace.projects import library as writing_projects
from laplace.writing import records as writing_records
from laplace.writing import session_reads
from laplace.pipeline import authoring


def test_source_before_is_literal_while_artifact_before_is_digest():
    for operation in ('propose_revision','apply_revision'):
        help=d.help_payload(operation,permitted=True)
        before=help['example']['edits'][0]['before']
        assert 'Exact consumed source text' in before
        assert 'digest' not in before and 'sha256' not in before
        assert help['input']['properties']['edits']['items']['properties']['before']['x-laplace-value-form']=='text' if operation=='propose_revision' else True
    help=d.help_payload('store_artifact',permitted=True)
    assert 'Exact prior artifact text' in help['example']['before']
    assert all(form=='text' for route in v.ROUTES if route.operation=='store_artifact' for name,home,form,optional in route.guards if name=='before')
    assert d.DECLARATIONS['store_artifact'].payload['oneOf'][1]['properties']['expected_revision']['x-laplace-value-form']=='digest'


def fixture(root):
    md=root/'papers'/'p'/'manuscript'/'tex';md.mkdir(parents=True)
    main=md/'Main.tex';main.write_text('\\documentclass{article}\n\\begin{document}\nOriginal prose.\n\\end{document}\n')
    code,value=writing_projects.import_source({'name':'alias','title':'Alias','root':main.relative_to(root).as_posix(),'editable':True},root)
    assert code==201,value
    context=authoring.build_context('alias',{'files':['Main.tex']},root)
    writing_records.bank(root,{'record':'writing-session','id':'S','project':'alias','provider':'codex','model':'not-invoked','effort':'low'})
    writing_records.bank(root,{'record':'writing-turn','id':'T','session_id':'S','project':'alias','text':'Change one sentence','mode':'work',
        'selection':{'files':['Main.tex']},'context_id':context['context_id'],'dependencies':context['dependencies'],'document':context['document'],'consumed':context['consumed']})
    return md,main


def test_help_then_source_alias_then_real_proposal_and_canonical_recovery(tmp_path):
    md,main=fixture(tmp_path)
    source=writing_tools.execute(tmp_path,'alias','work','source',{'files':['manuscript/tex/Main.tex']},turn_id='T')
    assert source['sources'][0]['file']==main.relative_to(tmp_path).as_posix()
    template=d.help_payload('propose_revision',permitted=True)['example']
    edit={**template['edits'][0],'file':'manuscript/tex/Main.tex','line_start':3,'line_end':3,'before':'Original prose.','after':'Revised prose.'}
    outcome=writing_tools.execute(tmp_path,'alias','work','propose_revision',{'edits':[edit]},turn_id='T')
    assert outcome['ok']
    turn=session_reads._records(tmp_path)['turns']['T']
    assert p.canonical_consumed_files(tmp_path,'alias',turn,[edit['file']])==[main.relative_to(tmp_path).as_posix()]
    recovery=writing_tools.failure_response(tmp_path,'alias','work','propose_revision',{'edits':[edit]},ValueError('fixture failure'),turn_id='T')
    assert recovery['next_reads'][0]=={'operation':'source','payload':{'files':[main.relative_to(tmp_path).as_posix()]}}
    assert main.read_text().splitlines()[2]=='Original prose.' # proposal never applies itself


@pytest.mark.parametrize('value',['../Main.tex','/absolute/Main.tex','papers/other/manuscript/tex/Main.tex','manuscript/tex/missing.tex'])
def test_alias_cannot_escape_selected_consumed_identity(tmp_path,value):
    md,main=fixture(tmp_path)
    allowed={main.resolve():[(3,3)]}
    assert p.consumed_source_identity(tmp_path,md.resolve(),value,allowed) is None


def test_missing_consumption_ambiguous_alias_and_symlink_do_not_gain_scope(tmp_path):
    md,main=fixture(tmp_path)
    assert p.consumed_source_identity(tmp_path,md.resolve(),'manuscript/tex/Main.tex',{}) is None
    left=md/'left'/'same.tex';left.parent.mkdir();left.write_text('one')
    right=md/'right'/'same.tex';right.parent.mkdir();right.write_text('two')
    assert p.consumed_source_identity(tmp_path,md.resolve(),'same.tex',{left:[(1,1)],right:[(1,1)]}) is None
    outside=tmp_path/'outside.tex';outside.write_text('outside');link=md/'link.tex';link.symlink_to(outside)
    assert p.consumed_source_identity(tmp_path,md.resolve(),'link.tex',{link:[(1,1)]}) is None


def test_alias_never_turns_stale_before_into_current_acceptance(tmp_path):
    md,main=fixture(tmp_path)
    turn={'tool_reads':{'r':{'operation':'source','source_scope':[{'file':main.relative_to(tmp_path).as_posix(),'line_start':3,'line_end':3}]}}}
    main.write_text(main.read_text().replace('Original prose.','Changed current prose.'))
    result=p.preflight(tmp_path,'alias',turn,{'edits':[{'file':'manuscript/tex/Main.tex','line_start':3,'line_end':3,'before':'Original prose.','after':'Unapproved change.'}]})
    assert not result['valid']
    assert 'exact full-line match' in result['errors'][0]
    assert 'Changed current prose.' in main.read_text()


def test_all_exposed_before_carriers_have_owned_meaning_and_no_shared_annotation_leak():
    from laplace.writing.schemas import SCHEMAS, FIELD_VALUE_SEMANTICS
    seen=set()
    def visit(operation,value,path=()):
        if not isinstance(value,dict):return
        for name,child in (value.get('properties') or {}).items():
            address=path+(name,)
            if name in ('before','after_before'):
                key=(operation,'.'.join(address));seen.add(key)
                assert key in FIELD_VALUE_SEMANTICS
                assert child['x-laplace-value-form']==FIELD_VALUE_SEMANTICS[key][0]
            visit(operation,child,address)
        if isinstance(value.get('items'),dict):visit(operation,value['items'],path+('[]',))
        for axis in ('oneOf','anyOf','allOf'):
            for child in value.get(axis) or []:visit(operation,child,path)
    for operation,value in SCHEMAS.items():visit(operation,value)
    assert seen=={key for key in FIELD_VALUE_SEMANTICS if key[1].split('.')[-1] in ('before','after_before')}
    assert SCHEMAS['conversation_history']['properties']['before']['x-laplace-value-form']=='cursor'
    assert 'digest' not in d.help_payload('propose_revision',permitted=True)['example']['edits'][0]['before']
    assert 'literal exact consumed source text' in str([rule.says for rule in d.DECLARATIONS['propose_revision'].rules])
    # An operation-local annotation mutation cannot change another schema's same word.
    source=SCHEMAS['propose_revision']['properties']['edits']['items']['properties']['before']
    artifact=SCHEMAS['store_artifact']['oneOf'][0]['properties']['before']
    assert source is not artifact
    prior=artifact['description'];source['test_owner_isolation']=True
    try:assert artifact['description']==prior and 'test_owner_isolation' not in artifact
    finally:source.pop('test_owner_isolation')


def test_real_artifact_digest_text_and_conversation_cursor_stay_distinct(tmp_path):
    fixture(tmp_path)
    created=writing_tools.execute(tmp_path,'alias','work','store_artifact',{'path':'notes/a.txt','before':None,'content':'First','reason':'fixture'})
    observed=writing_tools.execute(tmp_path,'alias','work','read_artifact',{'path':'notes/a.txt'})
    with pytest.raises(ValueError,match='changed'):
        writing_tools.execute(tmp_path,'alias','work','store_artifact',{'path':'notes/a.txt','before':observed['revision'],'content':'wrong','reason':'fixture'})
    updated=writing_tools.execute(tmp_path,'alias','work','store_artifact',{'path':'notes/a.txt','expected_revision':observed['revision'],'content':'Second','reason':'fixture'})
    assert updated
    assert d.DECLARATIONS['conversation_history'].payload['properties']['before']['x-laplace-value-form']=='cursor'
    assert any('older_cursor' in rule.says for rule in d.DECLARATIONS['conversation_history'].rules)
