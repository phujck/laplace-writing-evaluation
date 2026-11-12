"""RESEARCH ARTIFACT READ (S1 B6): GET /research/artifact, resolved then read.

Two owners share this transport and stay visibly distinct:
  * ordinary Research state-home files: the project/manuscript base (research_context.project_root /
    the manuscript directory) and `_artifact_target`'s fence;
  * canonical writing artifacts (owner=writing-artifact or artifact_id): writing.artifacts.target /
    resolve_path, the receipt and path owner.
A path is never inferred from an id or basename. A complete receipt pin forces exact bytes; an
incomplete one is admitted only for the explicit writing-artifact owner, and the answer says the
historical identity is unavailable. json_record.py stays the pointer/page parser.

  resolve_read     admit scope/owner/pin and resolve the exact target (a refusal is a response).
  read_response    companion links, pinned bytes, PDF preview, NPZ projection, media, text pages.
  _artifact_target / _pinned_artifact_bytes / _companion_* / _source_companion / _pdf_companion /
  _zip_pdf_inclusion / _numpy_json_value / _npz_projection
                   the fenced target, byte-pin check, companion links and binary projections.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from laplace.projects import artifacts
from laplace.research import research_context
from laplace.web.research_http import json_reply, q1


def _zip_pdf_inclusion(archive: Path, pdf: Path, pdf_sha256: str) -> dict | None:
    """Observe exact PDF inclusion without extracting or trusting a manifest."""
    size = pdf.stat().st_size
    if not 0 < size <= 64 * 1024 * 1024:
        return None
    try:
        before = archive.stat()
        with zipfile.ZipFile(archive) as package:
            entries = package.infolist()
            if len(entries) > 2048:
                return None
            candidates = [entry for entry in entries if not entry.is_dir()
                          and entry.filename.lower().endswith('.pdf') and entry.file_size == size]
            if len(candidates) > 16 or sum(entry.file_size for entry in candidates) > 128 * 1024 * 1024:
                return None
            for entry in candidates:
                digest = hashlib.sha256()
                remaining = size
                with package.open(entry) as stream:
                    while chunk := stream.read(min(65536, remaining + 1)):
                        remaining -= len(chunk)
                        if remaining < 0:
                            return None
                        digest.update(chunk)
                if remaining == 0 and digest.hexdigest() == pdf_sha256:
                    after = archive.stat()
                    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                        return None
                    return {'member': entry.filename, 'pdf_sha256': pdf_sha256,
                            'inspection_only': True, 'download_binding': 'UNPINNED',
                            'claim': 'The exact exported PDF bytes were found during archive inspection; other members and later downloads are not assessed.'}
    except (OSError, ValueError, RuntimeError, NotImplementedError, zipfile.BadZipFile):
        pass
    return None


def _artifact_target(base: Path, raw: str, root: Path) -> Path | None:
    """Accept an explicit scope-relative or checkout-relative identity, never probe alternatives."""
    path = Path(raw)
    if not path.is_absolute():
        try:
            prefix = base.resolve().relative_to(root.resolve())
            if prefix.parts and path.parts[:len(prefix.parts)] == prefix.parts:
                return research_context.inside(base, root / path)
        except ValueError:
            pass
    return research_context.inside(base, path)


def _companion_relative(uri: str) -> tuple[str, str]:
    from urllib.parse import unquote, urlsplit
    import re
    if not isinstance(uri, str) or len(uri) > 4096:
        raise ValueError('Invalid companion link.')
    link = urlsplit(uri)
    relative = unquote(link.path)
    # Literal ../ is useful inside a project. Encoded traversal must not acquire
    # a second interpretation at another URI layer.
    if (link.scheme or link.netloc or link.query or not relative
            or relative.startswith(('/', '\\')) or '\\' in relative or '\0' in relative
            or re.search(r'%(?:2e|2f|5c|00|25)', link.path, re.I)):
        raise ValueError('Only literal relative project companion paths are supported; encoded traversal and URI schemes are refused.')
    return relative, link.fragment


def _companion_source_root(project: str, project_root: Path, source: Path, root: Path) -> Path:
    """Use the selected document only after proving membership in its source closure."""
    from laplace.manuscript import manuscript_source
    selected = manuscript_source.resolve(project, repo_root=root)
    if selected.get('status') == 'ambiguous':
        raise ValueError('Select a manuscript root before opening its companion links.')
    declared = selected.get('root')
    document = research_context.inside(project_root, root / declared) if isinstance(declared, str) else None
    if document and document.is_file():
        closure = manuscript_source.traversal(document, repo_root=root)
        members = {(root / value).resolve() for value in closure.get('files', [])}
        if source in members:
            return document
    # An unrelated standalone source keeps its own directory. Never choose a
    # candidate merely because the linked file exists there.
    return source


def _pinned_artifact_bytes(target: Path | None, expected: str) -> tuple[bytes | None, dict | None]:
    """Read once: the bytes verified here are the bytes returned by the media/download path."""
    if not expected or not target or not target.is_file():
        return None, None
    data = target.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        return None, {'error': 'Artifact identity changed. The recorded bytes were not returned. Reopen the recorded source or explicitly choose the current file.',
                      'expected_sha256': expected, 'actual_sha256': actual}
    return data, None


def _source_companion(project: str, project_root: Path, source: Path, uri: str, root: Path) -> dict:
    """Included chapters use their selected compiled document's companion base."""
    from urllib.parse import urlencode
    if not source or research_context.inside(project_root, source) != source or source.suffix.lower() != '.tex' or not source.is_file():
        raise ValueError('The originating project source is unavailable; reopen its exact source selection.')
    relative, fragment = _companion_relative(uri)
    document = _companion_source_root(project, project_root, source, root)
    target = research_context.inside(project_root, document.parent / relative)
    if not target:
        raise ValueError('The linked companion escapes this project; use a project-confined relative URI.')
    if not target.is_file():
        raise ValueError('Linked companion is missing: ' + target.relative_to(project_root).as_posix()
                         + '. Restore that file or correct the link relative to '
                         + document.relative_to(project_root).as_posix() + '.')
    suffix = target.suffix.lower()
    text_types = {'.json', '.jsonl', '.csv', '.tsv', '.txt', '.log', '.py', '.md', '.lean', '.tex', '.tikz', '.toml', '.yaml', '.yml'}
    if suffix not in text_types | {'.pdf', '.zip', '.npz', '.png', '.jpg', '.jpeg', '.svg'}:
        raise ValueError('This companion file type is not supported by the project reader.')
    kind = 'pdf' if suffix == '.pdf' else 'download' if suffix in {'.zip', '.npz'} else 'text' if suffix in text_types else 'image'
    path = target.relative_to(project_root).as_posix()
    params = {'project': project, 'scope': 'project', 'path': path}
    if kind == 'download': params['download'] = '1'
    return {'project': project, 'path': path, 'scope': 'project', 'kind': kind,
            'label': target.name, 'fragment': fragment,
            'basis': 'selected-manuscript-root' if document != source else 'current-source-directory',
            'origin_source': source.relative_to(project_root).as_posix(),
            'document_root': document.relative_to(project_root).as_posix(),
            'companion_identity': 'CURRENT_PROJECT_FILE',
            'url': '/research/artifact?' + urlencode(params)}


