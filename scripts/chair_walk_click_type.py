"""The machine chair for GESTURE 1 — click-and-type (usability contract, clause 1).

Drives a real headless browser through the gesture exactly as his hands would: click into
a paragraph, type, watch it bank through the rewrite door; Esc reverts; islands refuse
deletion and open their source on click; a pause banks without any key. Every verdict
names the run that produced it, and the run happens on a DISPOSABLE GROUND — a sparse git
worktree holding src/ + the corpus — so no splice and no banked row ever touches the real
tree. The worktree is removed at the end (``--keep`` preserves it for reading).

Usage:  python scripts/chair_walk_click_type.py [--corpus paper_roland_qrc] [--keep]
Exit:   0 every check passed · 1 any check failed · 3 REFUSED TO GRADE (no browser, or
        the ground scanner never came up — nothing measured, nothing written)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_probe import REFUSAL_EXIT, port_open, refusal_line  # noqa: E402

REPO = Path(__file__).resolve().parents[1]


class GroundAbsent(RuntimeError):
    """The disposable ground's own scanner never answered. Not a failed check —
    an absent instrument. Carries the reason so the refusal can name it."""
VIEWPORTS = [(1280, 900), (1536, 960)]
PORT = 8799
SPARSE = ["src", "corpus_friction", "registry_projects.json", "corpus/corpus.bib"]

VERDICTS: list[dict] = []


def caret_into(page, bid: str, offset: int = 5) -> None:
    """Place the caret INSIDE a block's prose (never on an island) and focus the host —
    an element-center click can land on rendered math once the layout has shifted, which
    opens the flip instead of editing (measured at 1280x900, 2026-08-11)."""
    page.evaluate(
        """([id, off]) => { const host = document.querySelector(
               `[data-block=\"${CSS.escape(id)}\"] .blk-body[contenteditable=true]`);
             if (!host) return;
             const w = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
             let t; while ((t = w.nextNode())) if (t.nodeValue.trim().length > off + 2) break;
             if (!t) return;
             const r = document.createRange();
             r.setStart(t, off); r.collapse(true);
             const s = window.getSelection();
             s.removeAllRanges(); s.addRange(r); host.focus(); }""", [bid, offset])


def check(name: str, ok: bool, evidence: str) -> None:
    VERDICTS.append({"check": name, "verdict": "PASS" if ok else "FAIL",
                     "evidence": evidence})
    print(("PASS  " if ok else "FAIL  ") + name + "  — " + evidence)


def _chrome_path() -> str | None:
    for c in ("/opt/pw-browsers/chromium",):
        p = Path(c)
        if p.is_file():
            return str(p)
        if p.is_dir():
            hits = sorted(p.glob("**/chrome")) + sorted(p.glob("**/headless_shell"))
            if hits:
                return str(hits[0])
    for c in ("/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"):
        if Path(c).is_file():
            return c
    return None


def make_ground(corpus: str, keep_dir: Path) -> Path:
    """A sparse worktree of HEAD: src + the corpus + the registry — the disposable ground."""
    ground = keep_dir / "click_type_ground"
    if ground.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(ground)],
                       cwd=REPO, capture_output=True)
        shutil.rmtree(ground, ignore_errors=True)
    subprocess.run(["git", "worktree", "add", "--no-checkout", "--detach",
                    str(ground), "HEAD"], cwd=REPO, check=True, capture_output=True)
    subprocess.run(["git", "sparse-checkout", "set", "--no-cone", *SPARSE, corpus],
                   cwd=ground, check=True, capture_output=True)
    subprocess.run(["git", "checkout"], cwd=ground, check=True, capture_output=True)
    # the chair grades what his reload will serve: the WORKING TREE's interaction layer
    # rides on top of the HEAD ground (the substrate beneath is identical at HEAD).
    for rel in ("src/laplace/web/walk.html", "src/laplace/manuscript/walk.py",
                "src/laplace/web/static_shared/walk.mjs"):
        src_f = REPO / rel
        if src_f.is_file():
            dst = ground / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_f, dst)
    return ground


def drop_ground(ground: Path) -> None:
    subprocess.run(["git", "worktree", "remove", "--force", str(ground)],
                   cwd=REPO, capture_output=True)
    shutil.rmtree(ground, ignore_errors=True)
    subprocess.run(["git", "worktree", "prune"], cwd=REPO, capture_output=True)


def start_scanner(ground: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ground / "src")
    env.pop("LAPLACE_WALK_ONLY", None)
    env.pop("LAPLACE_WALK_TOKEN", None)
    # THE PORT MUST BE FREE FIRST. Something else already holding PORT means this run
    # would drive a stranger's server (or the scanner would die on bind and the wait
    # below would spend its whole budget on a corpse) — refuse before spawning.
    if port_open("127.0.0.1", PORT):
        raise GroundAbsent(
            f"127.0.0.1:{PORT} is already in use, so the disposable ground's own "
            "scanner cannot bind it; this chair only ever grades ITS OWN ground")
    proc = subprocess.Popen([sys.executable, "-m", "laplace.web.scanner",
                             "--port", str(PORT)],
                            cwd=ground, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # A SHORT BOUNDED WAIT THAT WATCHES THE CHILD. The old loop slept its full 30s even
    # when the scanner had already exited (a missing dep, a bad port) — half a minute
    # spent waiting on a process that was never coming back. Now the child's own death
    # ends the wait immediately, and the budget only bounds a slow-but-alive boot.
    deadline = time.time() + 20
    while time.time() < deadline:
        if proc.poll() is not None:
            raise GroundAbsent(
                f"the ground scanner exited immediately (rc={proc.returncode}) — "
                f"`{sys.executable} -m laplace.web.scanner` will not run from the ground")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/corpus/list", timeout=2)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise GroundAbsent("the ground scanner did not answer /corpus/list inside 20s")


def drive(page, corpus: str, ground: Path, shots: Path, tag: str) -> None:
    page.goto(f"http://127.0.0.1:{PORT}/walk?corpus={corpus}&actor=chair-g1",
              wait_until="domcontentloaded")
    page.wait_for_function("() => window.walk && window.walk.ready()", timeout=30000)

    # ── the affordance exists: paragraphs are editors ────────────────────────────────
    n_editable = page.evaluate(
        "() => document.querySelectorAll('.blk[data-kind=para] "
        ".blk-body[contenteditable=true]').length")
    check(f"[{tag}] paragraphs are editable by looking (contenteditable hosts)",
          n_editable >= 5, f"{n_editable} para hosts carry contenteditable=true")

    # a paragraph with plain prose to type into (its host text is long enough to click)
    blk_id = page.evaluate(
        """() => { for (const b of window.walk.blocks()) {
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (!el || el.dataset.kind !== 'para') continue;
             const host = el.querySelector('.blk-body[contenteditable=true]');
             if (host && host.textContent.length > 80) return b.id; }
           return null; }""")
    check(f"[{tag}] a typable paragraph exists", bool(blk_id), f"block {blk_id}")
    if not blk_id:
        return

    sel = f'[data-block="{blk_id}"] .blk-body'
    page.evaluate(
        "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
        ".scrollIntoView({block: 'center'})", blk_id)

    # ── click-and-type, committed by Ctrl-S ──────────────────────────────────────────
    marker = f"chairtyped{tag}"
    page.click(sel)
    card = page.evaluate(
        "() => { const c = document.getElementById('edit-card');"
        " return c && !c.hidden ? c.querySelector('.ec-src').textContent : null; }")
    check(f"[{tag}] the caret summons the card with the source span named",
          bool(card) and ".tex" in card, f"card src line: '{card}'")
    page.keyboard.press("End")
    page.keyboard.type(" " + marker)
    dirty = page.evaluate("() => window.walk.editState()")
    check(f"[{tag}] typing marks the edit in flight (card + state)",
          dirty["block"] == blk_id and dirty["dirty"] is True
          and page.evaluate("() => { const c = document.getElementById('edit-card');"
                            " return c && !c.hidden; }"),
          f"editState={dirty} card visible")
    # the altitude, chosen AT the card: click the voice chip, then bank
    page.click('#edit-card .ec-chip[data-scope="voice"]')
    chosen = page.evaluate("() => window.walk.editState()")
    check(f"[{tag}] a card chip sets the pending edit's altitude",
          chosen.get("scope") == "voice", f"editState.scope={chosen.get('scope')}")
    page.keyboard.press("Control+s")
    page.wait_for_function(
        "() => window.walk.deposits().length >= 1 && !window.walk.editState().dirty",
        timeout=15000)
    dep = page.evaluate("() => window.walk.deposits()[0]")
    check(f"[{tag}] Ctrl-S banks a rewrite row with the receipt in the band",
          dep["kind"] == "rewrite" and dep["applied"] is True and dep["by"] == "chair-g1",
          f"row {dep['id']} applied={dep['applied']} by={dep['by']}")
    check(f"[{tag}] the banked row carries the card-chosen altitude",
          dep.get("scope") == "voice" and dep.get("scope_source") == "chosen",
          f"row scope={dep.get('scope')} source={dep.get('scope_source')}")
    card_after = page.evaluate(
        "() => { const c = document.getElementById('edit-card');"
        " return c && !c.hidden ? c.querySelector('.ec-status').textContent : null; }")
    check(f"[{tag}] the receipt is said on the card, at the point of the edit",
          bool(card_after) and "banked" in card_after, f"card status: '{card_after}'")
    page.wait_for_function(
        f"() => {{ const el = document.querySelector('[data-block=\"{blk_id}\"]');"
        f" return el && el.textContent.includes('{marker}'); }}", timeout=15000)
    # the row's `file` is the fragment path as the door resolves it (tex-root relative);
    # find it on the ground by direct path first, else by name under the corpus tree.
    cands = [ground / dep["file"], ground / corpus / dep["file"]]
    if not any(c.is_file() for c in cands):
        cands = sorted((ground / corpus).rglob(Path(dep["file"]).name))
    hit = next((c for c in cands if c.is_file()
                and marker in c.read_text(encoding="utf-8", errors="replace")), None)
    check(f"[{tag}] the splice is byte-real on the ground's source file",
          hit is not None,
          f"'{marker}' in {hit.relative_to(ground) if hit else dep['file'] + ' (no file matched)'}")
    page.screenshot(path=str(shots / f"{tag}-typed-banked.png"))

    # ── Esc reverts, nothing banks ───────────────────────────────────────────────────
    before = page.evaluate("() => window.walk.deposits().length")
    blk2 = page.evaluate(
        """(skip) => { for (const b of window.walk.blocks()) {
             if (b.id === skip) continue;
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (!el || el.dataset.kind !== 'para') continue;
             const host = el.querySelector('.blk-body[contenteditable=true]');
             if (host && host.textContent.length > 80) return b.id; }
           return null; }""", blk_id)
    sel2 = f'[data-block="{blk2}"] .blk-body'
    page.evaluate(
        "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
        ".scrollIntoView({block: 'center'})", blk2)
    was_text = page.evaluate(f"() => document.querySelector('{sel2}').textContent")
    page.click(sel2)
    page.keyboard.press("End")
    page.keyboard.type(" discardme")
    page.keyboard.press("Escape")
    now_text = page.evaluate(f"() => document.querySelector('{sel2}').textContent")
    after = page.evaluate("() => window.walk.deposits().length")
    st = page.evaluate("() => window.walk.editState()")
    check(f"[{tag}] Esc reverts the paragraph and banks nothing",
          now_text == was_text and after == before and not st["block"],
          f"text restored={now_text == was_text} deposits {before}->{after}")

    # ── islands are atomic: a deletion across one is refused ─────────────────────────
    isl = page.evaluate(
        """() => { for (const b of window.walk.blocks()) {
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (!el || el.dataset.kind !== 'para') continue;
             const host = el.querySelector('.blk-body[contenteditable=true]');
             if (!host) continue;
             const n = host.querySelector('.mathq, .cite-wrap, .ref');
             if (n) return { id: b.id, kind: n.className.split(' ')[0] }; }
           return null; }""")
    if isl:
        n_before = page.evaluate(
            f"""() => document.querySelector('[data-block="{isl['id']}"] .blk-body')
                  .querySelectorAll('[contenteditable=false]').length""")
        deps_before = page.evaluate("() => window.walk.deposits().length")
        page.evaluate(
            f"""() => {{ const host = document.querySelector(
                   '[data-block="{isl['id']}"] .blk-body');
                 const n = host.querySelector('.mathq, .cite-wrap, .ref');
                 const r = document.createRange();
                 r.setStartBefore(n); r.setEndAfter(n);
                 const s = window.getSelection();
                 s.removeAllRanges(); s.addRange(r); host.focus(); }}""")
        page.keyboard.press("Backspace")
        n_after = page.evaluate(
            f"""() => document.querySelector('[data-block="{isl['id']}"] .blk-body')
                  .querySelectorAll('[contenteditable=false]').length""")
        chip = page.evaluate(
            "() => { const c = document.getElementById('edit-card');"
            " return c && !c.hidden ? c.querySelector('.ec-status').textContent : ''; }")
        deps_after = page.evaluate("() => window.walk.deposits().length")
        check(f"[{tag}] deleting across an island is refused in words",
              n_after == n_before and "island" in chip and deps_after == deps_before,
              f"{isl['kind']} islands {n_before}->{n_after}; chip: '{chip[:60]}'")
        page.keyboard.press("Escape")   # drop any armed selection state
    else:
        check(f"[{tag}] deleting across an island is refused in words", False,
              "no para block carries an island on this corpus — nothing was graded")

    # ── clicking an island opens ITS source in place, span selected ──────────────────
    m = page.evaluate(
        """() => { for (const b of window.walk.blocks()) {
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (!el || el.dataset.kind !== 'para') continue;
             const host = el.querySelector('.blk-body[contenteditable=true]');
             if (host && host.querySelector('.mathq')) return b.id; }
           return null; }""")
    if m:
        page.evaluate(
            "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
            ".scrollIntoView({block: 'center'})", m)
        page.evaluate("() => window.getSelection().removeAllRanges()")
        page.click(f'[data-block="{m}"] .blk-body .mathq')
        page.wait_for_function("() => window.walk.flipState().open", timeout=8000)
        span = page.evaluate(
            "() => { const ta = document.querySelector('.flip textarea');"
            " return ta ? [ta.selectionStart, ta.selectionEnd] : null; }")
        check(f"[{tag}] a math island's click opens ITS source with the span selected",
              bool(span) and span[1] > span[0],
              f"flip open on {m}, textarea selection {span}")
        page.keyboard.press("Escape")
    else:
        check(f"[{tag}] a math island's click opens ITS source with the span selected",
              False, "no math island found in any editable paragraph")

    # ── the pause banks NOTHING (his ruling 2026-08-11: hesitation is not consent —
    #    "I like to work and rework and don't want you to look through my
    #    intermediates"). Typing then pausing 4s leaves the edit parked and dirty;
    #    only Ctrl-S / Shift-Enter / blur bank. ─────────────────────────────────────────
    deps_before = page.evaluate("() => window.walk.deposits().length")
    page.evaluate(
        "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
        ".scrollIntoView({block: 'center'})", blk_id)
    page.click(sel)
    page.keyboard.press("End")
    page.keyboard.type(" parked" + tag)
    page.wait_for_timeout(4000)
    deps_now = page.evaluate("() => window.walk.deposits().length")
    st_now = page.evaluate("() => window.walk.editState()")
    check(f"[{tag}] a 4s typing pause banks NOTHING (the edit stays parked, dirty)",
          deps_now == deps_before and st_now["dirty"] is True
          and st_now["block"] == blk_id,
          f"deposits {deps_before}->{deps_now}; editState={st_now}")
    page.keyboard.press("Control+s")   # bank the parked edit so the ground stays settled
    page.wait_for_function(
        f"() => window.walk.deposits().length >= {deps_before} + 1"
        " && !window.walk.editState().dirty", timeout=15000)
    dep2 = page.evaluate("() => window.walk.deposits()[0]")
    # the row's `after` can re-express an insertion adjacent to repeated text (diff
    # ambiguity: inserting " parked<tag>" after "…<tag>" reads equally as inserting
    # "<tag> parked" one repeat earlier) — the byte-real source is the truth to assert.
    d2cands = sorted((ground / corpus).rglob(Path(dep2["file"]).name))
    d2_ok = any(("parked" + tag) in c.read_text(encoding="utf-8", errors="replace")
                for c in d2cands if c.is_file())
    check(f"[{tag}] Ctrl-S banks the parked edit it held through the pause",
          dep2["applied"] is True and d2_ok,
          f"row {dep2['id']} applied={dep2['applied']}; 'parked{tag}' on disk: {d2_ok}")

    # ── Enter splits the paragraph at the caret (his chair, 2026-08-11: "I can't
    #    carriage return or insert a new paragraph") — the split banks at once and the
    #    applied splice re-renders as two blocks through the shape-change path ─────────
    # settle the previous bank's re-render first: commitEdit's reloadBlock is async and
    # the chair types faster than hands — a split fired inside the reload window reads a
    # stale line span and banks PENDING (measured 2026-08-11 remote, both viewports; the
    # window itself is banked as an audit item in DESIGN_2026-08-11_the-text-editor-walk).
    page.evaluate("id => window.walk.reloadBlock(id)", blk_id)
    deps_s = page.evaluate("() => window.walk.deposits().length")
    blocks_s = page.evaluate("() => window.walk.blocks().length")
    page.click(sel)
    page.keyboard.press("Home")
    for _ in range(8):
        page.keyboard.press("ArrowRight")
    page.keyboard.press("Enter")
    page.wait_for_function(
        f"() => window.walk.deposits().length === {deps_s} + 1", timeout=10000)
    srow = page.evaluate("() => window.walk.deposits()[0]")
    check(f"[{tag}] Enter splits the paragraph and banks the split at once",
          srow["applied"] is True and "\n\n" in (srow.get("after") or ""),
          f"row {srow['id']} applied={srow['applied']}")
    try:
        page.wait_for_function(
            f"() => window.walk.blocks().length === {blocks_s} + 1", timeout=10000)
        check(f"[{tag}] the applied split re-renders as two blocks",
              True, f"blocks {blocks_s} -> {blocks_s + 1}")
    except Exception:
        n_now = page.evaluate("() => window.walk.blocks().length")
        check(f"[{tag}] the applied split re-renders as two blocks",
              False, f"blocks stayed {n_now} (expected {blocks_s + 1})")

    # ── the JOIN is the split's inverse (his chair, 2026-08-11: "enter works, but
    #    backspace doesn't. Should you not think of this like... a text editor?").
    #    Backspace at a paragraph's start joins it onto the previous block through the
    #    same rewrite door. The pair under the caret is the pair the split just made,
    #    so the separator is a fresh "\n\n" and the join must APPLY, not stand PENDING
    #    (the PENDING-honest branch is for odd separators, which this pair cannot be).
    if blocks_s + 1 == page.evaluate("() => window.walk.blocks().length"):
        # the split's halves carry a re-minted id chain (X and X-2): that names the pair
        # exactly — a length heuristic does not (Home is the VISUAL line start, so the
        # split point is mid-paragraph and neither half is short).
        pair = page.evaluate(
            """() => { const bs = window.walk.blocks();
                 for (let i = 1; i < bs.length; i++) {
                   const a = bs[i-1], b = bs[i];
                   if ((a.kind || 'para') !== 'para' || (b.kind || 'para') !== 'para')
                     continue;
                   if (!b.id.startsWith(a.id + '-')) continue;
                   const ea = document.querySelector(`[data-block=\"${CSS.escape(a.id)}\"] .blk-body[contenteditable=true]`);
                   const eb = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"] .blk-body[contenteditable=true]`);
                   if (ea && eb) return b.id; }
               return null; }""")
        if pair:
            deps_j = page.evaluate("() => window.walk.deposits().length")
            page.evaluate(
                "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
                ".scrollIntoView({block: 'center'})", pair)
            page.click(f'[data-block="{pair}"] .blk-body')
            page.evaluate(
                f"""() => {{ const host = document.querySelector(
                       '[data-block="{pair}"] .blk-body');
                     const w = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
                     const t = w.nextNode();
                     const r = document.createRange();
                     r.setStart(t, 0); r.collapse(true);
                     const s = window.getSelection();
                     s.removeAllRanges(); s.addRange(r); host.focus(); }}""")
            page.keyboard.press("Backspace")
            page.wait_for_function(
                f"() => window.walk.deposits().length === {deps_j} + 1", timeout=15000)
            jrow = page.evaluate("() => window.walk.deposits()[0]")
            check(f"[{tag}] Backspace at the paragraph's start joins it onto the previous "
                  f"block (a rewrite row, applied)",
                  jrow["kind"] == "rewrite" and jrow["applied"] is True,
                  f"row {jrow['id']} kind={jrow['kind']} applied={jrow['applied']}")
            try:
                page.wait_for_function(
                    f"() => window.walk.blocks().length === {blocks_s}", timeout=10000)
                check(f"[{tag}] the applied join re-renders as one paragraph again",
                      True, f"blocks {blocks_s + 1} -> {blocks_s}")
            except Exception:
                n_now = page.evaluate("() => window.walk.blocks().length")
                check(f"[{tag}] the applied join re-renders as one paragraph again",
                      False, f"blocks stayed {n_now} (expected {blocks_s})")
        else:
            dump = page.evaluate(
                """() => window.walk.blocks().slice(0, 6).map((b) => {
                     const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
                     const host = el ? el.querySelector('.blk-body[contenteditable=true]') : null;
                     return b.id + '/' + b.kind + '/' + (host ? host.textContent.trim().length : -1); })""")
            check(f"[{tag}] Backspace at the paragraph's start joins it onto the previous "
                  f"block (a rewrite row, applied)", False,
                  "the split's stub pair was not found after the re-adopt — nothing was "
                  f"graded; head of doc: {dump}")
    else:
        check(f"[{tag}] Backspace at the paragraph's start joins it onto the previous "
              f"block (a rewrite row, applied)", False,
              "the split did not leave the expected pair; the join was not graded")

    # the split/join re-adopted the whole doc and block ids re-minted (the shape-change
    # path): every check below re-resolves its block — the pre-split id is stale by
    # design, and driving it crashed the 2026-08-11 run (setStart on a null node).
    blk_id = page.evaluate(
        """() => { for (const b of window.walk.blocks()) {
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (!el || el.dataset.kind !== 'para') continue;
             const host = el.querySelector('.blk-body[contenteditable=true]');
             if (host && host.textContent.length > 80) return b.id; }
           return null; }""")
    check(f"[{tag}] a typable paragraph survives the split re-adopt", bool(blk_id),
          f"block {blk_id}")
    if not blk_id:
        return
    sel = f'[data-block="{blk_id}"] .blk-body'

    # ── the card's note: a comment at the point; beside an edit, ONE compound row ────
    deps0 = page.evaluate("() => window.walk.deposits().length")
    page.click(sel)
    page.click("#edit-card .ec-note")
    page.keyboard.type("chair note " + tag)
    page.keyboard.press("Enter")
    page.wait_for_function(
        f"() => window.walk.deposits().length === {deps0} + 1", timeout=10000)
    crow = page.evaluate("() => window.walk.deposits()[0]")
    check(f"[{tag}] a note alone banks a comment from the card",
          crow["kind"] == "comment" and ("chair note " + tag) in crow["comment"],
          f"row {crow['id']} kind={crow['kind']}")
    page.click(sel)
    page.keyboard.press("End")
    page.keyboard.type(" compoundbit" + tag)
    page.click("#edit-card .ec-note")
    page.keyboard.type("why " + tag)
    page.keyboard.press("Enter")
    page.wait_for_function(
        f"() => window.walk.deposits().length === {deps0} + 2", timeout=15000)
    krow = page.evaluate("() => window.walk.deposits()[0]")
    check(f"[{tag}] an edit + a note bank ONE compound row (replacement + rationale)",
          krow["kind"] == "compound" and ("why " + tag) in krow["comment"]
          and ("compoundbit" + tag) in krow["after"] and krow["applied"] is True,
          f"row {krow['id']} kind={krow['kind']} applied={krow['applied']}")

    # ── a plain-text section title is click-and-type too ─────────────────────────────
    head_id = page.evaluate(
        """() => { for (const b of window.walk.blocks()) {
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (!el || el.dataset.kind !== 'head') continue;
             const host = el.querySelector('.blk-body[contenteditable=true]');
             if (host) return b.id; }
           return null; }""")
    if head_id:
        hsel = f'[data-block="{head_id}"] .blk-body'
        page.evaluate(
            "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
            ".scrollIntoView({block: 'center'})", head_id)
        page.click(hsel)
        page.keyboard.press("End")
        page.keyboard.type(" Retitled" + tag)
        page.keyboard.press("Control+s")
        page.wait_for_function(
            f"() => window.walk.deposits().length === {deps0} + 3", timeout=15000)
        hrow = page.evaluate("() => window.walk.deposits()[0]")
        hcands = sorted((ground / corpus).rglob(Path(hrow["file"]).name))
        h_ok = any(("Retitled" + tag) in c.read_text(encoding="utf-8", errors="replace")
                   for c in hcands if c.is_file())
        check(f"[{tag}] a section title edits in place and the splice is byte-real",
              hrow["applied"] is True and h_ok,
              f"row {hrow['id']} applied={hrow['applied']}; title on disk: {h_ok}")
    else:
        check(f"[{tag}] a section title edits in place and the splice is byte-real",
              False, "no plain-text head found editable")

    # ── the asks: refs requested for a passage; a figure tagged for remake ───────────
    page.click(sel)
    page.click("#edit-card .ec-ask")
    page.wait_for_function(
        f"() => window.walk.deposits().length === {deps0} + 4", timeout=10000)
    rrow = page.evaluate("() => window.walk.deposits()[0]")
    check(f"[{tag}] 'request refs' banks a typed request row at delivery",
          rrow["kind"] == "comment" and "request: find supporting references"
          in rrow["comment"] and rrow["scope"] == "delivery",
          f"row {rrow['id']} scope={rrow['scope']}")
    fig_id = page.evaluate(
        """() => { for (const b of window.walk.blocks()) {
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (el && el.dataset.kind === 'figure') return b.id; }
           return null; }""")
    if fig_id:
        page.evaluate(
            "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
            ".scrollIntoView({block: 'center'})", fig_id)
        page.click(f'[data-block="{fig_id}"]')
        page.click("#edit-card .ec-ask")
        page.wait_for_function(
            f"() => window.walk.deposits().length === {deps0} + 5", timeout=10000)
        frow = page.evaluate("() => window.walk.deposits()[0]")
        check(f"[{tag}] a figure tags for remake from its card",
              frow["kind"] == "comment" and "request: remake this figure" in frow["comment"],
              f"row {frow['id']}: '{frow['comment'][:60]}'")
    else:
        check(f"[{tag}] a figure tags for remake from its card", False,
              "no figure block on this corpus")

    # ── where this sits · links ──────────────────────────────────────────────────────
    page.click(sel)
    page.click("#edit-card .ec-where-btn")
    where = page.evaluate(
        "() => { const w = document.querySelector('.ec-where');"
        " return w && !w.hidden ? w.textContent : null; }")
    check(f"[{tag}] the links view names the spine position",
          bool(where) and "sits:" in where and "referenced by:" in where,
          f"view text head: '{(where or '')[:80]}'")

    # ── heads are editable across the corpus (the \label-line shape included) ────────
    n_heads = page.evaluate(
        "() => document.querySelectorAll('.blk[data-kind=head] "
        ".blk-body[contenteditable=true]').length")
    check(f"[{tag}] section titles are editable across the corpus, labels included",
          n_heads >= 5, f"{n_heads} head hosts carry contenteditable=true")

    # ── a selection summons the CARD at the text; the rail stays put ─────────────────
    page.evaluate(
        f"""() => {{ const host = document.querySelector('{sel}');
             const w = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
             let t; while ((t = w.nextNode())) if (t.nodeValue.trim().length > 30) break;
             const r = document.createRange();
             r.setStart(t, 2); r.setEnd(t, 22);
             const s2 = window.getSelection();
             s2.removeAllRanges(); s2.addRange(r); }}""")
    page.dispatch_event("#paper", "mouseup")
    page.wait_for_function(
        "() => { const c = document.getElementById('edit-card');"
        " return c && !c.hidden && c.querySelector('.ec-status')"
        ".textContent.includes('selection held'); }", timeout=8000)
    rail = page.evaluate("() => document.getElementById('walk').dataset.rail")
    check(f"[{tag}] a selection summons the card, not the rail",
          rail == "strip", f"card holds the selection; rail={rail}")
    n0 = page.evaluate("() => window.walk.deposits().length")
    page.click("#edit-card .ec-note")
    page.keyboard.type("on this passage " + tag)
    page.keyboard.press("Enter")
    page.wait_for_function(
        f"() => window.walk.deposits().length === {n0} + 1", timeout=10000)
    srow = page.evaluate("() => window.walk.deposits()[0]")
    check(f"[{tag}] the note banks a comment anchored to the HELD selection",
          srow["kind"] == "comment" and len(srow.get("quote") or "") >= 15,
          f"row {srow['id']} quote='{(srow.get('quote') or '')[:30]}…'")

    # ── a head's ask: suggest a new section (structure altitude) ─────────────────────
    if head_id:
        n0 = page.evaluate("() => window.walk.deposits().length")
        page.evaluate(
            "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
            ".scrollIntoView({block: 'center'})", head_id)
        page.click(f'[data-block="{head_id}"] .blk-body')
        page.click("#edit-card .ec-ask")
        page.wait_for_function(
            f"() => window.walk.deposits().length === {n0} + 1", timeout=10000)
        hrow2 = page.evaluate("() => window.walk.deposits()[0]")
        check(f"[{tag}] a head's card suggests a new section at structure",
              "new section" in hrow2["comment"] and hrow2["scope"] == "structure",
              f"row {hrow2['id']} scope={hrow2['scope']}")
    else:
        check(f"[{tag}] a head's card suggests a new section at structure", False,
              "no editable head found")

    # ── an equation's click shows what uses it, where ────────────────────────────────
    eq_id = page.evaluate(
        """() => { for (const b of window.walk.blocks()) {
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (el && el.dataset.kind === 'equation') return b.id; }
           return null; }""")
    if eq_id:
        page.evaluate(
            "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
            ".scrollIntoView({block: 'center'})", eq_id)
        page.evaluate("() => window.getSelection().removeAllRanges()")
        page.click(f'[data-block="{eq_id}"] .blk-body .mathq')
        page.wait_for_function("() => window.walk.flipState().open", timeout=8000)
        eq_where = page.evaluate(
            "() => { const w = document.querySelector('.ec-where');"
            " const s2 = document.querySelector('.ec-status');"
            " return { view: !!(w && !w.hidden), words: s2 ? s2.textContent : '' }; }")
        check(f"[{tag}] an equation's flip carries its usage on the card",
              eq_where["view"] and ("references" in eq_where["words"]
                                    or "no label" in eq_where["words"]),
              f"links view open={eq_where['view']}; status: '{eq_where['words'][:60]}'")
        page.keyboard.press("Escape")
    else:
        check(f"[{tag}] an equation's flip carries its usage on the card", False,
              "no equation block on this corpus")

    # ── the plan joins ride the links view, or their absence is said ─────────────────
    page.click(sel)
    page.click("#edit-card .ec-where-btn")
    page.wait_for_timeout(800)
    jtext = page.evaluate(
        "() => { const w = document.querySelector('.ec-where');"
        " return w && !w.hidden ? w.textContent : ''; }")
    joined = ("argues here" in jtext or "beat:" in jtext
              or "plan door did not answer" in jtext or "no plan section" in jtext)
    check(f"[{tag}] the conceptric/storyboard joins show, or say why not",
          joined, f"view: '{jtext[:110]}'")
    page.click("#edit-card .ec-where-btn")

    # ── the band claims no width on its own; the mouse has every door ────────────────
    rail = page.evaluate("() => document.getElementById('walk').dataset.rail")
    check(f"[{tag}] a typed bank leaves the band closed (the card is its receipt)",
          rail == "strip", f"rail mode after pause-bank: {rail}")
    page.click("#rail-strip")
    rail = page.evaluate("() => document.getElementById('walk').dataset.rail")
    n_rows = page.evaluate("() => document.querySelectorAll('#band-list .dep').length")
    check(f"[{tag}] the strip opens the band by mouse, rows listed",
          rail == "band" and n_rows >= 2, f"rail={rail} rows={n_rows}")
    page.click("#band-collapse")
    rail = page.evaluate("() => document.getElementById('walk').dataset.rail")
    check(f"[{tag}] the band's visible control collapses it by mouse",
          rail == "strip", f"rail after collapse: {rail}")
    page.click("#rail-strip")
    page.mouse.click(640, 400)   # a return to the paper puts the band away
    rail = page.evaluate("() => document.getElementById('walk').dataset.rail")
    check(f"[{tag}] a click back into the paper puts the band away",
          rail == "strip", f"rail after paper click: {rail}")

    # ══ THE PARKING MODEL (job C, 2026-08-11: edits park per block; NOTHING banks until
    #    his hand says — Ctrl-S banks all standing; blur/block-change park; Esc reverts
    #    the current block; an island click on a dirty block asks) ═════════════════════
    two = page.evaluate(
        """() => { const out = [];
             for (const b of window.walk.blocks()) {
               const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
               if (!el || el.dataset.kind !== 'para') continue;
               const host = el.querySelector('.blk-body[contenteditable=true]');
               if (host && host.textContent.length > 80) out.push(b.id);
               if (out.length === 2) break; }
           return out; }""")
    if len(two) == 2:
        pa, pb = two
        deps_p = page.evaluate("() => window.walk.deposits().length")
        for bid, marker in ((pa, "parkA" + tag), (pb, "parkB" + tag)):
            page.evaluate(
                "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
                ".scrollIntoView({block: 'center'})", bid)
            caret_into(page, bid)
            page.keyboard.type(" " + marker)
        st = page.evaluate("() => window.walk.editState()")
        pa_marked = page.evaluate(
            f"""() => {{ const el = document.querySelector('[data-block="{pa}"]');
                 return el ? el.dataset.parked || '' : null; }}""")
        deps_now = page.evaluate("() => window.walk.deposits().length")
        check(f"[{tag}] a block-change PARKS (amber edge, nothing banks)",
              deps_now == deps_p and pa_marked == "1" and st["parked"] == 2
              and st["block"] == pb and st["dirty"] is True,
              f"deposits {deps_p}->{deps_now}; pa parked='{pa_marked}'; editState={st}")
        strip_txt = page.evaluate(
            "() => { const s = document.getElementById('rail-parked');"
            " return s && !s.hidden ? s.textContent : null; }")
        check(f"[{tag}] the rail strip carries the standing unbanked count",
              strip_txt == "2¶", f"rail-parked: '{strip_txt}'")
        page.screenshot(path=str(shots / f"{tag}-parked.png"))
        was_pb = page.evaluate(
            f"""() => {{ const e = document.querySelector('[data-block="{pb}"] .blk-body');
                 return e ? e.textContent.includes('parkB{tag}') : null; }}""")
        page.keyboard.press("Escape")
        now_pb = page.evaluate(
            f"""() => {{ const e = document.querySelector('[data-block="{pb}"] .blk-body');
                 return e ? e.textContent.includes('parkB{tag}') : null; }}""")
        st2 = page.evaluate("() => window.walk.editState()")
        check(f"[{tag}] Esc reverts ONLY the block under the caret; the park stands",
              was_pb is True and now_pb is False and st2["parked"] == 1
              and st2["parkedIds"] == [pa],
              f"pb marker {was_pb}->{now_pb}; editState={st2}")
        page.keyboard.press("Control+s")
        page.wait_for_function(
            f"() => window.walk.deposits().length === {deps_p} + 1"
            " && window.walk.editState().parked === 0", timeout=15000)
        prow = page.evaluate("() => window.walk.deposits()[0]")
        pcands = sorted((ground / corpus).rglob(Path(prow["file"]).name))
        p_ok = any(("parkA" + tag) in c.read_text(encoding="utf-8", errors="replace")
                   for c in pcands if c.is_file())
        check(f"[{tag}] Ctrl-S banks ALL standing parked blocks, splice byte-real",
              prow["applied"] is True and p_ok,
              f"row {prow['id']} applied={prow['applied']}; parkA on disk: {p_ok}")
    else:
        check(f"[{tag}] a block-change PARKS (amber edge, nothing banks)", False,
              "fewer than two typable paragraphs found — parking was not graded")

    # island click on a DIRTY block PARKS AND OPENS (his friction #3): the words are
    # held, the flip opens on the island's source; closing the flip restores his words
    # onto the face; Esc on the parked block then reverts it (the informed revert).
    isl2 = page.evaluate(
        """() => { for (const b of window.walk.blocks()) {
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (!el || el.dataset.kind !== 'para') continue;
             const host = el.querySelector('.blk-body[contenteditable=true]');
             if (host && host.querySelector('.mathq')) return b.id; }
           return null; }""")
    if isl2:
        deps_i = page.evaluate("() => window.walk.deposits().length")
        page.evaluate(
            "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
            ".scrollIntoView({block: 'center'})", isl2)
        caret_into(page, isl2)
        page.keyboard.type(" ask" + tag)
        page.evaluate("() => window.getSelection().removeAllRanges()")
        page.click(f'[data-block="{isl2}"] .blk-body .mathq')
        try:
            page.wait_for_function("() => window.walk.flipState().open", timeout=8000)
            flip_open = True
        except Exception:
            flip_open = False
        st_i = page.evaluate("() => window.walk.editState()")
        deps_i2 = page.evaluate("() => window.walk.deposits().length")
        check(f"[{tag}] an island click on a dirty block PARKS AND OPENS — no bank",
              flip_open and deps_i2 == deps_i and isl2 in st_i["parkedIds"],
              f"flip={flip_open}; deposits {deps_i}->{deps_i2}; parkedIds={st_i['parkedIds']}")
        page.keyboard.press("Escape")   # close the flip: restoreFace re-places his words
        page.wait_for_timeout(400)
        back = page.evaluate(
            f"""() => {{ const el = document.querySelector('[data-block="{isl2}"]');
                 const host = el ? el.querySelector('.blk-body') : null;
                 return {{ marker: el ? el.dataset.parked || '' : null,
                          face: host ? host.textContent.includes('ask{tag}') : null,
                          flip: window.walk.flipState().open }}; }}""")
        check(f"[{tag}] the flip closes back ONTO the parked words (restoreFace)",
              back["flip"] is False and back["marker"] == "1" and back["face"] is True,
              f"after Escape: {back}")
        page.keyboard.press("Escape")   # Esc on the parked block: the informed revert
        page.wait_for_function(
            "() => window.walk.editState().parked === 0", timeout=8000)
        gone = page.evaluate(
            f"""() => {{ const host = document.querySelector('[data-block="{isl2}"] .blk-body');
                 return host ? host.textContent.includes('ask{tag}') : null; }}""")
        check(f"[{tag}] Esc on a parked block reverts it without typing first",
              gone is False, f"marker still on face: {gone}")
    else:
        check(f"[{tag}] an island click on a dirty block PARKS AND OPENS — no bank",
              False, "no para block carries an island — nothing was graded")

    # a parked face SURVIVES a structural re-adopt elsewhere (split in another block)
    if len(two) == 2:
        pa, pb = two
        deps_s2 = page.evaluate("() => window.walk.deposits().length")
        blocks_s2 = page.evaluate("() => window.walk.blocks().length")
        page.evaluate(
            "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
            ".scrollIntoView({block: 'center'})", pa)
        caret_into(page, pa)
        page.keyboard.type(" parkC" + tag)
        page.evaluate(
            "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
            ".scrollIntoView({block: 'center'})", pb)
        caret_into(page, pb)                            # parks pa (focus moves)
        page.keyboard.press("Enter")                    # split pb: banks + whole re-adopt
        page.wait_for_function(
            f"() => window.walk.deposits().length === {deps_s2} + 1"
            f" && window.walk.blocks().length === {blocks_s2} + 1", timeout=15000)
        held = page.evaluate(
            """() => { const st = window.walk.editState();
                 if (st.parked !== 1) return { parked: st.parked };
                 const id = st.parkedIds[0];
                 const el = document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`);
                 const host = el ? el.querySelector('.blk-body') : null;
                 return { parked: 1, marker: el ? el.dataset.parked || '' : null,
                          face: host ? host.textContent : '' }; }""")
        check(f"[{tag}] a parked face survives a structural re-adopt elsewhere",
              held.get("parked") == 1 and held.get("marker") == "1"
              and ("parkC" + tag) in (held.get("face") or ""),
              f"held={ {k: (v[:40] + '…' if isinstance(v, str) and len(v) > 40 else v) for k, v in held.items()} }")
        page.keyboard.press("Control+s")
        page.wait_for_function(
            f"() => window.walk.deposits().length === {deps_s2} + 2"
            " && window.walk.editState().parked === 0", timeout=15000)
        crow2 = page.evaluate("() => window.walk.deposits()[0]")
        ccands = sorted((ground / corpus).rglob(Path(crow2["file"]).name))
        c_ok = any(("parkC" + tag) in c.read_text(encoding="utf-8", errors="replace")
                   for c in ccands if c.is_file())
        check(f"[{tag}] the survived park then banks byte-real through the door",
              crow2["applied"] is True and c_ok,
              f"row {crow2['id']} applied={crow2['applied']}; parkC on disk: {c_ok}")

    # ══ THE SIX-FRICTION PASS (2026-08-11b: his chair question — "what would my
    #    friction be?" — answered in code, each answer graded) ═══════════════════════════

    # the band's parked rows: each park named with its DELTA and its own bank/revert doors
    fresh2 = page.evaluate(
        """() => { const out = [];
             for (const b of window.walk.blocks()) {
               const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
               if (!el || el.dataset.kind !== 'para') continue;
               const host = el.querySelector('.blk-body[contenteditable=true]');
               if (host && host.textContent.length > 80) out.push(b.id);
               if (out.length === 2) break; }
           return out; }""")
    if len(fresh2) == 2:
        qa, qb = fresh2
        deps_q = page.evaluate("() => window.walk.deposits().length")
        for bid, marker in ((qa, "bankone" + tag), (qb, "keep" + tag)):
            page.evaluate(
                "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
                ".scrollIntoView({block: 'center'})", bid)
            caret_into(page, bid)
            page.keyboard.type(" " + marker)
        page.click("#rail-strip")
        rows_info = page.evaluate(
            """() => { const line = document.getElementById('band-parked');
                 if (!line || line.hidden) return null;
                 const rows = line.querySelectorAll('.pk-row');
                 return { n: rows.length,
                          plus: line.querySelectorAll('.pk-plus').length,
                          banks: line.querySelectorAll('.pk-btn').length }; }""")
        check(f"[{tag}] the band names each park with its delta and its doors",
              bool(rows_info) and rows_info["n"] == 2 and rows_info["plus"] >= 2
              and rows_info["banks"] >= 4,
              f"band-parked rows: {rows_info}")
        page.evaluate(
            "() => { const r = document.querySelector('#band-parked .pk-row');"
            " const b = r ? r.querySelector('.pk-btn') : null; if (b) b.click(); }")
        page.wait_for_function(
            f"() => window.walk.deposits().length === {deps_q} + 1"
            " && window.walk.editState().parked === 1", timeout=15000)
        qrow = page.evaluate("() => window.walk.deposits()[0]")
        st_q = page.evaluate("() => window.walk.editState()")
        check(f"[{tag}] one park banks ALONE from its band row; the other stands",
              qrow["applied"] is True and ("bankone" + tag) in qrow["after"]
              and st_q["parkedIds"] == [qb],
              f"row {qrow['id']} applied={qrow['applied']}; parkedIds={st_q['parkedIds']}")
        page.click("#rail-strip")
        page.evaluate(
            "() => { const r = document.querySelector('#band-parked .pk-row');"
            " const btns = r ? r.querySelectorAll('.pk-btn') : []; "
            " if (btns.length) btns[btns.length - 1].click(); }")
        page.wait_for_function(
            "() => window.walk.editState().parked === 0", timeout=8000)
        kept = page.evaluate(
            f"""() => {{ const host = document.querySelector('[data-block="{qb}"] .blk-body');
                 return host ? host.textContent.includes('keep{tag}') : null; }}""")
        check(f"[{tag}] the other park reverts from ITS band row (face shows the source)",
              kept is False, f"marker on face after revert: {kept}")
    else:
        check(f"[{tag}] the band names each park with its delta and its doors", False,
              "fewer than two typable paragraphs — the band rows were not graded")

    # the CROSS-PARAGRAPH rewrite: select mid-A to mid-B, press a letter — one applied
    # rewrite, the span becomes one paragraph, typing lands where the caret sits
    adj = page.evaluate(
        """() => { const bs = window.walk.blocks();
             for (let i = 1; i < bs.length; i++) {
               const a = bs[i-1], b = bs[i];
               if ((a.kind || 'para') !== 'para' || (b.kind || 'para') !== 'para') continue;
               if (!a.file || a.file !== b.file) continue;
               const ea = document.querySelector(`[data-block=\"${CSS.escape(a.id)}\"] .blk-body[contenteditable=true]`);
               const eb = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"] .blk-body[contenteditable=true]`);
               if (ea && eb && ea.textContent.length > 60 && eb.textContent.length > 60)
                 return [a.id, b.id]; }
           return null; }""")
    if adj:
        xa, xb = adj
        deps_x = page.evaluate("() => window.walk.deposits().length")
        blocks_x = page.evaluate("() => window.walk.blocks().length")
        ok_sel = page.evaluate(
            """([ida, idb]) => {
                 const ha = document.querySelector(`[data-block=\"${CSS.escape(ida)}\"] .blk-body`);
                 const hb = document.querySelector(`[data-block=\"${CSS.escape(idb)}\"] .blk-body`);
                 const wa = document.createTreeWalker(ha, NodeFilter.SHOW_TEXT);
                 let ta; while ((ta = wa.nextNode())) if (ta.nodeValue.trim().length > 30) break;
                 const wb = document.createTreeWalker(hb, NodeFilter.SHOW_TEXT);
                 let tb; while ((tb = wb.nextNode())) if (tb.nodeValue.trim().length > 30) break;
                 if (!ta || !tb) return false;
                 const r = document.createRange();
                 r.setStart(ta, 10); r.setEnd(tb, 10);
                 const s = window.getSelection();
                 s.removeAllRanges(); s.addRange(r);
                 ha.focus();
                 return true; }""", [xa, xb])
        page.keyboard.press("Q")
        page.wait_for_function(
            f"() => window.walk.deposits().length === {deps_x} + 1", timeout=15000)
        xrow = page.evaluate("() => window.walk.deposits()[0]")
        try:
            page.wait_for_function(
                f"() => window.walk.blocks().length === {blocks_x} - 1", timeout=10000)
            merged = True
        except Exception:
            merged = False
        check(f"[{tag}] a selection across paragraphs + a letter rewrites as ONE row",
              ok_sel and xrow["applied"] is True and xrow["after"] == "Q" and merged,
              f"row {xrow['id']} applied={xrow['applied']} after='{xrow['after']}';"
              f" blocks {blocks_x}->{blocks_x - 1 if merged else 'unchanged'}")
    else:
        check(f"[{tag}] a selection across paragraphs + a letter rewrites as ONE row",
              False, "no adjacent same-file paragraph pair — nothing was graded")

    # a MULTI-PARAGRAPH paste splits: the breaks land in the source, banked at once
    pc0 = page.evaluate(
        """() => { for (const b of window.walk.blocks()) {
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (!el || el.dataset.kind !== 'para') continue;
             const host = el.querySelector('.blk-body[contenteditable=true]');
             if (host && host.textContent.length > 80) return b.id; }
           return null; }""")
    if pc0:
        deps_v = page.evaluate("() => window.walk.deposits().length")
        blocks_v = page.evaluate("() => window.walk.blocks().length")
        page.evaluate(
            "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
            ".scrollIntoView({block: 'center'})", pc0)
        caret_into(page, pc0)
        page.evaluate(
            f"""(id) => {{ const host = document.querySelector(
                   '[data-block="{pc0}"] .blk-body');
                 const dt = new DataTransfer();
                 dt.setData('text/plain',
                   'Chair pasted one PASTEA{tag}.\\n\\nChair pasted two PASTEB{tag}.');
                 host.dispatchEvent(new InputEvent('beforeinput',
                   {{ inputType: 'insertFromPaste', bubbles: true, cancelable: true,
                     dataTransfer: dt }})); }}""", pc0)
        page.wait_for_function(
            f"() => window.walk.deposits().length === {deps_v} + 1"
            f" && window.walk.blocks().length === {blocks_v} + 1", timeout=15000)
        vrow = page.evaluate("() => window.walk.deposits()[0]")
        check(f"[{tag}] a two-paragraph paste makes two paragraphs, banked at once",
              vrow["applied"] is True and ("PASTEA" + tag) in vrow["after"],
              f"row {vrow['id']} applied={vrow['applied']}; blocks {blocks_v}->{blocks_v + 1}")
    else:
        check(f"[{tag}] a two-paragraph paste makes two paragraphs, banked at once",
              False, "no typable paragraph found — the paste was not graded")

    # ══ THE SECOND PASS (his ask: "one more pass — what are you still missing?") ═══════

    # notes PARK with their block: a half-written note survives the card moving away,
    # comes back on return, and banks as the comment it always was
    np2 = page.evaluate(
        """() => { const out = [];
             for (const b of window.walk.blocks()) {
               const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
               if (!el || el.dataset.kind !== 'para') continue;
               const host = el.querySelector('.blk-body[contenteditable=true]');
               if (host && host.textContent.length > 80) out.push(b.id);
               if (out.length === 2) break; }
           return out; }""")
    if len(np2) == 2:
        na, nb2 = np2
        deps_n = page.evaluate("() => window.walk.deposits().length")
        caret_into(page, na)
        page.click("#edit-card .ec-note")
        page.keyboard.type("half a thought " + tag)
        caret_into(page, nb2)          # the card moves: the note must park, not die
        st_n = page.evaluate("() => window.walk.editState()")
        note_now = page.evaluate(
            "() => document.querySelector('#edit-card .ec-note').value")
        check(f"[{tag}] a half-written note PARKS with its block when the card moves",
              na in st_n["parkedIds"] and note_now == "",
              f"parkedIds={st_n['parkedIds']}; field now: '{note_now}'")
        caret_into(page, na)           # returning restores the note to the field
        page.keyboard.type("x")        # (typing resumes the block)
        note_back = page.evaluate(
            "() => document.querySelector('#edit-card .ec-note').value")
        check(f"[{tag}] the parked note returns to the field with its block",
              ("half a thought " + tag) in note_back, f"field: '{note_back[:40]}'")
        page.keyboard.press("Control+s")
        page.wait_for_function(
            f"() => window.walk.deposits().length >= {deps_n} + 1"
            " && window.walk.editState().parked === 0", timeout=15000)
        nrow = page.evaluate("() => window.walk.deposits()[0]")
        check(f"[{tag}] the note banks WITH its block (one compound row)",
              nrow["kind"] == "compound" and ("half a thought " + tag) in nrow["comment"],
              f"row {nrow['id']} kind={nrow['kind']} comment='{(nrow['comment'] or '')[:40]}'")
    else:
        check(f"[{tag}] a half-written note PARKS with its block when the card moves",
              False, "fewer than two typable paragraphs — notes-park was not graded")

    # Ctrl-Z outside an in-flight edit is refused in words (the divergence guard)
    cz = np2[0] if np2 else None
    if cz:
        caret_into(page, cz)
        was_cz = page.evaluate(
            f"""() => {{ const h = document.querySelector('[data-block="{cz}"] .blk-body');
                 return h ? h.textContent : ''; }}""")
        page.keyboard.press("Control+z")
        now_cz = page.evaluate(
            f"""() => {{ const h = document.querySelector('[data-block="{cz}"] .blk-body');
                 return h ? h.textContent : ''; }}""")
        chip_cz = page.evaluate(
            "() => { const c = document.getElementById('edit-card');"
            " return c && !c.hidden ? c.querySelector('.ec-status').textContent : ''; }")
        check(f"[{tag}] Ctrl-Z outside an in-flight edit refuses in words, face unmoved",
              was_cz == now_cz and "no edit in flight" in chip_cz,
              f"face unchanged={was_cz == now_cz}; card: '{chip_cz[:50]}'")

    # cross-paragraph CUT: Ctrl-X over a selection spanning two paragraphs — one
    # applied delete-rewrite, the clipboard carries the words
    adj2 = page.evaluate(
        """() => { const bs = window.walk.blocks();
             for (let i = 1; i < bs.length; i++) {
               const a = bs[i-1], b = bs[i];
               if ((a.kind || 'para') !== 'para' || (b.kind || 'para') !== 'para') continue;
               if (!a.file || a.file !== b.file) continue;
               const ea = document.querySelector(`[data-block=\"${CSS.escape(a.id)}\"] .blk-body[contenteditable=true]`);
               const eb = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"] .blk-body[contenteditable=true]`);
               if (ea && eb && ea.textContent.length > 60 && eb.textContent.length > 60)
                 return [a.id, b.id]; }
           return null; }""")
    if adj2:
        ca, cb = adj2
        cut_file_pre = page.evaluate(
            "id => (window.walk.blocks().find(b => b.id === id) || {}).file || null", ca)
        deps_c = page.evaluate("() => window.walk.deposits().length")
        blocks_c = page.evaluate("() => window.walk.blocks().length")
        page.evaluate(
            """([ida, idb]) => {
                 const ha = document.querySelector(`[data-block=\"${CSS.escape(ida)}\"] .blk-body`);
                 const hb = document.querySelector(`[data-block=\"${CSS.escape(idb)}\"] .blk-body`);
                 const wa = document.createTreeWalker(ha, NodeFilter.SHOW_TEXT);
                 let ta; while ((ta = wa.nextNode())) if (ta.nodeValue.trim().length > 30) break;
                 const wb = document.createTreeWalker(hb, NodeFilter.SHOW_TEXT);
                 let tb; while ((tb = wb.nextNode())) if (tb.nodeValue.trim().length > 30) break;
                 const r = document.createRange();
                 r.setStart(ta, 10); r.setEnd(tb, 10);
                 const s = window.getSelection();
                 s.removeAllRanges(); s.addRange(r);
                 ha.focus(); }""", [ca, cb])
        page.keyboard.press("Control+x")
        page.wait_for_function(
            f"() => window.walk.deposits().length === {deps_c} + 1", timeout=15000)
        crow3 = page.evaluate("() => window.walk.deposits()[0]")
        try:
            page.wait_for_function(
                f"() => window.walk.blocks().length === {blocks_c} - 1", timeout=10000)
            cut_merged = True
        except Exception:
            cut_merged = False
        check(f"[{tag}] Ctrl-X across paragraphs cuts as ONE applied rewrite",
              crow3["applied"] is True and crow3["after"] == "(deleted)" and cut_merged,
              f"row {crow3['id']} applied={crow3['applied']} after='{crow3['after']}'")

        # cross-paragraph PASTE: pasting over a spanning selection rewrites with the
        # clipboard's words (synthetic paste event carrying clipboardData)
        # the same FILE as the cut's pair: its gaps are proven plain, so the paste's
        # applied path is deterministic (an odd-gap pair pends honestly, but that is
        # the byte guard's check, not this one's)
        cut_file = cut_file_pre
        adj3 = page.evaluate(
            """(wantFile) => { const bs = window.walk.blocks();
                 for (let i = 1; i < bs.length; i++) {
                   const a = bs[i-1], b = bs[i];
                   if ((a.kind || 'para') !== 'para' || (b.kind || 'para') !== 'para') continue;
                   if (!a.file || a.file !== b.file) continue;
                   if (wantFile && a.file !== wantFile) continue;
                   const ea = document.querySelector(`[data-block=\"${CSS.escape(a.id)}\"] .blk-body[contenteditable=true]`);
                   const eb = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"] .blk-body[contenteditable=true]`);
                   if (ea && eb && ea.textContent.length > 60 && eb.textContent.length > 60)
                     return [a.id, b.id]; }
               return null; }""", cut_file)
        if adj3:
            deps_c2 = page.evaluate("() => window.walk.deposits().length")
            page.evaluate(
                f"""([ida, idb]) => {{
                     const ha = document.querySelector(`[data-block=\"${{CSS.escape(ida)}}\"] .blk-body`);
                     const hb = document.querySelector(`[data-block=\"${{CSS.escape(idb)}}\"] .blk-body`);
                     const wa = document.createTreeWalker(ha, NodeFilter.SHOW_TEXT);
                     let ta; while ((ta = wa.nextNode())) if (ta.nodeValue.trim().length > 30) break;
                     const wb = document.createTreeWalker(hb, NodeFilter.SHOW_TEXT);
                     let tb; while ((tb = wb.nextNode())) if (tb.nodeValue.trim().length > 30) break;
                     const r = document.createRange();
                     r.setStart(ta, 10); r.setEnd(tb, 10);
                     const s = window.getSelection();
                     s.removeAllRanges(); s.addRange(r);
                     ha.focus();
                     const dt = new DataTransfer();
                     dt.setData('text/plain', 'crosspaste{tag} rides the clipboard.');
                     document.dispatchEvent(new ClipboardEvent('paste',
                       {{ bubbles: true, cancelable: true, clipboardData: dt }})); }}""",
                adj3)
            page.wait_for_function(
                f"() => window.walk.deposits().length === {deps_c2} + 1", timeout=15000)
            prow3 = page.evaluate("() => window.walk.deposits()[0]")
            check(f"[{tag}] pasting over a cross-paragraph selection rewrites with the "
                  f"clipboard's words",
                  prow3["applied"] is True,
                  f"row {prow3['id']} applied={prow3['applied']}")
    else:
        check(f"[{tag}] Ctrl-X across paragraphs cuts as ONE applied rewrite", False,
              "no adjacent same-file pair — the cut was not graded")

    # the LIVE REDLINE: r toggles; a park shows its ins mark + struck deletion beside
    # it; a banked row keeps its change visible; r again returns the clean face
    rl_b = page.evaluate(
        """() => { for (const b of window.walk.blocks()) {
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (!el || el.dataset.kind !== 'para') continue;
             const host = el.querySelector('.blk-body[contenteditable=true]');
             if (host && host.textContent.length > 80) return b.id; }
           return null; }""")
    if rl_b:
        caret_into(page, rl_b)
        page.evaluate(
            f"""() => {{ const host = document.querySelector(
                   '[data-block="{rl_b}"] .blk-body');
                 const w = document.createTreeWalker(host, NodeFilter.SHOW_TEXT);
                 let t; while ((t = w.nextNode())) if (t.nodeValue.trim().length > 20) break;
                 const r = document.createRange();
                 r.setStart(t, 2); r.setEnd(t, 8);
                 const s = window.getSelection();
                 s.removeAllRanges(); s.addRange(r); host.focus(); }}""")
        page.keyboard.type("redl" + tag)   # replaces 6 chars: an ins AND a del
        other_rl = page.evaluate(
            """(skip) => { for (const b of window.walk.blocks()) {
                 if (b.id === skip) continue;
                 const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
                 if (!el || el.dataset.kind !== 'para') continue;
                 const host = el.querySelector('.blk-body[contenteditable=true]');
                 if (host && host.textContent.length > 80) return b.id; }
               return null; }""", rl_b)
        caret_into(page, other_rl or rl_b, 40)   # park it (block-change, fresh id)
        page.wait_for_function(
            f"() => window.walk.editState().parkedIds.includes('{rl_b}')", timeout=8000)
        page.evaluate("() => window.walk.toggleRedline()")
        marks = page.evaluate(
            f"""() => {{ const el = document.querySelector('[data-block="{rl_b}"]');
                 return {{ on: window.walk.redline(),
                          ins: el ? el.querySelectorAll('.rl-ins').length : -1,
                          del: el ? el.querySelectorAll('.rl-del').length : -1 }}; }}""")
        check(f"[{tag}] redline ON shows the parked delta: ins marked, deletion struck",
              marks["on"] is True and marks["ins"] >= 1 and marks["del"] >= 1,
              f"{marks}")
        page.evaluate("() => window.walk.toggleRedline()")
        clean = page.evaluate(
            f"""() => {{ const el = document.querySelector('[data-block="{rl_b}"]');
                 const host = el ? el.querySelector('.blk-body') : null;
                 return {{ on: window.walk.redline(),
                          ins: el ? el.querySelectorAll('.rl-ins').length : -1,
                          face: host ? host.textContent.includes('redl{tag}') : null,
                          parked: window.walk.editState().parkedIds,
                          head: host ? host.textContent.slice(0, 120) : null }}; }}""")
        check(f"[{tag}] redline OFF returns the clean face, the edit still standing",
              clean["on"] is False and clean["ins"] == 0 and clean["face"] is True,
              f"{clean}")
        # banked rows stay visible in redline until the next pass
        page.evaluate("() => window.walk.toggleRedline()")
        deps_r = page.evaluate("() => window.walk.deposits().length")
        page.keyboard.press("Control+s")   # banks the parked redl edit (+ any note)
        page.wait_for_function(
            f"() => window.walk.deposits().length >= {deps_r} + 1"
            " && window.walk.editState().parked === 0", timeout=15000)
        banked_marks = page.evaluate(
            f"""() => {{ const el = document.querySelector('[data-block="{rl_b}"]');
                 return {{ ins: el ? el.querySelectorAll('.rl-ins').length : -1,
                          badge: el ? el.querySelectorAll('.rl-badge').length : -1 }}; }}""")
        check(f"[{tag}] a BANKED change stays visible in redline (inline or badged)",
              banked_marks["ins"] >= 1 or banked_marks["badge"] >= 1,
              f"{banked_marks}")
        page.evaluate("() => window.walk.toggleRedline()")

    # PENDING KEEPS HIS WORDS ON THE PAGE: shift the source under a block, bank — the
    # row stands PENDING and the face keeps showing what he typed (amber, held)
    pcp = page.evaluate(
        """() => { for (const b of window.walk.blocks()) {
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (!el || el.dataset.kind !== 'para') continue;
             const host = el.querySelector('.blk-body[contenteditable=true]');
             if (host && host.textContent.length > 80) return { id: b.id, file: b.file }; }
           return null; }""")
    if pcp:
        # EVERY candidate mutates (a same-named build copy must not soak the shift)
        for pfile in sorted((ground / corpus).rglob(Path(pcp["file"]).name)):
            if pfile.is_file():
                pfile.write_text("% moved by the chair (pending check)\n"
                                 + pfile.read_text(encoding="utf-8", errors="replace"),
                                 encoding="utf-8")
        deps_w = page.evaluate("() => window.walk.deposits().length")
        page.evaluate(
            "id => document.querySelector(`[data-block=\"${CSS.escape(id)}\"]`)"
            ".scrollIntoView({block: 'center'})", pcp["id"])
        caret_into(page, pcp["id"])
        page.keyboard.type(" pend" + tag)
        page.keyboard.press("Control+s")
        page.wait_for_function(
            f"() => window.walk.deposits().length === {deps_w} + 1", timeout=15000)
        wrow = page.evaluate("() => window.walk.deposits()[0]")
        held_w = page.evaluate(
            f"""() => {{ const el = document.querySelector('[data-block="{pcp['id']}"]');
                 const host = el ? el.querySelector('.blk-body') : null;
                 return {{ marker: el ? el.dataset.parked || '' : null,
                          face: host ? host.textContent.includes('pend{tag}') : null,
                          parked: window.walk.editState().parked }}; }}""")
        check(f"[{tag}] a PENDING bank keeps his words on the page (amber, held)",
              wrow["pending"] is True and held_w["face"] is True
              and held_w["marker"] == "1" and held_w["parked"] >= 1,
              f"row {wrow['id']} pending={wrow['pending']}; {held_w}")
        page.click("#rail-strip")
        page.evaluate(
            "() => { const r = document.querySelector('#band-parked .pk-row');"
            " const btns = r ? r.querySelectorAll('.pk-btn') : [];"
            " if (btns.length) btns[btns.length - 1].click(); }")
        page.wait_for_function(
            "() => window.walk.editState().parked === 0", timeout=8000)
        check(f"[{tag}] 'drop face' releases the pending park; the row keeps the words",
              True, "parked count 0 after the drop; the pending row stands in the band")
    else:
        check(f"[{tag}] a PENDING bank keeps his words on the page (amber, held)",
              False, "no typable paragraph found — the pending path was not graded")

    # the PARKS SURVIVE a reload: park a marker, reload the page, the draft returns
    pr_b = page.evaluate(
        """() => { for (const b of window.walk.blocks()) {
             const el = document.querySelector(`[data-block=\"${CSS.escape(b.id)}\"]`);
             if (!el || el.dataset.kind !== 'para') continue;
             const host = el.querySelector('.blk-body[contenteditable=true]');
             if (host && host.textContent.length > 80) return b.id; }
           return null; }""")
    if pr_b:
        caret_into(page, pr_b)
        page.keyboard.type(" survives" + tag)
        page.evaluate("() => document.activeElement && document.activeElement.blur()")
        page.wait_for_function("() => window.walk.editState().parked >= 1", timeout=8000)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_function("() => window.walk && window.walk.ready()", timeout=30000)
        st_r = page.evaluate("() => window.walk.editState()")
        face_r = page.evaluate(
            f"""() => {{ const ids = window.walk.editState().parkedIds;
                 for (const id of ids) {{
                   const h = document.querySelector(`[data-block=\"${{CSS.escape(id)}}\"] .blk-body`);
                   if (h && h.textContent.includes('survives{tag}')) return true; }}
                 return false; }}""")
        check(f"[{tag}] a parked draft SURVIVES a page reload (storage + re-place)",
              st_r["parked"] >= 1 and face_r is True,
              f"parked={st_r['parked']}; face carries the draft: {face_r}")
        # settle: revert every standing park so the next viewport starts clean
        page.evaluate(
            """() => { for (const id of window.walk.editState().parkedIds) {
                 const el = document.querySelector(`[data-block=\"${CSS.escape(id)}\"] .blk-body`);
                 if (el) el.focus(); } }""")
        for _ in range(6):
            if page.evaluate("() => window.walk.editState().parked") == 0:
                break
            page.evaluate(
                """() => { const id = window.walk.editState().parkedIds[0];
                     const el = document.querySelector(`[data-block=\"${CSS.escape(id)}\"] .blk-body`);
                     if (el) el.focus(); }""")
            page.keyboard.press("Escape")
    page.screenshot(path=str(shots / f"{tag}-final.png"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", default="paper_roland_qrc")
    ap.add_argument("--keep", action="store_true",
                    help="keep the worktree ground for reading afterwards")
    ap.add_argument("--shots",
                    default=f"evidence/walk_gesture1_click_type_{date.today().isoformat()}")
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(refusal_line("CLICK-TYPE CHAIR", "playwright (the browser this chair drives)",
                           [f"import playwright under {sys.executable}: {exc}"]))
        return REFUSAL_EXIT
    chrome = _chrome_path()

    # THE EVIDENCE DIR IS NOT CREATED YET. It used to be made here, before the ground
    # or the scanner existed, so every refusing run left an empty
    # evidence/walk_gesture1_click_type_<date>/ behind — a dated dir that looks like a
    # walk happened. It is created below, once a browser and a live ground are proved.
    shots = REPO / args.shots
    scratch = Path(os.environ.get("CHAIR_SCRATCH",
                                  Path.home() / ".cache" / "laplace_chair"))
    scratch.mkdir(parents=True, exist_ok=True)

    ground = make_ground(args.corpus, scratch)
    proc = None
    try:
        try:
            proc = start_scanner(ground)
        except GroundAbsent as exc:
            print(refusal_line("CLICK-TYPE CHAIR", "the ground scanner", [str(exc)]))
            return REFUSAL_EXIT
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(
                    **({"executable_path": chrome} if chrome else {}))
            except Exception as exc:                                  # noqa: BLE001
                print(refusal_line(
                    "CLICK-TYPE CHAIR", "a launchable chromium",
                    [f"resolved executable: {chrome or 'playwright default'}",
                     f"launch(): {str(exc)[:200]}"]))
                return REFUSAL_EXIT
            shots.mkdir(parents=True, exist_ok=True)
            for w, h in VIEWPORTS:
                page = browser.new_page(viewport={"width": w, "height": h})
                drive(page, args.corpus, ground, shots, f"{w}x{h}")
                page.close()
            browser.close()
    finally:
        if proc is not None:
            proc.terminate()
        if not args.keep:
            drop_ground(ground)

    # A CHAIR THAT GRADED NOTHING DOES NOT WRITE A VERDICT. Zero checks means the drive
    # never reached a single assertion; writing verdict.json here would overwrite a real
    # banked verdict with an empty one that reads PASS (no FAILs, therefore green).
    if not VERDICTS:
        print(refusal_line("CLICK-TYPE CHAIR", "any check at all (zero checks ran)",
                           ["the walk loaded but produced no verdict rows"]))
        return REFUSAL_EXIT

    failed = [v for v in VERDICTS if v["verdict"] == "FAIL"]
    (shots / "verdict.json").write_text(json.dumps({
        "chair": "click-and-type (gesture 1)", "corpus": args.corpus,
        "ground": "sparse git worktree of HEAD (disposable; removed unless --keep)",
        "checks": VERDICTS,
        "verdict": "FAIL" if failed else "PASS",
    }, indent=1), encoding="utf-8")
    print(f"\nCLICK-TYPE CHAIR: {'FAIL' if failed else 'PASS'} - "
          f"{len(VERDICTS) - len(failed)}/{len(VERDICTS)} checks passed; "
          f"evidence -> {shots.relative_to(REPO)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
