#!/usr/bin/env python3
"""Materialise a reviewed Writing evaluation candidate into a NEW directory.

Never copies global state, provider transcripts, hooks or the source Git history.
Original project files and selected ledger rows retain their bytes and hashes.
Derived registry, imports and exact path aliases are declared separately.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from pathlib import PurePosixPath, PureWindowsPath

sys.path.insert(0, str(Path(__file__).resolve().parent))
import writing_eval_manifest as inventory


def export_project_data(root, destination, pinned_plan):
    """Explicit data-only policy; the unchanged export/export_projects defaults remain distributions."""
    from laplace.projects.project_handover import export
    return export(root, destination, pinned_plan)


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


PORTABLE_PATH_FIELDS = {"producer_base", "cwd", "result_absolute", "stdout_path",
                        "stderr_path", "cancel_path", "path", "source_path",
                        "local_path", "attachment_path"}
OPTIONAL_RESULT_STATES = {"FAILED", "CANCELLED"}
REQUIRED_RELEASE_INPUTS = (
    "docs/writing-evaluation-release.md",
    "docs/writing-evaluator-readme.md",
    "docs/writing-evaluator-agents.md",
    "docs/writing-container.md",
    "deploy/writing/Dockerfile",
    "deploy/writing/writing-entrypoint.sh",
    "deploy/writing/smoke.py",
)
# The exporter's own repeatable tooling, the necessary Atlas package declaration and the
# bounded operational documentation every export carries. Personal startup/close
# instructions are deliberately not part of this installation. A document an exported
# operational document links to belongs here too (tests/test_writing_evaluation_export.py
# checks that closure on this tree).
OPERATIONAL_INPUTS = inventory.OPERATIONAL_INPUTS  # the shared distribution declaration
DERIVED_RELEASE_PATHS = {
    "registry_projects.json", ".gitattributes", "README.md", ".gitignore", "AGENTS.md",
    "REVIEWER_GUIDE.md", "pytest.ini",
    "profiles/writing_sources.json", "writing-portability.json",
    "release/source-manifest.json", "release/export-manifest.json",
    "contract/talk.jsonl", "contract/journal.jsonl", "corpus_friction/work_orders.jsonl",
    "release/selection-policy.json", "release/alias-proofs.json",
}
SELECTION_POLICY = 'release/selection-policy.json'
ALIAS_PROOFS = 'release/alias-proofs.json'


def size_refusal(rows):
    """Refuse BEFORE copying: any SOURCE INPUT over the per-file Git ceiling (the actionable source path). Omission is
    never evidence availability: an oversized required file refuses rather than being dropped. The whole written
    output (generated files included) is gated separately by output_refusal."""
    report = inventory.size_report(rows)
    if report['oversized']:
        raise ValueError('export refused: file(s) over ' + str(inventory.LARGE_FILE_BYTES) + ' bytes (no external-asset '
                         'policy is defined; review the selection or keep the asset outside this export): '
                         + ', '.join(f"{row['path']} ({row['bytes']} B)" for row in report['oversized'][:10]))
    return report


def output_refusal(rows, max_total_bytes=None):
    """Refuse BEFORE the destination exists: any planned written file (copied, companion, history, travelled policy or
    generated manifest) over the per-file ceiling, or a full output over an explicit --max-total-bytes budget."""
    rows = list(rows)
    oversized = [row for row in rows if row['bytes'] > inventory.LARGE_FILE_BYTES]
    if oversized:
        raise ValueError('export refused: planned output file(s) over ' + str(inventory.LARGE_FILE_BYTES) + ' bytes: '
                         + ', '.join(f"{row['path']} ({row['bytes']} B)" for row in sorted(oversized, key=lambda r: r['path'])[:10]))
    total = sum(row['bytes'] for row in rows)
    if max_total_bytes is not None and total > max_total_bytes:
        raise ValueError(f"export refused: the planned output of {len(rows)} files, {total} bytes, would exceed the stated budget {max_total_bytes}")
    return total


def _project_relative_absolute(value, project_dir):
    """Map one absolute spelling only through the canonical registered project anchor."""
    path = PurePosixPath(str(value).replace('\\', '/'))
    if not path.is_absolute():
        return None
    parts, anchor = path.parts, PurePosixPath(project_dir).parts
    starts = [i for i in range(len(parts) - len(anchor) + 1)
              if parts[i:i + len(anchor)] == anchor]
    if len(starts) != 1:
        raise ValueError("historical path has no unique canonical project anchor: " + str(value))
    index = starts[0]
    return PurePosixPath(*parts[index:]).as_posix()


def _recorded_namespace_refused(parsed) -> bool:
    """Private, cache, runtime and secret namespaces in a recorded spelling, wherever it points."""
    parts = set(parsed.parts)
    name = parsed.name
    return bool(parts & (inventory.PRIVATE | inventory.CACHES | {'.laplace-state', '.laplace-cache'})
                or name in inventory.SECRET_NAMES or name == '.env' or name.startswith('.env.')
                or parsed.suffix in {'.pem', '.key', '.pyc'})


def _recorded_path_hash(container, key):
    """Normalise the two recorded SHA-256 spellings without changing source bytes."""
    name = 'source_sha256' if key == 'source_path' else 'sha256'
    if name not in container:
        return None
    value = container[name]
    if not isinstance(value, str):
        raise ValueError(f"malformed recorded {name}")
    raw = value[7:] if value.startswith('sha256:') else value
    if len(raw) != 64 or any(ch not in '0123456789abcdef' for ch in raw.lower()):
        raise ValueError(f"malformed recorded {name}")
    return 'sha256:' + raw.lower()


def _published_alias(root, candidates, recorded, state):
    """The exact published alias for `recorded` from a prior export's portability manifest, with
    its primary AND every version verified against the published export manifest pins and the
    present bytes; the recorded spelling must still resolve (unpinned → primary, pinned → version)
    through the portability owner. Directory aliases alone are no authority. Returns the alias
    template to carry forward, or None when the manifest or spelling is absent."""
    from laplace.projects import writing_portability
    if 'data' not in state:
        admitted = inventory.published_admission(root)   # the one shared fence/owner/schema/pin admission
        if admitted is None:
            return None
        state['data'], state['pins'] = admitted['index'], admitted['pins']
    data, pins = state['data'], state['pins']
    alias = (data.get('source_aliases') or {}).get(recorded)
    if not alias and recorded.startswith('\\'):
        alias = (data.get('source_aliases') or {}).get(recorded.replace('\\', '/'))
    if alias is None:
        return None   # directory aliases alone are not exact source proof
    def verified(entry, label):
        rel = entry.get('path') if isinstance(entry, dict) else None
        if not isinstance(rel, str):
            raise ValueError('published source alias ' + label + ' has no exact target')
        target = inventory._safe(root, rel)
        if inventory._excluded(Path(rel)) or {'.laplace-state', '.laplace-cache'} & set(Path(rel).parts):
            raise ValueError('private or runtime published alias target refused')
        original = _recorded_path_hash(entry, 'path') if 'sha256' in entry else _recorded_path_hash({'sha256': entry.get('original_sha256')}, 'path')
        declared = pins.get(rel)
        if not original or not declared or original != declared.get('sha256'):
            raise ValueError('published source alias ' + label + ' pin is unavailable or changed: ' + rel)
        if not target.is_file():
            raise ValueError('published source alias ' + label + ' target is missing: ' + rel)
        current = inventory._file_record(root, target)
        if current['sha256'] != original:
            raise ValueError('published source alias ' + label + ' bytes changed: ' + rel)
        previous = candidates.setdefault(rel, current)
        if previous['sha256'] != current['sha256']:
            raise ValueError('published source alias conflicts with candidate: ' + rel)
        return rel, original
    primary_rel, primary_sha = verified(alias, 'primary')
    if writing_portability.source_path(recorded, root) != inventory._safe(root, primary_rel).resolve():
        raise ValueError('published source alias resolution changed')
    versions = {}
    for pin, entry in (alias.get('versions') or {}).items():
        pinned = _recorded_path_hash({'sha256': pin}, 'path')
        rel, sha = verified(entry, 'version ' + pin)
        if sha != pinned or rel == primary_rel:
            raise ValueError('published source alias version pin is unavailable or changed: ' + recorded)
        if writing_portability.source_path(recorded, root, sha256=pin) != inventory._safe(root, rel).resolve():
            raise ValueError('published source alias version resolution changed: ' + recorded)
        versions[pinned] = {'path': rel, 'original_sha256': pinned,
                            **({'reason': entry['reason']} if isinstance(entry.get('reason'), str) else {}),
                            'basis': 'exact published portability alias version and original source pin'}
    return {'path': primary_rel, 'original_sha256': primary_sha, **({'versions': versions} if versions else {}),
            'proof': 'exact published portability alias and original source pin'}


def _historical_aliases(root, manifest, candidates, explicit_external=None):
    """Exact aliases proven from immutable project records and exported target bytes.

    `explicit_external` maps a recorded spelling to {pin: selection} (or, for older callers,
    to one pin string). A recorded reading whose sibling hash equals an explicit pin resolves
    to that pinned companion even when the spelling also names a current checkout file whose
    bytes have since changed; a reading without a sibling hash can select only an unambiguous
    single pin.
    """
    project_dir = manifest['registry_selection']['resolved_project_dir']
    aliases, proofs = {}, []
    explicit_external = {old: (pins if isinstance(pins, dict) else {pins: {'path': None, 'original_sha256': pins}})
                         for old, pins in (explicit_external or {}).items()}
    published_state = {}
    def explicit_proof(child, recorded_hash, source, here):
        """The explicit companion selection for a recorded spelling, or None."""
        pins = explicit_external.get(child)
        if not pins:
            return None
        if recorded_hash:
            if recorded_hash not in pins:
                raise ValueError(f"recorded source hash mismatch: {source}:{here}")
            selection = pins[recorded_hash]
        elif len(pins) == 1:
            selection = next(iter(pins.values()))
        else:
            raise ValueError(f"ambiguous historical reading without a recorded hash: {source}:{here}")
        rel = candidates.get(child) if child in candidates else None
        return {"record_file": source, "field": here, "recorded": child, "availability": "explicit-supplementary",
                **({"path": selection['path']} if selection.get('path') else {}),
                **({"recorded_sha256": recorded_hash, "sha256": selection['original_sha256']} if recorded_hash else {"sha256": selection['original_sha256']}),
                **({"resolution_basis": "explicit pinned companion of an original reading; the current checkout file at this address has different bytes and keeps its own path"}
                   if _current_address(child) else {})}
    def _current_address(child):
        path = Path(child)
        if not path.is_absolute() or not path.is_relative_to(root):
            return False
        return candidates.get(path.relative_to(root).as_posix()) is not None
    def selected_repository_target(recorded, recorded_hash, source, locator):
        """Admit no new input: bind an exact current-root address to selected bytes."""
        path = Path(recorded)
        if not path.is_absolute() or not path.is_relative_to(root):
            return None
        relative = path.relative_to(root)
        if '..' in relative.parts:
            raise ValueError(f"unsafe current-root source path: {source}:{locator}")
        rel = relative.as_posix()
        row = candidates.get(rel)
        if row is None:
            return None
        if inventory._excluded(relative) or {'.laplace-state', '.laplace-cache'} & set(relative.parts):
            raise ValueError(f"private or runtime source alias target refused: {source}:{locator}")
        target = inventory._safe(root, rel)
        if not recorded_hash:
            raise ValueError(f"current-root source alias requires recorded hash: {source}:{locator}")
        if recorded_hash != row['sha256']:
            raise ValueError(f"recorded source hash mismatch: {source}:{locator}")
        if not target.is_file() or inventory._file_record(root, target)['sha256'] != row['sha256']:
            raise ValueError(f"selected source bytes changed: {source}:{locator}")
        return rel

    def published_target(recorded, recorded_hash=None):
        """Reuse only an exact pinned published alias, with its exact versions; never its original location.

        Returns (rel, sha, template): the target this reading resolves to (the version whose pin
        equals the recorded hash, else the primary), its pin, and the complete alias to carry
        into the new export (primary and every verified version), or None.
        """
        template = _published_alias(root, candidates, recorded, published_state)
        if template is None:
            return None
        versions = template.get('versions') or {}
        if recorded_hash and recorded_hash in versions:
            return versions[recorded_hash]['path'], recorded_hash, template
        return template['path'], template['original_sha256'], template
    project_files = [row['path'] for row in manifest['groups']['selected_project']
                     if row['path'].endswith('references.json')
                     or '/research_runs/run-' in row['path'] and row['path'].endswith('.json')]
    def walk(value, source, locator="", optional_values=frozenset()):
        if isinstance(value, dict):
            for key, child in value.items():
                here = locator + "." + key if locator else key
                if key in PORTABLE_PATH_FIELDS and isinstance(child, str):
                    recorded_hash = _recorded_path_hash(value, key)
                    reused = None
                    selected_repository = None
                    try:
                        rel = _project_relative_absolute(child, project_dir)
                    except ValueError:
                        pins = explicit_external.get(child)
                        if pins and (recorded_hash in pins or not recorded_hash):
                            # the explicit pin stands for this reading, current file or not; a reading
                            # without a recorded hash may select one pin only (explicit_proof refuses two)
                            proofs.append(explicit_proof(child, recorded_hash, source, here))
                            continue
                        selected_repository = selected_repository_target(child, recorded_hash, source, here)
                        if selected_repository is not None:
                            rel = selected_repository
                        elif pins:
                            proofs.append(explicit_proof(child, recorded_hash, source, here))   # refuses: the recorded hash matches no pin
                            continue
                        else:
                            reused = published_target(child, recorded_hash)
                            if reused is None:
                                raise
                            rel = reused[0]
                    if rel is None:
                        from laplace.projects import writing_portability
                        if child in explicit_external:
                            proofs.append(explicit_proof(child, recorded_hash, source, here))
                            continue
                        if writing_portability._recorded_absolute(child):
                            reused = published_target(child, recorded_hash)
                            if reused is None:
                                raise ValueError('absolute source has no exact published alias: ' + child)
                            rel = reused[0]
                    if rel:
                        optional = key == 'cancel_path' or child in optional_values
                        target = inventory._safe(root, rel)
                        row = candidates.get(rel)
                        if not target.exists() and not optional:
                            raise ValueError(f"historical target missing: {source}:{here} -> {rel}")
                        if target.exists() and target.is_file() and row is None:
                            raise ValueError(f"historical target omitted from export: {source}:{here} -> {rel}")
                        proof = {"record_file": source, "field": here, "recorded": child,
                                 "path": rel, "availability": "present" if target.exists() else "absent-optional"}
                        if reused:
                            proof['resolution_basis'] = ('exact published portability alias version and original source pin'
                                                         if rel != reused[2]['path'] else 'exact published portability alias and original source pin')
                            proof['published_original_sha256'] = reused[1]
                        elif selected_repository:
                            proof['resolution_basis'] = 'exact selected current-root address and recorded source pin'
                        if row:
                            proof['sha256'] = row['sha256']
                            if recorded_hash and recorded_hash != row['sha256']:
                                raise ValueError(f"recorded source hash mismatch: {source}:{here}")
                            if recorded_hash:
                                proof['recorded_sha256'] = recorded_hash
                                proof['identity_basis'] = 'recorded sibling hash equals exported bytes'
                            stem = target.stem.lower()
                            if len(stem) == 64 and all(ch in '0123456789abcdef' for ch in stem):
                                if row['sha256'] != 'sha256:' + stem:
                                    raise ValueError(f"historical content hash mismatch: {source}:{here}")
                                proof['identity_basis'] = ((proof.get('identity_basis') + '; ') if proof.get('identity_basis') else '') + 'content-addressed filename equals exported bytes'
                        carried = reused[2] if reused else {"path": rel, **({"original_sha256": row['sha256']} if row else {}),
                                                   "proof": ("exact selected current-root address and recorded source pin"
                                                             if selected_repository else "canonical registered project suffix")}
                        aliases.setdefault(child, carried)
                        if aliases[child]['path'] != carried['path']:
                            raise ValueError("conflicting historical alias: " + child)
                        proofs.append(proof)
                walk(child, source, here, optional_values)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, source, f"{locator}[{index}]", optional_values)
    for rel in project_files:
        value = inventory._json(inventory._safe(root, rel))
        file_optional = set()
        if not rel.endswith('references.json'):
            if not isinstance(value, dict) or not any(value.get(key) for key in
                    ("producer_base", "result_absolute", "stdout_path", "stderr_path")):
                continue
            receipt_path = inventory._safe(root, rel).with_name(
                inventory._safe(root, rel).stem + '.receipt.json')
            receipt = inventory._json(receipt_path) if receipt_path.is_file() else {}
            if receipt.get('state') in OPTIONAL_RESULT_STATES and value.get('result_absolute'):
                file_optional.add(value['result_absolute'])
            value = {key: value.get(key) for key in ("producer_base", "cwd", "result_absolute",
                     "stdout_path", "stderr_path", "cancel_path") if value.get(key)}
        walk(value, rel, optional_values=frozenset(file_optional))
    return aliases, proofs


def export(root: Path, destination: Path, project: str, extra_sources=(), *, intents=None, selection=None,
           max_total_bytes=None, work_inputs=None, portable_document=False):
    """Backward-compatible single-project export API."""
    return export_projects(root, destination, [project], extra_sources, intents=intents, selection=selection,
                           max_total_bytes=max_total_bytes, work_inputs=work_inputs, portable_document=portable_document)


def export_projects(root: Path, destination: Path, projects, extra_sources=(), *, intents=None, selection=None,
                    max_total_bytes=None, work_inputs=None, portable_document=False):
    """`selection` is the exact bytes (or parsed value) of a reviewed selection policy
    (writing_eval_manifest.SELECTION_SCHEMA); it travels as release/selection-policy.json.

    ``work_inputs='current'`` selects every current input of a reviewed Work obligation that lies outside the
    manuscript closure through the existing pinned supplementary mechanism, at its exact repository path and its
    review pin (a changed, missing or private input refuses). ``portable_document`` stages a derived portable copy
    of each selected manuscript (links to a readable appendix, an HTML list, a PDF through the declared build chain
    when it can run) and declares its input/output mapping in the export manifest. Both are explicit selections;
    without them the manifest still states every link and Work-input disposition."""
    if work_inputs not in (None, 'current'):
        raise ValueError("work_inputs selects 'current' (the current inputs of reviewed Work obligations) or nothing")
    root, destination = root.resolve(), destination.resolve()
    projects = [str(project) for project in projects]
    if destination.exists() or destination.is_relative_to(root) or root.is_relative_to(destination):
        raise ValueError("export requires a new directory outside the source checkout")
    selected_intents = inventory.project_intents(projects, intents)
    policy_raw = (selection if isinstance(selection, (bytes, bytearray)) or selection is None
                  else encoded(selection))
    policy_value = json.loads(policy_raw) if policy_raw is not None else None
    combined = inventory.build_many(root, projects, intents=selected_intents, selection=policy_value)
    manifests = (combined.get('project_manifests') or
                 {combined['project']: combined})
    if combined['missing_public_bodies'] or combined['unresolved_body_formats']:
        raise ValueError("history body closure is incomplete")
    manifest_hashes = {project: digest(encoded(manifest))
                       for project, manifest in manifests.items()}
    original_manifest_hash = digest(encoded(combined))
    # CURRENT WORK INPUTS (portable links, 2026-10-20): an explicit selection of the current inputs of reviewed Work
    # obligations outside the manuscript closure, admitted through the SAME pinned supplementary route below (its
    # containment, privacy and collision rules); never a crawl of historical row paths.
    links_owner = inventory._portable()
    preselected = {r['path'] for group in combined['groups'].values() for r in group} | {r['path'] for r in combined['public_body_refs']}
    extra_sources = list(extra_sources)
    work_input_omissions = {}
    if work_inputs == 'current':
        for project in projects:
            admitted, omitted = links_owner.admit_current_work_inputs(root, links_owner.work_inputs(root, project, packaged=preselected))
            extra_sources.extend(admitted)
            work_input_omissions[project] = omitted
    # External inputs must be explicitly named and pinned, never discovered and
    # copied by following arbitrary historical paths.
    external = []
    for entry in extra_sources:
        path = Path(entry['path']).resolve()
        if (entry.get('repository_path') == 'profiles/writing/sealed-reader-qualification.json'
                or path == root / 'profiles/writing/sealed-reader-qualification.json'):
            raise ValueError('Host-local reader qualification is not a portable source input.')
        raw = path.read_bytes()
        sha = digest(raw)
        if sha != entry['sha256']:
            raise ValueError("supplementary source changed: " + str(path))
        if not entry.get('reason'):
            raise ValueError("supplementary source needs its release inclusion reason")
        repository_path = entry.get('repository_path')
        if repository_path is not None:
            if (not isinstance(repository_path, str) or not path.is_relative_to(root)
                    or repository_path != path.relative_to(root).as_posix()):
                raise ValueError("repository_path must be the source's exact repo-relative spelling")
            inventory._safe(root, repository_path)
            relative = Path(repository_path)
            if (inventory._excluded(relative) or
                    {'.laplace-state', '.laplace-cache'} & set(relative.parts)):
                raise ValueError("private or runtime supplementary repository_path refused")
        recorded = entry.get('recorded_path')
        if recorded is not None:
            if not isinstance(recorded, str) or not recorded or any(ord(ch) < 32 for ch in recorded):
                raise ValueError('recorded_path needs a valid absolute spelling')
            original = PurePosixPath(recorded) if recorded.startswith('/') else PureWindowsPath(recorded)
            if not original.is_absolute() or '..' in original.parts:
                raise ValueError('recorded_path must be an absolute spelling without traversal')
            if repository_path:
                suffix = PurePosixPath(repository_path).parts
                if (original.parts[-len(suffix):] != suffix
                        or sum(original.parts[i:i + len(suffix)] == suffix
                               for i in range(len(original.parts) - len(suffix) + 1)) != 1):
                    raise ValueError('recorded_path must have the exact unique repository_path suffix')
            else:
                # A content-addressed companion that carries the ORIGINAL reading of a recorded
                # address: the current file (if any) stays current under its own path; the
                # original bytes travel beside it and the alias names them by their pin only.
                # The captured bytes come from OUTSIDE the repository (a reviewed input); a file
                # inside the repository keeps using the qualified repository_path route.
                content_addressed = (path.parent == (root / 'supplementary_sources').resolve()
                                     and path.stem.lower() == entry['sha256'].split(':')[-1])   # a re-export carries its own companions
                if path.is_relative_to(root) and not content_addressed:
                    raise ValueError('recorded_path needs repository_path for a companion inside the repository: ' + str(path))
                # the PARSED spelling is judged wherever it points (another checkout, Windows): no
                # private/cache/runtime/secret namespace, and the companion keeps the recorded name
                if _recorded_namespace_refused(original):
                    raise ValueError('private or runtime recorded_path refused: ' + recorded)
                if not content_addressed and original.name != path.name:
                    raise ValueError('historical companion must keep the recorded file name: ' + recorded)
                original_path = Path(recorded)
                if original_path.is_absolute() and original_path.is_relative_to(root):
                    current = inventory._safe(root, original_path.relative_to(root).as_posix())
                    if current.is_file() and inventory._file_record(root, current)['sha256'] == entry['sha256']:
                        raise ValueError('historical companion duplicates the current file; select the current repository_path instead: ' + recorded)
        external.append((path, raw, entry))
    candidates = {r['path']: r for group in combined['groups'].values() for r in group}
    candidates.update({r['path']: r for r in combined['public_body_refs']})
    # Export its own repeatable tooling, necessary Atlas package declaration and
    # bounded operational documentation (OPERATIONAL_INPUTS).
    for rel in OPERATIONAL_INPUTS:
        for path in inventory._files(root, rel):
            row = inventory._file_record(root, path)
            candidates[row['path']] = row
    for path in inventory.generated_release_files(root):
        row = inventory._file_record(root, path)
        candidates[row['path']] = row
    missing_release = [rel for rel in REQUIRED_RELEASE_INPUTS
                       if not inventory._safe(root, rel).is_file()]
    if missing_release:
        raise ValueError("required release input missing: " + ", ".join(missing_release))
    # spelling → {pin → selection}: a recorded spelling may name the current file AND the
    # pinned original bytes of an earlier reading; two selections of one spelling must differ
    # by pin, never by destination of the same pin
    explicit_aliases, qualified_spellings = {}, set()
    for path, _raw, entry in external:
        rel = entry.get('repository_path') or ('supplementary_sources/' +
              entry['sha256'].split(':')[-1] + path.suffix.lower())
        for spelling in [str(path), *([entry['recorded_path']] if entry.get('recorded_path') else [])]:
            selection = {'path': rel, 'original_sha256': entry['sha256'], 'reason': entry['reason']}
            pins = explicit_aliases.setdefault(spelling, {})
            previous = pins.setdefault(entry['sha256'], selection)
            if previous != selection:
                raise ValueError('conflicting explicit supplementary alias: ' + spelling)
            if entry.get('repository_path') is not None:
                qualified_spellings.add(spelling)
    # order-independent: a spelling owned by a qualified companion (its raw source address or its
    # recorded address) may carry exactly one pin
    for spelling in sorted(qualified_spellings):
        if len(explicit_aliases.get(spelling, {})) > 1:
            raise ValueError('a qualified repository_path companion cannot share its spelling with another pin: ' + spelling)
    historical_aliases, alias_proofs = {}, []
    for manifest in manifests.values():
        aliases, proofs = _historical_aliases(root, manifest, candidates, explicit_aliases)
        for old, row in aliases.items():
            prior = historical_aliases.setdefault(old, row)
            if prior != row:
                raise ValueError("conflicting historical alias across projects: " + old)
        alias_proofs.extend(proofs)
    for old, pins in explicit_aliases.items():
        prior = historical_aliases.get(old)
        if prior:
            same_pin = pins.get(prior.get('original_sha256'))
            if same_pin and same_pin['path'] != prior['path']:
                raise ValueError('conflicting explicit and historical alias: ' + old)
            if not same_pin and len(pins) == 1 and prior.get('original_sha256') is None:
                raise ValueError('conflicting explicit and historical alias: ' + old)
    # These launchers assume the author's authored wake, device runtime and
    # semantic state. The browser release has its own explicit server entry.
    for rel in ['scripts/laplace-python', 'scripts/install_writing_app.py', 'scripts/wake.py',
                'scripts/sewup.py', 'scripts/reembed.py', 'scripts/reconstruct_node.py',
                'runtime_profiles.toml',
                # Host qualification is bound to local executable/source and local evidence bodies.
                # Portable releases carry the reader owner, never this host's installed proof.
                'profiles/writing/sealed-reader-qualification.json']:
        candidates.pop(rel, None)
    # A re-export keeps the published alias of every explicit spelling: its primary and EVERY
    # carried version are verified and entered as candidates HERE, before the copied-file set is
    # frozen, so no carried version can be declared without its target travelling (Sol H1 residual).
    published_seeds, published_state = {}, {}
    owned = {str(path) for path, _raw, _entry in external} | {str(root / rel) for rel in candidates}
    for spelling in sorted(explicit_aliases):
        if spelling not in historical_aliases and spelling not in owned:
            seed = _published_alias(root, candidates, spelling, published_state)
            if seed is not None:
                published_seeds[spelling] = seed
    selected = defaultdict(dict)
    for row in combined['selected_rows']:
        selected[row['file']][row['line']] = row
    # Explicit public companions can preserve a qualified repository address.
    # They may not overwrite selected code, project/history or derived views.
    external_destinations = {}
    for original, _raw, entry in external:
        rel = entry.get('repository_path') or ('supplementary_sources/' +
              entry['sha256'].split(':')[-1] + original.suffix.lower())
        if (entry.get('repository_path') is not None and
                (rel in candidates or rel in selected or rel in DERIVED_RELEASE_PATHS)):
            raise ValueError("supplementary repository_path collides with release input: " + rel)
        qualified = entry.get('repository_path') is not None
        if rel in external_destinations and (qualified or external_destinations[rel]):
            raise ValueError("supplementary destinations collide: " + rel)
        external_destinations[rel] = qualified
    ledger_bytes = {}
    sessions_by_project = {project: [row['id'] for row in inventory.project_rows(combined, project)
                                     if row.get('record') == 'writing-session' and row.get('id')]
                           for project, manifest in manifests.items()}
    for rel, wanted in selected.items():
        kept = []
        with inventory._safe(root, rel).open('rb') as stream:
            for number, raw in enumerate(stream, 1):
                if number not in wanted:
                    continue
                if digest(raw) != wanted[number]['row_sha256']:
                    raise ValueError(f"selected history row changed: {rel}:{number}")
                kept.append(raw)
        if len(kept) != len(wanted):
            raise ValueError("selected history rows disappeared: " + rel)
        ledger_bytes[rel] = b''.join(kept)
    # per-file refusal over every source input first (the existing selected_size report: source-input bytes only)
    selected_size = size_refusal([*candidates.values(),
                                  *({'path': entry.get('repository_path') or str(path), 'bytes': len(raw)}
                                    for path, raw, entry in external),
                                  *({'path': rel, 'bytes': len(raw)} for rel, raw in ledger_bytes.items())])
    # THE PLANNED OUTPUT (repair1 RP-R3): every file this export writes -- copied inputs, supplementary companions,
    # selected history, the travelled selection policy and every generated manifest -- is planned in memory with its
    # exact byte count BEFORE the destination exists; the per-file ceiling applies to each and --max-total-bytes to
    # the whole output (the export manifest included). Nothing is dropped to fit.
    now = datetime.now(timezone.utc).isoformat()
    copies, aliases, derived, planned = [], {}, [], {}
    for rel, row in sorted(candidates.items()):
        copies.append({'path': rel, 'bytes': row['bytes'], 'sha256': row['sha256']})
        aliases[str(root / rel)] = {'path': rel, 'original_sha256': row['sha256']}
    aliases.update(historical_aliases)
    for original, raw, entry in external:
        rel = entry.get('repository_path') or ('supplementary_sources/' +
              entry['sha256'].split(':')[-1] + original.suffix.lower())
        copies.append({'path': rel, 'bytes': len(raw), 'sha256': digest(raw)})
        planned[rel] = raw
        prior = aliases.get(str(original))
        if prior and prior.get('path') != rel:
            raise ValueError("conflicting explicit and historical alias: " + str(original))
        aliases[str(original)] = {'path': rel, 'original_sha256': entry['sha256'], 'reason': entry['reason']}
    for spelling, pins in explicit_aliases.items():
        current = aliases.get(spelling)
        if current is None:
            current = published_seeds.get(spelling)   # verified above: the published primary and all its versions
            if current is not None:
                aliases[spelling] = current
        for pin, selection in pins.items():
            if current is None:
                aliases[spelling] = current = dict(selection)
            elif current.get('path') == selection['path']:
                continue
            elif current.get('original_sha256') and current['original_sha256'] != pin:
                # the spelling names a current checkout file; the companion is an exact earlier
                # version of it, reachable only by its recorded pin (writing_portability.source_path)
                versions = current.setdefault('versions', {})
                known = versions.get(pin)
                if known is not None and (known.get('path') != selection['path'] or known.get('original_sha256') != pin):
                    raise ValueError('conflicting historical versions for one spelling: ' + spelling)
                if known is None:
                    versions[pin] = {**selection, 'basis': 'explicit pinned companion of an original reading; the current file keeps its own path'}
            else:
                raise ValueError('conflicting explicit and historical alias: ' + spelling)
    def plan(rel, raw, derivation=None):
        planned[rel] = raw
        derived.append({'path': rel, 'bytes': len(raw), 'sha256': digest(raw), **({'derivation': derivation} if derivation else {})})
    imports = [{'record': 'writing-session-import',
                'id': 'IMPORT-' + hashlib.sha256((manifest_hashes[project] + session).encode()).hexdigest()[:24],
                'session_id': session, 'project': project, 'ts': now,
                'source_manifest_sha256': manifest_hashes[project]}
               for project in projects for session in sessions_by_project[project]]
    for rel, raw in ledger_bytes.items():
        if not (imports and rel == 'contract/talk.jsonl'):
            plan(rel, raw, 'exact selected original rows in original order')
    if imports:
        plan('contract/talk.jsonl', ledger_bytes.get('contract/talk.jsonl', b'')
             + b''.join(encoded(row).replace(b'\n', b'') + b'\n' for row in imports),
             'exact selected original rows, then explicit imported-session boundaries')
    registry = {'projects': [manifests[project]['registry_selection']['selected_row']
                             for project in projects]}
    plan('registry_projects.json', encoded(registry))
    plan('.gitattributes', b'# Preserve exact recorded bytes on every operating system.\n* -text\n')
    readme = root / 'docs/writing-evaluator-readme.md'
    if readme.is_file():
        plan('README.md', readme.read_bytes())
    plan('.gitignore', b'.venv/\n.laplace-state/\n.laplace-cache/\n__pycache__/\n.pytest_cache/\n.pytest-tmp/\n*.egg-info/\nbuild/\ndist/\n.env\n.env.*\n.auth/\n.credentials/\n*.lock.tmp\n')
    plan('AGENTS.md', (root / 'docs/writing-evaluator-agents.md').read_bytes())
    # Portable reviewer entry and test scope are authored for the package root.
    for template, target in [('docs/writing-reviewer-guide.md', 'REVIEWER_GUIDE.md'),
                             ('docs/writing-pytest.ini', 'pytest.ini')]:
        source = root / template
        if source.is_file():
            plan(target, source.read_bytes())
    plan('profiles/writing_sources.json', encoded({'repositories': {'laplace': '.', 'supplementary': 'supplementary_sources'}}))
    # EMPTY PROJECT HOMES (2026-10-16): a selected registered home with no exported file would vanish from Git/ZIP and
    # its re-export would refuse; it travels as its generated marker (inventory.HOME_MARKER), planned and size-gated like
    # every output and declared as derived release data. Homes holding any exported file are unchanged.
    written = {row['path'] for row in copies} | set(planned)
    for project in projects:
        home = manifests[project]['registry_selection']['resolved_project_dir']
        if not any(Path(rel).is_relative_to(Path(home)) for rel in written):
            marker = (Path(home) / inventory.HOME_MARKER).as_posix()
            plan(marker, inventory.home_marker(project, home),
                 'generated project-home marker: the registered home held no exportable authored file; not authored research')
            written.add(marker)
    # THE PORTABLE INDEX (full-collection index, 2026-10-16): the resolver parses writing-portability.json for every
    # recorded-path lookup, so it holds only what resolution needs. A copied file's own current-root spelling resolves
    # through directory_aliases to exactly its exported path, and its pin is already copied_files[path].sha256 (checked
    # by the verifier); an unchanged per-file primary repeats both and is not listed (19,185 of 20,252 aliases, 6.5 MB,
    # in the 21-project collection). Every alias that says more -- another target, pinned versions, a reason, a proof
    # -- stays. The alias proofs are evidence, not resolution input: they travel exactly, pinned, beside the index.
    covered = 0
    for rel, row in candidates.items():
        key = str(root / rel)
        if aliases.get(key) == {'path': rel, 'original_sha256': row['sha256']}:
            del aliases[key]; covered += 1
    proofs_raw = encoded({'schema': 'laplace.writing-alias-proofs/1', 'source_manifest_sha256': original_manifest_hash,
                          'proofs': alias_proofs})
    plan(ALIAS_PROOFS, proofs_raw, 'every exact alias proof of this export, in derivation order')
    portable = {'schema': 'laplace.writing-portability/1', 'project': projects[0],
                'projects': projects,
                'source_manifest_sha256': original_manifest_hash, 'source_aliases': aliases,
                # the verified original roots of a published lineage stay resolvable on every hop (history store relocation)
                'directory_aliases': {str(root): '.', **{old: '.' for old in combined.get('recorded_roots') or []}},
                'directory_covered': {'files': covered, 'root': str(root),
                                      'basis': 'each copied file\'s own current-root spelling resolves through directory_aliases to '
                                               'its exported path; its pin is copied_files[path].sha256'},
                'alias_proofs': {'path': ALIAS_PROOFS, 'sha256': digest(proofs_raw), 'count': len(alias_proofs)},
                'history': 'Original selected bytes retained. Provider-native conversations are not exported; new turns start new native conversations.'}
    plan('writing-portability.json', encoded(portable))
    if policy_raw is not None:
        plan(SELECTION_POLICY, bytes(policy_raw), 'the reviewed selection policy this export applied, exact bytes')
    # THE LINK AND WORK-INPUT RELATIONSHIPS OF THIS EXPORT (portable links, 2026-10-20): the manifest's inventory,
    # judged against what this export actually holds (copies, supplementary entries, planned files); then, when
    # asked, the derived portable copy with its appendix, HTML list and PDF, every file declared and mapped.
    from laplace.manuscript import manuscript_source
    packaged_final = {row['path'] for row in copies} | set(planned)
    supplementary_paths = {rel for rel in packaged_final if any(entry.get('repository_path') == rel for _o, _r, entry in external)}
    manuscript_links, work_inventory, portable_documents = {}, {}, {}
    for project in projects:
        manifest = manifests[project]
        closure_files = manifest['selected_source_closure']['files']
        records_path = ((manifest.get('project_closure') or {}).get('authored_metadata') or {}).get('research_records', {}).get('path')
        manuscript_links[project] = links_owner.manuscript_links(root, project, closure_files, selected_projects=set(projects), packaged=packaged_final,
                                                              records_paths={project: records_path} if records_path else {})
        work_inventory[project] = links_owner.work_inputs(root, project, packaged=preselected, supplementary=supplementary_paths)
        # omissions were decided per relationship before any copy; physical inclusion is the union over every selection, so
        # each omission is reconciled against this final inventory before it is recorded anywhere (PL-C2-R1)
        work_input_omissions[project] = links_owner.reconcile_omissions(work_input_omissions.get(project, []), work_inventory[project])
        if portable_document:
            source_root = manuscript_source.resolve(project, repo_root=root).get('root')
            document = links_owner.portable_document(root, project, source_root=source_root, closure_files=closure_files,
                                                  links=manuscript_links[project], work=work_inventory[project], omissions=work_input_omissions.get(project, []))
            built = links_owner.compile_portable(document['files'], document['mapping']['derived_root'])
            mapping = document['mapping']
            mapping['compiler'] = {key: built[key] for key in ('ok', 'chain', 'log_tail', 'missing_capability', 'reason', 'errors') if key in built}
            pdf_rel = None
            if built['ok']:
                pdf_rel = PurePosixPath(mapping['derived_root']).with_suffix('.pdf').as_posix()
                # the compiled PDF's URI actions made true at the derived location: a relative link keeps its original
                # meaning (beside the original PDF) only when that meaning is a selected copy at its pin; a machine-bound
                # or uncarried one loses its link action; the record of every change travels in the mapping
                relocated = links_owner.relocate_uri_actions(
                    built['pdf'], derived_pdf=pdf_rel, original_pdf=PurePosixPath(source_root).with_suffix('.pdf').as_posix(),
                    admitted={row['path']: row['sha256'] for row in copies},
                    present=packaged_final | set(document['files']) | {pdf_rel, document['html_rel']})
                mapping['uri_actions'] = relocated['record']
                if relocated['ok']:
                    built['pdf'] = relocated['pdf']
                    mapping['pdf'] = {'path': pdf_rel, 'sha256': digest(built['pdf']), 'bytes': len(built['pdf'])}
                else:
                    built['ok'], pdf_rel = False, None
            html_raw = links_owner._html_list(project, manuscript_links[project], work_inventory[project], work_input_omissions.get(project, []), document['html_rel'], pdf_rel,
                                           mapping['derived_root'], source_root)
            for rel, raw in document['files'].items():
                plan(rel, raw, 'portable copy of the selected source closure (portable_documents mapping)')
            plan(document['html_rel'], html_raw, 'generated portable list of qualified link targets and reviewed Work inputs')
            if built['ok']:
                plan(pdf_rel, built['pdf'], 'portable PDF compiled from the derived copy by the declared build chain (portable_documents.compiler)')
            portable_documents[project] = mapping
    source_manifest = encoded(combined)
    outputs = [*copies, *derived, {'path': 'release/source-manifest.json', 'bytes': len(source_manifest)}]
    output_size = {'files': len(outputs) + 1, 'bytes_excluding_export_manifest': sum(row['bytes'] for row in outputs),
                   'per_file_limit_bytes': inventory.LARGE_FILE_BYTES,
                   'scope': 'every file this export writes; --max-total-bytes also counts release/export-manifest.json, '
                            'which records this count (the budget itself is not recorded, so it never changes the size)'}
    report = {'schema': ('laplace.writing-evaluation-export/1' if len(projects) == 1
                         else 'laplace.writing-evaluation-export/2'),
              'created': now, 'project': projects[0], 'projects': projects,
              'project_intents': selected_intents,
              'source_manifest_sha256': original_manifest_hash, 'copied_files': copies,
              'derived_files': derived, 'imported_sessions': len(imports),
              'selected_supplementary_sources': [
                  {'path': entry.get('repository_path') or ('supplementary_sources/' +
                    entry['sha256'].split(':')[-1] + original.suffix.lower()),
                   'sha256': entry['sha256'], 'reason': entry['reason'],
                   **({'recorded_path': entry['recorded_path']} if entry.get('recorded_path') else {}),
                   'selection': 'qualified-repository-path' if entry.get('repository_path')
                                else 'content-addressed-historical-reading' if entry.get('recorded_path')
                                else 'content-addressed-supplementary'}
                  for original, _raw, entry in external],
              'imported_sessions_by_project': {project: len(sessions_by_project[project])
                                               for project in projects},
              'excluded': ['source Git history', 'global/personal semantic state', 'credentials and provider transcripts',
                           'raw private author calibration', 'startup hooks', 'unrelated projects'],
              'selection_policy': ({'path': SELECTION_POLICY, 'sha256': digest(bytes(policy_raw)),
                                    'projects': sorted(inventory.selection_policy(policy_value))}
                                   if policy_raw is not None else None),
              'selected_size': {**selected_size, 'scope': 'source-input bytes only; output_size is the written total'},
              'output_size': output_size,
              'status': 'CANDIDATE_REQUIRES_CLEAN_INSTALL_ACCEPTANCE',
              'history_scope': combined['row_selection'],
              'manuscript_links': manuscript_links, 'work_inputs': work_inventory, 'work_input_omissions': work_input_omissions,
              'portable_documents': portable_documents,
              'work_input_selection': work_inputs or 'none (dispositions stated; nothing selected beyond the project closure and explicit supplementary entries)'}
    export_manifest = encoded(report)
    output_refusal([*outputs, {'path': 'release/export-manifest.json', 'bytes': len(export_manifest)}], max_total_bytes)
    destination.mkdir(parents=True)
    def put(rel, raw):
        target = inventory._safe(destination, rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    for rel, row in sorted(candidates.items()):
        raw = inventory._safe(root, rel).read_bytes()
        if digest(raw) != row['sha256'] or len(raw) != row['bytes']:
            raise ValueError("candidate changed during export: " + rel)
        put(rel, raw)
    for rel, raw in planned.items():
        put(rel, raw)
    put('release/source-manifest.json', source_manifest)
    put('release/export-manifest.json', export_manifest)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', required=True, type=Path)
    parser.add_argument('--destination', required=True, type=Path)
    parser.add_argument('--project', action='append', required=True)
    parser.add_argument('--project-intent', action='append', metavar='PROJECT=INTENT',
                        help='Explicit selected-project closure intent (default: completed-manuscript)')
    parser.add_argument('--supplementary-sources', type=Path)
    parser.add_argument('--selection-policy', type=Path,
                        help='Reviewed per-file selection (' + inventory.SELECTION_SCHEMA + '); a re-export may pass '
                             'the export\'s own ' + SELECTION_POLICY)
    parser.add_argument('--max-total-bytes', type=int, help='Refuse before creating the destination when the complete planned output (every written file, generated manifests included) is larger')
    parser.add_argument('--work-inputs', choices=['current'], help='Select the current inputs of reviewed Work obligations outside the manuscript closure, through the pinned supplementary route at their exact repository paths')
    parser.add_argument('--portable-document', action='store_true', help='Stage a derived portable copy of each selected manuscript (appendix of qualified link targets, HTML list, PDF through the declared build chain when it can run)')
    args = parser.parse_args(argv)
    sources = json.loads(args.supplementary_sources.read_text(encoding="utf-8")) if args.supplementary_sources else []
    policy = args.selection_policy.read_bytes() if args.selection_policy else None
    result = export_projects(args.repo_root, args.destination, args.project, sources, intents=args.project_intent,
                             selection=policy, max_total_bytes=args.max_total_bytes, work_inputs=args.work_inputs,
                             portable_document=args.portable_document)
    print(json.dumps({'destination': str(args.destination), 'status': result['status'],
                      'files': len(result['copied_files']), 'imported_sessions': result['imported_sessions']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
