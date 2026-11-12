# The uniform grammar of the writing system

Wave `WRITING-RECONCILIATION-W1`, packet `grammar`, 2026-10-02.

This is the prerequisite every other lane installs. It is one sentence, made structural:

> **A door never names a field without naming the home its value comes from.**

The friction report measured the cost of its absence: 29 of the 74 refusals met writing that
report and 94 of the 210 failures the system has ever recorded are an identity guard whose home
was not named; 20 field names carry 9 values; 6 of those names carry more than one
(`evidence/WRITING_FRICTION_2026-10-01/wave1/synthesis.md` §1.1, `verb-altitude-audit.md` §1.3).

Five files hold the grammar and nothing else does:

| file | what it is |
|---|---|
| `GRAMMAR.md` (this file) | the specification. Its two tables are renders; their row sources are named below. |
| `grammar.py` | the module every lane copies into `src/laplace/`. 58 home kinds, 9 verbs, 4 shapes, 1 comparison. Its `CONCEPTS`/`VERB_CONCEPTS` block is generated — `map_verbs.py` splices it from `mapping.csv`. |
| `map_verbs.py` | the row source for the mapping table, the obtain table and **every count in this document**. Reads the audit's `verb_matrix.csv`, refuses to emit while one audited verb is unassigned. |
| `home_census.py` / `home_census.json` | the measurement that fixed the home list: 33 identity observations on one real project resolve to 16 values. |
| `obtain_census.py` | the measurement that fixed §2.1: which of the 58 homes `identity()` can obtain from the home alone, run against a real project in a real worktree. |
| `test_grammar.py` | the proofs the module owes — including that the declared obtain partition is the behaviour, that every declared guard names the door that compares it, and that the cited `file:line`s are the lines they claim. |

Regenerate the two tables with
`scripts/laplace-python evidence/WRITING_RECONCILIATION_2026-10-02/grammar/map_verbs.py`.
Any Markdown here that carries state is a render; the rows are in `grammar.py` and `mapping.csv`.

---

## 0. What was measured before anything was designed

The friction report counted identity *names*. Before fixing the home list I counted identity
*values*, because a home is a value class, not a name. `home_census.py` calls every read that
publishes an identity field on a real project and groups the names by the value they carry.

```
$ scripts/laplace-python evidence/.../grammar/home_census.py writing-system-friction-report
observations 33   distinct values 16
```

Reproduced on a second project (`synthetics-foundations`): 33 observations, 16 values. Five
results changed the design — the fifth came from reading an owner the census did not reach:

1. **One value under nine names.** The selected edition's root-file bytes come back as
   `structure.authority.source_revision`, `structure.selected_source.revision`,
   `manuscript_source.resolve.revision`, `source.document.revision`, and — when the file read
   happens to be the root — `sources[0].expected_source_digest`, `.full_text_sha256`,
   `.raw_file_sha256`, `.sha256`. Reading a *non-root* chapter splits them: `document.revision`
   still returns the **root's** digest while `sources[0].*` return the chapter's. So
   `document.revision` is the selected-edition home, not the read file's home, and a caller who
   reads chapter-01 and sends `document.revision` as the chapter's digest is wrong in a way no
   refusal explains today. Two homes: `selected-edition` and `source-file`.
2. **`source.source_revision` is a third home.** It is identical across both file reads
   (`147776b8…` for the root and for chapter-01), so it identifies the whole traversal, not any
   file. `help visual_place` already warns about this in prose; the grammar makes it a different
   home kind, `source-traversal`, so the warning is unnecessary.
