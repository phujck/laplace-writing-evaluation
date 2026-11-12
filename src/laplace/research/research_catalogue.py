"""RESEARCH STATE CATALOGUE (S1 B5): the one derived research state and its ONE cache.

OWNER AND DATA FLOW. `state_payload` is the one producer of the research state; the HTTP
door (`/research/state`, `/research/result`), the catalogue (`view=summary`) and the
writing pipeline all read through it. Deriving it hashes every declared dependency and
artifact of every record, resolves every named run, joins concept usage and reader-plan
locations, and enumerated two directories with `rglob` on EVERY call: measured 310–390 ms
repeated on the live project (plan §11, journey K) for an 18 KB summary.

THE STAMP. A derived state is kept with the WITNESS of everything it was derived from:
the owner's index files (records, manifest, producers, runs index, visual specs, registry),
every file that was hashed for currentness (the `digest_cache` keys are exactly those,
with their stat identity), every run receipt that was resolved, the declared producer
executables, and a directory signature of the source scan roots (the mtime of every
non-hidden directory under them: adding or removing a file changes its directory's
mtime, so the listing is current while the signature is). A read is a HIT when every
witnessed file still has the same (mtime_ns, ctime_ns, size, inode) and every scanned
directory tree the same signature; that costs O(witnessed files + directories) stats and
no byte is hashed. Anything else is a MISS and derives again.

BOUNDS. At most STATE_CACHE_MAX_ENTRIES projects are retained (LRU). The usage join reads
OTHER owners (the structure state: reader plan, concept rewire ledger, authoring state,
feedback, the selected source files), so those files are witnessed too; what remains
unwitnessed is bounded by STATE_CACHE_TTL_S: an entry older than that is re-derived even
when its witness is unchanged (the asset model's own files are the known residual).
Retention is memory only: nothing is written. `index_stamp` on the payload names the
witness a response came from.

INVALIDATION is by witness, never by event: a write through this module's own doors
changes a witnessed file, and an external edit of a dependency does too. A hit returns a
deep copy, so no consumer can mutate the retained entry.

The consumed-file ledger is writing.research_observation._READ_LEDGER (one ContextVar);
_derive_state opens it for each derivation and the witness closes over it.
"""
from __future__ import annotations

import copy
import json
import os
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any


STATE_CACHE_LIVE_TTL_S = 2.0      # retention of a derivation that sampled live process facts
STATE_CACHE_MAX_ENTRIES = 8       # projects retained (LRU)
STATE_CACHE_TTL_S = 30.0          # retention bound for what the witness cannot see
_STATE_CACHE: "OrderedDict[str, dict]" = OrderedDict()   # THE one research state cache
_STATE_CACHE_LOCK = threading.Lock()
_INSPECTABLE = {'.py','.json','.csv','.tsv','.txt','.log','.pdf','.png',
                '.jpg','.jpeg','.svg','.md','.toml','.yaml','.yml','.lean'}


def _directory_signature(directory: Path) -> tuple:
    """(relative directory, mtime_ns) for every non-hidden directory under `directory`.

    One `os.scandir` per directory and no file stats: O(directories). A file added,
    removed or renamed anywhere below changes its own directory's mtime.
    """
    rows = []
    pending = [directory]
    while pending:
        current = pending.pop()
        try:
            st = current.stat()
            rows.append((current.relative_to(directory).as_posix(), st.st_mtime_ns))
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.name.startswith('.'):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                    except OSError:
                        continue
        except OSError:
            rows.append((current.relative_to(directory).as_posix() if current != directory else '.', None))
    return tuple(sorted(rows))


def _walk_sources(directory: Path):
    """Inspectable files under `directory`, hidden parts skipped, shallowest first then by path.

    The replacement for the per-call `rglob('*')` + `is_file()` + suffix filter: one
    `os.walk` that prunes hidden directories instead of visiting every entry.
    """
    found = []
    for current, dirnames, filenames in os.walk(directory):
        dirnames[:] = [name for name in dirnames if not name.startswith('.')]
        base = Path(current)
        for name in filenames:
            if name.startswith('.') or Path(name).suffix.lower() not in _INSPECTABLE:
                continue
            candidate = base / name
            relative = candidate.relative_to(directory)
            found.append(((len(relative.parts), relative.as_posix()), candidate))
    return [candidate for _key, candidate in sorted(found, key=lambda row: row[0])]


