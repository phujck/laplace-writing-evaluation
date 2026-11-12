"""Presentation profiles and bounded, source-preserving compiled previews."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import threading
import time
import uuid

from filelock import FileLock
from laplace.manuscript import manuscript_source, tex_dependencies
from laplace.pipeline import registry

_JOBS: dict[tuple[str, str], dict] = {}
_LOCK = threading.RLock()
_PRESETS = {"book": "book", "article": "article", "report": "report", "briefing": "article"}
from laplace.manuscript.document import CLASS_RE as _CLASS_RE
_CLASS_FAMILIES = {
    "book": {"book", "memoir", "scrbook"},
    "report": {"report", "scrreprt"},
    "article": {"article", "amsart", "revtex4", "revtex4-1", "revtex4-2",
                "ieeetran", "elsarticle", "acmart", "llncs", "aastex", "aastex6",
                "aastex631", "proc"},
}


def _base(project, root=None, *, writable=False, _observed_source=None):
    root = Path(root or registry._repo_root()).resolve()
    source = _observed_source if _observed_source is not None else manuscript_source.resolve(project, repo_root=root, include_candidates=False)
    if _observed_source is not None and source.get("project")!=project:
        raise ValueError("The observed source belongs to another project.")
    if source.get("status") != "resolved":
        raise ValueError("Choose a manuscript source before adjusting its presentation.")
    if writable and source.get("read_only"):
        raise ValueError("The selected manuscript source is read-only.")
    base = (root / source["manuscript_dir"]).resolve()
    project_record = registry.resolve(project, repo_root=root)
    canonical = project_record.path(project_record.manuscript_dir, root) if project_record else None
    if canonical is not None and canonical.resolve().is_relative_to(root) and (root / source['root']).resolve().is_relative_to(canonical.resolve()):
        base = canonical.resolve()
    storage = ((root / source["storage_dir"]).resolve() if source.get("read_only") and source.get("storage_dir") else base)
    if not storage.is_relative_to(root):
        raise ValueError("Style workspace escapes the active project checkout.")
    return root, source, base, storage


def _atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _validate(value):
    preset = value.get("preset") or value.get("profile") or "book"
    if preset.startswith("profiles/typography/"):
        preset = Path(preset).stem
    if preset not in _PRESETS:
        raise ValueError("Choose book, article, report or briefing.")
    def choice(key, default, allowed):
        v = str(value.get(key, default))
        if v not in allowed:
            raise ValueError(f"Unsupported {key}: {v}")
        return v
    visuals = dict(value.get("visual_overrides") if "visual_overrides" in value else value.get("visuals") or {})
    aliases = {"width":"width_inches", "height":"height_inches", "dpi":"preview_dpi"}
    visuals = {aliases.get(k,k):v for k,v in visuals.items()}
    if set(visuals) - {"font_size", "width_inches", "height_inches", "preview_dpi", "palette"}:
        raise ValueError("Unknown visual style setting.")
    for key in ("font_size", "width_inches", "height_inches", "preview_dpi"):
        if key in visuals:
            number = float(visuals[key])
            bounds = {"font_size": (6, 24), "width_inches": (2, 16), "height_inches": (1, 16), "preview_dpi": (72, 600)}[key]
            if not bounds[0] <= number <= bounds[1]:
                raise ValueError(f"Visual {key} must be between {bounds[0]} and {bounds[1]}.")
            visuals[key] = number
    if "palette" in visuals and (not isinstance(visuals["palette"], list) or not visuals["palette"]
            or any(not re.fullmatch(r"#[0-9a-fA-F]{6}", str(v)) for v in visuals["palette"])):
        raise ValueError("Palette must contain hexadecimal RGB colours.")
    overrides = dict(visuals)
    margins = choice("margins", "25mm", {"20mm", "25mm", "30mm", "0.75in", "1in", "1.25in"})
    columns = choice("columns", "1", {"1", "2"})
    paper_size = choice("paper_size", "a4paper", {"a4paper", "letterpaper"})
    margin_inches = float(margins[:-2]) / (25.4 if margins.endswith('mm') else 1)
    width = ((210/25.4 if paper_size=='a4paper' else 8.5)-2*margin_inches-(int(columns)-1)*.2)/int(columns)
    visuals.setdefault('width_inches', round(width,3))
    visuals.setdefault('height_inches', round(max(2.0,width*.62),3))
    return {"preset": preset, "profile": preset,
            "font_size": choice("font_size", "11pt", {"10pt", "11pt", "12pt"}),
            "margins": margins,
            "line_spacing": choice("line_spacing", "1.15", {"1", "1.15", "1.5", "2"}),
            "columns": columns,
            "paper_size": paper_size,
            "visuals": visuals, "visual_overrides": overrides}


def _class_family(name: str) -> str | None:
    lowered = name.casefold()
    for family, names in _CLASS_FAMILIES.items():
        if lowered in names:
            return family
    return None


def _styled_documentclass(text: str, style: dict) -> tuple[str, dict]:
    match = _CLASS_RE.search(text)
    if match is None:
        raise ValueError("The selected root lacks a document class.")
    original = match.group(2).strip()
    original_options = [item.strip() for item in (match.group(1) or "").split(",") if item.strip()]
    requested_family = _PRESETS[style["preset"]]
    family = _class_family(original)
    if family is None:
        raise ValueError("The custom document class " + original + " cannot be replaced by a preset. Edit its exact source and build the selected manuscript.")
    preserve = family == requested_family
    rendered_class = original if preserve else requested_family
    removable = {"10pt", "11pt", "12pt", "a4paper", "letterpaper",
                 "onecolumn", "twocolumn"}
    if original.casefold().startswith("revtex"):
        removable |= {"preprint", "reprint"}
    options = ([item for item in original_options if item.casefold() not in removable]
               if preserve else [])
    options.extend([style["font_size"], style["paper_size"]])
    if rendered_class.casefold().startswith("revtex"):
        options.append("reprint" if style["columns"] == "2" else "preprint")
    else:
        options.append("twocolumn" if style["columns"] == "2" else "onecolumn")
    options = list(dict.fromkeys(options))
    replacement = "\\documentclass[" + ",".join(options) + "]{" + rendered_class + "}"
    revised = text[:match.start()] + replacement + text[match.end():]
    return revised, {"original_class": original, "rendered_class": rendered_class,
                     "class_family": requested_family, "class_preserved": preserve,
                     "original_options": original_options, "rendered_options": options}


def defaults_status(project, root=None, *, _observed_source=None):
    root, source, _, storage = _base(project, root, _observed_source=_observed_source)
    from laplace.pipeline import projection_spec
    return defaults_at(projection_spec.spec_path(project, root), storage / 'document_style.json', root)


def defaults_at(spec_path, legacy_path, root):
    """Authored canonical presence wins, including empty; legacy is read-only fallback."""
    root = Path(root).resolve()
    spec_path = Path(spec_path) if spec_path is not None else None
    legacy_path = Path(legacy_path)
    legacy = None; canonical = None; present = False
    if spec_path and spec_path.is_file():
        raw = spec_path.read_bytes(); spec = json.loads(raw)
        if not isinstance(spec, dict) or not isinstance(spec.get('manuscript', {}), dict):
            raise ValueError('Canonical manuscript rendering defaults are invalid; inspect manuscript_spec.json.')
        if 'presentation' in spec.get('manuscript', {}):
            present = True; canonical = spec['manuscript']['presentation']
            if not isinstance(canonical, dict):
                raise ValueError('Authored canonical presentation must be an object; legacy fallback is not permitted.')
    if legacy_path.is_file():
        legacy = json.loads(legacy_path.read_bytes())
        if not isinstance(legacy, dict):raise ValueError('Legacy document defaults are invalid.')
    effective = canonical if present else legacy if legacy is not None else {}
    origin = 'canonical-spec' if present else 'legacy-read-only-fallback' if legacy is not None else 'defaults'
    selected = spec_path if present else legacy_path if legacy is not None else None
    value_revision = 'sha256:' + hashlib.sha256(json.dumps(effective, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    return {'values': effective, 'effective_origin': origin, 'revision': 'sha256:' + hashlib.sha256(json.dumps(
        [origin, selected.relative_to(root).as_posix() if selected else None, value_revision]).encode()).hexdigest(),
        'consumed_source': {'path': selected.relative_to(root).as_posix() if selected else None,
            'field': 'manuscript.presentation' if present else None, 'revision': value_revision},
        'canonical_present': present, 'legacy_present': legacy is not None,
        'legacy_conflict': bool(present and legacy is not None and canonical != legacy),
        'authority': 'Rendering and figure defaults only. Current class/options belong to actual TeX source.',
        'migration': 'No preview-triggered writes. Later authorised defaults migration may explicitly retire legacy fallback.'}


def load(project, root=None, *, _observed_source=None):
    return defaults_status(project, root, _observed_source=_observed_source)['values']


def save(project, style, root=None):
    from laplace.manuscript.document_templates import legacy_refusal
    raise legacy_refusal(project, 'Legacy style save wrote two settings stores. Use the guarded template candidate source flow; rendering defaults remain separately owned.')


def _home(root, project):
    return root / ".laplace-cache" / "writing-style" / project


def status(project, root=None):
    from laplace.manuscript.document_templates import handle
    root = Path(root or registry._repo_root()).resolve()
    path = _home(root, project) / 'latest.json'
    old = json.loads(path.read_text()) if path.is_file() else {}
    return {'status': 'RETIRED', 'legacy_preview_id': old.get('id'),
        'reason': 'Legacy mutable style previews are historical. Inspect exact template candidates and their addressed build/output.',
        'candidates_read': handle(project, {'view': 'template-candidates'})}


def current_status(project, root=None, *, source=None, source_tree=None, include_preview=True) -> dict:
    """Compatibility for style-era callers; current document composition lives in writing.document.

    Retire this wrapper once external imports of document_style.current_status
    migrate; all application HTTP/native/walk consumers use the domain owner.
    """
    from laplace.manuscript import document
    return document.current(project, root, source=source, source_tree=source_tree, include_preview=include_preview)


def _preview_dependency_hashes(root, stage_root, target):
    """Map the staged build's consumed inputs back to their original files."""
    originals = set()
    for staged in tex_dependencies.dependency_paths(target, root):
        try:
            relative = staged.relative_to(stage_root)
        except ValueError:
            original = staged
        else:
            original = (root / relative).resolve()
        if original.is_file() and original.is_relative_to(root):
            originals.add(original)
    return tex_dependencies.snapshot_paths(originals, root)


