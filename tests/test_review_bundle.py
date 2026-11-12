"""The remote-review bundle (ported onto the artefact surface, WO-20260717 exporter-port):
pin the password gate + seal round-trip, the artefact-surface template + its self-contained
ESM module graph, the ledger ingest (device-minted id/ts preserved), and the inbox drain.
The full DATA bake needs the LaTeX toolchain + a browser to render, and is exercised live
(a real run against a manuscript root); the template/graph proofs here need neither."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))


def test_seal_roundtrip_and_wrong_password():
    from laplace.web import site_seal
    plain = json.dumps({"pages": ["x"], "secret": "res:window-verdict"}).encode()
    blob = site_seal.encrypt(plain, "the-passphrase")
    assert blob[:6] == b"LREV1\0", "magic header present"
    assert b"res:window-verdict" not in blob, "plaintext must not survive in the blob"
    assert site_seal.decrypt(blob, "the-passphrase") == plain
    for bad in ("wrong", "", "The-Passphrase"):
        try:
            site_seal.decrypt(blob, bad)
            raise AssertionError("wrong passphrase must not decrypt")
        except Exception as e:
            assert "review bundle" not in str(e)  # got past magic, failed at AES
    # a non-bundle blob is rejected at the magic before any key work
    try:
        site_seal.decrypt(b"not-a-bundle-at-all", "x")
        raise AssertionError("must reject non-bundle")
    except ValueError:
        pass


def test_unlock_js_matches_iter():
    from laplace.web import site_seal
    assert str(site_seal.PBKDF2_ITER) in site_seal.UNLOCK_JS
    assert "AES-GCM" in site_seal.UNLOCK_JS


def test_app_html_bakes_the_artefact_surface():
    """The PORT (WO-20260717 exporter-port): the bundle's app.html is the REAL artefact
    surface (artefact.html + artefact-panes.mjs over store.mjs) — not the retired bespoke
    review_static.html. Proves the WORKING template, not a grep of the old one: the artefact
    chrome is present, the prepended fetch shim installs, and the inline module import is
    rewritten relative so the bundle resolves offline (zero surviving absolute /shared/ imports)."""
    import re
    import export_review as er
    app = er.build_app_html()
    # the artefact chrome the panes drive (the reader, the standing rail, the findings tray, the editor).
    # UPDATED TO CURRENT TRUTH (W-TRIAGE 2026-07-22): the editor chrome was restructured — the bare
    # "editing" literal and #art-edit-toggle are gone; the live editor is the synctex tex-source pane
    # (id="art-source-pane") with save->recompile (id="art-edit-save"). Assert the current editor marker.
    for marker in ('id="art-reader"', 'id="art-rail"', 'id="art-tray-sec"', 'id="art-source-pane"'):
        assert marker in app, f"artefact chrome missing: {marker}"
    # the surface boots through the shared module, rewritten document-relative.
    assert 'from "./shared/artefact-panes.mjs"' in app, "inline module import not rewritten relative"
    assert "initArtefact" in app
    # the prepended shim: hydrate from the gate + override fetch (no engine, no CDN).
    assert "__REVIEW SHIM__" in app and '__review_payload' in app
    assert "window.fetch=function" in app.replace(" ", ""), "the fetch override is not installed"
    # SELF-CONTAINED: not one absolute /shared/…mjs import may survive in the baked page
    # (it would resolve to the SITE root, not the bundle) — the mechanical offline proof.
    assert not re.search(r'(?:from|import)\s*\(?\s*["\']/shared/[^"\']+\.mjs', app), \
        "a surviving absolute /shared/ import breaks the offline bundle"


def test_gate_decrypts_to_the_app():
    """The gate (index.html) is the password door: laplaceUnlock over the SAME site_seal
    UNLOCK_JS, fetch of data.enc, and the sessionStorage handoff to app.html."""
    import export_review as er
    idx = er.build_index_html()
    assert "laplaceUnlock" in idx
    assert 'fetch("data.enc")' in idx
    assert "__review_payload" in idx and 'location.href="app.html"' in idx
    assert str(__import__("laplace.web.site_seal", fromlist=["PBKDF2_ITER"]).PBKDF2_ITER) in idx


def test_copy_shared_rewrites_the_module_graph(tmp_path):
    """The bundle's shared/ layer is self-contained: the ESM module graph is copied with every
    import specifier rewritten relative, the pdf.js worker string is repointed under the bundle,
    and the verbatim vendored dirs (pdfjs/vendor/katex) ship whole — so the reader, editor and
    shell all resolve with no network."""
    import re
    import export_review as er
    copied = er._copy_shared(tmp_path)
    shared = tmp_path / "shared"
    assert "store.mjs" in copied and "artefact-panes.mjs" in copied
    # the rewritten top-level graph carries NO absolute /shared/ import.
    for name in ("store.mjs", "artefact-panes.mjs"):
        txt = (shared / name).read_text(encoding="utf-8")
        assert not re.search(r'(?:from|import)\s*\(?\s*["\']/shared/[^"\']+\.mjs', txt), \
            f"{name} still carries an absolute /shared/ import"
    panes = (shared / "artefact-panes.mjs").read_text(encoding="utf-8")
    assert 'from "./store.mjs"' in panes, "the store import was not rewritten relative"
    assert '"shared/pdfjs/pdf.worker.min.mjs"' in panes, "the pdf.js worker src was not repointed"
    # the verbatim assets the surface loads off disk (never through the fetch shim).
    assert (shared / "hymn.css").is_file() and (shared / "shell.js").is_file()
    assert (shared / "pdfjs" / "pdf.worker.min.mjs").is_file()
    assert (shared / "vendor" / "codemirror" / "codemirror.bundle.mjs").is_file()


def test_feedback_ingest_preserves_id_and_dedups(tmp_path):
    from laplace.manuscript import manuscript_bridge as mb
    ledger = tmp_path / "feedback.jsonl"
    rec = {"id": "FB-20260703-101112-window-verdict-ab12", "ts": "2026-07-03T10:11:12",
           "node_id": "res:window-verdict", "kind": "imprecise",
           "comment": "this bound feels off", "by": "gerard",
           "anchor": {"page": 4, "section": "S6"}}
    out = mb.feedback_ingest(REPO, "demo", rec, ledger=ledger)
    assert out["ok"] and out["id"] == rec["id"]
    stored = json.loads(ledger.read_text(encoding="utf-8").strip())
    assert stored["id"] == rec["id"] and stored["ts"] == rec["ts"], "device id/ts preserved"
    assert stored["status"] == "open"
    # idempotent: re-ingesting the same id is a skip, not a duplicate
    again = mb.feedback_ingest(REPO, "demo", rec, ledger=ledger)
    assert again.get("skipped") and ledger.read_text().strip().count("\n") == 0
    # a record missing the load-bearing fields is refused
    assert "error" in mb.feedback_ingest(REPO, "demo", {"id": "x"}, ledger=ledger)


def test_drain_folds_inbox_into_ledger(tmp_path, monkeypatch):
    import drain_feedback as df
    # a fake manuscript tree: <root>/manuscript/whitepaper/main.tex + feedback/inbox/*.json
    mdir = tmp_path / "manuscript" / "whitepaper"
    inbox = mdir / "feedback" / "inbox"
    inbox.mkdir(parents=True)
    root = mdir / "main.tex"
    root.write_text("\\documentclass{article}\\begin{document}x\\end{document}")
    for i in range(3):
        rec = {"id": f"FB-2026-{i}", "ts": f"2026-07-03T10:0{i}:00",
               "node_id": "res:window-verdict", "comment": f"comment {i}", "kind": "note"}
        (inbox / f"FB-2026-{i}.json").write_text(json.dumps(rec))
    (inbox / "bad.json").write_text("{ not json")

    out = df.drain(str(root), "demo")
    assert out["found"] == 4 and out["ingested"] == 3 and out["bad"] == 1
    ledger = mdir / "feedback" / "feedback.jsonl"
    lines = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 3
    ids = {json.loads(l)["id"] for l in lines}
    assert ids == {"FB-2026-0", "FB-2026-1", "FB-2026-2"}
    # drained files removed; the bad one stays for inspection
    assert not list(inbox.glob("FB-2026-*.json")) and (inbox / "bad.json").is_file()
    # re-drain is a no-op (idempotent)
    out2 = df.drain(str(root), "demo")
    assert out2["ingested"] == 0
