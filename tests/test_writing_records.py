"""Substantive journal owner checks: original bytes, cuts, costs and lifetime."""
import json,subprocess,sys
from pathlib import Path
import pytest
from laplace.work import history as author_history
from laplace.core.records import journal
from laplace.writing import records
from laplace.representation import writing_bodies as bodies


def fixture(root, unrelated=0):
    home=root/'sources/book';home.mkdir(parents=True)
    (root/'contract').mkdir()
    (home/'main.tex').write_text('Original.\n')
    (root/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'book','kind':'tex',
        'project_dir':'sources/book','manuscript_dir':'sources/book','tex_root':'sources/book',
        'document':{'root':'main.tex','manuscript_dir':'sources/book'}}]}))
    rows=[{'record':'writing-artifact','id':'ART','project':'book','path':'sources/book/notes.txt',
           'artifact_path':'notes.txt','scope':'project','before':None,'after':'Exact saved note'},
          {'record':'writing-session','id':'WS','project':'book','provider':'claude','model':'old','role':'work'},
          {'record':'writing-turn','id':'WT','project':'book','session_id':'WS','text':'Original request',
           'provider_settings':{'provider':'codex','model':'admitted','effort':'high'}},
          {'record':'writing-reply','id':'WR','turn_id':'WT','session_id':'WS','status':'completed',
           'text':'Original public answer — 雪\n'*1000},
          {'record':'writing-tool-action','id':'ACTION','project':'book','turn_id':'WT','operation':'source',
           'payload':{'files':['main.tex']},'duration_seconds':1.25,'response_bytes':42,
           'outcome':{'status':'SUCCEEDED','output_sha256':'a'*64}},
          {'record':'writing-tool-read','id':'READ','project':'book','turn_id':'WT','operation':'source',
           'payload':{'files':['main.tex']},'output_sha256':'b'*64},
          {'record':'writing-tool-failure','id':'TOOLFAIL','project':'book','turn_id':'WT','operation':'source',
           'payload':{'files':['missing.tex']},'error':'Exact original error',
           'recovery':{'operation':'source','payload':{'files':['main.tex']}}}]
    for row in rows:
        # Historical imported replies can carry a public text body reference.
        if row['record']=='writing-reply':
            row['text']=bodies.retain_leaves(root,{'text':row['text']},('text',))['text']
        row['ts']='2026-10-09T00:00:00.000Z'
        with (root/'contract/talk.jsonl').open('a') as stream:
            stream.write(json.dumps(bodies.prepare_row(root,row))+'\n')
    big=bodies.prepare_row(root,{'record':'writing-turn','dependencies':{'note':'Unrelated body '*1000}})['dependencies']
    # Growth is an authored journal fixture, not 2000 ambient-act/fsync tests.
    with (root/'contract/talk.jsonl').open('a') as stream:
        for n in range(unrelated):stream.write(json.dumps({
            'record':'writing-turn','id':'OTHER-'+str(n),'project':'other','dependencies':big})+'\n')
    return rows


def test_full_public_envelopes_match_original_source(tmp_path):
    fixture(tmp_path)
    golden=json.loads((Path(__file__).parent/'fixtures/writing_records_c91b754d4.json').read_text())
    expected=golden['expected']
    actual=[author_history.record('book','activity:journal:'+i,tmp_path) for i in ['WT','WR','ACTION','READ','TOOLFAIL','ART']]
    # The original broad Activity presenter saw unresolved selected CAS values.
    # Preserve every original fact; explicitly qualify the approved enrichment
    # from resolving THIS row before deriving its summary/navigation targets.
    raw_rows={row['id']:row for row in map(json.loads,(tmp_path/'contract/talk.jsonl').read_text().splitlines())}
    for prior,current in zip(expected,actual):
        assert all(target in current['item']['targets'] for target in prior['item']['targets'])
        if prior['item']['targets']!=current['item']['targets']:
            assert isinstance(raw_rows[current['record']['id']].get('payload'),dict)
            assert raw_rows[current['record']['id']]['payload'].get('content_handle')
            assert current['item']['targets']==[{'kind':'manuscript','file':file} for file in current['record']['payload']['files']]
            prior['item']['targets']=current['item']['targets']
        if prior['item']['summary']!=current['item']['summary']:
            assert current['record_kind']=='writing-reply'
            assert raw_rows[current['record']['id']]['text'].get('content_handle')
            assert current['item']['summary'].startswith('Original public answer')
            prior['item']['summary']=current['item']['summary']
    assert actual==expected
    measured={x['kind']:x for x in actual[2]['measurements']}
    assert measured['duration_seconds']['value']==1.25 and measured['response_bytes']['value']==42
    actual[1]['record']['text']='Caller mutation'
    assert author_history.record('book','activity:journal:WR',tmp_path)['record']['text']==fixture_text()


