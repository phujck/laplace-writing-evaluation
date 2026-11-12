// The typed topology view: one array paints the graph and the relation list, ranks follow the
// typed direction, groups are honoured, and boundaries read only through owner handles.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {installDOM,Node,findButton} from './helpers/evidence_reader_harness.mjs';
import {layoutTopology,topologyRows,mountTopology,foldPlan,TOPOLOGY_EDGE_KINDS,CARD,GRID_COLUMNS,FOLD_ABOVE,FOCUS_NEIGHBOURS,FOLD_PAGE} from '../src/laplace/web/static_shared/workspace-topology.mjs';

const nodes=[{id:'A',title:'Campaign'},{id:'B',title:'Child'},{id:'C',title:'Prerequisite'}];
const edges=[{kind:'contains',source:'A',target:'B'},{kind:'requires',source:'B',target:'C'},{kind:'targets-logical-node',source:'B',target:'logical::x'}];

test('ranks follow the typed direction: containers above members, prerequisites above the work that waits on them',()=>{
 const layout=layoutTopology(nodes,edges);
 assert.equal(layout.rank.get('A'),0);assert.equal(layout.rank.get('B'),1);assert.equal(layout.rank.get('C'),0,'a prerequisite is ranked above its dependent');
 const hinted=layoutTopology(nodes,edges,{hints:{rank:{C:2},groups:[{id:'g',title:'Group',nodes:['A','B']}]}});
 assert.equal(hinted.rank.get('C'),2);assert.equal(hinted.groups.length,1);assert.ok(hinted.groups[0].w>0&&hinted.groups[0].h>0);
 const cyclic=layoutTopology([{id:'x'},{id:'y'}],[{kind:'contains',source:'x',target:'y'},{kind:'contains',source:'y',target:'x'}]);
 assert.ok([...cyclic.rank.values()].every(Number.isInteger),'a cycle yields finite ranks');
 assert.deepEqual([...layout.positions.keys()].sort(),['A','B','C']);
});

test('relation rows are one per typed edge with both ends labelled and boundaries marked',()=>{
 const rows=topologyRows(nodes,[...edges,edges[0]],[{id:'logical::x'}]);
 assert.equal(rows.length,3,'a repeated edge is one row');
 assert.deepEqual(rows.map(row=>row.label),['Contains','Requires','Targets']);
 assert.equal(rows[0].sourceLabel,'Campaign');assert.equal(rows[0].targetLabel,'Child');
 assert.equal(rows[2].targetOutside.id,'logical::x');assert.equal(rows[2].note,TOPOLOGY_EDGE_KINDS['targets-logical-node'].note);
});

test('the mounted view lists every relation, selects through the owner id and expands boundaries only through a handle',async()=>{
 const d=installDOM();try{
  const host=new Node('section'),selected=[],expanded=[];
  const view=mountTopology(host,{title:'Neighbourhood',nodes,edges,boundaries:[{id:'logical::x'},{id:'Z',read_handle:{http:{method:'GET',url:'/work/state?project=p&view=detail&id=Z'}}}],selected:'B',onSelect:id=>selected.push(id),onExpand:row=>expanded.push(row.id),chip:node=>node.id==='B'?{label:'blocked',tone:'blocked'}:null});
  const region=host.querySelector('.topology');assert.ok(region);assert.equal(region.dataset.control,'topology:view');
  assert.equal(region.querySelectorAll('.topology-card').length,3);assert.equal(region.all().find(n=>n.dataset.topologyNode==='B').attrs['aria-current'],'true');
  assert.ok(region.textContent.includes('blocked'),'the owner chip travels with the card');
  const rows=region.querySelectorAll('li');assert.equal(rows.length,3);
  await rows[0].all().find(n=>n.tag==='button').onclick();assert.deepEqual(selected,['B']);
  const logical=rows[2];assert.ok(logical.textContent.includes('not an execution prerequisite'));assert.equal(logical.all().find(n=>n.tag==='button'),undefined,'a logical target is a note, not a door');
  view.update({nodes:[{id:'Y',title:'Later page'}],edges:[{kind:'requires',source:'Y',target:'Z'}]});
  const added=region.querySelectorAll('li').find(row=>row.textContent.includes('Later page'));assert.ok(added.textContent.includes('outside this page · read'));
  await added.all().find(n=>n.tag==='button').onclick();assert.deepEqual(expanded,['Z']);
  assert.equal(view.rows.length,4);view.destroy();assert.equal(host.querySelector('.topology'),null);
 }finally{d.restore();}
});

