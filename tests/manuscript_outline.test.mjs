import {beforeEach,test} from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
import {register} from 'node:module';register(new URL('./helpers/shared_resolve.mjs',import.meta.url));
// the outline helpers are the real facade exports (workspace-manuscript-outline.mjs, M5 S2 F1)
const source=await readFile(new URL('../src/laplace/web/static_shared/workspace.mjs',import.meta.url),'utf8');
const {manuscriptOutlineTree,manuscriptOutlinePosition,plannedManuscriptHeading,currentManuscriptHeading,manuscriptHeadingDeletion,mountManuscriptOutline}=await import('../src/laplace/web/static_shared/workspace.mjs');
class Node {
 constructor(tag='div'){this.tag=tag;this.children=[];this.dataset={};this.attrs={};this.className='';this.style={};this._text='';this.isConnected=true;this.hidden=false;}
 set textContent(value){this._text=String(value);this.children=[];}get textContent(){return this._text+this.children.map(node=>node.textContent).join('');}
 append(...nodes){for(const node of nodes){node.parentElement=this;this.children.push(node);}}replaceChildren(...nodes){this._text='';this.children=[];this.append(...nodes);}setAttribute(name,value){this.attrs[name]=String(value);}removeAttribute(name){delete this.attrs[name];}
 remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(node=>node!==this);this.isConnected=false;}all(){return [this,...this.children.flatMap(node=>node.all())];}contains(node){return this.all().includes(node);}focus(){document.activeElement=this;}getBoundingClientRect(){return {left:10,top:10,bottom:40,width:220,height:140};}
}
beforeEach(()=>{globalThis.document={body:new Node('body'),createElement:tag=>new Node(tag),addEventListener(){},removeEventListener(){}};globalThis.window={innerWidth:1280,innerHeight:720,addEventListener(){},removeEventListener(){}};});
const sections=[{id:'chapter',title:'A real chapter'},...Array.from({length:7},(_,i)=>({id:'s'+i,title:'Scientific section '+i}))];
const heads=[{id:'chapter-head',section:'chapter',level:'chapter',title:'A real chapter',file:'chapter.tex',label:'ch:first',number:'1'},...Array.from({length:7},(_,i)=>({id:'head-'+i,section:'s'+i,level:'section',title:'Scientific section '+i,file:'chapter.tex',label:'sec:'+i,number:'1.'+(i+1)}))];
const find=(host,cls)=>host.all().find(node=>node.className===cls),all=(host,cls)=>host.all().filter(node=>node.className===cls);
const visible=node=>{for(let at=node;at;at=at.parentElement)if(at.hidden)return false;return true;};

