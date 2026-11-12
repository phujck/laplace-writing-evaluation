"""WO-20260914-s2-13: exercise the reader, write door, and cold store descent."""
from dataclasses import replace
import base64
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from atlas.errors import ContentHashMismatch, SnapshotRegenerationRefused, StaleOwner, StateTransitionRefused
from atlas.entry import BYTE_CAP, build_entry, descend_event, encode_entry
from atlas.history import AtlasEvent, ConceptricObject, EventKind, RevisionAct, SeatRole
from atlas.ids import canonical_json, hash_bytes
from atlas.snapshot import load_snapshot
from atlas.store import ConceptricStore
from atlas.updown import up
from atlas.updown_history import bind_up_result, promotion_event
from test_snapshot import text_node, write_bundle
from test_updown_history import (setup_store, promote, event, ASSUMPTION, FIBRE,
                                CONTRACT, SOURCE, RUNTIME, PRODUCER, UNKNOWN_CLOSURE)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args]).decode().strip()


def clean_bundle(tmp_path):
    repo = tmp_path / "source"
    repo.mkdir()
    git(repo, "init", "-q")
    data = b"pinned bytes\n"
    (repo / "record.txt").write_bytes(data)
    git(repo, "add", "record.txt")
    git(repo, "-c", "user.name=Atlas test", "-c", "user.email=atlas@example.invalid", "commit", "-qm", "fixture")
    root = write_bundle(tmp_path / "bundle", [text_node("record.txt", data)], {})
    bundle = load_snapshot(root)
    manifest = replace(bundle.manifest, source_repo=str(repo), commit_sha=git(repo, "rev-parse", "HEAD"))
    manifest = replace(manifest, snapshot_id=manifest.computed_id())
    (root / "manifest.json").write_text(canonical_json(manifest.to_dict()))
    return load_snapshot(root), repo, data


def test_regeneration_uses_pinned_commit_verifies_and_caches(tmp_path):
    bundle, repo, data = clean_bundle(tmp_path)
    (repo / "record.txt").write_bytes(b"changed worktree\n")
    assert bundle.read_node_bytes("record.txt") == data
    assert bundle.blobs.get(hash_bytes(data)) == data
    assert not bundle.cache_refusals


def test_regeneration_hash_mismatch_never_caches(tmp_path):
    bundle, repo, data = clean_bundle(tmp_path)
    node = text_node("record.txt", b"forged")
    bundle._nodes = {node.node_id: node}
    with pytest.raises(ContentHashMismatch, match="regenerated Git bytes"):
        bundle.read_node_bytes(node.node_id)
    assert not bundle.blobs.has(node.content_hash)
    assert not bundle.blobs.has(hash_bytes(data))


@pytest.mark.parametrize("cause", ["dirty-tree", "git-unreachable"])
def test_regeneration_refusal_names_door_and_remedy(tmp_path, cause):
    bundle, repo, data = clean_bundle(tmp_path)
    bundle._manifest = replace(bundle.manifest, tree_dirty=cause == "dirty-tree",
                               source_repo=str(tmp_path / "absent"))
    with pytest.raises(SnapshotRegenerationRefused) as caught:
        bundle.read_node_bytes("record.txt")
    assert caught.value.detail["cause"] == cause
    assert caught.value.detail["door"] == "SnapshotBundle.read_node_bytes"
    assert "restore" in str(caught.value)


def promotion(inputs, object_ids):
    receipt = bind_up_result(inputs, up(inputs), object_ids)
    return receipt, promotion_event(
        receipt, occurred_at="2026-08-24T18:01:00Z", producer=SeatRole.EGO, actor=SeatRole.EGO,
        correlation_id="envelope-test", provenance=(SOURCE,), runtime=RUNTIME,
        producer_ref=PRODUCER, goal_residual=UNKNOWN_CLOSURE)


