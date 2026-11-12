---
name: conceptric_evolution
description: "Evolve a project conceptric between versions through a CONTRACT, never an ad-hoc rewrite: source verdict banked verbatim, mints/reshapes/deprecations enumerated in an evolution_plan.json, executed as APPEND-ONLY rewire records on the one friction ledger, round-tripped against the contract's own manifest. The versioned-reprojection procedure, mechanised - proven on subset-sum-itqde v2->v3 (2026-07-04) and its 2026-07-08 fold-back."
---
# conceptric_evolution

**Status: PROVEN ONCE, FOLDED ONCE** — authored as a working contract on the
sunset-sum branch (2026-07-04, the v2→v3 Spectral Surfacing evolution: 26 mints,
86 set-projections, 23 edges, 11 essence edits) and validated the hard way on
2026-07-08 when the whole evolution folded back into master's conceptric as a
pure ledger append with an EXACT round-trip (392 → 418 live nodes, every mint
present, zero strays, zero removals). This file is the skill the contract's
`meta.contract: canon://skills/conceptric_evolution` pointed at before it
existed — the reference is now real.

## Why this exists
A conceptric under a live manuscript cannot be rewritten in place when the
author reframes the work (a new organising object, a coordinate change, a
renamed method). An ad-hoc rewrite loses the old frame, breaks the plan mid
projection, and cannot be audited or merged across branches. The evolution
CONTRACT makes the reframe a first-class, versioned, mergeable operation —
the substrate-level half of [feedback grows the conceptric, not the
draft](canon://workflow/core_outward_trunk.md); whether the evolved conceptric
is genuinely integrated afterwards is
[conceptric_coherence](canon://skills/conceptric_coherence)'s axis, and the
re-projection that follows is
[manuscript projection](canon://workflow/manuscript_projection.md)'s.

## The procedure (what the v2→v3 run did, generalised)
1. **Bank the verdict verbatim.** The author's ratified reframe goes to
   `manuscript/evolutions/<from>_to_<to>/sources/<date>_<slug>.md` untouched.
   Supersessions of earlier rulings are NEW dated files beside it, never edits.
2. **Write the contract.** `evolution_plan.json` with `meta.from_version`,
   `meta.to_version`, `meta.source_documents`, `meta.naming_ruling`, and the
   full enumeration: mints (with essence seeds in `_essences.json` and each
   mint's `section_target`), reshapes of existing nodes, deprecations
   (projection.retired — retire projections, do not delete nodes), edges.
3. **Execute as ledger appends.** Every operation becomes a rewire record on
   `corpus_friction/<corpus>.jsonl` (add-node / set-projection / add-edge /
   edit-essence). APPEND-ONLY is the merge guarantee: a branch that evolves a
   conceptric this way can fold back into any line whose ledger is a prefix.
4. **Round-trip against the manifest.** Rebuild the network and diff the live
   node-id set before/after against the contract's own enumeration. Exact or
   stop. (2026-07-08: BEFORE 392, AFTER 418, +26 = the mint list, −0.)
5. **Wire mints to the SHARED spine.** Each mint's `section_ref` points at a
   spine beat that exists on every line (this is what let the C-hinge place all
   26 mints mechanically after the fold). A mint anchored to a branch-local
   beat strands itself.
6. **Keep the contract as the audit trail.** The `evolutions/` directory ships
   with the manuscript forever; the ledger entry in `CONCEPTRIC_LEDGER.md`
   records the fold.

## The laws learned
- **Fold by ledger, never by replay.** Re-running the contract's assembler
  against an evolved store double-applies reshapes and mints duplicate record
  ids. The assembler's OUTPUT (the appended records) is the evolution; git
  moves it between lines.
- **Deprecate projections, keep nodes.** `projection.retired` preserves history
  and lets the plan validator name every stale seat the projection still holds
  (S1/S3/A3 held the retired SSC node on 2026-07-08 and the board's
  inherited-defect gate walked the plan out of it op by op).
- **The plan is downstream.** The contract changes the SUBSTRATE; re-planning
  (placing mints in sections) and re-projection (prose) are separate, later
  moves through the storyboard ledger and the dispatch manifest.
