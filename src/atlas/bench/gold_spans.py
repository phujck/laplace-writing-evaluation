"""gold_spans.py - resolving gold evidence to BYTE ADDRESSES, for both benchmarks, with no model.

F.23's check refuses a coverage number whose gold "spans are not resolvable to byte addresses in
the record". This module is what makes them resolvable. For each dataset it builds a deterministic
BYTE IMAGE per container and an addressable unit table over it, then maps each gold evidence item
to the address of the unit that carries it.

  QASPER        one image per paper; units = abstract, SECTION HEADERS, paragraphs, captions.
                Grades: 0 unit, 1 section / abstract / float-group, 2 paper.
  LongMemEval   one image per question case; units = turns.
                Grades: 0 turn, 1 session, 2 case.
  MultiHop-RAG  one image per news document; the gold FACT resolves to its byte range in the body.

Because the units of a container are laid out CONTIGUOUSLY in its image in the order they are
declared, a grade-1 node (a section, a session) is a genuine byte interval that CONTAINS its
members' intervals. That is what makes a graded read scorable by the same containment predicate as
a flat one: opening a node does not need a different metric, it needs the same one.

THE QASPER GOLD-EVIDENCE MAP REPAIR. ``qasper_data.export_gold`` maps a gold evidence string to an
observation by exact whitespace-collapsed equality against the exported observations, and the
export contains no section headers and no float captions under the name QASPER's evidence uses.
Over the 32-question development bank that leaves 10 unmapped requirements, in exactly three
kinds, and each stays in the denominator forever - so a perfect arm scores below 1. The repair,
all of it deterministic and fail-closed:

  (1) SECTION HEADERS. QASPER's evidence may be a section name ('Soft attention', 'Ablation
      Study'); nested names are written 'Approach ::: Soft attention'. Section headers become
      addressable units, and a header matches on its full name or on its last ' ::: ' component.
  (2) 'FLOAT SELECTED: ...'. Evidence for a table or figure is the string 'FLOAT SELECTED: ' plus
      the float's caption, sometimes with trailing footnote digits. The prefix is stripped and the
      remainder must match a caption of the SAME paper exactly, or be a containment match with a
      UNIQUE caption; two candidates is an ``AmbiguousGoldMapping`` refusal, never a pick.
  (3) UNICODE AND HYPHENATION. Matching runs through ``repair_normalize``: NFKC, soft hyphens
      removed, the dash family unified, whitespace collapsed, casefolded.

The repair is reported as a BEFORE and AFTER count, never folded silently into a headline: the
established 'all' metric is reproduced against the LEGACY map (requirement 2), and the repaired map
is reported beside it with the number of requirements it rescues.

No function here embeds anything, calls a model, or reads an arm's output.
"""

from __future__ import annotations

import functools
import hashlib
import importlib.util
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .evidence_coverage import (
    GoldUnresolvable,
    AmbiguousGoldMapping,
    GoldAlternative,
    GoldEvidence,
    GoldRequirement,
    SpanAddress,
    repair_normalize,
)

#: The repository root, three levels above ``src/atlas/bench``.
REPO_ROOT = Path(__file__).resolve().parents[3]
RECONSTRUCTION = REPO_ROOT / "synthetics papers" / "corpus-as-a-state" / "reconstruction"
EXTENSION = RECONSTRUCTION / "extension"

#: The byte separator between two units of one container image. Declared, not tuned: a separator
#: must be a sequence no unit text can contain after the source's own whitespace handling, and two
#: newlines is the separator the prior work's packers already use between passages.
UNIT_SEPARATOR = b"\n\n"

FLOAT_PREFIX = "float selected: "
SECTION_NESTING = " ::: "


def _load_prior_module(path: Path, name: str):
    """Import one of the prior work's stdlib-only modules BY PATH, without re-authoring it.

    The quarry's files live under a directory with a space in its name and are not a package. They
    are loaded here rather than copied so that a change in them is visible to this scorer; the
    caller records the file's sha256 beside any number it produces.
    """
    if not path.exists():
        raise FileNotFoundError(f"prior-work module not found: {path}")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --------------------------------------------------------------------------------------------
# The container image: units laid out contiguously, every unit a byte interval.
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Unit:
    """One addressable level-0 object inside a container image."""

    unit_id: str
    kind: str
    span: SpanAddress
    text: str
    parent_id: str


