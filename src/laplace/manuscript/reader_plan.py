"""Authored reader transitions and paragraph plans over the existing stage artifacts.

Structure reads/writes, native context and scoped Work review consume this owner.
Physical source correspondence remains in bindings; artifact publication/custody
remains in artifacts. Legacy stage loaders retain their data shape, but do not
acquire reviewed standing merely by producing files. No paragraph order is an ID.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from pathlib import Path

from laplace.projects import artifacts
from laplace.writing import records

CONTRACT_STRINGS = ('function', 'question_answered', 'entry_state', 'exit_state', 'permitted_recap')
CONTRACT_ARRAYS = ('depends_on', 'forward_uses', 'citations', 'equations', 'figures', 'tables')
PARAGRAPH_STRINGS = ('function', 'proposition', 'explanation', 'derivation_detail', 'equation_anchor',
                     'figure_anchor', 'qualification', 'from_previous', 'to_next', 'detail_level', 'length_range')
PARAGRAPH_ARRAYS = ('input_nodes', 'citations')
MAX_BYTES = 2_000_000


def fingerprint(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode()).hexdigest()


def raw_revision(raw):
    return 'sha256:' + hashlib.sha256(raw).hexdigest() if raw is not None else None


def read_handle(project, section_id, **scope):
    payload = {'view': 'detail', 'section_ids': [section_id], **scope}
    return {'operation': 'structure', 'payload': payload,
            'http': {'method': 'GET', 'route': '/work/structure',
                     'query': {'project': project, **payload}}}


def _paths(project, root, section_id, *, plan=None):
    from laplace.pipeline import registry, pathsafe, schema
    record = registry.resolve(project, repo_root=root)
    if record is None or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.:-]{0,79}', section_id):
        raise ValueError('Reader state requires a registered project and exact safe section ID.')
    contracts, narrative = record.stage_path('contracts', root), record.stage_path('narrative', root)
    if contracts is None or narrative is None:
        raise ValueError('This project has no declared reader-state artifact namespace.')
    encoded = pathsafe.encode_sid_for_path(section_id)
    aliases = [row['id'] for row in schema.plan_sections(plan if plan is not None else record.read_plan(root) or {})
               if pathsafe.encode_sid_for_path(row['id']) == encoded]
    if len(aliases) != 1 or aliases[0] != section_id:
        raise ValueError('Narrative filename is absent or ambiguous across current section identities.')
    paths = (contracts.resolve(), (narrative / (encoded + '.json')).resolve())
    if any(not path.is_relative_to(Path(root).resolve()) for path in paths):
        raise ValueError('Reader-state artifacts are outside this workspace.')
    return paths


def _json(path):
    if not path.exists():
        return None, None
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Reader-state artifact is not a bounded JSON file.')
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Reader-state artifact must contain an object.')
    return value, raw


def _contracts(value):
    rows = (value or {}).get('sections', {})
    if not isinstance(rows, dict) or any(not isinstance(row, dict) or row.get('section_id') != key for key, row in rows.items()):
        raise ValueError('Section contracts must be keyed by their exact section IDs.')
    return list(rows.values())


def _paragraphs(value, section_id):
    if value and value.get('section_id') != section_id:
        raise ValueError('Narrative artifact names a different section.')
    rows = (value or {}).get('paragraphs', [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('Narrative artifact must contain paragraph objects.')
    return rows


def _subject(rows, name, ident):
    matches = [row for row in rows if row.get(name) == ident]
    if len(matches) > 1:
        raise ValueError('Reader-state identity is duplicated; reconcile the retained artifact before editing.')
    return matches[0] if matches else None


def _architecture(section, sections, root, *, cache=None):
    from laplace.pipeline import narrative
    cache = {} if cache is None else cache
    if 'architecture_profile' not in cache:
        cache['architecture_profile'] = narrative.architecture_status(root, include_content=True)
    profile = cache['architecture_profile']
    position = next((i for i, row in enumerate(sections) if row['id'] == section['id']), None)
    projection = narrative.architecture_brief_for_section(profile.get('fields'), position, len(sections),
        section.get('job'), bool(section.get('derivation') or 'deriv' in str(section.get('job', '')).lower()))
    fields = (projection or {}).get('fields', {})
    effective = {'fields': fields, 'summary': '\n'.join(v['summary'] for v in fields.values()),
                 'revision': fingerprint({'status': profile['status'], 'fields': fields})}
    return {key: value for key, value in profile.items() if key != 'fields'} | {'effective_projection': effective}


class _InputPins(dict):
    """Internal request-local pins plus qualification, serialised as ordinary pins.
    The persisted/public qualifier remains reader-basis/1.unobserved_inputs.
    """
    def __init__(self, pins, links):
        super().__init__(pins)
        self.unobserved_inputs = sorted({row['input_key'] for row in links
            if row.get('input_key') and row.get('status') not in {'AVAILABLE', 'CURRENT'}})


def _visual_inputs(project, root, ids, cache):
    from laplace.pipeline import registry, visual_production
    record = registry.resolve(project, repo_root=root)
    manuscript = record.path(record.manuscript_dir, root) if record and record.manuscript_dir else None
    base = record.path(record.project_dir, root) if record and record.project_dir else manuscript
    if manuscript is None:
        return {ident: {'id': ident, 'status': 'UNRESOLVED', 'problems': ['Visual owner namespace unavailable'],
                       'observation': {'id': ident, 'status': 'UNAVAILABLE'}} for ident in ids}
    visual_cache = cache.setdefault('reader_visuals', {})
    observed = visual_production.reader_inputs(manuscript, ids, base, cache=visual_cache)
    for row in observed.values():
        row['observation']['manuscript'] = manuscript.relative_to(Path(root)).as_posix()
        row['observation']['input_base'] = base.relative_to(Path(root)).as_posix()
    return observed


def _inputs(project, root, section, sections, subject, contracts, architecture, *, paragraph=False, cache=None):
    """Pin consumed subject projections, not whole sibling artifacts or source files."""
    from laplace.research import corpus_ingest
    cache = {} if cache is None else cache
    pins, links = {}, []
    # Reader purpose/placement is authored independently of the source title.
    pins['plan-section'] = fingerprint({key: section.get(key) for key in
        ('id', 'job', 'serves', 'why', 'node_ids', 'beat_ids')})
    pins['architecture'] = architecture['effective_projection']['revision']
    if paragraph:
        contract = _subject(contracts, 'section_id', section['id'])
        pins['reader-transition'] = fingerprint(contract)
        rows = cache.get('paragraph_rows', [])
        if 'paragraph_positions' not in cache:
            cache['paragraph_positions'] = {row.get('paragraph_id'): index for index, row in enumerate(rows)}
        index = cache['paragraph_positions'].get(subject.get('paragraph_id'))
        if index is not None:
            def neighbor(position):
                if not 0 <= position < len(rows):
                    return None
                return {key: rows[position].get(key) for key in
                    ('paragraph_id', 'function', 'proposition', 'explanation', 'qualification', 'from_previous', 'to_next')}
            pins['reader-neighbors'] = fingerprint({'previous': neighbor(index - 1), 'next': neighbor(index + 1)})
    for ident in dict.fromkeys(subject.get('depends_on', []) + subject.get('forward_uses', [])):
        pins['section:' + ident] = fingerprint(_subject(contracts, 'section_id', ident))
        links.append({'kind': 'reader-plan', 'label': ident, 'input_key': 'section:' + ident,
            'status': 'AVAILABLE' if _subject(contracts, 'section_id', ident) is not None else 'UNRESOLVED',
            'read': read_handle(project, ident)})
    node_ids = list(dict.fromkeys(subject.get('input_nodes', section.get('node_ids', []))))
    if len(node_ids) > 80:
        raise ValueError('Reader input scope exceeds 80 canonical objects; narrow the authored subject.')
    if (node_ids or cache.get('need_choices')) and 'network' not in cache:
        corpus = corpus_ingest.resolve_corpus(root, project)
        cache['network'] = corpus_ingest.corpus_network(corpus, repo_root=root, name=project) if corpus else {'nodes': {}}
    net = cache.get('network') or {'nodes': {}}
    result_ids = []
    for ident in node_ids:
        node = (net.get('nodes') or {}).get(ident)
        from laplace.manuscript.project_structure import _node_row
        projection = (node or {}).get('projection') or {}
        # The planning packet consumes this explanatory projection, not every
        # source-file byte or unrelated placement/display metadata on the node.
        pins['concept:' + ident] = concept_input_revision(net.get('nodes') or {}, ident, net)
        result_ids.extend(str(row['id']) for row in ((node or {}).get('projection') or {}).get('result_bindings', []) if isinstance(row, dict) and row.get('id'))
        links.append({'kind': 'argument', 'input_key': 'concept:' + ident, 'label': _node_row(net.get('nodes') or {}, ident)['label'], 'status': 'AVAILABLE' if node else 'UNRESOLVED',
            'read': {'operation': 'concept', 'payload': {'node': ident},
                'http': {'method': 'GET', 'route': '/concepts/context', 'query': {'corpus': project, 'node': ident}}}})
    if result_ids:
        from laplace.research import research_context, research_records
        if 'research' not in cache:
            record, store = research_context.project(project, root)
            cache['research'] = (store, research_context.project_root(record, root) or store,
                research_records._records(store) if store is not None else ([], 'Research store unavailable'))
        store, project_root, retained = cache['research']
        observed = research_records.result_bindings(store, result_ids, project_root,
            records_snapshot=retained, digest_cache=cache.setdefault('result_digests', {})) if store else {'bindings': []}
        by_id = {row['id']: row for row in observed['bindings']}
        for ident in dict.fromkeys(result_ids):
            pins['result:' + ident] = fingerprint(by_id.get(ident))
            links.append({'kind': 'result', 'input_key': 'result:' + ident, 'label': ident, 'status': by_id.get(ident, {}).get('currentness', 'UNRESOLVED'), 'read': {
                'operation': 'research', 'payload': {'view': 'result', 'id': ident},
                'http': {'method': 'GET', 'route': '/research/result', 'query': {'project': project, 'id': ident}}}})
    # Bibliography entry text is the consumed input, not an unrelated .bib edit.
    from laplace.manuscript import manuscript_source
    from laplace.research import references_surface
    if (subject.get('citations') or cache.get('need_choices')) and 'bibliography' not in cache:
        source = manuscript_source.resolve(project, root, include_candidates=False)
        manuscript = (Path(root) / source['manuscript_dir']) if source.get('manuscript_dir') else None
        entries = {}
        if manuscript is not None and source.get('root'):
            for name in references_surface._bibliography_names(Path(root) / source['root']):
                path = (Path(root) / source['root']).parent.joinpath(name if name.endswith('.bib') else name + '.bib').resolve()
                if path.is_relative_to(Path(root).resolve()) and path.is_file() and path.stat().st_size <= MAX_BYTES:
                    for row in references_surface._bib_entries(path.read_text(encoding='utf-8')):
                        entries.setdefault(row['key'], []).append(row['text'])
        cache['bibliography'] = entries
    entries = cache.get('bibliography', {})
    for key in subject.get('citations', []):
        pins['citation:' + key] = fingerprint(entries.get(key))
        links.append({'kind': 'literature', 'input_key': 'citation:' + key, 'label': key, 'status': 'AVAILABLE' if len(entries.get(key, [])) == 1 else 'UNRESOLVED', 'read': {
            'operation': 'references_attached', 'payload': {'citekey': key},
            'http': {'method': 'GET', 'route': '/references/attached', 'query': {'project': project, 'citekey': key}}}})
    from laplace.pipeline import projection_spec
    needs_assets = any(subject.get(key) for key in ('equations', 'tables', 'equation_anchor')) or cache.get('need_choices')
    if needs_assets and 'spec' not in cache:
        cache['spec'] = projection_spec.load_spec(project, root) or {}
        cache['equations'] = projection_spec.effective_equation_ledger(project, root)
    figures = subject.get('figures', []) + ([subject['figure_anchor']] if subject.get('figure_anchor') else [])
    for ident, row in _visual_inputs(project, root, figures, cache).items() if figures else []:
        pins['figures:' + ident] = fingerprint(row['observation'])
        links.append({'kind': 'visual', 'input_key': 'figures:' + ident, 'label': ident,
            'status': row['status'], 'reason': '; '.join(row['problems']),
            'read': {'operation': 'visuals', 'payload': {'id': ident},
                'http': {'method': 'GET', 'route': '/visuals/state', 'query': {'project': project, 'id': ident}}}})
    for kind, requested in (
        ('equations', subject.get('equations', []) + ([subject['equation_anchor']] if subject.get('equation_anchor') else [])),
        ('tables', subject.get('tables', []))):
        available = cache.get('equations', {}) if kind == 'equations' else cache.get('spec', {}).get(kind, {})
        for ident in requested:
            value = available.get(ident) if isinstance(available, dict) else None
            pins[kind + ':' + ident] = fingerprint(value)
            links.append({'kind': kind, 'input_key': kind + ':' + ident, 'label': ident,
                'status': 'AVAILABLE' if isinstance(value, dict) and value else 'UNRESOLVED',
                'read': read_handle(project, section['id'], edit_choices=True)})
    return _InputPins(pins, links), links


def _basis(project, path, subject_id, subject, inputs, section_id):
    return {'schema_version': 'laplace.reader-basis/1', 'project': project, 'path': path,
            'section_id': section_id, 'subject_id': subject_id, 'subject_revision': fingerprint(subject), 'inputs': dict(inputs), 'unobserved_inputs': list(getattr(inputs, 'unobserved_inputs', []))}


def standing_projection(recorded, current):
    """THE ONE STANDING PROJECTION (G1-R2): a recorded scoped observation against the current owner
    observation. Every identity in EITHER map counts (a retained pin for an input that disappeared is a
    change, never dropped), as do the authored-subject revision and retained unobserved inputs. The
    readback (`_standing`), the observation-only reply and the content-save reply all use this."""
    if recorded is None:
        return {'status': 'UNPINNED', 'changed_inputs': [], 'reason': 'No completed scoped input observation is recorded.'}
    retained, observed = recorded.get('inputs', {}), current['inputs']
    changed = sorted(key for key in set(retained) | set(observed) if retained.get(key) != observed.get(key))
    if recorded.get('subject_revision') != current['subject_revision']:
        changed.insert(0, 'authored-subject')
    unobserved = sorted(set(recorded.get('unobserved_inputs', [])) | set(current.get('unobserved_inputs', [])))
    return {'status': 'UNOBSERVED' if unobserved else 'STALE' if changed else 'CURRENT',
            'unobserved_inputs': unobserved, 'changed_inputs': changed,
            'reason': 'Input observation is not a judgement of intelligibility or accepted review.'}


def _standing(root, project, path, subject_id, basis):
    return standing_projection(records.index(root).reader_subjects.get((project, path, subject_id)), basis)


def _descriptors(strings, arrays, sections, section):
    descriptors = [{'name': key, 'label': key.replace('_', ' ').capitalize(), 'type': 'string', 'multiline': True}
                   for key in strings]
    for key in arrays:
        choices = []
        if key in {'depends_on', 'forward_uses'}:
            choices = [{'value': row['id'], 'label': row.get('title') or row['id']} for row in sections if row['id'] != section['id']]
        elif key == 'input_nodes':
            choices = [{'value': ident, 'label': ident} for ident in section.get('node_ids', [])]
        descriptors.append({'name': key, 'label': key.replace('_', ' ').capitalize(), 'type': 'string_array', 'choices': choices[:80]})
    return descriptors


def _action(operation, section_id, plan_revision, revision, fields, values, *, reader_basis, **extra):
    guard = 'expected_contract_revision' if operation == 'section_contract' else 'expected_narrative_revision'
    return {'operation': 'structure_change', 'payload': {'operation': operation, 'section_id': section_id,
        'expected_plan_revision': plan_revision, guard: revision, 'expected_reader_basis': reader_basis, **extra},
        'http': {'method': 'POST', 'route': '/work/structure/change'}, 'fields': fields,
        'values': {field['name']: values.get(field['name'], [] if field['type'] == 'string_array' else '') for field in fields}}


def _new_id(root, project, path, section_id, revision, rows):
    # A guarded cut supplies a stable offered ID. Order never enters identity.
    reserved = records.index(root).reader_reserved_ids.get((project, path), set())
    current = {row.get('paragraph_id') for row in rows}
    count = 0
    while True:
        seed = fingerprint([project, path, revision, len(reserved), count])
        ident = section_id + '-p' + str(int(seed.split(':')[1][:24], 16))
        if ident not in reserved and ident not in current:
            return ident
        count += 1


def section_view(project, root, section, sections, plan_revision, *, paragraph_offset=0,
                 paragraph_limit=20, paragraph_id=None, paragraph_as_of=None, edit_choices=False, cache=None):
    """One selected authored section; only the requested paragraph page is enriched."""
    cache = {} if cache is None else cache
    cache['need_choices'] = bool(edit_choices)
    from laplace.pipeline import registry, schema
    if 'plan' not in cache:
        cache['plan'] = registry.resolve(project, repo_root=root).read_plan(root) or {}
    if 'plan_sections' not in cache:
        cache['plan_sections'] = list(schema.plan_sections(cache['plan']))
    all_sections = cache['plan_sections']
    contracts_path, narrative_path = _paths(project, root, section['id'], plan=cache['plan'])
    for path in (contracts_path, narrative_path):
        if ('json', path) not in cache:
            cache[('json', path)] = _json(path)
    contracts_value, contracts_raw = cache[('json', contracts_path)]
    narrative_value, narrative_raw = cache[('json', narrative_path)]
    contracts, paragraphs = _contracts(contracts_value), _paragraphs(narrative_value, section['id'])
    contract = _subject(contracts, 'section_id', section['id'])
    architecture = _architecture(section, all_sections, root, cache=cache)
    sections = all_sections
    input_cache = cache
    input_cache['paragraph_rows'] = paragraphs
    input_cache.pop('paragraph_positions', None)
    contract_fields = _descriptors(CONTRACT_STRINGS, CONTRACT_ARRAYS, sections, section)
    paragraph_fields = _descriptors(PARAGRAPH_STRINGS, PARAGRAPH_ARRAYS, sections, section)
    cp, np = (path.relative_to(root).as_posix() for path in (contracts_path, narrative_path))
    cr, nr = raw_revision(contracts_raw), raw_revision(narrative_raw)
    if paragraph_as_of is not None and paragraph_as_of != nr:
        raise ValueError('CHANGED_INPUT: paragraph plan changed between reads; inspect the selected section again.')
    fields = contract or {'section_id': section['id']}
    inputs, links = _inputs(project, root, section, sections, fields, contracts, architecture, cache=input_cache)
    if edit_choices:
        from laplace.pipeline import visual_production
        record = registry.resolve(project, repo_root=root)
        manuscript = record.path(record.manuscript_dir, root) if record and record.manuscript_dir else None
        input_cache['visual_choices'] = visual_production.reader_catalogue(manuscript) if manuscript else {'specs': [], 'problems': ['unavailable']}
    enrich_descriptors(project, section, sections, contract_fields + paragraph_fields, input_cache)
    basis = _basis(project, cp, section['id'], contract, inputs, section['id'])
    currentness = _standing(root, project, cp, section['id'], basis)
    currentness['reads'] = [read_handle(project, section['id'])]
    transition = {'section_id': section['id'], 'status': 'DECLARED' if contract is not None else 'NOT_DECLARED',
        'fields': fields, 'revision': cr, 'subject_revision': basis['subject_revision'],
        'reader_basis': basis, 'input_currentness': currentness, 'review': {'status': 'NOT_REVIEWED'},
        'read_handle': read_handle(project, section['id']), 'links': links,
        'diagnostics': input_diagnostics(fields, links, contract=True),
        'edit_action': _action('section_contract', section['id'], plan_revision, cr, contract_fields, fields, reader_basis=basis)}
    transition['edit_action']['choices_read'] = read_handle(project, section['id'], edit_choices=True)
    transition.update(review_fields(project, root, basis, section['id'], cache=input_cache))
    ids = [row.get('paragraph_id') for row in paragraphs]
    stable = all(isinstance(ident, str) and re.fullmatch(r'.+-p[0-9]+', ident) for ident in ids) and len(set(ids)) == len(ids)
    if paragraph_id is not None:
        selected = [_subject(paragraphs, 'paragraph_id', paragraph_id)]
        if selected == [None]:
            from laplace.manuscript.reader_logical_publication import retired_view
            retained=retired_view(project,root,section['id'],paragraph_id)
            if retained:return retained
            raise ValueError('The exact paragraph ID is absent; inspect the current section plan.')
    else:
        selected = paragraphs[paragraph_offset:paragraph_offset + paragraph_limit]
    occurrences = source_occurrences(project, root, {row.get('paragraph_id') for row in selected}, cache=cache)
    items = []
    for row in selected:
        ident = row.get('paragraph_id')
        inputs, links = _inputs(project, root, section, sections, row, contracts, architecture, paragraph=True, cache=input_cache)
        pb = _basis(project, np, str(ident), row, inputs, section['id'])
        handle = read_handle(project, section['id'], paragraph_id=ident) if ident else read_handle(project, section['id'])
        item = {**row, 'identity_status': 'STABLE' if stable else 'UNPROVEN_LEGACY',
            'subject_revision': pb['subject_revision'], 'reader_basis': pb,
            'input_currentness': {**_standing(root, project, np, str(ident), pb), 'reads': [handle]},
            'read_handle': handle, 'links': links, 'diagnostics': input_diagnostics(row, links), 'source_occurrences': occurrences.get(ident, []),
            'mapping_precision': 'LOGICAL_UNIT_TO_PHYSICAL_OCCURRENCES',
            'lineage': lineage(project, root, section['id'], ident, cache=input_cache)}
        item.update(review_fields(project, root, pb, section['id'], cache=input_cache))
        if stable:
            item['edit_action'] = _action('paragraph_plan', section['id'], plan_revision, nr, paragraph_fields, row, reader_basis=pb,
                action='upsert', paragraph_id=ident)
            item['edit_action']['choices_read'] = read_handle(project, section['id'], paragraph_id=ident, edit_choices=True)
            item['remove_action'] = _action('paragraph_plan', section['id'], plan_revision, nr, [], {}, reader_basis=pb,
                action='remove', paragraph_id=ident)
        if stable:
            from laplace.manuscript.reader_restructure import action as restructure_action
            split=restructure_action(project,section['id'],'preview-restructure',kind='logical-split',draft={'paragraph_ids':[ident],'successor_count':2})
            merge=restructure_action(project,section['id'],'preview-restructure',kind='logical-merge',draft={'paragraph_ids':[ident]})
            merge['choices_read']=read_handle(project,section['id'])
            item['restructure_actions']={'split':split,'merge':merge}
        items.append(item)
    next_offset = paragraph_offset + len(selected)
    next_read = (read_handle(project, section['id'], paragraph_offset=next_offset, paragraph_limit=paragraph_limit or 20,
        paragraph_as_of=nr) if paragraph_id is None and next_offset < len(paragraphs) else None)
    plan = {'section_id': section['id'], 'status': 'DECLARED' if narrative_value is not None else 'NOT_DECLARED',
        'revision': nr, 'identity_status': 'STABLE' if stable else 'UNPROVEN_LEGACY',
        'read_handle': read_handle(project, section['id']),
        'paragraphs': {'items': items, 'total': len(paragraphs), 'offset': paragraph_offset, 'limit': paragraph_limit, 'next_read': next_read}}
    if stable:
        candidate_id = _new_id(root, project, np, section['id'], nr, paragraphs)
        create_cache = {**cache, 'paragraph_rows': [*paragraphs, {'paragraph_id': candidate_id}]}
        create_cache.pop('paragraph_positions', None)
        create_inputs, _ = _inputs(project, root, section, sections, {'paragraph_id': candidate_id}, contracts,
            architecture, paragraph=True, cache=create_cache)
        create_basis = _basis(project, np, candidate_id, None, create_inputs, section['id'])
        plan['create_action'] = _action('paragraph_plan', section['id'], plan_revision, nr, paragraph_fields, {},
            reader_basis=create_basis, action='upsert', paragraph_id=candidate_id, create=True)
        plan['create_action']['placement'] = {'kind': 'APPEND', 'after_paragraph_id': ids[-1] if ids else None}
        plan['create_action']['choices_read'] = read_handle(project, section['id'], edit_choices=True)
        order_inputs, _ = _inputs(project, root, section, sections, {}, contracts, architecture, paragraph=True, cache=cache)
        order_basis = _basis(project, np, '@order', ids, order_inputs, section['id'])
        plan['reorder_action'] = _action('paragraph_plan', section['id'], plan_revision, nr, [], {},
            reader_basis=order_basis, action='reorder', order=ids)
        plan['reorder_action']['choices'] = [{'value': row['paragraph_id'], 'label': str(row.get('proposition') or row.get('function') or row['paragraph_id'])[:200]} for row in paragraphs]
    from laplace.manuscript import reader_restructure
    plan['pending_restructures']=reader_restructure.pending(project,section['id'],root)
    plan['latest_restructure']=reader_restructure.latest_operation(project,section['id'],root)
    return {'reader_transition': transition, 'paragraph_plan': plan,
            'reader_inputs': {'architecture_prior': architecture}}


GUARD_SCHEMA = 'laplace.project-structure-guard/1'
GUARD_SUBJECTS = ('contract', 'paragraph', 'create', 'reorder', 'section', 'structure')
GUARD_ROW_CLIP = 200
GUARD_TEXT_CLIP = 150   # serialized bytes of an authored field on a default subject read (repair2 R2); edit_choices is whole
GUARD_OMITTED_NOTE = ('members, support, evidence, edges, history, descriptors and full authored text: full_read, or the '
                      'subject read with edit_choices for one call\'s descriptors and exact values')
GUARD_PAGE_ROWS = 4   # the contract subject's default paragraph page; paragraph_as_of continues it exactly


def _guard_action(action):
    """The exact owner-issued edit call: operation, payload (every guard field) and HTTP route; the
    typed field descriptors and choice lists (12-14 KB per section on the live project) are the
    plain detail read's."""
    if not isinstance(action, dict):
        return None
    return {key: action[key] for key in ('operation', 'payload', 'http', 'placement') if key in action}


