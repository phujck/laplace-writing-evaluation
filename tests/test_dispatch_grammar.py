"""The ONE dispatch grammar (S0, 2026-10-04): one tier table, one return schema, one
judgement schema, one place each becomes a launcher's argument.

Before this wave the same facts lived in three vocabularies: ``WORKER_MODEL`` in Claude names
only (``src/laplace/pipeline/schema.py``), a ``MODEL`` literal plus inline ``BUILD_SCHEMA`` /
``JUDGE_SCHEMA`` in ``.claude/workflows/atlas-wave.js``, and whatever Codex root typed into
each ``collaboration.spawn_agent`` call. Each test below pins one of those joins shut.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

from laplace.pipeline import schema

ROOT = Path(__file__).resolve().parents[1]
PY = str(ROOT / "scripts" / "laplace-python")
DISTIL = str(ROOT / "scripts" / "distil.py")
FIXTURES = Path("/home/phujck/VScodeProjects/laplace/evidence/WRITING_JOINS_2026-10-04/S0/one-grammar/fixtures")
PLAN = Path("/home/phujck/VScodeProjects/laplace/evidence/WRITING_JOINS_2026-10-04/S0/plan.json")

#: What ``WORKER_MODEL`` was as a hand-written literal at af94b5e6e, kept here verbatim so a
#: change to the tier table that moved any worker's model or effort fails loudly.
LITERAL_WORKER_MODEL = {
    "derive": ("opus", "high"),
    "simulate": ("sonnet", "medium"),
    "figure": ("sonnet", "medium"),
    "mint": ("haiku", "low"),
    "prose": ("sonnet", "medium"),
    "structure": ("sonnet", "medium"),
    "narrative": ("sonnet", "medium"),
    "render": ("haiku", "low"),
}


def _distil(*args, expect: int | None = 0) -> str:
    out = subprocess.run([PY, DISTIL, *args], capture_output=True, text=True)
    if expect is not None:
        assert out.returncode == expect, (out.returncode, out.stdout[-2000:], out.stderr[-2000:])
    return out.stdout + out.stderr


def _load_distil():
    spec = importlib.util.spec_from_file_location("distil", ROOT / "scripts" / "distil.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("distil", mod)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------- the tier table

def test_worker_model_is_the_derived_literal():
    """``WORKER_MODEL`` is now a projection of ``WORKER_TIER`` through ``TIERS['claude']`` and
    must still be byte-identical to the literal it replaced - same keys, same order, same
    tuples - or its consumers (``pipeline/dispatch.py:1217``, ``pipeline_surface.py:1774``)
    silently change which model every worker kind runs at."""
    assert schema.WORKER_MODEL == LITERAL_WORKER_MODEL
    assert list(schema.WORKER_MODEL) == list(LITERAL_WORKER_MODEL)
    assert all(isinstance(v, tuple) and len(v) == 2 for v in schema.WORKER_MODEL.values())
    # a plain mutable dict: tests/test_dispatch_model_ceiling.py monkeypatches an item of it
    assert type(schema.WORKER_MODEL) is dict


def test_tier_table_is_the_one_holder():
    assert set(schema.TIERS) == {"deep", "standard", "light"}
    assert [schema.TIERS[t]["claude"] for t in ("light", "standard", "deep")] == list(schema.MODEL_RANK)
    assert schema.TIERS["deep"]["codex"] == "gpt-6.1-sol"
    assert schema.tier_model("standard", "codex") == "gpt-5.6-terra"
    assert schema.tier_model("light", "codex") == "gpt-6-luna"
    assert schema.tier_model("light") == "haiku"
    # the ceiling law still binds and is still enforced where it was
    assert schema.clamp_model(schema.tier_model("deep")) == schema.MAX_MODEL


@pytest.mark.parametrize("args", [("nope",), ("deep", "gemini")])
def test_tier_model_refuses_what_it_cannot_resolve(args):
    """A mistyped tier or provider RAISES rather than falling back to the apex: the same rule
    ``pin_model`` already applies to a mistyped pin (``schema.py`` pin_model)."""
    with pytest.raises(ValueError):
        schema.tier_model(*args)


# ------------------------------------------------------------------------------ the schemas

def test_both_schemas_are_files_and_the_only_holder():
    mod = _load_distil()
    known = mod._schemas()
    assert set(known) == {"laplace.packet-return/1", "laplace.packet-return/2",
                          "laplace.packet-judgement/1", "laplace.packet-judgement/2"}
    for sid, (path, doc) in known.items():
        assert Path(path).parent == ROOT / "profiles" / "workflows"
        assert doc["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert doc["additionalProperties"] is False
        # every declared field carries its one-line description
        assert all("description" in p for p in doc["properties"].values()), sid
    # no Python module and no launcher carries a copy of either schema
    for holder in (ROOT / "scripts" / "distil.py", ROOT / "src" / "laplace" / "pipeline" / "workflow.py"):
        assert '"$schema"' not in holder.read_text(encoding="utf-8"), holder


def test_check_return_accepts_the_fixture_return_and_judgement():
    assert "CLEAN" in _distil("check-return", str(FIXTURES / "return.json"))
    assert "CLEAN" in _distil("check-return", str(FIXTURES / "verdict.r1.json"))


def test_check_return_refuses_an_acceptance_without_an_observation(tmp_path):
    """The carrier's rule at ``src/laplace/pipeline/workflow.py:811-813``, applied to a file:
    an acceptance with no successful command of the judge's own is not an acceptance."""
    doc = json.loads((FIXTURES / "verdict.r1.json").read_text(encoding="utf-8"))
    doc["accepted"] = True
    doc["deficiencies"] = []
    doc["own_observations"] = [{**doc["own_observations"][0], "exit_code": 1}]
    bad = tmp_path / "no-observation.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    out = _distil("check-return", str(bad), expect=1)
    assert "acceptance-without-observation" in out


