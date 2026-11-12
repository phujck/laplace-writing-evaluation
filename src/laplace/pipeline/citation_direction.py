"""The citation-direction organ — the literature door of the research agenda.

His held-out prediction scored TRUE (EVIDENCE_the-fixed-point_2026-07-17.md): the
loop could not close the bibliography basin by iterating; it closed only when the
organs EXISTED. The gap ledger's substrate-absent branch (:mod:`gap_ledger`) types a
citation-grounding gap as a ``literature`` RESEARCH INTENT and routes it to THIS
organ (``door: "citation-direction"``). The bibliography stage
(:mod:`bibliography_stage`) types every DANGLING cite key the same way. This module
is the door those intents wait at (ARMING_2026-07-16 §1(f), the substrate-absent
branch, literature leg).

The four stages, each a plain, durable organ:

1. INPUT — :func:`collect_intents` reads the two contracted intent sources off disk:
   the bibliography manifest (``dangling`` keys + any banked ``intents`` of class
   ``literature``) and the shared research-intent ledger (``research_intents.jsonl``,
   the gap_ledger ``to_research_intents`` shape filtered to ``literature``). Plus the
   VERIFICATION lane (:func:`scan_verification_intents`): a mechanical reader that
   types the manuscript's OWN door-pending citation claims — a ``\\cite`` sitting by a
   ``not been checked against`` / ``unverified pending`` / ``through the door`` tell is
   a resolved-but-UNVERIFIED intent (the falqon distrust appendix names these by
   hand; this reader types them mechanically). A dangling key has no source; a
   verification intent has the wrong/unverified source — both are literature work.

2. DIRECTED RETRIEVAL — candidates from what is LAWFULLY REACHABLE, local FIRST:
   :func:`reference_corpus_candidates` ranks the on-disk ``reference_corpus/`` refs by
   content-word overlap of the claim (deterministic, offline — the same Jaccard
   machinery :mod:`readers.source_delta` uses, no model call). Then, if the network
   leg is reachable, :func:`arxiv_candidates` fetches arXiv metadata (title + abstract
   + authors + year) for the same claim. The network leg DEGRADES Plainly: one probe
   (:func:`probe_arxiv`); if the proxy blocks it the organ returns local-only
   candidates and banks the network leg as ``attested-available`` with its enable
   documented (:data:`ARXIV_ENABLE_NOTE`) — never a silent skip, never a fabricated
   candidate.

3. ENTAILMENT CHECK — machine-checkable PREFILTERS run in code
   (:func:`machine_prefilter`: title/id/year resolution, salient-term floor — a
   candidate with zero claim-term overlap or a hard year contradiction is REJECTED
   here, the mechanical floor). Everything that survives the floor is NOT admitted by
   cosine: it becomes a JUDGE PACKET (:func:`entailment_packet`) in the
   growth_adjudicator idiom — ``{claim, candidate text, entailment_law}`` — and the
   packets emit as a dispatch manifest (:func:`emit_entailment_manifest`). A candidate
   is ADMITTED only when a dispatched judge rules ENTAILS against the candidate's
   abstract/text. Topical adjacency is NOT entailment: the falqon mis-anchor
   (``childs2012hamiltonian`` cited for an amplitude-estimation constant — the
   adjacent LCU paper, not the canonical Brassard reference) is exactly the
   cosine-would-admit / entailment-rejects case this stage exists to catch.

4. ADMISSION — on an ENTAILS verdict, :func:`apply_admission` lands the source as a
   CITATION-NODE (epistemic provenance ``cited`` + the entailment verdict ref) through
   the existing conceptric ingest gate (:func:`adjudicate.make_conceptric_intent`
   shape) AND writes its BibTeX so :mod:`bibliography_stage` RESOLVES the key and the
   reference RENDERS. Rejected / unresolved / needs-judge intents stay TYPED intents —
   never silently dropped (the run record banks every bucket).

TELEMETRY — :func:`write_run_sidecar` banks a per-run sidecar (the form-channel
sidecar idiom): the network leg's state, the corpus probed, and per-intent candidate
+ bucket counts, so a run is a watchable object without re-reading the manifests.

The honesty law, wired: the run record states ran-vs-compiled plainly — retrieval +
prefilter + manifest emission RAN; the judge-tier admission is COMPILED (the manifest
is emitted; ``admitted`` stays 0 until a dispatched judge consumes it). Epistemic
provenance travels with substrate: an admitted source is ``cited``; an unresolved
intent carries no substrate and makes no claim it cannot back.

Pure at import (no filesystem/network at module load). The only network call is the
explicit arXiv probe/fetch, guarded and degrade-safe.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from laplace.pipeline.readers import source_delta as SD
from laplace.pipeline.schema import NODE_ID_RE, canonical_status, token_for

# --------------------------------------------------------------------------- #
# Laws + constants
# --------------------------------------------------------------------------- #

#: the desk-rejection's ENTAILMENT LAW — the contract a dispatched judge applies to
#: every candidate. Stated once here, carried verbatim in every judge packet. The
#: mis-anchor clause is the falqon datum: topical adjacency is NOT entailment.
ENTAILMENT_LAW = (
    "A candidate source is ADMITTED for a claim ONLY IF the candidate's abstract/text "
    "ENTAILS the claim it must support — the source STATES, PROVES, or MEASURES what "
    "the prose asserts it does, at the specificity the prose leans on it for. Topical "
    "adjacency is NOT entailment: a paper in the same field, or one that mentions the "
    "same method, does NOT support a specific constant, scaling, or result unless it "
    "actually establishes THAT quantity. The mis-anchor fault (an LCU / "
    "Hamiltonian-simulation paper cited for an amplitude-estimation constant) is a "
    "REJECT even though both are quantum-algorithms papers. Rule exactly one of: "
    "ENTAILS (admit, epistemic provenance 'cited'), NOT-ENTAILS (reject — name the "
    "better source class if known), INSUFFICIENT-TEXT (the abstract alone cannot "
    "settle it — needs the full source, stays a typed intent)."
)

#: the arXiv metadata endpoint (Atom API) — the reachable network leg.
ARXIV_ENDPOINT = "http://export.arxiv.org/api/query"

#: the network leg's enable, documented so a blocked run degrades HONESTLY rather
#: than silently. Banked into the run record whenever the probe fails.
ARXIV_ENABLE_NOTE = (
    "network leg = arXiv metadata (Atom API) at " + ARXIV_ENDPOINT + ". Enable: allow "
    "outbound HTTPS/HTTP to export.arxiv.org through the agent proxy. When blocked, "
    "candidates come from reference_corpus/ only and this leg is attested-available."
)

#: door-pending TELLS — a manuscript's own admission that a cited claim is not yet
#: source-verified (the verification lane). Matched near a ``\\cite`` to type a
#: resolved-but-unverified literature intent. Mechanical floor; the semantic call is
#: the judge's, exactly as :mod:`citation_audit`'s tells work.
_DOOR_PENDING_TELL = re.compile(
    r"(?:not\s+(?:yet\s+)?been\s+checked\s+against"
    r"|has\s+not\s+been\s+checked"
    r"|unverified\s+pending"
    r"|through\s+the\s+door"
    r"|not\s+yet\s+done"
    r"|deferred\s+until"
    r"|once\s+fetched"
    r"|remains?\s+unconfirmed"
    r"|not\s+(?:re-?)?derived"
    r"|pending\s+(?:on\s+)?(?:a\s+)?(?:door|external|source)"
    r"|kept\s+qualitative"
    r"|enter[s]?\s+(?:as\s+)?(?:literature\s+records?|through\s+the\s+door))",
    re.I)

_CITE_RE = re.compile(r"\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
_SECTION_GLOBS = ("s*.tex", "appendix_*.tex", "abstract.tex")
#: an unescaped LaTeX line comment (``%`` not preceded by a backslash) to end of line.
_TEX_COMMENT_RE = re.compile(r"(?<!\\)%.*")
#: a bib entry's arXiv id, from its ``note = {arXiv:XXXX.XXXXX}`` field.
_ARXIV_ID_RE = re.compile(r"arXiv:\s*([0-9]{4}\.[0-9]{4,5}(?:v\d+)?|[a-z\-]+/[0-9]{7})",
                          re.I)

#: intent classes this organ services (both are literature work).
INTENT_DANGLING = "dangling"          # cited, no .bib source
INTENT_VERIFICATION = "verification"  # cited + resolved, but source unverified

#: the admission buckets a run banks — every intent lands in exactly one.
BUCKETS = ("admitted", "needs-judge", "rejected", "no-candidate")


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #


@dataclass
class LiteratureIntent:
    """A literature-class research intent: a CLAIM that needs an external source.
    ``key`` is the cite key when one exists (dangling / verification); ``claim`` is
    the prose the source must ENTAIL (extracted from the manuscript, not the generic
    manifest note)."""

    id: str
    key: str
    claim: str
    section: str = ""
    lane: str = INTENT_DANGLING          # INTENT_DANGLING | INTENT_VERIFICATION
    note: str = ""
    source: str = "citation_direction"
    research_class: str = "literature"
    #: the entailed-claim CONCEPTRIC NODE this source must support, when the intent
    #: rides one. A gap-ledger literature intent carries its originating node (the
    #: ungrounded claim's ``where``); a manuscript-scanned intent (dangling /
    #: verification) has only a section + the claim sentence, so it stays "" and the
    #: admission banks an honest unresolved marker rather than edging a guess.
    claim_node: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Candidate:
    """A retrieved candidate source. ``text`` is the entailment-checkable material
    (title + abstract) surfaced to the judge; ``provenance`` names where it came
    from (``reference_corpus`` | ``arxiv``) so the epistemic chain is auditable."""

    cand_id: str
    title: str
    year: Optional[int]
    authors: list[str]
    provenance: str                       # reference_corpus | arxiv
    abstract: str = ""
    arxiv_id: str = ""
    doi: str = ""
    match_score: float = 0.0              # deterministic retrieval score (NOT admission)

    @property
    def text(self) -> str:
        parts = [self.title.strip()]
        if self.abstract.strip():
            parts.append(self.abstract.strip())
        return "\n\n".join(p for p in parts if p)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["text"] = self.text
        return d


@dataclass
class IntentResult:
    """One intent's full ledger: the candidates found, the machine-rejected set, the
    survivors that became judge packets, and the bucket the intent lands in."""

    intent: dict
    candidates: list[dict] = field(default_factory=list)
    rejected_code: list[dict] = field(default_factory=list)   # {cand_id, reason}
    needs_judge: list[str] = field(default_factory=list)      # cand_ids in the manifest
    manifest_path: str = ""
    bucket: str = "no-candidate"


# --------------------------------------------------------------------------- #
# 1. INPUT — collect literature intents
# --------------------------------------------------------------------------- #


def _section_files(mdir: Path) -> list[Path]:
    out: list[Path] = []
    for g in _SECTION_GLOBS:
        for p in sorted(mdir.glob(g)):
            if p not in out:
                out.append(p)
    return out


def _strip_tex_comments(text: str) -> str:
    """Drop unescaped ``%`` line comments (LaTeX) — a section-label comment like
    ``% appendix_c-p13`` must never leak into a claim's prose or its retrieval terms.
    Escaped ``\\%`` (a literal percent) survives."""
    return "\n".join(_TEX_COMMENT_RE.sub("", ln) for ln in text.splitlines())


def _sentence_spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, sentence) spans over comment-stripped tex, splitting on sentence
    enders that are NOT inside a brace group — so a ``\\cite{a,b}`` mid-sentence keeps
    its sentence whole. Coarse but deterministic."""
    text = _strip_tex_comments(text)
    spans: list[tuple[int, int, str]] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        elif ch in ".!?" and depth == 0:
            nxt = text[i + 1: i + 2]
            if nxt == "" or nxt.isspace():
                seg = text[start:i + 1].strip()
                if seg:
                    spans.append((start, i + 1, seg))
                start = i + 1
    tail = text[start:].strip()
    if tail:
        spans.append((start, len(text), tail))
    return spans


