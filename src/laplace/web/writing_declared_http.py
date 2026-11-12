"""The HTTP door's own preconditions, declared the same way as the tool door's.

The friction report counted the editor's door as a *separate* contract surface and
found that nothing publishes its preconditions at all.  Two of them cost the
scripted arrival two of its seven refusals:

* `A1-create-no-header` --- every mutating route under `/authoring/`,
  `/research/`, `/references/`, `/formal/`, `/projects/`, `/work/`, `/concepts/`
  and `/visuals/` requires the request header `X-Laplace-Writing: 1`, checked at
  `src/laplace/scanner.py:2185` and refused at `src/laplace/scanner.py:2186` with
  "Missing writing-client header."  No contract, catalogue or help response
  mentions it, so the only way to learn it is to be refused by it.
* `K2-turn-no-message` --- `POST /authoring/turn` reads the author's message from
  the field `text` (`writing/turn_admission.py` `prepare_request`) and refuses "Write a
  message first." there when neither `text`
  nor `queued_work_ids` is present.  The arrival sent `message`, which is what a
  reader guesses, and paid a refusal for a field name nothing declares.

Both are now rules of a declaration, reachable through `help {door: "http"}` and
`help {route: "/authoring/turn"}`, generated from the same `Rule` type the tool
door uses, and the route names the line that enforces each one.

Scope, stated: these are the four routes the recorded corpus actually replays
(`harness/corpus/arrival.jsonl`: 8 replayable HTTP rows over `/projects/create`,
`/review/adjudicate`, `/authoring/providers` and `/authoring/turn`), plus the
door-wide header rule that covers all eight POST prefixes.

THAT RESIDUAL IS CLOSED (WRITING-CONSOLIDATION-W1).  The sentence above used to end
"the editor's save and compile routes and the walk are not declared here and are
named as a residual".  The editor's five doors --- `/authoring/section-change`,
`/authoring/block-change`, `/authoring/structural-undo`, `/authoring/apply`,
`/authoring/proposal-decision` --- and the comment act of `/review/adjudicate` are
declared below, each with the `expected` field every one of them now takes and each
rule naming the line that enforces it.  Scope now stated positively: eleven rows of
one table (`tools/writing_verbs/http_routes.csv`), which is every mutating editor
door the walk and the workspace post to, plus the two reads beside them.  The delivery
gate's required reads and build path are declared below as well.  This does not claim the
whole projection surface: only routes with current consumers in the gate are included,
and the derived interface view says which exact consumers those are.
"""
from __future__ import annotations

from laplace.core import identity_doors
from laplace.manuscript import project_structure
from laplace.writing.schemas import SCHEMAS
from laplace.writing import sealed_reader as _sealed_reader
from laplace.manuscript.build_targets import target_schema as _build_target_schema
from laplace.manuscript.build_jobs import request_schema as _build_request_schema
from laplace.manuscript.review_surface import rewrite_retry_contract
from laplace.manuscript.proposal_navigation import http_contract as _proposal_http_contract
from laplace.native.declarations import Rule, anchored_site, declare, help_http_contract
from laplace.manuscript.profiles import http_contract as _profile_http_contract

_STRING = {"type": "string"}
_INT = {"type": "integer"}
_HEADER = "X-Laplace-Writing: 1"
_HEADER_DOOR = "src/laplace/scanner.py:2185"

#: The identity field, from the one place that defines it.  Every editor door below takes it
#: and not one of them declares a guard name of its own, so the twenty-name census the
#: friction report took cannot grow by this packet: `identity_doors.EXPECTED_FIELD` is the
#: whole schema and `identity_doors.DOORS` is the whole list of old names still answered to.
_EXPECTED = identity_doors.EXPECTED_FIELD

#: The one sentence that says what `expected` buys, written ONCE.  `help structure_change`
#: renders a repeated field eleven times (`identity_doors.py:271`'s own measurement), so a
#: per-door paragraph here would be the contract-prose defect at the width of six doors.
_RESOLVER = "a stale token is refused with refused.needed; retry {**request, **needed}"

#: EVERY COORDINATE THIS LANE TYPES IS AN ANCHOR INSTEAD (WRITING-CONSOLIDATION-W1).
#:
#: `Rule.door` is a typed `file:line` and `writing_declarations`' own docstring measures what
#: that costs: 64 of 93 coordinates in this tree name a line that holds other code, because
#: every lane moves lines.  Resolving a door by its own source TEXT is residual 4 there, and
#: residual 4 is deferred because it would need the base text at render time for the 186 rules
#: that already exist.  It needs nothing at all for a rule written NOW, in the tree it ships
#: in: `anchored_site` is the same resolver `handler_anchor` already uses, it refuses an
#: ambiguous or missing anchor instead of guessing, and the one coordinate it cannot produce is
#: a wrong one.  Measured while writing this packet: the editor's ten coordinates drifted FOUR
#: TIMES in one afternoon's edits to their own owners, and each drift was a silently wrong
#: citation until the sweep caught it.
#:
#: So the editor's rules name their line by the line, and residual 4 shrinks by exactly these
#: ten rather than being restated.
def _at(rel: str, anchor: str) -> str:
    return anchored_site(rel, anchor)


_RV = "src/laplace/manuscript/review_surface.py"
_MB = "src/laplace/manuscript/blocks.py"
_AS = "src/laplace/web/authoring.py"
_SR = "src/laplace/writing/session_reads.py"
_TE = "src/laplace/writing/turn_execution.py"   # live turn execution (S1 B2)
_TC = "src/laplace/writing/turn_control.py"     # steering and interruption (S1 B2)
_SA = "src/laplace/manuscript/source_application.py"  # the source application transaction (S1 B3)
_AH = "src/laplace/web/authoring_http.py"     # the /authoring/* HTTP door (S1 B4)
_TA = "src/laplace/writing/turn_admission.py"     # turn request shape and admission (S1 B1)
_MP = "src/laplace/manuscript/manuscript_proposals.py"
_PA = "src/laplace/pipeline/authoring.py"


def _object(required=(), properties=None, *, additional=True):
    return {"type": "object", "required": list(required),
            "properties": properties or {}, "additionalProperties": additional}


def _structure_change_input():
    """The HTTP body from the owner's operation contract, without a copied variant list."""
    from laplace.manuscript.project_structure import operation_contract
    contract = operation_contract()
    variants = []
    for name, schema in contract["operations"].items():
        variants.append({"type": "object", "required": ["project", *schema["required"]],
                         "properties": schema["properties"],
                         "additionalProperties": False, "title": name,
                         **{key:schema[key] for key in ("oneOf","allOf") if key in schema}})
    return {"type": "object", "oneOf": variants,
            "required": ["project", "operation"]}


declare(
    "http-door",
    door="http",
    route="*",
    payload=_object(),
    does="Every mutating HTTP route under the eight writing prefixes.",
    header=_HEADER,
    header_door=_HEADER_DOOR,
    # ONE line for the door-wide row, and it is the one that DECIDES: the header check at
    # _HEADER_DOOR.  The prefix test three lines above it was the other candidate --- it is
    # what the route table's `holds` column used to name --- but it occurs TWICE in
    # scanner.py (:1485 in the GET path, :2182 in do_POST), so it cannot be an anchor at all:
    # `anchored_site` refuses a text that matches more than one line, which is how this was
    # found.  The table's row now names the same line, so the declaration and the table agree
    # (tests/test_one_table.py::test_the_http_door_is_in_the_same_table).
    handler_anchor="src/laplace/web/scanner.py:if self.headers.get(\"X-Laplace-Writing\") != \"1\":",
    rules=(
        Rule("header", field="X-Laplace-Writing", door=_HEADER_DOOR,
             says="POST under /authoring/ /research/ /references/ /formal/ /projects/ "
                  "/work/ /concepts/ /visuals/ sends this header"),
        Rule("scope", field="Content-Length", door="src/laplace/scanner.py:2189",
             says="JSON bodies over 2 MiB are refused 413. Only POST /projects/material-intake/upload admits raw PDF up to 16000000 bytes or UTF-8 text up to2000000, with one finite Content-Length, no Transfer-Encoding and closed matching media metadata."),
        Rule("scope", door="src/laplace/scanner.py:2186",
             says="a missing header is 403 'Missing writing-client header.', not 401 and "
                  "not an owner refusal"),
    ),
)

declare(
    "projects/create",
    door="http",
    route="/projects/create",
    payload=_object(("name", "title"),
                    {"name": _STRING, "title": _STRING,
                     "kind": {"enum": ["general", "software", "development", "company", "transcript", "campaign", "book", "paper"], "default": "general"},
                     "purpose": _STRING, "audience": _STRING, "question": _STRING}),
    does="Create a source-optional project registry/framing, or an explicit book/paper manuscript.",
    header=_HEADER,
    header_door=_HEADER_DOOR,
    # The ROUTE line, not the function it calls.  `def create(...)` at :217 is where the work
    # happens; `:363` is where `/projects/create` is recognised, which is what the route table
    # names and what the other four HTTP declarations name for themselves.  One answer per
    # question: the handler is the line that routes.
    handler_anchor=("src/laplace/projects/library.py:if path in {\"/projects/create\", "
                    "\"/projects/import\", \"/projects/start\"}:"),
    effects=("registry row", "manuscript source", "authoring framing"),
    rules=(
        Rule("shape", field="name", door="src/laplace/writing_projects.py:227",
             says="name is a slug; a name that is not matches nothing and is refused 422"),
        Rule("enum", field="kind", values=("general", "software", "development", "company", "transcript", "campaign", "book", "paper"),
             door="src/laplace/writing_projects.py:228",
             says="title is required; omitted kind defaults to general with no fabricated manuscript"),
    ),
)

