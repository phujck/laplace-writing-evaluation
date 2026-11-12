// M5 P2 reached consumer (Root CUA, 2026-10-14): Material -> Recorded files -> Read of a manuscript-scoped artifact saved
// after Add manuscript. The real Material view opens the row through its OWNER-ISSUED receipt route, so the real shared
// opener reads the selected draft; the bare path URL it used to rebuild reaches a state-home decoy and the owner refuses it.
// Owner answers: tests/fixtures/shell/generate_owner_answers.py (drafted_*).
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {installDOM,Node} from './helpers/evidence_reader_harness.mjs';
import {mountMaterial,artifactReaderOptions} from '../src/laplace/web/static_shared/workspace-material.mjs';
import {openArtifact,artifactURL} from '../src/laplace/web/static_shared/writing-artifact.mjs';

const OWNERS = JSON.parse(readFileSync(new URL('./fixtures/shell/owner-answers.json', import.meta.url), 'utf8'));
const row = OWNERS.drafted_materials.materials.find(item => item.path === 'notes/owned-after-start.json');
const receipt = new URL(row.human_read.url, 'http://local').searchParams;

function owner(calls) {
  return async path => {
    calls.push(path);
    const url = new URL(path, 'http://local'), q = url.searchParams;
    if (url.pathname === '/work/materials') return structuredClone(OWNERS.drafted_materials);
    if (url.pathname === '/projects/material-references') return {references: [], revision: 'r', total: 0, next_offset: null, owners: {repositories: []}};
    if (url.pathname === '/research/artifact') {
      // the owner answers the receipt route; any other coordinates reach the state-home decoy and are refused (409)
      if (q.get('owner') === 'writing-artifact' && q.get('artifact_id') === row.id) return structuredClone(OWNERS.drafted_receipt_page);
      throw Object.assign(Error(OWNERS.drafted_bare_refusal.body.error), {status: 409, result: OWNERS.drafted_bare_refusal.body});
    }
    return {};
  };
}

test('the recorded-file options are the owner-issued receipt route, checked against the row', () => {
  const options = artifactReaderOptions(row, {project: 'drafted'});
  assert.deepEqual({path: options.path, scope: options.scope, artifactId: options.artifactId, artifactOwner: options.artifactOwner, expectedSha256: options.expectedSha256},
    {path: 'notes/owned-after-start.json', scope: 'manuscript', artifactId: row.id, artifactOwner: 'writing-artifact', expectedSha256: receipt.get('expected_sha256')});
  const url = new URL(artifactURL({project: 'drafted', ...options}, {expected_sha256: options.expectedSha256}), 'http://local').searchParams;
  for (const key of ['project', 'path', 'scope', 'artifact_id', 'owner', 'expected_sha256']) assert.equal(url.get(key), receipt.get(key), key);
  // a route for another receipt or pin is not adopted; the row's own receipt id, owner, path and pin are still carried
  for (const bad of [{...row, human_read: {url: row.human_read.url.replace(row.id, 'ART-' + '0'.repeat(32))}},
                     {...row, recorded_revision: '1'.repeat(64)}, {...row, human_read: undefined}]) {
    const fallback = artifactReaderOptions(bad, {project: 'drafted'});
    assert.deepEqual([fallback.artifactId, fallback.artifactOwner, fallback.path, fallback.scope, fallback.expectedSha256],
      [row.id, 'writing-artifact', row.path, 'manuscript', bad.recorded_revision.replace(/^sha256:/, '').toLowerCase()]);
  }
});

