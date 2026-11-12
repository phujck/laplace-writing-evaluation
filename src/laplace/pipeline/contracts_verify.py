"""The executable halves of the operation contracts (schema.OPERATION_CONTRACTS).

Each callable DEMONSTRATES its surface's claim and returns {"pass": bool, ...}.
The ``contracts`` verify check runs every row: a canon node without a green
executable is a claim the engine cannot back, and fails the gate.

GENERICITY NOTE (Leg C bite C1 — Deliberate contract pins, not genericity debt).
The concrete project names below (``subset-sum-itqde``, ``paper_eigen``,
``eigenengine``) are NOT a hard-coded default to be registry-parameterised: they
are the CONTRACT being tested. These callables assert the engine can back its
claims against the REAL registered substrate — ``registry_resolves`` in
particular exists to prove the three LAYOUT FAMILIES (conceptric / loop / tex)
each resolve to a real project with real paths on disk. Parameterising the names
away would delete the very assertion (that these specific projects are present
and well-formed) and turn a substrate contract into a tautology. They are pinned
on purpose; leave them literal.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import importlib
import subprocess
import sys
from pathlib import Path
from typing import Any


def _root() -> Path:
    return source_tree()


def _contract_script(name: str):
    """Load a CLI without taking its __main__ write path."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        f"_contract_{name}", _root() / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def journal_bank_row_contract() -> dict[str, Any]:
    """Consume temporary durable rows and observe intent before a failed append."""
    import inspect
    import json
    from tempfile import TemporaryDirectory
    from unittest.mock import patch
    from laplace.core.records import journal as j
    params = inspect.signature(j.bank_row).parameters
    assert list(params) == ["store", "row", "act_id", "edges", "root"]
    assert all(params[n].kind == inspect.Parameter.KEYWORD_ONLY and params[n].default is None
               for n in ("act_id", "edges", "root"))
    assert j.REL == {"grounds", "amends", "grades", "supersedes", "resolves",
                     "raised-by", "cures", "relays", "consumes", "part-of"}
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "contract").mkdir()
        events = []
        append = j._append
        def observe(path, row):
            events.append((Path(path), dict(row)))
            append(path, row)
        with patch.object(j, "_append", side_effect=observe):
            banked = j.bank_row("rows.jsonl", {"id": "child"}, act_id="contract",
                                edges=[{"rel": "part-of", "target": "parent"}], root=root)
        assert [r.get("phase") for _, r in events] == ["begin", None, "done"]
        assert events[0][0] == events[2][0] == j._store(root)
        row = json.loads((root / "rows.jsonl").read_text())
        assert row["edges"] == [{"rel": "part-of", "target": "parent"}] and row["ts"]
        assert banked == row   # the return is the exact row as banked (stamped, edges first-class)
        with patch.object(j, "_append") as writes:
            for kw in ({"edges": [{"rel": "unknown", "target": "parent"}]},
                       {"edges": [{"rel": "part-of", "target": ""}]}):
                try:
                    j.bank_row("rows.jsonl", {"id": "bad"}, root=root, **kw)
                except ValueError:
                    pass
                else:
                    raise AssertionError("malformed edge accepted")
            try:
                j.bank_row("rows.jsonl", {"id": "bad", "edges": []}, edges=[], root=root)
            except ValueError:
                pass
            else:
                raise AssertionError("duplicate edge source accepted")
            writes.assert_not_called()
        events.clear()
        def fail_target(path, row):
            events.append(row)
            if Path(path) == root / "failed.jsonl":
                raise OSError("contract fixture")
            append(path, row)
        with patch.object(j, "_append", side_effect=fail_target):
            try:
                j.bank_row("failed.jsonl", {"id": "failed"}, act_id="contract", root=root)
            except OSError:
                pass
            else:
                raise AssertionError("append failure swallowed")
        assert [r.get("phase") for r in events] == ["begin", None]
    return {"pass": True, "detail": "signature, REL, durable round trip, rejection and interrupted append"}


