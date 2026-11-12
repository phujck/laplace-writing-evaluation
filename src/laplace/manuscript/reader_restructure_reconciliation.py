"""Explicit current-source adoption for retained structural metadata only.

A historical physical effect remains historical. This door proves exact marker
frames and paragraph boundaries at recorded coordinates; it never searches for
similar prose, replays source, or turns changed support into accepted science.
"""
from __future__ import annotations
import copy
from pathlib import Path


def read_handle(project,section_id,receipt):
    fields={'view':'restructure','section_ids':[section_id], 'receipt_id':receipt['id'],
        'intent_artifact_id':receipt['intent_artifact_id'],'reconcile_current':True}
    from laplace.core import grammar
    return {'operation':'structure','payload':fields,
        'native_request':{'verb':'read','concept':'plan@plan','target':project,'expected':[],'payload':grammar.to_payload(fields),'by':''},
        'http':{'method':'GET','route':'/work/structure','query':{'project':project,**fields}}}


def inspect(project,root,intent,value,assignments=None):
    value=copy.deepcopy(value)
    if assignments is not None:value['_current_occurrence_assignments']=copy.deepcopy(assignments)
    from laplace.manuscript import reader_restructure as owner, bindings
    from laplace.writing import records
    from laplace.manuscript import manuscript_source, projection_viewer
    root=Path(root);sid=intent['section_id'];snapshot=owner._snapshot(project,sid,root)
    observation=manuscript_source.observation(project,root)
    reasons=[];reads=[]
    latest=records.index(root).reader_restructure_receipts.get((project,value['receipt']['intent_artifact_id']))
    latest_outcome=(latest or {}).get('reader_metadata',{}).get('restructure') or {}
    if value.get('complete') or latest_outcome.get('complete'):reasons.append('This structural record is already complete; inspect its latest exact receipt.')
    plan_only=value.get('source_required') is False and value.get('source_unchanged') is True
    if not plan_only and value.get('source_effect',{}).get('state') not in {'COMMITTED','UNCHANGED'}:
        reasons.append('The original recorded source commit is unavailable; no current-source adoption is implied.')
    if observation['selection_identity']!=intent['guards']['expected_selection']:
        reasons.append('The selected source identity changed.')
    if snapshot['state']['authority']['plan_revision']!=intent['guards']['expected_plan_revision']:
        reasons.append('The declared reader plan changed.')
    for name in ('narrative','provenance'):
        allowed={intent['guards']['expected_'+name+'_revision']}
        if name+'_after_revision' in intent:allowed.add(intent[name+'_after_revision'])
        prior=value.get('metadata_reconciliation') or {}
        if name+'_after_revision' in prior:allowed.add(prior[name+'_after_revision'])
        if owner.revision(snapshot['raw'][name]) not in allowed:
            reasons.append('Relevant '+name+' metadata changed outside this exact operation.')
    decision_rows=(snapshot['documents']['decisions'] or {}).get('decisions',[])
    refs=[row for row in decision_rows if row.get('owner')=='reader-restructure']
    if len(refs)!=1 or refs[0].get('intent_artifact_id')!=value['receipt']['intent_artifact_id']:
        reasons.append('The retained structural decision pointer changed.')
    if owner.fingerprint([row for row in decision_rows if row.get('owner')!='reader-restructure'])!=intent['decision_other_revision']:
        reasons.append('Unrelated reader decisions changed.')
    mapping=intent.get('occurrence_mapping',{}).get('after',[])
    if not mapping and not plan_only:reasons.append('The retained postimage has no proved physical occurrence mapping.')
    parsed={};expected_rows=[];choices=[];witnesses=[];relocations=[]
    from laplace.manuscript.reader_logical_restructure import occurrence_id
    for expected in mapping:
        file=expected.get('file') or intent['source_changes'][0]['file']
        start=expected.get('start_line',expected.get('line_start'));end=expected.get('end_line',expected.get('line_end'))
        old={'file':file,'line_start':start,'line_end':end,'spec_ids':list(expected['spec_ids'])}
        old['id']='WIT-'+owner.fingerprint(old).split(':')[1][:32]
        old['read']=bindings.source_read(file,{'line':start,'line_end':end},project=project)
        expected_rows.append(old)
        if file not in parsed:
            path=root/file;text=path.read_text() if path.is_file() else ''
            lines=text.splitlines(keepends=True)
            parsed[file]=[]
            for span in projection_viewer.parse_paragraphs(text):
                row={'file':file,'line_start':span['start_line'],'line_end':span['end_line'],'spec_ids':list(span['spec_ids']),
                    'content_sha256':owner.revision(''.join(lines[span['start_line']-1:span['end_line']]).encode())}
                row['id']=occurrence_id(row)
                row['read']=bindings.source_read(file,{'line':row['line_start'],'line_end':row['line_end']},project=project)
                parsed[file].append(row)
    expected_by_id={row['id']:row for row in expected_rows}
    from collections import defaultdict
    expected_groups=defaultdict(list);choice_groups=defaultdict(list)
    for row in expected_rows:expected_groups[(row['file'],tuple(row['spec_ids']))].append(row)
    for file,rows in parsed.items():
        for row in rows:
            key=(file,tuple(row['spec_ids']))
            if key in expected_groups:choices.append(row);choice_groups[key].append(row)
    eligibility=[];slot_proofs={};coordinates={}
    for key,old_rows in expected_groups.items():
        current_rows=choice_groups[key]
        group_id='OCG-'+owner.fingerprint(key).split(':')[1][:32]
        eligibility.append({'id':group_id,'file':key[0],'spec_ids':list(key[1]),'choice_ids':[row['id'] for row in current_rows]})
        for old in old_rows:old['allowed_current_occurrence_group_id']=group_id
        slot_proofs[key]=len(current_rows)==len(old_rows) and {(row['line_start'],row['line_end']) for row in current_rows}=={(row['line_start'],row['line_end']) for row in old_rows}
        for row in current_rows:coordinates[(key,row['line_start'],row['line_end'])]=row
    supplied=value.pop('_current_occurrence_assignments',None) or []
    assignment={};used=set()
    if len({row.get('expected_occurrence_id') for row in supplied})!=len(supplied):
        raise ValueError('Choose each exact retained physical occurrence once.')
    choices_by_id={row['id']:row for row in choices}
    for row in supplied:
        old=expected_by_id.get(row.get('expected_occurrence_id'));new=choices_by_id.get(row.get('current_occurrence_id'))
        if old is None or new is None or old['file']!=new['file'] or old['spec_ids']!=new['spec_ids'] or new['id'] in used:
            raise ValueError('CHANGED_INPUT: current occurrence selection must preserve the exact full marker set and use each physical group once.')
        assignment[old['id']]=new;used.add(new['id'])
    for old in expected_rows:
        if old['id'] in assignment:continue
        key=(old['file'],tuple(old['spec_ids']));group=choice_groups[key]
        chosen=coordinates.get((key,old['line_start'],old['line_end'])) if slot_proofs[key] else group[0] if len(group)==1 and len(expected_groups[key])==1 else None
        if chosen and chosen['id'] not in used:assignment[old['id']]=chosen;used.add(chosen['id'])
        elif not group:reasons.append('No current full marker set is provable for '+old['file']+':'+str(old['line_start'])+'.')
    normalized=[]
    for old in expected_rows:
        new=assignment.get(old['id'])
        if new:
            witnesses.append({key:copy.deepcopy(new[key]) for key in ('file','line_start','line_end','spec_ids')})
            normalized.append({'expected_occurrence_id':old['id'],'current_occurrence_id':new['id']})
            relocations.append({'before':{key:old[key] for key in ('file','line_start','line_end','spec_ids')},
                'after':{key:new[key] for key in ('file','line_start','line_end','spec_ids')}})
    reads=[row['read'] for row in choices]
    needs_selection=len(witnesses)!=len(expected_rows)
    for key,rows in expected_groups.items():
        if len(choice_groups[key])!=len(rows):
            reasons.append('Current full marker group count changed; this recovery cannot infer the new structural correspondence.')
    guards={**value['guards'],'expected_narrative_revision':owner.revision(snapshot['raw']['narrative']),
        'expected_provenance_revision':owner.revision(snapshot['raw']['provenance']),
        'expected_decision_revision':owner.revision(snapshot['raw']['decisions']),
        'source_guards':{row['file']:'sha256:'+observation['file_revisions'][row['file']] for row in witnesses if row['file'] in observation['file_revisions']}}
    changed_inputs=[]
    if intent['kind'].startswith('logical-'):
        from laplace.manuscript.reader_logical_publication import observed_reader_basis
        try:
            fresh=observed_reader_basis(project,root,intent,snapshot)
            guards['expected_reader_basis']=fresh
            for ident,basis in fresh.items():
                original=intent['guards']['expected_reader_basis'][ident]['inputs']
                changed=[key for key in set(original)|set(basis['inputs']) if original.get(key)!=basis['inputs'].get(key)]
                if changed:changed_inputs.append({'paragraph_id':ident,'changed_inputs':sorted(changed)})
        except ValueError as exc:reasons.append(str(exc))
        guards['expected_source_set_revision']=observation['source_revision']
    observation={**observation,'guards':copy.deepcopy(guards)}
    prior=value.get('metadata_reconciliation') or {}
    provenance_before=owner.revision(snapshot['raw']['provenance'])
    mode='PREIMAGE' if provenance_before==intent['guards']['expected_provenance_revision'] else 'POSTIMAGE'
    if prior and provenance_before==prior.get('provenance_after_revision'):mode='RELOCATED_POSTIMAGE'
    relocation={'relocations':relocations,'provenance_base_mode':mode,
        'previous_relocations':prior.get('relocations',[]) if mode=='RELOCATED_POSTIMAGE' else []}
    try:provenance=provenance_document(project,root,intent,snapshot,relocation)
    except ValueError as exc:reasons.append(str(exc));provenance=None
    facts={'original_receipt':value['receipt'],'current_observation':observation,'marker_witnesses':witnesses,
        'guards':guards,'changed_dependencies':changed_inputs,'remaining_steps':list(value['remaining_steps']),
        **relocation,'provenance_after_revision':owner.revision(_encode(provenance))}
    token=owner.fingerprint(facts)
    obligations=[{'kind':'SOURCE_CHANGED_AFTER_STRUCTURAL_COMMIT',
        'reason':'The physical effect is historical. Current source was explicitly inspected for metadata only; scientific review and later human edits are not accepted by this recording.'}]
    if plan_only:obligations=[{'kind':'CURRENT_READER_DEPENDENCIES_ADOPTED',
        'reason':'No physical source effect was required. Current dependencies were explicitly inspected for metadata only; scientific review remains separate.'}]
    obligations += [{'kind':'CHANGED_LOGICAL_READER_INPUTS','paragraph_id':row['paragraph_id'],'changed_inputs':row['changed_inputs']} for row in changed_inputs]
    return {**facts,'status':'UNPROVABLE' if reasons else 'NEEDS_INPUT' if needs_selection else 'READY',
        'occurrence_inventory':expected_rows,'current_occurrence_choices':choices,'current_occurrence_groups':eligibility,'current_occurrence_assignments':normalized,
        'preview_action':owner.action(project,sid,'preview-reconciliation',receipt_id=value['receipt']['id'],
            intent_artifact_id=value['receipt']['intent_artifact_id']),'reconciliation_token':token,
        'refusal_reasons':reasons,'source_reads':reads,'review_obligations':obligations,
        'action':owner.action(project,sid,'reconcile-restructure',receipt_id=value['receipt']['id'],
            intent_artifact_id=value['receipt']['intent_artifact_id'],reconciliation_token=token,guards=guards,current_occurrence_assignments=normalized) if not reasons and not needs_selection else None}


