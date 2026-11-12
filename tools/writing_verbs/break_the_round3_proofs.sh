#!/bin/bash
# DELIBERATELY break the two proofs round 3 asked this lane to strengthen, and show them
# fail; then restore and show them pass again.  Same shape as break_the_alphabet.sh, which
# is the only reason a reader should believe either check bites.
#
#   1. THE CITATION TABLE. Move `ROUTES` one line.  routing.py cites the dispatch table by
#      line, and the old test's catch-all loop asserted only that the number was in range,
#      so it passed on a number six lines off.  The table in tests/test_routing.py asserts
#      the TEXT of the line, so moving the table must fail it.
#   2. THE IMPORT CLOSURE. Plant a write at `routing.py` MODULE LEVEL.  The original probe
#      installs its hook after `from laplace.native import routing`, so it cannot see this write
#      and reports zero violations; the new import probe installs the hook first and must
#      catch it.  Both numbers are printed side by side, because the contrast IS the fix.
set -u
W=/home/phujck/VScodeProjects/laplace/.claude/worktrees/wf_2b127eb4-edb-27
CIT="tests/test_routing.py::test_the_cited_lines_are_the_lines_they_claim"
NW="tests/test_routing.py::test_the_advisor_cannot_reach_a_write"
cd "$W" || exit 3

echo "### 0. CLEAN: the two proofs on the merged tree"
scripts/laplace-python -m pytest -q $CIT $NW --basetemp=/tmp/pytest-r3-0 -p no:cacheprovider 2>&1 | tail -3
echo "    grep -n '^ROUTES' src/laplace/native/verbs.py -> $(grep -n '^ROUTES' src/laplace/native/verbs.py)"
echo "    the citation in routing.py            -> $(grep -n 'writing_verbs.py:1' src/laplace/native/routing.py | head -1 | cut -c1-96)"

echo
echo "### 1. BREAK: ROUTES moves one line down (a blank line above it)"
scripts/laplace-python - <<'EOF'
import pathlib
p = pathlib.Path("src/laplace/native/verbs.py")
s = p.read_text()
old = "ROUTES: tuple[Route, ...] = (\n"
assert old in s, "ROUTES moved; re-aim this break"
s = s.replace(old, "\n" + old, 1)
p.write_text(s)
print("  patched: ROUTES is now at line %d"
      % next(i for i, line in enumerate(s.split("\n"), 1) if line.startswith("ROUTES")))
EOF
scripts/laplace-python -m pytest -q $CIT --basetemp=/tmp/pytest-r3-1 -p no:cacheprovider 2>&1 | tail -8
echo "  --- and the ALPHABET proof is untouched by a line move, as it should be:"
scripts/laplace-python -m pytest -q tests/test_routing.py::test_the_route_alphabet_is_the_dispatch_table_not_a_list \
    --basetemp=/tmp/pytest-r3-1b -p no:cacheprovider 2>&1 | tail -2
git checkout -- src/laplace/native/verbs.py

echo
echo "### 2. BREAK: a write at routing.py MODULE LEVEL (the hole round 3 found)"
PLANTED=/tmp/claude-1000/r3-planted-$$.txt
rm -f "$PLANTED"
scripts/laplace-python - "$PLANTED" <<'EOF'
import pathlib, sys
planted = sys.argv[1]
p = pathlib.Path("src/laplace/native/routing.py")
s = p.read_text()
old = "from laplace.native import verbs as writing_verbs"
assert old in s, "the module-level table import moved; re-aim this break"
s = s.replace(old, old + "\nimport os as _os_break\nopen(%r, 'a').write(str(_os_break.getpid()) + chr(10))   # DELIBERATE BREAK"
              % planted, 1)
p.write_text(s)
print("  patched: routing.py writes to %s at import" % planted)
EOF
echo "  --- the two probes, side by side, on the planted tree:"
scripts/laplace-python - "$PLANTED" <<'EOF'
import importlib.util, json, os, pathlib, subprocess, sys, tempfile
spec = importlib.util.spec_from_file_location("t_routing", "tests/test_routing.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
labels = mod._labels_file(pathlib.Path(tempfile.mkdtemp()))
for name, text, env in (
        ("_AUDIT_PROBE        (hook AFTER the import, the round-2 shape)",
         mod._AUDIT_PROBE, dict(os.environ)),
        ("_AUDIT_IMPORT_PROBE (hook BEFORE the import, the round-3 fix)",
         mod._AUDIT_IMPORT_PROBE, dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))):
    script = pathlib.Path(tempfile.mkdtemp()) / "probe.py"
    script.write_text(text % {"src": "src", "labels": str(labels)})
    done = subprocess.run(["scripts/laplace-python", str(script)], capture_output=True,
                          text=True, check=False, env=env)
    if done.returncode != 0:
        print("  %s -> probe exited %d" % (name, done.returncode)); continue
    out = json.loads(done.stdout.strip().splitlines()[-1])
    print("  %s -> n_violations %d, n_import_violations %s"
          % (name, out["n_violations"], out.get("n_import_violations", "(not measured)")))
    if out.get("import_violations"):
        print("      caught: %r" % (out["import_violations"][0],))
planted = pathlib.Path(sys.argv[1])
print("  the planted file exists: %s, %d pid line(s) in it"
      % (planted.is_file(), len(planted.read_text().splitlines()) if planted.is_file() else 0))
EOF
echo "  --- and the test's verdict on the planted tree:"
scripts/laplace-python -m pytest -q $NW --basetemp=/tmp/pytest-r3-2 -p no:cacheprovider 2>&1 | tail -6
git checkout -- src/laplace/native/routing.py
rm -f "$PLANTED"

echo
echo "### 3. RESTORED: both proofs pass again, and the tree is clean"
scripts/laplace-python -m pytest -q $CIT $NW --basetemp=/tmp/pytest-r3-3 -p no:cacheprovider 2>&1 | tail -3
git status --porcelain -- src tests tools
echo "git status over src tests tools printed above (empty means clean)"
