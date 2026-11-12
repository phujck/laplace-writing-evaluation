#!/usr/bin/env python3
"""Read-only candidate closure for a Writing App evaluator export.

This inventories bytes and exact event selections. It neither exports a repository
nor certifies privacy, licensing, portable installation or complete dependencies.
"""
from __future__ import annotations

import argparse
import ast
import collections
import hashlib
import json
import os
import re
import sys
from pathlib import Path

# Bootstrap the shared custody contract; selected layout/source owners are
# imported on demand by project closure, without runtime telemetry.
_source = Path(__file__).resolve().parents[1] / "src"
if _source.is_dir() and str(_source) not in sys.path:sys.path.insert(0, str(_source))
from laplace.core.bodies import REFERENCE_SCHEMA as PUBLIC_BODY_SCHEMA, is_reference as is_public_body_reference, require_reference as require_public_body_reference

BODY_SCHEMA = PUBLIC_BODY_SCHEMA
from laplace.projects.project_data import (published_admission, published_lineage, project_rows, collect_definitions, select_history, ManifestError, _sha, _safe, _excluded, _files, home_marker, _project_files, _file_record, _json, _rows, _belongs, _journal_store_key, _row_record, _typed_refs, _body_closure)
from laplace.projects.project_data import HEX, PRIVATE, CACHES, SECRET_NAMES, MAX_JSON, HOME_MARKER
PROJECT_INTENTS = ('completed-manuscript', 'current-project-snapshot')
DEFAULT_PROJECT_INTENT = PROJECT_INTENTS[0]
#: Authored project metadata a current-project-snapshot may truthfully lack (recorded UNAUTHORED, never fabricated)
UNAUTHORED_ALLOWED = ('plan', 'references', 'research_records')
#: Per-file ceiling of a Git-oriented export (hosted Git refuses larger files); no external-asset policy is defined
LARGE_FILE_BYTES = 100 * 1024 * 1024
SELECTION_SCHEMA = 'laplace.writing-export-selection/1'
SELECTION_DECISIONS = ('include', 'exclude')

# The existing distribution owner declares operational inputs once. The exporter consumes
# OPERATIONAL_INPUTS; both container selectors are generated from this same declaration.
OPERATIONAL_INPUTS = (
    'setup.py', 'MANIFEST.in',  # canonical packet profiles generate package resources at build time
    'atlas/pyproject.toml', 'atlas/README.md',
    'src/atlas/front/README.md', 'src/atlas/sensorium/README.md',
    'src/laplace/pipeline/writing_organ',
    'docs/writing-evaluation-release.md', 'docs/writing-evaluator-readme.md',
    'docs/writing-evaluator-agents.md', 'docs/writing-reviewer-guide.md',
    'docs/writing-pytest.ini',
    'docs/writing-account-setup.md',
    'docs/writing-start-here.md', 'docs/writing-tasks.md',
    'docs/writing-glossary.md', 'docs/writing-reference.md',
    'tests/test_first_use_guidance.py', 'tests/workflow_first_use.test.mjs',
    'tests/first_use_shell.test.mjs', 'tests/first_use_context.test.mjs',
    'tests/review_setup_first_use.test.mjs',
    'tests/first_use_status.test.mjs', 'tests/task_trail.test.mjs',
    'tests/human_workspace_shell.test.mjs', 'tests/helpers/shared_resolve.mjs',
    'tests/research_geometry.test.mjs',
    'tests/local_document_intake_ui.test.mjs', 'tests/local_document_intake_return.test.mjs',
    'tests/helpers/inspector_close_harness.mjs',
    'docs/writing-engine-walkthrough.md', 'docs/writing-agent-start.md',
    'docs/writing-conversation-reading.md',
    'docs/writing-workspace.md', 'docs/pilot-session-settings.md',
    'docs/writing-source-inventory.md', 'docs/source-kernel-bridge.md',
    # Frozen public Source-input evaluator; no upstream kernel/world execution suite.
    'tests/source_inputs_gate.py', 'tests/test_source_inputs_projection.py',
    # Public self-description/controller checks; canonical runtime inputs remain excluded.
    'tests/test_source_publication_self_description.py',
    'tests/workspace_source_constituents.test.mjs', 'tests/helpers/html_dom.mjs',
    'docs/writing-source-map.md', 'docs/writing-code-overview.md',
    'docs/project-data-handover.md',
    'docs/operational-homes.md',   # the one entry the code overview and src/laplace/README.md link (where things live)
    'docs/writing-work-review-lifecycle.md', 'docs/writing-consulted-read-recovery.md',
    'docs/writing-review-evidence.md', 'docs/writing-evidence-navigation.md',
    'tests/test_review_evidence_doors.py', 'tests/test_work_provenance.py',
    'tests/test_work_provenance_doors.py', 'tests/test_backlog_display_order.py',
    'tests/workspace_review_evidence.test.mjs',
    'tests/helpers/backlog_fixture.mjs',
    'tests/test_review_evidence.py', 'tests/writing_owner_review_evidence.test.mjs',
    # Eigen continuity evaluator controls (Root e716/e2f6): A doors/reconstruction/deliberation, B owner/delivery, C frontend.
    'tests/test_eigen_continuity_doors.py', 'tests/test_eigen_continuity_reconstruction.py',
    'tests/test_bounded_deliberation.py', 'tests/test_eigen_continuity_owner.py',
    'tests/test_eigen_continuity_delivery.py', 'tests/eigen_continuity_frontend.test.mjs',
    'tests/test_eigen_continuity_stop_custody.py',
    # System owner contracts evaluator control (A, 2026-11-02): public feedback-home, retained-read,
    # visual-template and owner-factory transport cases; self-contained (no other test-module imports).
    'tests/test_system_owner_contracts.py',
    # Root e331 integration controls: B runtime/development and C human-research application owners.
    'tests/test_system_runtime_development.py', 'tests/test_human_research_application.py',
    'docs/scoped-progress.md',
    'docs/workflow-definition-owner.md', 'docs/writing-workflow-editor.md',
    'tests/test_selected_definition_consumer.py', 'tests/test_selected_definition_custody.py',
    'tests/test_workflow_history_continuation.py', 'tests/test_workflow_history_doors.py',
    'tests/test_workflow_operations.py', 'tests/test_workflow_operation_doors.py',
    # Public helper modules test_workflow_operations.py imports (the doors test imports it in turn).
    'tests/test_research_workflow_runs.py', 'tests/test_writing_operating.py',
    'tests/workflow_history_frontend.test.mjs',
    'tests/workflow_operation_frontend.test.mjs', 'tests/fixtures/workflow_history/public-owner.json',
    'tests/fixtures/workflow_operation/public-owner.json',
    'tests/research_carried_workflow.test.mjs',
    'tests/runtime_guard.py',
    'docs/failed-review-continuation.md', 'docs/source-read-contract.md',
    'docs/sealed-text-reader.md',
    'docs/owner-discovery.md', 'docs/writing-research-workbench.md',
    'docs/development-source-use.md',   # the system-entry route operational-homes.md links (work.owner-discovery)
    'src/laplace/README.md', 'src/laplace/writing/README.md',
    # the system description: laplace.system.load reads this exact JSON beside its module, and the front door
    # (docs/writing-code-overview.md) links to it; package-data cannot restore bytes this selection omits (CT-R2)
    'src/laplace/system/description.json',
    'src/laplace/web/static_shared/README.md',
    'tools/writing_verbs/gen_routes.py', 'tools/writing_verbs/reanchor_http_routes.py',
    'tools/writing_verbs/http_routes.csv', 'tests/grammar_spec/mapping.csv',
    'profiles/workflows',
    # the research collection's entry documents (M5 release portability, 2026-10-16)
    'docs/writing-campaigns.md', 'docs/writing-paper-collection.md',
    'atlas_system_walkthrough.pdf', 'walkthrough',
    'docs/writing-browser-server.md', 'docs/writing-container.md', 'docs/writing-registry.md',
    'docs/writing-container-download.md', 'scripts/writing_container_package.py',
    '.github/workflows/package-writing-container.yml', 'tests/test_writing_container_package.py',
    'scripts/writing_eval_manifest.py', 'scripts/export_writing_evaluation.py',
    'scripts/verify_writing_evaluation.py', 'docs/writing-release-selection.md', 'deploy/writing',
    # the read-only boot-failure inspection path and its shared byte layer (Work5 recovery, 2026-10-20)
    'scripts/inspect_writing_export.py', 'scripts/writing_export_bytes.py', 'docs/writing-recovery-and-currentness.md',
    # the manuscript-link / Work-input projection the manifest builder, this exporter and the verifier all import (portable links, 2026-10-20)
    'scripts/writing_portable_links.py', 'tests/test_writing_portable_links.py',
    '.github/workflows/writing-browser-smoke.yml',
    'tests/test_writing_portable.py', 'tests/test_writing_portability.py', 'tests/test_writing_portable_core.py',
    'tests/project_landing.test.mjs', 'tests/helpers/evidence_reader_harness.mjs',
)

