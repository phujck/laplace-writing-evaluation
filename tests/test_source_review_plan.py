"""Public focused Source edit custody and exact offered review input controls."""
import copy,json,hashlib
from pathlib import Path
import pytest
from test_source_use_joins import source,candidate,prepared,sha
from laplace.work import development_source as D,project_work as W
from laplace.projects import writing_sources


def make_plan(s,*,edits=None,content=None,windows=None):
 changed=candidate(s,**({'edits':edits or [{'old':'unique old','new':'new chosen'}]} if content is None else {'content':content}))
 D.apply(s['root'],'public',{'candidate_id':changed['candidate_id']},s['door'])
 pins={p:D._pin(s['checkout']/p) for p in ['src/answer.py','evaluator.py','guide.md']}
 basis=D.prepare_review_basis(s['root'],'public','work',{'grant_id':s['grant']['id'],'candidate_id':changed['candidate_id']},pins,door=s['door'])
 if windows is None:windows=[{'path':p,'line_start':1,'line_end':len(D._reader_text((s['checkout']/p).read_bytes().decode()).splitlines())} for p in pins]
 return changed,basis,D.prepare_review_plan(s['root'],'public','work',basis,pins,{'windows':windows})


def test_dirty_unicode_crlf_edits_plan_and_exact_bounded_reader_handles(source,monkeypatch):
 s=source;path=s['checkout']/'src/answer.py';original='α dirty\r\nunique old\r\nlast old\r\n';path.write_bytes(original.encode())
 edits=[{'old':'last old','new':'終 🧪'},{'old':'unique old','new':'first\r\nsecond'}]
 c=candidate(s,edits=edits);final=original.replace('unique old','first\r\nsecond').replace('last old','終 🧪')
 assert candidate(s,content=final)==c
 task=W._tasks('public',s['root'])['work'];held=copy.deepcopy(D._latest(task,'candidate',c['candidate_id']))
 assert held['files'][0]['verified_edits']['before_sha256']==sha(original)
 D.apply(s['root'],'public',{'candidate_id':c['candidate_id']},s['door'])
 pins={p:D._pin(s['checkout']/p) for p in ['src/answer.py','evaluator.py','guide.md']};basis=D.prepare_review_basis(s['root'],'public','work',{'grant_id':s['grant']['id'],'candidate_id':c['candidate_id']},pins,door=s['door'])
 windows=[{'path':'src/answer.py','line_start':2,'line_end':3},{'path':'src/answer.py','line_start':3,'line_end':4},{'path':'evaluator.py','line_start':1,'line_end':1},{'path':'guide.md','line_start':1,'line_end':1}]
 before=W._ledger(s['root']).read_bytes();plan=D.prepare_review_plan(s['root'],'public','work',basis,pins,{'windows':windows});assert W._ledger(s['root']).read_bytes()==before
 assert plan['state']=='COMPLETE' and plan['semantic_adequacy']=='UNASSESSED' and plan['offered_not_observed']
 item=next(i for i in plan['inputs'] if i['path']=='src/answer.py');assert len(item['selected_context'])==1 and len(item['requested_context'])==2 and item['uninspected_extents']
 assert item['verified_edits']['before_sha256']==sha(original) and not item['uncovered_edit_ids']
 for item in plan['inputs']:
  text=D._reader_text((s['checkout']/item['path']).read_bytes().decode())
  for read in item['initial_reads']:
   page=writing_sources.execute(s['root'],read['read']['payload']);assert page['content']==text[read['offset']:read['offset']+read['chars']]
   assert read['offset']+len(page['content'])<=read['stop_before_offset']
 assert D._latest(W._tasks('public',s['root'])['work'],'candidate',c['candidate_id'])==held
 (s['root']/'sample-plan.json').write_text(json.dumps(plan,indent=2,ensure_ascii=False))


def test_pin_only_read_is_projection_only_and_rejected_on_other_actions(source,monkeypatch):
 s=source;path=s['checkout']/'src/answer.py';actual=Path.read_bytes
 def no_materialization(p):
  if p==path:pytest.fail('pin-only read must not materialize path.read_bytes')
  return actual(p)
 monkeypatch.setattr(Path,'read_bytes',no_materialization)
 out=D.handle(s['root'],'public',{'action':'read','grant_id':s['grant']['id'],'path':'src/answer.py','include_text':False},s['door']);assert out['text'] is None and out['bytes']>0 and out['repository_read']['payload']['expected_sha256']==out['sha256']
 from jsonschema import validate,ValidationError
 for action in ['candidate','status','apply','grant','check']:
  with pytest.raises(ValidationError):validate({'action':action,'include_text':False},D.contract())
 with pytest.raises(ValueError):D.status(s['root'],'public',{'work_id':'work','include_text':False},s['door'])


def test_legacy_first_candidate_replay_never_augments_facts_and_is_unavailable(source):
 s=source;path=s['checkout']/'src/answer.py';original=path.read_text();full=candidate(s,content=original.replace('unique old','new chosen'));ledger=W._ledger(s['root']).read_bytes()
 assert candidate(s,edits=[{'old':'unique old','new':'new chosen'}])==full and W._ledger(s['root']).read_bytes()==ledger
 row=D._latest(W._tasks('public',s['root'])['work'],'candidate',full['candidate_id']);assert 'verified_edits' not in row['files'][0]
 _c,basis,plan=make_plan(s,content=original.replace('unique old','new chosen'));assert plan['state']=='UNAVAILABLE'
 reasons=next(i for i in plan['inputs'] if i['path']=='src/answer.py')['reasons']
 # The cumulative geometry may additionally name an unknown baseline when the base blob is not readable here.
 assert reasons[0]=='VERIFIED_EDITS_UNAVAILABLE' and set(reasons)<={'VERIFIED_EDITS_UNAVAILABLE','CUMULATIVE_GEOMETRY_UNKNOWN_BASELINE'}


def test_per_input_projection_locality_plan_identity_and_missing_change_coverage(source):
 s=source;c,basis,plan=make_plan(s,windows=[{'path':'src/answer.py','line_start':1,'line_end':4},{'path':'evaluator.py','line_start':1,'line_end':1}]);assert plan['state']=='INCOMPLETE'
 pins={p:basis['pins'][p] for p in ['src/answer.py','evaluator.py']};projected=D.review_plan_for_inputs(plan,pins);assert projected['state']=='COMPLETE' and projected['outside_consumed_inputs']==['guide.md']
 assert D.review_plan_for_inputs(plan,{'guide.md':basis['pins']['guide.md']})['state']=='INCOMPLETE'
 projected['inputs'][0]['state']='caller';assert D.review_plan_for_inputs(plan,pins)['state']=='COMPLETE'
 changed=copy.deepcopy(plan);changed['inputs'][0]['state']='caller'
 with pytest.raises(ValueError):D.review_plan_for_inputs(changed,pins)
 with pytest.raises(ValueError):D.review_plan_for_inputs(plan,{'src/answer.py':sha('forged')})
 uncovered=D.prepare_review_plan(s['root'],'public','work',basis,basis['pins'],{'windows':[{'path':'src/answer.py','line_start':1,'line_end':1}]});assert D.review_plan_for_inputs(uncovered,pins)['state']=='INCOMPLETE'


@pytest.mark.parametrize('window',[{'path':'not-covered','line_start':1,'line_end':1},{'path':'src/answer.py','line_start':True,'line_end':2},{'path':'src/answer.py','line_start':3,'line_end':2},{'path':'src/answer.py','line_start':1,'line_end':99}])
def test_bad_context_refuses_without_custody_effect(source,window):
 s=source;c,basis,plan=make_plan(s);before=W._ledger(s['root']).read_bytes()
 with pytest.raises(ValueError):D.prepare_review_plan(s['root'],'public','work',basis,basis['pins'],{'windows':[window]})
 assert W._ledger(s['root']).read_bytes()==before


def test_changed_or_retargeted_source_cannot_offer_current_plan(source):
 s=source;c,basis,plan=make_plan(s);(s['checkout']/'src/answer.py').write_text('changed')
 with pytest.raises(ValueError,match='CHANGED'):D.prepare_review_plan(s['root'],'public','work',basis,basis['pins'],{'windows':[]})
 (s['root']/'profiles/writing_sources.json').write_text(json.dumps({'repositories':{'selected':str(s['root'])}}))
 with pytest.raises(ValueError):D.prepare_review_plan(s['root'],'public','work',basis,basis['pins'],{'windows':[]})


def test_empty_and_unsupported_large_inputs_are_explicit(source):
 s=source;c,basis,plan=make_plan(s,edits=[{'old':(s['checkout']/'src/answer.py').read_text(),'new':''}],windows=[{'path':'evaluator.py','line_start':1,'line_end':1},{'path':'guide.md','line_start':1,'line_end':1}]);item=next(i for i in plan['inputs'] if i['path']=='src/answer.py');assert item['state']=='INCOMPLETE' and item['reasons']==['EMPTY_INPUT_HAS_NO_LINE_WINDOW'] and item['reader_chars']==0 and item['initial_reads']==[]
 # Add an unchanged large required input to a fresh owner-validated basis.
 path=s['checkout']/'guide.md';path.write_text('x'*(D.MAX_CANDIDATE_BYTES+1));pins={**basis['pins'],'guide.md':D._pin(path)};held=D.prepare_review_basis(s['root'],'public','work',{k:basis[k] for k in ['grant_id','candidate_id']},pins,door=s['door'])
 big=D.prepare_review_plan(s['root'],'public','work',held,pins,{'windows':[]});item=next(i for i in big['inputs'] if i['path']=='guide.md');assert item['state']=='UNAVAILABLE' and item['reader_chars'] is None and not item['initial_reads'] and item['fallback_read']['payload']['expected_sha256']==pins['guide.md']


def test_issued_human_HTTP_extent_uses_existing_material_owner(source):
 from urllib.parse import urlsplit,parse_qs
 from laplace.projects import library
 s=source;c,basis,plan=make_plan(s);read=plan['inputs'][0]['initial_reads'][0]
 url=urlsplit(read['read']['http']['url']);code,_,body=library.handle(url.path,parse_qs(url.query),'GET',b'',s['root']);assert code==200,body
 native=writing_sources.execute(s['root'],read['read']['payload']);observed=json.loads(body)
 assert observed['owner_result']['content']==native['content'] and len(native['content'])==read['chars']
 assert read['read']['human_read']['url']==read['read']['http']['url']
 (s['root']/'sample-plan-with-human-reads.json').write_text(json.dumps(plan,indent=2,ensure_ascii=False))


def test_tampered_verified_facts_cannot_claim_complete_plan(source):
 s=source;c,basis,plan=make_plan(s);task=W._tasks('public',s['root'])['work'];row=copy.deepcopy(D._latest(task,'candidate',c['candidate_id']))
 row['files'][0]['verified_edits']['edits'][0]['before']['text']='fabricated old span';W._append(s['root'],row)
 bad=D.prepare_review_plan(s['root'],'public','work',basis,basis['pins'],plan['source_context']);assert bad['state']=='UNAVAILABLE'
 assert 'VERIFIED_EDITS_INVALID' in next(i for i in bad['inputs'] if i['changed'])['reasons']


