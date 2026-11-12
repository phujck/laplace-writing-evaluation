"""Focused real-owner checks. All files are created beneath pytest's supplied fixture."""
import hashlib
import json
import shutil
from pathlib import Path

from laplace.manuscript import manuscript_source
from laplace.web import research_surface as rs, shared_ui


def project(root):
    p=root/"book"; m=p/"manuscript"; (m/"chapters").mkdir(parents=True)
    (p/"blueprint").mkdir()
    (root/"registry_projects.json").write_text(json.dumps({"projects":[{
        "name":"fixture","kind":"conceptric","project_dir":"book","tex_root":"book/manuscript",
        "manifest":{"document":{"root":"book/manuscript/main.tex","manuscript_dir":"book/manuscript"}}}]}))
    main=m/"main.tex"
    main.write_text("\\documentclass{book}\n\\begin{document}\n\\input{chapters/limits}\n\\end{document}\n")
    chapter=m/"chapters"/"limits.tex"
    chapter.write_text("\\section{Limits}\n\\href{../blueprint/argument-map.json}{Argument}\n")
    target=p/"blueprint"/"argument-map.json"; target.write_text('{"schema_version":"fixture/1","value":7}')
    (m/"main.pdf").write_bytes(b"%PDF fixture")
    return p,m,main,chapter,target


def call(root, **params):
    status,media,body=rs.handle("/research/artifact",{"project":["fixture"],**{k:[str(v)] for k,v in params.items()}},"GET",b"",repo_root=root)
    return status, json.loads(body) if media.startswith("application/json") else body


def test_nested_source_root_and_compiled_pdf_choose_same_declared_base(tmp_path):
    p,m,main,chapter,target=project(tmp_path)
    assert chapter.relative_to(tmp_path).as_posix() in manuscript_source.traversal(main,tmp_path)["files"]
    # An attractive but incorrect file must not affect resolution.
    (m/"blueprint").mkdir();(m/"blueprint"/target.name).write_text('{"wrong":true}')
    values=[]
    for source in (main,chapter):
        for identity in (str(source),source.relative_to(tmp_path).as_posix()):
            status,v=call(tmp_path,scope="project",path=identity,resolve="source-link",uri="../blueprint/argument-map.json#claim")
            assert status==200,v
            assert v["path"]=="blueprint/argument-map.json" and v["fragment"]=="claim"
            assert v["document_root"]=="manuscript/main.tex"
            values.append(v["path"])
        status,v=call(tmp_path,scope="project",path=source.relative_to(tmp_path),resolve="pdf-link",uri="../blueprint/argument-map.json")
        assert status==200,v
        values.append(v["path"])
    assert len(set(values))==1
    assert call(tmp_path,scope="project",path=target.relative_to(tmp_path),format="json")[1]["content"]==target.read_text()


def test_export_receipt_and_portable_aliases_keep_same_companion(tmp_path):
    p,m,main,chapter,target=project(tmp_path)
    exports=m/"exports";exports.mkdir();pdf=exports/"edition.pdf";pdf.write_bytes(b"%PDF retained")
    receipt={"project":"fixture","exported_file":str(pdf),
             "selected_source":{"root":str(main)},"pdf_sha256":hashlib.sha256(pdf.read_bytes()).hexdigest()}
    pdf.with_suffix(".json").write_text(json.dumps(receipt))
    status,v=call(tmp_path,scope="project",path=str(pdf),resolve="pdf-link",uri="../blueprint/argument-map.json")
    assert status==200 and v["basis"]=="verified-export-source"
    clone=tmp_path/"portable";clone.mkdir()
    shutil.copytree(p,clone/"book");shutil.copy2(tmp_path/"registry_projects.json",clone/"registry_projects.json")
    (clone/"writing-portability.json").write_text(json.dumps({"schema":"laplace.writing-portability/1",
        "directory_aliases":{str(tmp_path):"."},"source_aliases":{}}))
    for origin,kind in ((str(chapter),"source-link"),(str(pdf),"pdf-link")):
        status,moved=call(clone,scope="project",path=origin,resolve=kind,uri="../blueprint/argument-map.json")
        assert status==200,moved
        assert moved["path"]==v["path"]
    (clone/"book/manuscript/exports/edition.pdf").write_bytes(b"changed")
    assert call(clone,scope="project",path=str(pdf),resolve="pdf-link",uri="../blueprint/argument-map.json")[0]==422