# Optional generated owner outputs, never required missing canonical source inputs.
# Only this separately admitted selected engineering metadata closure travels.
GENERATED_RELEASE_INPUTS = ('release/engineering-programme-20261028',)
DOCKER_SELECTORS = ('deploy/writing/Dockerfile.dockerignore', 'deploy/writing/Dockerfile.refresh.dockerignore')
DOCKER_RECIPES = ('deploy/writing/Dockerfile', 'deploy/writing/Dockerfile.refresh')
_TOOLS_BEGIN = '# OPERATIONAL-TOOLS: generated from OPERATIONAL_INPUTS\n'
_TOOLS_END = '# END OPERATIONAL-TOOLS\n'
# Existing broad application/resource classes and portable evaluator subset stay unchanged.
# Workspace-only tooling/history selection remains separate from the image context.
DOCKER_APPLICATION_PATTERNS = (
    'pyproject.toml', 'setup.py', 'MANIFEST.in', 'README.md', 'src/**',
    'atlas/pyproject.toml', 'atlas/README.md',
    'deploy/writing/writing-entrypoint.sh', 'deploy/writing/smoke.py',
    'profiles/workflows/**', 'profiles/typography/**', 'profiles/visual_style.json',
    'docs/writing*.md',
)
DOCKER_EVALUATOR_INPUTS = (
    'tests/test_first_use_guidance.py', 'tests/workflow_first_use.test.mjs',
    'tests/first_use_shell.test.mjs', 'tests/first_use_context.test.mjs',
    'tests/review_setup_first_use.test.mjs',
    'tests/first_use_status.test.mjs', 'tests/task_trail.test.mjs',
    'tests/human_workspace_shell.test.mjs', 'tests/helpers/shared_resolve.mjs',
    'tests/research_geometry.test.mjs',
    'tests/local_document_intake_ui.test.mjs', 'tests/local_document_intake_return.test.mjs',
    'tests/helpers/inspector_close_harness.mjs',
    'tests/test_selected_definition_consumer.py', 'tests/test_selected_definition_custody.py',
    'tests/test_workflow_history_continuation.py', 'tests/test_workflow_history_doors.py',
    'tests/test_workflow_operations.py', 'tests/test_workflow_operation_doors.py',
    # Public helper modules test_workflow_operations.py imports (the doors test imports it in turn).
    'tests/test_research_workflow_runs.py', 'tests/test_writing_operating.py',
    'tests/workflow_history_frontend.test.mjs',
    'tests/workflow_operation_frontend.test.mjs', 'tests/fixtures/workflow_history/public-owner.json',
    'tests/fixtures/workflow_operation/public-owner.json',
    'tests/research_carried_workflow.test.mjs',
    'tests/runtime_guard.py',
    'tests/test_review_evidence.py', 'tests/test_review_evidence_doors.py', 'tests/test_work_provenance.py',
    'tests/test_work_provenance_doors.py', 'tests/test_backlog_display_order.py',
    'tests/workspace_review_evidence.test.mjs', 'tests/writing_owner_review_evidence.test.mjs',
    'tests/helpers/backlog_fixture.mjs',
    # Eigen continuity evaluator controls (Root e716/e2f6): the same six exact paths as OPERATIONAL_INPUTS.
    'tests/test_eigen_continuity_doors.py', 'tests/test_eigen_continuity_reconstruction.py',
    'tests/test_bounded_deliberation.py', 'tests/test_eigen_continuity_owner.py',
    'tests/test_eigen_continuity_delivery.py', 'tests/eigen_continuity_frontend.test.mjs',
    'tests/test_eigen_continuity_stop_custody.py',
    # Root e331 system integration controls (A owner contracts, B runtime/development, C human-research application),
    # the same three exact paths as OPERATIONAL_INPUTS.
    'tests/test_system_owner_contracts.py', 'tests/test_system_runtime_development.py',
    'tests/test_human_research_application.py',
    'tests/test_writing_portable.py', 'tests/test_writing_portability.py',
    'tests/test_writing_container_package.py', 'tests/test_writing_portable_core.py',
    'tests/project_landing.test.mjs', 'tests/helpers/evidence_reader_harness.mjs',
    'tests/source_inputs_gate.py', 'tests/test_source_inputs_projection.py',
    # Public self-description/controller checks; canonical runtime inputs remain excluded.
    'tests/test_source_publication_self_description.py',
    'tests/workspace_source_constituents.test.mjs', 'tests/helpers/html_dom.mjs',
)
DOCKER_LEGACY_TOOL_INPUTS = ('scripts/writing_portable_index.py',)
DOCKER_EXCLUSIONS = ('profiles/writing/sealed-reader-qualification.json', 'contract/**', '.laplace-state/**')

def dockerignore_text() -> str:
    """One deterministic projection of existing image classes and operational docs/tooling.

    Public guides and exporter sibling tools cannot fall through a separately maintained
    allowlist. This does not admit project data, host proof, private state or arbitrary tests.
    """
    operational = [p for p in OPERATIONAL_INPUTS
                   if p.startswith('docs/') and (p.endswith('.md') or p == 'docs/writing-pytest.ini')
                   or p.startswith('scripts/') and p.endswith('.py')
                   or p.startswith('tools/')]
    patterns = list(dict.fromkeys((*DOCKER_APPLICATION_PATTERNS, *operational,
                                  *DOCKER_EVALUATOR_INPUTS, *DOCKER_LEGACY_TOOL_INPUTS, 'deploy/writing/**', *(p + '/**' for p in GENERATED_RELEASE_INPUTS))))
    return ('# Generated by scripts/writing_eval_manifest.py --write-docker-selectors; do not edit.\n'
            '# Operational docs/tooling and preserved image classes have one distribution declaration.\n'
            '**\n' + ''.join('!' + p + '\n' for p in patterns)
            + '\n# Host qualification and operator observations are not portable application inputs.\n'
            + ''.join(p + '\n' for p in DOCKER_EXCLUSIONS))