def _claim_sentences_for_key(mdir: Path, key: str) -> list[tuple[str, str]]:
    """Every (section_stem, sentence) where ``key`` is cited — the prose a source
    for ``key`` must entail. Reads RAW tex (cites survive; markup is stripped only
    for the words later)."""
    out: list[tuple[str, str]] = []
    for f in _section_files(mdir):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for a, b, sent in _sentence_spans(text):
            hit = any(key in (m.group(1) or "").split(",")
                      or key in [k.strip() for k in (m.group(1) or "").split(",")]
                      for m in _CITE_RE.finditer(sent))
            if hit:
                out.append((f.stem, " ".join(sent.split())))
    return out


def load_manifest_intents(manuscript_dir: str | Path) -> list[LiteratureIntent]:
    """Literature intents from ``bibliography_manifest.json``: every ``dangling`` key
    (the source is MISSING) plus any banked ``intents`` of class ``literature``. The
    claim is pulled from the prose that cites the key (not the generic manifest note),
    so retrieval + entailment have the real assertion to work against."""
    mdir = Path(manuscript_dir)
    manifest = mdir / "bibliography_manifest.json"
    out: list[LiteratureIntent] = []
    if not manifest.exists():
        return out
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out

    dangling = list(data.get("dangling") or [])
    banked = [i for i in (data.get("intents") or [])
              if str(i.get("cls") or i.get("research_class") or "") == "literature"]
    keys = list(dict.fromkeys(dangling + [i.get("key") for i in banked if i.get("key")]))
    for key in keys:
        if not key:
            continue
        claims = _claim_sentences_for_key(mdir, key)
        claim = claims[0][1] if claims else (
            f"the manuscript cites {key!r} but no .bib entry defines it")
        section = claims[0][0] if claims else ""
        out.append(LiteratureIntent(
            id=f"RI-LIT-{key}", key=key, claim=claim, section=section,
            lane=INTENT_DANGLING,
            note=f"dangling cite key {key!r}: no .bib source; needs a real reference"))
    return out


def load_ledger_intents(ledger_path: str | Path) -> list[LiteratureIntent]:
    """Literature intents from the shared research-intent ledger
    (``research_intents.jsonl`` — the gap_ledger :func:`to_research_intents` shape and
    the bibliography stage's ``ResearchIntent`` shape). Filtered to
    ``research_class``/``cls`` == ``literature``. The claim is the record's
    ``issue``/``quote`` (gap_ledger) or ``note`` (bib stage)."""
    path = Path(ledger_path)
    out: list[LiteratureIntent] = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        cls = str(rec.get("research_class") or rec.get("cls") or "")
        if cls != "literature":
            continue
        key = rec.get("key") or (rec.get("gap") or {}).get("where") or rec.get("node") or ""
        claim = (rec.get("issue") or rec.get("note") or rec.get("text") or "").strip()
        quote = ((rec.get("gap") or {}).get("quote") or rec.get("quote") or "").strip()
        if quote and quote not in claim:
            claim = (claim + " " + quote).strip()
        # the ORIGINATING claim node the admitted source must support (the gap
        # ledger's research intent rides it as ``node`` / ``gap.where``). Only a
        # real kind-prefixed conceptric node id counts — a bare section stem or the
        # ``source-vs-projection`` sentinel is honestly NOT a node, so it stays "".
        node_ref = str(rec.get("node") or (rec.get("gap") or {}).get("where") or "")
        claim_node = node_ref if NODE_ID_RE.match(node_ref) else ""
        out.append(LiteratureIntent(
            id=str(rec.get("id") or f"RI-LIT-{key}"), key=str(key), claim=claim,
            section=str(rec.get("section") or ""), lane=INTENT_DANGLING,
            note="from research-intent ledger", source="research_ledger",
            claim_node=claim_node))
    return out


