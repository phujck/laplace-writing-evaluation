"""A stale-evidence refusal names every stale family, where each read moved, and bounded inspect reads."""
import json
import pytest
from laplace.native import tools as writing_tools
from laplace.writing import reads
from laplace.manuscript import proposal_currentness
from laplace.manuscript import source_application
from laplace.writing import session_reads
from test_consumed_read_recovery import seed_reads


def test_basis_index_names_the_selectors_each_owner_publishes():
    visuals = {'specs': [{'id': 'a', 'spec_revision': 'r1', 'currentness': {'status': 'CURRENT'}, 'placement_caption': {'status': 'MATCHES'}, 'render': {'renderer': 'tikz-pdf'}},
                         {'id': 'b', 'spec_revision': 'r2', 'currentness': {'status': 'STALE'}}]}
    index = reads.read_basis_index('visuals', visuals)
    assert set(reads.basis_index_selectors(index)) == {'spec:a', 'currentness:a', 'placement:a', 'render:a', 'spec:b', 'currentness:b'}
    moved = {'specs': [{**visuals['specs'][0], 'spec_revision': 'r9'}, visuals['specs'][1], {'id': 'c', 'spec_revision': 'r3'}]}
    changes = reads.basis_changes(index, reads.read_basis_index('visuals', moved))
    assert changes['changed'] == ['spec:a'] and changes['added'] == ['spec:c'] and changes['removed'] == [] and changes['unchanged'] == 5
    assert reads.bounded_inspect_reads('visuals', {}, changes) == [{'operation': 'visuals', 'payload': {'id': 'a'}}, {'operation': 'visuals', 'payload': {'id': 'c'}}]
    structure = {'schema_version': 'laplace.project-structure/1', 'sections': [{'id': 's1', 'title': 'One', 'job': 'open'}, {'id': 's2', 'title': 'Two'}], 'gaps': []}
    before = reads.read_basis_index('structure', structure)
    after = reads.read_basis_index('structure', {**structure, 'sections': [structure['sections'][0], {'id': 's2', 'title': 'Two, revised'}]})
    changes = reads.basis_changes(before, after)
    assert changes['changed'] == ['section:s2']
    assert reads.bounded_inspect_reads('structure', {'view': 'full'}, changes) == [{'operation': 'structure', 'payload': {'view': 'detail', 'section_ids': ['s2'], 'projection': 'guard'}}]
    document = {'files': [{'file': 'a.tex', 'expected_source_digest': 'sha256:1'}, {'file': 'b.tex', 'expected_source_digest': 'sha256:2'}], 'selected_source': {'revision': 'x'}}
    changes = reads.basis_changes(reads.read_basis_index('document', document),
        reads.read_basis_index('document', {**document, 'files': [document['files'][0], {'file': 'b.tex', 'expected_source_digest': 'sha256:3'}]}))
    assert changes['changed'] == ['file:b.tex'] and reads.bounded_inspect_reads('document', {}, changes) == [{'operation': 'source', 'payload': {'files': ['b.tex']}}]
    uses = {'uses': [{'key': 'doi:10.1/x', 'claim_id': 'claim:a', 'note': 'n'}], 'source_revision': 'r'}
    changes = reads.basis_changes(reads.read_basis_index('literature_uses', uses),
        reads.read_basis_index('literature_uses', {**uses, 'uses': [{**uses['uses'][0], 'note': 'changed'}]}))
    assert changes['changed'] == ['use:doi:10.1/x|claim:a']
    assert reads.bounded_inspect_reads('literature_uses', {}, changes) == [{'operation': 'literature_uses', 'payload': {'key': 'doi:10.1/x', 'limit': 10, 'citation_limit': 10}}]
    assert reads.basis_changes({}, {'a': 'b'}) is None and reads.basis_changes(None, {}) is None


