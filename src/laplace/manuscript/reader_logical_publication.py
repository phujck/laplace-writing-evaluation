"""Logical preparation/publication delegated by the paragraph-restructure owner.

The active narrative remains current state, not a retired-row archive. Scoped
predecessors, assignments and inverse patches belong to its existing ART; RPUB
tracks required publication. This module introduces no store or tool family.
"""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

from laplace.manuscript import reader_plan, reader_logical_restructure as logical

EXTRA_GUARDS = ('expected_reader_basis', 'expected_source_set_revision')


def _pin(text):
    return 'sha256:' + hashlib.sha256(text.encode('utf-8')).hexdigest()


def _attachment(project, section_id, paragraph_id, field, value, kind, *, pin, read):
    return {'id': 'ATT-' + logical.fingerprint([project, section_id, paragraph_id, field, value, pin]).split(':')[1][:32],
            'kind': kind, 'paragraph_ids': [paragraph_id], 'field': field, 'value': copy.deepcopy(value),
            'pin': pin, 'read': read, 'owner': 'reader-plan',
            'label': field.replace('_', ' ') + ': ' + str(value)[:180]}


def _carried_attachments(project, section_id, selected, rows, root):
    """Resolve flat references through each unit's indexed creating intent.

    The active plan carries references, not copied attachment bodies or ancestry.
    One exact ART per creating operation supplies the typed value and original
    disposition. Inverses do not overwrite the creation index. Current declared
    fields are inventoried from their current owner, not renewed from old refs.
    """
    from laplace.writing import records
    from laplace.manuscript import reader_restructure as owner
    index = records.index(root)
    creators = {}; carried = {}; carried_signatures = {}; handled_feedback = set(); observed_creators = set()

    def feedback_refs(item):
        if item.get('owner') == 'feedback':
            if item.get('record_id'):
                handled_feedback.add((item['record_id'], item.get('pin')))
            elif item.get('field') == 'unlinked_feedback':
                handled_feedback.update((ref.get('id'), ref.get('pin'))
                    for ref in item.get('value') or [] if isinstance(ref, dict))
        # Older operations offered their generated list as one legacy field.
        # Honour its recorded disposition; do not resurrect the contained refs.
        if item.get('field') == 'attachment_refs' and isinstance(item.get('value'), list):
            for ref in item['value']:
                if isinstance(ref, dict) and ref.get('owner') == 'feedback' and ref.get('record_id'):
                    handled_feedback.add((ref['record_id'], ref.get('pin')))

    for ident in selected:
        artifact_id = index.reader_unit_creations.get((project, section_id, ident))
        if artifact_id and artifact_id not in creators:
            try:
                intent = owner._intent(project, root, artifact_id)
                inserted = intent['narrative_patch']['inserted']
                if (intent.get('section_id') != section_id or intent.get('inverse')
                        or not intent.get('kind', '').startswith('logical-')):
                    raise ValueError('The creating intent has a different logical owner.')
                inventory = {item['id']: item for item in intent['attachment_inventory']}
                decisions = {item['attachment_id']: item for item in intent['attachment_dispositions']}
                unresolved = {}
                for key, decision in decisions.items():
                    if decision.get('disposition') == 'retain-unresolved':
                        for destination in decision.get('successor_ids') or [row['paragraph_id'] for row in inserted]:
                            unresolved.setdefault(destination, []).append(key)
                destinations = {key: set(decision.get('successor_ids') or []) for key, decision in decisions.items()}
                signatures = {key: logical.fingerprint({field: item.get(field) for field in
                    ('kind', 'pin', 'owner', 'record_id', 'field', 'value')}) for key, item in inventory.items()}
                creators[artifact_id] = (inventory, decisions, {row['paragraph_id'] for row in inserted}, unresolved, destinations, signatures)
            except (KeyError, ValueError, OSError, TypeError):
                creators[artifact_id] = None
        creation = creators.get(artifact_id)
        if creation and ident not in creation[2]:
            creation = None
        if creation and artifact_id not in observed_creators:
            for item in creation[0].values():
                feedback_refs(item)
            observed_creators.add(artifact_id)
        refs = rows[ident].get('attachment_refs') or []
        refs = refs if isinstance(refs, list) else [refs]
        pending = {}
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            key = ref.get('id') if isinstance(ref.get('id'), str) and ref['id'] else logical.fingerprint(ref)
            if key in pending and pending[key] != ref:
                raise ValueError('Carried attachment identity has conflicting flat references.')
            pending[key] = ref
        if artifact_id and not creation:
            pending.setdefault('unavailable-origin', {'origin_intent_artifact_id': artifact_id})
        if creation:
            for key in creation[3].get(ident, []):
                pending.setdefault(key, {'id': key, 'pin': creation[0][key]['pin']})
        for ref in refs:
            if not isinstance(ref, dict):
                pending[logical.fingerprint(ref)] = {'unavailable_reference': ref}
        for key, ref in pending.items():
            item = creation[0].get(key) if creation else None
            decision = creation[1].get(key) if creation else None
            verified = (item and decision and ref.get('pin') == item.get('pin')
                and (ident in creation[4][key]
                     or decision.get('disposition') == 'retain-unresolved' and not creation[4][key])
                and decision.get('disposition') in {'assign', 'retain-unresolved'}
                and all(ref.get(field) == item.get(field) for field in ref
                        if field in {'id', 'kind', 'pin', 'owner', 'record_id'}))
            if verified and decision['disposition'] == 'assign' and item.get('field') in logical.ARRAY_FIELDS | logical.SCALAR_ATTACHMENT_FIELDS:
                continue  # Current typed fields above are the operative authority.
            if verified:
                witness = {'paragraph_id': ident, 'disposition': decision['disposition'],
                    'intent_artifact_id': artifact_id, 'scope_unresolved': not bool(creation[4][key])}
                previous = carried.get(item['id'])
                if previous:
                    if carried_signatures.get(item['id']) != creation[5][key]:
                        raise ValueError('Carried attachment identity has conflicting exact origins.')
                    previous['paragraph_ids'].append(ident)
                    previous['prior_dispositions'].append(witness)
                    if previous['prior_disposition'] != decision['disposition']:
                        previous['prior_disposition'] = 'MIXED'
                    continue
                carried_signatures[item['id']] = creation[5][key]
                value = copy.deepcopy({field: value for field, value in item.items()
                    if field not in {'paragraph_ids', 'prior_disposition', 'prior_dispositions'}})
                value.setdefault('original_paragraph_ids', copy.deepcopy(item.get('paragraph_ids', [])))
                value['paragraph_ids'] = [ident]
                value['prior_disposition'] = decision['disposition']
                value['prior_dispositions'] = [witness]
                if item.get('field') == 'attachment_refs':
                    # An older author explicitly assigned an opaque container.
                    # Its original ART remains inspectable; never unwrap it as
                    # invented typed acceptance or carry another refs-of-refs body.
                    value.update(field='unavailable_attachment_reference',
                        value={'attachment_id': item['id'], 'pin': item['pin'],
                               'origin_intent_artifact_id': artifact_id},
                        origin_unavailable=True,
                        label='Previously assigned legacy reference list: typed scopes require inspection')
            else:
                value = _attachment(project, section_id, ident, 'unavailable_attachment_reference',
                    ref, 'legacy', pin=logical.fingerprint(ref),
                    read=reader_plan.read_handle(project, section_id, paragraph_id=ident))
                value['label'] = 'Carried attachment reference: exact typed origin unavailable'
                value['origin_unavailable'] = True
            previous = carried.get(value['id'])
            if previous:
                if any(previous.get(field) != value.get(field) for field in ('kind', 'pin', 'owner', 'record_id', 'field', 'value')):
                    raise ValueError('Carried attachment identity has conflicting exact origins.')
                previous['paragraph_ids'].append(ident)
                previous.setdefault('prior_dispositions', []).extend(value.get('prior_dispositions') or [])
                if previous.get('prior_disposition') != value.get('prior_disposition'):
                    previous['prior_disposition'] = 'MIXED'
            else:
                carried[value['id']] = value
    return list(carried.values()), handled_feedback