def _state_witness(root: Path, item: Any, manuscript: Path, *, project: str, digest_cache: dict, run_cache: dict,
                   producers: list, scanned: list[Path], ledger: dict | None = None) -> dict:
    from laplace.research import corpus_ingest
    from laplace.pipeline import registry
    # the owner index files and the cross-owner inputs of the usage join (`_result_usage`
    # reads the structure state): reader plan, concept rewire ledger, authoring state and
    # feedback, plus every file of the selected source traversal
    paths = set(_index_paths(root, item, manuscript, project))
    try:
        from laplace.manuscript import manuscript_source
        selected = manuscript_source.resolve(project, root, include_candidates=False)
        if selected.get('root'):
            for file in manuscript_source.traversal(selected['root'], root).get('files', []):
                paths.add(root / file)
    except Exception:   # noqa: BLE001 — the owner's own witness still stands; the TTL bounds the rest
        pass
    for key in digest_cache:
        if isinstance(key, tuple) and key and isinstance(key[0], str):
            paths.add(Path(key[0]))
    for key in run_cache:
        if isinstance(key, tuple) and len(key) == 2:
            paths.add(Path(key[0]) / research_runs._RUNS / f"{key[1]}.json")
            paths.add(Path(key[0]) / research_runs._RUNS / f"{key[1]}.receipt.json")
    # every file the derivation consumed through _read_object / _digest / _present
    for consumed in (ledger or {}).get('files', {}):
        paths.add(Path(consumed))
    project_root = research_context.project_root(item, root) or manuscript
    for producer in producers or []:
        executable = producer.get('executable') if isinstance(producer, dict) else None
        if isinstance(executable, str) and executable:
            resolved = research_context.inside(project_root, executable) or research_context.inside(manuscript, executable)
            if resolved is not None:
                paths.add(resolved)
    return {'files': {str(path): research_observation._stat_identity(path) for path in paths},
            'dirs': {str(directory): _directory_signature(directory) for directory in scanned}}


def _witness_current(witness: dict) -> bool:
    for path, identity in witness.get('files', {}).items():
        if research_observation._stat_identity(Path(path)) != identity:
            return False
    for directory, signature in witness.get('dirs', {}).items():
        if _directory_signature(Path(directory)) != signature:
            return False
    return True


def _witness_stamp(witness: dict) -> str:
    return "sha256:" + research_observation._object_digest({'files': witness.get('files', {}),
                                        'dirs': {key: list(value) for key, value in witness.get('dirs', {}).items()}})


def state_cache_clear() -> None:
    with _STATE_CACHE_LOCK:
        _STATE_CACHE.clear()


STATE_DERIVE_ATTEMPTS = 3   # a derivation whose inputs moved under it is retried this many times


def _index_paths(root: Path, item: Any, manuscript: Path, project: str) -> set[Path]:
    """The owner index files and cross-owner inputs that are read (not hashed) during a derivation."""
    from laplace.research import corpus_ingest
    from laplace.pipeline import registry
    from laplace.projects import writing_portability
    project_root = research_context.project_root(item, root) or manuscript
    paths = {manuscript / research_records._RECORDS, manuscript / 'figure_manifest.json', manuscript / research_runs._PRODUCERS,
             manuscript / 'manuscript_spec.json', manuscript / 'visual_specs.json',
             root / registry.DATA_PROJECTS_FILE, research_runs._declared_run_home(item, root, manuscript) / 'index.json',
             corpus_ingest._rewire_path(root, project), manuscript / 'authoring.json',
             manuscript / 'feedback' / 'feedback.jsonl',
             # cross-module inputs the footprint audit found (manuscript_source.resolve reads the
             # document selection; writing_portability.relocate_run reads the portability manifests)
             manuscript / 'document_selection.json', root / writing_portability.MANIFEST,
             project_root / writing_portability.MANIFEST, manuscript / writing_portability.MANIFEST}
    record = registry.resolve(project, root)
    if record is not None and getattr(record, 'plan_path', ''):
        plan = record.plan(root)
        if plan is not None:
            paths.add(plan)
    return paths


def _scan_roots(root: Path, item: Any, manuscript: Path) -> list[Path]:
    """Every candidate source scan root, present or ABSENT: an absent root that appears is a change."""
    roots = [manuscript.parent / 'numerics']
    if getattr(item, 'evidence_store', ''):
        evidence = item.path(item.evidence_store, root)
        if evidence is not None:
            roots.append(evidence)
    return roots


def _witness_dirs(root: Path, item: Any, manuscript: Path) -> list[Path]:
    """The directories whose entry sets the witness signs: the scan roots and the manuscript
    directory itself. The footprint audit showed the selection resolver PROBING conventional
    manuscript roots (main.tex, whitepaper/main.tex) that may not exist; a directory signature
    (one scandir per directory, no file stats) sees such a file appear or disappear."""
    return [*_scan_roots(root, item, manuscript), manuscript]


