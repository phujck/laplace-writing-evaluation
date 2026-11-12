"""THE SYSTEM DESCRIPTION: the repository's one owner map, and the operations that use it.

The theory this follows (company-development-roadmap, theory-to-architecture synthesis, sections 6-8): a system that
changes itself must represent its own parts, their relationships, the operations they carry and the evaluators that
judge them, as qualified objects; ownership comes before any storage migration; a change should select the
consumers whose consumed meaning it touches and leave the rest current.

``description.json`` beside this module is the authority. It declares every subsystem of everything this repository
owns (source packages, browser and canon resources, profiles, scripts and tools, package and container declarations,
explanation documents) with its kind and layer, the domains it may use, its contracts, explanations and evaluators,
the deliberately retained boundaries with their exact consumers and retirement conditions, the shipped
distributions, and the capabilities whose operations are described end to end (contract, code, help, explanation,
evaluator, consumers, observables). This module is the one reader of that file and the one place its relationships
are computed:

  load()                 the description, or a finite list of shape problems
  owner(path)            the one subsystem that owns a repository path (exactly one, or a named problem)
  graph(root)            the measured import graph of source, scripts, tools and tests (AST only; nothing imported)
  check(root)            coverage, layer law, retained boundaries (exact: a ratchet), distributions, capabilities
  cone(root, paths)      the affected cone of a change: owners, importing modules, evaluators, explanations,
                         contracts, capabilities touched, and the subsystems structurally outside that import
                         cone (which is not independent-review CURRENT/STALE standing or semantic sufficiency)
  capability(id)         one operation-bearing self-description with every reference resolved
  entry(), choices(task)  the declared system entry: purpose, owner-qualified subsystem and capability references,
                         and the subsystems whose declared labels a task's words name (choices, never a guess)
  render_front_door()    the subsystem section of the human front door (docs/writing-code-overview.md), checked

Layers: core (0) owns the common qualified identity, record, action and effect mechanics; a domain (1) owns
meaningful state, transformations and adequacy criteria and may use core and the domains it declares; an adapter
(2) is an inbound door (native tools, HTTP, desktop or browser, command line) and may use anything below it. An
import from a lower layer into a higher one, or into an undeclared domain, is a violation unless the description
retains it as an exact boundary. Tests are evaluators: their owners are derived from the modules they import.
"""
from __future__ import annotations

import ast
import fnmatch
import json
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = 'laplace.system-description/1'
DESCRIPTION = Path(__file__).with_name('description.json')
LAYERS = {'core': 0, 'domain': 1, 'adapter': 2}
#: the repository areas whose files every subsystem together must own (tests are derived evaluators, below)
OWNED_ROOTS = ('src', 'scripts', 'tools', 'profiles', 'deploy', 'docs')
OWNED_FILES = ('pyproject.toml', 'atlas/pyproject.toml', 'uv.lock', 'pytest.ini', 'runtime_profiles.toml')
EVALUATOR_ROOTS = ('tests', 'atlas/tests')
_SKIP_PARTS = {'__pycache__', '.pytest_cache', 'node_modules'}


def repository_root() -> Path:
    from laplace.core import checkout
    return Path(checkout.repo_root()).resolve()


# ------------------------------------------------------------------------------------------------ the description
def load(path: Path | None = None) -> dict:
    value = json.loads(Path(path or DESCRIPTION).read_text(encoding='utf-8'))
    problems = shape_problems(value)
    if problems:
        raise ValueError('The system description is malformed: ' + '; '.join(problems[:6]))
    return value


