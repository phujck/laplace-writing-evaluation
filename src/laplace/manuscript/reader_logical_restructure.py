"""Pure preparation of logical paragraph restructuring for the reader owner.

This module does not register a tool, read a ledger, reserve an ID or mutate a
file. reader_plan supplies exact current fields/input pins; bindings supplies
the complete selected-source occurrence cut; the existing restructure owner
will retain its scoped patch in one ART and publish through its RPUB phases.
Keeping this logic separate prevents source presentation gestures from silently
acquiring semantic reassignment. Application/inverse admission stays upstream.
"""
from __future__ import annotations

from laplace.core import scoped as core_scoped
import copy
import hashlib
from laplace.manuscript import reader_plan

KINDS = {'logical-split', 'logical-merge'}
DISPOSITIONS = {'assign', 'retain-retired', 'retain-unresolved'}
ATTACHMENT_KINDS = {'claim', 'evidence', 'citation', 'equation', 'figure', 'note',
                    'protection', 'review', 'qualification', 'connection', 'legacy'}
AUTHORED_FIELDS = set(reader_plan.PARAGRAPH_STRINGS) - {'equation_anchor', 'figure_anchor'}
ARRAY_FIELDS = {'input_nodes', 'citations'}
SCALAR_ATTACHMENT_FIELDS = {'equation_anchor', 'figure_anchor', 'qualification',
                            'from_previous', 'to_next'}


def fingerprint(value):
    return reader_plan.fingerprint(value)


def _unique(rows, key, label):
    found = {}
    for row in rows:
        ident = row.get(key) if isinstance(row, dict) else None
        if not isinstance(ident, str) or not ident or ident in found:
            raise ValueError(label + ' identities are missing or duplicated.')
        found[ident] = row
    return found


def offer_successors(project, section_id, kind, selected_ids, count, *,
                     narrative_revision, current_ids, reserved_ids):
    """Stable unused offers; the publishing owner must reserve under its locks."""
    if kind not in KINDS or type(count) is not int or count < 1:
        raise ValueError('Choose a logical split or merge and its successor count.')
    if kind == 'logical-merge' and count != 1 or kind == 'logical-split' and count < 2:
        raise ValueError('A merge creates one unit; a split creates at least two.')
    unavailable = set(current_ids) | set(reserved_ids)
    seed = [project, section_id, kind, list(selected_ids), narrative_revision,
            sorted(unavailable)]
    offered = []
    attempt = 0
    while len(offered) < count:
        digest = fingerprint([seed, attempt]).split(':')[1]
        ident = section_id + '-p' + str(int(digest[:24], 16))
        if ident not in unavailable:
            offered.append(ident)
            unavailable.add(ident)
        attempt += 1
    return offered


def occurrence_id(row):
    """Exact physical occurrence, never a logical ID or the whole-file digest.

    Harmless rereads preserve identity. A changed range/content requires explicit
    basis adoption; the UI cannot remap a choice by matching text on its own.
    """
    return 'OCC-' + fingerprint({key: row.get(key) for key in
        ('file', 'line_start', 'line_end', 'spec_ids', 'content_sha256')}).split(':')[1][:32]


def _assignment_table(rows, inventory, key, label):
    found = _unique(rows, key, label)
    allowed = {key, 'changes'} if key == 'paragraph_id' else (
        {key, 'successor_ids', 'disposition'} if key == 'attachment_id' else {key, 'successor_ids'})
    if any(set(row) - allowed for row in found.values()):
        raise ValueError(label + ' has fields outside the owner contract.')
    unknown = set(found) - set(inventory)
    if unknown:
        raise ValueError(label + ' contains an identity outside the exact inventory.')
    return found


