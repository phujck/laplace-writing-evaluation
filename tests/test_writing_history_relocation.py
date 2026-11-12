"""Work bank and act receipts survive relocation (history store relocation, 2026-10-16).

The 21-project re-export dropped 1,274 bank rows and 14 act rows: their recorded store was the ORIGINAL checkout's
absolute work_orders.jsonl, which only the exact current root could relate. A published export now supplies the
original roots it records (verified by pin, published_lineage) for that lexical match; the match must still equal an
exact selected ledger file plus row id. Every hop carries the roots, and a re-export refuses to drop history its
published export selected. Disposable fixtures only; the original root is never read.
"""
from __future__ import annotations

import json
import shutil

import pytest

from test_writing_release_portability import _portable_first, exporter, verifier
from test_writing_eval_manifest import fixture, rows


def _source(tmp_path):
    root = tmp_path / 'source'; root.mkdir(); fixture(root); _portable_first(root)
    original = root.resolve()
    work = str(original / 'corpus_friction/work_orders.jsonl')
    journal = (root / 'contract/journal.jsonl').read_text()
    extra = [{'record': 'act', 'act_id': 'B', 'actor': 'ambient-bank'},
             {'record': 'bank', 'act_id': 'B', 'store': work, 'row_id': 'WO1'},                       # original absolute, selected row
             {'record': 'act_end', 'act_id': 'B'},
             {'record': 'bank', 'act_id': 'F', 'store': 'corpus_friction/work_orders.jsonl', 'row_id': 'WO1'},   # relative
             {'record': 'bank', 'act_id': 'C', 'store': work, 'row_id': 'WO2'},                       # another project's row
             {'record': 'bank', 'act_id': 'D', 'store': '/elsewhere/checkout/corpus_friction/work_orders.jsonl', 'row_id': 'WO1'},
             {'record': 'bank', 'act_id': 'E', 'store': str(original / 'soul/work_orders.jsonl'), 'row_id': 'WO1'}]
    (root / 'contract/journal.jsonl').write_text(journal + ''.join(json.dumps(row) + '\n' for row in extra))
    return root, original


def _banks(export):
    return sorted(line for line in (export / 'contract/journal.jsonl').read_text().splitlines()
                  if json.loads(line).get('act_id') in {'B', 'C', 'D', 'E', 'F'})


WANTED = {('act', 'B'), ('bank', 'B'), ('act_end', 'B'), ('bank', 'F')}


def test_original_root_banks_and_acts_travel_through_three_hops_without_reading_the_original_host(tmp_path):
    root, original = _source(tmp_path)
    first = tmp_path / 'first'
    exporter.export_projects(root, first, ['first'])
    selected = _banks(first)
    assert {(json.loads(line)['record'], json.loads(line)['act_id']) for line in selected} == WANTED, 'C/D/E stay out'
    shutil.rmtree(root)   # the original checkout is gone: selection is lexical, never a host read
    second = tmp_path / 'second'
    exporter.export_projects(first, second, ['first'])
    assert _banks(second) == selected, 'byte-identical bank and act rows after relocation'
    index = json.loads((second / 'writing-portability.json').read_text())['directory_aliases']
    assert index == {str(first.resolve()): '.', str(original): '.'}, 'the original root is carried'
    third = tmp_path / 'third'
    exporter.export_projects(second, third, ['first'])
    assert _banks(third) == selected, 'the second hop does not lose the original address'
    for export in (first, second, third):
        assert verifier.verify(export)['ok'], export


def test_a_re_export_that_would_drop_published_history_refuses_before_any_copy(tmp_path, monkeypatch):
    root, _original = _source(tmp_path)
    first = tmp_path / 'first'
    exporter.export_projects(root, first, ['first'])
    real = exporter.inventory._journal_store_key
    monkeypatch.setattr(exporter.inventory, '_journal_store_key', lambda base, value, recorded_roots=(): real(base, value))  # the old rule
    target = tmp_path / 'second'
    with pytest.raises(ValueError, match=r'would drop 3 history row\(s\) the published export selected for first \(contract/journal\.jsonl: 3\)'):
        exporter.export_projects(first, target, ['first'])
    assert not target.exists()


