"""stage_retrieval.py — the RETRIEVAL WIRE for the stage-stores (Wave 2E).

The generalisation of :mod:`laplace.pipeline.voice_retrieval` one altitude UP.
The voice pass writes prose FROM his real prose (``voice_retrieval.build_channel``
→ the ``RETRIEVED-EXEMPLARS`` fence in ``compile_weld_dispatch``); this module does
the same for every PLANNING stage — the pipeline retrieves the nearest REAL
exemplars from a gate-passed stage-store and fences their FORM (never their
content) into the stage's compiled dispatch (DESIGN_2026-07-15_the-stage-stores
§4, §2.1).

The three laws, wired not remembered (his, non-negotiable):

  * **FORM never CONTENT** (§2.1). A store row has two typed regions: ``embed_text``
    (his REAL prose — the retrieval basis + an audit handle) and ``form`` (the
    abstracted shape). This channel surfaces ONLY the ``form`` fields and the
    ``paper_id``/``section_label`` provenance — NEVER ``embed_text``. The guarantee
    is structural, not disciplined: retrieval loads the store's ``_index.json``
    (whose ROWS carry no ``embed_text`` — the ``.jsonl`` files that do are never
    opened here; store-level ``caveats`` notes may name the field, but they are
    fleet metadata outside the rows and are never fenced) and surfaces a fixed
    WHITELIST of form keys. There is no prose in the fence to leak; the envelope
    preamble states the rule the schema enforces.

  * **Gate-passed only, and the dial cannot override the gate** (§4 kill-switch).
    A store is readable IFF ``dials.stores.<store>.enabled`` is true (a deliberate
    act — every per-store dial ships false, so the wiring lands behaviour-inert)
    AND its ``gate_verdict.json`` says ``passed=true`` (the holdout gate's
    evidence, §5). A DISABLED store is a silent no-op (``None`` — the inert
    default). A store whose dial is ON but whose gate verdict is absent or FAILED
    REFUSES LOUDLY (``SystemExit``): the dial is a permission, never a proof, and a
    store that cannot pick the right exemplar is worse than no store.

  * **Defective rows are never retrieved** (§2.1). Rows the store marks defective
    (``_index.json`` ``defective_rows`` / a row's ``defective`` flag — e.g. a
    chunker splice) are excluded from the candidate set by construction.

Deterministic for a fixed store + query: the query embeds once through the SAME
local backend the store used (the vendored bge-small over ONNX, offline-safe),
cosine ranks the non-defective rows, and ties break on ``row_id`` — so a fixed
store + query always renders the same envelope.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from laplace.representation.embed_router import get_backend
from laplace.pipeline import schema
from laplace.pipeline.dials import load_dials

#: the fenced channel name (DESIGN §4's FORM-EXEMPLARS injection channel).
FORM_EXEMPLAR_CHANNEL = "FORM-EXEMPLARS"

#: the ONE-LINE law that heads the envelope (his words, §4/§2.1).
FORM_LAW = ("form exemplars from the author's published corpus — imitate the "
            "SHAPE, never the content")

#: the form-never-content type-boundary preamble (DESIGN §4, modelled on the
#: weld's ``register_instruction``). Because rows surface ``form`` and never
#: ``embed_text``, there is no prose in the fence to leak — this states the rule
#: the schema already enforces.
FORM_PREAMBLE = (
    "FORM EXEMPLARS — these show HOW comparable real paragraphs/sections/steps are "
    "SHAPED (their role, their connective, their granularity). They are FORM ONLY. "
    "They carry NONE of this paper's content; your content comes solely from the "
    "OBJECT/PACKET above (the conceptric). Match their move-structure, never their "
    "subject. Introducing a claim, number, or citation from an exemplar is the "
    "contamination fault."
)

#: the FORM fields surfaced into the prompt — a WHITELIST, so no field outside it
#: (least of all ``embed_text``) can ever reach a stage prompt (§2.1). Provenance
#: (``paper_id``/``section_label``) is added alongside, per-exemplar. Keys absent
#: from a row render null and are harmless — the union below serves all five
#: stores (paragraph_plan + the four-lens stores merged 2026-07-15: their gate
#: classes and residue fields must be surfaceable or a flipped store would render
#: empty form blocks).
_FORM_KEYS = (
    # paragraph_plan
    "normalized_role", "role", "connective_prev", "connective_next",
    "proposition_shape", "detail_level", "length_band",
    "carries_math", "carries_figure",
    # section_architecture
    "normalized_job", "job", "arc", "question_class",
    # spine_chain
    "ladder_move", "claim_class", "supports_class",
    # derivation_walk
    "step_kind", "granularity", "elision", "eq_env",
    # figure_caption (gated OUT today; the whitelist is store-agnostic)
    "caption_move", "figure_role", "panels", "panel_labels",
)


def _read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _gate_refusal(verdict: dict[str, Any] | None) -> str | None:
    """``None`` when the store may be served; else the DECLARED one-line reason it is
    REFUSED. Three ways a dial-enabled store is refused (§4/§5 + SCOUT_2026-07-16
    TRACK B ADDENDUM — the ``gate.passed``-only check was a live hazard):

      * ``refusal_proof_holds=false`` — the store cannot prove it REFUSES a
        signal-free / planted-bad query (figure_caption's plain OUT). A true
        ``gate.passed`` does NOT redeem it: a store that also fires on noise is
        worse than no store, and a flipped dial must not smuggle it in.
      * ``wired_in=false`` — the rows are not verified wired to the gate class the
        score was measured on; a passing number describing a different object.
      * ``gate.passed != true`` (or an absent verdict) — the holdout gate itself
        did not pass.

    Only an EXPLICIT ``false`` on a proof field refuses; an ABSENT field is not a
    refusal (a verdict predating the field is judged on its gate alone) — so this
    closes the known hazard without retro-failing older/leaner verdicts."""
    if not isinstance(verdict, dict):
        return "gate_verdict.json absent"
    if verdict.get("refusal_proof_holds") is False:
        return ("refusal_proof_holds=false — the store cannot prove it refuses a "
                "signal-free/planted-bad query; its OUT is honest and gate.passed "
                "does not override it")
    if verdict.get("wired_in") is False:
        return ("wired_in=false — the store's rows are not verified wired to the "
                "gate class its score was measured on")
    top = verdict.get("passed")
    if isinstance(top, bool):
        passed = top
    else:
        gate = verdict.get("gate")
        passed = bool(isinstance(gate, dict) and gate.get("passed") is True)
    return None if passed else "gate.passed!=true"


def _gate_passed(verdict: dict[str, Any] | None) -> bool:
    """The store's readiness predicate (§5), HARDENED: served IFF the holdout gate
    passed (``gate.passed`` — a top-level ``passed`` honoured too) AND neither
    ``refusal_proof_holds`` nor ``wired_in`` is explicitly false. figure_caption
    ships ``gate.passed=true`` with ``refusal_proof_holds=false`` — the smuggle a
    flipped dial must not open. Absent/None verdict → not passed. The stated reason
    on refusal is :func:`_gate_refusal`."""
    return _gate_refusal(verdict) is None


def _defective_ids(index: dict[str, Any]) -> set[str]:
    """Every defective row_id (§2.1): the top-level ``defective_rows`` roster AND
    any row flagged ``defective`` inline — a defective row is never a candidate."""
    ids = {r.get("row_id") for r in (index.get("defective_rows") or [])
           if isinstance(r, dict) and r.get("row_id")}
    ids |= {r.get("row_id") for r in (index.get("rows") or [])
            if isinstance(r, dict) and r.get("defective") and r.get("row_id")}
    return ids


def build_form_channel(store: str, query_text: str, k: int = 3,
                       dials: dict[str, Any] | None = None,
                       root: str | Path = ".") -> str | None:
    """The per-stage ``FORM-EXEMPLARS`` envelope (str) for one gate-passed store, or
    ``None`` when disabled. The envelope-only projection of
    :func:`build_form_channel_and_record`; the record-bearing sibling is what a
    wire uses to bank the audit sidecar. See that function for the full contract."""
    served = build_form_channel_and_record(store, query_text, k=k, dials=dials,
                                            root=root)
    return None if served is None else served[0]


def build_form_channel_and_record(
        store: str, query_text: str, k: int = 3,
        dials: dict[str, Any] | None = None,
        root: str | Path = ".") -> tuple[str, dict[str, Any]] | None:
    """The per-stage ``FORM-EXEMPLARS`` channel + its durable AUDIT record.

    Returns ``(envelope, record)`` where ``envelope`` is the rendered fenced block
    ready to append to a compiled dispatch and ``record`` is the sidecar payload
    ``{store, k, query_digest, ts, n_exemplars, exemplars:[{row_id, cos}]}`` —
    everything needed to watch a flipped store IN USE without re-reading the prompt
    (its `write_form_channel_sidecar`). Returns ``None`` when the store is disabled
    — the inert default (a silent no-op, so wiring lands behaviour-inert and NO
    sidecar is written until a dial is deliberately flipped). ``store`` is the store
    name (e.g. ``paragraph_plan``); ``query_text`` is the stage's current OBJECT
    (DESIGN §4: "embed the stage's current OBJECT").

    Gate law (§4): readable IFF ``dials.stores.<store>.enabled`` AND the store's
    ``gate_verdict.json`` passes :func:`_gate_refusal` (gate passed, refusal proof
    holds, wired in). A DISABLED store → ``None``. An ENABLED store the gate refuses
    **raises** ``SystemExit`` with the Stated reason — the dial cannot override the
    gate (a loud refusal; the caller may catch it exactly as the weld catches
    ``voice_retrieval``'s fail-loud). A broken/unembedded gate-passed store likewise
    raises (fail loud, never a silent degrade).

    FORM never CONTENT (§2.1): the envelope surfaces only ``_FORM_KEYS`` +
    ``paper_id``/``section_label``. ``embed_text`` is never loaded (retrieval reads
    ``_index.json``, which carries none). The record carries only ``row_id``/``cos``
    provenance, never form or prose. Deterministic for a fixed store + query (the
    record's ``ts`` is the only non-deterministic field, and it is audit-only —
    never fenced into the prompt, so the byte-inert law is untouched).
    """
    if dials is None:
        dials = load_dials()
    store_dial = (dials.get("stores") or {}).get(store) or {}
    if not store_dial.get("enabled"):
        return None                     # inert default: disabled store is a no-op

    store_dir = Path(root) / "corpus_stores" / store
    verdict = _read_json(store_dir / "gate_verdict.json")
    refusal = _gate_refusal(verdict)
    if refusal is not None:
        # the dial is ON but the gate refuses: the dial is a permission, never a
        # proof (§4/§5). REFUSE loudly with the HONEST reason — gate.passed alone is
        # not enough (figure_caption passes its gate yet its refusal proof fails), a
        # store that did not earn its place is worse than no store, and a flipped
        # dial must not smuggle it in. Fail-loud idiom shared with the voice store.
        raise SystemExit(
            f"stage_retrieval: store {store!r} is dial-enabled but REFUSED — "
            f"{refusal} (at {store_dir}). The dial cannot override the gate; flip it "
            f"only when the gate passes and its refusal proof holds."
        )

    index = _read_json(store_dir / "_index.json")
    embeddings = _read_json(store_dir / "embeddings.json")
    if not isinstance(index, dict) or not isinstance(embeddings, dict):
        raise SystemExit(
            f"stage_retrieval: store {store!r} passed its gate but its index/"
            f"embeddings are missing or unreadable at {store_dir} — rebuild the "
            f"store (disaster recovery); a gate-passed store must load."
        )
    items = embeddings.get("items") or {}
    defective = _defective_ids(index)
    rows = [r for r in (index.get("rows") or [])
            if isinstance(r, dict) and r.get("row_id")
            and r["row_id"] not in defective and r["row_id"] in items]
    if not rows:
        raise SystemExit(
            f"stage_retrieval: store {store!r} passed its gate but carries no "
            f"non-defective embedded rows at {store_dir} — rebuild the store."
        )

    backend = get_backend()
    if backend is None:
        # enabled + gate-passed but no local model to embed the query: the
        # generative substrate is reachable, the query is not. Fail loud (§4),
        # exactly as the voice store does — never a silent no-op that would look
        # like the inert default.
        raise SystemExit(
            f"stage_retrieval: no embedding backend to query store {store!r}; "
            f"the vendored bge-small model did not load."
        )

    import numpy as np

    X = np.asarray([items[r["row_id"]] for r in rows], dtype=np.float64)
    X /= np.clip(np.linalg.norm(X, axis=1, keepdims=True), 1e-12, None)
    q = np.asarray(backend.embed([query_text])[0], dtype=np.float64)
    q /= max(float(np.linalg.norm(q)), 1e-12)
    scores = X @ q

    # deterministic top-k: rank by (-cos, row_id) so a fixed store + query always
    # renders the same exemplars (ties never reorder run-to-run).
    order = sorted(range(len(rows)),
                   key=lambda i: (-float(scores[i]), rows[i]["row_id"]))
    top = order[:max(1, int(k))]

    exemplars: list[dict[str, Any]] = []
    for i in top:
        r = rows[i]
        form = r.get("form") or {}
        prov = r.get("provenance") or {}
        span = prov.get("span_ref") or {}
        exemplars.append({
            "row_id": r["row_id"],
            "paper_id": prov.get("paper_id"),
            "section_label": span.get("section_label"),
            "cos": round(float(scores[i]), 3),
            # FORM ONLY — a fixed whitelist; embed_text is not in scope here.
            "form": {key: form.get(key) for key in _FORM_KEYS},
        })

    k_eff = max(1, int(k))
    header = (f"{store} — {FORM_LAW}\n"
              f"store: {store} · k={k_eff} · {len(exemplars)} exemplars")
    body = "\n\n".join([
        header,
        FORM_PREAMBLE,
        json.dumps(exemplars, ensure_ascii=False, indent=1),
    ])
    envelope = schema.fence(FORM_EXEMPLAR_CHANNEL, body)
    record = {
        "store": store,
        "k": k_eff,
        "query_digest": "sha256:" + hashlib.sha256(
            query_text.encode("utf-8")).hexdigest()[:16],
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "n_exemplars": len(exemplars),
        # PROVENANCE ONLY — the exact rows served and how near, so a flipped store
        # is watchable mechanically. NO form, NO prose (that lives in the ephemeral
        # prompt fence, never the durable sidecar).
        "exemplars": [{"row_id": e["row_id"], "cos": e["cos"]} for e in exemplars],
    }
    return envelope, record


#: the sidecar STEM the form channel banks under (mirrors
#: :data:`voice_retrieval.SIDECAR_NAME`). Voice banks ONE file per weld; a planning
#: stage can inject MORE THAN ONE store (the narrative planner injects both
#: ``paragraph_plan`` and ``spine_chain``) and compiles PER SECTION, so the form
#: sidecar is keyed by store + target — one durable record per (store, section).
SIDECAR_STEM = "_form_retrieval"


def sidecar_name(store: str, target_stem: str) -> str:
    """The per-(store, section) sidecar filename, e.g.
    ``_form_retrieval.paragraph_plan.N4.json``. ``target_stem`` is the caller's
    path-safe section id (the wire encodes it exactly as it names the dispatch
    record, so the sidecar sits beside its dispatch)."""
    return f"{SIDECAR_STEM}.{store}.{target_stem}.json"


def write_form_channel_sidecar(path: Path | str,
                               record: dict[str, Any]) -> Path:
    """PERSIST one SERVED ``FORM-EXEMPLARS`` record to a JSON sidecar (the form-
    channel sibling of :func:`voice_retrieval.write_channel_sidecar`).

    Before this, a flipped store's influence had NO on-disk trace — "watch them in
    use" meant reading compiled prompts by hand. This file-backs the served record
    ``{store, k, query_digest, ts, n_exemplars, exemplars:[{row_id, cos}]}`` so a
    run's FORM grounding is an auditable object. Written ONLY when an envelope was
    served (the caller banks iff :func:`build_form_channel_and_record` returned
    non-``None``); a disabled store writes nothing. The record carries provenance
    only — never form, never prose — so this sidecar is safe to keep. Returns the
    written path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(record, ensure_ascii=False, indent=1),
                 encoding="utf-8")
    return p
