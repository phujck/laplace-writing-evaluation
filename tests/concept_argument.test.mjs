import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
// Load the pure projection from the served module; DOM mounting is exercised in CUA.
const source=await readFile(new URL('../src/laplace/web/static_shared/concept-explorer.mjs',import.meta.url),'utf8');
const layoutSource=await readFile(new URL('../src/laplace/web/static_shared/conceptric-panes.mjs',import.meta.url),'utf8');
const layoutPure=layoutSource.slice(layoutSource.indexOf('const G_SPX ='),layoutSource.indexOf('const G_SPX =')+layoutSource.slice(layoutSource.indexOf('const G_SPX =')).indexOf(';')+1)+'\n'+layoutSource.slice(layoutSource.indexOf('export function layoutConceptricGraph('),layoutSource.indexOf('function computeGraphLayout('));
const pure=layoutPure+"import {displayLabel as label} from '"+new URL('../src/laplace/web/static_shared/concept-reader.mjs',import.meta.url).href+"';\n"+source.slice(source.indexOf('const ARGUMENT_AUXILIARY='),source.indexOf('export async function mountArgumentOverview('));
const {projectArgument,clusterArgument,argumentRoute,argumentLayout,argumentScope,ARGUMENT_SCOPE_LIMIT,resizedArgumentCamera,initialArgumentScope,argumentContents,argumentObligations,argumentLocalContext}=await import('data:text/javascript;base64,'+Buffer.from(pure).toString('base64'));
const nodes=[{id:'root',kind:'paper',parent:null,members:['group']},{id:'group',kind:'definition',parent:'root',members:['premise','claim'],grade:1},{id:'premise',kind:'postulate',parent:'group',members:[],grade:0},{id:'claim',kind:'theorem',parent:'group',members:[],grade:1},{id:'outside',kind:'result',parent:null,members:[],grade:2},{id:'loose',kind:'definition',parent:null,members:[],grade:0}];
const edges=[{from:'claim',to:'premise'},{from:'outside',to:'claim'}];
test('collapsed containment retains exact prerequisite origins and uncontained objects',()=>{
 const before=JSON.stringify({nodes,edges}),view=projectArgument(nodes,edges,'root');
 assert.deepEqual(new Set(view.nodes.map(node=>node.id)),new Set(['group','outside','loose']));
 assert.deepEqual(view.links,[{from:'group',to:'outside',pairs:[{dependent:'outside',prerequisite:'claim'}]}]);
 assert.equal(JSON.stringify({nodes,edges}),before);
});
test('expanding a concept exposes premise-to-dependent direction and external boundary',()=>{
 const view=projectArgument(nodes,edges,'root','group');
 const edge=view.links.find(link=>link.from==='premise');
 assert.equal(edge.to,'claim');assert.deepEqual(edge.pairs,[{dependent:'claim',prerequisite:'premise'}]);
 assert.equal(view.nodes.find(node=>node.id==='outside').boundary,true);
 assert.equal(view.nodes.some(node=>node.id==='loose'),false);
});


test('prerequisite view groups preserve shared premises and exact underlying pairs',()=>{
 const items=[{id:'root',kind:'paper',members:[],parent:null},{id:'shared',kind:'postulate',members:[],parent:null,grade:0}];const requirements=[];
 for(let i=0;i<6;i++){items.push({id:'p'+i,kind:'definition',parent:null,members:[],grade:0},{id:'r'+i,label:'Result '+i,kind:'result',parent:null,members:[],grade:1});requirements.push({from:'r'+i,to:'p'+i},{from:'r'+i,to:'shared'});}
 for(let i=0;i<3;i++)items.push({id:'loose'+i,kind:'definition',parent:null,members:[],grade:0});
 const shown=clusterArgument(projectArgument(items,requirements,'root'));
 assert.equal(shown.nodes.length,8);assert.ok(shown.nodes.some(node=>node.id==='shared'&&!node.display_group));
 assert.equal(shown.nodes.find(node=>node.id==='view:unconnected').view_members.length,3);
 assert.ok(shown.links.every(link=>link.pairs.every(pair=>requirements.some(edge=>edge.from===pair.dependent&&edge.to===pair.prerequisite))));
 assert.equal(shown.owner('r0'),'view:cone:r0');
});

test('dependency levels remain ordered while disconnected components stay separate',()=>{
 const view=projectArgument(nodes,edges,'root','group'),layout=argumentLayout(view.nodes,view.links,900,450);
 for(const edge of view.links){const a=layout.positions.get(edge.from),b=layout.positions.get(edge.to);assert.ok(b.rank>a.rank);assert.ok(b.y<a.y);}
 const independent={id:'independent',kind:'definition',grade:100,members:[]},all=argumentLayout([...view.nodes,independent],view.links,900,450);
 const point=all.positions.get('independent');assert.notEqual(point.component,all.positions.get('claim').component);
});

