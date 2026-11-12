"""Both provider adapters return precise bounded recovery, never a success marker."""
import io,json
from pathlib import Path
import pytest
from laplace.native import tools as writing_tools, declarations as writing_declarations
from laplace.writing import provider as writing_provider
from laplace.writing import turn_reads
from laplace.writing import records as writing_records
from laplace.representation import writing_bodies
from laplace.writing import session_reads
from laplace.manuscript import proposal_currentness
from test_literature_joined_workflow import project,seed_turn,execute


def test_known_operation_failure_returns_exact_local_import_shape(tmp_path):
    result=writing_tools.failure_response(tmp_path,'p','work','literature_import',{'title':'misplaced'},ValueError('unknown field title'))
    assert result['ok'] is False
    # The example is generated, and `literature_import` requires NOTHING in its schema:
    # its obligation is "supply doi OR metadata plus provenance", which used to be the
    # third clause of a precondition and is now a typed rule with the line that enforces
    # it. So the repair block states the branch and the example takes one.
    rule=next(r for r in result['contract']['rules'] if r['rule']=='one-of')
    assert rule['fields'][0]=='doi' and 'provenance' in rule['fields']
    # the enforcing line is stated once per operation and only per rule where it differs, and
    # it carries the commit it is a coordinate in: a typed door was typed against the campaign
    # base and 42 of the 76 of them hold other code here (tools/door_citations.py), so the
    # refusal a caller reads cannot send them to a line in the tree they are holding.
    declared=next(r for r in writing_declarations.DECLARATIONS['literature_import'].rules if r.kind=='one-of')
    assert result['contract']['rules_enforced_at']==writing_declarations.cited(declared.door)
    assert result['contract']['rules_enforced_at'].endswith('@706a8204')
    assert result['contract']['line_numbers']==writing_declarations.COORDINATE_LAW
    assert 'enforced_at' not in rule
    assert set(result['contract']['example'])<=set(rule['fields'])
    assert result['contract']['example']
    assert result['help']=={'operation':'help','payload':{'operation':'literature_import'}}
    assert len(json.dumps(result))<5000


def test_a_supported_literal_operation_returns_only_the_matching_variant(tmp_path):
    """RD-RECOVERY-VARIANT: logical_plan_change takes a LITERAL operation string; recovery names exactly that
    variant, its input and example, and the moved sections are read for the same variant."""
    result=writing_tools.failure_response(tmp_path,'p','work','logical_plan_change',{'operation':'add_object'},ValueError('meaning is required'))
    contract=result['contract']
    assert contract['selected_variant']=='add_object' and 'variants' not in contract
    assert contract['input']['properties']['operation']['const']=='add_object'
    assert contract['example']['operation']=='add_object'
    assert 'oneOf' not in contract['input']
    assert contract['sections']['read']['payload']=={'operation':'logical_plan_change','section':'<name>','variant':'add_object'}
    assert result['help']=={'operation':'help','payload':{'operation':'logical_plan_change'}}
    wire=json.dumps(result,ensure_ascii=False)
    assert len(wire)<5000 and len(wire.encode('utf-8'))<5000


def test_a_malformed_nested_discriminator_is_not_normalised_into_an_action(tmp_path,monkeypatch):
    """A nested {kind: ...} is not this owner's shape: recovery offers the variant chooser and its declared
    read (never a silently selected variant), and the real door refuses the attempt before owner work."""
    attempt={'operation':{'kind':'add_object'},'node':'n','kind':'goal','meaning':'m','expected':['token']}
    result=writing_tools.failure_response(tmp_path,'p','work','logical_plan_change',dict(attempt),ValueError('operation requires a string'))
    contract=result['contract']
    assert 'selected_variant' not in contract and 'input' not in contract
    assert 'add_object' in contract['variants'] and contract['read_one_variant']
    from laplace.research import concepts as concepts_surface
    monkeypatch.setattr(concepts_surface,'handle',lambda *a,**k:pytest.fail('owner reached'))
    sent=json.loads(json.dumps(attempt))
    with pytest.raises(writing_declarations.PayloadAdmissionError) as refused:
        writing_tools.execute(tmp_path,'p','work','logical_plan_change',sent)
    assert refused.value.response()['refused']['kind']=='shape' and sent==attempt     # not normalised in place


