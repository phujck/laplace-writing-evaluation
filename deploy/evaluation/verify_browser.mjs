// Actual Chromium/UI journey against the image's server. No intercepted routes,
// no injected provider responses, and no model operations.
import {createRequire} from 'node:module';
import {readFileSync,writeFileSync} from 'node:fs';
import path from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
const require=createRequire(import.meta.url);
let pw;
for(const name of [process.env.PLAYWRIGHT_MODULE,'playwright','playwright-core','/opt/evaluation/browser/node_modules/playwright'].filter(Boolean)){
  try{pw=require(name);break;}catch{}
}
if(!pw)throw Error('Image must include actual Playwright and Chromium; no download attempted by verifier.');
const base=process.argv[2]||'http://127.0.0.1:8771';
const workspace=process.argv[3]||'/data/workspace';
const out=path.join(workspace,'container-verification');
const browser=await pw.chromium.launch({headless:true,args:['--no-sandbox'],
  ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE?{executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE}:{})});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
page.setDefaultTimeout(30000);
const frame='iframe[title="Manuscript reader and editor"]';
const witness=' Container persistence witness.';
const sha=bytes=>createHash('sha256').update(bytes).digest('hex');
const receipt={scope:'Actual Chromium create Article → edit paragraph → Save → parent reload → Undo → Home/reopen. No model calls.',checks:[]};
async function ready(p){await p.waitForFunction(s=>{
  const f=document.querySelector(s),w=f?.contentWindow;
  return w?.location.pathname==='/walk'&&w.walk?.ready?.()&&w.walk.blocks().length>0;
},frame);}
async function get(route){const r=await fetch(base+route);if(!r.ok)throw Error(route+': '+r.status);return r.json();}
try{
  await page.goto(base+'/project?workspace=writing&app=projects&start=create',{waitUntil:'domcontentloaded'});
  await page.getByLabel('Working title',{exact:true}).fill('Container writing check '+randomUUID().slice(0,8));
  await page.getByLabel(/^Project category/).selectOption('paper');
  await page.getByLabel('Purpose',{exact:true}).fill('Disposable persistent volume check; no provider calls.');
  await Promise.all([page.waitForURL(u=>u.pathname==='/project'&&u.searchParams.get('corpus')&&u.searchParams.get('view')==='overview'),
    page.getByRole('button',{name:'Create project',exact:true}).click()]);
  const project=new URL(page.url()).searchParams.get('corpus');
  await page.getByRole('button',{name:'Continue writing',exact:true}).click();await ready(page);
  const block=await page.evaluate(s=>document.querySelector(s).contentWindow.walk.blocks().find(b=>b.file==='chapters/chapter-01.tex'&&b.line_start===2),frame);
  if(!block)throw Error('Actual starter paragraph missing; refusing guessed editor coordinates.');
  const reg=JSON.parse(readFileSync(path.join(workspace,'registry_projects.json')));
  const selected=reg.projects.find(p=>p.name===project);
  const file=path.join(selected.manifest.document.manuscript_dir,block.file);
  const target=path.join(workspace,file),before=readFileSync(target);
  await page.frameLocator(frame).locator('#doc .blk[data-block='+JSON.stringify(block.id)+'] .blk-body').click();
  await page.keyboard.press('End');await page.keyboard.type(witness);
  await page.getByRole('button',{name:'Save changes',exact:true}).click();
  await page.waitForFunction(s=>{const w=document.querySelector(s)?.contentWindow?.walk,e=w?.editState?.();return w?.ready?.()&&e&&!e.dirty&&!e.parked;},frame);
  const saved=readFileSync(target);
  if(!saved.includes(witness)||sha(before)===sha(saved))throw Error('UI Save did not commit witness bytes.');
  receipt.checks.push({check:'manual UI edit and Save commit exact bytes',before_sha256:sha(before),saved_sha256:sha(saved)});
  await page.reload({waitUntil:'domcontentloaded'});await ready(page);
  const contains=await page.evaluate(({s,w})=>document.querySelector(s).contentWindow.walk.blocks().some(b=>String(b.text).includes(w)),{s:frame,w:witness});
  if(!contains)throw Error('Parent reload lost saved paragraph.');
  await page.getByText('Document tools',{exact:true}).click();
  await page.locator('[data-control="manuscript:undo"]').click();
  await page.waitForFunction(({s,w})=>{const x=document.querySelector(s)?.contentWindow?.walk;return x?.ready?.()&&!x.blocks().some(b=>String(b.text).includes(w));},{s:frame,w:witness});
  // Wait for actual source owner write, not only DOM disappearance.
  for(let i=0;i<100&&sha(readFileSync(target))!==sha(before);i++)await new Promise(r=>setTimeout(r,100));
  const undone=readFileSync(target);
  if(sha(undone)!==sha(before))throw Error('Undo did not restore exact original source bytes.');
  await page.locator('[data-control="nav:overview"]').click();
  await page.getByRole('button',{name:'Continue writing',exact:true}).click();await ready(page);
  await page.reload({waitUntil:'domcontentloaded'});await ready(page);
  if(sha(readFileSync(target))!==sha(before))throw Error('Normal reload/reopen changed restored source.');
  const fresh=await browser.newPage();
  await fresh.goto(base+'/project?'+new URLSearchParams({workspace:'writing',corpus:project,view:'manuscript'}));await ready(fresh);
  await fresh.screenshot({path:path.join(out,'browser-reopened.png'),fullPage:true});
  const doc=await get('/walk/doc?'+new URLSearchParams({corpus:project}));
  if(!doc.ok)throw Error('Fresh HTTP document failed.');
  const state={project,file,original_sha256:sha(before),saved_sha256:sha(saved),restored_sha256:sha(undone)};
  writeFileSync(path.join(out,'browser-state.json'),JSON.stringify(state,null,2)+'\n');
  receipt.status='PASS';receipt.browser=browser.version();receipt.state=state;
  receipt.checks.push({check:'Undo restores exact original; Home/reopen, parent reload and fresh tab work'});
}catch(e){receipt.status='FAIL';receipt.error=String(e.stack||e);throw e;}
finally{writeFileSync(path.join(out,'browser-proof.json'),JSON.stringify(receipt,null,2)+'\n');await browser.close();console.log(JSON.stringify(receipt));}