def generated_release_files(root: Path) -> list[Path]:
    """Only exact ordinary-owner-verified selected Work output files, when present.

    Missing generated outputs are normal in a canonical source checkout. A caller
    carrying an actual engineering handover validates it before copying to the
    private workspace or the isolated image context. No broad release tree scan.
    """
    from laplace.projects import project_handover as H
    root = Path(root).resolve(); result = []
    for rel in GENERATED_RELEASE_INPUTS:
        folder = _safe(root, rel)
        if not folder.exists():continue
        if not folder.is_dir():raise ManifestError('Generated engineering output is not an owned directory.')
        H.inspect_handover(folder)
        receipt = _json(_safe(folder, H.MANIFEST)); selection = receipt['plan'].get('selection')
        if not selection:raise ManifestError('Generated engineering output requires selected owner custody.')
        manifest, _meta = H._retained_manifest(folder, receipt['plan']['project'], selection['manifest_id'])
        included = [entry for entry in manifest['entries'] if entry.get('class') == 'included']
        if not included or any(entry.get('reference', {}).get('kind') != 'work' or entry.get('representation') != 'frozen-owner-snapshot' for entry in included):
            raise ManifestError('Generated engineering output is selected frozen Work metadata only.')
        names = {H.MANIFEST, *(entry['path'] for entry in receipt['outputs'])}
        # Detect unexpected entrants by names only; never open or disclose them.
        actual = set(); directories = 0
        for directory, dirs, files in os.walk(folder, followlinks=False):
            directories += 1
            if directories > 1024:raise ManifestError('Generated output directory bound exceeded.')
            for name in dirs:
                if (Path(directory) / name).is_symlink():raise ManifestError('Generated output symlink refused.')
            for name in files:
                path = Path(directory) / name
                if path.is_symlink():raise ManifestError('Generated output symlink refused.')
                actual.add(path.relative_to(folder).as_posix())
                if len(actual) > 2048:raise ManifestError('Generated output file bound exceeded.')
        if actual != names:raise ManifestError('Generated output has unlisted or missing files; no extras admitted.')
        result.extend(_safe(folder, name) for name in sorted(names))
    return result


def generated_release_copy_instructions(root: Path) -> list[str]:
    """Delivery-only additions to the maintained refresh recipe, not a required canonical COPY.

    The isolated context contains only generated_release_files. The normal source
    Dockerfiles remain usable without generated metadata or a release checkout.
    """
    paths = generated_release_files(root); root = Path(root).resolve()
    return ['COPY --chown=laplace:laplace ' + json.dumps([rel, '/opt/laplace/' + rel])
            for rel in GENERATED_RELEASE_INPUTS if any(path.is_relative_to(root / rel) for path in paths)]


def operational_tool_copy_instructions() -> list[str]:
    """Exact declared tool files only; no arbitrary tools directory is admitted."""
    return ['COPY ' + json.dumps([rel, '/opt/laplace/' + rel])
            for rel in OPERATIONAL_INPUTS if rel.startswith('tools/')]


def _docker_recipe_projection(text: str) -> str:
    block = _TOOLS_BEGIN + '\n'.join(operational_tool_copy_instructions()) + '\n' + _TOOLS_END
    if _TOOLS_BEGIN in text:
        import re
        return re.sub(re.escape(_TOOLS_BEGIN) + r'.*?' + re.escape(_TOOLS_END), lambda _m: block, text, flags=re.S)
    anchor = 'COPY scripts ./scripts\n'
    if anchor not in text:raise ManifestError('Maintained APP copy anchor is missing.')
    return text.replace(anchor, anchor + block)


def check_docker_selectors(root: Path) -> dict:
    """Check selectors and exact operational-tool recipe blocks; no project/runtime activity."""
    expected = dockerignore_text().encode()
    recipes = all((Path(root) / p).is_file() and (Path(root) / p).read_text() == _docker_recipe_projection((Path(root) / p).read_text()) for p in DOCKER_RECIPES)
    return {'ok': recipes and all((Path(root) / p).is_file() and (Path(root) / p).read_bytes() == expected for p in DOCKER_SELECTORS),
            'paths': list(DOCKER_SELECTORS), 'sha256': _sha(expected),
            'recipe_paths':list(DOCKER_RECIPES),'operational_tools':operational_tool_copy_instructions(),
            'declaration': 'scripts/writing_eval_manifest.py:OPERATIONAL_INPUTS',
            'scope': 'Operational image docs/tooling plus existing app classes/evaluator subset; not project closure or privacy certification.'}

def write_docker_selectors(root: Path) -> dict:
    """Explicit generation of maintained selectors and exact tool COPY blocks only."""
    root = Path(root).resolve(); raw = dockerignore_text().encode()
    for rel in DOCKER_SELECTORS:
        path = _safe(root, rel)
        if not path.is_file():raise ValueError('Expected existing Docker selector: ' + rel)
        path.write_bytes(raw)
    for rel in DOCKER_RECIPES:
        path = _safe(root, rel)
        if not path.is_file():raise ValueError('Expected existing Docker recipe: ' + rel)
        path.write_text(_docker_recipe_projection(path.read_text()))
    return check_docker_selectors(root)



def project_intents(projects, supplied=None) -> dict:
    """One explicit closure-policy owner, shared by CLI/export/verification.

    This is requested packaging intent, not scientific or project completion.
    Missing inputs never choose a less strict intent automatically.
    """
    selected = list(projects)
    result = {project: DEFAULT_PROJECT_INTENT for project in selected}
    if supplied is None:
        return result
    entries = list(supplied.items()) if isinstance(supplied, dict) else supplied
    if not isinstance(entries, (list, tuple)):
        raise ManifestError('project intents must be a selected-project mapping')
    seen = set()
    for entry in entries:
        if isinstance(entry, str) and entry.count('=') == 1:
            project, intent = entry.split('=', 1)
        elif isinstance(entry, tuple) and len(entry) == 2:
            project, intent = entry
        else:
            raise ManifestError('project intent must be PROJECT=INTENT')
        if (not isinstance(project, str) or project not in result or project in seen
                or not isinstance(intent, str) or intent not in PROJECT_INTENTS):
            raise ManifestError('unknown, unselected or repeated project intent: ' + str(project))
        seen.add(project); result[project] = intent
    return result


def project_manifest(selection, project):
    """One selected project view in the existing single/combined manifest."""
    if 'project_manifests' in selection:
        if project not in selection['project_manifests']:
            raise ManifestError('project is absent from source manifest: ' + project)
        return selection['project_manifests'][project]
    if selection.get('project') != project:
        raise ManifestError('project is absent from source manifest: ' + project)
    return selection


def metadata_paths(root, project, resolved) -> dict:
    """Each authored metadata file at its CANONICAL owner's coordinate (M5 release portability, 2026-10-16).

    The selected TeX directory is the edit/compile/bibliography root only. Reference associations and research
    records are project state at the owners' state home (``manuscript_source.project_state_dir``: an editable
    source-optional project keeps them in its storage home whichever nested draft is selected); the reader plan is
    the registry's declared ``plan_path``; the figure manifest is the visuals owner's manuscript home.
    """
    from laplace.research import references_surface, visuals_surface
    from laplace.research import research_context
    from laplace.research import research_records
    root = Path(root).resolve()

    def relative(path, kind, name=None):
        if path is None:
            return ''
        path = Path(path)
        path = Path(os.path.abspath(path if path.is_absolute() else root / path))
        if name:
            path = path / name
        if not path.is_relative_to(root):
            raise ManifestError(kind + ' owner coordinate is outside the repository')
        return path.relative_to(root).as_posix()
    research_home = research_context.project(project, root)[1]
    return {'plan': relative(resolved.plan(root), 'plan'),
            'references': relative(references_surface._manuscript(project, root), 'references', 'references.json'),
            'research_records': relative(research_home, 'research_records', research_records._RECORDS),
            'figure_manifest': relative(visuals_surface._m(project, root), 'figure_manifest', 'figure_manifest.json')}


