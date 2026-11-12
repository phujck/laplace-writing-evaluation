---
name: deck_applet
description: "[EXPERIMENTAL] The web-asset bench - the talks/web counterpart of figure_standard. Build an interactive HTML applet (a Slidev embed or an in-site widget) on one shared harness instead of hand-cloning it: a fill-parent no-scroll shell, a 2x-DPR crisp-canvas + device-pixel text helper, a ResizeObserver re-fit, a host-inherited dark palette, ONE of the two interaction patterns (discrete stepper / continuous knob) with talk presets, and a parametrised headless-playwright verify that renders every state to PNG and asserts no overflow, clean console, painted canvas. visual_director hands down to it."
---
# deck_applet

**Status: [EXPERIMENTAL]** - forged 2026-06-02 from the talk-finetune session, where the same applet harness was hand-cloned ~6 times (model-loop, two-level phenomenology, reservoir schematic, viable-window, coarse-graining, title art). The boilerplate is identical every time and the failure modes recur every time (grainy fonts, scrollbars in the slide, labels colliding, a blank canvas). This skill makes the harness canon so the next applet starts from a passing bench, not a blank file.

## Purpose
An interactive web asset is a figure that runs. [`figure_standard`](canon://skills/figure_standard.md) is the bench for a static figure; this is the bench for a live one. The asset is load-bearing or it is gone (the [Voice](canon://aesthetics/voice_and_style.md) - the figure lands a point and stops), and it must read as one object with its host (the [talks axioms](canon://domains/talks/axioms.md) - substrate decides the theme, furniture matches the figure's own colour). The hard part is never the idea, it is the harness: an applet that does not fit the frame, renders grainy, or paints blank fails no matter how good the idea. This skill carries the harness so the build is the asset, not the plumbing.

Most applets are also self-modifying in the sense [`clean_room_check`](canon://skills/clean_room_check.md) cares about - the author of the applet cannot trust their own eye on whether it renders right in the deck. So the verify harness is part of the skill, not an afterthought: an applet is not done until a headless render of every state comes back clean.

## When to use it
- A Slidev slide needs a live embed (an explorable phase portrait, a stepped derivation, a settling field) - `visual_director` decided **embed, not bake** for that slide and hands the asset spec down here.
- An in-site widget must inherit the host page's aesthetic (the `viz/` integrators, an engine-on-the-page graph).
- Title art or a schematic that is generated rather than reused - the algorithmic-art carve-out below applies.

Not for a static manuscript figure (that is [`figure_standard`](canon://skills/figure_standard.md)) and not for a finished non-interactive clip (bake it - `visual_director`'s embed-vs-bake call). The trigger is *live interactivity is the value*.

## The harness (the seven things every applet needs - copy them, do not reinvent)
The v3 seeds (`viz/*.html`, `tools/{shoot,verify-*}.mjs`) were **not carried into this repo** - the
only deck sources on disk are `talks/laws-of-learning-sources/` and `talks/explaining-eigen/`,
markdown only. Rules 1-7 below are therefore self-contained: the shell CSS, the DPR resize function,
the ResizeObserver line, the IntersectionObserver gate and the playwright assertion list are inlined
verbatim, so an applet can be built from this text alone with no seed to lift.

1. **Fill-parent, no-scroll shell.** The deck frame is fixed-height: the applet must sit in it seamlessly with no scrollbars. `*{box-sizing:border-box;margin:0;padding:0}`, `html,body{width:100%;height:100%;overflow:hidden}`, body `display:flex;flex-direction:column`. The stage is `position:relative;flex:1 1 auto;min-height:0`; the canvas is `position:absolute;inset:0;width:100%;height:100%`. The slide carries the title - the applet carries at most a thin control strip.
2. **Crisp canvas at 2x DPR.** Size the backing store to `devicePixelRatio` and scale the context, or text and lines are grainy on a projector and on HiDPI:
   ```js
   function resize(){
     DPR = Math.max(1, window.devicePixelRatio || 1);
     const r = stage.getBoundingClientRect();
     W_ = Math.round(r.width); H_ = Math.round(r.height);
     cv.width = Math.max(1, Math.round(W_*DPR)); cv.height = Math.max(1, Math.round(H_*DPR));
     ctx.setTransform(DPR,0,0,DPR,0,0); layout();
   }
   ```
   **Guard every draw against a transient 0-or-negative size.** The applet can be measured before its iframe has a real box (the eager-init case below, a pre-reveal layout). Clamp the backing store to `>= 1` as above, return early from the draw when `W_ <= 0 || H_ <= 0`, and clamp any rounded-rect / arc radius to `>= 0` (`Math.max(0, r)`). A negative-radius `arcTo` *throws*, and the throw aborts the first paint - the applet then shows the frame but never the figure. This was the v3 root cause of "the embed loads but the interactive asset does not".
   Pair the canvas with a **device-pixel text helper** that rounds to the integer CSS-pixel grid: `function text(s,x,y,font,fill,align,baseline){ ctx.font=font; ctx.fillStyle=fill; ctx.textAlign=align||'left'; ctx.textBaseline=baseline||'alphabetic'; ctx.fillText(s, Math.round(x), Math.round(y)); }`. Use a serif italic (`'Cambria Math','Georgia',serif`) for maths variables so an equation reads as an equation, not as UI text.
3. **ResizeObserver re-fit.** The iframe box changes after load (a lazy v-click reveal, a layout settle, presenter zoom) with **no** window `resize` event. Observe the stage element directly: `if (window.ResizeObserver) new ResizeObserver(resize).observe(stage);` - and keep the `window` resize listener too. Skipping this is the single most common "looks fine locally, broken in the deck" bug.
4. **Host-inherited dark palette.** Read the colours from the host deck/site, do not pick by taste. The Laplace decks are dark (`BG '#0a0d12'`, `INK '#e6e8ee'`, `MUTED '#8b92a1'`); the loop legs reuse the SAME accent across applets (gold control, vermilion environment, green fast-state, blue measurement) so every applet reads as one object. Substrate decides the theme - a dark deck gets dark assets, never a light widget fighting the slide.
5. **One interaction pattern, chosen per asset** - and only one. An applet that is both a stepper and an explorer carries two ideas and lands neither (one idea per slide).
   - **Discrete stepper** - a prev/next reveal that walks an argument one beat at a time (the model-loop's 8-step derivation). A thin control strip: `back` / `step` buttons, a pip rail (one dot per step, the active lit, click to jump), a `n / N` counter, an optional `play`. Drive it from a single `gotoStep(n)` the verify harness can call. Each step lights the relevant element and reveals its panel with a settle (`appear` 0->1).
   - **Continuous knob** - sliders driving a live simulation the audience can push (the viable-window explorer, the two-level phenomenology). **Ship one-click presets** for the talk (e.g. "stable" / "edge of chaos") so the presenter lands the regime without fiddling sliders live.
6. **Parametrised playwright verify.** An applet is not done until it renders clean headless. Adapt `tools/verify-<name>.mjs` (seed: `verify-model-loop.mjs`): load the HTML `file://` at the deck viewport (`1280x720`, `deviceScaleFactor: 2`), then assert, capturing a PNG of every state for the eye check:
   - **no console / page errors** (`page.on('console'...)`, `page.on('pageerror'...)`);
   - **no scroll overflow** - `scrollWidth/Height <= clientWidth/Height + 1` (the no-scroll rule, checked);
   - **the canvas painted** - sample the pixel buffer, count non-background pixels, fail on a blank/black frame;
   - **every state is reachable and correct** - walk all stepper steps (the right node lights, the panel finished revealing, a live orbit actually advanced) or exercise each preset; confirm the buttons/keyboard drive it.
   Print `{pass, problems, shots}` and set the exit code. This is the [`clean_room_check`](canon://skills/clean_room_check.md) discipline in miniature - "green" means it ran, and the harness is the external checker the applet author's own eye cannot replace.
7. **Load the embed on-screen, once, at real size - via an explicit IntersectionObserver.** Do not init the applet on `DOMContentLoaded` and do not lean on the iframe's native `loading="lazy"`. Eager init runs every applet at slide-build time when its iframe is a transient 0-size box (the guard in rule 2 keeps it from throwing, but it still inits blank and never repaints). Native lazy-load *misfires inside Slidev's CSS-scaled slide* - the transform fools the heuristic and the asset intermittently never loads at all. Gate the init on a real intersection instead: `new IntersectionObserver((es,o)=>{ if(es[0].isIntersecting){ o.disconnect(); resize(); start(); } }).observe(stage);`. Fire once (disconnect on first hit), `resize()` first so the first paint is at the on-screen size, then start. This and the 0-size guard are the two halves of the v3 "frame loads, asset does not" fix.

## The render-and-look loop (the agent's inner loop)
`tools/shoot.mjs` is the deck-level companion to the per-applet verify: a one-shot cached `slidev build` served on an ephemeral port, driven by playwright to slide N (`?clicks=c` for a reveal state) at 2x DPR, one PNG out. Edit `slides.md` or the applet -> `node tools/shoot.mjs <n>[.<clicks>]` -> Read the PNG -> iterate. Build-and-shoot, not a long-running dev server: a persistent server is a flake/hang trap in an agent loop. No deck in this repo ships this script today; the loop above is the contract for the one that does.

## The algorithmic-art carve-out
Generated art (a title field, a schematic) **keeps the seeded-determinism discipline** of [`algorithmic-art`](anthropic-skills:algorithmic-art) - a seeded RNG so the same seed gives the same frame, parameters explored deliberately, original work. It **drops that skill's gallery shell** - the light theme, the Poppins sidebar, the seed-navigation chrome. An in-deck or in-site asset inherits the host aesthetic (rule 4): dark palette, no gallery frame, no sidebar. Build the field on this harness (rules 1-3, 6), seed it deterministically, and let the deck supply the theme. Title-art rule, from the session: the title slide is title + name + art only - **no gnomic subtitle, no gloss on the art** (the [Voice](canon://aesthetics/voice_and_style.md) - state the claim, do not narrate the visual).

## Two asset categories that need a publish path
- **A live view that must ship to a static site.** When the asset is a genuinely live tool (the engine conceptric, driven by `laplace.viewer`), the published deck cannot run the local server. Either bake a **static client-side export** (the data baked into the page, the renderer reused - the proven seed is `laplace/scripts/bake_graph_snapshot.py`, which turns canon/substrate into a static clickable graph) or render to a clip. The live tool is the local-build ceiling; the published artifact is its server-free projection. Decide this at the asset handoff, not at deploy.
- **Porting a live tool to a server-free deck embed** (the concrete form of the bullet above). A genuinely live tool (the engine conceptric viewer) cannot run its server inside a published static deck. The proven v3 port keeps the interaction and drops the server: **inline the graph JSON into a `<script type="application/json">` block** in the embed and read it from the DOM, then strip the fetch / comment / polling machinery that talked to the local backend. The interaction survives intact - zoom a node to reveal its subnetwork, the flow side-view - with no server behind it. The live tool is the local-build ceiling; the inlined-data embed is its server-free projection. Decide it at the asset handoff, and [`talk_ledger`](canon://skills/talk_ledger.md) then verifies the projection like any other applet.
- **The names-only facsimile.** A static stand-in for a live interactive (an `engine-facsimile.html` showing structure without the live engine) is a distinct asset category - honest about being a facsimile, built on this harness for crispness and fit, never passed off as the live thing. The session's standing direction: prefer the real baked graph over a hand-built facsimile where the data exists.

## Operations
- Gitignore the build scratch (`.shoot/`, `dist/`) and keep the published build untouched while iterating - the harness is additive in the deck dir.

## Relationship to neighbours
Handed down to by [`visual_director`](canon://skills/visual_director.md): the director decides per slide *embed-vs-bake, substrate, one idea*, and when the call is **embed a live asset** the asset is built here. It is the live-figure peer of [`figure_standard`](canon://skills/figure_standard.md) (static figures) and borrows [`clean_room_check`](canon://skills/clean_room_check.md)'s external-verify stance for its render harness. [`talk_smith`](canon://skills/talk_smith.md) names it as the bench its asset-handoff stage hands down to.

## Backing
None yet. The natural backing is a scaffolder that writes a passing skeleton applet - the no-scroll shell + 2x-DPR canvas + ResizeObserver + palette constants + an empty `gotoStep`/`presets` hook + a matching `verify-<name>.mjs` - so a new applet starts green and the author fills in only the drawing. Lift it from the session seeds once they prove on a second deck.
