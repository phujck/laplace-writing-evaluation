import json, shutil
from pathlib import Path
import pytest


def test_current_document_uses_canonical_build_and_labels_style_preview_separately(tmp_path,monkeypatch):
    from laplace.manuscript import document_style, projection_viewer, manuscript_source
    from test_manuscript_source import _project
    _project(tmp_path,{'document':{'root':'main.tex'}})
    md=tmp_path/'synthetics papers/book/manuscript'
    (md/'main.tex').write_text('\\documentclass{book}\n\\begin{document}\n\\input{chapter}\n\\end{document}')
    (md/'chapter.tex').write_text('\\chapter{One}\nIncluded prose.')
    calls=[]
    def build(file,**kwargs):
        calls.append(file)
        return {'state':'done','ok':True,'fresh':True,'running':False,'pdf':'fixture.pdf','finished':'fixed',
                'input_revisions':manuscript_source.observation('book',tmp_path)['file_revisions']}
    monkeypatch.setattr(projection_viewer,'recompile_status',build)
    current=document_style.current_status('book',tmp_path)
    assert current['status']=='READY' and current['style_preview']['status']=='NOT_BUILT'
    assert current['current_build']['fresh'] and calls==[current['selected_source']['root']]
    source=manuscript_source.resolve('book',repo_root=tmp_path)
    tree=manuscript_source.traversal(source['root'],tmp_path)
    thin=document_style.current_status('book',tmp_path,source=source,source_tree=tree,include_preview=False)
    assert thin['current_revision']==current['current_revision'] and 'style_preview' not in thin
    (md/'chapter.tex').write_text('New included prose.')
    changed=document_style.current_status('book',tmp_path,include_preview=False)
    assert changed['current_revision']!=thin['current_revision']
    monkeypatch.setattr(projection_viewer,'recompile_status',lambda *a,**k:{'state':'failed','ok':False,'fresh':False,'running':False})
    assert document_style.current_status('book',tmp_path)['status']=='FAILED'


def test_current_document_refuses_crossed_source_build_basis_and_keeps_real_output_identity(tmp_path,monkeypatch):
    from laplace.manuscript import document_style, projection_viewer, manuscript_source
    from test_manuscript_source import _project
    _project(tmp_path,{'document':{'root':'main.tex'}})
    md=tmp_path/'synthetics papers/book/manuscript'
    (md/'main.tex').write_text('\\documentclass{book}\n\\begin{document}\n\\input{chapter}\n\\end{document}')
    chapter=md/'chapter.tex';chapter.write_text('Original included prose.')
    source=manuscript_source.resolve('book',repo_root=tmp_path)
    old_tree=manuscript_source.traversal(source['root'],tmp_path)
    old_pins=manuscript_source.observation('book',tmp_path,source=source,source_tree=old_tree)['file_revisions']
    proof={'state':'done','ok':True,'fresh':True,'running':False,'pdf':'same.pdf','finished':'same',
           'input_revisions':old_pins,'outputs_current':True,'output_proof':'VERIFIED',
           'outputs':{'files':{'same.pdf':{'sha256':'a'*64}}}}
    monkeypatch.setattr(projection_viewer,'recompile_status',lambda *a,**k:proof)
    first=document_style.current_status('book',tmp_path,include_preview=False)
    assert first['status']=='READY'
    chapter.write_text('Changed included prose.')
    # Build's earlier fresh observation must not bless later source bytes.
    crossed=document_style.current_status('book',tmp_path,include_preview=False)
    assert crossed['status']!='READY' and crossed['observation_coherence']['status']=='CHANGED_DURING_READ'
    proof['input_revisions']=manuscript_source.observation('book',tmp_path)['file_revisions']
    # Conversely, a new build cannot bless the full reader's captured old body.
    old_body=document_style.current_status('book',tmp_path,source=source,source_tree=old_tree,include_preview=False)
    assert old_body['status']!='READY' and old_body['observation_coherence']['status']=='CHANGED_DURING_READ'
    current=document_style.current_status('book',tmp_path,include_preview=False)
    proof['outputs']={'files':{'same.pdf':{'sha256':'b'*64}}}
    changed_output=document_style.current_status('book',tmp_path,include_preview=False)
    assert changed_output['presentation_revision']!=current['presentation_revision']
    proof.pop('input_revisions')
    assert document_style.current_status('book',tmp_path,include_preview=False)['observation_coherence']['status']=='UNPROVED'
    assert document_style.current_status('book',tmp_path,include_preview=False)['status']!='READY'
    proof.update(state='error',ok=None)
    failed=document_style.current_status('book',tmp_path,include_preview=False)
    assert failed['status']=='FAILED' and failed['current_build']['state']=='error'
