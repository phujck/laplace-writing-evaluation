"""Stage 3, the question side (R3): a question compiles to slot masks over R1's seven tuple axes.

    (t_coarse, t_fine, source, e_subj, m_code, polarity, e_obj)    R1's banked schema, exactly as banked

Condition first, score second: every facet of a question becomes one allowed-label set per axis, and the
coupling (index.py) returns the exact tuple support of the conjunction before anything is scored.

What each axis is compiled from (one organ per slot, nothing re-authored):
  source    the imported finite outlet grammar ``news_projection.query_facets`` (outlet aliases, clause split on
            while/whereas, nearest date): its facets are the facets here, so a facet vector supplied by the
            imported trial machinery stays aligned with its facet.
  t_fine    a facet's day from ``query_facets``; its ROLE from the engine organ
  t_coarse  ``atlas.reconstruction.query_plan.compile_query`` (publication | event | unknown). A publication date
            conditions t_fine exactly. An event or unknown-role date is a DECLARED WINDOW [d, d + EVENT_WINDOW_DAYS - 1]
            (labelled assumption: coverage follows an event within a week), never an exact day, because the organ
            itself refuses exact conditioning on it (query_plan.py:400-407). Grammar extension, declared: ISO dates
            (2023-10-12), which neither imported grammar reads, are rendered to the month-name form before the organ
            sees them; a date in a facet's text that no facet holds as its day (query_facets binds ONE day per
            outlet facet, so "the Sporting News article published on September 28 ... and the November 1 article"
            loses the second) joins that facet's window; a month named with a year and no day ("in October 2023")
            conditions t_coarse (news t_coarse is the month).
  e_subj    R1's own canonicalizer on the facet text: ``entities.extract`` with the corpus CaseStats R1 measured,
            ``entities.scope_aliases`` inside the facet, the registry's global aliases, outlets excluded. The facet's
            registered entities form one allowed set (union: a facet naming two entities is satisfied by a card that
            witnesses either; index.py routes every entity a card mentions onto this axis). Conventional default
            refused: a separate alias table or a model NER pass - a question resolved by a different canonicalizer
            than the cards cannot meet them on a shared label.
  m_code    the facet vector (imported fp16 BGE, query role; the encoder config declares no query prefix, common.py
            ENCODERS) against R1's unit centroids; the top-m codes are allowed, with m a dial MEASURED on the
            development questions (index_dev48.py). A facet whose best centroid cosine is below the codebook's own
            support radius (0.61346, codebook_v1.json) is <unknown> in the codebook's terms - exactly R1's assign
            rule (codebook.py:106-111) - so the axis stays unconstrained.
  polarity  R1's cue lexicon (polarity.decide) on the facet text; a fired cue allows its one class.
  e_obj     never constrained on news. DECLARED MAPPING (W1a amendment 5): news e_obj kinds are {registry entity,
            <rare>, qty:percent, qty:currency, qty:number, <unknown>}; the planted law's e_obj has NONE (no object)
            as a category distinct from unknown. The compiler never equates NONE, <rare> and <unknown>: NONE has no
            news counterpart, <rare> is "an entity below the registry floor", <unknown> is "nothing extracted". The
            role split subj/obj is by spread and position, not syntax (R1 residual), so the news compiler puts a
            question's entities on e_subj only, where index.py routes every mentioned entity of a card.

THE UNKNOWN (W1a amendment 2). On an unconstrained axis the mask is all-true, so '<unknown>' (index cardinality-1,
the one spelling in relational.polarity) is a MATCHING label. On a constrained axis the allowed set never contains
it: an unknown tuple value there is a DECLARED MISS, and every facet receipt says which, per axis.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from atlas.reconstruction.query_plan import compile_query

from relational import entities as ent
from relational import paths
from relational import polarity as pol
from relational.tuples import AXES

STAGE = "query"
UNKNOWN = pol.UNKNOWN

# The R1 artifacts R3 conditions on, at their re-banked pins. Every load verifies. W2-CANON-FIX re-banked the news
# tuples under the declared supersessions derived/tuples/superseded/20261022T051158Z (v1 bytes 07f7a61b... retired)
# and 20261022T051425Z, and its continuation 1 retired polarity_v1 8a10156e... and the receipt 62fc8be8... at
# 20261022T053947Z (tuples unchanged); the file names stay fixed (tuples.Supersession), the pins move with the bytes.
TUPLE_PINS = {
    "multihoprag_tuples_v1.json": "486ecf93d5992084f17b593a1d3b9e2b8538d6b6b43111a170a8c98246632a30",
    "multihoprag_receipt_v1.json": "a7f61884d07f2538974e563323ce6a15a31d816d4327ab6049e1dfe0e071952c",
    "entity_registry_v1.json": "39e8381c3454c01cac5a21d7d5d5566b06af6d715a12e946a9920fdbaca14b1f",
    "mechanism_codebook_v1.json": "7771b77e2d534e51bc4172cc55cb289825a3c94b4da142454dd951feb1c913b1",
    "mechanism_codebook_v1.npy": "4f6a2754f8a992c1d3e68c0feca684bdc08a06c2885725d8318f3784c781fc42",
    "polarity_v1.json": "7947e47576aacb1107c85731c2fe51d77c46517404ab3d3c107b72eba9c5ef9e",
}
EVENT_WINDOW_DAYS = 7          # labelled assumption (module doc): an event date admits [d, d+6]
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december")
_ISO = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
_FULL = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?(?:,)?\s+(20\d{2})\b", re.I)
_MONTH_YEAR = re.compile(r"\b(" + "|".join(_MONTHS) + r")\s+(?:of\s+)?(20\d{2})\b", re.I)


def tuples_path(name: str) -> Path:
    return paths.derived("tuples", name)


def verify_pins() -> dict:
    """sha256 of every pinned R1 artifact; a moved pin is refused, never silently consumed."""
    out = {}
    for name, want in TUPLE_PINS.items():
        got = paths.sha256(tuples_path(name))
        if got != want:
            raise ValueError(f"R1 artifact {name} moved: {got} != pinned {want}")
        out[name] = got
    return out


def news_projection():
    """The imported outlet/date grammar module (read-only, loaded by the one imported-code loader)."""
    from relational.packer_replay import imported_module
    return imported_module("reconstruction", "news_projection")


def _iso_to_words(match: re.Match) -> str:
    y, m, d = int(match[1]), int(match[2]), int(match[3])
    return f"{_MONTHS[m - 1].capitalize()} {d}, {y}" if 1 <= m <= 12 else match.group(0)


def _dates_in(text: str) -> list[str]:
    """Every full date in ``text`` (month-name or ISO) as YYYY-MM-DD, in reading order."""
    found = [(m.start(), f"{int(m[3]):04d}-{_MONTHS.index(m[1].casefold()) + 1:02d}-{int(m[2]):02d}")
             for m in _FULL.finditer(text)]
    found += [(m.start(), f"{m[1]}-{m[2]}-{m[3]}") for m in _ISO.finditer(text) if 1 <= int(m[2]) <= 12]
    return [d for _, d in sorted(found)]


def _month_years(text: str) -> list[str]:
    out = []
    for m in _MONTH_YEAR.finditer(text):
        out.append(f"{int(m[2]):04d}-{_MONTHS.index(m[1].casefold()) + 1:02d}")
    return out


@dataclass(frozen=True)
class Slot:
    axis: str
    allowed: tuple[int, ...] | None          # None: unconstrained (all-true mask, <unknown> matches)
    rule: str
    evidence: tuple = ()

    @property
    def unknown(self) -> str:
        return ("matching (axis unconstrained: all-true mask)" if self.allowed is None
                else "declared miss (axis constrained: <unknown> excluded)")

    def to_dict(self) -> dict:
        return {"axis": self.axis, "allowed": None if self.allowed is None else list(self.allowed),
                "rule": self.rule, "evidence": list(self.evidence), "unknown": self.unknown}


@dataclass(frozen=True)
class FacetSlots:
    index: int
    text: str
    source: str | None
    day: str | None
    slots: tuple[Slot, ...]                  # one per axis, AXES order

    def slot(self, axis: str) -> Slot:
        return self.slots[AXES.index(axis)]

    @property
    def constrained(self) -> tuple[str, ...]:
        return tuple(s.axis for s in self.slots if s.allowed is not None)

    def to_dict(self) -> dict:
        return {"facet": self.index, "text": self.text, "source": self.source, "day": self.day,
                "constrained_axes": list(self.constrained), "slots": [s.to_dict() for s in self.slots]}


@dataclass(frozen=True)
class CompilerConfig:
    """Which slot families condition. Each is a dial measured on the development questions (index_dev48.py)."""
    source: bool = True
    time: bool = True
    entity: bool = False
    mechanism_m: int | None = None           # None: mechanism unconstrained; m: top-m codebook codes
    polarity: bool = False

    def label(self) -> str:
        parts = [n for n, on in (("source", self.source), ("time", self.time), ("entity", self.entity),
                                 ("polarity", self.polarity)) if on]
        if self.mechanism_m is not None:
            parts.append(f"mech{self.mechanism_m}")
        return "+".join(parts) or "unconstrained"


# THE MEASURED CHOICE (derived/index/dev48_containment_v3.json, its "table"; R3-INDEX report
# slot_compiler.default_config). A slot family conditions hard (the support every candidate comes from) only if it
# keeps the development gold. source + time keeps 86/89 gold documents (mean 158.1 support cards). The entity hard mask
# (source+time+entity) narrows the support 2.4x (65.9 mean cards) but keeps 71/89: it drops gold documents whose card
# never names the question's entity (cards are four short fields and a title, not the body), so entity ACTIVATES
# branches instead: inside the hard support, the episodes that also match the entity slot are the packer's active
# branches (R4: covering is right only over active branches). Mechanism and polarity are refused as HARD masks on that
# measurement: source+time+mech-m loses gold at every m (69/89, 79/89, 83/89 at m = 16, 32, 64; the best, 83/89, is
# below source+time's 86/89) and source+time+polarity keeps 53/89. No receipt measures mechanism or polarity as an
# activation slot, so ACTIVATION_CONFIG leaves both unconstrained.
DEFAULT_CONFIG = CompilerConfig(source=True, time=True, entity=False, mechanism_m=None, polarity=False)
ACTIVATION_CONFIG = CompilerConfig(source=True, time=True, entity=True, mechanism_m=None, polarity=False)


class SlotCompiler:
    """Question text (+ one facet vector per facet) -> FacetSlots, over R1's banked vocabularies."""

    def __init__(self) -> None:
        self.pins = verify_pins()
        doc = json.loads(tuples_path("multihoprag_tuples_v1.json").read_text(encoding="utf-8"))
        self.vocab = doc["vocabularies"]
        self.index_of = {axis: {v: i for i, v in enumerate(self.vocab[axis])} for axis in AXES}
        registry = json.loads(tuples_path("entity_registry_v1.json").read_text(encoding="utf-8"))
        self.entity_ids = {e["key"]: e["id"] for e in registry["entities"]}
        for key, i in self.entity_ids.items():          # registry id == e_subj vocabulary index (R1 assembly)
            if self.index_of["e_subj"].get(key) != i:
                raise ValueError(f"registry id {i} of {key!r} is not its e_subj code")
        self.global_alias = registry["global_alias"]
        codebook = json.loads(tuples_path("mechanism_codebook_v1.json").read_text(encoding="utf-8"))
        self.radius = float(codebook["support_radius_cosine"])
        self.centroids = np.load(tuples_path("mechanism_codebook_v1.npy")).astype(np.float64)
        corpus = json.loads(paths.imported("data/multihoprag/corpus.json").read_text(encoding="utf-8"))
        cards = json.loads(paths.imported("data/cards/semantic_faces_full.json").read_text(encoding="utf-8"))["cards"]
        self.sources = tuple(sorted({d.get("source") or "" for d in corpus}))   # section_fine_projection.py:102
        self.outlets = ent.outlet_aliases(list(self.sources))
        # R1's CaseStats over exactly the texts R1 measured (tuples.build_multihoprag: bodies + the four fields)
        self.stats = ent.CaseStats()
        for d, c in zip(corpus, sorted(cards, key=lambda c: c["document_id"])):
            self.stats.add(d["body"])
            for f in ("object", "mechanism", "conditions", "consequences"):
                self.stats.add(c[f])
        self._grammar = news_projection()

    # ------------------------------------------------------------------ facets (the imported grammar)
    def facets(self, question: str):
        return self._grammar.query_facets(question, self.sources)

    # ------------------------------------------------------------------ per-axis compilers
    def _date_roles(self, question: str) -> dict:
        normal = _ISO.sub(_iso_to_words, question)
        plan = compile_query(normal, self.sources)
        return {d.iso_date: d.role for d in plan.dates}

    def _time(self, facet, roles: dict, bound: set) -> tuple[Slot, Slot]:
        # the facet's own day (query_facets), plus every date in its text that no facet holds as its day
        days = ([facet.day] if facet.day else []) + [d for d in _dates_in(facet.text) if d not in bound]
        fine_vocab = self.vocab["t_fine"][:-1]
        if days:
            allowed, evidence = set(), []
            for day in dict.fromkeys(days):
                role = roles.get(day, "unknown")
                if role == "publication":
                    window = [day]
                else:
                    start = _dt.date.fromisoformat(day)
                    window = [(start + _dt.timedelta(days=k)).isoformat() for k in range(EVENT_WINDOW_DAYS)]
                hit = [self.index_of["t_fine"][d] for d in window if d in self.index_of["t_fine"]
                       and d in fine_vocab]
                allowed.update(hit)
                evidence.append({"day": day, "role": role, "window": [window[0], window[-1]], "vocab_days": len(hit)})
            return (Slot("t_coarse", None, "implied by t_fine"),
                    Slot("t_fine", tuple(sorted(allowed)), "publication day exact; event/unknown role a declared "
                         f"{EVENT_WINDOW_DAYS}-day window", tuple(evidence)))
        months = [m for m in _month_years(facet.text) if m in self.index_of["t_coarse"]]
        if months:
            allowed = tuple(sorted({self.index_of["t_coarse"][m] for m in months}))
            return (Slot("t_coarse", allowed, "month named with a year and no day", tuple(months)),
                    Slot("t_fine", None, "no day named"))
        return Slot("t_coarse", None, "no time named"), Slot("t_fine", None, "no time named")

    def _source(self, facet) -> Slot:
        if facet.source is None:
            return Slot("source", None, "no outlet named (query_facets)")
        code = self.index_of["source"].get(facet.source)
        return Slot("source", () if code is None else (code,), "outlet named (query_facets)", (facet.source,))

    def resolve_entities(self, text: str) -> list[dict]:
        """R1's canonicalizer on one text: mentions with canonical key, status and registry id."""
        mentions = ent.extract(text, self.stats)
        local, _ = ent.scope_aliases([mentions], [text])
        local = {short: full for short, (full, _) in local.items()}
        out = []
        for m in mentions:
            if m.key in self.outlets:
                out.append({"surface": m.surface, "key": m.key, "status": "outlet", "entity_id": None})
                continue
            key, seen = m.key, set()
            while True:                                    # entities.Registry.build canonical(): local, then global
                nxt = local.get(key) or self.global_alias.get(key)
                if nxt is None or nxt in seen or nxt == key:
                    break
                seen.add(key)
                key = nxt
            eid = self.entity_ids.get(key)
            out.append({"surface": m.surface, "key": key, "status": "entity" if eid is not None else "rare",
                        "entity_id": eid})
        return out

    def _entity(self, facet) -> Slot:
        resolved = self.resolve_entities(facet.text)
        ids = sorted({r["entity_id"] for r in resolved if r["entity_id"] is not None})
        evidence = tuple(f"{r['surface']}->{r['key']}:{r['status']}" for r in resolved)
        if not ids:
            return Slot("e_subj", None, "no registered entity named (unregistered surfaces cannot constrain)",
                        evidence)
        return Slot("e_subj", tuple(ids), "registered entities named in the facet (union; R1 canonicalizer)",
                    evidence)

    def mechanism_scores(self, vector) -> np.ndarray:
        v = np.asarray(vector, dtype=np.float64)
        v = v / np.linalg.norm(v)
        return self.centroids @ v

    def _mechanism(self, vector, m: int | None) -> Slot:
        if m is None:
            return Slot("m_code", None, "mechanism dial off")
        if vector is None:          # compile() refuses this before it gets here; kept for direct callers
            raise ValueError(f"mechanism dial m={m} needs a facet vector; none supplied (refused, never unconstrained)")
        sims = self.mechanism_scores(vector)
        order = np.argsort(-sims, kind="stable")
        best = float(sims[order[0]])
        if best < self.radius:
            return Slot("m_code", None, f"best centroid cosine {best:.4f} < support radius {self.radius}: "
                        "<unknown> in the codebook's own terms", (round(best, 6),))
        codes = tuple(sorted(int(c) for c in order[:m]))
        return Slot("m_code", codes, f"top-{m} codebook codes by centroid cosine",
                    tuple(round(float(sims[c]), 6) for c in order[:m]))

    def _polarity(self, facet, on: bool) -> Slot:
        if not on:
            return Slot("polarity", None, "polarity dial off")
        record = pol.decide([("facet", facet.text)])
        if record["polarity"] == UNKNOWN:
            return Slot("polarity", None, "no cue fired")
        return Slot("polarity", (self.index_of["polarity"][record["polarity"]],),
                    "R1 cue lexicon (precedence supersede>negate>update>open>assert)", (record["cue"],))

    def encode_facets(self, facets) -> np.ndarray:
        """Facet texts -> 384-d query vectors through the ONE imported-encoder loader (relational.encoder), CPU, role
        'query': the same encoder, role and device that produced the fresh-200 frame queries (index_frames.fresh200)."""
        from relational.encoder import load_imported_encoder
        enc = load_imported_encoder("cpu")
        return enc.embed([f.text for f in facets], role="query").astype(np.float32)

    def labels(self, axis: str, allowed) -> list[str] | None:
        return None if allowed is None else [self.vocab[axis][i] for i in allowed]

    # ------------------------------------------------------------------ the compiler
    def compile(self, question: str, facet_vectors=None, config: CompilerConfig = DEFAULT_CONFIG,
                facets=None) -> list[FacetSlots]:
        facets = self.facets(question) if facets is None else facets
        if facet_vectors is not None and len(facet_vectors) != len(facets):
            raise ValueError("one facet vector per facet is required")
        if config.mechanism_m is not None and facet_vectors is None:
            raise ValueError(f"mechanism dial m={config.mechanism_m} needs one facet vector per facet; none supplied "
                             "(refused by name: the mechanism axis is never silently left unconstrained). The door "
                             "encodes them: query --question TEXT --mechanism-m M")
        roles = self._date_roles(question)
        bound = {f.day for f in facets if f.day}
        out = []
        for i, facet in enumerate(facets):
            t_coarse, t_fine = self._time(facet, roles, bound) if config.time else (
                Slot("t_coarse", None, "time dial off"), Slot("t_fine", None, "time dial off"))
            source = self._source(facet) if config.source else Slot("source", None, "source dial off")
            e_subj = self._entity(facet) if config.entity else Slot("e_subj", None, "entity dial off")
            vector = None if facet_vectors is None else np.asarray(
                facet_vectors[i].detach().cpu().numpy() if hasattr(facet_vectors[i], "detach") else facet_vectors[i])
            m_code = self._mechanism(vector, config.mechanism_m)
            polarity = self._polarity(facet, config.polarity)
            e_obj = Slot("e_obj", None, "never constrained on news (declared e_obj mapping, module doc)")
            slots = {s.axis: s for s in (t_coarse, t_fine, source, e_subj, m_code, polarity, e_obj)}
            out.append(FacetSlots(i, facet.text, facet.source, facet.day, tuple(slots[a] for a in AXES)))
        return out


