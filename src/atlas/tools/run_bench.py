"""run_bench - run the Tier-1 arms over one frozen bundle and bank the result.

    python -m atlas.tools.run_bench <snapshot_dir> --bundle atlas/bench/tasks/<hex>/tasks.json \\
        --out atlas/bench/runs/<date>/<label> [--universe bench-filtered|full] [--no-planted]

One run is one bundle, one universe and the four Tier-1 arms (five, counting the flat read's two
variants). Correctness is scored before any cost aggregate exists; the summary that follows
recomputes every number from the rows and refuses on disagreement.

The full-universe control is the SAME command with ``--universe full``. It is a control and not a
second experiment: same bundle, same arms, same seeds, and the only difference is the declared
exclusion list, which is exactly what the author's ruling asked to be measured rather than
assumed.

``--no-planted`` skips the planted-bad control, which costs one extra fold per arm. The scored
run banks with it; the determinism gate runs without it, because re-running the control twice
proves nothing the main rows do not already prove.

THE PREDICTION TABLE IS BOUND, NOT MERELY PRESENT. ``freeze.json`` records the sha256 of the
``predictions.json`` that existed at freeze time; this runner recomputes that hash and REFUSES if
it disagrees. A prediction table edited between the freeze and the run is not a pre-registration,
and "the file was sitting next to the bundle" is not a check.

The hash is deliberately NOT folded into ``bundle_id``. The bundle's identity covers the corpus
and the ground truth (design §5); folding a prediction table into it would retroactively
invalidate every id already banked, and it would make an ordering claim into a content claim.
The binding belongs where the ordering claim already lives - beside the freeze, checked at the
run - so ``freeze.json`` carries it and the runner enforces it.
"""

from __future__ import annotations

import argparse
import json
import sys
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ..bench.arms import (
    AtlasArm,
    APPLICABLE_KINDS,
    Bm25Arm,
    DenseFlatArm,
    FlatReadArm,
    GrepSkilledArm,
    IncumbentArchArm,
    RaptorArm,
)
from ..bench.contamination import report as contamination_report
from ..bench.runner import run_bundle, write_run
from ..bench.task import BenchTaskBundle
from ..bench.universe import (
    BENCH_FILTERED,
    FULL_UNIVERSE,
    RULED_ONLY,
    PlantedSpan,
    SnapshotView,
)
from ..errors import AtlasError, ProtocolViolation
from ..ids import hash_bytes
from ..snapshot import load_snapshot

UNIVERSES = {"bench-filtered": BENCH_FILTERED, "ruled-only": RULED_ONLY,
             "full": FULL_UNIVERSE}
DEFAULT_SEED = 20260801
V2_AMENDED_FIELDS = frozenset(('schema', 'work_order', 'registered_ts', 'arms', 'arm_selection',
                               'verbatim_rule', 'displaced_focal_arm', 'displaced_rule'))


def validate_v2_law(original, revision):
    if set(revision['amended_fields']) != V2_AMENDED_FIELDS:
        raise ProtocolViolation('V1_LAW_AMENDMENT_SCOPE')
    if any(revision.get(k) != original[k] for k in set(original) - V2_AMENDED_FIELDS):
        raise ProtocolViolation('V1_LAW_DRIFT')



def validate_v3_law(parent, revision):
    if any(revision.get(k) != v for k, v in parent.items()):
        raise ProtocolViolation('V2_LAW_DRIFT')
    if revision.get('routing_v3', {}).get('version') != 3:
        raise ProtocolViolation('MISSING_ROUTING_V3')


def routing_dials(registration, beam=None, face_score=None, k=None):
    """Resolve additive routing registration; older registrations keep their law."""
    from ..bench.arms.atlas_arm import FACE_SCORE_LAWS
    extension = registration.get('routing_v3')
    if extension is None:
        if beam not in (None, 1) or face_score not in (None, 'equal-mean') or k not in (None, registration['retrieval_k']):
            raise ProtocolViolation('UNREGISTERED_ROUTING_DIAL')
        return dict(atlas_beam=1, atlas_face_score='equal-mean', atlas_k=registration['retrieval_k'])
    beam = extension['default']['beam'] if beam is None else beam
    face_score = extension['default']['face_score'] if face_score is None else face_score
    k = extension['default']['k'] if k is None else k
    if (type(beam) is not int or beam not in extension['beam'] or
            face_score not in extension['face_score'] or face_score not in FACE_SCORE_LAWS or
            type(k) is not int or k not in extension['k']):
        raise ProtocolViolation('UNREGISTERED_ROUTING_DIAL')
    return dict(atlas_beam=beam, atlas_face_score=face_score, atlas_k=k)