from laplace.manuscript import document_style
from laplace.manuscript import tex_dependencies
from laplace.web import project_work_surface
from laplace.native import contracts as writing_contracts, tools as writing_tools
import hashlib

@pytest.mark.skipif(not (shutil.which('latexmk') or shutil.which('pdflatex')),reason='TeX compiler unavailable')
def test_source_book_preview_preserves_authored_bytes(tmp_path):
 base=tmp_path/'synthetics papers'/'book'/'manuscript';base.mkdir(parents=True)
 (tmp_path/'profiles'/'typography').mkdir(parents=True)
 (tmp_path/'profiles'/'typography'/'article.json').write_text((Path(__file__).resolve().parents[1]/'profiles'/'typography'/'article.json').read_text())
 (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{'name':'book','tex_root':'synthetics papers/book/manuscript','manifest':{'document':{'root':'main.tex'}}}]}))
 main=base/'main.tex'; original='\\documentclass{article}\n\\begin{document}\nOriginal book prose.\\end{document}\n';main.write_text(original)
 out=document_style.preview('book',{'profile':'article','font_size':'11pt'},tmp_path,wait=True)
 assert main.read_text()==original
 assert json.loads((base/'document_style.json').read_text())['font_size']=='11pt'
 assert out['status']=='READY' and Path(out['pdf_path']).is_file()


def test_columns_resize_derived_visuals_without_erasing_explicit_overrides():
    initial=document_style._validate({'columns':'1','visual_overrides':{'font_size':10}})
    changed=document_style._validate({**initial,'columns':'2'})
    assert changed['visuals']['width_inches'] < initial['visuals']['width_inches']
    assert changed['visuals']['font_size']==10
    assert changed['visual_overrides']=={'font_size':10}
    explicit=document_style._validate({**changed,'visual_overrides':{'width_inches':4}})
    assert explicit['visuals']['width_inches']==4


