// THE TASK CUE RUNNER (M5 C10; the former interactive guide). Purpose: run one declared journey
// over the actual workspace as a compact cue beside the control each step points at. Every step
// names a real control and is marked done only when the real state it describes is observed
// (root.dataset.view, the Work chip, the return button, an open history entry, the conversation
// inspector, the template inspector dialog). The cue never clicks for the person, never fakes a
// state and never starts a write, a model or a run; stopping it leaves everything as it is.
//
// THE STEPS ARE THE HELP OWNER'S (G8). A journey is declared once in writing_declarations.py
// (JOURNEY_DECLARATIONS) and served by `/authoring/help?view=areas` and the native
// `help {concept: journeys}`; `journeySteps` turns a declared journey into runnable steps, and
// `stepDone` evaluates its closed predicate language (`equals`, `not_equals`, `truthy`, `all`)
// over the facts `observeWorkspace` reports. There is no local step copy.
//
// Observation discipline (root-ui/m5-fable-ux-findings.json): the cue is mounted OUTSIDE the
// observed subtree, mutations inside the cue are ignored, a paint happens only when the
// observation signature changes, and the control buttons are created once and updated in place
// so a click target stays the same node. No polling.
//
// Anchoring (plan §7/§8 help cue): the cue sits beside the step's first visible control
// ([data-control="<id>"]), to its right when there is room, else below; it never covers the
// target, which is highlighted (class is-help-target) and stays operable; a control inside the
// conversation pane anchors the cue inside that pane; without layout (tests) the stylesheet's
// fixed corner stands. Back / Next (Skip when the step is not yet seen) / Stop; Esc stops.
// C12 (2026-10-15): placement is measured again whenever the page changes (a mutation burst, resize, scroll),
// not only when a step changes; the cue keeps clear of the step control AND of the declared controls visible
// inside it (Document setup's Template & layout), and when nothing fits beside them it takes the largest free
// band of the viewport, height-capped with its own scroll. The resize/scroll listeners leave with the cue.
//
// RUNS AND OUTCOMES (C12): each mount is one run of one declaration (journey id + help version). A step is SEEN
// in this run when its predicate is observed true while it is the current step; seen is kept per run and bounded
// by the declared step ids, so a step whose state passes (a modal inspector that closes again) can still be
// finished. A closed run's seen steps are never carried into a new run; an unclosed run of the same declaration
// resumes with its seen steps (a reload). Finish records outcome "finished" only when the last step was seen in
// this run; Stop and Escape record "stopped", Skip on the last step "skipped": neither is ever Finished.
//
// Storage: the person's progress in `laplace:learning:<project>` through workspace-journeys
// (learningStore); the retired `laplace:guide:<project>` is migrated there once and removed.
// An entry is {step, closed, outcome?, run?: {id, version, seen: [step ids]}}; unknown fields are kept.
// Controls: help:cue.
import {stateChip} from './workspace-presentation.mjs';
import {learningStore} from './workspace-journeys.mjs';
const el = (tag, text = '', cls = '') => {const node = document.createElement(tag); node.textContent = text; node.className = cls; return node;};
const visible = node => !!node && node.hidden !== true;

