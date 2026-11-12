"""The site_backend drift gate (bite B2, website milestone one).

site_backend is the ONE producer of the public site's shell: it renders every
page as ``shell(spine) + authored innards`` and re-renders to check for drift.
These tests pin the contract that makes ``update.ps1``-style regex mutation
impossible:

- render is DETERMINISTIC (render twice -> identical bytes; a re-run writes 0);
- ``check_site`` is CLEAN immediately after ``render_site``;
- a hand-touched SHELL on the deployed page is CAUGHT;
- a changed INNARDS without a re-render is CAUGHT (the live page no longer
  equals ``render(spine, content)``);
- ``memories/`` and ``review/`` are provably NEVER in the render set (the
  memorial page is untouchable);
- the generated marker comment is on EVERY page.

The unit tests use a miniature two-page site under ``tmp_path`` so they never
depend on the live clone. ONE integration test runs against the real sibling
clone when it is present (skipped otherwise).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.web import site_backend as sb

# ---------------------------------------------------------------------------
# Miniature site fixture: two fake pages, full spine tokens.
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
                "https://example.test/me",
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
    """A rendered-ready miniature site under tmp_path (spine + 2 innards)."""
    (tmp_path / "site" / "content").mkdir(parents=True)
    (tmp_path / "site" / "spine.json").write_text(
        json.dumps(_mini_spine(), ensure_ascii=False, indent=2), encoding="utf-8")
    (tmp_path / "site" / "content" / "index.html").write_text(
        '  <section class="hero">\n    <h1 id="who">Home</h1>\n  </section>\n',
        encoding="utf-8")
    (tmp_path / "site" / "content" / "about.html").write_text(
        '  <main>\n    <p>About body.</p>\n  </main>\n', encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# Determinism + clean check.
# ---------------------------------------------------------------------------

def test_render_is_deterministic_and_idempotent(mini_site: Path):
    r1 = sb.render_site(site_root=mini_site)
    assert set(r1["written"]) == {"index.html", "about.html"}
    assert r1["errors"] == []
    first = {p: (mini_site / p).read_bytes() for p in ("index.html", "about.html")}

    r2 = sb.render_site(site_root=mini_site)  # second render, no source change
    second = {p: (mini_site / p).read_bytes() for p in ("index.html", "about.html")}

    assert first == second, "render must be byte-identical across runs"
    assert r2["written"] == [], "a re-run must write 0 pages (idempotent)"
    assert set(r2["unchanged"]) == {"index.html", "about.html"}


def test_check_clean_after_render(mini_site: Path):
    sb.render_site(site_root=mini_site)
    res = sb.check_site(site_root=mini_site)
    assert res["ok"] is True
    assert res["drift"] == []
    assert res["errors"] == []


def test_rendered_nav_exposes_the_control_target(mini_site: Path):
    sb.render_site(site_root=mini_site)
    text = (mini_site / "index.html").read_text(encoding="utf-8")
    assert 'aria-controls="nav-links"' in text
    assert '<ul class="nav-links" id="nav-links">' in text


def test_check_flags_unrendered_page(mini_site: Path):
    # never rendered -> live files absent -> drift (missing)
    res = sb.check_site(site_root=mini_site)
    assert res["ok"] is False
    assert {d["path"] for d in res["drift"]} == {"index.html", "about.html"}


# ---------------------------------------------------------------------------
# Drift detection: shell edit, innards edit without re-render.
# ---------------------------------------------------------------------------

def test_planted_shell_edit_is_caught(mini_site: Path):
    sb.render_site(site_root=mini_site)
    live = mini_site / "index.html"
    # hand-touch the generated SHELL (the nav) on the deployed page
    tampered = live.read_text(encoding="utf-8").replace(
        'class="nav-brand"', 'class="nav-brand tampered"')
    live.write_text(tampered, encoding="utf-8")

    res = sb.check_site(site_root=mini_site)
    assert res["ok"] is False
    assert any(d["path"] == "index.html" for d in res["drift"])


def test_planted_innards_edit_without_rerender_is_caught(mini_site: Path):
    sb.render_site(site_root=mini_site)
    # edit the INNARDS source (content file) but do NOT re-render: the live page
    # is now stale versus render(spine, content).
    content = mini_site / "site" / "content" / "index.html"
    content.write_text(
        content.read_text(encoding="utf-8").replace("Home", "Home EDITED"),
        encoding="utf-8")

    res = sb.check_site(site_root=mini_site)
    assert res["ok"] is False
    assert any(d["path"] == "index.html" for d in res["drift"])


def test_hand_edited_live_innards_is_caught(mini_site: Path):
    sb.render_site(site_root=mini_site)
    live = mini_site / "about.html"
    # hand-touch the CONTENT region on the deployed page (bypassing the source)
    live.write_text(
        live.read_text(encoding="utf-8").replace("About body.", "About body. HACK"),
        encoding="utf-8")

    res = sb.check_site(site_root=mini_site)
    assert res["ok"] is False
    assert any(d["path"] == "about.html" for d in res["drift"])


# ---------------------------------------------------------------------------
# Exclusions + marker.
# ---------------------------------------------------------------------------

def test_memories_and_review_never_in_render_set(mini_site: Path):
    # plant sacred decoys that must never be listed, rendered, or touched
    (mini_site / "memories").mkdir()
    memorial = mini_site / "memories" / "index.html"
    memorial.write_text("THE MEMORIAL PAGE — UNTOUCHABLE", encoding="utf-8")
    (mini_site / "review" / "ssc").mkdir(parents=True)
    review = mini_site / "review" / "ssc" / "index.html"
    review.write_text("REVIEW LANDING", encoding="utf-8")

    spine = sb.load_spine(mini_site)
    listed = [p["path"] for p in spine["pages"]]
    assert not any(p.startswith(("memories/", "review/")) for p in listed)

    result = sb.render_site(site_root=mini_site)
    touched = set(result["written"]) | set(result["unchanged"])
    assert not any(p.startswith(("memories/", "review/")) for p in touched)
    # bytes provably untouched
    assert memorial.read_text(encoding="utf-8") == "THE MEMORIAL PAGE — UNTOUCHABLE"
    assert review.read_text(encoding="utf-8") == "REVIEW LANDING"


def test_marker_on_every_generated_page(mini_site: Path):
    sb.render_site(site_root=mini_site)
    for page in ("index.html", "about.html"):
        text = (mini_site / page).read_text(encoding="utf-8")
        assert "generated by laplace site_backend" in text
        assert f"edit site/content/{page}" in text, "marker must name the page's source"


def test_marker_does_not_trigger_quirks_mode(mini_site: Path):
    # the doctype must remain the first line (a comment before it => quirks mode)
    sb.render_site(site_root=mini_site)
    text = (mini_site / "index.html").read_text(encoding="utf-8")
    assert text.startswith("<!DOCTYPE html>\n<!-- generated by laplace site_backend")


# ---------------------------------------------------------------------------
# Integration: the real sibling clone (skipped when absent).
# ---------------------------------------------------------------------------

def _real_site_root() -> Path | None:
    try:
        root = sb.resolve_site_root()
    except Exception:
        return None
    return root if (root / "site" / "spine.json").exists() else None


@pytest.mark.skipif(_real_site_root() is None,
                    reason="real sibling clone / spine.json absent")
def test_integration_real_clone_check_passes_after_render():
    root = _real_site_root()
    assert root is not None
    sb.render_site(site_root=root)          # idempotent once bootstrapped
    res = sb.check_site(site_root=root)
    assert res["ok"] is True, res["drift"]