def scan_verification_intents(manuscript_dir: str | Path) -> list[LiteratureIntent]:
    """The VERIFICATION lane: type the manuscript's OWN door-pending citation claims.
    A sentence that both CITES a key and carries a door-pending tell
    (:data:`_DOOR_PENDING_TELL` — ``has not been checked against``, ``unverified
    pending``, ``through the door``, ...) is a resolved-but-UNVERIFIED literature
    intent: the key renders, but the source has never been confirmed to SUPPORT the
    claim. The falqon distrust appendix names these by hand; this reader types them
    mechanically so the run is reproducible from the manuscript, not a hand list."""
    mdir = Path(manuscript_dir)
    out: list[LiteratureIntent] = []
    seen: set[str] = set()
    for f in _section_files(mdir):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for _a, _b, sent in _sentence_spans(text):
            if not _DOOR_PENDING_TELL.search(sent):
                continue
            keys: list[str] = []
            for m in _CITE_RE.finditer(sent):
                keys.extend(k.strip() for k in (m.group(1) or "").split(",") if k.strip())
            if not keys:
                continue
            claim = " ".join(sent.split())
            for key in dict.fromkeys(keys):
                iid = f"RI-VERIFY-{f.stem}-{key}"
                if iid in seen:
                    continue
                seen.add(iid)
                out.append(LiteratureIntent(
                    id=iid, key=key, claim=claim, section=f.stem,
                    lane=INTENT_VERIFICATION,
                    note=("resolved-but-unverified: the manuscript flags this cited "
                          "claim as not yet source-checked (door-pending)")))
    return out


def collect_intents(manuscript_dir: str | Path,
                    ledger_path: str | Path | None = None,
                    *, include_verification: bool = True) -> list[LiteratureIntent]:
    """The whole INPUT: manifest intents + ledger intents + (optionally) the
    verification lane, deduped by id (first-seen wins; the dangling/ledger sources
    outrank the verification scan for a shared key)."""
    mdir = Path(manuscript_dir)
    intents: list[LiteratureIntent] = []
    intents.extend(load_manifest_intents(mdir))
    if ledger_path is None:
        ledger_path = mdir / "research_intents.jsonl"
    intents.extend(load_ledger_intents(ledger_path))
    if include_verification:
        intents.extend(scan_verification_intents(mdir))
    seen: set[str] = set()
    out: list[LiteratureIntent] = []
    for it in intents:
        if it.id in seen:
            continue
        seen.add(it.id)
        out.append(it)
    return out


# --------------------------------------------------------------------------- #
# 2. DIRECTED RETRIEVAL — local corpus first, then arXiv (degrade-safe)
# --------------------------------------------------------------------------- #


def probe_reference_corpus(corpus_dir: str | Path = "reference_corpus") -> list[dict]:
    """Load the on-disk reference corpus (every ``*.json`` with a ``references``
    list). Each ref carries ``id``/``title``/``year``/``authors`` — the lawful local
    substrate retrieval ranks against. Missing dir → empty (local leg contributes
    nothing; the run degrades to arXiv-only, banked plainly)."""
    cdir = Path(corpus_dir)
    refs: list[dict] = []
    if not cdir.exists():
        return refs
    for p in sorted(cdir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for r in (data.get("references") or []):
            if isinstance(r, dict) and r.get("title"):
                r = dict(r)
                r["_corpus"] = p.name
                refs.append(r)
    return refs


def _expand_hyphens(words: frozenset[str]) -> frozenset[str]:
    """Fold hyphenated compounds into their pieces AND keep the whole: so
    ``early-fault-tolerant`` overlaps a candidate's ``fault-tolerant``/``early``. A
    pure string set would miss the match on a hyphen artifact alone — the exact
    false-reject that dropped a correctly-cited source in the falqon run."""
    out = set(words)
    for w in words:
        if "-" in w:
            out.update(p for p in w.split("-") if len(p) >= 4)
    return frozenset(out)


def _claim_words(claim: str) -> frozenset[str]:
    """Content words of a claim — the SAME machinery :mod:`readers.source_delta`
    uses (offline, deterministic), so a fixed claim always re-mines the same set,
    with hyphenated compounds folded to their pieces (:func:`_expand_hyphens`)."""
    return _expand_hyphens(SD._content_words(SD._strip_markup(claim)))


_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def reference_corpus_candidates(intent: LiteratureIntent, refs: list[dict],
                                *, k: int = 5, floor: float = 0.04) -> list[Candidate]:
    """Rank the local corpus refs by content-word overlap (Jaccard) of the claim
    against each ref's title (+authors). Deterministic + offline. Returns the top-k
    above ``floor`` as :class:`Candidate` (provenance ``reference_corpus``). The
    corpus refs carry NO abstract, so their ``text`` is title-only — a title-level
    candidate the judge weighs accordingly (or that routes to arXiv for the abstract).
    ``floor`` keeps zero/near-zero-overlap noise out (the machine floor is
    :func:`machine_prefilter`; this is a retrieval cutoff)."""
    qw = _claim_words(intent.claim)
    if not qw:
        return []
    scored: list[tuple[float, dict]] = []
    for r in refs:
        title = str(r.get("title") or "")
        auth = " ".join(r.get("authors") or [])
        rw = _expand_hyphens(SD._content_words(title) | SD._content_words(auth))
        if not rw:
            continue
        inter = len(qw & rw)
        if inter == 0:
            continue
        j = inter / len(qw | rw)
        if j >= floor:
            scored.append((j, r))
    scored.sort(key=lambda t: (-t[0], str(t[1].get("id") or t[1].get("title"))))
    out: list[Candidate] = []
    for j, r in scored[:max(1, k)]:
        yr = r.get("year")
        out.append(Candidate(
            cand_id=f"corpus:{r.get('id') or _slug(r.get('title', ''))}",
            title=str(r.get("title") or ""),
            year=int(yr) if isinstance(yr, int) else None,
            authors=list(r.get("authors") or []),
            provenance="reference_corpus",
            match_score=round(float(j), 4)))
    return out


def probe_arxiv(timeout: int = 15) -> tuple[bool, str]:
    """One probe request to the arXiv API. Returns ``(reachable, note)``. Reachable
    → the network leg fires; blocked → the leg is attested-available and the run
    degrades to local candidates only (:data:`ARXIV_ENABLE_NOTE`)."""
    url = ARXIV_ENDPOINT + "?" + urllib.parse.urlencode(
        {"search_query": "all:electron", "max_results": 1})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ok = 200 <= getattr(resp, "status", 200) < 300
        return ok, "arxiv reachable" if ok else "arxiv non-2xx"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, f"arxiv unreachable ({type(e).__name__}): {ARXIV_ENABLE_NOTE}"


_UA = "laplace-citation-direction/0.1 (+research-agenda literature door)"
_ATOM = "{http://www.w3.org/2005/Atom}"


def arxiv_candidates(intent: LiteratureIntent, *, max_results: int = 5,
                     timeout: int = 20,
                     fetch: Callable[[str], bytes] | None = None) -> list[Candidate]:
    """Fetch arXiv metadata candidates for the claim (title + abstract + authors +
    year). ``fetch`` is injectable (a bytes-returning callable over a URL) so tests
    drive a fixed Atom fixture with NO network; the default is a guarded urllib GET.
    A network/parse failure returns ``[]`` (the caller has already probed; this is the
    plain degrade, never a raise that aborts the run)."""
    terms = _salient_terms(intent)
    if not terms:
        return []
    query = " AND ".join(f"all:{t}" for t in terms[:6])
    url = ARXIV_ENDPOINT + "?" + urllib.parse.urlencode(
        {"search_query": query, "start": 0, "max_results": max_results})
    try:
        raw = fetch(url) if fetch is not None else _http_get(url, timeout)
        root = ET.fromstring(raw)
    except (urllib.error.URLError, OSError, ET.ParseError, ValueError):
        return []
    out: list[Candidate] = []
    for entry in root.findall(f"{_ATOM}entry"):
        title = _text(entry.find(f"{_ATOM}title"))
        summary = _text(entry.find(f"{_ATOM}summary"))
        aid = _text(entry.find(f"{_ATOM}id"))
        published = _text(entry.find(f"{_ATOM}published"))
        year = None
        ym = _YEAR_RE.search(published)
        if ym:
            year = int(ym.group(0))
        authors = [_text(a.find(f"{_ATOM}name"))
                   for a in entry.findall(f"{_ATOM}author")]
        arxiv_id = aid.rsplit("/", 1)[-1] if aid else ""
        doi = _text(entry.find("{http://arxiv.org/schemas/atom}doi"))
        out.append(Candidate(
            cand_id=f"arxiv:{arxiv_id or _slug(title)}",
            title=" ".join(title.split()),
            year=year, authors=[a for a in authors if a],
            provenance="arxiv", abstract=" ".join(summary.split()),
            arxiv_id=arxiv_id, doi=doi))
    return out


def _http_get(url: str, timeout: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _text(node: Optional[ET.Element]) -> str:
    return (node.text or "") if node is not None else ""


def _salient_terms(intent: LiteratureIntent, *, cap: int = 4) -> list[str]:
    """The claim's salient retrieval terms for an arXiv term-search: hyphen-split
    single words (``early-fault-tolerant`` -> ``early``/``fault``/``tolerant`` — arXiv
    ``all:`` matches words, not compounds), the longest first, plus the cite key's
    author/topic stem (``childs2012hamiltonian`` -> ``childs``/``hamiltonian``) hoisted
    to the front since it names the target most precisely. Capped small: a wide AND
    query returns nothing. Deterministic order."""
    raw = set()
    for w in _claim_words(intent.claim):
        for piece in w.split("-"):
            if len(piece) >= 5:
                raw.add(piece)
    words = sorted(raw, key=lambda w: (-len(w), w))[:cap]
    terms: list[str] = []
    for tok in re.findall(r"[a-z]{4,}", (intent.key or "").lower()):
        if not tok.isdigit():
            terms.append(tok)
    terms.extend(words)
    return list(dict.fromkeys(terms))[:cap + 2]


# --------------------------------------------------------------------------- #
# Identity resolution — a KNOWN key's actual cited source (verification lane)
# --------------------------------------------------------------------------- #


def bib_entry_for_key(manuscript_dir: str | Path, key: str,
                      bib_basename: str = "refs") -> dict | None:
    """The ``.bib`` entry a resolved key names — ``{title, authors, year, arxiv_id,
    doi}`` parsed from ``<bib_basename>.bib``. The IDENTITY the verification lane
    resolves against (machine-checkable: the key is defined, its arXiv id is a hard
    handle). None when the key is not defined (a dangling key has no entry)."""
    bib = Path(manuscript_dir) / f"{bib_basename}.bib"
    try:
        text = bib.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"@\s*[a-zA-Z]+\s*\{\s*" + re.escape(key) + r"\s*,(.*?)\n\}",
                  text, re.S)
    if not m:
        return None
    body = m.group(1)

    def _field(name: str) -> str:
        fm = re.search(name + r"\s*=\s*\{(.*?)\}", body, re.S | re.I)
        return " ".join(fm.group(1).split()) if fm else ""

    note = _field("note")
    aid = _ARXIV_ID_RE.search(note)
    authors = [a.strip() for a in re.split(r"\s+and\s+", _field("author")) if a.strip()]
    yr = _field("year")
    return {
        "title": _field("title"),
        "authors": authors,
        "year": int(yr) if yr.isdigit() else None,
        "arxiv_id": aid.group(1) if aid else "",
        "doi": _field("doi"),
    }


def resolved_source_candidate(intent: LiteratureIntent, manuscript_dir: str | Path,
                              *, bib_basename: str = "refs", timeout: int = 20,
                              fetch: Callable[[str], bytes] | None = None
                              ) -> Candidate | None:
    """For a KNOWN key (verification lane), the ACTUAL cited source as a candidate —
    identity-resolved by the ``.bib`` entry's arXiv id and fetched for its abstract, so
    the judge checks entailment of the CLAIM against the very paper the prose cites
    (the exact 'door-check' the falqon distrust appendix describes). Returns None when
    the key is unresolved (dangling) or has no arXiv handle to fetch an abstract from
    (falls back to the title-only bib metadata as the candidate in that case)."""
    entry = bib_entry_for_key(manuscript_dir, intent.key, bib_basename)
    if entry is None:
        return None
    abstract = ""
    if entry["arxiv_id"]:
        base_id = entry["arxiv_id"].split("v")[0]
        url = ARXIV_ENDPOINT + "?" + urllib.parse.urlencode(
            {"id_list": base_id, "max_results": 1})
        try:
            raw = fetch(url) if fetch is not None else _http_get(url, timeout)
            root = ET.fromstring(raw)
            entry_el = root.find(f"{_ATOM}entry")
            if entry_el is not None:
                abstract = " ".join(_text(entry_el.find(f"{_ATOM}summary")).split())
        except (urllib.error.URLError, OSError, ET.ParseError, ValueError):
            abstract = ""
    return Candidate(
        cand_id=f"cited:{intent.key}", title=entry["title"], year=entry["year"],
        authors=entry["authors"], provenance="cited-source", abstract=abstract,
        arxiv_id=entry["arxiv_id"], doi=entry["doi"], match_score=1.0)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:48] or "x"