def inputs(project, section_id, draft, root):
    """Read one authored section plus its complete selected-source marker cut."""
    from laplace.manuscript import reader_restructure as owner, bindings
    from laplace.manuscript import manuscript_source, projection_viewer
    root = Path(root).resolve()
    snapshot = owner._snapshot(project, section_id, root)
    selected = draft.get('paragraph_ids') or []
    rows = {row['paragraph_id']: row for row in snapshot['rows']}
    if len(set(selected)) != len(selected) or any(ident not in rows for ident in selected):
        raise ValueError('Choose exact active paragraph identities in this reader section.')
    cache = {}; readers = {}; attachments = []
    for ident in selected:
        view = reader_plan.section_view(project, root, snapshot['section'], snapshot['state']['sections'],
            snapshot['state']['authority']['plan_revision'], paragraph_id=ident, cache=cache)
        item = view['paragraph_plan']['paragraphs']['items'][0]
        readers[ident] = item['reader_basis']
        links = {entry.get('label'): entry.get('read') for entry in item.get('links', [])}
        original = rows[ident]
        for field in sorted(logical.ARRAY_FIELDS | logical.SCALAR_ATTACHMENT_FIELDS):
            values = original.get(field) or []
            values = values if isinstance(values, list) else [values]
            for value in values:
                kind = {'input_nodes': 'claim', 'citations': 'citation', 'equation_anchor': 'equation',
                        'figure_anchor': 'figure', 'qualification': 'qualification',
                        'from_previous': 'connection', 'to_next': 'connection'}[field]
                key = {'input_nodes': 'concept:', 'citations': 'citation:', 'equation_anchor': 'equations:',
                       'figure_anchor': 'figures:'}.get(field)
                pin = readers[ident]['inputs'].get(key + value) if key else logical.fingerprint(value)
                attachments.append(_attachment(project, section_id, ident, field, value, kind,
                    pin=pin or logical.fingerprint({'unresolved_input': field, 'value': value}),
                    read=links.get(value) or reader_plan.read_handle(project, section_id, paragraph_id=ident)))
        # Evidence is independently scoped, not silently accepted with its claim.
        for key, pin in readers[ident]['inputs'].items():
            if key.startswith('result:'):
                value = key.removeprefix('result:')
                attachment = _attachment(project, section_id, ident, 'evidence_refs', value, 'evidence',
                    pin=pin, read=links.get(value))
                attachment.update(owner='research', record_id=value)
                attachments.append(attachment)
        declared = set(reader_plan.PARAGRAPH_STRINGS) | set(reader_plan.PARAGRAPH_ARRAYS) | {'section_id', 'paragraph_id', 'attachment_refs'}
        for field in sorted(set(original) - declared):
            if original[field] not in (None, '', [], {}):
                attachments.append(_attachment(project, section_id, ident, field, original[field], 'legacy',
                    pin=logical.fingerprint(original[field]), read=reader_plan.read_handle(project, section_id, paragraph_id=ident)))
        for review in item.get('review', {}).get('records', []):
            attachment = _attachment(project, section_id, ident, 'review', review['id'], 'review',
                pin=logical.fingerprint(review), read=review.get('read'))
            attachment.update(owner='project-work', record_id=review['id'])
            attachments.append(attachment)
    carried, handled_feedback = _carried_attachments(project, section_id, selected, rows, root)
    attachments.extend(carried)
    # Provenance records can carry qualified claim/equation/note fields beyond
    # the narrative schema. Each nonempty value is an explicit scoped reference;
    # none is silently rebound to a new logical identity.
    for index,row in enumerate((snapshot['documents']['provenance'] or {}).get('paragraphs',[])):
        original_ids=row.get('spec_ids') or [row.get('spec_id')]
        matched=[ident for ident in selected if ident in original_ids]
        if not matched: continue
        values=dict(row)
        if row.get('origin') not in {'explicit-logical-restructure','explicit-presentation-restructure'}:
            values['original_occurrence']={'spec_ids':original_ids,'source':row.get('source')}
        for field,value in values.items():
            if row.get('origin') in {'explicit-logical-restructure','explicit-presentation-restructure'} and field in {'origin','semantic_currentness','scientific_acceptance','source_section','retained_provenance_index','retained_provenance_indices'}:continue
            if field in {'spec_id','spec_ids','source','paragraph_id'} or value in (None,'',[],{}):continue
            item=_attachment(project,section_id,','.join(matched),'provenance.'+field,value,'legacy',
                pin=logical.fingerprint(row),
                read=reader_plan.read_handle(project,section_id,paragraph_id=matched[0]))
            item.update(owner='reader-provenance',paragraph_ids=matched,provenance_index=index,
                original_spec_ids=original_ids,
                label='Original source provenance '+field.replace('_',' ')+': '+str(value)[:180])
            attachments.append(item)
    source, tree = cache.get('source_tree') or bindings.selected_tree(project, root)
    observation = manuscript_source.observation(project, root, source=source, source_tree=tree)
    occurrences = []; text_by_file = {}; seen = set()
    for item in tree.get('sources', []):
        file = item['file']
        if file not in text_by_file:
            text_by_file[file] = item['text']
            if _pin(text_by_file[file]) != item['raw_file_sha256']:
                raise ValueError('Selected-source body does not match its physical observation.')
        text = text_by_file[file]; lines = text.splitlines(keepends=True)
        for span in projection_viewer.parse_paragraphs(text):
            key = (file, span['start_line'], span['end_line'])
            if key in seen or not set(selected).intersection(span['spec_ids']):
                continue
            seen.add(key)
            row = {'file': file, 'line_start': span['start_line'], 'line_end': span['end_line'],
                'spec_ids': list(span['spec_ids']),
                'content_sha256': _pin(''.join(lines[span['start_line']-1:span['end_line']])),
                'basis': {'selection_identity': source['selection_identity'], 'source_digest': _pin(text)},
                'read': bindings.source_read(file, {'line': span['start_line'], 'line_end': span['end_line']}, project=project)}
            row['id'] = logical.occurrence_id(row)
            occurrences.append(row)
    # Select metadata before opening any feedback text. The original feedback
    # owner keeps the body and attribution; this decision stores only exact refs.
    from laplace.work import author_history_metrics as feedback_owner
    feedback_rows = []
    for index in feedback_owner._feedback_sources(root, project):
        feedback_rows.extend(row for row in index.rows if row.get('project') in (None, project))
    superseded = {row.get('supersedes') for row in feedback_rows if row.get('supersedes')}
    affected_files = {row['file'] for row in occurrences}
    ambiguous = []
    for row in feedback_rows:
        if (row['id'] in superseded or row.get('kind')=='paragraph-marker-restructure'
                or (row['id'], row['_hash']) in handled_feedback):
            # Logical marker effects are exact history/lineage, not a newly
            # authored prose protection that grows into future dependencies.
            continue
        anchor = row.get('anchor') if isinstance(row.get('anchor'), dict) else {}
        scoped = set(anchor.get('spec_ids') or []) | {anchor.get('paragraph_id')}
        matched = [ident for ident in selected if ident in scoped]
        if matched:
            kind = 'protection' if row.get('record') == 'author-edit' else 'note'
            attachment = _attachment(project, section_id, ','.join(matched), kind, row['id'], kind,
                pin=row['_hash'], read=feedback_owner._read_handle(project,
                    {'view': 'record', 'id': 'activity:feedback:' + row['id']}))
            attachment.update(paragraph_ids=matched, owner='feedback', record_id=row['id'],
                              original_spec_ids=sorted(value for value in scoped if isinstance(value, str)))
            attachments.append(attachment)
        elif any(owner._same_source_file(row.get('file'), file, root, root/source['manuscript_dir']) for file in affected_files):
            ambiguous.append({'id': row['id'], 'pin': row['_hash']})
    if ambiguous:
        attachment = _attachment(project, section_id, ','.join(selected), 'unlinked_feedback', ambiguous, 'legacy',
            pin=logical.fingerprint(ambiguous), read=feedback_owner._read_handle(project, {'projection': 'feedback', 'scope': 'project'}))
        attachment.update(paragraph_ids=selected, owner='feedback',
            label='Legacy feedback in affected source: logical scope is unproved',
            ambiguity='Original feedback stays with its owner; this change never invents its original paragraph scope.')
        attachments.append(attachment)
    return {'snapshot': snapshot, 'readers': readers, 'attachments': attachments,
            'occurrences': occurrences, 'source': source, 'observation': observation,
            'source_texts': text_by_file,'coverage':{'complete':not bool(tree.get('diagnostics'))},
            'inventory_diagnostics':copy.deepcopy(tree.get('diagnostics') or [])}


