"""Pure B2 contract proofs; no registration, source/service or ledger writes."""
import copy

import pytest

from laplace.manuscript import reader_logical_restructure as owner, reader_plan


@pytest.fixture
def case():
    rows = [
        {'section_id': 'first', 'paragraph_id': 'first-p1', 'function': 'Introduce',
         'proposition': 'One', 'input_nodes': ['claim:one'], 'qualification': 'Prior scope'},
        {'section_id': 'first', 'paragraph_id': 'first-p2', 'function': 'Explain',
         'proposition': 'Two', 'citations': ['reference-two']},
        {'section_id': 'first', 'paragraph_id': 'first-p3', 'function': 'Unrelated',
         'proposition': 'Three', 'qualification': 'Unchanged standing'}]
    occurrences = []
    for line, ids in [(3, ['first-p1']), (6, ['first-p1']), (9, ['first-p1', 'first-p2'])]:
        row = {'file': 'chapter.tex', 'line_start': line, 'line_end': line + 2,
               'spec_ids': ids, 'content_sha256': owner.fingerprint([line, ids]),
               'basis': {'selection_identity': owner.fingerprint('selected edition'),
                         'source_digest': owner.fingerprint('physical source')}}
        row['id'] = owner.occurrence_id(row)
        occurrences.append(row)
    attachments = [
        {'id': 'ATT-claim', 'kind': 'claim', 'paragraph_ids': ['first-p1'],
         'field': 'input_nodes', 'value': 'claim:one', 'pin': owner.fingerprint('claim input')},
        {'id': 'ATT-qualification', 'kind': 'qualification', 'paragraph_ids': ['first-p1'],
         'field': 'qualification', 'value': 'Prior scope', 'pin': owner.fingerprint('Prior scope')},
        {'id': 'ATT-review', 'kind': 'review', 'paragraph_ids': ['first-p1'],
         'record_id': 'WORK-old-review', 'pin': owner.fingerprint({'accepted': True})},
        {'id': 'ATT-protection', 'kind': 'protection', 'paragraph_ids': ['first-p1'],
         'record_id': 'EDIT-old', 'pin': owner.fingerprint('old protection')},
        {'id': 'ATT-note', 'kind': 'note', 'paragraph_ids': ['first-p1'],
         'record_id': 'NOTE-old', 'pin': owner.fingerprint('old note'),
         'read': {'operation': 'author_history', 'payload': {'id': 'activity:feedback:NOTE-old'}}},
        {'id': 'ATT-legacy', 'kind': 'legacy', 'paragraph_ids': ['first-p1'],
         'pin': owner.fingerprint({'unknown': 'preserved in exact retained intent'})}]
    basis = {'expected_reader_basis': {'first-p1': reader_plan._basis(
        'book', 'narrative/first.json', 'first-p1', rows[0],
        {'architecture': owner.fingerprint('effective profile'), 'concept:one': owner.fingerprint('current claim')}, 'first')},
        'source_set_revision': owner.fingerprint(['chapter.tex']),
        'attachment_revision': owner.fingerprint(attachments)}
    successors = owner.offer_successors('book', 'first', 'logical-split', ['first-p1'], 2,
        narrative_revision=owner.fingerprint(rows), current_ids=[row['paragraph_id'] for row in rows], reserved_ids=[])
    return {'rows': rows, 'selected_ids': ['first-p1'], 'successor_ids': successors,
            'occurrences': occurrences, 'attachments': attachments, 'basis': basis,
            'coverage': {'complete': True}}


def prepare(case, draft=None, kind='logical-split'):
    return owner.prepare('book', 'first', kind, **case, draft=draft)


def complete_draft(case):
    first, second = case['successor_ids']
    return {'paragraph_ids': case['selected_ids'],
        'successors': [{'paragraph_id': first, 'changes': {'function': 'Introduce separately', 'proposition': 'First authored role'}},
                       {'paragraph_id': second, 'changes': {'function': 'Explain separately', 'proposition': 'Second authored role'}}],
        'attachment_assignments': [
            {'attachment_id': 'ATT-claim', 'successor_ids': [first], 'disposition': 'assign'},
            {'attachment_id': 'ATT-qualification', 'successor_ids': [], 'disposition': 'retain-retired'},
            {'attachment_id': 'ATT-review', 'successor_ids': [], 'disposition': 'retain-retired'},
            {'attachment_id': 'ATT-protection', 'successor_ids': [], 'disposition': 'retain-retired'},
            {'attachment_id': 'ATT-note', 'successor_ids': [second], 'disposition': 'assign'},
            {'attachment_id': 'ATT-legacy', 'successor_ids': [second], 'disposition': 'retain-unresolved'}],
        'occurrence_assignments': [{'occurrence_id': row['id'], 'successor_ids': [first] if index == 0 else [second]}
                                   for index, row in enumerate(case['occurrences'])]}


