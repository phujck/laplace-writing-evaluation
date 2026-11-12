from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import struct
import threading

import pytest

from laplace.manuscript import manuscript_figure_preview as preview
from laplace.manuscript import manuscript_source


SOURCE = Path("synthetics papers/corpus-as-a-state/manuscript/main.tex")
FIGURES = [(789, 848, "tikz"), (1080, 1097, "tikz"),
           (1236, 1257, "tikz"), (4664, 4705, "table")]


@pytest.mark.skipif(not shutil.which("pdflatex") or not shutil.which("pdftocairo"),
                    reason="local bounded TeX/PNG renderer unavailable")
def test_actual_synthetics_declared_tcolorbox_renders_with_selected_root_aux():
    root = Path("synthetics papers/synthetics-master-guide/manuscript")
    chapter = root / "chapters/what-a-theory-does.tex"
    before = hashlib.sha256(chapter.read_bytes()).hexdigest()
    revision = manuscript_source.resolve("synthetics-master-guide", repo_root=Path(".")).get("revision")
    lines = chapter.read_text(encoding="utf-8").splitlines()
    start = next(index + 1 for index, line in enumerate(lines) if "\\begin{operationalexample}" in line)
    end = next(index + 1 for index in range(start - 1, len(lines)) if "\\end{operationalexample}" in lines[index])
    result = preview.preview("synthetics-master-guide", str(chapter), start, end, revision,
                             repo_root=Path("."),
                             source_file_revision=hashlib.sha256(chapter.read_bytes()).hexdigest(),
                             environment="operationalexample")
    assert result["status"] == "READY" and result["receipt"]["kind"] == "environment"
    assert result["receipt"]["environment"] == "operationalexample"
    assert result["path"].read_bytes().startswith(b"\x89PNG")
    assert hashlib.sha256(chapter.read_bytes()).hexdigest() == before


@pytest.mark.skipif(not shutil.which("pdflatex") or not shutil.which("pdftocairo"),
                    reason="local bounded TeX/PNG renderer unavailable")
def test_generic_local_environment_uses_original_class_and_never_writes_source(tmp_path):
    manuscript = tmp_path / "generic" / "manuscript"
    manuscript.mkdir(parents=True)
    main = manuscript / "main.tex"
    main.write_text("\\documentclass{article}\n"
                    "\\newenvironment{remarkbox}{\\begin{quote}\\itshape}{\\end{quote}}\n"
                    "\\begin{document}\n\\begin{remarkbox}\n"
                    "Visible generic environment.\n\\end{remarkbox}\n\\end{document}\n",
                    encoding="utf-8")
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "generic", "project_dir": "generic", "tex_root": "generic/manuscript"}]}),
        encoding="utf-8")
    before = hashlib.sha256(main.read_bytes()).hexdigest()
    revision = manuscript_source.resolve("generic", repo_root=tmp_path)["revision"]

    result = preview.preview("generic", "generic/manuscript/main.tex", 4, 6, revision,
                             repo_root=tmp_path, source_file_revision=before,
                             environment="remarkbox")

    assert result["status"] == "READY" and result["receipt"]["environment"] == "remarkbox"
    assert result["path"].read_bytes().startswith(b"\x89PNG")
    assert hashlib.sha256(main.read_bytes()).hexdigest() == before


@pytest.mark.skipif(not shutil.which("pdflatex") or not shutil.which("pdftocairo"),
                    reason="local bounded TeX/PNG renderer unavailable")
def test_class_environment_without_local_declaration_compiles_or_reports_real_error(tmp_path):
    manuscript = tmp_path / "class-env" / "manuscript"
    manuscript.mkdir(parents=True)
    main = manuscript / "main.tex"
    main.write_text("\\documentclass{article}\n\\begin{document}\n"
                    "\\begin{minipage}{\\linewidth}\nVisible class environment.\n"
                    "\\end{minipage}\n\\end{document}\n", encoding="utf-8")
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "class-env", "project_dir": "class-env", "tex_root": "class-env/manuscript"}]}),
        encoding="utf-8")
    revision = manuscript_source.resolve("class-env", repo_root=tmp_path)["revision"]
    digest = hashlib.sha256(main.read_bytes()).hexdigest()

    result = preview.preview("class-env", "class-env/manuscript/main.tex", 3, 5, revision,
                             repo_root=tmp_path, source_file_revision=digest, environment="minipage")
    assert result["status"] == "READY" and result["receipt"]["environment"] == "minipage"

    main.write_text(main.read_text(encoding="utf-8").replace("minipage", "undefinedbox"), encoding="utf-8")
    changed_revision = manuscript_source.resolve("class-env", repo_root=tmp_path)["revision"]
    with pytest.raises(preview.PreviewError) as error:
        preview.preview("class-env", "class-env/manuscript/main.tex", 3, 5, changed_revision,
                        repo_root=tmp_path,
                        source_file_revision=hashlib.sha256(main.read_bytes()).hexdigest(),
                        environment="undefinedbox")
    assert error.value.code == "COMPILE_FAILED"


