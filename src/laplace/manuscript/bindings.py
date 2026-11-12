"""Source occurrences and their reader-plan witnesses, never a second graph.

The selected source owns bytes; storyboard owns authored reader sections; concepts
own scientific meaning. This module joins those existing subjects. project_structure,
proposal_basis, heading follow-through and the native/HTTP outline adapters consume
this assessment. Old correspondence/parser entry points delegate here until their
external callers migrate. No title or generated outline ID becomes logical authority.
"""
from __future__ import annotations

import hashlib
from bisect import bisect_right
from collections import Counter
import json
from pathlib import Path

from laplace.manuscript import manuscript_source
from laplace.core import identity_doors


def digest(raw):
    if isinstance(raw, str):
        raw = raw.encode('utf-8')
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def selected_tree(project, root, *, source=None):
    """Retain exact bytes (including CRLF) while reusing selected include traversal."""
    root = Path(root).resolve()
    source = dict(source or manuscript_source.resolve(project, root, include_candidates=False))
    source['selection_identity'] = manuscript_source.selection_identity(source, project)
    source['project'] = project
    tree = manuscript_source.traversal(source['root'], root) if source.get('root') else {'sources': [], 'files': []}
    # traversal already reads exact bytes once per physical file, preserves CRLF
    # in text and publishes their raw SHA. Reuse that same observed body/pin.
    for row in tree.get('sources', []):
        row['raw_file_sha256'] = 'sha256:' + row['sha256'].removeprefix('sha256:')
    return source, tree


class ParsedHeadings(list):
    """Request-local lookup over one physical parse; never persistent authority."""
    def __init__(self, rows):
        super().__init__(rows)
        self.by_label, self.by_title, self.by_line = {}, {}, {}
        for row in rows:
            self.by_label.setdefault(row.get('label'), []).append(row)
            self.by_title.setdefault(row['title'], []).append(row)
            self.by_line.setdefault(row['line'], []).append(row)


def display_title(title_tex):
    """The human heading title: the reader's own flattening of the title TeX (walk), so inline \\label{...} and
    other non-text commands never reach navigation, and outline and rendered heading titles are the same string."""
    from laplace.manuscript import walk
    return ' '.join(walk._flatten_pieces(walk.tex_pieces(str(title_tex or ''))).split())


def headings(text):
    """Balanced headings, exact command bytes and file-local enclosing spans."""
    from laplace.manuscript import manuscript_structure
    rows = manuscript_structure._heading_rows(text)
    levels = manuscript_structure._STRUCTURE_LEVEL
    line_starts = [0] + [index + 1 for index, char in enumerate(text) if char == '\n']
    stack = []
    for row in rows:
        level = levels[row['kind']]
        while stack and stack[-1]['level'] >= level:
            previous = stack.pop()
            previous['line_end'] = bisect_right(line_starts, max(previous['start'], row['start'] - 1))
        row.update(level=level, heading_before=text[row['start']:row['end']],
                   heading_line_end=bisect_right(line_starts, row['end']),
                   parent_line=stack[-1]['line'] if stack else None,
                   display_title=display_title(row['title']))
        stack.append(row)
    for row in stack:
        row['line_end'] = bisect_right(line_starts, max(row['start'], len(text) - 1))
    return ParsedHeadings(rows)


def source_read(file, heading=None, *, project=''):
    payload = {'files': [file]}
    if heading:
        payload.update(line_start=heading['line'], line_end=heading['line_end'])
    return {'operation': 'source', 'payload': payload,
            **({'http': {'method': 'GET', 'route': '/projection/tex',
                        'query': {'corpus': project, 'file': file, 'view': 'source'}}} if project else {})}


def outline_rows(source, tree, *, files=None, parsed=None):
    rows = []
    wanted = set(files or [])
    counts = Counter(item["file"] for item in tree.get("sources", []))
    parsed = parsed if parsed is not None else {}
    from laplace.manuscript.manuscript_structure import _execution_prefixes
    prefixes = _execution_prefixes(tree)
    for order, item in enumerate(tree.get('sources', [])):
        file, text = item['file'], str(item.get('text') or '')
        if wanted and file not in wanted:
            continue
        if file not in parsed:
            parsed[file] = headings(text)
        for heading in parsed[file]:
            row = {key: heading.get(key) for key in (
                'line', 'line_end', 'heading_line_end', 'kind', 'title', 'display_title', 'label', 'labels',
                'level', 'parent_line', 'heading_before')}
            row.update(file=file, parent_file=file if row['parent_line'] else None,
                       source_order=order, include_parent=item.get('parent'),
                       include_line=item.get('include_line'),
                       basis={'selection_identity': source.get('selection_identity'),
                              'source_digest': item.get('raw_file_sha256') or digest(text)},
                       source_read=source_read(file, heading, project=source.get('project', '')),
                       shared_occurrences=counts[file],
                       structure_read={'operation': 'structure', 'payload': {
                           'view': 'detail', 'files': [file], 'line_start': heading['line'],
                           'line_end': heading['line_end']},
                           'http': {'method': 'GET', 'route': '/work/structure', 'query': {
                               'project': source.get('project'), 'view': 'detail', 'files': [file],
                               'line_start': heading['line'], 'line_end': heading['line_end']}}})
            row["_position"] = prefixes[order] + (heading["start"],)
            rows.append(row)
    rows.sort(key=lambda row: row["_position"])
    for row in rows:
        row.pop("_position")
    return rows


