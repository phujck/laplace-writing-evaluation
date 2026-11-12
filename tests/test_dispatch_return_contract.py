"""Provider-facing scope and executable /2 contracts after actual NO-RETURN trial."""
import json

import pytest
from jsonschema import Draft202012Validator

from laplace.work import project_work
from laplace.writing import operating as writing_operating
from laplace.native import tools as writing_tools
from laplace.web import authoring_http
from laplace.writing import records as writing_records
from laplace.writing import child_hosts
from laplace.writing import session_reads
from laplace.projects import artifacts
from laplace.writing import dispatch_parent
from test_dispatch_plan_contract import parent
from test_dispatch_parent import synthesis_case


def _artifact_rows(root):
    return sum(1 for row in writing_records.index(root).by_project.get('book',[]) if row.get('record')=='writing-artifact')


def test_reserved_child_return_refuses_before_any_write_and_the_same_live_child_corrects_it(parent):
    """The Artifact prewrite guard: invalid typed bytes and a foreign actor leave no file or receipt; the child corrects."""
    from laplace.writing import dispatch_returns
    task,_,_=synthesis_case(parent)
    _plan,declared,revision=dispatch_parent.plan(task,parent)
    judge=next(row for row in declared['packets'] if row['role']=='judge')
    target=artifacts.resolve_path(parent,'book',judge['return_path'])
    # the exact admission receipt fields the launch owner records beside the admitted plan hash
    project_work.transition('book',{'id':task['id'],'status':project_work._tasks('book',parent)[task['id']]['status']},parent,
        dispatch_receipt={'dispatch_return_reservations':{judge['packet']:target.relative_to(parent).as_posix()},
                          'dispatch_plan_sha256':revision.removeprefix('sha256:')})
    # the judge child is live: its session execution record is RUNNING for this exact admitted turn
    child_hosts._begin_child_execution(parent,'WS-child-1',{'project':'book','session_id':'WS-child-1','turn_id':'WT-child-1',
        'dispatch_id':task['id'],'parent_turn_id':'WT-parent','state':'RUNNING','host':child_hosts._process_identity()})
    valid=target.read_text();before=target.read_bytes()
    action=writing_tools.execute(parent,'book','review','session_settings',{},turn_id='WT-child-1')['return_contract']['publish_action']
    banked=_artifact_rows(parent)
    broken=json.dumps({'schema_version':'laplace.packet-judgement/2','packet':'not-a-worker'})
    with pytest.raises(ValueError,match='refused before publication') as refused:
        writing_tools.call(parent,'book','review',{**action,'payload':{**action['payload'],'content':broken}},turn_id='WT-child-1')
    assert 'Field: schema' in str(refused.value) and judge['return_path'] in str(refused.value)
    assert target.read_bytes()==before and _artifact_rows(parent)==banked
    with pytest.raises(ValueError,match='Field: actor'):
        dispatch_returns.validate_child_publication(parent,'book',target,valid,'WT-parent')
    with pytest.raises(ValueError,match='Field: document'):
        dispatch_returns.validate_child_publication(parent,'book',target,'not json','WT-child-1')
    assert target.read_bytes()==before
    # the same live child corrects through its exact contract; an ordinary unreserved path is untouched by this guard
    writing_tools.call(parent,'book','review',{**action,'payload':{**action['payload'],'content':valid}},turn_id='WT-child-1')
    assert target.read_text()==valid
    assert dispatch_returns.validate_child_publication(parent,'book',artifacts.resolve_path(parent,'book','development/ordinary-note.md'),'x','WT-parent') is None
    # a displaced turn: another RUNNING turn of the same session now holds its execution record
    child_hosts._begin_child_execution(parent,'WS-child-1',{'project':'book','session_id':'WS-child-1','turn_id':'WT-child-1-next',
        'dispatch_id':task['id'],'parent_turn_id':'WT-parent','state':'RUNNING','host':child_hosts._process_identity()})
    with pytest.raises(ValueError,match='Field: actor') as displaced:
        dispatch_returns.validate_child_publication(parent,'book',target,valid,'WT-child-1')
    assert 'guarded continuation' in str(displaced.value) and 'in this same turn' not in str(displaced.value)
    assert target.read_text()==valid
    # once settled, the same child turn no longer holds the reserved path
    child_hosts._finish_child_execution(parent,'WS-child-1','WT-child-1','completed')
    with pytest.raises(ValueError,match='Field: actor'):
        dispatch_returns.validate_child_publication(parent,'book',target,valid,'WT-child-1')
    assert target.read_text()==valid


