"""Obligation-witness reading, pass 0: the question compiles to obligations and an operator kind (zero model calls).

DESIGN_STAGE3 §2.2 "Pass 0, compile" (evidence/BENCH_RECOVERY_2026-11-09/stage2/DESIGN_STAGE3.md). One compiler per
dataset, each the existing organ extended to emit the obligation list it already computes internally:

  multihoprag    query.SlotCompiler (query.py:194-362): one obligation per facet of the imported outlet/date grammar,
                 slots = the facet's bound outlet, day (publication day exact, event day a declared window) and the
                 registered entities R1's canonicaliser finds in the facet (ACTIVATION_CONFIG); an unbound facet axis is
                 '<unknown>'. The exact (outlet, date) binding is the one piece here only this system has (§2.1(a)).
  frames         frames_corpus.compile_question (frames_corpus.py:1634-1643, entity_slots 1059-1088): the question's
                 constraint clauses in its own words, then each comparison / list operand and each relative or
                 subordinate hop as its own obligation (frames_obligation_needs), each carrying the registered entities
                 it names; this is decomposition-as-prompt-data plus registry extraction, the field's practice on
                 FRAMES (said plainly, §2.1(a)).
  longmemeval_s  the question text and question_date: count/latest questions get one open ('each') obligation; order
                 questions and spans between two events one dated obligation per side or event; a span to the question
                 date one obligation for its event; an age at an event the stated age and the event; no registry entity
                 binds the counted class on LongMem (P6 §6), so entity slots stay '<unknown>' unless the caller supplies
                 a resolver.

THE OPERATOR KIND is chosen by a declared rule over the dataset's gold-blind stratum label (MultiHop question_type,
LongMem raw question_type, FRAMES the rarest reasoning label; datasets.py:159, 203, 384), refined only inside a
stratum by wording (temporal -> order | change, multi-session -> count | duration). Two deviations from the design's
table, both made so that no answerability signal reaches the reader:
  * MultiHop null_query routes to 'bridge' like inference_query (the design wrote 'lookup with abstention allowed');
    every null_query gold is 'Insufficient information', so a kind used only for null queries would tell the reader
    the answer. Abstention is allowed for every kind by the instruction, so nothing is lost.
  * LongMem routes on the RAW question_type, never on the loader's 'abstention' relabel of '_abs' ids (that suffix
    marks unanswerable questions).
Conventional default refused: a surface-form router over all classes (P6 §2 measured 22% misrouting on LongMem).

An obligation's cardinality is 'one' (exactly one witness row) or 'each' (one row per distinct instance found: the
operands of count / latest). The design's schema says one row per obligation; a count needs as many rows as there are
operands, so 'each' is the one declared extension and the parser enforces both.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

from relational import polarity as pol

UNKNOWN = pol.UNKNOWN
DATASETS = ("multihoprag", "frames", "longmemeval_s")
KINDS = ("compare", "order", "change", "count", "latest", "duration", "bridge", "chain", "lookup", "recommend",
         "extract")
# kinds whose answer the operator module can compute from typed witnesses (recorded beside the reader's answer)
COMPUTED_KINDS = ("order", "change", "count", "latest", "duration")
AUX = re.compile(r"^\s*(is|was|were|are|did|does|do|has|have|had|can|could|will|would|should|shall|might|may)\b", re.I)

# ---------------------------------------------------------------------------------------------- data


@dataclass
class Obligation:
    id: str
    need: str                                   # the side of the question this witnesses, in the question's words
    slots: dict                                 # {"source", "date", "entity"}: a bound value or '<unknown>'
    cardinality: str = "one"                    # 'one' | 'each'
    window: list = field(default_factory=list)  # days (YYYY-MM-DD) or months (YYYY-MM) the date slot admits; [] = any

    def prompt_view(self) -> dict:
        """What the reader sees (the window is the compiler's, used by growth resolution, not shown)."""
        return {"id": self.id, "need": self.need, "slots": dict(self.slots), "cardinality": self.cardinality}


@dataclass
class Compiled:
    dataset: str
    question: str
    question_date: str | None
    stratum: str
    kind: str
    over: list                                  # obligation ids the operator needs
    frame: dict                                 # operator parameters (direction, yes/no frame, unit): internal
    obligations: list                           # [Obligation]
    route: dict                                 # which rule chose the kind, on which input

    def operator_view(self) -> dict:
        return {"kind": self.kind, "over": list(self.over)}

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


def _slots(source=UNKNOWN, date=UNKNOWN, entity=UNKNOWN) -> dict:
    return {"source": source or UNKNOWN, "date": date or UNKNOWN, "entity": entity or UNKNOWN}


AUX_AFTER_CLAUSE = re.compile(r"[,;]\s+(is|was|were|are|did|does|do|has|have|had|can|could|will|would|should)\s",
                              re.I)
WH_START = re.compile(r"^\s*(who|what|which|when|where|why|how)\b", re.I)


def yes_no(question: str) -> bool:
    """A yes/no question opens with an auxiliary verb, or opens with a leading clause and then asks with one
    ('Between the X report ... and the Y report ..., was there ...?'); a wh-question is never yes/no."""
    if WH_START.match(question):
        return False
    return bool(AUX.match(question) or AUX_AFTER_CLAUSE.search(question))


# ---------------------------------------------------------------------------------------------- wording rules
CHANGE_WORDS = re.compile(r"\b(consisten\w*|change\w*|same|maintain\w*|remain\w*|unchanged|shift\w*|alter\w*|differ\w*"
                          r"|align\w*|agree\w*|contradict\w*|revers\w*)\b", re.I)
CONSISTENCY_FRAME = re.compile(r"\b(consisten\w*|same|maintain\w*|remain\w*|unchanged|align\w*|agree\w*|no change)\b",
                               re.I)
ORDER_WORDS = re.compile(r"\b(before|after|prior|earlier|later|first|preced\w*|follow\w*|subsequent\w*|last)\b", re.I)
BEFORE = re.compile(r"\b(before|prior to|earlier than|preced\w*|first)\b", re.I)
AFTER = re.compile(r"\b(after|later than|subsequent\w*|follow\w*|last|most recent\w*|latest)\b", re.I)
NEGATED = re.compile(r"\b(fail(?:ed|s)? to|not|never|n't)\b", re.I)
DURATION_UNIT = re.compile(r"\bhow many (days|weeks|months|years|hours|minutes)\b|\bhow long\b", re.I)
AGO = re.compile(r"\b(ago|since|so far|until now|by now)\b", re.I)
SUM_WORDS = re.compile(r"\bhow much\b|\bin total\b|\btotal\b|\bcombined\b|\baltogether\b|\bsum\b", re.I)
UNIT_NAMES = ("days", "weeks", "months", "years", "hours", "minutes")


def news_kind(stratum: str, question: str) -> tuple[str, dict]:
    if stratum == "comparison_query":
        return "compare", {}
    if stratum == "temporal_query":
        if CHANGE_WORDS.search(question) or not ORDER_WORDS.search(question):
            return "change", {"yes_means": "unchanged" if CONSISTENCY_FRAME.search(question) else "changed",
                              "yes_no": yes_no(question)}
        return "order", _order_frame(question)
    if stratum in ("inference_query", "null_query"):
        return "bridge", {}
    raise ValueError(f"unknown multihoprag stratum {stratum!r}")


def _order_frame(question: str) -> dict:
    if BEFORE_OR_AFTER.search(question):
        return {"direction": "before", "yes_no": False, "before_or_after": True, "negated": False}
    direction = "after" if (AFTER.search(question) and not BEFORE.search(question)) else "before"
    return {"direction": direction, "yes_no": yes_no(question), "negated": bool(NEGATED.search(question))}


# 'How old was I when Alex was born?': an age at an event is the user's stated age (a number with the date it held)
# carried to the event's date; with no event clause the event is the question date. Without this rule the question fell
# to multi-session 'count' (judge round 1, defect 4).
AGE = re.compile(r"\bhow old\s+(?:was|am|will|would|were)\s+I\b(?:\s+be)?(?:\s+(?:when|on|at|by)\s+(?P<event>.+?))?\s*\??\s*$",
                 re.I)
# 'How many years older am I than when I graduated?' is the time from that event to the question date
OLDER_THAN_WHEN = re.compile(r"\b(?:older|younger)\b.*?\bthan\s+when\s+(?P<event>.+?)\s*\??\s*$", re.I)
# 'How many days did I spend on camping trips this year?' adds up stated durations (one per trip); it is not a span
# between two dated events, so it is a summed count with the unit, not a date difference
SPENT = re.compile(r"\b(spend|spent|in total|total|combined|altogether)\b", re.I)


def longmem_kind(stratum: str, question: str) -> tuple[str, dict]:
    q = question
    if stratum == "knowledge-update":
        return "latest", {}
    if stratum in ("multi-session", "temporal-reasoning") and AGE.search(q):
        return "duration", {"unit": "years", "anchor": "age"}
    if stratum == "multi-session":
        if DURATION_UNIT.search(q) and SPENT.search(q):
            return "count", {"aggregate": "sum", "unit": _duration_frame(q)["unit"]}
        if DURATION_UNIT.search(q):
            return "duration", _duration_frame(q)
        return "count", {"aggregate": "sum" if SUM_WORDS.search(q) else "distinct"}
    if stratum == "temporal-reasoning":
        if DURATION_UNIT.search(q) or AGO.search(q) or OLDER_THAN_WHEN.search(q):
            return "duration", _duration_frame(q)
        if ORDER_WORDS.search(q):
            return "order", _order_frame(q)
        return "lookup", {}
    if stratum == "single-session-preference":
        return "recommend", {}
    if stratum in ("single-session-user", "single-session-assistant"):
        return "lookup", {}
    raise ValueError(f"unknown longmemeval_s question_type {stratum!r} (give the raw question_type, never 'abstention')")


def _duration_frame(question: str) -> dict:
    m = re.search(r"\bhow many (days|weeks|months|years|hours|minutes)\b", question, re.I)
    unit = m.group(1).lower() if m else "days"
    # 'since X when Y' / 'since X until Y' is a span between two events, not a span to the question date
    two_events = re.search(r"\bsince\b.+\b(?:when|until|till|before|by the time)\b", question, re.I)
    anchored = (AGO.search(question) or OLDER_THAN_WHEN.search(question)) and not two_events
    return {"unit": unit, "anchor": "question_date" if anchored else "between"}


def wording_kind(dataset: str, question: str) -> tuple[str, dict]:
    """Sensitivity router that reads only the question text (no stratum); never the default (P6 §2: 22% misroutes)."""
    if dataset == "frames":
        return "chain", {}
    if dataset == "multihoprag":
        if re.search(r"\b(both|similar|while|whereas|compared|discrepancy|same as)\b", question, re.I):
            return "compare", {}
        if CHANGE_WORDS.search(question) and ORDER_WORDS.search(question):
            return "change", {"yes_means": "unchanged" if CONSISTENCY_FRAME.search(question) else "changed",
                              "yes_no": yes_no(question)}
        if ORDER_WORDS.search(question) and yes_no(question):
            return "order", _order_frame(question)
        return "bridge", {}
    if DURATION_UNIT.search(question):
        return "duration", _duration_frame(question)
    if re.search(r"\bhow many\b", question, re.I) or SUM_WORDS.search(question):
        return "count", {"aggregate": "sum" if SUM_WORDS.search(question) else "distinct"}
    if re.search(r"\b(currently|now|latest|most recent|still)\b", question, re.I):
        return "latest", {}
    if re.search(r"\b(recommend|suggest|any tips|ideas)\b", question, re.I):
        return "recommend", {}
    if ORDER_WORDS.search(question):
        return "order", _order_frame(question)
    return "lookup", {}


# ---------------------------------------------------------------------------------------------- news
_NEWS = {}


def _news_compiler():
    if "c" not in _NEWS:
        from relational import query as Q
        _NEWS["c"] = Q.compiler()
        _NEWS["Q"] = Q
    return _NEWS["c"], _NEWS["Q"]


def _outlet_spans(question: str, sources) -> list[tuple[int, int, str]]:
    """The imported grammar's outlet mentions (news_projection.query_facets lines 111-128), positions only."""
    lower = question.casefold()
    mentions = []
    for source in sources:
        aliases = {source.casefold().strip()}
        if "|" in source:
            aliases.add(source.split("|", 1)[0].casefold().strip())
        if source.casefold().startswith("the "):
            aliases.add(source[4:].casefold())
        for alias in aliases:
            if len(alias) < 2:
                continue
            for m in re.finditer(r"(?<!\w)" + re.escape(alias) + r"(?!\w)", lower):
                mentions.append((m.start(), m.end(), source))
    mentions.sort(key=lambda x: (x[0], -(x[1] - x[0])))
    clean = []
    for item in mentions:
        if not clean or item[0] >= clean[-1][1]:
            clean.append(item)
    return clean


def _side_text(question: str, spans, facet_source, facet_day, used: set) -> str:
    """The question's words for one facet: from its outlet mention to the next outlet mention, trimmed."""
    from relational.query import _dates_in
    cands = []
    for i, (start, _end, source) in enumerate(spans):
        if i in used or source != facet_source:
            continue
        right = spans[i + 1][0] if i + 1 < len(spans) else len(question)
        local = question[start:right]
        dated = facet_day is not None and facet_day in _dates_in(local)
        cands.append((0 if dated else 1, i, local))
    for _rank, i, local in sorted(cands):
        used.add(i)
        # open at the start of the clause holding the mention ("the article from Fortune ..."), not at the outlet
        prev_end = spans[i - 1][1] if i > 0 else 0
        lead = question[prev_end:spans[i][0]]
        cut_at = max((m.end() for m in re.finditer(r",\s+|;\s+|\b(?:and|while|whereas|but|between)\s+", lead, re.I)),
                     default=0 if i == 0 else len(lead))
        local = lead[cut_at:] + local
        # trim a trailing connector clause ("..., and the article from") and, on the last side, the question clause
        local = re.sub(r"[,;]?\s+(?:and|or|while|whereas|but)\b(?:\s+\S+){0,5}\s*$", "", local, flags=re.I)
        local = re.sub(r"[\s,;]*(and|or|while|whereas|but)?\s*(the|a|an)?\s*$", "", local, flags=re.I)
        cut = re.search(r",\s+(was|is|did|does|do|are|were|has|have|which|who|what)\b", local, re.I)
        if cut and i + 1 == len(spans):
            local = local[:cut.start()]
        local = local.strip(" ,;?")
        if len(local.split()) >= 3:
            return local
        break
    return question.strip()


def compile_news(question: str, stratum: str, *, route_on: str = "stratum") -> Compiled:
    comp, Q = _news_compiler()
    facets = comp.compile(question, config=Q.ACTIVATION_CONFIG)
    spans = _outlet_spans(question, comp.sources)
    used: set = set()
    obligations, seen = [], set()
    for f in facets:
        t_fine, t_coarse = f.slot("t_fine"), f.slot("t_coarse")
        labels = comp.labels("e_subj", f.slot("e_subj").allowed) or []
        side = _side_text(question, spans, f.source, f.day, used) if f.source else question.strip()
        # one obligation per dated window the compiler bound for this facet: the grammar binds ONE day per outlet
        # facet and query.py joins every further date in the facet's text to its window (query.py:233-252); each
        # such date is a side of a temporal question, so each becomes its own obligation
        dated = []
        if t_fine.allowed is not None and t_fine.evidence:
            for ev in t_fine.evidence:
                lo, hi = ev["window"]
                dated.append((lo if lo == hi else f"{lo}..{hi}", _days(lo, hi), ev["day"]))
        elif t_coarse.allowed is not None:
            months = [comp.vocab["t_coarse"][i] for i in t_coarse.allowed]
            dated.append((",".join(months), months, None))
        else:
            dated.append((UNKNOWN, [], None))
        for date, window, day in dated:
            key = (f.source, date)
            if key in seen:
                continue
            seen.add(key)
            need = side if len(dated) == 1 else _date_clause(question, day) or side
            obligations.append(Obligation(f"o{len(obligations) + 1}", need,
                                          _slots(f.source or UNKNOWN, date, "; ".join(labels) or UNKNOWN), "one",
                                          sorted(set(window))))
    if not obligations:
        obligations = [Obligation("o1", question.strip(), _slots(), "one", [])]
    split = before_or_after_sides(question)
    kind, frame = news_kind(stratum, question) if route_on == "stratum" else wording_kind("multihoprag", question)
    if not split and kind in ("compare", "change", "order") and len(obligations) == 1:
        split = compare_sides(question)
    if split and len(obligations) == 1:
        base = obligations[0]
        obligations = [Obligation(f"o{i + 1}", t, _side_slots(base.slots, t), "one", list(base.window))
                       for i, t in enumerate(split)]
    if not obligations:
        obligations = [Obligation("o1", question.strip(), _slots(), "one", [])]
    return Compiled("multihoprag", question, None, stratum, kind, [o.id for o in obligations], frame, obligations,
                    {"rule": route_on, "input": stratum if route_on == "stratum" else "question text",
                     "compiler": "query.SlotCompiler ACTIVATION_CONFIG (query.py:191, 338-362)",
                     "facets": len(facets)})


def _side_slots(slots: dict, side: str) -> dict:
    """A split side keeps the facet's outlet and date; its entity slot keeps only the facet's entities its own words
    name (all of them when it names none)."""
    ents = [e for e in str(slots.get("entity", UNKNOWN)).split("; ") if e != UNKNOWN]
    mine = [e for e in ents if e.casefold() in side.casefold()]
    return {**slots, "entity": "; ".join(mine or ents) or UNKNOWN}


def _date_clause(question: str, day: str | None) -> str | None:
    """The clause of the question that holds ``day`` (month-name or ISO form), bounded by clause punctuation."""
    if not day:
        return None
    import datetime as dt
    d = dt.date.fromisoformat(day)
    forms = [f"{d.strftime('%B')} {d.day}, {d.year}", f"{d.strftime('%B')} {d.day} {d.year}", day,
             f"{d.strftime('%B')} {d.day}"]
    for form in forms:
        i = question.find(form)
        if i >= 0:
            left = max(question.rfind(",", 0, max(0, i - 2)), question.rfind(";", 0, i), -1) + 1
            right_c = [j for j in (question.find(",", i + len(form) + 1), question.find("?", i)) if j >= 0]
            clause = question[left:min(right_c) if right_c else len(question)].strip(" ,;?")
            return clause if len(clause.split()) >= 3 else None
    return None


BEFORE_OR_AFTER = re.compile(r"\s+(before or after|after or before)\s+", re.I)

# Two sides of a comparison that the outlet grammar binds to ONE facet (both sides from the same outlet: 8 of the 24
# comparison questions in P4's 40 compile to a single obligation). One declared rule list, tried in order; the first
# connective found splits the question; a trailing alternative clause (', or do they ...') is cut from the second side.
COMPARE_SPLITS = (
    re.compile(r",?\s+compared\s+(?:to|with)\s+", re.I),
    re.compile(r",?\s+align(?:s|ed)?\s+with\s+", re.I),
    re.compile(r"\b(?:same|similar|different)\b[^,?]*?(\s+as\s+)", re.I),
    re.compile(r",\s+and\s+(?=(?:did|does|do|is|was|were|has|have|had)\b)", re.I),
    re.compile(r"\s+and\s+(?=[^,?]*?\bboth\b)", re.I),
)
TRAILING_ALTERNATIVE = re.compile(r",?\s+or\s+(?:are|is|do|does|did|was|were|have|has)\b.*$", re.I)


def compare_sides(question: str) -> list:
    """[side A, side B] in the question's words when one declared connective splits it, else []."""
    q = question.strip()
    for rx in COMPARE_SPLITS:
        m = rx.search(q)
        if not m:
            continue
        cut_start, cut_end = (m.start(1), m.end(1)) if m.groups() else (m.start(), m.end())
        a = q[:cut_start].strip(" ,?")
        b = TRAILING_ALTERNATIVE.sub("", q[cut_end:]).strip(" ,?")
        b = re.sub(r"\s+both\b.*$", "", b, flags=re.I).strip(" ,?") if "both" in b.casefold() else b
        b = re.sub(r"[,\s]+(?:with|and|or|while|whereas)$", "", b, flags=re.I).strip(" ,?")
        if len(a.split()) >= 3 and len(b.split()) >= 3:
            return [a, b]
    return []


def before_or_after_sides(question: str) -> list:
    """'Did X report on A before or after B?' -> [A-side, B-side] (the two events whose order is asked)."""
    m = BEFORE_OR_AFTER.search(question)
    if not m:
        return []
    a, b = question[:m.start()].strip(" ,"), question[m.end():].strip(" ?,")
    return [a, b] if len(a.split()) >= 2 and len(b.split()) >= 2 else []


def _days(lo: str, hi: str) -> list[str]:
    import datetime as dt
    a, b = dt.date.fromisoformat(lo), dt.date.fromisoformat(hi)
    return [(a + dt.timedelta(days=k)).isoformat() for k in range((b - a).days + 1)]


# ---------------------------------------------------------------------------------------------- FRAMES
_FR = {}


def _frames_compiler():
    if "doc" not in _FR:
        from relational import frames_corpus as F
        _FR["doc"], _FR["stats"], _FR["F"] = F.compiler_doc(), F._case_stats(), F
    return _FR["doc"], _FR["stats"], _FR["F"]


_ABBREV_END = re.compile(r"(?:^|[\s(])(?:[A-Z]|St|Dr|Mr|Mrs|Ms|Jr|Sr|vs|No|Mt|Ft|U\.S|U\.K|A\.D|B\.C)\.$")
# ... unless what follows opens a new sentence ('built by a king in 460 A.D. What is the name ...')
_SENTENCE_START = re.compile(r"^(?:What|Who|Whom|Whose|Which|When|Where|Why|How|Is|Was|Were|Are|Did|Does|Do|Can|"
                             r"Could|Would|Will|Has|Have|Had|The|A|An|It|He|She|They|This|That|There|His|Her|Their|"
                             r"I|In|On)\b")


def frames_clauses(question: str) -> list[str]:
    """The question's constraint clauses in its own words: split at ',', ';', ':' and sentence ends, then fragments
    shorter than four words are joined to the clause before them (a date or a name is not a constraint alone)."""
    raw = [p.strip() for p in re.split(r"(?<=[,;:?.!])\s+|(?<=[.?!][\"”’'])\s+", question.strip()) if p.strip()]
    # an initial or abbreviation ('Fred J. Rath', 'U.S. coin', 'Wall St. Journal', '460 A.D.') ends no clause
    parts: list[str] = []
    for p in raw:
        if parts and _ABBREV_END.search(parts[-1]) and not _SENTENCE_START.match(p):
            parts[-1] = f"{parts[-1]} {p}"
        else:
            parts.append(p)
    out: list[str] = []
    for p in parts:
        if out and len(p.split()) < 4:
            out[-1] = f"{out[-1]} {p}"
        else:
            out.append(p)
    if len(out) > 1 and len(out[0].split()) < 4:
        out[1] = f"{out[0]} {out[1]}"
        out = out[1:]
    return [c.strip(" ,;:") for c in out] or [question.strip()]


# ---- FRAMES decomposition (judge round 1, defect 2: 30 of the 60 E5 questions compiled to ONE obligation, e.g. 'How old
# was the journalist who reviewed the first iPad ... when the first iPad came out?' and 'difference in original sale
# price between "Northern River" and "Northern Lake"', so the witness table could not name the missing hop and growth
# could not aim at it). Declared rules over the question's words, in this order, each gold-blind:
#   1. clause punctuation (frames_clauses), with the commas inside an enumeration of registered entities protected;
#   2. operands: 'between A and B' and 'head, A or B' give one obligation per operand ('head: A'); an enumeration of
#      registered entities joined only by commas / and / or ('Will Carling, Chris Oti, and Andy Mullins') gives one
#      obligation per entity, the enumeration replaced by that entity in the clause's words;
#   3. hops: a split before a relative or subordinate word (who, whom, whose, which, that, where, when, while), before a
#      comparison's second side ('than ...', 'in common with ...'), before a temporal anchor ('in the same year ...',
#      'three years before ...') and before an agentive reduced relative ('directed by ...', 'founded by ...');
#   4. a piece with fewer than two content words is merged into its neighbour, and an answer-format directive ('Round
#      your answer to the nearest ten.', 'Give the answer in morse code.') is not an evidence obligation: it stays in
#      the question and never aims growth.
# This is decomposition-as-prompt-data, the field's practice on FRAMES; what is ours is only that an unwitnessed piece
# aims the second pass.
_STOP = frozenset((
    "a an the and or but of in on at to for from by with as is was were are be been being am do does did has have had "
    "it its it's this that these those there here what which who whom whose when where why how many much can could "
    "would should will shall may might must you your me my i i'm we our us he his him she her they their them please "
    "tell know if than then so such also all any some one each same year time first answer").split())
_THAT_BLOCK = frozenset((
    "so such now than is was are were be said says say know knew think thought believe heard hear fact means mean ensure "
    "note given assuming except provided sure claim claimed show shows showed found find reported noted stated "
    "realize realized given that").split())
_WH_BLOCK = frozenset("know tell me ask asked wonder wondering about whether".split())
_PREP = frozenset("from in of at to by for with on into onto".split())
_AUX_BEFORE = frozenset("is was were are be been being has have had get got become became".split())
_THAN_BLOCK = frozenset("more less fewer rather other no greater".split())
_HOP = re.compile(
    r"\b(?P<wh>who|whom|whose|which|where|when|while|if)\s"
    r"|\b(?P<that>that)\s"
    r"|\b(?P<than>than)\s"
    r"|\b(?P<common>in\s+common\s+with)\b"
    r"|\b(?P<year>(?:in|during)\s+the\s+(?:same\s+)?year)\b"
    r"|\b(?P<span>(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|several|a\s+few)\s+"
    r"(?:years?|months?|days?|weeks?)\s+(?:before|after|prior\s+to|later\s+than)\s)"
    r"|\b(?P<agent>(?:co-)?[a-z]+ed\s+by)\s", re.I)
_FORMAT_DIRECTIVE = re.compile(r"^\s*(?:please\s+)?(?:round|give|write|answer|express|ignore|return|provide|respond|"
                               r"state|use)\b", re.I)
_QUALIFIER = re.compile(r"^\s*(?:as of|as at|before|after|during|since|until|by)\b", re.I)
_MERGE_FORWARD = re.compile(r"^\s*(?:than|in|during|between|or|and|the|a|an)\b", re.I)
_PROTECT = "\u0001"


def _content(text: str) -> int:
    return sum(1 for w in re.findall(r"[\w'’-]+", text.casefold()) if w not in _STOP and len(w) > 1)


def _mentions(text: str, entities) -> list:
    """(start, end, entity) of each registered entity mention, longest first at a position, non-overlapping."""
    low, out = text.casefold(), []
    for e in sorted(set(entities), key=len, reverse=True):
        if len(e) < 3:
            continue
        for m in re.finditer(r"(?<!\w)" + re.escape(e.casefold()) + r"(?!\w)", low):
            if not any(a < m.end() and m.start() < b for a, b, _ in out):
                out.append((m.start(), m.end(), e))
    return sorted(out)


_JOIN = re.compile(r"^\s*,?\s*(?:(?:and|or|&)\s+)?(?:the\s+)?$", re.I)


def _enumerations(text: str, entities) -> list:
    """Runs of >= 2 entity mentions separated only by commas / and / or: [(start, end, [(s, e), ...]), ...]."""
    ms, runs, cur = _mentions(text, entities), [], []
    for m in ms:
        if cur and _JOIN.match(text[cur[-1][1]:m[0]]):
            cur.append(m)
        else:
            if len(cur) >= 2:
                runs.append(cur)
            cur = [m]
    if len(cur) >= 2:
        runs.append(cur)
    return [(r[0][0], r[-1][1], [(a, b) for a, b, _ in r]) for r in runs]


def _operands(clause: str, entities) -> list:
    """Rule 2: one piece per operand, else [clause]."""
    # the LAST 'between' before the 'and' ('the difference between the years served ... between that state's senator
    # and his uncle' compares the senator and the uncle)
    m = re.search(r"^(.*)\bbetween\s+(?P<a>.+?)\s+and\s+(?P<b>.+?)\s*[?.]?$", clause, re.I | re.S)
    if m and not (re.match(r"^\W*\d", m.group("a")) and re.match(r"^\W*\d", m.group("b"))):
        head = m.group(1).strip(" ,:")
        head = re.sub(r"\s+between$", "", head, flags=re.I)
        if len(head.split()) >= 2:
            return [f"{head}: {m.group('a').strip(' ,')}", f"{head}: {m.group('b').strip(' ,')}"]
    m = re.search(r"^(.*?[,:])\s+(.+?),?\s+or\s+(.+?)\s*[?.]?$", clause, re.I)
    if m and len(m.group(1).split()) >= 2 and WH_START.match(m.group(1)):
        head = m.group(1).strip(" ,:")
        return [f"{head}: {m.group(2).strip(' ,')}", f"{head}: {m.group(3).strip(' ,')}"]
    runs = _enumerations(clause, entities)
    if runs:
        s, e, spans = runs[0]
        # a mention's own article travels with it ('bands The Northern Pikes, ..., and The Sheepdogs')
        spans = [(a - 4 if clause[max(0, a - 4):a].casefold() == "the " else a, b) for a, b in spans]
        s = spans[0][0]
        before, after = clause[:s].rstrip(), clause[e:].lstrip()
        return [" ".join(x for x in (before, clause[a:b], after) if x) for a, b in spans]
    return [clause]


def _hops(piece: str) -> list:
    """Rule 3 and 4's merge: the piece cut before each hop marker that passes its guard."""
    cuts = []
    for m in _HOP.finditer(piece):
        pos = m.start()
        if pos == 0:
            continue
        if piece[pos].isupper():                                 # 'Doctor Who', 'When Harry Met Sally': a name
            continue
        before = piece[:pos].rstrip()
        words = re.findall(r"[\w'’-]+", before.casefold())
        prev = words[-1] if words else ""
        if m.group("that") and prev in _THAT_BLOCK:
            continue
        if m.group("that") and re.match(r"that\s+[\w-]+['’]s\b", piece[pos:], re.I):   # 'that state's senator'
            continue
        if m.group("wh") and prev in _WH_BLOCK:
            continue
        if m.group("than") and prev in _THAN_BLOCK:
            continue
        if m.group("agent") and (prev in _AUX_BEFORE or prev.endswith("ly")):
            continue
        if m.group("wh") and prev in _PREP:                     # 'the city from where ...' cuts before 'from'
            pos = before.casefold().rfind(prev)
        cuts.append(pos)
    pieces, last = [], 0
    for c in sorted(set(cuts)):
        pieces.append(piece[last:c])
        last = c
    pieces.append(piece[last:])
    pieces = [re.sub(r"[\s,;]+(?:and|or)?\s*$", "", p).strip(" ,;") for p in pieces]
    pieces = [p for p in pieces if p]
    merged: list = []
    i = 0
    while i < len(pieces):
        p = pieces[i]
        if _content(p) < 2 and len(pieces) > 1:
            if (not merged or _MERGE_FORWARD.match(p)) and i + 1 < len(pieces):
                pieces[i + 1] = f"{p} {pieces[i + 1]}"
            elif merged:
                merged[-1] = f"{merged[-1]} {p}"
            else:
                merged.append(p)
            i += 1
            continue
        merged.append(p)
        i += 1
    return merged or [piece]


def frames_obligation_needs(question: str, entities) -> list:
    """The FRAMES obligation needs of a question, in order (rules 1-4 above)."""
    protected = question
    for s, e, _ in sorted(_enumerations(question, entities), reverse=True):
        protected = protected[:s] + protected[s:e].replace(",", _PROTECT) + protected[e:]
    clauses, carry = [], ""
    for clause in frames_clauses(protected):
        clause = clause.replace(_PROTECT, ",")
        if _FORMAT_DIRECTIVE.match(clause):
            continue
        # a bare time qualifier ('As of August 1, 2024', 'Before the COVID-19 pandemic') qualifies the next clause
        if _QUALIFIER.match(clause) and len(clause.split()) <= 6:
            carry = f"{carry} {clause},".strip()
            continue
        clauses.append((carry, clause))
        carry = ""
    if carry:
        clauses.append(("", carry.rstrip(",")))
    needs = []
    for qualifier, clause in clauses:
        for piece in _operands(clause, entities):
            hops = _hops(piece)
            # the qualifier binds each operand's first piece ('As of 2024, ... between A and B' -> both A and B)
            needs.extend([f"{qualifier} {hops[0]}", *hops[1:]] if qualifier else hops)
    return [n.strip(" ,;?") for n in needs if n.strip(" ,;?")] or [question.strip()]


def compile_frames(question: str, stratum: str, *, entities: list | None = None, route_on: str = "stratum") -> Compiled:
    if entities is None:
        doc, stats, F = _frames_compiler()
        entities = F.compile_question(question, doc, stats)["entities"]
    obligations = []
    for i, c in enumerate(frames_obligation_needs(question, entities)):
        named = [e for _, _, e in _mentions(c, entities)]
        obligations.append(Obligation(f"o{i + 1}", c, _slots(entity="; ".join(dict.fromkeys(named)) or UNKNOWN),
                                      "one", []))
    return Compiled("frames", question, None, stratum, "chain", [o.id for o in obligations], {}, obligations,
                    {"rule": route_on, "input": stratum,
                     "compiler": "frames_corpus.compile_question + witness_compile.frames_obligation_needs",
                     "entities": list(entities)})


# ---------------------------------------------------------------------------------------------- LongMem


def longmem_sides(question: str) -> list[str]:
    """Two sides of an order/duration question: 'between A and B', or 'A or B' after the last comma/colon."""
    q = question.strip().rstrip("?")
    m = re.search(r"\bbetween\s+(.+?)\s+and\s+(.+)$", q, re.I)
    if m:
        return [m.group(1).strip(" ,"), m.group(2).strip(" ,")]
    tail = re.split(r"[,:]\s+", q)[-1]
    m = re.search(r"^(?:the\s+)?(.+?)\s+or\s+(?:the\s+)?(.+)$", tail, re.I)
    if m and len(re.split(r"[,:]\s+", q)) > 1:
        return [m.group(1).strip(), m.group(2).strip()]
    return []


AGE_NEED = "the user's age as the conversations state it (value_number) and the date that age held (value_date)"
EVENT_NEED = "when it happened"
BEGAN_NEED = "when it began"
_DURATION_LEAD = re.compile(r"^\s*how\s+(?:long|many\s+\w+|much\s+time)\b\s*(?:ago\b\s*)?"
                            r"(?:(?:have|has|had)\s+(?:it\s+been|passed)\b\s*|passed\b\s*|elapsed\b\s*)?(?:since\b\s*)?"
                            r"(?:(?:did|had|have|has|was|were|do|does|is|am)\b\s*)?", re.I)


def anchored_event(question: str) -> str:
    """The event of a span-to-the-question-date question, in its words: 'How many days ago did I attend the service?'
    -> 'when it happened: I attend the service'."""
    core = _DURATION_LEAD.sub("", question.strip().rstrip("?").strip())
    core = re.sub(r"\s+ago$", "", core, flags=re.I).strip(" ,")
    return f"{EVENT_NEED}: {core}" if len(core.split()) >= 2 else question.strip()
_EVENT_JOIN = re.compile(r"\s+(before|after|until|till|when)\s+", re.I)
_SECOND_CLAUSE = re.compile(r"\s+(?=(?:did|had|was|were|do|does)\s+(?:I|we)\b)", re.I)


def event_sides(question: str) -> list:
    """The two events of a span question joined by before / after / until / when, each as a dated obligation need:
    'How long did I use my new binoculars before I saw the goldfinches?' -> ['when it began: I use my new binoculars',
    'when it happened: I saw the goldfinches']; 'How many days after I bought the bike did I first ride it?' ->
    ['when it happened: I bought the bike', 'when it happened: I first ride it']. [] when no such join exists."""
    q = question.strip().rstrip("?").strip()
    m = _EVENT_JOIN.search(q)
    if not m:
        return []
    head, tail = q[:m.start()], q[m.end():]
    core = _DURATION_LEAD.sub("", head).strip(" ,")
    began = bool(re.match(r"^\s*how\s+long\b", head, re.I))
    if len(core.split()) >= 2:
        first, second = core, tail
    else:
        # the connective follows the unit ('how many days after X did I Y'): X is one event, Y the other
        k = _SECOND_CLAUSE.search(tail)
        if not k:
            return []
        first, second = tail[:k.start()], _DURATION_LEAD.sub("", tail[k.end():]).strip()
        second = re.sub(r"^(?:did|had|was|were|do|does)\s+", "", second, flags=re.I)
        began = False
    first, second = first.strip(" ,"), second.strip(" ,")
    if len(first.split()) < 2 or len(second.split()) < 2:
        return []
    return [f"{BEGAN_NEED if began else EVENT_NEED}: {first}", f"{EVENT_NEED}: {second}"]


def compile_longmem(question: str, question_date: str, stratum: str, *, resolver=None,
                    route_on: str = "stratum") -> Compiled:
    if stratum == "abstention":
        raise ValueError("give the raw LongMem question_type; the 'abstention' relabel marks unanswerable ids")
    if not question_date:
        raise ValueError("LongMem compile requires question_date")
    kind, frame = longmem_kind(stratum, question) if route_on == "stratum" else wording_kind("longmemeval_s", question)
    ent = UNKNOWN
    if resolver is not None:
        ent = "; ".join(r["key"] for r in resolver(question) if r.get("entity_id") is not None) or UNKNOWN
    if kind in ("count", "latest"):
        need = ("each distinct item the question counts or adds up" if kind == "count" else
                "every statement of the value the question asks about, with the date it held")
        obligations = [Obligation("o1", f"{need}: {question.strip()}", _slots(entity=ent), "each", [])]
    elif kind == "duration" and frame.get("anchor") == "age":
        m = AGE.search(question)
        obligations = [Obligation("o1", AGE_NEED, _slots(entity=ent), "one", [])]
        if m and m.group("event"):
            obligations.append(Obligation("o2", f"{EVENT_NEED}: {m.group('event').strip(' ?')}", _slots(entity=ent),
                                          "one", []))
    elif kind in ("order", "duration"):
        sides = longmem_sides(question)
        if kind == "duration" and frame.get("anchor") == "question_date":
            m = OLDER_THAN_WHEN.search(question)
            sides = ([f"{EVENT_NEED}: {m.group('event').strip(' ?')}"] if m else sides[:1] or [anchored_event(question)])
        elif kind == "duration" and not sides:
            # a span between two events the question joins with before / after / until / when: one dated obligation
            # per event, so the operator can take the two dates (judge round 1, defect 4: the binoculars question had
            # one obligation and op_duration needs two dates)
            sides = event_sides(question)
        if not sides:
            sides = [question.strip()]
        obligations = [Obligation(f"o{i + 1}", s, _slots(entity=ent), "one", []) for i, s in enumerate(sides)]
    else:
        obligations = [Obligation("o1", question.strip(), _slots(entity=ent), "one", [])]
    return Compiled("longmemeval_s", question, question_date, stratum, kind, [o.id for o in obligations], frame,
                    obligations, {"rule": route_on, "input": stratum if route_on == "stratum" else "question text",
                                  "compiler": "witness_compile.compile_longmem"})


# ---------------------------------------------------------------------------------------------- the door


def compile_question(dataset: str, question: str, stratum: str, question_date: str | None = None,
                     **kw) -> Compiled:
    if dataset == "multihoprag":
        return compile_news(question, stratum, **kw)
    if dataset == "frames":
        return compile_frames(question, stratum, **kw)
    if dataset == "longmemeval_s":
        return compile_longmem(question, question_date, stratum, **kw)
    raise ValueError(f"dataset must be one of {DATASETS}")


__all__ = ["COMPUTED_KINDS", "Compiled", "compare_sides", "DATASETS", "KINDS", "Obligation", "compile_frames", "compile_longmem",
           "compile_news", "compile_question", "frames_clauses", "longmem_kind", "longmem_sides", "news_kind",
           "wording_kind", "yes_no"]