def _declared_files(source, tree, declared):
    files = list(dict.fromkeys(str(row['file']) for row in tree.get('sources', [])))
    if not declared:
        return files
    # Only exact repository or manuscript-relative spellings. Suffix coincidence
    # can never establish membership in another directory.
    relative = str(Path(str(source.get('manuscript_dir') or '')) / declared)
    return [file for file in files if file == declared or file == relative]


def correspondence(source, tree, section, *, heading_rows_by_file=None):
    """One witness; file-only and inferred candidates are not exact passages."""
    from laplace.manuscript import proposal_preflight
    declared_file = str(section.get('source_file') or '')
    label = str(section.get('source_label') or '')
    files = _declared_files(source, tree, declared_file)
    source_title = str(section.get('source_title', section.get('title') or '')).strip()
    candidates, basis = [], {}
    anchor = section.get('source_anchor')
    for order, item in enumerate(tree.get('sources', [])):
        file, text = str(item['file']), str(item.get('text') or '')
        if file not in files:
            continue
        basis[file] = {'selection_identity': source.get('selection_identity'),
                       'source_digest': item.get('raw_file_sha256') or digest(text)}
        observed = (heading_rows_by_file or {}).get(file)
        if observed is None or any("line_end" not in row for row in observed):
            observed = headings(text)
            if isinstance(heading_rows_by_file, dict):
                heading_rows_by_file[file] = observed
        proven = None
        if anchor and section.get('source_heading'):
            proven = proposal_preflight.proven_current_span(text, {
                'before': section['source_heading'], 'source_anchor': anchor})
        if not isinstance(observed, ParsedHeadings):
            observed = ParsedHeadings(observed)
            if isinstance(heading_rows_by_file, dict):
                heading_rows_by_file[file] = observed
        possible = (observed.by_label.get(label, []) if label else
                    observed.by_line.get(proven[0], []) if proven else
                    observed.by_title.get(source_title, []) if not anchor else [])
        for heading in possible:
            exact = heading.get('label') == label if label else bool(
                proven and heading['line'] == proven[0]
                and heading['heading_line_end'] == proven[1])
            inferred = not label and not anchor and heading['title'] == source_title
            if exact or inferred:
                candidates.append({**heading, 'file': file, 'source_order': order})
    # Repeated inclusion shares one physical source occurrence; it does not
    # create an arbitrary first include as binding authority.
    physical = {}
    for row in candidates:
        key = (row['file'], row['start'], row['end'])
        value = physical.setdefault(key, {**row, 'source_orders': []})
        value['source_orders'].append(row['source_order'])
    candidates = list(physical.values())
    for row in candidates:
        if len(row['source_orders']) > 1:
            row['source_order'] = None
    exact_declared = bool(label or anchor)
    unique = candidates[0] if len(candidates) == 1 else None
    if len(candidates) > 1:
        precision, status = 'AMBIGUOUS', 'AMBIGUOUS'
    elif unique and exact_declared:
        precision, status = 'EXACT_HEADING', 'MATCHED'
    elif declared_file and files and not exact_declared:
        precision, status = 'FILE_ONLY', 'MATCHED'
    elif unique and not exact_declared:
        precision, status = 'INFERRED', 'MATCHED'
        files = [unique['file']]
    else:
        precision, status = 'UNRESOLVED', 'UNRESOLVED'
        if not declared_file:
            files = []
    independent = (section.get('source_plan_title') is not None
                   and section.get('title') != section['source_plan_title'])
    exact_heading = unique if precision == 'EXACT_HEADING' else None
    heading = ({key: unique.get(key) for key in (
        'file', 'line', 'line_end', 'heading_line_end', 'title', 'kind', 'label',
        'heading_before', 'source_order', 'source_orders')} if unique else None)
    return {'section_id': section.get('id'), 'source_files': files, 'status': status,
            'precision': precision, 'title_status': (
                'UNAVAILABLE' if not unique else 'INDEPENDENT' if independent else
                'MATCHED' if source_title == unique['title'] else 'MISMATCH'),
            'plan_title': section.get('title'), 'source_titles': list(dict.fromkeys(
                row['title'] for row in candidates)), 'source_label': label or None,
            'heading': heading, 'basis': {file: basis[file] for file in files if file in basis},
            'mapping': ('explicit-source-label' if label else 'explicit-source-anchor' if anchor
                        else 'explicit-source-file' if declared_file else 'legacy-title-or-stem'),
            'selected_root': source.get('root'),
            'source_reads': [source_read(file, exact_heading, project=source.get('project', '')) for file in files],
            'clearing_read': {'operation': 'structure', 'payload': {'view': 'outline'}}}