def test_generated_child_contract_names_the_declared_output_and_both_role_vocabularies(parent):
    from laplace.writing import dispatch_execution
    worker={'packet':'develop','role':'worker','return_path':'development/develop-return.json','output':'development/declared-output-probe.md'}
    contract=dispatch_execution._declared_output_contract(parent,'book',worker)
    assert contract['declared_output']['path']=='development/declared-output-probe.md'
    assert contract['declared_output']['write']['payload']=={'path':'development/declared-output-probe.md','scope':'project',
        'reason':"Store this packet's declared report.",'before':None}
    assert contract['return_roles']==['build','continue'] and 'plan role of this packet is worker' in contract['role_vocabulary']
    assert 'validated before the Artifact write' in contract['prewrite_validation']
    legacy=dispatch_execution._declared_output_contract(parent,'book',{**worker,'output':None})
    assert legacy['declared_output'] is None and 'legacy /1' in legacy['output_policy']
    assert set(dispatch_execution._declared_output_contract(parent,'book',{'packet':'review','role':'judge','return_path':'r.json'}))=={'prewrite_validation'}


def test_actual_judge_scope_is_consistent_in_both_provider_frames_native_help_http_and_publisher(parent):
    task,document,_=synthesis_case(parent)
    brief=writing_operating.build('book','review',parent,session_id='WS-child-1',dispatch_id=task['id'])
    assert 'store_artifact' in brief['permissions']
    assert 'store_artifact' not in writing_operating.build('book','review',parent)['permissions']
    expected='development/review-return.json'
    for provider in ('codex','claude'):
        blocks=writing_operating.process_instructions(brief,provider,resumed=False)
        rendered=json.dumps(blocks)
        assert expected in rendered and 'exact-declared-packet-return' in rendered and 'store_artifact' in rendered
    native=writing_tools.execute(parent,'book','review','help',{'operation':'store_artifact'},turn_id='WT-child-1')
    human=authoring_http.inspect_help(parent,{'project':['book'],'turn_id':['WT-child-1'],'operation':['store_artifact']})
    assert native['action']['permitted'] and human['help']=={key:value for key,value in native.items() if key!='read_receipt'}
    state=writing_tools.execute(parent,'book','review','session_settings',{},turn_id='WT-child-1')
    contract=state['return_contract'];action=contract['publish_action']
    schema=writing_tools.execute(parent,'book','review',contract['schema_read']['operation'],
        contract['schema_read']['payload'],turn_id='WT-child-1')
    assert action['payload']['path']==expected and schema['schema']['$id']=='laplace.packet-judgement/2'
    content=artifacts.resolve_path(parent,'book',expected).read_text()
    writing_tools.call(parent,'book','review',{**action,
        'payload':{**action['payload'],'content':content}},turn_id='WT-child-1')
    with pytest.raises(ValueError,match='Independent review'):
        writing_tools.call(parent,'book','review',{'operation':'store_artifact',
            'payload':{**{key:value for key,value in action['payload'].items() if key!='expected_revision'},'path':'development/arbitrary.md','before':None,
                'content':'Unauthorised reviewer output.'}},turn_id='WT-child-1')


def test_parent_blocked_scaffold_has_exact_profile_pins_check_and_publish_recovery_after_no_return(parent):
    task,document,_=synthesis_case(parent)
    judge=artifacts.resolve_path(parent,'book','development/review-return.json');judge.unlink()
    view=project_work.dispatch_view(task,'book',parent)
    contract=dispatch_parent.parent_return_contract(task,'book',parent,turn_id='WT-parent',view=view)
    assert contract['missing_packets']==['review']
    assert contract['schema']['$id']==contract['scaffold']['schema_version']=='laplace.packet-return/2'
    scaffold=contract['scaffold']
    assert scaffold['status']=='BLOCKED' and scaffold['continuation'] and scaffold['residuals']==[]
    assert scaffold['scripted_check']['state']=='PASSED' and scaffold['scripted_check']['ok'] is True
    assert view['execution_state']=='FAILED'  # Read execution remains separate.
    for item in contract['required_reads']:
        writing_tools.call(parent,'book','work',{'operation':item['read']['operation'],
            'payload':item['read']['payload']},turn_id='WT-parent')
    refreshed=dispatch_parent.parent_return_contract(task,'book',parent,turn_id='WT-parent')
    authored=json.loads(refreshed['publish_action']['payload']['content'])
    authored.update(summary='The worker report is retained; the independent judge omitted its required typed return.',
        most_important=['The current dispatch cannot qualify accepted completion without its independent typed judgement.'])
    Draft202012Validator(refreshed['schema']).validate(authored)
    saved=writing_tools.call(parent,'book','work',{**refreshed['publish_action'],
        'payload':{**refreshed['publish_action']['payload'],'content':json.dumps(authored)}},turn_id='WT-parent')
    observed=dispatch_parent.synthesis_view(task,'book',parent)
    assert observed['status']=='VALID' and observed['retained_status']=='BLOCKED'
    assert observed['artifact']['id']==saved['id']
    writing_tools.call(parent,'book','work',{'operation':'task_status','payload':observed['attach_action']['payload']},turn_id='WT-parent')
    assert project_work._tasks('book',parent)[task['id']]['status']=='blocked'


