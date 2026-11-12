"""Versioned author voice, provenance-aware calibration and project guidance."""
from __future__ import annotations
from laplace.core.checkout import source_tree

import hashlib
import json
import re
from pathlib import Path
import uuid


DEFAULT_PROFILE = "profiles/voice/gerard-technical-v1.md"
MAX_PROFILE_BYTES = 64 * 1024
MAX_PROVENANCE_BYTES = 256 * 1024
MAX_CALIBRATION_BYTES = 16 * 1024
MAX_CALIBRATION_LINES = 80
_PROVENANCE_RE = re.compile(r"`(evidence/[^`]+\.json)`")
_JUDGEMENT_FIELDS = {"summary", "retained", "changed", "genre_boundary",
                     "authorship_boundary", "verification_limit", "author_instruction"}
_UNPINNED = object()


def _root(value=None):
    if value is not None:
        return Path(value).resolve()
    from laplace.pipeline import registry
    return registry._repo_root().resolve()


def _digest(value):
    return "sha256:" + hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _profile(root: Path, relative: str) -> tuple[Path, str]:
    raw = Path(relative)
    path = (root / raw).resolve()
    home = (root / "profiles" / "voice").resolve()
    if (raw.is_absolute() or '..' in raw.parts or not home.is_relative_to(root)
            or not path.is_relative_to(home) or path.suffix.lower() != ".md"
            or any((root / Path(*raw.parts[:index])).is_symlink() for index in range(1, len(raw.parts) + 1))):
        raise ValueError("voice profile must name an existing versioned profiles/voice Markdown file")
    origin = "project"
    if not path.is_file() and relative == DEFAULT_PROFILE:
        deployed_root = source_tree()
        path = (deployed_root / DEFAULT_PROFILE).resolve()
        origin = "deployed-house"
    if not path.is_file():
        raise ValueError("voice profile must name an existing versioned profiles/voice Markdown file")
    if path.stat().st_size > MAX_PROFILE_BYTES:
        raise ValueError("voice profile exceeds the bounded profile size")
    return path, origin


def _profile_section(content: str, heading: str) -> str:
    match = re.search(rf"^## {re.escape(heading)}\s*$", content, re.MULTILINE)
    if not match:
        return ""
    end = re.search(r"^## ", content[match.end():], re.MULTILINE)
    stop = match.end() + end.start() if end else len(content)
    return content[match.start():stop].strip()


def _runtime_content(content: str) -> str:
    sections = [_profile_section(content, "Current runtime prompt"),
                _profile_section(content, "Confirmed surface and terminology preferences")]
    compact = "\n\n".join(section for section in sections if section)
    # A legacy profile without structured headings remains usable as selected.
    return compact or content


def _profile_metadata(content: str) -> dict:
    title = re.search(r"^#\s+(.+?)\s*$", content, re.MULTILINE)
    version = re.search(r"^Version:\s*([^\s(]+)", content, re.MULTILINE)
    return {"title": title.group(1).strip() if title else "Untitled voice profile",
            "version": version.group(1).strip() if version else None}


def _provenance_reference(content: str) -> str | None:
    match = _PROVENANCE_RE.search(content)
    return match.group(1) if match else None


def _provenance_path(root: Path, profile_path: Path, content: str) -> tuple[Path | None, Path]:
    relative = _provenance_reference(content)
    base = root if profile_path.is_relative_to(root) else source_tree()
    if not relative:
        return None, base
    raw = Path(relative)
    path = (base / raw).resolve()
    evidence = (base / "evidence").resolve()
    if raw.is_absolute() or not path.is_relative_to(evidence):
        raise ValueError("voice-profile provenance must name a repository evidence JSON file")
    return path, base


