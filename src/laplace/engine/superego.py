"""The superego — the standing judge organ, architecturally distinct from the producer.

Named by him 2026-07-22 (``contract/promises.jsonl`` row PRM-20260721-unprompted):
the scattered close-detectors are one organ — a standing judge instance, always on,
veto-bearing, whose voice is his banked question set. Its core function, per the
Dunning-Kruger asymmetry he named (asked, I know; unasked, I proceed confident): be
the asking, permanently. Production never self-certifies; confidence is not evidence;
every done-claim is interrogated by a non-builder instance before it counts.

His ruling this session (2026-07-22): the minimal superego is ratified, and it
inherits a fusion — HIS taste and the engine's knowledge. Two channels ride every
packet:

- the taste channel: him, internalized — threaded to the WHOLE implicit substrate
  (his ruling 2026-07-22: the loop closes against its own judgement, fuelled by the
  corpus of his implicit tastes and standards). :mod:`laplace.engine.taste_retrieval` ranks his
  verbatim rulings AND his overrules of the machine (``proxy_verdicts.jsonl``), the promise
  asks (``contract/promises.jsonl``), the stage stores of his sixteen first-author papers
  (``corpus_stores/*/``, with their precomputed embeddings), and the architecture / voice /
  house-style profiles (``profiles/``) by RAW embedding cosine — the distilled metric
  ``.metric_M.npz`` is stale against the current basis and is skipped, not applied silently.
  Keyword overlap is the marked offline fallback. Refs-only plus one bounded quote per item;
- the knowledge channel: the engine's typed law (the ``structural`` rows and
  ``counts`` laws across ``contract/surfaces/*.yaml``), the clause name, its bar,
  its red marker, its source file.

The seam is the same one the growth adjudicator holds: builder is not judge. This
module never makes a GENERATIVE model call — it produces no prose and returns no verdict;
its only model touch is the mechanical, deterministic embedding router the recall ring
already uses, to RANK his corpus for the taste channel (open-weight, local, offline-safe,
with a keyword fallback). :func:`assemble_packet` builds a decision packet a
dispatched judge consumes; :func:`bank_verdict` is the single append-only write door,
guarded so a builder cannot certify his own work. No HTTP surface, no scanner wiring —
the face is a later wave (G5). This is the organ and its door.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from laplace.engine import author_proxy, taste_retrieval

# Reuse the one ledger engine's IO where it's importable (superego lives inside the
# package, so no src-path bootstrap is needed); fall back to a local tolerant
# read/append if the pipeline import chain is unavailable in some thin context. This
# mirrors author_proxy's guard so both doors share a single write shape and its
# cross-process FileLock.
try:
    from laplace.pipeline.ledger import append_jsonl as _append_jsonl
    from laplace.pipeline.ledger import read_jsonl as _read_jsonl
except Exception:  # pragma: no cover - defensive: the fallback matches the engine's shape
    def _read_jsonl(path: Path | str) -> list[dict]:
        p = Path(path)
        if not p.is_file():
            return []
        out: list[dict] = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return out

    def _append_jsonl(path: Path | str, record: dict) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

#: his named stations — the boundaries where a done-claim is interrogated.
STATIONS: tuple[str, ...] = (
    "dispatch",         # a brief judged against the whole before work starts
    "candidate-lock",   # the whole-object reader tier
    "reach-him",        # the personified boundary, no theatre
    "close",            # the close gates
    "wave-close",       # the adversarial close of a whole wave
)

#: the two verdicts a judge returns. STANDS = the done-claim survives; REFUTED = it
#: does not. The judge is briefed to refute, so a STANDS is a survived attack.
VERDICTS: tuple[str, ...] = ("STANDS", "REFUTED")

#: defect severities, worst first. A verdict may STAND and still carry notes; it may
#: be REFUTED on a single fatal.
DEFECT_SEVERITIES: tuple[str, ...] = ("fatal", "must-fix", "cosmetic", "note")

#: THE JUDGE IDENTITY (WO-20260817-verdict-versioning). A verdict is a reading taken by
#: a particular evaluator; when that evaluator changes, the reading is no longer known to
#: hold. The lived specimen: the distilled metric M retrained on 2026-08-16 (AUC
#: 0.9317 -> 0.9908) and not one M-derived score or verdict was marked stale. So every
#: banked verdict now carries WHO judged it, in what version, leaning on which artefacts,
#: and a fingerprint over exactly that — staleness becomes a hash comparison, never a
#: memory. Rows banked before this block exists are read tolerantly (see
#: :func:`judge_identity_of`) and classed ``legacy``: never trusted fresh, never lost.
JUDGE_IDENTITY_SCHEMA = "judge.identity/1"

#: the evaluator this door writes for, and the version of the verdict spine it enforces.
#: BUMP ``EVALUATOR_VERSION`` whenever the spine or the derivation law changes: every
#: verdict banked under the old spine then fingerprints differently and reads STALE.
EVALUATOR = "laplace.engine.superego.bank_verdict"
EVALUATOR_VERSION = "1"

#: the judge classes. ``instance`` — a judging model instance, whose identity is its
#: name + model + version; the class that goes stale. ``mechanical`` — the
#: evaluator-independent floor (walker floors, unit tests, the register audit): the
#: reading is a property of the artefact, not of who took it, so it never goes stale.
#: ``legacy`` — a row banked before identity was stamped; unknown, never fresh.
JUDGE_CLASSES: tuple[str, ...] = ("instance", "mechanical", "legacy")

#: the staleness vocabulary returned by :func:`verdict_staleness`.
STALENESS_STATES: tuple[str, ...] = (
    "fresh",                 # identity fingerprints equal to the current judge
    "stale",                 # the judge changed under it — re-derive before trusting
    "unknown",               # identity incomplete on one side; freshness not decidable
    "evaluator-independent",  # the mechanical floor; no judge to go stale
)

#: the ledger, under repo_root — one JSON object per line, append-only. Appends go
#: through the one ledger engine (:func:`laplace.pipeline.ledger.append_jsonl`), whose
#: sidecar FileLock serialises writers across processes.
LEDGER_REL = ("contract", "judged_verdicts.jsonl")

#: the caps on each channel, and the per-quote character bound. The taste channel is
#: refs-only: the quote is the only free text an entry carries.
_TASTE_CAP = 6
_KNOWLEDGE_CAP = 8
_QUOTE_CAP = 400

#: the served-verdict vocabulary for a principal-question row, and the cap on how many
#: principal questions ride a packet.
SERVED_VALUES: tuple[str, ...] = ("yes", "partial", "no")
_QUESTIONS_CAP = 6

#: callable-shape docs travelling in every packet's ``bank`` slot — the contract a
#: dispatched judge fulfils to produce a bankable verdict. This module states the
#: shape; :func:`bank_verdict` performs the write (builder is not judge).
BANK_CONTRACT: dict = {
    "function": "laplace.engine.superego.bank_verdict",
    "signature": "bank_verdict(repo_root, record) -> dict",
    "stations": list(STATIONS),
    "verdicts": list(VERDICTS),
    "defect_severities": list(DEFECT_SEVERITIES),
    "served_values": list(SERVED_VALUES),
    "record_shape": {
        "station": "one of stations",
        "claim": "the done-claim under judgement (non-empty)",
        "verdict": "STANDS or REFUTED",
        "judge": "the ruling non-builder instance (non-empty, explicit, never defaulted)",
        "builder": "who produced the work under judgement (non-empty)",
        "questions": (
            "non-empty list of {question (non-empty), answer (non-empty prose), "
            "served in served_values} — the packet's principal questions, each answered "
            "so the ledger reads as prose a human can walk"
        ),
        "defects": "list of {severity in defect_severities, what, evidence}",
        "refs": "list of refs the verdict rests on",
        "judge_model": (
            "OPTIONAL — the model the judging instance ran as (explicit, never "
            "inherited). Absent lands an incomplete identity, which reads `unknown`"),
        "judge_version": (
            "OPTIONAL — the version/hash of the judge itself (prompt, panel, or "
            "scorer revision)"),
        "judge_artifacts": (
            "OPTIONAL — {name: digest} of the artefacts the judge leaned on (e.g. the "
            "distilled metric M): when one changes, dependent verdicts read STALE"),
        "judge_class": (
            f"OPTIONAL — one of {list(JUDGE_CLASSES)}; `mechanical` marks the "
            "evaluator-independent floor (walker floors, unit tests, register audit), "
            "which never goes stale. Default `instance`"),
    },
    "judge_identity_law": (
        "bank_verdict stamps a judge.identity/1 block on every verdict (name, class, "
        "model, version, artefact digests, evaluator + spine version, fingerprint). A "
        "judge change moves the fingerprint, and verdict_staleness/stale_verdicts read "
        "the dependent rows as STALE — re-derive on demand, never silently trust. Rows "
        "banked before the block exists read back as class `legacy`: unknown, never fresh"),
    "actor_guard": "judge must differ from builder — production never self-certifies",
    "derivation_law": (
        "the overall verdict derives from the principal questions: STANDS cannot carry a "
        "served=no answer, and REFUTED cannot have every answer served=yes"
    ),
    "id_shape": "SEV-<UTCstamp>, stamped by bank_verdict",
    "note": (
        "The dispatched judge returns a verdict record carrying the required spine, "
        "answering every principal question the packet raised; the consumer calls "
        "bank_verdict(repo_root, record), which stamps the id and ts and appends. The "
        "write is append-only: a change of mind is a later record, never an in-place "
        "edit. A verdict whose judge equals its builder is refused, as is a verdict "
        "whose overall call contradicts its own answered questions."
    ),
}


# ------------------------------------------------------------------ ledger IO
def _ledger_path(repo_root: Path | str) -> Path:
    """Resolve the verdict ledger under ``repo_root`` — mirrors the way
    ``author_proxy`` resolves its own ledger from the repo root. Reads and appends
    both travel through the one ledger engine (:mod:`laplace.pipeline.ledger`)."""
    return Path(repo_root).joinpath(*LEDGER_REL)


# ---------------------------------------------------------------- keyword selection
def _keywords(claim: str, extra: list | None) -> set[str]:
    """The selection set: substantive tokens (length >= 4) from the claim, plus every
    explicit keyword whole and its own tokens. Lower-cased throughout — selection is
    case-insensitive overlap, not ranking."""
    kws = set(re.findall(r"[a-z0-9]{4,}", (claim or "").lower()))
    for k in extra or []:
        text = str(k).lower().strip()
        if text:
            kws.add(text)
            kws.update(re.findall(r"[a-z0-9]{2,}", text))
    return kws


def _matches(text: str, keywords: set[str]) -> bool:
    """True when any selection keyword appears in ``text`` on a WORD BOUNDARY
    (case-insensitive). Boundary-anchored, not bare substring, so ``hold`` no longer
    matches ``threshold``. Deterministic: the caller iterates a fixed keyword set and
    the caps downstream are unchanged. An empty selection matches nothing, so a blank
    claim with no keywords retrieves no evidence rather than the whole corpus."""
    if not keywords:
        return False
    low = text.lower()
    return any(re.search(r"\b" + re.escape(kw) + r"\b", low) for kw in keywords)


# the taste channel now lives in :mod:`laplace.engine.taste_retrieval` — his rulings, his
# overrules of the machine, the stage stores, and the profiles, ranked by embedding cosine
# with a keyword fallback. :func:`assemble_packet` calls ``retrieve_taste``; the classic
# keyword-over-rulings loop is subsumed there (kept as the marked offline fallback).


# -------------------------------------------------------------- the knowledge channel
def _knowledge_entries(repo_root: Path, keywords: set[str]) -> list[dict]:
    """The engine's typed law: the ``structural`` clauses and ``counts`` laws across
    ``contract/surfaces/*.yaml``, selected by the same keyword overlap. Each entry
    carries the clause name, its bar (if present), its red marker (if present), and
    the source file. Missing PyYAML degrades to an empty channel rather than a crash."""
    try:
        import yaml  # type: ignore
    except Exception:
        return []

    surfaces_dir = repo_root / "contract" / "surfaces"
    if not surfaces_dir.is_dir():
        return []

    entries: list[dict] = []
    for path in sorted(surfaces_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue

        for row in data.get("structural") or []:
            if not isinstance(row, dict):
                continue
            clause = row.get("clause")
            if not clause:
                continue
            haystack = " ".join(str(v) for v in row.values() if v is not None)
            haystack += " " + " ".join(str(k) for k in row.keys())
            if not _matches(haystack, keywords):
                continue
            entry = {"source": path.name, "clause": str(clause)}
            if row.get("bar") is not None:
                entry["bar"] = row.get("bar")
            if row.get("red") is not None:
                entry["red"] = row.get("red")
            entries.append(entry)

        counts = data.get("counts")
        if isinstance(counts, dict):
            law = counts.get("law")
            if law is not None and _matches(str(counts), keywords):
                entries.append({"source": path.name, "clause": f"counts:{law}"})

    return entries[:_KNOWLEDGE_CAP]


# ------------------------------------------------ the principal questions (his ruling)
def _surface_purpose(repo_root: Path, surface: str) -> str:
    """The ``purpose:`` line of ``contract/surfaces/<surface>.yaml``, or ``""``. Token-free
    and tolerant: a missing file or absent PyYAML degrades to no question, never a crash."""
    path = repo_root / "contract" / "surfaces" / f"{surface}.yaml"
    if not path.is_file():
        return ""
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return ""
    if isinstance(data, dict) and data.get("purpose"):
        return str(data["purpose"]).strip()
    return ""


def _goal_essences(repo_root: Path, corpus: str) -> list[str]:
    """The essences of the goal-kind nodes in ``corpus_friction/<corpus>.jsonl``, in
    file order. A node is goal-kind when an ``add-node`` record carries ``node_kind ==
    "goal"`` or a ``set-kind`` record carries ``value == "goal"`` — the record shapes
    ``corpus_ingest.rewire_add`` writes. Essence comes from the node's ``add-node``
    record; a node named goal only by ``set-kind`` falls back to its own id."""
    path = repo_root / "corpus_friction" / f"{corpus}.jsonl"
    records = _read_jsonl(path)
    essence_by_node: dict[str, str] = {}
    goal_nodes: list[str] = []
    superseded: set[str] = set()
    for row in records:
        if not isinstance(row, dict):
            continue
        kind = row.get("kind")
        node = row.get("node")
        if not node:
            continue
        node = str(node)
        if kind == "add-node":
            if row.get("essence") is not None:
                essence_by_node.setdefault(node, str(row["essence"]).strip())
            if row.get("node_kind") == "goal" and node not in goal_nodes:
                goal_nodes.append(node)
            # the supersede reduction (the G1 judge's must-fix): a goal-v2 record that
            # supersedes goal-v1 retires v1 from the question set the same way the
            # overlay retires it from the tree - the holder of the whole must never
            # ask a stale question about a goal the substrate already replaced.
            sup = row.get("supersedes")
            if sup and str(sup) != node:
                superseded.add(str(sup))
    for row in records:
        if not isinstance(row, dict) or row.get("kind") != "set-kind":
            continue
        node = row.get("node")
        if node and row.get("value") == "goal" and str(node) not in goal_nodes:
            goal_nodes.append(str(node))
    return [essence_by_node.get(node) or node
            for node in goal_nodes if node not in superseded]


#: the standing close-station question (his ruling 2026-07-22, after the consumer
#: was foreseen, typed red, and still not built): a reds review orders by loudness;
#: only an essentiality walk orders by what the engine cannot do without. Asked at
#: every close-class station, forever - a standing organ, never a session-ephemeral
#: check.
ESSENTIAL_PATH_QUESTION = (
    "Walk the loop end to end as it would really run, without him: what breaks first, "
    "and is anything on that essential path typed-but-unbuilt - a debt whose loud "
    "marker is standing in for the organ itself?")

_CLOSE_STATIONS = ("wave-close", "close", "reach-him")


def derive_principal_questions(repo_root: Path | str, corpus: str | None = None,
                               surface: str | None = None,
                               station: str | None = None) -> list[str]:
    """The principal questions an object must answer — his ruling (2026-07-22): the
    superego is run on asking the principal questions of an object, and whether it has
    succeeded in serving them, in a manner a human can read.

    Mechanical and token-free: from a ``surface`` name, the ``purpose`` line of
    ``contract/surfaces/<surface>.yaml``; from a ``corpus`` name, the essence of any
    goal-kind node in ``corpus_friction/<corpus>.jsonl``. Bounded (:data:`_QUESTIONS_CAP`),
    deterministic, deduplicated — surface purpose first, then goal essences in file order.
    """
    repo = Path(repo_root)
    seeds: list[str] = []
    if surface:
        purpose = _surface_purpose(repo, surface)
        if purpose:
            seeds.append(f"Does the object serve its stated purpose — {purpose}?")
    if corpus:
        for essence in _goal_essences(repo, corpus):
            if essence:
                seeds.append(f"Has the object achieved its goal — {essence}?")

    if station in _CLOSE_STATIONS:
        seeds.append(ESSENTIAL_PATH_QUESTION)

    out: list[str] = []
    seen: set[str] = set()
    for q in seeds:
        if q not in seen:
            seen.add(q)
            out.append(q)
    return out[:_QUESTIONS_CAP]


# ------------------------------------------------------------------ the packet
def assemble_packet(repo_root: Path | str, claim: str, station: str, builder: str,
                    refs: list | None = None, keywords: list | None = None,
                    principal_questions: list | None = None,
                    corpus: str | None = None, surface: str | None = None) -> dict:
    """One done-claim → one dispatch-ready judge packet. Deterministic, no generative model
    call (the taste ranking uses the deterministic embedding router; a keyword fallback when
    it is offline — see ``frame.taste_provenance``).

    The fusion frame he ratified rides here, its taste channel threaded to the implicit
    substrate: ``frame.taste`` is up to six refs-only items — his rulings, his overrules of
    the machine (always surfaced when they match), the stage stores of his corpus, and his
    architecture/voice/house-style profile fields — ranked by raw embedding cosine against
    the claim (``frame.taste_provenance`` records the ranking method, the model, and that the
    stale metric was skipped). ``frame.knowledge``
    is up to eight matching typed clauses (the ``structural`` rows and ``counts`` laws of
    ``contract/surfaces/*.yaml``) with clause name, bar, and red marker. Both channels select
    by case-insensitive keyword overlap with ``claim`` (plus any explicit ``keywords``).

    His ruling (2026-07-22) also rides here: the packet carries ``principal_questions`` — the
    questions the object must answer, that a verdict is derived from. Explicit questions passed
    by the caller ride first, then any derived from ``surface``/``corpus`` via
    :func:`derive_principal_questions`; the list is deduplicated and capped at
    :data:`_QUESTIONS_CAP`. The bank docs tell the judge every verdict must answer them.

    The packet mirrors the growth adjudicator's shape: ``{kind, station, claim, builder,
    refs, principal_questions, frame, bank}``, where ``bank`` is :data:`BANK_CONTRACT` —
    callable-shape docs telling the judge exactly what a bankable verdict looks like, without
    this module ever writing.

    Raises :class:`ValueError` on an unknown station or an empty claim or builder.
    """
    if station not in STATIONS:
        raise ValueError(
            f"unknown station {station!r}; expected one of {list(STATIONS)}")
    if not str(claim).strip():
        raise ValueError("claim must be a non-empty done-claim")
    if not str(builder).strip():
        raise ValueError("builder must be named (non-empty)")

    repo = Path(repo_root)
    kws = _keywords(claim, keywords)

    # explicit questions ride first, then the derived ones; dedupe, preserve order, cap.
    questions: list[str] = []
    seen: set[str] = set()
    for q in list(principal_questions or []) + derive_principal_questions(
            repo, corpus=corpus, surface=surface, station=station):
        text = str(q).strip()
        if text and text not in seen:
            seen.add(text)
            questions.append(text)
    questions = questions[:_QUESTIONS_CAP]

    # the taste channel, threaded to the implicit substrate (his ruling 2026-07-22): his
    # verbatim rulings AND his overrules of the machine AND the stage stores of his corpus
    # AND the architecture/voice/house-style profiles, ranked by raw embedding cosine
    # (keyword overlap the marked offline fallback; the stale metric skipped, not applied).
    taste = taste_retrieval.retrieve_taste(repo, kws, claim, _TASTE_CAP)

    return {
        "kind": "superego-packet",
        "station": station,
        "claim": claim,
        "builder": builder,
        "refs": list(refs or []),
        "principal_questions": questions,
        "frame": {
            "taste": taste["entries"],
            "taste_provenance": taste["provenance"],
            "knowledge": _knowledge_entries(repo, kws),
        },
        "bank": BANK_CONTRACT,
    }


# ------------------------------------------------------------------ the write door
def _actor_key(name: str) -> str:
    """One comparable key per actor identity: NFKC-normalise (full-width and
    combining forms collapse), drop format characters (zero-width joiners and
    spaces, category Cf), then strip and casefold. Closes the unicode dodges the
    v2 refutation demonstrated against the bare casefold compare."""
    normalised = unicodedata.normalize("NFKC", name)
    visible = "".join(ch for ch in normalised if unicodedata.category(ch) != "Cf")
    return visible.strip().casefold()


# ------------------------------------------------------------ the judge identity
def artifact_digest(path: Path | str) -> str | None:
    """A short content digest for an artefact a judge leans on (the distilled metric,
    a frozen basis, a scoring table). ``None`` when the file is absent — an absent
    artefact is recorded as unknown, which makes the identity incomplete and the
    verdicts resting on it un-freshenable, rather than silently equal."""
    p = Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def judge_fingerprint(identity: dict) -> str:
    """The fingerprint over an identity's IDENTIFYING components — name, model,
    version, the artefact digests, and the evaluator + its spine version. Canonical
    JSON, sorted keys, so the same judge fingerprints the same on any machine and a
    changed artefact digest moves it."""
    core = {
        "name": str(identity.get("name") or ""),
        "model": identity.get("model"),
        "version": identity.get("version"),
        "artifacts": {str(k): str(v) for k, v in
                      sorted((identity.get("artifacts") or {}).items())},
        "evaluator": identity.get("evaluator") or EVALUATOR,
        "evaluator_version": identity.get("evaluator_version") or EVALUATOR_VERSION,
    }
    blob = json.dumps(core, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def judge_identity(name: str, *, model: str | None = None, version: str | None = None,
                   artifacts: dict | None = None,
                   judge_class: str = "instance") -> dict:
    """Build a judge-identity block. ``complete`` is the honest half: an instance judge
    is complete only when BOTH its model and its version are named; a mechanical judge
    needs only its version (there is no model to change under it). An incomplete
    identity can never certify freshness — it reads ``unknown``, which is the true
    answer, not a green one."""
    if judge_class not in JUDGE_CLASSES:
        raise ValueError(
            f"judge_class must be one of {list(JUDGE_CLASSES)}: {judge_class!r}")
    arts = {str(k): str(v) for k, v in (artifacts or {}).items()}
    ident = {
        "schema": JUDGE_IDENTITY_SCHEMA,
        "name": str(name or "").strip(),
        "judge_class": judge_class,
        "model": str(model).strip() if model else None,
        "version": str(version).strip() if version else None,
        "artifacts": arts,
        "evaluator": EVALUATOR,
        "evaluator_version": EVALUATOR_VERSION,
    }
    if judge_class == "legacy":
        ident["complete"] = False
    elif judge_class == "mechanical":
        ident["complete"] = bool(ident["version"])
    else:
        ident["complete"] = bool(ident["model"]) and bool(ident["version"])
    ident["unstamped"] = [k for k in ("model", "version")
                          if not ident[k] and not (judge_class == "mechanical"
                                                   and k == "model")]
    ident["fingerprint"] = judge_fingerprint(ident)
    return ident


def judge_identity_of(row: dict) -> dict:
    """READER TOLERANCE. The identity of a banked verdict, whether or not it was banked
    with one. A row written before this organ existed carries only a bare ``judge``
    string: it is read back as a ``legacy`` identity — the name preserved, the model and
    version unknown, ``complete`` false. Nothing is dropped and nothing is invented; the
    old row keeps its place in the ledger and simply never reads fresh."""
    if not isinstance(row, dict):
        raise ValueError("row must be a dict")
    ident = row.get("judge_identity")
    if isinstance(ident, dict) and ident.get("name"):
        out = dict(ident)
        out.setdefault("schema", JUDGE_IDENTITY_SCHEMA)
        out.setdefault("judge_class", "instance")
        out.setdefault("model", None)
        out.setdefault("version", None)
        out.setdefault("artifacts", {})
        out.setdefault("evaluator", EVALUATOR)
        out.setdefault("evaluator_version", EVALUATOR_VERSION)
        out.setdefault("complete", bool(out["model"]) and bool(out["version"]))
        out.setdefault("unstamped", [k for k in ("model", "version") if not out[k]])
        out.setdefault("fingerprint", judge_fingerprint(out))
        return out
    return judge_identity(str(row.get("judge") or "").strip() or "unnamed-judge",
                          judge_class="legacy")


def verdict_staleness(row: dict, current: dict | None = None) -> dict:
    """Is this banked verdict still the reading of the judge in front of us?

    ``current`` is the identity of the judge as it stands NOW (from
    :func:`judge_identity`). The states are :data:`STALENESS_STATES`; every answer
    carries the reason and the two fingerprints it was read off, so a caller can show
    its work. The atlas staleness idiom: nothing is re-derived here — the row is
    labelled, and re-derivation happens on demand.
    """
    ident = judge_identity_of(row)
    was = ident.get("fingerprint")
    now = current.get("fingerprint") if isinstance(current, dict) else None
    base = {"id": row.get("id"), "judge": ident.get("name"),
            "judge_class": ident.get("judge_class"),
            "banked_fingerprint": was, "current_fingerprint": now}
    if ident.get("judge_class") == "mechanical":
        return {**base, "state": "evaluator-independent",
                "reason": "a mechanical-floor verdict: the reading is a property of "
                          "the artefact, not of who took it"}
    if current is None:
        return {**base, "state": "unknown",
                "reason": "no current judge identity supplied — freshness is not decidable"}
    if not ident.get("complete"):
        miss = ", ".join(ident.get("unstamped") or []) or "identity"
        return {**base, "state": "unknown",
                "reason": f"the banked identity is incomplete (unstamped: {miss})"}
    if not current.get("complete"):
        miss = ", ".join(current.get("unstamped") or []) or "identity"
        return {**base, "state": "unknown",
                "reason": f"the current judge identity is incomplete (unstamped: {miss})"}
    if was == now:
        return {**base, "state": "fresh",
                "reason": "the judge is unchanged since the verdict was banked"}
    return {**base, "state": "stale",
            "reason": "the judge changed since this verdict was banked — re-derive "
                      "before trusting it"}


def stale_verdicts(repo_root: Path | str, current: dict | None = None, *,
                   claim_substr: str | None = None, station: str | None = None,
                   limit: int = 200, include_unknown: bool = True) -> list[dict]:
    """Every banked verdict that is NOT known to still hold under ``current``, newest
    first — the staleness sweep a judge change fires. ``include_unknown`` keeps the
    legacy/incomplete rows in the answer (default: they are exactly the rows the
    M-retrain lesson was about); set it False for the strict-mismatch list alone."""
    keep = {"stale"} | ({"unknown"} if include_unknown else set())
    out: list[dict] = []
    for row in verdicts_for(repo_root, claim_substr=claim_substr, station=station,
                            limit=limit):
        report = verdict_staleness(row, current)
        if report["state"] in keep:
            out.append(report)
    return out


def _validate_verdict(record: dict) -> None:
    """Enforce the verdict spine. The actor guard is checked last and quotes the law it
    serves, so its refusal message names the standing ruling."""
    if not isinstance(record, dict):
        raise ValueError("verdict record must be a dict")

    station = record.get("station")
    if station not in STATIONS:
        raise ValueError(
            f"station must be one of {list(STATIONS)}: {station!r}")

    if not str(record.get("claim", "")).strip():
        raise ValueError("claim must be a non-empty done-claim")

    verdict = record.get("verdict")
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {list(VERDICTS)}: {verdict!r}")

    judge = str(record.get("judge", "")).strip()
    if not judge:
        raise ValueError("judge must be named explicitly (non-empty, never defaulted)")

    builder = str(record.get("builder", "")).strip()
    if not builder:
        raise ValueError("builder must be named (non-empty)")

    # The judge-identity inputs (optional, but shape-checked when present): the class,
    # the model, the version, and the artefact digests the judge leaned on. Absence is
    # legal and honest — it lands as an incomplete identity, never as a silent green.
    jclass = record.get("judge_class", "instance")
    if jclass not in JUDGE_CLASSES:
        raise ValueError(
            f"judge_class must be one of {list(JUDGE_CLASSES)}: {jclass!r}")
    arts = record.get("judge_artifacts")
    if arts is not None and not isinstance(arts, dict):
        raise ValueError(
            "judge_artifacts must be a dict of {artefact name: digest} — the things "
            "whose change makes this verdict stale")

    # The principal-question spine (his ruling, 2026-07-22): every verdict answers the
    # object's principal questions, in prose a human can walk. A non-empty list of rows,
    # each {question, answer, served}. The overall verdict derives from these answers.
    questions = record.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError(
            "questions must be a non-empty list of {question, answer, served} rows -- "
            "'the overall verdict derives from the principal questions'")
    served_seen: list[str] = []
    for q in questions:
        if not isinstance(q, dict):
            raise ValueError("each question row must be a dict {question, answer, served}")
        if not str(q.get("question", "")).strip():
            raise ValueError("each question row must carry a non-empty 'question'")
        if not str(q.get("answer", "")).strip():
            raise ValueError("each question row must carry a non-empty 'answer' (prose)")
        served = q.get("served")
        if served not in SERVED_VALUES:
            raise ValueError(
                f"served must be one of {list(SERVED_VALUES)}: {served!r}")
        served_seen.append(served)

    defects = record.get("defects")
    if not isinstance(defects, list):
        raise ValueError("defects must be a list of {severity, what, evidence}")
    for defect in defects:
        if not isinstance(defect, dict):
            raise ValueError("each defect must be a dict {severity, what, evidence}")
        if defect.get("severity") not in DEFECT_SEVERITIES:
            raise ValueError(
                f"defect severity must be one of {list(DEFECT_SEVERITIES)}: "
                f"{defect.get('severity')!r}")
        if "what" not in defect or "evidence" not in defect:
            raise ValueError("each defect must carry 'what' and 'evidence'")

    # Severity coherence: this module's own vocabulary calls a fatal refutation-grade,
    # so a STANDS carrying one is a self-contradictory record and the door refuses it
    # (the v2 refutation's catch: the ledger must not bank what the intent disowns).
    if record.get("verdict") == "STANDS" and any(
            d.get("severity") == "fatal" for d in defects):
        raise ValueError(
            "a STANDS verdict cannot carry a fatal defect -- a fatal is "
            "refutation-grade by this ledger's own vocabulary")

    if not isinstance(record.get("refs"), list):
        raise ValueError("refs must be a list")

    # The derivation law: the overall verdict is read off the answered questions. A
    # STANDS cannot carry an unserved (served=no) question; a REFUTED cannot have every
    # question fully served. Either contradiction is refused, quoting the law.
    if verdict == "STANDS" and "no" in served_seen:
        raise ValueError(
            "a STANDS verdict cannot carry a served=no question -- "
            "'the overall verdict derives from the principal questions'")
    if verdict == "REFUTED" and all(s == "yes" for s in served_seen):
        raise ValueError(
            "a REFUTED verdict cannot have every question served=yes -- "
            "'the overall verdict derives from the principal questions'")

    # The actor guard: a builder cannot certify his own work. Identities are compared
    # through _actor_key (NFKC + format-character drop + casefold) so casing,
    # whitespace, full-width, and zero-width games cannot dodge the law. The strings
    # remain caller-supplied - the key raises the cost of spoofed equality, and a real
    # actor registry is later law. The refusal quotes the standing ruling.
    if _actor_key(judge) == _actor_key(builder):
        raise ValueError(
            "actor guard: judge equals builder -- 'production never self-certifies'. "
            "A done-claim must be judged by a non-builder instance to count.")


def bank_verdict(repo_root: Path | str, record: dict) -> dict:
    """The single append-only write door. Validate ``record`` against the verdict spine,
    refuse when the judge is the builder (quoting the law), stamp an ``id`` (``SEV-`` plus
    a UTC timestamp) and a ``ts``, append, and return the stored record.

    A change of verdict is a later record, never an in-place edit — the ledger is
    append-only, and :func:`verdicts_for` reads newest first.
    """
    _validate_verdict(record)
    stored = dict(record)
    now = _dt.datetime.now(_dt.timezone.utc)
    stored["id"] = "SEV-" + now.strftime("%Y%m%dT%H%M%SZ")
    stored["ts"] = now.isoformat()
    # WO-20260817-verdict-versioning: the verdict carries WHO judged it. The block is
    # always stamped — a judge that named no model/version lands incomplete, which reads
    # `unknown`, not fresh. A caller may supply its own block; the name is forced to the
    # record's judge and the fingerprint is always recomputed here, so the identity can
    # never disagree with the verdict it rides on.
    supplied_ident = stored.get("judge_identity")
    if isinstance(supplied_ident, dict):
        stored["judge_identity"] = judge_identity(
            str(stored.get("judge", "")).strip(),
            model=supplied_ident.get("model"),
            version=supplied_ident.get("version"),
            artifacts=supplied_ident.get("artifacts"),
            judge_class=supplied_ident.get("judge_class",
                                           stored.get("judge_class", "instance")))
    else:
        stored["judge_identity"] = judge_identity(
            str(stored.get("judge", "")).strip(),
            model=stored.get("judge_model"),
            version=stored.get("judge_version"),
            artifacts=stored.get("judge_artifacts"),
            judge_class=stored.get("judge_class", "instance"))
    # The composition layer (DESIGN_2026-07-22, A.2): a verdict carries a composed
    # account minted from its questions-as-prose. A judge that authored its own block
    # is validated and kept; otherwise one is composed here. A block that cannot be
    # composed (an account field would carry barred vocabulary) is left absent — the
    # bank door still banks the verdict; the fallback law renders the absence.
    from laplace.pipeline import composed as _composed
    supplied = stored.get("composed")
    if supplied is not None:
        _composed.validate_composed(supplied)
    else:
        composed_block = _compose_verdict(stored)
        if composed_block is not None:
            stored["composed"] = composed_block
    _append_jsonl(_ledger_path(repo_root), stored)
    return stored


def _gravest_defect(defects: list) -> str:
    """The plainest sentence naming the worst defect, or an empty string when clean.
    Severity order: fatal, then major, then minor."""
    order = {"fatal": 0, "major": 1, "minor": 2}
    ranked = sorted((d for d in defects if isinstance(d, dict)),
                    key=lambda d: order.get(d.get("severity"), 9))
    if not ranked:
        return ""
    return str(ranked[0].get("what", "")).strip().rstrip(".")


#: prose destined for glance/working is masked into plain words — the raw claim,
#: ids, and paths stay on the record itself (the audit altitude). Masking beats
#: refusing: an engineering claim naming a module is the common case, and banking
#: bare there would starve the account exactly where it is most read
#: (the E1 adversarial close's must-fix, SEV-20260722T145424Z).
_PLAIN_MASKS = (
    (re.compile(r"src/laplace/[\w/.-]+"), "a source module"),
    (re.compile(r"\b[A-Z]{2,4}-\d[\w:.TZ-]*"), "a banked record"),
    (re.compile(r"\bsec:s\d+\b"), "a section anchor"),
)


def _plain_prose(text: str) -> str:
    for rx, word in _PLAIN_MASKS:
        text = rx.sub(word, text)
    return text


def _compose_verdict(rec: dict) -> dict | None:
    """The composed account for a banked verdict, minted from its principal
    questions-as-prose with barred vocabulary masked into plain words. Returns
    ``None`` only when even the masked account is refused (the fallback law then
    renders the absence rather than the door)."""
    from laplace.pipeline import composed as _composed
    claim = _plain_prose(str(rec.get("claim", "")).strip().rstrip("."))
    verdict = rec.get("verdict")
    questions = rec.get("questions") or []
    gravest = _plain_prose(_gravest_defect(rec.get("defects") or []))
    if verdict == "STANDS":
        glance = f"A done-claim was judged and it stands: {claim}."
        if gravest:
            glance += f" One caveat was noted: {gravest}."
    else:
        glance = f"A done-claim was judged and it does not stand: {claim}."
        if gravest:
            glance += f" The gravest fault: {gravest}."
    served_word = {"yes": "served", "partial": "partly served", "no": "unserved"}
    lines: list[str] = []
    for q in questions:
        qq = _plain_prose(str(q.get("question", "")).strip().rstrip("?"))
        ans = _plain_prose(str(q.get("answer", "")).strip().rstrip("."))
        sw = served_word.get(q.get("served"), str(q.get("served")))
        if qq and ans:
            lines.append(f"On whether {qq[:1].lower()}{qq[1:]}: {ans} ({sw}).")
    working = " ".join(lines) or "The claim was judged against its principal questions."
    audit = {"ids": [str(rec.get("id", ""))],
             "provenance": [str(r) for r in (rec.get("refs") or [])], "citations": []}
    sfp = _composed.fingerprint(
        claim + " " + " ".join(str(q.get("question", "")) + str(q.get("answer", ""))
                               for q in questions))
    try:
        return _composed.make_composed(
            glance=glance, working=working, decision=None, audit=audit,
            minted_by=str(rec.get("judge") or "the judge instance"),
            substrate_fingerprint=sfp, goal_version=None,
            record_ids=[str(rec.get("id", ""))])
    except ValueError:
        return None


# ------------------------------------------------------------------ the reads
def verdicts_for(repo_root: Path | str, claim_substr: str | None = None,
                 station: str | None = None, limit: int = 20) -> list[dict]:
    """Banked verdicts, newest first, optionally filtered by a case-insensitive
    ``claim_substr`` and an exact ``station``. Capped at ``limit``."""
    rows = _read_jsonl(_ledger_path(repo_root))
    rows.sort(key=lambda r: str(r.get("ts", "")), reverse=True)
    needle = (claim_substr or "").lower()
    out: list[dict] = []
    for row in rows:
        if station is not None and row.get("station") != station:
            continue
        if needle and needle not in str(row.get("claim", "")).lower():
            continue
        out.append(row)
        if len(out) >= max(0, limit):
            break
    return out


def latest_verdict(repo_root: Path | str, claim_substr: str) -> dict | None:
    """The newest banked verdict whose claim contains ``claim_substr``, or ``None``."""
    hits = verdicts_for(repo_root, claim_substr=claim_substr, limit=1)
    return hits[0] if hits else None