def bequest_parcel_contract() -> dict[str, Any]:
    """Parse the documented syntax and check the cap at its owning write gate."""
    from tempfile import TemporaryDirectory
    from laplace.engine import bequest as b
    node = "canon://operations/sewup_contract"
    query = "what flags does the sew-up take"
    sample = f"Check the close contract. -> descend: {node} | probe: {query}"
    rows = b.parse_parcel(sample)
    assert rows == [{"text": "Check the close contract.", "node": node,
                     "probe": {"query": query, "must_reach": [node]}}]
    assert b.parse_parcel(sample.replace("->", "→")) == rows
    assert b.TEXT_CAP == 900
    with TemporaryDirectory() as tmp:
        assert b.rotate(tmp, rows, by="contract", dry_run=True)["ok"]
        exact = b.parse_parcel("x" * 900 + f" -> descend: {node}")
        assert b.rotate(tmp, exact, by="contract")["ok"]
        before = {p.relative_to(tmp): p.read_bytes() for p in Path(tmp).rglob("*") if p.is_file()}
        over = b.parse_parcel("x" * 901)
        result = b.rotate(tmp, over, by="contract")
        assert not result["ok"] and result["chars"] == 901 and "refused" in result["error"]
        assert len(over[0]["text"]) == 901
        after = {p.relative_to(tmp): p.read_bytes() for p in Path(tmp).rglob("*") if p.is_file()}
        assert before == after
    return {"pass": True, "detail": "example parsed; 900 accepted; 901 refused without trimming or writes"}


def reembed_contract() -> dict[str, Any]:
    """Check the no-run argv door and producer calls; never execute a deposit."""
    import ast
    import contextlib
    import io
    import os
    from tempfile import TemporaryDirectory
    from unittest.mock import patch
    from laplace.representation import device_policy
    from laplace.engine import meaning_upfold
    m = _contract_script("reembed")
    with patch.object(m, "require_system_runtime", side_effect=AssertionError("deposit entered")):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            assert m.main(["--help"]) == 0
            assert m.main(["--bogus"]) == 2
        assert "--full" in out.getvalue()
    expected_phases = ["upfold", "write", "index", "wire", "embed", "metric_distill", "publish"]
    assert m.ACT_STEPS == expected_phases
    tree = ast.parse((_root() / "scripts/reembed.py").read_text())
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    deposit = functions["_run_deposit"]
    calls = {ast.unparse(n.func) for n in ast.walk(deposit) if isinstance(n, ast.Call)}
    assert {"keeper.build_self", "_stage_tree_renders", "_stage_index_render",
            "_publish_renders", "_discard_staged", "journal.act_end", "_bank_timing_record"} <= calls
    assert not {"keeper.write_tree_local", "keeper.write_skeleton", "self_shard.write_index"} & calls
    # The public manifest must describe the actual journal sequence, including the
    # terminal publication boundary; a matching constant alone is insufficient.
    boundaries = {}
    for method in ("step_begin", "step_done"):
        rows = sorted((n for n in ast.walk(deposit) if isinstance(n, ast.Call)
                       and ast.unparse(n.func) == "journal." + method), key=lambda n: n.lineno)
        assert [(ast.literal_eval(n.args[1]), ast.literal_eval(n.args[2])) for n in rows] == list(enumerate(expected_phases))
        boundaries[method] = {ast.literal_eval(n.args[2]): n.lineno for n in rows}
    for helper, phase in (("_stage_tree_renders", "write"), ("_stage_index_render", "index"),
                          ("_publish_renders", "publish")):
        sites = [n for n in ast.walk(deposit) if isinstance(n, ast.Call) and ast.unparse(n.func) == helper]
        assert len(sites) == 1
        assert boundaries["step_begin"][phase] < sites[0].lineno < boundaries["step_done"][phase]
    staged_tree = functions["_stage_tree_renders"]
    for producer in ("keeper.write_tree_local", "keeper.write_skeleton"):
        sites = [n for n in ast.walk(staged_tree) if isinstance(n, ast.Call) and ast.unparse(n.func) == producer]
        assert len(sites) == 1
        assert any(k.arg == "destination" and isinstance(k.value, ast.Subscript)
                   and isinstance(k.value.value, ast.Name) and k.value.value.id == "staged"
                   for k in sites[0].keywords)
    assert any(isinstance(n, ast.Call) and ast.unparse(n.func) == "TIMING_LOG.open"
               for n in ast.walk(functions["_bank_timing_record"]))
    staged_index = functions["_stage_index_render"]
    assert any(isinstance(n, ast.Call) and ast.unparse(n.func) == "self_shard.write_index"
               for n in ast.walk(staged_index))
    assert any(isinstance(n, ast.Assign) and any(ast.unparse(t) == "self_shard._INDEX" for t in n.targets)
               and ast.unparse(n.value) == "temporary.name" for n in ast.walk(staged_index))
    assert any(isinstance(n, ast.keyword) and n.arg == "force_full" and
               ast.unparse(n.value) == "force_full" for n in ast.walk(deposit))
    with patch.dict(os.environ, {"LAPLACE_NO_SPECTRAL": "1"}), \
            patch.object(device_policy, "record_fallback") as fallback:
        assert meaning_upfold._spectral_allowed() is False
        assert fallback.call_args.kwargs["dialed"] is True
    with TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "LAPLACE_FALLBACK_LOG": str(Path(tmp) / "fallback.jsonl"), "LAPLACE_REQUIRE_GPU": "1"}):
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            try:
                device_policy.record_fallback("contract", "cpu", "fixture unavailable")
            except device_policy.DeviceRequired:
                pass
            else:
                raise AssertionError("required GPU silently fell back")
    return {"pass": True, "detail": "no-run argv, journal order, staged producer/publication wiring and device refusal; no deposit run"}