def sections_for_span(structure, file, lo, hi, *, require_exact=True):
    """Select witnessed enclosing/overlapping sections without re-matching titles."""
    selected, limitations = [], []
    source = structure.get('selected_source') or {}
    normalized = str(Path(str(source.get('manuscript_dir') or '')) / file)
    for section in structure.get('sections') or []:
        witness = section.get('source') or {}
        if not any(value in {file, normalized} for value in witness.get('source_files', [])):
            continue
        heading = witness.get('heading')
        if witness.get('precision') != 'EXACT_HEADING' or not heading:
            limitations.append('Section %s has %s source correspondence; inspect and bind an exact occurrence.'
                               % (section.get('id'), witness.get('precision', 'UNRESOLVED')))
            continue
        if heading['line'] <= hi and lo <= heading['line_end']:
            selected.append(section)
    covered = [row for row in selected if lo <= row['source']['heading']['line']
               and hi >= row['source']['heading']['line_end']]
    if covered:
        return covered, list(dict.fromkeys(limitations))
    enclosing = [row for row in selected if row['source']['heading']['line'] <= lo
                 and hi <= row['source']['heading']['line_end']]
    if enclosing:
        start = max(row['source']['heading']['line'] for row in enclosing)
        selected = [row for row in enclosing if row['source']['heading']['line'] == start]
    return selected, list(dict.fromkeys(limitations))


#: The outline LIST row (G18b): what a reader needs to show a heading, place it in source order
#: and address it. The per-file raw byte basis and the owner's read handles are stated ONCE on
#: the outline (`sources`, `read_routes`) instead of once per row: 80 rows cost 149,091 B
#: with a 1.8 KB row carrying its own basis, source read and structure read; the trimmed row
#: is title, kind, file, span, label, the heading's exact first line (the `bind_source` guard),
#: its source order and its share count. `outline_rows` keeps the complete row for the state's
#: own `source_outline` and for correspondence; only this view trims. M5 (2026-10-16): `title` stays the exact source
#: title (plan matching, bind guards); `display_title` is what navigation shows, so an inline \label never leaks.
OUTLINE_ROW_FIELDS = ('title', 'display_title', 'kind', 'file', 'line', 'line_end', 'heading_line_end', 'label',
                      'heading_before', 'source_order', 'shared_occurrences')


def outline_read_routes(project):
    """The owner's read handles for ANY heading of this outline, as templates.

    `<file>`, `<line>` and `<line_end>` are filled from a row by the consumer
    (`workspace-spine.outlineOccurrence`); the handle shape is the owner's, not guessed."""
    return {'source_read': source_read('<file>', {'line': '<line>', 'line_end': '<line_end>'}, project=project),
            'structure_read': {'operation': 'structure', 'payload': {
                'view': 'detail', 'files': ['<file>'], 'line_start': '<line>', 'line_end': '<line_end>'},
                'http': {'method': 'GET', 'route': '/work/structure', 'query': {
                    'project': project, 'view': 'detail', 'files': ['<file>'],
                    'line_start': '<line>', 'line_end': '<line_end>'}}}}


