"""Source-backed move/delete for whole typed manuscript blocks."""
from __future__ import annotations
import hashlib
import json
from contextvars import ContextVar
import re
from pathlib import Path
from typing import Mapping
from filelock import FileLock

_MUTATION = ContextVar("manuscript_block_mutation", default=None)

_ATOMIC = frozenset({"figure", "custom", "table", "equation", "theorem", "list", "raw"})

def undo_input_contract() -> dict:
    """Pure current Undo shape, shared by native admission and this owner."""
    from laplace.core.identity_doors import EXPECTED_FIELD
    location = {"type":"object", "required":["section", "section_scope", "section_repo_file"],
        "properties":{key:{"type":["string", "null"]}
                      for key in ("section", "section_scope", "section_repo_file")},
        "additionalProperties":False}
    edit = {"type":"object", "required":["file", "line_start", "line_end", "before", "after"],
        "properties":{"file":{"type":"string", "minLength":1},
            "line_start":{"type":"integer", "minimum":1},
            "line_end":{"type":"integer", "minimum":1},
            "before":{"type":"string"}, "after":{"type":"string"}},
        "additionalProperties":False}
    placement = {"type":["object", "null"], "required":["id", "before", "after"],
        "properties":{"id":{"type":"string", "minLength":1},
            "before":location, "after":location}, "additionalProperties":False,
        "description":"Copy the explicit returned placement, including null. Missing legacy metadata requires reinspection of the recorded structural Undo."}
    return {"type":"object", "required":["operation", "edits", "placement"],
        "properties":{"operation":{"const":"undo"},
            "edits":{"type":"array", "minItems":1, "items":edit},
            "placement":placement, "project":{"type":"string", "minLength":1},
            "expected":{**EXPECTED_FIELD, "items":dict(EXPECTED_FIELD["items"])}},
        "additionalProperties":False}


def _validate_undo(project: str, payload: Mapping) -> None:
    from jsonschema import Draft202012Validator
    if "placement" not in payload:
        raise ValueError("Undo placement metadata is unavailable; reinspect the recorded structural Undo before retrying")
    error = next(Draft202012Validator(undo_input_contract()).iter_errors(payload), None)
    if error is not None:
        coordinate = ".".join(map(str, error.absolute_path)) or "payload"
        raise ValueError("Undo " + coordinate + ": " + error.message +
                         "; reinspect the recorded structural Undo before retrying")
    if payload.get("project", project) != project:
        raise ValueError("Undo project conflicts with the selected project")


def _path(root: Path, project: str, file: str):
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("read_only"):
        raise ValueError("selected manuscript source is read-only")
    manuscript = (root / str(source.get("manuscript_dir") or "")).resolve()
    try:
        candidate = manuscript_source.source_path(root, manuscript, file)
    except ValueError as exc:
        raise ValueError("block file is not in the selected manuscript source") from exc
    traversal = manuscript_source.traversal(source.get("root"), repo_root=root) if source.get("root") else {}
    if not candidate.is_file() or candidate.relative_to(root).as_posix() not in set(traversal.get("files") or []):
        raise ValueError("block file is not in the selected manuscript source")
    return source, manuscript, candidate

def _block(root: Path, project: str, value: Mapping, allowed=_ATOMIC):
    source, manuscript, path = _path(root, project, str(value.get("file") or ""))
    raw = path.read_text(encoding="utf-8"); lines = raw.split("\n")
    lo, hi = value.get("line_start"), value.get("line_end")
    if not isinstance(lo, int) or not isinstance(hi, int) or not 1 <= lo <= hi <= len(lines):
        raise ValueError("block line_start and line_end must be a valid inclusive source span")
    before = value.get("before")
    if not isinstance(before, str) or "\n".join(lines[lo-1:hi]) != before:
        raise ValueError("block source changed; refresh before moving or deleting it")
    from laplace.manuscript import walk, manuscript_figure_preview
    root_tex = (root / str(source.get("root") or "")).resolve()
    envs = manuscript_figure_preview.declared_environments(root_tex, root)
    rendered_source = walk.root_content(raw)[0] if path == root_tex else raw
    blocks = walk.blocks_for(rendered_source, file_rel=path.relative_to(manuscript).as_posix(),
                             repo_file=path.relative_to(root).as_posix(), md=manuscript,
                             corpus=project, dir_param="", para_spans=[], known_macros=walk.preamble_macros(root_tex),
                             declared_envs=envs)
    block = next((row for row in blocks if row.get("src", {}).get("line_start") == lo
                  and row.get("src", {}).get("line_end") == hi and row.get("tex") == before), None)
    if block is None or block.get("kind") not in allowed:
        raise ValueError("select one whole current paragraph" if allowed == frozenset({"para"}) else "select one whole atomic figure, custom environment, table, equation, theorem, list, or raw source block")
    expected = str(value.get("expected_source_digest") or "").removeprefix("sha256:")
    digest = hashlib.sha256(raw.encode()).hexdigest()
    if not expected or expected != digest:
        raise ValueError("origin expected_source_digest is required and must be current")
    return source, manuscript, path, raw, block