3. **Three guard names are one home — the audit read this as three.** `concept {node}.revision`,
   `logical_plan.revision`, `logical_plan {node,attention}.revision` and
   `logical_plan/context.revision` are **one value** (`559d2e96…` on the report project,
   `28ea455e…` on Foundations), because `concepts_surface.state` **mints it at `:123` and
   publishes it at `:136`** while `concepts_surface.logical_plan` **mints and publishes it at
   `:752`**, both calling the same `_revision(nodes, relations, rows)` (`concepts_surface.py:20-22`)
   over the same `_network` snapshot. (Round 1 of this packet cited `:130` and `:747` for these two
   mints; both were wrong by a few lines, on the packet's largest single claim. `grep -n
   '_revision(nodes' src/laplace/concepts_surface.py` → `123`, `223`, `752`.) Therefore `base_revision`
   (`concept_change`), `base_revision` (`logical_plan_change`) and `expected_concept_revision`
   (`structure_change bind_results`, compared at `project_structure.py:852-855`) all compare the
   **`concept-network`** home. `verb-altitude-audit.md` §1.2 records these as "the same name, a
   different home and a different value"; the code and the measurement say one home. This is the
   single largest collapse in the census and the reason `bind_results` is expressible at all.
   Proved in `test_grammar.py::test_the_measured_collapse_three_guard_names_one_home`.
4. **One home is not a digest at all, and the census did not find it** — the audit's guard census
   did, and reading the owner settled it. `framing` and `argument` guard `base_revision` against
   `authoring.load(project)["revision"]`, which is a **monotone integer** (`pipeline/authoring.py:93`,
   coerced at `:113`, compared at `:398`, incremented at `:434`), and `:386-392` accepts
   `base_revision`, `expected_revision` and `revision` as three aliases for it. So: one home
   (`authoring-state`), two concepts guarding it, three accepted names, and a published sibling
   `argument_revision` (`:94`, `:432`) that **nothing compares**. My own first mapping put these two
   guards on `concept-network`; reading `project_work.py:147-151` and `pipeline/authoring.py:386-399`
   disproved it. The token grammar grew its second digest form for this one home, and no other.
5. **Two equalities in the census are degenerate and must not be read as collapses.**
   `project_guidance.revision == catalog_revision == 4f53cda1…` is `sha256("[]")` — both projects
   have no configured guides — and `writing_style.guidance_sha256 == e3b0c442…` is `sha256("")`.
   They are two homes (`guide-instructions`, `guide-catalogue`) that happen to be empty.
   `writing_style`'s four values are identical across both projects, which is the real finding
   there: `style-profile` is a **global** home read through a per-project door.

---

## 1. The token

```
rev:<home-kind>:<home-id>:<digest>
```

| part | rule |
|---|---|
| `rev:` | the literal prefix. A value that does not start with it is not a token and is refused by `parse`. |
| `<home-kind>` | one of the 58 kinds in §2. Lower-kebab, **no colon** (enforced by `grammar.py`'s `_KIND`). |
| `<home-id>` | `<project>` for a whole-project home, `<project>::<id>` for a home inside a project, `::<id>` for a home that is not per project. **May contain colons** — real node ids do (`def:task-relative-representation`) — so a token is parsed from both ends (`split(":", 2)` then `rsplit(":", 1)`), never by splitting on every colon. `::` is the only segment separator. **One segment is reserved: an id may not END with `sha256`** (`mint` refuses it), because that segment, sitting immediately before the digest, is the digest's own prefix. |
| `<digest>` | lowercase hex sha256, no prefix. **One form, and there is no second.** `mint` and `parse` accept the owner's `sha256:`-prefixed and upper-case spellings and normalise them, exactly as `revision_identity.py:9-22` already does, so no caller is refused over a spelling; an integer is refused with the name of the home that mints over bytes instead. The prefix is the owner's exact lower-case spelling — `revision_identity.py:6` normalises `(?:sha256:)?([0-9a-fA-F]{64})` and nothing else, so the grammar tolerates neither more nor less than the door it has to agree with. |

**The reserved segment, and the silent corruption it ends.** Round 2's `parse` split the digest off
from the right and nothing else, so the owner's own prefixed spelling —
`project_structure.py:14-17` publishes exactly `sha256:<64 hex>` — was eaten **into the home id**:

```
rev:plan:proj:sha256:<64 hex>   ->  kind plan   home id `proj:sha256`   digest <64 hex>
```

The digest normalised correctly, the id named a home that does not exist, and **nothing refused**.
A refusal built from such a token hands the caller `needed` for the wrong home — the misdirected
resolver this whole layer exists to prevent. The segment immediately before a 64-hex tail is now
read as the digest's prefix, and `mint` refuses to make a token whose home id ends in that word, so
the rule is lossless in both directions and `parse(str(token)) == token` for every id shape —
including ids that carry `sha256:` *inside* them (`proj::blob:sha256:deadbeef`), ids with a path,
ids with a node id full of colons, and the `::<id>` form
(`test_grammar.py::test_a_prefixed_token_round_trips_with_its_home_id_intact`).

**Why there is exactly one digest form, and what the one counter home digests.** One owner numbers
its home with a **monotone integer** instead of publishing a digest: `pipeline/authoring.py:93-94`
keeps `revision` as an int, coerces it at `:113`, compares it at `:398-399` and increments it at
`:434`. That home is **`authoring-state`**, and nothing else — `framing` and `argument` are two
recipe-`J` content homes *guarded through* it (`grammar.py`'s own comment above `_HEX` says the
same, and §2's table gives all three their recipe). The token does not carry the counter. The
`authoring-state` home's one minting rule digests **the bytes that counter counts**: the project's
`authoring.json` — `_STATE_NAME` at `pipeline/authoring.py:24`, the path the owner's own
`_state_path` resolves at `:63-86`, the file `_write` (`:244`) rewrites at `:435`, `:1177` and
`:1256`. So it is a recipe-`B` home like any other file home, and `expected` holds one kind of
value everywhere.

Two things follow, and both are stated rather than hoped. The counter stays the owner's: it is
still what the door compares today and still what the refusal says, so `revision conflict:
expected 0, current 2` — the refusal the synthesis names as one of the three best in the system
(§1.1) — is unchanged and still reproducible; the token is the *cure* field, not the sentence. And
the file is rewritten once without the counter moving (`:1084`, a context write), so this token
discriminates one state the counter does not: it can refuse where the counter accepted, never
accept where the counter refused. A replay will see that one extra refusal class; a shim that
rewrites an old int `base_revision` therefore maps it through the counter, not into the token.
*Conventional default refused*: **a second token form.** Admitting a counter spelling in the
digest slot so one home can wear its counter in the identity looks like uniformity with the owner
and costs two parse rules,
two mint rules, two comparison semantics and a separate parity argument per form — and a lane has
to know which home it holds before it can compare two `expected` values.

**The token adds no new digest for a home an owner already mints — and recipe `J` is the stated
exception.** Scope it exactly, because §9 and every later lane will cite this sentence:

| recipe | what the token's digest is | is it the owner's own value? |
|---|---|---|
| `O` | the string the owner publishes at a named json path, used verbatim | **yes**, byte-identical |
| `B` | sha256 of the same file bytes the owner digests, with the owner's own function (`manuscript_structure.py:46-51` `_digest`/`_digest_bytes`, `manuscript_blocks.py:50`) | **yes**, same bytes, same function |
| `J` | **a sha256 of canonical JSON that no owner publishes.** This layer computes it | **no** |

So a replay can test an `O` or `B` token against the recorded corpus directly — including
`authoring-state`, whose file is in the corpus even though the counter inside it is what the door
compares. A `J` token has nothing to compare against, and the harness lane must not treat it as
parity evidence: the `J` homes are listed with their recipe in the §2 table and the 21 of them are
counted in §7's generated paragraph. **Which `J` homes any door compares today: none** — and that
is a check, not a sentence: `test_grammar.py`'s `test_no_door_compares_a_recipe_j_home` walks
`GUARD_NAMES` against `HOME_KINDS` and fails naming the home, so the next lane that declares a
guard on a `J` home is stopped at install. Every guard name in the census resolves to an `O` or `B`
home. (Round 1 of this packet had three `J` homes declaring a guard — `visual`, the duplicate plan
kind and `block` under the wrong recipe; round 2 found a fourth the sentence had missed, `note`'s
`supersedes`, which is the *id of the note being replaced* and not an identity at all —
`writing_contracts.py:433` types it `_STRING` and `:436` says it "explicitly replaces an obsolete
instruction", and every comparison in the tree is against an id, `pipeline/authoring.py:1143-1146`
and `manuscript_structure.py:644`, never against a revision. It now travels in the request payload
as content, the way `anchor_text` does, and `map_verbs.NOT_A_GUARD` records it as a miscount in the
20-name census.) That is the useful form of the claim: no refusal in the system today depends on a
digest this layer invents.

- *Measurement it answers*: nothing — this is the parity constraint, not a cure. Differential
  replay against the recorded corpus is this campaign's acceptance condition, and a new digest
  scheme would fail it on the first commit.
- *Conventional default refused*: **another revision field.** The obvious move is to define a
  fresh `grammar_revision` and migrate the owners onto it. That is how the system got to 20 names
  over 9 values. The grammar's contribution is that the home is *named* and the mint rule is
  *written down once* — not that the bytes change. One later migration, after parity, may unify
  the two JSON canonicalisations (`project_structure.py:14-17` against
  `concepts_surface.py:20-22`); the grammar does not need it.

**Three recipes.** Two of them digest bytes here (`B`, `J`); one carries the owner's own published
value (`O`). The counts are in §7's generated paragraph, never typed here.

| recipe | rule | examples |
|---|---|---|
| `B` | sha256 of the exact bytes of one named file. Nothing added, nothing sorted. | `source-file`, `artifact`, `producer`, `guide-document`, `block`, `prose`, and `authoring-state`, the one home whose owner keeps a counter instead of a digest |
| `J` | sha256 of `json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))`. `project_structure.py:14-17`'s spelling, chosen because more owners already use it than any other. **No owner publishes these values**, which is why this recipe exists and why a `J` token is not parity evidence. | `plan-section`, `claim-position`, `spine-position`, `task`, `framing` |
| `O` | the owner's own published value, read through the owner at a named json path, used verbatim. | `concept-network`, `plan`, `selected-edition`, `style-state`, `source-traversal` |

`identity(home)` has exactly one implementation per home kind: one `OWNER_READS` entry, or the
file read for recipe `B`. A kind with no wired read raises `NotImplementedError` whose message
carries the home's `closes` — the read or the owner publication that would close it — and never
falls back to recomputing a digest, because a recomputed digest that differed would pass the test
suite and fail replay. §2.1 is the whole partition, so a lane knows before it runs anything.

---

## 2. The home alphabet

One minting rule per home kind. `bytes` is what is digested, so anyone can reproduce the token
from the repository alone. `source` is the live code that produces the value today.

**Two name columns, because they are two different sets.** `asked for as` is what a *door
compares*; `published as` is what a *read returns*. The friction report's 20-name census is of
published fields, and conflating the two is how `sha256` came to look like a guard — `source`
publishes it, no door compares it. `grammar.py` enforces the distinction: a payload may not speak
an **asked-for** name (that identity belongs in `expected`), and may mention a **published** name
freely, because a published name says where the caller got the value, not what it must send.

Row source: `grammar.py`'s `HOME_KINDS`.

<!-- BEGIN HOME TABLE (generated by map_verbs.py; do not edit by hand) -->

| home kind | home id | bytes digested (the one minting rule) | recipe | `identity()` obtains it | minted today at | asked for as | published as | the one read |
|---|---|---|---|---|---|---|---|---|
| `source-file` | repository-relative path of one .tex file | the file's exact bytes | B | **read** | manuscript_structure.py:46-51; manuscript_blocks.py:50 | `expected_source_digest`, `before` (door: before=manuscript_blocks.py:166 (`if path.read_text(encoding="utf-8") == edit["before"]`) and :242 compare the WHOLE file text against `before` during undo and rollback; the SPAN-level `before` is the prose home, compared at review_surface.py:1860) | `sha256`, `raw_file_sha256`, `full_text_sha256`, `expected_source_digest` | source {files:[path]} -> sources[0].sha256 |
| `selected-edition` | project | the selected manuscript root file's exact bytes | O | **read** | manuscript_source.py:263 | `expected_source_revision`, `expected_root_digest` | `revision`, `source_revision`, `document.revision` | source {} -> document.revision |
| `source-traversal` | project | sha256 over the traversal IN SOURCE ORDER of each row's `file` + NUL + its full `text` + NUL --- the owner's own _revision, not a sorted snapshot | O | **read** | pipeline/authoring.py:439-447 (_revision), computed at :722 and published at :796 as source.source_revision; help visual_place warns in prose that it MUST NOT be sent as expected_source_revision (§1.3). NOT manuscript_structure.py:349-353, which digests a sorted [{file,sha256}] snapshot as the SOURCE_ONLY fallback of the fallback: a different value under a name one letter apart, and my own first reading of this home | -- | -- | source {} -> source_revision |
| `plan-file` | project | the canonical projection_plan.json file's exact bytes | O | **read** | project_structure.py:176, :303 (authority.plan_revision) | `expected_plan_revision` | -- | structure {} -> authority.plan_revision |
| `plan-section` | project + section id | canonical JSON of that section's row in the plan projection | J | **read** | NOT MINTED TODAY -- the gap `place` closes (synthesis.md §1.8: reconcile said CURRENT while plan order and \input order disagreed in 4 of 7 positions) | -- | -- | structure {} -> sections[id] |
| `plan` | project | canonical JSON of {authority, sections, gaps} of the plan projection --- the value `structure {} -> revision` returns, NOT the whole projection_plan.json document (those bytes are the `plan-file` home). Round 2 of this packet merged its duplicate kind into this one: one set of bytes had two kinds, `identity()` minted both, and `require` answered a present, unchanged home with `unknown-home` and an empty `needed` | O | **read** | project_structure.py:308 via _digest :14-17 | `expected_revision`, `expected_plan_revision` | -- | structure {} -> revision |
| `concept-network` | project | canonical JSON of {rows, nodes, relations} of the whole conceptric network | O | **read** | concepts_surface.py:20-22 _revision; minted at :123 and published at :136 by state(), minted and published at :752 by logical_plan() --- one value, two reads | `base_revision`, `expected_concept_revision`, `concept_revision` | `revision` | concept {node} -> revision  (identical to logical_plan -> revision; measured) |
| `concept-node` | project + node id | canonical JSON of {node, content, relations, sources, prerequisites} | O | **read** | concepts_surface.py:78-82 _content_revision | `mutation_revision` | `content_revision`, `mutation_revision` | concept {node} -> content_revision |
| `concept-catalogue` | project + query | canonical JSON of the WHOLE sorted row set, page-independent | O | **read** | concepts_surface.py:167 | -- | -- | logical_plan {view:catalog} -> revision  (NOT a change guard; §1.3's trap) |
| `claim-meaning` | project + node id | canonical JSON of {kind, meaning, mathematics, source_refs} of one claim | O | **read** | literature_support.py:64-76 meaning_revision | `claim_revision` | -- | literature_scope {node} -> meaning_revision |
| `result` | project + record id | canonical JSON of the research record with its own `revision` key removed | O | **read** | research_surface.py:571-573 _record_revision | `expected_revision`, `result_revision` | -- | research {view:result} -> revision |
| `result-binding` | project + claim id + result id | canonical JSON of the binding row | J | caller `value=` | research_surface.result_bindings | -- | -- | structure {} -> evidence |
| `run` | project + run id | canonical JSON of research_runs/run-<id>.json merged with its receipt at read | O | caller `value=` | research_surface.py:799-812 | -- | -- | run_status {id} -> state |
| `producer` | project + producer path | the declared producer file's exact bytes | B | **read** | research_surface.py:206-213 | `source_revision` | -- | research {view:full} -> current_dependencies[].sha256 |
| `artifact` | project + scope + path | the artifact file's exact bytes | B | **read** | writing_tools.py:98-99 _artifact_revision | `expected_revision`, `before` | -- | read_artifact {path, scope} -> revision |
| `visual-spec` | project + spec id | canonical JSON of the figure spec | O | caller `value=` | visuals_surface.py:237 vp.digest(spec | `expected_revision` | -- | visuals {} -> specs[id].spec_revision |
| `visual` | project + spec id | canonical JSON of {spec_revision, placed_file, placed_caption} | J | caller `value=` | visuals_surface.py:393 writes; :430 observes placement | -- | -- | visuals {} -> placement |
| `note` | project + note id | canonical JSON of the row the author-history page publishes for this note | J | **read** | pipeline/authoring.py:1150 writes the row {id, created, text, kind, scope, anchor, by, status, base_revision}; it publishes NO identity of its own --- its base_revision is the authoring-state home's counter, not this home's digest --- so this layer digests the published row.  Measured: author_history.history(project, {view: corrections}) returns 20 rows keyed `activity:journal:WR-...` with {id, at, status, summary, targets} and no revision.  NO GUARD: round 1 of this packet declared `supersedes` on this home.  It is a REFERENCE to another note's id, not an identity of any home's state --- writing_contracts.py:433 types it `_STRING` inside the note input and :436 says it "explicitly replaces an obsolete instruction" beside `reply_to`; the only comparisons in the tree are against ids (manuscript_structure.py:644 `row.get("supersedes") == receipt_id`, concepts_surface.py:456, and pipeline/authoring.py:1143-1146 looks the row up by id), never against a revision.  So it travels in the request PAYLOAD, the way `anchor_text` does, and map_verbs.NOT_A_GUARD records it as a miscount in the 20-name census | -- | -- | author_history {view:corrections} -> rows[id] |
| `storage` | project | canonical JSON of measured store sizes | J | **read** | writing_storage.inspect | -- | -- | storage {} -> bytes |
| `task` | project + task id | canonical JSON of the task row | J | **read** | project_work.py:124-140 state | -- | -- | project {} -> tasks[id] |
| `obligation` | project + node id | canonical JSON of the obligation projection | J | **read** | concepts_surface.py logical_plan -> obligations | -- | -- | logical_plan {} -> obligations[id] |
| `relation` | project + source + rel + target | canonical JSON of the typed edge row | J | **read** | concepts_surface.py:_relations (projection) | -- | -- | concept_tree {node} -> relations |
| `source-ref` | project + node id | canonical JSON of the node's source_refs list | J | **read** | concepts_surface.py:_source_refs | -- | -- | concept {node} -> focus.source |
| `reference` | citekey | canonical JSON of {version, modified} plus the provider metadata identity | O | **read** | references_surface.py:651, :478 _digest(_metadata(item)) | -- | -- | reference {key} -> source.revision |
| `reference-text` | citekey + reading id | the fetched full text's exact bytes | B | **read** | references_surface.py:207 | -- | -- | reference_text {key} -> reading_id |
| `reference-candidate` | provider + query | canonical JSON of the provider's returned row | J | caller `value=` | references_surface.literature_discover | -- | -- | literature_discover {q} |
| `material-reference` | project + binding id | canonical registry membership fact with a consumed owner pin | J | caller `value=` | writing_projects.material_references | -- | -- | material_references {id,view:source} |
| `project-metadata` | project | canonical JSON of the project's registry_projects.json row | O | **read** | writing_projects.py:126-129 _metadata | `expected_revision` | -- | project_metadata {} -> revision |
| `guide-catalogue` | project | canonical JSON of [{path, role, sha256}] over ALL configured guides | O | **read** | project_protocol.py:98-104 catalog_revision | `expected_catalog_revision` | -- | project_guidance {} -> catalog_revision |
| `guide-instructions` | project | canonical JSON of [{path, role, sha256}] over the INSTRUCTIONS-role guides only | O | **read** | project_protocol.py:94-97, :103 (revision); :80-85 states why it is separate from catalog_revision -- a handoff update must be observable without invalidating a context that never read it | -- | -- | project_guidance {} -> revision |
| `guide-document` | project + guide path | the guide Markdown file's exact bytes | B | **read** | project_protocol.py:72 | `before` | -- | project_guidance {path} -> sha256 |
| `style-profile` | repository-relative voice profile path (GLOBAL, not per project) | the profile Markdown file's exact bytes | O | **read** | writing_style.py:34 _file_digest, :158 | `expected_profile_revision` | -- | writing_style {view:profile} -> profile_revision |
| `style-state` | project | canonical JSON of {profile, profile_revision, guidance, genre, provenance_revision} | O | **read** | writing_style.py:184-186 | `expected_revision` | -- | writing_style {view:summary} -> revision |
| `style-provenance` | project | canonical JSON of the provenance summary | O | **read** | writing_style.py:_provenance_summary | `expected_provenance_revision` | -- | writing_style {view:provenance} -> provenance.revision |
| `style-calibration` | project | canonical JSON of the calibration projection | J | caller `value=` | writing_style.writing_style_calibration | -- | -- | writing_style_calibration {} |
| `stage` | project + stage | canonical JSON of {stage, recipe, profiles, selected_source} | O | **read** | writing_stages.py:116-117 | `known_revision` | -- | writing_stage {stage} -> revision |
| `proposal` | project + proposal id | owner-sealed instance of authored content and immutable consumed input basis | O | caller `value=` | manuscript_proposals.proposal_version (opaque instance); authored bytes separately proposal_content_sha256 | -- | -- | author_changes {} -> proposals[id] |
| `prose` | project + file + line range | the exact bytes of the addressed block, whole lines | B | **read** | review_surface.py:1860 (`if current != before:`, the comparison --- VERIFIED by `grep -n 'current != before' src/laplace/review_surface.py` -> 1860, against HEAD and in a worktree; the round-1 judgement asked for :1859 and is wrong); manuscript_blocks.py:50 | `before` (door: before=review_surface.py:1860) | -- | source {files:[path]} -> blocks[]  (the exact span text stays EXACT and travels as payload.anchor_text, which is content, not identity: proposal_preflight.py:81, :93-97 must not be given to a model) |
| `block` | project + file + line range | the exact bytes of one parsed block | B | **read** | manuscript_blocks.py:50 | `expected_source_digest` (door: expected_source_digest=manuscript_blocks.py:49-52 (origin) and :175-176, :221-222 (destination); manuscript_structure.py:540, :917) | -- | source {files:[path]} -> blocks[] |
| `section` | project + section id | the section's source file bytes | B | **read** | manuscript_structure.py:50 | -- | -- | source {files:[path]} |
| `heading` | project + file + line | the heading line's exact bytes | B | **read** | manuscript_structure.py:46 | -- | -- | source {files:[path]} |
| `chapter` | project + chapter file | the chapter file's exact bytes | B | **read** | manuscript_structure.py:50 | -- | -- | source {files:[path]} |
| `claim-position` | project + section id + claim id | canonical JSON of {section, order, claim} in the plan | J | caller `value=` | NOT MINTED TODAY -- `place`'s order obligation | -- | -- | structure {} -> sections[].nodes |
| `spine-position` | project + node id | canonical JSON of {node, order} in the spine | J | caller `value=` | concepts_surface.py:566 ledger_revision (nearest existing) | -- | -- | logical_plan {} -> reader_order |
| `build` | project + mode | the compiled PDF's exact bytes | O | caller `value=` | document_style.py:422 pdf_sha256 | -- | -- | build_status {} -> pdf_sha256 |
| `export` | project + mode | the exported PDF's exact bytes | O | caller `value=` | document_style.py:249 | -- | -- | export_pdf -> sha256 |
| `experiment` | project + run id | canonical JSON of {producer digest, declaration, inputs} | O | caller `value=` | research_surface.py:206-213 + the run declaration | -- | -- | run_status {id} |
| `proof` | project + node id + declaration | canonical JSON of {concept-network token, producer token, declaration} | J | caller `value=` | pipeline/formal_verification.py:268, :396 | -- | -- | proof_targets {node} |
| `turn` | turn id | the delivered prompt's exact bytes | O | caller `value=` | authoring_surface.py:1230 context_sha256 | -- | -- | conversation_history {} -> turns[id].context_sha256 |
| `act-ledger` | project | canonical JSON of the activity projection page | J | caller `value=` | author_history.py:758 | -- | -- | author_history {view:activity} |
| `change-history` | project | canonical JSON of the author-change projection | J | caller `value=` | manuscript_fragments.author_changes | -- | -- | author_changes {} |
| `contract` | operation or empty | canonical JSON of the published operation contract | O | caller `value=` | writing_contracts.py:550 operation_contract | -- | -- | help {operation} |
| `document-form` | project | canonical JSON of the document style record | J | **read** | document_style.py:139-142 load() returns the raw document_style.json record (or {} when absent, which is this project's case) and publishes no revision, so this layer digests the record | -- | -- | document {} |
| `pipeline` | project | canonical JSON of the pipeline projection | J | **read** | writing_pipeline.state | -- | -- | pipeline {view:summary} |
| `project` | project | canonical JSON of the project projection | J | **read** | writing_tools.py project read | -- | -- | project {} |
| `repository` | project | canonical JSON of the listed repository tree | J | caller `value=` | writing_sources.py | -- | -- | repository {action:list} |
| `repository-file` | project + path | the file's exact bytes | B | **read** | writing_sources.py | -- | -- | repository {action:read, path} |
| `authoring-state` | project | the exact bytes of the project's `authoring.json` --- THE BYTES THE COUNTER COUNTS.  The owner numbers this home with a monotone integer `revision` rather than a digest, and the token digests the file that integer lives in and counts, so the token grammar keeps one digest form.  The file: `_STATE_NAME` (pipeline/authoring.py:24) under the directory the owner's own `_state_path` (:63-86) resolves; `_write` (:244) is the only writer.  Measured consequence, stated because a replay will see it: :1084 rewrites the file for a context write WITHOUT incrementing `revision`, so this token discriminates one state the counter does not --- strictly more conservative (it can refuse where the counter accepted, never accept where the counter refused), and the counter itself stays in the refusal sentence the owner serves at :398-399.  ONE home, guarded by both the framing concept and the argument concept, under three accepted aliases for the one name | B | **read** | pipeline/authoring.py:93 (blank), :113 (coerced), :386-392 (accepts base_revision, expected_revision and revision as aliases), :398-399 (compares, and SERVES the value: `revision conflict: expected 0, current 2` -- the synthesis names this one of the three best refusals in the system), :434 (incremented). The sibling `argument_revision` (:94, :432) is published and compared by nothing | `base_revision`, `expected_revision`, `revision` | `revision`, `argument_revision` | project {} -> revision  (pipeline/authoring.load -> revision) |
| `framing` | project | canonical JSON of the framing record {purpose, audience, question} | J | **read** | pipeline/authoring.py:_public (:288-289); its identity is authoring-state, not its own digest -- the content home and the guard home differ here exactly as concept-node differs from concept-network | -- | -- | project {} -> framing |
| `argument` | project | canonical JSON of the sustained-argument record | J | **read** | pipeline/authoring.py:288-289; guarded through authoring-state | -- | -- | project {} -> argument |

<!-- END HOME TABLE -->

### 2.1 Which homes a lane can obtain a token for

This is the question a lane asks first, and round 1 of this packet could not answer it without
running the module: `identity(home)` raised `NotImplementedError` for **34 of the 59 kinds** while
the spec described a mint rule for every one — a description beside a check, the exact default this
packet refuses. Two things were done about it.

**The reads the table already named are now wired.** `OWNER_READS` grew from 13 entries to 30, each
one the owner's own call with its own spelling, its json path, and — for a home inside a published
container — the selector that indexes it by its own id. Measured by
`obtain_census.py` on `synthetics-foundations` **in a real git worktree** (a project whose registry
row and whole corpus are tracked at `HEAD`, so every worktree has it):

```
$ cd <worktree> && scripts/laplace-python .../grammar/obtain_census.py synthetics-foundations <worktree>
OBTAINED FROM THE HOME ALONE: 38 of 58
NEEDS A CALLER VALUE: 20  (18 with no read wired, 2 wired but the home does not exist in this project)
DECLARED MINT_STATUS vs OBSERVED: 0 mismatches
```

38, not 40, because `relation` and `reference` are wired reads whose home *does not exist in that
project* (0 relations; no attached reference library) — a `ValueError` naming the absence, not a
missing rule. The declaration is `MINT_STATUS` in `grammar.py`: **40 kinds `read`, 18
`caller-value`**, and `test_grammar.py::test_the_declared_obtain_partition_is_what_really_happens`
compares the declaration against the behaviour on the real project, so the two cannot drift.

**The 18 that remain are listed, each with what would close it.** None of them is unknowable; each
is one owner publication or one call-shape change away, and the row says which.

<!-- BEGIN OBTAIN TABLE (generated by map_verbs.py; do not edit by hand) -->

| home kind | recipe | `identity(home)` | what would close it |
|---|---|---|---|
| `result-binding` | J | **caller must pass `value=`** | research_surface.result_bindings(manuscript, result_ids, ...) takes a manuscript PATH and a list of result ids, not a project, so it does not fit the one project/root call shape; either give it a project-shaped read or have state_payload publish the binding rows keyed by (claim, result) with their own digest |
| `run` | O | **caller must pass `value=`** | research_surface.state_payload publishes producer_runs rows, but a live row carries pid, deadline_at and finished_at, so two reads of a RUNNING home would mint two tokens; research_surface.py:799-812 already settles a run with its receipt -- publish that settled value and this home becomes readable |
| `visual-spec` | O | **caller must pass `value=`** | same owner as visual: visuals_surface exposes only handle(...). visuals_surface.py:237 digests the spec already; export the specs projection as a module read and wire it |
| `visual` | J | **caller must pass `value=`** | visuals_surface exposes only handle(path, query, method, body, repo_root) -- an HTTP surface with no module-level read, while visuals_surface.py:237 already digests a spec. Export the specs/placement projection as a module read and wire it. NOTE: the guard expected_source_revision was declared on THIS home in round 1 of this packet and is removed, because both doors that compare that name (visuals_surface.py:349-350 and project_structure.py:777) compare the SELECTED EDITION, so selected-edition is its only home |
| `reference-candidate` | J | **caller must pass `value=`** | the value is a provider's returned row, so obtaining it would make a NETWORK call and a read must not. Caller-value by design: the candidate is minted from the row the caller already received |
| `material-reference` | J | **caller must pass `value=`** | Read the exact binding and its owner identity; membership never grants owner write permission. |
| `style-calibration` | J | **caller must pass `value=`** | writing_style.calibration(project, payload, repo_root) requires the calibration request as a payload, so there is no payload-free read of this home; writing_style would have to publish the current calibration in state() |
| `proposal` | O | **caller must pass `value=`** | Read the exact owner proposal_version/identities from proposal preview, pending proposals or exact turn detail. Apply and decision require that instance; callers must not derive it from authored JSON or renew it with a later read. proposal_content_sha256 identifies authored bytes only. |
| `claim-position` | J | **caller must pass `value=`** | no owner publishes a claim's position. project_structure.state's sections[].nodes carries the order implicitly; the lane that implements place must publish {section, order, claim} -- this is finding 1.8, reconcile saying CURRENT while plan order and input order disagreed in 4 of 7 positions |
| `spine-position` | J | **caller must pass `value=`** | concepts_surface.logical_plan publishes reader_order as a STATUS dict {status, reason, revision, source_outline, omitted_sections}, not a position per node; the place lane must publish the node's own order |
| `build` | O | **caller must pass `value=`** | document_style.status(project, root) publishes {status, style} only; the pdf_sha256 at document_style.py:422 lives in the build receipt, not in the status projection |
| `export` | O | **caller must pass `value=`** | obtaining it would RUN document_style.export_pdf at :249, i.e. do work, and a read must not. Caller-value by design, minted from the export receipt |
| `experiment` | O | **caller must pass `value=`** | research_surface publishes experiments with no digest (0 rows on the measured project); the value is a run declaration plus its producer digest research_surface.py:206-213, which nothing assembles into a published home |
| `proof` | J | **caller must pass `value=`** | pipeline/formal_verification.py:268, :396 digests at verification time and no read republishes it; the proof lane must publish it beside the check receipt |
| `turn` | O | **caller must pass `value=`** | authoring_surface.session_turn_detail(root, project, ident, view) needs a turn id AND a view, so it is not a project-shaped read; the context_sha256 at :1230 is published inside the delivery record of one turn |
| `act-ledger` | J | **caller must pass `value=`** | author_history.history(project, {view: activity}, root) publishes the page, but the page carries as_of, a wall clock measured in this packet, so two reads of an UNCHANGED ledger would mint two tokens. The owner must publish a page digest that excludes as_of before this home can be read |
| `change-history` | J | **caller must pass `value=`** | manuscript_fragments.author_changes publishes the projection and, like act-ledger, its rows carry live turn state; the same as_of exclusion is the fix |
| `contract` | O | **caller must pass `value=`** | writing_contracts.operation_contract is keyed by an OPERATION, not a project, so it does not fit the project/root call shape; the generated-contract lane owns this home and publishes its digest with the contract |
| `repository` | J | **caller must pass `value=`** | writing_sources lists the tree on request with a path and a limit, so the value is a VIEW of a listing rather than a home with one settled value; a listing digest over the tracked paths would close it |

<!-- END OBTAIN TABLE -->

A lane that must act on one of those 18 mints its token with `identity(home, value=…)` from the
value it already holds, and the `J` recipe says what to pass.

Three home kinds (`plan-file`, `selected-edition`, `source-traversal`) are guarded by today's
doors but are never the target of an act: a caller must present them and can never change them
through a verb. That asymmetry is now visible instead of implicit.

Three further corrections to the audit's guard census fell out of writing the table, each from
reading the owner the row names:

- **One counted guard is not an identity.** `conversation_history`'s `before` is a pagination
  cursor: `writing_contracts.py:386` declares its input as `{before: string, limit: int}` and
  `pipeline/authoring.history` uses it to page. It is recorded in `map_verbs.py`'s `NOT_A_GUARD`
  with its reason and given no home, because giving it one would invent a home.
- **One guard name accepts two homes, both legal.** `section_change`'s `expected_plan_revision`
  is checked by `_check_plan_guard` (`manuscript_structure.py:362-369`), which builds an
  `accepted` set of **both** `state["revision"]` (the `plan` home) and
  `authority.plan_revision` (the `plan-file` home) and passes on either. The table renders this
  as `plan|plan-file` rather than picking one, because picking one would make a correct
  caller look wrong.
- **Two accepted aliases are declared nowhere.** `pipeline/authoring.py:386-392` accepts
  `base_revision`, `expected_revision` **and** `revision` for the `authoring-state` home, while
  the published contract declares only `base_revision`. The audit's census could not see the other
  two because it read the schemas. They are in `GUARD_HOME` and carry a comment saying so.

`guide-instructions` and `guide-catalogue` are two homes on purpose
(`project_protocol.py:80-85` states why: a handoff update must be observable without invalidating
a context that never read it). That is the one place in the system where two identity names over
one read were already deliberate and documented, and the grammar keeps both.

---

## 3. The verb alphabet

Nine verbs, closed. A concept may add payload keys; it may **not** add a verb.
`grammar.py`'s `Request.__post_init__` refuses a verb outside the alphabet and refuses a payload
key that restates a request field.

**The verb test.** A verb is individuated by its *gate*: what must be proven before the act, and
which homes the receipt must account for afterwards. Two acts that differ only in their payload
are the same verb at different concepts. This is the author's rule — "the verbs act as the gate
to ensure structure is always readable … completely uniform grammar, specialised to the concept"
— turned into a decision procedure.

| verb | gate: what must be proven | owes: what the receipt accounts for | audited verbs |
|---|---|---|---|
| `read` | nothing | the current token of every home it read | 52 |
| `create` | the container's token | a home that did not exist (`before: null`) plus the container | 22 |
| `change` | the target's token | the same home id, a new token | 34 |
| `move` | **both** containers' tokens | two container tokens; the moved home's own token **unchanged** | 8 |
| `delete` | the target's token | `after: null` for the target, plus the container | 11 |
| `bind` | **both** endpoints' tokens | a relation home | 8 |
| `place` | container + placed home + the container's **order** | the container | 6 |
| `run` | the inputs' tokens | `outcome: banked` and a run token to poll | 10 |
| `record` | a **state**, not only an identity | the recorded home | 1 |

### What was added to the audit's eight acts, and why

The audit named eight acts: read content, change content, create a unit, delete a unit, move a
unit, place a claim, bind evidence, comment (`acts_by_altitude.csv`). Three changes:

**`run` added.** Measurement: `help run_status` is 608 characters with `effects: []` and no
outputs, and the terminal-state vocabulary (`RUNNING` `research_surface.py:1501`, `COMPLETE` and
`REFUSED`/`UNKNOWN` `:1095`, `FAILED` `:818`/`:830`, `CANCEL_REQUESTED` `:1623`) appears nowhere
in the contract, so a polling loop written from the contract cannot know when to stop
(synthesis §1.10). The audit filed `experiment_run`, `visual_render`, `proof_check`, `build` and
`export_pdf` under change/bind/create, which hides the one property they share and nothing else
has: **their receipt is not final at return.** `run` is the only verb whose `outcome` is `banked`
with a `run` token in `next`. Giving it a verb is what makes the terminal vocabulary part of the
verb's declared outcome set instead of prose nobody published.
*Conventional default refused*: a `status` field on `change`. That is what
`review_surface.py:1876` does — `{"ok": true, "pending": true, "applied": null}` — and four
`pending-rewrite` rows are still open because a field name is not a status (synthesis §1.4).

**`record` added.** Measurement: `research_record`'s gate is not an identity match. It requires a
*third* home to be in a terminal state — `run.state != "COMPLETE"` refuses at
`research_surface.py:1226-1229`, and renewal additionally requires the exact prior record
revision at `:1214-1216`. No other act has a state precondition, and the grammar needs the
distinction because a refusal whose `kind` is `state-not-reached` cannot be cured by sending a
fresher token; its resolver is a different read. Folding it into `create`/`change` would make
`needed` a lie in exactly one case.
*Conventional default refused*: one `write` verb with a discriminator. That is `writing_tools`
today: 73 names, 152 verbs, the discriminator keyword changing with depth (`operation` at the
top, `kind` one level down, synthesis §1.7).

**`comment` removed.** Measurement: the audit's `comment` row is 2 verbs over 2 operations
(`note`, `note_status`) at 2 altitudes, and it is the smallest act in the matrix. Treating it as
its own verb is what left the system with no way to retire a row: `note_status` is a
status-setter, not a `delete`, so four `pending-rewrite` rows are open and *no operation in the
tool's read or write set can retire them* (synthesis §1.4, §6). Modelled as `create note@claim`,
`change note@claim` and `delete note@claim`, the retiring door exists because every concept gets
the same nine verbs.

**Which verb × concept `note_status` is.** It is a status-setter over three values —
`writing_contracts.py:439` declares `{"enum": ["open", "resolved", "dismissed"]}` and
`pipeline/authoring.py:1191-1192` enforces exactly those three — so it is **`change note@claim`**
as an operation, and the mapping splits it by that payload enum exactly as the audit's own `view=`
and `operation=` discriminators are split: `status=resolved` and `status=dismissed` are
**`delete note@claim`** (the retirement this argument demands: `pipeline/authoring.py:1255-1256`
writes the row's new status and the note stops being an open instruction), and `status=open` is
**`change note@claim`** — `change note@claim` reopens a retired note, the inverse of the
retirement and the one act of the operation that is not one. Round 1 mapped the whole operation to
`delete`, which kept half the defect: the grammar could retire a note and had no request that
reopened one, in the very row that implements this argument. The split lives in
`map_verbs.STATUS_SPLIT` with the measurement for each value, so the dispatch lane and the
contract lane generate a door for all three statuses, and `note@claim` carries three declared
pairs (`create`, `change`, `delete`), not two. No verb was created by specialising: `change` and
`delete` are two of the nine.
A note also could not record its writer — the contract declares `additionalProperties: false`
with no `by`, and `writing_tools.py:458` hard-codes the actor, so all 140 notes of the report from
six writers read back under one name (synthesis §1.10). `by` is a fixed request field here, so the
writer is on every request and in every banked row. It is **not** yet a field the owners take, and
the grammar says exactly where it is taken rather than letting four lanes discover that one refusal
at a time.

#### Which doors take `by` — declared, because the owners disagree

Measured on this tree over the 73 audited operations (`by_census.py`, which
`test_grammar.py::test_the_grammar_declares_which_doors_take_by` re-runs; the table is
`grammar.BY_AT_DOORS` and `grammar.by_at(operation)`):

| status | ops | what happens at the door |
|---|---|---|
| **overwritten** | 4 | `writing_tools.py:309` replaces the caller's value with the constant `"eigen:session"` before the owner is called: `concept_change`, `logical_plan_change`, `writing_style_change`, `writing_style_profile_change`. Their contract declares `by` (`writing_contracts.py:604` adds it to every `logical_plan_change` variant) and the owner records it, so the caller is neither refused nor attributed — **this line is the 140-notes defect, in the code that causes it.** |
| **refused** | 18 | the door validates unknown keys and `by` is not in its key set, so the call fails outright: `structure_change payload contains unknown keys: by` (`project_structure.py:746` → `:710`), `repository list has irrelevant or unknown fields: by` (`writing_sources.py:203`), `source` (`writing_tools.py:194`), `help` (`:211`), the ten literature/reference/`proposal_supersede` operations checked against their contract at `:215`, `writing_stage` (`writing_stages.py:58`), `writing_style` (`writing_style.py:225`), `writing_style_calibration` (`:288`), and `apply_revision` **in its `proposal` wrapper form only** (`authoring_surface.py:2166`). |
| **dropped** | 51 | no key check and nothing reads it: the writer is accepted and lost in silence. `project_metadata_change` lists `by` in its key set (`writing_projects.py:150`) without reading it; `style` keeps only its nine named keys (`project_work.py:163`). |
| **declared** | **0** | a contract that declares `by`, an owner that reads it, and a door that leaves it alone. No operation is in this class today. |

So a lane passes `by` to an owner only where the status is not `refused`, never cites an
`overwritten` door as evidence of attribution, and always banks the writer in its own row. Making
`by` real is the generated-contract lane's work: one declared `by` per operation, and
`writing_tools.py:309` deleted.
*Conventional default refused*: **a verb named after its object.** `comment` is the object
wearing a verb's clothes. Every such verb forces a second vocabulary; the measured end state is
131 verbs through 73 names.

### Why `place` and `bind` were not collapsed into `create`

They nearly were. A relation is a home, so `bind` looks like `create relation@relation`, and a
position is a home, so `place` looks like `create claim-position@section`. The gate test keeps
them apart and one measurement decides it:

- `bind`'s gate names **two** endpoint homes (`bind_results` requires `plan` **and**
  `concept-network`; `literature_bind` requires `claim-meaning` **and** the reference). A
  two-home gate is a different obligation from a one-home gate, and the measured cost of pretending
  otherwise is the 8 refusals one writer paid learning that `bind_results` wants both and names
  only the first.
- `place`'s gate includes the container's **order**, and *nothing owns order today*:
  `structure_change reconcile` returned `CURRENT` and `structure` reported zero gaps in the same
  second while the reader plan's order and the selected root's `\input` order disagreed in four of
  seven positions (synthesis §1.8). The root was repaired by hand. Making order a `place`
  obligation is what makes that defect fixable by a lane rather than by a writer.

Collapsing them would have cost those two things and saved two rows in a table. The nine verbs
stand.

---

## 4. The concept alphabet

A concept is `<object>@<altitude>`: **the home kind being acted on, at the grain it is acted on.**

```
plan-section@section      concept-node@claim      prose@paragraph      result@run
```

- **objects**: the 58 home kinds of §2. 53 of them are reached as the target of some act.
- **altitudes**: `project`, `book`, `chapter`, `section`, `paragraph`, `plan`, `claim`,
  `relation`, `evidence`, `run` — the audit's lexicon, now declared. Nine are reached by the 152
  audited verbs (155 mapping rows, counting the three status rows §3 explains); `book` is declared and **unreached**, which is itself the measurement: no verb
  acts on the manuscript as a whole, only on the plan that projects it, so the one place a reader
  experiences the book has no gate.
- 65 `object@altitude` pairs are reached, in **104 declared `(verb, concept)` pairs**.
  `grammar.py` validates **both** halves — the altitude against `ALTITUDES`, the object against
  `HOME_KINDS` — and then the pair against `VERB_CONCEPTS`, a frozenset spliced into `grammar.py`
  from `mapping.csv` by `map_verbs.py` (one row source, no second list to agree with). So the
  option set is closed and enumerable: 104 pairs, not nine verbs times anything. In round 1 of
  this packet only the altitude was checked and `Request(verb="read",
  concept="totally-made-up-thing@claim", …)` was accepted — an open set, which is the door through
  which 73 operations grew 152 bare-string sub-verbs. A lane that needs a pair the audit never
  reached calls `declare_pair(verb, concept, because="<the measurement>")`; an empty reason is
  refused, so an addition is a visible act with a record, not a new string.

*Measurement this answers*: "Altitude is the audit's lexicon, not the system's. No operation
declares an altitude, so the altitude column is assigned from field and enum names through a fixed
table" (synthesis §6). Declaring it removes the need for the audit.

*Conventional default refused*: **altitude as an optional parameter on one verb.** That reads as
the cure and is not, because the *guard* changes with altitude: `expected_root_digest` is
**optional** at chapter altitude (`writing_tools.py:339-341`) and the plan guard is **mandatory**
one step below (`manuscript_structure.py:368-369`). An optional parameter cannot carry a changing
obligation. The concept carries it, because the concept selects the payload schema and the schema
states the homes.

### The specialisation rule

> Specialisation lives **only** in the concept's payload schema.

The request's six keys are the same for every verb and every concept. A concept contributes:
its payload schema, which homes the verb's gate names for it, and nothing else. Enforced three ways
in `grammar.py`:

1. `Request` refuses a verb outside `VERBS`.
2. `Request` refuses a payload key that restates a request field.
3. `Request` refuses a payload key that is **any** of the 22 old guard names, naming the home(s) it
   belongs to. An identity is presented in `expected` as a token or not at all; only a `Shim` may
   speak an old name.

*Measurement this answers*: 73 operations cost 3,231 characters as a specification while one
`concept_change` contract costs 49,285 (synthesis §1.3), and 75.3 per cent of
`help structure_change` is a byte-identical duplicate of itself (`writing_tools.py:271` against
`writing_contracts.py:550`). Under this rule the contract for a verb is written once and the
per-concept part is only the payload schema, which is the part a caller needs *after* it has
chosen.

*Conventional default refused*: **a description beside a check.** The report's sharpest finding
about documentation is the opposite of the expected one: three of the four guard facts the arrival
replay counted as undeclared *are* stated — in the third clause of a precondition inside 41,476
characters (`writing_contracts.py:314`, `:620`, `:170`). "The repair is not more prose; it is
less." So the home is not a sentence next to the field; it is the field's **type**. The one place
the live code already does this is `visuals_surface.py:355`, which returns
`"guard_fields": {"expected_source_revision": "source.document.revision"}` inside a refusal — the
right idea, in the wrong place (one refusal of one door) and with the wrong value: the census shows
`document.revision` is the selected-edition home, so a caller using it as a chapter's digest is
misdirected by the best-behaved refusal in the system.

---

## 5. The four shapes

### Request

```json
{"verb": "bind", "concept": "result@claim", "target": "p::node:1",
 "expected": ["rev:plan:p:da64ee…", "rev:concept-network:p:559d2e…"],
 "payload": {"bindings": [{"id": "r1"}]}, "by": "eigen"}
