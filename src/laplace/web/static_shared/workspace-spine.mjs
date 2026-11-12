// READER PLAN (M5 C6). Owner: project_structure (summary list rows G18, one section detail with
// its reader transition and paragraph plan, the bounded guard projection) through the same
// /work/structure door the native tool uses. This view paints the ordered plan (number, title,
// purpose, binding mark, current marker = the selected section, set on arrival from the
// manuscript or the last-opened item), the selected section as an object header with Open in
// manuscript first, the reader transition and exposition plan, a lazily shown relation map
// (section <-> source heading, argument, evidence, work; from the detail read alone, drawn by
// workspace-topology), the binding, author notes and the structural prior behind lazy reads.
// Paragraph edit/move/remove dialogs open on a bounded subject read (readerSubjectRead) so
// their guards are fresh and small. Drafts live in sessionStorage laplace:reader-state-draft.
// Reads (C10-C11, ACTUAL-C6-DETAIL-BYTES): the selected section is read as its display
// (projection:display, bounded page: authored text, standing and doors), a paragraph row expands
// in place through its own display read, every edit/remove/review/restructure/link/prepare call
// is acquired on its subject read when the door opens (edit_choices for the descriptors), and the
// plan-level editors read view:plan (planGuardHandle) instead of the full structure.
// Controls: reader-plan:item, reader-plan:open-in-manuscript, reader-plan:relation-map,
// reader-plan:paragraph-action, reader-plan:paragraph-expand, reader-plan:transition-expand (reader-state.mjs).
import {restructureFollowThroughSubmission,validateRestructureEffect,openMetadataReconciliation,openRecordedRestructure} from './reader-restructure.mjs';
import {openLogicalRestructure} from './reader-logical-restructure.mjs';
import {orderedPlan,objectHeader,bindingChip,inputChip,lazySection,action,presentationStyles,declareControl} from './workspace-presentation.mjs';
import {mountTopology} from './workspace-topology.mjs';
import {
  renderReaderState,
  readerSubjectRead,
  readerSubjectAction,
  readerDisplayHandle,
  readerDoor,
  editReaderMetadata,
  renderArchitecturePrior,
  inspectArchitecturePrior,
  changeReaderParagraph,
  acknowledgeReaderInputs,
  showReaderDialog,
  labelReaderControl,
  lockReaderDialog
} from './reader-state.mjs';
import {
  ownerHumanTarget
} from './writing-owner-read.mjs';
import {
  readManuscriptSource
} from './manuscript-source-client.mjs';
import {
  requirePlanCompletion,
  planFailure
} from './plan-publication.mjs';
import {pendingRead} from './pending-read.mjs';
// wave 13 id sweep: control ids by tag and label (begin)
// wave 13 id sweep: control ids (end)
const pin = value => typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value);
const sourcePath = value => typeof value === 'string' && value.length > 0 && !value.startsWith('/') && !value.includes('\\') && !value.split('/').includes('..') && !/[\u0000-\u001f]/.test(value);
const element = (tag, text = '', className = '') => {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
};
export function structureReadURL(project, payload) {
  const query = new URLSearchParams({
    project
  });
  for (const [key, value] of Object.entries(payload || {})) {
    if (value !== undefined && value !== null) query.set(key, Array.isArray(value) ? JSON.stringify(value): String(value));
  }
  const url = '/work/structure?' + query;
  const read = ownerHumanTarget(url);
  if (read?.kind !== 'structure' || read.project !== project) throw Error('The reader-plan owner supplied invalid reading coordinates.');
  return url;
}
// Normalise the owner's existing method/route/query companion. Never resolve a
// label, path suffix or effect name into a destination.
export function spineReadURL(handle, project) {
  if (!handle || handle.operation !== 'structure') throw Error('This link has no reader-plan owner.');
  const native = structureReadURL(project, handle.payload);
  if (!handle.http) return native;
  // Existing native-only structure continuations.
  const http = handle.http;
  if (http.method !== 'GET' || http.route !== '/work/structure' || http.query?.project !== project) throw Error('The reader-plan link belongs to a different owner.');
  const served = structureReadURL(project, Object.fromEntries(Object.entries(http.query).filter(([key]) => key !== 'project')));
  const a = new URL(native, 'http://local').searchParams;
  const b = new URL(served, 'http://local').searchParams;
  if (a.size !== b.size || [...a].some(([key, value]) => b.get(key) !== value)) throw Error('The reader-plan link disagrees with its native coordinates.');
  return served;
}
// G18b: an outline (laplace.source-outline/2) states each file's raw byte basis ONCE in
// `sources[file]` beside `selected_source.selection_identity`, and the owner's read handles
// ONCE as `read_routes` templates. This rebuilds the exact occurrence every guard below
// expects from the owner's own templates: nothing is guessed, `<file>`, `<line>` and
// `<line_end>` are filled from the row and `sourceOccurrence` still validates the result.
export function outlineOccurrence(value, row) {
  const source = value?.sources?.[row?.file];
  const routes = value?.read_routes || {};
  if (!source || !routes.source_read || !routes.structure_read) throw Error('This outline carries no source basis or read routes for the heading. Refresh the document outline.');
  const fill = template => JSON.parse(JSON.stringify(template), (key, item) => item === '<file>' ? row.file : item === '<line>' ? row.line : item === '<line_end>' ? row.line_end : item);
  return {
    ...row,
    basis: {selection_identity: value.selected_source?.selection_identity, source_digest: source.source_digest},
    source_read: fill(routes.source_read),
    structure_read: fill(routes.structure_read)
  };
}
export function sourceOccurrence(row) {
  if (!sourcePath(row?.file) || !Number.isInteger(row.line) || row.line < 1 || !Number.isInteger(row.line_end) || row.line_end < row.line || !pin(row.basis?.selection_identity) || !pin(row.basis?.source_digest)) {
    throw Error('This source occurrence has no exact inspected basis. Refresh the document outline.');
  }
  const read = row.source_read;
  const http = read?.http;
  if (read?.operation !== 'source' || read.payload?.files?.length !== 1 || read.payload.files[0] !== row.file || read.payload.line_start !== row.line || read.payload.line_end !== row.line_end || http?.method !== 'GET' || http.route !== '/projection/tex' || http.query?.view !== 'source' || http.query.file !== row.file) {
    throw Error('This occurrence has no exact source read handle.');
  }
  if (Object.keys(http.query).some(key => !['corpus', 'file', 'view'].includes(key))) throw Error('The source read handle has unsupported coordinates.');
  return row;
}
export async function inspectSourceOccurrence(row, project, {
  read = readManuscriptSource
}
= {}) {
  sourceOccurrence(row);
  if (row.source_read.http.query.corpus !== project) throw Error('This source occurrence belongs to another project.');
  const observed = await read({
    project,
    file: row.file
  });
  if (observed.file !== row.file || observed.selection_identity !== row.basis.selection_identity || observed.expected_source_digest !== row.basis.source_digest) {
    throw Error('The source changed since this outline was read. Refresh the outline and choose the heading again; your draft is preserved.');
  }
  return observed;
}
export function bindingLabel(source = {}) {
  const labels = {
    EXACT_HEADING: 'Linked source heading',
    FILE_ONLY: 'Linked source file',
    INFERRED: 'Suggested match · not linked',
    UNRESOLVED: 'No source heading linked',
    AMBIGUOUS: 'Source link needs a choice'
  };
  return labels[source.precision] || 'Source link unavailable';
}
export function boundPlanHeading(sections, head) {
  if (!head || !sourcePath(head.file)) return null;
  const matches = sections.filter(section => {
    const source = section.source;
    const heading = source?.heading;
    return source?.precision === 'EXACT_HEADING' && source.status === 'MATCHED' && heading?.file === head.file && heading.line === head.line_start && (!head.label || heading.label === head.label);
  });
  return matches.length === 1 ? matches[0]: null;
}
export function structureObservation(value, sections = value?.sections || []) {
  const files = new Map();
  for (const section of sections) for (const [file, basis] of Object.entries(section.source?.basis || {})) {
    if (!sourcePath(file) || !pin(basis.source_digest) || basis.selection_identity !== value?.selected_source?.selection_identity) throw Error('The displayed source binding has no exact byte observation. Refresh the plan item.');
    files.set(file, {
      file,
      source_digest: basis.source_digest
    });
  }
  if (files.size > 16) throw Error('This displayed scope contains more than 16 source files. Select a narrower plan item before sending.');
  const selection = value?.selected_source?.selection_identity;
  if (!pin(selection)) return null;
  if (value.structure_observation) {
    const observed = value.structure_observation;
    if (observed.selection_identity !== selection || !Array.isArray(observed.source_files) || observed.source_files.length > 16 || !Array.isArray(observed.reader_subjects) || observed.reader_subjects.length > 64 || [...files.values()].some(file => !observed.source_files.some(row => row.file === file.file && row.source_digest === file.source_digest))) {
      throw Error('The owner did not provide a complete observation of the displayed reader scope. Refresh or select a narrower item.');
    }
    return observed;
  }
  return {
    plan_revision: value.authority?.plan_revision || null,
    selection_identity: selection,
    source_files: [...files.values()],
    ...(value.authority?.spine_revision ? {
      spine_revision: value.authority.spine_revision
    }
    : {})
  };
}
export function bindingSubmission(project, action, row, sectionId) {
  sourceOccurrence(row);
  if (action?.operation !== 'structure_change' || action.http?.method !== 'POST' || action.http.route !== '/work/structure/change' || action.payload?.operation !== 'bind_source' || typeof sectionId !== 'string' || !sectionId || action.payload.section_id !== sectionId || !pin(action.payload.expected_plan_revision) || typeof row.heading_before !== 'string' || !row.heading_before) {
    throw Error('The plan owner supplied no guarded source-link action. Refresh this plan item.');
  }
  if (Object.keys(action.payload).some(key => !['operation', 'section_id', 'expected_plan_revision'].includes(key))) throw Error('The source-link preparation contains unobserved action fields. Nothing was sent.');
  if (row.source_read.http.query.corpus !== project) throw Error('This heading belongs to another project.');
  return {
    project,
    ...action.payload,
    file: row.file,
    line: row.line,
    heading_before: row.heading_before,
    expected_selection: row.basis.selection_identity,
    expected_source_digest: row.basis.source_digest
  };
}
function styles() {
  presentationStyles();
  if (document.querySelector('link[data-workspace-spine]')) return;
  const link = element('link');
  link.rel = 'stylesheet';
  link.href = '/shared/workspace-spine.css';
  link.dataset.workspaceSpine = '';
  document.head.append(link);
}
function button(label, run, onError, className = '') {
  const control = element('button', label, className);
  control.type = 'button';
  control.onclick = async () => {
    control.disabled = true;
    const unlock = lockReaderDialog(control.closest?.('dialog'));
    try {
      await run();
    } catch (error) {
      onError(error);
    } finally {
      unlock();
      if (control.isConnected !== false) control.disabled = false;
    }
  };
  return control;
}
function validateOutline(value, project) {
  if (value?.schema_version !== 'laplace.source-outline/2' || value.project !== project || !Array.isArray(value.headings?.items) || typeof value.as_of !== 'string' || !value.sources || !value.read_routes) {
    throw Error('The document outline returned a different owner or an incomplete reading.');
  }
  return value;
}
// One local chooser over actual source observations; no graph hydration, source
// rewrite or new binding store. Confirm submits the original three owner guards.
export async function chooseSourceBinding({
  project,
  section,
  action,
  request,
  opener,
  onLinked = async () => {},
  refreshAction,
  readSource = readManuscriptSource
}) {
  styles();
  const dialog = element('dialog', '', 'spine-binding-dialog');
  const title = element('h2', 'Link source heading');
  const message = element('p', '', 'spine-status');
  message.setAttribute('role', 'status');
  const choices = element('div', '', 'spine-heading-choices');
  const preview = element('pre', '', 'spine-source-preview');
  preview.hidden = true;
  const controls = element('div', '', 'spine-actions');
  let alive = true,
  generation = 0,
  selected = null,
  page = null,
  preparedAction = action,
  pending = false,
  settled = false;
  const fail = error => {
    let outcome;
    try {
      outcome = planFailure(error);
    } catch (invalid) {
      error = invalid;
    }
    if (outcome || error.planUnverified) settled = true;
    message.textContent = outcome?.message || error.message;
    message.classList.add('error');
    if (settled) confirm.disabled = true;
  };
  const confirm = element('button', 'Link this heading', 'primary');
  confirm.type = 'button';
  confirm.onclick = async () => {
    if (!selected || pending || settled) return;
    pending = true;
    confirm.disabled = true;
    const unlock = lockReaderDialog(dialog);
    message.textContent = 'Saving source link…';
    try {
      const submitted = selected;
      const payload = bindingSubmission(project, preparedAction, submitted, section.id);
      const result = await request(preparedAction.http.route, payload);
      requirePlanCompletion(result);
      if (result.operation !== 'bind_source' || result.link_established !== true || result.binding?.section_id !== section.id) {
        settled = true;
        throw Error('The returned source-link outcome could not be matched to this item. Inspect the current plan before another action.');
      }
      settled = true;
      try {
        await onLinked(result);
      } catch (error) {
        fail(Error('Source link saved. The plan view could not refresh: ' + error.message + ' Do not repeat the saved action.'));
        return;
      }
      dialog.close();
    } catch (error) {
      fail(error);
    } finally {
      unlock();
      pending = false;
      confirm.disabled = settled || !selected;
    }
  };
  confirm.disabled = true;
  async function select(row) {
    const ticket = ++ generation;
    selected = null;
    confirm.disabled = true;
    preview.hidden = false;
    preview.textContent = row.heading_before || '';
    pendingRead(message, 'Inspecting the selected source…');
    message.classList.remove('error');
    const observed = await inspectSourceOccurrence(row, project, {
      read: readSource
    });
    if (!alive || ticket !== generation) return;
    const lines = observed.content.split('\n');
    preview.textContent = lines.slice(Math.max(0, row.line - 2), Math.min(lines.length, (row.heading_line_end || row.line) + 5)).join('\n');
    selected = row;
    confirm.disabled = false;
    message.textContent = row.shared_occurrences > 1 ? 'This physical heading is included more than once. The link refers to its shared source.': 'Reader title and purpose will stay unchanged.';
  }
  function appendPage(value) {
    for (const compact of value.headings.items) {
      const row = outlineOccurrence(value, compact);
      const item = button(row.title || row.kind || 'Heading', () => select(row), fail, 'spine-heading-choice');
      item.append(element('small', row.file + ' · line ' + row.line));
      choices.append(item);
    }
    if (!choices.children.length) choices.append(element('p', 'No source headings are available to link. You can add one in the manuscript source.'));
  }
  async function refresh(reinspectPlan = false) {
    ++ generation;
    selected = null;
    confirm.disabled = true;
    preview.hidden = true;
    if (reinspectPlan && refreshAction) preparedAction = await refreshAction();
    page = validateOutline(await request(spineReadURL(preparedAction.choose_from, project)), project);
    if (!alive) return;
    if (reinspectPlan) settled = false;
    choices.replaceChildren();
    appendPage(page);
    more.hidden = !page.headings.next_read;
    message.textContent = 'Choose the physical heading this plan item develops.';
    message.classList.remove('error');
  }
  const more = button('More headings', async () => {
    const next = page?.headings.next_read;
    if (!next) return;
    const value = validateOutline(await request(spineReadURL(next, project)), project);
    if (value.as_of !== page.as_of) throw Error('The outline changed. Refresh before choosing a heading.');
    if (!alive) return;
    page = value;
    appendPage(value);
    more.hidden = !value.headings.next_read;
  }, fail);
  more.hidden = true;
  controls.append(confirm, button('Refresh choices', () => refresh(true), fail), button('Cancel', () => dialog.close(),
  fail));
  dialog.append(title, element('p', section.title, 'spine-reader-title'), message, choices, more, preview, controls);
  dialog.addEventListener('close', () => {
    alive = false;
    ++ generation;
    dialog.remove();
    if (opener?.isConnected) opener.focus({
      preventScroll: true
    });
  });
  showReaderDialog(dialog, opener);
  try {
    await refresh();
  } catch (error) {
    fail(error);
  }
  return dialog;
}
// A narrative beat is named by its authored term; without one its id is shown readable (the res:/def: prefix and
// separators dropped) and the exact id stays inspectable as the control's title (M5 Reader usability).
export function beatLabel(beat) {
  if (beat?.term) return beat.term;
  const id = String(beat?.id || '');
  return id.replace(/^[a-z]+:/, '').replace(/[-_]+/g, ' ').trim() || id;
}
// one owner page of the reader plan: sections and narrative beats requested together
export const READER_PLAN_PAGE = 6;
export async function mountReaderPlan(host, {
  project,
  request,
  initial = {},
  onSource,
  onConcept,
  onEvidence,
  onWork,
  onRead,
  onReview,
  onOccurrence,
  onScope = () => {},
  onChanged = () => {},
  onEdit,
  onCreate,
  onPrepareWork,
  onGenerateProfile,
  readOnly = false,
  status = () => {}
}) {
  styles();
  host.classList.add('reader-plan-home');
  const header = element('header');
  header.append(element('h2', 'Reader plan'), element('p', 'The intended order and purpose for the reader.',
  'muted'));
  const message = element('p', '', 'spine-status');
  message.setAttribute('role', 'status');
  const layout = element('div', '', 'spine-layout');
  const list = element('nav', '', 'spine-plan-list');
  list.setAttribute('aria-label', 'Reader-plan items');
  const detail = element('section', '', 'spine-detail');
  layout.append(list, detail);
  host.replaceChildren(header, message, layout);
  let alive = true,
  version = 0,
  selectedId = initial.sectionId || null,
  beatId = initial.beatId || null;
  let activeRead = initial.readHandle || null;
  let summary = null,
  selected = null,
  selectedBeat = null,
  detailValue = null;
  const fail = error => {
    if (alive) {
      message.textContent = error.message;
      message.classList.add('error');
      status(error.message, true);
    }
  };
  const read = handle => request(spineReadURL(handle, project));
  // the dialogs this plan opened for one item's subject (S2-R1: the G1 acknowledgement): disposed when the
  // plan is destroyed or another item is selected
  const ownedDialogs = new Map();
  const ownDialog = sectionId => dispose => {ownedDialogs.set(dispose, sectionId); return () => ownedDialogs.delete(dispose);};
  const disposeDialogs = (keep = null) => {for (const [dispose, id] of [...ownedDialogs]) if (id !== keep) {ownedDialogs.delete(dispose); dispose();}};
  // THE HUMAN READ IS THE DISPLAY (ACTUAL-C6-DETAIL-BYTES, 2026-10-14): one section's bounded
  // page (projection:display, <= 12,000 B measured) instead of the plain detail (800,724 B on the
  // live project). Every owner-issued single-section detail handle (a list row's detail_read, a
  // save's detail_read, an arrival with paragraph_id) is read as its display; the exact calls open
  // on subject reads when an action opens. A handle that already names a projection, a node or a
  // file selector is read as given.
  const detailHandle = id => readerDisplayHandle(project, id);
  const asDisplay = handle => {
    const payload = handle?.payload;
    if (handle?.operation !== 'structure' || payload?.view !== 'detail' || payload.projection || payload.subject || payload.node_id || payload.node_ids || payload.files || payload.sections || !Array.isArray(payload.section_ids) || payload.section_ids.length !== 1) return handle;
    return readerDisplayHandle(project, payload.section_ids[0], Object.fromEntries(Object.entries(payload).filter(([key]) => !['view', 'section_ids', 'edit_choices', 'http'].includes(key))));
  };
  // a section-level or row-level call acquired on its bounded subject read when the door opens
  const sectionCall = async (sectionId, kind) => {
    const value = await read(readerSubjectRead(project, sectionId, 'section'));
    if (!alive) throw Error('This reader-plan view was closed.');
    const call = readerSubjectAction(value, 'section', {project, sectionId, kind});
    if (!call) throw Error('This plan item no longer offers that action. Refresh the reader plan.');
    return call;
  };
  const structureCall = async (sectionId, paragraphId, kind) => {
    const value = await read(readerSubjectRead(project, sectionId, 'structure', paragraphId));
    if (!alive) throw Error('This reader-plan view was closed.');
    const call = readerSubjectAction(value, 'structure', {project, sectionId, paragraphId, kind});
    if (!call) throw Error('This paragraph plan no longer offers that action. Refresh the reader plan.');
    return call;
  };
  const currentScope = () => selectedBeat ? {
    surface: 'structure',
    label: beatLabel(selectedBeat),
    node_id: selectedBeat.id,
    beat_id: selectedBeat.id,
    section_ids: selectedBeat.section_ids || [],
    ...(structureObservation(detailValue, detailValue.sections || []) ? {
      structure_observation: structureObservation(detailValue, detailValue.sections || [])
    }
    : {})
  }
  : selected ? {
    surface: 'structure',
    label: selected.title,
    section_ids: [selected.id],
    ...(structureObservation(detailValue, [selected]) ? {
      structure_observation: structureObservation(detailValue, [selected])
    }
    : {})
  }
  : {
    surface: 'structure',
    label: 'Reader plan',
    section_ids: []
  };
  function renderList() {
    // Exposition order is numbered; the number is reading order only. Title and purpose
    // are separate lines; the mark is the mechanical source-binding fact, never a guess
    // about support.
    list.replaceChildren(element('h3', 'Sections'));
    // G18 list rows in exposition order with the binding mark; the current marker is the
    // selected section (you-are-here: set on arrival from the manuscript through
    // /concepts/plan/context, otherwise the last-opened section)
    // hierarchy: a row indents under its parent (depth from the loaded parent chain, at most three levels)
    const parents = new Map(summary.sections.items.map(row => [row.id, row.parent_id || null]));
    const depthOf = row => {let depth = 0, at = row.parent_id; while (at && depth < 3) {depth++; at = parents.get(at);} return depth;};
    list.append(orderedPlan(summary.sections.items.map((section, index) => ({
      id: section.id, number: section.number || index + 1, title: section.title || section.id, purpose: section.job || '', depth: depthOf(section),
      owner: project + '::' + section.id,
      // the list row carries the binding mark (precision, status); the correspondence itself is detail
      mark: bindingChip(section.source || {precision: section.precision, status: section.binding_status}), detail_read: section.detail_read
    })), {current: beatId ? null : selectedId, onSelect: item => selectSection(item.id, item.detail_read), onError: fail, control: 'reader-plan:item'}));
    // the selected section may lie beyond the loaded pages (arrival from the manuscript, or a
    // return to a selection made on a later page): its detail above is exact; here it keeps its
    // order context from the owner row's number and total, and More plan items loads toward it
    if (selectedId && !beatId && selected && !summary.sections.items.some(row => row.id === selectedId)) {
      list.append(element('p', 'Selected: ' + (selected.number ? 'Section ' + selected.number + ' of ' + planTotal() + ', ' : '') + (selected.title || selectedId) +
        ' is beyond the loaded plan items. Its detail is exact; More plan items loads toward it.', 'muted spine-offpage'));
    }
    if (summary.sections.next_read) list.append(button('More plan items', async () => {
      const next = await read(summary.sections.next_read);
      if (!alive) return;
      if (next.project !== project || next.as_of !== summary.as_of || !Array.isArray(next.sections?.items)) throw Error('The reader plan changed. Refresh it before continuing.');
      // the owner continuation re-sends every other collection at its first page (next_read is
      // the query plus one offset); only the paged collection is merged, so narrative beats
      // already loaded stay loaded
      summary = {
        ...summary,
        sections: {
          ...next.sections,
          items: [...summary.sections.items, ...next.sections.items]
        }
      };
      renderList();
    }, fail));
    renderSpineList();
  }
  // the plan's true size is the owner's total, never the rows loaded so far
  function planTotal() {return Number.isInteger(summary?.sections?.total) ? summary.sections.total : summary.sections.items.length;}
  function renderSpineList() {
    const page = summary.spine;
    if (!page?.items?.length) return;
    list.append(element('h3', 'Narrative spine'));
    for (const beat of page.items) {
      const control = button(beatLabel(beat), () => selectBeat(beat.id, beat.detail_read), fail);
      control.title = beat.id;
      if (beatId === beat.id) control.setAttribute('aria-current', 'true');
      if (beat.narrative) control.append(element('small', beat.narrative));
      if (!beat.placed) control.append(element('small', 'Not placed in a plan section'));
      list.append(control);
    }
    if (page.next_read) list.append(button('More narrative beats', async () => {
      const next = await read(page.next_read);
      if (!alive) return;
      if (next.project !== project || next.as_of !== summary.as_of || !Array.isArray(next.spine?.items)) throw Error('The narrative spine changed. Refresh before continuing.');
      summary = {
        ...summary,
        spine: {
          ...next.spine,
          items: [...page.items, ...next.spine.items]
        }
      };
      renderList();
    }, fail));
  }
  async function selectBeat(id, handle = {
    operation: 'structure',
    payload: {
      view: 'detail',
      node_id: id
    }
  }) {
    const ticket = ++ version;
    const value = await read(handle);
    if (!alive || ticket !== version) return;
    const beat = value.spine?.find(row => row.id === id);
    if (value.project !== project || !beat) throw Error('This narrative beat is no longer present. Refresh the reader plan.');
    beatId = id;
    selectedBeat = beat;
    selected = null;
    detailValue = value;
    renderList();
    renderBeat();
  }
  function renderBeat() {
    const beat = selectedBeat;
    detail.replaceChildren(element('h3', beatLabel(beat)));
    detail.append(element('p', beat.narrative || 'No connective narrative has been written for this beat.'));
    if (onConcept) detail.append(button('Read argument and evidence', () => onConcept(beat.id, beat.concept_read),
    fail));
    const placements = detailValue.sections || [];
    if (placements.length) {
      detail.append(element('h4', 'Reader-plan sections'));
      for (const section of placements) detail.append(button(section.title || section.id, () => selectSection(section.id),
      fail));
    } else detail.append(element('p', 'This beat has no reader-plan section placement.', 'muted'));
    const actions = element('div', '', 'spine-actions');
    for (const [mode, label] of (readOnly ? [] : [['narrative', 'Edit connective narrative'], ['order', 'Move narrative beat'], ['remove',
    'Remove from narrative spine']])) {
      actions.append(button(label, () => editNarrativeBeat({
        project,
        beat,
        mode,
        request,
        isCurrent: () => alive,
        fullGuardRead: beat.full_guard_read || detailValue.full_guard_read,
        opener: document.activeElement,
        onSaved: async result => {
          await onChanged(result);
          if (mode === 'remove') beatId = null;
          await refresh();
        }
      }), fail));
    }
    detail.append(actions);
    onScope(currentScope());
  }
  async function currentAction() {
    try {return await sectionCall(selectedId, 'link_source');}
    catch (error) {throw /no longer offers/.test(error.message) ? Error('This plan item no longer offers a source-link action. Refresh the reader plan.') : error;}
  }
  function renderDetail() {
    detail.replaceChildren();
    if (!selected) {
      detail.append(element('h3', 'No reader plan yet'), element('p', 'The manuscript outline remains available while you develop a reader plan.',
      'muted'));
      if (onCreate && !readOnly) detail.append(declareControl(button('Create reader-plan item', () => onCreate(summary), fail, 'primary'),'reader-plan:create-item'));
      onScope(currentScope());
      return;
    }
    const section = selected,
    source = section.source || {};
    // The section as an object: its number and title, its purpose, its binding and
    // input chips, and the primary action a reader wants first: go to it in the manuscript.
    const position = summary.sections.items.findIndex(row => row.id === section.id);
    const chips = [bindingChip(source), inputChip(section.reader_transition?.input_currentness || section.paragraph_plan?.input_currentness)].filter(Boolean);
    const sourceReads = source.source_reads || section.source_reads || [];
    const primaryActions = [];
    for (const sourceRead of sourceReads) {
      const file = sourceRead.payload?.files?.[0];
      if (!file || !onSource) continue;
      const precise = source.precision === 'EXACT_HEADING' && source.heading?.file === file;
      const label = precise ? 'Open in manuscript': source.precision === 'INFERRED' ? 'Inspect suggested file': 'Inspect linked file';
      const open = action({label, primary: precise, run: (_button, intent) => onSource({sourceRead, source, file, sectionId: section.id}, intent), onError: fail});
      // the section's source door, whatever its precision (M5-R2): EXACT_HEADING, FILE_ONLY and INFERRED reads
      // are one control whose owner is the section and the file it reads, so a Return finds the same door again
      open.setAttribute('data-control','reader-plan:open-in-manuscript');
      open.setAttribute('data-control-owner', project + '::' + section.id + '::' + file);
      primaryActions.push(open);
    }
    const number = section.number || (position >= 0 ? position + 1 : null);
    // the selected section's heading is the domain's own focus destination (objectHeader focusTarget): where a
    // Return lands when the exact door it left from is not painted again
    const header = objectHeader({eyebrow: number ? 'Section ' + number + ' of ' + planTotal() : 'Reader-plan item',
      title: section.title || section.id, chips, summary: section.job || '', actions: primaryActions, focusTarget: 'reader-plan:' + section.id});
    detail.append(header);
    const binding = element('div', '', 'spine-source-binding');
    binding.append(element('p', source.precision === 'EXACT_HEADING' && source.heading?.title ? 'Source: ' + source.heading.title: bindingLabel(source),
    'spine-link-status'));
    const sourceActions = element('div', '', 'spine-actions');
    if (!readOnly && (section.clearing_action || readerDoor(section, 'link_source'))) {
      let control;
      control = button(source.precision === 'EXACT_HEADING' ? 'Change source link': 'Link source heading', async () => chooseSourceBinding({
        project,
        section,
        action: section.clearing_action || await currentAction(),
        request,
        opener: control,
        refreshAction: currentAction,
        onLinked: async result => {
          await onChanged(result);
          await selectSection(section.id, result.detail_read || result.read_handle || detailHandle(section.id));
          message.textContent = result.changed === false ? 'Source link already current.': 'Source link saved.';
          message.classList.remove('error');
        }
      }), fail, source.precision === 'EXACT_HEADING' || sourceReads.length ? '': 'primary');
      sourceActions.append(control);
    }
    if (!readOnly && (section.prepare_action || readerDoor(section, 'prepare_work')) && onPrepareWork) {
      sourceActions.append(button('Prepare work', async () => onPrepareWork(section.prepare_action || await sectionCall(section.id, 'prepare_work'), section), fail));
      sourceActions.append(element('p', 'Prepare work records a linked Work item for this section; nothing runs until it is started.', 'muted spine-consequence'));
    }
    binding.append(sourceActions);
    if (source.shared_occurrences > 1 || (source.source_orders || source.heading?.source_orders)?.length > 1) binding.append(element('p',
    'This physical heading is used more than once in the document.', 'muted'));
    if (source.precision === 'AMBIGUOUS' || source.precision === 'UNRESOLVED') {
      const explanation = source.reason || source.diagnostics?.[0];
      if (explanation) binding.append(element('p', explanation, 'muted'));
    }
    // Order (READER_TRANSITION_BURIED): the reader's journey through this section comes
    // first, then its immediate relations, then the binding and notes, and the workspace
    // structural profile last as a contextual read.
    const relations = element('div', '', 'spine-relations');
    const nodes = section.nodes || [];
    if (nodes.length) {
      const ideas = element('section');
      ideas.append(element('h4', 'Argument and evidence'));
      for (const node of nodes) {
        const item = element('div', '', 'spine-actions');
        item.append(onConcept && !node.missing && node.status !== 'UNAVAILABLE' ? button(node.label || node.title || node.id,
        () => onConcept(node.id, node.detail_read), fail): element('p', (node.label || node.title || node.id) + (node.missing || node.status === 'UNAVAILABLE' ? ' · unavailable': '')));
        if (!readOnly && !node.missing && node.status !== 'UNAVAILABLE' && !node.beat && !(detailValue.spine || []).some(beat => beat.id === node.id)) item.append(button('Use as narrative beat',
        () => addSectionBeat({
          project,
          sectionId: section.id,
          node,
          request,
          fullGuardRead: detailValue.full_guard_read,
          opener: document.activeElement,
          onSaved: async result => {
            await onChanged(result);
            await refresh();
          }
        }), fail));
        ideas.append(item);
      }
      relations.append(ideas);
    }
    const evidence = section.evidence || detailValue.evidence || [];
    if (evidence.length && onEvidence) {
      const results = element('section');
      results.append(element('h4', 'Related evidence'));
      for (const item of evidence) results.append(button(item.title || item.label || item.id, () => onEvidence(item.id,
      item.read_handle || item.detail_read), fail));
      relations.append(results);
    }
    const work = section.work || section.tasks || [];
    if (work.length && onWork) {
      const tasks = element('section');
      tasks.append(element('h4', 'Related work'));
      for (const item of work) tasks.append(button(item.title || item.id, () => onWork(item.id, item.read_handle || item.detail_read),
      fail));
      relations.append(tasks);
    }
    // the structural prior: carried by the plain detail; on the display it is a deliberate read of
    // the workspace profile (view:architecture-profile), never part of the page's cost
    const prior = section.reader_inputs?.architecture_prior;
    const priorRead = !prior && detailValue.projection === 'display' ? {operation: 'structure', payload: {view: 'architecture-profile'}} : null;
    const priorSection = prior && prior.family === 'architecture' || priorRead ? lazySection({label: 'Structural preferences (workspace profile)', load: async () => prior || read(priorRead), render: (body, value) => renderArchitecturePrior(body, value, {
      onInspect: value => inspectArchitecturePrior({
        value,
        read,
        ...(!readOnly?{project,request,onGenerate:onGenerateProfile,onChanged:async result=>{
          await onChanged(result);
          if(alive&&selected?.id===section.id)await selectSection(section.id,detailHandle(section.id));
        }}:{}),
        opener: document.activeElement,
        isCurrent: () => alive
      }),
      onError: fail
    })}) : null;
    const editMetadata = async (value, paragraph = undefined) => {
      const isContract = paragraph === undefined;
      const subject = isContract ? 'contract' : paragraph ? 'paragraph' : 'create';
      // the exact call with its descriptors and choices: carried by the plain detail, else ONE
      // bounded subject read with edit_choices when the door opens (never the whole detail)
      const acquire = async () => {
        const value_ = await read(readerSubjectRead(project, section.id, subject, paragraph?.paragraph_id || null, {choices: true}));
        if (!alive) throw Error('This reader-plan view was closed.');
        const call = readerSubjectAction(value_, subject, {project, sectionId: section.id, paragraphId: paragraph?.paragraph_id || null});
        if (!call) throw Error('This plan item no longer offers that edit. Refresh the reader plan.');
        return call;
      };
      const action = (isContract ? value.edit_action: paragraph?.edit_action || value.create_action) || await acquire();
      const inspectAction = async prepared => {
        const latest = await read(prepared.choices_read || paragraph?.read_handle || value.read_handle || detailHandle(section.id));
        if (latest?.schema_version === 'laplace.project-structure-guard/1') return readerSubjectAction(latest, latest.subject, {project, sectionId: section.id, paragraphId: prepared.payload.paragraph_id || null});
        const current = latest.sections?.find(row => row.id === section.id);
        if (!current) throw Error('This reader-plan section no longer exists. Your draft is retained.');
        if (prepared.payload.operation === 'section_contract') return current.reader_transition?.edit_action;
        if (prepared.payload.create) return current.paragraph_plan?.create_action;
        const entry = current.paragraph_plan?.paragraphs?.items.find(row => row.paragraph_id === prepared.payload.paragraph_id);
        if (!entry) throw Error('The original planned unit is unavailable. Its retained draft remains available.');
        return entry.edit_action;
      };
      return editReaderMetadata({
        project,
        action,
        loadChoices: inspectAction,
        title: isContract ? 'Reader transition': paragraph ? 'Paragraph plan': 'Add paragraph plan',
        request,
        opener: document.activeElement,
        inspectCurrent: () => inspectAction(action),
        onSaved: async result => {
          await onChanged(result);
          await selectSection(section.id, result.detail_read || result.read_handle || detailHandle(section.id));
        }
      });
    };
    renderReaderState(detail, {
      section, project,
      onInspectLatestStructure:readOnly?null:retained=>{
        let ticket=version,inspectedSection=section;
        return openRecordedRestructure({project,retained,request,onRead,opener:document.activeElement,isCurrent:()=>alive,onSaved:async result=>{
          await onChanged(result);
          if(!alive||version!==ticket||selected!==inspectedSection)return;
          const refreshedVersion=version+1;
          await selectSection(section.id,result.detail_read||detailHandle(section.id));
          if(alive&&version===refreshedVersion&&selected?.id===section.id){ticket=version;inspectedSection=selected;}
        }});
      },
      onRecoverStructure:readOnly ? null : async(action, retained) => {
        const ticket = version;
        const submission = restructureFollowThroughSubmission(action, project, retained);
        let result;
        try {result = await request(submission.url, submission.payload);}
        catch (error) {if(error.result?.schema_version !== 'laplace.paragraph-restructure/1')throw error;result=error.result;}
        validateRestructureEffect(result, {project, prior:retained});
        await onChanged(result);
        if (!alive || version !== ticket || selected !== section) return result;
        await selectSection(section.id, result.detail_read || detailHandle(section.id));
      },
      onInspectReconciliation:readOnly?null:(handle,retained)=>{
        const ticket=version;
        return openMetadataReconciliation({project,handle,retained,request,onRead,opener:document.activeElement,isCurrent:()=>alive,
          onSaved:async result=>{await onChanged(result);if(alive&&version===ticket&&selected===section)await selectSection(section.id,result.detail_read||detailHandle(section.id));}});
      },
      onRead,
      onExpandParagraph: async (paragraph, rowRead = null) => {
        // a display list row's whole read is the owner's row_read with only its paragraph_id put in
        // (repair3 R2); a template that is not this section's display row read is refused, not guessed
        const sameSection = payload => Array.isArray(payload?.section_ids) && payload.section_ids.length === 1 && payload.section_ids[0] === section.id;
        if (rowRead && (rowRead.operation !== 'structure' || rowRead.payload?.projection !== 'display' || rowRead.payload?.paragraph_id !== '<paragraph_id>' || !sameSection(rowRead.payload)))
          throw Error('This paragraph plan offers no whole read for this section. Refresh the reader plan.');
        const handle = rowRead ? {...rowRead, payload: {...rowRead.payload, paragraph_id: paragraph.paragraph_id}}
          : paragraph.read_handle || readerDisplayHandle(project, section.id, {paragraph_id: paragraph.paragraph_id});
        const latest = await read(handle);
        if (!alive) return null;
        const latestSection = latest.sections?.find(row => row.id === section.id);
        const whole = latestSection?.paragraph_plan?.paragraphs?.items?.find(row => row.paragraph_id === paragraph.paragraph_id);
        if (latest.project !== project || !whole) throw Error('This paragraph plan is no longer present. Refresh the reader plan.');
        // the whole row must be the plan this page shows: a newer plan is not painted into an older page
        const shownCut = section.paragraph_plan?.revision;
        if (shownCut && latestSection.paragraph_plan?.revision !== shownCut) throw Error('The paragraph plan changed since this page was read. Refresh the reader plan to read its current text.');
        return whole;
      },
      // the reader transition's full authored text: the owner's values_read (the contract subject),
      // admitted only for this project, section and the transition revision shown; read only, so the
      // returned values carry no call and no editor draft or basis is touched (repair3 R2)
      onReadTransition: async transition => {
        const handle = transition.values_read, payload = handle?.payload;
        if (handle?.operation !== 'structure' || payload?.subject !== 'contract' || payload?.projection !== 'guard' || !Array.isArray(payload.section_ids) || payload.section_ids.length !== 1 || payload.section_ids[0] !== section.id)
          throw Error('This reader transition offers no full read for this section. Refresh the reader plan.');
        const value = await read(handle);
        if (!alive) return null;
        const owner = value?.reader_transition, values = owner?.edit_action?.values;
        if (value?.project !== project || value.section_id !== section.id || value.subject !== 'contract' || owner?.section_id !== section.id || !values || typeof values !== 'object')
          throw Error('The reader transition is no longer present. Refresh the reader plan.');
        if (owner.revision !== transition.revision || owner.subject_revision !== transition.subject_revision)
          throw Error('The reader transition changed since this page was read. Refresh the reader plan to read its current text.');
        return structuredClone(values);
      },
      onLogicalRestructure:readOnly?null:async(prepared,kind,paragraph,plan)=>{
        const ticket=version;
        const action=prepared||await structureCall(section.id,paragraph.paragraph_id,kind==='logical-split'?'split':'merge');
        return openLogicalRestructure({project,action,kind,paragraph,plan,request,read,onRead,opener:document.activeElement,
          isCurrent:()=>alive,onSaved:async result=>{
            await onChanged(result);
            if(alive&&version===ticket&&selected===section)await selectSection(section.id,result.detail_read||detailHandle(section.id));
          }});
      },
      onError: fail,
      onReview: readOnly || !onReview ? null : async (prepared, subject) => onReview(prepared || (subject?.paragraph_id ? await structureCall(section.id, subject.paragraph_id, 'review') : await sectionCall(section.id, 'review')), subject),
      onOccurrence,
      onEditContract: readOnly ? null : value => editMetadata(value),
      // G1: one bounded guard read of the exact subject; its edit call carries the pins the human records
      onAcknowledgeInputs: readOnly ? null : (value, paragraph = null) => acknowledgeReaderInputs({
        project, request, opener: document.activeElement, isCurrent: () => alive && selected?.id === section.id, own: ownDialog(section.id),
        title: paragraph ? 'Paragraph plan ' + (paragraph.label || paragraph.paragraph_id) : 'Reader transition of ' + (section.title || section.id),
        acquire: async () => {
          const subject = paragraph ? 'paragraph' : 'contract', paragraphId = paragraph?.paragraph_id || null;
          const handle = readerSubjectRead(project, section.id, subject, paragraphId), guard = await read(handle);
          if (!alive) throw Error('This reader-plan view was closed.');
          const call = readerSubjectAction(guard, subject, {project, sectionId: section.id, paragraphId});
          if (!call) throw Error('This plan item no longer offers an exact edit call. Refresh the reader plan.');
          return {action: call, currentness: (paragraph ? guard.paragraph : guard.reader_transition)?.input_currentness, read: handle};
        },
        onSaved: async result => {
          const ticket = version;
          await onChanged(result);
          if (alive && version === ticket && selected?.id === section.id) await selectSection(section.id, result.detail_read || detailHandle(section.id));
        }
      }),
      onEditParagraph: readOnly ? null : (value, paragraph) => editMetadata(value, paragraph),
      onParagraphAction: readOnly ? null : async (action, paragraph, kind) => changeReaderParagraph({
        project,
        action: await freshParagraphAction(section.id, action, paragraph, kind),
        paragraph,
        request,
        opener: document.activeElement,
        onSaved: async result => {
          await onChanged(result);
          await selectSection(section.id, result.detail_read || result.read_handle || detailHandle(section.id));
        }
      }),
      onMoreParagraphs: async handle => {
        const previous = section.paragraph_plan,
        latest = await read(handle);
        if (!alive) return;
        const current = latest.sections?.find(row => row.id === section.id)?.paragraph_plan;
        if (latest.project !== project || !current || current.revision !== previous.revision) throw Error('The paragraph plan changed. Refresh before continuing.');
        selected = latest.sections.find(row => row.id === section.id);
        detailValue = latest;
        renderDetail();
      }
    });
    // the section's argument, evidence and work are context for planning, one disclosure away (not the primary surface)
    if (relations.children.length) {
      const count = nodes.length + (onEvidence ? evidence.length : 0) + (onWork ? work.length : 0);
      const context = element('details', '', 'spine-relations-context');
      context.append(element('summary', 'Argument, evidence and work (' + count + ')'), relations);
      detail.append(context);
    }
    // THE RELATION MAP (C6): section <-> source heading, argument nodes, evidence and work,
    // from this detail read alone (no extra read), drawn and listed by workspace-topology.
    const mapSection = lazySection({label: 'Show relation map', hideLabel: 'Hide relation map', cls: 'spine-relation-map',
      load: async () => readerRelationTopology(section, detailValue, project),
      render: (body, topology) => {mountTopology(body, {title: 'Relations of this section', legend: 'The section is bound to its source heading, argues its planned objects, is supported by their evidence and tracked by related work. Every edge comes from the detail read.',
        ...topology, selected: 'section:' + section.id, listOnly: (globalThis.innerWidth || 1280) < 1000, ariaLabel: 'Reader-plan relations',
        onSelect: (id, node) => {if (node?.kind === 'argument' && onConcept) return onConcept(node.ref, node.detail_read); if (node?.kind === 'evidence' && onEvidence) return onEvidence(node.ref, node.detail_read); if (node?.kind === 'work' && onWork) return onWork(node.ref, node.detail_read); if (node?.kind === 'source' && sourceReads[0] && onSource) return onSource({sourceRead: sourceReads[0], source, file: sourceReads[0].payload?.files?.[0], sectionId: section.id});}});}});
    mapSection.querySelector?.('.lazy-toggle')?.setAttribute('data-control','reader-plan:relation-map');
    detail.append(mapSection);
    detail.append(binding);
    if (section.notes) detail.append(lazySection({label: 'Author notes', load: async () => section.notes, render: (body, notes) => {body.append(element('p', notes, 'outline-notes'));}}));
    if (priorSection) detail.append(priorSection);
    if (detailValue.spine?.length) {
      const beats = element('section');
      beats.append(element('h4', 'Narrative beats'));
      for (const beat of detailValue.spine) {const control = button(beatLabel(beat), () => selectBeat(beat.id, beat.detail_read), fail); control.title = beat.id; beats.append(control);}
      detail.append(beats);
    } else if (detailValue.spine_page?.total && detailValue.spine_page.read) {
      // ACTUAL-C1011-DISPLAY-BYTES: the beats are read when opened, one compact page at a time, each
      // page admitted only for this project and section and BOTH cuts this page was read at: the
      // spine revision (beat order and narrative) and the plan revision (which beats this section
      // holds; RELEASE-SPINE-PLAN-CUT). A mismatch is refused in words; rows already shown and their
      // continuation stay, and Refresh reads the current page.
      const shown = detailValue, page = shown.spine_page, beatsAt = shown.structure_observation?.spine_revision, planAt = shown.structure_observation?.plan_revision;
      const beatRead = id => page.row_read?.operation === 'structure' && page.row_read.payload?.node_id === '<id>'
        ? {...page.row_read, payload: {...page.row_read.payload, node_id: id}} : undefined;
      const readPage = async (handle, offset) => {
        const value = await read(handle);
        if (!alive) throw Error('This reader-plan view was closed.');
        if (value.project !== project || value.section_id !== section.id || value.page !== 'spine' || !Array.isArray(value.spine) || value.spine_page?.offset !== offset)
          throw Error('These narrative beats belong to another reader-plan item. Refresh the reader plan.');
        if (beatsAt && value.structure_observation?.spine_revision !== beatsAt) throw Error('The narrative spine changed since this page was read. Refresh the reader plan.');
        if (planAt && value.structure_observation?.plan_revision !== planAt) throw Error('This section\'s beats changed since this page was read. Refresh the reader plan.');
        return value;
      };
      const beats = lazySection({label: 'Narrative beats (' + page.total + ')', hideLabel: 'Hide narrative beats', cls: 'spine-beats',
        load: () => readPage(page.read, 0),
        render: (body, first) => {
          const list = element('div', '', 'spine-actions');
          const more = value => {
            for (const beat of value.spine) {const control = button(beatLabel(beat), () => selectBeat(beat.id, beatRead(beat.id)), fail); control.title = beat.id; list.append(control);}
            const next = value.spine_page.next_read;
            if (!next) return;
            const after = value.spine_page.offset + value.spine.length;
            const door = button('More narrative beats (' + (value.spine_page.total - after) + ' more)', async () => {more(await readPage(next, after)); door.remove();}, fail);
            list.append(door);
          };
          body.append(list); more(first);
        }});
      detail.append(beats);
    }
    const itemActions = element('div', '', 'spine-actions spine-item-actions');
    if (!readOnly) itemActions.append(element('p', 'Editing or moving this item changes the reader plan only; the manuscript source is not rewritten.', 'muted spine-consequence'));
    if (onEdit && !readOnly) itemActions.append(button('Edit reader-plan item', () => onEdit(section, detailValue), fail));
    if (!readOnly) itemActions.append(button('Move reader-plan item', () => moveReaderPlanItem({
      project,
      section,
      request,
      fullGuardRead: detailValue.full_guard_read,
      opener: document.activeElement,
      onSaved: async result => {
        await onChanged(result);
        await refresh();
      }
    }), fail));
    if (itemActions.children.length) detail.append(itemActions);
    onScope(currentScope());
  }
  // The exact call for a paragraph action, re-read on its bounded subject at open time; a
  // read that fails keeps the call the detail delivered (the owner still guards it).
  async function freshParagraphAction(sectionId, action, paragraph, kind = action?.payload?.action) {
    const subject = kind === 'reorder' ? 'reorder' : kind === 'remove' ? 'paragraph' : null;
    if (!subject) return action;
    try {
      const value = await read(readerSubjectRead(project, sectionId, subject, subject === 'paragraph' ? paragraph.paragraph_id : null));
      if (!alive) return action;
      return readerSubjectAction(value, subject, {project, sectionId, paragraphId: paragraph.paragraph_id, kind: 'remove'}) || action;
    } catch (error) {
      // the detail delivered the call: it stands (the owner still guards it); a display door has no
      // call to fall back on, so the failed subject read is the outcome
      if (action && !/different guard subject|different paragraph/.test(error.message)) return action;
      throw error;
    }
  }
  async function selectSection(id, handle = detailHandle(id)) {
    const ticket = ++ version;
    handle = asDisplay(handle);
    const value = await read(handle);
    if (!alive || ticket !== version) return;
    if (value.project !== project || !Array.isArray(value.sections)) throw Error('The reader-plan detail returned a different owner.');
    const row = value.sections.find(section => section.id === id);
    if (!row) throw Error('This reader-plan item is no longer available. Refresh the plan; the prior selection is retained.');
    message.textContent = '';
    message.classList.remove('error');
    disposeDialogs(id);
    activeRead = handle;
    selectedId = id;
    beatId = null;
    selectedBeat = null;
    selected = row;
    detailValue = value;
    renderList();
    renderDetail();
    return row;
  }
  async function refresh() {
    const ticket = ++ version;
    // THE FIRST PAGE (journey I, Sol C6-I 2026-10-14): one useful owner page of sections and
    // narrative beats; the live 16-section edition measures 8,380 B at 6+6 against the 10,000 B
    // journey budget, where 40 rows measured 15,649 B. Later pages come only through the owner's
    // exact as_of continuation (More plan items / More narrative beats); the complete order and
    // the relation map remain deliberate reads (the full detail, the relation map disclosure).
    const value = await read({
      operation: 'structure',
      payload: {
        view: 'summary',
        section_limit: READER_PLAN_PAGE,
        spine_limit: READER_PLAN_PAGE,
        object_limit: 1,
        gap_limit: 1
      }
    });
    if (!alive || ticket !== version) return;
    if (value.project !== project || value.schema_version !== 'laplace.project-structure-summary/2' || !Array.isArray(value.sections?.items)) throw Error('The reader plan returned an incompatible summary.');
    summary = value;
    renderList();
    if (beatId) await selectBeat(beatId);
    else if (selectedId || value.sections.items.length) {
      const id = selectedId || value.sections.items[0].id;
      const focused = activeRead?.payload?.paragraph_id ? {
        operation: 'structure',
        payload: {
          view: 'detail',
          section_ids: [id],
          paragraph_id: activeRead.payload.paragraph_id
        }
      }
      : activeRead;
      await selectSection(id, focused || detailHandle(id));
    } else {
      selected = null;
      detailValue = null;
      renderDetail();
    }
    message.textContent = '';
    message.classList.remove('error');
  }
  header.append(declareControl(button('Refresh reader plan', refresh, fail),'reader-plan:refresh'));
  const ready = refresh().catch (fail);
  await ready;
  return {
    ready,
    refresh,
    select: selectSection,
    context: currentScope,
    capture: () => ({
      sectionId: selectedId,
      readHandle: activeRead,
      beatId
    }),
    destroy: () => {
      alive = false;
      ++ version;
      disposeDialogs();
    }
  };
}
// One owner-derived node/edge array for a section's relations: the section, its bound source
// heading (precision from the correspondence), the argument objects it places, the evidence
// bound to them and the related work. Typed edges only; nothing is inferred.
export function readerRelationTopology(section, detailValue = {}, project = '') {
  const sectionNode = {id: 'section:' + section.id, title: section.title || section.id, kind: 'section'};
  const nodes = [sectionNode], edges = [];
  const source = section.source || {};
  if (source.heading?.title || source.source_files?.length) {
    const file = source.heading?.file || source.source_files?.[0];
    nodes.push({id: 'source:' + (file || section.id), title: source.heading?.title || file || 'Source', kind: 'source', precision: source.precision});
    edges.push({kind: 'bound-to', source: sectionNode.id, target: 'source:' + (file || section.id)});
  }
  for (const node of section.nodes || []) {
    if (!node?.id) continue;
    nodes.push({id: 'argument:' + node.id, title: node.label || node.title || node.id, kind: 'argument', ref: node.id, detail_read: node.detail_read, missing: !!node.missing});
    edges.push({kind: 'argues', source: sectionNode.id, target: 'argument:' + node.id});
  }
  for (const item of section.evidence || detailValue.evidence || []) {
    if (!item?.id) continue;
    const owner = item.node_id && nodes.some(row => row.id === 'argument:' + item.node_id) ? 'argument:' + item.node_id : sectionNode.id;
    nodes.push({id: 'evidence:' + item.id, title: item.title || item.label || item.id, kind: 'evidence', ref: item.id, detail_read: item.read_handle || item.detail_read});
    edges.push({kind: 'supported-by', source: owner, target: 'evidence:' + item.id});
  }
  for (const item of section.work || section.tasks || []) {
    if (!item?.id) continue;
    nodes.push({id: 'work:' + item.id, title: item.title || item.id, kind: 'work', ref: item.id, detail_read: item.read_handle || item.detail_read});
    edges.push({kind: 'tracked-by', source: sectionNode.id, target: 'work:' + item.id});
  }
  return {nodes, edges, boundaries: [], hints: {rank: Object.fromEntries(nodes.map(node => [node.id, node.kind === 'source' ? 0 : node.kind === 'section' ? 1 : node.kind === 'argument' ? 2 : 3]))}};
}
const itemValues = item => ({
  title: item?.title || '',
  job: item?.job || '',
  notes: item?.notes || '',
  kind: item?.kind || 'section',
  parent_id: item?.parent_id || ''
});
export function readerPlanItemOps(item, values) {
  const before = itemValues(item),
  after = {
    ...values,
    title: String(values.title || '').trim()
  };
  const ops = [];
  if (after.kind !== before.kind || after.parent_id !== before.parent_id) ops.push({
    kind: 'set-outline',
    section: item.id,
    outline_kind: after.kind,
    parent_id: after.parent_id || null
  });
  for (const [field, kind] of[['title', 'retitle'], ['job', 'edit-job'], ['notes', 'edit-notes']]) {
    if (after[field] !== before[field]) ops.push({
      kind,
      section: item.id,
      [field]: after[field]
    });
  }
  return ops;
}
// THE PLAN GUARD (2026-10-14): the plan-level editors need the complete plan order, the narrative
// spine and the mutation revision, which view:plan carries without the hydrated structure
// (view:full measured 302,953-316,437 B on the live project). A full-structure handle the owner
// published for this purpose is read as the plan guard: the `revision` is the same `plan` home
// token, so a changed plan still refuses at the owner.
export function planGuardHandle(handle) {
  if (handle?.operation === 'structure' && handle.payload && !['full', 'plan'].includes(handle.payload.view)) return handle;
  return {operation: 'structure', payload: {view: 'plan'}};
}
export async function editReaderPlanItem({
  project,
  section = null,
  fullGuardRead,
  request,
  onSaved = async () => {},
  opener,
  storage = globalThis.sessionStorage,
  isCurrent = () => true
}) {
  styles();
  const key = 'laplace:reader-plan-draft:' + JSON.stringify([project, section?.id || null]);
  let settled = false;
  const guardRead = planGuardHandle(fullGuardRead);
  let current = await request(spineReadURL(guardRead, project));
  if (!isCurrent()) return null;
  if (current.project !== project || !pin(current.revision)) throw Error('The plan owner returned no original mutation basis.');
  let base = section ? current.sections?.find(row => row.id === section.id): null;
  if (section && !base) throw Error('This plan item no longer exists. Refresh the reader plan.');
  let guard = current.revision,
  sourceRevision = current.selected_source?.revision;
  let values = itemValues(base),
  restored = false;
  try {
    const saved = JSON.parse(storage?.getItem(key) || 'null');
    if (saved?.project === project && saved.section_id === (section?.id || null) && pin(saved.guard)) {
      base = saved.base;
      guard = saved.guard;
      sourceRevision = saved.sourceRevision;
      values = saved.values;
      restored = true;
    }
  } catch {
    /* The current owner read remains available if the local cache is absent. */
  }
  const dialog = element('dialog', '', 'spine-binding-dialog');
  dialog.append(element('h2', section ? 'Edit reader-plan item': 'Create reader-plan item'));
  const message = element('p', restored ? 'Your draft and its original plan basis are retained.': '', 'spine-status');
  message.setAttribute('role', 'status');
  const form = element('form', '', 'work-form'),
  inputs = {};
  for (const [name, label, multiline] of[['title', 'Title', false], ['job', 'Purpose of this plan item', true],
  ['notes', 'Working notes', true]]) {
    const wrapper = element('label', label),
    input = element(multiline ? 'textarea': 'input');
    input.value = values[name];
    labelReaderControl(wrapper, input, label);
    input.name = name;
    input.required = name === 'title';
    inputs[name] = input;
    wrapper.append(input);
    form.append(wrapper);
  }
  const more = element('details');
  more.append(element('summary', 'Level and containing item'));
  for (const [name, label, options] of[['kind', 'Level', ['part', 'chapter', 'section', 'subsection', 'subsubsection'].map(value => [value,
  value])], ['parent_id', 'Within', [['', 'Reader plan'], ...(current.sections || []).filter(row => row.id !== section?.id && !row.ancestor_ids?.includes(section?.id)).map(row => [row.id,
  row.title])]]]) {
    const wrapper = element('label', label),
    input = element('select');
    input.name = name;
    labelReaderControl(wrapper, input, label);
    for (const [value, label] of options) {
      const option = element('option', label);
      option.value = value;
      input.append(option);
    }
    input.value = values[name];
    inputs[name] = input;
    wrapper.append(input);
    more.append(wrapper);
  }
  form.append(more);
  const readValues = () => Object.fromEntries(Object.entries(inputs).map(([key, input]) => [key, input.value]));
  const persist = () => {
    values = readValues();
    try {
      storage?.setItem(key, JSON.stringify({
        project,
        section_id: section?.id || null,
        base,
        guard,
        sourceRevision,
        values
      }));
    } catch {
      message.textContent = 'The draft is retained in this open editor; local storage is unavailable.';
    }
  };
  form.oninput = persist;
  const inspection = element('div');
  const inspect = button('Inspect current plan', async () => {
    persist();
    const fresh = await request(spineReadURL(guardRead, project));
    if (fresh.project !== project || !pin(fresh.revision)) throw Error('The current plan basis is unavailable.');
    const item = section ? fresh.sections?.find(row => row.id === section.id): null;
    if (section && !item) throw Error('The saved plan item was removed. Your draft is retained for copying.');
    inspection.replaceChildren(element('h3', 'Current saved values'));
    const facts = element('dl');
    for (const [name, label] of[['title', 'Title'], ['job', 'Purpose'], ['notes', 'Working notes'], ['kind', 'Level'],
    ['parent_id', 'Within']]) {
      facts.append(element('dt', label), element('dd', itemValues(item) [name] || 'Not set'));
    }
    inspection.append(facts);
    inspection.append(button('Use this inspected plan basis', () => {
      const old = itemValues(base),
      changed = Object.fromEntries(Object.entries(values).filter(([key, value]) => value !== old[key]));
      base = item;
      current = fresh;
      guard = fresh.revision;
      sourceRevision = fresh.selected_source?.revision;
      settled = false;
      save.disabled = false;
      values = {
        ...itemValues(item),
        ...changed
      };
      for (const [name, input] of Object.entries(inputs)) input.value = values[name];
      persist();
      inspection.replaceChildren();
      message.textContent = 'Inspected basis selected. Your changed fields are retained; review them before saving.';
    }, fail));
  }, fail);
  const save = element('button', 'Save reader-plan item', 'primary');
  save.type = 'submit';
  const actions = element('div', '', 'spine-actions');
  actions.append(save, inspect, button('Close', () => dialog.close(), fail));
  form.append(actions);
  function fail(error) {
    let outcome;
    try {
      outcome = planFailure(error);
    } catch (invalid) {
      error = invalid;
    }
    if (outcome || error.planUnverified) settled = true;
    message.textContent = outcome?.message || error.message;
    message.classList.add('error');
  }
  let saving = false;
  form.onsubmit = async event => {
    event.preventDefault();
    if (saving || settled) return;
    persist();
    if (!values.title.trim()) {
      fail(Error('Give the plan item a title.'));
      return;
    }
    saving = true;
    save.disabled = true;
    const unlock = lockReaderDialog(dialog);
    message.textContent = 'Saving…';
    try {
      let payload;
      const slug = values.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 65);
      const id = section?.id || (slug && (/^[a-z]/.test(slug) ? slug: 'section-' + slug));
      if (!id) throw Error('Use a title with a letter or number.');
      if (section) {
        const ops = readerPlanItemOps(base, values);
        if (!ops.length) {
          storage?.removeItem(key);
          dialog.close();
          return;
        }
        payload = {
          project,
          operation: 'plan',
          expected_revision: guard,
          ops
        };
      } else if (!current.authority?.plan_path || current.status === 'MISSING') {
        payload = {
          project,
          operation: 'initialize',
          expected_revision: guard,
          expected_source_revision: sourceRevision,
          sections: [{
            id,
            title: values.title.trim(),
            kind: values.kind,
            parent_id: values.parent_id || null,
            job: values.job,
            notes: values.notes
          }]
        };
      } else {
        payload = {
          project,
          operation: 'plan',
          expected_revision: guard,
          ops: [{
            kind: 'add-section',
            section: id,
            title: values.title.trim(),
            outline_kind: values.kind,
            parent_id: values.parent_id || null
          }, ...(values.job ? [{
            kind: 'edit-job',
            section: id,
            job: values.job
          }]: []), ...(values.notes ? [{
            kind: 'edit-notes',
            section: id,
            notes: values.notes
          }]: [])]
        };
      }
      const result = await request('/work/structure/change', payload);
      requirePlanCompletion(result);
      if (result.ok !== true) throw Error('The reader-plan change was not acknowledged. Your draft is retained.');
      settled = true;
      try {
        storage?.removeItem(key);
      } catch (error) {
        fail(Error('Reader plan saved. Local draft cleanup is unavailable; the retained cache is historical.'));
      }
      try {
        await onSaved(result, id);
      } catch (error) {
        fail(Error('Reader plan saved. Its view could not refresh: ' + error.message + ' Do not repeat the saved action.'));
        save.disabled = true;
        return;
      }
      dialog.close();
    } catch (error) {
      fail(error);
    } finally {
      unlock();
      saving = false;
      if (dialog.open) save.disabled = settled;
    }
  };
  dialog.append(message, form, inspection);
  dialog.addEventListener('close', () => {
    dialog.remove();
    if (opener?.isConnected) opener.focus({
      preventScroll: true
    });
  });
  showReaderDialog(dialog, opener);
  inputs.title.focus();
  return dialog;
}
export function narrativeBeatOperation(full, beatId, mode, value) {
  if (!pin(full?.revision) || !Array.isArray(full.spine)) throw Error('The complete narrative order and original guard are required.');
  const beat = full.spine.find(row => row.id === beatId);
  if (!beat) throw Error('This beat is no longer in the narrative spine. Refresh it before editing.');
  if (mode === 'narrative') return String(value) === (beat.narrative || '') ? null: {
    kind: 'set-narrative',
    node: beatId,
    narrative: String(value)
  };
  if (mode === 'remove') return {
    kind: 'unset-spine',
    node: beatId
  };
  if (mode !== 'order' || !Number.isInteger(value) || value < 0 || value >= full.spine.length) throw Error('Choose a position in the complete narrative order.');
  const order = full.spine.map(row => row.id);
  if (new Set(order).size !== order.length) throw Error('The narrative owner returned duplicate beat identities.');
  const previous = order.indexOf(beatId);
  if (previous === value) return null;
  order.splice(previous, 1);
  order.splice(value, 0, beatId);
  return {
    kind: 'reorder-spine',
    order
  };
}
// Each confirmation is one existing guarded spine operation. Reordering uses
// the full observed membership, never the visible summary page or section IDs.
export async function editNarrativeBeat({
  project,
  beat,
  mode,
  request,
  fullGuardRead,
  onSaved = async () => {},
  opener,
  storage = globalThis.sessionStorage,
  isCurrent = () => true
}) {
  const handle = planGuardHandle(fullGuardRead);
  const current = await request(spineReadURL(handle, project));
  if (!isCurrent()) return null;
  if (current.project !== project) throw Error('The narrative read belongs to another project.');
  const original = current.spine?.find(row => row.id === beat.id);
  if (!original) throw Error('This beat is no longer in the narrative spine.');
  const key = 'laplace:spine-draft:' + JSON.stringify([project, beat.id, mode]);
  let base = current,
  held = false,
  pending = false;
  const dialog = element('dialog', '', 'spine-binding-dialog');
  dialog.append(element('h2', mode === 'narrative' ? 'Connective narrative': mode === 'order' ? 'Move narrative beat': 'Remove narrative beat'),
  element('p', beat.term || beat.id));
  const message = element('p', '', 'spine-status');
  message.setAttribute('role', 'status');
  let input;
  if (mode === 'narrative') {
    input = element('textarea');
    input.rows = 6;
    input.value = original.narrative || '';
    input.setAttribute('aria-label', 'How this beat advances the reader’s journey');
    try {
      const saved = JSON.parse(storage?.getItem(key) || 'null');
      if (saved?.project === project && saved.beat_id === beat.id && pin(saved.base?.revision)) {
        base = saved.base;
        input.value = saved.text;
        message.textContent = 'Your narrative draft and original basis are retained.';
      }
    } catch {
      /* A missing local draft does not replace the owner read. */
    }
    input.oninput = () => {
      try {
        storage?.setItem(key, JSON.stringify({
          project,
          beat_id: beat.id,
          base: {
            project,
            revision: base.revision,
            spine: base.spine.filter(row => row.id === beat.id)
          },
          text: input.value
        }));
      } catch {
        message.textContent = 'Your draft remains in this editor; local storage is unavailable.';
      }
    };
    dialog.append(input);
  } else if (mode === 'order') {
    input = element('select');
    input.setAttribute('aria-label', 'New narrative position');
    current.spine.forEach((row, index) => {
      const option = element('option', `${index + 1} · ${row.term || row.id}`);
      option.value = String(index);
      input.append(option);
    });
    input.value = String(current.spine.findIndex(row => row.id === beat.id));
    dialog.append(input);
  } else dialog.append(element('p', 'The argument object and its evidence remain. This removes only its membership of the narrative spine.'));
  const actions = element('div', '', 'spine-actions');
  const fail = error => {
    let effect;
    try {
      effect = planFailure(error);
    } catch (invalid) {
      error = invalid;
    }
    held = held || !!effect || !!error.planUnverified;
    message.textContent = effect?.message || error.message;
    message.classList.add('error');
  };
  const save = button(mode === 'remove' ? 'Remove beat': 'Save narrative change', async () => {
    if (held || pending) return;
    const op = narrativeBeatOperation(base, beat.id, mode, mode === 'order' ? Number(input.value): input?.value);
    if (!op) {
      message.textContent = 'No narrative changes.';
      return;
    }
    pending = true;
    try {
      const result = await request('/work/structure/change', {
        project,
        operation: 'spine',
        op,
        expected_revision: base.revision
      });
      requirePlanCompletion(result);
      held = true;
      try {
        storage?.removeItem(key);
      } catch {
        /* The confirmed owner outcome remains authoritative. */
      }
      try {
        await onSaved(result);
        dialog.close();
      } catch (error) {
        message.textContent = 'Narrative change saved. The view could not refresh: ' + error.message + ' Do not repeat the saved action.';
      }
    } finally {
      pending = false;
    }
  }, fail, 'primary');
  const inspect = button('Inspect current narrative', async () => {
    const fresh = await request(spineReadURL(handle, project));
    if (fresh.project !== project || !pin(fresh.revision)) throw Error('No current narrative basis was returned.');
    const live = fresh.spine?.find(row => row.id === beat.id);
    if (!live) throw Error('This beat was removed. Your draft remains available here for copying.');
    const comparison = element('section');
    comparison.append(element('h3', 'Current saved narrative'), element('p', live.narrative || 'No connective narrative.'));
    comparison.append(button('Use this inspected basis', () => {
      base = fresh;
      held = false;
      comparison.remove();
      input?.oninput?.();
      if (mode === 'order') {
        input.replaceChildren();
        fresh.spine.forEach((row, index) => {
          const option = element('option', `${index + 1} · ${row.term || row.id}`);
          option.value = String(index);
          input.append(option);
        });
        input.value = String(fresh.spine.findIndex(row => row.id === beat.id));
      }
      message.textContent = 'Current basis selected. Review your intended change before saving.';
    }, fail));
    dialog.insertBefore(comparison, actions);
  }, fail);
  actions.append(save, inspect, button('Close', () => dialog.close(), fail));
  dialog.append(message, actions);
  dialog.addEventListener('close', () => {
    dialog.remove();
    if (opener?.isConnected) opener.focus({
      preventScroll: true
    });
  });
  showReaderDialog(dialog, opener);
  input?.focus();
  return dialog;
}
export async function addSectionBeat({
  project,
  sectionId,
  node,
  request,
  fullGuardRead,
  onSaved,
  opener
}) {
  const full = await request(spineReadURL(planGuardHandle(fullGuardRead), project));
  const section = full.sections?.find(row => row.id === sectionId);
  if (full.project !== project || !pin(full.revision) || !section?.nodes?.some(row => (typeof row === 'string' ? row: row.id) === node.id)) {
    throw Error('This argument object is no longer in the selected plan item. Refresh before adding a beat.');
  }
  const dialog = element('dialog', '', 'spine-binding-dialog');
  dialog.append(element('h2', 'Add narrative beat'), element('p', node.label || node.title || node.id), element('p',
  'Use this argument object as a narrative beat in ' + (section.title || sectionId) + '. Its scientific prerequisites remain distinct from assumptions about what the reader already knows.'));
  const message = element('p', '', 'spine-status');
  message.setAttribute('role', 'status');
  let settled = false;
  const fail = error => {
    let outcome;
    try {
      outcome = planFailure(error);
    } catch (invalid) {
      error = invalid;
    }
    if (outcome || error.planUnverified) settled = true;
    message.textContent = outcome?.message || error.message;
  };
  dialog.append(message, button('Add beat', async () => {
    if (settled) return;
    const result = await request('/work/structure/change', {
      project,
      operation: 'plan',
      ops: [{
        kind: 'toggle-beat',
        section: sectionId,
        node: node.id,
        on: true
      }],
      expected_revision: full.revision
    });
    requirePlanCompletion(result);
    settled = true;
    try {
      await onSaved(result);
      dialog.close();
    } catch (error) {
      message.textContent = 'Narrative beat saved. The view could not refresh: ' + error.message + ' Do not repeat the action.';
    }
  }, fail, 'primary'), button('Cancel', () => dialog.close(), fail));
  dialog.addEventListener('close', () => {
    dialog.remove();
    if (opener?.isConnected) opener.focus({
      preventScroll: true
    });
  });
  showReaderDialog(dialog, opener);
  return dialog;
}
export function readerPlanReorder(full, sectionId, siblingIndex) {
  if (!pin(full?.revision) || !Array.isArray(full.sections)) throw Error('The complete reader plan and original guard are required.');
  const item = full.sections.find(row => row.id === sectionId);
  if (!item || !['sections', 'appendices'].includes(item.collection)) throw Error('This item has no exact plan collection. Refresh the reader plan.');
  const order = full.plan_collections?.[item.collection];
  if (!Array.isArray(order) || new Set(order).size !== order.length || order.some(id => !full.sections.some(row => row.id === id))) throw Error('The owner did not return complete collection membership.');
  const byId = new Map(full.sections.map(row => [row.id, row]));
  const siblings = order.map(id => byId.get(id)).filter(row => row.parent_id === item.parent_id);
  const previous = siblings.findIndex(row => row.id === sectionId);
  if (!Number.isInteger(siblingIndex) || siblingIndex < 0 || siblingIndex >= siblings.length) throw Error('Choose a position within this item’s parent.');
  if (previous === siblingIndex) return null;
  const groups = new Map(siblings.map(row => [row.id, order.filter(id => id === row.id || byId.get(id).ancestor_ids?.includes(row.id))]));
  const affected = new Set([...groups.values()].flat());
  const ids = siblings.map(row => row.id);
  ids.splice(previous, 1);
  ids.splice(siblingIndex, 0, sectionId);
  const reordered = ids.flatMap(id => groups.get(id));
  let offset = 0;
  return {
    kind: item.collection === 'appendices' ? 'reorder-appendices': 'reorder-sections',
    order: order.map(id => affected.has(id) ? reordered[offset ++]: id)
  };
}
async function moveReaderPlanItem({
  project,
  section,
  request,
  fullGuardRead,
  opener,
  onSaved
}) {
  const full = await request(spineReadURL(planGuardHandle(fullGuardRead), project));
  if (full.project !== project || !pin(full.revision)) throw Error('No current reader-plan guard was returned.');
  const item = full.sections?.find(row => row.id === section.id);
  if (!item) throw Error('This reader-plan item is no longer present.');
  const ids = full.plan_collections?.[item.collection];
  if (!Array.isArray(ids)) throw Error('No complete reader-plan collection was returned.');
  const siblings = ids.map(id => full.sections.find(row => row.id === id)).filter(row => row && row.parent_id === item.parent_id);
  const dialog = element('dialog', '', 'spine-binding-dialog'),
  choose = element('select');
  choose.setAttribute('aria-label', 'Reader-plan position');
  siblings.forEach((row, index) => {
    const option = element('option', `${index+1} · ${row.title || row.id}`);
    option.value = String(index);
    choose.append(option);
  });
  choose.value = String(siblings.findIndex(row => row.id === item.id));
  const message = element('p', '', 'spine-status');
  message.setAttribute('role', 'status');
  let settled = false;
  const fail = error => {
    let effect;
    try {
      effect = planFailure(error);
    } catch (invalid) {
      error = invalid;
    }
    if (effect || error.planUnverified) settled = true;
    message.textContent = effect?.message || error.message;
  };
  dialog.append(element('h2', 'Move reader-plan item'), element('p', item.title), element('p', 'This changes the intended reader order. Source headings and narrative beats keep their separate orders.'),
  choose, message, button('Save reader order', async () => {
    if (settled) return;
    const op = readerPlanReorder(full, item.id, Number(choose.value));
    if (!op) {
      message.textContent = 'No reader-order change.';
      return;
    }
    const result = await request('/work/structure/change', {
      project,
      operation: 'plan',
      ops: [op],
      expected_revision: full.revision
    });
    requirePlanCompletion(result);
    settled = true;
    try {
      await onSaved(result);
      dialog.close();
    } catch (error) {
      message.textContent = 'Reader order saved. Refresh is unavailable: ' + error.message + ' Do not repeat the action.';
    }
  }, fail, 'primary'), button('Close', () => dialog.close(), fail));
  dialog.addEventListener('close', () => {
    dialog.remove();
    if (opener?.isConnected) opener.focus({
      preventScroll: true
    });
  });
  showReaderDialog(dialog, opener);
  return dialog;
}