def preview(project, section_id, kind, draft, root, *, _current=None):
    from laplace.manuscript import reader_restructure as owner
    from laplace.writing import records
    current = _current or inputs(project, section_id, draft, root)
    snapshot = current['snapshot']; ids = draft.get('paragraph_ids') or []
    count = draft.get('successor_count', 2 if kind == 'logical-split' else 1)
    path = snapshot['paths']['narrative'].relative_to(Path(root).resolve()).as_posix()
    reserved = records.index(root).reader_reserved_ids.get((project, path), set())
    offered = logical.offer_successors(project, section_id, kind, ids, count,
        narrative_revision=owner.revision(snapshot['raw']['narrative']),
        current_ids=[row['paragraph_id'] for row in snapshot['rows']], reserved_ids=reserved)
    guards = {'expected_plan_revision': snapshot['state']['authority']['plan_revision'],
        'expected_narrative_revision': owner.revision(snapshot['raw']['narrative']),
        'expected_decision_revision': owner.revision(snapshot['raw']['decisions']),
        'expected_provenance_revision': owner.revision(snapshot['raw']['provenance']),
        'expected_attachment_revision': logical.fingerprint(current['attachments']),
        'expected_selection': current['source'].get('selection_identity'),
        'source_guards': {row['file']: row['basis']['source_digest'] for row in current['occurrences']},
        'expected_reader_basis': current['readers'],
        'expected_source_set_revision': current['observation']['source_revision']}
    prepared = logical.prepare(project, section_id, kind, rows=snapshot['rows'], selected_ids=ids,
        successor_ids=offered, occurrences=current['occurrences'], attachments=current['attachments'],
        basis={'expected_reader_basis': current['readers'], 'source_set_revision': guards['expected_source_set_revision'],
               'attachment_revision': guards['expected_attachment_revision']},
        draft=draft, coverage=current['coverage'])
    staged = logical.stage_markers(current['source_texts'], prepared) if prepared['ready'] else {'source_changes': []}
    token = logical.fingerprint({'project': project, 'section_id': section_id, 'kind': kind,
                                 'guards': guards, 'draft': draft})
    descriptors = [{'name': name, 'label': name.replace('_', ' ').capitalize(), 'type': 'string',
                    'required': name in {'function', 'proposition'}} for name in reader_plan.PARAGRAPH_STRINGS
                   if name in logical.AUTHORED_FIELDS]
    successors = [{'paragraph_id': row['paragraph_id'], 'fields': descriptors,
                   'values': {key: row.get(key, '') for key in sorted(logical.AUTHORED_FIELDS)}}
                  for row in prepared['successors']]
    return {'schema_version': owner.SCHEMA, 'project': project, 'section_id': section_id, 'kind': kind,
        'draft': copy.deepcopy(draft), 'guards': guards, 'restructure_token': token, 'preview_only': True,
        'ready': prepared['ready'], 'needs_input': prepared['needs_input'], 'successors': successors,
        'inventory_diagnostics':current['inventory_diagnostics'],
        'attachment_inventory': [{**row, 'allowed_dispositions': sorted(logical.DISPOSITIONS),
            'allowed_successor_ids': offered} for row in prepared['attachment_inventory']],
        'occurrence_inventory': prepared['occurrence_inventory'],
        'predecessors': [{'paragraph_id': ident, 'values': copy.deepcopy(next(row for row in snapshot['rows'] if row['paragraph_id']==ident)),
            'read': reader_plan.read_handle(project, section_id, paragraph_id=ident)} for ident in ids],
        'review_obligations': prepared['review_obligations'], 'semantic_currentness': 'NOT_REVIEWED',
        'source_required': bool(current['occurrences']), 'source_changes': staged['source_changes'],
        'retired_ids': ids, 'successor_ids': offered,
        'apply_action': owner.action(project,section_id,'restructure',kind=kind,restructure_token=token,guards=guards) if prepared['ready'] else None}


def _encode(value):
    import json
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode() if value is not None else None


def _prepared(project, section_id, kind, draft, root, current=None):
    """Reconstruct the same pure patch from current owners, not a UI projection."""
    from laplace.manuscript import reader_restructure as owner
    current = current or inputs(project, section_id, draft, root)
    value = preview(project, section_id, kind, draft, root, _current=current)
    patch = logical.prepare(project, section_id, kind, rows=current['snapshot']['rows'],
        selected_ids=draft['paragraph_ids'], successor_ids=value['successor_ids'],
        occurrences=current['occurrences'], attachments=current['attachments'],
        basis={'expected_reader_basis': current['readers'],
               'source_set_revision': current['observation']['source_revision'],
               'attachment_revision': value['guards']['expected_attachment_revision']},
        draft=draft, coverage=current['coverage'])
    if not patch['ready']:
        raise ValueError('Complete every authored successor, attachment disposition and physical occurrence assignment.')
    return value, current, patch


def _source_postimages(root, changes, *, inverse=False):
    """Apply only witnessed marker hunks, with linear offsets and exact file pins."""
    result = {}
    for change in changes:
        path = Path(root)/change['file']; raw = path.read_bytes()
        expected = change['after_sha256'] if inverse else change['before_sha256']
        if _pin(raw.decode()) != expected:
            raise ValueError('CHANGED_INPUT: exact logical source postimage is unavailable.')
        lines = raw.decode().splitlines(keepends=True)
        edits = []; shift = 0
        for edit in sorted(change['marker_edits'], key=lambda row: row['line_start']):
            old, new = (edit['after'], edit['before']) if inverse else (edit['before'], edit['after'])
            start = edit['line_start'] + (shift if inverse else 0)
            end = start - 1 + len(old.splitlines(keepends=True))
            if ''.join(lines[start-1:end]) != old:
                raise ValueError('CHANGED_INPUT: exact marker frame changed; no prose was rewritten.')
            edits.append((start, end, new))
            shift += len(edit['after'].splitlines()) - len(edit['before'].splitlines())
        for start, end, new in reversed(edits):
            lines[start-1:end] = new.splitlines(keepends=True)
        after = ''.join(lines)
        wanted = change['before_sha256'] if inverse else change['after_sha256']
        if _pin(after) != wanted:
            raise ValueError('Scoped marker patches do not reproduce the admitted exact postimage.')
        result[change['file']] = after
    return result


def _reverse_changes(changes):
    reversed_changes = []
    for row in changes:
        edits = []; shift = 0
        for edit in sorted(row['marker_edits'], key=lambda item: item['line_start']):
            start = edit['line_start'] + shift
            edits.append({**edit, 'line_start': start,
                'line_end': start - 1 + len(edit['after'].splitlines()),
                'before': edit['after'], 'after': edit['before']})
            shift += len(edit['after'].splitlines()) - len(edit['before'].splitlines())
        reversed_changes.append({**row, 'before_sha256': row['after_sha256'],
            'after_sha256': row['before_sha256'], 'marker_edits': edits})
    return reversed_changes


