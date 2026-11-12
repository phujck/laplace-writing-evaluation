"""The close boundary: authored source survives failure and precedes exact publication.

The renderer and close/journal/receipt code run against a temporary repository. Only the
expensive upfold process is substituted with a publisher fixture; cold recovery is a
separate acceptance scenario and is never inferred from these focused regressions.
"""
import importlib.util
import json
from pathlib import Path

import pytest

from laplace.engine import close_beats, handoff_render

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts/sewup.py"
_SPEC = importlib.util.spec_from_file_location("sewup_publication_test", _SCRIPT)
close = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(close)

ARTIFACTS = (
    ".self_graded.json", "SELF_GRADED_INDEX.md", "SELF_SHARD_INDEX.md",
    ".meaning_tree.json", ".self_embeddings.json", ".metric_M.npz",
    ".metric_M.receipt.json", ".metric_pairs.json",
    ".meaning_vectors.f32.npy", ".meaning_vectors.index.json",
    ".self_record_floor.jsonl",
)


@pytest.fixture
def isolated_close(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "HANDOFF.md").write_text(
        "# Current handoff\n\n## NEXT SESSION AIM\nOld aim.\n\n"
        "## System map\nLaplace owns the lifecycle; Atlas owns reconstruction.\n")
    (root / "contract").mkdir()
    # Realistic unresolved history must survive; ordinary close has no predecessor dependency.
    (root / "contract/custody_mode.jsonl").write_text('{"mode":"OFF"}\n')
    (root / "contract/historical_holder.json").write_text('{"holder":"unretirable-old-session"}')
    monkeypatch.setattr(close, "ROOT", root)
    monkeypatch.setattr(close, "require_system_runtime", lambda root: {"fixture": True})
    real_render = handoff_render.render_close
    monkeypatch.setattr(handoff_render, "render_close", lambda root, **kwargs:
                        real_render(root, scratch=tmp_path / "preview", **kwargs))
    executed = []

    def execute(name, *, worker_flags, **_kwargs):
        executed.append(name)
        close._configure_globals(worker_flags)
        return {**close._typed_step_result(close._step_fns()[name]()), "seconds": 0.0}

    monkeypatch.setattr(close, "_execute_step", execute)
    yield root, executed
    close._configure_globals([])


def publisher(monkeypatch, root, *, mode="published"):
    def run(command, *, env, **_kwargs):
        assert command[0] == str(root / "scripts/laplace-python")
        inputs = json.loads(env["LAPLACE_REEMBED_INPUTS_JSON"])
        assert "HANDOFF.md" in inputs
        dated = next(path for path in inputs if path.startswith("SESSION_HANDOFF_"))
        assert "Tested the trivial change; next reader should recover it." in (root / dated).read_text()
        assert all(close._file_digest(root / path) == digest for path, digest in inputs.items())
        if mode == "failed":
            return 1, "upfold refused: metric evaluation identity mismatch"
        if mode == "no_receipt":
            return 0, "process completed without publication"
        artifacts = {}
        for path in ARTIFACTS:
            (root / path).write_text("fixture semantic generation\n")
            artifacts[path] = close._file_digest(root / path)
        record = {"schema_version": "laplace.publication/1", "published": True,
                  "artifacts": artifacts, "absent_artifacts": [
                      ".self_isometries.npz", ".learned_keywords.json", ".escalate_briefs.json"],
                  "input_signature": {"sources": inputs}}
        if mode == "missing_source":
            record["input_signature"]["sources"] = {}
        elif mode == "tampered":
            (root / ".self_graded.json").write_text("different generation")
        elif mode == "source_changed":
            (root / dated).write_text("changed during publication")
        return 0, "LAPLACE_PUBLICATION=" + json.dumps(record)
    monkeypatch.setattr(close, "_run", run)


AUTHORED = "Tested the trivial change; next reader should recover it."