def revision(name, old, new):
    template = event(EventKind.REVISION, RevisionAct(name, tuple(old), tuple(new), "replace member path").to_dict(),
                     assumption=ASSUMPTION, fibre=FIBRE)
    return AtlasEvent.create(
        occurred_at=template.occurred_at, kind=template.kind, producer=template.producer,
        actor=template.actor, subject="revision:" + name, assumption=ASSUMPTION, fibre=FIBRE,
        correlation_id=template.correlation_id, causation_ids=(), provenance=template.provenance,
        residual=template.residual, runtime=template.runtime, producer_ref=template.producer_ref,
        validity=template.validity, payload=template.payload)


def test_torn_member_refused_at_store_seal(tmp_path):
    store, inputs, ids = setup_store(tmp_path / "store")
    ids[inputs.children[0].handle] = "absent-member"
    receipt, packet = promotion(inputs, ids)
    before = store.events()
    with pytest.raises(StateTransitionRefused, match="member object does not resolve") as caught:
        store.append(packet)
    assert caught.value.reason == "state-transition-refused"
    assert store.events() == before
    assert receipt.coarse_object_id not in store.replay().graph_objects


def replacement(store, inputs, ids):
    child = replace(inputs.children[0], handle=hash_bytes(b"replacement"), text="replacement source")
    new_ids = {**ids, child.handle: "leaf:new"}
    del new_ids[inputs.children[0].handle]
    item = ConceptricObject("leaf:new", "source-leaf", child.handle, ASSUMPTION, FIBRE,
                            CONTRACT.contract_id, "fine", (SOURCE,), {})
    leaf = event(EventKind.OBJECT, item.to_dict(), assumption=ASSUMPTION, fibre=FIBRE)
    receipt, promoted = promotion(replace(inputs, children=(child, *inputs.children[1:])), new_ids)
    return leaf, receipt, promoted


@pytest.mark.parametrize("by_hash", [False, True])
def test_stale_owner_refused_at_publication_without_partial_append(tmp_path, by_hash):
    store, inputs, ids = setup_store(tmp_path / "store")
    owner, _ = promote(store, inputs, ids)
    leaf, receipt, promoted = replacement(store, inputs, ids)
    source = inputs.children[0].handle if by_hash else ids[inputs.children[0].handle]
    before = store.events()
    with pytest.raises(StaleOwner) as caught:
        store.append_many((leaf, revision("leaf-only", [source], ["leaf:new"])))
    assert caught.value.reason == "stale-owner"
    assert caught.value.detail["owner"] == owner.coarse_object_id
    assert store.events() == before
    assert "leaf:new" not in store.replay().graph_objects


def test_whole_owner_path_with_successors_publishes_atomically(tmp_path):
    store, inputs, ids = setup_store(tmp_path / "store")
    owner, _ = promote(store, inputs, ids)
    leaf, successor, promoted = replacement(store, inputs, ids)
    packet = (leaf, promoted,
              revision("leaf", [ids[inputs.children[0].handle]], ["leaf:new"]),
              revision("owner", [owner.coarse_object_id], [successor.coarse_object_id]))
    assert len(store.append_many(packet)) == 4
    assert store.append_many(packet) == store.append_many(packet)
    assert successor.coarse_object_id in store.replay().graph_objects


def test_owner_successor_must_be_a_real_new_node(tmp_path):
    store, inputs, ids = setup_store(tmp_path / "store")
    owner, _ = promote(store, inputs, ids)
    with pytest.raises(StaleOwner, match="replacement must resolve"):
        store.append_many((revision("leaf", [inputs.children[0].handle], ["new-leaf"]),
                           revision("owner", [owner.coarse_object_id], ["imagined-owner"])))


def test_every_current_owner_is_required_and_lost_index_rebuilds(tmp_path):
    store, inputs, ids = setup_store(tmp_path / "store")
    owner, _ = promote(store, inputs, ids)
    other, _ = promote(store, replace(inputs, chi=2), ids)
    leaf, successor, promoted = replacement(store, inputs, ids)
    store.projection_path.unlink()
    before = store.events()
    with pytest.raises(StaleOwner) as caught:
        store.append_many((leaf, promoted,
                           revision("leaf", [inputs.children[0].handle], ["leaf:new"]),
                           revision("owner", [owner.node_handle], [successor.node_handle])))
    assert caught.value.detail["owner"] == other.coarse_object_id
    assert store.events() == before