def outline(project, root, *, files=None, offset=0, limit=80, as_of=''):
    """The selected source's heading outline: trimmed rows, one basis per file, owner read routes."""
    source, tree = selected_tree(project, root)
    cut = digest(json.dumps({'selection': source['selection_identity'],
        'files': {row['file']: row.get('raw_file_sha256') for row in tree.get('sources', [])}}, sort_keys=True))
    if as_of and as_of != cut:
        raise ValueError('CHANGED_INPUT: selected source outline changed; read the current outline.')
    wanted = set(files or [])
    if wanted - set(tree.get('files', [])):
        raise ValueError('Outline files must belong to the exact selected source traversal.')
    rows = [{key: row.get(key) for key in OUTLINE_ROW_FIELDS} for row in outline_rows(source, tree, files=wanted)]
    offset, limit = max(0, int(offset)), max(1, min(200, int(limit)))
    page = {'items': rows[offset:offset + limit], 'total': len(rows), 'offset': offset,
            'limit': limit, 'omitted_before': min(offset, len(rows)),
            'omitted_after': max(0, len(rows) - offset - limit)}
    # the raw byte basis of each file THIS PAGE's rows live in, once (journey H budget)
    on_page = {str(row['file']) for row in page['items']}
    sources = {}
    for item in tree.get('sources', []):
        file = str(item['file'])
        if file in on_page and file not in sources:
            sources[file] = {'source_digest': item.get('raw_file_sha256') or digest(str(item.get('text') or ''))}
    if page['omitted_after']:
        page['next_read'] = {'operation': 'structure', 'payload': {
            'view': 'outline', 'files': sorted(wanted), 'offset': offset + limit,
            'limit': limit, 'as_of': cut}}
    return {'schema_version': 'laplace.source-outline/2', 'project': project,
            'status': 'AVAILABLE' if source.get('root') else 'UNAVAILABLE',
            'selected_source': {key: source.get(key) for key in (
                'root', 'manuscript_dir', 'edition', 'status', 'read_only', 'selection_identity')},
            'as_of': cut, 'headings': page,
            # the raw byte basis of every included file, once; a row's basis is
            # selected_source.selection_identity plus sources[row.file].source_digest
            'sources': sources,
            'read_routes': outline_read_routes(source.get('project', '')),
            'diagnostics': tree.get('diagnostics', [])}


def clearing_action(project, section_id, plan_revision):
    if not plan_revision:
        return None
    return {'operation': 'structure_change', 'payload': {
                'operation': 'bind_source', 'section_id': section_id,
                'expected_plan_revision': plan_revision},
            'http': {'method': 'POST', 'route': '/work/structure/change'},
            'choose_from': {'operation': 'structure', 'payload': {'view': 'outline'},
                'http': {'method': 'GET', 'route': '/work/structure',
                         'query': {'project': project, 'view': 'outline'}}},
            'required_occurrence_fields': ['file', 'line', 'heading_before',
                                          'expected_selection', 'expected_source_digest']}


def reader_snapshot(project, root, *, scope=None, window=None):
    """Current reader-plan metadata before scientific/support hydration.

    The full plan is the existing authored object. Only requested sections receive
    source witnesses; this read never folds author history or loads scientific
    bodies merely to show the reader order. Full legacy state remains explicit.
    """
    from laplace.pipeline import registry, schema
    root = Path(root).resolve()
    source, tree = selected_tree(project, root)
    record = registry.resolve(project, repo_root=root)
    path = record.plan(root) if record and record.plan_path else None
    raw = path.read_bytes() if path and path.is_file() else None
    plan = json.loads(raw) if raw else {}
    plan_revision = digest(raw) if raw is not None else None
    scope = scope or {}
    wanted_ids = set(scope.get('section_ids') or [])
    wanted_files = {file for supplied in scope.get('files', [])
                    for file in _declared_files(source, tree, str(supplied))}
    wanted_nodes = set(scope.get('node_ids') or []) | ({scope['node_id']} if scope.get('node_id') else set())
    raw_sections = list(schema.plan_sections(plan))
    collection_of = {row["id"]: name for name in ("sections", "appendices") for row in plan.get(name, [])}
    scoped = bool(wanted_ids or scope.get('files') or wanted_nodes)
    candidates = [row for row in raw_sections if not scoped
        or row['id'] in wanted_ids
        or bool(wanted_files and set(_declared_files(source, tree, str(row.get('source_file') or ''))) & wanted_files)
        or bool(set(schema.section_nodes(row) + list(row.get('beats') or [])) & wanted_nodes)]
    selected = {row['id'] for row in (candidates[window[0]:window[0] + window[1]] if window else candidates)}
    parsed, sections, ids = {}, [], set()
    for order, item in enumerate(raw_sections):
        nodes, beats = schema.section_nodes(item), list(item.get('beats') or [])
        ids.update(nodes + beats)
        row = {key: item.get(key) for key in ('id', 'title', 'kind', 'parent_id', 'depth',
                                            'number', 'ancestor_ids', 'child_ids', 'job', 'notes')}
        row.update(collection=collection_of.get(item["id"]), order=order, node_ids=nodes, beat_ids=beats, nodes=[], beats=[], evidence=[])
        row['source'] = (correspondence(source, tree, item, heading_rows_by_file=parsed)
                         if item['id'] in selected else {'precision': 'NOT_ASSESSED', 'source_files': []})
        row['clearing_action'] = clearing_action(project, item['id'], plan_revision)
        from laplace.writing.prepared_work import action as prepare_action
        row['prepare_action'] = prepare_action(project,plan_revision,source['selection_identity'],[item['id']])
        sections.append(row)
    spine, spine_revision = spine_snapshot(project, root, plan=plan)
    authority = {'spine_revision': spine_revision, 'plan_path': path.relative_to(root).as_posix() if path else None,
                 'plan_revision': plan_revision, 'conceptric_revision': None,
                 'source_revision': source.get('revision')}
    revision = digest(json.dumps({'plan': plan_revision, 'spine': spine_revision, 'selection': source['selection_identity'],
        'source_files': {item['file']: item.get('raw_file_sha256') for item in tree.get('sources', [])}}, sort_keys=True))
    return {'project': project, 'status': 'CURRENT' if raw_sections else 'MISSING',
            'availability': {'reader_plan': 'AVAILABLE' if raw_sections else 'MISSING'},
            'revision': revision, 'authority': authority, 'selected_source': source,
            'identities': identity_doors.identities(
                ('plan-file', project, plan_revision)),
            'sections': sections, 'spine': spine, 'nodes': [], 'edges': [], 'evidence': [], 'gaps': [],
            'logical_objects': [{'id': ident, 'label': ident, 'label_basis': 'address',
                                 'status': 'NOT_ASSESSED', 'placed': True} for ident in sorted(ids)],
            'unplaced_nodes': [], 'source_outline': []}