def project_closure(root, project, intent=DEFAULT_PROJECT_INTENT, *, resolved=None, source=None,
                    selected_projects=None, artifact_contexts=None):
    """Observe selected local closure without telemetry, builds or file creation."""
    from laplace.manuscript import manuscript_source, tex_dependencies
    from laplace.pipeline import registry
    root = Path(root).resolve()
    project_intents([project], {project: intent})
    resolved = resolved or registry.resolve(project, repo_root=root)
    if resolved is None or resolved.external_root:
        raise ManifestError('selected project has no local canonical registry layout')
    source = source if source is not None else manuscript_source.resolve(project, repo_root=root)
    source_root, md = source.get('root'), source.get('manuscript_dir')
    if not isinstance(source_root, str) or not _safe(root, source_root).is_file():
        raise ManifestError('required selected manuscript source is missing')
    if not isinstance(md, str) or not _safe(root, md).is_dir():
        raise ManifestError('required manuscript directory is missing')
    owners = metadata_paths(root, project, resolved)
    required = {'source': source_root, **owners,
                'build_pdf': str(Path(source_root).with_suffix('.pdf'))}
    missing = {kind: path for kind, path in required.items()
               if not path or not _safe(root, path).is_file()}
    # A current snapshot may record unauthored plan/reference/research metadata as absent (never fabricated);
    # a completed manuscript stays strict.
    allowed_absent = ({'figure_manifest', 'build_pdf', *UNAUTHORED_ALLOWED}
                      if intent == PROJECT_INTENTS[1] else set())
    if set(missing) - allowed_absent:
        raise ManifestError('required project closure is incomplete: ' + ', '.join(
            f'{kind}:{path}' for kind, path in missing.items() if kind not in allowed_absent))
    current_inputs = set()

    # Same placed-figure coordinate/fence contract as the existing verifier, at the visuals owner's home.
    figures = _safe(root, required['figure_manifest'])
    figure_home = figures.parent
    if figures.is_file():
        value = _json(figures)
        if not isinstance(value, dict) or not isinstance(value.get('placed', []), list):
            raise ManifestError('malformed figure manifest')
        if 'figures' in value and not isinstance(value['figures'], (dict, list)):
            raise ManifestError('malformed figure manifest figures')
        for row in value.get('placed', []):
            if not isinstance(row, dict): raise ManifestError('malformed placed figure')
            for field in ('artefact', 'placed_at'):
                path = row.get(field)
                if field == 'placed_at' and not path: continue
                if not isinstance(path, str) or not path:
                    raise ManifestError('placed figure ' + field + ' is unavailable')
                target = (figure_home / path).resolve()
                if not target.is_relative_to(figure_home.resolve()) or not target.is_file():
                    raise ManifestError('placed figure ' + field + ' is unavailable')
                _safe(root, target.relative_to(root).as_posix())
                current_inputs.add(target.relative_to(root).as_posix())
    graphics = tex_dependencies.graphic_references(root / source_root, root)
    if any(row['status'] != 'AVAILABLE' for row in graphics):
        raise ManifestError('required declared graphic output is unavailable')
    for graphic in graphics:
        _safe(root, graphic['repo_file'])
        current_inputs.add(graphic['repo_file'])

    # Resolve CURRENT binding coordinates through their existing owners. Do not
    # equate basenames, interpret an ART id, or hydrate historical read receipts.
    from laplace.projects import artifacts
    from laplace.web import research_artifact_read
    from laplace.research import research_records
    admitted = set(selected_projects or [project])
    contexts = artifact_contexts if artifact_contexts is not None else {}
    absent = {(root / path).resolve(): kind for kind, path in missing.items()}

    def owner_context(qualified):
        if not isinstance(qualified, str) or qualified not in admitted:
            raise ManifestError('current reference project is not selected')
        if qualified not in contexts:
            contexts[qualified] = artifacts.context(root, qualified)
        return contexts[qualified]

    def scoped_target(raw, qualified, scope, *, artifact=False, required=False, legacy_base=None):
        if not isinstance(raw, str) or not raw:
            if required: raise ManifestError('current reference has no exact path')
            return None
        ctx = owner_context(qualified)
        if artifact:
            # Same canonical scope/path restrictions as the actual artifact door.
            target = artifacts.resolve_path(root, qualified, raw, scope, context=ctx)
        else:
            if scope not in {'project', 'manuscript'}:
                raise ManifestError('current reference scope must be project or manuscript')
            base = legacy_base if legacy_base is not None else (
                ctx['base'] if scope == 'project' else root / ctx['source']['manuscript_dir'])
            # Existing research reader admits explicit scoped or checkout-relative
            # coordinates inside that same base; no alternative filename search.
            target = research_artifact_read._artifact_target(base, raw, root)
        if target is None:
            if required: raise ManifestError('current reference is outside its declared scope')
            return None
        _safe(root, target.relative_to(root).as_posix())
        if target in absent:
            raise ManifestError('current record requires absent generated output: ' + absent[target])
        if required and not target.is_file():
            raise ManifestError('current required reference is unavailable')
        if target.is_file():
            current_inputs.add(target.relative_to(root).as_posix())
        return target

    # These are retained observations, not declarations that current bytes exist.
    historical = {'history', 'provenance', 'owner_evidence', 'action_receipt',
                  'read_receipt', 'read_handle', 'human_read'}
    path_fields = {'path', 'file', 'pdf', 'pdf_path', 'source_path', 'output',
                   'result_path', 'artefact', 'placed_at', 'figure_manifest'}

    def references_absent(value, qualified=project, scope='manuscript', *, required=False, legacy_base=None):
        if isinstance(value, dict):
            if 'project' in value or 'scope' in value:
                legacy_base = None
            qualified = value.get('project', qualified)
            scope = value.get('scope', scope)
            owner = value.get('owner')
            if isinstance(owner, str) and owner in {'artifact', 'writing-artifact'}:
                scoped_target(value.get('path'), qualified, value.get('scope', 'project'),
                              artifact=True, required=True)
                return
            if required and owner is not None:
                raise ManifestError('unsupported current artifact reference owner')
            if required and not isinstance(value.get('path'), str):
                raise ManifestError('current reference has no exact path')
            for key, child in value.items():
                if key in historical: continue
                if key in path_fields and isinstance(child, str):
                    scoped_target(child, qualified, value.get(key + '_scope', scope), required=required,
                                  legacy_base=legacy_base if key + '_scope' not in value else None)
                elif key in {'artifact', 'artifacts'}:
                    references_absent(child, qualified, scope, required=True, legacy_base=legacy_base)
                elif isinstance(child, (dict, list)):
                    references_absent(child, qualified, scope, legacy_base=legacy_base)
        elif isinstance(value, list):
            for child in value: references_absent(child, qualified, scope, required=required, legacy_base=legacy_base)
        elif required:
            raise ManifestError('current reference has no exact path')

    for name in ('plan', 'references', 'research_records'):
        if name in missing:
            continue   # recorded UNAUTHORED below (current-project-snapshot only)
        value = _json(_safe(root, required[name]))
        if not isinstance(value, dict): raise ManifestError('malformed current project ' + name)
        references_absent(value)
        if name == 'research_records':
            # Existing field-specific research scopes, without treating saved
            # dependency observations/history as a fresh required declaration.
            for record in value.get('records', []):
                if not isinstance(record, dict): continue
                for raw, scope in research_records._dependency_specs(record):
                    scoped_target(raw, record.get('project', project), scope)
    target_dir = resolved.resolved_target_dir(root)
    receipt_paths = {root / md / 'compile.json', root / md / 'release/finalize.json'}
    if target_dir is not None:
        receipt_paths.add(target_dir / 'release/finalize.json')
    for receipt in sorted(receipt_paths):
        if receipt.is_file():
            _safe(root, receipt.relative_to(root).as_posix())
            value = _json(receipt)
            if not isinstance(value, dict): raise ManifestError('malformed project-local build receipt')
            references_absent(value, legacy_base=(receipt.parent.parent
                                if receipt.name == 'finalize.json' else receipt.parent))

    context = registry.project_context(project, repo_root=root)
    pipeline_state = registry._release_state(context.target_dir, context.manuscript_dir)[1]
    generated = {kind: {'path': required[kind], 'presence': 'ABSENT' if kind in missing else 'PRESENT',
                       'availability': ('UNAVAILABLE_OR_NOT_BUILT' if kind == 'build_pdf' else 'UNAVAILABLE_OR_NOT_CREATED')
                                       if kind in missing else 'PINNED_PRESENT',
                       'currentness': 'UNVERIFIED',
                       'qualification': 'Observed file availability only; no history or scientific completion inferred.'}
                 for kind in ('figure_manifest', 'build_pdf')}
    authored = {kind: {'path': required[kind], 'status': 'UNAUTHORED' if kind in missing else 'PRESENT',
                       **({'qualification': 'Not authored for this imported/current snapshot; recorded absent, not created.'}
                          if kind in missing else {})}
                for kind in UNAUTHORED_ALLOWED}
    return {'intent': intent,
            'required_files': {kind: _file_record(root, _safe(root, path)) for kind, path in required.items()
                               if kind not in missing},
            'authored_metadata': authored,
            'current_inputs': sorted(current_inputs),
            'generated_outputs': generated,
            'observed_lifecycle': {'pipeline_state': pipeline_state,
                                  'current_artefact': context.current_artefact,
                                  'selected_source': {key: source.get(key) for key in
                                      ('root', 'manuscript_dir', 'edition', 'status', 'read_only')},
                                  'qualification': 'Registry/source inventory, not Work or scientific completion. Runtime telemetry excluded.'}}