def _rewrite(manuscript: Path, project: str, path: Path, before: str, after: str, note: str):
    from laplace.manuscript import review_surface
    result = review_surface.adjudicate(manuscript, project, {"verb":"rewrite", "by":"author",
        "expected_selection":(_MUTATION.get() or {}).get("selection_identity"),
        "file":path.relative_to(manuscript).as_posix(), "line_start":1,
        "line_end":len(before.split("\n")), "before":before, "after":after,
        "scope":"artefact", "note":note}, source_changes=(_MUTATION.get() or {}).get("heading_changes"), repo_root=(_MUTATION.get() or {}).get("root"))
    if not result.get("ok") or result.get("pending") or result.get("error"):
        raise ValueError(result.get("error") or "source rewrite did not complete")
    context = _MUTATION.get()
    if context is not None:
        context["files"].append((path, before.encode("utf-8"), after.encode("utf-8")))
        record = result.get("record") or {}
        if record.get("id"): context["corrections"].append(record["id"])
    return result

def _visual_placement(root: Path, manuscript: Path, label: str, file: str | None):
    """Only change the named generated-visual placement; never touch its asset/result."""
    if not label.startswith("fig:"):
        return None
    from laplace.pipeline import visual_production as vp
    data = vp.load(manuscript); ident = label.removeprefix("fig:")
    spec = next((row for row in data.get("specs", []) if row.get("id") == ident), None)
    if spec is None:
        return None
    before = {key: spec.get(key) for key in ("section", "section_scope", "section_repo_file")}
    spec["section"] = file
    spec["section_scope"] = "manuscript" if file else None
    spec["section_repo_file"] = ((manuscript / file).resolve().relative_to(root).as_posix()
                                  if file else None)
    written = vp.save(manuscript, data, mutation_root=root)
    context = _MUTATION.get()
    if context is not None and isinstance(written, dict):
        context["owned"].extend([written["file_receipt"]] if written.get("file_receipt") else [])
    return {"id": ident, "before": before, "after": {key: spec.get(key) for key in before}}

def _restore_placement(manuscript: Path, receipt):
    if not isinstance(receipt, Mapping) or not receipt.get("id"): return
    from laplace.pipeline import visual_production as vp
    data=vp.load(manuscript); spec=next((row for row in data.get("specs",[]) if row.get("id")==receipt["id"]),None)
    if spec is not None:
        expected=receipt.get("after") or {}
        if any(spec.get(key) != value for key,value in expected.items()):
            raise ValueError("visual placement changed since this operation; undo is refused")
        spec.update(receipt.get("before") or {}); context = _MUTATION.get()
        written = vp.save(manuscript,data, mutation_root=context["root"] if context else None)
        context = _MUTATION.get()
        if context is not None and isinstance(written, dict):
            context["owned"].extend([written["file_receipt"]] if written.get("file_receipt") else [])

def _check_placement(manuscript: Path, receipt):
    if not isinstance(receipt, Mapping) or not receipt.get("id"): return
    from laplace.pipeline import visual_production as vp
    data=vp.load(manuscript); spec=next((row for row in data.get("specs",[]) if row.get("id")==receipt["id"]),None)
    expected=receipt.get("after") or {}
    if spec is None or any(spec.get(key) != value for key,value in expected.items()):
        raise ValueError("visual placement changed since this operation; undo is refused")

