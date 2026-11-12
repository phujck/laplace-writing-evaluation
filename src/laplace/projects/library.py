"""The manuscript-project library and its small, user-triggered creation doors."""
from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import hashlib
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from filelock import FileLock

_JSON = "application/json; charset=utf-8"
_NAME = re.compile(r"^(?=.{2,64}$)[a-z0-9]+(?:-[a-z0-9]+)*$")
_TITLE = re.compile(r"\\title\s*\{([^}]*)\}")
_DOC = re.compile(r"\\documentclass\b")


def _root() -> Path:
    return source_tree()


def _response(status: int, value: Any) -> tuple[int, str, bytes]:
    return status, _JSON, json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _q1(query: dict, name: str) -> str:
    value = query.get(name, "")
    if isinstance(value, (list, tuple)): value = value[0] if value else ""
    return value.strip() if isinstance(value, str) else ""


def _title(path: Path, fallback: str) -> str:
    try: match = _TITLE.search(path.read_text(encoding="utf-8", errors="replace"))
    except OSError: match = None
    return re.sub(r"\\[A-Za-z]+", "", match.group(1)).strip() if match else fallback


def _library(root: Path) -> dict:
    from laplace.pipeline import registry
    from laplace.manuscript import manuscript_source
    projects = []
    declared = {row.get("name") for row in registry._data_projects(root)}
    for name, project in sorted(registry.all_projects(root).items()):
        if project.kind == "site": continue
        source = manuscript_source.resolve(name, repo_root=root)
        manifest = project.manifest if isinstance(project.manifest, dict) else {}
        writing = manifest.get("writing") if isinstance(manifest.get("writing"), dict) else {}
        source_path = root / source["root"] if source.get("root") else None
        candidates = source.get("candidates", [])
        projects.append({
            "name": name, "title": manifest.get("display_name") or (_title(source_path, name) if source_path else name),
            "kind": writing.get("kind") or project.kind, "layout": project.kind,
            "source_optional": project.kind == "project",
            "creation": manifest.get("creation", {"status": "ready"}),
            **_capabilities(project, source, name in declared, root=root),
            "root": source.get("root"),
            "manuscript_dir": source.get("manuscript_dir"), "status": source.get("status"),
            "selection": source.get("selection"), "candidates": candidates[:12],
            "candidates_truncated": len(candidates) > 12,
            "foreign": source.get("foreign", False), "read_only": source.get("read_only", False),
            "framing": {"purpose": writing.get("purpose", ""), "audience": writing.get("audience", "")},
        })
    return {"schema_version": "laplace.writing-projects/1", "projects": projects,
            "read_only": True, "reembed": False}


def _research_served(record, base: Path) -> bool:
    """True when the Research owner admits this source-optional project at a home inside the project's
    own directory: never through the owner's legacy repository-root manuscript fallback, which would
    show another project's research."""
    from laplace.research import research_context
    try:
        home = research_context.owner_home(record.name, base)
        own = record.path(record.project_dir, base) if record.project_dir else None
        return bool(home and own and Path(home).resolve().is_relative_to(Path(own).resolve()))
    except (OSError, ValueError):
        return False


def _capabilities(record, source: dict, metadata_available: bool, root=None) -> dict:
    """One capability projection for library, metadata and create callers."""
    base = Path(root or _root()).resolve()
    try:
        plan_path = record.plan(base) if record.plan_path else None
        reader_plan = bool(plan_path and plan_path.resolve().is_relative_to(base))
    except (OSError, ValueError):
        reader_plan = False
    return {"layout": record.kind, "source_optional": record.kind == "project",
        "capabilities": {"manuscript": source.get("status") == "resolved",
            "reader_plan": reader_plan,
            "start_manuscript": not source.get("read_only") and source.get("status") not in {"resolved", "ambiguous"} and bool(record.manuscript_dir),
            "work": True, "materials": True, "turns": True, "history": True, "settings": True,
            "concepts": (record.kind != "project" or bool(record.plan_path)) and source.get("status") == "resolved",
            # a source-optional project with a selected manuscript but no plan owner may start its reader plan
            # (writing.project_lifecycle); read project_metadata.authoring_lifecycle for the guarded action
            "start_planning": (record.kind == "project" and not record.plan_path and source.get("status") == "resolved"
                               and not source.get("read_only") and not source.get("foreign")),
            # a source-optional project shows Research when the Research owner serves it from inside
            # the project's own home (results and artifacts need no manuscript); every other layout
            # keeps its rule (campaign research visibility, 2026-10-14)
            "research": record.kind != "project" or _research_served(record, base),
            "review": source.get("status") == "resolved",
            "presentation": source.get("status") == "resolved",
            "material_references": metadata_available}}


def project_capabilities(project: str, root: Path | None = None) -> dict:
    from laplace.pipeline import registry
    from laplace.manuscript import manuscript_source
    root = Path(root or _root()).resolve()
    record = registry.resolve(project, root)
    if record is None:
        raise ValueError("Unknown project")
    return _capabilities(record, manuscript_source.resolve(project, repo_root=root),
                         any(row.get("name") == project for row in registry._data_projects(root)), root=root)


def discover(root: Path | None = None, limit: int = 60) -> dict:
    """Search only recognized repository manuscript homes, never the user's disk."""
    root = (root or _root()).resolve()
    from laplace.pipeline import registry
    from laplace.manuscript import manuscript_source
    registered = {str(source.get("root")) for name in registry.all_projects(root)
                  if (source := manuscript_source.resolve(name, repo_root=root)).get("root")}
    homes: set[Path] = set()
    for project in registry.all_projects(root).values():
        if project.manuscript_dir:
            candidate = project.path(project.manuscript_dir, root)
            if candidate and candidate.is_dir(): homes.add(candidate)
    papers = root / "synthetics papers"
    if papers.is_dir(): homes.update(p for p in papers.glob("*/manuscript") if p.is_dir())
    rows = []
    for home in sorted(homes):
        for path in sorted(home.rglob("*.tex")):
            if any(part in {"editor_saves", "versions", "whitepaper"} for part in path.relative_to(home).parts): continue
            try: text = path.read_text(encoding="utf-8", errors="replace")
            except OSError: continue
            rel = path.relative_to(root).as_posix()
            if rel in registered or not _DOC.search(text) or manuscript_source.edition_wrapper(text): continue
            rows.append({"root": rel, "title": _title(path, path.stem), "status": "candidate",
                         "manuscript_dir": path.parent.relative_to(root).as_posix()})
            if len(rows) >= limit: return {"candidates": rows, "limit": limit, "bounded": True}
    return {"candidates": rows, "limit": limit, "bounded": True}


def _registry_write(root: Path, mutate) -> Any:
    from laplace.pipeline import registry
    path = root / registry.DATA_PROJECTS_FILE
    lock = FileLock(str(path) + ".lock", timeout=20)
    with lock:
        raw = {"projects": []}
        if path.is_file():
            try: raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError): raise ValueError("registry_projects.json is unreadable")
        if not isinstance(raw, dict) or not isinstance(raw.get("projects"), list):
            raise ValueError("registry_projects.json has no projects list")
        result = mutate(raw["projects"])
        staged = path.with_suffix(".tmp")
        staged.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        staged.replace(path)
        return result


def _update_created_row(root: Path, name: str, title: str, kind: str, purpose: str, audience: str, filename: str) -> None:
    def mutate(rows):
        for row in rows:
            if row.get("name") == name:
                manifest = row.setdefault("manifest", {})
                manifest["display_name"] = title
                manifest["document"] = {"root": filename, "manuscript_dir": row["tex_root"], "edition": "draft", "title":title, "basename":Path(filename).stem}
                manifest["writing"] = {"kind": kind, "purpose": purpose, "audience": audience}
                return
        raise ValueError("new registry row disappeared before it could be completed")
    _registry_write(root, mutate)


