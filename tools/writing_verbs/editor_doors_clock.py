"""Is the `concept-network` token of a freshly created project clock-dependent?

The six ARRIVAL rows that differ between the base tree and this one differ in ONE value: the
`concept-network` token of `probe-editor-arrival-replay`, the project the replay itself creates.
If that token is a digest over a value carrying a creation timestamp, then two runs a second
apart cannot agree and the difference says nothing about either tree.  Measured, not argued:
the same tree creates the project twice, a second apart, and the two tokens are compared.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

work = pathlib.Path("/tmp/claude-1000/consol-editor-doors/clock")
template = pathlib.Path("/tmp/claude-1000/consol-measure/browser/template")
if not template.is_dir():
    raise SystemExit("no fixture template at %s; run harness2/_measure.py once" % template)

CHILD = """
import json, pathlib, sys
sandbox = pathlib.Path(sys.argv[1])
from laplace.projects import library as writing_projects; from laplace.core import grammar as g
code, body = writing_projects.create(
    {"name": "probe-clock-check", "title": "Probe clock check", "kind": "paper"}, sandbox)
assert code < 400, body
token = g.identity(g.Home("concept-network", "probe-clock-check"),
                   project="probe-clock-check", root=sandbox)
print(json.dumps({"code": code, "token": str(token)}))
"""

child = work / "child.py"
out = {}
for label in ("first", "second"):
    sandbox = work / label
    if sandbox.exists():
        shutil.rmtree(sandbox)
    sandbox.parent.mkdir(parents=True, exist_ok=True)
    child.write_text(CHILD, encoding="utf-8")
    shutil.copytree(template, sandbox, symlinks=True)
    env = dict(os.environ, LAPLACE_REPO_ROOT=str(sandbox),
               LAPLACE_STATE_ROOT=str(work / (label + "-state")))
    got = subprocess.run([sys.argv[1] if len(sys.argv) > 1 else "scripts/laplace-python",
                          str(child), str(sandbox)],
                         capture_output=True, text=True, env=env)
    if got.returncode != 0:
        raise SystemExit(got.stderr[-2000:])
    out[label] = json.loads(got.stdout.strip().splitlines()[-1])["token"]
    if label == "first":
        time.sleep(1.2)

print(json.dumps({"tokens": out, "equal": out["first"] == out["second"],
                  "verdict": ("the token is CLOCK-DEPENDENT: two creations of the same project "
                              "on ONE tree disagree, so this value cannot be a signal about a "
                              "tree" if out["first"] != out["second"] else
                              "the token is NOT clock-dependent on this path")}, indent=1))