@dataclass(frozen=True, slots=True)
class Node:
    """One coarse node: a byte interval that CONTAINS the intervals of the members it coarsens.

    ``face_tokens`` is the node's typed face, folded by ONE rule at every level - the union of its
    members' faces - and ``member_counts`` is the integer block sum of its members' counts. Those
    two are what the reference graded read in ``reference_reads.py`` evaluates a condition against
    before it opens anything; they are carried here because the coarse node has to carry its own
    coarsening, not point at its children's vectors.
    """

    node_id: str
    grade: int
    kind: str
    span: SpanAddress
    member_ids: tuple[str, ...]
    face_tokens: frozenset[str]
    member_counts: dict
    face_text: str


@dataclass(frozen=True, slots=True)
class ContainerImage:
    """A deterministic byte image of one container, with its units and its coarse nodes."""

    handle: str
    image: bytes
    units: tuple[Unit, ...]
    nodes: tuple[Node, ...]

    @property
    def by_unit_id(self) -> dict[str, Unit]:
        return {u.unit_id: u for u in self.units}

    @property
    def nbytes(self) -> int:
        return len(self.image)


def _tokens(text: str) -> frozenset[str]:
    """The typed face vocabulary of a unit: its normalized word forms.

    Deliberately a SET of exact surface tokens, not a vector: the face has to support an EXACT
    admission test (a member cannot contain a token its parent's face lacks), which is what makes
    the graded read's prune exact rather than a similarity heuristic.
    """
    normalized = repair_normalize(text)
    return frozenset(w.strip(".,;:!?()[]{}\"'`") for w in normalized.split() if w.strip(".,;:!?()[]{}\"'`"))


def _lay_out(handle: str, entries: Sequence[tuple[str, str, str, str]]) -> tuple[bytes, tuple[Unit, ...]]:
    """Concatenate ``(unit_id, kind, parent_id, text)`` entries into one image. O(total bytes)."""
    chunks: list[bytes] = []
    units: list[Unit] = []
    offset = 0
    for i, (unit_id, kind, parent_id, text) in enumerate(entries):
        if i:
            chunks.append(UNIT_SEPARATOR)
            offset += len(UNIT_SEPARATOR)
        payload = text.encode("utf-8")
        chunks.append(payload)
        units.append(
            Unit(
                unit_id=unit_id,
                kind=kind,
                span=SpanAddress(handle, offset, offset + len(payload)),
                text=text,
                parent_id=parent_id,
            )
        )
        offset += len(payload)
    return b"".join(chunks), tuple(units)


def _group_nodes(
    handle: str, units: Sequence[Unit], *, grade: int, kind: str, prefix: str
) -> tuple[Node, ...]:
    """One grade-``grade`` node per distinct ``parent_id``, spanning its members contiguously."""
    order: list[str] = []
    members: dict[str, list[Unit]] = {}
    for unit in units:
        if unit.parent_id not in members:
            members[unit.parent_id] = []
            order.append(unit.parent_id)
        members[unit.parent_id].append(unit)
    nodes: list[Node] = []
    for parent_id in order:
        group = members[parent_id]
        start = min(u.span.start for u in group)
        end = max(u.span.end for u in group)
        face: frozenset[str] = frozenset().union(*(_tokens(u.text) for u in group))
        counts: dict[str, int] = {}
        for unit in group:
            counts[unit.kind] = counts.get(unit.kind, 0) + 1
        nodes.append(
            Node(
                node_id=f"{prefix}{parent_id}",
                grade=grade,
                kind=kind,
                span=SpanAddress(handle, start, end),
                member_ids=tuple(u.unit_id for u in group),
                face_tokens=face,
                member_counts=dict(sorted(counts.items())),
                face_text=" ".join(sorted(face)),
            )
        )
    return tuple(nodes)


def _root_node(handle: str, image: bytes, units: Sequence[Unit], grade: int, kind: str) -> Node:
    face: frozenset[str] = frozenset().union(*(_tokens(u.text) for u in units)) if units else frozenset()
    counts: dict[str, int] = {}
    for unit in units:
        counts[unit.kind] = counts.get(unit.kind, 0) + 1
    return Node(
        node_id=f"root:{handle}",
        grade=grade,
        kind=kind,
        span=SpanAddress(handle, 0, len(image)),
        member_ids=tuple(u.unit_id for u in units),
        face_tokens=face,
        member_counts=dict(sorted(counts.items())),
        face_text=" ".join(sorted(face)),
    )