def _pdf_companion(project: str, project_root: Path, pdf: Path, uri: str, root: Path) -> dict:
    """Resolve a PDF link against its recorded source, confined to this project."""
    from urllib.parse import urlencode
    if not pdf or research_context.inside(project_root, pdf) != pdf or pdf.suffix.lower() != '.pdf' or not pdf.is_file():
        raise ValueError('The originating project PDF is unavailable.')
    relative, fragment = _companion_relative(uri)
    directory, basis, pdf_digest = pdf.parent, 'pdf-directory', None
    receipt_path = pdf.with_suffix('.json')
    if receipt_path.is_file():
        receipt, error = research_observation._read_object(receipt_path, {})
        if receipt.get('exported_file') or pdf.parent.name == 'exports':
            recorded_pdf = research_context.inside(project_root, root / str(receipt.get('exported_file') or ''))
            selection = receipt.get('selected_source')
            source = selection.get('root') if isinstance(selection, dict) else None
            selected = research_context.inside(project_root, root / source) if isinstance(source, str) else None
            pdf_digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
            if (error or recorded_pdf != pdf or receipt.get('project') != project or
                    receipt.get('pdf_sha256') != pdf_digest or not selected):
                raise ValueError('This exported PDF has no matching source receipt; its companion directory cannot be verified.')
            directory, basis = selected.parent, 'verified-export-source'
    elif pdf.parent.name == 'exports':
        raise ValueError('The export source receipt is missing; its companion directory cannot be verified.')
    target = research_context.inside(project_root, directory / relative)
    if not target or not target.is_file():
        raise ValueError('Linked companion is missing or outside this project: ' + relative + '. Restore the target or correct the link relative to the PDF source directory.')
    suffix = target.suffix.lower()
    text_types = {'.json', '.jsonl', '.csv', '.tsv', '.txt', '.log', '.py', '.md', '.lean', '.tex', '.tikz', '.toml', '.yaml', '.yml'}
    if suffix not in text_types | {'.pdf', '.zip', '.npz', '.png', '.jpg', '.jpeg', '.svg'}:
        raise ValueError('This companion file type is not supported by the project reader.')
    relative_target = target.relative_to(project_root).as_posix()
    params = {'project': project, 'path': relative_target, 'scope': 'project'}
    kind = 'pdf' if suffix == '.pdf' else 'download' if suffix in {'.zip', '.npz'} else 'text' if suffix in text_types else 'image'
    if kind == 'download': params['download'] = '1'
    inclusion = _zip_pdf_inclusion(target, pdf, pdf_digest) if suffix == '.zip' and pdf_digest else None
    return {'project': project, 'path': relative_target, 'scope': 'project', 'kind': kind,
            'label': target.name, 'basis': basis, 'fragment': fragment,
            'basis_scope': 'PDF identity and originating directory only; no companion snapshot',
            'companion_identity': 'CURRENT_PROJECT_FILE',
            'edition_match': 'EXACT_PDF_INCLUDED' if inclusion else 'UNRECORDED',
            'inclusion': inclusion,
            'notice': ('Current project package · this exact PDF was found during inspection. Other members and later file changes are unverified.' if inclusion else
                       'This link opens the current project file. Its match to this PDF edition has not been recorded.'),
            'url': '/research/artifact?' + urlencode(params)}


