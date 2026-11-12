import json
import sqlite3
import urllib.error
from pathlib import Path
import shutil
import subprocess

from laplace.research import references_surface as rs
from laplace.pipeline import authoring


KEY = "ABCDEFGH"


def _db(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.executescript("""
        CREATE TABLE items(itemID INTEGER PRIMARY KEY,itemTypeID INTEGER,key TEXT,version INTEGER,dateModified TEXT);
        CREATE TABLE itemTypes(itemTypeID INTEGER PRIMARY KEY,typeName TEXT);
        CREATE TABLE fields(fieldID INTEGER PRIMARY KEY,fieldName TEXT);
        CREATE TABLE itemData(itemID INTEGER,fieldID INTEGER,valueID INTEGER);
        CREATE TABLE itemDataValues(valueID INTEGER PRIMARY KEY,value TEXT);
        CREATE TABLE creators(creatorID INTEGER PRIMARY KEY,firstName TEXT,lastName TEXT);
        CREATE TABLE itemCreators(itemID INTEGER,creatorID INTEGER,orderIndex INTEGER);
        CREATE TABLE collections(collectionID INTEGER PRIMARY KEY,collectionName TEXT);
        CREATE TABLE collectionItems(collectionID INTEGER,itemID INTEGER);
        CREATE TABLE itemAttachments(itemID INTEGER,parentItemID INTEGER,contentType TEXT,path TEXT);
        """)
        con.execute("INSERT INTO itemTypes VALUES(1,'journalArticle')")
        con.execute("INSERT INTO items VALUES(1,1,?,3,'2026-09-26 10:00:00')", (KEY,))
        con.executemany("INSERT INTO fields VALUES(?,?)", [(1, "title"), (2, "date"), (3, "DOI")])
        con.executemany("INSERT INTO itemDataValues VALUES(?,?)", [(1, "A Typed Paper"), (2, "2024"), (3, "10.1/example")])
        con.executemany("INSERT INTO itemData VALUES(1,?,?)", [(1, 1), (2, 2), (3, 3)])
        con.execute("INSERT INTO creators VALUES(1,'Ada','Lovelace')")
        con.execute("INSERT INTO itemCreators VALUES(1,1,0)")
        con.execute("INSERT INTO collections VALUES(1,'Evidence')")
        con.execute("INSERT INTO collectionItems VALUES(1,1)")
        con.execute("INSERT INTO items VALUES(2,1,'ATTACH01',1,'2026-09-26 10:00:00')")
        con.execute("INSERT INTO itemAttachments VALUES(2,1,'application/pdf','storage:file.pdf')")


def _library(path: Path, monkeypatch) -> rs.Library:
    def unavailable(*args, **kwargs):
        raise urllib.error.URLError("not listening")
    monkeypatch.setattr(rs, "_api_get", unavailable)
    return rs.Library(path)


def _project(root: Path) -> Path:
    (root / "registry_projects.json").write_text(json.dumps({"projects": [{
        "name": "fixture", "kind": "conceptric", "project_dir": "fixture",
        "tex_root": "fixture/manuscript",
    }]}), encoding="utf-8")
    manuscript = root / "fixture" / "manuscript"; manuscript.mkdir(parents=True)
    (manuscript / "main.tex").write_text("\\bibliography{sources}\n", encoding="utf-8")
    (manuscript / "sources.bib").write_text("@article{existing,\n title={Existing}\n}\n", encoding="utf-8")
    return manuscript


def test_readonly_sqlite_search_and_item_return_metadata_not_attachment_bodies(tmp_path, monkeypatch):
    db = tmp_path / "zotero.sqlite"; _db(db); library = _library(db, monkeypatch)
    provider, items = library.search("Typed")
    assert provider == "sqlite" and [item["key"] for item in items] == [KEY]
    provider, item = library.item(KEY)
    assert provider == "sqlite" and item["collections"] == ["Evidence"]
    assert item["attachments"] == [{"key": "ATTACH01", "content_type": "application/pdf", "path": "storage:file.pdf"}]
    assert "body" not in item and item["citation_key"] == "zotero_abcdefgh"
    assert library.status()["item_count"] == 2


def test_api_is_preferred_over_sqlite(tmp_path, monkeypatch):
    db = tmp_path / "zotero.sqlite"; _db(db)
    monkeypatch.setattr(rs, "_api_get", lambda path, params=None: [{"data": {
        "key": KEY, "version": 9, "dateModified": "2026-01-01", "itemType": "book",
        "title": "API item", "creators": [{"firstName": "Grace", "lastName": "Hopper"}],
    }}])
    provider, items = rs.Library(db).search("ignored")
    assert provider == "api" and items[0]["title"] == "API item"


def test_attach_preserves_existing_bib_and_refresh_marks_source_revision_stale(tmp_path, monkeypatch):
    db = tmp_path / "zotero.sqlite"; _db(db); library = _library(db, monkeypatch)
    manuscript = _project(tmp_path)
    status, out = rs.attach("fixture", {"key": KEY, "claim_id": "claim:one", "note": "author note"}, tmp_path, library)
    assert status == 201 and out["bib_path"] == "sources.bib"
    bib = (manuscript / "sources.bib").read_text(encoding="utf-8")
    assert "@article{existing" in bib and "@article{zotero_abcdefgh" in bib
    records = json.loads((manuscript / "references.json").read_text(encoding="utf-8"))["associations"]
    assert records[0]["note"] == "author note" and records[0]["state"] == "CURRENT"
    status, duplicate = rs.attach("fixture", {"key": KEY, "claim_id": "claim:one"}, tmp_path, library)
    assert status == 409 and "already" in duplicate["error"]
    with sqlite3.connect(db) as con: con.execute("UPDATE items SET version=4 WHERE key=?", (KEY,))
    status, refreshed = rs.refresh("fixture", tmp_path, library)
    assert status == 200 and refreshed["stale"] == [KEY]
    updated = json.loads((manuscript / "references.json").read_text(encoding="utf-8"))["associations"][0]
    assert updated["state"] == "STALE" and updated["note"] == "author note"


def test_attach_rejects_bib_collision_without_clobbering_user_entry(tmp_path, monkeypatch):
    db = tmp_path / "zotero.sqlite"; _db(db); library = _library(db, monkeypatch); manuscript = _project(tmp_path)
    before = (manuscript / "sources.bib").read_text(encoding="utf-8")
    status, out = rs.attach("fixture", {"key": KEY, "citekey": "existing"}, tmp_path, library)
    assert status == 409 and "collision" in out["error"]
    assert (manuscript / "sources.bib").read_text(encoding="utf-8") == before


def test_http_attached_uses_explicit_fixture_root(tmp_path, monkeypatch):
    db = tmp_path / "zotero.sqlite"; _db(db); library = _library(db, monkeypatch)
    manuscript = _project(tmp_path)
    monkeypatch.setattr(rs, "Library", lambda: library)
    payload = {"project": "fixture", "key": KEY, "claim_id": "claim:http", "note": "HTTP note"}

    status, _, _ = rs.handle("/references/attach", {}, "POST", json.dumps(payload).encode(),
                             repo_root=tmp_path)
    got_status, _, body = rs.handle("/references/attached", {"project": ["fixture"]},
                                    "GET", b"", repo_root=tmp_path)

    assert status == 201 and got_status == 200
    attached = json.loads(body)
    assert attached["project"] == "fixture"
    assert attached["associations"][0]["metadata"]["title"] == "A Typed Paper"
    assert attached["associations"][0]["note"] == "HTTP note"
    assert (manuscript / "references.json").is_file()


def test_same_item_identity_is_bounded_to_matching_bibtex_entry(tmp_path, monkeypatch):
    db = tmp_path / "zotero.sqlite"; _db(db); library = _library(db, monkeypatch)
    manuscript = _project(tmp_path)
    bib = manuscript / "sources.bib"
    bib.write_text(
        "@article{claimed,\n  title={Different item},\n  zotero_key={OTHERKEY},\n}\n"
        f"@article{{elsewhere,\n  title={{Right identity elsewhere}},\n  zotero_key={{{KEY}}},\n}}\n",
        encoding="utf-8")
    before = bib.read_bytes()

    status, result = rs.attach("fixture", {"key": KEY, "citekey": "claimed"},
                               tmp_path, library)

    assert status == 409 and "collision" in result["error"]
    assert bib.read_bytes() == before


class _SpecialLibrary:
    def item(self, key):
        return "fixture", {"key": key, "version": "1", "modified": "now",
            "item_type": "journalArticle", "citation_key": "safe_special",
            "title": r"A & 50%_# $cost {draft} \\ path", "creators": ["A & B_#"],
            "year": "2026", "doi": "10.1/a_b%2", "url": "https://example.test/a_b?x=1&y=2"}


class _MutableLibrary:
    def __init__(self):
        self.current = {
            "key": KEY, "version": "1", "modified": "2026-09-25",
            "item_type": "journalArticle", "citation_key": "stable_key",
            "title": "Original title", "creators": ["Ada Lovelace"],
            "year": "2024", "doi": "10.1/example", "url": "https://old.example",
            "publication_title": "Old Journal", "volume": "1", "issue": "2",
            "pages": "1--9", "publisher": "Old Press",
        }

    def item(self, key):
        return "fixture", dict(self.current) if key == KEY else None


def test_attached_user_metadata_is_tex_escaped_and_compiles(tmp_path):
    manuscript = _project(tmp_path)
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n\\cite{safe_special}\n"
        "\\bibliographystyle{plain}\n\\bibliography{sources}\n\\end{document}\n", encoding="utf-8")
    status, result = rs.attach("fixture", {"key": KEY}, tmp_path, _SpecialLibrary())
    assert status == 201, result
    bib = (manuscript / "sources.bib").read_text(encoding="utf-8")
    for escaped in (r"\&", r"\%", r"\_", r"\#", r"\$", r"\{", r"\}", r"\textbackslash{}"):
        assert escaped in bib
    if shutil.which("pdflatex") and shutil.which("bibtex"):
        first = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
                               cwd=manuscript, capture_output=True, timeout=30)
        bibliography = subprocess.run(["bibtex", "main"], cwd=manuscript,
                                      capture_output=True, timeout=30)
        final = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "main.tex"],
                               cwd=manuscript, capture_output=True, timeout=30)
        assert first.returncode == bibliography.returncode == final.returncode == 0