```

`expected` is a **list**, unordered, and `require` checks every entry.

**The one key an owner spells the same as a request field, and which side wins.**
`logical_plan_change operation=connect` declares a top-level `target` — the far endpoint of the
edge — at `writing_contracts.py:607`, and a payload may not restate a request field, so that route
could not express its own payload at all. It is a live shape: 2 rows of the recorded corpus carry a
top-level `target`, both `logical_plan_change`, and one of them applied. **The request field keeps
the name.** The six keys are the same six for all 104 declared pairs and are spoken by the door, the
receipt, the refusal and every shim; renaming one of them to clear one owner's key would make the
uniform half of the grammar negotiable per concept. The owner's key travels under a declared
carrier and the shim restores the owner's spelling at the owner's door:

| the owner's key | the carrier in the grammar's payload | restored by |
|---|---|---|
| `target` (`writing_contracts.py:607`) | `edge_target` | `grammar.to_owner_payload(payload)` at the owner's door; `grammar.to_payload(owner_payload)` makes the request's payload |

One declaration (`grammar.PAYLOAD_CARRIERS`), checked at import, so four build lanes do not invent
four spellings; the refusal a caller gets names the carrier and the two functions. `concept_change`'s
edges never collide — they carry their target inside the op object (`writing_contracts.py:579`).

### Receipt

```json
{"ok": true, "outcome": "applied",
 "affected": [{"home": "source-file:p::chapters/chapter-01.tex",
               "before": "rev:source-file:p::chapters/chapter-01.tex:87bab2…",
               "after":  "rev:source-file:p::chapters/chapter-01.tex:c974c3…"}],
 "receipt_id": "APP-4f1c…", 
 "banked_row": {"verb": "change", "concept": "prose@paragraph", "altitude": "paragraph",
                "target": "p::chapters/chapter-01.tex", "by": "eigen"},
 "next": [{"verb": "read", "concept": "plan@plan", "target": "p"}]}
