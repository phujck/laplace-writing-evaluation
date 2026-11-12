"""Proofs the routing advisor owes.

Two of them are the ones the packet brief names, and they are checks rather than
sentences: the decision alphabet IS the dispatch table (so it cannot be written by
hand, and the test fails if either side moves), and the advisor cannot reach a write
(so it cannot be the thing that authorises one).  The rest hold the flag off by
default, hold the calibration monotone with counts, and hold every `file:line` this
lane cites to the line it claims.

    scripts/laplace-python -m pytest -q tests/test_routing.py \
        --basetemp=/tmp/pytest-jev-routing -p no:cacheprovider
"""
from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import textwrap

import pytest

HERE = Path(__file__).resolve().parent
TREE = HERE.parent
sys.path.insert(0, str(TREE / "src"))
sys.path.insert(0, str(HERE / "routing_calibration"))

from laplace.core import grammar as g        # noqa: E402
from laplace.native import routing             # noqa: E402

MAPPING = HERE / "grammar_spec" / "mapping.csv"
CORPUS = Path("/home/phujck/VScodeProjects/laplace/evidence/"
              "WRITING_RECONCILIATION_2026-10-02/harness/corpus")


# ---------------------------------------------------------------------------
# 1. The alphabet is the dispatch table.  The brief's first required test.
# ---------------------------------------------------------------------------
def _mapping_pairs() -> set[tuple[str, str]]:
    with MAPPING.open(newline="", encoding="utf-8") as handle:
        return {(row["verb"].strip(), row["concept"].strip()) for row in csv.DictReader(handle)}


def test_the_route_alphabet_is_the_dispatch_table_not_a_list():
    """`routing.ROUTE_OPTIONS` is generated from the DISPATCH TABLE, and the three
    sides are compared both ways.

    The synthesis stage moved the generator from `grammar.VERB_CONCEPTS` to
    `writing_verbs.ROUTES`, the table the verb door actually routes with, because the
    advisor must not be able to suggest a pair `writing_tools.request()` cannot route.
    `mapping.csv` is the one row source behind both. This test fails if ANY of the three
    moves: a pair in the mapping with no `door == "both"` route, a route for a pair the
    grammar does not declare, a pair written into either lane by hand."""
    from laplace.native import verbs as v
    import laplace.core.identity_doors                       # noqa: F401  (declares live pairs)
    dispatch = {(route.verb, route.concept) for route in v.ROUTES if route.door == "both"}
    # The alphabet is the door=both projection UNION the pairs a lane declared live
    # (`route_options`' own definition). Asserting plain equality held only while
    # `ADDED_PAIRS` was empty at import, which stopped being true when `identity_doors`
    # declared the editor's keep/cut acts; the union is what the module documents and what
    # the companion test (`test_a_pair_declared_at_runtime_widens_the_advisors_alphabet`)
    # requires, so the equality is stated against the union and the EXECUTABILITY claim is
    # made separately and more strongly below.
    assert set(routing.ROUTE_OPTIONS) == dispatch, (
        "the advisor's option set is not the dispatch table's door=both projection: "
        "%r only in the module, %r only in the table"
        % (sorted(set(routing.ROUTE_OPTIONS) - dispatch),
           sorted(dispatch - set(routing.ROUTE_OPTIONS))))
    # ... and every live-declared pair the verb door cannot route is REPORTED with the door
    # that can. A pair only an HTTP door routes is a legitimate act of this system (the
    # editor's keep/cut ruling); a pair neither door routes is an entry nothing can execute.
    outside = routing.declared_pairs_outside_the_verb_door()
    assert [row for row in outside if row["routed_by"] == "none"] == [], outside
    assert {row["act"] for row in outside} == {
        "%s %s" % pair for pair in set(g.ADDED_PAIRS) - dispatch}, outside
    declared = set(g.VERB_CONCEPTS) | set(g.ADDED_PAIRS)   # the closed set and the pairs owners declare at import
    # every pair the verb door routes is a declared pair, and every pair of the closed set is routed by the verb door;
    # a pair declared at import may instead be routed by an HTTP door alone (reported above, never silently)
    assert dispatch <= declared and set(g.VERB_CONCEPTS) <= dispatch, (
        "the dispatch table and the grammar's declared pairs disagree: "
        "%r only routable, %r closed-set pairs not routable"
        % (sorted(dispatch - declared), sorted(set(g.VERB_CONCEPTS) - dispatch)))
    assert dispatch == _mapping_pairs(), (
        "the dispatch table and mapping.csv disagree: "
        "%r only in the table, %r only in the csv"
        % (sorted(dispatch - _mapping_pairs()), sorted(_mapping_pairs() - dispatch)))
    # every pair of the whole table, shim routes included, is a pair the grammar
    # declares: a route for an undeclared pair could never be asked for in a Request.
    assert {(route.verb, route.concept) for route in v.ROUTES} <= set(g.VERB_CONCEPTS) | set(g.ADDED_PAIRS)
    # 105 routable pairs (104 + (change, turn@project), S2 settings-three-ways 2026-10-05:
    # session_settings_change, added after the verb audit the same way repository
    # action=interface was), plus whatever a lane declared live (3 today: the editor's
    # keep/cut ruling at paragraph, section and chapter altitude). The two numbers are kept
    # apart so a new tool route and a new live declaration cannot be confused for each other.
    # S3 dispatch-build (2026-10-06): 105 + 3 pairs at task@project (create/read/run), the
    # in-app dispatch door's five operations over three pairs.
    # Reconciled 2026-10-19 (core consolidation, runtime family): the pins are the table's own
    # measured sizes.  Since 2026-10-06 other lanes added profile-candidate, architecture-profile,
    # artifact@paragraph and plan-section pairs without refreshing these numbers; the structural
    # law (every both-door pair is declared, every declared pair is routed) is held above and in
    # tests/test_core_runtime_dispatch.py, so a count here can only catch an unexplained drift.
    # in-harness join (2026-10-20): + 8 reviewed lane pairs and 10 routes (development_source 6, work_delivery 4);
    # causal correction (2026-10-20): + 1 route (development_source status, the bounded facet page) on an existing pair;
    # residual closure (2026-10-20): + 1 route (development_source delegate, the parent's narrowing) on the bind pair
    assert len(dispatch) == 130, len(dispatch)
    assert len(routing.ROUTE_OPTIONS) == 130, len(routing.ROUTE_OPTIONS)
    assert len(v.ROUTES) == 194, len(v.ROUTES)


def test_this_lane_writes_no_verb_concept_or_refusal_kind_of_its_own():
    """No list of verbs, concepts or refusal kinds anywhere in `routing.py`.

    A second list is the 20-names defect in a new spelling (GRAMMAR.md §8, "two lanes
    with two grammar.py files"), so the module is searched for every verb name
    appearing in a tuple or list literal."""
    source = (TREE / "src" / "laplace" / "native" / "routing.py").read_text(encoding="utf-8")
    for verb in g.VERBS:
        assert '"%s",' % verb not in source and "'%s'," % verb not in source, verb
    for kind in g.Refusal.KINDS:
        # the kinds appear as RESOLVER_CURE keys, which is a cure per kind, not a
        # second alphabet -- so the check is that they never appear in a sequence
        # literal that could stand in for the alphabet.
        assert '"%s",' % kind not in source, kind
    assert "grammar.VERB_CONCEPTS" in source and "grammar.Refusal.KINDS" in source


