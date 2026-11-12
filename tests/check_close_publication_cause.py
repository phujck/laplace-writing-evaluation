"""Finite Source-check evaluator for close/publication cause custody (stdlib only).

Run from a Source stage with /usr/bin/python3 -I -B this-file.  No package import,
model, upfold, git or child process is needed. Exact AST-selected production
function bodies are COMPILED AND EXECUTED, not matched as text. Module bootstrap,
runtime selection, heavy deposit, snapshot/restore and sewup's child invocation
are explicit seams. This tests result propagation, not real rollback, runtime
compatibility, artifact validation or full publication. No production fix here.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
CAUSE = "source frontier changed during upfold: public-fixture/authored-log.txt"
ACT = "reembed-public-result-fixture"
INPUTS = {"HANDOFF.md": "fixture-checkpoint-digest"}


def functions(path, names, namespace):
    """Execute unchanged selected function nodes; imports/callees below are seams."""
    raw = path.read_bytes()
    parsed = ast.parse(raw, filename=str(path))
    nodes = [n for n in parsed.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    if {n.name for n in nodes} != set(names):
        raise RuntimeError("Evaluator setup: expected production function missing")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), namespace)
    return hashlib.sha256(raw).hexdigest()


def reembed_at(root, outcome):
    # _publication_record imports only this digest for unpublished results.
    digest_module = types.ModuleType("laplace.representation.embed_router")
    digest_module._file_digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    for name in ("laplace", "laplace.representation"):
        sys.modules.setdefault(name, types.ModuleType(name))
    sys.modules[digest_module.__name__] = digest_module
    restored = []
    def snapshot(_root, **_kwargs):
        path = root / "snapshot"
        path.mkdir()
        return path
    def restore(_snapshot, _root):
        restored.append(True)
        (root / "prior-publication").write_bytes(b"prior accepted bytes")
        return {"artifacts": {}}
    def deposit(_argv, *, publication_out):
        (root / "prior-publication").write_bytes(b"unaccepted temporary bytes")
        if outcome == "exception":
            raise RuntimeError("public producer interruption")
        if outcome == "cause":
            publication_out.append(ns["_publication_record"](root, published=False,
                act_id=ACT, input_signature=INPUTS, reason=CAUSE))
        return 1
    ns = {"__name__": "close_result_evaluator", "ROOT": root, "SOURCE_ROOT": ROOT,
          "Path": Path, "sys": sys, "json": json, "REQUIRED_PUBLICATION_NAMES": (),
          "OPTIONAL_PUBLICATION_NAMES": (), "PUBLICATION_NAMES": (),
          "require_system_runtime": lambda _root: None,
          "_prepare_reader_projections": lambda _root: [],
          "_snapshot_publication": snapshot, "restore_publication_snapshot": restore,
          "_run_deposit": deposit}
    functions(ROOT / "scripts/reembed.py", {"main", "_publication_record"}, ns)
    stream = io.StringIO()
    error = None
    with contextlib.redirect_stdout(stream):
        try:
            code = ns["main"]([])
        except RuntimeError as exc:
            code, error = None, str(exc)
    rows = [json.loads(line.split("=", 1)[1]) for line in stream.getvalue().splitlines()
            if line.startswith("LAPLACE_PUBLICATION=")]
    if len(rows) != 1:
        raise RuntimeError("Evaluator setup/result: expected one publication marker")
    assert restored and (root / "prior-publication").read_bytes() == b"prior accepted bytes"
    return code, rows[0], error


class CloseResultContract(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_original_cause_and_producer_identity_survive_restoration(self):
        code, publication, error = reembed_at(self.root, "cause")
        self.assertEqual(code, 1)
        self.assertIsNone(error)
        self.assertFalse(publication["published"])
        self.assertEqual(publication["artifacts"], {})
        self.assertEqual(publication["reason"], CAUSE)
        self.assertEqual(publication["act_id"], ACT)
        self.assertEqual(publication["input_signature"], INPUTS)
        # Restoration is reported separately, never substituted for the cause.
        self.assertTrue(publication.get("restoration", {}).get("restored"))

    def test_no_producer_result_stays_unpublished_with_honest_fallback(self):
        code, publication, _ = reembed_at(self.root, "none")
        self.assertEqual(code, 1)
        self.assertFalse(publication["published"])
        self.assertEqual(publication["artifacts"], {})
        self.assertTrue(publication["reason"])
        self.assertNotEqual(publication["reason"], CAUSE)

    def test_exception_remains_exception_with_original_cause(self):
        code, publication, error = reembed_at(self.root, "exception")
        self.assertIsNone(code)
        self.assertEqual(error, "public producer interruption")
        self.assertFalse(publication["published"])
        self.assertIn(error, publication["reason"])

    def test_sewup_projects_retained_cause_directly_without_success(self):
        publication = {"schema_version": "laplace.publication/1", "published": False,
            "act_id": ACT, "input_signature": INPUTS, "reason": CAUSE, "artifacts": {},
            "restoration": {"restored": True}}
        ns = {"DRY_RUN": False, "FULL_METRIC": False, "ROOT": ROOT,
              "CHECKPOINT_INPUTS": INPUTS, "json": json,
              "runtime_command": lambda *_args: ["NO-CHILD-SEAM"],
              "_run": lambda *_args, **_kwargs: (1, "LAPLACE_PUBLICATION=" + json.dumps(publication)),
              "_publication_matches": lambda *_args: (_ for _ in ()).throw(AssertionError("failure must not validate as success"))}
        functions(ROOT / "scripts/sewup.py", {"step_reembed"}, ns)
        result = ns["step_reembed"]()
        self.assertFalse(result["pass"])
        self.assertEqual(result["publication"], publication)
        self.assertEqual(result["detail"], CAUSE)


if __name__ == "__main__":
    print(json.dumps({"evaluator": "close-publication-cause/1", "script_pins": {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in ("scripts/reembed.py", "scripts/sewup.py")},
        "scope": "executed selected production bodies with disclosed callee seams; no full upfold"}), flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CloseResultContract)
    if "--smoke" in sys.argv:
        suite = unittest.TestSuite(test for test in suite if test._testMethodName in {
            "test_no_producer_result_stays_unpublished_with_honest_fallback",
            "test_exception_remains_exception_with_original_cause"})
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
