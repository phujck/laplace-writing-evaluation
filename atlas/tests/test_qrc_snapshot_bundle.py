"""Pinned qrc bytes consumed by SnapshotView, freezing, and registration-based entry."""
from dataclasses import replace
import json
from pathlib import Path

import pytest

from atlas import entry
from atlas.bench.freeze import anchor_task, freeze_bundle, verify_bundle
from atlas.bench.task import Anchor, BenchTaskBundle
from atlas.bench.universe import FULL_UNIVERSE, SnapshotView
from atlas.dataset import load_manifest, resolve_sources
from atlas.errors import AnchorUnresolved, AtlasError, StoreError
from atlas.ids import hash_bytes
from atlas.snapshot import load_snapshot
from atlas.tools.build_spans import build, build_dataset, dataset_snapshot_dir, verified_segmentation
from atlas.tools.freeze_tasks import build as freeze_tasks

REPO = Path(__file__).resolve().parents[2]
MANIFEST = REPO / "atlas/datasets/qrc.json"
SEED = REPO / "atlas/bench/tasks/source_qrc_seed_2026-09-14.json"


@pytest.fixture()
def qrc(tmp_path):
    container = tmp_path / "atlas"
    root, generation = build_dataset(MANIFEST, REPO, container)
    manifest = load_manifest(MANIFEST, REPO)
    return container, root, generation, manifest


def task_for(view):
    spec = json.loads(SEED.read_text())["tasks"][0]
    return anchor_task(view, **{k: v for k, v in spec.items() if k != "prefer_nodes"},
                       prefer_nodes=tuple(spec["prefer_nodes"]))


def test_qrc_manifest_build_yields_exact_pinned_sources_and_stable_view(qrc):
    container, root, generation, manifest = qrc
    documents, contents = resolve_sources(manifest["core"], REPO)
    snap = load_snapshot(root)
    view = SnapshotView(snap, FULL_UNIVERSE)
    assert view.node_ids == sorted(doc.path for doc in documents)
    assert snap.manifest.sources == view.node_ids
    assert {node: view.node_bytes(node) for node in view.node_ids} == contents
    assert snap.manifest.manifest_handle == manifest["manifest_handle"]
    assert snap.manifest.pinned_commit == manifest["core"]["pinned_commit"]
    assert generation.coverage == 1.0
    assert generation.span_count > 0
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    again, repeated = build_dataset(MANIFEST, REPO, container)
    assert again == root and repeated == generation
    assert before == {p: p.read_bytes() for p in before}
    changed = replace(snap.manifest, manifest_handle="sha256:" + "0" * 64)
    assert changed.computed_id() != snap.manifest.snapshot_id
    with pytest.raises(AtlasError, match="segmentation is frozen"):
        build(root, target_tokens=128)
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize("keep_valid", [False, True])
def test_freeze_refuses_atom_outside_declared_anchor(qrc, keep_valid):
    _, root, generation, _ = qrc
    view = SnapshotView(load_snapshot(root), FULL_UNIVERSE)
    task = task_for(view)
    # A real, correctly hashed span from a different source that lacks this atom.
    span = next(s for s in view.leaf_spans if s.node_id.endswith("sec_r2_weight.tex"))
    wrong = Anchor(span.node_id, span.span_id, view.span_content_hash(span), 0)
    corrupted = replace(task, anchors=([*task.anchors, wrong] if keep_valid else [wrong]))
    with pytest.raises(AnchorUnresolved, match="post-normalizer"):
        freeze_bundle(view, generation.generation_id, [corrupted])


def test_freeze_refuses_wrong_anchor_owner(qrc):
    _, root, generation, _ = qrc
    view = SnapshotView(load_snapshot(root), FULL_UNIVERSE)
    task = task_for(view)
    task = replace(task, anchors=[replace(task.anchors[0], node_id="wrong.tex")])
    with pytest.raises(AnchorUnresolved, match="does not own"):
        freeze_bundle(view, generation.generation_id, [task])


def test_freeze_tool_honours_declared_anchor_and_writes_nothing_on_refusal(qrc, tmp_path):
    _, root, _, _ = qrc
    view = SnapshotView(load_snapshot(root), FULL_UNIVERSE)
    task = task_for(view)
    source = json.loads(SEED.read_text())
    source["tasks"] = [replace(task, atoms=["this atom is absent"]).to_dict()]
    spec = tmp_path / "bad-source.json"
    spec.write_text(json.dumps(source))
    output = tmp_path / "tasks"
    with pytest.raises(AnchorUnresolved):
        freeze_tasks(root, spec, output, "full")
    assert not output.exists()


