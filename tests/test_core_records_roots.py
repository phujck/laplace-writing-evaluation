"""laplace.core.records after the move out of the package root: root precedence, the shared row reader and scopes.

The journal and lineage used to derive the checkout from their own file depth; they now resolve it through
laplace.core.checkout.repo_root. These cases pin the precedence: an explicit root wins, the journal's own stores follow
LAPLACE_STATE when no root is given, then LAPLACE_REPO_ROOT, then the source tree.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.engine import engine_ledger
from laplace.core import checkout
from laplace.core.records import journal, lineage, rows


def test_an_explicit_root_wins_over_state_and_the_configured_checkout(tmp_path, monkeypatch):
    monkeypatch.setenv('LAPLACE_STATE', str(tmp_path / 'state'))
    monkeypatch.setenv('LAPLACE_REPO_ROOT', str(tmp_path / 'served'))
    root = tmp_path / 'explicit'
    assert journal._store(root) == root / 'contract' / 'journal.jsonl'
    assert journal._cost_store(root) == root / 'contract' / 'act_costs.jsonl'
    assert lineage._repo_root(root) == root


def test_without_a_root_the_journal_follows_state_and_targets_follow_the_served_checkout(tmp_path, monkeypatch):
    state, served = tmp_path / 'state', tmp_path / 'served'
    (served / 'demo').mkdir(parents=True)
    monkeypatch.setenv('LAPLACE_STATE', str(state))
    monkeypatch.setenv('LAPLACE_REPO_ROOT', str(served))
    assert journal._store() == state / 'journal.jsonl' and journal._cost_store() == state / 'act_costs.jsonl'
    stamped = journal.bank_row('demo/rows.jsonl', {'id': 'R1', 'ts': 'claimed'}, act_id='roots-test')
    assert stamped['ts_claimed'] == 'claimed' and stamped['ts'].endswith('Z')
    assert [json.loads(line)['id'] for line in (served / 'demo/rows.jsonl').read_text().splitlines()] == ['R1']
    phases = [json.loads(line)['phase'] for line in (state / 'journal.jsonl').read_text().splitlines()]
    assert phases == ['begin', 'done']


def test_without_state_the_configured_checkout_holds_the_journal(tmp_path, monkeypatch):
    monkeypatch.delenv('LAPLACE_STATE', raising=False)
    monkeypatch.setenv('LAPLACE_REPO_ROOT', str(tmp_path))
    assert journal._store() == tmp_path.resolve() / 'contract' / 'journal.jsonl'
    assert lineage._repo_root() == tmp_path.resolve()


def test_with_nothing_configured_the_default_is_the_source_tree_root(monkeypatch):
    monkeypatch.delenv('LAPLACE_STATE', raising=False)
    monkeypatch.delenv('LAPLACE_REPO_ROOT', raising=False)
    source_tree = Path(__file__).resolve().parents[1]   # this test's own checkout
    assert checkout.source_tree() == source_tree
    assert journal._root() == source_tree == lineage._repo_root()
    assert (source_tree / 'src' / 'laplace' / 'core' / 'records' / 'journal.py').resolve() == Path(journal.__file__).resolve()


def test_the_row_reader_skips_and_counts_what_is_not_an_object(tmp_path):
    store = tmp_path / 'rows.jsonl'
    store.write_text('{"id": "A"}\n\nnot json\n[1, 2]\n"text"\n{"id": "B"}\n{"torn": \n')
    assert rows.read_rows(store) == ([{'id': 'A'}, {'id': 'B'}], 4)
    assert rows.load_records(store) == [{'id': 'A'}, {'id': 'B'}]
    assert rows.read_rows(tmp_path / 'absent.jsonl') == ([], 0)


def test_a_walk_needs_its_scope_and_a_scope_speaks_only_the_closed_vocabulary(tmp_path):
    with pytest.raises(ValueError, match='scope'):
        lineage.ancestors('ROW', root=tmp_path)
    with pytest.raises(ValueError, match='closed vocabulary'):
        lineage.Scope('bad', ('rows',), legacy_fields={'parent': 'relates-to'})
    (tmp_path / 'rows').mkdir()
    (tmp_path / 'rows' / 'a.jsonl').write_text('{"id": "C", "parent": "P"}\n{"id": "P"}\n')
    plain = lineage.Scope('plain', ('rows',))
    assert lineage.ancestors('C', root=tmp_path, scope=plain)['children'] == []
    typed = lineage.Scope('typed', ('rows',), legacy_fields={'parent': 'part-of'})
    [edge] = lineage.ancestors('C', root=tmp_path, scope=typed)['children']
    assert (edge['id'], edge['rel'], edge['via']) == ('P', 'part-of', 'legacy:parent')
    assert engine_ledger.ROW_GRAPH.store_dirs == ('corpus_friction', 'contract')