declare(
    "review/adjudicate",
    derived={"source_effect_protocol":"laplace.manuscript.source_effects:protocol"},
    door="http",
    route="/review/adjudicate",
    payload=_object(("corpus", "verb", "file", "line_start", "line_end", "before", "by"),
                    {"corpus": _STRING, "verb": _STRING, "file": _STRING,
                     "line_start": {"type": "integer"}, "line_end": {"type": "integer"},
                     "before": _STRING, "after": _STRING, "by": _STRING,
                     "note": _STRING, "surface": _STRING, "dir": _STRING,
                     "expected": _EXPECTED,
                     # the grammar's uniform spelling of the TEXT guard, and the key this
                     # door's own refusal serves the current span under, so a retry is
                     # literally `{**request, **refused.needed}`
                     "before_content": _STRING,
                     "passage_before": _STRING, "passage_after": _STRING,
                     "rewrite_retry": rewrite_retry_contract()}),
    does="Adjudicate one addressed span of the manuscript through the editor's door.",
    header=_HEADER,
    header_door=_HEADER_DOOR,
    handler_anchor="src/laplace/web/review_http.py:if path == \"/review/adjudicate\" and method == \"POST\":",
    effects=("adjudication row", "source rewrite for a splice verb"),
    outputs=("exact record/receipt and source effect acknowledgement", "receipt.rewrite_retry on a new pending row",
             "receipt.retry_settlement links exact pending/applied IDs after swap; retry_warning preserves applied ACK on unresolved status"),
    rules=(
        Rule("identity", field="before", home="prose",
             door="src/laplace/review_surface.py:1860",
             says="before is the prose home's exact current span text, whole lines"),
        Rule("shape", field="corpus", door="src/laplace/review_surface.py:3495",
             says="an unknown corpus or dir is 404 before the verb is looked at"),
        Rule("enum", field="verb", door="src/laplace/review_surface.py:1253",
             values=("confirm", "defer", "dismiss", "widen", "revoke", "route-conceptric",
                     "route-plan", "calibrate", "revoke-intent", "edit-in-place", "comment",
                     "rewrite", "scope"),
             says="the door accepts thirteen verbs; the executor docstring at :1394 lists "
                  "eight and is stale by five"),
        Rule("scope", door="src/laplace/review_surface.py:1876",
             says="a banked pending row returns ok with applied null; that is 'banked', "
                  "not 'applied'"),
        Rule("identity", field="expected", home="prose",
             door=_at(_RV, '"apply_revision", supplied={**payload, "before": before}'),
             says=_RESOLVER),
        Rule("scope", field="passage_before",
             door=_at(_RV, "if current is not None and stale is None and before != current:"),
             says="a current token with different text re-splices your own passage into the "
                  "CURRENT bytes; a passage not found exactly once writes nothing"),
    ),
)

# ---------------------------------------------------------------------------
# THE EDITOR'S OWN DOORS (WRITING-CONSOLIDATION-W1).  Six declarations, one per row of
# the table, each naming the line that enforces each rule.  Not one of them declares a
# guard NAME: `expected` is the identity field everywhere (`identity_doors.EXPECTED_FIELD`),
# so the editor's doors are now gated without adding a twenty-first name to the census.
# ---------------------------------------------------------------------------
declare(
    "review/adjudicate-comment",
    door="http",
    route="/review/adjudicate",
    payload=_object(("corpus", "verb", "by"),
                    # two spellings of one act: the executor's own adjudication verb, and the
                    # grammar's `create` beside a `concept` (the shim restores the first from
                    # the second at `review_http._owner_adjudication`)
                    {"corpus": _STRING, "verb": {"enum": ["comment", "create"]}, "by": _STRING,
                     "concept": {"enum": ["note@paragraph", "note@section", "note@chapter"]},
                     "comment": _STRING, "mark_only": {"type": "boolean"},
                     "section": _STRING, "paragraph": _STRING, "quote": _STRING,
                     "spec_ids": {"type":"array","items":_STRING,"minItems":1,"maxItems":32,"uniqueItems":True},
                     "source_section": _STRING,
                     "file": _STRING, "line_start": _INT, "line_end": _INT,
                     "block": _STRING, "figure": _STRING, "page": _INT,
                     "region": {"type": "object"}, "span": {"type": "object"},
                     "altitude": {"enum": ["paragraph", "section", "chapter"]},
                     "disposition": {"enum": ["keep", "cut", "rework"]},
                     "scope": _STRING, "scope_source": _STRING, "suggested_scope": _STRING,
                     "context_before": _STRING, "context_after": _STRING,
                     "expected": _EXPECTED, "dir": _STRING}),
    does="Bank one author comment on a passage, with its keep/cut/rework ruling.",
    header=_HEADER,
    header_door=_HEADER_DOOR,
    handler_anchor="src/laplace/manuscript/review_surface.py:if verb == \"comment\":",
    effects=("feedback row", "walk deposit badge", "session context instruction"),
    outputs=("record", "grade", "refused"),
    rules=(
        Rule("enum", field="disposition", values=("keep", "cut", "rework"),
             door=_at(_RV, "def _ruling_fields(payload: dict)"),
             says="the ruling is a payload key of this concept and never a verb of its own; "
                  "absent means a comment that leaves the passage's fate open"),
        Rule("enum", field="altitude", values=("paragraph", "section", "chapter"),
             door=_at(_RV, "def _comment_altitude(payload: dict, supplied: dict) -> str:"),
             says="absent is derived from what the gesture addressed (a file and a line span "
                  "is paragraph, a section alone is section) and the row records which"),
        # One rule per altitude, because one rule per HOME is the whole point: a reader is
        # told which home its altitude proves and which read serves the token, and the three
        # are not interchangeable.
        Rule("identity", field="expected", home="prose",
             read="GET /review/fragment -> identities, or GET /walk/doc?identities=1 -> "
                  "sections[].blocks[].expected",
             door=_at(_RV, '"comment@" + altitude, supplied=payload'),
             says="altitude paragraph proves the addressed span. " + _RESOLVER),
        Rule("identity", field="expected", home="section",
             read="GET /review/fragment -> identities",
             door=_at(_RV, '"comment@" + altitude, supplied=payload'),
             says="altitude section proves the section's source file. " + _RESOLVER),
        Rule("identity", field="expected", home="chapter",
             read="GET /review/fragment -> identities",
             door=_at(_RV, '"comment@" + altitude, supplied=payload'),
             says="altitude chapter proves the chapter file. " + _RESOLVER),
        Rule("scope", field="expected", door=_at(_RV, 'if container is None and payload.get("expected"):'),
             says="a whole-paper or span deposit has no one container, so a token sent with "
                  "one is refused unknown-home rather than ignored"),
        Rule("scope", door=_at(_RV, "prov_fields.update(ruling)"),
             says="the ruling is banked on the anchor of the existing comment row kind; no "
                  "row kind and no top-level stored key is added"),
        Rule("scope", door=_at(_PA, "ruling = {key: anchor[key] for key in"),
             says="the ruling reaches a session through author_history {view: corrections}, "
                  "the note home's own declared read, and is rendered in the prompt line"),
    ),
)

declare(
    "authoring/section-change",
    derived={"source_effect_protocol":"laplace.manuscript.source_effects:protocol"},
    door="http",
    route="/authoring/section-change",
    payload={"type": "object", "required": ["project", "operation"],
             "properties": {"project": _STRING, **SCHEMAS["section_change"]["properties"],
                 "expected": _EXPECTED},
             "allOf": SCHEMAS["section_change"]["allOf"],
             "additionalProperties": False},
    does="Create a new heading, convert a whole prose paragraph to a new heading, undo, delete or restore. Existing heading titles use guarded source revision.",
    header=_HEADER,
    header_door=_HEADER_DOOR,
    handler_anchor=(_AH + ":elif method == \"POST\" and path == "
                    "\"/authoring/section-change\":"),
    effects=("source edit", "plan projection", "author correction record"),
    outputs=("undo", "edits", "receipt", "correction_id"),
    rules=(
        Rule("identity", field="expected", home="plan",
             read="GET /work/structure -> revision",
             door=anchored_site("src/laplace/manuscript/manuscript_structure.py",
                                '"section_change plan", supplied={**payload, "expected_plan_revision": supplied},'),
             says="plan or plan-file is accepted and the refusal serves both. " + _RESOLVER),
        Rule("scope", field="undo", door=_at("src/laplace/manuscript/manuscript_structure.py", '"project":project, "operation":operation, "undo":result["undo"]}, root=root)'),
             says="every accepted change returns its exact inverse in `undo`; a reply with "
                  "no `undo` is not a reversible change and the editor refuses it"),
    ),
)

declare(
    "authoring/block-change",
    derived={"source_effect_protocol":"laplace.manuscript.source_effects:protocol"},
    door="http",
    route="/authoring/block-change",
    payload=_object(("project", "operation"),
                    {"project": _STRING, "operation": _STRING,
                     "edits": {"type": "array", "items": {"type": "object"}},
                     "placement": {"type": "object"}, "clip": {"type": "object"},
                     "destination": {"type": "object"}, "block": {"type": "object"},
                     "expected": _EXPECTED}),
    does="Move, insert, delete or undo one addressed object in the source.",
    header=_HEADER,
    header_door=_HEADER_DOOR,
    handler_anchor=(_AH + ":elif method == \"POST\" and path == "
                    "\"/authoring/block-change\":"),
    effects=("source edit", "object placement"),
    outputs=("edits", "placement", "refused"),
    rules=(
        Rule("identity", field="expected", home="source-file",
             door=_at(_MB, '"block_change undo", supplied={**payload, **edit}'), says=_RESOLVER),
        Rule("identity", field="after", home="source-file",
             door=_at(_MB, '"block_change undo", supplied={**payload, **edit}'),
             says="an undo's guard is the file's exact TEXT, so the refusal serves the "
                  "current bytes as before_content; no token reconstructs text"),
        Rule("identity", field="expected_source_digest", home="source-file",
             door="src/laplace/manuscript_blocks.py:176",
             says="an insert addresses its destination by the file's current digest and the "
                  "line it goes after; both are required and both are compared"),
    ),
)

