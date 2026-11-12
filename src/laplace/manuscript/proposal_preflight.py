"""Pure source-addressing validation for model manuscript proposals."""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from laplace.manuscript import manuscript_source

from laplace.core.identity import require_schema_version

VERSION = "laplace.proposal-preflight/1"
SOURCE_ANCHOR_SCHEMA = "laplace.source-anchor/2"
SOURCE_ANCHOR_SCHEMAS = ("laplace.source-anchor/1", SOURCE_ANCHOR_SCHEMA)

def source_anchor_contract() -> dict:
    """The source-address owner's supported tagged and tagless input forms."""
    return {"type":"object", "properties":{
        "schema_version":{"enum":list(SOURCE_ANCHOR_SCHEMAS)},
        "sha256":{"type":"string"},
        **{key:{"type":"integer"} for key in ("line_start","line_end")},
        **{key:{"type":"array","items":{"type":"string"}} for key in ("prefix","suffix")},
        **{key:{"type":"boolean"} for key in ("unique","at_start","at_end")}},
        "additionalProperties":False}


def source_anchor_version_error(anchor) -> str | None:
    try:require_schema_version(anchor, SOURCE_ANCHOR_SCHEMAS, owner="Source anchor", allow_untagged=True)
    except ValueError as exc:return str(exc)
    return None


def _resolve(root: Path, manuscript: Path, value: str) -> Path | None:
    raw = Path(str(value or ""))
    if raw.is_absolute() or ".." in raw.parts:
        return None
    for candidate in ((root / raw).resolve(), (manuscript / raw).resolve()):
        try:
            candidate.relative_to(manuscript)
        except ValueError:
            continue
        if candidate.suffix == ".tex" and candidate.is_file():
            return candidate
    return None


def consumed_source_identity(root:Path, manuscript:Path, value:str, allowed:Mapping[Path,Any]) -> Path | None:
    """Resolve a lookup alias only to one already-consumed selected-source identity."""
    raw=Path(str(value or ''))
    if raw.is_absolute() or '..' in raw.parts or raw.suffix!='.tex':return None
    direct=_resolve(root,manuscript,value)
    if direct is not None:return direct if direct in allowed else None
    from laplace.pipeline.authoring import _source_matches
    candidates=[]
    for path in allowed:
        resolved=path.resolve()
        if not resolved.is_file() or not resolved.is_relative_to(manuscript) or not resolved.is_relative_to(root):continue
        if _source_matches({'file':resolved.relative_to(root).as_posix()},str(raw)):
            candidates.append(resolved)
    return candidates[0] if len(set(candidates))==1 else None


def _scope(turn: Mapping[str, Any], root: Path, manuscript: Path, project:str) -> dict[Path, list[tuple[int, int]] | None]:
    allowed: dict[Path, list[tuple[int, int]] | None] = {}

    def admit(value, lo=None, hi=None):
        path = _resolve(root, manuscript, str(value or ""))
        if path is None:
            return
        if lo is None or hi is None:
            allowed[path] = None
            return
        if path in allowed and allowed[path] is None:
            return
        allowed.setdefault(path, []).append((int(lo), int(hi)))

    receipt = turn.get("dependencies") or {}
    if isinstance(receipt, Mapping):
        for row in receipt.get("source_dependencies") or []:
            if isinstance(row, Mapping) and row.get("role") == "selected":
                admit(row.get("file"), row.get("line_start"), row.get("line_end"))
        for row in receipt.get("selection_spans") or []:
            if isinstance(row, Mapping):
                admit(row.get("file"), row.get("line_start"), row.get("line_end"))
    selection = turn.get("selection") or {}
    if isinstance(selection, Mapping):
        for file in selection.get("files") or []:
            admit(file, selection.get("line_start"), selection.get("line_end"))
    for read in (turn.get("tool_reads") or {}).values():
        if not isinstance(read, Mapping) or read.get("operation") != "source":
            continue
        projected=read.get("source_scope")
        if isinstance(projected,list):
            for row in projected:
                if isinstance(row,Mapping):admit(row.get("file"),row.get("line_start"),row.get("line_end"))
            continue
        payload = read.get("payload") or {}
        if not isinstance(payload, Mapping):
            continue
        for file in payload.get("files") or []:
            admit(file, payload.get("line_start"), payload.get("line_end"))
        if payload.get("section_ids"):
            # Compatibility for source reads banked before source_scope existed.
            # Re-run the same canonical selector; current-read checks elsewhere
            # still require this projection to match the banked output digest.
            from laplace.pipeline import authoring
            observed=authoring.inspect(project,payload,repo_root=root)
            for row in observed.get("sources") or []:
                if isinstance(row,Mapping):admit(row.get("file"),row.get("line_start"),row.get("line_end"))
    return allowed


