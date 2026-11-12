"""Bounded, read-only previews for inline TikZ and tabular manuscript figures."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
from typing import Any

from filelock import FileLock

from laplace.manuscript import manuscript_source

_PATH = "/walk/figure-preview"
_MIME = {"png": "image/png", "pdf": "application/pdf"}
_MAX_BYTES = 160_000
_MAX_LINES = 700
_TIMEOUT = 45
_SLOTS = threading.BoundedSemaphore(2)
_ACTIVE_RENDERS = 0
_ACTIVE_LOCK = threading.Lock()
_BEGIN_DOC = re.compile(r"\\begin\s*\{document\}")
_DOCUMENTCLASS = re.compile(r"\\documentclass\s*(?:\[[^]]*\]\s*)?\{[^}]+\}")
_INPUT = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")
_PACKAGE = re.compile(r"\\usepackage\s*(?:\[[^]]*\]\s*)?\{([^}]+)\}")
_INLINE = re.compile(r"\\begin\s*\{(?:tikzpicture|tabular\*?|tabularx)\}")
_NEW_TCOLORBOX = re.compile(r"\\(?:new|renew|provide)tcolorbox\s*\{?\s*([A-Za-z@*]+)")
_NEW_THEOREM = re.compile(r"\\(?:new|renew)theorem(?:\*)?\s*\{\s*([A-Za-z@][A-Za-z0-9@:_*\-]*)\s*\}")
_NEW_ENVIRONMENT = re.compile(r"\\(?:new|renew)environment\s*\{\s*([A-Za-z@*]+)\s*\}")
_NEW_DOCUMENT_ENVIRONMENT = re.compile(r"\\(?:New|Renew|Provide)DocumentEnvironment\s*\{\s*([A-Za-z@*]+)\s*\}")
_DEFINECOLOR_HTML = re.compile(r"\\definecolor\s*\{([^}]+)\}\s*\{HTML\}\s*\{([0-9A-Fa-f]{6})\}")


class PreviewError(ValueError):
    def __init__(self, reason: str, *, status: int = 422, code: str = "UNSUPPORTED"):
        super().__init__(reason)
        self.status, self.code = status, code


def active_renders() -> int:
    with _ACTIVE_LOCK:
        return _ACTIVE_RENDERS


def _begin_render() -> None:
    global _ACTIVE_RENDERS
    with _ACTIVE_LOCK:
        _ACTIVE_RENDERS += 1


def _end_render() -> None:
    global _ACTIVE_RENDERS
    with _ACTIVE_LOCK:
        _ACTIVE_RENDERS = max(0, _ACTIVE_RENDERS - 1)


def _q(query: dict, key: str, default=""):
    value = query.get(key, default)
    return value[0] if isinstance(value, (list, tuple)) and value else value


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _selected(project: str, file: str, root: Path) -> tuple[Path, Path, dict]:
    source = manuscript_source.resolve(project, repo_root=root)
    if source.get("status") != "resolved" or not source.get("root"):
        raise PreviewError("selected manuscript source is unavailable", status=404, code="NO_SOURCE")
    traversal = manuscript_source.traversal(source["root"], repo_root=root)
    allowed = set(traversal.get("files") or [])
    raw = Path(str(file or ""))
    if raw.is_absolute() or ".." in raw.parts:
        raise PreviewError("figure source file must stay inside the selected manuscript")
    source_dir = Path(source.get("manuscript_dir") or "")
    source_dir = source_dir if source_dir.is_absolute() else root / source_dir
    candidates = [(root / raw).resolve(), (source_dir / raw).resolve()]
    for candidate in candidates:
        if not _inside(candidate, root) or not _inside(candidate, source_dir):
            continue
        relative = candidate.relative_to(root).as_posix()
        if relative in allowed and candidate.is_file():
            root_tex = (root / source["root"]).resolve()
            return candidate, root_tex, source
    raise PreviewError("figure source file is not in the selected manuscript traversal",
                       status=404, code="FILE_OUTSIDE_SOURCE")


def _span(path: Path, line_start: int, line_end: int, environment: str = "figure") -> str:
    if (isinstance(line_start, bool) or isinstance(line_end, bool)
            or line_start < 1 or line_end < line_start
            or line_end - line_start + 1 > _MAX_LINES):
        raise PreviewError("preview source span is outside the declared line bounds",
                           code="BAD_SPAN")
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    if line_end > len(lines):
        raise PreviewError("figure source span no longer exists", status=409, code="STALE_SPAN")
    source = "".join(lines[line_start - 1:line_end])
    if len(source.encode("utf-8")) > _MAX_BYTES:
        raise PreviewError("inline preview exceeds the bounded preview size", code="TOO_LARGE")
    stripped = source.strip()
    actual_environment = "figure*" if environment == "figure" and re.match(
        r"\\begin\s*\{figure\*\}", stripped) else environment
    start = re.compile(r"\\begin\s*\{" + re.escape(actual_environment) + r"\}")
    end = re.compile(r"\\end\s*\{" + re.escape(actual_environment) + r"\}\s*$")
    if not (start.match(stripped) and end.search(stripped)
            and _environment(stripped, actual_environment) == stripped):
        words = ("source span is not one complete figure environment" if environment == "figure"
                 else "source span is not one complete declared environment")
        raise PreviewError(words, code="NOT_ENVIRONMENT")
    return source


def _environment(tex: str, env: str) -> str | None:
    token = re.compile(r"\\(begin|end)\s*\{" + re.escape(env) + r"\}")
    depth = 0
    start = None
    for match in token.finditer(tex):
        if match.group(1) == "begin":
            if depth == 0:
                start = match.start()
            depth += 1
        elif depth:
            depth -= 1
            if depth == 0 and start is not None:
                return tex[start:match.end()]
    return None


def _balanced_end(text: str, start: int, opening: str, closing: str) -> int | None:
    if start >= len(text) or text[start] != opening:
        return None
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opening and (index == 0 or text[index - 1] != "\\"):
            depth += 1
        elif text[index] == closing and (index == 0 or text[index - 1] != "\\"):
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _command_spans(text: str, name: str, *, optional: bool) -> list[tuple[int, int]]:
    """Return complete command spans, refusing an unbalanced argument."""
    spans: list[tuple[int, int]] = []
    token = re.compile(r"\\" + re.escape(name) + r"\b")
    for match in token.finditer(text):
        cursor = match.end()
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if optional and cursor < len(text) and text[cursor] == "[":
            end = _balanced_end(text, cursor, "[", "]")
            if end is None:
                raise PreviewError(f"{name} has an unbalanced optional argument", code="UNBALANCED")
            cursor = end
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
        end = _balanced_end(text, cursor, "{", "}")
        if end is None:
            raise PreviewError(f"{name} has an unbalanced argument", code="UNBALANCED")
        spans.append((match.start(), end))
    return spans


def _without_commands(text: str, spans: list[tuple[int, int]]) -> str:
    # Preserve line geometry for diagnostics and any line-sensitive TeX payload.
    chars = list(text)
    for start, end in spans:
        for index in range(start, end):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars)


def supports(figure: str) -> bool:
    """Whether the exact figure contains an inline body this renderer owns."""
    return bool(_INLINE.search(figure))


def declared_environments(root_tex: Path, repo_root: Path) -> dict[str, str]:
    """Declared project environments that have an honest rendered block contract.

    This deliberately recognises only declaration forms whose bodies can be kept as
    source-mapped prose (theorem) or compiled faithfully (tcolorbox and generic
    local environments).  It follows
    preamble ``\\input`` files under the project fence, never distribution packages.
    """
    declared: dict[str, str] = {}
    queue = [root_tex]
    seen: set[Path] = set()
    while queue and len(seen) < 32:
        current = queue.pop(0).resolve()
        if current in seen or not _inside(current, repo_root) or not current.is_file():
            continue
        seen.add(current)
        text = current.read_text(encoding="utf-8", errors="replace")
        begin = _BEGIN_DOC.search(text)
        preamble = manuscript_source._uncomment(text[:begin.start()] if begin else text)
        for match in _NEW_TCOLORBOX.finditer(preamble):
            declared[match.group(1)] = "tcolorbox"
        for match in _NEW_THEOREM.finditer(preamble):
            declared.setdefault(match.group(1), "theorem")
        for match in _NEW_ENVIRONMENT.finditer(preamble):
            declared.setdefault(match.group(1), "compiled")
        for match in _NEW_DOCUMENT_ENVIRONMENT.finditer(preamble):
            declared.setdefault(match.group(1), "compiled")
        for match in _INPUT.finditer(preamble):
            raw = Path(match.group(1).strip())
            candidate = (current.parent / raw).with_suffix(raw.suffix or ".tex").resolve()
            if _inside(candidate, repo_root):
                queue.append(candidate)
    return declared


def declared_environment_presentation(root_tex: Path, repo_root: Path) -> dict[str, dict[str, str]]:
    """Visual names/counter declarations and safe local tcolorbox style hints.

    Theorem counters are metadata, never a simulated numbering authority.
    Only literal colour names and local ``\\definecolor{...}{HTML}{RRGGBB}`` values
    are emitted.  Arbitrary TeX option expressions remain absent for the client to
    use its neutral box fallback.
    """
    colours: dict[str, str] = {}
    boxes: dict[str, dict[str, str]] = {}

    def option_value(options: str, key: str) -> str | None:
        match = re.search(r"(?:^|,)\s*" + re.escape(key) + r"\s*=\s*", options)
        if match is None:
            return None
        start = match.end()
        if start < len(options) and options[start] == "{":
            end = _balanced_end(options, start, "{", "}")
            return options[start + 1:end - 1] if end is not None else None
        end = options.find(",", start)
        return options[start:] if end < 0 else options[start:end]
    queue = [root_tex]
    seen: set[Path] = set()
    while queue and len(seen) < 32:
        current = queue.pop(0).resolve()
        if current in seen or not _inside(current, repo_root) or not current.is_file():
            continue
        seen.add(current)
        text = current.read_text(encoding="utf-8", errors="replace")
        begin = _BEGIN_DOC.search(text)
        preamble = manuscript_source._uncomment(text[:begin.start()] if begin else text)
        colours.update({name: "#" + value.upper() for name, value in _DEFINECOLOR_HTML.findall(preamble)})
        for match in _NEW_THEOREM.finditer(preamble):
            cursor = match.end()
            def argument(opening: str, closing: str) -> str | None:
                nonlocal cursor
                while cursor < len(preamble) and preamble[cursor].isspace():
                    cursor += 1
                end = _balanced_end(preamble, cursor, opening, closing)
                if end is None:
                    return None
                value = preamble[cursor + 1:end - 1]
                cursor = end
                return value
            shared = argument("[", "]")
            label = argument("{", "}")
            if label is None:
                continue
            within = argument("[", "]")
            numbered = "*" not in match.group(0).split("{", 1)[0]
            boxes[match.group(1)] = {"theorem_label": label,
                "numbered": "true" if numbered else "false",
                "counter": (shared or match.group(1)) if numbered else "",
                "within_counter": within or ""}
        for match in _NEW_TCOLORBOX.finditer(preamble):
            body_start = preamble.find("{", match.end())
            body_end = _balanced_end(preamble, body_start, "{", "}") if body_start >= 0 else None
            if body_end is None:
                continue
            options = preamble[body_start + 1:body_end - 1]
            style: dict[str, str] = {}
            for key in ("colback", "colframe", "colbacktitle"):
                value = re.search(r"(?:^|,)\s*" + key + r"\s*=\s*([A-Za-z][A-Za-z0-9@*]*)\s*(?:,|$)", options)
                if value:
                    name = value.group(1)
                    style[key] = colours.get(name, name)
            title_template = option_value(options, "title")
            if title_template is not None:
                style["title_template"] = title_template
            if style:
                boxes[match.group(1)] = style
        for match in _INPUT.finditer(preamble):
            raw = Path(match.group(1).strip())
            candidate = (current.parent / raw).with_suffix(raw.suffix or ".tex").resolve()
            if _inside(candidate, repo_root):
                queue.append(candidate)
    return boxes


def _snippet(figure: str) -> tuple[str, str]:
    body_match = re.search(r"\\begin\s*\{figure\*?\}(?:\[[^]]*\])?", figure)
    end = re.search(r"\\end\s*\{figure\*?\}\s*$", figure)
    if not body_match or not end or body_match.end() > end.start():
        raise PreviewError("figure delimiters are unbalanced", code="UNBALANCED")
    body = figure[body_match.end():end.start()]
    tikz_count = len(re.findall(r"\\begin\s*\{tikzpicture\}", body))
    table_count = len(re.findall(r"\\begin\s*\{(?:tabular\*?|tabularx)\}", body))
    if not (tikz_count or table_count):
        raise PreviewError("figure has no supported inline TikZ or tabular body",
                           code="UNSUPPORTED_FIGURE")
    spans = _command_spans(body, "caption", optional=True)
    spans.extend(_command_spans(body, "label", optional=False))
    rendered = _without_commands(body, sorted(spans)).strip()
    if tikz_count == 1 and not table_count and "\\includegraphics" not in rendered:
        kind = "tikz"
    elif table_count and not tikz_count and "\\includegraphics" not in rendered:
        kind = "table"
    else:
        kind = "composite"
    return kind, rendered


def _preamble(root_tex: Path, repo_root: Path, kind: str) -> tuple[str, dict[str, str]]:
    text = root_tex.read_text(encoding="utf-8", errors="replace")
    begin = _BEGIN_DOC.search(text)
    raw = text[:begin.start()] if begin else text
    if not _DOCUMENTCLASS.search(raw):
        raise PreviewError("selected manuscript preamble has no document class", code="NO_PREAMBLE")
    if kind == "tikz":
        rendered = _DOCUMENTCLASS.sub(lambda _match: r"\documentclass[tikz,border=2pt]{standalone}", raw, count=1)
    elif kind in {"table", "composite"}:
        rendered = _DOCUMENTCLASS.sub(lambda _match: r"\documentclass[border=2pt,varwidth=40cm]{standalone}", raw, count=1)
    else:
        # Custom environments can depend on class counters (e.g. book's chapter
        # counter).  Preserve the selected root's actual class and preamble.
        rendered = raw
    dependencies: dict[str, str] = {}
    queue = [(root_tex, raw)]
    seen: set[Path] = set()
    fence = repo_root
    while queue and len(seen) < 32:
        current, current_text = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        for match in _INPUT.finditer(current_text):
            raw_path = Path(match.group(1).strip())
            candidate = (current.parent / raw_path).with_suffix(raw_path.suffix or ".tex").resolve()
            if candidate.is_file() and _inside(candidate, fence):
                data = candidate.read_bytes()
                dependencies[candidate.relative_to(repo_root).as_posix()] = hashlib.sha256(data).hexdigest()
                queue.append((candidate, data.decode("utf-8", errors="replace")))
        for match in _PACKAGE.finditer(current_text):
            for package in match.group(1).split(","):
                candidate = (current.parent / (package.strip() + ".sty")).resolve()
                if candidate.is_file() and _inside(candidate, fence):
                    dependencies[candidate.relative_to(repo_root).as_posix()] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    return rendered, dependencies


def _key(project: str, file: Path, lines: tuple[int, int], figure: str,
         preamble: str, dependencies: dict[str, str]) -> str:
    value = {"schema": "laplace.inline-figure-preview/2", "project": project,
             "file": file.as_posix(), "lines": lines, "figure": figure,
             "preamble": preamble, "dependencies": dependencies}
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _compile(source: str, work: Path, cwd: Path) -> dict[str, Any]:
    latex = shutil.which("pdflatex") or shutil.which("lualatex")
    if not latex:
        raise PreviewError("no local TeX compiler is available", status=503, code="NO_TEX")
    work.mkdir(parents=True, exist_ok=True)
    tex = work / "preview.tex"
    tex.write_text(source, encoding="utf-8")
    command = [latex, "-no-shell-escape", "-recorder", "-interaction=nonstopmode", "-halt-on-error",
               "-output-directory", str(work), str(tex)]
    try:
        run = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=_TIMEOUT)
    except subprocess.TimeoutExpired:
        raise PreviewError("inline figure preview exceeded its time bound", status=504,
                           code="TIMEOUT")
    pdf = work / "preview.pdf"
    if run.returncode or not pdf.is_file():
        reason = ((run.stdout or "") + (run.stderr or ""))[-3000:]
        raise PreviewError("inline figure did not compile: " + reason, code="COMPILE_FAILED")
    cairo = shutil.which("pdftocairo")
    png = work / "preview.png"
    if cairo:
        try:
            converted = subprocess.run([cairo, "-png", "-singlefile", "-r", "180",
                                        str(pdf), str(png.with_suffix(""))],
                                       capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            converted = None
        if converted is None or converted.returncode or not png.is_file():
            png.unlink(missing_ok=True)
    return {"pdf": pdf, "png": png if png.is_file() else None,
            "fls": work / "preview.fls", "compiler": Path(latex).name}


def _lexical(path: Path) -> Path:
    """Absolute normalized path without resolving symlinks."""
    return Path(os.path.abspath(os.fspath(path)))


def _relative_lexical(path: Path, root: Path) -> str | None:
    try:
        return _lexical(path).relative_to(_lexical(root)).as_posix()
    except ValueError:
        return None


def _recorded_inputs(fls: Path, cwd: Path, repo_root: Path,
                     generated_dir: Path | None = None) -> dict[str, dict[str, str]]:
    if not fls.is_file():
        raise PreviewError("TeX compiler did not produce a dependency record",
                           code="NO_DEPENDENCY_RECORD")
    inputs: dict[str, dict[str, str]] = {}
    for line in fls.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("INPUT "):
            continue
        raw = line[6:].strip()
        if not raw:
            continue
        path = Path(raw)
        alias = _lexical(path if path.is_absolute() else cwd / path)
        if generated_dir is not None and _inside(alias, generated_dir):
            # preview.aux and siblings are compiler outputs, not manuscript inputs.
            continue
        relative = _relative_lexical(alias, repo_root)
        if relative is None:
            continue
        try:
            resolved = alias.resolve(strict=True)
        except OSError as exc:
            raise PreviewError(f"recorded figure dependency is unavailable: {relative}",
                               status=409, code="STALE_DEPENDENCY") from exc
        if not _inside(resolved, repo_root) or not resolved.is_file():
            raise PreviewError(f"recorded figure dependency escapes the project: {relative}",
                               code="DEPENDENCY_OUTSIDE_PROJECT")
        resolved_relative = resolved.relative_to(repo_root.resolve()).as_posix()
        inputs[relative] = {
            "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
            "resolved": resolved_relative,
        }
    return dict(sorted(inputs.items()))


def _output_hashes(cache: Path) -> dict[str, str]:
    return {fmt: hashlib.sha256((cache / f"preview.{fmt}").read_bytes()).hexdigest()
            for fmt in _MIME if (cache / f"preview.{fmt}").is_file()}


def _cache_state(cache: Path, fmt: str, repo_root: Path) -> tuple[dict | None, list[str]]:
    receipt_path = cache / "receipt.json"
    output = cache / f"preview.{fmt}"
    if not receipt_path.is_file() or not output.is_file():
        return None, ["cache output or receipt is absent"]
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, ["cache receipt is unreadable"]
    reasons: list[str] = []
    if receipt.get("schema_version") != "laplace.inline-figure-preview/2":
        reasons.append("cache receipt schema is obsolete")
    expected_outputs = receipt.get("output_sha256")
    if not isinstance(expected_outputs, dict) or fmt not in expected_outputs:
        reasons.append(f"cached {fmt} digest is absent")
        expected_outputs = expected_outputs if isinstance(expected_outputs, dict) else {}
    for output_format, expected_hash in expected_outputs.items():
        candidate = cache / f"preview.{output_format}"
        if output_format not in _MIME or not candidate.is_file():
            reasons.append(f"cached {output_format} output is absent")
        elif expected_hash != hashlib.sha256(candidate.read_bytes()).hexdigest():
            reasons.append(f"cached {output_format} digest changed")
    dependencies = receipt.get("input_digests")
    if not isinstance(dependencies, dict):
        reasons.append("compiler dependency record is absent")
        dependencies = {}
    for alias_name, recorded in dependencies.items():
        if not isinstance(alias_name, str) or not isinstance(recorded, dict):
            reasons.append("compiler dependency record is malformed")
            continue
        if "/laplace-figure-preview-" in alias_name:
            # Receipts written before generated-dir filtering may contain
            # compiler outputs from the temporary preview directory; they are
            # never manuscript dependencies.
            continue
        alias = _lexical(repo_root / alias_name)
        if _relative_lexical(alias, repo_root) != alias_name:
            reasons.append(f"dependency alias changed: {alias_name}")
            continue
        if not alias.exists():
            raise PreviewError(f"recorded figure dependency is missing: {alias_name}",
                               status=409, code="STALE_DEPENDENCY")
        try:
            resolved = alias.resolve(strict=True)
        except OSError as exc:
            raise PreviewError(f"recorded figure dependency is unavailable: {alias_name}",
                               status=409, code="STALE_DEPENDENCY") from exc
        if not _inside(resolved, repo_root):
            raise PreviewError(f"recorded figure dependency escapes the project: {alias_name}",
                               status=409, code="STALE_DEPENDENCY")
        current_resolved = resolved.relative_to(repo_root.resolve()).as_posix()
        current_hash = hashlib.sha256(resolved.read_bytes()).hexdigest()
        if recorded.get("resolved") != current_resolved:
            reasons.append(f"dependency target changed: {alias_name}")
        if recorded.get("sha256") != current_hash:
            reasons.append(f"dependency content changed: {alias_name}")
    return (receipt if not reasons else None), reasons


def preview(project: str, file: str, line_start: int, line_end: int,
            source_revision: str, fmt: str = "png", repo_root: Path | str | None = None,
            *, source_file_revision: str | None = None, environment: str = "figure") -> dict:
    from laplace.pipeline import registry
    root = Path(repo_root or registry._repo_root()).resolve()
    if fmt not in _MIME:
        raise PreviewError("format must be png or pdf", code="BAD_FORMAT")
    target, root_tex, selected = _selected(project, file, root)
    if not source_revision or source_revision != selected.get("revision"):
        raise PreviewError("selected manuscript revision changed; reload the document",
                           status=409, code="STALE_SOURCE")
    if source_file_revision and hashlib.sha256(target.read_bytes()).hexdigest() != source_file_revision:
        raise PreviewError("figure source file changed; reload the document",
                           status=409, code="STALE_SOURCE")
    figure = _span(target, line_start, line_end, environment)
    kind, snippet = _snippet(figure) if environment == "figure" else ("environment", figure)
    preamble, dependencies = _preamble(root_tex, root, kind)
    aux = root_tex.with_suffix(".aux")
    if environment != "figure" and aux.is_file() and _inside(aux, root):
        dependencies[aux.relative_to(root).as_posix()] = hashlib.sha256(aux.read_bytes()).hexdigest()
    digest = _key(project, target.relative_to(root), (line_start, line_end),
                  figure, preamble, dependencies)
    cache = root / ".laplace-cache" / "figure-preview" / digest
    output = cache / ("preview." + fmt)
    receipt_path = cache / "receipt.json"
    cached, _ = _cache_state(cache, fmt, root)
    if cached is not None:
        return {"status": "READY", "content_type": _MIME[fmt], "path": output,
                "receipt": cached, "reused": True}
    if not _SLOTS.acquire(timeout=1):
        raise PreviewError("inline figure preview capacity is busy", status=429, code="BUSY")
    _begin_render()
    try:
        with FileLock(str(cache) + ".lock", timeout=10):
            cached, rebuild_reasons = _cache_state(cache, fmt, root)
            if cached is not None:
                return {"status": "READY", "content_type": _MIME[fmt], "path": output,
                        "receipt": cached, "reused": True}
            with tempfile.TemporaryDirectory(prefix="laplace-figure-preview-") as temporary:
                work = Path(temporary)
                setup = ""
                if environment != "figure":
                    # preview crops the declared box while the original document class
                    # keeps its counters and preamble declarations faithful.
                    setup = ("\\usepackage[active,tightpage]{preview}\n"
                             f"\\PreviewEnvironment{{{environment}}}\n")
                aux_input = ""
                if environment != "figure" and aux.is_file():
                    aux_input = f"\\makeatletter\\@input{{{aux.name}}}\\makeatother\n"
                # LaTeX reads label definitions before the document body; replay the
                # selected root's aux at the same phase, not after \begin{document}.
                source = (preamble + "\n" + setup + aux_input + "\\pagestyle{empty}\n\\begin{document}\n"
                          + snippet + "\n\\end{document}\n")
                built = _compile(source, work, root_tex.parent)
                if fmt == "png" and built["png"] is None:
                    raise PreviewError("PNG conversion is unavailable", status=503,
                                       code="NO_PNG_CONVERTER")
                input_digests = _recorded_inputs(built["fls"], root_tex.parent, root, work)
                cache.mkdir(parents=True, exist_ok=True)
                for output_format in _MIME:
                    if built.get(output_format) is not None:
                        shutil.copy2(built[output_format], cache / f"preview.{output_format}")
                receipt = {"schema_version": "laplace.inline-figure-preview/2",
                           "project": project, "kind": kind, "environment": environment,
                           "file": target.relative_to(root).as_posix(),
                           "line_start": line_start, "line_end": line_end,
                           "source_revision": selected.get("revision"),
                           "source_sha256": hashlib.sha256(figure.encode()).hexdigest(),
                           "preamble_sha256": hashlib.sha256(preamble.encode()).hexdigest(),
                           "dependency_digests": dependencies,
                           "input_digests": input_digests,
                           "output_sha256": _output_hashes(cache),
                           "cache_key": digest, "compiler": built["compiler"],
                           "shell_escape": False,
                           "rebuild_reasons": rebuild_reasons}
                receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n",
                                        encoding="utf-8")
            return {"status": "READY", "content_type": _MIME[fmt], "path": output,
                    "receipt": receipt, "reused": False}
    finally:
        _end_render()
        _SLOTS.release()


def handle(path: str, query: dict, method: str, body: bytes = b"", repo_root=None):
    if path != _PATH:
        return None
    if method.upper() != "GET":
        return 405, "application/json", b'{"error":"GET only"}'
    try:
        result = preview(str(_q(query, "corpus")), str(_q(query, "file")),
                         int(_q(query, "line_start")), int(_q(query, "line_end")),
                         str(_q(query, "source_revision")), str(_q(query, "format", "png")),
                         repo_root=repo_root, source_file_revision=str(_q(query, 'source_file_revision')) or None,
                         environment=str(_q(query, "environment", "figure")))
        return 200, result["content_type"], result["path"].read_bytes()
    except (PreviewError, TypeError, ValueError) as exc:
        status = exc.status if isinstance(exc, PreviewError) else 422
        code = exc.code if isinstance(exc, PreviewError) else "BAD_REQUEST"
        return status, "application/json; charset=utf-8", json.dumps(
            {"error": str(exc), "status": code}, ensure_ascii=False).encode()