// Pure observation of the shell; no state of its own. The fact names are the help owner's
// OBSERVATION_FACTS; a declared step may name no other.
export function observeWorkspace(root, page = document) {
  const q = selector => root.querySelector?.(selector) || null;
  const details = [...(root.querySelectorAll?.('.history-detail') || [])];
  return {
    view: root.dataset?.view || '',
    researchFocus: q('[data-geometry-focus-kind]')?.dataset?.geometryFocusKind||'',
    researchRepresentation:q('[data-geometry-representation]')?.dataset?.geometryRepresentation||'',
    researchFocal:q('[data-geometry-focal]')?.dataset?.geometryFocal==='true',
    researchReading:q('[data-geometry-representation]')?.dataset?.geometryRepresentation==='focus'&&!!q('[data-rw-observed-reading=true]'),
    researchInputs:Number(q('[data-rw-input-count]')?.dataset?.rwInputCount||0),
    reviewPanel:[...(page.body?.querySelectorAll?.('dialog[open][data-guide-panel]')||[])].at(-1)?.dataset?.guidePanel||'',
    outline: visible(q('[data-manuscript-outline]')),
    returnVisible: visible(q('[data-return-reader]')),
    historyOpen: details.some(node => node.hidden !== true),
    workSelected: visible(q('[data-work-scope]')),
    sessionOpen: visible(q('[data-session]')),
    inspectorOpen: visible(q('[data-inspector]')),
    // a REAL live template inspector: the dialog is in the page, open, and adopted by the shared inspector
    templateOpen: [...(page.body?.querySelectorAll?.('.document-template-dialog') || [])].some(node =>
      node.isConnected !== false && node.open === true && node.dataset?.inspector === 'template-setup')
  };
}
// The declared predicate language, evaluated over one observation. Unknown shapes are false,
// never true: a malformed declaration cannot mark a step done.
export function stepDone(predicate, observation) {
  if (!predicate || typeof predicate !== 'object') return false;
  if (Array.isArray(predicate.all)) return predicate.all.length > 0 && predicate.all.every(item => stepDone(item, observation));
  if (typeof predicate.fact !== 'string' || !(predicate.fact in observation)) return false;
  const value = observation[predicate.fact];
  if ('equals' in predicate) return value === predicate.equals;
  if ('not_equals' in predicate) return value !== predicate.not_equals;
  if ('truthy' in predicate) return !!value === !!predicate.truthy;
  return false;
}
// The overview (areas) names how many controls the help owner declares and the one read that returns them
// (areas.controls = {known, read}); the control ids a journey step may name come from THAT read, taken when a
// journey starts: the same help version as the overview, or it is refused.
export async function readJourneyControls(areas, request) {
  const read = areas?.controls?.read?.http;
  if (!read || read.method !== 'GET' || typeof read.route !== 'string') throw Error('The help owner offers no controls read.');
  const value = (await request(read.route + '?' + new URLSearchParams(read.query || {})))?.help;
  if (!value || value.version !== areas.version || !Array.isArray(value.controls)) throw Error('The help owner\u2019s controls read is of another help version than its overview.');
  if (value.controls.length !== areas.controls.known) throw Error('The help owner\u2019s controls read does not hold the ' + areas.controls.known + ' controls its overview counts.');
  return value;
}
// Runnable steps from the help owner's declared journey; `controlsRead` is what readJourneyControls returned.
export function journeySteps(areas, journeyId, controlsRead) {
  if (areas?.schema_version !== 'laplace.help-areas/1' || !Array.isArray(areas.journeys)) throw Error('The help owner returned no journey declarations.');
  const journey = areas.journeys.find(row => row.id === journeyId);
  if (!journey || !Array.isArray(journey.steps) || !journey.steps.length) throw Error('The help owner declares no journey named ' + journeyId + '.');
  if (!controlsRead || controlsRead.version !== areas.version || !Array.isArray(controlsRead.controls)) throw Error('Journey steps need the help owner\u2019s controls read of the overview\u2019s version.');
  const controls = new Set(controlsRead.controls.map(row => row.id));
  return journey.steps.map(step => {
    if (!controls.has(step.control)) throw Error('Journey step ' + step.id + ' names an undeclared control.');
    return Object.freeze({id: step.id, title: step.title, say: step.say, control: step.control, done: observation => stepDone(step.done, observation)});
  });
}
export function guideProgress(steps, observation) {
  return steps.map(step => {try {return !!step.done(observation);} catch {return false;}});
}
// A mutation record is the guide's own when its target sits inside the panel.
export function ownMutation(record, panel) {
  for (let node = record?.target; node; node = node.parentElement || node.parentNode) if (node === panel) return true;
  return false;
}
// The first visible control for a step, by its declared id (a dynamic instance carries the same family id).
export function stepTarget(root, control, page = document) {
  const candidates = [...(root.querySelectorAll?.('[data-control="' + control + '"]') || []), ...(page.body?.querySelectorAll?.('[data-control="' + control + '"]') || [])];
  return candidates.find(node => visible(node)) || candidates[0] || null;
}
// Where the cue goes, in viewport coordinates: beside the anchor when that fits and covers none of the
// rectangles to keep clear (the anchor and the requested controls inside the step control); otherwise slid to a
// viewport edge beside or below/above it; otherwise into the largest free vertical band at one of three columns,
// height-capped (maxHeight) so it scrolls inside itself; otherwise compact or withheld (below). Returns
// {left, top}, {left, top, maxHeight}, {left, top, maxHeight, compact: true} or {withheld: true}; null without
// layout. No returned box covers a kept rectangle.
const intersects = (box, rect) => box.left < rect.right && box.left + box.w > rect.left && box.top < rect.bottom && box.top + box.h > rect.top;
export function cuePlacement(targetRect, cueSize, viewport, keepClear = targetRect ? [targetRect] : []) {
  if (!targetRect || !viewport) return null;
  const gap = 12, m = 8, {w, h} = cueSize;
  const clampX = x => Math.max(m, Math.min(x, viewport.w - w - m)), clampY = y => Math.max(m, Math.min(y, viewport.h - h - m));
  const fits = box => box.left >= m && box.top >= m && box.left + w <= viewport.w - m && box.top + h <= viewport.h - m;
  const clear = box => keepClear.every(rect => !intersects({...box, w, h}, rect));
  const t = targetRect, right = t.right + gap, below = t.bottom + gap, left = t.left - gap - w, above = t.top - gap - h;
  const candidates = [{left: right, top: clampY(t.top)}, {left: clampX(t.left), top: below}, {left, top: clampY(t.top)}, {left: clampX(t.left), top: above},
    {left: right, top: m}, {left: right, top: viewport.h - h - m}, {left: m, top: below}, {left: viewport.w - w - m, top: below},
    {left, top: m}, {left, top: viewport.h - h - m}, {left: m, top: above}, {left: viewport.w - w - m, top: above}];
  for (const box of candidates) if (fits(box) && clear(box)) return {left: box.left, top: box.top};
  // no full-height fit: the largest free vertical band in one of three columns
  let best = null;
  for (const x of [clampX(t.left), m, Math.max(m, viewport.w - w - m)]) {
    const blocks = keepClear.filter(rect => x < rect.right && x + w > rect.left).map(rect => [rect.top, rect.bottom]).sort((a, b) => a[0] - b[0]);
    let start = m;
    for (const [top, bottom] of [...blocks, [viewport.h - m, viewport.h - m]]) {
      const end = Math.min(top - gap, viewport.h - m);
      if (end - start > 0 && (!best || end - start > best.maxHeight)) best = {left: x, top: start, maxHeight: Math.floor(end - start)};
      start = Math.max(start, bottom + gap);
    }
  }
  // THE NO-FIT DISPOSITIONS (C12 residual R5): a band of at least BAND_MIN px takes the full cue, height-capped with
  // its own scroll; a band of at least COMPACT_HEIGHT px takes the COMPACT cue (one line: progress, title and its
  // controls); with no free band at all the cue is WITHHELD (not shown) until the layout changes, Escape still
  // stops it. No disposition ever returns a box that covers a kept control, and none clicks or acts for the person.
  if (best && best.maxHeight >= BAND_MIN) return best;
  if (best && best.maxHeight >= COMPACT_HEIGHT) return {left: best.left, top: best.top, maxHeight: COMPACT_HEIGHT, compact: true};
  return {withheld: true};
}
export const BAND_MIN = 96, COMPACT_HEIGHT = 44;
// The rectangles a step keeps reachable: the anchor (an open disclosure's summary, else the control) and the
// declared controls visible inside the step control, at most 12.
export function stepRects(target) {
  if (!target?.getBoundingClientRect) return {anchor: null, keep: []};
  const summary = target.tagName === 'DETAILS' && target.open ? target.querySelector?.('summary') : null;
  const anchor = (summary || target).getBoundingClientRect();
  const inner = [...(target.querySelectorAll?.('[data-control]') || [])].filter(node => visible(node) && node.getBoundingClientRect).slice(0, 12)
    .map(node => node.getBoundingClientRect()).filter(rect => rect.width > 0 && rect.height > 0);
  return {anchor, keep: [anchor, ...inner]};
}
// THE CONVERSATION PANE'S REQUIRED CONTROLS (M5 D, Root actual at 720x800: the in-pane cue, 144 x 431 px,
// covered Send). A cue anchored in the pane keeps these clear as well as its step's own rectangles: the
// message, Send, Stop, the composer's target, Expand and the inspector's Close.
export const PANE_REQUIRED = '[data-message],[data-send],[data-stop],[data-composer-target],[data-compose-expand],[data-inspector-close]';
export function paneRequiredRects(pane) {
  return [...(pane?.querySelectorAll?.(PANE_REQUIRED) || [])].filter(node => visible(node) && node.getBoundingClientRect)
    .map(node => node.getBoundingClientRect()).filter(rect => rect.width > 0 && rect.height > 0);
}
// The run's seen steps: only declared step ids, in declared order, without repeats.
export function seenSteps(steps, ids) {
  const wanted = new Set(Array.isArray(ids) ? ids : []);
  return steps.map(step => step.id).filter(id => wanted.has(id));
}