def shape_problems(value: Any) -> list[str]:
    problems = []
    if not isinstance(value, dict) or value.get('schema_version') != SCHEMA:
        return ['schema_version is not ' + SCHEMA]
    ids = set()
    for index, row in enumerate(value.get('subsystems') or []):
        where = 'subsystems[%d]' % index
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or not row['id']:
            problems.append(where + ' has no id'); continue
        if row['id'] in ids:
            problems.append(where + ' repeats id ' + row['id'])
        ids.add(row['id'])
        if row.get('kind') not in LAYERS:
            problems.append(where + ' kind is not one of ' + ', '.join(LAYERS))
        for key in ('modules', 'files', 'uses', 'contracts', 'explanation', 'evaluators'):
            if not isinstance(row.get(key, []), list) or any(not isinstance(item, str) for item in row.get(key, [])):
                problems.append('%s.%s is not a list of strings' % (where, key))
        if not isinstance(row.get('summary'), str) or not row['summary']:
            problems.append(where + ' has no summary')
    for index, row in enumerate(value.get('subsystems') or []):
        for used in row.get('uses', []) if isinstance(row, dict) else []:
            if used not in ids:
                problems.append('subsystems[%d] uses unknown %s' % (index, used))
    for index, row in enumerate(value.get('retained') or []):
        where = 'retained[%d]' % index
        if not isinstance(row, dict):
            problems.append(where + ' is not an object'); continue
        for key in ('id', 'owner', 'reason', 'retire_when'):
            if not isinstance(row.get(key), str) or not row[key]:
                problems.append('%s.%s is missing' % (where, key))
        if not isinstance(row.get('edges'), list) or any(not (isinstance(edge, list) and len(edge) == 2) for edge in row.get('edges') or []):
            problems.append(where + '.edges is not a list of [importer, imported] pairs')
    for index, row in enumerate(value.get('capabilities') or []):
        if not isinstance(row, dict) or not isinstance(row.get('id'), str) or row.get('owner') not in ids:
            problems.append('capabilities[%d] has no id or an unknown owner' % index)
    if not isinstance(value.get('distributions'), list) or not value['distributions']:
        problems.append('distributions are missing')
    return problems


def subsystems(description: dict) -> dict[str, dict]:
    return {row['id']: row for row in description['subsystems']}


# ------------------------------------------------------------------------------------------------ the system entry
ENTRY_SCHEMA = 'laplace.system-entry/1'
#: words a task sentence carries that name no subsystem (choices are made only from declared words)
_TASK_STOPWORDS = frozenset(
    'about across affect affecting affects after also and any are because been being between both but can current '
    'currently does done each every find from have into its more most must need needs not only other over owns that '
    'the their them then there these they this those through under upon what when where which while with within work '
    'would your'.split())


def subsystem_reference(row: dict) -> dict:
    """A declared subsystem as an owner-qualified reference: the system description (core.identity) declares it."""
    from laplace.core.identity import reference
    return reference('core.identity', 'subsystem', {'id': row['id']})


def capability_reference(row: dict) -> dict:
    from laplace.core.identity import reference
    return reference(row['owner'], 'capability', {'id': row['id']})


def entry(description: dict | None = None) -> dict:
    """The declared entry an outer adapter composes: purpose, subsystem and capability references, structural only.

    It states what is declared here (ownership, layers, operation-bearing capabilities). It does not read any
    domain's records: which Work affects a subsystem is the Work owner's answer, composed by the adapter."""
    description = description or load()
    rows = [{'reference': subsystem_reference(row), 'layer': row['kind'], 'summary': row['summary'],
             'uses': list(row.get('uses') or []), 'explanation': list(row.get('explanation') or [])}
            for row in description['subsystems']]
    capabilities = [{'reference': capability_reference(row), 'summary': row['summary'],
                     'operation': row.get('operation') or {}} for row in description.get('capabilities', [])]
    return {'schema_version': ENTRY_SCHEMA, 'purpose': description['summary'], 'subsystems': rows,
            'capabilities': capabilities}


def _words(text: str) -> set[str]:
    import re
    return {word for word in re.findall(r'[a-z]+', text.lower()) if len(word) > 3 and word not in _TASK_STOPWORDS}


def choices(task: str, description: dict | None = None) -> list[dict]:
    """The subsystems whose declared id or summary contain a word of the task, most shared words first.

    A deterministic match on declared text: it returns labelled choices with the words that matched and never
    selects one owner for the caller. An empty list means no declared word was named, not that nothing applies."""
    description = description or load()
    wanted = _words(task or '')
    found = []
    for row in description['subsystems']:
        terms = sorted(wanted & (_words(row['summary']) | _words(row['id'].replace('.', ' '))))
        if terms:
            found.append({'reference': subsystem_reference(row), 'terms': terms})
    return sorted(found, key=lambda item: (-len(item['terms']), item['reference']['identity']['id']))


