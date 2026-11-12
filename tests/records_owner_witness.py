"""Cold source/installed exact records witness; authored fixture, no providers."""
import argparse,hashlib,importlib.abc,json,sys,tempfile,time
from pathlib import Path


class NoController(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {'laplace.web.authoring','laplace.native.tools','laplace.writing.provider'}:
            raise AssertionError('Cold record path imported live controller: '+fullname)


def witness(lib, atlas_lib):
    lib=Path(lib).resolve();atlas_lib=Path(atlas_lib or lib).resolve()
    sys.path[:0]=[str(lib),str(atlas_lib)]
    guard=NoController();sys.meta_path.insert(0,guard);started=time.perf_counter()
    from laplace.writing import records
    from laplace.projects import artifacts
    from laplace.representation import writing_bodies as bodies
    from laplace.work import history as author_history
    from laplace.core.records import journal
    cold_modules=[records,records._index,records._fold,records._project,artifacts,bodies,author_history]
    # Reach actual inline proposal metadata, not only a title-only toy index.
    projection=records._index._metadata({'record':'writing-proposal','id':'PROP-cold',
        'project':'p','proposal':{'summary':'Retained','edits':[{'file':'main.tex',
        'line_start':1,'line_end':1,'before':'Old','after':'New'}]}},0,1,1,'sha256:'+'0'*64)
    assert projection['proposal_projection']['edits'][0]['edit_id'].startswith('EDIT-')
    assert all(Path(m.__file__).resolve().is_relative_to(lib) for m in cold_modules)
    with tempfile.TemporaryDirectory(prefix='laplace-records-witness-') as raw:
        root=Path(raw);home=root/'proj';home.mkdir();(root/'contract').mkdir()
        (home/'main.tex').write_text('\\documentclass{article}\n\\begin{document}Fixture.\\end{document}\n')
        (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','kind':'conceptric',
            'project_dir':'proj','tex_root':'proj/main.tex'}]}))
        rows=[{'record':'writing-session','id':'WS','project':'p','provider':'codex','model':'fixture-model','role':'work'},
              {'record':'writing-turn','id':'WT','project':'p','session_id':'WS','mode':'work','text':'Fixture read and artifact',
               'provider_settings':{'provider':'codex','model':'fixture-model','effort':'high'}},
              {'record':'writing-reply','id':'WR-cold','project':'p','turn_id':'WT','session_id':'WS','text':'Exact historical reply'}]
        for row in rows:journal.bank_row('contract/talk.jsonl',row,root=root)
        assert author_history.record('p','activity:journal:WR-cold',root)['text']=='Exact historical reply'
        assert not any(n in sys.modules for n in ('laplace.web.authoring','laplace.native.tools','laplace.writing.provider'))
        journal.bank_row('contract/talk.jsonl',{'record':'writing-turn','id':'WT-child','project':'p','session_id':'WS','parent_turn_id':'WT','dispatch_id':'D1'},root=root)
        sys.meta_path.remove(guard)
        from laplace.native import tools as writing_tools
        from laplace.web import authoring as authoring_surface, research_surface
        from laplace.writing import records
        from laplace.writing import session_reads
        from urllib.parse import urlsplit,parse_qs
        text='Exact selected owner body — 雪\n'*500
        saved=writing_tools.execute(root,'p','work','store_artifact',{
            'path':'notes/result.md','scope':'project','before':None,'content':text,'reason':'Authored owner witness'},turn_id='WT')
        read=writing_tools.execute(root,'p','work','read_artifact',{'id':saved['id'],'limit':40000},turn_id='WT')
        assert read['content']==text
        records.bank(root,{'record':'writing-reply','id':'WR-final','project':'p','session_id':'WS',
            'turn_id':'WT','status':'completed','text':'Stored and read exact artifact'})
        targets=[saved['id'],saved['action_receipt']['id'],read['read_receipt']['id'],'WR-final']
        previous=authoring_surface._root;authoring_surface._root=lambda:root
        try:
            for ident in targets:
                payload={'view':'record','id':'activity:journal:'+ident}
                native=writing_tools.execute(root,'p','review','author_history',payload)
                status,_,body=authoring_surface.handle('/authoring/history',
                    {'project':['p'],**{k:[v] for k,v in payload.items()}},'GET',b'')
                human=json.loads(body)
                assert status==200 and native['record']==human['record'] and native['item']==human['item']
                assert human['record']['id']==ident and human['project']=='p'
                if ident!=saved['id']:assert human['item']['dispatch_ids']==['D1']
            records.bank(root,{'record':'writing-tool-failure','id':'TOOLFAIL-cure','project':'p',
                'turn_id':'WT','operation':'read_artifact','payload':{'id':'missing'},'error':'Authored refusal',
                'recovery':{'help':{'operation':'help','payload':{'operation':'read_artifact'}}}})
            guidance=writing_tools.execute(root,'p','work','help',{'operation':'read_artifact'},turn_id='WT')
            failure=next(row for row in session_reads.session_turn_detail(root,'p','WT','failures')['items']
                         if row['record']['id']=='TOOLFAIL-cure')
            assert failure['resolved_later'] is False and failure['recovery_read']['recovers_read_goal'] is False
            handle=failure['recovery_read']['read_handle'];assert handle['http']['method']=='GET'
            assert failure['recovery_read']['read_id']==guidance['read_receipt']['id']
            status,_,data=authoring_surface.handle('/authoring/history',parse_qs(urlsplit(handle['http']['url']).query),'GET',b'')
            assert status==200 and json.loads(data)['record']['id']==guidance['read_receipt']['id']
            q=parse_qs(urlsplit(saved['human_read']['url']).query)
            status,_,raw=research_surface.handle('/research/artifact',q,'GET',b'',repo_root=root)
            assert status==200 and raw==text.encode()
        finally:authoring_surface._root=previous
        import atlas
        assert Path(atlas.__file__).resolve().is_relative_to(atlas_lib)
        fixture_bytes=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    origins={m.__name__:str(Path(m.__file__).resolve()) for m in [*cold_modules,writing_tools,authoring_surface]}
    assert all(Path(p).is_relative_to(lib) for p in origins.values())
    return {'origins':origins,'source_pins':{n:hashlib.sha256(Path(p).read_bytes()).hexdigest() for n,p in origins.items()},
        'cold_controller_imports':False,'checks':['original cold WR','actual owner guarded artifact/ACTION/READ',
        'exact original ART/ACTION/READ/WR human/native parity','parent dispatch relationship retained','derived recovery READ canonical HTTP transport without status inference','pinned raw artifact bytes'],
        'fixture_bytes':fixture_bytes,'fixture_cleaned':True,'provider_calls':0,'services':0,
        'qualification':'Authored admission/reply fixture and real tool/HTTP owners, not real native provider delivery.',
        'seconds':time.perf_counter()-started}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--lib',required=True);parser.add_argument('--atlas-lib')
    a=parser.parse_args();print(json.dumps(witness(a.lib,a.atlas_lib),sort_keys=True))
