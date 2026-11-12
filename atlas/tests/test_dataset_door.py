"""The dataset door is consumed by a pinned pour and cold blueprint reconstruction."""
import copy
import json
import subprocess
from pathlib import Path

import pytest

from atlas.dataset import (DatasetRefused, SEALED_PREFIXES, extra_authority_files,
                           load_manifest, mint_manifest, pour_dataset, resolve_sources)
from atlas.blueprint import reconstruct_blueprint
from atlas.encoders.base import EncoderRuntimeEvidence
from atlas.encoders.deterministic import SyntheticEncoder
from atlas.history import ProducerRef, SeatRole, SourceRef
from atlas.ids import chash, hash_bytes
from atlas.runtime import collect_runtime_receipt
from atlas.segment import segment_bytes
from atlas.spectral_pour import PourMetadata
from atlas.store import ConceptricStore


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args]).decode().strip()


def core_for(pin, encoder):
    return {"dataset_id": "fixture", "store": "stores/fixture", "pinned_commit": pin,
            "sources": [{"glob": "manuscript/*.tex", "include": [], "exclude": [],
                         "role": "manuscript", "document_id_from": "path", "kind": "source"}],
            "segmentation": {"generation": "seg/1", "target_tokens": 384,
                             "hard_cap_tokens": 512, "segmenters": {"tex/1": "seg/3"}},
            "encoder": {"generation": encoder.spec.spec_id, "model_dir": "synthetic://fixture",
                        "spec": encoder.spec.to_dict()},
            "spectral": {"assumption": "the fixture is pinned source content", "fibre": "dataset-fixture",
                         "grade_contract_id": "dataset-fixture/1", "axis": "source-detail",
                         "lens_id": "fixture/1", "metric_version": "cosine-affinity/1",
                         "cluster_count": 2, "chi": 1, "phi": 0.85,
                         "placement_operator": "cosine-affinity-spectral-fixed-k/1",
                         "entry_role": "manuscript"}}