# ------------------------------------------------------------------------------------------------ ownership
def module_name(relative: str) -> str | None:
    """The importable name of a source file (``src/<package>/...py``), or None."""
    path = PurePosixPath(relative)
    if path.parts[:1] != ('src',) or path.suffix != '.py':
        return None
    parts = list(path.with_suffix('').parts[1:])
    if parts and parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts) or None


def _specificity(pattern: str) -> int:
    """More literal characters is more specific; an exact name beats any wildcard pattern of the same length."""
    literal = ''.join(ch for ch in pattern if ch not in '*?[]')
    return len(literal) * 2 + (1 if not set(pattern) & set('*?[') else 0)


def _match(description: dict, key: str, field: str) -> list[tuple[int, str, str]]:
    found = []
    for row in description['subsystems']:
        for pattern in row.get(field, []):
            if fnmatch.fnmatchcase(key, pattern):
                found.append((_specificity(pattern), row['id'], pattern))
    return sorted(found, reverse=True)


def owner(description: dict, relative: str) -> tuple[str | None, str | None]:
    """(subsystem id, None) for the one most specific declared owner of a repository path, else (None, problem).
    Source modules are matched by importable name against ``modules``; every other file by path against ``files``."""
    name = module_name(relative)
    found = _match(description, name, 'modules') if name else []
    if not found:
        found = _match(description, relative, 'files')
    if not found:
        return None, 'no subsystem owns ' + relative
    best = [row for row in found if row[0] == found[0][0]]
    if len({row[1] for row in best}) > 1:
        return None, 'ambiguous owners for %s: %s' % (relative, ', '.join(sorted({row[1] for row in best})))
    return best[0][1], None


def owned_paths(root: Path) -> list[str]:
    root = Path(root)
    paths = []
    for area in OWNED_ROOTS:
        base = root / area
        if base.is_dir():
            for path in base.rglob('*'):
                if path.is_file() and not (set(path.relative_to(root).parts) & _SKIP_PARTS) and path.suffix != '.pyc':
                    paths.append(path.relative_to(root).as_posix())
    paths.extend(name for name in OWNED_FILES if (root / name).is_file())
    return sorted(paths)


# ------------------------------------------------------------------------------------------------ the import graph
@lru_cache(maxsize=4)
def _graph(root: str, stamp: tuple) -> dict:
    root_path = Path(root)
    modules = {}
    for path in sorted((root_path / 'src').rglob('*.py')):
        if _SKIP_PARTS & set(path.parts):
            continue
        name = module_name(path.relative_to(root_path).as_posix())
        if name:
            modules[name] = path.relative_to(root_path).as_posix()

    def resolve(name: str) -> str | None:
        while name and name not in modules:
            name = name.rpartition('.')[0]
        return name or None
    edges: dict[str, list[str]] = {}
    files: dict[str, str] = {}
    for area in ('src', 'scripts', 'tools', *EVALUATOR_ROOTS):
        base = root_path / area
        if not base.is_dir():
            continue
        for path in sorted(base.rglob('*.py')):
            if _SKIP_PARTS & set(path.parts):
                continue
            relative = path.relative_to(root_path).as_posix()
            key = module_name(relative) if area == 'src' else relative
            try:
                tree = ast.parse(path.read_text(encoding='utf-8'))
            except (SyntaxError, UnicodeDecodeError):
                edges[key], files[key] = [], relative
                continue
            package = ''
            if area == 'src':
                package = key if path.name == '__init__.py' else key.rpartition('.')[0]
            found = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        target = resolve(alias.name)
                        if target:
                            found.add(target)
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        parts = package.split('.') if package else []
                        anchor = '.'.join(parts[:len(parts) - node.level + 1]) if node.level > 1 else package
                        target = (anchor + '.' + node.module) if node.module else anchor
                    else:
                        target = node.module or ''
                    for alias in node.names:
                        resolved = resolve(target + '.' + alias.name) or resolve(target)
                        if resolved:
                            found.add(resolved)
            edges[key] = sorted(found - {key})
            files[key] = relative
    return {'modules': modules, 'edges': edges, 'files': files}


