"""Source outline headings show their human title; labels stay identity (M5 2026-10-16, reached Root CUA case).

Root saw ``Quenched representation and influence functional\\label{sec:quenched}\\label{sec:model}`` and
``The Hamiltonian of Mean Force\\label{sec:qubit_closure}`` verbatim in Manuscript navigation. The structure owner
keeps the exact source title for plan matching and adds ``display_title`` (the reader's own flattening) and
``labels``; the reader's head block carries the same labels, so navigation finds its destination. The manuscript
text is never changed. Disposable text only.
"""
from __future__ import annotations

from laplace.manuscript import manuscript_structure, walk
from laplace.manuscript import bindings

TEX = ('\\section{Quenched representation and influence functional\\label{sec:quenched}\\label{sec:model}}\n'
       'Body.\n'
       '\\section{The Hamiltonian of Mean Force\\label{sec:qubit_closure}}\n'
       'Body.\n'
       '\\subsection{Energy $E=\\hbar\\omega$ and $\\{x\\}$ sets}\\label{sub:energy}\\label{sub:e2}\n'
       'Body with \\label{eq:not-a-heading}.\n'
       '\\section{Plain title}\n')


def test_display_titles_drop_labels_and_keep_math_while_source_titles_stay_exact():
    rows = bindings.headings(TEX)
    assert [row['display_title'] for row in rows] == [
        'Quenched representation and influence functional', 'The Hamiltonian of Mean Force',
        'Energy $E=\\hbar\\omega$ and $\\{x\\}$ sets', 'Plain title']
    assert rows[0]['title'] == 'Quenched representation and influence functional\\label{sec:quenched}\\label{sec:model}'


def test_inline_and_consecutive_labels_are_identity_not_title():
    rows = manuscript_structure._heading_rows(TEX)
    assert [row['labels'] for row in rows] == [['sec:quenched', 'sec:model'], ['sec:qubit_closure'], ['sub:energy', 'sub:e2'], []]
    assert [row['label'] for row in rows] == ['sec:quenched', 'sec:qubit_closure', 'sub:energy', None]
    assert 'eq:not-a-heading' not in {label for row in rows for label in row['labels']}, 'body labels are not stolen'


def test_the_reader_head_blocks_carry_the_same_title_and_labels_for_navigation(tmp_path):
    blocks = [block for block in walk.blocks_for(TEX, file_rel='main.tex', repo_file='paper/main.tex', md=tmp_path, corpus='fixture',
                                                 dir_param='', para_spans=[], known_macros=frozenset()) if block.get('kind') == 'head']
    rows = bindings.headings(TEX)
    assert [block['title'] for block in blocks] == [row['display_title'] for row in rows]
    for block, row in zip(blocks, rows):
        assert block.get('labels', []) == row['labels']
        if row['label']:
            assert row['label'] in [block['label'], *block['labels']], 'the outline label finds its rendered destination'


def test_the_served_outline_row_carries_the_display_title_navigation_shows(tmp_path):
    """The trimmed outline LIST row (the one the Manuscript navigation renders) carries display_title beside the exact
    source title; the frontend shows display_title."""
    rows = bindings.outline_rows({'project': 'p'}, {'sources': [{'file': 'main.tex', 'text': TEX}]})
    trimmed = [{key: row.get(key) for key in bindings.OUTLINE_ROW_FIELDS} for row in rows]
    assert [row['display_title'] for row in trimmed][:2] == ['Quenched representation and influence functional', 'The Hamiltonian of Mean Force']
    assert trimmed[0]['title'].endswith('\\label{sec:model}') and trimmed[0]['label'] == 'sec:quenched'