@pytest.fixture
def fixture(tmp_path):
    (tmp_path / "manuscript").mkdir()
    (tmp_path / "manuscript/a.tex").write_text("\\section{Reservoir}\nQuantum reservoirs retain exact equations $x=1$.\n")
    (tmp_path / "manuscript/b.tex").write_text("\\section{Measurement}\nPhoton measurements determine the response spectrum.\n")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "manuscript")
    git(tmp_path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
    encoder = SyntheticEncoder()
    return tmp_path, core_for(git(tmp_path, "rev-parse", "HEAD"), encoder), encoder


def metadata(root, encoder):
    return PourMetadata("2026-09-14T19:00:00Z", SeatRole.EGO, SeatRole.EGO, "dataset-test",
                        (SourceRef("test:dataset", "sha256:" + "a" * 64, None),),
                        collect_runtime_receipt(root, observed_at="2026-09-14T19:00:00Z"),
                        ProducerRef("test", "synthetic", "dataset-test"),
                        EncoderRuntimeEvidence.exact_single_provider(encoder.spec, "deterministic-python", "sha256:" + "f" * 64))


@pytest.mark.parametrize("prefix", ["soul/", "soul_corpus/", "archive/soul_dump/", "soul_vectors/"])
def test_manifest_refuses_sealed_at_mint(fixture, prefix):
    root, core, _ = fixture
    core["sources"][0] = {**core["sources"][0], "glob": prefix + "*.tex"}
    with pytest.raises(DatasetRefused, match="SEALED-SOURCE"):
        mint_manifest(core, root)


def test_missing_pin_refuses(fixture):
    root, core, _ = fixture
    del core["pinned_commit"]
    with pytest.raises(DatasetRefused, match="PINNED-COMMIT-REQUIRED"):
        mint_manifest(core, root)


def test_core_identity_survives_later_judgement(fixture):
    root, core, _ = fixture
    first = mint_manifest(core, root)
    second = mint_manifest(core, root, judgement={"review_ref": "test:independent"})
    assert first["manifest_handle"] == second["manifest_handle"]
    assert first["core"]["dataset_id"] == second["core"]["dataset_id"]
    assert first["judgement_ref"] != second["judgement_ref"]
    assert first["manifest_handle"] == chash({"schema_version": first["schema_version"], "core": first["core"]})
    file = root / "manifest.json"
    file.write_text(json.dumps(second))
    assert load_manifest(file, root) == second
    second["core"]["store"] = "stores/other"
    file.write_text(json.dumps(second))
    with pytest.raises(DatasetRefused, match="MANIFEST-HANDLE-MISMATCH"):
        load_manifest(file, root)


def test_two_file_pour_covers_pinned_bytes_and_reconstructs(fixture):
    root, core, encoder = fixture
    manifest = mint_manifest(core, root)
    original = (root / "manuscript/a.tex").read_text()
    (root / "manuscript/a.tex").write_text("uncommitted replacement must not enter")
    report = pour_dataset(manifest, root, root / "atlas", encoder, metadata(root, encoder))
    assert report["segmentation_coverage"] == 1.0
    assert report["source_files"] == report["leaves"] == 2
    assert report["covered_bytes"] == report["source_bytes"]
    assert report["structure_violations"] == 0 and report["oversize"] == []
    result = reconstruct_blueprint(ConceptricStore(root / "atlas/stores/fixture", read_only=True),
                                   root, "reservoir", encoder, metadata(root, encoder), top_k=2, beam=2,
                                   container_root=root / "atlas", dataset_roots={"fixture": root})
    assert result.generation_id == report["generation_id"]
    assert any(original == row["text"] for row in result.results)
    assert result.source_currency["source_roots"] == "MOVED"


def test_typed_jsonl_rows_keep_subject_identity_across_insertion_and_change(tmp_path):
    rows = tmp_path / "corpus_friction"
    rows.mkdir()
    source = rows / "work_orders.jsonl"
    source.write_text(
        '{"id":"WO-a","what":"first exact obligation"}\n'
        '{"id":"WO-b","what":"second exact obligation"}\n'
    )
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", "corpus_friction/work_orders.jsonl")
    git(tmp_path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "initial rows")
    encoder = SyntheticEncoder()
    core = {
        "dataset_id": "work-orders", "store": "stores/work-orders",
        "pinned_commit": git(tmp_path, "rev-parse", "HEAD"),
        "sources": [{"path": "corpus_friction/work_orders.jsonl", "include": [], "exclude": [],
                     "role": "obligation", "document_id_from": "path", "kind": "typed-row",
                     "row_id_field": "id"}],
        "segmentation": {"generation": "seg/1", "target_tokens": 384, "hard_cap_tokens": 512,
                         "segmenters": {"structured-jsonl/1": "seg/1"}},
        "encoder": {"generation": encoder.spec.spec_id, "model_dir": "synthetic://fixture",
                    "spec": encoder.spec.to_dict()},
        "spectral": {"assumption": "fixture typed obligation rows", "fibre": "dataset-work-orders",
                     "grade_contract_id": "dataset-work-orders/1", "axis": "source-detail",
                     "lens_id": "work-orders/1", "metric_version": "cosine-affinity/1",
                     "cluster_count": 2, "chi": 1, "phi": 0.85,
                     "placement_operator": "cosine-affinity-spectral-fixed-k/1",
                     "entry_role": "obligation"},
    }
    first = pour_dataset(mint_manifest(core, tmp_path), tmp_path, tmp_path / "atlas", encoder,
                         metadata(tmp_path, encoder))
    store_path = tmp_path / "atlas/stores/work-orders"
    first_generation = reconstruct_blueprint(ConceptricStore(store_path, read_only=True), tmp_path,
                                             "second exact obligation", encoder, metadata(tmp_path, encoder),
                                             top_k=2, beam=2, container_root=tmp_path / "atlas",
                                             dataset_roots={"work-orders": tmp_path})
    first_rows = {row["typed_row_id"]: row for row in first_generation.results}
    assert set(first_rows) == {"WO-a", "WO-b"}

    source.write_text(
        '{"id":"WO-new","what":"inserted exact obligation"}\n'
        '{"id":"WO-a","what":"first exact obligation"}\n'
        '{"id":"WO-b","what":"revised second exact obligation"}\n'
    )
    git(tmp_path, "add", "corpus_friction/work_orders.jsonl")
    git(tmp_path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "insert and revise rows")
    core["pinned_commit"] = git(tmp_path, "rev-parse", "HEAD")
    second = pour_dataset(mint_manifest(core, tmp_path), tmp_path, tmp_path / "atlas", encoder,
                          metadata(tmp_path, encoder), parent_generation=first["generation_id"])
    moved = second["pour_receipt"]["moved_rows"]
    assert moved["added"]["count"] == moved["changed"]["count"] == 1
    assert moved["removed"]["count"] == 0
    assert "WO-b" not in moved["added"]["ids"]
    assert second["generation_id"] != first["generation_id"]
    cold = reconstruct_blueprint(ConceptricStore(store_path, read_only=True), tmp_path,
                                 "revised second exact obligation", encoder, metadata(tmp_path, encoder),
                                 top_k=3, beam=2, container_root=tmp_path / "atlas",
                                 dataset_roots={"work-orders": tmp_path})
    revised = next(row for row in cold.results if row.get("typed_row_id") == "WO-b")
    assert revised["logical_id"] == first_rows["WO-b"]["logical_id"]
    assert revised["text"] == '{"id":"WO-b","what":"revised second exact obligation"}\n'


@pytest.mark.parametrize("mutation,issue", [
    ({"store": "../escape"}, "PATH-ESCAPES-ROOT"),
    ({"sealed_prefixes": ["soul/"]}, "SEALED-PREFIXES-NARROWED"),
    ({"pinned_commit": "HEAD"}, "PINNED-COMMIT-REQUIRED"),
])
def test_manifest_refuses_unsafe_core(fixture, mutation, issue):
    root, core, _ = fixture
    core.update(mutation)
    with pytest.raises(DatasetRefused, match=issue):
        mint_manifest(core, root)


def test_tex_coverage_and_named_oversize():
    data = b"\\section{Equation}\n" + b"x" * 3000
    result = segment_bytes("tex-fixture", "fixture.tex", hash_bytes(data), data)
    leaves = sorted((s for s in result.spans if s.is_leaf), key=lambda s: s.start)
    assert b"".join(data[s.start:s.end] for s in leaves) == data
    assert result.oversize and all(row["reason"] for row in result.oversize)
    assert all(s.segmenter_id == "tex/1" for s in result.spans)


def test_single_tex_root_refuses_unselected_include(fixture):
    root, core, _ = fixture
    (root / "manuscript/a.tex").write_text("\\input{b}\n")
    git(root, "add", "manuscript")
    git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "input")
    core["pinned_commit"] = git(root, "rev-parse", "HEAD")
    core["sources"][0].pop("glob")
    core["sources"][0]["path"] = "manuscript/a.tex"
    with pytest.raises(DatasetRefused, match="TEX-INCLUDE-OUTSIDE-DECLARED-ROOT"):
        mint_manifest(core, root)