def canonical_consumed_files(root:Path, project:str, turn:Mapping[str,Any], values:list[str]) -> list[str]:
    """New recovery uses the same consumed selected-source identity as validation."""
    source=manuscript_source.resolve(project,repo_root=root)
    directory=source.get('manuscript_dir')
    if not isinstance(directory,str) or not directory:return list(values)
    raw=Path(directory);manuscript=(raw if raw.is_absolute() else root/raw).resolve()
    allowed=_scope(turn,root,manuscript,project)
    result=[]
    for value in values:
        path=consumed_source_identity(root,manuscript,value,allowed)
        name=path.relative_to(root).as_posix() if path is not None else value
        if name not in result:result.append(name)
    return result


def _within(span: tuple[int, int], ranges: list[tuple[int, int]] | None) -> bool:
    return ranges is None or any(lo <= span[0] and span[1] <= hi for lo, hi in ranges)


def _matches(raw: str, before: str) -> list[tuple[int, int]]:
    if not before:
        return []
    lines = raw.split("\n")
    width = before.count("\n") + 1
    found = []
    for index in range(0, len(lines) - width + 1):
        if "\n".join(lines[index:index + width]) == before:
            found.append((index + 1, index + width))
    return found


def source_anchor(raw: str, lo: int, hi: int) -> dict:
    """Server-authored identity for a proposed occurrence, including neighbours."""
    lines=raw.split("\n")
    prefix=lines[max(0,lo-3):lo-1]
    suffix=lines[hi:hi+2]
    context="\n".join(prefix+lines[lo-1:hi]+suffix)
    return {"schema_version":SOURCE_ANCHOR_SCHEMA,"sha256":hashlib.sha256(raw.encode()).hexdigest(),
            "line_start":lo,"line_end":hi,
            "prefix":prefix,"suffix":suffix,"unique":len(_matches(raw,context))==1,
            "at_start":lo==1,"at_end":not any(line.strip() for line in lines[hi:])}


def _anchored_matches(raw:str,before:str,anchor:dict) -> list[tuple[int,int]]:
    if source_anchor_version_error(anchor):return []
    if not anchor.get("unique"):return []
    prefix,suffix=anchor.get("prefix"),anchor.get("suffix")
    if not isinstance(prefix,list) or not isinstance(suffix,list):return []
    if not all(isinstance(line,str) for line in prefix+suffix):return []
    context="\n".join(prefix+[before]+suffix)
    width=before.count("\n")+1
    # Old anchors called the final empty split line an unconsumed suffix. Prove
    # the original EOF from its recorded full-file digest, never from span size.
    eof=bool(anchor.get('at_end')) or (not any(line.strip() for line in suffix)
        and hashlib.sha256(context.encode()).hexdigest()==anchor.get('sha256'))
    if (anchor.get('schema_version')!=SOURCE_ANCHOR_SCHEMA and not eof
            and not any(line.strip() for line in suffix)):
        return []  # Legacy whitespace suffix cannot prove partial scope versus EOF.
    lines=raw.split('\n')
    return [(lo+len(prefix),lo+len(prefix)+width-1) for lo,hi in _matches(raw,context)
            if (not anchor.get("at_start") or lo==1)
            and (not eof or not any(line.strip() for line in lines[lo+len(prefix)+width-1:]))]


