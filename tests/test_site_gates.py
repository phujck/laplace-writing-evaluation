"""The gates family (bite B5): the ONE pre-push ritual for the website project.

``python -m laplace.web.site_backend gates [--skip-visual]`` runs, in order: drift
(the existing check_site), links (every internal href/src resolves), survival
(every site/must_survive.json entry survives), meta (unique titles, one
canonical, og:title, theme-color pinned to the palette), deslop (the tell-list
lint over visible text), visual/mobile (375px no horizontal overflow, via
Playwright -- gracefully skipped, never failed, when no browser is present).

Unit tests build tiny tmp_path miniature sites (seeding one specific defect
each) so they never depend on the live clone. ONE integration test runs
``gates --skip-visual`` against the real sibling clone (skipped otherwise) --
that run must be green today.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.web import site_backend as sb

# ---------------------------------------------------------------------------
# Miniature site fixture -- the same shape test_site_backend.py uses (no
# cross-test-file import: tests/ has no __init__.py, so each module is
# self-contained).
# ---------------------------------------------------------------------------


def _mini_spine() -> dict:
    return {
        "site": {
            "base_url": "https://example.test",
            "author": "Test Author",
            "theme_color": "#0a0e1a",
            "brand_html": "T<span>.</span>A",
            "nav": [
                {"key": "home", "label": "Home", "href": "/"},
                {"key": "about", "label": "About", "href": "/about.html"},
            ],
            "footer_text": "© 2026 Test Author. Built by algebra.",
            "footer_links": [
                {"label": "Email", "href": "mailto:t@example.test"},
                {"label": "GitHub", "href": "https://github.com/example"},
            ],
            "rel_me": [
                "https://github.com/example",
                "https://otherplatform.example/me",
            ],
            "google_site_verification": "TEST-GSV-TOKEN",
            "font_url": "https://fonts.example/css2?family=JetBrains+Mono&family=Lora&family=Outfit",
            "og_site_name": "Test Author",
            "og_locale": "en_GB",
            "jsonld_person": '  {\n    "@type": "Person",\n    "name": "Test Author"\n  }',
        },
        "pages": [
            {
                "path": "index.html", "layout": "full", "nav_active": "home",
                "title": "Test Author — Person", "description": "Home description.",
                "canonical": "https://example.test/", "og_type": "profile",
                "og_title": "Test Author — Person", "og_description": "OG home.",
                "og_image": "https://example.test/me.jpg",
                "og_image_width": "1200", "og_image_height": "630",
                "twitter_card": "summary_large_image",
                "twitter_title": "Test Author — Person",
                "twitter_description": "Twitter home.", "extra_css": [],
            },
            {
                "path": "about.html", "layout": "full", "nav_active": "about",
                "title": "About — Test Author", "description": "About description.",
                "canonical": "https://example.test/about.html", "og_type": "website",
                "og_title": "About — Test Author", "og_description": "OG about.",
                "og_image": "https://example.test/me.jpg",
                "twitter_card": "summary", "twitter_title": "About — Test Author",
                "twitter_description": "Twitter about.", "extra_css": [],
                "jsonld": '  {\n    "@type": "WebPage",\n    "name": "About"\n  }',
            },
        ],
    }


@pytest.fixture
def mini_site(tmp_path: Path) -> Path:
    """A rendered-ready miniature site under tmp_path (spine + 2 innards), plus
    the template's own boilerplate asset refs (favicon/manifest/css/js) so the
    LINKS gate has something real to resolve those against -- the shell always
    references them (render_head/render_page), so a 'clean' fixture for a
    links test must provide them, same as the real clone does."""
    (tmp_path / "site" / "content").mkdir(parents=True)
    (tmp_path / "site" / "spine.json").write_text(
        json.dumps(_mini_spine(), ensure_ascii=False, indent=2), encoding="utf-8")
    (tmp_path / "site" / "content" / "index.html").write_text(
        '  <section class="hero">\n    <h1 id="who">Home</h1>\n  </section>\n',
        encoding="utf-8")
    (tmp_path / "site" / "content" / "about.html").write_text(
        '  <main>\n    <p>About body.</p>\n  </main>\n', encoding="utf-8")
    (tmp_path / "assets" / "css").mkdir(parents=True)
    (tmp_path / "assets" / "js").mkdir(parents=True)
    (tmp_path / "assets" / "css" / "style.css").write_text("", encoding="utf-8")
    (tmp_path / "assets" / "js" / "main.js").write_text("", encoding="utf-8")
    (tmp_path / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")
    return tmp_path

# ---------------------------------------------------------------------------
# links
# ---------------------------------------------------------------------------


def test_gate_links_passes_on_clean_mini_site(mini_site: Path):
    sb.render_site(site_root=mini_site)
    (mini_site / "site" / "must_survive.json").write_text("[]", encoding="utf-8")
    res = sb.gate_links(site_root=mini_site)
    assert res["ok"] is True, res["detail"]


def test_gate_links_catches_seeded_broken_link(mini_site: Path):
    # plant a broken absolute href in the about page's authored innards
    content = mini_site / "site" / "content" / "about.html"
    content.write_text(
        content.read_text(encoding="utf-8") + '\n<a href="/nowhere.html">gone</a>\n',
        encoding="utf-8")
    sb.render_site(site_root=mini_site)
    (mini_site / "site" / "must_survive.json").write_text("[]", encoding="utf-8")

    res = sb.gate_links(site_root=mini_site)
    assert res["ok"] is False
    assert any("nowhere.html" in d for d in res["detail"])


def test_gate_links_ignores_anchors_mailto_and_external(mini_site: Path):
    content = mini_site / "site" / "content" / "about.html"
    content.write_text(
        content.read_text(encoding="utf-8") +
        '\n<a href="#section">jump</a><a href="#">noop</a>'
        '<a href="mailto:x@example.test">mail</a>'
        '<a href="https://example.com/elsewhere">ext</a>\n',
        encoding="utf-8")
    sb.render_site(site_root=mini_site)
    (mini_site / "site" / "must_survive.json").write_text("[]", encoding="utf-8")

    res = sb.gate_links(site_root=mini_site)
    assert res["ok"] is True, res["detail"]


def test_gate_links_normalizes_dir_style_and_file_style(mini_site: Path):
    # '/about/' (directory-style) must resolve via an index.html under it;
    # '/about.html' (file-style) resolves directly. Plant both a good
    # directory link and a bad one to prove the dir-vs-file shapes are each
    # actually being checked, not silently accepted.
    (mini_site / "sub").mkdir()
    (mini_site / "sub" / "index.html").write_text("<html></html>", encoding="utf-8")
    content = mini_site / "site" / "content" / "about.html"
    content.write_text(
        content.read_text(encoding="utf-8") +
        '\n<a href="/sub/">sub ok</a><a href="/about.html">self ok</a>'
        '<a href="/missing-dir/">sub bad</a>\n',
        encoding="utf-8")
    sb.render_site(site_root=mini_site)
    (mini_site / "site" / "must_survive.json").write_text("[]", encoding="utf-8")

    res = sb.gate_links(site_root=mini_site)
    assert res["ok"] is False
    assert any("missing-dir" in d for d in res["detail"])
    assert not any("/sub/'" in d or "'/sub/'" in d for d in res["detail"])


def test_gate_links_accepts_declared_redirect_entry(mini_site: Path):
    # a link to a URL that only survives via a declared must_survive redirect
    # (not literally present on disk under that exact normalized path) passes.
    content = mini_site / "site" / "content" / "about.html"
    content.write_text(
        content.read_text(encoding="utf-8") + '\n<a href="/old/">old</a>\n',
        encoding="utf-8")
    sb.render_site(site_root=mini_site)
    (mini_site / "site" / "must_survive.json").write_text(
        json.dumps([{"url": "/old/", "kind": "redirect"}]), encoding="utf-8")

    res = sb.gate_links(site_root=mini_site)
    assert res["ok"] is True, res["detail"]


# ---------------------------------------------------------------------------
# survival
# ---------------------------------------------------------------------------


def test_gate_survival_catches_seeded_missing_asset(mini_site: Path):
    (mini_site / "site" / "must_survive.json").write_text(json.dumps([
        {"url": "/does-not-exist.pdf", "kind": "asset"},
    ]), encoding="utf-8")
    res = sb.gate_survival(site_root=mini_site)
    assert res["ok"] is False
    assert any("does-not-exist.pdf" in d for d in res["detail"])


def test_gate_survival_passes_for_existing_page_asset_special(mini_site: Path):
    sb.render_site(site_root=mini_site)
    (mini_site / "CNAME").write_text("example.test\n", encoding="utf-8")
    (mini_site / "site" / "must_survive.json").write_text(json.dumps([
        {"url": "/index.html", "kind": "page"},
        {"url": "/CNAME", "kind": "special"},
    ]), encoding="utf-8")
    res = sb.gate_survival(site_root=mini_site)
    assert res["ok"] is True, res["detail"]


def test_gate_survival_redirect_requires_stub_and_working_meta_refresh(mini_site: Path):
    (mini_site / "old").mkdir()
    (mini_site / "old" / "index.html").write_text(
        '<meta http-equiv="refresh" content="0; url=/about.html">', encoding="utf-8")
    sb.render_site(site_root=mini_site)
    (mini_site / "site" / "must_survive.json").write_text(json.dumps([
        {"url": "/old/", "kind": "redirect"},
    ]), encoding="utf-8")
    res = sb.gate_survival(site_root=mini_site)
    assert res["ok"] is True, res["detail"]

    # now break the refresh target -- must be caught
    (mini_site / "old" / "index.html").write_text(
        '<meta http-equiv="refresh" content="0; url=/nowhere.html">', encoding="utf-8")
    res = sb.gate_survival(site_root=mini_site)
    assert res["ok"] is False
    assert any("nowhere.html" in d for d in res["detail"])


# ---------------------------------------------------------------------------
# meta
# ---------------------------------------------------------------------------


def test_gate_meta_passes_on_clean_mini_site(mini_site: Path):
    sb.render_site(site_root=mini_site)
    res = sb.gate_meta(site_root=mini_site)
    assert res["ok"] is True, res["detail"]


def test_gate_meta_catches_seeded_duplicate_title(mini_site: Path):
    spine_path = mini_site / "site" / "spine.json"
    spine = json.loads(spine_path.read_text(encoding="utf-8"))
    spine["pages"][1]["title"] = spine["pages"][0]["title"]  # about == index title
    spine_path.write_text(json.dumps(spine), encoding="utf-8")
    sb.render_site(site_root=mini_site)

    res = sb.gate_meta(site_root=mini_site)
    assert res["ok"] is False
    assert any("duplicate title" in d for d in res["detail"])


def test_gate_meta_catches_theme_color_drift_from_palette(mini_site: Path, tmp_path: Path):
    # the mini_site's theme_color ("#0a0e1a") must equal the palette's
    # screen-dark bg-primary -- point at a palette whose bg-primary differs.
    palette = {
        "tokens": ["bg-primary"],
        "modes": {"screen-dark": {"bg-primary": "#123456"}},
    }
    palette_dir = tmp_path / "engine" / "templates" / "identity"
    palette_dir.mkdir(parents=True)
    (palette_dir / "palette.json").write_text(json.dumps(palette), encoding="utf-8")
    sb.render_site(repo_root=tmp_path / "engine", site_root=mini_site)

    res = sb.gate_meta(repo_root=tmp_path / "engine", site_root=mini_site)
    assert res["ok"] is False
    assert any("theme-color" in d for d in res["detail"])


# ---------------------------------------------------------------------------
# deslop
# ---------------------------------------------------------------------------


def test_gate_deslop_catches_seeded_slop_word(mini_site: Path):
    content = mini_site / "site" / "content" / "about.html"
    content.write_text(
        content.read_text(encoding="utf-8") + "\n<p>This is a rigorous demo.</p>\n",
        encoding="utf-8")
    sb.render_site(site_root=mini_site)

    res = sb.gate_deslop(site_root=mini_site)
    assert res["ok"] is False
    assert any("rigorous" in d for d in res["detail"])


def test_gate_deslop_catches_seeded_epigram_shape(mini_site: Path):
    content = mini_site / "site" / "content" / "index.html"
    content.write_text(
        content.read_text(encoding="utf-8") + "\n<h2>A tool, not a toy</h2>\n",
        encoding="utf-8")
    sb.render_site(site_root=mini_site)

    res = sb.gate_deslop(site_root=mini_site)
    assert res["ok"] is False
    assert any("epigram" in d for d in res["detail"])


def test_gate_deslop_exempts_long_body_prose_epigram(mini_site: Path):
    # the same '<A>, not <B>' connective inside a long paragraph is body prose
    # -- exempt by construction (heading/tagline position only).
    long_line = ("This whole paragraph goes on for quite a long while about many things, "
                 "and ends with a clause that reads as substance, not slogan, in context.")
    content = mini_site / "site" / "content" / "about.html"
    content.write_text(
        content.read_text(encoding="utf-8") + f"\n<p>{long_line}</p>\n", encoding="utf-8")
    sb.render_site(site_root=mini_site)

    res = sb.gate_deslop(site_root=mini_site)
    assert res["ok"] is True, res["detail"]


def test_gate_deslop_allowlist_suppresses_known_string_but_not_new_ones(mini_site: Path):
    content = mini_site / "site" / "content" / "about.html"
    content.write_text(
        content.read_text(encoding="utf-8") +
        "\n<p>This is a rigorous demo.</p>\n<p>Also a rigorous experiment.</p>\n",
        encoding="utf-8")
    sb.render_site(site_root=mini_site)
    (mini_site / "site" / "deslop_allow.json").write_text(
        json.dumps(["This is a rigorous demo."]), encoding="utf-8")

    res = sb.gate_deslop(site_root=mini_site)
    # the allowlisted line is suppressed, but the second, un-allowlisted
    # 'rigorous' still fails the gate -- allowlisting one string must not
    # blanket-suppress the bare word everywhere else on the page.
    assert res["ok"] is False
    assert not any("This is a rigorous demo" in d for d in res["detail"])
    assert any("Also a rigorous experiment" in d for d in res["detail"])


def test_gate_deslop_ignores_script_and_style_content(mini_site: Path):
    content = mini_site / "site" / "content" / "about.html"
    content.write_text(
        content.read_text(encoding="utf-8") +
        "\n<script>var rigorous = 'delve';</script>"
        "\n<style>.rigorous { color: red; }</style>\n",
        encoding="utf-8")
    sb.render_site(site_root=mini_site)

    res = sb.gate_deslop(site_root=mini_site)
    assert res["ok"] is True, res["detail"]


# ---------------------------------------------------------------------------
# visual (skip path only -- no browser dependency in the unit tests)
# ---------------------------------------------------------------------------


def test_gate_visual_skip_flag_never_fails():
    res = sb.gate_visual(skip=True)
    assert res["ok"] is True
    assert res["skipped"] is True
    assert res["detail"]


# ---------------------------------------------------------------------------
# run_gates orchestration
# ---------------------------------------------------------------------------


def test_run_gates_ok_false_when_any_gate_fails(mini_site: Path):
    sb.render_site(site_root=mini_site)
    (mini_site / "site" / "must_survive.json").write_text(json.dumps([
        {"url": "/nope.pdf", "kind": "asset"},
    ]), encoding="utf-8")

    result = sb.run_gates(site_root=mini_site, skip_visual=True)
    assert result["ok"] is False
    names = {g["name"]: g for g in result["gates"]}
    assert names["survival"]["ok"] is False
    assert names["visual"]["skipped"] is True


def test_run_gates_green_on_clean_mini_site(mini_site: Path):
    sb.render_site(site_root=mini_site)
    (mini_site / "site" / "must_survive.json").write_text("[]", encoding="utf-8")
    result = sb.run_gates(site_root=mini_site, skip_visual=True)
    assert result["ok"] is True, [g for g in result["gates"] if not g["ok"]]


# ---------------------------------------------------------------------------
# Integration: the real sibling clone, skipped when absent. Green today.
# ---------------------------------------------------------------------------


def _real_site_root() -> Path | None:
    try:
        root = sb.resolve_site_root()
    except Exception:
        return None
    return root if (root / "site" / "spine.json").exists() else None


@pytest.mark.skipif(_real_site_root() is None,
                    reason="real sibling clone / spine.json absent")
def test_integration_real_clone_gates_skip_visual_is_green():
    root = _real_site_root()
    assert root is not None
    sb.render_site(site_root=root)  # idempotent once bootstrapped
    result = sb.run_gates(site_root=root, skip_visual=True)
    assert result["ok"] is True, [g for g in result["gates"] if not g["ok"]]


# ---------------------------------------------------------------------------
# VERDICT sentinel -- the pipe-swallow fix: the CLI's true last line must be
# machine-parsable (VERDICT=PASS / VERDICT=FAIL checks=n/n reasons=...) so a
# truncated read (tail -1, last log line) still carries the whole verdict.
# ---------------------------------------------------------------------------


def _fake_gates(*, ok_flags: list[bool], names: list[str]) -> dict:
    gates = [{"name": n, "ok": ok, "skipped": False, "detail": [] if ok else [f"{n} broke"]}
              for n, ok in zip(names, ok_flags)]
    return {"ok": all(ok_flags), "gates": gates}


def test_gates_verdict_line_pass():
    result = _fake_gates(ok_flags=[True, True, True], names=["drift", "links", "meta"])
    assert sb._gates_verdict_line(result) == "VERDICT=PASS"


def test_gates_verdict_line_fail_names_and_counts():
    result = _fake_gates(ok_flags=[True, False, False], names=["drift", "survival", "meta"])
    assert sb._gates_verdict_line(result) == "VERDICT=FAIL checks=2/3 reasons=survival,meta"


def test_main_gates_emits_sentinel_as_last_line_on_pass(monkeypatch, capsys):
    monkeypatch.setattr(sb, "run_gates",
                         lambda **kw: _fake_gates(ok_flags=[True, True], names=["drift", "links"]))
    rc = sb._main(["gates", "--skip-visual"])
    lines = capsys.readouterr().out.rstrip("\n").splitlines()
    assert lines[-1] == "VERDICT=PASS"
    assert rc == 0


def test_main_gates_emits_sentinel_as_last_line_on_fail(monkeypatch, capsys):
    monkeypatch.setattr(sb, "run_gates",
                         lambda **kw: _fake_gates(ok_flags=[True, False, False],
                                                   names=["drift", "survival", "meta"]))
    rc = sb._main(["gates"])
    lines = capsys.readouterr().out.rstrip("\n").splitlines()
    assert lines[-1] == "VERDICT=FAIL checks=2/3 reasons=survival,meta"
    assert rc == 1