def _numpy_json_value(value:Any,np)->Any:
    """Convert a NumPy preview to strict JSON without erasing scientific types."""
    import datetime
    if isinstance(value,np.void) and value.dtype.names:
        return {name:_numpy_json_value(value[name],np) for name in value.dtype.names}
    if isinstance(value,np.ndarray):
        if value.dtype.names:
            return [_numpy_json_value(item,np) for item in value.reshape(-1)]
        return _numpy_json_value(value.tolist(),np)
    if isinstance(value,np.generic):
        if isinstance(value,(np.datetime64,np.timedelta64)):return str(value)
        return _numpy_json_value(value.item(),np)
    if isinstance(value,complex):
        return {'real':_numpy_json_value(value.real,np),'imag':_numpy_json_value(value.imag,np)}
    if isinstance(value,float):
        if value!=value:return 'NaN'
        if value==float('inf'):return '+Infinity'
        if value==float('-inf'):return '-Infinity'
        return value
    if isinstance(value,bytes):
        try:return value.decode('utf-8')
        except UnicodeDecodeError:return {'bytes_hex':value.hex()}
    if isinstance(value,(datetime.date,datetime.datetime,datetime.timedelta)):return str(value)
    if isinstance(value,(list,tuple)):return [_numpy_json_value(item,np) for item in value]
    if isinstance(value,dict):return {str(key):_numpy_json_value(item,np) for key,item in value.items()}
    if value is None or isinstance(value,(str,int,bool)):return value
    return str(value)