def test_local_pdf_text_extraction_has_bounded_offset_pagination(tmp_path, monkeypatch):
    db = tmp_path / "zotero.sqlite"; _db(db); library = _library(db, monkeypatch)
    pdf = tmp_path / "storage" / "ATTACH01" / "file.pdf"
    pdf.parent.mkdir(parents=True); pdf.write_bytes(b"%PDF-fixture")
    text = "A" * 900 + "\f" + "B" * 900 + "\f" + "C" * 900
    class _Run:
        returncode = 0; stdout = text; stderr = ""
    monkeypatch.setattr(rs.shutil, "which", lambda name: "/fixture/pdftotext")
    monkeypatch.setattr(rs.subprocess, "run", lambda *args, **kwargs: _Run())

    first = rs.extract_text(KEY, library, limit=1000, offset=0)
    second = rs.extract_text(KEY, library, limit=1000, offset=first["next_offset"])

    assert first["source_state"] == "extracted" and first["truncated"] is True
    assert first["next_offset"] == 1000 and second["offset"] == 1000
    assert first["page_start"] == 1 and first["page_end"] == 2
    assert second["page_start"] == 2 and second["page_end"] == 3
    assert first["attachment"]["sha256"].startswith("sha256:")


def test_update_replaces_only_its_entries_and_invalidates_old_authoring_context(tmp_path, monkeypatch):
    manuscript = _project(tmp_path)
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "The source is cited here \\cite{stable_key}.\n"
        "\\bibliographystyle{plain}\n\\bibliography{sources}\n\\end{document}\n",
        encoding="utf-8")
    unrelated = "@article{unrelated,\n  title={Keep these exact bytes & punctuation},\n}\n"
    (manuscript / "sources.bib").write_text(unrelated, encoding="utf-8")
    library = _MutableLibrary()
    first_status, first = rs.attach(
        "fixture", {"key": KEY, "citekey": "stable_key", "claim_id": "claim:one",
                    "note": "Keep this authored note"}, tmp_path, library)
    second_status, _ = rs.attach(
        "fixture", {"key": KEY, "citekey": "stable_key", "claim_id": "claim:two",
                    "note": "Keep the second note"}, tmp_path, library)
    assert first_status == second_status == 201, first
    attached_bib = (manuscript / "sources.bib").read_text(encoding="utf-8")
    stable_entry = next(entry["text"] for entry in rs._bib_entries(attached_bib)
                        if entry["key"] == "stable_key")
    preserved_tail = "% human divider stays exactly here\n" + unrelated
    (manuscript / "sources.bib").write_text(stable_entry + "\n" + preserved_tail,
                                             encoding="utf-8")
    old_context = authoring.build_context("fixture", {"files": ["main.tex"]}, repo_root=tmp_path)
    assert old_context["consumed"]["references"][0]["metadata"]["title"] == "Original title"

    library.current.update({
        "version": "2", "modified": "2026-09-26", "title": "Corrected title",
        "publication_title": "New Journal", "volume": "3", "issue": "4",
        "pages": "10--20", "publisher": "New Press", "url": "https://new.example",
    })
    refresh_status, refreshed = rs.refresh("fixture", tmp_path, library)
    assert refresh_status == 200 and refreshed["stale"] == [KEY, KEY]
    monkeypatch.setattr(rs, "Library", lambda: library)
    http_status, _, update_body = rs.handle(
        "/references/update", {}, "POST",
        json.dumps({"project": "fixture", "key": KEY}).encode(), repo_root=tmp_path)
    update_result = json.loads(update_body)
    assert http_status == 200 and update_result["updated"] == 2

    bib = (manuscript / "sources.bib").read_text(encoding="utf-8")
    assert bib[bib.index("% human divider"):] == preserved_tail
    assert bib.count("@article{unrelated") == bib.count("@article{stable_key") == 1
    assert "title = {Corrected title}" in bib and "journal = {New Journal}" in bib
    assert "title = {Original title}" not in bib
    rows = json.loads((manuscript / "references.json").read_text(encoding="utf-8"))["associations"]
    assert [row["note"] for row in rows] == ["Keep this authored note", "Keep the second note"]
    assert {row["citekey"] for row in rows} == {"stable_key"}
    assert {row["bib_path"] for row in rows} == {"fixture/manuscript/sources.bib"}
    assert {row["state"] for row in rows} == {"CURRENT"}
    assert {row["metadata"]["title"] for row in rows} == {"Corrected title"}
    assert all("refresh" not in row for row in rows)

    stale = authoring.inspect("fixture", repo_root=tmp_path)["stale"]
    old = next(row for row in stale if row["context_id"] == old_context["context_id"])
    assert "reference-association-changed" in old["reasons"]
    new_context = authoring.build_context("fixture", {"files": ["main.tex"]}, repo_root=tmp_path)
    assert {row["metadata"]["title"] for row in new_context["consumed"]["references"]} == {"Corrected title"}
    assert "Corrected title" in new_context["prompt"]
    talk = [json.loads(line) for line in (tmp_path / "contract" / "talk.jsonl").read_text().splitlines()]
    update_record = next(row for row in talk if row.get("record") == "reference-update")
    assert update_record["before"]["associations"][0]["metadata"]["title"] == "Original title"
    assert update_record["after"]["associations"][0]["metadata"]["title"] == "Corrected title"


