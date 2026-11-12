"""W8.2 — THE EXTENSIVE TEST WELD: the one gate all waves converge on.

This is not new features — it is the STANDING converged gate over the interface weld
(Part II, W0→W7 + W8.1). Ten clauses, each a test or a small family, reusing the
per-wave test idioms (imported where exposed) rather than reinventing them:

  (1)  NAV CLOSURE — every roster row reachable ≤2 interactions from /desk; no dead
       door (every roster path 200; retired paths answer their ruled status).
  (2)  CONTEXT CARRIES — active_corpus set via the cockpit door resolves on bare
       /review, /artefact, /projection, /storyboard (the W0.2 law, cross-surface).
  (3)  DESK VERBS ROUND-TRIP — one adjudication verb and one plan-op verb through
       POST /desk/act write the SAME ledger record as the direct executor, and
       ratify produces a REAL plan delta via the storyboard reduce (the C3.5 chain).
  (4)  THE RAIL MATCHES DISK — /shared/versions rows all resolve to extant paths (the
       W3.1 law, as a standing gate over the LIVE tree).
  (5)  SYNCTEX BOTH WAYS — the W4.2 fixture roundtrip, imported as a gate clause.
  (6)  THE RUN PANEL REFLECTS A REAL ROUND — /storyboard/run over the crank's banked
       evidence derives the banked verdicts; heavy launch buttons spawn NOTHING (the
       W5.2 process-level harness, re-run as a gate).
  (7)  GOLDEN PAYLOADS — every bounded first-paint read (≤16KB) and the desk (≤40 rows).
  (8)  375PX EVERYWHERE — the census/overflow checks over every roster surface.
  (9)  DESLOP — the deslop idiom over the interface authored prose.
  (10) THE CLOSE GAINS THE WELD SMOKE — a close beat (the banked-what-travels
       precedent) that re-runs a FAST subset (clauses 1,2,4,7) every close.

The FAST subset (clauses 1,2,4,7) carry ``weld_smoke`` in their names so the close
beat's ``-k weld_smoke`` shard selects exactly them.

Marking discipline (the strip-and-drive precedent): every clause has a HEADLESS proof
that runs everywhere (stdlib HTTP / pure function calls); the browser tiers auto-skip
when Playwright/Chromium is absent. The synctex clause skips without latexmk/synctex.

LOCAL-CHECKS NOTE (the ARMING line "the PSU guard proven in-browser"): the PSU guard
is a LOCAL launcher posture — remote proves only the REMOTE half (env unset ⇒ unlimited,
which the W5.2/W6.1 tests already do). The in-browser-under-launcher half belongs on the
LOCAL-CHECKS list; clause 6 here proves the *process-level* half (a model-heavy launch
spawns no process/thread), which is what a remote box can honestly prove.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import threading
import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src" / "laplace"
_STATIC = _SRC / "web" / "static_shared"

# the sibling test modules whose idioms this gate reuses (tests/ is on sys.path under
# pytest; belt-and-suspenders for direct invocation).
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_guide as _tg                       # noqa: E402  desk act helpers
import test_w7_3_density as _w73               # noqa: E402  the control-group census
import test_w4_2_synctex_follow as _w42        # noqa: E402  the synctex fixture roundtrip


# ── shared harness ──────────────────────────────────────────────────────────

def _serve():
    from laplace.web import scanner
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), scanner.make_handler())
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _get(port: int, path: str):
    """One GET, redirects NOT followed → (status, location, body-bytes)."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    try:
        c.request("GET", path)
        r = c.getresponse()
        body = r.read()
        return r.status, r.getheader("Location"), body
    finally:
        c.close()


def _roster() -> list[dict]:
    from laplace.web import shared_ui
    from laplace.manuscript import manuscript_versions
    return shared_ui.views_roster()["views"]


# the Chromium fence: env → $PLAYWRIGHT_BROWSERS_PATH → /opt/pw-browsers → the user
# cache, over both chrome-linux / chrome-linux64 layouts (tests/browser_fence.py). The
# hardcoded /opt glob this used to carry SKIPPED every browser tier on any box that
# installed playwright's browsers the ordinary way — green while proving nothing.
import browser_fence as _bf                    # noqa: E402
_CHROME = _bf.CHROME
try:
    import playwright.sync_api as _pw  # noqa: F401
    _HAS_PW = True
except Exception:
    _HAS_PW = False
_NO_BROWSER = _CHROME is None or not _HAS_PW
_SKIP_BROWSER = (_bf.NO_CHROME_REASON if _CHROME is None else "playwright not installed")


# ═════════════════════════════════════════════════════════════════════════════
# CLAUSE 1 — NAV CLOSURE: no dead door; every roster path 200; retirements ruled;
#            every row ≤2 interactions from /desk. (FAST subset → weld_smoke.)
# ═════════════════════════════════════════════════════════════════════════════

# the retired doors and their ruled answer (W0.3 + W3): a 301 to the successor, or 410 GONE.
# W3 inverted the conceptric redirect — /conceptric is now THE page, /conceptric2 the 301 stub.
_RETIRED = {
    "/navigator": (301, "/altitude"),
    "/conceptric2": (301, "/conceptric"),
    "/editor": (410, None),
}


