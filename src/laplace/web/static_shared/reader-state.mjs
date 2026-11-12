// READER STATE (reader transition and paragraph plans) of one reader-plan section. Purpose:
// paint the authored reader transition and the exposition plan (paragraph cards with their
// standing, inputs, source passages, lineage and doors) and open the metadata editors on exact
// owner calls. Ownership: reader_plan (owner) publishes the fields, descriptors, choices, bases,
// currentness and every call; project_structure serves them as the plain detail (calls on the
// rows), the bounded display (doors on the rows; projection:display) and the guard subjects
// (one exact call per read; projection:guard with subject contract|paragraph|create|reorder|
// section|structure, edit_choices for the descriptors). Public contract: renderReaderState,
// readerSubjectRead/readerSubjectAction/readerDisplayHandle/readerDoor, editReaderMetadata,
// readerMetadataSubmission, changeReaderParagraph, readerParagraphAction, renderReaderGuard,
// acknowledgeReaderInputs/readerAcknowledgementSubmission/readerAcknowledgementOutcome,
// renderArchitecturePrior/inspectArchitecturePrior, the dialog helpers (showReaderDialog,
// lockReaderDialog, labelReaderControl). Inputs: a section (detail or display row shapes);
// outputs: DOM and owner submissions. Currentness: every submission carries the owner's
// expected_plan_revision, artifact revision and reader basis; a stale one refuses with
// CHANGED_INPUT and the retained draft stays. Storage: sessionStorage laplace:reader-state-draft:*
// (draft text with its original inspected basis). Controls: reader-plan:paragraph-action,
// reader-plan:paragraph-expand, reader-plan:transition-expand, reader-plan:guard,
// reader-plan:acknowledge-inputs.
import {renderRestructureOutcome} from './reader-restructure.mjs';
import {inspectProfilePreferences} from './profile-preferences.mjs';
import {objectHeader,stateChip,actionRow} from './workspace-presentation.mjs';
import {pendingRead} from './pending-read.mjs';
// Authored reader intent and paragraph exposition belong to their existing
// stage artifacts. This renderer never infers reader knowledge from graph edges.
const el = (tag, text = '', className = '') => {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
};
const READER_LABELS = {
  function: 'What this step does',
  question_answered: 'Question it answers',
  entry_state: 'What the reader brings',
  exit_state: 'What they should understand afterwards',
  permitted_recap: 'What can be repeated',
  depends_on: 'Related steps it relies on',
  forward_uses: 'What will be developed later',
  proposition: 'Point to establish',
  explanation: 'How to explain it',
  qualification: 'Limits and qualifications',
  from_previous: 'Connection from the preceding passage',
  to_next: 'Lead into the next passage'
};
const readerLabel = field => READER_LABELS[field.name] || field.label || field.name;
// the selected planned unit per project::section, kept for this page's life (never a plan model or a lifecycle)
const FOCUSED_UNITS = new Map();
// containment without a DOM reference kept past the call: is `node` inside `host` right now
const within = (host, node) => {for (let at = node; at; at = at.parentNode || at.parentElement || null) if (at === host) return true; return false;};
let readerControlSequence = 0;
export function labelReaderControl(wrapper, input, label) {
  input.id = 'reader-field-' + (++ readerControlSequence);
  input.setAttribute('aria-label', label);
  wrapper.htmlFor = input.id;
}
export function showReaderDialog(dialog, opener) {
  const host = opener?.closest?.('.workspace') || document.querySelector('.workspace') || document.body;
  host.append(dialog);
  dialog.showModal();
}
// Keep the submitted dialog stable until both the write acknowledgement and
// its view follow-through settle. Native disabled controls prevent late typing.
export function lockReaderDialog(dialog) {
  if (!dialog) return () => {};
  const controls = ['input','textarea','select','button'].flatMap(tag => [...dialog.querySelectorAll(tag)]);
  const previous = controls.map(control => [control, control.disabled]);
  for (const control of controls) control.disabled = true;
  const priorCancel = dialog.oncancel;
  const cancel = event => event.preventDefault();
  dialog.oncancel = cancel;
  dialog.setAttribute('aria-busy','true');
  return () => {
    for (const [control, disabled] of previous) if (control.disabled === true) control.disabled = disabled;
    if (dialog.oncancel === cancel) dialog.oncancel = priorCancel;
    dialog.removeAttribute?.('aria-busy');
  };
}
const fieldText = value => Array.isArray(value) ? value.join(', '): value == null ? '': String(value);
const action = (label, run, onError) => {
  const node = el('button', label);
  node.type = 'button';
  node.onclick = async () => {
    // the explicit action's intent, read before the control is disabled (M5-R2)
    const intent = {active: node};
    node.disabled = true;
    const unlock = lockReaderDialog(node.closest?.('dialog'));
    try {
      await run(intent);
    } catch (error) {
      onError(error);
    } finally {
      unlock();
      if (node.isConnected !== false) node.disabled = false;
    }
  };
  return node;
};
export function readerInputStatus(value) {
  const current = value?.input_currentness?.status;
  return ({
    CURRENT: 'Inputs current.',
    STALE: 'Inputs changed. Inspect the affected material before relying on this plan.',
    UNPINNED: 'Earlier inputs were not recorded.',
    UNOBSERVED: 'New support has not yet been inspected.'
  }) [current] || 'Input currentness is unavailable.';
}
function facts(host, fields, labels) {
  const list = el('dl', '', 'reader-state-facts');
  for (const [key, label] of labels) {
    const text = fieldText(fields?.[key]);
    if (text) list.append(el('dt', label), el('dd', text));
  }
  if (list.children.length) host.append(list);
}
function readerChecks(host, value, {
  onRead,
  onAcknowledgeInputs = null,
  onError
}) {
  const current = value.input_currentness || {},
  changed = [...new Set([...(current.changed_inputs || []), ...(current.unobserved_inputs || [])])],
  diagnostics = value.diagnostics || [];
  if (!changed.length && !diagnostics.length) return;
  const detail = el('details');
  detail.append(el('summary', 'Inputs and open points'));
  for (const key of changed) detail.append(el('p', (current.unobserved_inputs || []).includes(key)
    ? 'Not yet inspected: ' + readerInputName(key): 'Changed: ' + readerInputName(key)));
  for (const item of diagnostics) {
    detail.append(el('p', item.field ? 'Still to write: ' + (READER_LABELS[item.field] || item.field): 'Support needs attention: ' + (item.subject || item.reason)));
    if (item.read && onRead) detail.append(action('Inspect ' + (item.subject || 'input'), () => onRead(item.read,
    item.subject), onError));
  }
  host.append(detail);
  // G1: beside the disclosure, the human records inspected inputs on a fresh exact owner subject;
  // the dialog lists which of them can be acknowledged
  if (changed.length && onAcknowledgeInputs) {
    const acknowledge = action('Record inspected inputs…', () => onAcknowledgeInputs(value), onError);
    acknowledge.setAttribute('data-control','reader-plan:acknowledge-inputs');
    host.append(acknowledge);
  }
}
// A reader input situated on one claim: only an owner-issued concept read {operation:'concept', payload:{node}} names
// the claim. The Literature owner then inspects that claim's CURRENT meaning revision itself; nothing here is a guard.
export function readerLiteratureTarget(item) {
  const read = item?.read;
  if (read?.operation !== 'concept' || typeof read.payload?.node !== 'string' || !read.payload.node) return null;
  return {claim_id: read.payload.node, ...(typeof item.label === 'string' && item.label ? {label: item.label.slice(0, 240)} : {})};
}
function linkedInputs(host, value, {
  onRead,
  onError
}) {
  const links = value?.links || [];
  if (links.length) {
    const group = el('div', '', 'spine-actions');
    for (const item of links) if (item.read && onRead) group.append(action(item.label || 'Inspect linked input',
    () => onRead(item.read, item.label), onError));
    for (const item of links) {
      const target = readerLiteratureTarget(item);
      if (target && onRead?.literature) group.append(action('Find literature for ' + (target.label || target.claim_id),
      () => onRead.literature(target), onError));
    }
    if (group.children.length) host.append(group);
  }
  const reads = value?.input_currentness?.reads || [];
  if (reads.length && onRead) {
    const group = el('details');
    group.append(el('summary', 'Inspect recorded inputs'));
    for (const item of reads) {
      const read = item.read || item;
      group.append(action(item.label || 'Inspect input', () => onRead(read, item.label), onError));
    }
    host.append(group);
  }
}
export function renderReaderState(host, {
  section,
  project,
  onRead: ownerRead,
  onLiterature = null,
  onRecoverStructure,
  onInspectReconciliation,
  onInspectLatestStructure,
  onEditContract,
  onEditParagraph,
  onReview,
  onMoreParagraphs,
  onParagraphAction,
  onLogicalRestructure,
  onOccurrence,
  onExpandParagraph = null,
  onReadTransition = null,
  onAcknowledgeInputs = null,
  onError = () => {}
}) {
  // The situated Literature handoff travels with the existing owner-read callback to every linked-input row.
  const onRead = ownerRead && onLiterature ? Object.assign((...args) => ownerRead(...args), {literature: onLiterature}) : ownerRead;
  const transition = section.reader_transition,
  plan = section.paragraph_plan;
  if (!transition && !plan) return;
  const block = el('section', '', 'reader-state');
  block.append(el('h4', 'Reader transition'));
  if (transition) {
    if (transition.status === 'NOT_DECLARED') block.append(el('p', 'The reader’s entry and exit states have not been declared.',
    'muted'));
    else if (transition.status === 'UNAVAILABLE') block.append(el('p', transition.reason || 'The authored reader transition is unavailable.',
    'error'));
    const controls = el('div', '', 'spine-actions');
    let moreAppended = false, more = null;
    const MAIN = [['entry_state', 'What the reader brings'], ['question_answered', 'Question this section answers'],
    ['function', 'Role in the explanation'], ['exit_state', 'What they should understand afterwards']],
    MORE = [['depends_on', 'Authored dependencies'], ['forward_uses', 'Introduced now, used or justified later'],
    ['permitted_recap', 'Permitted recap'], ['citations', 'Citations'], ['equations', 'Equations'], ['figures',
    'Figures'], ['tables', 'Tables']];
    // repair3 R2 (2026-10-14): the shown text lives in its own hosts so a full read replaces it in place
    const shown = el('div', '', 'reader-transition-text'), shownMore = el('div', '', 'reader-transition-text');
    if (!['NOT_DECLARED', 'UNAVAILABLE'].includes(transition.status)) {
      facts(shown, transition.fields, MAIN);
      block.append(shown);
      // the display shortens long authored text; the owner's values_read is the full, read-only text
      const clipped = Array.isArray(transition.clipped) ? transition.clipped : [];
      if (clipped.length && transition.values_read && onReadTransition) {
        const names = clipped.map(name => (READER_LABELS[name] || name.replaceAll('_', ' ')).toLowerCase());
        const note = el('p', 'Shortened here: ' + names.join(', ') + '.', 'muted');
        const full = action('Read full reader transition', async () => {
          const values = await onReadTransition(transition);
          if (!values || block.isConnected === false) return;
          shown.replaceChildren(); shownMore.replaceChildren();
          facts(shown, values, MAIN); facts(shownMore, values, MORE);
          note.textContent = 'Full authored text (read only).';
          // dependency text the page did not show joins its disclosure, which takes the door's place
          if (!moreAppended && shownMore.children.length) {moreAppended = true; full.replaceWith(more);} else full.remove();
        }, onError);
        full.setAttribute('data-control','reader-plan:transition-expand');
        block.append(note, full);
      }
    }
    if (transition.status === 'DECLARED') {
      block.append(el('p', readerInputStatus(transition), 'muted'));
      readerChecks(block, transition, {
        onRead,
        onAcknowledgeInputs: onAcknowledgeInputs && (value => onAcknowledgeInputs(value)),
        onError
      });
    }
    more = el('details');
    more.append(el('summary', 'Dependencies, forward use and support'));
    facts(shownMore, transition.fields, MORE);
    more.append(shownMore);
    linkedInputs(more, transition, {
      onRead,
      onError
    });
    // shown when it carries text or a linked input (children beyond the summary and the text host)
    moreAppended = shownMore.children.length > 0 || more.children.length > 2;
    if (moreAppended) block.append(more);
    if ((transition.edit_action || readerDoor(transition, 'edit')) && onEditContract) controls.append(action(transition.status === 'NOT_DECLARED' ? 'Define reader transition': 'Edit reader transition',
    () => onEditContract(transition), onError));
    if (transition.review?.read && onRead) controls.append(action('Inspect reader-transition review', () => onRead(transition.review.read,
    'Reader-transition review'), onError));
    for (const review of transition.review?.records || []) if (review.read && onRead) controls.append(action('Inspect review · ' + review.status,
    () => onRead(review.read, 'Reader-transition review'), onError));
    if ((transition.review_action || transition.review?.action || readerDoor(transition, 'review')) && onReview) controls.append(action(transition.review?.records?.length ? 'Create another review work item': 'Create review work',
    () => onReview(transition.review_action || transition.review?.action || null, transition), onError));
    if (controls.children.length) block.append(controls);
    if (['NOT_ESTABLISHED', 'NOT_REVIEWED'].includes(transition.review?.status)) block.append(el('p', 'No review recorded.',
    'muted'));
    else if (transition.review?.status && !transition.review.records?.length) block.append(el('p', 'Recorded review: ' + (transition.review.label || transition.review.status.replaceAll('_',
    ' ').toLowerCase()), 'muted'));
  }
  host.append(block);
  if (!plan) return;
  const exposition = el('section', '', 'reader-exposition');
  exposition.append(el('h4', 'Exposition plan'));
  if (plan.status === 'NOT_DECLARED') exposition.append(el('p', 'No paragraph plan has been authored for this section.',
  'muted'));
  else if (plan.status === 'UNAVAILABLE') exposition.append(el('p', plan.reason || 'The paragraph plan is unavailable.',
  'error'));
  else if (plan.input_currentness) exposition.append(el('p', readerInputStatus(plan), 'muted'));
  if(plan.latest_restructure){const latest=plan.latest_restructure;if(onInspectLatestStructure)exposition.append(action('Inspect latest structural operation',()=>onInspectLatestStructure(latest),onError));else if(onRead&&latest.read_handle)exposition.append(action('Inspect latest structural operation',()=>onRead(latest.read_handle,'Latest structural operation'),onError));}
  for (const retained of plan.pending_restructures || []) {
    renderRestructureOutcome(exposition, retained, {project, onRead:handle => onRead?.(handle, 'Paragraph structure'),
      onRecovery:onRecoverStructure,onInspectReconciliation, isCurrent:() => host.isConnected !== false});
  }
  // THE FOCUSED UNIT (M5 Reader-plan usability, WORK-editor-reader-plan-usability-20261015): every planned unit is a
  // compact row in reading order (number, narrative label, how it follows, one attention state); ONE selected unit
  // opens in place into its workspace (reader knowledge before/after, support, grouped actions with their consequence).
  // The selection is remembered per section, so a save, refresh or page return comes back to the same unit.
  const items = plan.paragraphs?.items || [], offset = plan.paragraphs?.offset || 0, unitKey = project + '::' + section.id;
  const wholeRows = new Map();
  let focused = FOCUSED_UNITS.get(unitKey);
  if (!items.some(row => row.paragraph_id === focused)) focused = items[0]?.paragraph_id;
  const unitAttention = (paragraph, index) => {
    const status = paragraph.input_currentness?.status;
    if (status === 'STALE') return {label: 'Inputs changed', tone: 'attention'};
    if (status === 'UNOBSERVED') return {label: 'New support not inspected', tone: 'attention'};
    if (paragraph.identity_status === 'UNPROVEN_LEGACY') return {label: 'Identity unproven', tone: 'attention'};
    if (index + offset > 0 && !paragraph.from_previous && !(paragraph.authored || []).includes('from_previous')) return {label: 'Transition not written', tone: 'neutral'};
    return null;
  };
  const unitLabel = paragraph => paragraph.proposition || paragraph.function || 'Planned unit';
  const unitHead = (paragraph, index, open) => {
    const head = el('button', '', 'reader-unit-head');
    head.type = 'button';
    head.setAttribute('aria-expanded', String(open));
    head.setAttribute('data-control','reader-plan:unit-select');
    head.setAttribute('data-control-owner', project + '::' + section.id + '::' + paragraph.paragraph_id);
    head.setAttribute('aria-label', 'Planned unit ' + (index + offset + 1) + ' · ' + unitLabel(paragraph));
    head.append(el('span', String(index + offset + 1), 'reader-unit-number'), el('span', unitLabel(paragraph), 'reader-unit-label'));
    const follows = String(paragraph.from_previous || '');
    if (follows) head.append(el('span', 'Follows: ' + (follows.length > 90 ? follows.slice(0, 89) + '…' : follows), 'reader-unit-follows'));
    const attention = unitAttention(paragraph, index);
    if (attention) head.append(stateChip(attention));
    head.onclick = () => {
      if (focused === paragraph.paragraph_id) return;
      const previous = focused;
      focused = paragraph.paragraph_id;
      FOCUSED_UNITS.set(unitKey, focused);
      for (const id of [previous, focused]) {
        const at = items.findIndex(row => row.paragraph_id === id), node = cards.get(id);
        if (at < 0 || !node) continue;
        const next = paragraphCard(wholeRows.get(id) || items[at], at);
        node.replaceWith(next);
      }
      cards.get(focused)?.querySelector?.('.reader-unit-head')?.focus?.();
    };
    // the list is one stop for the keyboard: arrows move between units, Enter or Space opens one
    head.onkeydown = event => {
      if (!['ArrowDown', 'ArrowUp'].includes(event.key)) return;
      const order = items.map(row => cards.get(row.paragraph_id)?.querySelector?.('.reader-unit-head')).filter(Boolean), at = order.indexOf(head);
      const target = order[at + (event.key === 'ArrowDown' ? 1 : -1)];
      if (target) {event.preventDefault?.(); target.focus?.();}
    };
    return head;
  };
  const actionGroup = (title, consequence, nodes) => {
    if (!nodes.length) return null;
    const group = el('div', '', 'reader-unit-actions');
    group.append(el('h6', title), el('p', consequence, 'muted reader-unit-consequence'), ...nodes);
    return group;
  };
  const cards = new Map();
  const paragraphCard = (paragraph, index = items.findIndex(row => row.paragraph_id === paragraph.paragraph_id)) => {
    const card = el('article', '', 'reader-paragraph');
    card.dataset.paragraphId = paragraph.paragraph_id;
    const open = paragraph.paragraph_id === focused;
    card.dataset.focused = String(open);
    cards.set(paragraph.paragraph_id, card);
    card.append(unitHead(paragraph, Math.max(0, index), open));
    if (!open) return card;
    card.append(el('h5', unitLabel(paragraph)));
    // what the reader knows before and after this unit, and why it follows the previous one
    const knowledge = el('dl', '', 'reader-state-facts reader-unit-knowledge');
    for (const [key, label] of [['from_previous', 'Reader arrives with (why it follows)'], ['proposition', 'Point the reader gains'], ['to_next', 'Leads the reader on to']]) {
      const text = fieldText(paragraph[key]);
      if (text) knowledge.append(el('dt', label), el('dd', text));
    }
    if (knowledge.children.length) card.append(knowledge);
    if (index + offset > 0 && !paragraph.from_previous && !(paragraph.authored || []).includes('from_previous')) card.append(el('p',
      'No connection from the preceding unit is written: a step may be missing, or the transition is unsupported.', 'muted'));
    // a display list row: fields it did not carry, or text it shortened (repair3 R2: a clipped-only
    // row with authored:[] too), open the whole row in place through the owner's row_read, read only
    const omitted = Array.isArray(paragraph.authored) ? paragraph.authored : [], shortened = Array.isArray(paragraph.clipped) ? paragraph.clipped : [];
    const label = name => (READER_LABELS[name] || name.replaceAll('_', ' ')).toLowerCase();
    if ((omitted.length || shortened.length) && onExpandParagraph && (paragraph.read_handle || paragraph.paragraph_id)) {
      if (shortened.length) card.append(el('p', 'Shortened here: ' + shortened.map(label).join(', ') + '.', 'muted'));
      if (omitted.length) card.append(el('p', 'Also authored: ' + omitted.map(label).join(', ') + '.', 'muted'));
      const expand = action('Read whole paragraph plan', async intent => {
        // the person acted from this card's door (M5-I2/R2): the intent is the action's, read before the door was
        // disabled, and it is the only thing carried to the result
        const held = within(card, intent?.active);
        const whole = await onExpandParagraph(paragraph, plan.paragraphs?.row_read || null);
        // a late answer to a card that is no longer shown paints nothing and focuses nothing
        if (!whole || card.isConnected === false) return;
        const row = {...whole, authored: [], clipped: whole.clipped || []}; wholeRows.set(paragraph.paragraph_id, row);
        const next = paragraphCard(row, index); card.replaceWith(next);
        // the replacement is the same unit by its coordinate (data-control-owner); the keyboard lands on its
        // head, and only if it was still on this card or had nowhere to be once the door was replaced
        const now = document.activeElement;
        if (held && next.isConnected !== false && (!now || now === document.body || within(card, now) || now === expand))
          next.querySelector('.reader-unit-head')?.focus?.({preventScroll: true});
      }, onError);
      expand.setAttribute('data-control','reader-plan:paragraph-expand');
      card.append(expand);
    }
    if (paragraph.input_currentness) card.append(el('p', readerInputStatus(paragraph), 'muted'));
    readerChecks(card, paragraph, {
      onRead,
      onAcknowledgeInputs: onAcknowledgeInputs && paragraph.paragraph_id && (value => onAcknowledgeInputs(value, paragraph)),
      onError
    });
    if (paragraph.identity_status === 'UNPROVEN_LEGACY') card.append(el('p', 'This legacy plan has no proven persistent identity. Inspect its recorded origin before editing.',
    'muted'));
    facts(card, paragraph, [['explanation', 'Explanation'], ['qualification', 'Qualification']]);
    const details = el('details');
    details.append(el('summary', 'Inputs and writing obligations'));
    facts(details, paragraph, [['function', 'Function'], ['input_nodes', 'Argument inputs'], ['derivation_detail',
    'Derivation detail'], ['equation_anchor', 'Equation'], ['figure_anchor', 'Figure'], ['detail_level', 'Detail level'],
    ['length_range', 'Length range'], ['citations', 'Citations']]);
    linkedInputs(details, paragraph, {
      onRead,
      onError
    });
    if (details.children.length > 1) card.append(details);
    if (paragraph.source_occurrences?.length || paragraph.lineage?.read || paragraph.lineage?.items?.length) {
      const origins = el('details');
      origins.append(el('summary', 'Source passages and restructuring history'));
      for (const occurrence of paragraph.source_occurrences || []) {
        origins.append(el('p', 'Planned units in this source passage: ' + occurrence.spec_ids.join(', '), 'muted'));
        if (onOccurrence) origins.append(action('Read source passage · ' + occurrence.file.split('/').at(- 1) + ':' + occurrence.line_start,
        () => onOccurrence(occurrence), onError));
      }
      for (const change of paragraph.lineage?.items || []){origins.append(el('p',change.rationale||change.kind||'Recorded restructuring'));if(change.read&&onRead)origins.append(action('Inspect recorded restructuring decision',()=>onRead(change.read,'Paragraph restructuring'),onError));}
      if (paragraph.lineage?.read && onRead) origins.append(action('Inspect retained restructuring decisions', () => onRead(paragraph.lineage.read,
      'Paragraph restructuring'), onError));
      card.append(origins);
    }
    const paragraphControl = node => {node.setAttribute('data-control','reader-plan:paragraph-action'); return node;};
    // a door without its call (display row) opens on the bounded subject read; the consumer acquires it. The doors are
    // grouped by what they change, and each group says so before any effect.
    const edit = [], restructure = [], review = [];
    if ((paragraph.edit_action || readerDoor(paragraph, 'edit')) && onEditParagraph) edit.push(paragraphControl(action('Edit paragraph plan', () => onEditParagraph(plan,
    paragraph), onError)));
    for(const [key,label,kind]of [['split','Split planned unit','logical-split'],['merge','Combine planned units','logical-merge']]){
      const prepared=paragraph.restructure_actions?.[key];
      if((prepared||readerDoor(paragraph,key))&&onLogicalRestructure)restructure.push(action(label,()=>onLogicalRestructure(prepared||null,kind,paragraph,plan),onError));
    }
    if (onParagraphAction && (plan.reorder_action || readerDoor(plan, 'reorder'))) restructure.push(paragraphControl(action('Move paragraph plan', () => onParagraphAction(plan.reorder_action || null,
    paragraph, 'reorder'), onError)));
    if (onParagraphAction && (paragraph.remove_action || readerDoor(paragraph, 'remove'))) restructure.push(paragraphControl(action('Remove paragraph plan', () => onParagraphAction(paragraph.remove_action || null,
    paragraph, 'remove'), onError)));
    if ((paragraph.review_action || readerDoor(paragraph, 'review')) && onReview) review.push(action('Create paragraph review work', () => onReview(paragraph.review_action || null,
    paragraph), onError));
    for (const record of paragraph.review?.records || []) if (record.read && onRead) review.push(action('Inspect paragraph review · ' + record.status,
    () => onRead(record.read, 'Paragraph review'), onError));
    for (const group of [actionGroup('Edit this unit', 'Saving changes this planned unit in the reader plan only; manuscript text is not edited.', edit),
      actionGroup('Change the plan structure', 'Each opens its scope and a preview first; it changes the reader plan, never the manuscript source.', restructure),
      actionGroup('Review', 'Creates a linked Work item for review; it does not start a writing session.', review)]) if (group) card.append(group);
    return card;
  };
  const units = el('div', '', 'reader-unit-list');
  units.setAttribute('role', 'group');
  units.setAttribute('aria-label', 'Planned units in reading order');
  for (const [index, paragraph] of items.entries()) units.append(paragraphCard(paragraph, index));
  exposition.append(units);
  if (plan.paragraphs?.items?.length) exposition.append(el('p', `Planned units ${plan.paragraphs.offset+1}–${plan.paragraphs.offset+plan.paragraphs.items.length} of ${plan.paragraphs.total}`,
  'muted'));
  if (plan.paragraphs?.offset > 0 && plan.read_handle && onMoreParagraphs) exposition.append(action('First paragraph plans',
  () => onMoreParagraphs(plan.read_handle), onError));
  if (plan.paragraphs?.next_read && onMoreParagraphs) exposition.append(action('Next paragraph plans', () => onMoreParagraphs(plan.paragraphs.next_read),
  onError));
  if ((plan.create_action || readerDoor(plan, 'create')) && onEditParagraph) exposition.append(action('Add paragraph plan', () => onEditParagraph(plan,
  null), onError));
  linkedInputs(exposition, plan, {
    onRead,
    onError
  });
  host.append(exposition);
}
const selectedValues = (input, previous = []) => {
  const selected = [...input.children].filter(option => option.selected).map(option => option.value);
  return [...previous.filter(value => selected.includes(value)), ...selected.filter(value => !previous.includes(value))];
};
const revision = value => typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value);
const contractFields = new Set(['function', 'question_answered', 'entry_state', 'exit_state', 'depends_on',
'forward_uses', 'permitted_recap', 'citations', 'equations', 'figures', 'tables']);
const paragraphFields = new Set(['function', 'input_nodes', 'proposition', 'explanation', 'derivation_detail',
'equation_anchor', 'figure_anchor', 'qualification', 'from_previous', 'to_next', 'detail_level', 'length_range',
'citations']);
export function readerMetadataSubmission(action, values, project) {
  const base = action?.payload;
  if (action?.operation !== 'structure_change' || action.http?.method !== 'POST' || action.http.route !== '/work/structure/change' || !base || !['section_contract',
  'paragraph_plan'].includes(base.operation) || typeof base.section_id !== 'string' || !base.section_id || !revision(base.expected_plan_revision)) throw Error('This reader-state edit has no original owner guard. Refresh the selected item.');
  const contract = base.operation === 'section_contract',
  guard = contract ? 'expected_contract_revision': 'expected_narrative_revision';
  if (!Object.hasOwn(base, guard) || base[guard] !== null && !revision(base[guard])) throw Error('The reader artifact revision is missing.');
  const expectedBasis = base.expected_reader_basis;
  if (expectedBasis?.schema_version !== 'laplace.reader-basis/1' || expectedBasis.project !== project || expectedBasis.section_id !== base.section_id || !revision(expectedBasis.subject_revision) || !expectedBasis.inputs || typeof expectedBasis.inputs !== 'object' || Array.isArray(expectedBasis.inputs) || expectedBasis.subject_id !== (contract ? base.section_id: base.action === 'reorder' ? '@order': base.paragraph_id)) throw Error('The original displayed reader input basis is missing. Inspect the current subject before saving.');
  const allowed = ['operation', 'section_id', 'expected_plan_revision', 'expected_reader_basis', guard, ...(contract ? []: ['action',
  'paragraph_id', 'create', 'order'])];
  if (Object.keys(base).some(key => !allowed.includes(key))) throw Error('The edit template contains unobserved fields. Nothing was sent.');
  if (!contract && (!['upsert', 'remove', 'reorder'].includes(base.action) || base.action !== 'reorder' && (typeof base.paragraph_id !== 'string' || !base.paragraph_id))) throw Error('The paragraph action has no exact owner identity.');
  const known = contract ? contractFields: paragraphFields,
  descriptors = action.fields || [];
  if (!Array.isArray(descriptors) || descriptors.some(field => !known.has(field.name) || !['string', 'string_array'].includes(field.type))) throw Error('The owner supplied an unsupported reader-state field.');
  const changes = {};
  for (const [name, value] of Object.entries(values)) {
    const field = descriptors.find(item => item.name === name);
    if (!field) throw Error('This reader-state field was not offered by the owner.');
    if (field.type === 'string' && typeof value !== 'string' || field.type === 'string_array' && (!Array.isArray(value) || value.some(item => typeof item !== 'string'))) throw Error('The reader-state value does not match its declared field type.');
    if (JSON.stringify(value) !== JSON.stringify(action.values?.[name] ?? (field.type === 'string_array' ? []: ''))) changes[name] = value;
  }
  const inputObservations = {};
  for (const field of descriptors) {
    if (field.type !== 'string_array') continue;
    for (const value of values[field.name] || []) {
      if ((action.values?.[field.name] || []).includes(value)) continue;
      const choice = field.choices?.find(item => item.value === value);
      if (choice?.input_key && revision(choice.input_revision) && !Object.hasOwn(expectedBasis.inputs, choice.input_key)) inputObservations[choice.input_key] = choice.input_revision;
    }
  }
  return {
    project,
    ...base,
    changes,
    ...(Object.keys(inputObservations).length ? {
      input_observations: inputObservations
    }
    : {})
  };
}
export async function editReaderMetadata({
  project,
  action: original,
  title,
  request,
  inspectCurrent,
  loadChoices,
  onSaved = async () => {},
  opener,
  storage = globalThis.sessionStorage
}) {
  const {
    requirePlanCompletion,
    planFailure
  }
  = await import('./plan-publication.mjs');
  readerMetadataSubmission(original, {}, project);
  const identity = JSON.stringify([original.payload.operation, original.payload.section_id, original.payload.paragraph_id || null]);
  const key = 'laplace:reader-state-draft:' + project + ':' + identity;
  let basis = original,
  values = structuredClone(original.values || {}),
  settled = false,
  pending = false,
  restored = false,
  recoveredWithoutBasis = false;
  try {
    const held = JSON.parse(storage?.getItem(key) || 'null');
    if (held?.project === project && held.identity === identity) {
      try {
        readerMetadataSubmission(held.action, held.values, project);
        basis = held.action;
      } catch {
        readerMetadataSubmission(original, held.values, project);
        recoveredWithoutBasis = true;
      }
      values = held.values;
      restored = true;
      recoveredWithoutBasis = recoveredWithoutBasis || held.basis_unavailable === true;
    }
  } catch {
    /* Invalid local data cannot replace the inspected owner action. */
  }
  let choiceNotice = recoveredWithoutBasis ? 'Your local text is retained, but its old input basis is unavailable. Inspect the current plan before saving.': '',
  needsInspection = recoveredWithoutBasis;
  // ONE READ at open (C10-C11 H1): a fresh action that already carries its descriptors (a guard
  // read with edit_choices) is used as it is; the choices read runs only for a retained draft
  // (its original basis stands, the fresh read is the explicit stale inspection) or for an action
  // delivered without descriptors
  const needsChoices = restored || !Array.isArray(basis.fields) || !basis.fields.length;
  if (basis.choices_read && loadChoices && needsChoices) {
    try {
      const inspected = await loadChoices(basis);
      readerMetadataSubmission(inspected, {}, project);
      if (sameReaderActionBasis(basis, inspected)) basis = {
        ...basis,
        fields: inspected.fields
      };
      else if (sameReaderSubjectGuard(basis, inspected)) {
        basis = {
          ...basis,
          fields: inspected.fields
        };
        choiceNotice = 'Some supporting material changed. This draft retains the inputs it was opened with.';
      } else {
        choiceNotice = 'The saved plan changed while opening its choices. Your original draft is retained; inspect the current plan before saving.';
        needsInspection = true;
      }
    } catch (error) {
      choiceNotice = 'Choices could not be loaded: ' + error.message;
    }
  }
  const dialog = el('dialog', '', 'spine-binding-dialog'),
  form = el('form', '', 'work-form'),
  status = el('p', '', 'spine-status');
  status.setAttribute('role', 'status');
  if (restored) status.textContent = 'Your local draft and its original inspected basis are retained.';
  if (choiceNotice) status.textContent = choiceNotice;
  dialog.append(el('h2', title), form, status);
  const inputs = new Map(),
  advanced = el('details');
  advanced.append(el('summary', 'Inputs, anchors and further obligations'));
  const primary = new Set(['entry_state', 'exit_state', 'question_answered', 'function', 'proposition', 'explanation',
  'qualification', 'from_previous', 'to_next']);
  for (const field of basis.fields) {
    const choosing = field.type === 'string_array' && Array.isArray(field.choices) && field.choices.length;
    const wrapper = el('label', readerLabel(field)),
    input = el(choosing ? 'select': field.multiline || field.type === 'string_array' ? 'textarea': 'input');
    input.name = field.name;
    labelReaderControl(wrapper, input, readerLabel(field));
    const value = values[field.name] ?? (field.type === 'string_array' ? []: '');
    if (choosing) {
      input.multiple = true;
      input.size = Math.min(6, Math.max(3, field.choices.length));
      const known = new Set();
      for (const choice of field.choices) {
        const option = el('option', choice.label || choice.value);
        option.value = choice.value;
        option.selected = value.includes(choice.value);
        input.append(option);
        known.add(choice.value);
      }
      for (const retained of value) if (!known.has(retained)) {
        const option = el('option', 'Unresolved saved reference: ' + retained);
        option.value = retained;
        option.selected = true;
        input.append(option);
      }
    } else input.value = field.type === 'string_array' ? value.join('\n'): value;
    if (input.tagName === 'TEXTAREA') input.rows = field.type === 'string_array' ? 3: 4;
    wrapper.append(input);
    if (field.type === 'string_array' && !choosing) wrapper.append(el('small', 'One identifier or citation key per line.',
    'muted'));
    inputs.set(field.name, {
      input,
      field,
      choosing
    });
    (primary.has(field.name) ? form: advanced).append(wrapper);
  }
  if (advanced.children.length > 1) form.append(advanced);
  const readValues = () => Object.fromEntries([...inputs].map(([name, {
    input,
    field,
    choosing
  }]) => [name, choosing ? selectedValues(input, values[name] || []): field.type === 'string_array' ? (input.value === (basis.values?.[name] || []).join('\n') ? structuredClone(basis.values?.[name] || []): input.value.split('\n').map(value => value.trim()).filter(Boolean)): input.value]));
  const persist = () => {
    values = readValues();
    try {
      storage?.setItem(key, JSON.stringify({
        project,
        identity,
        action: basis,
        basis_unavailable: needsInspection,
        values
      }));
    } catch {
      status.textContent = 'Your draft remains in this editor; local draft storage is unavailable.';
    }
  };
  form.oninput = persist;
  const fail = error => {
    let effect;
    try {
      effect = planFailure(error);
    } catch (invalid) {
      error = invalid;
    }
    if (effect || error.planUnverified) settled = true;
    status.textContent = effect?.message || error.message;
    status.classList.add('error');
  };
  const controls = el('div', '', 'spine-actions'),
  save = el('button', original.payload.operation === 'section_contract' ? 'Save reader transition': 'Save paragraph plan',
  'primary');
  save.type = 'submit';
  save.disabled = needsInspection;
  controls.append(save);
  if (inspectCurrent) controls.append(action('Inspect current saved plan', async () => {
    persist();
    const current = await inspectCurrent();
    readerMetadataSubmission(current, {}, project);
    if (current.payload.section_id !== basis.payload.section_id || current.payload.paragraph_id !== basis.payload.paragraph_id) throw Error('The original planned object is no longer available. Your draft remains here for copying into a deliberate new item.');
    const comparison = el('section');
    comparison.append(el('h3', 'Current saved plan'));
    facts(comparison, current.values, current.fields.map(field => [field.name, readerLabel(field)]));
    comparison.append(action('Use this inspected basis', () => {
      const changed = readerMetadataSubmission(basis, values, project).changes;
      basis = current;
      values = {
        ...current.values,
        ...changed
      };
      settled = false;
      needsInspection = false;
      recoveredWithoutBasis = false;
      save.disabled = false;
      for (const [name, {
        input,
        field,
        choosing
      }] of inputs) {
        const value = values[name] ?? (field.type === 'string_array' ? []: '');
        if (choosing) {
          const choices = current.fields.find(item => item.name === name)?.choices || [];
          for (const next of[...choices, ...value.map(value => ({
            value,
            label: 'Unresolved saved reference: ' + value
          }))]) if (![...input.children].some(option => option.value === next.value)) {
            const option = el('option', next.label || next.value);
            option.value = next.value;
            input.append(option);
          }
          for (const option of input.children) {
            option.selected = value.includes(option.value);
            option.textContent = choices.find(choice => choice.value === option.value)?.label || 'Unresolved saved reference: ' + option.value;
          }
        } else input.value = field.type === 'string_array' ? value.join('\n'): value;
      }
      persist();
      comparison.remove();
      status.textContent = 'Inspected basis selected. Your changed fields remain; review before saving.';
    }, fail));
    dialog.insertBefore(comparison, status);
  }, fail));
  controls.append(action('Close', () => dialog.close(), fail));
  form.append(controls);
  form.onsubmit = async event => {
    event.preventDefault();
    if (pending || settled || needsInspection) return;
    persist();
    const payload = readerMetadataSubmission(basis, values, project);
    if (!Object.keys(payload.changes).length && !basis.payload.create && basis.payload.expected_contract_revision !== null) {
      status.textContent = 'No authored-plan changes.';
      return;
    }
    pending = true;
    save.disabled = true;
    const unlock = lockReaderDialog(dialog);
    status.textContent = 'Saving…';
    try {
      const result = await request('/work/structure/change', payload);
      const publication = requirePlanCompletion(result);
      if (!publication || !readerAcknowledgementMatches(result, payload)) throw Object.assign(Error('The authored-plan publication was not verified. Keep this draft and inspect the saved outcome before another action.'),
      {
        result,
        planUnverified: true
      });
      settled = true;
      try {
        storage?.removeItem(key);
      } catch {}
      try {
        await onSaved(result);
        dialog.close();
      } catch (error) {
        status.textContent = 'Authored plan saved. The view could not refresh: ' + error.message + ' Do not repeat the action.';
      }
    } catch (error) {
      fail(error);
    } finally {
      unlock();
      pending = false;
      save.disabled = settled;
    }
  };
  dialog.addEventListener('close', () => {
    dialog.remove();
    if (opener?.isConnected) opener.focus({
      preventScroll: true
    });
  });
  showReaderDialog(dialog, opener);
  inputs.values().next().value?.input.focus();
  return dialog;
}
export function renderArchitecturePrior(host, value, {
  onInspect,
  onError = () => {}
}
= {}) {
  if (!value || value.family !== 'architecture') return;
  const section = el('section', '', 'reader-architecture-prior');
  section.append(el('h4', 'Structural writing preferences'), el('p', value.purpose || 'Shared preferences for the shape of an explanation.'));
  if (value.status === 'AVAILABLE') section.append(el('p', 'Shared workspace input · ' + (value.currentness === 'CURRENT' ? 'current profile bytes': 'currentness unavailable'),
  'muted'));
  else section.append(el('p', value.reason || 'No readable structural profile is available.', 'muted'));
  const effective = value.effective_projection;
  if (effective?.summary) section.append(el('p', effective.summary));
  if (effective?.fields && Object.keys(effective.fields).length) {
    const used = el('details');
    used.append(el('summary', 'Preferences used for this section'));
    for (const [name, field] of Object.entries(effective.fields)) {
      used.append(el('h5', name.replaceAll('_', ' ')), el('p', typeof field === 'string' ? field: field.summary || ''));
    }
    section.append(used);
  }
  if (value.read_more && onInspect) section.append(action('Inspect structural preferences', () => onInspect(value),
  onError));
  host.append(section);
}
export async function inspectArchitecturePrior({
  project,
  request,
  onChanged,
  onGenerate,
  value,
  read,
  opener,
  isCurrent = () => true
}) {
  if(project&&request){
    if(!isCurrent())return null;
    const opened=await inspectProfilePreferences({project,family:'architecture',scope:'workspace',request,opener,onChanged,onGenerate});
    if(!isCurrent()){opened.controller.destroy();opened.dialog.close();return null;}
    return opened.dialog;
  }
  const current = await read(value.read_more);
  if (!isCurrent()) return null;
  if (current.family !== 'architecture' || current.scope !== 'workspace') throw Error('The profile reader returned a different input family.');
  const dialog = el('dialog', '', 'spine-binding-dialog');
  dialog.append(el('h2', 'Structural writing preferences'), el('p', current.purpose || ''));
  if (current.status !== 'AVAILABLE') dialog.append(el('p', current.reason || 'This profile is unavailable.',
  'error'));
  else for (const [name, field] of Object.entries(current.fields || {})) {
    const section = el('section');
    section.append(el('h3', name.replaceAll('_', ' ')), el('p', field.summary || ''));
    if (field.confirmed_his) section.append(el('p', 'Recorded author confirmation', 'muted'));
    dialog.append(section);
  }
  const source = el('details');
  source.append(el('summary', 'Scope and source'), el('p', 'Shared across this workspace'), el('p', current.source?.path || 'Source unavailable'),
  el('p', current.currentness_basis || 'Profile bytes do not establish accepted exposition.'));
  dialog.append(source, el('p', 'Shared structural preferences are read-only in this view.', 'muted'), action('Close',
  () => dialog.close(), () => {}));
  dialog.addEventListener('close', () => {
    dialog.remove();
    if (opener?.isConnected) opener.focus({
      preventScroll: true
    });
  });
  showReaderDialog(dialog, opener);
  return dialog;
}
// THE BOUNDED SUBJECT READ (N1, 2026-10-14): one exact owner-issued call with its guards,
// from the same detail owner projected to one subject -- the section contract, one paragraph
// (edit and remove), the create call or the reorder call -- so a dialog opens on a fresh,
// bounded basis instead of a 70-180 KB detail re-read. The HTTP form is the payload as query
// parameters on /work/structure; writing-owner-read admits projection/subject coordinates.
// Subjects (C10-C11 adds two beside the accepted four): `section` carries the section-level calls
// (link a source heading, prepare work, create review work) and `structure` one row's split/merge
// previews and review call; `choices: true` adds the typed field descriptors and choice lists to a
// contract, paragraph or create subject so an editor opens on ONE bounded read.
export const READER_SUBJECTS = Object.freeze(['contract', 'paragraph', 'create', 'reorder', 'section', 'structure']);
export function readerSubjectRead(project, sectionId, subject, paragraphId = null, {choices = false} = {}) {
  if (!READER_SUBJECTS.includes(subject)) throw Error('Unknown reader-plan subject: ' + subject);
  if ((subject === 'paragraph' || subject === 'structure') && !paragraphId) throw Error('A ' + subject + ' subject read needs its paragraph_id.');
  const payload = {view: 'detail', section_ids: [sectionId], projection: 'guard', subject, ...(paragraphId ? {paragraph_id: paragraphId} : {}),
    ...(choices && ['contract', 'paragraph', 'create'].includes(subject) ? {edit_choices: true} : {})};
  return {operation: 'structure', payload, http: {method: 'GET', route: '/work/structure', query: {project, ...payload}}};
}
export function readerSubjectAction(value, subject, {project, sectionId, paragraphId = null, kind = 'edit'} = {}) {
  if (value?.schema_version !== 'laplace.project-structure-guard/1' || value.project !== project || value.section_id !== sectionId || value.subject !== subject) throw Error('The reader-plan owner returned a different guard subject.');
  if (subject === 'contract') return kind === 'review' ? value.reader_transition?.review_action : value.reader_transition?.edit_action;
  if (subject === 'create') return value.create_action;
  if (subject === 'reorder') return value.reorder_action;
  if (subject === 'section') {
    const calls = value.section_calls || {};
    return {link_source: calls.clearing_action, prepare_work: calls.prepare_action, review: calls.review_action}[kind];
  }
  if (value.paragraph?.paragraph_id !== paragraphId) throw Error('The reader-plan owner returned a different paragraph.');
  if (subject === 'structure') return kind === 'review' ? value.paragraph.review_action : value.paragraph.restructure_actions?.[kind];
  return kind === 'remove' ? value.paragraph.remove_action : value.paragraph.edit_action;
}
// THE DISPLAY ROW (ACTUAL-C6-DETAIL-BYTES): a projection:display row names its doors and the
// authored fields it did not carry; the plain detail row carries the calls themselves.
export const readerDoor = (row, name) => Array.isArray(row?.doors) ? row.doors.includes(name) : !!(row?.doors && typeof row.doors === 'object' && row.doors[name]);
export function readerDisplayHandle(project, sectionId, extra = {}) {
  const payload = {view: 'detail', section_ids: [sectionId], ...extra, projection: 'display'};
  return {operation: 'structure', payload, http: {method: 'GET', route: '/work/structure', query: {project, ...payload}}};
}
// THE HUMAN GUARD INSPECTOR (Sol guard-consumer, 2026-10-14). A saved, nested or recovered
// projection:guard read is one exact owner subject (contract, paragraph, create or reorder), not a
// reader plan: it renders read-only from the response it was given, refuses a response for a
// different owner, section, subject or paragraph through readerSubjectAction, and issues no read
// of its own. Further reads are the owner's own handles (full detail, the contract subject, the
// paragraph's handle) and open only through the consumer's onRead. Actions stay on the Reader plan.
// The calls one guard subject carries, by their owner names (H5, 2026-10-14): the four accepted
// subjects carry one edit/create/reorder call; `section` carries the section-level calls and
// `structure` one row's structural and review calls. Each is read through readerSubjectAction,
// so a different owner, section, subject or paragraph refuses before anything renders.
const GUARD_CALL_KINDS = Object.freeze({contract: ['edit'], paragraph: ['edit', 'remove'], create: ['edit'], reorder: ['edit'],
  section: ['link_source', 'prepare_work', 'review'], structure: ['split', 'merge', 'review']});