def _read_basis(cache: str, stamp: str, observed_at: float, *, retries: int = 0, reason: str | None = None,
                live: dict | None = None, ttl: float = STATE_CACHE_TTL_S) -> dict:
    """What a reader is told about the response's basis: cache outcome, witness stamp, age, the
    one join the witness does not cover (the asset model, bounded by the TTL) and, when the
    derivation sampled live process/deadline facts, exactly which runs and how old they may be."""
    age = max(0.0, time.time() - observed_at)
    basis = {'cache': cache, 'index_stamp': stamp,
             'observed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(observed_at)),
             'age_s': round(age, 3),
             'asset_join': {'basis': 'ttl', 'ttl_s': ttl,
                            'remaining_s': round(max(0.0, ttl - age), 3),
                            'note': 'figure asset joins read the asset model, which is not witnessed; they are at most ttl_s old'}}
    if live:
        basis['live_facts'] = {'basis': 'ttl', 'ttl_s': STATE_CACHE_LIVE_TTL_S,
                               'remaining_s': round(max(0.0, STATE_CACHE_LIVE_TTL_S - age), 3),
                               'runs': sorted(live),
                               'note': ('process liveness and deadline state of these RUNNING jobs were sampled at '
                                        'observed_at; a cached answer is at most ttl_s old and is derived again after that')}
    if retries:
        basis['retries'] = retries
    if reason:
        basis['reason'] = reason
    return basis


def _witness_consistent(witness: dict, pre: dict, digest_cache: dict, ledger: dict | None = None) -> bool:
    """The post-derivation witness must equal every identity observed AT READ TIME: the index
    files' pre-derivation stats, every file the ledger saw as it was consumed, every hashed
    file's stat taken when it was hashed, and the scan roots' signatures. Anything else means
    an input moved during the derivation."""
    files = witness.get('files', {})
    for path, identity in pre.get('files', {}).items():
        if files.get(path) != identity:
            return False
    for path, identity in (ledger or {}).get('files', {}).items():
        if files.get(path, None) != identity:
            return False
    for key in digest_cache:
        if not (isinstance(key, tuple) and len(key) == 4 and isinstance(key[0], str)):
            continue
        observed = files.get(key[0])
        if observed is None:
            if key[1:4] != (None, None, None):   # hashed as present, witnessed as absent
                return False
        elif key[1:4] != tuple(observed[:3]):
            return False
    dirs = witness.get('dirs', {})
    for directory, signature in pre.get('dirs', {}).items():
        if dirs.get(directory) != signature:
            return False
    return True


def state_payload(project: str, root: Path | None = None, *, cached: bool = True) -> dict | None:
    """The research state: served from the witness cache when every input is unchanged.

    A derivation is PUBLISHED only when the witness collected after it equals every identity
    observed at read time (`_witness_consistent`); otherwise it is derived again, up to
    STATE_DERIVE_ATTEMPTS times, and after that served UNCACHED with `read_basis.reason`
    saying the inputs kept changing. No response labels a newly witnessed stale derivation
    with a fresh stamp (Sol, 2026-10-12).
    """
    root = (root or research_context.repo_root()).resolve()
    key = f"{root}::{project}"
    now = time.monotonic()
    if cached:
        with _STATE_CACHE_LOCK:
            entry = _STATE_CACHE.get(key)
        if entry is not None and now - entry['at'] <= entry.get('ttl', STATE_CACHE_TTL_S) and _witness_current(entry['witness']):
            with _STATE_CACHE_LOCK:
                if key in _STATE_CACHE:
                    _STATE_CACHE.move_to_end(key)
            payload = copy.deepcopy(entry['payload'])
            payload['read_basis'] = _read_basis('hit', entry['stamp'], entry['observed_at'], live=entry.get('live'), ttl=entry.get('ttl', STATE_CACHE_TTL_S))
            return payload
    item, manuscript = research_context.project(project, root)
    if item is None or manuscript is None:
        return None
    attempts = 0
    while True:
        # THE TTL ANCHOR: retention is measured from the moment the inputs were OBSERVED (the
        # pre-derivation stats, the earliest consumed observation), never from publication;
        # a derivation that outlives its own TTL is served but not retained (Sol 2026-10-12).
        observed_at = time.time(); observed_monotonic = time.monotonic()
        pre = {'files': {str(path): research_observation._stat_identity(path) for path in _index_paths(root, item, manuscript, project)},
               'dirs': {str(directory): _directory_signature(directory) for directory in _witness_dirs(root, item, manuscript)}}
        derived = _derive_state(project, root)
        if derived is None:
            return None
        payload, witness, digest_cache, ledger = derived
        attempts += 1
        if _witness_consistent(witness, pre, digest_cache, ledger):
            break
        if attempts >= STATE_DERIVE_ATTEMPTS:
            stamp = _witness_stamp(witness)
            payload['index_stamp'] = stamp
            payload['read_basis'] = _read_basis('uncached', stamp, observed_at, retries=attempts - 1, live=ledger.get('live'),
                                                reason='inputs changed during derivation on every attempt; this response is not retained')
            return payload
    stamp = _witness_stamp(witness)
    live = ledger.get('live') or None
    ttl = STATE_CACHE_LIVE_TTL_S if live else STATE_CACHE_TTL_S
    payload['index_stamp'] = stamp
    elapsed = time.monotonic() - observed_monotonic
    if elapsed > ttl:
        payload['read_basis'] = _read_basis('uncached', stamp, observed_at, retries=attempts - 1, live=live, ttl=ttl,
                                            reason=f'the derivation took {elapsed:.1f} s, longer than the {ttl:.0f} s retention of its observations; this response is not retained')
        return payload
    payload['read_basis'] = _read_basis('miss', stamp, observed_at, retries=attempts - 1, live=live, ttl=ttl)
    if cached:
        with _STATE_CACHE_LOCK:
            _STATE_CACHE[key] = {'at': observed_monotonic, 'observed_at': observed_at, 'witness': witness, 'stamp': stamp,
                                 'live': live, 'ttl': ttl, 'payload': copy.deepcopy(payload)}
            _STATE_CACHE.move_to_end(key)
            while len(_STATE_CACHE) > STATE_CACHE_MAX_ENTRIES:
                _STATE_CACHE.popitem(last=False)
    return payload