def test_initial_inspection_offers_unused_stable_ids_and_withholds_application(case):
    before = copy.deepcopy(case)
    value = prepare(case)
    assert not value['ready'] and value['needs_input'] and value['provider_started'] is False
    assert all(not row.get('function') and not row.get('proposition') for row in value['successors'])
    assert case == before
    offered = owner.offer_successors('book', 'first', 'logical-split', ['first-p1'], 2,
        narrative_revision=owner.fingerprint(case['rows']), current_ids=[row['paragraph_id'] for row in case['rows']], reserved_ids=[])
    assert offered == case['successor_ids']
    reserved = owner.offer_successors('book', 'first', 'logical-split', ['first-p1'], 2,
        narrative_revision=owner.fingerprint(case['rows']), current_ids=[row['paragraph_id'] for row in case['rows']], reserved_ids=offered)
    assert not set(reserved).intersection(offered)


def test_complete_repeated_occurrences_preserve_unretired_ids_and_scoped_attachments(case):
    value = prepare(case, complete_draft(case)); first, second = case['successor_ids']
    assert value['ready'] and len(value['source_mappings']) == 3
    assert value['source_mappings'][2]['after_ids'] == [second, 'first-p2']
    assert value['successors'][0]['input_nodes'] == ['claim:one']
    assert any(row['id'] == 'ATT-note' for row in value['successors'][1]['attachment_refs'])
    assert not any(row['kind'] in {'review', 'protection'} for unit in value['successors'] for row in unit['attachment_refs'])
    assert value['semantic_currentness'] == 'NOT_REVIEWED'
    assert any(row['kind'] == 'ATTACHMENT_RECONCILIATION' for row in value['review_obligations'])


def test_missing_or_truncated_occurrence_inventory_cannot_be_applied(case):
    draft = complete_draft(case); draft['occurrence_assignments'].pop()
    assert any(row['kind'] == 'OCCURRENCE_ASSIGNMENT' for row in prepare(case, draft)['needs_input'])
    case['coverage'] = {'complete': False}
    assert not prepare(case, complete_draft(case))['ready']


def test_unbound_retained_prose_requires_explicit_empty_assignment_and_obligation(case):
    draft = complete_draft(case); draft['occurrence_assignments'][0]['successor_ids'] = []
    value = prepare(case, draft)
    assert value['ready'] and value['source_mappings'][0]['after_ids'] == []
    assert any(row['kind'] == 'UNBOUND_RETAINED_PROSE' for row in value['review_obligations'])


def test_crossed_draft_scope_and_implicit_scientific_fields_refuse(case):
    for mutate in [lambda draft: draft.update(source_edits=[]),
                   lambda draft: draft['successors'][0]['changes'].update(input_nodes=['invented']),
                   lambda draft: draft['attachment_assignments'].append(copy.deepcopy(draft['attachment_assignments'][0])),
                   lambda draft: draft['occurrence_assignments'][0].update(successor_ids=['unoffered'])]:
        draft = complete_draft(case); mutate(draft)
        with pytest.raises(ValueError): prepare(case, draft)


def test_changed_subject_or_effective_profile_basis_requires_new_owner_admission(case):
    original = prepare(case, complete_draft(case))
    changed = copy.deepcopy(case); changed['rows'][0]['proposition'] = 'Concurrent authored change'
    with pytest.raises(ValueError, match='reader basis'): prepare(changed, complete_draft(changed))
    changed = copy.deepcopy(case)
    changed['basis']['expected_reader_basis']['first-p1']['inputs']['architecture'] = owner.fingerprint('changed effective architecture')
    assert prepare(changed, complete_draft(changed))['basis_token'] != original['basis_token']


def test_scoped_narrative_patch_and_inverse_preserve_disjoint_full_rows(case):
    value = prepare(case, complete_draft(case)); before = copy.deepcopy(case['rows'])
    after = owner.apply_narrative_patch(before, value['narrative_patch'])
    assert after[-2:] == before[-2:]
    assert owner.apply_narrative_patch(after, value['narrative_patch'], inverse=True) == before
    after[0]['qualification'] = 'Intervening edit'
    with pytest.raises(ValueError, match='postimage'): owner.apply_narrative_patch(after, value['narrative_patch'], inverse=True)


def test_merge_resolves_into_one_unused_successor_without_dropping_intervening_rows(case):
    case = copy.deepcopy(case); case['selected_ids'] = ['first-p1', 'first-p3']; case['successor_ids'] = ['first-p999']
    case['basis']['expected_reader_basis']['first-p3'] = reader_plan._basis('book', 'narrative/first.json', 'first-p3', case['rows'][2], {}, 'first')
    case['attachments'].append({'id':'ATT-qualification-three','kind':'qualification','paragraph_ids':['first-p3'],
        'field':'qualification','value':'Unchanged standing','pin':owner.fingerprint('Unchanged standing')})
    draft = complete_draft({**case, 'successor_ids': ['first-p999', 'unused-only-for-helper']})
    draft['attachment_assignments'].append({'attachment_id':'ATT-qualification-three','successor_ids':[], 'disposition':'retain-retired'})
    draft['successors'] = draft['successors'][:1]
    for row in draft['attachment_assignments']:
        if row['successor_ids']: row['successor_ids'] = ['first-p999']
    for row in draft['occurrence_assignments']: row['successor_ids'] = ['first-p999']
    value = prepare(case, draft, 'logical-merge')
    assert value['ready']
    after = owner.apply_narrative_patch(case['rows'], value['narrative_patch'])
    assert [row['paragraph_id'] for row in after] == ['first-p999', 'first-p2']
    assert owner.apply_narrative_patch(after, value['narrative_patch'], inverse=True) == case['rows']


