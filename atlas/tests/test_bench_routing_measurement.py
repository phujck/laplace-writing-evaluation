"""Opt-in frozen routing grid. Reuses s2-09 unchanged; no live store writes.

Run this file with --unit or --measure. CUDA libraries are resolved from the
installed NVIDIA wheels in the child process, without changing LAPLACE settings.
"""
from collections import Counter
import contextlib
import gc
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'atlas/bench/runs/2026-09-14-qrc-routing'
SCRATCH = ROOT / 'atlas/tests/.scratch-routing'


def diagnose(arm, bundle, rows):
    """Read only: anchored target path versus recorded scored/pruned nodes.

    The supplied s2-09 test exposes no diagnosis function. This explicit trace
    consumer implements the same routing-versus-terminal-rank partition.
    """
    tasks = {t.task_id: t for t in bundle.tasks}
    by_span = {s.span_id: key for key, s in arm.spans.items()}
    misses = []
    for row in rows:
        if row['correct']:
            continue
        task = tasks[row['task']]
        assert len(task.anchors) == 1
        target = by_span[task.anchors[0].span_id]
        path = sorted((c for c in arm.clusters if target in c['member_logical_ids']),
                      key=lambda c: c.get('depth', 1))
        trace = {r['node_handle']: r for step in row['detail']['routing_trace'] for r in step}
        pruned = next((c for c in path if c['node_handle'] in trace and not trace[c['node_handle']]['kept']), None)
        item = dict(task=row['task'], target=target, target_path=[c['node_handle'] for c in path])
        if pruned:
            r = trace[pruned['node_handle']]
            step = next(step for step in row['detail']['routing_trace'] if r in step)
            parent = next((p for p in path if pruned['cluster_id'] in p.get('child_cluster_ids', [])), None)
            siblings = set(parent['child_cluster_ids']) if parent else {c['cluster_id'] for c in arm.roots}
            selected_siblings = [c['node_handle'] for c in arm.clusters
                                 if c['cluster_id'] in siblings and c['node_handle'] in trace
                                 and trace[c['node_handle']]['kept']]
            item.update(kind='ROUTING_OMISSION', grade=r['grade'], target_face_rank=r['rank'],
                        target_face_score=r['score'], cutoff_score=min(s['score'] for s in step if s['kept']),
                        selected_siblings=selected_siblings, selected_same_grade=[s['node_handle'] for s in step if s['kept']])
        else:
            assert all(c['node_handle'] in trace and trace[c['node_handle']]['kept'] for c in path)
            item.update(kind='TERMINAL_TOP_K', grade=path[-1].get('depth', 1))
        misses.append(item)
    return dict(misses=len(misses), counts=dict(Counter(m['kind'] for m in misses)),
                routing_by_grade=dict(Counter(str(m['grade']) for m in misses if m['kind']=='ROUTING_OMISSION')),
                selected_sibling_misses=sum(bool(m.get('selected_siblings')) for m in misses), per_query=misses)