def proven_current_span(raw:str,edit:Mapping[str,Any],*,turn=None,root=None,path=None) -> tuple[int,int]|None:
    """Prove an occurrence from recorded source identity, never historical offsets alone."""
    before=edit.get('before');lines=raw.split('\n')
    if not isinstance(before,str):return None
    anchor=edit.get('source_anchor')
    sha=hashlib.sha256(raw.encode()).hexdigest()
    if isinstance(anchor,dict):
        if source_anchor_version_error(anchor):return None
        if anchor.get('sha256')==sha:
            lo,hi=anchor.get('line_start'),anchor.get('line_end')
            if isinstance(lo,int) and isinstance(hi,int) and 1<=lo<=hi<=len(lines) and '\n'.join(lines[lo-1:hi])==before:
                return lo,hi
            return None
        candidates=_anchored_matches(raw,before,anchor)
        return candidates[0] if len(candidates)==1 else None
    lo,hi=edit.get('line_start'),edit.get('line_end')
    if not isinstance(lo,int) or not isinstance(hi,int) or not 1<=lo<=hi<=len(lines) or '\n'.join(lines[lo-1:hi])!=before:return None
    # A complete current preimage proves the file boundary. A legacy root edit
    # can also use the turn's recorded full root digest; a prefix cannot do so.
    if lo==1 and (hi==len(lines) or hi==len(lines)-1 and lines[-1]==''):return lo,hi
    document=(turn or {}).get('document') or {}
    if root is not None and path is not None and document.get('root') and (Path(root)/document['root']).resolve()==Path(path).resolve() and document.get('revision')==sha:return lo,hi
    return None


def _active_tex(raw:str) -> str:
    """Mask explicit literal regions only; this does not claim full TeX evaluation."""
    raw=raw.replace('\r\n','\n').replace('\r','\n')
    environment=re.compile(r'\\begin\s*\{(verbatim\*?|Verbatim|BVerbatim|LVerbatim|lstlisting|minted|comment)\}')
    inline=re.compile(r'\\(?:verb\*?|Verb|lstinline(?:\[[^\]\n]*\])?)(?P<delimiter>[^\w\s])')
    result=[];index=0
    def masked(end):
        nonlocal index
        result.append(re.sub(r'[^\n]',' ',raw[index:end]));index=end
    while index<len(raw):
        if raw[index]=='%':
            end=raw.find('\n',index);masked(len(raw) if end<0 else end);continue
        if raw[index]=='\\':
            literal=inline.match(raw,index)
            if literal:
                newline=raw.find('\n',literal.end());newline=len(raw) if newline<0 else newline
                close=raw.find(literal['delimiter'],literal.end(),newline)
                masked(close+1 if close>=0 else newline);continue
            opening=environment.match(raw,index)
            if opening:
                ending=re.search(r'\\end\s*\{'+re.escape(opening[1])+r'\}',raw[opening.end():])
                masked(opening.end()+ending.end() if ending else len(raw));continue
            # Escaped control symbols include \% and \\. A percent after a
            # doubled backslash is still an ordinary comment opener.
            if index+1<len(raw) and not raw[index+1].isalpha():
                result.append(raw[index:index+2]);index+=2;continue
        result.append(raw[index]);index+=1
    return ''.join(result)