# --------------------------------------------------------------------------- #
# 3. ENTAILMENT — machine prefilter (code) + judge packet (never cosine-only)
# --------------------------------------------------------------------------- #


def machine_prefilter(intent: LiteratureIntent,
                      cand: Candidate) -> tuple[bool, str]:
    """The MACHINE FLOOR — the checks code can settle, so the judge sees only real
    entailment questions. Returns ``(kept, reason)``. A candidate is rejected in code
    when: (a) the claim names a year the candidate hard-contradicts (a candidate can
    only support a claim if it PREDATES or matches the year the claim asserts), or
    (b) it shares NO salient term with the claim (title/abstract) — pure retrieval
    noise. Everything else is KEPT for the judge (title/id resolution passes). This is
    NEVER an admission — admission is the judge's ENTAILS verdict."""
    ctext = f"{cand.title} {cand.abstract}".lower()
    cwords = _expand_hyphens(SD._content_words(ctext))
    qw = _claim_words(intent.claim)
    if qw and not (qw & cwords):
        return False, "zero salient-term overlap with the claim (retrieval noise)"
    # year contradiction: a claim asserting a specific prior year cannot be supported
    # by a source published strictly AFTER it (the source could not have grounded it).
    claim_years = [int(m.group(0)) for m in _YEAR_RE.finditer(intent.claim)]
    if claim_years and cand.year:
        earliest = min(claim_years)
        if cand.year > earliest + 1:
            return False, (f"year contradiction: candidate {cand.year} postdates the "
                           f"claim's asserted year {earliest}")
    return True, "passes the machine floor — routed to the entailment judge"


#: the bank-contract every entailment packet carries (the growth_adjudicator idiom):
#: the judge returns a verdict; the consumer calls :func:`apply_admission`.
BANK_CONTRACT: dict = {
    "function": "laplace.pipeline.citation_direction.apply_admission",
    "signature": "apply_admission(manuscript_dir, intent, candidate, verdict, ...) -> dict",
    "verdicts": ["ENTAILS", "NOT-ENTAILS", "INSUFFICIENT-TEXT"],
    "law": ENTAILMENT_LAW,
    "note": (
        "The dispatched judge rules ENTAILS / NOT-ENTAILS / INSUFFICIENT-TEXT against "
        "the candidate's abstract/text. On ENTAILS the consumer calls apply_admission, "
        "which lands the source as a citation-node (epistemic 'cited' + the verdict "
        "ref) through the conceptric ingest gate and writes its BibTeX so the "
        "bibliography stage resolves the key. NOT-ENTAILS/INSUFFICIENT-TEXT keep the "
        "intent TYPED (never silently dropped). Builder != judge: this module emits "
        "the packet; it never rules."
    ),
}