def test_default_close_publishes_authored_checkpoint_with_custody_off(isolated_close, monkeypatch):
    root, executed = isolated_close
    from laplace.representation import custody_mode
    monkeypatch.setattr(custody_mode, "is_off", lambda *_a: pytest.fail("default custody gate retired"))
    publisher(monkeypatch, root)
    assert close.main(["--authored-text", AUTHORED]) == 0
    assert executed == ["handoff", "reembed"]
    receipt = close_beats.read_close_receipt(root)
    assert receipt and receipt["status"] == "PUBLISHED"
    assert receipt["successor_consumption"] == "UNVERIFIED"
    assert receipt["checkpoint"] == receipt["publication"]["input_signature"]["sources"]
    assert (root / "contract/historical_holder.json").read_text() == '{"holder":"unretirable-old-session"}'
    live_handoff = (root / "HANDOFF.md").read_text()
    assert "## System map\nLaplace owns" in live_handoff
    assert AUTHORED in live_handoff
    assert "scripts/laplace-python scripts/wake.py --health" in live_handoff
    assert "No established publication boundary yet" not in live_handoff
    assert live_handoff.index(AUTHORED) < live_handoff.index("**Open account:**")
    from laplace.engine import self_corpus
    aim = self_corpus._first_section(live_handoff, "NEXT SESSION AIM")
    next_text = self_corpus._next_from_aim(aim[1])
    assert AUTHORED in next_text and "**Open account:**" not in next_text


def test_explicit_full_metric_reaches_publication_without_running_full_suite(isolated_close, monkeypatch):
    root, executed = isolated_close
    publisher(monkeypatch, root)
    original = close._run
    commands = []
    def record(command, **kwargs):
        commands.append(command)
        return original(command, **kwargs)
    monkeypatch.setattr(close, "_run", record)
    assert close.main(["--full-metric", "--authored-text", AUTHORED]) == 0
    assert executed == ["handoff", "reembed"]
    assert len(commands) == 1 and commands[0][-1] == "--full-metric"
    assert close_beats.read_close_receipt(root)["status"] == "PUBLISHED"


@pytest.mark.parametrize("mode", ["failed", "no_receipt", "missing_source", "tampered", "source_changed"])
def test_failed_publication_keeps_checkpoint_and_previous_receipt(isolated_close, monkeypatch, mode):
    root, executed = isolated_close
    previous = '{"previous":"accepted receipt must not advance"}\n'
    (root / close.CLOSE_RECEIPT).write_text(previous)
    publisher(monkeypatch, root, mode=mode)
    assert close.main(["--authored-text", AUTHORED]) == 1
    assert executed == ["handoff", "reembed"]
    assert (root / close.CLOSE_RECEIPT).read_text() == previous
    dated = next(root.glob("SESSION_HANDOFF_*.md"))
    if mode != "source_changed":
        assert AUTHORED in dated.read_text()
    journal = [json.loads(line) for line in (root / "contract/journal.jsonl").read_text().splitlines()]
    assert journal[-1]["record"] == "act_end" and journal[-1]["status"] == "fail"


def test_empty_authorship_preserves_draft_and_refuses_upfold(isolated_close, monkeypatch):
    root, executed = isolated_close
    monkeypatch.setattr(close, "_run", lambda *_a, **_kw: pytest.fail("upfold ran without authorship"))
    assert close.main(["--authored-text", "   "]) == 1
    assert executed == ["handoff"]
    assert list(root.glob("SESSION_HANDOFF_*.md"))
    assert not (root / close.CLOSE_RECEIPT).exists()


def test_handoff_only_is_a_checkpoint_and_preview_never_upfolds(isolated_close, monkeypatch):
    root, executed = isolated_close
    monkeypatch.setattr(close, "_run", lambda *_a, **_kw: pytest.fail("preview launched upfold"))
    assert close.main(["--dry-run", "--authored-text", AUTHORED]) == 0
    assert not list(root.glob("SESSION_HANDOFF_*.md"))
    assert not (root / close.CLOSE_RECEIPT).exists()
    executed.clear()
    assert close.main(["--only", "handoff", "--authored-text", AUTHORED]) == 0
    assert executed == ["handoff"]
    assert not (root / close.CLOSE_RECEIPT).exists()