def prepare(project, section_id, kind, *, rows, selected_ids, successor_ids,
            occurrences, attachments, basis, draft=None, coverage=None):
    """Return a reviewable scoped plan; incomplete authored choices stay pending.

    Inputs are owner projections, not caller authority. Integration must obtain
    them freshly under existing plan/publication/source locks and compare the
    emitted basis before publishing. No result here acknowledges an effect.
    """
    if kind not in KINDS:
        raise ValueError('Choose the existing logical split or merge kind.')
    current = _unique(rows, 'paragraph_id', 'Current paragraph')
    selected_ids = list(selected_ids)
    if (not selected_ids or len(set(selected_ids)) != len(selected_ids)
            or any(ident not in current for ident in selected_ids)):
        raise ValueError('Choose exact current predecessor units.')
    if kind == 'logical-split' and len(selected_ids) != 1:
        raise ValueError('A logical split has exactly one predecessor.')
    if kind == 'logical-merge' and len(selected_ids) < 2:
        raise ValueError('A logical merge has at least two predecessors.')
    successor_ids = list(successor_ids)
    if (len(set(successor_ids)) != len(successor_ids)
            or any(not isinstance(ident, str) or not ident or ident in current for ident in successor_ids)
            or kind == 'logical-split' and len(successor_ids) < 2
            or kind == 'logical-merge' and len(successor_ids) != 1):
        raise ValueError('Use the complete unused successor identities offered by the owner.')
    readers = basis.get('expected_reader_basis') or {}
    if set(readers) != set(selected_ids):
        raise ValueError('Every predecessor needs its exact inspected reader basis.')
    from jsonschema import Draft202012Validator
    for ident, value in readers.items():
        issue = next(Draft202012Validator(reader_plan.basis_schema()).iter_errors(value), None)
        if (issue or value['project'] != project or value['section_id'] != section_id
                or value['subject_id'] != ident
                or value['subject_revision'] != fingerprint(current[ident])):
            raise ValueError('The inspected reader basis differs from its exact predecessor.')
    if not basis.get('source_set_revision'):
        raise ValueError('The complete selected-source traversal identity is required.')

    selected = set(selected_ids)
    occurrences = [copy.deepcopy(row) for row in occurrences
                   if selected.intersection(row.get('spec_ids') or [])]
    occurrence_map = _unique(occurrences, 'id', 'Source occurrence')
    for row in occurrences:
        ids = row.get('spec_ids')
        if not isinstance(ids, list) or len(ids) != len(set(ids)) or row['id'] != occurrence_id(row):
            raise ValueError('The source occurrence is not the exact owner-issued full ID set.')
        row['preserved_ids'] = [ident for ident in ids if ident not in selected]
    attachments = [copy.deepcopy(row) for row in attachments
                   if selected.intersection(row.get('paragraph_ids') or [])]
    attachment_map = _unique(attachments, 'id', 'Attachment')
    for row in attachments:
        if row.get('kind') not in ATTACHMENT_KINDS or not row.get('pin'):
            raise ValueError('Every scoped attachment needs its owner kind and exact input pin.')
        if row.get('field') in ARRAY_FIELDS | SCALAR_ATTACHMENT_FIELDS and not isinstance(row.get('value'), str):
            raise ValueError('Typed attachment values must retain their declared field shape.')

    draft = copy.deepcopy(draft or {})
    allowed = {'paragraph_ids', 'successor_count', 'successors',
               'attachment_assignments', 'occurrence_assignments'}
    if set(draft) - allowed:
        raise ValueError('Logical changes accept explicit assignments, never free marker/source edits.')
    if draft.get('paragraph_ids', selected_ids) != selected_ids:
        raise ValueError('The authored draft belongs to different predecessor units.')
    supplied = _assignment_table(draft.get('successors') or [],
                                dict.fromkeys(successor_ids), 'paragraph_id', 'Successor')
    attached = _assignment_table(draft.get('attachment_assignments') or [],
                                attachment_map, 'attachment_id', 'Attachment assignment')
    located = _assignment_table(draft.get('occurrence_assignments') or [],
                               occurrence_map, 'occurrence_id', 'Occurrence assignment')
    needs = []
    if 'successor_count' in draft and (type(draft['successor_count']) is not int
                                       or draft['successor_count'] != len(successor_ids)):
        raise ValueError('The authored successor count differs from the owner-issued identities.')
    # The caller cannot claim complete coverage while omitting a nonempty
    # supported predecessor field. Unsupported legacy fields are retained as
    # explicit inventory items by the producer, never silently inherited.
    covered_fields = {(paragraph_id, item['field'], item['value'])
        for item in attachments if item.get('field') in ARRAY_FIELDS | SCALAR_ATTACHMENT_FIELDS
        for paragraph_id in item['paragraph_ids']}
    for paragraph_id in selected_ids:
        original = current[paragraph_id]
        for field in sorted(ARRAY_FIELDS | SCALAR_ATTACHMENT_FIELDS):
            values = original.get(field) or []
            values = values if isinstance(values, list) else [values]
            for value in values:
                if (paragraph_id, field, value) not in covered_fields:
                    needs.append({'kind': 'ATTACHMENT_INVENTORY', 'paragraph_id': paragraph_id,
                                  'field': field, 'value_revision': fingerprint(value)})
    obligations = []
    new_rows = []
    for ident in successor_ids:
        changes = (supplied.get(ident) or {}).get('changes') or {}
        if (not isinstance(changes, dict) or set(changes) - AUTHORED_FIELDS
                or any(not isinstance(value, str) for value in changes.values())):
            raise ValueError('Successor fields must be typed authored paragraph text; attachments are assigned separately.')
        missing = [key for key in ('function', 'proposition') if not changes.get(key, '').strip()]
        if missing:
            needs.append({'kind': 'SUCCESSOR_FIELDS', 'id': ident, 'fields': missing})
        new_rows.append({'section_id': section_id, 'paragraph_id': ident, **changes,
                         'attachment_refs': []})
    by_new = {row['paragraph_id']: row for row in new_rows}

    for ident, item in attachment_map.items():
        decision = attached.get(ident)
        if decision is None:
            needs.append({'kind': 'ATTACHMENT_ASSIGNMENT', 'id': ident})
            continue
        disposition = decision.get('disposition')
        destinations = decision.get('successor_ids') or []
        if (disposition not in DISPOSITIONS or not isinstance(destinations, list)
                or len(set(destinations)) != len(destinations)
                or any(value not in by_new for value in destinations)
                or disposition == 'assign' and not destinations
                or disposition == 'retain-retired' and destinations):
            raise ValueError('Choose an explicit scoped attachment disposition and exact successor IDs.')
        if disposition == 'retain-unresolved':
            obligations.append(core_scoped.obligation('ATTACHMENT_RECONCILIATION',
                'This attachment was retained unresolved; reconcile it with its successor reader units.',
                subject=ident, attachment_id=ident, successor_ids=destinations, original_read=item.get('read')))
        if item['kind'] == 'legacy' and disposition != 'retain-retired':
            obligations.append(core_scoped.obligation('UNSUPPORTED_ATTACHMENT_REVIEW',
                'A legacy attachment is not carried automatically; review it against its successor reader units.',
                subject=ident, attachment_id=ident, successor_ids=destinations, original_read=item.get('read')))
        if disposition != 'assign':
            continue
        for destination in destinations:
            target = by_new[destination]
            target['attachment_refs'].append({key: copy.deepcopy(item[key]) for key in
                ('id', 'kind', 'pin', 'owner', 'record_id', 'paragraph_ids') if key in item})
            field = item.get('field')
            if field in ARRAY_FIELDS:
                target.setdefault(field, [])
                if item['value'] not in target[field]:
                    target[field].append(copy.deepcopy(item['value']))
            elif field in SCALAR_ATTACHMENT_FIELDS:
                if field in target and target[field] != item['value']:
                    raise ValueError('Conflicting scalar attachments require an explicit scoped reconciliation.')
                target[field] = copy.deepcopy(item['value'])
            # Review/protection/note qualifications are references to the
            # original owner. They never become new acceptance/confirmation.
    mappings = []
    for ident, item in occurrence_map.items():
        decision = located.get(ident)
        if decision is None:
            needs.append({'kind': 'OCCURRENCE_ASSIGNMENT', 'id': ident})
            continue
        destinations = decision.get('successor_ids')
        if (not isinstance(destinations, list) or len(set(destinations)) != len(destinations)
                or any(value not in by_new for value in destinations)):
            raise ValueError('Assign each exact physical occurrence to issued successor identities.')
        after = []
        replaced = False
        for old_id in item['spec_ids']:
            if old_id in selected:
                if not replaced:
                    after.extend(destinations)
                    replaced = True
            else:
                after.append(old_id)
        after = list(dict.fromkeys(after))
        mappings.append({'occurrence_id': ident, 'file': item['file'],
                         'before_ids': item['spec_ids'], 'after_ids': after,
                         'source_basis': copy.deepcopy(item.get('basis'))})
        if not after:
            obligations.append(core_scoped.obligation('UNBOUND_RETAINED_PROSE',
                'Retained prose is no longer bound to any reader unit; review or bind it.', subject=ident, occurrence_id=ident))
    if not (coverage or {}).get('complete'):
        needs.append({'kind': 'OCCURRENCE_COVERAGE', 'reason': 'The complete selected-source inventory is not proved.'})
    for row in new_rows:
        obligations.append(core_scoped.obligation('NEW_READER_UNIT_NOT_REVIEWED',
            'This new reader unit has not been reviewed.', subject=row['paragraph_id'], paragraph_id=row['paragraph_id']))
    removed = [{'index': index, 'row': copy.deepcopy(row)} for index, row in enumerate(rows)
               if row['paragraph_id'] in selected]
    patch = {'removed': removed, 'insert_at': min(row['index'] for row in removed),
             'inserted': new_rows}
    return {'project': project, 'section_id': section_id, 'kind': kind,
            'basis': copy.deepcopy(basis), 'basis_token': fingerprint(basis),
            'successors': new_rows, 'attachment_inventory': attachments,
            'occurrence_inventory': occurrences, 'source_mappings': mappings,
            'retired_ids': selected_ids, 'needs_input': needs, 'ready': not needs,
            'review_obligations': obligations, 'narrative_patch': patch,
            'attachment_dispositions': [copy.deepcopy(attached[ident]) for ident in attachment_map if ident in attached],
            'occurrence_dispositions': [copy.deepcopy(located[ident]) for ident in occurrence_map if ident in located],
            'semantic_currentness': 'NOT_REVIEWED', 'provider_started': False}


