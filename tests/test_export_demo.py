"""Tests for the PUBLIC, READ-ONLY tour bundle (his rulings 2026-07-23).

Builds against the REAL scanner into a temp dir, then pins the bundle law: no gate and
no visitor identity, no write path of any kind, the seal denylist holds over every
emitted byte, the SSG guard refuses SSG-family strings, the ESM module graph resolves
relative inside the bundle, and a rebuild at the same commit is byte-stable.

The bundle fixture needs the real engine server (export raises it on demand); these
tests are therefore integration tests of the actual bake, not of a stub.
"""
from __future__ import annotations

import json
import posixpath
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import export_demo as ed          # noqa: E402

STATIONS = ["conceptric.html", "conceptric-cockpit.html", "storyboard.html",
            "artefact.html", "lineage.html"]
# www.w3.org = XML namespace identifiers baked into vendored KaTeX/pdf.js/SVG — never a
# network request. NOTHING else external is allowed: the tour bundle has no outbox host.
_HOST_RX = re.compile(r"https?://[A-Za-z0-9.-]+")
_ALLOWED_HOSTS = {"http://www.w3.org", "https://www.w3.org"}
_ESM_IMPORT_RX = re.compile(r'''(?:from|import)\s*\(?\s*["']([^"']+\.mjs)["']''')


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp("demo")
    rep = ed.export(out)
    return out, rep


def _code_files(out: Path):
    """Bundle code/style/markup — data.json is data, judged by its own tests below."""
    for p in out.rglob("*"):
        if p.name == "data.json":
            continue
        if p.is_file() and p.suffix.lower() in (".html", ".js", ".css", ".mjs"):
            yield p


def _first_party_code(out: Path):
    for p in _code_files(out):
        rel = p.relative_to(out).as_posix()
        if not rel.startswith(("shared/katex/", "shared/pdfjs/", "shared/vendor/")):
            yield p


def test_bundle_shape(bundle):
    out, rep = bundle
    for rel in (["index.html", "data.json", "baked/paper_falqon.pdf",
                 "shared/hymn.css", "shared/shell.js"] + STATIONS):
        assert (out / rel).is_file(), f"missing {rel}"
    assert rep["meta"]["corpus"] == "paper_falqon"
    assert rep["meta"]["read_only"] is True
    assert (out / "baked" / "paper_falqon.pdf").read_bytes().startswith(b"%PDF")
    # the sealed-era artefacts are GONE: no gate, no encrypted blob
    assert not (out / "data.enc").exists()
    assert not (out / "app.html").exists()
    assert not (out / "projection.html").exists()


def test_no_gate_no_visitor_identity(bundle):
    out, _ = bundle
    index = (out / "index.html").read_text(encoding="utf-8")
    assert "passphrase" not in index.lower()
    assert 'type="password"' not in index
    for p in _first_party_code(out):
        t = p.read_text(errors="ignore")
        assert "__demo_visitor" not in t, f"visitor-identity handoff survived in {p.name}"
        assert "laplaceUnlock" not in t, f"the unlock gate survived in {p.name}"


def test_no_write_path(bundle):
    """The tour bundle carries NO minting affordance: no comment dock, no outbox, no
    github token slot, and the shim refuses every non-GET."""
    out, _ = bundle
    db_text = (out / "data.json").read_text(encoding="utf-8")
    assert "github_token" not in db_text
    for p in _first_party_code(out):
        t = p.read_text(errors="ignore")
        assert "api.github.com" not in t, f"an outbox host survived in {p.name}"
        assert "demo-dock" not in t and "demo-comment" not in t, \
            f"the comment dock survived in {p.name}"
    for name in STATIONS:
        t = (out / name).read_text(encoding="utf-8")
        assert "read-only slice" in t, f"{name}: the read-only refusal shim is missing"


def test_table_serves_the_stations(bundle):
    out, _ = bundle
    db = json.loads((out / "data.json").read_text(encoding="utf-8"))
    T = db["responses"]
    for key in ("/corpus/map?corpus=paper_falqon",
                "/storyboard/plan?corpus=paper_falqon",
                "/artefact/context?corpus=paper_falqon",
                "/corpus/list"):
        assert key in T, f"required baked read missing: {key}"
        assert T[key]["status"] == 200
    # the slice boundary: the corpus list names ONLY the subject
    assert T["/corpus/list"]["json"] == {"corpora": ["paper_falqon"], "default": "paper_falqon"}
    # the artefact context points its pdf at the baked file, not the live endpoint
    ctx = T["/artefact/context?corpus=paper_falqon"]["json"]
    assert ctx["pdf_endpoint"] == "baked/paper_falqon.pdf"


def test_tour_overlay_present(bundle):
    out, _ = bundle
    for name in STATIONS:
        t = (out / name).read_text(encoding="utf-8")
        assert "tour-bar" in t, f"{name}: tour overlay missing"
        assert "baked at commit" in t, f"{name}: bake provenance banner missing"
    index = (out / "index.html").read_text(encoding="utf-8")
    for name in ["conceptric.html", "storyboard.html", "artefact.html", "lineage.html"]:
        assert name in index, f"index.html does not link station {name}"