def test_failed_explicit_diagnostic_does_not_discard_authored_work(isolated_close, monkeypatch):
    root, executed = isolated_close
    publisher(monkeypatch, root, mode="failed")
    monkeypatch.setattr(close, "step_suite", lambda: {"pass": False, "detail": "real regression"})
    assert close.main(["--with-suite", "--authored-text", AUTHORED]) == 1
    assert executed == ["suite", "handoff", "reembed"]
    assert AUTHORED in next(root.glob("SESSION_HANDOFF_*.md")).read_text()
    assert not (root / close.CLOSE_RECEIPT).exists()


@pytest.mark.parametrize("value", [None, [], {}, {"schema_version": "laplace.publication/1", "published": True}])
def test_malformed_or_empty_publication_is_never_proof(value):
    assert close._publication_matches(value) is False


def test_wake_projection_distinguishes_prior_publication_from_new_failure(isolated_close, monkeypatch):
    root, _ = isolated_close
    publisher(monkeypatch, root)
    assert close.main(["--authored-text", AUTHORED]) == 0
    previous = (root / close.CLOSE_RECEIPT).read_bytes()
    from laplace.core.records import journal
    act = journal.act_begin("sewup-close", ["handoff", "reembed"], root=root)
    journal.act_end(act, "fail", summary="close_status=PUBLICATION_FAILED; publication_complete=False", root=root)
    projection = close_beats.close_projection(root)
    assert projection["publication"]["status"] == "RECORDED"
    assert projection["publication"]["semantic_freshness"] == "UNVERIFIED"
    assert projection["latest_attempt"]["status"] == "FAIL"
    assert projection["latest_attempt"]["close_status"] == "PUBLICATION_FAILED"
    assert len(json.dumps(projection)) < 1000
    assert (root / close.CLOSE_RECEIPT).read_bytes() == previous


@pytest.mark.parametrize("contents", [None, b"not JSON\n", b"x" * 70000 + b'\n{"record":"act_end","act_id":"sewup-close-old","status":"pass"}\n'])
def test_close_projection_cannot_inherit_pass_from_absent_or_incomplete_tail(tmp_path, contents):
    if contents is not None:
        (tmp_path / "contract").mkdir()
        (tmp_path / "contract/journal.jsonl").write_bytes(contents)
    projection = close_beats.close_projection(tmp_path)
    assert projection["publication"]["status"] == "UNKNOWN"
    assert projection["latest_attempt"]["status"] == "UNKNOWN"
    assert projection["journal_tail"]["bytes"] <= 65536


# ---- wave 13, close-hygiene: the re-handoff of the stale source_publication input, proven on a temporary root ----
# The live recipe is evidence/WRITING_TAKEOVER_2026-11-05/frontend/redesign/wave13/close-hygiene/recipe/
# rehandoff_source_publication.py. A temporary root with a Work of the same shape stands in for the live Work ledger
# (never opened here); the publication itself needs a GPU, so only its pure owner steps run: prepare and merge.

_RECIPE_RELATIVE = ("evidence/WRITING_TAKEOVER_2026-11-05/frontend/redesign/wave13/close-hygiene/recipe/"
                    "rehandoff_source_publication.py")


