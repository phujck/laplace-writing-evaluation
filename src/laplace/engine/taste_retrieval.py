"""The taste substrate — his judgement, fuelled by the corpus of his implicit standards.

His ruling (2026-07-22, the engine session): the loop must close "against its own
judgement, fueled by the enormous corpus of my implicit tastes and standards — which
obviously exists and should be threaded in wherever it can." A judge holding his banked
QUOTES without the corpus is a stranger wearing his words. This module threads the wider
substrate into the superego's taste channel so a judge packet on a manuscript claim
carries the relevant SLICE of how HE actually writes — not a keyword hit over his explicit
rulings alone.

What the substrate is (what genuinely exists, at what grain):

- his verbatim rulings — ``proxy_verdicts.jsonl`` (question + ruling + his banked
  choice-commentary in ``ruling``); the explicit channel the superego already had.
- his corrections of the machine — the taste-correction idiom inside the same ledger:
  rows whose ``kind`` is one of the author-* correction kinds, or whose text carries
  correction vocabulary. A place he corrected the machine is the highest-signal taste,
  so a matching overrule is ALWAYS included and outranks bare similarity (his law).
- the promise asks — the ``ask`` fields of ``contract/promises.jsonl``.
- the stage stores — ``corpus_stores/<stage>/<paper>.jsonl``: one row per section /
  paragraph / rung / derivation-step / figure of his sixteen first-author papers, each
  carrying an ``embed_text`` slice and a ``form`` (job / arc / position …) and a byte-span
  ``provenance`` ref back to the source ``.tex``. Each store ships a sibling
  ``embeddings.json`` (``row_id`` -> a unit bge-small vector) — the wire was laid at fold
  time, so ranking his whole published corpus against a claim is one dot product per row.
- the profiles — ``profiles/author_architecture.yaml`` (whole-paper structural grain:
  introduction shape, narrative arc, section rhythm, figure placement, conclusion posture,
  each a field with a ``summary`` and a his-confirmed flag), ``profiles/house_style/``
  (cross-ref / citation / orthography rules), and ``profiles/voice/`` (sentence register).
  Profile fields ride as typed rows: the field name is the ref, the summary is the quote,
  and the his-confirmed flag rides a quote prefix.

THE RANKING. When the vendored open-weight embedding model is reachable
(:mod:`laplace.representation.embed_router`, bge-small-en-v1.5, local, deterministic — the SAME geometry
the recall ring uses; NOT a generative call), every substrate item is scored against the
claim. Keyword overlap is the OFFLINE fallback, marked ``keyword-degraded`` in the packet's
provenance. The distilled metric ``.metric_M.npz`` is applied AS ``q'Mv`` (the trained
bilinear metric — the query bent by M before the dot) whenever it is FRESH against the
current embedding basis, i.e. it postdates ``.self_embeddings.json`` (the metric-redistill
producer act, WO-20260721-222252: a re-embed and a metric re-distill are ONE producer
step). When M instead PREDATES the basis — a re-embed that did not re-distill — it is STALE
and skipped, ranking falls back to RAW cosine, and the packet SAYS SO rather than using a
stale metric silently (the skip branch is kept precisely for that future staleness). An
absent metric is the identity special case (raw cosine).

THE SEAL. Refs-only holds: every entry carries a ref the judge descends and ONE bounded
quote — the packet carries the relevant SLICE with provenance, never a wholesale corpus
dump. The whole channel is bounded by the caller's cap (the superego's ``_TASTE_CAP``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: the substrate stage stores, in a fixed order (determinism), each with a sibling
#: ``embeddings.json`` mapping ``row_id`` -> unit vector.
_STORES: tuple[str, ...] = (
    "section_architecture", "paragraph_plan", "spine_chain",
    "derivation_walk", "figure_caption",
)

#: the taste-correction idiom — a place he corrected the machine's own pre-ruling, the
#: highest-signal taste (his law). Narrow on purpose: the ``author-taste`` /
#: ``author-correction`` kinds, plus text that literally records correcting a machine
#: ruling. A matching overrule rides the TOP of the channel — but bounded (see
#: ``_overrule_reserve``) so it supplements the corpus rather than swallowing the packet.
_OVERRULE_KINDS: frozenset[str] = frozenset({"author-taste", "author-correction"})
#: sharp, unambiguous correction phrases only — a common phrase like "his correction"
#: false-matches retrospective mentions, so the vocabulary here names an ACT of overruling
#: a machine ruling. The ``kind`` above is the primary signal; this is the belt.
_CORRECTION_VOCAB: tuple[str, ...] = (
    "correcting the reconstructed", "correcting the machine", "overrule the",
    "overrode the", "i am favouring", "you can only compress",
)

#: the cosine floor a SUBSTRATE item (store row / profile field) must clear to ride the
#: embedding channel — a heuristic bar that keeps a claim about the UI from dragging in a
#: clearly-unrelated physics exemplar. His rulings keep the keyword gate as well, so this
#: bar governs only the implicit substrate. Documented, not silent.
_SUBSTRATE_FLOOR = 0.35

#: the bar an overrule must clear to be FORCED to the top on similarity alone (a keyword
#: match forces it regardless). Higher than the substrate floor so only a relevant
#: correction pre-empts the corpus — his law is "outrank similarity", not "ignore relevance".
_FORCE_FLOOR = 0.45

_QUOTE_CAP = 400


def _overrule_reserve(cap: int) -> int:
    """How many top slots a matching overrule may claim — bounded so the CORPUS (his
    implicit standards, the point of the wave) still fills the majority of the channel.
    Overrules ride the very top when relevant; they never swallow the packet."""
    return max(1, cap // 3)

#: process-local embedding cache for the sources that ship NO precomputed vectors (rulings,
#: promise asks, profile fields). Keyed by (backend name, text) so a session's repeated
#: packet assembly — and the two-call determinism check — never re-embeds the same text.
_EMBED_CACHE: dict[tuple[str, str], list[float]] = {}


# ---------------------------------------------------------------- keyword / overrule
def _matches(text: str, keywords: set[str]) -> bool:
    """Word-boundary keyword overlap (case-insensitive) — mirrors the superego's own
    matcher so the classic ruling gate is unchanged."""
    if not keywords:
        return False
    low = text.lower()
    return any(re.search(r"\b" + re.escape(kw) + r"\b", low) for kw in keywords)


def _is_overrule(row: dict) -> bool:
    """A place he corrected the machine — the highest-signal taste. True when the row's
    ``kind`` is an author-* correction kind, or its text carries correction vocabulary."""
    if str(row.get("kind") or "") in _OVERRULE_KINDS:
        return True
    text = (str(row.get("question", "")) + " " + str(row.get("ruling", ""))).lower()
    return any(w in text for w in _CORRECTION_VOCAB)


def _bounded(text: str, prefix: str = "") -> str:
    """One bounded quote — the only free text an entry carries. The prefix (a typed flag
    like ``[his-overrule]``) rides INSIDE the bound, so the total never exceeds the cap."""
    return (prefix + " ".join(str(text).split()))[:_QUOTE_CAP]


# ---------------------------------------------------------------- embedding geometry
def _cos(a, b) -> float:
    import numpy as np
    va = np.asarray(a, dtype="float32")
    vb = np.asarray(b, dtype="float32")
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if not na or not nb:
        return 0.0
    return float(va.dot(vb) / (na * nb))


def _metric_status(repo: Path, dim: int | None):
    """Use the same generation contract as ordinary geometric reconstruction."""
    from laplace.representation import embed_router
    status = embed_router.metric_status(repo)
    M = embed_router.load_metric(repo)
    if M is not None and dim is not None and M.shape != (dim, dim):
        raise embed_router.MetricGenerationMismatch(
            f"metric shape {M.shape} differs from backend dimension {dim}")
    return M, status


def _embed_one(backend, text: str) -> list[float] | None:
    """Embed a single text through the router, cached. None when the backend can't."""
    key = (getattr(backend, "name", "?"), text)
    hit = _EMBED_CACHE.get(key)
    if hit is not None:
        return hit
    try:
        vec = backend.embed([text])[0]
    except Exception:
        return None
    _EMBED_CACHE[key] = vec
    return vec