def _provenance_patch(current, prepared, changes, root):
    """Retain affected occurrence values once; disjoint rows stay current state."""
    from laplace.manuscript import reader_restructure as owner
    snapshot = current['snapshot']; document = snapshot['documents']['provenance']
    rows = (document or {}).get('paragraphs', [])
    mappings = {row['occurrence_id']: row for row in prepared['source_mappings']}
    occurrences = {row['id']: row for row in prepared['occurrence_inventory']}
    removed = []; inserted = []; covered = set()
    home = root/current['source']['manuscript_dir']
    for index, row in enumerate(rows):
        loc = row.get('source') or {}
        matched = [occ for occ in occurrences.values()
            if owner._same_source_file(loc.get('file'), occ['file'], root, home)
            and loc.get('line_start') == occ['line_start'] and isinstance(loc.get('line_end'),int)
            and loc['line_end'] <= occ['line_end']
            and not ''.join(current['source_texts'][occ['file']].splitlines(keepends=True)[loc['line_end']:occ['line_end']]).strip()]
        if len(matched) > 1:
            raise ValueError('Ambiguous exact provenance occurrence; no logical publication was admitted.')
        old_ids=row.get('spec_ids') or [row.get('spec_id')]
        if not matched and set(old_ids).intersection(prepared['retired_ids']):
            removed.append({'index':index,'row':copy.deepcopy(row)})
        if matched:
            occ = matched[0]; mapping = mappings[occ['id']]; covered.add(occ['id'])
            removed.append({'index': index, 'row': copy.deepcopy(row)})
            updated = {key:copy.deepcopy(row[key]) for key in ('paragraph_id',) if key in row}
            updated['source']={**loc,'line_start':occ['line_start'],'line_end':occ['line_end']}
            updated.update(spec_ids=mapping['after_ids'],
                spec_id=mapping['after_ids'][0] if mapping['after_ids'] else '',
                semantic_currentness='NOT_REVIEWED',
                origin='explicit-logical-restructure')
            inserted.append(updated)
    for occ in occurrences.values():
        if occ['id'] not in covered:
            ids = mappings[occ['id']]['after_ids']
            inserted.append({'spec_id': ids[0] if ids else '', 'spec_ids': ids,
                'source': {key: occ[key] for key in ('file', 'line_start', 'line_end')},
                'origin': 'explicit-logical-restructure', 'semantic_currentness': 'NOT_REVIEWED'})
    return {'absent_before': document is None, 'removed': removed, 'inserted': inserted,
            'insert_at': min((row['index'] for row in removed), default=len(rows)),
            'changes': [{'file': row['file'], 'marker_edits': [{key: edit[key] for key in ('line_start', 'line_end', 'before', 'after')}
                for edit in row['marker_edits']]} for row in changes],
            'manuscript_dir': current['source']['manuscript_dir']}


def _apply_provenance(document, patch, section_id, root, *, inverse=False):
    from laplace.manuscript import reader_restructure as owner
    result = copy.deepcopy(document or {'section_id': section_id, 'paragraphs': []})
    rows = result.get('paragraphs', [])
    def relocate(row, backwards=False):
        row = copy.deepcopy(row); loc = row.get('source')
        if not isinstance(loc, dict): return row
        for change in patch['changes']:
            if not owner._same_source_file(loc.get('file'), change['file'], root, root/patch['manuscript_dir']): continue
            old_start, old_end = loc.get('line_start'), loc.get('line_end')
            if not isinstance(old_start, int) or not isinstance(old_end, int): continue
            cumulative = 0; delta_start = 0; delta_end = 0
            for edit in change['marker_edits']:
                delta = len(edit['after'].splitlines()) - len(edit['before'].splitlines())
                edge = edit['line_end'] + (cumulative + delta if backwards else 0)
                if old_start > edge: delta_start += -delta if backwards else delta
                if old_end > edge: delta_end += -delta if backwards else delta
                cumulative += delta
            loc['line_start'] += delta_start; loc['line_end'] += delta_end
        return row
    at = patch['insert_at']
    if inverse:
        inserted = [relocate(row) for row in patch['inserted']]
        if rows[at:at+len(inserted)] != inserted:
            raise ValueError('Exact logical provenance postimage changed; inverse is unavailable.')
        rest = rows[:at] + rows[at+len(inserted):]
        rest = [relocate(row, True) for row in rest]
        removed = {row['index']: row['row'] for row in patch['removed']}
        restored = []; cursor = iter(rest)
        for index in range(len(rest)+len(removed)):
            restored.append(copy.deepcopy(removed[index]) if index in removed else next(cursor))
        result['paragraphs'] = restored
        return None if patch['absent_before'] else result
    removed = {row['index']: row['row'] for row in patch['removed']}
    if any(index >= len(rows) or rows[index] != old for index, old in removed.items()):
        raise ValueError('Exact logical provenance preimage changed before publication.')
    retained = [copy.deepcopy(row) for index, row in enumerate(rows) if index not in removed]
    retained[at:at] = copy.deepcopy(patch['inserted'])
    result['paragraphs'] = [relocate(row) for row in retained]
    return result


def phase(project, root, intent, artifact_id):
    """Actual source fate and exact retained metadata steps, including plan-only."""
    from laplace.manuscript import reader_restructure as owner
    from laplace.manuscript import storyboard
    files = []
    for change in intent['source_changes']:
        path = root/change['file']
        files.append({'scope': 'repository', 'path': change['file'],
            'before_sha256': change['before_sha256'], 'after_sha256': change['after_sha256'],
            'observed_after_sha256': owner.revision(path.read_bytes()) if path.is_file() else None})
    effect = owner.source_effects.receipt(project, intent['guards']['expected_selection'], files,
        complete=False, required=[{'owner': 'logical-reader-metadata', 'status': 'UNPROVED'}]) if files else None
    source_ok = not files or effect['state'] in {'COMMITTED', 'UNCHANGED'}
    snapshot = owner._snapshot(project, intent['section_id'], root)
    remaining = ['source-history', 'author-protection'] if files else []
    remaining += ['narrative-publication', 'provenance-publication', 'receipt-publication']
    value = {'schema_version': owner.SCHEMA, 'project': project, 'section_id': intent['section_id'],
        'kind': intent['kind'], 'inverse_direction':'REDO' if intent.get('inverse',False) else 'UNDO', 'complete': False, 'source_required': bool(files), 'source_unchanged': not files,
        'source_committed': source_ok, 'remaining_steps': remaining,
        'guards': {**intent['guards'], 'expected_decision_revision': owner.revision(snapshot['raw']['decisions'])},
        'receipt': {'id': intent['source_receipt_id'], 'intent_artifact_id': artifact_id,
            'kind': intent['kind'], 'remaining_steps': remaining},
        'metadata_path': intent['metadata_path'], 'source_changes': intent['source_changes'],
        'retired_ids': intent['retired_ids'], 'successor_ids': intent['successor_ids'],
        'review_obligations': intent['review_obligations'], 'semantic_currentness': 'NOT_REVIEWED',
        'plan_publication': storyboard.reader_publication('logical-paragraph-restructure', 'PARTIAL', False, 0)}
    if effect: value['source_effect'] = effect
    return value


def _actions(project, section_id, value):
    from laplace.manuscript import reader_restructure as owner
    value = owner._actions(project, section_id, value)
    fields = {'receipt_id': value['receipt']['id'], 'intent_artifact_id': value['receipt']['intent_artifact_id'],
              'guards': value['guards']}
    value.pop('undo_action', None)
    if value['complete'] and not value.get('metadata_only'):
        if value.get('inverse_currentness',{}).get('status','CURRENT')=='CURRENT':
            value['undo_action'] = owner.action(project, section_id, 'undo-restructure', **fields)
            value['undo_action']['title']='Redo this structural operation' if value.get('inverse_direction')=='REDO' else 'Undo this structural operation'
    elif value['source_committed'] and value['remaining_steps'] and not value.get('publication_not_attempted'):
        value['recovery_action'] = owner.action(project, section_id, 'recover-restructure', **fields)
    else:
        value.pop('recovery_action', None)
    return value