def measure():
    from atlas.bench.draw import fingerprint
    from atlas.bench.task import BenchTaskBundle
    from atlas.bench.universe import SnapshotView, FULL_UNIVERSE
    from atlas.ids import hash_bytes
    from atlas.snapshot import load_snapshot
    from atlas.tools import run_bench
    from test_spectral_pour_qrc_measurement import test_qrc_depth_pour_and_frozen_displaced

    assert os.environ['LAPLACE_REQUIRE_GPU'] == '1'
    reg_path = ROOT / 'atlas/bench/instrument/qrc-two-mode-20260914-v3.json'
    reg = json.loads(reg_path.read_text())
    parent_path = ROOT / reg['routing_v3']['parent_path']
    assert hash_bytes(parent_path.read_bytes()) == reg['routing_v3']['parent_sha256']
    run_bench.validate_v3_law(json.loads(parent_path.read_text()), reg)
    run_bench.validate_v2_law(json.loads((ROOT / reg['frozen_draws']['registration_path']).read_text()), reg)
    binding = reg['frozen_draws']['bundles']['DISPLACED']
    task_path = ROOT / binding['path']
    assert hash_bytes(task_path.read_bytes()) == binding['tasks_sha256']
    assert hash_bytes((task_path.parent/'freeze.json').read_bytes()) == binding['freeze_sha256']
    bundle = BenchTaskBundle.from_dict(json.loads(task_path.read_text()))
    snap_path = ROOT / reg['snapshot_dir']
    live = ROOT / reg['atlas_store']
    initial = dict(live=fingerprint(live), snapshot=fingerprint(snap_path))
    print('REGISTRATION', hash_bytes(reg_path.read_bytes()), 'tasks', binding['tasks_sha256'], flush=True)
    copied_parent = SCRATCH / 'pytest-s2-09'
    if copied_parent.exists():
        # Resume only an exact, completed s2-09 copy; never silently reuse partial state.
        lines=(OUT/'s2-09-reused.txt').read_text().splitlines()
        stamps=json.loads(next(line.removeprefix('FINGERPRINTS ') for line in lines if line.startswith('FINGERPRINTS ')))
        assert stamps['match'] and stamps['before']==stamps['after']
        assert fingerprint(copied_parent/'qrc-copy')==stamps['after']['store']
        assert initial['live']==stamps['live_after']
        assert initial['snapshot']==stamps['after']['snapshot']
        print('S2_09_RESUME_EXACT_COPY true',flush=True)
    else:
        copied_parent.mkdir()
        start = time.perf_counter()
        with (OUT/'s2-09-reused.txt').open('w') as stream, contextlib.redirect_stdout(stream):
            test_qrc_depth_pour_and_frozen_displaced(copied_parent)
        print('S2_09_REUSED_SECONDS', round(time.perf_counter()-start, 3), flush=True)
    gc.collect()
    copied = copied_parent/'qrc-copy'
    # s2-09 already ran identical baselines through the public runner and GPU gate.
    base_rows = [json.loads(line) for line in (copied_parent/'displaced/rows.jsonl').read_text().splitlines()]
    baselines = [r for r in base_rows if r['arm'] != 'atlas']
    assert sum(r['correct'] for r in baselines if r['arm']=='dense_flat') == 14
    assert sum(r['correct'] for r in baselines if r['arm']=='bm25') == 12
    (OUT/'baseline-rows.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in baselines))
    for name in ['summary.json', 'registration-v3.json']:
        shutil.copyfile(copied_parent/name, OUT/('s2-09-'+name))
    view = SnapshotView(load_snapshot(snap_path), FULL_UNIVERSE)
    cells=[]
    encoder=None
    print('depth beam face fraction paired_delta_CI mean_visited/196 seconds', flush=True)
    for depth, store in [(1, live), (3, copied)]:
        for beam in reg['routing_v3']['beam']:
            for law in reg['routing_v3']['face_score']:
                dials=run_bench.routing_dials(reg, beam, law, 10)
                arms=run_bench.build_arms(reg['arm_seed'], reg['retrieval_k'], False,
                    str(ROOT/reg['atlas_encoder']['model_dir']), SCRATCH/'unused-projections',
                    atlas_store=store, atlas_reference_queries=reg['fold_reference_queries'], **dials)
                arm=next(a for a in arms if a.protocol.arm_id=='atlas')
                if encoder is not None:
                    arm.encoder=encoder
                arm.prepare_encoder()
                encoder=arm.encoder
                before=dict(store=fingerprint(store), snapshot=fingerprint(snap_path), live=fingerprint(live))
                started=time.perf_counter()
                result=run_bench.run_bundle(bundle, view, [arm], segmentation_id=reg['segmentation_id'],
                                           run_label=f'routing-d{depth}-b{beam}-{law}')
                seconds=time.perf_counter()-started
                after=dict(store=fingerprint(store), snapshot=fingerprint(snap_path), live=fingerprint(live))
                assert before==after
                assert max(c.get('depth',1) for c in arm.clusters)==depth
                assert len(arm.clauses)==196
                summary=run_bench.instrument_summary(baselines+result.rows, reg, 'DISPLACED')
                pair=next(p for p in summary['bootstrap']['pairwise'] if {p['arm_a'],p['arm_b']}=={'atlas','dense_flat'})
                lo,hi=pair['ci_low'],pair['ci_high']
                if pair['arm_a']!='atlas': lo,hi=-hi,-lo
                diagnosis=diagnose(arm,bundle,result.rows)
                cell=dict(depth=depth,beam=beam,face_score=law,k=10,correct=sum(r['correct'] for r in result.rows),
                    queries=40, paired_dense_interval=[lo/40,hi/40],mean_visited=sum(r['detail']['visited'] for r in result.rows)/40,
                    total=196,seconds=round(seconds,3),diagnosis=diagnosis,
                    registration_sha256=hash_bytes(reg_path.read_bytes()),frozen_draws=binding,
                    fingerprints=dict(before=before,after=after,match=True),
                    generation_id=arm.generation.generation_id,encoder_providers=encoder._load().model.model.get_providers(),
                    summary=summary,manifest=result.manifest,rows=result.rows,
                    timing_scope='atlas fold + 40 queries including embedding, routing, stored leaf ranking, counted reads and scoring; excludes bootstrap/diagnosis/fingerprints; encoder session shared')
                cell['fraction']=cell['correct']/40
                filename=f'd{depth}-b{beam}-{law}.json'
                (OUT/filename).write_text(json.dumps(cell,indent=2)+'\n')
                cells.append({key:cell[key] for key in ['depth','beam','face_score','correct','fraction','paired_dense_interval','mean_visited','total','seconds']})
                print(f"{depth} {beam} {law} {cell['correct']}/40 [{lo/40:+.3f},{hi/40:+.3f}] {cell['mean_visited']:.3f}/196 {seconds:.3f}",flush=True)
                if beam==1 and law=='equal-mean':
                    assert cell['correct']==(11 if depth==1 else 5)
                if beam in (1,8) and law=='equal-mean':
                    smi=subprocess.run(['nvidia-smi'],capture_output=True,text=True,check=True).stdout
                    (OUT/f'nvidia-d{depth}-b{beam}.txt').write_text(smi)
                del arm,result,arms
                gc.collect()
    frontier=[]
    for depth in (1,3):
        for beam in (1,2,4,8):
            eligible=[c for c in cells if c['depth']==depth and c['beam']==beam]
            frontier.append(sorted(eligible,key=lambda c:(-c['correct'],c['mean_visited'],c['face_score']))[0])
    positive=[c for c in cells if c['correct']>=14 and c['paired_dense_interval'][0]>0]
    final=dict(initial=initial, final=dict(live=fingerprint(live),snapshot=fingerprint(snap_path)))
    assert final['initial']==final['final']
    (OUT/'table.json').write_text(json.dumps(dict(cells=cells,frontier=frontier,positive=positive,final=final),indent=2)+'\n')
    print('FRONTIER '+json.dumps(frontier),flush=True)
    print('POSITIVE_LOWER_BOUND_CELLS '+json.dumps(positive),flush=True)
    print('LIVE_AND_SNAPSHOT_UNCHANGED true; CELLS 40',flush=True)


def verify_receipts():
    from atlas.bench.draw import fingerprint
    from atlas.blueprint import current_blueprint_generation
    from atlas.dataset import extra_authority_files
    from atlas.ids import hash_bytes
    from atlas.snapshot import load_snapshot
    from atlas.store import ConceptricStore
    table=json.loads((OUT/'table.json').read_text())
    reg_path=ROOT/'atlas/bench/instrument/qrc-two-mode-20260914-v3.json'
    reg=json.loads(reg_path.read_text())
    expected={(d,b,f) for d in (1,3) for b in (1,2,4,8) for f in reg['routing_v3']['face_score']}
    assert {(c['depth'],c['beam'],c['face_score']) for c in table['cells']}==expected
    sources=json.loads((OUT/'source-observed-during-run.json').read_text())
    assert all(hash_bytes((ROOT/k).read_bytes())==v for k,v in sources.items())
    rows_checked=0
    for depth,store_path in [(1,ROOT/reg['atlas_store']),(3,SCRATCH/'pytest-s2-09/qrc-copy')]:
        store=ConceptricStore(store_path,read_only=True,immutable=True,extra_authority_files=extra_authority_files(ROOT))
        generation=current_blueprint_generation(store)
        handles={c['logical_id']:c['content_handle'] for c in generation.clauses}
        for beam in (1,2,4,8):
            for law in reg['routing_v3']['face_score']:
                cell=json.loads((OUT/f'd{depth}-b{beam}-{law}.json').read_text())
                assert cell['registration_sha256']==hash_bytes(reg_path.read_bytes())
                assert cell['fingerprints']['before']==cell['fingerprints']['after']
                assert cell['fingerprints']['after']['store']==fingerprint(store_path)
                rows=cell['rows']
                assert len(rows)==len({r['task'] for r in rows})==40
                assert sum(r['correct'] for r in rows)==cell['correct']
                assert sum(r['detail']['visited'] for r in rows)/40==cell['mean_visited']
                misses={r['task']:r for r in rows if not r['correct']}
                diagnosis=cell['diagnosis']
                assert len(misses)==diagnosis['misses']==sum(diagnosis['counts'].values())
                for item in diagnosis['per_query']:
                    row=misses[item['task']]
                    assert handles[item['target']] not in row['retrieved']
                    trace={r['node_handle']:r for step in row['detail']['routing_trace'] for r in step}
                    pruned=[trace[h] for h in item['target_path'] if h in trace and not trace[h]['kept']]
                    if item['kind']=='ROUTING_OMISSION':
                        assert len(pruned)==1 and pruned[0]['grade']==item['grade']
                        assert pruned[0]['rank']>beam
                    else:
                        assert all(h in trace and trace[h]['kept'] for h in item['target_path'])
                rows_checked+=len(rows)
    assert fingerprint(ROOT/reg['atlas_store'])==table['initial']['live'] if 'initial' in table else fingerprint(ROOT/reg['atlas_store'])==table['final']['initial']['live']
    assert table['final']['initial']==table['final']['final']
    assert not table['positive']
    print(f'RECEIPTS_VERIFIED cells=40 rows={rows_checked} fingerprints=unchanged routing_and_top_k=consistent sources=unchanged')


def launch(mode):
    OUT.mkdir(parents=True,exist_ok=True)
    SCRATCH.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    cuda=Path.home()/'.local/lib/python3.12/site-packages/nvidia'
    env['LD_LIBRARY_PATH']=':'.join(str(p) for p in sorted(cuda.glob('*/lib')) if p.parent.name!='cu13')+(':'+env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    env['TMPDIR']=str(SCRATCH)
    env['CUPY_CACHE_DIR']=str(SCRATCH/'cupy-cache')
    print('CUDA_LIBRARY_PATH '+env['LD_LIBRARY_PATH'],flush=True)
    if mode=='--unit':
        args=[sys.executable,'-m','pytest','-q','-p','no:cacheprovider','-p','no:randomly',
              *['atlas/tests/'+n for n in ['test_bench_atlas_arm.py','test_bench_draw.py','test_bench_freeze.py','test_bench_leakage.py','test_bench_routing.py']],
              '--basetemp=atlas/tests/.scratch-routing/pytest-unit']
    else:
        if not (SCRATCH/'pytest-s2-09').exists():
            prep=[sys.executable,str(Path(__file__).resolve()),'--child-prepare']
            print('COMMAND '+' '.join(prep),flush=True)
            status=subprocess.run(prep,env=env,cwd=ROOT).returncode
            if status:
                return status
        args=[sys.executable,str(Path(__file__).resolve()),'--child-measure']
    print('COMMAND '+' '.join(args),flush=True)
    return subprocess.run(args,env=env,cwd=ROOT).returncode


if __name__=='__main__':
    if sys.argv[1]=='--verify':
        verify_receipts()
    elif sys.argv[1]=='--child-prepare':
        from test_spectral_pour_qrc_measurement import test_qrc_depth_pour_and_frozen_displaced
        copied_parent=SCRATCH/'pytest-s2-09'
        copied_parent.mkdir()
        started=time.perf_counter()
        with (OUT/'s2-09-reused.txt').open('w') as stream, contextlib.redirect_stdout(stream):
            test_qrc_depth_pour_and_frozen_displaced(copied_parent)
        print('S2_09_REUSED_SECONDS',round(time.perf_counter()-started,3),flush=True)
    elif sys.argv[1]=='--child-measure':
        measure()
    else:
        raise SystemExit(launch(sys.argv[1]))