def test_entry_computed_and_all_record_bytes_reached_without_enumeration(tmp_path, monkeypatch):
    store, inputs, ids = setup_store(tmp_path / "store")
    for index in range(10):
        store.append(event(EventKind.OBSERVATION, {"schema_version": "test-observation/1", "sample": index}))
    expected = {e.event_id: canonical_json(e.to_dict()).encode() for e in store.events()}
    def forbidden(*args, **kwargs):
        raise AssertionError("cold descent cannot enumerate directories or replay history")
    monkeypatch.setattr(Path, "glob", forbidden)
    monkeypatch.setattr(Path, "iterdir", forbidden)
    monkeypatch.setattr(ConceptricStore, "events", forbidden)
    monkeypatch.setattr(ConceptricStore, "replay", forbidden)
    entry = build_entry(store.root)
    assert len(encode_entry(entry)) <= BYTE_CAP
    assert not entry["enumerated_store_dirs"]
    assert entry["snapshot_id"] is None
    assert any(i["owner"] == "snapshot-export-registration" for i in entry["issues"])
    reached = {}
    while True:
        for ref in entry["records"]:
            offset, data = 0, b""
            while True:
                page = descend_event(store.root, ref["handle"], offset=offset, expected_head=entry["head"])
                assert len(encode_entry(page)) <= BYTE_CAP
                chunk = base64.b64decode(page["bytes_base64"])
                data += chunk
                offset += len(chunk)
                if page["next"] is None:
                    break
            assert hash_bytes(data) == page["content_hash"]
            reached[ref["handle"]] = data
        if min(row["sequence"] for row in entry["records"]) == 1:
            break
        entry = build_entry(store.root, before=min(row["sequence"] for row in entry["records"]),
                            expected_head=entry["head"])
    assert reached == expected


def test_entry_roots_come_from_completed_generation(tmp_path):
    from test_blueprint import fixtures, write_fixture
    from atlas.blueprint import pour_blueprint
    docs = write_fixture(tmp_path)
    encoder, contract, metadata, bindings = fixtures(tmp_path)
    store = ConceptricStore(tmp_path / "blueprint")
    generation = pour_blueprint(store, tmp_path, docs, bindings, encoder, contract, metadata)
    entry = build_entry(store.root)
    assert entry["blueprint_generation"]["handle"] == generation.generation_id
    assert {r["handle"] for r in entry["fibre_roots"]}.issubset({c["node_handle"] for c in generation.clusters})
    assert entry["fibre_roots"]
    assert len(encode_entry(entry)) <= BYTE_CAP