# --------------------------------------------------------------------------------------------
# QASPER
# --------------------------------------------------------------------------------------------


def qasper_paper_image(paper_id: str, paper: Mapping) -> ContainerImage:
    """The byte image of one QASPER paper, in the export's own order plus section headers.

    Unit ids for the abstract, paragraphs and captions are EXACTLY the ids
    ``qasper_data.export_source_questions`` mints, so the established id-space metric and this
    span-space metric are computed over the same objects. Section headers are new ids and exist
    only for the gold-map repair.
    """
    entries: list[tuple[str, str, str, str]] = []
    if paper.get("abstract", "").strip():
        entries.append((f"qasper:{paper_id}:abstract", "abstract", "Abstract", paper["abstract"]))
    for si, section in enumerate(paper["full_text"]):
        name = section.get("section_name") or ""
        parent = f"s{si}"
        if name.strip():
            entries.append((f"qasper:{paper_id}:s{si}:header", "section_header", parent, name))
        for pi, paragraph in enumerate(section["paragraphs"]):
            if paragraph.strip():
                entries.append((f"qasper:{paper_id}:s{si}:p{pi}", "paragraph", parent, paragraph))
    for fi, figure in enumerate(paper.get("figures_and_tables", [])):
        caption = figure.get("caption", "")
        if caption.strip():
            entries.append((f"qasper:{paper_id}:caption{fi}", "caption", "Figures and tables", caption))
    handle = f"qasper:paper:{paper_id}"
    image, units = _lay_out(handle, entries)
    nodes = _group_nodes(handle, units, grade=1, kind="section", prefix=f"qasper:{paper_id}:sec:")
    root = _root_node(handle, image, units, grade=2, kind="paper")
    return ContainerImage(handle=handle, image=image, units=units, nodes=nodes + (root,))


def _qasper_index(image: ContainerImage) -> tuple[dict[str, list[Unit]], dict[str, list[Unit]], dict[str, list[Unit]]]:
    """Three lookup tables: the LEGACY exact one, the repaired normalized one, and captions."""
    legacy: dict[str, list[Unit]] = {}
    repaired: dict[str, list[Unit]] = {}
    captions: dict[str, list[Unit]] = {}
    for unit in image.units:
        if unit.kind != "section_header":
            legacy.setdefault(" ".join(unit.text.split()), []).append(unit)
        key = repair_normalize(unit.text)
        repaired.setdefault(key, []).append(unit)
        if unit.kind == "section_header":
            tail = unit.text.split(SECTION_NESTING)[-1]
            repaired.setdefault(repair_normalize(tail), []).append(unit)
        if unit.kind == "caption":
            captions.setdefault(key, []).append(unit)
    return legacy, repaired, captions


def _resolve_qasper_evidence(
    evidence: str, image: ContainerImage, tables, *, repaired: bool
) -> tuple[SpanAddress, ...]:
    legacy_index, repaired_index, captions = tables
    if not repaired:
        return tuple(u.span for u in legacy_index.get(" ".join(evidence.split()), []))
    key = repair_normalize(evidence)
    hits = repaired_index.get(key, [])
    if hits:
        return tuple(u.span for u in hits)
    if key.startswith(FLOAT_PREFIX):
        stripped = key[len(FLOAT_PREFIX):].strip()
        exact = captions.get(stripped, [])
        if exact:
            return tuple(u.span for u in exact)
        contained = [
            unit
            for caption_key, units in captions.items()
            for unit in units
            if stripped and (stripped in caption_key or caption_key in stripped)
        ]
        if len(contained) > 1:
            raise AmbiguousGoldMapping(
                f"'FLOAT SELECTED' evidence matches {len(contained)} captions of {image.handle}; "
                "the repair refuses to pick one"
            )
        if contained:
            return (contained[0].span,)
    return ()