def _derive_state(project: str, root: Path) -> tuple[dict, dict, dict, dict] | None:
    """Derive the research state from its files; returns the payload, its witness, the
    hashed-file identities observed while hashing (the `digest_cache` keys) and the read
    ledger (every consumed file's identity at consumption, and the live facts sampled)."""
    ledger = {'files': {}, 'live': {}}
    token = research_observation._READ_LEDGER.set(ledger)
    try:
        derived = _derive_state_under_ledger(project, root, ledger)
    finally:
        research_observation._READ_LEDGER.reset(token)
    if derived is None:
        return None
    payload, witness, digest_cache = derived
    return payload, witness, digest_cache, ledger


def _derive_state_under_ledger(project: str, root: Path, ledger: dict) -> tuple[dict, dict, dict] | None:
    """One derivation under the open ledger. Phases, in the original read order: records and figures,
    unreviewed available sources, currentness, invalidation edges, producer runs, presented records,
    then the witness. Every join reads the same records snapshot and shares one digest/run cache."""
    item, manuscript = research_context.project(project, root)
    if item is None or manuscript is None:
        return None
    records, error = research_records._records(manuscript)
    experiments = [row for row in records if row.get("kind") == "experiment"]
    results = [row for row in records if row.get("kind") == "result"]
    bindings = [row for row in records if row.get("kind") == "figure_binding"]
    figures = research_presentation._manifest_figures(manuscript, project)
    project_root = research_context.project_root(item, root) or manuscript
    digest_cache:dict={};run_cache:dict={}
    try:
        from laplace.pipeline import visual_production
        visual_specs=visual_production.load(manuscript).get("specs") or []
    except (OSError,ValueError,TypeError,json.JSONDecodeError):
        visual_specs=[]
    available_sources = _available_sources(root, item, manuscript, project_root, experiments + results)
    currentness, currentness_by_id = _derived_currentness(manuscript, project_root, experiments, results,
                                                          digest_cache=digest_cache, run_cache=run_cache,
                                                          visual_specs=visual_specs)
    from laplace.manuscript import manuscript_source
    read_only=bool(manuscript_source.resolve(project,repo_root=root).get('read_only'))
    invalidation = _invalidation(experiments, results, bindings)
    unique_runs = _producer_runs(item, root, manuscript, project, records, run_cache=run_cache, digest_cache=digest_cache)
    presented_results, presented_experiments = _presented_records(
        project, root, manuscript, project_root, (records, error), experiments, results, bindings, figures,
        currentness_by_id, run_cache=run_cache, digest_cache=digest_cache, visual_specs=visual_specs)
    producers = (research_observation._read_object(manuscript/research_runs._PRODUCERS,{"producers":[]})[0].get('producers') or [])
    consumption = _summary_provenance(root, project, manuscript, project_root, producers,
        records, presented_results, presented_experiments, unique_runs, digest_cache)
    witness = _state_witness(root, item, manuscript, project=project, digest_cache=digest_cache, run_cache=run_cache,
                             producers=producers, scanned=_witness_dirs(root, item, manuscript), ledger=ledger)
    # Evaluated only without a records error, after the witness, exactly as before.
    state = "REFUSED" if error else ("COMPLETE" if results and currentness["status"] == "CURRENT" and all(
        (not r.get('run_id')) or (research_runs._run_status(manuscript,r['run_id'],_cache=run_cache,_digest_cache=digest_cache)
                                  or {}).get('state')=='COMPLETE' for r in results) else "UNKNOWN")
    return {
        "schema_version": "laplace.research-state/1",
        "project": project,
        "state": state,
        "records_error": error,
        "currentness": currentness,
        "experiments": presented_experiments,
        "results": presented_results,
        "assets": [asset for asset in figures if asset.get("id")],
        "figures": figures,
        "invalidation": invalidation,
        "_summary_consumption": consumption,
        "producer_runs": unique_runs, "producers": producers, "available_sources":available_sources,
        "read_only": read_only,
        "polling": "none; currentness is recomputed when this endpoint is read and its owned index witness changed",
    }, witness, digest_cache