declare(
    "authoring/structural-undo",
    door="http",
    route="/authoring/structural-undo",
    payload=_object(("project", "kind", "id"), {"project":{"type":"string", "minLength":1},
        "kind":{"enum":["block", "section"]}, "id":{"type":"string", "minLength":1, "maxLength":300}}),
    does="Read the exact inverse of one banked block or heading change.",
    handler_anchor=(_AH + ":elif method == \"GET\" and path == "
                    "\"/authoring/structural-undo\":"),
    outputs=("undo",),
    rules=(
        Rule("enum", field="kind", values=("block", "section"),
             door=_at("src/laplace/work/history.py", 'if isinstance(payload, Mapping) and payload.get("kind") not in ("block", "section"):'),
             says="kind and id are query parameters; any other kind is refused before a "
                  "record is looked up"),
        Rule("scope", door="src/laplace/scanner.py:2182",
             says="a GET needs no writing-client header, and this route writes nothing: it "
                  "serves the saved inverse the editor then POSTs back"),
    ),
)

declare(
    "authoring/apply",
    derived={"source_effect_protocol":"laplace.manuscript.source_effects:protocol"},
    door="http",
    route="/authoring/apply",
    payload=_object(("turn_id",),
                    {"turn_id": _STRING, "project": _STRING, "expected": _EXPECTED}),
    does="Apply one saved proposal's source edits to the manuscript.",
    header=_HEADER,
    header_door=_HEADER_DOOR,
    handler_anchor=(_AH + ":elif method == \"POST\" and path == "
                    "\"/authoring/apply\":"),
    effects=("source edits", "application record", "turn context baseline"),
    outputs=("complete and application id only for recorded application",
             "source_effect_retained/source_applied and tracking UNPROVED with actual source receipts if parent recording fails",
             "warning: inspect exact receipts/current source; do not repeat an effect"),
    rules=(
        Rule("identity", field="expected", home="proposal",
             read="GET /authoring/proposals -> proposals[].identities "
                  "(" + _at("src/laplace/manuscript/proposal_navigation.py", "def handle(project,payload):") + ")",
             door=_at(_SA, '"apply_proposal", supplied=payload'), says=_RESOLVER),
    ),
)

declare(
    "authoring/proposal-decision",
    derived={"source_effect_protocol":"laplace.manuscript.source_effects:protocol"},
    door="http",
    route="/authoring/proposal-decision",
    payload=__import__('laplace.manuscript.reconciliation',fromlist=['decision_contract']).decision_contract(),
    does="Inspect, preview or apply an exact current-source revision; finish-resolution-record saves only the exact predecessor disposition of a completed application, without replaying source. Existing whole-edit decisions remain available.",
    header=_HEADER,
    header_door=_HEADER_DOOR,
    handler_anchor=(_AH + ":elif method == \"POST\" and path == "
                    "\"/authoring/proposal-decision\":"),
    effects=("proposal decision record", "source edit for an accept"),
    outputs=("decision", "application", "remaining",
             "reviewable false and source/tracking facts on incomplete application; no accepted decision or sibling advancement from an unrecorded object"),
    rules=(
        Rule("identity", field="expected", home="proposal",
             read="GET /authoring/proposal-preview -> identities "
                  "(" + _at(_MP, '"identities": _idd.identities(') + ", the same value its "
                  "proposal_version field carries, with its home on it)",
             door=_at(_MP, '"proposal_decision", supplied=payload'), says=_RESOLVER),
        Rule("enum", field="decision",
             values=("accept", "reject", "keep-current", "replace-current", "merge",
                     "supersede", "prepare-resolution", "preview-resolution", "apply-resolution", "apply-candidate", "finish-resolution-record"),
             door="src/laplace/manuscript_proposals.py:298",
             says="an unknown decision is refused before the turn is read"),
    ),
)

declare(
    "authoring/turn",
    door="http",
    route="/authoring/turn",
    payload={'oneOf':[_object(("project",),
                    {"project": _STRING, "text": _STRING, 'profile':{'not':{}},
                     "queued_work_ids": {"type": "array", "items": _STRING},
                     "session_id": _STRING,
                     "mode": {"enum": ["discuss", "revise", "work", "review"]},
                     "provider": _STRING, "model": _STRING, "effort": _STRING,
                     "request_id": _STRING, "selection": {"type": "object"},
                     "work_id": _STRING, "expected_work_scope_revision": _STRING,
                     "expected_dependency_revision": _STRING,
                     "connected_observation_seconds": {'type':'integer','minimum':1,'maximum':2147478},
                     "workspace_context": {"type": "object"}}), _sealed_reader.start_contract()]},
    does="Start one provider turn against this project and return its turn id.",
    header=_HEADER,
    header_door=_HEADER_DOOR,
    handler_anchor="src/laplace/writing/turn_admission.py:def start_turn(root: Path, payload: dict, *, dispatch: dict | None = None) -> dict:",
    effects=("durable turn", "provider job", "context receipt"),
    rules=(
        Rule("one-of", fields=("text", "queued_work_ids"),
             door=_at(_TA, 'raise ValueError("Write a message first.")'),
             says="the author's message is the field `text`, not `message`; or supply "
                  "queued_work_ids"),
        Rule("scope", field="text", door=_at(_TA, "if len(text) > 100_000:"),
             says="text over 100,000 characters is refused; attach the source to the "
                  "project and refer to it"),
        Rule("enum", field="mode", values=("discuss", "revise", "work", "review"),
             door=_at(_TA, "if mode not in MODES:"),
             says="an unknown mode is refused before the turn exists"),
        Rule("scope", field="request_id", door=_at(_TA, 'if old.get("request_id") == request["request_id"] and old.get("project") == request["project"]:'),
             says="the same request_id in the same project and mode returns the first "
                  "turn with reused true"),
        Rule("scope", field="work_id",
             says="An explicitly attached Work requires expected_work_scope_revision and "
                  "expected_dependency_revision from its inspected detail read. Missing or "
                  "changed observations refuse before session/provider effects and return "
                  "the exact Work next_reads. Legacy saved associations are not fresh observations."),
        Rule('scope', field='workspace_context',
             says='workflow_action accepts only its qualified reference and expected_basis. The continuation owner resolves it before session/provider effects; only the owner creates the retained exact snapshot. Replay of the same parent request compares the full submitted intent before resolving mutable context again.'),
    ),
)

declare(
    "authoring/providers",
    door="http",
    route="/authoring/providers",
    payload=_object(),
    does="List the providers a turn can start with, each model with its tier and the one "
         "session default; `model_choice` is the declaration, generated at read time.",
    # Model choice is ONE table.  This names its producer instead of restating it, so the
    # tool door's help, the HTTP response (`writing_provider.with_model_choice`) and the
    # composer's pane read the same declaration.
    derived={"model_choice": "laplace.pipeline.schema:model_choice_declaration"},
    # The anchor used to name the TURN route's own line --- the typed `:2619` this door had
    # before anchors, copied into the anchor instead of being replaced by it, so the one
    # citation `test_the_http_door_is_in_the_same_table` exists to catch was still wrong and
    # the table (`:2509`) and the declaration (`:2619`) disagreed on the merged tree.
    handler_anchor=_AH + ":elif method == \"GET\" and path == \"/authoring/providers\":",
    rules=(
        Rule("scope", door="src/laplace/scanner.py:2182",
             says="a GET needs no writing-client header; only the POST prefixes are gated"),
    ),
)


# ---------------------------------------------------------------------------
# REQUIRED DELIVERY-GATE READS AND BUILD PATH (WRITING-CONSOLIDATION-CODEX-CORRECTIONS).
# Their acts and methods come from the generated HTTP table.  Their response and consumer
# anchors are resolved at import and feed the repository interface projection; they are not
# a second dispatch table.
# ---------------------------------------------------------------------------
declare(
    "authoring/events",
    door="http", route="/authoring/events",
    payload=_object(("turn",), {"turn": _STRING, "after": _INT}, additional=False),
    does="Stream one active turn until its provider result is durably saved or fails.",
    handler_anchor="src/laplace/web/scanner.py:if u.path == \"/authoring/events\":",
    outputs=("delta|progress|usage are nonterminal", "complete is terminal after reply save",
             "error is terminal save failure"),
    errors=("404 text: stream expired; reload the saved session",),
    recoverable=("EventSource reconnects by cursor; a closed stream requires the saved session read",),
    rules=(Rule("state", field="type", says="delta, progress and usage never mean delivered; complete follows durable reply save"),),
    response_anchors={
        "complete-after-save": _TE + ':emit(launch, {"type": "complete", "result": result})',
        "terminal-error": _TE + ':emit(launch, {"type": "error", "message": message})',
        "expired-404": _AS + ':handler.send_error(404, "Turn stream expired; reload the saved session.")',
    },
    consumer_anchors={
        "event-source": "src/laplace/web/static_shared/workspace-session.mjs:const stream=new EventSource(endpoint.pathname+endpoint.search);",
        "event-state-machine": "src/laplace/web/static_shared/workspace-session.mjs:stream.onmessage=event=>{",
        "connection-failure": "src/laplace/web/static_shared/workspace-session.mjs:stream.onerror=()=>{",
    },
)

declare(
    "authoring/interrupt",
    door="http", route="/authoring/interrupt",
    payload=_object(("turn_id",), {"turn_id": _STRING}, additional=False),
    does="Request cancellation of one active provider turn without rolling back saved work.",
    header=_HEADER, header_door=_HEADER_DOOR,
    handler_anchor=_AH + ':elif method == "POST" and path in ("/authoring/interrupt", "/authoring/steer"):',
    outputs=("provider acknowledgement only; terminal state remains on the turn result",),
    errors=("409 JSON refused/error: the turn is absent, finished, or has no provider", "500 JSON error: provider interruption failed"),
    recoverable=("wait for events or reload the saved session; never resubmit the provider request",),
    rules=(Rule("state", field="status", says="interrupt requested is not interrupted; saved actions and partial public text are retained"),),
    response_anchors={
        "cancellation-requested": "src/laplace/writing/provider.py:self.cancelled.set()",
        "terminal-claude-result": "src/laplace/writing/provider.py:values = {\"status\": \"interrupted\" if self.cancelled.is_set() else",
    },
    consumer_anchors={"stop-control": "src/laplace/web/static_shared/workspace-session.mjs:this.find('[data-stop]').onclick=()=>this.guard(()=>this.stopSelectedTurn());"},
)