def test_encoder_model_dial_precedence(tmp_path, monkeypatch):
    from atlas.encoders.bge_onnx import MODEL_DIR_ENV, MODEL_FILE, resolve_model_dir
    env, arg = tmp_path / "env", tmp_path / "arg"
    default = tmp_path / "models/fastembed/fast-bge-small-en-v1.5"
    for path in (env, arg, default):
        path.mkdir(parents=True)
        (path / MODEL_FILE).write_bytes(b"fixture")
    monkeypatch.setenv(MODEL_DIR_ENV, str(env))
    assert resolve_model_dir(arg, repo_root=tmp_path) == env
    monkeypatch.delenv(MODEL_DIR_ENV)
    assert resolve_model_dir(arg, repo_root=tmp_path) == arg
    assert resolve_model_dir(repo_root=tmp_path) == default


def test_actual_sealed_glob_match_refuses_even_if_excluded(fixture):
    root, core, _ = fixture
    (root / 'soul').mkdir()
    (root / 'soul/private.tex').write_text('sealed fixture')
    git(root, 'add', 'soul')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'sealed fixture')
    core['pinned_commit'] = git(root, 'rev-parse', 'HEAD')
    core['sources'][0].update(glob='*/*.tex', exclude=['soul/*'])
    with pytest.raises(DatasetRefused, match='SEALED-SOURCE'):
        mint_manifest(core, root)


def test_symlink_cannot_alias_sealed_source(fixture):
    root, core, _ = fixture
    (root / 'manuscript/alias.tex').symlink_to('../soul/private.tex')
    git(root, 'add', 'manuscript/alias.tex')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'alias')
    core['pinned_commit'] = git(root, 'rev-parse', 'HEAD')
    with pytest.raises(DatasetRefused, match='SOURCE-NOT-REGULAR'):
        mint_manifest(core, root)


def test_bridge_authority_tuple_is_constructed_without_engine_import(tmp_path):
    bridge = tmp_path / 'src/laplace/atlas_bridge.py'
    bridge.parent.mkdir(parents=True)
    bridge.write_text('# caller authority fixture\n')
    assert extra_authority_files(tmp_path) == (bridge.resolve(),)


def test_actual_encoder_window_refuses_before_any_generation(fixture):
    from atlas.errors import StateTransitionRefused
    root, core, encoder = fixture
    encoder.token_lengths = lambda texts: [513] * len(texts)
    encoder.max_tokens = 512
    with pytest.raises(StateTransitionRefused, match='ENCODER-WINDOW-EXCEEDED'):
        pour_dataset(mint_manifest(core, root), root, root / 'atlas', encoder, metadata(root, encoder))
    assert ConceptricStore(root / 'atlas/stores/fixture', read_only=True).events() == ()


def test_tex_delimiter_tail_keeps_bytes_in_a_nonempty_leaf():
    data = b'\\section{Long}\n' + (b'a ' * 510 + b'\n\n') * 4
    result = segment_bytes('tex-tail', 'tail.tex', hash_bytes(data), data,
                           target_tokens=256, hard_cap_tokens=320)
    leaves = sorted((s for s in result.spans if s.is_leaf), key=lambda s: s.start)
    assert all(data[s.start:s.end].strip() for s in leaves)
    assert b''.join(data[s.start:s.end] for s in leaves) == data