def _metadata(row: dict) -> dict:
    encoded = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {"schema_version": "laplace.project-metadata/1", "project": row["name"],
            "title": (row.get("manifest") or {}).get("display_name") or row["name"],
            "publication_editions": (row.get("manifest") or {}).get("publication_editions") or [],
            "revision": "sha256:" + hashlib.sha256(encoded).hexdigest(),
            "scope": "project library/display title; manuscript title and research question are separate"}


def metadata(project: str, root: Path | None = None) -> dict:
    root = Path(root or _root()).resolve()
    path = root / "registry_projects.json"
    try:
        rows = json.loads(path.read_text())["projects"]
        row = next(row for row in rows if row.get("name") == project)
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        raise ValueError("Project metadata is unavailable for this registered project") from exc
    # the one project's source facts the shell's Home needs (selected root, read-only, the
    # bounded edition candidates), so entry reads this owner instead of the whole library
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve(project, repo_root=root)
    candidates = source.get("candidates", [])
    from laplace.projects import project_lifecycle
    lifecycle, capable = project_lifecycle.observe(project, root), project_capabilities(project, root)
    # Home's Start reader plan follows the lifecycle owner's own state (a refused or pending declaration included)
    capable["capabilities"]["start_planning"] = lifecycle["state"] in {"MANUSCRIPT_WITHOUT_PLAN", "PLAN_PUBLICATION_PENDING"}
    return {**_metadata(row), **capable, "authoring_lifecycle": lifecycle,
            "root": source.get("root"), "manuscript_dir": source.get("manuscript_dir"), "status": source.get("status"),
            "selection": source.get("selection"), "read_only": source.get("read_only", False),
            "candidates": candidates[:12], "candidates_truncated": len(candidates) > 12}


def change_metadata(project: str, payload: dict, root: Path | None = None) -> dict:
    """Edit a project display title, and optionally its publication-edition declaration, without
    renaming its identity or source files (writing.publication_editions validates the declaration)."""
    from laplace.core import identity_doors
    from laplace.core.records import journal
    identity_doors.admit_expected(payload, "project_metadata_change")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    from laplace.core.receipts import bundle, file_receipt
    root = Path(root or _root()).resolve()
    if not isinstance(payload, dict) or set(payload) - {"title", "expected_revision", "expected",
                                                        "reason", "by", "project", "publication_editions"}:
        raise ValueError("Project metadata accepts title, expected_revision, optional publication_editions and reason")
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip() or len(title) > 240:
        raise ValueError("Project title must be non-empty and at most 240 characters")
    title = " ".join(title.split())
    editions = payload.get("publication_editions")
    if editions is not None:
        # Admitted against the selected root before the registry lock (source resolution reads the registry).
        from laplace.manuscript import publication_editions
        editions = publication_editions.validate(project, editions, root)
    path = root / "registry_projects.json"
    with FileLock(str(path) + ".lock", timeout=20):
        before_bytes = path.read_bytes()
        data = json.loads(before_bytes)
        row = next((row for row in data.get("projects", []) if row.get("name") == project), None)
        if row is None:
            raise ValueError("Unknown project")
        before = _metadata(row)
        # One of the six refusals that held the value in a local variable at the moment they
        # declined to return it (`before["revision"]` is right there).  `require` takes the
        # observed token as its second argument, so the value is in hand before the refusal
        # exists and cannot be dropped: `needed.expected` now carries it.
        from laplace.core import identity_doors
        identity_doors.gate("project_metadata_change", supplied=payload,
                            homes=[("project-metadata", project, before["revision"])],
                            required=["expected_revision"],
                            said="Project metadata revision conflict; read project_metadata and retry")
        if before["title"] == title and editions in (None, before["publication_editions"]):
            return {**before, "unchanged": True, "owned_changes": bundle(views=["project"])}
        row.setdefault("manifest", {})["display_name"] = title
        if editions:
            row["manifest"]["publication_editions"] = editions
        elif editions is not None:
            row["manifest"].pop("publication_editions", None)
        reason = payload.get("reason") or ("Edit project display title" if editions is None or before["title"] != title
                                           else "Define publication editions")
        after = _metadata(row)
        encoded = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
        ident = "PMETA-" + uuid.uuid4().hex
        (root / "contract").mkdir(exist_ok=True)
        # THE ONE SEAM for a writing row (WRITING-CONSOLIDATION-W1): these rows once went
        # straight to `journal.bank_row`, bypassing the custody bound. The seam is the
        # records owner's bank (writing.records), which the native door's own rows use too.
        from laplace.writing import records as writing_records
        writing_records.bank(root, {"record": "project-metadata-change-intent",
            "id": ident + "-intent", "project": project, "before": before, "after": after,
            "by": payload.get("by") or "author", "reason": reason})
        staged = path.with_suffix(".tmp")
        staged.write_bytes(encoded)
        staged.replace(path)
        owned = file_receipt(root, path, before_bytes, encoded)
        writing_records.bank(root, {"record": "project-metadata-change",
            "id": ident, "project": project, "before": before, "after": after,
            "by": payload.get("by") or "author", "reason": reason,
            "registry_before_sha256": owned["before_sha256"],
            "registry_after_sha256": owned["after_sha256"]})
    return {**after, "unchanged": False, "record_id": ident,
            "owned_changes": bundle(files=[owned], views=["project"])}


def _draft_source(manuscript: Path, title: str, kind: str, purpose: str) -> list[Path]:
    def tex(value):
        escapes = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
                   "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
        return "".join(escapes.get(c, c) for c in value)
    chapters = manuscript / "chapters"; chapters.mkdir(exist_ok=True)
    chapter = chapters / "chapter-01.tex"
    heading = "Chapter One" if kind == "book" else "Introduction"
    document = "book" if kind == "book" else "article"
    from laplace.manuscript.document_metadata import basename
    from laplace.manuscript.manuscript_source import source_mutation
    from laplace.projects import project_creation
    main = manuscript / (basename(title) + '.tex')
    bib = manuscript / 'refs.bib'
    stub = manuscript / 'main.tex'
    with source_mutation([main, chapter, bib, stub]):
        for target in (main, chapter, bib):
            if target.exists() and not (target == stub and target.read_text() == project_creation.SCAFFOLD_MAIN_TEX):
                raise ValueError("Draft target already has source material; refresh before creating it.")
        import os
        from laplace.manuscript.manuscript_source import stage_source
        chapter_text = (f"\\chapter{{{heading}}}\n" if kind == "book" else f"\\section{{{heading}}}\n")
        chapter_text += "\\textit{Draft — this opening is ready for authoring.}\n\n"
        if purpose: chapter_text += tex(purpose.strip()) + "\n"
        main_text = f"\\documentclass{{{document}}}\n\\usepackage{{amsmath,amssymb,graphicx,hyperref}}\n\\title{{{tex(title)}}}\n\\hypersetup{{pdftitle={{{tex(title)}}}}}\n\\author{{}}\n\\date{{}}\n\\begin{{document}}\n\\maketitle\n\\input{{chapters/chapter-01}}\n\\bibliographystyle{{plain}}\n\\bibliography{{refs}}\n\\end{{document}}\n"
        planned = {chapter:chapter_text, main:main_text,
                   bib:'% Project references are attached through /references/attach.\n'}
        staged = {}
        try:
            for target, text in planned.items():
                staged[target] = stage_source(target, text.replace("\n", os.linesep).encode('utf-8'))
            for target, temporary in staged.items():
                temporary.replace(target)
        finally:
            for temporary in staged.values(): temporary.unlink(missing_ok=True)
    return [main, chapter, bib]