def test_retained_script_case_offers_eight_bounded_initial_reads_without_model(source):
 import ast
 s=source;checkout=s['checkout'];S=Path(__file__).resolve().parents[1]
 paths=['scripts/reembed.py','scripts/sewup.py','docs/reembed.md','docs/sewup.md','tests/evaluator.py']
 source_names=['scripts/reembed.py','scripts/sewup.py','src/laplace/pipeline/canon/wiki/operations/reembed_contract.md','src/laplace/pipeline/canon/wiki/operations/sewup_contract.md','tests/check_close_publication_cause.py']
 for rel,name in zip(paths,source_names):
  p=checkout/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((S/name).read_bytes())
 task=W._tasks('public',s['root'])['work'];W.task('public',{'id':'work','expected_work_revision':W._task_revision(task),'review_obligations':[{'id':'source','scope':'source','label':'Cause result and guards','inputs':paths}]},s['root'])
 payload={**s['payload'],'request_id':'public-retained-case-plan','expected_work_revision':W._task_revision(W._tasks('public',s['root'])['work']),'paths':['scripts/*.py','docs/*.md','tests/*.py'],'checks':{}}
 grant=D.grant(s['root'],'public',payload,{'origin':'human'})['grant']
 changes=[('scripts/reembed.py','deposit refused without a producer reason','deposit refused without a producer Reason'),('scripts/sewup.py','published artifacts verified','published artifacts Verified'),('docs/reembed.md', (checkout/'docs/reembed.md').read_text().splitlines()[0], (checkout/'docs/reembed.md').read_text().splitlines()[0]+' '),('docs/sewup.md',(checkout/'docs/sewup.md').read_text().splitlines()[0],(checkout/'docs/sewup.md').read_text().splitlines()[0]+' ')]
 files=[{'path':p,'before_sha256':D._pin(checkout/p),'edits':[{'old':a,'new':b}]} for p,a,b in changes]
 changed=D.candidate(s['root'],'public',{'grant_id':grant['id'],'files':files},s['door']);D.apply(s['root'],'public',{'candidate_id':changed['candidate_id']},s['door'])
 pins={p:D._pin(checkout/p) for p in paths};basis=D.prepare_review_basis(s['root'],'public','work',{'grant_id':grant['id'],'candidate_id':changed['candidate_id']},pins,door=s['door'])
 windows=[];ast_chars=0
 for path,names in [('scripts/reembed.py',['main','_publication_record']),('scripts/sewup.py',['step_reembed','_publication_matches'])]:
  text=(checkout/path).read_text();tree=ast.parse(text)
  for node in tree.body:
   if isinstance(node,ast.FunctionDef) and node.name in names:
    windows.append({'path':path,'line_start':node.lineno,'line_end':node.end_lineno});ast_chars+=len(ast.get_source_segment(text,node))
 for path in ['docs/reembed.md','docs/sewup.md','tests/evaluator.py']:windows.append({'path':path,'line_start':1,'line_end':len((checkout/path).read_text().splitlines())})
 # The fixture is the exact declared public script (bc3fa194), not the earlier copy this oracle was first written against.
 assert D._pin(S/'scripts/reembed.py')=='sha256:52f5a1743c4b904e9066194e0abcc5a678f92bdb97aad46421f2c82b48e46b01'
 old=D.prepare_review_plan(s['root'],'public','work',basis,pins,{'windows':windows})
 stale={i['path']:i for i in old['inputs']}['scripts/reembed.py']
 # Authentic old result: the originally named functions do not contain this script's actual edit, and the owner says so.
 assert old['state']=='INCOMPLETE' and stale['state']=='INCOMPLETE' and stale['uncovered_edit_ids']==['edit-1'],[(i['path'],i['state'],i['reasons']) for i in old['inputs']]
 assert 'CHANGED_SPANS_OUTSIDE_SELECTED_CONTEXT' in stale['reasons'] and all(i['state']=='COMPLETE' for i in old['inputs'] if i['path']!='scripts/reembed.py')
 # Original oracle relation preserved on exact bytes: each inclusive line window adds its trailing newline to the AST span.
 ORIGINAL={'function_AST_chars':8394,'inclusive_line_window_chars':8398,'named_windows':4}
 script_chars=sum(e['chars'] for i in old['inputs'] if i['path'].startswith('scripts/') for e in i['selected_context'])
 assert ORIGINAL['inclusive_line_window_chars']-ORIGINAL['function_AST_chars']==ORIGINAL['named_windows']==script_chars-ast_chars
 # Select the actual current edit and its cumulative hunk, then the whole plan is COMPLETE through bounded issued reads.
 text=D._reader_text((checkout/'scripts/reembed.py').read_bytes().decode())
 for edit in stale['verified_edits']['edits']:
  a=edit['reader_after']['offset'];b=a+edit['reader_after']['chars']
  windows.append({'path':'scripts/reembed.py','line_start':text.count('\n',0,a)+1,'line_end':text.count('\n',0,b)+1})
 for hunk in stale['cumulative_change']['geometry']['hunks']:
  first,last=hunk['after_lines'];windows.append({'path':'scripts/reembed.py','line_start':max(1,first),'line_end':max(first,last)})
 plan=D.prepare_review_plan(s['root'],'public','work',basis,pins,{'windows':windows});assert plan['state']=='COMPLETE',[(i['path'],i['state'],i['reasons'],i.get('uncovered_hunk_ids'),i.get('uncovered_edit_ids')) for i in plan['inputs']]
 assert plan['initial_read_calls']==sum(len(i['initial_reads']) for i in plan['inputs'])>old['initial_read_calls']>=8
 for item in plan['inputs']:
  for read in item['initial_reads']:
   observed=writing_sources.execute(s['root'],read['read']['payload']);assert len(observed['content'])==read['chars']
 proof={'actual_historical_repository_attempts':32,'offered_initial_reads':plan['initial_read_calls'],'function_AST_chars':ast_chars,'inclusive_line_window_chars':script_chars,'newline_difference':'Each inclusive line range includes its trailing newline; exact AST span excluded it.','qualification':'Public script copies and new same-size controlled edits. Not real source-task replay, semantic completeness, model/token/cost proof; deliberate expansion may need additional reads.','plan':plan}
 (s['root']/'retained-case-plan-proof.json').write_text(json.dumps(proof,indent=2,ensure_ascii=False))


def test_pin_only_actual_native_and_HTTP_doors(source):
 from laplace.native import tools
 from laplace.web import project_work_surface
 s=source;payload={'action':'read','grant_id':s['grant']['id'],'path':'src/answer.py','include_text':False}
 native=tools.execute(s['root'],'public','work','development_source',payload,turn_id='WT-parent')
 code,_,body=project_work_surface.handle('/work/development',{},'POST',json.dumps({'project':'public',**payload}).encode(),s['root']);assert code==200
 result=json.loads(body);assert result['text'] is None and native['sha256']==result['sha256'] and native['repository_read']==result['repository_read']
 bad={'project':'public','action':'status','work_id':'work','include_text':False};code,_,body=project_work_surface.handle('/work/development',{},'POST',json.dumps(bad).encode(),s['root']);assert code>=400


@pytest.mark.parametrize('raw',[b'public\x00input',b'public\xffinput'])
def test_unsupported_required_text_geometry_is_explicit(source,raw):
 s=source;c,basis,plan=make_plan(s);path=s['checkout']/'evaluator.py';path.write_bytes(raw);pins={**basis['pins'],'evaluator.py':D._pin(path)}
 held=D.prepare_review_basis(s['root'],'public','work',{k:basis[k] for k in ['grant_id','candidate_id']},pins,door=s['door'])
 result=D.prepare_review_plan(s['root'],'public','work',held,pins,plan['source_context']);row=next(i for i in result['inputs'] if i['path']=='evaluator.py')
 assert row['state']=='UNAVAILABLE' and row['reasons']==['PLAIN_UTF8_GEOMETRY_UNAVAILABLE'] and not row['initial_reads'] and row['reader_chars'] is None


@pytest.mark.parametrize('first_compact',[False,True])
def test_equivalent_concurrent_snapshot_replay_preserves_first_candidate_metadata(source,monkeypatch,first_compact):
 s=source;original=(s['checkout']/'src/answer.py').read_text();old_task=W._tasks('public',s['root'])['work'];real=D._current
 first_fields={'edits':[{'old':'unique old','new':'new chosen'}]} if first_compact else {'content':original.replace('unique old','new chosen')}
 first=candidate(s,**first_fields);ledger=W._ledger(s['root']).read_bytes()
 def stale(*a,**k):
  task,row,checkout=real(*a,**k);return old_task,row,checkout
 monkeypatch.setattr(D,'_current',stale)
 next_fields={'content':original.replace('unique old','new chosen')} if first_compact else {'edits':[{'old':'unique old','new':'new chosen'}]}
 assert candidate(s,**next_fields)==first and W._ledger(s['root']).read_bytes()==ledger
 held=D._latest(W._tasks('public',s['root'])['work'],'candidate',first['candidate_id']);assert ('verified_edits' in held['files'][0])==first_compact


# ------------------------------------------------------------------ cumulative review subject (closure contract 2026-11-02)

def _apply(s, grant_id, files):
    c = D.candidate(s['root'], 'public', {'grant_id': grant_id, 'files': files}, s['door'])
    assert D.apply(s['root'], 'public', {'candidate_id': c['candidate_id']}, s['door'])['ok']
    return c


def _edit(s, path, old, new):
    return {'path': path, 'before_sha256': D._pin(s['checkout'] / path), 'edits': [{'old': old, 'new': new}]}


def _full_windows(s, pins):
    return [{'path': p, 'line_start': 1, 'line_end': len(D._reader_text((s['checkout'] / p).read_bytes().decode()).splitlines())} for p in pins]


def _reissue(s, request):
    payload = {**s['payload'], 'request_id': request, 'expected_work_revision': W._task_revision(W._tasks('public', s['root'])['work'])}
    return D.grant(s['root'], 'public', payload, {'origin': 'human'})['grant']


def test_cumulative_subject_spans_every_committed_effect_samefile_and_reissued_grant(source):
    s = source; root = s['root']
    first = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'unique old', 'first change')])
    second = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'last old', 'second change')])   # same file, later effect
    again = _reissue(s, 'public-source-use-reissue')
    assert again['id'] != s['grant']['id']
    third = _apply(s, again['id'], [_edit(s, 'guide.md', 'Public unchanged documentation.', 'Public changed documentation.')])
    pins = {p: D._pin(s['checkout'] / p) for p in ['src/answer.py', 'evaluator.py', 'guide.md']}
    basis = D.prepare_review_basis(root, 'public', 'work', {'grant_id': again['id'], 'candidate_id': third['candidate_id']}, pins, door=s['door'])
    ledger = W._ledger(root).read_bytes()
    subject = D.review_subject(root, 'public', 'work', basis)
    assert W._ledger(root).read_bytes() == ledger   # pure derivation, no custody effect
    assert subject['union'] == {'paths_total': 2, 'commission_changed': 2, 'carry_members': 0, 'carry_outside_changes': 0, 'effects': 3, 'grants': 2}
    answer = next(r for r in subject['changed_files'] if r['path'] == 'src/answer.py')
    assert [link['candidate_id'] for link in answer['effects']] == [first['candidate_id'], second['candidate_id']]
    assert answer['retained_preimage'] == sha('α original\nunique old\nkeep middle\nlast old\n') and answer['current_postimage'] == pins['src/answer.py']
    assert answer['chain_continuous'] and answer['geometry']['state'] == 'DERIVED' and answer['baseline'] == 'PINNED'
    assert [h['after_lines'] for h in answer['geometry']['hunks']] == [[2, 2], [4, 4]]
    # The latest candidate is the exact anchor only; it never touched src/answer.py.
    assert subject['latest_delta']['candidate_id'] == third['candidate_id'] and [f['path'] for f in subject['latest_delta']['files']] == ['guide.md']
    assert subject['readonly_carry']['state'] == 'NOT_DECLARED' and subject['stage'] == {'state': 'NOT_DECLARED'}
    plan = D.prepare_review_plan(root, 'public', 'work', basis, pins, {'windows': _full_windows(s, pins)})
    assert plan['schema_version'] == D.REVIEW_PLAN_SCHEMA_V2 and plan['state'] == 'COMPLETE' and plan['review_subject'] == subject
    item = next(i for i in plan['inputs'] if i['path'] == 'src/answer.py')
    assert item['changed'] and item['verified_edits'] is None
    assert item['cumulative_change']['effect_ids'] == [link['effect_id'] for link in answer['effects']]
    projected = D.review_plan_for_inputs(plan, {'src/answer.py': pins['src/answer.py']})
    assert projected['review_subject']['subject_id'] == subject['subject_id'] and projected['latest_delta'] == subject['latest_delta']
    # Change coverage comes from cumulative geometry, never stale offsets of either earlier candidate.
    narrow = D.prepare_review_plan(root, 'public', 'work', basis, pins, {'windows': [{'path': 'src/answer.py', 'line_start': 1, 'line_end': 2}]})
    row = next(i for i in narrow['inputs'] if i['path'] == 'src/answer.py')
    assert row['uncovered_hunk_ids'] == ['hunk-2'] and 'CUMULATIVE_CHANGES_OUTSIDE_SELECTED_CONTEXT' in row['reasons'] and row['state'] == 'INCOMPLETE'
    offered = D.review_preflight(root, 'public', {'work_id': 'work', 'grant_id': again['id'], 'candidate_id': third['candidate_id'], 'paths': ['src/answer.py']}, s['door'])
    assert offered['commission']['effects'] == 3 and offered['commission']['changed_total'] == 2 and offered['scaffold']['offered_not_observed']
    assert {(w['line_start'], w['line_end']) for w in offered['scaffold']['windows']} == {(1, 4)}
    assert D.validate_review_subject(root, 'public', 'work', basis, subject)['status'] == 'CURRENT'
    # A later committed effect of the same commission moves the whole subject; the recorded one is no longer current.
    _apply(s, again['id'], [_edit(s, 'src/answer.py', 'keep middle', 'keep middle moved')])
    moved = D.validate_review_subject(root, 'public', 'work', basis, subject)
    assert moved['status'] == 'CHANGED'
    forged = {**subject, 'union': {**subject['union'], 'effects': 1}}
    assert D.validate_review_subject(root, 'public', 'work', basis, forged)['status'] == 'UNKNOWN'


