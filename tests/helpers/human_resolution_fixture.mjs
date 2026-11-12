import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const generated=spawnSync('./scripts/laplace-python',['-c',String.raw`
import json,tempfile,sys
from pathlib import Path
import pytest
sys.path.insert(0,'tests')
from test_human_reconciliation import current_candidate,prepared_case,target
from laplace.manuscript import manuscript_proposals,projection_viewer,proposal_navigation; from laplace.web import authoring as authoring_surface
from laplace.manuscript import reconciliation
monkey=pytest.MonkeyPatch()
with tempfile.TemporaryDirectory(prefix='laplace-human-ui-consumer-') as raw:
 make=getattr(current_candidate,'__wrapped__',None) or current_candidate._get_wrapped_function()
 case=make(Path(raw),monkey);root,md,source,selector=case
 prepared,payload=prepared_case(case)
 required=reconciliation.prepare(root,'fixture',selector)
 monkey.setattr(projection_viewer,'_repo_root',lambda:root)
 status,_,body=projection_viewer.handle('/projection/tex',{'corpus':['fixture'],'file':[prepared['target']['file']],'view':['source']},'GET',b'')
 assert status==200
 observed=json.loads(body)
 preview=manuscript_proposals.decide(root,'fixture',{**prepared['actions']['preview']['payload'],'choices':payload['choices']})
 unchanged=manuscript_proposals.decide(root,'fixture',{**prepared['actions']['preview']['payload'],'choices':[
  {'hunk_id':hunk['id'],'choice':'current'} for hunk in prepared['hunks']]})
 previous_limit=reconciliation.MAX_COMPARE_REGIONS
 monkey.setattr(reconciliation,'MAX_COMPARE_REGIONS',1)
 coarse=reconciliation.prepare(root,'fixture',{**selector,'target':target(root,md,source)})
 monkey.setattr(reconciliation,'MAX_COMPARE_REGIONS',previous_limit)
 previous_source=(md/'main.tex').read_text()
 (md/'main.tex').write_text(previous_source+'\n% unrelated source note\n')
 harmless=reconciliation.prepare(root,'fixture',{**selector,'target':target(root,md,source)})
 (md/'main.tex').write_text(previous_source)
 applied=manuscript_proposals.decide(root,'fixture',payload)
 fresh=reconciliation.prepare(root,'fixture',{**selector,'target':target(root,md,source)})
 original_history=proposal_navigation.read(root,'fixture',{'id':selector['turn_id'],'proposal_version':selector['proposal_version'],'edit_id':selector['edit_id'],'view':'preview'})
 pending_monkey=pytest.MonkeyPatch()
 with tempfile.TemporaryDirectory(prefix='laplace-resolution-record-ui-') as pending_raw:
  pending_case=make(Path(pending_raw),pending_monkey);pending_root,pending_md,_,_=pending_case
  pending_prepared,pending_payload=prepared_case(pending_case)
  pending_preview=manuscript_proposals.decide(pending_root,'fixture',{**pending_prepared['actions']['preview']['payload'],'choices':pending_payload['choices']})
  bank=authoring_surface._bank
  with pending_monkey.context() as outage:
   def fail_disposition(path,row):
    if row.get('record')=='writing-proposal-decision' and row.get('decision')=='resolved-into-successor':raise OSError('Simulated disposition publication outage')
    return bank(path,row)
   outage.setattr(authoring_surface,'_bank',fail_disposition)
   pending_receipt=manuscript_proposals.decide(pending_root,'fixture',pending_payload)
  pending_selector=pending_case[3]
  pending_history=proposal_navigation.read(pending_root,'fixture',{'id':pending_selector['turn_id'],'proposal_version':pending_selector['proposal_version'],'edit_id':pending_selector['edit_id'],'view':'preview'})
  pending_source=pending_md/'main.tex'
  pending_source.write_text(pending_source.read_text()+'\n% Later unrelated source change\n')
  source_before_finish=pending_source.read_bytes()
  finished_receipt=manuscript_proposals.decide(pending_root,'fixture',pending_receipt['disposition']['recovery_action']['payload'])
  assert pending_source.read_bytes()==source_before_finish
 pending_monkey.undo()
 print(json.dumps({'prepared':prepared,'apply_payload':payload,'preview':preview,'unchanged':unchanged,
  'receipt':applied,'original_history':original_history,'pending_receipt':pending_receipt,'pending_prepared':pending_prepared,'pending_history':pending_history,'pending_preview':pending_preview,'finished_receipt':finished_receipt,'fresh':fresh,'harmless':harmless,'coarse':coarse,'target_required':required,'source':observed,'after':(md/'main.tex').read_text()}))
monkey.undo()
`],{cwd:fileURLToPath(new URL('../..',import.meta.url)),encoding:'utf8',timeout:30000});
assert.equal(generated.status,0,generated.stderr);
export const humanWire=JSON.parse(generated.stdout);
