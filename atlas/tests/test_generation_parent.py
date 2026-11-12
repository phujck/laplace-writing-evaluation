"""C4: consume lineage and persisted receipts through cold temporary-store reads.

Synthetic source geometry is deliberate; no live dataset is ever poured here.
"""
from dataclasses import replace
import json

import pytest

from atlas.blueprint import (
    BLUEPRINT_GENERATION_SCHEMA, GENESIS_GENERATION, BlueprintGeneration,
    GenerationParentRefused, current_blueprint_generation, generation_rows_diff,
    pour_blueprint, reconstruct_blueprint,
)
from atlas.ids import chash
from atlas.store import ConceptricStore
from test_blueprint import fixtures, write_fixture
from test_dataset_door import fixture, git, metadata
from atlas.dataset import mint_manifest, pour_dataset


def setup_pour(root):
    docs = write_fixture(root)
    encoder, contract, meta, _ = fixtures(root)
    store = ConceptricStore(root / "store")
    return store, docs, encoder, contract, meta


def test_first_pour_genesis_and_required_hashed_parent(tmp_path):
    store, docs, encoder, contract, meta = setup_pour(tmp_path)
    generation = pour_blueprint(store, tmp_path, docs, (), encoder, contract, meta,
                                parent_generation=GENESIS_GENERATION)
    assert generation.schema_version == BLUEPRINT_GENERATION_SCHEMA
    assert generation.parent_generation == GENESIS_GENERATION
    assert generation.hashed_dict()["parent_generation"] == GENESIS_GENERATION
    fields = generation.hashed_dict()
    del fields["parent_generation"]
    with pytest.raises(GenerationParentRefused):
        BlueprintGeneration.create(**fields)
    fields["parent_generation"] = "sha256:" + "e" * 64
    assert BlueprintGeneration.create(**fields).generation_id != generation.generation_id
    assert generation.receipt.moved_rows["added"]["count"] == len(generation.clauses)
    assert current_blueprint_generation(ConceptricStore(store.root, read_only=True)) == generation


@pytest.mark.parametrize("parent", [None, GENESIS_GENERATION, "sha256:" + "e" * 64])
def test_existing_generation_refuses_missing_genesis_or_wrong_parent_without_writes(tmp_path, parent):
    store, docs, encoder, contract, meta = setup_pour(tmp_path)
    first = pour_blueprint(store, tmp_path, docs, (), encoder, contract, meta)
    before = store.events()
    args = {} if parent is None else {"parent_generation": parent}
    with pytest.raises(GenerationParentRefused, match="this dataset already has a generation") as caught:
        pour_blueprint(store, tmp_path, docs, (), encoder, contract, meta, **args)
    assert caught.value.detail["expected_parent_generation"] == first.generation_id
    assert store.events() == before


def test_second_pour_banks_five_unsummed_costs_and_exact_changed_source_rows(tmp_path, monkeypatch):
    store, docs, encoder, contract, meta = setup_pour(tmp_path)
    first = pour_blueprint(store, tmp_path, docs, (), encoder, contract, meta)
    target = tmp_path / "design/atomic.md"
    target.write_text(target.read_text().replace("alpha one", "alpha revised"))
    calls, vectors = [], []
    embed = encoder.embed

    def measured(texts):
        calls.append(tuple(texts))
        result = embed(texts)
        vectors.extend(result)
        return result

    monkeypatch.setattr(encoder, "embed", measured)
    second = pour_blueprint(store, tmp_path, docs, (), encoder, contract, meta,
                            parent_generation=first.generation_id, commit_sha="a" * 40)
    cold = current_blueprint_generation(ConceptricStore(store.root, read_only=True))
    assert cold == second
    receipt = cold.receipt
    assert receipt.parent_generation == first.generation_id
    assert receipt.commit_sha == "a" * 40
    assert receipt.generation_id == second.generation_id
    assert set(receipt.costs) == {
        "wall_seconds", "bytes_read", "encoder_calls", "records_touched", "vectors_built",
    }
    assert receipt.costs["wall_seconds"] > 0
    assert receipt.costs["bytes_read"] == sum((tmp_path / d.path).stat().st_size for d in docs)
    assert receipt.costs["encoder_calls"] == len(calls) == len(second.clauses)
    assert receipt.costs["vectors_built"] == len(vectors) == len(second.clauses)
    assert receipt.costs["records_touched"] == len(first.clauses) + len(second.clauses)
    changed = receipt.moved_rows["changed"]
    assert changed["ids"] == sorted(row["logical_id"] for row in second.clauses
                                     if row["source_path"] == "design/atomic.md")
    assert changed["count"] == 1
    assert all(row["before_content_handle"] != row["after_content_handle"] for row in changed["rows"])
    assert receipt.moved_rows["added"]["count"] == receipt.moved_rows["removed"]["count"] == 0
    assert "receipt" not in second.hashed_dict() and "costs" not in second.hashed_dict()
    altered = replace(second, receipt=replace(receipt, costs={**receipt.costs, "wall_seconds": 999.0}))
    assert chash(altered.hashed_dict()) == second.generation_id
    result = reconstruct_blueprint(ConceptricStore(store.root, read_only=True), tmp_path,
                                   "alpha atomic", encoder, meta, beam=2, top_k=4)
    assert result.generation_id == second.generation_id
    assert any("alpha revised" in row["text"] for row in result.results)
    with pytest.raises(GenerationParentRefused):
        pour_blueprint(store, tmp_path, docs, (), encoder, contract, meta,
                       parent_generation=first.generation_id)