# ---------------------------------------------------------------- candidate sources
def _ruling_candidates(repo: Path, keywords: set[str]) -> list[dict]:
    """His verbatim rulings + the overrule idiom. A non-overrule ruling rides ONLY on the
    classic keyword gate (the explicit channel, unchanged); an overrule is a candidate the
    moment it exists, forced later when it matches (keyword OR embedding)."""
    from laplace.engine import author_proxy
    out: list[dict] = []
    for row in author_proxy.load_verdicts(repo):
        if not isinstance(row, dict):
            continue
        question = str(row.get("question", ""))
        ruling = str(row.get("ruling", ""))
        haystack = question + " " + ruling
        overrule = _is_overrule(row)
        kw = _matches(haystack, keywords)
        if not (kw or overrule):
            continue
        # classic quote shape preserved verbatim for the explicit channel; an overrule
        # carries a typed prefix so the judge SEES it is a place he corrected the machine.
        base = (question + " -- " + ruling).strip(" -")
        prefix = "[his-overrule] " if overrule else ""
        out.append({
            "source": author_proxy.LEDGER_NAME,
            "ref": str(row.get("id", "")),
            "date": str(row.get("date", "")),
            "quote": _bounded(base, prefix) if overrule else base[:_QUOTE_CAP],
            "text": haystack,
            "overrule": overrule,
            "kw_match": kw,
            "gate": "ruling",
        })
    return out