def reconcile(project,root,intent,value,payload,*,actor=None):
    from contextlib import nullcontext
    from laplace.manuscript import manuscript_source
    # Use only admitted physical targets, never caller-supplied guard paths.
    paths=[Path(root)/row['file'] for row in intent['source_changes']]
    with manuscript_source.selection_mutation(project,root), (manuscript_source.source_mutation(paths) if paths else nullcontext()):
        return _reconcile_locked(project,root,intent,value,payload,actor=actor)


def _reconcile_locked(project,root,intent,value,payload,*,actor=None):
    from laplace.manuscript import reader_restructure as owner
    current=inspect(project,root,intent,value,payload.get('current_occurrence_assignments'))
    if current['status']!='READY':raise ValueError('Current-source metadata reconciliation is unproved: '+'; '.join(current['refusal_reasons']))
    if payload.get('reconciliation_token')!=current['reconciliation_token'] or any(payload.get(key)!=item for key,item in current['guards'].items()):
        raise ValueError('CHANGED_INPUT: inspect and explicitly adopt this exact current-source metadata basis.')
    adopted=copy.deepcopy(value)
    adopted['guards']=copy.deepcopy(current['guards'])
    adopted['metadata_reconciliation']={key:copy.deepcopy(item) for key,item in current.items() if key not in {'action','preview_action'}}
    adopted['metadata_reconciliation']['actor']=actor or {'kind':'human'}
    adopted['review_obligations']=[*adopted.get('review_obligations',[]),*current['review_obligations']]
    adopted['source_currentness']='HISTORICAL_EFFECT_WITH_SEPARATE_CURRENT_OBSERVATION'
    # Bank the adopted current basis before metadata, using the existing RPUB.
    adopted['source_receipt_id']=intent['source_receipt_id']
    adopted['receipt']={**adopted['receipt'],'id':None}
    adopted=owner._record_receipt(project,root,adopted)
    if intent['kind'].startswith('logical-'):
        from laplace.manuscript.reader_logical_publication import publish_metadata
        return publish_metadata(project,root,intent,adopted)
    return owner._publish_metadata(project,root,intent,adopted)