// Sol topology-controls (2026-10-14): both ends of a relation are doors when the owner page makes
// them readable; Fit contains the whole world on a wide page; appended pages retain nodes.
test('an incoming edge from a readable boundary makes the source end a door to its owner, and the inside end still selects',async()=>{
 const d=installDOM();try{
  const host=new Node('main'),selected=[],expanded=[];
  mountTopology(host,{nodes:[{id:'inside',title:'Visible child'}],edges:[{kind:'contains',source:'outside',target:'inside'}],
   boundaries:[{id:'outside',available:true,read_handle:{http:{method:'GET',url:'/work/state?project=p&view=detail&id=outside'}}}],onSelect:id=>selected.push(id),onExpand:row=>expanded.push(row.id)});
  const row=host.querySelector('li'),buttons=row.all().filter(n=>n.tag==='button');
  assert.deepEqual(buttons.map(n=>n.textContent),['outside','Visible child']);assert.ok(row.textContent.includes('from outside this page · read'));
  await buttons[0].onclick();assert.deepEqual(expanded,['outside']);assert.deepEqual(selected,[]);
  await buttons[1].onclick();assert.deepEqual(selected,['inside']);
  const inert=new Node('main');mountTopology(inert,{nodes:[{id:'inside',title:'Visible child'}],edges:[{kind:'contains',source:'gone',target:'inside'}],boundaries:[{id:'gone',available:false}],onExpand:()=>assert.fail('unavailable')});
  const inertRow=inert.querySelector('li');assert.deepEqual(inertRow.all().filter(n=>n.tag==='button').map(n=>n.textContent),['Visible child']);assert.ok(inertRow.textContent.includes('from outside this page · unavailable'));
 }finally{d.restore();}
});
test('Fit contains a valid fifty-node page without a scale floor, zoom stays coherent with it, and an appended page keeps the nodes already shown',async()=>{
 const d=installDOM();
 try{
  document.createElementNS=(_ns,tag)=>new Node(tag);
  Object.defineProperty(Node.prototype,'clientWidth',{configurable:true,get:()=>760});Object.defineProperty(Node.prototype,'clientHeight',{configurable:true,get:()=>420});
  const nodes=[{id:'parent',title:'Parent'},...Array.from({length:49},(_,i)=>({id:'child-'+i,title:'Child '+i}))];const edges=nodes.slice(1).map(n=>({kind:'contains',source:'parent',target:n.id}));
  // an unfolded wide rank wraps into GRID_COLUMNS per row (no longer one 49-card strip)
  const layout=layoutTopology(nodes,edges,{width:760});assert.ok(layout.world.w<760*2&&layout.world.h>CARD.h*8,'a wide rank wraps into a grid');
  const host=new Node('main');d.body.append(host);const view=mountTopology(host,{nodes,edges});view.unfold();
  const box=()=>host.querySelector('svg').attrs.viewBox.split(' ').map(Number);
  const named=label=>host.all().find(n=>n.tag==='button'&&n.attrs['aria-label']===label);
  const contains=b=>b[0]<=0&&b[0]+b[2]>=layout.world.w&&b[1]<=0&&b[1]+b[3]>=layout.world.h;
  assert.ok(contains(box()),'the first paint fits the world');
  await named('Zoom in').onclick();assert.ok(!contains(box()),'zooming in narrows the view');
  await findButton(host,'Fit').onclick();assert.ok(contains(box()),'Fit contains every card again');
  assert.ok(Math.abs(760/box()[2]-Math.min(760/layout.world.w,420/layout.world.h))<1e-9,'Fit uses exactly the containing scale');
  await named('Zoom out').onclick();assert.ok(contains(box()),'zooming out below Fit is allowed no further than the containing scale');
  view.update({nodes:[{id:'child-49',title:'Child 49'}],edges:[{kind:'contains',source:'parent',target:'child-49'}]});
  assert.equal(host.querySelectorAll('.topology-card').length,51,'an appended page retains and repaints the accumulated nodes');
  view.destroy();
 }finally{delete Node.prototype.clientWidth;delete Node.prototype.clientHeight;delete document.createElementNS;d.restore();}
});

