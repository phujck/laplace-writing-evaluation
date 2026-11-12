import pytest
from laplace.manuscript import project_protocol
from laplace.projects import library as writing_projects
from laplace.writing import operating as writing_operating
from laplace.native import tools as writing_tools
from laplace.pipeline import authoring, projection_spec


def test_guide_is_reloaded_for_sessions_and_invalidates_consumed_proposals(tmp_path):
    status, _ = writing_projects.create({'name':'guide-book','title':'Synthetics','kind':'book'},tmp_path)
    assert status == 201
    project=tmp_path/'synthetics papers/guide-book'
    guide=project/'WORKING_GUIDE.md';guide.write_text('Inputs must be pinned before running.\n')
    projection_spec.write_spec('guide-book',{'manuscript':{'working_guides':['WORKING_GUIDE.md']}},tmp_path)
    first=writing_operating.build('guide-book','work',tmp_path)
    context=authoring.build_context('guide-book',{'files':['chapters/chapter-01.tex']},tmp_path)
    assert 'Inputs must be pinned' in context['prompt']
    guide.write_text('Inputs and imported code must be pinned before running.\n')
    resumed=writing_operating.build('guide-book','work',tmp_path)
    assert first['project_protocol']['revision'] != resumed['project_protocol']['revision']
    assert 'imported code' in resumed['project_protocol']['documents'][0]['content']
    row=next(r for r in authoring.inspect('guide-book',repo_root=tmp_path)['stale'] if r['context_id']==context['context_id'])
    assert 'project-working-guide-changed' in row['reasons']
    guide.unlink()
    with pytest.raises(ValueError,match='missing'):
        writing_operating.build('guide-book','work',tmp_path)
    projection_spec.write_spec('guide-book',{'manuscript':{'working_guides':['../../outside.md']}},tmp_path)
    with pytest.raises(ValueError,match='inside its project'):
        writing_operating.build('guide-book','work',tmp_path)


def test_guide_roles_keep_handoff_discoverable_but_out_of_default_context(tmp_path):
    for name in ('first-book', 'second-book'):
        status, _ = writing_projects.create({'name':name, 'title':name, 'kind':'book'}, tmp_path)
        assert status == 201
    first = tmp_path / 'synthetics papers/first-book'
    second = tmp_path / 'synthetics papers/second-book'
    (first / 'WORKING_GUIDE.md').write_text('Pin inputs before execution.\n')
    (first / 'CURRENT.md').write_text('Dated handoff: private prior status.\n')
    (first / 'BACKGROUND.md').write_text('Historical rationale only.\n')
    (second / 'WORKING_GUIDE.md').write_text('Second project instructions.\n')
    projection_spec.write_spec('first-book', {'manuscript': {'working_guides': [
        {'path':'WORKING_GUIDE.md', 'role':'instructions'},
        {'path':'CURRENT.md', 'role':'handoff'},
        {'path':'BACKGROUND.md', 'role':'background'}]}}, tmp_path)
    projection_spec.write_spec('second-book', {'manuscript': {
        'working_guides':['WORKING_GUIDE.md']}}, tmp_path)

    brief = writing_operating.build('first-book', 'work', tmp_path)
    rendered = writing_operating.prompt(brief)
    documents = brief['project_protocol']['documents']
    assert documents[0]['content'] == 'Pin inputs before execution.\n'
    assert 'content' not in documents[1] and 'content' not in documents[2]
    assert 'private prior status' not in rendered and 'Historical rationale' not in rendered
    catalogue = writing_tools.execute(tmp_path, 'first-book', 'work', 'project_guidance', {})
    assert all('content' not in row for row in catalogue['documents'])
    exact = writing_tools.execute(tmp_path, 'first-book', 'work', 'project_guidance', {'path':'CURRENT.md'})
    assert exact['role'] == 'handoff' and 'private prior status' in exact['content']
    other = writing_tools.execute(tmp_path, 'second-book', 'work', 'project_guidance', {})
    assert [row['path'] for row in other['documents']] == ['WORKING_GUIDE.md']
    with pytest.raises(ValueError, match='configured'):
        writing_tools.execute(tmp_path, 'second-book', 'work', 'project_guidance', {'path':'CURRENT.md'})


def test_handoff_change_does_not_stale_unconsumed_context_or_resume(tmp_path):
    status, _ = writing_projects.create({'name':'role-book', 'title':'Roles', 'kind':'book'}, tmp_path)
    assert status == 201
    project = tmp_path / 'synthetics papers/role-book'
    instruction = project / 'WORKING_GUIDE.md'
    handoff = project / 'CURRENT.md'
    instruction.write_text('Keep the qualification.\n')
    handoff.write_text('Prior session status A.\n')
    projection_spec.write_spec('role-book', {'manuscript': {'working_guides': [
        {'path':'WORKING_GUIDE.md', 'role':'instructions'},
        {'path':'CURRENT.md', 'role':'handoff'}]}}, tmp_path)
    first = writing_operating.build('role-book', 'work', tmp_path)
    context = authoring.build_context('role-book', {'files':['chapters/chapter-01.tex']}, tmp_path)
    assert 'Prior session status A' not in context['prompt']

    handoff.write_text('Prior session status B.\n')
    resumed = writing_operating.build('role-book', 'work', tmp_path)
    assert resumed['project_protocol']['revision'] == first['project_protocol']['revision']
    assert resumed['project_protocol']['catalog_revision'] != first['project_protocol']['catalog_revision']
    assert writing_operating.orientation_delta(first, resumed)['changed'] is False
    assert not any(row['context_id'] == context['context_id']
                   for row in authoring.inspect('role-book', repo_root=tmp_path)['stale'])

    instruction.write_text('Keep the qualification and exact source.\n')
    changed = writing_operating.build('role-book', 'work', tmp_path)
    delta = writing_operating.orientation_delta(resumed, changed)
    assert delta['changed'] is True
    assert 'exact source' in delta['guidance']['project_protocol']['documents'][0]['content']
    row = next(row for row in authoring.inspect('role-book', repo_root=tmp_path)['stale']
               if row['context_id'] == context['context_id'])
    assert 'project-working-guide-changed' in row['reasons']


