#!/usr/bin/env python3
"""The deck's visual gate: drive the unsealed preview in headless Chromium.

Owns law 15 (pdf-pagination) and the behavioral half of the deck's
verification: fonts actually loaded (fail loud, never a silent fallback),
keyboard navigation does what the shell script promises, a provenance click
does not advance the deck, every slide screenshots, and the printed PDF has
exactly one page per slide with the provenance lines surviving into its text
layer.

Fonts: the deployed shell loads Google Fonts; a headless file:// render here
cannot, so the gate injects the site's own vendored variable faces
(phujck.github.io/demo/shared/fonts) as data-URIs into ITS RENDER COPY ONLY —
the artifact under seal is untouched, and the verdict records which source
served.

Usage:
  deck_visual_gate.py --preview DIR --evidence DIR --shots DIR
"""
from __future__ import annotations

import argparse
import base64
import glob
import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO.parent / "phujck.github.io"
FONTS = SITE / "demo" / "shared" / "fonts"
META = json.loads((REPO / "site_exports" / "registers" / "deck" / "deck.meta.json")
                  .read_text(encoding="utf-8"))
N_SLIDES = len(META["slides"])
LAST_ID = META["slides"][-1]["id"]
MARKED = [i + 1 for i, sl in enumerate(META["slides"]) if sl["numbers"] or sl.get("src")]

FAILS: list[str] = []