test('source order produces one chapter row with seven children and only observed numbering',()=>{
 const tree=manuscriptOutlineTree(sections,heads);assert.equal(tree.length,1);assert.equal(tree[0].children.length,7);assert.deepEqual(tree[0].children.map(node=>node.number),['1.1','1.2','1.3','1.4','1.5','1.6','1.7']);
 const plain=manuscriptOutlineTree([{id:'s',title:''}],[{id:'h',section:'s',level:'section',title:'',file:'main.tex'}]);assert.equal(plain[0].title,'Untitled section');assert.equal(plain[0].number,'');
});
test('subheadings retain their actual hierarchy and paragraph attention resolves to the preceding heading',()=>{
 const nested=[heads[0],heads[1],{id:'sub',section:'s0',level:'subsection',title:'A premise',file:'chapter.tex'},...heads.slice(2)];const tree=manuscriptOutlineTree(sections,nested);assert.equal(tree[0].children[0].children[0].head.id,'sub');assert.equal(tree[0].children[1].head.id,'head-1');
 const blocks=[{id:'chapter-head'},{id:'head-0'},{id:'sub'},{id:'para'},{id:'head-1'}];assert.equal(manuscriptOutlinePosition(nested,blocks,{blockId:'para'},'s0'),'sub');assert.equal(manuscriptOutlinePosition(nested,blocks,{},'s1'),'head-1');
});
test('compact outline navigates exact source headings, preserves collapsed state and has no repeated ceremony rows',()=>{
 const host=new Node(),navigated=[],tree=manuscriptOutlineTree(sections,heads),options={tree,current:'head-0',onNavigate:node=>navigated.push(node.head.id),actionsFor:()=>[{label:'Rename heading',run(){}}]};const mounted=mountManuscriptOutline(host,options);
 assert.equal(all(host,'outline-title').filter(visible).length,8);assert.ok(!host.textContent.includes('Section actions'));assert.ok(!host.textContent.includes('Subsections'));all(host,'outline-title')[7].onclick();assert.deepEqual(navigated,['head-6']);
 find(host,'outline-toggle').onclick();assert.equal(all(host,'outline-title').filter(visible).length,1);const expanded=mounted.capture();mounted.destroy();mountManuscriptOutline(host,{...options,expanded});assert.equal(all(host,'outline-title').filter(visible).length,1);
});
test('only the current chapter path opens automatically, and deliberate choices survive refresh and navigation',()=>{
 const moreHeads=[...heads,{id:'chapter-two',section:'chapter2',level:'chapter',title:'Second chapter',file:'second.tex',label:'ch:second'},...Array.from({length:5},(_,index)=>({id:'second-'+index,section:'second'+index,level:'section',title:'Second section '+index,file:'second.tex',label:'s:second'+index}))],moreSections=[...sections,{id:'chapter2'},...Array.from({length:5},(_,index)=>({id:'second'+index}))];const tree=manuscriptOutlineTree(moreSections,moreHeads),host=new Node(),changes=[];
 let mounted=mountManuscriptOutline(host,{tree,current:'head-0',onNavigate(){},onExpansionChange:value=>changes.push(value)});let toggles=all(host,'outline-toggle');assert.equal(toggles[0].attrs['aria-expanded'],'true');assert.equal(toggles[1].attrs['aria-expanded'],'false');assert.equal(mounted.capture().size,0,'automatic path is not stored as a deliberate expansion');
 toggles[0].onclick();assert.equal(toggles[0].attrs['aria-expanded'],'false');assert.equal(all(host,'outline-row')[0].dataset.currentPath,'true');mounted.setCurrent('head-1');assert.equal(toggles[0].attrs['aria-expanded'],'false','moving within a deliberately collapsed chapter does not undo the choice');
 mounted.setCurrent('second-2');assert.equal(toggles[1].attrs['aria-expanded'],'true');assert.equal(toggles[0].attrs['aria-expanded'],'false');toggles[0].onclick();const saved=new Map(JSON.parse(JSON.stringify([...mounted.capture()])));mounted.destroy();mounted=mountManuscriptOutline(host,{tree,current:'second-2',expanded:saved,onNavigate(){}});toggles=all(host,'outline-toggle');assert.equal(toggles[0].attrs['aria-expanded'],'true');assert.equal(toggles[1].attrs['aria-expanded'],'true');assert.equal(changes.length,2);
 mounted.setCurrent('head-3');assert.equal(toggles[1].attrs['aria-expanded'],'false','previous automatic chapter folds when reading elsewhere');
});
test('outline keyboard arrows expand, visit children, collapse and return to the parent',()=>{
 const host=new Node();mountManuscriptOutline(host,{tree:manuscriptOutlineTree(sections,heads),current:'head-0',onNavigate(){}});const rows=all(host,'outline-row'),titles=all(host,'outline-title'),toggles=all(host,'outline-toggle');const key=(row,key)=>row.onkeydown({key,target:titles[rows.indexOf(row)],preventDefault(){}});
 key(rows[0],'ArrowLeft');assert.equal(toggles[0].attrs['aria-expanded'],'false');key(rows[0],'ArrowRight');assert.equal(toggles[0].attrs['aria-expanded'],'true');key(rows[0],'ArrowRight');assert.equal(document.activeElement,titles[1]);key(rows[1],'ArrowLeft');assert.equal(document.activeElement,titles[0]);
});
test('source refresh preserves a visible heading anchor and repeated attention does not scroll or remeasure it',()=>{
 const host=new Node(),nav={scrollTop:170,getBoundingClientRect:()=>({top:0,bottom:220})};host.closest=()=>nav;let measures=0;const geometry=()=>all(host,'outline-row').forEach((row,index)=>{row.getBoundingClientRect=()=>{measures++;return {top:100+index*30-nav.scrollTop,bottom:130+index*30-nav.scrollTop};};});
 const options={tree:manuscriptOutlineTree(sections,heads),current:'head-3',onNavigate(){}};let mounted=mountManuscriptOutline(host,options);geometry();const scroll=mounted.captureScroll(),expanded=mounted.capture();assert.ok(scroll.anchor);const before=measures;for(let i=0;i<100;i++)mounted.setCurrent('head-3');assert.equal(measures,before);assert.equal(nav.scrollTop,170);mounted.destroy();
 const newHead={id:'inserted',section:'new-section',level:'section',title:'An inserted heading',file:'chapter.tex',label:'sec:new'};mounted=mountManuscriptOutline(host,{...options,expanded,tree:manuscriptOutlineTree([sections[0],{id:'new-section'},...sections.slice(1)],[heads[0],newHead,...heads.slice(1)])});geometry();nav.scrollTop=0;mounted.restoreScroll(scroll);assert.equal(nav.scrollTop,200,'the same original heading remains at its prior screen offset after insertion above it');assert.equal(mounted.captureScroll().anchor,scroll.anchor);assert.equal(mounted.captureScroll().offset,scroll.offset);assert.equal(all(host,'outline-title').filter(node=>node.attrs['aria-current']==='location').length,1);
});
test('row menus are available by button, right click and keyboard and invoke the original action identity',async()=>{
 const host=new Node(),seen=[];mountManuscriptOutline(host,{tree:manuscriptOutlineTree(sections,heads),current:'head-0',onNavigate(){},actionsFor:node=>[{label:'Rename heading',run:()=>seen.push(['rename',node.head.id])},{label:'Delete section and contents',run:()=>seen.push(['delete',node.head.id])},{label:'Move earlier in reader plan',disabled:true,reason:'First within its parent.',run:()=>seen.push(['move',node.head.id])}]});
 const row=all(host,'outline-row')[1],more=all(host,'outline-more')[1];more.onclick();let menu=find(document.body,'manuscript-outline-menu');assert.equal(menu.attrs.role,'menu');assert.equal(menu.children[2].disabled,true);assert.equal(menu.children[2].title,'First within its parent.');await menu.children[1].onclick();assert.deepEqual(seen,[['delete','head-0']]);
 let prevented=false;row.oncontextmenu({type:'contextmenu',clientX:30,clientY:40,preventDefault(){prevented=true;}});assert.ok(prevented);menu=find(document.body,'manuscript-outline-menu');menu.onkeydown({key:'Escape',preventDefault(){}});assert.equal(document.activeElement,more);assert.equal(more.attrs['aria-expanded'],'false');
 row.onkeydown({key:'F10',shiftKey:true,preventDefault(){}});menu=find(document.body,'manuscript-outline-menu');await menu.children[0].onclick();assert.deepEqual(seen.at(-1),['rename','head-0']);
});
test('reader-plan actions require a unique source correspondence and never guess a repeated title',()=>{
 const linked=[{id:'plan-1',title:'Editorial title',source:{precision:'EXACT_HEADING',status:'MATCHED',heading:{file:heads[1].file,line:heads[1].line_start,label:'sec:0'}}}];assert.equal(plannedManuscriptHeading(linked,heads[1]).id,'plan-1');assert.equal(plannedManuscriptHeading(linked,{...heads[1],file:'other.tex'}),null);const ambiguous=[{id:'one',title:heads[1].title,source:{source_files:['chapter.tex']}},{id:'two',title:heads[1].title,source:{source_files:['chapter.tex']}}];assert.equal(plannedManuscriptHeading(ambiguous,heads[1]),null);
});


