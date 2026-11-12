import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from atlas.encoders.bge_onnx import BgeOnnxEncoder
from atlas.ids import canonical_json, chash
from atlas.store import ConceptricStore
from atlas.tools import blueprint as tool


def test_default_store_target_is_the_manifest_authority():
    target, custody = tool._store_target(
        {"store": "atlas/stores/blueprint"}, None,
    )
    assert target == (tool.ROOT / "atlas/stores/blueprint").resolve()
    assert custody == "manifest-authority"


def test_candidate_store_is_isolated_and_carries_no_promotion_claim(tmp_path: Path):
    target, custody = tool._store_target(
        {"store": "atlas/stores/blueprint"}, tmp_path / "candidate",
    )
    assert target == (tmp_path / "candidate").resolve()
    assert custody == "candidate-no-promotion-claim"


def test_candidate_label_cannot_alias_the_manifest_authority():
    authority = tool.ROOT / "atlas/stores/blueprint"
    with pytest.raises(SystemExit, match="resolves to the manifest authority"):
        tool._store_target({"store": "atlas/stores/blueprint"}, authority)


def test_manifest_spec_matches_model_bytes_and_excludes_provider_from_semantic_identity(monkeypatch):
    monkeypatch.setenv(
        "LAPLACE_EMBED_MODEL_DIR",
        str(tool.ROOT / "models" / "fastembed" / "fast-bge-small-en-v1.5"),
    )
    raw = tool._load(tool.DEFAULT_MANIFEST)
    contract = tool._contract(raw)
    cpu = BgeOnnxEncoder(providers=("CPUExecutionProvider",))
    cuda = BgeOnnxEncoder(
        providers=("CUDAExecutionProvider", "CPUExecutionProvider"),
    )

    assert contract.lens_id == "atlas-blueprint-governing-design/1"
    assert contract.encoder_spec == cpu.spec == cuda.spec


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def test_pinned_documents_read_head_blobs_and_expand_recursive_globs(tmp_path):
    repo = tmp_path / "repo"
    (repo / "atlas/src/atlas/nested").mkdir(parents=True)
    (repo / "design.md").write_text("committed\n")
    (repo / "atlas/src/atlas/direct.py").write_text("DIRECT = 1\n")
    (repo / "atlas/src/atlas/nested/deep.py").write_text("DEEP = 1\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run([
        "git", "-C", str(repo), "-c", "user.name=Fixture",
        "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture",
    ], check=True)
    pin = _git(repo, "rev-parse", "HEAD")
    (repo / "design.md").write_text("working tree must not enter\n")
    raw = {"commit_sha": pin, "documents": [
        {"path": "design.md", "role": "law", "document_id": "design"},
        {"glob": "atlas/src/atlas/**/*.py", "role": "source"},
    ]}

    documents, contents, commit_sha, counts = tool._pinned_documents(raw, repo)

    assert commit_sha == pin
    assert contents["design.md"] == b"committed\n"
    assert {document.path for document in documents} == {
        "design.md", "atlas/src/atlas/direct.py", "atlas/src/atlas/nested/deep.py",
    }
    assert counts["atlas/src/atlas/**/*.py"] == 2


def test_pour_refuses_adopt_because_the_seal_is_one_way(tmp_path, capsys):
    """--adopt is REFUSED, and that refusal is the contract (2026-09-15).

    The first implementation reached back into the engine - `from laplace import atlas_bridge`
    plus a sys.path insertion - so the atlas imported laplace and atlas/tests/test_seal.py caught
    it on the close's floor. The adoption transition lives engine-side, so the sequence is two
    orchestrator acts with no file change between; making it one process is
    WO-20260915-the-adoption-door-belongs-to-the-atlas.
    """

    import atlas.tools.blueprint as tool

    with pytest.raises(SystemExit) as caught:
        tool._prepare_authority_epoch(tmp_path / "blueprint")
    message = str(caught.value)
    assert "--adopt is refused" in message
    assert "atlas_adopt_authority.py" in message, "the refusal must name the door that does work"
    assert "seal" in message


