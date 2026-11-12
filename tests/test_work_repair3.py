"""Repair3 of the Work navigation packet (WORK-source-state-work-repair-20261019; Sol WI-R5b-R1): THE FINAL-OUTPUT
INVARIANT. Every navigation output, or its explicit refusal, fits the retained line as actually emitted: the HTTP body and
the model-facing text of the native door (owner result plus the door's own review_read and read_receipt). Synthetic roots.
"""
from __future__ import annotations

import json

import pytest

from laplace.work import project_work_navigation as nav
from laplace.projects import writing_sources
from laplace.native import tools as writing_tools, verbs as writing_verbs
from test_work_repair2 import LINE, get, make, native, root  # noqa: F401  (the same bounded fixture)


def model_text(value):
    return {provider: len(writing_sources.content_items(value, provider)[0]['text'].encode('utf-8')) for provider in ('claude', 'codex')}


def walk(root, door, **query):
    """Every page of one navigation list through its owner continuations, through one door; (pages, covered positions)."""
    pages, covered = [], []
    while True:
        if door == 'http':
            code, raw, value = get(root, **query)
            assert code == 200, raw[:300]
            size = len(raw)
        else:
            value = native(root, **query);size = max(model_text(value).values())
        pages.append(size);pagination = value['pagination']
        covered += [row['id'] for row in value.get('children') or value.get('roots') or []] + ['#%d' % n['position'] for n in pagination.get('oversized', [])]
        if not pagination['next_read']:
            return pages, covered
        query = {k: v for k, v in pagination['next_read']['payload'].items() if k != 'namespace'}


@pytest.mark.parametrize('parent_bytes', [501, 651, 700, 801, 1201])
def test_an_escaped_identity_singleton_fits_as_emitted_by_both_doors(root, parent_bytes):
    parent, child = 'P' + 'x' * (parent_bytes - 1), 'C' + '\x00' * 1020   # Sol case A at 700, with its bounded neighbours
    make(root, parent, title='parent', goal='parent');make(root, child, title='child', goal='child', parent_work_id=parent)
    code, raw, value = get(root, view='branch', id=parent)
    assert code == 200 and len(raw) <= LINE, len(raw)
    assert max(model_text(native(root, view='branch', id=parent)).values()) <= LINE
    shown = value['children'] + value['pagination'].get('oversized', [])
    assert len(shown) == 1 and value['pagination']['covered'] == 1 and value['pagination']['next_read'] is None
    if value['pagination'].get('oversized'):
        notice = value['pagination']['oversized'][0]
        assert notice['id_bytes'] == len(child.encode()) and notice['id_sha256'].startswith('sha256:'), 'identified, never cut or aliased'
        assert value['pagination']['complete'] is False


@pytest.mark.parametrize('parent_bytes', [901, 1201, 1500, 1801])
def test_native_metadata_is_inside_the_line_and_continuation_covers_every_child(root, parent_bytes):
    parent = 'P' + 'x' * (parent_bytes - 1)                              # Sol case B at 1500, with its bounded neighbours
    make(root, parent, title='parent', goal='parent')
    for n in range(20):
        make(root, 'c%d' % n, title='界' * 160, goal='意' * 200, parent_work_id=parent)
    expected = ['c%d' % n for n in range(20)]
    for door in ('http', 'native'):
        pages, covered = walk(root, door, view='branch', id=parent)
        assert max(pages) <= LINE, (door, pages)
        assert covered == expected, (door, covered)


def test_the_native_line_is_the_exact_size_of_what_the_native_door_adds(root):
    parent = 'P' + 'x' * 1499
    make(root, parent, title='parent', goal='parent');make(root, 'c0', title='child', goal='child', parent_work_id=parent)
    value = native(root, view='branch', id=parent)
    owner = {key: item for key, item in value.items() if key not in {'review_read', 'read_receipt'}}
    added = nav.emitted(value) - nav.emitted(owner)
    act = writing_verbs.classify('project', {'view': 'branch', 'id': parent}, project='p', by='', root=root)
    from laplace.writing import delivery
    assert delivery.inserted({}, writing_tools._read_metadata(root, 'p', 'project', {'view': 'branch', 'id': parent}, 'WT-n', act)) == added


def test_the_original_cases_and_an_unfittable_page_refuse_within_the_line(root):
    make(root, 'W-' + 'x' * 20000, title='Long existing identity', goal='Keep the exact identity')   # repair2 witness stays a notice
    code, raw, page = get(root, view='roots')
    assert code == 200 and len(raw) <= LINE and page['pagination']['oversized'][0]['id_bytes'] == 20002
    big = 'B-' + 'x' * 20000;make(root, big);make(root, 'child', parent_work_id=big)
    code, raw, value = get(root, view='branch', id=big)
    assert code == 422 and len(raw) <= LINE and 'cannot be delivered within its' in value['error']
    with pytest.raises(nav.OutputRefused):
        native(root, view='branch', id=big)
