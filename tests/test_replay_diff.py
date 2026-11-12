"""Contract tests for the constant-diff replay harness."""
import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "replay_diff.py"
spec = importlib.util.spec_from_file_location("replay_diff", SCRIPT)
replay_diff = importlib.util.module_from_spec(spec)
sys.modules["replay_diff"] = replay_diff
spec.loader.exec_module(replay_diff)  # type: ignore[union-attr]


def _run(seconds, io=None, receipt=100, patch=50):
    return {"seconds": seconds, "io": io or {"rchar": 3, "wchar": 4,
                                               "read_bytes": 5, "write_bytes": 6},
            "receipt_bytes": receipt, "declared_patch_bytes": patch}


def test_repeat_gate_requires_wall_within_ten_percent_and_exact_bytes():
    verdict = replay_diff._stability([_run(10.0), _run(10.8)])
    assert verdict == {"status": "PASS", "wall_fraction": 0.074074,
                       "within_10_percent": True, "byte_counts_exact": True}

    changed = _run(10.1, receipt=101)
    verdict = replay_diff._stability([_run(10.0), changed])
    assert verdict["status"] == "FAIL" and not verdict["byte_counts_exact"]


def test_fold_outputs_are_not_reapplied_as_inputs(monkeypatch):
    payload = (b"paper.tex\0.self_graded.json\0contract/journal.jsonl\0"
               b"src/laplace/engine/keeper.py\0SELF_SHARD_INDEX.md\0")

    def fake_git(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout=payload, stderr=b"")

    monkeypatch.setattr(replay_diff, "_git", fake_git)
    assert replay_diff._input_paths("parent", "commit") == [
        "paper.tex", "src/laplace/engine/keeper.py",
    ]


def test_replay_removes_its_named_scratch(monkeypatch, tmp_path):
    scratch = tmp_path / ".scratch-odiff-a"
    monkeypatch.setattr(replay_diff, "SCRATCH", scratch)
    monkeypatch.setattr(replay_diff, "_input_paths", lambda parent, commit: ["x"])

    def fake_git(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="parent\n", stderr="")

    monkeypatch.setattr(replay_diff, "_git", fake_git)
    monkeypatch.setattr(replay_diff, "_one_run",
                        lambda commit, parent, paths, index: _run(1.0))

    report = replay_diff.replay(["commit"], repeat=1)

    assert report["commits"][0]["stability"]["status"] == "UNASSESSED"
    assert not scratch.exists()