def create(payload: dict, root: Path | None = None) -> tuple[int, dict]:
    root = (root or _root()).resolve()
    if not isinstance(payload, dict) or any(payload.get(key) is not None and not isinstance(payload[key], str)
                                            for key in ("name", "title", "kind", "purpose", "audience", "question")):
        return 422, {"error": "Project name, title, category and framing fields must be text"}
    name, title, kind = (payload.get("name") or "").strip(), (payload.get("title") or "").strip(), payload.get("kind")
    purpose, audience = (payload.get("purpose") or "").strip(), (payload.get("audience") or "").strip()
    if not _NAME.fullmatch(name): return 422, {"error": "name must be a slug"}
    if not title or len(title) > 240: return 422, {"error": "title is required and must be at most 240 characters"}
    if kind is None: kind = "general"
    if kind not in {"book", "paper", "general", "software", "development", "company", "transcript", "campaign"}:
        return 422, {"error": "Choose a supported project category"}
    if kind not in {"book", "paper"}:
        return _create_general(root, name, title, kind, purpose, audience)
    from laplace.manuscript import manuscript_source
    from laplace.projects import project_creation
    status, created = project_creation.create_project(name, "conceptric", root=root, goal=purpose or title)
    if status != 201: return status, created
    manuscript = root / "synthetics papers" / name / "manuscript"
    made: list[Path] = []
    try:
        made = _draft_source(manuscript, title, kind, purpose)
        _update_created_row(root, name, title, kind, purpose, audience, made[0].name)
        # Replace only the exact stub this creation call just made. Never retain
        # a competing generic root, and never remove an authored source.
        scaffold = manuscript / 'main.tex'
        with manuscript_source.source_mutation([scaffold]):
            if scaffold != made[0] and scaffold.is_file() and scaffold.read_text() == project_creation.SCAFFOLD_MAIN_TEX:
                scaffold.unlink()
        source = manuscript_source.resolve(name, repo_root=root)
        # The authoring context becomes usable at the same moment as the source;
        # no caller must first satisfy a compile, embedding, or release lock.
        from laplace.pipeline import authoring
        authoring.save(name, {"argument": purpose,
                              "framing": {"purpose": purpose, "audience": audience,
                                          "question": str(payload.get("question") or "").strip()}},
                       repo_root=root)
        return 201, {"ok": True, "project": name, "title": title, "kind": kind, "layout": "conceptric",
                     "source_optional": False, "source": source,
                     **project_capabilities(name, root),
                     "editable": [path.relative_to(root).as_posix() for path in made], "pipeline_locked": False}
    except Exception as exc:
        # Preserve the claimed project's partial source and record the failure;
        # a failed creation never deletes subsequently authored files or hides its row.
        _creation_failed(root, name, exc)
        return 500, {"error": f"creation did not complete: {exc}", "project": name,
                     "creation_status": "failed", "retained_project": True,
                     "retained_paths": [path.relative_to(root).as_posix() for path in made if path.exists()]}


def _creation_failed(root: Path, name: str, error: Exception) -> None:
    def mark(rows):
        row = next(row for row in rows if row.get("name") == name)
        row.setdefault("manifest", {})["creation"] = {"status": "failed", "error": str(error)[:1000]}
    _registry_write(root, mark)


def _create_general(root: Path, name: str, title: str, kind: str,
                    purpose: str, audience: str) -> tuple[int, dict]:
    with FileLock(str(root / "registry_projects.json") + ".create.lock", timeout=30):
        return _create_general_claimed(root, name, title, kind, purpose, audience)


def _create_general_claimed(root: Path, name: str, title: str, kind: str,
                            purpose: str, audience: str) -> tuple[int, dict]:
    """Register a workspace without creating manuscript contents or pipeline work."""
    from laplace.pipeline import registry, authoring
    from laplace.manuscript import manuscript_source
    if registry.resolve(name, root) is not None:
        return 409, {"error": "project name already exists"}
    home = root / "writing_projects" / name
    try:
        home.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return 409, {"error": "project directory already exists"}
    row = {"name": name, "kind": "project", "project_dir": home.relative_to(root).as_posix(),
           "created_by": "projects-create", "manifest": {"display_name": title,
               "writing": {"kind": kind, "purpose": purpose, "audience": audience}}}
    def append(rows):
        if any(existing.get("name") == name for existing in rows):
            raise ValueError("project name already exists")
        rows.append(row)
    try:
        _registry_write(root, append)
    except (OSError, ValueError) as exc:
        home.rmdir()
        return 409, {"error": str(exc)}
    try:
        authoring.save(name, {"argument": purpose, "framing": {"purpose": purpose, "audience": audience}}, repo_root=root)
    except Exception as exc:
        _creation_failed(root, name, exc)
        return 500, {"error": f"creation did not complete: {exc}", "project": name,
                     "creation_status": "failed", "retained_project": True}
    return 201, {"ok": True, "project": name, "title": title, "kind": kind,
                 "layout": "project", "source_optional": True,
                 "source": manuscript_source.resolve(name, repo_root=root),
                 **project_capabilities(name, root), "editable": [], "pipeline_locked": False}


def start_manuscript(payload: dict, root: Path | None = None) -> tuple[int, dict]:
    """Add manuscript (POST /projects/start), the human door of writing.project_lifecycle.start_authoring.

    A source-optional project gets its manuscript AND its reader/argument plan ownership through the one
    lifecycle owner (the same transition as native structure_change start_authoring); a project of another
    layout keeps the manuscript-only start it always had. Refusals keep their statuses."""
    root = (root or _root()).resolve()
    project = str(payload.get('project') or '') if isinstance(payload, dict) else ''
    from laplace.pipeline import registry
    from laplace.projects import project_lifecycle as lifecycle
    record = registry.resolve(project, repo_root=root)
    if record is None or record.kind != 'project' or payload.get('kind', 'paper') not in {'book', 'paper'}:
        return _start_manuscript_unplanned(payload, root)
    observed = lifecycle.observe(project, root)
    if observed['state'] != 'NO_MANUSCRIPT':
        return _start_manuscript_unplanned(payload, root)
    try:
        result = lifecycle.start_authoring(project, {'expected_project_lifecycle': observed['revision'],
            **{key: payload[key] for key in ('kind', 'title') if key in payload}}, root, actor={'kind': 'human'})
    except lifecycle.LifecycleRefused as refused:
        return 409, {'error': str(refused), 'authoring_lifecycle': refused.lifecycle}
    started = result['manuscript_started'] or {}
    return 201, {'ok': True, 'project': project, 'source': started.get('source'), 'receipt_id': started.get('receipt_id'),
                 'planning': result['planning'], 'planning_receipt_id': result['receipt_id'], 'authoring_lifecycle': result['lifecycle']}


def _start_manuscript_unplanned(payload: dict, root: Path | None = None) -> tuple[int, dict]:
    """Give a registered, source-less project a draft without replacing old files."""
    from laplace.pipeline import registry, authoring
    from laplace.manuscript import manuscript_source
    from laplace.core.records import journal
    import uuid
    root = (root or _root()).resolve()
    project = str(payload.get('project') or '')
    record = registry.resolve(project, repo_root=root)
    if record is None or not record.manuscript_dir:
        return 404, {'error':'Choose a registered manuscript project.'}
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get('read_only'):
        return 403, {'error':'The imported source is read-only.'}
    if source.get('status') in {'resolved','ambiguous'}:
        return 409, {'error':'This project already has source material; choose its edition.'}
    home = record.path(record.manuscript_dir, root).resolve()
    if not home.is_relative_to(root):
        return 403, {'error':'The manuscript home is outside the active checkout.'}
    home.mkdir(parents=True, exist_ok=True)
    with FileLock(str(home/'.start-manuscript.lock'), timeout=15):
        draft = home/'working-draft'
        if draft.exists():
            return 409, {'error':'A working draft already exists; refresh the source choices.'}
        kind = payload.get('kind','paper')
        if kind not in {'book','paper'}:
            return 422, {'error':'Choose book or paper.'}
        title = str(payload.get('title') or project).strip()
        framing = authoring.load(project, root).get('framing',{})
        (root/'contract').mkdir(parents=True,exist_ok=True)
        ident = 'DRAFT-'+uuid.uuid4().hex
        from laplace.writing import records as writing_records  # the one seam; see change_metadata
        writing_records.bank(root, {'record':'manuscript-draft-start','id':ident,
            'project':project,'directory':draft.relative_to(root).as_posix(),'kind':kind,'title':title})
        draft.mkdir()
        made = _draft_source(draft,title,kind,framing.get('purpose',''))
        selected = manuscript_source.select(project,made[0].relative_to(root).as_posix(),repo_root=root)
        writing_records.bank(root, {'record':'manuscript-draft-ready','id':ident+'-ready',
            'project':project,'source':selected['root'],'files':[p.relative_to(root).as_posix() for p in made]})
    return 201, {'ok':True,'project':project,'source':selected,'receipt_id':ident}


