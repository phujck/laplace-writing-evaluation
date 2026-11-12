// READER-PLAN USABILITY (M5 2026-10-16, WORK-editor-reader-plan-usability-20261015). Root measured the live plan: six
// paragraph cards repeating the whole edit/split/combine/move/remove/review family, 96 buttons and a 4,303 px scroll in
// a 593 px viewport. The exposition plan is now compact rows in reading order with ONE open unit whose workspace shows
// what the reader brings and gains, a missing-transition cue, and actions grouped by what they change, each group saying
// its consequence before any effect. The open unit survives a re-render (save, refresh, return). Display rows only.
import assert from 'node:assert/strict';
import {test} from 'node:test';
import {renderReaderState} from '../src/laplace/web/static_shared/reader-state.mjs';
import {beatLabel} from '../src/laplace/web/static_shared/workspace-spine.mjs';
import {installDOM,Node} from './helpers/evidence_reader_harness.mjs';

const DOORS=['edit','remove','split','merge','review'];
const unit=(i,extra={})=>({paragraph_id:'PAR-'+i,proposition:'Point '+i,function:'step',from_previous:i?'Builds on point '+(i-1):'',to_next:'Prepares point '+(i+1),
  explanation:'Explain '+i,doors:DOORS,authored:[],clipped:[],...extra});
const section=(items,offset=0)=>({id:'orientation',title:'Orientation',paragraph_plan:{status:'DECLARED',revision:'sha256:'+'1'.repeat(64),doors:['reorder','create'],
  paragraphs:{items,offset,total:114,next_read:{operation:'structure',payload:{view:'detail'}}}}});
const handlers=()=>({onEditParagraph(){},onParagraphAction(){},onLogicalRestructure(){},onReview(){},onRead(){},onError:error=>{throw error;}});
const buttons=host=>host.all().filter(n=>n.tag==='button');
const head=(host,id)=>host.querySelectorAll('.reader-paragraph').find(card=>card.dataset.paragraphId===id).all().find(n=>n.attrs['data-control']==='reader-plan:unit-select');

test('a page of planned units is compact rows; only the open unit carries fields and mutation controls',()=>{
  const dom=installDOM();try{
    const host=new Node('section');dom.body.append(host);
    renderReaderState(host,{project:'guide',section:section(Array.from({length:6},(_,i)=>unit(i))),...handlers()});
    const cards=host.querySelectorAll('.reader-paragraph');
    assert.equal(cards.length,6,'every unit keeps its exact identity row');
    assert.deepEqual(cards.map(card=>card.dataset.focused),['true','false','false','false','false','false']);
    const mutations=buttons(host).filter(n=>/^(Edit paragraph plan|Split planned unit|Combine planned units|Move paragraph plan|Remove paragraph plan|Create paragraph review work)$/.test(n.textContent));
    assert.equal(mutations.length,6,'one unit\'s six doors, not 36');
    assert.ok(mutations.every(n=>cards[0].all().includes(n)));
    assert.ok(buttons(host).length<=6+6+3,'six row selectors, the open unit\'s doors and the page doors: '+buttons(host).length);
    // rows say where they sit and how they follow; raw ids are not the label
    assert.match(head(host,'PAR-3').attrs['aria-label'],/^Planned unit 4 · Point 3$/);
    assert.match(head(host,'PAR-3').textContent,/Follows: Builds on point 2/);
  }finally{dom.restore();}
});

test('the open unit shows reader knowledge before and after, and each action group states its consequence first',()=>{
  const dom=installDOM();try{
    const host=new Node('section');dom.body.append(host);
    renderReaderState(host,{project:'guide',section:section([unit(0),unit(1,{from_previous:''}),unit(2)]),...handlers()});
    let open=host.querySelectorAll('.reader-paragraph')[0];
    assert.match(open.textContent,/Point the reader gains.*Point 0.*Leads the reader on to.*Prepares point 1/s);
    for(const consequence of [/manuscript text is not edited/,/scope and a preview first; it changes the reader plan, never the manuscript source/,/does not start a writing session/])
      assert.match(open.textContent,consequence);
    // the missing step: unit 2 has no written connection from unit 1
    assert.match(head(host,'PAR-1').textContent,/Transition not written/);
    head(host,'PAR-1').onclick();
    open=host.querySelectorAll('.reader-paragraph').find(card=>card.dataset.focused==='true');
    assert.equal(open.dataset.paragraphId,'PAR-1');
    assert.match(open.textContent,/No connection from the preceding unit is written: a step may be missing, or the transition is unsupported/);
    assert.equal(globalThis.document.activeElement,head(host,'PAR-1'),'focus stays on the unit just opened');
  }finally{dom.restore();}
});

test('the open unit is remembered for its section across a re-render, and arrows move between units',()=>{
  const dom=installDOM();try{
    const items=Array.from({length:4},(_,i)=>unit(i)),first=new Node('section');dom.body.append(first);
    renderReaderState(first,{project:'guide-keep',section:section(items),...handlers()});
    head(first,'PAR-2').onclick();
    const again=new Node('section');dom.body.append(again);
    renderReaderState(again,{project:'guide-keep',section:section(items),...handlers()});
    assert.equal(again.querySelectorAll('.reader-paragraph').find(card=>card.dataset.focused==='true').dataset.paragraphId,'PAR-2','a save or refresh returns to the same unit');
    let prevented=false;head(again,'PAR-2').onkeydown({key:'ArrowDown',preventDefault(){prevented=true;}});
    assert.equal(globalThis.document.activeElement,head(again,'PAR-3'));assert.equal(prevented,true);
    // a unit no longer on the page falls back to the first, never to a guess
    const other=new Node('section');dom.body.append(other);
    renderReaderState(other,{project:'guide-keep',section:section([unit(7),unit(8)],7),...handlers()});
    assert.equal(other.querySelectorAll('.reader-paragraph').find(card=>card.dataset.focused==='true').dataset.paragraphId,'PAR-7');
    assert.match(head(other,'PAR-7').attrs['aria-label'],/^Planned unit 8 /,'numbers are reading order across pages');
  }finally{dom.restore();}
});

test('narrative beats are named by their term, or their id made readable',()=>{
  assert.equal(beatLabel({id:'res:diamond-recovery',term:'The diamond recovers'}),'The diamond recovers');
  assert.equal(beatLabel({id:'res:diamond-recovery'}),'diamond recovery');
  assert.equal(beatLabel({id:'def:token_basis'}),'token basis');
});
