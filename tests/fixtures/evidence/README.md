# Evidence viewer fixtures, version 1

These compact JSON files are minimised historical representatives of the two
explicit viewer schemas, not complete/current canonical project snapshots.
Their `fixture` metadata pins the originating campaign artifact SHA-256 and
states the selection. Recorded node, source, result and figure identities are
retained verbatim. Referenced companion files are not runtime test dependencies.

The argument excerpt selects the project goal, diamond identity and formal-gap
claims, and the formal repair question, then closes that set over prerequisite
targets. Only relevant chapter membership, documentary support and research
bindings remain. The visual excerpt retains all seven entries with their briefs,
PDF/SVG identities and result bindings. Broad history, long inspection records and
unrelated source catalogues are omitted.

Run from the checkout root, with no producer or campaign directory setup:

```sh
node --test tests/evidence_artifact.test.mjs tests/writing_pdf_links.test.mjs tests/concept_argument.test.mjs tests/concept_argument_navigation.test.mjs
```

The test uses module-relative URLs, so a relocated checkout or portable test
bundle works without a particular working directory. Include this fixture
directory whenever carrying the tests. The existing Unicode continuation test
constructs a JSON payload larger than 65,536 bytes in memory, so these files need
no padding and are not a substitute for that boundary test.

Changes to the historical fixture selection or schema should be deliberate and
versioned. Do not silently regenerate these files from whichever project happens
to be installed, and do not treat retained hashes as current source verification.

## Retained representation coverage

`visual-index.paths.v1.json` is a separate labelled representative of the current
visual-owner shape: manuscript-relative output strings and an exact-path
`output_digests` map. The earlier `visual-index.v1.json` retains the historical
explicit output-object variant. Neither replaces the other. Mixed/contradictory
forms must fail visibly. Current campaign artifacts are additionally checked by
the explicit `check_evidence_current.mjs` command; ordinary tests require only
these shipped fixtures.

The current-artifact command is intentionally separate:

```sh
node tests/check_evidence_current.mjs /absolute/argument-map.json /absolute/visual-index.json
```

Its arguments are exact saved files. It performs bounded read-only UI adapter
checks using local DOM/transport doubles, not live owner fetches or independent
browser acceptance.

`argument-map.v2.json` captures the explicitly observed corrected argument-map/2 shape, including recorded meaning and source detail. The /1 fixture remains unchanged; unknown /3 is not treated as compatible.