def test_readonly_carry_is_admitted_separately_and_refuses_drift_foreign_escape_and_write(source):
    s = source; root = s['root']; checkout = s['checkout']
    original_answer = D._pin(checkout / 'src/answer.py')
    (checkout / 'docs').mkdir(); (checkout / 'docs/carry.md').write_text('Inherited unreviewed carry.\n')
    c = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'unique old', 'carry change')])
    pins = {p: D._pin(checkout / p) for p in ['src/answer.py', 'evaluator.py', 'guide.md']}
    basis = D.prepare_review_basis(root, 'public', 'work', {'grant_id': s['grant']['id'], 'candidate_id': c['candidate_id']}, pins, door=s['door'])
    carry = {'schema': D.REVIEW_CARRY_SCHEMA, 'repository': 'selected', 'base': s['grant']['base'], 'members': [
        {'path': 'src/answer.py', 'sha256': original_answer}, {'path': 'guide.md', 'sha256': pins['guide.md']},
        {'path': 'docs/carry.md', 'sha256': D._pin(checkout / 'docs/carry.md')}]}
    stage = {'id': 'pre-source-bootstrap', 'pre_source_review': ['External guarded functional proof of the named tests.'],
             'post_adoption': ['Ordinary app Source check after adoption.'], 'authority': [{'path': 'research/stage.json', 'sha256': sha('stage')}]}
    subject = D.review_subject(root, 'public', 'work', basis, {'carry': carry, 'stage': stage})
    relations = {m['path']: m['relation'] for m in subject['readonly_carry']['members']}
    # F1: a carry member is UNCHANGED_CARRY only when it IS the base blob; the untracked inherited file was added after the base
    assert relations == {'src/answer.py': 'COMMISSION_PREIMAGE', 'guide.md': 'UNCHANGED_CARRY', 'docs/carry.md': 'ADDED_SINCE_BASE'}
    assert subject['union'] == {'paths_total': 3, 'commission_changed': 1, 'carry_members': 3, 'carry_outside_changes': 2, 'effects': 1, 'grants': 1}
    assert subject['stage']['post_adoption'] == ['Ordinary app Source check after adoption.'] and 'neither satisfies nor waives' in subject['stage']['meaning']
    # The carry is review scope only: the write fence and grant paths are unchanged.
    with pytest.raises(ValueError):
        D.candidate(root, 'public', {'grant_id': s['grant']['id'], 'files': [{'path': 'docs/carry.md', 'before_sha256': D._pin(checkout / 'docs/carry.md'), 'content': 'x'}]}, s['door'])
    assert D._latest(W._tasks('public', root)['work'], 'grant', s['grant']['id'])['paths'] == s['grant']['paths']
    assert D.validate_review_subject(root, 'public', 'work', basis, subject)['status'] == 'CURRENT'
    (checkout / 'docs/carry.md').write_text('drifted\n')
    moved = D.validate_review_subject(root, 'public', 'work', basis, subject)
    assert moved['status'] == 'CHANGED' and 'drifted' in moved['reason']
    (checkout / 'docs/carry.md').write_text('Inherited unreviewed carry.\n')
    assert D.validate_review_subject(root, 'public', 'work', basis, subject)['status'] == 'CURRENT'
    for bad in ({**carry, 'base': '0' * 40}, {**carry, 'members': [{'path': 'src/answer.py', 'sha256': sha('foreign cut')}]},
                {**carry, 'members': [{'path': '../escape.md', 'sha256': sha('x')}]}, {**carry, 'schema': 'other'}):
        with pytest.raises(ValueError):
            D.review_subject(root, 'public', 'work', basis, {'carry': bad})
    with pytest.raises(ValueError):
        D.review_subject(root, 'public', 'work', basis, {'stage': {**stage, 'pre_source_review': []}})
    with pytest.raises(ValueError):
        D.review_subject(root, 'public', 'work', basis, {'carry': carry, 'other': True})


def test_readonly_carry_above_ordinary_pin_bound_keeps_obligation_pins_local(source):
    """A whole subject larger than the <=64 Work/obligation pin bound: the typed subject retains every read-only member
    while the handoff pins and consumed inputs stay an ordinary bounded projection and the write fence is unchanged."""
    s = source; root = s['root']; checkout = s['checkout']
    (checkout / 'carry').mkdir()
    members = []
    for index in range(80):
        path = checkout / ('carry/held-%02d.md' % index); path.write_text('held carry %d\n' % index)
        members.append({'path': 'carry/held-%02d.md' % index, 'sha256': D._pin(path)})
    c = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'unique old', 'bounded change')])
    pins = {p: D._pin(checkout / p) for p in ['src/answer.py', 'evaluator.py', 'guide.md']}
    basis = D.prepare_review_basis(root, 'public', 'work', {'grant_id': s['grant']['id'], 'candidate_id': c['candidate_id']}, pins, door=s['door'])
    carry = {'schema': D.REVIEW_CARRY_SCHEMA, 'members': members}
    plan = D.prepare_review_plan(root, 'public', 'work', basis, pins, {'windows': _full_windows(s, pins)}, {'carry': carry})
    subject = plan['review_subject']
    assert subject['readonly_carry']['members_total'] == 80 and subject['union']['paths_total'] == 81 and subject['union']['carry_outside_changes'] == 80
    assert len(plan['pins']) == 3 and sorted(i['path'] for i in plan['inputs']) == sorted(pins) and plan['state'] == 'COMPLETE'
    assert len(D.review_plan_for_inputs(plan, {'src/answer.py': pins['src/answer.py']})['inputs']) == 1
    with pytest.raises(ValueError):   # pins themselves keep their ordinary bound; the carry never widens them
        D.prepare_review_plan(root, 'public', 'work', basis, {m['path']: m['sha256'] for m in members}, {'windows': []})
    with pytest.raises(ValueError):   # and never becomes write authority
        D.candidate(root, 'public', {'grant_id': s['grant']['id'], 'files': [{'path': members[0]['path'], 'before_sha256': members[0]['sha256'], 'content': 'x'}]}, s['door'])
    assert D.validate_review_subject(root, 'public', 'work', basis, subject)['status'] == 'CURRENT'
    (checkout / members[79]['path']).write_text('drifted\n')
    assert D.validate_review_subject(root, 'public', 'work', basis, subject)['status'] == 'CHANGED'


def test_handoff_retains_subject_and_request_renders_whole_subject_stage_brief_before_geometry(source):
    from laplace.work import project_work_review as R, work_delivery as WD
    s = source; root = s['root']; checkout = s['checkout']
    first = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'unique old', 'first change')])
    latest = _apply(s, s['grant']['id'], [_edit(s, 'guide.md', 'Public unchanged documentation.', 'Public changed documentation.')])
    pins = {p: D._pin(checkout / p) for p in ['src/answer.py', 'evaluator.py', 'guide.md']}
    stage = {'id': 'pre-source-bootstrap', 'pre_source_review': ['External guarded functional proof.'], 'post_adoption': ['Ordinary app Source check.']}
    evidence = root / 'research/functional.json'; evidence.parent.mkdir(parents=True, exist_ok=True); evidence.write_text('functional')
    request = {'id': 'work', 'phase': 'handoff', 'request_id': 'cumulative-handoff-0001',
               'expected_work_revision': W._task_revision(W._tasks('public', root)['work']),
               'source_basis': {'grant_id': s['grant']['id'], 'candidate_id': latest['candidate_id']}, 'pins': pins,
               'obligations': ['source', 'guide'], 'source_context': {'windows': _full_windows(s, pins)}, 'source_subject': {'stage': stage},
               'summary': 'Whole closure handoff: two committed effects.', 'evidence': [{'path': 'research/functional.json', 'sha256': sha('functional')}]}
    recorded = R.record('public', request, root, door=s['door'])
    handoff = recorded['phase']
    plan = handoff['source_review_plan']
    assert handoff['source_subject'] == {'stage': stage} and plan['schema_version'] == D.REVIEW_PLAN_SCHEMA_V2
    assert plan['review_subject']['union']['effects'] == 2 and plan['latest_delta']['candidate_id'] == latest['candidate_id']
    summary = R.source_plan_summary(plan)
    assert summary['changed_file_count'] == 2 and summary['latest_delta_file_count'] == 1 and summary['review_subject']['stage'] == 'pre-source-bootstrap'
    pin = WD._content_pin(handoff)
    assert pin != WD._content_pin({**handoff, 'summary': 'another brief'})   # the reviewer-visible brief is bound
    with pytest.raises(ValueError):
        R.record('public', {**request, 'expected_work_revision': W._task_revision(W._tasks('public', root)['work']),
                            'source_subject': {'stage': {**stage, 'id': 'other-stage'}}}, root, door=s['door'])
    task = W._tasks('public', root)['work']
    intent = {'id': 'WD-cumulative-request', 'obligation_id': 'source', 'handoff_id': handoff['id'], 'work_scope_revision': 'scope',
              'recipient': {'id': s['binding']['id'], 'revision': s['binding']['revision']},
              'source_basis': handoff['source_basis'], 'source_review_plan': plan}
    text = WD._request_text(task, intent, handoff, root)
    lines = text.split('\n')
    at = lambda prefix: next(i for i, line in enumerate(lines) if line.startswith(prefix))
    assert 'Complete candidate file inventory' not in text and 'What changed in' not in text
    assert at('WHOLE REVIEW SUBJECT ' + plan['review_subject']['subject_id']) < at('Acceptance stage pre-source-bootstrap') < at('Handoff summary (bounded): Whole closure handoff')
    assert at('Handoff evidence') < at('Commission change inventory') < at('Latest delta only') < at('Cumulative change in src/answer.py') < at('Context and coverage for src/answer.py')
    assert 'Ordinary app Source check.' in lines[at('Acceptance stage')] and 'research/functional.json' in lines[at('Handoff evidence')]
    assert first['candidate_id'] not in lines[at('Latest delta only')] and 'guide.md' in lines[at('Latest delta only')]
    assert 'Read-only carry: NOT DECLARED' in text


def test_prepared_completion_carries_the_same_cumulative_subject_stage_and_currentness(source):
    """The prepared (armed) completion uses the SAME Source collector, subject, stage and currentness as an ordinary
    cumulative handoff; a legacy-shaped arm keeps its original meaning. Public synthetic producer turn (no provider)."""
    from test_eigen_continuity_owner import produce, arm_payload, PRODUCER, judged
    from laplace.work import project_work_continuity as C, work_delivery as WD
    s = source; root = s['root']
    grant, _account, candidate = produce(s)
    pins = {p: D._pin(s['checkout'] / p) for p in ('src/answer.py', 'evaluator.py', 'guide.md')}
    stage = {'id': 'pre-source-bootstrap', 'pre_source_review': ['External guarded functional proof.'], 'post_adoption': ['Ordinary app Source check.']}
    with pytest.raises(ValueError, match='source_context'):
        D.handle(root, 'public', arm_payload(s, grant, candidate, request_id='public-subject-arm-0', source_subject={'stage': stage}), PRODUCER)
    armed = D.handle(root, 'public', arm_payload(s, grant, candidate, request_id='public-subject-arm-1',
                     source_context={'windows': _full_windows(s, pins)}, source_subject={'stage': stage}), PRODUCER)['intent']
    assert armed['production']['effects_scope'] == 'commission' and armed['production']['review_subject']['stage'] == 'pre-source-bootstrap'
    row = C._intent(W._tasks('public', root)['work'], armed['id'])
    plan = row['production']['source_review_plan']
    assert plan['schema_version'] == D.REVIEW_PLAN_SCHEMA_V2 and plan['review_subject']['union']['effects'] == 2
    assert plan['latest_delta']['candidate_id'] == candidate
    assert sorted(r['path'] for r in plan['review_subject']['changed_files']) == ['guide.md', 'src/answer.py']
    assert row['production']['effects'] == [e['id'] for e in plan['review_subject']['effects']]
    ready = judged(s, armed)
    assert ready['facts']['source'] == 'CURRENT' and ready['facts']['source_subject'] == 'CURRENT'
    tasks = W._tasks('public', root)
    handoff = C._handoff(root, 'public', tasks, tasks['work'], row, {'actor': 'dispatcher', 'origin': 'human'})
    assert handoff['source_review_plan'] == plan and handoff['source_subject'] == {'stage': stage} and 'source_review_plan_absent' not in handoff
    assert plan['review_subject']['subject_id'] in handoff['summary']
    assert WD._content_pin(handoff) != WD._content_pin({k: v for k, v in handoff.items() if k != 'source_review_plan'})
    # a legacy-shaped arm (no reading offer) keeps its original meaning: no plan and an explicit absence in its handoff
    legacy = D.handle(root, 'public', arm_payload(s, grant, candidate, request_id='public-legacy-arm-1', obligation_id='guide'), PRODUCER)['intent']
    lrow = C._intent(W._tasks('public', root)['work'], legacy['id'])
    assert 'source_review_plan' not in lrow['production'] and 'source_subject' not in judged(s, legacy)['facts']
    tasks = W._tasks('public', root)
    lhand = C._handoff(root, 'public', tasks, tasks['work'], lrow, {'actor': 'dispatcher', 'origin': 'human'})
    assert 'source_review_plan_absent' in lhand and 'source_review_plan' not in lhand
    # a later committed effect of the commission moves the subject: the armed intent stops being READY on it
    made = D.candidate(root, 'public', {'grant_id': grant['id'], 'files': [_edit(s, 'src/answer.py', 'keep middle', 'keep middle moved')]}, PRODUCER)
    assert D.apply(root, 'public', {'candidate_id': made['candidate_id']}, PRODUCER)['ok']
    codes = {r['code'] for r in judged(s, armed)['reasons']}
    assert 'PRODUCTION_ADVANCED' in codes and 'SOURCE_SUBJECT_CHANGED' in codes