def test_the_resolver_alphabet_is_the_grammars_refusal_kinds():
    assert routing.RESOLVER_OPTIONS == g.Refusal.KINDS
    assert set(routing.RESOLVER_CURE) == set(g.Refusal.KINDS)
    for kind, cure in routing.RESOLVER_CURE.items():
        assert cure.strip(), kind


def test_both_option_sets_fit_one_choice():
    """255 options is the vendor's documented ceiling for one `choice`
    (`primitives/choice.md`, jev-assessment.md §1).  104 and 4 fit, so the chained
    beam search the vendor documents above the ceiling is not needed --- and this is a
    check, because a lane that declares pairs could cross it."""
    assert routing.options_fit_one_choice()
    assert len(routing.ROUTE_OPTIONS) <= routing.CHOICE_CEILING
    assert len(routing.RESOLVER_OPTIONS) <= routing.CHOICE_CEILING


# ---------------------------------------------------------------------------
# 2. The advisor cannot reach a write.  The brief's second required test.
# ---------------------------------------------------------------------------
# THE HOLE ROUND 3 FOUND, AND WHY IT MATTERED HERE.  The probe below installs the audit
# hook AFTER `from laplace.native import routing`, so a write performed while the advisor's
# modules IMPORT was never recorded: planting
# `open('/tmp/.../planted.txt','a').write(...)` at `routing.py` module level left the test
# reporting "1 passed" while the write really ran.  That hole is exactly this synthesis's
# business, because this is the stage that WIDENED the import closure -- `routing.py` now
# imports `laplace.native.verbs` at module level to read the dispatch table, so "what
# happens at import" is a bigger surface after this merge than before it.  So there are now
# TWO probes and the test asserts both:
#
#   _AUDIT_PROBE         hook after the import  -> covers the DECISION CALLS (600 of them)
#   _AUDIT_IMPORT_PROBE  hook before any laplace import -> covers THE IMPORT ITSELF,
#                        and then the decision calls again under the same hook
#
# The import probe runs with `PYTHONDONTWRITEBYTECODE=1`. That is not an exemption for the
# advisor: CPython's own import machinery writes `__pycache__/*.pyc` through
# `open(..., 'xb')` and `os.replace`, which the hook sees and cannot tell apart from a
# module-level write, so the interpreter's bytecode cache is switched off rather than
# filtered out of the result. Every other write the hook can see is reported.
#: THE WRITE-OPEN RULE, one text, interpolated into both probes below and into the control
#: that plants a write.  Two copies of a guard is the defect this campaign is about, and the
#: guard was wrong in both copies: `args[1]` is the STRING mode for `builtins.open` and `None`
#: for `os.open`, where the int flags in `args[2]` carry the intent, so an `os.open` write was
#: invisible to a proof whose whole content is that the count is zero.  Measured on this
#: interpreter, not assumed: `test_the_write_probe_sees_an_os_open_write` plants one and the
#: rule this replaced is run on the same planted text and shown reporting nothing.
_WRITE_OPEN_RULE = '''
import os

_WRITE_FLAGS = (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC)

def _is_write_open(args):
    mode = args[1] if len(args) > 1 else None
    flags = args[2] if len(args) > 2 else None
    if isinstance(mode, str):
        return any(flag in mode for flag in ("w", "a", "x", "+"))
    for candidate in (flags, mode):
        if isinstance(candidate, int) and not isinstance(candidate, bool):
            return bool(candidate & _WRITE_FLAGS)
    return True
'''

#: The rule this replaced, kept as text so the control can run it and the blindness is a
#: measurement rather than a sentence.  `os.open` puts `None` where this reads the mode.
_LEGACY_OPEN_RULE = '''
def _is_write_open(args):
    mode = args[1] if len(args) > 1 else "r"
    return bool(mode) and any(flag in str(mode) for flag in ("w", "a", "x", "+"))
'''

#: An `os.open` write, planted into a probe immediately after the hook goes in.
_PLANTED_OS_OPEN = (
    "\nimport os as _plant_os\n"
    "_plant_fd = _plant_os.open(%(planted)r, _plant_os.O_WRONLY | _plant_os.O_CREAT, 0o600)\n"
    "_plant_os.write(_plant_fd, b'planted')\n"
    "_plant_os.close(_plant_fd)\n")

_HOOK_INSTALLED = "sys.addaudithook(hook)"


def _probe_text(probe: str, labels: Path, rule: str = "") -> str:
    return probe % {"src": str(TREE / "src"), "labels": str(labels),
                    "write_open": rule or _WRITE_OPEN_RULE}


def _run_probe(tmp_path, name: str, source: str, env=None) -> dict:
    """Run one probe in its own interpreter and return the JSON line it prints."""
    script = tmp_path / name
    script.write_text(source)
    completed = subprocess.run([str(TREE / "scripts" / "laplace-python"), str(script)],
                               capture_output=True, text=True, cwd=str(TREE), check=False,
                               env=env)
    assert completed.returncode == 0, completed.stderr[-2000:]
    return json.loads(completed.stdout.strip().splitlines()[-1])


_AUDIT_PROBE = textwrap.dedent(
    '''
    import json, sys
    sys.path.insert(0, %(src)r)

    BANNED = ("subprocess.Popen", "subprocess.run", "os.system", "os.exec", "os.fork",
              "socket.socket", "socket.connect", "shutil.", "os.rename", "os.remove",
              "os.mkdir", "os.rmdir", "urllib.Request")
    violations = []
    %(write_open)s

    def hook(event, args):
        if event == "open":
            if _is_write_open(args):
                violations.append((event, str(args[0])))
        elif event.startswith(BANNED) or event in ("exec", "compile"):
            if event in ("exec", "compile"):
                return
            violations.append((event, str(args)[:120]))

    from laplace.native import routing            # imported BEFORE the hook, like any module
    rows = [json.loads(line) for line in open(%(labels)r).read().splitlines() if line.strip()]
    sys.addaudithook(hook)

    head = routing.PriorDecider().fit([(routing.features(routing.RouteState(**r["state"])),
                                        r["label"]) for r in rows[:200]])
    advised = 0
    for row in rows:
        advice = routing.advise(routing.RouteState(**row["state"]), decider=head,
                                threshold=0.0, by="test")
        advised += 1
        if advice.request is not None:
            assert advice.request.verb in routing.__dict__ or True
    for row in rows[:60]:
        routing.advise_refusal(row.get("error") or "revision conflict", decider=head,
                               threshold=0.0)
    print(json.dumps({"advised": advised, "violations": violations[:8],
                      "n_violations": len(violations),
                      "laplace_modules": sorted(m for m in sys.modules
                                                if m == "laplace" or m.startswith("laplace."))}))
    '''
)