def _publication_metadata(project, root, intent, value):
    """Idempotent metadata follow-through; it never calls a source writer."""
    from laplace.manuscript import reader_restructure as owner
    from laplace.projects import artifacts
    from laplace.manuscript import manuscript_source, projection_viewer, storyboard
    from laplace.core.records import journal
    from laplace.pipeline import edits
    snapshot = owner._snapshot(project, intent['section_id'], root)
    if not value['source_committed']:
        raise ValueError('The exact logical source effect is not a proved commit; inspect it.')
    source = manuscript_source.resolve(project, repo_root=root)
    reconciled=value.get('metadata_reconciliation')
    if reconciled:
        from laplace.manuscript.reader_restructure_reconciliation import verify_adopted
        verify_adopted(project,root,intent,value)
    if manuscript_source.selection_identity(source, project) != intent['guards']['expected_selection']:
        raise ValueError('CHANGED_INPUT: logical source selection changed; do not replay the source effect.')
    for change in intent['source_changes']:
        if owner.revision((root/change['file']).read_bytes()) != (reconciled['current_observation']['guards']['source_guards'][change['file']] if reconciled else change['after_sha256']):
            raise ValueError('CHANGED_INPUT: logical source changed after commit; no source replay is allowed.')
    observed_source=manuscript_source.observation(project,root,source=source)
    expected_files=dict(intent['source_file_guards'])
    expected_files.update({row['file']:row['after_sha256'].removeprefix('sha256:') for row in intent['source_changes']})
    if reconciled:expected_files=reconciled['current_observation']['file_revisions']
    if observed_source['file_revisions']!=expected_files:
        raise ValueError('CHANGED_INPUT: selected-source traversal/files changed outside the admitted marker effect.')
    if not reconciled:_verify_inputs(project,root,intent,snapshot)
    if snapshot['state']['authority']['plan_revision'] != intent['guards']['expected_plan_revision']:
        raise ValueError('CHANGED_INPUT: declared reader plan changed during logical publication.')
    refs = [row for row in (snapshot['documents']['decisions'] or {}).get('decisions', []) if row.get('owner')=='reader-restructure']
    if len(refs)!=1 or refs[0].get('intent_artifact_id') != value['receipt']['intent_artifact_id']:
        raise ValueError('CHANGED_INPUT: exact logical intent pointer changed.')
    if owner.fingerprint([row for row in (snapshot['documents']['decisions'] or {}).get('decisions', []) if row.get('owner')!='reader-restructure']) != intent['decision_other_revision']:
        raise ValueError('CHANGED_INPUT: unrelated reader decisions changed during logical publication.')
    intended = {}
    for name in ('narrative', 'provenance'):
        observed = owner.revision(snapshot['raw'][name])
        if name=='provenance' and reconciled:
            from laplace.manuscript.reader_restructure_reconciliation import provenance_document
            intended[name]=provenance_document(project,root,intent,snapshot,reconciled)
            if owner.revision(_encode(intended[name]))!=reconciled['provenance_after_revision']:
                raise ValueError('The explicitly adopted provenance postimage changed.')
        elif observed == intent[name+'_after_revision']:
            intended[name] = snapshot['documents'][name]
        elif observed == intent['guards']['expected_'+name+'_revision']:
            if name == 'narrative':
                document = copy.deepcopy(snapshot['documents'][name])
                document['paragraphs'] = logical.apply_narrative_patch(document['paragraphs'], intent['narrative_patch'], inverse=intent.get('inverse', False))
            else:
                document = _apply_provenance(snapshot['documents'][name], intent['provenance_patch'], intent['section_id'], root, inverse=intent.get('inverse', False))
            if owner.revision(_encode(document)) != intent[name+'_after_revision']:
                raise ValueError('The scoped logical '+name+' patch does not reproduce its admitted postimage.')
            intended[name] = document
        else:
            raise ValueError('CHANGED_INPUT: logical '+name+' changed outside the exact pending publication.')
    finished = []; versions = []
    home = root/source['manuscript_dir']
    for change in intent['source_changes']:
        history_source = 'paragraph-restructure:'+value['receipt']['intent_artifact_id']
        path = root/change['file']
        matches = [row for row in projection_viewer._load_saves_index(home).get('saves', [])
            if row.get('source')==history_source and row.get('sha')==change['after_sha256'].removeprefix('sha256:')]
        if len(matches)>1: raise ValueError('Ambiguous exact logical source-history receipt.')
        version = matches[0] if matches else None if reconciled else projection_viewer.bank_editor_save(home, path, path.read_bytes(),
            author=intent['actor'].get('kind','unknown'), surface='reader-restructure', source=history_source)
        if version:versions.append(version['version_id'])
        ident = 'EDIT-RESTRUCT-'+value['receipt']['intent_artifact_id']+'-'+logical.fingerprint(change['file']).split(':')[1][:12]
        from laplace.manuscript.projection_viewer import _PARA_RE
        ids=list(dict.fromkeys(match.group(1) for row in change['marker_edits'] for line in row['after'].splitlines()
            if (match:=_PARA_RE.fullmatch(line))))
        record = edits.make_author_edit(intent['section_id'], ids[0] if ids else '', change['file'],
            ''.join(row['before'] for row in change['marker_edits']), ''.join(row['after'] for row in change['marker_edits']),
            kind='paragraph-marker-restructure', lines=[min(row['line_start'] for row in change['marker_edits']), max(row['line_end'] for row in change['marker_edits'])],
            project=project, actor='eigen:session' if intent['actor'].get('kind')=='agent' else 'author', rec_id=ident, spec_ids=ids)
        feedback = home/'feedback/feedback.jsonl'; feedback.parent.mkdir(parents=True, exist_ok=True)
        index = owner._protection_index(root, feedback); matches = index.by_id.get(ident) or []
        if len(matches)>1: raise ValueError('Ambiguous exact logical author-protection record.')
        if matches:
            actual = owner.records.raw_indexed_record(index, matches[0])
            if any(actual.get(key)!=record.get(key) for key in ('record','id','project','before','after','anchor','kind','source')):
                raise ValueError('Exact logical protection record differs from admitted marker changes.')
        else: journal.bank_row(feedback.relative_to(root).as_posix(), record, root=root)
    if intent['source_changes']: finished += ['source-history', 'author-protection']
    for name in ('narrative', 'provenance'):
        path = snapshot['paths'][name]
        if owner.revision(snapshot['raw'][name]) != (reconciled['provenance_after_revision'] if name=='provenance' and reconciled else intent[name+'_after_revision']):
            metadata = {'path': path.relative_to(root).as_posix(), 'subjects': {}, 'reserved_ids': intent['reserved_ids'] if name=='narrative' else [],
                'logical_lineage': {'section_id': intent['section_id'], 'retired_ids': intent['retired_ids'],
                    'successor_ids': intent['successor_ids'], 'intent_artifact_id': value['receipt']['intent_artifact_id'],
                    'inverse': intent.get('inverse',False), 'source_receipt_id':intent['source_receipt_id']}}
            if intended[name] is None:
                artifacts.restore_owned_absence(root, project, path, owner.revision(snapshot['raw'][name]).removeprefix('sha256:'), metadata)
            else: owner._store(project, root, path, intended[name], snapshot['raw'][name], metadata=metadata)
        finished.append(name+'-publication')
    result = copy.deepcopy(value); result.update(complete=True, remaining_steps=[], source_receipt_id=intent['source_receipt_id'])
    result.pop('error',None)
    result['receipt'] = {**value['receipt'], 'id': None, 'remaining_steps': [], 'versions': versions}
    observed = owner._snapshot(project, intent['section_id'], root)
    result['guards'].update(expected_narrative_revision=owner.revision(observed['raw']['narrative']),
        expected_provenance_revision=owner.revision(observed['raw']['provenance']),
        expected_decision_revision=owner.revision(observed['raw']['decisions']),
        source_guards={row['file']:row['after_sha256'] for row in intent['source_changes']})
    result['plan_publication'] = storyboard.reader_publication('logical-paragraph-restructure', 'COMMITTED', True, 2)
    if result.get('source_effect'):
        result['source_effect'] = owner.source_effects.receipt(project, intent['guards']['expected_selection'], result['source_effect']['files'],
            complete=True, required=[{'owner': name, 'status':'COMPLETE'} for name in finished])
    from laplace.core.receipts import bundle
    metadata_files=[{'scope':'repository','path':snapshot['paths'][name].relative_to(root).as_posix(),
        'before_sha256':owner.revision(snapshot['raw'][name]),
        'after_sha256':owner.revision(_encode(intended[name])),
        'observed_after_sha256':owner.revision(snapshot['paths'][name].read_bytes()) if snapshot['paths'][name].is_file() else None}
        for name in ('narrative','provenance')]
    result['owned_changes']=bundle(files=[*(result.get('source_effect') or {}).get('files',[]),*metadata_files],
        views=['manuscript','document','structure','history'] if intent['source_changes'] else ['structure','history'])
    if reconciled:
        from laplace.manuscript.reader_restructure_reconciliation import qualify_result
        result=qualify_result(result,value,history_unavailable=len(versions)!=len(intent['source_changes']))
    return _actions(project, intent['section_id'], owner._record_receipt(project, root, result))


