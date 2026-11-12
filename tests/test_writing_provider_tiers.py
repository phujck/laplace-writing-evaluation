"""ONE table for model choice: the tier table resolves a role to a model per provider.

Before this file the app never asked that table.  Its session default was whichever
catalogue row the VENDOR flagged ``default`` --- ``src/laplace/writing/provider.py``'s
``_claude_models`` copies the Claude SDK's own ``default`` entry and the composer
preselected it --- and the effort it banked for a model with no effort control was the
compatibility value ``'medium'`` while the adapter sent no flag at all (the live row
WS-abc8cfa1d95c4828bc49aacbd93b81b8 in ``contract/talk.jsonl``).

The tests are the shape ``tests/test_one_table.py`` uses: not "the two copies agree" but
"the words are not there to agree or disagree".  The grep is the right instrument for the
model-literal test for the same reason it is there: it must fail on a line a human adds
back by hand.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

TREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TREE / "src"))

from laplace.work import project_work            # noqa: E402
from laplace.writing import provider as writing_provider
from laplace.native import declarations as d                 # noqa: E402
import laplace.native.declared                               # noqa: E402,F401
import laplace.web.writing_declared_http                          # noqa: E402,F401
from laplace.pipeline import schema                           # noqa: E402

#: The five files the APP's model choice used to be spread over --- the whole scope of the
#: grep below, and the scope of the claim it licenses.  This is a SCOPE, not a list of
#: exemptions: inside these five files the rule has no exceptions of any kind, and nothing
#: here says anything about the rest of the tree.  One other role table exists on purpose
#: (``src/laplace/pipeline/dials.py:60`` ``_DEFAULTS``, the convergence pipeline's
#: calibration dial) and is a different fact; the one role NAME it shares with
#: ``schema.ROLE_TIER`` is pinned by
#: :func:`test_the_one_role_name_the_two_tables_share_agrees` below, not by this grep.
GREPPED = ("src/laplace/writing/provider.py", "src/laplace/work/project_work.py",
           "src/laplace/web/authoring.py", "src/laplace/writing/operating.py",
           "src/laplace/native/tools.py")

MODEL_NAMES = {schema.tier_model(tier, provider)
               for tier, column in schema.TIERS.items() for provider in column}


# --------------------------------------------------------------------------- #
# 1. the table is one table, and the role defaults are read OUT of it
# --------------------------------------------------------------------------- #
def test_each_tier_pairs_with_one_effort():
    """``tier_effort`` is a derivation only while this holds; the moment one ``WORKER_TIER``
    row pairs a tier with a second effort, a role default would be guessing."""
    for tier in schema.TIERS:
        efforts = {effort for kind_tier, effort in schema.WORKER_TIER.values() if kind_tier == tier}
        assert len(efforts) == 1, (tier, efforts)
        assert schema.tier_effort(tier) == efforts.pop()


def test_the_role_defaults_are_derived_not_typed():
    """The author's law: the interfacing session runs at the highest tier, a dispatched
    worker never inherits it, and anything that drives a real provider in a test rides the
    floor.  Every value is read off ``TIERS``/``WORKER_TIER``, so this asserts the LAW
    against the derivation, not one literal against another."""
    highest = max(schema.TIERS, key=lambda tier: schema.MODEL_RANK.index(schema.TIERS[tier]["claude"]))
    lowest = min(schema.TIERS, key=lambda tier: schema.MODEL_RANK.index(schema.TIERS[tier]["claude"]))
    assert schema.role_tier("session") == highest
    assert schema.role_tier("test") == lowest
    assert schema.role_tier("worker") == schema.role_tier("judge")
    assert schema.role_tier("worker") != schema.role_tier("session")
    assert schema.role_model("test", "claude")["model"] == schema.tier_model(lowest, "claude")
    assert schema.role_model("test", "codex") == {
        "role": "test", "tier": lowest, "model": schema.tier_model(lowest, "codex"),
        "effort": schema.tier_effort(lowest)}
    with pytest.raises(ValueError):
        schema.role_tier("orchestrator")


def test_the_tier_of_a_model_is_read_back_out_of_the_same_table():
    """The reverse lookup, by mechanism: an alias suffix and a resolved model id are
    spellings of one row, and a model the table does not name has no tier (``None``), never
    a guessed one."""
    for tier, column in schema.TIERS.items():
        for provider, model in column.items():
            assert schema.model_tier(model, provider) == tier
    assert schema.model_tier("opus[1m]", "claude") == "deep"
    assert schema.model_tier("", "claude", "claude-sonnet-5") == "standard"
    assert schema.model_tier("claude-fable-5-1[1m]", "claude", "claude-fable-5-1") is None
    assert schema.model_tier("gpt-5.5", "codex") is None


def test_no_model_literal_outside_the_schema_decides_a_default():
    """A model name may be a KEY --- a question asked ABOUT a model, like the advertised
    context window ``src/laplace/writing/provider.py`` keys by id --- and never a VALUE,
    which is an answer about WHICH model.  That is the whole rule, and inside its scope it is
    a mechanism: no exempt display names and no exempt lines.  The SCOPE is ``GREPPED``
    above --- the five files the app's model choice was spread over --- and the claim this
    test licenses is exactly that scope, no wider.  Documentation (a docstring, which is a
    bare expression) states history and is not a decision."""
    offenders = []
    for name in GREPPED:
        source = (TREE / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        allowed = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                allowed.update(id(key) for key in node.keys if key is not None)
            if isinstance(node, (ast.Set, ast.Tuple, ast.List)) and isinstance(
                    getattr(node, "ctx", None), ast.Load):
                # a membership set/sequence asks the same question: "is this one of these?"
                allowed.update(id(item) for item in node.elts)
            if isinstance(node, ast.Compare):
                allowed.update(id(item) for item in node.comparators)
            if isinstance(node, ast.Expr):
                allowed.add(id(node.value))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in allowed:
                continue
            if schema.model_spellings(node.value) & MODEL_NAMES:
                offenders.append((name, node.lineno, node.value[:60]))
    assert not offenders, offenders


# --------------------------------------------------------------------------- #
# 2. the app resolves role -> tier -> provider model, and records why
# --------------------------------------------------------------------------- #
def _claude_catalogue():
    """The live installation's own shape: the SDK's unnamed `default` entry FIRST, resolving
    to the deep tier's model, then the aliases.  The order is the trap this lane removed."""
    return {"id": "claude", "available": True, "models": [
        {"id": "", "resolved_model": "claude-opus-5[1m]", "default": True,
         "supports_effort": True, "efforts": ["low", "medium", "high"]},
        {"id": "opus[1m]", "resolved_model": "claude-opus-5[1m]", "default": False,
         "supports_effort": True, "efforts": ["low", "medium", "high"]},
        {"id": "sonnet", "resolved_model": "claude-sonnet-5", "default": False,
         "supports_effort": True, "efforts": ["low", "medium", "high"]},
        {"id": "haiku", "resolved_model": "claude-haiku-4-5-20251001", "default": False,
         "supports_effort": False, "efforts": []}]}