def test_old_complete_content_noop_does_not_invent_verified_edit_facts(source):
 s=source;original=(s['checkout']/'src/answer.py').read_text();c,basis,plan=make_plan(s,content=original)
 assert not next(i for i in plan['inputs'] if i['path']=='src/answer.py')['changed']
 assert D.review_plan_for_inputs(plan,{'src/answer.py':basis['pins']['src/answer.py']})['state']=='UNAVAILABLE'


def test_cumulative_subject_joins_explicitly_selected_prior_commission_production_with_provenance(source):
    """Root F1: two separately attributed commissions of ONE Work and original parent. Commission A (the opted-in native
    commission) changes guide.md and src/answer.py; the later, separately attributed production B (the plain grant)
    changes src/answer.py again. B's own subject no longer calls A's changes unchanged: its first preimage is
    CHANGED_BEFORE_SUBJECT and a carry pin of guide.md is CHANGED_SINCE_BASE. Explicitly selecting A joins its effects
    and chains with A's own attribution, without merging accounts or widening a write fence; own, foreign, empty and
    malformed ancestry refuse, and A's later production moves the joined subject."""
    from test_eigen_continuity_owner import PRODUCER, produce
    s = source; root = s['root']; checkout = s['checkout']
    grant_a, _account, _candidate_a = produce(s)
    assert grant_a['native_allowance']['commission_request_id'] != (s['grant'].get('native_allowance') or {}).get('commission_request_id')
    later = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'keep middle', 'keep middle second commission')])
    pins = {p: D._pin(checkout / p) for p in ['src/answer.py', 'evaluator.py', 'guide.md']}
    basis = D.prepare_review_basis(root, 'public', 'work', {'grant_id': s['grant']['id'], 'candidate_id': later['candidate_id']}, pins, door=s['door'])
    carry = {'schema': D.REVIEW_CARRY_SCHEMA, 'members': [{'path': 'guide.md', 'sha256': pins['guide.md']}, {'path': 'evaluator.py', 'sha256': pins['evaluator.py']}]}
    own = D.review_subject(root, 'public', 'work', basis, {'carry': carry})
    [answer] = own['changed_files']
    assert answer['path'] == 'src/answer.py' and answer['base_relation'] == 'CHANGED_BEFORE_SUBJECT'
    assert {m['path']: m['relation'] for m in own['readonly_carry']['members']} == {'guide.md': 'CHANGED_SINCE_BASE', 'evaluator.py': 'UNCHANGED_CARRY'}
    assert 'prior_production' not in own and own['union']['effects'] == 1 and own['base_relation']['declared'] is False
    joined = D.review_subject(root, 'public', 'work', basis, {'carry': carry, 'prior': {'grants': [grant_a['id']]}})
    by_path = {row['path']: row for row in joined['changed_files']}
    assert sorted(by_path) == ['guide.md', 'src/answer.py'] and joined['union']['effects'] == 3
    assert [link['grant_id'] for link in by_path['src/answer.py']['effects']] == [grant_a['id'], s['grant']['id']]
    assert by_path['src/answer.py']['chain_continuous'] and by_path['src/answer.py']['base_relation'] == 'PREIMAGE_AT_BASE'
    assert by_path['guide.md']['base_relation'] == 'PREIMAGE_AT_BASE'
    assert {m['path']: m['relation'] for m in joined['readonly_carry']['members']} == {'guide.md': 'COMMISSION_POSTIMAGE', 'evaluator.py': 'UNCHANGED_CARRY'}
    prior = joined['prior_production']
    assert [g['id'] for g in prior['grants']] == [grant_a['id']]
    assert prior['grants'][0]['commission_request_id'] == grant_a['native_allowance']['commission_request_id'] and len(prior['effects']) == 2
    assert joined['union']['prior_grants'] == 1 and joined['commission']['grants'] == own['commission']['grants']
    assert D.validate_review_subject(root, 'public', 'work', basis, joined)['status'] == 'CURRENT'
    assert D._latest(W._tasks('public', root)['work'], 'grant', s['grant']['id'])['paths'] == s['grant']['paths']   # no widened fence
    for bad, match in (({'grants': [s['grant']['id']]}, 'already belongs'), ({'grants': ['DG-' + '0' * 24]}, 'foreign ancestry'),
                       ({'grants': []}, 'prior is'), ({'grants': [grant_a['id'], grant_a['id']]}, 'prior is'), ({'grant': [grant_a['id']]}, 'prior is')):
        with pytest.raises(ValueError, match=match):
            D.review_subject(root, 'public', 'work', basis, {'prior': bad})
    with pytest.raises(ValueError, match='not a readable commit'):
        D.review_subject(root, 'public', 'work', basis, {'prior': {'grants': [grant_a['id']]}, 'accepted_base': '0' * 40})
    made = D.candidate(root, 'public', {'grant_id': grant_a['id'], 'files': [
        _edit(s, 'guide.md', 'Public continuity documentation.', 'Public continuity documentation moved.')]}, PRODUCER)
    assert D.apply(root, 'public', {'candidate_id': made['candidate_id']}, PRODUCER)['ok']
    assert D.validate_review_subject(root, 'public', 'work', basis, joined)['status'] == 'CHANGED'


def test_bounded_review_request_keeps_scope_upfront_and_pages_every_omitted_carry_member(source):
    """Root F2: the COMPLETE rendered reviewer request has an explicit byte ceiling. A real handoff admits a read-only
    carry of the declared maximum member count; its full rendering exceeds the ceiling, so the request is re-rendered
    bounded: purpose, question, subject identity, stage, brief and evidence stay upfront, and every omitted carry member
    is reached by following the exact owner-issued continuation pages, in recorded order, each page byte-bounded."""
    from laplace.work import project_work_review as R, work_delivery as WD, project_work_continuity as C
    from laplace.work.owner_discovery import project_scope
    s = source; root = s['root']; checkout = s['checkout']
    scope = project_scope('public', 'native')
    (checkout / 'carry').mkdir()
    members = []
    for index in range(D.MAX_DEPENDENCY_MANIFEST_MEMBERS):
        path = checkout / ('carry/held-%04d.md' % index); path.write_text('held carry %d\n' % index)
        members.append({'path': 'carry/held-%04d.md' % index, 'sha256': D._pin(path)})
    latest = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'unique old', 'bounded change')])
    pins = {p: D._pin(checkout / p) for p in ['src/answer.py', 'evaluator.py', 'guide.md']}
    stage = {'id': 'pre-source-bootstrap', 'pre_source_review': ['External guarded functional proof.'], 'post_adoption': ['Ordinary app Source check.']}
    evidence = root / 'research/functional.json'; evidence.parent.mkdir(parents=True, exist_ok=True); evidence.write_text('functional')
    request = {'id': 'work', 'phase': 'handoff', 'request_id': 'bounded-handoff-0001',
               'expected_work_revision': W._task_revision(W._tasks('public', root)['work']),
               'source_basis': {'grant_id': s['grant']['id'], 'candidate_id': latest['candidate_id']}, 'pins': pins, 'obligations': ['source', 'guide'],
               'source_context': {'windows': _full_windows(s, pins)},
               'source_subject': {'carry': {'schema': D.REVIEW_CARRY_SCHEMA, 'members': members}, 'stage': stage},
               'summary': 'Bounded closure handoff: one change and the whole admitted carry.',
               'evidence': [{'path': 'research/functional.json', 'sha256': sha('functional')}]}
    handoff = R.record('public', request, root, door=s['door'])['phase']
    plan = handoff['source_review_plan']; subject = plan['review_subject']
    task = W._tasks('public', root)['work']
    intent = {'id': 'WD-bounded-request', 'obligation_id': 'source', 'handoff_id': handoff['id'], 'work_scope_revision': 'scope',
              'recipient': {'id': s['binding']['id'], 'revision': s['binding']['revision']},
              'source_basis': handoff['source_basis'], 'source_review_plan': plan}
    assert len(WD._render_request(task, intent, handoff, root).encode('utf-8')) > WD.MAX_REVIEW_REQUEST_BYTES   # the received F2 defect
    text = WD._request_text(task, intent, handoff, root)
    assert len(text.encode('utf-8')) <= WD.MAX_REVIEW_REQUEST_BYTES
    lines = text.split('\n')
    at = lambda prefix: next(i for i, line in enumerate(lines) if line.startswith(prefix))
    assert at('Purpose: ') < at('Review question: ') < at('WHOLE REVIEW SUBJECT ' + subject['subject_id']) < at('Acceptance stage pre-source-bootstrap')
    assert at('Handoff summary (bounded): Bounded closure handoff') < at('Handoff evidence') < at('Commission change inventory')
    assert 'research/functional.json' in lines[at('Handoff evidence')]
    for prefix in ('Bounded request: ', 'Exact qualified handoff read: ', 'Consumed inputs, compact', 'Bounded initial reads;'):
        assert any(line.startswith(prefix) for line in lines), prefix
    carry_line = lines[at('Carry members [path, pin, relation] (bounded: showing ')]
    shown = int(carry_line.split('showing ', 1)[1].split(' of ', 1)[0])
    assert 0 < shown < len(members) and ' of %d)' % len(members) in carry_line
    collected = [[row['path'], row['sha256'], row['relation']] for row in subject['readonly_carry']['members']][:shown]
    handle = json.loads(carry_line.split("following each page's next: ", 1)[1])
    pages = 0
    while handle is not None:
        page = C.read(root, scope, 'public', 'work', handle['payload']['request'])
        assert page['part'] == 'subject' and page['review_subject_id'] == subject['subject_id'] and page['offset'] == len(collected)
        assert len(json.dumps(page['items'], sort_keys=True).encode('utf-8')) <= C.SUBJECT_PAGE_BYTES
        collected.extend([row['path'], row['sha256'], row['relation']] for row in page['items'])
        handle, pages = page['next'], pages + 1
    assert pages > 1 and collected == [[m['path'], m['sha256'], 'ADDED_SINCE_BASE'] for m in sorted(members, key=lambda m: m['path'])]
    hunks = C.read(root, scope, 'public', 'work', {'part': 'subject', 'payload': {'phase_id': handoff['id'], 'section': 'hunks', 'path': 'src/answer.py'}})
    assert hunks['items'] == next(r for r in subject['changed_files'] if r['path'] == 'src/answer.py')['geometry']['hunks'] and hunks['next'] is None
    reads = C.read(root, scope, 'public', 'work', {'part': 'subject', 'payload': {'phase_id': handoff['id'], 'section': 'initial_reads', 'obligation_id': 'source'}})
    planned = D.review_plan_for_inputs(plan, WD._source_consumed_pins(task, intent, handoff))
    assert reads['returned'] and reads['items'] == [WD.native_initial_read(r) for i in planned['inputs'] for r in i['initial_reads']][:reads['returned']]
    for bad in ({'phase_id': handoff['id'], 'section': 'hunks'}, {'phase_id': handoff['id'], 'section': 'inputs'},
                {'phase_id': 'PHASE-unknown', 'section': 'effects'}, {'phase_id': handoff['id'], 'section': 'other'}):
        with pytest.raises(ValueError):
            C.read(root, scope, 'public', 'work', {'part': 'subject', 'payload': bad})


def test_bounded_listing_of_repeated_hunk_geometry_keeps_order_count_and_exact_continuation():
    """Repeated geometry at the bound (2,048 synthetic hunk rows; unit level): a bounded list renders the exact leading
    prefix within its share, the omitted count and the caller's exact continuation at that offset; unbounded is unchanged."""
    from laplace.work import work_delivery as WD
    rows = [{'id': 'hunk-%d' % (i + 1), 'tag': 'replace', 'before_lines': [2 * i + 1, 2 * i + 1], 'after_lines': [2 * i + 1, 2 * i + 1]}
            for i in range(2048)]
    seen = []
    line = WD._listing('Cumulative hunks', rows, 4000, lambda section, offset: seen.append((section, offset)) or {'section': section, 'offset': offset}, 'hunks')
    shown = WD._fit(rows, 4000)
    assert 0 < len(shown) < len(rows) and seen == [('hunks', len(shown))] and shown == rows[:len(shown)]
    assert '(bounded: showing %d of 2048)' % len(shown) in line and json.dumps(shown, sort_keys=True) in line and len(line.encode('utf-8')) < 4600
    assert WD._listing('All', rows[:3], None, None, 'hunks') == 'All: ' + json.dumps(rows[:3], sort_keys=True)