def test_stale_read_recovery_preserves_exact_old_scope_without_rebasing(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    turn=seed_turn(tmp_path,source,{'files':['chapters/chapter-01.tex']},'WT-read-repair')
    execute(tmp_path,'literature_scope',{},turn)
    before=(tmp_path/'contract/talk.jsonl').read_bytes()
    result=writing_tools.failure_response(tmp_path,'joined','work','apply_revision',{'edits':[]},ValueError('Consulted project evidence changed (literature_scope). Request a fresh revision; nothing was applied.'),turn)
    assert {'operation':'literature_scope','payload':{}} in result['next_reads']
    assert (tmp_path/'contract/talk.jsonl').read_bytes()==before


def test_structure_conflict_prioritises_actual_unconsumed_correction_reads(tmp_path,monkeypatch):
    writing_records.bank(tmp_path,{'record':'writing-session','id':'WS-context-cause',
        'project':'p','provider':'codex','model':'fixture','effort':'low'})
    writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-context-cause',
        'session_id':'WS-context-cause','project':'p','mode':'work'})
    required=[{'operation':'author_history','payload':{'id':'AC-current','project':'p'}},
              {'operation':'structure','payload':{'project':'p'}}]
    monkeypatch.setattr(turn_reads,'failure_recovery_reads',lambda *a,**k:{
        'reads':required,'context_reasons':['correction-unconsumed:AC-current',
        'structure-plan-conceptric-or-evidence-changed']})

    result=writing_tools.failure_response(tmp_path,'p','work','structure_change',{
        'operation':'bind_results','node':'claim:x'},
        ValueError('concept revision conflict; inspect the focused concept first'),'WT-context-cause')

    assert result['recovery_cause']['kind']=='unconsumed-author-correction'
    assert result['recovery_cause']['correction_ids']==['AC-current']
    assert result['next_reads'][0]=={'operation':'author_history','payload':{'id':'AC-current'}}
    assert not any(row['operation']=='concept' for row in result['next_reads'])
    # `retry_instruction` is DELETED (identity_doors, report §2): it was a SENTENCE built in
    # this formatter, so it reached two of the four caller paths.  What replaced it is the
    # resolver itself -- the ordered reads as DATA -- which this test now asserts instead of
    # the prose that used to repeat them.
    assert 'retry_instruction' not in result
    assert result['recovery_cause']['retry']['reads'] == [
        {'operation':'author_history','payload':{'id':'AC-current'}},
        {'operation':'structure','payload':{}}]
    assert result['recovery_cause']['required_reads'] == result['recovery_cause']['retry']['reads']
    assert 'identities' in result['recovery_cause']['retry']['then']


def _mcp(root,monkeypatch,turn,payload):
    incoming='\n'.join(json.dumps(row) for row in [
        {'jsonrpc':'2.0','id':1,'method':'initialize'},
        {'jsonrpc':'2.0','id':2,'method':'tools/call','params':{'name':'laplace_project','arguments':{'operation':'literature_import','payload':payload}}}])+'\n'
    output=io.StringIO();monkeypatch.setattr('sys.stdin',io.StringIO(incoming));monkeypatch.setattr('sys.stdout',output)
    writing_tools.main(['--root',str(root),'--project','p','--mode','work','--turn-id',turn])
    failed=[json.loads(line) for line in output.getvalue().splitlines()][-1]['result']
    return failed,failed['content'][0]['text']


def _failures(root):
    path=root/'contract/talk.jsonl'
    return [json.loads(line) for line in path.read_text().splitlines()
            if json.loads(line).get('record')=='writing-tool-failure'] if path.is_file() else []


def _admit(root,project,turn,session,**fields):
    """An explicit synthetic admitted session and its one bound project turn, through the owner."""
    writing_records.bank(root,{'record':'writing-session','id':session,'project':project,'provider':'codex','model':'fixture','effort':'low'})
    writing_records.bank(root,{'record':'writing-turn','id':turn,'session_id':session,'project':project,'mode':'work',**fields})


def _shape_refusal(recovery,operation):
    assert recovery['ok'] is False and recovery['operation']==operation
    assert recovery['refused']['kind']=='shape' and recovery['refused']['homes']==[]
    assert recovery['help']==recovery['refused']['needed']['help']=={'operation':'help','payload':{'operation':operation}}
    assert 'contract' not in recovery            # pure shape admission: the declared Help read carries the schema