def split_inline_paragraph(text: str, offset: int) -> tuple[str, str]:
    """Split at an exact source boundary, carrying known inline style scopes."""
    if not isinstance(offset, int) or not 0 < offset < len(text):
        raise ValueError("paragraph offset must be inside its exact source text")
    styles = {"emph", "textbf", "textit", "texttt", "textrm", "textsf", "textsl", "textsc", "textnormal", "underline"}
    scopes = []; math = False; cursor = 0
    while cursor < offset:
        char = text[cursor]
        if char == "%":
            end = text.find("\n", cursor)
            if end < 0 or end >= offset:
                raise ValueError("choose a caret in the paragraph text, outside a TeX comment")
            cursor = end + 1; continue
        if char == "\\":
            command = re.match(r"\\([A-Za-z]+)\*?", text[cursor:])
            if command:
                end = cursor + len(command.group(0)); brace = end
                while brace < len(text) and text[brace].isspace(): brace += 1
                if command.group(1) in styles and brace < offset and text[brace] == "{":
                    scopes.append(text[cursor:brace+1]); cursor = brace+1; continue
                cursor = end; continue
            cursor += 2; continue
        if char == "$": math = not math
        elif char == "{": scopes.append(None)
        elif char == "}":
            if not scopes: raise ValueError("paragraph source has an unmatched closing brace")
            scopes.pop()
        cursor += 1
    if math or any(scope is None for scope in scopes):
        raise ValueError("place the caret outside mathematics or an unsupported grouped command")
    return text[:offset] + "}" * len(scopes), "".join(scopes) + text[offset:]