def bind_source(project, payload, root):
    """Bind an inspected physical heading in the existing plan, changing no source.

    Lock order: selected edition, physical source, plan structure/publication.
    Every supplied basis is compared inside that boundary. Repeated includes
    share the same physical heading; they do not pick an arbitrary include.
    """
    from filelock import FileLock
    from laplace.manuscript import storyboard, proposal_preflight
    from laplace.pipeline import registry, schema
    root = Path(root).resolve()
    with manuscript_source.selection_mutation(project, root):
        source = manuscript_source.resolve(project, root, include_candidates=False)
        if payload.get('expected_selection') != manuscript_source.selection_identity(source, project):
            raise ValueError('CHANGED_INPUT: selected source changed; inspect the occurrence again.')
        file = str(payload.get('file') or '')
        path = (root / file).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Source binding escapes the repository.')
        with manuscript_source.source_mutation([path]):
            source, tree = selected_tree(project, root, source=source)
            if file not in tree.get('files', []):
                raise ValueError('Source binding must name an exact selected source file.')
            raw = path.read_bytes()
            if payload.get('expected_source_digest') != digest(raw):
                raise ValueError('CHANGED_INPUT: source bytes changed; inspect the occurrence again.')
            text = raw.decode('utf-8')
            observed_headings = headings(text)
            found = [row for row in observed_headings if row['line'] == payload.get('line')
                     and row['heading_before'] == payload.get('heading_before')]
            if len(found) != 1:
                raise ValueError('The inspected heading is missing or ambiguous; choose an exact occurrence.')
            heading = found[0]
            label = heading.get('label')
            if label and len(observed_headings.by_label.get(label, [])) != 1:
                raise ValueError('The source label is ambiguous in this physical file; repair it or choose an unambiguous occurrence.')
            lo, hi = heading['line'], heading['heading_line_end']
            anchored_text = '\n'.join(text.split('\n')[lo - 1:hi])
            anchor = proposal_preflight.source_anchor(text, lo, hi)
            if not label and not anchor.get('unique'):
                raise ValueError('The unlabelled heading has no unique source anchor; give it a unique label before binding.')
            record = registry.resolve(project, repo_root=root)
            plan_path = record.plan(root) if record and record.plan_path else None
            if plan_path is None or not plan_path.resolve().is_relative_to(root) or not plan_path.is_file():
                raise ValueError('Reader plan is unavailable; initialise the existing plan owner first.')
            with FileLock(str(plan_path) + '.structure.lock', timeout=15):
                plan_bytes = plan_path.read_bytes()
                from laplace.core import identity_doors
                identity_doors.gate('structure_change bind_source', supplied=payload,
                    homes=[('plan-file', project, digest(plan_bytes))],
                    required=['expected_plan_revision'],
                    said='CHANGED_INPUT: reader plan changed; inspect the section again.')
                plan = json.loads(plan_bytes)
                matches = [row for row in schema.plan_sections(plan) if row['id'] == payload.get('section_id')]
                if len(matches) != 1:
                    raise ValueError('Reader-plan section identity is missing or ambiguous.')
                section = matches[0]
                if section is None:
                    raise ValueError('The selected reader-plan section is unavailable.')
                before = correspondence(source, tree, section)
                current_heading = before.get('heading') or {}
                unchanged = (before['precision'] == 'EXACT_HEADING'
                    and current_heading.get('file') == file and current_heading.get('line') == lo)
                if unchanged:
                    result = {'ok': True, 'applied': True, 'changed': False,
                              'plan_publication': storyboard.reader_publication('reader-plan', 'UNCHANGED', True, 0)}
                    binding = before
                else:
                    op = {'kind': 'bind-source', 'section': section['id'],
                          'source_file': file, 'source_label': label,
                          'source_title': heading['title'], 'source_heading': anchored_text,
                          'source_anchor': anchor,
                          'source_plan_title': section.get('source_plan_title', heading['title']),
                          'expected_plan_digest': digest(plan_bytes), 'by': payload.get('by') or 'author:source-binding'}
                    result = storyboard.plan_write_batch(project, [op], root, _source_binding=True)
                    if not result.get('applied'):
                        raise ValueError(result.get('error') or 'Reader-plan binding was refused.')
                    updated = {**section, **{key: value for key, value in op.items() if key.startswith('source_')}}
                    binding = correspondence(source, tree, updated)
    return {'ok': result.get('ok', True), 'operation': 'bind_source',
            'status': result.get('status', 'CURRENT'), 'changed': not unchanged,
            'link_established': binding['precision'] == 'EXACT_HEADING', 'binding': binding,
            'affected': {'identities': [payload['section_id']]},
            'detail_read': {'operation': 'structure', 'payload': {'view': 'detail', 'section_ids': [payload['section_id']]},
                'http': {'method': 'GET', 'route': '/work/structure', 'query': {
                    'project': project, 'view': 'detail', 'section_ids': [payload['section_id']]}}},
            **({'owned_changes': result['owned_changes']} if result.get('owned_changes') else {}),
            **({'plan_publication': result['plan_publication']} if result.get('plan_publication') else {})}


