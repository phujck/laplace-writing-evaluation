"""structural_conformance.py — The pre-projection conformance pass (SCOUT_2026-07-16
line 4 / line 5; the high-altitude sibling of the local voice washer).

His commission (PV-20260717T002125Z, "Commission it") on the scout's synthesis:
**the adjudication persona IS the revoicing persona** — the same profile-organ-
wearing judge that closes a parked structural fork rules "he'd respine/demote/reorder
this section", and its ruling is a PV verdict the EXISTING apply bridge executes on
the spine/storyboard. This module is the READ leg of that loop: it reads a project's
authored spine+plan, retrieves the nearest authored section-architectures and ladder-
moves, and emits CANDIDATE structural patches — stated in the projection-intent op
vocabulary (``evolution_consumer._VERB_TO_PROPOSED_OP``: CUT/DEMOTE/SPLIT/REORDER/
RESPINE…) — as a DISPATCH MANIFEST for the profile-wearing judge.

Three hard boundaries, wired not remembered:

  * **BUILDER ≠ JUDGE.** This module NEVER calls a model and NEVER decides. It
    computes a transparent conformance SIGNAL (how far a section sits from the
    author's own published manifold, a cosine measurement) and CONJECTURES a
    candidate verb from it (every candidate stamped ``provenance="conjectured"`` with
    its signal, per the honesty law). The judge — reading the shared frame's profile
    organs + the retrieved FORM exemplars — rules KEEP or a verb; the conjecture is a
    prior, never a verdict.

  * **the same judge, the same bank path.** The manifest's shared frame is
    :func:`author_proxy.assemble_decision_frame` (the fusion organ — its third input,
    the FORM-EXEMPLARS envelope, is exactly this pass's structural evidence), hoisted
    ONCE at the manifest top (the growth-adjudicator manifest idiom). Every ruling
    banks through :func:`author_proxy.bank_ruling` — no new adjudication surface.

  * **no new apply mechanism.** A ruling that changes structure becomes an open
    projection-intent; :func:`evolution_consumer.apply_plan_proposals` (Fork-8 ruled,
    ``PV-20260713T221204Z-weld-apply-bridge``) derives what is derivable and routes
    section ops needs-author. This module APPLIES NOTHING. The read leg is
    LEDGER-INERT: it writes ONLY the manifest artifact — never ``proxy_verdicts.jsonl``,
    never ``feedback.jsonl`` (the boom guard the tests enforce).

Dial-gated like every lens: the two stores (``section_architecture``, ``spine_chain``)
are read IFF their per-store dial is enabled AND their holdout gate passes (the
retrieval wire's two-key law). At the default (dial-off) the pass is behaviour-inert —
it emits a declared empty-patch manifest naming the disabled stores, exactly as the
rest of the store wiring lands inert until a deliberate flip.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from laplace.engine import author_proxy
from laplace.pipeline import stage_retrieval
from laplace.pipeline.evolution_consumer import _VERB_TO_PROPOSED_OP

#: the two structural stores this pass reads (the scout's line 57 evidence):
#: section_architecture's ``normalized_job``/``arc`` + spine_chain's ``ladder_move``
#: are exactly the structural evidence a "he'd respine/demote this" ruling needs.
_ARCH_STORE = "section_architecture"
_SPINE_STORE = "spine_chain"

#: the conformance FLOOR is plan-RELATIVE (``mean - Z*std`` over this manuscript's
#: section-to-authored cosines), not an absolute cutoff. Length/register differences
#: between a plan's terse ``job`` text and a published section's full prose shift the
#: absolute cosine wholesale; the plan-relative outlier is robust to that shift and
#: portable across projects — it answers "which sections conform LEAST, relative to
#: the rest of this manuscript and the authored corpus". Z is documented, tunable.
_FLOOR_Z = 0.5

#: position-drift above this (normalized 0..1) flags a section whose authored analog
#: sits at a very different point in the arc → a REORDER candidate rather than a
#: whole RESPINE.
_POSITION_DRIFT = 0.34

#: the bank contract every packet carries — the SAME path a fork ruling banks
#: through (author_proxy.bank_ruling), so the structural-conformance judge and the
#: fork-adjudication judge are literally one organ.
STRUCTURAL_BANK_CONTRACT: dict = {
    "function": "laplace.engine.author_proxy.bank_ruling",
    "signature": "bank_ruling(repo_root, ruling) -> dict",
    "kind": "structural-conformance",
    "required_keys": list(author_proxy.REQUIRED_KEYS),
    "confidence_levels": sorted(author_proxy.CONFIDENCE_LEVELS),
    "id_shape": "PV-<UTCstamp>-<slug>  (via author_proxy.make_ruling_id)",
    "note": (
        "The dispatched profile-wearing judge returns a ruling carrying the required "
        "keys; the consumer calls author_proxy.bank_ruling(repo_root, ruling) — the "
        "SAME append-only, decide-and-bank, contested-not-veto path a parked fork "
        "banks through. A ruling that changes structure is written as an open "
        "projection-intent for the apply bridge below."
    ),
}

#: how a banked ruling LANDS — the EXISTING bridge, named so the manifest is
#: self-describing. No new apply mechanism; no auto-apply beyond Fork-8's derivable.
APPLY_BRIDGE: dict = {
    "function": "laplace.pipeline.evolution_consumer.apply_plan_proposals",
    "signature": "apply_plan_proposals(out_dir, corpus, *, by) -> dict",
    "note": (
        "A structural ruling becomes an open projection-intent in the project's "
        "feedback ledger; apply_plan_proposals derives what Fork-8 ruled derivable "
        "(a resolved meta target under a mechanical verb → set-meta through the "
        "storyboard plan-ledger door) and routes section ops needs-author (content "
        "judgment, never guessed). This pass applies NOTHING — it is the read leg."
    ),
}


# --------------------------------------------------------------------------- helpers
def _store_form_index(store: str, root: Path | str) -> dict[str, dict]:
    """``{row_id: form}`` for every non-defective row of ``store`` — read from the
    store's ``_index.json`` (FORM ONLY; the index rows carry no ``embed_text``, so no
    prose is touched). Used to look up a served exemplar's ``position``/``arc`` for
    the candidate conjecture. Empty dict when the index is absent/unreadable."""
    p = Path(root) / "corpus_stores" / store / "_index.json"
    try:
        index = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    defective = {r.get("row_id") for r in (index.get("defective_rows") or [])
                 if isinstance(r, dict) and r.get("row_id")}
    out: dict[str, dict] = {}
    for r in (index.get("rows") or []):
        rid = isinstance(r, dict) and r.get("row_id")
        if rid and rid not in defective and not r.get("defective"):
            out[rid] = r.get("form") or {}
    return out


def _serve(store: str, query: str, k: int, dials: dict | None,
           root: Path | str) -> tuple[str | None, dict | None, str]:
    """Retrieve ``store`` for ``query`` through the one gate-and-dial-gated wire.
    Returns ``(envelope, record, note)``. ``record`` is ``None`` when nothing was
    served (dial-off or refused), and ``note`` is the stated reason — mirroring the
    frame's declared presence/absence discipline (a store is never a silent no-op)."""
    try:
        served = stage_retrieval.build_form_channel_and_record(
            store=store, query_text=query, k=k, dials=dials, root=root)
    except SystemExit as exc:                    # dial ON but gate refused / broken
        return None, None, f"refused: {exc}"
    if served is None:
        return None, None, "dial-off (store not enabled)"
    envelope, record = served
    return envelope, record, f"served: k={max(1, int(k))}"