def _change(root: Path | str, project: str, payload: Mapping):
    root = Path(root).resolve(); operation = str(payload.get("operation") or "")
    if operation == "undo":
        edits = payload.get("edits")
        if not isinstance(edits, list) or not edits: raise ValueError("undo requires the returned edits array")
        prepared=[]
        for edit in reversed(edits):
            _source, manuscript, path = _path(root, project, str(edit.get("file") or ""))
            current=path.read_text(encoding="utf-8")
            # THE SAME COMPARISON, WITH ITS CURE (WRITING-CONSOLIDATION-W1). This door
            # refused with the current bytes already in `current` and served neither the
            # identity nor the text, so an editor Undo that lost the race had nothing to
            # retry with and the author's inverse was simply gone. The comparison is
            # unchanged (the texts are equal exactly when the tokens are) and the
            # SENTENCE is unchanged, so differential replay sees the same refusal class,
            # the same house and the same words; what is added is `refused.needed` with
            # the `source-file` token and the current bytes under the one carrier name
            # (`before_content`), which makes the retry mechanical.
            from laplace.core import identity_doors
            identity_doors.gate(
                # `{**payload, **edit}`: the request's own keys AND this edit's, so a
                # token sent ONCE at the top of the body is reachable here --- one undo is
                # one act over however many edits it takes --- and handing the gate the
                # edit alone would make that field unreachable at this site, which is the
                # defect `tests/test_identity_doors.py` fences. WHAT IS TRUE TODAY: the
                # door ACCEPTS `expected` and NO CALLER IN THIS TREE SENDS ONE. The walk's
                # object undo posts `{project, operation, edits, placement}`
                # (`static_shared/walk.mjs:3079`) and the insert/move gesture the same, so
                # what actually gates both is the `after` BYTES guard this call already
                # requires. That is deliberate rather than pending: a mechanical
                # `{**request, **needed}` retry here would replace the undo's own `after`
                # with the file's CURRENT bytes and undo nothing, so the cure this refusal
                # serves is for a human reader --- `walk.mjs:3103` shows its text --- and
                # the token is for a caller that reads the file's identity first.
                "block_change undo", supplied={**payload, **edit},
                homes=[("source-file", "%s::%s" % (project, str(edit.get("file") or "")),
                        current.encode("utf-8"))],
                required=["after"], bytes_guards=["after"],
                serves={"before_content": current},
                said="object changed since this operation; undo is refused")
            prepared.append((manuscript,path,current,edit))
        _check_placement(manuscript, payload.get("placement"))
        applied=[]
        try:
            for manuscript,path,current,edit in prepared:
                _rewrite(manuscript, project, path, current, str(edit.get("before")), "Undo object source change")
                applied.append((manuscript,path,edit))
            _restore_placement(manuscript, payload.get("placement"))
        except Exception:
            for manuscript,path,edit in reversed(applied):
                if path.read_text(encoding="utf-8") == edit["before"]:
                    _rewrite(manuscript,project,path,edit["before"],edit["after"],"Rollback incomplete object undo")
            raise
        return {"ok":True,"operation":"undo","edits":[{**edit,"before":edit["after"],"after":edit["before"]} for _m,_p,edit in applied],
                "placement":({**payload["placement"],"before":payload["placement"]["after"],"after":payload["placement"]["before"]} if payload.get("placement") else None)}
    if operation in {"insert", "insert-at-caret"}:
        clip=payload.get("clip"); destination=payload.get("destination")
        if not isinstance(clip,Mapping) or not isinstance(clip.get("before"),str) or not isinstance(destination,Mapping): raise ValueError("insert requires a returned clip and destination")
        _source,manuscript,dest=_path(root,project,str(destination.get("file") or "")); raw=dest.read_text(encoding="utf-8"); lines=raw.split("\n"); line=destination.get("line")
        expected=str(destination.get("expected_source_digest") or "").removeprefix("sha256:")
        if not isinstance(line,int) or not 0<=line<=len(lines) or not expected or expected!=hashlib.sha256(raw.encode()).hexdigest(): raise ValueError("destination expected_source_digest is required and must be current")
        if line and (not isinstance(destination.get("before"),str) or lines[line-1]!=destination["before"]): raise ValueError("destination.before does not match its insertion context")
        labels=re.findall(r"\\label\s*\{([^}]+)\}",clip["before"]); label=str(clip.get("label") or "")
        if labels:
            from laplace.manuscript import manuscript_source
            root_tex=(root/str(_source.get("root") or "")).resolve(); existing="\n".join(str(row.get("text") or "") for row in manuscript_source.traversal(root_tex,repo_root=root).get("sources") or [])
            duplicate=next((value for value in labels if value in set(re.findall(r"\\label\s*\{([^}]+)\}", existing))),None)
            if duplicate: raise ValueError("insert would duplicate an existing object label: "+duplicate)
        anchor = {"file":dest.relative_to(manuscript).as_posix(),"line_start":line+1,"before":clip["before"]}
        if operation == "insert-at-caret":
            paragraph = destination.get("paragraph")
            if not isinstance(paragraph, Mapping): raise ValueError("insert-at-caret requires an exact paragraph and source offset")
            _block(root, project, {**paragraph, "file":destination["file"],
                "expected_source_digest":destination["expected_source_digest"]}, allowed=frozenset({"para"}))
            left, right = split_inline_paragraph(paragraph["before"], paragraph.get("offset"))
            lo, hi = paragraph["line_start"], paragraph["line_end"]
            replacement = left + "\n\n" + clip["before"] + "\n\n" + right
            after = "\n".join(lines[:lo-1] + replacement.split("\n") + lines[hi:])
            anchor["line_start"] = lo + left.count("\n") + 2
        else:
            if destination.get("paragraph") is not None: raise ValueError("use insert-at-caret for a paragraph split")
            after="\n".join(lines[:line]+clip["before"].split("\n")+lines[line:])
        edit={"file":dest.relative_to(manuscript).as_posix(),"line_start":1,"line_end":len(lines),"before":raw,"after":after}
        try:
            _rewrite(manuscript,project,dest,raw,after,"Insert pasted object block")
            placement=_visual_placement(root,manuscript,label,edit["file"])
        except Exception:
            if dest.read_text(encoding="utf-8") == after:
                _rewrite(manuscript,project,dest,after,raw,"Rollback incomplete object insert")
            raise
        return {"ok":True,"operation":operation,"anchor":anchor,"block":{"kind":clip.get("kind"),"label":label},"edits":[edit],"placement":placement,"undo":{"operation":"undo","edits":[edit],"placement":placement}}
    if operation not in {"delete","move"}: raise ValueError("operation must be delete, move, insert, insert-at-caret, or undo")
    block = payload.get("block")
    if not isinstance(block, Mapping): raise ValueError("block is required")
    source, manuscript, origin, raw, typed = _block(root, project, block)
    lines=raw.split("\n"); lo,hi=block["line_start"],block["line_end"]
    origin_after="\n".join(lines[:lo-1]+lines[hi:]); edits=[]
    destination=None
    if operation == "move":
        destination=payload.get("destination")
        if not isinstance(destination, Mapping): raise ValueError("move requires destination")
        _s,_m,dest=_path(root,project,str(destination.get("file") or "")); dest_raw=dest.read_text(encoding="utf-8")
        line=destination.get("line")
        if not isinstance(line,int) or not 0 <= line <= len(dest_raw.split("\n")): raise ValueError("destination.line must be a 0-based insertion boundary")
        expected=str(destination.get("expected_source_digest") or "").removeprefix("sha256:")
        if not expected or expected != hashlib.sha256(dest_raw.encode()).hexdigest(): raise ValueError("destination expected_source_digest is required and must be current")
        context=destination.get("before")
        if line and (not isinstance(context,str) or dest_raw.split("\n")[line-1] != context): raise ValueError("destination.before does not match its insertion context")
        if dest == origin:
            if lo <= line <= hi: raise ValueError("destination cannot be inside the moved block")
            at=line-(hi-lo+1) if line > hi else line
            reduced=lines[:lo-1]+lines[hi:]
            after="\n".join(reduced[:at]+block["before"].split("\n")+reduced[at:])
            edits=[{"file":origin.relative_to(manuscript).as_posix(),"line_start":1,"line_end":len(lines),"before":raw,"after":after}]
        else:
            dest_lines=dest_raw.split("\n"); dest_after="\n".join(dest_lines[:line]+block["before"].split("\n")+dest_lines[line:])
            edits=[{"file":dest.relative_to(manuscript).as_posix(),"line_start":1,"line_end":len(dest_lines),"before":dest_raw,"after":dest_after}, {"file":origin.relative_to(manuscript).as_posix(),"line_start":1,"line_end":len(lines),"before":raw,"after":origin_after}]
    else:
        edits=[{"file":origin.relative_to(manuscript).as_posix(),"line_start":1,"line_end":len(lines),"before":raw,"after":origin_after}]
    applied=[]
    placement=None
    try:
        for edit in edits:
            _s,_m,path=_path(root,project,edit["file"]); current=path.read_text(encoding="utf-8")
            if current != edit["before"]: raise ValueError("source changed during object operation")
            _rewrite(manuscript,project,path,current,edit["after"],f"{operation.title()} {typed['kind']} block")
            applied.append(edit)
        placement=_visual_placement(root, manuscript, str(typed.get("label") or ""),
                                    edits[0]["file"] if operation=="move" else None)
    except Exception:
        for edit in reversed(applied):
            _s,_m,path=_path(root,project,edit["file"])
            if path.read_text(encoding="utf-8") == edit["after"]:
                _rewrite(manuscript,project,path,edit["after"],edit["before"],"Rollback incomplete object operation")
        raise
    return {"ok":True,"operation":operation,"block":{"kind":typed["kind"],"label":typed.get("label")},
            "edits":edits,"placement":placement,"clip":{"before":block["before"],"kind":typed["kind"],"label":typed.get("label")},"undo":{"operation":"undo","edits":edits,"placement":placement}}


