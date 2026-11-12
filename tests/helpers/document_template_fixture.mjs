import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

// The production candidate owner supplies all selectors, actions and byte parts.
const generated=spawnSync('./scripts/laplace-python',['-c',String.raw`
import json,sys,tempfile
from pathlib import Path
import pytest
sys.path.insert(0,'tests')
from test_document_templates import case,request,prepared
from laplace.manuscript import document_templates as owner
from laplace.manuscript import projection_viewer
from test_candidate_builds import candidate_case,settle
monkey=pytest.MonkeyPatch()
with tempfile.TemporaryDirectory(prefix='laplace-template-ui-') as temporary:
    home=Path(temporary)
    monkey.setenv('LAPLACE_STATE',str(home/'state'))
    make=getattr(case,'__wrapped__',None) or case._get_wrapped_function()
    item=make(home/'repo',monkey);root,path=item
    monkey.setattr(projection_viewer,'_repo_root',lambda:root)
    code,_,raw=projection_viewer.handle('/projection/tex',{'corpus':['template-book'],'file':[path.relative_to(root).as_posix()],'view':['source']},'GET',b'')
    assert code==200,raw
    source=json.loads(raw)
    discovery=owner.discovery('template-book',root)
    saved=prepared(item);draft=prepared(item,draft=True)
    parts={}
    for name,handle in saved['source_changes'][0]['reads'].items():
        pieces=[];payload={**handle['payload'],'limit':40};payload.pop('project',None)
        while payload:
            value=owner.inspect('template-book',payload,root)
            pieces.append(value);payload=value.get('next_read',{}).get('payload')
            if payload:payload={key:item for key,item in payload.items() if key!='project'}
        parts[name]=pieces
    listing=owner.inspect('template-book',{'view':'template-candidates'},root)
    for index in range(21):
        more=request(item);more['reason']='Bounded candidate catalogue '+str(index)
        owner.change('template-book',more,root,actor={'kind':'human'})
    catalogue_pages=[];page={'view':'template-candidates'}
    while page:
        observed=owner.inspect('template-book',page,root);catalogue_pages.append(observed)
        page=observed.get('next_read',{}).get('payload')
        if page:page={key:value for key,value in page.items() if key!='project'}
    before=path.read_bytes();path.write_bytes(before+b'% later human edit\n')
    changed=owner.inspect('template-book',{key:value for key,value in saved['read_handle']['payload'].items() if key!='project'},root)
    if not projection_viewer._latexmk_bin():raise RuntimeError('Template Apply acceptance needs an installed TeX toolchain; configure LAPLACE_LATEXMK_BIN or install the project runtime outside this test.')
    make_build=getattr(candidate_case,'__wrapped__',None) or candidate_case._get_wrapped_function()
    setup=make_build(home/'built',monkey);built=next(setup);br,bp,original,bm,bb=built
    monkey.setattr(projection_viewer,'_repo_root',lambda:br)
    def source_value():
        code,_,raw=projection_viewer.handle('/projection/tex',{'corpus':['book'],'file':[bp.relative_to(br).as_posix()],'view':['source']},'GET',b'')
        assert code==200,raw
        return json.loads(raw)
    source_before=source_value()
    brequest={'action':'prepare','source_edits':[{'file':bp.relative_to(br).as_posix(),'content':bp.read_text().replace('Original','Reviewed')}],
        'guards':{'expected_selection':bb['selected_source']['selection_identity'],'source_guards':{bp.relative_to(br).as_posix():owner.pin(original)}},
        'reason':'Captured editor draft preview','draft_basis':{'file':bp.relative_to(br).as_posix(),'revision':'draft-1'}}
    metadata=owner.change('book',brequest,br,actor={'kind':'human'})
    target=metadata['build_action']['payload']['build_target']
    code,started=projection_viewer.recompile(target['root'],'book','author',repo_root=br,build_target=target)
    assert code==200,started
    finished=settle(br,started['build_job']);assert finished.get('ok') and finished.get('preview_ref'),finished
    code,second_started=projection_viewer.recompile(target['root'],'book','author',repo_root=br,build_target=target)
    assert code==200,second_started
    second_finished=settle(br,second_started['build_job']);assert second_finished.get('ok'),second_finished
    latest=owner.inspect('book',{'view':'template','candidate_ref':metadata['candidate_ref']},br)
    reviewed=owner.inspect('book',{'view':'template','candidate_ref':metadata['candidate_ref'],'preview_ref':finished['preview_ref']},br)
    assert reviewed['apply_action']['payload']['preview_ref']==finished['preview_ref']
    assert latest['build']['preview_ref']==second_finished['preview_ref']
    applied=owner.change('book',{key:value for key,value in reviewed['apply_action']['payload'].items() if key!='project'},br,actor={'kind':'human'})
    assert applied['source_effect']['state']=='COMMITTED',applied
    source_after=source_value()
    recovered=owner.change('book',{'action':'recover','candidate_ref':metadata['candidate_ref'],'application_id':applied['application_recording']['application_id']},br,actor={'kind':'human'})
    print(json.dumps({'built':{'metadata':metadata,'reviewed':reviewed,'started':started,'finished':finished,'latest':latest,'second_finished':second_finished,'applied':applied,'recovered':recovered,
        'source_before':source_before,'source_after':source_after,'draft_content':brequest['source_edits'][0]['content']},
        'catalogue_pages':catalogue_pages,'source':source,'discovery':discovery,'saved':saved,'draft':draft,'parts':parts,'listing':listing,'changed':changed,'request':request(item)}))
    setup.close()
monkey.undo()
`],{cwd:fileURLToPath(new URL('../..',import.meta.url)),encoding:'utf8',timeout:30000});
assert.equal(generated.status,0,generated.stderr);
export const templateWire=JSON.parse(generated.stdout);
