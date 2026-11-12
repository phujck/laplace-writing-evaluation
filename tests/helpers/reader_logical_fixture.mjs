import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const generated=spawnSync('./scripts/laplace-python',['-c',String.raw`
import json,sys,tempfile
from pathlib import Path
import pytest
sys.path.insert(0,'tests')
from test_reader_restructure import case
from test_reader_logical_publication import completed_preview,apply,reconciliation_case,larger_reconciliation_case,_feedback_attachment_case,_attachment_preview
from laplace.manuscript import reader_restructure as owner
monkey=pytest.MonkeyPatch()
with tempfile.TemporaryDirectory(prefix='laplace-logical-ui-') as temporary:
    make=getattr(case,'__wrapped__',None) or case._get_wrapped_function()
    root,home,source=make(Path(temporary),monkey)
    source.write_text('\\chapter{First}\\label{chapter:first}\n% PLAN:first\n'+''.join(
        '% first-p1\n% first-p2\nSaved passage '+str(index)+'.\n\n' for index in range(3)))
    narrative=owner._snapshot('book','first',root)['paths']['narrative']
    document=json.loads(narrative.read_text())
    document['paragraphs'][0]['qualification']='This example tests the editing workflow rather than a scientific claim.'
    narrative.write_text(json.dumps(document))
    original=source.read_bytes()
    draft={'paragraph_ids':['first-p1'],'successor_count':2}
    initial=owner.preview('book','first','logical-split',draft,root)
    ids=[row['paragraph_id'] for row in initial['successors']]
    authored={**draft,'successors':[{'paragraph_id':ident,'changes':{'function':'Role '+str(index),'proposition':'Authored point '+str(index)}} for index,ident in enumerate(ids)],
        'attachment_assignments':[{'attachment_id':row['id'],'disposition':'assign','successor_ids':[ids[0]]} for row in initial['attachment_inventory']],
        'occurrence_assignments':[{'occurrence_id':row['id'],'successor_ids':[ids[0] if index==0 else ids[1]]} for index,row in enumerate(initial['occurrence_inventory'])]}
    preview=owner.preview('book','first','logical-split',authored,root)
    assert source.read_bytes()==original
    source.write_bytes(original.replace(b'Saved passage 2.',b'Saved passage 2. A changed source detail.'))
    refreshed=owner.preview('book','first','logical-split',draft,root)
    def fresh_case(name,plan_only=False):
        item=make(Path(temporary)/name,monkey)
        r,h,s=item
        if plan_only:s.write_text('\\chapter{First}\\label{chapter:first}\n')
        else:s.write_bytes(original)
        path=owner._snapshot('book','first',r)['paths']['narrative']
        doc=json.loads(path.read_text());doc['paragraphs'][0]['qualification']=document['paragraphs'][0]['qualification'];path.write_text(json.dumps(doc))
        return item
    def prepare_case(item):
        first,ready=completed_preview(item)
        authored={**ready['draft'],'successor_count':2}
        first=owner.preview('book','first','logical-split',{'paragraph_ids':['first-p1'],'successor_count':2},item[0])
        ready=owner.preview('book','first','logical-split',authored,item[0])
        return first,ready
    written=fresh_case('application');wi,wp=prepare_case(written);saved=apply(written,wp)
    assert saved['complete'],saved
    from laplace.manuscript import reader_plan
    def section_plan(item):
        snap=owner._snapshot('book','first',item[0])
        return reader_plan.section_view('book',item[0],snap['section'],snap['state']['sections'],snap['state']['authority']['plan_revision'])['paragraph_plan']
    discovery={'plan':section_plan(written),'saved':owner.read('book',saved['read_handle']['payload'],written[0])}
    before_inverse=written[2].read_bytes()
    inverse=owner.change('book',saved['undo_action']['payload'],written[0]);assert inverse['complete'] and written[2].read_bytes()==original
    discovery['inverse']=owner.read('book',inverse['read_handle']['payload'],written[0]);discovery['changed']=owner.read('book',saved['read_handle']['payload'],written[0])
    redo=owner.change('book',inverse['undo_action']['payload'],written[0]);assert redo['complete'] and written[2].read_bytes()==before_inverse
    discovery['redo']=owner.read('book',redo['read_handle']['payload'],written[0])
    mi,mp=completed_preview(written,'logical-merge',selected=saved['successor_ids'])
    snapshot=owner._snapshot('book','first',written[0])
    from laplace.manuscript import reader_plan
    merge_plan=reader_plan.section_view('book',written[0],snapshot['section'],snapshot['state']['sections'],snapshot['state']['authority']['plan_revision'])['paragraph_plan']
    merged=apply(written,mp);assert merged['complete'],merged
    pending_case=fresh_case('partial');pi,pp=prepare_case(pending_case)
    target=owner._snapshot('book','first',pending_case[0])['paths']['provenance'];store=owner._store
    with monkey.context() as outage:
        def fail(project,root,path,*args,**kwargs):
            if path==target:raise OSError('Simulated logical provenance publication outage')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail);partial=apply(pending_case,pp)
    assert partial['source_effect']['state']=='COMMITTED' and not partial['complete']
    physical=pending_case[2].read_bytes()
    from laplace.manuscript import manuscript_structure
    with monkey.context() as recovery_guard:
        recovery_guard.setattr(manuscript_structure,'_write_source',lambda *a,**k:pytest.fail('Metadata recovery replayed logical source'))
        recovered=owner.change('book',partial['recovery_action']['payload'],pending_case[0])
    assert recovered['complete'] and pending_case[2].read_bytes()==physical
    narrative_case=fresh_case('narrative-partial');ni,np=prepare_case(narrative_case)
    target_narrative=owner._snapshot('book','first',narrative_case[0])['paths']['narrative']
    with monkey.context() as outage:
        def fail_narrative(project,root,path,*args,**kwargs):
            if path==target_narrative:raise OSError('Simulated logical narrative publication outage')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail_narrative);narrative_partial=apply(narrative_case,np)
    assert narrative_partial['source_effect']['state']=='COMMITTED' and not narrative_partial['complete']
    from laplace.manuscript import manuscript_source,projection_viewer,walk
    nr,nh,ns=narrative_case;resolution=manuscript_source.resolve('book',repo_root=nr)
    blocks=walk.blocks_for(ns.read_text(),file_rel=ns.relative_to(nh).as_posix(),repo_file=ns.relative_to(nr).as_posix(),md=nh,corpus='book',dir_param='',known_macros=frozenset(),para_spans=projection_viewer.parse_paragraphs(ns.read_text()))
    top_pending=owner.annotate_walk('book',nr,[{'blocks':blocks}],resolution,manuscript_source.traversal(resolution['root'],nr))
    snapshot=owner._snapshot('book','first',nr)
    pending_plan=reader_plan.section_view('book',nr,snapshot['section'],snapshot['state']['sections'],snapshot['state']['authority']['plan_revision'])['paragraph_plan']
    physical=ns.read_bytes()
    with monkey.context() as recovery_guard:
        recovery_guard.setattr(manuscript_structure,'_write_source',lambda *a,**k:pytest.fail('Narrative recovery replayed source'))
        narrative_recovered=owner.change('book',narrative_partial['recovery_action']['payload'],nr)
    assert narrative_recovered['complete'] and ns.read_bytes()==physical
    alone=fresh_case('plan-only',plan_only=True);ai,ap=prepare_case(alone);alone_before=alone[2].read_bytes();plan_only=apply(alone,ap)
    assert plan_only['complete'] and 'source_effect' not in plan_only and alone[2].read_bytes()==alone_before
    reconciliation={}
    for name,logical,shift in [('logical',True,False),('presentation',False,False),('shifted',False,True)]:
        item=make(Path(temporary)/('reconcile-'+name),monkey)
        reconciliation[name]=reconciliation_case(item,monkey,logical_kind=logical,line_shift=shift)
        with monkey.context() as source_context:
            source_context.setattr(projection_viewer,'_repo_root',lambda:item[0])
            reconciliation[name]['source_read']=projection_viewer._source_observation(item[2])
    item=make(Path(temporary)/'reconcile-plan-only',monkey);r,h,s=item;s.write_text('\\chapter{First}\\label{chapter:first}\n')
    _,final=completed_preview(item);target=owner._snapshot('book','first',r)['paths']['provenance']
    with monkey.context() as outage:
        def fail(project,root,path,*args,**kwargs):
            if path==target:raise OSError('metadata unavailable')
            return store(project,root,path,*args,**kwargs)
        outage.setattr(owner,'_store',fail);plan_partial=apply(item,final)
    architecture=reader_plan._architecture
    with monkey.context() as changed_inputs:
        import copy
        def changed(*args,**kwargs):
            result=copy.deepcopy(architecture(*args,**kwargs));result['effective_projection']['revision']='sha256:'+'a'*64;return result
        changed_inputs.setattr(reader_plan,'_architecture',changed)
        ready=owner.read('book',plan_partial['reconciliation_read']['payload'],r)
        acknowledged=owner.change('book',ready['metadata_reconciliation']['action']['payload'],r)
    reconciliation['plan_only']={'partial':plan_partial,'ready':ready,'acknowledged':acknowledged}
    omitted_case=fresh_case('summary-omitted');path=owner._snapshot('book','first',omitted_case[0])['paths']['narrative']
    doc=json.loads(path.read_text());doc['paragraphs'][0]['qualification']='Exact long qualification '+('π'*600);path.write_text(json.dumps(doc))
    _,omitted_preview=prepare_case(omitted_case);omitted_result=apply(omitted_case,omitted_preview)
    omitted_read=owner.read('book',omitted_result['read_handle']['payload'],omitted_case[0])
    larger=larger_reconciliation_case(make(Path(temporary)/'reconcile-large',monkey),monkey,count=120)
    carried_case=make(Path(temporary)/'carried-witnesses',monkey);_feedback_attachment_case(carried_case)
    _,carried_ready=_attachment_preview(carried_case,'logical-split',['first-p1'],both=True)
    carried_saved=apply(carried_case,carried_ready);left,right=carried_saved['successor_ids']
    _,branch_ready=_attachment_preview(carried_case,'logical-split',[left],disposition='retain-unresolved')
    branch=apply(carried_case,branch_ready)
    mixed=owner.preview('book','first','logical-merge',{'paragraph_ids':[branch['successor_ids'][0],right]},carried_case[0])
    unresolved=owner.preview('book','first','logical-merge',{'paragraph_ids':branch['successor_ids']},carried_case[0])
    carried={name:{'initial':value,'action':owner.action('book','first','preview-restructure',kind='logical-merge',draft={'paragraph_ids':value['draft']['paragraph_ids']})} for name,value in [('mixed',mixed),('unresolved',unresolved)]}
    print(json.dumps({'carried_witnesses':carried,'summary_omitted':omitted_read,'discovery':discovery,'large_reconciliation':larger,'reconciliation':reconciliation,'initial':initial,'draft':authored,'preview':preview,'refreshed':refreshed,
        'application':{'initial':wi,'preview':wp,'result':saved,'inverse':inverse,'redo':redo},
        'merge':{'initial':mi,'preview':mp,'plan':merge_plan,'result':merged,'action':owner.action('book','first','preview-restructure',kind='logical-merge',draft={'paragraph_ids':[saved['successor_ids'][0]]})},
        'partial':{'initial':pi,'preview':pp,'result':partial,'recovered':recovered},
        'narrative_partial':{'initial':ni,'preview':np,'result':narrative_partial,'recovered':narrative_recovered,'plan':pending_plan,
            'top_pending':top_pending,'tagged_block_leases':[row.get('restructure_preview') for row in blocks if row.get('spec_ids')]},
        'plan_only':{'initial':ai,'preview':ap,'result':plan_only},
        'action':owner.action('book','first','preview-restructure',kind='logical-split',draft=draft)}))
monkey.undo()
`],{cwd:fileURLToPath(new URL('../..',import.meta.url)),encoding:'utf8',timeout:30000});
assert.equal(generated.status,0,generated.stderr);
export const logicalWire=JSON.parse(generated.stdout);