test('subsection deletion resolves its current label and never substitutes its parent plan identity',()=>{
 const head={id:'old',section:'parent',level:'subsection',title:'Inner',label:'sub:inner',file:'chapter.tex',line_start:3};
 const block={id:'fresh',kind:'head',level:'subsection',title:'Inner',label:'sub:inner',tex:'\\subsection{Inner}\n\\label{sub:inner}',src:{file:'chapter.tex',repo_file:'chapter.tex',line_start:5,line_end:6}};const doc={sections:[{id:'parent',blocks:[block]}]};const heading=currentManuscriptHeading(head,doc);assert.equal(heading.head.line_start,5);
 const source='\\section{Parent}\n\\label{sec:parent}\nLead.\n\n'+block.tex+'\nInner words.\n';const plan=[{id:'parent',title:'Inner',source:{source_files:['chapter.tex'],source_label:'sec:parent'}}];const target=manuscriptHeadingDeletion(heading,source,plan);assert.equal(target.kind,'subsection');assert.equal(target.line_start,5);assert.equal(target.section_id,'sub:inner');assert.notEqual(target.section_id,'parent');
 assert.throws(()=>manuscriptHeadingDeletion(heading,source.replace('sub:inner','sub:changed'),plan),/source changed/);assert.throws(()=>currentManuscriptHeading(head,{sections:[{id:'parent',blocks:[block,block]}]}),/ambiguous/);
 const linked=[...plan,{id:'own-plan',title:'An editorial title',source:{precision:'EXACT_HEADING',status:'MATCHED',heading:{file:'chapter.tex',line:5,label:'sub:inner'}}}];assert.equal(manuscriptHeadingDeletion(heading,source,linked).section_id,'own-plan');
});