def test_an_omitted_model_is_the_roles_tier_default_not_the_vendors_flag():
    row = _claude_catalogue()
    values = project_work.resolve_session_settings(row, {"provider": "claude", "model": "", "effort": ""})
    assert values["model_source"] == "tier-default"
    assert values["tier"] == schema.role_tier("session")
    assert values["effort"] == schema.tier_effort(schema.role_tier("session"))
    # the vendor's own default row is the FIRST one and is not the answer: the advertised
    # row whose own id names the tier's model is
    assert values["model"] == "opus[1m]" and row["models"][0]["default"] is True


def test_a_named_model_and_a_project_preference_override_and_say_so():
    row = _claude_catalogue()
    named = project_work.resolve_session_settings(
        row, {"provider": "claude", "model": "sonnet", "effort": "low"})
    assert (named["model"], named["model_source"], named["tier"], named["effort"]) == (
        "sonnet", "named", "standard", "low")
    preference = project_work.resolve_session_settings(
        row, {"provider": "claude", "model": "sonnet", "effort": "low"},
        origin="project-preference")
    assert preference["model_source"] == "project-preference"
    assert {value["model_source"] for value in (named, preference)} <= set(schema.MODEL_SOURCES)
    outside = project_work.resolve_session_settings(
        row, {"provider": "claude", "model": "", "effort": "low"}, role="test")
    assert (outside["model"], outside["tier"]) == ("haiku", "light")


def test_a_model_without_effort_control_records_what_was_sent():
    """EFFORT TRUTH: ``None`` --- no effort flag --- never the compatibility value 'medium'
    the live row WS-abc8cfa1d95c4828bc49aacbd93b81b8 carries."""
    values = project_work.resolve_session_settings(
        _claude_catalogue(), {"provider": "claude", "model": "haiku", "effort": "medium"})
    assert values["effort"] is None and values["model"] == "haiku"
    with pytest.raises(ValueError):
        project_work.resolve_session_settings(
            _claude_catalogue(), {"provider": "claude", "model": "sonnet", "effort": "ultra"})