// P2 repair1 (Sol P2-R1): older receipts whose pin is missing, null or malformed. The owner issues no receipt route;
// the consumer keeps owner + receipt id (never a bare path), asks for no pin, and says the historical identity is
// unavailable. The owner answers that request with the CURRENT selected-draft bytes; the bare path reaches the decoy.
const legacyRows = OWNERS.drafted_legacy_materials.materials.filter(item => item.path.startsWith('notes/legacy-'));
function legacyOwner(calls) {
  return async path => {
    calls.push(path);
    const url = new URL(path, 'http://local'), q = url.searchParams;
    if (url.pathname === '/work/materials') return structuredClone(OWNERS.drafted_legacy_materials);
    if (url.pathname === '/projects/material-references') return {references: [], revision: 'r', total: 0, next_offset: null, owners: {repositories: []}};
    if (url.pathname === '/research/artifact') {
      if (q.get('owner') === 'writing-artifact' && OWNERS.drafted_legacy_pages[q.get('artifact_id')] && !q.has('expected_sha256'))
        return structuredClone(OWNERS.drafted_legacy_pages[q.get('artifact_id')]);
      if (!q.has('owner') && !q.has('artifact_id') && OWNERS.drafted_legacy_bare[q.get('path')]) return structuredClone(OWNERS.drafted_legacy_bare[q.get('path')]);
      throw Object.assign(Error('unexpected artifact request ' + path), {status: 422});
    }
    return {};
  };
}

test('a receipt without a complete pin keeps its owner and id, requests no pin and says the revision is unavailable', () => {
  assert.equal(legacyRows.length, 3);
  for (const legacy of legacyRows) {
    assert.equal(legacy.human_read, undefined, 'the owner issues no receipt route without a complete pin');
    const options = artifactReaderOptions(legacy, {project: 'drafted'});
    assert.deepEqual([options.artifactId, options.artifactOwner, options.path, options.scope, options.expectedSha256],
      [legacy.id, 'writing-artifact', legacy.path, 'manuscript', undefined], legacy.path);
    assert.match(options.notice, /recorded no byte identity, so its historical revision is unavailable/);
    assert.doesNotMatch(options.notice, /must match this revision/);
    const q = new URL(artifactURL({project: 'drafted', ...options}, {format: 'json'}), 'http://local').searchParams;
    assert.deepEqual([q.get('owner'), q.get('artifact_id'), q.has('expected_sha256')], ['writing-artifact', legacy.id, false]);
  }
  // a malformed id is never sent as a receipt; the request still names the writing-artifact owner, path and scope
  const odd = artifactReaderOptions({...legacyRows[0], id: 'ART-../x'}, {project: 'drafted'});
  assert.deepEqual([odd.artifactId, odd.artifactOwner, odd.path], [undefined, 'writing-artifact', legacyRows[0].path]);
});

for (const legacy of legacyRows) {
  test('Material -> Read of a legacy receipt (' + legacy.path + ') opens the selected draft, never the state-home decoy', async () => {
    const dom = installDOM();
    try {
      const host = new Node('main'), calls = [], request = legacyOwner(calls);
      dom.body.append(host);
      const info = {capabilities: {manuscript: true, research: true, materials: true, material_references: false}, source_optional: true};
      await mountMaterial(host, {project: 'drafted', info, request, onShow() {}, onHistory() {}, projects: [],
        onArtifact: (path, label, options) => openArtifact({project: 'drafted', path, label, ...options, request})});
      const file = host.all().filter(n => n.attrs['data-control'] === 'material:file').find(n => n.textContent.includes(legacy.path));
      await file.all().find(n => n.tag === 'button' && n.textContent.startsWith('Read ')).onclick();
      await new Promise(resolve => setTimeout(resolve, 0));
      const reads = calls.filter(path => path.startsWith('/research/artifact')).map(path => new URL(path, 'http://local').searchParams);
      assert.ok(reads.length >= 1 && reads.every(q => q.get('owner') === 'writing-artifact' && q.get('artifact_id') === legacy.id), 'every read keeps owner and receipt');
      const dialog = dom.dialogs().at(-1);
      assert.match(dialog.textContent, new RegExp('selected draft ' + legacy.path.slice('notes/legacy-'.length, -4)));
      assert.match(dialog.textContent, /historical revision is unavailable/);
      assert.doesNotMatch(dialog.textContent, /state-home decoy|matched expected revision/);
    } finally {dom.restore();}
  });
}