def test_project_guidance_tool_configures_roles_and_writes_with_exact_guards(tmp_path):
    status, _ = writing_projects.create({'name':'guide-tool', 'title':'Guide Tool', 'kind':'book'}, tmp_path)
    assert status == 201
    project = tmp_path / 'synthetics papers/guide-tool'
    guide = project / 'CURRENT.md'
    guide.write_text('Old handoff.\n')
    projection_spec.write_spec('guide-tool', {'manuscript': {'working_guides':['CURRENT.md']}}, tmp_path)
    help_value = writing_tools.execute(tmp_path, 'guide-tool', 'work', 'help', {
        'operation':'project_guidance_change'})['action']
    # D2 help sections (input inline limit 600 since M5 2026-10-16): a larger input is its summary plus one exact read
    schema = help_value.get('input') or writing_tools.execute(tmp_path, 'guide-tool', 'work', 'help', {
        'operation':'project_guidance_change', 'section':'input'})['action']['value']
    assert help_value['input_summary']['required'] == schema['required'] if 'input_summary' in help_value else True
    assert schema['properties']['operation']['enum'] == ['configure', 'write']
    assert schema['required'] == ['operation', 'expected_catalog_revision']
    current = writing_tools.execute(tmp_path, 'guide-tool', 'work', 'project_guidance', {})
    configured = writing_tools.execute(tmp_path, 'guide-tool', 'work', 'project_guidance_change', {
        'operation':'configure', 'expected_catalog_revision':current['catalog_revision'],
        'guides':[{'path':'CURRENT.md', 'role':'handoff'}]})
    assert configured['documents'][0]['role'] == 'handoff'
    assert 'content' not in configured['documents'][0]
    exact = writing_tools.execute(tmp_path, 'guide-tool', 'work', 'project_guidance', {'path':'CURRENT.md'})
    saved = writing_tools.execute(tmp_path, 'guide-tool', 'work', 'project_guidance_change', {
        'operation':'write', 'expected_catalog_revision':exact['catalog_revision'],
        'path':'CURRENT.md', 'before':exact['content'], 'content':'New handoff.\n'})
    assert saved['document']['content'] == 'New handoff.\n'
    with pytest.raises(ValueError, match='changed'):
        writing_tools.execute(tmp_path, 'guide-tool', 'work', 'project_guidance_change', {
            'operation':'write', 'expected_catalog_revision':exact['catalog_revision'],
            'path':'CURRENT.md', 'before':'Old handoff.\n', 'content':'Lost update.\n'})


def test_model_preferences_are_project_backed_and_validate_discovered_choices(tmp_path,monkeypatch):
    from laplace.work import project_work
    from laplace.writing import provider as writing_provider
    writing_projects.create({'name':'model-book','title':'Models','kind':'book'},tmp_path)
    monkeypatch.setattr(writing_provider,'capabilities',lambda root:{'providers':[{'id':'codex','available':True,'models':[{'id':'available-model','efforts':['low','medium']}]}]})
    saved=project_work.session_preferences('model-book',{'provider':'codex','model':'available-model','effort':'low'},tmp_path)
    assert project_work.session_preferences('model-book',repo_root=tmp_path)==saved
    with pytest.raises(ValueError,match='advertised model'):
        project_work.session_preferences('model-book',{'provider':'codex','model':'unavailable-model','effort':'low'},tmp_path)
    with pytest.raises(ValueError,match='supported effort'):
        project_work.session_preferences('model-book',{'provider':'codex','model':'available-model','effort':'ultra'},tmp_path)


def test_title_named_book_remains_available_to_the_concept_viewer(tmp_path):
    from laplace.research import concepts as concepts_surface, corpus_ingest
    status,made=writing_projects.create({'name':'named-book','title':'Synthetics','kind':'book'},tmp_path)
    assert status==201
    root_file=tmp_path/made['source']['root']
    assert root_file.name=='Synthetics.tex'
    assert not root_file.with_name('main.tex').exists()
    preamble=root_file.with_name('preamble.tex');preamble.write_text('\\usepackage{amsmath}\n')
    root_file.write_text(root_file.read_text().replace('\\begin{document}','\\input{preamble}\n\\begin{document}'))
    corpus_ingest._CORPUS_CACHE.clear()
    tree=concepts_surface.tree('named-book',root=tmp_path)
    assert tree['current']['id']=='paper://'
    assert all(n['id']!='sec:preamble' for n in tree['children'])
