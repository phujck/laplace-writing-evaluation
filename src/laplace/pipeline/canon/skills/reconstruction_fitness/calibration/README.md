# The G1 faithfulness calibration set

The sealed semantic adjudicator (`../scripts/adjudicate_sealed.py`) is the meter that replaces the
void 2-shingle proxy. **A meter you have not validated cannot validate anything** — so before it
gates the climb, it gates itself against this set.

Each item is an `{original, ghost}` pair whose ground-truth property is **known** (`expected.json`),
drawn from real engine content so the calibration is meaningful, not synthetic. The harness holds
the truth and checks the meter's **raw signals** — the meter itself emits no fate label (FORK-FATES
is the author's, deferred):

- **faithful** — the ghost preserves the meaning, often in different words. The meter must show
  ~nothing lost, nothing added. (`faithful_paraphrase`, `faithful_companion` — the low-overlap
  cases the void meter mis-scored as confabulated.)
- **partial** — the spine survives, the finer flesh is lost, in a structured way that recurses. The
  *target band*, not a failure. (`partial_spine`.)
- **confabulated + PLANT** — the ghost asserts a specific falsehood we inserted. The meter MUST
  surface it in `added`. A meter that misses a plant is void; a meter never tried against a plant
  cannot pass. (`confab_people_ratchet` — the covenant ratchet inverted, the morally load-bearing
  catch; `confab_rho_estimator` — the estimator mechanism inverted.)

## Running the gate (Phase 2, cloud)

For each item: build the brief, spawn N model/temp-diverse **sealed** adjudicators on it, drop each
returned verdict JSON into the item's dir (`v1.json`, `v2.json`, …). Then:

```
python ../scripts/adjudicate_sealed.py gate .
```

The gate aggregates each item's ensemble into the joint and scores: calibration agreement with the
known labels, every plant caught, ensemble agreement above threshold. **PASS un-voids the scalar
gate** the first rung had to throw away.

The labels here brush **FORK-FATES** (the author's) — they are the proto-vocabulary, his to correct.