def _npz_projection(path:Path)->dict:
    """Bounded structural read of a NumPy archive; object payloads never load."""
    import numpy as np
    size=path.stat().st_size
    if size>64*1024*1024:raise ValueError("NPZ archive exceeds the 64 MiB inspection limit")
    arrays=[]
    with zipfile.ZipFile(path) as archive:
        members=[item for item in archive.infolist() if not item.is_dir()]
        if len(members)>128:raise ValueError("NPZ archive contains more than 128 members")
        if sum(item.file_size for item in members)>256*1024*1024:
            raise ValueError("NPZ archive expands beyond the 256 MiB inspection limit")
        for item in members:
            if not item.filename.endswith('.npy'):continue
            try:
                with archive.open(item) as stream:
                    version=np.lib.format.read_magic(stream)
                    reader=(np.lib.format.read_array_header_1_0 if version==(1,0) else
                            np.lib.format.read_array_header_2_0 if version==(2,0) else None)
                    if reader is None:raise ValueError(f"unsupported NPY header version {version}")
                    shape,fortran,dtype=reader(stream,max_header_size=10_000)
                    count=1
                    for dimension in shape:count*=int(dimension)
                    sample_count=min(count,8)
                    sample_bytes=sample_count*int(dtype.itemsize)
                    sample=(_numpy_json_value(np.frombuffer(stream.read(sample_bytes),dtype=dtype,
                                              count=sample_count),np)
                            if sample_count and sample_bytes<=8192 and not dtype.hasobject else None)
            except Exception as exc:
                arrays.append({'name':item.filename.removesuffix('.npy'),'status':'UNREADABLE',
                               'reason':str(exc)[:240]});continue
            row={'name':item.filename.removesuffix('.npy'),'shape':list(shape),
                 'dtype':str(dtype),'elements':count,'fortran_order':bool(fortran),
                 'compressed_bytes':item.compress_size,'bytes':item.file_size}
            if count<=16 and item.file_size<=64*1024 and not dtype.hasobject:
                try:row['values']=_numpy_json_value(
                    np.load(io.BytesIO(archive.read(item)),allow_pickle=False),np)
                except Exception as exc:row['values_error']=str(exc)[:240]
            elif dtype.hasobject:row['values_note']='Object values are not loaded.'
            else:
                if sample is not None:row['sample_values']=sample
                row['values_note']='Full values omitted; preview shows at most the first 8 stored values.'
            arrays.append(row)
    lines=[f"NumPy archive · {path.name}",f"{len(arrays)} array{'s' if len(arrays)!=1 else ''} · {size} bytes",'']
    for row in arrays:
        if row.get('status')=='UNREADABLE':lines.append(f"{row['name']} · unreadable · {row['reason']}");continue
        shape=' × '.join(str(value) for value in row['shape']) or 'scalar'
        line=f"{row['name']} · shape {shape} · {row['dtype']} · {row['elements']} values"
        if 'values' in row:line+=' · '+json.dumps(row['values'],ensure_ascii=False,allow_nan=False)
        elif 'sample_values' in row:line+=' · sample '+json.dumps(row['sample_values'],ensure_ascii=False,allow_nan=False)
        elif row.get('values_note'):line+=' · '+row['values_note']
        lines.append(line)
    return {'kind':'numpy-archive','arrays':arrays,'content':'\n'.join(lines)+'\n',
            'bytes':size,'download_available':True}


@dataclass
class ReadTarget:
    """An admitted /research/artifact read: the exact target and the identity it is read against."""
    root: Path
    project: str
    item: Any
    manuscript: Path | None
    scope: str
    raw: str
    expected: str
    target: Path | None
    artifact_id: str = ''
    receipt_unpinned: bool = False
    artifact_record: dict | None = None