// ACTUAL-C4-GRAPH-READABILITY and repair H4 (2026-10-14): a wide rank folds to a BOUNDED focus (the
// selected node and at most FOCUS_NEIGHBOURS direct relations) plus one counted fold card that descends
// FOLD_PAGE cards at a time into a GRID_COLUMNS grid; the list keeps every edge; nothing is inferred.
function fifty(){const nodes=[{id:'parent',title:'Parent'},...Array.from({length:49},(_,i)=>({id:'child-'+i,title:'Child '+i}))];return {nodes,edges:nodes.slice(1).map(n=>({kind:'contains',source:'parent',target:n.id}))};}
const geometry=(layout,pane)=>{const k=Math.min(1,pane.w/layout.world.w,pane.h/layout.world.h);return {k,label:12*k,card:{w:CARD.w*k,h:CARD.h*k}};};
test('fold plans: a selected leaf keeps itself and its parent; a selected parent keeps five of forty-nine children; descent is paged; counts stay exact',()=>{
 const {nodes,edges}=fifty();
 const leaf=foldPlan(nodes,edges,{selected:'child-3'});
 assert.deepEqual(leaf.wide,[1]);assert.equal(leaf.folds.length,1);assert.equal(leaf.folds[0].count,48);assert.equal(leaf.folds[0].total,49);assert.equal(leaf.folds[0].shown,1);
 assert.ok(!leaf.folded.has('child-3')&&!leaf.folded.has('parent')&&leaf.folded.has('child-4'));
 const parent=foldPlan(nodes,edges,{selected:'parent'});
 assert.equal(parent.folds.length,1,'a selected parent with 49 direct children is bounded, not 49 protected cards (Sol H4)');
 assert.equal(parent.folds[0].count,49-FOCUS_NEIGHBOURS);assert.equal(parent.folds[0].shown,FOCUS_NEIGHBOURS);assert.equal(parent.folds[0].related,49);
 assert.deepEqual(['child-0','child-1','child-2','child-3','child-4'].map(id=>parent.folded.has(id)),[false,false,false,false,false],'the first five relations in owner order stay cards');
 const page=foldPlan(nodes,edges,{selected:'parent',open:new Map([[1,FOLD_PAGE]])});
 assert.equal(page.folds[0].count,49-FOCUS_NEIGHBOURS-FOLD_PAGE);assert.equal(page.folds[0].shown,FOCUS_NEIGHBOURS+FOLD_PAGE,'one descent step shows twelve more');
 assert.equal(foldPlan(nodes,edges,{selected:'parent',open:new Map([[1,Infinity]])}).folds.length,0,'Unfold all shows every one');
 assert.equal(foldPlan(nodes,edges,{selected:'child-3',above:100}).folds.length,0,'a rank within the threshold never folds');
 // geometry at Fit (Sol's 600 x 420 pane and a 760 x 420 pane): labels stay readable in every state
 const at=(selected,open,pane)=>geometry(layoutTopology(nodes,edges,{width:pane.w,fold:foldPlan(nodes,edges,{selected,open})}),pane);
 for(const pane of [{w:600,h:420},{w:760,h:420}]){
  assert.ok(at('parent',new Map(),pane).label>=11,'parent-selected folded: labels >= 11 px at '+pane.w);
  assert.ok(at('child-3',new Map(),pane).label>=11,'leaf-selected folded');
  assert.ok(at('parent',new Map([[1,FOLD_PAGE]]),pane).label>=8,'after one descent step: labels >= 8 px at '+pane.w);
 }
 assert.ok(at('parent',new Map([[1,Infinity]]),{w:600,h:420}).label<8,'fully unfolded is the explicit deep state: the grid, not the overview');
 const layout=layoutTopology(nodes,edges,{width:760});assert.ok(layout.world.w<760*2&&layout.world.h>CARD.h*8,'an unfolded wide rank wraps into a grid');
});
test('the mounted fifty-node page: parent selected shows five children and one fold card, every relation listed; the fold descends, the toolbar folds; an appended page joins the fold',async()=>{
 const d=installDOM();
 try{
  document.createElementNS=(_ns,tag)=>new Node(tag);
  Object.defineProperty(Node.prototype,'clientWidth',{configurable:true,get:()=>600});Object.defineProperty(Node.prototype,'clientHeight',{configurable:true,get:()=>420});
  const {nodes,edges}=fifty();
  const host=new Node('main');d.body.append(host);const view=mountTopology(host,{nodes,edges,selected:'parent'});
  const svg=()=>host.querySelector('svg');
  const drawn=()=>svg().all().filter(n=>n.dataset.topologyNode).length,foldCards=()=>svg().all().filter(n=>n.dataset.topologyFold);
  assert.equal(drawn(),1+FOCUS_NEIGHBOURS,'the parent and five children are the node cards');assert.equal(foldCards().length,1);
  assert.equal(foldCards()[0].attrs['aria-label'],'Show 12 more of 44 remaining at this level (5 of 49 shown)');assert.equal(foldCards()[0].dataset.control,'topology:fold');
  const edgeLabels=()=>svg().all().filter(n=>n.tag==='text').map(n=>n.textContent);
  assert.ok(edgeLabels().includes('Contains ×44'),'edges into the fold draw once with their exact count');assert.equal(edgeLabels().filter(t=>t==='Contains').length,5);
  assert.equal(host.querySelectorAll('li').length,49,'every relation stays in the accessible list');assert.equal(host.querySelectorAll('.topology-card').length,50);
  const box=()=>svg().attrs.viewBox.split(' ').map(Number);const world=layoutTopology(nodes,edges,{width:600,fold:foldPlan(nodes,edges,{selected:'parent'})}).world;
  assert.ok(box()[0]<=0&&box()[0]+box()[2]>=world.w&&box()[1]<=0&&box()[1]+box()[3]>=world.h,'Fit contains the folded world');
  assert.ok(600/box()[2]>=0.9,'the folded page fits near 1:1');
  const toggle=host.all().find(n=>n.tag==='button'&&n.dataset.control==='topology:fold');assert.ok(toggle&&!toggle.hidden);assert.equal(toggle.textContent,'Unfold all');
  foldCards()[0].onkeydown({key:'Enter',preventDefault(){}});
  assert.equal(drawn(),1+FOCUS_NEIGHBOURS+FOLD_PAGE,'one descent step: twelve more real cards');assert.equal(foldCards().length,1);assert.equal(foldCards()[0].attrs['aria-label'],'Show 12 more of 32 remaining at this level (17 of 49 shown)');
  await toggle.onclick();assert.equal(drawn(),50,'Unfold all draws every card');assert.equal(foldCards().length,0);assert.equal(toggle.textContent,'Fold wide levels');
  await toggle.onclick();assert.equal(drawn(),1+FOCUS_NEIGHBOURS,'the toolbar folds the wide levels again');
  view.select('child-3');assert.equal(drawn(),2,'selecting a leaf keeps it and its parent');assert.equal(view.folds[0].count,48);
  view.update({nodes:[{id:'child-49',title:'Child 49'}],edges:[{kind:'contains',source:'parent',target:'child-49'}]});
  assert.equal(host.querySelectorAll('.topology-card').length,51);assert.equal(view.folds[0].count,49,'an appended page joins the fold with its exact count');
  view.destroy();
 }finally{delete Node.prototype.clientWidth;delete Node.prototype.clientHeight;delete document.createElementNS;d.restore();}
});

