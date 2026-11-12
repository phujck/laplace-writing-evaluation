"""The in-app dispatch door, end to end, with the provider stubbed at the boundary.

ONE parent turn plans a dispatch, launches two worker children and one judge child, and
consumes their returns through the bounded project-artifact reader; the dispatch row reaches
`done` with those returns pinned as its evidence.  Nothing here reaches a model, a network or
the host's login: `WritingTurn` is replaced at the one boundary `_start_turn`'s own `run()`
reads it from, and the stub drives the REAL door (`writing_tools.execute`) with each child's
own turn id, so what is proved is the door's behaviour and not the stub's.

The shape of the proof is `tests/test_session_contract.py:834`'s: hermetic, the provider
stubbed where the path actually reads it, no reliance on the host.  S2's own lesson is kept:
the fixture's catalogue is stubbed at BOTH capability boundaries, so an assertion can name
the exact model the table resolved instead of merely "not the other one".
"""
from __future__ import annotations
from work_read_helpers import guarded_transition, standing_payload

import hashlib
import io
import json
import sys
from pathlib import Path

import pytest

from laplace.work import project_work
from laplace.native import tools as writing_tools
from laplace.projects import artifacts as writing_artifacts
from laplace.writing import session_reads
from laplace.writing import turn_admission
from laplace.writing import records as writing_records
from laplace.writing import turn_jobs
from laplace.writing import turn_admission, turn_jobs
from laplace.pipeline import schema
from laplace.writing import provider as writing_provider

#: the real provider class, captured before any fixture binds the stub at the runtime lookup: a test that
#: exercises the provider's own pure capability table (control_capabilities) reads it from here, never from
#: writing_provider after the fixture, and never constructs it (object.__new__ only).
REAL_TURN = writing_provider.WritingTurn
assert REAL_TURN.__module__.startswith('laplace.')
from test_writing_operating import _project


CATALOGUE = {"providers": [{"id": "claude", "available": True, "models": [
    {"id": "haiku", "resolved_model": "claude-haiku-stub", "supports_effort": True,
     "efforts": ["low", "medium", "high"]},
    {"id": "sonnet", "resolved_model": "claude-sonnet-stub", "supports_effort": True,
     "efforts": ["low", "medium", "high"]},
    {"id": "opus", "resolved_model": "claude-opus-stub", "supports_effort": True,
     "efforts": ["low", "medium", "high"]}]}]}


def _return_document(packet: str, goal: str, input_path: str, input_token: str,
                     output: str) -> str:
    """A return the one validator accepts: `scripts/distil.py check-return`'s schema, with
    no vague word, no placeholder and an input digest that pins the bytes on disk."""
    return json.dumps({
        "schema_version": "laplace.packet-return/1", "packet": packet, "role": "build",
        "status": "COMPLETE", "goal": goal,
        "inputs": [{"path": input_path, "sha256": input_token}],
        "source": {"branch": "s3/dispatch-build", "base_commit": "0" * 40,
                   "candidate": "1" * 40, "candidate_parent": "0" * 40,
                   "candidate_tree": "2" * 40, "worktree": "/tmp/stub-worktree"},
        "output": output, "files_written": [output],
        "summary": "The child read its one declared input through the door and wrote this "
                   "return at the path its packet named.",
        "most_important": ["the child's own turn consumed its input through read_artifact "
                           "and wrote its return through store_artifact"],
        "scripted_check": {"command": "scripts/laplace-python -m pytest "
                                      "tests/test_writing_dispatch.py -q",
                           "exit_code": 0, "output_tail": "1 passed"},
        "residuals": []}, ensure_ascii=False)


class _StubTurn:
    """Stands exactly where `authoring_surface.WritingTurn` stands, and drives the real door.

    A worker child reads its one declared input and writes its return; a judge child writes
    its judgement.  Each call goes through `writing_tools.execute` with THAT CHILD's turn id,
    which is the whole point: a child's authority is its own turn's, not the parent's.
    """

    instructions: dict = {}
    observed: list = []

    def __init__(self, root, provider, model, effort, native_id, emit, mode, *,
                 project, logical_turn_id, native_source_paths=None, session_id=None):
        self.root, self.emit, self.mode = Path(root), emit, mode
        self.project, self.turn_id, self.session_id = project, logical_turn_id, session_id
        self.model, self.effort, self.provider = model, effort, provider
        self.inference_started = False
        self.native_id = native_id
        self.operating_brief = None
        self.supports_effort = True

    def run(self, prompt: str) -> dict:
        from laplace.writing import operating as writing_operating
        workspace = writing_operating.session_workspace(self.session_id)
        self.emit({"type": "session", "native_id": "stub-" + str(self.session_id),
                   "provider": self.provider, "model": self.model,
                   "process": {"cwd": str(workspace), "tools": [], "mcp": "ok"}})
        self.inference_started = True
        # Children run in their own threads, so this row is built LOCALLY and appended once:
        # an `observed[-1]` was another child's row under concurrency, which is the very
        # contention the design's section 7.2 says to measure rather than reason about.
        row = {"turn_id": self.turn_id, "session_id": self.session_id, "mode": self.mode,
               "model": self.model, "effort": self.effort, "cwd": str(workspace),
               "prompt_chars": len(prompt), "calls": []}
        failures = []
        for operation, payload in _StubTurn.instructions.get(self.session_id, []):
            try:
                result = writing_tools.execute(self.root, self.project, self.mode, operation,
                                               dict(payload), turn_id=self.turn_id)
            except Exception as exc:                     # recorded, never swallowed
                failures.append({"operation": operation, "error": repr(exc)})
                continue
            row["calls"].append({"operation": operation, "ok": True,
                                 "token": result.get("revision") or result.get("sha256")})
        row["tool_failures"] = failures
        _StubTurn.observed.append(row)
        return {"status": "completed", "text": "wrote the return this packet declared",
                "native_id": "stub-" + str(self.session_id)}


