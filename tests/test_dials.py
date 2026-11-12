"""THE DIALS: code defaults own today's design, the versioned YAML overlays them,
and an unknown key raises loudly (a typo must never silently no-op)."""
import copy

import pytest

from laplace.web import dials_surface as ds
from laplace.pipeline import dials as pipeline_dials


def _deep_merge(base, over):
    """defaults ⊕ overlay — the same deep-merge the loader applies (unknown-key
    strictness aside; a reduced overlay only carries known leaves)."""
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def test_defaults_carry_todays_design():
    d = pipeline_dials.defaults()
    assert d["version"] == "dials-v1"
    assert d["roles"]["builder"] == {"model": "opus", "effort": "high"}
    assert d["roles"]["sealed_reader"] == {"model": "haiku", "effort": "low"}
    assert d["loop"]["max_rounds"] == 4
    assert d["loop"]["weld"] == "auto"
    assert d["loop"]["weld_global_dirty_threshold"] == 4
    assert d["loop"]["lock"]["readers"] == ["R1", "R2", "R4", "R5", "R6", "R7", "R9", "R10"]
    assert d["loop"]["lock"]["voice_wash"] is True
    assert d["loop"]["verify_votes"] == 1
    assert d["drift"] == {"page_change_warn": 3, "page_count_change": "loud"}
    assert d["suppression"]["key"] == ["node", "kind", "fingerprint"]
    assert d["suppression"]["stale_on_fingerprint_mismatch"] is True
    assert d["prompts"]["overrides_dir"] == "profiles/pipeline/prompts"
    # F2 (audit §A4): the fan-out width / batch bound. max_width=0 is UNCAPPED —
    # today's exact behaviour, so the default changes no existing fleet's shape.
    assert d["fanout"] == {"max_width": 0, "batch_max_chars": 140000}


def test_staged_leg_roles_pin_todays_tiers():
    # AUDIT §A3 (F1): the staged build leg (project-staged.js) was brought under the
    # dials via three dedicated roles. They default to the tiers the leg's OWN
    # in-script literals already ran at, so wiring the leg to the dials is honest with
    # ZERO silent behaviour change by default (retunable on /dials, but never by
    # accident — this pin fails loudly if the tiers drift). The narrative planners and
    # prose realisers ran at sonnet; the mechanical utilities (read-manifest /
    # compile-dispatches / validate / post-weld-fidelity) ran at haiku/low.
    d = pipeline_dials.defaults()
    assert d["roles"]["planner"] == {"model": "sonnet", "effort": "medium"}
    assert d["roles"]["realiser"] == {"model": "sonnet", "effort": "medium"}
    assert d["roles"]["staged_utility"] == {"model": "haiku", "effort": "low"}
    # THE ONE REAL BEHAVIOUR CHANGE (named alongside so the pair reads together): the
    # weld no longer runs at the staged sonnet literal — it maps to the EXISTING
    # welder role (opus/high), honouring the dial that always claimed that seat.
    assert d["roles"]["welder"] == {"model": "opus", "effort": "high"}
    # the shipped profile mirrors these (the shipped-YAML-equals-defaults invariant,
    # exercised in full by test_shipped_yaml_equals_code_defaults).
    loaded = pipeline_dials.load_dials()
    for r in ("planner", "realiser", "staged_utility", "welder"):
        assert loaded["roles"][r] == d["roles"][r]


def test_shipped_yaml_equals_code_defaults():
    # THE SHIPPED-PROFILE INVARIANT, in its two regimes:
    #   * PRISTINE (no <name>.friction.jsonl sidecar beside DEFAULT_DIALS_PATH):
    #     the versioned profile carries EXACTLY the code defaults, so a fresh
    #     checkout runs the designed pipeline and load_dials() round-trips the file.
    #   * BOARDED (a friction ledger exists — the profile has been edited through
    #     the dials conjugate): the managed YAML equals defaults ⊕ the reduced
    #     overlay (base + the ledger folded), i.e. load_dials() must reflect the
    #     ledger, not the pristine defaults.
    path = pipeline_dials.DEFAULT_DIALS_PATH
    assert path.is_file()
    name = path.name
    ledger = ds._ledger_path(path, name)
    if not ledger.is_file():
        assert pipeline_dials.load_dials() == pipeline_dials.defaults()
    else:
        base = ds._read_base(path, name)
        ops = ds._ledger.read_jsonl(ledger)
        expected = _deep_merge(pipeline_dials.defaults(), ds.reduce_overlay(base, ops))
        assert pipeline_dials.load_dials() == expected


