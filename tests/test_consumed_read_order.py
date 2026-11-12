"""CR-R2 (M5 2026-10-15): the selected candidate projection replays the seal's own consumed-read identity sequence.

The warm fold keys each read by [operation, canonical payload]; a key keeps the position its FIRST read gave it,
and the seal hashes the reads in that key order (records._fold._read_basis_digest). The cold selected-record route
(proposal_navigation.selected_records) used to fold only the sealed reads with payloads, so a key first claimed by
a superseded read moved later and the same immutable receipts hashed differently (UNKNOWN identities-disagree).
These controls compare the warm seal with the cold projection on disposable fixtures; the checksum is never
replaced and genuine missing, altered, duplicate or stale receipts still refuse.
"""
from __future__ import annotations

import json

import pytest

from laplace.manuscript import manuscript_proposals as proposals, proposal_navigation as nav
from laplace.native import tools as writing_tools
from laplace.projects import artifacts as writing_artifacts
from laplace.writing import records as writing_records
from laplace.manuscript import proposal_currentness
from laplace.manuscript import source_application
from laplace.writing import session_reads
from laplace.writing.records._fold import _read_basis_digest
from test_proposal_lifecycle import setup
from test_writing_controller import _bind_rewrite_fixture


def _fixture(root, monkeypatch):
    md, turn, changes, _ = setup(root)
    _bind_rewrite_fixture(monkeypatch, md)
    return writing_artifacts.project_root(root, 'fixture'), turn, changes


def _read(root, turn, name):
    return writing_tools.execute(root, 'fixture', 'revise', 'read_artifact', {'path': name, 'scope': 'project'}, turn_id=turn)


def _propose(root, turn, changes, ident, answer='Exact consumed evidence.'):
    writing_records.bank(root, {'record': 'writing-proposal', 'id': ident, 'turn_id': turn, 'project': 'fixture',
                         'proposal': {'answer': answer, 'edits': changes}})
    return session_reads._records(root)['turns'][turn]['pending_proposal_version']


def _sequence(basis):
    return [(read['id'], json.dumps(read.get('payload'), sort_keys=True)) for read in basis['tool_reads'].values()]


def _cold(root, turn, version):
    state = nav.selected_records(root, 'fixture', turn, version)
    return state['turns'][turn]['proposal_bases'][version], state['coverage']


def _same_identity(root, turn, version):
    """The warm seal and the cold selected projection carry one identity sequence that verifies the seal."""
    warm = session_reads._records(root)['turns'][turn]['proposal_bases'][version]
    cold, coverage = _cold(root, turn, version)
    assert _read_basis_digest(warm['tool_reads']) == warm['read_receipts_sha256']
    assert _sequence(cold) == _sequence(warm), 'the seal\'s own identity sequence, aliases and repeats included'
    assert _read_basis_digest(cold['tool_reads']) == cold['read_receipts_sha256'] == warm['read_receipts_sha256']
    assert cold['read_ids'] == warm['read_ids']
    return warm, cold, coverage


def _synthetic_read(root, turn, ident, operation, payload, *, record='writing-tool-read', aliases=None):
    row = {'record': record, 'id': ident, 'turn_id': turn, 'project': 'fixture', 'operation': operation,
           'payload': payload, 'output_sha256': 'sha256:' + ident.encode().hex()[:64].ljust(64, '0')}
    if aliases:
        row['payload_aliases'] = aliases
    writing_records.bank(root, row)


def test_repeated_payloads_interleaved_across_families_replay_in_seal_order_and_stay_current(tmp_path, monkeypatch):
    project, turn, changes = _fixture(tmp_path, monkeypatch)
    for name, text in (('a.json', 'a1'), ('b.json', 'b1'), ('c.json', 'c')):
        (project / name).write_text(text)
    _read(tmp_path, turn, 'a.json')
    _synthetic_read(tmp_path, turn, 'READ-repo-1', 'repository', {'action': 'read', 'path': 'r.txt', 'offset': 0})
    _read(tmp_path, turn, 'b.json')
    _read(tmp_path, turn, 'c.json')
    (project / 'a.json').write_text('a2'); _read(tmp_path, turn, 'a.json')            # repeated payload, later read
    _synthetic_read(tmp_path, turn, 'READ-repo-2', 'repository', {'action': 'read', 'path': 'r.txt'})  # equivalent alias
    (project / 'b.json').write_text('b2'); _read(tmp_path, turn, 'b.json')
    version = _propose(tmp_path, turn, changes, 'PROP-interleaved')
    warm, cold, coverage = _same_identity(tmp_path, turn, version)
    assert len(warm['read_ids']) == 4 and 'READ-repo-2' in warm['read_ids'] and 'READ-repo-1' not in warm['read_ids']
    assert coverage['positional_reads'] == 3, 'only the superseded same-operation reads before the carrier are opened'
    # the public selected route no longer reports the valid receipts as disagreeing identities
    validation = proposals.preview(tmp_path, 'fixture', turn, version)['validation_basis']
    assert 'identities disagree' not in (validation.get('reason') or '')