def test_typography_only_save_preserves_existing_visual_overrides(tmp_path):
    base=tmp_path/'book/manuscript';base.mkdir(parents=True)
    (tmp_path/'registry_projects.json').write_text(json.dumps({'projects':[{
        'name':'book','project_dir':'book','tex_root':'book/manuscript',
        'manifest':{'document':{'root':'main.tex'}}}]}))
    (base/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nSubstantive fixture prose.\n\\end{document}\n')
    first=document_style.save('book',{'preset':'book','visual_overrides':{
        'font_size':9,'palette':['#112233','#445566']}},tmp_path)

    changed=document_style.save('book',{'preset':'article','columns':'2','margins':'20mm'},tmp_path)

    assert changed['preset']=='article' and changed['columns']=='2'
    assert changed['visual_overrides']==first['visual_overrides']
    assert changed['visuals']['font_size']==9
    assert changed['visuals']['palette']==['#112233','#445566']


def test_preview_tracks_original_bibliography_and_figure_not_unrelated_asset(tmp_path, monkeypatch):
    base = tmp_path / "synthetics papers" / "book" / "manuscript"
    base.mkdir(parents=True)
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "book", "tex_root": "synthetics papers/book/manuscript",
        "manifest": {"document": {"root": "main.tex"}},
    }]}), encoding="utf-8")
    main = base / "main.tex"
    original = ("\\documentclass{article}\n\\begin{document}\nOriginal prose. "
                "\\includegraphics{figure}\\bibliography{refs}\n\\end{document}\n")
    main.write_text(original, encoding="utf-8")
    bib = base / "refs.bib"; bib.write_text("@book{x,title={Original}}\n", encoding="utf-8")
    figure = base / "figure.png"; figure.write_bytes(b"original figure")
    unrelated = base / "unused.png"; unrelated.write_bytes(b"unused")

    class _Process:
        returncode = 0
        pid = 12345

        def __init__(self, args, cwd, **_kwargs):
            self.args, self.cwd = args, Path(cwd)

        def communicate(self, timeout=None):
            target = self.cwd / self.args[-1]
            target.with_suffix(".pdf").write_bytes(b"fixture pdf")
            target.with_suffix(".fls").write_text(
                "\n".join([f"INPUT {target}", f"INPUT {self.cwd / 'refs.bib'}",
                            f"INPUT {self.cwd / 'figure.png'}",
                            f"OUTPUT {target.with_suffix('.pdf')}"]) + "\n",
                encoding="utf-8")
            return b"fixture compile", None

    monkeypatch.setattr(document_style.shutil, "which", lambda name: "/fixture/latexmk")
    monkeypatch.setattr(document_style.subprocess, "Popen", _Process)
    built = document_style.preview("book", {"profile": "article", "font_size": "11pt"},
                                   tmp_path, wait=True)

    assert built["status"] == "READY"
    assert set(built["dependency_digests"]) == {
        "synthetics papers/book/manuscript/main.tex",
        "synthetics papers/book/manuscript/refs.bib",
        "synthetics papers/book/manuscript/figure.png",
    }
    assert built["dependency_digests"]["synthetics papers/book/manuscript/main.tex"] == hashlib.sha256(original.encode()).hexdigest()
    assert all(".laplace-cache" not in path for path in built["dependency_digests"])
    assert main.read_text(encoding="utf-8") == original

    unrelated.write_bytes(b"changed but not consumed")
    assert document_style.status("book", tmp_path)["status"] == "READY"
    bib.write_text("@book{x,title={Changed}}\n", encoding="utf-8")
    bib_stale = document_style.status("book", tmp_path)
    assert bib_stale["status"] == "STALE"
    assert bib_stale["dependency_changes"] == ["synthetics papers/book/manuscript/refs.bib"]
    bib.write_text("@book{x,title={Original}}\n", encoding="utf-8")
    figure.write_bytes(b"changed figure")
    figure_stale = document_style.status("book", tmp_path)
    assert figure_stale["status"] == "STALE"
    assert figure_stale["dependency_changes"] == ["synthetics papers/book/manuscript/figure.png"]


