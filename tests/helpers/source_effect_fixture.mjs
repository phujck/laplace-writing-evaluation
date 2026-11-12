import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
// Physical fixtures are observed by the actual owner in a disposable directory.
// Native compaction and saved-action projection consume those same receipts.
// The tracked selector is run exactly as scripts/laplace-python runs it (-I -S -B), with the interpreter the
// caller selected (LAPLACE_TEST_PYTHON) or the launcher's own /usr/bin/python3, so a read-only staged
// checkout without an executable launcher bit observes the same owner.
const selector = fileURLToPath(new URL('../../scripts/laplace_python.py', import.meta.url));
const interpreter = process.env.LAPLACE_TEST_PYTHON || '/usr/bin/python3';
export const fixtures = JSON.parse(execFileSync(interpreter, ['-I', '-S', '-B', selector, '-c', String.raw`
import json,tempfile
from pathlib import Path
from laplace.manuscript import source_effects as owner
from laplace.native import tools as writing_tools
with tempfile.TemporaryDirectory(prefix='source-effect-consumer-') as directory:
 root=Path(directory); path=root/'main.tex'; other=root/'other.tex'
 result={}; selection='sha256:'+'b'*64
 for name,final,complete in [('unchanged',b'before',True),('committed',b'after',True),('incomplete',b'after',False),('rollback',b'before',False),('partial',b'foreign',False)]:
  path.write_bytes(final)
  intended=b'before' if name=='unchanged' else b'after'
  files=[owner.observed_file(root,path,b'before',intended)]
  effect=owner.receipt('book',selection,files,complete=complete,required=[{'owner':'fixture-domain','status':'COMPLETE' if complete else 'FAILED'}])
  packet=owner.finish({'ok':complete},'book',root,effect,heading_sync={'status':'NOT_NEEDED'})
  packet['action_receipt']=writing_tools._action_summary('book','apply_revision',{},packet)
  result[name]={'result':packet,'native':writing_tools._compact_write_response('book','apply_revision',{},packet),'action':packet['action_receipt']}
 path.write_bytes(b'before')
 effect=owner.receipt('book',selection,[owner.observed_file(root,path,b'before',b'before')],complete=False,required=[{'owner':'metadata','status':'FAILED'}])
 result['unchanged_incomplete']={'result':owner.finish({'ok':False},'book',root,effect,heading_sync={'status':'NOT_NEEDED'})}
 files=[owner.observed_file(root,path,b'before',b'after')];files[0]['observation_error']='fixture observation unavailable';files[0]['observed_after_sha256']=None
 result['unproved']={'result':owner.finish({'ok':False},'book',root,owner.receipt('book',selection,files,complete=False),heading_sync={'status':'NOT_NEEDED'})}
 optional=json.loads(json.dumps(result['committed']['result']));optional['source_effect']['follow_through']['maintenance_warnings']=[{'operation':'fixture-maintenance','reason':'unavailable'}];result['optional']={'result':optional}
 bad_steps=[{'owner':'fixture-domain','status':'FAILED'}]
 forced=owner.receipt('book',selection,result['committed']['result']['source_effect']['files'],complete=True,required=bad_steps)
 result['constructor_invariant']=forced
 error=owner.SourceEffectFailure(ValueError('required fixture tracking failed'),result['incomplete']['result']['source_effect'])
 saved=writing_tools.bank_failure(root,'book','section_change',{},error)
 result['saved_failure']=next(json.loads(line) for line in (root/'contract/talk.jsonl').read_text().splitlines() if json.loads(line).get('id')==saved['row_id'])
 print(json.dumps(result))
`], {cwd:new URL('../..', import.meta.url),env:{...process.env,PYTHONPATH:'src'},encoding:'utf8'}));

