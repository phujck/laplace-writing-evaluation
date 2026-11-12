"""The seats page's structural teeth.

Written 2026-08-25 after the design audit ranked it the worst surface remaining: 3.5
screens, zero links, zero buttons, and a first heading reading "Permission asks —
waiting on you" that the reader could do nothing about.

These assert the laws that survive without a browser: the house register (one font
family, one accent, no page-local design system), a way home, and — the one that would
have caught a real broken promise — that every door this page POSTs to is a door the
server actually handles.

Runtime law: /usr/bin/python3, system + user site, read-only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PAGE = ROOT / "src" / "laplace" / "web" / "seats_surface.html"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_the_page_can_be_left():
    """It had zero anchors: a reader could reach it and had no way back but the browser
    button. Same cul-de-sac class as /front/atlas and /front/walk before their cures."""
    html = _page()
    assert 'href="/front"' in html, "no route back to the front door"
    assert 'class="chrome"' in html


def test_no_page_local_design_system():
    """The audit found three design systems where there should be one. This page ran
    Georgia headlines on a dark ground and named "IBM Plex Sans" without ever loading
    it — so it rendered as system-ui here and would render as a different product on any
    machine that happens to have Plex installed."""
    html = _page()
    assert "Georgia" not in re.sub(r"/\*.*?\*/", "", html, flags=re.S), (
        "a serif light-background face is back on the dark surface")
    assert "IBM Plex" not in re.sub(r"/\*.*?\*/", "", html, flags=re.S), (
        "a font is named that nothing loads — the page renders differently per machine")
    assert "color-scheme: dark" in html or "color-scheme:dark" in html, (
        "without this, UA scrollbars and inputs flip to light on a dark-only instrument")


def test_headings_are_not_smaller_than_the_text_they_title():
    """Section headings measured 11.52px against 15px body copy, so the page read as one
    grey texture broken by faint uppercase whispers rather than as sections."""
    html = _page()
    h2 = re.search(r"\bh2\s*\{([^}]*)\}", html)
    assert h2, "no h2 rule"
    size = re.search(r"font:[^;]*?(\d+(?:\.\d+)?)px", h2.group(1))
    assert size and float(size.group(1)) >= 15, (
        f"h2 is {size.group(1) if size else '?'}px against 15px body copy")


def test_every_door_this_page_posts_to_is_actually_served():
    """THE GUARD THAT MATTERS MOST HERE, and the both-directions law the places table
    established: the asks card grew approve/refuse buttons, and a button that posts to a
    route the server does not handle is a broken promise rendered in the most
    convincing possible place — on the one card that says NEEDS YOU.

    The act deliberately reuses the front door's own door rather than reimplementing it:
    one act, one producer.
    """
    from laplace.web import front_door

    posted = set(re.findall(r'fetch\(\s*"(/[^"]+)"', _page()))
    act_doors = {d for d in posted if not d.startswith("/seats")}
    assert act_doors, "the page posts nowhere — the asks card lost its act"

    for door in act_doors:
        # a POST handler must exist: handle() returns None for "not mine, fall through"
        res = front_door.handle(door, {}, "POST", b"{}")
        assert res is not None, f"{door} is posted to but no handler owns it"
        status, _ctype, _payload = res
        assert status != 404, f"{door} is posted to but answers 404"


def test_the_asks_card_leads_with_words_not_an_id():
    """His conjugate-handle law, broken on the most consequential card on the page: the
    card led with `a.id`. The ask's own words lead now; the id stays summonable."""
    html = _page()
    assert 'el("span", "name", a.id)' not in html, "the card leads with an internal id"
    assert "a.text || a.id" in html, "the ask's own words must lead"
    assert "name.title = a.id" in html, "the id must stay summonable, never lost"