def _guard_handle(handle, **scope):
    if not isinstance(handle, dict):
        return None
    payload = {**(handle.get('payload') or {}), **scope, 'projection': 'guard'}
    return {'operation': 'structure', 'payload': payload,
            'http': {'method': 'GET', 'route': '/work/structure', 'query': {**((handle.get('http') or {}).get('query') or {}), **scope, 'projection': 'guard'}}}


def _serialized_bytes(text):
    """The bytes `text` occupies inside a JSON string (ensure_ascii=False), without the quotes."""
    return len(json.dumps(text, ensure_ascii=False).encode('utf-8')) - 2


def _clip(value, limit=GUARD_ROW_CLIP):
    """The longest prefix of `value` whose JSON-serialized UTF-8 form (ensure_ascii=False, the form
    the HTTP surface sends) is at most `limit` bytes, with an ellipsis (3 bytes) when clipped; a
    character or escape sequence is never split (C10-C11 H1: character clips were not byte caps;
    CJK and quoted text overran the 12,000 B page)."""
    text = str(value or '')
    if _serialized_bytes(text) <= limit:
        return text
    used, end = 0, 0
    for index, char in enumerate(text):
        cost = _serialized_bytes(char)
        if used + cost > limit - 3:
            break
        used += cost
        end = index + 1
    return text[:end] + '…'