def test_check_return_refuses_an_acceptance_with_deficiencies(tmp_path):
    doc = json.loads((FIXTURES / "verdict.r1.json").read_text(encoding="utf-8"))
    doc["accepted"] = True
    doc["own_observations"] = [{**doc["own_observations"][0], "exit_code": 0}]
    doc["deficiencies"] = [{"id": "D1", "item": "scripts/distil.py:1", "problem": "wrong",
                            "evidence": "read it", "done_looks_like": "right"}]
    bad = tmp_path / "accepted-with-deficiencies.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    out = _distil("check-return", str(bad), expect=1)
    assert "acceptance-with-deficiencies" in out


def test_check_return_refuses_a_vague_or_empty_return(tmp_path):
    """``cmd_check``'s two prose rules, the ones a JSON Schema cannot express."""
    doc = json.loads((FIXTURES / "return.json").read_text(encoding="utf-8"))
    doc["summary"] = "the appropriate organ was extended as needed"
    bad = tmp_path / "vague.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    out = _distil("check-return", str(bad), expect=1)
    assert "vague-word" in out

    # emptiness is the schema's business and the schema states it
    doc = json.loads((FIXTURES / "return.json").read_text(encoding="utf-8"))
    doc["most_important"] = []
    bad = tmp_path / "empty.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    assert "schema: most_important" in _distil("check-return", str(bad), expect=1)

    # what a schema with minLength 1 cannot see: a required field filled with a placeholder
    doc = json.loads((FIXTURES / "return.json").read_text(encoding="utf-8"))
    doc["summary"] = "n/a"
    bad = tmp_path / "placeholder.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    assert "empty-field: summary is a placeholder" in _distil("check-return", str(bad), expect=1)

    # and the same rule at depth: the fields a reader trusts most are nested ones
    doc = json.loads((FIXTURES / "return.json").read_text(encoding="utf-8"))
    doc["scripted_check"]["output_tail"] = "n/a"
    bad = tmp_path / "nested-placeholder.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    assert "empty-field: scripted_check/output_tail is a placeholder" in _distil(
        "check-return", str(bad), expect=1)


def test_check_return_refuses_a_complete_status_carrying_residuals(tmp_path):
    doc = json.loads((FIXTURES / "return.json").read_text(encoding="utf-8"))
    doc["status"] = "COMPLETE"
    doc["residuals"] = [{"clause": "c", "failing_command": "f", "smallest_change": "s"}]
    bad = tmp_path / "complete-with-residuals.json"
    bad.write_text(json.dumps(doc), encoding="utf-8")
    assert "schema: residuals" in _distil("check-return", str(bad), expect=1)


