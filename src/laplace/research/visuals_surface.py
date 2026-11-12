"""HTTP-shaped visual production and source-addressed placement surface."""
from __future__ import annotations
from laplace.core.checkout import source_tree

import hashlib
import json
import os
from pathlib import Path
import re

from filelock import FileLock, Timeout
from laplace.core.receipts import bundle, file_receipt
from laplace.core.identity import bytes_digest as mutation_digest
from laplace.pipeline import visual_production as vp
from laplace.core import identity_doors
from laplace.manuscript import manuscript_source

_JSON = "application/json; charset=utf-8"


def _r() -> Path:
    return source_tree()


def _j(status, value):
    return status, _JSON, json.dumps(value, ensure_ascii=False).encode()


def _q(query, name, default=""):
    value = query.get(name, default)
    return value[0] if isinstance(value, list) and value else value


def _m(project, repo_root=None):
    from laplace.pipeline import registry
    root = Path(repo_root).resolve() if repo_root else _r()
    record = registry.resolve(project, repo_root=root)
    return record.path(record.manuscript_dir, root) if record and record.manuscript_dir else None


def _project_base(project: str, root: Path, manuscript: Path) -> Path:
    from laplace.pipeline import registry
    record = registry.resolve(project, repo_root=root)
    if record and record.project_dir:
        candidate = record.path(record.project_dir, root)
        if candidate is not None and candidate.resolve().is_relative_to(root):
            return candidate.resolve()
    return manuscript.resolve()


def _selected_target(project: str, section: str, root: Path, *,
                     source: dict | None = None,
                     traversal: dict | None = None) -> tuple[Path | None, dict]:
    from laplace.manuscript import manuscript_source
    source = source or manuscript_source.resolve(project, repo_root=root)
    raw = Path(str(section or ""))
    if not section or raw.is_absolute() or ".." in raw.parts or not source.get("root"):
        return None, source
    traversal = traversal or manuscript_source.traversal(source["root"], repo_root=root)
    allowed = set(traversal.get("files") or [])
    source_dir = Path(source.get("manuscript_dir") or "")
    if not source_dir.is_absolute():
        source_dir = root / source_dir
    candidates = [(root / raw).resolve(), (source_dir / raw).resolve()]
    for candidate in candidates:
        try:
            repo_rel = candidate.relative_to(root).as_posix()
            candidate.relative_to(source_dir.resolve())
        except ValueError:
            continue
        if repo_rel in allowed and candidate.is_file():
            return candidate, source
    return None, source


def _placement_text(target: Path, block: str, label: str,
                    after_line: int | None = None) -> tuple[str, str, bool]:
    """Stage a figure after an exact 1-based source line, or at document tail."""
    before = target.read_text(encoding="utf-8")
    if f"\\label{{{label}}}" in before:
        return before, before, False
    lines = before.splitlines(keepends=True)
    if after_line is not None:
        if isinstance(after_line, bool) or not isinstance(after_line, int) or not 1 <= after_line <= len(lines):
            raise ValueError("after_line must be a 1-based line inside the selected source file")
        prefix, suffix = "".join(lines[:after_line]), "".join(lines[after_line:])
        separator = "" if not prefix or prefix.endswith("\n") else "\n"
        return before, prefix + separator + block + suffix, True
    # A caller without a reading-position line gets a safe document-tail default:
    # immediately before end{document}, or after the last source content in a fragment.
    end = re.search(r"\\end\s*\{document\}", before)
    position = end.start() if end else len(before)
    prefix, suffix = before[:position], before[position:]
    separator = "" if not prefix or prefix.endswith("\n") else "\n"
    return before, prefix + separator + block + suffix, True


def _placement_caption(project: str, spec: dict, root: Path, manuscript: Path, *,
                       source: dict | None = None,
                       traversal: dict | None = None) -> dict:
    """Compare the brief with authored TeX without rewriting either source."""
    from laplace.pipeline.caption_audit import _FLOAT_RE, _LABEL_RE
    from laplace.research.mathematical_records import _uncomment
    from laplace.manuscript.walk import _caption_of
    raw=spec.get('section_repo_file')
    if not raw and spec.get('section'):
        raw=(manuscript/spec['section']).relative_to(root).as_posix()
    if not raw:return {'status':'UNPLACED'}
    target,_source=_selected_target(project,raw,root,source=source,traversal=traversal)
    if target is None:return {'status':'UNRESOLVED','file':raw,'reason':'Recorded placement is not in the selected manuscript traversal'}
    text=target.read_text(encoding='utf-8');clean=_uncomment(text)
    floats=[match for match in _FLOAT_RE.finditer(clean)
            if 'fig:'+spec['id'] in _LABEL_RE.findall(match.group(3))]
    if len(floats)!=1:return {'status':'UNRESOLVED','file':raw,'reason':'Expected exactly one placed figure label'}
    match=floats[0];lo=clean.count('\n',0,match.start());hi=clean.count('\n',0,match.end())
    caption,start,end,_offset=_caption_of(text.splitlines(),lo,hi)
    if not start:return {'status':'UNRESOLVED','file':raw,'reason':'Placed caption has no unambiguous source boundary'}
    return {'status':'MATCHES' if caption.strip()==str(spec.get('caption') or '').strip() else 'DIFFERS',
            'file':raw,'line_start':start,'line_end':end,
            'next_read':{'operation':'source','payload':{'files':[raw],'line_start':start,'line_end':end}},
            'edit_operation':'apply_revision',
            'note':'The manuscript caption is authored source. Read this exact span, then use apply_revision for a requested change; visual_render only updates the brief/asset metadata.'}


