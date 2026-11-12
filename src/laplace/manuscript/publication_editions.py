"""Publication editions: named PDF editions of one canonical project source.

One project, one selected master root, one set of chapter files and shared
references.  An edition is a name, a title and the master chapter inputs it
keeps; the declaration is the project's registry row
(``manifest.publication_editions``), written only by
``writing_projects.change_metadata`` under the project-metadata revision.

Preparation derives one wrapper per edition beside the selected master root:
TeX and the include contract (``tex_dependencies.tex_input``) resolve
``\\input`` against the compile directory and refuse ``..``, so that is the one
placement that reads the same chapter files without copying them.  The wrapper
is the master preamble and body with only that edition's chapter lines, an
edition title and a companion line naming sibling PDFs by relative file name.
The master root and chapters are never written.  The wrapper's first line is
``manuscript_source.EDITION_WRAPPER_MARKER``, so it is never a selectable
source candidate.

The edition build target is issued here and built, cancelled, recorded and read
by the existing owners (build_targets, build_jobs, projection_viewer).
Currentness is per edition: the target pins this edition's definition, its
exact wrapper bytes and the declared-input snapshot of its own include tree.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode

KIND = "publication-edition"
NAME = r"^[a-z0-9][a-z0-9-]{0,47}$"
MAX_EDITIONS = 12
_NAME = re.compile(NAME)
_SOLE_INPUT = re.compile(r"^\s*\\(input|include)\s*\{\s*([^}]+?)\s*\}\s*$")
# Every active body token that reads another TeX file. Only a whole braced \input/\include line
# (_SOLE_INPUT) is admitted; any other occurrence (unbraced, split across lines, beside text, or
# another reading command) refuses, so it is never copied into every edition as shared body.
_ANY_INPUT = re.compile(r"\\@?(?:input|include|InputIfFileExists|subfile|subfileinclude|import|subimport"
                        r"|inputfrom|includefrom|subinputfrom|subincludefrom)(?![A-Za-z@])")
_LABEL = re.compile(r"\\label\s*\{([^}]+)\}")
_REF = re.compile(r"\\(?:ref|eqref|pageref|autoref|nameref|vref|cref|Cref|cpageref)\s*\*?\s*\{([^}]+)\}")


def definition_schema():
    return {"type": "array", "maxItems": MAX_EDITIONS, "items": {
        "type": "object", "required": ["name", "title", "chapters"], "additionalProperties": False,
        "properties": {"name": {"type": "string", "pattern": NAME},
                       "title": {"type": "string", "minLength": 1, "maxLength": 240},
                       "chapters": {"type": "array", "minItems": 1, "maxItems": 64,
                                    "items": {"type": "string", "minLength": 1}}}}}


def prepare_schema():
    return {"type": "object", "required": ["edition", "definition_revision"], "additionalProperties": False,
            "properties": {"edition": {"type": "string", "pattern": NAME},
                           "definition_revision": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"}}}


def target_schema():
    pins = {key: {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"} for key in (
        "selection_identity", "definition_revision", "preparation_revision", "input_revision")}
    return {"type": "object", "additionalProperties": False,
            "required": ["schema_version", "kind", "project", "edition", "root", "source_root", *pins],
            "properties": {"schema_version": {"const": "laplace.build-target/1"}, "kind": {"const": KIND},
                           "project": {"type": "string", "minLength": 1},
                           "edition": {"type": "string", "pattern": NAME},
                           "root": {"type": "string", "minLength": 1},
                           "source_root": {"type": "string", "minLength": 1}, **pins}}


def _refused(message, project, code="INVALID_TARGET"):
    from laplace.manuscript.build_targets import TargetRefused
    return TargetRefused(message, project, reason_code=code, next_reads=[read_handle(project)])


def _digest(value) -> str:
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _argument(value: str) -> str:
    value = value.strip().strip('"')
    return value[:-4] if value.lower().endswith(".tex") else value


def _code(line: str) -> str:
    from laplace.manuscript import manuscript_source
    return manuscript_source._uncomment(line)


def file_name(name: str) -> str:
    """The stable relative output name companions link to; the edition name is its identity."""
    return "edition-" + name + ".pdf"


# -- the canonical master ---------------------------------------------------------------------

def master(project: str, root: Path) -> dict:
    """The selected master root, split at its document environment; refuses unsupported layouts."""
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve(project, repo_root=root, include_candidates=False)
    if source.get("status") != "resolved" or not source.get("root"):
        raise _refused("Select the project's manuscript source before defining publication editions.", project, "NOT_CONFIGURED")
    if source.get("read_only") or source.get("foreign"):
        raise _refused("Publication editions are built beside an editable selected source; this source is read-only.", project, "READ_ONLY_SOURCE")
    path = (root / source["root"]).resolve()
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    begins = [i for i, line in enumerate(lines) if _code(line).strip() == "\\begin{document}"]
    ends = [i for i, line in enumerate(lines) if _code(line).strip() == "\\end{document}"]
    if len(begins) != 1 or len(ends) != 1 or ends[0] < begins[0]:
        raise _refused("Publication editions need \\begin{document} and \\end{document} each alone on one line of the selected root.",
                       project, "UNSUPPORTED_SOURCE_LAYOUT")
    chapters, mixed = [], []
    for line in lines[begins[0] + 1:ends[0]]:
        code = _code(line)
        sole = _SOLE_INPUT.match(code)
        if sole:
            chapters.append(_argument(sole.group(2)))
        elif _ANY_INPUT.search(code):
            mixed.append(code.strip())
    if mixed:
        raise _refused("Each body file input of the selected root must be a braced \\input{...} or \\include{...} alone on "
                       "its line to select editions; this one is refused: " + mixed[0],
                       project, "UNSUPPORTED_SOURCE_LAYOUT")
    if len(set(chapters)) != len(chapters):
        raise _refused("The selected root includes one chapter input twice; editions select chapters by input.", project, "UNSUPPORTED_SOURCE_LAYOUT")
    return {"source": source, "path": path, "root": path.relative_to(root).as_posix(), "lines": lines,
            "begin": begins[0], "end": ends[0], "chapters": chapters,
            "selection_identity": manuscript_source.selection_identity(source, project)}


# -- the declaration --------------------------------------------------------------------------

def declared(project: str, root: Path) -> list[dict]:
    try:
        rows = json.loads((Path(root) / "registry_projects.json").read_text())["projects"]
        row = next(row for row in rows if row.get("name") == project)
    except (OSError, ValueError, KeyError, StopIteration) as error:
        raise _refused("Project metadata is unavailable for this registered project.", project, "NOT_CONFIGURED") from error
    value = (row.get("manifest") or {}).get("publication_editions") or []
    return value if isinstance(value, list) else []


def validate(project: str, editions, root: Path) -> list[dict]:
    """The exact declaration admitted before any registry write; chapters are master chapter inputs."""
    from jsonschema import Draft202012Validator
    problem = next(Draft202012Validator(definition_schema()).iter_errors(editions), None)
    if problem:
        raise ValueError("publication_editions does not match its contract: " + problem.message)
    names = [edition["name"] for edition in editions]
    if len(set(names)) != len(names):
        raise ValueError("Publication edition names must be unique within the project.")
    if not editions:
        return []
    known = master(project, Path(root).resolve())["chapters"]
    clean = []
    for edition in editions:
        chapters = [_argument(chapter) for chapter in edition["chapters"]]
        unknown = [chapter for chapter in chapters if chapter not in known]
        if unknown or len(set(chapters)) != len(chapters):
            raise ValueError("Edition " + edition["name"] + " selects " + (", ".join(unknown) or "a chapter twice")
                             + "; choose among the selected root's chapter inputs: " + ", ".join(known))
        clean.append({"name": edition["name"], "title": " ".join(edition["title"].split()), "chapters": chapters})
    return clean


def _companions(editions, name):
    return [{"name": other["name"], "title": other["title"], "file": file_name(other["name"])}
            for other in editions if other["name"] != name]


def definition_revision(editions, name) -> str:
    """This edition's meaning: its own entry and the sibling names/titles its companion line consumes."""
    entry = next(edition for edition in editions if edition["name"] == name)
    return _digest({"edition": entry, "companions": [(other["name"], other["title"]) for other in editions
                                                    if other["name"] != name]})