def read(project: str, query: dict, method: str, repo_root=None) -> tuple:
    """GET /research/artifact: resolve the exact target, then read it."""
    if method != 'GET': return json_reply(405, {'error':'GET only'})
    root = Path(repo_root) if repo_root else research_context.repo_root()
    resolved = resolve_read(root, project, query)
    if isinstance(resolved, tuple):
        return resolved
    return read_response(resolved, query)


def resolve_read(root: Path, project: str, query: dict) -> ReadTarget | tuple:
    """Admit scope, owner and pin, and resolve the exact target; a refusal is returned as its response."""
    _q1, _json = q1, json_reply
    item, manuscript = research_context.project(project, root)
    scope = _q1(query, 'scope') or 'manuscript'
    if scope not in {'project', 'manuscript'}:
        return _json(422, {'error':'scope must be project or manuscript'})
    # Artifact project scope is the same owner workspace used by native tools,
    # including separately declared state for read-only imported manuscripts.
    artifact_owner = _q1(query,'owner')
    if artifact_owner not in {'','writing-artifact'}:
        return _json(422, {'error':'Unknown artifact reader owner.'})
    if scope == 'project' and (artifact_owner or _q1(query,'artifact_id')):
        try:base = artifacts.project_root(root,project)
        except ValueError:base = None
    else:base = research_context.project_root(item,root) if item and scope=='project' else manuscript
    raw = _q1(query, 'path')
    expected = _q1(query, 'expected_sha256')
    if expected:
        match = re.fullmatch(r'(?:sha256:)?([a-fA-F0-9]{64})', expected)
        if not match:
            return _json(422, {'error': 'expected_sha256 must be a complete SHA-256 digest.'})
        expected = match[1].lower()
    artifact_id = _q1(query, 'artifact_id'); receipt_unpinned = False; artifact_record = None
    if artifact_id:
        try:
            exact, artifact_path, recorded_scope, artifact_record = artifacts.target(
                root, project, {'id':artifact_id}, allow_read_only=True)
            if _q1(query,'scope') and scope != recorded_scope:
                raise ValueError('Artifact receipt belongs to a different scope.')
            # a writing-artifact receipt is compared through its own owner
            if raw and (artifacts.resolve_path(root,project,raw,recorded_scope,allow_read_only=True) if artifact_owner
                        else _artifact_target(base,raw,root)) != exact:
                raise ValueError('Artifact receipt does not identify this exact scoped path.')
            recorded_pin=str((artifact_record or {}).get('sha256') or '').removeprefix('sha256:').lower()
            if not re.fullmatch(r'[a-f0-9]{64}',recorded_pin):
                # An older receipt without a complete pin: only the explicit writing-artifact owner may read the
                # CURRENT bytes at the receipt's exact path and scope (as native read_artifact does by id). The
                # answer says the historical identity is unavailable; a requested pin guards current bytes only.
                if not artifact_owner:
                    raise ValueError('Historical artifact receipt has no complete byte identity.')
                receipt_unpinned, recorded_pin = True, expected
            elif expected and expected != recorded_pin:
                raise ValueError('Requested byte identity differs from the exact artifact receipt.')
            scope, raw, expected, target = recorded_scope, artifact_path, recorded_pin, exact
        except (ValueError,OSError) as exc:
            return _json(422, {'error':str(exc)})
    else:
        if artifact_owner:
            try:target = artifacts.resolve_path(root,project,raw,scope,allow_read_only=True)
            except ValueError as exc:return _json(422, {'error':str(exc)})
        else:target = _artifact_target(base, raw, root) if base else None
    return ReadTarget(root, project, item, manuscript, scope, raw, expected, target,
                      artifact_id, receipt_unpinned, artifact_record)