def _available_sources(root: Path, item, manuscript: Path, project_root: Path, rows: list) -> list[dict]:
    """Up to 30 source files under the scan roots that no record declares (AVAILABLE_UNREVIEWED)."""
    available_sources=[]; seen_sources=set(); linked_sources=set()
    for row in rows:
        default_scope=row.get('scope','manuscript')
        linked_sources.update((default_scope,path) for path in research_records._dependencies(row))
        linked_sources.update((artifact.get('scope',default_scope),artifact.get('path'))
                              for artifact in row.get('artifacts') or []
                              if isinstance(artifact,dict) and isinstance(artifact.get('path'),str))
    scanned_dirs: list[Path] = _scan_roots(root, item, manuscript)   # witnessed whether present or absent
    for directory in scanned_dirs:
        if directory.is_dir():
            for candidate in _walk_sources(directory):
                try:
                    path = candidate.relative_to(project_root).as_posix()
                    scope = 'project'
                except ValueError:
                    try:
                        path = candidate.relative_to(manuscript).as_posix()
                        scope = 'manuscript'
                    except ValueError:
                        continue
                identity=(scope,path)
                if identity in seen_sources or identity in linked_sources:continue
                seen_sources.add(identity)
                available_sources.append({'path':path,'scope':scope,
                                          'state':'AVAILABLE_UNREVIEWED'})
                if len(available_sources)>=30:break
        if len(available_sources)>=30:break
    return available_sources


def _derived_currentness(manuscript: Path, project_root: Path, experiments: list, results: list, *,
                         digest_cache: dict, run_cache: dict, visual_specs: list) -> tuple[dict, dict]:
    """The records' currentness, then STALE when a result names a missing or incomplete run."""
    currentness = research_records._currentness(manuscript,experiments+results,project_root,
                                                digest_cache=digest_cache,visual_specs=visual_specs)
    currentness_by_id={str(row.get("record_id")):{"status":row.get("status"),
        "reason":("all explicitly declared dependencies match their recorded identities"
                  if row.get("status")=="CURRENT" else row.get("reason")),
        "records":[row]} for row in currentness.get("records") or []}
    for result_row in results:
        if not result_row.get('run_id'):
            continue
        run = research_runs._run_status(manuscript,result_row['run_id'],_cache=run_cache,
                                        _digest_cache=digest_cache)
        if run is None:
            currentness['status']='STALE';currentness['reason']='a result names a missing run receipt'
            break
        if run.get('state') != 'COMPLETE':
            currentness['status']='STALE';currentness['reason']='a result run or its producer provenance is no longer current'
            break
    return currentness, currentness_by_id


def _invalidation(experiments: list, results: list, bindings: list) -> list[dict]:
    """The declared invalidation edges: inputs, depicted figures, manifest identity, explicit bindings."""
    invalidation = []
    for row in experiments + results:
        for dependency in research_records._dependencies(row):
            invalidation.append({"from": dependency, "to": row.get("id"), "kind": "declared-input"})
        for figure_id in row.get("figure_ids") or []:
            invalidation.append({"from": row.get("id"), "to": figure_id,
                                 "kind": "result-depicted-by-figure"})
        for figure_id in row.get("evidence_for") or []:
            invalidation.append({"from": "figure_manifest.json", "to": figure_id,
                                 "kind": "manifest-identity"})
            invalidation.append({"from": figure_id, "to": row.get("id"), "kind": "explicit-figure-evidence"})
    for row in bindings:
        invalidation.append({"from": row.get("result_id"), "to": row.get("figure_id"),
                             "kind": "explicit-binding", "relation":"depicts"})
    return invalidation


