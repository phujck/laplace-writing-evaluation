"""Read-only, repo-scoped snapshots of inputs consumed by a TeX build."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterable

_INPUT_SUFFIXES = {".tex", ".bib", ".sty", ".cls", ".bst",
                   ".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg",
                   ".tikz", ".pgf"}
_TEX_INPUT = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")
_BIB_INPUT = re.compile(r"\\(?:bibliography|addbibresource)\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}")
_GRAPHIC_INPUT = re.compile(r"\\includegraphics\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}")
_GRAPHIC_PATH = re.compile(r"\\graphicspath\s*\{((?:\s*\{[^{}]*\}\s*)+)\}")
_GRAPHIC_DIR = re.compile(r"\{([^{}]+)\}")
_PACKAGE_INPUT = re.compile(r"\\usepackage\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}")
_STYLE_INPUT = re.compile(r"\\bibliographystyle\s*\{([^}]+)\}")
_CLASS_INPUT = re.compile(r"\\documentclass\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}")
_FIGURE_SUFFIXES = (".pdf", ".png", ".jpg", ".jpeg", ".eps", ".svg")

_OVERLAY_TEXT_SUFFIXES = {'.tex', '.cls', '.sty', '.tikz', '.pgf'}
_OVERLAY_MAX_FILES = 2048
_OVERLAY_MAX_BYTES = 256 * 1024 * 1024
_OVERLAY_PACKAGE = re.compile(r'\\(?:usepackage|RequirePackage|RequirePackageWithOptions)\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}')
_OVERLAY_CLASS = re.compile(r'\\(?:documentclass|LoadClass|LoadClassWithOptions)\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}')
_OVERLAY_OPTIONAL = re.compile(r'\\(?:InputIfFileExists|IfFileExists)\s*\{([^}]+)\}')
_OVERLAY_UNBRACED_INPUT = re.compile(r'\\input\s+([^\s{}%\\]+)')


def _closure_digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def _file_identity(path, *, text=False):
    """Hash one regular observed file; retain only bounded parseable text."""
    with path.open('rb') as stream:
        before=os.fstat(stream.fileno());digest=hashlib.sha256();parts=[];size=0
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            size+=len(chunk);digest.update(chunk)
            if text and size<=2_000_000:parts.append(chunk)
        after=os.fstat(stream.fileno())
    current=path.stat();keys=('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')
    if any(getattr(before,key)!=getattr(after,key) or getattr(after,key)!=getattr(current,key) for key in keys):
        raise ValueError('CHANGED_INPUT: dependency changed during observation: '+str(path))
    content=b''.join(parts).decode('utf-8') if text and size<=2_000_000 else None
    return 'sha256:'+digest.hexdigest(),size,content


def prepare_closure(project, root, source, overrides, template_sources=()):
    """Discover proposed declarations, never an old recorder or an entire tree.

    Paths remain repository-relative, including witnessed aliases. Missing and
    dynamic declarations are explicit; installed TeX requests remain separate
    from local closure. Actual compiler observations can supplement this static
    declaration proof without rewriting it.
    """
    root=Path(root).resolve();source_root=source.get('root')
    if not isinstance(source_root,str):raise ValueError('Candidate closure needs the original exact selected root.')
    def lexical(value):
        path=Path(value)
        if path.is_absolute():raise ValueError('Dependency paths must be repository-relative.')
        path=Path(os.path.abspath(root/path))
        if not path.is_relative_to(root):raise ValueError('Dependency path escapes its repository.')
        return path
    first=lexical(source_root);compile_dir=first.parent
    overlay={lexical(name).relative_to(root).as_posix():value for name,value in overrides.items()}
    if any(not isinstance(value,str) for value in overlay.values()):raise ValueError('Proposed TeX overlays require exact text.')
    members={};basis={};aliases={};absences=set();diagnostics=[];system=[];queue=[(first,'root')];graphics=[];total=0
    def diagnostic(code,**values):
        row={'code':code,**values}
        if row not in diagnostics:diagnostics.append(row)
    def find(argument,current,suffixes,role,*,optional=False,installed=False):
        if not argument.strip() or any(char in argument for char in ('\\','#','{','}','$')):
            diagnostic('DYNAMIC_DECLARATION',source=current.relative_to(root).as_posix(),role=role,argument=argument);return
        if role=='include':   # the shared TeX include contract (tex_input): the compilation directory only
            found=tex_input(argument,including=current,compile_dir=compile_dir,fence=root)
            source_name=current.relative_to(root).as_posix()
            if found['status']=='unsafe':diagnostic('ESCAPING_DECLARATION',argument=argument,role=role);return
            candidate=found['path'];name=candidate.relative_to(root).as_posix()
            if found['status']=='ambiguous':
                diagnostic('AMBIGUOUS_DECLARATION',source=source_name,role=role,argument=argument,path=name,
                           alternate=found['alternate'].relative_to(root).as_posix());return
            if found['status']=='resolved' or name in overlay:queue.append((candidate,role));return
            absences.add(name)
            if not optional:diagnostic('MISSING_DECLARATION',source=source_name,role=role,argument=argument,paths=[name],
                **({'including_relative':found['alternate'].relative_to(root).as_posix()} if found['alternate'] else {}))
            return
        raw=Path(argument.strip().strip('"'));variants=('',) if raw.suffix else suffixes
        if raw.is_absolute():diagnostic('ESCAPING_DECLARATION',argument=argument,role=role);return
        candidates=[]
        for parent in dict.fromkeys((compile_dir,current.parent,*graphics)):
            for suffix in variants:
                candidate=Path(os.path.abspath(parent/(str(raw)+suffix)))
                if not candidate.is_relative_to(root):
                    diagnostic('ESCAPING_DECLARATION',argument=argument,role=role);continue
                candidates.append(candidate)
                name=candidate.relative_to(root).as_posix()
                if candidate.is_file() or name in overlay:
                    queue.append((candidate,role));return
                absences.add(name)
        if installed and raw.parent==Path('.'):
            row={'role':role,'name':argument,'status':'INSTALLED_TEX_REQUEST_UNVERIFIED'}
            if row not in system:system.append(row)
        elif not optional:diagnostic('MISSING_DECLARATION',source=current.relative_to(root).as_posix(),role=role,argument=argument,paths=[p.relative_to(root).as_posix() for p in candidates])
    while queue:
        path,role=queue.pop(0);name=path.relative_to(root).as_posix()
        if name in members:
            if role not in members[name]['roles']:members[name]['roles'].append(role)
            continue
        if len(members)>=_OVERLAY_MAX_FILES:diagnostic('CLOSURE_FILE_BOUND',limit=_OVERLAY_MAX_FILES);break
        target=path.resolve()
        if not target.is_relative_to(root):diagnostic('ESCAPING_ALIAS',path=name);continue
        if not target.is_file():diagnostic('MISSING_LOCAL_INPUT',path=name);continue
        target_name=target.relative_to(root).as_posix()
        for count in range(1,len(path.relative_to(root).parts)+1):
            prefix=root/Path(*path.relative_to(root).parts[:count])
            if prefix.is_symlink():aliases[prefix.relative_to(root).as_posix()]=os.readlink(prefix)
        try:before,size,text=_file_identity(target,text=path.suffix.lower() in _OVERLAY_TEXT_SUFFIXES)
        except (OSError,UnicodeError) as error:diagnostic('UNREADABLE_INPUT',path=name,error=str(error));continue
        basis[target_name]=before
        proposed=overlay.get(name,overlay.get(target_name))
        if proposed is not None:text=proposed;size=len(proposed.encode());pin='sha256:'+hashlib.sha256(proposed.encode()).hexdigest()
        else:pin=before
        total+=size
        if total>_OVERLAY_MAX_BYTES:diagnostic('CLOSURE_BYTE_BOUND',limit=_OVERLAY_MAX_BYTES);break
        members[name]={'path':name,'canonical_path':target_name,'content_revision':pin,'original_revision':before,
            'bytes':size,'roles':[role],'overlay':proposed is not None}
        if target_name!=name:queue.append((target,'alias-target'))
        if path.suffix.lower() not in _OVERLAY_TEXT_SUFFIXES:continue
        if text is None:diagnostic('PARSE_TEXT_BOUND',path=name,limit=2_000_000);continue
        text=_uncomment(text)
        for match in _GRAPHIC_PATH.finditer(text):
            for value in _GRAPHIC_DIR.findall(match.group(1)):
                if any(char in value for char in ('\\','#','$')):
                    diagnostic('DYNAMIC_DECLARATION',source=name,role='graphic-path',argument=value);continue
                for parent in (compile_dir,path.parent):
                    directory=Path(os.path.abspath(parent/value.strip()))
                    if directory.is_relative_to(root) and directory not in graphics:graphics.append(directory)
                    elif not directory.is_relative_to(root):diagnostic('ESCAPING_GRAPHIC_PATH',path=name,argument=value)
        for pattern,suffixes,kind,installed in [(_TEX_INPUT,('.tex',),'include',False),(_BIB_INPUT,('.bib',),'bibliography',False),
                (_GRAPHIC_INPUT,_FIGURE_SUFFIXES,'graphic',False),(_OVERLAY_PACKAGE,('.sty',),'package',True),
                (_OVERLAY_CLASS,('.cls',),'class',True),(_STYLE_INPUT,('.bst',),'bibliography-style',True)]:
            for match in pattern.finditer(text):
                values=match.group(1).split(',') if kind in {'package','bibliography'} else [match.group(1)]
                for value in values:find(value.strip(),path,suffixes,kind,installed=installed)
        for match in _OVERLAY_OPTIONAL.finditer(text):find(match.group(1),path,('', '.tex'),'conditional',optional=True,installed=True)
        for match in _OVERLAY_UNBRACED_INPUT.finditer(text):find(match.group(1),path,('.tex',),'include')
        if re.search(r'\\(?:import|subimport|includefrom|subincludefrom)\b',text):
            diagnostic('UNRESOLVED_IMPORT_DECLARATION',source=name)
        if re.search(r'\\(?:input|include|usepackage|RequirePackage|documentclass|LoadClass|includegraphics)\s*\\',text):
            diagnostic('DYNAMIC_DECLARATION',source=name,role='unresolved-command')
    material=[]
    for item in template_sources:
        content=item.get('content');pin=item.get('sha256')
        if not isinstance(content,str) or pin!='sha256:'+hashlib.sha256(content.encode()).hexdigest():
            raise ValueError('Template witness bytes differ from their exact retained identity.')
        matched=[name for name,row in members.items() if row['content_revision']==pin]
        path=item.get('path')
        if path is not None and lexical(path).relative_to(root).as_posix() not in matched:
            diagnostic('TEMPLATE_INPUT_NOT_CONSUMED',path=path)
        if path is None and not matched:diagnostic('UNBOUND_ARCHIVE_TEMPLATE_MEMBER',source=item.get('source'))
        material.append({'path':path,'source':item.get('source'),'content_revision':pin,'matched_paths':matched})
    value={'schema_version':'laplace.tex-overlay-closure/1','project':project,'root':source_root,
        'selection_identity':source.get('selection_identity'),'status':'UNPROVED' if diagnostics else 'COMPLETE',
        'members':sorted(members.values(),key=lambda row:row['path']),'basis':dict(sorted(basis.items())),
        'aliases':dict(sorted(aliases.items())),'absences':sorted(absences-set(members)),
        'installed_requests':system,'template_witnesses':material,'diagnostics':diagnostics,
        'local_bytes':sum(row['bytes'] for row in members.values())}
    value['input_revision']=_closure_digest(value)
    value['revision']=value['input_revision']
    value['pins']={name:pin.removeprefix('sha256:') for name,pin in value['basis'].items()}
    value['counts']={'members':len(value['members']),'local_bytes':value['local_bytes']}
    return value


def closure_changes(closure, root, *, ignore_files=()):
    """Reobserve only the sealed local basis, aliases and absence witnesses."""
    root=Path(root).resolve();changed=[];ignored={str(name) for name in ignore_files}
    ignored.update((root/name).resolve().relative_to(root).as_posix() for name in list(ignored) if (root/name).resolve().is_relative_to(root))
    for name,pin in closure['basis'].items():
        if name in ignored:continue
        path=root/name
        if not path.is_file() or not path.resolve().is_relative_to(root) or _file_identity(path)[0]!=pin:changed.append('file:'+name)
    for member in closure['members']:
        if (root/member['path']).resolve()!=root/member['canonical_path']:changed.append('membership:'+member['path'])
    for name,target in closure.get('aliases',{}).items():
        path=root/name
        if not path.is_symlink() or os.readlink(path)!=target:changed.append('alias:'+name)
    for name in closure.get('absences',[]):
        if (root/name).exists() or (root/name).is_symlink():changed.append('absence:'+name)
    return sorted(changed)


def graphic_references(root_tex: Path | str, repo_root: Path | str) -> list[dict]:
    """Exact declared graphics of the selected source tree, including imports.

    Research state may live separately from an imported manuscript. It is not
    the trust boundary for that manuscript's explicitly declared image inputs.
    No repository-wide filename search or basename substitution is performed.
    """
    from laplace.manuscript import manuscript_source
    root, repo = Path(root_tex).resolve(), Path(repo_root).resolve()
    if not _inside(root, repo):
        return []
    tree = manuscript_source.traversal(root, repo_root=repo)
    sources = tree.get('sources') or []
    directories = []
    for source in sources:
        for match in _GRAPHIC_PATH.finditer(_uncomment(source.get('text') or '')):
            for value in _GRAPHIC_DIR.findall(match.group(1)):
                directory = (root.parent / value.strip()).resolve()
                if _inside(directory, repo):
                    directories.append(directory)
    result = []
    for source in sources:
        current = repo / source['file']
        for match in _GRAPHIC_INPUT.finditer(_uncomment(source.get('text') or '')):
            argument = match.group(1).strip()
            # TeX is compiled from the root document's directory. A local input
            # directory is considered only when the root declaration has no hit.
            target = _candidate(argument, root, root.parent, _FIGURE_SUFFIXES, directories)
            if target is None:
                target = _candidate(argument, current, root.parent, _FIGURE_SUFFIXES, directories)
            allowed = target is not None and _inside(target, repo) and target.suffix.lower() in _FIGURE_SUFFIXES
            result.append({'source': source['file'], 'argument': argument,
                           'repo_file': target.relative_to(repo).as_posix() if allowed else None,
                           'status': 'AVAILABLE' if allowed else 'UNRESOLVED'})
    return result


def _uncomment(text: str) -> str:
    lines = []
    for line in text.splitlines():
        cut = len(line)
        for index, char in enumerate(line):
            if char == "%" and (index == 0 or line[index - 1] != "\\"):
                cut = index
                break
        lines.append(line[:cut])
    return "\n".join(lines)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def tex_input(argument: str, *, including: Path, compile_dir: Path, fence: Path) -> dict:
    """THE \\input/\\include path contract, shared by source traversal (membership guards and outline) and the
    build closure (WORK-editor-tex-include-resolution-20261016).

    TeX runs in the compilation directory (the selected root's directory) and resolves a relative \\input or
    \\include argument against it, appending ``.tex`` when the argument has no suffix; the including file's own
    directory is not searched. Returns {"status", "path", "alternate"}:
      resolved   ``path`` is the compilation-directory file;
      ambiguous  a different file also exists at the including-file-relative spelling (``alternate``): which one an
                 author meant is not decidable, so it is refused rather than guessed (identical bytes are not
                 ambiguous);
      missing    nothing at the compilation-directory path; ``alternate`` names an including-relative file TeX
                 would not read, as a hint;
      unsafe     absolute, ``..`` or outside ``fence``, lexically OR once symlinks resolve.

    Both the target and any alternate are fenced on their RESOLVED path before anything is stat'ed or read, so a
    symlinked file or directory pointing outside the fence is refused without touching outside bytes; a symlink that
    stays inside the fence remains a usable alias (repair1 WR-R6).
    """
    raw = Path(argument.strip().strip('"'))
    if not argument.strip() or raw.is_absolute() or ".." in raw.parts:
        return {"status": "unsafe", "path": None, "alternate": None}
    name = raw if raw.suffix else raw.with_suffix(".tex")
    target = Path(os.path.abspath(compile_dir / name))
    if not target.is_relative_to(fence) or not _inside(target, fence):
        return {"status": "unsafe", "path": None, "alternate": None}
    other = Path(os.path.abspath(including.parent / name)) if including.parent != compile_dir else None
    other = (other if other is not None and other.is_relative_to(fence) and _inside(other, fence) and other.is_file()
             else None)
    if not target.is_file():
        return {"status": "missing", "path": target, "alternate": other}
    if other is not None and other.resolve() != target.resolve():
        try:
            same = other.read_bytes() == target.read_bytes()
        except OSError:
            same = False
        if not same:
            return {"status": "ambiguous", "path": target, "alternate": other}
    return {"status": "resolved", "path": target, "alternate": None}


def _candidate(value: str, current: Path, compile_dir: Path,
               suffixes: tuple[str, ...], extra_dirs: Iterable[Path] = ()) -> Path | None:
    raw = Path(value.strip().strip('"'))
    variants = (suffixes if not raw.suffix else ("",))
    for parent in dict.fromkeys((current.parent, compile_dir, *extra_dirs)):
        for suffix in variants:
            candidate = (parent / (str(raw) + suffix)).resolve()
            if candidate.is_file():
                return candidate
    return None


def _candidate_alias(value: str, current: Path, compile_dir: Path,
                     suffixes: tuple[str, ...], extra_dirs: Iterable[Path] = ()) -> tuple[Path, Path] | None:
    raw = Path(value.strip().strip('"'))
    variants = (suffixes if not raw.suffix else ("",))
    for parent in dict.fromkeys((current.parent, compile_dir, *extra_dirs)):
        for suffix in variants:
            alias = Path(os.path.abspath(parent / (str(raw) + suffix)))
            if alias.is_file():
                return alias, alias.resolve()
    return None


def declared_aliases(root_tex: Path | str, repo_root: Path | str) -> dict[Path, Path]:
    """Return declared input aliases whose symlinks resolve to another repo path."""
    repo, root = Path(repo_root).resolve(), Path(root_tex).resolve()
    if not root.is_file() or not _inside(root, repo):
        return {}
    aliases: dict[Path, Path] = {}
    queue, seen, global_graphics = [root], set(), []
    try:
        root_text = _uncomment(root.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        root_text = ""
    for match in _GRAPHIC_PATH.finditer(root_text):
        global_graphics.extend(Path(os.path.abspath(root.parent / value.strip()))
                               for value in _GRAPHIC_DIR.findall(match.group(1)))

    def remember(found):
        if found is None:
            return None
        alias, target = found
        if _inside(alias, repo) and _inside(target, repo) and alias != target:
            aliases[alias] = target
        return target

    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        try:
            text = _uncomment(current.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        graphic_dirs = list(global_graphics)
        for match in _GRAPHIC_PATH.finditer(text):
            for value in _GRAPHIC_DIR.findall(match.group(1)):
                graphic_dirs.extend([Path(os.path.abspath(current.parent / value.strip())),
                                     Path(os.path.abspath(root.parent / value.strip()))])
        for match in _TEX_INPUT.finditer(text):
            found = tex_input(match.group(1), including=current, compile_dir=root.parent, fence=repo)
            if found["status"] == "resolved":
                target = remember((found["path"], found["path"].resolve()))
                if target is not None:
                    queue.append(target)
        for match in _BIB_INPUT.finditer(text):
            for value in match.group(1).split(","):
                remember(_candidate_alias(value, current, root.parent, (".bib",)))
        for match in _GRAPHIC_INPUT.finditer(text):
            remember(_candidate_alias(match.group(1), current, root.parent,
                                      _FIGURE_SUFFIXES, graphic_dirs))
        for match in _PACKAGE_INPUT.finditer(text):
            for value in match.group(1).split(","):
                remember(_candidate_alias(value, current, root.parent, (".sty",)))
        for match in _CLASS_INPUT.finditer(text):
            remember(_candidate_alias(match.group(1), current, root.parent, (".cls",)))
    return aliases


def _fls_inputs(root_tex: Path, repo_root: Path, fls_path: Path | None = None) -> set[Path]:
    path = fls_path or root_tex.with_suffix(".fls")
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return set()
    found: set[Path] = set()
    for line in lines:
        if not line.startswith("INPUT "):
            continue
        raw = line[6:].strip().strip('"')
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root_tex.parent / candidate
        try:
            candidate = candidate.resolve()
        except OSError:
            continue
        if (candidate.is_file() and _inside(candidate, repo_root)
                and candidate.suffix.lower() in _INPUT_SUFFIXES
                and candidate != root_tex.with_suffix(".pdf").resolve()):
            found.add(candidate)
    return found


def dependency_paths(root_tex: Path | str, repo_root: Path | str,
                     *, fls_path: Path | None = None, use_recorder: bool = True) -> set[Path]:
    """Return existing repo-owned TeX, bibliography, style, and figure inputs.

    Recorder output is authoritative when present.  Direct declarations remain
    additive because BibTeX inputs are not reliably listed by every driver and
    they provide a safe pre-compile snapshot before a first ``.fls`` exists.
    """
    repo = Path(repo_root).resolve()
    root = Path(root_tex).resolve()
    if not root.is_file() or not _inside(root, repo):
        return set()
    recorded = _fls_inputs(root, repo, fls_path) if use_recorder else set()
    found = {root} | recorded
    # A recorder file names the TeX files actually opened, including conditional
    # includes.  Before the first build, fall back to the declared TeX graph so
    # root and bibliography changes can still be guarded.
    queue = sorted((path for path in recorded if path.suffix.lower() == ".tex"), key=str) or [root]
    if root not in queue:
        queue.insert(0, root)
    seen = set()
    try:
        root_text = _uncomment(root.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        root_text = ""
    graphic_dirs = []
    for match in _GRAPHIC_PATH.finditer(root_text):
        for value in _GRAPHIC_DIR.findall(match.group(1)):
            raw = Path(value.strip())
            graphic_dirs.append((root.parent / raw).resolve())
    while queue:
        current = queue.pop(0).resolve()
        if current in seen or not current.is_file() or not _inside(current, repo):
            continue
        seen.add(current); found.add(current)
        try:
            text = _uncomment(current.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        local_graphic_dirs = list(graphic_dirs)
        for match in _GRAPHIC_PATH.finditer(text):
            for value in _GRAPHIC_DIR.findall(match.group(1)):
                raw = Path(value.strip())
                local_graphic_dirs.extend([(current.parent / raw).resolve(),
                                           (root.parent / raw).resolve()])
        if not recorded:
            for match in _TEX_INPUT.finditer(text):
                child = _candidate(match.group(1), current, root.parent, (".tex",))
                if child is not None and _inside(child, repo):
                    found.add(child); queue.append(child)
        for match in _BIB_INPUT.finditer(text):
            for value in match.group(1).split(","):
                child = _candidate(value, current, root.parent, (".bib",))
                if child is not None and _inside(child, repo):
                    found.add(child)
        for match in _STYLE_INPUT.finditer(text):
            child = _candidate(match.group(1), current, root.parent, (".bst",))
            if child is not None and _inside(child, repo):
                found.add(child)
        if not recorded:
            for match in _GRAPHIC_INPUT.finditer(text):
                child = _candidate(match.group(1), current, root.parent,
                                   _FIGURE_SUFFIXES, local_graphic_dirs)
                if child is not None and _inside(child, repo):
                    found.add(child)
            for match in _PACKAGE_INPUT.finditer(text):
                for value in match.group(1).split(","):
                    child = _candidate(value, current, root.parent, (".sty",))
                    if child is not None and _inside(child, repo):
                        found.add(child)
            for match in _CLASS_INPUT.finditer(text):
                child = _candidate(match.group(1), current, root.parent, (".cls",))
                if child is not None and _inside(child, repo):
                    found.add(child)
    return {path for path in found if path.suffix.lower() in _INPUT_SUFFIXES
            and path != root.with_suffix(".pdf").resolve()}


def snapshot_paths(paths: Iterable[Path | str], repo_root: Path | str) -> dict[str, str | None]:
    """Hash exact paths, retaining a missing marker for deletion detection."""
    repo = Path(repo_root).resolve()
    result: dict[str, str | None] = {}
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute():
            path = repo / path
        try:
            path = path.resolve()
            relative = path.relative_to(repo).as_posix()
        except (OSError, ValueError):
            continue
        try:
            result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            result[relative] = None
    return dict(sorted(result.items()))


def snapshot(root_tex: Path | str, repo_root: Path | str,
             *, fls_path: Path | None = None, use_recorder: bool = True) -> dict[str, str | None]:
    return snapshot_paths(dependency_paths(root_tex, repo_root, fls_path=fls_path,
                                          use_recorder=use_recorder), repo_root)


def changed(expected: dict[str, str | None], repo_root: Path | str) -> list[str]:
    """List exact receipt paths whose current bytes differ or disappeared."""
    current = snapshot_paths(expected, repo_root)
    return sorted(path for path, digest in expected.items() if current.get(path) != digest)


def modified_since(paths: Iterable[Path | str], repo_root: Path | str,
                   timestamp_ns: int, finished_ns: int | None = None) -> list[str]:
    """Return receipt paths written during a bounded build interval."""
    repo = Path(repo_root).resolve()
    changed_paths = []
    for raw in paths:
        path = Path(raw)
        if not path.is_absolute():
            path = repo / path
        try:
            resolved = path.resolve()
            relative = resolved.relative_to(repo).as_posix()
            modified = resolved.stat().st_mtime_ns
            if modified >= timestamp_ns and (finished_ns is None or modified <= finished_ns):
                changed_paths.append(relative)
        except (OSError, ValueError):
            continue
    return sorted(set(changed_paths))