def _fixture(root: Path):
    manuscript = root / "corpus/manuscript"
    manuscript.mkdir(parents=True)
    manuscript.joinpath("main.tex").write_bytes(SOURCE.read_bytes())
    root.joinpath("registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "corpus", "project_dir": "corpus", "tex_root": "corpus/manuscript",
        "manifest": {"document": {"root": "corpus/manuscript/main.tex"}},
    }]}))
    return manuscript


@pytest.mark.skipif(not shutil.which("pdflatex") or not shutil.which("pdftocairo"),
                    reason="local bounded TeX/PNG renderer unavailable")
def test_actual_three_tikz_and_table_figures_render_read_only_and_reuse_cache(tmp_path):
    manuscript = _fixture(tmp_path)
    main = manuscript / "main.tex"
    before = hashlib.sha256(main.read_bytes()).hexdigest()
    revision = manuscript_source.resolve("corpus", repo_root=tmp_path)["revision"]

    for line_start, line_end, kind in FIGURES:
        result = preview.preview("corpus", "corpus/manuscript/main.tex",
                                 line_start, line_end, revision, "png", tmp_path)
        assert result["status"] == "READY" and result["path"].read_bytes().startswith(b"\x89PNG")
        assert result["receipt"]["kind"] == kind
        assert result["receipt"]["source_revision"] == revision
        assert result["receipt"]["shell_escape"] is False
        assert result["receipt"]["source_sha256"] == hashlib.sha256(
            "".join(main.read_text().splitlines(keepends=True)[line_start - 1:line_end]).encode()).hexdigest()
        assert result["receipt"]["output_sha256"]["png"] == hashlib.sha256(
            result["path"].read_bytes()).hexdigest()
        if kind == "table":
            width, height = struct.unpack(">II", result["path"].read_bytes()[16:24])
            assert width > height  # cropped table, not a portrait page with a blank tail
        reused = preview.preview("corpus", "corpus/manuscript/main.tex",
                                 line_start, line_end, revision, "png", tmp_path)
        assert reused["reused"] is True and reused["path"] == result["path"]

    assert hashlib.sha256(main.read_bytes()).hexdigest() == before
    assert not list(manuscript.glob("*.aux")) and not list(manuscript.glob("*.log"))
    assert len(list((tmp_path / ".laplace-cache/figure-preview").glob("*/receipt.json"))) == 4


@pytest.mark.skipif(not shutil.which("pdflatex") or not shutil.which("pdftocairo"),
                    reason="local bounded TeX/PNG renderer unavailable")
def test_preview_route_refuses_stale_revision_and_out_of_source_file(tmp_path, monkeypatch):
    manuscript = _fixture(tmp_path)
    revision = manuscript_source.resolve("corpus", repo_root=tmp_path)["revision"]
    query = {"corpus": ["corpus"], "file": ["corpus/manuscript/main.tex"],
             "line_start": ["789"], "line_end": ["848"],
             "source_revision": [revision], "format": ["png"]}

    status, content_type, body = preview.handle(
        "/walk/figure-preview", query, "GET", repo_root=tmp_path)
    assert status == 200 and content_type == "image/png" and body.startswith(b"\x89PNG")
    from laplace.manuscript import walk
    monkeypatch.setattr(walk, "_repo_root", lambda: tmp_path)
    status, content_type, body = walk.handle(
        "/walk/figure-preview", query, "GET", b"")
    assert status == 200 and content_type == "image/png" and body.startswith(b"\x89PNG")
    stale = {**query, "source_revision": ["stale"]}
    status, _, body = preview.handle(
        "/walk/figure-preview", stale, "GET", repo_root=tmp_path)
    assert status == 409 and json.loads(body)["status"] == "STALE_SOURCE"
    escaped = {**query, "file": ["../outside.tex"]}
    status, _, body = preview.handle(
        "/walk/figure-preview", escaped, "GET", repo_root=tmp_path)
    assert status == 422 and json.loads(body)["status"] == "UNSUPPORTED"

    # A source edit invalidates the walk revision before any cached bytes serve.
    main = manuscript / "main.tex"
    main.write_text(main.read_text() + "% changed\n")
    status, _, body = preview.handle(
        "/walk/figure-preview", query, "GET", repo_root=tmp_path)
    assert status == 409 and json.loads(body)["status"] == "STALE_SOURCE"