def staged_integrity_errors(before:str,after:str,*,is_root:bool=False) -> list[str]:
    """Deterministic document boundaries and canonical identities, not prose-size guesses."""
    from laplace.manuscript import manuscript_source
    old,new=_active_tex(before),_active_tex(after)
    boundary=re.compile(r'\\documentclass\b|\\begin\s*\{document\}|\\end\s*\{document\}')
    old_tokens=boundary.findall(old);new_tokens=boundary.findall(new)
    errors=[]
    if is_root and new_tokens:
        matches=list(boundary.finditer(new))
        if matches[-1].group().replace(' ','')==r'\end{document}' and new[matches[-1].end():].strip():
            errors.append('replacement leaves source content after the document end')
    if old_tokens!=new_tokens:
        expected=[r'\documentclass',r'\begin{document}',r'\end{document}']
        normalized=[re.sub(r'\s+','',token) for token in new_tokens]
        if (not is_root and new_tokens) or (is_root and normalized!=expected):
            errors.append('replacement breaks the canonical document boundary; use a fresh source-centered proposal')
    labels=re.compile(r'\\label\s*\{([^{}]+)\}')
    old_labels=Counter(value for value in labels.findall(old) if '#' not in value and '\\' not in value)
    new_labels=Counter(value for value in labels.findall(new) if '#' not in value and '\\' not in value)
    duplicated=sorted(key for key,count in new_labels.items() if count>max(1,old_labels[key]))
    if duplicated:
        errors.append('replacement creates duplicate canonical labels: '+', '.join(
            '%s (x%d in this file)'%(key,new_labels[key]) for key in duplicated[:8])+(' and %d more'%(len(duplicated)-8) if len(duplicated)>8 else ''))
    return errors


def duplicate_label_errors(before_files:Mapping,after_files:Mapping,*,fact_cache=None) -> list[str]:
    pattern=re.compile(r'\\label\s*\{([^{}]+)\}')
    def labels(files):
        cache={} if fact_cache is None else fact_cache
        total=Counter()
        for path,raw in files.items():
            key=(str(path),hashlib.sha256(raw.encode()).hexdigest())
            if key not in cache:cache[key]=Counter(label for label in pattern.findall(_active_tex(raw)) if '#' not in label and '\\' not in label)
            total.update(cache[key])
        return total
    old,new=labels(before_files),labels(after_files)
    duplicated=sorted(label for label,count in new.items() if count>max(1,old[label]))
    if not duplicated:return []
    # name the conflicting label and every source occurrence, so the author can choose the
    # occurrence to rename instead of guessing from a bare refusal (dossier 2026-10-13)
    def where(label):
        places=[]
        for path,raw in after_files.items():
            count=sum(1 for found in pattern.findall(_active_tex(raw)) if found==label)
            if count:places.append('/'.join(Path(str(path)).parts[-2:])+('' if count==1 else ' x%d'%count))
        return label+' ('+', '.join(sorted(places))+')'
    return ['replacement creates duplicate canonical labels across source files: '+'; '.join(where(label) for label in duplicated[:8])
            +(' and %d more'%(len(duplicated)-8) if len(duplicated)>8 else '')]


