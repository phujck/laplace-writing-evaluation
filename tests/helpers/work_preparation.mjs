// The owner's review-phase preparation for hand-built frontend fixtures (repair1 WI-R1): the recorder renders only what
// project_work_review.preparation returns, so a fixture asks the REAL owner function for it instead of restating phases,
// inputs or bases in test code. One Python call per distinct (facet, phases, guard), cached for the test process.
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
const ROOT=fileURLToPath(new URL('../..',import.meta.url)),cache=new Map();
const CODE='import json,sys\nfrom laplace.work import project_work_review as r\nfacet,phases,guard=json.load(sys.stdin)\nprint(json.dumps(r.preparation(facet,phases,guard)))';
export function ownerPreparation(facet,phases,guard){
  const key=JSON.stringify([facet,phases,guard]);
  if(!cache.has(key)){const result=spawnSync('./scripts/laplace-python',['-c',CODE],{cwd:ROOT,input:key,encoding:'utf8',timeout:60000});
    if(result.status!==0)throw Error(result.stderr||'the owner preparation refused');cache.set(key,JSON.parse(result.stdout));}
  return structuredClone(cache.get(key));
}
// an owner-shaped work_review action for a fixture facet
export const reviewAction=(id,guard,facet,phases)=>({operation:'work_review',permitted:true,project:'fixture',payload:{id,expected_work_revision:guard},phases,
  http:{method:'POST',url:'/work/review'},preparation:ownerPreparation(facet,phases,guard)});
