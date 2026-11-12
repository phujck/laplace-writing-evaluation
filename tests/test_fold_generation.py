"""The derived session/turn fold follows its journal's generation (M5 S3).

records._fold._records reuses a cached projection only for the journal generation it was folded from; the
generation is the existing metadata index's observation of the file (records._index.MetadataIndex). Before
this, a journal recreated at the same path with an equal or larger size kept the old projection, and
authoring_surface._bank sealed a new reply's proposal_basis with the OLD turn's context. These tests drive the
real sealer and fold on disposable roots: no real history, provider or source effect.
"""
import json
import shutil

import pytest

from laplace.writing import records as writing_records
from laplace.writing.records import _fold


def _seed(root, context, *, turn='WT-g', session='WS-g', reply='WR-g'):
    """One session, one turn consuming `context`, one reply whose proposal_basis the real _bank seals."""
    writing_records.bank(root, {'record': 'writing-session', 'id': session, 'project': 'fixture', 'title': 'Generation'})
    writing_records.bank(root, {'record': 'writing-turn', 'id': turn, 'session_id': session, 'project': 'fixture',
                                   'text': 'Revise the opening.', 'context_id': context})
    writing_records.bank(root, {'record': 'writing-reply', 'id': reply, 'turn_id': turn, 'session_id': session,
                                   'project': 'fixture', 'proposal': {'edits': [{'file': 'main.tex', 'old': 'a', 'new': 'b'}]}})


def _rows(root):
    return [json.loads(line) for line in (root / 'contract' / 'talk.jsonl').read_text().splitlines() if line.strip()]


def _sealed(root, reply='WR-g'):
    return next(row for row in _rows(root) if row.get('id') == reply)['proposal_basis']['context_id']


@pytest.mark.parametrize('extra', [False, True], ids=['equal-size', 'larger'])
def test_a_journal_recreated_at_the_same_path_is_folded_afresh_and_seals_its_own_context(tmp_path, extra):
    root = tmp_path / 'project'
    root.mkdir()
    _seed(root, 'CTX-old')
    assert _sealed(root) == 'CTX-old' and _fold._records(root)['turns']['WT-g']['context_id'] == 'CTX-old'
    raw = (root / 'contract' / 'talk.jsonl').read_text(encoding='utf-8')
    shutil.rmtree(root)
    (root / 'contract').mkdir(parents=True)
    # the same path, identifiers and row boundaries; a context of the same length, so the recreated journal is
    # exactly the old size (or that plus one appended row): the old fold offset lands on a row boundary
    recreated = raw.replace('CTX-old', 'CTX-new')
    if extra:
        recreated += json.dumps({'record': 'writing-steer', 'id': 'WSTEER-x', 'turn_id': 'WT-g', 'project': 'fixture', 'text': 'more'}) + '\n'
    (root / 'contract' / 'talk.jsonl').write_text(recreated, encoding='utf-8')
    assert len(recreated) >= len(raw)
    assert _fold._records(root)['turns']['WT-g']['context_id'] == 'CTX-new'
    writing_records.bank(root, {'record': 'writing-reply', 'id': 'WR-g2', 'turn_id': 'WT-g', 'session_id': 'WS-g',
                                   'project': 'fixture', 'proposal': {'edits': [{'file': 'main.tex', 'old': 'b', 'new': 'c'}]}})
    assert _sealed(root, 'WR-g2') == 'CTX-new', 'a new reply is sealed with the recreated turn context, never the old fold'


def test_a_journal_rewritten_in_place_with_a_changed_prefix_is_folded_afresh(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    _seed(root, 'CTX-old')
    _fold._records(root)
    journal = root / 'contract' / 'talk.jsonl'
    rows = _rows(root)
    rows[1]['context_id'] = 'CTX-rewritten-longer'
    with journal.open('r+', encoding='utf-8') as stream:   # same inode, rewritten prefix, larger size
        stream.seek(0)
        stream.write(''.join(json.dumps(row) + '\n' for row in rows))
        stream.truncate()
    assert _fold._records(root)['turns']['WT-g']['context_id'] == 'CTX-rewritten-longer'


def test_a_journal_that_disappeared_leaves_no_projection_to_reuse(tmp_path):
    root = tmp_path / 'project'
    root.mkdir()
    _seed(root, 'CTX-old')
    assert 'WT-g' in _fold._records(root)['turns']
    shutil.rmtree(root / 'contract')
    state = _fold._records(root)
    assert state['turns'] == {} and state['sessions'] == {} and state['offset'] == 0


def test_another_root_never_contributes_its_context(tmp_path):
    first, second = tmp_path / 'one', tmp_path / 'two'
    first.mkdir()
    second.mkdir()
    _seed(first, 'CTX-one')
    _seed(second, 'CTX-two')
    assert _sealed(first) == 'CTX-one' and _sealed(second) == 'CTX-two'
    assert _fold._records(first)['turns']['WT-g']['context_id'] == 'CTX-one'


def test_an_ordinary_append_keeps_the_generation_reads_only_the_suffix_and_never_renews_an_old_seal(tmp_path, monkeypatch):
    root = tmp_path / 'project'
    root.mkdir()
    _seed(root, 'CTX-first')
    state = _fold._records(root)
    generation, offset = state.get('generation'), state['offset']
    folded = []
    original = _fold._fold_record
    monkeypatch.setattr(_fold, '_fold_record', lambda state, row, root: (folded.append(row.get('id')), original(state, row, root)))
    writing_records.bank(root, {'record': 'writing-turn', 'id': 'WT-h', 'session_id': 'WS-g', 'project': 'fixture',
                                   'text': 'Second turn.', 'context_id': 'CTX-second'})
    after = _fold._records(root)
    assert after.get('generation') is generation and after['offset'] > offset, 'an append is the same generation'
    assert folded == ['WT-h'], 'only the appended row is folded'
    assert after['turns']['WT-g']['context_id'] == 'CTX-first' and _sealed(root) == 'CTX-first', 'the earlier seal is unchanged'
