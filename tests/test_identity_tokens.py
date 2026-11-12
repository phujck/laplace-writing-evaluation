"""The unified identity tokens (N55, website milestone one bite B3).

ONE token source -- ``templates/identity/palette.json`` -- projected into modes.
``site_backend`` emits the screen-dark mode as a ``<style id="identity-tokens">``
block into every page head; ``style.css`` consumes the same custom-property
names. These tests pin the contract:

- palette.json parses and declares a canonical, meta-free ``tokens`` list;
- EVERY mode emits EXACTLY the full token set (no mode drops a token, none
  smuggles an extra) -- so a consumer of any surface gets a complete palette;
- the generated block is a FAITHFUL projection of palette.json (drift check):
  ``identity_tokens_style`` declares exactly the screen-dark values in canonical
  order, so a stale re-render is impossible to hide;
- the four dead generic hues (blue/green/purple/rose) and their ``--highlight-*``
  var names appear NOWHERE in the served CSS/HTML -- scanning the live site repo
  but EXCLUDING built artifacts (``memories/``, ``review/``, ``unlisted/``, the
  ``talks/`` deck dirs, ``.venv``/``.git``) that are not ours to rewrite.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from laplace.web import site_backend as sb

DEAD_HEXES = ["#3b82f6", "#10b981", "#8b5cf6", "#f43f5e"]
DEAD_VARS = ["--highlight-blue", "--highlight-green",
             "--highlight-purple", "--highlight-rose"]
REQUIRED_MODES = {"screen-dark", "print-light", "deck", "graph"}


def _palette() -> dict:
    return sb.load_palette()


def test_palette_parses_and_declares_tokens():
    pal = _palette()
    assert isinstance(pal.get("tokens"), list) and pal["tokens"]
    assert len(pal["tokens"]) == len(set(pal["tokens"])), "tokens must be unique"
    assert all(not t.startswith("_") for t in pal["tokens"]), "tokens are not meta keys"
    assert isinstance(pal.get("modes"), dict) and pal["modes"]


def test_every_mode_emits_the_full_token_set():
    pal = _palette()
    canonical = set(pal["tokens"])
    assert REQUIRED_MODES <= set(pal["modes"]), "the four ruled modes must exist"
    for name, mode in pal["modes"].items():
        emitted = {k for k in mode if not k.startswith("_")}
        assert emitted == canonical, (
            f"mode {name!r}: missing {sorted(canonical - emitted)}, "
            f"extra {sorted(emitted - canonical)}")
        assert all(str(mode[k]).strip() for k in canonical), \
            f"mode {name!r} has an empty token value"


def test_generated_block_is_faithful_projection_of_screen_dark():
    pal = _palette()
    block = sb.identity_tokens_style(pal, "screen-dark")
    assert block.startswith('  <style id="identity-tokens">:root{')
    assert block.endswith("}</style>")
    sd = pal["modes"]["screen-dark"]
    # exactly the screen-dark declarations, in canonical order (the drift check)
    expected = "".join(f"--{k}:{sd[k]};" for k in pal["tokens"])
    assert expected == block[len('  <style id="identity-tokens">:root{'):-len("}</style>")]


def test_semantic_tokens_reserved():
    pal = _palette()
    sd = pal["modes"]["screen-dark"]
    for tok in ("refused", "evidence"):
        assert tok in pal["tokens"], f"{tok} must be a declared token"
        assert sd[tok], f"{tok} must have a screen-dark value"
    # refused is the shown-refusal red, aligned to the conceptric 'missing' red
    assert pal["modes"]["graph"]["refused"] == sd["refused"]


def test_block_injected_into_rendered_pages(tmp_path: Path):
    """render_site injects the identity block into the shell of every page."""
    site = tmp_path / "site"
    (site / "content").mkdir(parents=True)
    (site / "spine.json").write_text(_MINI_SPINE, encoding="utf-8")
    (site / "content" / "index.html").write_text("  <main>hi</main>\n", encoding="utf-8")
    sb.render_site(site_root=tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '<style id="identity-tokens">:root{--bg-primary:' in html
    for v in DEAD_VARS:
        assert v not in html


# --- the dead-hue sweep over the served site repo -----------------------------

_EXCLUDE_PREFIXES = (
    "memories/", "review/", "unlisted/", "talks/",
    ".venv/", ".git/", "_b3_screens/", "site/_b3_screens/",
)


def _site_root():
    try:
        root = sb.resolve_site_root()
    except Exception:
        return None
    return root if (root / "site" / "spine.json").exists() else None


@pytest.mark.skipif(_site_root() is None, reason="real site clone absent")
def test_dead_hues_absent_from_served_css_html():
    root = _site_root()
    needles = [h.lower() for h in DEAD_HEXES] + [v.lower() for v in DEAD_VARS]
    offenders: list[str] = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix not in (".css", ".html"):
            continue
        rel = p.relative_to(root).as_posix()
        if any(rel.startswith(x) for x in _EXCLUDE_PREFIXES):
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore").lower()
        offenders += [f"{rel}: {n}" for n in needles if n in txt]
    assert not offenders, "dead hues in served CSS/HTML:\n" + "\n".join(offenders)


_MINI_SPINE = """{
  "site": {
    "base_url": "https://example.test", "author": "T A", "theme_color": "#0a0e1a",
    "brand_html": "T", "nav": [{"key": "home", "label": "Home", "href": "/"}],
    "footer_text": "x", "footer_links": [{"label": "E", "href": "mailto:t@t.test"}],
    "rel_me": ["https://example.test/me"], "google_site_verification": "T",
    "font_url": "https://fonts.example/css2?family=JetBrains+Mono",
    "og_site_name": "T A", "og_locale": "en_GB",
    "jsonld_person": "  {}"
  },
  "pages": [
    {"path": "index.html", "layout": "full", "nav_active": "home",
     "title": "T", "description": "d", "canonical": "https://example.test/",
     "og_type": "profile", "og_title": "T", "og_description": "d",
     "og_image": "https://example.test/me.jpg", "twitter_card": "summary",
     "twitter_title": "T", "twitter_description": "d", "extra_css": []}
  ]
}
"""