def _manifest_placement(root: Path, manuscript: Path, asset_id: str, placed_at: str,
                        repo_file: str) -> dict | None:
    path = manuscript / "figure_manifest.json"
    if not path.is_file():
        return None
    with FileLock(str(path)+'.lock', timeout=15):
        before=path.read_bytes()
        raw=json.loads(before.decode('utf-8'))
        for row in raw.get("placed", []):
            if row.get("asset_id") == asset_id:
                row["placed_at"] = placed_at
                row["placed_at_scope"] = "manuscript"
                row["placed_repo_file"] = repo_file
        intended=(json.dumps(raw,ensure_ascii=False,indent=2)+"\n").encode('utf-8')
        temp=path.with_name(path.name+".pending");temp.write_bytes(intended);temp.replace(path)
        return file_receipt(root,path,before,intended)


def _review_rewrite(source_dir: Path, project: str, target: Path,
                    before: str, after: str, note: str, *, source_changes=None, expected_selection=None, repo_root=None) -> dict:
    if before == after:
        return {"ok": True, "reused": True}
    from laplace.manuscript import review_surface
    result = review_surface.adjudicate(source_dir, project, {
        "verb": "rewrite", "by": "author", "expected_selection": expected_selection, "file": target.relative_to(source_dir).as_posix(),
        "line_start": 1, "line_end": len(before.split("\n")), "before": before,
        "after": after, "note": note, "scope": "artefact"}, source_changes=source_changes, repo_root=repo_root)
    if result.get("error") or result.get("pending") or not result.get("ok"):
        raise ValueError(result.get("error") or "source rewrite was not applied")
    return result


def _ensure_graphicx(root: Path, source: dict, project: str, *, source_changes=None) -> dict:
    root_file = (root / source["root"]).resolve()
    text = root_file.read_text(encoding="utf-8")
    if re.search(r"\\(?:usepackage|RequirePackage)(?:\[[^]]*\])?\{[^}]*\bgraphicx\b[^}]*\}", text):
        return {"ok": True, "reused": True, "source_change":None}
    match = re.search(r"\\documentclass\s*(?:\[[^]]*\])?\s*\{[^}]+\}[^\n]*(?:\n|$)", text)
    if match is None:
        raise ValueError("The selected manuscript root has no document class for graphicx placement.")
    after = text[:match.end()] + "\\usepackage{graphicx}\n" + text[match.end():]
    source_dir = Path(source["manuscript_dir"])
    if not source_dir.is_absolute():
        source_dir = root / source_dir
    result=_review_rewrite(source_dir, project, root_file, text, after,
                           "Enabled graphic inclusion for generated visuals", source_changes=source_changes,
                           expected_selection=manuscript_source.selection_identity(source, project), repo_root=root)
    return {**result,"source_change":{"path":root_file,"before":text.encode('utf-8'),
                                       "intended_after":after.encode('utf-8')}}


def _manifest_render_receipt(root:Path,manuscript:Path,before:bytes|None,row:dict|None)->dict|None:
    if row is None:return None
    value=json.loads(before.decode('utf-8')) if before is not None else {'placed':[]}
    asset=row.get('asset_id')
    value['placed']=[old for old in value.get('placed',[]) if old.get('asset_id')!=asset]+[row]
    intended=(json.dumps(value,indent=2)+'\n').encode('utf-8')
    return file_receipt(root,manuscript/'figure_manifest.json',before,intended)


def _output_receipt(root:Path,path:Path,before:bytes|None,expected_hex:str)->dict:
    observed=path.read_bytes() if path.is_file() else None
    return {'scope':'repository','path':path.resolve().relative_to(root.resolve()).as_posix(),
            'before_sha256':mutation_digest(before),
            'after_sha256':'sha256:'+expected_hex,
            'observed_after_sha256':mutation_digest(observed)}


