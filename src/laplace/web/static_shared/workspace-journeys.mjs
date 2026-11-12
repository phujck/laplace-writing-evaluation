// LEARNING PROGRESS AND TASK ROWS (M5 C10). Purpose: the person's progress through the help
// owner's declared journeys, and the task rows the help layer lists for one area.
// Ownership: the journeys themselves are the help owner's (writing_declarations
// JOURNEY_DECLARATIONS, read through /authoring/help?view=areas); this module owns only the
// local progress record. Public contract: learningStore(project, storage) -> {read, journey(id),
// update(id, patch), key}; journeyRows(areas, areaId, store) -> rows for the help layer.
// Storage: sessionStorage `laplace:learning:<project>` = {schema_version:'laplace.learning/1',
// journeys:{[id]:{step, closed, outcome?, run?}}, migrated_from} (outcome and run: workspace-guide.mjs).
// Retention: the tab's session; it is labelled as the person's progress and is never an owner fact (a business outcome comes from owner chips).
// Retired path (C11): `laplace:guide:<project>` held the welcome tour's step and closed flag. It is
// read here, carried WHOLE into journeys.welcome, and removed only after the new record is written
// and read back; nothing writes it again. Errors: a failed or unverified write keeps the retired
// key and reports status 'unsaved'; a foreign record (including a journeys array or any non-plain
// container) is kept untouched (status 'unsupported'). The retired record is also kept whole under
// legacy_records[<retired key>] (a different record already there keeps its key; the new one takes
// the first unused <retired key>#n), so mixed old/new state loses nothing while newer progress wins.
// An existing legacy_records value that is not a plain map makes the whole record 'unsupported'.
// Producers/consumers: workspace-guide.mjs (writes a journey's step on every move),
// workspace-help.mjs (reads rows), workspace.mjs (one store per project session).
export const LEARNING_SCHEMA = 'laplace.learning/1';
export const learningKey = project => 'laplace:learning:' + project;
export const legacyGuideKey = project => 'laplace:guide:' + project;
// THE MIGRATION IS A USER-STATE OPERATION (C10-C11 H3). The retired record is read whole and
// carried whole (every field, known or not) into journeys.welcome unless progress is already
// recorded there; the new record is written and READ BACK before the retired key is removed; a
// failed or unverified write leaves the retired key in place, keeps the carried progress in
// memory and says so (status 'unsaved'); a stored record this module does not understand is
// never overwritten (status 'unsupported', read-only, kept under `foreign`). No reset is ever
// automatic.
export function learningStore(project, storage = globalThis.sessionStorage) {
  const key = learningKey(project), legacy = legacyGuideKey(project);
  let value = null, status = 'unsaved';
  const parse = text => {try {return text == null ? null : JSON.parse(text);} catch {return undefined;}};
  // repair2 R3: only a plain object is a supported container; an array, a class instance or a
  // malformed record is foreign and is never overwritten (status 'unsupported')
  const plain = value => !!value && Object.prototype.toString.call(value) === '[object Object]';
  // key-order independent JSON text: the same record read back in another key order is the same record
  const canonical = record => JSON.stringify(record, (_key, item) => plain(item) ? Object.fromEntries(Object.keys(item).sort().map(k => [k, item[k]])) : item);
  const ours = record => plain(record) && record.schema_version === LEARNING_SCHEMA && plain(record.journeys);
  // write, then read back: a swallowed setItem failure or a storage that lies is not a save
  const persist = () => {
    if (status === 'unsupported') return false;
    const text = JSON.stringify(value);
    try {storage?.setItem(key, text);} catch {status = 'unsaved'; return false;}
    let back = null; try {back = storage?.getItem(key);} catch {back = null;}
    status = back === text ? 'saved' : 'unsaved';
    return status === 'saved';
  };
  const read = () => {
    if (value) return value;
    const stored = parse((() => {try {return storage?.getItem(key);} catch {return null;}})());
    if (stored === undefined || (stored !== null && !ours(stored))) {
      // an unreadable or foreign record: kept, never overwritten; progress is read-only here
      value = {schema_version: LEARNING_SCHEMA, journeys: {}, migrated_from: null, foreign: stored === undefined ? 'unparseable' : stored};
      status = 'unsupported';
      return value;
    }
    value = stored || {schema_version: LEARNING_SCHEMA, journeys: {}, migrated_from: null};
    status = stored ? 'saved' : 'unsaved';
    // repair3 R3 (2026-10-14): legacy_records is reserved for this migration. A value already there
    // that is not a plain map is someone else's data: the record is kept exactly as stored and is
    // read-only ('unsupported') BEFORE any write or removal; the retired key stays where it is.
    if (stored && Object.hasOwn(stored, 'legacy_records') && !plain(stored.legacy_records)) {status = 'unsupported'; return value;}
    const old = parse((() => {try {return storage?.getItem(legacy);} catch {return null;}})());
    if (plain(old)) {
      // carry the retired record WHOLE (unknown fields included) into welcome unless newer progress
      // is already recorded there; in every case keep the original record itself, opaque and complete,
      // under legacy_records so nothing the old key held is lost. Every record already kept stays
      // under its own key; the same record is never kept twice; a conflicting record takes the first
      // key <retired key>#n that is verified unused (never a count, which can name a kept record).
      if (!value.journeys.welcome) value.journeys.welcome = {...old, step: Math.max(0, Number(old.step) || 0), closed: !!old.closed};
      const kept = {...(value.legacy_records || {})}, same = record => canonical(record) === canonical(old);
      if (!Object.values(kept).some(same)) {
        let slot = legacy;
        for (let n = 2; Object.hasOwn(kept, slot); n += 1) slot = legacy + '#' + n;
        kept[slot] = old;
      }
      value.legacy_records = kept;
      value.migrated_from = legacy;
      if (persist()) {try {storage?.removeItem(legacy);} catch {/* the retired key stays; the next read carries it again, idempotently */}}
    } else if (old !== null && old !== undefined) {
      // a retired value this module cannot read stays where it is; nothing is carried or removed
      value.migrated_from = null;
    }
    return value;
  };
  return {
    get key() {return key;},
    get status() {read(); return status;},
    read,
    journey(id) {const entry = read().journeys[id]; return plain(entry) ? entry : null;},
    // a malformed entry (not a plain object) is kept as it is; progress for it is not written
    update(id, patch) {const current = read(); const entry = current.journeys[id]; if (status === 'unsupported' || (entry !== undefined && !plain(entry))) return plain(entry) ? entry : null; current.journeys[id] = {...(entry || {step: 0, closed: false}), ...patch}; persist(); return current.journeys[id];}
  };
}
// THE PROGRESS WORDS (C12, 2026-10-15). "Finished" only for a run that recorded outcome "finished" (its last step
// seen in that run, then Finish). Stop and Escape record "stopped", Skip on the last step "skipped". An entry
// written before outcomes existed says only that it was closed, never Finished. The stored entry is not changed.
export function journeyStatus(progress, total) {
  if (!progress) return 'Not started';
  const at = 'step ' + (Math.min(Math.max(0, Number(progress.step) || 0), total - 1) + 1) + ' of ' + total;
  if (!progress.closed) return 'S' + at.slice(1);
  if (progress.outcome === 'finished') return 'Finished';
  if (progress.outcome === 'skipped') return 'Skipped ' + at;
  if (progress.outcome === 'stopped') return 'Stopped at ' + at;
  return 'Closed at ' + at;
}
// The task rows of one area: the declared journeys with the person's progress in words.
export function journeyRows(areas, areaId, store = null) {
  const area = (areas?.areas || []).find(row => row.id === areaId);
  return (area?.journeys || []).map(id => {
    const journey = (areas.journeys || []).find(row => row.id === id);
    if (!journey) return null;
    const progress = store?.journey(id), total = journey.steps.length;
    return {id, title: journey.title, area: journey.area, steps: total, step: progress?.step || 0, closed: !!progress?.closed, outcome: progress?.closed ? progress.outcome || null : null, status: journeyStatus(progress, total)};
  }).filter(Boolean);
}
