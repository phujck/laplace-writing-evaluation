#!/usr/bin/env python3
"""Verify an untouched evaluator export without model calls or source writes."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True   # the verifier writes nothing under an export, bytecode included (shared read-only contract, W5-R2)

from laplace.writing import records as writing_records  # noqa: E402

import argparse  # noqa: E402
import importlib.util  # noqa: E402
import json
import os
import re
from pathlib import Path
from urllib.parse import unquote

# THE BYTE LAYER is shared with the read-only inspector (scripts/inspect_writing_export.py), which runs without the kernel;
# this verifier adds the application's own semantics on top of it and therefore needs a working kernel (Work5, 2026-10-20).
# the sibling scripts (manifest builder, portable-links projection) resolve from this file's own directory, however the
# interpreter was started (safe-path mode, -I, an exported checkout run from elsewhere): the exporter does the same
sys.path.insert(0, str(Path(__file__).resolve().parent))
_BYTES_SPEC = importlib.util.spec_from_file_location('writing_export_bytes', Path(__file__).resolve().with_name('writing_export_bytes.py'))
_bytes_layer = importlib.util.module_from_spec(_BYTES_SPEC)
_BYTES_SPEC.loader.exec_module(_bytes_layer)
sha = _bytes_layer.sha
repository_scope = _bytes_layer.repository_scope
Fence = _bytes_layer.Fence


def import_scope(imports, session_projects, projects):
    failures = []
    for row in imports:
        if (row.get('project') not in projects
                or session_projects.get(row.get('session_id')) != row.get('project')):
            failures.append({'reason': 'session import crosses project boundary',
                             'session_id': row.get('session_id'),
                             'project': row.get('project')})
    return failures


def alias_closure(root, report):
    """Every PINNED portable source alias target (a primary carrying original_sha256 and each
    version) must be a declared, present export file with exactly the pinned bytes: a declared
    version whose file never travelled, or whose declared pin differs, is a dangling alias,
    never a success. Unpinned project-relative address aliases (a run's producer directory,
    an optional marker that was absent when recorded) make no byte claim and are left as before."""
    portable = root / 'writing-portability.json'
    if not portable.is_file():
        return []
    declared = {row['path']: row['sha256'] for row in report['copied_files'] + report['derived_files']}
    failures = []
    try:
        index = json.loads(portable.read_text(encoding="utf-8"))
        aliases = index.get('source_aliases') or {}
    except (OSError, ValueError) as exc:
        return [{'path': 'writing-portability.json', 'reason': 'unreadable portability manifest: ' + str(exc)[:200]}]
    proofs = index.get('alias_proofs')
    if isinstance(proofs, dict):
        # the proofs travel beside the resolver index (full-collection index): declared, exact and complete
        rel = proofs.get('path')
        if not isinstance(rel, str) or rel not in declared or declared[rel] != proofs.get('sha256') or not (root / rel).is_file():
            failures.append({'path': rel, 'reason': 'alias proofs are not the declared exported file named by the index'})
        else:
            try:
                carried = json.loads((root / rel).read_text(encoding='utf-8'))
                if (carried.get('source_manifest_sha256') != index.get('source_manifest_sha256')
                        or len(carried.get('proofs') or []) != proofs.get('count')):
                    failures.append({'path': rel, 'reason': 'alias proofs do not match the portability index'})
            except (OSError, ValueError) as exc:
                failures.append({'path': rel, 'reason': 'unreadable alias proofs: ' + str(exc)[:200]})
    def pin(value):
        value = str(value or '').strip().lower()
        return value if value.startswith('sha256:') else ('sha256:' + value if value else None)
    def check(spelling, entry, label, expected_pin):
        rel = entry.get('path') if isinstance(entry, dict) else None
        expected = expected_pin or pin(entry.get('original_sha256'))
        if not expected:
            return   # an unpinned address translation claims no exact bytes
        if not isinstance(rel, str) or rel not in declared:
            reason = 'alias target is not a declared export file'
        elif expected and (declared[rel] != expected or pin(entry.get('original_sha256')) != expected):
            reason = 'alias target pin differs from the declared export file'
        elif not (root / rel).is_file():
            reason = 'alias target file is missing'
        else:
            return
        failures.append({'path': rel if isinstance(rel, str) else None, 'alias': spelling, 'version': label, 'reason': 'dangling source alias: ' + reason})
    for spelling, alias in aliases.items():
        if not isinstance(alias, dict):
            failures.append({'alias': spelling, 'reason': 'dangling source alias: alias is not an exact target'})
            continue
        check(spelling, alias, 'primary', None)
        versions = alias.get('versions') or {}
        for key, entry in (versions.items() if isinstance(versions, dict) else []):
            expected = pin(key)
            if not expected or not isinstance(entry, dict) or entry.get('path') == alias.get('path'):
                failures.append({'alias': spelling, 'version': key, 'reason': 'dangling source alias: version must pin a distinct exact target'})
                continue
            check(spelling, entry, key, expected)
    return failures


def _home_inventory(root, home, inventory):
    """The ACTUAL files under one exported project home (never the declared copy list): every regular file, with each
    symlink (file or directory) reported and never followed."""
    actual, problems = {}, []
    base = root / home
    if base.is_symlink():
        return actual, [{'path': home, 'reason': 'a selected project home is a symlink in the export'}]
    for directory, dirs, files in os.walk(base, followlinks=False):
        for name in list(dirs):
            path = Path(directory) / name
            if path.is_symlink():
                problems.append({'path': path.relative_to(root).as_posix(), 'reason': 'a symlinked directory is present in the export'})
                dirs.remove(name)
        for name in files:
            path = Path(directory) / name
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                problems.append({'path': rel, 'reason': 'a symlink is present in the export'})
            elif path.is_file():
                actual[rel] = path.stat().st_size
            else:
                problems.append({'path': rel, 'reason': 'a non-regular file is present in the export'})
    return actual, problems


def selection_closure(root, report, inventory, project_dirs):
    """The travelled reviewed selection, applied again to the ACTUAL exported bytes (repair1 RP-R1): under each policy
    project's home the export holds exactly its included files with their pinned bytes, plus any declared derived
    output there. Every other actual file -- an excluded file reintroduced, an unreviewed addition, a private/runtime/
    secret name, an oversized file or a symlink -- fails with its exact path; nothing is ignored by folder name. The
    same policy is what a re-export consumes."""
    declared = report.get('selection_policy')
    if not declared:
        return []
    path = root / declared.get('path', '')
    if not path.is_file() or sha(path) != declared.get('sha256'):
        return [{'path': declared.get('path'), 'reason': 'selection policy identity mismatch'}]
    try:
        policy = inventory.selection_policy(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError) as exc:
        return [{'path': declared.get('path'), 'reason': 'unreadable selection policy: ' + str(exc)[:200]}]
    copied = {row['path']: row for row in report['copied_files']}
    derived = {row['path'] for row in report['derived_files']}
    failures = []
    for project, rows in policy.items():
        home = project_dirs.get(project)
        if not home:
            failures.append({'project': project, 'reason': 'selection policy names an unselected project'})
            continue
        included = {rel: row for rel, row in rows.items() if row['decision'] == 'include'}
        actual, problems = _home_inventory(root, home, inventory)
        failures.extend({'project': project, **row} for row in problems)
        # the perimeter applies to EVERY actual file first (repair2 RP-R1-R1): a copied or derived label never
        # declassifies a private, runtime or secret path; only then may a declared derived output be allowed
        private = {rel for rel in actual if inventory._excluded(Path(rel))}
        for rel in sorted(private):
            failures.append({'project': project, 'path': rel, 'reason': 'a private, runtime or secret file is present in the export'})
        allowed = set(included) | {rel for rel in derived if Path(rel).is_relative_to(Path(home))}
        for rel in sorted(set(actual) - allowed - private):
            decision = (rows.get(rel) or {}).get('decision')
            reason = ('an excluded file is present in the export' if decision == 'exclude'
                      else 'a file present in the export is not in the reviewed selection')
            failures.append({'project': project, 'path': rel, 'reason': reason})
        for rel, size in sorted(actual.items()):
            if size > inventory.LARGE_FILE_BYTES:
                failures.append({'project': project, 'path': rel, 'reason': 'file exceeds the per-file export ceiling'})
        for rel, row in sorted(included.items()):
            if rel not in actual:
                failures.append({'project': project, 'path': rel, 'reason': 'reviewed included file is missing from the export'})
            elif rel not in copied:
                failures.append({'project': project, 'path': rel, 'reason': 'reviewed included file was not declared as exported'})
            elif copied[rel]['sha256'] != row['sha256'] or sha(root / rel) != row['sha256']:
                failures.append({'project': project, 'path': rel, 'reason': 'exported bytes differ from the reviewed pin'})
    return failures


# inline [text](target "title") / [text](<target with spaces>) and reference definitions [id]: target
_LINK = re.compile(r'\]\(\s*(<[^>\n]+>|[^)\s]+)(?:\s+(?:"[^"]*"|\'[^\']*\'|\([^)]*\)))?\s*\)')
_REFERENCE = re.compile(r'^ {0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|\S+)', re.M)
_SCHEME = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:')
LINK_STATUSES = ('resolved', 'missing-selected', 'missing-common', 'unselected-project')


def document_links(root, report, owners):
    """Every relative link of an exported Markdown entry document (README, AGENTS, docs/*.md), classified by its
    actual owner (repair1 RP-R2): resolved inside the export; missing under a SELECTED project's home (project
    directory, registered TeX root or manuscript directory) or a selected source binding (failure: a selected file did
    not travel); missing under the home of a registered project this export did not select (reported with that
    project's name, never copied); otherwise a missing common engine/script/doc input (failure). ``owners`` is
    {'selected': {project: [homes]}, 'unselected': {project: [homes]}, 'bindings': {path: [projects]}}."""
    rows, failures = [], []
    if owners and all(isinstance(value, str) for value in owners.values()):
        owners = {'selected': {project: [home] for project, home in owners.items()}}   # the earlier {project: dir} form
    pins = {row['path']: row.get('sha256') for row in report['copied_files'] + report['derived_files']}
    declared = set(pins)
    # a docs/ source whose exact bytes ARE a generated root entry (README.md, AGENTS.md) is authored for that location
    # and checked there once (its links are root-relative); any other copy is checked where it lies
    entries = {pins[name] for name in ('README.md', 'AGENTS.md', 'REVIEWER_GUIDE.md') if name in pins}
    declared -= {rel for rel in declared if rel.startswith('docs/') and pins[rel] and pins[rel] in entries}
    selected, unselected = owners.get('selected') or {}, owners.get('unselected') or {}
    bindings = owners.get('bindings') or {}
    def owner(path, homes):
        return next((project for project, places in homes.items()
                     if any(path.is_relative_to(Path(place)) for place in places)), None)
    for rel in sorted(declared):
        if not rel.endswith('.md') or not (rel in {'README.md', 'AGENTS.md', 'REVIEWER_GUIDE.md'} or rel.startswith('docs/')):
            continue
        text = (root / rel).read_text(encoding='utf-8', errors='replace')
        for raw in [*_LINK.findall(text), *_REFERENCE.findall(text)]:
            raw = raw[1:-1].strip() if raw.startswith('<') and raw.endswith('>') else raw
            if raw.startswith(('#', '//')) or _SCHEME.match(raw):
                continue   # fragments, protocol-relative and scheme URLs (https:, mailto:, data:) are not files
            target = unquote(raw.split('#', 1)[0].split('?', 1)[0])
            if not target:
                continue
            resolved = Path(os.path.normpath((Path(rel).parent / target).as_posix()))
            if resolved.is_absolute() or '..' in resolved.parts:
                failures.append({'path': rel, 'link': raw, 'reason': 'document link leaves the export'})
                continue
            if (root / resolved).exists():
                rows.append({'path': rel, 'link': raw, 'status': 'resolved'})
                continue
            mine = owner(resolved, selected) or next(iter(bindings.get(resolved.as_posix()) or []), None)
            if mine:
                rows.append({'path': rel, 'link': raw, 'status': 'missing-selected', 'project': mine})
                failures.append({'path': rel, 'link': raw, 'project': mine, 'reason': 'document link names a selected file that did not travel'})
            elif (other := owner(resolved, unselected)):
                rows.append({'path': rel, 'link': raw, 'status': 'unselected-project', 'project': other})
            else:
                rows.append({'path': rel, 'link': raw, 'status': 'missing-common'})
                failures.append({'path': rel, 'link': raw, 'reason': 'document link names a common engine, script or document file that did not travel'})
    return rows, failures


def source_closure_again(root, selection, projects, intents, declared, inventory):
    """Re-establish each selected TeX source closure IN THE EXPORT (repair1 RP-R4) with the same canonical owner the
    export used: the same files, every one a declared exported file with its exact bytes, the same frozen
    bibliography pin. Installed TeX inputs are re-observed, never copied."""
    from laplace.manuscript import manuscript_source
    failures = []
    for project in projects:
        recorded = (inventory.project_manifest(selection, project).get('selected_source_closure') or {})
        try:
            again = inventory.selected_source_closure(root, manuscript_source.resolve(project, repo_root=root), intents[project])
        except (OSError, ValueError, KeyError) as exc:
            failures.append({'project': project, 'reason': 'selected source closure does not re-establish in the export: ' + str(exc)[:300]})
            continue
        if again['files'] != recorded.get('files'):
            failures.append({'project': project, 'reason': 'selected source closure differs from the recorded closure',
                             'added': sorted(set(again['files']) - set(recorded.get('files') or []))[:10],
                             'missing': sorted(set(recorded.get('files') or []) - set(again['files']))[:10]})
        observed = lambda rows: sorted((row.get('argument'), row.get('relative'), row.get('sha256')) for row in rows or [])
        if observed(again['installed_inputs']) != observed(recorded.get('installed_inputs')):
            failures.append({'project': project, 'reason': 'installed TeX input provenance or availability differs from the recorded closure',
                             'recorded': observed(recorded.get('installed_inputs'))[:5], 'observed': observed(again['installed_inputs'])[:5]})
        if (again['frozen_bibliography'] or {}).get('sha256') != (recorded.get('frozen_bibliography') or {}).get('sha256'):
            failures.append({'project': project, 'reason': 'frozen bibliography pin differs from the recorded closure'})
        for rel in again['files']:
            if rel not in declared:
                failures.append({'project': project, 'path': rel, 'reason': 'source closure file is not a declared exported file'})
            elif declared[rel] != sha(root / rel):
                failures.append({'project': project, 'path': rel, 'reason': 'source closure bytes differ from the declared pin'})
    return failures


def verify(root):
    root = Path(root).resolve()
    os.environ['LAPLACE_REPO_ROOT'] = str(root)
    os.environ['LAPLACE_STATE'] = str(root / '.laplace-state')
    fence = Fence(root)   # the shared admission boundary: fixed and declared coordinates are regular files inside the root (W5-R2)
    declared = _bytes_layer.declared_manifest(fence)
    if declared.get('problem'):
        raise ValueError('release/export-manifest.json ' + declared['problem'])
    report = declared['report']
    failures = []
    checked = 0
    selection = None
    import writing_eval_manifest as inventory
    source_manifest = root / 'release/source-manifest.json'
    if not declared['source_manifest']['identity_match']:
        failures.append({'path': 'release/source-manifest.json', 'reason': 'source manifest identity mismatch' + (': ' + declared['source_manifest']['problem'] if declared['source_manifest'].get('problem') else '')})
    else:
        selection = json.loads(source_manifest.read_text(encoding="utf-8"))
        try:
            for project in report.get('projects') or [report['project']]:
                inventory.project_rows(selection, project)
        except (ValueError, KeyError, TypeError) as exc:
            failures.append({'path': 'release/source-manifest.json', 'reason': str(exc)})
    for row in report['copied_files'] + report['derived_files']:
        path, problem = fence.admit(row['path'])
        if problem:
            failures.append({'path': row['path'], 'reason': 'missing or outside checkout' if problem in ('missing', 'resolves outside the inspected root') else problem})
        elif sha(path) != row['sha256']:
            failures.append({'path': row['path'], 'reason': 'export bytes changed'})
        else:
            size = path.stat().st_size   # the actual size establishes the ceiling; a declared count must agree with it
            if 'bytes' in row and row['bytes'] != size:
                failures.append({'path': row['path'], 'reason': 'declared byte count differs from the exported file'})
            if size > inventory.LARGE_FILE_BYTES:
                failures.append({'path': row['path'], 'reason': 'file exceeds the per-file export ceiling'})
        checked += 1
    for rel in ('release/source-manifest.json', 'release/export-manifest.json'):
        if (root / rel).is_file() and (root / rel).stat().st_size > inventory.LARGE_FILE_BYTES:
            failures.append({'path': rel, 'reason': 'file exceeds the per-file export ceiling'})
    failures.extend(alias_closure(root, report))
    from laplace.web import authoring as authoring_surface, shared_ui
    from laplace.research import literature
    from laplace.research import research_runs
    from laplace.pipeline import registry
    projects = report.get('projects') or [report['project']]
    selected_projects = {project: registry.resolve(project, repo_root=root)
                         for project in projects}
    for project, selected in selected_projects.items():
        if selected is None:
            failures.append({'project': project, 'reason': 'project does not resolve'})
    # Closure intent is an explicit source/export agreement, never a fallback
    # selected from file availability. Unchanged old manifests remain strict.
    closures = {}
    try:
        intents = inventory.project_intents(projects, report.get('project_intents'))
        if selection is not None:
            if (selection.get('projects') or [selection.get('project')]) != projects:
                raise ValueError('source/export project selection mismatch')
            recorded_intents = inventory.project_intents(projects, selection.get('project_intents'))
            for project in projects:
                local = inventory.project_manifest(selection, project)
                intent = local.get('project_intent', inventory.DEFAULT_PROJECT_INTENT)
                if intent != intents[project] or (selection.get('project_intents') is not None
                                                   and intent != recorded_intents[project]):
                    raise ValueError('source/export project intent mismatch: ' + project)
                closure = inventory.project_closure(root, project, intent, selected_projects=projects)
                if local.get('required_project_files') != closure['required_files']:
                    raise ValueError('required project closure bytes changed: ' + project)
                recorded = local.get('project_closure')
                if recorded is not None and (recorded.get('intent') != intent or
                        recorded.get('generated_outputs') != closure['generated_outputs']):
                    raise ValueError('recorded generated-output availability changed: ' + project)
                # authored-metadata status (PRESENT/UNAUTHORED) must agree; current_inputs is the export-time exclusion
                # guard and may legitimately differ here, where historical spellings resolve through the portability aliases
                if recorded is not None and 'authored_metadata' in recorded and recorded['authored_metadata'] != closure['authored_metadata']:
                    raise ValueError('recorded authored metadata status changed: ' + project)
                closures[project] = closure
    except (OSError, ValueError, KeyError, TypeError) as exc:
        failures.append({'path': 'release/source-manifest.json', 'reason': str(exc)})
    registry_names = set(registry.all_projects(root))
    if registry_names != set(projects):
        failures.append({'reason': 'unrelated registry entries', 'projects': sorted(registry_names)})
    records = writing_records.fold_records(root)
    sessions = [s for s in records['sessions'].values() if s.get('project') in projects]
    foreign_sessions = [s.get('id') for s in records['sessions'].values()
                        if s.get('project') not in projects]
    if foreign_sessions:
        failures.append({'reason': 'history contains an unselected project session',
                         'sessions': foreign_sessions})
    if any(s.get('native_id') for s in sessions):
        failures.append({'reason': 'an imported session retains original native binding'})
    foreign_turns = [turn.get('id') for turn in records['turns'].values()
                     if turn.get('project') not in projects]
    if foreign_turns:
        failures.append({'reason': 'history contains an unselected project turn',
                         'turns': foreign_turns})
    for turn in records['turns'].values():
        if turn.get('custody_errors'):
            failures.append({'turn': turn['id'], 'reason': 'history body unresolved'})
    repositories, repository_failures = repository_scope(root)
    failures.extend(repository_failures)
    imports = []
    talk = root / 'contract/talk.jsonl'
    if talk.is_file():
        imports = [row for line in talk.read_text(encoding="utf-8").splitlines() if line.strip()
                   for row in [json.loads(line)] if row.get('record') == 'writing-session-import']
    session_projects = {s.get('id'): s.get('project') for s in records['sessions'].values()}
    failures.extend(import_scope(imports, session_projects, projects))
    run_states, local_sources, metadata_only, per_project = {}, 0, 0, {}
    for project, selected in selected_projects.items():
        if selected is None:
            continue
        manuscript = root / selected.manuscript_dir
        project_states, project_local, project_metadata, project_figures = {}, 0, 0, 0
        index = manuscript / 'research_runs/index.json'
        for run_id in json.loads(index.read_text(encoding="utf-8")).get('runs', []) if index.is_file() else []:
            run = research_runs._run_status(manuscript, run_id)
            if not run:
                failures.append({'project': project, 'run': run_id, 'reason': 'retained run unavailable'})
                continue
            state = str(run.get('state'))
            run_states[state] = run_states.get(state, 0) + 1
            project_states[state] = project_states.get(state, 0) + 1
            for key in ('result_absolute', 'producer_base', 'stdout_path', 'stderr_path'):
                if run.get(key) and not Path(run[key]).resolve().is_relative_to(root):
                    failures.append({'project': project, 'run': run_id,
                                     'reason': key + ' resolves outside export'})
            if run.get('reason') == 'successful receipt has no current result output':
                failures.append({'project': project, 'run': run_id, 'reason': run['reason']})
        # reference associations at their OWNER's coordinate (project state home), not the selected TeX folder;
        # a snapshot's recorded unauthored absence is truthful, any other absence is a failure
        authored = (closures.get(project) or {}).get('authored_metadata', {}).get('references', {})
        references = root / authored['path'] if authored.get('path') else manuscript / 'references.json'
        if authored.get('status') == 'UNAUTHORED':
            associations = []
        elif not references.is_file():
            failures.append({'project': project, 'reason': 'required references.json is missing'})
            associations = []
        else:
            associations = json.loads(references.read_text(encoding="utf-8")).get('associations', [])
        keys = sorted({r['key'] for r in associations if r.get('key')})
        for key in keys:
            try:
                _info, path = literature.source_info(project, key, root)
                if path:
                    if not path.resolve().is_relative_to(root):
                        raise ValueError('source resolved outside export')
                    local_sources += 1; project_local += 1
                else:
                    metadata_only += 1; project_metadata += 1
            except Exception as exc:
                failures.append({'project': project, 'source': key, 'reason': str(exc)[:300]})
        figure_manifest = manuscript / 'figure_manifest.json'
        if figure_manifest.is_file():
            # Availability/path validation belongs to project_closure above;
            # this is only the retained presentation count.
            try:
                figures = json.loads(figure_manifest.read_text(encoding="utf-8"))
                placed = figures.get('placed', []) if isinstance(figures, dict) else []
                project_figures = len(placed) if isinstance(placed, list) else 0
            except (OSError, ValueError):
                pass
        per_project[project] = {
            'sessions': sum(1 for session in sessions if session.get('project') == project),
            'turns': sum(1 for turn in records['turns'].values() if turn.get('project') == project),
            'historical_run_states': project_states,
            'local_sources': project_local,
            'metadata_only_sources': project_metadata,
            'figures': project_figures,
            'authored_metadata': {kind: row.get('status') for kind, row in
                                  ((closures.get(project) or {}).get('authored_metadata') or {}).items()},
        }
    project_dirs = {project: selected.project_dir for project, selected in selected_projects.items()
                    if selected is not None and selected.project_dir}
    # every selected registered home exists in the export; a generated home marker is exact and declared derived
    derived_pins = {row['path']: row['sha256'] for row in report['derived_files']}
    for project, home in project_dirs.items():
        if not (root / home).is_dir():
            failures.append({'project': project, 'path': home, 'reason': 'registered project home is missing from the export'})
            continue
        marker = Path(home) / inventory.HOME_MARKER
        present = root / marker
        if present.is_symlink() or present.exists():
            if present.is_symlink() or not present.is_file():   # type before any read (empty-home repair1 EH-R1b)
                failures.append({'project': project, 'path': marker.as_posix(), 'reason': 'project-home marker is not a regular file'})
            elif (present.read_bytes() != inventory.home_marker(project, home)
                    or derived_pins.get(marker.as_posix()) != sha(present)):
                failures.append({'project': project, 'path': marker.as_posix(), 'reason': 'project-home marker is not the declared generated marker'})
    failures.extend(selection_closure(root, report, inventory, project_dirs))
    if selection is not None and closures:
        declared_pins = {row['path']: row['sha256'] for row in report['copied_files']}
        failures.extend(source_closure_again(root, selection, list(closures), intents, declared_pins, inventory))
    selected_homes = {project: sorted({value for value in (selected.project_dir, getattr(selected, 'tex_root', None), selected.manuscript_dir)
                                       if isinstance(value, str) and value not in {'', '.'} and not Path(value).is_absolute()})
                      for project, selected in selected_projects.items() if selected is not None}
    links, link_failures = document_links(root, report, {
        'selected': selected_homes, 'unselected': (selection or {}).get('unselected_registered_homes') or {},
        'bindings': (selection or {}).get('source_bindings') or {}})
    failures.extend(link_failures)
    # the declared manuscript-link, Work-input and portable-document relationships are what the export holds (portable links, 2026-10-20)
    portable_failures, portable_summary = inventory._portable().verify_portable(report, {row['path']: row.get('sha256') for row in report['copied_files'] + report['derived_files']},
                                                                           admit=fence.admit, identity=_bytes_layer.file_identity)
    failures.extend(portable_failures)
    assets = shared_ui.capture_asset_snapshot()
    return {'schema': 'laplace.writing-evaluation-verification/1',
            'ok': not failures, 'checked_files': checked,
            'projects': projects, 'project_intents': report.get('project_intents') or
                {project: inventory.DEFAULT_PROJECT_INTENT for project in projects},
            'per_project': per_project,
            'sessions': len(sessions), 'turns': len(records['turns']),
            'historical_run_states': run_states,
            'local_sources': local_sources, 'metadata_only_sources': metadata_only,
            'repositories': repositories,
            'document_links': {status: sum(1 for row in links if row['status'] == status) for status in LINK_STATUSES},
            'unselected_project_links': sorted({(row['link'], row['project']) for row in links if row['status'] == 'unselected-project'}),
            'selection_policy': report.get('selection_policy'),
            **portable_summary,
            'assets': assets.identity, 'failures': failures,
            'scope': 'Exact untouched export bytes, selected project, imported history and source resolution. No model, numerical or build execution.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    result = verify(args.root)
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
