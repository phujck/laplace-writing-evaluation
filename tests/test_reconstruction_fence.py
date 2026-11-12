"""Tests for the advisory reconstruction fence (WO-20260812-reconstruction-fence).

Runnable two ways, because pytest is not installed everywhere the engine runs:

    python3 -m unittest tests.test_reconstruction_fence      # from the repo root
    python3 tests/test_reconstruction_fence.py
    python3 -m pytest tests/test_reconstruction_fence.py

The cases hold the advisory tier's four promises: the probe finds a banked row from an
intent that describes it; it states the retrieval path it used and the semantic leg it
did not have; it reads no clock; and wiring it into compile_dispatch changes neither the
prompt bytes nor the ledger unless a stamp is passed.
"""

import ast
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.engine import reconstruction_fence as fence  # noqa: E402

STAMP = "2026-08-17"

_WO = {
    "id": "WO-20260812-reconstruction-fence",
    "ts": "2026-08-13T00:58:24",
    "kind": "work-order",
    "action": "build-reconstruction-before-authoring-fence",
    "what": "a reconstruction probe as a pre-build fence in the dispatch path: does the "
            "record already hold this? Ship advisory first, measuring its own "
            "false-negative rate against later landing-sweep catches.",
    "why": "every reauthoring session is a measured reconstruction failure",
    "status": "open",
}
_OTHER = {
    "id": "WO-20260814-pilot-timestamp-mechanism",
    "ts": "2026-08-14T10:03:42",
    "kind": "work-order",
    "action": "build-pilot-expiry-mechanism",
    "what": "the pilot licence carries an expiry the customer can verify without a "
            "network call to us",
    "why": "a commitment said aloud on a call",
    "status": "open",
}
_NOTE = {
    "id": "NOTE-20260813-01",
    "kind": "note",
    "target": "WO-20260812-reconstruction-fence",
    "text": "the store under the probe is the dependency: a probe over an unfaithful "
            "store licenses the reauthoring it exists to prevent",
}


def _fixture_repo(tmp: Path) -> Path:
    """A small repo carrying one of each leg the probe reads."""
    (tmp / "corpus_friction").mkdir(parents=True, exist_ok=True)
    with (tmp / fence.WORK_ORDERS).open("w", encoding="utf-8") as fh:
        for row in (_WO, _OTHER, _NOTE):
            fh.write(json.dumps(row) + "\n")
    (tmp / fence.HANDOFF).write_text(
        "# handoff\n\n## AIM (2026-08-16)\n\nthe closure meter landed on every "
        "descend, byte-proven\n\n## PRIOR AIM (2026-08-12)\n\nthe forced check was "
        "ratified: a probe before authoring\n", encoding="utf-8")
    (tmp / fence.OPEN_STACK).write_text(
        "# open stack\n\n## sweep 2026-08-12\n\nthe pilot expiry mechanism is owed to "
        "a customer commitment\n", encoding="utf-8")
    return tmp


class ProbeCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _fixture_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_probe_names_the_banked_row_for_an_intent_that_describes_it(self):
        result = fence.probe(self.repo,
                             "build a reconstruction probe that checks the record "
                             "before authoring, advisory in the dispatch path")
        ids = [r["id"] for r in result["rows"]]
        self.assertIn(_WO["id"], ids)
        orders = [r for r in result["rows"] if r["leg"] == "work_orders"]
        self.assertEqual(orders[0]["id"], _WO["id"],
                         "the matching order should outrank the unrelated one")
        self.assertEqual(orders[0]["status"], "open")
        self.assertTrue(orders[0]["ref"].endswith("#" + _WO["id"]))
        self.assertGreaterEqual(len(orders[0]["shared"]), fence.SCORE_FLOOR)

    def test_note_rows_are_folded_into_their_work_order(self):
        result = fence.probe(self.repo,
                             "an unfaithful store under the probe licenses reauthoring")
        ids = [r["id"] for r in result["rows"]]
        self.assertIn(_WO["id"], ids,
                      "the note's wording should reach its target work-order")

    def test_the_markdown_legs_answer_with_line_span_refs(self):
        result = fence.probe(self.repo, "a closure meter on every descend, byte-proven")
        hits = [r for r in result["rows"] if r["leg"] == "handoff"]
        self.assertTrue(hits, "the handoff leg should answer here")
        self.assertRegex(hits[0]["ref"], r"^HANDOFF\.md#L\d+-L\d+$")

    def test_an_unrelated_intent_returns_nothing_and_still_says_what_it_read(self):
        result = fence.probe(self.repo, "sourdough hydration ratios for rye flour")
        self.assertEqual(result["rows"], [])
        p = result["provenance"]
        self.assertGreater(p["documents"], 0)
        self.assertEqual(p["retrieval"], "lexical")
        text = fence.render(result, "sourdough hydration ratios for rye flour")
        self.assertIn("lexical", text)
        self.assertIn("not proof the record is empty", text)

    def test_the_result_names_the_retrieval_path_and_the_missing_semantic_leg(self):
        p = fence.probe(self.repo, "a reconstruction probe")["provenance"]
        self.assertEqual(p["retrieval"], "lexical")
        self.assertIn(fence.SEMANTIC_MODULE, p["semantic_leg"])
        self.assertIs(p["embedder"]["present"], fence.embedder_state()["present"])
        if not p["embedder"]["present"]:
            self.assertIn("no semantic retrieval ran", p["semantic_leg"])

    def test_the_graded_tree_leg_is_opt_in_and_the_skip_is_reported(self):
        default = fence.probe(self.repo, "a reconstruction probe")["provenance"]
        self.assertIn("graded_tree", default["legs_skipped"])
        self.assertNotIn("graded_tree", [x["leg"] for x in default["legs"]])

    def test_sealed_tree_nodes_never_reach_a_hit(self):
        (self.repo / fence.GRADED_TREE).write_text(json.dumps({
            "soul/0001.md": {"id": "soul/0001.md", "grade": 0, "sealed": True,
                             "essence": "sealed fragment",
                             "keywords": ["reconstruction", "probe", "authoring"]},
            "src/laplace/engine/spine.py": {"id": "src/laplace/engine/spine.py", "grade": 0,
                                     "sealed": False,
                                     "essence": "the goal to reconstruction-calls reflex",
                                     "keywords": ["reconstruction", "probe", "authoring"]},
        }), encoding="utf-8")
        rows = fence.probe(self.repo, "reconstruction probe authoring",
                           legs=fence.ALL_LEGS)["rows"]
        ids = [r["id"] for r in rows]
        self.assertIn("src/laplace/engine/spine.py", ids)
        self.assertNotIn("soul/0001.md", ids)

    def test_an_unknown_leg_is_refused_by_name(self):
        with self.assertRaises(fence.FenceError):
            fence.probe(self.repo, "anything", legs=("no_such_leg",))

    def test_missing_work_order_authority_refuses_a_lower_bound_reconstruction(self):
        (self.repo / fence.WORK_ORDERS).unlink()
        with self.assertRaisesRegex(fence.FenceError, "work_orders.jsonl wounded"):
            fence.probe(self.repo, "a reconstruction probe", legs=("work_orders",))

    def test_the_probe_is_deterministic(self):
        a = fence.probe(self.repo, "a reconstruction probe before authoring")
        b = fence.probe(self.repo, "a reconstruction probe before authoring")
        self.assertEqual(a, b)


class LedgerCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _fixture_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_advise_without_a_stamp_writes_nothing(self):
        rec = fence.advise(self.repo, "a reconstruction probe", site="test")
        self.assertTrue(rec["hits"])
        self.assertIn("no stamp", rec["banked"])
        self.assertFalse((self.repo / fence.LEDGER).exists())

    def test_advise_with_a_stamp_banks_one_typed_row(self):
        rec = fence.advise(self.repo, "a reconstruction probe before authoring",
                           site="test", stamp=STAMP)
        self.assertEqual(rec["id"], "FP-20260817-01")
        rows = fence.ledger_rows(self.repo)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["schema"], fence.PROBE_SCHEMA)
        self.assertEqual(rows[0]["verdict"], "unjudged")
        self.assertEqual(rows[0]["stamp"], STAMP)
        self.assertEqual(rows[0]["site"], "test")

    def test_ids_number_within_a_stamp(self):
        a = fence.advise(self.repo, "a reconstruction probe", site="t", stamp=STAMP)
        b = fence.advise(self.repo, "a pilot expiry mechanism", site="t", stamp=STAMP)
        self.assertEqual([a["id"], b["id"]], ["FP-20260817-01", "FP-20260817-02"])

    def test_a_bad_stamp_is_refused(self):
        with self.assertRaises(fence.FenceError):
            fence.bank(self.repo, {"hits": []}, stamp="last tuesday")

    def test_a_judgement_needs_a_banked_probe_and_a_known_verdict(self):
        rec = fence.advise(self.repo, "a reconstruction probe", site="t", stamp=STAMP)
        row = fence.judge(self.repo, rec["id"], "true-catch", by="gerard", stamp=STAMP,
                          hit=_WO["id"], note="already banked as a work-order")
        self.assertEqual(row["id"], "FV-20260817-01")
        self.assertEqual(row["target"], rec["id"])
        with self.assertRaises(fence.FenceError):
            fence.judge(self.repo, rec["id"], "sort-of", by="gerard", stamp=STAMP)
        with self.assertRaises(fence.FenceError):
            fence.judge(self.repo, "FP-nope", "true-catch", by="gerard", stamp=STAMP)

    def test_the_ledger_survives_a_corrupt_line(self):
        fence.advise(self.repo, "a reconstruction probe", site="t", stamp=STAMP)
        with (self.repo / fence.LEDGER).open("a", encoding="utf-8") as fh:
            fh.write("{not json\n")
        self.assertEqual(len(fence.ledger_rows(self.repo)), 1)


class RateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = _fixture_repo(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_landed_order_a_probe_named_counts_as_caught(self):
        fence.advise(self.repo, "a reconstruction probe before authoring, advisory in "
                     "the dispatch path", site="t", stamp=STAMP)
        rep = fence.false_negative_report(self.repo, [_WO["id"]])
        self.assertEqual([c["id"] for c in rep["caught"]], [_WO["id"]])
        self.assertEqual(rep["missed"], [])
        self.assertEqual(rep["false_negative_rate"], 0.0)

    def test_a_landed_order_no_probe_named_is_a_false_negative(self):
        fence.advise(self.repo, "a reconstruction probe before authoring",
                     site="t", stamp=STAMP)
        rep = fence.false_negative_report(self.repo, [_WO["id"], _OTHER["id"]])
        self.assertEqual(rep["missed"], [_OTHER["id"]])
        self.assertEqual(rep["false_negative_rate"], 0.5)

    def test_an_empty_denominator_gives_no_rate_rather_than_a_perfect_score(self):
        rep = fence.false_negative_report(self.repo, [])
        self.assertIsNone(rep["false_negative_rate"])
        self.assertIn("undefined, not zero", rep["rate_note"])

    def test_the_report_counts_the_judgements_and_banks_only_with_a_stamp(self):
        rec = fence.advise(self.repo, "a reconstruction probe before authoring, "
                           "advisory in the dispatch path", site="t", stamp=STAMP)
        fence.judge(self.repo, rec["id"], "true-catch", by="gerard", stamp=STAMP,
                    hit=_WO["id"])
        unbanked = fence.false_negative_report(self.repo, [_WO["id"]])
        self.assertEqual(unbanked["judged"]["true-catch"], 1)
        self.assertNotIn("id", unbanked)
        self.assertEqual(len(fence.ledger_rows(self.repo)), 2)
        banked = fence.false_negative_report(self.repo, [_WO["id"]], stamp=STAMP)
        self.assertEqual(banked["id"], "FR-20260817-01")
        self.assertEqual(len(fence.ledger_rows(self.repo)), 3)


class HouseRulesCase(unittest.TestCase):
    """The two rules that bind this machinery: no clock reads, and no blocking."""

    CLOCK_CALLS = {("datetime", "now"), ("datetime", "utcnow"), ("datetime", "today"),
                   ("date", "today"), ("time", "time"), ("time", "time_ns"),
                   ("os", "times")}

    def _clock_calls(self, path: Path):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                owner = node.func.value
                name = owner.id if isinstance(owner, ast.Name) else (
                    owner.attr if isinstance(owner, ast.Attribute) else "")
                if (name, node.func.attr) in self.CLOCK_CALLS:
                    found.append(f"{name}.{node.func.attr} at line {node.lineno}")
        return found

    def test_the_machinery_reads_no_clock(self):
        for rel in ("src/laplace/engine/reconstruction_fence.py",
                    "scripts/reconstruction_fence.py"):
            self.assertEqual(self._clock_calls(ROOT / rel), [],
                             f"{rel} must take timestamps through an explicit stamp")

    def test_advise_reports_a_broken_root_instead_of_raising(self):
        rec = fence.advise(ROOT / "no-such-directory-here", "anything", site="t")
        self.assertEqual(rec["hits"], [])
        self.assertIn("banked", rec)

    def test_a_read_only_ledger_does_not_break_the_advisory_caller(self):
        tmp = Path(tempfile.mkdtemp())
        try:
            _fixture_repo(tmp)
            (tmp / "corpus_friction" / "fence_probes.jsonl").mkdir()  # not a file
            rec = fence.advise(tmp, "a reconstruction probe", site="t", stamp=STAMP)
            self.assertIn("no row", rec["banked"])
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class DispatchWiringCase(unittest.TestCase):
    """The hook in pipeline/dispatch.py: a report on the record, nothing more."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["LAPLACE_STATE"] = str(Path(self._tmp.name) / "_state")

    def tearDown(self):
        os.environ.pop("LAPLACE_STATE", None)
        self._tmp.cleanup()

    def test_a_compiled_dispatch_carries_the_fence(self):
        from laplace.pipeline import dispatch
        out = dispatch.compile_dispatch("def:reconstruction-fence",
                                        "build the reconstruction fence probe",
                                        "derive", None, None)
        self.assertNotIn("error", out)
        self.assertIn("fence", out)
        self.assertEqual(out["fence"]["retrieval"], "lexical")
        self.assertIn("no stamp", out["fence"]["banked"])
        self.assertTrue(any(h["id"] == "WO-20260812-reconstruction-fence"
                            for h in out["fence"]["hits"]),
                        "the fence should name its own work-order from this goal")

    def test_the_fence_changes_no_prompt_byte(self):
        from laplace.pipeline import dispatch
        out = dispatch.compile_dispatch("def:reconstruction-fence",
                                        "build the reconstruction fence probe",
                                        "derive", None, None)
        core = dispatch._compile_dispatch_core("def:reconstruction-fence",
                                               "build the reconstruction fence probe",
                                               "derive", None, None)
        # the packet spine: the AIM block above the core, and - where the task class
        # has rows - the METHODS block TRAILING it (the methods fibre, WO-20260820;
        # repositioned below the core so nothing comes between the AIM fence and the
        # stage's own opening line). Both minted before the fence runs; the fence
        # itself must still add nothing.
        expected = (dispatch._aim_head_fence(out["composed_head"])
                    + "\n\n" + core["prompt"])
        if out.get("methods"):
            expected += "\n\n" + dispatch._methods_fence(out["methods"])
        self.assertEqual(out["prompt"], expected)
        self.assertNotIn("fence-probe", out["prompt"])

    def test_the_hook_banks_nothing_into_the_live_ledger(self):
        from laplace.pipeline import dispatch
        before = len(fence.ledger_rows(ROOT))
        dispatch.compile_dispatch("def:reconstruction-fence", "a probe", "derive",
                                  None, None)
        self.assertEqual(len(fence.ledger_rows(ROOT)), before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
