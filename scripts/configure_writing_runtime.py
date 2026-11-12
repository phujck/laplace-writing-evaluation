#!/usr/bin/env python3
"""Explicitly bind this checkout's managed commands to a chosen local Python.

Installs nothing and never reads or copies the author's runtime declaration.
Foreground browser reading does not require this managed-command setup.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--python', required=True, type=Path, help='explicit existing interpreter, for example .venv/bin/python')
    parser.add_argument('--replace', action='store_true', help='replace an existing local declaration')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    target = root / 'runtime_profiles.toml'
    if target.exists() and not args.replace:
        parser.error('runtime_profiles.toml exists; inspect it before using --replace')
    python = args.python.absolute() if args.python.is_absolute() else (root / args.python).absolute()
    if not python.is_file() or not os.access(python, os.X_OK): parser.error('selected Python is not executable')
    observed = json.loads(subprocess.check_output([str(python), '-I', '-c',
        'import json,sys,platform;print(json.dumps({"version":platform.python_version(),"major_minor":list(sys.version_info[:2])}))'], text=True))
    if observed['major_minor'] < [3, 11]: parser.error('managed runtime setup requires Python 3.11+ (3.12 is the evaluation profile)')
    selected = python.relative_to(root).as_posix() if python.is_relative_to(root) else str(python)
    content = ('schema = "laplace-runtime-profiles/1"\nproject_python = ">=3.11"\n\n[lifecycle]\n'
               'python = ' + json.dumps(selected) + '\nexpected_python = ' + json.dumps(observed['version']) + '\n'
               'launcher = "scripts/laplace-python"\noverride_env = "LAPLACE_PYTHON"\n'
               'source_roots = ["src"]\nuser_site = false\nvirtual_environment = "explicit selection only"\n'
               'install_policy = "explicit setup only; never at startup"\n\n'
               '[browser_server]\nentry = "python -m laplace.web.writing_server --root ."\n'
               'state_policy = "explicit local checkout; no author-home fallback"\n')
    template = (Path(__file__).resolve().parents[1] / 'profiles/runtime-portable.toml').read_text(encoding='utf-8')
    content += '\n[publication]' + template.split('[publication]', 1)[1]
    target.write_text(content, encoding='utf-8')
    print(json.dumps({'status': 'CONFIGURED', 'path': str(target), 'selected_python': selected,
                      'version': observed['version'], 'packages_installed': False,
                      'scope': 'Local runtime selection; not a capability, GPU or provider qualification.'}))
    return 0


if __name__ == '__main__': raise SystemExit(main())