def test_an_undiscovered_catalogue_is_not_evidence_against_a_tier():
    """A provider whose discovery failed carries one placeholder row with an empty id.
    Refusing the tier default against it would refuse a list that does not exist, so the
    tier's own model name is recorded and the provider gets to answer."""
    placeholder = {"id": "codex", "available": True, "models": [
        {"id": "", "name": "Configured model", "default": True,
         "efforts": ["low", "medium", "high"]}]}
    assert writing_provider.models_discovered(placeholder) is False
    values = project_work.resolve_session_settings(placeholder, {"provider": "codex", "model": "", "effort": "low"})
    assert values["model"] == schema.tier_model(schema.role_tier("session"), "codex")
    assert values["model_source"] == "tier-default" and values["tier"] == schema.role_tier("session")
    discovered = {"id": "codex", "available": True, "models": [{"id": "gpt-5.5", "efforts": ["low"]}]}
    with pytest.raises(ValueError) as refusal:
        project_work.resolve_session_settings(discovered, {"provider": "codex", "model": "", "effort": "low"})
    assert schema.tier_model(schema.role_tier("session"), "codex") in str(refusal.value)


def test_a_token_carrying_an_alias_suffix_the_live_catalogue_no_longer_prints_still_names_its_row():
    """ux/m5-live-pilot-friction.json ADVERTISED_FABLE_REJECTED: the pane offered
    ``claude-fable-5-1[1m]`` from an earlier catalogue; the live catalogue advertises the
    same model as ``claude-fable-5-1``.  The alias suffix is the only difference, in the
    direction the first lookup did not try, and strict validation refused the person's own
    advertised choice.  One mechanism, both directions, no alias list."""
    live = {"id": "claude", "available": True, "models": [
        {"id": "fable", "resolved_model": "claude-fable-5-1", "supports_effort": True, "efforts": ["low", "high"]},
        {"id": "haiku", "resolved_model": "claude-haiku-fixture", "supports_effort": False, "efforts": []}]}
    assert writing_provider.advertised_model(live, "claude-fable-5-1[1m]")["id"] == "fable"
    assert writing_provider.advertised_model(live, "fable[1m]")["id"] == "fable"
    resolved = project_work.resolve_session_settings(live, {"provider": "claude", "model": "claude-fable-5-1[1m]", "effort": "high"})
    assert resolved["model"] == "fable" and resolved["model_source"] == "named"
    # a suffix on a token nothing advertises is still refused: stripping is not inventing
    assert writing_provider.advertised_model(live, "claude-nothing-9[1m]") is None
    with pytest.raises(ValueError, match="advertised"):
        project_work.resolve_session_settings(live, {"provider": "claude", "model": "claude-nothing-9[1m]", "effort": "high"})


def test_a_turn_with_no_recorded_effort_declares_no_effort_argument(tmp_path, monkeypatch):
    """ux/m5-live-pilot-friction.json HAIKU_REQUIRED_EFFORT: the session recorded effort
    ``None`` (a model without effort control, resolved against the passive catalogue), the
    live catalogue did not advertise that model, so ``supports_effort`` defaulted to True and
    the declaration demanded a flag the argv never appends.  The argv and the declaration
    now read one predicate: an effort is sent exactly when one is recorded and supported."""
    unadvertised = _claude_argv(monkeypatch, tmp_path, "haiku", None, True)
    assert "--effort" not in unadvertised
    withheld = _claude_argv(monkeypatch, tmp_path, "haiku", "low", False)
    assert "--effort" not in withheld
    sent = _claude_argv(monkeypatch, tmp_path, "sonnet", "low", True)
    assert sent[sent.index("--effort") + 1] == "low"


# --------------------------------------------------------------------------- #
# 3. catalogue, door and help are one declaration
# --------------------------------------------------------------------------- #
def test_the_catalogue_derives_its_tiers_and_never_stores_them():
    annotated = writing_provider.with_model_choice({"providers": [_claude_catalogue()]})
    models = annotated["providers"][0]["models"]
    assert [model["tier"] for model in models] == ["deep", "deep", "standard", "light"]
    assert [model.get("session_default") for model in models] == [None, True, None, None]
    assert annotated["model_choice"] == schema.model_choice_declaration()
    # the source rows are untouched: nothing a cache or a ledger holds carries a tier
    assert "tier" not in _claude_catalogue()["models"][0]