def test_default_entry_selects_manifest_blueprint_among_two_stores(tmp_path, monkeypatch, capsys):
    from atlas import entry
    from atlas.ids import chash
    container = tmp_path / "container"
    blueprint, _, _ = setup_store(container / "stores" / "self-hosting-renamed")
    dataset, _, _ = setup_store(container / "stores" / "dataset")
    (container / "blueprint_manifest.json").write_text(json.dumps({
        "schema_version": "atlas.blueprint-manifest/1", "store": "atlas/stores/self-hosting-renamed"}))
    core = {"dataset_id": "fixture", "store": "stores/dataset"}
    manifest = {"schema_version": "atlas.dataset-manifest/1", "core": core}
    manifest["manifest_handle"] = chash(manifest)
    (container / "datasets").mkdir()
    (container / "datasets" / "fixture.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(entry, "CONTAINER_ROOT", container)
    # A discoverable dataset snapshot must never override the self-hosting store.
    from atlas.tools import build_spans
    snapshot = container / "dataset-snapshot"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text("{}")
    monkeypatch.setattr(build_spans, "dataset_snapshot_dir", lambda *args: snapshot)
    assert entry.default_store() == blueprint.root
    monkeypatch.setattr("sys.argv", ["atlas.entry", "--json"])
    assert entry.main() == 0
    page = json.loads(capsys.readouterr().out)
    assert page["serving_store"]["path"] == str(blueprint.root)
    assert "blueprint-generation" in page["serving_store"]["reason"]
    assert page["head"] == build_entry(blueprint.root)["head"]
    assert page["dataset_manifests"] == [{"handle": manifest["manifest_handle"],
                                         "descend": entry._command(dataset.root)}]
    monkeypatch.setattr("sys.argv", ["atlas.entry", "--json", "--store", str(dataset.root)])
    assert entry.main() == 0
    explicit = json.loads(capsys.readouterr().out)
    assert explicit["serving_store"] == {"path": str(dataset.root), "reason": "explicit store selection"}
    assert len(encode_entry(page)) < BYTE_CAP


@pytest.mark.parametrize("target", ["../outside", "", "/outside"])
def test_default_store_refuses_invalid_blueprint_target(tmp_path, monkeypatch, target):
    from atlas import entry
    from atlas.errors import StoreError
    (tmp_path / "blueprint_manifest.json").write_text(json.dumps({
        "schema_version": "atlas.blueprint-manifest/1", "store": target}))
    monkeypatch.setattr(entry, "CONTAINER_ROOT", tmp_path)
    with pytest.raises(StoreError) as caught:
        entry.default_store()
    assert caught.value.detail["code"] == "ENTRY-BLUEPRINT-INVALID"


def test_registered_snapshot_verification_is_banked_by_snapshot_id(tmp_path, monkeypatch):
    from atlas import entry, snapshot
    from atlas.tools import build_spans

    container = tmp_path / "container"
    bundle = container / "bundle"
    bundle.mkdir(parents=True)
    (bundle / "manifest.json").write_text("{}", encoding="utf-8")
    handle = "sha256:" + "a" * 64
    pinned = "b" * 40
    dataset = {"schema_version": "atlas.dataset-manifest/1", "manifest_handle": handle,
               "core": {"dataset_id": "fixture", "pinned_commit": pinned}}
    nodes = [SimpleNamespace(path="one.md", content_hash="sha256:" + "c" * 64)]
    calls = {"verify": 0, "iter_nodes": 0, "segmentation": 0}

    class Bundle:
        manifest = SimpleNamespace(snapshot_id="sha256:" + "d" * 64,
                                   manifest_handle=handle, pinned_commit=pinned,
                                   commit_sha=pinned, sources=["one.md"])

        def verify(self):
            calls["verify"] += 1

        def iter_nodes(self):
            calls["iter_nodes"] += 1
            return iter(nodes)

    monkeypatch.setattr(entry, "CONTAINER_ROOT", container)
    monkeypatch.setattr(entry, "_dataset_registrations", lambda root: iter(((dataset, root),)))
    monkeypatch.setattr(build_spans, "dataset_snapshot_dir", lambda *args: bundle)
    monkeypatch.setattr(build_spans, "verified_segmentation",
                        lambda path: calls.__setitem__("segmentation", calls["segmentation"] + 1))
    monkeypatch.setattr(snapshot, "load_snapshot", lambda path: Bundle())
    prefix = "dataset:fixture://"
    observations = {"events": [{"event": {"event_id": "generation", "payload": {
        "schema_version": "atlas.blueprint-generation/5",
        "source_roots": {prefix + nodes[0].path: nodes[0].content_hash}},
        "provenance": [{"source_id": "atlas:dataset-manifest", "digest": handle}]}}]}

    first = entry._registered_snapshot(tmp_path / "store", observations)
    second = entry._registered_snapshot(tmp_path / "store", observations)
    assert first == second
    assert calls == {"verify": 1, "iter_nodes": 1, "segmentation": 1}
    receipts = list((container / ".cache" / "entry-snapshots").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text())
    assert receipt["manifest_handle"] == handle
    assert receipt["snapshot_id"] == Bundle.manifest.snapshot_id
    receipt["manifest_handle"] = "sha256:" + "e" * 64
    receipts[0].write_text(json.dumps(receipt), encoding="utf-8")
    entry._registered_snapshot(tmp_path / "store", observations)
    assert calls == {"verify": 2, "iter_nodes": 2, "segmentation": 2}
