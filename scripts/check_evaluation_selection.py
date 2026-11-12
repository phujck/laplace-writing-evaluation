#!/usr/bin/env python3
"""Check the curated distribution's recorded bytes without importing the application."""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--records', action='store_true', help='also resolve current scientific declarations through installed/base application owners')
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / 'release/selection-manifest.json').read_text())
    rows = list(manifest['files']) + [dict(row, path=path) for path, row in manifest['derived_files'].items()]
    errors = []
    for row in rows:
        relative = Path(row['path'])
        path = root / relative
        if relative.is_absolute() or '..' in relative.parts or not path.resolve().is_relative_to(root):
            errors.append({'path': str(relative), 'error': 'unsafe path'})
            continue
        if path.is_symlink() or not path.is_file():
            errors.append({'path': str(relative), 'error': 'missing file or symlink'})
            continue
        raw = path.read_bytes()
        if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256'].removeprefix('sha256:'):
            errors.append({'path': str(relative), 'error': 'recorded bytes differ'})
    sys.path.insert(0, str(root / 'scripts'))
    import writing_eval_manifest as inventory
    selected = {row['path'] for row in rows}
    application = inventory.application_closure(root, tests=True)
    for row in application['files']:
        if row['path'] not in selected: errors.append({'path': row['path'], 'error': 'application/resource omitted from selection'})
    if args.records:
        for paper in manifest.get('papers', []):
            closure = inventory.retained_record_closure(root, paper['project'], restricted=manifest.get('private_record_input_exclusions', []))
            errors.extend({'path': row['path'], 'error': 'required scientific input missing'} for row in closure['missing_required'])
            errors.extend({'path': row['path'], 'error': 'scientific input omitted from selection'} for row in closure['files'] if row['path'] not in selected)
    print(json.dumps({'status': 'PASS' if not errors else 'FAIL', 'checked_files': len(rows), 'errors': errors,
                      'application_files': len(application['files']), 'records_checked': args.records,
                      'scope': 'Selected bytes and complete declared application/resource families; optional scientific owner closure. Not rights or scientific validation.'}, indent=2))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
