"""RESEARCH RESULT PRESENTATION (S1 B5): pure projections of one research record for the catalogue.

Each reads only through writing.research_observation primitives, so the derivation ledger
witnesses every file it consumes; nothing here caches, writes or launches.

  _bounded_measurement            small exact JSON measurements, else omitted (never truncated).
  _presentation                   one record's presentation: currentness, run, figures, measurements.
  _result_usage / _result_visuals where a result is used (concepts, reader plan) and drawn.
  _derived_presentation_artifacts / _manifest_figures
                                  the figure artifacts a record presents, from its manifest.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from laplace.research import research_context


def _bounded_measurement(value: Any) -> Any:
    """Return small scalar/JSON measurements exactly; omit large or irregular payloads."""
    nodes = 0
    def valid(item: Any, depth: int = 0) -> bool:
        nonlocal nodes
        nodes += 1
        if nodes > 128 or depth > 5:
            return False
        if item is None or isinstance(item, (str, int, float, bool)):
            return not isinstance(item, float) or item == item and abs(item) != float("inf")
        if isinstance(item, list):
            return len(item) <= 32 and all(valid(child, depth + 1) for child in item)
        if isinstance(item, dict):
            return (len(item) <= 24 and all(isinstance(key, str) and len(key) <= 200
                    and valid(child, depth + 1) for key, child in item.items()))
        return False
    if not valid(value):
        return None
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        return None
    return value if len(encoded) <= 8192 else None


def _presentation(record: dict, manuscript: Path, project_root: Path, *,
                  currentness_snapshot: dict | None = None,
                  digest_cache: dict | None = None,
                  visual_specs: list[dict] | None = None,
                  run_cache: dict | None = None) -> dict:
    """Resolve human-facing measurements from the exact result, never copied numbers."""
    shown = dict(record)
    base = project_root if record.get('result_scope', record.get('scope')) == 'project' else manuscript
    result = research_context.inside(base, record.get('result', ''))
    payload = {}
    if result and research_observation._present(result) and result.suffix == '.json':
        try: payload = json.loads(result.read_text())
        except (OSError, ValueError): pass
    measurements = []
    for declaration in record.get('measures', []):
        if not isinstance(declaration, dict): continue
        key = declaration.get('key', '')
        value = payload.get(key) if isinstance(payload, dict) else None
        if value is None:
            value = payload
            for part in str(key).split('.'):
                value = value.get(part) if isinstance(value, dict) else None
        measurements.append({**declaration, 'value':_bounded_measurement(value)})
    shown['measurements'] = measurements
    currentness = (currentness_snapshot if currentness_snapshot is not None else
                   research_records._currentness(manuscript,[record],project_root,digest_cache=digest_cache,
                                visual_specs=visual_specs))
    shown['currentness'] = currentness['status']
    shown['currentness_reason'] = currentness['reason']
    observed = next((row.get('dependencies') for row in currentness.get('records', [])
                     if row.get('record_id') == record.get('id')), [])
    shown['current_dependencies'] = observed or []
    shown['dependency_coverage'] = next((row.get('coverage') for row in currentness.get('records', []) if row.get('record_id') == record.get('id')), {})
    if record.get('run_id'):
        run = research_runs._run_status(manuscript, record['run_id'],_cache=run_cache,
                          _digest_cache=digest_cache)
        shown['run'] = ({key: run.get(key) for key in (
            'id', 'producer_id', 'mode', 'state', 'reason', 'started_at',
            'completed_at', 'result_path', 'result_sha256', 'exit_code', 'args')}
            if run else {'id': record['run_id'], 'state': 'MISSING',
                         'reason': 'the named execution receipt is unavailable'})
        if not run or run.get('state') != 'COMPLETE':
            shown['currentness'] = 'STALE'
            shown['currentness_reason'] = (run or {}).get(
                'reason') or 'the named execution is not complete and current'
        if run and isinstance(run.get('producer_id'), str):
            producer, producer_error = research_runs._producer(manuscript, run['producer_id'])
            if producer is not None:
                shown['producer'] = {key: producer.get(key) for key in
                    ('id', 'title', 'description', 'executable', 'scope', 'modes',
                     'dependencies', 'result_path', 'allowed_args')}
            elif producer_error:
                shown['producer'] = {'id': run['producer_id'], 'status': 'MISSING',
                                     'reason': producer_error}
    files = []
    roles = {'config': 'Configuration', 'source': 'Analysis source', 'result': 'Recorded output', 'data': 'Input data'}
    for field, path, scope in research_records.dependency_rows(record):   # the one declared dependency scope
        files.append({'role': roles[field], 'path': path, 'scope': scope})
    producer = shown.get('producer') or {}
    if isinstance(producer.get('executable'), str):
        files.insert(0, {'role': 'Code', 'path': producer['executable'],
                         'scope': producer.get('scope', 'manuscript')})
    existing = {(row.get('scope'), row.get('path')) for row in files}
    for path in producer.get('dependencies') or []:
        identity = (producer.get('scope', 'manuscript'), path)
        if isinstance(path, str) and identity not in existing:
            files.append({'role': 'Producer input', 'path': path, 'scope': identity[0]})
            existing.add(identity)
    if isinstance(record.get('run_id'), str):
        files.extend([
            {'role': 'Run log', 'path': f"{research_runs._RUNS}/{record['run_id']}.stdout.log", 'scope': 'manuscript'},
            {'role': 'Run errors', 'path': f"{research_runs._RUNS}/{record['run_id']}.stderr.log", 'scope': 'manuscript'},
        ])
    for file in files:
        file_base=project_root if file.get('scope')=='project' else manuscript
        target=research_context.inside(file_base or manuscript,file.get('path',''))
        if target is not None:
            file['identity']='sha256:'+hashlib.sha256(str(target).encode()).hexdigest()
            file['availability']='PRESENT' if research_observation._present(target) else 'MISSING'
    shown['evidence_files'] = files
    return shown


def _result_usage(project: str, root: Path, *,
                  records_snapshot: tuple[list[dict], str | None] | None = None,
                  currentness_snapshot: Mapping[str,dict] | None = None,
                  run_cache: dict | None = None,digest_cache: dict | None = None,
                  visual_specs: list[dict] | None = None) -> dict[str, list[dict]]:
    """Join result revisions to canonical concepts and reader-plan locations.

    Bindings remain stored only on conceptric projections.  This function makes
    that existing relation visible to the research reader; it creates no mirror
    record and does not infer support from matching prose or filenames.
    """
    try:
        from laplace.manuscript import project_structure
        try:
            structure = project_structure.state(
                project,root,research_records_snapshot=records_snapshot,
                research_currentness_snapshot=currentness_snapshot,
                research_run_cache=run_cache,research_digest_cache=digest_cache,
                research_visual_specs=visual_specs)
        except TypeError as exc:
            # Preserve compatibility with narrow embedders/test doubles that
            # implement the established two-argument read contract.
            if "research_records_snapshot" not in str(exc):
                raise
            structure = project_structure.state(project, root)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        try:
            from laplace.research import concepts as concepts_surface
            logical = concepts_surface.logical_plan(project, root=root, limit=500) or {}
            structure = {'sections': [], 'logical_objects': logical.get('objects') or []}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}
    locations: dict[str, list[dict]] = {}
    for section in structure.get('sections') or []:
        source = section.get('source') or {}
        location = {key: section.get(key) for key in
                    ('id', 'title', 'kind', 'number', 'order', 'parent_id')}
        location['source_files'] = list(source.get('source_files') or [])
        for node_id in list(section.get('node_ids') or []) + list(section.get('beat_ids') or []):
            locations.setdefault(str(node_id), []).append(location)
    usage: dict[str, list[dict]] = {}
    for node in structure.get('logical_objects') or structure.get('nodes') or []:
        bindings = node.get('result_bindings') or []
        for binding in bindings:
            if not isinstance(binding, dict) or not binding.get('id'):
                continue
            result_id = str(binding['id'])
            usage.setdefault(result_id, []).append({
                'concept': {key: node.get(key) for key in
                            ('id', 'label', 'kind', 'status', 'summary')},
                'binding_revision': binding.get('revision'),
                'manuscript_locations': locations.get(
                    str(node.get('id')), list(node.get('placements') or [])),
            })
    return usage


def _result_visuals(manuscript: Path, project_root: Path, *,
                    records_snapshot: tuple[list[dict], str | None] | None = None,
                    visual_specs: list[dict] | None = None,
                    currentness_snapshot: Mapping[str,dict] | None = None,
                    run_cache: dict | None = None,digest_cache: dict | None = None) -> dict[str, list[dict]]:
    """Reverse-project canonical visual specs through their explicit result ids."""
    try:
        from laplace.pipeline import visual_production
        specs = visual_specs if visual_specs is not None else visual_production.load(manuscript).get('specs') or []
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    linked: dict[str, list[dict]] = {}
    for spec in specs:
        if not isinstance(spec, dict) or not isinstance(spec.get('id'), str):
            continue
        result_ids = spec.get('result_ids') or []
        if not isinstance(result_ids, list):
            continue
        try:
            observed = visual_production.provenance(
                manuscript, spec, project_root,
                research_records_snapshot=records_snapshot,
                research_currentness_snapshot=currentness_snapshot,
                research_run_cache=run_cache,research_digest_cache=digest_cache,
                research_visual_specs=visual_specs)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            observed = {'status': 'UNKNOWN', 'research_binding': {'bindings': []}}
        bindings = {row.get('id'): row for row in
                    (observed.get('research_binding') or {}).get('bindings', [])
                    if isinstance(row, dict)}
        input_scope='manuscript' if project_root.resolve()==manuscript.resolve() else 'project'
        visual = {'visual_id': spec['id'], 'path': spec['id'] + '.pdf',
                  'label': spec.get('title') or spec['id'],
                  'caption': spec.get('caption') or spec.get('question'),
                  'kind': spec.get('kind'), 'source_data': spec.get('source_data'),
                  'source': spec.get('source'), 'input_scope':input_scope,
                  'status': observed.get('status') or 'UNKNOWN',
                  'evidence_binding_status': observed.get('evidence_binding_status') or 'UNKNOWN',
                  'presentation_status': observed.get('presentation_status') or 'UNKNOWN',
                  'metadata_changes': observed.get('metadata_changes') or [],
                  'input_files': observed.get('input_files') or [],
                  'changed_dependencies': observed.get('changed_dependencies') or [],
                  'basis_changes': observed.get('basis_changes') or [],
                  'rendered': isinstance(spec.get('render'), dict),
                  'render': spec.get('render') if isinstance(spec.get('render'), dict) else None}
        for result_id in result_ids:
            if not isinstance(result_id, str) or not result_id:
                continue
            binding = bindings.get(result_id) or {}
            linked.setdefault(result_id, []).append({
                **visual, 'result_revision': binding.get('revision'),
                'result_currentness': binding.get('currentness'),
            })
    return linked


def _derived_presentation_artifacts(manuscript: Path, record: dict, *,
                                    visual_specs: list[dict] | None = None) -> set[tuple[str, str]]:
    """Artifacts explicitly owned by a canonical downstream visual are presentation.

    The classification requires both sides of the existing join: the result
    artifact names ``visual_id`` and that canonical visual spec names this result
    in ``result_ids``. Untyped images remain evidence artifacts.
    """
    try:
        from laplace.pipeline import visual_production
        specs = visual_specs if visual_specs is not None else visual_production.load(manuscript).get('specs') or []
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return set()
    result_id = record.get('id')
    downstream = {str(spec.get('id')) for spec in specs if isinstance(spec, dict)
                  and result_id in (spec.get('result_ids') or []) and spec.get('id')}
    identities = set()
    for artifact in record.get('artifacts') or []:
        if not isinstance(artifact, dict) or artifact.get('visual_id') not in downstream \
                or not isinstance(artifact.get('path'), str):
            continue
        identities.add((artifact.get('scope', record.get('scope', 'manuscript')), artifact['path']))
    return identities


def _manifest_figures(manuscript: Path, project: str) -> list[dict]:
    """Join existing banked manifest rows to the asset store by explicit fields."""
    raw, error = research_observation._read_object(manuscript / "figure_manifest.json", {"placed": []})
    if error:
        return []
    assets_by_render: dict[str, dict] = {}
    try:
        from laplace.pipeline import asset_model
        for asset in asset_model.enumerate_assets(project):
            for render in asset.rendered:
                assets_by_render[Path(render).name] = {"id": asset.id,
                                                       "producer": asset.producer.path}
    except Exception:
        pass
    figures: list[dict] = []
    for row in raw.get("placed") or []:
        if not isinstance(row, dict):
            continue
        artefact = row.get("artefact")
        if not isinstance(artefact, str):
            continue
        asset = assets_by_render.get(Path(artefact).name, {})
        figures.append({
            "id": row.get("asset_id") or asset.get("id") or row.get("label"),
            "label": row.get("label"), "promise": row.get("promise"),
            "generator": row.get("generator"), "artefact": artefact,
            "matched": row.get("matched"), "asset_producer": asset.get("producer"),
            "manifest": "figure_manifest.json",
        })
    return figures


from laplace.research import research_observation  # noqa: E402  (cycle-safe: imported last)
from laplace.research import research_records  # noqa: E402  (cycle-safe: imported last)
from laplace.research import research_runs  # noqa: E402  (cycle-safe: imported last)