```

- `outcome` is `applied` | `banked` | `refused` — a **status**, not a field name.
  *Measurement*: `review_surface.py:1876` returns `{"ok": true, "pending": true,
  "applied": null}`; "the two outcomes differ in a field name, not in a status code", and a caller
  that logs `ok` and the record id records a write that did not happen (synthesis §1.4).
- `affected` accounts for every home: `before: null` means the home did not exist, `after: null`
  means it is gone. A caller never has to re-read to learn what moved.
  *Measurement*: `visual_place` returned `ok` with `reused: true` while the printed caption kept a
  retracted number; the divergence is detected by a *later* read, never by the door that
  succeeded (`visuals_surface.py:393`, synthesis §1.4).
- `banked_row` carries `verb`, `concept` and `altitude`.
  *Measurement*: the banked row carries the operation name only, so for
  `structure_change {operation: plan, op: {kind: set-nodes}}` the row says `structure_change` and
  recovering which of its 26 verbs ran means re-parsing the payload
  (`writing_tools.py:959-971`, `:1000-1006`, synthesis §1.7).
  *Conventional default refused*: **recording in the owner.** The owners do record the verb — into
  three stores under two field names (`manuscript_structure.py:150-151`,
  `corpus_ingest.py:951`/`:1078`, `pipeline/authoring.py:1109`/`:1150`). "The defect is therefore
  not a missing trail. It is that there is no one place, and no one grain."
- `next` is the routing the system already does well where it exists (`research_record`'s exact
  next write; `read_artifact`/`store_artifact`'s filled-in handles at
  `writing_tools.py:500-501`, `:560-566`), expressed as grammar requests so it is uniform.

### Refusal — `needed` **is** the resolver

```json
{"ok": false, "refused": {
  "kind": "identity-stale",
  "homes": [{"home": "concept-network:p", "current_token": "rev:concept-network:p:559d2e…",
             "sent_token": "rev:concept-network:p:377e72…",
             "read": "concept {node} -> revision", "bytes": "canonical JSON of {rows, nodes, relations}…"}],
  "needed": {"expected": ["rev:plan:p:da64ee…", "rev:concept-network:p:559d2e…"]},
  "said": "concept-network:p moved"}}