def test_the_tool_door_help_and_the_http_catalogue_read_the_one_declaration():
    declaration = d.HTTP_DECLARATIONS["authoring/providers"]
    assert declaration.derived == {"model_choice": "laplace.pipeline.schema:model_choice_declaration"}
    served = d.http_help("/authoring/providers", "GET")
    assert served["model_choice"] == schema.model_choice_declaration()
    assert served["model_choice"]["role_defaults"]["session"]["tier"] == schema.role_tier("session")
    # one declaration, not two renderings of one: what the door serves and what the
    # catalogue annotates are the same object by value
    assert json.loads(json.dumps(served["model_choice"])) == \
        writing_provider.with_model_choice({"providers": []})["model_choice"]


# --------------------------------------------------------------------------- #
# 4. the shared battery instrument measures tiers under authorisation
# --------------------------------------------------------------------------- #
INSTRUMENT = "evidence/WRITING_CONSOLIDATION_2026-10-03/resume-codex-20261003/provider_contact.py"
GUARD_FIXTURE = Path(__file__).resolve().parent / "fixtures/provider_tier_guard.py"


def _guard_source(path):
    text = path.read_text(encoding="utf-8")
    guard = next(node for node in ast.parse(text).body
                 if isinstance(node, ast.FunctionDef) and node.name == "tier_guard")
    return guard, ast.get_source_segment(text, guard)


def _instrument():
    """The instrument's tier guard, from its checked public copy (no provider contact, no
    evidence import). When the instrument itself is in this tree the copy must be verbatim."""
    guard, text = _guard_source(GUARD_FIXTURE)
    pinned = re.search(r'TIER_GUARD_SHA256 = "([0-9a-f]{64})"', GUARD_FIXTURE.read_text()).group(1)
    assert hashlib.sha256(text.encode()).hexdigest() == pinned
    if (TREE / INSTRUMENT).is_file():
        assert _guard_source(TREE / INSTRUMENT)[1] == text, "the checked copy drifted from the instrument"
    namespace = {"Path": Path}
    exec(compile(ast.Module(body=[guard], type_ignores=[]), str(GUARD_FIXTURE), "exec"), namespace)
    return namespace["tier_guard"]


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_the_instrument_resolves_a_tier_and_refuses_above_the_floor_without_authorisation(tmp_path):
    guard = _instrument()
    floor = schema.role_tier("test")
    for provider in ("claude", "codex"):
        resolved = guard(_Args(provider=provider, tier=floor, effort=schema.tier_effort(floor),
                               model=schema.tier_model(floor, provider), authorised_by=None))
        assert resolved == {"tier": floor, "model": schema.tier_model(floor, provider),
                            "effort": schema.tier_effort(floor), "authorised_by": None}
    with pytest.raises(ValueError) as refusal:
        guard(_Args(provider="claude", tier="standard", effort="low",
                    model=schema.tier_model("standard", "claude"), authorised_by=None))
    assert "authorised-by" in str(refusal.value)
    with pytest.raises(ValueError):
        guard(_Args(provider="claude", tier="standard", effort="low",
                    model=schema.tier_model("standard", "claude"),
                    authorised_by=str(tmp_path / "absent.json")))
    authorisation = tmp_path / "present.json"
    authorisation.write_text("{}")
    allowed = guard(_Args(provider="claude", tier="standard", effort="low",
                          model=schema.tier_model("standard", "claude"),
                          authorised_by=str(authorisation)))
    assert allowed["authorised_by"] == str(authorisation.resolve())
    assert allowed["model"] == schema.tier_model("standard", "claude")
    # a model is never named instead of a tier, and only the two providers resolve
    with pytest.raises(ValueError, match="name a tier, not a model"):
        guard(_Args(provider="claude", tier=floor, effort=schema.tier_effort(floor),
                    model=schema.tier_model("standard", "claude"), authorised_by=None))
    with pytest.raises(ValueError, match="Unknown provider"):
        guard(_Args(provider="other", tier=floor, effort=schema.tier_effort(floor), model="m", authorised_by=None))


