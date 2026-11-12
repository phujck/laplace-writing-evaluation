"""Bounded visuals reads: the index list and exact per-figure detail beside the whole catalogue."""
import copy
import json
import pytest

from laplace.research import visuals_surface
from laplace.native import tools as writing_tools
from test_visual_tool_contracts import project, call, help_for


def size(value):
    return len(json.dumps(value, ensure_ascii=False).encode())


def specs(root, count, start=0):
    made = []
    for index in range(start, start + count):
        payload = copy.deepcopy(help_for(root, 'visual_create')['examples']['plot'])
        payload['spec']['id'] = 'figure-' + str(index); payload['spec']['title'] = 'Figure ' + str(index)
        made.append(call(root, 'visual_create', payload)['spec']['id'])
    call(root, 'visual_render', {'id': made[0]})
    return made


def test_index_rows_carry_the_catalogue_identities_and_detail_matches_the_catalogue_entry(tmp_path):
    project(tmp_path); ids = specs(tmp_path, 3)
    catalogue = call(tmp_path, 'visuals', {})
    index = call(tmp_path, 'visuals', {'view': 'index'})
    assert index['schema_version'] == 'laplace.visuals-index/1' and index['specs']['total'] == 3
    by_id = {row['id']: row for row in catalogue['specs']}
    for row in index['specs']['items']:
        full = by_id[row['id']]
        assert row['spec_revision'] == full['spec_revision'] and row['render_freshness'] == full['render_freshness']
        assert row['currentness']['drawing_freshness'] == full['currentness']['drawing_freshness']
        assert row['placement']['status'] == full['placement_caption']['status']
        assert 'tikz' not in row and 'caption' not in row and 'output_digests' not in row['currentness']
    assert index['specs']['items'][0]['render']['renderer'] == 'matplotlib'
    detail = call(tmp_path, 'visuals', index['specs']['items'][1]['detail_read']['payload'])
    assert detail['specs'] == [by_id[ids[1]]] and detail['selection'] == {'view': 'detail', 'ids': [ids[1]]} and detail['catalogue_total'] == 3
    several = call(tmp_path, 'visuals', {'ids': [ids[2], ids[0]]})
    assert [row['id'] for row in several['specs']] == [ids[2], ids[0]]
    assert size(index) < size(catalogue) and size(detail) < size(catalogue)
    # HTTP serves the same selectors through the query string
    for query, native in ((({'project': ['visual-lab'], 'view': ['index']}), index), ({'project': ['visual-lab'], 'id': [ids[1]]}, detail)):
        code, _, raw = visuals_surface.handle('/visuals/state', query, 'GET', b'', repo_root=tmp_path)
        assert code == 200 and json.loads(raw) == native
    # the whole catalogue is unchanged in shape
    assert set(catalogue) == {'specs', 'authority', 'renderers', 'style'}


def test_index_pages_with_a_cut_and_a_changed_catalogue_refuses_the_continuation(tmp_path):
    project(tmp_path); ids = specs(tmp_path, 3)
    first = call(tmp_path, 'visuals', {'view': 'index', 'limit': 2})
    assert [row['id'] for row in first['specs']['items']] == ids[:2] and first['specs']['omitted_after'] == 1
    second = call(tmp_path, 'visuals', first['specs']['next_read']['payload'])
    assert [row['id'] for row in second['specs']['items']] == ids[2:] and 'next_read' not in second['specs']
    bare = call(tmp_path, 'visuals', {'limit': 2})
    assert bare['specs']['items'] == first['specs']['items'], 'offset/limit alone select the index'
    specs(tmp_path, 1, start=3)
    with pytest.raises(ValueError, match='CHANGED_INPUT'):
        call(tmp_path, 'visuals', first['specs']['next_read']['payload'])


def test_unknown_or_conflicting_selectors_refuse_with_the_index_route(tmp_path):
    project(tmp_path); ids = specs(tmp_path, 1)
    with pytest.raises(ValueError, match='spec'):
        call(tmp_path, 'visuals', {'id': 'figure-missing'})
    with pytest.raises(ValueError, match='view:index'):
        call(tmp_path, 'visuals', {'view': 'index', 'id': ids[0]})
    with pytest.raises(ValueError):
        call(tmp_path, 'visuals', {'ids': ['f' + str(i) for i in range(9)]})
    with pytest.raises(ValueError):
        call(tmp_path, 'visuals', {'view': 'everything'})
    code, _, raw = visuals_surface.handle('/visuals/state', {'project': ['visual-lab'], 'id': ['figure-missing']}, 'GET', b'', repo_root=tmp_path)
    assert code == 404 and json.loads(raw)['read'] == {'operation': 'visuals', 'payload': {'view': 'index'}}


def test_visual_failures_recover_through_the_exact_figure_read(tmp_path):
    project(tmp_path); ids = specs(tmp_path, 1)
    response = writing_tools.failure_response(tmp_path, 'visual-lab', 'work', 'visual_render', {'id': ids[0]}, ValueError('Visual spec revision conflict'))
    assert {'operation': 'visuals', 'payload': {'id': ids[0]}} in response['next_reads']
    assert {'operation': 'visuals', 'payload': {}} not in response['next_reads']
    assert 'view:index' in writing_tools.execute(tmp_path, 'visual-lab', 'work', 'help', {'operation': 'visuals'})['action']['does']