export function mountGuide(root, {project, steps, journeyId = 'welcome', version = '', storage = globalThis.sessionStorage, store = null, page = document, onClose = () => {}} = {}) {
  if (!Array.isArray(steps) || !steps.length) throw Error('The guide needs the help owner\'s journey steps; read /authoring/help?view=areas first.');
  const learning = store || learningStore(project, storage);
  const saved = learning.journey(journeyId) || {};
  let index = Math.min(Math.max(0, Number(saved.step) || 0), steps.length - 1), alive = true, frame = 0, signature = '', paints = 0, target = null, placements = 0;
  // the run: an unclosed run of this same declaration resumes (its seen steps included); anything else is new
  const resumed = !saved.closed && saved.run && typeof saved.run === 'object' && saved.run.version === version && typeof saved.run.id === 'string';
  const run = {id: resumed ? saved.run.id : 'run-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8), version,
               seen: resumed ? seenSteps(steps, saved.run.seen) : []};
  const panel = el('aside', '', 'workspace-guide'); panel.setAttribute('aria-label', 'Task cue'); panel.setAttribute('role', 'complementary'); panel.dataset.control='help:cue'; panel.dataset.journey = journeyId;
  const head = el('div', '', 'workspace-guide-head'), progress = el('span', '', 'workspace-guide-progress'), close = el('button', 'Stop', 'act workspace-guide-close'); close.type = 'button'; close.setAttribute('aria-label', 'Stop this task');
  head.append(progress, close);
  const title = el('h3', '', 'workspace-guide-title'), say = el('p', '', 'workspace-guide-say'), state = el('div', '', 'workspace-guide-state'), controls = el('div', '', 'workspace-guide-controls action-row');
  // Stable controls: created once, updated in place.
  const back = el('button', 'Back', 'act workspace-guide-back'), next = el('button', 'Next', 'act workspace-guide-next');
  back.type = next.type = 'button'; controls.append(back, next);
  panel.append(head, title, say, state, controls);
  // a write of this run: open, without a previous run's outcome (an undefined field is not stored), unless finish passes one
  const remember = patch => learning.update(journeyId, {step: index, closed: false, outcome: undefined, run: {id: run.id, version: run.version, seen: [...run.seen]}, ...patch});
  const seen = i => run.seen.includes(steps[i].id);
  function anchor(step) {
    const found = stepTarget(root, step.control, page);
    if (target && target !== found) target.classList?.remove('is-help-target');
    target = found; target?.classList?.add('is-help-target');
    // a control inside the conversation pane anchors the cue inside that pane
    const pane = target?.closest?.('[data-session]') || null, home = pane || page.body || root;
    if (panel.parentNode !== home) home.append(panel);
    panel.classList.toggle('is-in-pane', !!pane);
    if (target) {const id = target.id || (target.id = 'help-target-' + journeyId + '-' + step.id); panel.setAttribute('aria-describedby', id);}
    place();
  }
  // Measure again and move only when the position changes (no repaint, no content change).
  let placed = '', fullSize = {w: 360, h: 160};
  function place() {
    if (!alive) return;
    // a cue in the conversation pane is placed like any other (viewport coordinates, the same no-fit
    // dispositions), and also keeps the pane's required controls clear
    const pane = panel.classList.contains('is-in-pane') ? panel.parentNode : null, {anchor: rect, keep} = stepRects(target);
    // always placed by its FULL size, measured as anchored (its own width, not a narrow pane's), so a
    // compact or withheld cue cannot flap back and forth
    if (!panel.classList.contains('is-compact') && !panel.hidden) {
      const anchored = panel.classList.contains('is-anchored'), pinned = panel.style.width, capped = panel.style.maxHeight;
      if (!anchored) panel.classList.add('is-anchored');panel.style.width = '';panel.style.maxHeight = '';
      fullSize = {w: panel.offsetWidth || 360, h: panel.scrollHeight || panel.offsetHeight || 160};
      if (!anchored) panel.classList.remove('is-anchored');panel.style.width = pinned;panel.style.maxHeight = capped;
    }
    const kept = pane ? [...keep, ...paneRequiredRects(pane)] : keep;
    const where = rect && typeof globalThis.innerWidth === 'number' ? cuePlacement(rect, fullSize, {w: globalThis.innerWidth, h: globalThis.innerHeight}, kept) : null;
    const key = where ? (where.withheld ? 'withheld' : [where.left, where.top, where.maxHeight || '', where.compact ? 'c' : ''].join(',')) : '';
    if (key === placed) return;
    placed = key; placements++;
    panel.hidden = !!where?.withheld; panel.classList.toggle('is-compact', !!where?.compact); panel.setAttribute('data-disposition', where?.withheld ? 'withheld' : where?.compact ? 'compact' : where?.maxHeight ? 'band' : where ? 'beside' : 'corner');
    // the placed box is the measured box: a capped cue's own scrollbar comes out of its content, never widens it
    if (where && !where.withheld) {panel.classList.add('is-anchored'); panel.style.left = where.left + 'px'; panel.style.top = where.top + 'px'; panel.style.width = where.compact ? '' : fullSize.w + 'px'; panel.style.maxHeight = where.maxHeight ? where.maxHeight + 'px' : ''; panel.style.overflowY = where.maxHeight ? 'auto' : '';}
    else {panel.classList.remove('is-anchored'); panel.style.left = ''; panel.style.top = ''; panel.style.width = ''; panel.style.maxHeight = ''; panel.style.overflowY = '';}
  }
  function paint(force = false) {
    if (!alive) return false;
    const observation = observeWorkspace(root, page), done = guideProgress(steps, observation), step = steps[index];
    // the current step observed true in this run is seen (bounded by the declared ids); written once
    if (done[index] && !seen(index)) {run.seen = seenSteps(steps, [...run.seen, step.id]); remember();}
    const ready = done[index] || seen(index);
    const next_signature = JSON.stringify([index, done, run.seen]);
    if (!force && next_signature === signature) {place(); return false;}
    signature = next_signature; paints++;
    progress.textContent = 'Step ' + (index + 1) + ' of ' + steps.length;
    title.textContent = step.title; say.textContent = step.say;
    state.replaceChildren(stateChip(done[index] ? {label: 'Done · seen in the app', tone: 'ok'} : seen(index) ? {label: 'Seen earlier in this task', tone: 'ok'} : {label: 'Waiting for you', tone: 'attention'}));
    back.disabled = index === 0;
    next.textContent = ready ? (index >= steps.length - 1 ? 'Finish' : 'Next') : 'Skip';
    next.className = 'act workspace-guide-next' + (ready ? ' primary' : '');
    panel.setAttribute('data-step', step.id); panel.setAttribute('data-done', String(done[index])); panel.setAttribute('data-seen', String(seen(index)));
    if (step.control) panel.setAttribute('data-control-target', step.control);
    anchor(step);
    return true;
  }
  back.onclick = () => {index = Math.max(0, index - 1); remember(); paint(true);};
  next.onclick = () => {if (index >= steps.length - 1) {finish(seen(index) ? 'finished' : 'skipped'); return;} index += 1; remember(); paint(true);};
  let pending = false;
  function schedule() {
    // One frame per burst of meaningful mutations; the flag, not the frame handle, gates it.
    if (!alive || pending) return;
    pending = true;
    const run = () => {pending = false; frame = 0; paint();};
    if (typeof requestAnimationFrame === 'function') frame = requestAnimationFrame(run); else run();
  }
  const onMutations = records => {if (!alive) return; if (records.some(record => !ownMutation(record, panel))) schedule();};
  const observer = typeof MutationObserver === 'function' ? new MutationObserver(onMutations) : null;
  observer?.observe(root, {attributes: true, childList: true, subtree: true, attributeFilter: ['hidden', 'data-view', 'open', 'aria-current', 'data-geometry-focus-kind', 'data-geometry-representation', 'data-geometry-focal', 'data-rw-observed-reading', 'data-rw-input-count']});
  const bodyObserver = typeof MutationObserver === 'function' && page.body ? new MutationObserver(onMutations) : null;
  bodyObserver?.observe(page.body, {childList: true});
  globalThis.addEventListener?.('laplace-workspace-navigation', schedule);
  // layout only: one frame per burst of resize/scroll moves the cue; nothing repaints
  let layoutPending = false, layoutFrame = 0;
  const onLayout = () => {if (!alive || layoutPending) return; layoutPending = true;
    const run_ = () => {layoutPending = false; layoutFrame = 0; place();};
    if (typeof requestAnimationFrame === 'function') layoutFrame = requestAnimationFrame(run_); else run_();};
  globalThis.addEventListener?.('resize', onLayout); globalThis.addEventListener?.('scroll', onLayout, {capture: true, passive: true});
  const onKey = event => {if (event.key === 'Escape' && alive) {event.preventDefault?.(); finish('stopped');}};
  page.addEventListener?.('keydown', onKey);
  // RELEASE (C12 residual R4): everything this cue owns (observers, frames, its four listeners, the target
  // highlight, its DOM) goes; nothing is written. finish() is release plus the person's outcome; dispose() is
  // release alone, used when the workspace itself is torn down: the run stays open and resumes on the next
  // mount (its step and seen steps as last recorded), so a teardown never reads as Finished or Stopped.
  function release() {
    if (!alive) return false; alive = false; observer?.disconnect(); bodyObserver?.disconnect();
    if (frame && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(frame);
    if (layoutFrame && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(layoutFrame);
    globalThis.removeEventListener?.('laplace-workspace-navigation', schedule); page.removeEventListener?.('keydown', onKey);
    globalThis.removeEventListener?.('resize', onLayout); globalThis.removeEventListener?.('scroll', onLayout, {capture: true});
    target?.classList?.remove('is-help-target'); panel.remove();
    return true;
  }
  function finish(outcome = 'stopped') {
    if (!release()) return;
    remember({closed: true, outcome: outcome === 'finished' && seen(steps.length - 1) && index === steps.length - 1 ? 'finished' : outcome === 'skipped' ? 'skipped' : 'stopped'}); onClose();
  }
  close.onclick = () => finish('stopped');
  // Mounted on the page body (or inside the conversation pane), outside the observed workspace root.
  (page.body || root).append(panel); paint(true);
  return {get index() {return index;}, get paints() {return paints;}, get placements() {return placements;}, get run() {return {id: run.id, version: run.version, seen: [...run.seen]};}, get target() {return target;}, paint, place, observe: onMutations, close: () => finish('stopped'), dispose: () => {release();}, get alive() {return alive;}, get element() {return panel;}, get next() {return next;}};
}