test('Material -> Recorded files -> Read opens the selected draft through the real opener, not the decoy', async () => {
  const dom = installDOM();
  try {
    const host = new Node('main'), calls = [], request = owner(calls);
    dom.body.append(host);
    const info = {capabilities: {manuscript: true, research: true, materials: true, material_references: false}, source_optional: true};
    await mountMaterial(host, {project: 'drafted', info, request, onShow() {}, onHistory() {}, projects: [],
      onArtifact: (path, label, options) => openArtifact({project: 'drafted', path, label, ...options, request})});
    const file = host.all().filter(n => n.attrs['data-control'] === 'material:file').find(n => n.textContent.includes('notes/owned-after-start.json'));
    assert.ok(file, 'the recorded file row is listed');
    await file.all().find(n => n.tag === 'button' && n.textContent.startsWith('Read ')).onclick();
    await new Promise(resolve => setTimeout(resolve, 0));
    const reads = calls.filter(path => path.startsWith('/research/artifact'));
    assert.ok(reads.length >= 1 && reads.every(path => new URL(path, 'http://local').searchParams.get('artifact_id') === row.id), 'every read names the receipt');
    const dialog = dom.dialogs().at(-1);
    assert.ok(dialog, 'the reader opened');
    assert.match(dialog.textContent, /selected draft/);
    assert.doesNotMatch(dialog.textContent, /Artifact identity changed|state-home decoy/);
  } finally {dom.restore();}
});

test('History opens an artifact activity through the same owner-issued receipt route', async () => {
  // the History open handler is the activity owner's (workspace-activity.mjs, M5 S2 F1)
  const source = readFileSync(new URL('../src/laplace/web/static_shared/workspace-activity.mjs', import.meta.url), 'utf8');
  const start = source.indexOf("else if(target.kind==='artifact'){"), end = source.indexOf("else if(target.kind==='concept')", start);
  assert.ok(start > 0 && end > start, 'the History artifact branch');
  const body = source.slice(start + "else if(target.kind==='artifact'){".length, source.lastIndexOf('}', end));
  const opened = [];
  const run = new Function('artifactReaderOptions', 'inspectProjectArtifact', 'project', 'target', 'const inspect={projectArtifact:inspectProjectArtifact};return (async()=>{' + body + '})();');
  const target = {kind: 'artifact', id: row.id, artifact_path: row.path, label: row.path, scope: row.scope, recorded_revision: row.recorded_revision, human_read: row.human_read};
  await run(artifactReaderOptions, async (...args) => opened.push(args), 'drafted', target);
  const [path, , options] = opened[0];
  assert.equal(path, row.path);
  assert.deepEqual([options.artifactId, options.artifactOwner, options.scope], [row.id, 'writing-artifact', 'manuscript']);
  assert.match(options.notice, /Recorded receipt/);
  // History activities: a legacy receipt keeps owner + id with the unavailable-identity notice; an activity with no
  // receipt id opens through the owner with its path and scope (and its pin when recorded), never a bare path
  for (const [activity, expected] of [
      [{kind: 'artifact', id: legacyRows[1].id, artifact_path: legacyRows[1].path, scope: 'manuscript', recorded_revision: null}, [legacyRows[1].id, undefined, /historical revision is unavailable/]],
      [{kind: 'artifact', id: legacyRows[0].id, artifact_path: legacyRows[0].path, scope: 'manuscript', recorded_revision: 'sha256:not-a-digest'}, [legacyRows[0].id, undefined, /historical revision is unavailable/]],
      [{kind: 'artifact', id: null, artifact_path: 'notes/plain.md', scope: 'project', recorded_revision: null}, [undefined, undefined, /No recorded receipt or revision/]],
      [{kind: 'artifact', id: null, artifact_path: 'notes/plain.md', scope: 'project', recorded_revision: 'A'.repeat(64)}, [undefined, 'a'.repeat(64), /Recorded artifact revision/]]]) {
    opened.length = 0;
    await run(artifactReaderOptions, async (...args) => opened.push(args), 'drafted', activity);
    const [openedPath, , got] = opened[0];
    assert.equal(openedPath, activity.artifact_path);
    assert.deepEqual([got.artifactOwner, got.artifactId, got.expectedSha256, got.scope], ['writing-artifact', expected[0], expected[1], activity.scope]);
    assert.match(got.notice, expected[2]);
  }
});