def graph(root: Path) -> dict:
    root = Path(root).resolve()
    stamp = tuple(sorted((str(p), p.stat().st_mtime_ns) for area in ('src', 'scripts', 'tools', *EVALUATOR_ROOTS)
                         if (root / area).is_dir() for p in (root / area).rglob('*.py') if not (_SKIP_PARTS & set(p.parts))))
    return _graph(str(root), stamp)


def module_owner(description: dict, modules: dict[str, str], name: str) -> str | None:
    return owner(description, modules[name])[0] if name in modules else None


def violations(description: dict, measured: dict) -> list[tuple[str, str, str]]:
    """Every source import that breaks the layer law: (importer, imported, reason)."""
    table = subsystems(description)
    modules = measured['modules']
    out = []
    for importer, targets in measured['edges'].items():
        if importer not in modules:
            continue
        source = module_owner(description, modules, importer)
        for imported in targets:
            target = module_owner(description, modules, imported)
            if source is None or target is None or source == target:
                continue
            a, b = table[source], table[target]
            if LAYERS[a['kind']] < LAYERS[b['kind']]:
                out.append((importer, imported, '%s %s imports %s %s' % (a['kind'], source, b['kind'], target)))
            elif a['kind'] == b['kind'] == 'domain' and target not in a.get('uses', []):
                out.append((importer, imported, 'domain %s uses undeclared domain %s' % (source, target)))
            elif a['kind'] == b['kind'] == 'core' and target not in a.get('uses', []):
                out.append((importer, imported, 'core %s uses undeclared core %s' % (source, target)))
    return sorted(out)


def derived_evaluators(description: dict, measured: dict) -> dict[str, list[str]]:
    """Each subsystem's evaluators: the test files that import one of its modules, plus its declared evaluator globs."""
    modules = measured['modules']
    out: dict[str, set[str]] = {row['id']: set() for row in description['subsystems']}
    for key, targets in measured['edges'].items():
        relative = measured['files'][key]
        if not relative.startswith(tuple(root + '/' for root in EVALUATOR_ROOTS)):
            continue
        for imported in targets:
            target = module_owner(description, modules, imported)
            if target:
                out[target].add(relative)
    for row in description['subsystems']:
        for pattern in row.get('evaluators', []):
            out[row['id']].update(path for path in measured['files'].values() if fnmatch.fnmatchcase(path, pattern))
    return {key: sorted(value) for key, value in out.items()}


# ------------------------------------------------------------------------------------------------ retained facades
def facade_forwards(root: Path, facade: str) -> set[str]:
    """The names a facade re-exports from owners: its own top-level ``from laplace... import name [as alias]``."""
    path = Path(root) / 'src' / (facade.replace('.', '/') + '.py')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    return {alias.asname or alias.name for node in tree.body if isinstance(node, ast.ImportFrom) and node.level == 0
            and (node.module or '').startswith('laplace') for alias in node.names}


def facade_consumers(root: Path, facade: str) -> list[str]:
    """Every file outside the facade that reaches one of its forwarded owner names through it (a ``from facade import
    name`` or an ``alias.name`` use after ``from laplace import facade``): the consumers a retained facade serves."""
    root = Path(root)
    forwards = facade_forwards(root, facade)
    parent, _, short = facade.rpartition('.')
    facade_file = 'src/' + facade.replace('.', '/') + '.py'
    out = []
    for area in ('src', 'scripts', 'tools', *EVALUATOR_ROOTS):
        base = root / area
        if not base.is_dir():
            continue
        for path in sorted(base.rglob('*.py')):
            relative = path.relative_to(root).as_posix()
            if _SKIP_PARTS & set(path.parts) or relative == facade_file:
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            if short not in text:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            aliases, uses = set(), False
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.level == 0:
                    if node.module == facade and any(alias.name in forwards for alias in node.names):
                        uses = True
                    elif node.module == parent:
                        aliases.update(alias.asname or alias.name for alias in node.names if alias.name == short)
                elif isinstance(node, ast.Import):
                    aliases.update(alias.asname for alias in node.names if alias.name == facade and alias.asname)
            if not uses and aliases:
                uses = any(isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases
                           and node.attr in forwards for node in ast.walk(tree))
            if uses:
                out.append(relative)
    return out