#: THE PROJECT-HOME MARKER (empty state homes, 2026-10-16): a registered canonical project home that holds no exportable
#: authored file (an imported project whose selected TeX lives elsewhere) would vanish from a file-only Git/ZIP export
#: and its re-export would refuse. The exporter then writes this generated marker into that home. It is release data,
#: never a plan, reference, research record or source; the manifest walk never treats it as an authored project file.


from laplace.projects.project_data import PUBLISHED_EXPORT_SCHEMAS


def _source_dependencies(root: Path, project_files: list[Path]) -> list[dict]:
    found = []
    def walk(value, source, locator=""):
        if isinstance(value, dict):
            for key, child in value.items():
                here = f"{locator}.{key}" if locator else key
                if isinstance(child, str) and child and len(child) < 4096:
                    if key.lower() in {"doi", "url", "uri"}:
                        found.append({"record_file": source, "field": here, "value": child,
                                      "classification": "citation_or_source_identifier"})
                    elif key.lower() in {"path", "file", "local_path", "attachment_path", "source_file", "source_path", "bib_path", "location"}:
                        found.append({"record_file": source, "field": here, "value": child,
                                      "classification": "source_path_requires_scope_and_license_review"})
                walk(child, source, here)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, source, f"{locator}[{index}]")
    for path in project_files:
        if path.name == "references.json":
            walk(_json(path), path.relative_to(root).as_posix())
    return found


def selection_policy(value) -> dict:
    """The explicit reviewed file selection: {project: {path: row}} (schema laplace.writing-export-selection/1).

    Each project entry lists EVERY file of its project directory with its exact pin (sha256, bytes), a decision
    (include | exclude) and the reviewed reason; the project then exports exactly its included files. A project
    without an entry keeps the complete-directory walk. A proposal is not a policy: the schema must be explicit.
    """
    if value is None:
        return {}
    if not isinstance(value, dict) or value.get('schema') != SELECTION_SCHEMA or not isinstance(value.get('projects'), dict):
        raise ManifestError('selection policy needs schema ' + SELECTION_SCHEMA + ' and a projects map')
    result = {}
    for project, entry in value['projects'].items():
        files = entry.get('files') if isinstance(entry, dict) else None
        if not isinstance(project, str) or not project or not isinstance(files, list) or not files:
            raise ManifestError('selection policy project needs a non-empty files list: ' + str(project))
        rows = {}
        for row in files:
            if (not isinstance(row, dict) or not isinstance(row.get('path'), str) or not row['path']
                    or not isinstance(row.get('sha256'), str) or not HEX.fullmatch(row['sha256'].removeprefix('sha256:'))
                    or not row['sha256'].startswith('sha256:') or type(row.get('bytes')) is not int or row['bytes'] < 0
                    or row.get('decision') not in SELECTION_DECISIONS
                    or not isinstance(row.get('reason'), str) or not row['reason'].strip()):
                raise ManifestError('malformed selection row (path, sha256:<hex>, bytes, decision, reason): '
                                    + str(row.get('path') if isinstance(row, dict) else row))
            if row['path'] in rows:
                raise ManifestError('selection policy repeats a path: ' + row['path'])
            rows[row['path']] = row
        result[project] = rows
    return result


#: environment variables through which an author or session can add search paths; the provenance lookup drops them
_TEX_SEARCH_OVERRIDES = re.compile(r"^(TEX|KPATHSEA|BIBINPUTS|BSTINPUTS|ENCFONTS|TFMFONTS|VFFONTS|T1FONTS|OPENTYPEFONTS)")


def installed_tex_input(argument: str):
    """The TeX DISTRIBUTION file an ``\\input`` names, with its provenance, or None (repair2 RP-R4-R1).

    kpsewhich runs with every author/session search override removed (TEXINPUTS, TEXMF*, KPATHSEA*, ...) from a
    neutral directory, and the hit must lie inside the distribution trees kpsewhich itself reports (TEXMFDIST,
    TEXMFMAIN). An author file found through TEXINPUTS, TEXMFHOME, TEXMFLOCAL or any checkout is NOT installed: it
    stays an unresolved declaration. The record names the distribution root, the distribution-relative path and the
    pin, so a verifier (or the container gate) can re-observe the same file; nothing is copied from the system."""
    import shutil
    import subprocess
    name = argument.strip()
    if not name or '/' in name or '\\' in name or name.startswith('.'):
        return None
    tool = shutil.which('kpsewhich')
    if tool is None:
        return None
    env = {key: value for key, value in os.environ.items() if not _TEX_SEARCH_OVERRIDES.match(key)}
    def kpse(*args):
        try:
            return subprocess.run([tool, *args], capture_output=True, text=True, timeout=30, cwd='/', env=env).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ''
    roots = [Path(value).resolve() for value in dict.fromkeys((kpse('-var-value=TEXMFDIST'), kpse('-var-value=TEXMFMAIN')))
             if value and Path(value).is_absolute() and Path(value).is_dir()]
    for candidate in dict.fromkeys((name, name if Path(name).suffix else name + '.tex')):
        found = kpse(candidate)
        if not found or not Path(found).is_absolute() or not Path(found).is_file():
            continue
        resolved = Path(found).resolve()
        home = next((root for root in roots if resolved.is_relative_to(root)), None)
        if home is None:
            return None   # found, but not in the distribution: an author or local tree is never "installed"
        return {'path': str(resolved), 'distribution_root': str(home), 'relative': resolved.relative_to(home).as_posix(),
                'sha256': _sha(resolved.read_bytes())}
    return None