def test_defaults_are_deep_copied_not_shared():
    a = pipeline_dials.load_dials()
    a["loop"]["max_rounds"] = 99
    a["roles"]["builder"]["model"] = "mutated"
    b = pipeline_dials.load_dials()
    assert b["loop"]["max_rounds"] == 4
    assert b["roles"]["builder"]["model"] == "opus"


def test_yaml_overlays_known_keys(tmp_path):
    prof = tmp_path / "pipeline_dials.yaml"
    prof.write_text("loop:\n  max_rounds: 7\ndrift:\n  page_change_warn: 5\n",
                    encoding="utf-8")
    d = pipeline_dials.load_dials(prof)
    assert d["loop"]["max_rounds"] == 7          # overlaid
    assert d["drift"]["page_change_warn"] == 5    # overlaid
    assert d["loop"]["verify_votes"] == 1         # untouched default survives
    assert d["roles"]["builder"] == {"model": "opus", "effort": "high"}


def test_unknown_top_level_key_raises(tmp_path):
    prof = tmp_path / "pipeline_dials.yaml"
    prof.write_text("looop:\n  max_rounds: 7\n", encoding="utf-8")
    with pytest.raises(ValueError) as ei:
        pipeline_dials.load_dials(prof)
    assert "looop" in str(ei.value)


def test_unknown_nested_key_raises_with_dotted_path(tmp_path):
    prof = tmp_path / "pipeline_dials.yaml"
    prof.write_text("loop:\n  maxx_rounds: 7\n", encoding="utf-8")
    with pytest.raises(ValueError) as ei:
        pipeline_dials.load_dials(prof)
    assert "loop.maxx_rounds" in str(ei.value)


def test_unknown_fanout_key_raises(tmp_path):
    # F2 (audit §A4): a typo in the fanout group must raise, never silently no-op.
    prof = tmp_path / "pipeline_dials.yaml"
    prof.write_text("fanout:\n  max_widht: 8\n", encoding="utf-8")
    with pytest.raises(ValueError) as ei:
        pipeline_dials.load_dials(prof)
    assert "fanout.max_widht" in str(ei.value)


def test_fanout_width_overlays(tmp_path):
    # a real cap is opt-in via the profile; the default stays 0 (uncapped).
    prof = tmp_path / "pipeline_dials.yaml"
    prof.write_text("fanout:\n  max_width: 8\n", encoding="utf-8")
    d = pipeline_dials.load_dials(prof)
    assert d["fanout"]["max_width"] == 8
    assert d["fanout"]["batch_max_chars"] == 140000   # untouched default survives


def test_unknown_role_raises(tmp_path):
    prof = tmp_path / "pipeline_dials.yaml"
    prof.write_text("roles:\n  buidler:\n    model: opus\n", encoding="utf-8")
    with pytest.raises(ValueError) as ei:
        pipeline_dials.load_dials(prof)
    assert "roles.buidler" in str(ei.value)


def test_mapping_expected_where_scalar_given(tmp_path):
    prof = tmp_path / "pipeline_dials.yaml"
    prof.write_text("loop: 4\n", encoding="utf-8")   # loop must be a mapping
    with pytest.raises(ValueError) as ei:
        pipeline_dials.load_dials(prof)
    assert "loop" in str(ei.value)


def test_missing_explicit_path_is_loud(tmp_path):
    with pytest.raises(FileNotFoundError):
        pipeline_dials.load_dials(tmp_path / "does-not-exist.yaml")


def test_role_accessor_raises_on_typo():
    d = pipeline_dials.defaults()
    assert pipeline_dials.role(d, "referee") == {"model": "opus", "effort": "high"}
    with pytest.raises(KeyError):
        pipeline_dials.role(d, "referi")