def verify_adopted(project,root,intent,value):
    """Check the recorded explicit adoption again; never turn it into polling authority."""
    from laplace.manuscript import manuscript_source
    from laplace.manuscript import reader_restructure as owner
    adopted=value['metadata_reconciliation'];expected=adopted['current_observation']
    observed=manuscript_source.observation(project,root)
    if any(observed.get(key)!=expected.get(key) for key in ('selection_identity','source_revision','file_revisions')):
        raise ValueError('CHANGED_INPUT: current source changed after explicit metadata reconciliation; inspect it again.')
    snapshot=owner._snapshot(project,intent['section_id'],root)
    if intent['kind'].startswith('logical-'):
        from laplace.manuscript.reader_logical_publication import observed_reader_basis
        if observed_reader_basis(project,root,intent,snapshot)!=adopted['guards']['expected_reader_basis']:
            raise ValueError('CHANGED_INPUT: scoped reader inputs changed after explicit metadata adoption.')
    for name in ('narrative','provenance'):
        allowed={adopted['guards']['expected_'+name+'_revision'],adopted.get(name+'_after_revision'),intent.get(name+'_after_revision')}
        if owner.revision(snapshot['raw'][name]) not in allowed:
            raise ValueError('CHANGED_INPUT: relevant '+name+' changed after explicit adoption.')