def apply_narrative_patch(rows, patch, *, inverse=False):
    """Guard exact scoped rows; preserve disjoint rows/order without archiving them."""
    result = copy.deepcopy(rows)
    if inverse:
        inserted = patch['inserted']
        at = patch['insert_at']
        if result[at:at + len(inserted)] != inserted:
            raise ValueError('The exact successor postimage changed; inverse is unavailable.')
        del result[at:at + len(inserted)]
        for row in sorted(patch['removed'], key=lambda item: item['index']):
            result.insert(row['index'], copy.deepcopy(row['row']))
    else:
        removed = {row['index']: row['row'] for row in patch['removed']}
        for index, old in removed.items():
            if index >= len(result) or result[index] != old:
                raise ValueError('The exact predecessor row changed before logical publication.')
        result = [row for index, row in enumerate(result) if index not in removed]
        at = patch['insert_at']
        result[at:at] = copy.deepcopy(patch['inserted'])
    return result


def stage_markers(source_texts, prepared):
    """Stage exact marker-only substitutions; preserve every prose byte.

    The returned full postimages are transient execution inputs, never intent
    history. The existing ART retains only scoped marker hunks and file pins.
    The source-set guard still belongs to the calling owner under its locks.
    """
    from laplace.manuscript.projection_viewer import parse_paragraphs, _PARA_RE
    if not prepared.get('ready'):
        raise ValueError('Complete every logical field and assignment before staging source.')
    inventory = {row['id']: row for row in prepared['occurrence_inventory']}
    grouped = {}
    for mapping in prepared['source_mappings']:
        grouped.setdefault(mapping['file'], []).append(mapping)
    outputs = {}
    changes = []
    pin = lambda value: 'sha256:' + hashlib.sha256(value.encode('utf-8')).hexdigest()
    for file, mappings in grouped.items():
        if file not in source_texts or not isinstance(source_texts[file], str):
            raise ValueError('The exact current selected source body is unavailable.')
        before = source_texts[file]
        source_pin = pin(before)
        spans = {row['start_line']: row for row in parse_paragraphs(before)}
        lines = before.splitlines(keepends=True)
        edits = []
        for mapping in mappings:
            observed = inventory[mapping['occurrence_id']]
            basis = observed.get('basis') or {}
            span = spans.get(observed['line_start'])
            if (basis.get('source_digest') != source_pin or span is None
                    or span['end_line'] != observed['line_end']
                    or span['spec_ids'] != mapping['before_ids']):
                raise ValueError('CHANGED_INPUT: exact logical source occurrence changed.')
            fragment = ''.join(lines[span['start_line'] - 1:span['end_line']])
            if observed.get('content_sha256') != pin(fragment):
                raise ValueError('CHANGED_INPUT: scoped occurrence body changed.')
            destinations = mapping['after_ids']
            if any('\n' in ident or '\r' in ident or not _PARA_RE.fullmatch('% ' + ident)
                   for ident in destinations):
                raise ValueError('Successor identities are not valid owner paragraph markers.')
            start = span['start_line'] - 1
            end = start
            witnessed = []
            while end < span['end_line']:
                line = lines[end]
                marker = _PARA_RE.fullmatch(line.rstrip('\r\n'))
                if marker:
                    witnessed.append(marker.group(1))
                elif line.strip():
                    break
                end += 1
            if witnessed != mapping['before_ids']:
                raise ValueError('The complete marker frame is not this admitted occurrence.')
            prior = ''.join(lines[start:end])
            newline = '\r\n' if lines[start].endswith('\r\n') else '\n'
            gaps = ''.join(line for line in lines[start:end]
                           if not _PARA_RE.fullmatch(line.rstrip('\r\n')))
            after = ''.join('% ' + ident + newline for ident in destinations) + gaps
            edits.append({'line_start': start + 1, 'line_end': end,
                          'before': prior, 'after': after,
                          'occurrence_id': mapping['occurrence_id']})
        last_end = 0
        for edit in sorted(edits, key=lambda row: row['line_start']):
            if edit['line_start'] <= last_end:
                raise ValueError('Logical source occurrence frames overlap; no source was staged.')
            last_end = edit['line_end']
        after_lines = list(lines)
        for edit in sorted(edits, key=lambda row: row['line_start'], reverse=True):
            after_lines[edit['line_start'] - 1:edit['line_end']] = edit['after'].splitlines(keepends=True)
        after = ''.join(after_lines)
        outputs[file] = after
        changes.append({'file': file, 'before_sha256': source_pin,
                        'after_sha256': pin(after), 'marker_edits': edits})
    return {'staged_sources': outputs, 'source_changes': changes}