def _parse_position(pos: Any) -> float | None:
    """Normalise a ``"k-of-N"`` position (section_architecture ``form.position``) to
    ``(k-1)/(N-1)`` in ``[0, 1]``, or ``None`` if unparseable. So a section's place
    in the arc can be compared to its authored analog's place."""
    if not isinstance(pos, str) or "-of-" not in pos:
        return None
    try:
        k_str, n_str = pos.split("-of-")
        k_i, n_i = int(k_str), int(n_str)
    except (ValueError, TypeError):
        return None
    if n_i <= 1:
        return 0.0
    return max(0.0, min(1.0, (k_i - 1) / (n_i - 1)))


def _floor(cosines: list[float]) -> float | None:
    """The plan-relative conformance floor ``mean - _FLOOR_Z*std`` over ``cosines``.
    ``None`` when there is nothing to compare against (0 or 1 scored section)."""
    n = len(cosines)
    if n < 2:
        return None
    mean = sum(cosines) / n
    var = sum((c - mean) ** 2 for c in cosines) / n
    return mean - _FLOOR_Z * (var ** 0.5)


def _conjecture_verb(arch_cos: float, spine_cos: float,
                     arch_floor: float | None, spine_floor: float | None,
                     position_drift: float | None) -> str | None:
    """CONJECTURE one candidate verb (in the projection-intent op vocabulary) for a
    section, or ``None`` when the section conforms (no patch). A verb is proposed ONLY
    for a section below the plan-relative arch floor (it conforms least):

      * also below the spine floor (off BOTH authored manifolds) → ``RESPINE`` — the
        whole shape is unlike anything he writes; respine it toward the nearest arc;
      * else a large position drift (fits an authored job, but at the wrong point in
        the arc) → ``REORDER``;
      * else (weak fit, no clear drift) → ``DEMOTE`` — it earns less prominence in the
        ladder than its current place claims.

    Never returns a verb outside :data:`_VERB_TO_PROPOSED_OP`; the judge overrides
    freely — this is a prior, not a verdict."""
    if arch_floor is None or arch_cos >= arch_floor:
        return None                              # conforms — no candidate patch
    if spine_floor is not None and spine_cos < spine_floor:
        return "RESPINE"
    if position_drift is not None and position_drift > _POSITION_DRIFT:
        return "REORDER"
    return "DEMOTE"