def qualify_result(result,original,*,history_unavailable=False):
    """A metadata acknowledgement never invents a fresh source effect or inverse."""
    result=copy.deepcopy(result)
    if result.get('complete'):result.pop('error',None)
    adopted=original['metadata_reconciliation']
    result.update(metadata_only=True,metadata_reconciliation=copy.deepcopy(adopted),
        current_observation=copy.deepcopy(adopted['current_observation']),
        source_currentness='HISTORICAL_EFFECT_WITH_SEPARATE_CURRENT_OBSERVATION',
        source_receipt_id=original['source_receipt_id'])
    if 'source_effect' in original:result['source_effect']=copy.deepcopy(original['source_effect'])
    else:
        result.pop('source_effect',None)
        result['source_currentness']='NO_PHYSICAL_EFFECT_WITH_SEPARATE_CURRENT_OBSERVATION'
    if result.get('owned_changes'):
        physical={row['path'] for row in original.get('source_effect',{}).get('files',[])}
        result['owned_changes']['files']=[row for row in result['owned_changes'].get('files',[]) if row.get('path') not in physical]
        result['owned_changes']['views']=['structure','history']
    result['guards']['source_guards']=copy.deepcopy(adopted['guards']['source_guards'])
    result['review_obligations']=copy.deepcopy(original.get('review_obligations') or [])
    if history_unavailable:
        result['review_obligations'].append({'kind':'ORIGINAL_SOURCE_HISTORY_UNAVAILABLE',
            'reason':'The original physical commit is recorded, but its full saved text was unavailable after later edits. No source history was fabricated.',
            'receipt_id':original['source_receipt_id']})
    result.pop('undo_action',None)
    return result