def test_confinement_invalid_uri_missing_and_standalone_are_explicit(tmp_path):
    p,m,main,chapter,target=project(tmp_path)
    outside=tmp_path/"outside.json";outside.write_text("{}")
    (p/"blueprint"/"escape.json").symlink_to(outside)
    for uri in ("../../outside.json","%2e%2e/blueprint/argument-map.json",
                "%252e%252e/outside.json","file:///etc/passwd","//host/x","/etc/passwd",
                "..\\outside.json","../blueprint/argument-map.json?x=1","../blueprint/escape.json"):
        status,v=call(tmp_path,scope="project",path=str(chapter),resolve="source-link",uri=uri)
        assert status==422 and v["error"],uri
    status,v=call(tmp_path,scope="project",path=str(chapter),resolve="source-link",uri="../blueprint/missing.json")
    assert status==422 and "blueprint/missing.json" in v["error"] and "Restore" in v["error"]
    (p/"blueprint"/"unsupported.exe").write_bytes(b"no")
    assert call(tmp_path,scope="project",path=str(chapter),resolve="source-link",uri="../blueprint/unsupported.exe")[0]==422
    standalone=p/"appendix.tex";standalone.write_text("Standalone")
    (p/"local.md").write_text("Local")
    status,v=call(tmp_path,scope="project",path=str(standalone),resolve="source-link",uri="local.md")
    assert status==200 and v["basis"]=="current-source-directory"
    assert call(tmp_path,scope="project",path="../outside.json",format="json")[0]==404


def test_large_json_pages_and_download_never_silently_truncate(tmp_path):
    p,m,main,chapter,target=project(tmp_path)
    value={"schema_version":"writing-system-architecture.visual-index/1","text":"é😀"*24000}
    data=(json.dumps(value,ensure_ascii=False)+"\n").encode();target.write_bytes(data)
    assert len(data)>65536
    status,v=call(tmp_path,scope="project",path="blueprint/argument-map.json")
    assert status==413 and "next_read" in v and "download" in v
    text="";offset=0;sha=None
    while offset is not None:
        status,v=call(tmp_path,scope="project",path="blueprint/argument-map.json",format="json",offset=offset,limit=12000)
        assert status==200
        if sha is not None:assert v["sha256"]==sha
        sha=v["sha256"];text+=v["content"];offset=v["next_offset"]
    assert json.loads(text)==value
    assert call(tmp_path,scope="project",path="blueprint/argument-map.json",download=1)==(200,data)
    target.write_bytes(data+b" ")
    assert call(tmp_path,scope="project",path="blueprint/argument-map.json",format="json")[1]["sha256"]!=sha


def test_shared_assets_have_real_served_callers_and_documentation():
    root=Path(__file__).resolve().parents[1]
    for name in ("writing-artifact.mjs","writing-artifact.css"):
        status,media,data=shared_ui.handle("/shared/"+name,{})
        assert status==200 and data==(root/"src/laplace/web/static_shared"/name).read_bytes()
    assert shared_ui.handle("/shared/../writing-artifact.mjs",{})[0]==404
    shared=root/"src/laplace/web/static_shared"
    for name in ("workspace.mjs","writing-pdf.mjs","writing-evidence.mjs"):
        assert "/shared/writing-artifact.mjs" in (shared/name).read_text()
    from walk_source import walk_source
    assert "/shared/writing-artifact.mjs" in walk_source()   # the walk root and its owner modules
    scanner=(root/"src/laplace/web/scanner.py").read_text()
    assert '"research": research_surface' in scanner and "_su.handle(u.path" in scanner
    assert "scanner.serve(" in (root/"src/laplace/web/writing_server.py").read_text()
    exporter=(root/"scripts/export_writing_evaluation.py").read_text()
    assert "docs/writing-evaluator-readme.md" in exporter and "put('README.md', readme.read_bytes())" in exporter
    docs=(root/"docs/writing-evaluator-readme.md").read_text()
    assert "Foundations of Synthetics" in docs
    # The current release README's own links: every linked operational doc exists here and is exported,
    # its section anchor is a real heading, and the release facts are owned by the recorded files, not by names.
    import re
    exported=re.search(r"OPERATIONAL_INPUTS = \((.*?)\n\)",exporter,re.S).group(1)
    linked=sorted(set(re.findall(r"\]\((docs/[^)#]+\.md)(?:#([^)]+))?\)",docs)))
    assert len({path for path,_ in linked})>=7
    for path,anchor in linked:
        assert (root/path).is_file() and "'%s'"%path in exported, path
        if anchor:
            headings={re.sub(r"[^a-z0-9 -]","",line.lstrip("#").strip().lower()).replace(" ","-")
                      for line in (root/path).read_text().splitlines() if line.startswith("#")}
            assert anchor in headings, (path,anchor)
    for owned in ("container-package.json","release/export-manifest.json","release/acceptance.json"):
        assert "`%s`"%owned in docs
    assert "Edition names and local tags alone do not establish those facts." in docs


