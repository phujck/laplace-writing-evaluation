"""Transactional creation of an empty titled chapter or section."""
from __future__ import annotations
from laplace.core.checkout import source_tree

import hashlib
from contextvars import ContextVar
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import uuid
from typing import Mapping

from filelock import FileLock

from laplace.core import identity_doors
from laplace.manuscript import manuscript_bridge, manuscript_source
from laplace.core.records import journal

_MUTATION = ContextVar("manuscript_structure_mutation", default=None)


def _plan_write(*args, **kwargs):
    from laplace.manuscript import storyboard
    result = storyboard.plan_write(*args, **kwargs)
    context = _MUTATION.get()
    if context is not None:
        context["owned"].extend((result.get("owned_changes") or {}).get("files") or [])
    return result


_CLASS = re.compile(r"\\documentclass\s*(?:\[[^]]*\])?\s*\{\s*([^}]+)\s*\}")
_INSERT_BEFORE = re.compile(
    r"\\(?:bibliographystyle|bibliography|printbibliography)\b|"
    r"\\begin\s*\{thebibliography\}|\\end\s*\{document\}")
_TITLE_ESCAPES = {
    "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_STRUCTURE_HEADING_START = re.compile(
    r"\\(part|chapter|section|subsection|subsubsection)\*?\s*\{")
_STRUCTURE_LEVEL = {
    "part": 0, "chapter": 1, "section": 2, "subsection": 3, "subsubsection": 4,
}


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(path: Path) -> str:
    return _digest_bytes(path.read_bytes())


def _escape(value: str) -> str:
    return "".join(_TITLE_ESCAPES.get(char, char) for char in value)


def _normal_title(value: str) -> str:
    title = " ".join(str(value or "").split())
    if not title:
        raise ValueError("title is required")
    if len(title) > 240:
        raise ValueError("title is too long")
    return title


def _selected(project: str, root: Path, *, allow_empty: bool = False) -> tuple[dict, Path, Path]:
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("read_only"):
        raise ValueError("selected manuscript source is read-only")
    allowed_status = {"resolved", "empty"} if allow_empty else {"resolved"}
    if source.get("status") not in allowed_status or not source.get("root") or not source.get("manuscript_dir"):
        raise ValueError("no selected manuscript root")
    main = (root / source["root"]).resolve()
    manuscript = (root / source["manuscript_dir"]).resolve()
    try:
        main.relative_to(root)
        main.relative_to(manuscript)
        manuscript.relative_to(root)
    except ValueError as exc:
        raise ValueError("selected manuscript paths escape the active checkout") from exc
    if main.suffix.lower() != ".tex" or not main.is_file() or not manuscript.is_dir():
        raise ValueError("selected manuscript root is not a local TeX file")
    return source, main, manuscript


@contextmanager
def _source_scope(project: str, root: Path, source: dict, extra=()):
    """Source and required plan compensation share the full physical scope.

    The structure feature lock is already outer. Plan transactions are leaves;
    no plan-owned caller may acquire a physical source lease from inside them.
    """
    def namespace():
        return {(root / name).resolve() for name in manuscript_source.traversal(source["root"], repo_root=root).get("files", [])}
    selected_paths = namespace()
    try:
        with manuscript_source.selection_mutation(project, root), manuscript_source.source_mutation(selected_paths | {Path(path).resolve() for path in extra}):
            current = manuscript_source.resolve(project, repo_root=root)
            if any(current.get(key) != source.get(key) for key in ("root", "manuscript_dir", "edition", "read_only")) or namespace() != selected_paths:
                raise ValueError("selected source namespace changed; refresh the structure operation")
            yield
    except manuscript_source.SourceLeaseError as exc:
        raise ValueError(str(exc)) from exc


def _chapter_plan(main: Path, manuscript: Path, title: str) -> tuple[Path, str, str, str]:
    text = main.read_text(encoding="utf-8")
    match = _CLASS.search(text)
    if match is None:
        raise ValueError("selected manuscript root has no documentclass")
    document_class = match.group(1).strip().lower()
    level = "chapter" if document_class in {"book", "report", "memoir"} else "section"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or level
    directory = manuscript / "chapters" if (manuscript / "chapters").is_dir() else manuscript
    target = (directory / f"{slug}.tex").resolve()
    try:
        target.relative_to(manuscript)
    except ValueError as exc:
        raise ValueError("chapter path escapes the selected manuscript") from exc
    argument = target.relative_to(manuscript).with_suffix("").as_posix()
    input_line = f"\\input{{{argument}}}\n"
    if re.search(r"\\(?:input|include)\s*\{\s*" + re.escape(argument) + r"(?:\.tex)?\s*\}", text):
        raise ValueError("chapter is already included by the selected root")
    insert = _INSERT_BEFORE.search(text)
    position = insert.start() if insert else len(text)
    separator = "" if position == 0 or text[:position].endswith("\n") else "\n"
    updated = text[:position] + separator + input_line + text[position:]
    chapter = f"\\{level}{{{_escape(title)}}}\n\\label{{{level}:{slug}}}\n\n"
    return target, chapter, text, updated


def _stage_main(main: Path, updated: str) -> Path:
    return manuscript_source.stage_source(main, updated.encode("utf-8"))