def selected_source_closure(root: Path, source: dict, intent: str = DEFAULT_PROJECT_INTENT) -> dict:
    """The selected TeX source and its COMPLETE declared local build inputs, repository-relative.

    The canonical declaration contract (``tex_dependencies.prepare_closure``: braced and unbraced ``\\input``,
    includes against the compilation directory, bibliography, local styles/classes, graphics and graphic paths) is
    the closure; the TeX-order traversal adds its cycle/readability refusals and the static ``dependency_paths``
    answer is kept as a subset witness. Every unresolved declaration refuses with its exact code, except:

      * an ``\\input`` of a bare name that kpsewhich finds inside the installed TeX DISTRIBUTION tree with author
        search overrides removed (``installed_inputs`` with root, relative path and pin; nothing is copied);
      * a missing bibliography database of a ``current-project-snapshot`` whose compilation directory holds the
        original ``<root>.bbl``: that exact pinned file travels as the frozen bibliography; editable bibliography
        regeneration stays unavailable and is named (``frozen_bibliography``). Nothing is invented.

    Installed package/class/style requests stay separate (``installed_requests``) and are never checkout files.
    A symlinked source path, a private/fenced member or a missing file refuses.
    """
    from laplace.manuscript import manuscript_source, tex_dependencies
    tree = manuscript_source.traversal(source['root'], repo_root=root)
    for row in tree.get('diagnostics') or []:
        kind = str(row.get('kind', ''))
        if kind in {'include-cycle', 'unreadable', 'missing-root', 'unsafe-include', 'ambiguous-include'}:
            raise ManifestError('selected source closure is incomplete (' + kind + '): '
                                + str(row.get('target') or row.get('file') or row.get('argument')))
    declared = tex_dependencies.prepare_closure(source.get('project') or 'selected', root, {'root': source['root']}, {})
    compile_dir = (root / source['root']).parent
    installed, frozen, refused = [], None, []
    for row in declared['diagnostics']:
        code = row.get('code')
        if code == 'MISSING_DECLARATION' and row.get('role') == 'include':
            found = installed_tex_input(str(row.get('argument') or ''))
            if found and not Path(found['path']).is_relative_to(root):
                installed.append({'argument': row['argument'], 'source': row.get('source'), 'status': 'INSTALLED_TEX_INPUT',
                                  'distribution_root': found['distribution_root'], 'relative': found['relative'],
                                  'sha256': found['sha256']})
                continue
        if code == 'MISSING_DECLARATION' and row.get('role') == 'bibliography':
            bbl = compile_dir / (Path(source['root']).stem + '.bbl')
            rel = bbl.relative_to(root).as_posix()
            if intent == 'current-project-snapshot' and bbl.is_file() and not _excluded(Path(rel)):
                _safe(root, rel)
                frozen = frozen or {'path': rel, 'sha256': _sha(bbl.read_bytes()), 'missing_databases': [],
                                    'status': 'FROZEN_ORIGINAL_BBL',
                                    'qualification': 'The original bibliography output travels with its exact pin; '
                                                     'the bibliography database is absent, so editable bibliography '
                                                     'regeneration is unavailable. Nothing is invented.'}
                frozen['missing_databases'].append(row.get('argument'))
                continue
        refused.append(row)   # every other diagnostic (missing, ambiguous, escaping, dynamic, unreadable, bound) refuses
    if refused:
        first = refused[0]
        raise ManifestError('selected source closure is incomplete (' + str(first.get('code')) + '): '
                            + '; '.join(str(row.get('argument') or row.get('path') or row.get('source') or row.get('code'))
                                        + (' [' + str(row.get('role')) + ']' if row.get('role') else '')
                                        for row in refused[:6]))
    if declared['aliases']:
        raise ManifestError('selected source closure uses a symlinked path (symlink input refused): '
                            + ', '.join(sorted(declared['aliases'])[:5]))
    found = {row['file'] for row in tree.get('sources') or []}
    found.update(row['canonical_path'] for row in declared['members'])
    for path in tex_dependencies.dependency_paths(root / source['root'], root, use_recorder=False):
        found.add(Path(path).resolve().relative_to(root).as_posix())
    if frozen:
        found.add(frozen['path'])
    files = []
    for rel in sorted(found):
        path = _safe(root, rel)
        if _excluded(Path(rel)) or not path.is_file():
            raise ManifestError('selected source dependency is private, fenced or unavailable: ' + rel)
        files.append(rel)
    return {'files': files, 'installed_inputs': installed, 'installed_requests': declared['installed_requests'],
            'frozen_bibliography': frozen}


def _under(rel: str, directory: str) -> bool:
    return Path(rel).is_relative_to(Path(directory))


def registered_homes(root: Path) -> dict:
    """Every registered local project's homes: its project directory and its registered TeX root."""
    from laplace.pipeline import registry as project_registry
    homes = {}
    for name in project_registry.all_projects(root):
        resolved = project_registry.resolve(name, repo_root=root)
        if resolved is None or resolved.external_root:
            continue
        rows = {value for value in (resolved.project_dir, getattr(resolved, "tex_root", None), resolved.manuscript_dir)
                if isinstance(value, str) and value not in {"", "."} and not Path(value).is_absolute()}
        if rows:
            homes[name] = sorted(rows)
    return homes