def test_row_diff_added_removed_changed_ignores_location_only_changes():
    before = [{"logical_id": "a", "content_handle": "old"},
              {"logical_id": "b", "content_handle": "same", "source_hash": "old-file"},
              {"logical_id": "c", "content_handle": "removed"}]
    after = [{"logical_id": "a", "content_handle": "new"},
             {"logical_id": "b", "content_handle": "same", "source_hash": "new-file"},
             {"logical_id": "d", "content_handle": "added"}]
    diff = generation_rows_diff(before, after)
    assert {kind: row["ids"] for kind, row in diff.items()} == {
        "added": ["d"], "removed": ["c"], "changed": ["a"],
    }
    assert all(row["count"] == 1 for row in diff.values())
    assert diff["changed"]["rows"] == [{"logical_id": "a", "before_content_handle": "old",
                                         "after_content_handle": "new"}]


@pytest.mark.parametrize("schema", ["atlas.blueprint-generation/4", "atlas.blueprint-generation/5"])
def test_legacy_generation_preserves_original_hash_and_absent_parent(tmp_path, schema):
    store, docs, encoder, contract, meta = setup_pour(tmp_path)
    generation = pour_blueprint(store, tmp_path, docs, (), encoder, contract, meta)
    fields = generation.hashed_dict()
    fields["schema_version"] = schema
    del fields["parent_generation"]
    if schema.endswith("/4"):
        for key in ("lens_id", "encoder_spec", "encoder_runtime_evidence"):
            del fields[key]
    raw = {**fields, "generation_id": chash(fields)}
    restored = BlueprintGeneration.from_dict(raw)
    assert restored.parent_generation is None
    assert restored.to_dict() == raw


def test_qrc_dataset_requires_exact_previous_generation_in_temporary_store(fixture):
    root, core, encoder = fixture
    core.update(dataset_id="qrc", store="stores/qrc")
    manifest = mint_manifest(core, root)
    meta = metadata(root, encoder)
    first = pour_dataset(manifest, root, root / "atlas", encoder, meta,
                          parent_generation=GENESIS_GENERATION)
    store = ConceptricStore(root / "atlas/stores/qrc", read_only=True)
    before = store.events()
    with pytest.raises(GenerationParentRefused, match="this dataset already has a generation"):
        pour_dataset(manifest, root, root / "atlas", encoder, meta)
    assert store.events() == before
    path = root / "manuscript/a.tex"
    path.write_text(path.read_text().replace("x=1", "x=2"))
    git(root, "add", "manuscript/a.tex")
    git(root, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "changed fixture source")
    core["pinned_commit"] = git(root, "rev-parse", "HEAD")
    second = pour_dataset(mint_manifest(core, root), root, root / "atlas", encoder, meta,
                           parent_generation=first["generation_id"])
    assert second["parent_generation"] == first["generation_id"]
    assert second["pour_receipt"] == current_blueprint_generation(store).receipt.to_dict()
    assert second["pour_receipt"]["moved_rows"]["changed"]["ids"] == [
        row["logical_id"] for row in current_blueprint_generation(store).clauses
        if row["source_path"] == "manuscript/a.tex"
    ]


def test_dataset_cli_passes_parent_and_prints_typed_refusal(fixture, monkeypatch, capsys):
    from atlas.tools import pour_dataset as tool
    root, core, encoder = fixture
    manifest = mint_manifest(core, root)
    meta = metadata(root, encoder)
    monkeypatch.setattr(tool, "load_manifest", lambda *_: manifest)
    monkeypatch.setattr(tool, "_runtime_encoder", lambda *a, **kw:
                        (encoder, meta.runtime, ("deterministic-python",), meta.encoder_runtime_evidence))
    args = ["pour_dataset", "--manifest", str(root / "manifest.json"),
            "--repo-root", str(root), "--container-root", str(root / "atlas")]
    monkeypatch.setattr("sys.argv", args)
    assert tool.main() == 0
    first = json.loads(capsys.readouterr().out)
    assert tool.main() == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused["reason"] == "generation-parent-refused"
    assert refused["message"] == "this dataset already has a generation"
    monkeypatch.setattr("sys.argv", [*args, "--parent-generation", first["generation_id"]])
    assert tool.main() == 0
    second = json.loads(capsys.readouterr().out)
    assert second["parent_generation"] == first["generation_id"]