def _create_refusal(data: dict, spec: dict) -> dict:
    """What a refused visual_create needs to succeed in one corrected request.

    The owner validator reports every issue of the spec as it would be saved (the prior row of the same id
    merged with the caller's authored fields, exactly as upsert merges them), and the owner's own required
    fields and example for that kind come from visual_production.authoring_contract. Nothing is saved.
    """
    contract = vp.authoring_contract()
    transport = vp.update_transport_fields()
    read_fields, owner_fields = set(transport["read"]), set(transport["protected"])
    ident = spec.get("id") if isinstance(spec, dict) else None
    prior = next((row for row in data.get("specs", []) if isinstance(row, dict) and row.get("id") == ident), None) if isinstance(ident, str) else None
    merged = {**{key: value for key, value in (prior or {}).items() if key not in read_fields},
              **{key: value for key, value in (spec if isinstance(spec, dict) else {}).items() if key not in owner_fields | read_fields}}
    kind = merged.get("kind")
    variant = contract["variants"].get(kind) if isinstance(kind, str) else None
    issues = vp.render_readiness(merged)["issues"]
    out = {"saved": False, "issues": issues, "kinds": list(contract["variants"]),
           "help": {"operation": "help", "payload": {"operation": "visual_create"}},
           "note": ("Nothing was saved. Correct every listed field together, then send the spec again." if issues else
                    "Nothing was saved. The spec's fields are valid; the error above names what must change.")}
    if variant:
        out["required"] = list(variant["required"])
        out["example"] = contract["examples"][kind]
    return out


INDEX_LIMIT = 16
INDEX_ROW_KEYS = ("id", "kind", "title")


def _state_selection(query, body) -> dict:
    """The visuals read selectors from the HTTP query or the native JSON body (body wins).

    {} is the whole catalogue (unchanged); {view:index, offset, limit, cut} the bounded list;
    {id} or {ids:[..8]} the exact figures. A continuation names the cut it was paging.
    """
    values = {}
    for key in ("view", "id", "ids", "offset", "limit", "cut"):
        raw = _q(query, key, None)
        if raw not in (None, ""):
            values[key] = raw
    if body:
        try:
            given = json.loads(body)
        except (TypeError, ValueError):
            given = None
        if isinstance(given, dict):
            values.update({key: value for key, value in given.items() if key in ("view", "id", "ids", "offset", "limit", "cut") and value is not None})
    ids = values.get("ids")
    if isinstance(ids, str):
        ids = json.loads(ids) if ids.startswith("[") else [part.strip() for part in ids.split(",") if part.strip()]
    if ids is not None and (not isinstance(ids, list) or not all(isinstance(item, str) and item for item in ids) or not 1 <= len(ids) <= 8):
        raise ValueError("visuals ids must name one to eight exact spec ids")
    if values.get("id") is not None:
        if not isinstance(values["id"], str) or not values["id"]:
            raise ValueError("visuals id must be an exact spec id")
        ids = [values["id"], *(ids or [])]
    view = values.get("view") or ("detail" if ids else "index" if any(key in values for key in ("offset", "limit", "cut")) else "catalogue")
    if view not in {"catalogue", "index", "detail"}:
        raise ValueError("visuals view must be catalogue, index or detail")
    if view == "detail" and not ids:
        raise ValueError("visuals view:detail needs id or ids; view:index lists the exact ids")
    if view != "detail" and ids:
        raise ValueError("visuals id/ids select exact figures; drop them for view:" + view)
    page = {}
    for key, default, maximum in (("offset", 0, 100000), ("limit", INDEX_LIMIT, 200)):
        raw = values.get(key, default)
        try:
            number = int(raw)
        except (TypeError, ValueError):
            raise ValueError("visuals " + key + " must be an integer")
        if isinstance(raw, bool) or not (0 if key == "offset" else 1) <= number <= maximum:
            raise ValueError("visuals " + key + " is out of range")
        page[key] = number
    return {"view": view, "ids": list(dict.fromkeys(ids or [])), **page, "cut": values.get("cut")}