def entailment_packet(intent: LiteratureIntent, cand: Candidate) -> dict:
    """One JUDGE PACKET (growth_adjudicator idiom): ``{decision, bank}`` where the
    decision carries the CLAIM, the CANDIDATE TEXT (title + abstract — the entailment
    is checked against this, never a cosine), and the entailment LAW. Frame-less
    (the law is the shared frame, hoisted once at the manifest level). NEVER calls a
    model."""
    return {
        "decision": {
            "kind": "citation-entailment",
            "intent_id": intent.id,
            "cite_key": intent.key,
            "lane": intent.lane,
            "claim": intent.claim,
            "candidate": {
                "cand_id": cand.cand_id,
                "title": cand.title,
                "abstract": cand.abstract,
                "year": cand.year,
                "authors": cand.authors,
                "provenance": cand.provenance,
                "arxiv_id": cand.arxiv_id,
                "doi": cand.doi,
                "has_abstract": bool(cand.abstract.strip()),
            },
            "question": (
                f"ENTAILMENT — does this candidate ENTAIL the claim it must support? "
                f"Claim: {intent.claim!r}. Rule ENTAILS / NOT-ENTAILS / "
                f"INSUFFICIENT-TEXT per the law."),
        },
        "bank": BANK_CONTRACT,
    }


def emit_entailment_manifest(packets: Iterable[dict], out_path: str | Path,
                             *, intent: LiteratureIntent | None = None) -> dict:
    """Write the citation-entailment dispatch manifest a judge tier consumes — the
    growth_adjudicator ``emit_dispatch_manifest`` idiom: a self-describing JSON
    (``kind`` / ``count`` / ``cut_at`` / ``bank_contract`` / ``frame``(the shared
    entailment law) / ``packets``). Returns the manifest dict; the file is the same
    content. The judge reads the shared law once and each packet's own claim +
    candidate text."""
    plist = list(packets)
    manifest = {
        "kind": "citation-entailment-adjudication",
        "schema": 2,
        "count": len(plist),
        "cut_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "frame": {"entailment_law": ENTAILMENT_LAW,
                  "intent": intent.as_dict() if intent else None},
        "bank_contract": BANK_CONTRACT,
        "packets": plist,
        "invocation": None,
    }
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest["invocation"] = f'/citation-entailment --manifest "{out.name}"'
    out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    return manifest


# --------------------------------------------------------------------------- #
# 4. ADMISSION — citation-node through the conceptric gate + BibTeX render
# --------------------------------------------------------------------------- #

_ADMIT_VERDICT = "ENTAILS"


def _bibtex_for(cand: Candidate, key: str) -> str:
    """Render an admitted candidate as a BibTeX entry — what makes
    :mod:`bibliography_stage` RESOLVE the key so the reference renders."""
    fields: list[tuple[str, str]] = []
    if cand.authors:
        fields.append(("author", " and ".join(cand.authors)))
    if cand.title:
        fields.append(("title", cand.title))
    if cand.year:
        fields.append(("year", str(cand.year)))
    if cand.doi:
        fields.append(("doi", cand.doi))
    note_bits = []
    if cand.arxiv_id:
        note_bits.append(f"arXiv:{cand.arxiv_id}")
    note_bits.append(f"admitted via citation-direction (provenance {cand.provenance})")
    fields.append(("note", "; ".join(note_bits)))
    body = ",\n".join(f"  {k:<8} = {{{v}}}" for k, v in fields)
    return f"@article{{{key},\n{body},\n}}\n"


def _append_bib_entry(bib_path: Path, entry: str, key: str) -> bool:
    """Append a BibTeX entry idempotently (a key already defined is a no-op). Returns
    True when the file was modified."""
    bib_path.parent.mkdir(parents=True, exist_ok=True)
    existing = bib_path.read_text(encoding="utf-8") if bib_path.exists() else ""
    if re.search(r"@\s*[a-zA-Z]+\s*\{\s*" + re.escape(key) + r"\s*,", existing):
        return False
    sep = "" if existing.endswith("\n") or not existing else "\n"
    bib_path.write_text(existing + sep + "\n" + entry, encoding="utf-8")
    return True


def resolve_claim_node(intent: LiteratureIntent) -> str | None:
    """The entailed-claim CONCEPTRIC NODE id the admitted source must support, or
    ``None`` when the intent carries no resolvable one. A gap-ledger literature
    intent rides its originating node (threaded onto ``claim_node``); a
    manuscript-scanned intent (dangling / verification) carries only a section stem
    + the claim sentence, so it stays unresolved here — the admission banks the
    unresolved marker rather than edge a guess (the arming's law: never a silent
    drop, never a fabricated link)."""
    cn = (getattr(intent, "claim_node", "") or "").strip()
    return cn if cn and NODE_ID_RE.match(cn) else None


def _rw_id() -> str:
    """A rewire-record id in the ledger's own mint shape (mirror of
    :func:`corpus_ingest.rewire_add`)."""
    import datetime as _dt
    return _dt.datetime.now().strftime("RW-%Y%m%d-%H%M%S-%f")


def _rw_ts() -> str:
    import datetime as _dt
    return _dt.datetime.now().isoformat(timespec="seconds")


def _status_record(node_id: str, carrier: str, *, verdict_ref: str = "",
                   by: str = "citation_direction") -> dict | None:
    """A ``set-status`` op in the rewire_add shape — the admitted source's epistemic
    status written through :func:`schema.canonical_status` (which folds the carrier
    into the enum: ``cited`` -> ``imported``), so the citation path never stamps a
    private vocabulary that can drift from the enum. Returns ``None`` for a carrier
    that does not fold (refused rather than mint a fictional status)."""
    canon = canonical_status(carrier)
    if canon is None:
        return None
    return {"id": _rw_id(), "ts": _rw_ts(), "kind": "set-status",
            "node": node_id, "value": canon, "by": by, "status": "open",
            "entailment_verdict_ref": verdict_ref}


def _support_edge_record(cit_node: str, claim_node: str, verdict_ref: str,
                         *, by: str = "citation_direction") -> dict:
    """A ``supports``-axis add-edge in the rewire_add shape: the admitted literature
    node BEARS (supports) the entailed claim node — the proven link admission used
    to discard. The edge TOKEN is minted through :func:`schema.token_for` and carried
    on the record for visibility; apply_overlay re-mints the byte-identical token on
    the next build (leg 1a's typed born/add-edge path). The entailment verdict rides
    the edge as its evidence."""
    return {"id": _rw_id(), "ts": _rw_ts(), "kind": "add-edge",
            "node": cit_node, "target": claim_node, "axis": "supports",
            "token": token_for("supports", claim_node), "value": verdict_ref,
            "by": by, "status": "open", "entailment_verdict_ref": verdict_ref}


def citation_node_record(intent: LiteratureIntent, cand: Candidate,
                         verdict_ref: str, *, project: str = "",
                         round: int = 0, claim_node: str | None = None) -> dict:
    """The CITATION-NODE deposit — an admitted source routed through the existing
    conceptric ingest gate (:func:`adjudicate.make_conceptric_intent`, the same door
    the gap ledger banks through). Carries the epistemic provenance the substrate now
    wears (``cited``) and the entailment VERDICT REF (a claim's floor is the weakest
    node in its grounding chain, reader-visible — the arming's LAW). ``entailed_claim``
    is the resolved claim node id, or ``"unresolved"`` — the marker for a citation
    whose entailed claim carries no conceptric node id (never a silent drop)."""
    from laplace.pipeline import adjudicate as ADJ
    rec = ADJ.make_conceptric_intent(
        intent.key or intent.id, "content-missing",
        note=f"[citation-admitted] {intent.claim[:180]}",
        finding_id=intent.id, kind="citation-direction", section=intent.section,
        actor="citation_direction", round=round, project=project)
    rec["epistemic"] = "cited"
    rec["cite_key"] = intent.key
    rec["entailment_verdict_ref"] = verdict_ref
    rec["candidate"] = cand.as_dict()
    rec["lane"] = intent.lane
    rec["entailed_claim"] = claim_node or "unresolved"
    return rec