def _proposed_op(verb: str) -> str:
    """The storyboard plan op the verb maps to for a SECTION object (the same map the
    evolution consumer's apply bridge reads) — kept in the op vocabulary by
    construction. Falls back to ``set-meta`` only if the verb is unknown (it never is,
    since candidates come from :func:`_conjecture_verb`)."""
    return _VERB_TO_PROPOSED_OP.get(verb, {}).get("section", "set-meta")


# ------------------------------------------------------------------- the read + build
def build_conformance_manifest(corpus: str, *, k: int = 3,
                               dials: dict | None = None,
                               root: str | Path = ".",
                               out_path: str | Path | None = None,
                               write: bool = True) -> dict:
    """the read leg: read ``corpus``'s authored spine+plan, retrieve the nearest
    authored section-architectures / ladder-moves per section, conjecture candidate
    structural patches in the projection-intent op vocabulary, and emit the dispatch
    manifest the profile-wearing judge consumes. READ-ONLY: writes ONLY the manifest
    file at ``out_path`` (default ``<manuscript>/dispatches/structural_conformance_
    manifest.json`` when resolvable, else nothing on disk). NEVER writes a ledger,
    NEVER applies, NEVER calls a model.

    ``write=False`` is the dry-run preview (the conjugate wave, Lane 3): the manifest
    is computed and RETURNED but nothing is written to disk (no manifest file, no
    ``invocation``/``manifest_path`` stamped) — the ``/pipeline`` structural card's
    pre-arm preview. ``write=True`` (the default, the FIRE) banks the manifest at
    ``out_path``.

    Returns the manifest dict (identical to the file when one is written):
    ``{kind, corpus, schema, count, cut_at, frame, bank_contract, apply_bridge,
    packets, conformant, unscored, stores, read_only}``.
    """
    from laplace.manuscript import storyboard as _sb

    plan = _sb.enriched_plan(corpus)
    if plan is None:
        return {"kind": "structural-conformance", "corpus": corpus,
                "error": f"no projection plan for {corpus!r}", "packets": [],
                "count": 0, "read_only": True}

    sections = plan.get("sections") or []
    n = len(sections)
    arch_forms = _store_form_index(_ARCH_STORE, root)

    # PASS 1 — retrieve + score every section (the plan-relative floor needs the whole
    # distribution before any section can be flagged).
    scored: list[dict] = []
    store_notes: dict[str, str] = {}
    for i, s in enumerate(sections):
        sid = s.get("id") or f"section-{i}"
        title = s.get("title") or ""
        job = s.get("job") or ""
        query = (f"{title}. {job}").strip()
        pos_label = f"{i + 1}-of-{n}"

        arch_env, arch_rec, arch_note = _serve(_ARCH_STORE, query, k, dials, root)
        spine_env, spine_rec, spine_note = _serve(_SPINE_STORE, query, k, dials, root)
        store_notes.setdefault(_ARCH_STORE, arch_note)
        store_notes.setdefault(_SPINE_STORE, spine_note)

        arch_ex = (arch_rec or {}).get("exemplars") or []
        spine_ex = (spine_rec or {}).get("exemplars") or []
        arch_cos = max((e["cos"] for e in arch_ex), default=None)
        spine_cos = max((e["cos"] for e in spine_ex), default=None)
        nearest_arch = arch_ex[0]["row_id"] if arch_ex else None
        nearest_spine = spine_ex[0]["row_id"] if spine_ex else None

        # position drift vs the nearest authored analog's place in its own arc
        authored_pos = _parse_position((arch_forms.get(nearest_arch) or {}).get(
            "position")) if nearest_arch else None
        section_pos = 0.0 if n <= 1 else i / (n - 1)
        drift = (abs(section_pos - authored_pos)
                 if authored_pos is not None else None)

        scored.append({
            "sid": sid, "title": title, "job": job, "position": pos_label,
            "arch_cos": arch_cos, "spine_cos": spine_cos,
            "nearest_arch_row": nearest_arch, "nearest_spine_row": nearest_spine,
            "position_drift": None if drift is None else round(drift, 3),
            "arch_env": arch_env, "spine_env": spine_env,
            "arch_note": arch_note, "spine_note": spine_note,
        })

    # the plan-relative floors, computed over the scored sections only.
    arch_floor = _floor([r["arch_cos"] for r in scored if r["arch_cos"] is not None])
    spine_floor = _floor([r["spine_cos"] for r in scored if r["spine_cos"] is not None])

    # PASS 2 — conjecture candidates + build packets for the below-floor sections.
    packets: list[dict] = []
    conformant: list[dict] = []
    unscored: list[dict] = []
    for r in scored:
        if r["arch_cos"] is None:                # store dial-off / refused → cannot score
            unscored.append({"section": r["sid"], "reason": r["arch_note"]})
            continue
        verb = _conjecture_verb(
            r["arch_cos"], r["spine_cos"] if r["spine_cos"] is not None else 1.0,
            arch_floor, spine_floor, r["position_drift"])
        if verb is None:
            conformant.append({"section": r["sid"], "arch_cos": r["arch_cos"],
                               "spine_cos": r["spine_cos"]})
            continue

        proposed_op = _proposed_op(verb)
        candidate = {
            "verb": verb,
            "object_kind": "section",
            "object_key": r["sid"],
            "proposed_op": proposed_op,
            "provenance": "conjectured",
            "signal": {
                "arch_cos": r["arch_cos"], "spine_cos": r["spine_cos"],
                "arch_floor": None if arch_floor is None else round(arch_floor, 3),
                "spine_floor": None if spine_floor is None else round(spine_floor, 3),
                "position_drift": r["position_drift"],
                "nearest_arch_row": r["nearest_arch_row"],
                "nearest_spine_row": r["nearest_spine_row"],
            },
            "rationale": _rationale(verb, r, arch_floor, spine_floor),
        }
        question = (
            f"STRUCTURAL CONFORMANCE — section {r['sid']!r} ({r['title']!r}, "
            f"{r['position']}) conforms LEAST to the author's published section "
            f"architecture (cos {r['arch_cos']} < floor "
            f"{None if arch_floor is None else round(arch_floor, 3)}). Rule ONE of "
            f"KEEP (it is genuinely his shape), or a structural op — "
            f"RESPINE/REORDER/DEMOTE/SPLIT/CUT — weighing the retrieved authored "
            f"section-architectures and ladder-moves as evidence. The conjectured "
            f"candidate is {verb} (a prior from the conformance distance, not a "
            f"verdict); override it freely."
        )
        packets.append({
            "section": {"id": r["sid"], "title": r["title"], "job": r["job"],
                        "position": r["position"]},
            "candidate": candidate,
            "question": question,
            "evidence": {
                _ARCH_STORE: r["arch_env"] if r["arch_env"] else r["arch_note"],
                _SPINE_STORE: r["spine_env"] if r["spine_env"] else r["spine_note"],
            },
            "bank": STRUCTURAL_BANK_CONTRACT,
        })

    # the SHARED frame — the fusion organ, hoisted ONCE (its third input, the
    # FORM-EXEMPLARS envelope, IS this pass's structural evidence at manifest level).
    manifest_question = (
        f"STRUCTURAL CONFORMANCE for {corpus!r}: for each flagged section below, does "
        f"the author RESPINE / REORDER / DEMOTE / SPLIT / CUT it, or KEEP it? Rule "
        f"with his published section-architecture and spine-ladder as evidence."
    )
    frame = author_proxy.assemble_decision_frame(
        Path(root), manifest_question, form_k=k, dials=dials)

    manifest = {
        "kind": "structural-conformance",
        "corpus": corpus,
        "schema": 2,
        "count": len(packets),
        "cut_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "frame": frame,
        "bank_contract": STRUCTURAL_BANK_CONTRACT,
        "apply_bridge": APPLY_BRIDGE,
        "packets": packets,
        "conformant": conformant,
        "unscored": unscored,
        "stores": {"section_architecture": store_notes.get(_ARCH_STORE, "unqueried"),
                   "spine_chain": store_notes.get(_SPINE_STORE, "unqueried")},
        "floors": {"arch": None if arch_floor is None else round(arch_floor, 3),
                   "spine": None if spine_floor is None else round(spine_floor, 3),
                   "z": _FLOOR_Z},
        "read_only": True,
        "invocation": None,
    }

    out = _resolve_out_path(corpus, out_path, root)
    if write and out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        manifest["invocation"] = (
            f'/structural-conformance --manifest "{out.name}"')
        out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8")
        manifest["manifest_path"] = str(out)
    elif not write:
        # the dry-run preview: computed, returned, nothing on disk.
        manifest["preview"] = True
    return manifest