@pytest.fixture
def tree(tmp_path, monkeypatch):
    import runtime_guard
    runtime_guard.arm(monkeypatch)   # fail-closed: no provider binary, shell, network or canonical state from here on
    _project(tmp_path)
    monkeypatch.setattr(writing_provider, "capabilities", lambda *a, **k: CATALOGUE)
    from laplace.writing import provider as _wp
    monkeypatch.setattr(_wp, "capabilities", lambda *a, **k: CATALOGUE)
    monkeypatch.setattr(writing_provider, "WritingTurn", _StubTurn)
    monkeypatch.setattr(writing_provider, "context_window_advertised", lambda *a, **k: None)   # the runtime lookup (turn_admission)
    monkeypatch.setattr(session_reads, 'context_window_advertised', lambda *a, **k: None)
    # The whole chain in ONE process, which is what makes this replay hermetic: a dispatched
    # child's turn is started in a DETACHED one-shot door host in operation
    # (`authoring_surface.start_turn`, the `_CHILD_HOST` branch), and a separate process would
    # see neither `_StubTurn` nor this catalogue and would reach the host's real `claude`.
    # The flag is the same one the host itself sets, so the stub stands exactly where the
    # host's own `start_turn` call does.  The detachment is proved on its own below, from the
    # argv captured at `subprocess.Popen`, and end to end by the stub rehearsal.
    monkeypatch.setattr(turn_jobs, "_CHILD_HOST", True)
    monkeypatch.setenv("LAPLACE_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("LAPLACE_GUARD_TESTS", str(Path(__file__).resolve().parent))
    monkeypatch.setenv("LAPLACE_GUARD_LOG", str(tmp_path / "guard-denials.jsonl"))
    _StubTurn.instructions, _StubTurn.observed = {}, []
    runtime_guard.assert_stub_bound()   # the actual runtime lookup is the stub before any child is admitted
    return tmp_path


def _settle(root: Path, children: list, timeout: float = 60.0) -> float:
    """Wait for every child's own turn to reach a saved terminal reply, and return how long.

    `launch_dispatch` returns STARTED, so a reader that asserts on a child's rows without
    waiting is asserting on a turn that has not happened -- which is the same mistake as
    reading terminal state out of a launch answer.  The wall time is reported because the
    design's section 7.2 asks for the fold's behaviour under a bounded fan-out to be
    MEASURED and not reasoned about.
    """
    import time
    started = time.monotonic()
    wanted = {child["turn_id"] for child in children}
    while time.monotonic() - started < timeout:
        replies = {row.get("turn_id") for row in _talk(root)
                   if row.get("record") == "writing-reply"}
        if wanted <= replies and all(job.get("done") for key, job in turn_jobs._JOBS.items() if key in wanted):
            return time.monotonic() - started
        time.sleep(0.05)
    raise AssertionError("children did not finish: %r" % (wanted - replies,))


def _talk(root: Path) -> list:
    path = root / "contract/talk.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _parent_turn(root: Path) -> tuple[str, str]:
    session = turn_admission.new_session(root, "book", "claude", "opus", "high")
    writing_records.bank(root, {"record": "writing-turn", "id": "WT-parent",
                                   "session_id": session["id"], "project": "book",
                                   "text": "Dispatch this job", "mode": "work",
                                   "provider_settings": {"provider": "claude",
                                                         "model": "opus", "effort": "high"}})
    return session["id"], "WT-parent"


def _plan(root: Path) -> dict:
    """Two worker packets and one judge, each with its own project-relative return path."""
    return {"schema_version": "laplace.dispatch-plan/1", "wave": "stub-replay",
            "goal": "read one input and return what it establishes", "fan_out_max": 3,
            "packets": [
                {"packet": "worker-a", "role": "worker", "scope": "project",
                 "return_path": "dispatch/worker-a.return.json",
                 "brief": "Read brief.md and write your return."},
                {"packet": "worker-b", "role": "worker", "scope": "project",
                 "return_path": "dispatch/worker-b.return.json",
                 "brief": "Read brief.md and write your return."},
                {"packet": "judge", "role": "judge", "scope": "project",
                 "return_path": "dispatch/judge.judgement.json",
                 "brief": "Read both returns and judge them."}]}


def test_one_parent_launches_two_workers_and_a_judge_and_consumes_their_returns(tree):
    root = tree
    session_id, parent_turn = _parent_turn(root)

    # the one input every child is given, written through the door the children read it with
    brief = writing_tools.execute(root, "book", "work", "store_artifact",
                                  {"path": "dispatch/brief.md", "scope": "project",
                                   "before": None,
                                   "reason":"Retain the exact shared child input.",
                                   "content": "The input this dispatch's children read.\n"},
                                  turn_id=parent_turn)
    brief_token = brief["revision"]

    # 1. PLAN: the plan is a project artifact and the row names it in `evidence`.
    planned = writing_tools.execute(root, "book", "work", "dispatch_plan",
                                    {"title": "stub replay", "goal": _plan(root)["goal"],
                                     "path": "dispatch/plan.json", "plan": _plan(root)},
                                    turn_id=parent_turn)
    dispatch_id = planned["dispatch_id"]
    assert dispatch_id.startswith("WORK-")
    row = project_work._tasks("book", root)[dispatch_id]
    assert row["task_kind"] == "dispatch" and row["status"] == "open"
    assert row["section_ids"] == [] and row["evidence"] == [planned["plan_artifact"]]
    assert row["origin"] == "eigen:session"
    # NO new row kind: the plan's own row and its transition are project-work records.
    kinds = {json.loads(line)["record"] for line
             in (root / "corpus_friction/work_orders.jsonl").read_text().splitlines() if line.strip()}
    assert kinds <= {"project-work", "project-work-transition"}, kinds

    # 2. LAUNCH.  Each child's instructions are what its stub process will do through the
    # door: read the one input, then write the document its packet declared.
    launch_plan = _plan(root)
    children_by_packet = {}

    def _instruct(child):
        packet, path = child["packet"], child["return_path"]
        if packet == "judge":
            document = json.dumps({
                "schema_version": "laplace.packet-judgement/1", "packet": "worker-a",
                "round": 1, "max_rounds": 2, "accepted": True,
                "judged": {"candidate": "1" * 40, "review_checkout": "/tmp/stub-review-worktree"},
                "scripted_check": {"command": "scripts/laplace-python -m pytest "
                                              "tests/test_writing_dispatch.py -q",
                                   "exit_code": 0, "output_tail": "1 passed"},
                "checked": [{"item": "the worker wrote its return at the declared path",
                             "how": "read_artifact on that exact path through the door"}],
                "accepted_subsets": [{"id": "return", "status": "ACCEPTED",
                                  "finding": "the return is at the path the packet declared"}],
                "deficiencies": [],
                "own_observations": [{"command": "read_artifact dispatch/worker-a.return.json",
                                      "exit_code": 0,
                                      "output_tail": "laplace.packet-return/1"}]},
                ensure_ascii=False)
        else:
            document = _return_document(packet, launch_plan["goal"],
                                        str(writing_artifacts.resolve_path(root,"book","dispatch/brief.md")),
                                        brief_token, path)
        return [("read_artifact", {"path": "dispatch/brief.md", "scope": "project"}),
                ("store_artifact", {"path": path, "scope": "project", "before": None,
                                    "reason":"Return this packet's exact observed result.",
                                    "content": document})]

    # the session ids are only known after the launch, so the instructions are keyed by
    # packet first and re-keyed as each child opens: `launch_dispatch` opens the sessions in
    # the plan's own order, which is the order the packets are declared in.
    pending = {item["packet"]: _instruct(item) for item in launch_plan["packets"]}
    # the launch opens each child's session through the admission OWNER (dispatch_execution calls
    # turn_admission.new_session); the facade name is a one-way alias, so the key-by-session hook
    # stands on the owner and the alias is kept pointing at the same hook
    original_new_session = turn_admission.new_session

    def new_session(*args, **kwargs):
        opened = original_new_session(*args, **kwargs)
        if kwargs.get("packet"):
            _StubTurn.instructions[opened["id"]] = pending[kwargs["packet"]]
        return opened

    turn_admission.new_session = new_session
    try:
        started = writing_tools.execute(root, "book", "work", "dispatch_launch",
                                        {"id": dispatch_id}, turn_id=parent_turn)
    finally:
        turn_admission.new_session = original_new_session

    assert started["started"] is True and started["dispatch_id"] == dispatch_id
    assert [child["packet"] for child in started["children"]] == ["worker-a", "worker-b", "judge"]
    children_by_packet = {child["packet"]: child for child in started["children"]}
    # LAUNCHED IS in-progress: no status value was invented.
    assert project_work._tasks("book", root)[dispatch_id]["status"] == "in-progress"

    # 3. the children: their rows, their models and their own empty workspaces
    settled = _settle(root, started["children"])
    assert settled < 60.0, settled
    records = session_reads._records(root)
    for packet, child in children_by_packet.items():
        turn = records["turns"][child["turn_id"]]
        session = records["sessions"][child["session_id"]]
        assert turn["parent_turn_id"] == parent_turn, packet
        assert turn["dispatch_id"] == dispatch_id, packet
        assert session["dispatch_id"] == dispatch_id and session["packet"] == packet
        role = "judge" if packet == "judge" else "worker"
        # the model is the ROLE TABLE's, resolved through the one producer, never a literal
        expected = schema.role_model(role, "claude")
        assert session["model"] == expected["model"], (packet, session["model"])
        assert session["effort"] == expected["effort"], (packet, session["effort"])
        assert session["model_source"] == "tier-default" and session["tier"] == expected["tier"]
        assert session["role"] == ("review" if role == "judge" else "author")
        assert turn["mode"] == ("review" if role == "judge" else "work")
    # the parent's own turn row carries NEITHER member, so the two are what distinguish them
    assert "parent_turn_id" not in records["turns"][parent_turn]
    assert "dispatch_id" not in records["turns"][parent_turn]
    assert "dispatch_id" not in records["sessions"][session_id]

    # every child ran in its own empty directory, keyed by its own session id
    observed = {row["session_id"]: row for row in _StubTurn.observed}
    seen = set()
    for child in started["children"]:
        row = observed[child["session_id"]]
        assert row["cwd"].endswith(child["session_id"].replace("WS-", "WS-")), row["cwd"]
        assert not list(Path(row["cwd"]).iterdir()), row["cwd"]
        seen.add(row["cwd"])
        assert row["tool_failures"] == [], row
    assert len(seen) == 3, seen
    # ZERO tool failures anywhere, read from the bank and not from the stub's own tally
    banked = _talk(root)
    assert [row for row in banked if row.get("record") == "writing-tool-failure"] == []
    # each child banked its OWN binding row, with its own process observation
    bindings = {row["session_id"]: row for row in banked
                if row.get("record") == "writing-binding"}
    for child in started["children"]:
        assert bindings[child["session_id"]]["process"]["cwd"] == observed[child["session_id"]]["cwd"]

    # 4. STATUS: terminal state from the durable row and each child's own session.  The default
    # view is SMALL (declared: "Default view:status is small; ... view:detail child evidence
    # detail", bounded on 2026-10-12): bounded child rows and no fan-out.  The child's parent
    # and the dispatch's fan-out are child evidence, read through `view: detail`.
    status = writing_tools.execute(root, "book", "work", "dispatch_status",
                                   {"id": dispatch_id}, turn_id=parent_turn)
    assert status["status"] == "in-progress" and len(status["children"]) == 3
    assert "fan_out" not in status and "parent_turn_id" not in status["children"][0]
    for child in status["children"]:
        assert child["return_exists"] is True and child["state"] == "COMPLETE"
    detail = writing_tools.execute(root, "book", "work", "dispatch_status",
                                   {"id": dispatch_id, "view": "detail"}, turn_id=parent_turn)
    assert detail["status"] == "in-progress" and detail["fan_out"] == 3
    for child in detail["children"]:
        assert child["return_exists"] is True and child["state"] == "COMPLETE"
        assert child["parent_turn_id"] == parent_turn

    # 4b. S3 dispatch-pane: the SAME computation read by `project_work.state`, the project-
    # work pane's one source (`/work/state`, no new endpoint).  The judge's own return is a
    # `laplace.packet-judgement/1` document (declared above); its `accepted: True` is
    # surfaced as a VERDICT, derived from the already-hashed return bytes, never stored.
    pane_task = {t["id"]: t for t in project_work.state("book", root)["tasks"]}[dispatch_id]
    assert pane_task["dispatch"]["status"] == "in-progress"
    assert pane_task["dispatch"]["fan_out"] == 3
    assert pane_task["dispatch"]["children"] == detail["children"]
    assert pane_task["dispatch"]["verdicts"] == [
        {"packet": "judge", "judges": "worker-a", "accepted": True, "round": 1, "max_rounds": 2}]
    judge_child = next(c for c in pane_task["dispatch"]["children"] if c["packet"] == "judge")
    assert judge_child["verdict"] == pane_task["dispatch"]["verdicts"][0]
    worker_children = [c for c in pane_task["dispatch"]["children"] if c["packet"] != "judge"]
    assert all(c["self_status"] == "COMPLETE" and c["verdict"] is None for c in worker_children)
    assert pane_task["dispatch"]["cost"] == {
        "input_tokens": 0, "output_tokens": 0, "turns_replied": 3, "turns_total": 3}
    # dispatch_status's OWN detail view and the pane's projection agree field for field: one
    # function (project_work.dispatch_view), two readers; detail adds only the caller's
    # addressing and the parent's return contract.
    assert {k: v for k, v in detail.items()
            if k not in {"note", "read_receipt", "caller_turn_id", "parent_return_contract"}} == {
        "dispatch_id": dispatch_id, **pane_task["dispatch"]}
    assert detail["caller_turn_id"] == parent_turn

    # 4c. S3 dispatch-pane: a child turn is found WITH its parent through the History
    # projection's existing filter mechanism (`author_history.history`, the `row` key) --
    # a filter over rows the fold already walks, not a second query.
    from laplace.work import history as author_history
    scoped = author_history.history("book", {"row": dispatch_id}, root)
    scoped_turn_ids = {(item.get("conversation") or {}).get("turn_id") for item in scoped["items"]}
    assert parent_turn in scoped_turn_ids, scoped_turn_ids
    for child in started["children"]:
        assert child["turn_id"] in scoped_turn_ids, (child["packet"], scoped_turn_ids)
    # an unrelated activity item (the plan artifact's own store, on the parent's turn before
    # the dispatch existed) is NOT pulled in by an unrelated dispatch id
    assert author_history.history("book", {"row": "WORK-" + "0" * 32}, root)["items"] == []

    # 5. RETURNS: consumed through the bounded artifact reader, not a stream
    returns = writing_tools.execute(root, "book", "work", "dispatch_returns",
                                    {"id": dispatch_id}, turn_id=parent_turn)
    assert {item["packet"] for item in returns["returns"]} == set(children_by_packet)
    for item in returns["returns"]:
        assert item["return"]["exists"] is True
        document = json.loads(item["return"]["return"]["content"]) if False else json.loads(
            item["return"]["content"])
        assert document["schema_version"] in ("laplace.packet-return/1",
                                              "laplace.packet-judgement/1")

    # 6. Execution is terminal, but one judgement names only worker-a: worker-b has
    # no exact accepted coverage. Legacy v1 judgement remains readable, not upgraded.
    paths = [planned["plan_artifact"]] + [item["return"]["path"] for item in returns["returns"]]
    with pytest.raises(ValueError,match='per-worker review coverage'):
        writing_tools.execute(root, "book", "work", "task_status",
                              standing_payload("book", {"id": dispatch_id, "status": "done", "evidence": paths}, root),
                              turn_id=parent_turn)
    final = project_work._tasks("book", root)[dispatch_id]
    assert final["status"] == "in-progress"
    assert status['execution_state']=='COMPLETE' and status['review_state']=='UNVERIFIED'
    assert 'worker-b' in status['uncovered_workers']


def test_a_dispatched_child_proposes_and_the_parent_applies(tree):
    """The one guard this packet adds beside the review-mode refusal: the apply operation is
    refused for a turn whose row carries a `parent_turn_id`."""
    root = tree
    _, parent_turn = _parent_turn(root)
    child_session = turn_admission.new_session(root, "book", "claude", "", "",
                                                  model_role="worker",
                                                  dispatch_id="WORK-stub", packet="worker-a")
    writing_records.bank(root, {"record": "writing-turn", "id": "WT-child",
                                   "session_id": child_session["id"], "project": "book",
                                   "parent_turn_id": parent_turn, "dispatch_id": "WORK-stub",
                                   "text": "child", "mode": "work"})
    proposal={'edits':[{'file':'missing.tex','line_start':1,'line_end':1,
        'before':'Original source.','after':'Proposed source.'}]}
    with pytest.raises(ValueError, match="the parent applies"):
        writing_tools.execute(root, "book", "work", "apply_revision", {"proposal": proposal},
                              turn_id="WT-child")
    # the parent's own turn is refused for its own reason and NOT by this guard
    with pytest.raises(ValueError) as refused:
        writing_tools.execute(root, "book", "work", "apply_revision", {"proposal": proposal},
                              turn_id=parent_turn)
    assert "the parent applies" not in str(refused.value)


def test_a_plan_the_carrier_would_refuse_is_refused_before_anything_starts(tree):
    """`launch_dispatch`'s refusal half IS `dispatch_plan`'s validator, so these are refused
    at planning time with no row written and no child opened."""
    root = tree
    _, parent_turn = _parent_turn(root)
    good = _plan(root)

    def refuse(mutate, match):
        plan = json.loads(json.dumps(good))
        mutate(plan)
        with pytest.raises(ValueError, match=match):
            writing_tools.execute(root, "book", "work", "dispatch_plan",
                                  {"title": "t", "goal": "g", "path": "dispatch/p.json",
                                   "plan": plan}, turn_id=parent_turn)

    # no judge: the carrier's own UNREVIEWED-BUILDER / INDEPENDENT-REVIEW refusal
    refuse(lambda p: p.__setitem__("packets", p["packets"][:1]),
           "INDEPENDENT-REVIEW-AND-SYNTHESIS-REQUIRED|UNREVIEWED-BUILDER")
    refuse(lambda p: p.__setitem__("fan_out_max", 2), "exceed the plan's own declared")
    refuse(lambda p: p["packets"][0].__setitem__("model", "  "), "names its model or omits")
    from laplace.native.declarations import PayloadAdmissionError
    scope_plan=json.loads(json.dumps(good));scope_plan['packets'][0]['scope']='repository'
    with pytest.raises(PayloadAdmissionError) as scope_refusal:
        writing_tools.execute(root,'book','work','dispatch_plan',{
            'title':'t','goal':'g','path':'dispatch/p.json','plan':scope_plan},turn_id=parent_turn)
    assert scope_refusal.value.operation=='dispatch_plan'
    assert scope_refusal.value.response()['refused']['kind']=='shape'
    refuse(lambda p: p["packets"][0].__setitem__("return_path", "../escape.json"),
           "belong inside the selected project")
    refuse(lambda p: p["packets"][0].__setitem__("return_path", "main.tex"),
           "source, bibliography, or canonical-record operation")
    refuse(lambda p: p.__setitem__("schema_version", "something/else"),
           "laplace.dispatch-plan/1")
    # nothing was written and nothing was opened by any of those refusals
    assert project_work._tasks("book", root) == {}
    assert _StubTurn.observed == []


def test_a_dispatch_is_cancellable_and_a_child_cannot_award_verification(tree):
    """Two guards, both widened or kept rather than invented: `cancelled` was refused for
    every task_kind but `session-request` (project_work.py:324) and is now accepted for
    `dispatch`; `verified` stays refused outright for everything."""
    root = tree
    _, parent_turn = _parent_turn(root)
    planned = writing_tools.execute(root, "book", "work", "dispatch_plan",
                                    {"title": "t", "goal": "g", "path": "dispatch/p.json",
                                     "plan": _plan(root)}, turn_id=parent_turn)
    ident = planned["dispatch_id"]
    with pytest.raises(ValueError, match="verified requires"):
        guarded_transition("book", {"id": ident, "status": "verified"}, root)
    moved = guarded_transition("book", {"id": ident, "status": "cancelled"}, root)
    assert moved["status"] == "cancelled"
    assert project_work._tasks("book", root)[ident]["status"] == "cancelled"
    # an `execution` task is still refused, so the guard WIDENED and did not open
    other = project_work.task("book", {"title": "t", "goal": "g"}, root)
    with pytest.raises(ValueError, match="can be cancelled"):
        guarded_transition("book", {"id": other["id"], "status": "cancelled"}, root)


def test_a_dispatched_child_resolves_at_the_role_table_on_a_project_that_has_a_preference(tree):
    """The author's model law, observed in OPERATION and not only where no preference exists.

    `project_work.session_choice` consulted the project's SAVED session preference before the
    role table, so on a project whose author saved a model -- which the real project
    `writing-system-architecture` does -- a dispatched worker's and judge's model was that
    preference and only their effort came from `schema.role_model`.  That is the inheritance
    "a dispatched worker never inherits it" forbids: a project saved at the apex handed every
    child the apex.  `project_work.DISPATCHED_ROLES` now makes `session_choice` skip the
    preference for roles `worker` and `judge`, so the child's `model_source` is `tier-default`
    on a project that HAS one.  The test above covers a project with NONE; this one is the
    case that was wrong.
    """
    root = tree
    # the author's own preference for this project: the APEX, the model the law says a
    # dispatched worker must not inherit
    saved = project_work.session_preferences("book", {"provider": "claude", "model": "opus",
                                                      "effort": "high"}, root)
    assert saved["preferences"]["model"] == "opus"
    assert project_work.saved_preferences("book", root)["model"] == "opus"
    # the AUTHOR's own new conversation still gets his preference: the exception is the
    # dispatched roles and nothing else
    his = project_work.session_choice("book", {"provider": "claude"}, root)
    assert (his["model"], his["model_source"]) == ("opus", "project-preference")
    for role in project_work.DISPATCHED_ROLES:
        child = project_work.session_choice("book", {"provider": "claude"}, root, role=role)
        expected = schema.role_model(role, "claude")
        assert (child["model"], child["effort"]) == (expected["model"], expected["effort"]), role
        assert child["model_source"] == "tier-default" and child["tier"] == expected["tier"]
        assert child["model"] != "opus", role

    # and through the whole door, on the rows a reader actually sees
    _, parent_turn = _parent_turn(root)
    planned = writing_tools.execute(root, "book", "work", "dispatch_plan",
                                    {"title": "preference", "goal": "g",
                                     "path": "dispatch/plan.json", "plan": _plan(root)},
                                    turn_id=parent_turn)
    started = writing_tools.execute(root, "book", "work", "dispatch_launch",
                                    {"id": planned["dispatch_id"]}, turn_id=parent_turn)
    _settle(root, started["children"])
    records = session_reads._records(root)
    for child in started["children"]:
        session = records["sessions"][child["session_id"]]
        role = "judge" if child["packet"] == "judge" else "worker"
        assert session["model"] == schema.role_model(role, "claude")["model"]
        assert session["model_source"] == "tier-default", (child["packet"], session)


def test_a_dispatched_childs_turn_is_started_in_a_detached_process_of_its_own(tree,
                                                                              monkeypatch):
    """The child outlives the parent turn because it was never inside it.

    A turn is supervised by the process that started it (`_start_turn`'s own
    `threading.Thread`), and a dispatch is launched from a TOOL CALL, so a child started in
    the caller's process is supervised by the parent turn's stdio door adapter and dies with
    it: the stub chain measured writing-reply 1 of 4 when the parent returned the instant it
    had launched.  `start_turn` therefore starts a child in a one-shot host of its own with
    `start_new_session=True`, which is what `research_surface.py:1609` already does for a
    research run's supervisor.  The proof is the ARGV CAPTURED AT `subprocess.Popen` (S2's
    own shape for a process fact), plus the host's real entry point answering.
    """
    import subprocess as _sp
    root = tree
    _, parent_turn = _parent_turn(root)
    session = turn_admission.new_session(root, "book", "claude", "", "",
                                            model_role="worker", dispatch_id="WORK-stub",
                                            packet="worker-a")
    monkeypatch.setattr(turn_jobs, "_CHILD_HOST", False)
    seen = {}

    class _Host:
        pid = 4321

        def __init__(self, argv, **kwargs):
            seen["argv"], seen["kwargs"] = list(argv), kwargs
            self.stdin, self.stdout = io.StringIO(), io.StringIO(
                json.dumps({"turn_id": "WT-child-host", "session_id": session["id"]}) + "\n")

    monkeypatch.setattr(_sp, "Popen", _Host)
    jobs_before = set(turn_jobs._JOBS)      # module state outlives one test
    started = turn_admission.start_turn(root, {"project": "book",
                                                  "session_id": session["id"], "mode": "work",
                                                  "text": "the child's whole brief"},
                                           dispatch={"dispatch_id": "WORK-stub",
                                                     "parent_turn_id": parent_turn})
    assert started == {"turn_id": "WT-child-host", "session_id": session["id"],
                       "host_pid": 4321}
    assert seen["argv"] == [sys.executable, "-m", "laplace.native.tools", "--root", str(root),
                            "--project", "book", "--mode", "work", "--start-child-turn",
                            "--dispatch-id", "WORK-stub", "--parent-turn-id", parent_turn]
    assert seen["kwargs"]["start_new_session"] is True, seen["kwargs"]
    assert seen["kwargs"]["cwd"] == str(root)
    # nothing was started in THIS process: no job, no turn row, no provider
    assert set(turn_jobs._JOBS) == jobs_before and _StubTurn.observed == []
    assert [row["id"] for row in _talk(root)
            if row.get("record") == "writing-turn"] == [parent_turn]

    # and the host's own entry point exists and runs the door's real start_turn: with an
    # empty payload it is the ordinary refusal, printed as the host's one answer line
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    printed = []
    monkeypatch.setattr("builtins.print", lambda *a, **k: printed.append(a[0] if a else ""))
    assert writing_tools.main(["--root", str(root), "--project", "book",
                               "--start-child-turn"]) == 1
    assert json.loads(printed[-1])["error"].startswith("ValueError: Write a message first")


def test_a_packet_may_name_its_childs_model_and_the_projects_preference_still_loses(tree):
    """The author's law has two halves and both are observed on the rows.

    "A model the user names for a task overrides this" -- so a packet that names a model gets
    it, banked as `model_source` 'named' (the orchestrator's steer S4 of 2026-10-06 sets this
    order; the accepted contract refused a packet-named model outright, which left a real
    light-tier rehearsal impossible because `role_model` puts a worker at the standard tier).
    "A dispatched worker never inherits it" -- so the project's saved preference is not
    consulted either way, which is what the apex preference here shows.
    """
    root = tree
    project_work.session_preferences("book", {"provider": "claude", "model": "opus",
                                              "effort": "high"}, root)
    _, parent_turn = _parent_turn(root)
    plan = _plan(root)
    for packet in plan["packets"]:
        packet["model"], packet["effort"] = "haiku", "low"
    planned = writing_tools.execute(root, "book", "work", "dispatch_plan",
                                    {"title": "named", "goal": "g",
                                     "path": "dispatch/plan.json", "plan": plan},
                                    turn_id=parent_turn)
    started = writing_tools.execute(root, "book", "work", "dispatch_launch",
                                    {"id": planned["dispatch_id"]}, turn_id=parent_turn)
    _settle(root, started["children"])
    records = session_reads._records(root)
    for child in started["children"]:
        session = records["sessions"][child["session_id"]]
        assert (session["model"], session["effort"]) == ("haiku", "low"), child["packet"]
        assert session["model_source"] == "named" and session["tier"] == "light"
        assert session["model"] != "opus"
    assert project_work.saved_preferences("book", root)["model"] == "opus"


def test_a_bare_transition_leaves_the_rows_own_evidence_intact(tree):
    """The shared owner's cure, and the reason the dispatch door needed one.

    `_tasks` merges a task row and its transitions KEY BY KEY, and `transition` used to bank
    `"evidence": []` on every row where the caller named none, so ANY bare transition erased
    the task's evidence from the merged view -- for the dispatch that meant `launch_dispatch`
    moved the row to in-progress and `dispatch_status` then could not find the plan artifact
    the row had named.  The cure is at the owner: the key is omitted, so the transition says
    nothing about evidence instead of saying there is none.
    """
    root = tree
    made = project_work.task("book", {"title": "t", "goal": "g",
                                      "evidence": ["projects/book/dispatch/plan.json"]}, root)
    ident = made["id"]
    assert project_work._tasks("book", root)[ident]["evidence"] == [
        "projects/book/dispatch/plan.json"]
    moved = guarded_transition("book", {"id": ident, "status": "in-progress"}, root)
    assert "evidence" not in moved, moved
    assert project_work._tasks("book", root)[ident]["evidence"] == [
        "projects/book/dispatch/plan.json"]
    # a transition that DOES name evidence still writes it, and the merge takes the newer
    named = guarded_transition("book", {"id": ident, "status": "open",
                                             "evidence": ["projects/book/dispatch/b.json"]},
                                    root)
    assert named["evidence"] == ["projects/book/dispatch/b.json"]
    assert project_work._tasks("book", root)[ident]["evidence"] == [
        "projects/book/dispatch/b.json"]


def test_a_turn_request_cannot_make_itself_a_dispatched_child(tree, monkeypatch):
    """The judge's own round-2 probe, which is the payload the HTTP door hands `start_turn`.

    `POST /authoring/turn` passes the request body to `start_turn` verbatim
    (`authoring_surface.py` :3301 `data = start_turn(root, payload)`), and the child branch
    used to read `dispatch_id` straight off that body: a client of the local app could name a
    fabricated dispatch, get a DETACHED one-shot host per request, and bank writing-turn rows
    whose `parent_turn_id` and `dispatch_id` name nothing -- none of `launch_dispatch`'s
    refusals being on that path.  The two members are now the launcher's alone: they reach a
    turn only on the internal `dispatch` argument, and the door refuses a request that
    carries them BEFORE anything is started.  Proved the way the file proves a process fact:
    `subprocess.Popen` is replaced by something that records, and it is never reached.
    """
    import subprocess as _sp
    root = tree
    monkeypatch.setattr(turn_jobs, "_CHILD_HOST", False)
    spawned = []
    monkeypatch.setattr(_sp, "Popen", lambda *a, **k: spawned.append(a) or 1 / 0)

    probe = {"project": "no-such-project", "session_id": "WS-does-not-exist", "mode": "discuss",
             "text": "x", "dispatch_id": "WORK-fabricated-by-the-caller",
             "parent_turn_id": "WT-invented"}
    with pytest.raises(ValueError, match="cannot carry dispatch_id"):
        turn_admission.start_turn(root, probe)
    # the parent_turn_id half is refused on its own, so neither member is a way in
    with pytest.raises(ValueError, match="cannot carry parent_turn_id"):
        turn_admission.start_turn(root, {key: value for key, value in probe.items()
                                           if key != "dispatch_id"})
    # nothing was spawned, nothing was started, nothing was banked
    assert spawned == [] and _StubTurn.observed == []
    assert project_work._tasks("no-such-project", root) == {}
    assert [row for row in _talk(root) if row.get("record") == "writing-turn"] == []


def test_a_dispatch_at_its_fan_out_max_cannot_gain_another_child_through_the_door(tree,
                                                                                 monkeypatch):
    """The bound is the plan's and it is enforced in ONE place, so the door needs no copy.

    A real dispatch launched at its `fan_out_max` of 3 has three children; the only way to
    add a fourth would be a turn request naming its `dispatch_id`, and that request is
    refused as a shape, not re-judged against the plan.  So the dispatch's child count is
    whatever `launch_dispatch` allowed and nothing else, which is what "nothing may
    hand-set a dispatch's budget" has to mean in operation.
    """
    import subprocess as _sp
    root = tree
    _, parent_turn = _parent_turn(root)
    plan = _plan(root)
    assert plan["fan_out_max"] == len(plan["packets"]) == 3
    planned = writing_tools.execute(root, "book", "work", "dispatch_plan",
                                    {"title": "full", "goal": "g", "path": "dispatch/p.json",
                                     "plan": plan}, turn_id=parent_turn)
    ident = planned["dispatch_id"]
    started = writing_tools.execute(root, "book", "work", "dispatch_launch", {"id": ident},
                                    turn_id=parent_turn)
    _settle(root, started["children"])
    children = [row["id"] for row in _talk(root)
                if row.get("record") == "writing-turn" and row.get("dispatch_id") == ident]
    assert len(children) == 3

    # a fourth child through the door: the session is a real child session of THIS dispatch
    # and the parent turn is real, so only the door's own refusal stands in the way
    monkeypatch.setattr(turn_jobs, "_CHILD_HOST", False)
    spawned = []
    monkeypatch.setattr(_sp, "Popen", lambda *a, **k: spawned.append(a) or 1 / 0)
    extra = turn_admission.new_session(root, "book", "claude", "haiku", "low",
                                          model_role="worker", dispatch_id=ident,
                                          packet="worker-a")
    with pytest.raises(ValueError, match="dispatch_launch alone"):
        turn_admission.start_turn(root, {"project": "book", "session_id": extra["id"],
                                            "mode": "work", "text": "a fourth child",
                                            "dispatch_id": ident,
                                            "parent_turn_id": parent_turn})
    assert spawned == []
    assert [row["id"] for row in _talk(root)
            if row.get("record") == "writing-turn" and row.get("dispatch_id") == ident
            ] == children
    assert project_work._tasks("book", root)[ident]["status"] == "in-progress"
