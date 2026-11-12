// manuscript-editor.mjs — THE EDITOR BAND and the TeX pane of the Manuscript view (M5 C7).
// Purpose: one band (Write | TeX | PDF, document chips, Save changes, Build, Build details,
//   Undo/Redo, Drafts, Document setup) over the walk iframe, plus the TeX source pane.
// Ownership: document state belongs to /authoring/document (chips, Save, Build); the reading
//   place, visual edits and edit history belong to the walk (reached only through walk()); TeX
//   drafts belong here; proposal drafts belong to the shared laplace:proposal-draft:* keys.
// Public contract: createManuscriptEditor(host,{project,frame,storage,request,sourceClient,
//   mountSourceEditor,onOpenArtifact,...}) -> {observe, openSource, showWrite, save, build,
//   readPdf, history, capture, attention, hasDraft, destroy, ...}; sourceDraftAttachment,
//   sourceComparisonPlan, sourceDraftBelongs, hasStoredSourceDraft, writeSourceLocation,
//   templateDraftSnapshot (pure).
// Inputs/outputs/currentness: observe() reads /authoring/document (one read per explicit
//   observation; idle refresh is manuscript-editing.createManuscriptRefresh's conditional build
//   summary, G17); the Document setup panel renders from that one response (object header,
//   files as relation rows, Template & layout primary when offered, Exact build basis).
// Errors/recovery: a failed build keeps the selected file and position; Build details opens the
//   owner's reason and log tail; a changed saved source shows "Earlier source version".
// Producers/consumers: workspace.mjs mounts it; document-template.mjs opens from Document setup;
//   derived-output.mountBuildCancellation follows a running build.
// Storage: sessionStorage laplace:source-drafts:<project> (TeX drafts with their observed
//   digest; pruned when clean). No other key.
// Retired (C7): the Document setup prose list; Undo/Redo as passage-menu items (they are band
//   actions here and keys in the walk).
// Tradeoffs: the band holds no document truth of its own; it repaints from the last observation.
import {
  mountExactSourceEditor
} from './exact-source-editor.mjs';
import {sourceEffectFromError,sourceEffectDisposition} from './source-effect.mjs';
import {mountBuildCancellation,sameBuildJob} from './derived-output.mjs';
import {openDocumentTemplate} from './document-template.mjs';
import {blockSourceLocation} from './manuscript-editing.mjs';
import {chipRow,documentChips,presentationStyles,objectHeader,relationList,declareControl} from './workspace-presentation.mjs';
import {
  readManuscriptSource,
  saveManuscriptSource,
  acknowledgeDraft,
  sourceDraftDirty,
  validateSourceRead
} from './manuscript-source-client.mjs';
import {
  openPdf
} from './writing-pdf.mjs';
import {
  manuscriptPdfState,
  documentPdfURL,
  documentPdfNotice
} from './manuscript-document-view.mjs';
import {pendingRead} from './pending-read.mjs';
// wave 13 id sweep: control ids by tag and label (begin)
// wave 13 id sweep: control ids (end)
export {
  manuscriptPdfState
} from './manuscript-document-view.mjs';
const el = (tag, text = '', cls = '') => {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = cls;
  return node;
};
// THE SETUP POPOVERS (M5 D, Root actual C10/C11 at 720x800: a 520px panel opened rightwards from a
// right-aligned summary and clipped Template & layout at x 849..977). One placement owns both
// popovers (Document setup, Retained drafts): the summary sits at the right end of its toolbar line;
// the panel is as wide as the preferred width allows inside its bound (the nearest scrolling
// ancestor's visible box, within the viewport) less the gutters, right-aligned to the summary and
// shifted only as far as needed to stay inside that bound; its height is what remains below the
// summary, never less than a usable floor (then the bound scrolls). Values are pixels; the returned
// left is relative to the details element (the panel's containing block).
export const SETUP_PANEL = {preferred: 520, gutter: 8, minHeight: 200, maxViewportShare: 0.65};
export function setupPanelPlacement({anchorLeft, anchorRight, anchorBottom = 0, boundLeft = 0, boundRight, viewportHeight = Infinity,
  preferred = SETUP_PANEL.preferred, gutter = SETUP_PANEL.gutter}) {
  const width = Math.max(0, Math.min(preferred, boundRight - boundLeft - 2 * gutter));
  const left = Math.max(boundLeft + gutter, Math.min(anchorRight - width, boundRight - gutter - width));
  const room = viewportHeight - anchorBottom - gutter;
  const maxHeight = Math.max(SETUP_PANEL.minHeight, Math.min(room, viewportHeight * SETUP_PANEL.maxViewportShare));
  return {width, left: left - anchorLeft, maxHeight};
}
function popoverBound(details) {
  const viewportWidth = document.documentElement?.clientWidth || window.innerWidth;
  for (let node = details.parentElement; node && node !== document.body; node = node.parentElement) {
    if (getComputedStyle(node).overflowX === 'visible') continue;
    const box = node.getBoundingClientRect();
    return {boundLeft: Math.max(0, box.left + node.clientLeft), boundRight: Math.min(viewportWidth, box.left + node.clientLeft + node.clientWidth)};
  }
  return {boundLeft: 0, boundRight: viewportWidth};
}
function placePopover(details, panel) {
  if (!details.open || !details.getBoundingClientRect || !panel?.style) return;
  const rect = details.getBoundingClientRect();
  const {width, left, maxHeight} = setupPanelPlacement({anchorLeft: rect.left, anchorRight: rect.right, anchorBottom: rect.bottom,
    viewportHeight: window.innerHeight, ...popoverBound(details)});
  panel.style.width = width + 'px';panel.style.left = left + 'px';panel.style.right = 'auto';panel.style.maxHeight = maxHeight + 'px';
}
export function sourceDraftAttachment(draft) {
  if (!sourceDraftDirty(draft)) return null;
  if (draft.content.length > 64000) throw Error('This TeX draft exceeds the conversation limit. Save it first or copy a smaller passage into your message; the draft remains intact.');
  return {
    status: 'UNSAVED',
    format: 'tex',
    text: draft.content,
    anchor: {
      file: draft.file,
      line_start: 1,
      line_end: draft.base.split('\n').length
    },
    reason: 'Unsaved local TeX draft. Its anchor is the original inspected file, not saved coordinates for the new text. It has not been applied.'
  };
}
export function sourceComparisonPlan(draft, observed, admitted) {
  if (!observed) return {
    columns: [['When opened', draft.base], ['Your draft', draft.content]],
    notice: 'Current source is unavailable; the retained basis and draft remain inspectable.'
  };
  const sameSelection = observed.selection_identity === draft.observed.selection_identity;
  const changedBasis = observed.expected_source_digest !== draft.observed.expected_source_digest;
  if (observed.content === draft.content) return {
    columns: [],
    notice: sourceDraftDirty(draft) ? 'Your draft matches the current saved source.' : 'No source changes.',
    useSavedVersion: admitted && sameSelection && changedBasis && sourceDraftDirty(draft)
  };
  if (!changedBasis && sameSelection) return {
    columns: [['Saved', observed.content], ['Your changes', draft.content]]
  };
  const changedContent = observed.content !== draft.base;
  return {
    columns: changedContent
      ? [['When opened', draft.base], ['Saved now', observed.content], ['Your draft', draft.content]]
      : [['Saved', observed.content], ['Your draft', draft.content]],
    notice: sameSelection ? 'Saved source changed since this draft was opened.' : 'This draft belongs to an earlier document selection.',
    canUseBasis: admitted && sameSelection && changedContent
  };
}
export function sourceDraftBelongs(draft, document) {
  return !!draft && draft.observed?.selection_identity === document?.selection_identity && (document?.files || []).some(row => row.file === draft.file && !row.read_only);
}
export function hasStoredSourceDraft(project, document, storage = globalThis.sessionStorage) {
  try {
    return JSON.parse(storage.getItem('laplace:source-drafts:' + project) || '[]').some(draft => sourceDraftDirty(draft) && sourceDraftBelongs(draft,
    document));
  } catch {
    throw Error('Stored source drafts could not be inspected. Open the editor before building.');
  }
}
// Write and TeX share the currently observed physical source location. A
// rendered block identity is not a filename; use the owner's repository path.
export function writeSourceLocation(walk) {
  return blockSourceLocation(walk,walk?.readingPosition?.()?.blockId);
}
const draftRevision=draft=>draft.revision||= 'DRAFT-'+globalThis.crypto.randomUUID();
function setDraftText(draft,text){if(draft.content!==text){draft.content=text;draft.revision='DRAFT-'+globalThis.crypto.randomUUID();}}
export async function templateDraftSnapshot(draft,documentState){
  if(!sourceDraftBelongs(draft,documentState)||draft.observed?.read_only||draft.effectHold)throw Error('Open an editable TeX draft in the selected manuscript before previewing it. Its original basis stays retained.');
  validateSourceRead(draft.observed);
  const snapshot={file:draft.file,content:draft.content,revision:draftRevision(draft),expected_source_digest:draft.observed.expected_source_digest,
    selection_identity:draft.observed.selection_identity,position:structuredClone(draft.position||{})};
  const bytes=new TextEncoder().encode(snapshot.content),hash=new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256',bytes));
  snapshot.input_content_sha256='sha256:'+Array.from(hash,byte=>byte.toString(16).padStart(2,'0')).join('');
  return Object.freeze(snapshot);
}

