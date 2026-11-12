---
name: talk_ledger
description: The deck-aware talk verify - the refine stage of talk_smith. Verifies the RENDERED talk, not the source alone: the no-slop voice in the slide prose (via the masking detector lint_voice.py), every live applet rendering (the per-applet verify-*.mjs harnesses), and optionally the deployed deck under its real base. PASS/FAIL/SKIP aggregate.
---

# Talk Ledger

The refine stage of [`talk_smith`](canon://skills/talk_smith). A talk is the manuscript voice in a freer medium, so its checks are deck-aware - the source alone does not tell you the deck renders. This runs the three a deck needs, all exercised by hand the session it was forged:

1. **Voice** - the masking slop detector `lint_voice.py` over the slide source and the applets, masking code, markup, KaTeX, and Slidev frontmatter so it flags only prose. (The `voice_linter` SKILL's enforcement mandate was retired by the 2026-07-09 rebuild ruling; the script survives as a detector under this skill and `blind_reader`, which is what runs here.)
2. **Applets** - every `tools/verify-*.mjs` the deck ships (per-applet headless render: no console error, canvas paints, no overflow, the stepper walks).
3. **Deploy** (optional, `--deploy`) - `tools/verify-deploy.mjs`: load the built deck under its real base and fail on a console error or a broken same-origin request. The slow check - it builds, serves, and drives a browser.

**A leg that could not run is named, never dropped.** No `tools/verify-*.mjs` and no applets under
`public/viz` reports the applet leg as `SKIP`; applets shipped with no harness for them is a `FAIL`;
`--deploy` with no `tools/verify-deploy.mjs` is a printed `SKIP`. The aggregate line says
`LEDGER: PASS with N leg(s) SKIPPED` whenever the sweep was partial, so a green exit cannot narrate
checks that did not happen.

## Usage
```
laplace_run(skill="talk_ledger", target="<deck-dir>")
laplace_run(skill="talk_ledger", target="<deck-dir>", args=["--strict-voice"])
laplace_run(skill="talk_ledger", target="<deck-dir>", args=["--deploy"])
```

Default skips the slow deploy check so it fits a bounded runner. Exit 2 on a bad target, 1 if any check fails, 0 if all pass or skip. The deck must ship a `slides.md`; the `tools/verify-*.mjs` harnesses that the [`deck_applet`](canon://skills/deck_applet) bench emits are what the applet leg drives. Voice is advisory by default (the deck author may keep a deliberate construction); pass `--strict-voice` to gate on it.

## The render harnesses it leans on
The ledger does not render the deck itself - it drives harnesses the deck dir ships:
- **`tools/verify-*.mjs`** - one per applet: headless render, no console error, canvas paints, no overflow, the stepper walks.
- **`tools/verify-deploy.mjs`** - serve the *repo root* the way GitHub Pages does (root `404.html`, hash routing) and drive a browser over the built deck, failing on a console error or a broken same-origin request. This is the deploy check above - the one that catches a wrong `--base`, a missing asset, a route that 404s under the static host.
- **`tools/deck-slide-shot.mjs`** - a reload-based per-slide render (navigate, full reload, screenshot one slide), the deck-level companion to the per-applet `verify-*.mjs`. The reload per slide is deliberate - it renders each slide from a clean state, so an applet's on-screen-load (the [`deck_applet`](canon://skills/deck_applet) IntersectionObserver gate) actually fires the way it does for a viewer landing on that slide.

**None of these exist in this repo today.** The v3 deck work they came from was not carried: the
only deck sources on disk are `talks/laws-of-learning-sources/` and `talks/explaining-eigen/`, both
markdown only - no `tools/`, no `public/viz`, no `.mjs`. Until a deck ships them the applet and
deploy legs are dormant and the ledger says so in its report rather than passing over them. Treat
the three bullets above as the contract a deck must meet to be verified, not as files you can read.