def fixture_text():return 'Original public answer — 雪\n'*1000


@pytest.mark.parametrize('unrelated',[0,200,2000])
def test_selected_public_record_and_detail_do_not_discover_history(tmp_path,monkeypatch,unrelated):
    fixture(tmp_path,unrelated);records.index(tmp_path)  # cold cost is charged separately
    monkeypatch.setattr(author_history,'_all',lambda *a:pytest.fail('global Activity discovery'))
    monkeypatch.setattr(records,'fold_records',lambda *a:pytest.fail('global rich fold'))
    observed=[];raw=records._index._raw_indexed_record;body_reads=[];body=bodies.read_bytes
    def selected(idx,meta):
        observed.append((meta['id'],meta['_end']-meta['_offset']))
        return raw(idx,meta)
    monkeypatch.setattr(records._index,'_raw_indexed_record',selected)
    monkeypatch.setattr(bodies,'read_bytes',lambda ref,root:(body_reads.append(ref['content_handle']) or body(ref,root)))
    value=author_history.record('book','activity:journal:WR',tmp_path)
    assert value['text']==fixture_text() and value['item']['actor']['model']=='admitted'
    assert [x[0] for x in observed]==['WR','WT','WS'] and len(body_reads)==1
    observed.clear();body_reads.clear()
    detail=author_history.detail('book','activity:journal:WR',tmp_path)
    assert detail['saved_text_available'] is True
    assert [x[0] for x in observed]==['WR','WT','WS'] and len(body_reads)==1
    with pytest.raises(ValueError,match='unavailable'):
        author_history.record('book','activity:journal:DOES-NOT-EXIST',tmp_path)


@pytest.mark.parametrize('kind',['session','artifact'])
def test_supporting_namespace_and_artifact_middle_rewrite_refuse_current_cut(tmp_path,kind):
    fixture(tmp_path)
    path=tmp_path/'contract/talk.jsonl'
    entries=[{'record':'writing-steer','id':'PAD0','project':'book','text':'x'*5000},
             {'record':'writing-session','id':'SUPPORT','project':'book'},
             {'record':'writing-artifact','id':'ART','project':'book','artifact_path':'a.txt','scope':'project','sha256':'a'*64},
             {'record':'writing-reply','id':'WR-SCOPE','session_id':'SUPPORT','text':'Scoped'},
             {'record':'writing-steer','id':'PAD1','project':'book','text':'y'*5000}]
    path.write_text(''.join(json.dumps(x)+'\n' for x in entries))
    idx=records.index(tmp_path);old_generation=idx._generation
    before=path.read_bytes();selected='SUPPORT' if kind=='session' else 'ART'
    lines=before.splitlines(keepends=True)
    for i,line in enumerate(lines):
        if json.loads(line).get('id')==selected:lines[i]=line.replace(b'"book"',b'"cook"')
    path.write_bytes(b''.join(lines)+b'{"record":"writing-steer","id":"APPEND","project":"book"}\n')
    with pytest.raises(ValueError,match='selected journal row changed'):
        (records.selected_journal('book','WR-SCOPE',tmp_path) if kind=='session'
         else records.artifact_record(tmp_path,'book','ART'))
    assert records.indexes[idx._cache_key].identity is None
    fresh=records.index(tmp_path);assert fresh._generation is not old_generation
    if kind=='artifact':assert records.artifact_record(tmp_path,'cook','ART')['project']=='cook'
    else:assert records.selected_journal('cook','WR-SCOPE',tmp_path)[0]['text']=='Scoped'
    scans=fresh.stats['scans'];journal.bank_row('contract/talk.jsonl',{'record':'writing-steer','id':'LATER'},root=tmp_path)
    assert records.index(tmp_path).stats['scans']==scans


def test_duplicate_identity_and_supporting_scope_are_not_silently_picked(tmp_path):
    fixture(tmp_path)
    journal.bank_row('contract/talk.jsonl',{'record':'writing-tool-read','id':'WR','project':'book'},root=tmp_path)
    with pytest.raises(ValueError,match='ambiguous'):records.selected_journal('book','WR',tmp_path)
    with pytest.raises(ValueError,match='unavailable'):author_history.record('other','activity:journal:ACTION',tmp_path)