```

A caller retries with `{**request, **refused.needed}` and guesses nothing. `kind` is one of
`identity-stale`, `unknown-home`, `state-not-reached`, `shape` — the system's first error taxonomy
as a typed field (today "the only typed field is `error_type`, which is `ValueError` for almost
everything", synthesis §6).

- *Measurement*: 29 of 74 refusals; and `bind_results` names only the guard it checked first, which
  cost one writer 8 refusals and then 8 more. `require` compares **all** expected tokens and the
  refusal lists **every** stale and unknown home. Proved in
  `test_grammar.py::test_require_names_every_stale_home_not_only_the_first`.
- *Measurement*: `retry_instruction` is set inside `failure_response`
  (`writing_tools.py:1049`, `:1056`) which has exactly two callers (`:1240`,
  `writing_provider.py:555`), so a direct or HTTP caller gets neither the instruction nor the
  recovery revision (synthesis §1.10). `needed` is built by `require` — the **comparison** — which
  is on every caller path by construction. The resolver cannot be reachable from one path only,
  because it is produced where the refusal is decided, not where it is formatted.
- *Measurement*: six refusals hold the value in a local variable at the moment they decline to
  return it (`project_protocol.py:164-165`, `writing_projects.py:163-164`,
  `manuscript_structure.py:366-368`, `project_structure.py:765-766`, `writing_style.py:469-470`,
  `:432-433`). `require` receives the observed tokens as its second argument, so the value is in
  hand before the refusal exists and cannot be dropped.
- *Conventional default refused*: **"read X and retry."** Nine of 43 probed refusals do exactly
  that (`verb-altitude-audit.md` §1.5) and it costs a turn plus the read. A refusal that can name
  the read can serve the value.

### Affected / Home

`Home(kind, id)` and `Affected(home, before, after)` are the only two ways a home is ever
mentioned. There is no free-text home.

---

## 6. The shim rule

An old operation name is served by a `Shim`, and a shim obeys four rules, all load-bearing:

1. **A shim rewrites; it never implements.** `Shim.to_request` produces a grammar `Request` and the
   same function runs. One code path, so replay cannot diverge between the old and the new name.
2. **A shim carries an expiry** — a date and the parity run that retires it. *A shim with no expiry
   is the mapping file this grammar refuses.* This is a **gate**, not a sentence:
   `Shim.__post_init__` refuses an empty expiry, an expiry without a `YYYY-MM-DD` date, an expiry
   that does not name parity, a `verb` outside the nine, a `concept` whose object is not a home
   kind, and a `guard_to_home` value that is not a `HOME_KINDS` key (or a legal `a|b` pair). In
   round 1 of this packet `Shim(verb="frobnicate", concept="nope@nope", expiry="")` was
   constructible while `Home`, `Request`, `Receipt` and `Refusal` all validated themselves — the
   one object a lane builds by hand from `mapping.csv` was the one with no gate. One test per
   refusal (`test_a_shim_cannot_be_built_without_an_expiry_a_verb_and_real_homes`).
3. **A shim translates the refusal back.** `needed` comes out of `require` keyed by grammar fields;
   `Shim.from_refusal` renames those keys to the old guard names that shim accepts. So an old
   caller still gets a resolver rather than an instruction — the guarantee is not lost during the
   migration, which is the usual way a migration is abandoned half-done.
4. **A shim is retired on replay parity**: when differential replay over the recorded corpus is
   byte-identical through the grammar request alone, the shim is deleted. Not deprecated. Deleted.

`grammar.py` registers the two the report's sharpest instances need
(`structure_change bind_results`, `logical_plan_change add_object`); each lane registers the shims
for the operations it owns, from `mapping.csv`.

*Conventional default refused*: **a compatibility layer with its own logic.** The measured end
state of that is `review_surface.py`'s roster drift — the door accepts 13 verbs (`:1253-1257`)
while the executor docstring the route itself names as "the ONE roster" lists 8 (`:1394-1397`),
stale by five including `rewrite`, the verb through which every word of the friction report was
written.

---

## 7. The mapping table

Every verb the audit published, mapped to `verb × concept`, with each old guard name resolved to
its home kind. A `?` after a home kind means that guard is **optional** on that door today — the
`chapter`/`section` asymmetry is visible in the table rather than discovered by refusal.

Row source: `map_verbs.py` over
`evidence/WRITING_FRICTION_2026-10-01/wave1/verb-altitude-audit/verb_matrix.csv`.
<!-- BEGIN COVERAGE COUNTS (generated by map_verbs.py; do not edit by hand) -->

Coverage, computed by this script from the rows and spliced here, so no count in this document is hand-typed: **131 leaf verbs + 21 sub-verbs + 3 status rows + 16 post-audit extensions = 171**, 9 verbs used, 68 concepts in 114 declared `(verb, concept)` pairs, 19 of the 60 home kinds reached by today's guards. No verb was invented: every row's grammar verb is one of the nine, and the script exits non-zero if one audited verb is unassigned. The 3 status rows are one audited leaf verb (`note_status`) split by the payload enum its door enforces, declared in `map_verbs.STATUS_SPLIT` with the measurement for each.

Of the 60 home kinds, `identity(home)` obtains **41** from the home alone (11 recipe `B` whose home id is the path, read straight from disk, + 30 wired owner reads, one of them the recipe-`B` file `authoring-state` whose path its owner resolves) and **19** need the caller to pass `value=`; §2.1 lists those 19 with what would close each. Recipes: 12 `B`, 23 `J`, 25 `O`; there is no fourth recipe and no second token form.

<!-- END COVERAGE COUNTS -->

<!-- BEGIN MAPPING TABLE (generated by map_verbs.py; do not edit by hand) -->

| # | old name (operation / verb) | grammar verb | concept | old guard name(s) | home kind(s) | owner |
|---|---|---|---|---|---|---|
| 1 | `apply_revision` / `apply_revision` | `change` | `prose@paragraph` | `-` | `-` | `authoring_surface.py` |
| 2 | `apply_revision` / `apply_revision` | `change` | `prose@paragraph` | `-` | `-` | `authoring_surface.py` |
| 3 | `argument` / `argument` | `change` | `argument@plan` | `base_revision` | `authoring-state` | `writing_tools.py` |
| 4 | `author_changes` / `author_changes` | `read` | `change-history@project` | `-` | `-` | `manuscript_fragments.py` |
| 5 | `author_history` / `view=activity` | `read` | `act-ledger@project` | `-` | `-` | `author_history.py` |
| 6 | `author_history` / `view=corrections` | `read` | `note@project` | `-` | `-` | `author_history.py` |
| 7 | `author_history` / `view=record` | `read` | `act-ledger@project` | `-` | `-` | `author_history.py` |
| 8 | `author_history` / `view=telemetry` | `read` | `act-ledger@project` | `-` | `-` | `author_history.py` |
| 9 | `block_change` / `operation=delete` | `delete` | `block@paragraph` | `-` | `-` | `manuscript_blocks.py` |
| 10 | `block_change` / `operation=insert` | `create` | `block@paragraph` | `-` | `-` | `manuscript_blocks.py` |
| 11 | `block_change` / `operation=insert-at-caret` | `create` | `block@paragraph` | `-` | `-` | `manuscript_blocks.py` |
| 12 | `block_change` / `operation=move` | `move` | `block@paragraph` | `-` | `-` | `manuscript_blocks.py` |
| 13 | `block_change` / `operation=undo` | `change` | `block@paragraph` | `-` | `-` | `manuscript_blocks.py` |
| 14 | `build` / `build` | `run` | `build@project` | `-` | `-` | `manuscript_source.py` |
| 15 | `build_status` / `build_status` | `read` | `build@project` | `-` | `-` | `manuscript_source.py` |
| 16 | `chapter` / `chapter` | `create` | `chapter@chapter` | `expected_root_digest` | `selected-edition?` | `manuscript_structure.py` |
| 17 | `concept` / `concept` | `read` | `concept-node@claim` | `-` | `-` | `concepts_surface.py` |
| 18 | `concept_change` / `operation=add_edge` | `bind` | `relation@relation` | `base_revision/mutation_revision` | `concept-network/concept-node?` | `concepts_surface.py` |
| 19 | `concept_change` / `operation=remove_edge` | `delete` | `relation@relation` | `base_revision/mutation_revision` | `concept-network/concept-node?` | `concepts_surface.py` |
| 20 | `concept_change` / `operation=retype_edge` | `change` | `relation@relation` | `base_revision/mutation_revision` | `concept-network/concept-node?` | `concepts_surface.py` |
| 21 | `concept_change` / `operation=edit_node` | `change` | `concept-node@claim` | `base_revision/mutation_revision` | `concept-network?/concept-node?` | `concepts_surface.py` |
| 22 | `concept_change` / `operation=add_node` | `create` | `concept-node@claim` | `base_revision/mutation_revision/supersedes` | `concept-network/concept-node?/NONE (the id of the note being replaced: a payload reference, not an identity (writing_contracts.py:433, :436))` | `concepts_surface.py` |
| 23 | `concept_change` / `operation=set_source` | `bind` | `source-ref@claim` | `base_revision/mutation_revision` | `concept-network?/concept-node?` | `concepts_surface.py` |
| 24 | `concept_change` / `operation=set_projection` | `change` | `concept-node@claim` | `base_revision/mutation_revision` | `concept-network?/concept-node?` | `concepts_surface.py` |
| 25 | `concept_change` / `operation=set_mathematics` | `change` | `concept-node@claim` | `base_revision/mutation_revision` | `concept-network?/concept-node?` | `concepts_surface.py` |
| 26 | `concept_change` / `operation=set_kind` | `change` | `concept-node@claim` | `base_revision/mutation_revision` | `concept-network?/concept-node?` | `concepts_surface.py` |
| 27 | `concept_change` / `operation=set_status` | `change` | `concept-node@claim` | `base_revision/mutation_revision` | `concept-network?/concept-node?` | `concepts_surface.py` |
| 28 | `concept_change` / `operation=set_spine` | `place` | `spine-position@plan` | `base_revision/mutation_revision` | `concept-network/concept-node?` | `concepts_surface.py` |
| 29 | `concept_change` / `operation=unset_spine` | `delete` | `spine-position@plan` | `base_revision/mutation_revision` | `concept-network/concept-node?` | `concepts_surface.py` |
| 30 | `concept_change` / `operation=move_node` | `move` | `concept-node@claim` | `base_revision/mutation_revision` | `concept-network/concept-node?` | `concepts_surface.py` |
| 31 | `concept_history` / `concept_history` | `read` | `concept-node@claim` | `-` | `-` | `concepts_surface.py` |
| 32 | `concept_tree` / `concept_tree` | `read` | `concept-network@claim` | `-` | `-` | `concepts_surface.py` |
| 33 | `conversation_history` / `conversation_history` | `read` | `turn@project` | `before` | `NONE (pagination cursor, not an identity (writing_contracts.py:386))` | `authoring_surface.py` |
| 34 | `document` / `document` | `read` | `document-form@project` | `-` | `-` | `document_style.py` |
| 35 | `experiment_run` / `mode=full` | `run` | `experiment@run` | `-` | `-` | `research_surface.py` |
| 36 | `experiment_run` / `mode=smoke` | `run` | `experiment@run` | `-` | `-` | `research_surface.py` |
| 37 | `export_pdf` / `mode=selected-source` | `run` | `export@project` | `-` | `-` | `document_style.py` |
| 38 | `export_pdf` / `mode=style-preview` | `run` | `export@project` | `-` | `-` | `document_style.py` |
| 39 | `framing` / `framing` | `change` | `framing@plan` | `base_revision` | `authoring-state` | `writing_tools.py` |
| 40 | `help` / `help` | `read` | `contract@project` | `-` | `-` | `writing_operating.py` |
| 41 | `literature_bind` / `literature_bind` | `bind` | `reference@evidence` | `claim_revision` | `claim-meaning?` | `references_surface.py` |
| 42 | `literature_discover` / `literature_discover` | `read` | `reference-candidate@evidence` | `-` | `-` | `references_surface.py` |
| 43 | `literature_import` / `literature_import` | `create` | `reference@evidence` | `-` | `-` | `references_surface.py` |
| 44 | `literature_lookup` / `literature_lookup` | `read` | `reference@evidence` | `-` | `-` | `references_surface.py` |
| 45 | `literature_scope` / `literature_scope` | `read` | `reference@claim` | `-` | `-` | `references_surface.py` |
| 46 | `literature_uses` / `literature_uses` | `read` | `reference@claim` | `-` | `-` | `references_surface.py` |
| 47 | `logical_plan` / `view=attention` | `read` | `concept-network@plan` | `-` | `-` | `concepts_surface.py` |
| 48 | `logical_plan` / `view=catalog` | `read` | `concept-catalogue@plan` | `-` | `-` | `concepts_surface.py` |
| 49 | `logical_plan_change` / `operation=add_object` | `create` | `concept-node@claim` | `base_revision` | `concept-network` | `concepts_surface.py` |
| 50 | `logical_plan_change` / `operation=edit_meaning` | `change` | `claim-meaning@claim` | `base_revision` | `concept-network` | `concepts_surface.py` |
| 51 | `logical_plan_change` / `operation=connect` | `bind` | `relation@relation` | `base_revision` | `concept-network` | `concepts_surface.py` |
| 52 | `logical_plan_change` / `operation=add_obligation` | `create` | `obligation@claim` | `base_revision` | `concept-network` | `concepts_surface.py` |
| 53 | `logical_plan_change` / `operation=update_obligation` | `change` | `obligation@claim` | `base_revision` | `concept-network` | `concepts_surface.py` |
| 54 | `logical_plan_change` / `operation=route_obligation` | `bind` | `task@claim` | `base_revision` | `concept-network` | `concepts_surface.py` |
| 55 | `note` / `note` | `create` | `note@claim` | `supersedes` | `NONE (the id of the note being replaced: a payload reference, not an identity (writing_contracts.py:433, :436))` | `writing_tools.py` |
| 56 | `note_status` / `note_status` | `change` | `note@claim` | `base_revision` | `authoring-state?` | `writing_tools.py` |
| 57 | `note_status` / `status=resolved` | `delete` | `note@claim` | `base_revision` | `authoring-state?` | `writing_tools.py` |
| 58 | `note_status` / `status=dismissed` | `delete` | `note@claim` | `base_revision` | `authoring-state?` | `writing_tools.py` |
| 59 | `note_status` / `status=open` | `change` | `note@claim` | `base_revision` | `authoring-state?` | `writing_tools.py` |
| 60 | `pipeline` / `view=audit` | `read` | `pipeline@project` | `-` | `-` | `writing_pipeline.py` |
| 61 | `pipeline` / `view=summary` | `read` | `pipeline@project` | `-` | `-` | `writing_pipeline.py` |
| 62 | `project` / `project` | `read` | `project@project` | `-` | `-` | `writing_tools.py` |
| 63 | `project_guidance` / `project_guidance` | `read` | `guide-document@project` | `-` | `-` | `project_protocol.py` |
| 64 | `project_guidance_change` / `operation=configure` | `change` | `guide-catalogue@project` | `before/expected_catalog_revision` | `guide-document?/guide-catalogue` | `project_protocol.py` |
| 65 | `project_guidance_change` / `operation=write` | `change` | `guide-document@project` | `before/expected_catalog_revision` | `guide-document?/guide-catalogue` | `project_protocol.py` |
| 66 | `project_metadata` / `project_metadata` | `read` | `project-metadata@project` | `-` | `-` | `writing_projects.py` |
| 67 | `project_metadata_change` / `project_metadata_change` | `change` | `project-metadata@project` | `expected_revision` | `project-metadata` | `writing_projects.py` |
| 68 | `proof_check` / `proof_check` | `run` | `proof@claim` | `concept_revision/result_revision/source_revision` | `concept-network?/result?/producer?` | `formal_surface.py` |
| 69 | `proof_targets` / `proof_targets` | `read` | `proof@claim` | `-` | `-` | `formal_surface.py` |
| 70 | `proofs` / `proofs` | `read` | `proof@project` | `-` | `-` | `formal_surface.py` |
| 71 | `proposal_supersede` / `proposal_supersede` | `delete` | `proposal@paragraph` | `-` | `-` | `writing_tools.py` |
| 72 | `propose_revision` / `propose_revision` | `create` | `proposal@paragraph` | `-` | `-` | `authoring_surface.py` |
| 73 | `read_artifact` / `read_artifact` | `read` | `artifact@project` | `-` | `-` | `writing_tools.py` |
| 74 | `read_artifact` / `read_artifact` | `read` | `artifact@project` | `-` | `-` | `writing_tools.py` |
| 75 | `reference` / `reference` | `read` | `reference@evidence` | `-` | `-` | `references_surface.py` |
| 76 | `reference_attach` / `reference_attach` | `create` | `reference@evidence` | `-` | `-` | `references_surface.py` |
| 77 | `reference_fetch` / `reference_fetch` | `run` | `reference-text@evidence` | `-` | `-` | `references_surface.py` |
| 78 | `reference_refresh` / `reference_refresh` | `run` | `reference@project` | `-` | `-` | `references_surface.py` |
| 79 | `reference_source` / `reference_source` | `read` | `reference@evidence` | `-` | `-` | `references_surface.py` |
| 80 | `reference_text` / `reference_text` | `read` | `reference-text@evidence` | `-` | `-` | `references_surface.py` |
| 81 | `reference_update` / `reference_update` | `change` | `reference@evidence` | `-` | `-` | `references_surface.py` |
| 82 | `references` / `references` | `read` | `reference@project` | `-` | `-` | `references_surface.py` |
| 83 | `references_attached` / `references_attached` | `read` | `reference@project` | `-` | `-` | `references_surface.py` |
| 84 | `repository` / `action=list` | `read` | `repository@project` | `-` | `-` | `writing_sources.py` |
| 85 | `repository` / `action=files` | `read` | `repository-file@paragraph` | `-` | `-` | `writing_sources.py` |
| 86 | `repository` / `action=search` | `read` | `repository-file@paragraph` | `-` | `-` | `writing_sources.py` |
| 87 | `repository` / `action=read` | `read` | `repository-file@paragraph` | `-` | `-` | `writing_sources.py` |
| 88 | `repository` / `action=view` | `read` | `repository@project` | `-` | `-` | `writing_sources.py` |
| 89 | `research` / `view=full` | `read` | `result@project` | `-` | `-` | `research_surface.py` |
| 90 | `research` / `view=result` | `read` | `result@project` | `-` | `-` | `research_surface.py` |
| 91 | `research` / `view=summary` | `read` | `result@project` | `-` | `-` | `research_surface.py` |
| 92 | `research_producer` / `research_producer` | `create` | `producer@run` | `-` | `-` | `research_surface.py` |
| 93 | `research_reconcile` / `research_reconcile` | `change` | `result-binding@evidence` | `-` | `-` | `research_surface.py` |
| 94 | `research_record` / `research_record` | `record` | `result@run` | `expected_revision` | `result?` | `research_surface.py` |
| 95 | `run_cancel` / `run_cancel` | `change` | `run@run` | `-` | `-` | `research_surface.py` |
| 96 | `run_status` / `run_status` | `read` | `run@run` | `-` | `-` | `research_surface.py` |
| 97 | `section_change` / `operation=convert` | `change` | `section@section` | `expected_plan_revision/expected_source_digest` | `plan|plan-file/source-file` | `manuscript_structure.py` |
| 98 | `section_change` / `operation=create` | `create` | `section@section` | `expected_plan_revision/expected_source_digest` | `plan|plan-file/source-file` | `manuscript_structure.py` |
| 99 | `section_change` / `operation=create-section` | `create` | `section@section` | `expected_plan_revision/expected_source_digest` | `plan|plan-file/source-file` | `manuscript_structure.py` |
| 100 | `section_change` / `operation=delete` | `delete` | `section@section` | `expected_plan_revision/expected_source_digest` | `plan|plan-file/source-file` | `manuscript_structure.py` |
| 101 | `section_change` / `operation=delete-section` | `delete` | `section@section` | `expected_plan_revision/expected_source_digest` | `plan|plan-file/source-file` | `manuscript_structure.py` |
| 102 | `section_change` / `operation=insert-heading` | `create` | `heading@section` | `expected_plan_revision/expected_source_digest` | `plan|plan-file/source-file` | `manuscript_structure.py` |
| 103 | `section_change` / `operation=restore` | `create` | `section@section` | `expected_plan_revision/expected_source_digest` | `plan|plan-file/source-file` | `manuscript_structure.py` |
| 104 | `section_change` / `operation=restore-section` | `create` | `section@section` | `expected_plan_revision/expected_source_digest` | `plan|plan-file/source-file` | `manuscript_structure.py` |
| 105 | `section_change` / `operation=undo-create` | `delete` | `section@section` | `expected_plan_revision/expected_source_digest` | `plan|plan-file/source-file` | `manuscript_structure.py` |
| 106 | `source` / `source` | `read` | `source-file@paragraph` | `-` | `-` | `writing_tools.py` |
| 107 | `store_artifact` / `store_artifact` | `change` | `artifact@project` | `before` | `artifact` | `writing_tools.py` |
| 108 | `store_artifact` / `store_artifact` | `change` | `artifact@project` | `expected_revision` | `artifact` | `writing_tools.py` |
| 109 | `structure` / `structure` | `read` | `plan@plan` | `-` | `-` | `project_structure.py` |
| 110 | `structure_change` / `operation=initialize` | `create` | `plan@plan` | `expected_revision/expected_source_revision` | `plan/selected-edition` | `project_structure.py` |
| 111 | `structure_change` / `operation=plan` | `change` | `plan-section@section` | `expected_revision` | `plan` | `project_structure.py` |
| 112 | `structure_change operation=plan` / `op.kind=add-section` | `create` | `plan-section@section` | `expected_revision` | `plan` | `project_structure.py` |
| 113 | `structure_change operation=plan` / `op.kind=remove-section` | `delete` | `plan-section@section` | `expected_revision` | `plan` | `project_structure.py` |
| 114 | `structure_change operation=plan` / `op.kind=restore-section` | `create` | `plan-section@section` | `expected_revision` | `plan` | `project_structure.py` |
| 115 | `structure_change operation=plan` / `op.kind=set-outline` | `change` | `plan@plan` | `expected_revision` | `plan` | `project_structure.py` |
| 116 | `structure_change operation=plan` / `op.kind=reorder-sections` | `move` | `plan-section@section` | `expected_revision` | `plan` | `project_structure.py` |
| 117 | `structure_change operation=plan` / `op.kind=reorder-appendices` | `move` | `plan-section@section` | `expected_revision` | `plan` | `project_structure.py` |
| 118 | `structure_change operation=plan` / `op.kind=retitle` | `change` | `plan-section@section` | `expected_revision` | `plan` | `project_structure.py` |
| 119 | `structure_change operation=plan` / `op.kind=reorder-nodes` | `move` | `claim-position@section` | `expected_revision` | `plan` | `project_structure.py` |
| 120 | `structure_change operation=plan` / `op.kind=edit-job` | `change` | `plan-section@section` | `expected_revision` | `plan` | `project_structure.py` |
| 121 | `structure_change operation=plan` / `op.kind=edit-notes` | `change` | `plan-section@section` | `expected_revision` | `plan` | `project_structure.py` |
| 122 | `structure_change operation=plan` / `op.kind=set-refs` | `bind` | `reference@section` | `expected_revision` | `plan` | `project_structure.py` |
| 123 | `structure_change operation=plan` / `op.kind=move-node` | `move` | `claim-position@section` | `expected_revision` | `plan` | `project_structure.py` |
| 124 | `structure_change operation=plan` / `op.kind=add-node` | `place` | `claim-position@section` | `expected_revision` | `plan` | `project_structure.py` |
| 125 | `structure_change operation=plan` / `op.kind=remove-node` | `delete` | `claim-position@section` | `expected_revision` | `plan` | `project_structure.py` |
| 126 | `structure_change operation=plan` / `op.kind=toggle-beat` | `change` | `plan-section@section` | `expected_revision` | `plan` | `project_structure.py` |
| 127 | `structure_change operation=plan` / `op.kind=set-nodes` | `place` | `claim-position@section` | `expected_revision` | `plan` | `project_structure.py` |
| 128 | `structure_change operation=plan` / `op.kind=set-meta` | `change` | `plan-section@section` | `expected_revision` | `plan` | `project_structure.py` |
| 129 | `structure_change operation=plan` / `op.kind=set-serves` | `bind` | `claim-position@section` | `expected_revision` | `plan` | `project_structure.py` |
| 130 | `structure_change` / `operation=spine` | `move` | `spine-position@plan` | `expected_revision` | `plan` | `project_structure.py` |
| 131 | `structure_change operation=spine` / `op.kind=reorder-spine` | `move` | `spine-position@plan` | `expected_revision` | `plan` | `project_structure.py` |
| 132 | `structure_change operation=spine` / `op.kind=set-narrative` | `place` | `spine-position@plan` | `expected_revision` | `plan` | `project_structure.py` |
| 133 | `structure_change operation=spine` / `op.kind=unset-spine` | `delete` | `spine-position@plan` | `expected_revision` | `plan` | `project_structure.py` |
| 134 | `structure_change` / `operation=reconcile` | `run` | `plan@plan` | `expected_revision` | `plan` | `project_structure.py` |
| 135 | `structure_change` / `operation=bind_results` | `bind` | `result@claim` | `expected_concept_revision/expected_revision` | `concept-network/plan` | `project_structure.py` |
| 136 | `style` / `style` | `change` | `document-form@project` | `-` | `-` | `writing_style.py` |
| 137 | `task` / `task` | `create` | `task@section` | `-` | `-` | `writing_tools.py` |
| 138 | `task_status` / `task_status` | `change` | `task@evidence` | `-` | `-` | `writing_tools.py` |
| 139 | `visual_create` / `visual_create` | `create` | `visual-spec@run` | `-` | `-` | `visuals_surface.py` |
| 140 | `visual_create` / `visual_create` | `create` | `visual-spec@run` | `expected_revision` | `visual-spec` | `visuals_surface.py` |
| 141 | `visual_place` / `visual_place` | `place` | `visual@section` | `-` | `-` | `visuals_surface.py` |
| 142 | `visual_place` / `visual_place` | `place` | `visual@section` | `-` | `-` | `visuals_surface.py` |
| 143 | `visual_render` / `visual_render` | `run` | `visual@run` | `-` | `-` | `visuals_surface.py` |
| 144 | `visuals` / `visuals` | `read` | `visual@project` | `-` | `-` | `visuals_surface.py` |
| 145 | `writing_stage` / `view=full` | `read` | `stage@project` | `known_revision` | `stage?` | `writing_stages.py` |
| 146 | `writing_stage` / `view=guidance` | `read` | `stage@project` | `known_revision` | `stage?` | `writing_stages.py` |
| 147 | `writing_stage` / `view=materials` | `read` | `stage@project` | `known_revision` | `stage?` | `writing_stages.py` |
| 148 | `writing_stage` / `view=summary` | `read` | `stage@project` | `known_revision` | `stage?` | `writing_stages.py` |
| 149 | `writing_style` / `view=profile` | `read` | `style-profile@project` | `-` | `-` | `writing_style.py` |
| 150 | `writing_style` / `view=provenance` | `read` | `style-provenance@project` | `-` | `-` | `writing_style.py` |
| 151 | `writing_style` / `view=summary` | `read` | `style-state@project` | `-` | `-` | `writing_style.py` |
| 152 | `writing_style_calibration` / `writing_style_calibration` | `read` | `style-calibration@project` | `-` | `-` | `writing_style.py` |
| 153 | `writing_style_change` / `writing_style_change` | `change` | `style-state@project` | `expected_revision` | `style-state` | `project_work.py` |
| 154 | `writing_style_profile_change` / `basis=author_preference` | `change` | `style-profile@project` | `expected_profile_revision/expected_provenance_revision` | `style-profile/style-provenance?` | `project_work.py` |
| 155 | `writing_style_profile_change` / `basis=source_calibration` | `change` | `style-profile@project` | `expected_profile_revision/expected_provenance_revision` | `style-profile/style-provenance` | `project_work.py` |
| 156 | `materials` / `materials` | `read` | `artifact@project` | `-` | `-` | `project_work_surface.py` |
| 157 | `storage` / `storage` | `read` | `storage@project` | `-` | `-` | `writing_storage.py` |
| 158 | `storage_prune` / `storage_prune` | `delete` | `storage@project` | `-` | `-` | `writing_storage.py` |
| 159 | `repository` / `action=interface` | `read` | `contract@project` | `-` | `-` | `writing_sources.py` |
| 160 | `session_settings` / `session_settings` | `read` | `turn@project` | `-` | `-` | `authoring_surface.py` |
| 161 | `session_settings_change` / `session_settings_change` | `change` | `turn@project` | `-` | `-` | `authoring_surface.py` |
| 162 | `dispatch_plan` / `dispatch_plan` | `create` | `task@project` | `-` | `-` | `project_work.py` |
| 163 | `dispatch` / `dispatch` | `read` | `task@project` | `-` | `-` | `project_work.py` |
| 164 | `dispatch_launch` / `dispatch_launch` | `run` | `task@project` | `-` | `-` | `authoring_surface.py` |
| 165 | `dispatch_status` / `dispatch_status` | `read` | `task@project` | `-` | `-` | `authoring_surface.py` |
| 166 | `dispatch_returns` / `dispatch_returns` | `read` | `task@project` | `-` | `-` | `writing_tools.py` |
| 167 | `app_settings` / `scope=application` | `read` | `contract@project` | `-` | `-` | `writing_projects.py` |
| 168 | `material_references` / `material_references` | `read` | `material-reference@project` | `-` | `-` | `writing_projects.py` |
| 169 | `material_reference_change` / `action=attach` | `create` | `material-reference@project` | `expected_revision` | `project-metadata` | `writing_projects.py` |
| 170 | `material_reference_change` / `action=adopt` | `change` | `material-reference@project` | `expected_revision` | `project-metadata` | `writing_projects.py` |
| 171 | `material_reference_change` / `action=remove` | `delete` | `material-reference@project` | `expected_revision` | `project-metadata` | `writing_projects.py` |

<!-- END MAPPING TABLE -->

---

## 8. INSTALL — what each lane runs

Each build lane works in its own git worktree and never touches
`/home/phujck/VScodeProjects/laplace/src`. From the lane's worktree root:

**The installed suite is self-contained.** Step 1 copies *every* file the proofs read into the
worktree, so a later edit in this packet's directory shows up as a diff at the lane's next install
rather than as a silently changed test result underneath it. In round 1 the installed test read
`map_verbs.py`, `GRAMMAR.md` and `mapping.csv` from the live evidence tree — in a campaign whose
acceptance is differential replay per branch, one edit here would have moved ten lanes' results at
once.

**Round 2's list was one file short, and every lane hit it.** The copy omitted `grammar.py` itself,
which `test_grammar.py:149` reads *as a file* (the one-digest-form proof greps the module and the
document for a string that must be absent from both), so the first install of each of the four build
lanes failed with `FileNotFoundError: …/tests/grammar_spec/grammar.py`. "Every file the proofs read"
is now a check rather than a promise: `::test_the_install_block_copies_every_file_the_proofs_read`
collects every `GRAMMAR_DIR / "…"` path in the suite, asserts the block below copies each one, and
asserts the expected-pass number in this section equals the number of tests in the suite.

```bash
G=/home/phujck/VScodeProjects/laplace/evidence/WRITING_RECONCILIATION_2026-10-02/grammar
A=/home/phujck/VScodeProjects/laplace/evidence/WRITING_FRICTION_2026-10-01/wave1/verb-altitude-audit