GUARD_SELECTOR_RULE = ('projection:guard reads exactly one canonical section_ids entry and no files, node_id, node_ids or sections '
                       'selector. Resolve a node or file first with the plain detail read ({view:detail, node_ids:[...]} or '
                       '{view:detail, files:[...]}): each returned section carries its canonical id; then read '
                       '{view:detail, section_ids:[that id], projection:guard} with the subject you need.')
GUARD_ALTERNATIVE_SELECTORS = ('files', 'node_id', 'node_ids', 'sections')


def guard_section_id(scope):
    """The one canonical section a guard read names (Sol guard-selector-policy, 2026-10-14). The
    bounded subject policy (four-row default, no hydration for create/reorder, one exact basis)
    is defined on the canonical section, so a guard selected by node_ids, node_id, files or the
    sections alias is refused before any owner resolution or row hydration, with the plain detail
    read as the route that resolves those selectors to a canonical id. Every guard handle the owner
    issues already carries section_ids. The check is on key PRESENCE, as in the declared schema and
    the qualified human parser (Sol guard-selector-policy-empty-presence): files:[], node_ids:[],
    node_id:"" or sections:null name an alternative selector and refuse like a populated one. No
    door injects an absent key before this check (the HTTP door forwards only the query's keys, the
    native door only the payload's), so a canonical request is never mistaken for a mixed one."""
    ids = scope.get('section_ids')
    present = [key for key in GUARD_ALTERNATIVE_SELECTORS if key in scope]
    if present or not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str) or not ids[0].strip():
        raise ValueError(GUARD_SELECTOR_RULE + (' (present: %s)' % ', '.join(present) if present else ''))
    return ids[0]


def guard_detail_scope(scope):
    """The detail-owner scope one guard subject needs (Sol N1-default, 2026-10-14). The owner's
    default paragraph page is 20 rows, which the contract guard projected to 12.6-13.3 KB at 16-20
    ordinary rows; the contract subject therefore reads GUARD_PAGE_ROWS rows unless the caller names
    a page (paragraph_offset/paragraph_limit) or a paragraph, and `next_read` continues that page
    with `paragraph_as_of`. A create or reorder subject carries no rows (its calls are built from
    the complete plan list, not the hydrated page), so no unrelated row is enriched for it; the
    paragraph cut `paragraph_as_of` still refuses a changed plan."""
    guard_section_id(scope)
    subject = scope.get('subject') or ('paragraph' if scope.get('paragraph_id') else 'contract')
    detail = {key: value for key, value in scope.items() if key != 'subject'}
    if subject in ('create', 'reorder', 'section'):
        return {**{key: value for key, value in detail.items() if key not in ('paragraph_id', 'paragraph_offset', 'paragraph_limit')
                   and not (key == 'edit_choices' and subject != 'create')},
                'paragraph_limit': 0}
    if subject == 'structure':
        return {key: value for key, value in detail.items() if key not in ('paragraph_offset', 'paragraph_limit', 'edit_choices')}
    if subject == 'contract' and 'paragraph_limit' not in detail and 'paragraph_id' not in detail:
        detail['paragraph_limit'] = GUARD_PAGE_ROWS
    return detail


def guard_projection(context, scope):
    """One selected section's exact reader-plan edit guards with bounded authored context.

    Built from the canonical detail read (`project_structure.context`), so every token here is the
    one that read published: `expected_plan_revision` (the plan-file home), the authored artifact
    revisions (`expected_contract_revision` / `expected_narrative_revision`) and each subject's
    `expected_reader_basis`. Nothing is minted here and no second token store exists; a write that
    carries a stale guard still refuses with CHANGED_INPUT at the owner.

    ONE subject per read (Sol N1, 2026-10-14): each reader basis is ~110 B per member pin, so a
    read that carried the section contract, the create and reorder calls and every row's edit and
    remove calls grew past the native ceiling the moment paragraphs existed (22.9 KB at one row,
    45.8 KB at four, on a 17-member chapter). `subject` selects which exact call travels:
      contract  (default) the section_contract edit call, the section's source binding, current
                authored values, input currentness and a clipped id/proposition row list of the
                paragraph page (GUARD_PAGE_ROWS rows by default, continued with next_read) with one
                subject handle per row; no paragraph bases
      paragraph (paragraph_id) that one unit's full authored row, source occurrences, input
                currentness and its edit and remove calls; no section contract call
      create    the owner-issued create call (unused paragraph identity, placement); no row hydrated
      reorder   the reorder call with the complete current order; no row hydrated
      section   (C10-C11, 2026-10-14) the section-level calls beside the contract: link a source
                heading (clearing_action), prepare work (prepare_action) and create review work for
                the reader transition (review_action); no row hydrated. The bounded human display
                (projection:display) names these as doors and opens them here.
      structure (paragraph_id) one row's structural and review calls: split and merge previews
                (restructure_actions) and create review work (review_action); the row's own edit
                and remove calls stay on subject:paragraph.
    The plain detail read remains `full_read`.
    """
    wanted = guard_section_id(scope)
    sections = [row for row in context.get('sections') or [] if row.get('id') == wanted]
    if len(sections) != 1:
        raise ValueError('projection:guard reads exactly one existing reader-plan section; section_ids entry %r is not a current section (read view:summary for current ids).' % wanted)
    subject = scope.get('subject') or ('paragraph' if scope.get('paragraph_id') else 'contract')
    if subject not in GUARD_SUBJECTS:
        raise ValueError('projection:guard subject must be contract, paragraph, create, reorder, section or structure')
    if subject in ('paragraph', 'structure') and not scope.get('paragraph_id'):
        raise ValueError('projection:guard subject:%s needs paragraph_id; the contract read lists each row with its subject handle' % subject)
    # THE CHOICES, WHEN NEEDED (C10-C11, 2026-10-14): `edit_choices: true` on a guard read keeps the
    # typed field descriptors and their choice lists on the subject's one call (the detail owner
    # enriched them under the same flag), so an editor opens on ONE bounded read instead of the
    # guard plus a `choices_read` of the whole detail; the descriptors stay off every other read.
    with_fields = bool(scope.get('edit_choices'))
    # Repair2 R2: the editor read (edit_choices) carries the call's typed descriptors AND its exact
    # complete current values (the detail owner's `values`, keyed by descriptor), so a fresh editor
    # opens on the authored text, an untouched field sends no change and a cleared field is a change.
    # The default subject reads are display-and-guard carriers: their authored text is clipped at
    # GUARD_TEXT_CLIP serialized bytes with the clipped names listed, never the call or its guards.
    def guard_action(action):
        value = _guard_action(action)
        if value is not None and with_fields and isinstance(action, dict) and action.get('fields') is not None:
            value['fields'] = action['fields']
            value['values'] = copy.deepcopy(action.get('values') or {})
        return value
    def shown(values, names):
        """Authored text for a default (display) subject read: clipped by serialized bytes, the clipped
        names listed; the exact text is on the edit_choices read."""
        if with_fields:
            return {key: values.get(key) for key in names if key in values}, []
        out, clipped = {}, []
        for key in names:
            if key not in values:
                continue
            text = values.get(key)
            if isinstance(text, str) and _serialized_bytes(text) > GUARD_TEXT_CLIP:
                out[key] = _clip(text, GUARD_TEXT_CLIP); clipped.append(key)
            else:
                out[key] = text
        return out, clipped
    def payload_only(handle):
        return {'operation': handle['operation'], 'payload': handle['payload']} if isinstance(handle, dict) else handle
    section = sections[0]
    sid = section['id']
    transition = section.get('reader_transition') or {}
    plan = section.get('paragraph_plan') or {}
    paragraphs = plan.get('paragraphs') or {}
    rows = paragraphs.get('items') or []
    base_handle = transition.get('read_handle') or plan.get('read_handle')
    def subject_handle(**extra):
        clean = {key: value for key, value in (base_handle.get('payload') if isinstance(base_handle, dict) else {}).items()
                 if key not in ('paragraph_id', 'paragraph_offset', 'paragraph_limit', 'paragraph_as_of', 'edit_choices', 'subject')}
        handle = {'operation': 'structure', 'payload': clean, 'http': {'method': 'GET', 'route': '/work/structure',
                  'query': {'project': context.get('project'), **clean}}}
        return _guard_handle(handle, **extra)
    source = section.get('source') or {}
    members = section.get('members') or {}
    selected = context.get('selected_source') or {}
    result = {'schema_version': GUARD_SCHEMA, 'project': context.get('project'), 'section_id': sid,
            'projection': 'guard', 'subject': subject,
            'eligible_for_authoring': context.get('eligible_for_authoring'),
            'authority': context.get('authority'),
            'selected_source': {key: selected.get(key) for key in ('status', 'root', 'edition', 'revision', 'selection_identity', 'read_only') if key in selected},
            'section': {**{key: section.get(key) for key in ('id', 'title', 'kind', 'number', 'parent_id', 'collection', 'job') if key in section},
                        'member_count': members.get('total', len(section.get('node_ids') or []) + len(section.get('beat_ids') or [])),
                        'source': source},
            'paragraph_plan': {key: plan.get(key) for key in ('section_id', 'status', 'revision', 'identity_status') if key in plan},
            # the subject handles once, as native payloads; the HTTP form is the same payload as
            # query parameters on read_handle.http.route (one http block per read, not per row)
            'subject_reads': {'contract': subject_handle(subject='contract')['payload'],
                              'paragraph': subject_handle(subject='paragraph', paragraph_id='<paragraph_id from the contract read rows>')['payload'],
                              'create': subject_handle(subject='create')['payload'], 'reorder': subject_handle(subject='reorder')['payload'],
                              'http': 'GET read_handle.http.route with the payload fields as query parameters plus project'},
            'full_read': {'operation': 'structure', 'payload': {'view': 'detail', 'section_ids': [sid]},
                          'http': {'method': 'GET', 'route': '/work/structure', 'query': {'project': context.get('project'), 'view': 'detail', 'section_ids': [sid]}}},
            'omitted': GUARD_OMITTED_NOTE}
    if subject != 'contract':
        # a paragraph/create/reorder subject is one exact call: the section's source binding, the
        # four subject handles and the omission list are the contract read's (2.9 KB on a wide chapter)
        result['section'] = {key: value for key, value in result['section'].items() if key not in ('source',)}
        result['subject_reads'] = {'contract': result['subject_reads']['contract'], 'http': result['subject_reads']['http']}
        result.pop('omitted')
        result['scope'] = 'One exact owner-issued call with its guards; the section binding, authored contract and row list are on subject_reads.contract, everything else on full_read.'
    if subject == 'contract':
        guard = {key: transition.get(key) for key in ('section_id', 'status', 'revision', 'subject_revision',
                                                       'input_currentness', 'review', 'diagnostics') if key in transition}
        # the authored contract fields only (not the plan copy of nodes_in_order), clipped on a default read
        fields = transition.get('fields') or {}
        guard['fields'], clipped = shown(fields, (*CONTRACT_STRINGS, *CONTRACT_ARRAYS))
        if clipped:
            guard['clipped'] = clipped
        guard['edit_action'] = guard_action(transition.get('edit_action'))
        guard['choices_read'] = payload_only(subject_handle(subject='contract', edit_choices=True))
        guard['reader_basis'] = 'edit_action.payload.expected_reader_basis'
        guard['review_action_read'] = 'subject_reads.section carries reader_transition.review_action beside the section-level calls'
        guard['read_handle'] = payload_only(subject_handle(subject='contract'))
        result['structure_observation'] = {key: value for key, value in (context.get('structure_observation') or {}).items() if key != 'reader_subjects'}
        result['reader_transition'] = guard
        # the paragraph page as a bounded row list: identity, clipped text and the one subject
        # handle per row; bases travel only on that row's own subject read
        items = [{'paragraph_id': row.get('paragraph_id'), 'function': _clip(row.get('function')),
                  'proposition': _clip(row.get('proposition')), 'identity_status': row.get('identity_status'),
                  'input_currentness': (row.get('input_currentness') or {}).get('status')}
                 for row in rows if isinstance(row, dict)]
        next_read = payload_only(_guard_handle(paragraphs.get('next_read'), subject='contract')) if paragraphs.get('next_read') else None
        result['paragraph_plan']['paragraphs'] = {'items': items, 'total': paragraphs.get('total'), 'offset': paragraphs.get('offset'),
                                                  'limit': paragraphs.get('limit'), 'next_read': next_read,
                                                  'scope': 'Identity rows with clipped text (%d characters); a row\'s edit and remove calls are read with subject_reads.paragraph and its paragraph_id; create and reorder calls with subject_reads.create / subject_reads.reorder' % GUARD_ROW_CLIP}
        return result
    if subject == 'paragraph':
        wanted = scope.get('paragraph_id')
        row = next((row for row in rows if isinstance(row, dict) and row.get('paragraph_id') == wanted), None)
        if row is None:
            raise ValueError('The exact paragraph ID is absent from this page; read the contract subject to list current rows.')
        item = {key: row.get(key) for key in ('section_id', 'paragraph_id') if key in row}
        authored, clipped = shown(row, (*PARAGRAPH_STRINGS, *PARAGRAPH_ARRAYS))
        item.update(authored)
        if clipped:
            item['clipped'] = clipped
        item.update({key: row.get(key) for key in ('identity_status', 'subject_revision', 'input_currentness', 'diagnostics', 'review') if key in row})
        item['source_occurrences'] = [{key: occurrence.get(key) for key in ('file', 'line_start', 'line_end', 'status') if key in occurrence}
                                      for occurrence in row.get('source_occurrences') or [] if isinstance(occurrence, dict)][:8]
        item['edit_action'] = guard_action(row.get('edit_action'))
        if item['edit_action'] is not None:
            item['edit_action']['choices_read'] = subject_handle(subject='paragraph', paragraph_id=wanted, edit_choices=True)
        item['remove_action'] = _guard_action(row.get('remove_action'))
        item['reader_basis'] = 'edit_action.payload.expected_reader_basis'
        item['read_handle'] = subject_handle(subject='paragraph', paragraph_id=wanted)
        result['paragraph'] = item
        return result
    if subject == 'section':
        result['section_calls'] = {name: section[name] for name in ('clearing_action', 'prepare_action') if section.get(name) is not None}
        result['section_calls']['review_action'] = _guard_action(transition.get('review_action'))
        result['section_calls']['read_handle'] = subject_handle(subject='section')
        return result
    if subject == 'structure':
        wanted = scope.get('paragraph_id')
        row = next((row for row in rows if isinstance(row, dict) and row.get('paragraph_id') == wanted), None)
        if row is None:
            raise ValueError('The exact paragraph ID is absent from this page; read the contract subject to list current rows.')
        result['paragraph'] = {'paragraph_id': wanted, 'identity_status': row.get('identity_status'),
                               'review_action': _guard_action(row.get('review_action')),
                               'restructure_actions': {key: {k: v for k, v in value.items() if k != 'choices_read'}
                                                       for key, value in (row.get('restructure_actions') or {}).items() if isinstance(value, dict)},
                               'read_handle': subject_handle(subject='structure', paragraph_id=wanted)}
        return result
    if subject == 'create':
        if plan.get('create_action') is None:
            raise ValueError('No create call is offered: the paragraph plan identity is not STABLE; read full_read for its reconciliation.')
        result['create_action'] = guard_action(plan['create_action'])
        result['create_action']['choices_read'] = subject_handle(subject='create', edit_choices=True)
        result['create_action']['reader_basis'] = 'payload.expected_reader_basis'
        return result
    if plan.get('reorder_action') is None:
        raise ValueError('No reorder call is offered: the paragraph plan identity is not STABLE; read full_read for its reconciliation.')
    result['reorder_action'] = _guard_action(plan['reorder_action'])
    result['reorder_action']['order_choices'] = [{'value': row.get('value'), 'label': _clip(row.get('label'), 120)} for row in plan['reorder_action'].get('choices') or []]
    result['reorder_action']['reader_basis'] = 'payload.expected_reader_basis'
    return result


