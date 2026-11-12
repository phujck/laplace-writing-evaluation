"""Readable, source-addressed projections of existing manuscript change records."""
from __future__ import annotations

from pathlib import Path
from typing import Any

_HUNK_LIMIT = 60
_FRAGMENT_BYTE_LIMIT = 100_000


def _root(value=None) -> Path:
    if value is not None:
        return Path(value).resolve()
    from laplace.pipeline import registry
    return registry._repo_root().resolve()


def _source_file(root: Path, project: str, value: str) -> tuple[Path, Path, dict]:
    from laplace.manuscript import manuscript_source
    source = manuscript_source.resolve(project, repo_root=root)
    directory = source.get("manuscript_dir")
    if not isinstance(directory, str) or not directory:
        raise ValueError("selected manuscript source is unavailable")
    raw = Path(str(value or ""))
    if raw.is_absolute() or ".." in raw.parts:
        raise ValueError("change preview file must stay inside the selected manuscript")
    base_raw = Path(directory)
    manuscript = (base_raw if base_raw.is_absolute() else root / base_raw).resolve()
    candidates = ((root / raw).resolve(), (manuscript / raw).resolve())
    target = next((path for path in candidates
                   if path.is_file() and path.suffix == ".tex" and path.is_relative_to(manuscript)), None)
    if target is None:
        raise ValueError("change preview file is unavailable in the selected manuscript")
    return manuscript, target, source


def render_fragment(project: str, file: str, text: str,
                    root: Path | str | None = None) -> list[dict[str, Any]]:
    """Render source text through the same typed blocks as the manuscript reader."""
    if len(str(text).encode("utf-8")) > _FRAGMENT_BYTE_LIMIT:
        raise ValueError("change preview fragment is too large for inline rendering")
    root = _root(root)
    manuscript, target, source = _source_file(root, project, file)
    root_tex = (root / str(source.get("root") or "")).resolve()
    if not root_tex.is_file():
        raise ValueError("selected manuscript root is unavailable")
    from laplace.manuscript import manuscript_figure_preview, projection_viewer, walk
    blocks = walk.blocks_for(
        str(text), file_rel=target.relative_to(manuscript).as_posix(),
        repo_file=target.relative_to(root).as_posix(), md=manuscript, corpus=project,
        dir_param="", para_spans=projection_viewer.parse_paragraphs(str(text)),
        known_macros=walk.preamble_macros(root_tex),
        declared_envs=manuscript_figure_preview.declared_environments(root_tex, root),
        declared_presentation=manuscript_figure_preview.declared_environment_presentation(root_tex, root))
    for block in blocks:
        block["change_preview"] = True
    return blocks


def _hunk(project: str, file: str, row: dict, root: Path) -> dict:
    before = row.get("before")
    after = row.get("after")
    before_text = "\n".join(before) if isinstance(before, list) else str(before or "")
    after_text = "\n".join(after) if isinstance(after, list) else str(after or "")
    start, end = int(row.get("start") or 1), int(row.get("end") or row.get("start") or 1)
    omitted = [name for name, text in (("before", before_text), ("after", after_text))
               if len(text.encode("utf-8")) > _FRAGMENT_BYTE_LIMIT]
    return {"anchor": {"file": file, "line_start": start, "line_end": max(start, end)},
            "deleted": bool(row.get("deleted")),
            "before": "" if "before" in omitted else before_text,
            "after": "" if "after" in omitted else after_text,
            "before_blocks": (render_fragment(project, file, before_text, root)
                              if before_text and "before" not in omitted else []),
            "after_blocks": (render_fragment(project, file, after_text, root)
                             if after_text and "after" not in omitted else []),
            "preview_omitted": omitted,
            "source_bytes": {"before": len(before_text.encode("utf-8")),
                             "after": len(after_text.encode("utf-8"))}}


def recorded_source_hunks(item: dict) -> list[dict[str, Any]]:
    """Normalise only banked source deltas; never infer old bytes from live source."""
    anchor = item.get("anchor")
    file = (anchor.get("file") if isinstance(anchor, dict) else anchor) or item.get("file") or ""
    rows = item.get("hunks")
    if not isinstance(rows, list):
        return []

    def exact_text(value):
        if isinstance(value, str):
            return value
        if isinstance(value, list) and all(isinstance(line, str) for line in value):
            return "\n".join(value)
        return None

    result = []
    for row in rows[:_HUNK_LIMIT]:
        if not isinstance(row, dict):
            continue
        before, after = exact_text(row.get("before")), exact_text(row.get("after"))
        if before is None or after is None:
            continue
        start = row.get("start")
        end = row.get("end")
        result.append(
            {
                "file": str(file),
                "start": start if type(start) is int and start > 0 else 1,
                "end": end
                if type(end) is int and end > 0
                else start
                if type(start) is int and start > 0
                else 1,
                "before": before,
                "after": after,
                "deleted": bool(row.get("deleted")),
            }
        )
    return result


