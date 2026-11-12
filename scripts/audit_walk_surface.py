"""THE WALK SURFACE'S OWN FENCE — static, mechanical, runnable on any box.

``scripts/chair_walk_scroll_law.py`` grades the scroll law by DRIVING a headless browser,
which needs one installed. This grades everything that can be settled without rendering,
and it grades more than the scroll law:

  * the scroll-law arithmetic over the module's own reallocation constants, at 1280/1536;
  * bounded panes (every band scrolls inside itself, the page never does);
  * the motion law — no transition, no animation, no smooth-scroll API, one bounded jump;
  * the hover law — no tooltip anywhere, no affordance that exists only behind hover;
  * the raw-tex law — no right-rail node is ever assigned a block's source;
  * the echo defect — ONE gated entry point into the session band (the session cursor),
    and every renderer replacing rather than accumulating;
  * the keyboard chain, and the felt mode boundary on the digit keys;
  * the register law over every user-facing string, in the module and in the page;
  * the clean room — the import allowlist, and every loadable asset.

Usage:  python scripts/audit_walk_surface.py
Exit 0 = every check passes; exit 1 = the failures are named, one line each.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):                  # the verdicts carry en dashes
    sys.stdout.reconfigure(encoding="utf-8")

SRC = Path(__file__).resolve().parents[1] / "src" / "laplace"
HTML = (SRC / "web" / "walk.html").read_text(encoding="utf-8")
MJS = (SRC / "web" / "static_shared" / "walk.mjs").read_text(encoding="utf-8")

# THE MODULE WITH ITS COMMENTS REMOVED. A prose comment is not an interface string and it
# is not a mechanism: grading either one against comment text lets a check pass on a
# sentence ABOUT the code (a note recording a closed defect satisfied the session-cursor
# check verbatim) and lets the register law trip on a word inside a comment that no reader
# ever sees. Every check that asks "does the module DO this" reads this view.
MJS_CODE = re.sub(r"/\*.*?\*/", " ", MJS, flags=re.S)
MJS_CODE = re.sub(r"(?m)^\s*//.*$", "", MJS_CODE)
MJS_CODE = re.sub(r"(?m)([;,)\{\}])\s*//.*$", r"\1", MJS_CODE)

fail = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fail
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not ok:
        fail += 1


# ── 1 · THE SCROLL LAW, by arithmetic over the module's own constants ────────────────────
K = {k: int(v) for k, v in re.findall(r"const (RAIL_STRIP|RAIL_BAND|RAIL_ARMED|SPINE_W|"
                                      r"PAPER_MIN) = (\d+)", MJS)}
K.update({k: int(v) for k, v in re.findall(r"(RAIL_BAND|RAIL_ARMED|PAPER_MIN|SPINE_W)"
                                          r" = (\d+)", MJS)})
worst = K["SPINE_W"] + K["RAIL_ARMED"] + K["PAPER_MIN"]
for w in (1280, 1536):
    check(f"scroll law @{w}: spine+rail+paper fits",
          worst <= w, f"{K['SPINE_W']}+{K['RAIL_ARMED']}+{K['PAPER_MIN']} = {worst} ≤ {w}")
check("scroll law: the rail is CLAMPED to the room, never its wish",
      "Math.min(want, room)" in MJS)
check("scroll law: the page itself never scrolls",
      re.search(r"html, body \{[^}]*overflow: hidden", HTML, re.S) is not None)
check("scroll law: the grid's free column is minmax(0, 1fr) (no blowout)",
      "grid-template-columns: var(--spine-w) minmax(0, 1fr) var(--rail-w)" in HTML)
# the reading column at rest, in px, against the narrowest pane it can be given
measure_em = int(re.search(r"MEASURE_EM = (\d+)", MJS).group(1))
base = float(re.search(r"DOC_BASE = ([\d.]+)", MJS).group(1))
check("scroll law: the reading column fits the narrowest pane",
      measure_em * base <= K["PAPER_MIN"] * 1.55,
      f"{measure_em}em x {base}px = {measure_em * base:.0f}px column, "
      f"pane floor {K['PAPER_MIN']}px, and past that the PANE pans (G2)")
for sel in ("#paper", "#geo-scroll", "#spine", "#band-list", "#composer", "#ledger-list"):
    body = re.search(re.escape(sel) + r" \{[^}]*\}", HTML, re.S)
    check(f"bounded pane {sel}", bool(body) and "overflow" in body.group(0))

# ── 2 · THE MOTION LAW ───────────────────────────────────────────────────────────────────
check("no css transitions or animations anywhere",
      not re.search(r"\b(transition|animation|@keyframes)\b", HTML))
check("no smooth-scroll api (motion is the walk's own solved scroll only)",
      "behavior:" not in MJS and "scrollIntoView" not in MJS)
check("the one motion is the jump, bounded",
      "JUMP_MIN_MS" in MJS and "JUMP_MAX_MS" in MJS and "REDUCED" in MJS)

# ── 3 · THE HOVER LAW ────────────────────────────────────────────────────────────────────
check("no title= tooltip on any element", not re.search(r"\stitle=\"", HTML))
check("KaTeX's own hover-only title is stripped", 'removeAttribute("title")' in MJS)
hover_rules = re.findall(r"([^\n{]*:hover)\s*\{([^}]*)\}", HTML)
bad_hover = [r for r, body in hover_rules
             if re.search(r"display|visibility|opacity|content|pointer-events", body)]
check("no affordance exists only behind hover", not bad_hover, str(bad_hover))
check("focus is always visible", ":focus-visible { outline" in HTML)

# ── 4 · NO RAW TEX IN THE RIGHT RAIL ─────────────────────────────────────────────────────
RAIL = ("compWhere", "compShape", "compRoute", "compHint", "compEcho", "bandNote",
        "bandCount", "railCount", "compQuoteLbl", "compBodyLbl")
leaks = [n for n in RAIL if re.search(re.escape(n) + r"\.(textContent|value)\s*=\s*[^;]*\.tex\b", MJS)]
check("no rail node is ever assigned a block's raw tex", not leaks, str(leaks))
check("the composer's quote is the RENDERED passage, not source",
      'compQuote.value = quotable(a) ? a.quote : ""' in MJS_CODE)
# and the passage is only offered when the block's FACE is prose. A raw block (this
# corpus: tables, tabulars, enumerates) and a formula the renderer refused both show their
# own LaTeX, so tree-walking their text into the quote field put source in the rail.
check("a block that SHOWS its source never prefills the rail",
      re.search(r"function quotable\(a\)\s*\{[^}]*?!a\.texFace", MJS_CODE, re.S) is not None
      and re.search(r"b\.texFace = kind === \"raw\"", MJS_CODE) is not None
      and "const hasQuote = quotable(a)" in MJS_CODE
      and re.search(r"function shapeOf\(\)\s*\{.{0,200}?if \(!quotable\(a\)\) return "
                    r"\"comment\"", MJS_CODE, re.S) is not None)
# the canvas's own words about a block (the raw badge, the missing-image note) are chrome,
# and no reader of a block's text may see them — they were being banked as his quote.
check("the canvas's own chrome is never read as the block's text",
      'node.dataset.chrome = "1"' in MJS_CODE
      and MJS_CODE.count("document.createTreeWalker(") == 1
      and re.search(r"function textWalker\(host\)", MJS_CODE) is not None
      and MJS_CODE.count("textWalker(") >= 5)
check("the source flip's receipt row carries words, not tex",
      'flip: true, where: srcLabel(b)' in MJS and 'before: "", after: ""' in MJS)
check("the only textarea holding tex is the in-place block flip",
      MJS.count("ta.value = b.tex") == 1)

# ── 4b · THE ECHO DEFECT, closed by construction ─────────────────────────────────────────
check("the band has ONE entry point (admit), gated before the list",
      MJS_CODE.count("C.rows.unshift(") == 1
      and re.search(r"function admit\(row, token\).{0,900}?C\.rows\.unshift\(row\)",
                    MJS_CODE, re.S) is not None)
# THE GATE IS PROVENANCE, NOT A CLOCK. It used to compare the ledger's server-local naive
# timestamp against the client's UTC ISO string; west of UTC that refuses EVERY deposit the
# walk banks while the composer echoes that it banked — the echo defect inverted. Only the
# two bank paths hold the mint token, so nothing else can reach the list.
check("the band's gate is provenance, never a cross-process clock compare",
      "const MINTED = Symbol(" in MJS_CODE
      and re.search(r"function admit\(row, token\)\s*\{.{0,200}?token !== MINTED",
                    MJS_CODE, re.S) is not None
      # four mint sites, all this walk's own bank paths: the composer (bankDeposit),
      # the block flip (saveFlip), the typed edit (commitEdit), and the card's
      # comment/request (bankCardComment).
      and MJS_CODE.count("admit(row, MINTED)") == 4
      and re.search(r"\bts\s*<\s*S\.opened\b", MJS_CODE) is None)
check("a refused row is said, and the saying outlives the next render",
      "C.refusal" in MJS_CODE
      and re.search(r"function renderBand\(\).{0,8000}?C\.refusal", MJS_CODE, re.S)
      is not None
      and re.search(r"C\.last = listed \? row : null", MJS_CODE) is not None)
check("nothing fetches the historical ledger into the band",
      not re.search(r"C\.rows\s*=\s*[^;]*findings", MJS)
      and "/review/findings" in MJS      # it IS fetched — into the LEDGER door only
      and re.search(r"L\.rows = ledgerRows", MJS) is not None)
# renderBand is a thin wrapper (band + the linkages repaint in the same frame); the
# replace-never-accumulate law is graded on the core that owns the list.
check("renderBand delegates to the core and repaints the linkages in the same frame",
      re.search(r"function renderBand\(\) \{\s*renderBandCore\(\);\s*renderLinkages\(\);\s*\}",
                MJS_CODE) is not None)
for fn, node in [("renderBandCore", "bandList"), ("renderLedger", "ledgerList"),
                 ("renderScopeChips", "compScopes"), ("renderSpine", "spineList"),
                 ("renderDoc", "docEl"), ("renderLinkages", "lkBody")]:
    body = re.search(r"function " + fn + r"\(.*?\n\}", MJS, re.S)
    check(f"{fn} replaces, never accumulates",
          bool(body) and re.search(node + r"\.textContent = \"\"", body.group(0))
          is not None)

# ── 5 · THE KEYBOARD CHAIN ───────────────────────────────────────────────────────────────
for key, what in [('"?"', "the key map"), ('"o"', "the spine"), ('"n"', "next section"),
                  ('"p"', "previous section"), ('"0"', "the whole paper"),
                  ('"s"', "the in-place source flip"), ('"u"', "the undo"),
                  ('"g"', "the geometry face"), ('"l"', "the ledger history"),
                  ('"b"', "the band"), ('"f"', "fit"), ('"Escape"', "the escape chain"),
                  ('"Enter"', "arm / bank")]:
    check(f"key {key} is wired ({what})", f"ev.key === {key}" in MJS)
# THE FELT BOUNDARY, IN ONE PLACE, FOR EVERY SURFACE THE KEY LANDS ON. Three boundaries
# have been tried. (1) "the note is empty and holds the caret" — a state the dominant
# gesture never reaches, so a bare `1` typed a digit into the frozen quote and Enter banked
# a rewrite of his paragraph. (2) "am I in a text field" — right for the field case, but
# Alt+digit was reachable ONLY from inside the composer element, so the key promised to
# work "wherever the caret is" did nothing in the paper or a flipped block. (3) THIS: ONE
# `scopeKey(ev)`, called from the composer's chain AND the document's, the document's chain
# bailing on any key a nearer handler already took.
check("the scope key is ONE decision, not one per handler",
      MJS_CODE.count("function scopeKey(ev)") == 1
      and MJS_CODE.count("if (scopeKey(ev))") == 1
      and "if (ev.altKey && scopeKey(ev))" in MJS_CODE
      and 'ev.target === compBody && !compBody.value' not in MJS_CODE)
check("in a field a bare digit TYPES; Alt+digit scopes from anywhere",
      "if (!ev.altKey && inField(ev.target)) return false;" in MJS_CODE
      and re.search(r"function onKey\(ev\)\s*\{[^}]*?if \(ev\.defaultPrevented\) return;",
                    MJS_CODE, re.S) is not None)
check("the composer arms with the caret where the hint says the boundary is",
      'if (quotable(a)) compQuote.focus(); else compBody.focus();' in MJS_CODE
      and "digit there TYPES" in MJS)
# and the digit that DOES type is never silent: the passage's own label and the shape line
# state the conversion to a rewrite in the frame of the keystroke.
check("a digit typed into the passage states the conversion in the same frame",
      re.search(r"const edited = hasQuote && norm\(compQuote\.value\) !== norm\(a\.quote\)",
                MJS_CODE) is not None
      and 'compQuote.dataset.edited = edited ? "1" : ""' in MJS_CODE
      and re.search(r'compQuote\.addEventListener\("input".{0,220}?renderComposer\(\)',
                    MJS_CODE, re.S) is not None
      and '#comp-quote[data-edited="1"]' in HTML)
# the promise and the door: "scope it later from the band" is only sayable with a band
# control behind it, and that control must POST an append, never relabel the row locally.
# THE GATE IS scope_source, NOT scope: a rewrite banked at the door's own `sentence`
# default carries a scope, and gating on `!r.scope` made it the ONE row class the band
# could never re-scope — the machine's lean frozen as if it were his hand.
check("the band's scope-later door is gated on scope_source, never on scope",
      re.search(r'verb: "scope"', MJS_CODE) is not None
      and re.search(r"function scopeRow\(row, scope\)", MJS_CODE) is not None
      and re.search(r'const open = live && \(!r\.scope \|\| !src \|\| src === "default"'
                    r'\s*\|\| src === "inferred"\);', MJS_CODE) is not None
      and re.search(r"if \(!r\.scope && r\.state !== \"declined\"\)", MJS_CODE) is None
      and re.search(r"row\.scope = \(res && res\.scope\) \|\| scope", MJS_CODE) is not None)
check("a chosen altitude reads settled and still offers the door on focus",
      'scopeRowEl.dataset.settled = "1"' in MJS_CODE
      and '.dep-scopes[data-settled="1"] { display: none; }' in HTML
      and ".dep:focus-within .dep-scopes[data-settled=\"1\"] { display: flex; }" in HTML)
# the pre-Enter line and the banked row are ONE truth: a rewrite with no digit does not
# bank unscoped (the door defaults it), so the routing line must branch on the shape.
check("the routing line names the shape's ACTUAL altitude, not one word for both",
      re.search(r"function routeLine\(\).{0,1400}?shapeOf\(\) !== \"comment\"",
                MJS_CODE, re.S) is not None
      and 'const DOOR_DEFAULT_SCOPE = "sentence"' in MJS_CODE)
# the no-motion law: dwell accrues on the timer, the TINTS never repaint on it.
tick = re.search(r"setInterval\(\(\) => \{.*?\}, DWELL_TICK_MS\)", MJS_CODE, re.S)
check("coverage never repaints on a timer (scroll-idle + section change only)",
      bool(tick) and "paintCoverage" not in tick.group(0)
      and re.search(r"function onIdle\(\)[^}]*paintCoverage\(\)", MJS_CODE, re.S) is not None
      and re.search(r"function updateCurrent\(\).*?paintCoverage\(\)",
                    MJS_CODE, re.S) is not None)
# click-and-type (usability contract clause 1): the canvas is an editor. The islands are
# sealed atomic on every render path, a click on one opens ITS source in place (the cite's
# resolved entry riding the flip note), the diff is pristine-coordinate prefix/suffix
# (never a re-serialization), and the splice rides spliceOf — the one splice authority.
check("every render path seals islands and derives editability (one place)",
      re.search(r"function renderBlockBody\(b, host\) \{\s*renderBlockBodyInner\(b, host\);"
                r"\s*sealIslands\(host\);\s*setEditable\(b, host\);", MJS_CODE) is not None)
check("a typed edit diffs the pristine snapshot and splices through rewritePayload",
      re.search(r"function commitEdit\(why\).*?anchorFromPristine\(b, was, start, end\)"
                r".*?rewritePayload\(a, typed, \"\"\)", MJS_CODE, re.S) is not None
      and re.search(r"payload\.source = \"click-type\"", MJS_CODE) is not None)
check("an island deletion is refused in words, never absorbed",
      re.search(r"rangeTouchesIsland\(r, host\)[\s\S]{0,200}?ev\.preventDefault\(\)",
                MJS_CODE) is not None)
check("a citation island opens ITS source with the resolved entry named",
      re.search(r"islandSource\(wrap, k\)", MJS_CODE) is not None
      and re.search(r"resolves to no entry in the built bibliography", MJS_CODE) is not None)
check("an unapplied typed edit re-renders the source's truth (no phantom face)",
      re.search(r"else if \(b\.bodyEl && F\.blockId !== b\.id\) \{[\s\S]{0,400}?"
                r"renderBlockBody\(b, b\.bodyEl\);", MJS_CODE) is not None)
check("every key in the map is a key the module handles",
      all(f'>{k}<' in HTML or f"<dt>{k}</dt>" in HTML for k in ("0", "s", "u", "n", "p",
                                                                "o", "b", "g", "l", "f")))

# ── 6 · THE REGISTER LAW over every user-facing string ───────────────────────────────────
BANNED = re.compile(r"\b(oops|whoops|sorry|please try again|something went wrong|"
                    r"successfully|awesome|great|magic|seamless|effortless|simply|just "
                    r"click|powerful|leverage|unlock|delight)\b", re.I)
strings = re.findall(r'"((?:[^"\\]|\\.){12,})"', MJS_CODE)
offenders = sorted({s[:70] for s in strings if BANNED.search(s)})
check("no sales / apology register in any interface string", not offenders, str(offenders[:3]))
html_text = re.sub(r"<(script|style)\b.*?</\1>", " ", HTML, flags=re.S)
html_text = re.sub(r"<[^>]+>", " ", html_text)
check("no sales / apology register in the page's own copy",
      not BANNED.search(html_text), str(BANNED.findall(html_text)[:3]))
check("the fidelity honesty is stated on the surface",
      "content-faithful" in MJS and "geometry face" in MJS)
check("every refusal names what was NOT written",
      MJS.count("REFUSED") >= 4 and "nothing was banked" in MJS)

# ── 7 · THE CLEAN ROOM ───────────────────────────────────────────────────────────────────
imports = re.findall(r'^import .*?from "([^"]+)"', MJS, re.M) + \
          re.findall(r'import\("([^"]+)"\)', MJS)
allowed = {"/shared/store.mjs", "/shared/pdfjs/pdf.min.mjs", "PDFJS_SRC"}
check("import allowlist holds", set(imports) <= allowed, str(sorted(set(imports))))
# every /shared/… path the surface can actually LOAD: the module's own url constants,
# every src= in the page and every <link href=, and the dynamic import's target.
#
# AN ANCHOR'S href IS NOT A LOAD. The clean room governs what this surface IMPORTS, never
# what it LINKS to (his call 2026-08-10: integration, not orphanhood) — the named return
# door to the artefact surface is a plain <a>, and reading it as a loadable asset would
# make the allowlist forbid the one thing the door exists to be.
# a /shared/ string carrying a query is a DATA DOOR (store.fetchJSON on shared_ui's
# payload routes — /shared/plan for the joins), not a loadable asset: assets never
# carry queries, and the clean room governs imports, never HTTP reads.
loadable = {u for u in re.findall(r'"(/shared/[^"]+)"', MJS) if "?" not in u} \
    | set(re.findall(r'\ssrc="([^"]+)"', HTML)) \
    | set(re.findall(r'<link\b[^>]*\shref="([^"]+)"', HTML))
allowed_loads = {"/shared/store.mjs", "/shared/pdfjs/pdf.min.mjs",
                 "/shared/pdfjs/pdf.worker.min.mjs", "/shared/katex/katex.min.js",
                 "/shared/katex/katex.min.css", "/shared/walk.mjs",
                 "/shared/fonts/lora-var.woff2", "/shared/fonts/outfit-var.woff2"}
check("every loadable asset is on the allowlist",
      loadable <= allowed_loads, str(sorted(loadable - allowed_loads)))
# the forbidden modules must not appear in any LOAD position (naming them in a comment
# that explains the clean room is not a reference).
code = re.sub(r"//[^\n]*", "", MJS)
code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
page = re.sub(r"<!--.*?-->", "", HTML, flags=re.S)
page = re.sub(r"/\*.*?\*/", "", page, flags=re.S)      # the <style> block's own comments
for forbidden in ("engine.mjs", "shell.js", "inspector.js", "hymn.css", "-panes.mjs"):
    check(f"forbidden module never loaded: {forbidden}",
          forbidden not in code and forbidden not in page)
check("the page pulls no stylesheet but the vendored KaTeX",
      HTML.count("<link") == 0 and "KATEX_CSS" in MJS)
# THE DOORS ARE LINKS, AND THEY ARE NAMED. No anchor on this page hardcodes its target:
# the href is set from the model (one source for a surface link, the rule that keeps the
# nav from having two), and every anchor carries visible words rather than an icon.
anchors = re.findall(r"<a\b[^>]*>(.*?)</a>", HTML, re.S)
check("every anchor is named in words, and none hardcodes its target",
      bool(anchors)
      and all(re.sub(r"<[^>]+>|\s", "", a) for a in anchors)
      and not re.search(r'<a\b[^>]*\shref=', HTML), str(anchors))
check("the walk carries the named return door to the artefact surface",
      'id="back-door"' in HTML and ">artefact surface</a>" in HTML
      and re.search(r'backDoor\.href = S\.corpus \? "/artefact\?corpus="', MJS_CODE)
      is not None
      and re.search(r"function wireControls\(\)\s*\{\s*paintBackDoor\(\);", MJS_CODE)
      is not None)

# ── 8 · THE NEW MECHANISMS THIS ROUND LANDS ──────────────────────────────────────────────
# the piecewise-exact locator: the door's piece offsets, the renderer's measured spans, and
# the one place the two are inverted — wired into BOTH the pre-Enter verdict and the splice.
check("the piece map is built by the renderer and inverted in one place",
      MJS_CODE.count("function renderPiecesMapped(") == 1
      and MJS_CODE.count("function pieceSpanOf(") == 1
      and MJS_CODE.count("function pieceLocate(") == 1
      and re.search(r"b\.pieceMap = usableMap\(map\) \? map : null", MJS_CODE) is not None
      and re.search(r"function spliceOf\(a, after\).{0,600}?const pl = pieceLocate\(a\)",
                    MJS_CODE, re.S) is not None
      and re.search(r"function spliceState\(a\)\s*\{\s*const pl = pieceLocate\(a\)",
                    MJS_CODE, re.S) is not None)
check("a payload with no piece offsets falls back, never half-maps",
      re.search(r"function usableMap\(map\).{0,300}?Number\.isFinite\(m\.oStart\)",
                MJS_CODE, re.S) is not None)
check("rendered math refuses in words, and says where to edit it instead",
      '"in-math"' in MJS_CODE and "not addressable as prose" in MJS
      and "press `s` at the block" in MJS.lower())
# the list grammar, and the honesty about what stays raw
check("lists render as lists and tables stay raw",
      'if (kind === "list")' in MJS_CODE
      and MJS_CODE.count("function renderListInto(") == 1
      and "ul.lst, ol.lst {" in HTML)
# the scope-mix line: one plain line, glanceable, never interactive, bounded
check("the scope-mix line is one bounded, non-interactive line",
      MJS_CODE.count("function paintScopeMix(") == 1
      and re.search(r"function renderBand\(\).{0,9000}?paintScopeMix\(\);",
                    MJS_CODE, re.S) is not None
      and re.search(r"#band-mix \{[^}]*white-space: nowrap", HTML, re.S) is not None
      and re.search(r"#band-mix[^{]*\{[^}]*text-overflow: ellipsis", HTML, re.S) is not None
      and "bandMix.addEventListener" not in MJS_CODE)
# the three gestureless scopes: frozen rules keyed on the gesture, marked, never selected
check("the three gestureless scopes ride frozen grade rules, marked not selected",
      MJS_CODE.count("const GRADE_RULES = Object.freeze([") == 1
      and MJS_CODE.count("function gradeRuleFor(") == 1
      and re.search(r'const RULE_SET_ID = "walk-rules-2026-08-10-r2"', MJS_CODE) is not None
      and re.search(r"function suggestScope\(hay, grade, shape\)", MJS_CODE) is not None
      and re.search(r'C\.scope = C\.suggested', MJS_CODE) is None)   # never pre-selected
check("the ? map names where each of the six scopes naturally lives",
      all(w in HTML for w in ("where each", "<b>sentence</b>", "<b>structure</b>",
                              "<b>voice</b>", "<b>artefact</b>", "<b>meta</b>",
                              "<b>delivery</b>")))
# the root's own prose, and the note that names what was skipped
PY = (SRC / "manuscript" / "walk.py").read_text(encoding="utf-8")
check("the root's own content is emitted, or the payload names what was skipped",
      "def root_content(" in PY and '"root_note"' in PY
      and "def list_items(" in PY and "_LIST_ENVS" in PY
      and re.search(r'"o_start": base \+ buf_at', PY) is not None)

print()
print("audit verdict:", "GREEN — every check above passed" if not fail
      else f"RED — {fail} check(s) failed")
raise SystemExit(1 if fail else 0)