def test_recorded_roots_come_only_from_a_verified_published_export(tmp_path):
    root, original = _source(tmp_path)
    assert exporter.inventory.published_lineage(root.resolve()) is None, 'an ordinary checkout records no other root'
    first = tmp_path / 'first'
    exporter.export_projects(root, first, ['first'])
    lineage = exporter.inventory.published_lineage(first.resolve())
    assert lineage['roots'] == [str(original)]
    index = first / 'writing-portability.json'
    value = json.loads(index.read_text()); value['directory_aliases']['/forged/root'] = '.'
    index.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='published portability provenance changed'):
        exporter.export_projects(first, tmp_path / 'second', ['first'])
    assert not (tmp_path / 'second').exists()


def test_store_keys_match_only_exact_roots_never_suffixes():
    from pathlib import Path
    key = exporter.inventory._journal_store_key
    root = Path('/export/root')
    assert key(root, '/original/root/corpus_friction/work_orders.jsonl', ['/original/root']) == 'corpus_friction/work_orders.jsonl'
    assert key(root, '/other/original/root/corpus_friction/work_orders.jsonl', ['/original/root']) is None, 'no suffix match'
    assert key(root, '/original/rootling/corpus_friction/work_orders.jsonl', ['/original/root']) is None
    assert key(root, '/original/root/../x/work_orders.jsonl', ['/original/root']) is None
    assert key(root, 'corpus_friction/work_orders.jsonl', ['/original/root']) == 'corpus_friction/work_orders.jsonl'


# ---------------------------------------------------------------------------------------------- repair1 (Sol HS-R1)

def _repin_index(first):
    import hashlib
    path = first / 'release/export-manifest.json'; report = json.loads(path.read_text())
    row = next(item for item in report['derived_files'] if item['path'] == 'writing-portability.json')
    raw = (first / 'writing-portability.json').read_bytes()
    row['sha256'] = 'sha256:' + hashlib.sha256(raw).hexdigest(); row['bytes'] = len(raw)
    path.write_text(json.dumps(report))


@pytest.mark.parametrize('case,match', [
    ('index-schema', 'refused by its owner: unknown portable source manifest'),
    ('oversized-index', 'refused by its owner: portable source manifest exceeds size limit'),
    ('report-schema', 'unknown published export manifest')])
def test_lineage_admits_only_the_owners_index_and_a_known_export_report_even_when_internally_repinned(tmp_path, case, match):
    root, _original = _source(tmp_path)
    first = tmp_path / 'first'
    exporter.export_projects(root, first, ['first'])
    if case == 'report-schema':
        path = first / 'release/export-manifest.json'; value = json.loads(path.read_text())
        value['schema'] = 'unknown.export/99'; path.write_text(json.dumps(value))
    else:
        index = first / 'writing-portability.json'; value = json.loads(index.read_text())
        if case == 'index-schema':
            value['schema'] = 'unknown.portability/99'
        else:
            value['pad'] = 'x' * (4 * 1024 * 1024)   # the reader's unchanged 4 MiB guard
        index.write_text(json.dumps(value)); _repin_index(first)
    with pytest.raises(ValueError, match=match):
        exporter.inventory.published_lineage(first.resolve())
    with pytest.raises(ValueError, match=match):
        exporter.export_projects(first, tmp_path / 'again', ['first'])
    assert not (tmp_path / 'again').exists()


def test_a_symlinked_published_index_is_refused_before_any_open_of_its_target(tmp_path, monkeypatch):
    from pathlib import Path
    root, _original = _source(tmp_path)
    first = tmp_path / 'first'
    exporter.export_projects(root, first, ['first'])
    index = first / 'writing-portability.json'
    outside = tmp_path / 'outside-metadata.json'; outside.write_bytes(index.read_bytes())
    index.unlink(); index.symlink_to(outside)
    opened, real = [], Path.open
    monkeypatch.setattr(Path, 'open', lambda self, *a, **k: (opened.append(str(self)), real(self, *a, **k))[1])
    with pytest.raises(ValueError, match='symlink input refused: writing-portability.json'):
        exporter.inventory.published_lineage(first.resolve())
    assert not [path for path in opened if path.endswith(('writing-portability.json', 'outside-metadata.json'))], opened
    with pytest.raises(ValueError, match='symlink input refused'):
        exporter.export_projects(first, tmp_path / 'again', ['first'])
    assert not (tmp_path / 'again').exists()