def test_mcp_returns_json_recovery_and_banks_only_one_failure(tmp_path,monkeypatch):
    """RD-RECOVERY-ADAPTERS (MCP): an admitted unique turn banks ONE canonical failure row with the literal
    attempt and an exact lazy read; the reply is a bounded shape refusal with the declared Help read."""
    _admit(tmp_path,'p','WT-mcp','WS-mcp')
    attempt={'title':'标题 "wrong level" \\ \u0007'}
    failed,text=_mcp(tmp_path,monkeypatch,'WT-mcp',attempt)
    recovery=json.loads(text)
    assert failed['isError'] is True
    _shape_refusal(recovery,'literature_import')
    rows=_failures(tmp_path)
    assert len(rows)==1 and rows[0]['id']==recovery['failure_receipt']['row_id']
    assert (rows[0]['turn_id'],rows[0]['project'],rows[0]['operation'])==('WT-mcp','p','literature_import')
    assert writing_bodies.resolve_fields(rows[0],tmp_path)['payload']==attempt          # the literal attempt
    assert recovery['failure_read']=={'operation':'author_history','payload':{'view':'record','id':'activity:journal:'+rows[0]['id']}}
    assert len(text)<5000 and len(text.encode('utf-8'))<5000 and len(json.dumps(recovery,ensure_ascii=False).encode())<5000


@pytest.mark.parametrize('case',['missing','wrong-project','duplicate'])
def test_mcp_never_invents_a_failure_row_for_an_unadmitted_turn(tmp_path,monkeypatch,case):
    if case=='wrong-project':_admit(tmp_path,'other','WT-mcp','WS-mcp')
    if case=='duplicate':
        _admit(tmp_path,'p','WT-mcp','WS-mcp')
        writing_records.bank(tmp_path,{'record':'writing-turn','id':'WT-mcp','session_id':'WS-mcp','project':'p','mode':'work'})
    failed,text=_mcp(tmp_path,monkeypatch,'WT-mcp',{'title':'wrong level'})
    recovery=json.loads(text)
    _shape_refusal(recovery,'literature_import')
    assert recovery['failure_receipt']['row_id'] is None and 'unavailable' in recovery['failure_receipt']['note'].lower()
    assert _failures(tmp_path)==[]


def test_propose_revision_cannot_drop_top_level_lineage_before_preflight(tmp_path,monkeypatch):
    """RD-RECOVERY-LINEAGE: undeclared top-level lineage is a structured shape refusal naming `develops`,
    before classification, preflight or any proposal/source write; it is never dropped or moved."""
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    turn=seed_turn(tmp_path,source,{'files':['chapters/chapter-01.tex']},'WT-lineage')
    from laplace.manuscript import proposal_preflight
    from laplace.native import verbs as writing_verbs
    monkeypatch.setattr(proposal_preflight,'preflight',lambda *a,**k:pytest.fail('preflight reached'))
    monkeypatch.setattr(writing_verbs,'classify',lambda *a,**k:pytest.fail('classification reached'))
    journal,chapter=(tmp_path/'contract/talk.jsonl').read_bytes(),(manuscript/'chapters/chapter-01.tex').read_bytes()
    with pytest.raises(writing_declarations.PayloadAdmissionError) as refused:
        execute(tmp_path,'propose_revision',{'edits':[],'develops':[{'id':'claim:lost'}]},turn)
    body=refused.value.response()
    assert body['refused']['kind']=='shape' and "'develops' was unexpected" in body['refused']['said']
    assert body['help']=={'operation':'help','payload':{'operation':'propose_revision'}}
    assert (tmp_path/'contract/talk.jsonl').read_bytes()==journal and (manuscript/'chapters/chapter-01.tex').read_bytes()==chapter