// repair2 R6 (2026-10-14): the advertised descent equals what one descent reveals at every boundary
test('each fold advertises exactly the cards one descent reveals, including a lone remainder (19-node witness)',async()=>{
 const {descentStep}=await import('../src/laplace/web/static_shared/workspace-topology.mjs');
 for(const n of [17,18,19,20,21,30,31,50]){
  const nodes=Array.from({length:n},(_,i)=>({id:'n'+i,title:'Work '+i})),edges=nodes.slice(1).map(x=>({kind:'contains',source:'n0',target:x.id}));
  let open=new Map(),plan=foldPlan(nodes,edges,{selected:'n0',open});
  while(plan.folds.length){const fold=plan.folds[0],step=descentStep(fold.count);open=new Map([[1,(open.get(1)||0)+step]]);const next=foldPlan(nodes,edges,{selected:'n0',open});
   assert.equal(plan.folded.size-next.folded.size,step,n+' nodes: advertised '+step+' of '+fold.count);assert.notEqual(next.folds[0]?.count,1,'never a fold of one');plan=next;}
  assert.equal(plan.folded.size,0,n+' nodes: descent ends with every card shown');
 }
 const d=installDOM();try{document.createElementNS=(_ns,tag)=>new Node(tag);
  const nodes=Array.from({length:19},(_,i)=>({id:'n'+i,title:'Work '+i})),edges=nodes.slice(1).map(x=>({kind:'contains',source:'n0',target:x.id}));
  const host=new Node('main');d.body.append(host);mountTopology(host,{nodes,edges,selected:'n0'});
  const fold=()=>host.querySelector('svg').all().find(n=>n.dataset.topologyFold),cards=()=>host.querySelector('svg').all().filter(n=>n.dataset.topologyNode).length;
  assert.equal(fold().attrs['aria-label'],'Show 13 more of 13 remaining at this level (5 of 18 shown)');assert.equal(cards(),6);
  fold().onkeydown({key:'Enter',preventDefault(){}});assert.equal(cards(),19,'all thirteen appear, as advertised');assert.equal(fold(),undefined);
  assert.equal(host.querySelectorAll('li').length,18,'the list keeps every typed edge');
 }finally{delete document.createElementNS;d.restore();}
});

