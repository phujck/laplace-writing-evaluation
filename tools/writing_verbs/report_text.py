"""The fixed prose of the lane report. Every NUMBER is substituted by emit_report.py from a
banked measurement file, so no figure in the report is typed in two places."""

HEAD = """# Altitude dispatch: one verb per act, the concept carries the altitude

## 0. Where the work is

**worktree** `/home/phujck/VScodeProjects/laplace/.claude/worktrees/wf_2b127eb4-edb-11`, branch
`worktree-wf_2b127eb4-edb-11`, built on `706a82047ae9`. Master is untouched and nothing is pushed.
**Final commit on the branch: `@@COMMIT@@`** -- the judge and the synthesis work from that commit.
Wave `WRITING-RECONCILIATION-W1`, packet `altitude-dispatch`, 2026-10-02. Evidence:
`evidence/WRITING_RECONCILIATION_2026-10-02/wave1/altitude-dispatch/`.

The friction report of 2026-10-01 measured the disease: **152 verbs through 73 operation names**,
create-a-unit spelled five ways at five altitudes with four guard spellings, and a banked row that
records the operation name rather than the act (`src/laplace/writing_tools.py:974-971` and
`src/laplace/writing_tools.py:1015-1006`, as the lines stand at `706a8204`; in this branch the same
two rows are at `:969-974` and `:1011-1017`). This lane installs the dispatch the grammar packet's
alphabet implies: **nine verbs, 65 concepts, 104 declared pairs, @@ROUTES@@ routes, one request
shape**, each route reaching an owner call that already exists, and a banked row carrying verb,
concept and altitude on every caller path.

No owner was rewritten, and that is not a claim about intent: the whole diff against `706a8204`
under `src/` is three files -- `writing_verbs.py` and the grammar packet's `grammar.py`, both new, and
exactly one existing file, `writing_tools.py`, by **108 insertions and 0 deletions in four hunks**
(`git diff --numstat 706a82047ae9 -- src/`). Not one line of an owner module changed, and not one line
deleted anywhere.

The parity argument is a check rather than a promise. For every replayable row of the
recorded corpus the dispatch rebuilds the owner call out of the grammar request and compares it,
**per call at runtime**, with the legacy pair; only an identical pair is used, and any difference
falls through to the legacy payload untouched (`src/laplace/writing_tools.py:957-951`). An owner
handed the same `(operation, payload)` cannot behave differently, which is why the differential
replay can be clean -- and section 5 is the measurement, not the hope.

---

## 1. What is in the tree

| file | what it is |
|---|---|
| `src/laplace/native/verbs.py` | the dispatch: `ROUTES`, `from_owner_call` (the shim direction), `to_owner_call` (the verb direction), `classify` (what every caller path records), `SHIMS`, `resolver` |
| `src/laplace/native/tools.py` | **86 insertions, 0 deletions, four hunks** against `706a8204` -- nothing in the router is rewritten or removed: `execute` routes every call through `classify` (`:942-951`); the two banked rows gain the act's grain (`:971` inside the read row at `:969-974`, `:1013` inside the action row at `:1011-1017`); a third branch banks the same two record kinds on a path with no turn (`:1020-1047`); `request()` is the verb door (`:1089-1133`) |
| `src/laplace/core/grammar.py` | the grammar packet's module, installed per GRAMMAR.md section 8, unedited |
| `tools/writing_verbs/gen_routes.py` | the generator. `ROUTES` is spliced from `tests/grammar_spec/mapping.csv` and from `writing_tools.py`'s own handler lines, so neither the table nor its citations are hand-typed |
| `tools/writing_verbs/corpus_round_trip.py` | the round-trip measurement over the recorded corpus |
| `tools/writing_verbs/verb_door_demo.py` | the verb door driven against a real workspace: the five content-tree altitudes of section 3, the banked rows, and the pin for the one that cannot apply |
| `tools/writing_verbs/replay_verb_door.py` + `_worker.py` | the BOTH-WAYS replay: one tree, two doors, the four parity kinds (section 5). The worker is the harness's protocol plus `{"op": "request"}` |
| `tools/writing_verbs/shim_retirement.py` | the retirement ledger: RETIRABLE / HELD-UNREACHABLE / HELD-UNEXERCISED for every route, from the deposited both-ways run |
| `tools/writing_verbs/make_bank_on_allow.py` | the allow list for the configuration that SHIPS, with every row checked rather than listed |
| `tools/writing_verbs/emit_tables.py`, `emit_report.py`, `report_text.py` | the evidence tables and this report, both rendered from the measurements |
| `tests/test_writing_verbs.py` | 17 proofs. `tests/test_grammar.py` is the grammar packet's 42 |

## 2. The dispatch table

Row source: `tests/grammar_spec/mapping.csv` -- the grammar packet's own file, installed unedited,
its digest recorded in `writing_verbs.GENERATED_FROM` as
`mapping.csv lf-lines sha256:21b1bcf30ca934e4cf6c1b1601fd65142c60126ab9033e5c588f2ae3c1ff1473`.

**That line used to be a provenance that was true of my working file and false of the artifact a judge
checks out, and the test that guards it used to pass only for me.** The packet's `mapping.csv` carries
CRLF line endings (156 CR bytes); this repository has `core.autocrlf=input`, so the committed blob was
the LF form and its raw-byte digest was `a596903a...` where my working file's was `36f0fd51...`. In a
fresh checkout `gen_routes.py --tree . --check` therefore printed `ROUTES up to date: False` and
`tests/test_writing_verbs.py::test_the_route_table_is_exactly_what_the_mapping_generates` FAILED --
the one test whose own message says a hand-edited dispatch table "is the 20-names defect with a new
spelling" -- while in my worktree it printed `True` on a clean `git status`. Two cures, both landed:
the digest is now taken over LF-NORMALISED LINES, because what a provenance line owes is a digest of
the ROWS; and `mapping.csv` was re-added with `tests/grammar_spec/.gitattributes`'s `* -text` in force
so the blob carries the packet's bytes verbatim as well. Verified where it matters, in a
`git worktree add --detach` of the final commit: **156 CR bytes present, `ROUTES up to date: True`,
and `tests/test_writing_verbs.py` + `tests/test_grammar.py` 64 passed** (22 lane proofs and the
grammar packet's 42). Full table:
`altitude-dispatch/dispatch.csv`, @@ROUTES@@ rows, each with its owner call and the line in
`writing_tools.py` that makes it. Counts: `altitude-dispatch/dispatch_counts.json`.

| | |
|---|---|
| routes | **@@ROUTES@@** |
| old operation names they retire | **@@OLDNAMES@@** |
| verbs used | **9** -- bind, change, create, delete, move, place, read, record, run |
| concepts | **65**, in **104** declared `(verb, concept)` pairs |
| altitudes reached | 9: chapter, claim, evidence, paragraph, plan, project, relation, run, section. `book` is declared and unreached: no verb acts on the manuscript as a whole |
| routes carrying a guard | **@@GUARDED@@**, over **@@GNAMES@@** guard names and **@@GHOMES@@** homes |
| guard forms | @@GFORMS@@ |
| reachable from the verb door | **@@VERBROUTES@@** routes, covering **104 of 104** pairs |
| reachable only through the old name | **@@SHIMROUTES@@**, each carrying its reason in `Route.because` |
| owner citations verified by test | **@@CITED@@** of @@ROUTES@@ |

**The nine verbs recur at every altitude** instead of a new vocabulary per depth
(`dispatch_counts.json`, key `verbs_by_altitude`):

| altitude | verbs |
|---|---|
| project | change, read, run |
| chapter | create |
| section | bind, change, create, delete, move, place |
| paragraph | change, create, delete, move, read |
| plan | change, create, delete, move, place, read, run |
| claim | bind, change, create, delete, move, read, run |
| relation | bind, change, delete |
| evidence | bind, change, create, read, run |
| run | change, create, read, record, run |

**What a route carries, and why each field has to exist.**

* `selector` -- the old discriminator that named the sub-verb, split in two. `lift` holds the pairs
  that NAME THE ACT (`operation=`, `op.kind=`); they come out of the payload, because the verb and
  the concept name the act now. The rest (`view=`, `mode=`, `action=`, `basis=`, `status=`, `kind=`)
  stay in the payload, because `view=audit` against `view=summary` is two projections of one home,
  not two verbs -- specialisation in the concept's payload schema, as GRAMMAR.md section 4 rules. A
  payload that omits a kept key still names the route whose value is the owner's own default. Each of
  the eight defaults is declared as `(value, the line that applies it, how)`, where `how` is
  `spelled` when the cited line writes the default itself (`src/laplace/writing_sources.py:252`,
  `src/laplace/writing_stages.py:60`) and `else-branch:<other>` when the owner has no default and
  sends everything that is not `<other>` to this read (`src/laplace/writing_tools.py:608` for
  `research`), and `::test_every_selector_default_is_the_line_it_cites` checks the cited line still
  says so. Two keys are deliberately NOT declared, because their owner requires them:
  `experiment_run`'s `mode` and `writing_style_profile_change`'s `basis`
  (`src/laplace/writing_style.py:374`). An old spelling the owner itself normalises also still names its route:
  nine audited `section_change` sub-verbs are five acts at
  `src/laplace/manuscript_structure.py:1043-1044`, so `create-section` reaches
  `create section@section` and is not refused over the spelling.
* `guards` -- `(old name, home, form, optional)`. The form is the measured answer to "can a token
  carry this value?", and there are four because the system has four:
  * **digest**, @@GDIGEST@@ routes. The token's digest IS the owner's published value for a recipe `O` or
    `B` home, so restoring it is verbatim. 104 of the 110 guard values in the whole recorded corpus
    are 64-hex digests (measured).
  * **counter**, @@GCOUNTER@@. The `authoring-state` home: its door compares a monotone integer
    (`src/laplace/pipeline/authoring.py:398-399`), not a digest. The route restores the integer --
    the owner's own current counter when the token matches `authoring.json`, and the token itself
    when it does not, so the owner refuses in its own house with its own sentence. **Zero corpus
    rows exercise this path**, which is why it is stated rather than relied on.
  * **text**, @@GTEXT@@. `before`. The editor's rewrite door compares the exact previous TEXT of the span
    (`src/laplace/review_surface.py:1860`), the whole-file undo compares the whole text
    (`src/laplace/manuscript_blocks.py:166`), and no digest reconstructs text. So the text travels
    as content under one uniform name, `before_content`, with the `prose` token beside it in
    `expected`. A caller may send the token alone: the dispatch reads the addressed span and hands
    the bytes to the owner only when their digest matches the token; when it does not, it hands the
    owner the token, so the refusal is still the owner's.
  * **cursor**, @@GCURSOR@@. `conversation_history`'s `before` is a pagination cursor
    (`src/laplace/writing_contracts.py:386`), not an identity -- GRAMMAR.md section 2.1 already
    records it as a miscount in the 20-name census, and the dispatch treats it as content.
* `owner` + `site` -- the branch of `writing_tools._execute` that reaches the owner, read out of the
  file by the generator, with a test that the cited line is still a handler (section 9, finding 5).
* `door` + `because` -- whether the verb door can reach the route, and if not, exactly why.
* `expiry` -- on every route, hence on every shim, and **its own sentence per route**. It used to
  be one identical string on all @@ROUTES@@ of them, naming a condition ("replay parity through the
  verb door alone") that no deposited instrument could evaluate: an expiry in form, with no measurable
  condition and no per-shim retirement. Each one now names its own old spelling, its own
  `(verb, concept)`, the deposited run `parity-verb-door/rows.jsonl` and the tool that reads it,
  `tools/writing_verbs/shim_retirement.py` -- which answers RETIRABLE, HELD-UNREACHABLE or
  HELD-UNEXERCISED for every route (section 5). 131 distinct sentences over @@ROUTES@@ routes, with
  `::test_every_expiry_is_this_route_s_own_and_names_the_instrument_that_tests_it` asserting that each
  names its route, carries a date, names the instrument and says HELD exactly when its door is
  `shim`.

### The round trip, measured on the recorded corpus

`to_owner_call(from_owner_call(op, payload)) == (op, payload)` over the 559 tool-door rows
(`corpus_round_trip.json`, `corpus_round_trip.out`):

| | rows |
|---|---|
| rebuilt exactly -- the dispatch is in the causal path | **@@EXACT@@** |
| rebuilt, but not byte-identically -- falls through to the legacy payload | **@@INEXACT@@** |
| no route: the call names no act | **@@UNMAPPED@@** |
| reachable from the verb door given the request alone | @@VERBDOOR@@ |
| reachable only through the old name | @@SHIMONLY@@ |

The @@INEXACT@@ are all one cause and it is not a gap in the table: they spell a guard with the
owner's `sha256:` prefix at a door that compares the string RAW (`manuscript_structure`,
`writing_stages`), and the grammar's token normalises the spelling (GRAMMAR.md section 1), so
re-spelling them could change an outcome. They fall through, which costs the dispatch its place in
the causal path for those nine rows and costs the owner nothing.

The @@UNMAPPED@@ are two kinds, both real: **31** are recorded write rows whose payload is **empty**,
and **5** are not writing operations at all (`Bash`, `Write` -- the failure census records every
tool). An empty payload names no act, and the dispatch says so rather than guessing one: six of those
31 are `experiment_run`, whose owner requires `producer_id` and an explicit mode, so there is no
default to fall back on. The empty payloads are not a corpus defect either; see section 9, finding 7.

## 3. Create at five altitudes: one request shape, one guard list

The audit's "create a unit" is 9 operations, 21 verbs, 10 altitudes and 7 guard spellings
(`evidence/WRITING_FRICTION_2026-10-01/wave1/verb-altitude-audit/acts_by_altitude.csv`). Its five
content-tree verbs, and the whole of what changes:

| altitude | before | guard spelling(s) before | after |
|---|---|---|---|
| paragraph | `block_change {operation: insert, ...}` | **none declared** -- `block_change`'s contract declares no guard at all | `create block@paragraph` |
| section | `section_change {operation: create-section, ...}` | `expected_plan_revision` + `expected_source_digest` | `create section@section` |
| chapter | `chapter {title, expected_root_digest}` | `expected_root_digest`, optional | `create chapter@chapter` |
| plan | `structure_change {operation: plan, op: {kind: add-section}, ...}` | `expected_revision` | `create plan-section@section` |
| claim | `concept_change {operation: add_node, ...}` | `base_revision` + `mutation_revision` | `create concept-node@claim` |

Six guard spellings over five homes, not the audit's four: `concept_change add_node` declares two
(`mapping.csv` row 22). After the reconciliation the caller writes
`{verb, concept, target, expected, payload, by}` at every altitude, `expected` is a list of tokens,
and which home a token belongs to is read OFF THE TOKEN rather than inferred from a field name.
`tests/test_writing_verbs.py::test_create_is_one_request_shape_at_every_altitude` asserts the five
rebuild into the five old calls with one request shape;
`::test_one_guard_per_altitude_is_one_token_whose_home_is_in_the_token` mints a token per home and
asserts the owner receives it under its old name.

### Applied, not described: four of the five through the verb door

Structural proof is not an applied act, so the five were driven against a prepared workspace through
`writing_tools.request()` and nothing else (`tools/writing_verbs/verb_door_demo.py`, deposited as
`verb-door/demo.out` and `demo.json`; `::test_the_deposited_demo_applied_four_of_the_five_altitudes_and_pinned_the_fifth`
asserts the deposit). A project is created through the same HTTP door the arrival uses, the plan is
initialised through the verb door, and then each altitude is asked in the owners' own dependency order,
with the tokens re-read before every step because each applied write moves a home.

| altitude | request | result | the OWNER prerequisite the route does not supply |
|---|---|---|---|
| chapter | `create chapter@chapter` | **APPLIED** | the selected edition's token; the owner's contract is `{title}` |
| plan | `create plan-section@section` | **APPLIED** | an initialised plan, and `op.{section,title}` -- `project_structure` refuses `payload.op requires section` and then `requires title` |
| claim | `create concept-node@claim` | **APPLIED** | `node`, `node_kind` from the owner's 13-value enum, `essence` |
| paragraph | `create block@paragraph` | **APPLIED** | a `clip` and a `destination` carrying the file RELATIVE TO THE MANUSCRIPT DIR, the line and that file's current digest (`src/laplace/manuscript_blocks.py:172-177`) |
| section | `create section@section` | **refused**, and pinned below | `kind` from the owner's enum, a `source_file`, `after_line` with `after_before` (`src/laplace/manuscript_structure.py:907-930`) -- and one thing no payload can supply |

**The fifth is pinned to one owner line, not attributed to a guess.** `create section@section` is
refused `projection plan changed; refresh before changing the section` from
`src/laplace/manuscript_structure.py:369`. The cause is `_check_plan_guard` at
`src/laplace/manuscript_structure.py:364-366`, which builds `accepted` out of the owner's own
publications and compares the supplied guard RAW (`supplied not in accepted`). Those publications
carry the `sha256:` prefix and the grammar's token normalises it away (GRAMMAR.md section 1), so the
digests are equal and the strings are not. The demo pins it by running the same call by its old name
with the owner's own spelling, and recording both values side by side: owner publishes
`sha256:da0f3498...`, token publishes `rev:plan-file:verb-door-demo:da0f3498...`, and
`section_change` **APPLIES** (`demo.json`, key `pin`). So this is not the dispatch, not the payload
schema and not a missing prerequisite: it is residual 3, demonstrated on a live owner instead of
counted on nine corpus rows. The smallest change that closes it is that comparison going through
`revision_identity.revision_matches`, the function five other owners already use (section 8,
decision 4) -- and this lane does not make it, because re-spelling a raw-compared guard can turn a
recorded refusal into an apply.

One more thing the run makes visible, and it is residual 8 in the concrete: the two owners of the
content tree want the same file under two conventions -- `manuscript_blocks._path` resolves
`manuscript / file` (`src/laplace/manuscript_blocks.py:22-25`) while `section_change`'s `_source_path`
accepts either spelling (`src/laplace/manuscript_structure.py:295`). One concept, two spellings of its
own target. That is the contract lane's to reconcile; the dispatch cannot, because the route declares
selectors and guards and no payload keys.

**The editor's rewrite door and `apply_revision` are one concept with one span guard.**
`change prose@paragraph` is the only `(verb, concept)` pair for either, its guard list is exactly
`[(before, prose, text)]`, and the request carries the span text as content
(`payload.before_content`) beside the `prose` token
(`::test_the_editor_rewrite_and_apply_revision_are_one_concept_with_one_span_guard`). The turn-bound
consulted-read machinery stays where it was and is not extended: `execute` captures and refreshes
turn read baselines for the same operations as before, with `apply_revision` and
`proposal_supersede` still excluded from the capture (`src/laplace/writing_tools.py:968-956`). A
request driven on a path with no turn reproduces the owner's own refusal, in the owner's own house:
`apply_revision requires the current project turn.` from `src/laplace/writing_tools.py:227`
(`altitude-dispatch/verb-door/demo.json`, the `said` and `raised` fields of that record). This
report's first version cited `:224` for that line and the deposit did not contain the sentence at
all; the line is 227 in this branch AND at `706a8204`, and the sentence is now in the file.

## 4. The shims: @@OLDNAMES@@ old names, @@ROUTES@@ routes, every one with an expiry

`altitude-dispatch/shims.csv` is the list -- old operation, old sub-verb, verb, concept, every old
guard mapped to its home, expiry. They are not a table of strings: `SHIMS` is built by handing every
route to `grammar.Shim`, whose `__post_init__` is the gate GRAMMAR.md section 6 rule 2 demands. It
refuses an empty expiry, an expiry with no YYYY-MM-DD date, an expiry that does not name parity, a
verb outside the nine, a concept whose object is not a home kind, and a guard mapped to anything
that is not a home kind. **The module cannot import unless all @@ROUTES@@ routes are legal by the
grammar's own rules**, and `::test_every_old_name_is_a_shim_and_every_shim_carries_an_expiry`
asserts the @@OLDNAMES@@ names and both expiry properties besides.

A shim rewrites and never implements. There is one code path: the old name and the verb door both
end at the same branch of `writing_tools._execute`.
"""