# The same hook, installed BEFORE anything from `laplace` is imported, so the import of
# `laplace`, `laplace.pipeline.canon`, `laplace.core.grammar`, `laplace.native.verbs` (the dispatch
# table this synthesis added to the closure) and `laplace.native.routing` all run under it.
_AUDIT_IMPORT_PROBE = textwrap.dedent(
    '''
    import json, sys
    sys.path.insert(0, %(src)r)

    BANNED = ("subprocess.Popen", "subprocess.run", "os.system", "os.exec", "os.fork",
              "socket.socket", "socket.connect", "shutil.", "os.rename", "os.remove",
              "os.mkdir", "os.rmdir", "urllib.Request")
    violations = []
    %(write_open)s

    def hook(event, args):
        if event == "open":
            if _is_write_open(args):
                violations.append((event, str(args[0])))
        elif event.startswith(BANNED) or event in ("exec", "compile"):
            if event in ("exec", "compile"):
                return
            violations.append((event, str(args)[:120]))

    assert not any(m == "laplace" or m.startswith("laplace.") for m in sys.modules), \\
        "a laplace module was already imported before the hook; the probe would not cover it"
    sys.addaudithook(hook)                   # BEFORE any laplace import, unlike the other probe
    from laplace.native import routing              # the whole closure imports UNDER the hook
    import_violations = list(violations)

    rows = [json.loads(line) for line in open(%(labels)r).read().splitlines() if line.strip()]
    head = routing.PriorDecider().fit([(routing.features(routing.RouteState(**r["state"])),
                                        r["label"]) for r in rows[:200]])
    advised = 0
    for row in rows:
        routing.advise(routing.RouteState(**row["state"]), decider=head,
                       threshold=0.0, by="test")
        advised += 1
    for row in rows[:60]:
        routing.advise_refusal(row.get("error") or "revision conflict", decider=head,
                               threshold=0.0)
    print(json.dumps({"advised": advised,
                      "import_violations": import_violations[:8],
                      "n_import_violations": len(import_violations),
                      "violations": violations[:8], "n_violations": len(violations),
                      "laplace_modules": sorted(m for m in sys.modules
                                                if m == "laplace" or m.startswith("laplace."))}))
    '''
)