def test_preview_mirrors_external_bib_and_symlinked_graphic_inside_staging(tmp_path, monkeypatch):
    project = tmp_path / "project"
    base = project / "manuscript"
    tex_dir = base / "tex"; tex_dir.mkdir(parents=True)
    numerics = project / "numerics"; numerics.mkdir()
    references = project / "references"; references.mkdir()
    figure = numerics / "plot.pdf"; figure.write_bytes(b"original plot")
    bib = references / "shared.bib"; bib.write_text("@book{x,title={Shared}}\n")
    (base / "figures").symlink_to("../numerics", target_is_directory=True)
    main = tex_dir / "main.tex"
    original = ("\\documentclass{article}\n\\usepackage{graphicx}\n"
                "\\graphicspath{{../figures/}}\n\\begin{document}\n"
                "\\includegraphics{plot}\\bibliography{../../references/shared}\n"
                "\\end{document}\n")
    main.write_text(original)
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "book", "project_dir": "project", "tex_root": "project/manuscript/tex",
        "manifest": {"document": {"root": "project/manuscript/tex/main.tex"}},
    }]}))
    observed = {}

    class _Process:
        returncode = 0
        pid = 12346

        def __init__(self, args, cwd, **_kwargs):
            self.args, self.cwd = args, Path(cwd)

        def communicate(self, timeout=None):
            target = self.cwd / self.args[-1]
            staged_figure = (self.cwd / "../figures/plot.pdf").resolve()
            staged_bib = (self.cwd / "../../references/shared.bib").resolve()
            observed.update(figure=staged_figure, bib=staged_bib)
            assert ".laplace-cache" in str(staged_figure) and staged_figure.read_bytes() == b"original plot"
            assert ".laplace-cache" in str(staged_bib) and "Shared" in staged_bib.read_text()
            target.with_suffix(".pdf").write_bytes(b"fixture pdf")
            target.with_suffix(".fls").write_text(
                f"INPUT {target}\nINPUT {staged_figure}\nINPUT {staged_bib}\n"
                f"OUTPUT {target.with_suffix('.pdf')}\n")
            return b"fixture compile", None

    monkeypatch.setattr(document_style.shutil, "which", lambda name: "/fixture/latexmk")
    monkeypatch.setattr(document_style.subprocess, "Popen", _Process)
    built = document_style.preview("book", {"profile": "article"}, tmp_path, wait=True)

    assert built["status"] == "READY", built
    assert set(built["dependency_digests"]) == {
        "project/manuscript/tex/main.tex", "project/numerics/plot.pdf",
        "project/references/shared.bib",
    }
    assert observed["figure"] != figure.resolve() and observed["bib"] != bib.resolve()
    assert (base / "figures").is_symlink()
    assert main.read_text() == original and figure.read_bytes() == b"original plot"
    figure.write_bytes(b"changed plot")
    stale = document_style.status("book", tmp_path)
    assert stale["status"] == "STALE"
    assert stale["dependency_changes"] == ["project/numerics/plot.pdf"]


def test_style_preview_export_is_explicit_and_banks_durable_pdf_receipt_without_source_edits(tmp_path, monkeypatch):
    base = tmp_path / "book" / "manuscript"; base.mkdir(parents=True)
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "book", "project_dir": "book", "tex_root": "book/manuscript",
        "manifest": {"document": {"root": "main.tex"}},
    }]}))
    main = base / "main.tex"
    original = "\\documentclass{article}\n\\begin{document}\nExport fixture.\n\\end{document}\n"
    main.write_text(original)
    exports = base / "exports"; exports.mkdir(); (exports / "older.pdf").write_bytes(b"older")

    with pytest.raises(ValueError, match="current style preview"):
        document_style.export_pdf("book", tmp_path, mode="style-preview")

    class _Process:
        returncode = 0
        pid = 12347

        def __init__(self, args, cwd, **_kwargs):
            self.args, self.cwd = args, Path(cwd)

        def communicate(self, timeout=None):
            assert not (self.cwd / "exports").exists()
            target = self.cwd / self.args[-1]
            target.with_suffix(".pdf").write_bytes(b"%PDF-export-fixture")
            target.with_suffix(".fls").write_text(f"INPUT {target}\n")
            return b"fixture compile", None

    monkeypatch.setattr(document_style.shutil, "which", lambda name: "/fixture/latexmk")
    monkeypatch.setattr(document_style.subprocess, "Popen", _Process)
    built = document_style.preview("book", {"profile": "article"}, tmp_path, wait=True)
    assert built["status"] == "READY"

    exported = document_style.export_pdf("book", tmp_path, mode="style-preview")

    assert exported["mode"] == "style-preview"
    pdf_path, receipt_path = tmp_path / exported["file"], tmp_path / exported["receipt"]
    assert pdf_path.read_bytes() == b"%PDF-export-fixture"
    receipt = json.loads(receipt_path.read_text())
    assert receipt["status"] == "READY" and receipt["id"] == built["id"]
    assert receipt["exported_file"] == exported["file"]
    assert receipt["pdf_sha256"] == hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    assert exported["url"].startswith("/projection/pdf?")
    assert main.read_text() == original
    assert not list(exports.glob("*.pending"))
    journal = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]
    assert any(row.get("record") == "manuscript-export" and row.get("receipt") == exported["receipt"]
               for row in journal)

    preview_pdf = Path(built["pdf_path"])
    preview_pdf.write_bytes(b"tampered preview")
    with pytest.raises(ValueError, match="current style preview"):
        document_style.export_pdf("book", tmp_path, mode="style-preview")
    preview_pdf.write_bytes(b"%PDF-export-fixture")
    assert document_style.status("book", tmp_path)["status"] == "READY"

    main.write_text(original.replace("fixture", "changed fixture"))
    before = sorted(path.name for path in exports.iterdir())
    with pytest.raises(ValueError, match="current style preview"):
        document_style.export_pdf("book", tmp_path, mode="style-preview")
    assert sorted(path.name for path in exports.iterdir()) == before