def preflight(root: Path | str, project: str, turn: Mapping[str, Any], proposal: Any,
              *, relocate_unanchored: bool = True) -> dict:
    from laplace.manuscript.manuscript_proposals import ProposalIdentity, EditIdentity
    if isinstance(proposal,ProposalIdentity) or isinstance(proposal,Mapping) and any(isinstance(edit,EditIdentity) for edit in proposal.get("edits") or []):
        raise ValueError("Identity-only proposal summaries are read-only; exact source edit bodies are required.")
    root = Path(root).resolve()
    source = manuscript_source.resolve(project, repo_root=root)
    directory = source.get("manuscript_dir")
    manuscript = (root / str(directory or "")).resolve()
    result = {"schema_version": VERSION, "valid": True, "status": "VALID",
              "edits": [], "errors": [], "proposal": proposal}
    if source.get("status") != "resolved" or not directory or not manuscript.is_relative_to(root):
        return {**result, "valid": False, "status": "INVALID",
                "errors": ["selected manuscript source is unavailable"]}
    if not isinstance(proposal, Mapping) or not isinstance(proposal.get("edits"), list):
        return {**result, "valid": False, "status": "INVALID",
                "errors": ["provider reply has no structured edits array"]}
    # Provider schemas and human proposal rows share this owner boundary.  In
    # particular, scientific lineage is per edit; silently ignoring a top-level
    # declaration would drop the author's intended provenance.
    misplaced = set(proposal) & {"develops", "evidence_refs"}
    unknown = set(proposal) - {"answer", "edits"}
    if unknown:
        message = ("Proposal lineage belongs inside each edits[] item, not at top level. "
                   "Example: {\"edits\":[{\"file\":\"chapter.tex\",\"line_start\":2,\"line_end\":2,"
                   "\"before\":\"exact current text\",\"after\":\"revised text\",\"reason\":\"why\","
                   "\"develops\":[{\"id\":\"claim:current\",\"content_revision\":\"copy from concept\"}],"
                   "\"evidence_refs\":[]}]} . Read concept and research for real identities; "
                   "evidence_refs names current research results, while source citations use literal citekeys and canonical literature links."
                   if misplaced else "Unknown proposal fields: "+", ".join(sorted(unknown))+". Only answer and edits are accepted at proposal top level.")
        return {**result,"valid":False,"status":"INVALID","errors":[message]}
    if "answer" in proposal and not isinstance(proposal["answer"],str):
        return {**result,"valid":False,"status":"INVALID","errors":["proposal.answer must be text when supplied"]}
    normalized = {**proposal, "edits": []}
    allowed = _scope(turn, root, manuscript, project)
    occupied: dict[str, list[tuple[int, int]]] = {}
    for index, raw_edit in enumerate(proposal["edits"]):
        original = {key: raw_edit.get(key) if isinstance(raw_edit, Mapping) else None
                    for key in ("file", "line_start", "line_end")}
        row = {"index": index, "valid": False, "status": "INVALID",
               "original_span": original, "normalized_span": None,
               "normalization": None, "reason": None}
        if not isinstance(raw_edit, Mapping):
            row["reason"] = "edit is not an object"
            result["errors"].append(f"edit {index}: {row['reason']}")
            result["edits"].append(row)
            continue
        unknown_edit = set(raw_edit) - {"file","line_start","line_end","before","after","reason","develops","evidence_refs","source_anchor"}
        if unknown_edit:
            row["reason"] = "unknown edit fields: "+", ".join(sorted(unknown_edit))+"; use develops/evidence_refs on this edit for lineage, and only the documented source-address fields"
            result["errors"].append(f"edit {index}: {row['reason']}")
            result["edits"].append(row)
            normalized["edits"].append(dict(raw_edit))
            continue
        if raw_edit.get('source_anchor') is not None:
            version_error=source_anchor_version_error(raw_edit['source_anchor'])
            if version_error:
                row['reason']=version_error
                result['errors'].append(f"edit {index}: {version_error}")
                result['edits'].append(row)
                normalized['edits'].append(dict(raw_edit))
                continue
        if isinstance(raw_edit.get('before'),str) and isinstance(raw_edit.get('after'),str):
            # Addressing is over the same universal-newline text that
            # Path.read_text exposes. Raw source reads retain physical endings;
            # normalize their copied preimage without inventing a new scope.
            raw_edit={**raw_edit,**{key:raw_edit[key].replace('\r\n','\n').replace('\r','\n')
                                  for key in ('before','after')}}
        path = consumed_source_identity(root, manuscript, str(raw_edit.get("file") or ""),allowed)
        if path is None or path not in allowed:
            row["reason"] = "edit file was not consumed in the selected/source-tool scope"
        elif not isinstance(raw_edit.get("before"), str) or not isinstance(raw_edit.get("after"), str):
            row["reason"] = "before and after must be source text"
        elif (not isinstance(raw_edit.get("line_start"), int)
              or isinstance(raw_edit.get("line_start"), bool)
              or not isinstance(raw_edit.get("line_end"), int)
              or isinstance(raw_edit.get("line_end"), bool)):
            row["reason"] = "line_start and line_end must be integers"
        else:
            raw = path.read_text(encoding="utf-8")
            lines = raw.split("\n")
            lo, hi = raw_edit["line_start"], raw_edit["line_end"]
            declared = ("\n".join(lines[lo - 1:hi])
                        if 1 <= lo <= hi <= len(lines) else None)
            match = (lo, hi) if declared == raw_edit["before"] else None
            normalization = "declared-exact"
            anchor=raw_edit.get("source_anchor")
            anchor_changed=isinstance(anchor,dict) and anchor.get("sha256")!=hashlib.sha256(raw.encode()).hexdigest()
            if isinstance(anchor,dict) and not anchor_changed:
                a,b=anchor.get("line_start"),anchor.get("line_end")
                if isinstance(a,int) and isinstance(b,int) and 1<=a<=b<=len(lines) and '\n'.join(lines[a-1:b])==raw_edit['before']:
                    match=(a,b);normalization='recorded-source-anchor'
            if anchor_changed:
                # An unchanged sentence at the old line can be a different
                # occurrence after deletion. Check identity, not only its text.
                candidates=[span for span in _anchored_matches(raw,raw_edit["before"],anchor)
                            if _within(span,allowed[path])]
                match=candidates[0] if len(candidates)==1 else None
                normalization="unique-context-anchor"
                if match is None:row["reason"]="the proposed occurrence changed or its source context is ambiguous"
            if match is None:
                candidates = ([span for span in _matches(raw, raw_edit["before"])
                              if _within(span, allowed[path])]
                              if not anchor_changed and relocate_unanchored else [])
                if len(candidates) == 1:
                    match = candidates[0]
                    normalization = "unique-exact-full-line"
                elif not candidates:
                    row["reason"] = "before text has no exact full-line match in consumed scope"
                else:
                    row["reason"] = "before text has multiple exact full-line matches in consumed scope"
            if match is not None and not _within(match, allowed[path]):
                row["reason"] = "matched source span is outside the consumed scope"
                match = None
            if match is not None:
                canonical = path.relative_to(manuscript).as_posix()
                overlap = any(match[0] <= other[1] and match[1] >= other[0]
                              for other in occupied.setdefault(canonical, []))
                if overlap:
                    row["reason"] = "normalized edit overlaps another proposal edit"
                else:
                    occupied[canonical].append(match)
                    edit = dict(raw_edit)
                    edit.update(file=canonical, line_start=match[0], line_end=match[1])
                    edit["source_anchor"]=source_anchor(raw,*match)
                    normalized["edits"].append(edit)
                    row.update(valid=True, status="VALID", normalization=normalization,
                               normalized_span={"file": canonical,
                                                "line_start": match[0], "line_end": match[1]},
                               source_sha256=hashlib.sha256(raw.encode()).hexdigest())
        if not row["valid"]:
            result["errors"].append(f"edit {index}: {row['reason']}")
            normalized["edits"].append(dict(raw_edit))
        elif isinstance(raw_edit, Mapping) and ("develops" in raw_edit or "evidence_refs" in raw_edit):
            from laplace.manuscript import proposal_basis
            basis = proposal_basis.assess(root, project, edit)
            if basis["errors"]:
                row.update(valid=False, status="INVALID", reason="; ".join(basis["errors"]))
                result["errors"].append(f"edit {index}: {row['reason']}")
            else:
                row["basis"] = basis
        result["edits"].append(row)
    result["valid"] = not result["errors"]
    result["status"] = ("NORMALIZED" if result["valid"] and any(
        row.get("normalization") == "unique-exact-full-line" for row in result["edits"])
        else "VALID" if result["valid"] else "INVALID")
    result["proposal"] = normalized
    return result
