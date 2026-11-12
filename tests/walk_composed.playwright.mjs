// The walk composed, in a real browser (M5 S2 F3-F8, L-MENU-ELIGIBILITY). The real /walk page loads the walk
// composition root (walk.mjs and its owner modules) and the real writing panel against the real HTTP owners
// (tests/helpers/walk_owner_server.py); nothing is stubbed. Cases:
//   W1 bootstrap: ready, no page error, the model's block ids equal the rendered article ids, and the public
//      facade window.walk keeps exactly the frozen key set of the parent (199783380, 107 keys).
//   W2 a matched passage (article and its body): the eligible actions, focus on the first enabled item, one menu.
//   W3 a passage the current model does not hold (the article's id changed under it): the bounded unavailable
//      disposition with one draft-preserving "Reload the manuscript view" item, which refreshes the view so the
//      model and the DOM agree again; no basename, text or ordinal guess.
//   W4 a background with no action: the browser's own menu (no preventDefault, no popup).
//   W5 the loading disposition, through a facade double whose ready() is false (the real bootstrap renders and
//      becomes ready in one turn, so a block without a ready model is not reachable through the real open).
//   W6 the transient diagnostic: overwritten on each opening, bounded keys, no text.
// Run: node tests/walk_composed.playwright.mjs
import {startOwners} from './helpers/owner_browser.mjs';

const FROZEN_KEYS = [
  "actor","admit","armArtefact","armBlock","armBlockAtReadingLine","armCitationPlacement","armSelection","armSpan","armed","authorChangesEnabled",
  "bank","beginObjectMove","blocks","body","cancelFlip","captureFocus","checkOrphans","clearProposal","clearSpan","closeGeometry","closeLedger",
  "commitAll","commitEdit","context","contextualInsertionPoint","current","deleteBlock","deleteObject","deposits","disarm","dismissEditorCard","doc",
  "docSize","documentVersion","editBlock","editState","emitted","flip","flipState","focusProposal","geometry","identities","insertHeading","insertText",
  "insertionPoint","inspection","jumpToBlock","jumpToSection","ledger","nameActor","objectKind","off","on","openFind","openGeometry","openLedger",
  "openReferencePicker","outline","placeSent","placeStats","prepareForSession","proposalDraftConflict","quote","readingPosition","ready","reallocate",
  "redline","redoEdit","refresh","refreshAuthorChanges","reloadBlock","rememberExternalApplication","rememberExternalChange",
  "rememberExternalTransaction","restoreEditHistory","restoreFocus","returnMode","revertEdit","revokeRow","rewritePayload","ruleRow","ruleSet","ruling",
  "saveFlip","scopeRow","sections","session","setAuthorChanges","setDocSize","setFlipSource","setReturnMode","setRuling","setScope","shape",
  "showOtherVersion","showProposal","source","sourceObservation","span","spliceOf","spliceState","subscribers","suggestion","toggleRedline","undo","undoEdit",
  "wrapSelection"
];
let passed = 0;
function ok(condition, message) {
  if (!condition) throw new Error('FAIL: ' + message);
  passed += 1;
  console.log('ok - ' + message);
}
const DIAGNOSTIC_KEYS = ['block', 'connected', 'disposition', 'insertion', 'items', 'matches', 'ready', 'revision', 'rows'];