# ----------------------------------------------------------------------------- the launchers

def test_launch_args_resolves_tiers_and_embeds_both_schemas():
    mod = _load_distil()
    args = json.loads(_distil("launch-args", str(PLAN)))
    assert args["wave"] and args["programme"] == "WRITING-JOINS-2026-10-04"
    models = args["models"]
    assert models["one-grammar"]["build"] == {"tier": "deep", "model": schema.tier_model("deep"),
                                              "effort": "high"}
    assert models["launcher"]["build"]["model"] == schema.tier_model("standard")
    # a judge is never cheaper than the work it judges
    assert models["launcher"]["judge"]["model"] == schema.tier_model("deep")
    assert models["synthesis"]["synthesis"]["model"] == schema.tier_model("deep")
    # the wave's row bank is an agent too, so its model is resolved here like every other role's:
    # without it the launcher would need a literal of its own for the one phase that is not a packet
    assert models["bank"]["bank"] == {"tier": "light", "model": schema.tier_model("light"),
                                      "effort": "low"}
    # both schemas ride as content, so the JavaScript holds no schema literal
    for key, sid in (("return", mod._current_schema_id(mod.RETURN_FAMILY)),
                     ("judgement", mod._current_schema_id(mod.JUDGEMENT_FAMILY))):
        assert args["schemas"][key]["$id"] == sid
        assert args["schemas"][key]["additionalProperties"] is False
        assert args["schemas"][key + "_path"].endswith(".schema.json")
    # the per-packet fields a launcher needs, and no brief text. ``judge`` and ``judge_first``
    # joined the set with the launcher packet (S0 stage 2): they are the plan's own judgement
    # switches, and a launcher that cannot see them judges a packet the plan exempted and re-runs
    # a builder the plan retired. Both are projections of the plan, not new state.
    for agent in args["agents"]:
        expected = {"label", "stage", "feeds", "output", "check", "judge",
                    "judge_first", "judge_sample", "judge_focus"}
        if agent.get("check"): expected.add("requires_command_check")
        assert set(agent) == expected
        assert agent["judge"] is True and agent["judge_first"] is False


def test_launch_args_projects_the_plans_judgement_switches():
    """``judge: false`` and ``judge_first`` reach the launcher as booleans or not at all."""
    distil = _load_distil()
    plan = {"agents": [{"label": "unjudged", "judge": False, "output": "/tmp/a.md"},
                       {"label": "already-built", "judge_first": True, "output": "/tmp/b.md"},
                       {"label": "ordinary", "output": "/tmp/c.md"}],
            "judge_default": {"sample": 4, "focus": "f"}}
    by = {a["label"]: a for a in distil._launch_agents(plan)}
    assert by["unjudged"]["judge"] is False
    assert by["already-built"]["judge"] is True and by["already-built"]["judge_first"] is True
    assert by["ordinary"]["judge"] is True and by["ordinary"]["judge_first"] is False
    # the plan's judge_default still supplies the sample and focus of a packet with no judge block
    assert by["ordinary"]["judge_sample"] == 4 and by["ordinary"]["judge_focus"] == "f"


def test_spawn_args_is_the_observed_codex_tuple():
    """The shape Codex root used in its 2026-10-03 rollout: a task name, a model from the
    CODEX column of the one tier table, a reasoning effort, no forked turns, and a message
    that names the brief command, the return path and the schema."""
    args = json.loads(_distil("spawn-args", str(PLAN), "one-grammar", "--role", "build"))
    assert set(args) == {"task_name", "model", "reasoning_effort", "fork_turns", "message"}
    assert args["task_name"].endswith("-one-grammar-build")
    assert args["model"] == schema.TIERS["deep"]["codex"] == "gpt-6.1-sol"
    assert args["model"] not in schema.MODEL_RANK          # never a Claude name on the Codex leg
    assert args["reasoning_effort"] == "high"
    assert args["fork_turns"] == "none"
    assert "distil.py brief" in args["message"]
    assert "one-grammar/return.json" in args["message"]
    assert "packet-return.v2.schema.json" in args["message"]
    assert "check-return" in args["message"]

    judge = json.loads(_distil("spawn-args", str(PLAN), "launcher", "--role", "judge", "--round", "2"))
    assert judge["model"] == schema.TIERS["deep"]["codex"]  # judge_default tier, not the packet's
    assert "launcher/verdict.r2.json" in judge["message"]
    assert "packet-judgement.v2.schema.json" in judge["message"]


