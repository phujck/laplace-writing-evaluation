"""One read-only, source-hashed status record for an Atlas project."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "laplace.atlas-current-projection/2"


def _snapshot(root: Path, relative: Path) -> tuple[dict[str, Any], bytes | None]:
    path = root / relative
    if not path.is_file():
        return {"path": str(relative), "status": "MISSING"}, None
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    stable = (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
    return {"path": str(relative), "status": "PRESENT", "currentness": "CURRENT-AT-OBSERVATION" if stable else "MOVED-DURING-READ",
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest(), "bytes": len(data), "mtime_ns": before.st_mtime_ns}, data


def _json_snapshot(root: Path, relative: Path) -> tuple[dict[str, Any], Any | None]:
    source, data = _snapshot(root, relative)
    if data is None:
        return source, None
    try:
        return source, json.loads(data)
    except json.JSONDecodeError as exc:
        return {**source, "parse": "INVALID", "error": str(exc)}, None


def _jsonl_snapshot(root: Path, relative: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source, data = _snapshot(root, relative)
    if data is None:
        return source, []
    rows, invalid = [], []
    for number, line in enumerate(data.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            invalid.append(number)
        else:
            if isinstance(row, dict): rows.append(row)
            else: invalid.append(number)
    return ({**source, "parse": "PARTIAL", "invalid_lines": invalid[:12]} if invalid else source), rows


def _paths(project: str) -> dict[str, Path]:
    if not project or Path(project).name != project or project in {".", ".."}:
        raise ValueError("project must be a registered-style name, not a path")
    base = Path("synthetics papers") / project
    return {"base": base, "manifest": base / "spec/manuscript_spec.json", "worklist": base / "spec/worklist.json", "graph": base / "spec/conceptric_v1.json", "ledger": Path("corpus_friction") / f"{project}.jsonl", "campaign": Path("corpus_friction/campaign.jsonl")}


def _result_paths(root: Path, paths: dict[str, Path], manifest: Any) -> list[Path]:
    found: set[Path] = set()
    if isinstance(manifest, dict):
        for benchmark in manifest.get("benchmarks", []):
            if isinstance(benchmark, dict) and isinstance(benchmark.get("results"), str): found.add(Path(benchmark["results"]))
    for directory, pattern in ((root / paths["base"] / "numerics/results", "*.json"), (root / paths["base"] / "spec", "*_verify.json")):
        if directory.is_dir(): found.update(path.relative_to(root) for path in directory.glob(pattern))
    return sorted(found, key=str)


def _coverage(graph: Any, ledger_rows: list[dict[str, Any]], work_ids: set[str]) -> dict[str, Any]:
    nodes = graph.get("nodes", []) if isinstance(graph, dict) else []
    graph_ids = {str(node["id"])[5:] for node in nodes if isinstance(node, dict) and str(node.get("id", "")).startswith("work:")}
    ledger_ids = {str(row.get("id", "")) for row in ledger_rows}
    def face(ids: set[str]) -> dict[str, Any]:
        missing = sorted(work_ids - ids)
        return {"classification": "DATED-PROJECTION", "covered_count": len(work_ids & ids), "missing_count": len(missing), "missing_ids": missing[:8], "currentness": "STALE" if missing else "UNVERIFIED-CURRENT"}
    return {"worklist_item_count": len(work_ids), "generated_graph": face(graph_ids), "project_ledger": face(ledger_ids)}


def project_atlas_current_status(repo_root: Path | str, *, project: str,
                                 work_cap: int = 8, result_cap: int = 12) -> dict[str, Any]:
    """Project current records for *project* without executing campaign gates."""
    if work_cap < 1 or result_cap < 1: raise ValueError("caps must be at least one")
    root, paths = Path(repo_root), _paths(project)
    manifest_source, manifest = _json_snapshot(root, paths["manifest"])
    work_source, worklist = _json_snapshot(root, paths["worklist"])
    graph_source, graph = _json_snapshot(root, paths["graph"])
    ledger_source, ledger_rows = _jsonl_snapshot(root, paths["ledger"])
    campaign_before, _ = _snapshot(root, paths["campaign"])
    items = worklist.get("items", []) if isinstance(worklist, dict) else []
    work = [item for item in items if isinstance(item, dict) and item.get("id")]
    work_ids = {str(item["id"]) for item in work}
    from laplace.engine import wake
    effective_campaign = wake.campaign(root, run_gates=False)
    campaign_after, _ = _snapshot(root, paths["campaign"])
    campaign_currentness = "CURRENT-AT-OBSERVATION" if campaign_before.get("sha256") == campaign_after.get("sha256") else "MOVED-DURING-PROJECTION"
    records = []
    result_paths = _result_paths(root, paths, manifest)
    for relative in result_paths[-result_cap:]:
        path = root / relative
        if path.is_file():
            stat = path.stat()
            source = {"path": str(relative), "status": "REFERENCED", "bytes": stat.st_size,
                      "mtime_ns": stat.st_mtime_ns, "content_verification": "on exact descent"}
        else:
            source = {"path": str(relative), "status": "MISSING"}
        records.append({"path": str(relative), "source": source, "record_kind": "RESULT-REFERENCE",
                        "descend": "scripts/laplace-python scripts/reconstruct_node.py " + __import__("shlex").quote(str(relative))})
    effective_campaign = {key: effective_campaign.get(key) for key in ("next_act", "progress", "schema_residuals")} | {
        "stages": [{key: stage.get(key) for key in ("id", "status", "generation")} for stage in effective_campaign.get("stages", [])]}
    visible = [{"id": item["id"], "item": item.get("item"), "discharge": item.get("discharge")} for item in work[-work_cap:]]
    payload = {"schema_version": SCHEMA, "project": project, "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "authority": {"work": str(paths["worklist"]), "result_records": "manifest-declared and project-discovered JSON records", "campaign": "laplace.engine.wake.campaign(root, run_gates=False)"}, "sources": {"manifest": manifest_source, "worklist": work_source, "generated_graph": graph_source, "project_ledger": ledger_source, "campaign": campaign_after}, "worklist": {"version": worklist.get("worklist_version") if isinstance(worklist, dict) else None, "item_count": len(work), "visible_items": visible, "omitted_item_count": max(0, len(work) - len(visible))}, "result_records": {"count": len(result_paths), "visible": records, "omitted_count": max(0, len(result_paths) - len(records))}, "campaign": {"currentness": campaign_currentness, "effective": effective_campaign if campaign_currentness == "CURRENT-AT-OBSERVATION" else None}, "coverage": _coverage(graph, ledger_rows, work_ids), "read_only": True}
    payload["shown_handle"] = "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return payload


__all__ = ["SCHEMA", "project_atlas_current_status"]