def applicable_arm_ids(registration, corpus_kinds):
    declared = registration.get('applicable_kinds')
    if declared is None:
        return list(registration['arms']), []
    if not corpus_kinds or set(registration['arms']) - set(declared):
        raise ProtocolViolation('MISSING_ARM_APPLICABILITY')
    included = [a for a in registration['arms'] if set(corpus_kinds) <= set(declared[a])]
    excluded = [dict(arm=a, reason='unsupported corpus kinds',
                     unsupported_kinds=sorted(set(corpus_kinds) - set(declared[a])))
                for a in registration['arms'] if a not in included]
    if len(included) < 2 or registration['displaced_focal_arm'] not in included:
        raise ProtocolViolation('INSUFFICIENT_APPLICABLE_ARMS')
    return included, excluded


def instrument_summary(rows, registration, mode, corpus_kinds=None):
    from ..bench.stats import bootstrap_totals
    included, excluded = applicable_arm_ids(registration, corpus_kinds or registration.get('corpus_kinds'))
    expected = set(included)
    tasks = {r['task'] for r in rows}
    cells = {(r['arm'], r['task']) for r in rows}
    if (len(tasks) != registration['draws_per_mode'] or len(rows) != len(cells)
            or cells != {(a, t) for a in expected for t in tasks}):
        raise ProtocolViolation('INCOMPLETE_INSTRUMENT_ROWS')
    b = registration['bootstrap']
    stats = bootstrap_totals(rows, resamples=b['resamples'], seed=b['seed'], alpha=b['alpha'])
    stats.pop('per_class_note', None)  # The inherited n=3 annotation does not apply here.
    n = stats['task_count']
    per_arm = stats['per_arm']
    for arm, values in per_arm.items():
        baseline = sorted((a for a in expected if a != arm),
                          key=lambda a: (-per_arm[a]['observed_correct'], a))[0]
        pair = next(p for p in stats['pairwise'] if {p['arm_a'], p['arm_b']} == {arm, baseline})
        lo, hi = pair['ci_low'], pair['ci_high']
        delta = pair['observed_difference']
        if pair['arm_a'] != arm:
            lo, hi, delta = -hi, -lo, -delta
        values.update(strongest_baseline=baseline, difference=delta / n,
                      difference_ci=[lo / n, hi / n])
    floor = all(v['observed_correct'] / n >= registration['verbatim_floor'] for v in per_arm.values())
    focal = per_arm[registration['displaced_focal_arm']]
    verdict = ('REFUSED_LEXICAL_TAUTOLOGY' if floor else 'FLOOR_NOT_TRIGGERED') if mode == 'VERBATIM' else (
        'SUCCESS' if focal['observed_correct'] / n >= registration['displaced_success_threshold']
        and focal['difference_ci'][0] > 0 else 'THRESHOLD_NOT_MET')
    accounting = {}
    for arm in included:
        selected = [r for r in rows if r['arm'] == arm]
        accounting[arm] = dict(mean_reads_per_query=sum(
            r.get('cost', {}).get('spans_read', 0) + r.get('cost', {}).get('whole_file_reads', 0)
            for r in selected) / n)
        if arm == 'atlas':
            accounting[arm]['per_query'] = [dict(task=r['task'], **r.get('detail', {})) for r in selected]
    return dict(mode=mode, verdict=verdict, applicable_arms=included, excluded_arms=excluded,
        accounting=accounting, floor_verdict=(
        'REFUSED_LEXICAL_TAUTOLOGY' if floor else 'FLOOR_NOT_TRIGGERED') if mode == 'VERBATIM' else 'NOT_APPLICABLE',
        bootstrap=stats)