test('direct prerequisite curves use distinct node ports rather than an apparent common bus',()=>{
 const a={x:110,y:200,rank:0},b={x:110,y:100,rank:1},c={x:310,y:100,rank:1};
 const left=argumentRoute(a,b,0,{sourcePort:-20}),right=argumentRoute(a,c,0,{sourcePort:20});
 assert.ok(left.startsWith('M90,171C'));assert.ok(right.startsWith('M130,171C'));assert.ok(!left.includes('H')&&!right.includes('H'));
 const skip=argumentRoute(a,{x:110,y:0,rank:2},0,{bounds:{left:0,right:420}});assert.ok(skip.includes('L10,'));
});

test('declared cycles remain explicitly marked instead of receiving a fictitious derivation order',()=>{
 const ns=[{id:'a'},{id:'b'},{id:'c'}],es=[{from:'a',to:'b'},{from:'b',to:'a'},{from:'b',to:'c'}];
 const layout=argumentLayout(ns,es,800,400);assert.deepEqual(layout.cyclic,new Set(['a','b']));assert.equal(layout.positions.get('a').rank,layout.positions.get('b').rank);assert.ok(layout.positions.get('c').rank>layout.positions.get('a').rank);
});


test('an 85-member group preserves every exact canonical session target',()=>{
 const members=Array.from({length:85},(_,i)=>({id:'claim:'+i,kind:'claim',members:[]}));
 const shown=clusterArgument(projectArgument([{id:'root',kind:'paper'},...members],[],'root'));
 const scope=argumentScope(shown.nodes[0]);assert.equal(scope.node_ids.length,85);assert.deepEqual(new Set(scope.node_ids),new Set(members.map(node=>node.id)));assert.equal(scope.id,undefined);
});
test('groups above the backend limit are explicitly partitioned without losing or guessing membership',()=>{
 const members=Array.from({length:1003},(_,i)=>({id:'claim:'+i,kind:'claim',members:[]}));
 const shown=clusterArgument(projectArgument([{id:'root',kind:'paper'},...members],[],'root'));
 assert.equal(shown.nodes.length,3);const scopes=shown.nodes.map(argumentScope);
 assert.ok(scopes.every(scope=>scope.node_ids.length<=ARGUMENT_SCOPE_LIMIT));assert.equal(new Set(scopes.flatMap(scope=>scope.node_ids)).size,1003);assert.ok(scopes.every(scope=>scope.id===undefined));assert.ok(shown.nodes.every(node=>node.partition.total===1003));
 for(const member of members)assert.ok(shown.nodes.find(node=>node.id===shown.owner(member.id)).view_members.includes(member.id));
});


test('manual argument resize preserves world center and Fit recomputes full visible bounds',()=>{
 const camera={x:300,y:100,k:1.2},before={width:2200,height:1100},after={width:1041,height:451},world={x:0,y:0,w:1090,h:486};
 const manual=resizedArgumentCamera(camera,before,after,world,false);assert.ok(Math.abs(manual.x+after.width/(2*manual.k)-(camera.x+before.width/(2*camera.k)))<1e-9);assert.ok(Math.abs(manual.y+after.height/(2*manual.k)-(camera.y+before.height/(2*camera.k)))<1e-9);
 const fitted=resizedArgumentCamera(camera,before,after,world,true);assert.ok(fitted.x<=0&&fitted.y<=0);assert.ok(fitted.x+after.width/fitted.k>=world.w);assert.ok(fitted.y+after.height/fitted.k>=world.h);
});