# ------------------------------------------------------------------------------------------------ the check
def check(root: Path | None = None, description: dict | None = None) -> dict:
    """Every relationship the description claims, measured against the tree. ``ok`` only when nothing is open."""
    root = Path(root or repository_root()).resolve()
    description = description or load()
    measured = graph(root)
    problems: list[dict] = []
    unowned, ambiguous, counts = [], [], {}
    for relative in owned_paths(root):
        found, problem = owner(description, relative)
        if found is None:
            (ambiguous if problem and problem.startswith('ambiguous') else unowned).append(relative)
        else:
            counts[found] = counts.get(found, 0) + 1
    for relative in unowned:
        problems.append({'kind': 'unowned', 'path': relative})
    for relative in ambiguous:
        problems.append({'kind': 'ambiguous', 'path': relative})
    for row in description['subsystems']:
        if not counts.get(row['id']):
            problems.append({'kind': 'empty-subsystem', 'subsystem': row['id']})
    measured_violations = violations(description, measured)
    retained_edges = {}
    for row in description.get('retained', []):
        for importer, imported in row['edges']:
            retained_edges[(importer, imported)] = row['id']
    actual = {(importer, imported) for importer, imported, _reason in measured_violations}
    for importer, imported, reason in measured_violations:
        if (importer, imported) not in retained_edges:
            problems.append({'kind': 'layer-violation', 'importer': importer, 'imported': imported, 'reason': reason})
    for edge, boundary in retained_edges.items():
        if edge not in actual:
            problems.append({'kind': 'retained-edge-no-longer-exists', 'boundary': boundary, 'importer': edge[0], 'imported': edge[1],
                             'reason': 'the consumer was converted: remove it from the retained boundary (the list only shrinks)'})
    problems.extend(distribution_problems(root, description, measured))
    for row in description.get('retained_facades', []):
        actual = set(facade_consumers(root, row['facade']))
        declared = set(row['consumers'])
        for relative in sorted(actual - declared):
            problems.append({'kind': 'facade-consumer-not-retained', 'facade': row['facade'], 'path': relative,
                             'reason': 'reach the owner directly (a scoped manual migration checked by its actual callers and evaluators) instead of adding a consumer'})
        for relative in sorted(declared - actual):
            problems.append({'kind': 'retained-facade-consumer-gone', 'facade': row['facade'], 'path': relative,
                             'reason': 'this consumer no longer uses forwards: remove it (the list only shrinks)'})
    problems.extend(front_door_problems(root, description))
    for row in description.get('capabilities', []):
        problems.extend({'kind': 'capability', 'capability': row['id'], 'reason': reason} for reason in capability_problems(root, row))
    for row in description['subsystems']:
        for key in ('contracts', 'explanation'):
            for relative in row.get(key, []):
                if not (root / relative.split('#', 1)[0]).exists():
                    problems.append({'kind': 'missing-reference', 'subsystem': row['id'], 'field': key, 'path': relative})
    return {'schema_version': 'laplace.system-check/1', 'ok': not problems, 'problems': problems,
            'owned_files': sum(counts.values()), 'per_subsystem': dict(sorted(counts.items())),
            'violations_retained': len(retained_edges), 'source_modules': len(measured['modules']),
            'facade_consumers_retained': {row['facade']: len(row['consumers']) for row in description.get('retained_facades', [])}}


def distribution_problems(root: Path, description: dict, measured: dict) -> list[dict]:
    """Every top-level source package is shipped by exactly one declared distribution, and each distribution's
    declaration file says what the description says it ships. A source check of the declarations: it proves no
    archive, wheel or curated export carries every resource (the export selection holds its own closure)."""
    problems = []
    packages = sorted({name.split('.')[0] for name in measured['modules']})
    shipped: dict[str, list[str]] = {name: [] for name in packages}
    for row in description['distributions']:
        declaration = root / row['declaration']
        if not declaration.is_file():
            problems.append({'kind': 'distribution', 'distribution': row['name'], 'reason': 'declaration file is missing'}); continue
        text = declaration.read_text(encoding='utf-8')
        if 'name = "%s"' % row['name'] not in text:
            problems.append({'kind': 'distribution', 'distribution': row['name'], 'reason': 'declaration names another project'})
        for package in row['packages']:
            if '"%s*"' % package not in text:
                problems.append({'kind': 'distribution', 'distribution': row['name'], 'reason': 'declaration does not include %s*' % package})
            if package in shipped:
                shipped[package].append(row['name'])
    for package, rows in shipped.items():
        if len(rows) != 1:
            problems.append({'kind': 'distribution', 'package': package,
                             'reason': 'shipped by %s distributions' % (len(rows) or 'no') + ('' if not rows else ': ' + ', '.join(rows))})
    return problems


