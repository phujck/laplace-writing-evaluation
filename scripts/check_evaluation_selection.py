#!/usr/bin/env python3
"""Check the curated distribution's recorded bytes without importing the application."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
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
    print(json.dumps({'status': 'PASS' if not errors else 'FAIL', 'checked_files': len(rows), 'errors': errors,
                      'scope': 'Recorded byte identity only; not privacy, rights, completeness or scientific validation.'}, indent=2))
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
