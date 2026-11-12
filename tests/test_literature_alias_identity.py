"""Source aliases resolve to one edition identity before observation or binding."""
import copy,json,shutil,time
import pytest
from laplace.research import literature, literature_support, references_surface, corpus_ingest
from laplace.native import tools as writing_tools
from test_literature_joined_workflow import project,execute,bind_heading


def association_rows(manuscript):return json.loads((manuscript/'references.json').read_text())['associations']


def bind_alias(root,key,receipt):
    return execute(root,'literature_bind',{'key':key,'claim_id':'result:first','relation':'supports',
        'rationale':'The observed source supports the bounded controlled statement.','reading_status':'partial',
        'reading_id':receipt['id'],'evidence':{'locator':receipt['locator']}})


@pytest.mark.skipif(shutil.which('latexmk') is None,reason='latexmk unavailable')
def test_alias_read_bind_and_real_compilation_reuse_existing_identity(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    read=execute(tmp_path,'reference_text',{'key':'FixtureSource'})
    assert read['key']==key and read['requested_key']=='FixtureSource'
    assert read['reading_receipt']['reference_key']==key
    assert {row['key'] for row in association_rows(manuscript)}=={key}
    bound=bind_alias(tmp_path,'FixtureSource',read['reading_receipt'])
    assert bound['association']['key']==key and bound['association']['citekey']=='FixtureSource'
    assert bound['canonical_source']=='ref:FixtureSource'
    assert execute(tmp_path,'literature_uses',{'key':'FixtureSource'})['uses']
    for alias in (key,'FixtureSource','ref:FixtureSource'):
        assert execute(tmp_path,'reference_text',{'key':alias})['key']==key
    rows=association_rows(manuscript)
    assert len(rows)==2 and {row['key'] for row in rows}=={key}
    citations=[node for node in literature_support.network('joined',tmp_path)['nodes'].values() if node.get('kind')=='citation']
    assert len(citations)==1
    chapter=manuscript/'chapters/chapter-01.tex';chapter.write_text(chapter.read_text().replace('First passage.','First passage \\cite{FixtureSource}.'))
    # Citation text and a complete bibliography do not establish attribution.
    # Assert the exact FILE_ONLY/not-yet-cited defect independently of build.
    unbound=execute(tmp_path,'literature_scope',{'node':'result:first'})
    unbound_source=unbound['claims'][0]['sources'][0]
    assert unbound_source['qualification']=='PASSAGE_OBSERVED'
    assert unbound_source['manuscript_uses']==[]
    assert any(g['kind']=='not-yet-cited' for g in unbound['gaps'])
    assert not unbound['ready_for_completion']
    sections=execute(tmp_path,'structure',{'view':'detail','section_ids':['first','second']})['sections']
    assert {row['source']['precision'] for row in sections}=={'FILE_ONLY'}
    for sid,heading in [('first','\\section{First claim}'),('second','\\section{Second claim}')]:
        assert bind_heading(tmp_path,sid,heading)['binding']['precision']=='EXACT_HEADING'
    attributed=execute(tmp_path,'literature_scope',{'node':'result:first'})
    uses=attributed['claims'][0]['sources'][0]['manuscript_uses']
    assert len(uses)==1 and uses[0]['claim_ids']==['result:first']
    assert uses[0]['section_ids']==['first']
    assert not any(g['kind']=='not-yet-cited' for g in attributed['gaps'])
    assert execute(tmp_path,'literature_uses',{'claim_id':'result:second'})['uses']==[]
    assert len([n for n in literature_support.network('joined',tmp_path)['nodes'].values()
                if n.get('kind')=='citation'])==1
    assert {row['key'] for row in association_rows(manuscript)}=={key}
    execute(tmp_path,'build',{})
    for _ in range(150):
        status=execute(tmp_path,'build_status',{})
        if not status.get('running'):break
        time.sleep(.1)
    assert status.get('ok') and status.get('fresh'),status
    coverage=execute(tmp_path,'literature_scope',{'node':'result:first'})
    assert coverage['ready_for_completion'],coverage['gaps']
    assert 'FixtureSource' in coverage['bibliography']['rendered_keys']
    assert coverage['claims'][0]['sources'][0]['manuscript_uses'][0]['claim_ids']==['result:first']


def test_legacy_alias_shadow_is_repaired_without_another_source_node(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    read=execute(tmp_path,'reference_text',{'key':key})
    rows=association_rows(manuscript);primary=rows[0]
    ghost='cite:legacy-source'
    assert corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'add-node','node':ghost,'node_kind':'citation','essence':primary['metadata']['title'],
        'projection':{'bibliography':{'reference_key':'FixtureSource','citekey':None}}}).get('ok')
    assert corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'add-edge','node':'result:first','target':ghost,'rel':'support','rationale':'Earlier alias binding.'}).get('ok')
    shadow={'key':'FixtureSource','metadata':copy.deepcopy(primary['metadata']),'source':{'provider':'local'},'state':'CURRENT','bibliography_state':'NOT_LINKED','reading_observations':[read['reading_receipt']]}
    bound={**copy.deepcopy(shadow),'claim_id':'result:first','canonical_id':ghost,'binding_state':'BOUND','relation':'supports','rationale':'Earlier alias binding.',
        'reading_receipt':read['reading_receipt'],'claim_revision':literature_support.meaning_revision('joined','result:first',tmp_path)}
    references_surface._write_associations(manuscript,rows+[shadow,bound])
    before_nodes=set(literature_support.network('joined',tmp_path)['nodes'])
    repaired_read=execute(tmp_path,'reference_text',{'key':'FixtureSource'})
    result=bind_alias(tmp_path,'FixtureSource',repaired_read['reading_receipt'])
    assert result['canonical_source']==ghost
    assert set(literature_support.network('joined',tmp_path)['nodes'])==before_nodes
    repaired=association_rows(manuscript)
    assert len(repaired)==2 and {row['key'] for row in repaired}=={key}
    assert all(row['citekey']=='FixtureSource' for row in repaired)
    assert any(row.get('identity_history') for row in repaired)
    node=literature_support.network('joined',tmp_path)['nodes'][ghost]
    assert node['projection']['bibliography']['citekey']=='FixtureSource'
    assert result['support']['sources'][0]['citekey']=='FixtureSource'