def test_preview_refuses_nonfigure_and_unsupported_figure_without_fake_output(tmp_path):
    manuscript = _fixture(tmp_path)
    main = manuscript / "main.tex"
    revision = manuscript_source.resolve("corpus", repo_root=tmp_path)["revision"]
    with pytest.raises(preview.PreviewError, match="not one complete figure"):
        preview.preview("corpus", "corpus/manuscript/main.tex", 1, 4,
                        revision, "png", tmp_path)

    unsupported = ("\\begin{figure}\n\\centering\n"
                   "\\includegraphics{external}\n\\end{figure}\n")
    original = main.read_text()
    with main.open("a") as stream:
        if not original.endswith("\n"):
            stream.write("\n")
        start = len(original.splitlines()) + 1
        stream.write(unsupported)
    fresh = manuscript_source.resolve("corpus", repo_root=tmp_path)["revision"]
    end = start + len(unsupported.splitlines()) - 1
    with pytest.raises(preview.PreviewError, match="no supported inline"):
        preview.preview("corpus", "corpus/manuscript/main.tex", start, end,
                        fresh, "png", tmp_path)


def test_composite_snippet_keeps_every_panel_and_removes_only_balanced_metadata():
    figure = r"""\begin{figure}[t]
\begin{tikzpicture}\node{first panel};\end{tikzpicture}
\caption[Short {nested}]{A caption with {nested material}}
\begin{tikzpicture}\node{second panel};\end{tikzpicture}
\begin{tabular}{cc} left & right \\ \end{tabular}
\label{fig:all-panels}
\end{figure}
"""
    assert preview.supports(figure) is True
    kind, snippet = preview._snippet(figure)
    assert kind == "composite"
    assert "first panel" in snippet and "second panel" in snippet
    assert "left & right" in snippet
    assert "caption" not in snippet and "fig:all-panels" not in snippet

    with pytest.raises(preview.PreviewError, match="unbalanced argument"):
        preview._snippet(figure.replace("{A caption with {nested material}}", "{broken"))


def _dependency_fixture(root: Path) -> tuple[Path, int, int]:
    manuscript = root / "corpus/manuscript"
    manuscript.mkdir(parents=True)
    source = r"""\documentclass{article}
\usepackage{tikz}
\begin{document}
Manuscript prose.
\begin{figure}
\centering
\begin{tikzpicture}
\node[draw]{\input{panel-text.tex}};
\end{tikzpicture}
\caption{External body input}
\label{fig:external}
\end{figure}
\end{document}
"""
    main = manuscript / "main.tex"
    main.write_text(source)
    manuscript.joinpath("panel-text.tex").write_text("First panel")
    root.joinpath("registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "corpus", "project_dir": "corpus", "tex_root": "corpus/manuscript",
        "manifest": {"document": {"root": "corpus/manuscript/main.tex"}},
    }]}))
    lines = source.splitlines()
    start = lines.index(r"\begin{figure}") + 1
    end = lines.index(r"\end{figure}") + 1
    return manuscript, start, end


@pytest.mark.skipif(not shutil.which("pdflatex") or not shutil.which("pdftocairo"),
                    reason="local bounded TeX/PNG renderer unavailable")
