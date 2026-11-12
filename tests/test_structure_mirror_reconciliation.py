"""Multiply placed nodes: the eligibility rule and the reconciler must agree on the FIRST placement."""
import json
from pathlib import Path
import pytest

from laplace.research import corpus_ingest
from laplace.manuscript import project_structure, storyboard


def fixture(root: Path):
    """A node placed in two sections whose plan LIST order differs from document (outline) order:
    sections [A chapter, C chapter, B section under A]; X is placed in C and in B."""
    manuscript = root / 'book' / 'manuscript'; manuscript.mkdir(parents=True)
    (root / 'registry_projects.json').write_text(json.dumps({'projects': [{
        'name': 'book', 'kind': 'conceptric', 'project_dir': 'book', 'tex_root': 'book/manuscript',
        'manifest': {'document': {'root': 'book/manuscript/main.tex'}}}]}))
    (root / 'corpus').mkdir(); (root / 'corpus/corpus.bib').write_text('')
    (manuscript / 'main.tex').write_text('\\documentclass{book}\n\\begin{document}\n\\input{A}\n\\input{B}\n\\input{C}\n\\end{document}\n')
    for name, heading in (('A', '\\chapter{Alpha}'), ('B', '\\section{Beta}'), ('C', '\\chapter{Gamma}')):
        (manuscript / (name + '.tex')).write_text(heading + '\\label{source-' + name + '}\nProse.\n')
    plan = {'meta': {'project': 'book', 'target_dir': 'book/manuscript'}, 'sections': [
        {'id': 'A', 'title': 'Alpha', 'kind': 'chapter', 'job': 'open', 'source_file': 'book/manuscript/A.tex', 'source_label': 'source-A', 'beats': ['beat:a'], 'nodes_in_order': ['beat:a'], 'refs': []},
        {'id': 'C', 'title': 'Gamma', 'kind': 'chapter', 'job': 'close', 'source_file': 'book/manuscript/C.tex', 'source_label': 'source-C', 'beats': ['beat:c'], 'nodes_in_order': ['beat:c', 'def:x'], 'refs': []},
        {'id': 'B', 'title': 'Beta', 'kind': 'section', 'parent_id': 'A', 'job': 'support', 'source_file': 'book/manuscript/B.tex', 'source_label': 'source-B', 'beats': ['beat:b'], 'nodes_in_order': ['beat:b', 'def:x'], 'refs': []},
    ], 'appendices': []}
    (manuscript / 'projection_plan.json').write_text(json.dumps(plan, indent=2))
    for ident, kind in (('beat:a', 'result'), ('beat:b', 'result'), ('beat:c', 'result'), ('def:x', 'definition')):
        assert not corpus_ingest.rewire_add(root, 'book', {'kind': 'add-node', 'node': ident, 'node_kind': kind, 'essence': ident, 'by': 'fixture'}).get('error')
    for order, ident in enumerate(('beat:a', 'beat:b', 'beat:c')):
        assert not corpus_ingest.rewire_add(root, 'book', {'kind': 'set-spine', 'node': ident, 'ord': order, 'narrative': 'beat', 'by': 'fixture'}).get('error')
    return manuscript


def mirror_gaps(value):
    return [gap for gap in value['gaps'] if gap['kind'] == 'mirror']


def test_reconciler_and_eligibility_agree_on_document_order_first_placement(tmp_path):
    fixture(tmp_path)
    first = storyboard.reconcile_section_refs('book', tmp_path)
    assert first['ok'] and first['unanchored'] == 0
    # document order is A, B (under A), C: the first placement of def:x is B, so its mirror is beat:b
    assert [row['section_ref'] for row in first['deltas'] if row['node'] == 'def:x'] == ['beat:b']
    full = project_structure.state('book', tmp_path)
    assert full['status'] == 'AVAILABLE' and full['eligible_for_authoring'] is True and mirror_gaps(full) == []
    # idempotent: a second run emits nothing and eligibility holds
    assert storyboard.reconcile_section_refs('book', tmp_path)['emitted'] == 0
    assert project_structure.state('book', tmp_path)['eligible_for_authoring'] is True


def test_scoped_detail_reports_the_same_mirror_eligibility_as_the_full_read(tmp_path):
    fixture(tmp_path)
    # a stale mirror (pointing at the later placement's anchor) is INELIGIBLE on the full read ...
    assert not corpus_ingest.rewire_add(tmp_path, 'book', {'kind': 'set-projection', 'node': 'def:x', 'value': {'section_ref': 'beat:c'}, 'by': 'fixture'}).get('error')
    full = project_structure.state('book', tmp_path)
    assert full['eligible_for_authoring'] is False and [gap['id'] for gap in mirror_gaps(full)] == ['def:x']
    assert mirror_gaps(full)[0]['expected_section_ref'] == 'beat:b' and mirror_gaps(full)[0]['section_id'] == 'B'
    # ... and a detail read scoped to the OTHER placement must not call the plan eligible
    scoped = project_structure.read('book', {'view': 'detail', 'section_ids': ['C']}, tmp_path)
    assert scoped['eligible_for_authoring'] is False
    summary = project_structure.read('book', {'view': 'summary'}, tmp_path)
    assert summary['eligible_for_authoring'] is None and summary['eligibility_scope'].startswith('NOT_ASSESSED')
    # the reconciler repairs exactly that mirror and the full read agrees
    repaired = storyboard.reconcile_section_refs('book', tmp_path)
    assert [(row['node'], row['was'], row['section_ref']) for row in repaired['deltas']] == [('def:x', 'beat:c', 'beat:b')]
    assert project_structure.state('book', tmp_path)['eligible_for_authoring'] is True
