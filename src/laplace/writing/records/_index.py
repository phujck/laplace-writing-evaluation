"""Writing's journal index: which talk rows are indexed, their metadata projection and every Writing relation.

The captured-log mechanics (incremental suffix reads, replacement detection, line hashes, exact selected-row reads,
cut tokens) are core: laplace.core.records.capture. MetadataIndex is a CapturedLog that admits Writing's record kinds.
"""
from __future__ import annotations
import collections,copy,hashlib,math,threading,re
from pathlib import Path, PurePosixPath
from laplace.core.identity import canonical_digest
from laplace.core.records import capture
_LOCK = threading.RLock()


_INDEXES = collections.OrderedDict()


_KINDS = {'writing-source-execution', 'writing-source-admission', 'writing-source-admission-binding',
          'writing-native-call-claim', 'writing-native-call-outcome', 'writing-native-call-denied', 'writing-source-execution-stop',
          'writing-material-intake', 'writing-session', 'writing-session-settings', 'writing-session-import', 'writing-reader-input', 'writing-reader-refusal',
          'writing-binding', 'writing-turn', 'writing-turn-context-baseline', 'writing-reply', 'writing-tool-read',
          'writing-tool-read-baseline', 'writing-artifact', 'writing-reader-publication',
          'writing-tool-action', 'writing-tool-failure', 'writing-application',
          'writing-proposal', 'writing-proposal-anchor', 'writing-proposal-decision', 'writing-native-file-change',
          'writing-steer', 'writing-author-update-delivery', 'writing-author-update-ack',
          'writing-turn-stop-request'}


_FIELDS = ('id', 'record', 'project', 'session_id', 'turn_id', 'native_id', 'native_turn_id',
           'provider', 'model', 'effort', 'role', 'mode', 'ts', 'status', 'provider_stage',
           'packet', 'tier', 'model_source', 'created_at', 'settings_revision', 'provider_changed',
           'resolved_model', 'operation', 'tool_use_id', 'work_id', 'dispatch_id',
           'parent_turn_id', 'proposal_version', 'edit_id', 'application_id','candidate_id','candidate_kind','origin_turn_id','superseding_turn_id','successor_candidate_id','resolution_application_id',
           'profile_family','profile_scope','profile_path','template_selection','application_intent_id','candidate_version', 'caused_by', 'proposal_instance_version', 'proposal_content_sha256', 'proposal_sha256', 'edit_sha256', 'request_sha256', 'complete', 'rolled_back', 'decision', 'resolution',
           'by', 'origin', 'correction_id', 'approval_mode', 'output_sha256', 'duration_seconds', 'response_bytes', 'cost', 'cost_unit', 'request_id', 'context_id', 'context_sha256',
           'science_context_digest', 'tool_contract_digest', 'native_registration_signature',
           'commission_id', 'allowance_revision', 'source_grant_id', 'original_parent_session_id',
           'commission_request_id', 'admission_id', 'source_admission_id', 'native_invocation_id',
           'claim_id', 'original_wire_sha256', 'ordinal', 'state', 'deadline_at', 'opened_at', 'reason_code',
           'outcome', 'new_session', 'transport_kind', 'transport_epoch', 'transport_request_digest',
           'execution_generation')


_DERIVED = {'writing-tool-read-baseline'}