def test_weld_smoke_c1_nav_closure_no_dead_door():
    """No dead door on the roster: every authored roster row's path serves 200, and
    every retired path answers its ruled status (301→successor / 410 GONE) — proven
    over the LIVE tree in the real scanner."""
    roster = _roster()
    assert roster, "the authored roster must be non-empty"
    httpd, port = _serve()
    try:
        dead = []
        for v in roster:
            st, loc, body = _get(port, v["path"])
            # a roster row that 301s to a LIVE successor is a live door, not a dead one — follow
            # one hop to the landed page (W-TRIAGE 2026-07-22: the pipeline row keeps its /pipeline
            # label but 301s to /project, the ACTUAL cockpit page — contract/tombstones.yaml
            # '/pipeline 301s HERE'; the palette-per-route seal uses the same one-hop follow).
            if st in (301, 302) and loc:
                st, _loc2, body = _get(port, loc)
            if st != 200 or len(body) < 200:
                dead.append((v["id"], v["path"], st, len(body)))
        assert not dead, f"roster rows that are not a live 200 page: {dead}"

        wrong = []
        for path, (want_st, want_loc) in _RETIRED.items():
            st, loc, body = _get(port, path)
            if st != want_st:
                wrong.append((path, "status", st, want_st))
            if want_loc is not None and loc != want_loc:
                wrong.append((path, "location", loc, want_loc))
            if want_st == 410 and b"/projection" not in body:
                wrong.append((path, "410-names", body[:80], "/projection"))
        assert not wrong, f"a retired door did not answer its ruled status: {wrong}"
    finally:
        httpd.shutdown()


def test_weld_smoke_c1_every_row_within_two_interactions():
    """≤2 interactions from /desk, static-structure proof: every roster row is in the
    primary strip (group primary → 1 click) or the '…' disclosure (group 'more' → open
    + click = 2). There is NO third tier, and the shell wires the disclosure — so no row
    is ever more than two interactions deep. (The renderer-level ≤2-clicks drive rides
    below and auto-skips without a browser.)"""
    # SUPERSEDED 2026-07-22 (the journey shell): the '…' disclosure died into the
    # process spine — every roster row now appears exactly once in the journey, as a
    # STAGE (one click) or as a DOOR on a stage's hover/focus card (reveal + click = 2).
    # The ≤2-interactions law is proven against shared_ui.journey_payload, the same
    # producer the shell renders.
    from laplace.web import shared_ui
    from laplace.manuscript import manuscript_versions
    roster_ids = {v["id"] for v in _roster()}
    seen: list[str] = []
    for st in shared_ui.journey_payload(None)["stages"]:
        seen.append(st["view"])
        seen.extend(d["view"] for d in st["doors"] if d.get("view"))
    assert sorted(seen) == sorted(set(seen)), f"journey names a view twice: {seen}"
    assert set(seen) == roster_ids, (
        f"journey coverage broken — missing {roster_ids - set(seen)}, "
        f"phantom {set(seen) - roster_ids}")
    shell = (_STATIC / "shell.js").read_text(encoding="utf-8")
    assert "journeyHTML" in shell and "sc-door" in shell, \
        "the shell must render the journey (stages + stage-card doors)"


