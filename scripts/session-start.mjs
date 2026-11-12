#!/usr/bin/env node
// Passive projection; no state or environment mutation, models, services or watchers.
import { execFileSync } from 'node:child_process';
import { dirname, join } from 'node:path';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import process from 'node:process';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const launcher = join(root, 'scripts', 'laplace-python');
const fallback = `At session startup, before answering the first user message or starting project work, `
  + `run and read scripts/laplace-python scripts/wake.py --grade 0 --person from ${root}; `
  + `follow ${join(root, 'EIGEN_PROTOCOL.md')}. Do not wait for a greeting or orientation request. `
  + 'Respect an explicit no-start instruction. Workers replace --person with --engine. '
  + 'This passive context projection does not satisfy the authored wake. '
  + 'Normal operation uses /home/phujck/VScodeProjects/laplace with shared state at /home/phujck/.mcp-gerard/laplace. '
  + 'An assigned worktree/fixture retains its declared state; this hook changes no state selection. '
  + 'Custody is OFF; this hook does not run Fabric, watchers or lifecycle commands.';

function currentContext() {
  const pieces = [];
  try {
    const memory = execFileSync(launcher, ['-m', 'laplace.engine.session_memory', 'show', '--compact'], {
      cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 1200,
    }).trim();
    const current = JSON.parse(memory);
    pieces.push('[current law/preferences from records; cached provider notes are historical] ' +
      JSON.stringify({status: current.status, generation: current.generation, views: current.views,
        unreconciled_rulings: current.unreconciled_rulings, read_cost: current.read_cost}) + '\n' +
      current.entries.map(item => `${item.reference}: ${item.text}${item.complete_text ? '' : ' [excerpt; reconstruct the reference for full context]'}`).join('\n'));

  } catch (error) {
    pieces.push(`[current memory unavailable: ${error.message}; use wake --memory to inspect]`);
  }
  try {
    const handoff = readFileSync(join(root, 'HANDOFF.md'), 'utf8');
    pieces.push(`[current handoff: ${join(root, 'HANDOFF.md')}]\n${handoff.slice(0, 5000)}`
      + (handoff.length > 5000 ? '\n[bounded excerpt; reconstruct HANDOFF.md for the continuation]' : ''));
  } catch (error) {
    pieces.push(`[current handoff unavailable: ${error.code || error.message}]`);
  }
  try {
    const close = JSON.parse(readFileSync(join(root, 'contract/close_receipt.json'), 'utf8'));
    pieces.push('[recorded close; verify current artifacts with wake --health] ' + JSON.stringify({
      close_act_id: close.close_act_id || close.act_id,
      publication_act_id: close.publication?.act_id,
      published: close.publication?.published,
    }));
  } catch { pieces.push('[no readable recorded close receipt]'); }
  return pieces.join('\n');
}

function emit(text) {
  process.stdout.write(`${JSON.stringify({hookSpecificOutput: {
    hookEventName: 'SessionStart', additionalContext: `${text}\n${fallback}\n${currentContext()}`,
  }})}\n`);
}

try {
  const result = execFileSync(launcher, [join(root, 'scripts', 'runtime_truth.py')], {
    cwd: root, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 1_200,
  }).trim();
  emit(result || '[runtime-truth] UNKNOWN; the passive probe returned nothing.');
} catch (error) {
  emit(`[runtime-truth] UNKNOWN; the passive probe did not complete (${error.message}).`);
}