def test_parent_schema_is_inspectable_through_existing_exact_help_and_no_source_tool_is_needed(parent):
    task,_,_=synthesis_case(parent)
    query={'project':['book'],'turn_id':['WT-parent'],'operation':['dispatch_status'],
        'context':[json.dumps({'id':task['id'],'view':'return-contract'})]}
    inspected=authoring_http.inspect_help(parent,query)['help']['action']['return_contract']
    assert inspected['schema_id']=='laplace.packet-return/2' and inspected['publish_action']['operation']=='store_artifact'
    assert all(row['read']['operation']=='read_artifact' for row in inspected['required_reads'])


def test_explicit_same_session_recovery_contract_binds_actual_new_caller_and_never_relaunches_children(parent):
    task,_,_=synthesis_case(parent)
    writing_records.bank(parent,{'record':'writing-turn','id':'WT-recovery-contract','session_id':'WS-parent',
        'project':'book','mode':'work','work_id':task['id']})
    state=writing_tools.execute(parent,'book','work','dispatch_status',{'id':task['id']},turn_id='WT-recovery-contract')
    assert state['caller_turn_id']=='WT-recovery-contract'
    handle=state['parent_return_contract']['read_contract']
    contract=writing_tools.execute(parent,'book','work',handle['operation'],handle['payload'],turn_id='WT-recovery-contract')['parent_return_contract']
    assert json.loads(contract['publish_action']['payload']['content'])['scripted_check']['state']=='NOT_RUN'
    for entry in contract['required_reads']:
        writing_tools.execute(parent,'book','work',entry['read']['operation'],entry['read']['payload'],turn_id='WT-recovery-contract')
    refreshed=writing_tools.execute(parent,'book','work',handle['operation'],handle['payload'],turn_id='WT-recovery-contract')
    check=json.loads(refreshed['parent_return_contract']['publish_action']['payload']['content'])['scripted_check']
    actual=session_reads._records(parent)['read_receipts'][check['receipt_id']]
    assert check['state']=='PASSED' and actual['turn_id']=='WT-recovery-contract'
    assert len([row for row in session_reads._records(parent)['turns'].values() if row.get('dispatch_id')==task['id']])==2


def test_delivered_native_views_are_bounded_and_recovery_uses_one_publish_content(parent):
    from laplace.projects.writing_sources import content_items
    task,_,_=synthesis_case(parent)
    writing_records.bank(parent,{'record':'writing-turn','id':'WT-bounded-recovery','session_id':'WS-parent',
        'project':'book','mode':'work','work_id':task['id']})
    def call(payload):
        result=writing_tools.call(parent,'book','work',{'operation':'dispatch_status','payload':payload},turn_id='WT-bounded-recovery')
        for provider in ('claude','codex'):
            encoded=content_items(result,provider)
            text=encoded[0]['text']
            limit=18000 if payload.get('view')=='return-schema' else 12000 if payload.get('view')=='return-contract' else 8000
            assert len(text.encode())<limit,(payload,len(text.encode()))
            assert json.loads(text)['dispatch_id']==task['id']
        return result
    initial=call({'id':task['id']})
    handle=initial['parent_return_contract']['read_contract']
    action=call(handle['payload'])['parent_return_contract']
    assert 'schema' not in action and 'scaffold' not in action
    assert action['publish_action']['payload']['path']=='development/parent-return.json'
    for read in action['required_reads']:
        writing_tools.call(parent,'book','work',read['read'],turn_id='WT-bounded-recovery')
    current=call(handle['payload'])['parent_return_contract']
    document=json.loads(current['publish_action']['payload']['content'])
    document.update(summary='The retained independent review and worker report support this bounded result.',
        most_important=['All required exact retained inputs were consumed in this recovery.'],
        status='COMPLETE',remaining_work=[],continuation=None)
    schema=call(current['schema_read']['payload'])['schema']
    Draft202012Validator(schema).validate(document)
    writing_tools.call(parent,'book','work',{'operation':'store_artifact','payload':{
        **current['publish_action']['payload'],'content':json.dumps(document)}},turn_id='WT-bounded-recovery')
    assert dispatch_parent.synthesis_view(project_work._tasks('book',parent)[task['id']],'book',parent)['status']=='VALID'
    published=call({'id':task['id']})
    attach=published['synthesis']['attach_action']
    assert attach['operation']=='task_status' and attach['payload']['status']=='done'
    writing_tools.call(parent,'book','work',{'operation':attach['operation'],'payload':attach['payload']},turn_id='WT-bounded-recovery')
    assert project_work._tasks('book',parent)[task['id']]['status']=='done'