def _metadata(row, offset, end, order, line_hash):
    item = {key: row[key] for key in _FIELDS if key in row and isinstance(row[key], (str, int, float, bool, type(None)))}
    if isinstance(row.get('source_execution'), dict):
        item['source_execution'] = {key: copy.deepcopy(value) for key, value in row['source_execution'].items()
            if key in {'schema_version','commission_id','allowance_revision','project','work_id','source_grant_id','original_parent_session_id','policy'}
            and (isinstance(value, str) or key == 'policy' and isinstance(value, dict))}
        for key in ('commission_id','allowance_revision'):
            if isinstance(item['source_execution'].get(key), str): item[key]=item['source_execution'][key]
    if row.get('record') == 'writing-source-execution' and isinstance(row.get('policy'), dict):
        item['policy'] = copy.deepcopy(row['policy'])
    if isinstance(row.get('reader_profile'),dict):
        profile=row['reader_profile'];header={'profile':str(profile.get('profile') or 'UNSUPPORTED')[:160]}
        for key in ('manifest_id','support_basis','fingerprint'):
            if isinstance(profile.get(key),str) and re.fullmatch(r'sha256:[0-9a-f]{64}',profile[key]):header[key]=profile[key]
        ref=profile.get('input')
        if isinstance(ref,dict):
            header['input']={key:value for key,value in ref.items() if key in
                {'schema_version','content_handle','store','encoding','bytes'} and (
                isinstance(value,str) and len(value)<=256 or type(value)==int and value>=0)}
        item['reader_profile']=header
        digest=row.get('reader_intent_sha256')
        if isinstance(digest,str) and re.fullmatch(r'sha256:[0-9a-f]{64}',digest):item['reader_intent_sha256']=digest
    item.update(_offset=offset, _end=end, _order=order, _hash=line_hash)
    if row.get('record') == 'writing-artifact':
        item.update({key: row.get(key) for key in ('path', 'artifact_path', 'scope', 'sha256')
                     if isinstance(row.get(key), str)})
        if isinstance(row.get('original_metadata'),dict):item['original_metadata']=copy.deepcopy(row['original_metadata'])
        if isinstance(row.get('custody_degradation'),dict):
            item['custody_degradation']=copy.deepcopy(row['custody_degradation'])
    if row.get('record')=='writing-tool-read':
        item.update({key:row[key] for key in ('artifact_path','artifact_scope','artifact_record_id')
            if isinstance(row.get(key),str)})
    if row.get('record') in {'writing-artifact', 'writing-reader-publication'} and isinstance(row.get('reader_metadata'), dict):
        item['reader_metadata'] = copy.deepcopy(row['reader_metadata'])
    for field in ('proposal_projection','edit_projection','proposal_basis','source_anchor'):
        if isinstance(row.get(field),(dict,list)):item[field]=copy.deepcopy(row[field])
    if isinstance(row.get('successor_ref'),dict):item['successor_ref']=copy.deepcopy(row['successor_ref'])
    if row.get('candidate_kind')=='current-source-resolution' and isinstance(row.get('predecessor'),dict):
        item['predecessor']=copy.deepcopy(row['predecessor'])
    if row.get('record')=='writing-application' and row.get('candidate_id'):
        item['semantic_currentness']=(row.get('validation_basis') or {}).get('semantic_currentness','NOT_ASSERTED')
        item['review_obligations']=copy.deepcopy(row.get('review_obligations') or [])
    if isinstance(row.get('proposal_carrier'),dict):
        carrier=row['proposal_carrier']
        item['proposal_carrier']={key:copy.deepcopy(carrier[key]) for key in
            ('kind','candidate_record_id','candidate_version','application_id','application_ids',
             'covered_edit_ids','remaining_edit_ids','complete','emitted_content_sha256') if key in carrier}
    if isinstance(row.get('document'),dict):
        item['document']={key:row['document'].get(key) for key in ('root','manuscript_dir','edition','read_only','revision')}
    if isinstance(row.get('proposal'),dict):
        item['has_proposal']=True
        if isinstance(row['proposal'].get('edits'),list):
            from laplace.manuscript.manuscript_proposals import proposal_metadata
            item['proposal_projection']=proposal_metadata(row['proposal'])
        else:item['proposal_reference']={key:row['proposal'].get(key) for key in ('schema_version','content_handle','store','bytes')}
    if row.get('record')=='writing-application' and isinstance(row.get('edits'),dict):
        item['edits_reference']={key:row['edits'].get(key) for key in ('schema_version','content_handle','store','bytes')}
    if row.get('record')=='writing-application' and isinstance(row.get('edits'),list):
        from laplace.manuscript.manuscript_proposals import edit_metadata
        item['edit_projection']=[edit_metadata(edit) for edit in row['edits']]
    if isinstance(row.get('work_basis'), dict):
        item['work_basis'] = {key: row['work_basis'].get(key) for key in ('work_id', 'revision', 'scope_revision', 'parent')}
    settings = row.get('provider_settings')
    if isinstance(settings, dict):
        item['provider_settings'] = {key: settings.get(key) for key in ('provider', 'model', 'effort')}
    for key in ('queued_work_ids', 'candidate_edit_ids','consumed_correction_ids','correction_ids'):
        if isinstance(row.get(key), list): item[key] = [x for x in row[key] if isinstance(x, str)]
    if row.get('record') == 'writing-session' and isinstance(row.get('title'), str):
        item['title'] = row['title'][:200]  # Explicit stored title, never a prompt-derived label.
    if row.get('record') == 'writing-turn' and isinstance(row.get('text'), str):
        from ._fold import _session_display_title
        item['catalogue_display_title'] = _session_display_title(row['text'])
    if row.get('record')=='writing-turn' and any(row.get(key) for key in ('feedback_execution','workflow_execution','source_execution')):
        item['settings_execution_bound']=True
    if row.get('record') == 'writing-reply':
        text = row.get('text')
        if isinstance(text, str): item['response_sha256'] = hashlib.sha256(text.encode()).hexdigest()
        usage = row.get('usage')
        if isinstance(usage, dict):
            item['legacy_usage'] = {key: value for key, value in usage.items()
                if key in ('provider', 'input', 'cached_input', 'cache_write_input', 'output',
                           'reasoning_output', 'total', 'context_window')
                and isinstance(value, (str, int, float, type(None))) and not isinstance(value, bool)}
            item['legacy_usage_shape'] = sorted(usage)
        for key in ('context_tokens_used', 'context_window_advertised', 'context_window_effective'):
            value = row.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool): item[key] = value
        for key in ('usage_facts_projection', 'delivery_receipt_projection'):
            if isinstance(row.get(key), dict): item[key] = _provider_header(key, row[key])
        for key in ('usage_facts', 'delivery_receipt'):
            value = row.get(key)
            if isinstance(value, dict):
                item[key + '_reference'] = {k: value.get(k) for k in
                    ('schema_version', 'content_handle', 'store', 'bytes') if k in value}
    outcome = row.get('outcome')
    if isinstance(outcome, dict):
        item['outcome_status'] = outcome.get('status') if isinstance(outcome.get('status'), str) else None
        item['outcome_ref'] = {k: outcome.get(k) for k in ('schema_version', 'content_handle', 'bytes') if k in outcome}
        for key in ('identities', 'receipts'):
            if isinstance(outcome.get(key), list): item['outcome_' + key] = [x for x in outcome[key] if isinstance(x, str)]
    payload = row.get('payload')
    if isinstance(payload, dict) and not payload.get('content_handle'):
        item['targets'] = {key: payload[key] for key in ('id', 'node', 'file', 'path', 'run_id')
                           if isinstance(payload.get(key), str)}
    if isinstance(row.get('selection'),dict):
        item['selection']={key:row['selection'].get(key) for key in
            ('files','file','section_ids','node_id','node_ids','line_start','line_end') if key in row['selection']}
    if isinstance(row.get('consumed'),dict) and isinstance(row['consumed'].get('corrections'),list):
        item['consumed_correction_ids']=[value for value in row['consumed']['corrections'] if isinstance(value,str)]
    context = row.get('workspace_context')
    if isinstance(context, dict):
        item['workspace_context'] = {key: context.get(key) for key in
            ('surface', 'node_id', 'node_ids', 'section_ids', 'beat_id') if key in context}
        observation=context.get('structure_observation')
        if isinstance(observation,dict):
            item['workspace_context']['structure_observation']={
                key:copy.deepcopy(observation[key]) for key in ('plan_revision','spine_revision','selection_identity','reader_subjects')
                if key in observation and isinstance(observation[key],(str,type(None)))}
            item['workspace_context']['structure_observation']['source_files']=[
                {key:entry[key] for key in ('file','source_digest') if isinstance(entry.get(key),str)}
                for entry in (observation.get('source_files') if isinstance(observation.get('source_files'),list) else [])[:16]
                if isinstance(entry,dict)]
        if isinstance(context.get('label'), str):
            # Display only: retain validated current labels, bound oversized historical rows.
            item['workspace_context']['label'] = context['label'][:240]
            item['workspace_context']['label_truncated'] = len(context['label']) > 240
    return item


def recorded_source_file(document, file):
    """Exact repository identity under the retained document namespace, without I/O.

    Both historical source spellings were admitted by proposal_preflight._resolve.
    A missing namespace cannot be reconstructed from a basename or today's edition.
    """
    if not isinstance(document, dict) or not isinstance(file, str) or not file:
        return None
    directory = document.get('manuscript_dir')
    if not isinstance(directory, str) or not directory:
        return None
    raw, base = PurePosixPath(file.replace('\\', '/')), PurePosixPath(directory.replace('\\', '/'))
    if raw.is_absolute() or base.is_absolute() or '..' in raw.parts or '..' in base.parts:
        return None
    if not base.parts or not raw.parts:
        return None
    return str(raw if raw.is_relative_to(base) else base / raw)


def _application_carriers(application, carriers):
    """Use recorded candidate/content/effect identities, never title/path guesses."""
    def same_content(values):
        hashes = {(row.get('proposal_projection') or {}).get('content_sha256')
                  or (row.get('proposal_reference') or {}).get('content_handle') for row in values}
        # Unknown headers cannot certify repeated identical publication.
        return values[:1] if len(hashes) == 1 and None not in hashes else values

    version = application.get('candidate_version')
    if version:
        matched = [row for row in carriers if row.get('proposal_instance_version') == version]
        if matched:
            return same_content(matched)
    content = application.get('proposal_sha256')
    if content:
        matched = [row for row in carriers if
                   ((row.get('proposal_projection') or {}).get('content_sha256')
                    or (row.get('proposal_reference') or {}).get('content_handle')) == content]
        if matched:
            return same_content(matched)
    effect = application.get('edit_sha256')
    matched = [row for row in carriers if effect and
               (row.get('proposal_projection') or {}).get('effect_sha256') == effect]
    # An effect pin alone cannot choose between distinct scientific declarations.
    return same_content(matched)