def test_exact_selectors_are_never_truncated_and_coverage_is_declared_under_the_byte_budget():
    """Sol N2: two legal paths that differ after 120 characters, one long path, a saturated index."""
    files = ['chapters/' + ('a' * 110) + '-one.tex', 'chapters/' + ('a' * 110) + '-two.tex']
    before = {'files': [{'file': x, 'expected_source_digest': 'sha256:old'} for x in files]}
    after = {'files': [{'file': files[0], 'expected_source_digest': 'sha256:new'}, before['files'][1]]}
    recorded = reads.read_basis_index('document', before)
    assert set(reads.basis_index_selectors(recorded)) == {'file:' + files[0], 'file:' + files[1]}, 'exact keys, no shared-prefix collision'
    assert recorded[reads.BASIS_COVERAGE_KEY] == {'complete': True, 'indexed': 2, 'omitted': 0, 'budget_bytes': reads.BASIS_INDEX_BYTES, 'budget_entries': reads.BASIS_INDEX_LIMIT}
    changes = reads.basis_changes(recorded, reads.read_basis_index('document', after))
    assert changes['changed'] == ['file:' + files[0]] and changes['unchanged'] == 1 and changes['attributed'] and changes['coverage']['complete'] and not changes['outside_coverage']
    assert reads.bounded_inspect_reads('document', {}, changes) == [{'operation': 'source', 'payload': {'files': [files[0]]}}], 'the inspect read names the recorded file, never a prefix'
    # saturated: 200 long files do not fit the retained byte budget; coverage says so and the diff is truthful
    many = {'files': [{'file': 'chapters/' + 'b' * 100 + str(i) + '.tex', 'expected_source_digest': 'sha256:' + str(i)} for i in range(200)]}
    saturated = reads.read_basis_index('document', many)
    coverage = saturated[reads.BASIS_COVERAGE_KEY]
    assert len(json.dumps(saturated).encode()) <= reads.BASIS_INDEX_BYTES + 400 and coverage['complete'] is False and coverage['indexed'] + coverage['omitted'] == 200
    assert all(key.endswith('.tex') for key in reads.basis_index_selectors(saturated)), 'an indexed selector is always exact'
    moved_outside = {'files': [{**row, 'expected_source_digest': 'sha256:x'} if i == 199 else row for i, row in enumerate(many['files'])]}
    changes = reads.basis_changes(saturated, reads.read_basis_index('document', moved_outside))
    assert changes['changed'] == [] and changes['outside_coverage'] is True and 'exact consulted read' in changes['note']
    assert reads.bounded_inspect_reads('document', {}, changes) == [], 'no bounded read is invented for a change the index did not cover'
    # a change in an un-indexed top-level field (complete coverage, nothing attributed) is also outside coverage
    changes = reads.basis_changes(recorded, reads.read_basis_index('document', {**before, 'other': 1}))
    assert changes['changed'] == [] and changes['added'] == [] and changes['outside_coverage'] is True and changes['coverage']['complete']
    # a receipt from before the coverage marker reads as a legacy complete index
    legacy = {'file:a.tex': '0123456789abcdef'}
    assert reads.basis_index_coverage(legacy)['legacy'] is True and reads.basis_changes(legacy, reads.read_basis_index('document', {'files': [{'file': 'a.tex', 'expected_source_digest': 'z'}]}))['changed'] == ['file:a.tex']


def test_stale_message_names_every_family_and_round_trips():
    changed = [{'operation': 'document'}, {'operation': 'visuals'}, {'operation': 'structure'}, {'operation': 'visuals'}]
    message = reads.stale_evidence_message(changed)
    assert message.startswith('Consulted project evidence changed (document, visuals, structure). 4 consulted reads are no longer current;')
    assert reads.stale_evidence_families(message) == ['document', 'visuals', 'structure']
    assert reads.stale_evidence_families('Consulted project evidence changed (repository). Request a fresh proposal.') == ['repository']
    assert reads.stale_evidence_message([{'operation': 'source'}]).startswith('Consulted project evidence changed (source). consumed_read_recovery')


def test_refusal_carries_changed_selectors_and_inspect_reads_without_replaying_or_renewing(tmp_path, monkeypatch):
    md, turn, version, paths, calls = seed_reads(tmp_path, monkeypatch, 2)
    recorded = session_reads._records(tmp_path)['turns'][turn]['tool_reads']
    assert all(isinstance(read.get('basis_index'), dict) and read['basis_index'] for read in recorded.values()), 'every read receipt retains its basis index'
    paths[0].write_text('Changed evidence.'); paths[1].write_text('Also changed.')
    before = (tmp_path / 'contract/talk.jsonl').read_bytes()
    with pytest.raises(proposal_currentness.ProposalBasisRefused) as refused:
        source_application.apply_proposal(tmp_path, {'turn_id': turn, 'proposal_version': version})
    assert '2 consulted reads are no longer current' in str(refused.value)
    diagnostic = writing_tools.failure_response(tmp_path, 'fixture', 'revise', 'apply_revision', {'turn_id': turn, 'proposal_version': version}, refused.value, turn)
    recovery = diagnostic['consumed_read_recovery']
    assert recovery['observed_changed_read_count'] == 2 and len(recovery['changed_reads']) == 2
    for row in recovery['changed_reads']:
        assert 'content' in row['changed_selectors']['changed'] and 'artifact_path' not in row['changed_selectors']['changed'] and row['changed_selectors']['unchanged'] >= 1
    assert recovery['next_reads'] == [{'operation': 'read_artifact', 'payload': {'path': path.name, 'scope': 'project'}} for path in paths]
    assert recovery['inspect_reads'] == [] and 'renews its witness' in recovery['note']
    assert not calls and (tmp_path / 'contract/talk.jsonl').read_bytes() == before
    assert len(json.dumps(recovery)) < 6500


