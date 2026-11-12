"""The Chromium fence, resolved instead of assumed.

The banked disease (WO-20260810-w4-2-synctex-family): every headless tier in the
suite hardcoded ``/opt/pw-browsers/chromium-*/chrome-linux/chrome`` — the layout of
ONE remote container. Two ways that lies:

  * on a box where playwright installed its browsers the ordinary way
    (``~/.cache/ms-playwright``) the glob misses and every headless test SKIPS,
    so the tier reads green while proving nothing (the UNPROVEN verdict, not a pass);
  * newer playwright builds name the directory ``chrome-linux64``, not
    ``chrome-linux``, so even a /opt install can miss.

So resolve the binary in a declared order — ``$LAPLACE_CHROME`` →
``$PLAYWRIGHT_BROWSERS_PATH`` → ``/opt/pw-browsers`` → the default user cache — over
BOTH directory layouts, and hand back an honest ``None`` with a reason naming the
places that were searched. Same shape as the synctex-binary law in
``projection_viewer``: env → search → honest None, never a hardcoded path.
"""

from __future__ import annotations

import os
from pathlib import Path

# every place a playwright chromium is known to land, in resolution order
_ROOTS = ("/opt/pw-browsers", "~/.cache/ms-playwright", "~/.local/share/ms-playwright")
# the two chrome-directory layouts playwright has shipped
_LAYOUTS = ("chrome-linux/chrome", "chrome-linux64/chrome",
            "chrome-mac/Chromium.app/Contents/MacOS/Chromium", "chrome-win/chrome.exe")


def _roots() -> list[Path]:
    out: list[Path] = []
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env and env != "0":
        out.append(Path(env))
    out.extend(Path(r).expanduser() for r in _ROOTS)
    return out


def find_chrome() -> str | None:
    """The chromium executable, or an honest ``None``. Never raises."""
    direct = os.environ.get("LAPLACE_CHROME", "").strip()
    if direct:
        return direct if Path(direct).is_file() else None
    for root in _roots():
        try:
            if not root.is_dir():
                continue
            for build in sorted(root.glob("chromium-*")):
                for layout in _LAYOUTS:
                    cand = build / layout
                    if cand.is_file():
                        return str(cand)
        except OSError:
            continue
    return None


CHROME: str | None = find_chrome()

NO_CHROME_REASON = (
    "no Chromium build found — set $LAPLACE_CHROME, or install one under "
    + " / ".join(_ROOTS)
    + " (searched layouts: " + ", ".join(_LAYOUTS) + ")"
)


def playwright_available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except Exception:
        return False
    return True


HAS_PLAYWRIGHT: bool = playwright_available()
NO_BROWSER: bool = CHROME is None or not HAS_PLAYWRIGHT
SKIP_REASON: str = NO_CHROME_REASON if CHROME is None else "playwright not installed"