def test_a_grouped_baseline_alias_interleaved_with_another_family_keeps_its_first_position(tmp_path, monkeypatch):
    project, turn, changes = _fixture(tmp_path, monkeypatch)
    _synthetic_read(tmp_path, turn, 'READ-node', 'concept', {'node': 'same'})
    _synthetic_read(tmp_path, turn, 'READ-research', 'research', {'view': 'summary'})
    _synthetic_read(tmp_path, turn, 'READBASE-grouped', 'concept', {'q': 'new'}, record='writing-tool-read-baseline',
                    aliases=[{'payload': {'node': 'same'}, 'supersedes_read': 'READ-node'}])
    version = _propose(tmp_path, turn, changes, 'PROP-grouped')
    warm, cold, _ = _same_identity(tmp_path, turn, version)
    assert [ident for ident, _ in _sequence(warm)] == ['READBASE-grouped', 'READ-research', 'READBASE-grouped'], \
        'one grouped read appears at its alias\'s first position and again at its own payload'


def test_late_reads_and_a_new_candidate_leave_the_old_seal_verifiable(tmp_path, monkeypatch):
    project, turn, changes = _fixture(tmp_path, monkeypatch)
    (project / 'a.json').write_text('a1'); (project / 'b.json').write_text('b')
    _read(tmp_path, turn, 'a.json'); _read(tmp_path, turn, 'b.json')
    (project / 'a.json').write_text('a2'); _read(tmp_path, turn, 'a.json')
    old = _propose(tmp_path, turn, changes, 'PROP-old')
    old_seal = json.dumps(session_reads._records(tmp_path)['turns'][turn]['proposal_bases'][old], sort_keys=True, default=str)
    (project / 'a.json').write_text('a3'); _read(tmp_path, turn, 'a.json')              # a late read after the old seal
    new = _propose(tmp_path, turn, changes, 'PROP-new', answer='A new candidate on new evidence.')
    assert new != old
    _same_identity(tmp_path, turn, old)
    _same_identity(tmp_path, turn, new)
    assert json.dumps(session_reads._records(tmp_path)['turns'][turn]['proposal_bases'][old], sort_keys=True, default=str) == old_seal


def test_a_terminal_repetition_carrier_selects_the_same_immutable_basis(tmp_path, monkeypatch):
    project, turn, changes = _fixture(tmp_path, monkeypatch)
    (project / 'a.json').write_text('a1'); (project / 'b.json').write_text('b')
    _read(tmp_path, turn, 'a.json'); _read(tmp_path, turn, 'b.json')
    (project / 'a.json').write_text('a2'); _read(tmp_path, turn, 'a.json')
    version = _propose(tmp_path, turn, changes, 'PROP-original')
    writing_records.bank(tmp_path, {'record': 'writing-reply', 'id': 'REPLY-repeat', 'turn_id': turn, 'project': 'fixture',
                             'proposal': {'answer': 'Repeated transport text.', 'edits': changes}})
    rows = [json.loads(line) for line in (tmp_path / 'contract' / 'talk.jsonl').read_text().splitlines()]
    reply = next(row for row in rows if row.get('id') == 'REPLY-repeat')
    assert reply['proposal_carrier']['kind'] == 'terminal-repetition' and reply['proposal_instance_version'] == version
    _same_identity(tmp_path, turn, version)


def _rewrite_journal(root, change):
    """A synthetic edit of the disposable fixture journal only."""
    path = root / 'contract' / 'talk.jsonl'
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows:
        change(row)
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows))