def test_valid_per_edit_lineage_is_retained_and_stale_or_foreign_lineage_refuses(tmp_path):
    """Lineage belongs inside the edit with its exact concept revision; a placed, current concept is
    retained by the sealed proposal, while a stale revision or a concept not placed at this source refuses
    without publishing a proposal."""
    from test_project_structure import _fixture
    from laplace.research import concepts as concepts_surface
    _fixture(tmp_path)
    _admit(tmp_path,'book','WT-lineage','WS-lineage',selection={'files':['N1.tex']})
    current=concepts_surface.state('book',node='res:one',root=tmp_path)
    edit={'file':'N1.tex','line_start':2,'line_end':2,'before':'Opening prose.','after':'A source-backed opening.',
          'reason':'Develop the result.','develops':[{'id':'res:one','content_revision':current['content_revision']}]}
    def proposals():
        path=tmp_path/'contract/talk.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines() if json.loads(line).get('record')=='writing-proposal']
    for bad,said in (([{'id':'res:one','content_revision':'stale'}],'develops concept changed: res:one'),
                     ([{'id':'res:missing','content_revision':current['content_revision']}],'res:missing')):
        with pytest.raises(ValueError,match=said):
            writing_tools.execute(tmp_path,'book','work','propose_revision',{'edits':[{**edit,'develops':bad}]},turn_id='WT-lineage')
    assert proposals()==[]
    sealed=writing_tools.execute(tmp_path,'book','work','propose_revision',{'edits':[edit]},turn_id='WT-lineage')
    assert sealed['status']=='PROPOSED' and len(proposals())==1
    turn=session_reads._records(tmp_path)['turns']['WT-lineage']
    assert proposal_currentness.proposal_view(turn)['proposal']['edits'][0]['develops']==edit['develops']


@pytest.mark.parametrize('admitted',[True,False])
def test_codex_adapter_returns_the_same_bounded_recovery_without_double_banking(tmp_path,monkeypatch,admitted):
    """RD-RECOVERY-ADAPTERS (Codex): the same canonical shape refusal as the shared tool_failure and the MCP
    door; ONE row only for an explicitly admitted turn, none invented otherwise."""
    project(tmp_path,monkeypatch);handbacks=[]
    if admitted:_admit(tmp_path,'joined','WT-codex-recovery','WS-codex-recovery')
    class Connection:
        def __init__(self,cwd,event,tool_handler=None):self.event=event;self.tool_handler=tool_handler
        def request(self,method,params):
            if method=='thread/start':return {'thread':{'id':'writer-thread'}}
            if method=='turn/start':
                try:self.tool_handler({'tool':'laplace_project','threadId':'writer-thread','arguments':{'operation':'literature_import','payload':{'title':'wrong'}}})
                except ValueError as error:handbacks.append(json.loads(str(error)))
                self.event({'method':'turn/completed','params':{'threadId':'writer-thread','turn':{'id':'writer-turn','status':'completed'}}})
                return {'turn':{'id':'writer-turn'}}
            raise AssertionError(method)
        def close(self):pass
    monkeypatch.setattr(writing_provider,'CodexConnection',Connection)
    result=writing_provider.WritingTurn(tmp_path,'codex','','low',None,lambda event:None,project='joined',logical_turn_id='WT-codex-recovery').run('Exercise malformed input.')
    assert result['status']=='completed'
    _shape_refusal(handbacks[0],'literature_import')
    rows=[row for row in _failures(tmp_path) if row.get('turn_id')=='WT-codex-recovery']
    if admitted:
        assert len(rows)==1 and handbacks[0]['failure_receipt']['row_id']==rows[0]['id']
        assert writing_bodies.resolve_fields(rows[0],tmp_path)['payload']=={'title':'wrong'}
    else:
        assert rows==[] and handbacks[0]['failure_receipt']['row_id'] is None
    shared=writing_tools.tool_failure(tmp_path,'joined','work','literature_import',{'title':'wrong'},
        writing_declarations.PayloadAdmissionError('literature_import',handbacks[0]['error']),None)
    assert {key:shared[key] for key in ('ok','operation','refused','help')}=={key:handbacks[0][key] for key in ('ok','operation','refused','help')}


def test_malformed_help_returns_the_requested_contract_in_one_bounded_error():
    result=writing_tools.failure_response(Path('.'),'example','work','help',{'topic':'literature_import'},ValueError('help accepts only operation'))
    assert result['ok'] is False and result['contract']['operation']=='literature_import'
    assert result['help']=={'operation':'help','payload':{'operation':'literature_import'}}


def test_missing_claim_recovery_discovers_existing_objects_instead_of_refocusing_missing_id():
    result=writing_tools.failure_response(Path('.'),'example','work','literature_bind',{'claim_id':'missing','key':'local:known'},ValueError('claim_id must identify an existing logical-plan object.'))
    assert {'operation':'logical_plan','payload':{}} in result['next_reads']
    assert not any(row['operation']=='concept' for row in result['next_reads'])