# -- derivation -------------------------------------------------------------------------------

def _tex(value: str) -> str:
    escapes = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
               "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(escapes.get(char, char) for char in value)


def wrapper_path(base: dict, name: str) -> Path:
    return base["path"].parent / ("edition-" + name + ".tex")


def derive(project: str, base: dict, editions: list[dict], name: str) -> bytes:
    """Deterministic wrapper bytes from the master text and this edition's meaning only.

    The edition opening is its own visible title with its companion navigation on the same page:
    the edition title replaces the master title, and the companion line rides in the title block
    after the master's own date, so it can never fall onto a separate navigation-only page. An
    explicit master ``\\maketitle`` is reused, never duplicated; a master ``titlepage`` environment
    receives the edition title and navigation at its top; a master with neither opening gets one
    ``\\maketitle`` (in book-style classes a title page, in article-style classes a title block).
    """
    from laplace.manuscript import manuscript_source
    entry = next(edition for edition in editions if edition["name"] == name)
    keep, lines = set(entry["chapters"]), base["lines"]
    title = _tex(entry["title"])
    companions = _companions(editions, name)
    navigation = ("{\\small Companion editions: "
                  + "; ".join("\\LaplaceCompanion{" + other["file"] + "}{" + _tex(other["title"]) + "}" for other in companions)
                  + "\\endgraf}") if companions else ""
    body = lines[base["begin"] + 1:base["end"]]
    codes = [_code(line) for line in body]
    explicit = any("\\maketitle" in code for code in codes)
    titlepage = next((i for i, code in enumerate(codes) if re.search(r"\\begin\s*\{titlepage\}", code)), None)
    out = [manuscript_source.EDITION_WRAPPER_MARKER + " project=" + project + " edition=" + name + "\n",
           "% Derived from " + base["root"] + " by the publication-edition owner; edit the canonical source, not this file.\n",
           *lines[:base["begin"]],
           "\\makeatletter\n",
           "\\@ifundefined{href}{\\providecommand\\LaplaceCompanion[2]{#2 (\\texttt{#1})}}{\\providecommand\\LaplaceCompanion[2]{\\href{#1}{#2}}}\n",
           "\\@ifundefined{hypersetup}{}{\\hypersetup{pdftitle={" + title + "}}}\n",
           "\\let\\LaplaceMasterDate\\@date\n",
           "\\makeatother\n",
           "\\title{" + title + "}\n",
           # \\date is not \\long, so the paragraph break is \\endgraf rather than \\par.
           *(["\\date{\\LaplaceMasterDate\\endgraf\\medskip " + navigation + "}\n"] if companions else []),
           *(["\\newcommand\\LaplaceEditionOpening{\\begin{center}{\\LARGE\\bfseries " + title + "\\par}\\medskip "
              + navigation + "\\end{center}}\n"] if titlepage is not None and not explicit else []),
           lines[base["begin"]],
           *(["\\maketitle\n"] if not explicit and titlepage is None else [])]
    for index, line in enumerate(body):
        sole = _SOLE_INPUT.match(codes[index])
        if sole:
            argument = _argument(sole.group(2))
            if argument not in keep:
                continue
            # \include's per-chapter .aux is shared with the master build; an edition reads the chapter by \input.
            out.append(("\\clearpage\\input{" + sole.group(2) + "}\\clearpage\n") if sole.group(1) == "include" else line)
        elif index == titlepage and not explicit:
            # The opening goes immediately after the matched \\begin{titlepage} token (inside the title page even
            # when begin, content and end share one line); a line holding only the token keeps its own line.
            begin = re.search(r"\\begin\s*\{titlepage\}", codes[index]).end()
            rest = line[begin:]
            out.append(line + "\\LaplaceEditionOpening\n" if not rest.strip()
                       else line[:begin] + "\\LaplaceEditionOpening " + rest)
        else:
            out.append(line)
    out.extend(lines[base["end"]:])
    return "".join(out).encode("utf-8")