def build(root: Path, project: str, *, intent=DEFAULT_PROJECT_INTENT, _shared: dict | None = None) -> dict:
    root = root.resolve()
    shared = _shared if _shared is not None else {}
    if not _safe(root, "pyproject.toml").is_file():
        raise ManifestError("repo root lacks pyproject.toml")
    registry_path = _safe(root, "registry_projects.json")
    if "registry" not in shared:
        shared["registry"] = _json(registry_path)
    registry = shared["registry"]
    entries = [row for row in registry.get("projects", []) if row.get("name") == project]
    if len(entries) != 1:
        raise ManifestError("select exactly one explicitly registered project")
    entry = entries[0]
    # Use the same layout owner as the application. tex_root is the manuscript
    # subtree, not the complete project (numerics/research may be its siblings).
    from laplace.pipeline import registry as project_registry
    for key in ("project_dir", "tex_root"):
        if entry.get(key):
            _safe(root, entry[key])
    resolved = project_registry.resolve(project, repo_root=root)
    if resolved is None or resolved.external_root:
        raise ManifestError("selected project has no local canonical registry layout")
    directory = resolved.project_dir
    if not isinstance(directory, str) or directory in {"", "."}:
        raise ManifestError("project data needs an explicit non-repository-wide directory")
    project_root = _safe(root, directory)
    if not project_root.is_dir():
        raise ManifestError("registered project directory is missing")
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve(project, repo_root=root)
    source_root = source.get("root")
    if not isinstance(source_root, str) or not _safe(root, source_root).is_file():
        raise ManifestError("required selected manuscript source is missing")
    manuscript_dir = source.get("manuscript_dir")
    if not isinstance(manuscript_dir, str) or not _safe(root, manuscript_dir).is_dir():
        raise ManifestError("required manuscript directory is missing")
    closure = project_closure(root, project, intent, resolved=resolved, source=source,
                              selected_projects=shared.get("selected_projects"),
                              artifact_contexts=shared.setdefault("artifact_contexts", {}))
    if "common_grouped" not in shared:
        common = {
            "engine_python_candidates": _files(root, "src/laplace", ".py") + _files(root, "src/atlas", ".py"),
            "static_candidates": _files(root, "src/laplace/web/static_shared"),
            "launcher_and_profile_candidates": [],
        }
        for path in sorted((root / "src/laplace/web").glob("*.html")):
            common["static_candidates"].append(_safe(root, path.relative_to(root).as_posix()))
        for relative in ["scripts/laplace-python", "scripts/install_writing_app.py", "scripts/wake.py",
                         "scripts/sewup.py", "scripts/reembed.py", "scripts/reconstruct_node.py",
                         "pyproject.toml", "uv.lock", "runtime_profiles.toml", "profiles/writing",
                         "profiles/acceptance", "profiles/voice", "profiles/typography", "profiles/visual_style.json"]:
            common["launcher_and_profile_candidates"].extend(_files(root, relative))
        shared["common_grouped"] = common
    grouped = {name: list(paths) for name, paths in shared["common_grouped"].items()}
    grouped["selected_project"] = _project_files(root, project, directory, shared.get("project_dirs"))
    record_cache = shared.setdefault("file_records", {})
    def record(path):
        key = path.relative_to(root).as_posix()
        if key not in record_cache:
            record_cache[key] = _file_record(root, path)
        return record_cache[key]

    # THE SELECTED SOURCE CLOSURE (M5): the selected TeX and its exact local inputs (never an ancestor tree), even
    # outside this project's directory (an imported project's registered tex_root, Memory's source in Corpus).
    # Each exact file is bound to this project and to every selected project whose home holds it, and copied
    # once; a file in the home of a registered project that is NOT selected refuses and names that owner.
    if "registered_homes" not in shared:
        shared["registered_homes"] = registered_homes(root)
    selected_names = set(shared.get("selected_projects") or [project])
    source_qualified = selected_source_closure(root, source, intent)
    source_closure = source_qualified["files"]
    # every REQUIRED current input travels: closure files (source, owner metadata, built PDF), current record inputs
    # and the source closure; one outside this project's directory is bound and copied by the same rule
    required_inputs = sorted({row["path"] for row in closure["required_files"].values()}
                             | set(closure["current_inputs"]) | set(source_closure))
    bindings, outside = {}, []
    for rel in required_inputs:
        if _under(rel, directory):
            continue
        holders = {name for name, homes in shared["registered_homes"].items() if any(_under(rel, home) for home in homes)}
        foreign = sorted(holders - selected_names)
        if foreign:
            raise ManifestError("selected source dependency belongs to an unselected project: " + rel
                                + " (select " + ", ".join(foreign) + ")")
        bindings[rel] = sorted(holders | {project})
        outside.append(_safe(root, rel))
    grouped["selected_source_closure"] = outside

    # THE REVIEWED SELECTION (M5): a project with a policy entry exports exactly its pinned included files. Every
    # walked file must be reviewed; a changed or absent included file, a changed excluded file, a policy path
    # outside the project and an excluded required input all refuse before any copy.
    policy = (shared.get("selection_policy") or {}).get(project)
    excluded = {}
    if policy is not None:
        walked = {path.relative_to(root).as_posix(): path for path in grouped["selected_project"]}
        unreviewed = sorted(set(walked) - set(policy))
        if unreviewed:
            raise ManifestError(f"selection policy does not review {len(unreviewed)} project file(s), e.g. "
                                + ", ".join(unreviewed[:5]))
        included = []
        for rel, row in sorted(policy.items()):
            if not _under(rel, directory):
                raise ManifestError("selection policy path is outside its project: " + rel)
            if row["decision"] == "include":
                if rel not in walked:
                    raise ManifestError("selection policy includes an absent, private or fenced file: " + rel)
                current = record(walked[rel])
                if (current["sha256"], current["bytes"]) != (row["sha256"], row["bytes"]):
                    raise ManifestError("stale selection pin (included file changed): " + rel)
                included.append(walked[rel])
            else:
                if rel in walked:
                    current = record(walked[rel])
                    if (current["sha256"], current["bytes"]) != (row["sha256"], row["bytes"]):
                        raise ManifestError("stale selection pin (excluded file changed since review): " + rel)
                excluded[rel] = row
        grouped["selected_project"] = included
    dropped = [rel for rel in required_inputs if rel in excluded]
    if dropped:
        raise ManifestError("selection policy excludes a required current input: " + ", ".join(
            f"{rel} ({excluded[rel]['reason']})" for rel in dropped[:5]))

    if "talk" not in shared:
        shared["talk"] = _rows(root, "contract/talk.jsonl")
    talk = shared["talk"]
    if "journal" not in shared:
        shared["journal"] = _rows(root, "contract/journal.jsonl")
    if "lineage" not in shared:
        shared["lineage"] = published_lineage(root)
    definition_rows, definition_bodies, definition_packages = collect_definitions(root, project, read_rows=_rows)
    selected, history_lineage = select_history(root, project, talk=talk, journal=shared["journal"], additional=definition_rows,
                              recorded_roots=(shared["lineage"] or {}).get("roots", ()), read_rows=_rows, with_lineage=True)
    values = [item[3] for item in selected]
    for path in grouped["selected_project"]:
        if path.suffix == ".json":
            values.append(_json(path))
    bodies, missing, unresolved = _body_closure(root, values)
    bodies = sorted({r["path"]: r for r in [*bodies, *definition_bodies]}.values(), key=lambda r: r["path"])
    unresolved_code = []
    groups = {name: [record(path) for path in sorted(set(paths))] for name, paths in grouped.items()}
    third_party = set()
    for path in grouped["engine_python_candidates"]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            unresolved_code.append({"path": path.relative_to(root).as_posix(), "reason": "Python import inventory unavailable"})
            continue
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
            third_party.update(name.split(".")[0] for name in names if not name.startswith(("laplace", "atlas")))
    # THE QUALIFIED LINK AND WORK-INPUT INVENTORY (portable links, 2026-10-20): read where the owners keep them
    # (scripts/writing_portable_links.py), judged against this manifest's own selection; the exporter and the
    # verifier consume the same inventory and never a second store.
    portable = _portable()
    packaged = set(required_inputs) | {path.relative_to(root).as_posix() for path in grouped["selected_project"]}
    records_path = ((closure.get("authored_metadata") or {}).get("research_records") or {}).get("path")
    manuscript_links = portable.manuscript_links(root, project, source_closure, selected_projects=selected_names, packaged=packaged,
                                                 records_paths={project: records_path} if records_path else {})
    work_inputs = portable.work_inputs(root, project, packaged=packaged)
    return {"schema": "laplace.writing-evaluation-manifest/2", "repo_root": str(root), "project": project,
            **({"history_lineage": history_lineage} if history_lineage else {}),
            **({"workflow_definitions": definition_packages, "workflow_lineage": "Original scoped WDEF rows; legacy question-mark bank attribution is unavailable."} if definition_packages else {}),
            "export_ready": False, "manuscript_links": manuscript_links, "work_inputs": work_inputs, "registry_selection": {"source_sha256": _sha(registry_path.read_bytes()),
                "resolved_project_dir": directory,
                "selected_row": entry, "export_mode": "derived single-project registry; never copy the whole input registry"},
            "project_intent": intent, "project_closure": closure,
            "required_project_files": closure["required_files"],
            "selected_source_closure": {"files": source_closure, "bindings": bindings,
                                        "installed_inputs": source_qualified["installed_inputs"],
                                        "installed_requests": source_qualified["installed_requests"],
                                        "frozen_bibliography": source_qualified["frozen_bibliography"],
                                        "qualification": "selected TeX and its complete declared local inputs (tex_dependencies.prepare_closure: braced and unbraced input, includes, bibliography, local styles/classes, graphics); installed TeX inputs/requests are named, never copied; bindings name the selected owners of every required input outside the project directory"},
            "required_inputs": required_inputs,
            "selection": ({"policy": SELECTION_SCHEMA, "included": len(grouped["selected_project"]),
                           "excluded": [{"path": rel, "sha256": row["sha256"], "bytes": row["bytes"], "reason": row["reason"]}
                                        for rel, row in sorted(excluded.items())]}
                          if policy is not None else {"policy": None, "walk": "complete project directory"}),
            "groups": groups, "selected_rows": sorted((_row_record(item) for item in selected), key=lambda r: (r["file"], r["line"])),
            "row_selection": "exact project identity, linked unscoped session/turn rows and associated journal banks/acts; no substring matching",
            "public_body_refs": bodies, "missing_public_bodies": missing, "unresolved_body_formats": unresolved,
            "unresolved_code_inputs": unresolved_code,
            "scientific_source_dependencies": _source_dependencies(root, grouped["selected_project"]),
            "python_import_names": sorted(third_party),
            "dependency_scope": "conservative candidates and import names, not a verified minimal runtime or package-resolution closure",
            "required_reviews": ["clean-checkout bootstrap and runtime/state isolation", "candidate/history privacy and licensing", "scientific source scope and retrievability", "native/provider and browser behaviour", "source transformations for portable configuration"],
            "limits": ["read-only dry-run; no copying/install/service/provider invocation", "raw row/body contents are not embedded in this manifest", "private/global semantic state and provider transcripts are excluded", "missing typed bodies remain missing; shared user state is never consulted"]}


def _portable():
    """The portable-links projection beside this script (importable whichever way this module was loaded)."""
    try:
        import writing_portable_links
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import writing_portable_links
    return writing_portable_links


def size_report(rows) -> dict:
    """Selected bytes and every file over the per-file Git ceiling, with the actionable path."""
    rows = list(rows)
    return {"files": len(rows), "bytes": sum(row["bytes"] for row in rows),
            "per_file_limit_bytes": LARGE_FILE_BYTES,
            "oversized": sorted(({"path": row["path"], "bytes": row["bytes"]} for row in rows
                                 if row["bytes"] > LARGE_FILE_BYTES), key=lambda row: row["path"])}