def qasper_gold(
    paper_id: str, paper: Mapping, image: ContainerImage, question_ids: Iterable[str], *, repaired: bool
) -> dict[str, GoldEvidence]:
    """Gold evidence for the paper's questions, as addresses. ``repaired`` selects the map."""
    wanted = set(question_ids)
    tables = _qasper_index(image)
    out: dict[str, GoldEvidence] = {}
    for question in paper["qas"]:
        qid = question["question_id"]
        if qid not in wanted:
            continue
        alternatives: list[GoldAlternative] = []
        for item in question["answers"]:
            answer = item["answer"]
            if answer["unanswerable"]:
                continue
            evidence = list(answer["evidence"])
            if not evidence:
                continue
            requirements = tuple(
                GoldRequirement(
                    requirement_id=f"{item['annotation_id']}:{i}",
                    addresses=_resolve_qasper_evidence(text, image, tables, repaired=repaired),
                    text=text,
                )
                for i, text in enumerate(evidence)
            )
            alternatives.append(GoldAlternative(item["annotation_id"], requirements))
        out[qid] = GoldEvidence(
            question_id=qid,
            dataset="qasper",
            alternatives=tuple(alternatives),
            eligible=bool(alternatives),
        )
    return out


@functools.lru_cache(maxsize=None)
def load_qasper_split(split: str) -> Mapping:
    """The raw QASPER split, through the prior work's own reader (no re-authoring).

    Cached: the three splits are read-only here and the test archive is 60 MB; re-reading it once
    per caller would be the whole-corpus-rebuild the charter forbids, in miniature.
    """
    module = _load_prior_module(EXTENSION / "qasper_data.py", "_prior_qasper_data")
    return module.read_split(split)


# --------------------------------------------------------------------------------------------
# LongMemEval
# --------------------------------------------------------------------------------------------

LONGMEM_DATASET = EXTENSION / ".cache" / "longmemeval" / "longmemeval_s_cleaned.json"


def longmem_case_image(case) -> ContainerImage:
    """The byte image of one LongMemEval question case: sessions in order, turns inside them.

    A session is a contiguous byte interval containing its turns, so a graded read that opens a
    session supplies exactly the turns the session coarsens.
    """
    module = _load_prior_module(EXTENSION / "longmem_data.py", "_prior_longmem_data")
    handle = f"longmem:case:{case.jurisdiction_id}"
    entries: list[tuple[str, str, str, str]] = []
    for session in case.sessions:
        parent = module.session_unit_id(session.session_id, session.session_index)
        for turn in session.turns:
            entries.append(
                (
                    module.turn_unit_id(session.session_id, session.session_index, turn.turn_index),
                    f"turn:{turn.role}",
                    parent,
                    turn.content,
                )
            )
    image, units = _lay_out(handle, entries)
    nodes = _group_nodes(handle, units, grade=1, kind="session", prefix="session:")
    root = _root_node(handle, image, units, grade=2, kind="case")
    return ContainerImage(handle=handle, image=image, units=units, nodes=nodes + (root,))


def longmem_gold(record, image: ContainerImage) -> GoldEvidence:
    """Gold = the turns the dataset flags ``has_answer``, as byte addresses.

    An abstention question has no answer turn; it is marked ineligible rather than scored 0, the
    same treatment ``qasper_benchmark.evidence_metrics`` gives an unanswerable annotation.
    """
    by_id = image.by_unit_id
    requirements: list[GoldRequirement] = []
    for turn_id in record.answer_turn_ids:
        unit = by_id.get(turn_id)
        if unit is None:
            raise GoldUnresolvable(
                f"{record.question_id}: gold turn {turn_id!r} has no byte address in "
                f"{image.handle}. Unlike QASPER's unmapped evidence strings - a known property of "
                "that export, which the repair fixes - a LongMemEval answer turn is an index into "
                "the very sessions the image is built from, so a miss is a defect in the image and "
                "F.23 refuses a coverage number computed against it."
            )
        requirements.append(
            GoldRequirement(requirement_id=turn_id, addresses=(unit.span,), text=unit.text)
        )
    eligible = bool(requirements) and not record.is_abstention
    return GoldEvidence(
        question_id=record.question_id,
        dataset="longmemeval_s",
        alternatives=(GoldAlternative("longmem:answer-turns", tuple(requirements)),) if requirements else (),
        eligible=eligible,
    )


def load_longmem(limit: int | None = None, *, verify: bool = False):
    """Source cases and gold records, paired by question id, through the prior work's loader."""
    module = _load_prior_module(EXTENSION / "longmem_data.py", "_prior_longmem_data")
    cases = module.iter_source_cases(LONGMEM_DATASET, verify=verify)
    golds = module.iter_gold_records(LONGMEM_DATASET, verify=verify)
    out = []
    for i, (case, gold) in enumerate(zip(cases, golds)):
        if limit is not None and i >= limit:
            break
        if case.jurisdiction_id != gold.question_id:  # pragma: no cover - the loader pairs by order
            raise ValueError("source case and gold record are out of step")
        out.append((case, gold))
    return out