DISPLAY_SCHEMA = 'laplace.project-structure-display/1'
DISPLAY_PAGE_ROWS = 6      # paragraph rows per display page (the Reader plan's 6+6 convention)
DISPLAY_MEMBER_ROWS = 6    # member rows per display page
DISPLAY_EVIDENCE_ROWS = 6
DISPLAY_TEXT_CLIP = 150    # serialized bytes of the proposition on a list row; a single-paragraph display read is whole
DISPLAY_INPUT_ROWS = 12    # linked inputs and diagnostics on a whole-row display, with their totals
DISPLAY_ROW_STRINGS = ('proposition', 'function')   # the list row's authored text; the whole row opens on paragraphs.row_read
# ACTUAL-C1011-DISPLAY-BYTES (2026-10-14): the section's narrative beats are LAZY. Measured on a
# populated owner (64 sections, 13 beats, 22 rows, 17 members): 13 beats at about 450 B each cost
# 5.9 KB and took the page to 17.4 KB. The page states the exact beat count and the read of the first
# beat page (spine_page); that read (the display with spine_offset) returns ONLY a compact page of
# beats (id, term clipped, placed) with its continuation, never the section again. A beat's narrative
# is on its beat read (spine_page.row_read with the id); member rows that are beats say so (beat:true).
DISPLAY_SPINE_ROWS = 12
DISPLAY_TERM_CLIP = 120
DISPLAY_OMITTED = ('calls (subject_reads)', 'narrative beats (spine_page.read; each beat on spine_page.row_read)', 'reader_basis', 'links/diagnostics/lineage (row display)', 'source_support', 'edges', 'gaps',
                   'scoped_history', 'direct_dependencies', 'reader_inputs', 'outline', 'ancestors', 'children', 'boundaries')
PLAN_SCHEMA = 'laplace.project-structure-plan/1'


def _display_text(row, names, limit=DISPLAY_TEXT_CLIP):
    """Authored strings clipped for display; `clipped` names the fields whose whole text is on the subject read."""
    value, clipped = {}, []
    for name in names:
        text = row.get(name)
        if text is None or text == '':
            continue
        if isinstance(text, str) and _serialized_bytes(text) > limit:
            value[name] = _clip(text, limit)
            clipped.append(name)
        else:
            value[name] = text
    return value, clipped


def _display_currentness(value):
    current = (value or {}).get('input_currentness') or {}
    # a CURRENT status carries only the owner's standing disclaimer as its reason (stated on the
    # subject reads); a changed or unobserved status keeps its reason (ACTUAL-C1011-DISPLAY-BYTES)
    return {key: current.get(key) for key in ('status', 'reason', 'changed_inputs', 'unobserved_inputs')
            if key in current and not (key == 'reason' and current.get('status') == 'CURRENT')}


def _display_handle(handle, **scope):
    """A display continuation: the native payload only (its HTTP form is GET /work/structure with the
    payload as query parameters plus project, stated once on subject_reads.http)."""
    if not isinstance(handle, dict):
        return None
    payload = {key: value for key, value in {**(handle.get('payload') or {}), **scope}.items() if key not in ('edit_choices', 'subject')}
    payload['projection'] = 'display'
    return {'operation': 'structure', 'payload': payload}


def _display_read(handle, limit=DISPLAY_INPUT_ROWS):
    """A linked read as its native handle only."""
    if not isinstance(handle, dict):
        return None
    return {key: handle[key] for key in ('operation', 'payload') if key in handle}