const draftKey = draft => JSON.stringify([draft.file, draft.observed?.selection_identity || 'legacy']);
export function createManuscriptEditor(host, {
  project,
  frame,
  request,
  onChanged = () => {},
  onAttention = () => {},
  onHistory = () => {},
  onOpenArtifact,
  status = () => {},
  mountSourceEditor = mountExactSourceEditor,
  sourceClient = {
    read: readManuscriptSource,
    save: saveManuscriptSource
  },
  storage = globalThis.sessionStorage
}) {
  const drafts = new Map(),
  key = 'laplace:source-drafts:' + project;
  let documentState = null,
  mode = 'write',
  current = null,
  adapter = null,
  adapterPromise = null,
  loadGeneration = 0,
  observationGeneration = 0,
  templateOpening = false,
  templateButton = null,
  saving = false,
  savePromise = null,
  poll = null,
  persistTimer = null,
  alive = true,
  position = null,
  readError = '', persistentError = '';
  // the Template & layout note: one node, carried to the current button by every setup repaint
  const templateNote = el('span', '', 'template-layout-note');templateNote.setAttribute('role', 'status');
  const walk = () => frame.contentWindow?.walk;
  // THE SAVE LINE beside the document chips (NODE.w3 ruling 3): the walk's own state for Write
  // edits (walk.mjs saveLine); an unsaved TeX draft is Unsaved changes
  const saveLine = () => sourceDirty() ? true : (walk()?.editState?.()?.save ?? visualDirty());
  const visualDirty = () => {
    const state = walk()?.editState?.();
    return !!(state && (state.dirty || state.parked || state.committing || state.proposal_dirty));
  };
  const belongs = draft => sourceDraftBelongs(draft, documentState);
  const allDirty = () => [...drafts.values()].filter(sourceDraftDirty);
  const sourceDirty = () => allDirty().some(belongs);
  const hasAnyDraft = (document = documentState) => {
    const observed = walk()?.sourceObservation?.()?.source_observation?.selection_identity;
    return allDirty().some(draft => sourceDraftBelongs(draft, document)) || (visualDirty() && (!observed || observed === document?.selection_identity));
  };
  try {
    for (const draft of JSON.parse(storage.getItem(key) || '[]')) if (typeof draft.file === 'string' && typeof draft.content === 'string' && typeof draft.base === 'string' && draft.observed?.expected_source_digest) drafts.set(draftKey(draft),
    draft);
  } catch (error) {
    readError = 'Local source drafts could not be read. Keep this tab open.';
  }
  if (!document.querySelector('[data-manuscript-editor-css]')) {
    const css = el('link');
    css.rel = 'stylesheet';
    css.href = '/shared/manuscript-editor.css';
    css.dataset.manuscriptEditorCss = '';
    document.head.append(css);
  }
  host.classList.add('manuscript-editor');
  const chrome = el('div', '', 'manuscript-editor-chrome'),
  tools = el('div', '', 'manuscript-editor-tools'),
  message = el('p', '', 'manuscript-editor-state'),
  sourcePane = el('section', '', 'manuscript-source-pane'),
  fileBar = el('div', '', 'manuscript-source-files'),
  editorHost = el('div', '', 'manuscript-source-code'),
  comparison = el('section', '', 'manuscript-source-comparison');
  message.setAttribute('role', 'status');
  sourcePane.hidden = true;
  comparison.hidden = true;
  const act = (label, fn) => {
    const button = el('button', label);
    button.type = 'button';
    button.onclick = async () => {
      try {
        await fn();
      } catch (error) {
        say(error.message, true);
      }
    };
    return button;
  };
  const writeButton = declareControl(act('Write', () => showWrite()),'writing:mode-write'),
  texButton = declareControl(act('TeX', () => openSource()),'writing:mode-tex'),
  pdfButton = declareControl(act('PDF', () => readPdf()),'writing:mode-pdf'),
  saveButton = act('Save changes', () => save()),
  buildButton = declareControl(act('Build PDF', () => build()),'writing:build'),
  buildDetailsButton = declareControl(act('Build details', () => {moreTools.open=true;setup.open=true;const detail=setupBody.querySelector('.manuscript-build-details');if(detail)detail.open=true;setup.querySelector('summary')?.focus();}),'writing:build-details'),
  historyButton = declareControl(act('File history', () => history()),'writing:file-history'),
  // THE EDITOR BAND carries Undo/Redo (M5 C7): the walk's own edit history through the shell's
  // walk accessor (undoEdit/redoEdit are in the frozen command set); the keys still work inside
  // the manuscript, and the passage menu no longer repeats them.
  undoButton = act('Undo', () => {const api = walk();if (!api?.undoEdit) throw Error('Undo is available once the manuscript is open.');return api.undoEdit();}),
  redoButton = act('Redo', () => {const api = walk();if (!api?.redoEdit) throw Error('Redo is available once the manuscript is open.');return api.redoEdit();});
  undoButton.title = 'Undo the last manuscript edit · Ctrl/⌘ Z';redoButton.title = 'Redo · Ctrl/⌘ Shift-Z';
  undoButton.setAttribute('data-control','manuscript:undo');redoButton.setAttribute('data-control','manuscript:redo');
  const draftShelf = el('details', '', 'manuscript-document-setup');
  const draftSummary = el('summary', 'Retained drafts'),
  draftList = el('div');
  draftShelf.append(draftSummary, draftList);
  draftShelf.hidden = true;
  const setup = el('details', '', 'manuscript-document-setup');
  setup.append(declareControl(el('summary', 'Document setup'),'writing:setup'));
  setup.setAttribute('data-control','manuscript:document-setup');
  const setupBody = el('div', '', 'manuscript-document-setup-panel');
  setup.append(setupBody);
  const popovers = [[draftShelf, draftList], [setup, setupBody]], placePopovers = () => {for (const [details, panel] of popovers) placePopover(details, panel);};
  for (const [details, panel] of popovers) details.addEventListener?.('toggle', () => placePopover(details, panel));
  window.addEventListener?.('resize', placePopovers);
  // The document's state as chips beside the mode buttons: PDF freshness, unsaved edits.
  const chipHost = el('span', '', 'manuscript-editor-chips');
  const moreTools=el('details','','manuscript-tools-more'),moreTitle=declareControl(el('summary','Document tools'),'writing:tools'),moreBody=el('div','','manuscript-tools-secondary');moreTools.append(moreTitle,moreBody);moreBody.append(undoButton,redoButton,buildButton,buildDetailsButton,draftShelf,setup);
  tools.append(writeButton,texButton,pdfButton,chipHost,saveButton,moreTools);
  presentationStyles();
  const buildControls=mountBuildCancellation(tools,{project,request,
    onStatus:observed=>{if(documentState&&sameBuildJob(documentState.current_build?.build_job,observed.build_job))documentState={...documentState,current_build:observed};paint();},
    onTerminal:async()=>{await observe();onChanged();},onInspect:()=>observe({replaceBuild:true}),onError:error=>say(error.message,true)});
  chrome.append(tools, message);
  fileBar.append(el('label', 'Source file '));
  const files = declareControl(el('select'), 'writing:source-file');
  files.setAttribute('aria-label', 'Source file');
  fileBar.firstChild.append(files);
  files.onchange = () => openSource(files.value).catch (error => say(error.message, true));
  fileBar.append(declareControl(act('Reload saved source', () => openSource(current?.file)), 'writing:source-reload'), declareControl(act('Preamble', async () => {
    await openSource(undefined, 1, true);
  }), 'writing:source-preamble'), declareControl(act('Copy draft', () => copyDraft()), 'writing:source-copy'), declareControl(act('Compare saved source', () => compare()), 'writing:source-compare'), declareControl(act('Discard source draft',
  () => discard()), 'writing:source-discard'));
  sourcePane.append(fileBar, editorHost, comparison);
  host.prepend(chrome);
  host.append(sourcePane);
  const say = (text, error = false) => {
    if (error) persistentError = text;
    message.textContent = text;
    message.classList.toggle('error', error);
  };
  function remember() {
    clearTimeout(persistTimer);
    try {
      const held = [...drafts.values()].filter(sourceDraftDirty);
      if (held.length) storage.setItem(key, JSON.stringify(held));
      else storage.removeItem(key);
      readError = '';
    } catch (error) {
      readError = 'Source draft could not be stored for reload. Keep this tab open.';
    }
    paint();
  }
  function persist() {
    clearTimeout(persistTimer);
    persistTimer = setTimeout(remember, 250);
  }
  function capture() {
    if (current && adapter) {
      setDraftText(current,adapter.getText());
      current.position = adapter.capture();
    }
    persist();
  }
  function paint() {
    if (!alive) return;
    writeButton.setAttribute('aria-pressed', String(mode === 'write'));
    texButton.setAttribute('aria-pressed', String(mode === 'tex'));
    saveButton.disabled = saving || (mode === 'tex' && (!belongs(current) || current?.observed?.read_only || current?.effectHold)) || !(mode === 'tex' ? sourceDraftDirty(current): visualDirty());
    saveButton.textContent = saving ? 'Saving…': 'Save changes';
    saveButton.hidden = !saving && !(mode === 'tex' ? sourceDraftDirty(current): visualDirty());
    buildButton.disabled = saving || sourceDirty() || visualDirty() || documentState?.current_build?.running || buildControls.active;
    buildDetailsButton.hidden=!(documentState?.status==='FAILED'||documentState?.current_build?.reason||documentState?.current_build?.error||documentState?.current_build?.log_tail);
    pdfButton.disabled = !documentState?.read_handles?.pdf;
    undoButton.hidden = redoButton.hidden = mode !== 'write';
    undoButton.disabled = redoButton.disabled = !(mode === 'write' && !!walk()?.undoEdit && !sourceDirty());
    if (documentState) chipHost.replaceChildren(chipRow(documentChips(documentState, saveLine())));
    historyButton.disabled = !(current?.file || documentState?.selected_source?.root);
    frame.inert = sourceDirty();
    if (adapter) adapter.setReadOnly((belongs(current) && visualDirty()) || current?.observed?.read_only === true || (!belongs(current) && !sourceDraftDirty(current)));
    paintDrafts();
    // One home for document state: the chips carry PDF freshness once they exist; the
    // status line keeps the draft/source facets (root-ui/m5-fable-ux-findings.json
    // DUPLICATE_DOCUMENT_STATUS).
    const pdf = () => chipHost.children.length ? '' : manuscriptPdfState(documentState);
    const join = (...parts) => parts.filter(Boolean).join(' · ');
    if (readError) say(readError, true);
    else if (persistentError) {
      // An error line keeps the document state beside it: the retained human error and the
      // PDF claim are read together when recovering.
      message.textContent = join(persistentError, manuscriptPdfState(documentState));
      message.classList.add('error');
    }
    else if (mode === 'tex' && current && !belongs(current)) say(sourceDraftDirty(current) ? 'Earlier document draft · edits stay local. Copy, compare or discard; it cannot overwrite the current manuscript.': join('Read-only document dependency', pdf()));
    else if (current?.effectHold) say(current.effectHold.message, true);
    else if (sourceDirty()) say(mode === 'write' ? 'Saved manuscript · your unsaved TeX draft is retained. Return to TeX to save or discard it.': join('Unsaved TeX draft', pdf()));
    else if (mode === 'tex' && (!belongs(current) || current?.observed?.read_only)) say(join('Read-only document dependency', pdf()));
    else if (mode === 'tex' && visualDirty()) say('Saved source · your unsaved Write edits are retained. Return to Write to save them.');
    else {
      const live = (documentState?.files || []).find(row => row.file === current?.file)?.expected_source_digest;
      const old = mode === 'tex' && live && live !== current?.observed?.expected_source_digest;
      say(join(old ? 'Earlier source version · reload saved source': mode === 'tex' ? 'Saved source': '', pdf()));
    }
  }
  function paintDrafts() {
    const held = allDirty();
    draftShelf.hidden = !held.length;
    draftSummary.textContent = 'Drafts (' + held.length + ')';
    draftList.replaceChildren();
    for (const draft of held) {
      const row = el('div');
      row.append(act(draft.file.split('/').pop() + (belongs(draft) ? ' · unsaved': ' · earlier document'), () => {
        draftShelf.open = false;
        return openDraft(draft);
      }));
      draftList.append(row);
    }
  }
  function paintDocument() {
    const selected = documentState.selected_source || {},
    list = documentState.files || Object.keys(documentState.source_observation?.file_revisions || {}).map(file => ({
      file
    }));
    files.replaceChildren();
    for (const row of list) {
      const file = typeof row === 'string' ? row: row.file || row.path;
      if (!file) continue;
      const option = el('option', file.split('/').pop() + (file === selected.root ? ' · root': '') + (row.read_only ? ' · read-only': ''));
      option.value = file;
      files.append(option);
    }
    if (current) files.value = current.file;
    // THE DOCUMENT SETUP PANEL (M5 C7, plan §5 manuscript.document_setup): an object header for
    // the selected root (chips: editable or read-only edition, document class, PDF freshness),
    // the document files as relation rows, Template & layout as the primary action when the
    // owner offers it, and one Exact disclosure for the build basis; build diagnostics open
    // on failure. Nothing here is read beyond /authoring/document.
    const template = documentState.template;
    const rootName = (selected.root || '').split('/').pop();
    const setupChips = [selected.read_only ? {label: 'Read-only edition', tone: 'historical', title: 'The selected edition cannot be written to.'} : {label: 'Editable source', tone: 'ok'},
      ...(template?.class_name ? [{label: 'Class ' + template.class_name, tone: 'neutral', title: template.class_file || ''}] : template ? [{label: 'Document class unavailable', tone: 'attention'}] : []),
      ...documentChips(documentState, saveLine())];
    const openRoot = declareControl(act('Open root and preamble', () => openSource(selected.root, 1)),'writing:open-root');
    const setupActions = [openRoot, historyButton];
    if (template?.available) {
      const layout = act('Template & layout', () => openTemplateLayout());
      layout.classList.add('primary');layout.setAttribute('data-control','manuscript:template-layout');
      layout.disabled = templateOpening;if (templateOpening) layout.setAttribute('aria-busy', 'true');
      templateButton = layout;setupActions.push(layout);
    } else templateButton = null;
    if (template?.available || templateNote.textContent) setupActions.push(templateNote);
    setupBody.replaceChildren(objectHeader({eyebrow: 'Document setup', title: rootName || 'No selected source', chips: setupChips,
      summary: manuscriptPdfState(documentState), actions: setupActions}));
    setupBody.append(relationList(list.map(row => {
      const file = typeof row === 'string' ? row : row.file || row.path;
      if (!file) return null;
      return {kind: file === selected.root ? 'Root' : 'File', label: file, run: () => openSource(file), control: 'writing:setup-file', owner: file, onError: error => say(error.message, true),
        chip: row.read_only ? {label: 'read-only', tone: 'historical'} : null};
    }).filter(Boolean), {emptyText: 'No document files recorded.'}));
    const exact = el('details', '', 'operator-exact');
    exact.append(declareControl(el('summary', 'Exact build basis'),'writing:build-basis'), el('code', selected.root || 'No selected source'), el('p', manuscriptPdfState(documentState)));
    if (documentState.observation_coherence?.status !== 'MATCHED') exact.append(el('p', 'Build basis: ' + String(documentState.observation_coherence?.status || 'unproved').toLowerCase().replaceAll('_', ' ')));
    if (template?.class_options) exact.append(el('p', 'Class options: ' + (Array.isArray(template.class_options) ? template.class_options.join(', ') : template.class_options)));
    if (template?.class_file) exact.append(el('code', template.class_file));
    setupBody.append(exact);
    const buildState=documentState.current_build||{};
    if(documentState.status==='FAILED'||buildState.reason||buildState.error||buildState.log_tail){
      const diagnostic=el('details','','manuscript-build-details');diagnostic.open=documentState.status==='FAILED';
      diagnostic.append(declareControl(el('summary',buildState.state==='cancelled'?'Stopped build':documentState.status==='FAILED'?'Build error':'Build details'),'writing:build-log'));
      if(buildState.reason||buildState.error)diagnostic.append(el('p',buildState.reason||buildState.error));
      if(buildState.log_tail)diagnostic.append(el('pre',buildState.log_tail));
      setupBody.append(diagnostic);
    }
    paint();
  }
  // TEMPLATE & LAYOUT (C12, 2026-10-15; Root saw an enabled button do nothing on a repeat open). The click re-reads
  // the document first, and that read repaints this panel, so the clicked button is replaced while it opens and a
  // refusal reached only the editor status line far from it. One editor-owned flag and one persistent note follow
  // the CURRENT button: every repaint renders it disabled and aria-busy while opening, the note says what is
  // happening and keeps any refusal beside the button (also said in the status line). It never opens twice.
  async function openTemplateLayout() {
    if (templateOpening) return;
    templateOpening = true;pendingRead(templateNote, 'Opening Template & layout…');templateNote.classList.remove('error');busyTemplate(true);
    try {
      capture();await observe();
      if (!alive) return;
      const descriptor = documentState?.template;
      if (!descriptor?.available) throw Error(descriptor?.reason || 'Template inspection is unavailable for this selected source.');
      setup.open = false;
      await openDocumentTemplate({project,documentState,request,captureDraft:mode==='tex'&&current?()=>controller.captureTemplateDraft():null,
        capturePlace:()=>controller.capturePlace(),restorePlace:place=>controller.restorePlace(place),
        onApplied:settleTemplateApplication,onCanonicalBuild:build,onCanonicalPdf:readPdf,
        onEditSource:()=>openSource(undefined,1,true),onOpenArtifact,isCurrent:()=>alive,
        onRead:(handle,label)=>{if(onOpenArtifact)return onOpenArtifact(handle.http?.url,label,{ownerRead:handle});}
      });
      templateNote.textContent = '';
    } catch (error) {
      templateNote.textContent = error.message;templateNote.classList.add('error');
      if (!templateNote.isConnected && templateButton?.parentNode) templateButton.after?.(templateNote);
      throw error;
    } finally {templateOpening = false;busyTemplate(false);}
  }
  function busyTemplate(on) {if (!templateButton) return;templateButton.disabled = on;if (on) templateButton.setAttribute('aria-busy', 'true');else templateButton.removeAttribute?.('aria-busy');}
  async function observe({replaceBuild=false}={}) {
    const ticket = ++ observationGeneration;
    const value = await request('/authoring/document?' + new URLSearchParams({
      project
    }));
    if (!alive || ticket !== observationGeneration) return;
    documentState = value;
    buildControls.observe(value.current_build,{replace:replaceBuild});
    paintDocument();
    return value;
  }
  async function displayDraft(draft, line, ticket) {
    current = draft;
    mode = 'tex';
    frame.hidden = true;
    sourcePane.hidden = false;
    files.value = current.file;
    comparison.hidden = true;
    if (!adapter) adapter = await (adapterPromise ||= mountSourceEditor(editorHost, {
      content: current.content,
      onChange: (text, selection) => {
        setDraftText(current,text);
        current.position = selection;
        persist();
        paint();
        onAttention();
      },
      onSelection: selection => {
        if (current) current.position = selection;
        onAttention();
      },
      onSave: () => save().catch (error => say(error.message, true))
    }));
    if (!alive || ticket !== loadGeneration) return;
    adapter.setDocument(current.content, current.position);
    if (line) adapter.focusLine(line);
    else adapter.focus();
    paint();
    onAttention();
  }
  async function openDraft(draft) {
    capture();
    persistentError='';
    const ticket = ++ loadGeneration;
    position = mode === 'write' ? walk()?.captureFocus?.(): position;
    return displayDraft(draft, undefined, ticket);
  }
  async function openSource(file, line, useCurrentRoot=false, occurrenceBasis=null, observedRead=null) {
    capture();
    const held = !file && !useCurrentRoot
      ? (sourceDraftDirty(current) ? current : allDirty().find(belongs)) : null;
    const ticket = ++loadGeneration;
    position = mode === 'write' ? walk()?.captureFocus?.() : position;
    try {
      const writeLocation=!held&&!file&&!useCurrentRoot&&mode==='write'?writeSourceLocation(walk()):null;
      await observe();
      if (!alive || ticket !== loadGeneration) return;
      if (held) {
        persistentError='';
        await displayDraft(held,line,ticket);
        say('Unsaved TeX draft retained · '+held.file.split('/').at(-1));
        return;
      }
      if(writeLocation){
        if(writeLocation.basis.selection_identity!==documentState.selection_identity||!documentState.files?.some(row=>row.file===writeLocation.file))throw Error('The document selection changed. Refresh the displayed manuscript before opening its TeX.');
        file=writeLocation.file;line=line||writeLocation.line;occurrenceBasis=writeLocation.basis;
      }
      const basis=documentState;
      const currentMember=(basis.files||[]).some(row=>row.file===current?.file);
      file = useCurrentRoot ? basis.selected_source?.root
        : file || (currentMember ? current.file : basis.selected_source?.root);
      if (!file) throw Error('Select a manuscript source first.');
      // A qualified reader may already have inspected this exact owner response.
      // Reuse it as a read, never as a replacement for a retained draft's basis.
      const observed=observedRead?validateSourceRead(observedRead):await sourceClient.read({project,file});
      if((observedRead||occurrenceBasis)&&observed.file!==file)throw Error('The source observation addresses a different file.');
      if (!alive || ticket !== loadGeneration) return;
      if (observed.selection_identity!==basis.selection_identity || documentState.selection_identity!==basis.selection_identity)
        throw Error('The selected document changed while its source was opening. Reopen TeX to inspect the current document; your draft is retained.');
      if (occurrenceBasis && (occurrenceBasis.selection_identity!==observed.selection_identity || occurrenceBasis.source_digest!==observed.expected_source_digest))
        throw Error('This source location changed since it was linked. Refresh the outline or reader-plan item before navigating; your draft is preserved.');
      if(observedRead){const currentDigest=basis.files?.find(row=>row.file===file)?.expected_source_digest;if(currentDigest&&currentDigest!==observed.expected_source_digest)throw Error('The saved source changed while opening the inspected passage. Refresh the outline; your draft is preserved.');}
      const id=draftKey({file:observed.file,observed}),retained=drafts.get(id);
      const draft=sourceDraftDirty(retained)?retained:{file:observed.file,content:observed.content,base:observed.content,observed,position:retained?.position};
      drafts.set(id,draft);
      persistentError='';
      const heldPosition = occurrenceBasis && sourceDraftDirty(retained);
      await displayDraft(draft,heldPosition?undefined:line,ticket);
      if (heldPosition) {
        const lines=observed.content.split('\n'),start=Math.max(0,(line||1)-1);
        comparison.replaceChildren(el('h3','Saved source passage'),el('p','Your TeX draft and its position are retained.'),el('pre',lines.slice(start,start+20).join('\n')));
        comparison.hidden=false;
      }
      if (sourceDraftDirty(retained) && retained.observed.expected_source_digest!==observed.expected_source_digest)
        say('Saved source changed. Your draft and original basis are preserved; compare saved source before saving.',true);
    } catch(error) {
      if (!alive || ticket !== loadGeneration) return;
      if (held) await displayDraft(held,line,ticket);
      say(error.message,true);
      if (!held) throw error;
    }
  }
  function showWrite({restoreKeyboard=false,isCurrent=()=>true}={}) {
    if(!isCurrent())return;
    capture();
    mode = 'write';
    frame.hidden = false;
    sourcePane.hidden = true;
    walk()?.restoreFocus?.(position,{keyboard:restoreKeyboard,isCurrent});
    paint();
    onAttention();
  }
  async function save() {
    if (savePromise) return savePromise;
    savePromise = (async () => {
      saving = true;
      let operationDraft = null;
      paint();
      try {
        if (mode === 'write') {
          if (sourceDirty()) throw Error('Save or discard the TeX draft before saving Write edits.');
          if (walk()?.flipState?.().open) await walk().saveFlip();
          else await walk()?.commitAll?.();
          // words still held (a save still out, refused, uncertain or in conflict): the save line
          // in the chips says which; this band line adds nothing, least of all TeX advice (save-trace C8)
          if (visualDirty()) { persistentError = ''; return; }
          await observe();
          onChanged();
          return;
        }
        capture();
        if (!current || !sourceDraftDirty(current)) return;
        if (current.effectHold) throw Error(current.effectHold.message);
        if (!belongs(current)) throw Error('This retained draft does not belong to the current editable document. Copy or compare it; no source was written.');
        if (visualDirty()) throw Error('Save the Write edits before changing the exact source.');
        const draft = current,
        submitted = {
          file: draft.file,
          content: draft.content,
          expected_source_digest: draft.observed.expected_source_digest,
          expected_selection: draft.observed.selection_identity
        };
        operationDraft = draft;
        const receipt = await sourceClient.save({
          project,
          observed: draft.observed,
          content: submitted.content
        });
        Object.assign(draft, acknowledgeDraft(draft, submitted, receipt));
        persistentError='';
        remember();
        comparison.hidden = true;
        onChanged();
        try {
          await walk()?.refresh?.();
          await observe();
        } catch (error) {
          say('File saved. Document refresh failed: ' + error.message, true);
          return;
        }
        say((receipt.changed === false ? 'No source changes': 'File saved') + ' · ' + manuscriptPdfState(documentState) + (receipt.maintenance_warnings?.length ? ' · History maintenance needs attention': ''));
      } catch (error) {
        const recoveryDraft = operationDraft || current;
        if (recoveryDraft) recoveryDraft.uncertain = true;
        let disposition;
        try { disposition = sourceEffectFromError(error, {project, selectionIdentity:recoveryDraft?.observed?.selection_identity,file:recoveryDraft?.file,beforeDigest:recoveryDraft?.observed?.expected_source_digest}); }
        catch (invalid) { error = invalid; }
        if (disposition) error.message = disposition.message;
        if (recoveryDraft && (disposition?.suppressRetry || error.sourceEffectUnverified)) {
          recoveryDraft.effectHold = {state:disposition?.state || 'UNPROVED',message:error.message};
          // Keep original text and guards until explicit inspection/reconciliation.
          // A landed source write is not an ordinary unsaved draft or retry.
          onChanged();
          try { await observe(); } catch { /* The retained receipt remains visible. */ }
        }
        remember();
        const retained=Object.assign(new Error(error.message+(recoveryDraft?.effectHold?' Your recovery copy and original basis are retained.':' Your draft is retained. Use Compare saved source before retrying.')),{cause:error,status:error.status,reason:error.reason,result:error.result,recovery:error.recovery});
        say(retained.message,true);
        throw retained;
      } finally {
        const finalMessage = message.textContent,
        failed = message.classList.contains('error');
        saving = false;
        savePromise = null;
        paint();
        say(finalMessage, failed);
      }
    })().finally(() => {
      savePromise = null;
    });
    return savePromise;
  }
  async function copyDraft() {
    if (!current) return;
    capture();
    try {
      await navigator.clipboard.writeText(current.content);
      say('Draft copied.');
    } catch {
      comparison.replaceChildren(el('h3', 'Copy retained draft'));
      const text = el('textarea');
      text.value = current.content;
      text.readOnly = true;
      text.setAttribute('aria-label', 'Retained draft to copy');
      comparison.append(text);
      comparison.hidden = false;
      text.focus();
      text.select?.();
      say('Select and copy the retained text below.');
    }
  }
  async function compare() {
    capture();
    if (!current) return;
    const draft = current;
    await observe();
    if(current!==draft)return;
    const documentBasis=documentState;
    let observed = null,
    unavailable = 'This file is not part of the current document.';
    if ((documentState?.files || []).some(row => row.file === draft.file)) {
      try {
        observed = await sourceClient.read({project,file:draft.file});
        if(observed.selection_identity!==documentBasis.selection_identity||documentState.selection_identity!==documentBasis.selection_identity)throw Error('The selected document changed while comparing source. Compare again; the original draft basis is retained.');
      } catch (error) {
        observed=null;
        unavailable = error.message;
      }
    }
    if (current !== draft) return;
    comparison.replaceChildren(el('h3', 'Compare source'));
    const plan = sourceComparisonPlan(draft, observed, belongs(draft));
    if (plan.notice) comparison.append(el('p', observed ? plan.notice : unavailable));
    if (plan.columns.length) {
      const columns = el('div', '', 'source-comparison-columns');
      columns.dataset.columns = String(plan.columns.length);
      for (const [label, text] of plan.columns) {
        const side = el('section');
        side.append(el('h4', label), el('pre', text));
        columns.append(side);
      }
      comparison.append(columns);
    }
    const useReviewedBasis = () => {
      draft.base = observed.content;
      draft.observed = observed;
      draft.revision='DRAFT-'+globalThis.crypto.randomUUID();
      draft.uncertain = false;
      delete draft.effectHold;
      persistentError='';
      remember();
      comparison.hidden = true;
      say(plan.useSavedVersion ? 'Using the matching saved version.' : 'Reviewed basis selected. Check your draft, then Save changes.');
    };
    if (plan.canUseBasis) {
      comparison.append(el('p', 'Reconcile your draft first. The next save will replace the reviewed saved file with your draft.'),
        act('Use this reviewed save basis', useReviewedBasis));
    } else if (plan.useSavedVersion) {
      comparison.append(act('Use saved version', useReviewedBasis));
    }
    comparison.append(act('Close comparison', () => {
      comparison.hidden = true;
    }));
    comparison.hidden = false;
  }
  async function discard() {
    if (!sourceDraftDirty(current)) return;
    if (!confirm('Discard this unsaved source draft?')) return;
    const draft = current,
    file = draft.file,
    admitted = belongs(draft);
    drafts.delete (draftKey(draft));
    persistentError='';
    current = null;
    remember();
    if (admitted) await openSource(file);
    else showWrite();
  }
  async function build() {
    await observe();
    if (hasAnyDraft()) throw Error('Save your edits before building the PDF.');
    const receipt=await request('/authoring/build', {
      project
    });
    if(receipt?.build_job)await buildControls.follow(receipt);
    await observe();
    if(receipt?.build_job)return;
    const check = async () => {
      try {
        await observe();
        if (documentState.current_build?.running) poll = setTimeout(check, 900);
        else if (documentState.status === 'FAILED') {
          const error = documentState.current_build;
          say('Build failed. Your saved source is intact. ' + (error.error || error.reason || 'Open Document setup for the build basis.'),
          true);
        } else {
          await walk()?.refresh?.();
          onChanged();
        }
      } catch (error) {
        say(error.message, true);
      }
    };
    if (documentState.current_build?.running) poll = setTimeout(check, 900);
    else await check();
  }
  async function readPdf() {
    capture();
    await observe();
    const url = documentPdfURL(documentState);
    if (!url) throw Error('Build this document to create a PDF.');
    await openPdf(url, documentState.status === 'READY' ? 'Current manuscript PDF': 'Saved manuscript PDF', {
      notice: documentPdfNotice(documentState, sourceDirty() || visualDirty()),
      onOpenArtifact
    });
  }
  function history(file) {
    capture();
    return onHistory({
      file: file || current?.file || documentState?.selected_source?.root,
      label: (file || current?.file || documentState?.selected_source?.root || 'Manuscript').split('/').pop()
    });
  }
  async function settleTemplateApplication(result,candidate){
    if(!alive)return {settled:false,reason:'This editor has closed. Reopen the exact candidate and current source to inspect the retained outcome.'};
    capture();
    if(result?.metadata_only===true){await observe();return {settled:false,reason:'Recording finished without another source write. Existing drafts were retained.'};}
    const included=result?.included_draft;
    const selection=candidate?.selected_source?.selection_identity;
    const effect=sourceEffectDisposition(result,{project,selectionIdentity:selection});
    if(!effect)return {settled:false,reason:'Inspect the exact source outcome before changing the local draft.'};
    const committed=['COMMITTED','UNCHANGED'].includes(effect.state);
    if(!included){await observe();if(alive&&committed){if(!visualDirty()&&!sourceDirty())await walk()?.refresh?.();onAttention();onChanged();}return {settled:false,reason:'Saved source observed. Local TeX drafts were not part of this candidate and remain retained.'};}
    if(included.file!==candidate.included_draft?.file||included.revision!==candidate.included_draft?.revision||included.input_content_sha256!==candidate.included_draft?.input_content_sha256)
      throw Error('The application did not acknowledge this exact captured draft. Its local text and original basis are retained.');
    const draft=drafts.get(draftKey({file:included.file,observed:{selection_identity:selection}})),before=candidate.source_changes.find(row=>row.file===included.file)?.before_sha256;
    const matches=()=>draft&&draft.revision===included.revision&&draft.observed.expected_source_digest===before&&draft.observed.selection_identity===selection;
    const retain=async reason=>{if(alive){remember();await observe();if(alive&&committed){onAttention();onChanged();}}return {settled:false,reason};};
    if(!committed){if(draft)draft.effectHold={state:effect.state,message:effect.message};return retain(effect.message+' The local recovery copy and original basis remain retained.');}
    if(!matches())return retain('Template source saved. Newer local typing remains unsaved on its original basis; compare saved source before saving it.');
    let snapshot;
    try{snapshot=await templateDraftSnapshot(draft,documentState);}catch{return retain('Template source saved. The local draft no longer belongs to the current editable selection and remains retained on its original basis.');}
    if(snapshot.input_content_sha256!==included.input_content_sha256)return retain('Template source saved. The local draft differs from the captured input and remains retained.');
    const file=effect.effect.files.find(row=>row.path===included.file);
    if(!file)return retain('Template source saved. No physical change to this draft file was recorded; its local text remains retained.');
    let observed;
    try{
      observed=validateSourceRead(await sourceClient.read({project,file:included.file}));
      if(observed.file!==included.file||observed.selection_identity!==selection||observed.expected_source_digest!==file.after_sha256)
        throw Error('Current source differs from the acknowledged template postimage.');
    }catch(error){return retain('Template source was saved, but its exact postimage could not be reopened: '+error.message+' The local draft and original basis remain retained.');}
    if(!alive)return {settled:false,reason:'Source outcome retained. The closed editor did not change any local draft.'};
    capture();
    if(!matches()||draft.content!==snapshot.content)return retain('Template source saved. Newer local typing remains unsaved on its original basis; compare saved source before saving it.');
    Object.assign(draft,{content:observed.content,base:observed.content,observed,revision:'DRAFT-'+globalThis.crypto.randomUUID(),uncertain:false});delete draft.effectHold;
    if(current===draft&&mode==='tex'&&adapter)adapter.setDocument(draft.content,draft.position);
    remember();await observe();if(!alive)return {settled:true,reason:'The exact captured draft was acknowledged before this editor closed.'};onAttention();
    if(!visualDirty())await walk()?.refresh?.();
    onChanged();return {settled:true,reason:'Template source saved. The unchanged captured TeX draft now shows the reviewed applied source.'};
  }
  const beforeUnload = event => {
    capture();
    remember();
    if (allDirty().length) {
      event.preventDefault();
      event.returnValue = '';
    }
  };
  window.addEventListener('beforeunload', beforeUnload);
  const controller={
    observe,
    openSource,
    showWrite,
    save,
    build,
    readPdf,
    history,
    capture,
    settleTemplateApplication,
    async captureTemplateDraft(){if(mode!=='tex'||!current)throw Error('Open the TeX draft you want to preview. No edits were saved.');capture();const snapshot=await templateDraftSnapshot(current,documentState);remember();return snapshot;},
    capturePlace() {
      capture();
      return {mode, draftKey:current?draftKey(current):null, position:mode==='write'?walk()?.captureFocus?.({keyboard:true}):current?.position};
    },
    async restorePlace(place,{isCurrent=()=>true}={}) {
      if (!place||!isCurrent()) return;
      if (place.mode==='tex' && drafts.has(place.draftKey)) {
        const draft=drafts.get(place.draftKey);
        draft.position=place.position||draft.position;
        await openDraft(draft);
      } else {
        position=place.position||position;
        showWrite({restoreKeyboard:true,isCurrent});
      }
    },
    openSetup() {
      moreTools.open=true;setup.open = true;
      setup.querySelector('summary').focus();
    },
    hasDraft: sourceDirty,
    hasAnyDraft,
    mode: () => mode,
    stateChanged() {
      paint();
      onAttention();
    },
    changed() {
      paint();
      observe().catch (error => say(error.message, true));
    },
    prepareForSession(selection = {}) {
      capture();
      if (!current || !sourceDraftDirty(current) || mode !== 'tex' && !belongs(current) || mode !== 'tex' && !selection.files?.length) return {};
      if (selection.files?.length && !selection.files.includes(current.file)) return {};
      return {
        selection: {
          ...(belongs(current) ? {
            files: [current.file]
          }
          : {}),
          draft: sourceDraftAttachment(current)
        }
      };
    },
    attention() {
      if (mode !== 'tex' || !current) return null;
      const dirty = sourceDraftDirty(current),
      selected = adapter?.selection() || {};
      return {
        surface: 'manuscript',
        label: current.file.split('/').pop() + (dirty ? ' · unsaved draft': ''),
        selection: {
          ...(belongs(current) || !dirty ? {
            files: [current.file]
          }
          : {}),
          ...(!dirty ? {
            line_start: selected.line_start || 1,
            line_end: selected.line_end || 1,
            ...(selected.quote ? {
              quote: selected.quote
            }
            : {})
          }
          : {})
        }
      };
    },
    destroy() {
      alive = false;
      capture();
      remember();
      clearTimeout(poll);
      clearTimeout(persistTimer);
      buildControls.destroy();
      adapter?.destroy();
      window.removeEventListener('beforeunload', beforeUnload);
      window.removeEventListener?.('resize', placePopovers);
    }
  };
  return controller;
}