def longmem_split_manifest() -> Mapping:
    path = EXTENSION / "reviews" / "longmem_split_manifest.json"
    return json.loads(path.read_text())


# --------------------------------------------------------------------------------------------
# MultiHop-RAG
# --------------------------------------------------------------------------------------------

MULTIHOP = REPO_ROOT / "synthetics papers" / "corpus-as-a-state" / "data" / "multihoprag"


def load_multihop() -> tuple[list[dict], list[dict]]:
    corpus = json.loads((MULTIHOP / "corpus.json").read_text())
    questions = json.loads((MULTIHOP / "MultiHopRAG.json").read_text())
    return corpus, questions


@dataclass(frozen=True, slots=True)
class MultihopDocument:
    """The three fields ``reach_scores`` reads, matching ``real_data.Document``'s face."""

    document_id: int
    title: str
    url: str | None


def multihop_documents(corpus: Sequence[Mapping]) -> list[MultihopDocument]:
    return [MultihopDocument(i, d["title"], d.get("url")) for i, d in enumerate(corpus)]


def multihop_fact_addresses(corpus: Sequence[Mapping]) -> tuple[dict[str, bytes], dict]:
    """Whitespace-collapsed body images per document, and the index a fact is located in.

    The image is declared: ``" ".join(body.split())`` encoded UTF-8. Collapsing is necessary
    because the gold ``fact`` strings are re-whitespaced copies of the body text; it is declared
    rather than silently applied, and the same collapse defines the byte offsets, so an address is
    reproducible from the corpus file alone.
    """
    images = {
        f"multihoprag:doc:{i}": " ".join(d["body"].split()).encode("utf-8")
        for i, d in enumerate(corpus)
    }
    return images, {handle: blob.decode("utf-8") for handle, blob in images.items()}


def multihop_gold(
    question: Mapping, corpus_index: Mapping[str, set], images: Mapping[str, bytes], texts: Mapping[str, str]
) -> GoldEvidence:
    """One requirement per gold evidence item; resolved iff its fact occurs literally in its doc."""
    requirements: list[GoldRequirement] = []
    for i, item in enumerate(question["evidence_list"]):
        doc_ids = corpus_index.get(("url", item.get("url"))) or corpus_index.get(("title", item.get("title"))) or set()
        fact = " ".join(str(item.get("fact", "")).split())
        addresses: list[SpanAddress] = []
        for doc_id in sorted(doc_ids):
            handle = f"multihoprag:doc:{doc_id}"
            position = texts[handle].find(fact)
            if fact and position >= 0:
                start = len(texts[handle][:position].encode("utf-8"))
                addresses.append(SpanAddress(handle, start, start + len(fact.encode("utf-8"))))
        requirements.append(
            GoldRequirement(requirement_id=f"{i}", addresses=tuple(addresses), text=fact)
        )
    return GoldEvidence(
        question_id=hashlib.sha256(question["query"].encode()).hexdigest(),
        dataset="multihoprag",
        alternatives=(GoldAlternative("multihop:evidence-list", tuple(requirements)),),
        eligible=bool(requirements),
    )


def multihop_corpus_index(corpus: Sequence[Mapping]) -> dict:
    index: dict = {}
    for i, doc in enumerate(corpus):
        if doc.get("url"):
            index.setdefault(("url", doc["url"]), set()).add(i)
        index.setdefault(("title", doc["title"]), set()).add(i)
    return index


__all__ = [
    "REPO_ROOT",
    "RECONSTRUCTION",
    "EXTENSION",
    "UNIT_SEPARATOR",
    "Unit",
    "Node",
    "ContainerImage",
    "file_digest",
    "qasper_paper_image",
    "qasper_gold",
    "load_qasper_split",
    "longmem_case_image",
    "longmem_gold",
    "load_longmem",
    "longmem_split_manifest",
    "LONGMEM_DATASET",
    "load_multihop",
    "MultihopDocument",
    "multihop_documents",
    "multihop_fact_addresses",
    "multihop_gold",
    "multihop_corpus_index",
]