def import_source(payload: dict, root: Path | None = None) -> tuple[int, dict]:
    root = (root or _root()).resolve(); name, title, raw = payload.get("name"), payload.get("title"), payload.get("root")
    if not isinstance(name, str) or not _NAME.fullmatch(name): return 422, {"error": "name must be a slug"}
    if not isinstance(title, str) or not title.strip() or not isinstance(raw, str): return 422, {"error": "title and root are required"}
    path = (root / raw).resolve()
    try: rel = path.relative_to(root).as_posix()
    except ValueError: return 422, {"error": "root must be a repository-relative source"}
    if path.suffix != ".tex" or not path.is_file() or not _DOC.search(path.read_text(encoding="utf-8", errors="replace")):
        return 422, {"error": "root must be an existing TeX document source"}
    from laplace.pipeline import registry
    from laplace.manuscript import manuscript_source
    if registry.resolve(name, root) is not None: return 409, {"error": "project name already exists"}
    # A source identity includes every registered selected root and candidate.
    # A new name may not launder a foreign/read-only tree into an editable one.
    existing: set[str] = set(); protected: list[Path] = []
    for project in registry.all_projects(root):
        source = manuscript_source.resolve(project, repo_root=root)
        roots = [source.get("root")] + [candidate.get("root") for candidate in source.get("candidates", []) if isinstance(candidate, dict)]
        for known in roots:
            if isinstance(known, str): existing.add(known)
        if source.get("foreign") or source.get("read_only"):
            for known in roots:
                if isinstance(known, str):
                    # Roots are TeX files; paths such as a foreign checkout
                    # named ``*.io`` are directories and must not be guessed
                    # from their suffix.
                    protected.append((root / known).resolve().parent)
            known_dir = source.get("manuscript_dir")
            if isinstance(known_dir, str):
                protected.append((root / known_dir).resolve())
    if any(path.is_relative_to(candidate) for candidate in protected):
        return 409, {"error": "source belongs to an already registered foreign/read-only project"}
    if rel in existing: return 409, {"error": "source is already registered"}
    editable = payload.get("editable") is True
    state_rel = f"writing_projects/{name}"
    state_dir = root / state_rel
    try:
        state_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        return 409, {"error": "project state directory already exists"}
    row = {"name": name, "kind": "conceptric", "project_dir": state_rel,
           "tex_root": path.parent.relative_to(root).as_posix(), "created_by": "projects-import",
           "manifest": {"display_name": title.strip(), "document": {"root": rel, "manuscript_dir": path.parent.relative_to(root).as_posix(), "edition": "imported", "read_only": not editable, "state_dir": state_rel},
                        "writing": {"kind": "imported", "purpose": "", "audience": ""}}}
    def mutate(rows):
        if any(existing.get("name") == name for existing in rows):
            raise ValueError("project name already exists")
        rows.append(row)
    try: _registry_write(root, mutate)
    except ValueError as exc:
        shutil.rmtree(state_dir)
        return 409, {"error": str(exc)}
    return 201, {"ok": True, "project": name, "source": rel, "copied": False, "rewritten": False,
                 "read_only": not editable, "state_dir": state_rel}


_MATERIAL_OWNERS = {"repository", "artifact"}
_REVISION = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")


def material_reference_contract() -> dict:
    """The same action payload shapes used by HTTP, agent help and native contracts."""
    text = {"type": "string", "minLength": 1}
    revision = {"type": "string", "minLength": 1}
    repository = {"type": "object", "additionalProperties": False,
        "required": ["owner", "repository", "path"],
        "properties": {"owner": {"const": "repository"}, "repository": text, "path": text}}
    artifact = {"type": "object", "additionalProperties": False,
        "required": ["owner", "project", "path", "scope"],
        "properties": {"owner": {"const": "artifact"}, "project": text, "path": text,
                       "scope": {"enum": ["project", "manuscript"]}}}
    common = {"project": text, "expected_revision": revision, "reason": {"type": "string"}, "by": {"type": "string"}}
    actions = {}
    for action, extras, required in (
        ("attach", {"target": {"oneOf": [repository, artifact]}, "consumed_revision": revision}, ["target", "consumed_revision"]),
        ("adopt", {"id": text, "consumed_revision": revision}, ["id", "consumed_revision"]),
        ("remove", {"id": text}, ["id"])):
        actions[action] = {"type": "object", "additionalProperties": False,
            "required": ["action", "expected_revision", *required],
            "properties": {**common, "action": {"const": action}, **extras}}
    # one JSON value by RFC 6901 pointer through the owning reader (campaign bounded source reading,
    # 2026-10-14): continuations carry the source pin; laplace.core.json_record states the rules
    record = {"pointer": {"type": "string", "maxLength": 4096},
              "expected_sha256": {"type": "string", "pattern": "^(sha256:)?[0-9a-fA-F]{64}$"}}
    return {"schema_version": "laplace.material-reference-contract/1",
        "read": {"oneOf": [
            {"type":"object","additionalProperties":False,"required":["view"],"properties":{
                "project":text,"by":{"type":"string"},"view":{"const":"intake"},"request_id":{"type":"string","minLength":8,"maxLength":96}}},
            {"type": "object", "additionalProperties": False, "properties": {"project": text, "by": {"type": "string"},
                "view": {"const": "list"}, "offset": {"type": "integer", "minimum": 0, "default": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50}}},
            {"type": "object", "additionalProperties": False, "required": ["id", "view"],
                "properties": {"project": text, "by": {"type": "string"}, "id": text, "view": {"const": "source"},
                    "offset": {"type": "integer", "minimum": 0, "maximum": 1000000000, "default": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 40000, "default": 16000},
                    "page": {"type": "integer", "minimum": 1},
                    "page_count": {"type": "integer", "minimum": 1, "maximum": 4}, **record}},
            {"type": "object", "additionalProperties": False, "required": ["target", "view"],
                "properties": {"project": text, "by": {"type": "string"},
                    "target": {"oneOf": [repository, artifact]}, "view": {"const": "preview"},
                    "offset": {"type": "integer", "minimum": 0, "maximum": 1000000000, "default": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 40000, "default": 16000},
                    "page": {"type": "integer", "minimum": 1},
                    "page_count": {"type": "integer", "minimum": 1, "maximum": 4}, **record}},
            {"type": "object", "additionalProperties": False, "required": ["view"],
                "properties": {"project": text, "by": {"type": "string"}, "view": {"const": "workspace"},
                    "consumer": text, "query": {"type": "string"}, "as_of": text,
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100}}},
            {"type": "object", "additionalProperties": False, "required": ["view", "consumer", "id"],
                "properties": {"project": text, "by": {"type": "string"}, "view": {"const": "workspace-source"},
                    "consumer": text, "id": text,
                    "offset": {"type": "integer", "minimum": 0, "maximum": 1000000000},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 40000},
                    "page": {"type": "integer", "minimum": 1},
                    "page_count": {"type": "integer", "minimum": 1, "maximum": 4}, **record}}]},
        "actions": actions, "write": {"oneOf": list(actions.values())},
        "law": "Registry membership only. Owner handles grant no target writes, proof validity or work completion. Current reads do not archive historical bytes. Adoption requires exact observed consumed_revision."}