def test_bounded_review_request_fits_maximal_valid_upfront_fields_with_a_maximal_carry(source):
    """F2 boundary (the reported upfront-share caveat), on real owners: every upfront field at its declared maximum (16
    criteria of the maximum length in each stage list, the maximum authority references, the maximum stage summary, the
    maximum handoff summary and evidence rows) together with a carry of the maximum member count. The full rendering
    exceeds the ceiling; the bounded request still fits, keeps every criterion, both summaries and every evidence path
    verbatim upfront, and pages the carry. No valid maximal input is refused or silently cut."""
    from laplace.work import project_work_review as R, work_delivery as WD
    s = source; root = s['root']; checkout = s['checkout']
    (checkout / 'carry').mkdir()
    members = []
    for index in range(D.MAX_DEPENDENCY_MANIFEST_MEMBERS):
        path = checkout / ('carry/held-%04d.md' % index); path.write_text('held carry %d\n' % index)
        members.append({'path': 'carry/held-%04d.md' % index, 'sha256': D._pin(path)})
    latest = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'unique old', 'boundary change')])
    pins = {p: D._pin(checkout / p) for p in ['src/answer.py', 'evaluator.py', 'guide.md']}
    criterion = lambda tag, n: (tag + ' criterion %02d: ' % n + 'x' * D.MAX_STAGE_TEXT)[:D.MAX_STAGE_TEXT]
    evidence = []
    for n in range(R.MAX_EVIDENCE):
        target = root / ('research/boundary-%d.json' % n); target.parent.mkdir(parents=True, exist_ok=True); target.write_text('boundary %d' % n)
        evidence.append({'path': 'research/boundary-%d.json' % n, 'sha256': sha('boundary %d' % n)})
    stage = {'id': 'pre-source-bootstrap', 'pre_source_review': [criterion('now', n) for n in range(D.MAX_STAGE_CRITERIA)],
             'post_adoption': [criterion('later', n) for n in range(D.MAX_STAGE_CRITERIA)],
             'authority': evidence[:D.MAX_STAGE_AUTHORITY], 'summary': 's' * D.MAX_STAGE_SUMMARY}
    brief = 'B' * R.MAX_TEXT
    request = {'id': 'work', 'phase': 'handoff', 'request_id': 'boundary-handoff-0001',
               'expected_work_revision': W._task_revision(W._tasks('public', root)['work']),
               'source_basis': {'grant_id': s['grant']['id'], 'candidate_id': latest['candidate_id']}, 'pins': pins, 'obligations': ['source', 'guide'],
               'source_context': {'windows': _full_windows(s, pins)},
               'source_subject': {'carry': {'schema': D.REVIEW_CARRY_SCHEMA, 'members': members}, 'stage': stage},
               'summary': brief, 'evidence': evidence}
    handoff = R.record('public', request, root, door=s['door'])['phase']
    plan = handoff['source_review_plan']
    task = W._tasks('public', root)['work']
    intent = {'id': 'WD-boundary-request', 'obligation_id': 'source', 'handoff_id': handoff['id'], 'work_scope_revision': 'scope',
              'recipient': {'id': s['binding']['id'], 'revision': s['binding']['revision']},
              'source_basis': handoff['source_basis'], 'source_review_plan': plan}
    assert len(WD._render_request(task, intent, handoff, root).encode('utf-8')) > WD.MAX_REVIEW_REQUEST_BYTES
    text = WD._request_text(task, intent, handoff, root)
    assert len(text.encode('utf-8')) <= WD.MAX_REVIEW_REQUEST_BYTES
    for item in stage['pre_source_review'] + stage['post_adoption']:
        assert item in text
    assert stage['summary'] in text and brief in text and all(row['path'] in text for row in evidence)
    assert 'Carry members [path, pin, relation] (bounded: showing ' in text and "following each page's next: " in text


def test_default_delivery_status_never_copies_the_whole_plan_and_pages_every_section(source):
    """Root causal case RW-20261103-111139-631665: delivery status copied the whole recorded plan into each event (a
    450-620K single line). The default event now carries the owner summary and NOT_EXPANDED exact subject-page
    continuations; the immutable plan on the intent and handoff is unchanged and every section is reached by pages."""
    from laplace.work import project_work_review as R, work_delivery as WD, project_work_continuity as C
    from laplace.work.owner_discovery import project_scope
    s = source; root = s['root']; checkout = s['checkout']
    scope = project_scope('public', 'native')
    (checkout / 'carry').mkdir()
    members = []
    for index in range(D.MAX_DEPENDENCY_MANIFEST_MEMBERS):
        path = checkout / ('carry/held-%04d.md' % index); path.write_text('held carry %d\n' % index)
        members.append({'path': 'carry/held-%04d.md' % index, 'sha256': D._pin(path)})
    latest = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'unique old', 'status change')])
    pins = {p: D._pin(checkout / p) for p in ['src/answer.py', 'evaluator.py', 'guide.md']}
    stage = {'id': 'pre-source-bootstrap', 'pre_source_review': ['External guarded functional proof.'], 'post_adoption': ['Ordinary app Source check.']}
    request = {'id': 'work', 'phase': 'handoff', 'request_id': 'status-header-handoff-0001',
               'expected_work_revision': W._task_revision(W._tasks('public', root)['work']),
               'source_basis': {'grant_id': s['grant']['id'], 'candidate_id': latest['candidate_id']}, 'pins': pins, 'obligations': ['source', 'guide'],
               'source_context': {'windows': _full_windows(s, pins)},
               'source_subject': {'carry': {'schema': D.REVIEW_CARRY_SCHEMA, 'members': members}, 'stage': stage},
               'summary': 'Status header handoff: one change and the whole admitted carry.'}
    handoff = R.record('public', request, root, door=s['door'])['phase']
    plan = handoff['source_review_plan']; subject = plan['review_subject']
    task = W._tasks('public', root)['work']
    intent = {'id': 'WD-status-header', 'obligation_id': 'source', 'handoff_id': handoff['id'], 'source_review_plan': plan}
    original = copy.deepcopy(intent)
    header = WD.plan_reads('public', task, intent)
    size = len(json.dumps(header, sort_keys=True).encode('utf-8'))
    assert len(json.dumps(plan, sort_keys=True).encode('utf-8')) > 10 * size and size < 8192
    assert intent == original and next(r for r in task['phases'] if r['id'] == handoff['id'])['source_review_plan'] == plan
    assert header['state'] == 'NOT_EXPANDED' and header['plan_id'] == plan['plan_id'] and header['review_subject_id'] == subject['subject_id']
    assert set(header['sections']) == set(WD.PLAN_READ_SECTIONS)
    collected, handle = [], header['sections']['readonly_carry']
    while handle is not None:
        page = C.read(root, scope, 'public', 'work', handle['payload']['request'])
        assert page['review_subject_id'] == subject['subject_id'] and page['offset'] == len(collected)
        assert len(json.dumps(page['items'], sort_keys=True).encode('utf-8')) <= C.SUBJECT_PAGE_BYTES
        collected.extend(page['items']); handle = page['next']
    assert collected == subject['readonly_carry']['members']
    for section in ('changed_files', 'effects', 'inputs', 'initial_reads'):
        page = C.read(root, scope, 'public', 'work', header['sections'][section]['payload']['request'])
        assert page['section'] == section and page['review_subject_id'] == subject['subject_id'] and page['offset'] == 0
    legacy = WD.plan_reads('public', task, {**intent, 'source_review_plan': {k: v for k, v in plan.items() if k != 'review_subject'}})
    assert legacy['state'] == 'NOT_EXPANDED' and legacy['sections'] is None and legacy['review_subject_id'] is None
    # Durable closeout header from existing records: handoff recorded, review missing; adoption/live/publication not inferred.
    before = W._ledger(root).read_bytes()
    summary = C.read(root, scope, 'public', 'work', {'part': 'summary'})
    head = summary['closeout']
    assert head['handoff'] == handoff['id'] and head['reviews'] == [] and head['synthesis'] is None and head['missing_next'] == 'review'
    assert {head[key] for key in ('adoption', 'live', 'publication')} == {'NOT_RECORDED'} and head['work']['status'] == summary['standing']['status']
    assert set(summary['production']['checks']['cleanup']) <= {'REMOVED', 'RETAINED', 'FAILED', 'ABSENT', 'UNKNOWN'}
    assert W._ledger(root).read_bytes() == before   # observing the closeout executes and records nothing