@pytest.mark.parametrize('case', ['altered seal', 'missing receipt', 'duplicate receipt'])
def test_altered_missing_or_duplicate_receipts_still_refuse(tmp_path, monkeypatch, case):
    project, turn, changes = _fixture(tmp_path, monkeypatch)
    (project / 'a.json').write_text('a1'); (project / 'b.json').write_text('b')
    _read(tmp_path, turn, 'a.json'); _read(tmp_path, turn, 'b.json')
    (project / 'a.json').write_text('a2'); _read(tmp_path, turn, 'a.json')
    version = _propose(tmp_path, turn, changes, 'PROP-guarded')
    sealed = session_reads._records(tmp_path)['turns'][turn]['proposal_bases'][version]['read_ids']
    if case == 'altered seal':
        def change(row):
            if row.get('id') == 'PROP-guarded':
                row['proposal_basis']['read_receipts_sha256'] = 'sha256:' + '0' * 64
        said = 'identities disagree'
    elif case == 'missing receipt':
        def change(row):
            if row.get('id') == sealed[-1]:
                row['id'] = 'READ-renamed-elsewhere'
        said = 'unavailable'
    else:
        _synthetic_read(tmp_path, turn, sealed[0], 'research', {'view': 'dup'})
        change = lambda row: None
        said = 'more than one journal row'
    _rewrite_journal(tmp_path, change)
    validation = proposals.preview(tmp_path, 'fixture', turn, version)['validation_basis']
    assert validation['currentness'] != 'CURRENT'
    if said:
        assert said in validation['reason']


def test_stale_consumed_output_and_another_project_still_refuse(tmp_path, monkeypatch):
    project, turn, changes = _fixture(tmp_path, monkeypatch)
    (project / 'a.json').write_text('a1'); (project / 'b.json').write_text('b')
    _read(tmp_path, turn, 'a.json'); _read(tmp_path, turn, 'b.json')
    (project / 'a.json').write_text('a2'); _read(tmp_path, turn, 'a.json')
    version = _propose(tmp_path, turn, changes, 'PROP-stale')
    _same_identity(tmp_path, turn, version)
    (project / 'b.json').write_text('b changed after the seal')
    with pytest.raises(proposal_currentness.ProposalBasisRefused):
        source_application.apply_proposal(tmp_path, {'turn_id': turn, 'proposal_version': version})
    with pytest.raises(ValueError, match='does not belong'):
        nav.selected_records(tmp_path, 'another-project', turn, version)


def test_legacy_read_seal_bytes_are_unchanged_and_new_scope_is_sealed():
    from laplace.writing import reads
    from laplace.writing.records import _fold
    row={"id":"READ-legacy","operation":"research","payload":{"view":"summary"},"output_sha256":"old"}
    prior=_fold._proposal_digest([{k:row.get(k) for k in
        ("id","operation","payload","output_sha256","source_scope")}])
    assert _read_basis_digest({"one":row})==prior
    upgraded={**row,"consumption":{"schema_version":reads.RESEARCH_RECEIPT,"scope":{"project":"fixture"}}}
    assert _read_basis_digest({"one":upgraded})!=prior
    changed={**upgraded,"consumption":{**upgraded["consumption"],"scope":{"project":"foreign"}}}
    assert _read_basis_digest({"one":changed})!=_read_basis_digest({"one":upgraded})


def test_legacy_uuid_sensitive_comparison_is_not_upgraded_by_new_owner_output(tmp_path):
    from test_research_surface import _consumption_project, _summary
    from laplace.writing import reads
    _consumption_project(tmp_path);first=_summary(tmp_path);second=_summary(tmp_path)
    old={"operation":"research","payload":{"view":"summary","project":"fixture"},
         "output_sha256":reads.read_output_digest("research",first)}
    assert reads.comparison_digest("research",second,old,root=tmp_path)!=old["output_sha256"]
    old_seal=_read_basis_digest({"old":old})
    reads.record_read_basis("research",second,old["payload"],project="fixture")
    assert _read_basis_digest({"old":old})==old_seal
    assert "consumption" not in old and "research_raw" not in old


def test_baseline_grouping_never_merges_new_scopes_and_legacy_aliases(tmp_path):
    from laplace.writing import turn_reads
    from laplace.writing import reads
    rows=[{"operation":"research","payload":{"view":"summary"},"output_sha256":"same",
           "supersedes_read":"READ-"+scope,
           "consumption":{"schema_version":reads.RESEARCH_RECEIPT,"scope":{"project":scope}},
           "research_raw":{"project":scope}} for scope in ("a","b")]
    assert turn_reads.bank_read_baseline_groups(tmp_path,"WT-group","fixture","research_record",rows)==2
    banked=[json.loads(x) for x in (tmp_path/"contract/talk.jsonl").read_text().splitlines()]
    assert len(banked)==2
    assert all("consumption" in r and "research_raw" in r for r in banked)