def test_default_export_uses_only_fresh_pdf_for_exact_selected_edition(tmp_path, monkeypatch):
    base = tmp_path / "book/manuscript"; base.mkdir(parents=True)
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "book", "project_dir": "book", "tex_root": "book/manuscript",
        "manifest": {"document": {"root": "book/manuscript/main.tex", "edition": "draft"}},
    }]}))
    main = base / "main.tex"
    main.write_text("\\documentclass{article}\n\\begin{document}Current edition.\\end{document}\n")
    pdf = base / "main.pdf"; pdf.write_bytes(b"%PDF-current-selected-edition")
    other = base / "older.pdf"; other.write_bytes(b"%PDF-arbitrary-old-file")
    build = {"id": "recompile", "producer": "fixture latexmk", "state": "done",
        "ok": True, "fresh": True, "running": False,
        "pdf": "book/manuscript/main.pdf", "by": "author", "started": 10,
        "finished": 11, "built_ts": 11, "dependency_changes": [], "reason": None}
    monkeypatch.setattr("laplace.manuscript.projection_viewer.recompile_status",
                        lambda *_args, **_kwargs: dict(build))

    exported = document_style.export_pdf("book", tmp_path)

    assert exported["mode"] == "selected-source"
    assert exported["selected_source"]["root"] == "book/manuscript/main.tex"
    assert (tmp_path / exported["file"]).read_bytes() == pdf.read_bytes()
    receipt = json.loads((tmp_path / exported["receipt"]).read_text())
    assert receipt["mode"] == "selected-source"
    assert receipt["build"]["fresh"] is True and receipt["build"]["pdf"] == build["pdf"]
    assert receipt["selected_source"]["edition"] == "draft"
    journal = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]
    row = next(item for item in journal if item.get("record") == "manuscript-export")
    assert row["mode"] == "selected-source" and row["selected_source"]["root"] == receipt["selected_source"]["root"]

    build["fresh"] = False; build["reason"] = "compiled inputs changed"
    before = sorted((base / "exports").iterdir())
    with pytest.raises(ValueError, match="Build the current selected manuscript"):
        document_style.export_pdf("book", tmp_path)
    assert sorted((base / "exports").iterdir()) == before

    build.update(fresh=True, reason=None, pdf="book/manuscript/older.pdf")
    with pytest.raises(ValueError, match="Build the current selected manuscript"):
        document_style.export_pdf("book", tmp_path)