declare(
    "authoring/steer",
    door="http", route="/authoring/steer",
    payload=_object(("turn_id", "text"), {"turn_id": _STRING, "text": _STRING,
                    "selection": {"type": "object"},
                    "workspace_context": {"type": "object"},
                    "delivery_mode":{"type":"string","enum":["native_rpc","project_tool_boundary"]}}, additional=False),
    does="Send turn-bound input through observed native steering or retain it pending the same turn project-tool boundary; offer, exact read, and context delivery are distinct.",
    header=_HEADER, header_door=_HEADER_DOOR,
    handler_anchor=_AH + ':elif method == "POST" and path in ("/authoring/interrupt", "/authoring/steer"):',
    outputs=("native acknowledgement or durable PENDING control receipt with exact turn/sequence",),
    errors=("409 JSON refused/error: no active turn, empty text, wrong project, or unsupported provider", "500 JSON error: provider steering failed"),
    recoverable=("a refusal leaves the active turn unchanged; wait, stop, or send valid input once",),
    rules=(Rule("state", field="text", says="accepted steering is input to the active turn; it is not a completed reply or applied change"),),
    response_anchors={
        "native-steer": "src/laplace/writing/provider.py:return self.conn.request(\"turn/steer\", {\"threadId\": self.native_id,",
        "durable-steer": _TC + ':writing_records.bank(root,{"record":"writing-steer","id":"WST-"+uuid.uuid4().hex,',
    },
    consumer_anchors={"active-composer": "src/laplace/web/static_shared/workspace-session.mjs:const response=await projectRequest('/authoring/steer',"},
)

declare(
    "authoring/session",
    door="http", route="/authoring/session",
    payload=_object(("id",), {"id": _STRING, "before": _STRING,
                    "view": {"enum": ["full", "summary"]}, "limit": _INT}, additional=False),
    does="Read a bounded saved conversation and its active turn without replaying work.",
    handler_anchor=_AH + ':elif method == "GET" and path == "/authoring/session":',
    outputs=("session", "turns", "older_cursor", "active", "recovery",
             "view=summary turn rows are bounded under one text policy: request text, unsaved_draft.text, selection.quote and each steering text/quote/draft to 2000 characters; reply.display_text and proposal_answer to 4000; unsaved_draft.reason, reply.error and storage_errors messages to 500; every bounded field carries <field>_chars/<field>_truncated when cut; nested shapes are closed: selection carries only files/section_ids/node_id/node_ids/line_start/line_end, an owned anchor and the bounded quote; an anchor carries only file/repo_file/binding/line_start/line_end/lines/section/section_id/paragraph_id/block/node_id/sha256/schema_version/operation_id/grade/coarse exactly and none of its passage texts (quote/before/after/passage_before/passage_after stay in the exact record); unsaved_draft carries status/format, the same owned anchor and bounded text/reason; a storage error carries field/content_handle and a bounded message; no unknown key is copied at any level (the exact record behind body_read holds it); meters, identities and read handles are exact; reply.text and workspace_context are never carried; steering (5), undo_entries (10), storage_errors (5) and queued_work_ids (20) are capped before shaping with *_total/*_truncated; at most 3 result_links with result_links_total; every row carries packet/role of its session when present and body_read (session-turn view=turn) / summary_read (view=summary) handles to the exact originals"),
    errors=("409 JSON refused/error: unknown session, cursor or view", "500 JSON error: unexpected owner failure"),
    recoverable=("older_cursor continues the same immutable history cut", "recovery keeps saved actions and proposals without replay"),
    response_anchors={"saved-session": _SR + ':return {"session": session_view, "turns": page,'},
    consumer_anchors={
        "conversation-load": "src/laplace/web/static_shared/workspace-session.mjs:try{const data=await projectRequest('/authoring/session?id='",
        "turn-render": "src/laplace/web/static_shared/workspace-session.mjs:this.renderMessageTurns(data.turns,{before,activeId:data.active?.id})",
    },
)

declare(
    "authoring/session-turn",
    door="http", route="/authoring/session-turn",
    payload={'oneOf': [_object(("project", "id"), {"project": _STRING, "id": _STRING,
                    "view": {"enum": ["turn", "summary", "application", "actions", "failures", "controls"]},
                    "offset": _INT, "limit": _INT, "item_id": _STRING}, additional=False),
             _object(('project', 'session_id', 'request_id', 'view'), {'project': _STRING,
                     'session_id': _STRING, 'request_id': _STRING, 'view': {'const': 'request'}}, additional=False),
             _object(('project','request_id','manifest_id','view'),{'project':_STRING,'request_id':_STRING,
                     'manifest_id':_STRING,'view':{'const':'reader-request'}},additional=False),
             _object(('project','session_id','id','view','part'),{
                     'project':{'type':'string','minLength':1,'maxLength':160},
                     'session_id':{'type':'string','minLength':1,'maxLength':160},
                     'id':{'type':'string','minLength':1,'maxLength':160},
                     'view':{'const':'message'},'part':{'enum':['request','reply']},
                     'offset':{'type':'integer','minimum':0},
                     'limit':{'type':'integer','minimum':1,'maximum':40000},
                     'expected_basis':{'type':'string','minLength':71,'maxLength':71,'pattern':r'^sha256:[0-9a-f]{64}$'}},additional=False)]},
    does="Read one selected saved request/displayed-reply page, an exact saved turn, or bounded actions, failures and addressed control acknowledgements.",
    handler_anchor=_AH + ':elif method == "GET" and path == "/authoring/session-turn":',
    outputs=("turn or application", "items and pagination", "legacy detail views retain exact=true where supplied",
             "failures retain historical attempts: related_action is a compact original action identity/operation/target/read_handle with basis same_operation_target, never retry or task repair; resolved_later only reflects recovery_read.recovers_read_goal. Summary failure_count, read_recovery_count and related_action_count are distinct; legacy resolved_count/unresolved_count count attempts with/without exact read recovery, not tasks",
             "view=message: laplace.writing-message-part/1, fully qualified project/session/turn/part and source-row identity, presentation policy/origin, full-text content_sha256 and distinct basis; exact Unicode scalar-value character and UTF-8-byte extents; AVAILABLE content with complete/truncated, page_read/next_read and explicit current restart_read",
             "view=message without a saved reply: ABSENT/NO_SAVED_REPLY at that read, null content/basis and page/next; it does not imply provider completion or promote a proposal into a reply",
             "view=request is pure selected-action parent submission reconciliation scoped to project/session_id/request_id; effect NONE or RECORDED and exact receipt, never provider retry",
             "view=summary is the single-turn summary with complete request/steering text and up to 20 result_links, plus packet/role of the turn's session"),
    errors=("409 JSON refused/error: unknown turn, application, control or view",
            "409 view=message CHANGED_MESSAGE in message_refusal: exact target, expected/current basis and qualified restart_read; no changed content is delivered",
            "500 JSON error: unexpected owner failure"),
    recoverable=("pagination.next_offset continues actions, failures or controls; exact item_id recovers applications or controls",
                 "view=message page_read repeats the exact pinned page and next_read continues the same basis; restart_read explicitly selects current first-page content; a read failure never resends a turn"),
    rules=(Rule('shape',field='view',door=_at(_SR,'def public_message(root:Path, payload:dict) -> dict:'),
                says='view=message is closed to project/session_id/id/part and optional offset/limit/expected_basis. Identities are verified in the same logical session; default request/reply windows are 2000/4000 Unicode scalar-value characters and maximum 40000 is a delivery window, not a message completeness cap. Content, journal-row and custody-body hashes are distinct; only owner-issued expected_basis pins continuation.'),),
    response_anchors={
        "summary": _SR + ':return {"project":project,"turn":_session_turn_summary(source,records),"exact":True}',
        "controls": _SR + ':return {"view":view,"project":project,"turn_id":ident,"items":page,"exact":True,',
        "paged-detail": _SR + ':return {"project":project,"turn_id":ident,"view":view,"items":page,',
        "message": _SR + ":return {**common,**source_basis,'state':'AVAILABLE','basis':basis,'content':content,",
        "message-absence": _SR + ":return {**common,'state':'ABSENT','reason':'NO_SAVED_REPLY','basis':None,'content':None,",
        "message-changed": _SR + ':if expected and expected!=basis:raise MessagePartRefusal(payload,expected,basis)',
    },
    consumer_anchors={
        "saved-turn-summary": "src/laplace/web/static_shared/workspace-material.mjs:try{const value=await request(ownerPath)",
        "lazy-detail": "src/laplace/web/static_shared/workspace-session.mjs:"
                       "try{const data=await projectRequest('/authoring/session-turn?'+",
        "selected-message-sdk": 'src/laplace/sdk.py:return session_reads.public_message(_root(root),dict(payload))',
    },
)

declare(
    "authoring/proposals",
    door="http", route="/authoring/proposals",
    payload=_proposal_http_contract(),
    does="List bounded reviewable proposals for one project with their owner-minted identities.",
    handler_anchor=_AH + ':elif method == "GET" and path == "/authoring/proposals":',
    outputs=("current candidates on the inspected page", "page-qualified count and coverage", "exact continuation and child read handles", "identities on each proposal", "proposal_label/label_basis and turn_ts; conversation provenance is separate"),
    errors=("409 JSON refused/error: project is unregistered", "500 JSON error: unexpected owner failure"),
    response_anchors={"bounded-list": 'src/laplace/manuscript/proposal_navigation.py:def read(root,project,payload):'},
    consumer_anchors={"project-review-queue": "src/laplace/web/static_shared/workspace-review.mjs:const previous=data,path=handle?proposalReadURL(handle,{project,queue:true})"},
)

