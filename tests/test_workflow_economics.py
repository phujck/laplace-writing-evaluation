"""Leg A bite A5 — per-agent economics made legible.

THE RUN's named plumbing defect: the workflow journal carried no per-agent usage,
so the cost autopsy was a coarse prose guess. ``scripts/workflow_economics.py``
closes it by JOINING the harness journal (label/phase/model per ``agent()`` call)
with each agent's SDK transcript (``agent-<id>.jsonl``, whose ``assistant`` turns
and terminal ``result`` carry ``usage`` + ``duration_ms``) and totalling by stage.

The contract under test, driven against a SYNTHETIC run directory built in
``tmp_path`` (never a real run):
  (a) result-cumulative path — an agent whose transcript has a terminal ``result``
      message: usage/duration/cost come from it (assistant turns ignored);
  (b) assistant-sum fallback — an agent with only ``assistant`` turns (no result):
      usage is SUMMED across turns, duration derived from message timestamps;
  (c) the JOIN + rollup — economics.json totals and per-phase yield/cost are the
      exact sums of the two agents, keyed on the journal's phase labels;
  (d) the artifact — economics.md carries the per-stage table + TOTAL row;
  (e) the empty-run guard — a dir with neither journal nor transcript exits 2.

Both the real CLI (subprocess, the surface the runbook documents) and the
importable functions (the calibration-note consumer seam) are exercised.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "workflow_economics.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("workflow_economics", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_jsonl(path: Path, rows: list) -> None:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def run_dir(tmp_path: Path) -> Path:
    """A synthetic transcript dir: journal.jsonl + two agent transcripts.

    Agent 'aaa' (Weld/opus) has a terminal result message → cumulative path.
    Agent 'bbb' (Converge/haiku) has only assistant turns → assistant-sum path.
    """
    d = tmp_path / "run-2026-07-10"
    d.mkdir()

    # -- the harness journal: opts banked per ag() call (id joins to transcript) --
    _write_jsonl(d / "journal.jsonl", [
        {"agent_id": "aaa", "label": "weld", "phase": "Weld",
         "model": "opus", "effort": "high", "agentType": "general-purpose",
         "duration_ms": 12000},
        {"agent_id": "bbb", "label": "mechround", "phase": "Converge",
         "model": "haiku", "effort": "low",
         "started_at": "2026-07-10T12:00:00Z", "ended_at": "2026-07-10T12:00:10Z"},
    ])

    # -- aaa: assistant turns (partial usage, IGNORED) + result (cumulative) ------
    _write_jsonl(d / "agent-aaa.jsonl", [
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"model": "claude-opus-4-8", "usage": {
            "input_tokens": 400, "output_tokens": 200,
            "cache_creation_input_tokens": 100, "cache_read_input_tokens": 300}}},
        {"type": "assistant", "message": {"model": "claude-opus-4-8", "usage": {
            "input_tokens": 600, "output_tokens": 300,
            "cache_creation_input_tokens": 100, "cache_read_input_tokens": 500}}},
        {"type": "result", "subtype": "success", "duration_ms": 12000,
         "num_turns": 2, "total_cost_usd": 0.15, "usage": {
             "input_tokens": 1000, "output_tokens": 500,
             "cache_creation_input_tokens": 200, "cache_read_input_tokens": 800}},
    ])

    # -- bbb: assistant turns only (no result) -> sum + timestamp duration --------
    _write_jsonl(d / "agent-bbb.jsonl", [
        {"type": "assistant", "timestamp": "2026-07-10T12:00:00Z",
         "message": {"model": "claude-haiku-4-5", "usage": {
             "input_tokens": 300, "output_tokens": 100,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 400}}},
        {"type": "assistant", "timestamp": "2026-07-10T12:00:10Z",
         "message": {"model": "claude-haiku-4-5", "usage": {
             "input_tokens": 300, "output_tokens": 100,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 400}}},
    ])
    return d


def test_cli_emits_artifacts_with_correct_totals(run_dir: Path):
    r = subprocess.run([sys.executable, str(SCRIPT), str(run_dir)],
                       capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    econ = json.loads((run_dir / "economics.json").read_text())

    t = econ["totals"]
    assert t["agents"] == 2
    # aaa (result cumulative) 1000+500+200+800=2500 ; bbb (sum) 600+200+0+800=1600
    assert t["total_tokens"] == 4100
    assert t["input_tokens"] == 1600      # 1000 + (300+300)
    assert t["output_tokens"] == 700      # 500 + (100+100)
    assert t["duration_ms"] == 22000      # 12000 (journal/result) + 10000 (ts)

    # -- per-stage yield/cost rollup keyed on the journal phases -----------------
    assert econ["by_phase"]["Weld"]["total_tokens"] == 2500
    assert econ["by_phase"]["Converge"]["total_tokens"] == 1600
    assert econ["by_phase"]["Converge"]["duration_ms"] == 10000

    # -- per-agent rows carry label/phase/model/usage-source --------------------
    by_label = {a["label"]: a for a in econ["agents"]}
    assert by_label["weld"]["phase"] == "Weld"
    assert by_label["weld"]["usage_source"] == "result"
    assert by_label["weld"]["cost_source"] == "reported"     # total_cost_usd present
    assert "opus" in (by_label["weld"]["model"] or "")
    assert by_label["mechround"]["usage_source"] == "assistant-sum"
    assert by_label["mechround"]["cost_source"] == "estimated"  # haiku price table
    assert by_label["mechround"]["total_tokens"] == 1600


def test_markdown_artifact_has_stage_table(run_dir: Path):
    subprocess.run([sys.executable, str(SCRIPT), str(run_dir), "--quiet"],
                   check=True)
    md = (run_dir / "economics.md").read_text()
    assert "Per stage" in md
    assert "| Weld |" in md
    assert "| Converge |" in md
    assert "**TOTAL**" in md
    assert "4,100" in md  # formatted total tokens


def test_calibration_consumer_seam(run_dir: Path):
    """render_calibration_economics is the block the calibration note embeds."""
    mod = _load_module()
    econ = mod.build_economics(run_dir)
    block = mod.render_calibration_economics(econ)
    # stage rows in pipeline order (Weld before Converge), then a bold TOTAL
    assert block.index("| Weld |") < block.index("| Converge |")
    assert "**TOTAL**" in block
    assert "4,100" in block


def test_transcript_only_run_no_journal(tmp_path: Path):
    """No journal: enumerate agent-*.jsonl directly; label from filename."""
    d = tmp_path / "bare"
    d.mkdir()
    _write_jsonl(d / "agent-solo.jsonl", [
        {"type": "result", "subtype": "success", "duration_ms": 5000, "usage": {
            "input_tokens": 10, "output_tokens": 5,
            "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}},
    ])
    mod = _load_module()
    econ = mod.build_economics(d)
    assert econ["totals"]["agents"] == 1
    assert econ["totals"]["total_tokens"] == 15
    assert econ["agents"][0]["label"] == "solo"


def test_v2_sha_journal_joins_short_id_transcripts_no_phantoms(tmp_path: Path):
    """A5 JOIN FIX: THE RUN's journal keyed agents by a versioned id (``v2:<sha>``)
    while the transcript FILES are named by the bare id (``agent-<sha>.jsonl``), so
    the id-keyed join missed every row — 45 agents surfaced vs 15 real, 30 phantom
    zero-usage rows, every row unlabelled. The normalised join now strips the scheme
    prefix so ``v2:<sha>`` joins ``agent-<sha>.jsonl``: rows are LABELLED (from the
    journal), usage is JOINED (from the transcript), and there are NO phantom rows."""
    mod = _load_module()
    d = tmp_path / "run"
    d.mkdir()
    sha_a = "a1b2c3d4e5f60718293a4b5c6d7e8f90"     # a full 32-char id
    sha_b = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
    # journal keys by the VERSIONED id; the transcript files use the BARE id.
    _write_jsonl(d / "journal.jsonl", [
        {"agent_id": f"v2:{sha_a}", "label": "prepass#1", "phase": "Detect",
         "model": "haiku", "duration_ms": 3000},
        {"agent_id": f"v2:{sha_b}", "label": "harnessed-fix#1.1", "phase": "Fix",
         "model": "opus"},
    ])
    _write_jsonl(d / f"agent-{sha_a}.jsonl", [
        {"type": "result", "usage": {"input_tokens": 500, "output_tokens": 200,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 100},
         "duration_ms": 3000}])
    _write_jsonl(d / f"agent-{sha_b}.jsonl", [
        {"type": "assistant", "message": {"model": "claude-opus-4-8", "usage": {
            "input_tokens": 1000, "output_tokens": 400,
            "cache_creation_input_tokens": 200, "cache_read_input_tokens": 300}}}])

    agents = mod.collect_agents(d)
    # exactly 2 rows (no phantom agent-<i> duplicates from a failed join).
    assert len(agents) == 2
    by_label = {a["label"]: a for a in agents}
    assert set(by_label) == {"prepass#1", "harnessed-fix#1.1"}   # LABELLED, not agent-0/1
    # usage JOINED across the scheme-prefix mismatch.
    assert by_label["prepass#1"]["phase"] == "Detect"
    assert by_label["prepass#1"]["usage_source"] == "result"
    assert by_label["prepass#1"]["total_tokens"] == 800          # 500+200+0+100
    assert by_label["harnessed-fix#1.1"]["phase"] == "Fix"
    assert by_label["harnessed-fix#1.1"]["usage_source"] == "assistant-sum"
    assert by_label["harnessed-fix#1.1"]["total_tokens"] == 1900  # 1000+400+200+300
    # no row has zero usage (the phantom signature) and none defaulted to agent-<i>.
    assert all(a["total_tokens"] > 0 for a in agents)
    assert not any(str(a["label"]).startswith("agent-") for a in agents)

    econ = mod.summarize(d, agents)
    assert econ["totals"]["agents"] == 2
    assert econ["totals"]["total_tokens"] == 800 + 1900
    # token accounting is EXPLICIT: output tokens roll up distinctly from the
    # cache-inclusive gross total.
    assert econ["totals"]["output_tokens"] == 200 + 400
    md = mod.render_markdown(econ)
    assert "output:" in md and "cache-inclusive" in md


def test_truncated_transcript_id_still_joins(tmp_path: Path):
    """The transcript file may carry a TRUNCATED id (a sha prefix) while the journal
    carries the full versioned sha; the prefix/suffix join (>= 8 chars) still binds
    them, and there is no phantom row."""
    mod = _load_module()
    d = tmp_path / "run"
    d.mkdir()
    full = "abcdef0123456789abcdef0123456789"
    _write_jsonl(d / "journal.jsonl",
                 [{"agent_id": f"v2:{full}", "label": "redetect#1.1",
                   "phase": "Verify", "model": "haiku"}])
    # the transcript file uses only the first 12 chars of the sha.
    _write_jsonl(d / f"agent-{full[:12]}.jsonl", [
        {"type": "result", "usage": {"input_tokens": 10, "output_tokens": 5,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
         "duration_ms": 100}])
    agents = mod.collect_agents(d)
    assert len(agents) == 1
    assert agents[0]["label"] == "redetect#1.1"        # joined, not a phantom
    assert agents[0]["total_tokens"] == 15
    assert agents[0]["usage_source"] == "result"


def test_nested_opts_journal_is_labelled_not_agent_i(tmp_path: Path):
    """Defensive: when the harness banks the agent() opts NESTED under an ``opts``
    block (rather than flat), label/phase/model are still read — the row is labelled,
    not rendered as an unlabelled ``agent-<i>``."""
    mod = _load_module()
    d = tmp_path / "run"
    d.mkdir()
    _write_jsonl(d / "journal.jsonl",
                 [{"agent_id": "n1", "opts": {"label": "commit-fix#1.1",
                   "phase": "Fix", "model": "haiku"}}])
    _write_jsonl(d / "agent-n1.jsonl", [
        {"type": "result", "usage": {"input_tokens": 20, "output_tokens": 10,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}])
    agents = mod.collect_agents(d)
    assert len(agents) == 1
    assert agents[0]["label"] == "commit-fix#1.1"
    assert agents[0]["phase"] == "Fix"


# ---------------------------------------------------------------------------
# F1 (a6 judge, MEDIUM) — the per-stage table made derivable: the harness journal
# banks NO label/phase/model (keys v2:<sha>, started+result twin rows only), so the
# organ now emits its OWN stage manifest (agents_manifest.json: ordinal ->
# {label, phase, model}) and this reader joins it. Absent the manifest, the journal
# path must still collapse the started/result twins (no phantom double-count rows).
# ---------------------------------------------------------------------------

def _harness_journal_rows(shas: list, labels_absent=True) -> list:
    """The REAL harness journal shape the a6 judge autopsied: per agent a `started`
    and a `result` row, keyed by agentId + key (v2:<sha>), NO label/phase/model."""
    rows = []
    for i, sha in enumerate(shas):
        rows.append({"type": "started", "key": f"v2:{sha}", "agentId": f"aid{i}{sha[:8]}"})
        rows.append({"type": "result", "key": f"v2:{sha}", "agentId": f"aid{i}{sha[:8]}",
                     "result": {"ok": True}})
    return rows


def test_manifest_join_yields_real_per_stage_table_no_phantoms(tmp_path: Path):
    """THE F1 FIX end-to-end: a harness-shaped journal (started+result twins, v2 keys,
    no stage metadata) + the organ's agents_manifest.json + transcripts -> a per-stage
    table with REAL labels/phases and NO phantom rows."""
    mod = _load_module()
    d = tmp_path / "run"
    d.mkdir()
    sha_a = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    sha_b = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
    sha_c = "9988776655443322119988776655aabb"
    _write_jsonl(d / "journal.jsonl", _harness_journal_rows([sha_a, sha_b, sha_c]))
    for sha, tok in ((sha_a, 100), (sha_b, 2000), (sha_c, 300)):
        _write_jsonl(d / f"agent-{sha}.jsonl", [
            {"type": "result", "usage": {"input_tokens": tok, "output_tokens": 50,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
             "duration_ms": 1000}])
    # the organ's stage manifest: ordinal -> {label, phase, model} (project-harnessed
    # `ag()` records exactly this at each dispatch).
    (d / "agents_manifest.json").write_text(json.dumps([
        {"ordinal": 0, "label": "prepass#1", "phase": "Detect", "model": "haiku"},
        {"ordinal": 1, "label": "harnessed-fix#1.1", "phase": "Fix", "model": "opus"},
        {"ordinal": 2, "label": "redetect#1.1", "phase": "Verify", "model": "haiku"},
    ]), encoding="utf-8")

    econ = mod.build_economics(d)          # manifest AUTO-DISCOVERED in the run dir
    agents = econ["agents"]
    # exactly 3 rows: one per manifest entry — no started/result double-count, no
    # phantom zero-usage rows, no unlabelled agent-<i>.
    assert len(agents) == 3
    assert [a["label"] for a in agents] == ["prepass#1", "harnessed-fix#1.1", "redetect#1.1"]
    assert all(a["total_tokens"] > 0 for a in agents)
    # usage joined by ORDINAL through the journal's dispatch order (v2 keys).
    by_label = {a["label"]: a for a in agents}
    assert by_label["prepass#1"]["total_tokens"] == 150
    assert by_label["harnessed-fix#1.1"]["total_tokens"] == 2050
    assert by_label["redetect#1.1"]["total_tokens"] == 350
    # the per-stage table is REAL: three labelled stages, never one (unlabelled) row.
    assert set(econ["by_phase"]) == {"Detect", "Fix", "Verify"}
    assert econ["by_phase"]["Fix"]["total_tokens"] == 2050
    assert "(unlabelled)" not in econ["by_phase"]
    md = mod.render_calibration_economics(econ)
    assert "| Detect |" in md and "| Fix |" in md and "| Verify |" in md


def test_manifest_cli_flag_and_explicit_path(tmp_path: Path):
    """--manifest <path> joins a manifest living OUTSIDE the run dir (the organ banks
    it under the manuscript's rounds/harnessed/)."""
    d = tmp_path / "run"
    d.mkdir()
    sha = "abcdef0123456789abcdef0123456789"
    _write_jsonl(d / "journal.jsonl", _harness_journal_rows([sha]))
    _write_jsonl(d / f"agent-{sha}.jsonl", [
        {"type": "result", "usage": {"input_tokens": 10, "output_tokens": 5,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}])
    mpath = tmp_path / "rounds" / "harnessed" / "agents_manifest.json"
    mpath.parent.mkdir(parents=True)
    mpath.write_text(json.dumps([
        {"ordinal": 0, "label": "finalize", "phase": "Finalize", "model": "haiku"}]),
        encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT), str(d), "--manifest", str(mpath)],
                       capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    econ = json.loads((d / "economics.json").read_text())
    assert econ["totals"]["agents"] == 1
    assert econ["agents"][0]["label"] == "finalize"
    assert econ["agents"][0]["phase"] == "Finalize"
    assert econ["agents"][0]["total_tokens"] == 15


def test_manifest_prompt_sha_join_binds_without_ids(tmp_path: Path):
    """The content key: a manifest entry carrying prompt_sha joins its transcript by
    the sha256 of the transcript's first user prompt — no id, no journal needed."""
    import hashlib
    mod = _load_module()
    d = tmp_path / "run"
    d.mkdir()
    prompt = "Run the HARNESSED PRE-PASS for round 1"
    _write_jsonl(d / "agent-xyz.jsonl", [
        {"type": "user", "message": {"content": prompt}},
        {"type": "result", "usage": {"input_tokens": 40, "output_tokens": 2,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}])
    manifest = [{"ordinal": 0, "label": "prepass#1", "phase": "Detect",
                 "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()}]
    agents = mod.collect_agents(d, manifest=manifest)
    assert len(agents) == 1
    assert agents[0]["label"] == "prepass#1" and agents[0]["total_tokens"] == 42


def test_manifest_unclaimed_real_usage_transcript_still_counts(tmp_path: Path):
    """The orphan/phantom law holds in manifest mode: a transcript the manifest never
    claimed (the manifest-writer/economics bookkeepers) COUNTS when it has real usage,
    while a zero-usage leftover is DROPPED."""
    mod = _load_module()
    d = tmp_path / "run"
    d.mkdir()
    sha = "abcdef0123456789abcdef0123456789"
    _write_jsonl(d / "journal.jsonl", _harness_journal_rows([sha]))
    _write_jsonl(d / f"agent-{sha}.jsonl", [
        {"type": "result", "usage": {"input_tokens": 10, "output_tokens": 5,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}])
    # the bookkeeper (real usage, not in the manifest) + a garbage leftover (none).
    _write_jsonl(d / "agent-bookkeeper.jsonl", [
        {"type": "result", "usage": {"input_tokens": 7, "output_tokens": 3,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}])
    (d / "agent-empty.jsonl").write_text("", encoding="utf-8")
    (d / "agents_manifest.json").write_text(json.dumps([
        {"ordinal": 0, "label": "prepass#1", "phase": "Detect", "model": "haiku"}]),
        encoding="utf-8")
    agents = mod.collect_agents(d, manifest=mod.load_stage_manifest(d))
    labels = [a["label"] for a in agents]
    assert labels == ["prepass#1", "bookkeeper"]     # counted orphan, dropped phantom
    assert sum(a["total_tokens"] for a in agents) == 15 + 10


def test_harness_journal_without_manifest_collapses_started_result_twins(tmp_path: Path):
    """FALLBACK (no manifest): the harness journal's started+result twins collapse to
    ONE row per agent — the a6 judge's 15-real + 30-phantom pathology cannot recur —
    though rows stay unlabelled (only the manifest can recover the stage)."""
    mod = _load_module()
    d = tmp_path / "run"
    d.mkdir()
    shas = ["a1b2c3d4e5f60718293a4b5c6d7e8f90",
            "0f1e2d3c4b5a69788796a5b4c3d2e1f0"]
    _write_jsonl(d / "journal.jsonl", _harness_journal_rows(shas))
    for sha in shas:
        _write_jsonl(d / f"agent-{sha}.jsonl", [
            {"type": "result", "usage": {"input_tokens": 100, "output_tokens": 10,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}])
    agents = mod.collect_agents(d)
    # 2 agents, not 4 (started+result rows) — the twins collapsed; usage joined via
    # the agentId/key fields; no zero-usage phantom rows.
    assert len(agents) == 2
    assert all(a["total_tokens"] == 110 for a in agents)


def test_js_finalize_stage_contract_run_dir_with_colocated_manifest(tmp_path: Path):
    """P8: the exact CLI the project-harnessed Finalize post-stage shells into —
    ``workflow_economics.py <run_dir> --manifest <run_dir>/agents_manifest.json`` — where
    the Finalize agent has copied journal.jsonl + agent-*.jsonl INTO the run dir
    (rounds/harnessed) beside the manifest it already banked. Locks that this invocation
    writes economics.json with NON-EMPTY totals (the contract the JS chain depends on)."""
    run_dir = tmp_path / "rounds" / "harnessed"
    run_dir.mkdir(parents=True)
    sha_a = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    sha_b = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"
    # the harness journal + transcripts the Finalize agent copies in (real shape).
    _write_jsonl(run_dir / "journal.jsonl", _harness_journal_rows([sha_a, sha_b]))
    _write_jsonl(run_dir / f"agent-{sha_a}.jsonl", [
        {"type": "result", "usage": {"input_tokens": 1000, "output_tokens": 200,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
         "duration_ms": 4000}])
    _write_jsonl(run_dir / f"agent-{sha_b}.jsonl", [
        {"type": "result", "usage": {"input_tokens": 500, "output_tokens": 50,
         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
         "duration_ms": 2000}])
    manifest = run_dir / "agents_manifest.json"
    manifest.write_text(json.dumps([
        {"ordinal": 0, "label": "finalize", "phase": "Finalize", "model": "opus"},
        {"ordinal": 1, "label": "agents-manifest", "phase": "Finalize", "model": "haiku"},
    ]), encoding="utf-8")

    r = subprocess.run(
        [sys.executable, str(SCRIPT), str(run_dir), "--manifest", str(manifest)],
        capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    econ = json.loads((run_dir / "economics.json").read_text())
    assert (run_dir / "economics.md").exists()
    t = econ["totals"]
    assert t["agents"] == 2
    assert t["total_tokens"] == 1200 + 550          # non-empty totals: the locked contract
    assert t["output_tokens"] == 250
    assert set(econ["by_phase"]) == {"Finalize"}
    assert econ["by_phase"]["Finalize"]["total_tokens"] == 1750


def test_js_finalize_stage_tolerates_empty_capture(tmp_path: Path):
    """P8 tolerance: if the Finalize agent found no journal/transcripts (nothing copied
    in — only the manifest sits in the run dir), the reader exits 2 ("nothing to read").
    The JS stage maps that to "not captured" and does NOT fail the workflow; this locks
    that exit-2 signal so the stage's tolerant branch stays correct."""
    run_dir = tmp_path / "rounds" / "harnessed"
    run_dir.mkdir(parents=True)
    manifest = run_dir / "agents_manifest.json"
    manifest.write_text(json.dumps([
        {"ordinal": 0, "label": "finalize", "phase": "Finalize", "model": "opus"}]),
        encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(SCRIPT), str(run_dir), "--manifest", str(manifest)],
        capture_output=True, text=True, check=False)
    assert r.returncode == 2                          # nothing to read -> "not captured"
    assert "nothing to read" in r.stderr
    assert not (run_dir / "economics.json").exists()  # no false-positive artifact


def test_empty_run_dir_exits_2(tmp_path: Path):
    d = tmp_path / "empty"
    d.mkdir()
    r = subprocess.run([sys.executable, str(SCRIPT), str(d)],
                       capture_output=True, text=True, check=False)
    assert r.returncode == 2
    assert "nothing to read" in r.stderr


def test_missing_run_dir_exits_2(tmp_path: Path):
    r = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path / "nope")],
                       capture_output=True, text=True, check=False)
    assert r.returncode == 2


# ---------------------------------------------------------------------------
# Fix 0d — the round-keyed cost adapter: by_phase (phase-keyed) rolled into the
# round-ordinal shape the convergence ledger's cost column reads. Phase labels of
# shape mech_r<n>/judge_r<n> -> key "<n>"; every other phase -> key "0" (overhead).
# ---------------------------------------------------------------------------

def _result(tokens: int, cost: float) -> dict:
    """A terminal result row with a reported cost — so the round sums are exact."""
    return {"type": "result", "subtype": "success", "total_cost_usd": cost,
            "usage": {"input_tokens": tokens, "output_tokens": 0,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}


def test_rounds_adapter_maps_mech_and_judge_phases(tmp_path: Path):
    """render_rounds_economics collapses mech_r<n>/judge_r<n> phases onto round key
    "<n>": mech_r1 + judge_r1 sum into round "1"; mech_r2 stands alone as round "2".
    No unmappable phase, so there is NO key "0"."""
    mod = _load_module()
    d = tmp_path / "run"
    d.mkdir()
    _write_jsonl(d / "journal.jsonl", [
        {"agent_id": "m1", "label": "mech", "phase": "mech_r1", "model": "opus"},
        {"agent_id": "j1", "label": "judge", "phase": "judge_r1", "model": "haiku"},
        {"agent_id": "m2", "label": "mech2", "phase": "mech_r2", "model": "opus"},
    ])
    _write_jsonl(d / "agent-m1.jsonl", [_result(1000, 0.10)])
    _write_jsonl(d / "agent-j1.jsonl", [_result(200, 0.02)])
    _write_jsonl(d / "agent-m2.jsonl", [_result(500, 0.05)])

    rounds = mod.render_rounds_economics(mod.build_economics(d))
    assert set(rounds["rounds"]) == {"1", "2"}          # no "0": every phase named a round
    assert rounds["rounds"]["1"] == 0.12                # mech_r1 (0.10) + judge_r1 (0.02)
    assert rounds["rounds"]["2"] == 0.05
    assert rounds["run"]["agents"] == 3                 # the run totals ride along
    assert rounds["derived_from"] == str(d)
    assert "no key '0'" in rounds["note"]


def test_rounds_adapter_overhead_rolls_into_key_0_and_is_named(tmp_path: Path):
    """An unmappable phase (Finalize — run overhead) rolls into key "0", NAMED in the
    note (never silently dropped); mech_r1 keeps its own round key."""
    mod = _load_module()
    d = tmp_path / "run"
    d.mkdir()
    _write_jsonl(d / "journal.jsonl", [
        {"agent_id": "m1", "label": "mech", "phase": "mech_r1", "model": "opus"},
        {"agent_id": "f1", "label": "finalize", "phase": "Finalize", "model": "haiku"},
    ])
    _write_jsonl(d / "agent-m1.jsonl", [_result(1000, 0.10)])
    _write_jsonl(d / "agent-f1.jsonl", [_result(300, 0.03)])

    rounds = mod.render_rounds_economics(mod.build_economics(d))
    assert set(rounds["rounds"]) == {"1", "0"}
    assert rounds["rounds"]["1"] == 0.10
    assert rounds["rounds"]["0"] == 0.03                # Finalize overhead, not dropped
    assert "Finalize" in rounds["note"] and "run overhead" in rounds["note"]


def test_cli_rounds_out_writes_ledger_shape(run_dir: Path, tmp_path: Path):
    """--rounds-out <manuscript_dir> ALSO writes <manuscript_dir>/rounds/economics.json in
    the {"rounds": {...}} wrapper the convergence ledger tolerates. The fixture's Weld/
    Converge phases name no round, so both roll into overhead key "0"."""
    md = tmp_path / "manuscript"
    md.mkdir()
    r = subprocess.run([sys.executable, str(SCRIPT), str(run_dir),
                        "--rounds-out", str(md)],
                       capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    data = json.loads((md / "rounds" / "economics.json").read_text())
    assert set(data) == {"rounds", "run", "derived_from", "note"}
    assert set(data["rounds"]) == {"0"}                 # Weld + Converge are both overhead
    assert data["run"]["agents"] == 2
