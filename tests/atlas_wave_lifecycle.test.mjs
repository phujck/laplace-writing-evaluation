import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const source = fs.readFileSync(new URL('../.claude/workflows/atlas-wave.js', import.meta.url), 'utf8')
  .replace('export const meta =', 'const meta =');
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const execute = new AsyncFunction('args', 'agent', 'parallel', 'log', source);
const schema = name => JSON.parse(fs.readFileSync(new URL('../profiles/workflows/'+name, import.meta.url), 'utf8'));

function plan(version = 2) {
  const packets = ['one', 'dependent'];
  return {wave:'fixture', plan_path:'/fixture/plan.json',out_dir:'/fixture',max_judge_rounds:2,
    agents:packets.map((label,index)=>({label,stage:index+1,feeds:index?['one']:[],
      output:'/fixture/'+label+'.json',check:null,judge:true})),
    stages:[{title:'Stage 1',packets:['one']},{title:'Stage 2',packets:['dependent']}],
    synthesis:null,
    models:{...Object.fromEntries(packets.map(label=>[label,{build:{model:'fixture-model',effort:'high'},
      judge:{model:'fixture-model',effort:'high'}}])),bank:{bank:{model:'fixture-model',effort:'low'}}},
    schemas:{return:schema('packet-return'+(version===2?'.v2':'')+'.schema.json'),
      judgement:schema('packet-judgement'+(version===2?'.v2':'')+'.schema.json')}};
}

async function run(configuration, results) {
  const calls=[];
  const result=await execute(configuration,async(prompt,options)=>{
    calls.push({prompt,options});
    if(options.label==='bank')return {wave_returns:'fixture',wave_rows:'fixture',exit_codes:[0,0]};
    const value=results[options.label];
    assert.ok(value,'Unexpected dispatch '+options.label);
    return value;
  },async tasks=>Promise.all(tasks.map(fn=>fn())),()=>{});
  return {calls,result};
}

for(const status of ['INCOMPLETE','BLOCKED','INTERRUPTED']) {
  test(status+' keeps authored handoff without judge/retry/dependent dispatch',async()=>{
    const {calls,result}=await run(plan(),{'build:one':{return_path:'/fixture/one/return.json',summary:'retained',status}});
    assert.deepEqual(calls.map(call=>call.options.label),['build:one','bank']);
    const first=result.stages['Stage 1'][0],second=result.stages['Stage 2'][0];
    assert.equal(first.status,status);assert.equal(first.standing,status);
    assert.equal(second.standing,'BLOCKED');assert.equal(second.not_dispatched,true);
    assert.deepEqual(second.blocked_by,['one']);
    assert.deepEqual(calls[0].options.schema.properties.status,plan().schemas.return.properties.status);
  });
}

test('complete-but-rejected correction remains allowed and stops on interrupted continuation',async()=>{
  const {calls,result}=await run(plan(),{
    'build:one':{return_path:'/fixture/one/return.json',summary:'checkpoint',status:'COMPLETE'},
    'judge:one:r1':{return_path:'/fixture/one/verdict.r1.json',accepted:false,deficiencies:[{
      id:'fix',item:'fixture',problem:'observed defect',evidence:'independent read',done_looks_like:'correct fixture'}]},
    'continue:one:r1':{return_path:'/fixture/one/return.json',summary:'retained partial fix',status:'INTERRUPTED'}});
  assert.deepEqual(calls.map(call=>call.options.label),['build:one','judge:one:r1','continue:one:r1','bank']);
  assert.equal(result.stages['Stage 1'][0].status,'INTERRUPTED');
});

test('judge guidance follows current canonical owner-read/check definition',async()=>{
  const {calls}=await run({...plan(),agents:[plan().agents[0]],stages:[{title:'Stage 1',packets:['one']}]},{
    'build:one':{return_path:'/fixture/one/return.json',summary:'checkpoint',status:'COMPLETE'},
    'judge:one:r1':{return_path:'/fixture/one/verdict.r1.json',accepted:true,deficiencies:[]}});
  const prompt=calls.find(call=>call.options.label.startsWith('judge:')).prompt;
  assert.ok(prompt.includes('receipt-bound owner-read'));
  const marker='CURRENT CANONICAL RETURN/CHECK GUIDE (data from the schema owner; read its full file):\n';
  const guide=JSON.parse(prompt.split(marker)[1].split('\n\nYOU ARE THE INDEPENDENT JUDGE')[0]);
  assert.deepEqual(guide.definitions,plan().schemas.judgement.$defs);
  assert.ok(!prompt.includes('There is no \'not done\' return'));
  assert.ok(!prompt.includes('whose exit_code is 0'));
});

test('old /1 profiles and explicit judge-first receipt remain supported',async()=>{
  const configuration=plan(1);
  configuration.agents=[{...configuration.agents[0],judge_first:true}];
  configuration.stages=[{title:'Stage 1',packets:['one']}];
  configuration.prior={one:{return_path:'/fixture/old-return.json',summary:'old receipt'}};
  const {calls}=await run(configuration,{'judge:one:r1':{return_path:'/fixture/verdict.json',accepted:true,deficiencies:[]}});
  assert.deepEqual(calls.map(call=>call.options.label),['judge:one:r1','bank']);
});