def apply_admission(manuscript_dir: str | Path, intent: LiteratureIntent,
                    cand: Candidate, verdict: dict, *,
                    bib_basename: str = "refs", project: str = "",
                    round: int = 0) -> dict:
    """Land an ENTAILS verdict: write the candidate's BibTeX (so the key RESOLVES and
    the reference renders), emit the citation-node record through the conceptric gate,
    and — the weld (G3 leg 1) — no longer DISCARD the proven link:

    * the epistemic stamp writes through :func:`schema.canonical_status` — a
      ``set-status`` op carrying the canonical enum value (``imported``, from
      ``cited``), banked alongside the node's private ``epistemic`` field so the
      vocabulary can never drift;
    * when the entailed claim resolves to a conceptric node
      (:func:`resolve_claim_node`), a ``supports``-axis add-edge from the admitted
      literature node to that claim (minted through :func:`schema.token_for`, carrying
      the entailment verdict ref) — the edge the admission used to throw away. Where
      the claim node cannot be resolved, the node record banks the
      ``entailed_claim="unresolved"`` marker instead (never a silent drop).

    A non-ENTAILS verdict admits NOTHING — it returns the typed intent unchanged.
    ``verdict`` = ``{ruling, id?, evidence?}``; ``ruling`` must be ``ENTAILS``. Returns
    ``{admitted, node?, bib_written?, bib_key?, status_edge?, support_edge?,
    entailed_claim?, reason}`` — the ``status_edge`` / ``support_edge`` are rewire
    records the consumer lands on the friction ledger."""
    ruling = str(verdict.get("ruling") or verdict.get("verdict") or "").upper()
    verdict_ref = str(verdict.get("id") or verdict.get("ref") or "")
    if ruling != _ADMIT_VERDICT:
        return {"admitted": False, "reason": f"verdict {ruling!r} != ENTAILS — intent "
                f"stays typed", "intent": intent.as_dict()}
    key = intent.key or f"cd-{_slug(cand.title)}"
    mdir = Path(manuscript_dir)
    bib_written = _append_bib_entry(
        mdir / f"{bib_basename}.bib", _bibtex_for(cand, key), key)
    claim_node = resolve_claim_node(intent)
    node = citation_node_record(intent, cand, verdict_ref, project=project,
                                round=round, claim_node=claim_node)
    # the admitted literature node the atomiser mints (ref:<key>); the epistemic
    # status and the supports edge both hang off it.
    cit_node = f"ref:{key}"
    status_edge = _status_record(cit_node, "cited", verdict_ref=verdict_ref)
    support_edge = (_support_edge_record(cit_node, claim_node, verdict_ref)
                    if claim_node is not None else None)
    return {"admitted": True, "node": node, "bib_written": bib_written,
            "bib_key": key, "status_edge": status_edge, "support_edge": support_edge,
            "entailed_claim": claim_node or "unresolved",
            "reason": "ENTAILS — citation-node landed, key resolved"}


# --------------------------------------------------------------------------- #
# The run + telemetry
# --------------------------------------------------------------------------- #