const owners = await startOwners();
try {
  const page = await owners.newPage({viewport: {width: 1100, height: 800}});
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {if (message.type() === 'error') errors.push(message.text());});
  await page.goto(owners.base + '/walk?corpus=book&embedded=1&editor=workbench');
  await page.waitForFunction(() => window.walk?.ready?.(), null, {timeout: 20000});

  // W1
  const boot = await page.evaluate(() => ({
    keys: Object.keys(window.walk).sort(),
    model: window.walk.blocks({text: false}).map(row => row.id),
    dom: [...document.querySelectorAll('#doc .blk[data-block]')].map(node => node.dataset.block),
  }));
  ok(errors.length === 0, 'W1 the walk boots on the real owners with no page or console error');
  ok(boot.model.length >= 6 && JSON.stringify(boot.model) === JSON.stringify(boot.dom), 'W1 model block ids equal the rendered article ids (' + boot.model.length + ')');
  ok(JSON.stringify(boot.keys) === JSON.stringify([...FROZEN_KEYS].sort()), 'W1 window.walk keeps exactly the frozen public key set (' + boot.keys.length + ')');
  const target = boot.model.find(id => id.endsWith('#b3'));
  ok(!!target, 'W1 the fixture has the article the Root incident named (#b3)');

  const menu = () => page.evaluate(() => {
    const node = document.getElementById('manuscript-context-menu');
    const diagnostic = JSON.parse(document.documentElement.dataset.passageMenu || 'null');
    return {count: document.querySelectorAll('#manuscript-context-menu').length, children: node?.children.length || 0,
      items: node ? [...node.querySelectorAll('[role=menuitem]')].map(item => item.textContent) : [],
      disposition: node?.dataset.disposition || null, focused: document.activeElement?.getAttribute('role') === 'menuitem' ? document.activeElement.textContent : null,
      diagnostic};
  });
  const rightClick = async selector => {
    await page.evaluate(() => {window.__prevented = null; window.addEventListener('contextmenu', event => {window.__prevented = event.defaultPrevented;}, {once: true});});
    await page.click(selector, {button: 'right'});
    return {...await menu(), prevented: await page.evaluate(() => window.__prevented)};
  };
  const article = '#doc .blk[data-block="' + target + '"]';

  // W2
  for (const [label, selector] of [['article', article], ['article body', article + ' .blk-body']]) {
    const opened = await rightClick(selector);
    ok(opened.prevented === true && opened.count === 1, 'W2 ' + label + ': one passage menu replaces the browser menu');
    ok(['Edit this passage', 'Edit exact source', 'Open in TeX', 'Discuss this passage', 'Queue a request…'].every(name => opened.items.includes(name)),
      'W2 ' + label + ': the eligible passage actions are present (' + opened.items.length + ' items)');
    ok(opened.focused === opened.items[0], 'W2 ' + label + ': focus is on the first enabled item');
    ok(opened.diagnostic.disposition === 'actions' && opened.diagnostic.block === target && opened.diagnostic.matches === 1 && opened.diagnostic.connected,
      'W2 ' + label + ': the diagnostic names the exact block, one match, connected');
    await page.keyboard.press('Escape');
    ok((await menu()).count === 0, 'W2 ' + label + ': Escape closes the menu');
  }

  // W3
  // a real unsaved draft in another passage, which the reload must keep (parked) and never save
  const writes = [];
  page.on('request', request => {if (request.method() === 'POST') writes.push(request.url());});
  const draftBlock = boot.model[0];
  await page.click('#doc .blk[data-block="' + draftBlock + '"] .blk-body');
  await page.keyboard.press('End');
  await page.keyboard.type(' unsaved words');
  const drafts = () => page.evaluate(() => {const state = window.walk.editState(); return {dirty: state.dirty, parked: state.parked, ids: state.parkedIds};});
  const before = await drafts();
  ok(before.dirty === true || before.parked === 1, 'W3 setup: an unsaved draft stands in ' + draftBlock);
  await page.evaluate(selector => {document.querySelector(selector).dataset.block = 'chapters/chapter-01.tex#not-in-model';}, article);
  const stale = await rightClick('#doc .blk[data-block="chapters/chapter-01.tex#not-in-model"]');
  ok(stale.prevented === true && stale.disposition === 'unavailable' && stale.children > 0, 'W3 an unmatched passage gets the bounded unavailable disposition, never an empty menu');
  ok(JSON.stringify(stale.items) === JSON.stringify(['Reload the manuscript view']), 'W3 its only action reloads the view (no guessed target)');
  ok(stale.diagnostic.matches === 0 && stale.diagnostic.items === 0 && stale.diagnostic.ready === true, 'W3 the diagnostic records no match, no item, ready');
  ok(stale.focused === 'Reload the manuscript view', 'W3 focus is on the reload item');
  await page.click('#manuscript-context-menu [role=menuitem]');
  await page.waitForFunction(selector => !!document.querySelector(selector), article, {timeout: 20000});
  const after = await page.evaluate(() => ({model: window.walk.blocks({text: false}).map(row => row.id),
    dom: [...document.querySelectorAll('#doc .blk[data-block]')].map(node => node.dataset.block)}));
  const kept = await drafts();
  ok(JSON.stringify(after.model) === JSON.stringify(after.dom) && after.dom.includes(target), 'W3 reload restores model/DOM id agreement');
  ok((kept.dirty || kept.parked === 1) && writes.length === 0, 'W3 reload keeps the unsaved draft and writes nothing (' + JSON.stringify(kept) + ')');
  const again = await rightClick(article);
  ok(again.disposition === null && again.items.includes('Edit this passage'), 'W3 the same article has its actions again after the reload');
  await page.keyboard.press('Escape');

  // W4
  const background = await rightClick('#bar');
  ok(background.prevented === false && background.count === 0, 'W4 a background without actions keeps the browser menu (no popup)');
  ok(background.diagnostic.disposition === 'browser-menu' && background.diagnostic.block === null, 'W4 the diagnostic records browser-menu with no block');

  // W5
  await page.evaluate(() => {const real = window.walk; window.__real = real; window.walk = {...real, ready: () => false, blocks: () => [], contextualInsertionPoint: () => null};});
  const loading = await rightClick(article);
  await page.evaluate(() => {window.walk = window.__real;});
  ok(loading.disposition === 'loading' && JSON.stringify(loading.items) === JSON.stringify(['Close']), 'W5 a block before the model is ready gets loading with Close only');
  await page.keyboard.press('Escape');

  // W6
  const diagnostic = (await rightClick(article)).diagnostic;
  await page.keyboard.press('Escape');
  const raw = await page.evaluate(() => document.documentElement.dataset.passageMenu);
  ok(JSON.stringify(Object.keys(diagnostic).sort()) === JSON.stringify(DIAGNOSTIC_KEYS), 'W6 the diagnostic carries only its bounded keys');
  ok(raw.length < 400 && !raw.includes('text') && diagnostic.rows === after.model.length, 'W6 the diagnostic is small, holds no text and counts the model rows');
  for (let index = 0; index < 20; index++) {await page.click(article, {button: 'right'}); await page.keyboard.press('Escape');}
  ok((await menu()).count === 0 && errors.length === 0, 'W6 twenty openings leave no menu behind and raise no error');
  await page.close();
} finally {
  await owners.close();
}
console.log('\n' + passed + ' assertions passed');