def recorded_source_comparisons(item: dict) -> list[dict[str, Any]]:
    """The same stored hunk view for activity detail and exact-record readers."""
    result = []
    for row in recorded_source_hunks(item):
        omitted = [
            key
            for key in ("before", "after")
            if len(row[key].encode("utf-8")) > _FRAGMENT_BYTE_LIMIT
        ]
        result.append(
            {
                "format": "tex",
                "title": f"{row['file']} · recorded lines {row['start']}–{row['end']}",
                "before": None if "before" in omitted else row["before"],
                "after": None if "after" in omitted else row["after"],
                "basis": "exact banked source-change hunk",
                **(
                    {
                        "note": "Recorded source side exceeds the inline comparison limit; exact record retains it.",
                        "omitted": omitted,
                    }
                    if omitted
                    else {}
                ),
            }
        )
    return result

def _correction_preview(root: Path, project: str, ident: str) -> dict:
    from laplace.pipeline import authoring
    history = authoring.history(project, {"id": ident}, repo_root=root)
    item = history["item"]
    anchor = item.get("anchor") if isinstance(item.get("anchor"), dict) else {}
    file = str(anchor.get("file") or "")
    has_passage = "passage_before" in anchor or "passage_after" in anchor
    before = anchor.get("passage_before") if has_passage else item.get("before", anchor.get("before"))
    after = anchor.get("passage_after") if has_passage else item.get("after", anchor.get("after"))
    if not isinstance(before, str):
        before = ""
    if not isinstance(after, str):
        after = ""
    if after == "(paragraph deleted)":
        after = ""
    hunks = []
    if isinstance(item.get("hunks"), list) and item["hunks"]:
        hunks = [_hunk(project, row["file"], row, root) for row in recorded_source_hunks(item)]
    elif file and (before or after):
        _manuscript, target, _source = _source_file(root, project, file)
        raw = target.read_text(encoding="utf-8")
        location = after if after and raw.count(after) == 1 else ""
        if not has_passage and after == raw and before:
            import difflib
            before_lines, after_lines = before.splitlines(), after.splitlines()
            rows = []
            for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
                    a=before_lines, b=after_lines, autojunk=False).get_opcodes():
                if tag == "equal":
                    continue
                deleted = tag == "delete"
                start = max(1, j1 + 1)
                rows.append({"start": start, "end": max(start, j2),
                             "before": before_lines[i1:i2], "after": after_lines[j1:j2],
                             "deleted": deleted})
            hunks = [_hunk(project, file, row, root) for row in rows[:_HUNK_LIMIT]]
        elif location:
            offset = raw.index(location)
            start = raw.count("\n", 0, offset) + 1
            end = start + max(0, location.count("\n"))
            hunks = [_hunk(project, file, {"start": start, "end": end,
                                           "before": before, "after": after}, root)]
    return {"schema_version": "laplace.author-change-preview/1", "mode": "correction",
            "project": project, "revision": history["revision"],
            "correction": {key: item.get(key) for key in
                           ("id", "kind", "scope", "text", "by", "created", "status",
                            "status_note", "applied", "anchor")},
            "hunks": hunks, "hunks_omitted": max(0, len(item.get("hunks") or [])-len(hunks)),
            "locatable": bool(hunks),
            "note": ("The applied passage is located in the current source."
                     if hunks else "This history item has no unique current source passage.")}


def change_preview(project: str, payload: dict | None = None,
                   root: Path | str | None = None) -> dict:
    """Project aggregate hand hunks or one correction as readable typed blocks."""
    root = _root(root)
    payload = payload or {}
    ident = str(payload.get("id") or "").strip()
    file = str(payload.get("file") or "").strip()
    if bool(ident) == bool(file):
        raise ValueError("author_changes requires exactly one of file or id")
    if ident:
        return _correction_preview(root, project, ident)
    _manuscript, target, _source = _source_file(root, project, file)
    repo_file = target.relative_to(root).as_posix()
    from laplace.manuscript import review_surface
    observed = review_surface.hand_hunks(project, repo_file, root)
    if not observed.get("ok"):
        raise ValueError(observed.get("reason") or "author change baseline is unavailable")
    relative = target.relative_to(_manuscript).as_posix()
    return {"schema_version": "laplace.author-change-preview/1", "mode": "baseline",
            "project": project, "file": relative, "repo_file": repo_file,
            "attributed": observed.get("attributed", False),
            "whole_file": observed.get("whole_file", False),
            "baseline": observed.get("baseline"), "counts": observed.get("counts") or {},
            "note": observed.get("note"),
            "hunks": [_hunk(project, relative, row, root)
                      for row in [item for item in observed.get("hunks") or []
                                  if isinstance(item, dict)][:_HUNK_LIMIT]],
            "hunks_omitted": max(0, len([item for item in observed.get("hunks") or []
                                          if isinstance(item, dict)])-_HUNK_LIMIT)}