def _state_index(project, specs, selection, common):
    """The bounded list: one identity row per spec with its marks and one detail handle."""
    rows = []
    for spec in specs:
        caption = spec.get("placement_caption") or {}
        currentness = spec.get("currentness") or {}
        render = spec.get("render") or {}
        rows.append({**{key: spec.get(key) for key in INDEX_ROW_KEYS if spec.get(key) not in (None, "")},
                     "spec_revision": spec.get("spec_revision"),
                     "render_freshness": spec.get("render_freshness"),
                     "render_readiness": (spec.get("render_readiness") or {}).get("status"),
                     "currentness": {key: currentness.get(key) for key in ("status", "drawing_freshness", "evidence_binding_status", "presentation_status")},
                     "placement": {"status": caption.get("status"),
                                   **({"file": caption.get("file") or spec.get("section_repo_file") or spec.get("section")} if caption.get("file") or spec.get("section_repo_file") or spec.get("section") else {})},
                     "render": {key: render.get(key) for key in ("renderer", "asset") if render.get(key) is not None},
                     "detail_read": {"operation": "visuals", "payload": {"id": spec.get("id")}}})
    cut = "sha256:" + hashlib.sha256(json.dumps([[row.get("id"), row.get("spec_revision")] for row in rows], sort_keys=True).encode()).hexdigest()
    if selection.get("cut") and selection["cut"] != cut:
        return _j(409, {"error": "CHANGED_INPUT: the visuals catalogue changed since this index page was read; read view:index again before paging",
                        "read": {"operation": "visuals", "payload": {"view": "index"}}})
    offset, limit = selection["offset"], selection["limit"]
    items = rows[offset:offset + limit]
    page = {"items": items, "offset": offset, "limit": limit, "total": len(rows), "cut": cut,
            "omitted_before": min(offset, len(rows)), "omitted_after": max(0, len(rows) - offset - len(items))}
    if offset + len(items) < len(rows):
        page["next_read"] = {"operation": "visuals", "payload": {"view": "index", "offset": offset + len(items), "limit": limit, "cut": cut}}
    return _j(200, {"schema_version": "laplace.visuals-index/1", "project": project, "specs": page,
                    "authority": common["authority"], "renderers": common["renderers"],
                    "detail_http": {"method": "GET", "route": "/visuals/state", "query": {"project": project, "id": "<spec id>"}},
                    "scope": "Identity rows: spec_revision (the visual-spec guard), drawing/evidence/presentation marks, placement comparison status and render identity. The drawing source, render outputs, caption text and evidence bindings are on each row's detail_read."})


def handle(path, query, method, body, repo_root=None):
    # Serialize the whole owner transaction, including loading the spec and
    # publishing render outputs/manifest/source placement. The manuscript-spec
    # lock inside save/upsert still preserves concurrent nonvisual fields.
    if method == 'POST' and path in {'/visuals/create','/visuals/render','/visuals/place'}:
        from laplace.manuscript.manuscript_source import SourceLeaseError
        root = Path(repo_root).resolve() if repo_root else _r()
        try:
            payload=json.loads(body)
        except (TypeError,ValueError):
            return _j(400, {'error':'json'})
        if not isinstance(payload,dict):return _j(400, {'error':'body must be an object'})
        try:
            if path == '/visuals/place': identity_doors.admit_expected(payload, "visual_place", allow_empty=True)   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
        except identity_doors.IdentityRefused as refused: return _j(409, identity_doors.refuse({'error': str(refused)}, refused))
        project=str(payload.get('project') or _q(query,'project',''))
        manuscript=_m(project,root)
        if manuscript is None:return _j(404, {'error':'project'})
        source_changes = []
        try:
            with FileLock(str(manuscript/'.visual-mutation.lock'),timeout=120):
                result = _handle(path,query,method,body,repo_root=root,source_changes=source_changes)
            if source_changes:
                from laplace.manuscript.review_surface import mirror_source_changes
                status, content_type, encoded = result
                response = json.loads(encoded)
                try:
                    response['plan_sync'] = mirror_source_changes(project, source_changes, root,
                        expected_selection=(response.get('source_effect') or {}).get('selection_identity'))
                except Exception as exc:
                    response['plan_sync'] = {'status':'UNPROVED', 'reason':str(exc), 'source_effect_retained':True}
                result = _j(status, response)
            status, _content_type, encoded = result
            response = json.loads(encoded)
            if isinstance(response.get('source_effect'), dict):
                from laplace.manuscript import source_effects
                source_effects.finish(response, project, root, response['source_effect'], changes=source_changes,
                    heading_sync=response.get('plan_sync'))
                result = _j(status, response)
            return result
        except Timeout:
            return _j(409, {'error':'Another visual mutation is still running; read visuals and retry after it completes. This request made no changes.'})
        except SourceLeaseError as exc:
            return _j(409, {'error':str(exc), 'reason':'source-lease-unavailable'})
    return _handle(path,query,method,body,repo_root=repo_root)


