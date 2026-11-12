import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createRequire} from 'node:module';
import {restructureWire} from './helpers/reader_restructure_fixture.mjs';
import {validateRestructurePreview,restructureApplySubmission,restructureFollowThroughSubmission} from '../src/laplace/web/static_shared/reader-restructure.mjs';
import {walkSource} from './helpers/walk_source.mjs';

const require=createRequire(import.meta.url);
let browserModule;
for(const name of process.env.LAPLACE_PLAYWRIGHT_MODULE?[process.env.LAPLACE_PLAYWRIGHT_MODULE]:['playwright','playwright-core']){
  let resolved;
  try{resolved=require.resolve(name);}catch(error){if(error.code!=='MODULE_NOT_FOUND')throw error;continue;}
  browserModule=require(resolved);break;
}
if(!browserModule?.chromium)throw Error('Browser test dependency unavailable. Make playwright or playwright-core resolvable, or set LAPLACE_PLAYWRIGHT_MODULE to an existing installed module. This acceptance test cannot be skipped.');
const {chromium}=browserModule;
const source=walkSource();
const section=(first,last)=>{const start=source.indexOf(first);assert.ok(start>=0);const end=source.indexOf(last,start);assert.ok(end>start);return source.slice(start,end);};
const code=section('const isChrome =','function srcOf(')+section('const SOURCE_OF =','// ── the piecewise-exact source map')+
  section('function sourceForRenderedRange(','/** Why the splice')+section('function caretRange(','function insertEditorText(');
async function withDOM(run){
  let browser;
  try{browser=await chromium.launch({headless:true,args:['--no-sandbox'],...(process.env.LAPLACE_BROWSER_EXECUTABLE?{executablePath:process.env.LAPLACE_BROWSER_EXECUTABLE}:{})});}
  catch(error){throw new Error('Chromium is unavailable. Use the browser supplied by the installed Playwright runtime, or set LAPLACE_BROWSER_EXECUTABLE to an existing Chromium/Chrome executable. This acceptance test cannot be skipped.',{cause:error});}
  try{
    const page=await browser.newPage();await page.setContent('<div id="host" contenteditable="true">Saved source</div>');
    await page.addScriptTag({content:code+'\nwindow.editorDOM={hostText,offsetIn,caretRange,nodeTextLen,sourceForRenderedRange};'});
    await run(page);
  }finally{await browser.close();}
}
async function nativePaste(page,text){
  await page.locator('#host').focus();await page.keyboard.press('Control+a');await page.keyboard.insertText(text);
  return page.locator('#host').evaluate(host=>{
    const api=window.editorDOM,text=api.hostText(host),roundtrips=[];
    for(let at=0;at<=text.length;at++){
      const range=api.caretRange(host,at);roundtrips.push(api.offsetIn(host,range.startContainer,range.startOffset));
    }
    return {html:host.innerHTML,text,roundtrips,source:api.sourceForRenderedRange({bodyEl:host,tex:'Saved source',pieceMap:[]},0,text.length)};
  });
}

test('actual Chromium native multiline paste keeps every authored blank line in source and caret offsets',async()=>withDOM(async page=>{
  const text='A source edit has a specific recorded outcome.\n\nThe save receipt describes what happened to the source bytes.\n\nThe same receipt can identify related work that needs inspection. Saving the text does not by itself complete those checks.';
  const observed=await nativePaste(page,text);
  assert.match(observed.html,/<div><br><\/div>/);assert.equal(observed.text,text);assert.equal(observed.source,text);
  assert.deepEqual(observed.roundtrips,Array.from({length:text.length+1},(_,index)=>index));
  for(const text of ['Ordinary text.','One line.\nSoft line.','\n\nUnfinished opening.','Unfinished end.\n\n']){
    const observed=await nativePaste(page,text);assert.equal(observed.text,text);assert.equal(observed.source,text);
    assert.deepEqual(observed.roundtrips,Array.from({length:text.length+1},(_,index)=>index));
  }
}));

test('actual native three and twelve paragraph DOM serialize to one exact owner draft and guarded inverse',async()=>withDOM(async page=>{
  for(const item of restructureWire.multipart){
    const observed=await nativePaste(page,item.draft.parts.join('\n\n'));
    const draft={...item.draft,parts:observed.source.split('\n\n'),source_edits:item.draft.source_edits.map(edit=>({...edit,after:observed.source}))};
    validateRestructurePreview(item.preview,{project:'book',kind:'presentation-split',draft});
    assert.deepEqual(restructureApplySubmission(item.preview,'book').payload.draft,draft);
    assert.equal(item.complete.remapped_occurrences.length,item.draft.parts.length);
    assert.equal(restructureFollowThroughSubmission(item.complete.undo_action,'book',item.complete,'undo-restructure').payload.action,'undo-restructure');
    assert.equal(item.undone.complete,true,'The real owner fixture proves byte-identical Undo of this exact serialized draft.');
  }
}));

test('shared DOM map preserves soft BR, emphasis and source atoms, including Enter hidden-tail staging',async()=>withDOM(async page=>{
  const value=await page.locator('#host').evaluate(host=>{
    const api=window.editorDOM;
    host.innerHTML='<em>Emphasis</em> <span class="mathq"><div>ω</div><div>x</div></span><br>Tail<span data-chrome>ignored</span>';
    const math=host.querySelector('.mathq'),tex='Emphasis $\\omega x$\nTail',start=tex.indexOf('$'),end=tex.lastIndexOf('$')+1;
    const block={bodyEl:host,tex,pieceMap:[{nodes:[math],oStart:start,oEnd:end}]};
    const atomStart=api.offsetIn(host,math,0),atomEnd=atomStart+api.nodeTextLen(math);
    const result={text:api.hostText(host),atom:api.sourceForRenderedRange(block,atomStart,atomEnd),emphasis:host.querySelector('em').textContent};
    host.innerHTML='A<!-- ignored --><div><br></div><span data-chrome>ignored</span><!-- ignored --><div>B</div>';
    result.comments=api.hostText(host);
    host.textContent='First. Second.';
    const text=host.firstChild,range=document.createRange();range.setStart(text,6);range.collapse(true);
    const breakNode=document.createTextNode('\n\n');range.insertNode(breakNode);
    const tail=document.createRange();tail.selectNodeContents(host);tail.setStartAfter(breakNode);
    const hidden=document.createElement('span');hidden.hidden=true;hidden.append(tail.extractContents());host.append(hidden);
    result.enter=api.hostText(host);result.hidden=hidden.textContent;return result;
  });
  assert.equal(value.text,'Emphasis ωx\nTail');assert.equal(value.atom,'$\\omega x$');assert.equal(value.emphasis,'Emphasis');
  assert.equal(value.comments,'A\n\nB');
  assert.equal(value.enter,'First.\n\n Second.');assert.equal(value.hidden,' Second.');
}));
