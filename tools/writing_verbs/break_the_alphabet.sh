#!/bin/bash
# DELIBERATELY break the alphabet, three ways, and show the proofs fail; then restore and
# show them pass again.  The judge of this packet is told to do exactly this, so it is done
# here first and the transcript deposited.
#
#   1. a pair the verb door can no longer reach: one route's door becomes "shim", so
#      `bind reference@evidence` is declared by the mapping and routable by nothing.
#   2. a route for a pair the grammar does not declare: `run prose@paragraph`.
#   3. the advisor's alphabet frozen back to the grammar's declared pairs instead of the
#      dispatch table, which is the state this synthesis moved away from -- it must FAIL
#      once the dispatch and the grammar differ, which is the whole point of reading the
#      table that acts.
set -u
W=/home/phujck/VScodeProjects/laplace/.claude/worktrees/wf_2b127eb4-edb-27
T="tests/test_routing.py::test_the_route_alphabet_is_the_dispatch_table_not_a_list tests/test_routing.py::test_the_advisor_cannot_suggest_a_pair_the_verb_door_cannot_route"
cd "$W" || exit 3

echo "### 0. CLEAN: the two alphabet proofs on the merged tree"
scripts/laplace-python -m pytest -q $T --basetemp=/tmp/pytest-break-0 -p no:cacheprovider 2>&1 | tail -3

echo
echo "### 1. BREAK: literature_bind's route becomes door='shim' (a shim-only pair)"
scripts/laplace-python - <<'EOF'
import pathlib
p = pathlib.Path("src/laplace/native/verbs.py")
s = p.read_text()
old = "    Route(verb='bind', concept='reference@evidence', operation='literature_bind',"
assert old in s, "the route moved; re-aim this break"
s = s.replace(old, old + "\n          door='shim', because='DELIBERATE BREAK',", 1)
p.write_text(s)
print("  patched: door='shim' on bind reference@evidence")
EOF
scripts/laplace-python -m pytest -q $T --basetemp=/tmp/pytest-break-1 -p no:cacheprovider 2>&1 | tail -12
git checkout -- src/laplace/native/verbs.py

echo
echo "### 2. BREAK: a route for a pair the grammar does not declare (run prose@paragraph)"
scripts/laplace-python - <<'EOF'
import pathlib
p = pathlib.Path("src/laplace/native/verbs.py")
s = p.read_text()
old = "ROUTES: tuple[Route, ...] = (\n"
assert old in s
s = s.replace(old, old + "    Route(verb='run', concept='prose@paragraph', "
                        "operation='propose_revision',\n"
                        "          owner='DELIBERATE BREAK', "
                        "site='src/laplace/writing_tools.py:1'),\n", 1)
p.write_text(s)
print("  patched: one extra Route for an undeclared pair")
EOF
scripts/laplace-python -m pytest -q $T --basetemp=/tmp/pytest-break-2 -p no:cacheprovider 2>&1 | tail -12
git checkout -- src/laplace/native/verbs.py

echo
echo "### 3. BREAK: the alphabet goes back to grammar.VERB_CONCEPTS while the table differs"
scripts/laplace-python - <<'EOF'
import pathlib
p = pathlib.Path("src/laplace/native/routing.py")
s = p.read_text()
old = "    return tuple(sorted(dispatch_pairs() | set(grammar.ADDED_PAIRS)))"
assert old in s
s = s.replace(old, "    return tuple(sorted(set(grammar.VERB_CONCEPTS) | "
                   "set(grammar.ADDED_PAIRS)))   # DELIBERATE BREAK")
p.write_text(s)
v = pathlib.Path("src/laplace/native/verbs.py")
t = v.read_text()
old = "    Route(verb='bind', concept='reference@evidence', operation='literature_bind',"
assert old in t
t = t.replace(old, old + "\n          door='shim', because='DELIBERATE BREAK',", 1)
v.write_text(t)
print("  patched: alphabet from the grammar, and one pair the door cannot reach")
EOF
scripts/laplace-python -m pytest -q $T --basetemp=/tmp/pytest-break-3 -p no:cacheprovider 2>&1 | tail -14
git checkout -- src/laplace/native/routing.py src/laplace/native/verbs.py

echo
echo "### 4. RESTORED: the two proofs pass again, and the tree is clean"
scripts/laplace-python -m pytest -q $T --basetemp=/tmp/pytest-break-4 -p no:cacheprovider 2>&1 | tail -3
git status --porcelain -- src tests tools
echo "git status over src tests tools printed above (empty means clean)"
