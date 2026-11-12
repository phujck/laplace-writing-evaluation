// ONE typed topology view (M5 plan §6): a visual graph and an accessible relation list
// rendered from the SAME node/edge array by one paint, so they cannot diverge. Input is
// one owner-derived page {nodes, edges, boundaries} plus optional authored layout hints
// {rank:{id:n}, groups:[{id,title,nodes}]}; the owner's continuation handle is the only way
// to see more. Instances: the Work neighbourhood (/work/state view=graph, paged with as_of),
// the reader-plan relation map (structure detail, no extra read) and declared help
// diagrams (always hinted). Display of implemented typed topology only: nothing here
// infers hierarchy, coarse-grains or promotes a logical edge to an execution prerequisite.
//
// Layout: with hints, a deterministic layered layout honouring rank and group boxes;
// without hints, ranks come from the edges themselves (longest path over the typed
// direction, cycle-guarded) which is the same rule concept-explorer's argumentLayout
// applies to prerequisite chains.
//
// WIDE RANKS (ACTUAL-C4-GRAPH-READABILITY, 2026-10-14): a rank with more than FOLD_ABOVE nodes
// on a 50-node page fitted to 11.94 x 4.12 px cards. Such a rank is painted FOLDED: the nodes in
// focus (the selected node, any node named by hints.pin, and at most FOCUS_NEIGHBOURS of the nodes
// it shares an edge with, in owner order: a selected parent with 49 children keeps five, H4) keep
// their cards; the rest of that rank is one fold card stating its exact count ("43 more at this
// level") that descends FOLD_PAGE real cards at a time into a grid of GRID_COLUMNS per row (Unfold
// all shows every one). Edges to folded nodes are drawn to the fold card once per kind with their
// count; every edge stays a row in the relation list, so nothing is coarsened, inferred or hidden
// from the accessible form; the fold is a display state (Unfold all / Fold wide levels in the
// toolbar), never a graph change.
//
// The SVG is drawn only where the document can create SVG elements and the host is wide enough
// (listOnly below 1000 px, per the plan); the relation list is always present and is the
// accessible form. DOM is bounded by the pages the consumer has appended: update() retains every
// node and edge already shown and repaints the whole accumulated set (a continuation adds to the
// DOM, it does not replace one page with the next), so a consumer that pages far keeps a growing
// view and should say so; nothing runs on idle. Both ends of a relation are doors when the owner
// page makes them readable: an inside end selects, an outside end (source or target boundary with
// an owner handle) expands through onExpand; a logical target and an unavailable boundary are
// notes, never doors. Fit scales the camera to contain the whole world (no scale floor), centred
// horizontally (Sol topology-controls). Colours are the shared tokens (tokens.css); the SVG reads
// them through var() so the graph follows the theme like every other surface.
// Controls: topology:view (region), topology:fold (fold card and toolbar fold toggle).
import {stateChip,relationList,presentationStyles,declareControl} from './workspace-presentation.mjs';
const el=(tag,text='',cls='')=>{const node=document.createElement(tag);node.textContent=text;node.className=cls;return node;};
// wave 13 id sweep: control ids by tag and label (begin)
// wave 13 id sweep: control ids (end)
const ns='http://www.w3.org/2000/svg';
export const TOPOLOGY_EDGE_KINDS=Object.freeze({
  contains:{label:'Contains',note:'membership'},requires:{label:'Requires',note:'gates work',dash:'6 4'},
  'targets-logical-node':{label:'Targets',note:'logical relationship; not an execution prerequisite',dash:'2 3'},
  'bound-to':{label:'Bound to',note:'source heading'},argues:{label:'Argues',note:'argument object'},
  'supported-by':{label:'Supported by',note:'evidence'},'tracked-by':{label:'Tracked by',note:'work'},
  'placed-in':{label:'Placed in',note:'reader-plan section'}});