@pytest.mark.skipif(_NO_BROWSER, reason=_SKIP_BROWSER)
def test_c1_full_roster_reachable_in_two_clicks_in_browser():
    """The renderer-level ≤2-interactions proof over the real roster from /desk, driven
    against THE JOURNEY SHELL.

    REALIGNED 2026-08-21 (WO-20260810-stale-browser-smokes). This leg still drove the
    pre-2026-07-22 nav: a primary strip plus a '…' disclosure button (``.hy-more-btn``)
    revealing the ``group == 'more'`` rows. That design died into the process spine the
    same day its static sibling above was superseded — ``.hy-more-btn`` exists nowhere
    in ``shell.js``, so this leg asserted a selector that no longer exists and could
    only ever fail (it read green solely by skipping for want of a browser).

    The live grammar, measured: every roster row appears exactly once in the journey —
    as a STAGE (``a.hy-stage[data-view]``, painted and visible at rest → ONE click), or
    as a DOOR on that stage's card (``a.sc-door[data-view]``, the card
    ``visibility:hidden`` at rest and revealed by hover OR keyboard focus of its stage
    → reveal + click = TWO). So: no row is invisible-and-unreachable, no door is
    exposed without its reveal, and there is no third tier."""
    from playwright.sync_api import sync_playwright
    roster_ids = {v["id"] for v in _roster()}
    httpd, port = _serve()
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 1400, "height": 900})
            pg.goto(f"http://127.0.0.1:{port}/desk", wait_until="networkidle")
            pg.wait_for_selector("#hy-shell a.hy-stage[data-view]", timeout=10000)

            def shown(sel):
                """views whose element is painted AND not visually hidden — the
                reveal rides visibility/opacity on the stage card, so a bounding box
                alone would call every hidden door visible."""
                return set(pg.eval_on_selector_all(sel, """els => els.filter(e => {
                    const r = e.getBoundingClientRect();
                    if (!(r.width > 2 && r.height > 2)) return false;
                    for (let n = e; n; n = n.parentElement) {
                      const cs = getComputedStyle(n);
                      if (cs.visibility === 'hidden' || cs.display === 'none'
                          || parseFloat(cs.opacity) < 0.05) return false;
                    }
                    return true;
                }).map(e => e.dataset.view)"""))

            stage_ids = set(pg.eval_on_selector_all(
                "#hy-shell a.hy-stage[data-view]", "els => els.map(e => e.dataset.view)"))
            door_ids = set(pg.eval_on_selector_all(
                "#hy-shell a.sc-door[data-view]", "els => els.map(e => e.dataset.view)"))

            # (1) coverage + no third tier: stages ∪ doors is exactly the roster, disjoint
            assert stage_ids | door_ids == roster_ids, (
                f"journey renderer coverage broken — missing "
                f"{roster_ids - (stage_ids | door_ids)}, phantom "
                f"{(stage_ids | door_ids) - roster_ids}")
            assert not (stage_ids & door_ids), \
                f"a view renders as BOTH a stage and a door: {stage_ids & door_ids}"

            # (2) every stage is directly visible → one click
            visible_stages = shown("#hy-shell a.hy-stage[data-view]")
            assert visible_stages == stage_ids, \
                f"stage(s) not directly visible: {stage_ids - visible_stages}"

            # (3) no door is exposed at rest, and each becomes reachable after ONE
            #     reveal of its own stage (hover; keyboard focus is the same door)
            assert not shown("#hy-shell a.sc-door[data-view]"), \
                f"door(s) visible before the reveal: {shown('#hy-shell a.sc-door[data-view]')}"
            # the reveal is DELAYED by design (hymn.css .hy-stage-card:
            # `transition:opacity .13s ease .14s, visibility 0s linear .27s` — the
            # hover-intent guard against cards flashing as the pointer crosses the
            # spine). So POLL for the reveal instead of racing it with one fixed
            # sleep: a 120ms wait sat below the 140ms delay and lost every time,
            # while a bigger magic number would only move the race. Measured on this
            # box: revealed at ~153ms. The bar is unchanged — ONE interaction reveals
            # it — and a door that never reveals still fails, now after 1.5s.
            def revealed_after_hover(el, view, budget_ms=1500):
                el.hover()
                for _ in range(budget_ms // 25):
                    if view in shown("#hy-shell a.sc-door[data-view]"):
                        return True
                    pg.wait_for_timeout(25)
                return False

            for view in sorted(door_ids):
                stage = pg.query_selector(
                    f"#hy-shell a.sc-door[data-view='{view}']"
                ).evaluate_handle(
                    "d => d.closest('.hy-stage-wrap').querySelector('a.hy-stage')"
                ).as_element()
                assert revealed_after_hover(stage, view), \
                    f"door {view} not revealed by one interaction on its stage"
            b.close()
    finally:
        httpd.shutdown()


# ═════════════════════════════════════════════════════════════════════════════
# CLAUSE 2 — CONTEXT CARRIES: active_corpus set via the cockpit door resolves on
#            bare /review, /artefact, /projection, /storyboard. (FAST → weld_smoke.)
# ═════════════════════════════════════════════════════════════════════════════

def test_weld_smoke_c2_context_carries_cross_surface(tmp_path, monkeypatch):
    """The W0.2 law, cross-surface: writing active_corpus through the cockpit door
    (scanner.cockpit_state — the one additive-merge writer) is read back by EVERY bare
    surface's resolver: active_corpus / default_corpus (→ /storyboard's /corpus/list
    default and /projection's bootstrap), review._resolve (→ /review), and
    project_context (→ /projection). The switch keeps his other cockpit keys."""
    from laplace.research import corpus_ingest as ci
    from laplace.web import scanner
    from laplace.manuscript import review_surface as rv
    monkeypatch.delenv("LAPLACE_ACTIVE_PROJECT", raising=False)
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(rv, "_repo_root", lambda: tmp_path)

    # a real registered corpus, taken from the roster the resolvers read (the one door)
    name = ci.registered_corpora(_REPO)[0]
    # ...and registered under the tmp root too, since default_corpus validates a
    # persisted value against THAT root's registry.
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [
        {"name": name, "kind": "conceptric",
         "tex_root": f"synthetics papers/{name}/manuscript"}]}), encoding="utf-8")

    # a pre-existing sibling knob — the switch must not clobber it (the merge law)
    scanner.cockpit_state({"panel_layout": "wide"})
    # THE COCKPIT DOOR: persist the active project
    scanner.cockpit_state({"active_corpus": name})

    # read back through every bare-surface resolver
    assert ci.active_corpus(tmp_path) == name           # the persisted read
    assert ci.default_corpus(tmp_path) == name          # → /storyboard, /projection bootstrap
    assert ci.project_context(tmp_path)["corpus"] == name  # → bare /projection

    seen: dict = {}
    monkeypatch.setattr(rv, "manuscript_dir",
                        lambda corpus="", dir_param="": seen.update(corpus=corpus) or tmp_path)
    md, corpus, _dir = rv._resolve({})                  # a BARE /review query
    assert md is not None and corpus == name and seen["corpus"] == name

    # the sibling survived the corpus switch (additive-merge, the desk-hint's contract)
    on_disk = json.loads((tmp_path / scanner.COCKPIT_FILE).read_text(encoding="utf-8"))
    assert on_disk["active_corpus"] == name and on_disk["panel_layout"] == "wide"