def pdf(project, root=None, *, candidate_ref=None, preview_ref=None):
    from laplace.manuscript.document_templates import legacy_refusal
    if not candidate_ref or not preview_ref:
        raise legacy_refusal(project, 'Preview PDF reads require the exact candidate and reviewed build/output proof; latest is discovery only.')
    from laplace.manuscript import build_targets
    observed = build_targets.inspect_preview(project, candidate_ref, preview_ref, Path(root or registry._repo_root()).resolve())
    return Path(observed['path']).read_bytes()


def _selected_source_pdf(project: str, root: Path, source: dict) -> tuple[Path, dict]:
    """Resolve only the fresh build owned by the selected manuscript edition."""
    from laplace.manuscript import projection_viewer
    if source.get("status") != "resolved" or not source.get("root"):
        raise ValueError("The selected manuscript edition changed; inspect it before exporting.")
    build = projection_viewer.recompile_status(source["root"], repo_root=root, corpus=project, compile_root=source["root"], _selection=source)
    expected = (root / source["root"]).resolve().with_suffix(".pdf")
    raw_pdf = build.get("pdf")
    observed = ((root / raw_pdf).resolve() if isinstance(raw_pdf, str) and not Path(raw_pdf).is_absolute()
                else Path(raw_pdf).resolve() if isinstance(raw_pdf, str) else None)
    if (build.get("state") != "done" or build.get("ok") is not True
            or build.get("fresh") is not True or build.get("running")
            or observed != expected or not expected.is_file()):
        reason = build.get("reason") or "the selected manuscript has no current successful PDF build"
        raise ValueError("Build the current selected manuscript before exporting it: " + reason)
    content = expected.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    identity = {key: source.get(key) for key in
                ("root", "manuscript_dir", "edition", "revision", "read_only", "selection")}
    receipt = {"id": "recompile:" + str(build.get("finished") or build.get("built_ts") or digest),
        "project": project, "status": "READY", "mode": "selected-source",
        "selected_source": identity, "pdf_path": str(expected), "pdf_sha256": digest,
        "build": {key: build.get(key) for key in
                  ("id", "producer", "state", "ok", "fresh", "pdf", "by", "started",
                   "finished", "built_ts", "dependency_changes")}}
    return expected, receipt


