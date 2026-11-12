import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const generated = spawnSync('./scripts/laplace-python', ['-c', String.raw`
import json,sys,tempfile
from pathlib import Path
import pytest
from jsonschema import Draft202012Validator
sys.path.insert(0,'tests')
from test_reader_restructure import case,split_draft,apply
from laplace.manuscript import reader_restructure as owner
from laplace.manuscript import manuscript_source,projection_viewer,walk
monkey=pytest.MonkeyPatch()
with tempfile.TemporaryDirectory(prefix='laplace-reader-restructure-ui-') as raw:
    make=getattr(case,'__wrapped__',None) or case._get_wrapped_function()
    fixture=make(Path(raw),monkey)
    root,_,source=fixture
    before=source.read_bytes()
    draft=split_draft(fixture)
    resolution=manuscript_source.resolve('book',repo_root=root)
    model=walk.blocks_for(source.read_text(),file_rel=source.relative_to(fixture[1]).as_posix(),repo_file=source.relative_to(root).as_posix(),md=fixture[1],corpus='book',dir_param='',known_macros=frozenset(),para_spans=projection_viewer.parse_paragraphs(source.read_text()))
    sections=[{'blocks':model}]
    owner.annotate_walk('book',root,sections,resolution,manuscript_source.traversal(resolution['root'],root))
    block=next(row for row in model if row.get('tex')==draft['source_edits'][0]['before'])
    preview=owner.preview('book','first','presentation-split',draft,root)
    request={**preview['apply_action']['payload'],'project':'book','draft':draft}
    Draft202012Validator(owner.contracts()).validate(request)
    assert source.read_bytes()==before
    complete=apply(fixture,preview)
    after_model=walk.blocks_for(source.read_text(),file_rel=source.relative_to(fixture[1]).as_posix(),repo_file=source.relative_to(root).as_posix(),md=fixture[1],corpus='book',dir_param='',known_macros=frozenset(),para_spans=projection_viewer.parse_paragraphs(source.read_text()))
    owner.annotate_walk('book',root,[{'blocks':after_model}],resolution,manuscript_source.traversal(resolution['root'],root))
    undone=owner.change('book',complete['undo_action']['payload'],root)
    assert source.read_bytes()==before
    partial_preview=owner.preview('book','first','presentation-split',split_draft(fixture),root)
    target=owner._snapshot('book','first',root)['paths']['provenance'];store=owner._store
    with monkey.context() as outage:
        def fail(project,root,path,*args,**kwargs):
            if path==target:raise OSError('Simulated provenance publication failure')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail)
        partial=apply(fixture,partial_preview)
    physical=source.read_bytes()
    from laplace.manuscript import manuscript_structure
    with monkey.context() as recovery_guard:
        recovery_guard.setattr(manuscript_structure,'_write_source',lambda *args,**kwargs:pytest.fail('Metadata recovery replayed source'))
        recovered=owner.change('book',partial['recovery_action']['payload'],root)
    assert source.read_bytes()==physical
    multipart=[]
    for count in (3,12):
        many=make(Path(raw)/('parts-'+str(count)),monkey)
        many_root,_,many_source=many
        many_source.write_text(many_source.read_text().replace('% first-p1\nFirst sentence.', '% first-p1\n% first-p2\nFirst sentence.',1))
        original=many_source.read_bytes()
        many_draft=split_draft(many)
        many_draft['paragraph_ids']=['first-p1','first-p2']
        many_draft['parts']=['Authored paragraph '+str(index)+'.' for index in range(count)]
        many_draft['source_edits'][0].update(line_start=5,line_end=5,after='\n\n'.join(many_draft['parts']))
        many_preview=owner.preview('book','first','presentation-split',many_draft,many_root)
        many_request={**many_preview['apply_action']['payload'],'project':'book','draft':many_draft}
        Draft202012Validator(owner.contracts()).validate(many_request)
        many_complete=apply(many,many_preview)
        many_resolution=manuscript_source.resolve('book',repo_root=many_root)
        many_blocks=walk.blocks_for(many_source.read_text(),file_rel=many_source.relative_to(many[1]).as_posix(),repo_file=many_source.relative_to(many_root).as_posix(),md=many[1],corpus='book',dir_param='',known_macros=frozenset(),para_spans=projection_viewer.parse_paragraphs(many_source.read_text()))
        owner.annotate_walk('book',many_root,[{'blocks':many_blocks}],many_resolution,manuscript_source.traversal(many_resolution['root'],many_root))
        many_undo=owner.change('book',many_complete['undo_action']['payload'],many_root)
        assert many_source.read_bytes()==original
        empty_draft=split_draft(many)
        empty_draft['paragraph_ids']=['first-p1','first-p2']
        empty_draft['parts']=['Authored paragraph.','','Unfinished paragraph.']
        empty_draft['source_edits'][0].update(line_start=5,line_end=5,after='\n\n'.join(empty_draft['parts']))
        try:
            owner.preview('book','first','presentation-split',empty_draft,many_root)
        except ValueError as error:
            empty_refusal=str(error)
        else:raise AssertionError('An empty unfinished draft was silently applied')
        assert many_source.read_bytes()==original
        multipart.append({'draft':many_draft,'preview':many_preview,'complete':many_complete,'after_blocks':many_blocks,'undone':many_undo,'empty_refusal':empty_refusal})
    legacy_case=make(Path(raw)/'legacy-feedback',monkey)
    legacy_root,legacy_home,legacy_source=legacy_case
    feedback=legacy_home/'feedback/feedback.jsonl';feedback.parent.mkdir(parents=True,exist_ok=True)
    feedback.write_text(json.dumps({'id':'FB-legacy','project':'book','ts':'2026-10-11T20:57:51Z',
        'source':'synthetic fixture','anchor':legacy_source.relative_to(legacy_root).as_posix(),'supersedes':'','scope':'paragraph',
        'kind':'author-rewrite','node_id':'','section':'first','text':'Preserved synthetic legacy rewrite.',
        'by':'author','status':'resolved','file':'chapters/chapter-01.tex','baseline':{},'counts':{},'hunks':[]})+'\n')
    from laplace.writing import records
    from laplace.writing.records._index import _metadata
    with monkey.context() as old_owner:
        old_owner.setattr(owner,'_protection_index',lambda root,path:records.index(root,path=path.relative_to(root).as_posix(),extractor=_metadata))
        legacy_pending=apply(legacy_case,owner.preview('book','first','presentation-split',split_draft(legacy_case),legacy_root))
    legacy_read=owner.read('book',{'view':'restructure','section_ids':['first'],'receipt_id':legacy_pending['receipt']['id'],
        'intent_artifact_id':legacy_pending['receipt']['intent_artifact_id']},legacy_root)
    assert legacy_read['error']=="'record'" and legacy_read['source_effect']['state']=='COMMITTED'
    print(json.dumps({'block':block,'draft':draft,'preview':preview,'apply_payload':request,
        'complete':complete,'after_blocks':after_model,'undone':undone,'partial_preview':partial_preview,'partial':partial,'recovered':recovered,
        'multipart':multipart,
        'legacy_partial_read':legacy_read,
        'preview_action':owner.preview_handle('book','first',['first-p1'])}))
monkey.undo()
`], {cwd:fileURLToPath(new URL('../..',import.meta.url)), encoding:'utf8', timeout:30000});
assert.equal(generated.status, 0, generated.stderr);
export const restructureWire = JSON.parse(generated.stdout);