def test_recorded_body_input_and_output_digests_control_cache_reuse(tmp_path):
    manuscript, start, end = _dependency_fixture(tmp_path)
    revision = manuscript_source.resolve("corpus", repo_root=tmp_path)["revision"]
    first = preview.preview("corpus", "corpus/manuscript/main.tex", start, end,
                            revision, "png", tmp_path)
    alias = "corpus/manuscript/panel-text.tex"
    assert first["receipt"]["input_digests"][alias]["sha256"] == hashlib.sha256(
        b"First panel").hexdigest()

    # Body dependencies are outside the root source revision and the cache key.
    # The recorder receipt must still force a rebuild when they change.
    manuscript.joinpath("panel-text.tex").write_text("Second panel is different")
    changed = preview.preview("corpus", "corpus/manuscript/main.tex", start, end,
                              revision, "png", tmp_path)
    assert changed["reused"] is False
    assert any("dependency content changed" in reason
               for reason in changed["receipt"]["rebuild_reasons"])
    assert changed["receipt"]["input_digests"][alias]["sha256"] == hashlib.sha256(
        b"Second panel is different").hexdigest()

    # Tampered artifacts are never blessed by a valid-looking receipt.
    changed["path"].write_bytes(b"not the rendered PNG")
    repaired = preview.preview("corpus", "corpus/manuscript/main.tex", start, end,
                               revision, "png", tmp_path)
    assert repaired["reused"] is False and repaired["path"].read_bytes().startswith(b"\x89PNG")
    assert any("cached png digest changed" in reason
               for reason in repaired["receipt"]["rebuild_reasons"])

    manuscript.joinpath("panel-text.tex").unlink()
    with pytest.raises(preview.PreviewError, match="dependency is missing") as caught:
        preview.preview("corpus", "corpus/manuscript/main.tex", start, end,
                        revision, "png", tmp_path)
    assert caught.value.code == "STALE_DEPENDENCY"


def test_only_an_uncached_inline_render_counts_as_active(tmp_path, monkeypatch):
    manuscript, start, end = _dependency_fixture(tmp_path)
    revision = manuscript_source.resolve("corpus", repo_root=tmp_path)["revision"]
    entered, release = threading.Event(), threading.Event()

    def compiling(source, work, cwd):
        entered.set()
        assert release.wait(2)
        pdf, png, fls = work / "preview.pdf", work / "preview.png", work / "preview.fls"
        pdf.write_bytes(b"%PDF fixture")
        png.write_bytes(b"\x89PNG fixture")
        fls.write_text("")
        return {"pdf": pdf, "png": png, "fls": fls, "compiler": "fixture"}

    monkeypatch.setattr(preview, "_compile", compiling)
    result, failures = [], []

    def render():
        try:
            result.append(preview.preview("corpus", "corpus/manuscript/main.tex",
                                          start, end, revision, "png", tmp_path))
        except Exception as exc:  # surfaced in the test thread below
            failures.append(exc)

    thread = threading.Thread(target=render)
    thread.start()
    assert entered.wait(1)
    assert preview.active_renders() == 1
    release.set(); thread.join(2)
    assert not thread.is_alive() and not failures
    assert preview.active_renders() == 0 and result[0]["reused"] is False

    cached = preview.preview("corpus", "corpus/manuscript/main.tex",
                             start, end, revision, "png", tmp_path)
    assert cached["reused"] is True and preview.active_renders() == 0


def test_included_figure_file_revision_is_guarded_when_root_is_unchanged(tmp_path, monkeypatch):
    manuscript = tmp_path / 'p'; manuscript.mkdir()
    (manuscript/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\n\\input{figure}\n\\end{document}\n')
    child=manuscript/'figure.tex'
    child.write_text('\\begin{figure}\n\\begin{tikzpicture}\\draw(0,0)--(1,1);\\end{tikzpicture}\n\\end{figure}\n')
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'p','project_dir':'p','tex_root':'p','manifest':{'document':{'root':'p/main.tex'}}}]}))
    root_revision=manuscript_source.resolve('p',repo_root=tmp_path)['revision']
    file_revision=hashlib.sha256(child.read_bytes()).hexdigest()
    child.write_text(child.read_text().replace('(1,1)','(2,2)'))
    assert manuscript_source.resolve('p',repo_root=tmp_path)['revision']==root_revision
    monkeypatch.setattr(preview,'_compile',lambda *a,**k:pytest.fail('stale source must refuse before compiling'))
    status,_,body=preview.handle('/walk/figure-preview',{'corpus':['p'],'file':['p/figure.tex'],
        'line_start':['1'],'line_end':['3'],'source_revision':[root_revision],
        'source_file_revision':[file_revision]},'GET',repo_root=tmp_path)
    assert status==409 and json.loads(body)['status']=='STALE_SOURCE'