# 1. The module, and the FIVE files its proofs read, into the worktree.
cp "$G/grammar.py" "$WORKTREE/src/laplace/grammar.py"
mkdir -p "$WORKTREE/tests/grammar_spec"      # NOT tests/grammar: a directory of that name
cp "$G/grammar.py" "$G/map_verbs.py" "$G/mapping.csv" "$G/GRAMMAR.md" \
   "$G/obtain_census.py" "$G/by_census.py" \
   "$WORKTREE/tests/grammar_spec/"           # imports as an empty namespace package and
cp "$A/verb_matrix.csv" "$WORKTREE/tests/grammar_spec/verb_matrix.csv"   # shadows the module
#  ^ grammar.py twice ON PURPOSE: src/ is the module the tree imports, grammar_spec/ is the
#    FILE two proofs read (test_grammar.py:149 and by_census's fallback import).

# 2. The proofs, next to the tree's own tests.
cp "$G/test_grammar.py" "$WORKTREE/tests/test_grammar.py"

# 3. Point the copied test at the installed module and at the COPIED grammar files.
#    Three substitutions, no path into the live tree left behind.
cd "$WORKTREE" && python3 - <<'EOF'
import pathlib
p = pathlib.Path("tests/test_grammar.py")
s = p.read_text()
s = s.replace('TREE = Path("/home/phujck/VScodeProjects/laplace")',
              'TREE = Path(__file__).resolve().parents[1]')