def test_media_and_download_pins_refuse_changed_bytes_and_preserve_exact_response(tmp_path, monkeypatch):
    p,m,main,chapter,target=project(tmp_path)
    for suffix,media in ((".pdf",b"%PDF recorded"),(".svg",b"<svg>recorded</svg>"),(".png",b"PNG recorded")):
        file=m/("pinned"+suffix);file.write_bytes(media);pin=hashlib.sha256(media).hexdigest()
        status,data=call(tmp_path,scope="manuscript",path=file.name,expected_sha256=pin)
        assert status==200 and data==media
        assert call(tmp_path,scope="manuscript",path=file.name,expected_sha256="sha256:"+pin,download=1)==(200,media)
        file.write_bytes(media+b" changed")
        status,error=call(tmp_path,scope="manuscript",path=file.name,expected_sha256=pin)
        assert status==409 and error["expected_sha256"]==pin
        assert error["actual_sha256"]==hashlib.sha256(file.read_bytes()).hexdigest()
        assert call(tmp_path,scope="manuscript",path=file.name,expected_sha256=pin,download=1)[0]==409
    assert call(tmp_path,scope="manuscript",path="pinned.pdf",expected_sha256="not-a-digest")[0]==422

    # NPZ metadata previews cannot claim an exact-byte pinned view, but their
    # original bytes remain available through the guarded download contract.
    archive=m/"data.npz";archive.write_bytes(b"bounded fixture bytes")
    pin=hashlib.sha256(archive.read_bytes()).hexdigest()
    native_read=Path.read_bytes
    def no_preview_read(path):
        assert path!=archive, "refused pinned NPZ preview must not materialise the archive"
        return native_read(path)
    with monkeypatch.context() as guard:
        guard.setattr(Path,"read_bytes",no_preview_read)
        status,error=call(tmp_path,scope="manuscript",path=archive.name,format="json",expected_sha256=pin)
        assert status==422 and "Pinned NPZ previews are unsupported" in error["error"]
    assert call(tmp_path,scope="manuscript",path=archive.name,download=1,expected_sha256=pin)==(200,archive.read_bytes())

    # Change the file immediately after the read used for verification. The
    # response must still contain those checked bytes, not a second path read.
    file=m/"once.svg";original=b"<svg>once</svg>";file.write_bytes(original)
    native=Path.read_bytes;reads=[]
    def changing_read(path):
        data=native(path)
        if path==file:
            reads.append(data)
            path.write_bytes(b"<svg>different</svg>")
        return data
    monkeypatch.setattr(Path,"read_bytes",changing_read)
    assert call(tmp_path,scope="manuscript",path=file.name,expected_sha256=hashlib.sha256(original).hexdigest())==(200,original)
    assert reads==[original]


def test_pinned_pdf_origin_cannot_resolve_companion_after_origin_changes(tmp_path):
    p,m,main,chapter,target=project(tmp_path)
    pdf=m/"main.pdf";pin=hashlib.sha256(pdf.read_bytes()).hexdigest()
    params=dict(scope="project",path=str(pdf),resolve="pdf-link",
                uri="../blueprint/argument-map.json",expected_sha256=pin)
    assert call(tmp_path,**params)[0]==200
    pdf.write_bytes(b"%PDF changed")
    assert call(tmp_path,**params)[0]==409


def test_pinned_text_download_checks_the_request_time_identity(tmp_path):
    p,m,main,chapter,target=project(tmp_path)
    pin=hashlib.sha256(target.read_bytes()).hexdigest()
    target.write_text('{"different":true}')
    assert call(tmp_path,scope="project",path="blueprint/argument-map.json",download=1,expected_sha256=pin)[0]==409
