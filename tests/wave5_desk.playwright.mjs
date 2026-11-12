// ═══════════════════════════════════════════════════════════════════════════
// RETIRED (W-DESK, 2026-07-22) — superseded by tests/engine_desk.playwright.mjs.
//
// This walk proved the desk's ORIGINAL geometry (W5): a #desk-strata filter-chip row,
// #desk-rows decision cards toggling a four-zone cockpit IN PLACE, and the per-card ✎
// rule mouth. W-DESK joined the desk to the ONE INSTRUMENT (engine.mjs): the desk now
// rests at a composed what-needs-him-now BRIEF, materializes a class on a chip (or
// pre-pins a deep-linked row, B.5), and opening a row REALLOCATES the four-zone cockpit
// with a named return door. The old selectors (#desk-strata .dk-chip, #desk-rows
// .dk-card, .dk-card.open .dk-cockpit) no longer exist, so this walk cannot be "repaired"
// in place — its intent is re-proven, under the new grammar, by engine_desk:
//
//   · the cockpit's four zones + the WHOLE referent (proxy verdict included) render in
//     the reallocated focus  → engine_desk "the cockpit renders .zone-* … the WHOLE
//     referent rendered inline";
//   · arm-to-fire on a destructive verb (one click never fires) → engine_desk "one click
//     on a destructive verb did NOT fire … it only armed";
//   · a live write door fires POST /desk/act with the actor → engine_desk "clicking
//     confirm fired exactly ONE POST /desk/act … carried the actor";
//   · the ✎ rule-in-place up-loop (D16) lands OPEN on the desk → tests/waveF_desk_landing
//     (the shared #hy-context header mouth, the canonical bank site, is untouched).
//
// Kept as a named retirement (not deleted) so the history of what moved where is legible;
// it exits 0 without asserting the vanished geometry — never a false green (it claims no
// coverage, it names its successor).
console.log('RETIRED (W-DESK): desk geometry moved to the one instrument — coverage now in ' +
  'tests/engine_desk.playwright.mjs (+ tests/waveF_desk_landing.playwright.mjs for the ✎ up-loop).');
process.exit(0);