def _current_span_candidates(values, span):
    """Prioritize exact current overlapping hashes before paging; old offsets prove nothing."""
    lines = span['lines']
    widths = sorted({entry.get('after_line_count') for entry in values
                     if type(entry.get('after_line_count')) is int and entry['after_line_count'] > 0})
    windows, hashes, hashed_bytes, skipped, skipped_count = {}, 0, 0, [], 0
    source_bytes = sum(len(line.encode('utf-8')) + 1 for line in lines)
    for width in widths:
        count = max(0, len(lines) - width + 1)
        # Cost is explicit: no history-by-file quadratic search or hidden truncation.
        estimated_bytes = source_bytes * width
        if len(windows) >= 32 or hashes + count > 100000 or hashed_bytes + estimated_bytes > 16 * 1024 * 1024:
            skipped_count += 1
            if len(skipped) < 32:
                skipped.append(width)
            continue
        matches = collections.defaultdict(list)
        for index in range(count):
            text = '\n'.join(lines[index:index + width])
            matches[hashlib.sha256(text.encode('utf-8')).hexdigest()].append((index + 1, index + width))
        windows[width] = matches
        hashes += count
        hashed_bytes += estimated_bytes
    selected = []
    for original in values:
        entry = dict(original)
        same_edition = isinstance(entry.get('document'), dict) and all(
            entry['document'].get(key) == span['document'].get(key)
            for key in ('root', 'manuscript_dir', 'edition'))
        positions = (windows.get(entry.get('after_line_count')) or {}).get(entry.get('after_sha256'))
        if (same_edition and entry.get('repository_file') == span['repository_file'] and positions):
            overlapping = [pair for pair in positions if pair[0] <= span['line_end'] and span['line_start'] <= pair[1]]
            if not overlapping:
                continue  # Current hash occurrences are all disjoint from the requested passage.
            entry['span_status'] = 'CURRENT_HASH_OVERLAP'
        else:
            entry['span_status'] = 'UNRESOLVED_CURRENT_SPAN'
        selected.append(entry)
    return selected, {'window_hashes': hashes, 'hashed_bytes_upper_bound': hashed_bytes,
                      'widths_examined': len(windows), 'incomplete_widths': skipped,
                      'incomplete_width_count': skipped_count,
                      'unresolved_candidates': sum(row['span_status'] != 'CURRENT_HASH_OVERLAP' for row in selected),
                      'basis': 'Current source hash overlap narrows discovery only; exact hydrated text/edition still decide standing.'}


def accepted_link_candidates(root, project, *, files=None, application_id=None,
                             edit_id=None, offset=0, limit=40, as_of='', _current_span=None):
    """Bounded declarations from the existing metadata index; no body/currentness claim.

    File filtering includes unknown-scope legacy applications so missing headers
    remain recoverable. A captured cut fixes historical discovery, while a later
    accepted_links read separately observes current source and logical basis.
    """
    if isinstance(files, str):
        files = [files]
    if files is not None and (not isinstance(files, (list, tuple, set))
                              or any(not isinstance(file, str) or not file for file in files)):
        raise ValueError('Accepted link files must be exact source file names.')
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Accepted link offset must be nonnegative and limit must be 1..100.')
    with _LOCK:
        idx = index(root)
        if files is not None:
            from laplace.manuscript import manuscript_source
            source = manuscript_source.resolve(project, repo_root=root)
            files = sorted({file if (project, file) in idx.source_links_by_file
                            else recorded_source_file(source, file) or file for file in files})
        query = {'project': project, 'files': sorted(set(files)) if files is not None else None,
                 'application_id': application_id, 'edit_id': edit_id}
        if _current_span is not None:
            query['span'] = {key: _current_span[key] for key in ('repository_file', 'line_start', 'line_end')}
            query['span']['source_revision'] = canonical_digest(_current_span['lines'])
        if application_id:
            selected = dict(idx.source_links_by_application.get((project, application_id), {}))
        elif edit_id:
            selected = dict(idx.source_links_by_edit.get((project, edit_id), {}))
            selected.update(idx.source_links_unknown.get(project, {}))
        elif files is None:
            selected = dict(idx.source_links_by_project.get(project, {}))
        else:
            selected = dict(idx.source_links_unknown.get(project, {}))
            for file in files:
                selected.update(idx.source_links_by_file.get((project, file), {}))
        values = [entry for entry in selected.values()
                  if (files is None or not entry.get('repository_file') or entry['repository_file'] in files)
                  and (not application_id or entry['application_id'] == application_id)
                  and (not edit_id or entry.get('edit_id') in (None, edit_id))]
        query_hash = canonical_digest(query)
        token = capture.decode_cut(as_of) if as_of else None
        if token and token['query'] != query_hash:
            raise ValueError('Accepted link continuation belongs to another scope.')
        upper = token['upper'] if token else idx.order
        values = [entry for entry in values if entry['_application']['_order'] <= upper]
        span_coverage = None
        if _current_span is not None:
            values, span_coverage = _current_span_candidates(values, _current_span)
        values.sort(key=lambda entry: (entry.get('span_status') == 'CURRENT_HASH_OVERLAP',
                                      entry['_application']['_order'], entry['_position']), reverse=True)
        revision = canonical_digest([(entry['_application']['_hash'],
                           (entry['_carrier'] or {}).get('_hash'), entry.get('document'),
                           entry.get('edit_id'), entry.get('repository_file'), entry['declaration_coverage'])
                          for entry in values])
        if token and token['revision'] != revision:
            raise ValueError('Accepted link candidate basis changed; read a fresh page.')
        cut = capture.encode_cut({'v': 1, 'query': query_hash, 'upper': upper, 'revision': revision})
        page = []
        for entry in values[offset:offset + limit]:
            item = {key: copy.deepcopy(value) for key, value in entry.items() if not key.startswith('_')}
            item['application_read'] = {'project': project, 'id': entry['application_id'],
                                        'row_sha256': entry['_application']['_hash']}
            carrier = entry['_carrier']
            item['carrier_read'] = {'project': project, 'id': carrier.get('id'),
                                    'row_sha256': carrier['_hash']} if carrier else None
            item['read_more'] = {'operation': 'author_history',
                                 'payload': {'view': 'record', 'id': 'activity:journal:' + str(entry['application_id'])}}
            if carrier:
                item['carrier_read_more'] = {'operation': 'author_history',
                    'payload': {'view': 'record', 'id': 'activity:journal:' + str(carrier.get('id'))}}
            page.append(item)
        remaining = max(0, len(values) - offset - len(page))
        return {'project': project, 'candidates': page, 'as_of': cut, 'file_scope': query['files'],
                'pagination': {'offset': offset, 'limit': limit, 'candidate_total': len(values),
                               'examined': len(page), 'remaining_candidates': remaining,
                               'next_offset': offset + len(page) if remaining else None},
                'coverage': {'status': ('PARTIAL_CURRENT_SCOPE' if span_coverage and
                                        (span_coverage['unresolved_candidates'] or span_coverage['incomplete_widths'])
                                        else 'PARTIAL' if remaining or offset else 'COMPLETE'),
                             'candidate_basis': 'Accepted declaration metadata; source and semantic basis unchecked.',
                             'unknown_scope_candidates': sum(entry['scope_status'] == 'UNKNOWN' for entry in values),
                             'legacy_declaration_candidates': sum(entry['declaration_coverage'] != 'INDEXED' for entry in values),
                             'body_reads': 0, 'whole_history_loaded': False,
                             'journal_status': idx.source_status, 'malformed_journal_rows': idx.malformed_rows,
                             **({'current_span': span_coverage} if span_coverage is not None else {})}}


class AmbiguousRecord(ValueError):
    """A selected immutable ID has multiple owner rows; not a stale SHA."""