declare(
    "authoring/proposal-preview",
    door="http", route="/authoring/proposal-preview",
    payload=_proposal_http_contract(preview=True),
    does="Read the canonical proposal summary/edit/basis/preview scope by id, or supported legacy turn_id alias. Omitted view defaults to preview; omitted version retains the owner's latest selection. Exact version/record handles preserve immutable candidate identity; id and turn_id must agree when both are supplied.",
    handler_anchor=_AH + ':elif method == "GET" and path == "/authoring/proposal-preview":',
    outputs=("proposal_version and identities", "reviewable and turn_active", "proposal_state and remaining", "edits with placement status", "read_scope names candidate versus selected-edit remaining scope", "view=changed-reads: bounded pages of changed consulted reads with next"),
    errors=("409 JSON refused/error: unknown proposal or unreadable source", "500 JSON error: unexpected owner failure"),
    recoverable=("conflict remains reviewable by current/proposed comparison; re-read before deciding",),
    response_anchors={"decision-state": _MP + ':return {"project": project, "turn_id": turn_id, "answer": proposal.get("answer", ""),'},
    consumer_anchors={
        "manuscript-preview": "src/laplace/web/static_shared/workspace-proposals.mjs:  async function reviewProposal(",
        "proposal-placement": "src/laplace/web/static_shared/workspace-proposals.mjs:walk.showProposal(preview,{readOnly,onDecision:readOnly?undefined:decide",
    },
)

declare(
    "work/structure",
    door="http", route="/work/structure",
    payload=project_structure.http_read_contract(),
    does="Read the existing full structure, or explicit scoped summary/detail through the same owner. Summary publishes source correspondence, paging cut and available guards; full supplies the plan-state mutation token.",
    handler_anchor="src/laplace/web/project_work_surface.py:elif path == \"/work/structure\" and method == \"GET\":" ,
    outputs=("revision and identities", "sections and source_outline", "logical objects, evidence and gaps"),
    errors=("422 JSON refused/error with the owner sentence",),
    response_anchors={"plan-state": "src/laplace/manuscript/project_structure.py:\"status\": \"AVAILABLE\" if eligible else \"INELIGIBLE\", \"eligible_for_authoring\": eligible,"},
    consumer_anchors={
        "structure-view": "src/laplace/web/static_shared/workspace-spine.mjs:const url = '/work/structure?' + query;",
        "heading-parent": "src/laplace/web/static_shared/walk-paragraph-ops.mjs:structure=await store.fetchJSON('/work/structure?'+new URLSearchParams({project:S.corpus}))",
    },
)

declare(
    "work/structure-change",
    door="http", route="/work/structure/change", payload=_structure_change_input(),
    does="Run the existing guarded project structure operation and return its refreshed state.",
    header=_HEADER, header_door=_HEADER_DOOR,
    handler_anchor="src/laplace/web/project_work_surface.py:elif path == \"/work/structure/change\" and method == \"POST\":" ,
    outputs=("ok/status and operation", "revision, affected and effects", "state from a fresh owner read"),
    errors=("422 JSON error/refused; stale identities include the owner-produced needed read",),
    recoverable=("caller replaces its projection with error.state when present, otherwise re-reads /work/structure",),
    response_anchors={
        "owner-state": "src/laplace/manuscript/project_structure.py:response={\"ok\": bool(result.get(\"ok\")),",
        "http-refusal": "src/laplace/web/project_work_surface.py:return 422, \"application/json\", json.dumps(",
    },
    consumer_anchors={"plan-refresh": "src/laplace/web/static_shared/workspace-reader-plan-view.mjs:"
                                      "async function plan(operation,extra={}){try{const result=await api('/work/structure/change'"},
)

declare(
    "walk/doc",
    door="http", route="/walk/doc",
    payload=_object(("corpus",), {"corpus": _STRING, "dir": _STRING,
                    "identities": {"enum": ["0", "1"]}, "known_revision": _STRING,
                    "sections": _STRING, "files": _STRING}, additional=False),
    does="Render the selected manuscript source as the walk block model and owner identities; optionally only named sections/files, or nothing when the caller's known_revision is still current.",
    handler_anchor="src/laplace/manuscript/walk.py:if path == \"/walk/doc\" and method == \"GET\":" ,
    outputs=("ok plus source/document identity", "sections and blocks", "optional owner-minted identities",
             "section_index (id, title, file, blocks, file_revision for every section) on every full or partial answer",
             "sections=<id,id> or files=<file,file> delivers only those sections with partial=true and selected_sections; known_revision=<current_revision> answers {unchanged:true, current_revision, source_observation, presentation_revision} without building the model; known_revision is a whole-document condition and is ignored (known_revision_ignored:true, sections delivered) when combined with sections/files"),
    errors=("404 JSON document projection when the selected source cannot be rendered",),
    recoverable=("the editor preserves drafts and retries a fresh whole-document read", "a partial answer whose section_index differs from the held document is followed by a whole read"),
    response_anchors={"document-model": "src/laplace/manuscript/walk.py:return _json_resp(200 if res.get(\"ok\") else 404, res)"},
    consumer_anchors={
        "walk-load": "src/laplace/web/static_shared/walk-document.mjs:raw = providedDocument || await store.fetchJSON(\"/walk/doc\"",
        "block-refresh": "src/laplace/web/static_shared/walk-document.mjs:raw = await store.fetchJSON(\"/walk/doc\", {params: {identities: 1}})",
    },
)

declare(
    "authoring/build-status",
    door="http", route="/authoring/build",
    payload={**_object(("project",), {"project": _STRING,"build_target":_STRING,"build_job":_STRING,
                                     "view": {"enum": ["summary"]}, "known_revision": _STRING}, additional=False),
        'allOf':[{'not':{'required':['build_target','build_job']}}]},
    does="Read current build lifecycle/freshness or the exact issued build_job, independent of later input/selection changes; no build or recovery mutation. With known_revision equal to the returned summary_revision the answer is the identities only.",
    handler_anchor=_AH + ':elif path == "/authoring/build" and method in {"GET", "POST"}:',
    # A supplied but blank build_target/build_job must reach the one admission rule and refuse, not vanish.
    extras={'lossless_query': True},
    outputs=("state and running", "ok, present, fresh and degraded", "pdf, reason, fix and log_tail",
             "every status answer carries summary_revision, a digest of the whole delivered status projection (document revision, build identity/started/finished, state, running, freshness, outputs, coherence) less log_tail/error_detail; view=summary omits log_tail/error_detail",
             "known_revision=<summary_revision> that still matches answers {unchanged:true, summary_revision, current_revision, document_status, state, running, as_of}; a new or finished build job on unchanged source changes summary_revision and is therefore delivered (the observation is still computed; bytes are saved, not the source stat/hash). The candidate/build_job addressed branches are not conditional."),
    errors=("409 JSON refused/error when no manuscript source is selected", "500 JSON error: unexpected status failure"),
    rules=(Rule("state", field="fresh", says="present or ok is not current; fresh also requires no active run and unchanged dependencies"),),
    response_anchors={"freshness": "src/laplace/manuscript/projection_viewer.py:return base(present=have_pdf, fresh=bool(fresh), degraded=(not fresh),"},
    consumer_anchors={"output-status": "src/laplace/web/static_shared/workspace-output.mjs:async function paintBuild(){"},
)

declare(
    "authoring/build-start",
    door="http", route="/authoring/build",
    payload={**_build_request_schema(),'required':['project'],
        'properties':{'project':_STRING,**_build_request_schema()['properties']}},
    does="Queue/coalesce a current manuscript or owner-issued derived build, or action:cancel the exact returned build_job. No caller PID/path selection; cancelling blocks retry until owned-process cleanup. Terminal cancellation is an explicit no-op; missing/stale job refuses.",
    header=_HEADER, header_door=_HEADER_DOOR,
    handler_anchor=_AH + ':elif path == "/authoring/build" and method in {"GET", "POST"}:',
    outputs=("status=started or running, or cancel_outcome=requested/recovered/already_terminal", "coalesced shares exact build_job", "job_status_read and cancel_action"),
    errors=("409 JSON refused/error: read-only source, absent source, or start refusal", "500 JSON error: unexpected build failure"),
    recoverable=("poll GET /authoring/build until running is false; inspect reason and log_tail on failure",),
    response_anchors={"queued": "src/laplace/manuscript/projection_viewer.py:return 200, {\"status\": \"started\", \"coalesced\": False, \"file\": file_param,"},
    consumer_anchors={"build-control": "src/laplace/web/static_shared/workspace-output.mjs:const compile=button(build.running?'Building…':'Build manuscript PDF'"},
)

declare(
    "projection/pdf",
    door="http", route="/projection/pdf",
    payload=_object(("file",), {"file": _STRING, "corpus": _STRING, "compile_root": _STRING,
        "build_target":_STRING,"export_receipt": _STRING,"expected_content_revision": {"type":"string","pattern":"^sha256:[0-9a-f]{64}$"}}, additional=False),
    does="Read the exact compiled PDF selected by the build status response, or a saved export PDF by its own receipt.",
    handler_anchor="src/laplace/manuscript/projection_viewer.py:if path == \"/projection/pdf\" and method == \"GET\":" ,
    outputs=("application/pdf bytes",),
    errors=("403 JSON error: file escapes the repository", "404 JSON error: no compiled PDF", "409 JSON error: selected compile root or membership is unproved",
            "409 JSON error: a saved export's path, project, receipt or recorded pin is refused (reason export-*)",
            "409 JSON error: export_receipt with a missing corpus or with compile_root/build_target is refused, never served as a current PDF"),
    response_anchors={
        "pdf-bytes": "src/laplace/manuscript/projection_viewer.py:return 200, \"application/pdf\", data",
        "saved-export-bytes": "src/laplace/manuscript/projection_viewer.py:return 200, 'application/pdf', data",
        "saved-export-refused": "src/laplace/manuscript/projection_viewer.py:return _json(409, {'error': str(refused), 'reason': refused.reason})",
        "missing": "src/laplace/manuscript/projection_viewer.py:return _json(404, {\"error\": f\"no compiled pdf at {p.name} - compile first\"})",
    },
    consumer_anchors={"read-current-or-last": "src/laplace/web/static_shared/workspace-output.mjs:const pdf=documentPdfURL(current);"},
)