def display_projection(context, scope):
    """THE HUMAN DISPLAY of one reader-plan section (ACTUAL-C6-DETAIL-BYTES, 2026-10-14).

    The plain detail read of one human section measured 800,724 B on the live project (20 paragraph
    rows, 17 members): each paragraph row carries its edit, remove, review and restructure calls,
    its reader basis, linked inputs and diagnostics (about 30 KB a row), and the structure
    observation repeats every reader subject. A person reading the plan needs the authored words,
    the standing of each row and the doors; the exact calls are needed only when an action opens.

    So this projection is bounded and the calls are lazy: from the same detail owner (`context`)
    read at DISPLAY_PAGE_ROWS paragraph rows and DISPLAY_MEMBER_ROWS members, it keeps the section
    identity, its source binding and the two section-level calls (link source, prepare work), the
    reader transition's authored fields and currentness, the paragraph page as display rows
    (authored text clipped at DISPLAY_TEXT_CLIP with the clipped fields named, status, currentness,
    occurrence count, which doors the row offers) with an exact display continuation, the member
    page, the placed narrative beats and the first evidence rows with totals. Every edit call,
    descriptor and basis is acquired through `subject_reads` (projection:guard, `edit_choices` for
    the descriptors) when the action opens; the complete plan order and the mutation revision the
    plan-level editors need are `plan_read` (view:plan); the unprojected detail stays `full_read`.
    Nothing here is minted: every token travels on the guard read that the action is sent with.
    """
    wanted = guard_section_id(scope)
    sections = [row for row in context.get('sections') or [] if row.get('id') == wanted]
    if len(sections) != 1:
        raise ValueError('projection:display reads exactly one existing reader-plan section; section_ids entry %r is not a current section (read view:summary for current ids).' % wanted)
    section = sections[0]
    sid, project = section['id'], context.get('project')
    base = read_handle(project, sid)
    def subject(**extra):
        return _guard_handle(base, **extra)
    transition = section.get('reader_transition') or {}
    plan = section.get('paragraph_plan') or {}
    paragraphs = plan.get('paragraphs') or {}
    members = section.get('members') or {}
    member_rows = members.get('items') or []
    availability = {row.get('id'): row for row in (section.get('nodes') or []) + (section.get('beats') or []) if isinstance(row, dict)}
    nodes = []
    for row in member_rows:
        known = availability.get(row.get('id')) or {}
        node = {'id': row.get('id')}   # its concept read is {operation: concept, payload: {node: id}}
        if row.get('role') and row.get('role') != 'node':
            node['role'] = row['role']
        if known.get('label') and known['label'] != row.get('id'):
            node['label'] = known['label']
        if known.get('kind'):
            node['kind'] = known['kind']
        if row.get('missing') or known.get('status'):
            node['status'] = known.get('status') or 'MISSING'
            node['missing'] = bool(row.get('missing'))
        nodes.append(node)
    evidence_rows = section.get('evidence') or context.get('evidence') or []
    evidence = [{key: item.get(key) for key in ('id', 'title', 'label', 'node_id', 'status', 'revision_match', 'read_handle', 'detail_read') if key in item}
                for item in evidence_rows[:DISPLAY_EVIDENCE_ROWS] if isinstance(item, dict)]
    # ONE paragraph named (paragraph_id): the whole row; the page: list rows (proposition and
    # function, clipped) that open to the whole row through their own display read
    whole = bool(scope.get('paragraph_id'))
    rows = []
    for row in paragraphs.get('items') or []:
        if not isinstance(row, dict):
            continue
        strings, clipped = _display_text(row, PARAGRAPH_STRINGS if whole else DISPLAY_ROW_STRINGS, limit=MAX_BYTES if whole else DISPLAY_TEXT_CLIP)
        occurrences = row.get('source_occurrences') or []
        review = row.get('review') or {}
        doors = [key for key, present in (('edit', row.get('edit_action') is not None), ('remove', row.get('remove_action') is not None),
                                           ('review', row.get('review_action') is not None)) if present]
        doors += sorted((row.get('restructure_actions') or {}).keys())
        if (row.get('lineage') or {}).get('items') or (row.get('lineage') or {}).get('read'):
            doors.append('lineage')
        currentness = {key: value for key, value in _display_currentness(row).items() if key != 'reason' and value not in ([], None)}
        item = {**({'section_id': sid} if whole else {}), 'paragraph_id': row.get('paragraph_id'), **strings,
                **{key: row.get(key) for key in PARAGRAPH_ARRAYS if row.get(key)},
                # the authored fields beyond the ones shown; their text is on read_handle (the whole row)
                'authored': [key for key in (*PARAGRAPH_STRINGS, *PARAGRAPH_ARRAYS) if row.get(key) and key not in strings],
                'identity_status': row.get('identity_status'), 'input_currentness': currentness, 'doors': doors,
                'source_occurrence_total': len(occurrences)}
        # repair2 R2: a list row's whole read is derived from its paragraph_id (display payload with
        # paragraph_id), stated once in `row_read`; it is not repeated per row
        if review.get('status') and review.get('status') not in ('NOT_REVIEWED', 'NOT_ESTABLISHED'):
            item['review'] = {key: review.get(key) for key in ('status', 'label') if key in review}
        if whole:
            diagnostics = row.get('diagnostics') or []
            links = row.get('links') or []
            item.update({'subject_revision': row.get('subject_revision'), 'input_currentness': _display_currentness(row),
                         'diagnostics': [{**{key: entry.get(key) for key in ('kind', 'subject', 'status', 'reason') if key in entry}, 'read': _display_read(entry.get('read'))}
                                         for entry in diagnostics[:DISPLAY_INPUT_ROWS] if isinstance(entry, dict)],
                         'diagnostics_total': len(diagnostics),
                         'links': [{**{key: entry.get(key) for key in ('kind', 'label', 'status') if key in entry}, 'read': _display_read(entry.get('read'))}
                                   for entry in links[:DISPLAY_INPUT_ROWS] if isinstance(entry, dict)],
                         'links_total': len(links),
                         'source_occurrences': [{key: occurrence.get(key) for key in ('file', 'line_start', 'line_end', 'status', 'spec_ids') if key in occurrence}
                                                for occurrence in occurrences[:8] if isinstance(occurrence, dict)],
                         'lineage': row.get('lineage'), 'review': review,
                         'subject_read': {'operation': 'structure', 'payload': subject(subject='paragraph', paragraph_id=row.get('paragraph_id'))['payload']}})
        if clipped:
            item['clipped'] = clipped
        rows.append(item)
    next_read = _display_handle(paragraphs.get('next_read')) if paragraphs.get('next_read') else None
    pending = plan.get('pending_restructures') or []
    display_plan = {key: plan.get(key) for key in ('section_id', 'status', 'reason', 'revision', 'identity_status') if key in plan}
    display_plan.update({'input_currentness': _display_currentness(plan) if plan.get('input_currentness') else None,
                         'paragraphs': {'items': rows, 'total': paragraphs.get('total'), 'offset': paragraphs.get('offset'),
                                        'limit': paragraphs.get('limit'), 'next_read': next_read,
                                        'row_read': {'operation': 'structure', 'payload': {**_display_handle(base)['payload'], 'paragraph_id': '<paragraph_id>'}}},
                         'doors': {'create': plan.get('create_action') is not None, 'reorder': plan.get('reorder_action') is not None},
                         'pending_restructures': pending[:3], 'pending_restructures_total': len(pending),
                         'latest_restructure': plan.get('latest_restructure'),
                         'read_handle': _display_handle(base)})
    if display_plan['input_currentness'] is None:
        display_plan.pop('input_currentness')
    display_transition = {key: transition.get(key) for key in ('section_id', 'status', 'reason', 'revision', 'subject_revision') if key in transition}
    # repair2 R2: the authored contract on the display page is clipped by serialized bytes (the clipped
    # names listed); the exact values are on the contract subject read with edit_choices
    contract_fields, contract_clipped = {}, []
    for key in (*CONTRACT_STRINGS, *CONTRACT_ARRAYS):
        value = (transition.get('fields') or {}).get(key)
        if value in (None, '', []):
            continue
        if isinstance(value, str) and _serialized_bytes(value) > DISPLAY_TEXT_CLIP:
            value = _clip(value, DISPLAY_TEXT_CLIP); contract_clipped.append(key)
        contract_fields[key] = value
    display_transition['fields'] = contract_fields
    if contract_clipped:
        display_transition['clipped'] = contract_clipped
        display_transition['values_read'] = {'operation': 'structure', 'payload': {**subject(subject='contract')['payload'], 'edit_choices': True}}
    display_transition.update({'input_currentness': _display_currentness(transition),
                               'review': {key: value for key, value in (transition.get('review') or {}).items() if key in ('status', 'label', 'read', 'records')},
                               'doors': {'edit': transition.get('edit_action') is not None, 'review': transition.get('review_action') is not None},
                               'read_handle': {'operation': 'structure', 'payload': subject(subject='contract')['payload']}})
    source = {key: value for key, value in (section.get('source') or {}).items()
              if key not in ('clearing_read', 'source_titles', 'plan_title', 'title_status', 'selected_root', 'mapping', 'source_label')}
    beats = [beat for beat in context.get('spine') or [] if isinstance(beat, dict)]
    row_read = {'operation': 'structure', 'payload': {'view': 'detail', 'node_id': '<id>'}}
    spine_read = lambda offset: {'operation': 'structure', 'payload': {**_display_handle(base)['payload'], 'spine_offset': offset}}
    if 'spine_offset' in scope:
        # the beat page: compact rows of this section's beats and the exact continuation; the
        # section itself is not repeated (its page is the read without spine_offset)
        spine_offset = scope.get('spine_offset')
        if isinstance(spine_offset, bool) or not isinstance(spine_offset, int) or spine_offset < 0 or spine_offset >= max(len(beats), 1):
            raise ValueError('projection:display spine_offset must be a whole number below the section\'s %d narrative beats (read spine_page.read, then its next_read).' % len(beats))
        # a lone remainder joins this page, so no continuation lists a single beat (the R6 fold rule)
        following = len(beats) if len(beats) - spine_offset == DISPLAY_SPINE_ROWS + 1 else min(len(beats), spine_offset + DISPLAY_SPINE_ROWS)
        observation = context.get('structure_observation') or {}
        return {'schema_version': DISPLAY_SCHEMA, 'project': project, 'section_id': sid, 'projection': 'display', 'page': 'spine',
                'spine': [{'id': beat.get('id'), **({'term': _clip(beat['term'], DISPLAY_TERM_CLIP)} if beat.get('term') else {}),
                           **({'placed': True} if beat.get('placed') else {})}
                          for beat in beats[spine_offset:following]],
                'spine_page': {'total': len(beats), 'offset': spine_offset, 'limit': following - spine_offset,
                               'next_read': spine_read(following) if following < len(beats) else None, 'row_read': row_read},
                'structure_observation': {key: observation.get(key) for key in ('plan_revision', 'spine_revision') if key in observation},
                'revision': context.get('revision')}
    spine_page = {'total': len(beats), 'read': spine_read(0) if beats else None, 'row_read': row_read}
    # a member row that is already a beat says so (its beats are read lazily)
    beat_ids = {beat.get('id') for beat in beats}
    for node in nodes:
        if node.get('id') in beat_ids:
            node['beat'] = True
    selected = context.get('selected_source') or {}
    result = {'schema_version': DISPLAY_SCHEMA, 'project': project, 'section_id': sid, 'projection': 'display',
              'eligible_for_authoring': context.get('eligible_for_authoring'), 'authority': context.get('authority'),
              'selected_source': {key: selected.get(key) for key in ('status', 'root', 'edition', 'revision', 'selection_identity', 'read_only') if key in selected},
              # the displayed scope's observation: the page's reader subjects as compact refs (the
              # send refuses on a changed subject or input exactly as with whole bases)
              'structure_observation': {**{key: value for key, value in (context.get('structure_observation') or {}).items() if key != 'reader_subjects'},
                                        'reader_subjects': [ref for ref in [subjects_ref((context.get('structure_observation') or {}).get('reader_subjects') or [])] if ref]},
              'sections': [{**{key: section.get(key) for key in ('id', 'title', 'kind', 'number', 'parent_id', 'collection', 'depth', 'job') if key in section},
                            'notes': _clip(section.get('notes'), 600),
                            'source': source,
                            # the section-level calls (link a source heading, prepare work) open on
                            # the contract subject read, which carries them beside the edit call
                            'doors': [key for key, name in (('link_source', 'clearing_action'), ('prepare_work', 'prepare_action')) if section.get(name) is not None],
                            # the member page as display rows (label, kind, standing, concept read); the
                            # ordered-membership cut and continuation are the detail owner's
                            'nodes': nodes,
                            'members': {**{key: members.get(key) for key in ('offset', 'limit', 'total', 'cut', 'omitted_before', 'omitted_after') if key in members},
                                        **({'next_read': _display_handle(members['next_read'])} if members.get('next_read') else {})},
                            'member_count': members.get('total', len(section.get('node_ids') or []) + len(section.get('beat_ids') or [])),
                            'evidence': evidence, 'evidence_total': len(evidence_rows),
                            'reader_transition': display_transition, 'paragraph_plan': display_plan}],
              'spine_page': spine_page, 'evidence': evidence,
              'subject_reads': {'contract': subject(subject='contract')['payload'],
                                'subjects': 'contract | section | paragraph+paragraph_id | structure+paragraph_id | create | reorder; edit_choices:true adds descriptors',
                                'http': 'GET /work/structure with the payload fields as query parameters plus project'},
              'plan_read': {'operation': 'structure', 'payload': {'view': 'plan'}},
              'full_guard_read': {'operation': 'structure', 'payload': {'view': 'plan'}},
              'full_read': {'operation': 'structure', 'payload': {'view': 'detail', 'section_ids': [sid]}},
              'omitted': list(DISPLAY_OMITTED),
              # the whole-row read names its scope (its size grows with the authored fields); the page
              # read's scope is the schema's: DISPLAY_PAGE_ROWS rows clipped at DISPLAY_TEXT_CLIP bytes
              **({'scope': 'whole row: authored text unclipped; links and diagnostics capped at %d with totals; not bounded by the page budget' % DISPLAY_INPUT_ROWS} if whole else {})}
    result['revision'] = context.get('revision')
    return result


def plan_guard(state_value):
    """THE PLAN GUARD (view:plan, 2026-10-14): the complete ordered reader plan and narrative spine
    identities with the mutation revision the plan-level operations are sent with, and nothing
    hydrated. The plan-item, narrative-beat, add-beat and move-item editors read `view:full` for
    this (302,953-316,437 B on the live project: every logical object, edge, evidence row and
    support body) when all they consume is the section order, titles, parents, collections,
    members and the beats. `revision` is the same `plan` home value the full read publishes, so a
    changed plan still refuses at the owner; no second token is minted."""
    sections = [{**{key: row.get(key) for key in ('id', 'title', 'kind', 'parent_id', 'ancestor_ids', 'child_ids', 'collection', 'number', 'depth', 'order', 'job')
                    if key in row}, 'notes': row.get('notes') or '', 'node_ids': list(row.get('node_ids') or []), 'beat_ids': list(row.get('beat_ids') or []),
                 'nodes': [{'id': node.get('id'), 'missing': bool(node.get('missing'))} for node in row.get('nodes') or [] if isinstance(node, dict)]}
                for row in state_value.get('sections') or []]
    spine = [{key: beat.get(key) for key in ('id', 'term', 'narrative', 'section_ids', 'placed', 'spine_status') if key in beat}
             for beat in state_value.get('spine') or [] if isinstance(beat, dict)]
    selected = state_value.get('selected_source') or {}
    return {'schema_version': PLAN_SCHEMA, 'project': state_value.get('project'), 'view': 'plan',
            'status': state_value.get('status'), 'eligible_for_authoring': state_value.get('eligible_for_authoring'),
            'revision': state_value.get('revision'), 'authority': state_value.get('authority'),
            'identities': state_value.get('identities'),
            'selected_source': {key: selected.get(key) for key in ('status', 'root', 'edition', 'revision', 'selection_identity', 'read_only') if key in selected},
            'sections': sections, 'plan_collections': state_value.get('plan_collections'), 'spine': spine,
            'omitted': ['nodes[bodies]', 'edges', 'evidence', 'gaps', 'logical_objects', 'source_support', 'source_outline', 'relation_diagnostics'],
            'full_read': {'operation': 'structure', 'payload': {'view': 'full'}},
            'scope': 'The complete plan order and narrative spine with the mutation revision; the hydrated structure is full_read.'}