def test_prompt_override_naming_rule(tmp_path):
    # <overrides_dir>/<name>.<ext> REPLACES the built-in template when present.
    d = pipeline_dials.defaults()
    d["prompts"]["overrides_dir"] = str(tmp_path / "prompts")
    assert pipeline_dials.prompt_override(d, "referee") is None
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "referee.md").write_text("REPLACED referee template",
                                                     encoding="utf-8")
    assert pipeline_dials.prompt_override(d, "referee") == "REPLACED referee template"
    # a label with no override file stays None (built-in stands)
    assert pipeline_dials.prompt_override(d, "cold_reader") is None


# Engine dial consumers; every mutation uses an isolated store.
import ast
import json
import os
from pathlib import Path
import re
import subprocess

import pytest

from laplace.pipeline import dial_profiles as dials
from laplace.engine import meaning_upfold

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_DIALS_ROOT", str(tmp_path))
    dials.pour_genesis(tmp_path)
    return tmp_path


def cli(*args):
    proc = subprocess.run(["/usr/bin/python3", "-m", "laplace.pipeline.dial_profiles", *args],
                          cwd=ROOT, env=os.environ.copy(), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def test_no_module_level_dial_constants():
    # Text grep catches rebinding to a helper as well as literal constants.
    names = {
        "src/laplace/engine/meaning_upfold.py": ["LEAF_MAX", "BRANCH_MAX", "MAX_DEPTH", "_SPECTRAL_GPU_MIN_N",
            "_KMEANS_BLAS_THREADS", "_SELECTOR_CHI_LADDER", "_SELECTOR_CHI_DEEP", "_SELECTOR_BETA",
            "_SELECTOR_QUERIES", "_SELECTOR_SEED"],
        "src/laplace/representation/metric_distill.py": ["EPOCHS", "LR", "MARGIN", "ANCHOR", "HOLDOUT", "NEG_PER_POS", "SEED"],
        "scripts/export_atlas_snapshot.py": ["SEALED_REF_THRESHOLD", "SEALED_REF_TOP_N"],
    }
    for path, banned in names.items():
        text = (ROOT / path).read_text()
        assert not re.search(r"^(?:" + "|".join(banned) + r")\s*(?::[^=]+)?=", text, re.M), path
        for node in ast.parse(text).body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                assert not any(isinstance(t, ast.Name) and t.id in banned for t in targets)
    fold = (ROOT / "src/laplace/engine/meaning_upfold.py").read_text()
    assert '"LAPLACE_REEMBED_FULL_FRACTION", "0.20"' not in fold
    assert 'range(2, hi + 1)' not in fold
    metric = (ROOT / "src/laplace/representation/metric_distill.py").read_text()
    assert 'range(64)' not in metric


def test_genesis_matches_removed_constants(store):
    expected = {
        "engine-fold": dict(leaf_max=10, branch_max=8, max_depth=6, repair_sweep_per_deposit=64, silhouette_k_min=2,
            spectral_gpu_min_n=384, kmeans_blas_threads=6, kmeans_seed=0, kmeans_n_init=10,
            eigensolver_tolerance=1e-5, eigensolver_jitter=1e-8, eigensolver_power_iterations=256,
            selector_chi_top=16, selector_chi_deep=8, selector_beta=0.10, selector_queries=512, selector_seed=11),
        "engine-metric": dict(margin=0.2, lr=0.05, anchor=0.05, epochs=5, holdout=0.1,
            neg_per_pos=4, seed=7, sample_neg=64),
        "engine-triggers": dict(full_fraction=0.20, minimum_leaf_multiple=2),
        "atlas-export": dict(sealed_ref_threshold=100, sealed_ref_top_n=20),
    }
    for scope, values in expected.items():
        row = dials.current(scope)
        assert {k: v["value"] for k, v in row["dials"].items()} == values
        assert row["parent_dial_set"] == dials.GENESIS
        assert all(re.fullmatch(r".+\.py:\d+", v["source"]) for v in row["dials"].values())
        dials._validate(row)
    receipts = [json.loads(line) for line in (store / "contract/journal.jsonl").read_text().splitlines()]
    assert sum(r.get("record") == "bank" and r.get("phase") == "done" for r in receipts) == 4


def test_genesis_is_once_and_never_replaces_successor(store):
    row = dials.set_value("engine-fold", "max_depth", "7", by="test", why="fixture", root=store)
    before = (store / dials.STORE).read_bytes()
    dials.pour_genesis(store)
    assert (store / dials.STORE).read_bytes() == before
    assert dials.current("engine-fold") == row


def test_set_reaches_reader_in_fresh_process(store):
    parent = dials.current("engine-fold")["dial_set_id"]
    row = cli("--set", "engine-fold", "max_depth=7", "--by", "test", "--why", "fixture")
    assert row["parent_dial_set"] == parent
    assert cli("--show", "engine-fold")["dial_set_id"] == row["dial_set_id"]
    script = ('import json; from laplace.engine.meaning_upfold import depth_cap_figure; '
              'print(json.dumps(depth_cap_figure(dict(clusters={},parent_map={},leaf_sha={},root_id=""))))')
    proc = subprocess.run(["/usr/bin/python3", "-c", script], cwd=ROOT,
                          env=os.environ.copy(), capture_output=True, text=True, check=True)
    result = json.loads(proc.stdout)
    assert result["max_depth"] == 7
    assert result["dial_set_id"] == row["dial_set_id"]


def test_cache_invalidates_and_returned_record_is_detached(store):
    first = dials.current("engine-fold")
    first["dials"]["max_depth"]["value"] = 999
    assert dials.current("engine-fold")["dials"]["max_depth"]["value"] == 6
    cli("--set", "engine-fold", "max_depth=7", "--by", "test", "--why", "cache")
    assert dials.current("engine-fold")["dials"]["max_depth"]["value"] == 7


@pytest.mark.parametrize("name,raw", [("max_depth", "true"), ("max_depth", "1.5"),
    ("max_depth", "-1"), ("unknown", "1"), ("selector_beta", "NaN"),
    ("silhouette_k_min", "9")])
def test_invalid_set_appends_nothing(store, name, raw):
    path = store / dials.STORE
    before = path.read_bytes()
    with pytest.raises(dials.DialRefusal):
        dials.set_value("engine-fold", name, raw, by="test", why="invalid", root=store)
    assert path.read_bytes() == before


def test_hash_and_chain_are_checked(store):
    path = store / dials.STORE
    original = path.read_text()
    row = dials.current("engine-fold")
    row["dials"]["max_depth"]["value"] = 7
    path.write_text(original + json.dumps(row) + "\n")
    with pytest.raises(dials.DialRefusal, match="hash mismatch"):
        dials.current("engine-fold")
    row["dial_set_id"] = dials._hash(row)
    path.write_text(original + json.dumps(row) + "\n")
    with pytest.raises(dials.DialRefusal, match="parent chain"):
        dials.current("engine-fold")


def test_missing_store_refuses(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_DIALS_ROOT", str(tmp_path))
    with pytest.raises(dials.DialRefusal, match="missing engine-fold"):
        meaning_upfold.depth_cap_figure(dict(clusters={}, parent_map={}, leaf_sha={}, root_id=""))


def test_duplicate_json_refuses(store):
    path = store / dials.STORE
    path.write_text(path.read_text() + '{"scope":"engine-fold","scope":"atlas-export"}\n')
    with pytest.raises(dials.DialRefusal, match="duplicate key"):
        dials.current("engine-fold")


@pytest.mark.parametrize("mode", ["person", "engine"])
@pytest.mark.parametrize("full", [False, True])
def test_wake_cli_carries_dial_sets(store, monkeypatch, mode, full):
    monkeypatch.delenv("LAPLACE_CUSTODY_LIVE", raising=False)
    proc = subprocess.run(["/usr/bin/python3", "scripts/wake.py", "--grade", "0", "--" + mode,
                           *(["--full"] if full else [])], cwd=ROOT,
                          env=os.environ.copy(), capture_output=True, text=True, check=True)
    result = json.loads(proc.stdout)
    assert next(iter(result)) == "custody_mode"
    assert len(result["dial_sets"]) == 4
    for shown in result["dial_sets"]:
        row = dials.current(shown["scope"])
        assert shown["dial_set_id"] == row["dial_set_id"]
        if full:
            assert shown == row
        else:
            assert shown["n_dials"] == len(row["dials"])
            assert shown["parent"] == row["parent_dial_set"]
            assert shown["descend"].endswith("--show " + row["scope"])


def test_depth_cap_names_snapshot(store):
    row = dials.current("engine-fold")
    result = meaning_upfold.depth_cap_figure(dict(clusters={}, parent_map={}, leaf_sha={}, root_id=""))
    assert result["dial_set_id"] == row["dial_set_id"]
    assert result["leaf_max"] == row["dials"]["leaf_max"]["value"]
    assert result["max_depth"] == row["dials"]["max_depth"]["value"]


def test_all_metric_defaults_reach_gpu_consumer(store, monkeypatch):
    # Stub the numerical kernel at the call boundary; no CPU fit or fallback runs.
    import numpy as np
    from laplace.representation import metric_distill
    dials.set_value("engine-metric", "epochs", "9", by="test", why="consumer", root=store)
    seen = {}
    monkeypatch.setattr(metric_distill, "fit_backend", lambda device: ("gpu", ""))
    def fit(X, ids, trainset, held, sample_neg, rng, d, **kw):
        seen.update(kw)
        return np.eye(d, dtype="float32"), 0.5, 0.5
    monkeypatch.setattr(metric_distill, "_fit_gpu", fit)
    vecs = {str(i): [1.0] for i in range(12)}
    result = metric_distill.train(vecs, [(str(i), str(i+1)) for i in range(11)])
    # initial_M is cure-B's warm start (RES-20260914-cure-B-admitted-...): None on a full fit,
    # the banked M on an incremental one. It reaches the GPU consumer like every other dial.
    assert seen == dict(epochs=9, lr=0.05, margin=0.2, anchor=0.05, neg_per_pos=4, initial_M=None)
    assert result["device"] == "gpu"


def test_depth_cap_cli_distinguishes_missing_dials(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LAPLACE_DIALS_ROOT", str(tmp_path))
    (tmp_path / meaning_upfold.TREE_FILE).write_text(json.dumps(
        dict(clusters={}, parent_map={}, leaf_sha={}, root_id="")))
    assert meaning_upfold._main(["--depth-cap-figure", "--repo-root", str(tmp_path)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "DIAL-SET-REFUSED"


def test_genesis_source_coordinates_match_pre_migration_bytes():
    originals = {}
    new_schema = {"repair_sweep_per_deposit", "eigensolver_tolerance",
                  "eigensolver_jitter", "eigensolver_power_iterations"}
    for row in dials.genesis():
        for name, dial in row["dials"].items():
            if name in new_schema:
                continue  # new schema, not a constant migrated from 2f361faf
            path, line = dial["source"].rsplit(":", 1)
            if path not in originals:
                originals[path] = subprocess.run(
                    ["git", "show", "2f361faf:" + path], cwd=ROOT, text=True,
                    capture_output=True, check=True).stdout.splitlines()
            assert str(dial["value"]) in originals[path][int(line) - 1], dial["source"]


def test_new_dial_joins_legacy_store_by_successor_only(tmp_path, monkeypatch):
    monkeypatch.setenv("LAPLACE_DIALS_ROOT", str(tmp_path))
    row = next(r for r in dials.genesis() if r["scope"] == "engine-fold")
    del row["dials"]["repair_sweep_per_deposit"]
    (tmp_path / "contract").mkdir()
    old = dials._bank(row, tmp_path)
    dials.pour_genesis(tmp_path)
    assert dials.current("engine-fold") == old
    successor = dials.set_value("engine-fold", "repair_sweep_per_deposit", "64",
                                by="test", why="schema migration", root=tmp_path)
    assert successor["parent_dial_set"] == old["dial_set_id"]
    assert successor["dials"]["repair_sweep_per_deposit"]["value"] == 64
    assert all(successor["dials"][k] == v for k, v in old["dials"].items())
    with pytest.raises(dials.DialRefusal):
        dials.set_value("engine-fold", "repair_sweep_per_deposit", "-1",
                        by="test", why="invalid budget", root=tmp_path)