// M5 D (Root actual: keyboard descent 17 -> 29 children left focus on BODY): a descent repaints the
// SVG, so focus moves to the rank's replacement fold card, and to the first revealed card when the
// last descent removes the fold; a pointer descent from outside the view does not steal focus.
test('keyboard fold descent keeps focus on the replacement fold card, then on the first revealed card',async()=>{
 const d=installDOM();
 try{
  document.createElementNS=(_ns,tag)=>new Node(tag);Node.prototype.contains=function(node){return this.all().includes(node);};
  Object.defineProperty(Node.prototype,'clientWidth',{configurable:true,get:()=>600});Object.defineProperty(Node.prototype,'clientHeight',{configurable:true,get:()=>420});
  const {nodes,edges}=fifty();const host=new Node('main');d.body.append(host);const view=mountTopology(host,{nodes,edges,selected:'parent'});
  const svg=()=>host.querySelector('svg'),fold=()=>svg().querySelector('[data-topology-fold]'),drawn=()=>svg().querySelectorAll('[data-topology-node]').map(n=>n.dataset.topologyNode);
  fold().focus();
  for(let step=0;fold();step++){
   const before=fold(),hidden=view.folds[0].nodes.slice();before.onkeydown({key:'Enter',preventDefault(){}});
   assert.equal(before.isConnected===false||!svg().all().includes(before),true,'the old card was replaced');
   const active=document.activeElement;assert.ok(svg().all().includes(active),'focus stays inside the drawn view at step '+step);
   if(fold())assert.equal(active,fold(),'focus is on the replacement fold card');
   else{assert.equal(active.dataset.topologyNode,hidden[0],'the last descent focuses the first revealed card');assert.ok(drawn().includes(hidden[0]));}
  }
  assert.equal(drawn().length,50);
  // a pointer descent while focus is elsewhere leaves that focus alone
  view.fold();const outside=new Node('button');d.body.append(outside);outside.focus();fold().onclick();assert.equal(document.activeElement,outside);
  view.destroy();
 }finally{delete Node.prototype.contains;delete Node.prototype.clientWidth;delete Node.prototype.clientHeight;delete document.createElementNS;d.restore();}
});