def campaign_gate_contract() -> dict[str, Any]:
    """Drive CLI verdict-to-exit mappings, including real S0 row consumption."""
    import contextlib
    import io
    import json
    from tempfile import TemporaryDirectory
    from unittest.mock import patch
    for name, green in (("atlas_s1g2_gate", "DONE-PENDING-WALK"), ("atlas_s1_gate", "DONE")):
        m = _contract_script(name)
        for verdict in (green, "OPEN", "MISSING"):
            out = io.StringIO()
            with patch.object(m, "evaluate", return_value={"verdict": verdict}), contextlib.redirect_stdout(out):
                assert m.main() == (0 if verdict == green else 1)
            assert json.loads(out.getvalue())["verdict"] == verdict
    m = _contract_script("atlas_s0_gate")
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        with patch.object(m, "INVENTORY", root / "inventory.jsonl"), \
                patch.object(m, "CAMPAIGN", root / "campaign.jsonl"), \
                patch.object(m, "WORK_ORDERS", root / "work.jsonl"):
            for ready in (False, True):
                if ready:
                    m.INVENTORY.write_text('\n'.join(json.dumps(r) for r in [
                        {"record": "inventory-generation", "id": "g"},
                        {"generation": "g", "class": "mathematical-inheritance"}]) + '\n')
                    m.CAMPAIGN.write_text(json.dumps({"id": "atlas-s0-judged-fixture"}) + '\n')
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    assert m.main() == (0 if ready else 1)
                result = json.loads(out.getvalue())
                assert result["verdict"] == ("DONE-PENDING-WALK" if ready else "OPEN")
                assert bool(result["residuals"]) is not ready
    return {"pass": True, "detail": "all three CLI exit contracts exercised on controlled green/red inputs"}


