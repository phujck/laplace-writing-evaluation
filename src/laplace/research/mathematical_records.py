"""Scientific content over canonical concept metadata and exact local sources.

This is a read projection, not another claim ledger. Authored fields live in
projection.mathematics; qualification never certifies mathematical truth.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

KINDS = {"theorem", "lemma", "proposition", "corollary", "claim", "result",
         "definition", "def", "postulate", "assumption", "derivation-step"}
PROOF_KINDS = KINDS - {"definition", "def", "postulate", "assumption"}
ENVIRONMENTS = {"theorem", "lemma", "proposition", "corollary", "claim",
                "definition", "postulate", "assumption", "result", "axiom"}
_ENV = re.compile(r"\\(begin|end)\s*\{([^{}]+)\}")


def source_locator_schema() -> dict:
    """A text source location; fingerprints are fields, never TeX labels."""
    return {"type":"object","additionalProperties":False,"required":["path"],"properties":{
        "repository":{"type":"string","minLength":1},"path":{"type":"string","minLength":1},
        "label":{"type":"string","minLength":1},"line_start":{"type":"integer","minimum":1},
        "line_end":{"type":"integer","minimum":1},
        "sha256":{"type":"string","pattern":r"^(?:sha256:)?[0-9a-fA-F]{64}$"}}}


def source_replacement_schema() -> dict:
    locator=source_locator_schema()
    locator["oneOf"]=[{"required":["label"],"not":{"anyOf":[{"required":["line_start"]},{"required":["line_end"]}]}},
                      {"required":["line_start","line_end"],"not":{"required":["label"]}}]
    return {"type":"array","maxItems":20,"items":locator}


def bibliographic_reference_schema() -> dict:
    """The provenance object emitted by literature.bind, not a TeX selector."""
    return {"type":"object","additionalProperties":False,"required":["reference_key"],"properties":{
        "reference_key":{"type":"string","minLength":1},"citekey":{"type":"string","minLength":1},
        "path":{"type":"string","minLength":1},"locator":{"type":"string","minLength":1},
        "sha256":{"type":"string","pattern":r"^(?:sha256:)?[0-9a-fA-F]{64}$"}}}


def _invalid_sha256(path: str, value: str) -> str:
    pin = value.removeprefix('sha256:')
    return f"{path} must be a SHA-256 digest of 64 hexadecimal characters, with optional sha256: prefix; proposed pin length is {len(pin)}. Reuse the returned source.sha256 programmatically."


def validate_bibliographic_reference(project: str, ref: dict, root: Path):
    rules=bibliographic_reference_schema()['properties']
    unknown=set(ref)-set(rules)
    if unknown:raise ValueError('bibliographic source reference has unknown fields: '+', '.join(sorted(unknown)))
    for key,value in ref.items():
        if not isinstance(value,str) or not value.strip():raise ValueError('bibliographic source reference '+key+' must be nonempty text')
    if ref.get('sha256') and not re.fullmatch(r'(?:sha256:)?[0-9a-fA-F]{64}',ref['sha256']):raise ValueError(_invalid_sha256('sha256',ref['sha256']))
    if not ref.get('path'):
        if ref.get('sha256'):raise ValueError('A bibliographic source SHA-256 requires its registered source path')
        return
    from laplace.research import literature, references_surface
    from laplace.core.identity import revision_matches
    provider,item=literature.resolve_item(project,ref['reference_key'],root)
    if item is None:raise ValueError('Bibliographic source path requires an existing reference identity; read reference_source first')
    paths=[]
    if provider=='canonical':
        for index in range(len(item.get('source_refs') or [])):
            try:path,_=literature.canonical_source_path(project,item,root,index);paths.append(path.resolve())
            except (OSError,ValueError):continue
        # Acquisition is registered by the source owner, independently of the
        # original canonical alternatives. A failed default must not erase them.
        try:
            info,path=literature.source_info(project,ref['reference_key'],root)
            if path and info.get('currentness')=='CURRENT':paths.append(path.resolve())
        except (OSError,ValueError):
            pass
    else:
        _info,path=literature.source_info(project,ref['reference_key'],root)
        if path:paths.append(path.resolve())
    requested=Path(ref['path']);requested=(requested if requested.is_absolute() else root/requested).resolve()
    if requested not in paths:raise ValueError('Bibliographic source path must match a registered source location; read reference_source/reference_text')
    if ref.get('sha256') and not revision_matches(ref['sha256'],references_surface._sha256_file(requested)):
        raise ValueError('Bibliographic source SHA-256 changed; read reference_text again')
    if ref.get('citekey') and item.get('citation_key') and ref['citekey']!=item['citation_key']:
        raise ValueError('Bibliographic citekey does not match its registered reference identity')


def source_reference_schema() -> dict:
    """New locators are exact; legacy citation identities remain representable."""
    return {"anyOf":[{"type":"string"},source_replacement_schema()["items"],source_replacement_schema(),bibliographic_reference_schema(),
        {"type":"object","not":{"anyOf":[{"required":["path"]},{"required":["reference_key"]}]},"additionalProperties":True}]}


def validate_created_source_reference(project: str, ref, root: Path):
    if isinstance(ref,str):
        if re.search(r"#sha256[=:]",ref,re.I):
            raise ValueError('A #sha256 fragment is interpreted as a TeX label. Supply a structured source_ref/ref with repository, path, sha256 and an observed label or line_start/line_end instead; existing records can be repaired with concept_change set_source')
        return
    if isinstance(ref,list):
        validate_source_replacement(project,ref,root,context='ref');return
    if isinstance(ref,dict):
        if 'reference_key' in ref:
            try:validate_bibliographic_reference(project,ref,root)
            except ValueError as exc:raise ValueError(f'ref.{exc} No existing record changed.') from exc
            return
        if 'path' in ref:
            try:validate_source_replacement(project,[ref],root,context='ref')
            except ValueError as exc:raise ValueError(str(exc).replace('ref[0]','ref',1)) from exc
        elif 'file' in ref and any(key in ref for key in ('label','line','line_start','line_end','sha256')):
            locator={**ref,'path':ref['file']};locator.pop('file',None)
            if 'line' in locator:
                line=locator.pop('line');locator.setdefault('line_start',line);locator.setdefault('line_end',line)
            try:validate_source_replacement(project,[locator],root,context='ref')
            except ValueError as exc:raise ValueError(str(exc).replace('ref[0]','ref',1)) from exc
        return
    raise ValueError('source_ref/ref must be a legacy reference string, a structured source locator, or an array of locators')


def schema() -> dict:
    text = {"type": "string", "maxLength": 40000}
    locator = source_locator_schema()
    return {"type": "object", "additionalProperties": False, "properties": {
        "statement_tex": text, "domain": text,
        "assumptions": {"type": "array", "maxItems": 50, "items": {
            "type": "object", "additionalProperties": False, "required": ["text"],
            "properties": {"text": {**text, "minLength": 1},
                           "node_id": {"type": "string", "minLength": 1}}}},
        "proof": {"type": "object", "additionalProperties": False,
                  "required": ["text"], "properties": {"text": text}},
        "sources": {"type": "array", "maxItems": 20, "items": locator},
        "primary_source": {"type": "integer", "minimum": 0},
        "formal_targets": {"type": "array", "maxItems": 20, "items": {
            "type": "object", "additionalProperties": False,
            "required": ["file", "declaration"],
            "properties": {key: {"type": "string", "minLength": 1} for key in
                           ("file", "declaration", "result_id", "result_revision", "concept_id")}}},
        "limitations": {"type": "array", "maxItems": 50, "items": text}}}


def validate(value: dict, nodes: dict) -> None:
    def check(item, rule, path):
        kind = rule.get("type")
        good = ((kind == "object" and isinstance(item,dict)) or
                (kind == "array" and isinstance(item,list)) or
                (kind == "string" and isinstance(item,str)) or
                (kind == "integer" and isinstance(item,int) and not isinstance(item,bool)))
        if not good:
            raise ValueError(f"{path} must be {kind}")
        if kind == "object":
            missing = set(rule.get("required",[]))-set(item)
            unknown = set(item)-set(rule.get("properties",{}))
            if missing: raise ValueError(f"{path} requires {', '.join(sorted(missing))}")
            if unknown: raise ValueError(f"{path} has unknown fields: {', '.join(sorted(unknown))}")
            for key, child in item.items(): check(child,rule["properties"][key],path+"."+key)
        elif kind == "array":
            if len(item)>rule.get("maxItems",50): raise ValueError(f"{path} has too many entries")
            for i, child in enumerate(item): check(child,rule["items"],f"{path}[{i}]")
        elif kind == "string":
            if len(item)>rule.get("maxLength",40000) or len(item.strip())<rule.get("minLength",0):
                raise ValueError(f"{path} has invalid text length")
            if rule.get("pattern") and not re.fullmatch(rule["pattern"],item):
                raise ValueError(_invalid_sha256(path,item))
        elif kind == "integer" and item<rule.get("minimum",0):
            raise ValueError(f"{path} must be at least {rule['minimum']}")
    check(value,schema(),"mathematics")
    for assumption in value.get("assumptions", []):
        if assumption.get("node_id") and assumption["node_id"] not in nodes:
            raise ValueError("assumption node_id must name an existing concept")
    for target in value.get('formal_targets', []):
        if target.get('concept_id'):
            if target['concept_id'] not in nodes or target.get('result_id') or target.get('result_revision'):
                raise ValueError('formal target concept_id must name one existing concept without a result binding')
        elif not target.get('result_id') or not target.get('result_revision'):
            raise ValueError('formal target requires concept_id or result_id plus result_revision')
    for index,source in enumerate(value.get("sources", [])):
        if bool(source.get("line_start")) != bool(source.get("line_end")):
            raise ValueError(f"mathematics.sources[{index}].line_start and line_end must be supplied together")
        if source.get("line_end", 0) < source.get("line_start", 0):
            raise ValueError(f"mathematics.sources[{index}].line_end must not precede line_start")
    if "primary_source" in value:
        sources = value.get("sources") or []
        if value["primary_source"] >= len(sources):
            raise ValueError("primary_source must index the authored sources array")


def validate_source_replacement(project: str, value, root: Path, *, context: str = 'set_source.value') -> list[dict]:
    if not isinstance(value,list):raise ValueError(f'{context} must be the complete array of structured source locators; [] explicitly clears it. No existing record changed.')
    try:validate({"sources":value},{})
    except ValueError as exc:
        raise ValueError(str(exc).replace('mathematics.sources',context)+' No existing record changed.') from exc
    for index,locator in enumerate(value):
        if locator.get('label') and ('line_start' in locator or 'line_end' in locator):
            raise ValueError(f'{context}[{index}]: choose a TeX label OR an exact line range, not both. No existing record changed.')
        if not locator.get('label') and not (locator.get('line_start') and locator.get('line_end')):
            raise ValueError(f'{context}[{index}] needs a real TeX label or exact line_start/line_end from a source read; sha256 is a separate identity field. No existing record changed.')
        resolved=resolve_source(project,locator,root)
        if resolved.get('status')!='READ':raise ValueError(f"{context}[{index}]: {resolved.get('error')}; read repository search/read and supply an observed location. No existing record changed.")
    return value


def _uncomment(text: str) -> str:
    # Preserve offsets for provenance; escaped percent signs remain content.
    return re.sub(r"(?<!\\)%[^\n]*", lambda m: " " * len(m[0]), text)


def _environments(text: str) -> list[tuple]:
    stack, spans = [], []
    for match in _ENV.finditer(text):
        action, name = match.groups()
        if action == "begin":
            stack.append((name, match.start(), match.end()))
        elif stack and stack[-1][0] == name:
            _, start, body_start = stack.pop()
            spans.append((name, start, match.end(), body_start, match.start()))
    return spans


def _body(text: str, span: tuple) -> str:
    value = text[span[3]:span[4]].strip()
    value = re.sub(r"^\s*\[[^\]]*\]", "", value)
    return re.sub(r"\\label\s*\{[^{}]*\}", "", value).strip()


def resolve_source(project: str, ref, root: Path, *, read_context=None) -> dict:
    """Read a bounded labeled/ranged source, with an explicit unresolved result."""
    from laplace.manuscript import manuscript_source
    from laplace.projects import writing_sources
    row = {"status": "UNRESOLVED", "reference": ref}
    try:
        repositories = writing_sources.inventory(root)["repositories"]
        names = {item["id"] for item in repositories}
        if isinstance(ref, str):
            path, _, label = ref.partition("#")
            prefix, sep, tail = path.partition(":")
            spec = {"path": tail if sep and prefix in names else path}
            if sep and prefix in names:
                spec["repository"] = prefix
            if label:
                spec["label"] = label
        elif isinstance(ref, dict):
            spec = dict(ref)
            spec["path"] = spec.get("path") or spec.get("file")
            if spec.get("line") and not spec.get("line_start"):
                spec["line_start"] = spec["line_end"] = spec["line"]
        else:
            raise ValueError("Source locator must be text or an object")
        if not isinstance(spec.get("path"), str) or not spec["path"]:
            raise ValueError("Source locator has no file path")
        row.update({key: spec[key] for key in ("repository", "path", "label") if key in spec})
        if spec.get("repository"):
            _, path = writing_sources._path(root, spec)
        else:
            path = (root / spec["path"]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Source path escapes the project repository")
            if not path.is_file():
                selected = manuscript_source.resolve(project, repo_root=root)
                directory = selected.get("manuscript_dir")
                if not directory:
                    raise ValueError("No selected manuscript source directory")
                base = (root / directory).resolve()
                path = (base / spec["path"]).resolve()
                if not path.is_relative_to(base):
                    raise ValueError("Source path escapes the manuscript directory")
        if not path.is_file() or path.stat().st_size > 2_000_000:
            raise ValueError("Source must be a local text file smaller than 2 MB")
        observation=writing_sources.observe_bytes(path,read_context)
        raw=observation['raw'];actual_sha256=observation['sha256']
        if spec.get('sha256'):
            from laplace.core.identity import revision_matches
            row.update(sha256=actual_sha256,expected_sha256=spec['sha256'])
            if not revision_matches(spec['sha256'],actual_sha256):raise ValueError('Source SHA-256 changed; reread the original source before replacing its locator')
        text = raw.decode("utf-8")
        if "\x00" in text:
            raise ValueError("Source is binary")
        clean = _uncomment(text)
        spans = _environments(clean)
        start, end, statement, proof = None, None, None, None
        if spec.get("label"):
            matches = list(re.finditer(r"\\label\s*\{" + re.escape(spec["label"]) + r"\}", clean))
            if len(matches) != 1:
                if str(spec["label"]).startswith(("sha256=","sha256:")):
                    raise ValueError("A #sha256 fragment is not a TeX label. Use concept_change set_source with a structured locator, sha256 field and observed label or line range")
                raise ValueError("Source label is missing or ambiguous")
            position = matches[0].start()
            enclosing = [span for span in spans if span[1] <= position < span[2]]
            mathematical = [span for span in enclosing if span[0].rstrip("*") in ENVIRONMENTS]
            selected_span = min(mathematical or enclosing, key=lambda x: x[2]-x[1], default=None)
            if selected_span:
                start, end = selected_span[1:3]
                if selected_span[0].rstrip("*") in ENVIRONMENTS:
                    statement = selected_span
                    following = sorted((span for span in spans if span[0] == "proof" and span[1] >= end), key=lambda x:x[1])
                    if following and not clean[end:following[0][1]].strip():
                        proof = following[0]
                        end = proof[2]
            else:
                raise ValueError("Label has no enclosing mathematical environment; use an explicit source range")
        elif spec.get("line_start") and spec.get("line_end"):
            lines = text.splitlines(keepends=True)
            first, last = int(spec["line_start"]), int(spec["line_end"])
            if not 1 <= first <= last <= len(lines):
                raise ValueError("Source line range is outside the file")
            start, end = sum(map(len, lines[:first-1])), sum(map(len, lines[:last]))
            candidates = [span for span in spans if span[0].rstrip("*") in ENVIRONMENTS
                          and start <= span[1] and span[2] <= end]
            if len(candidates) == 1:
                statement = candidates[0]
                following = [span for span in spans if span[0] == "proof" and
                             statement[2] <= span[1] and span[2] <= end and
                             not clean[statement[2]:span[1]].strip()]
                proof = following[0] if following else None
        else:
            raise ValueError("Source needs an exact label or line_start/line_end; use repository search to locate it")
        fragment = text[start:end]
        excerpt = "".join(fragment.splitlines(keepends=True)[:240])[:32000]
        truncated = len(excerpt) < len(fragment)
        row.update(status="READ", file=str(path), sha256=actual_sha256,
                   line_start=text.count("\n",0,start)+1, line_end=text.count("\n",0,end-1)+1,
                   excerpt=excerpt, truncated=truncated)
        if not truncated and statement:
            row.update(statement_tex=_body(clean,statement), environment=statement[0])
        if not truncated and proof:
            row["proof_text"] = _body(clean,proof)
        if path.is_relative_to(root):
            row["file"] = str(path.relative_to(root))
        return row
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        return {**row, "error": str(exc)}


def _verification(project: str, targets: list, bindings: list, root: Path, ident: str = "") -> dict:
    result = {"status": "NOT_CHECKED", "informal_alignment": "UNASSESSED", "receipts": []}
    if not targets and not bindings and not ident:
        return result
    from laplace.pipeline import formal_verification
    formal = formal_verification.state(project, repo_root=root)
    def target_matches(receipt, target):
        if receipt.get('file') != target.get('file') or receipt.get('declaration') != target.get('declaration'): return False
        if target.get('concept_id'):
            return (receipt.get('concept') or {}).get('id') == target['concept_id']
        linked = receipt.get('result') or {}
        return linked.get('id') == target.get('result_id') and linked.get('revision') == target.get('result_revision')
    def matches(receipt):
        if targets: return any(target_matches(receipt, target) for target in targets)
        if ident and (receipt.get('concept') or {}).get('id') == ident: return True
        linked = receipt.get('result') or {}
        return any(linked.get('id') == b.get('id') and linked.get('revision') == b.get('revision') for b in bindings)
    receipts = [r for r in formal.get("receipts", []) if not r.get("superseded") and matches(r)]
    direct = [r for r in receipts if ident and (r.get("concept") or {}).get("id") == ident]
    if not targets and not direct:
        return {**result,"status":"RELATED_FORMAL_RECEIPT" if receipts else "NOT_CHECKED",
                "related_receipts":receipts,
                "reason":"These checks share a result binding; no declaration is explicitly linked to this concept."}
    result.update(receipts=receipts, reason=formal.get("reason"))
    if not receipts:
        result["status"] = "NOT_CHECKED"
    elif any(r.get("stale") for r in receipts):
        result["status"] = "STALE"
    elif formal.get("proof_status") == "UNAVAILABLE":
        result["status"] = "UNAVAILABLE"
    elif all(r.get("proof_status") == "CHECKED" for r in receipts):
        complete = bool(direct) if not targets else all(any(target_matches(receipt,target) for receipt in receipts) for target in targets)
        result["status"] = "CHECKED_DECLARATION" if complete else "PARTIALLY_CHECKED"
    else:
        result["status"] = "NOT_ESTABLISHED"
    return result


def read(project: str, ident: str, node: dict, root: Path, *, include_verification: bool = True, read_context=None) -> dict:
    projection = node.get("projection") or {}
    authored = projection.get("mathematics") or {}
    if not isinstance(authored, dict):
        authored = {}
    raw = node.get("source") or node.get("sources") or node.get("ref") or []
    authored_sources = list(authored.get("sources") or [])
    primary_ref = (authored_sources[authored["primary_source"]]
                   if isinstance(authored.get("primary_source"), int)
                   and 0 <= authored["primary_source"] < len(authored_sources) else None)
    refs = authored_sources + (raw if isinstance(raw,list) else [raw])
    refs = list({json.dumps(ref,sort_keys=True,default=str):ref for ref in refs}.values())
    if primary_ref is not None:
        primary_key = json.dumps(primary_ref,sort_keys=True,default=str)
        refs = [primary_ref] + [ref for ref in refs
                                if json.dumps(ref,sort_keys=True,default=str) != primary_key]
    sources, seen = [], set()
    inspected = 0
    for ref in refs:
        if inspected >= 12 or len(sources) >= 6:
            break
        inspected += 1
        item = resolve_source(project,ref,root,read_context=read_context)
        key = (item.get("file"),item.get("sha256"),item.get("line_start"),item.get("line_end")) if item.get("status")=="READ" else json.dumps(ref,sort_keys=True,default=str)
        if key in seen: continue
        seen.add(key);sources.append(item)
    statement_sources = [source for source in sources if source.get("statement_tex")]
    normalized = {re.sub(r"\s+", " ", source["statement_tex"]).strip()
                  for source in statement_sources}
    source_ambiguity = []
    if primary_ref is not None:
        candidate = sources[0] if sources and sources[0].get("statement_tex") else {}
    elif len(normalized) <= 1:
        candidate = statement_sources[0] if statement_sources else {}
    else:
        candidate = {}
        source_ambiguity = [{key: source.get(key) for key in
                             ("reference", "repository", "path", "label", "file", "sha256",
                              "line_start", "line_end", "statement_tex")}
                            for source in statement_sources]
    authored_statement = str(authored.get("statement_tex") or "").strip()
    statement = authored_statement or candidate.get("statement_tex") or ""
    proof_text = (authored.get("proof") or {}).get("text") or (candidate.get("proof_text") if not authored_statement else "") or ""
    proof = {"text": proof_text, "status": "NOT_RECORDED"}
    if proof_text:
        proof["status"] = "AUTHORED_UNREVIEWED" if (authored.get("proof") or {}).get("text") else "SOURCE_UNREVIEWED"
        if proof["status"] == "SOURCE_UNREVIEWED":
            proof["source"] = {key: candidate.get(key) for key in ("file","repository","path","label","sha256","line_start","line_end")}
    missing = []
    if source_ambiguity and not authored_statement:
        missing.append("unambiguous primary mathematical source")
    elif not statement:
        missing.append("precise statement")
    indexing_gaps = []
    fields = missing if authored_statement or not statement else indexing_gaps
    if not authored.get("domain"): fields.append("domain and scope")
    if "assumptions" not in authored: fields.append("explicit assumptions (or an explicit empty list)")
    if node.get("kind") in PROOF_KINDS and not proof_text: missing.append("proof or derivation")
    targets = authored.get("formal_targets") or []
    bindings = projection.get("result_bindings") or []
    verification = _verification(project,targets,bindings,root,ident=ident) if include_verification else {"status":"NOT_OBSERVED","informal_alignment":"UNASSESSED","receipts":[]}
    result = {"schema_version":"laplace.mathematical-record/1", "node":ident,
              "kind":node.get("kind"), "statement_tex":statement,
              "statement_origin":"AUTHORED" if authored_statement else "SOURCE" if statement else "MISSING",
              "domain":authored.get("domain", ""), "assumptions":authored.get("assumptions", []),
              "proof":proof, "source_locations":sources,
              "sources_omitted":max(0,len(refs)-inspected),
              "source_ambiguity":source_ambiguity,
              "evidence_links":bindings, "formal_targets":targets, "verification":verification,
              "qualification":{"status":"INCOMPLETE" if missing else "SOURCE_DOCUMENTED_UNREVIEWED" if not authored_statement else "DOCUMENTED_UNREVIEWED",
                               "missing":missing,"indexing_gaps":indexing_gaps,
                               "source_gaps":sum(s.get("status")!="READ" for s in sources),
                               "note":"Source statements carry their own hypotheses; optional separate indexing is not required. Documented content is not a certificate of mathematical correctness."},
              "limitations":authored.get("limitations", []), "authored":authored}
    result["revision"] = hashlib.sha256(json.dumps(result,sort_keys=True,default=str).encode()).hexdigest()
    return result