# ---------------------------------------------------------------------------------------------- the door

_COMPILER: SlotCompiler | None = None


def compiler() -> SlotCompiler:
    global _COMPILER
    if _COMPILER is None:
        _COMPILER = SlotCompiler()
    return _COMPILER


CONFIGS = {"default": DEFAULT_CONFIG, "activation": ACTIVATION_CONFIG}


def door_config(args) -> CompilerConfig:
    """The shipped config named by --config, with the explicit dials layered on it (never silently dropped)."""
    base = CONFIGS[args.config]
    return CompilerConfig(source=base.source, time=base.time, entity=base.entity or args.entity,
                          mechanism_m=args.mechanism_m if args.mechanism_m is not None else base.mechanism_m,
                          polarity=base.polarity or args.polarity)


def _run(args) -> dict:
    if args.planted:
        from relational import query_planted
        return query_planted.measure(events=args.events, seed=args.seed)
    if not args.question:
        return {"status": "USAGE", "exit": 2, "message": "query --question TEXT [--config default|activation] "
                "[--entity] [--mechanism-m M] [--polarity] | query --planted"}
    if args.mechanism_m is not None and args.mechanism_m < 1:
        return {"status": "REFUSED", "exit": 2, "message": f"--mechanism-m must be >= 1, got {args.mechanism_m}"}
    config = door_config(args)
    comp = compiler()
    facets = comp.facets(args.question)
    vectors, vector_source = None, "none (mechanism dial off)"
    if config.mechanism_m is not None:
        vectors = comp.encode_facets(facets)
        vector_source = ("encoded fresh: imported fp16 BGE-small, CPU, role=query, one vector per facet text "
                         "(relational.encoder.load_imported_encoder)")
    slots = comp.compile(args.question, vectors, config, facets=facets)
    out = []
    for s in slots:
        d = s.to_dict()
        d["e_subj"] = {"allowed": d["slots"][AXES.index("e_subj")]["allowed"],
                       "labels": comp.labels("e_subj", s.slot("e_subj").allowed),
                       "rule": s.slot("e_subj").rule, "evidence": list(s.slot("e_subj").evidence)}
        d["m_code"] = {"allowed": d["slots"][AXES.index("m_code")]["allowed"],
                       "labels": comp.labels("m_code", s.slot("m_code").allowed), "rule": s.slot("m_code").rule}
        d["unknown_semantics"] = {sl.axis: sl.unknown for sl in s.slots}
        out.append(d)
    return {"status": "COMPILED", "question": args.question, "config_name": args.config,
            "config": asdict(config), "config_label": config.label(), "facet_vectors": vector_source,
            "facets": out}