class MetadataIndex(capture.CapturedLog):
    def __init__(self, root, path='contract/talk.jsonl', extractor=None):
        super().__init__(Path(root) / path)
        self.root = root
        self.extractor = extractor
        self._cache_key = None   # set by index(); a directly built index has no cache entry to invalidate
        self.stats.update({'custody_bodies_opened': 0, 'retained_content_body_bytes': 0, 'retained_catalogue_label_bytes': 0})
        self._init_indexes()
        self._changed_turns = set()

    def _init_indexes(self):
        self.rows = []
        # Recovery ambiguity includes every journal occurrence, even kinds
        # without a Writing projection. Retain counts, never their bodies.
        self.journal_id_counts = collections.Counter()
        self.by_id = collections.defaultdict(list)
        self.sessions = {}
        self.turns = {}
        self.by_request = collections.defaultdict(list)
        self.by_project = collections.defaultdict(list)
        self.by_session = collections.defaultdict(list)
        self.by_turn = collections.defaultdict(list)
        self.by_source_commission = collections.defaultdict(list)
        self.by_source_admission = collections.defaultdict(list)
        self.by_candidate = collections.defaultdict(list)
        self.template_candidates_by_project = collections.defaultdict(list)
        self.template_candidates_by_version = {}
        self.template_builds_by_candidate = collections.defaultdict(list)
        self.template_build_by_job = {}
        self.profile_candidates_by_project = collections.defaultdict(list)
        self.profile_candidates_by_scope = collections.defaultdict(list)
        self.by_predecessor = collections.defaultdict(list)
        self.applications_by_file=collections.defaultdict(dict)
        self.by_parent_turn = collections.defaultdict(list)
        self.project_sessions = collections.defaultdict(set)
        self.project_turns = collections.defaultdict(set)
        self.reader_subjects = {}
        self.reader_logical_lineage = {}
        self.reader_unit_creations = {}
        self.reader_restructure_receipts = {}
        self.reader_restructure_intents = {}
        self.reader_reserved_ids = collections.defaultdict(set)
        self._clear_source_links()

    def _reset(self):
        self._init_indexes()
        self.stats['retained_catalogue_label_bytes'] = 0

    def _admit(self, row, raw, offset, end):
        if row.get('id'):
            self.journal_id_counts[str(row['id'])] += 1
        if not self.extractor and not isinstance(row.get('record'), str):
            return False
        if not (self.extractor or row.get('record') in _KINDS):
            return True
        item = (self.extractor or _metadata)(row, offset, end, self.order, capture.line_hash(raw))
        if item is None:
            return True
        changed_turns = self._changed_turns
        self.rows.append(item)
        reader = item.get('reader_metadata')
        if isinstance(reader, dict):
            key = (item.get('project'), reader.get('path'))
            template_build=reader.get('template_build')
            if item.get('record')=='writing-artifact' and isinstance(template_build,dict):
                self.template_builds_by_candidate[(item.get('project'),template_build.get('candidate_id'),template_build.get('candidate_version'))].append(item)
                self.template_build_by_job[(item.get('project'),template_build.get('build_job_id'))]=item
            structural=reader.get('restructure')
            admitted=reader.get('restructure_intent')
            if item.get('record')=='writing-reader-publication' and isinstance(structural,dict):
                art=(structural.get('receipt') or {}).get('intent_artifact_id')
                if art:self.reader_restructure_receipts[(item.get('project'),art)]=item
            if item.get('record')=='writing-artifact' and isinstance(admitted,dict):
                self.reader_restructure_intents[(item.get('project'),admitted.get('section_id'))]=item
            logical=reader.get('logical_lineage')
            if item.get('record')=='writing-artifact' and isinstance(logical,dict):
                if not logical.get('inverse') and logical.get('intent_artifact_id'):
                    for ident in logical.get('successor_ids') or []:
                        self.reader_unit_creations.setdefault(
                            (item.get('project'), logical.get('section_id'), ident),
                            logical['intent_artifact_id'])
                for role in ('retired_ids','successor_ids'):
                    relation={**logical,'role':role,'publication_artifact_id':item['id']}
                    for ident in logical.get(role) or []:
                        self.reader_logical_lineage[(item.get('project'),logical.get('section_id'),ident)]=relation
            self.reader_reserved_ids[key].update(reader.get('reserved_ids') or [])
            if item.get('record') == 'writing-reader-publication':
                for subject, basis in (reader.get('subjects') or {}).items():
                    self.reader_subjects[(*key, subject)] = copy.deepcopy(basis)

        self.stats['retained_catalogue_label_bytes'] += len(str(item.get('catalogue_display_title') or '').encode())
        if item.get('commission_id'): self.by_source_commission[(item.get('project'), item['commission_id'])].append(item)
        if item.get('source_admission_id') or item.get('admission_id'):
            self.by_source_admission[item.get('source_admission_id') or item['admission_id']].append(item)
        if item.get("id"): self.by_id[item["id"]].append(item)
        if item.get('parent_turn_id'): self.by_parent_turn[item['parent_turn_id']].append(item)
        owner = item.get('project')
        if owner: self.by_project[owner].append(item)
        sid = item.get('session_id') or (item.get('id') if item['record'] == 'writing-session' else None)
        tid = item.get('turn_id') or (item.get('id') if item['record'] == 'writing-turn' else None)
        if sid: self.by_session[sid].append(item)
        if tid: self.by_turn[tid].append(item)
        cid=item.get('candidate_id') or (item.get('id') if item.get('candidate_kind') in {'current-source-resolution','profile-change','document-template'} else None)
        if cid:self.by_candidate[cid].append(item)
        if item.get('record')=='writing-proposal' and item.get('candidate_kind')=='document-template':
            self.template_candidates_by_project[owner].append(item)
            self.template_candidates_by_version.setdefault((owner,item.get('proposal_instance_version')),item)
        if item.get('record')=='writing-proposal' and item.get('candidate_kind')=='profile-change':
            self.profile_candidates_by_project[owner].append(item)
            self.profile_candidates_by_scope[item.get('profile_scope')].append(item)
        if item.get('candidate_kind')=='current-source-resolution':
            pred=item.get('predecessor') or {};old=pred.get('candidate_ref') or {}
            self.by_predecessor[(owner,old.get('id') or pred.get('turn_id'),
                old.get('version') or pred.get('proposal_version'),pred.get('edit_id'))].append(item)
        if not self.extractor and cid:changed_turns.add(cid)
        if item['record']=='writing-application':
            document=item.get('document') or (self.turns.get(tid) or {}).get('document') or {}
            for edit in item.get('edit_projection') or []:
                file=recorded_source_file(document,edit.get('file'))
                if file:self.applications_by_file[(owner,file)][item['id']]=item
        if not self.extractor and tid and (item['record'] in {'writing-turn','writing-turn-context-baseline','writing-application'} or item.get('has_proposal')):
            changed_turns.add(tid)
        if not self.extractor and item['record']=='writing-session':
            changed_turns.update(value['id'] for value in self.by_session.get(sid,()) if value['record']=='writing-turn')
        if item.get('record') == 'writing-session':
            self.sessions[item['id']] = item
            if owner: self.project_sessions[owner].add(item['id'])
        elif item.get('record') == 'writing-turn':
            self.turns[item['id']] = item
            if owner:
                self.project_turns[owner].add(item['id'])
                if sid: self.project_sessions[owner].add(sid)
        if item.get('record') in {'writing-turn','writing-reader-refusal'}:
            request=item.get('request_id')
            if owner and isinstance(request,str) and 1<=len(request)<=160:
                self.by_request[(owner,request)].append(item)
        return True

    def _after_advance(self):
        changed, self._changed_turns = self._changed_turns, set()
        for tid in changed:
            self._refresh_source_links(tid)

    def _clear_source_links(self):
        self.source_links_by_file = collections.defaultdict(dict)
        self.source_links_by_project = collections.defaultdict(dict)
        self.source_links_unknown = collections.defaultdict(dict)
        self.source_links_by_turn = {}
        self.source_links_by_application = collections.defaultdict(dict)
        self.source_links_by_edit = collections.defaultdict(dict)

    def _refresh_source_links(self, tid):
        """Reindex only applications in a changed turn, without custody reads."""
        for key, old in self.source_links_by_turn.pop(tid, {}).items():
            self.source_links_by_file[(old.get('project'), old.get('repository_file'))].pop(key, None)
            self.source_links_by_project[old.get('project')].pop(key, None)
            self.source_links_unknown[old.get('project')].pop(key, None)
            self.source_links_by_application[(old.get('project'), old.get('application_id'))].pop(key, None)
            self.source_links_by_edit[(old.get('project'), old.get('edit_id'))].pop(key, None)
        entries = {}
        rows = self.by_candidate.get(tid, ()) if tid in self.by_candidate else self.by_turn.get(tid, ())
        carriers = [row for row in rows if row.get('has_proposal')]
        for app in rows:
            if app['record'] != 'writing-application' or not app.get('complete'):
                continue
            prior = [row for row in rows if row['_order'] <= app['_order']]
            document = app.get('document') or next((row['document'] for row in reversed(prior)
                             if row['record'] in {'writing-turn', 'writing-turn-context-baseline'}
                             and isinstance(row.get('document'), dict)), None)
            projection = app.get('edit_projection')
            carrier = None
            if projection is None:
                matches = _application_carriers(app, carriers)
                if len(matches) == 1:
                    carrier = matches[0]
                    projection = (carrier.get('proposal_projection') or {}).get('edits')
                    if projection is not None and app.get('candidate_edit_ids'):
                        projection = [edit for edit in projection if edit.get('edit_id') in app['candidate_edit_ids']]
                    document = (carrier.get('proposal_basis') or {}).get('document') or document
            # Missing old headers are retained as unknown candidates, not erased.
            for position, edit in enumerate(projection if projection is not None else [None]):
                known = isinstance(edit, dict) and edit.get('declaration_schema') == 'laplace.source-declarations/1'
                if known and not (edit.get('develops') or edit.get('evidence_refs')):
                    continue
                key = (app['_order'], position)
                repository_file = recorded_source_file(document, edit.get('file')) if edit else None
                entry = {'project': self.project(app), 'application_id': app.get('id'),
                         'turn_id': app.get('turn_id'), 'candidate_id':app.get('candidate_id'),
                         'origin_turn_id':app.get('origin_turn_id'),
                         'semantic_currentness':app.get('semantic_currentness'),
                         'review_obligations':copy.deepcopy(app.get('review_obligations') or []),
                         'session_id': (self.turns.get(tid) or {}).get('session_id'),
                         'document': document, 'candidate_edit_ids': list(app.get('candidate_edit_ids') or []),
                         'declaration_coverage': 'INDEXED' if known else 'LEGACY_UNKNOWN',
                         'scope_status': 'FILE' if repository_file else 'UNKNOWN',
                         'repository_file': repository_file,
                         '_application': app, '_carrier': carrier, '_position': position}
                if edit:
                    entry.update({name: copy.deepcopy(edit[name]) for name in
                                  ('edit_id', 'file', 'line_start', 'line_end', 'after_sha256', 'after_line_count',
                                   'develops', 'evidence_refs') if name in edit})
                entries[key] = entry
                self.source_links_by_project[entry['project']][key] = entry
                self.source_links_by_application[(entry['project'], entry['application_id'])][key] = entry
                if entry.get('edit_id'):
                    self.source_links_by_edit[(entry['project'], entry['edit_id'])][key] = entry
                if repository_file:
                    self.source_links_by_file[(entry['project'], repository_file)][key] = entry
                else:
                    self.source_links_unknown[entry['project']][key] = entry
        if entries:
            self.source_links_by_turn[tid] = entries

    def project(self, row):
        captured=getattr(self,'_captured_projects',None)
        if captured is not None:return captured.get(row.get('_order'))
        direct = row.get('project')
        turn = self.turns.get(row.get('turn_id')) or (row if row.get('record') == 'writing-turn' else {})
        session = self.sessions.get(row.get('session_id') or turn.get('session_id')) or {}
        return direct or turn.get('project') or session.get('project')