def law(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def chromium_path() -> str:
    cands = glob.glob("/opt/pw-browsers/chromium-*/chrome-linux/chrome")
    if cands:
        return cands[0]
    p = Path("/opt/pw-browsers/chromium")
    if p.is_file():
        return str(p)
    raise SystemExit("no chromium under /opt/pw-browsers — the gate needs the vendored browser")


def font_face_css() -> str:
    faces = [
        ("Outfit", FONTS / "outfit-var.woff2", "normal"),
        ("Lora", FONTS / "lora-var.woff2", "normal"),
        ("Lora", FONTS / "lora-italic-var.woff2", "italic"),
        ("JetBrains Mono", FONTS / "jetbrains-mono-var.woff2", "normal"),
    ]
    out = []
    for fam, path, style in faces:
        b64 = base64.b64encode(path.read_bytes()).decode()
        out.append(
            f"@font-face{{font-family:'{fam}';font-style:{style};"
            f"font-weight:100 900;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}"
        )
    return "<style id=\"gate-fonts\">" + "".join(out) + "</style>"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", required=True)
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--shots", required=True)
    args = ap.parse_args()

    src = Path(args.preview) / "deck" / "index.html"
    if not src.exists():
        raise SystemExit(f"no preview at {src} — run build_deck.py --preview first")
    evidence = Path(args.evidence)
    shots = Path(args.shots)
    evidence.mkdir(parents=True, exist_ok=True)
    shots.mkdir(parents=True, exist_ok=True)

    gate_page = shots / "gate-index.html"
    gate_page.write_text(
        src.read_text(encoding="utf-8").replace("</head>", font_face_css() + "\n</head>", 1),
        encoding="utf-8")

    from playwright.sync_api import sync_playwright

    exe = chromium_path()
    verdict: dict = {"date": date.today().isoformat(), "chromium": exe,
                     "font_source": "vendored data-URI (demo/shared/fonts), render copy only"}

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe)
        page = browser.new_context(viewport={"width": 1280, "height": 720},
                                   device_scale_factor=2).new_page()
        page.goto(gate_page.as_uri())
        page.wait_for_selector(".deck.js-on", timeout=8000)
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(300)

        fonts = {fam: page.evaluate(f"document.fonts.check(\"12px '{fam}'\")")
                 for fam in ("Outfit", "Lora", "JetBrains Mono")}
        verdict["fonts_loaded"] = fonts
        law("fonts-loaded", all(fonts.values()), str(fonts))

        def counter() -> str:
            return page.text_content("#deckcount").strip()

        law("nav-start", counter() == f"1 / {N_SLIDES}", counter())
        for _ in range(N_SLIDES - 1):
            page.keyboard.press("ArrowRight")
        law("nav-end", counter() == f"{N_SLIDES} / {N_SLIDES}"
            and page.evaluate("location.hash") == "#" + LAST_ID,
            f"{counter()} {page.evaluate('location.hash')}")
        page.keyboard.press("ArrowLeft")
        law("nav-back", counter() == f"{N_SLIDES - 1} / {N_SLIDES}", counter())
        page.keyboard.press("Home")
        law("nav-home", counter() == f"1 / {N_SLIDES}", counter())

        page.mouse.click(1100, 360)
        law("click-advances", counter() == f"2 / {N_SLIDES}", counter())

        page.evaluate("location.hash = '#s04-the-bill-for-orientation'")
        page.wait_for_timeout(150)
        before = counter()
        page.click(".slide.on .num", position={"x": 4, "y": 4})
        law("num-click-inert", counter() == before == f"4 / {N_SLIDES}",
            f"{before} → {counter()}")
        page.evaluate("document.activeElement && document.activeElement.blur()")
        page.mouse.move(20, 700)  # park the pointer so no hover card rides the screenshots

        # overflow probe + per-slide screenshots
        page.keyboard.press("Home")
        page.wait_for_timeout(120)
        overflow = []
        shot_files = []
        for i in range(N_SLIDES):
            page.wait_for_timeout(90)
            if page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1"):
                overflow.append(i + 1)
            f = shots / f"slide-{i + 1:02d}.png"
            page.screenshot(path=str(f))
            shot_files.append(f.name)
            page.keyboard.press("ArrowRight")
        law("no-horizontal-overflow", not overflow, str(overflow))
        verdict["screenshots"] = shot_files

        pdf_path = evidence / "deck.pdf"
        page.pdf(path=str(pdf_path), print_background=True, prefer_css_page_size=True,
                 width="338.7mm", height="190.5mm")

        # the one-pager: a standalone A4 DOCUMENT, its own render and PDF
        one_src = Path(args.preview) / "deck" / "onepager.html"
        gate_one = shots / "gate-onepager.html"
        gate_one.write_text(one_src.read_text(encoding="utf-8")
                            .replace("</head>", font_face_css() + "\n</head>", 1),
                            encoding="utf-8")
        one_path = evidence / "onepager.pdf"
        pg1 = browser.new_context(viewport={"width": 900, "height": 1273}).new_page()
        pg1.goto(gate_one.as_uri())
        pg1.evaluate("document.fonts.ready")
        pg1.wait_for_timeout(300)
        pg1.screenshot(path=str(shots / "onepager.png"), full_page=True)
        pg1.pdf(path=str(one_path), print_background=True, prefer_css_page_size=True,
                format="A4")

        # the analysis document (business plan): multi-page A4
        plan_src = Path(args.preview) / "deck" / "bizplan.html"
        plan_path = evidence / "bizplan.pdf"
        if plan_src.exists():
            gate_plan = shots / "gate-bizplan.html"
            gate_plan.write_text(plan_src.read_text(encoding="utf-8")
                                 .replace("</head>", font_face_css() + "\n</head>", 1),
                                 encoding="utf-8")
            pg2 = browser.new_context(viewport={"width": 900, "height": 1273}).new_page()
            pg2.goto(gate_plan.as_uri())
            pg2.evaluate("document.fonts.ready")
            pg2.wait_for_timeout(300)
            pg2.pdf(path=str(plan_path), print_background=True,
                    prefer_css_page_size=True, format="A4")
        browser.close()

    from pypdf import PdfReader

    deck_pdf = PdfReader(str(pdf_path))
    one_pdf = PdfReader(str(one_path))
    verdict["pdf_pages"] = len(deck_pdf.pages)
    verdict["onepager_pages"] = len(one_pdf.pages)
    law("pdf-pagination", len(deck_pdf.pages) == N_SLIDES,
        f"{len(deck_pdf.pages)} pages (want {N_SLIDES})")
    law("onepager-single-page", len(one_pdf.pages) == 1, f"{len(one_pdf.pages)} pages")

    missing = []
    for n in MARKED:
        text = deck_pdf.pages[n - 1].extract_text() or ""
        if "source:" not in text:
            missing.append(n)
    verdict["srclines_in_pdf"] = not missing
    law("srclines-survive-print", not missing, f"pages missing source line: {missing}")
    one_text = one_pdf.pages[0].extract_text() or ""
    law("onepager-sourced", "source:" in one_text, "the document's figure source line")
    if plan_path.exists():
        plan_pdf = PdfReader(str(plan_path))
        verdict["bizplan_pages"] = len(plan_pdf.pages)
        plan_text = " ".join((p.extract_text() or "") for p in plan_pdf.pages)
        law("bizplan-renders", 3 <= len(plan_pdf.pages) <= 9
            and "modelled" in plan_text and "SPEC" in plan_text,
            f"{len(plan_pdf.pages)} pages; typed-numbers language present")

    verdict["fails"] = FAILS
    (evidence / "verdict.json").write_text(json.dumps(verdict, indent=1) + "\n",
                                           encoding="utf-8")
    print(("gate green — " if not FAILS else "GATE FAILED — ")
          + f"verdict at {evidence / 'verdict.json'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