def test_qualification_inventory_omission_and_wrong_successor_count_withhold_or_refuse(case):
    case['attachments']=[item for item in case['attachments'] if item['id']!='ATT-qualification']
    draft=complete_draft(case);draft['attachment_assignments']=[item for item in draft['attachment_assignments'] if item['attachment_id']!='ATT-qualification']
    value=prepare(case,draft)
    assert not value['ready'] and any(item['kind']=='ATTACHMENT_INVENTORY' and item['field']=='qualification' for item in value['needs_input'])
    draft['successor_count']=3
    with pytest.raises(ValueError,match='successor count'):prepare(case,draft)


def test_explicit_retired_and_unresolved_dispositions_are_retained_for_lineage(case):
    draft=complete_draft(case);value=prepare(case,draft)
    assert value['attachment_dispositions']==draft['attachment_assignments']
    assert value['occurrence_dispositions']==draft['occurrence_assignments']
    assert any(item['disposition']=='retain-retired' and item['attachment_id']=='ATT-review' for item in value['attachment_dispositions'])


@pytest.mark.parametrize('newline',['\n','\r\n'])
def test_marker_only_staging_preserves_prose_complete_ids_and_physical_newlines(case,newline):
    import hashlib
    from laplace.manuscript.projection_viewer import parse_paragraphs, _PARA_RE
    text=('% first-p1\nFirst.\n\n% first-p1\nRepeated.\n\n% first-p1\n% first-p2\nShared.\n').replace('\n',newline)
    pin=lambda value:'sha256:'+hashlib.sha256(value.encode()).hexdigest()
    lines=text.splitlines(keepends=True);case=copy.deepcopy(case);case['occurrences']=[]
    for span in parse_paragraphs(text):
        row={'file':'chapter.tex','line_start':span['start_line'],'line_end':span['end_line'],
             'spec_ids':span['spec_ids'],'content_sha256':pin(''.join(lines[span['start_line']-1:span['end_line']])),
             'basis':{'selection_identity':owner.fingerprint('selected edition'),'source_digest':pin(text)}}
        row['id']=owner.occurrence_id(row);case['occurrences'].append(row)
    prepared=prepare(case,complete_draft(case));staged=owner.stage_markers({'chapter.tex':text},prepared)
    result=staged['staged_sources']['chapter.tex'];first,second=case['successor_ids']
    assert [span['spec_ids'] for span in parse_paragraphs(result)]==[[first],[second],[second,'first-p2']]
    strip=lambda value:''.join(line for line in value.splitlines(keepends=True) if not _PARA_RE.fullmatch(line.rstrip('\r\n')))
    assert strip(result)==strip(text)
    assert len(staged['source_changes'])==1 and len(staged['source_changes'][0]['marker_edits'])==3
    assert all('First.' not in edit['after'] and 'Shared.' not in edit['before'] for edit in staged['source_changes'][0]['marker_edits'])
    if newline=='\r\n':assert '\n' not in result.replace('\r\n','')
    current=text.replace('First.','Concurrent.')
    with pytest.raises(ValueError,match='CHANGED_INPUT'):owner.stage_markers({'chapter.tex':current},prepared)
    assert current==text.replace('First.','Concurrent.')


def test_large_supported_attachment_inventory_checks_coverage_in_linear_work(case):
    class CountedAttachment(dict):
        gets = 0
        def get(self, key, default=None):
            type(self).gets += 1
            return super().get(key, default)
    count=1200
    row=case['rows'][0];row.pop('input_nodes');row.pop('qualification')
    row['citations']=['reference-'+str(i) for i in range(count)]
    case['attachments']=[CountedAttachment(id='ATT-'+str(i),kind='citation',paragraph_ids=['first-p1'],
        field='citations',value=value,pin=owner.fingerprint(value)) for i,value in enumerate(row['citations'])]
    case['basis']['expected_reader_basis']['first-p1']=reader_plan._basis('book','narrative/first.json','first-p1',row,{},'first')
    draft={'paragraph_ids':['first-p1'], 'successors':[{'paragraph_id':ident,'changes':{'function':'Explain','proposition':'Point'}} for ident in case['successor_ids']],
        'attachment_assignments':[{'attachment_id':item['id'],'disposition':'retain-retired','successor_ids':[]} for item in case['attachments']],
        'occurrence_assignments':[{'occurrence_id':item['id'],'successor_ids':case['successor_ids'][:1]} for item in case['occurrences']]}
    CountedAttachment.gets=0
    result=prepare(case,draft)
    assert result['ready'] and len(result['attachment_inventory'])==count
    assert CountedAttachment.gets < count*20