def _material_target(root: Path, target: dict) -> dict:
    """Normalize handles through their content owner; a binding grants no writes."""
    if not isinstance(target, dict) or target.get("owner") not in _MATERIAL_OWNERS:
        raise ValueError("Material owner must be repository or artifact")
    if target["owner"] == "repository":
        if set(target) != {"owner", "repository", "path"} or not all(isinstance(target.get(k), str) and target[k] for k in ("repository", "path")):
            raise ValueError("Repository target requires only owner, repository and exact path")
        from laplace.projects import writing_sources
        return writing_sources.reference_identity(root, target)
    if set(target) != {"owner", "project", "path", "scope"} or not isinstance(target.get("project"), str) or not target["project"] or not isinstance(target.get("path"), str) or not target["path"]:
        raise ValueError("Artifact target requires only owner, project, exact path and scope")
    from laplace.projects import artifacts
    observed = artifacts.identity(root, target["project"],
                                     {"path": target["path"], "scope": target["scope"]})
    if not observed.get("exists"):
        raise ValueError("The owning project's artifact is absent")
    return {"owner": "artifact", "project": target["project"], "path": observed["artifact_path"],
            "scope": observed["scope"], "revision": observed["revision"],
            "read_handle": {"project": target["project"], "operation": "read_artifact",
                            "payload": {"path": observed["artifact_path"], "scope": observed["scope"]}}}


def workspace_material_references(root: Path, *, offset: int = 0, limit: int = 50,
                                  consumer: str | None = None, query: str = "",
                                  as_of: str | None = None) -> dict:
    """Page existing registry membership facts without reading any target contents."""
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0 or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Workspace references use nonnegative offset and limit 1–100")
    root = Path(root).resolve()
    path = root / "registry_projects.json"
    raw = path.read_bytes() if path.exists() else b'{"projects":[]}'
    revision = "sha256:" + hashlib.sha256(raw).hexdigest()
    if as_of and as_of != revision:
        raise ValueError("Registry revision conflict: workspace dependencies changed between pages. Refresh the dependency index.")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("projects"), list):
        raise ValueError("Project registry has no projects list")
    projects, rows, total, gaps = [], [], 0, []
    needle = query.casefold()
    for record in data["projects"]:
        if not isinstance(record, dict) or not isinstance(record.get("name"), str):
            continue
        name = record["name"]
        if not name or any(part in name for part in ("/", "\\", "..")):
            continue
        manifest = record.get("manifest") if isinstance(record.get("manifest"), dict) else {}
        title = manifest.get("display_name") or name
        projects.append({"id": name, "title": title,
            "href": "/project?workspace=writing&corpus=" + name})
        if consumer and consumer != name: continue
        bindings = manifest.get("material_references", [])
        if not isinstance(bindings, list):
            gaps.append({"consumer": name, "diagnostic": "Material membership is not a list"})
            continue
        for binding in bindings:
            if not isinstance(binding, dict) or not isinstance(binding.get("target"), dict) or not binding.get("id"):
                gaps.append({"consumer": name, "diagnostic": "A recorded membership lacks an exact target or id"})
                continue
            target = binding["target"]
            text = " ".join(str(value) for value in (name,title,target.get("owner"),target.get("project"),target.get("repository"),target.get("path"),binding["id"]))
            if needle and needle not in text.casefold():continue
            if offset <= total < offset + limit:
                rows.append({**binding, "consumer": {"project": name, "title": title},
                    "qualified_id": name + "::" + str(binding["id"]),
                    "currentness": "NOT_INSPECTED", "current_revision": None,
                    "write_permission": False,
                    "read_handle": {"operation": "material_references", "payload": {
                        "view": "workspace-source", "consumer": name, "id": binding["id"]}},
                    "consumer_href": "/project?workspace=writing&corpus=" + name + "&view=material"})
            total += 1
    return {"schema_version": "laplace.workspace-material-references/1", "scope": "workspace",
        "references": rows, "projects": projects, "total": total, "offset": offset, "limit": limit,
        "next_offset": offset + len(rows) if offset + len(rows) < total else None,
        "query": query, "consumer": consumer, "registry_revision": revision,
        "next_read": {"operation": "material_references", "payload": {
            "view": "workspace", "offset": offset + len(rows), "limit": limit,
            "as_of": revision, "query": query, **({"consumer": consumer} if consumer else {})}}
            if offset + len(rows) < total else None,
        "currentness_policy": "Target currentness is observed only on an explicit binding read, never while listing.",
        "coverage": [{"kind": "uses-material", "owner": "registry_projects.json manifest.material_references", "listing": "included"},
            {"kind": "task-prerequisites", "owner": "project_work", "listing": "project-local; open project Dependencies"},
            {"kind": "logical-evidential-links", "owner": "concepts_surface/literature_support", "listing": "typed project owners; open logical/research readers"},
            {"kind": "build-inputs", "owner": "build/context owner", "listing": "project-local; open output/build readers"}],
        "gaps": gaps, "write_permission": False}


def material_references(project: str, root: Path | None = None, *, offset: int = 0,
                        limit: int | None = None, id: str | None = None, view: str = "list",
                        page: int | None = None, page_count: int | None = None,
                        target: dict | None = None, consumer: str | None = None,
                        query: str = "", as_of: str | None = None,
                        pointer: str | None = None, expected_sha256: str | None = None, request_id: str | None = None) -> dict:
    """Project membership facts plus current owner observations, with no source bodies."""
    root = Path(root or _root()).resolve()
    if view=='intake':
        from laplace.projects import material_intake
        return material_intake.status(root,project,request_id) if request_id else material_intake.describe(root,project)
    if request_id is not None:raise ValueError('request_id belongs to the intake read only.')
    selection = {**({"pointer": pointer} if pointer is not None else {}),
              **({"expected_sha256": expected_sha256} if expected_sha256 is not None else {})}
    if selection and view not in {"source", "preview", "workspace-source"}:
        raise ValueError("pointer/expected_sha256 belong to a source, preview or workspace-source read")
    if view == "workspace":
        if id is not None or target is not None or page is not None or page_count is not None:
            raise ValueError("Workspace listing accepts consumer/query and reference-row pagination")
        return workspace_material_references(root, offset=offset, limit=50 if limit is None else limit,
                                             consumer=consumer, query=query, as_of=as_of)
    if as_of:
        raise ValueError("Registry page identity belongs to workspace dependency listing")
    if view == "workspace-source":
        if not isinstance(consumer, str) or not consumer or target is not None:
            raise ValueError("Workspace source read requires its exact consumer project and binding id")
        observed = material_references(consumer, root, view="source", id=id, offset=offset,
            limit=limit, page=page, page_count=page_count, **selection)
        for key in ("read_handle", "restart_read", "record_read", "page_read"):
            if observed.get(key):
                observed[key] = material_read_handle(consumer, {
                    **observed[key]["payload"], "view": "workspace-source", "consumer": consumer})
        if observed.get("record_read") or observed.get("page_read") or observed.get("restart_read"):
            observed["human_read"] = (observed.get("record_read") or observed.get("page_read") or observed["restart_read"])["human_read"]
        return {**observed, "scope": "workspace", "consumer": consumer}
    if consumer is not None or query:
        raise ValueError("Consumer/query filters belong to workspace reference listing")
    from laplace.pipeline import registry
    record = registry.resolve(project, root)
    if record is None:
        raise ValueError("Unknown project")
    meta = metadata(project, root)
    bindings = record.manifest.get("material_references", [])
    if not isinstance(bindings, list):
        raise ValueError("Material binding manifest is malformed")
    if view == "preview":
        if id is not None:
            raise ValueError("Preview uses a typed owner target, not a stored binding id")
        preview = {"id": None, "target": target, "consumed_revision": None}
        return {**_material_source(project, root, preview, offset=offset,
                    limit=_material_limit(limit, selection), page=page, page_count=page_count, record=selection),
                "revision": meta["revision"]}
    if view == "source":
        if target is not None:
            raise ValueError("Source view resolves its stored target; it accepts no replacement target")
        binding = next((b for b in bindings if isinstance(b, dict) and b.get("id") == id), None)
        if binding is None:
            raise ValueError("Choose an exact material reference id")
        return {**_material_source(project, root, binding, offset=offset, limit=_material_limit(limit, selection),
                                page=page, page_count=page_count, record=selection), "revision": meta["revision"]}
    if view != "list" or id is not None or target is not None or page is not None or page_count is not None:
        raise ValueError("List view accepts reference-row offset/limit; source view requires id")
    if limit is None: limit = 50
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0 or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("offset must be nonnegative and limit must be 1–100 reference rows")
    rows = []
    for binding in bindings[offset:offset + limit]:
        if not isinstance(binding, dict):
            raise ValueError("Material binding manifest contains a non-object reference")
        row = {**binding, "current_revision": None, "currentness": "UNRESOLVED", "write_permission": False}
        try:
            current = _material_target(root, binding["target"])
            if binding['target']['owner']=='artifact':
                from laplace.projects import artifacts
                original=artifacts.recorded_metadata(root,binding['target']['project'],binding['target']['path'],binding['target']['scope'])
                if original:row.update(display_name=original.get('display_name'),media_type=original.get('media_type'),original_read_only=True)
            row.update(current_revision=current["revision"], owner_read_handle=current["read_handle"],
                       read_handle={"project": project, "operation": "material_references",
                                    "payload": {"id": binding["id"], "view": "source"}},
                       currentness="CURRENT" if current["revision"].removeprefix("sha256:") == binding["consumed_revision"].removeprefix("sha256:") else "CHANGED_INPUT")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            row["diagnostic"] = str(exc)[:1000]
        rows.append(row)
    from laplace.projects import writing_sources
    owners = {"repositories": []}
    try:
        owners["repositories"] = writing_sources.inventory(root)["repositories"]
    except (OSError, ValueError, TypeError, KeyError) as exc:
        owners["diagnostic"] = "Repository choices are unavailable: " + str(exc)[:1000]
    return {"schema_version": "laplace.material-references/1", "project": project,
            "owners": owners,
            "revision": meta["revision"], "references": rows, "bounded": True, "limit": limit,
            "offset": offset, "total": len(bindings),
            "next_offset": offset + len(rows) if offset + len(rows) < len(bindings) else None,
            "policy": "pinned membership; owner read handles observe current content; prior bytes are not archived",
            "operations": ["attach", "adopt", "remove"], "write_permission": False}