# --------------------------------------------------------------------------- #
# 5. the one role NAME the engine's two role tables share
# --------------------------------------------------------------------------- #
def test_the_one_role_name_the_two_tables_share_agrees():
    """``src/laplace/pipeline/dials.py:60`` ``_DEFAULTS`` carries a SECOND role -> (model,
    effort) table, overlaid by ``profiles/pipeline/dials-v1.yaml:4`` ``roles``.  It is a
    different fact and it stays: ``schema.ROLE_TIER`` answers what model THIS SYSTEM gives a
    role of the engine (in-app session, dispatched worker, judge, test) and is derived with
    no literal, while those ``roles`` are the convergence pipeline's per-stage CALIBRATION
    dial, a setting a human retunes through ``/dials`` and a versioned profile.  What a
    second table may never do is disagree about a name they share -- and they share exactly
    one, ``judge``.  This test fails if a third name joins or if the LOADED dials (defaults
    plus the profile overlay, which is what a run reads) ever drift from the tier table."""
    from laplace.pipeline import dials
    loaded = dials.load_dials(None)["roles"]
    shared = sorted(set(loaded) & set(schema.ROLE_TIER))
    assert shared == ["judge"], shared
    for role in shared:
        want = schema.role_model(role, "claude")
        assert loaded[role]["model"] == want["model"], (role, loaded[role], want)
        assert loaded[role]["effort"] == want["effort"], (role, loaded[role], want)
    # and the dial's vocabulary is the tier table's own Claude column, not a second
    # model namespace with its own release schedule
    assert {row["model"] for row in loaded.values()} <= set(schema.MODEL_RANK)
    assert set(schema.MODEL_RANK) == {schema.TIERS[tier]["claude"] for tier in schema.TIERS}