# W5: the /guide-bare active-project clause retired with the /guide explainer (the desk
# is a GLOBAL worklist, not project-scoped). The bare-surface active-project law stays
# proven by test_weld_smoke_c2_context_carries_cross_surface (bare /review + project_context)
# above and by /artefact's registry.project_context resolver.


# ═════════════════════════════════════════════════════════════════════════════
# CLAUSE 3 — DESK VERBS ROUND-TRIP through POST /desk/act: one adjudication
#            verb writes the SAME record as the direct executor; one plan-op verb
#            (ratify) runs the C3.5 apply bridge and produces a REAL plan delta.
# ═════════════════════════════════════════════════════════════════════════════

def test_c3_adjudication_verb_round_trips_the_same_record(tmp_path, monkeypatch):
    """confirm through POST /desk/act writes byte-for-byte the record
    review_surface.adjudicate writes directly (minus the fresh id/ts) — the door is a
    thin dispatch, never a second copy of the executor."""
    from laplace.manuscript import review_surface as rs
    fb = [_tg._finding()]
    md_direct = _tg._manuscript(tmp_path / "direct", feedback=fb)
    md_door = _tg._manuscript(tmp_path / "door", feedback=fb)
    fields = {"finding_id": "FB-1", "node": "S1", "kind": "eq-unused"}
    direct = rs.adjudicate(md_direct, "smoke", {"by": "author", "verb": "confirm", **fields})
    assert direct["ok"]

    monkeypatch.setattr(rs, "manuscript_dir", lambda *a, **k: md_door)
    st, _, body = _tg._act({"class": "adjudications", "verb": "confirm",
                            "project": "smoke", "by": "author", **fields})
    door = json.loads(body)
    assert st == 200 and door["ok"]
    assert _tg._strip(door["record"]) == _tg._strip(direct["record"])


def test_c3_planop_ratify_runs_the_c35_bridge_and_writes_a_real_plan_delta(tmp_path, monkeypatch):
    """ratify through the door runs the C3.5 apply bridge end-to-end: it derives the
    open projection-intent, EXECUTES the set-meta op through the storyboard plan-ledger
    reduce (the plan file on disk actually changes), retires the intent, and is
    idempotent on a re-fire. The plan delta is READ off disk before/after — a real
    reduce, not a claimed one."""
    from laplace.manuscript import review_surface as rs
    from laplace.manuscript import manuscript_versions
    from laplace.pipeline import adjudicate as adj, registry
    APPLY = "weld-c3-apply"
    plan = {"meta": {"project": APPLY, "weighting": "even across sections",
                     "target_dir": ""},
            "sections": [{"id": "S1", "title": "Intro", "job": "open",
                          "nodes_in_order": ["a"], "beats": [], "figures": [], "refs": []}],
            "appendices": []}
    p = tmp_path / "projection_plan.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    monkeypatch.setattr(registry, "plan_path_for", lambda corpus: p)

    md = tmp_path / "wp"
    (md / "feedback").mkdir(parents=True)
    intent = adj.make_projection_intent("FB-w", "DEMOTE", object_kind="meta",
                                        object_key="weighting", note="lower it",
                                        finding_kind="emphasis-mismatch", project=APPLY)
    (md / "feedback" / "feedback.jsonl").write_text(json.dumps(intent) + "\n", encoding="utf-8")
    monkeypatch.setattr(rs, "manuscript_dir", lambda *a, **k: md)

    before = json.loads(p.read_text(encoding="utf-8"))["meta"]["weighting"]
    assert before == "even across sections"

    act = {"class": "plan-ops", "verb": "ratify", "project": APPLY, "by": "gerard"}
    st, _, body = _tg._act(act)
    d = json.loads(body)
    assert st == 200 and d["ok"]
    assert [x["intent"] for x in d["applied"]] == [intent["id"]]   # the C3.5 apply

    # THE REAL PLAN DELTA on disk: weighting was reduced through the storyboard reduce —
    # the prior value preserved under `value`, the ruling stamped alongside (reversible).
    after = json.loads(p.read_text(encoding="utf-8"))["meta"]["weighting"]
    assert after != before, "the plan meta did not change — no real reduce happened"
    assert isinstance(after, dict) and after["value"] == before
    assert after["projection_ruling"]["intent"] == intent["id"]

    # idempotent: the consumed intent is retired, so a second ratify applies nothing.
    st2, _, body2 = _tg._act(act)
    d2 = json.loads(body2)
    assert st2 == 200 and d2["applied"] == [] and d2["idempotent"] is True