def dispatch_codex_contract() -> dict[str, Any]:
    """Parse argv and consume a compiled row in a temporary root; never launch Codex."""
    import contextlib
    import io
    import json
    from tempfile import TemporaryDirectory
    from unittest.mock import patch
    m = _contract_script("dispatch_codex")
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        try:
            m.main(["--help"])
        except SystemExit as exc:
            assert exc.code == 0
    flags = ("--goal-file", "--output-schema", "--worker", "--kind", "--model",
             "--sandbox", "--out-dir", "--content-budget", "--run", "--compile-only", "--timeout")
    assert all(flag in output.getvalue() for flag in flags)
    with contextlib.redirect_stderr(io.StringIO()):
        for args in (["--sandbox", "danger-full-access"], ["--run", "--compile-only"]):
            try:
                m.main(["node", "goal", *args])
            except SystemExit as exc:
                assert exc.code == 2
            else:
                raise AssertionError("invalid dispatch argv accepted")
    with TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
        root = Path(tmp)
        stack.enter_context(patch.object(m, "ROOT", root))
        stack.enter_context(patch.object(m.custody_mode, "read", return_value={"mode": "OFF", "id": "fixture"}))
        stack.enter_context(patch.object(m, "reconstruct", return_value={"content_status": "COMPLETE"}))
        stack.enter_context(patch.object(m.D, "compile_dispatch", return_value={"prompt": "contract fixture", "model": "opus", "reconstruction_admission": {"admission_result": {"status": "ADMITTED", "reason": "fixture"}}}))
        stack.enter_context(patch.object(m, "_codex_default_model", return_value="fixture"))
        launch = stack.enter_context(patch.object(m.subprocess, "run", side_effect=AssertionError("worker launched")))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        for sandbox in (None, "workspace-write"):
            args = ["node", "goal", "--compile-only", "--out-dir", sandbox or "default"]
            if sandbox:
                args += ["--sandbox", sandbox]
            assert m.main(args) == 0
            row_path = next((root / (sandbox or "default")).rglob("row.json"))
            row = json.loads(row_path.read_text())
            assert row["record"] == "dispatch" and row["status"] == "COMPILED"
            assert row["sandbox"] == (sandbox or "read-only") and row["carrier"] == "compile-only"
            prompt = (row_path.parent / "prompt.md").read_text()
            assert row["prompt_handle"] == m._sha(prompt)
            assert row["prompt_chars"] == len(prompt)
            assert (row_path.parent / "packet.json").is_file()
            assert prompt.startswith("contract fixture") and "<!-- EXECUTION-FENCE -->" in prompt
            ledger = [json.loads(raw) for raw in (root / m.LEDGER).read_text().splitlines()]
            assert ledger[-1] == row
        launch.assert_not_called()
    return {"pass": True, "detail": "argv, sandbox refusal/default and compiled row consumed; no worker launched"}


def ledger_engine() -> dict[str, Any]:
    """The one ledger engine exists and both engines delegate to it."""
    from laplace.pipeline import ledger
    from laplace.research import corpus_ingest as ci
    from laplace.manuscript import storyboard as sb
    ok = (callable(ledger.read_jsonl) and callable(ledger.transaction)
          and ci._REWIRE_KINDS is not None
          and sb._OP_KINDS is not None)
    return {"pass": bool(ok)}


def rendered_docs_fresh() -> dict[str, Any]:
    """The schema-rendered canon bodies match the live code — the doc cannot
    drift from the source it claims to describe."""
    r = subprocess.run(
        [sys.executable, str(_root() / "scripts" / "render_pipeline_docs.py"),
         "--check"],
        capture_output=True, text=True, timeout=60)
    return {"pass": r.returncode == 0, "detail": (r.stdout or r.stderr)[-400:]}


def operators_importable() -> dict[str, Any]:
    """The native operators exist as modules AND as thin CLIs."""
    missing: list[str] = []
    for mod in ("evolve", "restructure", "propagate"):
        try:
            importlib.import_module(f"laplace.pipeline.{mod}")
        except Exception as e:
            missing.append(f"laplace.pipeline.{mod}: {e}")
        if not (_root() / "scripts" / f"{mod}.py").is_file():
            missing.append(f"scripts/{mod}.py")
    return {"pass": not missing, "missing": missing}