# --------------------------------------------------------------------------- #
# 6. effort truth where the catalogue was NOT discovered at open time
# --------------------------------------------------------------------------- #
def _claude_argv(monkeypatch, tmp_path, model, effort, supports_effort):
    """What the Claude transport actually SENDS for these settings: the argv it hands
    ``subprocess.Popen``, captured at the call instead of inferred from the guard at
    ``src/laplace/writing_provider.py:958``."""
    captured = {}

    class _Popen:
        def __init__(self, argv, **kw):
            captured["argv"] = list(argv)
            raise RuntimeError("argv captured")

    monkeypatch.setattr(writing_provider.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(writing_provider.subprocess, "Popen", _Popen)
    turn = writing_provider.WritingTurn(tmp_path, "claude", model, effort, None, lambda event: None)
    turn.supports_effort = supports_effort
    with pytest.raises(RuntimeError):
        turn.run("hello")
    return captured["argv"]


def test_a_session_opened_before_the_catalogue_was_discovered_records_what_is_sent(tmp_path, monkeypatch):
    """The residual the first round left open, now cured and measured end to end.

    A root with NO cached catalogue advertises one placeholder row
    (``src/laplace/writing_provider.py:454`` ``models_discovered`` is False), so the opening
    door --- which must not start a provider process --- records the effort it was handed.
    ``src/laplace/authoring_surface.py:984`` ``effort_as_sent`` corrects that on the turn
    path from the capability that path already reads, through the existing
    ``writing-session-settings`` row.  The assertion is not "the row says None" but "the row
    says what the transport sends": the sent value is read off the captured argv."""
    from laplace.writing import turn_admission
    from laplace.pipeline import registry

    monkeypatch.setattr(writing_provider, "_CAP_CACHE", None)
    monkeypatch.setattr(writing_provider.shutil, "which", lambda name: "/installed/" + name)
    monkeypatch.setattr(writing_provider, "CodexConnection",
                        lambda *a, **k: pytest.fail("idle Codex launch"))
    monkeypatch.setattr(writing_provider.subprocess, "run",
                        lambda *a, **k: pytest.fail("idle provider process"))
    monkeypatch.setattr(registry, "resolve", lambda project, repo_root=None: {"name": project})

    # 1. no cached catalogue: nothing is discovered, and the opening door banks the effort
    #    it was handed for a model whose capability is unknown here.
    assert not writing_provider._catalogue_path(tmp_path).exists()
    passive = writing_provider.provider_catalogue(tmp_path)
    claude_row = next(row for row in passive["providers"] if row["id"] == "claude")
    assert writing_provider.models_discovered(claude_row) is False
    opened = turn_admission.new_session(tmp_path, "book", "claude", "haiku", "low")
    assert opened["effort"] == "low" and opened["model"] == "haiku"

    # 2. the catalogue is now discovered and says this model has no effort control.
    discovered = {"providers": [{"id": "claude", "available": True, "models": [
        {"id": "haiku", "resolved_model": "claude-haiku-fixture",
         "supports_effort": False, "efforts": []}]}]}
    monkeypatch.setattr(writing_provider, "capabilities", lambda *a, **k: discovered)
    truth = turn_admission.effort_as_sent(tmp_path, opened)
    assert truth["supports_effort"] is False
    assert truth["session"]["effort"] is None
    assert truth["session"]["model"] == "haiku" and truth["session"]["tier"] == "light"

    # 3. the recorded effort EQUALS what the transport sends, observed on the argv.
    argv = _claude_argv(monkeypatch, tmp_path, "haiku", truth["session"]["effort"], False)
    assert "--effort" not in argv
    # the conjugate, so the assertion above measures the guard instead of restating it
    sendable = _claude_argv(monkeypatch, tmp_path, "sonnet", "low", True)
    assert sendable[sendable.index("--effort") + 1] == "low"

    # 4. no second store: the correction rode the existing row kind, once.
    rows = [json.loads(line) for line in
            (tmp_path / "contract/talk.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    settings_rows = [row for row in rows if row.get("record") == "writing-session-settings"]
    assert len(settings_rows) == 1 and settings_rows[0]["effort"] is None
    assert settings_rows[0]["session_id"] == opened["id"]
    assert {row.get("record") for row in rows} == {"writing-session", "writing-session-settings"}
    # idempotent: a second turn on the corrected session banks nothing further
    again = turn_admission.effort_as_sent(tmp_path, truth["session"])
    assert again["session"]["effort"] is None
    rows_after = [line for line in
                  (tmp_path / "contract/talk.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows_after) == len(rows)


# --------------------------------------------------------------------------- #
# 7. the round trip's own fold: model_source/tier on a settings CHANGE
# --------------------------------------------------------------------------- #
def test_a_settings_change_folds_model_source_and_tier_onto_the_live_session(tmp_path, monkeypatch):
    """settings-three-ways (S2): ``src/laplace/web/authoring.py``'s ``_records`` folded
    a ``writing-session-settings`` row onto ``state['sessions']`` by naming only
    ``('provider', 'model', 'effort', 'settings_revision')`` --- dropping ``model_source``
    and ``tier`` even though the row the HTTP door banks (``configure_session``, and the
    correction row ``effort_as_sent`` writes) always carries both. The ONE row the three
    settings doors share therefore kept the session-OPEN tier/source forever: the live
    session view never advanced past whatever ``new_session`` first resolved, even after a
    later ``configure_session`` call changed both. This is the MUST ACHIEVE (1) round trip's
    own failure mode, not a hypothetical: a reader asking the row what it is now got the
    answer from when the conversation started."""
    from laplace.writing import turn_admission
    from laplace.writing import session_reads
    from laplace.pipeline import registry

    monkeypatch.setattr(registry, "resolve", lambda project, repo_root=None: {"name": project})
    opened = turn_admission.new_session(tmp_path, "book", "claude", "", "")
    assert opened["model_source"] == "tier-default"

    discovered = {"providers": [{"id": "claude", "available": True, "models": [
        {"id": opened["model"], "resolved_model": "x", "supports_effort": True,
         "efforts": ["low", "medium", "high"]},
        {"id": "haiku", "resolved_model": "y", "supports_effort": True,
         "efforts": ["low", "medium", "high"]}]}]}
    monkeypatch.setattr(writing_provider, "capabilities", lambda *a, **k: discovered)
    changed = turn_admission.configure_session(
        tmp_path, "book", opened["id"], {"provider": "claude", "model": "haiku", "effort": "low"})

    # the row BANKED and the row RETURNED must carry the resolver's OWN model_source/tier
    import json
    rows = [json.loads(line) for line in
            (tmp_path / "contract/talk.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    banked = [row for row in rows if row.get("record") == "writing-session-settings"][-1]
    assert banked["model_source"] == "named" and banked["tier"] == "light"
    assert changed["session"]["model_source"] == banked["model_source"], (
        "configure_session's own return disagreed with the row it just banked")
    assert changed["session"]["tier"] == banked["tier"]

    # and a FRESH read (the other door) reads back the SAME row, not the session-open one
    reread = session_reads.session_state(tmp_path, opened["id"])
    assert reread["session"]["model_source"] == banked["model_source"], (
        "a fresh session_state read disagreed with the settings door's own banked row")
    assert reread["session"]["tier"] == banked["tier"]
    assert reread["session"]["model"] == "haiku"


def test_a_pre_tier_defaults_settings_row_folds_without_a_keyerror(tmp_path, monkeypatch):
    """The fix above reads ``model_source``/``tier`` off the row with ``if key in row``, not
    ``row[key]``: a ``writing-session-settings`` row banked before this installation ever
    resolved a tier (no such keys at all) must fold the fields it DOES carry and must not
    raise, and must not silently install a spurious ``None`` for the two it lacks."""
    from laplace.writing import turn_admission
    from laplace.writing import records as writing_records
    from laplace.writing import session_reads
    from laplace.pipeline import registry

    monkeypatch.setattr(registry, "resolve", lambda project, repo_root=None: {"name": project})
    opened = turn_admission.new_session(tmp_path, "book", "claude", "haiku", "low")
    writing_records.bank(tmp_path, {"record": "writing-session-settings",
        "id": "WSS-legacy", "session_id": opened["id"], "project": "book",
        "provider": "claude", "model": "sonnet", "effort": "high",
        "settings_revision": 1})
    reread = session_reads.session_state(tmp_path, opened["id"])
    assert reread["session"]["model"] == "sonnet" and reread["session"]["effort"] == "high"
    assert reread["session"]["model_source"] == opened["model_source"], (
        "a legacy row with no model_source must leave the prior value alone, not null it")
    assert reread["session"]["tier"] == opened["tier"]


# --------------------------------------------------------------------------- #
# 8. incomplete assistant reports never manufacture a logical-turn aggregate
# --------------------------------------------------------------------------- #
def test_claude_without_terminal_counter_retains_partial_requests(monkeypatch, tmp_path):
    """No terminal usage means the turn total is unknown; request snapshots do not sum."""
    from laplace.writing import provider as writing_provider
    import json as _json

    class Input:
        def write(self, _):
            pass

        def close(self):
            pass

    class Process:
        pid = 777

        def __init__(self, argv, **kwargs):
            self.argv = argv
            self.stdin = Input()
            self.stdout = iter([
                _json.dumps({"type": "system", "subtype": "init", "session_id": "s", "model": "actual"}) + "\n",
                # round trip 1: a tool-use message, little output, but real usage
                _json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use"}],
                    "usage": {"input_tokens": 5, "cache_creation_input_tokens": 0,
                              "cache_read_input_tokens": 0, "output_tokens": 40}}}) + "\n",
                # round trip 2: the final text, a SHORT closing sentence's own usage
                _json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}],
                    "usage": {"input_tokens": 50, "cache_creation_input_tokens": 0,
                              "cache_read_input_tokens": 0, "output_tokens": 1}}}) + "\n",
                _json.dumps({"type": "result", "result": "ok", "is_error": False,
                    "permission_denials": [], "modelUsage": {}}) + "\n",
            ])

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    from test_writing_operating import _project

    _project(tmp_path)
    monkeypatch.setattr(writing_provider.shutil, "which", lambda name: "/fixture/claude")
    monkeypatch.setattr(writing_provider.subprocess, "Popen", Process)
    turn = writing_provider.WritingTurn(tmp_path, "claude", "haiku", "low", None,
                                        lambda event: None, "discuss", project="book")
    result = turn.run("do the thing")
    assert result["usage"]["output"] == 1, result["usage"]
    assert result["usage_facts"]["selected"]["logical_turn"] is None
    assert result["usage_basis"]["completeness"] == "partial_turn"
    assert result["usage"]["input"] == 50, (
        "input/cache fields are a context SNAPSHOT: the later round trip's own value, "
        "not a sum of both")