def _create_chapter_owned(project: str, title: str, root=None,
                   expected_root_digest: str | None = None) -> dict:
    root = Path(root).resolve() if root else source_tree()
    title = _normal_title(title)
    source, main, manuscript = _selected(project, root)
    lock = manuscript / ".structure.lock"
    with FileLock(str(lock), timeout=30):
        # Resolve again inside the interprocess lock: edition and permissions may
        # have changed while this caller waited.
        source, main, manuscript = _selected(project, root)
        declared_target = _chapter_plan(main, manuscript, title)[0]
        with _source_scope(project, root, source, [declared_target]):
            before_digest = _digest(main)
            expected = str(expected_root_digest or "").removeprefix("sha256:")
            if expected and expected != before_digest:
                raise ValueError("selected manuscript root changed; refresh before creating the chapter")
            target, chapter_text, before, after = _chapter_plan(main, manuscript, title)
            if target != declared_target:
                raise ValueError("chapter target changed; refresh before creating the chapter")
            if target.exists():
                raise ValueError("chapter filename already exists")
            if len(before.encode("utf-8")) > 2_000_000:
                raise ValueError("selected manuscript root is too large for an atomic structure edit")
            chapter_bytes, after_bytes = chapter_text.encode("utf-8"), after.encode("utf-8")
            operation_id = "MSC-" + uuid.uuid4().hex
            relative_main = main.relative_to(root).as_posix()
            relative_target = target.relative_to(root).as_posix()
            intent = {
                "record": "manuscript-structure", "id": operation_id, "project": project,
                "operation": "create-chapter", "title": title,
                "before": {"root": before, "chapter": None},
                "after": {"root": after, "chapter": chapter_text},
                "paths": {"root": relative_main, "chapter": relative_target},
                "digests": {"root_before": before_digest, "root_after": _digest_bytes(after_bytes),
                            "chapter_after": _digest_bytes(chapter_bytes)},
            }
            (root / "contract").mkdir(parents=True, exist_ok=True)
            journal.bank_row("contract/talk.jsonl", intent, root=root)
            feedback = manuscript_bridge.feedback_add(root, project, {
                "node_id": relative_target, "kind": "author-structure", "by": "author",
                "comment": f"Created empty {('chapter' if chapter_text.startswith('\\chapter') else 'section')} {title!r} and included it from the selected root.",
                "anchor": {"file": relative_main, "before": before, "after": after,
                           "created_file": relative_target, "operation_id": operation_id},
            }, ledger=manuscript / "feedback" / "feedback.jsonl")
            if feedback.get("error"):
                raise ValueError("chapter feedback receipt refused: " + str(feedback["error"]))

            staged = _stage_main(main, after)
            created = False
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as handle:
                    handle.write(chapter_bytes)
                    handle.flush()
                    os.fsync(handle.fileno())
                created = True
                from laplace.manuscript.source_effects import publish
                publish(staged, main)
            except Exception as exc:
                staged.unlink(missing_ok=True)
                # Delete only the file created by this operation, and only while its
                # bytes still equal the intended empty chapter. Never remove a file
                # another process changed after creation.
                if created:
                    try:
                        if target.is_file() and target.read_bytes() == chapter_bytes:
                            target.unlink()
                    except OSError:
                        pass
                from laplace.manuscript import source_effects
                effect = source_effects.receipt(project,
                    manuscript_source.selection_identity(source, project),
                    [source_effects.observed_file(root, main, before.encode('utf-8'), after_bytes),
                     source_effects.observed_file(root, target, None, chapter_bytes)],
                    complete=False, required=[{'owner':'chapter-source-publication','status':'FAILED','reason':str(exc)}])
                raise source_effects.SourceEffectFailure(exc, effect) from exc

            from laplace.manuscript import source_effects
            effect = source_effects.receipt(project, manuscript_source.selection_identity(source, project),
                [source_effects.observed_file(root, main, before.encode('utf-8'), after_bytes),
                 source_effects.observed_file(root, target, None, chapter_bytes)],
                required=[{'owner':'chapter-source','status':'COMPLETE'}])
            try:
                from laplace.manuscript import projection_viewer
                root_version = projection_viewer.bank_editor_save(
                    manuscript, main, after_bytes, author="author", surface="writing-structure",
                    source="chapter-create")
                chapter_version = projection_viewer.bank_editor_save(
                    manuscript, target, chapter_bytes, author="author", surface="writing-structure",
                    source="chapter-create")
                completion = {
                    "record": "manuscript-structure-complete", "id": "MSCD-" + uuid.uuid4().hex,
                    "supersedes": operation_id, "project": project,
                    "root_digest": _digest(main), "chapter_digest": _digest(target),
                    "feedback_id": (feedback.get("record") or {}).get("id"),
                    "versions": [root_version.get("version_id"), chapter_version.get("version_id")],
                }
                journal.bank_row("contract/talk.jsonl", completion, root=root)
                return {
                    "file": relative_target, "root": relative_main, "root_digest": completion["root_digest"],
                    "receipt": {"id": operation_id, "project": project,
                                "kind": "chapter" if chapter_text.startswith("\\chapter") else "section",
                                "title": title, "feedback_id": completion["feedback_id"],
                                "versions": completion["versions"]},
                    "document": source, "source_effect": effect,
                    "next_read": {"operation":"source", "payload":{"files":[target.relative_to(manuscript).as_posix()], "line_start":1, "line_end":min(120,len(chapter_text.splitlines()))}},
                }

            except Exception as exc:
                effect['complete'] = False
                effect['follow_through']['required'].append({'owner':'structure-tracking','status':'UNPROVED','reason':str(exc)})
                raise source_effects.SourceEffectFailure(exc, effect) from exc


def _guard(value: object) -> str:
    return str(value or "").removeprefix("sha256:")


def _heading_matches(text: str) -> list[dict]:
    """Active TeX headings with balanced title braces and stable source offsets."""
    visible = list(text)
    for line_start in range(0, len(text) + 1):
        if line_start and text[line_start - 1] != "\n":
            continue
        line_end = text.find("\n", line_start)
        if line_end < 0:
            line_end = len(text)
        for index in range(line_start, line_end):
            if text[index] != "%":
                continue
            slashes = 0
            cursor = index - 1
            while cursor >= line_start and text[cursor] == "\\":
                slashes += 1; cursor -= 1
            if slashes % 2 == 0:
                visible[index:line_end] = " " * (line_end - index)
                break
    masked = "".join(visible)
    from bisect import bisect_right
    line_starts = [0] + [index + 1 for index, char in enumerate(text) if char == "\n"]
    rows = []
    for match in _STRUCTURE_HEADING_START.finditer(masked):
        depth, cursor = 1, match.end()
        while cursor < len(masked) and depth:
            char = masked[cursor]
            escaped = cursor > 0 and masked[cursor - 1] == "\\"
            if char == "{" and not escaped:
                depth += 1
            elif char == "}" and not escaped:
                depth -= 1
            cursor += 1
        if depth:
            continue
        rows.append({"start": match.start(), "end": cursor, "kind": match.group(1),
                     "title": text[match.end():cursor - 1].strip(),
                     "line": bisect_right(line_starts, match.start())})
    return rows


def _source_span(text: str, title: str = "", kind: str | None = None,
                 line_start: int | None = None) -> tuple[int, int]:
    """Locate one heading and all subordinate source below it.

    The next heading at the same or a higher level closes the span.  Ambiguous
    duplicate headings are refused: a destructive structure edit must have one
    exact source address.
    """
    matches = _heading_matches(text)
    candidates = [index for index, match in enumerate(matches)
                  if (line_start is None or match["line"] == line_start)
                  and (line_start is not None or not title or match["title"] == title)
                  and (not kind or match["kind"] == kind)]
    if len(candidates) != 1:
        detail = "not found" if not candidates else "ambiguous"
        raise ValueError(f"section heading is {detail} in its selected source file")
    index = candidates[0]
    match = matches[index]
    level = _STRUCTURE_LEVEL[match["kind"]]
    end = len(text)
    for following in matches[index + 1:]:
        if _STRUCTURE_LEVEL[following["kind"]] <= level:
            end = following["start"]
            break
    document_tail = _INSERT_BEFORE.search(text, match["end"])
    if document_tail is not None:
        end = min(end, document_tail.start())
    return match["start"], end


def _source_path(root: Path, manuscript: Path, value: object) -> Path:
    """Compatibility adapter for the shared source coordinate normalizer."""
    return manuscript_source.source_path(root, manuscript, value)


def _plan_sections(plan: dict, section_id: str) -> list[dict]:
    for collection in ("sections", "appendices"):
        rows = list(plan.get(collection) or [])
        if any(section.get("id") == section_id for section in rows):
            doomed = {section_id}
            while True:
                children = {str(section.get("id")) for section in rows
                            if section.get("parent_id") in doomed}
                if children <= doomed:
                    break
                doomed.update(children)
            return [{"collection": collection, "index": index, "section": section}
                    for index, section in enumerate(rows) if section.get("id") in doomed]
    raise ValueError("section is unavailable in the current projection plan")


def _receipt(root: Path, receipt_id: str, project: str) -> dict:
    path = root / "contract" / "talk.jsonl"
    if not path.is_file():
        raise ValueError("section deletion receipt is unavailable")
    found = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (row.get("record") == "manuscript-section-change"
                and row.get("id") == receipt_id and row.get("operation") == "delete"):
            found = row
    if found is None or found.get("project") != project:
        raise ValueError("section deletion receipt is unavailable for this project")
    return found


