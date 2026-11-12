"""A cold package copy must import and consume frozen snapshot metadata without Git."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_container_relocates(tmp_path: Path) -> None:
    container = Path(__file__).resolve().parents[1]
    relocated = tmp_path / "container"
    relocated.mkdir()
    # the source lives at <checkout>/src/atlas since core consolidation R2; a relocated container carries it under
    # its own src (the same package bytes), beside its tests and bench data
    shutil.copytree(container.parent / "src" / "atlas", relocated / "src" / "atlas",
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".scratch-*"))
    for name in ("tests", "bench"):
        shutil.copytree(
            container / name, relocated / name,
            ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".scratch-*"),
        )
    shutil.copy2(container / "pyproject.toml", relocated / "pyproject.toml")
    assert not (relocated / ".git").exists()
    assert not (relocated.parent / "src" / "laplace").exists()
    env = {
        key: value for key, value in os.environ.items()
        if not key.startswith("GIT_") and key != "PYTHONPATH"
    }
    env.update(PYTHONPATH=str(relocated / "src"), GIT_CEILING_DIRECTORIES=str(tmp_path))
    imported = subprocess.run(
        [sys.executable, "-c", "import atlas, atlas.store, atlas.snapshot, atlas.blueprint"],
        cwd=relocated, env=env, capture_output=True, text=True, timeout=30,
    )
    assert imported.returncode == 0, imported.stdout + imported.stderr

    # The newer, unsegmented snapshot has no segmentation.json. Exercise the latest
    # frozen bundle carrying all four metadata members, without inventing that file.
    members = ("manifest.json", "nodes.jsonl", "seal_report.json", "segmentation.json")
    latest = max(
        (path for path in (container / "stores" / "snapshots").glob("*/manifest.json")
         if all((path.parent / name).is_file() for name in members)),
        key=lambda path: (json.loads(path.read_text())["created_ts"], path.parent.name),
    ).parent
    snapshot = relocated / "stores" / "snapshots" / latest.name
    snapshot.mkdir(parents=True)
    for name in members:
        shutil.copy2(latest / name, snapshot / name)
    cold_read = subprocess.run(
        [sys.executable, "-c", """
import json
from pathlib import Path
import atlas
from atlas.snapshot import load_snapshot
assert Path(atlas.__file__).resolve().is_relative_to(Path.cwd() / 'src')
bundle = load_snapshot(Path('stores/snapshots') / %r)
nodes = list(bundle.iter_nodes())
assert len(nodes) == bundle.manifest.node_count > 0
assert len({node.node_id for node in nodes}) == len(nodes)
print(json.dumps({'snapshot': bundle.root.name, 'nodes': len(nodes)}))
""" % latest.name],
        cwd=relocated, env=env, capture_output=True, text=True, timeout=30,
    )
    assert cold_read.returncode == 0, cold_read.stdout + cold_read.stderr
    observed = json.loads(cold_read.stdout)
    assert observed["snapshot"] == latest.name
    assert observed["nodes"] > 0


def test_relocated_blueprint_reads_store_without_design_or_engine(tmp_path: Path) -> None:
    from test_blueprint import fixtures, write_fixture
    from atlas.blueprint import pour_blueprint, reconstruct_blueprint
    from atlas.store import ConceptricStore

    original = tmp_path / 'original'
    documents = write_fixture(original)
    encoder, contract, metadata, bindings = fixtures(original)
    container = original / 'atlas'
    store = ConceptricStore(container / 'stores/blueprint')
    datasets = {'design': original / 'design', 'implementation': original / 'impl'}
    generation = pour_blueprint(
        store, original, documents, bindings, encoder, contract, metadata,
        container_root=container, dataset_roots=datasets,
    )
    before = reconstruct_blueprint(
        store, original, 'alpha atomic banking', encoder, metadata,
        top_k=2, beam=1, container_root=container, dataset_roots=datasets,
    )
    assert before.source_currency['source_roots'] == 'CURRENT'
    assert 'dataset:design://atomic.md' in generation.source_roots
    relocated = tmp_path / 'detached'
    shutil.copytree(container, relocated)
    checkout = Path(__file__).resolve().parents[2]
    shutil.copytree(checkout / 'src' / 'atlas', relocated / 'src' / 'atlas',
                    ignore=shutil.ignore_patterns('__pycache__'))
    shutil.rmtree(original)
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('GIT_') and key != 'PYTHONPATH'}
    environment['PYTHONPATH'] = str(relocated / 'src')
    cold = subprocess.run(
        [sys.executable, '-m', 'atlas.tools.blueprint_fixture_probe',
         '--read-only',
         '--repo-root', str(relocated), '--store', str(relocated / 'stores/blueprint'),
         '--goal', 'alpha atomic banking', '--top-k', '2', '--beam', '1'],
        cwd=relocated, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert cold.returncode == 0, cold.stdout + cold.stderr
    observed = json.loads(cold.stdout)
    assert observed['generation_id'] == generation.generation_id
    assert observed['results'] == list(before.results)
    assert observed['dependency_frontier'] == generation.source_roots
    assert observed['source_currency']['source_roots'] == 'MOVED'
    assert all(item['actual'] is None for item in observed['source_currency']['moved'])
