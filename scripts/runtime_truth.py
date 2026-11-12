#!/usr/bin/env python3
"""Passive runtime and source projection; no model, GPU, state load or installation."""
from __future__ import annotations

import hashlib
import importlib.metadata as metadata
import importlib.util
import json
import runpy
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def probe() -> dict:
    policy = runpy.run_path(str(ROOT / 'src/laplace/core/runtime.py'))
    problems = []
    try:
        selected = policy['lifecycle_python'](ROOT)
        identity = policy['require_runtime'](ROOT)
    except RuntimeError as exc:
        selected = None
        identity = policy['receipt']()
        problems.append(str(exc))
    sources = {}
    for name, relative in (('laplace', 'src/laplace'), ('atlas', 'src/atlas')):
        spec = importlib.util.find_spec(name)
        origin = str(Path(spec.origin).resolve()) if spec and spec.origin else None
        sources[name] = origin
        if origin is None or not Path(origin).is_relative_to(ROOT / relative):
            problems.append(f'{name} source does not belong to this checkout: {origin}')
    packages = {}
    for name in ('dulwich', 'numpy', 'pydantic', 'PyYAML', 'filelock', 'psutil'):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
            problems.append(f'missing core package {name}')
    return {
        'probe': 'runtime-truth/3',
        'source_root': str(ROOT),
        'launcher': str(ROOT / 'scripts/laplace-python'),
        'selected_python': selected,
        'runtime': identity,
        'sources': sources,
        'core_packages': packages,
        'profile_sha256': 'sha256:' + hashlib.sha256((ROOT / 'runtime_profiles.toml').read_bytes()).hexdigest(),
        'bare_python3': shutil.which('python3'),
        'device_execution': 'not-run; package presence is not GPU proof',
        'state_access': 'not-run',
        'verdict': 'RUNTIME-BOUND' if not problems else 'RUNTIME-MISBOUND',
        'problems': problems,
    }


def main() -> int:
    truth = probe()
    if '--json' in sys.argv:
        print(json.dumps(truth, indent=2, sort_keys=True))
    else:
        suffix = '; ' + '; '.join(truth['problems']) if truth['problems'] else ''
        print(f"[runtime-truth] {truth['verdict']}; use {truth['launcher']}; "
              f"source {truth['source_root']}; device execution not checked{suffix}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