def publish_metadata(project, root, intent, value):
    from laplace.manuscript import reader_restructure as owner
    try:
        return _publication_metadata(project, root, intent, value)
    except Exception as exc:
        result = copy.deepcopy(value); result['complete'] = False; result['error'] = str(exc); result['source_receipt_id']=intent['source_receipt_id']
        snapshot = owner._snapshot(project, intent['section_id'], root)
        result['remaining_steps'] = [name+'-publication' for name in ('narrative','provenance')
            if owner.revision(snapshot['raw'][name]) != intent[name+'_after_revision']]
        if intent['source_changes']:
            result['remaining_steps'] = ['source-history', 'author-protection', *result['remaining_steps']]
        result['remaining_steps'].append('receipt-publication')
        result['guards'].update(expected_narrative_revision=owner.revision(snapshot['raw']['narrative']),
            expected_provenance_revision=owner.revision(snapshot['raw']['provenance']),
            expected_decision_revision=owner.revision(snapshot['raw']['decisions']))
        result['receipt'] = {**result['receipt'], 'id': None, 'remaining_steps': result['remaining_steps']}
        try: result = owner._record_receipt(project, root, result)
        except Exception:
            result = copy.deepcopy(value); result.update(complete=False,error=str(exc),receipt_recorded=False)
        return _actions(project, intent['section_id'], result)


def apply(project, root, value, *, actor=None, inverse_intent=None, admitted=None):
    """Reserve one scoped ART before one marker effect; no historical body nesting."""
    import uuid
    from laplace.manuscript import reader_restructure as owner
    from laplace.manuscript import manuscript_source, manuscript_structure
    sid = value['section_id']; snapshot = owner._snapshot(project, sid, root)
    backwards = not inverse_intent.get('inverse',False) if inverse_intent else False
    if inverse_intent:
        _verify_inputs(project,root,inverse_intent,snapshot)
        changes = _reverse_changes(inverse_intent['source_changes'])
        narrative_patch = inverse_intent['narrative_patch']; provenance_patch = inverse_intent['provenance_patch']
        narrative = copy.deepcopy(snapshot['documents']['narrative'])
        narrative['paragraphs'] = logical.apply_narrative_patch(narrative['paragraphs'], narrative_patch, inverse=backwards)
        provenance = _apply_provenance(snapshot['documents']['provenance'], provenance_patch, sid, root, inverse=backwards)
        assignments = copy.deepcopy(inverse_intent['occurrence_dispositions'])
        retired, successors = inverse_intent['successor_ids'], inverse_intent['retired_ids']
        attachments = inverse_intent['attachment_dispositions']
        occurrence_mapping={'before':copy.deepcopy(inverse_intent['occurrence_mapping']['after']), 'after':copy.deepcopy(inverse_intent['occurrence_mapping']['before'])}
        reserved = inverse_intent['reserved_ids']
        source_files = dict(inverse_intent['source_file_guards'])
        source_files.update({row['file']:row['before_sha256'].removeprefix('sha256:') for row in changes})
    else:
        if admitted is None:
            inspected,current,prepared=_prepared(project,sid,value['kind'],value['draft'],root)
            if inspected['restructure_token']!=value['restructure_token']:raise ValueError('CHANGED_INPUT: logical basis changed before admission.')
        else:current,prepared=admitted
        changes = value['source_changes']; narrative_patch = prepared['narrative_patch']
        provenance_patch = _provenance_patch(current, prepared, changes, root)
        narrative = copy.deepcopy(snapshot['documents']['narrative'])
        narrative['paragraphs'] = logical.apply_narrative_patch(snapshot['rows'], narrative_patch)
        provenance = _apply_provenance(snapshot['documents']['provenance'], provenance_patch, sid, root)
        assignments = prepared['occurrence_dispositions']; attachments = prepared['attachment_dispositions']
        retired, successors = value['retired_ids'], value['successor_ids']; reserved = successors
        source_files = current['observation']['file_revisions']
        occurrence_mapping=_occurrence_postimages(prepared,changes)
    if any(len(_encode(document) or b'')>reader_plan.MAX_BYTES for document in (narrative,provenance)):
        raise ValueError('The resulting reader artifact exceeds the existing 2 MB reader-owner resource bound; split the authored plan change.')
    if manuscript_source.observation(project,root)['file_revisions']!=source_files:
        raise ValueError('CHANGED_INPUT: the consumed selected-source file set changed before structural admission.')
    outputs = _source_postimages(root, changes)
    intent = {'schema_version': owner.SCHEMA, 'project': project, 'section_id': sid, 'kind': value['kind'],
        'guards': value['guards'], 'restructure_token': value['restructure_token'], 'actor': actor or {'kind':'human'},
        'source_changes': changes, 'occurrence_mapping':occurrence_mapping, 'source_file_guards':source_files, 'narrative_patch': narrative_patch, 'provenance_patch': provenance_patch,
        'inverse': backwards, 'retired_ids': retired, 'successor_ids': successors, 'reserved_ids': reserved,
        'attachment_dispositions': attachments, 'occurrence_dispositions': assignments,
        'attachment_inventory': copy.deepcopy(inverse_intent['attachment_inventory'] if inverse_intent else current['attachments']),
        'review_obligations': value.get('review_obligations') or [],
        'source_receipt_id': 'RPUB-'+uuid.uuid4().hex,
        'metadata_path': snapshot['paths']['narrative'].relative_to(root).as_posix(),
        'decision_path': snapshot['paths']['decisions'].relative_to(root).as_posix(),
        'decision_other_revision': owner.fingerprint([row for row in (snapshot['documents']['decisions'] or {}).get('decisions',[]) if row.get('owner')!='reader-restructure']),
        'narrative_after_revision': owner.revision(_encode(narrative)),
        'provenance_after_revision': owner.revision(_encode(provenance))}
    if len(_encode(intent))>reader_plan.MAX_BYTES:
        raise ValueError('The complete occurrence/attachment intent exceeds the existing 2 MB reader-artifact resource bound; no source effect was attempted.')
    path = snapshot['paths']['decisions'].with_suffix('.restructure-intent.json')
    _, before = reader_plan._json(path)
    saved = owner._store(project, root, path, intent, before, metadata={'path': intent['metadata_path'],
        'subjects': {}, 'reserved_ids': reserved,
        'restructure_intent': {'section_id': sid, 'kind': value['kind'], 'token': value['restructure_token'],
            'source_receipt_id': intent['source_receipt_id']}})
    decisions = copy.deepcopy(snapshot['documents']['decisions'] or {'section_id':sid,'decisions':[]})
    decisions['decisions'] = [row for row in decisions.get('decisions',[]) if row.get('owner')!='reader-restructure']
    decisions['decisions'].append({'owner':'reader-restructure','kind':'paragraph-restructure','state':'INTENT',
        'section':sid, 'spec_ids':retired, 'successor_ids':successors,
        'intent_artifact_id':saved['id'], 'restructure_token':value['restructure_token'],
        'rationale':'Explicit logical restructuring; prior acceptance remains historical.'})
    try:owner._store(project,root,snapshot['paths']['decisions'],decisions,snapshot['raw']['decisions'])
    except Exception as exc:
        result=phase(project,root,intent,saved['id'])
        result.update(error='Intent retained; effect admission did not complete: '+str(exc),publication_not_attempted=True,remaining_steps=[])
        result['receipt']['remaining_steps']=[]
        try:result=owner._record_receipt(project,root,result)
        except Exception:result['receipt_recorded']=False
        return _actions(project,sid,result)
    error = None; written = []
    paths = [root/row['file'] for row in changes]
    from contextlib import nullcontext
    with manuscript_source.selection_mutation(project, root), (manuscript_source.source_mutation(paths) if paths else nullcontext()):
        try:
            observed_source=manuscript_source.observation(project,root)
            if observed_source['file_revisions']!=source_files:
                raise ValueError('CHANGED_INPUT: selected-source files changed before the marker effect.')
            for change in changes:
                path = root/change['file']
                manuscript_source.source_access(project,path,root,writable=True,expected_selection=value['guards']['expected_selection'])
                before = path.read_bytes()
                manuscript_structure._write_source(path, outputs[change['file']], change['before_sha256'])
                written.append((path,before,change['after_sha256']))
        except Exception as exc:
            error = str(exc)
            for path, before, expected in reversed(written):
                try: manuscript_structure._write_source(path, before.decode(), expected)
                except Exception as rollback: error += '; rollback requires inspection: '+str(rollback)
        result = phase(project,root,intent,saved['id'])
    try: result = owner._record_receipt(project,root,result)
    except Exception as exc:
        result.update(error='Effect observation retained in exact ART; receipt unavailable: '+str(exc),receipt_recorded=False)
        return _actions(project,sid,result)
    if error or not result['source_committed']:
        result['error'] = error or 'Physical source outcome requires inspection.'
        if not changes:
            result.update(publication_not_attempted=True,remaining_steps=[])
            result['receipt']['remaining_steps']=[]
            try:result=owner._record_receipt(project,root,{**result,'receipt':{**result['receipt'],'id':None}})
            except Exception:pass
        return _actions(project,sid,result)
    return publish_metadata(project,root,intent,result)


