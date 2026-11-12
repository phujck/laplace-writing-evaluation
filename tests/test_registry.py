"""The registry roster - project_states (per-project release convergence state) and the
corrupt-vs-absent split in read_plan.

project_states is the inventory authority: one row per registered project, carrying its release
state, last-updated stamp, and harnessed round count. The load-bearing distinction is NEVER_RUN
(no state.json file at all) vs STAGED (a state.json exists and sits at the floor) - detected by
file existence, not by the string current_state returns on absence. Corruption (a truncated
write, a merge marker) warns rather than crashing the roster or reading as "no plan / no state".
"""

from __future__ import annotations

import json
import logging

from laplace.pipeline import registry


#: a known conceptric project whose manuscript_dir resolves cleanly under an arbitrary repo root.
_PROJ = "law-of-laws"


def _manuscript_dir(repo_root):
    md = repo_root / registry.all_projects()[_PROJ].manuscript_dir
    md.mkdir(parents=True, exist_ok=True)
    return md


def _row(repo_root, name=_PROJ):
    return {r["name"]: r for r in registry.project_states(repo_root)}[name]


def test_never_run_is_distinct_from_staged(tmp_path):
    """No state.json FILE -> NEVER_RUN (the release machine never touched it); a present state.json
    at the floor -> STAGED. The split is by file existence, not by current_state's absence default
    (which is itself STAGED) - the two must not collapse."""
    md = _manuscript_dir(tmp_path)
    assert _row(tmp_path)["state"] == "NEVER_RUN"

    (md / "release").mkdir()
    (md / "release" / "state.json").write_text(
        json.dumps({"state": "STAGED", "history": []}), encoding="utf-8")
    assert _row(tmp_path)["state"] == "STAGED"


def test_state_and_updated_read_from_the_sidecar(tmp_path):
    """A non-floor state and its updated stamp ride through from the sidecar."""
    md = _manuscript_dir(tmp_path)
    (md / "release").mkdir()
    (md / "release" / "state.json").write_text(
        json.dumps({"state": "UNDER_CONVERGENCE", "updated": "2026-07-12T00:00:00", "history": []}),
        encoding="utf-8")
    row = _row(tmp_path)
    assert row["state"] == "UNDER_CONVERGENCE"
    assert row["updated"] == "2026-07-12T00:00:00"