def _encode(value):
    import json
    return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode() if value is not None else None


def _relocate(document,relocations,root,manuscript_dir,*,inverse=False):
    from laplace.manuscript import reader_restructure as owner
    result=copy.deepcopy(document)
    if result is None:return None
    indexed={}
    for mapping in relocations:
        old,new=(mapping['after'],mapping['before']) if inverse else (mapping['before'],mapping['after'])
        key=((root/old['file']).resolve(),old['line_start'],old['line_end'],tuple(old['spec_ids']))
        if key in indexed:raise ValueError('Ambiguous exact provenance relocation; choose distinct current groups.')
        indexed[key]=new
    for row in result.get('paragraphs',[]):
        loc=row.get('source')
        if not isinstance(loc,dict):continue
        ids=tuple(row.get('spec_ids') or [row.get('spec_id')])
        matches=[indexed[key] for file in owner._source_file_keys(loc.get('file'),root,manuscript_dir)
            if (key:=(file,loc.get('line_start'),loc.get('line_end'),ids)) in indexed]
        if len(matches)>1:raise ValueError('Ambiguous source identity in exact provenance relocation.')
        if matches:loc.update(line_start=matches[0]['line_start'],line_end=matches[0]['line_end'])
    return result


def provenance_document(project,root,intent,snapshot,adopted):
    from laplace.manuscript import reader_restructure as owner
    document=copy.deepcopy(snapshot['documents']['provenance'])
    observed=owner.revision(snapshot['raw']['provenance'])
    if adopted.get('provenance_after_revision') is not None and observed==adopted['provenance_after_revision']:
        return document
    mode=adopted['provenance_base_mode']
    if mode=='PREIMAGE':
        if intent['kind'].startswith('logical-'):
            from laplace.manuscript.reader_logical_publication import _apply_provenance
            document=_apply_provenance(document,intent['provenance_patch'],intent['section_id'],root,inverse=intent.get('inverse',False))
        else:document=owner._apply_provenance_patch(document,intent['provenance_patch'],inverse=owner._provenance_inverse(intent),section_id=intent['section_id'],root=root)
    from laplace.manuscript import manuscript_source
    home=root/manuscript_source.resolve(project,repo_root=root)['manuscript_dir']
    if mode=='RELOCATED_POSTIMAGE':document=_relocate(document,adopted['previous_relocations'],root,home,inverse=True)
    return _relocate(document,adopted['relocations'],root,home)