def _load_provenance(root: Path, profile_path: Path, content: str) -> dict:
    path, source_root = _provenance_path(root, profile_path, content)
    if path is None:
        return {"status": "UNRECORDED_LEGACY", "path": None, "revision": None,
                "source_root": source_root, "data": None,
                "note": "This legacy profile has no recorded calibration ledger."}
    if not path.is_file():
        return {"status": "MISSING", "path": path, "revision": None,
                "source_root": source_root, "data": None,
                "note": "The profile's recorded calibration ledger is unavailable."}
    if path.stat().st_size > MAX_PROVENANCE_BYTES:
        return {"status": "REFUSED", "path": path, "revision": None,
                "source_root": source_root, "data": None,
                "note": "The profile's calibration ledger exceeds the bounded size."}
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_PROVENANCE_BYTES + 1)
        if len(raw) > MAX_PROVENANCE_BYTES:
            return {"status": "REFUSED", "path": path, "revision": None,
                "source_root": source_root, "data": None,
                "note": "The profile's calibration ledger exceeds the bounded size."}
        data = json.loads(raw.decode('utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {"status": "INVALID", "path": path, "revision": None,
                "source_root": source_root, "data": None,
                "note": "The profile's calibration ledger is not readable JSON."}
    rows = data.get("read") if isinstance(data, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return {"status": "INVALID", "path": path, "revision": 'sha256:' + hashlib.sha256(raw).hexdigest(),
                "source_root": source_root, "data": None,
                "note": "The calibration ledger has no structured read list."}
    return {"status": "RECORDED", "path": path, "revision": 'sha256:' + hashlib.sha256(raw).hexdigest(),
            "source_root": source_root, "data": data, "note": ""}


def _provenance_summary(value: dict, root: Path) -> dict:
    data = value.get("data") or {}
    rows = data.get("read") or []
    registers = sorted({str(row.get("register")) for row in rows if row.get("register")})
    path, base = value.get("path"), value.get("source_root") or root
    return {"status": value["status"],
            "path": path.relative_to(base).as_posix() if path and path.is_relative_to(base) else None,
            "revision": value.get("revision"), "sources": len(rows), "registers": registers,
            "reader": data.get("reader"), "purpose": data.get("purpose"),
            "verification_limit": data.get("verification_limit"), "note": value.get("note") or ""}


def effective_genre(project: str | None, repo_root=None, *, source=None, authored=None) -> dict:
    """Resolve authored genre or the selected source class for every consumer.

    Blank remains an authored inheritance choice. Source bytes are observations,
    not a reason to write that inferred value back into the manuscript contract.
    """
    root = _root(repo_root)
    if authored is None:
        from laplace.pipeline import projection_spec
        spec = (projection_spec.load_spec(project, root) or {}) if project is not None else {}
        authored = str((spec.get('manuscript') or {}).get('genre') or '').strip()
    if authored:
        return {'authored': authored, 'effective': authored, 'origin': 'manuscript-spec',
                'documentclass': None, 'source_revision': None}
    if project is None:
        return {'authored': '', 'effective': '', 'origin': 'unselected',
                'documentclass': None, 'source_revision': None}
    from laplace.manuscript import manuscript_source
    observed = source is not None
    source = source if observed else manuscript_source.resolve(project, repo_root=root, include_candidates=False)
    if observed and source.get('project') != project:
        raise ValueError('The observed source belongs to another project.')
    result = {'authored': '', 'effective': 'custom', 'origin': 'selected-source',
              'documentclass': None, 'source_revision': source.get('revision')}
    name = source.get('root')
    if source.get('status') not in {'resolved', 'empty'} or not isinstance(name, str) or not name:
        return result
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        return result
    try:
        text = manuscript_source._uncomment(path.read_text(encoding='utf-8', errors='replace'))
    except OSError:
        return result
    from laplace.manuscript.document import CLASS_RE
    match = CLASS_RE.search(text)
    documentclass = match.group(2).strip().split('/')[-1].casefold() if match else ''
    if documentclass in {'book', 'memoir', 'scrbook'}:
        genre = 'book'
    elif documentclass in {'report', 'scrreprt'}:
        genre = 'report'
    elif documentclass in {'article', 'amsart', 'revtex4', 'revtex4-1', 'revtex4-2',
                            'ieeetran', 'elsarticle', 'acmart', 'llncs', 'aastex', 'aastex6',
                            'aastex631', 'proc'} or any(token in documentclass for token in ('article', 'revtex', 'ieee')):
        genre = 'article'
    else:
        genre = 'custom'
    return {**result, 'effective': genre, 'documentclass': documentclass or None}


def _selection(root: Path, project: str | None, global_profile: str | None = None) -> dict:
    from laplace.pipeline import projection_spec, registry
    if project is not None and registry.resolve(project, repo_root=root) is None:
        raise ValueError("unknown project")
    spec = (projection_spec.load_spec(project, root) or {}) if project is not None else {}
    manuscript = spec.get("manuscript") or {}
    selected = str(global_profile or manuscript.get("voice_profile") or DEFAULT_PROFILE)
    path, origin = _profile(root, selected)
    with path.open('rb') as stream:
        raw = stream.read(MAX_PROFILE_BYTES + 1)
    if len(raw) > MAX_PROFILE_BYTES:
        raise ValueError('voice profile exceeds the bounded profile size')
    content = raw.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    guidance = str(manuscript.get("style_guidance") or "")
    genre = str(manuscript.get("genre") or "").strip()
    provenance = _load_provenance(root, path, content)
    return {"selected": selected, "path": path, "origin": origin, "content": content,
            "byte_revision": 'sha256:' + hashlib.sha256(raw).hexdigest(),
            "guidance": guidance, "genre": genre, "provenance": provenance}


def _profile_choices(root: Path) -> list[dict]:
    profiles = []
    for candidate in sorted((root / "profiles" / "voice").glob("*.md")):
        if candidate.stat().st_size > MAX_PROFILE_BYTES:
            profiles.append({"path": candidate.relative_to(root).as_posix(),
                             "name": candidate.stem, "origin": "project",
                             "status": "REFUSED", "reason": "profile exceeds bounded size",
                             "title": candidate.stem, "version": None})
            continue
        text = candidate.read_text(encoding="utf-8")
        candidate_metadata = _profile_metadata(text)
        profiles.append({"path": candidate.relative_to(root).as_posix(),
                         "name": candidate.stem, "origin": "project", "status": "AVAILABLE",
                         "revision": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
                         "title": candidate_metadata["title"],
                         "version": candidate_metadata["version"]})
    if not any(row["path"] == DEFAULT_PROFILE for row in profiles):
        deployed, deployed_origin = _profile(root, DEFAULT_PROFILE)
        deployed_metadata = _profile_metadata(deployed.read_text(encoding="utf-8"))
        profiles.append({"path": DEFAULT_PROFILE, "name": deployed.stem,
                         "origin": deployed_origin, "status": "AVAILABLE",
                         "revision": _file_digest(deployed),
                         "title": deployed_metadata["title"],
                         "version": deployed_metadata["version"]})
    return profiles


def global_catalogue(repo_root=None) -> dict:
    """Global profile identities without loading project selection or provenance bodies."""
    root = _root(repo_root)
    rows = _profile_choices(root)
    selected = next(row for row in rows if row["path"] == DEFAULT_PROFILE)
    return {"scope": "global", "profile": DEFAULT_PROFILE, "profiles": rows,
        "profile_revision": selected["revision"], "profile_title": selected["title"],
        "profile_version": selected["version"], "profile_editable": selected["origin"] == "project",
        "profile_edit_reason": "Repository profile" if selected["origin"] == "project" else "Deployed fallback is read-only here"}


def state(project: str, repo_root=None, *, profile_override: str | None = None) -> dict:
    root = _root(repo_root)
    selected = _selection(root, project, profile_override)
    content, guidance = selected["content"], selected["guidance"]
    profile_revision = selected['byte_revision']
    metadata = _profile_metadata(content)
    provenance = _provenance_summary(selected["provenance"], root)
    profiles = _profile_choices(root)
    genre = effective_genre(project, root, authored=selected['genre'])
    revision = _digest({"profile": selected["selected"], "profile_revision": profile_revision,
                        "guidance": guidance, "genre": selected["genre"],
                        "effective_genre": genre["effective"],
                        "provenance_revision": provenance["revision"]})
    return {"schema_version": "laplace.writing-style/2", "project": project,
            "revision": revision, "profile": selected["selected"],
            "profile_revision": profile_revision, "profile_origin": selected["origin"],
            "profile_title": metadata["title"], "profile_version": metadata["version"],
            "profile_editable": selected["origin"] == "project",
            "profile_edit_reason": ("This repository owns the selected profile."
                                    if selected["origin"] == "project"
                                    else "This project uses a deployed fallback; copy or select a repository profile before editing it."),
            "resolved_path": str(selected["path"]), "content": content,
            "runtime_content": _runtime_content(content),
            "guidance": guidance,
            "guidance_sha256": "sha256:" + hashlib.sha256(guidance.encode()).hexdigest(),
            "genre": selected["genre"], "effective_genre": genre["effective"],
            "genre_resolution": genre, "provenance": provenance, "profiles": profiles,
            "authority": "global profile content; manuscript_spec.json owns profile selection, genre and project guidance",
            "scope": "global voice profile plus explicit project selection/genre/guidance; project guidance does not promote global law"}


def context(project: str, repo_root=None, *, profile_override: str | None = None) -> dict:
    """Concise, exactly versioned projection used at native-session orientation."""
    value = state(project, repo_root, profile_override=profile_override)
    return {"schema_version": value["schema_version"], "project": project,
            "revision": value["revision"], "selected_profile": value["profile"],
            "profile_revision": value["profile_revision"], "profile_path": value["profile"],
            "profile_title": value["profile_title"], "profile_version": value["profile_version"],
            "profile_editable": value["profile_editable"],
            "profile_edit_reason": value["profile_edit_reason"],
            "profile_origin": value["profile_origin"],
            "selection_origin": 'explicit-section-contract' if profile_override else 'project-selection-or-workspace-default',
            # The voice profile's HOST path was the fourth absolute path the provider
            # instructions carried (src/laplace/writing_operating.py:315).  The session
            # names a profile by its id, revision and guidance digest, all of which are
            # here, and reads its bytes through the writing_style door; a host path named
            # the same profile in a spelling only this machine could resolve.
            "profile_read": {"operation": "writing_style", "payload": {"view": "profile"}},
            "content": value["runtime_content"],
            "content_scope": "Current runtime prompt and confirmed preferences; full profile is lazy",
            "guidance": value["guidance"], "guidance_sha256": value["guidance_sha256"],
            "genre": value["effective_genre"], "authored_genre": value["genre"],
            "effective_genre": value["effective_genre"], "genre_resolution": value["genre_resolution"],
            "provenance": value["provenance"], "scope": value["scope"],
            "read_more": {"operation": "writing_style",
                          "payloads": [{"view": "profile"}, {"view": "provenance"}]}}


def inspect(project: str, payload: dict | None = None, repo_root=None) -> dict:
    """Inspect bounded style identity; profile and provenance bodies are explicit descents."""
    payload = payload or {}
    unknown = set(payload) - {"view", "profile"}
    if unknown:
        raise ValueError("writing style inspection has unsupported fields: " + ", ".join(sorted(unknown)))
    view = str(payload.get("view") or "summary")
    root, value = _root(repo_root), state(project, repo_root)
    inspected_profile = str(payload.get("profile") or value["profile"])
    if project is not None and payload.get("profile") and view == "summary":
        raise ValueError("choose profile or provenance view to inspect an unselected profile")
    if inspected_profile == value["profile"]:
        inspected = {"profile": value["profile"], "profile_revision": value["profile_revision"],
            "profile_title": value["profile_title"], "profile_version": value["profile_version"],
            "profile_origin": value["profile_origin"], "profile_editable": value["profile_editable"],
            "profile_edit_reason": value["profile_edit_reason"], "runtime_content": value["runtime_content"],
            "content": value["content"], "resolved_path": value["resolved_path"],
            "provenance": value["provenance"]}
        selected_record = _selection(root, project)["provenance"]
    else:
        candidate_path, candidate_origin = _profile(root, inspected_profile)
        candidate_content = candidate_path.read_text(encoding="utf-8")
        candidate_metadata = _profile_metadata(candidate_content)
        selected_record = _load_provenance(root, candidate_path, candidate_content)
        inspected = {"profile": inspected_profile, "profile_revision": _file_digest(candidate_path),
            "profile_title": candidate_metadata["title"], "profile_version": candidate_metadata["version"],
            "profile_origin": candidate_origin, "profile_editable": candidate_origin == "project",
            "profile_edit_reason": ("This repository owns the inspected profile."
                if candidate_origin == "project" else "This is a deployed fallback and is not editable here."),
            "runtime_content": _runtime_content(candidate_content), "content": candidate_content,
            "resolved_path": str(candidate_path),
            "provenance": _provenance_summary(selected_record, root)}
    base = {key: value[key] for key in ("schema_version", "project", "revision", "profile",
            "profile_revision", "profile_title", "profile_version", "profile_editable",
            "profile_edit_reason", "profile_origin", "runtime_content",
            "guidance", "guidance_sha256", "genre", "effective_genre", "genre_resolution",
            "provenance", "profiles", "authority", "scope")}
    base.update({key: inspected[key] for key in ("profile_revision", "profile_title",
        "profile_version", "profile_editable", "profile_edit_reason", "profile_origin",
        "runtime_content", "provenance")})
    base.update(selected_profile=value["profile"] if project is not None else None, inspected_profile=inspected_profile)
    if project is None:
        base.update(profile=inspected_profile, scope="global", guidance="", genre="",
            revision=_digest({"profile": inspected_profile, "profile_revision": inspected["profile_revision"],
                              "provenance_revision": inspected["provenance"]["revision"]}),
            authority="profiles/voice owns shared profile bytes; project selection is unchanged")
    if view == "summary":
        return {**base, "read_more": [{"operation": "writing_style", "payload": {"view": "profile"}},
                                       {"operation": "writing_style", "payload": {"view": "provenance"}}]}
    if view == "profile":
        return {**base, "content": inspected["content"], "resolved_path": inspected["resolved_path"]}
    if view != "provenance":
        raise ValueError("writing style view must be summary, profile or provenance")
    data = selected_record.get("data") or {}
    return {**base, "sources": [{key: row.get(key) for key in
                                  ("path", "sha256", "coverage", "register")}
                                 for row in data.get("read") or []],
            "working_observations": data.get("working_observations") or [],
            "boundaries": data.get("boundaries") or [],
            "requested_remaining": data.get("requested_remaining") or [],
            "verification_limit": data.get("verification_limit")}


def _ledger_sources(record: dict) -> dict[str, dict]:
    return {str(row.get("path")): row for row in (record.get("data") or {}).get("read") or []
            if row.get("path")}


def calibration(project: str | None, payload: dict, repo_root=None, *, global_profile: str | None = None) -> dict:
    """Verify explicitly selected calibration handles and return a bounded read bundle."""
    root = _root(repo_root)
    unknown = set(payload) - {"sources", "purpose", "genre"}
    if unknown:
        raise ValueError("writing style calibration has unsupported fields: " + ", ".join(sorted(unknown)))
    requested = payload.get("sources")
    if not isinstance(requested, list) or not requested:
        raise ValueError("writing style calibration requires explicit ledger source handles")
    selected = _selection(root, project, global_profile)
    record = selected["provenance"]
    if record["status"] != "RECORDED":
        raise ValueError("the selected voice profile has no usable calibration ledger")
    ledger, rows, total = _ledger_sources(record), [], 0
    for request in requested:
        request = {"path": request} if isinstance(request, str) else request
        if not isinstance(request, dict) or set(request) - {"path", "line_start", "line_end"}:
            raise ValueError("each calibration source must name only path and optional line_start/line_end")
        path_key = str(request.get("path") or "")
        basis = ledger.get(path_key)
        if not basis or not str(basis.get("sha256") or "") or not str(basis.get("coverage") or "").strip():
            raise ValueError("calibration sources must use ledger handles with hash and reading coverage")
        target = (record["source_root"] / path_key).resolve()
        if not target.is_relative_to(record["source_root"]) or not target.is_file():
            rows.append({**{key: basis.get(key) for key in ("path", "sha256", "coverage", "register")},
                         "currentness": "MISSING", "text": None})
            continue
        current = hashlib.sha256(target.read_bytes()).hexdigest()
        expected = str(basis["sha256"]).removeprefix("sha256:")
        row = {**{key: basis.get(key) for key in ("path", "sha256", "coverage", "register")},
               "current_sha256": current, "currentness": "CURRENT" if current == expected else "STALE"}
        start, end = request.get("line_start"), request.get("line_end")
        if start is not None or end is not None:
            if row["currentness"] != "CURRENT":
                row["text"] = None
                row["note"] = "Recorded bytes changed; rerecord coverage before using an excerpt."
            elif target.suffix.lower() not in {".tex", ".md", ".txt"}:
                raise ValueError("line-bounded calibration excerpts require a recorded text source")
            elif not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool) or start < 1 or end < start or end - start + 1 > MAX_CALIBRATION_LINES:
                raise ValueError("calibration excerpt lines must be a positive bounded inclusive span")
            else:
                lines = target.read_text(encoding="utf-8").splitlines()
                excerpt = "\n".join(lines[start - 1:end])
                size = len(excerpt.encode())
                if total + size > MAX_CALIBRATION_BYTES:
                    raise ValueError("calibration excerpts exceed the bounded read bundle")
                total += size
                row.update(line_start=start, line_end=min(end, len(lines)), text=excerpt)
        rows.append(row)
    return {"schema_version": "laplace.writing-style-calibration/1", "project": project,
            "profile": selected["selected"], "profile_revision": _file_digest(selected["path"]),
            "provenance_revision": record["revision"], "purpose": str(payload.get("purpose") or "")[:1000],
            "genre": str(payload.get("genre") or selected["genre"])[:200], "sources": rows,
            "excerpt_bytes": total, "autonomous_analysis": False, "voice_score": None,
            "judgement_template": {"summary": "", "retained": [], "changed": [],
                "genre_boundary": "", "authorship_boundary": "", "verification_limit": "",
                "author_instruction": ""},
            "note": "This is source material for an explicit authored judgement, not a voice score or scientific verification."}


def _structured_judgement(value) -> dict:
    if not isinstance(value, dict) or set(value) - _JUDGEMENT_FIELDS:
        raise ValueError("profile update requires a structured authored judgement")
    summary = value.get("summary")
    if not isinstance(summary, str) or not summary.strip() or len(summary.encode()) > 4000:
        raise ValueError("authored judgement requires a bounded non-empty summary")
    result = {"summary": summary.strip()}
    for key in ("retained", "changed"):
        rows = value.get(key, [])
        if not isinstance(rows, list) or len(rows) > 30 or any(not isinstance(row, str) or len(row.encode()) > 1000 for row in rows):
            raise ValueError("authored judgement lists must contain bounded text")
        result[key] = [row.strip() for row in rows if row.strip()]
    for key in ("genre_boundary", "authorship_boundary", "verification_limit", "author_instruction"):
        text = value.get(key, "")
        if not isinstance(text, str) or len(text.encode()) > 4000:
            raise ValueError("authored judgement fields must be bounded text")
        result[key] = text.strip()
    return result


def update_profile(project: str, payload: dict, repo_root=None) -> dict:
    """The project tool retains its selected-profile authority and existing guards."""
    if not isinstance(project, str) or not project:
        raise ValueError("Project profile editing requires a selected registered project")
    return _update_profile(project, payload, repo_root)


def update_global_profile(payload: dict, repo_root=None, *, expected_current_provenance_revision=_UNPINNED) -> dict:
    """Explicit app-level profile editing through the same global file/provenance guards."""
    return _update_profile(None, payload, repo_root, global_profile=str(payload.get("profile") or ""),
        expected_current_provenance_revision=expected_current_provenance_revision)


def _update_profile(project: str | None, payload: dict, repo_root=None, *, global_profile: str | None = None,
                    validate_only: bool = False, expected_current_provenance_revision=_UNPINNED) -> dict:
    """Apply an explicit global profile edit with exact provenance guards; no model call."""
    from laplace.core import identity_doors
    identity_doors.admit_expected(payload, "writing_style_profile_change")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    root = _root(repo_root)
    required = {"profile", "content", "expected_profile_revision", "basis", "reason"}
    optional = {"expected_provenance_revision", "source_handles", "judgement",
                "provenance_kind", "by", "expected"}
    # This validator rejected unknown keys AND demanded the old guard name, so it was the one
    # converted door at which the grammar's token field could not be used even after the gate
    # was handed the payload -- measured by
    # evidence/WRITING_RECONCILIATION_2026-10-02/wave1/identity-tokens/expected_doors.py.
    # A caller presenting this home as a token is not asked for the old name as well, and the
    # list of old names is this door's shim and nothing else, so schema and gate cannot drift.
    if identity_doors.presents(payload, "style-profile"):
        required = required - identity_doors.old_names("writing_style_profile_change")
    unknown = set(payload) - required - optional
    if unknown or not required <= set(payload):
        raise ValueError("profile update requires profile, content, expected_profile_revision, basis and reason")
    selected = _selection(root, project, global_profile)
    if payload["profile"] != selected["selected"]:
        raise ValueError("inspect the project's currently selected profile before updating it")
    path, origin = _profile(root, payload["profile"])
    if origin != "project":
        raise ValueError("a deployed fallback profile cannot be updated from this repository")
    content = payload["content"]
    if not isinstance(content, str) or not content.strip() or len(content.encode()) > MAX_PROFILE_BYTES:
        raise ValueError("voice profile content must be bounded non-empty Markdown")
    basis = payload["basis"]
    if basis not in {"author_preference", "source_calibration", "reviewed_preference"}:
        raise ValueError("profile update basis must be author_preference, source_calibration or reviewed_preference")
    reason = payload["reason"]
    if not isinstance(reason, str) or not reason.strip() or len(reason.encode()) > 4000:
        raise ValueError("profile update requires a bounded non-empty reason")
    provenance_kind = payload.get("provenance_kind")
    if basis == "author_preference":
        if provenance_kind not in {"direct-author-instruction", "structured-author-edit"}:
            raise ValueError("author_preference requires direct-author-instruction or structured-author-edit provenance_kind")
        judgement = (_structured_judgement(payload["judgement"])
                     if "judgement" in payload else {"summary": reason.strip(), "retained": [],
                         "changed": [], "genre_boundary": "", "authorship_boundary": "",
                         "verification_limit": "", "author_instruction": reason.strip()})
    elif basis == "reviewed_preference":
        if provenance_kind != 'reviewed-profile-candidate':
            raise ValueError('reviewed_preference requires reviewed-profile-candidate provenance')
        judgement = {"summary": reason.strip(), "verification_limit":
            "Applied profile preference; no personal authorship or source calibration is asserted."}
    else:
        judgement = _structured_judgement(payload.get("judgement"))
    next_record = _load_provenance(root, path, content)
    normalized = []
    if basis == "source_calibration":
        if next_record["status"] != "RECORDED":
            raise ValueError("source-calibrated profile updates require a readable calibration ledger")
        if payload.get("expected_provenance_revision") != next_record["revision"]:
            raise ValueError("voice profile provenance revision conflict; inspect current provenance first")
        handles = payload.get("source_handles")
        if not isinstance(handles, list) or not handles:
            raise ValueError("source-calibrated profile updates require meaningful source handles")
        ledger = _ledger_sources(next_record)
        for handle in handles:
            if not isinstance(handle, dict) or set(handle) != {"path", "sha256"}:
                raise ValueError("source handles require exactly path and sha256")
            row = ledger.get(str(handle["path"]))
            if not row or not str(row.get("coverage") or "").strip() or str(row.get("sha256")).removeprefix("sha256:") != str(handle["sha256"]).removeprefix("sha256:"):
                raise ValueError("source handle does not match recorded hash and reading coverage")
            source = (next_record["source_root"] / str(handle["path"])).resolve()
            if not source.is_relative_to(next_record["source_root"]) or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != str(row["sha256"]).removeprefix("sha256:"):
                raise ValueError("a calibration source changed; inspect and rerecord it before updating the profile")
            normalized.append({"path": str(handle["path"]), "sha256": str(row["sha256"]),
                               "coverage": str(row["coverage"])})
    elif payload.get("source_handles"):
        raise ValueError("author-preference updates do not claim calibration source handles")
    from laplace.core import identity_doors
    if (payload.get("expected_provenance_revision") is not None
            or identity_doors.presents(payload, "style-provenance")):
        # `style-provenance`, a different home from `style-profile` two lines below and from
        # `style-state` in save(): three homes, three names, one door -- and the census found
        # all four of writing_style's values identical across two projects, because
        # `style-profile` is a GLOBAL home read through a per-project door.
        identity_doors.gate(
            "writing_style_profile_change",
            # The payload, so a `style-provenance` token in `expected` reaches the gate; the
            # old name's value is unchanged, and `expected_profile_revision` beside it names a
            # home this gate did not read, which `gate` passes over.
            supplied=payload,
            homes=[("style-provenance", project, next_record.get("revision"))],
            required=["expected_provenance_revision"],
            said="voice profile provenance revision conflict; inspect current provenance first")
    from filelock import FileLock
    from laplace.core.records import journal
    by = str(payload.get("by") or "author")[:200]
    intent = "VOICEPROFILE-" + uuid.uuid4().hex
    (root / "contract").mkdir(parents=True, exist_ok=True)
    with FileLock(str(path) + ".lock"):
        before_revision = _file_digest(path)
        if expected_current_provenance_revision is not _UNPINNED:
            existing_provenance = _load_provenance(root, path, path.read_text(encoding='utf-8'))
            if existing_provenance.get('revision') != expected_current_provenance_revision:
                raise ValueError('CHANGED_INPUT: current voice provenance changed; the candidate is retained.')
        # The profile file is a GLOBAL home (profiles/voice/...), not a per-project one, so its
        # home id has no project part: `style-profile::<path>`.  The digest handed to the gate
        # is the one `_file_digest` just produced at :34; nothing is recomputed.
        identity_doors.gate(
            "writing_style_profile_change", supplied=payload,
            homes=[("style-profile", "::%s" % (payload["profile"],), before_revision)],
            required=["expected_profile_revision"],
            said="voice profile revision conflict; inspect current profile first")
        # Recheck the calibration inputs while holding the actual consumer's
        # write lock. A pre-lock read never grants authority over a later ledger.
        checked_record = _load_provenance(root, path, content)
        if checked_record.get('revision') != next_record.get('revision'):
            raise ValueError('voice profile provenance revision conflict; inspect current provenance first')
        for handle in normalized:
            source = (checked_record['source_root'] / handle['path']).resolve()
            if (not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()
                    != str(handle['sha256']).removeprefix('sha256:')):
                raise ValueError('a calibration source changed; inspect and rerecord it before updating the profile')
        if validate_only:
            return {'profile_revision': before_revision, 'provenance_revision': next_record.get('revision'),
                    'source_handles': normalized, 'validated': True}
        after_revision = "sha256:" + hashlib.sha256(content.encode()).hexdigest()
        journal.bank_row("contract/talk.jsonl", {"record": "voice-profile-change-intent",
            "id": intent, "project": project, "profile": payload["profile"], "by": by,
            "before_revision": before_revision, "after_revision": after_revision,
            "basis": basis, "reason": reason.strip(), "provenance_kind": provenance_kind,
            "provenance_revision": next_record.get("revision"),
            "source_handles": normalized, "judgement": judgement}, root=root)
        pending = path.with_name(path.name + "." + uuid.uuid4().hex + ".pending")
        pending.write_bytes(content.encode('utf-8'))
        pending.replace(path)
    result = inspect(project, {"view": "summary", **({"profile": global_profile} if global_profile else {})}, root)
    journal.bank_row("contract/talk.jsonl", {"record": "voice-profile-change",
        "id": "VOICEPROFILE-DONE-" + uuid.uuid4().hex, "intent_id": intent,
        "project": project, "profile": payload["profile"], "by": by,
        "before_revision": before_revision, "after_revision": result["profile_revision"],
        "basis": basis, "provenance_revision": next_record.get("revision")}, root=root)
    return {**result, "scope_changed": "global-profile", "autonomous_analysis": False,
            "record_id": intent}


def save(project: str, payload: dict, repo_root=None, *, selected_profile_revision: str | None = None) -> dict:
    """Change only project selection/guidance; global profile bytes are never edited."""
    from laplace.core import identity_doors
    identity_doors.admit_expected(payload, "writing_style_change")   # D-R1: canonical presence is admitted before any read, lock or effect (identity_doors.admit_expected)
    root = _root(repo_root)
    from laplace.manuscript import manuscript_source
    if manuscript_source.resolve(project, repo_root=root).get("read_only"):
        raise ValueError("selected manuscript source is read-only")
    from laplace.pipeline import projection_spec
    path = projection_spec.spec_path(project, root)
    if path is None:
        raise ValueError("project has no canonical manuscript specification")
    expected, by = payload.get("expected_revision"), str(payload.get("by") or "author")[:200]
    intent_id, audit = "WRITINGSTYLE-" + uuid.uuid4().hex, {}
    (root / "contract").mkdir(parents=True, exist_ok=True)
    def update(spec):
        current = state(project, root)
        from laplace.core import identity_doors
        identity_doors.gate("writing_style_change",
                            # `payload.get("expected_revision")` IS `expected` (:473), so the
                            # old name behaves identically and `expected` becomes reachable.
                            supplied=payload,
                            homes=[("style-state", project, current["revision"])],
                            required=["expected_revision"],
                            said="writing style revision conflict; read current style first")
        chosen = current["profile"] if "profile" not in payload else payload["profile"]
        if not isinstance(chosen, str):
            raise ValueError("voice profile must be a path string")
        if selected_profile_revision is not None:
            selected_path, _ = _profile(root, chosen)
            if _file_digest(selected_path) != selected_profile_revision:
                raise ValueError('CHANGED_INPUT: proposed selected voice profile changed; candidate retained.')
        _profile(root, chosen)
        guidance = current["guidance"] if "guidance" not in payload else payload["guidance"]
        if not isinstance(guidance, str) or len(guidance.encode()) > 20_000:
            raise ValueError("project writing guidance must be bounded text")
        guidance = guidance.strip()
        genre = current["genre"] if "genre" not in payload else payload["genre"]
        if not isinstance(genre, str) or len(genre.encode()) > 1000:
            raise ValueError("project manuscript genre must be bounded text")
        genre = genre.strip()
        before = {key: current[key] for key in
                  ("revision", "profile", "profile_revision", "profile_origin", "content", "guidance", "genre")}
        from laplace.core.records import journal
        journal.bank_row("contract/talk.jsonl", {"record": "writing-style-change-intent",
            "id": intent_id, "project": project, "by": by, "before": before,
            "after_selection": {"profile": chosen, "guidance": guidance, "genre": genre}}, root=root)
        audit["before"] = before
        manuscript = spec.setdefault("manuscript", {})
        manuscript["voice_profile"], manuscript["style_guidance"] = chosen, guidance
        manuscript["genre"] = genre
        return spec
    if selected_profile_revision is not None:
        # A candidate pins its newly selected profile as well as the current
        # project state. Hold that real profile writer's lock through the spec
        # update so concurrent shared edits cannot race the selection guard.
        from filelock import FileLock
        selected_name = payload.get('profile') or _selection(root, project)['selected']
        selected_path, selected_origin = _profile(root, selected_name)
        if selected_origin == 'project':
            with FileLock(str(selected_path) + '.lock'):
                projection_spec.update_file(path, update)
        else:
            projection_spec.update_file(path, update)
    else:
        projection_spec.update_file(path, update)
    result = state(project, root)
    from laplace.core.records import journal
    journal.bank_row("contract/talk.jsonl", {"record": "writing-style-change",
        "id": "WRITINGSTYLE-DONE-" + uuid.uuid4().hex, "intent_id": intent_id,
        "project": project, "by": by, "before": audit["before"],
        "after": {key: result[key] for key in
                  ("revision", "profile", "profile_revision", "profile_origin", "content", "guidance", "genre")}}, root=root)
    return result