export const CARD={w:180,h:52,gapX:26,gapY:72,pad:24};
export const FOLD_ABOVE=8;      // a rank wider than this folds
export const FOCUS_NEIGHBOURS=5; // direct relations of the selected node kept as cards in a wide rank (H4)
export const FOLD_PAGE=12;       // cards one descent step adds from a fold (three grid rows)
// one descent step: FOLD_PAGE cards, or every remaining card when FOLD_PAGE would leave exactly one
export const descentStep=count=>count-FOLD_PAGE===1?count:Math.min(FOLD_PAGE,count);
export const GRID_COLUMNS=3;    // a wide rank wraps into rows of this many cards (full-size cards at a 640 px pane)
const GRID_GAP_Y=14;
const RANK_REVERSED=new Set(['requires']);
const kindOf=kind=>TOPOLOGY_EDGE_KINDS[kind]||{label:String(kind||'relates to').replaceAll('-',' '),note:''};
const foldId=rank=>'fold:'+rank;
const COLOUR={edge:'var(--edge)',edge2:'var(--edge2)',ink:'var(--ink)',ink2:'var(--ink2)',panel:'var(--panel)',panel2:'var(--panel2)',accent:'var(--accent)',ok:'var(--ok)',warn:'var(--warn)',bad:'var(--bad)',dim:'var(--dim)'};
// The relation rows: every edge once, in owner order, with the labels of both ends; an end
// outside the page is a boundary row (readable through its owner handle, never guessed).
export function topologyRows(nodes=[],edges=[],boundaries=[]){
  const byId=new Map(nodes.map(node=>[node.id,node])),outside=new Map(boundaries.map(row=>[row.id,row]));
  const label=id=>byId.get(id)?.title||byId.get(id)?.label||outside.get(id)?.title||outside.get(id)?.label||id;
  const seen=new Set(),rows=[];
  for(const edge of edges){
    const key=JSON.stringify([edge.kind,edge.source,edge.target]);if(seen.has(key))continue;seen.add(key);
    const kind=kindOf(edge.kind);
    rows.push({key,kind:edge.kind,label:kind.label,note:kind.note,source:edge.source,target:edge.target,
      sourceLabel:label(edge.source),targetLabel:label(edge.target),
      sourceOutside:!byId.has(edge.source)?outside.get(edge.source)||{id:edge.source}:null,
      targetOutside:!byId.has(edge.target)?outside.get(edge.target)||{id:edge.target}:null});
  }
  return rows;
}
// The ranks: from hints or from the typed direction of the edges (longest path, cycle-guarded).
export function topologyRanks(nodes=[],edges=[],hints=null){
  const ids=nodes.map(node=>node.id),index=new Map(ids.map((id,i)=>[id,i])),rank=new Map();
  // rank flows DOWN the typed direction except for `requires`, whose owner spells it
  // dependent -> prerequisite: the prerequisite sits above the work that waits on it
  const out=new Map(ids.map(id=>[id,[]]));
  for(const edge of edges){if(!index.has(edge.source)||!index.has(edge.target)||edge.source===edge.target)continue;const [from,to]=RANK_REVERSED.has(edge.kind)?[edge.target,edge.source]:[edge.source,edge.target];out.get(from).push(to);}
  if(hints?.rank)for(const id of ids)if(Number.isInteger(hints.rank[id]))rank.set(id,Math.max(0,hints.rank[id]));
  const active=new Set();
  const incoming=new Map(ids.map(id=>[id,[]]));for(const [from,targets]of out)for(const to of targets)incoming.get(to).push(from);
  const resolve=id=>{if(rank.has(id))return rank.get(id);if(active.has(id)){rank.set(id,0);return 0;}active.add(id);const value=Math.max(0,...incoming.get(id).map(from=>resolve(from)+1));active.delete(id);rank.set(id,value);return value;};
  for(const id of ids)resolve(id);
  return {rank,index};
}
// The fold plan: which nodes of each wide rank keep a card. Pure; the display state (which wide
// ranks are open) is the view's. `focus` is the selected node, its direct relations and hints.pin.
// `open` maps a rank to how many of its folded nodes the person has descended into (a count; a
// fold card adds FOLD_PAGE each time, Unfold all adds every one); the focus in a wide rank is the
// selected node, hints.pin and at most FOCUS_NEIGHBOURS of its direct relations in owner order, so
// a selected parent with 49 children (H4) is not 49 protected cards: the rest stay in the fold
// with their exact count and remain in the relation list.
export function foldPlan(nodes=[],edges=[],{hints=null,selected=null,open=new Map(),above=FOLD_ABOVE,neighbours=FOCUS_NEIGHBOURS,initialVisible=0}={}){
  const {rank}=topologyRanks(nodes,edges,hints);
  const pinned=new Set([selected,...(hints?.pin||[])].filter(Boolean));
  const related=[];for(const edge of edges){const other=edge.source===selected?edge.target:edge.target===selected?edge.source:null;if(other&&!pinned.has(other)&&!related.includes(other))related.push(other);}
  const rows=new Map();for(const node of nodes){const r=rank.get(node.id)||0;if(!rows.has(r))rows.set(r,[]);rows.get(r).push(node.id);}
  const folds=[],folded=new Map(),shown=(r,fallback=0)=>(open instanceof Map?(open.has(r)?open.get(r):fallback):open?.has?.(r)?Infinity:fallback)||0;
  for(const [r,ids]of rows){
    if(ids.length<=above)continue;
    const inRank=new Set(ids),focus=new Set([...pinned].filter(id=>inRank.has(id)));let kept=0;
    for(const id of related)if(inRank.has(id)&&kept<neighbours){focus.add(id);kept++;}
    const rest=ids.filter(id=>!focus.has(id)),visible=rest.slice(0,Math.min(rest.length,shown(r,Math.max(0,initialVisible-focus.size)))),hidden=rest.slice(visible.length);
    if(hidden.length<2)continue;
    folds.push({id:foldId(r),rank:r,nodes:hidden,count:hidden.length,total:ids.length,shown:ids.length-hidden.length,restShown:visible.length,related:related.filter(id=>inRank.has(id)).length});
    for(const id of hidden)folded.set(id,foldId(r));
  }
  return {rank,folds,folded,wide:[...rows.entries()].filter(([,ids])=>ids.length>above).map(([r])=>r)};
}
// Deterministic layered layout: rank from hints or from the typed direction of the edges.
// `fold` (a foldPlan) replaces each wide rank's hidden nodes with one fold card; an open wide rank
// wraps into a grid of GRID_COLUMNS so its cards stay legible at Fit.
export function layoutTopology(nodes=[],edges=[],{hints=null,width=760,fold=null,above=FOLD_ABOVE}={}){
  const {rank,index}=topologyRanks(nodes,edges,hints);
  const folded=fold?.folded||new Map(),folds=fold?.folds||[];
  const groups=(hints?.groups||[]).map(group=>({id:group.id,title:group.title,nodes:(group.nodes||[]).filter(id=>index.has(id))}));
  const rows=new Map();for(const id of nodes.map(node=>node.id)){if(folded.has(id))continue;const r=rank.get(id)||0;if(!rows.has(r))rows.set(r,[]);rows.get(r).push(id);}
  for(const item of folds){if(!rows.has(item.rank))rows.set(item.rank,[]);rows.get(item.rank).push(item.id);}
  const ranks=[...rows.keys()].sort((a,b)=>a-b),positions=new Map();let maxWidth=0;
  const order=id=>id.startsWith('fold:')?Number.MAX_SAFE_INTEGER:index.get(id);
  const lines=new Map();   // rank -> array of rows of ids (a wide open rank wraps)
  for(const r of ranks){const row=rows.get(r);row.sort((a,b)=>order(a)-order(b));
    const perLine=row.length>GRID_COLUMNS?GRID_COLUMNS:row.length;const chunks=[];for(let i=0;i<row.length;i+=Math.max(1,perLine))chunks.push(row.slice(i,i+Math.max(1,perLine)));
    lines.set(r,chunks);for(const chunk of chunks)maxWidth=Math.max(maxWidth,chunk.length*CARD.w+(chunk.length-1)*CARD.gapX);}
  let y=CARD.pad;
  for(const r of ranks){const chunks=lines.get(r);
    chunks.forEach((chunk,line)=>{const rowWidth=chunk.length*CARD.w+(chunk.length-1)*CARD.gapX,start=CARD.pad+(maxWidth-rowWidth)/2;
      chunk.forEach((id,i)=>positions.set(id,{x:start+i*(CARD.w+CARD.gapX)+CARD.w/2,y:y+line*(CARD.h+GRID_GAP_Y)+CARD.h/2,rank:r}));});
    y+=chunks.length*CARD.h+(chunks.length-1)*GRID_GAP_Y+CARD.gapY;}
  const boxes=groups.map(group=>{const points=group.nodes.map(id=>positions.get(id)).filter(Boolean);if(!points.length)return null;
    return {...group,x:Math.min(...points.map(p=>p.x))-CARD.w/2-10,y:Math.min(...points.map(p=>p.y))-CARD.h/2-26,
      w:Math.max(...points.map(p=>p.x))-Math.min(...points.map(p=>p.x))+CARD.w+20,h:Math.max(...points.map(p=>p.y))-Math.min(...points.map(p=>p.y))+CARD.h+36};}).filter(Boolean);
  return {positions,rank,groups:boxes,folds,world:{w:Math.max(width,maxWidth+CARD.pad*2),h:Math.max(CARD.h+CARD.pad*2,y-CARD.gapY+CARD.pad)}};
}
// Positions are card CENTRES (the SVG group subtracts half the card size).
// Enter the destination from the actual source direction, outside its rectangle;
// a requires edge may travel upwards rather than from bottom to top.
export function topologyEdgeGeometry(a,b,{gap=4}={}){
 const dx=b.x-a.x,dy=b.y-a.y,length=Math.hypot(dx,dy);
 if(!length){const x=a.x+CARD.w/2+gap,y=a.y;return {d:`M${x},${y+8}C${x+40},${y+40} ${x+40},${y-40} ${x},${y-8}`,start:{x,y:y+8},end:{x,y:y-8}};}
 const scale=Math.min(dx?CARD.w/2/Math.abs(dx):Infinity,dy?CARD.h/2/Math.abs(dy):Infinity),offset=scale+gap/length;
 const start={x:a.x+dx*offset,y:a.y+dy*offset},end={x:b.x-dx*offset,y:b.y-dy*offset},horizontal=Math.abs(dx)/CARD.w>Math.abs(dy)/CARD.h;
 const d=horizontal?`M${start.x},${start.y}C${(start.x+end.x)/2},${start.y} ${(start.x+end.x)/2},${end.y} ${end.x},${end.y}`:`M${start.x},${start.y}C${start.x},${(start.y+end.y)/2} ${end.x},${(start.y+end.y)/2} ${end.x},${end.y}`;
 return {d,start,end};
}
const svgEl=(tag,attrs={})=>{const node=document.createElementNS(ns,tag);for(const [key,value]of Object.entries(attrs))node.setAttribute(key,String(value));return node;};
function wrap(text,max=24){const words=String(text||'').split(/\s+/),lines=[''];for(const word of words){if((lines.at(-1)+' '+word).trim().length>max&&lines.at(-1))lines.push(word);else lines[lines.length-1]=(lines.at(-1)+' '+word).trim();}return lines.slice(0,2).map((line,i)=>i===1&&lines.length>2?line.slice(0,max-1)+'…':line);}
export function mountTopology(host,{title='Relations',nodes=[],edges=[],boundaries=[],hints=null,selected=null,legend='',description='',onSelect=()=>{},onExpand=null,listOnly=false,chip=()=>null,ariaLabel='Typed relationships',foldAbove=FOLD_ABOVE,initialCamera=null,onCameraChange=()=>{},readable=false}={}){
  presentationStyles();
  const region=el('section','','topology'+(readable?' topology-readable':''));region.dataset.control='topology:view';
  const head=el('div','','topology-head');head.append(el('h3',title,'topology-title'));region.append(head);
  const canDraw=typeof document.createElementNS==='function'&&!listOnly;
  const toolbar=el('div','','topology-toolbar'),viewport=el('div','','topology-viewport'),note=el('p',legend,'topology-note muted'),list=el('div','','topology-list');
  if(canDraw){viewport.tabIndex=0;viewport.setAttribute('aria-label',ariaLabel+'. Drag to pan; use the zoom controls to change scale.');region.append(toolbar,viewport);}
  if(readable){const equivalent=el('details','','topology-equivalent');equivalent.append(el('summary','All loaded objects and typed relations'),list);region.append(note,equivalent);}else region.append(note,list);host.append(region);
  let state={nodes:[...nodes],edges:[...edges],boundaries:[...boundaries]},camera={x:0,y:0,k:1},svg=null,world=null,positions=null,contentBounds=null,drag=null,alive=true,cameraReady=false,fitCamera=true,displayedPane=null;
  // the fold state: which wide ranks the person has opened; folds re-evaluate on every paint
  const open=new Map();let plan=null,foldAll=null;
  const allOpen=()=>!!plan?.wide.length&&!plan.folds.length;
  const button=(text,run,name=text)=>{const b=el('button',text,'act act-read');b.type='button';b.setAttribute('aria-label',name);b.onclick=()=>Promise.resolve(run());return b;};
  const visiblePane=()=>{const w=viewport.clientWidth,h=viewport.clientHeight;return w>0&&h>0?{w,h}:null;};
  const pane=()=>visiblePane()||displayedPane||{w:world.w,h:Math.min(world.h,420)};
  // Camera reconciliation never relays out or rereads graph facts. A hidden mount can use a
  // provisional box, but its first displayed size (and later sizes) must reach the SVG.
  const boundedOrigin=(wanted,min,max,extent)=>max-min<=extent?(min+max-extent)/2:Math.max(min,Math.min(max-extent,wanted));
  // the scale that contains the whole world in the pane (never enlarged past 1:1); the manual
  // zoom floor is that scale or 0.2, whichever is smaller, so Fit and zoom agree on a wide page
  const fitScale=()=>{const {w,h}=pane();return readable?1:Math.min(1,w/world.w,h/world.h);};
  const zoom=ratio=>{if(!world)return;fitCamera=false;const {w,h}=pane(),old=camera.k;camera.k=Math.max(readable?1:Math.min(.2,fitScale()),Math.min(2.5,old*ratio));camera.x+=w/(2*old)-w/(2*camera.k);camera.y+=h/(2*old)-h/(2*camera.k);paintCamera();if(cameraReady)onCameraChange({...camera});};
  const fit=()=>{if(!world)return;fitCamera=true;const {w,h}=pane(),k=fitScale(),anchor=readable&&(positions?.get(selected)||positions?.values().next().value);camera=readable?{k,x:boundedOrigin((anchor?.x??CARD.pad)-w/2,contentBounds.x,contentBounds.right,w),y:boundedOrigin((anchor?.y??CARD.pad)-h/2,contentBounds.y,contentBounds.bottom,h)}:{k,x:Math.min(0,(world.w-w/k)/2),y:0};paintCamera();if(cameraReady)onCameraChange({...camera});};
  const reconcilePane=()=>{if(!alive||!svg||!world)return;const measured=visiblePane();if(!measured||displayedPane?.w===measured.w&&displayedPane?.h===measured.h)return;displayedPane=measured;if(fitCamera)fit();else paintCamera();};
  if(canDraw){toolbar.append(declareControl(button('−',()=>zoom(1/1.2),'Zoom out'),'topology:zoom-out'),declareControl(button('+',()=>zoom(1.2),'Zoom in'),'topology:zoom-in'),declareControl(button('Fit',fit,'Fit to pane'),'topology:fit'));
    foldAll=button('Unfold all',()=>{if(allOpen())open.clear();else for(const r of plan?.wide||[])open.set(r,Infinity);paint();},'Unfold or fold the wide levels');foldAll.dataset.control='topology:fold';foldAll.hidden=true;toolbar.append(foldAll);}
  function paintCamera(){if(!svg||!world)return;const {w,h}=pane();svg.setAttribute('viewBox',`${camera.x} ${camera.y} ${w/camera.k} ${h/camera.k}`);for(const card of svg.querySelectorAll('[data-topology-node]'))card.classList.toggle('is-selected',card.dataset.topologyNode===selected);}
  function paint(){
    const rows=topologyRows(state.nodes,state.edges,state.boundaries);
    list.replaceChildren();
    const byKind=new Map();for(const row of rows){if(!byKind.has(row.kind))byKind.set(row.kind,[]);byKind.get(row.kind).push(row);}
    const cards=el('div','','topology-cards');
    for(const node of state.nodes){const card=el('button',node.title||node.label||node.id,'act act-read topology-card');card.type='button';card.dataset.topologyNode=node.id;card.dataset.control='topology:node';card.dataset.controlOwner=node.id;card.setAttribute('aria-current',String(node.id===selected));card.setAttribute('aria-label','Select '+(node.title||node.label||node.id));card.onclick=()=>onSelect(node.id,node);cards.append(card);const mark=chip(node);if(mark)cards.append(stateChip(mark));}
    if(state.nodes.length)list.append(cards);
    for(const [kind,group]of byKind){
      list.append(el('h4',kindOf(kind).label+(kindOf(kind).note?' · '+kindOf(kind).note:''),'topology-kind'));
      // an end outside the page: readable through its owner handle (or the owner id when the
      // consumer resolves ids itself), never through a guessed title; a logical target is a
      // relationship note, not a Work to open. An INCOMING edge from a readable boundary (the
      // parent of this page, which native graph pages publish) makes the source end a door too.
      list.append(relationList(group.map(row=>{const logical=row.kind==='targets-logical-node';const outside=row.targetOutside,from=row.sourceOutside;
        const readable=!!outside&&!logical&&!!onExpand&&outside.available!==false,fromReadable=!!from&&!!onExpand&&from.available!==false;
        return {kind:row.sourceLabel,kindRun:fromReadable?()=>onExpand(from):null,kindTitle:fromReadable?'Outside this page: read its owner':'',label:row.targetLabel,
          control:'topology:relation',owner:row.target,kindControl:'topology:relation-source',kindOwner:row.source,run:outside?(readable?()=>onExpand(outside):null):()=>onSelect(row.target,state.nodes.find(node=>node.id===row.target)),
          note:outside?(logical?'logical relationship; not an execution prerequisite':readable?'outside this page · read':'outside this page · unavailable'):from?(fromReadable?'from outside this page · read':'from outside this page · unavailable'):'',
          disabled:!!outside&&!readable};}),{emptyText:''}));
    }
    if(!rows.length)list.append(el('p','No typed relationships on this page.','muted'));
    if(!canDraw)return;
    plan=foldPlan(state.nodes,state.edges,{hints,selected,open,above:foldAbove,initialVisible:readable?FOLD_PAGE:0});
    if(foldAll){foldAll.hidden=!plan.wide.length;foldAll.textContent=allOpen()?'Fold wide levels':'Unfold all';}
    viewport.replaceChildren();const layout=layoutTopology(state.nodes,state.edges,{hints,width:viewport.clientWidth||760,fold:plan,above:foldAbove});world=layout.world;positions=layout.positions;
    if(readable){const points=[...positions.values()];contentBounds={x:Math.min(0,...points.map(p=>p.x-CARD.w/2-CARD.pad),...layout.groups.map(g=>g.x-CARD.pad)),y:Math.min(0,...points.map(p=>p.y-CARD.h/2-CARD.pad),...layout.groups.map(g=>g.y-CARD.pad)),right:Math.max(CARD.w+CARD.pad*2,...points.map(p=>p.x+CARD.w/2+CARD.pad),...layout.groups.map(g=>g.x+g.w+CARD.pad)),bottom:Math.max(CARD.h+CARD.pad*2,...points.map(p=>p.y+CARD.h/2+CARD.pad),...layout.groups.map(g=>g.y+g.h+CARD.pad))};note.textContent=(legend?legend+' ':'')+(state.nodes.length-plan.folded.size)+' of '+state.nodes.length+' loaded nodes drawn. Pan at readable scale or use the object list.';}
    svg=svgEl('svg',{width:'100%',height:'100%',role:'group','aria-label':ariaLabel});viewport.append(svg);
    // an SVG diagram carries its title and description; the relation list below is its equivalent
    if(description){const t=svgEl('title');t.textContent=ariaLabel;const d=svgEl('desc');d.textContent=description;svg.append(t,d);}
    const markerId='topology-arrow-'+Math.random().toString(36).slice(2),defs=svgEl('defs'),marker=svgEl('marker',{id:markerId,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:8,markerHeight:8,markerUnits:'userSpaceOnUse',orient:'auto'});marker.append(svgEl('path',{d:'M0 0L10 5L0 10z',fill:COLOUR.accent}));defs.append(marker);svg.append(defs);
    for(const box of layout.groups){const g=svgEl('g',{class:'topology-group'});g.append(svgEl('rect',{x:box.x,y:box.y,width:box.w,height:box.h,rx:9,fill:COLOUR.panel2,stroke:COLOUR.edge,'stroke-dasharray':'3 3'}));const text=svgEl('text',{x:box.x+10,y:box.y+16,fill:COLOUR.ink2,'font-size':11});text.textContent=box.title||box.id;g.append(text);svg.append(g);}
    const edgePath=(a,b,kind,label)=>{const path=svgEl('path',{d:topologyEdgeGeometry(a,b).d,fill:'none',stroke:COLOUR.accent,'stroke-opacity':.75,'stroke-width':1.6,'marker-end':`url(#${markerId})`,'vector-effect':'non-scaling-stroke',...(kind.dash?{'stroke-dasharray':kind.dash}:{})});
      path.dataset.topologyEdge=label.kind;svg.append(path);const mid=svgEl('text',{x:(a.x+b.x)/2+6,y:(a.y+b.y)/2,fill:COLOUR.ink2,'font-size':readable?12:10});mid.textContent=label.text;svg.append(mid);};
    // edges between visible cards draw once; edges into a fold draw once per (visible end, fold,
    // kind) with their count; edges between two folded nodes stay in the list only
    const folded=plan.folded,aggregate=new Map();
    for(const row of rows){const sf=folded.get(row.source),tf=folded.get(row.target);
      if(!sf&&!tf){const a=layout.positions.get(row.source),b=layout.positions.get(row.target);if(a&&b)edgePath(a,b,kindOf(row.kind),{kind:row.kind,text:kindOf(row.kind).label});continue;}
      if(sf&&tf)continue;
      const key=JSON.stringify([sf||row.source,tf||row.target,row.kind]);aggregate.set(key,(aggregate.get(key)||0)+1);}
    for(const [key,count]of aggregate){const [source,target,kind]=JSON.parse(key);const a=layout.positions.get(source),b=layout.positions.get(target);if(a&&b)edgePath(a,b,kindOf(kind),{kind,text:kindOf(kind).label+' ×'+count});}
    for(const node of state.nodes){const p=layout.positions.get(node.id);if(!p)continue;const g=svgEl('g',{transform:`translate(${p.x-CARD.w/2},${p.y-CARD.h/2})`,role:'button',tabindex:0,'aria-label':'Select '+(node.title||node.label||node.id)});g.dataset.topologyNode=node.id;g.dataset.control='topology:node';g.dataset.controlOwner=node.id;
      g.append(svgEl('rect',{width:CARD.w,height:CARD.h,rx:7,fill:COLOUR.panel,stroke:node.id===selected?COLOUR.accent:COLOUR.edge,'stroke-width':node.id===selected?2:1}));
      wrap(node.title||node.label||node.id).forEach((line,i)=>{const text=svgEl('text',{x:10,y:20+i*16,fill:COLOUR.ink,'font-size':readable?14:12});text.textContent=line;g.append(text);});
      const mark=chip(node);if(mark){const dot=svgEl('circle',{cx:CARD.w-10,cy:10,r:4,fill:mark.tone==='blocked'?COLOUR.bad:mark.tone==='ok'?COLOUR.ok:mark.tone==='attention'?COLOUR.warn:COLOUR.dim});dot.append(svgEl('title'));dot.firstChild.textContent=mark.label||'';g.append(dot);}
      g.onclick=()=>onSelect(node.id,node);g.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onSelect(node.id,node);}};svg.append(g);}
    // the fold cards: exact counts, opened in place; a display state, never a node
    // the advertised step is exactly what one descent reveals: a remainder of one is never left as a
    // fold of one (foldPlan shows a lone remainder), so a step that would leave one reveals it too (R6)
    for(const item of layout.folds){const p=layout.positions.get(item.id);if(!p)continue;const step=descentStep(item.count),label=item.count+' more at this level';
      const g=svgEl('g',{transform:`translate(${p.x-CARD.w/2},${p.y-CARD.h/2})`,role:'button',tabindex:0,'aria-label':'Show '+step+' more of '+item.count+' remaining at this level ('+item.shown+' of '+item.total+' shown)'});g.dataset.topologyFold=String(item.rank);g.dataset.control='topology:fold';
      g.append(svgEl('rect',{width:CARD.w,height:CARD.h,rx:7,fill:COLOUR.panel2,stroke:COLOUR.edge,'stroke-dasharray':'4 3'}));
      const text=svgEl('text',{x:10,y:22,fill:COLOUR.ink2,'font-size':12});text.textContent=label;g.append(text);
      const hint=svgEl('text',{x:10,y:40,fill:COLOUR.dim,'font-size':10});hint.textContent='Show '+step+' more · '+item.shown+' of '+item.total+' shown';g.append(hint);
      const descend=()=>{const focused=viewport.contains?.(globalThis.document?.activeElement);open.set(item.rank,(open.get(item.rank)??item.restShown??0)+step);paint();if(focused)refocus(item.rank,item.nodes[0]);};g.onclick=descend;g.onkeydown=event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();descend();}};svg.append(g);}
    fit();
  }
  // KEYBOARD CONTINUITY (M5 D, Root actual: 17 -> 29 children dropped focus to BODY): a descent
  // repaints the SVG, so the focused fold card is replaced. Focus moves to that rank's replacement
  // fold card, else to the first card the descent revealed, else to the viewport itself.
  function refocus(rank,revealed){
    const find=(key,value)=>[...(svg?.querySelectorAll?.('[data-'+key+']')||[])].find(n=>n.dataset[key==='topology-fold'?'topologyFold':'topologyNode']===value);
    (find('topology-fold',String(rank))||find('topology-node',revealed)||viewport).focus?.();
  }
  if(canDraw){viewport.onpointerdown=event=>{if(event.target.closest?.('button,[role=button]'))return;fitCamera=false;drag={x:event.clientX,y:event.clientY,camera:{...camera}};viewport.setPointerCapture?.(event.pointerId);};viewport.onpointermove=event=>{if(!drag)return;camera.x=drag.camera.x-(event.clientX-drag.x)/camera.k;camera.y=drag.camera.y-(event.clientY-drag.y)/camera.k;paintCamera();};viewport.onpointerup=()=>{if(drag)if(cameraReady)onCameraChange({...camera});drag=null;};}
  paint();if(initialCamera&&['x','y','k'].every(key=>Number.isFinite(initialCamera[key]))&&initialCamera.k>0){fitCamera=false;camera={...initialCamera,k:readable?Math.max(1,initialCamera.k):initialCamera.k};paintCamera();}
  cameraReady=true;displayedPane=visiblePane();
  const resizeObserver=readable&&canDraw&&typeof globalThis.ResizeObserver==='function'?new globalThis.ResizeObserver(reconcilePane):null;
  resizeObserver?.observe(viewport);
  return {refreshFacts(rows){const updates=new Map(rows.map(n=>[n.id,n]));state.nodes=state.nodes.map(n=>({...n,...updates.get(n.id)}));for(const node of state.nodes){for(const card of region.querySelectorAll('[data-topology-node]'))if(card.dataset.topologyNode===node.id){const title=node.title||node.label||node.id;card.setAttribute('aria-label','Select '+title);if(card.localName==='button')card.textContent=title;else if(card.localName==='g'){for(const text of [...card.querySelectorAll('text')])text.remove();wrap(title).forEach((line,i)=>{const text=svgEl('text',{x:10,y:20+i*16,fill:COLOUR.ink,'font-size':readable?14:12});text.textContent=line;card.append(text);});}}}},get camera(){return {...camera};},setCamera(value){if(!value||!['x','y','k'].every(key=>Number.isFinite(value[key]))||value.k<=0)throw Error('Invalid presentation camera.');fitCamera=false;camera={...value,k:readable?Math.max(1,value.k):value.k};paintCamera();},highlight(id){selected=id;for(const node of region.querySelectorAll('[data-topology-node]')){node.classList.toggle('is-selected',node.dataset.topologyNode===id);if(node.localName==='button')node.setAttribute('aria-current',String(node.dataset.topologyNode===id));}},update({nodes:more=[],edges:extra=[],boundaries:outside=null}={}){const known=new Set(state.nodes.map(node=>node.id));state.nodes.push(...more.filter(node=>!known.has(node.id)));state.edges.push(...extra);if(outside)state.boundaries=outside;paint();},
    select(id){selected=id;paint();},unfold(rank,count=Infinity){if(rank===undefined)for(const r of plan?.wide||[])open.set(r,count);else open.set(rank,count);paint();},fold(){open.clear();paint();},
    get folds(){return plan?.folds||[];},get rows(){return topologyRows(state.nodes,state.edges,state.boundaries);},destroy(){alive=false;resizeObserver?.disconnect();region.remove();},get alive(){return alive;},
    // the view's own focus target: the drawn viewport, else the list's first control
    focus(){(canDraw?viewport:list.querySelector?.('button')||region).focus?.();}};
}
