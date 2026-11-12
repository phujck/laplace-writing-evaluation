"""Opt-in WO-s2-09 measurement; all writes are inside pytest's supplied tmp_path.

RUN_S2_09_QRC=1 enables the GPU-only QRC measurement. Frozen draws and v2 law
are read unchanged; the additive extension declares temporary referents and dials.
The run_bench module's runner, arm constructors, GPU gate and summary are used
in-process because its CLI binds atlas_store to the live v2 pathname.
"""
import copy
from contextlib import closing
import gc
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import threading
import time

import pytest


@pytest.mark.skipif(os.environ.get('RUN_S2_09_QRC') != '1', reason='explicit GPU QRC measurement')
def test_qrc_depth_pour_and_frozen_displaced(tmp_path):
    from atlas.blueprint import current_blueprint_generation
    from atlas.bench.draw import fingerprint
    from atlas.bench.task import BenchTaskBundle
    from atlas.bench.universe import SnapshotView, FULL_UNIVERSE
    from atlas.dataset import mint_manifest, pour_dataset, extra_authority_files
    from atlas.encoders.base import EncoderRuntimeEvidence
    from atlas.encoders.bge_onnx import BgeOnnxEncoder
    from atlas.history import ProducerRef, SeatRole, SourceRef
    from atlas.ids import hash_bytes
    from atlas.runtime import collect_runtime_receipt
    from atlas.snapshot import load_snapshot
    from atlas.spectral_pour import PourMetadata
    from atlas.store import ConceptricStore
    from atlas.tools import run_bench

    assert os.environ['LAPLACE_REQUIRE_GPU'] == '1'
    root = Path(__file__).resolve().parents[2]
    live = root / 'atlas/stores/qrc'
    before_live = fingerprint(live)
    reg = json.loads((root / 'atlas/bench/instrument/qrc-two-mode-20260914-v2.json').read_text())
    original = json.loads((root / reg['frozen_draws']['registration_path']).read_text())
    run_bench.validate_v2_law(original, reg)
    binding = reg['frozen_draws']['bundles']['DISPLACED']
    tasks_path = root / binding['path']
    assert hash_bytes(tasks_path.read_bytes()) == binding['tasks_sha256']
    assert hash_bytes((tasks_path.parent / 'freeze.json').read_bytes()) == binding['freeze_sha256']
    core = json.loads((root / 'atlas/datasets/qrc.json').read_text())['core']
    core['spectral'].update(leaf_max=10, branching=2, max_depth=12,
                           grade_contract_id='axis-contract:dataset-qrc/s2-09-depth12',
                           axis='source-detail:s2-09-depth', fibre='dataset-qrc-manuscript:s2-09-depth')
    # v2 fields survive byte-for-byte as values; added fields describe this run.
    revision = copy.deepcopy(reg)
    revision['s2_09_depth_measurement'] = dict(
        version=3, parent_registration_sha256=hash_bytes((root / 'atlas/bench/instrument/qrc-two-mode-20260914-v2.json').read_bytes()),
        atlas_store_override=str(tmp_path / 'qrc-copy'),
        spectral=core['spectral'],
        operator_difference='engine silhouette-selected normalized Laplacian; atlas declared fixed-k normalized affinity',
        scope='QRC retrieval only; planted synthetics measured separately')
    assert all(revision[key] == value for key, value in reg.items())
    (tmp_path / 'registration-v3.json').write_text(json.dumps(revision, indent=2) + '\n')
    print('REGISTRATION ' + json.dumps(dict(additive=True, beam=reg['atlas_read_protocol']['beam'],
          k=reg['retrieval_k'], tasks_sha256=binding['tasks_sha256'], dials=core['spectral'])))
    authority = extra_authority_files(root)
    source = ConceptricStore(live, read_only=True, immutable=True, extra_authority_files=authority)
    old = current_blueprint_generation(source)
    encoder = BgeOnnxEncoder(model_dir=root / core['encoder']['model_dir'], threads=2,
                             providers=('CUDAExecutionProvider',))
    session = encoder._load().model.model
    assert session.get_providers()[0] == 'CUDAExecutionProvider'
    session.disable_fallback()
    meta = PourMetadata('2026-09-14T21:03:15Z', SeatRole.EGO, SeatRole.EGO, 'WO-s2-09-depth',
        (SourceRef('WO-s2-09-depth', hash_bytes(b'WO-s2-09-depth'), None),),
        collect_runtime_receipt(root), ProducerRef('codex', 'derive', 's2-09'),
        EncoderRuntimeEvidence.from_dict(old.encoder_runtime_evidence))
    # Copy first, before any mutation; the live root only has immutable readers.
    copied = tmp_path / 'qrc-copy'
    shutil.copytree(live, copied)
    with closing(sqlite3.connect(f'file:{copied / "conceptric.sqlite3"}?mode=ro', uri=True)) as db:
        predecessor = db.execute('SELECT checkpoint_digest FROM authority_checkpoint WHERE singleton=1').fetchone()[0]
    adopted = ConceptricStore.prepare_authority_checkpoint(copied,
        expected_predecessor=predecessor,
        authority_context=ConceptricStore.authority_context_manifest(copied, extra_authority_files=authority),
        extra_authority_files=authority)
    print('TMP_COPY_CHECKPOINT ' + json.dumps(adopted))
    smi = []
    ready = threading.Event()
    def observe_gpu():
        ready.wait()
        time.sleep(.2)
        smi.append(subprocess.run(['nvidia-smi'], capture_output=True, text=True, check=True).stdout)
        print('NVIDIA_SMI_DURING_POUR\n' + smi[0])
    observer = threading.Thread(target=observe_gpu)
    observer.start()
    ready.set()
    rows = []
    for name, parent in [('fresh', 'genesis'), ('qrc-copy', old.generation_id)]:
        from atlas.blueprint import GENESIS_GENERATION
        core['store'] = name
        manifest = mint_manifest(core, root, judgement=dict(status='UNJUDGED',
            owner='WO-s2-09', dial_basis='measurement leaf_max=10 branching=2 max_depth=12; inherited chi=4 phi=.85'))
        started = time.perf_counter()
        receipt = pour_dataset(manifest, root, tmp_path, encoder, meta,
                               parent_generation=GENESIS_GENERATION if name == 'fresh' else parent)
        gc.collect()
        # Finish the isolated writer before using SQLite's immutable read protocol.
        with closing(sqlite3.connect(tmp_path / name / 'conceptric.sqlite3')) as db:
            checkpoint = db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()
            assert checkpoint[0] == 0
        measured = ConceptricStore(tmp_path / name, read_only=True, immutable=True,
                                   extra_authority_files=authority)
        generation = current_blueprint_generation(measured)
        assert generation.generation_id == receipt['generation_id']
        per_grade = []
        for depth in sorted({c['depth'] for c in generation.clusters}):
            nodes = [c for c in generation.clusters if c['depth'] == depth]
            sizes = sorted(len(c['member_logical_ids']) for c in nodes)
            per_grade.append(dict(grade=depth, coarse_nodes=len(nodes), descendant_memberships=sum(sizes),
                sorted_sizes=sizes, terminal_leaf_memberships=sum(len(c['member_logical_ids']) for c in nodes if not c['child_cluster_ids']),
                stops={reason: sum(c['stop_reason']==reason for c in nodes)
                       for reason in sorted({c['stop_reason'] for c in nodes if c['stop_reason']})}))
        row = dict(referent=name, generation_id=generation.generation_id,
                   leaves=len(generation.clauses), per_grade=per_grade,
                   wall_seconds=round(time.perf_counter()-started, 3),
                   costs=generation.receipt.costs)
        rows.append(row)
        print('CLUSTER_SIZE ' + json.dumps(row))
    observer.join()
    # Two equivalent pours must give the same cluster-size rows.
    assert rows[0]['per_grade'] == rows[1]['per_grade']
    snap_path = root / reg['snapshot_dir']
    before = dict(snapshot=fingerprint(snap_path), store=fingerprint(copied))
    snap = load_snapshot(snap_path)
    view = SnapshotView(snap, FULL_UNIVERSE)
    bundle = BenchTaskBundle.from_dict(json.loads(tasks_path.read_text()))
    arms = run_bench.build_arms(reg['arm_seed'], reg['retrieval_k'], True,
        str(root / core['encoder']['model_dir']), tmp_path / 'projections',
        atlas_store=copied, atlas_reference_queries=reg['fold_reference_queries'])
    included, _ = run_bench.applicable_arm_ids(reg, reg['corpus_kinds'])
    arms = [a for a in arms if a.protocol.full_id in included]
    gpu = run_bench.require_dense_gpu(arms)
    atlas = next(a for a in arms if a.protocol.arm_id == 'atlas')
    assert atlas.protocol.beam == reg['atlas_read_protocol']['beam']
    atlas.prepare_encoder()
    result = run_bench.run_bundle(bundle, view, arms, segmentation_id=reg['segmentation_id'],
                                 run_label='WO-s2-09-depth-DISPLACED')
    after = dict(snapshot=fingerprint(snap_path), store=fingerprint(copied))
    assert before == after
    assert fingerprint(live) == before_live
    summary = run_bench.instrument_summary(result.rows, reg, 'DISPLACED')
    for name, values in summary['bootstrap']['per_arm'].items():
        print('DISPLACED ' + json.dumps(dict(arm=name, **values)))
    print('VERDICT ' + summary['verdict'])
    atlas_rows = [r['detail'] for r in result.rows if r['arm'] == 'atlas']
    print('DESCENT ' + json.dumps(dict(queries=len(atlas_rows),
          visited_min=min(r['visited'] for r in atlas_rows), visited_max=max(r['visited'] for r in atlas_rows),
          visited_mean=sum(r['visited'] for r in atlas_rows)/len(atlas_rows),
          maximum_grade=max(max(r['grades_descended']) for r in atlas_rows))))
    print('FINGERPRINTS ' + json.dumps(dict(before=before, after=after, live_before=before_live,
          live_after=fingerprint(live), match=True)))
    run_bench.write_run(result, tmp_path / 'displaced')
    (tmp_path / 'summary.json').write_text(json.dumps(summary, indent=2))