def change(root: Path | str, project: str, payload: Mapping):
    """Existing source writer plus compact recovery references; source stays in its correction rows."""
    from laplace.core import identity_doors
    from laplace.manuscript import manuscript_source, review_surface
    from laplace.core.records import journal
    from laplace.core.receipts import file_receipt, bundle
    identity_doors.admit_expected(payload, "block_change")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    root = Path(root).resolve()
    if payload.get("operation") == "undo":
        _validate_undo(project, payload)
    context = {"root":root, "files": [], "corrections": [], "owned": [], "heading_changes": []}
    token = _MUTATION.set(context)
    try:
        with FileLock(str(root / "contract" / ".block-change.lock"), timeout=30):
            selected = manuscript_source.resolve(project, repo_root=root)
            if not selected.get("root"):
                raise ValueError("no selected manuscript source")
            def namespace():
                return {(root / name).resolve() for name in manuscript_source.traversal(selected["root"], repo_root=root).get("files", [])}
            selected_paths = namespace()
            paths = set(selected_paths)
            undo_edits = payload.get("edits")
            declared = [payload.get("block"), payload.get("destination"), *(undo_edits if isinstance(undo_edits, list) else [])]
            for item in declared:
                if isinstance(item, Mapping) and item.get("file"):
                    paths.add(_path(root, project, str(item["file"]))[2])
            context['selection_identity'] = manuscript_source.selection_identity(selected, project)
            with manuscript_source.selection_mutation(project, root), manuscript_source.source_mutation(paths):
                current = manuscript_source.resolve(project, repo_root=root)
                if any(current.get(key) != selected.get(key) for key in ("root", "manuscript_dir", "edition", "read_only")) or namespace() != selected_paths:
                    raise ValueError("selected source namespace changed; refresh the block operation")
                try:
                    result = _change(root, project, payload)
                    files = [file_receipt(root, path, before, after) for path, before, after in context["files"]]
                    result["owned_changes"] = bundle(files=files + context["owned"], views=["manuscript", "visuals"])
                    from laplace.manuscript import source_effects
                    if files:
                        result['source_effect'] = source_effects.receipt(project, context['selection_identity'], files,
                            required=[{'owner':'block-operation','status':'COMPLETE'}])
                    if context["corrections"]:
                        ident = context["corrections"][0]
                        journal.bank_row("contract/talk.jsonl", {"record":"manuscript-block-change", "id":ident,
                            "project":project, "operation":result["operation"], "correction_ids":context["corrections"],
                            "placement":result.get("placement")}, root=root)
                        result["undo_ref"] = {"kind":"block", "id":ident, "project":project}
                        result["corrections"] = [{"id":correction_id,"file":edit["file"]}
                            for correction_id,edit in zip(context["corrections"],result.get("edits",[]))]
                    result.setdefault("undo", {"operation":"undo", "edits":result.get("edits", []), "placement":result.get("placement")})
                except Exception as exc:
                    if context['files']:
                        from laplace.manuscript import source_effects
                        effect = source_effects.from_changes(root, project, context['selection_identity'],
                            context['files'], complete=False, owner='block-operation')
                        source_effects.finish({'source_effect':effect}, project, root, effect,
                            heading_sync={'status':'UNPROVED','reason':'Required block operation did not complete; inspect its source and metadata.'})
                        raise source_effects.SourceEffectFailure(exc, effect) from exc
                    raise
        try:
            result["plan_sync"] = review_surface.mirror_source_changes(project, context["heading_changes"], root, expected_selection=context["selection_identity"])
        except (OSError, ValueError, manuscript_source.SourceLeaseError) as exc:
            result["plan_sync"] = {"status":"UNPROVED", "reason":str(exc)}
        if isinstance(result.get('source_effect'), dict):
            source_effects.finish(result, project, root, result['source_effect'],
                changes=context['heading_changes'], heading_sync=result['plan_sync'])
        return result
    except manuscript_source.SourceLeaseError as exc:
        raise ValueError(str(exc)) from exc
    finally:
        _MUTATION.reset(token)