def test_failure_recovery_reads_repeat_every_stale_family(tmp_path, monkeypatch):
    md, turn, version, paths, calls = seed_reads(tmp_path, monkeypatch, 1)
    result = writing_tools.failure_response(tmp_path, 'fixture', 'revise', 'apply_revision', {'edits': []},
        ValueError('Consulted project evidence changed (read_artifact, literature_scope). Request a fresh proposal.'), turn)
    assert {'operation': 'read_artifact', 'payload': {'path': paths[0].name, 'scope': 'project'}} in result['next_reads']


def test_unicode_selectors_are_budgeted_in_retained_utf8_bytes_with_the_coverage_marker_inside():
    """Sol N2-utf8: legal non-ASCII paths (80 CJK characters per filename, 240 bytes, under the
    255-byte component limit) are counted in the bytes the READ row retains (UTF-8 of the
    ensure_ascii=False dump that journal.bank_row writes), with the coverage marker inside the budget."""
    files = ['chapters/' + '界' * 80 + str(i) + '.tex' for i in range(200)]
    assert all(len(f.split('/')[-1].encode()) <= 255 for f in files)
    index = reads.read_basis_index('document', {'files': [{'file': f, 'expected_source_digest': 'sha256:' + str(i)} for i, f in enumerate(files)]})
    retained = json.dumps(index, ensure_ascii=False, default=str).encode('utf-8')   # journal.bank_row's serialization
    coverage = index[reads.BASIS_COVERAGE_KEY]
    assert len(retained) <= reads.BASIS_INDEX_BYTES == coverage['budget_bytes'], len(retained)
    assert reads.retained_bytes(index) == len(retained)
    assert coverage['complete'] is False and coverage['indexed'] + coverage['omitted'] == 200 and coverage['indexed'] >= 20
    selectors = reads.basis_index_selectors(index)
    assert list(selectors) == ['file:' + f for f in files[:coverage['indexed']]], 'exact keys in owner order, never a truncated prefix'
    # two legal non-ASCII paths that share a long prefix stay distinct exact keys
    pair = ['chapters/' + '界' * 60 + '-一.tex', 'chapters/' + '界' * 60 + '-二.tex']
    before = reads.read_basis_index('document', {'files': [{'file': f, 'expected_source_digest': 'sha256:old'} for f in pair]})
    after = reads.read_basis_index('document', {'files': [{'file': pair[0], 'expected_source_digest': 'sha256:new'}, {'file': pair[1], 'expected_source_digest': 'sha256:old'}]})
    assert before[reads.BASIS_COVERAGE_KEY]['complete'] is True and set(reads.basis_index_selectors(before)) == {'file:' + pair[0], 'file:' + pair[1]}
    changes = reads.basis_changes(before, after)
    assert changes['changed'] == ['file:' + pair[0]] and not changes['outside_coverage']
    assert reads.bounded_inspect_reads('document', {}, changes) == [{'operation': 'source', 'payload': {'files': [pair[0]]}}]
    # a change beyond the saturated index is outside coverage: no narrower read is invented, no witness renewed
    moved = reads.read_basis_index('document', {'files': [{'file': f, 'expected_source_digest': 'sha256:x' if i == 199 else 'sha256:' + str(i)} for i, f in enumerate(files)]})
    outside = reads.basis_changes(index, moved)
    assert outside['changed'] == [] and outside['outside_coverage'] is True and reads.bounded_inspect_reads('document', {}, outside) == []
    # the ASCII closure is unchanged: the same budget, exact keys, saturation declared
    ascii_index = reads.read_basis_index('document', {'files': [{'file': 'chapters/' + 'b' * 100 + str(i) + '.tex', 'expected_source_digest': 'sha256:' + str(i)} for i in range(200)]})
    assert len(json.dumps(ascii_index, ensure_ascii=False).encode()) <= reads.BASIS_INDEX_BYTES and ascii_index[reads.BASIS_COVERAGE_KEY]['complete'] is False
    assert reads.BASIS_COVERAGE_RESERVE < 200