def observation_contract():
    from laplace.manuscript.reader_plan import basis_schema, subjects_ref_schema
    pin = {'type': 'string', 'pattern': '^sha256:[0-9a-f]{64}$'}
    return {'type': 'object', 'additionalProperties': False,
            'required': ['plan_revision', 'selection_identity', 'source_files'],
            'properties': {'plan_revision': {'anyOf': [pin, {'type': 'null'}]},
                'selection_identity': pin, 'spine_revision': pin,
                # a subject travels whole (the detail read) or as its compact ref (the display read); both refuse the same stale send
                'reader_subjects': {'type': 'array', 'maxItems': 64, 'items': {'oneOf': [basis_schema(), subjects_ref_schema()]}}, 'source_files': {'type': 'array', 'maxItems': 16,
                    'items': {'type': 'object', 'additionalProperties': False,
                        'required': ['file', 'source_digest'],
                        'properties': {'file': {'type': 'string', 'minLength': 1}, 'source_digest': pin}}}}}


def validate_observation(project, root, value):
    """Validate shown context as observation, never turn it into write authority."""
    from jsonschema import Draft202012Validator
    from laplace.pipeline import registry
    issue = next(Draft202012Validator(observation_contract()).iter_errors(value), None)
    if issue:
        raise ValueError('workspace_context.structure_observation: ' + issue.message)
    source, tree = selected_tree(project, root)
    record = registry.resolve(project, repo_root=root)
    path = record.plan(root) if record and record.plan_path else None
    plan_revision = digest(path.read_bytes()) if path and path.is_file() else None
    if value['selection_identity'] != source['selection_identity'] or value['plan_revision'] != plan_revision:
        raise ValueError('CHANGED_INPUT: displayed reader-plan/source basis changed; inspect current structure and outline before sending this context.')
    if 'spine_revision' in value and value['spine_revision'] != spine_snapshot(project, root)[1]:
        raise ValueError('CHANGED_INPUT: displayed narrative spine changed; inspect current structure before sending this context.')
    pins = {row['file']: row['raw_file_sha256'] for row in tree.get('sources', [])}
    for row in value['source_files']:
        if pins.get(row['file']) != row['source_digest']:
            raise ValueError('CHANGED_INPUT: displayed source occurrence changed; inspect its current outline before sending this context.')
    from laplace.manuscript.reader_plan import observe_basis, subjects_ref_current, SUBJECTS_REF_SCHEMA
    reader_cache = {}
    for basis in value.get('reader_subjects', []):
        current = subjects_ref_current(project, root, basis, cache=reader_cache) if basis.get('schema_version') == SUBJECTS_REF_SCHEMA else observe_basis(project, root, basis, cache=reader_cache) == basis
        if not current:
            raise ValueError('CHANGED_INPUT: displayed reader subject or its effective inputs changed; inspect before sending.')
    return {**({'reader_subjects': list(value['reader_subjects'])} if 'reader_subjects' in value else {}),
            **({'spine_revision': value['spine_revision']} if 'spine_revision' in value else {}),
            'plan_revision': value['plan_revision'], 'selection_identity': value['selection_identity'],
            'source_files': [dict(row) for row in value['source_files']]}