def test_subject_pages_fit_the_whole_composed_envelope_on_every_door_and_descend_exactly(source, request):
    """Root deployed-acceptance HOLD: the actual ordinary native read of handoff PHASE-cbf4401c, section changed_files, offset 0
    (request fde16099..., response c9ce39ed...) returned 21/21 rows with next null and delivery_bound {bound 30000, emitted
    37165, exceeded true}, because subject_page fitted only json.dumps(items) to 48KiB. On real owners (a 600-member escaped-
    Unicode carry spanning many whole lines, a 24-effect chain on one file and every subject section) the WHOLE composed continuity response now fits
    the shared line through owner, native and HTTP doors; pages are ordered, contiguous and cut-pinned; a row too large for a
    reduced line is a NOT_EXPANDED header whose detail_read reassembles its exact canonical JSON; replay is stable and a
    changed cut, a foreign phase, a past-end row and a stale row pin refuse with the exact restart."""
    from urllib.parse import urlsplit, parse_qs
    from laplace.work import project_work_review as R, work_delivery as WD, project_work_continuity as C
    from laplace.work.owner_discovery import project_scope
    from laplace.native import tools
    from laplace.web import project_work_surface
    from laplace.writing import delivery
    import shutil
    s = source; root = s['root']; checkout = s['checkout']
    request.addfinalizer(lambda: shutil.rmtree(root.parent, ignore_errors=True))   # the shared check scratch stays bounded
    scope = project_scope('public', 'native')
    (checkout / 'carry').mkdir()
    members = []
    for index in range(600):   # bounded scratch: the escaped carry still spans many whole lines
        name = 'carry/ü€𝔘-%04d-%s.md' % (index, 'ж' * 24)
        path = checkout / name; path.write_text('held carry %d\n' % index)
        members.append({'path': name, 'sha256': D._pin(path)})
    previous, latest = 'unique old', None
    for step in range(24):   # one long effect chain: the src/answer.py changed_files row grows with every recorded effect link
        latest = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', previous, 'unique step %d' % (step + 1))])
        previous = 'unique step %d' % (step + 1)
    # The reached deployed shape (PHASE-cbf4401c changed_files: 21 rows, several effect links each): 20 more source files,
    # created and then edited twice by multi-file candidates, beside the long-chain src/answer.py.
    added = ['src/module_%02d.py' % n for n in range(20)]
    _apply(s, s['grant']['id'], [{'path': p, 'before_sha256': None, 'content': 'value = 0\n'} for p in added])
    for step in (1, 2):
        latest = _apply(s, s['grant']['id'], [_edit(s, p, 'value = %d' % (step - 1), 'value = %d' % step) for p in added])
    pins = {p: D._pin(checkout / p) for p in ['src/answer.py', 'evaluator.py', 'guide.md'] + added}
    stage = {'id': 'pre-source-bootstrap', 'pre_source_review': ['External guarded functional proof.'], 'post_adoption': ['Ordinary app Source check.']}
    recorded = {'id': 'work', 'phase': 'handoff', 'request_id': 'envelope-handoff-0001',
               'expected_work_revision': W._task_revision(W._tasks('public', root)['work']),
               'source_basis': {'grant_id': s['grant']['id'], 'candidate_id': latest['candidate_id']}, 'pins': pins, 'obligations': ['source', 'guide'],
               'source_context': {'windows': _full_windows(s, pins)},
               'source_subject': {'carry': {'schema': D.REVIEW_CARRY_SCHEMA, 'members': members}, 'stage': stage},
               'summary': 'Envelope handoff: a long effect chain and the whole admitted escaped-Unicode carry.'}
    handoff = R.record('public', recorded, root, door=s['door'])['phase']
    plan = handoff['source_review_plan']; subject = plan['review_subject']; hid = handoff['id']
    task = W._tasks('public', root)['work']
    assert len(next(r for r in subject['changed_files'] if r['path'] == 'src/answer.py')['effects']) >= 24
    reached = C.subject_rows(plan, 'changed_files')
    assert sorted(row['path'] for row in reached) == sorted(['src/answer.py'] + added) and len(reached) == 21
    # the received regime: the 21 rows alone exceed the declared 30000 line, so one whole page cannot carry them
    assert len(json.dumps(reached, sort_keys=True).encode('utf-8')) > 30000
    first_page = C.read(root, scope, 'public', 'work', C.subject_page_handle('public', 'work', hid, 'changed_files', 0)['payload']['request'])
    assert 0 < first_page['returned'] < 21 and first_page['total'] == 21 and first_page['next'] is not None and D._encoded(first_page) <= 30000
    projected = D.review_plan_for_inputs(plan, WD._source_consumed_pins(task, {'obligation_id': 'source'}, handoff))
    hunk_read = lambda path: C.subject_page_handle('public', 'work', hid, 'hunks', 0, path=path)
    sections = {('changed_files', None, None): C.subject_rows(plan, 'changed_files'),
                ('hunks', 'src/answer.py', None): C.subject_rows(plan, 'hunks', 'src/answer.py'),
                ('readonly_carry', None, None): subject['readonly_carry']['members'], ('effects', None, None): subject['effects'],
                ('inputs', None, 'source'): C.subject_rows(projected, 'inputs', hunk_read=hunk_read),
                ('initial_reads', None, 'source'): C.subject_rows(projected, 'initial_reads')}
    assert all(sections.values()) and len(json.dumps(sections[('readonly_carry', None, None)]).encode('utf-8')) > 4 * 30000
    before = W._ledger(root).read_bytes()

    def owner(h, line=30000):
        page = C.read(root, scope, 'public', 'work', h['payload']['request'])
        assert page['schema_version'] == C.SCHEMA and page['part'] == 'subject' and D._encoded(page) <= line, D._encoded(page)
        return page

    def native(h):
        page = tools.execute(root, 'public', 'work', h['operation'], h['payload'], turn_id='WT-parent')
        assert delivery.emitted(page) <= 30000 and not (page.get('delivery_bound') or {}).get('exceeded'), (page.get('error'), page.get('delivery_bound'))
        return page

    def http(h):
        target = h['http']; url = urlsplit(target['url'])
        body = json.dumps(target['payload']).encode() if target.get('payload') is not None else b''
        code, _, raw = project_work_surface.handle(url.path, parse_qs(url.query), target['method'], body, root)
        assert code == 200 and len(raw) <= 30000, (code, len(raw), raw[:300])
        return json.loads(raw)

    def traverse(read, first):
        collected, issued, pages, headers = [], first, 0, 0
        while issued is not None:
            page = read(issued); pages += 1
            assert page['review_subject_id'] == subject['subject_id'] and page['offset'] == len(collected) and page['total'] == len(rows)
            assert page['items'] and page['returned'] == len(page['items']) or not rows   # every page advances
            for item in page['items']:
                if item.get('expanded') is False:
                    headers += 1
                    text, part = '', item['detail_read']
                    while part is not None:
                        body = read(part); got = body['item']
                        assert got['offset'] == len(text) and got['row_sha256'] == item['row_sha256'] and got['index'] == len(collected)
                        assert got['end_offset'] > got['offset'] or got['eof']
                        text += got['content']; part = got['next_read']
                        if part is None:
                            assert got['eof'] and body['next'] == page['next']   # the last row page continues the section
                    assert 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest() == item['row_sha256'] and len(text) == item['row_chars']
                    collected.append(json.loads(text))
                else:
                    collected.append(item)
            issued = page['next']
            assert issued is None or issued['payload']['request']['payload']['cut'] == page['cut']
        return collected, pages, headers

    for (section, path, obligation), rows in sections.items():
        first = C.subject_page_handle('public', 'work', hid, section, 0, path=path, obligation_id=obligation)
        for read in (owner, native, http):
            collected, pages, _headers = traverse(read, first)
            assert json.loads(json.dumps(collected)) == json.loads(json.dumps(rows)), (section, read.__name__)   # each row once, in order
            if section == 'readonly_carry':
                assert pages > 4
        assert owner(first) == owner(first)   # stable replay
    # a reduced planned line: smaller truthful pages, and the long-chain row alone exceeds it, so it descends exactly
    rows = sections[('changed_files', None, None)]
    with delivery.planned(line=4000) as plan_line:
        collected, pages, headers = traverse(lambda h: owner(h, 4000), C.subject_page_handle('public', 'work', hid, 'changed_files', 0))
    assert collected == rows and headers >= 1 and plan_line['projection']['subject']
    # exact end, past end, a changed cut, a stale row pin and a foreign phase refuse; nothing is recorded
    total = len(sections[('effects', None, None)])
    end = owner(C.subject_page_handle('public', 'work', hid, 'effects', total))
    assert end['items'] == [] and end['next'] is None and end['returned'] == 0
    restart = C.subject_page_handle('public', 'work', hid, 'effects', 0)['payload']['request']
    for bad, field in (({'offset': total + 1}, 'offset'), ({'offset': 1, 'cut': 'sha256:' + '0' * 64}, 'cut'),
                       ({'offset': 0, 'item_sha256': 'sha256:' + '1' * 64, 'item_offset': 0}, 'item_sha256')):
        with pytest.raises(W.WorkConflict) as refused:
            C.read(root, scope, 'public', 'work', {'part': 'subject', 'payload': {'phase_id': hid, 'section': 'effects', **bad}})
        assert refused.value.details['field'] == field and refused.value.details['restart_read']['payload']['request'] == restart
        with pytest.raises(W.WorkConflict) as native_refused:   # the actual native route raises the same typed owner refusal
            tools.execute(root, 'public', 'work', 'project', {'namespace': 'public', 'view': 'continuity', 'id': 'work',
                          'request': {'part': 'subject', 'payload': {'phase_id': hid, 'section': 'effects', **bad}}}, turn_id='WT-parent')
        assert native_refused.value.details['field'] == field and native_refused.value.details['restart_read']['payload']['request'] == restart
    for bad in ({'phase_id': 'PHASE-foreign', 'section': 'effects'}, {'phase_id': hid, 'section': 'effects', 'item_offset': 0},
                {'phase_id': hid, 'section': 'effects', 'cut': 'not-a-pin'}):
        with pytest.raises(ValueError):
            C.read(root, scope, 'public', 'work', {'part': 'subject', 'payload': bad})
    assert W._ledger(root).read_bytes() == before


def test_malformed_manifest_carriers_are_diagnosed_by_role_before_any_artifact_lookup(source, monkeypatch):
    """Causal case activation-002: source_subject.carry.files was diagnosed as 'dependency Artifact None'. The one shared
    role-qualified carrier diagnosis names role, field, received keys, both accepted forms and coordinates BEFORE any
    Artifact lookup; both valid forms pass the shape step for both roles; nothing is recorded."""
    from laplace.writing.records import _index
    s = source; root = s['root']; checkout = s['checkout']
    latest = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'unique old', 'carrier change')])
    pins = {p: D._pin(checkout / p) for p in ['src/answer.py', 'evaluator.py', 'guide.md']}
    basis = D.prepare_review_basis(root, 'public', 'work', {'grant_id': s['grant']['id'], 'candidate_id': latest['candidate_id']}, pins, door=s['door'])
    inline = {'schema': D.REVIEW_CARRY_SCHEMA, 'members': [{'path': 'evaluator.py', 'sha256': pins['evaluator.py']}]}
    assert D.review_subject(root, 'public', 'work', basis, {'carry': inline})['readonly_carry']['members'][0]['path'] == 'evaluator.py'
    looked = []
    real = _index.artifact_record
    monkeypatch.setattr(_index, 'artifact_record', lambda *a, **k: looked.append(a) or real(*a, **k))
    before = W._ledger(root).read_bytes()
    with pytest.raises(ValueError) as caught:
        D.review_subject(root, 'public', 'work', basis, {'carry': {'files': {'evaluator.py': pins['evaluator.py']}}})
    text = str(caught.value)
    assert 'review carry manifest' in text and 'source_subject.carry' in text and "['files']" in text
    assert 'artifact_id' in text and 'members' in text and 'Artifact None' not in text and len(text) < 2000
    assert looked == [] and W._ledger(root).read_bytes() == before
    reference = {'artifact_id': 'ART-public', 'expected_sha256': '0' * 64}
    for role in ('check-dependency', 'review-carry'):
        assert D.manifest_carrier_shape(inline, role) is None and D.manifest_carrier_shape(reference, role) is None
        for bad in ({'files': {}}, {'artifact_id': None, 'expected_sha256': '0' * 64}, ['evaluator.py'], {'artifact_id': 'ART-x', 'members': []}):
            problem = D.manifest_carrier_shape(bad, role)
            assert problem['role'] == role and problem['field'] == D.MANIFEST_CARRIER_ROLES[role][0] and len(json.dumps(problem)) < 2000
    assert D.manifest_carrier_shape({'files': {}}, 'check-dependency')['field'] == 'checks.<name>.dependency_manifest'
    with pytest.raises(ValueError, match='not a project Artifact'):
        D.review_subject(root, 'public', 'work', basis, {'carry': reference})
    assert looked   # a well-shaped reference still reaches the Artifact owner and refuses there
    with pytest.raises(ValueError) as unknown:
        D.review_subject(root, 'public', 'work', basis, {'carry': reference})
    assert 'review carry manifest Artifact ART-public' in str(unknown.value) and 'dependency manifest' not in str(unknown.value)