def test_attach_reuses_entry_without_zotero_key_only_on_exact_doi(tmp_path):
    manuscript = _project(tmp_path)
    bib = manuscript / "sources.bib"
    existing = "@article{stable_key,\n  title={Hand maintained},\n  doi={10.1/example},\n}\n"
    bib.write_text(existing, encoding="utf-8")
    library = _MutableLibrary()

    status, result = rs.attach("fixture", {"key": KEY, "citekey": "stable_key",
                                            "note": "Association only"}, tmp_path, library)

    assert status == 201, result
    assert bib.read_text(encoding="utf-8") == existing
    row = json.loads((manuscript / "references.json").read_text())["associations"][0]
    assert row["citekey"] == "stable_key" and row["note"] == "Association only"


def test_update_refuses_association_from_a_different_selected_bibliography(tmp_path):
    manuscript = _project(tmp_path)
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}Text.\n"
        "\\bibliography{sources}\n\\end{document}\n", encoding="utf-8")
    library = _MutableLibrary()
    assert rs.attach("fixture", {"key": KEY, "citekey": "stable_key"},
                     tmp_path, library)[0] == 201
    association_path = manuscript / "references.json"
    state = json.loads(association_path.read_text())
    state["associations"][0]["bib_path"] = "fixture/manuscript/another.bib"
    association_path.write_text(json.dumps(state), encoding="utf-8")
    before = (manuscript / "sources.bib").read_bytes()

    status, result = rs.update("fixture", {"key": KEY}, tmp_path, library)

    assert status == 409 and "different selected bibliography" in result["error"]
    assert (manuscript / "sources.bib").read_bytes() == before