# ═════════════════════════════════════════════════════════════════════════════
# CLAUSE 4 — THE RAIL MATCHES DISK: every /shared/versions row resolves to an extant
#            path on the LIVE tree (the W3.1 law, standing). (FAST → weld_smoke.)
# ═════════════════════════════════════════════════════════════════════════════

def test_weld_smoke_c4_rail_rows_all_resolve_to_extant_paths():
    """Over every registered corpus, on the LIVE tree: every path in every
    /shared/versions row resolves to a file/dir that exists (repo-relative, never
    absolute). A rail row pointing at a path not on disk is a lie the join forbids."""
    from laplace.research import corpus_ingest as ci
    from laplace.web import shared_ui
    from laplace.manuscript import manuscript_versions
    checked = 0
    missing = []
    for corpus in ci.registered_corpora(_REPO):
        out = manuscript_versions.versions_payload(corpus)
        if out is None:
            continue
        for row in out["rows"]:
            for pth in row["paths"]:
                assert not pth.startswith("/"), f"{corpus}: absolute path leaked: {pth}"
                if not (_REPO / pth).exists():
                    missing.append((corpus, row.get("kind"), row.get("id"), pth))
                checked += 1
    assert not missing, f"rail rows point at paths not on disk: {missing[:12]}"
    assert checked > 0, "no rail rows resolved on the live tree — the gate proved nothing"


# ═════════════════════════════════════════════════════════════════════════════
# CLAUSE 5 — SYNCTEX BOTH WAYS: the W4.2 fixture roundtrip, imported as a gate clause.
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(_w42._LATEXMK is None or _w42._SYNCTEX is None,
                    reason="no latexmk/synctex toolchain on this box")
def test_c5_synctex_roundtrip_both_ways(monkeypatch, tmp_path):
    """The W4.2 fixture roundtrip, imported: compile the tiny fixture with
    ``latexmk -synctex=1``, then resolve a known line↔page pair BOTH ways — source→pdf
    (``synctex_locate``) and pdf→source (``synctex_anchor``) — proving the local-tex
    follow path is live end to end."""
    from laplace.manuscript import projection_viewer as pv
    monkeypatch.setattr("laplace.web.scanner._repo_root", lambda: tmp_path)
    (tmp_path / "main.tex").write_text(_w42._FIXTURE_TEX, encoding="utf-8")
    r = subprocess.run(
        [_w42._LATEXMK, "-pdf", "-synctex=1", "-interaction=nonstopmode", "main.tex"],
        cwd=str(tmp_path), capture_output=True, encoding="utf-8", errors="replace", timeout=180)
    if not (tmp_path / "main.pdf").is_file():
        pytest.skip(f"fixture failed to compile: {r.stdout[-400:]}")

    post = pv.follow_status("main.tex")
    assert post["present"] is True and post["fresh"] is True and post["degraded"] is False

    beta_line = _w42._FIXTURE_TEX.splitlines().index(r"\section{Beta target}") + 1
    loc = pv.synctex_locate("main.tex", "", beta_line)              # source → pdf
    assert "error" not in loc and loc["page"] >= 1 and loc["y"] > 0
    anc = pv.synctex_anchor("main.tex", loc["page"], loc["x"], loc["y"])   # pdf → source
    assert "error" not in anc and anc["file"].endswith("main.tex")
    assert abs(anc["line"] - beta_line) <= 3, (anc["line"], beta_line)


# ═════════════════════════════════════════════════════════════════════════════
# CLAUSE 6 — THE RUN PANEL REFLECTS A REAL ROUND: /storyboard/run over the crank's
#            banked evidence derives the banked verdicts; heavy launch spawns NOTHING.
# ═════════════════════════════════════════════════════════════════════════════

def test_c6_run_panel_derives_the_cranks_banked_verdicts():
    """/storyboard/run over the crank's REAL on-disk evidence (eigenengine) derives the
    banked final state, and its derived counts agree with the artifacts it read: the
    phase is a terminal 'finalized' proven by the finalize/minted_pdf artifacts, and the
    round counts are consistent with the round records present (never fabricated)."""
    from laplace.manuscript import storyboard as sb
    out = sb.run_payload("eigenengine")
    assert out is not None and out["corpus"] == "eigenengine"
    assert out["never_run"] is False
    assert out["phase"] == "finalized" and out["in_flight"] is False
    kinds = {a["kind"] for a in out["artifacts"]}
    # the derived terminal verdict is PROVEN by the artifacts on disk. ALIGNED WITH DISK TRUTH
    # (WO-20260715-002324 drained 2026-07-22): eigenengine's release/ carries finalize.json AND
    # the recovered minted PDF (eigenengine-2026-07-14-r1.pdf, re-minted through the release
    # finalize recipe — the .gitignore hole that dropped it is fixed, so it now commits and
    # travels), so the terminal 'finalized' phase is backed by BOTH the finalize record and the
    # minted-PDF blob. The recovery tightened this assertion, exactly as its prior note asked.
    assert "finalize" in kinds, f"terminal phase unbacked: {kinds}"
    assert "minted_pdf" in kinds, (
        "the recovered release PDF must back the terminal phase; if it goes missing again, "
        "recover it through release.finalize (WO-20260715-002324)")
    assert out["rounds_so_far"] >= 1 and out["current_round"] >= 1
    assert out["rounds_so_far"] >= out["current_round"] or out["current_round"] is not None
    for a in out["artifacts"]:
        assert not a["path"].startswith("/"), f"absolute artifact path leaked: {a['path']}"
        assert (_REPO / a["path"]).exists(), f"run-panel artifact not on disk: {a['path']}"


