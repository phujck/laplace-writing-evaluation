"""Explicit manuscript source selection and recursive TeX source traversal.

The registry names an edition when a project has more than one TeX tree.  This
module is deliberately the only fallback policy: consumers receive the selected
root and an ordered include expansion, never an attractive-looking file chosen
by mtime or byte count.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import math
import os
import threading
import time
import weakref
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_INPUT_RE = re.compile(r"\\(?:input|include)\s*\{\s*([^}]+?)\s*\}")
_DOC_RE = re.compile(r"\\documentclass\b")
_SELECTION_FILE = "document_selection.json"
# First line of a publication-edition wrapper (writing.publication_editions). The wrapper is
# derived build input beside the selected root, never a selectable source candidate.
EDITION_WRAPPER_MARKER = "% laplace.publication-edition/1"


def edition_wrapper(text: str) -> bool:
    return text.startswith(EDITION_WRAPPER_MARKER)


class SourceLeaseError(RuntimeError):
    """A cooperating source mutation cannot acquire its declared scope."""


class SourceLeaseTimeout(SourceLeaseError):
    """The total source-acquisition deadline expired; no partial lease survives."""


def stage_source(path: Path | str, data: bytes, *, suffix: str = ".pending") -> Path:
    """Stage exact bytes in one private sibling, preserving existing file mode.

    This does not publish or admit a write. The original owner retains its
    source lease, fresh guard, attribution ordering, replace and compensation.
    """
    import stat
    if not isinstance(data, bytes):
        raise TypeError("source staging requires exact bytes")
    path = Path(path)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix="." + path.name + ".", suffix=suffix)
    staged = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as handle:
            if mode is not None:
                os.chmod(staged, mode)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return staged
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class SourceLease:
    paths: tuple[Path, ...]
    outermost: bool


_SOURCE_LOCKS = weakref.WeakValueDictionary()
_SOURCE_LOCKS_GUARD = threading.Lock()
_SOURCE_HELD = threading.local()


def source_mutation_active() -> bool:
    """Whether this thread has an enclosing physical-source lease."""
    return bool(getattr(_SOURCE_HELD, "paths", ()))


@contextmanager
def source_mutation(paths, *, timeout: float = 15.0):
    """Lease a complete physical effect/rollback set before reading its guards.

    Resolved, platform-normalized paths acquire FileLocks in deterministic order.
    Existing same-thread leases permit subsets only, never late set growth. The
    one deadline covers every acquisition, and partial acquisition releases on
    failure. Live weak lock instances supply FileLock's thread-local reentrancy;
    no request/witness registry or persisted authority is introduced.

    Callers retain their source fences and optimistic byte guards. Parents must
    already exist (including for declared new files). Hold through attribution
    and required rollback, never model/render/build work. Sidecars are transient
    ``*.lock`` files. External writers and distinct hardlinks are not serialized.
    """
    from filelock import FileLock, Timeout

    if isinstance(paths, (str, Path)):
        raise ValueError("source_mutation requires a complete iterable of paths")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
        raise ValueError("source lease timeout must be finite and nonnegative")
    resolved = {}
    for value in paths:
        path = Path(value).resolve()
        resolved.setdefault(os.path.normcase(str(path)), path)
    canonical = tuple(resolved[key] for key in sorted(resolved))
    if not canonical:
        raise ValueError("source lease requires at least one path")
    if any(not path.parent.is_dir() for path in canonical):
        raise SourceLeaseError("source lease requires existing parent directories")
    held = getattr(_SOURCE_HELD, "paths", ())
    if held and not set(resolved).issubset({os.path.normcase(str(path)) for path in held}):
        raise SourceLeaseError("nested source lease cannot grow the enclosing physical set")
    deadline = time.monotonic() + timeout
    if held:
        deadline = min(deadline, _SOURCE_HELD.deadline)
    # Retain strong references across acquisition and use; only live instances
    # remain in the lookup. This prevents two threads creating distinct local
    # instances during first use, while unrelated files never share a wait lock.
    locks = []
    with _SOURCE_LOCKS_GUARD:
        for path in canonical:
            key = os.path.normcase(str(path))
            lock = _SOURCE_LOCKS.get(key)
            if lock is None:
                lock = FileLock(str(path.with_name("." + path.name + ".source.lock")))
                _SOURCE_LOCKS[key] = lock
            locks.append(lock)
    old_deadline = getattr(_SOURCE_HELD, "deadline", None)
    with ExitStack() as stack:
        try:
            for lock in locks:
                stack.enter_context(lock.acquire(timeout=max(0.0, deadline - time.monotonic()), poll_interval=0.01))
        except Timeout as exc:
            raise SourceLeaseTimeout("physical source lease acquisition timed out") from exc
        _SOURCE_HELD.paths = held or canonical
        _SOURCE_HELD.deadline = deadline
        try:
            yield SourceLease(canonical, not bool(held))
        finally:
            _SOURCE_HELD.paths = held
            _SOURCE_HELD.deadline = old_deadline


def _root(repo_root: Path | str | None) -> Path:
    if repo_root is not None:
        return Path(repo_root).resolve()
    from laplace.pipeline import registry
    return registry._repo_root().resolve()  # one registry root, also useful to fixtures


def source_path(root: Path, manuscript: Path, value: object) -> Path:
    """Normalize existing repository/manuscript coordinates with a manuscript fence.

    Preserve repository-first existing-file precedence. Callers still enforce
    selected traversal membership, editability, exact source guards and leases.
    """
    raw = Path(str(value or ""))
    if raw.is_absolute() or ".." in raw.parts or not raw.parts:
        raise ValueError("source_file must identify a TeX file in the selected manuscript")
    candidates = [(root / raw).resolve(), (manuscript / raw).resolve()]
    source_file = next((candidate for candidate in candidates if candidate.is_file()), candidates[0])
    try:
        source_file.relative_to(manuscript)
    except ValueError as exc:
        raise ValueError("section source escapes the selected manuscript") from exc
    return source_file


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return str(path)


def _under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def _uncomment(text: str) -> str:
    """Drop TeX comments while retaining an escaped percent sign."""
    out: list[str] = []
    for line in text.splitlines():
        cut = len(line)
        for i, char in enumerate(line):
            if char == "%" and (i == 0 or line[i - 1] != "\\"):
                cut = i
                break
        out.append(line[:cut])
    return "\n".join(out)


def _substantive(path: Path) -> bool:
    try:
        text = _uncomment(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return False
    begin = re.search(r"\\begin\s*\{document\}", text)
    end = re.search(r"\\end\s*\{document\}", text)
    # A scaffold is allowed to have a title, a document environment, and a
    # maketitle.  None of those make a manuscript readable.  For incomplete
    # sources (common during authoring), retain the non-preamble tail instead.
    if begin:
        text = text[begin.end():end.start() if end and end.start() > begin.end() else None]
    text = re.sub(r"\\(?:maketitle|tableofcontents|listoffigures|listoftables|"
                  r"bibliography|printbibliography|addbibresource|bibliographystyle)\b[^\n]*", "", text)
    text = re.sub(r"\\(?:documentclass|usepackage|title|author|date|begin|end)\b[^\n]*", "", text)
    return bool(re.search(r"[A-Za-z]{3,}", text)) or bool(_INPUT_RE.search(text))


def is_substantive(path: Path | str) -> bool:
    """Public content check used to avoid serving a successful empty scaffold."""
    return _substantive(Path(path))


def _candidate_rows(manuscript_dir: Path, root: Path) -> list[dict[str, Any]]:
    if not manuscript_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    excluded = {"editor_saves", "versions", "figures", "figures_tex", "_audit_S2", "_audit_S3", "_audit_S4",
                "_audit_S4A", "_audit_S4B", "_audit_S5", "_check_C", "_check_S2",
                "_check_S3", "_check_S4", "_check_S4A", "_check_S4B", "_check_S5"}
    for path in sorted(manuscript_dir.rglob("*.tex")):
        if any(part in excluded or part.startswith("_audit_") or part.startswith("_check_")
               for part in path.relative_to(manuscript_dir).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if edition_wrapper(text):
            continue
        source = _uncomment(text)
        if _DOC_RE.search(source) and re.search(r"\\begin\s*\{document\}", source):
            rows.append({"root": _rel(path, root), "substantive": _substantive(path)})
    return rows


def _configured_root(document: dict[str, Any], manuscript_dir: Path, root: Path) -> Path | None:
    value = document.get("root") or document.get("source")
    if not isinstance(value, str) or not value.strip():
        return None
    raw = Path(value)
    path = raw if raw.is_absolute() else root / raw
    # ``root: main.tex`` is intentionally relative to the declared manuscript
    # directory, while a repo-relative root remains unambiguous.
    if not raw.is_absolute() and not path.exists():
        path = manuscript_dir / raw
    return path.resolve()


def _selection_path(proj, root: Path) -> Path | None:
    """The project-owned persisted edition choice; foreign projects are read-only."""
    document = proj.manifest.get("document", {}) if isinstance(proj.manifest, dict) else {}
    if proj.external_root or bool(document.get("read_only")) or not proj.manuscript_dir:
        return None
    base = proj.path(proj.manuscript_dir, root)
    return base / _SELECTION_FILE if base is not None else None


def _state_dir(document: dict[str, Any], manuscript_dir: Path, root: Path) -> Path | None:
    """Where engine-owned state belongs for a read-only source.

    An imported manuscript may be inside the checkout yet remain author-owned.
    Its selected source stays at ``manuscript_dir`` while ``state_dir`` directs
    selection/authoring receipts to a separately declared engine directory.
    """
    raw = document.get("state_dir")
    if not isinstance(raw, str) or not raw.strip():
        return None if document.get("read_only") else manuscript_dir
    candidate = (root / raw).resolve()
    if not _under(candidate, root):
        return None
    if document.get("read_only") and _under(candidate, manuscript_dir):
        return None
    return candidate


def storage_home(project: str, repo_root=None, *, source=None) -> Path | None:
    """Existing selected editable/engine-owned state home, without creating it."""
    root = _root(repo_root)
    if source is None:
        # Storage is a declaration coordinate, independent of root body/hash
        # or saved edition choice. Reuse the same _state_dir fence as resolve;
        # history indexes must not open every TeX file just to find archives.
        from laplace.pipeline import registry
        declared = registry.resolve(project, repo_root=root)
        if declared is None:
            return None
        document = declared.manifest.get('document', {}) if isinstance(declared.manifest, dict) else {}
        document = document if isinstance(document, dict) else {}
        read_only = bool(declared.external_root) or bool(document.get('read_only'))
        relative = document.get('manuscript_dir') if isinstance(document.get('manuscript_dir'),str) else declared.manuscript_dir
        manuscript = declared.path(relative,root) if relative else None
        if manuscript is None:
            return None
        storage = _state_dir({**document,'read_only':read_only}, manuscript, root)
        return storage if storage is not None and _under(storage,root) else None
    if source.get("project") != project:
        raise ValueError("observed source belongs to another project")
    directory = source.get("storage_dir")
    if not directory and not source.get("read_only"):
        directory = source.get("manuscript_dir")
    if not isinstance(directory, str) or not directory:
        return None
    home = (root / directory).resolve()
    if not _under(home, root):
        return None
    return home


def feedback_ledger(project: str, repo_root=None, *, source=None) -> Path | None:
    """Current intake; declared generated-pipeline feedback remains separate."""
    home = storage_home(project, repo_root, source=source)
    return home / "feedback" / "feedback.jsonl" if home is not None else None


def _saved_selection(proj, root: Path) -> dict[str, Any] | None:
    path = _selection_path(proj, root)
    if path is None or not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def resolve(project: str, repo_root: Path | str | None = None,
            edition: str | None = None, *, include_candidates: bool = True) -> dict[str, Any]:
    """Resolve one registered manuscript source without heuristic selection.

    ``manifest.document`` accepts ``{root, edition, manuscript_dir}``.  An
    explicit root wins.  Without it, a single documentclass candidate is safe;
    the sole substantive candidate may replace an empty registered ``main.tex``.
    Multiple viable candidates remain an explicit ``ambiguous`` result.
    """
    from laplace.pipeline import registry

    root = _root(repo_root)
    proj = registry.resolve(project, repo_root=root)
    if proj is None:
        return {"project": project, "root": None, "manuscript_dir": None,
                "edition": edition, "status": "missing", "revision": None,
                "candidates": [], "foreign": False, "read_only": False,
                "diagnostics": ["unknown project"]}
    document = proj.manifest.get("document", {}) if isinstance(proj.manifest, dict) else {}
    document = document if isinstance(document, dict) else {}
    read_only = bool(proj.external_root) or bool(document.get("read_only"))
    saved = _saved_selection(proj, root)
    configured_edition = document.get("edition") if isinstance(document.get("edition"), str) else ""
    if edition and configured_edition and edition != configured_edition:
        return {"project": project, "root": None, "manuscript_dir": None,
                "edition": edition, "status": "missing", "revision": None,
                "candidates": [], "foreign": bool(proj.external_root),
                "read_only": read_only,
                "diagnostics": [f"edition {edition!r} is not registered"]}
    md_rel = document.get("manuscript_dir") if isinstance(document.get("manuscript_dir"), str) else proj.manuscript_dir
    manuscript_dir = proj.path(md_rel, root) if md_rel else None
    if manuscript_dir is None or not manuscript_dir.is_dir():
        return {"project": project, "root": None, "manuscript_dir": _rel(manuscript_dir, root) if manuscript_dir else None,
                "edition": edition or configured_edition or None, "status": "missing", "revision": None,
                "candidates": [], "foreign": bool(proj.external_root), "read_only": read_only,
                "diagnostics": ["declared manuscript directory is absent"]}
    # Addressed readers validate existing declarations, not the selection UI's
    # whole-directory discovery. An undeclared fallback needs explicit selection.
    candidates = _candidate_rows(manuscript_dir, root) if include_candidates else []
    registered_dir = proj.path(proj.tex_root, root) if proj.tex_root else None
    registered_root = registered_dir / "main.tex" if registered_dir is not None else None
    explicit = _configured_root(document, manuscript_dir, root)
    saved_root = _configured_root(saved or {}, manuscript_dir, root)
    # Target-plan resolution cannot affect an explicit/saved root. Addressed
    # reads need neither that unrelated plan nor the UI's candidate catalogue.
    target_dir = proj.resolved_target_dir(root) if include_candidates or not (explicit or saved_root) else None
    target_root = target_dir / "main.tex" if target_dir is not None else None
    chosen: Path | None = None
    status = "missing"
    selection = "none"
    diagnostics: list[str] = []
    if explicit is not None:
        if not _under(explicit, manuscript_dir):
            diagnostics.append("registered root escapes manuscript directory")
        elif explicit.is_file():
            chosen, status, selection = explicit, ("resolved" if _substantive(explicit) else "empty"), "manifest"
            if status == "empty":
                diagnostics.append("registered manifest root has no renderable manuscript content")
        else:
            diagnostics.append("registered root is absent")
    elif saved_root is not None:
        if not _under(saved_root, manuscript_dir):
            diagnostics.append("saved root escapes manuscript directory")
        elif not saved_root.is_file():
            diagnostics.append("saved root is absent")
        else:
            chosen, status, selection = saved_root, ("resolved" if _substantive(saved_root) else "empty"), "saved"
            if saved and saved.get("revision"):
                try:
                    if saved["revision"] != hashlib.sha256(saved_root.read_bytes()).hexdigest():
                        diagnostics.append("saved selection revision is stale; source path remains explicit")
                except OSError:
                    diagnostics.append("saved selection revision could not be checked")
            if status == "empty":
                diagnostics.append("saved manuscript root has no renderable manuscript content")
    else:
        main = manuscript_dir / "main.tex"
        if target_root is not None and target_root.is_file() and _substantive(target_root):
            # The authored projection plan already declares this target.  It is
            # the normal review edition; the registered tex root repairs only a
            # missing or structurally empty target.
            chosen, status, selection = target_root, "resolved", "target"
            diagnostics.append("declared target_dir/main.tex selected")
        elif registered_root is not None and registered_root.is_file() and _substantive(registered_root):
            # ``tex_root`` is the project's long-standing registered source
            # declaration.  It is authority, unlike the version/editor trees
            # stored beside it in manuscript_dir.
            chosen, status, selection = registered_root, "resolved", "registry"
            diagnostics.append("registered tex_root/main.tex selected")
        elif len(candidates) == 1 and candidates[0]["substantive"]:
            chosen, status, selection = root / candidates[0]["root"], "resolved", "fallback"
        elif main.is_file() and _substantive(main):
            # A substantive registered main is a declared convention, not a
            # tie-breaker by size/newness.
            chosen, status, selection = main, "resolved", "fallback"
        else:
            substantive = [c for c in candidates if c["substantive"]]
            if main.is_file() and not _substantive(main) and len(substantive) == 1:
                chosen, status, selection = root / substantive[0]["root"], "resolved", "fallback"
                diagnostics.append("empty registered main.tex replaced by sole substantive candidate")
            elif len([candidate for candidate in candidates if candidate["substantive"]]) > 1:
                status = "ambiguous"
                diagnostics.append("manifest.document.root is required to select among candidates")
            else:
                diagnostics.append("no TeX document root found")
        if chosen is None and status != "ambiguous" and registered_root is not None and registered_root.is_file():
            # Preserve the registered empty root as a visible state.  Consumers
            # can offer an edition choice or author it; they must not report an
            # empty document as successfully rendered.
            chosen, status, selection = registered_root, "empty", "registry"
            diagnostics.append("registered tex_root/main.tex has no renderable manuscript content")
    revision = None
    if chosen is not None:
        try:
            revision = hashlib.sha256(chosen.read_bytes()).hexdigest()
        except OSError:
            pass
    return {"project": project, "root": _rel(chosen, root) if chosen else None,
            "manuscript_dir": _rel(chosen.parent if chosen else manuscript_dir, root),
            "storage_dir": (_rel(storage, root) if (storage := _state_dir(document, manuscript_dir, root)) else None),
            "edition": edition or configured_edition or None, "status": status,
            "selection": selection,
            "revision": revision, "candidates": candidates,
            "foreign": bool(proj.external_root), "read_only": read_only,
            "diagnostics": diagnostics}


class SourceAccessError(ValueError):
    """An exact document/source request was not admitted; carries a bounded recovery."""
    def __init__(self, reason, message, *, project="", status=409):
        super().__init__(message)
        self.response = {"error": message, "reason": reason, "status": status,
                         "recovery": {"method": "GET", "route": "/authoring/document",
                                      "query": {"project": project}}}


def selection_identity(source: dict, project: str = "") -> str:
    """Edition authority, independent of file contents and build freshness."""
    value = {key: source.get(key) for key in ("root", "manuscript_dir", "edition")}
    value.update(project=project or source.get("project"), read_only=bool(source.get("read_only")))
    return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@contextmanager
def selection_mutation(project: str, repo_root=None):
    """Serialize cooperating edition selection and source admission before file leases."""
    from filelock import FileLock, Timeout
    root = _root(repo_root)
    home = root / ".laplace-cache" / "source-selection"
    home.mkdir(parents=True, exist_ok=True)
    key = str(home / (hashlib.sha256(project.encode()).hexdigest() + ".lock"))
    with _SOURCE_LOCKS_GUARD:
        lock = _SOURCE_LOCKS.get(key)
        if lock is None:
            lock = FileLock(key)
            _SOURCE_LOCKS[key] = lock
    try:
        with lock.acquire(timeout=15, poll_interval=.01):
            yield
    except Timeout as exc:
        raise SourceLeaseTimeout("document selection lease acquisition timed out") from exc


def source_access(project: str, path: Path, repo_root=None, *, writable=False,
                  expected_selection=None, source=None, source_tree=None, dependencies=None, selected_paths=None) -> dict:
    """Selected source membership is authority; dependency membership is read-only."""
    root = _root(repo_root)
    source = source if source is not None else resolve(project, root, include_candidates=False)
    if not source.get("root") or source.get("status") not in {"resolved", "empty"}:
        raise SourceAccessError("source-unavailable", "Choose a current manuscript source.", project=project, status=404)
    identity = selection_identity(source, project)
    if writable and expected_selection != identity:
        raise SourceAccessError("selection-revision-conflict", "The selected manuscript changed or its inspected selection guard is missing. Inspect the document; retain your draft.", project=project)
    if selected_paths is None:
        tree = source_tree if source_tree is not None else traversal(root / source["root"], root)
        selected = {(root / name).resolve() for name in tree.get("files", [])}
    else:
        selected = selected_paths
    path = path.resolve()
    if path not in selected:
        if writable:
            raise SourceAccessError("source-outside-selection", "This file is not current source of the selected manuscript.", project=project, status=403)
        from laplace.manuscript import tex_dependencies
        if path not in (dependencies if dependencies is not None else tex_dependencies.dependency_paths(root / source["root"], root)):
            raise SourceAccessError("source-outside-selection", "This file is outside the selected document source and dependencies. Read historical artifacts through their history owner.", project=project, status=403)
    readonly = bool(source.get("read_only")) or path not in selected
    if writable and readonly:
        raise SourceAccessError("source-not-writable", "The selected source is read-only; no source was written.", project=project, status=403)
    role = "root" if path == (root / source["root"]).resolve() else ({".cls":"class", ".sty":"package", ".bst":"bibliography-style", ".bib":"bibliography"}.get(path.suffix, "source" if path in selected else "figure"))
    return {"selection_identity": identity, "read_only": readonly, "role": role}


def require_unregistered_source(path: Path, repo_root=None, *, exclude_project=None) -> None:
    """A legacy directory/file address cannot bypass registered document authority."""
    from laplace.pipeline import registry
    root = _root(repo_root)
    path = path.resolve()
    for project in registry.all_projects(root).values():
        if project.name == exclude_project:
            continue  # Only a derived-output caller that already excluded exact membership may exempt its own project.
        document = project.manifest.get('document', {}) if isinstance(project.manifest, dict) else {}
        declarations = {project.manuscript_dir, document.get('manuscript_dir') if isinstance(document, dict) else None}
        for declared in declarations:
            base = project.path(declared, root) if declared else None
            if base and path.is_relative_to(base.resolve()):
                raise SourceAccessError('source-project-required', 'This registered manuscript requires its project and inspected selection guard.', project=project.name)


def source_protocol():
    """Exact registered raw-source transport; legacy unregistered scope is separate."""
    from laplace.manuscript.source_effects import protocol as effect_protocol
    text = {"type": "string"}
    pin = {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}
    read = {
        "type": "object",
        "required": ["corpus", "file", "view"],
        "properties": {"corpus": text, "file": text, "view": {"const": "source"},
            "offset": {"type":"integer","minimum":0}, "limit":{"type":"integer","minimum":1,"maximum":4096},
            "guards":{"type":"object","required":["source_revision","selection_identity"],
                "properties":{"source_revision":pin,"selection_identity":pin},"additionalProperties":False}},
        "additionalProperties": False,
    }
    save = {
        "type": "object",
        "required": ["corpus", "file", "author", "expected_selection", "expected_source_digest"],
        "properties": {
            "corpus": text,
            "file": text,
            "author": {"type": "string", "minLength": 1},
            "surface": text,
            "bank": text,
            "expected_selection": pin,
            "expected_source_digest": pin,
        },
        "additionalProperties": False,
    }
    return {
        "source_effect_protocol": effect_protocol(),
        "read_query": read,
        "save_query": save,
        "save_request": {
            "type": "object",
            "required": ["query", "body"],
            "properties": {"query": save, "body": text},
            "additionalProperties": False,
        },
        "read_response": {
            "type": "object",
            "required": [
                "schema_version",
                "file",
                "content",
                "expected_source_digest",
                "selection_identity",
                "read_only",
                "role",
                "read_handle",
                "save_handle",
            ],
            "properties": {
                "schema_version": {"const": "laplace.projection-source/1"},
                "file": text,
                "content": text,
                "expected_source_digest": pin,
                "selection_identity": pin,
                "read_only": {"type": "boolean"},
                "role": text,
                "read_handle": {"type": "object"},
                "save_handle": {"type": ["object", "null"]},
            },
        },
        "save_receipt": {
            "type": "object",
            "required": [
                "ok",
                "source_committed",
                "changed",
                "file",
                "consumed_source_digest",
                "expected_source_digest",
                "selection_identity",
                "invalidated",
                "history_read",
            ],
            "properties": {
                "ok": {"const": True},
                "source_committed": {"const": True},
                "changed": {"type": "boolean"},
                "file": text,
                "consumed_source_digest": pin,
                "expected_source_digest": pin,
                "selection_identity": pin,
                "invalidated": {"type": "array"},
                "history_read": {"type": "object"},
                "maintenance_warnings": {"type": "array"},
                "source_effect": {"type":"object", "properties":{"schema_version":{"const":"laplace.source-effect/1"}}},
            },
        },
        "error_response": {
            "type": "object",
            "required": ["error"],
            "properties": {"error": text, "reason": text, "recovery": {"type": "object"}},
        },
        "semantics": [
            "Submit the original selection and physical-byte digest; no automatic fresh-token retry.",
            "source_committed is the effect acknowledgement; later maintenance warnings never authorize repetition.",
            "changed:false preserves bytes/mtime and creates no saved version.",
            "Historical source reads issue no writable current-source guard.",
            "Unregistered legacy addresses remain explicitly separate and cannot address a registered manuscript.",
        ],
    }


def validate_source_query(query, *, write=False):
    from jsonschema import Draft202012Validator

    values = {}
    for name, value in query.items():
        if isinstance(value, (list, tuple)):
            if len(value) != 1:
                raise ValueError("Source query fields must occur exactly once: " + name)
            value = value[0]
        if not write and name in {'offset','limit'} and isinstance(value,str):
            try:value=int(value)
            except ValueError:raise ValueError('Source part offset/limit must be integers.')
        if not write and name=='guards' and isinstance(value,str):
            try:value=json.loads(value)
            except ValueError:raise ValueError('Source part guards must be exact JSON.')
        values[name] = value
    schema = source_protocol()["save_query" if write else "read_query"]
    error = next(Draft202012Validator(schema).iter_errors(values), None)
    if error:
        raise ValueError("Source query rejected: " + error.message)
    return values

def source_handles(project: str, file: str, digest: str, access: dict) -> dict:
    read = {"method":"GET", "route":"/projection/tex", "query":{"corpus":project,"file":file,"view":"source"}}
    save = None if access["read_only"] else {"method":"POST", "route":"/projection/tex",
        "query":{"corpus":project,"file":file,"expected_selection":access["selection_identity"],"expected_source_digest":digest,"bank":"editor"},
        "body_kind":"raw-text", "requires":["author"]}
    return {"read_handle":read,"save_handle":save}


def select(project: str, root: str, *, repo_root=None, expected_revision=None) -> dict:
    with selection_mutation(project, repo_root):
        return _select(project, root, repo_root=repo_root, expected_revision=expected_revision)


def _select(project: str, root: str, *, repo_root: Path | str | None = None,
           expected_revision: str | None = None) -> dict[str, Any]:
    """Persist a user-selected candidate without changing manuscript bytes.

    The choice lives in the project's ``manuscript/document_selection.json`` and
    is accepted only for a currently discovered candidate.  A foreign project
    has no writable selection file and is refused rather than rewritten.
    """
    from laplace.pipeline import registry

    base = _root(repo_root)
    proj = registry.resolve(project, repo_root=base)
    if proj is None:
        raise KeyError(f"unknown project {project!r}")
    path = _selection_path(proj, base)
    if path is None:
        raise PermissionError("foreign/read-only project source selection cannot be persisted")
    current = resolve(project, repo_root=base)
    known = {str(item.get("root")) for item in current.get("candidates", [])}
    if root not in known:
        raise ValueError("root must be one of the source candidates returned by resolve")
    candidate = (base / root).resolve()
    revision = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if expected_revision is not None and expected_revision != revision:
        raise ValueError("source changed since the displayed revision; refresh candidates before selecting")
    document = proj.manifest.get("document", {}) if isinstance(proj.manifest, dict) else {}
    declared_directory = document.get("manuscript_dir") if isinstance(document, dict) else None
    manuscript = proj.path(declared_directory or proj.manuscript_dir, base)
    configured = _configured_root(document, manuscript, base) if isinstance(document, dict) and manuscript is not None else None
    if configured is not None:
        if configured.resolve() != candidate:
            raise ValueError("The project manifest fixes its source root. Alternate selection was not saved; explicitly migrate the document definition before switching roots.")
        return {**current, "selection_changed":False}
    payload = {"root": root, "revision": revision}
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                     prefix=f".{_SELECTION_FILE}.", delete=False) as temp:
        json.dump(payload, temp, ensure_ascii=False, indent=1)
        temp.write("\n")
        staged = Path(temp.name)
    staged.replace(path)
    return resolve(project, repo_root=base)


def traversal(root_path: Path | str, repo_root: Path | str | None = None) -> dict[str, Any]:
    """Expand nested ``input``/``include`` calls in source order, resolving every argument the way TeX does: against
    the compilation directory (the root's directory), never the including file's (tex_dependencies.tex_input).

    Every occurrence is retained (a source included twice has two instances),
    while each item carries exact byte and line bounds in its own file.  Missing
    targets and cycles are diagnostics instead of silently shortening a book.
    """
    from laplace.manuscript import tex_dependencies
    repo = _root(repo_root)
    raw_root = Path(root_path)
    path = raw_root if raw_root.is_absolute() else repo / raw_root
    path = path.resolve()
    if not path.is_file():
        return {"root": _rel(path, repo), "files": [], "sources": [], "includes": [],
                "diagnostics": [{"kind": "missing-root", "file": _rel(path, repo)}]}
    fence = path.parent.resolve()
    sources: list[dict[str, Any]] = []
    includes: list[dict[str, Any]] = []
    seen_files: list[str] = []
    diagnostics: list[dict[str, Any]] = []
    observed: dict[Path, tuple[bytes,str,str]] = {}

    def visit(current: Path, parent: Path | None, include_line: int | None,
              stack: tuple[Path, ...]) -> None:
        rel = _rel(current, repo)
        if current in stack:
            diagnostics.append({"kind": "include-cycle", "file": rel,
                                "chain": [_rel(p, repo) for p in (*stack, current)]})
            return
        try:
            if current not in observed:
                data=current.read_bytes()
                observed[current]=(data,data.decode('utf-8',errors='replace'),hashlib.sha256(data).hexdigest())
            data,text,digest=observed[current]
        except OSError as exc:
            diagnostics.append({"kind": "unreadable", "file": rel, "error": str(exc)})
            return
        if rel not in seen_files:
            seen_files.append(rel)
        order = len(sources)
        sources.append({"order": order, "file": rel, "parent": _rel(parent, repo) if parent else None,
                        "include_line": include_line, "line_start": 1,
                        "line_end": len(re.split(r"\r\n|\r|\n",text)), "byte_start": 0,
                        "byte_end": len(data), "sha256": digest, "text": text})
        uncommented = _uncomment(text)
        for line_no, line in enumerate(uncommented.splitlines(), 1):
            for match in _INPUT_RE.finditer(line):
                argument = match.group(1).strip()
                # the shared TeX include contract: relative to the compilation directory (tex_dependencies.tex_input)
                found = tex_dependencies.tex_input(argument, including=current, compile_dir=fence, fence=fence)
                target = found["path"]
                target_rel = _rel(target, repo) if target is not None else argument
                record = {"parent": rel, "line_start": line_no, "line_end": line_no,
                          "argument": argument, "target": target_rel,
                          "exists": found["status"] in ("resolved", "ambiguous")}
                if found["alternate"] is not None:
                    record["alternate"] = _rel(found["alternate"], repo)
                includes.append(record)
                if found["status"] == "resolved":
                    visit(target.resolve(), current, line_no, (*stack, current))
                else:
                    diagnostics.append({"kind": found["status"] + "-include", **record})

    visit(path, None, None, ())
    return {"root": _rel(path, repo), "files": seen_files, "sources": sources,
            "includes": includes, "diagnostics": diagnostics}


def observation(project: str, repo_root=None, *, source=None, source_tree=None) -> dict:
    """Compact identity of selected source AND its actual included files.

    This is a scoped read, not a second document store. The full reader can pass
    its already-read traversal so these pins describe that body; polling never
    renders the book or reads history. Repeated includes retain their occurrence
    identity while physical source bytes are observed once per traversal.
    file_revisions contains unprefixed SHA-256 of those RAW bytes, including CRLF;
    it is not the normalized-text expected_source_digest used by span writers.
    """
    root=_root(repo_root);source=source if source is not None else resolve(project,repo_root=root)
    tree=source_tree if source_tree is not None else (
        traversal(root/source['root'],repo_root=root) if source.get('root') else {})
    files={row['file']:row['sha256'] for row in tree.get('sources',[])}
    occurrences=[{key:row.get(key) for key in ('file','sha256','parent','include_line')} for row in tree.get('sources',[])]
    identity={key:source.get(key) for key in ('root','manuscript_dir','edition','revision','read_only','status')}
    def digest(value):return 'sha256:'+hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    source_revision=digest({'sources':occurrences,'includes':tree.get('includes',[]),'diagnostics':tree.get('diagnostics',[])})
    return {'schema_version':'laplace.manuscript-source-observation/1','project':project,
            'status':'AVAILABLE' if source.get('status')=='resolved' and files else 'UNAVAILABLE',
            'selected_source':identity,'selection_identity':selection_identity(source, project),'source_revision':source_revision,
            'revision':digest({'project':project,'selected_source':identity,'source_revision':source_revision}),
            'file_revisions':files}


# PROJECT-OWNED STATE vs SELECTED SOURCE (campaign manuscript state home, 2026-10-14). Appended so no cited
# line of this owner moves.
def project_state_dir(source: dict[str, Any] | None, repo_root=None) -> str | None:
    """The repository-relative directory that holds a project's OWN engine state (research records and
    runs, reference associations, research figures) for an observed `resolve` result.

    A registered source-optional project (layout ``project``) keeps that state in its declared state home
    (``storage_dir``, the project's manuscript home) whichever draft is selected: starting or selecting a
    nested working draft changes the selected source and compile root (``root``/``manuscript_dir``), not
    where its evidence lives.  Every other layout, and every read-only or foreign source, keeps the
    existing coordinate (the selected ``manuscript_dir``), so edition and read-only fences are unchanged.
    """
    if not isinstance(source, dict):
        return None
    selected = source.get("manuscript_dir")
    storage = source.get("storage_dir")
    if source.get("read_only") or source.get("foreign") or not isinstance(storage, str) or not storage:
        return selected
    from laplace.pipeline import registry
    record = registry.resolve(str(source.get("project") or ""), repo_root=_root(repo_root))
    return storage if record is not None and getattr(record, "kind", "") == "project" else selected


def declared_evidence_choices(project: str, repo_root=None) -> dict:
    """A declared Writing file choice without candidate discovery or body reads.

    This is metadata admission for completion selection, not selected-source or
    byte-currentness proof. Opening/using the file keeps its existing owner gates.
    """
    from laplace.pipeline import registry
    from urllib.parse import urlencode
    root=_root(repo_root);proj=registry.resolve(project,repo_root=root)
    if proj is None:return {'items':[],'coverage':'UNAVAILABLE','reason':'Project is not registered.'}
    document=proj.manifest.get('document',{}) if isinstance(proj.manifest,dict) else {}
    document=document if isinstance(document,dict) else {}
    if proj.external_root or document.get('read_only'):
        return {'items':[],'coverage':'UNAVAILABLE','reason':'Read-only/foreign Source is not a project completion file; use its existing source reader.'}
    md_rel=document.get('manuscript_dir') if isinstance(document.get('manuscript_dir'),str) else proj.manuscript_dir
    manuscript=proj.path(md_rel,root) if md_rel else None
    base=proj.path(proj.project_dir or proj.manuscript_dir,root)
    if manuscript is None or base is None or not _under(manuscript,root) or not _under(base,root):
        return {'items':[],'coverage':'UNAVAILABLE','reason':'No in-checkout declared Writing home.'}
    explicit=_configured_root(document,manuscript,root)
    saved=_saved_selection(proj,root);saved_root=_configured_root(saved or {},manuscript,root)
    registered=proj.path(proj.tex_root,root) if proj.tex_root else None
    target=explicit or saved_root or (registered/'main.tex' if registered is not None else None)
    if not explicit and not saved_root and proj.kind=='project' and (target is None or not target.is_file()):
        return {'items':[],'coverage':'NOT_APPLICABLE','reason':'This source-optional project declares no Writing file.'}
    origin='manifest' if explicit else 'saved-selection' if saved_root else 'registry'
    if target is None or not _under(target,manuscript) or not _under(target,base) or not _under(target,root) or not target.is_file():
        return {'items':[],'coverage':'UNAVAILABLE','reason':'Declared Writing file is absent or outside its project owner scope.'}
    relative=target.relative_to(base.resolve()).as_posix();evidence=target.relative_to(root).as_posix();stamp=target.stat()
    read={'http':{'method':'GET','url':'/research/artifact?'+urlencode({'project':project,'scope':'project','path':relative})}}
    return {'items':[{'id':'writing-source:'+evidence,'label':'Declared Writing source · '+target.name,
        'owner':'manuscript-source','state':'OFFERED','evidence_value':evidence,'currentness':'NOT_CHECKED',
        'declaration':origin,'read':read,'owner_target':{'kind':'project-file','project':project,'scope':'project','path':relative,'expected_sha256':None},
        'support_manifest_eligibility':'NOT_AN_ARTIFACT_MANIFEST',
        'qualification':'Declared file only; no selection, source body, byte freshness or successful compilation was inferred.'}],
        'observation':{'declaration':document,'saved_selection':saved,'file':evidence,
            'stat':[stamp.st_ino,stamp.st_size,stamp.st_mtime_ns,stamp.st_ctime_ns]},
        'coverage':'Explicit/saved/registered root coordinate only; fallback candidates, include tree and source contents were not read.'}