def test_eight_character_citekey_and_distinct_editions_are_not_zotero_or_merged(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    other=tmp_path/'other-edition.txt';other.write_text('Different edition with a different bounded claim.')
    saved=execute(tmp_path,'literature_import',{'metadata':{'title':'Controlled source','creators':['Fixture Author'],'year':'2027','item_type':'unpublished'},
        'provenance':{'description':'A distinct supplied edition','path':str(other)},'citekey':'ABCDEFGH'})
    class NoZotero:
        def item(self,key):raise AssertionError('A registered local citekey must not query Zotero')
    monkeypatch.setattr(references_surface,'Library',NoZotero)
    assert execute(tmp_path,'reference',{'key':'ABCDEFGH'})['item']['key']==saved['association']['key']
    read=execute(tmp_path,'reference_text',{'key':'ABCDEFGH'})
    assert read['key']==saved['association']['key']!=key
    assert 'Different edition' in read['text']
    assert len(association_rows(manuscript))==2


def test_doi_aliases_and_fetch_use_the_same_registered_key(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    monkeypatch.setattr(references_surface,'_crossref',lambda **kwargs:[{'DOI':'10.5555/alias-audit','title':['DOI fixture'],'author':[{'given':'Test','family':'Author'}],'type':'journal-article','issued':{'date-parts':[[2026]]}}])
    saved=execute(tmp_path,'literature_import',{'doi':'10.5555/alias-audit','citekey':'DoiFixture'})
    canonical=saved['association']['key']
    monkeypatch.setattr(literature,'_download',lambda url:(b'This is accessible text from an isolated DOI identity test. It supplies no scientific conclusion.','text/plain',url))
    fetched=execute(tmp_path,'reference_fetch',{'key':'DoiFixture','url':'https://example.org/fixture.txt'})
    assert fetched['key']==canonical
    for alias in ('DoiFixture','10.5555/alias-audit','https://doi.org/10.5555/alias-audit',canonical):
        read=execute(tmp_path,'reference_text',{'key':alias})
        assert read['key']==canonical and read['reading_receipt']['reference_key']==canonical
    assert {row['key'] for row in association_rows(manuscript)}=={key,canonical}


def test_alias_metadata_update_reuses_the_existing_bibliography_entry(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    updated=execute(tmp_path,'reference_update',{'key':'FixtureSource','metadata':{'title':'Corrected source title'}})
    assert updated['key']==key
    assert {row['key'] for row in association_rows(manuscript)}=={key}
    entries=references_surface._bib_entries((manuscript/'refs.bib').read_text())
    assert len(entries)==1 and entries[0]['key']=='FixtureSource'
    assert 'Corrected source title' in entries[0]['text']


def test_original_canonical_source_handle_reuses_later_bibliographic_identity(tmp_path,monkeypatch):
    manuscript,source,key,original=project(tmp_path,monkeypatch)
    supplied=tmp_path/'prior-source.txt';supplied.write_text('A previously declared source with a bounded controlled statement.')
    ident='cite:prior-source'
    assert corpus_ingest.rewire_add(tmp_path,'joined',{'kind':'add-node','node':ident,'node_kind':'citation','essence':'Prior source','ref':str(supplied.relative_to(tmp_path))}).get('ok')
    assert execute(tmp_path,'reference_text',{'key':ident})['key']==ident
    saved=execute(tmp_path,'literature_import',{'metadata':{'title':'Prior source','creators':['Prior Author'],'year':'2026','item_type':'unpublished'},
        'provenance':{'description':'Explicit bibliography mapping of the prior canonical source'},'citekey':'PriorSource','canonical_id':ident})
    canonical=saved['association']['key']
    observed=execute(tmp_path,'reference_text',{'key':ident})
    assert observed['key']==canonical and 'previously declared source' in observed['text']
    linked=bind_alias(tmp_path,ident,observed['reading_receipt'])
    assert linked['canonical_source']==ident and linked['association']['citekey']=='PriorSource'
    assert not any(row['key']==ident for row in association_rows(manuscript))