# ------------------------------------------------------------------------------------------------ capabilities
def _symbol_exists(root: Path, reference: str) -> bool:
    """``path:Symbol`` or ``path:Class.method`` names a definition in that file (AST only)."""
    relative, _, symbol = reference.partition(':')
    path = root / relative
    if not path.is_file():
        return False
    if not symbol:
        return True
    try:
        tree = ast.parse(path.read_text(encoding='utf-8'))
    except SyntaxError:
        return False
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            if isinstance(node, ast.ClassDef):
                names.update(node.name + '.' + child.name for child in node.body if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)))
        elif isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return symbol in names


def capability_problems(root: Path, row: dict) -> list[str]:
    problems = []
    for key in ('contract', 'code', 'help', 'explanation', 'evaluator', 'consumers'):
        if not row.get(key):
            problems.append('declares no ' + key)
    for key in ('contract', 'code', 'help', 'consumers'):
        for reference in row.get(key) or []:
            if not _symbol_exists(root, reference):
                problems.append('%s reference does not resolve: %s' % (key, reference))
    for reference in row.get('explanation') or []:
        relative, _, anchor = reference.partition('#')
        path = root / relative
        if not path.is_file():
            problems.append('explanation file is missing: ' + relative)
        elif anchor and anchor not in path.read_text(encoding='utf-8'):
            problems.append('explanation anchor text is missing: ' + reference)
    for reference in row.get('evaluator') or []:
        relative, _, name = reference.partition('::')
        if not (root / relative).is_file() or (name and 'def ' + name not in (root / relative).read_text(encoding='utf-8')):
            problems.append('evaluator does not resolve: ' + reference)
    observables = row.get('observables') or {}
    for key in ('admission', 'effects', 'refusals', 'obligations'):
        if not observables.get(key):
            problems.append('observable %s is not stated' % key)
    if not (row.get('views') or {}).get('coarse') or not (row.get('views') or {}).get('fine'):
        problems.append('coarse and fine views are not both stated')
    return problems


def capability(identifier: str, description: dict | None = None, root: Path | None = None) -> dict:
    description = description or load()
    row = next((item for item in description.get('capabilities', []) if item['id'] == identifier), None)
    if row is None:
        raise ValueError('Unknown capability: ' + identifier)
    return {**row, 'problems': capability_problems(Path(root or repository_root()), row)}


# ------------------------------------------------------------------------------------------------ the human front door
FRONT_DOOR = 'docs/writing-code-overview.md'
FRONT_BEGIN, FRONT_END = '<!-- laplace.system: subsystems (generated; python -m laplace.system front-door) -->', '<!-- /laplace.system -->'


def render_front_door(description: dict) -> str:
    """The subsystem table the human front door carries, rendered from the description (never hand-edited)."""
    rows = ['| Subsystem | Kind | Owns | Uses |', '|---|---|---|---|']
    for row in description['subsystems']:
        rows.append('| `%s` | %s | %s | %s |' % (row['id'], row['kind'], row['summary'].replace('|', '/'),
                                                ', '.join('`%s`' % used for used in row.get('uses', [])) or '—'))
    retained = ['- **%s** (%d edges, owner `%s`): %s Retire when: %s' % (row['id'], len(row['edges']), row['owner'], row['reason'], row['retire_when'])
                for row in description.get('retained', [])]
    facades = ['- `%s`: %d consumers reach owners through its old names. Retire when: %s' % (row['facade'], len(row['consumers']), row['retire_when'])
               for row in description.get('retained_facades', [])]
    capabilities = ['- `%s` (owner `%s`): %s' % (row['id'], row['owner'], row['summary']) for row in description.get('capabilities', [])]
    return '\n'.join([FRONT_BEGIN, *rows, '', 'Retained boundaries (each list only shrinks; `python -m laplace.system check` fails on a new one):', '',
                      *retained, *facades, '', 'Capabilities described end to end (contract, code, help, explanation, evaluator, consumers, observables):', '',
                      *capabilities, FRONT_END])


