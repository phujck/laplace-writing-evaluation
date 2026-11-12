// Wave 9, the Workflows page as topology: the reading order of stages, the review-loop words, the
// three run marks, live-first run order, and the two drawing edits (add a stage after one, swap two).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {installDOM} from './helpers/evidence_reader_harness.mjs';
import {workflowStageLayout,workflowLoopWords,workflowRunMarks,workflowRunsOrder,workflowMiniDrawing} from '../src/laplace/web/static_shared/workspace-workflow-editor.mjs';
import {editWorkflow,workflowSwapBlocker} from '../src/laplace/web/static_shared/workflow-port.mjs';
const step=(id,title,role='builder')=>({id,title,parent_id:null,assignment:{role,instructions:'',settings:{}},inputs:[],outputs:[]});
const starter={title:'Draft, review',run_policy:{max_iterations:2,advance:'automatic-review',apply:'human'},steps:[step('write','Draft proposal'),step('review','Independent review','adversary')],edges:[{id:'e1',from:'write',to:'review',kind:'control'},{id:'e2',from:'review',to:'write',kind:'feedback'}],layout:{}};

test('stages are ranked by forward arrows only; a feedback arrow is a loop with the owner bound in words',()=>{
  const layout=workflowStageLayout(starter);
  assert.deepEqual(layout.columns.map(column=>column.map(row=>row.id)),[['write'],['review']]);
  assert.deepEqual(layout.loops.map(row=>row.id),['e2']);
  assert.equal(workflowLoopWords(starter,layout.loops[0]),'Sent back from Independent review to Draft proposal · at most 2 review rounds');
  assert.equal(workflowLoopWords({...starter,run_policy:undefined},layout.loops[0]),'Sent back from Independent review to Draft proposal','no bound is said where the owner states none');
  const parallel={steps:[step('a','A'),step('b','B'),step('c','C')],edges:[{id:'1',from:'a',to:'b',kind:'control'},{id:'2',from:'a',to:'c',kind:'data'}]};
  assert.deepEqual(workflowStageLayout(parallel).columns.map(column=>column.map(row=>row.id)),[['a'],['b','c']]);
});

test('the row drawing names every stage in order with arrows and the loop',()=>{
  const dom=installDOM();try{const drawing=workflowMiniDrawing(starter);assert.match(drawing.textContent,/Draft proposal→Independent review↺ Sent back/);assert.match(drawing.getAttribute('aria-label'),/Stages: Draft proposal, then Independent review/);assert.match(workflowMiniDrawing({steps:[],edges:[]}).textContent,/No stages yet/);}finally{dom.restore();}
});

test('run marks keep planned, admitted and observed apart and link only an observed conversation',()=>{
  assert.deepEqual(workflowRunMarks(undefined),{planned:true,admitted:false,state:null,observed:false,conversation:null});
  assert.deepEqual(workflowRunMarks({state:'NOT_STARTED'}),{planned:true,admitted:true,state:'NOT_STARTED',observed:false,conversation:null});
  const conversation={project_url:'/project?corpus=p&session=s1',session_id:'s1',project:'p'};
  assert.deepEqual(workflowRunMarks({state:'RUNNING',current_attempt:{observed:true},conversation}),{planned:true,admitted:true,state:'RUNNING',observed:true,conversation});
  assert.equal(workflowRunMarks({state:'RUNNING',current_attempt:{observed:false},conversation}).conversation,null);
});

test('runs whose task is not finished come first, owner order kept inside each group',()=>{
  const items=['done','open','cancelled','in-progress','verified','blocked'].map((recorded_status,i)=>({work_id:'w'+i,recorded_status}));
  assert.deepEqual(workflowRunsOrder(items).map(row=>row.recorded_status),['open','in-progress','blocked','done','cancelled','verified']);
});

