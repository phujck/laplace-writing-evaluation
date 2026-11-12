"""conftest.py - the clean-interpreter probe behind the two import-reach checks.

``test_seal.py::test_import_pulls_no_laplace`` and ``test_encoders.py::test_unit_suite_loads_no_model``
both ask what importing an atlas module drags in with it. Read against the running test process's
``sys.modules``, that question has no answer: the root ``pyproject.toml`` sets
``testpaths = ["tests", "atlas/tests"]``, so both halves of the repository share one interpreter,
and by the time the atlas half executes the laplace half has already imported ``laplace`` and
``fastembed`` for its own reasons. The ambient reading describes the process, not the import.
Run ``atlas/tests`` alone and it passes; run the suite pyproject actually declares and it fails,
which is the shape of a broken instrument rather than a broken seal.

``clean_import_probe`` moves the reading into a fresh interpreter that imports the named modules
and nothing else. Two properties of the child make its verdict mean what the seal says:

* its path carries ``src``, where both ``atlas`` and ``laplace`` live, so ``laplace`` is importable there. An empty
  result therefore says atlas declined the import, not that it lacked the option.
* its working directory is an empty temporary one, so the child's import machinery is not
  reading from the repository root. (A root ``atlas/`` without ``__init__.py`` would only be
  recorded as a namespace *portion* and the scan would continue to ``src/atlas`` on the
  path anyway — the empty cwd removes the ambiguity rather than averting a wrong resolution.)

A module-scope import of something absent from the environment raises inside the child, which
surfaces as a nonzero exit rather than a leak report - so the checks still bite when an optional
dependency such as ``fastembed`` is not installed.

One interpreter per test, not one per suite: each parametrized module keeps its own test id and
its own assertion.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

#: one source home since core consolidation R2: src/atlas beside src/laplace
ATLAS_SRC = Path(__file__).resolve().parents[2] / "src"
LAPLACE_SRC = Path(__file__).resolve().parents[2] / "src"

# Runs in the child. Reads one JSON argument, imports what it names, and prints one JSON line.
_PROBE = r'''
import importlib
import importlib.util
import json
import sys

spec = json.loads(sys.argv[1])
for name in spec["import"]:
    importlib.import_module(name)

report = {
    "leaked_laplace": sorted(
        m for m in sys.modules if m == "laplace" or m.startswith("laplace.")
    ),
    "loaded": {name: (name in sys.modules) for name in spec["watch"]},
}
# After the snapshot above: find_spec imports parent packages, so it must not colour the reading
# it is there to qualify.
report["importable"] = {
    name: (importlib.util.find_spec(name) is not None) for name in spec["witness"]
}
print(json.dumps(report))
'''


@pytest.fixture(scope="session")
def clean_import_probe():
    """Import modules in a fresh interpreter and report what came with them.

    ``imports`` names the modules to import, ``watch`` the modules to report presence for, and
    ``witness`` the modules to report importability for (used to show a check is not vacuous).
    Returns the child's report: ``leaked_laplace``, ``loaded``, ``importable``.
    """

    def probe(*, imports, watch=(), witness=()):
        env = dict(os.environ)
        # Set rather than extend: an inherited PYTHONPATH could put a laplace-importing
        # sitecustomize or conftest in front of the child.
        env["PYTHONPATH"] = os.pathsep.join([str(ATLAS_SRC), str(LAPLACE_SRC)])
        env.pop("PYTHONSTARTUP", None)
        spec = json.dumps({"import": list(imports), "watch": list(watch),
                           "witness": list(witness)})
        with tempfile.TemporaryDirectory() as neutral_cwd:
            proc = subprocess.run(
                [sys.executable, "-c", _PROBE, spec],
                capture_output=True, text=True, env=env, cwd=neutral_cwd, timeout=120,
            )
        assert proc.returncode == 0, (
            f"import probe failed for {list(imports)} (exit {proc.returncode}).\n"
            f"An import raising in the child is itself a finding - a module-scope import of "
            f"something the environment lacks lands here.\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
        return json.loads(proc.stdout)

    return probe