test('one authored hierarchy opens its first branching science level without flattening obligations into the DAG',()=>{
 const science=[{id:'root',kind:'paper',members:['refs']},{id:'refs',kind:'references',parent:'root',members:['citation']},{id:'citation',kind:'citation',parent:'refs',members:[]},{id:'goal',kind:'goal',parent:null,members:['preparation']},{id:'preparation',kind:'portal',parent:'goal',members:[]}];
 for(let i=0;i<6;i++){science.find(node=>node.id==='preparation').members.push('area'+i);science.push({id:'area'+i,kind:'portal',parent:'preparation',members:['claim'+i]},{id:'claim'+i,kind:'result',parent:'area'+i,members:[]});}
 const questions=Array.from({length:11},(_,i)=>({id:'question'+i,kind:'question',parent:null,members:[]}));science.push(...questions);
 const dependencies=[{from:'claim1',to:'claim0'},{from:'claim2',to:'claim1'}];assert.equal(initialArgumentScope(science,dependencies,'root'),'preparation');
 const view=projectArgument(science,dependencies,'root','preparation');assert.ok(Array.from({length:6},(_,i)=>'area'+i).every(id=>view.nodes.some(node=>node.id===id)));assert.equal(view.links.length,2);assert.ok(view.nodes.every(node=>node.kind!=='question'&&node.kind!=='references'&&node.kind!=='citation'));
 const project=projectArgument(science,dependencies,'root');assert.deepEqual(project.nodes.map(node=>node.id),['goal']);assert.equal(argumentContents(science,dependencies,'goal').objects,6);
 science.push({id:'independent',kind:'postulate',parent:null,members:[]});assert.equal(initialArgumentScope(science,dependencies,'root'),'root','a separate uncontained scientific object prevents an arbitrary default focus');
});
test('scoped obligations follow their node or relation targets regardless of containment',()=>{
 const rows=[{id:'node-question',state:'open',target:{kind:'node',node_id:'claim'}},{id:'edge-question',state:'open',target:{kind:'relation',source:'elsewhere',target:'claim',rel:'prerequisite'}},{id:'closed',state:'addressed',target:{kind:'node',node_id:'claim'}},{id:'unrelated',state:'open',target:{kind:'node',node_id:'other'}}];
 assert.deepEqual(argumentObligations(rows,new Set(['claim'])).map(row=>row.id),['node-question','edge-question']);
});
test('a scoped diagram shows outside prerequisites at the neighboring authored boundary',()=>{
 const ns=[{id:'root',kind:'paper',members:['work']},{id:'work',kind:'goal',parent:'root',members:['left','right']},{id:'left',kind:'portal',parent:'work',members:['a']},{id:'right',kind:'portal',parent:'work',members:['b']},{id:'a',kind:'result',parent:'left',members:[]},{id:'b',kind:'postulate',parent:'right',members:[]}];
 const view=projectArgument(ns,[{from:'a',to:'b'}],'root','left');assert.ok(view.nodes.some(node=>node.id==='right'&&node.boundary));assert.ok(!view.nodes.some(node=>node.id==='work'));assert.deepEqual(view.links[0].pairs,[{dependent:'a',prerequisite:'b'}]);
});


test('group preview has typed members and exact external prerequisites and uses',()=>{
 const group={id:'area',kind:'portal',members:['claim','premise']};const ns=[group,{id:'claim',kind:'result',parent:'area',members:[],meaning:'Main result.'},{id:'premise',kind:'postulate',parent:'area',members:[]},{id:'outside',kind:'definition',members:[]},{id:'consumer',kind:'theorem',members:[]}];
 const context=argumentLocalContext(ns,[{from:'claim',to:'premise'},{from:'claim',to:'outside'},{from:'consumer',to:'claim'}],group);assert.deepEqual(context.members.map(node=>node.id),['claim','premise']);assert.deepEqual(context.requires,['outside']);assert.deepEqual(context.usedBy,['consumer']);
 const view=projectArgument([{id:'root',kind:'paper',members:['area']},{...group,parent:'root'},...ns.slice(1)],[], 'root','area');assert.ok(!view.nodes.some(node=>node.id==='area'),'container record remains in breadcrumb rather than a redundant self-card');
});


test('an explicit Whole project choice survives reload and is not mistaken for an unset scope',()=>{
 const ns=[{id:'paper://',kind:'paper',members:[]},{id:'goal',kind:'goal',parent:null,members:['group']},{id:'group',kind:'portal',parent:'goal',members:['a','b']},{id:'a',kind:'result',parent:'group',members:[]},{id:'b',kind:'postulate',parent:'group',members:[]}];
 assert.equal(initialArgumentScope(ns,[],'paper://',null),'group');
 assert.equal(initialArgumentScope(ns,[],'paper://','paper://'),'paper://');
 assert.equal(initialArgumentScope(ns,[],'paper://',''),'paper://');
 assert.equal(initialArgumentScope(ns,[],'paper://','retired-group'),'paper://','a removed remembered scope returns to project instead of choosing another branch');
 assert.equal(initialArgumentScope(ns,[],'paper://','goal'),'goal');
});

test('stale dispositions share the attention list with open points without changing their states',()=>{
 const obligations=[{id:'open',state:'open',target:{kind:'node',node_id:'claim'}},
  {id:'stale',state:'addressed',currentness:{status:'STALE'},target:{kind:'node',node_id:'claim'}},
  {id:'current',state:'addressed',currentness:{status:'CURRENT'},target:{kind:'node',node_id:'claim'}},
  {id:'elsewhere',state:'open',target:{kind:'node',node_id:'outside'}}];
 assert.deepEqual(argumentObligations(obligations,new Set(['claim'])).map(row=>row.id),['open','stale']);
 assert.equal(obligations[1].state,'addressed');
});