TAIL = """
## 9. Findings the other lanes need, each with its repro

**1. GRAMMAR.md section 8's INSTALL is incomplete, and its expected count is stale.** The install
block copies `map_verbs.py`, `mapping.csv`, `GRAMMAR.md` and `obtain_census.py` into
`tests/grammar_spec/` but not `grammar.py`, and one proof reads it from there:
`tests/test_grammar.py::test_the_token_has_exactly_one_digest_form` fails with
`FileNotFoundError: .../tests/grammar_spec/grammar.py`. With that one file copied in as well the
suite is **42 passed**, not the 39 the section states (a real git worktree of `706a8204`,
`scripts/laplace-python -m pytest -q tests/test_grammar.py`). Every build lane hits this on its
first install.

**2. CLOSED. The installed `grammar.py` made `holder_census.py` fail for every build lane, and the
first of the two cures landed.** The census counts guard-shaped names from the text of the tree, and
`grammar.py` exports `digest_canonical_json` in `__all__` at `src/laplace/grammar.py:61` (the function
itself is at `:137`), so `identity_fields` went 229 -> 230 and the census exited 1 with
`NEW HOLDERS: 1` on four lanes that had added no name of their own. This report's first version named
two cures and said the choice was not mine; the instrument took the first one. `harness/holder_census.py`
now allows that one name under three named conditions -- it must be in `grammar.py`'s own `__all__`,
every site the counter found for it must be inside that statement, and the allowance is printed on
every run and carried in the JSON -- rather than by a blanket exclusion. Re-run at the final commit the
census prints `ALLOWED digest_canonical_json ... (an export of src/laplace/core/grammar.py, not a holder)`
and `NO NEW HOLDER`, and **exits 0** (`holder_census.out`). `identity_names.py --static` reads the same
230 against the base's 229 with the 16 payload-accepted names unchanged name for name. Nothing is owed
here any more; it is left in place because three sibling lanes were told the same thing.

**3. `grammar.Request`'s fixed field `target` collides with a real owner payload key, in SEVEN
sub-operations and not one.** `Request.__post_init__` refuses a payload key that restates a request
field, so any route whose owner declares a top-level `target` cannot express its own payload.
Enumerated from the owners' own contracts rather than asserted
(`by_and_target.json`, from `concepts_surface.operation_contract` and
`writing_contracts.exact_contract` in this tree): **`concept_change`** declares a top-level `target`
in `add_edge`, `add_node`, `move_node`, `remove_edge` and `retype_edge` -- 5 of its 13 sub-operations
-- and **`logical_plan_change`** in `add_obligation` and `connect`, 2 of its 6. The report's first
version named only `connect` at `src/laplace/writing_contracts.py:607`
(`if name=="connect":properties["target"]=_STRING`), which is where the plain-string one is written;
the other six come through the same `strings["target"]` table at
`src/laplace/writing_contracts.py:597` and through `concepts_surface`'s own contract. Measured on the
corpus: 2 recorded rows carry a top-level `target`, both `logical_plan_change`, and one of them
**applied** -- so the shape is live, not malformed. The dispatch carries it as `edge_target` and
restores the owner's spelling (`writing_verbs.FIELD_CARRIERS`), which works and is a second spelling
the grammar forced. The grammar packet should either rename its request field or declare the carrier
itself, so four lanes do not each invent one -- and the scope it has to cover is those seven.

**4. `grammar.parse` silently mis-parses a `sha256:`-prefixed token.** GRAMMAR.md section 1 says
`mint` and `parse` accept the owner's prefixed spelling and normalise it, "so no caller is refused
over a spelling". The digest is normalised; the **home id is corrupted**:

```
token:     rev:plan:proj:sha256:<64 hex>      (the owner's own spelling; project_structure.py:14-17
                                               publishes exactly this prefix)
parse ->   kind      plan
           home id   proj:sha256    <-- the prefix was eaten by the ID, not by the digest
           digest    <64 hex>       (normalised correctly)
```

Run it as `scripts/laplace-python -c` with `from laplace.core import grammar; t = grammar.parse(...)`.

`parse` splits the id lazily and the digest from the right, so `sha256` lands in the id. Nothing
refuses it, and a refusal built from such a token names a home that does not exist -- a misdirected
resolver, which is the defect `needed` exists to prevent. The repro is two lines; the fix is to
strip a `sha256:` prefix from the digest segment before splitting, or to refuse the prefixed token
form outright and say so.

**5. Three owner citations I generated were wrong, and the test that caught them is worth keeping.**
A substring search for `if operation == "<name>"` attributes an owner to any line that mentions the
operation. It gave `concept_change` the owner `document_style.status` at
`src/laplace/writing_tools.py:324` (the `if operation in {...}` line that forbids a review-mode
write), `store_artifact` a line inside the response compactor, and `concept` a line inside the read
post-processing. The generator now takes a single-operation branch first, the surface route table
second, and a membership test last, and
`::test_every_cited_owner_site_still_names_its_operation` asserts the cited line is still a handler.
Any lane that cites `writing_tools.py` line numbers should run the same check.

**6. `by` is DECLARED at some doors and fatal at others, so the grammar's fixed `by` field is not
yet usable at every altitude.** GRAMMAR.md section 3 makes `by` a request field precisely because a
note could not record its writer (140 notes from six writers read back under one name). The headline
holds; three statements under it did not, and here is what the owners' contracts actually say
(`by_and_target.json`, enumerated, not asserted):

* **`concept_change` declares `by` in all 13 of its sub-operations**, and `add_node`'s accepted
  properties are `axis, base_revision, by, essence, mutation_revision, node, node_kind, operation,
  parent, project, ref, rel, supersedes, target` -- fourteen keys. The first version of this finding
  said "no operation's contract declares it" and gave `add_node`'s input as
  `{operation, node, base_revision, value}`; `value` is not an accepted key of `add_node` at all. Both
  were wrong, and `concept_change` tolerating `by` on 36 recorded failure rows was the clue I did not
  follow.
* **`logical_plan_change` declares `by` in all 6 of its variants** --
  `allowed=list(dict.fromkeys(allowed+["by"]))` at `src/laplace/writing_contracts.py:604`.
* **`structure_change` declares it in none of its 5**, and refuses it outright at
  `src/laplace/project_structure.py:710` (`raise ValueError(f"{label} contains unknown keys: ...")`).
  Measured through the verb door and deposited verbatim this time: the demo's request "change the plan
  carrying by=eigen" is answered `structure_change payload contains unknown keys: by`, raised at
  `src/laplace/project_structure.py:710` (`verb-door/demo.json`, the `said` and `raised` fields of that
  record). The first version cited this sentence to `verb-door/demo.out`, which did not contain it --
  that demo's `structure_change` call carried `by: ""`, which the dispatch drops. The claim was true
  and the citation was not, which is the same defect as a stale line number.

So `by` is legal at 19 of the sub-operations this report measured and fatal at 5, with nothing in the
grammar telling a caller which. The dispatch passes `by` through unchanged (that is what reproduces the
recorded rows) and records the writer in the banked row regardless, so the attribution is never lost
even where the owner will not take it -- the demo's refused request still banks
`{"verb": "create", "concept": "plan-section@section", "altitude": "section", ...}`. The contract lane
should put `by` in the generated contract for every operation, or the grammar should say which doors it
is legal at; and `structure_change` is the door to start with.

**7. The banked write row keeps no payload, so the system's own record of a write cannot be
replayed.** The read row banks `payload` (`src/laplace/writing_tools.py:974-971`); the action row
banks only `outcome` (`:1000-1006`). The consequence is visible in the oracle's own corpus: **all @@WTOTAL@@ rows of `writes.jsonl` have
an empty payload**, so in the gate run @@WREFUSED@@ of them refuse on the empty payload and
@@WAPPLIED@@ apply something that needs no payload at all (counted from the banked
`parity-dial-off/rows.jsonl`) -- not one replays the write it recorded. That is worth the harness
lane's attention (its `writes` source measures less than its row count suggests) and the author's (a
write is not reconstructible from its own receipt). I did not add the payload to that row: it would
change bytes in `contract/talk.jsonl` on turn rows and it is the contract lane's call how much of a
payload a receipt should keep.

### One more decision, and it is a confession

The verb door's refusal carries a `kind` from GRAMMAR.md section 5's four-value taxonomy, and the
dispatch picks it **from the owner's sentence**, because no owner publishes a typed error: "the only
typed field is `error_type`, which is `ValueError` for almost everything" (synthesis section 6). A
substring test over an error message is the very thing the friction report names at
`src/laplace/writing_tools.py:1263` (`:1151` at `706a8204`), so I am not going to pretend this is a
cure. What the dispatch
does guarantee is the part that does not need a taxonomy: the owner's own sentence is passed through
verbatim, the owner's file and line travel beside it, the frame that actually RAISED travels with it
(`writing_tools._owner_frames`, the same definition the oracle uses at `harness/_worker.py:50`), and
`needed` carries the current token of every home the ROUTE declares -- not only the homes the request
happened to name. That distinction is the whole of it: the first version of this resolver walked
`request.tokens()`, so the caller who most needs the read named, the one who holds no token yet, got
`needed {"expected": []}` beside the owner's bare field name. It is built by the comparison, so it is
on every caller path and not only the provider's (`writing_verbs.account`, `writing_verbs.resolver`),
and `Refusal.homes` now carries, per home, the token AND the read it comes from -- or, for the 18 home
kinds no wired read reaches, what would close them. `state-not-reached` is never produced by this lane; the typed
error belongs to the generated-contract lane, which owns the shape the owners should raise.

## 10. Residuals, and what each would take

1. **CLOSED: the configuration that ships has now been through the whole oracle.** The first
   version of this report gated the lane at the legacy bank grain
   (`LAPLACE_WRITING_BANK_EVERY_PATH=0`) and proposed to close the question with the merge -- which
   would have closed it by making it permanently unmeasurable, because after the merge there is no
   non-banking side left to compare against. The number was taken instead, before the merge, on the
   whole corpus at the dial's default: `class` 0, `home` 0, `homes` on 49 rows, `bytes` in 2 paths,
   all 49 in the `arrival` source, every one of them checked against four conditions before it was
   allowed (section 5). The gate exits 0 on the tree that ships. What is left is not a residual but a
   trigger: at the merge both sides bank, `allow.bank-on.json`'s 49 entries describe nothing, and the
   dial and that file retire together.
2. **The arrival is unchanged, not improved.** `E2`, `E4` and `F4` are my lane's named targets and
   curing them is a behaviour change: `apply_revision` refuses outside a turn at
   `src/laplace/writing_tools.py:227`, and 57 recorded `apply_revision` refusals would change
   class
   if that gate moved. What it would take: an allowance scoped to those 57 rows plus a replay that
   shows nothing else moved, which is a pass of its own.
3. **@@INEXACT@@ corpus rows fall through** -- and residual 10 below is the same defect caught on
   a live owner, with the command that pins it -- because their guard is compared raw at
   `manuscript_structure` and `writing_stages` while five other owners compare through
   `revision_identity.revision_matches`. The real cure is one owner change -- those two doors
   comparing through the same function -- and it is not this lane's to make.
4. **@@SHIMROUTES@@ routes are reachable only through their old name**, which is exactly the count
   the retirement ledger reports HELD-UNREACHABLE (section 5) (and @@SHIMONLY@@ of the
   559 replayed rows travel through one). Each says why in
   `Route.because`: two or more old operations share one `(verb, concept)` and nothing in the payload
   chooses between them (for example `read reference@evidence` is `reference`,
   `literature_lookup` and `reference_source` -- three operations, one act, three projections nobody
   named). Closing them needs a payload key the owners do not share yet, which is the contract lane's
   work; the verb door still reaches all 104 pairs through the canonical route of each.
5. **Half the counter form is unexercised.** No row of the recorded corpus guards
   `authoring-state`, so the branch that hands the owner its own integer when the token matches
   `authoring.json` has no test and no replay behind it;
   `::test_the_counter_home_hands_the_owner_a_value_it_can_compare` covers only the other branch, the
   one that hands the owner the token so it refuses at
   `src/laplace/pipeline/authoring.py:398-399`. A `framing` or `argument` write inside a turn would
   exercise the first, and the harness lane should know the corpus does not.
6. **`concept`, `logical_plan` and `source` carry no owner citation** (3 operations of
   @@OLDNAMES@@): their row in
   the surface route table spans two lines, or their handler returns through a conditional the
   generator does not follow. The remaining 143 are asserted by test.
7. **The refusal's `kind` is inferred from the owner's sentence**, not read from a typed field, and
   `state-not-reached` is never produced. The cure is an owner-side typed error and belongs to the
   contract lane; see the confession above section 10.
8. **The 65 concepts' payload schemas are not written here**, and by the grammar packet's own
   division they are not mine: GRAMMAR.md section 9 assigns them to the contract lane, from
   `mapping.csv`. What this lane declares per concept is the part the dispatch needs to route --
   which selector pairs name the act, which guards exist with their home and form, and which owner
   call the pair reaches -- so "specialisation lives only in the concept's payload schema" is
   *enforced* here (a payload may not restate a request field or speak a guard name) and *stated*
   there. A caller today still learns a concept's payload keys from the old operation's `help`.
9. **The verb door has no HTTP route of its own, and no production caller.** It is callable from
   Python and it is now EXERCISED under replay -- 412 recorded rows entered through it and agreed with
   their old spelling on all four parity kinds (section 5) -- but every existing caller in the tree
   still arrives by operation name: the provider adapter at `src/laplace/writing_provider.py:611` and
   the HTTP server both call `execute`, which is why the dispatch had to sit inside `execute` for the
   banked row to be universal. Giving the verb door its own HTTP route belongs with the contract
   lane's generated schema, so a caller sees one vocabulary at both doors. Until then the door's
   evidence is the both-ways replay, the 4-of-5 applied demo and the 22 unit proofs, not a caller.
10. **One altitude of section 3 cannot apply through the verb door**, and the cause is one owner line:
   `_check_plan_guard` at `src/laplace/manuscript_structure.py:364-366` compares the supplied guard
   RAW against its own `sha256:`-prefixed publication, while the grammar's token normalises the
   prefix. Pinned on a live owner in section 3 (the same call applies with the owner's own spelling).
   It is residual 3 with a demonstration instead of a count; the cure is that comparison going
   through `revision_identity.revision_matches`, and it is an owner change, not a dispatch change.
"""
