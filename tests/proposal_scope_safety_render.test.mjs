import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as editing from '../src/laplace/web/static_shared/manuscript-editing.mjs';
import {walkSource,walkDeclarations} from './helpers/walk_source.mjs';
const source=walkSource();
const code=walkDeclarations('showProposal');
// The renderer's helpers are exactly the names its owner module (walk-review.mjs) imports from manuscript-editing.mjs
// (its real import line).
const reviewSource=readFileSync(new URL('../src/laplace/web/static_shared/walk-review.mjs',import.meta.url),'utf8');
const imported=reviewSource.match(/import \{([^}]*)\} from "\/shared\/manuscript-editing\.mjs";/)[1].split(',').map(n=>n.trim()).filter(Boolean);
const helpers=Object.fromEntries(imported.map(n=>{assert.ok(n in editing,n);return [n,editing[n]];}));
const {proposalResolutionAvailable,proposalScopeUnproven,proposalDraftKey,proposalDraftBasis,proposalActionAllowed,proposalDraftOverlap,proposalComparisonAvailable,proposalReviewStatus}=editing;
class Node {
 constructor(tag,cls,text=''){this.tag=tag;this.className=cls;this.textContent=text;this.children=[];this.dataset={};this.attrs={};this.offsetTop=10;this.classList={add(){}};}
 append(...nodes){this.children.push(...nodes);}
 setAttribute(k,v){this.attrs[k]=v;}
 all(){return [this,...this.children.flatMap(n=>n.all())];}
 querySelectorAll(selector){return this.all().filter(n=>n.tag===selector);}
}
test('real proposal renderer offers inspection and keep, preserves draft and does not move current source',async()=>{
 let inserted,sourceMoves=0,sourceHighlights=0;const block={id:'current-block',src:{file:'chapter.tex',lineStart:50,lineEnd:60},el:{before:n=>inserted=n,classList:{add:()=>sourceHighlights++}},bodyEl:{setAttribute:()=>sourceMoves++}};
 const drafts=new Map([['laplace:proposal-draft:p:t:e','Held combined wording']]),decisions=[];
 const ctx={docEl:{querySelectorAll:()=>[]},proposalUiStates:new Map(),proposalDraftKey,proposalActionAllowed,proposalDraftOverlap,manuscriptDraftRanges:()=>[],S:{corpus:'p',blocks:[block]},proposalView:null,clearObjectSelection(){},captureFocus:()=>({}),clearProposal(){},suspendAuthorChanges(){},srcOf:b=>b.src,
 el:(...a)=>new Node(...a),asChrome:n=>n,proposalModels:(host,models,id)=>{const bs=models.map((text,i)=>({id:id+i,el:new Node('p','',text)}));host.append(...bs.map(b=>b.el));return bs;},
 paintRevisionDifference:()=>({before:[]}),syncRevisionHighlights(){},measure(){},restoreFocus(){},emit(){},paper:{scrollTop:0},attentionBlockId:null,noteAttention:id=>{ctx.attentionBlockId=id;},
 localStorage:{getItem:k=>drafts.get(k)??null,removeItem:k=>drafts.delete(k)},proposalResolutionAvailable,proposalScopeUnproven,proposalDraftKey,proposalDraftBasis,proposalActionAllowed,proposalDraftOverlap,proposalComparisonAvailable,proposalReviewStatus,...helpers};
 vm.createContext(ctx);vm.runInContext(code+';this.render=showProposal',ctx);
 ctx.render({turn_id:'t',proposal_version:'version',reviewable:true,edits:[{edit_id:'e',file:'chapter.tex',line_start:999,line_end:1002,status:'conflict',allowed_actions:['keep-current'],resolution_available:false,current_mapping:'unproven-historical-location',review_token:'obsolete-token',before:'Historical words',before_blocks:['Historical words'],after:'Proposed words',after_blocks:['Proposed words']}]},{onDecision:async(...x)=>decisions.push(x),onInspectCurrentFile(){},onRequestChanges(){}});
 const nodes=inserted.all(),buttons=nodes.filter(n=>n.tag==='button');assert.equal(sourceMoves,0);assert.equal(sourceHighlights,0);
 assert.ok(nodes.some(n=>n.textContent==='Original saved passage · historical comparison'));
 assert.ok(buttons.some(n=>n.textContent==='Inspect current source file'));assert.ok(buttons.some(n=>n.textContent==='Request fresh reconciliation'));
 assert.equal(buttons.some(n=>/^(Accept|Replace current passage|Edit combined|Save combined passage)$/.test(n.textContent)),false);
 const retained=nodes.find(n=>n.tag==='textarea');assert.equal(retained.readOnly,true);assert.equal(retained.value,'Held combined wording');
 await buttons.find(n=>n.textContent==='Keep current').onclick();assert.equal(decisions.length,1);assert.equal(decisions[0][1],'keep-current');assert.equal(drafts.size,1);
});