def _export_candidate(project: str, root: Path, source: dict, mode: str, *, candidate_ref=None, preview_ref=None) -> tuple[Path, dict]:
    if mode == 'selected-source':
        if candidate_ref or preview_ref:raise ValueError('Selected-source export cannot substitute candidate proof.')
        return _selected_source_pdf(project, root, source)
    if mode != 'style-preview':raise ValueError('export mode must be selected-source or style-preview')
    from laplace.manuscript import build_targets, document_templates
    if not candidate_ref or not preview_ref:raise document_templates.legacy_refusal(project,'Template preview export needs exact candidate_ref and preview_ref; latest is not authority.')
    observed=build_targets.inspect_preview(project,candidate_ref,preview_ref,root)
    return Path(observed['path']),{'id':preview_ref['build_receipt_id'],'project':project,'mode':'style-preview','status':'READY',
        'candidate_ref':candidate_ref,'preview_ref':preview_ref,'pdf_sha256':preview_ref['output']['content_revision'].removeprefix('sha256:'),
        'selected_source':document_templates.candidate(project,candidate_ref,root)['proposal']['selected_source']}


def export_pdf(project, root=None, mode="selected-source", *, candidate_ref=None, preview_ref=None):
    """Keep an exact selected-edition build (default) or explicit style preview."""
    root, source, _, storage = _base(project, root, writable=True)
    export_dir = storage / 'exports'
    with _LOCK, FileLock(str(storage / '.document-style-export.lock'), timeout=15):
        pdf_path, receipt = _export_candidate(project, root, source, mode,candidate_ref=candidate_ref,preview_ref=preview_ref)
        content = pdf_path.read_bytes()
        content_digest = hashlib.sha256(content).hexdigest()
        if content_digest != receipt.get('pdf_sha256'):
            raise ValueError('The selected PDF changed before export; build it again.')
        # Re-read the same owner after the bytes. A source/style change racing
        # export cannot receive a durable current receipt.
        _, checked = _export_candidate(project, root, manuscript_source.resolve(
            project, repo_root=root), mode,candidate_ref=candidate_ref,preview_ref=preview_ref)
        if ({key:checked.get(key) for key in ('mode','pdf_sha256','selected_source','id')} !=
                {key:receipt.get(key) for key in ('mode','pdf_sha256','selected_source','id')}):
            raise ValueError('The selected PDF became stale during export; nothing was saved.')
        from laplace.pipeline import registry
        from laplace.manuscript.document_metadata import basename
        project_record = registry.resolve(project, repo_root=root)
        title = project_record.manifest.get('display_name') or project
        name = basename(title) + '-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6]
        export_dir.mkdir(parents=True, exist_ok=True)
        target = export_dir / (name + '.pdf')
        receipt_path = export_dir / (name + '.json')
        pending = target.with_name(target.name + '.pending')
        pending.write_bytes(content)
        pending.replace(target)
        result = {**receipt, 'exported_file':target.relative_to(root).as_posix(),
                  'export_receipt': receipt_path.relative_to(root).as_posix(),
                  'pdf_sha256':content_digest, 'exported_at':time.time()}
        try:
            _atomic(receipt_path, result)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        if hashlib.sha256(target.read_bytes()).hexdigest() != content_digest:
            target.unlink(missing_ok=True); receipt_path.unlink(missing_ok=True)
            raise ValueError('The exported PDF could not be verified; nothing was retained.')
        _, final = _export_candidate(project, root, manuscript_source.resolve(
            project, repo_root=root), mode,candidate_ref=candidate_ref,preview_ref=preview_ref)
        if ({key:final.get(key) for key in ('mode','pdf_sha256','selected_source','id')} !=
                {key:receipt.get(key) for key in ('mode','pdf_sha256','selected_source','id')}):
            target.unlink(missing_ok=True); receipt_path.unlink(missing_ok=True)
            raise ValueError('The selected PDF became stale during export; nothing was retained.')
        from laplace.core.records import journal
        (root / 'contract').mkdir(parents=True, exist_ok=True)
        journal.bank_row('contract/talk.jsonl', {'record':'manuscript-export','id':'EXPORT-'+uuid.uuid4().hex,
            'project':project,'file':result['exported_file'],'pdf_sha256':result['pdf_sha256'],
            'mode':mode,'selected_source':receipt.get('selected_source'),
            'build_id':receipt['id'],'receipt':result['export_receipt']},root=root)
        from urllib.parse import urlencode
        return {'file':result['exported_file'],'receipt':result['export_receipt'],
                'mode':mode,'selected_source':receipt.get('selected_source'),
                'pdf_sha256':result['pdf_sha256'],
                'url':'/projection/pdf?'+urlencode({'file':result['exported_file'],'corpus':project,
                                                     'export_receipt':result['export_receipt']})}


