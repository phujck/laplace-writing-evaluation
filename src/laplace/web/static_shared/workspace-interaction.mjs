import {workflowActionInput,actionSubmissionRead} from './workflow-action-context.mjs';
import {objectContextInput} from './research-object-context.mjs';
import {materialReadingInput} from './local-document-intake-port.mjs';
// Authored message intent belongs to the local conversation draft. Reading
// attention is an observation and never implicitly replaces this attachment.
const schema = 'laplace.composer-draft/1';
const pin = value => typeof value === 'string' && /^sha256:[0-9a-f]{64}$/.test(value);
const contextFields = ['surface', 'label', 'node_id', 'node_ids', 'section_ids',
  'beat_id', 'review', 'structure_observation', 'workflow_action', 'material_read', 'object_context'];

export function messageTarget(reading = {}, work = null) {
  const context = {};
  for (const key of contextFields) {
    if (reading[key] !== undefined) context[key] = structuredClone(reading[key]);
  }
  context.surface ||= 'project';
  context.label ||= 'Project';
  if(context.material_read)materialReadingInput(context.material_read);
  if(context.object_context)objectContextInput(context.object_context);
  if (work) {
    if (!work.id || !pin(work.work_scope_revision) || !pin(work.dependency_revision)) {
      throw Error('Inspect this Work item before using it for a message. Its scope and prerequisite basis are required.');
    }
    Object.assign(context, {
      task_id: work.id,
      work_label: work.title || work.id,
      expected_work_scope_revision: work.work_scope_revision,
      expected_dependency_revision: work.dependency_revision
    });
  }
  return context;
}

export function encodeComposerDraft(text, intent = null) {
  return intent ? JSON.stringify({schema, text, intent}) : text;
}

export function connectedObservationSeconds(intent) {
  const value=intent?.connected_observation_seconds;
  if(value===undefined)return undefined;
  if(!Number.isSafeInteger(value)||value<=0)throw Error('Enter a positive whole number of seconds for connected waiting, or leave it blank.');
  return value;
}

export function sameComposerIntent(left, right) {
  const canonical = value => Array.isArray(value) ? value.map(canonical) :
    value && typeof value === 'object' ? Object.fromEntries(
      Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value;
  return JSON.stringify(canonical(left || null)) === JSON.stringify(canonical(right || null));
}

export function decodeComposerDraft(value = '') {
  // Old drafts, including text that happens to be JSON, remain exact text.
  try {
    const record = JSON.parse(value);
    if (record?.schema === schema && typeof record.text === 'string' &&
        record.intent && typeof record.intent === 'object' && !Array.isArray(record.intent)) {
      const context = record.intent.context;
      if (!context || typeof context !== 'object' || Array.isArray(context)) {
        throw Error('The retained message target is incomplete.');
      }
      if (context.task_id && (!pin(context.expected_work_scope_revision) || !pin(context.expected_dependency_revision))) {
        throw Error('The retained Work target has no inspected scope basis.');
      }
      if(context.workflow_action)workflowActionInput(context.workflow_action);
      if(context.material_read)materialReadingInput(context.material_read);
      if(context.object_context)objectContextInput(context.object_context);
      if(record.intent.submission)actionSubmissionRead(record.intent.submission);
      return {text: record.text, intent: record.intent};
    }
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error;
  }
  return {text: value, intent: null};
}

// Workspace return composition retains domain-owned positions. It does not
// interpret graph, PDF, source or history coordinates itself.
export function createWorkspaceReturn(initial = null) {
  let place = initial;
  return {
    get current() { return place; },
    remember(value, {replace = false} = {}) {
      if (!place || replace) place = value;
      return place;
    },
    take() { const value = place; place = null; return value; },
    clear() { place = null; }
  };
}

// One local settings envelope grammar for bootstrap Send and the lazy inspector.
// Legacy flat choices remain readable; malformed pending custody is never repaired here.
export function preferenceDraftEnvelope(raw){
  if(!raw||typeof raw!=='object'||Array.isArray(raw))throw Error('The retained settings draft is damaged. Nothing was replaced or sent.');
  if(Object.hasOwn(raw,'pilot_preferences')){const held=raw.pilot_preferences;if(!held||typeof held!=='object'||Array.isArray(held)||!held.values||typeof held.values!=='object'||Array.isArray(held.values)||typeof held.dirty!=='boolean'||!Object.hasOwn(held,'pending')||!Object.hasOwn(held,'last')||[held.pending,held.last].some(v=>v!==null&&(typeof v!=='object'||Array.isArray(v))))throw Error('The retained settings draft is damaged. Nothing was replaced or sent.');return structuredClone(held);}
  return {values:Object.fromEntries(['provider','model','effort'].filter(k=>Object.hasOwn(raw,k)).map(k=>[k,raw[k]])),dirty:false,pending:null,last:null};
}
