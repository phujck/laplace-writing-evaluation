// The walk's source as one text, for tests that read or slice its real functions (M5 S2): walk.mjs is
// the composition root and its owner modules are walk-*.mjs beside it. Order: the root, then the owner
// modules by file name. A slice is the module's own verbatim text; nothing is rewritten here.
import {readFileSync, readdirSync} from 'node:fs';
const dir = new URL('../../src/laplace/web/static_shared/', import.meta.url);
export const WALK_FILES = Object.freeze(['walk.mjs', ...readdirSync(dir).filter(name => /^walk-[a-z-]+\.mjs$/.test(name)).sort()]);
export const walkSource = () => WALK_FILES.map(name => readFileSync(new URL(name, dir), 'utf8')).join('\n');
// One top-level declaration by name, verbatim with its leading comment, from whichever owner module
// holds it; walkDeclarations joins several in the order given. A declaration ends where the next
// column-0 statement or comment begins (module bodies are indented inside declarations).
const DECLARATION = name => new RegExp('^(?:export )?(?:async )?(?:function\\*? ' + name + '\\(|(?:const|let) ' + name + '\\b)', 'm');
export function walkDeclaration(name) {
  for (const file of WALK_FILES) {
    const text = readFileSync(new URL(file, dir), 'utf8'), match = DECLARATION(name.replace(/\$/g, '\\$')).exec(text);
    if (!match) continue;
    let start = match.index;
    while (start > 0) {
      const previous = text.lastIndexOf('\n', start - 2) + 1, line = text.slice(previous, start - 1);
      if (!/^(\/\/|\/\*\*|\s\*)/.test(line)) break;
      start = previous;
    }
    const rest = text.slice(match.index + 1), next = /\n(?=[^\s}\])])/.exec(rest);
    const end = next ? match.index + 1 + next.index + 1 : text.length;
    return text.slice(start, end);
  }
  throw Error('No walk declaration named ' + name);
}
export const walkDeclarations = (...names) => names.map(walkDeclaration).join('\n');
