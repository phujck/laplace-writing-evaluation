"""W2 — THE ARTEFACT SURFACE: the mechanical §6.2 island budget for artefact.html.

The mirror of ``test_dashboard_css_island_is_layout_only_under_4kb_no_color_literals``:
§6.2 says a rebuilt surface's OWN ``<style>`` is ≤4KB layout-only with NO color literals —
"island budgets are mechanical" only if a test actually enforces it per surface. Dashboard
shipped that test; W2 shipped none, so the artefact island silently grew to ~6.7KB. This
file closes that gap for artefact.html. The COMPONENT atoms it moved OUT (anchor-overlay
rows, rail rows, diff pane, tray groups, edit pane, hover bands) live in the companion
module's injected COMPONENT_CSS (already palette-checked by test_shared_model.py) — so we
also assert the relocation is REAL (the module carries the injected style), not a deletion.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[1] / "src" / "laplace"
_STATIC = _SRC / "web" / "static_shared"
_GOLDEN = 16 * 1024


def _artefact_html() -> str:
    return (_SRC / "web" / "artefact.html").read_text(encoding="utf-8")


def _style_block(html: str) -> str:
    m = re.search(r"<style>(.*?)</style>", html, re.S)
    return m.group(1) if m else ""


def test_artefact_html_is_within_16kb():
    assert len(_artefact_html().encode("utf-8")) <= _GOLDEN


def test_artefact_css_island_is_layout_only_under_4kb_no_color_literals():
    """Visual §6.1/§6.2: the surface links hymn.css (the one palette) and its OWN <style>
    is ≤4KB layout-only with NO color literals — every card/chip/door color rides a hymn
    component class, so the palette cannot re-fork per surface."""
    html = _artefact_html()
    assert 'href="/shared/hymn.css"' in html, "must link the one palette sheet"
    style = _style_block(html)
    n = len(style.encode("utf-8"))
    assert n <= 4 * 1024, f"the CSS island is over the 4KB budget ({n} bytes)"
    hexes = re.findall(r"#[0-9a-fA-F]{3,8}\b", style)
    funcs = re.findall(r"\b(?:rgb|rgba|hsl|hsla)\(", style)
    assert not hexes and not funcs, f"color literals leaked into the island: {hexes + funcs}"
    # composed from the shared component vocabulary (hymn.css), not bespoke classes
    assert "hy-door" in html, "the artefact surface must compose from the shared hy-door"


def test_artefact_component_atoms_relocated_not_deleted():
    """The island shrank because the component atoms moved to the companion module's injected
    COMPONENT_CSS (§6.2 relocation), NOT because rules were dropped. Assert the module carries
    the injected style AND the atoms that left the island (the overlay/rail/diff/tray/edit
    rules) actually land there — so a future 'trim' that deletes them instead is caught."""
    mod = (_STATIC / "artefact-panes.mjs").read_text(encoding="utf-8")
    assert "COMPONENT_CSS" in mod and "injectStyle" in mod, \
        "the companion module must inject its component CSS (§6.2 relocation target)"
    for sel in (".art-anchor-row", ".art-grp", "#art-diffpane", "#art-edit",
                ".art-hoverband", ".art-dism"):
        assert sel in mod, f"component rule {sel!r} was dropped, not relocated to the module"


def test_bare_file_link_resolves_its_owning_corpus_not_the_active_default(monkeypatch):
    """F4: a bare ``/artefact?file=<tex>`` (NO ?corpus=) must resolve the corpus that OWNS the
    file — not fall through to the active project and render the WRONG paper's reader/nodemap.
    Proven against a file whose corpus is NOT the active default, so the derivation is what
    changes the resolution (the test would pass vacuously if file= were still ignored).

    HERMETIC (WO-20260720-002501, the order-dependent flake drained 2026-07-22): the active
    default is derived from ambient repo state — ``LAPLACE_ACTIVE_PROJECT`` / ``.cockpit.json`` /
    the corpus whose friction ledger moved MOST RECENTLY (``corpus_ingest.default_corpus``). A
    sibling in a full-suite run that touched ``corpus_friction/paper_falqon.jsonl`` made
    paper_falqon the newest-mtime ledger, so ``default_project`` returned the OWNER and the
    ``owner != default`` premise coin-flipped red. The fix pins the default to a deterministic
    NON-owner corpus via the env override (checked first, above the mtime race), so the property
    under test — ``file=`` overriding the active default — is the only thing that moves the
    resolution, order be damned."""
    from laplace.web import artefact
    from laplace.research import corpus_ingest
    from laplace.pipeline import registry

    root = artefact._repo_root().resolve()

    # a real, unambiguous corpus that OWNS a current_artefact file
    owner = "paper_falqon"
    # pin the active default to a deterministic corpus that is NOT the owner (env wins over the
    # newest-ledger-mtime race that made this order-dependent), so `default != owner` always.
    others = [c for c in corpus_ingest.registered_corpora(root) if c != owner]
    assert others, "the repo needs a corpus distinct from the owner"
    pinned = "eigenengine" if "eigenengine" in others else others[0]
    monkeypatch.setenv("LAPLACE_ACTIVE_PROJECT", pinned)

    default = registry.default_project(root)
    assert default == pinned and owner != default, \
        "the env-pinned default must be deterministic and distinct from the owner"
    ctx = registry.project_context(owner, root)
    tex = (ctx.current_artefact or {}).get("tex")
    assert tex, f"{owner} has no current_artefact tex to address"

    # bare file= (no corpus) → the OWNING corpus, not the default
    derived = artefact.context_payload("", file=tex)
    assert derived is not None and derived["corpus"] == owner, \
        f"bare file= resolved to {derived and derived['corpus']!r}, not the owning {owner!r}"
    # the reader fact it seeds is the OWNER's paper, not the default's
    assert derived["current_artefact"].get("tex") == tex

    # control: with NO file and NO corpus, resolution DOES fall to the active default —
    # proving the file= above is what redirected it (not some coincidence of the default).
    bare = artefact.context_payload("")
    assert bare is not None and bare["corpus"] == default

    # and the pure resolver returns '' (keep the default) when nothing owns the path
    assert artefact._corpus_for_file("no/such/paper/main.tex", root) == ""


def test_reader_default_has_a_real_release_pdf_to_prefer_over_a_live_candidate():
    """finding-1 (his 2026-07-23 walk, RW-20260723-134848 banked, storm-resumed 2026-07-23):
    ``registry.project_context``'s ``current_artefact`` is the raw editor candidate (main.pdf)
    whenever the release state machine isn't literally RELEASED — even when a real minted
    release sits right beside it (paper_falqon: ``release/finalize.json`` + the r2 pdf exist on
    disk, but no ``release/state.json`` sidecar, so ``current_artefact.kind`` stays
    ``"candidate"`` forever). A bare reader arrival must not be served whatever the last probe
    or editor compile happened to leave in ``main.pdf``.

    THE FIX IS CLIENT-SIDE (``artefact-panes.mjs`` ``currentRevision()``): when
    ``current_artefact.kind != "release"``, the reader prefers the newest ``"release"``-kind
    row from the SAME ``/shared/versions`` rail over the raw candidate — never here. Both
    ``artefact.context_payload`` and ``/projection/pdf`` deliberately keep handing back the
    raw, undecided facts (the module's own docstring: "the surface can never re-derive a
    root" — ``current_artefact`` is a SHARED fact dashboard/pipeline_surface/ladder/
    project_state/corpus_ingest all read for THEIR OWN purposes; substituting the reader's
    preferred display revision into it would silently change what every one of those means).
    ``/projection/pdf`` is a dumb file server with no resolution opinion of its own.

    So the only thing this suite CAN verify server-side, without duplicating the client's
    display choice, is the DATA CONTRACT that choice depends on: for a corpus whose
    ``current_artefact`` is a live candidate, the versions rail must carry a newest
    ``"release"``-kind row whose pdf path is a file that GENUINELY EXISTS on disk (never a
    client-side guess — shared_ui._release_rows only ever adds a path after ``.is_file()``)
    and differs from the live candidate, so a client preferring it never serves a 404 and the
    preference is a real, observable change.

    FIXTURE (repointed 2026-08-07): the walk's original case was paper_falqon, but its
    ``main.pdf`` is gitignored (``paper_falqon/manuscript/.gitignore:15``), so in any clone
    ``_current_artefact`` falls through to the newest minted pdf — the SAME file as the
    release row — and the difference assertion cannot hold. subset-sum-itqde reproduces the
    shape with tracked files: ``whitepaper/main.pdf`` is the live candidate and
    ``whitepaper/subset-sum-itqde-2026-07-14-r1.pdf`` is the minted release beside it."""
    from laplace.web import artefact, shared_ui
    from laplace.manuscript import manuscript_versions
    from laplace.pipeline import registry

    root = artefact._repo_root().resolve()
    corpus = "subset-sum-itqde"
    ctx = registry.project_context(corpus, root)
    assert ctx is not None, f"{corpus} must resolve"
    art = ctx.current_artefact or {}
    # the exact bug shape: the live compile, never a minted release, is what current_artefact
    # names whenever the release state machine hasn't been (re)armed — the premise the
    # client-side default-preference exists to route around. If this corpus now resolves to
    # "release" the fixture has moved on; re-point the test at one that still reproduces it.
    assert art.get("kind") != "release", (
        f"{corpus} is the walk's reproduction case (a live candidate, no release/state.json "
        "sidecar) — this test needs a corpus whose current_artefact is still a live candidate")

    versions = manuscript_versions.versions_payload(corpus, root)
    assert versions is not None
    release_rows = [r for r in versions["rows"] if r["kind"] == "release"]
    assert release_rows, "a reader default has nothing real to prefer without a banked release row"

    # newest-first (the rail's own ts sort, the same order the client's .find() walks).
    newest = release_rows[0]
    pdf_path = next((p for p in newest["paths"] if p.lower().endswith(".pdf")), None)
    assert pdf_path, f"the newest release row must carry a real pdf path ({newest})"
    assert (root / pdf_path).is_file(), (
        f"the release row's pdf must genuinely exist on disk ({pdf_path}) — the client's "
        "reader-default preference would otherwise serve a 404 to every bare arrival")
    assert pdf_path != art.get("pdf"), (
        f"the release pdf ({pdf_path}) must differ from the live candidate ({art.get('pdf')}) "
        "for the reader-default preference to be a meaningful, observable change")