class ExportReadRefused(ValueError):
    def __init__(self, message: str, reason: str):
        super().__init__(message); self.reason = reason


def exported_pdf(project, file, root=None, *, receipt=None):
    """THE SAVED EXPORT READ (repair1 RP-R5): one immutable exported PDF by the identity export_pdf issued.

    A saved export is a distinct exact artifact, never the selected current manuscript output, so it is read through
    its own receipt rather than the compile-root membership of whatever source is selected now. The exact spelling is
    a public repository path (no private/runtime namespace, no symlink component, no escape) in an ``exports``
    directory under a REGISTERED home of ``project``; its sibling receipt must name this project, this exact file and
    itself; the bytes must equal the recorded pin. Every check precedes reading the PDF. Returns (bytes, receipt)."""
    from laplace.core.perimeter import public_repository_path
    root = Path(root or registry._repo_root()).resolve()
    if not isinstance(file, str) or not file.lower().endswith('.pdf'):
        raise ExportReadRefused('A saved export is read by its exact .pdf path.', 'export-path-refused')
    try:
        target = public_repository_path(root, file)
    except ValueError as error:
        raise ExportReadRefused(str(error), 'export-path-refused') from error
    rel = target.relative_to(root).as_posix()
    record = registry.resolve(project, repo_root=root) if project else None
    homes = [value for value in ((record.project_dir, getattr(record, 'tex_root', None), record.manuscript_dir) if record and not record.external_root else ())
             if isinstance(value, str) and value not in {'', '.'} and not Path(value).is_absolute()]
    if target.parent.name != 'exports' or not any(Path(rel).is_relative_to(Path(home)) for home in homes):
        raise ExportReadRefused('This PDF is not a saved export of the named project.', 'export-project-mismatch')
    receipt_rel = rel[:-len('.pdf')] + '.json'
    if receipt is not None and receipt != receipt_rel:
        raise ExportReadRefused('The named export receipt is not this export\'s receipt.', 'export-receipt-mismatch')
    try:
        value = json.loads(public_repository_path(root, receipt_rel).read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        raise ExportReadRefused('The export receipt is missing or unreadable; the saved PDF is not served.', 'export-receipt-missing') from error
    pin = value.get('pdf_sha256') if isinstance(value, dict) else None
    if (not isinstance(pin, str) or not re.fullmatch(r'[0-9a-f]{64}', pin)
            or (value.get('project'), value.get('exported_file'), value.get('export_receipt')) != (project, rel, receipt_rel)):
        raise ExportReadRefused('The export receipt does not name this project and exact file.', 'export-receipt-mismatch')
    if not target.is_file():
        raise ExportReadRefused('The saved export PDF is missing.', 'export-missing')
    data = target.read_bytes()
    if hashlib.sha256(data).hexdigest() != pin:
        raise ExportReadRefused('The saved export PDF no longer has its recorded bytes; nothing was served.', 'export-pin-changed')
    return data, value


def preview(project, style, root=None, *, wait=False):
    from laplace.manuscript.document_templates import legacy_refusal
    raise legacy_refusal(project, 'Preview no longer saves settings or starts a private compiler. Prepare an exact template candidate and use its existing build action.')