def observed_reader_basis(project,root,intent,snapshot):
    """Reobserve canonical original scoped subjects after their own row effect."""
    rows=snapshot['rows']
    original_ids={row['row']['paragraph_id'] for row in intent['narrative_patch']['removed']}
    if not original_ids.issubset({row['paragraph_id'] for row in rows}):
        rows=logical.apply_narrative_patch(rows,intent['narrative_patch'],inverse=True)
    cp,_=reader_plan._paths(project,root,intent['section_id'])
    contracts=reader_plan._contracts(reader_plan._json(cp)[0])
    cache={'paragraph_rows':rows}
    architecture=reader_plan._architecture(snapshot['section'],snapshot['state']['sections'],root,cache=cache)
    observed={}
    for ident,basis in intent['guards']['expected_reader_basis'].items():
        subject=next((row for row in rows if row['paragraph_id']==ident),None)
        if subject is None or logical.fingerprint(subject)!=basis['subject_revision']:
            raise ValueError('CHANGED_INPUT: original logical subject no longer matches retained custody.')
        pins,_=reader_plan._inputs(project,root,snapshot['section'],snapshot['state']['sections'],subject,contracts,architecture,paragraph=True,cache=cache)
        observed[ident]={**copy.deepcopy(basis),'inputs':pins}
    return observed


def _verify_inputs(project,root,intent,snapshot):
    if observed_reader_basis(project,root,intent,snapshot)!=intent['guards']['expected_reader_basis']:
        raise ValueError('CHANGED_INPUT: logical reader dependencies changed; retained publication requires scoped reconciliation.')


def lineage_read(project, section_id, metadata, root):
    from laplace.manuscript import reader_restructure as owner
    from laplace.writing import records
    latest=records.index(root).reader_restructure_receipts.get((project,metadata['intent_artifact_id']))
    receipt=((latest or {}).get('reader_metadata',{}).get('restructure') or {}).get('receipt') or {}
    fields={'view':'restructure','section_ids':[section_id],
        'receipt_id':receipt.get('id') or metadata['source_receipt_id'],
        'intent_artifact_id':metadata['intent_artifact_id']}
    return {'operation':'structure','payload':fields,
        'http':{'method':'GET','route':'/work/structure','query':{'project':project,**fields}}}


def retired_view(project,root,section_id,paragraph_id):
    """Exact retired unit through its indexed operation, not a current-row archive."""
    from laplace.manuscript import reader_restructure as owner
    from laplace.writing import records
    meta=records.index(root).reader_logical_lineage.get((project,section_id,paragraph_id))
    if not meta or meta['role']!='retired_ids':return None
    intent=owner._intent(project,root,meta['intent_artifact_id'])
    rows=intent['narrative_patch']['inserted'] if intent.get('inverse') else [row['row'] for row in intent['narrative_patch']['removed']]
    row=next((row for row in rows if row['paragraph_id']==paragraph_id),None)
    if row is None:raise ValueError('The indexed retired unit is absent from its exact operation ART.')
    latest=records.index(root).reader_restructure_receipts.get((project,meta['intent_artifact_id']))
    outcome=copy.deepcopy((latest or {}).get('reader_metadata',{}).get('restructure') or {})
    return {'reader_transition':None,'paragraph_plan':{'section_id':section_id,'status':'RETIRED',
        'paragraphs':{'items':[{**copy.deepcopy(row),'retired':True,'read_only':True,
            'semantic_currentness':'HISTORICAL_REVIEW_ONLY','read_handle':reader_plan.read_handle(project,section_id,paragraph_id=paragraph_id),
            'lineage':{'status':'RECORDED','items':[copy.deepcopy(meta)]},
            'successor_reads':[reader_plan.read_handle(project,section_id,paragraph_id=ident) for ident in meta['successor_ids']],
            'attachment_dispositions':copy.deepcopy(intent['attachment_dispositions']),
            'attachment_inventory':copy.deepcopy(intent['attachment_inventory']),
            'occurrence_dispositions':copy.deepcopy(intent['occurrence_dispositions']),
            'review_obligations':copy.deepcopy(outcome.get('review_obligations') or intent['review_obligations'])}], 'total':1,'offset':0,'limit':1,'next_read':None},
        'pending_restructures':owner.pending(project,section_id,root),
        'publication':{'complete':bool(outcome.get('complete')),'receipt':outcome.get('receipt')}},
        'reader_inputs':{}}