def run(manuscript_dir: str | Path, *,
        corpus_dir: str | Path = "reference_corpus",
        out_dir: str | Path | None = None,
        ledger_path: str | Path | None = None,
        include_verification: bool = True,
        use_network: bool = True,
        arxiv_fetch: Callable[[str], bytes] | None = None,
        k_local: int = 5, k_arxiv: int = 5,
        project: str = "") -> dict:
    """The whole organ end-to-end on a manuscript's literature intents.

    collect intents -> retrieve (local corpus FIRST, then arXiv if reachable) ->
    machine prefilter -> emit a judge manifest per intent (survivors) -> bucket ->
    bank the run record + telemetry sidecar. Admission is DEFERRED to the judge tier:
    every survivor is ``needs-judge`` (the manifest is emitted); ``admitted`` is 0
    until :func:`apply_admission` runs a judge's ENTAILS verdict. This is the plain
    ran-vs-compiled seam — retrieval + prefilter + manifest RAN; the entailment
    admission is COMPILED (emitted, awaiting the judge).

    Returns the run record; also written to ``out_dir`` alongside the manifests and
    the telemetry sidecar."""
    mdir = Path(manuscript_dir)
    out = Path(out_dir) if out_dir else (mdir / "citation_direction")
    out.mkdir(parents=True, exist_ok=True)

    intents = collect_intents(mdir, ledger_path,
                              include_verification=include_verification)
    refs = probe_reference_corpus(corpus_dir)

    net_reachable, net_note = (False, "network leg disabled (use_network=False)")
    if use_network and arxiv_fetch is None:
        net_reachable, net_note = probe_arxiv()
    elif use_network and arxiv_fetch is not None:
        net_reachable, net_note = True, "network leg via injected fetch"

    results: list[IntentResult] = []
    manifests: list[str] = []
    for it in intents:
        cands: list[Candidate] = []
        # identity-resolved source FIRST (verification lane): the actual cited paper,
        # its abstract fetched by the .bib entry's arXiv id — the real door-check.
        if use_network and net_reachable:
            resolved = resolved_source_candidate(it, mdir, fetch=arxiv_fetch)
            if resolved is not None:
                cands.append(resolved)
        cands += reference_corpus_candidates(it, refs, k=k_local)
        if use_network and net_reachable:
            cands = cands + arxiv_candidates(it, max_results=k_arxiv,
                                             fetch=arxiv_fetch)
        # dedupe by cand_id (the resolved source may also surface via term search)
        seen_c: set[str] = set()
        cands = [c for c in cands
                 if not (c.cand_id in seen_c or seen_c.add(c.cand_id))]
        rejected: list[dict] = []
        packets: list[dict] = []
        survivors: list[str] = []
        for c in cands:
            kept, reason = machine_prefilter(it, c)
            if not kept:
                rejected.append({"cand_id": c.cand_id, "reason": reason})
                continue
            packets.append(entailment_packet(it, c))
            survivors.append(c.cand_id)

        res = IntentResult(
            intent=it.as_dict(),
            candidates=[c.as_dict() for c in cands],
            rejected_code=rejected, needs_judge=survivors)
        if packets:
            mpath = out / f"entailment_manifest.{_slug(it.id)}.json"
            emit_entailment_manifest(packets, mpath, intent=it)
            res.manifest_path = str(mpath)
            manifests.append(str(mpath))
            res.bucket = "needs-judge"
        elif cands:
            res.bucket = "rejected"       # candidates found, all machine-rejected
        else:
            res.bucket = "no-candidate"
        results.append(res)

    record = {
        "organ": "citation_direction",
        "ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "manuscript": str(mdir),
        "ran_vs_compiled": (
            "retrieval + machine-prefilter + judge-manifest emission RAN; the "
            "entailment ADMISSION is COMPILED (manifests emitted, admitted=0 until a "
            "dispatched judge rules ENTAILS via apply_admission)"),
        "network_leg": {"reachable": net_reachable, "note": net_note,
                        "enable": ARXIV_ENABLE_NOTE},
        "corpus": {"dir": str(corpus_dir), "n_refs": len(refs)},
        "intents_n": len(intents),
        "candidates_total": sum(len(r.candidates) for r in results),
        "buckets": _bucket_counts(results),
        "by_intent": [
            {"intent_id": r.intent["id"], "key": r.intent["key"],
             "lane": r.intent["lane"], "section": r.intent["section"],
             "n_candidates": len(r.candidates),
             "n_rejected_code": len(r.rejected_code),
             "n_needs_judge": len(r.needs_judge),
             "bucket": r.bucket, "manifest": r.manifest_path}
            for r in results],
        "manifests": manifests,
        "admitted": 0,
    }
    (out / "run_record.json").write_text(
        json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    write_run_sidecar(out / "_citation_direction.sidecar.json", record, results)
    return record


def _bucket_counts(results: list[IntentResult]) -> dict[str, int]:
    counts = {b: 0 for b in BUCKETS}
    for r in results:
        counts[r.bucket] = counts.get(r.bucket, 0) + 1
    return counts


def write_run_sidecar(path: str | Path, record: dict,
                      results: list[IntentResult]) -> Path:
    """The per-run TELEMETRY sidecar (the form-channel sidecar idiom): the network
    leg's state, the corpus probed, and the per-intent candidate + bucket counts —
    everything to WATCH a run in use without re-reading the manifests. Provenance +
    counts only; the claim/candidate text lives in the manifests, not the sidecar."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    sidecar = {
        "organ": "citation_direction",
        "ts": record.get("ran_at"),
        "network_leg": record.get("network_leg", {}).get("reachable"),
        "corpus_n_refs": record.get("corpus", {}).get("n_refs"),
        "intents_n": record.get("intents_n"),
        "candidates_total": record.get("candidates_total"),
        "buckets": record.get("buckets"),
        "manifests_n": len(record.get("manifests") or []),
        "by_intent": [
            {"intent_id": r.intent["id"], "lane": r.intent["lane"],
             "n_candidates": len(r.candidates),
             "n_needs_judge": len(r.needs_judge),
             "n_rejected_code": len(r.rejected_code),
             "bucket": r.bucket}
            for r in results],
    }
    p.write_text(json.dumps(sidecar, indent=1, ensure_ascii=False), encoding="utf-8")
    return p


def _verification_state(by_intent: Iterable[dict]) -> dict[str, int]:
    """Aggregate the VERIFICATION lane's bucket distribution from a run's per-intent
    rows (sidecar or record ``by_intent`` — both carry ``lane`` + ``bucket``). A
    verification intent is a resolved-but-unverified door-check; its bucket says
    whether the door has been walked: ``needs-judge`` = the source is fetched and the
    entailment packet is emitted, awaiting the judge; ``admitted`` = a judge ruled
    ENTAILS and the claim is grounded. Counts only."""
    state = {"intents_n": 0}
    for b in BUCKETS:
        state[b.replace("-", "_")] = 0
    for row in by_intent:
        if str(row.get("lane") or "") != INTENT_VERIFICATION:
            continue
        state["intents_n"] += 1
        bucket = str(row.get("bucket") or "")
        slot = bucket.replace("-", "_")
        if slot in state:
            state[slot] += 1
    return state


def _empty_run_record(mdir: Path) -> dict:
    """The honest-empty read shape — every fact zeroed/empty, ``present`` False, no
    raise. The ``/pipeline`` citation-direction card renders its absence string off
    this (``no run banked · N dangling citations await directed retrieval``)."""
    return {
        "present": False,
        "manuscript": str(mdir),
        "ran_at": "",
        "ran_vs_compiled": "",
        "intents_n": 0,
        "candidates_total": 0,
        "buckets": {b: 0 for b in BUCKETS},
        "admitted": 0,
        "manifests_pending": 0,
        "manifests_on_disk": 0,
        "manifests": [],
        "network_leg": None,
        "corpus_n_refs": 0,
        "verification": _verification_state([]),
        "by_intent": [],
    }


def read_run_record(manuscript_dir: str | Path) -> dict:
    """The lawful READER — view=mechanism: the ``/pipeline`` citation-direction card
    calls THIS, never re-parses the artifacts. The conjugate of :func:`run` /
    :func:`write_run_sidecar`: a PURE read (no subprocess, no compile, no network, no
    writes) of the banked run at ``<manuscript_dir>/citation_direction/`` —
    ``run_record.json`` + the ``entailment_manifest.*.json`` set + the
    ``_citation_direction.sidecar.json`` telemetry.

    Facts returned (present run):

    * the run summary — ``ran_at``, ``intents_n``, ``candidates_total``, ``buckets``
      (the four admission buckets), and the plain ``ran_vs_compiled`` seam;
    * ``manifests_pending`` vs ``admitted`` — the surviving entailment manifests on
      disk (each a per-intent judge packet set awaiting a dispatched judge) against
      ``admitted`` (0 until a judge rules ENTAILS via :func:`apply_admission`); each
      manifest summarised to counts (``n_packets`` + its own ``cut_at``/intent handle),
      never its packet bodies;
    * the VERIFICATION state from the sidecar (:func:`_verification_state`) — the
      resolved-but-unverified door-checks and how many the judge has walked;
    * the network leg's reachability and the corpus depth probed.

    ``present`` is ALWAYS carried. Absent artifact (or unreadable/malformed) →
    :func:`_empty_run_record` (``present`` False, every fact zeroed) — never a raise,
    never None."""
    mdir = Path(manuscript_dir)
    out = mdir / "citation_direction"
    record_path = out / "run_record.json"
    if not record_path.exists():
        return _empty_run_record(mdir)
    # ONE boom-guard over json.loads AND the whole field extraction (the
    # detector_organs.read_detector_organs exemplar): a valid-JSON-but-wrong-typed
    # run_record.json (e.g. ``by_intent`` an int, ``buckets`` a list) must degrade to
    # honest-empty, never raise a 500 on this GET path.
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))

        # the manifests are the disk truth (view=mechanism): glob them, summarise each to
        # counts — the card shows N surviving manifests, never the packet bodies.
        manifests: list[dict] = []
        for p in sorted(out.glob("entailment_manifest.*.json")):
            summary = {"name": p.name, "intent_id": "", "cite_key": "", "lane": "",
                       "section": "", "n_packets": 0, "cut_at": ""}
            try:
                man = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifests.append(summary)
                continue
            summary["n_packets"] = int(man.get("count") or 0)
            summary["cut_at"] = str(man.get("cut_at") or "")
            intent = (man.get("frame") or {}).get("intent") or {}
            summary["intent_id"] = str(intent.get("id") or "")
            summary["cite_key"] = str(intent.get("key") or "")
            summary["lane"] = str(intent.get("lane") or "")
            summary["section"] = str(intent.get("section") or "")
            manifests.append(summary)

        # verification lane state: the sidecar's per-intent rows (fall back to the record's
        # own by_intent if the sidecar is absent — both carry lane + bucket).
        by_intent = list(record.get("by_intent") or [])
        ver_rows = by_intent
        sidecar_path = out / "_citation_direction.sidecar.json"
        network_leg = (record.get("network_leg") or {}).get("reachable")
        if sidecar_path.exists():
            try:
                sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                sidecar = {}
            if sidecar.get("by_intent"):
                ver_rows = list(sidecar["by_intent"])
            if sidecar.get("network_leg") is not None:
                network_leg = sidecar.get("network_leg")

        buckets = {b: int((record.get("buckets") or {}).get(b, 0)) for b in BUCKETS}
        return {
            "present": True,
            "manuscript": str(record.get("manuscript") or mdir),
            "ran_at": str(record.get("ran_at") or ""),
            "ran_vs_compiled": str(record.get("ran_vs_compiled") or ""),
            "intents_n": int(record.get("intents_n") or 0),
            "candidates_total": int(record.get("candidates_total") or 0),
            "buckets": buckets,
            "admitted": int(record.get("admitted") or 0),
            "manifests_pending": len(manifests),
            "manifests_on_disk": len(manifests),
            "manifests": manifests,
            "network_leg": network_leg,
            "corpus_n_refs": int((record.get("corpus") or {}).get("n_refs") or 0),
            "verification": _verification_state(ver_rows),
            "by_intent": by_intent,
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return _empty_run_record(mdir)


def finding_kinds_manifest() -> list[dict[str, str]]:
    """This organ CONSUMES literature intents and introduces no finding kinds of its
    own — the empty manifest so ``register_component_kinds`` folds it uniformly."""
    return []


# --------------------------------------------------------------------------- #
# 5. CONSUMPTION — a judge tier's rulings landed as one durable act
# --------------------------------------------------------------------------- #

_ADJUDICATED_DIR = "adjudicated"


def _intent_from_frame(frame_intent: dict) -> LiteratureIntent:
    """Rebuild the typed intent from a manifest's ``frame.intent`` — only the
    dataclass's own fields (a manifest may carry extras)."""
    fields_ = {f for f in LiteratureIntent.__dataclass_fields__}
    return LiteratureIntent(**{k: v for k, v in frame_intent.items() if k in fields_})


def _candidate_from_packet(cand: dict) -> Candidate:
    """Rebuild the typed candidate from a packet's ``decision.candidate`` (drops the
    derived ``text`` / ``has_abstract`` views)."""
    fields_ = {f for f in Candidate.__dataclass_fields__}
    return Candidate(**{k: v for k, v in cand.items() if k in fields_})


def consume_verdicts(manuscript_dir: str | Path, verdicts: dict | str | Path, *,
                     bib_basename: str = "refs", project: str = "",
                     round: int = 0) -> dict:
    """The CONSUMER leg — land a dispatched judge tier's rulings as ONE durable act.

    ``verdicts`` is the judge tier's return (or a path to it):
    ``{"verdicts": [{"intent_id", "rulings": [{"cand_id", "ruling", "evidence", ...}]}]}``.
    For every pending entailment manifest whose ``frame.intent.id`` has a verdict:

    * exactly one ENTAILS candidate (the ``cited:`` one preferred) is admitted via
      :func:`apply_admission` — BibTeX lands, and the citation-node record is
      APPENDED to the project friction ledger (``corpus_friction/<project>.jsonl``,
      the :mod:`friction_consumer` deposit shape) so the conceptric gate sees it;
    * an all-NOT-ENTAILS intent is judged-and-rejected — the intent stays TYPED
      (never dropped), the manifest is walked;
    * an INSUFFICIENT-TEXT intent (no ENTAILS) stays PENDING — the abstract could
      not settle it; the full-source door remains open.

    Walked manifests (admitted / rejected) MOVE to ``citation_direction/adjudicated/``
    so ``manifests_pending`` reports only the genuinely-awaiting set. The raw rulings
    bank verbatim as ``judge_verdicts.<ts>.json`` (the instrument, auditable), and
    ``run_record.json`` + the sidecar update their buckets/``admitted`` so
    :func:`read_run_record` (the ``/pipeline`` card) reports the walked state.
    Idempotent: a manifest already moved is skipped; a bib key already present is a
    no-op append. Returns the consumption record."""
    from laplace.pipeline.ledger import append_jsonl

    mdir = Path(manuscript_dir)
    out = mdir / "citation_direction"
    if isinstance(verdicts, (str, Path)):
        verdicts = json.loads(Path(verdicts).read_text(encoding="utf-8"))
    by_id: dict[str, list[dict]] = {
        str(v.get("intent_id") or ""): list(v.get("rulings") or [])
        for v in (verdicts.get("verdicts") if isinstance(verdicts, dict) else verdicts) or []}

    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    verdicts_path = out / f"judge_verdicts.{ts.replace(':', '')}.json"
    consumption: dict = {"kind": "citation-entailment-consumption", "judged_at": ts,
                         "verdicts_file": verdicts_path.name, "by_intent": [],
                         "admitted": 0, "rejected": 0, "insufficient": 0,
                         "unmatched": sorted(by_id)}
    adjudicated = out / _ADJUDICATED_DIR

    for mpath in sorted(out.glob("entailment_manifest.*.json")):
        try:
            man = json.loads(mpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        frame_intent = (man.get("frame") or {}).get("intent") or {}
        iid = str(frame_intent.get("id") or "")
        if iid not in by_id:
            continue
        consumption["unmatched"].remove(iid)
        rulings = {str(r.get("cand_id") or ""): r for r in by_id[iid]}
        packets = {str(((p.get("decision") or {}).get("candidate") or {}).get("cand_id") or ""): p
                   for p in (man.get("packets") or [])}
        entails = [cid for cid, r in rulings.items()
                   if str(r.get("ruling", "")).upper() == _ADMIT_VERDICT and cid in packets]
        entails.sort(key=lambda c: (not c.startswith("cited:"), c))
        row: dict = {"intent_id": iid, "cite_key": str(frame_intent.get("key") or ""),
                     "manifest": mpath.name, "outcome": "", "bib_written": False}
        if entails:
            intent = _intent_from_frame(frame_intent)
            cand = _candidate_from_packet(
                (packets[entails[0]].get("decision") or {}).get("candidate") or {})
            res = apply_admission(
                mdir, intent, cand,
                {"ruling": _ADMIT_VERDICT, "id": f"{verdicts_path.name}#{iid}"},
                bib_basename=bib_basename, project=project, round=round)
            if project and res.get("node"):
                ledger = mdir.parents[1] / "corpus_friction" / f"{project}.jsonl" \
                    if (mdir.parents[1] / "corpus_friction").is_dir() \
                    else Path("corpus_friction") / f"{project}.jsonl"
                # the epistemic set-status + the supports edge land FIRST, so the
                # citation-node record stays the ledger's last row (the reader /
                # friction_current invariant). apply_overlay applies them
                # order-independently; a None (claim unresolved / status refused) is
                # skipped, never a silent write.
                for aux in (res.get("status_edge"), res.get("support_edge")):
                    if aux:
                        append_jsonl(ledger, aux)
                append_jsonl(ledger, res["node"])
                row["ledger"] = str(ledger)
            row.update(outcome="admitted", bib_written=bool(res.get("bib_written")),
                       bib_key=res.get("bib_key"),
                       entailed_claim=res.get("entailed_claim"),
                       support_edge=bool(res.get("support_edge")))
            consumption["admitted"] += 1
        elif all(str(r.get("ruling", "")).upper() == "NOT-ENTAILS"
                 for r in rulings.values()) and rulings:
            row["outcome"] = "rejected"
            consumption["rejected"] += 1
        else:
            row["outcome"] = "insufficient-text"
            consumption["insufficient"] += 1
        if row["outcome"] in ("admitted", "rejected"):
            adjudicated.mkdir(parents=True, exist_ok=True)
            mpath.rename(adjudicated / mpath.name)
        consumption["by_intent"].append(row)

    # bank the instrument verbatim + the consumption record beside it
    out.mkdir(parents=True, exist_ok=True)
    verdicts_path.write_text(
        json.dumps({"banked_at": ts, "verdicts": verdicts, "consumption": consumption},
                   indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    # the run record + sidecar report the walked state (view = mechanism)
    outcome_bucket = {"admitted": "admitted", "rejected": "rejected",
                      "insufficient-text": "needs-judge"}
    new_buckets = {r["intent_id"]: outcome_bucket[r["outcome"]]
                   for r in consumption["by_intent"]}
    for fname in ("run_record.json", "_citation_direction.sidecar.json"):
        fpath = out / fname
        if not fpath.exists():
            continue
        try:
            rec = json.loads(fpath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = list(rec.get("by_intent") or [])
        for r in rows:
            iid = str(r.get("intent_id") or "")
            if iid in new_buckets:
                r["bucket"] = new_buckets[iid]
        buckets = {b: 0 for b in BUCKETS}
        for r in rows:
            b = str(r.get("bucket") or "")
            if b in buckets:
                buckets[b] += 1
        rec["by_intent"] = rows
        rec["buckets"] = buckets
        rec["admitted"] = buckets["admitted"]
        if fname == "run_record.json":
            rec["ran_vs_compiled"] = (str(rec.get("ran_vs_compiled") or "") +
                                      f"; ADMISSION CONSUMED {ts}: "
                                      f"{consumption['admitted']} admitted, "
                                      f"{consumption['rejected']} rejected, "
                                      f"{consumption['insufficient']} awaiting full text")
            rec["judged_at"] = ts
        fpath.write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    return consumption


if __name__ == "__main__":  # pragma: no cover
    import argparse
    ap = argparse.ArgumentParser(description="the citation-direction organ")
    ap.add_argument("manuscript")
    ap.add_argument("--corpus", default="reference_corpus")
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-network", action="store_true")
    ap.add_argument("--no-verification", action="store_true")
    a = ap.parse_args()
    rec = run(a.manuscript, corpus_dir=a.corpus, out_dir=a.out,
              use_network=not a.no_network,
              include_verification=not a.no_verification)
    print(json.dumps(rec, indent=1, ensure_ascii=False))