def _promise_candidates(repo: Path, keywords: set[str]) -> list[dict]:
    """The ``ask`` fields of the promise ledger — keyword-gated, as the classic channel."""
    out: list[dict] = []
    path = repo / "contract" / "promises.jsonl"
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        ask = str(row.get("ask", ""))
        if not _matches(ask, keywords):
            continue
        out.append({
            "source": "contract/promises.jsonl",
            "ref": str(row.get("id", "")),
            "date": str(row.get("date", "")),
            "quote": ask[:_QUOTE_CAP],
            "text": ask,
            "overrule": False,
            "kw_match": True,
            "gate": "ruling",
        })
    return out


def _profile_candidates(repo: Path, keywords: set[str], project: str | None = None) -> list[dict]:
    """The profiles as typed rows: author-architecture fields (field name + summary +
    his-confirmed flag), house-style rules, and the voice register. Substrate rows —
    embedding-gated when a model is present, keyword-gated offline."""
    out: list[dict] = []
    try:
        import yaml  # type: ignore
    except Exception:
        yaml = None

    # -- author_architecture.yaml: the whole-paper structural grain, field by field.
    from laplace.pipeline import narrative
    architecture = narrative.architecture_status(repo, include_content=True)
    if architecture['status'] == 'AVAILABLE':
        prof = architecture.get('fields') or {}
        version = architecture['profile_revision']
        if isinstance(prof, dict):
            for field, val in prof.items():
                if not isinstance(val, dict) or "summary" not in val:
                    continue
                summary = str(val["summary"])
                confirmed = bool(val.get('confirmed_his'))
                flag = ('[confirmed-his] ' if confirmed else '[historical confirmation assertion] '
                    if val.get('historical_confirmation_assertion') else '[reconstructed] ')
                out.append({
                    "source": "profiles/author_architecture.yaml",
                    "ref": str(field),
                    "date": version,
                    "quote": _bounded(summary, flag),
                    "text": field.replace("_", " ") + ". " + summary,
                    "overrule": False,
                    "kw_match": _matches(summary + " " + field, keywords),
                    "gate": "substrate",
                })

    # -- house_style rules: cross-ref / citation / orthography preferences.
    house = repo / "profiles" / "house_style" / "gerard-manuscript-v1.yaml"
    if yaml is not None and house.is_file():
        try:
            data = yaml.safe_load(house.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            data = None
        for rule in (data or {}).get("rules", []) if isinstance(data, dict) else []:
            if not isinstance(rule, dict) or not rule.get("id"):
                continue
            dim = str(rule.get("dimension", ""))
            prefer = str(rule.get("prefer", ""))
            notes = str(rule.get("rule_notes", ""))
            body = f"{dim}: prefer {prefer}. {notes}".strip()
            out.append({
                "source": "profiles/house_style/gerard-manuscript-v1.yaml",
                "ref": str(rule["id"]),
                "date": "",
                "quote": _bounded(body, "[house-style] "),
                "text": f"{rule['id']} {body}",
                "overrule": False,
                "kw_match": _matches(body + " " + str(rule["id"]), keywords),
                "gate": "substrate",
            })

    # -- voice register: one row, the operational voice slice.
    from laplace.manuscript import writing_style
    try:
        voice = writing_style.context(project, repo)
    except (ValueError, OSError):
        voice = None
    if voice:
        register = voice['content']
        if voice.get('guidance'):
            register += '\n\nPROJECT VOICE GUIDANCE\n' + voice['guidance']
        if voice.get('genre'):
            register += '\n\nPROJECT GENRE\n' + voice['genre']
        out.append({
            "source": voice['selected_profile'],
            "ref": Path(voice['selected_profile']).stem,
            "date": voice['profile_revision'],
            "quote": _bounded(register, "[voice] "),
            "text": register,
            "overrule": False,
            "kw_match": _matches(register, keywords),
            "gate": "substrate",
        })
    return out


def _store_candidates(repo: Path) -> list[dict]:
    """Every stage-store row of his first-author corpus, each carrying its precomputed
    unit vector so the whole corpus ranks against a claim by dot product. Rows without a
    precomputed vector are skipped (nothing to rank them by; the skip is stated)."""
    out: list[dict] = []
    base = repo / "corpus_stores"
    for store in _STORES:
        sdir = base / store
        if not sdir.is_dir():
            continue
        emb_path = sdir / "embeddings.json"
        if not emb_path.is_file():
            continue
        try:
            items = json.loads(emb_path.read_text(encoding="utf-8", errors="replace")).get("items", {})
        except Exception:
            continue
        if not isinstance(items, dict) or not items:
            continue
        for jf in sorted(sdir.glob("*.jsonl")):
            if jf.name.startswith("_"):
                continue
            for line in jf.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = str(row.get("row_id", ""))
                vec = items.get(rid)
                if not rid or vec is None:
                    continue
                form = row.get("form") or {}
                job = str(form.get("job") or form.get("title") or form.get("normalized_job") or "")
                paper = str((row.get("provenance") or {}).get("paper_id", jf.stem))
                embed_text = str(row.get("embed_text", ""))
                head = f"[{store}·{paper}] " + (f"{job}: " if job else "")
                out.append({
                    "source": f"corpus_stores/{store}/{jf.name}",
                    "ref": rid,
                    "date": paper,
                    "quote": _bounded(embed_text, head),
                    "vec": vec,
                    "overrule": False,
                    "kw_match": False,
                    "gate": "substrate",
                })
    return out


# ---------------------------------------------------------------- the retrieval
_UNSET = object()


def retrieve_taste(repo_root: Path | str, keywords: set[str], claim: str,
                   cap: int, backend=_UNSET, *, project: str | None = None) -> dict:
    """Rank the whole taste substrate against a claim and return the bounded, refs-only
    slice plus its provenance.

    Returns ``{"entries": [...], "provenance": {...}}`` where each entry is exactly
    ``{source, ref, quote, date}`` (refs-only; the quote is the only free text, bounded and
    carrying its typed flag as a prefix). Overrules that match ride FIRST (his law); the
    remainder rank by raw embedding cosine, or by keyword overlap when no model is reachable
    (marked ``keyword-degraded``). The distilled metric is deliberately skipped as stale —
    the provenance says so.

    ``backend`` defaults to the router's process-wide model; pass an explicit backend (or
    ``None`` to force the offline path) for hermetic tests.
    """
    repo = Path(repo_root)
    kws = set(keywords or set())

    rulings = _ruling_candidates(repo, kws)
    promises = _promise_candidates(repo, kws)
    profiles = _profile_candidates(repo, kws, project)
    stores = _store_candidates(repo)

    if backend is _UNSET:
        try:
            from laplace.representation import embed_router
            backend = embed_router.get_backend()
        except Exception:
            backend = None

    provenance: dict = {
        "channel": "taste-substrate",
        # the metric verdict from the files alone (fresh / stale / absent); the online
        # branch re-checks with the backend's dim and applies M when fresh.
        "metric": _metric_status(repo, None)[1],
        "sources": {
            "rulings": sum(1 for r in rulings if not r["overrule"]),
            "overrules": sum(1 for r in rulings if r["overrule"]),
            "promise_asks": len(promises),
            "profile_fields": len(profiles),
            "store_exemplars": len(stores),
        },
    }

    all_candidates = rulings + promises + profiles + stores

    reserve = _overrule_reserve(cap)

    if backend is None:
        # --- offline: keyword overlap is the fallback, marked degraded. Substrate rows
        #     ride only on a keyword match; a matching overrule takes up to `reserve` top
        #     slots, the rest order newest-first.
        provenance["ranking"] = "keyword-degraded"
        provenance["model"] = None
        for c in all_candidates:
            c["_sim"] = 1.0 if c["kw_match"] else 0.0
        kept = [c for c in all_candidates if c["overrule"] or c["kw_match"]]
        overrules = sorted((c for c in kept if c["overrule"]),
                           key=lambda c: (_neg(c.get("date", "")), c["ref"]))
        rest = sorted((c for c in kept if c not in overrules),
                      key=lambda c: (_neg(c.get("date", "")), c["ref"]))
        selected = overrules[:reserve] + rest + overrules[reserve:]
    else:
        # --- online: raw-cosine rank of the whole substrate against the claim (the stale
        #     metric is skipped). Overrules ride the reserved top slots when relevant; the
        #     remaining, larger part of the channel is the corpus + rulings by similarity.
        provenance["ranking"] = "embedding"
        provenance["model"] = getattr(backend, "name", "?")
        provenance["substrate_floor"] = _SUBSTRATE_FLOOR
        provenance["overrule_reserve"] = reserve
        try:
            qv = backend.query(claim)
        except Exception:
            qv = None
        if qv is not None:
            # apply the trained metric when it is FRESH against the current basis: bend the
            # query by M so every similarity below is q'Mv (the skip branch stays live for a
            # stale/absent/mismatched metric, and the provenance names which held).
            M, metric_status = _metric_status(repo, len(qv))
            provenance["metric"] = metric_status
            if M is not None:
                import numpy as np
                qv = np.asarray(qv, dtype="float32") @ M
        if qv is None:
            provenance["ranking"] = "keyword-degraded"
            provenance["model"] = None
            for c in all_candidates:
                c["_sim"] = 1.0 if c["kw_match"] else 0.0
            kept = [c for c in all_candidates if c["overrule"] or c["kw_match"]]
            overrules = sorted((c for c in kept if c["overrule"]),
                               key=lambda c: (_neg(c.get("date", "")), c["ref"]))
            rest = sorted((c for c in kept if c not in overrules),
                          key=lambda c: (_neg(c.get("date", "")), c["ref"]))
            selected = overrules[:reserve] + rest + overrules[reserve:]
        else:
            scored: list[dict] = []
            for c in all_candidates:
                if "vec" in c:
                    sim = _cos(qv, c["vec"])
                else:
                    ev = _embed_one(backend, c["text"])
                    sim = _cos(qv, ev) if ev is not None else 0.0
                c["_sim"] = sim
                if c["overrule"]:
                    # relevance still gates a force: keyword match, or a HIGH cosine.
                    if c["kw_match"] or sim >= _FORCE_FLOOR:
                        scored.append(c)
                elif c["gate"] == "ruling":
                    scored.append(c)  # already keyword-gated at candidacy
                elif sim >= _SUBSTRATE_FLOOR:
                    scored.append(c)
            by_sim = sorted(scored, key=lambda c: (-round(c["_sim"], 6), c["ref"]))
            overrules = [c for c in by_sim if c["overrule"]]
            rest = [c for c in by_sim if not c["overrule"]]
            selected = overrules[:reserve] + rest + overrules[reserve:]

    # dedupe by (source, ref); the reserved overrules already lead; cap the whole channel.
    seen: set[tuple[str, str]] = set()
    entries: list[dict] = []
    forced: list[str] = []
    for c in selected:
        key = (c["source"], c["ref"])
        if key in seen:
            continue
        seen.add(key)
        if c["overrule"] and len(forced) < reserve and len(entries) < reserve:
            forced.append(c["ref"])
        entries.append({
            "source": c["source"], "ref": c["ref"],
            "quote": c["quote"], "date": c.get("date", ""),
        })
        if len(entries) >= cap:
            break
    provenance["overrules_forced"] = forced
    return {"entries": entries, "provenance": provenance}


def _neg(s: str) -> tuple:
    """A reverse-lexicographic sort key for a date string: sorts NEWEST first without
    reversing the whole (overrule-first) order. Deterministic on equal dates via the ref
    tiebreak the caller appends."""
    return tuple(-ord(ch) for ch in s)