def index(root, path='contract/talk.jsonl', extractor=None):
    root = Path(root).resolve(); key = (str(root), str(path))
    with _LOCK:
        value = _INDEXES.pop(key, None) or MetadataIndex(root, path, extractor)
        value._cache_key=key
        value.advance(); _INDEXES[key] = value
        # Bound fixture/root lifetimes, not project paths within one workspace:
        # a global feedback query must not evict the hot talk index and force 54MB rescans.
        roots = list(dict.fromkeys(key[0] for key in _INDEXES))
        while len(roots) > 4:
            retired = roots.pop(0)
            for old_key in [key for key in _INDEXES if key[0] == retired]: _INDEXES.pop(old_key)
        return value


def _snapshot(idx, upper):
    """The sessions/turns maps of ONE captured cut, through THE identity rule (_family_rows) bounded by `upper`.

    Every collision, immutable-duplicate and creation check sees only rows at or before the cut, so a row appended
    later (another project or kind under the same ID) never changes an earlier observation, while the current cut
    detects it. Single-row and multi-version sessions take the same branch. A global map cannot hold two projects'
    rows of one immutable ID; such an ID is reported as an identity issue, never silently chosen."""
    view = copy.copy(idx); view.cut_upper = upper; view.identity_issues = []
    for name, kind in (('sessions', SESSION_FAMILY), ('turns', 'writing-turn')):
        values = {}
        for ident in getattr(idx, name):
            try:
                resolved = _family_rows(idx, ident, upper=upper, verify=False)
            except AmbiguousRecord:
                view.identity_issues.append({'owner':'authoring_surface','kind':kind,'id':ident,'status':'AMBIGUOUS'})
                continue
            if resolved is not None and resolved[0] == kind:
                values[ident] = resolved[1][-1]   # the current version at this cut
        setattr(view, name, values)
    return view


def _dispatch_metadata_cut(root, project, dispatch_ids):
    """Detach only closed requested dispatch proof metadata from one index cut.

    This is not project-history discovery. Namespace inference is captured from
    the existing owner index without inventing a project on raw actor records.
    Required ID collisions remain visible even when the duplicate actor is outside
    this selection. No context/proposal/action or custody bodies are retained.
    """
    targets=frozenset(dispatch_ids)
    with _LOCK:
        idx=index(root);upper=idx.order;selected={};admissions=[];evidence={}
        def eligible(row):return row['_order']<=upper and idx.project(row)==project
        def add(row):selected[row['_order']]=row
        def identity(row):
            # Every row of a selected ID inside the cut is identity EVIDENCE (R1). Same-kind same-project rows are the
            # selection; a foreign-project or other-kind row of the ID is retained in by_id only (never folded), so THE
            # canonical family rule (_family_rows) applied to this cut still sees the collision it must refuse.
            if row.get('id'):
                for value in idx.by_id.get(row['id'],()):
                    if value['_order']>upper:continue
                    if value['record']==row['record'] and eligible(value):add(value)
                    else:evidence[value['_order']]=value
            else:add(row)
        for tid in idx.project_turns.get(project,()):
            rows=[row for row in idx.by_id.get(tid,()) if row['record']=='writing-turn' and eligible(row)]
            if not any(row.get('dispatch_id') in targets for row in rows):continue
            if len(rows)!=1:raise ValueError('Selected dispatch writing-turn identity is ambiguous.')
            admissions.append(rows[0]);identity(rows[0])
        for child in admissions:
            sid=child.get('session_id')
            # Include all exact original session identity rows as well as the
            # selected session's settings/binding chronology through this cut.
            for row in idx.by_id.get(sid,()):
                if row['record']=='writing-session' and eligible(row):identity(row)
            for row in idx.by_session.get(sid,()):
                if row['record'] in {'writing-session','writing-session-settings','writing-binding'} and eligible(row):identity(row)
            for row in idx.by_turn.get(child['id'],()):
                if row['record'] in {'writing-reply','writing-tool-read'} and eligible(row):identity(row)
        rows=sorted(selected.values(),key=lambda row:row['_order'])
        cut=copy.copy(idx);cut.rows=rows;cut.dispatch_ids=targets;cut.cut_upper=upper
        extra=[row for order,row in sorted(evidence.items()) if order not in selected]
        cut._captured_projects={row['_order']:idx.project(row) for row in (*rows,*extra)}
        cut.by_id=collections.defaultdict(list);cut.by_session=collections.defaultdict(list);cut.by_turn=collections.defaultdict(list)
        cut.sessions={};cut.turns={}
        for row in rows:
            if row.get('id'):cut.by_id[row['id']].append(row)
            sid=row.get('session_id') or (row.get('id') if row['record']=='writing-session' else None)
            tid=row.get('turn_id') or (row.get('id') if row['record']=='writing-turn' else None)
            if sid:cut.by_session[sid].append(row)
            if tid:cut.by_turn[tid].append(row)
            if row['record']=='writing-session':cut.sessions[row['id']]=row
            elif row['record']=='writing-turn':cut.turns[row['id']]=row
        for row in extra:cut.by_id[row['id']].append(row)
        for values in cut.by_id.values():values.sort(key=lambda row:row['_order'])
        return cut


