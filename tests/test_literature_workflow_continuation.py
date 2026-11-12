"""Generic registered-content and retained qualification joins; no live corpus."""
import json
from pathlib import Path
import pytest
from laplace.research import literature, references_surface as rs, literature_support
from laplace.native import tools
from test_literature_joined_workflow import project,execute,bind


def test_registered_content_search_receipt_currentness_and_http_native_parity(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    content='Introductory source text.\n'*100+'Needle: the controlled source passage.\n'+'Tail.\n'*100
    original.write_text(content)
    hit=execute(tmp_path,'reference_text',{'key':key,'query':'controlled source passage','limit':1000})
    assert hit['search_state']=='MATCH' and content[hit['hit']['character_start']:hit['hit']['character_end']]=='controlled source passage'
    assert hit['reading_receipt']['source_sha256']==rs._sha256_file(original)
    assert hit['reading_receipt']['offset']<=hit['hit']['character_start']
    query={'project':['joined'],'key':[key],'query':['controlled source passage'],'limit':['1000']}
    status,_,body=rs.handle('/references/text',query,'GET',b'',repo_root=tmp_path)
    human=json.loads(body)
    assert status==200 and human['hit']==hit['hit'] and human['reading_receipt']==hit['reading_receipt']
    before=(manuscript/'references.json').read_bytes()
    missing=execute(tmp_path,'reference_text',{'key':key,'query':'Absent exact term','limit':1000})
    assert missing['search_state']=='NO_MATCH' and 'reading_receipt' not in missing
    assert (manuscript/'references.json').read_bytes()==before
    original.write_text(content+'Changed input.')
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        execute(tmp_path,'reference_text',{'key':key,'offset':1000,'expected_source_revision':hit['reading_receipt']['source_sha256'],'limit':1000})


def test_empty_out_of_range_read_cannot_qualify_claim_or_grow_history(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    store=manuscript/'references.json';before=store.read_bytes()
    result=execute(tmp_path,'reference_text',{'key':key,'offset':200000,'limit':1000})
    assert result['source_state']=='exhausted' and 'reading_receipt' not in result
    assert store.read_bytes()==before
    good=execute(tmp_path,'reference_text',{'key':key,'limit':1000})['reading_receipt']
    malformed={**good,'id':'READ-legacy-empty','offset':200000,'length':0}
    rows=rs._load_associations(manuscript);rows[0].setdefault('reading_observations',[]).append(malformed);rs._write_associations(manuscript,rows)
    before=store.read_bytes()
    with pytest.raises(ValueError,match='current source passage'):
        execute(tmp_path,'literature_bind',{'key':key,'claim_id':'result:first','relation':'supports',
            'rationale':'A historical empty receipt is not a passage.','reading_status':'partial',
            'reading_id':malformed['id'],'evidence':{'locator':malformed['locator']}})
    assert store.read_bytes()==before
    valid=execute(tmp_path,'literature_bind',{'key':key,'claim_id':'result:first','relation':'supports',
        'rationale':'Actual returned source.','reading_status':'partial','reading_id':good['id'],
        'evidence':{'locator':good['locator']}})
    rows=rs._load_associations(manuscript)
    for row in rows:
        if row.get('claim_id')=='result:first':row['reading_receipt']=malformed
    rs._write_associations(manuscript,rows)
    support=literature_support.for_node('joined','result:first',tmp_path)
    assert support['sources'][0]['qualification']=='NO_PASSAGE_OBSERVED'


def test_required_meaning_guard_and_meaningful_target_refuse_before_binding_mutation(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    read=execute(tmp_path,'reference_text',{'key':key,'limit':1000})
    payload={'key':key,'claim_id':'result:first','relation':'supports','rationale':'Conditional source support',
        'reading_status':'partial','reading_id':read['reading_receipt']['id'],'evidence':{'locator':read['reading_receipt']['locator']}}
    before=(manuscript/'references.json').read_bytes()
    with pytest.raises(ValueError,match='claim_revision'):
        tools.execute(tmp_path,'joined','work','literature_bind',payload)
    revision=literature_support.meaning_revision('joined','result:first',tmp_path)
    from laplace.research import corpus_ingest
    assert corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'edit-essence','node':'result:first','value':'A changed scientific statement.'}).get('ok')
    with pytest.raises(ValueError,match='meaning changed'):
        execute(tmp_path,'literature_bind',{**payload,'claim_revision':revision})
    assert (manuscript/'references.json').read_bytes()==before
    net=literature_support.network('joined',tmp_path)
    with pytest.raises(ValueError,match='meaningful scientific'):
        execute(tmp_path,'literature_bind',{**payload,'claim_id':net['root'],'claim_revision':revision})


def test_retained_reading_basis_beyond128_is_single_source_home_and_duplicate_reads_do_not_grow(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    original.write_text('A generic readable source. '*6000)
    reads=[execute(tmp_path,'reference_text',{'key':key,'offset':offset,'limit':1000}) for offset in range(0,140000,1000)]
    first=reads[0]['reading_receipt'];payload={'key':key,'claim_id':'result:first','claim_revision':literature_support.meaning_revision('joined','result:first',tmp_path),
        'relation':'supports','rationale':'An explicitly bounded authored use','reading_status':'partial','reading_id':first['id'],'evidence':{'locator':first['locator'],'excerpt':'generic readable source'}}
    admitted=execute(tmp_path,'literature_bind',payload)
    assert admitted['association']['reading_receipt']==first
    assert 'reading_observations' not in admitted['association']
    store=manuscript/'references.json';before=store.read_bytes();stamp=store.stat().st_mtime_ns
    repeat=execute(tmp_path,'reference_text',{'key':key,'offset':0,'limit':1000})
    assert repeat['reading_receipt']==first and store.read_bytes()==before and store.stat().st_mtime_ns==stamp
    rows=rs._load_associations(manuscript);base=next(row for row in rows if not row.get('claim_id'))
    assert len(base['reading_observations'])==140
    assert len(json.dumps(base['reading_observations']))<160000
    listed=execute(tmp_path,'literature_uses',{})
    assert all('reading_observations' not in row for row in listed['uses'])
    assert next(row for row in listed['uses'] if not row.get('claim_id'))['reading_observation_count']==140


def test_extraction_reused_for_pages_bind_and_invalidated_by_source_bytes(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    actual=literature._extract_content;calls=[]
    def extract(path):calls.append(str(path));return actual(path)
    monkeypatch.setattr(literature,'_extract_content',extract);literature._EXTRACTION_CACHE.clear()
    original.write_text('A controlled source passage. '*400)
    first=execute(tmp_path,'reference_text',{'key':key,'limit':1000})
    execute(tmp_path,'reference_text',{'key':key,'offset':1000,'limit':1000})
    execute(tmp_path,'literature_bind',{'key':key,'claim_id':'result:first','reading_id':first['reading_receipt']['id'],'reading_status':'partial','relation':'supports','rationale':'Controlled statement only','evidence':{'locator':first['reading_receipt']['locator'],'excerpt':'controlled source passage'}})
    assert len(calls)==1
    original.write_text('Changed source bytes. '+original.read_text())
    execute(tmp_path,'reference_text',{'key':key,'offset':1000,'limit':1000})
    assert len(calls)==2


def test_counterevidence_is_qualified_cited_and_current_while_original_results_stay_distinct(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    read=execute(tmp_path,'reference_text',{'key':key})
    linked=execute(tmp_path,'literature_bind',{'key':key,'claim_id':'result:first','relation':'contradicts','rationale':'Challenges an unrestricted version of this claim.',
        'reading_id':read['reading_receipt']['id'],'reading_status':'partial','evidence':{'locator':read['reading_receipt']['locator']}})
    scope=execute(tmp_path,'literature_scope',{'node':'result:first'})
    assert scope['claims'][0]['sources'][0]['relation']=='counterevidence'
    assert any(gap['kind']=='not-yet-cited' for gap in scope['gaps'])
    assert any(gap['kind']=='citation-not-rendered' for gap in scope['gaps'])
    original.write_text('Changed counterevidence content.')
    with pytest.raises(ValueError,match='CHANGED_INPUT'):
        execute(tmp_path,'literature_scope',{'node':'result:first','as_of':scope['revision']})
    changed=execute(tmp_path,'literature_scope',{'node':'result:first'})
    assert any(gap['kind']=='source-not-qualified' and gap['state']=='STALE' for gap in changed['gaps'])
    assert changed['claims'][0]['own_evidence']==[] and changed['ready_for_completion'] is False


def test_owner_candidates_are_exact_and_fetched_content_is_unread_until_inspected(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    rows=rs._load_associations(manuscript);next(row for row in rows if not row.get('claim_id'))['metadata']['fulltext_urls']=['https://example.org/fulltext.txt']
    rs._write_associations(manuscript,rows)
    info=execute(tmp_path,'reference_source',{'key':key});choice=info['fulltext_candidates'][0]
    calls=[]
    monkeypatch.setattr(literature,'_download',lambda url:(calls.append(url) or b'Fresh acquired source content.\n','text/plain',url))
    fetched=execute(tmp_path,'reference_fetch',{'key':key,'candidate_id':choice['id']})
    assert calls==[choice['url']] and 'ACQUIRED_UNREAD' in fetched['source_text']['qualification']
    assert execute(tmp_path,'reference_source',{'key':key})['acquisition_state']=='ACQUIRED_UNREAD'
    assert not any(row.get('reading_observations') for row in rs._load_associations(manuscript))
    with pytest.raises(ValueError,match='candidate changed'):
        execute(tmp_path,'reference_fetch',{'key':key,'candidate_id':'FETCH-invalid'})


def test_literal_tex_cites_are_not_saved_active_citations_and_section_limits_stay_explicit(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    chapter=manuscript/'chapters/chapter-01.tex'
    chapter.write_text('\\section{First claim}\nLiteral \\verb|\\cite{Fake}|.\n\\begin{verbatim}\n\\cite{AlsoFake}\n\\end{verbatim}\nActive \\cite{FixtureSource}.\n\\section{Second claim}\nSecond passage.\n')
    selected,spans,_=rs.citation_spans('joined',tmp_path)
    assert [span['citekey'] for span in spans]==['FixtureSource']
    assert chapter.read_text()[spans[0]['character_start']:spans[0]['character_end']]=='\\cite{FixtureSource}'
    coverage=execute(tmp_path,'literature_scope',{'node':'result:first'})
    assert 'section' in coverage['attribution_limits'] and 'entailment' in coverage['attribution_limits']


def test_original_result_binding_and_external_counterevidence_do_not_share_fake_result_identity(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    from laplace.research import concepts as concepts_surface
    from laplace.manuscript import project_structure
    from laplace.research import research_records
    data=manuscript/'independent.json';data.write_text('{"controlled_measure":2}')
    status,record=research_records.record('joined',{'kind':'result','id':'result:independent','result':'independent.json'},tmp_path)
    assert status==201
    current=project_structure.state('joined',tmp_path);concept=concepts_surface.state('joined',node='result:first',root=tmp_path)
    execute(tmp_path,'structure_change',{'operation':'bind_results','node':'result:first','results':[{'id':'result:independent','revision':record['record']['revision']}],
        'expected_revision':current['revision'],'expected_concept_revision':concept['revision']})
    read=execute(tmp_path,'reference_text',{'key':key})
    execute(tmp_path,'literature_bind',{'key':key,'claim_id':'result:first','reading_id':read['reading_receipt']['id'],'reading_status':'partial','relation':'contradicts','rationale':'Limited contrary source passage','evidence':{'locator':read['reading_receipt']['locator']}})
    original.write_text('The external source changed.')
    state=literature_support.for_node('joined','result:first',tmp_path)
    assert state['sources'][0]['qualification']=='STALE'
    assert state['own_evidence'][0]['id']=='result:independent' and state['own_evidence'][0]['currentness']=='CURRENT'
    assert len(execute(tmp_path,'research',{'view':'summary'})['results'])==1


def _two_claims_one_section(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    for section,ids in [('first',['result:first','result:second']),('second',[])]:
        current=execute(tmp_path,'structure',{})
        execute(tmp_path,'structure_change',{'operation':'plan','expected_revision':current['revision'],'op':{'kind':'set-nodes','section':section,'order':ids}})
    bind(tmp_path,key,'result:first');bind(tmp_path,key,'result:second')
    chapter=manuscript/'chapters/chapter-01.tex';chapter.write_text('\\section{First claim}\nOne claim uses a source \\cite{FixtureSource}.\n\nAnother claim in a distinct paragraph has no local cite.\n\\section{Second claim}\nNo claim placed here.\n')
    return manuscript,chapter


def _uses(tmp_path,node):
    value=execute(tmp_path,'literature_scope',{'node':node})
    return value,value['claims'][0]['sources'][0]['manuscript_uses']


def test_file_only_or_unplaced_section_correspondence_never_attributes_a_citation(tmp_path,monkeypatch):
    # The plan sections carry only file/title (FILE_ONLY): a citation in that file is not attributed to them.
    _two_claims_one_section(tmp_path,monkeypatch)
    for node in ['result:first','result:second']:
        value,uses=_uses(tmp_path,node)
        assert uses==[]
        assert {'citekey':'FixtureSource','kind':'not-yet-cited','node_id':node,'source_id':'ref:FixtureSource'} in value['gaps']


def test_same_section_multiple_claims_retain_explicit_coarse_attribution_limits(tmp_path,monkeypatch):
    manuscript,chapter=_two_claims_one_section(tmp_path,monkeypatch)
    # Bind the exact current heading through the existing guarded owner (selection, file and plan guards).
    outline=execute(tmp_path,'structure',{'view':'outline'});summary=execute(tmp_path,'structure',{'view':'summary'})
    heading=next(row for row in outline['headings']['items'] if row['heading_before']=='\\section{First claim}')
    bound=execute(tmp_path,'structure_change',{'operation':'bind_source','section_id':'first','file':heading['file'],
        'line':heading['line'],'heading_before':heading['heading_before'],
        'expected_plan_revision':summary['authority']['plan_revision'],
        'expected_selection':outline['selected_source']['selection_identity'],
        'expected_source_digest':outline['sources'][heading['file']]['source_digest']})
    assert bound['link_established'] and bound['binding']['precision']=='EXACT_HEADING'
    digest=outline['sources'][heading['file']]['source_digest']
    for node in ['result:first','result:second']:
        value,uses=_uses(tmp_path,node)
        assert len(uses)==1;span=uses[0]
        assert span['attribution']=='canonical-section' and set(span['claim_ids'])=={'result:first','result:second'}
        assert span['section_ids']==['first'] and span['citekey']=='FixtureSource' and span['text']=='\\cite{FixtureSource}'
        assert span['file']==heading['file'] and 'sha256:'+span['source_sha256']==digest
        # the unbound section stays named as FILE_ONLY; nothing is inferred from its title or file
        assert span['attribution_limits']==['Section second has FILE_ONLY source correspondence; inspect and bind an exact occurrence.']
        assert 'does not establish paragraph-level entailment' in value['attribution_limits']
        assert not any(gap['kind']=='not-yet-cited' for gap in value['gaps'])
    # A changed heading makes the binding stale: the citation is no longer attributed.
    chapter.write_text('% moved\n\\section{Renamed claim}\nOne claim uses a source \\cite{FixtureSource}.\n\\section{Second claim}\nNo claim placed here.\n')
    value,uses=_uses(tmp_path,'result:first')
    assert uses==[] and any(gap['kind']=='not-yet-cited' for gap in value['gaps'])