def material_read_handle(project: str, payload: dict) -> dict:
    """One read-only native/HTTP handle for local and workspace source consumers."""
    from urllib.parse import urlencode
    fields = {"project": project, **payload}
    if isinstance(fields.get("target"), dict):
        fields["target"] = json.dumps(fields["target"], separators=(",", ":"))
    route = "/projects/material-references?" + urlencode(fields)
    return {"project": project, "operation": "material_references", "payload": dict(payload),
            "http": {"method": "GET", "url": route},
            "human_read": {"kind": "material-source", "project": project, "url": route,
                "content_policy": "current owner bytes; no historical-byte or acceptance grant"}}


def _material_http_read(query: dict) -> dict:
    """Decode the existing read contract once, without ambiguous URL coordinates."""
    from jsonschema import Draft202012Validator
    values = {}
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Material target has duplicate field: " + key)
            result[key] = value
        return result
    for key, items in query.items():
        if isinstance(items, str):
            items = [items]  # Existing in-process HTTP adapters supply scalar strings.
        if not isinstance(items, (list, tuple)) or len(items) != 1:
            raise ValueError("Material read requires one value per field: " + key)
        value = items[0]
        if key in {"offset", "limit", "page", "page_count"}:
            if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
                raise ValueError("Material read requires an unsigned integer: " + key)
            value = int(value)
        elif key == "target":
            value = json.loads(value, object_pairs_hook=unique_object)
        values[key] = value
    values.setdefault("view", "list")
    error = next(Draft202012Validator(material_reference_contract()["read"]).iter_errors(values), None)
    if error is not None:
        raise ValueError("Material read does not match its owner contract: " + error.message)
    return values


RECORD_RESTART_SEMANTICS = ("restart_read reads the CURRENT source from the first character of the selected value, "
                            "without the pin; human_read and read_handle keep the pin of the page they continue.")


def _material_limit(limit, record):
    """A JSON-record page defaults to json_record.POINTER_DEFAULT_LIMIT characters; a plain page to 16000."""
    if limit is not None:
        return limit
    from laplace.core import json_record
    return json_record.POINTER_DEFAULT_LIMIT if "pointer" in record else 16000


def _material_source(project: str, root: Path, binding: dict, *, offset: int, limit: int,
                     page: int | None, page_count: int | None, record: dict | None = None) -> dict:
    """Read the stored owner's current bytes from an active consumer without adopting."""
    from jsonschema import Draft202012Validator
    record = dict(record or {})
    preview = binding.get("id") is None
    request = {**({"target": binding["target"], "view": "preview"} if preview else
                  {"id": binding["id"], "view": "source"}), "offset": offset, "limit": limit,
               **({"page": page} if page is not None else {}),
               **({"page_count": page_count} if page_count is not None else {}), **record}
    error = next(Draft202012Validator(material_reference_contract()["read"]).iter_errors(request), None)
    if error is not None:
        raise ValueError("Material source request does not match its bounded read contract: " + error.message)
    target = binding["target"]
    result = {"schema_version": "laplace.material-reference-source/1", "project": project,
        "id": binding["id"], "target": target, "consumed_revision": binding["consumed_revision"],
        "current_revision": None, "currentness": "UNRESOLVED", "content_policy": "current owner bytes; consumed identity is not silently adopted",
        "write_permission": False, "owner_result": None}
    controls = {"offset": offset, "limit": limit, **record}
    try:
        if target.get("owner") == "repository":
            from laplace.projects import writing_sources
            observed = writing_sources.execute(root, {"action": "read", "repository": target["repository"],
                "path": target["path"], **controls,
                **({"page": page} if page is not None else {}),
                **({"page_count": page_count} if page_count is not None else {})})
            revision = observed["source"]["sha256"]
            # Qualify the owner's file identity by its declared alias, not host location.
            observed["source"] = {**observed["source"], "path": target["path"], "repository": target["repository"]}
            units = observed.get("units") or "Unicode characters; optional PDF pages select extracted text"
        elif target.get("owner") == "artifact":
            from laplace.projects import artifacts
            observed = artifacts.read(root, target["project"],
                {"path": target["path"], "scope": target["scope"], **controls,
                 **({"page":page} if page is not None else {}), **({"page_count":page_count} if page_count is not None else {})})
            revision = observed.get("revision")
            if not observed.get("exists"):
                raise ValueError("The owning project's artifact is absent")
            # Direct artifact calls select their project from the caller context.
            # Material must keep this target's qualified wrapper handles instead;
            # the existing JSON record/restart wrappers already carry that target.
            if observed.get('original_read'):result['original_read']=observed['original_read']
            observed = {k: v for k, v in observed.items() if k not in {"update_handle", "read_handle", "page_read", "human_read", "original_read"}
                        and not (k == "restart_read" and v.get("operation") == "read_artifact")}
            units = observed.get("units") or "UTF-8 byte offsets from the artifact owner's returned continuation"
        else:
            raise ValueError("Material reference has an unsupported owner")
        result.update(current_revision=revision, owner_result=observed, units=units,
            currentness="UNBOUND" if preview else "CURRENT" if revision.removeprefix("sha256:") == binding["consumed_revision"].removeprefix("sha256:") else "CHANGED_INPUT")
        # Character continuation stays inside the selected PDF page range. Only
        # after it finishes do we advance pages; all other controls stay unchanged.
        scope = {**request}
        if observed.get("pdf_page_start") is not None:
            scope["page"] = observed["pdf_page_start"]
            scope["page_count"] = page_count if page_count is not None else 1
        # the restart reads the current source from the first character (no pin)
        result["restart_read"] = material_read_handle(project, {**{key: value for key, value in scope.items() if key != "expected_sha256"}, "offset": 0})
        # Every continuation pins the observed raw source; pointer alone chooses JSON parsing.
        scope["expected_sha256"] = "sha256:" + str(revision).removeprefix("sha256:")
        if "pointer" in record:
            # repair1 R1: the human link opens THIS record page (pointer, offset, limit) under the same
            # pin, so a changed source is refused there too; restart_read is the separate unpinned
            # current-source read from the first character
            result["record_read"] = material_read_handle(project, {**scope, "offset": offset})
            result["restart_read_semantics"] = RECORD_RESTART_SEMANTICS
        else:
            result["page_read"] = material_read_handle(project, {**scope, "offset": offset})
        result["human_read"] = (result.get("record_read") or result["page_read"])["human_read"]
        result["link_instruction"] = ("Use human_read.url verbatim for the shared source reader. "
            "It is an owner route, not an artifact filename; current content does not adopt a consumed revision.")
        if observed.get("next_offset") is not None:
            result["read_handle"] = material_read_handle(project, {**scope, "offset": observed["next_offset"]})
        elif observed.get("pdf_page_end", 0) < observed.get("pdf_total_pages", 0):
            result["read_handle"] = material_read_handle(project, {
                **scope, "offset": 0, "page": observed["pdf_page_end"] + 1})
    except (OSError, ValueError, KeyError, TypeError) as exc:
        from laplace.core import json_record, source_pin
        if isinstance(exc, (json_record.RecordRefusal, source_pin.SourcePinRefusal)):
            raise   # a pointer, source-JSON, size or pin refusal answers the request; it is not owner unavailability
        result["diagnostic"] = str(exc)[:1000]
    return result