def effect_impact(project, root, changes, *, expected_selection):
    """Bounded mechanical witnesses over transient changed text, not scientific edits.

    No candidate/history body is loaded here. Selected indexed application handles
    are discovery only; their owner assesses live text/declared scientific basis.
    Formatting/preamble changes do not make all claims stale by file hash alone.
    """
    import difflib
    from laplace.pipeline import registry, schema
    from laplace.writing import records
    root = Path(root).resolve()
    source, tree = selected_tree(project, root)
    if source['selection_identity'] != expected_selection:
        return {'status': 'UNPROVED', 'bindings': [], 'reads': [],
                'coverage': 'Selected edition changed after source effect; no binding was inferred.'}
    selected = set(tree.get('files', []))
    record = registry.resolve(project, repo_root=root)
    plan_path = record.plan(root) if record and record.plan_path else None
    plan = json.loads(plan_path.read_bytes()) if plan_path and plan_path.is_file() else {}
    section_rows = list(schema.plan_sections(plan))
    parsed_after, observed, reads, ranges, changed_files = {}, {}, [], [], []
    for path, before, after in changes:
        path = Path(path).resolve()
        file = path.relative_to(root).as_posix()
        if file not in selected or path.suffix.lower() != '.tex':
            continue
        before = before.decode('utf-8') if isinstance(before, bytes) else before or ''
        after = after.decode('utf-8') if isinstance(after, bytes) else after or ''
        if digest(path.read_bytes()) != digest(after):
            return {'status': 'UNPROVED', 'bindings': [], 'reads': [],
                    'coverage': 'Changed file postimage moved before binding inspection.'}
        old_lines, new_lines = before.splitlines(), after.splitlines()
        if old_lines == new_lines:
            continue
        changed_files.append(file)
        if len(old_lines) + len(new_lines) > 40000:
            reads.append({'operation': 'structure', 'payload': {'view': 'detail', 'files': [file]}})
            ranges.append({'file': file, 'status': 'NOT_ASSESSED',
                           'reason': 'Large source delta requires deliberate scoped inspection.'})
            continue
        hunks = [(i1 + 1, max(i1 + 1, i2), j1 + 1, max(j1 + 1, j2))
                 for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines).get_opcodes()
                 if tag != 'equal']
        ranges.extend({'file': file, 'before': {'line_start': lo, 'line_end': hi},
                       'after': {'line_start': new_lo, 'line_end': new_hi}}
                      for lo, hi, new_lo, new_hi in hunks[:40])
        old_tree = {**tree, 'sources': [{**item, 'text': before,
                    'raw_file_sha256': digest(before)} if item['file'] == file else item
                    for item in tree.get('sources', [])]}
        parsed_before = {}
        for section in section_rows:
            declared_file = str(section.get('source_file') or '')
            if declared_file and file not in _declared_files(source, tree, declared_file):
                continue
            prior = correspondence(source, old_tree, section, heading_rows_by_file=parsed_before)
            current = correspondence(source, tree, section, heading_rows_by_file=parsed_after)
            affected = False
            for witness, pairs in ((prior, [(a, b) for a, b, _c, _d in hunks]),
                                   (current, [(c, d) for _a, _b, c, d in hunks])):
                heading = witness.get('heading') or {}
                if witness['precision'] == 'EXACT_HEADING' and heading.get('file') == file:
                    affected |= any(heading['line'] <= hi and lo <= heading['line_end'] for lo, hi in pairs)
            if not affected:
                continue
            ident = section['id']
            handle = {'operation': 'structure', 'payload': {'view': 'detail', 'section_ids': [ident]}}
            observed[ident] = {'section_id': ident, 'precision': current['precision'],
                              'status': 'REOBSERVE', 'reason': 'Source range changed; scientific meaning was not rewritten or adjudicated.',
                              'detail_read': handle,
                              'concept_reads': [{'operation': 'concept', 'payload': {'node': node}}
                                  for node in list(dict.fromkeys(schema.section_nodes(section) + list(section.get('beats') or [])))[:40]]}
    candidates = (records.accepted_link_candidates(root, project, files=changed_files, limit=40)
                  if changed_files else {'candidates': [], 'coverage': {'whole_history_loaded': False, 'body_reads': 0}})
    bindings_page = list(observed.values())[:40]
    reads.extend(row['detail_read'] for row in bindings_page)
    # The candidate owner returns exact application reads; they remain qualified
    # discovery, not a claim that old stored offsets still identify a live span.
    for row in candidates.get('candidates', []):
        if row.get('application_id'):
            reads.append({'operation': 'author_history', 'payload': {
                'view': 'record', 'id': 'activity:journal:' + row['application_id']}})
    return {'status': 'REOBSERVE' if changed_files else 'NONE', 'bindings': bindings_page,
            'bindings_omitted': max(0, len(observed) - 40), 'ranges': ranges[:40],
            'ranges_omitted': max(0, len(ranges) - 40),
            'accepted_links': candidates, 'reads': reads,
            'coverage': 'Exact changed-source ranges and witnessed plan sections; indexed application candidates require their own currentness read. No scientific status was inferred from whole-file SHA.'}


