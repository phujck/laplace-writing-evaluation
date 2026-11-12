"""Pre-registered, paired random queries over a frozen segmentation."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import hashlib

from ..errors import AtlasError, ProtocolViolation
from ..ids import hash_bytes
from ..snapshot import load_snapshot
from ..tools.freeze_tasks import build as freeze_tasks
from .freeze import find_anchor
from .scoring import normalize
from .universe import FULL_UNIVERSE, SnapshotView


def fingerprint(root):
    """Static file bytes and extent, including relative paths; no store writes."""
    root = Path(root)
    digest, count, extent = hashlib.sha256(), 0, 0
    for path in sorted(p for p in root.rglob('*') if p.is_file()):
        raw = path.read_bytes()
        name = str(path.relative_to(root)).encode()
        digest.update(len(name).to_bytes(8, 'big') + name)
        digest.update(len(raw).to_bytes(8, 'big') + raw)
        count += 1
        extent += len(raw)
    return dict(sha256=digest.hexdigest(), files=count, bytes=extent)


def assert_registered_before(registered_ts, started_ts):
    try:
        registered = datetime.fromisoformat(registered_ts.replace('Z', '+00:00'))
        started = datetime.fromisoformat(started_ts.replace('Z', '+00:00'))
        valid = registered.tzinfo is not None and started.tzinfo is not None and registered < started
    except (TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise ProtocolViolation('registration must precede draw and run',
                                registered_ts=registered_ts, started_ts=started_ts)


def unique_atoms(view):
    accepted, excluded = [], Counter()
    for span in sorted(view.leaf_spans, key=lambda s: (s.node_id, s.start, s.end, s.span_id)):
        atom = view.span_text(span)
        if not normalize(atom):
            excluded['empty'] += 1
            continue
        anchors = find_anchor(view, 0, [atom])
        if len(anchors) != 1:
            excluded['absent' if not anchors else 'ambiguous'] += 1
        elif anchors[0].span_id != span.span_id:
            excluded['owner_mismatch'] += 1
        else:
            accepted.append((span, atom, anchors[0]))
    return accepted, {'atoms_before': len(view.leaf_spans), 'atoms_after_uniqueness': len(accepted),
                      'excluded_count': sum(excluded.values()), 'excluded_reasons': dict(excluded)}


def displaced_population(view, spans, atoms):
    groups, valid = {}, {}
    for s in view.leaf_spans:
        p = spans.get(s.parent_span)
        if p and not p.is_leaf and p.node_id == s.node_id and p.start <= s.start < s.end <= p.end:
            groups.setdefault(p.span_id, []).append(s)
            valid[s.span_id] = p
    for group in groups.values():
        group.sort(key=lambda s: (s.start, s.end, s.span_id))
    population, excluded = [], Counter()
    for span, atom, anchor in atoms:
        parent = valid.get(span.span_id)
        if parent is None:
            excluded['missing_or_invalid_parent'] += 1
            continue
        group = groups[parent.span_id]
        if len(group) < 2:
            excluded['singleton_parent'] += 1
            continue
        i = group.index(span)
        sibling = group[i + 1 if i + 1 < len(group) else i - 1]
        question = view.span_text(sibling)
        if normalize(atom) in normalize(question):
            excluded['query_contains_target'] += 1
            continue
        population.append((span, atom, anchor, sibling, question))
    return population, dict(excluded)


def draw(registration_path: Path, out: Path):
    raw = registration_path.read_bytes()
    reg = json.loads(raw)
    started = datetime.now(timezone.utc).isoformat()
    assert_registered_before(reg['registered_ts'], started)
    if reg['schema'] != 'qrc-two-mode/1' or reg['universe'] != 'full':
        raise ProtocolViolation('unsupported instrument schema or universe')
    snap = load_snapshot(Path(reg['snapshot_dir']))
    snap.verify()
    segmentation = snap.segmentation()
    if snap.manifest.snapshot_id != reg['snapshot_id'] or segmentation['generation_id'] != reg['segmentation_id']:
        raise ProtocolViolation('instrument snapshot or segmentation mismatch')
    view = SnapshotView(snap, FULL_UNIVERSE)
    atoms, report = unique_atoms(view)
    population, exclusions = displaced_population(view, snap.spans, atoms)
    report.update(displacement_exclusions=exclusions, eligible_population=len(population),
                  registered_ts=reg['registered_ts'], draw_started_ts=started,
                  registration_sha256=hash_bytes(raw))
    out.mkdir(parents=True, exist_ok=True)
    (out / 'population.json').write_text(json.dumps(report, indent=2) + '\n')
    if len(population) < max(reg['minimum_population'], reg['draws_per_mode']):
        raise ProtocolViolation('INSUFFICIENT_UNIQUE_POPULATION', population=report)
    selected = random.Random(reg['draw_seed']).sample(population, reg['draws_per_mode'])
    results = {}
    for mode in ('VERBATIM', 'DISPLACED'):
        tasks = []
        for i, (span, atom, anchor, sibling, question) in enumerate(selected):
            tasks.append(dict(schema_version='bench-task/2', task_id=f'Q{i:03d}', task_class=mode,
                              question=atom if mode == 'VERBATIM' else question,
                              atoms=[atom], anchors=[anchor.to_dict()], window=None,
                              source=span.node_id, truth_date='2026-09-14',
                              intent=f'target={span.span_id}; query_span={span.span_id if mode == "VERBATIM" else sibling.span_id}; parent={span.parent_span}'))
        sampling = dict(kind='random-query', random_query_instrument=True, mode=mode,
                        seed=reg['draw_seed'], draws=reg['draws_per_mode'], **report)
        source = dict(tasks=tasks, sampling=sampling, predictions={'instrument': reg},
                      note=json.dumps(sampling, sort_keys=True))
        source_path = out / f'{mode}-source.json'
        with source_path.open('x') as stream:
            stream.write(json.dumps(source, indent=2) + '\n')
        frozen = freeze_tasks(Path(reg['snapshot_dir']), source_path, out / 'bundles', 'full')
        results[mode] = str(frozen['path'] / 'tasks.json')
    report['bundles'] = results
    (out / 'population.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--registration', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    try:
        print(json.dumps(draw(args.registration, args.out), indent=2))
    except AtlasError as exc:
        print(f'REFUSED {exc}')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