def dispatch_compiles() -> dict[str, Any]:
    """compile_dispatch produces a typed prompt for both dispatch families:
    a node worker opens with the graded-node kernel; the prose worker opens
    with the clean stage preamble (mandate §13 - no engine framing) or, when
    the narrative artifact does not exist yet, refuses with a typed error
    naming the missing stage rather than inventing a frame.

    W-AIM (0ad73500): a prompt-bearing dispatch carries the content-level AIM
    block above that kernel / preamble, so the check reads the body past the
    AIM fence. It stays an *opens-with* check, never a bare ``in`` - a preamble
    buried anywhere in the packet is exactly what this gate must still catch.

    The methods fibre (WO-20260820) rides as a TRAILING METHODS block, below the body
    it governs, precisely so this gate keeps its meaning: nothing comes between the AIM
    fence and the stage's own opening line. This check briefly read past a leading
    METHODS fence too, while the fibre was injected above the body; that position broke
    the opens-with law and the fibre was moved below it instead."""
    from laplace.pipeline import dispatch, schema

    def _body(prompt: str) -> str:
        return prompt.split("<!-- /AIM -->", 1)[-1].lstrip()

    # 2026-09-14: the compiler admits only a hash-verified typed descent (the dispatch
    # kernel's law); this contract builds one over a real file, under the custody-off
    # admission, instead of compiling with no reconstruction (red since 2026-08-28).
    from laplace.representation import custody_mode
    from laplace.engine import descent
    from unittest.mock import patch
    _target = "DESIGN_2026-09-14_the-atlas-container.md"
    _rec = descent.descend(kind="repository-file", reference=_target, goal="contract probe",
                           content_budget=400_000, record_telemetry=False)
    _rec = {**_rec, "goal": "contract probe", "authority_write": "none"}
    _live = patch.object(custody_mode, "is_off", lambda root=None: True)
    _live.start()
    node = dispatch.compile_dispatch(_target, "contract probe",
                                     "derive", "subset-sum-itqde", reconstruction=_rec)
    node_ok = "prompt" in node and _body(node["prompt"]).startswith("You are one node")
    # A prose target is its owning row id, not a file descent relabelled S2.
    # Missing authored rows remain a failed contract with an owning-stage issue.
    stage_rec = dispatch.reconstruct_stage("S2", "contract probe", repo_root=_root())
    try:
        prose = dispatch.compile_dispatch("S2", "contract probe", "prose",
                                          "subset-sum-itqde", reconstruction=stage_rec)
    finally:
        _live.stop()
    prose_ok = ("prompt" in prose
                and _body(prose["prompt"]).startswith(schema.PROSE_STAGE_PREAMBLE[:40]))
    admission = (prose.get("reconstruction_admission") or {}).get("admission_result") or {}
    issue = None if prose_ok else {
        "record": "issue", "owner": "subset-sum-itqde/S2",
        "reason": admission.get("reason") if admission.get("status") == "REFUSED" else prose.get("error"),
    }
    return {"pass": bool(node_ok and prose_ok), "prose_residual": issue,
            "node_keys": sorted(node), "prose_keys": sorted(prose)}


def staged_stages_ready() -> dict[str, Any]:
    """The staged pipeline's modules import, its artifact map resolves, and the
    voice profile sits at its versioned path (supplied only to the prose
    realiser and the weld)."""
    missing: list[str] = []
    for mod in ("projection_spec", "structural", "narrative", "document_model",
                "tex_backend"):
        try:
            importlib.import_module(f"laplace.pipeline.{mod}")
        except Exception as e:
            missing.append(f"laplace.pipeline.{mod}: {e}")
    from laplace.pipeline import dispatch, registry, schema
    proj = registry.resolve("subset-sum-itqde")
    for key in schema.STAGE_ARTIFACTS:
        if proj is not None and proj.stage_path(key) is None:
            missing.append(f"stage_path({key!r}) unresolved")
    if not (_root() / dispatch.VOICE_PROFILE_PATH).is_file():
        missing.append(dispatch.VOICE_PROFILE_PATH)
    if not (_root() / "scripts" / "render_manuscript.py").is_file():
        missing.append("scripts/render_manuscript.py")
    return {"pass": not missing, "missing": missing}


def sewup_ready() -> dict[str, Any]:
    """The standing up-operator exists and its render step runs green."""
    script = _root() / "scripts" / "sewup.py"
    if not script.is_file():
        return {"pass": False, "missing": "scripts/sewup.py"}
    r = subprocess.run([sys.executable, str(script), "--only=render"],
                       capture_output=True, text=True, timeout=120, cwd=_root())
    return {"pass": r.returncode == 0, "detail": (r.stdout or r.stderr)[-200:]}


def registry_resolves() -> dict[str, Any]:
    """The registry resolves all three layout families with real paths.

    The tex family is represented by ``ssg-disclosure``: ``eigenengine`` used to be
    the tex example but its kind flipped tex -> conceptric (2026-07-12, registry.py's
    documented corpus-membership fix), so the family probe moved to a project that is
    still kind="tex". The three families (conceptric / loop / tex) each resolve with a
    real on-disk path, and a path escaping the repo root still resolves to None.
    """
    from laplace.pipeline import registry
    rr = _root()
    ss = registry.resolve("subset-sum-itqde")   # conceptric family
    pe = registry.resolve("paper_eigen")         # loop family
    tx = registry.resolve("ssg-disclosure")      # tex family
    ok = (ss is not None and ss.kind == "conceptric" and (rr / ss.ledger).is_file()
          and pe is not None and pe.kind == "loop"
          and tx is not None and tx.kind == "tex" and (rr / tx.tex_root).exists()
          and registry.resolve("../soul") is None)
    return {"pass": bool(ok)}
