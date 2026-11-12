"""Regenerates tests/fixtures/editor_spine/display-owner.json from the real reader-plan owner on disposable
synthetic projects (no real data): the wide 20-paragraph section with a declared, shortened reader
transition, its subject/choices reads and values_read answer, and (repair3 R2) a second section whose rows
carry only a clipped proposition or function, with their whole-row reads. Run from the repository root:
scripts/laplace-python tests/fixtures/editor_spine/generate_display_owner.py"""
import sys,json,tempfile,pathlib
sys.path.insert(0,'tests')
from test_structure_display_projection import wide
from laplace.manuscript import project_structure
with tempfile.TemporaryDirectory(prefix='fx-') as t:
    root=pathlib.Path(t);wide(root,text='the reader is shown the mechanism in plain words and the consequence it has for the claim; '*3)
    r=lambda p:project_structure.read('book',p,root)
    # release repair (ACTUAL-C1011-DISPLAY-BYTES): 14 of the members are narrative beats, read lazily in two pages
    from laplace.research import corpus_ingest
    for index in range(14):
        corpus_ingest.rewire_add(root,'book',{'kind':'set-spine','node':'concept:wide-member-%02d' % index,'ord':index+1,'narrative':'Beat %d: the reader meets this step of the argument.' % index,'by':'fixture'})
    # repair3 R2: a declared reader transition whose entry text the display shortens
    from laplace.native import tools as writing_tools
    call=r({'view':'detail','section_ids':['first'],'projection':'guard'})['reader_transition']['edit_action']
    writing_tools.execute(root,'book','work','structure_change',{**call['payload'],'changes':{'entry_state':'The reader arrives knowing the mechanism in outline but not its consequence for the claim. '*4,'exit_state':'The reader can state the consequence.','depends_on':['concept:wide-member-00']}})
    d=r({'view':'detail','section_ids':['first'],'projection':'display'})
    pid=d['sections'][0]['paragraph_plan']['paragraphs']['items'][0]['paragraph_id']
    out={'display':d,'paragraph_display':r({'view':'detail','section_ids':['first'],'paragraph_id':pid,'projection':'display'}),
     'section_subject':r({'view':'detail','section_ids':['first'],'projection':'guard','subject':'section'}),
     'structure_subject':r({'view':'detail','section_ids':['first'],'projection':'guard','subject':'structure','paragraph_id':pid}),
     'paragraph_choices':r({'view':'detail','section_ids':['first'],'projection':'guard','subject':'paragraph','paragraph_id':pid,'edit_choices':True}),
     'plan':r({'view':'plan'}),'contract_values':None,'summary':r({'view':'summary','section_limit':6,'spine_limit':6,'object_limit':1,'gap_limit':1})}
    out['spine_pages']=[]
    handle=d['spine_page']['read']
    while handle:
        page=r(handle['payload']);out['spine_pages'].append(page);handle=page['spine_page']['next_read']
    out['beat_detail']=r({'view':'detail','node_id':'concept:wide-member-00'})
    out['beat_detail']={key:out['beat_detail'].get(key) for key in ('schema_version','project','spine','revision')}
    out['contract_values']=r(d['sections'][0]['reader_transition']['values_read']['payload'])
    for f in out['contract_values']['reader_transition']['edit_action'].get('fields',[]):
        if isinstance(f.get('choices'),list):f['choices']=f['choices'][:2]
    for f in out['paragraph_choices']['paragraph']['edit_action'].get('fields',[]):
        if isinstance(f.get('choices'),list):f['choices']=f['choices'][:2]
    # repair3 R2: rows whose only shown text is clipped (authored == []), from a second synthetic project
    from test_manuscript_structure import _section_fixture
    with tempfile.TemporaryDirectory(prefix='fx2-') as t2:
        root2=pathlib.Path(t2);_section_fixture(root2);r2=lambda p:project_structure.read('book',p,root2)
        for name,text in (('proposition','A complete authored proposition, kept whole. '*12),('function','A complete authored function, “quoted” and 中文. '*12)):
            create=r2({'view':'detail','section_ids':['first'],'projection':'guard','subject':'create'})['create_action']
            writing_tools.execute(root2,'book','work','structure_change',{**create['payload'],'changes':{name:text}})
        d2=r2({'view':'detail','section_ids':['first'],'projection':'display'})
        out['clipped_only']={'display':d2,'whole':{row['paragraph_id']:r2({**d2['sections'][0]['paragraph_plan']['paragraphs']['row_read']['payload'],'paragraph_id':row['paragraph_id']}) for row in d2['sections'][0]['paragraph_plan']['paragraphs']['items']}}
    pathlib.Path('tests/fixtures/editor_spine/display-owner.json').write_text(json.dumps(out,ensure_ascii=False,indent=0)+'\n')
    print({k:len(json.dumps(v,ensure_ascii=False).encode()) for k,v in out.items()}, sorted(out['paragraph_choices']['paragraph']['edit_action']['values'])[:4])
