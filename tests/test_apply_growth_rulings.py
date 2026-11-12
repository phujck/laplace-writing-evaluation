"""Scoped tests for scripts/apply_growth_rulings.py — the enrich step that replays the
growth adjudicator's banked KEEP/KILL/REWRITE rulings back onto a corpus conceptric.

Fixture-driven: a synthetic conceptric (nodes carry their essence in ``label``, as the
real ``conceptric_v1.json`` does) plus a synthetic ``proxy_verdicts.jsonl`` of growth
rulings. Proven: a REWRITE rewrites the essence and is idempotent on replay; a KILL
tombstones the essence WITHOUT dropping the node or its edges (dependents survive); a
KEEP is a counted no-op; a foreign-corpus ruling is ignored; ``--dry-run`` writes
nothing. The script derives everything from the banked ledger — it takes no free text.
"""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_apply():
    spec = importlib.util.spec_from_file_location(
        "apply_growth_rulings", ROOT / "scripts" / "apply_growth_rulings.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ag = _load_apply()


# ----------------------------------------------------------------- fixtures
CORPUS = "testcorp"


def _conceptric(tmp_path: Path) -> Path:
    """A minimal conceptric: essence in ``label`` (pour's essence field), plus edges so
    the KILL test can prove the graph survives an essence-blank."""
    concept = {
        "nodes": [
            {"id": "c_rw", "kind": "claim",
             "label": "The old slogan-shaped line that the proxy ruled must be rewritten."},
            {"id": "c_kill", "kind": "claim",
             "label": "A line the proxy ruled should be excised entirely."},
            {"id": "c_keep", "kind": "claim",
             "label": "A grounded line the proxy ruled stands as his voice."},
            {"id": "c_dep", "kind": "claim",
             "label": "A dependent that draws on c_kill and must survive its kill."},
        ],
        "edges": [
            {"src": "c_dep", "dst": "c_kill", "rel": "draws"},
            {"src": "c_rw", "dst": "c_keep", "rel": "draws"},
        ],
    }
    p = tmp_path / "conceptric_v1.json"
    p.write_text(json.dumps(concept, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def _subject(node_id: str, essence_prefix: str, corpus: str = CORPUS) -> str:
    return f"conceptric[{corpus}]:{node_id} :: {essence_prefix[:120]}"


def _rulings(tmp_path: Path) -> Path:
    """A proxy_verdicts.jsonl with one REWRITE, one KILL, one KEEP for CORPUS, plus a
    REWRITE addressed to a DIFFERENT corpus (must be ignored)."""
    rows = [
        {"kind": "growth", "id": "PV-rw-1", "ruling": "REWRITE: the truer line",
         "rewrite_text": "A grounded, generator-owned replacement line.",
         "decision": {"kind": "deslop-keep-kill-rewrite",
                      "subject": _subject("c_rw", "The old slogan-shaped line")}},
        {"kind": "growth", "id": "PV-kill-1", "ruling": "KILL: excise it",
         "rewrite_text": None,
         "decision": {"kind": "deslop-keep-kill-rewrite",
                      "subject": _subject("c_kill", "A line the proxy ruled")}},
        {"kind": "growth", "id": "PV-keep-1", "ruling": "KEEP: stands as his voice",
         "decision": {"kind": "deslop-keep-kill-rewrite",
                      "subject": _subject("c_keep", "A grounded line")}},
        {"kind": "growth", "id": "PV-other-1", "ruling": "REWRITE: not ours",
         "rewrite_text": "should never land",
         "decision": {"kind": "deslop-keep-kill-rewrite",
                      "subject": _subject("c_rw", "elsewhere", corpus="othercorp")}},
    ]
    p = tmp_path / "proxy_verdicts.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    concept = _conceptric(tmp_path)
    _rulings(tmp_path)
    return concept, tmp_path


def _load(concept_path: Path) -> dict:
    data = json.loads(concept_path.read_text(encoding="utf-8"))
    return {n["id"]: n for n in data["nodes"]}


# ----------------------------------------------------------------- REWRITE + idempotent
def test_rewrite_applies_then_is_idempotent(tmp_path):
    concept, root = _setup(tmp_path)
    report = ag.run(concept, CORPUS, root, dry_run=False)

    nodes = _load(concept)
    assert nodes["c_rw"]["label"] == "A grounded, generator-owned replacement line."
    rw = next(a for a in report["actions"] if a["node"] == "c_rw")
    assert rw["status"] == "applied"
    assert rw["old"].startswith("The old slogan-shaped line")

    # replay: the essence already equals rewrite_text → unchanged, nothing written
    before = concept.read_text(encoding="utf-8")
    report2 = ag.run(concept, CORPUS, root, dry_run=False)
    assert report2["wrote"] is False
    assert concept.read_text(encoding="utf-8") == before
    rw2 = next(a for a in report2["actions"] if a["node"] == "c_rw")
    assert rw2["status"] == "unchanged"


# ----------------------------------------------------------------- KILL keeps the graph
def test_kill_tombstones_without_dropping_node_or_edges(tmp_path):
    concept, root = _setup(tmp_path)
    ag.run(concept, CORPUS, root, dry_run=False)

    data = json.loads(concept.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in data["nodes"]}
    # the node still exists; its essence is a tombstone naming the ruling
    assert "c_kill" in nodes
    assert nodes["c_kill"]["label"] == "(killed by PV-kill-1)"
    # NEVER drop the node or its edges — the dependent still reconstructs
    assert "c_dep" in nodes
    assert {"src": "c_dep", "dst": "c_kill", "rel": "draws"} in data["edges"]
    assert len(data["edges"]) == 2


# ----------------------------------------------------------------- KEEP no-op
def test_keep_is_counted_noop(tmp_path):
    concept, root = _setup(tmp_path)
    report = ag.run(concept, CORPUS, root, dry_run=False)
    keep = next(a for a in report["actions"] if a["node"] == "c_keep")
    assert keep["status"] == "noop-keep"
    nodes = _load(concept)
    assert nodes["c_keep"]["label"] == "A grounded line the proxy ruled stands as his voice."


# ----------------------------------------------------------------- corpus filter
def test_foreign_corpus_ruling_ignored(tmp_path):
    concept, root = _setup(tmp_path)
    report = ag.run(concept, CORPUS, root, dry_run=False)
    ids = {a["ruling_id"] for a in report["actions"]}
    assert "PV-other-1" not in ids                    # othercorp subject filtered out
    assert report["considered"] == 3                  # only the three CORPUS rulings


# ----------------------------------------------------------------- dry-run writes nothing
def test_dry_run_writes_nothing(tmp_path):
    concept, root = _setup(tmp_path)
    before = concept.read_text(encoding="utf-8")
    report = ag.run(concept, CORPUS, root, dry_run=True)
    assert report["dry_run"] is True and report["wrote"] is False
    assert concept.read_text(encoding="utf-8") == before        # untouched on disk
    # yet the report still shows what WOULD change
    assert any(a["status"] == "applied" for a in report["actions"])


# ----------------------------------------------------------------- unresolved node
def test_unresolved_node_reported_not_fatal(tmp_path):
    concept = _conceptric(tmp_path)
    rows = [{"kind": "growth", "id": "PV-ghost", "ruling": "REWRITE: x",
             "rewrite_text": "y",
             "decision": {"kind": "deslop-keep-kill-rewrite",
                          "subject": _subject("c_missing", "no such node")}}]
    (tmp_path / "proxy_verdicts.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    report = ag.run(concept, CORPUS, tmp_path, dry_run=False)
    ghost = next(a for a in report["actions"] if a["ruling_id"] == "PV-ghost")
    assert ghost["status"] == "unresolved"
    assert report["wrote"] is False


# ----------------------------------------------------------------- CLI path
def test_main_dry_run_cli(tmp_path, capsys):
    concept, root = _setup(tmp_path)
    rc = ag.main(["--conceptric", str(concept), "--corpus", CORPUS,
                  "--root", str(root), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "apply_growth_rulings" in out