def front_door_problems(root: Path, description: dict) -> list[dict]:
    path = Path(root) / FRONT_DOOR
    text = path.read_text(encoding='utf-8') if path.is_file() else ''
    start, end = text.find(FRONT_BEGIN), text.find(FRONT_END)
    if start < 0 or end < 0:
        return [{'kind': 'front-door', 'path': FRONT_DOOR, 'reason': 'the generated subsystem section is missing'}]
    if text[start:end + len(FRONT_END)] != render_front_door(description):
        return [{'kind': 'front-door', 'path': FRONT_DOOR, 'reason': 'the subsystem section differs from the description; run python -m laplace.system front-door --write'}]
    return []


def write_front_door(root: Path, description: dict) -> bool:
    path = Path(root) / FRONT_DOOR
    text = path.read_text(encoding='utf-8')
    start, end = text.find(FRONT_BEGIN), text.find(FRONT_END)
    if start < 0 or end < 0:
        raise ValueError('The front door has no laplace.system section markers.')
    new = text[:start] + render_front_door(description) + text[end + len(FRONT_END):]
    if new != text:
        path.write_text(new, encoding='utf-8')
    return new != text


# ------------------------------------------------------------------------------------------------ the affected cone
def cone(root: Path | None, paths: list[str], description: dict | None = None, *, depth: int = 2) -> dict:
    """The bounded affected cone of a change to ``paths`` (repository-relative): their owners; the source modules
    importing a changed module (up to ``depth`` import steps) and their owners; the evaluators that import any
    module in the cone; the explanations and contracts of every affected subsystem; the capabilities whose
    declared contract, code, help, explanation or evaluator includes a changed path; and the subsystems outside
    that selected import cone. Purely structural: outside the cone is not an independent-review CURRENT/STALE
    standing and not semantic sufficiency (a consumer reached through a callable or a file is found by its
    evaluator, not here); a semantic change still has to name the consumed meaning. The cone bounds where to
    look first; it certifies nothing."""
    root = Path(root or repository_root()).resolve()
    description = description or load()
    measured = graph(root)
    modules = measured['modules']
    importers: dict[str, set[str]] = {}
    for key, targets in measured['edges'].items():
        for target in targets:
            importers.setdefault(target, set()).add(key)
    changed_modules = {module_name(path) for path in paths if module_name(path) in modules}
    frontier, seen = set(changed_modules), set(changed_modules)
    for _ in range(max(0, depth)):
        frontier = {key for target in frontier for key in importers.get(target, set()) if key in modules} - seen
        seen |= frontier
    owners_changed = sorted({owner(description, path)[0] for path in paths if owner(description, path)[0]})
    affected = sorted({module_owner(description, modules, name) for name in seen if module_owner(description, modules, name)} | set(owners_changed))
    evaluators = sorted({measured['files'][key] for key, targets in measured['edges'].items()
                         if measured['files'][key].startswith(tuple(r + '/' for r in EVALUATOR_ROOTS)) and set(targets) & seen})
    table = subsystems(description)
    touched = []
    for row in description.get('capabilities', []):
        references = [reference.partition(':')[0].partition('::')[0].partition('#')[0]
                      for key in ('contract', 'code', 'help', 'explanation', 'evaluator', 'consumers') for reference in row.get(key) or []]
        if set(references) & set(paths):
            touched.append(row['id'])
    return {'schema_version': 'laplace.system-cone/1', 'changed': sorted(paths), 'owners': owners_changed,
            'modules': sorted(seen), 'affected_subsystems': affected,
            'unaffected_subsystems': sorted(set(table) - set(affected)),
            'unaffected_meaning': 'structurally outside the selected import cone; not independent-review CURRENT/STALE and not semantic sufficiency',
            'evaluators': evaluators,
            'explanations': sorted({doc for sid in affected for doc in table[sid].get('explanation', [])}),
            'contracts': sorted({doc for sid in affected for doc in table[sid].get('contracts', [])}),
            'capabilities': touched, 'depth': depth}