def test_brief_section_zero_names_the_return_path_and_schema():
    mod = _load_distil()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert mod._return_path(plan, "one-grammar", "build").endswith("S0/one-grammar/return.json")
    assert mod._return_path(plan, "one-grammar", "judge", 2).endswith("S0/one-grammar/verdict.r2.json")
    assert mod._schema_file(mod._current_schema_id(mod.RETURN_FAMILY)).endswith(
        "profiles/workflows/packet-return.v2.schema.json")
    assert mod._schema_file(mod._current_schema_id(mod.JUDGEMENT_FAMILY)).endswith(
        "profiles/workflows/packet-judgement.v2.schema.json")
    with pytest.raises(SystemExit):
        mod._schema_file("laplace.packet-return/99")


def test_the_version_in_force_is_read_from_the_directory(tmp_path, monkeypatch):
    """A version bump is a FILE and nothing else. The three places that tell a worker which
    schema to satisfy (brief section 0, launch-args, spawn-args) resolve the version in force
    from the directory, so no constant in ``scripts/distil.py`` moves when one is published."""
    mod = _load_distil()
    assert mod._current_schema_id(mod.RETURN_FAMILY) == "laplace.packet-return/2"
    staging = tmp_path / "workflows"
    staging.mkdir()
    for name in ("packet-return.schema.json", "packet-judgement.schema.json"):
        (staging / name).write_text((ROOT / "profiles" / "workflows" / name).read_text(encoding="utf-8"),
                                    encoding="utf-8")
    bumped = json.loads((staging / "packet-return.schema.json").read_text(encoding="utf-8"))
    bumped["$id"] = "laplace.packet-return/2"
    bumped["properties"]["schema_version"]["const"] = "laplace.packet-return/2"
    (staging / "packet-return.v2.schema.json").write_text(json.dumps(bumped), encoding="utf-8")
    monkeypatch.setattr(mod, "SCHEMA_DIR", str(staging))

    assert mod._current_schema_id(mod.RETURN_FAMILY) == "laplace.packet-return/2"
    assert mod._schema_file("laplace.packet-return/2").endswith("packet-return.v2.schema.json")
    # the other family is untouched, and version 1 is still resolvable for documents naming it
    assert mod._current_schema_id(mod.JUDGEMENT_FAMILY) == "laplace.packet-judgement/1"
    assert mod._schema_file("laplace.packet-return/1").endswith("packet-return.schema.json")
    # and the module itself names families, never a version
    source = (ROOT / "scripts" / "distil.py").read_text(encoding="utf-8")
    assert 'RETURN_FAMILY = "laplace.packet-return"' in source
    assert '"laplace.packet-return/1"' not in source


# -------------------------------------------------------------------------------- the rows

def test_from_dir_rows_disclose_what_the_audit_requires(tmp_path):
    """``wave-rows --from-dir`` banks rows that ``scripts/audit_dispatch_models.py`` can read:
    each dispatch row carries ``packet_model_stamp`` derived from the plan's tier through
    ``schema.TIERS``, plus the explicit ``executor``, ``codex_model`` and ``sandbox`` that
    ``audit_dispatch_models.py:211-217`` requires. The 227 rows banked before this grammar
    carry none of them, which is why the live ledger is red."""
    mod = _load_distil()
    audit_spec = importlib.util.spec_from_file_location(
        "audit_dispatch_models", ROOT / "scripts" / "audit_dispatch_models.py")
    audit = importlib.util.module_from_spec(audit_spec)
    sys.modules.setdefault("audit_dispatch_models", audit)
    audit_spec.loader.exec_module(audit)

    plan = json.loads((FIXTURES / "plan.json").read_text(encoding="utf-8"))
    label = plan["agents"][0]["label"]

    class A:
        from_dir, plan, wave = str(FIXTURES), str(FIXTURES / "plan.json"), "S0-FIXTURE-REHEARSAL"
        provider, executor, sandbox = "claude", None, None

    wave, wave_plan, deposit, labels = mod._from_dir_doc(A)
    assert wave == "S0-FIXTURE-REHEARSAL"
    assert set(labels) == {label, f"judge:{label}:r1"}
    doc = json.loads(Path(deposit).read_text(encoding="utf-8"))
    assert [r["agentId"] for r in doc["returns"]] == [label, f"judge:{label}:r1"]

    row = {"record": "dispatch", **mod._transport(wave_plan, label, "build", A)}
    assert row["packet_model_stamp"] == schema.tier_model(plan["agents"][0]["tier"])
    assert row["executor"] == "claude-workflow-tool"
    assert row["codex_model"].startswith("not-applicable")
    assert row["sandbox"]
    ledger = tmp_path / "contract" / "dispatches.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_text(json.dumps(row) + "\n", encoding="utf-8")
    assert audit.scan(tmp_path).violations == []

    # a judge row resolves through the judge tier, and a row with no plan claims nothing
    judge_row = mod._transport(wave_plan, f"judge:{label}:r1", "judge", A)
    assert judge_row["packet_model_stamp"] == schema.tier_model("deep")
    assert mod._transport(None, label, "build", A) == {}