def test_child_native_discovery_and_profile_views_do_not_duplicate_or_spill(parent):
    from laplace.projects.writing_sources import content_items
    synthesis_case(parent)
    for view,limit in [('summary',10000),('return-contract',5000),('return-schema',18000)]:
        result=writing_tools.call(parent,'book','review',{'operation':'session_settings','payload':{'view':view}},turn_id='WT-child-1')
        for provider in ('claude','codex'):
            text=content_items(result,provider)[0]['text']
            assert len(text.encode())<limit,(view,len(text.encode()))
        if view!='return-schema':assert 'schema' not in result['return_contract']


def test_ordinary_parent_work_joins_dispatch_and_exact_same_work_recovery(parent):
    import hashlib,time
    from test_dispatch_plan_contract import example
    work=project_work.task('book',{'title':'Ordinary scoped work','goal':'Complete the exact ordinary author goal.'},parent)
    writing_records.bank(parent,{'record':'writing-turn','id':'WT-ordinary-origin','session_id':'WS-parent',
        'project':'book','mode':'work','work_id':work['id'],'connected_observation':dispatch_parent.observation_budget(1)})
    plan=example();plan['synthesis_return_path']='development/ordinary-synthesis.json'
    made=writing_tools.execute(parent,'book','work','dispatch_plan',{'title':'Ordinary dispatch','goal':plan['goal'],
        'path':'development/ordinary-plan.json','plan':plan},turn_id='WT-ordinary-origin')
    task=project_work._tasks('book',parent)[made['dispatch_id']]
    assert task['parent_work_id']==work['id']
    assert task['id'] in project_work._tasks('book',parent)[work['id']]['depends_on']
    child_hosts._begin_child_execution(parent,'WS-parent',{'project':'book','session_id':'WS-parent','turn_id':'WT-ordinary-origin',
        'state':'RUNNING','host':child_hosts._process_identity()})
    observation=dispatch_parent.prepare_observation(task,'book',parent,'WT-ordinary-origin',time.time())
    admitted={key:value for key,value in observation.items() if not key.startswith('_')};admitted['basis']=observation['_basis']
    project_work.transition('book',{'id':task['id'],'status':'in-progress'},parent,dispatch_receipt={
        'dispatch_admitted':True,'dispatch_parent_turn_id':'WT-ordinary-origin','dispatch_parent_observation':admitted,
        'dispatch_plan_sha256':hashlib.sha256((parent/made['plan_artifact']).read_bytes()).hexdigest()})
    dispatch_parent.install_observation(parent,observation)
    receipt=dispatch_parent.final_receipt(parent,'WS-parent','WT-ordinary-origin',author_stopped=True)
    writing_records.bank(parent,{'record':'writing-reply','id':'WR-ordinary-origin','project':'book','session_id':'WS-parent',
        'turn_id':'WT-ordinary-origin','status':'interrupted','parent_continuation':receipt})
    child_hosts._finish_child_execution(parent,'WS-parent','WT-ordinary-origin','interrupted')
    writing_records.bank(parent,{'record':'writing-turn','id':'WT-ordinary-recovery','session_id':'WS-parent',
        'project':'book','mode':'work','work_id':work['id'],'connected_observation':dispatch_parent.observation_budget(1)})
    child_hosts._begin_child_execution(parent,'WS-parent',{'project':'book','session_id':'WS-parent','turn_id':'WT-ordinary-recovery',
        'state':'RUNNING','host':child_hosts._process_identity()})
    task=project_work._tasks('book',parent)[task['id']]
    recovered=dispatch_parent.prepare_observation(task,'book',parent,'WT-ordinary-recovery',time.time())
    assert recovered['origin_parent_turn_id']=='WT-ordinary-origin' and recovered['turn_id']=='WT-ordinary-recovery'
    assert recovered['_basis']==observation['_basis'] and recovered['work_id']==work['id']