def _provider_header(field, value):
    """Canonical family validation; numeric/identity-only headers never carry raw observations."""
    from laplace.writing import operating as owner
    try: owner.validate_provider_metadata({field: value})
    except ValueError:
        return {'schema_version': value.get('schema_version'), 'status': 'UNAVAILABLE', 'reason': 'unsupported-or-malformed-owner-header'}
    if field == 'usage_facts_projection':
        selected = value.get('selected')
        if not isinstance(selected, dict): return {'status': 'UNAVAILABLE', 'reason': 'malformed-owner-header'}
        keep = ('schema_version', 'attempt_id', 'logical_turn_id', 'provider', 'native_binding_id', 'native_turn_id', 'reset_epoch')
        result = {key: value.get(key) for key in keep}
        def observation(item):
            if item is None: return None
            if not isinstance(item, dict): raise ValueError()
            keys = ('observation_id','basis','counter_scope','counter_domain','completeness','value','value_basis','metric','exact_post_compaction_occupancy','derivation')
            out = {key: item.get(key) for key in keys if isinstance(item.get(key), (str, int, float, type(None)))}
            counts = item.get('counts')
            if counts is not None:
                if not isinstance(counts, dict) or any(counts.get(key) is not None and
                    (not isinstance(counts[key], int) or isinstance(counts[key], bool) or counts[key] < 0)
                    for key in owner.USAGE_FACTS_CONTRACT['counts']): raise ValueError()
                out['counts'] = {key: counts.get(key) for key in owner.USAGE_FACTS_CONTRACT['counts']}
            ref = item.get('raw_observation_ref')
            if isinstance(ref, dict): out['raw_observation_ref'] = {key: ref.get(key) for key in
                ('schema_version','content_handle','store','bytes','encoding') if key in ref}
            cost = item.get('reported_cost_estimate')
            if isinstance(cost, dict): out['reported_cost_estimate'] = {key: val for key, val in cost.items()
                if key in ('amount','currency','basis','invoice','field','source','value','unit','source_field','cost_basis','counter_domain') and isinstance(val, (str,int,float,bool,type(None)))}
            return out
        try:
            result['selected'] = {key: observation(selected.get(key)) for key in owner.USAGE_FACTS_CONTRACT['selection_keys'] if key != 'unselected_variants'}
            variants = selected.get('unselected_variants', [])
            if not isinstance(variants, list): raise ValueError()
            result['selected']['unselected_variants'] = [observation(item) for item in variants[:100]]
            result['variants_omitted'] = max(0, len(variants) - 100)
        except (ValueError, TypeError): return {'status': 'UNAVAILABLE', 'reason': 'malformed-owner-header'}
        result['coverage'] = {key: val for key,val in (value.get('coverage') or {}).items()
                              if isinstance(val, (str,bool,int,type(None)))} if isinstance(value.get('coverage'), dict) else {}
        result['baseline'] = {key: val for key,val in (value.get('baseline') or {}).items()
                              if isinstance(val, (str,bool,int,type(None)))} if isinstance(value.get('baseline'), dict) else {}
        native = (value.get('coverage') or {}).get('native_metadata') if isinstance(value.get('coverage'), dict) else None
        if isinstance(native, dict):
            result['coverage']['native_metadata'] = {key: val for key,val in native.items()
                if isinstance(val, (str,bool,int,type(None))) and key not in ('text','content','error')}
        baseline_counts = (value.get('baseline') or {}).get('value') if isinstance(value.get('baseline'), dict) else None
        if isinstance(baseline_counts, dict):
            result['baseline']['value'] = {key: baseline_counts.get(key) for key in owner.USAGE_FACTS_CONTRACT['counts']
                if baseline_counts.get(key) is None or isinstance(baseline_counts.get(key), int) and not isinstance(baseline_counts.get(key), bool)}
        models = value.get('model_observations') or []
        result['model_observations'] = [{key: item.get(key) for key in ('actual_reported_model','resolved_alias','admitted_model','source','observed_at') if key in item}
            for item in models[:100] if isinstance(item, dict)] if isinstance(models, list) else []
        return result
    parts = value.get('parts')
    if not isinstance(parts, dict) or any(not isinstance(parts.get(key), dict)
            or parts[key].get('state') not in owner.DELIVERY_RECEIPT_CONTRACT['states']
            for key in owner.DELIVERY_RECEIPT_CONTRACT['parts']):
        return {'status': 'UNAVAILABLE', 'reason': 'malformed-owner-delivery-header'}
    # The owner creates metadata-only delivery fields. Reject accidental text fields recursively.
    def clean(item):
        if isinstance(item, dict): return {key: clean(val) for key,val in item.items()
            if key not in ('text','prompt','content','instructions','raw_observation','error')}
        if isinstance(item, list): return [clean(val) for val in item[:512]]
        return item if isinstance(item, (str,int,float,bool,type(None))) else None
    return clean({key:value.get(key) for key in ('schema_version','provider','app_semantic_digest','parts','channels',
        'request_fingerprints','request_fingerprint_basis','native_inventory','platform_extra_instructions','provider_retention')})


def exact_record(project, ident, root, *, catalogue_only=False):
    """One existing public journal row by owner ID, resolved only on explicit demand."""
    with _LOCK:
        return _exact_record_locked(project, ident, root, catalogue_only=catalogue_only)


def _invalidate_index_cut(idx):
    """Refuse this cut; rebuild only its still-matching live generation next time."""
    with _LOCK:
        live=_INDEXES.get(idx._cache_key)
        if live is not None and live._generation is idx._generation:
            live.identity=None


def _raw_indexed_record(idx, meta):
    """Read exactly one captured immutable row, without unrelated custody bodies."""
    try:
        row, data = capture.read_captured_row(idx.path, meta['_offset'], meta['_end'], meta['_hash'])
    except capture.CapturedRowChanged:
        _invalidate_index_cut(idx)
        raise
    idx.stats['selected_rows_read']=idx.stats.get('selected_rows_read',0)+1
    idx.stats['selected_bytes_read']=idx.stats.get('selected_bytes_read',0)+len(data)
    if row.get('id')!=meta.get('id') or row.get('record')!=meta.get('record'):
        raise ValueError('The selected journal row identity disagrees with its index.')
    return row


def _exact_record_locked(project, ident, root, *, catalogue_only=False):
    raw_id = ident.removeprefix('activity:journal:')
    idx = index(root)
    try:
        resolved = _resolve(idx, project, raw_id)
    except AmbiguousRecord as error:
        raise AmbiguousRecord('This owner record ID is ambiguous; inspect the exact saved turn. ' + str(error)) from None
    if resolved is None: return None
    meta, raw, _version, _related = resolved
    if catalogue_only and meta['record'] in {
            'writing-turn', 'writing-reply', 'writing-application', 'writing-proposal-decision',
            'writing-tool-read', 'writing-tool-action', 'writing-tool-failure',
            'writing-native-file-change', 'writing-proposal'}:
        return None  # Preserve the existing richer Activity detail contract.
    from laplace.representation import writing_bodies as bodies
    row = bodies.resolve_fields(raw, Path(root), strict=True)
    return copy.deepcopy(row), copy.deepcopy(meta)