def _producer_runs(item, root: Path, manuscript: Path, project: str, records: list, *,
                   run_cache: dict, digest_cache: dict) -> list[dict]:
    """Recorded runs plus every indexed run handle, each checked against its exact locator identity."""
    indexed_runs = research_runs._runs(manuscript,records,run_cache=run_cache,digest_cache=digest_cache)
    run_index, _ = research_observation._read_object(research_runs._declared_run_home(item,root,manuscript) / 'index.json',
                                                     {'runs': []})
    handles = run_index.get('run_handles') or {}
    for run_id in run_index.get('runs') or []:
        handle = handles.get(run_id) if isinstance(handles,dict) else None
        target = research_runs._pending_job(handle,root) if handle is not None else None
        run = research_runs._run_status(target.parent.parent if target else manuscript,run_id,
                                        _cache=run_cache,_digest_cache=digest_cache)
        if handle is not None and (not target or not run or handle.get('project')!=project
                or run.get('project')!=project or run.get('launch_token')!=handle.get('launch_token')):
            run = {'id':run_id,'state':'UNAVAILABLE','reason':'run locator identity mismatch'}
        if run:
            indexed_runs.append(run)
    return list({run['id']: run for run in indexed_runs if run.get('id')}.values())


def _presented_records(project: str, root: Path, manuscript: Path, project_root: Path, records_snapshot: tuple,
                       experiments: list, results: list, bindings: list, figures: list, currentness_by_id: dict, *,
                       run_cache: dict, digest_cache: dict, visual_specs: list) -> tuple[list, list]:
    """Each result and experiment presented, with usage, linked figures and visuals and renewal history."""
    # Every join in this response is against the same exact records snapshot.
    # Besides avoiding dozens of identical JSON parses, this prevents one state
    # response from mixing revisions if an owner write lands between joins.
    usage = research_presentation._result_usage(project,root,records_snapshot=records_snapshot,
        currentness_snapshot=currentness_by_id,run_cache=run_cache,
        digest_cache=digest_cache,visual_specs=visual_specs)
    result_visuals = research_presentation._result_visuals(
        manuscript,project_root,records_snapshot=records_snapshot,visual_specs=visual_specs,
        currentness_snapshot=currentness_by_id,run_cache=run_cache,digest_cache=digest_cache)
    renewal_history = research_records._renewal_history(manuscript)
    presented_results = []
    figures_by_id = {str(figure.get('id')): figure for figure in figures if figure.get('id')}
    bindings_by_result: dict[str, list[dict]] = {}
    for binding in bindings:
        result_id = binding.get('result_id')
        figure_id = binding.get('figure_id')
        if not isinstance(result_id, str) or not isinstance(figure_id, str):
            continue
        bindings_by_result.setdefault(result_id, []).append({
            'binding_id': binding.get('id'), 'figure_id': figure_id,
            'figure': figures_by_id.get(figure_id),
        })
    for row in results:
        shown = research_presentation._presentation(row,manuscript,project_root,
            currentness_snapshot=currentness_by_id.get(str(row.get("id"))),
            digest_cache=digest_cache,visual_specs=visual_specs,run_cache=run_cache)
        shown['usage'] = usage.get(str(row.get('id')), [])
        shown['linked_figures'] = bindings_by_result.get(str(row.get('id')), [])
        shown['linked_visuals'] = result_visuals.get(str(row.get('id')), [])
        shown['renewal_history'] = renewal_history.get(str(row.get('id')), [])
        presented_results.append(shown)
    presented_experiments = []
    for row in experiments:
        shown = research_presentation._presentation(row,manuscript,project_root,
            currentness_snapshot=currentness_by_id.get(str(row.get("id"))),
            digest_cache=digest_cache,visual_specs=visual_specs,run_cache=run_cache)
        shown['renewal_history'] = renewal_history.get(str(row.get('id')), [])
        presented_experiments.append(shown)
    return presented_results, presented_experiments