def build_many(root: Path, projects, *, intents=None, selection=None) -> dict:
    """Build explicit project closures while scanning shared ledgers/runtime bytes once."""
    requested = [str(project) for project in projects]
    if not requested or any(not project for project in requested):
        raise ManifestError("select at least one explicitly registered project")
    if len(set(requested)) != len(requested):
        raise ManifestError("project selection must not repeat")
    selected_intents = project_intents(requested, intents)
    policy = selection_policy(selection)
    foreign = sorted(set(policy) - set(requested))
    if foreign:
        raise ManifestError("selection policy names an unselected project: " + ", ".join(foreign))
    from laplace.pipeline import registry as project_registry
    root = Path(root).resolve()
    project_dirs = {}
    for project in requested:
        resolved = project_registry.resolve(project, repo_root=root)
        if resolved is None or resolved.external_root or not resolved.project_dir or resolved.project_dir == ".":
            raise ManifestError("selected project has no local canonical registry layout: " + project)
        project_dirs[project] = resolved.project_dir
    shared = {"selected_projects": requested, "project_dirs": project_dirs, "selection_policy": policy,
              "registered_homes": registered_homes(root), "lineage": published_lineage(root)}
    manifests = {project: build(root, project, intent=selected_intents[project], _shared=shared) for project in requested}
    lineage = shared["lineage"]
    if lineage is not None:
        # a re-export never silently drops history its published export selected for the same project: every prior
        # selected row (by ledger file and exact row bytes) must be selected again; new rows (import boundaries) may add
        prior = lineage["source_manifest"]
        for project in requested:
            if project not in (prior.get("projects") or [prior.get("project")]):
                continue
            current = collections.Counter((row["file"], row["row_sha256"]) for row in manifests[project]["selected_rows"])
            missing = collections.Counter((row["file"], row["row_sha256"]) for row in project_rows(prior, project)) - current
            if missing:
                files = collections.Counter(file for file, _sha in missing.elements())
                raise ManifestError("re-export would drop %d history row(s) the published export selected for %s (%s)"
                                    % (sum(missing.values()), project, ", ".join(f"{file}: {count}" for file, count in sorted(files.items()))))
    recorded_roots = (lineage or {}).get("roots", [])
    # a required input of ONE project may live in ANOTHER selected project whose policy excluded it
    excluded = {row["path"]: (project, row["reason"]) for project, manifest in manifests.items()
                for row in manifest["selection"].get("excluded", [])}
    dropped = sorted({rel for manifest in manifests.values() for rel in manifest["required_inputs"] if rel in excluded})
    if dropped:
        raise ManifestError("selection policy excludes a required current input: " + ", ".join(
            f"{rel} ({excluded[rel][0]}: {excluded[rel][1]})" for rel in dropped[:5]))
    # the homes of registered projects this export did NOT select: a document link into one is truthfully named, never
    # copied (verify_writing_evaluation.document_links); nothing else about them travels
    unselected = {name: homes for name, homes in sorted(shared["registered_homes"].items()) if name not in requested}
    if len(requested) == 1:
        manifest = manifests[requested[0]]
        manifest["unselected_registered_homes"] = unselected
        manifest["recorded_roots"] = recorded_roots
        manifest["size"] = size_report([*{row["path"]: row for group in manifest["groups"].values() for row in group}.values(),
                                        *manifest["public_body_refs"]])
        return manifest
    groups = {}
    for manifest in manifests.values():
        for name, rows in manifest["groups"].items():
            by_path = groups.setdefault(name, {})
            for row in rows:
                prior = by_path.setdefault(row["path"], row)
                if prior != row:
                    raise ManifestError("project manifests disagree on exported bytes: " + row["path"])
    selected = {}
    for manifest in manifests.values():
        for row in manifest["selected_rows"]:
            key = (row["file"], row["line"])
            prior = selected.setdefault(key, row)
            if prior != row:
                raise ManifestError("project manifests disagree on selected history row")
    bodies = {}
    for manifest in manifests.values():
        for row in manifest["public_body_refs"]:
            bodies.setdefault(row["path"], row)
    bindings = {}
    for manifest in manifests.values():
        for rel, owners in manifest["selected_source_closure"]["bindings"].items():
            bindings.setdefault(rel, set()).update(owners)
    ordered = sorted(selected.values(), key=lambda row: (row["file"], row["line"]))
    positions = {(row["file"], row["line"]): i for i, row in enumerate(ordered)}
    # Selections share existing row coordinates; do not serialize the full history
    # metadata both under each project and again in the combined table.
    compact = {project: {**{k: v for k, v in manifest.items() if k != "selected_rows"},
                         "selected_row_indices": [positions[(r["file"], r["line"])]
                                                  for r in manifest["selected_rows"]]}
               for project, manifest in manifests.items()}
    return {
        "schema": "laplace.writing-evaluation-manifest/3",
        "repo_root": str(Path(root).resolve()),
        "projects": requested,
        "project_intents": selected_intents,
        "project_manifests": compact,
        "groups": {name: sorted(rows.values(), key=lambda row: row["path"])
                   for name, rows in groups.items()},
        "selected_rows": ordered,
        "public_body_refs": sorted(bodies.values(), key=lambda row: row["path"]),
        "missing_public_bodies": [row for manifest in manifests.values()
                                  for row in manifest["missing_public_bodies"]],
        "unresolved_body_formats": [row for manifest in manifests.values()
                                    for row in manifest["unresolved_body_formats"]],
        "scientific_source_dependencies": [row for manifest in manifests.values()
                                           for row in manifest["scientific_source_dependencies"]],
        "row_selection": "union of exact per-project selections, deduplicated by original file and line; original ledger order retained",
        "source_bindings": {rel: sorted(owners) for rel, owners in sorted(bindings.items())},
        "unselected_registered_homes": unselected,
        "recorded_roots": recorded_roots,
        "size": size_report([*{row["path"]: row for rows in groups.values() for row in rows.values()}.values(),
                             *bodies.values()]),
        "limits": manifests[requested[0]]["limits"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--project", action="append")
    selector = parser.add_mutually_exclusive_group()
    selector.add_argument("--check-docker-selectors", action="store_true")
    selector.add_argument("--write-docker-selectors", action="store_true")
    parser.add_argument("--project-intent", action="append", metavar="PROJECT=INTENT",
                        help="Explicit closure intent: completed-manuscript (default) or current-project-snapshot")
    parser.add_argument("--selection-policy", type=Path,
                        help="Reviewed per-file selection (" + SELECTION_SCHEMA + ") for projects that are not exported whole")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.check_docker_selectors or args.write_docker_selectors:
        if args.project or args.project_intent or args.selection_policy or args.output:
            parser.error('Selector generation/check does not select project data or output manifests.')
        result = write_docker_selectors(args.repo_root) if args.write_docker_selectors else check_docker_selectors(args.repo_root)
        print(json.dumps(result, sort_keys=True)); return 0 if result['ok'] else 1
    if not args.project:parser.error('--project is required for a project manifest.')
    try:
        policy = _json(args.selection_policy) if args.selection_policy else None
        result = build_many(args.repo_root, args.project, intents=args.project_intent, selection=policy)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        destination = args.output.resolve()
        protected = {args.repo_root.resolve() / row["path"] for group in result["groups"].values() for row in group}
        protected.update(args.repo_root.resolve() / row["path"] for row in result["public_body_refs"])
        protected.update(args.repo_root.resolve() / row["file"] for row in result["selected_rows"])
        protected.add(args.repo_root.resolve() / "registry_projects.json")
        if destination in protected:
            print(json.dumps({"error": "manifest output would overwrite an input"}))
            return 2
        if destination.exists():
            try:
                prior = _json(destination)
            except (ValueError, OSError):
                prior = {}
            prior_projects = prior.get("projects") or [prior.get("project")]
            current_projects = result.get("projects") or [result.get("project")]
            if prior.get("schema") != result["schema"] or prior_projects != current_projects:
                print(json.dumps({"error": "existing output is not a matching generated manifest"}))
                return 2
        args.output.write_text(output)
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