#: THE record-family rule (Root e331). Only the writing-session ID family has version/upsert semantics: the session owner
#: appends a whole new writing-session row for a legitimate settings/configuration change. Every other kind is immutable.
SESSION_FAMILY = 'writing-session'
#: A session's immutable identity: fixed at creation and restated unchanged by every later version. Settings (provider,
#: model, effort, native ids, bindings) are DATA that may change; runtime/admission guards decide their effects.
SESSION_IDENTITY_FIELDS = ('project', 'role', 'dispatch_id', 'packet')
#: The session's creation identity (Root ruling ART-9e1c3774: turn_admission.create_session mints it once; legitimate
#: updates retain it). Two versions that BOTH carry it and disagree are two creations, not an upsert. A legacy version
#: without it stays admissible; row ts and settings are never creation identity.
SESSION_CREATION_FIELD = 'created_at'


def _cut_rows(idx, ident, upper=None):
    """Every indexed journal row of one ID inside ONE captured cut, oldest first: `upper` when given, else the cut a
    _snapshot or _dispatch_metadata_cut view carries (cut_upper), else the whole live index at its current order."""
    bound = getattr(idx, 'cut_upper', None) if upper is None else upper
    return [row for row in idx.by_id.get(ident, ()) if bound is None or row['_order'] <= bound]


def _creation_identity(value):
    """created_at as creation identity (B HOLD F3). Equal numbers are one creation (5 == 5.0: exact int/float
    comparison, no rounding); text compares exactly and is never coerced to a number without an authored rule; a bool
    is not a number. Anything else compares by its exact type and representation."""
    if isinstance(value, bool):
        return ('bool', value)
    if isinstance(value, (int, float)):
        return ('non-finite', repr(value)) if isinstance(value, float) and not math.isfinite(value) else ('number', value)
    if isinstance(value, str):
        return ('text', value)
    return ('value', type(value).__name__, repr(value))


def _family_rows(idx, ident, *, project=None, kind=None, upper=None, verify=True):
    """THE one cut-bounded identity rule (Root e331; B HOLD PHASE-c7e728 F1/F2): (family, versions, raws) of one ID at
    the captured cut, or None when the cut holds no row of it (in `project`, when one is selected).

    The cut is `upper`, else the view's cut_upper, else the live index order (_cut_rows); every collision, duplicate and
    creation check reads only rows inside it. The declared scope, identical for the snapshot, the single-row reader,
    the resolver and the supporting-row reader:
    - A writing-session ID is GLOBAL. Once any row of the ID inside the cut is a writing-session row, every row of
      that ID must be a writing-session row of one project; otherwise the ID is AMBIGUOUS from EVERY side, whether
      the read selects the session or the colliding row.
    - Every other kind is IMMUTABLE and project-scoped: inside the selected project the ID names exactly ONE row of
      ONE kind (byte-identical duplicates are two rows). Another project's row of an immutable ID is that project's
      own identity. Without a selected project (a global map) two projects' rows of one immutable ID cannot be chosen.
    - kind, when given, must be the only record kind of the ID in the selected scope.
    raws is the verified rows of a session history that needed them; otherwise None and the caller reads (and
    hash-verifies) its one selected row. Nothing here picks a latest-any row."""
    every = _cut_rows(idx, ident, upper)
    rows = every if project is None else [row for row in every if idx.project(row) == project]
    if not rows:
        return None
    if any(row.get('record') == SESSION_FAMILY for row in every) and (
            any(row.get('record') != SESSION_FAMILY for row in every) or len({idx.project(row) for row in every}) != 1):
        raise AmbiguousRecord('The supporting journal identity is ambiguous: session %s collides with another record kind or project.' % ident)
    kinds = {row.get('record') for row in rows}
    if len(kinds) != 1 or (kind is not None and kinds != {kind}):
        raise AmbiguousRecord('Record %s is ambiguous: its rows name %s%s.' % (
            ident, ', '.join(sorted(map(str, kinds))), '' if kind is None else ' (requested %s)' % kind))
    family = next(iter(kinds))
    if family == SESSION_FAMILY:
        versions, raws = _session_versions(idx, ident, rows, verify=verify)
        return family, versions, raws
    if len(rows) != 1:
        projects = {idx.project(row) for row in rows}
        raise AmbiguousRecord('Record %s is ambiguous: an immutable %s ID has %d rows%s.' % (
            ident, family, len(rows), '' if len(projects) == 1 else ' across %d projects' % len(projects)))
    return family, rows, None


def _session_versions(idx, ident, metas, *, verify=True):
    """The verified version history of ONE writing-session ID's rows, already bounded and collision-checked by
    _family_rows, oldest first.

    Every version restates the session's immutable identity (SESSION_IDENTITY_FIELDS) and, where both record it, its
    creation identity (SESSION_CREATION_FIELD compared by _creation_identity). With verify every version is read and
    hash-verified (_raw_indexed_record); a cut snapshot (verify=False) skips the reads only when every version is
    byte-identical and therefore cannot contradict. A contradiction refuses; nothing picks a latest-any row."""
    versions = sorted(metas, key=lambda row: row['_order'])
    if not verify and len({row['_hash'] for row in versions}) <= 1:
        return versions, None
    raws = [_raw_indexed_record(idx, meta) for meta in versions]
    for raw in raws[1:]:
        changed = [field for field in SESSION_IDENTITY_FIELDS if raw.get(field) != raws[0].get(field)]
        if changed:
            raise AmbiguousRecord('The supporting journal identity is ambiguous: session %s versions contradict its immutable %s.'
                                  % (ident, ', '.join(changed)))
    created = {_creation_identity(raw[SESSION_CREATION_FIELD]) for raw in raws if raw.get(SESSION_CREATION_FIELD) is not None}
    if len(created) > 1:
        raise AmbiguousRecord('The supporting journal identity is ambiguous: session %s versions contradict its creation identity '
                              '(%s differs between versions that both record it).' % (ident, SESSION_CREATION_FIELD))
    return versions, raws


def _resolve(idx, project, ident, *, kind=None, expected_row_sha256=None, retained_row_sha256=None):
    """(meta, raw, version, supporting) of one owner record ID at this captured cut, or None when the project has none.

    Identity follows THE cut-bounded rule _family_rows and its declared scope: immutable kinds (turn, reply, artifact,
    everything but writing-session) need exactly one row in the project; a writing-session ID is global and
    resolves through _session_versions: by default its CURRENT (latest) version; retained_row_sha256 instead selects one
    exact recorded version, reported as selection 'retained' and never as current authority. expected_row_sha256 guards
    the current selection and refuses when it moved. kind, when given, must be the only record kind of the ID."""
    if expected_row_sha256 and retained_row_sha256:
        raise ValueError('expected_row_sha256 guards the current row and retained_row_sha256 selects a retained row: name only one.')
    raw_id = str(ident).removeprefix('activity:journal:')
    resolved = _family_rows(idx, raw_id, project=project, kind=kind)
    if resolved is None:
        return None
    family, versions, raws = resolved
    current = versions[-1]
    if retained_row_sha256:
        matches = [position for position, row in enumerate(versions) if row['_hash'] == retained_row_sha256]
        if len(matches) != 1:
            raise ValueError('Retained journal row %s is not one recorded version of %s.' % (retained_row_sha256, raw_id))
        position, selection = matches[0], 'retained'
    else:
        position, selection = len(versions) - 1, 'current'
    meta = versions[position]
    if expected_row_sha256 and meta['_hash'] != expected_row_sha256:
        raise ValueError('Selected journal row changed since discovery; read its metadata again.')
    raw = raws[position] if raws is not None else _raw_indexed_record(idx, meta)
    trace = []
    supporting = _supporting_rows(idx, raw, project, trace=trace)
    version = {'family': family, 'selection': selection, 'is_current': meta is current, 'versions_total': len(versions),
               'current_row_sha256': current['_hash'], 'selected_row_sha256': meta['_hash'], 'supporting_row_sha256': trace}
    return meta, raw, version, supporting