def _catalogue_result(row: dict) -> dict:
    return {key:row.get(key) for key in
            ("id","revision","title","question","summary","kind","currentness","limitations")
            if key in row} | {
        "usage":[{"concept":{key:(item.get("concept") or {}).get(key)
                                for key in ("id","label","title","kind")},
                  "manuscript_locations":[{key:place.get(key) for key in ("id","title")}
                                          for place in item.get("manuscript_locations") or []]}
                 for item in row.get("usage") or []],
        "linked_visuals":[{key:visual.get(key) for key in
                            ("visual_id","label","kind","status","evidence_binding_status",
                             "presentation_status","rendered")}
                           for visual in row.get("linked_visuals") or []],
        "next_read":{"operation":"research","payload":{"view":"result","id":row.get("id")}}}


def state_read(project: str, root: Path | None = None, *, view: str = '', ident: str = '') -> tuple[int, dict]:
    """One project's research state for the HTTP door and the native operation: (status, value).

    view=result selects one exact result row by id (404 when the project or the row is unavailable);
    view=summary is the catalogue; the default is the full state."""
    result = state_payload(project, root=root)
    if view == 'result':
        row = next((item for item in (result or {}).get("results") or [] if item.get("id") == ident), None)
        return ((200, {"schema_version": "laplace.research-result-detail/1", "project": project,
                       "result": row, "exact": True}) if row is not None
                else (404, {"error": "result is unavailable"}))
    if result is None:
        return 404, {"error": "unknown project"}
    return 200, (catalogue_payload(result) if view == 'summary' else
                 {k:v for k,v in result.items() if k != '_summary_consumption'})



def _summary_provenance(root, project, manuscript, project_root, producers, records,
                        results, experiments, runs, digest_cache):
    """Only Research inputs, under the SAME open derivation ledger and closing witness.

    Code is hashed even without a completed run. Current dependency bytes remain
    significant while a record is already stale. Never use stat stamps as substance.
    """
    from laplace.manuscript import manuscript_source
    issues, declared = [], []
    config, error = research_observation._read_object(manuscript/research_runs._PRODUCERS, {"producers":[]})
    if error: issues.append(error)
    if config.get("producers", []) != producers: issues.append("producer declaration moved")
    for producer in producers:
        if not isinstance(producer, dict):
            issues.append("malformed producer"); continue
        scope = producer.get("scope", "manuscript")
        base = project_root if scope == "project" else manuscript
        if scope not in {"project", "manuscript"}:
            issues.append("unsupported producer scope"); continue
        executable = producer.get("executable")
        if not isinstance(executable, str) or not executable:
            issues.append("producer executable unavailable"); continue
        code = research_observation._relative_digest(base, executable, _cache=digest_cache)
        dependencies = producer.get("dependencies", [])
        if not isinstance(dependencies, list) or any(not isinstance(p,str) or not p for p in dependencies):
            issues.append("producer dependencies malformed"); continue
        inputs = [research_observation._relative_digest(base,p,_cache=digest_cache)
                  for p in dict.fromkeys(dependencies)]
        if any(p.get("status") != "PRESENT" for p in [code,*inputs]):
            issues.append("producer code/input unavailable")
        declared.append({"declaration":producer,"scope":scope,"code":code,"dependencies":inputs})
    selected = manuscript_source.resolve(project, repo_root=root, include_candidates=False)
    for rows in (producers, records, runs):
        ids=[row.get("id") for row in rows if isinstance(row,dict)]
        if len(ids)!=len(set(ids)): issues.append("ambiguous Research identity")
    if any(run.get("state") in {"UNAVAILABLE","CLEANUP_UNRESOLVED"} for run in runs):
        issues.append("run provenance unavailable")
    if any(row.get("currentness") in {"UNKNOWN","UNAVAILABLE","UNTRACKED"} for row in results):
        issues.append("result provenance unavailable")
    source = {k:selected.get(k) for k in ("root","manuscript_dir","edition","read_only","status")}
    # Scientific analysis sources are pinned by records/current_dependencies and
    # producer code above. Manuscript text remains the proposal's independent
    # exact source guard, including its proven owned-sibling inverse. Consuming
    # it again here would wrongly stale that inverse after the first hunk.
    return {"schema_version":"laplace.research-consumption-basis/1",
            "project":project,"view":"summary","complete":not issues,
            "issues":issues,"producers":declared,"records":records,"results":results,
            "experiments":experiments,"runs":runs,"source":source}