test('a current edit with a pending local review says it can be applied and what stays to review',()=>{
 let inserted,sourceMoves=0,sourceHighlights=0;const block={id:'current-block',src:{file:'chapter.tex',lineStart:50,lineEnd:60},el:{before:n=>inserted=n,classList:{add:()=>sourceHighlights++}},bodyEl:{setAttribute:()=>sourceMoves++}};
 const drafts=new Map([['laplace:proposal-draft:p:t:e','Held combined wording']]),decisions=[];
 const ctx={docEl:{querySelectorAll:()=>[]},proposalUiStates:new Map(),proposalDraftKey,proposalActionAllowed,proposalDraftOverlap,manuscriptDraftRanges:()=>[],S:{corpus:'p',blocks:[block]},proposalView:null,clearObjectSelection(){},captureFocus:()=>({}),clearProposal(){},suspendAuthorChanges(){},srcOf:b=>b.src,
 el:(...a)=>new Node(...a),asChrome:n=>n,proposalModels:(host,models,id)=>{const bs=models.map((text,i)=>({id:id+i,el:new Node('p','',text)}));host.append(...bs.map(b=>b.el));return bs;},
 paintRevisionDifference:()=>({before:[]}),syncRevisionHighlights(){},measure(){},restoreFocus(){},emit(){},paper:{scrollTop:0},attentionBlockId:null,noteAttention:id=>{ctx.attentionBlockId=id;},
 localStorage:{getItem:k=>drafts.get(k)??null,removeItem:k=>drafts.delete(k)},proposalResolutionAvailable,proposalScopeUnproven,proposalDraftKey,proposalDraftBasis,proposalActionAllowed,proposalDraftOverlap,proposalComparisonAvailable,proposalReviewStatus,...helpers};
 ctx.document={createElement:tag=>new Node(tag,''),createComment:text=>new Node('#comment','',''),createTextNode:text=>new Node('#text','',text),activeElement:null,querySelector:()=>null};
 vm.createContext(ctx);vm.runInContext(code+';this.render=showProposal',ctx);
 ctx.render({turn_id:'t',proposal_version:'version',reviewable:true,edits:[{edit_id:'e',file:'chapter.tex',line_start:999,line_end:1002,status:'conflict',allowed_actions:['keep-current'],resolution_available:false,
  current_mapping:'unproven-historical-location',review_token:'obsolete-token',before:'Historical words',before_blocks:['Historical words'],after:'Proposed words',
  after_blocks:['Proposed words'],basis_currentness:'CURRENT',review_obligations:[{schema:'laplace.scoped-obligation/1',kind:'CONSULTED_INPUT_CHANGED',reason:'A consulted observation changed.'}]}]},{onDecision:async()=>{},onInspectCurrentFile(){},onRequestChanges(){}});
 const text=inserted.all().map(n=>n.textContent).join(' ');
 assert.match(text,/This edit can be applied: it changes only the source it names/);
 assert.match(text,/Applying is not acceptance of every claim it touches/);
 assert.doesNotMatch(text,/Inputs changed; reconcile this edit/);
});