def _handle(path, query, method, body, repo_root=None, *, source_changes=None):
    from laplace.manuscript import manuscript_source
    root = Path(repo_root).resolve() if repo_root else _r()
    project = str(_q(query, "project", "") or "")
    manuscript = _m(project, root)

    if path == "/visuals/state" and method == "GET":
        data = vp.load(manuscript) if manuscript else None
        if not data:
            return _j(404, {"error": "project"})
        try:
            selection = _state_selection(query, body)
        except ValueError as exc:
            return _j(422, {"error": str(exc)})
        catalogue = data.get("specs", [])
        # Bounded reads (2026-10-14): an exact figure (id/ids) enriches only the selected
        # specs; the index lists every spec's identities and currentness marks without its
        # drawing source, render outputs or caption comparison text (the whole catalogue of
        # 33 live figures measured 210 KB, 6.4 KB per spec).  The plain read is unchanged.
        if selection["view"] == "detail":
            wanted = selection["ids"]
            by_id = {item.get("id"): item for item in catalogue}
            missing = [ident for ident in wanted if ident not in by_id]
            if missing:
                return _j(404, {"error": "spec", "missing": missing,
                                "read": {"operation": "visuals", "payload": {"view": "index"}}})
            specs = [by_id[ident] for ident in wanted]
        else:
            specs = catalogue
        # Resolve the selected source edition once for this exact response.  A
        # foundations book can have dozens of placed figures; resolving and
        # traversing the same immutable selection for every caption dominated
        # this read path.  This is deliberately request-local so a subsequent
        # source-selection change can never observe stale data.
        source = traversal = None
        if any(spec.get("section_repo_file") or spec.get("section") for spec in specs):
            from laplace.manuscript import manuscript_source
            source = manuscript_source.resolve(project, repo_root=root)
            traversal = (manuscript_source.traversal(source["root"], repo_root=root)
                         if source.get("root") else {"files": []})
        base = _project_base(project, root, manuscript)
        research_records_snapshot = None
        if any(spec.get("result_ids") for spec in specs):
            from laplace.research import research_records
            research_records_snapshot = research_records._records(manuscript)
        for spec in specs:
            spec_revision = vp.digest(spec)
            observed = vp.provenance(
                manuscript, spec, project_root=base,
                research_records_snapshot=research_records_snapshot)
            readiness = vp.render_readiness(spec, observed)
            spec['spec_revision'] = spec_revision
            spec['render_readiness'] = readiness
            spec['placement_caption'] = _placement_caption(
                project, spec, root, manuscript, source=source, traversal=traversal)
            spec["input_scope"] = "manuscript" if base.resolve() == manuscript.resolve() else "project"
            spec["render_freshness"] = observed["status"]
            spec["currentness"] = {key: observed.get(key) for key in
                                   ("status", "drawing_freshness", "evidence_binding_status",
                                    "presentation_status", "metadata_changes",
                                    "input_files",
                                    "input_error", "evidence_gap", "research_binding",
                                    "basis_changes", "changed_dependencies",
                                    "output_error", "input_digest",
                                    "style_version", "output_digests")}
        common = {"authority": data.get("authority"),
                  "renderers": ["matplotlib", "graphviz-dot", "tikz-pdf", "supervised-run-artifact"],
                  "style": vp.house_style(manuscript, {}, project_root=root)}
        if selection["view"] == "index":
            return _state_index(project, specs, selection, common)
        if selection["view"] == "detail":
            return _j(200, {"specs": specs, "selection": {"view": "detail", "ids": selection["ids"]},
                            "catalogue_total": len(catalogue), **common,
                            "index_read": {"operation": "visuals", "payload": {"view": "index"}}})
        return _j(200, {"specs": specs, **common})

    if path in {"/visuals/create", "/visuals/render"} and method == "POST":
        try:
            payload = json.loads(body)
        except (TypeError, ValueError):
            return _j(400, {"error": "json"})
        project = str(payload.get("project") or project)
        manuscript = _m(project, root)
        if not manuscript:
            return _j(404, {"error": "project"})
        from laplace.manuscript import manuscript_source
        if manuscript_source.resolve(project, repo_root=root).get("read_only"):
            return _j(403, {"error": "source is read-only"})
        data = vp.load(manuscript)
        if path.endswith("create"):
            if not isinstance(payload.get('spec'),dict):
                return _j(422, {'error':'spec must be an object; read help for visual_create', **_create_refusal(data, {})})
            try:
                saved=vp.upsert(manuscript,payload['spec'],payload.get('expected_revision'),root)
            except vp.SpecRevisionConflict as exc:
                return _j(409, {'error':str(exc)})
            except ValueError as exc:
                return _j(422, {'error':str(exc), **_create_refusal(data, payload['spec'])})
            spec=saved['spec']
            owned=bundle(files=[saved['file_receipt']],objects=[{
                'owner':'visual-spec','id':spec['id'],
                'before_revision':saved['before_revision'],
                'after_revision':saved['spec_revision']}],views=['visuals','presentation'])
            return _j(201, {"spec": spec, "spec_revision":saved['spec_revision'], "readiness": "SPECIFIED",
                            "placement_caption":_placement_caption(project,spec,root,manuscript),
                            "owned_changes":owned})
        spec = next((item for item in data["specs"] if item.get("id") == payload.get("id")), None)
        if not spec:
            return _j(404, {"error": "spec"})
        try:
            before_spec=json.loads(json.dumps(spec))
            manifest=manuscript/'figure_manifest.json'
            manifest_before=manifest.read_bytes() if manifest.is_file() else None
            generated=manuscript/'figures'/'generated'
            generated_before={path.resolve():path.read_bytes() for path in generated.glob('**/*') if path.is_file()}
            rendered = vp.render(manuscript, spec, project_root=_project_base(project, root, manuscript))
            manifest_row=rendered.pop('_manifest_record',None)
            saved=vp.save(manuscript,{'specs':[spec]},mutation_root=root)
            files=[saved['file_receipt']]
            manifest_receipt=_manifest_render_receipt(root,manuscript,manifest_before,manifest_row)
            if manifest_receipt:files.append(manifest_receipt)
            for rel,expected in (rendered.get('output_digests') or {}).items():
                output=(manuscript/rel).resolve()
                if output.is_relative_to(manuscript.resolve()):
                    prior=generated_before.get(output)
                    if mutation_digest(prior)!='sha256:'+expected:
                        files.append(_output_receipt(root,output,prior,expected))
            owned=bundle(files=files,objects=[{
                'owner':'visual-render','id':spec['id'],
                'before_revision':vp.digest(before_spec),
                'after_revision':vp.digest(spec)}],views=['visuals','presentation'])
            return _j(200, {"render": rendered, "readiness": "GENERATED",
                            "placement_caption":_placement_caption(project,spec,root,manuscript),
                            "owned_changes":owned})
        except ValueError as exc:
            observed=vp.provenance(manuscript, spec, project_root=_project_base(project, root, manuscript))
            return _j(422, {"error": str(exc),"render_readiness":vp.render_readiness(spec,observed)})

    if path == "/visuals/place" and method == "POST":
        try:
            payload = json.loads(body)
        except (TypeError, ValueError):
            return _j(400, {"error": "json"})
        project = str(payload.get("project") or project)
        manuscript = _m(project, root)
        if not manuscript:
            return _j(404, {"error": "project"})
        target, source = _selected_target(project, payload.get("section") or payload.get("file"), root)
        if source.get("read_only"):
            return _j(403, {"error": "source is read-only"})
        if target is None:
            return _j(422, {"error": "generated spec and selected source section required"})
        source_dir = Path(source["manuscript_dir"])
        if not source_dir.is_absolute():
            source_dir = root / source_dir
        with FileLock(str(source_dir / ".visual-place.lock"), timeout=15):
            # Re-resolve both edition and target after acquiring the placement
            # lock. The walk's source_revision is the selected root digest; the
            # optional base_revision is the exact selected file digest.
            live_target, live_source = _selected_target(
                project, payload.get("section") or payload.get("file"), root)
            if live_target is None or live_source.get("read_only"):
                return _j(409, {"error": "selected source changed before placement"})
            if live_source.get("manuscript_dir") != source.get("manuscript_dir"):
                return _j(409, {"error": "selected manuscript edition changed before placement"})
            expected_source = payload.get("expected_source_revision")
            try:
                # Optional guard: HEAD skipped the compare when the field was absent or null and
                # refused on any other value, including the empty string.  `required` reproduces
                # that exactly, so the door's mind is unchanged.
                identity_doors.gate(
                    "visual_place", supplied=payload,
                    homes=[("selected-edition", project, live_source.get("revision"))],
                    required=["expected_source_revision"] if expected_source is not None else [],
                    said="selected manuscript revision conflict")
            except identity_doors.IdentityRefused as refused:
                return _j(409, identity_doors.refuse({"error": "selected manuscript revision conflict",
                    "source_revision": live_source.get("revision"),
                    "recovery": {
                        "read": {"operation": "source", "payload": {"files": [payload.get("section") or payload.get("file")]}},
                        # This refusal was the one place in the live code that already named the
                        # read a guard's value comes from -- the right idea in the wrong place
                        # (one refusal of one door) and with one wrong value.  Both fields now
                        # name their HOME as well as the read, and `base_revision` points at
                        # `sha256` -- the one name the `source-file` home keeps.  `raw_file_sha256`
                        # carries the same value and is still published, but only as a shim with an
                        # expiry (pipeline/authoring.py:522-532): a caller that reads THIS refusal
                        # is sent to the name that survives, and to the token beside it.
                        "guard_fields": {"expected_source_revision": "source.document.revision",
                                         "base_revision": "source.sources[target].sha256"},
                        "guard_homes": {"expected_source_revision": "selected-edition",
                                        "base_revision": "source-file"},
                        "identities": {"selected-edition": "source.identities",
                                       "source-file": "source.sources[target].identities"},
                        "note": "Reread the exact target and copy the token from that read's `identities` block. document.revision is the selected-edition home; top-level source_revision is the whole traversal, a different home one letter away. Nothing was placed."}}, refused))
            target, source = live_target, live_source
            data = vp.load(manuscript)
            spec = next((item for item in data.get("specs", [])
                         if item.get("id") == payload.get("id")), None)
            if not spec:
                return _j(422, {"error": "generated spec and selected source section required"})
            observed = vp.provenance(manuscript, spec,
                                     project_root=_project_base(project, root, manuscript))
            if (observed["status"] != "CURRENT" or
                    observed.get("evidence_binding_status") not in {"CURRENT", "THEORY_ONLY"}):
                return _j(409, {"error": "visual drawing or evidence basis needs review before placement",
                                "currentness": observed})
            before_spec=json.loads(json.dumps(spec))
            root_file=Path(source["root"])
            if not root_file.is_absolute():root_file=root/root_file
            root_file=root_file.resolve()
            from laplace.manuscript.manuscript_source import source_mutation, selection_mutation
            with selection_mutation(project, root), source_mutation([root_file, target]):
                checked_target, checked_source = _selected_target(project, payload.get("section") or payload.get("file"), root)
                if checked_target != target or checked_source.get("root") != source.get("root") or checked_source.get("manuscript_dir") != source.get("manuscript_dir") or checked_source.get("read_only"):
                    return _j(409, {"error": "selected source changed while waiting for its physical lease"})
                try:
                    identity_doors.gate("visual_place", supplied=payload,
                        homes=[("selected-edition", project, checked_source.get("revision"))],
                        required=["expected_source_revision"] if payload.get("expected_source_revision") is not None else [],
                        said="selected manuscript revision conflict")
                except identity_doors.IdentityRefused as refused:
                    return _j(409, identity_doors.refuse({"error": "selected manuscript revision conflict"}, refused))
                source_preimages={path:path.read_bytes() for path in {root_file,target} if path.is_file()}
                before_hash = hashlib.sha256(target.read_bytes()).hexdigest()
                expected = payload.get("base_revision")
                try:
                    # `base_revision` here is the TARGET FILE's bytes -- the `source-file` home, whose
                    # one published name is `sha256` -- and the sentence this door serves on a
                    # mismatch says "source revision conflict", which reads as the selected edition.
                    # The sentence is kept for replay; `refused` names the home.
                    identity_doors.gate(
                        "visual_place", supplied=payload,
                        homes=[("source-file",
                                "%s::%s" % (project, target.relative_to(root).as_posix()
                                            if target.is_relative_to(root) else target.name),
                                before_hash)],
                        required=["base_revision"] if expected is not None else [],
                        said="source revision conflict")
                except identity_doors.IdentityRefused as refused:
                    return _j(409, identity_doors.refuse(
                        {"error": "source revision conflict", "revision": before_hash}, refused))
                def failed_source_step(error, status=409, **extra):
                    response = {"ok":False, "error":str(error), **extra}
                    if source_changes:
                        from laplace.manuscript import source_effects
                        response['source_effect'] = source_effects.from_changes(root, project,
                            manuscript_source.selection_identity(source, project), source_changes,
                            complete=False, owner='visual-placement')
                        response['source_effect_retained'] = response['source_effect']['state'] in {'COMMITTED','PARTIAL'}
                        response['recovery'] = 'Inspect retained source and required placement work before another action; do not automatically repeat it.'
                    return _j(status, response)
                try:
                    package_receipt = _ensure_graphicx(root, source, project, source_changes=source_changes)
                except ValueError as exc:
                    return failed_source_step(exc)
                package_change=package_receipt.pop('source_change',None)
                label = "fig:" + spec["id"]
                asset_stem = (manuscript / "figures" / "generated" / spec["id"]).resolve()
                try:
                    asset_stem.relative_to(manuscript.resolve())
                except ValueError:
                    return failed_source_step("generated visual escapes the registered manuscript", 422)
                graphic_path = Path(os.path.relpath(asset_stem, source_dir.resolve())).as_posix()
                block = ("\\begin{figure}[t]\n\\centering\n"
                         "\\includegraphics[width=\\linewidth]{" + graphic_path + "}\n"
                         "\\caption{" + spec["caption"] + "}\n"
                         "\\label{" + label + "}\n\\end{figure}\n")
                try:
                    before, after, changed = _placement_text(target, block, label, payload.get("after_line"))
                except ValueError as exc:
                    return failed_source_step(exc, 422)
                if changed:
                    try:
                        _review_rewrite(source_dir, project, target, before, after,
                                        "Placed generated visual " + spec["id"], source_changes=source_changes,
                                        expected_selection=manuscript_source.selection_identity(source, project), repo_root=root)
                    except ValueError as exc:
                        return failed_source_step(exc, package_receipt=package_receipt)
                committed_target_digest = hashlib.sha256(target.read_bytes()).hexdigest()
                committed_root_digest = hashlib.sha256(root_file.read_bytes()).hexdigest()
                intended_sources={}
                if package_change:
                    intended_sources[package_change['path'].resolve()]=package_change['intended_after']
                if changed:intended_sources[target.resolve()]=after.encode('utf-8')
                if not intended_sources:
                    intended_sources[target.resolve()] = source_preimages[target.resolve()]
                source_receipts=[file_receipt(root,path,source_preimages.get(path),intended)
                                 for path,intended in intended_sources.items()]
                from laplace.manuscript import source_effects
                effect = source_effects.receipt(project, manuscript_source.selection_identity(source, project), source_receipts,
                    required=[{'owner':'visual-placement','status':'COMPLETE'}])
            repo_section = target.relative_to(root).as_posix()
            manuscript_section = target.relative_to(manuscript.resolve()).as_posix()
            spec["section"] = manuscript_section
            spec["section_scope"] = "manuscript"
            spec["section_repo_file"] = repo_section
            files=list(source_receipts);objects=[]
            failed_operation='visual-spec'
            try:
                saved=vp.save(manuscript,{'specs':[spec]},mutation_root=root)
                files.append(saved['file_receipt'])
                objects.append({'owner':'visual-placement','id':spec['id'],
                    'before_revision':vp.digest(before_spec),'after_revision':vp.digest(spec)})
                failed_operation='figure-manifest'
                manifest_receipt=_manifest_placement(root,manuscript,"figure:"+spec["id"],
                                                     manuscript_section,repo_section)
                if manifest_receipt:files.append(manifest_receipt)
            except Exception as exc:
                effect['complete'] = False
                effect['follow_through']['required'] = [{'owner':failed_operation,'status':'UNPROVED','reason':str(exc)}]
                return _j(409, {'ok':False,'source_effect':effect,'source_effect_retained':effect['state'] != 'UNCHANGED',
                    'metadata_tracking':'UNPROVED','failed_operation':failed_operation,
                    'error':'Visual source effects were retained, but metadata publication could not be confirmed: '+str(exc)[:400],
                    'repo_file':repo_section,'revision':committed_target_digest,
                    'source_revision':committed_root_digest,'package_receipt':package_receipt,
                    'owned_changes':bundle(files=files,objects=objects,views=['visuals','presentation','manuscript']),
                    'recovery':{'read':{'operation':'visuals','payload':{}}, 'asset_id':spec['id'],
                                'source':{'operation':'source','payload':{'files':[repo_section]}},
                                'note':'Inspect the current source and tracking before further action. Do not repeat the retained source effect.'}})
            owned=bundle(files=files,objects=objects,views=['visuals','presentation','manuscript'])
            return _j(200, {"ok": True, "placed_at": manuscript_section,
                            "placed_at_scope": "manuscript", "repo_file": repo_section,
                            "reused": not changed,
                            "revision": committed_target_digest,
                            "source_revision": committed_root_digest,
                            "package_receipt": package_receipt,
                            "owned_changes":owned, "source_effect":effect})

    if path == "/visuals/asset" and method == "GET" and manuscript:
        data = vp.load(manuscript)
        ident = _q(query, "id")
        fmt = str(_q(query, "format", "svg"))
        spec = next((item for item in data["specs"] if item.get("id") == ident), None)
        if spec and fmt in {"svg", "pdf", "png"}:
            observed = vp.provenance(manuscript, spec,
                                     project_root=_project_base(project, root, manuscript))
            inspect = _q(query,"inspect") == "1"
            if (observed["status"] != "CURRENT" or
                    observed.get("evidence_binding_status") not in {"CURRENT", "THEORY_ONLY"}) and not inspect:
                return _j(409, {"error": "visual drawing or evidence basis is not current",
                                "currentness": observed})
            suffix = "." + fmt
            outputs=(spec.get('render') or {}).get('outputs',[]) if inspect else observed["outputs"]
            rel = next((item for item in outputs if isinstance(item,str) and item.endswith(suffix)), None)
            target = (manuscript / rel).resolve() if rel else None
            if target and target.is_file() and target.is_relative_to(manuscript.resolve()):
                return 200, {"svg": "image/svg+xml", "pdf": "application/pdf",
                             "png": "image/png"}[fmt], target.read_bytes()
        return _j(404, {"error": "asset"})
    return None