def test_the_grammars_own_rows_add_no_audit_violation(tmp_path):
    """The whole bank of one rehearsal wave - two dispatch rows AND the workflow row - read by
    the audit. Before this packet the workflow row was counted ``<malformed dispatch row>``
    purely for being a workflow row, which is what the 160 workflow/workflow-stage lines
    already in ``contract/dispatches.jsonl`` were being counted as."""
    audit_spec = importlib.util.spec_from_file_location(
        "audit_dispatch_models", ROOT / "scripts" / "audit_dispatch_models.py")
    audit = importlib.util.module_from_spec(audit_spec)
    sys.modules.setdefault("audit_dispatch_models", audit)
    audit_spec.loader.exec_module(audit)
    assert audit.LEDGER_EVENT_RECORDS == {"workflow", "workflow-stage"}

    ledger = tmp_path / "contract" / "dispatches.jsonl"
    ledger.parent.mkdir(parents=True)
    stamped = {"record": "dispatch", "packet_model_stamp": "haiku", "executor": "claude-workflow-tool",
               "codex_model": "not-applicable; claude-workflow-tool surface", "sandbox": "disclosed"}
    ledger.write_text("\n".join(json.dumps(r) for r in (
        stamped,
        {"record": "workflow", "id": "WORKFLOW-20261004T000000Z-abcdefabcdef", "phase": "result"},
        {"record": "workflow-stage", "id": "WORKFLOW-20261004T000000Z-abcdefabcdef:build"},
    )) + "\n", encoding="utf-8")
    assert audit.scan(tmp_path).violations == []

    # a record kind that is NOT a known run-level event is still a violation, so nothing hides
    for hidden in ({"record": "dispatch-ish"}, {}, None):
        ledger.write_text(json.dumps(hidden) + "\n", encoding="utf-8")
        assert len(audit.scan(tmp_path).violations) == 1, hidden


def _stage_wave(out: Path, wave: str) -> tuple:
    """The fixture wave copied to ``out``: one plan, one build return, one judgement. The
    returns pin the live fixture plan by absolute path, so their input digests stay true."""
    out.mkdir(parents=True, exist_ok=True)
    plan = json.loads((FIXTURES / "plan.json").read_text(encoding="utf-8"))
    plan["wave"], plan["out_dir"], plan["plan_path"] = wave, str(out), str(out / "plan.json")
    (out / "plan.json").write_text(json.dumps(plan, indent=1), encoding="utf-8")
    label = plan["agents"][0]["label"]
    (out / label).mkdir(exist_ok=True)
    for name in ("return.json", "verdict.r1.json"):
        (out / label / name).write_text((FIXTURES / "exemplar" / name).read_text(encoding="utf-8"),
                                        encoding="utf-8")
    return plan, label


class _Bank:
    """The argparse namespace ``cmd_wave_rows`` reads, with nothing else in it."""

    def __init__(self, out: Path, wave: str):
        self.from_dir, self.plan, self.wave = str(out), str(out / "plan.json"), wave
        self.waves, self.partial = None, False
        self.provider, self.executor, self.sandbox = "claude", None, None