def test_large_phase_read_is_a_bounded_header_with_exact_pinned_body_pages(source):
    """Root goal item 2/3 (the ~230 KB handoff phase): a guarded phase read of a large recorded phase returns a bounded
    semantic header and exact canonical-JSON body pages pinned to phase_revision. The pages reassemble to the stored rows
    byte for byte; each whole page fits the project line; a changed revision and an out-of-range offset refuse."""
    from laplace.work import project_work_review as R, project_work_views as V
    s = source; root = s['root']; checkout = s['checkout']
    (checkout / 'carry').mkdir()
    members = []
    for index in range(512):   # far above the inline phase budget; small enough for the check's bounded scratch
        path = checkout / ('carry/held-%04d.md' % index); path.write_text('held carry %d\n' % index)
        members.append({'path': 'carry/held-%04d.md' % index, 'sha256': D._pin(path)})
    latest = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'unique old', 'phase header change')])
    pins = {p: D._pin(checkout / p) for p in ['src/answer.py', 'evaluator.py', 'guide.md']}
    stage = {'id': 'pre-source-bootstrap', 'pre_source_review': ['External guarded functional proof.'], 'post_adoption': ['Ordinary app Source check.']}
    request = {'id': 'work', 'phase': 'handoff', 'request_id': 'phase-header-handoff-0001',
               'expected_work_revision': W._task_revision(W._tasks('public', root)['work']),
               'source_basis': {'grant_id': s['grant']['id'], 'candidate_id': latest['candidate_id']}, 'pins': pins, 'obligations': ['source', 'guide'],
               'source_context': {'windows': _full_windows(s, pins)},
               'source_subject': {'carry': {'schema': D.REVIEW_CARRY_SCHEMA, 'members': members}, 'stage': stage},
               'summary': 'Phase header handoff: é "quoted" \\ and the whole admitted carry.'}
    handoff = R.record('public', request, root, door=s['door'])['phase']
    recorded = [row for row in W._tasks('public', root)['work']['phases'] if row['id'] == handoff['id']]
    from laplace.work.owner_discovery import project_scope
    scope = project_scope('public', 'native')   # a guarded phase read needs the actual admitted caller Scope
    first = V.read('public', {'view': 'review', 'id': 'work', 'phase_id': handoff['id']}, root, native_caller=scope)
    phase = first['phase']
    assert phase['rows'] is None and phase['rows_state'] == 'NOT_EXPANDED' and [h['id'] for h in phase['header']] == [handoff['id']]
    assert phase['header'][0]['source_review_plan']['plan_id'] == handoff['source_review_plan']['plan_id'] and phase['header'][0]['pins'] == 3
    assert len(json.dumps(first).encode('utf-8')) <= 30000
    body, handle, pages = '', phase['body']['page_read'], 0
    while handle is not None:
        page = V.read('public', handle['payload'], root, native_caller=scope)
        assert len(json.dumps(page).encode('utf-8')) <= 30000 and page['phase']['body']['offset'] == len(body)
        assert page['phase']['revision'] == phase['revision'] and page['phase']['body']['end_offset'] > page['phase']['body']['offset']
        body += page['phase']['body']['content']; handle = page['phase']['body']['next_read']; pages += 1
    assert pages > 1 and json.loads(body) == recorded and 'sha256:' + hashlib.sha256(body.encode('utf-8')).hexdigest() == phase['body']['sha256']
    with pytest.raises(Exception, match='changed since it was read'):
        V.read('public', {**phase['body']['page_read']['payload'], 'phase_revision': 'sha256:' + '0' * 64}, root, native_caller=scope)
    with pytest.raises(ValueError, match='beyond'):
        V.read('public', {**phase['body']['page_read']['payload'], 'offset': phase['body']['chars'] + 1}, root, native_caller=scope)
    with pytest.raises(ValueError, match='actual admitted caller scope'):
        V.read('public', phase['body']['page_read']['payload'], root)   # no label-only or missing caller reads a guarded page
    # The native recording and replay acknowledgements of a large whole-subject handoff are bounded headers with the exact
    # phase read; the stored row stays whole; a small acknowledgement is returned unchanged.
    from laplace.native import tools
    from laplace.writing import delivery
    native_request = {**request, 'request_id': 'phase-header-handoff-native-0001',
                      'expected_work_revision': W._task_revision(W._tasks('public', root)['work'])}
    for status in ('RECORDED', 'REUSED'):
        ack = tools.execute(root, 'public', 'work', 'work_review', native_request, turn_id='WT-parent')
        assert ack['status'] == status and len(json.dumps(ack).encode('utf-8')) <= 30000, (ack.get('status'), len(json.dumps(ack)))
        assert ack['phase']['rows_state'] == 'NOT_EXPANDED' and ack['phase']['header']['source_review_plan']['plan_id']
        assert ack['phase']['read']['payload']['phase_revision'].startswith('sha256:') and 'detail_read' not in ack
    stored = [row for row in W._tasks('public', root)['work']['phases'] if row.get('request_id') == 'phase-header-handoff-native-0001']
    assert len(stored) == 1 and stored[0]['source_review_plan']['review_subject']['subject_id']
    # The same large acknowledgements through the HTTP /work/review door (human recording identity), then the issued
    # phase read reached through a review-mode native turn: a read, bounded, the header and the first exact body page.
    from laplace.web import project_work_surface
    http_request = {**request, 'project': 'public', 'request_id': 'phase-header-handoff-http-0001',
                    'expected_work_revision': W._task_revision(W._tasks('public', root)['work'])}
    for status in ('RECORDED', 'REUSED'):
        code, _, raw_body = project_work_surface.handle('/work/review', {}, 'POST', json.dumps(http_request).encode(), root)
        http_ack = json.loads(raw_body)
        assert code == 200 and len(raw_body) <= 30000 and http_ack['status'] == status, (code, http_ack.get('error'), len(raw_body))
        assert http_ack['phase']['rows_state'] == 'NOT_EXPANDED' and http_ack['phase']['header']['source_review_plan']['plan_id']
        assert http_ack['phase']['read']['payload']['phase_revision'].startswith('sha256:') and 'detail_read' not in http_ack
    issued = ack['phase']['read']
    reviewed = tools.execute(root, 'public', 'review', issued['operation'], issued['payload'], turn_id='WT-review')
    assert reviewed['phase']['rows_state'] == 'NOT_EXPANDED' and reviewed['phase']['body']['offset'] == 0, reviewed.get('error')
    assert not (reviewed.get('delivery_bound') or {}).get('exceeded') and delivery.emitted(reviewed) <= 30000
    small = {'status': 'RECORDED', 'phase': {'id': 'PHASE-small'}}
    assert R.bounded_ack('public', small) is small and delivery.profile('work_review', native_request)['bound'] >= 16000


from test_work_review_lifecycle import root as lifecycle_root  # noqa: E402  the existing public lifecycle Work fixture


@pytest.fixture
def held_lifecycle(lifecycle_root):
    return lifecycle_root


def test_closeout_next_and_held_follow_the_owner_decision_not_phase_presence(held_lifecycle):
    """C closeout: after a recorded HOLD the header must not report 'synthesis' merely because a review phase exists.
    missing_next/remaining/held come from the review owner's current facet; recorded verdicts stay history."""
    import test_work_review_lifecycle as L
    from laplace.work import project_work_continuity as C
    from laplace.work.owner_discovery import project_scope
    root = held_lifecycle
    first = L.handoff(root)
    L.reviewed(root, first['phase']['id'], 'source', verdict='HOLD', request='req-closeout-hold-0001',
               findings=[{'id': 'F1', 'summary': 'held for the closeout header'}])
    summary = C.read(root, project_scope(L.P, 'native'), L.P, 'parent', {'part': 'summary'})
    head = summary['closeout']
    assert head['reviews'][-1]['verdict'] == 'HOLD' and head['handoff'] == first['phase']['id'] and head['synthesis'] is None
    assert head['missing_next'] == summary['review']['next'] and head['missing_next'] != 'synthesis'
    assert head['remaining'] and head['held'] == [o['id'] for o in summary['review']['obligations'] if o['status'] == 'HOLD']
    assert head['latest_synthesis_covers_latest_handoff'] is False and head['review_required'] == 'REQUIRED'


def test_closeout_of_a_work_without_review_obligations_never_invents_a_handoff(source):
    """HOLD F3: a Work with no review obligations has no review cycle: missing_next is None and review_required is
    NOT_REQUIRED through the real continuity summary, never an invented 'handoff'; a managed row keeps the owner decision."""
    from laplace.work import project_work_continuity as C
    from laplace.work.owner_discovery import project_scope
    s = source; root = s['root']
    W.task('public', {'id': 'plain', 'title': 'Unreviewed public note', 'goal': 'No review is declared'}, root)
    plain = W._tasks('public', root)['plain']
    for row in ({'status': 'open'}, {'status': 'open', 'review': {}}, {'status': 'open', 'review': {'obligations': [], 'next': {'kind': 'handoff'}}}):
        head = C.closeout(plain, row)
        assert head['missing_next'] is None and head['review_required'] == 'NOT_REQUIRED' and head['handoff'] is None, row
    managed = C.closeout(plain, {'review': {'obligations': [{'id': 'source', 'status': 'AWAITING_HANDOFF'}], 'next': {'kind': 'handoff'}}})
    assert managed['missing_next'] == 'handoff' and managed['review_required'] == 'REQUIRED'
    summary = C.read(root, project_scope('public', 'native'), 'public', 'plain', {'part': 'summary'})
    assert summary['closeout']['missing_next'] is None and summary['closeout']['review_required'] == 'NOT_REQUIRED'


def test_preflight_without_paths_derives_the_whole_cumulative_subject(source):
    """Root causal case PHASE-7608dc0d: the producer named only its latest files and 21 of 22 inputs lacked context. With
    paths omitted the owner derives declared inputs, commission production and candidate files; its scaffold then makes
    the whole plan COMPLETE. Read-only, offered not observed; an explicit caller selection is kept as CALLER."""
    s = source; root = s['root']
    changed = candidate(s, edits=[{'old': 'unique old', 'new': 'new chosen'}])
    D.apply(root, 'public', {'candidate_id': changed['candidate_id']}, s['door'])
    request = {'work_id': 'work', 'grant_id': s['grant']['id'], 'candidate_id': changed['candidate_id']}
    before = W._ledger(root).read_bytes()
    bare = D.review_preflight(root, 'public', request, s['door'])
    assert W._ledger(root).read_bytes() == before
    task = W._tasks('public', root)['work']
    declared = {p for row in task.get('review_obligations') or () for p in row.get('inputs') or ()}
    assert bare['paths_origin'] == 'CUMULATIVE_SUBJECT' and 'src/answer.py' in bare['pins'] and declared <= set(bare['pins'])
    assert bare['state'] == 'INCOMPLETE' and bare['scaffold']['offered_not_observed'] and bare['scaffold']['within_bound']
    named = D.review_preflight(root, 'public', {**request, 'paths': ['src/answer.py']}, s['door'])
    assert named['paths_origin'] == 'CALLER' and set(named['pins']) == {'src/answer.py'}
    offered = D.review_preflight(root, 'public', {**request, 'source_context': {'windows': bare['scaffold']['windows']}}, s['door'])
    assert offered['state'] == 'COMPLETE' and offered['incomplete'] == [] and set(offered['pins']) == set(bare['pins'])
    assert W._ledger(root).read_bytes() == before
    assert bare['subject_geometry'] == 'COMMISSION' and bare['subject'] is None   # legacy absent subject unchanged


def test_preflight_offers_the_selected_subject_geometry_that_arm_validates_and_recovery_keeps_it(source):
    """Source5: two real commissions of one Work and original parent. Commission A makes a prior-only change beyond the
    80-line head window and both commissions change src/answer.py. With the explicit subject the preflight uses the ONE
    canonical review_subject geometry, its scaffold fed unchanged makes the arm's plan COMPLETE, the bare-commission
    scaffold does not, a refused subject is never a bare success, and recovery keeps the caller's own subject."""
    import json
    from test_eigen_continuity_owner import PRODUCER, produce, arm_payload
    from laplace.work import project_work_continuity as C
    s = source; root = s['root']; checkout = s['checkout']
    grant_a, _account, _candidate_a = produce(s)
    long = (checkout / 'guide.md').read_text() + ''.join('prior line %d\n' % n for n in range(120)) + 'prior-only tail\n'
    made = D.candidate(root, 'public', {'grant_id': grant_a['id'], 'files': [{'path': 'guide.md', 'before_sha256': D._pin(checkout / 'guide.md'), 'content': long}]}, PRODUCER)
    assert D.apply(root, 'public', {'candidate_id': made['candidate_id']}, PRODUCER)['ok']
    stage = {'id': 'pre-source-bootstrap', 'pre_source_review': ['External guarded functional proof.'], 'post_adoption': ['Ordinary app Source check.']}
    before = W._ledger(root).read_bytes()
    with pytest.raises(ValueError) as refused_arm:   # an incomplete selected context: recovery repeats the caller's subject
        D.handle(root, 'public', arm_payload(s, grant_a, made['candidate_id'], request_id='public-preflight-arm-1',
                 source_context={'windows': [{'path': 'src/answer.py', 'line_start': 1, 'line_end': 1}]}, source_subject={'stage': stage}), PRODUCER)
    assert 'nothing was armed' in str(refused_arm.value) and '"source_subject": {"stage": {"id": "pre-source-bootstrap"' in str(refused_arm.value)
    assert W._ledger(root).read_bytes() == before   # no intent, handoff or event
    later = _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'keep middle', 'keep middle second commission')])   # overlap
    request = {'work_id': 'work', 'grant_id': s['grant']['id'], 'candidate_id': later['candidate_id']}
    subject = {'prior': {'grants': [grant_a['id']]}}
    before = W._ledger(root).read_bytes()
    bare = D.review_preflight(root, 'public', request, s['door'])
    selected = D.review_preflight(root, 'public', {**request, 'source_subject': subject}, s['door'])
    assert W._ledger(root).read_bytes() == before
    assert bare['subject_geometry'] == 'COMMISSION' and selected['subject_geometry'] == 'SELECTED_SUBJECT' and selected['subject']['state'] == 'ADMISSIBLE'
    guide = lambda report: [(w['line_start'], w['line_end']) for w in report['scaffold']['windows'] if w['path'] == 'guide.md']
    assert max(end for _start, end in guide(selected)) > 80 and max(end for _start, end in guide(bare)) <= 80
    pins = selected['pins']
    basis = D.prepare_review_basis(root, 'public', 'work', {'grant_id': s['grant']['id'], 'candidate_id': later['candidate_id']}, pins, door=s['door'])
    plan = D.prepare_review_plan(root, 'public', 'work', basis, pins, {'windows': selected['scaffold']['windows']}, subject)
    assert plan['state'] == 'COMPLETE' and plan['review_subject']['subject_id'] == selected['subject']['summary']['subject_id']
    stale = D.prepare_review_plan(root, 'public', 'work', basis, pins, {'windows': bare['scaffold']['windows']}, subject)
    assert stale['state'] == 'INCOMPLETE'   # the bare commission scaffold misses the selected prior-only geometry
    refused = D.review_preflight(root, 'public', {**request, 'source_subject': {'prior': {'grants': ['DG-' + '0' * 24]}}}, s['door'])
    assert refused['subject']['state'] == 'REFUSED' and refused['state'] == 'UNAVAILABLE' and refused['subject_geometry'] == 'REFUSED_SUBJECT'
    assert refused['scaffold']['windows'] == [] and refused['scaffold']['withheld'].startswith('REFUSED_SUBJECT') and bare['scaffold']['windows']
    assert W._ledger(root).read_bytes() == before
    small = C.preflight_read('public', 'work', s['grant']['id'], later['candidate_id'], subject)
    assert small['payload']['source_subject'] == subject and small['http']['payload']['source_subject'] == subject and 'source_subject_reuse' not in small
    large_subject = {**subject, 'stage': {**stage, 'pre_source_review': ['x' * 590] * 8}}
    large = C.preflight_read('public', 'work', s['grant']['id'], later['candidate_id'], large_subject)
    assert 'source_subject' not in large['payload'] and large['source_subject_reuse']['state'] == 'REUSE_ORIGINAL'
    assert large['source_subject_reuse']['chars'] > C.PREFLIGHT_SUBJECT_INLINE_CHARS and len(json.dumps(large)) < 4 * C.PREFLIGHT_SUBJECT_INLINE_CHARS
    assert 'source_subject' not in C.preflight_read('public', 'work', s['grant']['id'], later['candidate_id'])['payload']
    # the inline bound is measured as actually emitted (ASCII-escaped): 300 astral characters are 3600 escaped characters
    astral = {**subject, 'stage': {**stage, 'pre_source_review': ['\U0001F600' * 300]}}
    assert len(json.dumps(astral, ensure_ascii=False)) < C.PREFLIGHT_SUBJECT_INLINE_CHARS < len(json.dumps(astral))
    escaped = C.preflight_read('public', 'work', s['grant']['id'], later['candidate_id'], astral)
    assert 'source_subject' not in escaped['payload'] and escaped['source_subject_reuse']['state'] == 'REUSE_ORIGINAL'
    held = C.preflight_read('public', 'work', s['grant']['id'], later['candidate_id'], astral, holder='retained')
    assert held['source_subject_reuse']['state'] == 'RETAINED_UNAVAILABLE' and 'source_subject' not in held['payload']
    odd = C.preflight_read('public', 'work', s['grant']['id'], later['candidate_id'], ['not', 'an', 'object'])
    assert odd['source_subject_reuse']['state'] == 'NOT_AN_OBJECT' and 'source_subject' not in odd['payload']
    for chosen in (subject, astral, large_subject, ['x']):   # the whole emitted recovery is one valid bounded machine JSON
        emitted = C._recovery_text('public', 'work', s['grant']['id'], later['candidate_id'], chosen)
        assert json.loads(emitted)['operation'] == 'development_source' and len(emitted) <= C.PREFLIGHT_SUBJECT_INLINE_CHARS + 900
        assert emitted.isascii()


