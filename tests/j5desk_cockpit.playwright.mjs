// ═══════════════════════════════════════════════════════════════════════════
// RETIRED (W-DESK, 2026-07-22) — superseded by tests/engine_desk.playwright.mjs.
//
// The J5 harness proved the desk's ORIGINAL geometry: a #desk-strata chip row filtering
// #desk-rows cards, each toggling a four-zone cockpit IN PLACE, with the ⓘ info tags and
// arm-to-fire on the destructive verbs. W-DESK joined the desk to the ONE INSTRUMENT
// (engine.mjs): the desk now rests at a composed what-needs-him-now BRIEF, materializes a
// class on a chip (or pre-pins a deep-linked row, B.5), and opening a row REALLOCATES the
// four-zone cockpit with a named return door. The old selectors (#desk-strata .dk-chip,
// #desk-rows .dk-card, .dk-card.open .dk-cockpit) no longer exist, so this walk cannot be
// repaired in place — its intent is re-proven, under the new grammar, by engine_desk:
//
//   · strata chip → materialize a class's rows (the counts law: chip == reachable rows)
//       → engine_desk "opening the … chip materialised its rows … the counts law holds";
//   · descend into a row → the four-zone cockpit + the WHOLE referent, inline
//       → engine_desk "the cockpit renders .zone-* … the WHOLE referent rendered inline";
//   · act through the ONE mutation door, actor-attributed
//       → engine_desk "clicking confirm fired exactly ONE POST /desk/act … carried the actor";
//   · arm-to-fire on the destructive verbs
//       → engine_desk "one click on a destructive verb did NOT fire … it only armed".
//
// Kept as a named retirement (not deleted) so what-moved-where stays legible; it exits 0
// without asserting the vanished geometry — never a false green (it claims no coverage, it
// names its successor).
console.log('RETIRED (W-DESK): the J5 desk-cockpit geometry moved to the one instrument — ' +
  'coverage now in tests/engine_desk.playwright.mjs.');
process.exit(0);
