"""The typed routing advisor: two decisions over the grammar's own alphabets.

This module is the `jev-routing` lane of wave WRITING-RECONCILIATION-W1.  It is a
side experiment and it is **off by default**: `enabled()` is false unless
`LAPLACE_ROUTING_ADVISOR` is set, and nothing in the writing path calls into here
while it is false.

Two decisions, both of them decisions the live system already makes badly:

**D1 — route.**  `route(state)` answers *which `(verb, concept)` pair is this
request?* over the option set the grammar declares.  Today that decision is made
by handing a text model the whole operating brief --- carried as the whole system
prompt on every provider turn at `src/laplace/writing_provider.py:1275-1015` (Claude,
which since 2026-10-05 REPLACES the CLI's base prompt rather than appending to it) and
`:781-783` (Codex), measured at 18,158 characters for `synthetics-foundations` in this
worktree at 87ece9da (the session contract since splits those bytes: the kernel rides
every Claude process and the project body rides once per session) --- and then the exact contract for whatever operation it guessed, up to
32,611 characters for `concept_change` (`src/laplace/writing_contracts.py:107`).
The dispatch itself is `src/laplace/writing/operations.py:145` (`_execute`), whose
option set is the union of the two bare sets at `src/laplace/writing/reads.py:16`
(35 reads) and `:18` (38 writes), with the sub-verb carried in a payload key whose
name changes with depth.

**D4 — classify a refusal.**  `classify(error_text)` answers *which kind of
refusal is this, and therefore which cure does the caller need?* over
`grammar.Refusal.KINDS`.  Today that decision is a substring test over the error
prose: `src/laplace/writing_tools.py:1443` tests the lower-cased message for
`changed`/`stale`/`conflict`/`consumed`, and the resolver target set is the
`add(...)` ladder at `src/laplace/writing_tools.py:1404-1551`.  The response is
then truncated by size at `src/laplace/writing_tools.py:1392`.

**The alphabets are generated, never written here, and they are read live.**
`ROUTE_OPTIONS` is generated from the DISPATCH TABLE --- the `(verb, concept)` pairs
`writing_verbs.ROUTES` can actually reach through the verb door (`door == "both"`) ---
union `grammar.ADDED_PAIRS`, and
`RESOLVER_OPTIONS` is `grammar.Refusal.KINDS`.  There is no list of verbs,
concepts or refusal kinds in this file; a pair this module can suggest is exactly
a pair the dispatch can route AND `grammar.declared_pair` accepts, and
`tests/test_routing.py` fails if any of the three sides moves.

**Why the dispatch table and not `grammar.VERB_CONCEPTS` alone.**  Before this
synthesis the advisor's alphabet came from `grammar.VERB_CONCEPTS`, the pairs
`map_verbs.py` splices from `mapping.csv`, while the thing that would have to EXECUTE
a suggestion was `writing_verbs.ROUTES`, generated from the same table by
`tools/writing_verbs/gen_routes.py`.  Two generators over one row source agree until
one of them stops: a pair declared in the mapping with no `door == "both"` route is a
pair the advisor would suggest and the verb door would refuse to route, and a route
added to the dispatch for a pair the grammar does not declare is a pair the advisor
would never suggest although the door accepts it.  Measured on the merged tree
(`evidence/.../wave1/synth-dispatch-jev/alphabet.json`): 146 routes, 104 distinct
pairs, 104 of them reachable with `door == "both"`, and the three sets ---
dispatch-reachable pairs, `grammar.VERB_CONCEPTS`, `mapping.csv` rows --- are equal,
0 either way.  The alphabet is now read off the side that has to act on it, and the
equality is a check (`test_the_route_alphabet_is_the_dispatch_table_not_a_list`)
rather than a coincidence of two generators.  Both names are module properties (PEP 562 `__getattr__`), not
values frozen at import, because `grammar.declare_pair` is the grammar's own
documented second route into the closed set (`grammar.py:1115`, GRAMMAR.md §11):
a pair declared at runtime by a lane widens `declared_pair`, so freezing the
alphabet at import would let the grammar accept a `Request` this advisor could
never suggest, and the advisor would abstain on every such row in silence.

**It cannot authorise a write.**  `advise()` returns a `grammar.Request` and a
confidence; it never calls an owner, and it imports nothing that can.  The measured
import closure is five modules --- `laplace`, `laplace.pipeline.canon` (pulled in by
`src/laplace/__init__.py:9`), `laplace.core.grammar`, `laplace.native.verbs` (the dispatch
TABLE, whose only module-level import is `laplace.core.grammar`; it builds an
`(operation, payload)` pair and imports no owner to hand it to) and this one --- and no
owner surface is among them, which `test_the_advisor_cannot_reach_a_write` asserts by name,
with `laplace.native.tools` --- the one module that can execute --- asserted ABSENT, while
running the whole advisor over all 540 labelled rows under an audit hook that records
any `open` for writing, any subprocess and any socket.  Routing state includes
manuscript text, and
`evidence/WRITING_FRICTION_2026-10-01/wave1/jev-assessment.md` §4.5 states the
boundary this keeps: a decision layer may choose among verbs and reads, each still
guarded by the owners' own revision and scope checks, and must never be the thing
that authorises a write.

**Calibration is the whole value, so the probability is calibrated here and not
asserted.**  A raw head score is mapped through `Calibration`, a monotone
piecewise-constant map fitted by pool-adjacent-violators on held-out labels, so
`Decision.probability` is an estimate of *being right* rather than a score.  The
fitted maps and the reliability bins with their counts are in
`tests/routing_calibration/`; the vendor publishes no calibration curve for jev
(`jev-assessment.md` §4.3), which is why this layer measures its own.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import json
import math
import os
import time
from typing import Any, Mapping, Protocol, Sequence

from laplace.core import grammar
# The DISPATCH TABLE, imported for its rows and for nothing else: `writing_verbs` imports
# `laplace.core.grammar` at module level and no owner at all, so this does not put an owner in
# the advisor's import closure -- asserted, closure and absence both, by
# `test_the_advisor_cannot_reach_a_write`.
from laplace.native import verbs as writing_verbs

# ---------------------------------------------------------------------------
# 0. The flag.  Off unless the environment says otherwise.
# ---------------------------------------------------------------------------
ADVISOR_FLAG = "LAPLACE_ROUTING_ADVISOR"
_TRUE = {"1", "true", "yes", "on"}


def enabled(env: Mapping[str, str] | None = None) -> bool:
    """True only when the flag is explicitly set.  Default off, by construction."""
    source = os.environ if env is None else env
    return str(source.get(ADVISOR_FLAG, "")).strip().lower() in _TRUE


# ---------------------------------------------------------------------------
# 1. The two option sets, GENERATED from the grammar module.
# ---------------------------------------------------------------------------
def dispatch_pairs() -> frozenset[tuple[str, str]]:
    """The `(verb, concept)` pairs the DISPATCH can route through the verb door.

    `writing_verbs.ROUTES` is the dispatch table (`src/laplace/writing_verbs.py:161`,
    inside the generated block whose marker is `src/laplace/writing_verbs.py:159`,
    generated by `tools/writing_verbs/gen_routes.py` from `mapping.csv`); a route whose
    `door` is `"shim"` is reachable only under its old operation name, because two or
    more old operations share that pair and no payload key chooses between them
    (`writing_verbs.choose` refuses to guess).  Suggesting such a pair would be
    suggesting a request `writing_tools.request()` cannot route, so the alphabet is the
    `door == "both"` projection and nothing wider.  The table is bound AT IMPORT (the
    module-level `from laplace.native import verbs as writing_verbs` below); the projection is taken per
    call, because `grammar.declare_pair` can widen the set afterwards.
    """
    return frozenset((route.verb, route.concept) for route in writing_verbs.ROUTES
                     if route.door == "both")


def route_options() -> tuple[tuple[str, str], ...]:
    """The D1 option set: every pair THE VERB DOOR can route, read live.

    Generated from the dispatch table (`dispatch_pairs`) on every call, so a route added to
    the table is suggestible immediately and this module still holds no list of its own.
    `mapping.csv` is the one row source behind both `ROUTES` and `grammar.VERB_CONCEPTS`,
    and `test_the_route_alphabet_is_the_dispatch_table_not_a_list` fails if the sets stop
    agreeing.

    `grammar.ADDED_PAIRS` WAS UNIONED IN HERE AND IS NOT ANY MORE
    (WRITING-CONSOLIDATION-W1).  Two tests of this lane disagreed and neither could fail
    while `ADDED_PAIRS` was empty at import: one asserted the alphabet IS the `door == "both"`
    projection, the other asserted a live-declared pair widens it.  `identity_doors` then
    declared `create note@paragraph|section|chapter` --- the editor's keep/cut ruling, an act
    of an HTTP door (`writing_verbs` ``review/adjudicate-comment``) with no tool route and
    none wanted --- and the disagreement became three concrete pairs.

    The verb door wins, because the advisor's output is CONSUMED by
    `writing_tools.request` -> `writing_verbs.choose`, which raises for a pair the table
    cannot route: a suggestion outside the dispatch is not a visible refusal, it is a label
    that throws inside the caller's own call.  `declare_pair` makes a pair legal for a
    grammar `Request`; whether the verb door can execute one is a different question with a
    different answer, and this module answers only the second.  A pair only an HTTP door
    routes is routable THERE, and that door's advisor --- if one is ever built --- reads
    :func:`http_pairs`.  Nothing is silent: :func:`declared_pairs_outside_the_verb_door`
    names every declared pair this alphabet leaves out, and where it IS routable.
    """
    return tuple(sorted(dispatch_pairs()))


def http_pairs() -> frozenset[tuple[str, str]]:
    """The `(verb, concept)` pairs the HTTP doors route (`writing_verbs.HTTP_ROUTES`)."""
    return frozenset((route.verb, route.concept) for route in writing_verbs.HTTP_ROUTES)


def declared_pairs_outside_the_verb_door() -> tuple[dict[str, str], ...]:
    """Every live-declared pair the verb door cannot route, with where it IS routable.

    A row per pair: the act, the door that routes it (`http` with the route, or `none`), and
    the reason the pair was declared (`grammar.ADDED_PAIRS`' own `because`).  A `none` row is
    a pair nothing can execute, which is what
    `test_the_route_alphabet_is_the_dispatch_table_not_a_list` refuses.  Returned, not
    raised: this is a report about two tables that are read live.
    """
    verb_door, http = dispatch_pairs(), http_pairs()
    out = []
    for pair, because in sorted(grammar.ADDED_PAIRS.items()):
        if pair in verb_door:
            continue
        routes = [route.route for route in writing_verbs.HTTP_ROUTES
                  if (route.verb, route.concept) == pair]
        out.append({"act": "%s %s" % pair,
                    "routed_by": "http" if pair in http else "none",
                    "route": routes[0] if routes else "",
                    "because": because})
    return tuple(out)


def resolver_options() -> tuple[str, ...]:
    """The D4 option set: the grammar's refusal kinds, in the grammar's order."""
    return tuple(grammar.Refusal.KINDS)


# `routing.ROUTE_OPTIONS` and `routing.RESOLVER_OPTIONS` are read-through module
# attributes, not constants: PEP 562 sends the lookup to `__getattr__` below, which
# calls the generator.  A reader who wrote `from laplace.native.routing import ROUTE_OPTIONS`
# would still get a snapshot, which is why nothing in this module or the proofs does.
_LIVE_OPTIONS = {"ROUTE_OPTIONS": route_options, "RESOLVER_OPTIONS": resolver_options}


def __getattr__(name: str):
    generator = _LIVE_OPTIONS.get(name)
    if generator is not None:
        return generator()
    raise AttributeError("module %r has no attribute %r" % (__name__, name))

# The 255-option ceiling a `choice` accepts (jev-assessment.md §1, the vendor's
# `primitives/choice.md`).  Both option sets must fit in one question or the
# design needs the documented chained-choice remedy; this is checked, not assumed.
CHOICE_CEILING = 255


def options_fit_one_choice() -> bool:
    return (len(route_options()) <= CHOICE_CEILING
            and len(resolver_options()) <= CHOICE_CEILING)


# ---------------------------------------------------------------------------
# 2. The state a decision is composed from, and its features.
# ---------------------------------------------------------------------------
# The vendor's hard cap is 32k tokens for `state` plus the longest question, and
# its published weakness page names accuracy falling as unrelated content grows
# the state (jev-assessment.md §1, §4.2).  So the state is composed per decision
# and never the whole brief.  `state_text` is what any decider sees, and
# `Decision.state_chars` is its length, which is the number the comparison with
# today's whole-brief routing is made on.

_DISCRIMINATOR_KEYS = ("operation", "action", "kind", "view", "status", "op", "mode")
"""Payload keys that carry the sub-verb today.  They are the ANSWER to D1, so a
route state must not contain them: `writing_tools.py:16`/`:18` hold the top-level
names, and the discriminator keyword changes with depth (`operation` at the top,
`kind` one level down, `op.kind` a third level --- jev-assessment.md §2 D1)."""


@dataclass(frozen=True)
class RouteState:
    """What D1 is given: the request's own content, with the answer removed."""

    door: str = "tool"                 # "tool" | "http"
    mode: str = "work"
    payload: Mapping[str, Any] = field(default_factory=dict)
    target: str = ""
    path: str = ""                     # the HTTP path, for the http door
    note: str = ""                     # free text a caller already has, if any

    def stripped_payload(self) -> dict[str, Any]:
        """The payload without any key that names the sub-verb, at ANY depth.

        Top-level stripping is not enough and the corpus proves it: the sub-verb is
        one level down in `logical_plan_change.operation.kind` and two levels down in
        `structure_change.op.kind` (jev-assessment.md §2, D1 detail), so a state that
        stripped only the top level would hand the decider its own answer on those
        rows.  The strip is therefore by NAME at every depth, which costs a little
        genuine content --- a block's own `kind` is content, not a discriminator --- and
        the cost is accepted, because the alternative is a leak that would make every
        accuracy figure in this lane meaningless.  `test_the_route_state_never_carries_
        the_answer` checks it over all 662 corpus payloads.
        """
        return _strip(self.payload)

    def state_text(self) -> str:
        body = {"door": self.door, "mode": self.mode, "target": self.target,
                "payload": _shape(self.stripped_payload())}
        if self.path:
            body["path"] = self.path
        if self.note:
            body["note"] = self.note
        return json.dumps(body, sort_keys=True, ensure_ascii=False, default=str)


def _strip(value: Any) -> Any:
    """Remove every discriminator-named key from a nested structure."""
    if isinstance(value, Mapping):
        return {k: _strip(v) for k, v in value.items() if k not in _DISCRIMINATOR_KEYS}
    if isinstance(value, (list, tuple)):
        return [_strip(v) for v in value]
    return value


def _shape(value: Any, depth: int = 0) -> Any:
    """A value's shape, not its bytes: keys kept, long strings replaced by a type.

    The decision is about which home kind is being acted on, so a 40 KB chapter
    body contributes its type and nothing else.  This is the per-decision state
    composition the vendor's 32k cap and its context-rot warning both force
    (jev-assessment.md §3 D1, §4.2).
    """
    if depth > 3:
        return "<deep>"
    if isinstance(value, Mapping):
        return {str(k): _shape(v, depth + 1) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_shape(v, depth + 1) for v in value[:3]] + (["<more>"] if len(value) > 3 else [])
    if isinstance(value, str):
        if len(value) > 120:
            return "<str:%d>" % len(value)
        return value
    if isinstance(value, bool) or value is None:
        return value
    return value


# Feature sets.  The three exist to measure one thing: whether the grammar's own
# home vocabulary carries the routing signal better than the 20 old guard names
# the friction report counted (synthesis.md §1.1).
FEATURE_SETS = ("noguard", "names", "homes", "homes+shapes")


def features(state: RouteState, feature_set: str = "homes") -> tuple[str, ...]:
    """The binary features a head scores.  `feature_set` selects the vocabulary.

    * `noguard` --- payload key names and value types, with every old guard name
      dropped.  The control: what is left when identity names carry nothing.
    * `names` --- the same, plus `guard=<old name>` for each of the 22 names in
      `grammar.GUARD_NAMES` the payload speaks.  This is today's vocabulary.
    * `homes` --- the same, but each old guard name is REPLACED by the home kind(s)
      `grammar.GUARD_NAMES` resolves it to.  This is the grammar's vocabulary, and
      it is the default because it measured best (see `tests/routing_calibration`).
    * `homes+shapes` --- `homes` plus what each value LOOKS like (a `.tex` path, a
      `def:`-prefixed id, a 64-hex digest).  Kept as a named set rather than folded
      into the default because it measurably HURT: 0.389 against 0.413 on the same
      folds.  Correlated features on a Bernoulli naive-Bayes head cost more than the
      pattern adds, and the negative result stays in the table instead of being
      quietly dropped.
    """
    if feature_set not in FEATURE_SETS:
        raise ValueError("feature_set must be one of %r" % (FEATURE_SETS,))
    shapes = feature_set.endswith("+shapes")
    vocabulary = feature_set.split("+", 1)[0]
    out: list[str] = ["door=" + state.door, "mode=" + state.mode]
    if state.path:
        out.append("path=" + state.path)
    out.append("target=" + ("empty" if not state.target else
                            "path" if "/" in state.target else "id"))
    payload = state.stripped_payload()
    out.append("nkeys=%d" % min(len(payload), 8))
    for key, value in sorted(payload.items(), key=lambda kv: str(kv[0])):
        if key in grammar.GUARD_NAMES:
            if vocabulary == "noguard":
                continue
            if vocabulary == "homes":
                for home in grammar.GUARD_NAMES[key]:
                    out.append("home=" + home)
                continue
            out.append("guard=" + key)
            continue
        out.append("key=" + str(key))
        out.append("type:%s=%s" % (key, type(value).__name__))
        if shapes:
            out.extend("shape:%s=%s" % (key, p) for p in _value_patterns(value))
        if isinstance(value, Mapping):
            for sub in sorted(str(k) for k in value):
                out.append("sub=%s.%s" % (key, sub))
        elif isinstance(value, (list, tuple)) and value and isinstance(value[0], Mapping):
            for sub in sorted(str(k) for k in value[0]):
                out.append("item=%s.%s" % (key, sub))
    return tuple(sorted(set(out)))


_HEX = set("0123456789abcdef")


def _value_patterns(value: Any) -> tuple[str, ...]:
    """What a value LOOKS like, never what it says.

    A `.tex` path, a `def:`-prefixed node id and a 64-hex digest are three different
    home kinds wearing three different shapes, and the shape is information a caller
    already holds before it chooses a door.  None of these patterns can contain an
    operation name, so none of them leaks the answer; the one thing that would ---
    the discriminator key --- is removed before `features` is reached.
    """
    if isinstance(value, (list, tuple)):
        return ("list%d" % min(len(value), 4),) + (
            _value_patterns(value[0]) if value else ())
    if isinstance(value, Mapping):
        return ("map%d" % min(len(value), 4),)
    if not isinstance(value, str):
        return (type(value).__name__,)
    low = value.lower()
    out: list[str] = []
    if low.endswith(".tex"):
        out.append("tex")
    elif "." in low.rsplit("/", 1)[-1]:
        out.append("ext:" + low.rsplit(".", 1)[-1][:8])
    if "/" in low:
        out.append("path")
    if len(low) == 64 and set(low) <= _HEX:
        out.append("sha256")
    elif low.startswith("sha256:"):
        out.append("sha256-prefixed")
    elif ":" in low:
        out.append("prefixed:" + low.partition(":")[0][:16])
    out.append("len%d" % min(len(low) // 20, 4))
    return tuple(out)


_REFUSAL_WORDS = ("revision", "conflict", "stale", "changed", "consumed", "current",
                  "unknown", "missing", "required", "not exist", "outside", "no exact",
                  "unavailable", "unsupported", "before", "first", "failed", "http",
                  "must be", "enum", "use the", "refused", "scope", "range", "fresh")


def refusal_features(text: str) -> tuple[str, ...]:
    """The features D4 scores: lower-cased word presence over the refusal prose.

    Deliberately the same INPUT the live decision has --- `writing_tools.py:1591`
    tests four of these words and nothing else --- so the comparison is between two
    readings of one string, not between two different amounts of information.
    """
    low = (text or "").lower()
    out = ["w=" + w.replace(" ", "_") for w in _REFUSAL_WORDS if w in low]
    out.append("len=%d" % min(len(low) // 40, 6))
    tokens = [t.strip(".,;:'\"()") for t in low.split()]
    out.extend("t=" + t for t in sorted({t for t in tokens if 3 <= len(t) <= 14}))
    return tuple(sorted(set(out)))


# ---------------------------------------------------------------------------
# 3. Calibration: pool adjacent violators, in the standard library.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Calibration:
    """A monotone map from a head's raw top score to P(the choice is right).

    Fitted by pool-adjacent-violators (isotonic regression) on held-out
    (score, correct) pairs.  Each knot carries the COUNT of held-out rows behind
    it, because a reliability curve without counts is a picture, not a measurement.
    """

    knots: tuple[tuple[float, float, int], ...] = ()   # (score, calibrated, n)
    n: int = 0
    fitted_on: str = ""

    def __call__(self, score: float) -> float:
        if not self.knots:
            return float(score)
        best = self.knots[0][1]
        for edge, value, _count in self.knots:
            if score >= edge:
                best = value
            else:
                break
        return float(best)

    def bins(self, width: float = 0.1) -> list[dict[str, Any]]:
        out = []
        for i in range(int(round(1.0 / width))):
            lo, hi = i * width, (i + 1) * width
            rows = [k for k in self.knots if lo <= k[0] < hi]
            if rows:
                total = sum(r[2] for r in rows)
                out.append({"lo": round(lo, 3), "hi": round(hi, 3), "n": total,
                            "mean_calibrated": round(sum(r[1] * r[2] for r in rows) / total, 4)})
        return out


def fit_calibration(pairs: Sequence[tuple[float, bool]], *, fitted_on: str = "") -> Calibration:
    """Pool adjacent violators.  No dependency, no second implementation."""
    if not pairs:
        return Calibration(fitted_on=fitted_on)
    ordered = sorted(pairs, key=lambda p: p[0])
    blocks: list[list[float]] = []      # [sum_correct, count, score_at_left_edge]
    for score, correct in ordered:
        blocks.append([1.0 if correct else 0.0, 1.0, score])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            last = blocks.pop()
            blocks[-1][0] += last[0]
            blocks[-1][1] += last[1]
    knots = tuple((b[2], b[0] / b[1], int(b[1])) for b in blocks)
    return Calibration(knots=knots, n=len(ordered), fitted_on=fitted_on)


def expected_calibration_error(pairs: Sequence[tuple[float, bool]], width: float = 0.1) -> dict[str, Any]:
    """ECE with the per-bin counts printed beside it, never the scalar alone."""
    bins: list[dict[str, Any]] = []
    total = len(pairs)
    error = 0.0
    for i in range(int(round(1.0 / width))):
        lo, hi = i * width, (i + 1) * width
        rows = [p for p in pairs if (lo <= p[0] < hi) or (i == int(round(1 / width)) - 1 and p[0] == 1.0)]
        if not rows:
            continue
        mean_p = sum(p[0] for p in rows) / len(rows)
        frac = sum(1 for p in rows if p[1]) / len(rows)
        bins.append({"lo": round(lo, 2), "hi": round(hi, 2), "n": len(rows),
                     "mean_predicted": round(mean_p, 4), "observed_correct": round(frac, 4)})
        error += (len(rows) / total) * abs(mean_p - frac)
    return {"ece": round(error, 4), "n": total, "bins": bins}


# ---------------------------------------------------------------------------
# 4. The deciders.
# ---------------------------------------------------------------------------
class Decider(Protocol):
    """One decision: a distribution over the option labels given a state.

    Both arguments are passed to every decider, and the two implementations use
    different ones, which is stated here rather than discovered: `AdapterDecider`
    reads `state_text` (it is a model, the state is its document) and
    `PriorDecider` reads `feature_hint` (it is a fitted head over the features
    `features()`/`refusal_features()` derive from that same state).  Neither sees
    anything the other does not: `Decision.state_chars` is the length of the one
    state both are given.
    """

    name: str

    def ask(self, state_text: str, options: Sequence[str], instructions: str,
            feature_hint: Sequence[str] = ()) -> dict[str, float]:
        ...


@dataclass
class PriorDecider:
    """A fitted, dependency-free head: smoothed Bernoulli naive Bayes over features.

    This is the decider the calibration is measured on, because it can be refitted
    and re-run by anyone who checks out the commit --- no key, no vendor, no
    network.  `AdapterDecider` answers the same question through the MIT System One
    adapter so the two can be compared on the same held-out slice.
    """

    name: str = "prior"
    alpha: float = 0.6
    log_prior: dict[str, float] = field(default_factory=dict)
    log_likelihood: dict[str, dict[str, float]] = field(default_factory=dict)
    log_absent: dict[str, dict[str, float]] = field(default_factory=dict)
    vocabulary: tuple[str, ...] = ()
    trained_rows: int = 0

    def fit(self, rows: Sequence[tuple[Sequence[str], str]]) -> "PriorDecider":
        labels = sorted({label for _f, label in rows})
        vocab = sorted({f for feats, _l in rows for f in feats})
        self.vocabulary = tuple(vocab)
        self.trained_rows = len(rows)
        counts = {label: 0 for label in labels}
        present: dict[str, dict[str, int]] = {label: {} for label in labels}
        for feats, label in rows:
            counts[label] += 1
            bucket = present[label]
            for f in set(feats):
                bucket[f] = bucket.get(f, 0) + 1
        total = float(len(rows))
        self.log_prior = {l: math.log((counts[l] + self.alpha) / (total + self.alpha * len(labels)))
                          for l in labels}
        self.log_likelihood = {}
        self.log_absent = {}
        for label in labels:
            n = counts[label]
            lp, la = {}, {}
            for f in vocab:
                p = (present[label].get(f, 0) + self.alpha) / (n + 2 * self.alpha)
                lp[f] = math.log(p)
                la[f] = math.log(1.0 - p)
            self.log_likelihood[label] = lp
            self.log_absent[label] = la
        return self

    def scores(self, feats: Sequence[str]) -> dict[str, float]:
        if not self.log_prior:
            raise RuntimeError("PriorDecider.fit was never called")
        have = set(feats) & set(self.vocabulary)
        out = {}
        for label, prior in self.log_prior.items():
            lp, la = self.log_likelihood[label], self.log_absent[label]
            total = prior + sum(la.values())
            for f in have:
                total += lp[f] - la[f]
            out[label] = total
        return out

    def ask(self, state_text: str, options: Sequence[str], instructions: str,
            feature_hint: Sequence[str] = ()) -> dict[str, float]:
        raw = self.scores(feature_hint)
        raw = {k: v for k, v in raw.items() if k in set(options)} or raw
        top = max(raw.values())
        exp = {k: math.exp(v - top) for k, v in raw.items()}
        total = sum(exp.values()) or 1.0
        return {k: v / total for k, v in exp.items()}


@dataclass
class AdapterDecider:
    """The System One request shape, through the MIT adapter, on a local provider.

    `github.com/typesafe-ai/system-one-adapter-python` (MIT) is installed in a
    scratch venv under /tmp and is NOT jev: it emulates the request shape on an
    ordinary provider.  No account was created and no vendor key is used --- there
    is none in this environment --- so the provider is one already on this machine
    (`GET /authoring/providers` lists `codex` and `claude`), driven through its CLI
    by `tests/routing_calibration/claude_cli_provider.py`, which implements the
    adapter's own `SyncProvider` protocol.  `callable_` is injected so this module
    imports neither the adapter nor a subprocess module.
    """

    callable_: Any = None
    name: str = "adapter"

    def ask(self, state_text: str, options: Sequence[str], instructions: str,
            feature_hint: Sequence[str] = ()) -> dict[str, float]:
        if self.callable_ is None:
            raise RuntimeError(
                "AdapterDecider needs its `callable_` injected: this module never "
                "imports the adapter or a provider, so an advisor cannot acquire a "
                "network or a subprocess by importing laplace.native.routing.")
        return self.callable_(state_text, list(options), instructions)


# ---------------------------------------------------------------------------
# 5. The two decisions.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Decision:
    question: str
    choice: str
    probability: float                  # calibrated P(choice is right)
    raw_probability: float              # the head's own top mass
    confidence: float                   # the vendor's statistic: spread of the distribution
    abstained: bool
    threshold: float
    n_options: int
    state_chars: int
    latency_ms: float
    decider: str
    distribution: Mapping[str, float] = field(default_factory=dict)

    def as_row(self) -> dict[str, Any]:
        return {"question": self.question, "choice": self.choice,
                "probability": round(self.probability, 4),
                "raw_probability": round(self.raw_probability, 4),
                "confidence": round(self.confidence, 4), "abstained": self.abstained,
                "threshold": self.threshold, "n_options": self.n_options,
                "state_chars": self.state_chars, "latency_ms": round(self.latency_ms, 3),
                "decider": self.decider}


def spread_confidence(distribution: Mapping[str, float]) -> float:
    """The vendor's definition: 1.0 when all mass is on one option, low when even.

    `docs.typesafe.ai/confidence.md` describes confidence as a derived statistic of
    the distribution's shape, not a second signal (jev-assessment.md §1).  This is
    normalised negative entropy, which has exactly that behaviour, and it is
    reported BESIDE `probability` rather than instead of it: the calibration is
    fitted on the top mass, because that is the quantity a reliability curve is
    about.
    """
    values = [p for p in distribution.values() if p > 0]
    if len(values) <= 1:
        return 1.0
    entropy = -sum(p * math.log(p) for p in values)
    return max(0.0, min(1.0, 1.0 - entropy / math.log(len(distribution))))


DEFAULT_ROUTE_THRESHOLD = 0.5
DEFAULT_RESOLVER_THRESHOLD = 0.5


def route(state: RouteState, *, decider: Decider, calibration: Calibration | None = None,
          threshold: float = DEFAULT_ROUTE_THRESHOLD, feature_set: str = "homes",
          options: Sequence[tuple[str, str]] | None = None) -> Decision:
    """D1.  Which `(verb, concept)` pair is this request?  Never executes anything."""
    pairs = tuple(options) if options is not None else route_options()
    labels = ["%s %s" % (v, c) for v, c in pairs]
    text = state.state_text()
    feats = features(state, feature_set)
    started = time.perf_counter()
    distribution = decider.ask(text, labels, _ROUTE_INSTRUCTIONS, feats)
    latency = (time.perf_counter() - started) * 1000.0
    choice = max(distribution, key=lambda k: distribution[k]) if distribution else ""
    raw = float(distribution.get(choice, 0.0))
    calibrated = calibration(raw) if calibration is not None else raw
    return Decision(question="D1-route", choice=choice, probability=calibrated,
                    raw_probability=raw, confidence=spread_confidence(distribution),
                    abstained=calibrated < threshold, threshold=threshold,
                    n_options=len(labels), state_chars=len(text), latency_ms=latency,
                    decider=getattr(decider, "name", type(decider).__name__),
                    distribution=distribution)


_ROUTE_INSTRUCTIONS = (
    "Choose the one grammar pair `<verb> <object>@<altitude>` this request is. "
    "The verb is the gate the act must pass; the concept is the home kind being "
    "acted on, at the grain it is acted on. Answer the question as written.")

_RESOLVER_INSTRUCTIONS = (
    "Choose the one refusal kind this refusal is. `identity-stale`: a home the "
    "caller named moved. `unknown-home`: the home the request addresses is not "
    "there. `state-not-reached`: a third home is not yet in the state this act "
    "requires. `shape`: the request's own shape is wrong.")


def classify(error_text: str, *, decider: Decider, calibration: Calibration | None = None,
             threshold: float = DEFAULT_RESOLVER_THRESHOLD,
             options: Sequence[str] | None = None) -> Decision:
    """D4.  Which refusal kind is this, and therefore which cure does the caller need?"""
    labels = list(options) if options is not None else list(resolver_options())
    feats = refusal_features(error_text)
    started = time.perf_counter()
    distribution = decider.ask(error_text, labels, _RESOLVER_INSTRUCTIONS, feats)
    latency = (time.perf_counter() - started) * 1000.0
    choice = max(distribution, key=lambda k: distribution[k]) if distribution else ""
    raw = float(distribution.get(choice, 0.0))
    calibrated = calibration(raw) if calibration is not None else raw
    return Decision(question="D4-classify", choice=choice, probability=calibrated,
                    raw_probability=raw, confidence=spread_confidence(distribution),
                    abstained=calibrated < threshold, threshold=threshold,
                    n_options=len(labels), state_chars=len(error_text or ""),
                    latency_ms=latency,
                    decider=getattr(decider, "name", type(decider).__name__),
                    distribution=distribution)


# The cure each refusal kind needs.  Not a resolver VALUE --- `grammar.require`
# produces that, and `needed` IS the resolver (GRAMMAR.md §5) --- but the read a
# caller performs to obtain it.  This is the typed replacement for the substring
# ladder at `src/laplace/writing_tools.py:1404-1551`, whose target is chosen by
# twelve `operation` tests rather than by the kind of refusal it is.
RESOLVER_CURE: dict[str, str] = {
    "identity-stale": "re-read the home named in refused.homes[].read and resend "
                      "refused.needed.expected; grammar.require already holds the value",
    "unknown-home": "the home id is wrong, not stale: read the container that lists it "
                    "(the home kind's own read in GRAMMAR.md §2) and address an id it returns",
    "state-not-reached": "a fresher token cannot cure this; read the third home's state "
                         "until it is terminal (research_surface.py:1245-1248 is the measured case)",
    "shape": "the request's shape is wrong: fetch the concept's payload schema, not an "
             "identity --- this is the one kind a token cannot fix",
}


@dataclass(frozen=True)
class Advice:
    """What the pre-call advisor returns.  A suggestion, never an act."""

    request: grammar.Request | None
    decision: Decision
    cure: str = ""
    said: str = ""

    @property
    def abstained(self) -> bool:
        return self.request is None

    def as_row(self) -> dict[str, Any]:
        return {"request": None if self.request is None else {
                    "verb": self.request.verb, "concept": self.request.concept,
                    "target": self.request.target},
                "decision": self.decision.as_row(), "cure": self.cure, "said": self.said}


def advise(state: RouteState, *, decider: Decider, calibration: Calibration | None = None,
           threshold: float = DEFAULT_ROUTE_THRESHOLD, feature_set: str = "homes",
           by: str = "", expected: Sequence[str] = ()) -> Advice:
    """The pre-call advisor.  Returns a suggested `grammar.Request` or abstains.

    It cannot be the thing that authorises a write.  It builds a `Request` ---
    which validates its own verb, concept, pair and payload against the grammar ---
    and hands it back.  The caller still presents its tokens, the owner still
    compares them, and if the advisor is wrong the owner refuses exactly as it does
    today.  When the calibrated probability is below `threshold` the advisor
    returns `request=None`, which is the one thing the live path cannot do: today a
    wrong route costs a turn plus the refusal's contract, up to 32,611 characters
    (`writing_contracts.py:107`, measured at `writing_tools.py:1547`'s 9,500-char
    truncation boundary).
    """
    decision = route(state, decider=decider, calibration=calibration,
                     threshold=threshold, feature_set=feature_set)
    if decision.abstained or not decision.choice:
        return Advice(request=None, decision=decision,
                      said="abstained at %.2f < %.2f: the caller routes as it does today"
                           % (decision.probability, threshold))
    verb, concept = decision.choice.split(" ", 1)
    try:
        request = grammar.Request(verb=verb, concept=concept, target=state.target,
                                  expected=tuple(expected),
                                  payload=state.stripped_payload(), by=by)
    except ValueError as exc:
        return Advice(request=None, decision=decision,
                      said="the grammar refused the suggestion, so it is not made: %s" % exc)
    return Advice(request=request, decision=decision,
                  said="suggested %s at p=%.2f over %d declared pairs"
                       % (decision.choice, decision.probability, decision.n_options))


def advise_refusal(error_text: str, *, decider: Decider,
                   calibration: Calibration | None = None,
                   threshold: float = DEFAULT_RESOLVER_THRESHOLD) -> Advice:
    """The D4 advisor: the refusal's kind and the read that cures it, or an abstention."""
    decision = classify(error_text, decider=decider, calibration=calibration,
                        threshold=threshold)
    if decision.abstained or not decision.choice:
        return Advice(request=None, decision=decision,
                      said="abstained: return the whole contract, which is what "
                           "writing_tools.py:1547 already does by size")
    return Advice(request=None, decision=decision,
                  cure=RESOLVER_CURE.get(decision.choice, ""),
                  said="refusal kind %s at p=%.2f" % (decision.choice, decision.probability))


# ---------------------------------------------------------------------------
# 6. The cost rule the abstain threshold is chosen against.
# ---------------------------------------------------------------------------
# Measured in this worktree, both reproducible by `tests/routing_calibration/costs.py`:
#   * one provider turn carries the operating brief before any content:
#     18,158 characters for `synthetics-foundations`
#     (`writing_operating.prompt(writing_operating.build(...))`, sent as the whole
#     system prompt at `src/laplace/writing_provider.py:1275-1015`).
#   * recovering from a wrong route costs that operation's exact contract:
#     73 operations, 168,912 characters in total, median 985, max 32,611
#     (`concept_change`), from `src/laplace/writing_contracts.py:107`.
TURN_CHARS = 18158
CONTRACT_CHARS_MEDIAN = 985
CONTRACT_CHARS_MAX = 32611
# What a refusal actually DELIVERS today: `failure_response` embeds the operation's
# contract and drops the nested schema above this many characters
# (`src/laplace/writing_tools.py:1392`), handing back a `full_schema` pointer instead.
# So the price of a refusal that names no kind is bounded by this, while the price of
# CURING a wrong decision is the whole contract, because the cure is the exact `help`
# call and that is not truncated.
FAILURE_RESPONSE_BOUND = 9500


def bounded_delivery(contract_chars: int) -> int:
    return min(int(contract_chars), FAILURE_RESPONSE_BOUND)


def realised_cost(wrong_contract_chars: Sequence[int]) -> int:
    """The price actually paid by the wrong routes a threshold let through."""
    return int(sum(wrong_contract_chars))


def within_one_turn(wrong_contract_chars: Sequence[int], turn_chars: int = TURN_CHARS) -> bool:
    return realised_cost(wrong_contract_chars) < turn_chars