declare('work/storage', door='http', route='/work/storage',
        payload=_object(('project',), {'project': _STRING}, additional=False),
        does='Measure project store bytes and protected cleanup categories.',
        handler_anchor='src/laplace/web/project_work_surface.py:if path == "/work/storage" and method == "GET":')
declare('work/storage-prune', door='http', route='/work/storage/prune',
        payload=_object(('project','confirm'), {'project': _STRING, 'confirm': {'const': True}}, additional=False),
        does='Confirm removal of empty orphan provider workspaces; all content stays protected.',
        handler_anchor='src/laplace/web/project_work_surface.py:elif path == "/work/storage/prune" and method == "POST":')

declare(
    "work/materials", door="http", route="/work/materials",
    payload=_object(("project",), {"project": _STRING, "offset": {"type": "integer", "minimum": 0}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, additional=False),
    does="Read the same bounded recorded-material catalogue exposed by the materials agent operation.",
    handler_anchor='src/laplace/web/project_work_surface.py:elif path == "/work/materials" and method == "GET":',
    outputs=("materials with exact scoped path/receipt/read_handle", "pagination total/next_offset", "coverage and unresolved receipt count"),
    errors=("422: unknown project or invalid pagination",),
    recoverable=("Read exact artifact handle to check current file revision.",),
    response_anchors={"catalogue": 'src/laplace/projects/artifacts.py:return {"project": project, "materials": materials[offset:offset + limit],'},
    consumer_anchors={"material-view": "src/laplace/web/static_shared/workspace-material.mjs:const value=await request(url('/work/materials'"},
)


from laplace.projects.library import material_reference_contract

declare('projects/material-references', door='http', route='/projects/material-references',
    payload=material_reference_contract()['read'],
    does='Read paged shared membership or bounded current source through one exact stored binding.',
    handler_anchor='src/laplace/projects/library.py:if path == "/projects/material-references":',
    outputs=('exact consumed/current identities and explicit currentness', 'owner-backed read continuation'),
    errors=('422: unknown project/binding or invalid read controls',))

declare('projects/material-reference-change', door='http', route='/projects/material-references',
    payload=material_reference_contract()['write'],
    does='Explicitly attach/adopt/remove shared uses-material membership using the registry revision guard.',
    header=_HEADER, header_door=_HEADER_DOOR,
    handler_anchor='src/laplace/projects/library.py:if path == "/projects/material-references":',
    effects=('project membership only',),
    errors=('409: changed registry or owner identity', '422: malformed target/action'),
    rules=(Rule('scope', says='Binding grants no target writes and copies no source contents.'),))


from laplace.projects.library import app_settings_contract, app_voice_change_contract
declare('projects/app-settings', door='http', route='/projects/app-settings',
    payload=app_settings_contract(require_scope=False), does='Inspect global application configuration and shared voice without creating or selecting a project.',
    handler_anchor='src/laplace/projects/library.py:if path == "/projects/app-settings":',
    outputs=('owned configuration metadata with explicit missing mutation capabilities',))
declare('projects/app-voice-change', door='http', route='/projects/app-settings',
    payload=app_voice_change_contract(),
    does='Edit an explicit shared voice profile through existing exact profile/provenance guards; project selections remain unchanged.',
    header=_HEADER, header_door=_HEADER_DOOR,
    handler_anchor='src/laplace/projects/library.py:if path == "/projects/app-settings":',
    effects=('existing profiles/voice file only',))

from laplace.writing.schemas import SCHEMAS
from laplace.work.history import activity_http_contract, source_http_contract

_history_http_payload=_object((), {'project': _STRING,'corpus': _STRING, **SCHEMAS['author_history']['properties']}, additional=False)
_history_http_payload['allOf']=[{'anyOf':[{'required':['project']},{'required':['corpus']}]},
    {'if':{'required':['view'],'properties':{'view':{'const':'activity'}}},'then':activity_http_contract()},
    {'if':{'required':['view'],'properties':{'view':{'const':'source'}}},'then':source_http_contract()}]

declare('authoring/history', door='http', route='/authoring/history',
    payload=_history_http_payload,
    derived={'historical_source_protocol':'laplace.work.history:source_protocol'},
    does='Read the same bounded correction projection as author_history, or inspect one exact off-page correction.',
    handler_anchor=_AH + ':elif method == "GET" and path == "/authoring/history":',
    outputs=('safe metadata and explicit text-preview omissions', 'category/status counts and exact total/next_offset', 'current authoring revision and read cut covering feedback',
             'manuscript targets carry repo_file (checkout path) with binding BOUND; a historical row that kept only a basename carries file with binding UNPROVED and is never mapped onto a same-named file',
             'view=activity with id delivers comparisons as one page (comparison_offset/comparison_limit, default 6) with comparisons_pagination.total and next_read; view=record keeps every hunk'),
    errors=('409: CHANGED_INPUT when paging across a changed authoring/feedback snapshot', '409: exact correction is unavailable'),
    rules=(Rule('shape', says='Carry as_of when paging; refresh explicitly after CHANGED_INPUT. Use revision for the existing authoring mutation guard.'),
           Rule('shape', says='An id read retains complete correction history independently of filters or offset; source comparisons remain explicit author_changes reads.')))

declare('authoring/state-summary', door='http', route='/authoring/state',
    payload=_object(('project', 'view'), {'project': _STRING, 'view': {'enum': ['summary', 'sessions']}, 'session_limit': _INT}, additional=False),
    does='Read framing or bounded session metadata without hydrating historical corrections and contexts.',
    handler_anchor=_AH + ':elif method == "GET" and path == "/authoring/state":',
    outputs=('summary: argument/framing and original revision guards', 'sessions: session metadata and total count'))

# Literature HTTP consumes the same schemas and owners as the existing native acts.
for _name,_route,_verb in [('reference_source','/references/source','GET'),('reference_text','/references/text','GET'),('reference_fetch','/references/fetch','POST'),('literature_import','/references/literature-import','POST'),('literature_bind','/references/literature-bind','POST'),('literature_scope','/references/literature-scope','GET')]:
    _variants=SCHEMAS[_name].get('oneOf',[SCHEMAS[_name]])
    _http_variants=[_object(('project',*variant.get('required',[])),{'project':_STRING,**variant.get('properties',{})},additional=False) for variant in _variants]
    declare('references/'+_name, door='http', route=_route,
        payload={'oneOf':_http_variants} if len(_http_variants)>1 else _http_variants[0],
        does='Use the existing '+_name+' literature owner; source bytes, meaning guards and rendered bibliography remain distinct.',
        header=_HEADER if _verb=='POST' else None, header_door=_HEADER_DOOR if _verb=='POST' else None,
        handler_anchor='src/laplace/research/literature.py:'+("if path == '"+_route+"':" if _name not in {'literature_bind','literature_import'} else "if path in ('/references/literature-import', '/references/literature-bind'):"),
        outputs=('registered source/binding/scoped coverage owner result',),
        errors=('changed source/claim/coverage refuses; retained metadata and authored drafts are not silently refreshed',))

# Existing technical friction owner routes, coupled through the same generic verbs.
from laplace.work.technical_friction import read_contract as _friction_read_contract, report_contract as _friction_report_contract, PERMITTED_MODES as _friction_modes
for _name,_verb in (('corpus/friction-read','read'),('corpus/friction-report','record'),('corpus/friction-create','create')):
    declare(_name,door='http',route='/corpus/friction',
        payload=_friction_read_contract() if _verb=='read' else _friction_report_contract(),
        does='Read or record an existing technical friction observation; never manuscript instruction or work acceptance.',
        handler_anchor='src/laplace/web/scanner.py:elif u.path == "/corpus/friction":' if _verb=='read' else 'src/laplace/web/scanner.py:            if u.path == "/corpus/friction":',
        outputs=('owner record and exact read handle','status open without automatic work/guidance change'),
        extras={'generic_permission':{'permitted_modes':sorted(_friction_modes),'agent_bound_required':_verb!='read','by':'server-bound eigen:session on report'}})


declare(
    "authoring/help", door="http", route="/authoring/help",
    payload=help_http_contract(), extras={"lossless_query": True},
    does="Inspect current help under an exact saved turn role or explicit unbound human role; records no provider read or retry. view=areas serves the workspace's own help: areas, journeys and controls from the shared declarations (the native help {concept: areas|journeys|controls} read), versioned and bounded, with no role.",
    handler_anchor=_AH + ':elif method == "GET" and path == "/authoring/help":',
    outputs=("project", "inspection binding, turn_id and mode", "help: same native response",
             "view=areas: inspection binding 'declarations' and help: laplace.help-areas/1 with version, areas, journeys, controls, observation_facts and predicate_language"),
    errors=("409: duplicate/unknown/conflicting selector or binding; unavailable/ambiguous project turn",),
)


# THE HEALTH DOOR (C12 residual R1, 2026-10-15). One process-scoped GET with one optional selector,
# admitted against this payload by scanner._health_view BEFORE any health work. No query: the lifecycle
# answer the desktop launcher (writing_app.health) and the workspace read. view=traffic: the server
# process traffic ledger (src/laplace/web/traffic.py), developer instrumentation for actual gates.
# Neither view has a native (tool) door: both are server-process state, not project state.
_HEALTH_ANCHOR = 'src/laplace/web/scanner.py:if u.path == "/authoring/health":'
declare(
    "authoring/health", door="http", route="/authoring/health",
    payload=_object((), {"view": {"enum": ["traffic"], "description": "absent: lifecycle health; traffic: the process traffic ledger"}}, additional=False),
    extras={"lossless_query": True, "native": None, "scope": "server process; every client; no project, role or session"},
    does=("Read the server process's health. No query: the lifecycle answer (laplace.writing-health/2: source, runtime, "
          "pid, active turns, previews, builds, runs, proof checks, mutations and work). view=traffic: the process traffic "
          "ledger (laplace.writing-traffic/1): per declared route or fixed bucket, requests, status classes, in-flight, "
          "bytes the socket accepted, failed writes, declared request lengths by label, total and max time; the event "
          "stream's opened/closed/open now/writes/bytes; reads of this view counted apart. Loopback clients only; a "
          "restart resets it; difference two reads. Neither view has a native tool door."),
    handler_anchor=_HEALTH_ANCHOR,
    outputs=("no query: laplace.writing-health/2", "view=traffic: laplace.writing-traffic/1 (routes, event_stream, diagnostic, unattributed, observer_errors, limits, scope, not_counted)"),
    errors=("422 any other query (unknown, repeated or blank key, a view other than traffic, a view mixed with another key), refused before any health work, naming the two admitted reads",
            "403 view=traffic from a non-loopback client", "403 a foreign Host header (every route)"),
    rules=(Rule("scope", field="view", door=_at("src/laplace/web/scanner.py", 'if str(self.client_address[0]).removeprefix("::ffff:") not in ("127.0.0.1", "::1"):'),
                says="view=traffic answers loopback clients only; other clients are refused 403 with the admitted reads"),),
)


from laplace.manuscript.manuscript_source import source_protocol
_raw_source = source_protocol()
declare('projection/source', door='http', route='/projection/tex',
    payload=_raw_source['read_query'],
    derived={'source_protocol':'laplace.manuscript.manuscript_source:source_protocol'},
    does='Read exact current document source with its original file and selected-edition guards; historical source has a separate read scope.',
    handler_anchor='src/laplace/manuscript/projection_viewer.py:if path == "/projection/tex":',
    outputs=('laplace.projection-source/1 with source/selection guards and read/save handles',),
    errors=('403 outside selected source/dependencies', '404 unavailable source', '422 invalid query'))
declare('projection/source-save', door='http', route='/projection/tex',
    payload=_raw_source['save_request'],
    derived={'source_protocol':'laplace.manuscript.manuscript_source:source_protocol'},
    does='Commit raw source using the inspected selected-document and physical-file basis. Body is UTF-8 text; guards are query fields.',
    handler_anchor='src/laplace/manuscript/projection_viewer.py:if path == "/projection/tex":',
    effects=('selected source; bank=editor also retains source history',),
    outputs=('source_committed, changed, consumed/new digests, selection_identity, invalidated, history_read and maintenance_warnings',),
    errors=('409 changed/missing inspected basis', '403 source not writable or outside selection', '422 invalid actor/query'),
    rules=(Rule('scope', says='Legacy projection transport does not inherit the eight-prefix writing header gate. Registered source/actor guards are still mandatory; application clients send the deliberate-action header.'),))
declare('authoring/document', door='http', route='/authoring/document',
    payload=_object(('project',), {'project':_STRING,'target_kind':{'enum':['manuscript','derived','publication-edition']}}, additional=False),
    does='Read the bounded document-domain composition used by native document, with exact source and pinned PDF handles.',
    handler_anchor=_AH + ':elif method == "GET" and path == "/authoring/document":',
    outputs=('laplace.current-document/1, selection_identity, files, dependency_revisions, template, pdf_identity and read_handles',
             'target_kind=publication-edition reads laplace.publication-editions/1, the same owner view as native document'))

# Actual architecture/voice owners share candidate contracts across HTTP/native.
declare('work/profiles', door='http', route='/work/profiles', payload=_profile_http_contract(),
    handler_anchor='src/laplace/web/project_work_surface.py:elif path == "/work/profiles" and method == "GET":',
    homes=(), effects=(), extras={'lossless_query': True},
    does='Inspect actual scoped profile values and immutable candidates; projectless reads are workspace-only.')
declare('work/profiles-change', door='http', route='/work/profiles/change', payload=_profile_http_contract(write=True),
    handler_anchor='src/laplace/web/project_work_surface.py:elif path == "/work/profiles/change" and method == "POST":',
    homes=(), effects=('typed profile candidate or guarded preference change; explicit human confirmation remains separate',),
    does='Use ordinary settings authority to propose/apply scoped preferences or explicitly confirm exact architecture fields.',
    rules=(Rule('header', field='X-Laplace-Writing', says='POST requires X-Laplace-Writing: 1 through the existing writing gateway.'),))

# One selected-input owner; explicit preparation and read-only inspection share it.
declare('authoring/reader', door='http', route='/authoring/reader',
    payload={**_sealed_reader.request_contract(), 'properties':{
        **_sealed_reader.request_contract()['properties'], 'action':{'const':'prepare'}}},
    does='Prepare or inspect one exact sealed text-only input and its qualified fresh-reader support.',
    handler_anchor=_AH + ":elif path == '/authoring/reader' and method in {'GET','POST'}:",
    outputs=('immutable manifest/input part reads, exact size facts, candidate versus qualified support, explicit Start descriptor, currentness and result',),
    rules=(Rule('scope', says='POST action=prepare retains selected input bytes; GET reads never Start. The separate authoring/turn profile accepts only project/profile/input/support/request and creates a fresh one-attempt reader after qualification. Tools, project context and resume are unavailable.'),))

from laplace.pipeline.correction_origin import contracts as _comment_contracts

declare('authoring/correction-prepare',door='http',route='/authoring/correction-prepare',
    payload=_comment_contracts()['prepare'],header=_HEADER,header_door=_HEADER_DOOR,
    does='Prepare one passage comment from inspected prose tokens or recheck a retained source basis without reanchoring.',
    handler_anchor=_AH+':elif method == "POST" and path == "/authoring/correction-prepare":',
    outputs=('exact raw-source/selection/extent basis','original authoring guard','ordinary author-instruction meaning'),
    recoverable=('Keep the original quote and draft; explicitly compare changed source. Do not borrow new guards for an old submission.',))
declare('authoring/correction-request',door='http',route='/authoring/correction-request',
    payload=_comment_contracts()['request'],
    does='Read one submitted comment request in its retained canonical feedback home without saving or routing.',
    handler_anchor=_AH+':elif method == "GET" and path == "/authoring/correction-request":',
    outputs=('RECORDED with original AC/FB and intent','terminal NOT_ADMITTED for an explicitly settled original request','NONE only in the registered canonical project home','UNKNOWN on incomplete or mismatched custody'),
    recoverable=('An absent or unknown observation is not terminal non-admission and is not permission to mint another request.',))
declare('authoring/correction-settle',door='http',route='/authoring/correction-settle',
    payload=_comment_contracts()['settle'],header=_HEADER,header_door=_HEADER_DOOR,
    does='Explicitly settle an exact original Save: retain an already recorded origin or durably prevent that uncommitted request from creating a comment.',
    handler_anchor=_AH+':elif method == "POST" and path == "/authoring/correction-settle":',
    effects=('one non-comment terminal outcome in the same canonical feedback family only if the Save has not committed',),
    outputs=('RECORDED original AC/FB','verified terminal NOT_ADMITTED','UNKNOWN when custody is uncertain'),
    recoverable=('Only the matched observed terminal request permits explicit reinspection and a later new Save decision. No automatic retry, comment deletion or route cancellation is performed.',))
declare('authoring/correction-origin',door='http',route='/authoring/correction-origin',
    payload=_object(('project','origin_ref'),{'project':_STRING,'origin_ref':_comment_contracts()['origin']},additional=False),
    does='Read the exact saved comment material and currentness independently of status or sibling feedback churn.',
    handler_anchor=_AH+':elif method == "GET" and path == "/authoring/correction-origin":',
    outputs=('exact origin reference','complete original comment','current source qualification','exact read handle'))
declare('authoring/correction-request-save',door='http',route='/authoring/correction',
    payload=_comment_contracts()['save'],header=_HEADER,header_door=_HEADER_DOOR,
    does='Save one source-bound ordinary passage instruction with same-request AC/FB recovery before mutable guards.',
    handler_anchor=_AH+':elif method == "POST" and path == "/authoring/correction":',
    effects=('one canonical feedback comment and authoring projection','optional separately admitted Work review route after origin locks release'),
    outputs=('original AC/FB receipt and immutable material reference or the prior terminal non-admission','separate review-route outcome only for a recorded origin'),
    recoverable=('Reconcile the same request and exact retained intent after a lost response. A route failure can leave the comment saved.',))


from laplace.projects.material_intake import metadata_contract as _intake_metadata_contract
for _intake_name,_intake_path,_intake_method,_intake_payload,_intake_effect in (
    ('projects/material-intake','/projects/material-intake','GET',_object(('project','request'),{'project':_STRING,'request':{'type':'string','maxLength':8192}},additional=False),()),
    ('projects/material-intake-upload','/projects/material-intake/upload','POST',_intake_metadata_contract(),('immutable original bytes and separate explicitly requested Material membership',)),
    ('projects/material-intake-link','/projects/material-intake/link','POST',_object(('project','request_id','expected_revision'),{'project':_STRING,'request_id':{'type':'string','minLength':8,'maxLength':96},'expected_revision':_STRING},additional=False),('recover retained ART receipt and original requested membership',)),
    ('projects/material-intake-read','/projects/material-intake/read','GET',_object(('project','request'),{'project':_STRING,'request':{'type':'string','maxLength':8192}},additional=False),()),
    ('projects/material-intake-original','/projects/material-intake/original','GET',_object(('project','id','expected_sha256'),{'project':_STRING,'id':_STRING,'expected_sha256':{'type':'string','pattern':'^(sha256:)?[a-f0-9]{64}$'}},additional=False),()),
):
    declare(_intake_name,door='http',route=_intake_path,payload=_intake_payload,
        does='Explicit bounded local document intake or exact original/request inspection through artifact custody.',
        header=_HEADER if _intake_method=='POST' else None,header_door=_HEADER_DOOR if _intake_method=='POST' else None,
        handler_anchor='src/laplace/projects/material_intake.py:def http(path,query,method,body,root):',
        effects=_intake_effect,outputs=('original bytes retention/ART receipt and Material membership are separate facts with exact read/recovery handles',),
        rules=(Rule('shape',says='Upload metadata is closed JSON in the request query; body is raw PDF or UTF-8 bytes and Content-Type matches media_type. Project/request exact replay precedes mutable destination guard. NONE is not terminal no-effect; retain original bytes and wire. Link is explicit after inspecting current destination, and completed upload replay never relinks removed membership.'),))


from laplace.work import owner_discovery as _object_discovery
from laplace.work.object_facets import change_contract as _object_change_contract
from laplace.projects.project_handover import object_contract as _object_handover_contract

declare('work/object-discovery',door='http',route='/work/discovery',payload=_object_discovery.contract(),
    does='Discover workspace objects without a selected project, or follow an exact owner-qualified object, consumed dependency, page or retained request.',
    handler_anchor='src/laplace/web/project_work_surface.py:if path == "/work/discovery" and method == "GET":',
    extras={'lossless_query':True,'json_query_fields':['reference','read','object_request','coordinate','relations']},
    outputs=('same scoped SDK/native facets, exact owner actions/reads, removable project lenses, explicit coverage and unavailable standing',),
    rules=(Rule('scope',says='The served workspace supplies authority. A lens narrows discovery; it does not grant source or mutation access. Reference/read/object_request/coordinate/relations use exact JSON encoding; geometry carries bounded typed metadata and independent owner cuts, never implied authority.'),))
for _name,_route,_contract,_anchor in [
    ('work/object-change','/work/object-change',_object_change_contract(),"elif path == '/work/object-change' and method == 'POST':"),
    ('work/object-handover','/work/object-handover',_object_handover_contract(),"elif path == '/work/object-handover' and method == 'POST':")]:
    _payload={**_contract,'required':list(dict.fromkeys([*_contract['required'],'project']))}
    if _name=='work/object-handover':
        _payload={**_contract,'allOf':[*_contract.get('allOf',[]),
            {'if':{'properties':{'definition_transport':{'const':'lineage-v2'}},'required':['definition_transport']},
             'else':{'required':['project']}}]}
    declare(_name,door='http',route=_route,payload=_payload,
        header=_HEADER,header_door=_HEADER_DOOR,
        handler_anchor='src/laplace/web/project_work_surface.py:'+_anchor,
        does='Use the exact selected owner decision and original request through the local human door.',
        outputs=('actual owner receipt/currentness and exact same-request recovery; generic errors never imply no effects',),
        recoverable=('Keep the original wire and newer draft. Follow the issued same-request lookup or explicit settlement; do not infer a new identity from absence or changed current content.',))


declare('research/run-request',door='http',route='/research/run/request',
    payload=_object(('project','request'),{'project':_STRING,'request':SCHEMAS['run_status']['oneOf'][1]['properties']['request']},additional=False),
    does='Inspect one exact original registered Research launch request without launching or changing it.',
    handler_anchor='src/laplace/web/research_surface.py:def _run_request_route',
    effects=(),outputs=('effect RECORDED with actual run, NONE, UNKNOWN or CONFLICT',),
    recoverable=('Keep the exact original request on unknown transport or custody. NONE is not terminal non-admission or permission to mint a replacement; retry only explicitly with identical wire.',))


from laplace.research.research_records import record_request_contract as _research_record_request
declare('research/record-request',door='http',route='/research/record/request',
    payload=_object(('project','request'),{'project':_STRING,'request':_research_record_request()},additional=False),
    does='Read the same original canonical result Save from its responsible record and retained history without saving.',
    handler_anchor='src/laplace/web/research_surface.py:def _record_request_route',
    effects=(),outputs=('NONE nonterminal; RECORDED exact current or historical record; UNKNOWN or CONFLICT',),
    recoverable=('Retain the original wrapper and request_id. NONE permits only explicit identical retry; missing/pruned custody is not new admission authority.',))

def _research_record_http_contract():
    import copy
    value=copy.deepcopy(SCHEMAS['research_record'])
    for branch in value['anyOf']:
        branch['properties']={'project':_STRING,**branch['properties']}
        branch['required']=['project',*branch['required']]
    return value

declare('research/record',door='http',route='/research/record',payload=_research_record_http_contract(),
    header=_HEADER,header_door=_HEADER_DOOR,
    does='Explicitly record or revise a canonical result from the actual completed run and authored interpretation; scientific acceptance is separate.',
    handler_anchor='src/laplace/web/research_surface.py:def _record_route',
    effects=('one guarded canonical Research record and its existing renewal history',),
    outputs=('record revision/provenance and exact original request receipt when request-bound',),
    recoverable=('Inspect the original request after uncertain delivery. Replay uses the same request before mutable run freshness or prior-record CAS; never borrow a fresh guard for an old Save.',))

# One scoped preference owner across SDK, native and the two existing HTTP families.
from laplace.writing import session_settings as _pilot_settings
for _name,_route,_kind,_anchor in (
    ('authoring/session-settings','/authoring/session-settings','conversation',_AH+':elif path == "/authoring/session-settings" and method in {"GET","POST"}:'),
    ('work/session-preferences','/work/session-preferences','project-defaults','src/laplace/web/project_work_surface.py:elif path == "/work/session-preferences" and method in {"GET","POST"}:')):
    declare(_name+'-read',door='http',route=_route,payload=_pilot_settings.http_contract('GET',_kind),
        handler_anchor=_anchor,homes=(),effects=(),extras={'lossless_query':True},
        does='Inspect exact scoped future preferences or original request; passive providers and declared role ceiling are not future authority.',
        outputs=('laplace.session-settings/1 or laplace.session-settings-request/1; current observation is separate from historical receipt',))
    declare(_name+'-change',door='http',route=_route,payload=_pilot_settings.http_contract('POST',_kind),
        handler_anchor=_anchor,homes=(),effects=('future preferences or exact durable NOT_ADMITTED request closure; no execution',),
        does='Save guarded future provider/model/effort preferences or explicitly withdraw the exact unadmitted request. Existing flat fields remain compatible.',
        outputs=('RECORDED/NOT_ADMITTED durable original receipt; storage uncertainty UNKNOWN; no admitted work is rewritten',),
        rules=(Rule('header',field='X-Laplace-Writing',says='Requires X-Laplace-Writing: 1; role/mode/grant/credential fields are not preferences.'),))
del _name,_route,_kind,_anchor

# Only the new opt-in history facets add a closed sub-contract; legacy definition
# reads retain their existing owner admission rather than a second grammar.
from laplace.pipeline.workflow_definition_history import request_contract as _workflow_history_contract, FACETS as _workflow_history_facets
from laplace.pipeline.workflow_operations import read_contract as _workflow_operation_contract, withdraw_contract as _workflow_withdraw_contract, FACETS as _workflow_operation_facets
declare('work/workflow-history',door='http',route='/work/workflow-definitions',
    payload={'type':'object','allOf':[{'if':{'properties':{'facet':{'enum':list(_workflow_history_facets)}},'required':['facet']},'then':_workflow_history_contract()},
                                    {'if':{'properties':{'facet':{'enum':list(_workflow_operation_facets)}},'required':['facet']},'then':_workflow_operation_contract()}]},
    handler_anchor="src/laplace/web/workflow_definitions_surface.py:if path == '/work/workflow-definitions' and method == 'GET':",
    extras={'lossless_query':True,'json_query_fields':['reference','step_ids','inputs','selection','definition','scope','original_request']},
    does='Read bounded retained workflow metadata or one exact saved version through actual served-workspace scope.',
    outputs=('same owner history/lineage/body pages and issued continuations; fixed prefix and explicit current-head reads remain separate',),
    rules=(Rule('scope',says='A project lens narrows actual authority. Native project reads cannot acquire workspace custody or destination/export permission.'),
           Rule('shape',says='History is newest-first, lineage oldest-first, owner ordinals are chronological from1. End-at-cut is not all-pages-loaded or body inspection. BODY_PAGE needs complete explicit exact-pin/codepoint-order assembly before a complete saved-body reading.')))


declare('work/workflow-operation-read',door='http',route='/work/workflow-definitions',
    payload=_workflow_operation_contract(),
    handler_anchor="src/laplace/web/workflow_definitions_surface.py:elif method == 'POST' and path == '/work/workflow-definitions':",
    homes=(),effects=(),
    does='Inspect a scoped execution preview, declared context, creation choices or actual recorded uses through a bounded JSON read; this POST does not Save, prepare or start.',
    outputs=('same owner laplace.workflow-operation/1 and issued explicit continuations; transport_request hashes exact POST body bytes for correlation only, never owner intent or authority',),
    rules=(Rule('scope',says='The served root supplies authority; project_lens narrows it. A JSON scope describes the selected definition, not a grant.'),))

declare('work/workflow-withdraw',door='http',route='/work/workflow-definitions/withdraw',
    payload=_workflow_withdraw_contract(),
    handler_anchor="src/laplace/web/workflow_definitions_surface.py:elif method == 'POST' and path == '/work/workflow-definitions/withdraw':",
    homes=(),effects=('one exact durable no-admission decision only if withdrawal wins the existing owner lock',),
    does='Withdraw the exact unadmitted Save or preparation request. A recorded winner returns its original receipt, never undo; UNKNOWN retains the original wire.',
    outputs=('NOT_ADMITTED/WITHDRAWN, original RECORDED receipt or UNKNOWN; exact request read',),
    rules=(Rule('header',field='X-Laplace-Writing',says='Requires X-Laplace-Writing: 1; native callers still need the actual admitted-author door.'),))