def change_material_reference(project: str, payload: dict, root: Path | None = None) -> dict:
    """Guard registry membership and the explicitly consumed owner revision separately."""
    from laplace.core import identity_doors
    identity_doors.admit_expected(payload, "material_reference_change")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    from laplace.core.receipts import bundle, file_receipt
    from laplace.writing import records as writing_records
    root = Path(root or _root()).resolve()
    from jsonschema import Draft202012Validator
    error = next(Draft202012Validator(material_reference_contract()["write"]).iter_errors(payload), None)
    if error is not None:
        raise ValueError("Material binding payload does not match its action contract: " + error.message)
    if payload.get("project", project) != project:
        raise ValueError("Material membership project does not match the selected project")
    action = payload["action"]
    path = root / "registry_projects.json"
    with FileLock(str(path) + ".lock", timeout=20):
        before_bytes = path.read_bytes()
        data = json.loads(before_bytes)
        row = next((r for r in data["projects"] if r.get("name") == project), None)
        if row is None:
            raise ValueError("Unknown project")
        before = _metadata(row)
        identity_doors.gate("project_metadata_change", supplied=payload,
            homes=[("project-metadata", project, before["revision"])], required=["expected_revision"],
            said="Project metadata revision conflict; read material references and retry")
        bindings = row.setdefault("manifest", {}).setdefault("material_references", [])
        if not isinstance(bindings, list):
            raise ValueError("Material binding manifest is malformed")
        selected = next((b for b in bindings if b.get("id") == payload.get("id")), None)
        if action != "attach" and selected is None:
            raise ValueError("Choose an existing material reference id")
        observed = None
        if action in {"attach", "adopt"}:
            consumed = payload.get("consumed_revision")
            if not isinstance(consumed, str) or not _REVISION.fullmatch(consumed):
                raise ValueError("Explicit consumed_revision must be the sha256 identity read from the owner")
            observed = _material_target(root, payload.get("target") if action == "attach" else selected["target"])
            if consumed.removeprefix("sha256:") != observed["revision"].removeprefix("sha256:"):
                raise ValueError("Material source revision conflict; read the owner and explicitly adopt its observed revision")
        if action == "attach":
            target = {k: v for k, v in observed.items() if k not in {"revision", "read_handle"}}
            if any(b.get("target") == target for b in bindings):
                raise ValueError("Material is already referenced; explicitly adopt its revision")
            selected = {"id": "MAT-" + uuid.uuid4().hex, "relation": "uses-material", "target": target,
                        "consumed_revision": observed["revision"], "version_policy": "pinned"}
            bindings.append(selected)
        elif action == "adopt":
            selected["consumed_revision"] = observed["revision"]
        else:
            bindings.remove(selected)
        after = _metadata(row)
        encoded = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
        ident = "MREF-" + uuid.uuid4().hex
        (root / "contract").mkdir(exist_ok=True)
        writing_records.bank(root, {"record": "material-reference-change-intent", "id": ident + "-intent",
            "project": project, "action": action, "reference": selected,
            "before_revision": before["revision"], "after_revision": after["revision"],
            "by": payload.get("by") or "author", "reason": payload.get("reason") or "Explicit material membership change"})
        staged = path.with_suffix(".tmp")
        staged.write_bytes(encoded)
        staged.replace(path)
        owned = file_receipt(root, path, before_bytes, encoded)
        writing_records.bank(root, {"record": "material-reference-change", "id": ident,
            "project": project, "action": action, "reference": selected,
            "before_revision": before["revision"], "after_revision": after["revision"]})
    return {"project": project, "revision": after["revision"], "reference": selected,
            "action": action, "record_id": ident, "write_permission": False,
            "qualification": "membership only; evidence and work completion are not asserted",
            "owned_changes": bundle(files=[owned], views=["project", "materials"])}


def app_settings_contract(*, require_scope: bool = True) -> dict:
    common = {"scope": {"const": "application", "default": "application"}, "by": {"type": "string"}}
    variants = []
    for view in ("summary", "runtime", "voice", "voice-provenance", "voice-calibration", "profile-contexts"):
        fields = {**common, "view": {"const": view}}
        required = (["scope"] if require_scope else []) + ([] if view == "summary" else ["view"])
        if view.startswith("voice"):
            fields["profile"] = {"type": "string"}
        if view == "voice-calibration":
            required.append("sources")
            fields.update(sources={"type": "array", "minItems": 1, "items": {"type": "object"}},
                          purpose={"type": "string"}, genre={"type": "string"})
        variants.append({"type": "object", "additionalProperties": False,
                         "required": required, "properties": fields})
    return {"oneOf": variants}


def app_voice_change_contract() -> dict:
    """HTTP wrapper derives every voice guard/input from the existing profile contract."""
    return {"oneOf": [{**schema, "required": ["action", *schema["required"]],
        "properties": {**schema["properties"], "action": {"const": "voice-profile"}}}
        for schema in style_profile_change_contract()["oneOf"]]}


def style_profile_change_contract() -> dict:
    """The writing_style_profile_change input this module's owner admits: an author preference or a source
    calibration, each with the literal owner attribution ``by``. The native schema table and the HTTP voice
    wrapper both read it here."""
    return {"oneOf": [{"type": "object", "required": ["profile", "content", "expected_profile_revision", "basis", "reason", "provenance_kind"], "properties": {"profile": {"type": "string"}, "content": {"type": "string"}, "expected_profile_revision": {"type": "string"}, "expected_provenance_revision": {"type": "string"}, "basis": {"const": "author_preference"}, "reason": {"type": "string"}, "provenance_kind": {"enum": ["direct-author-instruction", "structured-author-edit"]}, "judgement": {"type": "object", "required": [], "properties": {}, "additionalProperties": True}, "by": {"type": "string"}}, "additionalProperties": False}, {"type": "object", "required": ["profile", "content", "expected_profile_revision", "expected_provenance_revision", "basis", "reason", "source_handles", "judgement"], "properties": {"profile": {"type": "string"}, "content": {"type": "string"}, "expected_profile_revision": {"type": "string"}, "expected_provenance_revision": {"type": "string"}, "basis": {"const": "source_calibration"}, "reason": {"type": "string"}, "source_handles": {"type": "array", "minItems": 1, "items": {"type": "object", "required": ["path", "sha256"], "properties": {"path": {"type": "string"}, "sha256": {"type": "string"}}, "additionalProperties": False}}, "judgement": {"type": "object", "required": ["summary"], "properties": {"summary": {"type": "string"}, "retained": {"type": "array", "items": {"type": "string"}}, "changed": {"type": "array", "items": {"type": "string"}}, "genre_boundary": {"type": "string"}, "authorship_boundary": {"type": "string"}, "verification_limit": {"type": "string"}, "author_instruction": {"type": "string"}}, "additionalProperties": False}, "by": {"type": "string"}}, "additionalProperties": False}]}