def unsupported_references(base: dict, editions: list[dict], name: str, root: Path) -> list[dict]:
    """References in this edition whose label lives only in a chapter it omits: qualified, never linked."""
    from laplace.manuscript import manuscript_source
    tree = manuscript_source.traversal(base["path"], repo_root=root)
    master_rel = base["root"]
    parents = {source["file"]: source["parent"] for source in tree.get("sources", [])}
    texts = {source["file"]: _code(source["text"]) for source in tree.get("sources", [])}
    top = {}
    for include in tree.get("includes", []):
        if include["parent"] == master_rel:
            top.setdefault(include["target"], _argument(include["argument"]))

    def chapter_of(file):
        while file is not None and file not in top:
            file = parents.get(file)
        return top.get(file) if file is not None else None

    entry = next(edition for edition in editions if edition["name"] == name)
    kept = set(entry["chapters"])
    selected = {file for file in texts if file == master_rel or chapter_of(file) is None or chapter_of(file) in kept}
    labels = {}
    for file, text in texts.items():
        for label in _LABEL.findall(text):
            labels.setdefault(label.strip(), file)
    defined_here = {label for file in selected for label in _LABEL.findall(texts[file])}
    owner = {chapter: edition["name"] for edition in editions for chapter in edition["chapters"]}
    rows = []
    for file in sorted(selected):
        for group in _REF.findall(texts[file]):
            for label in (part.strip() for part in group.split(",")):
                if label and label not in defined_here and label in labels:
                    chapter = chapter_of(labels[label])
                    rows.append({"label": label, "file": file, "defined_in": labels[label],
                                 "companion": owner.get(chapter),
                                 "treatment": "UNSUPPORTED_CROSS_EDITION_REFERENCE: printed unresolved; read the companion edition"})
    return rows