def operation_contracts():
    string = {'type': 'string', 'minLength': 1}
    nullable = {'type': ['string', 'null']}
    def fields(strings, arrays):
        return {'type': 'object', 'additionalProperties': False, 'properties': {
            **{key: {'type': 'string'} for key in strings},
            **{key: {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 80} for key in arrays}}}
    from laplace.core import identity_doors
    common = {'project': string, 'section_id': string, 'expected_plan_revision': string, 'expected': identity_doors.EXPECTED_FIELD,
        'expected_reader_basis': basis_schema(), 'input_observations': {'type': 'object', 'maxProperties': 250,
            'additionalProperties': {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'}}}
    result={
        'section_contract': {'required': ['operation', 'section_id', 'expected_plan_revision', 'expected_contract_revision', 'expected_reader_basis', 'changes'],
            'properties': {**common, 'operation': {'const': 'section_contract'}, 'expected_contract_revision': nullable,
                'changes': fields(CONTRACT_STRINGS, CONTRACT_ARRAYS)}},
        'paragraph_plan': {'required': ['operation', 'section_id', 'expected_plan_revision', 'expected_narrative_revision', 'expected_reader_basis', 'action'],
            'properties': {**common, 'operation': {'const': 'paragraph_plan'}, 'expected_narrative_revision': nullable,
                'action': {'enum': ['upsert', 'remove', 'reorder']}, 'paragraph_id': string, 'create': {'type': 'boolean'},
                'order': {'type': 'array', 'items': string}, 'changes': fields(PARAGRAPH_STRINGS, PARAGRAPH_ARRAYS)}}}
    from laplace.manuscript import reader_restructure
    structural=reader_restructure.contracts();old=result['paragraph_plan']
    old_required=old.pop('required')
    old['properties']={**old['properties'],**structural['properties']}
    old['properties']['action']={'enum':['upsert','remove','reorder',*structural['properties']['action']['enum']]}
    old['required']=['operation','section_id','action']
    old['allOf']=[{'if':{'properties':{'action':{'enum':structural['properties']['action']['enum']}}},
        'then':{'allOf':structural['allOf']},'else':{'required':old_required}}]
    return result


def _artifact_coordinate(project, root, path, *, writable=False):
    """Translate an OWNER-derived physical path, never a caller destination."""
    root, target = Path(root).resolve(), Path(path).resolve()
    context = artifacts.context(root, project)
    source = context['source']
    eligible = (source.get('status') == 'resolved' and source.get('root')
                and (not writable or not source.get('read_only')) and not source.get('foreign'))
    if writable and (source.get('read_only') or source.get('foreign')):
        raise ValueError('read-only/foreign reader publication is refused.')
    if not target.is_relative_to(root):
        raise ValueError('Reader artifact is outside this workspace.')
    base, scope = context['base'].resolve(), 'project'
    if not target.is_relative_to(base):
        directory = source.get('manuscript_dir')
        if not eligible or not directory:
            raise ValueError('Reader artifact has no eligible selected manuscript namespace.')
        base = (root / directory).resolve()
        selected = (root / source['root']).resolve()
        if (not base.is_relative_to(root) or not selected.is_relative_to(base)
                or not selected.is_file() or not target.is_relative_to(base)):
            raise ValueError('Reader artifact is outside the selected manuscript namespace.')
        scope = 'manuscript'
    relative = target.relative_to(base).as_posix()
    if artifacts.resolve_path(root, project, relative, scope, context=context, allow_read_only=not writable) != target:
        raise ValueError('Reader artifact scoped coordinate changed its physical target.')
    return {'path': relative, 'scope': scope}


def change(project, payload, root, *, actor=None):
    """Keep selection fixed while the existing ART owner resolves its scope."""
    from laplace.manuscript import reader_restructure, manuscript_source
    if payload.get('action') in reader_restructure.ACTIONS:
        return reader_restructure.change(project,payload,root,actor=actor)
    root = Path(root).resolve()
    with manuscript_source.selection_mutation(project, root):
        source = manuscript_source.resolve(project, repo_root=root)
        # Project-contained planning may precede an empty/missing draft.
        # Resolved selected-root confinement belongs only to the fallback.
        if source.get('read_only') or source.get('foreign'):
            raise ValueError('read-only/foreign reader publication is refused.')
        return _change(project, payload, root, actor=actor)


def _change(project, payload, root, *, actor=None):
    """Guard plan and artifact, publish through the existing ART writer, retain provenance."""
    from laplace.manuscript import reader_restructure
    if payload.get('action') in reader_restructure.ACTIONS:
        return reader_restructure.change(project,payload,root,actor=actor)
    from filelock import FileLock
    from laplace.pipeline import registry
    from laplace.manuscript import storyboard
    from laplace.manuscript import bindings
    root = Path(root).resolve()
    record = registry.resolve(project, repo_root=root)
    plan_path = record.plan(root) if record else None
    if plan_path is None or not plan_path.resolve().is_relative_to(root):
        raise ValueError('A writable declared reader plan is required.')
    sid, operation = payload['section_id'], payload['operation']
    with FileLock(str(plan_path) + '.structure.lock'), FileLock(str(plan_path) + '.publication.lock'):
        snapshot = bindings.reader_snapshot(project, root)
        from laplace.core import identity_doors
        identity_doors.gate('structure_change ' + operation, supplied=payload,
            homes=[('plan-file', project, snapshot['authority']['plan_revision'])], required=['expected_plan_revision'],
            said='CHANGED_INPUT: reader plan changed; inspect the selected item before revising.')
        section = next((row for row in snapshot['sections'] if row['id'] == sid), None)
        if section is None:
            raise ValueError('Reader-state section is absent from the current plan.')
        cp, np = _paths(project, root, sid)
        path = cp if operation == 'section_contract' else np
        document, before = _json(path)
        guard = 'expected_contract_revision' if operation == 'section_contract' else 'expected_narrative_revision'
        if payload[guard] != raw_revision(before):
            raise ValueError('CHANGED_INPUT: authored reader state changed; inspect this exact subject.')
        rel = path.relative_to(root).as_posix()
        view = section_view(project, root, section, snapshot['sections'], snapshot['authority']['plan_revision'])
        reserved, subjects = [], {}
        if operation == 'section_contract':
            document = copy.deepcopy(document or {'project': project, 'sections': {}})
            rows = _contracts(document)
            old = _subject(rows, 'section_id', sid)
            prior_subject = copy.deepcopy(old)
            updated = {**(old or {'section_id': sid, 'title': section.get('title', ''),
                       'nodes_in_order': section.get('node_ids', [])}), **payload['changes']}
            document['sections'][sid] = updated
            subject_id = sid
        else:
            document = copy.deepcopy(document or {'section_id': sid, 'paragraphs': []})
            rows = _paragraphs(document, sid)
            ids = [row.get('paragraph_id') for row in rows]
            if view['paragraph_plan']['identity_status'] != 'STABLE':
                raise ValueError('Legacy missing or duplicate paragraph IDs need explicit reconciliation before mutation.')
            action = payload['action']
            subject_id = payload.get('paragraph_id') or '@order'
            if action == 'reorder':
                prior_subject = list(ids)
                order = payload.get('order')
                if not isinstance(order, list) or len(order) != len(ids) or set(order) != set(ids):
                    raise ValueError('Paragraph reorder requires the complete exact current ID permutation.')
                by_id = {row['paragraph_id']: row for row in rows}
                document['paragraphs'] = [by_id[ident] for ident in order]
                updated = order
            elif action in {'upsert', 'remove'}:
                old = _subject(rows, 'paragraph_id', subject_id)
                prior_subject = copy.deepcopy(old)
                if action == 'remove':
                    if old is None:
                        raise ValueError('The exact paragraph to remove is absent.')
                    rows.remove(old)
                    updated = None
                else:
                    if payload.get('create'):
                        offered = view['paragraph_plan']['create_action']['payload']['paragraph_id']
                        if subject_id != offered or old is not None:
                            raise ValueError('Use the current owner-issued unused paragraph identity.')
                        reserved = [subject_id]
                    elif old is None:
                        raise ValueError('Paragraph is absent; creation requires the owner-issued create action.')
                    updated = {**(old or {'section_id': sid, 'paragraph_id': subject_id}), **payload.get('changes', {})}
                    if old is None:
                        rows.append(updated)
                    else:
                        rows[rows.index(old)] = updated
            else:
                raise ValueError('Unknown paragraph-plan action.')
        original_basis = payload['expected_reader_basis']
        if (original_basis.get('project') != project or original_basis.get('path') != rel
                or original_basis.get('section_id') != sid or original_basis.get('subject_id') != subject_id
                or original_basis.get('subject_revision') != fingerprint(prior_subject)):
            raise ValueError('CHANGED_INPUT: reader action does not carry the original exact authored subject basis.')
        intended = (json.dumps(document, ensure_ascii=False, indent=2) + '\n').encode()
        if intended == before or document == (json.loads(before) if before else None):
            unchanged = {'operation': operation, 'section_id': sid, 'paragraph_id': payload.get('paragraph_id'),
                'changed': False, 'consumed_revision': raw_revision(before), 'revision': raw_revision(before),
                'plan_publication': storyboard.reader_publication(('reader-contract' if operation == 'section_contract' else 'paragraph-plan'), 'UNCHANGED', True, 0),
                'read_handle': read_handle(project, sid)}
            if not payload.get('input_observations'):
                return unchanged          # nothing authored and nothing explicitly inspected: a proved no-op
            contracts = _contracts(document) if operation == 'section_contract' else _contracts(_json(cp)[0])
            inputs, _ = _inputs(project, root, section, snapshot['sections'], updated if isinstance(updated, dict) else {},
                contracts, view['reader_inputs']['architecture_prior'], paragraph=operation == 'paragraph_plan',
                cache={'paragraph_rows': document.get('paragraphs', [])})
            # G1-R1: the action's expected input basis is the owner's observation at read time. An
            # acknowledgement is admitted only against the SAME current facts: a stale, altered, missing or
            # extra expected identity refuses here, before observation keys, idempotency or any append.
            expected_inputs = original_basis['inputs']
            drift = sorted(key for key in set(expected_inputs) | set(inputs) if expected_inputs.get(key) != inputs.get(key))
            if drift:
                raise ValueError('CHANGED_INPUT: expected_reader_basis.inputs is not the current input observation; read '
                                 'structure ' + json.dumps(read_handle(project, sid)['payload']) + ' and acknowledge against '
                                 'its fresh edit action reader_basis. Differing inputs: ' + ', '.join(drift[:8]))
            return {**unchanged, **_observe_inputs(root, project, rel, sid, subject_id, prior_subject, inputs,
                payload['input_observations'], operation=operation, consumed=raw_revision(before), actor=actor)}
        contracts = _contracts(document) if operation == 'section_contract' else _contracts(_json(cp)[0])
        inputs, _ = _inputs(project, root, section, snapshot['sections'], updated if isinstance(updated, dict) else {},
            contracts, view['reader_inputs']['architecture_prior'], paragraph=operation == 'paragraph_plan',
            cache={'paragraph_rows': document.get('paragraphs', [])})
        observed_inputs = {**payload.get('input_observations', {}), **original_basis['inputs']}
        unobserved = sorted(set(key for key in inputs if key not in observed_inputs) | set(inputs.unobserved_inputs))
        consumed_inputs = {key: observed_inputs.get(key, fingerprint({'unobserved': key})) for key in inputs}
        subjects[subject_id] = _basis(project, rel, subject_id, updated, consumed_inputs, sid)
        subjects[subject_id]['unobserved_inputs'] = unobserved
        metadata = {'path': rel, 'subjects': subjects, 'reserved_ids': reserved}
        coordinate = _artifact_coordinate(project, root, path, writable=True)
        request = {**coordinate, 'content': intended.decode(),
                   'reason': 'Authored reader-state change',
                   **({'expected_revision': raw_revision(before).removeprefix('sha256:')} if before is not None else {'before': None})}
        saved = None
        publication_witness = {}
        try:
            saved = artifacts.store(root, project, request, owner_metadata=metadata, publication_witness=publication_witness)
            from laplace.writing import records as writing_records
            writing_records.bank(root, {'record': 'writing-reader-publication', 'id': 'RPUB-' + uuid.uuid4().hex,
                'project': project, 'artifact_id': saved['id'], 'reader_metadata': metadata})
        except Exception as exc:
            if not publication_witness.get("banked"):
                raise
            observed = path.read_bytes() if path.is_file() else None
            state = 'COMMITTED' if observed == intended else 'COMPENSATED' if observed == before else 'UNPROVED'
            failure = storyboard.PlanPublicationFailure('Reader metadata publication did not complete; inspect retained state before any new write.',
                project, storyboard.reader_publication(('reader-contract' if operation == 'section_contract' else 'paragraph-plan'), state, False, 1))
            failure.details.update(next_reads=[read_handle(project, sid)], operation=operation, section_id=sid,
                consumed_revision=raw_revision(before), revision=raw_revision(observed),
                artifact_record_id=publication_witness.get('record_id'),
                recovery='Inspect this authored reader subject. Do not repeat a committed or unproved artifact publication.')
            raise failure from exc
        saved.pop('update_handle', None)
        return {**saved, 'operation': operation, 'section_id': sid, 'paragraph_id': payload.get('paragraph_id'),
            'changed': True, 'consumed_revision': raw_revision(before), 'revision': raw_revision(intended),
            'subject_revision': subjects[subject_id]['subject_revision'], 'reader_basis': subjects[subject_id],
            'input_currentness': {**standing_projection(subjects[subject_id], _basis(project, rel, subject_id, updated, inputs, sid)),
                'reads': [read_handle(project, sid)]},
            'plan_publication': storyboard.reader_publication(('reader-contract' if operation == 'section_contract' else 'paragraph-plan'), 'COMMITTED', True, 1),
            'read_handle': read_handle(project, sid), 'effects': ['structure', 'reader-state']}


def _observe_inputs(root, project, rel, sid, subject_id, subject, inputs, observations, *, operation, consumed, actor=None):
    """THE OBSERVATION-ONLY ACKNOWLEDGEMENT (G1, 2026-10-15). The authored subject is unchanged and its exact
    guards already held; the caller names the inputs it inspected, each with the pin the owner observes NOW.
    Unknown keys or pins that are not the current observation refuse before any append. Only the named keys
    are renewed in the recorded basis; unacknowledged pins, unobserved inputs and a changed authored-subject
    flag are kept. One bounded writing-reader-publication row (no artifact body, no ART/source mutation) is
    the durable receipt; an identical recorded observation appends nothing. Observation standing is not
    content change, accepted review, scientific support or reader comprehension."""
    from laplace.manuscript import storyboard
    owner = 'reader-contract' if operation == 'section_contract' else 'paragraph-plan'
    unknown = sorted(set(observations) - set(inputs))
    if unknown:
        raise ValueError('CHANGED_INPUT: input_observations names inputs this subject does not consume: ' + ', '.join(unknown[:8]))
    unavailable = sorted(set(observations) & set(inputs.unobserved_inputs))
    if unavailable:
        raise ValueError('INPUT_UNRESOLVED: observation cannot qualify unavailable inputs: ' + ', '.join(unavailable[:8]))
    moved = sorted(key for key, pin in observations.items() if pin != inputs[key])
    if moved:
        raise ValueError('CHANGED_INPUT: these inputs are not at the inspected pin; re-read the subject: ' + ', '.join(moved[:8]))
    recorded = records.index(root).reader_subjects.get((project, rel, subject_id))
    prior = copy.deepcopy(recorded) if recorded else {**_basis(project, rel, subject_id, subject, {}, sid), 'unobserved_inputs': list(inputs)}
    renewed = {**prior, 'inputs': {**prior.get('inputs', {}), **observations},
               'unobserved_inputs': [key for key in prior.get('unobserved_inputs', []) if key not in observations]}
    renewed['unobserved_inputs'] += [key for key in inputs if key not in renewed['inputs'] and key not in renewed['unobserved_inputs']]
    acknowledged = sorted(observations)
    current = _basis(project, rel, subject_id, subject, inputs, sid)
    def outcome(disposition, receipt=None, appends=0):
        return {'content_changed': False,
                'observation': {'disposition': disposition, 'acknowledged_inputs': acknowledged, 'receipt': receipt,
                                'scope': 'Scoped input observation only; not content change, accepted review or reader comprehension.'},
                'observation_publication': storyboard.reader_publication(owner, 'COMMITTED' if appends else 'UNCHANGED', True, appends),
                'reader_basis': renewed,
                'input_currentness': {**standing_projection(renewed, current), 'reads': [read_handle(project, sid)]}}
    if recorded == renewed:
        return outcome('ALREADY_RECORDED')
    ident = 'RPUB-' + uuid.uuid4().hex
    metadata = {'path': rel, 'subjects': {subject_id: renewed}, 'reserved_ids': [],
                'observation': {'kind': 'reader-input-observation', 'operation': operation, 'section_id': sid,
                                'subject_id': subject_id, 'acknowledged_inputs': acknowledged, 'artifact_revision': consumed,
                                **({'actor': {key: actor[key] for key in ('kind', 'turn_id', 'mode') if key in actor}}
                                   if isinstance(actor, dict) else {})}}
    from laplace.writing import records as writing_records
    try:
        writing_records.bank(root, {'record': 'writing-reader-publication', 'id': ident, 'project': project, 'reader_metadata': metadata})
    except Exception as exc:
        observed = records.index(root).reader_subjects.get((project, rel, subject_id))
        failure = storyboard.PlanPublicationFailure('Reader input observation did not complete; inspect the subject before any new write.',
            project, storyboard.reader_publication(owner, 'COMMITTED' if observed == renewed else 'UNPROVED', False, 1))
        failure.details.update(next_reads=[read_handle(project, sid)], operation=operation, section_id=sid, observation_record_id=ident,
            recovery='Read this subject. Do not repeat an observation that may already be recorded.')
        raise failure from exc
    return outcome('RECORDED', ident, 1)


def basis_schema():
    pin = {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$',
           'examples': ['sha256:' + '0' * 64],
           'description': 'Copy the owner-observed pin; an example hash illustrates shape only and grants no authority.'}
    return {'type': 'object', 'additionalProperties': False,
        'required': ['schema_version', 'project', 'path', 'section_id', 'subject_id', 'subject_revision', 'inputs'],
        'properties': {'schema_version': {'const': 'laplace.reader-basis/1'},
            **{key: {'type': 'string', 'minLength': 1} for key in ('project', 'path', 'section_id', 'subject_id')},
            'subject_revision': pin, 'inputs': {'type': 'object', 'maxProperties': 250, 'additionalProperties': pin},
            'unobserved_inputs': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 250}}}


SUBJECTS_REF_SCHEMA = 'laplace.reader-subjects-ref/1'


def _subject_tuple(basis):
    return [basis['subject_id'], basis['subject_revision'], fingerprint(basis.get('inputs') or {}), sorted(basis.get('unobserved_inputs') or [])]


def subjects_ref(bases):
    """THE COMPACT SUBJECT OBSERVATION (ACTUAL-C6-DETAIL-BYTES, 2026-10-14): one section's displayed
    reader subjects as one ref: the subject ids in display order and one digest over every
    subject's (id, revision, digest of its effective inputs, unobserved inputs). Whole bases carry
    one pin per member per subject (about 2.3 KB a subject on a 17-member chapter, 16 KB for a
    display page); the ref is about 400 B. A send guarded by the ref refuses exactly when a send
    guarded by the whole bases would: the owner re-observes every named subject and compares the
    digest. Nothing is minted: the digest is over the pins the owner itself observed."""
    bases = [basis for basis in bases if isinstance(basis, dict) and basis.get('inputs') is not None]
    if not bases:
        return None
    section_ids = sorted({basis['section_id'] for basis in bases})
    if len(section_ids) != 1:
        raise ValueError('A reader-subjects ref covers one section.')
    return {'schema_version': SUBJECTS_REF_SCHEMA, 'project': bases[0]['project'], 'section_id': section_ids[0],
            'subject_ids': [basis['subject_id'] for basis in bases],
            'digest': fingerprint([_subject_tuple(basis) for basis in bases])}


def subjects_ref_schema():
    pin = {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'}
    return {'type': 'object', 'additionalProperties': False,
            'required': ['schema_version', 'project', 'section_id', 'subject_ids', 'digest'],
            'properties': {'schema_version': {'const': SUBJECTS_REF_SCHEMA},
                           **{key: {'type': 'string', 'minLength': 1} for key in ('project', 'section_id')},
                           'subject_ids': {'type': 'array', 'minItems': 1, 'maxItems': 64, 'items': {'type': 'string', 'minLength': 1}},
                           'digest': pin}}


def subjects_ref_current(project, root, ref, *, cache=None):
    """Re-observe every subject the ref names and compare the digest: True only when every subject's
    revision, effective inputs and unobserved inputs are what the display showed."""
    from jsonschema import Draft202012Validator
    issue = next(Draft202012Validator(subjects_ref_schema()).iter_errors(ref), None)
    if issue or ref.get('project') != project:
        raise ValueError('Reader subjects ref is malformed or belongs to another project.')
    sid = ref['section_id']
    cp, np = _paths(project, Path(root).resolve(), sid)
    root_path = Path(root).resolve()
    contract_path, narrative_path = cp.relative_to(root_path).as_posix(), np.relative_to(root_path).as_posix()
    observed = []
    for ident in ref['subject_ids']:
        probe = {'schema_version': 'laplace.reader-basis/1', 'project': project, 'path': contract_path if ident == sid else narrative_path,
                 'section_id': sid, 'subject_id': ident, 'subject_revision': 'sha256:' + '0' * 64, 'inputs': {}, 'unobserved_inputs': []}
        current = observe_basis(project, root, probe, cache=cache)
        if current.get('unobserved_inputs'):
            return False
        observed.append(_subject_tuple(current))
    return fingerprint(observed) == ref['digest']


def observe_basis(project, root, basis, *, cache=None):
    """Re-observe the exact authored subject and effective inputs, never bless it."""
    from jsonschema import Draft202012Validator
    from laplace.manuscript import bindings
    from laplace.pipeline import registry, schema
    issue = next(Draft202012Validator(basis_schema()).iter_errors(basis), None)
    if issue or basis.get('project') != project:
        raise ValueError('Reader basis is malformed or belongs to another project.')
    root = Path(root).resolve()
    sid, ident = basis['section_id'], basis['subject_id']
    cache = {} if cache is None else cache
    if 'reader_snapshot' not in cache:
        cache['reader_snapshot'] = bindings.reader_snapshot(project, root)
    snapshot = cache['reader_snapshot']
    section = next((row for row in snapshot['sections'] if row['id'] == sid), None)
    if section is None:
        raise ValueError('Reader-basis section no longer exists.')
    if ('paths', sid) not in cache:
        cache[('paths', sid)] = _paths(project, root, sid)
    cp, np = cache[('paths', sid)]
    if ('document', cp) not in cache:
        cache[('document', cp)] = _json(cp)[0]
    contracts = _contracts(cache[('document', cp)])
    contract_path, narrative_path = cp.relative_to(root).as_posix(), np.relative_to(root).as_posix()
    if basis['path'] == contract_path and ident == sid:
        subject, paragraph = _subject(contracts, 'section_id', sid), False
    elif basis['path'] == narrative_path:
        if ('document', np) not in cache:
            cache[('document', np)] = _json(np)[0]
        rows = _paragraphs(cache[('document', np)], sid)
        cache['paragraph_rows'] = rows
        cache.pop('paragraph_positions', None)
        subject = [row.get('paragraph_id') for row in rows] if ident == '@order' else _subject(rows, 'paragraph_id', ident)
        paragraph = True
    else:
        raise ValueError('Reader-basis path does not identify its declared subject.')
    if 'plan_sections' not in cache:
        cache['plan_sections'] = list(schema.plan_sections(registry.resolve(project, repo_root=root).read_plan(root) or {}))
    sections = cache['plan_sections']
    if ('architecture', sid) not in cache:
        cache[('architecture', sid)] = _architecture(section, sections, root)
    architecture = cache[('architecture', sid)]
    inputs, _ = _inputs(project, root, section, sections, subject if isinstance(subject, dict) else {},
        contracts, architecture, paragraph=paragraph, cache=cache)
    return _basis(project, basis['path'], ident, subject, inputs, sid)


def compare_basis(project, root, basis, *, cache=None):
    try:
        current = observe_basis(project, root, basis, cache=cache)
    except (ValueError, OSError) as exc:
        return {'status': 'STALE', 'kind': 'READER_INPUT_CHANGED', 'reason': str(exc),
                'reads': [read_handle(project, basis.get('section_id', ''))]}
    changed = [key for key in set(basis['inputs']) | set(current['inputs'])
               if basis['inputs'].get(key) != current['inputs'].get(key)]
    if basis['subject_revision'] != current['subject_revision']:
        changed.insert(0, 'authored-subject')
    unqualified = sorted(set(basis.get('unobserved_inputs', [])) | set(current.get('unobserved_inputs', [])))
    if unqualified:
        return {'status': 'STALE', 'kind': 'READER_INPUT_UNQUALIFIED',
                'reason': 'Consumed inputs remain unobserved or unavailable.', 'unobserved_inputs': unqualified,
                'changed_inputs': changed, 'reads': [read_handle(project, basis['section_id'])]}
    return {'status': 'STALE' if changed else 'CURRENT', 'kind': 'READER_INPUT_CHANGED' if changed else 'READER_INPUTS_CURRENT',
            'reason': 'Reader subject or consumed inputs changed.' if changed else 'The reviewed subject and consumed inputs still match.',
            'changed_inputs': changed, 'reads': [read_handle(project, basis['section_id'])]}


def review_fields(project, root, basis, section_id, *, cache=None):
    from laplace.work import project_work, project_work_views
    cache = {} if cache is None else cache
    if 'work' not in cache:
        cache['work'] = project_work._tasks(project, root)
    tasks = cache['work']
    rows = [row for row in tasks.values() if row.get('task_kind') == 'reader-review'
            and isinstance(row.get('reader_basis'), dict)
            and (row['reader_basis'].get('path'), row['reader_basis'].get('subject_id')) == (basis['path'], basis['subject_id'])]
    review = {'status': 'NOT_REVIEWED', 'records': []}
    for row in rows[-8:]:
        currentness = project_work._completion_currentness(row, root, tasks=tasks, read_context=cache)
        review['records'].append({'id': row['id'], 'status': row['status'], 'origin': row.get('origin'),
            'currentness': currentness, 'read': project_work_views.handle(project, {'view': 'detail', 'id': row['id']})})
    if rows:
        review['status'] = 'RECORDED'
    action = {'operation': 'task', 'payload': {'title': 'Review reader transition: ' + basis['subject_id'],
        'goal': 'Review the authored transition or paragraph for intelligibility, support and continuity on this exact basis. Record evidence and findings; current inputs alone do not establish acceptance.',
        'kind': 'reader-review', 'section_ids': [section_id], 'reader_basis': basis},
        'http': {'method': 'POST', 'route': '/work/task'}}
    return {'review': review, 'review_action': action}


def source_occurrences(project, root, ids, *, cache=None):
    """A marker witnesses physical location, not an inferred one-to-one origin."""
    from laplace.manuscript.bindings import selected_tree, source_read
    from laplace.manuscript.projection_viewer import parse_paragraphs
    ids = {ident for ident in ids if isinstance(ident, str) and ident}
    if not ids:
        return {}
    cache = {} if cache is None else cache
    if 'source_tree' not in cache:
        cache['source_tree'] = selected_tree(project, root)
    source, tree = cache['source_tree']
    found, parsed = {}, cache.setdefault('paragraph_spans', {})
    for order, item in enumerate(tree.get('sources', [])):
        if item['file'] not in parsed:
            parsed[item['file']] = parse_paragraphs(item.get('text') or '')
        for span in parsed[item['file']]:
            for ident in ids.intersection(span['spec_ids']):
                row = {'file': item['file'], 'source_order': order, 'source_section': span['section'],
                    'line_start': span['start_line'], 'line_end': span['end_line'],
                    'spec_ids': list(span['spec_ids']), 'precision': 'SOURCE_MARKER',
                    'basis': {'selection_identity': source['selection_identity'], 'source_digest': item.get('raw_file_sha256') or 'sha256:' + item['sha256'].removeprefix('sha256:')},
                    'read': source_read(item['file'], {'line': span['start_line'], 'line_end': span['end_line']}, project=project)}
                found.setdefault(ident, []).append(row)
    return found


def lineage(project, root, section_id, paragraph_id, *, cache=None):
    """Inspect retained restructuring decisions without copying their prose bodies."""
    from laplace.pipeline import document_model, registry, pathsafe
    logical_meta=records.index(root).reader_logical_lineage.get((project,section_id,paragraph_id))
    if logical_meta:
        from laplace.manuscript.reader_logical_publication import lineage_read
        return {'status':'RECORDED','items':[{'kind':'paragraph-restructure',**copy.deepcopy(logical_meta),
            'semantic_currentness':'NOT_REVIEWED','read':lineage_read(project,section_id,logical_meta,root)}]}
    record = registry.resolve(project, repo_root=root)
    directory = record.stage_path('decisions', root)
    path = (directory / (pathsafe.encode_sid_for_path(section_id) + '.json')) if directory else None
    if path is None or not path.is_file():
        return {'status': 'NOT_RECORDED', 'items': []}
    if path.stat().st_size > MAX_BYTES:
        return {'status': 'UNAVAILABLE', 'items': [], 'reason': 'Retained decision artifact exceeds bounded read.'}
    cache = {} if cache is None else cache
    key = ('decisions', section_id)
    if key not in cache:
        cache[key] = (document_model.load_decisions(project, section_id, root) or [], raw_revision(path.read_bytes()))
    decisions, decision_revision = cache[key]
    chosen = [row for row in decisions if paragraph_id in document_model._record_spec_ids(row)]
    try:
        coordinate = _artifact_coordinate(project, root, path)
    except (ValueError, OSError) as error:
        return {'status': 'UNAVAILABLE', 'items': [], 'reason': str(error)}
    read = {'operation': 'read_artifact', 'payload': coordinate,
            'http': artifacts.human_read(project, coordinate['path'], coordinate['scope'], decision_revision)['http']}
    def projection(row):
        result={key:row.get(key) for key in ('kind','spec_id','spec_ids','rationale')}
        if row.get('owner')=='reader-restructure':
            meta=records.index(root).reader_restructure_receipts.get((project,row.get('intent_artifact_id')))
            outcome=(meta or {}).get('reader_metadata',{}).get('restructure') or {}
            result.update(state='COMPLETE' if outcome.get('complete') else 'SOURCE_COMMITTED' if outcome.get('source_effect',{}).get('state')=='COMMITTED' else 'INTENT',
                intent_artifact_id=row.get('intent_artifact_id'),receipt_id=(outcome.get('receipt') or {}).get('id'))
        return result
    return {'status': 'RECORDED', 'items': [projection(row) for row in chosen[:20]],
            'omitted': max(0, len(chosen) - 20), 'read': read}


def input_diagnostics(subject, links, *, contract=False):
    required = ('function', 'question_answered', 'entry_state', 'exit_state') if contract else ('function', 'proposition')
    missing = [{'kind': 'AUTHORED_FIELD_EMPTY', 'field': key,
                'reason': 'The intended reader transition has not been authored.'} for key in required if not subject.get(key)]
    return missing + [{'kind': 'INPUT_UNRESOLVED', 'subject': row['label'], 'status': row['status'],
        'reason': row.get('reason') or 'Supporting input is missing, ambiguous, or stale; observation is not validation.', 'read': row['read']}
        for row in links if row.get('status') not in {None, 'AVAILABLE', 'CURRENT'}]


def enrich_descriptors(project, section, sections, descriptors, cache):
    """Choices retain actual IDs and display metadata, never labels as authority."""
    nodes = (cache.get('network') or {}).get('nodes') or {}
    from laplace.manuscript.project_structure import _label
    for field in descriptors:
        name = field['name']
        if name in {'depends_on', 'forward_uses'}:
            field['choices'] = [{'value': row['id'], 'label': row.get('title') or row['id'],
                'read': read_handle(project, row['id'])} for row in sections if row['id'] != section['id']][:80]
        elif name == 'input_nodes':
            field['choices'] = [{'value': ident, 'label': _label(nodes[ident], ident),
                'input_key': 'concept:' + ident, 'input_revision': concept_input_revision(nodes, ident, cache.get('network', {})),
                'read': {'operation': 'concept', 'payload': {'node': ident}}}
                for ident in section.get('node_ids', []) if ident in nodes][:80]
        elif name == 'citations':
            field['choices'] = [{'value': key, 'label': key, 'input_key': 'citation:' + key, 'input_revision': fingerprint(cache['bibliography'][key]),
                'read': {'operation': 'references_attached', 'payload': {'citekey': key},
                    'http': {'method': 'GET', 'route': '/references/attached', 'query': {'project': project, 'citekey': key}}}}
                for key in sorted(cache.get('bibliography', {}))][:80]
        elif name in {'figures', 'figure_anchor'}:
            # Choice navigation uses the same list identities without rendering or
            # hashing every unconsumed asset. A chosen ID is qualified by _inputs.
            visual_cache = cache.get('reader_visuals', {})
            catalogue = visual_cache.get('catalogue')
            if catalogue is None:
                catalogue = cache.get('visual_choices', {'specs': [], 'problems': []})
            rows = catalogue['specs']
            ids = [row.get('id') for row in rows if isinstance(row, dict)]
            field['choices'] = [{'value': row['id'], 'label': str(row.get('caption') or row.get('title') or row['id'])[:240],
                'input_key': 'figures:' + row['id'], 'read': {'operation': 'visuals', 'payload': {'id': row['id']}}}
                for row in rows if isinstance(row, dict) and isinstance(row.get('id'), str)
                and ids.count(row['id']) == 1 and not catalogue['problems']][:80]
        elif name in {'equations', 'tables'}:
            available = cache.get('equations', {}) if name == 'equations' else cache.get('spec', {}).get(name, {})
            field['choices'] = [{'value': key, 'input_key': name + ':' + key, 'input_revision': fingerprint(value), 'label': str(value.get('caption') or value.get('title') or key)[:240],
                **({'read': {'operation': 'concept', 'payload': {'node': value['node']}}} if value.get('node') in nodes else {})}
                for key, value in list(available.items())[:80] if isinstance(value, dict)]


def contract():
    return {'owner': 'laplace.manuscript.reader_plan',
        'reads': 'structure view detail section_ids:[exact ID] returns reader_transition, paragraph_plan and reader_inputs. paragraph_id reads an exact logical unit; paragraph_offset/limit/paragraph_as_of follow pinned next_read. projection:guard (laplace.project-structure-guard/1) is the bounded form of the same read, ONE subject per read: subject:contract (default) carries the section_contract edit call with its guards (expected_plan_revision, expected_contract_revision, expected_reader_basis), the section source binding, current authored values, input currentness and a clipped id/proposition row list of the paragraph page with one subject_read per row; subject:paragraph with paragraph_id carries that one unit in full with its edit and remove calls (expected_narrative_revision, expected_reader_basis); subject:create the create call; subject:reorder the reorder call with the complete current order. No members, support, evidence, relations, history or field descriptors (full_read names the plain detail). A guard read names exactly ONE canonical section_ids entry: files, node_id, node_ids and sections are refused for it (resolve them with the plain detail read first; each returned section carries its canonical id), so the bounded subject policy never widens through an alternative selector.',
        'writes': ('Use the returned edit_action with changed typed fields. section_contract and paragraph_plan share structure_change, '
                   'exact original plan-file and artifact guards, ART custody and publication. Raw missing artifact guard is null, '
                   'never an invented digest. A content edit records the input basis its action consumed.'),
        'observation': ('Acknowledge inspected inputs of an UNCHANGED subject: the current edit_action with changes:{} and '
                        'input_observations {input: current pin} for the keys you inspected. Its expected_reader_basis.inputs must '
                        'equal the current observation exactly, else CHANGED_INPUT and nothing is written (re-read). Only named keys '
                        'renew; others keep their standing. One metadata-only writing-reader-publication row (observation_publication; '
                        'no ART, content or order change); an identical repeat is ALREADY_RECORDED. Absent or empty input_observations '
                        'is a no-op. Not review.'),
        'identity': 'paragraph_id is an opaque stable string, not its ordinal or current section. Order is separate. spec_ids maps logical units many-to-many onto physical source occurrences; missing/duplicate legacy identity is unproved and cannot be silently renumbered.',
        'currentness': 'Authored content, scoped effective input observation, diagnostics and recorded Work review are separate. CURRENT inputs never establish valid exposition. A logical prerequisite is not necessarily an earlier reader prerequisite.',
        'review': 'review_action prepares existing reader-review Work carrying exact reader_basis. Existing evidence and role constraints govern completion. Changed subject/support reopens it; disjoint sibling edits do not.',
        'publication': 'plan_publication describes reader metadata, not source bytes. Incomplete or unproved effects suppress replay; exact subject read remains available. ART reservations retain issued paragraph IDs through failed publication/deletion.',
        'restructuring':'B1 presentation changes use structure view:restructure section_ids:[exact declared ID], kind:presentation-split|presentation-join and the exact authored body draft. HTTP preview-restructure is a pure POST read. Returned apply/recovery/inverse actions carry the same nested seven-value guards; native plan-file authority uses the canonical expected token. Copy original draft at apply; source parts are exact UTF-8 READ-backed chunks. COMMITTED source with PARTIAL metadata must settle the saved text and recover only missing steps. Only exact still-current inverse may restore marker mapping; logical split/merge remain unavailable until separately delivered.',
        'discovery': 'Generated change artifact@section and change artifact@paragraph adapt the same existing owners; no second writer or review ledger.'}


def owns_path(project, root, path):
    """Public generic ART stores cannot bypass typed reader identity/plan guards."""
    from laplace.pipeline import registry
    record = registry.resolve(project, repo_root=root)
    if record is None:
        return False
    contracts, narrative = record.stage_path('contracts', root), record.stage_path('narrative', root)
    target = Path(path).resolve()
    decisions=record.stage_path('decisions',root)
    return bool((decisions is not None and target.parent==decisions.resolve() and target.name.endswith('.restructure-intent.json')) or
                (contracts is not None and target == contracts.resolve()) or
                (narrative is not None and target.parent == narrative.resolve() and target.suffix == '.json'))


def concept_input_revision(nodes, ident, network):
    from laplace.manuscript.project_structure import _node_row
    projection = (nodes.get(ident) or {}).get('projection') or {}
    return fingerprint({'object': _node_row(nodes, ident), 'mathematics': projection.get('mathematics'),
        'relations': [row for row in network.get('relations', []) if ident in (row.get('source'), row.get('target'))]})