def test_seal_law_refuses_a_denylisted_string():
    with pytest.raises(ed.SealViolation):
        ed._seal_law_scan("probe", 'a record with by:"gerard" in it')
    with pytest.raises(ed.SealViolation):
        ed._seal_law_scan("probe", "a path into soul/transfer.md")
    with pytest.raises(ed.SealViolation):
        ed._seal_law_scan("probe", "leak someone@example.com here")
    ed._seal_law_scan("probe", "contact eigen@gmccaul.co.uk")       # must not raise
    ed._seal_law_scan("probe", "contact gerard.mccaul@gmail.com")   # published byline: allowed


def test_ssg_guard_refuses_ssg_family_strings():
    for poison in ("the SSG whitepaper", "a subset-sum instance", "subset sum",
                   "the ITQDE device", "itqde", "QMill"):
        with pytest.raises(ed.SSGViolation):
            ed._ssg_guard("probe", f"text carrying {poison} inside")
    # near-misses stay legal: 'subset' alone is ordinary technical vocabulary
    ed._ssg_guard("probe", "a subset of nodes in the graph")   # must not raise


def test_bundle_is_ssg_clean(bundle):
    out, _ = bundle
    for p in out.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".html", ".js", ".css", ".json", ".mjs", ".md"):
            ed._ssg_guard(str(p.relative_to(out)),
                          p.read_text(encoding="utf-8", errors="ignore"))


def test_bundle_is_denylist_clean(bundle):
    out, _ = bundle
    for p in out.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".html", ".js", ".css", ".json", ".mjs", ".md"):
            ed._seal_law_scan(str(p.relative_to(out)),
                              p.read_text(encoding="utf-8", errors="ignore"))


def test_no_author_literal_in_code(bundle):
    """The write-path law, kept absolute over CODE: no author-identity literal in any
    script or markup. data.json may carry HISTORICAL records attributed by:"gerard" —
    his real margin comments on the falqon manuscript are provenance exhibits, and the
    bundle has no minting path at all (test_no_write_path)."""
    out, _ = bundle
    for p in _first_party_code(out):
        t = p.read_text(errors="ignore")
        assert not re.search(r'''["']gerard["']''', t), f"author literal in {p.name}"


def test_no_external_hosts(bundle):
    out, _ = bundle
    hosts = set()
    for p in _first_party_code(out):
        for m in _HOST_RX.finditer(p.read_text(errors="ignore")):
            hosts.add(m.group(0))
    extra = hosts - _ALLOWED_HOSTS
    assert not extra, f"unexpected external host references: {sorted(extra)}"


def test_esm_module_graph_resolves_inside_bundle(bundle):
    out, _ = bundle
    scripts = sorted(out.rglob("*.mjs")) + [out / n for n in STATIONS]
    n_checked = 0
    for script in scripts:
        text = script.read_text(encoding="utf-8", errors="ignore")
        rel = script.parent.relative_to(out).as_posix()
        if rel.startswith(("shared/katex", "shared/pdfjs", "shared/vendor")):
            continue
        for spec in _ESM_IMPORT_RX.findall(text):
            n_checked += 1
            assert spec.startswith(("./", "../")), (
                f"{script.relative_to(out)}: import {spec!r} is not a valid relative "
                "ESM specifier")
            resolved = posixpath.normpath(posixpath.join(rel, spec))
            assert (out / resolved).is_file(), (
                f"{script.relative_to(out)}: import {spec!r} -> {resolved} not in bundle")
    assert n_checked >= 5, "expected the surfaces' module graphs to be walked"


def test_no_absolute_shared_esm_import_survives(bundle):
    out, _ = bundle
    for p in list(out.rglob("*.mjs")) + list(out.rglob("*.html")):
        rel = p.relative_to(out).as_posix()
        if rel.startswith(("shared/katex", "shared/pdfjs", "shared/vendor")):
            continue
        hits = ed._shared_mjs_imports(p.read_text(encoding="utf-8", errors="ignore"))
        assert not hits, f"{rel}: absolute /shared/ ESM import(s) survived: {hits}"


def test_email_redaction_holds(bundle):
    """No email but the public site address anywhere in first-party text (the crawl
    redacts collaborator emails out of baked tex; the seal scan re-checks)."""
    out, _ = bundle
    db_text = (out / "data.json").read_text(encoding="utf-8")
    for m in ed._EMAIL_RX.finditer(db_text):
        assert m.group(0).lower() in ed.PUBLIC_EMAILS, f"leaked email {m.group(0)!r}"


def test_rebuild_is_deterministic(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    ed.export(a)
    ed.export(b)
    assert (a / "data.json").read_bytes() == (b / "data.json").read_bytes()
    assert (a / "index.html").read_bytes() == (b / "index.html").read_bytes()
    for n in STATIONS:
        assert (a / n).read_bytes() == (b / n).read_bytes()