const GUARD_CALL_LABELS = Object.freeze({edit: 'Edit call', remove: 'Remove call', link_source: 'Link source heading', prepare_work: 'Prepare work', review: 'Create review work', split: 'Split planned unit (preview)', merge: 'Combine planned units (preview)'});
export function readerGuardCalls(value, subject, {project, sectionId, paragraphId = null} = {}) {
  const kinds = GUARD_CALL_KINDS[subject];
  if (!kinds) throw Error('Unknown reader-plan subject: ' + subject);
  const calls = kinds.map(kind => [kind, readerSubjectAction(value, subject, {project, sectionId, paragraphId, kind})]).filter(([, call]) => call?.payload);
  if (!calls.length) throw Error('The reader-plan owner published no ' + subject + ' call for this section.');
  return calls;
}
export function renderReaderGuard(host, value, {project, sectionId, subject, paragraphId = null, onRead = null} = {}) {
  const calls = readerGuardCalls(value, subject, {project, sectionId, paragraphId});
  const action = calls[0][1];
  const section = value.section || {}, payload = action.payload, basis = payload.expected_reader_basis || {};
  const region = el('section', '', 'reader-guard');
  region.setAttribute('data-control','reader-plan:guard');
  const transition = value.reader_transition || {}, paragraph = value.paragraph || {}, plan = value.paragraph_plan || {};
  const status = subject === 'contract' ? transition.status : subject === 'paragraph' ? paragraph.identity_status : plan.identity_status;
  const currentness = (subject === 'paragraph' ? paragraph.input_currentness : transition.input_currentness)?.status;
  const chips = [status ? {label: String(status).replaceAll('_', ' ').toLowerCase(), tone: 'neutral'} : null,
    currentness ? {label: 'inputs ' + String(currentness).replaceAll('_', ' ').toLowerCase(), tone: currentness === 'CURRENT' ? 'ok' : 'attention'} : null].filter(Boolean);
  region.append(objectHeader({eyebrow: 'Reader-plan guard · ' + subject, title: section.title || sectionId, chips: chips.map(stateChip),
    summary: 'Exact owner subject, read-only. ' + (subject === 'section' ? 'The section-level calls (link a source heading, prepare work, review) as the owner issued them.' : subject === 'structure' ? 'One row\'s structural previews and review call as the owner issued them.' : 'Edits open from the Reader plan on a fresh guard.')}));
  const facts = el('dl', '', 'reader-guard-facts');
  const fact = (term, detail) => {if (detail === undefined || detail === null || detail === '') return; facts.append(el('dt', term), el('dd', String(detail)));};
  fact('Project', value.project); fact('Section', section.number ? sectionId + ' (section ' + section.number + ')' : sectionId);
  fact('Subject', subject); if (paragraphId) fact('Paragraph', paragraphId);
  fact('Call', action.operation + (action.http?.method ? ' · ' + action.http.method + ' ' + (action.http.route || action.http.url || '') : ''));
  fact('Plan revision', payload.expected_plan_revision || value.authority?.plan_revision);
  fact('Contract revision', payload.expected_contract_revision); fact('Narrative revision', payload.expected_narrative_revision);
  fact('Subject revision', basis.subject_revision);
  fact('Basis inputs', basis.inputs && typeof basis.inputs === 'object' ? Object.keys(basis.inputs).length + ' pinned' : undefined);
  if (subject === 'paragraph') {fact('Function', paragraph.function); fact('Proposition', paragraph.proposition);}
  if (subject === 'contract') {const source = section.source || {}; fact('Source binding', source.precision ? source.precision + (source.heading?.title ? ' · ' + source.heading.title : '') : undefined);
    const rows = plan.paragraphs; if (rows?.items) fact('Paragraph rows', rows.items.length + ' of ' + (rows.total ?? rows.items.length) + ' listed');}
  if (subject === 'create') fact('Placement', action.placement ? JSON.stringify(action.placement) : payload.paragraph_id ? 'new unit ' + payload.paragraph_id : undefined);
  if (subject === 'reorder') fact('Current order', Array.isArray(payload.order) ? payload.order.length + ' units' : undefined);
  if (subject === 'structure') fact('Identity', value.paragraph?.identity_status);
  region.append(facts);
  // every call the subject carries, read-only: its operation, route and the guards it is sent with
  if (subject === 'section' || subject === 'structure' || calls.length > 1) {
    const list = el('dl', '', 'reader-guard-facts reader-guard-calls');
    for (const [kind, call] of calls) {
      list.append(el('dt', GUARD_CALL_LABELS[kind] || kind));
      const guards = Object.keys(call.payload || {}).filter(key => /^expected_/.test(key)).sort();
      list.append(el('dd', call.operation + (call.http?.method ? ' · ' + call.http.method + ' ' + (call.http.route || call.http.url || '') : '') + (guards.length ? ' · guards: ' + guards.join(', ') : '') + (call.payload?.expected_plan_revision ? ' · plan ' + call.payload.expected_plan_revision : '')));
    }
    region.append(list);
  }
  if (onRead) {
    const reads = [];
    if (value.full_read) reads.push({label: 'Read full section detail', handle: value.full_read});
    if (subject !== 'contract' && value.subject_reads?.contract) reads.push({label: 'Read the contract subject', handle: {operation: 'structure', payload: value.subject_reads.contract}});
    if (subject === 'paragraph' && paragraph.read_handle) reads.push({label: 'Read this paragraph', handle: paragraph.read_handle});
    if (reads.length) region.append(actionRow(reads.map(row => ({label: row.label, kind: 'read', run: () => onRead(row.handle, row.label)}))));
  }
  host.append(region);
  return region;
}
export function readerParagraphAction(action, project, order = null) {
  const payload = readerMetadataSubmission(action, {}, project);
  delete payload.changes;
  if (!['remove', 'reorder'].includes(payload.action)) throw Error('This is not a paragraph removal or reorder action.');
  if (payload.action === 'reorder') {
    const original = payload.order;
    if (!Array.isArray(original) || new Set(original).size !== original.length || original.some(id => typeof id !== 'string') || !Array.isArray(order) || order.length !== original.length || new Set(order).size !== order.length || order.some(id => !original.includes(id))) {
      throw Error('Reordering requires the complete original paragraph membership.');
    }
    payload.order = order;
  }
  return payload;
}
export async function changeReaderParagraph({
  project,
  action: prepared,
  paragraph,
  request,
  onSaved,
  opener
}) {
  const {
    requirePlanCompletion,
    planFailure
  }
  = await import('./plan-publication.mjs');
  const moving = prepared?.payload?.action === 'reorder';
  const original = prepared?.payload?.order;
  readerParagraphAction(prepared, project, moving ? original: null);
  const dialog = el('dialog', '', 'spine-binding-dialog'),
  status = el('p', '', 'spine-status');
  status.setAttribute('role', 'status');
  dialog.append(el('h2', moving ? 'Move paragraph plan': 'Remove paragraph plan'), el('p', paragraph.proposition || paragraph.function || paragraph.paragraph_id),
  el('p', moving ? 'The planned unit keeps its identity. This changes plan order; manuscript prose is not rewritten.': 'This removes the authored planning unit. Manuscript prose and its recorded provenance remain separate and may need review.',
  'muted'));
  let position = null;
  if (moving) {
    if (!original.includes(paragraph.paragraph_id)) throw Error('This paragraph is absent from the complete observed plan.');
    position = el('select');
    position.setAttribute('aria-label', 'New paragraph-plan position');
    original.forEach((id, index) => {
      const label = prepared.choices?.find(choice => choice.value === id)?.label || id;
      const option = el('option', `${index+1} · ${label}`);
      option.value = String(index);
      position.append(option);
    });
    position.value = String(original.indexOf(paragraph.paragraph_id));
    dialog.append(position);
  }
  let settled = false;
  const fail = error => {
    let effect;
    try {
      effect = planFailure(error);
    } catch (invalid) {
      error = invalid;
    }
    if (effect || error.planUnverified) settled = true;
    status.textContent = effect?.message || error.message;
  };
  const confirm = action(moving ? 'Save paragraph order': 'Remove planned unit', async () => {
    if (settled) return;
    let order = null;
    if (moving) {
      const at = Number(position.value),
      previous = original.indexOf(paragraph.paragraph_id);
      if (at === previous) {
        status.textContent = 'No paragraph-order change.';
        return;
      }
      order = [...original];
      order.splice(previous, 1);
      order.splice(at, 0, paragraph.paragraph_id);
    }
    const payload = readerParagraphAction(prepared, project, order),
    result = await request('/work/structure/change', payload);
    const publication = requirePlanCompletion(result);
    if (!publication || !readerAcknowledgementMatches(result, payload)) throw Object.assign(Error('The paragraph-plan outcome was not verified. Inspect the saved record before another action.'),
    {
      result,
      planUnverified: true
    });
    settled = true;
    try {
      await onSaved(result);
      dialog.close();
    } catch (error) {
      status.textContent = 'Paragraph plan saved. Refresh failed: ' + error.message + ' Do not repeat the saved action.';
    }
  }, fail);
  dialog.append(status, confirm, action('Cancel', () => dialog.close(), fail));
  dialog.addEventListener('close', () => {
    dialog.remove();
    if (opener?.isConnected) opener.focus({
      preventScroll: true
    });
  });
  showReaderDialog(dialog, opener);
  return dialog;
}
export function readerAcknowledgementMatches(result, payload) {
  const guard = payload.operation === 'section_contract' ? 'expected_contract_revision': 'expected_narrative_revision';
  const same = (!result?.project || result.project === payload.project) && result?.read_handle?.http?.query?.project === payload.project && result?.operation === payload.operation && result.section_id === payload.section_id && (result.paragraph_id || null) === (payload.paragraph_id || null) && result.consumed_revision === payload[guard] && typeof result.changed === 'boolean' && (result.revision === null || revision(result.revision));
  if (!same) return false;
  if (!result.changed) return true;
  const before = payload.expected_reader_basis,
  after = result.reader_basis;
  return after?.schema_version === 'laplace.reader-basis/1' && after.project === payload.project && after.path === before.path && after.subject_id === before.subject_id && after.section_id === before.section_id && after.subject_revision === result.subject_revision && !!after.inputs && Object.entries(after.inputs).every(([key,
  value]) => !Object.hasOwn(before.inputs, key) || before.inputs[key] === value);
}
// G1 HUMAN INPUT ACKNOWLEDGEMENT (S2, 2026-10-15). The owner's observation-only write: the CURRENT
// edit call of an unchanged subject with changes:{} and input_observations {key: the pin the owner
// issued on that same call}. Only keys the call's expected basis still consumes can be named; a
// removed input or a changed authored subject is reported, never acknowledged. Contract bytes,
// unnamed pins and review stay as they are; an identical repeat is the owner's ALREADY_RECORDED.
export const READER_INPUT_NAMES = Object.freeze({
  'plan-section': 'Reader-plan purpose or placement',
  'architecture': 'Structural writing preferences',
  'reader-transition': 'Reader transition',
  'reader-neighbors': 'Neighbouring paragraph plans',
  'authored-subject': 'Authored content'
});
// an owner input key: a named family, else its kind and identity ('citation:new-a' reads 'Citation new-a')
export const readerInputName = key => READER_INPUT_NAMES[key] || String(key).replace(/^([a-z-]+):/, (_, kind) => kind[0].toUpperCase() + kind.slice(1).replaceAll('-', ' ') + ' ');
export function readerAcknowledgementSubmission(action, keys, project) {
  const checked = readerMetadataSubmission(action, {}, project);
  const inputs = checked.expected_reader_basis.inputs;
  const named = [...new Set(keys || [])];
  if (!named.length) throw Error('Select at least one inspected input.');
  const absent = named.filter(key => typeof key !== 'string' || !Object.hasOwn(inputs, key) || !revision(inputs[key]));
  if (absent.length) throw Error('These inputs are no longer consumed by this subject and cannot be acknowledged: ' + absent.join(', ') + '. Re-read the subject.');
  return {...checked, changes: {}, input_observations: Object.fromEntries(named.sort().map(key => [key, inputs[key]]))};
}
export function readerAcknowledgementOutcome(result, submission) {
  const seen = result?.observation, named = Object.keys(submission.input_observations).sort();
  if (!readerAcknowledgementMatches(result, submission) || result.changed !== false || result.content_changed !== false
    || !['RECORDED', 'ALREADY_RECORDED'].includes(seen?.disposition)
    || JSON.stringify([...(seen.acknowledged_inputs || [])].sort()) !== JSON.stringify(named))
    throw Error('The owner reply does not match the inputs acknowledged. Re-read the subject before recording again.');
  const standing = result.input_currentness?.status;
  return {disposition: seen.disposition, acknowledged: named, standing, receipt: seen.receipt || null,
    text: (seen.disposition === 'RECORDED' ? 'Recorded as inspected: ' : 'Already recorded; nothing new was written: ') + named.map(readerInputName).join(', ')
      + '. Input standing is now ' + String(standing || 'unavailable').toLowerCase() + '. This is not a review and changes no authored text.'};
}
// acquire() returns the fresh exact subject {action, currentness, read}; the dialog names what was seen on
// that read and sends only those pins. CHANGED_INPUT keeps the dialog and offers a fresh read.
// LIFETIME (S2-R1): own(dispose) registers the dialog with the controller that created it and returns its
// unregister; that owner disposes it on destroy or when its subject is no longer selected. Disposal closes an
// idle dialog and invalidates a pending read; isCurrent() is checked again right before the write and before
// any follow-through. A write already sent when the owner goes keeps the dialog to state its truthful outcome
// (recorded, or unknown after a failed reply) with the exact subject read for recovery and Close only; it never
// refreshes another view and never resends.
export async function acknowledgeReaderInputs({project, title, acquire, request, opener, isCurrent = () => true, onSaved = async () => {},
  own = () => () => {}}) {
  const dialog = el('dialog', '', 'dialog reader-acknowledge');
  dialog.setAttribute('aria-label', 'Record inspected inputs');
  dialog.append(el('h3', 'Record inspected inputs'));
  if (title) dialog.append(el('p', title, 'muted'));
  const body = el('div'), status = el('p', '', 'muted');
  status.setAttribute('role', 'status');
  const fail = error => {status.textContent = error.message;};
  let subject = null, boxes = [], disposed = false, writing = false, ticket = 0;
  const live = () => !disposed && isCurrent();
  const exactRead = () => {const http = subject?.read?.http;
    return http ? ' Exact read: ' + http.method + ' ' + http.route + '?' + new URLSearchParams(Object.entries(http.query || {}).map(([key, value]) =>
      [key, Array.isArray(value) ? value.join(',') : String(value)])) + '.' : '';};
  const load = async (note = '') => {
    const mine = ++ticket;
    pendingRead(status,'Reading the current subject…');
    const next = await acquire();
    if (!live() || mine !== ticket || !dialog.isConnected) return;
    subject = next; boxes = [];
    body.replaceChildren();
    const current = subject.currentness || {}, inputs = subject.action?.payload?.expected_reader_basis?.inputs || {};
    const unobserved = current.unobserved_inputs || [];
    const keys = [...new Set([...(current.changed_inputs || []), ...unobserved])];
    if (!keys.length) {status.textContent = (note ? note + ' ' : '') + 'Every consumed input is recorded at its current pin.'; return;}
    const list = el('fieldset');
    list.append(el('legend', 'Inputs you have inspected'));
    for (const key of keys) {
      const label = el('label'), name = readerInputName(key);
      if (Object.hasOwn(inputs, key)) {
        const box = el('input');
        box.type = 'checkbox'; box.value = key; boxes.push(box);
        label.append(box, document.createTextNode(' ' + (unobserved.includes(key) ? 'Not yet inspected: ' : 'Changed: ') + name));
      } else label.append(document.createTextNode(name + (key === 'authored-subject'
        ? ' changed; edit or review the subject itself.' : ' is no longer consumed and cannot be acknowledged.')));
      list.append(label);
    }
    body.append(list);
    status.textContent = note;
  };
  // the owner went while a write was out: say what is known, keep only Close, never refresh or resend
  const orphaned = text => {status.textContent = text + ' The reader-plan view closed or moved on, so it was not refreshed.' + exactRead();
    record.hidden = true; reread.hidden = true; dialog.dataset.outcome = 'orphaned';};
  const record = action('Record selected inputs as inspected', async () => {
    if (!subject) throw Error('Read the current subject first.');
    if (!live()) throw Error('This reader-plan item is no longer open. Nothing was recorded.');
    const keys = boxes.filter(box => box.checked).map(box => box.value);
    const submission = readerAcknowledgementSubmission(subject.action, keys, project);
    let result;
    writing = true;
    try {result = await request(subject.action.http.route, submission);}
    catch (error) {
      writing = false;
      if (/CHANGED_INPUT/.test(error.message || '')) {status.textContent = 'These inputs moved since this read. Nothing was recorded. Re-read and inspect again.'; return;}
      if (!live()) {orphaned('Whether the owner recorded this is unknown (' + error.message + '). Read the subject before recording again.'); return;}
      throw error;
    }
    writing = false;
    const outcome = readerAcknowledgementOutcome(result, submission);
    status.textContent = outcome.text;
    for (const box of boxes) box.checked = false;
    if (!live()) {orphaned(outcome.text + ' Do not repeat the recorded action.'); return;}
    try {await onSaved(result, outcome); if (live()) await load(outcome.text);}
    catch (error) {status.textContent = outcome.text + ' Refresh failed: ' + error.message + ' Do not repeat the recorded action.';}
  }, error => {writing = false; fail(error);});
  const reread = action('Re-read inputs', () => load(), fail);
  dialog.append(body, status, actionRow([record, reread, action('Close', () => dialog.close(), fail)]));
  const unregister = own(() => {if (disposed) return; disposed = true; ++ticket; if (!writing && dialog.open) dialog.close(); else if (!writing) dialog.remove();});
  dialog.addEventListener('close', () => {
    unregister();
    dialog.remove();
    if (opener?.isConnected) opener.focus({preventScroll: true});
  });
  showReaderDialog(dialog, opener);
  try {await load();} catch (error) {if (live()) fail(error);}
  return dialog;
}
export function readerReviewSubmission(prepared, project) {
  const payload = prepared?.payload;
  if (prepared?.operation !== 'task' || prepared.http?.method !== 'POST' || prepared.http.route !== '/work/task' || !payload || payload.kind !== 'reader-review' || typeof payload.title !== 'string' || typeof payload.goal !== 'string' || payload.reader_basis?.project !== project || payload.reader_basis.schema_version !== 'laplace.reader-basis/1' || !Array.isArray(payload.section_ids) || payload.section_ids.length !== 1 || payload.section_ids[0] !== payload.reader_basis.section_id || Object.keys(payload).some(key => !['title',
  'goal', 'kind', 'section_ids', 'reader_basis'].includes(key))) throw Error('This review has no exact owner-prepared subject basis. Refresh the reader plan.');
  return {
    project,
    ...payload
  };
}
export function sameReaderActionBasis(a, b) {
  const stable = value => Array.isArray(value) ? value.map(stable): value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key,
  stable(value[key])])): value;
  return a?.operation === b?.operation && JSON.stringify(stable(a?.payload)) === JSON.stringify(stable(b?.payload));
}
export function sameReaderSubjectGuard(a, b) {
  const subject = action => ({
    ...action,
    payload: {
      ...action.payload,
      expected_reader_basis: {
        ...action.payload.expected_reader_basis,
        inputs: {}
      }
    }
  });
  return sameReaderActionBasis(subject(a), subject(b));
}