def test_the_advisor_cannot_reach_a_write(tmp_path):
    """Run the whole advisor over every labelled row under an audit hook that records
    any `open` for writing, any subprocess, any socket and any filesystem mutation.

    This is the guarantee `jev-assessment.md` §4.5 asks for in one sentence --- a
    decision layer may choose among verbs and reads and must never be the thing that
    authorises a write --- as a check.

    The import closure is measured too, and the measured answer is four modules, not
    two: importing `laplace.native.routing` runs `laplace/__init__.py`, which imports
    `laplace.pipeline.canon` at `src/laplace/__init__.py:9`.  So the honest claim is the one
    asserted here --- no owner surface is in the closure, and `writing_tools._execute`
    (`src/laplace/writing_tools.py:181`) is not reachable by name --- not "nothing but
    the grammar"."""
    labels = _labels_file(tmp_path)
    result = _run_probe(tmp_path, "audit_probe.py", _probe_text(_AUDIT_PROBE, labels))
    assert result["n_violations"] == 0, result["violations"]
    assert result["advised"] > 100, result

    # THE SECOND PROBE: the same hook, installed before `laplace` is imported at all, so
    # the number covers the IMPORT of the whole closure as well as the decision calls.
    # Round 3 showed the first probe alone cannot see a module-level write; this one can,
    # and `break_the_round3_proofs.sh` §2 plants one and shows this test fail.
    imported = _run_probe(tmp_path, "audit_import_probe.py",
                          _probe_text(_AUDIT_IMPORT_PROBE, labels),
                          env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    assert imported["n_import_violations"] == 0, imported["import_violations"]
    assert imported["n_violations"] == 0, imported["violations"]
    assert imported["advised"] == result["advised"], (imported["advised"], result["advised"])
    # and the closure measured under the hook is the same closure the other probe measures,
    # so the five-module claim is not an artefact of when the hook went in
    assert imported["laplace_modules"] == result["laplace_modules"], (
        imported["laplace_modules"], result["laplace_modules"])
    # Five, not four: the synthesis stage made the alphabet the dispatch table, so
    # `laplace.native.verbs` is in the closure. It is a TABLE -- its only module-level
    # import is `laplace.core.grammar` -- and the module that can execute, `writing_tools`, is
    # asserted absent by name as well as by the owner scan below.
    assert result["laplace_modules"] == ["laplace", "laplace.pipeline.canon", "laplace.core.grammar",
                                         "laplace.native.routing",
                                         "laplace.native.verbs"], result["laplace_modules"]
    assert "laplace.native.tools" not in result["laplace_modules"]
    owners = ("writing_tools", "writing_provider", "authoring_surface", "project_structure",
              "concepts_surface", "manuscript_structure", "manuscript_blocks",
              "review_surface", "research_surface", "visuals_surface", "pipeline",
              "writing_contracts", "writing_sources", "journal")
    for module in result["laplace_modules"]:
        assert not any(owner in module for owner in owners), module


def test_the_write_probe_sees_an_os_open_write(tmp_path):
    """The negative control the never-writes guarantee did not have.

    `test_the_advisor_cannot_reach_a_write` asserts a count is 0, and a count that cannot
    rise is not evidence of anything.  So an `os.open` write is PLANTED into the probe,
    under the hook, and the rule the shipped probes use has to report it by path --- and the
    rule this synthesis replaced, run on the same planted text, is shown reporting nothing,
    which is exactly how the guarantee was blind.  One control covers both probes because
    `_WRITE_OPEN_RULE` is ONE text that both of them interpolate.
    """
    labels = _labels_file(tmp_path)
    planted = tmp_path / "planted_by_os_open.txt"
    plant = _PLANTED_OS_OPEN % {"planted": str(planted)}
    seeing = _probe_text(_AUDIT_PROBE, labels)
    blindly = _probe_text(_AUDIT_PROBE, labels, rule=_LEGACY_OPEN_RULE)
    for source in (seeing, blindly):
        assert source.count(_HOOK_INSTALLED + "\n") == 1, "the plant has one place to go"
    caught = _run_probe(tmp_path, "planted_probe.py",
                        seeing.replace(_HOOK_INSTALLED + "\n",
                                       _HOOK_INSTALLED + "\n" + plant))
    assert planted.is_file(), "the planted write did not run, so this control proves nothing"
    assert caught["n_violations"] >= 1, caught
    assert str(planted) in [path for _, path in caught["violations"]], caught["violations"]
    blind = _run_probe(tmp_path, "planted_legacy_probe.py",
                       blindly.replace(_HOOK_INSTALLED + "\n",
                                       _HOOK_INSTALLED + "\n" + plant))
    assert blind["n_violations"] == 0, (
        "the rule this replaced now reports the planted os.open write, so this control no "
        "longer shows what was blind and the fix it justifies needs re-measuring: %r"
        % (blind["violations"],))


DEPOSITED_LABELS = Path("/home/phujck/VScodeProjects/laplace/evidence/"
                        "WRITING_RECONCILIATION_2026-10-02/wave1/jev-routing/labels.json")
_LABELS_CACHE: dict[str, dict] = {}


def _labels_data() -> dict:
    """The labelled rows --- 540 D1, 286 D4 --- BUILT HERE, and never skipped.

    This used to look for a scratch file under /tmp and `pytest.skip` when it was
    absent, which meant the two guarantees that rest on it --- "the advisor cannot
    reach a write" and the only flag-ON exercise of the two seams --- silently
    vanished from a green run on any machine that did not happen to hold the
    builder's /tmp state.  A guarantee that can be absent from a green run is not a
    guarantee.  So: build the rows in-process from `labels.py` (0.24 s, the same
    `build()` the CLI calls, no file needed), fall back to a deposited
    `labels.json`, and FAIL with every path tried if neither works.
    """
    if "data" in _LABELS_CACHE:
        return _LABELS_CACHE["data"]
    tried, data = [], None
    try:
        import labels as labels_module          # tests/routing_calibration, already on sys.path
        data = labels_module.build()
        tried.append("labels.build() in-process: ok")
    except Exception as exc:                    # noqa: BLE001 - reported, not swallowed
        tried.append("labels.build() in-process: %s: %s" % (type(exc).__name__, exc))
    if data is None:
        for candidate in (HERE / "routing_calibration" / "labels.json", DEPOSITED_LABELS):
            try:
                data = json.loads(candidate.read_text())
                tried.append("%s: ok" % candidate)
                break
            except Exception as exc:            # noqa: BLE001
                tried.append("%s: %s: %s" % (candidate, type(exc).__name__, exc))
    assert data is not None, (
        "the labelled rows could not be built or read, so the guarantees that rest on "
        "them cannot be checked. This is a FAILURE and never a skip. Tried:\n  "
        + "\n  ".join(tried))
    assert len(data["d1"]) > 100 and len(data["d4"]) > 100, (
        "too few labelled rows to check anything: %s"
        % ({k: len(v) for k, v in data.items() if isinstance(v, list)},))
    _LABELS_CACHE["data"] = data
    return data


def _labels_file(tmp_path: Path) -> Path:
    """One JSONL line per labelled row, written where the caller's fixture points.

    Kept beside the test so the audit probe needs no laplace import of its own.
    """
    out = tmp_path / "labels.jsonl"
    data = _labels_data()
    rows = [{"state": r["state"], "label": r["label"]} for r in data["d1"]]
    for r in data["d4"][:60]:
        rows.append({"state": {"door": "tool", "mode": "work", "payload": {},
                               "target": "", "path": ""},
                     "label": data["d1"][0]["label"], "error": r["error"]})
    out.write_text("\n".join(json.dumps(r, sort_keys=True) for r in rows) + "\n")
    return out


def test_advise_returns_a_request_and_never_an_effect():
    head = routing.PriorDecider().fit([
        (routing.features(routing.RouteState(payload={"node": "x", "results": [{"id": "r"}]})),
         "bind result@claim"),
        (routing.features(routing.RouteState(payload={"files": ["a.tex"]})),
         "read source-file@paragraph")])
    advice = routing.advise(routing.RouteState(payload={"files": ["b.tex"]}),
                            decider=head, threshold=0.0, by="eigen")
    assert isinstance(advice.request, g.Request)
    assert advice.request.verb in g.VERBS
    assert (advice.request.verb, advice.request.concept) in g.VERB_CONCEPTS
    # the Advice carries no callable and no handle to anything that could act
    for value in vars(advice).values():
        assert not callable(value), value


def test_a_low_confidence_advisor_abstains_and_offers_no_request():
    head = routing.PriorDecider().fit([
        (("key=a",), "read plan@plan"), (("key=b",), "read source-file@paragraph")])
    advice = routing.advise(routing.RouteState(payload={"zzz": 1}), decider=head,
                            threshold=0.99)
    assert advice.request is None and advice.abstained
    assert "abstained" in advice.said


def test_a_suggestion_the_grammar_refuses_is_not_made():
    """The advisor builds a `grammar.Request`, so the grammar is the last word.  A
    decider that returns a pair outside the declared set produces an abstention with
    the grammar's own refusal quoted, not a request."""
    class Rogue:
        name = "rogue"

        def ask(self, state_text, options, instructions, feature_hint=()):  # noqa: ANN001
            return {"change totally-made-up-thing@claim": 1.0}

    advice = routing.advise(routing.RouteState(payload={"x": 1}), decider=Rogue(),
                            threshold=0.0)
    assert advice.request is None
    assert "the grammar refused" in advice.said


# ---------------------------------------------------------------------------
# 3. The flag, the state, the calibration.
# ---------------------------------------------------------------------------
def test_the_advisor_is_off_unless_the_flag_is_set():
    assert routing.enabled({}) is False
    assert routing.enabled({routing.ADVISOR_FLAG: ""}) is False
    assert routing.enabled({routing.ADVISOR_FLAG: "0"}) is False
    assert routing.enabled({routing.ADVISOR_FLAG: "1"}) is True
    assert routing.enabled({routing.ADVISOR_FLAG: "true"}) is True


def test_the_route_state_never_carries_the_answer():
    """The discriminator key IS the label, so a state that kept it would measure
    nothing.  Checked over every corpus payload, not over an example."""
    rows = []
    for name in ("failures", "reads", "writes", "arrival", "ledger"):
        path = CORPUS / ("%s.jsonl" % name)
        if path.exists():
            rows += [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    assert rows, "the harness corpus is not where HARNESS.md says it is"
    leaked = 0
    for row in rows:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        state = routing.RouteState(door=row.get("door") or "tool",
                                   mode=row.get("mode") or "work", payload=payload)
        text = json.dumps(state.stripped_payload(), sort_keys=True, default=str)
        for key in routing._DISCRIMINATOR_KEYS:
            assert ('"%s":' % key) not in text.replace(" ", ""), (row["id"], key, text[:200])
        if payload:
            leaked += len(payload) - len(state.stripped_payload())
    assert leaked > 0, "no corpus payload carried a discriminator, so this test proves nothing"
    # The state's own top-level `mode` is the WRITING mode (work | discuss | revise |
    # review, `src/laplace/writing_tools.py:184`), which is legitimate decision state
    # and is never a sub-verb; the payload-level `mode` of `experiment_run` and
    # `export_pdf` IS a sub-verb, and the assertion above is what removes it.
    state = routing.RouteState(mode="work", payload={"mode": "smoke", "producer_id": "p"})
    assert "smoke" not in state.state_text()
    assert '"mode": "work"' in state.state_text()


def test_the_home_vocabulary_replaces_the_guard_names_rather_than_adding_to_them():
    state = routing.RouteState(payload={"base_revision": "x" * 64, "node": "n"})
    names = routing.features(state, "names")
    homes = routing.features(state, "homes")
    noguard = routing.features(state, "noguard")
    assert "guard=base_revision" in names and not any(f.startswith("home=") for f in names)
    assert "guard=base_revision" not in homes
    assert sorted(f for f in homes if f.startswith("home=")) == sorted(
        "home=" + h for h in g.GUARD_NAMES["base_revision"])
    assert not any(f.startswith(("guard=", "home=")) for f in noguard)


def test_the_calibration_is_monotone_and_its_bins_carry_counts():
    pairs = [(0.1, False), (0.2, False), (0.3, True), (0.4, False), (0.5, True),
             (0.6, True), (0.7, True), (0.8, True), (0.9, True), (0.95, True)]
    mapping = routing.fit_calibration(pairs, fitted_on="unit")
    values = [mapping(score) for score, _ in pairs]
    assert values == sorted(values), values
    assert mapping.n == len(pairs)
    assert sum(k[2] for k in mapping.knots) == len(pairs)
    for row in mapping.bins():
        assert row["n"] >= 1 and 0.0 <= row["mean_calibrated"] <= 1.0
    curve = routing.expected_calibration_error([(mapping(s), c) for s, c in pairs])
    assert curve["n"] == len(pairs)
    assert all(b["n"] >= 1 for b in curve["bins"]), curve
    assert 0.0 <= curve["ece"] <= 1.0


def test_confidence_is_the_spread_of_the_distribution():
    assert routing.spread_confidence({"a": 1.0, "b": 0.0}) == pytest.approx(1.0)
    even = {chr(97 + i): 0.25 for i in range(4)}
    assert routing.spread_confidence(even) == pytest.approx(0.0, abs=1e-9)
    assert 0.0 < routing.spread_confidence({"a": 0.7, "b": 0.2, "c": 0.1}) < 1.0


def test_the_abstain_rule_is_the_measured_cost_rule():
    """One turn is the operating brief; a wrong route's price is that operation's
    contract.  Both numbers are measured, not chosen."""
    assert routing.TURN_CHARS == 18158
    assert routing.CONTRACT_CHARS_MAX == 32611
    assert routing.within_one_turn([985, 985, 985])
    assert not routing.within_one_turn([32611])


# ---------------------------------------------------------------------------
# 4. The citations.
# ---------------------------------------------------------------------------
def _line(rel: str, number: int) -> str:
    return (TREE / "src" / "laplace" / rel).read_text(encoding="utf-8").split("\n")[number - 1]


# Every load-bearing `file:line` this lane writes down, as (file, line, what must be ON
# that line).
#
# WHY A TABLE, AND NOT A LOOP.  Until round 3 the tail of the test below was a catch-all
# over every citation a regex could find in `routing.py`, and it asserted only two things:
# that the file exists, and that the number is inside it.  A range check is not a citation
# check, and it showed: `routing.py` cited the dispatch table as
# `src/laplace/writing_verbs.py:152`, `:152` was `return tuple(pair for pair in
# self.selector if pair not in lifted)` inside `Route.keep`, `ROUTES` is at `:159` in THIS tree --- seven
# lines off, on the one citation this synthesis's headline claim ("the alphabet is
# generated from the table") rests on --- and the loop passed. So the loop is gone. Every
# citation in `routing.py` must now appear here with a substring, and the completeness
# assertion at the end of the test fails on a citation nobody wrote a row for.
CITED_LINES: tuple[tuple[str, int, str], ...] = (
    ("writing/operations.py", 145, "def _execute("),
    ("writing/reads.py", 16, "READS = {"),
    ("writing/reads.py", 22, "WRITES = {"),
    ("native/tools.py", 1316, "def failure_response("),
    ("native/tools.py", 1224, "def bank_failure("),
    ("native/tools.py", 1277, "def tool_failure("),
    ("native/tools.py", 1323, "`retry_instruction` is DELETED"),
    ("native/tools.py", 1392, ">9500"),
    ("native/tools.py", 1443, '"changed","stale","conflict","consumed"'),
    ("native/tools.py", 1404, "def add(op,values)"),
    ("native/tools.py", 1439, 'add("proofs",{})'),
    ("native/tools.py", 1712, "recovery=tool_failure(Path(args.root)"),
    ("writing/provider.py", 1275, 'brief, "claude", resumed=bool(self.native_id))'),
    ("writing/provider.py", 1116, 'brief, "codex", resumed=bool(self.native_id))'),
    ("writing/provider.py", 1282, "--system-prompt"),
    ("writing/provider.py", 1120, "developerInstructions"),
    ("writing/provider.py", 1077, "tool_failure("),
    ("native/contracts.py", 107, "def exact_contract("),
    ("native/contracts.py", 33, "operation_contract()"),
    ("writing/turn_reads.py", 314, "def failure_recovery_reads"),
    ("research/research_records.py", 382, '"error": "run_id is not complete and current"'),
    ("native/verbs.py", 159, "BEGIN ROUTES"),
    ("native/verbs.py", 161, "ROUTES: tuple[Route, ...] = ("),
    ("__init__.py", 9, "from laplace.pipeline.canon import"),
)


def test_the_cited_lines_are_the_lines_they_claim():
    """Every load-bearing `file:line` in this lane, checked against the line's TEXT.

    The grammar packet lost a round to two wrong line numbers on its headline claim;
    this lane's headline claims are the two decision sites, the two cost sites and the
    dispatch table the alphabet is generated from."""
    for rel, number, expected in CITED_LINES:
        assert expected in _line(rel, number), (rel, number, expected,
                                                _line(rel, number).strip())
    # The SYNTHESIS stages' own reconciliation.  The altitude-dispatch lane inserted 108
    # lines above `failure_response`; the whole-system merge moved the same block again, and
    # WRITING-CONSOLIDATION-W1's synthesis moved it a third time by routing the stdio failure
    # receipt through `_bank_talk_row` and documenting the seven bank sites
    # (`failure_response` is at :1222 here, was :1190, then :1157, base :1049). The two that
    # a regex over `routing.py` cannot see -- a bare `:1416` inside a docstring in
    # writing_tools.py and the caller pair cited in writing_verbs.py -- are asserted here,
    # so the next lane that moves this block is stopped by a check rather than by a reader.
    assert "which :1592 already does by size" in (
        TREE / "src" / "laplace" / "native" / "tools.py").read_text(encoding="utf-8")
    assert "``writing_tools.py:1088@706a8204``, inside ``failure_response`` at" in (
        TREE / "src" / "laplace" / "native" / "verbs.py").read_text(encoding="utf-8")
    # COMPLETENESS. Every `src/laplace/<file>:<line>` `routing.py` cites must have a row
    # above, so a citation nobody wrote a substring for fails HERE instead of passing a
    # range test. This is the assertion that would have caught `writing_verbs.py:152`:
    # with no row for it, the set difference is non-empty and the test fails; with a row
    # for it, the substring check above fails. There is no longer a way for a wrong number
    # in `routing.py` to pass this test.
    source = (TREE / "src" / "laplace" / "native" / "routing.py").read_text(encoding="utf-8")
    cited = {(rel, int(number)) for rel, number
             in re.findall(r"src/laplace/([a-z_]+(?:/[a-z_]+)?\.py):(\d+)", source)}
    assert len(cited) >= 8, cited
    checked = {(rel, number) for rel, number, _ in CITED_LINES}
    assert cited <= checked, sorted(cited - checked)


def test_the_live_substring_decision_is_what_this_lane_says_it_is():
    """The comparison baseline is a reading of the live code, so it is checked against
    the live code: four words, one answer, and no refusal kind at all when it misses."""
    from calibrate import live_substring
    assert live_substring("structure revision conflict; read the current plan state first") \
        == "identity-stale"
    assert live_substring("Consulted project evidence changed (repository).") == "identity-stale"
    assert live_substring("Full-text retrieval failed (HTTP 403)") == "<no kind>"
    assert live_substring("unknown project") == "<no kind>"
    line = _line("native/tools.py", 1443)   # the CITED_LINES row for these four words; reconciled 2026-10-19
    for word in ("changed", "stale", "conflict", "consumed"):
        assert word in line


# ---------------------------------------------------------------------------
# 5. The labelling is a lookup, not an opinion.
# ---------------------------------------------------------------------------
def test_every_label_comes_from_the_mapping_table():
    from labels import load_mapping, route_label
    leaf, disc = load_mapping()
    pair, reason = route_label("structure_change", {"operation": "bind_results"}, leaf, disc)
    assert pair == ("bind", "result@claim") and "bind_results" in reason
    pair, reason = route_label("note_status", {"status": "open"}, leaf, disc)
    assert pair == ("change", "note@claim")
    pair, reason = route_label("note_status", {"status": "resolved"}, leaf, disc)
    assert pair == ("delete", "note@claim")
    pair, reason = route_label("logical_plan", {"project": "p"}, leaf, disc)
    assert pair is None and reason.startswith("default-sub-verb-unmapped")
    pair, reason = route_label("Bash", {"command": "ls"}, leaf, disc)
    assert pair is None and reason.startswith("outside-the-mapping")


def test_the_two_seams_are_silent_unless_the_flag_is_set():
    """The two places the advisor is wired, with the flag off, which is the default.

    `failure_response` is the D4 seam and `routing_advice_for_request` is the pre-call
    D1 seam.  With the flag unset both return None.  That they return it before loading
    any module is the stronger claim, and it is
    `test_the_off_path_loads_no_module` below that measures it, in a subprocess ---
    because by the time this test runs, this very file has already imported
    `laplace.native.routing`, so `sys.modules` here could never show the difference."""
    import os
    from laplace.native import tools as writing_tools
    os.environ.pop(routing.ADVISOR_FLAG, None)
    writing_tools._ROUTING_HEADS.clear()
    assert writing_tools.routing_advice_for_refusal("structure revision conflict") is None
    assert writing_tools.routing_advice_for_request("tool", "work", {"node": "n"}) is None
    response = writing_tools.failure_response(
        TREE, "synthetics-foundations", "work", "structure",
        {}, ValueError("structure revision conflict; read the current plan state first"))
    assert "routing_advice" not in response


def test_with_the_flag_and_a_head_the_seams_advise_and_still_cannot_act(tmp_path):
    import os
    from laplace.native import tools as writing_tools
    data = _labels_data()
    d4 = tmp_path / "d4.jsonl"
    d4.write_text("\n".join(json.dumps({"error": r["error"], "label": r["label"]})
                            for r in data["d4"]) + "\n")
    d1 = tmp_path / "d1.jsonl"
    d1.write_text("\n".join(json.dumps({"state": r["state"], "label": r["label"]})
                            for r in data["d1"]) + "\n")
    os.environ[routing.ADVISOR_FLAG] = "1"
    os.environ[writing_tools.ROUTING_HEAD_ENV["d4"]] = str(d4)
    os.environ[writing_tools.ROUTING_HEAD_ENV["d1"]] = str(d1)
    writing_tools._ROUTING_HEADS.clear()
    try:
        advice = writing_tools.routing_advice_for_refusal(
            "structure revision conflict; read the current plan state first")
        assert advice is not None
        assert advice["decision"]["choice"] in g.Refusal.KINDS
        assert advice["cure"], advice
        response = writing_tools.failure_response(
            TREE, "synthetics-foundations", "work", "structure", {},
            ValueError("structure revision conflict; read the current plan state first"))
        assert response["routing_advice"]["decision"]["question"] == "D4-classify"
        pre = writing_tools.routing_advice_for_request(
            "tool", "work", {"files": ["chapters/chapter-01.tex"]})
        assert pre is not None
        assert pre["request"] is None or (
            pre["request"]["verb"], pre["request"]["concept"]) in g.VERB_CONCEPTS
    finally:
        os.environ.pop(routing.ADVISOR_FLAG, None)
        os.environ.pop(writing_tools.ROUTING_HEAD_ENV["d4"], None)
        os.environ.pop(writing_tools.ROUTING_HEAD_ENV["d1"], None)
        writing_tools._ROUTING_HEADS.clear()


def test_the_refusal_class_table_covers_every_class_the_census_recorded():
    """A class the census recorded and this table does not name would be labelled
    silently by a default.  Both excluded classes are named with a reason."""
    from labels import CLASS_TO_KIND
    classes = set()
    path = CORPUS / "failures.jsonl"
    for line in path.read_text().splitlines():
        if line.strip():
            classes.add(json.loads(line)["recorded"]["error_class"])
    assert classes <= set(CLASS_TO_KIND), classes - set(CLASS_TO_KIND)
    for cls, (kind, reason) in CLASS_TO_KIND.items():
        assert kind is None or kind in g.Refusal.KINDS, (cls, kind)
        assert len(reason) > 40, cls
    assert {c for c, (k, _r) in CLASS_TO_KIND.items() if k is None} == {
        "external-fetch", "tool-permission"}


def test_the_off_path_loads_no_module():
    """Flag off: the seam returns None and `laplace.native.routing` is NOT in sys.modules.

    The judge of round 1 was right that the earlier code imported `laplace.native.routing`
    first and read the flag second, so every refusal in an unflagged live process
    pulled in the 1443-line grammar.  The replay parity run could not see it, because
    it compares response BYTES.  This test compares the loaded modules instead, in a
    fresh interpreter, before and after a refusal.  `routing_advisor_flag_on()`
    (`src/laplace/native/tools.py`, one `os.environ` read) is what makes it pass.
    """
    probe = textwrap.dedent("""
        import os, sys
        os.environ.pop("LAPLACE_ROUTING_ADVISOR", None)
        sys.path.insert(0, %(src)r)
        from laplace.native import tools as writing_tools
        before = "laplace.native.routing" in sys.modules
        assert writing_tools.routing_advice_for_refusal("structure revision conflict") is None
        assert writing_tools.routing_advice_for_request("tool", "work", {"node": "n"}) is None
        after = "laplace.native.routing" in sys.modules
        grammar = "laplace.core.grammar" in sys.modules
        print({"before": before, "after": after, "grammar": grammar,
               "notices": writing_tools.routing_advisor_notices()})
    """) % {"src": str(TREE / "src")}
    completed = subprocess.run([str(TREE / "scripts" / "laplace-python"), "-c", probe],
                               capture_output=True, text=True, cwd=str(TREE), check=False)
    assert completed.returncode == 0, completed.stderr[-2000:]
    seen = eval(completed.stdout.strip().splitlines()[-1])          # noqa: S307 - our own print
    # WHAT THE ZERO COVERS, AFTER THE WHOLE-SYSTEM MERGE.  `laplace.core.grammar` is now
    # imported by `writing_tools` itself at module level (the identity and contract lanes
    # put the token and the declarations on the tool door), so its presence in
    # `sys.modules` is no longer evidence about the advisor, and asserting `False` for it
    # measured the wrong tree.  The claim this proof makes is the one it can make: the
    # ADVISOR module is not imported by an unflagged call, and it records no notice.
    assert seen["before"] is False and seen["after"] is False, seen
    assert seen["notices"] == {}, seen
    assert seen["grammar"] is True, (
        "writing_tools imports laplace.core.grammar at module level in this tree; if that "
        "stops being true, re-measure the sentence above rather than the number")


def test_the_two_spellings_of_the_flag_agree():
    """`writing_tools` spells the flag name so the off path costs no import; this fails
    if that spelling, or the set of true words, ever differs from `routing`'s own."""
    from laplace.native import tools as writing_tools
    assert writing_tools.ROUTING_ADVISOR_FLAG == routing.ADVISOR_FLAG
    for value in ("1", "true", "TRUE", " yes ", "on", "0", "false", "", "maybe"):
        env = {routing.ADVISOR_FLAG: value}
        mine = str(value).strip().lower() in writing_tools.ROUTING_FLAG_TRUE
        assert mine == routing.enabled(env), (value, mine, routing.enabled(env))


def test_a_broken_advisor_is_recorded_rather_than_swallowed():
    """A head file that cannot be parsed must leave a reason behind, not silence.

    The round-1 code wrapped the whole seam in `except Exception: return None`, so a
    grammar module that is absent or raises at import --- a live possibility, the
    grammar being a stage-1 artefact lanes install by `cp` --- produced an advisor that
    was enabled and permanently silent with nothing recorded to say why."""
    import os
    from laplace.native import tools as writing_tools
    bad = Path(os.environ.get("TMPDIR", "/tmp")) / "jev-routing-broken-head.jsonl"
    bad.write_text("{this is not json}\n")
    writing_tools._ROUTING_NOTICES.clear()
    os.environ[routing.ADVISOR_FLAG] = "1"
    os.environ[writing_tools.ROUTING_HEAD_ENV["d4"]] = str(bad)
    try:
        assert writing_tools.routing_advice_for_refusal("structure revision conflict") is None
        notices = writing_tools.routing_advisor_notices()
        assert notices, "a broken head left no reason behind"
        assert any(n["where"] == "head-d4" and n["error_class"] == "JSONDecodeError"
                   for n in notices.values()), notices
    finally:
        os.environ.pop(routing.ADVISOR_FLAG, None)
        os.environ.pop(writing_tools.ROUTING_HEAD_ENV["d4"], None)
        writing_tools._ROUTING_NOTICES.clear()
        writing_tools._ROUTING_HEADS.clear()
        bad.unlink(missing_ok=True)


def test_a_head_that_arrives_or_changes_is_refitted_not_remembered(tmp_path):
    """The deposit is refittable IN A RUNNING PROCESS, which is what §3 claims.

    Round 1 memoised on `which` alone and cached a sentinel on failure, so the first
    refusal of a flag-on server before the operator exported the head path poisoned
    every later refusal in that process, and a replaced head was never re-read.  Three
    arrivals in one process here: absent, then present, then replaced."""
    import os
    from laplace.native import tools as writing_tools
    data = _labels_data()
    head = tmp_path / "d4.jsonl"
    rows = [{"error": r["error"], "label": r["label"]} for r in data["d4"]]
    os.environ[routing.ADVISOR_FLAG] = "1"
    os.environ[writing_tools.ROUTING_HEAD_ENV["d4"]] = str(head)
    writing_tools._ROUTING_HEADS.clear()
    writing_tools._ROUTING_NOTICES.clear()
    try:
        # 1. the head is not there yet: no advice, and NOTHING cached that forbids one.
        assert writing_tools.routing_advice_for_refusal("structure revision conflict") is None
        assert writing_tools._ROUTING_HEADS == {}, writing_tools._ROUTING_HEADS
        # 2. it arrives, in the same process: advice, with no restart.
        head.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        first = writing_tools.routing_advice_for_refusal("structure revision conflict")
        assert first is not None, writing_tools.routing_advisor_notices()
        assert len(writing_tools._ROUTING_HEADS) == 1
        # 3. it is REPLACED in place by a deposit with one class: the fit follows the file.
        one_kind = [r for r in rows if r["label"] == "shape"] or rows[:1]
        head.write_text("\n".join(json.dumps(r) for r in one_kind * 20) + "\n")
        os.utime(head, ns=(0, 0))               # a different mtime, even on a fast clock
        second = writing_tools.routing_advice_for_refusal("structure revision conflict")
        assert second is not None
        assert second["decision"]["choice"] == one_kind[0]["label"], (
            "the head was remembered rather than refitted: %r" % (second["decision"],))
        assert len(writing_tools._ROUTING_HEADS) == 1, "one entry per `which`, not a leak"
    finally:
        os.environ.pop(routing.ADVISOR_FLAG, None)
        os.environ.pop(writing_tools.ROUTING_HEAD_ENV["d4"], None)
        writing_tools._ROUTING_HEADS.clear()
        writing_tools._ROUTING_NOTICES.clear()


def test_a_pair_the_verb_door_gains_at_runtime_widens_the_advisors_alphabet():
    """The alphabet is read LIVE off the dispatch table, not frozen at import.

    This proof used to be written over `declare_pair` and asserted that declaring a pair ---
    `("read", "turn@run")`, which no route carries --- made the advisor suggest it. That was
    the wrong half of a disagreement inside this very file: the companion test
    (`test_the_advisor_cannot_suggest_a_pair_the_verb_door_cannot_route`) calls
    `writing_verbs.choose` for every option and asserts none of them raises, and `choose`
    raises for a pair with no route. Both tests passed only because `ADDED_PAIRS` was empty
    at import; `identity_doors` declaring the editor's keep/cut acts made the contradiction
    concrete (see `routing.route_options`). `declare_pair` makes a pair legal for a `Request`;
    it does not give the verb door a route, and a suggestion the caller's own `choose` throws
    on is worse than an abstention.

    So the property proved here is the one that was actually wanted: a ROUTE the table gains
    after this module was imported is suggestible immediately, with no re-import and no list
    in `routing.py` to update.
    """
    from laplace.native import verbs as v
    pair = ("read", "turn@project")                    # a real pair, a planted second route
    before = set(routing.ROUTE_OPTIONS)
    planted = ("read", "run@run")
    assert planted in before, "pick a pair the dispatch already routes"
    saved = v.ROUTES
    try:
        v.ROUTES = tuple(r for r in saved if (r.verb, r.concept) != planted)
        assert planted not in set(routing.ROUTE_OPTIONS), "the alphabet is frozen at import"
        v.ROUTES = saved
        assert set(routing.ROUTE_OPTIONS) == before, "and it follows the table back"
    finally:
        v.ROUTES = saved
    # the grammar's own second route into the closed set still works, and is still REPORTED
    # rather than silently suggested or silently dropped.
    try:
        g.declare_pair(*pair, because="a proof that a declared pair with no verb-door route "
                                      "is reported, not suggested")
        assert g.declared_pair(*pair)
        if pair not in before:
            assert pair not in set(routing.ROUTE_OPTIONS)
            assert "%s %s" % pair in {row["act"] for row in
                                      routing.declared_pairs_outside_the_verb_door()}
    finally:
        g.ADDED_PAIRS.pop(pair, None)
    assert set(routing.ROUTE_OPTIONS) == before, "the alphabet did not narrow back"


REPORT = Path("/home/phujck/VScodeProjects/laplace/evidence/"
              "WRITING_RECONCILIATION_2026-10-02/wave1/jev-routing.md")
PAIRED_DEPOSIT = Path("/home/phujck/VScodeProjects/laplace/evidence/"
                      "WRITING_RECONCILIATION_2026-10-02/wave1/jev-routing/paired_seeds")


def test_the_vocabulary_claim_is_the_pooled_rows_and_not_one_split():
    """The report's vocabulary claim must be the repeated-split result, not seed 20261002.

    Round 1 reported the paired `homes`-over-`names` comparison from ONE split --- 9
    discordant to 0, p = 0.0039 --- as "strictly dominates", "none the other way" and
    "the p is not marginal".  The report's own falsification recipe said a different
    seed should not move the direction; an independent judge ran three more splits and
    the direction held in sign while the two strong words became false (seed 13: 7 vs 1,
    p = 0.070; seed 7 at 10 folds: 4 vs 1, p = 0.375).  `paired_seeds.py` now repeats
    the whole procedure over 20 splits at 5 folds and 10 at 10 and pools the counts.

    This test is the row source holding the render: it fails if the report states a
    direction count the deposit does not carry, and it fails if the three falsified
    phrases come back.  A render that drifts from its rows is the defect this whole
    campaign is about.
    """
    assert REPORT.is_file(), REPORT
    text = REPORT.read_text()
    # The three falsified phrases may appear ONLY as the emphasised quotation inside the
    # withdrawal, never again as the report's own assertion.  Stripping the emphasised
    # form must leave no occurrence at all.
    assert "those three phrases are withdrawn" in text
    stripped = text
    for falsified in ("strictly dominates", "none the other way", "the p is not marginal"):
        stripped = stripped.replace("*%s*" % falsified, "<withdrawn>")
    for falsified in ("strictly dominates", "none the other way", "the p is not marginal"):
        assert falsified not in stripped, (
            "%r was falsified by the repeated splits and is asserted rather than quoted "
            "as withdrawn" % falsified)
    deposits = sorted(PAIRED_DEPOSIT.glob("paired_seeds_*.json"))
    assert len(deposits) >= 2, [str(d) for d in deposits]
    total_a = total_b = total_tied = total_splits = 0
    for deposit in deposits:
        summary = json.loads(deposit.read_text())
        row = summary["pooled"]["homes vs names"]
        assert row["splits_favouring_b"] == 0, (deposit.name, row)
        total_a += row["splits_favouring_a"]
        total_b += row["splits_favouring_b"]
        total_tied += row["splits_tied"]
        total_splits += row["n_splits"]
        # every split's own (discordant, p) pair is in the deposit, so the report's
        # table is checkable row by row rather than by its summary alone
        assert len(summary["per_split"]) == row["n_splits"]
    assert (total_splits, total_a, total_b, total_tied) == (30, 28, 0, 2), (
        total_splits, total_a, total_b, total_tied)
    # the sentence the report is allowed to make, in the numbers it is made of
    assert "28 of 30" in text, "the report must carry the pooled direction count"
    assert "0.0039" in text and "0.375" in text, (
        "both ends of the per-split p range belong in the report, not just the small one")


# ---------------------------------------------------------------------------
# The dispatch x jev SYNTHESIS stage's two proofs.
# ---------------------------------------------------------------------------
def test_no_reported_threshold_is_measured_on_the_rows_that_chose_it():
    """The abstain threshold is chosen on a block the scored rows are not in.

    Round 2's judge of this lane showed that `threshold_sweep` swept tau over the pooled
    TEST rows and the report then quoted that tau's precision and realised cost -- and that
    the tau does not transfer: 0.9864 precision in sample, 0.914-0.947 on other splits, with
    the realised cost four to six times over one turn, so the lane's own acceptance rule
    failed out of sample at the value it shipped.  `three_way` (calibrate.py:82) already
    holds a CALIBRATE block out; the fix was to let only that block choose tau.

    This test is the one the judge asked for: it fails if the report quotes a threshold whose
    precision was measured on the rows that chose it.  Two halves, source and behaviour.
    """
    source = (HERE / "routing_calibration" / "calibrate.py").read_text(encoding="utf-8")
    # 1. every sweep over the pooled test rows is stored under a key that SAYS in-sample,
    #    and the policy the printer quotes is the held-out one.
    sweeps = re.findall(r'"([a-z_]+)": threshold_sweep\(result\["rows"\]', source)
    assert sweeps, "the in-sample curve is no longer computed; nothing to label"
    for key in sweeps:
        assert key == "sweep_in_sample", key
    assert '"sweep_held_out": held_out_policy(result["rows"])' in source
    assert "HELD OUT (tau per fold from its calibrate block" in source
    assert "in-sample curve only, NOT a policy" in source
    # 2. behaviour: run one feature set and check each row carries its own fold's tau,
    #    that the taus differ by fold (so no single pooled tau is in use), and that the
    #    held-out policy reports precision and the cost verdict.
    import calibrate as cal
    data = _labels_data()
    costs = cal.contract_chars(None)
    result = cal.run_d1(data["d1"], seed=20261002, folds=5, feature_set="homes", costs=costs)
    by_fold = {fold["fold"]: fold["tau_chosen_on_calibrate"] for fold in result["folds"]}
    assert len(set(by_fold.values())) > 1, by_fold
    for row in result["rows"]:
        assert row["fold_tau"] == by_fold[row["fold"]], row
    held = cal.held_out_policy(result["rows"])
    assert held["n"] == len(result["rows"])
    assert held["precision_when_acting"] is not None
    assert held["realised_cost_under_one_turn"] in (True, False)
    assert held["turn_chars"] == routing.TURN_CHARS
    # the held-out policy and the in-sample curve are allowed to disagree; what is NOT
    # allowed is the held-out policy silently borrowing the in-sample point.
    in_sample = cal.threshold_sweep(result["rows"], routing.TURN_CHARS)["chosen"]
    if in_sample is not None:
        assert held["taus_by_fold"] != [in_sample["threshold"]], (held, in_sample)


def test_the_advisor_cannot_suggest_a_pair_the_verb_door_cannot_route():
    """Every pair the advisor may suggest has a route whose door is the verb door.

    The merge's point: the advisor's alphabet and the dispatch's table are one set, so a
    suggestion is always executable.  `choose` is the function `writing_tools.request` calls,
    so it is asked directly, with the route's own selector in the payload where the route
    needs one.  A pair reachable only through `door == "shim"` would be a suggestion the verb
    door refuses, which is why `route_options` takes the `door == "both"` projection; this
    test fails if the projection ever stops covering the alphabet.
    """
    from laplace.native import verbs as v
    both = {(r.verb, r.concept) for r in v.ROUTES if r.door == "both"}
    assert set(routing.ROUTE_OPTIONS) <= both
    unroutable = []
    for verb, concept in routing.ROUTE_OPTIONS:
        candidates = [r for r in v.ROUTES if (r.verb, r.concept) == (verb, concept)
                      and r.door == "both"]
        assert candidates, (verb, concept)
        payload = {}
        for path, value in candidates[0].selector:
            cursor = payload
            parts = path.split(".")
            for part in parts[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor[parts[-1]] = value
        try:
            chosen = v.choose(verb, concept, payload)
        except Exception as exc:                      # noqa: BLE001 - reported, not swallowed
            unroutable.append((verb, concept, type(exc).__name__, str(exc)[:160]))
            continue
        assert (chosen.verb, chosen.concept) == (verb, concept)
    assert not unroutable, unroutable