def _ledger_rows(root: Path, store="dispatches") -> list:
    path = root / "contract" / f"{store}.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_the_banker_refuses_a_document_the_gate_refuses(tmp_path, monkeypatch):
    """``wave-rows --from-dir`` runs every return and verdict through ``_return_problems`` -
    the same code path ``check-return`` is - and banks NOTHING when one is refused. A gate that
    only runs where a worker chooses to run it is the state S0 set out to end."""
    mod = _load_distil()
    monkeypatch.setattr(mod, "ROOT", str(tmp_path))
    out = tmp_path / "live" / "evidence" / "WAVE"
    _plan, label = _stage_wave(out, "S0-TEST-OFF-SCHEMA")
    # the harness envelope, which is NOT a packet-return document
    (out / label / "return.json").write_text(json.dumps(
        {"output": "/tmp/x.md", "summary": "what the harness carries", "most_important": ["one"]}),
        encoding="utf-8")
    with pytest.raises(SystemExit) as refusal:
        mod.cmd_wave_rows(_Bank(out, "S0-TEST-OFF-SCHEMA"))
    assert "schema_version" in str(refusal.value)
    assert "return.json" in str(refusal.value)
    assert _ledger_rows(tmp_path) == []


def test_rebanking_a_rewritten_return_is_one_run_and_names_its_own_source(tmp_path, monkeypatch):
    """The closure loop rewrites a build return in place when a packet continues. One wave is
    one run: the second bank reuses the id the ledger already holds and appends a correction,
    instead of minting a second workflow row that ``workflow.py list`` would read as a second
    run. The dispatch row's ``source`` also states what actually read the labels: there is no
    journal on this path, so naming one would be a lie the report then repeats."""
    mod = _load_distil()
    monkeypatch.setattr(mod, "ROOT", str(tmp_path))
    (tmp_path / "contract").mkdir()
    out = tmp_path / "live" / "evidence" / "WAVE"
    _plan, label = _stage_wave(out, "S0-TEST-CONTINUATION")

    assert mod.cmd_wave_rows(_Bank(out, "S0-TEST-CONTINUATION")) == 0
    first = [r for r in _ledger_rows(tmp_path) if r.get("record") == "workflow"]
    assert len(first) == 1

    # JD4: the row says where it came from, and does not name a journal that does not exist
    build = [r for r in _ledger_rows(tmp_path) if r.get("record") == "dispatch" and r.get("label") == label][0]
    assert "--from-dir" in build["source"] and "return.json" in build["source"]
    assert "journal.jsonl" not in build["source"]

    # the packet continues in place and rewrites its return
    ret = out / label / "return.json"
    doc = json.loads(ret.read_text(encoding="utf-8"))
    doc["summary"] = doc["summary"] + " Rewritten in place after a rejection."
    ret.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    os.utime(ret, (time.time() + 90, time.time() + 90))

    assert mod.cmd_wave_rows(_Bank(out, "S0-TEST-CONTINUATION")) == 0
    rows = _ledger_rows(tmp_path)
    workflow = [r for r in rows if r.get("record") == "workflow"]
    assert {r["id"] for r in workflow} == {first[0]["id"]}, "one wave is one run"
    assert workflow[-1].get("corrects"), "the second bank is a correction under the same id"
    # one dispatch id per packet turn (build + its round-one judgement), corrections aside
    assert len({r["id"] for r in rows if r.get("record") == "dispatch"}) == 2
    assert len({r["id"] for r in _ledger_rows(tmp_path, "judged_verdicts")}) == 1


def test_a_row_names_the_exact_return_from_outside_the_root(tmp_path, monkeypatch):
    """A lane's evidence lives in the live tree while ROOT is the lane's own worktree. The
    row's pointer to the exact return must open from wherever the ledger is read, which is the
    rule ``_ledger_path`` applies to every path a row carries."""
    mod = _load_distil()
    root = tmp_path / "worktree"
    (root / "contract").mkdir(parents=True)
    monkeypatch.setattr(mod, "ROOT", str(root))
    out = tmp_path / "live-tree" / "evidence" / "WAVE"       # outside ROOT
    _plan, label = _stage_wave(out, "S0-TEST-OUTSIDE")

    assert mod.cmd_wave_rows(_Bank(out, "S0-TEST-OUTSIDE")) == 0
    build = [r for r in _ledger_rows(root) if r.get("record") == "dispatch" and r.get("label") == label][0]
    key = build["prompt_key"]
    assert os.path.isabs(key), key
    assert Path(key).is_file(), key
    assert json.loads(Path(key).read_text(encoding="utf-8"))["packet"] == label