def test_update_rolls_back_bibliography_if_association_commit_fails(tmp_path, monkeypatch):
    manuscript = _project(tmp_path)
    (manuscript / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}Text \\cite{stable_key}.\n"
        "\\bibliography{sources}\n\\end{document}\n", encoding="utf-8")
    library = _MutableLibrary()
    assert rs.attach("fixture", {"key": KEY, "citekey": "stable_key"},
                     tmp_path, library)[0] == 201
    before_bib = (manuscript / "sources.bib").read_bytes()
    before_associations = (manuscript / "references.json").read_bytes()
    library.current.update({"version": "2", "modified": "later", "title": "Changed"})
    original_replace = Path.replace

    def fail_association_replace(path, target):
        if str(path).endswith("references.json.update.pending"):
            raise OSError("fixture association rename failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_association_replace)
    from laplace.manuscript.source_effects import SourceEffectFailure
    try:
        rs.update("fixture", {"key": KEY}, tmp_path, library)
    except SourceEffectFailure as exc:
        assert "fixture association" in str(exc)
        assert exc.details['source_effect']['state'] == 'ROLLED_BACK'
        assert exc.details['source_effect']['complete'] is False
    else:
        raise AssertionError("the simulated failed association commit was swallowed")
    assert (manuscript / "sources.bib").read_bytes() == before_bib
    assert (manuscript / "references.json").read_bytes() == before_associations