s = s.replace('GRAMMAR_DIR = HERE', 'GRAMMAR_DIR = HERE / "grammar_spec"')
s = s.replace("sys.path.insert(0, str(GRAMMAR_DIR))\n\nimport grammar as g",
              "sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))\n\n"
              "from laplace import grammar as g")
assert 'GRAMMAR_DIR = HERE / "grammar_spec"' in s and "from laplace import grammar as g" in s
p.write_text(s)
EOF

# 4. Run them from the worktree, with its own runtime.
cd "$WORKTREE" && scripts/laplace-python -m pytest -q tests/test_grammar.py \
  --basetemp="/tmp/pytest-$(basename "$WORKTREE")-grammar" -p no:cacheprovider
```

**Expected: `46 passed`, and that number was measured in a real git worktree, not a stand-in.**
(Round 2 said `39` from a run whose install was missing `grammar.py`; with the file copied that same
suite was `42`, and round 3 added four proofs — the prefixed-token round trip, the carrier, the `by`
census and this block's own check.)
Round 1 told lanes to expect `27 passed`; a git worktree actually got `24 passed, 3 skipped`,
because the three real-project tests read `writing-system-friction-report`, whose registry row and
corpus are **untracked** (`git show HEAD:registry_projects.json | grep -c
writing-system-friction-report` → `0`). The three tests that vacated were the collapse proof and
both "two reads of an unchanged owner home mint equal tokens" proofs — precisely the
parity-relevant evidence. They now read **`synthetics-foundations`**, whose registry row and 971
corpus files *are* tracked at `HEAD` (`git ls-files -- 'synthetics papers/synthetics-foundations' |
wc -l` → `971`), and they **fail** rather than skip if it is missing. The measurement:

```
$ git worktree add --detach $WT HEAD                      # a real worktree of HEAD, 706a8204
$ cd $WT && <steps 1-3 above>
$ cd $WT && scripts/laplace-python -m pytest -q tests/test_grammar.py \
    --basetemp=/tmp/pytest-grammar-installed-fix2 -p no:cacheprovider