def test_check_return_refuses_a_fabricated_input_digest(tmp_path):
    """The field whose whole purpose is pinning bytes must not accept an invented value: all
    zeros is the placeholder of digests, and anything else is checked against the file."""
    doc = json.loads((FIXTURES / "return.json").read_text(encoding="utf-8"))
    assert "CLEAN" in _distil("check-return", str(FIXTURES / "return.json"))

    doc["inputs"] = [{**doc["inputs"][0], "sha256": "sha256:" + "0" * 64}]
    zeros = tmp_path / "zero-digest.json"
    zeros.write_text(json.dumps(doc), encoding="utf-8")
    assert "input-digest: inputs/0/sha256 is all zeros" in _distil("check-return", str(zeros), expect=1)

    doc["inputs"] = [{**doc["inputs"][0], "sha256": "sha256:" + "a" * 64}]
    wrong = tmp_path / "wrong-digest.json"
    wrong.write_text(json.dumps(doc), encoding="utf-8")
    assert "whose bytes here are" in _distil("check-return", str(wrong), expect=1)


def test_programme_comes_from_the_plan_not_a_campaign_literal():
    source = (ROOT / "scripts" / "distil.py").read_text(encoding="utf-8")
    assert source.count('"ATLAS-PROGRAMME-20260921"') == 1       # the named default, once
    assert 'DEFAULT_PROGRAMME = "ATLAS-PROGRAMME-20260921"' in source
    plan = json.loads((FIXTURES / "plan.json").read_text(encoding="utf-8"))
    assert plan["programme"] == "WRITING-JOINS-2026-10-04"


# ------------------------------------------------- the launcher holds no model, and that is guarded

LAUNCHER = ".claude/workflows/atlas-wave.js"


def claude_model_tokens(text: str) -> list[str]:
    """Every Claude model name a launcher's TEXT names, with the name list read FROM the tier
    table (``schema.TIERS[*]['claude']``) so this guard moves when the table moves.

    The model audit cannot do this job and must not be mistaken for it: its pattern matches a
    quoted literal at a ``model:`` key only (``scripts/audit_dispatch_models.py:84``), so the
    ``const MODEL = {deep: 'opus', standard: 'sonnet', light: 'haiku'}`` this packet deleted was
    invisible to it - ``--root <tree> | grep -c '\\.js:.*model'`` returns 0 at the base commit and
    0 here, the same number whether the literal is present or gone. A measure that reads the same
    either way measures nothing, so the fact that the one Claude launcher names no model has its
    own holder, here, in the suite's causal path."""
    return sorted(t for t in {col["claude"] for col in schema.TIERS.values()}
                  if re.search(rf"\b{re.escape(t)}\b", text))


def test_the_one_claude_launcher_names_no_model_of_its_own():
    """The launcher this grammar installs reads every model from ``args.models``.

    Scoped to that one file on purpose. Seven other TRACKED .js launchers share the directory: three
    (``f-loop-integration.js``, ``pipeline-chain-integration.js``, ``weld-cwave3.js``) carry ``model:
    'opus'`` inline, which the audit's ``_LITERAL`` ceiling-checks (``scripts/audit_dispatch_models.py:84``);
    all seven bind ``const BOOTSTRAP_MODEL = 'haiku'``, which its ``_BOOTSTRAP`` checks
    (``scripts/audit_dispatch_models.py:90``). What had no guard was the ``const MODEL = {tier: name}``
    binding this packet deleted, which neither pattern sees; this test holds that fact for the one
    wave launcher (counted and classified by the orchestrator's own scan, S0/launcher.md, ruling)."""
    assert claude_model_tokens((ROOT / LAUNCHER).read_text(encoding="utf-8")) == []
    # and the file the guard names is the one the launch sequence names (docs/workflows.md)
    assert (ROOT / LAUNCHER).is_file()