test('a stage added after one takes over its forward arrows; swapping two stages keeps the drawing shape',()=>{
  const added=editWorkflow(starter,{type:'insert-after',after:'write',id:'check',edge_id:'e3'});
  assert.deepEqual(added.steps.map(row=>row.id),['write','check','review']);
  assert.deepEqual(added.edges.map(row=>[row.from,row.to,row.kind]),[['check','review','control'],['review','write','feedback'],['write','check','control']]);
  assert.deepEqual(workflowStageLayout(added).order.map(row=>row.id),['write','check','review']);
  const swapped=editWorkflow(added,{type:'swap',a:'check',b:'review'});
  assert.deepEqual(workflowStageLayout(swapped).order.map(row=>row.id),['write','review','check']);
  assert.equal(swapped.steps.find(row=>row.id==='review').assignment.role,'adversary','a stage keeps its own settings when it moves');
  const removed=editWorkflow(added,{type:'remove',id:'check'});
  assert.deepEqual(workflowStageLayout(removed).order.map(row=>row.id),['write','review'],'removing a middle stage keeps the chain');
  assert.deepEqual(removed.edges.filter(row=>row.kind==='control').map(row=>[row.from,row.to]),[['write','review']],'one control arrow bridges the removed stage');
  assert.ok(removed.edges.some(row=>row.from==='review'&&row.to==='write'&&row.kind==='feedback'),'the review loop is kept');
  const shape=body=>body.edges.map(row=>[row.from,row.to,row.kind]);
  assert.deepEqual(shape(editWorkflow(added,{type:'remove',id:'check',bridge:false})),shape(removed),'there is one remove behaviour: no flag changes it');
  assert.throws(()=>editWorkflow(starter,{type:'swap',a:'write',b:'write'}),/two different stages/);
  assert.throws(()=>editWorkflow(starter,{type:'insert-after',after:'missing'}),/Choose a stage/);
  assert.deepEqual(starter.steps.map(row=>row.id),['write','review'],'the draft given is not changed in place');
});

test('two stages trade places only where no hand-over or context choice names them; a moved draft passes the owner shape',()=>{
  const plain=editWorkflow(starter,{type:'swap',a:'write',b:'review'});
  assert.deepEqual(plain.steps.map(row=>row.id),['review','write']);
  assert.deepEqual(plain.edges.map(row=>[row.from,row.to,row.kind]),[['review','write','control'],['write','review','feedback']],'every arrow keeps its place, so the moved stages trade arrows');
  assert.equal(workflowSwapBlocker(starter,'write','review'),null);
  const named={...starter,steps:[{...starter.steps[0],assignment:{...starter.steps[0].assignment,handoff:{downstream:['review']}}},starter.steps[1]]};
  assert.match(workflowSwapBlocker(named,'write','review'),/Draft proposal names Independent review in its hand-over/);
  assert.throws(()=>editWorkflow(named,{type:'swap',a:'write',b:'review'}),/names Independent review in its hand-over/,'a swap that would leave a draft Save refuses is not made');
  const reads={...starter,steps:[starter.steps[0],{...starter.steps[1],assignment:{...starter.steps[1].assignment,context:[{kind:'upstream-return',step_id:'write'}]}}]};
  assert.match(workflowSwapBlocker(reads,'write','review'),/reads Draft proposal in its context choices/);
  const three={...starter,steps:[...starter.steps,step('apply','Apply')],edges:[...starter.edges,{id:'e3',from:'review',to:'apply',kind:'control'}]};
  const other={...three,steps:three.steps.map(row=>row.id==='apply'?{...row,assignment:{...row.assignment,context:[{kind:'upstream-return',step_id:'review'}]}}:row)};
  assert.match(workflowSwapBlocker(other,'write','review'),/Apply reads Independent review/,'a third stage that names a moved stage blocks the move too');
  assert.equal(workflowSwapBlocker(three,'review','apply'),null,'where nothing names the moved stages the move stays offered');
});