def test_public_export_adapters_forward_explicit_mode_and_document_the_default(tmp_path, monkeypatch):
    base = tmp_path / "book/manuscript"; base.mkdir(parents=True)
    (base / "main.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}")
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "book", "project_dir": "book", "tex_root": "book/manuscript",
        "manifest": {"document": {"root": "book/manuscript/main.tex"}},
    }]}))
    modes = []
    def exported(project, root, mode="selected-source"):
        modes.append(mode)
        return {"file": "book/manuscript/exports/current.pdf", "receipt": "receipt.json",
                "mode": mode, "pdf_sha256": "abc", "url": "/projection/pdf?file=current.pdf"}
    monkeypatch.setattr(document_style, "export_pdf", exported)

    native = writing_tools.execute(tmp_path, "book", "work", "export_pdf",
                                   {"mode": "style-preview"})
    code, _, raw = project_work_surface.handle("/work/style/export", {}, "POST",
        json.dumps({"project": "book", "mode": "selected-source"}).encode(), tmp_path)

    assert native["mode"] == "style-preview" and code == 201
    assert json.loads(raw)["mode"] == "selected-source"
    assert modes == ["style-preview", "selected-source"]
    contract = writing_contracts.CONTRACTS["export_pdf"]
    assert contract["input"]["properties"]["mode"]["enum"] == ["selected-source", "style-preview"]
    assert "by default" in contract["summary"]


@pytest.mark.skipif(not shutil.which("latexmk"), reason="latexmk unavailable")
def test_actual_imported_revtex_article_preview_preserves_class_and_compiles_isolated(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    original_root = repo / "synthetics papers/adaptive-normal-form/manuscript/tex/main.tex"
    dependencies = tex_dependencies.dependency_paths(original_root, repo)
    assert original_root in dependencies
    for source in dependencies:
        destination = tmp_path / source.relative_to(repo)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    relative_root = original_root.relative_to(repo).as_posix()
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "adaptive", "kind": "conceptric",
        "project_dir": "synthetics papers/adaptive-normal-form",
        "tex_root": "synthetics papers/adaptive-normal-form/manuscript/tex",
        "manifest": {"document": {"root": relative_root}},
    }]}))
    copied_root = tmp_path / relative_root
    source_before = {path.relative_to(tmp_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                     for path in (tmp_path / item.relative_to(repo) for item in dependencies)}

    built = document_style.preview("adaptive", {"preset": "article", "font_size": "11pt",
        "paper_size": "a4paper", "columns": "2", "margins": "25mm",
        "line_spacing": "1.15"}, tmp_path, wait=True)

    assert built["status"] == "READY", built.get("error")
    assert built["documentclass"]["original_class"] == "revtex4-2"
    assert built["documentclass"]["rendered_class"] == "revtex4-2"
    assert built["documentclass"]["class_preserved"] is True
    assert {"aps", "prx", "superscriptaddress", "reprint", "11pt", "a4paper"} <= set(
        built["documentclass"]["rendered_options"])
    staged_tex = Path(built["pdf_path"]).with_suffix(".tex").read_text(encoding="utf-8")
    assert "{revtex4-2}" in staged_tex
    assert "\\author{Gerard McCaul}" in staged_tex
    assert "\\affiliation{%" in staged_tex and "\\maketitle" in staged_tex
    assert "{article}" not in staged_tex.split("\\begin{document}", 1)[0]
    assert copied_root.read_bytes() == original_root.read_bytes()
    assert source_before == {
        path.relative_to(tmp_path).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (tmp_path / item.relative_to(repo) for item in dependencies)}


def test_compatible_class_family_preserves_memoir_and_cross_family_conversion_is_explicit():
    source = "\\documentclass[openright,10pt]{memoir}\n\\begin{document}x\\end{document}"
    book_style = document_style._validate({"preset": "book", "font_size": "12pt",
                                           "paper_size": "letterpaper", "columns": "1"})
    preserved, receipt = document_style._styled_documentclass(source, book_style)
    assert receipt["class_preserved"] is True and receipt["rendered_class"] == "memoir"
    assert "openright" in receipt["rendered_options"] and "12pt" in receipt["rendered_options"]
    assert "\\documentclass[" in preserved and "{memoir}" in preserved

    article_style = document_style._validate({"preset": "article"})
    converted, receipt = document_style._styled_documentclass(source, article_style)
    assert receipt["class_preserved"] is False and receipt["rendered_class"] == "article"
    assert "{article}" in converted and "openright" not in receipt["rendered_options"]