def test_seed_bundle_round_trip_predictions_hash_and_no_overwrite(qrc, tmp_path):
    _, root, _, manifest = qrc
    result = freeze_tasks(root, SEED, tmp_path / "tasks", "full")
    path = result["path"]
    data = json.loads((path / "tasks.json").read_text())
    bundle = BenchTaskBundle.from_dict(data)
    verify_bundle(bundle, result["view"])
    receipt = json.loads((path / "freeze.json").read_text())
    assert len(bundle.tasks) == receipt["task_count"] == 8
    assert receipt["sampling"]["kind"] == "seed"
    assert receipt["sampling"]["random_query_instrument"] is False
    assert receipt["manifest_handle"] == manifest["manifest_handle"]
    assert receipt["predictions_sha256"] == hash_bytes((path / "predictions.json").read_bytes())
    assert all(a.node_id == t.source for t in bundle.tasks for a in t.anchors)
    frozen = {p: p.read_bytes() for p in path.iterdir()}
    with pytest.raises(AtlasError, match="already exists"):
        freeze_tasks(root, SEED, tmp_path / "tasks", "full")
    assert frozen == {p: p.read_bytes() for p in frozen}


def registered_observations(root, manifest):
    snap = load_snapshot(root)
    prefix = f"dataset:{manifest['core']['dataset_id']}://"
    event = {"event_id": "registered-pour", "payload": {
        "schema_version": "atlas.blueprint-generation/5",
        "source_roots": {prefix + n.path: n.content_hash for n in snap.iter_nodes()}},
        "provenance": [{"source_id": "atlas:dataset-manifest", "digest": manifest["manifest_handle"]}]}
    return {"events": [{"event": event}]}


def catalog(container, manifest, monkeypatch):
    (container / "datasets").mkdir()
    (container / "datasets" / "registered.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(entry, "CONTAINER_ROOT", container)
    return container / manifest["core"]["store"]


def test_entry_resolves_snapshot_from_registered_generation(qrc, monkeypatch):
    container, root, generation, manifest = qrc
    store = catalog(container, manifest, monkeypatch)
    observations = registered_observations(root, manifest)
    result = entry._registered_snapshot(store, observations)
    assert result["snapshot_id"] == generation.snapshot_id
    assert Path(result["path"]) == dataset_snapshot_dir(manifest, container)
    (container / "blueprint_manifest.json").write_text(json.dumps({
        "schema_version": "atlas.blueprint-manifest/1", "store": "stores/self-hosting"}))
    assert entry.default_store() == container / "stores/self-hosting"
    assert entry.default_store() != store
    observations["events"][0]["event"]["provenance"] = []
    assert entry._registered_snapshot(store, observations) is None


def test_entry_refuses_generation_extent_mismatch(qrc, monkeypatch):
    container, root, _, manifest = qrc
    store = catalog(container, manifest, monkeypatch)
    observations = registered_observations(root, manifest)
    observations["events"][0]["event"]["payload"]["source_roots"].popitem()
    with pytest.raises(StoreError, match="disagrees"):
        entry._registered_snapshot(store, observations)


def test_segmentation_metadata_tampering_refuses(qrc):
    _, root, _, _ = qrc
    path = root / "segmentation.json"
    record = json.loads(path.read_text())
    record["span_count"] += 1
    path.write_text(json.dumps(record))
    with pytest.raises(AtlasError, match="identity mismatch"):
        verified_segmentation(root)


def test_qrc_blobless_sources_regenerate_all_sixteen_and_rebuild(qrc):
    import shutil
    _, root, generation, manifest = qrc
    _, expected = resolve_sources(manifest["core"], REPO)
    assert len(expected) == 16
    assert load_snapshot(root).manifest.source_repo == "."
    shutil.rmtree(root / "blobs")
    cold = load_snapshot(root)
    assert {node: cold.read_node_bytes(node) for node in cold.nodes} == expected
    cold.verify()
    assert build(root, generation.target_tokens, generation.hard_cap_tokens) == generation


def test_legacy_qrc_blobless_registration_resolves_without_remint(tmp_path):
    import shutil
    registered = load_manifest(MANIFEST, REPO)
    source = dataset_snapshot_dir(registered, REPO / "atlas")
    root = tmp_path / "legacy"
    root.mkdir()
    for name in ("manifest.json", "nodes.jsonl", "seal_report.json"):
        shutil.copyfile(source / name, root / name)
    before = (root / "manifest.json").read_bytes()
    cold = load_snapshot(root)
    _, expected = resolve_sources(registered["core"], REPO)
    assert len(expected) == 16
    assert {node: cold.read_node_bytes(node) for node in cold.nodes} == expected
    cold.verify()
    assert (root / "manifest.json").read_bytes() == before