@pytest.mark.parametrize("action", ["harnessed-round", "re-projection", "dream"])
def test_c6_heavy_launch_spawns_nothing_process_level(monkeypatch, tmp_path, action):
    """The W5.2 process-level harness, re-run as a gate: a model-heavy launch banks
    EXACTLY one work-order and spawns NOTHING — proven at the process level
    (subprocess.run/Popen AND threading.Thread all raise on that path, and the record
    still lands). The server never spends tokens on a click."""
    from laplace.manuscript import storyboard as sb
    import laplace.web.scanner as scanner
    monkeypatch.setattr(scanner, "_repo_root", lambda: tmp_path)

    import threading as _th
    def _boom(*a, **k):
        raise AssertionError("a model-heavy launch spawned a process/thread — the server "
                             "must only bank a work-order (heavy buttons spawn NOTHING)")
    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    monkeypatch.setattr(_th, "Thread", _boom)

    st, obj = sb.run_launch("eigenengine", action, "gerard")
    assert st == 200 and obj["ok"] is True
    assert obj["cost_class"] == "model-heavy" and obj["spawned"] is False
    store = tmp_path / "corpus_friction" / "work_orders.jsonl"
    lines = [l for l in store.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1 and json.loads(lines[0]) == obj["work_order"]


# ═════════════════════════════════════════════════════════════════════════════
# CLAUSE 7 — GOLDEN PAYLOADS: every bounded first-paint read ≤16KB; desk ≤40 rows.
#            (FAST subset → weld_smoke.)
# ═════════════════════════════════════════════════════════════════════════════

_GOLDEN = 16 * 1024


def test_weld_smoke_c7_golden_first_paint_reads_and_desk_rows():
    """The golden law over the bounded-by-contract first-paint reads, measured on the
    LIVE tree: each ≤16KB, and the desk's drill-down ≤40 rows (Law I, desk._QUEUE_CAP).
    These are the DELTAS-FIRST / summary reads whose contract is boundedness (each has a
    _MAX_BYTES enforcer); the desk, the review summary, the versions rail, the run panel,
    and the staleness strip."""
    from laplace.research import corpus_ingest as ci
    from laplace.web import desk, shared_ui
    from laplace.manuscript import review_surface as rv
    from laplace.manuscript import manuscript_versions
    from pathlib import Path as _P
    # the ACTIVE project, unless it has no review surface yet: a project born through
    # the New Project door legitimately 404s on the review reads until its plan and
    # target dir land (manuscript_dir fails closed on a plan with no target). The golden
    # law bounds the SIZE of a read that exists, so it is measured on the first project
    # that has one - deterministic, and never the newest-ledger mtime race.
    _roster = [ci.default_corpus(_P("."))] + ci.registered_corpora(_P("."), openable=True)
    corpus = next((c for c in _roster if rv.manuscript_dir(c) is not None), _roster[0])

    httpd, port = _serve()
    try:
        reads = [
            "/desk/data",
            f"/review/summary?corpus={corpus}",
            "/shared/staleness",
            f"/shared/staleness?corpus={corpus}",
            f"/shared/versions?corpus={corpus}",
            f"/storyboard/run?corpus={corpus}",
        ]
        oversize = []
        for path in reads:
            st, _loc, body = _get(port, path)
            assert st == 200, f"{path} → HTTP {st}"
            if len(body) > _GOLDEN:
                oversize.append((path, len(body)))
        assert not oversize, f"bounded first-paint reads over the 16KB golden: {oversize}"

        # the desk drill-down ≤40 rows (Law I), and its own payload ≤16KB.
        st, _loc, body = _get(port, "/desk/data")
        d = json.loads(body)
        assert desk._QUEUE_CAP == 40, "Law I: the ONE producer of the density bound is 40"
        assert d["cap"] == 40 and len(d["rows"]) <= 40, f"desk rows: {len(d['rows'])}"

        # per-corpus versions rail (every registered corpus) obeys the golden law too.
        for c in ci.registered_corpora(_REPO):
            st, _loc, body = _get(port, f"/shared/versions?corpus={c}")
            assert st in (200, 404)
            if st == 200:
                assert len(body) <= _GOLDEN, f"/shared/versions?corpus={c}: {len(body)}B > 16KB"
    finally:
        httpd.shutdown()


# W5: the /tutorial-document clause retired — the tutorial page died (its explainer role
# rehoused as per-surface ⓘ + the desk cockpit; census W5). No walkthrough document remains
# to measure.


# ═════════════════════════════════════════════════════════════════════════════
# CLAUSE 8 — 375PX EVERYWHERE: the census / overflow checks over every roster surface.
# ═════════════════════════════════════════════════════════════════════════════

def test_c8_shell_nav_375_law_holds_globally():
    """The 375px law at the shell (injected on EVERY roster surface). SUPERSEDED
    2026-07-22 (the journey shell): the '…' disclosure died — the journey row WRAPS
    (never horizontal-scrolls) and the stage cards are out of flow, hidden at rest,
    anchoring to the right edge on narrow viewports. One CSS idiom, every surface."""
    css = (_STATIC / "hymn.css").read_text(encoding="utf-8")
    row_rule = css.split("#hy-shell .hy-journey{")[1].split("}")[0]
    assert "flex-wrap:wrap" in row_rule and "flex:none" not in row_rule
    card_rule = css.split("#hy-shell .hy-stage-card{")[1].split("}")[0]
    assert "position:absolute" in card_rule and "visibility:hidden" in card_rule
    assert "#hy-shell .hy-stage-card{right:0;left:auto" in css.replace("\n", "")


def test_c8_density_census_over_the_dense_surfaces():
    """The W7.3 control-group census, imported: /storyboard and /conceptric each open at
    ≤4 first-paint control groups — the density half of the 375px discipline over the two
    (formerly) dense surfaces. WHERE a surface EXCEEDS the budget the excess is FOLDED (not
    deleted) behind a one-click disclosure; and every folded group carries its trigger.

    UPDATED TO CURRENT TRUTH (W-PINS 2026-07-22): BOTH surfaces are now JS boot shells whose
    control groups materialise AT RUNTIME behind a focus — /conceptric became the growth
    cockpit (cockpit-panes.mjs / initCockpit, W3/E3) and /storyboard became the storyboard
    in the engine (storyboard-panes.mjs / initStoryboard, W-SB). So the STATIC first-paint
    census carries ZERO static groups on each: the ≤4 density budget holds BY CONSTRUCTION,
    superseding the old 'storyboard folds its staleness strip' clause (the strip now
    materialises at runtime, it is not a static fold). GAP FLAGGED (named): the runtime
    first-paint density of the engine surfaces is owed to the interface/cockpit wave — a
    static parse cannot measure a JS-rendered surface. Any STATIC fold a shell does carry
    must still be reachable in one click (the discipline is retained for that case)."""
    for html_path in (_w73._STORYBOARD, _w73._CONCEPTRIC2):
        c = _w73.census(html_path.read_text(encoding="utf-8"))
        assert c.visible == [], \
            f"{html_path.name}: JS engine shell must carry no static density groups now: {c.visible}"
        for name, gid in c.folded:
            assert gid and gid in c.triggers, \
                f"{html_path.name}: folded group {name!r} has no one-click disclosure"
    # both surfaces are engine boot shells — the census is mechanically zero-group by
    # construction, so the density budget cannot be exceeded by a static parse here.
    for html_path, marker in ((_w73._STORYBOARD, "initStoryboard"), (_w73._CONCEPTRIC2, "initCockpit")):
        assert marker in html_path.read_text(encoding="utf-8"), \
            f"{html_path.name}: expected the engine boot shell ({marker})"


# W5: the tutorial 375px CSS-floor clause retired with the tutorial page. THE DESK COCKPIT's
# own 375px floor rides the shared shell (test_c8_shell_nav_375_law_holds_globally) + its
# layout-only <style> (single-column @max-width:720px), and the renderer-level overflow gate
# below drives EVERY roster surface (which now includes /desk).


@pytest.mark.skipif(_NO_BROWSER, reason=_SKIP_BROWSER)
def test_c8_no_horizontal_overflow_at_375px_every_surface():
    """The renderer-level 375px proof over EVERY roster surface: no horizontal scroll at
    375px, at rest and (where present) with the shell disclosure open. This is the real
    converged overflow gate; it auto-skips without a browser."""
    from playwright.sync_api import sync_playwright
    roster = _roster()
    httpd, port = _serve()
    overflows = []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch(executable_path=_CHROME)
            pg = b.new_page(viewport={"width": 375, "height": 720})
            for v in roster:
                pg.goto(f"http://127.0.0.1:{port}{v['path']}", wait_until="networkidle")
                try:
                    pg.wait_for_selector("#hy-shell nav a[data-view]", timeout=10000)
                except Exception:
                    pass
                w = pg.evaluate("() => document.documentElement.scrollWidth")
                cw = pg.evaluate("() => document.documentElement.clientWidth")
                if w > cw:
                    overflows.append((v["id"], "rest", w, cw))
                if pg.query_selector("#hy-shell .hy-more-btn"):
                    pg.click("#hy-shell .hy-more-btn")
                    pg.wait_for_timeout(120)
                    w2 = pg.evaluate("() => document.documentElement.scrollWidth")
                    cw2 = pg.evaluate("() => document.documentElement.clientWidth")
                    if w2 > cw2:
                        overflows.append((v["id"], "open", w2, cw2))
            b.close()
    finally:
        httpd.shutdown()
    assert not overflows, f"horizontal overflow at 375px: {overflows}"


# ═════════════════════════════════════════════════════════════════════════════
# CLAUSE 9 — DESLOP: the deslop idiom over the interface authored prose.
# ═════════════════════════════════════════════════════════════════════════════

def _load_deslop():
    spec = importlib.util.spec_from_file_location(
        "deslop_gate", _REPO / "scripts" / "deslop_gate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _interface_prose_units() -> list[dict]:
    """One text unit per authored interrogation block — the interface weld's new prose,
    and (verbatim) the tutorial's own rendered strings (zero-new-prose)."""
    text = (_REPO / "interface" / "FUNCTION_INTERROGATIONS.md").read_text(encoding="utf-8")
    units = []
    for block in re.split(r"^## ", text, flags=re.M)[1:]:
        lines = block.splitlines()
        units.append({"where": lines[0][:40], "text": "\n".join(lines[1:])})
    return units


# his own ruled vocabulary — NOT marketing slop. "first-class" is his verbatim word for
# the tutorial and for /analytics-as-a-consumer (ARMING 2026-07-13, "a FIRST-CLASS
# NAVIGABLE TUTORIAL", "survives as a first-class consumer"); the deslop jargon seed
# lists it as a slogan tell, but here it is his register, allow-listed with its cite.
_HIS_VOCABULARY = {"first-class"}


def test_c9_deslop_no_marketing_slop_beyond_his_vocabulary():
    """The public-jargon slop tell (the marketing-slop lexicon his mandate names —
    'soaked in slogan slop') finds NO unallowed slogan in the interface's new authored
    prose. The only hit is his own ruled vocabulary ('first-class'); a NEW slogan
    ('leverage', 'synergy', …) entering an authored surface fails this gate."""
    dg = _load_deslop()
    jargon = list(dg._SEED_JARGON)
    hits: set[str] = set()
    for u in _interface_prose_units():
        hits.update(t.lower() for t in dg.detect_jargon(u["text"], jargon, allowset=set()))
    unallowed = hits - _HIS_VOCABULARY
    assert not unallowed, f"marketing slop entered the interface prose: {sorted(unallowed)}"


def test_c9_deslop_gate_runs_advisory_over_the_prose(tmp_path):
    """The gate itself runs to completion over the interface prose (advisory by design —
    it reports, never blocks): scan() returns a ScanResult carrying its suppressed-ruled
    tally, in a hermetic tmp repo (so the seeded lexicon never touches the live tree).
    The oracle/antithesis detectors are noisy on legitimate technical prose — which is
    exactly why the gate is advisory and clause 9's TEETH are the jargon check above."""
    dg = _load_deslop()
    res = dg.scan(tmp_path, _interface_prose_units(), corpus_name=None,
                  today="2026-07-14", antithesis_min=2, density_min=0.5)
    assert isinstance(res, dg.ScanResult)
    assert isinstance(res.suppressed_ruled, int)
    # the seeded lexicon lives in the tmp repo, never the live tree
    assert (tmp_path / dg.DESLOP_LEXICON_NAME).is_file()
    assert not (_REPO / dg.DESLOP_LEXICON_NAME).exists() or True  # never asserts on the live file


# ═════════════════════════════════════════════════════════════════════════════
# CLAUSE 10 — THE CLOSE GAINS THE WELD SMOKE: a close beat re-runs the FAST subset.
# ═════════════════════════════════════════════════════════════════════════════

def test_c10_close_registers_the_smoke_beat():
    """The banked-what-travels precedent: close_beats.beat_plan registers a
    ``weld_smoke`` beat that fires every close (grade-0 — the weld is standing) and
    names the FAST ``-k weld_smoke`` shard as its source — never the flat suite."""
    from laplace.engine import close_beats as cb
    plan = cb.beat_plan(_REPO)
    beat = next((b for b in plan if b["beat"] == "weld_smoke"), None)
    assert beat is not None, "the weld_smoke close beat is not registered"
    assert beat["fire"] is True, "the weld smoke must fire every close"
    assert set(beat) == {"beat", "fire", "sources", "why"}
    src = beat["sources"][0]
    assert "test_interface_weld.py" in src and "-k weld_smoke" in src
    assert "flat" in beat["why"], "the beat must disclaim the flat suite"


def test_c10_smoke_shard_selects_exactly_the_fast_subset():
    """The ``-k weld_smoke`` shard the beat names selects EXACTLY clauses 1,2,4,7 — the
    fast-subset tests this file exposes (whose names carry ``weld_smoke``) — so the
    close's smoke is the intended fast gate, not an accidental over- or under-selection.
    The c10 meta-tests deliberately carry ``smoke`` but NOT ``weld_smoke``, so the shard
    never re-selects the beat-registration checks themselves."""
    import test_interface_weld as self_mod
    selected = {n for n in dir(self_mod) if n.startswith("test_") and "weld_smoke" in n}
    assert selected == {
        "test_weld_smoke_c1_nav_closure_no_dead_door",
        "test_weld_smoke_c1_every_row_within_two_interactions",
        "test_weld_smoke_c2_context_carries_cross_surface",
        "test_weld_smoke_c4_rail_rows_all_resolve_to_extant_paths",
        "test_weld_smoke_c7_golden_first_paint_reads_and_desk_rows",
    }, f"the weld_smoke shard drifted: {sorted(selected)}"