def read_response(read: ReadTarget, query: dict) -> tuple:
    """The admitted target's response: a companion link, a binary/media read, or a paged text read."""
    _q1, _json = q1, json_reply
    if _q1(query, 'resolve') in {'pdf-link', 'source-link'}:
        return _companion_link(read, query)
    target, expected = read.target, read.expected
    if target and target.suffix.lower() == '.npz' and expected and _q1(query, 'download') != '1':
        return _json(422, {'error': 'Pinned NPZ previews are unsupported. Use the hash-guarded download or explicitly open the current inspector.'})
    pinned_data, mismatch = _pinned_artifact_bytes(target, expected)
    if mismatch: return _json(409, mismatch)
    if target and target.is_file() and target.suffix.lower() == '.zip' and _q1(query, 'download') == '1':
        return 200, 'application/zip', (pinned_data if pinned_data is not None else target.read_bytes())
    if target and target.is_file() and target.suffix.lower() == '.pdf' and _q1(query, 'preview') == 'png':
        return _pdf_preview(read, pinned_data)
    if target and target.is_file() and target.suffix.lower()=='.npz':
        return _npz_read(read, query, pinned_data)
    media_types={'.pdf':'application/pdf','.png':'image/png','.jpg':'image/jpeg',
                 '.jpeg':'image/jpeg','.svg':'image/svg+xml; charset=utf-8'}
    if target and target.is_file() and target.suffix.lower() in media_types:
        return 200, media_types[target.suffix.lower()], (pinned_data if pinned_data is not None else target.read_bytes())
    if not target or not target.is_file() or (target.suffix.lower() not in {
            '.json','.jsonl','.csv','.tsv','.txt','.log','.py','.md','.lean','.tex','.tikz',
            '.toml','.yaml','.yml'} and target.name!='lean-toolchain'):
        return _json(404, {'error':'project text artifact unavailable'})
    return _text_read(read, query, pinned_data if pinned_data is not None else target.read_bytes())


def _companion_link(read: ReadTarget, query: dict) -> tuple:
    """resolve=pdf-link|source-link: the pinned target's compiled-PDF or source companion."""
    _q1, _json = q1, json_reply
    root, project, target = read.root, read.project, read.target
    project_base = research_context.project_root(read.item, root) if read.item else None
    if _q1(query, 'resolve') == 'pdf-link' and project_base and target and target.suffix.lower() == '.tex' and target.is_file():
        target = research_context.inside(project_base, _companion_source_root(project, project_base, target, root).with_suffix('.pdf'))
    try:
        if not project_base: raise ValueError('Project is unavailable.')
        _snapshot, mismatch = _pinned_artifact_bytes(target, read.expected)
        if mismatch: return _json(409, mismatch)
        if _q1(query, 'resolve') == 'source-link':
            return _json(200, _source_companion(project, project_base, target, _q1(query, 'uri'), root))
        return _json(200, _pdf_companion(project, project_base, target, _q1(query, 'uri'), root))
    except (ValueError, OSError) as exc:
        return _json(422, {'error': str(exc)})


def _pdf_preview(read: ReadTarget, pinned_data: bytes | None) -> tuple:
    # Disposable, content-addressed first-page thumbnail. Scientific files
    # and result identities are never written by this preview route.
    _json, target = json_reply, read.target
    data = (pinned_data if pinned_data is not None else target.read_bytes()); ident = hashlib.sha256(data).hexdigest()
    preview = read.manuscript / '.research_previews' / (ident + '.png')
    if not preview.is_file():
        from filelock import FileLock
        preview.parent.mkdir(exist_ok=True)
        with FileLock(str(preview)+'.lock', timeout=35):
            if not preview.is_file():
                executable = shutil.which('pdftocairo')
                if executable is None: return _json(503, {'error':'PDF preview renderer unavailable'})
                snapshot = preview.with_suffix('.pdf')
                snapshot.write_bytes(data)
                try:
                    rendered = subprocess.run([executable,'-png','-singlefile','-f','1','-l','1',
                        '-scale-to','1100',str(snapshot),str(preview.with_suffix(''))],
                        capture_output=True,timeout=30)
                    if rendered.returncode or not preview.is_file():
                        return _json(422, {'error':'PDF preview could not be rendered'})
                finally: snapshot.unlink(missing_ok=True)
    return 200, 'image/png', preview.read_bytes()