def native_projection(value,payload,read_id=None):
    """Small discovery; complete authored fields and marker patches through READ.

    The same human projection is chunked as explicit JSON, never truncated or
    represented as complete. Immutable receipt reads remain historical evidence.
    """
    import json
    from laplace.core import grammar
    from laplace.manuscript.reconciliation import _text_part
    def handle(offset=0):
        fields={'view':'restructure','section_ids':[value['section_id']],'part':'logical','offset':offset}
        if value.get('receipt'):
            fields.update(receipt_id=value['receipt']['id'],intent_artifact_id=value['receipt']['intent_artifact_id'])
        else:
            fields.update(read_id=read_id,restructure_token=value['restructure_token'])
        reconciliation=value.get('metadata_reconciliation') or {}
        if 'action' in reconciliation:
            fields.update(reconcile_current=True,reconciliation_token=reconciliation['reconciliation_token'])
            if read_id:
                fields.pop('receipt_id',None);fields.pop('intent_artifact_id',None);fields.pop('reconcile_current',None)
                fields['read_id']=read_id
            else:fields['current_occurrence_assignments']=reconciliation.get('current_occurrence_assignments',[])
        return {'native_request':{'verb':'read','concept':'plan@plan','target':value['project'],
            'expected':[],'payload':grammar.to_payload(fields),'by':''}}
    head={key:copy.deepcopy(value[key]) for key in ('schema_version','project','section_id','kind','restructure_token','receipt',
        'complete','ready','inverse_direction','inverse_currentness','metadata_only','source_receipt_id','source_currentness','source_required','source_unchanged','source_committed','plan_publication','source_effect','error') if key in value}
    if payload.get('part')!='logical':
        for key in ('read_receipt','action_receipt'):
            if key in value:head[key]={field:copy.deepcopy(item) for field,item in value[key].items() if field in {
                'id','turn_id','session_id','project','operation','output_sha256','status','metadata_only','source_currentness','current_observation','requested_by'}}
    if payload.get('part')=='logical':
        text=json.dumps({key:item for key,item in value.items() if key not in {'read_receipt','action_receipt','context_refresh'}},sort_keys=True,ensure_ascii=False,separators=(',',':'))
        chunk,end=_text_part(text,payload.get('offset',0))
        head={key:item for key,item in head.items() if key in {'schema_version','project','section_id','kind','restructure_token','receipt'}}
        if 'receipt' in head:head['receipt']={key:item for key,item in head['receipt'].items() if key in {'id','intent_artifact_id','kind'}}
        head.update(projection='logical-part',format='json',**chunk,
            source_currentness='HISTORICAL_OPERATION_ONLY' if value.get('receipt') else 'EXACT_GUARDED_CURRENT_SOURCE')
        if end<chunk['coverage']['total']:head['next_read']=handle(end)
        return head
    if value.get('disposition_summary'):head['disposition_summary']=copy.deepcopy(value['disposition_summary'])
    if value.get('inverse_currentness') and value.get('disposition_summary'):
        head['source_effect_state']=(head.pop('source_effect',{}) or {}).get('state')
        head['source_details_in']='Existing exact logical parts'
    reconciliation=value.get('metadata_reconciliation')
    if reconciliation:
        head['metadata_reconciliation']={key:copy.deepcopy(reconciliation[key]) for key in ('status','reconciliation_token','refusal_reasons','changed_dependencies') if key in reconciliation}
        if reconciliation.get('action'):
            head['metadata_reconciliation']['action']={key:copy.deepcopy(reconciliation['action'][key]) for key in ('operation','permitted','native_request')}
    if value.get('reconciliation_read'):head['reconciliation_read']={key:copy.deepcopy(value['reconciliation_read'][key]) for key in ('operation','native_request') if key in value['reconciliation_read']}
    head.update(projection='metadata',semantic_currentness=value.get('semantic_currentness','NOT_REVIEWED'),
        counts={key:len(value.get(key) or []) for key in ('successors','predecessors','attachment_inventory','occurrence_inventory','review_obligations','needs_input','source_changes')},
        contract_inline=False,contract_read=handle(),
        instruction=('Inspect inverse_currentness. Use the exact inverse action only when CURRENT; if its body is deferred, follow contract_read. Historical reviews are not renewed.' if value.get('complete') else 'Inspect the retained source/plan outcome and its exact recovery action; metadata recovery never replays source.' if value.get('receipt') else 'Read all exact logical JSON parts before authoring successors and explicit assignments. No old review or protection is inherited as scientific acceptance. Reuse the authored draft with the owner-issued Apply action.'))
    head['instruction']+=' Exact JSON parts use at_end/has_more for continuation; complete means the whole text is in this one response.'
    head['source_changes']=[{key:row[key] for key in ('file','before_sha256','after_sha256')} | {'marker_edit_count':len(row.get('marker_edits') or [])} for row in value.get('source_changes') or []]
    for key in ('apply_action','recovery_action','undo_action'):
        action=value.get(key)
        if action:
            compact={field:copy.deepcopy(action[field]) for field in ('operation','permitted','native_request','title') if field in action}
            if len(json.dumps(compact).encode())<4000 and len(json.dumps(head).encode())+len(json.dumps(compact).encode())<6500:head[key]=compact
            else:head[key]={'permitted':action.get('permitted',False),'exact_action_in':'contract_read complete JSON'}
    if len(json.dumps(head.get('metadata_reconciliation',{})).encode())>4000:
        head['metadata_reconciliation'].pop('action',None)
        head['metadata_reconciliation']['exact_action_in']='contract_read complete JSON'
    if len(json.dumps(head).encode())>6500:
        head.pop('source_changes',None);head.pop('source_effect',None)
        head['source_details_in']='contract_read complete JSON'
    return head


def _occurrence_postimages(prepared,changes):
    mappings={row['occurrence_id']:row for row in prepared['source_mappings']}
    byfile={row['file']:row for row in changes}
    before=[];after=[]
    for row in prepared['occurrence_inventory']:
        old={key:copy.deepcopy(row[key]) for key in ('file','line_start','line_end','spec_ids')}
        before.append(old);new=copy.deepcopy(old)
        shift=0;end_shift=0
        for edit in byfile[row['file']]['marker_edits']:
            delta=len(edit['after'].splitlines())-len(edit['before'].splitlines())
            if edit['line_end']<old['line_start']:shift+=delta
            if edit['line_end']<=old['line_end']:end_shift+=delta
        new.update(line_start=old['line_start']+shift,line_end=old['line_end']+end_shift,
            spec_ids=mappings[row['id']]['after_ids'])
        after.append(new)
    return {'before':before,'after':after}


def disposition_summary(intent,value):
    """Bounded factual receipt summary, not a second disposition authority.

    Counts cover the entire admitted inventory. Any omitted inline value or
    destination is explicit; exact heavier facts remain in existing ART parts.
    Historical author protections/reviews are refs, never copied body histories.
    """
    import json
    from collections import Counter
    assignments={row['attachment_id']:row for row in intent['attachment_dispositions']}
    inventory=intent.get('attachment_inventory') or []
    counts=Counter(row['disposition'] for row in assignments.values())
    destinations=Counter(ident for row in assignments.values() for ident in row['successor_ids'])
    qualifications=[row for row in inventory if row.get('kind')=='qualification']
    summary={'basis':{'receipt_id':value['receipt']['id'],'intent_artifact_id':value['receipt']['intent_artifact_id']},
        'attachment_count':len(inventory),'occurrence_count':len(intent['occurrence_dispositions']),
        'disposition_counts':{key:counts.get(key,0) for key in ('assign','retain-retired','retain-unresolved')},
        'category_counts':dict(sorted(Counter(row['kind'] for row in inventory).items())),
        'destination_counts':[],'qualification_count':len(qualifications),'qualifications':[],
        'coverage':{'counts_complete':True,'destinations_complete':False,'qualifications_complete':False,
            'omitted_destinations':len(destinations),'omitted_qualifications':len(qualifications),'omitted_qualification_values':0},
        'scientific_acceptance':'NOT_ASSERTED','old_reviews':'HISTORICAL_ONLY'}
    size=lambda:len(json.dumps(summary,ensure_ascii=False,separators=(',',':')).encode())
    for item in qualifications:
        assignment=assignments[item['id']];text=str(item['value']);raw=text.encode()
        row={'attachment_id':item['id'],'disposition':assignment['disposition'],
            'successor_ids':assignment['successor_ids'][:8],'successor_count':len(assignment['successor_ids']),
            'destinations_complete':len(assignment['successor_ids'])<=8,
            'value_coverage':{'unit':'utf8-bytes','total':len(raw),'sha256':_pin(text),'complete':len(raw)<=800}}
        if len(raw)<=800:row['value']=text
        summary['qualifications'].append(row)
        if size()>2400:
            row.pop('value',None);row['value_coverage']['complete']=False
        if size()>2400:
            summary['qualifications'].pop();continue
        summary['coverage']['omitted_qualifications']-=1
        if not row['value_coverage']['complete']:summary['coverage']['omitted_qualification_values']+=1
    for ident,count in sorted(destinations.items()):
        summary['destination_counts'].append({'paragraph_id':ident,'attachment_count':count})
        if size()>2400:summary['destination_counts'].pop();continue
        summary['coverage']['omitted_destinations']-=1
    summary['coverage']['destinations_complete']=summary['coverage']['omitted_destinations']==0
    summary['coverage']['qualifications_complete']=summary['coverage']['omitted_qualifications']==0 and summary['coverage']['omitted_qualification_values']==0
    return summary