def app_settings(root: Path | None = None, *, scope: str = "application", view: str = "summary",
                 profile: str | None = None, sources: list | None = None,
                 purpose: str = "", genre: str = "") -> dict:
    """Global configuration metadata and voice reads, with no project or startup discovery."""
    from laplace.manuscript import writing_style
    from laplace.core import runtime as core_runtime
    from laplace.pipeline import schema
    root = Path(root or _root()).resolve()
    if scope != "application": raise ValueError("App settings scope is application")
    if view != "voice-calibration" and (sources is not None or purpose or genre):
        raise ValueError("Source/genre/purpose fields belong to explicit voice calibration")
    if view in {"summary", "runtime"} and profile:
        raise ValueError("Profile selection belongs to explicit voice reads")
    if view == "profile-contexts":
        from laplace.pipeline import registry
        rows=[]
        for name,record in sorted(registry.all_projects(root).items()):
            relative=record.project_dir
            if not relative or record.kind=="site": continue
            path=(root/relative).resolve()
            if not path.is_relative_to(root) or not path.is_dir(): continue
            manifest=record.manifest if isinstance(record.manifest,dict) else {}
            rows.append({"name":name,"title":manifest.get("display_name") or name})
        return {"projects":rows,"scope":"workspace metadata only", "source_bodies_loaded":False,
                "purpose":"Explicit producing project for an actual profile-generation conversation; workspace effect is unchanged."}
    if view in {"voice", "voice-provenance"}:
        return writing_style.inspect(None, {"view": "profile" if view == "voice" else "provenance",
            **({"profile": profile} if profile else {})}, root)
    if view == "voice-calibration":
        return writing_style.calibration(None, {"sources": sources, "purpose": purpose, "genre": genre}, root,
            global_profile=profile)
    try:
        declared_runtime = core_runtime.configuration(root)
    except (OSError, ValueError) as exc:
        declared_runtime = {"path": "runtime_profiles.toml", "declared": {}, "diagnostic": str(exc)}
    runtime = {**declared_runtime, "observed": core_runtime.receipt(), "path": "runtime_profiles.toml",
        "configured": (declared_runtime.get("declared") or {}).get("lifecycle") or {},
        "mutable_from_app": False, "scope": "runtime interpreter/device policy; no startup installs or selection changes"}
    if view == "runtime": return runtime
    if view != "summary": raise ValueError("Unknown app settings view")
    from laplace.writing import provider_catalogue as _passive
    catalogue = _passive.provider_catalogue(root)
    try:
        voice = writing_style.global_catalogue(root)
    except (OSError, ValueError, KeyError) as exc:
        voice = {"scope": "global", "profiles": [], "diagnostic": str(exc)}
    return {"schema_version": "laplace.app-settings/1", "scope": "application",
        "providers": catalogue, "model_policy": schema.model_choice_declaration(), "runtime": runtime,
        "voice": {key: voice.get(key) for key in ("profile", "profile_revision", "profile_title", "profile_version", "profile_editable", "profile_edit_reason", "profiles", "scope", "diagnostic")},
        "operations": {"provider_refresh": {"path": "/authoring/providers?refresh=1", "effect": "explicit runtime discovery; not a writing turn"},
            "voice_read": {"path": "/projects/app-settings", "view": "voice"},
            "voice_change": {"path": "/projects/app-settings", "action": "voice-profile", "guards": ["expected_profile_revision", "source-calibration provenance when selected"]}},
        "gaps": [{"capability": "global-default-or-tier-write", "reason": "The current model policy is declared in pipeline.schema; no global mutation owner exists. Project/session defaults remain local."},
            {"capability": "runtime-selection-write", "reason": "Runtime selection is operator policy in runtime_profiles.toml; this page observes that existing owner."}]}


def handle(path: str, query: dict, method: str, body: bytes, repo_root=None) -> tuple[int, str, bytes] | None:
    if path != "/projects" and not path.startswith("/projects/"): return None
    method = (method or "GET").upper()
    root = Path(repo_root).resolve() if repo_root else _root()
    from laplace.projects import material_intake
    intake=material_intake.http(path,query,method,body,root)
    if intake is not None:return intake
    if path == "/projects/app-settings":
        try:
            if method == "GET":
                return _response(200, app_settings(root, scope=_q1(query, "scope") or "application", view=_q1(query, "view") or "summary",
                    profile=_q1(query, "profile") or None,
                    sources=json.loads(_q1(query, "sources")) if _q1(query, "sources") else None,
                    purpose=_q1(query, "purpose"), genre=_q1(query, "genre")))
            if method == "POST":
                from laplace.manuscript import writing_style
                payload = json.loads(body or b"{}")
                if not isinstance(payload, dict) or payload.get("action") != "voice-profile":
                    raise ValueError("App mutation is an explicit voice-profile edit")
                return _response(200, writing_style.update_global_profile({key: value for key, value in payload.items() if key != "action"}, root))
            return _response(405, {"error": "GET or POST only"})
        except (OSError, ValueError, KeyError) as exc:
            from laplace.core import identity_doors
            return _response(409 if "revision conflict" in str(exc) else 422,
                             identity_doors.body(exc, {"error": str(exc)}))
    if path == "/projects/material-references":
        try:
            if method == "GET":
                fields = _material_http_read(query)
                project = fields.pop("project", "")
                fields.pop("by", None)
                return _response(200, material_references(project, root, **fields))
            if method == "POST":
                payload = json.loads(body or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("body must be an object")
                return _response(200, change_material_reference(str(payload.get("project") or ""), payload, root))
            return _response(405, {"error": "GET or POST only"})
        except (OSError, ValueError, KeyError) as exc:
            from laplace.core import identity_doors
            return _response(409 if "revision conflict" in str(exc) else 422,
                             identity_doors.body(exc, {"error": str(exc)}))
    if path == "/projects/metadata":
        try:
            if method == "GET":
                return _response(200, metadata(_q1(query, "project"), root))
            if method == "POST":
                payload = json.loads(body or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("body must be an object")
                return _response(200, change_metadata(str(payload.get("project") or ""), payload, root))
            return _response(405, {"error": "GET or POST only"})
        except (OSError, ValueError, KeyError) as exc:
            from laplace.core import identity_doors
            return _response(409 if "revision conflict" in str(exc) else 422,
                             identity_doors.body(exc, {"error": str(exc)}))
    if path == "/projects/library": return _response(200, _library(root)) if method == "GET" else _response(405, {"error": "GET only"})
    if path == "/projects/discover": return _response(200, discover(root)) if method == "GET" else _response(405, {"error": "GET only"})
    if path in {"/projects/create", "/projects/import", "/projects/start"}:
        if method != "POST": return _response(405, {"error": "POST only"})
        try: payload = json.loads(body or b"{}")
        except (ValueError, TypeError): return _response(400, {"error": "bad json"})
        if not isinstance(payload, dict): return _response(400, {"error": "body must be an object"})
        status, out = create(payload, root) if path.endswith("create") else start_manuscript(payload,root) if path.endswith("start") else import_source(payload, root)
        return _response(status, out)
    return _response(404, {"error": "unknown projects route"})