def undo_record(root: Path | str, project: str, ident: str) -> dict:
    """Lazily join the completed transaction to the exact existing correction rows."""
    from laplace.manuscript import manuscript_source
    root = Path(root).resolve()
    path = root / "contract/talk.jsonl"
    rows = []
    for line in path.read_text().splitlines() if path.is_file() else []:
        try: rows.append(json.loads(line))
        except ValueError: continue
    row = next((row for row in reversed(rows) if row.get("record")=="manuscript-block-change"
                and row.get("id")==ident and row.get("project")==project), None)
    if row is None: raise ValueError("This project has no completed object change with that receipt")
    selected = manuscript_source.resolve(project, repo_root=root)
    manuscript = (root / str(selected.get("manuscript_dir") or "")).resolve()
    ledger = manuscript / "feedback/feedback.jsonl"
    corrections = {}
    for line in ledger.read_text().splitlines() if ledger.is_file() else []:
        try:
            value=json.loads(line);corrections[value.get("id")]=value
        except ValueError: continue
    edits=[]
    for correction_id in row["correction_ids"]:
        correction=corrections.get(correction_id) or {}; anchor=correction.get("anchor") or {}
        if not anchor.get("applied") or not isinstance(anchor.get("before"),str) or not isinstance(anchor.get("after"),str):
            raise ValueError("An exact source correction required by this object change is unavailable")
        file=anchor.get("file"); _path(root, project, file)
        edits.append({"file":file,"line_start":1,"line_end":len(anchor["before"].split("\n")),"before":anchor["before"],"after":anchor["after"]})
    return {"kind":"block","id":ident,"project":project,
            "undo":{"operation":"undo","edits":edits,"placement":row.get("placement")}}