def _npz_read(read: ReadTarget, query: dict, pinned_data: bytes | None) -> tuple:
    """An NPZ download, or its bounded, searchable JSON projection page."""
    _q1, _json, target = q1, json_reply, read.target
    if _q1(query,'download')=='1':return 200,'application/octet-stream',(pinned_data if pinned_data is not None else target.read_bytes())
    try:projection=_npz_projection(target)
    except (OSError,ValueError,zipfile.BadZipFile) as exc:
        return _json(422,{'error':str(exc)})
    content=projection['content'];search=_q1(query,'q')
    if search:content='\n'.join(line for line in content.splitlines() if search.casefold() in line.casefold())
    try:
        offset=max(0,int(_q1(query,'offset') or '0'))
        limit=min(65536,max(1,int(_q1(query,'limit') or '12000')))
    except ValueError:return _json(422,{'error':'offset and limit must be integers'})
    end=min(len(content),offset+limit)
    return _json(200,{**projection,'path':read.raw,'scope':read.scope,'sha256':hashlib.sha256((pinned_data if pinned_data is not None else target.read_bytes())).hexdigest(),
        'content':content[offset:end],'offset':offset,'total_chars':len(content),'filtered':bool(search),
        'next_offset':end if end<len(content) else None})


def _text_read(read: ReadTarget, query: dict, data: bytes) -> tuple:
    """A text artifact: download, plain text (64 KiB, never truncated), or a paged JSON read with support."""
    _q1, _json = q1, json_reply
    project, scope, raw, target = read.project, read.scope, read.raw, read.target
    if _q1(query, 'download') == '1':
        return 200, 'application/octet-stream', data
    if _q1(query, 'format') != 'json':
        if len(data) > 65536:
            from urllib.parse import urlencode
            params = {'project': project, 'scope': scope, 'path': raw}
            # Recovery continues THIS admitted read, not a generic/current one.
            # Do not invent an owner or pin for an unpinned legacy request.
            if _q1(query, 'owner'):
                params['owner'] = _q1(query, 'owner')
            if read.artifact_id:
                params['artifact_id'] = read.artifact_id
            if read.expected:
                params['expected_sha256'] = read.expected
            return _json(413, {'error': 'Artifact exceeds the plain-text limit. Use the paged inspector or download the complete file; no truncated text was returned.',
                'next_read': '/research/artifact?' + urlencode({**params, 'format': 'json', 'offset': 0, 'limit': 65536}),
                'download': '/research/artifact?' + urlencode({**params, 'download': 1})})
        return 200, 'text/plain; charset=utf-8', data
    try:
        offset = max(0, int(_q1(query, 'offset') or '0'))
        limit = min(65536, max(1, int(_q1(query, 'limit') or '12000')))
    except ValueError:
        return _json(422, {'error':'offset and limit must be integers'})
    content = data.decode('utf-8', errors='replace')
    search = _q1(query, 'q')
    if search:
        content = '\n'.join(f'{i}: {line}' for i, line in enumerate(content.splitlines(), 1)
                            if search.casefold() in line.casefold())
    end = min(len(content), offset + limit)
    from laplace.manuscript import project_protocol
    guide_support=project_protocol.support_for_path(project,target,read.root,
        content=data.decode('utf-8',errors='replace'),historical=bool(read.artifact_id) and not read.receipt_unpinned,read_context={})
    artifact_record = read.artifact_record
    return _json(200, {**({'engineering_support':guide_support} if guide_support is not None else {}),
                       **({'receipt_identity':'unavailable'} if read.receipt_unpinned else {}),  # current bytes, not the receipt's revision
                       **({'custody_degradation':artifact_record['custody_degradation']}
                          if read.artifact_id and isinstance(artifact_record.get('custody_degradation'),dict) else {}),
                       'path':raw, 'scope':scope, 'download_available':True, 'content':content[offset:end],
                       'sha256':hashlib.sha256(data).hexdigest(), 'bytes':len(data),
                       'offset':offset, 'total_chars':len(content), 'filtered':bool(search),
                       'next_offset':end if end < len(content) else None})


from laplace.research import research_observation  # noqa: E402  (cycle-safe: imported last)