def _rationale(verb: str, r: dict, arch_floor: float | None,
               spine_floor: float | None) -> str:
    """One plain line naming the computed signal behind the conjecture."""
    if verb == "RESPINE":
        return (f"below BOTH manifolds (arch {r['arch_cos']}<{arch_floor}, spine "
                f"{r['spine_cos']}<{spine_floor}) — shape unlike any authored section")
    if verb == "REORDER":
        return (f"fits an authored job but at a different arc point "
                f"(position_drift {r['position_drift']} > {_POSITION_DRIFT})")
    return (f"weak arch fit (cos {r['arch_cos']} < floor {arch_floor}) with no clear "
            f"position drift — earns less ladder prominence")


def _resolve_out_path(corpus: str, out_path: str | Path | None,
                      root: str | Path) -> Path | None:
    """The manifest's on-disk home: an explicit ``out_path``, else the project's
    ``<manuscript>/dispatches/structural_conformance_manifest.json`` (where compiled
    dispatches + form sidecars already bank), else ``None`` (return-only). Writing the
    manifest is the deliverable; it is a dispatch artifact, NEVER a ledger."""
    if out_path is not None:
        return Path(out_path)
    try:
        from laplace.pipeline import registry
        proj = registry.resolve(corpus)
    except Exception:
        proj = None
    if proj is None:
        return None
    mdir = getattr(proj, "manuscript_dir", None) or getattr(proj, "tex_root", None)
    if not mdir:
        return None
    return Path(root) / mdir / "dispatches" / _MANIFEST_NAME