def test_rich_mutable_alias_lifetime_preserved_without_new_eviction_policy(tmp_path):
    from laplace.writing.records import _fold as records_fold
    from laplace.writing import session_reads
    fixture(tmp_path);state=records.fold_records(tmp_path);turn=state['turns']['WT']
    assert records_fold._CACHE is records._fold._CACHE and records_fold._LOCK is records._fold._LOCK
    assert session_reads._records(tmp_path) is state
    journal.bank_row('contract/talk.jsonl',{'record':'writing-turn-context-baseline','id':'CTX','turn_id':'WT',
        'project':'book','context_id':'later-context'},root=tmp_path)
    assert records.fold_records(tmp_path) is state and state['turns']['WT'] is turn
    assert turn['context_id']=='later-context' and turn['context_basis_record_id']=='CTX'


@pytest.mark.parametrize('bad_kind',[[],{},None])
def test_malformed_record_discriminator_is_unknown_not_a_hashability_crash(tmp_path,bad_kind):
    fixture(tmp_path)
    with (tmp_path/'contract/talk.jsonl').open('a') as stream:
        stream.write(json.dumps({'record':bad_kind,'id':'CORRUPT','project':'book'})+'\n')
    assert records.index(tmp_path).malformed_rows==1
    with pytest.raises(ValueError,match='unavailable'):
        author_history.record('book','activity:journal:CORRUPT',tmp_path)
    assert author_history.record('book','activity:journal:WR',tmp_path)['text']==fixture_text()


@pytest.mark.parametrize('ident',['WT','WR','ACTION','READ','TOOLFAIL'])
def test_launched_dispatch_provenance_follows_verified_owning_turn(tmp_path,ident):
    fixture(tmp_path)
    journal.bank_row('contract/talk.jsonl',{'record':'writing-turn','id':'WT-child','project':'book',
        'session_id':'WS','parent_turn_id':'WT','dispatch_id':'D1'},root=tmp_path)
    old_items=author_history._all('book',tmp_path)[0]
    expected=next(value for value in old_items if value['id']=='activity:journal:'+ident)
    actual=author_history.record('book','activity:journal:'+ident,tmp_path)
    assert actual['item']['dispatch_ids']==expected['dispatch_ids']==['D1']


def test_launched_child_hash_and_namespace_are_from_the_same_cut(tmp_path):
    fixture(tmp_path);path=tmp_path/'contract/talk.jsonl'
    pad=lambda name,letter:json.dumps({'record':'writing-steer','id':name,'project':'book','text':letter*5000})+'\n'
    child=json.dumps({'record':'writing-turn','id':'WT-child','project':'book','session_id':'WS',
        'parent_turn_id':'WT','dispatch_id':'D1'})+'\n'
    path.write_text(pad('PAD0','x')+path.read_text()+child+pad('PAD1','y'))
    records.index(tmp_path)
    path.write_text(path.read_text().replace(child,child.replace('"book"','"cook"'))+
        json.dumps({'record':'writing-steer','id':'APPEND','project':'book'})+'\n')
    with pytest.raises(ValueError,match='selected journal row changed; read its metadata cut again'):
        author_history.record('book','activity:journal:WR',tmp_path)


def test_artifact_adapter_preserves_stale_sha_refusal_and_distinct_ambiguity_cure(tmp_path):
    from laplace.projects import artifacts
    fixture(tmp_path);path=tmp_path/'contract/talk.jsonl'
    pad=lambda name,letter:json.dumps({'record':'writing-steer','id':name,'project':'book','text':letter*5000})+'\n'
    art=json.dumps({'record':'writing-artifact','id':'ART-pin','project':'book','artifact_path':'a.txt',
        'scope':'project','sha256':'a'*64})+'\n'
    path.write_text(pad('PAD0','x')+art+pad('PAD1','y'))
    records.index(tmp_path)
    path.write_text(path.read_text().replace('a.txt','b.txt')+
        json.dumps({'record':'writing-steer','id':'APPEND','project':'book'})+'\n')
    with pytest.raises(ValueError) as refusal:artifacts.record(tmp_path,'book','ART-pin')
    assert str(refusal.value)=='The selected journal row changed; read its metadata cut again.'
    assert 'Ambiguous' not in str(refusal.value) and 'scoped path' not in str(refusal.value)
    records.index(tmp_path)  # Fresh request observes the new cut, not a retry in the refused one.
    journal.bank_row('contract/talk.jsonl',json.loads(art),root=tmp_path)
    with pytest.raises(ValueError,match='Ambiguous artifact id.*exact scoped path'):
        artifacts.record(tmp_path,'book','ART-pin')