def test_arm_refusal_and_its_recovery_fit_the_actual_failure_formatters_whole(source, monkeypatch):
    """Source6: the WHOLE arm refusal, not only its recovery JSON, fits the existing native failure formatter (it keeps
    str(error)[:4000]) and passes the HTTP error serializer unchanged. The caller's subject stays inline only while the whole
    refusal fits, otherwise the read is the truthful incomplete caller-owned template. Long non-BMP Work coordinates never
    yield a cut or shortened handle, and every issued read is callable as emitted."""
    import json
    from test_eigen_continuity_owner import PRODUCER, produce, arm_payload
    from laplace.work import project_work_continuity as C
    from laplace.native import tools
    from laplace.web import project_work_surface
    s = source
    root = s['root']
    grant, _account, candidate = produce(s)

    def machine(message):
        start = message.index('{"operation"')
        read, end = json.JSONDecoder().raw_decode(message, start)
        return read, start, end

    def formatted(error):
        native = tools.failure_response(root, 'public', 'work', 'development_source', {'action': 'arm'}, error)
        assert native['error'] == str(error), 'the native failure formatter cut the refusal'
        real = D.handle
        monkeypatch.setattr(D, 'handle', lambda *args, **kwargs: (_ for _ in ()).throw(error))
        try:
            code, _kind, body = project_work_surface.handle('/work/development', {}, 'POST',
                                                            json.dumps({'project': 'public', 'action': 'arm'}).encode(), root)
        finally:
            monkeypatch.setattr(D, 'handle', real)
        assert code == 422 and json.loads(body)['error'] == str(error)
        return native['error']

    small = {'id': 'pre-source-bootstrap', 'pre_source_review': ['External guarded functional proof.'], 'post_adoption': ['Ordinary app Source check.']}
    shaped = {'id': 'stage-\U0001F331', 'pre_source_review': ['\U0001F331' * 600] * 16, 'post_adoption': ['é' * 600] * 4}
    one_line = {'windows': [{'path': 'src/answer.py', 'line_start': 1, 'line_end': 1}]}
    ledger = W._ledger(root).read_bytes()
    captured = {}
    for label, over in (('inline', {'source_context': one_line, 'source_subject': {'stage': small}}),
                        ('shaped', {'source_context': one_line, 'source_subject': {'stage': shaped}}),
                        ('stageless', {'source_subject': {'prior': {'grants': ['DG-' + '\U0001F331' * 300]}}})):
        with pytest.raises(ValueError) as refused:
            D.handle(root, 'public', arm_payload(s, grant, candidate, request_id='public-whole-refusal-' + label, **over), PRODUCER)
        message = formatted(refused.value)
        assert len(message) <= C.FAILURE_TEXT_CHARS and 'thing was armed' in message.lower(), (label, len(message))
        read, start, end = machine(message)
        assert read['operation'] == 'development_source' and read['payload']['action'] == 'review-preflight'
        assert (read['payload']['work_id'], read['payload']['grant_id'], read['payload']['candidate_id']) == ('work', grant['id'], candidate)
        reuse = read.get('source_subject_reuse')
        if label == 'inline':
            assert read['payload']['source_subject'] == over['source_subject'] and reuse is None
        else:
            assert 'source_subject' not in read['payload'] and reuse['state'] == 'REUSE_ORIGINAL' and reuse['complete'] is False, (label, reuse)
        followed = D.handle(root, 'public', {**read['payload'], 'source_subject': over['source_subject']}, PRODUCER)
        assert 'scaffold' in followed, label   # the emitted read is callable as issued, with the caller's own original subject
        captured[label] = (message, start, end)
    assert W._ledger(root).read_bytes() == ledger
    # long non-BMP Work coordinates, composed with the actual arm prose around its read
    message, start, end = captured['inline']
    compose = lambda recovery: message[:start] + recovery + message[end:]
    subject = {'stage': {**small, 'pre_source_review': ['\U0001F331' * 120]}}
    assert len(json.dumps(subject)) <= C.PREFLIGHT_SUBJECT_INLINE_CHARS   # inline on its own
    long_work = 'WORK-' + '\U0001F331' * 200
    assert len(compose(C._recovery_text('public', long_work, grant['id'], candidate, subject))) > C.FAILURE_TEXT_CHARS   # inline would be cut
    fitted = str(C._recovery_refusal('public', long_work, grant['id'], candidate, subject, compose))
    assert len(fitted) <= C.FAILURE_TEXT_CHARS and formatted(ValueError(fitted)) == fitted
    read = machine(fitted)[0]
    assert read['payload']['work_id'] == long_work and 'source_subject' not in read['payload']
    assert read['source_subject_reuse']['state'] == 'REUSE_ORIGINAL' and 'failure text' in read['source_subject_reuse']['says']
    longest = 'WORK-' + '\U0001F331' * 400
    named = str(C._recovery_refusal('public', longest, grant['id'], candidate, subject, compose))
    assert len(named) <= C.FAILURE_TEXT_CHARS and '{"operation"' not in named and 'review-preflight' in named
    assert json.dumps(longest)[1:-1][:40] not in named and formatted(ValueError(named)) == named   # no cut or shortened handle


def test_two_commission_cumulative_arm_records_the_selected_complete_plan_and_refusals_append_nothing(source):
    """Source6: an attached eligible producer arms one cumulative intent over two commissions of one Work and parent. The
    earlier plain commission makes a prior-only change beyond line 80 and both change src/answer.py. With a typed stage, an
    explicit accepted_base and a read-only carry, the preflight's selected windows fed unchanged to the actual arm record a
    COMPLETE plan whose subject is the selected one. A bare-commission scaffold, the producer's own grant as prior ancestry
    and a stale arm after a late prior change all refuse and append nothing."""
    import copy
    import subprocess
    from test_eigen_continuity_owner import PRODUCER, STAGE, produce, arm_payload, judged
    from laplace.work import project_work_continuity as C
    s = source
    root, checkout = s['root'], s['checkout']
    long = (checkout / 'guide.md').read_text() + ''.join('prior line %d\n' % n for n in range(120)) + 'prior-only tail\n'
    made = D.candidate(root, 'public', {'grant_id': s['grant']['id'], 'files': [
        {'path': 'guide.md', 'before_sha256': D._pin(checkout / 'guide.md'), 'content': long}]}, s['door'])
    assert D.apply(root, 'public', {'candidate_id': made['candidate_id']}, s['door'])['ok']
    _apply(s, s['grant']['id'], [_edit(s, 'src/answer.py', 'keep middle', 'keep middle prior commission')])
    grant, _account, candidate = produce(s)
    pins = {p: D._pin(checkout / p) for p in ('src/answer.py', 'evaluator.py', 'guide.md')}
    base = grant.get('base') if isinstance(grant.get('base'), str) else subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=checkout, capture_output=True, text=True, check=True).stdout.strip()
    subject = {'stage': copy.deepcopy(STAGE), 'prior': {'grants': [s['grant']['id']]}, 'accepted_base': base,
               'carry': {'schema': D.REVIEW_CARRY_SCHEMA, 'members': [{'path': 'evaluator.py', 'sha256': pins['evaluator.py']}]}}
    request = {'work_id': 'work', 'grant_id': grant['id'], 'candidate_id': candidate}
    fence = {ident: D._latest(W._tasks('public', root)['work'], 'grant', ident)['paths'] for ident in (grant['id'], s['grant']['id'])}
    before = W._ledger(root).read_bytes()
    bare = D.review_preflight(root, 'public', request, PRODUCER)
    selected = D.review_preflight(root, 'public', {**request, 'source_subject': subject}, PRODUCER)
    assert W._ledger(root).read_bytes() == before
    assert selected['subject_geometry'] == 'SELECTED_SUBJECT' and selected['subject']['state'] == 'ADMISSIBLE', selected.get('subject')
    guide = lambda report: [w['line_end'] for w in report['scaffold']['windows'] if w['path'] == 'guide.md']
    assert max(guide(selected)) > 80 and max(guide(bare)) <= 80
    windows, chosen = selected['scaffold']['windows'], selected['pins']

    def arm(request_id, **over):
        return arm_payload(s, grant, candidate, request_id=request_id, pins=chosen,
                           **{'source_context': {'windows': windows}, 'source_subject': subject, **over})
    # the bare-commission scaffold misses the selected prior-only geometry of the whole plan (the obligation's own
    # projected inputs may still be covered by it), and an arm whose context misses its consumed inputs refuses
    basis = D.prepare_review_basis(root, 'public', 'work', {'grant_id': grant['id'], 'candidate_id': candidate}, chosen, door=PRODUCER)
    assert D.prepare_review_plan(root, 'public', 'work', basis, chosen, {'windows': bare['scaffold']['windows']}, subject)['state'] == 'INCOMPLETE'
    assert D.prepare_review_plan(root, 'public', 'work', basis, chosen, {'windows': windows}, subject)['state'] == 'COMPLETE'
    assert W._ledger(root).read_bytes() == before
    with pytest.raises(ValueError, match='INCOMPLETE'):
        D.handle(root, 'public', arm('public-two-commission-short', source_context={'windows': [
            {'path': 'src/answer.py', 'line_start': 1, 'line_end': 1}]}), PRODUCER)
    with pytest.raises(ValueError, match='already belongs'):
        D.handle(root, 'public', arm('public-two-commission-own', source_subject={**subject, 'prior': {'grants': [grant['id']]}}), PRODUCER)
    assert W._ledger(root).read_bytes() == before
    armed = D.handle(root, 'public', arm('public-two-commission-arm'), PRODUCER)
    intent = armed['intent']
    row = C._intent(W._tasks('public', root)['work'], intent['id'])
    plan = row['production']['source_review_plan']
    assert armed['ok'] and intent['state'] == 'ARMED' and plan['state'] == 'COMPLETE'
    recorded = plan['review_subject']
    assert recorded['subject_id'] == selected['subject']['summary']['subject_id']
    assert [g['id'] for g in recorded['prior_production']['grants']] == [s['grant']['id']]
    assert intent['production']['review_subject']['stage'] == STAGE['id'] and judged(s, intent)['facts']['source_subject'] == 'CURRENT'
    assert {ident: D._latest(W._tasks('public', root)['work'], 'grant', ident)['paths'] for ident in fence} == fence   # no widened fence
    stale = arm('public-two-commission-late')   # composed before the late change, with the Work revision it then read
    _apply(s, s['grant']['id'], [_edit(s, 'guide.md', 'prior-only tail', 'prior-only tail moved late')])
    assert 'SOURCE_SUBJECT_CHANGED' in {reason['code'] for reason in judged(s, intent)['reasons']}
    ledger = W._ledger(root).read_bytes()
    with pytest.raises(Exception):
        D.handle(root, 'public', stale, PRODUCER)
    assert W._ledger(root).read_bytes() == ledger