# -- issue / resolve / prepare ----------------------------------------------------------------

def _entry(project, root, name):
    editions = declared(project, root)
    if not any(edition.get("name") == name for edition in editions):
        raise _refused("This project declares no publication edition named " + repr(name) + ".", project, "UNKNOWN_EDITION")
    return editions


def issue(project: str, root: Path, name: str) -> dict:
    from laplace.manuscript import tex_dependencies
    root = Path(root).resolve()
    editions = _entry(project, root, name)
    base = master(project, root)
    data = derive(project, base, editions, name)
    wrapper = wrapper_path(base, name)
    if not wrapper.is_file():
        raise _refused("Publication edition " + name + " is not prepared yet.", project, "NOT_PREPARED")
    if wrapper.read_bytes() != data:
        raise _refused("Publication edition " + name + " changed in its definition or canonical root; prepare it again.",
                       project, "PREPARATION_STALE")
    inputs = tex_dependencies.snapshot(wrapper, root, use_recorder=False)
    return {"schema_version": "laplace.build-target/1", "kind": KIND, "project": project, "edition": name,
            "root": wrapper.relative_to(root).as_posix(), "source_root": base["root"],
            "selection_identity": base["selection_identity"],
            "definition_revision": definition_revision(editions, name),
            "preparation_revision": _digest(data), "input_revision": _digest(inputs)}


def resolve(target: dict, project: str, root: Path) -> Path:
    if target.get("project") != project:
        raise _refused("This publication-edition target belongs to another project.", project, "WRONG_PROJECT")
    current = issue(project, root, target["edition"])
    if target != current:
        raise _refused("Publication edition " + target["edition"] + " changed since this target was issued; inspect it again.",
                       project, "TARGET_CHANGED")
    return Path(root).resolve() / current["root"]


def prepare(project: str, payload: dict, root: Path) -> dict:
    """Write one edition's derived wrapper under its definition guard; never the canonical source.

    The check and the publication happen while holding the compiler's own per-root mutex for the
    wrapper (projection_viewer._recompile_lock_path), the same exclusion a build of that edition
    holds from admission to terminal state: a running build refuses preparation, and a build that
    validated its target earlier revalidates once it holds that mutex (projection_viewer.recompile).
    """
    from filelock import FileLock, Timeout
    from laplace.manuscript import manuscript_source, projection_viewer
    from laplace.core.receipts import bundle, file_receipt
    from laplace.manuscript import build_jobs
    from jsonschema import Draft202012Validator
    root = Path(root).resolve()
    request = payload.get("prepare")
    if set(payload) - {"prepare", "project"} or next(Draft202012Validator(prepare_schema()).iter_errors(request), None):
        raise _refused("Preparation is exactly the edition's prepare_action {prepare:{edition,definition_revision}}.", project)
    name, expected = request["edition"], request["definition_revision"]
    _entry(project, root, name)
    wrapper = wrapper_path(master(project, root), name)
    boundary = FileLock(str(projection_viewer._recompile_lock_path(wrapper)), timeout=0, thread_local=False)
    try:
        boundary.acquire()
    except Timeout:
        raise _refused("Publication edition " + name + " is building; wait for or stop that build before preparing it.",
                       project, "BUILD_ACTIVE") from None
    try:
        prior = projection_viewer._read_recompile_status(wrapper)
        if build_jobs.processes_active(prior) or prior.get("cleanup_unproved") or prior.get("state") in build_jobs.ACTIVE:
            raise _refused("Publication edition " + name + " has an unfinished build; inspect or stop it before preparing.",
                           project, "BUILD_ACTIVE")
        editions = _entry(project, root, name)
        if expected != definition_revision(editions, name):
            raise _refused("Publication edition " + str(name) + " definition changed; read the editions and use the returned prepare_action.",
                           project, "DEFINITION_CHANGED")
        base = master(project, root)
        if wrapper_path(base, name) != wrapper:
            raise _refused("The selected root changed while preparing; read the editions again.", project, "TARGET_CHANGED")
        data = derive(project, base, editions, name)
        before = wrapper.read_bytes() if wrapper.is_file() else None
        if before is not None and not manuscript_source.edition_wrapper(before.decode("utf-8", errors="replace")):
            raise _refused(wrapper.name + " already exists as an authored file; rename it before preparing this edition.",
                           project, "OCCUPIED")
        owned = []
        if before != data:
            staged = wrapper.with_name(wrapper.name + ".prepare-tmp")
            staged.write_bytes(data)
            os.replace(staged, wrapper)
            owned.append(file_receipt(root, wrapper, before, data))
    finally:
        boundary.release()
    # A bounded receipt: the issued target and its actions; the edition read carries detail.
    view = read(project, root, edition=name)["editions"][0]
    return {"schema_version": "laplace.publication-edition-preparation/1", "project": project, "edition": name,
            "status": view["status"], "file": view["file"], "unchanged": not owned, "read_handle": read_handle(project),
            **{key: view[key] for key in ("build_target", "build_action", "status_read") if key in view},
            "owned_changes": bundle(files=owned, views=["document"])}