def summary_consumption(value):
    """Owner-defined projection. Only two recognised launch-control positions are omitted.

    Every other field of the action, including args.request_id, stays significant.
    Cache age/transport stamps are raw diagnostics. Live state/deadline and
    provenance remain inside the witnessed basis. Unknown shapes refuse.
    """
    if (not isinstance(value,dict) or value.get("schema_version") != "laplace.research-catalogue/1"
            or not isinstance(value.get("project"),str)):
        raise ValueError("Unsupported Research summary shape")
    basis = value.get("consumption_basis")
    if (not isinstance(basis,dict) or basis.get("schema_version") != "laplace.research-consumption-basis/1"
            or basis.get("project") != value["project"] or basis.get("view") != "summary"
            or basis.get("complete") is not True or basis.get("issues")
            or set(basis)!={"schema_version","project","view","complete","issues","provenance_sha256"}
            or not isinstance(basis.get("provenance_sha256"),str)
            or not re.fullmatch(r"[0-9a-f]{64}",basis["provenance_sha256"])
            or value.get("records_error") or (value.get("read_basis") or {}).get("cache") == "uncached"):
        raise ValueError("Research summary consumption coverage unavailable")
    observation = value.get("read_basis") or {}
    if set(observation)-{"cache","index_stamp","observed_at","age_s","asset_join","live_facts","retries","reason"}:
        raise ValueError("Unsupported Research observation metadata")
    projected = copy.deepcopy({k:v for k,v in value.items()
        if k not in {"read_basis","index_stamp","read_receipt","context_refresh","author_updates","turn_input"}})
    projected["observation_policy"] = {
        "asset_join":{k:v for k,v in (observation.get("asset_join") or {}).items() if k!="remaining_s"},
        "live_facts":{k:v for k,v in (observation.get("live_facts") or {}).items() if k!="remaining_s"}}
    for producer in projected.get("producers",[]):
        if not isinstance(producer,dict): raise ValueError("Malformed summary producer")
        action = producer.get("launch_action")
        try:
            native, http = action["native"], action["http"]
            payload, wire = native["payload"], http["payload"]
            if (set(action)!={"id","title","permitted","fields","http","native","request_read","new_decision_read","meaning"}
                    or set(native)!={"operation","payload"} or set(http)!={"method","url","payload"}
                    or not isinstance(payload,dict) or not isinstance(payload.get("args"),dict)
                    or set(payload)-{"producer_id","request_id","args","mode","runtime_seconds"}):
                raise ValueError("Unsupported Research launch shape")
            if (action["id"] != "run-"+producer["id"] or native["operation"] != "experiment_run"
                    or http["method"] != "POST" or payload != wire
                    or payload["producer_id"] != producer["id"]
                    or not re.fullmatch(r"research-[0-9a-f]{32}",payload["request_id"])
                    or http["url"] != "/research/run?"+research_runs._query({"project":value["project"]})):
                raise ValueError("Unsupported Research launch action")
            del payload["request_id"]; del wire["request_id"]
        except (KeyError,TypeError,AttributeError) as exc:
            raise ValueError("Unsupported Research launch action") from exc
    return projected


def catalogue_payload(value: dict) -> dict:
    """Small Research index; exact record provenance is an explicit descent."""
    summary = {"schema_version":"laplace.research-catalogue/1","project":value.get("project"),
        "state":value.get("state"),"records_error":value.get("records_error"),
        "index_stamp":value.get("index_stamp"),"read_basis":value.get("read_basis"),
        "results":[_catalogue_result(row) for row in value.get("results") or []],
        "producers":[{**{key:row.get(key) for key in
                      ("id","title","description","executable","modes","allowed_args")},
                      "launch_action":research_runs.producer_launch_action(value['project'],row)}
                     for row in value.get("producers") or []],
        "producer_runs":[{**{key:row.get(key) for key in ("id","producer_id","mode","state")},
                          "next_read":{"operation":"run_status","payload":{"id":row.get("id")}}}
                         for row in value.get("producer_runs") or []],
        "figures":value.get("figures") or [],"available_sources":value.get("available_sources") or [],
        "read_only":value.get("read_only"),
        "detail":{"route":"/research/result","query":{"project":value.get("project"),"id":"<result id>"}},
        "omission":{"result_detail_fields":["measurements","linked visual provenance","evidence files",
            "current dependencies","renewal history","producer/run provenance"],
            "note":"Exact result detail remains available by stable result id."}}
    facts = value.get("_summary_consumption")
    summary["consumption_basis"] = ({k:facts[k] for k in
        ("schema_version","project","view","complete","issues")} |
        {"provenance_sha256":research_observation._object_digest(facts)}) if isinstance(facts,dict) else None
    return summary


from laplace.research import research_observation  # noqa: E402  (cycle-safe: imported last)
from laplace.research import research_presentation  # noqa: E402  (cycle-safe: imported last)
from laplace.research import research_records  # noqa: E402  (cycle-safe: imported last)
from laplace.research import research_runs  # noqa: E402  (cycle-safe: imported last)
from laplace.research import research_context  # noqa: E402