def register(sub) -> None:
    p = sub.add_parser("query", help="R3: question -> slot masks over the seven tuple axes")
    p.add_argument("--question", help="compile one question")
    p.add_argument("--config", choices=tuple(CONFIGS), default="default",
                   help="the shipped config: default = hard source+time (the support every candidate comes from); "
                        "activation = default + entity (the slots that activate episode branches)")
    p.add_argument("--entity", action="store_true", help="turn the entity dial on (e_subj allowed set)")
    p.add_argument("--mechanism-m", type=int, default=None, dest="mechanism_m",
                   help="turn the mechanism dial on with the top-M codebook codes; the facet vectors are encoded "
                        "fresh by the imported encoder (no vector input exists at the door)")
    p.add_argument("--polarity", action="store_true", help="turn the polarity dial on")
    p.add_argument("--planted", action="store_true",
                   help="compile the planted questions' TEXT and compare with their gold slot masks")
    p.add_argument("--events", type=int, default=1000)
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(func=_run)


__all__ = ["AXES", "ACTIVATION_CONFIG", "CONFIGS", "CompilerConfig", "DEFAULT_CONFIG", "FacetSlots", "Slot", "SlotCompiler", "TUPLE_PINS",
           "EVENT_WINDOW_DAYS", "compiler", "register", "verify_pins", "news_projection"]