def _recipe():
    here = Path(__file__).resolve().parents[1]
    for base in (here, Path("/home/phujck/VScodeProjects/laplace")):
        path = base / _RECIPE_RELATIVE
        if path.is_file():
            spec = importlib.util.spec_from_file_location("rehandoff_recipe", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    pytest.fail("the re-handoff recipe is not in this tree or the main tree: " + _RECIPE_RELATIVE)


def test_rehandoff_makes_the_stale_currentness_input_current_without_a_review(tmp_path, monkeypatch):
    import copy
    import hashlib
    from laplace.engine import source_kernel_input as E
    from laplace.representation import source_publication as P
    from laplace.work import (owner_discovery as O, project_work as W, project_work_review as R,
                              source_contracts as SC, source_kernel as K)

    recipe = _recipe()
    root, operator = tmp_path, O.owned_workspace("sdk")
    declaring = "src/laplace/representation/source_publication.py"
    other = "src/laplace/engine/source_kernel_input.py"
    (root / "p").mkdir()
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{"name": "p", "kind": "general", "project_dir": "p"}]}))
    (root / declaring).parent.mkdir(parents=True)
    (root / declaring).write_bytes(Path(P.__file__).read_bytes())
    (root / other).parent.mkdir(parents=True)
    (root / other).write_bytes(b'"""A second declared input."""\n')
    binding = {"owner": "domain.representation", "operation": "source_publication", "consumer": K.CONSUMER,
               "segments": ["currentness"]}
    W.task("p", {"id": "w", "title": "Publisher meaning", "goal": "Retained declaration",
                 "review_obligations": [{"id": "ob", "label": "Publisher declaration", "required": False, "scope": "source",
                                         "inputs": [declaring, other], "source_contract": binding}]}, root)
    real = SC.providers

    def old_edition():
        # the declaration as the 28 October handoff retained it: another wording of the one segment
        def provider():
            value = copy.deepcopy(P.source_contract())
            value["segments"]["currentness"] = {**value["segments"]["currentness"], "edition": "before the close carry"}
            return value
        provider.__module__ = P.source_contract.__module__
        return tuple(provider if item is P.source_contract else item for item in real())

    def pinned():
        return {path: "sha256:" + hashlib.sha256((root / path).read_bytes()).hexdigest() for path in (declaring, other)}

    pins = pinned()
    monkeypatch.setattr(SC, "providers", old_edition)
    first = R.record("p", {"id": "w", "phase": "handoff", "request_id": "first-handoff", "pins": pins,
                           "expected_work_revision": W._task_revision(W._tasks("p", root)["w"]),
                           "object": {"kind": "source"}}, root)
    # The live Work's shape: an ACCEPT review of that handoff, a synthesis, and the Work done (obligation not required).
    revision = lambda: W._task_revision(W._tasks("p", root)["w"])
    review = R.record("p", {"id": "w", "phase": "review", "request_id": "first-review", "handoff_id": first["phase"]["id"],
                            "obligation_id": "ob", "verdict": "ACCEPT", "pins": pins, "expected_work_revision": revision()}, root)
    R.record("p", {"id": "w", "phase": "synthesis", "request_id": "first-synthesis", "expected_work_revision": revision(),
                   "consumes": [first["phase"]["id"], review["phase"]["id"]]}, root)
    tasks = W._tasks("p", root)
    W.transition("p", {"id": "w", "status": "done", "evidence": [declaring], "summary": "done",
                       "expected_work_scope_revision": W._work_basis(tasks, "w")[0]["scope_revision"],
                       "expected_work_status_revision": W._standing_revision(tasks["w"])}, root)
    assert W._tasks("p", root)["w"]["status"] == "done"
    selection = {"namespace": "p", "work_id": "w", "handoff_id": first["phase"]["id"], "obligation_id": "ob"}
    held = first["phase"]["source_contracts"]["ob"]
    request = {"reference": SC.reference(held["owner"], held["operation"], held["version"]),
               "selection": selection, "segments": ["currentness"]}
    old = K.prepare_publication_inputs(root, operator, [request])
    parent = {lid: copy.deepcopy(leaf["projection"]) for lid, leaf in old["frame"]["leaves"].items()}
    monkeypatch.setattr(SC, "providers", real)
    # The change that moved the declaration also moved a pinned file's bytes (the close compares meaning only then).
    (root / other).write_bytes((root / other).read_bytes() + b"# the close carry landed\n")
    pins = pinned()

    # The live fault: the declaration moved, the retained basis did not. The close labels the row STALE and a
    # fresh selection refuses it.
    (lid, state), = K.validate_publication_inputs(root, operator, old["packet"], retained=parent)["frame"]["currentness"].items()
    assert state["state"] == "STALE" and state["changed_segments"] == ["currentness"]
    assert [item["path"] for item in state["moved"]] == [other]
    with pytest.raises(ValueError, match="SOURCE_KERNEL_SOURCE_STALE"):
        K.validate_publication_inputs(root, operator, old["packet"])

    # No fresh review comes first: the new handoff is recorded on a done, reviewed Work and selected without one.
    kinds = lambda: [row["phase"] for row in W._tasks("p", root)["w"]["phases"]]
    assert kinds() == ["handoff", "review", "synthesis"]
    monkeypatch.setattr(P, "current", lambda _root: {"mode": "ordinary-full-deposit", "publication_handle": "sha256:" + "a" * 64})
    plan = recipe.run(root, project="p", work="w", obligation="ob", handoff_request="second-handoff",
                      commit_request="second-commit", apply=False)
    assert plan["apply"] is False and plan["handoff_payload"]["pins"] == pins
    assert kinds() == ["handoff", "review", "synthesis"], "the plan wrote nothing"
    done = recipe.run(root, project="p", work="w", obligation="ob", handoff_request="second-handoff",
                      commit_request="second-commit", apply=True, out=tmp_path / "out")
    phases = [row for row in W._tasks("p", root)["w"]["phases"] if row["phase"] == "handoff"]
    assert kinds() == ["handoff", "review", "synthesis", "handoff"] and W._tasks("p", root)["w"]["status"] == "done"
    assert done["handoff"]["status"] == "RECORDED" and phases[1]["id"] == done["handoff"]["phase_id"] != first["phase"]["id"]
    assert phases[1]["actor"] == {"actor": "author", "role": "producer", "origin": "human"}
    assert phases[1]["pins"] == pins and phases[1]["source_contracts"]["ob"]["version"] != held["version"]
    facet = R.facet(W._tasks("p", root)["w"], root)
    assert facet["handoff"]["id"] == phases[1]["id"], "the Work's review projection now reads the new handoff, unreviewed"
    assert done["prepared"]["state"] == "PREPARED"
    commit = json.loads((tmp_path / "out" / "commit.json").read_text())
    assert commit == done["commit"] and commit["action"] == "commit" and commit["request_id"] == "second-commit"
    (row,) = commit["prepared"]["inputs"]
    assert row["node_id"] == lid and row["request"]["selection"]["handoff_id"] == phases[1]["id"]

    # The selected commit replaces that one row (same node id), and the next close reads it CURRENT.
    fresh = K.validate_publication_inputs(root, operator, commit["prepared"])["frame"]
    assert fresh["currentness"][lid]["state"] == "CURRENT"
    replaced = {name for name, leaf in fresh["leaves"].items() if parent.get(name) != leaf["projection"]}
    assert replaced == {lid}
    merged = K.merge_publication_inputs(root, operator, old["packet"], commit["prepared"], replaced)
    assert [item["request"]["selection"]["handoff_id"] for item in merged["inputs"]] == [phases[1]["id"]]
    carry_parent = {name: leaf["projection"] for name, leaf in fresh["leaves"].items()}
    closed = K.validate_publication_inputs(root, operator, merged, retained=carry_parent)["frame"]
    assert closed["currentness"][lid]["state"] == "CURRENT"
    assert E.counts(closed["currentness"]) == {"current": 1, "carried": 0, "stale": 0, "unknown": 0}

    # A replay of the same recipe is the owner's REUSED, not a second handoff.
    again = recipe.run(root, project="p", work="w", obligation="ob", handoff_request="second-handoff",
                       commit_request="second-commit", apply=True)
    assert again["handoff"] == {"status": "REUSED", "phase_id": phases[1]["id"]}
    assert kinds() == ["handoff", "review", "synthesis", "handoff"]
