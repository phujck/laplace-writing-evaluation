#!/usr/bin/env python3
"""Inspect a Writing export READ-ONLY when its kernel cannot start (Work5 recovery, 2026-10-20; read closure W5-R2-R1).

Standard library only: this never imports laplace or atlas, so it runs when the candidate's packages are broken, absent
or refuse to import. It writes nothing under the inspected root, not even bytecode (bytecode writing is disabled before
the one helper is loaded). It reports what the export declares (manifests, registry, repository configuration, package
declarations), what its bytes are (present / changed / missing / refused / unreadable / malformed), what its journal and
Work ledger hold (row kinds, sessions, import boundaries, native bindings, Work ids) and a finite recovery route.

    python /trusted/inspect_writing_export.py --root /path/to/candidate \\
        --accepted-manifest-sha256 sha256:... [--accepted-manifest /outside/accepted/export-manifest.json] \\
        [--output /path/outside/root/report.json]

ONE VERDICT consumes every requested check. Exit 0: the declared bytes are consistent AND every requested anchor check
succeeded (status ACCEPTED_IDENTITY_AND_BYTES when an anchor was given, DECLARED_BYTES_CONSISTENT_UNANCHORED when none
was). Exit 2: a discrepancy in any requested or declared condition (drift, source-manifest identity, an unreadable
declared or fixed file, a missing, unreadable, malformed, conflicting or inside-candidate anchor, a checker running inside
the candidate while an anchor was requested, a checker file whose identity could not be read, missing workspace inputs,
refused coordinates, unknown journal kinds), or an unsupported option. Exit 3: the export manifest is absent, unreadable,
malformed or of an unsupported schema. A requested anchor that fails never degrades to the unanchored outcome.

ONE READ CONTRACT. Admission (no climbing, no symlink component, inside the root, regular file) happens before any open;
the open, the streaming hash, the size and the JSON parse then return typed finite problems through the shared byte layer,
and every such problem reaches the verdict. Nothing is read outside the root except the explicitly supplied accepted copy.

NOT HERE. Container packages have their own tool (scripts/writing_container_package.py); this workspace inspector does not
compose with it. `--package` is refused as unsupported without opening anything.

TRUST BOUNDARY. The manifest inside the candidate is the candidate's own claim; "declared bytes consistent" is not
acceptance. The accepted identity comes from outside the candidate: the accepted export manifest's sha256 or an accepted
copy of it. And the CHECKER must come from outside too: this file and writing_export_bytes.py taken from the accepted
source commit, whose sha256 you hold and compare before running (docs/writing-recovery-and-currentness.md gives the
recipe). The report hashes the two files that actually ran (`checker`) so you can compare; that is a coordinate for YOUR
comparison, not a proof the program makes about itself. Run from inside the candidate, the same program can only describe
the candidate's declared consistency: an anchor requested from a candidate-local checker is refused.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True   # before the helper load: the inspection leaves the candidate tree byte for byte as it found it

import argparse  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('writing_export_bytes', HERE / 'writing_export_bytes.py')
bytes_layer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bytes_layer)

SCHEMA = 'laplace.writing-export-inspection/3'
CHECKER_FILES = ('inspect_writing_export.py', 'writing_export_bytes.py')
STATUS_EXIT = {'ACCEPTED_IDENTITY_AND_BYTES': 0, 'DECLARED_BYTES_CONSISTENT_UNANCHORED': 0, 'DISCREPANCY': 2, 'UNSUPPORTED_OPTION': 2, 'MALFORMED': 3}


def _self_pins(root_resolved: Path) -> dict:
    """The checker that actually ran, hashed through the shared read contract for the operator's comparison with the pinned
    accepted hashes; an identity that cannot be read is a problem the verdict consumes."""
    rows, problems = {}, []
    for name in CHECKER_FILES:
        path = HERE / name
        identity, problem = bytes_layer.file_identity(path)
        if problem:
            rows[name] = {'path': str(path), 'problem': problem}
            problems.append('%s: %s' % (name, problem))
        else:
            rows[name] = {'path': str(path), 'sha256': identity['sha256'], 'bytes': identity['bytes']}
    inside = HERE.is_relative_to(root_resolved)
    return {'files': rows, 'problems': problems, 'location': 'inside-candidate' if inside else 'outside-candidate',
            'statement': ('this checker runs from inside the inspected candidate: it can describe the candidate\'s declared consistency only; '
                          'an accepted identity needs the externally pinned checker' if inside else
                          'compare these hashes with the accepted checker pins you hold before trusting the verdict; the program cannot certify itself')}


def recovery_routes(root: Path, inspection: dict) -> list[dict]:
    """Finite, named next steps; none of them is performed here."""
    routes = [
        {'step': 'full-verify', 'needs': 'a working kernel (the installed laplace package)',
         'command': 'python scripts/verify_writing_evaluation.py --root %s' % root,
         'says': 'the application-semantic verification: registry/source closure, body custody, document links'},
        {'step': 'start-foreground-server', 'needs': 'a working kernel; the two workspace inputs registry_projects.json and profiles/writing_sources.json',
         'command': 'python -m laplace.web.writing_server --root %s --host 127.0.0.1 --port 8771' % root,
         'says': 'the existing app on this workspace; imported sessions resume detached (a new provider conversation)'},
        {'step': 'reimport-from-accepted-export', 'needs': 'the accepted export (its manifest identity is the external anchor) and a working kernel',
         'command': 'python scripts/export_writing_evaluation.py --repo-root <accepted source> --destination <fresh workspace> --project <name>',
         'says': 'rebuilds a workspace from selected original rows and bodies; session history keeps its original ids behind an explicit import boundary; native bindings are detached'},
    ]
    files = inspection.get('files') or {}
    if files.get('changed_count') or files.get('missing_count') or files.get('refused_count'):
        routes.insert(0, {'step': 'restore-declared-bytes', 'needs': 'the accepted export or its archive',
                          'command': '(copy the listed changed/missing/refused files from the accepted export; compare with this report again)',
                          'says': 'the declared bytes differ from the manifest; nothing here repairs them'})
    return routes


def inspect(root: Path, *, accepted_manifest_sha256=None, accepted_manifest_path=None) -> dict:
    try:
        fence = bytes_layer.Fence(root)
    except ValueError as exc:
        return {'schema': SCHEMA, 'root': str(root), 'status': 'MALFORMED', 'exit_status': 3, 'malformed': [{'path': str(root), 'problem': str(exc)}], 'discrepancies': [], 'writes': 'none'}
    manifest = bytes_layer.declared_manifest(fence)
    report = manifest.get('report')
    files = bytes_layer.declared_files(fence, report) if report else None
    inputs = bytes_layer.workspace_inputs(fence)
    repositories, repository_failures = bytes_layer.repository_scope(fence.resolved, fence)
    inspection = {
        'schema': SCHEMA, 'root': str(fence.resolved), 'kernel': 'not consulted: this inspector imports neither laplace nor atlas',
        'checker': _self_pins(fence.resolved),
        'manifest': {key: value for key, value in manifest.items() if key != 'report'},
        'files': files, 'workspace_inputs': inputs, 'repositories': repositories, 'repository_failures': repository_failures,
        'journal': bytes_layer.journal_summary(fence), 'work': bytes_layer.work_summary(fence),
        'trust': bytes_layer.trust(fence, manifest, accepted_manifest_sha256=accepted_manifest_sha256, accepted_manifest_path=accepted_manifest_path),
    }
    inspection['refused'] = fence.refused[:bytes_layer.LIST_LIMIT]
    inspection['refused_count'] = len(fence.refused)
    verdict(inspection, anchor_requested=inspection['trust']['requested'])
    inspection['recovery'] = recovery_routes(fence.resolved, inspection)
    inspection['writes'] = 'none under the root (bytecode writing disabled before the helper load)'
    return inspection


def verdict(inspection: dict, *, anchor_requested: bool) -> None:
    """THE ONE FINAL-STATUS POLICY: every requested and declared condition, admission refusals and read failures included,
    decides status and exit together."""
    malformed, discrepancies = [], []
    manifest = inspection['manifest']
    if manifest.get('problem'):
        malformed.append({'path': bytes_layer.EXPORT_MANIFEST, 'problem': manifest['problem']})
    for rel, entry in inspection['workspace_inputs'].items():
        if entry.get('problem'):
            malformed.append({'path': rel, 'problem': entry['problem']})
    journal, work = inspection['journal'], inspection['work']
    for ledger in (journal, work):
        if ledger.get('problem') and ledger['problem'] != 'missing':
            malformed.append({'path': ledger['path'], 'problem': ledger['problem']})
        if ledger.get('malformed_lines'):
            malformed.append({'path': ledger['path'], 'problem': '%d malformed lines' % ledger['malformed_lines']})
        if ledger.get('malformed_rows_count'):
            malformed.append({'path': ledger['path'], 'problem': '%d rows with malformed identities' % ledger['malformed_rows_count']})
    files = inspection.get('files')
    if files is not None:
        if not manifest['source_manifest']['identity_match']:
            discrepancies.append('source manifest identity does not match the export manifest' + (': ' + manifest['source_manifest']['problem'] if manifest['source_manifest'].get('problem') else ''))
        if not files['consistent']:
            discrepancies.append('declared files changed, missing, refused, unreadable or of another size')
    trust = inspection['trust']
    if anchor_requested:
        for problem in trust['problems']:
            discrepancies.append('anchor: ' + problem)
        if not trust['problems'] and trust['accepted_identity_match'] is False:
            discrepancies.append('the export manifest is not the accepted one (external anchor mismatch)')
        if inspection['checker']['location'] == 'inside-candidate':
            discrepancies.append('anchor: the checker runs from inside the candidate; an accepted identity is established only by the externally pinned checker')
    for problem in inspection['checker']['problems']:
        discrepancies.append('checker identity could not be read: ' + problem)
    for rel in (bytes_layer.REGISTRY, bytes_layer.REPOSITORIES):
        if not inspection['workspace_inputs'].get(rel, {}).get('present'):
            discrepancies.append('workspace input missing: ' + rel)
    for failure in inspection['repository_failures']:
        discrepancies.append('repository configuration: ' + failure['reason'])
    if journal.get('unsupported_kinds'):
        discrepancies.append('journal rows of kinds this inspector does not know: ' + ', '.join(sorted(journal['unsupported_kinds'])))
    if inspection['refused_count']:
        discrepancies.append('%d coordinates refused at the admission boundary (see refused)' % inspection['refused_count'])
    inspection['malformed'] = malformed
    inspection['discrepancies'] = discrepancies
    if manifest.get('problem') or files is None:
        status = 'MALFORMED'
    elif malformed or discrepancies:
        status = 'DISCREPANCY'
    elif anchor_requested:
        status = 'ACCEPTED_IDENTITY_AND_BYTES' if trust['accepted_identity_match'] is True else 'DISCREPANCY'
    else:
        status = 'DECLARED_BYTES_CONSISTENT_UNANCHORED'
    inspection['status'] = status
    inspection['exit_status'] = STATUS_EXIT[status]
    inspection['partial'] = status not in ('ACCEPTED_IDENTITY_AND_BYTES', 'DECLARED_BYTES_CONSISTENT_UNANCHORED')


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(arg == '--package' or arg.startswith('--package=') for arg in argv):
        # Root's simplification: container packages keep their own tool; this inspector does not compose with it and opens nothing for it
        print(json.dumps({'schema': SCHEMA, 'status': 'UNSUPPORTED_OPTION', 'exit_status': STATUS_EXIT['UNSUPPORTED_OPTION'],
                          'problem': '--package is not supported by this workspace inspector; verify a container package with scripts/writing_container_package.py',
                          'writes': 'none'}, indent=1))
        return STATUS_EXIT['UNSUPPORTED_OPTION']
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--accepted-manifest-sha256', help='the accepted export manifest identity, supplied from outside the candidate')
    parser.add_argument('--accepted-manifest', type=Path, help='an accepted copy of release/export-manifest.json, supplied from outside the candidate')
    parser.add_argument('--output', type=Path, help='write the report here (must be outside --root); the report always goes to stdout')
    args = parser.parse_args(argv)
    root = args.root
    try:
        resolved = root.resolve(strict=True)
    except OSError:
        print(json.dumps({'schema': SCHEMA, 'root': str(root), 'status': 'MALFORMED', 'exit_status': 3, 'malformed': [{'path': str(root), 'problem': 'not readable'}]}, indent=1))
        return 3
    if args.output is not None and args.output.resolve().is_relative_to(resolved):
        parser.error('--output must be outside --root: the inspection writes nothing under the inspected export')
    inspection = inspect(root, accepted_manifest_sha256=args.accepted_manifest_sha256, accepted_manifest_path=args.accepted_manifest)
    text = json.dumps(inspection, indent=1, sort_keys=True, ensure_ascii=False)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)
    return STATUS_EXIT.get(inspection['status'], 3)


if __name__ == '__main__':
    raise SystemExit(main())