def _structure_state(project: str, root: Path) -> dict:
    """Canonical structure state, or a guarded source-only state without a plan."""
    from laplace.manuscript import project_structure
    try:
        return project_structure.state(project, root)
    except ValueError as exc:
        if "canonical projection plan" not in str(exc).lower():
            raise
    source = manuscript_source.resolve(project, repo_root=root)
    traversal = (manuscript_source.traversal(source.get("root"), repo_root=root)
                 if source.get("root") else {"sources": []})
    snapshot = [{"file": row.get("file"), "sha256": row.get("sha256")}
                for row in traversal.get("sources") or []]
    revision = "sha256:" + _digest_bytes(json.dumps(
        snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return {"schema_version": "laplace.project-structure/1", "project": project,
            "status": "SOURCE_ONLY", "revision": revision,
            "authority": {"plan_path": None, "plan_revision": None,
                          "source_revision": source.get("revision")},
            "selected_source": source, "source_outline": [], "sections": [],
            "gaps": [{"kind": "plan", "id": "projection_plan",
                      "reason": "project has no canonical projection plan"}]}


def _check_plan_guard(state: dict, payload: Mapping[str, object], project: str = "") -> None:
    """One name, TWO legal homes, one gate.

    `expected_plan_revision` passes on either the `plan` home (`state["revision"]`) or the
    `plan-file` home (`authority.plan_revision`): this door built an `accepted` set of both
    and compared by set membership, so the audit's census could not tell which home it wanted
    and a correct caller using either looked wrong in the other's terms.  The gate accepts
    either and the refusal now serves BOTH current tokens, so the caller is never left
    guessing which of the two the door meant.
    """
    supplied = str(payload.get("expected_plan_revision") or "")
    if (not supplied and not payload.get("expected")
            and (state.get("authority") or {}).get("plan_path") is None):
        return
    # The caller's own payload, with the old name's value coerced exactly as this door
    # coerced it, so `expected` reaches `gate` and nothing else changes.  Handing the gate
    # `{"expected_plan_revision": supplied}` made the token field unreachable at this site.
    identity_doors.gate(
        "section_change plan", supplied={**payload, "expected_plan_revision": supplied},
        homes=[("plan", project, state.get("revision")),
               ("plan-file", project, (state.get("authority") or {}).get("plan_revision"))],
        required=["expected_plan_revision"],
        said="projection plan changed; refresh before changing the section")


def _write_source(path: Path, text: str, expected_digest: str | None = None) -> None:
    if expected_digest and (not path.is_file() or _digest(path) != _guard(expected_digest)):
        raise ValueError("section source changed during the guarded structure write")
    before = path.read_bytes() if path.is_file() else None
    staged = _stage_main(path, text)
    if expected_digest and (not path.is_file() or _digest(path) != _guard(expected_digest)):
        staged.unlink(missing_ok=True)
        raise ValueError("section source changed during the guarded structure write")
    from laplace.manuscript.source_effects import publish
    publish(staged, path)
    context = _MUTATION.get()
    if context is not None: context["files"].append((path, before, text.encode("utf-8")))


def _gap_anchors(before: str, start: int, end: int, width: int = 256) -> dict:
    left_lines = before[:start].splitlines(keepends=True)
    meaningful = next((index for index in range(len(left_lines) - 1, -1, -1)
                       if left_lines[index].strip()), None)
    left_boundary = "" if meaningful is None else "".join(left_lines[meaningful:])
    right_tail = before[end:]
    right_boundary = (right_tail.splitlines(keepends=True) or [""])[0]
    return {"deleted": before[start:end],
            "left": before[max(0, start - width):start],
            "right": before[end:min(len(before), end + width)],
            "left_boundary": left_boundary, "right_boundary": right_boundary}


def _restore_gap(current: str, source_record: Mapping[str, object], *, with_offset=False):
    anchors = source_record.get("anchors")
    if not isinstance(anchors, Mapping):
        before = str(source_record.get("before") or "")
        after = str(source_record.get("after") or "")
        start = int(source_record.get("start") or 0)
        removed_length = len(before) - len(after)
        anchors = _gap_anchors(before, start, start + removed_length)
    deleted = str(anchors.get("deleted") or "")
    left, right = str(anchors.get("left") or ""), str(anchors.get("right") or "")
    if not deleted:
        raise ValueError("deletion receipt carries no restorable source span")
    if "left_boundary" in anchors or "right_boundary" in anchors:
        left_boundary = str(anchors.get("left_boundary") or "")
        right_boundary = str(anchors.get("right_boundary") or "")
        if right_boundary:
            candidates = []
            for match in re.finditer(re.escape(right_boundary), current):
                prefix = current[:match.start()]
                if ((left_boundary and prefix.endswith(left_boundary))
                        or (not left_boundary and match.start() == 0)):
                    candidates.append(match.start())
            if len(candidates) != 1:
                raise ValueError("deleted source gap is modified or ambiguous; restore refused")
            insertion = candidates[0]
        else:
            if ((left_boundary and not current.endswith(left_boundary))
                    or (not left_boundary and current)):
                raise ValueError("deleted source gap is modified or ambiguous; restore refused")
            insertion = len(current)
        return (current[:insertion] + deleted + current[insertion:], insertion) if with_offset else current[:insertion] + deleted + current[insertion:]
    if left and right:
        seam = left + right
        positions = [match.start() for match in re.finditer(re.escape(seam), current)]
        if len(positions) != 1:
            raise ValueError("deleted source gap is modified or ambiguous; restore refused")
        insertion = positions[0] + len(left)
    elif right:
        if not current.startswith(right):
            raise ValueError("deleted source gap is modified or ambiguous; restore refused")
        insertion = 0
    elif left:
        if not current.endswith(left):
            raise ValueError("deleted source gap is modified or ambiguous; restore refused")
        insertion = len(current)
    else:
        if current:
            raise ValueError("deleted source gap is modified or ambiguous; restore refused")
        insertion = 0
    return (current[:insertion] + deleted + current[insertion:], insertion) if with_offset else current[:insertion] + deleted + current[insertion:]


def _restore_plan_entries(plan_record: Mapping[str, object], current: dict) -> list[dict]:
    entries = plan_record.get("entries")
    if not isinstance(entries, list) or not entries:
        return []
    restored = [entry for entry in entries if isinstance(entry, dict)
                and isinstance(entry.get("section"), dict)]
    restored_ids = [str(entry["section"].get("id") or "") for entry in restored]
    if not all(restored_ids) or len(restored_ids) != len(set(restored_ids)):
        raise ValueError("deletion receipt has invalid plan identities")
    current_ids = {str(row.get("id") or "")
                   for key in ("sections", "appendices") for row in current.get(key) or []}
    reused = sorted(set(restored_ids) & current_ids)
    if reused:
        raise ValueError("deleted plan identity was reused after deletion: " + ", ".join(reused))
    for entry in restored:
        parent = entry["section"].get("parent_id")
        if parent and parent not in restored_ids and str(parent) not in current_ids:
            raise ValueError("deleted section parent changed or disappeared; restore refused")

    orders = plan_record.get("orders_before")
    if not isinstance(orders, Mapping):
        return restored
    positioned: list[dict] = []
    by_id = {str(entry["section"]["id"]): entry for entry in restored}
    for collection in ("sections", "appendices"):
        original = [str(value) for value in orders.get(collection) or []]
        wanted = {ident for ident in restored_ids
                  if by_id[ident].get("collection") == collection}
        if not wanted:
            continue
        rows = list(current.get(collection) or [])
        row_ids = [str(row.get("id") or "") for row in rows]
        survivors = [ident for ident in original if ident not in wanted]
        observed = [ident for ident in row_ids if ident in set(survivors)]
        if observed != survivors:
            raise ValueError("surviving plan section order changed after deletion; restore refused")
        index = 0
        while index < len(original):
            if original[index] not in wanted:
                index += 1
                continue
            group = []
            while index < len(original) and original[index] in wanted:
                group.append(original[index]); index += 1
            next_id = next((ident for ident in original[index:] if ident not in wanted), None)
            previous_id = next((ident for ident in reversed(original[:index - len(group)])
                                if ident not in wanted), None)
            if next_id is not None:
                insertion = row_ids.index(next_id)
            elif previous_id is not None:
                insertion = row_ids.index(previous_id) + 1
            else:
                insertion = 0
            for offset, ident in enumerate(group):
                entry = {**by_id[ident], "index": insertion + offset}
                positioned.append(entry)
                rows.insert(insertion + offset, entry["section"])
                row_ids.insert(insertion + offset, ident)
    if {str(item["section"]["id"]) for item in positioned} != set(restored_ids):
        raise ValueError("deletion receipt plan order is incomplete")
    return positioned


def _delete_section(project: str, payload: Mapping[str, object], root: Path,
                    manuscript: Path) -> dict:
    from laplace.manuscript import storyboard, projection_viewer
    state = _structure_state(project, root)
    _check_plan_guard(state, payload, project)
    section_id = str(payload.get("section_id") or "").strip()
    if not section_id:
        raise ValueError("section_id is required")
    section_state = next((item for item in state.get("sections") or []
                          if item.get("id") == section_id), None)
    files = list(dict.fromkeys((section_state.get("source") or {}).get("source_files") or [])) \
        if section_state else []
    supplied_file = payload.get("source_file") or payload.get("file")
    if supplied_file:
        source_file = _source_path(root, manuscript, supplied_file)
    elif len(files) == 1:
        source_file = _source_path(root, manuscript, files[0])
    else:
        raise ValueError("source_file is required when the section has no unique plan correspondence")
    if not source_file.is_file() or source_file.suffix.lower() != ".tex":
        raise ValueError("section source is not an available TeX file")
    source_rel = source_file.relative_to(root).as_posix()
    plan_corresponds = bool(section_state and source_rel in files)
    before_bytes = source_file.read_bytes()
    if len(before_bytes) > 2_000_000:
        raise ValueError("section source is too large for an atomic structure edit")
    before_digest = _digest_bytes(before_bytes)
    # The same home, the same gate, the owner's own digest from the line above.
    identity_doors.gate(
        "section_change source", supplied=payload,
        homes=[("source-file", "%s::%s" % (project, source_rel), before_digest)],
        required=["expected_source_digest"],
        said="section source changed; refresh before deleting it")
    try:
        before_text = before_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("section source is not UTF-8") from exc

    from laplace.pipeline import registry
    record = registry.resolve(project, repo_root=root)
    plan_path = record.plan(root) if record is not None else None
    plan_entries: list[dict] = []
    raw_section: dict = {}
    if plan_path is not None and plan_path.is_file() and plan_corresponds:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        try:
            plan_entries = _plan_sections(plan, section_id)
            raw_section = next(entry["section"] for entry in plan_entries
                               if entry["section"].get("id") == section_id)
        except ValueError:
            plan_entries = []
    heading_title = str(payload.get("title") or raw_section.get("title")
                        or (section_state or {}).get("title") or "")
    heading_kind = str(payload.get("kind") or "") or None
    line_value = payload.get("line_start") or payload.get("line")
    try:
        heading_line = int(line_value) if line_value not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise ValueError("line_start must be a source line number") from exc
    if heading_line is None and not heading_title:
        raise ValueError("line_start or title is required to locate the source heading")
    start, end = _source_span(
        before_text, heading_title, heading_kind, heading_line)
    after_text = before_text[:start] + before_text[end:]
    after_bytes = after_text.encode("utf-8")
    operation_id = "MSX-" + uuid.uuid4().hex
    intent = {
        "record": "manuscript-section-change", "id": operation_id, "project": project,
        "operation": "delete", "section_id": section_id,
        "source": {"file": source_rel, "start": start,
                   "before": before_text, "after": after_text,
                   "anchors": _gap_anchors(before_text, start, end),
                   "before_digest": before_digest, "after_digest": _digest_bytes(after_bytes)},
        "plan": {"path": plan_path.relative_to(root).as_posix() if plan_path else None,
                 "entries": plan_entries,
                 "orders_before": ({key: [str(row.get("id") or "") for row in plan.get(key) or []]
                                    for key in ("sections", "appendices")}
                                   if plan_entries else {}),
                 "before_revision": state.get("revision")},
    }
    (root / "contract").mkdir(parents=True, exist_ok=True)
    journal.bank_row("contract/talk.jsonl", intent, root=root)
    before_version = projection_viewer.bank_editor_save(
        manuscript, source_file, before_bytes, author="author", surface="writing-structure",
        source="section-delete-recovery")
    _write_source(source_file, after_text, before_digest)
    if plan_entries:
        plan_result = _plan_write(
            project, {"kind": "remove-section", "section": section_id, "by": "author"}, root)
        if not plan_result.get("applied"):
            _write_source(source_file, before_text, _digest_bytes(after_bytes))
            raise ValueError("section plan change refused: " + str(plan_result.get("error") or "unknown error"))
    after_version = projection_viewer.bank_editor_save(
        manuscript, source_file, after_bytes, author="author", surface="writing-structure",
        source=f"section-delete:{operation_id}")
    current = _structure_state(project, root)
    intent["plan"]["after_revision"] = current.get("revision")
    completion = {
        "record": "manuscript-section-change-complete", "id": "MSXD-" + uuid.uuid4().hex,
        "supersedes": operation_id, "project": project, "operation": "delete",
        "source_digest": _digest(source_file), "plan_revision": current.get("revision"),
        "versions": [before_version.get("version_id"), after_version.get("version_id")],
    }
    # The delete row is immutable, so the post-plan guard needed by a later
    # process is carried by the completion row and joined during restore.
    journal.bank_row("contract/talk.jsonl", completion, root=root)
    undo = {"operation": "restore", "section_id": section_id, "receipt_id": operation_id,
            "expected_source_digest": completion["source_digest"],
            "expected_plan_revision": completion["plan_revision"]}
    return {"ok": True, "operation": "delete", "receipt": {
                "id": operation_id, "section_id": section_id, "file": source_rel,
                "versions": completion["versions"]},
            "source_digest": completion["source_digest"],
            "plan_revision": completion["plan_revision"], "state": current, "undo": undo}


def _restore_section(project: str, payload: Mapping[str, object], root: Path,
                     manuscript: Path) -> dict:
    from laplace.manuscript import storyboard, projection_viewer
    receipt_id = str(payload.get("receipt_id") or "").strip()
    if not receipt_id:
        raise ValueError("receipt_id is required to restore a deleted section")
    deleted = _receipt(root, receipt_id, project)
    section_id = str(payload.get("section_id") or "").strip()
    if section_id != deleted.get("section_id"):
        raise ValueError("restore section_id does not match its deletion receipt")
    state = _structure_state(project, root)
    completions = []
    path = root / "contract" / "talk.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (row.get("record") == "manuscript-section-change-complete"
                and row.get("supersedes") == receipt_id and row.get("operation") == "delete"):
            completions.append(row)
    if not completions:
        raise ValueError("section deletion did not complete and cannot be restored")
    deleted_complete = completions[-1]
    supplied_plan_guard = str(payload.get("expected_plan_revision") or "")
    current_plan_guards = {str(state.get("revision") or ""),
                           str((state.get("authority") or {}).get("plan_revision") or "")}
    if (supplied_plan_guard != str(deleted_complete.get("plan_revision") or "")
            and supplied_plan_guard not in current_plan_guards):
        raise ValueError("projection plan changed; refresh before restoring")
    source_record = deleted.get("source") or {}
    source_file = (root / str(source_record.get("file") or "")).resolve()
    try:
        source_file.relative_to(manuscript)
    except ValueError as exc:
        raise ValueError("receipt source escapes the selected manuscript") from exc
    if not source_file.is_file():
        raise ValueError("deleted section source file is unavailable")
    current_digest = _digest(source_file)
    required_digest = str(deleted_complete.get("source_digest") or "")
    supplied_source_guard = _guard(payload.get("expected_source_digest"))
    if supplied_source_guard not in {current_digest, required_digest}:
        raise ValueError("section source changed; refresh before restoring")
    current_text = source_file.read_text(encoding="utf-8")
    restored_text, restored_offset = _restore_gap(current_text, source_record, with_offset=True)
    restored_bytes = restored_text.encode("utf-8")
    _write_source(source_file, restored_text, current_digest)
    plan_record = deleted.get("plan") or {}
    if plan_record.get("entries"):
        from laplace.pipeline import registry
        record = registry.resolve(project, repo_root=root)
        plan_path = record.plan(root) if record is not None else None
        if plan_path is None or not plan_path.is_file():
            _write_source(source_file, current_text, _digest_bytes(restored_bytes))
            raise ValueError("canonical projection plan disappeared after deletion")
        current_plan_bytes = plan_path.read_bytes()
        current_plan = json.loads(current_plan_bytes)
        try:
            entries = _restore_plan_entries(plan_record, current_plan)
        except ValueError:
            _write_source(source_file, current_text, _digest_bytes(restored_bytes))
            raise
        result = _plan_write(project, {
            "kind": "restore-section", "entries": entries,
            "expected_plan_digest": _digest_bytes(current_plan_bytes),
            "by": "author"}, root)
        if not result.get("applied"):
            _write_source(source_file, current_text, _digest_bytes(restored_bytes))
            raise ValueError("section plan restore refused: " + str(result.get("error") or "unknown error"))
    version = projection_viewer.bank_editor_save(
        manuscript, source_file, restored_bytes, author="author", surface="writing-structure",
        source=f"section-restore:{receipt_id}")
    current = _structure_state(project, root)
    operation_id = "MSR-" + uuid.uuid4().hex
    journal.bank_row("contract/talk.jsonl", {
        "record": "manuscript-section-change-complete", "id": operation_id,
        "supersedes": receipt_id, "project": project, "operation": "restore",
        "section_id": section_id, "source_digest": _digest(source_file),
        "plan_revision": current.get("revision"), "versions": [version.get("version_id")],
    }, root=root)
    return {"ok": True, "operation": "restore",
            "receipt": {"id": operation_id, "restored_from": receipt_id,
                        "section_id": section_id, "file": source_record.get("file"),
                        "versions": [version.get("version_id")]},
            "source_digest": _digest(source_file), "plan_revision": current.get("revision"),
            "state": current,
            "undo": {"operation":"delete", "section_id":section_id,
                     "source_file":source_record.get("file"),
                     "line_start":restored_text[:restored_offset].count("\n")+1,
                     "expected_source_digest":_digest(source_file),
                     "expected_plan_revision":current.get("revision")}}


_HEADING_LABEL = re.compile(r"\\label\s*\{([^{}]+)\}")
_ADJACENT_LABEL = re.compile(r"(?:\s|%[^\n]*(?:\n|$))*\\label\s*\{([^{}]+)\}")


def _heading_rows(text: str) -> list[dict]:
    """Headings with their labels, without stealing labels from body text.

    ``labels`` lists every label written inside the title braces (``\\section{Title\\label{a}}``) and every
    consecutive label directly after the heading, in source order. ``label`` stays the first ADJACENT label when
    there is one (the established identity), else the first inline one. ``title`` remains the exact source text
    between the braces (plan matching uses it); readers display ``bindings.headings``' ``display_title``."""
    rows = _heading_matches(text)
    for row in rows:
        inline = [match.group(1).strip() for match in _HEADING_LABEL.finditer(row["title"])]
        adjacent, cursor = [], row["end"]
        while (match := _ADJACENT_LABEL.match(text, cursor)):
            adjacent.append(match.group(1).strip()); cursor = match.end()
        row["labels"] = inline + adjacent
        row["label"] = adjacent[0] if adjacent else inline[0] if inline else None
    return rows


def _same_source(file: str, declared: str) -> bool:
    return bool(declared and (file == declared or file.endswith("/" + declared)))


def _section_location(section: dict, traversal: dict) -> tuple[int, int, int] | None:
    matches = []
    for index, item in enumerate(traversal.get("sources") or []):
        file = str(item.get("file") or "")
        if section.get("source_file") and not _same_source(file, section["source_file"]):
            continue
        for heading in _heading_rows(str(item.get("text") or "")):
            matched = (heading["label"] == section["source_label"] if section.get("source_label")
                       else heading["title"] == section.get("source_title", section.get("title")))
            if matched:
                matches.append((index, heading["line"], heading["start"]))
    return matches[0] if len(matches) == 1 else None


def _execution_prefixes(traversal: dict) -> list[tuple]:
    """Order headings around nested includes, including headings in the root file."""
    sources = traversal.get("sources") or []; prefixes = []; used = {}
    for index, item in enumerate(sources):
        if not item.get("parent"):
            prefixes.append(()); continue
        parent_index = next((i for i in range(index-1, -1, -1) if sources[i]["file"] == item["parent"]), None)
        if parent_index is None:
            raise ValueError("source include has no resolved parent occurrence")
        parent = sources[parent_index]; lines = str(parent.get("text") or "").splitlines(keepends=True)
        line = int(item["include_line"]); text = manuscript_source._uncomment(lines[line-1])
        arguments = {row["argument"] for row in traversal.get("includes") or []
                     if row.get("parent") == item["parent"] and row.get("line_start") == line and row.get("target") == item["file"]}
        calls = [match for match in manuscript_source._INPUT_RE.finditer(text) if match.group(1).strip() in arguments]
        key = (parent_index, line, item["file"]); occurrence = used.get(key, 0); used[key] = occurrence + 1
        if occurrence >= len(calls):
            raise ValueError("source include order is ambiguous")
        offset = sum(len(value) for value in lines[:line-1]) + calls[occurrence].start()
        prefixes.append(prefixes[parent_index] + (offset, 1))
    return prefixes


def _insertion_plan(plan: dict, traversal: dict, file: str, line: int, parent: str | None) -> dict:
    """Place a new source heading between the same existing reader-plan entries."""
    source_index = next((i for i, item in enumerate(traversal.get("sources") or [])
                         if item.get("file") == file), None)
    if source_index is None:
        raise ValueError("heading source is not in the selected manuscript traversal")
    entries = [(collection, row) for collection in ("sections", "appendices")
               for row in plan.get(collection, [])]
    prefixes = _execution_prefixes(traversal)
    located = [(prefixes[position[0]] + (position[2], 0), collection, row) for collection, row in entries
               if (position := _section_location(row, traversal)) is not None]
    source_lines = str(traversal["sources"][source_index].get("text") or "").splitlines(keepends=True)
    boundary = prefixes[source_index] + (sum(len(value) for value in source_lines[:line]), -1)
    following = sorted((value for value in located if value[0] > boundary), key=lambda value: value[0])
    previous = sorted((value for value in located if value[0] <= boundary), key=lambda value: value[0])
    parent_entry = next(((collection, row) for collection, row in entries if row.get("id") == parent), None)
    collection = parent_entry[0] if parent_entry else (following[0][1] if following else previous[-1][1] if previous else "sections")
    following = [value for value in following if value[1] == collection]
    previous = [value for value in previous if value[1] == collection]
    return {"collection": collection, **({"before_section": following[0][2]["id"]} if following else
            {"after_section": previous[-1][2]["id"]} if previous else {})}


def _conversion(project: str, payload: Mapping, root: Path, manuscript: Path,
                source: dict, path: Path, raw: str) -> tuple[int, int, str] | None:
    replacement = payload.get("replacement")
    if replacement is None:
        return None
    if not isinstance(replacement, Mapping):
        raise ValueError("replacement must identify one exact current paragraph")
    try:
        lo, hi = int(replacement["line_start"]), int(replacement["line_end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("replacement requires paragraph line_start and line_end") from exc
    lines = raw.split("\n")
    before = replacement.get("before")
    if not 1 <= lo <= hi <= len(lines) or not isinstance(before, str) or "\n".join(lines[lo-1:hi]) != before:
        raise ValueError("the paragraph changed before conversion")
    from laplace.manuscript import walk, manuscript_figure_preview
    main = (root / source["root"]).resolve()
    rendered_source = walk.root_content(raw)[0] if path == main else raw
    blocks = walk.blocks_for(rendered_source, file_rel=path.relative_to(manuscript).as_posix(),
        repo_file=path.relative_to(root).as_posix(), md=manuscript, corpus=project,
        dir_param="", para_spans=[], known_macros=walk.preamble_macros(main),
        declared_envs=manuscript_figure_preview.declared_environments(main, root))
    if not any(block.get("kind") == "para" and block.get("tex") == before
               and block.get("src", {}).get("line_start") == lo
               and block.get("src", {}).get("line_end") == hi for block in blocks):
        raise ValueError("conversion requires one whole prose paragraph")
    if before.strip() == r"\par":
        raise ValueError("write a heading title before converting an empty paragraph")
    return lo, hi, before


def _record_heading_change(root: Path, manuscript: Path, project: str, path: Path,
                           before: str, after: str, passage_before: str, passage_after: str,
                           operation: str, section: str, operation_id: str) -> str | None:
    anchor = {"file": path.relative_to(manuscript).as_posix(), "section": section,
              "before": before, "after": after, "operation_id": operation_id}
    if passage_after:
        anchor.update(passage_before=passage_before, passage_after=passage_after)
    result = manuscript_bridge.feedback_add(root, project, {"kind": "author-structure",
        "node_id": section, "by": "author", "comment": operation,
        "anchor": anchor}, ledger=manuscript / "feedback" / "feedback.jsonl")
    return (result.get("record") or {}).get("id")


def mirror_heading_titles(project: str, path: Path, before: str, after: str,
                          root: Path | None = None, *, history_cache=None) -> list[str]:
    """Mirror a source rename only while its plan title still follows that source.

    Stable labels identify headings. Legacy unlabelled headings require unchanged
    heading order and an exact old title. Independent editorial plan titles stay.
    """
    from laplace.manuscript import storyboard
    from laplace.pipeline import registry
    root = Path(root).resolve() if root else source_tree()
    plan_path = registry.plan_path_for(project, root)
    if plan_path is None or not plan_path.is_file():
        return []
    source = manuscript_source.resolve(project, repo_root=root)
    manuscript = (root / source.get("manuscript_dir", "")).resolve()
    if not path.resolve().is_relative_to(manuscript):
        return []
    file = path.relative_to(root).as_posix()
    from laplace.manuscript import bindings
    original, current = bindings.headings(before), bindings.headings(after)
    if not original or not current:
        return []
    updates = []
    for index, old in enumerate(original):
        if old.get("label"):
            candidates = current.by_label.get(old["label"], [])
        else:
            candidates = ([current[index]] if len(current) == len(original)
                          and current[index]["kind"] == old["kind"] else [])
        if len(candidates) == 1 and candidates[0]["title"] != old["title"]:
            updates.append((old, candidates[0]))
    changed = []
    if not updates:
        return changed
    from laplace.manuscript import bindings
    from laplace.manuscript import proposal_preflight
    source, observed = bindings.selected_tree(project, root, source=source)
    traversal = {**observed, "sources": [{**item, "text": before,
        "raw_file_sha256": bindings.digest(before)} if item.get("file") == file else item
        for item in observed.get("sources", [])]}
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    history_cache = history_cache if history_cache is not None else {}
    if 'titles' not in history_cache:
        history_cache['titles'] = storyboard.prior_source_titles(project, root)
    parsed, operations = {file: original}, []
    sections = list(plan.get('sections', [])) + list(plan.get('appendices', []))
    witnesses = [(section, bindings.correspondence(source, traversal, section,
                  heading_rows_by_file=parsed)) for section in sections]
    by_occurrence = {}
    for section, witness in witnesses:
        heading = witness.get('heading') or {}
        if witness.get('precision') not in {'AMBIGUOUS', 'UNRESOLVED'}:
            by_occurrence.setdefault((heading.get('file'), heading.get('line')), []).append((section, witness))
    for old, new in updates:
        candidates = by_occurrence.get((file, old['line']), [])
        if len(candidates) != 1:
            continue
        section, witness = candidates[0]
        follows = section.get('title') == section.get('source_plan_title', old['title'])
        display_title = (history_cache['titles'].get((section['id'], new['title']), new['title'])
                         if follows else section.get('title'))
        operation = {'kind': 'retitle', 'section': section['id'], 'title': display_title,
            'source_title': new['title'],
            'source_plan_title': display_title if follows else section.get('source_plan_title', old['title']),
            'expected_plan_digest': _digest_bytes(plan_bytes), 'by': 'author:source-heading'}
        if section.get('source_anchor'):
            lo, hi = new['line'], new['heading_line_end']
            operation.update(source_heading='\n'.join(after.split('\n')[lo - 1:hi]),
                             source_anchor=proposal_preflight.source_anchor(after, lo, hi))
        operations.append(operation)
        changed.append(section['id'])
    if operations:
        result = storyboard.plan_write_batch(project, operations, root)
        context = _MUTATION.get()
        if context is not None:
            context['owned'].extend((result.get('owned_changes') or {}).get('files') or [])
        if not result.get('applied'):
            raise ValueError('heading was saved but its reader-plan title could not update: ' + str(result.get('error')))

    return changed


def _create_section(project: str, payload: Mapping[str, object], root: Path, manuscript: Path) -> dict:
    """Insert one empty source heading and coemit its reader-plan identity."""
    from laplace.manuscript import storyboard, projection_viewer, manuscript_source
    from laplace.core.records import journal
    (root/'contract').mkdir(parents=True,exist_ok=True)
    kind = str(payload.get("kind") or "")
    if kind not in {"chapter", "section", "subsection", "subsubsection"}:
        raise ValueError("kind must be chapter, section, subsection, or subsubsection")
    title = _normal_title(payload.get("title"))
    state = _structure_state(project, root)
    source_only = not (state.get("authority") or {}).get("plan_path") or (state.get("status") == "MISSING" and not (state.get("authority") or {}).get("plan_revision"))
    if not source_only:
        _check_plan_guard(state, payload, project)
    source_file = _source_path(root, manuscript, payload.get("source_file") or payload.get("file"))
    before = source_file.read_bytes().decode("utf-8"); digest = _digest_bytes(before.encode())
    # `expected_source_digest` names the `source-file` home: the exact bytes of one .tex file,
    # digested by this owner at :46-51.  The gate is handed the digest the owner JUST
    # COMPUTED on the line above -- nothing is recomputed here, because a second digest that
    # differed would pass the suite and fail differential replay.
    identity_doors.gate(
        "section_change source", supplied=payload,
        homes=[("source-file", "%s::%s" % (project, source_file.relative_to(root).as_posix()),
                digest)],
        required=["expected_source_digest"],
        said="section source changed; refresh before inserting")
    source_state = manuscript_source.resolve(project, repo_root=root)
    conversion = _conversion(project, payload, root, manuscript, source_state, source_file, before)
    lines = before.split("\n")
    if conversion:
        line, end, replaced = conversion[0]-1, conversion[1], conversion[2]
    else:
        try: line = int(payload.get("after_line"))
        except (TypeError, ValueError) as exc: raise ValueError("after_line must be a source line number") from exc
        if not 0 <= line <= len(lines): raise ValueError("after_line is outside the selected source")
        if line and payload.get("after_before") != lines[line - 1]:
            raise ValueError("after_before does not match the insertion boundary")
        end, replaced = line, ""
    ident = str(payload.get("section_id") or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or kind)
    used={str(section.get('id')) for section in state.get('sections',[])}
    source_state=manuscript_source.resolve(project,repo_root=root)
    traversal=manuscript_source.traversal(source_state['root'],repo_root=root)
    all_text='\n'.join(str(item.get('text') or '') for item in traversal.get('sources',[]))
    if source_file.relative_to(root).as_posix() not in traversal.get('files',[]):
        raise ValueError('heading source is not included by the selected manuscript root')
    seed=ident;counter=2
    while ident in used or f'\\label{{{kind}:{ident}}}' in all_text:
        if payload.get('section_id'):raise ValueError('section identity already exists')
        ident=f'{seed}-{counter}';counter+=1
    title_tex = str(payload.get("title_tex") if payload.get("title_tex") is not None else replaced if conversion else _escape(title))
    # The exact paragraph TeX is the default title when converting. Its macros,
    # emphasis and mathematics are never reconstructed from rendered text.
    probe = _heading_matches("\\" + kind + "{" + title_tex + "}")
    if len(probe) != 1 or probe[0]["end"] != len("\\" + kind + "{" + title_tex + "}"):
        raise ValueError("title_tex must be a balanced TeX heading title")
    label = f"{kind}:{ident}"; block = f"\\{kind}{{{title_tex}}}\n\\label{{{label}}}"
    after = "\n".join(lines[:line] + block.split("\n") + lines[end:])
    source_rel = source_file.relative_to(root).as_posix(); op = "MSC-" + uuid.uuid4().hex
    plan_path = None if source_only else (state.get("authority") or {}).get("plan_path")
    original_plan = json.loads((root/plan_path).read_text()) if plan_path else None
    placement = _insertion_plan(original_plan, traversal, source_rel, line, payload.get("parent_id")) if original_plan else {}
    plan_digest = _digest(root/plan_path) if plan_path else None
    _write_source(source_file, after, digest)
    if not source_only:
        try:
            result = _plan_write(project, {"kind":"add-section", "section":ident, "title":title,
                "outline_kind":kind, "parent_id":payload.get("parent_id"),
                "source_file":source_file.relative_to(manuscript).as_posix(), "source_label":label,
                "source_title":title_tex, "source_plan_title":title, **placement,
                "expected_plan_digest":plan_digest,
                "by":"author"}, root)
            if not result.get("applied"): raise ValueError(str(result.get("error") or "plan insertion refused"))
        except Exception:
            _write_source(source_file, before, _digest_bytes(after.encode()))
            raise
    version = projection_viewer.bank_editor_save(manuscript, source_file, after.encode(), author="author", surface="writing-structure", source="section-create")
    current = _structure_state(project, root); after_digest = _digest_bytes(after.encode())
    plan_path=None if source_only else (current.get('authority') or {}).get('plan_path')
    plan_entry=None
    if plan_path:
        plan=json.loads((root/plan_path).read_text())
        plan_entry=next((item for collection in ('sections','appendices') for item in plan.get(collection,[]) if item.get('id')==ident),None)
    journal.bank_row('contract/talk.jsonl',{'record':'manuscript-section-change','id':op,
        'project':project,'operation':'create','section_id':ident,'title':title,'kind':kind,
        'source':{'file':source_rel,'inserted':block,'replaced':replaced,'title_tex':title_tex,'before':before,'after':after,
                  'before_digest':digest,'after_digest':after_digest},
        'plan':{'path':plan_path,'created_entry':plan_entry}},root=root)
    correction_id = _record_heading_change(root, manuscript, project, source_file, before, after,
        replaced, block, "Converted paragraph to heading" if conversion else "Inserted heading", ident, op)
    return {"ok":True,"operation":"convert" if conversion else "create","correction_id":correction_id,"receipt":{"id":op,"section_id":ident,"label":label,"versions":[version.get("version_id")]},
            "edits":[{"file":source_file.relative_to(manuscript).as_posix(),"line_start":1,"line_end":len(before.split("\n")),"before":before,"after":after}],
            "source_digest":after_digest,"plan_revision":current.get("revision"),"state":current,
            "undo":{"operation":"undo-create","section_id":ident,"receipt_id":op,"source_file":source_rel,
                    "expected_source_digest":after_digest,"expected_plan_revision":current.get("revision")}}


def _undo_create(project:str,payload:Mapping[str,object],root:Path,manuscript:Path)->dict:
    """Remove only the inserted heading, never the pre-existing following prose."""
    from laplace.manuscript import storyboard, projection_viewer, proposal_preflight
    from laplace.core.records import journal
    receipt=None
    for line in (root/'contract/talk.jsonl').read_text().splitlines():
        try:row=json.loads(line)
        except ValueError:continue
        if row.get('record')=='manuscript-section-change' and row.get('operation')=='create' and row.get('id')==payload.get('receipt_id') and row.get('project')==project:receipt=row
    if receipt is None:raise ValueError('Heading creation receipt is unavailable')
    source=receipt['source'];path=_source_path(root,manuscript,source['file'])
    selected=manuscript_source.resolve(project,repo_root=root)
    if path.relative_to(root).as_posix() not in manuscript_source.traversal(selected['root'],repo_root=root).get('files',[]):
        raise ValueError('the heading file is no longer in the selected manuscript root')
    before=path.read_text();matches=proposal_preflight._matches(before,source['inserted'])
    if len(matches)!=1:raise ValueError('The created heading changed or is ambiguous; review it before undoing')
    lo,hi=matches[0];lines=before.split('\n');replaced=source.get('replaced','');after='\n'.join(lines[:lo-1]+(replaced.split('\n') if replaced else [])+lines[hi:])
    plan_record=receipt.get('plan') or {};plan_path=plan_record.get('path')
    if plan_path:
        plan=json.loads((root/plan_path).read_text());entries=_plan_sections(plan,receipt['section_id'])
        if len(entries)!=1 or entries[0]['section']!=plan_record.get('created_entry'):
            raise ValueError('This new section has subsequent planning work; undo those changes before removing its heading')
    _write_source(path,after,_digest_bytes(before.encode()))
    if plan_path:
        try:
            result=_plan_write(project,{'kind':'remove-section','section':receipt['section_id'],'by':'author'},root)
            if not result.get('applied'):raise ValueError(result.get('error') or 'plan removal refused')
        except Exception:
            _write_source(path,before,_digest_bytes(after.encode()));raise
    projection_viewer.bank_editor_save(manuscript,path,after.encode(),author='author',surface='writing-structure',source='undo-heading-create')
    state=_structure_state(project,root)
    operation_id='MSCU-'+uuid.uuid4().hex
    journal.bank_row('contract/talk.jsonl',{'record':'manuscript-section-change-complete','id':operation_id,
        'project':project,'operation':'undo-create','supersedes':receipt['id'],
        'source_digest':_digest_bytes(after.encode()),'plan_revision':state.get('revision')},root=root)
    # Redo uses the exact original insertion boundary in the now-current source.
    previous=lines[lo-2] if lo>1 else ''
    heading=_heading_matches(source['inserted'])[0]
    undo={'operation':'convert' if replaced else 'create','source_file':source['file'],'after_line':lo-1,'after_before':previous,
          'expected_source_digest':_digest_bytes(after.encode()),'expected_plan_revision':state.get('revision'),
          'title':receipt.get('title',heading['title']),'kind':receipt.get('kind',heading['kind']),'section_id':receipt['section_id']}
    if source.get('title_tex') is not None:undo['title_tex']=source['title_tex']
    if replaced:undo['replacement']={'line_start':lo,'line_end':lo+len(replaced.split('\n'))-1,'before':replaced}
    if plan_record.get('created_entry',{}):undo['parent_id']=plan_record['created_entry'].get('parent_id')
    correction_id = _record_heading_change(root, manuscript, project, path, before, after, source['inserted'], replaced, 'Restored paragraph' if replaced else 'Removed newly inserted heading', receipt['section_id'], receipt['id'])
    return {'ok':True,'operation':'undo-create','receipt':{'id':operation_id,'section_id':receipt['section_id']},'correction_id':correction_id,'state':state,'source_digest':_digest_bytes(after.encode()),
            'plan_revision':state.get('revision'),'undo':undo,
            'edits':[{'file':path.relative_to(manuscript).as_posix(),'line_start':1,'line_end':len(lines),'before':before,'after':after}]}


def change(project: str, payload: Mapping[str, object], root=None) -> dict:
    """Create, delete, or restore one selected-source section under source and plan guards."""
    if not isinstance(payload, Mapping):
        raise ValueError("section-change payload must be an object")
    identity_doors.admit_expected(payload, "section_change")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    operation = str(payload.get("operation") or "").strip().lower()
    operation = {"delete-section": "delete", "restore-section": "restore"}.get(operation, operation)
    operation = {"create-section": "create", "insert-heading": "create"}.get(operation, operation)
    if operation not in {"create", "convert", "undo-create", "delete", "restore"}:
        raise ValueError("operation must be create, convert, undo-create, delete, or restore")
    if operation == "convert" and not isinstance(payload.get("replacement"), Mapping):
        raise ValueError("convert requires an exact replacement paragraph")
    if operation == "create" and payload.get("replacement") is not None:
        raise ValueError("use operation convert to replace a paragraph with a heading")
    root = Path(root).resolve() if root else source_tree()
    _source, main, manuscript = _selected(project, root, allow_empty=operation == "restore")
    lock = manuscript / ".structure.lock"
    with FileLock(str(lock), timeout=30):
        from laplace.core.receipts import file_receipt, bundle
        _source, main, manuscript = _selected(project, root, allow_empty=operation == "restore")
        extra = []
        declared = payload.get("source_file") or payload.get("file")
        if declared:
            extra.append(_source_path(root, manuscript, declared))
        if operation == "restore":
            receipt = _receipt(root, str(payload.get("receipt_id") or ""), project)
            extra.append(_source_path(root, manuscript, (receipt.get("source") or {}).get("file")))
        with _source_scope(project, root, _source, extra):
            context = {"files": [], "owned": []}
            token = _MUTATION.set(context)
            try:
                if operation in {"create", "convert"}:
                    result = _create_section(project, payload, root, manuscript)
                elif operation == "undo-create":
                    result = _undo_create(project,payload,root,manuscript)
                elif operation == "delete":
                    result = _delete_section(project, payload, root, manuscript)
                else:
                    result = _restore_section(project, payload, root, manuscript)
                files = [file_receipt(root, path, before, after) for path, before, after in context["files"]]
                result["owned_changes"] = bundle(files=files + context["owned"], views=["manuscript", "structure"])
                ident = result["receipt"]["id"]
                journal.bank_row("contract/talk.jsonl", {"record":"manuscript-section-inverse", "id":ident,
                    "project":project, "operation":operation, "undo":result["undo"]}, root=root)
                result["undo_ref"] = {"kind":"section", "id":ident, "project":project}
                if context["files"]:
                    changed_file = context["files"][0][0]
                    result["next_read"] = {"operation":"source", "payload":{"files":[changed_file.relative_to(manuscript).as_posix()]}}
                if context['files']:
                    from laplace.manuscript import source_effects
                    result['source_effect'] = source_effects.from_changes(root, project,
                        manuscript_source.selection_identity(_source, project), context['files'], owner='section-plan-operation')
            except Exception as exc:
                if context['files']:
                    from laplace.manuscript import source_effects
                    effect = source_effects.from_changes(root, project,
                        manuscript_source.selection_identity(_source, project), context['files'],
                        complete=False, owner='section-plan-operation')
                    _finish_structure_effect({'source_effect':effect}, project, root)
                    raise source_effects.SourceEffectFailure(exc, effect) from exc
                raise
            finally:
                _MUTATION.reset(token)
    return _finish_structure_effect(result, project, root)


def _finish_structure_effect(result, project, root):
    from laplace.manuscript import source_effects

    effect = result.get("source_effect")
    if isinstance(effect, dict):
        source_effects.finish(
            result,
            project,
            root,
            effect,
            heading_sync={
                "status": "NOT_NEEDED",
                "updated": [],
                "reason": "This structure owner performs its required plan operation inside the compensated source transaction.",
            },
        )
        if effect["impact"]["status"] != "NONE":
            effect["impact"]["reads"].append(
                {"operation": "structure", "payload": {"view": "summary"}}
            )
    return result


def create_chapter(
    project: str, title: str, root=None, expected_root_digest: str | None = None
) -> dict:
    base = Path(root).resolve() if root else source_tree()
    try:
        result = _create_chapter_owned(project, title, base, expected_root_digest)
    except Exception as exc:
        from laplace.manuscript.source_effects import error_details

        details = error_details(exc)
        if details:
            _finish_structure_effect(details, project, base)
        raise
    return _finish_structure_effect(result, project, base)




def undo_record(project: str, ident: str, root=None) -> dict:
    """Read the compact inverse banked alongside the completed section receipt."""
    root = Path(root).resolve() if root else source_tree()
    _selected(project, root, allow_empty=True)
    path = root / "contract/talk.jsonl"
    rows=[]
    for line in path.read_text().splitlines() if path.is_file() else []:
        try: rows.append(json.loads(line))
        except ValueError: continue
    row=next((row for row in reversed(rows) if row.get("record")=="manuscript-section-inverse"
              and row.get("id")==ident and row.get("project")==project), None)
    if row is None: raise ValueError("This project has no completed section change with that receipt")
    return {"kind":"section", "id":ident, "project":project, "undo":row["undo"]}