def test_corrupt_state_json_warns_never_crashes(tmp_path, caplog):
    """An exists-but-unparseable state.json warns and degrades (the roster still assembles) rather
    than crashing project_states on the JSON error."""
    md = _manuscript_dir(tmp_path)
    (md / "release").mkdir()
    (md / "release" / "state.json").write_text("{ this is not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        row = _row(tmp_path)
    assert row["state"] == "STAGED"   # present-but-corrupt is not NEVER_RUN
    assert any("unparseable" in r.getMessage() for r in caplog.records), "corruption must warn"


def test_corrupt_plan_json_warns_absent_is_silent(tmp_path, caplog):
    """read_plan folds the corrupt-vs-absent split: an absent plan returns None silently, a
    present-but-unparseable plan returns None AND warns. Both None, only one noisy."""
    proj = registry.all_projects()[_PROJ]
    _manuscript_dir(tmp_path)

    # absent plan: silent None
    with caplog.at_level(logging.WARNING):
        assert proj.read_plan(tmp_path) is None
    assert not any("unparseable" in r.getMessage() for r in caplog.records)

    caplog.clear()
    plan_path = tmp_path / proj.plan_path
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("{ broken plan", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert proj.read_plan(tmp_path) is None
    assert any("unparseable" in r.getMessage() for r in caplog.records), "corrupt plan must warn"


def test_rounds_counted_independently_of_state(tmp_path):
    """rounds_n counts rounds/harnessed/mech_r*.json - a project can carry rounds while state.json
    is still absent (NEVER_RUN), so the two are read independently."""
    md = _manuscript_dir(tmp_path)
    harnessed = md / "rounds" / "harnessed"
    harnessed.mkdir(parents=True)
    for r in (1, 2, 5):
        (harnessed / f"mech_r{r}.json").write_text("{}", encoding="utf-8")
    # a non-round file in the same dir must not inflate the count.
    (harnessed / "detect_pre_r1.json").write_text("{}", encoding="utf-8")

    row = _row(tmp_path)
    assert row["rounds_n"] == 3
    assert row["state"] == "NEVER_RUN", "rounds without a state.json is still NEVER_RUN"


def test_roster_covers_every_registered_project(tmp_path):
    """One row per registered project, each carrying the full ENRICHED shape (W0.3) - no
    project silently absent. The dashboard enrichers ride: pipeline_position (mirrors
    state), latest_artefact (the one current-artefact fact), staleness (honestly
    'unchecked' here - not faked), next_action (the gesture the state invites)."""
    rows = registry.project_states(tmp_path)
    assert {r["name"] for r in rows} == set(registry.all_projects())
    for r in rows:
        assert set(r) == {"name", "kind", "display_name", "state", "updated", "rounds_n",
                          "pipeline_position", "latest_artefact", "staleness", "next_action"}
        assert r["pipeline_position"] == r["state"]          # the same fact, named for the dashboard
        assert r["staleness"] == "unchecked"                 # honest: not paid per row, not faked
        assert set(r["latest_artefact"]) == {"pdf", "tex", "version_id", "kind"}
        # an empty tmp root -> every project is NEVER_RUN and invited to run the pipeline.
        assert r["state"] == "NEVER_RUN" and r["next_action"] == "run pipeline"


# ─────────────────────────────────────────────────────────────────────────────
# THE MARRIAGE LAW (2026-07-28): a registry row is not a marriage. Three legs -
# the row's layout manifest (paths that resolve), the deposit in the
# self-conceptric, the cockpit mount under a ruled display name - each checked
# mechanically, and every unmet leg reported rather than the first.

#: the row the marriage tests register into a tmp root, with every leg met.
_MARRIED_ROW = {
    "name": "married-fixture",
    "kind": "conceptric",
    "tex_root": "synthetics papers/married-fixture/manuscript",
    "manifest": {
        "display_name": "The Married Fixture",
        "ledger": "synthetics papers/married-fixture/ledger.jsonl",
        "projection": "synthetics papers/married-fixture/projection",
        "state": "synthetics papers/married-fixture/STATE.json",
        "default_axis": "semantic",
        "maps": {"semantic": "synthetics papers/married-fixture/maps/semantic.json"},
    },
}


def _write_registry(repo_root, *rows):
    (repo_root / registry.DATA_PROJECTS_FILE).write_text(
        json.dumps({"projects": list(rows)}), encoding="utf-8")


def _write_manifest_paths(repo_root, row, skip=()):
    """Materialise every path the row's manifest declares, except the labels in ``skip``."""
    for label, rel in registry.manifest_paths(row["manifest"]):
        if label in skip:
            continue
        p = repo_root / rel
        if label == "projection":
            p.mkdir(parents=True, exist_ok=True)
            (p / "main.pdf").write_bytes(b"%PDF-")
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("{}", encoding="utf-8")


def _write_deposit(repo_root, *names):
    """A minimal self-conceptric grade-0 index in write_index's format."""
    lines = []
    for n in names:
        lines.append(f"<!-- shard name:{n} kind:md grade:0 sealed:0 -->")
        lines.append(f"- **{n}** - a deposited node · `x` · 1 lines")
    (repo_root / registry.SELF_INDEX).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_manifest_schema_round_trips_onto_the_row(tmp_path):
    """A manifest written on a registry_projects.json row rides onto the Project verbatim -
    maps keyed BY AXIS, one axis marked as the default routing section (the fibred-upfold
    consequence: there is no one map, so the schema carries the axis key)."""
    _write_registry(tmp_path, _MARRIED_ROW)
    proj = registry._projects(tmp_path)["married-fixture"]
    assert proj.manifest == _MARRIED_ROW["manifest"]
    assert registry.manifest_issues(proj.manifest) == []
    assert proj.manifest["default_axis"] in proj.manifest["maps"]
    assert registry.display_name(proj) == "The Married Fixture"
    # a row with NO manifest keeps the empty default - the field is additive, never required
    # for a row to register.
    assert registry.all_projects()[_PROJ].manifest == {}


def test_manifest_issues_name_every_shape_error():
    """The schema check is pure (no filesystem) and names each fault, so a row can be
    validated where it is written."""
    assert registry.manifest_issues({}) == ["absent"]
    assert registry.manifest_issues(None) == ["absent"]
    issues = registry.manifest_issues({
        "ledger": "a/b.jsonl", "projection": "/etc/passwd", "state": "",
        "maps": {"semantic": "../outside.json"}, "default_axis": "structural",
        "display_name": "  ",
    })
    joined = " | ".join(issues)
    assert "state is not declared" in joined
    assert "escapes the repo root" in joined                 # the absolute projection
    assert "maps.semantic" in joined and "escapes" in joined  # the ../ map
    assert "default_axis 'structural' is not a key of maps" in joined
    assert "display_name is declared but empty" in joined
    # the axis-keyed map is load-bearing: no axis at all is a schema error.
    assert any("maps declares no axis" in i for i in registry.manifest_issues(
        {"ledger": "a", "projection": "b", "state": "c", "default_axis": "semantic"}))


def test_married_needs_all_three_legs(tmp_path):
    """All three legs met -> married. The deposit leg reads the self-conceptric's grade-0
    index; the cockpit leg reads the ruled display name the roster mounts under."""
    _write_registry(tmp_path, _MARRIED_ROW)
    _write_manifest_paths(tmp_path, _MARRIED_ROW)
    _write_deposit(tmp_path, "synthetics papers/married-fixture/STATE.json")

    ok, missing = registry.married("married-fixture", tmp_path)
    assert (ok, missing) == (True, [])
    row = {r["name"]: r for r in registry.marriage_roster(tmp_path)}["married-fixture"]
    assert row["married"] and row["legs_missing"] == []
    assert row["display_name"] == "The Married Fixture"


def test_married_reports_every_missing_leg_honestly(tmp_path):
    """A row that meets no leg reports all three, not the first - and a row missing exactly
    one leg says which (the honest-missing case: genesis has a manifest and a deposit but no
    author-ruled display name, so it is unmarried on the cockpit leg alone)."""
    bare = {"name": "bare-fixture", "kind": "conceptric",
            "tex_root": "synthetics papers/bare-fixture/manuscript"}
    no_name = json.loads(json.dumps(_MARRIED_ROW))
    no_name["name"] = "nameless-fixture"
    no_name["manifest"].pop("display_name")
    for key in ("ledger", "projection", "state"):
        no_name["manifest"][key] = no_name["manifest"][key].replace("married-", "nameless-")
    no_name["manifest"]["maps"]["semantic"] = \
        no_name["manifest"]["maps"]["semantic"].replace("married-", "nameless-")
    _write_registry(tmp_path, bare, no_name)
    _write_manifest_paths(tmp_path, no_name)
    _write_deposit(tmp_path, "synthetics papers/nameless-fixture/STATE.json")

    ok, missing = registry.married("bare-fixture", tmp_path)
    assert not ok
    assert {m.split(":", 1)[0] for m in missing} == {"manifest", "deposit", "cockpit"}

    ok, missing = registry.married("nameless-fixture", tmp_path)
    assert not ok
    assert [m.split(":", 1)[0] for m in missing] == ["cockpit"]
    assert "no ruled display name" in missing[0]

    assert registry.married("no-such-project", tmp_path) == (
        False, ["registry: no row named 'no-such-project'"])


def test_married_manifest_leg_fails_on_a_path_that_does_not_exist(tmp_path):
    """A manifest is a declaration of WHERE things are - one that points at nothing is not a
    layout, so the leg fails and names the path."""
    _write_registry(tmp_path, _MARRIED_ROW)
    _write_manifest_paths(tmp_path, _MARRIED_ROW, skip=("maps.semantic",))
    _write_deposit(tmp_path, "synthetics papers/married-fixture/STATE.json")

    ok, missing = registry.married("married-fixture", tmp_path)
    assert not ok
    assert any("maps.semantic" in m and "does not exist" in m for m in missing)


def test_married_deposit_leg_reads_the_self_conceptric(tmp_path):
    """No node under the project's dir in SELF_SHARD_INDEX.md -> not deposited, said plainly."""
    _write_registry(tmp_path, _MARRIED_ROW)
    _write_manifest_paths(tmp_path, _MARRIED_ROW)
    _write_deposit(tmp_path, "HANDOFF.md", "src/laplace/engine/wake.py")   # nothing of this project

    ok, missing = registry.married("married-fixture", tmp_path)
    assert not ok
    assert [m.split(":", 1)[0] for m in missing] == ["deposit"]
    assert registry.SELF_INDEX in missing[0]


def test_truth_layer_flags_a_projection_beside_a_never_run_release(tmp_path):
    """ONE TRUTH PER PROJECT (PRM-20260721-truth-layer): a built projection on disk while the
    release machine reads NEVER_RUN, and a second run-state file declared where the release
    machine wrote no sidecar, are the two ways a project's surfaces disagree about run-state.
    Both are the live case this walk was built from."""
    _write_registry(tmp_path, _MARRIED_ROW)
    _write_manifest_paths(tmp_path, _MARRIED_ROW)      # projection dir holds a main.pdf
    _write_deposit(tmp_path, "synthetics papers/married-fixture/STATE.json")
    # the declared second home carries a RELEASE-ladder value: a genuinely competing
    # run-state claim (the 2026-08-07 reconciliation scoped the leg to release.STATES —
    # a growth sidecar or an alien state machine is a different ladder, not a second home).
    (tmp_path / "synthetics papers/married-fixture/STATE.json").write_text(
        json.dumps({"state": "UNDER_CONVERGENCE"}), encoding="utf-8")

    rows = {r["name"]: r for r in registry.truth_layer_check(tmp_path)}
    assert "married-fixture" in rows
    why = " | ".join(rows["married-fixture"]["why"])
    assert rows["married-fixture"]["state"] == "NEVER_RUN"
    assert "a built projection sits at" in why
    assert "two run-state homes" in why

    # a growth-ladder value in the same file is NOT a competing release claim: the
    # projection leg may still fire, the two-homes leg must not.
    (tmp_path / "synthetics papers/married-fixture/STATE.json").write_text(
        json.dumps({"state": "SEEDED"}), encoding="utf-8")
    rows = {r["name"]: r for r in registry.truth_layer_check(tmp_path)}
    why = " | ".join(rows["married-fixture"]["why"]) if "married-fixture" in rows else ""
    assert "two run-state homes" not in why

    # the release machine having actually run is the end of the contradiction: one truth.
    rel = tmp_path / "synthetics papers/married-fixture/manuscript" / "release"
    rel.mkdir(parents=True)
    (rel / "state.json").write_text(json.dumps({"state": "RELEASED", "history": []}),
                                    encoding="utf-8")
    assert "married-fixture" not in {r["name"] for r in registry.truth_layer_check(tmp_path)}


def test_truth_layer_ignores_rows_without_a_manifest(tmp_path):
    """No manifest, no declared surfaces - nothing to disagree. The walk is scoped to rows
    that actually declare where their projection and run-state live."""
    _write_registry(tmp_path, {"name": "bare-fixture", "kind": "conceptric",
                               "tex_root": "synthetics papers/bare-fixture/manuscript"})
    assert "bare-fixture" not in {r["name"] for r in registry.truth_layer_check(tmp_path)}


def test_data_row_project_dir_override_rehomes_the_deposit_leg(tmp_path):
    """A data row whose real home is outside ``synthetics papers/`` may declare it
    (the design-interface case: the deposit leg was checking a directory the project
    never occupied). The override rehomes project_dir AND the manuscript home follows
    the row's own tex_root; the escape fence holds for absolute/parent-walking values."""
    _write_registry(tmp_path,
        {"name": "rehomed", "kind": "conceptric", "tex_root": "elsewhere/manuscript",
         "project_dir": "elsewhere"},
        {"name": "escapee", "kind": "conceptric", "tex_root": "x/manuscript",
         "project_dir": "../outside"},
        {"name": "absolute", "kind": "conceptric", "tex_root": "y/manuscript",
         "project_dir": "/tmp/nope"})
    projs = registry._projects(tmp_path)
    assert projs["rehomed"].project_dir == "elsewhere"
    assert projs["rehomed"].manuscript_dir == "elsewhere/manuscript"
    assert "escapee" not in projs and "absolute" not in projs
    # the convention is untouched when no override is declared
    _write_registry(tmp_path, {"name": "plain", "kind": "conceptric",
                               "tex_root": "synthetics papers/plain/manuscript"})
    p = registry._projects(tmp_path)["plain"]
    assert p.project_dir == "synthetics papers/plain"
    assert p.manuscript_dir == "synthetics papers/plain/manuscript"