# -- inspection -------------------------------------------------------------------------------

def read_handle(project: str) -> dict:
    payload = {"target_kind": KIND}
    return {"operation": "document", "payload": payload,
            "http": {"method": "GET", "url": "/authoring/document?" + urlencode({"project": project, **payload})}}


def _metadata_revision(project, root):
    from laplace.projects import library as writing_projects
    rows = json.loads((root / "registry_projects.json").read_text())["projects"]
    row = next(row for row in rows if row.get("name") == project)
    return writing_projects._metadata(row)


def read(project: str, root: Path, *, edition: str | None = None) -> dict:
    """Every declared edition (one, for a preparation receipt), with its state, actions, companions and
    canonical-source return."""
    from laplace.manuscript import build_targets
    root = Path(root).resolve()
    result = {"schema_version": "laplace.publication-editions/1", "project": project, "target_kind": KIND,
              "read_handle": read_handle(project),
              "canonical_source": {"read": {"operation": "document", "payload": {},
                                            "http": {"method": "GET", "url": "/authoring/document?" + urlencode({"project": project})}}},
              "sequence": ["define: project_metadata_change publication_editions (POST /projects/metadata) under expected_revision",
                           "prepare: build {prepare: {edition, definition_revision}} (POST /authoring/build)",
                           "build: build {build_target} (POST /authoring/build); status: build_status {build_target}",
                           "read/download: pdf_read (GET /projection/pdf); save it as download_name so companion links resolve"]}
    try:
        meta = _metadata_revision(project, root)
        editions = declared(project, root)
        result["definition"] = {"field": "publication_editions", "editions": editions,
            "define_action": {"operation": "project_metadata_change", "project": project,
                "payload": {"title": meta["title"], "expected_revision": meta["revision"], "publication_editions": editions},
                "http": {"method": "POST", "route": "/projects/metadata"}}}
        base = master(project, root)
        result["canonical_source"].update(root=base["root"], selection_identity=base["selection_identity"])
        result["chapter_inputs"] = base["chapters"]
    except (ValueError, OSError, KeyError, StopIteration) as error:
        return {**result, "status": "UNAVAILABLE", "reason": str(error), "editions": [],
                **build_targets.error_details(error)}
    chosen = [entry for entry in editions if edition in (None, entry["name"])]
    if edition is not None and not chosen:
        return {**result, "status": "UNAVAILABLE", "reason_code": "UNKNOWN_EDITION", "editions": [],
                "reason": "This project declares no publication edition named " + repr(edition) + "."}
    result["status"] = "AVAILABLE" if editions else "NOT_DEFINED"
    result["editions"] = [_edition_view(project, root, base, editions, entry) for entry in chosen]
    return result


def _edition_view(project, root, base, editions, entry):
    from laplace.manuscript import build_targets
    name = entry["name"]
    wrapper = wrapper_path(base, name)
    revision = definition_revision(editions, name)
    view = {"name": name, "title": entry["title"], "chapters": entry["chapters"],
            "definition_revision": revision, "file": wrapper.relative_to(root).as_posix(),
            "download_name": file_name(name), "companions": _companions(editions, name),
            "unsupported_references": unsupported_references(base, editions, name, root),
            "prepare_action": {"operation": "build", "project": project,
                "payload": {"prepare": {"edition": name, "definition_revision": revision}},
                "http": {"method": "POST", "route": "/authoring/build"}}}
    try:
        target = issue(project, root, name)
    except build_targets.TargetRefused as refused:
        code = refused.details.get("reason_code")
        view.update(status={"NOT_PREPARED": "UNPREPARED"}.get(code, code), reason=str(refused), reason_code=code,
                    **build_targets.recorded_view(project, root, wrapper, None))
        return view
    view.update(build_targets.output_view(project, root, target))
    return view