def require_dense_gpu(arms):
    """Explicit CUDA session and live-process evidence; never accept a CPU default."""
    from ..encoders.bge_onnx import BgeOnnxEncoder
    import onnxruntime as ort
    if 'CUDAExecutionProvider' not in ort.get_available_providers():
        raise ProtocolViolation('GPU_REQUIRED', providers=ort.get_available_providers())
    dense = next((a for a in arms if a.protocol.arm_id == 'dense_flat'), None)
    if dense is None:
        raise ProtocolViolation('GPU_REQUIRED: dense arm missing')
    dense.encoder = BgeOnnxEncoder(model_dir=dense.model_dir, threads=2,
                                  providers=('CUDAExecutionProvider',))
    model = dense.encoder._load()
    session = model.model.model
    providers = session.get_providers()
    if not providers or providers[0] != 'CUDAExecutionProvider':
        raise ProtocolViolation('GPU_REQUIRED: encoder fell back', providers=providers)
    session.disable_fallback()
    # Exercise the same encoder object used by the arm while nvidia-smi observes this PID.
    dense.encoder.query('qrc GPU instrument probe')
    smi = subprocess.run(['nvidia-smi'], capture_output=True, text=True, check=True).stdout
    print(smi, end='')
    return dict(pid=os.getpid(), providers=providers, encoder=dense.encoder.encoder_id,
                nvidia_smi=smi)


def check_predictions_binding(bundle_path: Path) -> tuple[str | None, str | None]:
    """Recompute the prediction table's hash and refuse if it is not the registered one.

    Returns ``(frozen_sha, actual_sha)``; either is None when the corresponding file is absent,
    which is not an error - a bundle may legitimately carry no prediction table. What IS an error
    is a table that exists and disagrees with the hash ``freeze.json`` recorded, because that is a
    prediction edited after the freeze, which is not a prediction.
    """
    pred_path = bundle_path.parent / "predictions.json"
    freeze_path = bundle_path.parent / "freeze.json"
    if not pred_path.is_file():
        return None, None
    actual = hash_bytes(pred_path.read_bytes())
    if not freeze_path.is_file():
        return None, actual
    declared = json.loads(freeze_path.read_text(encoding="utf-8")).get("predictions_sha256")
    if declared and declared != actual:
        raise ProtocolViolation(
            "the prediction table is not the one registered at freeze time - a prediction "
            "edited after the freeze is not a pre-registration",
            declared=declared, actual=actual, path=str(pred_path),
        )
    return declared, actual


