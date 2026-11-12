"""The documented code-mode recipe emits image bytes only to image()."""
import json,shutil,subprocess
import pytest
from laplace.projects import writing_sources
from laplace.native import contracts as writing_contracts
from laplace.writing import operating as writing_operating


@pytest.mark.skipif(shutil.which('node') is None,reason='Node required for code-mode recipe test')
def test_image_recipe_handles_observed_flattening_image_only_multiple_and_structured():
    recipe=writing_contracts.exact_contract('repository',permitted=True)['code_mode_image_recipe']
    first='data:image/png;base64,AAAA';second='data:image/png;base64,BBBB'
    samples=[json.dumps({'pdf_page':2})+'\n'+first,first,first+'\n'+second,
        {'contentItems':[{'type':'inputText','text':'{"pdf_page":2}'},{'type':'inputImage','imageUrl':first}]},
        {'content':[{'type':'text','text':'metadata'},{'type':'image','mimeType':'image/png','data':'AAAA'}]},
        {'unknown_image_blob':'X'*100000},'no image '+'X'*100000]
    script='const recipe='+json.dumps(recipe)+';const samples='+json.dumps(samples)+';const out=samples.map(r=>{const texts=[],images=[];new Function("r","text","image",recipe)(r,x=>texts.push(x),x=>images.push(x));return {texts,images}});process.stdout.write(JSON.stringify(out));'
    result=json.loads(subprocess.run(['node'],input=script,check=True,capture_output=True,text=True).stdout)
    assert [len(row['images']) for row in result]==[1,1,2,1,1,0,0]
    assert result[0]['texts']==['{"pdf_page": 2}']
    assert result[1]['texts']==[]
    assert result[2]['images']==[first,second]
    assert all(len(json.dumps(row['texts']))<6500 for row in result)
    assert all('data:image' not in json.dumps(row['texts']) for row in result)
    assert 'repository_images' in writing_operating.CAPABILITY_GUIDANCE
    assert 'Never text()' in writing_sources.CODE_MODE_IMAGE_GUIDANCE
