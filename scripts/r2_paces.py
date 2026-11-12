"""The paces driver — automate a revision through the interface AS THE PROXY, auditing
claim vs delivery at every stop (his commission, 2026-07-23: "take the R2 revision and
automate putting it through its paces via the proxy of the interface" + "click every
button and see what it claims to do versus what it does").

The driver is GENERAL: parameterized over corpus and base URL; paper_falqon r2 is the
first instance, never the scope. It drives the LIVE scanner (his law: test in the user's
environment — a spawned twin writes the same ledgers anyway), with every write-path probe
attributed ``by: r2-paces-probe`` (the actor law) and every state-mutating verb run
probe-then-reverse so the stores end net-clean.

Evidence contract (one producer, this file): ``evidence/r2_paces_<date>/``
  * ``shots/<leg>-<control>-{before,after}.png``
  * ``paces.jsonl``  — one row per control: claim, delivery observed, verdict
                       PASS|FAIL|PARTIAL|SKIP (a skipped row is NAMED, never silent)
  * ``verdict.json`` — the rollup + the store-cleanliness fence (git diff before/after)
A FAIL additionally banks a friction row through the ONE sanctioned gate
(POST /corpus/friction), chain-of-custody carried.

Geometry grading rides every leg (his geometric frame, L0–L5): the grammar checks assert
no horizontal scroll, the context header, the lit journey stage — and the leg probes
assert the focal laws where they are testable (navigation lands focus; counts agree).

Run:  python scripts/r2_paces.py --corpus paper_falqon [--legs A,D] [--base http://127.0.0.1:8770]

Exit: 0 every graded row passed · 1 a graded FAIL · 3 REFUSED TO GRADE (the scanner
or playwright was absent — nothing was measured, nothing was written).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_probe import (  # noqa: E402
    REFUSAL_EXIT,
    _split,
    normalize,
    port_open,
    probed,
    refusal_line,
    resolve_service,
)

REPO = Path(__file__).resolve().parent.parent
PROBE_ACTOR = "r2-paces-probe"


# --------------------------------------------------------------------------- #
# evidence
# --------------------------------------------------------------------------- #
class Evidence:
    """The one producer of the paces evidence dir."""

    def __init__(self, base_url: str, corpus: str) -> None:
        stamp = _dt.date.today().isoformat()
        self.dir = REPO / "evidence" / f"r2_paces_{stamp}"
        self.shots = self.dir / "shots"
        self.shots.mkdir(parents=True, exist_ok=True)
        self.rows_path = self.dir / "paces.jsonl"
        self.base_url = base_url
        self.corpus = corpus
        self.counts = {"PASS": 0, "FAIL": 0, "PARTIAL": 0, "SKIP": 0}
        self.tier_counts: dict[str, dict[str, int]] = {}

    def chair_pending(self, leg: str, what: str) -> None:
        """Mint the leg's CHAIR row as PENDING — the acceptance only he can flip. Pending
        is not green: the rollup carries it until his grade lands (with his words)."""
        self.row(leg, f"{what}:chair", "does it glide (his epigraph — the acceptance bar)",
                 "awaiting his chair", "PENDING", tier="chair")

    def row(self, leg: str, control: str, claim: str, delivered: str,
            verdict: str, shots: list[str] | None = None, tier: str = "floor",
            **extra) -> None:
        """One verdict row. ``tier`` names WHICH kind of judgment this is (his law —
        green-at-one-tier is never good-overall):
          floor    — mechanical: the mechanism matches the promise; nothing more.
          stranger — a hold-out walker's judged narrative against the geometric laws.
          chair    — HIS grade; minted PENDING by the driver, only he flips it.
        A leg is done when all three are; the rollup keeps them separate."""
        assert verdict in self.counts or verdict == "PENDING", verdict
        assert tier in ("floor", "stranger", "chair"), tier
        self.counts[verdict] = self.counts.get(verdict, 0) + 1
        self.tier_counts.setdefault(tier, {}).setdefault(verdict, 0)
        self.tier_counts[tier][verdict] += 1
        rec = {"ts": _dt.datetime.now().isoformat(timespec="seconds"),
               "leg": leg, "control": control, "tier": tier, "claim": claim,
               "delivered": delivered, "verdict": verdict,
               "shots": shots or [], **extra}
        with self.rows_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tag = {"PASS": "ok", "FAIL": "XX", "PARTIAL": "~~", "SKIP": "--",
               "PENDING": ".."}[verdict]
        print(f"  {tag} [{leg}] {control}: {verdict}" + (f" — {delivered[:110]}" if verdict != "PASS" else ""))
        if verdict == "FAIL":
            self._bank_friction(leg, control, claim, delivered)

    def _bank_friction(self, leg: str, control: str, claim: str, delivered: str) -> None:
        payload = {
            "kind": "friction", "owning_layer": "interface", "by": PROBE_ACTOR,
            "corpus": "design-interface",
            "node": f"surface:{leg}/{control}",
            "value": f"CLAIM: {claim} // DELIVERED: {delivered}",
            "chain": ["r2 paces (his 2026-07-23 commission)", f"leg {leg}", control],
        }
        try:
            req = urllib.request.Request(
                self.base_url + "/corpus/friction",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as r:
                r.read()
        except Exception as e:  # noqa: BLE001 — the audit continues; the miss is in the row
            print(f"     (friction bank failed: {e})", file=sys.stderr)

    def finish(self, fence_before: str, fence_after: str) -> dict:
        rollup = {"ts": _dt.datetime.now().isoformat(timespec="seconds"),
                  "corpus": self.corpus, "counts": self.counts,
                  "tiers": self.tier_counts,
                  "ledger_fence": {"before": fence_before, "after": fence_after},
                  "rows": str(self.rows_path.relative_to(REPO))}
        (self.dir / "verdict.json").write_text(
            json.dumps(rollup, indent=1, ensure_ascii=False), encoding="utf-8")
        return rollup


def _ledger_fence() -> str:
    """The tracked-ledger fence: what the paces run is allowed to move is attributed and
    net-clean; everything else must not move. Captured before and after."""
    out = subprocess.run(
        ["git", "diff", "--stat", "--", "corpus_friction", "contract",
         "paper_falqon/manuscript/feedback"],
        cwd=REPO, capture_output=True, text=True)
    return out.stdout.strip()


def _get_json(base: str, path: str):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


# --------------------------------------------------------------------------- #
# the shared grammar check (the weld's bar, executed at every stop)
# --------------------------------------------------------------------------- #
GRAMMAR_JS = """() => {
  const lit = [...document.querySelectorAll('.hy-stage.on, .hy-stage.on-door')]
    .map(a => (a.querySelector('.st-t')||a).textContent.trim());
  const from = document.querySelector('.hy-from');
  return {
    shell: !!document.querySelector('#hy-shell'),
    hymn: !!document.querySelector('link[href*="hymn.css"]'),
    hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    context: !!document.querySelector('#hy-context'),
    lit,
    fromOk: !from || !/\\//.test(from.textContent.replace('← from','')),
  };
}"""


def grammar_stop(pg, ev: Evidence, leg: str, name: str, lit_stage: str | None) -> bool:
    g = pg.evaluate(GRAMMAR_JS)
    problems = []
    if not g["hymn"]:
        problems.append("hymn.css absent")
    if g["hscroll"]:
        problems.append("horizontal scroll at this width")
    if not g["context"]:
        problems.append("context header missing")
    if lit_stage and not any(lit_stage in t for t in g["lit"]):
        problems.append(f"stage '{lit_stage}' not lit (lit: {g['lit']})")
    if not g["fromOk"]:
        problems.append("return door speaks a raw path")
    claim = "the surface wears the one grammar (hymn, no h-scroll, context header, lit stage, journey doors)"
    if problems:
        ev.row(leg, f"{name}:grammar", claim, "; ".join(problems), "FAIL")
        return False
    ev.row(leg, f"{name}:grammar", claim, "grammar holds", "PASS")
    return True


def shot(pg, ev: Evidence, leg: str, name: str) -> str:
    rel = f"shots/{leg}-{name}.png"
    pg.screenshot(path=str(ev.dir / rel), full_page=False)
    return rel


# --------------------------------------------------------------------------- #
# LEG A — dashboard + journey: counts tell one truth
# --------------------------------------------------------------------------- #
def leg_A(pg, ev: Evidence, base: str, corpus: str) -> None:
    print("\n== LEG A: dashboard + journey (one truth for the counts) ==")
    pg.goto(f"{base}/?corpus={corpus}", wait_until="domcontentloaded")
    pg.wait_for_selector("#hy-shell", timeout=15000)
    time.sleep(0.8)
    shot(pg, ev, "A", "dashboard")
    grammar_stop(pg, ev, "A", "dashboard", "Home")

    # the journey badge vs the desk's own inventory — the B2 regression probe:
    # whatever the Desk stage word claims is waiting must equal what /desk lists.
    stages = pg.evaluate("""() => [...document.querySelectorAll('.hy-stage')].map(a => ({
        t: (a.querySelector('.st-t')||a).textContent.trim(),
        w: ((a.querySelector('.st-w')||{}).textContent||'').trim()}))""")
    desk_word = next((s["w"] for s in stages if "Desk" in s["t"]), "")
    badge_n = 0
    for tok in desk_word.split():
        if tok.isdigit():
            badge_n = int(tok)
            break
    # the badge's claim is cross-surface: it can only be judged against /desk itself.
    # Until leg F runs that comparison, this row is PARTIAL — a deferred check is never
    # a green (his law: green does not mean passed; started is not done).
    forks = _get_json(base, f"/shared/journey?corpus={corpus}")
    ev.row("A", "journey:desk-badge-vs-desk",
           "the Desk stage word counts exactly what the desk will show for this corpus",
           f"badge word: '{desk_word or '(empty)'}' (n={badge_n}); cross-check owed to leg F",
           "PARTIAL",
           note="resolved at leg F: badge n must equal the desk's owed rows for this corpus")

    # live state words ride the spine (the weld's bar)
    worded = sum(1 for s in stages if s["w"])
    ev.row("A", "journey:state-words",
           "live per-stage state words ride the spine (>=4 worded stages)",
           f"{worded} stages worded: " + " | ".join(f"{s['t']}:{s['w']}" for s in stages if s["w"]),
           "PASS" if worded >= 4 else "FAIL")
    ev.chair_pending("A", "dashboard")


# --------------------------------------------------------------------------- #
# LEG B — /conceptric (Grow): the graph chart's doors answer
# --------------------------------------------------------------------------- #
def leg_B(pg, ev: Evidence, base: str, corpus: str) -> None:
    print("\n== LEG B: /conceptric (Grow) ==")
    pg.goto(f"{base}/conceptric?corpus={corpus}", wait_until="domcontentloaded")
    pg.wait_for_selector("#hy-shell", timeout=15000)
    time.sleep(1.2)
    shot(pg, ev, "B", "conceptric")
    grammar_stop(pg, ev, "B", "conceptric", "Grow")

    # L4 structure-mirrors-the-object probe (his fifth ruling): is the conceptric
    # presented as a GRAPH (links visible) or as a list? Graded honestly — today this
    # is expected to FAIL and that failure is the banked commission for the map rework.
    geom = pg.evaluate("""() => ({
        svgEdges: document.querySelectorAll('svg line, svg path[class*="edge"], svg [class*="link"]').length,
        canvases: document.querySelectorAll('canvas').length,
        listRows: document.querySelectorAll('[class*="row"], li').length,
        bodyChars: document.body.innerText.length })""")
    drawn = geom["svgEdges"] > 0 or geom["canvases"] > 0
    ev.row("B", "conceptric:links-visible",
           "the conceptric map is defined by its links — the primary chart draws them (L4)",
           f"svg edges: {geom['svgEdges']}, canvases: {geom['canvases']}, "
           f"list rows: {geom['listRows']}",
           "PASS" if drawn else "FAIL")
    ev.chair_pending("B", "conceptric")


# --------------------------------------------------------------------------- #
# LEG C — /storyboard (Shape): the launch doors' contracts
# --------------------------------------------------------------------------- #
def leg_C(pg, ev: Evidence, base: str, corpus: str) -> None:
    print("\n== LEG C: /storyboard (Shape) ==")
    pg.goto(f"{base}/storyboard?corpus={corpus}", wait_until="domcontentloaded")
    pg.wait_for_selector("#hy-shell", timeout=15000)
    time.sleep(1.2)
    shot(pg, ev, "C", "storyboard")
    grammar_stop(pg, ev, "C", "storyboard", "Shape")

    # the actor law at the launch door: an unattributed fire must 422 and bank NOTHING.
    import urllib.error
    payload = json.dumps({"corpus": corpus, "action": "re-projection"}).encode()
    req = urllib.request.Request(base + "/storyboard/run/launch", data=payload,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            code, body = r.status, r.read().decode()[:200]
    except urllib.error.HTTPError as e:
        code, body = e.code, e.read().decode()[:200]
    ev.row("C", "launch:actor-law",
           "an unattributed launch is refused (422) — a fire is never silently defaulted",
           f"HTTP {code}: {body}",
           "PASS" if code == 422 else "FAIL")

    # the roster GET is a pure read (arms nothing)
    try:
        roster = _get_json(base, f"/storyboard/run/launch?corpus={corpus}")
        ok = isinstance(roster, dict)
        ev.row("C", "launch:roster-read",
               "GET /storyboard/run/launch is a pure roster read (previews, banks nothing)",
               json.dumps(roster)[:150], "PASS" if ok else "FAIL")
    except Exception as e:  # noqa: BLE001
        ev.row("C", "launch:roster-read",
               "GET /storyboard/run/launch is a pure roster read (previews, banks nothing)",
               f"read failed: {e}", "FAIL")
    ev.chair_pending("C", "storyboard")


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
LEGS = {"A": leg_A, "B": leg_B, "C": leg_C}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", default="paper_falqon")
    ap.add_argument("--base", default="",
                    help="scanner base URL; default = discovered "
                         "($LAPLACE_WALK_URL, else the known local default)")
    ap.add_argument("--legs", default="A", help="comma list, e.g. A,D")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    args = ap.parse_args()

    # ── the refusal fence ────────────────────────────────────────────────────────
    # NOTHING below this fence may run without a real service and a real browser, and
    # nothing above it may write: the evidence dir is not created, no verdict is
    # touched. A driver that cannot drive says so and grades nothing.
    #
    # An EXPLICIT --base is honored as the author's instruction, but is still probed
    # (sub-second) before the run commits to it — a typo refuses instead of spending
    # ten seconds per request discovering the same absence.
    if args.base:
        base = normalize(args.base)
        host, port = _split(base)
        live = port_open(host, port)
        tried = [f"--base {base} ({'listening' if live else 'nothing listening'})"]
    else:
        base = resolve_service()
        live = base is not None
        tried = probed()
    if not live:
        print(refusal_line("R2 PACES", "the scanner", tried), file=sys.stderr)
        print("  serve it (scripts/serve_walk_tailnet.sh, or `python -m laplace.web.scanner "
              "--port 8770`) or name it in $LAPLACE_WALK_URL, then run this again.",
              file=sys.stderr)
        return REFUSAL_EXIT

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print(refusal_line("R2 PACES", "playwright (the browser this driver drives)",
                           [f"import playwright under {sys.executable}: {exc}"]),
              file=sys.stderr)
        return REFUSAL_EXIT

    # the service is up; is it the scanner? a listening socket is not an API.
    try:
        _get_json(base, "/shared/views")
    except Exception as e:  # noqa: BLE001
        print(refusal_line("R2 PACES", f"the scanner API at {base}",
                           [f"GET {base}/shared/views: {e}"]), file=sys.stderr)
        return REFUSAL_EXIT

    args.base = base

    # The LAST absence that can make this run vacuous: a chromium that will not
    # launch. Proved BEFORE the evidence dir exists, so a refusal leaves no empty
    # r2_paces_<date>/ behind — the launched browser is then the one the legs drive,
    # so the genuine path pays for exactly one launch, as before.
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:                                      # noqa: BLE001
            print(refusal_line("R2 PACES", "a launchable chromium",
                               [f"pw.chromium.launch() under {sys.executable}: "
                                f"{str(exc)[:200]}"]), file=sys.stderr)
            return REFUSAL_EXIT

        ev = Evidence(args.base, args.corpus)
        fence_before = _ledger_fence()
        pg = b.new_page(viewport={"width": args.width, "height": args.height})
        errors: list[str] = []
        pg.on("pageerror", lambda e: errors.append(str(e)))

        for leg in [x.strip().upper() for x in args.legs.split(",") if x.strip()]:
            fn = LEGS.get(leg)
            if fn is None:
                ev.row(leg, "leg", f"leg {leg} requested", "not implemented yet", "SKIP")
                continue
            fn(pg, ev, args.base, args.corpus)

        ev.row("*", "session:page-errors",
               "zero uncaught page errors across the walked legs",
               errors[0] if errors else "clean",
               "PASS" if not errors else "FAIL")
        b.close()

    rollup = ev.finish(fence_before, _ledger_fence())
    print("\n== ROLLUP ==")
    print(json.dumps(rollup["counts"], indent=1))
    return 0 if rollup["counts"]["FAIL"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