..............................................                           [100%]
46 passed in 34.65s
$ cd $WT && scripts/laplace-python tests/grammar_spec/obtain_census.py \
    synthetics-foundations $WT | tail -2
DECLARED MINT_STATUS vs OBSERVED: 0 mismatches
{"minted": 38, "unwired": 18, "wired_but_absent": 2, "total": 58, "declared_read": 40,
 "declared_caller_value": 18, "mismatches": 0}
$ cd $WT && scripts/laplace-python tests/grammar_spec/by_census.py $WT | tail -2
  status counts: {'refused': 18, 'dropped': 51, 'overwritten': 4}
DECLARED `by` STATUS MATCHES THE DOORS
```

(The home-kind figures are 58/38 and not round 2's 59/39 because `plan-state` was deleted into
`plan`: one set of bytes, one home kind. The census says `0 mismatches` either way.)

The whole transcript, including the two `git` observations above, is in
`wave1/grammar/install_in_a_real_worktree.out`. One thing it also records: the first attempt
installed into `tests/grammar/`, and a directory of that name imports as an **empty namespace
package** that shadows `grammar`, so two tests failed with `module 'grammar' has no attribute
'HOME_KINDS'`. The directory is `tests/grammar_spec/` and both generators resolve
`laplace.grammar` first; the failure is written into their docstrings so no lane rediscovers it.

**What a lane must not do.** Do not edit `grammar.py` in place to add a home kind or a verb: send
the addition back to this packet's directory with the measurement that demands it, so all four
build lanes install the same bytes. Two lanes with two `grammar.py` files is the 20-names defect
with a new spelling.

**What a lane adds.** Its own shims (from `mapping.csv`), its own concept payload schemas, and —
where it needs one of the 18 homes `OWNER_READS` does not wire yet (§2.1) — one `OwnerRead` entry naming
the owner read, never a recomputed digest.

---

## 9. What this packet did not establish

Stated as numbers, because round 1 of this packet stated two of these as "three" and "14" when the
measured answer was 34, and a lane that trusts an understated residual builds on it.

- **18 of the 58 home kinds cannot be obtained from the home alone** (`identity(home)` raises
  `NotImplementedError`); the caller must hold the value and pass `value=`. They are listed, one
  per row with the read or owner publication that would close it, in **§2.1** — which is generated
  from `grammar.py`, so the list cannot drift from the module. The partition is `MINT_STATUS`:
  **40 `read`, 18 `caller-value`**, and a test compares it against the behaviour on a real project.
  Round 1's figure for this residual was "three recipe-`J` homes" plus "14 unwired `O` homes"; the
  measured figure then was 34 of 59, and the gap was closed by wiring 17 more reads, not by
  restating it.
- **The 21 recipe-`J` homes carry a digest no owner publishes.** §1 scopes the no-new-digest claim
  to `O` and `B` and says so for `J`. No door in the census compares a `J` home today — asserted by
  `test_no_door_compares_a_recipe_j_home`, not by this sentence — so no live refusal depends on a
  digest this layer invents; but the harness lane must not count a `J` token as replay evidence.
  The `J` homes that declared a guard in round 1 (`visual`, the duplicate plan kind, `block` under
  the wrong recipe) and in round 2 (`note`'s `supersedes`, a reference and not an identity) are
  corrected rather than explained.
- **The 65 concepts' payload schemas are not written.** This packet closes the request shape, the
  home list and the `(verb, concept)` set (104 declared pairs); the per-concept schemas are the
  contract lane's work, from `mapping.csv`.
- **Replay parity is not run here.** The claim that `O` and `B` tokens are parity-safe rests on
  their being the owner's own value read at a named path (or the owner's own digest function over
  the same bytes), verified on two projects for 12 home kinds by `home_census.py` and on 38 of 58
  kinds by `obtain_census.py` — not on a replay. The harness lane runs the replay. The one home
  whose owner keeps a counter, `authoring-state`, is parity-safe in the weaker sense §1 states: the
  file is in the corpus, and the token refuses in one case the counter accepts (`:1084`).
- **`identity()` was measured on one project in one worktree.** `synthetics-foundations`:
  38 of 58 kinds minted, 0 declaration mismatches, 2 wired reads whose home that project does not
  contain (`relation`, `reference`). A project with relations and an attached reference library
  would exercise those two; no such project is tracked at `HEAD`, which is itself worth knowing
  before the harness lane picks its corpus.
- **Two owner reads are wired through a projection whose row carries live state**, and are therefore
  *not* wired: `act-ledger` and `change-history` publish pages carrying `as_of` (a wall clock,
  observed in this packet), so two reads of an unchanged ledger would mint two tokens. They are in
  the §2.1 list with that reason. Any lane tempted to wire them must first make the owner publish a
  page digest that excludes `as_of`.
- **The six-identity-fields-from-one-`source`-read count is three homes, not six names over three
  values as the audit put it** — but the audit's §1.3 example read the selected root, where
  `selected-edition` and `source-file` coincide. On a non-root file the split is visible. Anyone
  re-deriving the audit's table from a root file will reproduce the collapse and should not read it
  as agreement.
- **`source-traversal`'s mint rule was wrong in round 1** and is corrected here: the live value is
  `pipeline/authoring.py:439-447`'s `_revision` — `file` + NUL + full `text` + NUL per row **in
  traversal order** — computed at `:722` and published at `:796`. Round 1 cited
  `manuscript_structure.py:351-352`, which digests a *sorted* `[{file, sha256}]` snapshot as the
  `SOURCE_ONLY` plan fallback: a different value under a name one letter apart. The two are
  not interchangeable and a lane that used one for the other would get a refusal it could not read.


### Exact served rewrite retry lineage

The existing editor HTTP/native grammar adapter accepts optional payload `rewrite_retry`, whose closed schema is owned by `review_surface.rewrite_retry_contract()`: `schema_version=laplace.rewrite-retry/1`, exact first `pending_id`, and owner-issued `intent_sha256`. Carry only the first pending receipt's witness through the one `{request, refused.needed}` retry. It is not a new token home or permission. Refreshed identity guards may change; the normalized original effect/attribution intent must not. The same rewrite owner resolves that exact pending feedback only after a successful source swap and records the applied feedback ID. Resolution failure preserves the effect ACK and reports the unresolved ID; no repeated effect or implicit old-row migration follows.