def test_claude_banked_output_is_the_results_own_aggregate_on_a_real_captured_turn(monkeypatch, tmp_path):
    """D2 (S2 settings-three-ways judge round 2): the test above is a SYNTHETIC stream built
    to match the per-round-trip-sum mechanism, and that mechanism is false on every real
    turn this programme has banked. The three lines below are copied, verbatim except the
    ~2KB `thinking.signature` blob (replaced with a short marker; every OTHER field,
    including every usage number, is byte-for-byte what the CLI sent), from a REAL two-round-
    trip Claude turn: evidence/WRITING_JOINS_2026-10-04/S1/observed-process/decision/
    arm-A.stream.jsonl lines 16, 39 and 45 (``python3 -c "import json;
    [print(i,json.loads(l)['type']) for i,l in
    enumerate(open('arm-A.stream.jsonl')) if l.strip()]"`` prints ``15 assistant / 38
    assistant / 44 result`` 0-indexed, i.e. lines 16/39/45 1-indexed).

    Both real top-level `assistant` events report the SAME `usage.output_tokens` (1) even
    though only the second carries the 222-character visible reply -- proving that field is
    not a per-round-trip delta that sums to a true count, so the OLD mechanism
    (`assistant_usage` accumulated across events, asserted above) was fixing the wrong
    number on every real turn. The `result` event's own `usage.output_tokens` (554) is the
    turn's real total (it folds the 475 thinking tokens the same `modelUsage` entry reports
    into `output`, matching `usage_projection`'s own "reasoning_output_folded_into_output"
    comment) -- this is what the fix above reads instead."""
    from laplace.writing import provider as writing_provider
    import json as _json

    class Input:
        def write(self, _):
            pass

        def close(self):
            pass

    # The real request/session ids and the thinking blob are replaced with short markers;
    # every usage number and the visible text are the file's own bytes.
    REAL_ASSISTANT_1 = {"type": "assistant", "message": {"model": "claude-haiku-4-5-20251001",
        "content": [{"type": "thinking", "thinking": "", "signature": "<2KB-signature-elided>"}],
        "usage": {"input_tokens": 10, "cache_creation_input_tokens": 15092,
                  "cache_read_input_tokens": 0, "output_tokens": 1}},
        "parent_tool_use_id": None}
    REAL_ASSISTANT_2 = {"type": "assistant", "message": {"model": "claude-haiku-4-5-20251001",
        "content": [{"type": "text", "text": "```json\n{\n  \"tool_definitions_actually_available\": [\n"
                     "    \"mcp__laplace__laplace_project\"\n  ],\n  \"shell_attempt\": \"no shell tool\",\n"
                     "  \"project_instructions_present\": false,\n  \"project_instructions_first_80_chars\": null\n}\n```"}],
        "usage": {"input_tokens": 10, "cache_creation_input_tokens": 15092,
                  "cache_read_input_tokens": 0, "output_tokens": 1}},
        "parent_tool_use_id": None}
    REAL_RESULT = {"type": "result", "is_error": False, "permission_denials": [],
        "result": "```json\n{...}\n```",
        "usage": {"input_tokens": 10, "cache_creation_input_tokens": 15092,
                  "cache_read_input_tokens": 0, "output_tokens": 554,
                  "output_tokens_details": {"thinking_tokens": 475}},
        "modelUsage": {"claude-haiku-4-5-20251001": {"inputTokens": 10, "outputTokens": 554,
            "cacheReadInputTokens": 0, "cacheCreationInputTokens": 15092,
            "thinkingTokens": 475, "canonicalModel": "claude-haiku-4-5"}}}

    class Process:
        pid = 778

        def __init__(self, argv, **kwargs):
            self.argv = argv
            self.stdin = Input()
            self.stdout = iter([
                _json.dumps({"type": "system", "subtype": "init", "session_id": "s", "model": "actual"}) + "\n",
                _json.dumps(REAL_ASSISTANT_1) + "\n",
                _json.dumps(REAL_ASSISTANT_2) + "\n",
                _json.dumps(REAL_RESULT) + "\n",
            ])

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    from test_writing_operating import _project

    _project(tmp_path)
    monkeypatch.setattr(writing_provider.shutil, "which", lambda name: "/fixture/claude")
    monkeypatch.setattr(writing_provider.subprocess, "Popen", Process)
    turn = writing_provider.WritingTurn(tmp_path, "claude", "haiku", "low", None,
                                        lambda event: None, "discuss", project="book")
    result = turn.run("do the thing")
    # The regression this proves: a 222-character real reply must not bank output 1 (the
    # per-event accumulator's answer) or 2 (the naive sum of the two real events' own
    # output_tokens) -- it must bank 554, the result event's own aggregate.
    assert result["usage"]["output"] == 554, result["usage"]
    assert result["usage"]["output"] != 1 and result["usage"]["output"] != 2
    assert result["usage"]["reasoning_output"] == 475
    assert result["usage_facts"]["selected"]["logical_turn"]["counts"]["output"] == 554


def test_current_codex_tier_defaults_have_documented_capacity_metadata():
    for tier, expected in (("deep", "gpt-6.1-sol"), ("standard", "gpt-5.6-terra"), ("light", "gpt-6-luna")):
        assert schema.tier_model(tier, "codex") == expected
        assert writing_provider.context_window_advertised("codex", expected) == 1_050_000
    assert writing_provider.context_window_max("codex", "gpt-6.1-sol") is None