def contract():
    return {'subjects': {
        'source_outline': {'operation': 'structure', 'payload': {'view': 'outline'}},
        'reader_plan': {'operation': 'structure', 'payload': {'view': 'summary'}},
        'argument_evidence': {'operation': 'logical_plan', 'payload': {'view': 'catalog'}}},
        'precision': ['EXACT_HEADING', 'FILE_ONLY', 'INFERRED', 'UNRESOLVED', 'AMBIGUOUS'],
        'outline_rows': 'laplace.source-outline/2 rows carry ' + ', '.join(OUTLINE_ROW_FIELDS) + '. The raw byte basis of each file carrying a row of the page is stated once in sources[file].source_digest beside selected_source.selection_identity; read_routes carries the owner source_read and structure_read templates whose <file>, <line> and <line_end> a consumer fills from the row.',
        'reader_plan_rows': 'laplace.project-structure-summary/2 list rows carry id, title, kind, parent_id, number, order, job, collection, precision, binding_status, member_count and one detail_read; members (paged by member_offset/member_limit; each page states its ordered-membership cut and every continuation carries it as member_cut, refused with CHANGED_INPUT when the plan changed), source correspondence, source_reads and the clearing/prepare actions live on the detail read.',
        'occurrence': 'Physical selected file+heading; repeated includes list their source orders. Labels must be unique in that physical file; unlabelled anchors use existing exact source-anchor proof. Titles alone never establish a binding.',
        'source_digest': 'basis.source_digest and bind_source.expected_source_digest are sha256: prefixed RAW byte identities, including CRLF. They are not normalized span-writer text guards.',
        'binding': 'Use section.clearing_action, choose an outline occurrence, preserve its original selection/raw file basis and authority.plan_revision. bind_source updates the existing reader-plan section, not source bytes or scientific meaning; existing independent reader titles stay independent.',
        'plan_edits': 'structure_change operation plan accepts exactly one legacy op or ordered ops array (1..16), with the existing full plan-state expected_revision. Summary as_of is not that mutation guard.',
        'attention': {'field': 'workspace_context.structure_observation',
                      'input': observation_contract(),
                      'meaning': 'Validated displayed observation only; changed basis refuses context admission. It grants no write authority.'},
        'missing': 'Source-only UNBOUND is legitimate. Missing plan/graph does not hide the source outline. File-only and inferred links permit inspection, not a fabricated precise paragraph jump.'}


def spine_snapshot(project, root, *, plan=None, network=None):
    """Existing ordered narrative beats; distinct from section order and logic edges."""
    from laplace.research import corpus_ingest
    if network is None:
        tex = corpus_ingest.resolve_corpus(Path(root), project)
        network = corpus_ingest.corpus_network(tex, repo_root=root, name=project) if tex else {}
    nodes = network.get('nodes') or {}
    placements = {}
    if plan:
        from laplace.pipeline.schema import plan_sections
        for section in plan_sections(plan):
            for ident in section.get('beats') or []:
                placements.setdefault(ident, []).append(section['id'])
    rows = []
    for beat in network.get('spine') or []:
        ident = beat['id']
        rows.append({key: beat.get(key) for key in ('id', 'ord', 'narrative')} | {
            'term': (nodes.get(ident, {}).get('projection') or {}).get('term'),
            'section_ids': placements.get(ident, []), 'placed': bool(placements.get(ident)),
            'detail_read': {'operation': 'structure', 'payload': {'view': 'detail', 'node_id': ident}},
            'concept_read': {'operation': 'concept', 'payload': {'node': ident}},
            'full_guard_read': {'operation': 'structure', 'payload': {'view': 'full'}}})
    revision = digest(json.dumps([{key: row[key] for key in ('id', 'ord', 'narrative')}
                                 for row in rows], sort_keys=True, ensure_ascii=False))
    return rows, revision