def build_arms(seed: int, k: int, with_dense: bool, model_dir: str | None,
               store_root: Path | None, raptor_fold: Path | None = None,
               with_incumbent: bool = False, atlas_store: Path | None = None,
               atlas_reference_queries: int = 80, atlas_beam: int = 1,
               atlas_face_score: str = 'equal-mean', atlas_k: int | None = None) -> list:
    """The arm list, in report order. The Tier-2 arms appear ONLY when explicitly asked for.

    ``raptor`` needs a banked fold (a model bill somebody already paid) and ``incumbent_arch``
    needs an encoder; neither is defaulted on, so the Tier-1 command keeps working unchanged and
    the Phase 3 command says out loud what it is adding.
    """
    from ..bench.arms.dense_flat import DEFAULT_STORE as PROJECTION_STORE

    arms: list = [FlatReadArm("B", seed=seed), FlatReadArm("B+", seed=seed),
                  GrepSkilledArm(seed=seed), Bm25Arm(k=k, seed=seed)]
    if with_dense:
        arms.append(DenseFlatArm(k=k, seed=seed, model_dir=model_dir, store_root=store_root))
    if raptor_fold is not None:
        arms.append(RaptorArm(fold_dir=raptor_fold,
                              projection_store=store_root or PROJECTION_STORE,
                              k=k, seed=seed, model_dir=model_dir))
    if with_incumbent:
        arms.append(IncumbentArchArm(k=k, seed=seed, model_dir=model_dir,
                                     store_root=store_root))
    if atlas_store is not None:
        arms.append(AtlasArm(store_root=atlas_store, k=k if atlas_k is None else atlas_k, seed=seed, model_dir=model_dir,
                             reference_queries=atlas_reference_queries, beam=atlas_beam,
                             face_score_law=atlas_face_score))
    for arm in arms:
        arm.applicable_kinds = APPLICABLE_KINDS[arm.protocol.full_id]
        arm.query_encoder_calls = int(hasattr(arm, "encoder"))
    return arms


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="run the Tier-1 bench arms over a frozen bundle")
    ap.add_argument("snapshot_dir", type=Path)
    ap.add_argument("--bundle", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--universe", default="bench-filtered", choices=sorted(UNIVERSES))
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--label", default="")
    ap.add_argument("--no-dense", action="store_true", help="skip the dense arm (no encoder)")
    ap.add_argument("--no-planted", action="store_true")
    ap.add_argument("--model-dir", default=None)
    ap.add_argument("--projection-store", type=Path, default=None)
    ap.add_argument("--raptor-fold", type=Path, default=None,
                    help="banked RAPTOR fold directory; adds the raptor arm (Phase 3)")
    ap.add_argument("--incumbent", action="store_true",
                    help="add the incumbent_arch arm (Phase 3)")
    ap.add_argument('--atlas-beam', type=int, default=None)
    ap.add_argument('--atlas-face-score', default=None)
    ap.add_argument('--atlas-k', type=int, default=None)
    ap.add_argument('--atlas-store', type=Path, default=None)
    ap.add_argument('--atlas-reference-queries', type=int, default=80)
    ap.add_argument("--stop-condition", type=Path, default=None,
                    help="JSON file of the PRE-REGISTERED stop, recorded in the manifest before "
                         "any row is scored")
    args = ap.parse_args(argv)

    try:
        # The binding check runs BEFORE the bundle is even loaded: a run against an edited
        # prediction table should cost nothing and produce nothing.
        frozen_pred, actual_pred = check_predictions_binding(args.bundle)
        bundle = BenchTaskBundle.from_dict(
            json.loads(args.bundle.read_text(encoding="utf-8")))
        snap = load_snapshot(args.snapshot_dir)
        segmentation = snap.segmentation() or {}
        view = SnapshotView(snap, UNIVERSES[args.universe])

        # THE PRE-REGISTERED STOP IS WRITTEN TO DISK BEFORE ANY ARM FOLDS. Pre-registration is an
        # ordering claim, so it is made the same way the freeze's is: the file lands first,
        # carrying its own timestamp, and the manifest records both its hash and the fact that it
        # preceded the run. A stop condition written after the numbers is a rationalisation.
        stop_record = None
        instrument = False
        sampling = None
        gpu = None
        before = None
        if args.stop_condition is not None:
            stop_bytes = args.stop_condition.read_bytes()
            stop_record = json.loads(stop_bytes)
            instrument = stop_record.get('schema') in ('qrc-two-mode/1', 'qrc-two-mode/2')
            if instrument:
                from ..bench.draw import assert_registered_before
                assert_registered_before(stop_record['registered_ts'], datetime.now(timezone.utc).isoformat())
                freeze = json.loads((args.bundle.parent / 'freeze.json').read_text())
                sampling = freeze.get('sampling', {})
                draw_registration_hash = hash_bytes(stop_bytes)
                draw_registered_ts = stop_record['registered_ts']
                if stop_record['schema'] == 'qrc-two-mode/2':
                    reuse = stop_record['frozen_draws']
                    original_bytes = Path(reuse['registration_path']).read_bytes()
                    original = json.loads(original_bytes)
                    if hash_bytes(original_bytes) != reuse['registration_sha256']:
                        raise ProtocolViolation('ORIGINAL_REGISTRATION_DRIFT')
                    validate_v2_law(original, stop_record)
                    if 'routing_v3' in stop_record:
                        extension = stop_record['routing_v3']
                        parent_bytes = Path(extension['parent_path']).read_bytes()
                        if hash_bytes(parent_bytes) != extension['parent_sha256']:
                            raise ProtocolViolation('PARENT_REGISTRATION_DRIFT')
                        validate_v3_law(json.loads(parent_bytes), stop_record)
                    binding = reuse['bundles'].get(sampling.get('mode'), {})
                    if (hash_bytes(args.bundle.read_bytes()) != binding.get('tasks_sha256')
                            or hash_bytes((args.bundle.parent / 'freeze.json').read_bytes()) != binding.get('freeze_sha256')):
                        raise ProtocolViolation('FROZEN_DRAW_DRIFT')
                    draw_registration_hash = reuse['registration_sha256']
                    draw_registered_ts = original['registered_ts']
                    if (args.atlas_store is None or str(args.atlas_store) != stop_record['atlas_store']
                            or args.atlas_reference_queries != stop_record['fold_reference_queries']):
                        raise ProtocolViolation('ATLAS_REGISTRATION_MISMATCH')
                if (sampling.get('kind') != 'random-query' or sampling.get('random_query_instrument') is not True
                        or sampling.get('registration_sha256') != draw_registration_hash
                        or sampling.get('mode') not in ('VERBATIM', 'DISPLACED')
                        or args.universe != stop_record['universe'] or args.seed != stop_record['arm_seed']
                        or args.k != stop_record['retrieval_k'] or args.projection_store is None):
                    raise ProtocolViolation('instrument registration/bundle/run mismatch')
                assert_registered_before(draw_registered_ts, sampling['draw_started_ts'])
                if (snap.manifest.snapshot_id != stop_record['snapshot_id']
                        or segmentation['generation_id'] != stop_record['segmentation_id']):
                    raise ProtocolViolation('instrument snapshot/segmentation mismatch')
            else:
                stop_record.setdefault("registered_ts", datetime.now(timezone.utc).isoformat())
                stop_bytes = (json.dumps(stop_record, sort_keys=True, indent=2) + "\n").encode("utf-8")
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / "stop_condition.json").write_bytes(stop_bytes)
            stop_record["sha256"] = hash_bytes(stop_bytes)
            print(f"pre-registered stop condition banked at {args.out / 'stop_condition.json'} "
                  f"({stop_record['sha256'][:23]}...) BEFORE any arm folded")

        dials = routing_dials(stop_record, args.atlas_beam, args.atlas_face_score, args.atlas_k) if instrument else dict(
            atlas_beam=args.atlas_beam or 1, atlas_face_score=args.atlas_face_score or 'equal-mean', atlas_k=args.atlas_k)
        arms = build_arms(args.seed, args.k, not args.no_dense, args.model_dir,
                          args.projection_store, raptor_fold=args.raptor_fold,
                          with_incumbent=args.incumbent, atlas_store=args.atlas_store,
                          atlas_reference_queries=args.atlas_reference_queries, **dials)
        if instrument:
            from ..bench.draw import fingerprint
            measured_store = args.atlas_store or Path('atlas/stores/qrc')
            before = {'snapshot': fingerprint(args.snapshot_dir),
                      'qrc_store': fingerprint(measured_store)}
            if [a.protocol.full_id for a in arms] != stop_record['arms']:
                raise ProtocolViolation('registered arm list mismatch')
            kinds = sorted({snap.nodes[n].kind for n in view.node_ids})
            if stop_record.get('applicable_kinds') is not None:
                if kinds != stop_record['corpus_kinds'] or any(
                        list(a.applicable_kinds) != stop_record['applicable_kinds'][a.protocol.full_id] for a in arms):
                    raise ProtocolViolation('ARM_APPLICABILITY_DRIFT')
                included, excluded = applicable_arm_ids(stop_record, kinds)
                arms = [a for a in arms if a.protocol.full_id in included]
                for arm in arms:
                    arm.reference_queries = stop_record['fold_reference_queries']
            gpu = require_dense_gpu(arms)
            atlas = next((a for a in arms if a.protocol.arm_id == 'atlas'), None)
            if atlas is not None:
                atlas.prepare_encoder()
                declared_encoder = stop_record['atlas_encoder']
                if atlas.encoder.spec.spec_id != declared_encoder['generation'] or atlas.encoder.spec.to_dict() != declared_encoder['spec']:
                    raise ProtocolViolation('ATLAS_MANIFEST_ENCODER_MISMATCH')
                gpu['atlas'] = dict(providers=atlas.encoder._load().model.model.get_providers(),
                                    encoder_spec=atlas.encoder.spec.to_dict())
        planted = None
        if not args.no_planted and bundle.planted:
            planted = [PlantedSpan(planted_id=p["planted_id"], node_id=p["node_id"],
                                   text=p["text"], targets_task=p["targets_task"],
                                   wrong_atoms=p.get("wrong_atoms", []))
                       for p in bundle.planted]
        result = run_bundle(bundle, view, arms,
                            segmentation_id=segmentation.get("generation_id", ""),
                            planted=planted,
                            run_label=args.label or f"{args.universe}/{args.out.name}")
        result.manifest['applicable_kinds'] = {a.protocol.full_id: list(a.applicable_kinds) for a in arms}
        result.manifest['declared_query_encoder_calls'] = {a.protocol.full_id: a.query_encoder_calls for a in arms}
        if actual_pred is not None:
            result.manifest["predictions_frozen_sha256"] = frozen_pred
            result.manifest["predictions_sha256"] = actual_pred
            result.manifest["predictions_path"] = str(args.bundle.parent / "predictions.json")
        if stop_record is not None:
            from ..bench.draw import assert_registered_before
            assert_registered_before(stop_record['registered_ts'], result.manifest['started_ts'])
            result.manifest["stop_condition"] = stop_record
            result.manifest["stop_condition_before_run"] = True
        # The contamination scan over the view this run actually served. Seconds, and it makes
        # "the headline view carried no answer key" a number in the run rather than a memory of
        # what the freeze said.
        result.manifest["contamination_scan"] = contamination_report(view, bundle.tasks)
        if instrument:
            after = {'snapshot': fingerprint(args.snapshot_dir),
                     'qrc_store': fingerprint(measured_store)}
            if before != after:
                raise ProtocolViolation('INSTRUMENT_STORE_DRIFT', before=before, after=after)
            summary = instrument_summary(result.rows, stop_record, sampling['mode'])
            summary['encoder_bill'] = result.manifest['encoder_bill']
            summary['cost_status'] = {a: c.fold.to_dict().get('pour_cost_status', 'COUNTED') for a, c in result.costs.items()}
            summary['issues'] = [dict(type='MISSING_POUR_COST_RECEIPT', owner='dataset-pour', arm=a,
                consequence='retrieval rates observed; historical fold cost and full-cost acceptance incomplete')
                for a, status in summary['cost_status'].items() if status == 'MISSING_POUR_COST_RECEIPT']
            summary['fingerprints'] = {'before': before, 'after': after, 'match': True}
            result.manifest['random_query_instrument'] = summary
            result.manifest['gpu'] = gpu
            (args.out / 'instrument_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
            print(f"INSTRUMENT {summary['mode']} {summary['verdict']} floor={summary['floor_verdict']}")
            for name, value in summary['bootstrap']['per_arm'].items():
                print(f"  {name} rate={value['rate']} "
                      f"CI=[{value['rate_ci_low']},{value['rate_ci_high']}] "
                      f"baseline={value['strongest_baseline']} difference={value['difference']} "
                      f"difference_CI={value['difference_ci']}")
            print('EXCLUDED_ARMS ' + json.dumps(summary['excluded_arms']))
            for name, accounting in summary['accounting'].items():
                print(f"READS {name} mean={accounting['mean_reads_per_query']}")
                for row in accounting.get('per_query', []):
                    print(f"  {row['task']} visited={row['visited']}/{row['total']} reads={row['reads']}")
            print('ENCODER_BILL ' + json.dumps(summary['encoder_bill']))
            print('ISSUES ' + json.dumps(summary['issues']))
            print(f"FINGERPRINTS_MATCH {before == after}")
        paths = write_run(result, args.out)
    except AtlasError as exc:
        print(f"REFUSED {exc}", file=sys.stderr)
        return 1

    # Correctness first, on stdout, before any cost number is printed.
    arms_seen = [a.protocol.full_id for a in arms]
    print(f"# bench v2 | bundle {bundle.bundle_id[:23]}... | universe {args.universe} "
          f"| {len(bundle.tasks)} tasks | VERDICT {result.manifest['verdict']}")
    print("\n## correctness (before any cost number)")
    for arm in arms_seen:
        rows = [r for r in result.rows if r["arm"] == arm]
        print(f"  {arm:<16} {sum(1 for r in rows if r['correct'])}/{len(rows)}")
    print("\n## cost")
    for arm in arms_seen:
        c = result.costs[arm].to_dict()
        print(f"  {arm:<16} touched_median {c['tokens_touched']['median']}  "
              f"query_model_calls {c['query_model_calls']}  "
              f"fold_seconds {c['fold']['wall_seconds']}  "
              f"latency_median {c['latency_ms']['median']}ms")
    for key, path in paths.items():
        print(f"banked {key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