def resolve_record_family(idx, project, ident, *, kind=None, expected_row_sha256=None, retained_row_sha256=None):
    """THE canonical record-family resolution every selected reader composes (B owner; A consumers read it, never re-derive it).

    Returns a detached {meta, raw, version} for one owner record ID of `project` at the captured index `idx`, or None
    when the project has no row of that ID. meta is the verified selected row metadata, raw the verified selected JSON
    row (no custody body hydration), version {family, selection: current|retained, is_current, versions_total,
    current_row_sha256, selected_row_sha256, supporting_row_sha256: [{record, id, row_sha256}]}. Only the writing-session
    family versions (SESSION_IDENTITY_FIELDS, and a numerically equal created_at where both record it, must agree);
    under the declared scope of _family_rows, immutable duplicates in the project, kind collisions in the project, any
    collision of a session-claimed ID (from either side) and contradictory session histories raise AmbiguousRecord;
    an immutable ID in another project is that project's own identity, not a collision; a stale expected pin or an
    unrecorded retained pin raises ValueError; a changed captured row raises capture.CapturedRowChanged. Read-only."""
    with _LOCK:
        resolved = _resolve(idx, project, ident, kind=kind, expected_row_sha256=expected_row_sha256, retained_row_sha256=retained_row_sha256)
        if resolved is None:
            return None
        meta, raw, version, _supporting = resolved
        return copy.deepcopy({'meta': meta, 'raw': raw, 'version': version})


def selected_journal_fields(project, ident, root, *, fields, expected_row_sha256=None):
    """Verified exact fields of one journal row, without unrelated body trees."""
    if not isinstance(fields, (list, tuple)) or any(not isinstance(field, str) for field in fields):
        raise ValueError('Selected journal fields must be named explicitly.')
    with _LOCK:
        idx = index(root)
        try:
            resolved = _resolve(idx, project, ident, expected_row_sha256=expected_row_sha256)
        except AmbiguousRecord as error:
            raise AmbiguousRecord('Exact selected journal record is missing or ambiguous: ' + str(error)) from None
        if resolved is None:
            raise ValueError('Exact selected journal record is missing or ambiguous.')
        _meta, raw, _version, _supporting = resolved
        from laplace.representation import writing_bodies as bodies
        from laplace.core import bodies as core_bodies
        requested = {field: raw.get(field) for field in fields}
        def reference_cost(value):
            if core_bodies.is_reference(value):
                return 1, int(value.get('bytes') or 0)
            children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
            costs = [reference_cost(child) for child in children]
            return sum(cost[0] for cost in costs), sum(cost[1] for cost in costs)
        count, size = reference_cost(requested)
        idx.stats['custody_bodies_opened'] += count
        idx.stats['selected_custody_bytes'] = idx.stats.get('selected_custody_bytes', 0) + size
        idx.stats['selected_field_reads'] = idx.stats.get('selected_field_reads', 0) + len(fields)
        return copy.deepcopy(bodies.resolve_fields(requested, Path(root), strict=True))


def artifact_record(root, project, ident):
    """Existing ART owner metadata, qualified by project, without rich history hydration."""
    with _LOCK:
        idx = index(root)
        try:   # THE identity rule: exactly one artifact row of this project and no kind mixing under its ID
            resolved = _family_rows(idx, ident, project=project)
        except AmbiguousRecord:
            raise AmbiguousRecord('Artifact id is ambiguous in this selected project.') from None
        if resolved is None or resolved[0] != 'writing-artifact': return None
        rows = resolved[1]
        _raw_indexed_record(idx, rows[0])
        return {key: copy.deepcopy(rows[0].get(key)) for key in ('id','project','path','artifact_path','scope','sha256','turn_id','ts','custody_degradation','original_metadata') if key in rows[0]}



# Fixed selected journal context, not a second metadata store or a rich fold.
_CONTEXT_FIELDS = ('record','id','project','session_id','turn_id','parent_turn_id',
                   'dispatch_id','provider','model','role','mode','provider_settings')


def _supporting_rows(idx, row, project, *, trace=None):
    """Verify the original rows that grant namespace and actor interpretation (a session through its one family rule)."""
    selected = []
    def original(ident, kind):
        if not ident:
            return None
        # THE same cut-bounded rule (_family_rows) and its declared scope. A writing-session ID is GLOBAL, so it is read
        # across projects (any collision refuses). Immutable kinds are PROJECT-SCOPED: the selected project's own original
        # is resolved first (its duplicates and kind collisions still refuse), so another project's own row of the same ID
        # never masks it (N1). Only when the selected project holds no row is it read across projects, so that a
        # foreign-only original is still found and refused below rather than hidden.
        resolved = _family_rows(idx, ident, project=project) if kind != SESSION_FAMILY and project is not None else None
        if resolved is None:
            resolved = _family_rows(idx, ident)
        if resolved is None or resolved[0] != kind:
            return None
        _family, metas, raws = resolved
        meta = metas[-1]
        value = raws[-1] if raws is not None else _raw_indexed_record(idx, meta)
        if trace is not None:
            trace.append({'record': kind, 'id': ident, 'row_sha256': meta['_hash']})
        selected.append(value)
        return value
    turn = row if row.get('record') == 'writing-turn' else original(row.get('turn_id'), 'writing-turn')
    session = row if row.get('record') == 'writing-session' else original(
        row.get('session_id') or (turn or {}).get('session_id'), 'writing-session')
    namespace = row.get('project') or (turn or {}).get('project') or (session or {}).get('project')
    if namespace != project:
        raise ValueError('The original journal namespace differs from the selected project.')
    for value in selected:
        if value.get('project') and value['project'] != project:
            raise ValueError('The supporting journal row belongs to another project.')
    return selected


def selected_journal(project, ident, root, *, strict=True):
    """One full public row and only verified metadata needed by its presenter.

    The index lock binds selection, supporting row hashes and detachment to one
    cut. A stale cut refuses; the next request may rebuild, never this request.
    """
    with _LOCK:
        idx = index(root)
        raw_id = ident.removeprefix('activity:journal:')
        try:
            resolved = _resolve(idx, project, raw_id)
        except AmbiguousRecord as error:
            raise AmbiguousRecord('This owner record ID is ambiguous; inspect the exact saved turn. ' + str(error)) from None
        if resolved is None:
            return None
        meta, row, _version, related = resolved
        # Parent activity lists the dispatches it launched. Retain only its
        # children through the existing incremental index, without a global scan.
        owning_turn = row if row.get('record') == 'writing-turn' else next(
            (value for value in related if value.get('record') == 'writing-turn'), None)
        if owning_turn is not None:
            for child in idx.by_parent_turn.get(owning_turn.get('id'), ()):
                if idx.project(child) == project:
                    raw = _raw_indexed_record(idx, child)
                    _supporting_rows(idx, raw, project)
                    related.append(raw)
        context = [{key: value[key] for key in _CONTEXT_FIELDS if key in value}
                   for value in related]
        from laplace.representation import writing_bodies as bodies
        row = bodies.resolve_fields(row, Path(root), strict=strict)
        row['_storage_bytes'] = meta['_end'] - meta['_offset']
        return copy.deepcopy((row, meta, context))
