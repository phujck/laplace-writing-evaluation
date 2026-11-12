from __future__ import annotations
import hashlib
import json
from pathlib import Path

from laplace.manuscript import blocks as manuscript_blocks
from laplace.projects import library as writing_projects
from laplace.native import tools as writing_tools
from laplace.core import checkout


def _fixture(root: Path):
    source=root/'source'; source.mkdir()
    figure='\\begin{figure}\n\\centering\n\\includegraphics{figures/a.pdf}\n\\caption{A figure.}\n\\label{fig:a}\n\\end{figure}'
    (source/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n\\input{chapter}\n\\input{other}\n\\end{document}\n')
    (source/'chapter.tex').write_text('Anchor.\n'+figure+'\nTail.\n')
    (source/'other.tex').write_text('Other anchor.\n')
    (source/'figures').mkdir(); (source/'figures'/'a.pdf').write_bytes(b'%PDF')
    (source/'manuscript_spec.json').write_text(json.dumps({'figure_specs':[{'id':'a','section':'chapter.tex',
        'section_scope':'manuscript','section_repo_file':'source/chapter.tex'}]}))
    status,row=writing_projects.import_source({'name':'blocks','title':'Blocks','root':'source/main.tex','editable':True},root)
    assert status==201,row
    return source,figure


def _digest(path): return 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()


def test_generated_figure_move_cross_file_and_undo_is_grouped(tmp_path):
    source,figure=_fixture(tmp_path); main,other=source/'chapter.tex',source/'other.tex'
    result=manuscript_blocks.change(tmp_path,'blocks',{'operation':'move','block':{
        'file':'chapter.tex','line_start':2,'line_end':7,'before':figure,'expected_source_digest':_digest(main)},
        'destination':{'file':'other.tex','line':1,'before':'Other anchor.','expected_source_digest':_digest(other)}})
    assert result['ok'] and figure not in main.read_text() and figure in other.read_text()
    assert len(result['edits'])==2 and result['undo']['operation']=='undo'
    undone=manuscript_blocks.change(tmp_path,'blocks',result['undo'])
    assert undone['ok'] and figure in main.read_text() and figure not in other.read_text()


def test_move_refuses_changed_destination_without_touching_origin(tmp_path):
    source,figure=_fixture(tmp_path); main,other=source/'chapter.tex',source/'other.tex'
    stale=_digest(other); other.write_text('Concurrent destination.\n')
    try:
        manuscript_blocks.change(tmp_path,'blocks',{'operation':'move','block':{
            'file':'chapter.tex','line_start':2,'line_end':7,'before':figure,'expected_source_digest':_digest(main)},
            'destination':{'file':'other.tex','line':1,'before':'Concurrent destination.','expected_source_digest':stale}})
    except ValueError as exc:
        assert 'destination expected_source_digest' in str(exc)
    else: raise AssertionError('stale destination accepted')
    assert figure in main.read_text()


def test_cross_file_move_rolls_back_destination_when_origin_write_fails(tmp_path, monkeypatch):
    source,figure=_fixture(tmp_path); main,other=source/'chapter.tex',source/'other.tex'
    real=manuscript_blocks._rewrite
    def fail_origin(manuscript, project, path, before, after, note):
        if path.name=='chapter.tex' and note.startswith('Move'):
            raise ValueError('planted origin failure')
        return real(manuscript,project,path,before,after,note)
    monkeypatch.setattr(manuscript_blocks,'_rewrite',fail_origin)
    try:
        manuscript_blocks.change(tmp_path,'blocks',{'operation':'move','block':{
            'file':'chapter.tex','line_start':2,'line_end':7,'before':figure,'expected_source_digest':_digest(main)},
            'destination':{'file':'other.tex','line':1,'before':'Other anchor.','expected_source_digest':_digest(other)}})
    except ValueError as exc:
        assert 'planted origin failure' in str(exc)
    else: raise AssertionError('origin failure accepted')
    assert figure in main.read_text() and figure not in other.read_text()


def test_delete_removes_whole_figure_but_keeps_asset(tmp_path):
    source,figure=_fixture(tmp_path); main=source/'chapter.tex'
    result=manuscript_blocks.change(tmp_path,'blocks',{'operation':'delete','block':{
        'file':'chapter.tex','line_start':2,'line_end':7,'before':figure,'expected_source_digest':_digest(main)}})
    assert result['block']['kind']=='figure' and figure not in main.read_text()
    assert (source/'figures'/'a.pdf').read_bytes()==b'%PDF'
    assert result['placement']['id']=='a' and result['placement']['after']['section'] is None
    manuscript_blocks.change(tmp_path,'blocks',result['undo'])
    restored=json.loads((source/'manuscript_spec.json').read_text())['figure_specs'][0]
    assert restored['section']=='chapter.tex'


def test_partial_source_read_returns_full_file_guard_consumed_by_block_change(tmp_path):
    source,figure=_fixture(tmp_path);main=source/'chapter.tex'
    read=writing_tools.execute(tmp_path,'blocks','work','source',{
        'files':['chapter.tex'],'line_start':2,'line_end':7})
    selected=read['sources'][0]

    assert selected['text']==figure+'\n'
    assert selected['expected_source_digest']==_digest(main)
    # `raw_file_sha256` was deleted as a second name for `sha256`; the `source-file` home is
    # published once, under that one name and as the token beside it.
    assert selected['sha256']==hashlib.sha256(main.read_bytes()).hexdigest()
    home='source-file:blocks::'+selected['file']
    assert selected['identities'][home]=='rev:'+home+':'+selected['sha256']
    changed=writing_tools.execute(tmp_path,'blocks','work','block_change',{'operation':'delete','block':{
        'file':'chapter.tex','line_start':2,'line_end':7,'before':figure,
        'expected_source_digest':selected['expected_source_digest']}})
    assert changed['ok'] and figure not in main.read_text()


def test_cut_clip_inserts_atomically_at_guarded_destination(tmp_path):
    source,figure=_fixture(tmp_path); main,other=source/'chapter.tex',source/'other.tex'
    cut=manuscript_blocks.change(tmp_path,'blocks',{'operation':'delete','block':{
        'file':'chapter.tex','line_start':2,'line_end':7,'before':figure,'expected_source_digest':_digest(main)}})
    pasted=manuscript_blocks.change(tmp_path,'blocks',{'operation':'insert','clip':cut['clip'],
        'destination':{'file':'other.tex','line':1,'before':'Other anchor.','expected_source_digest':_digest(other)}})
    assert figure in other.read_text() and pasted['block']['label']=='fig:a'
    manuscript_blocks.change(tmp_path,'blocks',pasted['undo'])
    assert figure not in other.read_text()


def test_cut_paste_at_inline_styled_caret_and_grouped_undo(tmp_path):
    source,figure=_fixture(tmp_path);main,other=source/'chapter.tex',source/'other.tex'
    paragraph=r'Start \emph{bright world} and $x^2$ end.'
    other.write_text(paragraph+'\n');original_main=main.read_text();original_other=other.read_text()
    cut=manuscript_blocks.change(tmp_path,'blocks',{'operation':'delete','block':{'file':'chapter.tex','line_start':2,'line_end':7,'before':figure,'expected_source_digest':_digest(main)}})
    pasted=manuscript_blocks.change(tmp_path,'blocks',{'operation':'insert-at-caret','clip':cut['clip'],
        'destination':{'file':'other.tex','line':0,'expected_source_digest':_digest(other),
            'paragraph':{'line_start':1,'line_end':1,'before':paragraph,'offset':paragraph.index('world')}}})
    assert other.read_text()==r'Start \emph{bright }'+'\n\n'+figure+'\n\n'+r'\emph{world} and $x^2$ end.'+'\n'
    assert pasted['anchor']['line_start']==3
    grouped={'operation':'undo','edits':pasted['edits']+cut['edits'],
        'placement':{**pasted['placement'],'before':cut['placement']['before']}}
    manuscript_blocks.change(tmp_path,'blocks',grouped)
    assert main.read_text()==original_main and other.read_text()==original_other


def test_caret_split_refuses_math_comment_and_unknown_macro_interiors():
    import pytest
    for text,offset in [(r'Before $x^2$ after',len(r'Before $x')),('Words % hidden comment',10),(r'Before \mystery{body} after',len(r'Before \mystery{bo'))]:
        with pytest.raises(ValueError):manuscript_blocks.split_inline_paragraph(text,offset)
    left,right=manuscript_blocks.split_inline_paragraph(r'A \textbf{bold \emph{inner text}} after',len(r'A \textbf{bold \emph{inner '))
    assert left==r'A \textbf{bold \emph{inner }}' and right==r'\textbf{\emph{text}} after'


def test_compact_object_undo_rejoins_existing_corrections_and_restores_spec(tmp_path):
    source,figure=_fixture(tmp_path);main,other=source/'chapter.tex',source/'other.tex'
    result=manuscript_blocks.change(tmp_path,'blocks',{'operation':'move','block':{
        'file':'chapter.tex','line_start':2,'line_end':7,'before':figure,'expected_source_digest':_digest(main)},
        'destination':{'file':'other.tex','line':1,'before':'Other anchor.','expected_source_digest':_digest(other)}})
    assert set(result['undo_ref'])=={'kind','id','project'}
    files=result['owned_changes']['files']
    assert {row['path'] for row in files}=={'source/chapter.tex','source/other.tex','source/manuscript_spec.json'}
    assert all(row['after_sha256']==row['observed_after_sha256'] for row in files)
    lazy=manuscript_blocks.undo_record(tmp_path,'blocks',result['undo_ref']['id'])
    assert lazy['undo']==result['undo']
    undone=manuscript_blocks.change(tmp_path,'blocks',lazy['undo'])
    assert figure in main.read_text() and figure not in other.read_text()
    redone=manuscript_blocks.change(tmp_path,'blocks',undone['undo'])
    assert figure not in main.read_text() and figure in other.read_text()
    assert redone['owned_changes']['files']


def test_structural_undo_http_route_has_exact_receipt_and_project_guard(tmp_path,monkeypatch):
    from laplace.web import authoring as authoring_surface
    source,figure=_fixture(tmp_path);main=source/'chapter.tex'
    result=manuscript_blocks.change(tmp_path,'blocks',{'operation':'delete','block':{
        'file':'chapter.tex','line_start':2,'line_end':7,'before':figure,'expected_source_digest':_digest(main)}})
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    query={'project':['blocks'],'kind':['block'],'id':[result['undo_ref']['id']]}
    status,_,raw=authoring_surface.handle('/authoring/structural-undo',query,'GET',b'')
    assert status==200 and json.loads(raw)['undo']==result['undo']
    status,_,raw=authoring_surface.handle('/authoring/structural-undo',{**query,'project':['foreign']},'GET',b'')
    assert status==409 and 'no completed object change' in json.loads(raw)['error']
    status,_,raw=authoring_surface.handle('/authoring/structural-undo',{**query,'kind':['unknown']},'GET',b'')
    assert status==409 and 'block or section' in json.loads(raw)['error']


def test_real_http_recovers_compact_agent_inverse_then_undo_and_redo(tmp_path,monkeypatch):
    from http.server import ThreadingHTTPServer
    import threading
    from urllib.request import Request,urlopen
    from urllib.parse import urlencode
    from laplace.web import scanner
    from laplace.manuscript import review_surface
    source,figure=_fixture(tmp_path);main=source/'chapter.tex'
    monkeypatch.setattr(scanner,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    monkeypatch.setattr(review_surface,'_repo_root',lambda:tmp_path)
    changed=manuscript_blocks.change(tmp_path,'blocks',{'operation':'delete','block':{
        'file':'chapter.tex','line_start':2,'line_end':7,'before':figure,'expected_source_digest':_digest(main)}})
    server=ThreadingHTTPServer(('127.0.0.1',0),scanner.make_handler())
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    try:
        with urlopen(base+'/authoring/structural-undo?'+urlencode(changed['undo_ref']),timeout=5) as response:
            inverse=json.load(response)
        def post(payload):
            request=Request(base+'/authoring/block-change',json.dumps({'project':'blocks',**payload}).encode(),headers={'Content-Type':'application/json','X-Laplace-Writing':'1'})
            with urlopen(request,timeout=5) as response:return json.load(response)
        restored=post(inverse['undo']);assert figure in main.read_text()
        post(restored['undo']);assert figure not in main.read_text()
    finally:
        server.shutdown();thread.join(timeout=5);server.server_close()


def test_atomic_block_in_document_root_uses_the_same_content_mask_as_reader(tmp_path):
    source,figure=_fixture(tmp_path);main=source/'main.tex'
    (source/'chapter.tex').write_text('Chapter body.\n')
    original=main.read_text().replace('\\end{document}',figure+'\n\\end{document}')
    main.write_text(original);at=original.split('\n').index('\\begin{figure}')+1
    changed=manuscript_blocks.change(tmp_path,'blocks',{'operation':'delete','block':{
        'file':'main.tex','line_start':at,'line_end':at+len(figure.split('\n'))-1,
        'before':figure,'expected_source_digest':_digest(main)}})
    assert figure not in main.read_text() and '\\begin{document}' in main.read_text()
    manuscript_blocks.change(tmp_path,'blocks',changed['undo']);assert main.read_text()==original


def test_returned_repository_source_coordinates_move_exact_parser_block_and_undo(tmp_path):
    from laplace.manuscript import walk
    source, figure = _fixture(tmp_path)
    origin, destination = source/'chapter.tex', source/'other.tex'
    original = '% spacer\n'*10 + '% PLACE: existing-figure\n' + figure + '\\clearpage\nTail.\n'
    origin.write_text(original)
    before_destination = destination.read_text()
    read = writing_tools.execute(tmp_path, 'blocks', 'work', 'source', {
        'files':['chapter.tex'], 'line_start':12, 'line_end':17})['sources'][0]
    target = writing_tools.execute(tmp_path, 'blocks', 'work', 'source', {
        'files':['other.tex']})['sources'][0]
    parsed = next(row for row in walk.blocks_for(origin.read_text(),
        file_rel='chapter.tex', repo_file=read['file'], md=source,
        corpus='blocks', dir_param='', para_spans=[], known_macros=frozenset())
        if row['kind']=='figure')
    assert parsed['src']['line_start']==12 and parsed['src']['line_end']==17
    assert parsed['tex']==read['text'].removesuffix('\n')
    assert read['file']=='source/chapter.tex' and target['file']=='source/other.tex'
    payload = {'operation':'move', 'block':{
        'file':read['file'], 'line_start':parsed['src']['line_start'],
        'line_end':parsed['src']['line_end'], 'before':parsed['tex'],
        'expected_source_digest':read['expected_source_digest']},
        'destination':{'file':target['file'], 'line':1, 'before':target['text'].split('\n')[0],
            'expected_source_digest':target['expected_source_digest']}}
    import pytest
    # The reached caller's preceding PLACE comment is not part of this atomic block.
    with pytest.raises(ValueError, match='whole atomic'):
        writing_tools.execute(tmp_path, 'blocks', 'work', 'block_change', {
            **payload, 'block':{**payload['block'], 'line_start':11,
                'before':'% PLACE: existing-figure\n'+parsed['tex']}})
    assert origin.read_text()==original and destination.read_text()==before_destination
    changed = writing_tools.execute(tmp_path, 'blocks', 'work', 'block_change', payload)
    assert changed['ok'] and parsed['tex'] not in origin.read_text()
    assert parsed['tex'] in destination.read_text()
    restored = writing_tools.execute(tmp_path, 'blocks', 'work', 'block_change', changed['undo'])
    assert origin.read_text()==original and destination.read_text()==before_destination
    redone = writing_tools.execute(tmp_path, 'blocks', 'work', 'block_change', restored['undo'])
    assert parsed['tex'] not in origin.read_text() and parsed['tex'] in destination.read_text()
    writing_tools.execute(tmp_path, 'blocks', 'work', 'block_change', redone['undo'])
    assert origin.read_text()==original and destination.read_text()==before_destination
    origin.write_text(original+'Changed unrelated tail.\n')
    with pytest.raises(ValueError, match='expected_source_digest.*current'):
        writing_tools.execute(tmp_path, 'blocks', 'work', 'block_change', payload)
    assert destination.read_text()==before_destination


def test_block_coordinates_keep_selected_membership_and_path_fences(tmp_path):
    import pytest
    source, _ = _fixture(tmp_path)
    from laplace.manuscript import manuscript_source, manuscript_structure
    canonical = source/'chapter.tex'
    for value in ['chapter.tex', 'source/chapter.tex']:
        assert manuscript_blocks._path(tmp_path,'blocks',value)[2]==canonical
        assert manuscript_structure._source_path(tmp_path,source,value)==canonical
    (source/'unselected.tex').write_text('Not included.\n')
    sibling = tmp_path/'source-other'; sibling.mkdir()
    (sibling/'chapter.tex').write_text('Wrong manuscript.\n')
    (source/'outside.tex').symlink_to(sibling/'chapter.tex')
    for value in [str(canonical), '../source/chapter.tex', 'source/../source/chapter.tex',
                  'unselected.tex', 'source/unselected.tex', 'source-other/chapter.tex',
                  'outside.tex', 'source/outside.tex', 'missing.tex', '']:
        with pytest.raises(ValueError, match='not in the selected manuscript source'):
            manuscript_blocks._path(tmp_path,'blocks',value)
    # Preserve structure's existing repository-first precedence, without basename search.
    (tmp_path/'chapter.tex').write_text('Repository collision outside manuscript.\n')
    with pytest.raises(ValueError, match='escapes the selected manuscript'):
        manuscript_source.source_path(tmp_path,source,'chapter.tex')
    with pytest.raises(ValueError, match='not in the selected manuscript source'):
        manuscript_blocks._path(tmp_path,'blocks','chapter.tex')
    assert manuscript_blocks._path(tmp_path,'blocks','source/chapter.tex')[2]==canonical


def test_native_undo_null_placement_roundtrip_and_current_help(tmp_path):
    from laplace.native import declarations as writing_declarations
    source, figure = _fixture(tmp_path)
    (source/'manuscript_spec.json').write_text(json.dumps({'figure_specs':[]}))
    original = (source/'chapter.tex').read_text()
    deleted = writing_tools.execute(tmp_path,'blocks','work','block_change',{'operation':'delete',
        'block':{'file':'source/chapter.tex','line_start':2,'line_end':7,'before':figure,
                 'expected_source_digest':_digest(source/'chapter.tex')}})
    assert 'placement' in deleted['undo'] and deleted['undo']['placement'] is None
    restored = writing_tools.execute(tmp_path,'blocks','work','block_change',deleted['undo'])
    assert (source/'chapter.tex').read_text()==original
    writing_tools.execute(tmp_path,'blocks','work','block_change',restored['undo'])
    assert figure not in (source/'chapter.tex').read_text()
    schema = writing_declarations.owner_input_schema('block_change')
    assert schema['oneOf'][1]['required']==['operation','edits','placement']
    assert schema['oneOf'][1]['properties']['placement']==manuscript_blocks.undo_input_contract()['properties']['placement']
    help_read=writing_tools.help_response(tmp_path,'blocks','work',{'operation':'block_change'})
    assert 'missing or partial legacy metadata requires reinspection' in json.dumps(help_read)


def test_undo_refuses_missing_partial_extra_or_wrong_project_without_effect(tmp_path):
    import copy
    import pytest
    source,figure=_fixture(tmp_path);main=source/'chapter.tex';spec=source/'manuscript_spec.json'
    changed=writing_tools.execute(tmp_path,'blocks','work','block_change',{'operation':'delete',
        'block':{'file':'source/chapter.tex','line_start':2,'line_end':7,'before':figure,
                 'expected_source_digest':_digest(main)}})
    mutations=[lambda p:p.pop('placement'),lambda p:p['placement'].pop('after'),
        lambda p:p['placement']['after'].pop('section_scope'),
        lambda p:p['placement']['before'].update(render={'path':'unrelated.py'}),
        lambda p:p['placement'].update(unrelated='value'),
        lambda p:p['edits'][0].update(unrelated='value'),
        lambda p:p['edits'][0].update(after=None),
        lambda p:p.update(expected=[{}]),lambda p:p.update(unrelated='value'),
        lambda p:p.update(project='OTHER')]
    before=(main.read_bytes(),spec.read_bytes())
    for index,mutate in enumerate(mutations):
        payload=copy.deepcopy(changed['undo']);mutate(payload)
        with pytest.raises(ValueError):
            writing_tools.execute(tmp_path,'blocks','work','block_change',payload)
        # a malformed canonical guard is refused by the one entry rule before the undo owner reads anything (D-R1)
        with pytest.raises(ValueError,match="canonical guard is malformed" if index==7 else 'Undo|undo'):
            manuscript_blocks.change(tmp_path,'blocks',payload)
        assert (main.read_bytes(),spec.read_bytes())==before
    with pytest.raises(ValueError,match='reinspect the recorded structural Undo'):
        manuscript_blocks.change(tmp_path,'blocks',{'operation':'undo','edits':changed['edits']})


def test_native_undo_stale_source_or_placement_refuses_before_any_effect(tmp_path):
    import pytest
    source,figure=_fixture(tmp_path);main=source/'chapter.tex';other=source/'other.tex'
    moved=writing_tools.execute(tmp_path,'blocks','work','block_change',{'operation':'move',
        'block':{'file':'source/chapter.tex','line_start':2,'line_end':7,'before':figure,'expected_source_digest':_digest(main)},
        'destination':{'file':'source/other.tex','line':1,'before':'Other anchor.','expected_source_digest':_digest(other)}})
    spec=source/'manuscript_spec.json';data=json.loads(spec.read_text());data['figure_specs'][0]['section']='current-unrelated.tex';spec.write_text(json.dumps(data))
    before=(main.read_bytes(),other.read_bytes(),spec.read_bytes())
    with pytest.raises(ValueError,match='visual placement changed'):
        writing_tools.execute(tmp_path,'blocks','work','block_change',moved['undo'])
    assert (main.read_bytes(),other.read_bytes(),spec.read_bytes())==before
    data['figure_specs'][0]['section']=moved['placement']['after']['section'];spec.write_text(json.dumps(data))
    main.write_text(main.read_text()+'External source edit.\n')
    before=(main.read_bytes(),other.read_bytes(),spec.read_bytes())
    with pytest.raises(ValueError,match='object changed since this operation'):
        writing_tools.execute(tmp_path,'blocks','work','block_change',moved['undo'])
    assert (main.read_bytes(),other.read_bytes(),spec.read_bytes())==before


def test_real_http_undo_keeps_project_and_expected_guard(tmp_path,monkeypatch):
    from http.server import ThreadingHTTPServer
    from urllib.request import Request,urlopen
    from urllib.error import HTTPError
    import threading
    from laplace.web import scanner
    from laplace.manuscript import review_surface
    from laplace.core import identity_doors
    source,figure=_fixture(tmp_path);main=source/'chapter.tex'
    monkeypatch.setattr(scanner,'_repo_root',lambda:tmp_path)
    monkeypatch.setattr(checkout, 'repo_root',lambda:tmp_path)
    monkeypatch.setattr(review_surface,'_repo_root',lambda:tmp_path)
    original=main.read_bytes()
    changed=writing_tools.execute(tmp_path,'blocks','work','block_change',{'operation':'delete',
        'block':{'file':'source/chapter.tex','line_start':2,'line_end':7,'before':figure,'expected_source_digest':_digest(main)}})
    home='blocks::'+changed['undo']['edits'][0]['file']
    expected=list(identity_doors.identities(('source-file',home,main.read_bytes())).values())
    server=ThreadingHTTPServer(('127.0.0.1',0),scanner.make_handler())
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(server.server_port)
    def post(payload):
        request=Request(base+'/authoring/block-change',json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-Laplace-Writing':'1'})
        with urlopen(request,timeout=5) as response:return json.load(response)
    try:
        before=main.read_bytes()
        stale=[expected[0].rsplit(':',1)[0]+':'+('0'*64)]
        with __import__('pytest').raises(HTTPError) as refusal:
            post({'project':'blocks',**changed['undo'],'expected':stale})
        assert refusal.value.code==409 and main.read_bytes()==before
        assert json.load(refusal.value)['refused']['kind']=='identity-stale'
        restored=post({'project':'blocks',**changed['undo'],'expected':expected})
        assert restored['ok'] and main.read_bytes()==original
    finally:
        server.shutdown();thread.join(timeout=5);server.server_close()