# ----------------------------------------------------------- the lawful READER
#: the ONE dispatch artifact this pass banks and the reader reads (the conjugate
#: pair share this name — :func:`build_conformance_manifest` writes it, :func:`read_manifest`
#: reads it; the ``/pipeline`` card never re-parses, it calls the reader).
_MANIFEST_NAME = "structural_conformance_manifest.json"


def _absent_read(mdir: Path) -> dict:
    """The honest-empty read shape — every fact zeroed/empty, ``present`` False, no
    raise. The ``/pipeline`` structural-conformance card renders its absence string
    off this (``no banked run for <project> · fire it below``)."""
    return {
        "present": False,
        "manuscript": str(mdir),
        "corpus": "",
        "cut_at": "",
        "patch_count": 0,
        "verdict": "absent",
        "conformant": 0,
        "unscored": 0,
        "stores": {},
        "stores_fed": [],
    }


def read_manifest(manuscript_dir: str | Path) -> dict:
    """The lawful READER — view=mechanism: the ``/pipeline`` structural-conformance
    card calls THIS, never re-parses the artifact. The conjugate of
    :func:`build_conformance_manifest`: a PURE read (no subprocess, no compile, no
    network, no writes) of the banked manifest at
    ``<manuscript_dir>/dispatches/structural_conformance_manifest.json``.

    Facts returned (present manifest):

    * ``patch_count`` — the candidate structural patches the pass conjectured
      (``len(packets)`` == the manifest's own ``count``);
    * ``verdict`` — the empty-vs-patched call: ``patched`` (one or more candidates)
      vs ``empty-patch`` (a manifest carrying zero candidates — the dial-off inert
      shape :func:`build_conformance_manifest` emits when both stores are off);
    * ``stores`` / ``stores_fed`` — WHICH stores fed the read: ``stores`` is the
      per-store plain note (``served: k=3`` / ``dial-off …`` / ``refused: …``),
      ``stores_fed`` the subset whose note is ``served`` — so the card shows the
      dial/gate truth, never a silent no-op;
    * ``conformant`` / ``unscored`` — sections ruled to conform (no patch) and
      sections that could not be scored (a store was dial-off / refused).

    ``present`` is ALWAYS carried. Absent artifact (or unreadable/malformed/not a
    dict) → :func:`_absent_read` (``present`` False, ``verdict`` ``absent``, every
    count zeroed) — never a raise, never None."""
    mdir = Path(manuscript_dir)
    path = mdir / "dispatches" / _MANIFEST_NAME
    # ONE boom-guard over json.loads AND the whole field extraction (the
    # detector_organs.read_detector_organs exemplar): a valid-JSON-but-wrong-typed
    # manifest (e.g. ``packets`` an int, ``stores`` a list) must degrade to
    # _absent_read, never raise a 500 on this GET path.
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            return _absent_read(mdir)
        packets = manifest.get("packets") or []
        patch_count = len(packets)
        stores = {str(k): str(v) for k, v in (manifest.get("stores") or {}).items()}
        stores_fed = [name for name, note in stores.items() if note.startswith("served")]
        return {
            "present": True,
            "manuscript": str(mdir),
            "corpus": str(manifest.get("corpus") or ""),
            "cut_at": str(manifest.get("cut_at") or ""),
            "patch_count": patch_count,
            "verdict": "patched" if patch_count else "empty-patch",
            "conformant": len(manifest.get("conformant") or []),
            "unscored": len(manifest.get("unscored") or []),
            "stores": stores,
            "stores_fed": stores_fed,
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return _absent_read(mdir)


if __name__ == "__main__":  # pragma: no cover
    import argparse
    ap = argparse.ArgumentParser(
        description="the structural-conformance read leg — retrieve the authored "
                    "manifolds, conjecture candidate patches, emit the dispatch manifest")
    ap.add_argument("corpus", help="the conceptric/project name")
    ap.add_argument("--k", type=int, default=3, help="exemplars per store (default 3)")
    ap.add_argument("--root", default=".", help="repo root (default .)")
    ap.add_argument("--out", default=None,
                    help="explicit manifest out-path (default the project's dispatches/)")
    ap.add_argument("--preview", action="store_true",
                    help="dry-run: compute + print the manifest, write NOTHING (write=False)")
    a = ap.parse_args()
    man = build_conformance_manifest(a.corpus, k=a.k, root=a.root, out_path=a.out,
                                     write=not a.preview)
    # print the manifest MINUS the packet bodies (bounded) — the counts + stores + floors
    print(json.dumps({k: v for k, v in man.items() if k not in ("packets", "frame")},
                     indent=1, ensure_ascii=False))
