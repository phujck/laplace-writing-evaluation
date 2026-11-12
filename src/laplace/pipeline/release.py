"""The release bundle, the release state machine, and the figure-freeze layer.

The hardening spine's terminal organ (his review, 2026-07-09). Finalisation
(title/pdftitle checking, slug naming, bib, metadata) creates a NEW artefact, so
the release must be pinned to the *exact bytes* that were judged. This module is
that pin — three cooperating pieces, assertions not a framework:

  * **the bundle** (:func:`build_bundle` / :func:`verify_bundle`) — a manifest of
    content hashes over every byte that a release depends on (the ``*.tex`` source
    tree, the assembled/flattened text, the final PDF, the bibliography, the figure
    assets, the active suppression set) plus the immutable evidence snapshot (the
    plan/dials versions, the gate + judge results). ``verify_bundle`` recomputes
    every *byte-addressable* hash against the CURRENT tree and names any field that
    drifted. **GERARD'S LAW:** nothing may modify source or PDF after the bundle
    passes — any change re-opens the release, and this is how the change is caught.

  * **the state machine** (:func:`transition` / :func:`reopen` / :func:`current_state`)
    — a sidecar ``release/state.json`` enforcing a forward-only lifecycle
    ``STAGED -> ... -> RELEASED`` with the escape hatch ``REOPENED``. It does NOT
    reimplement the acceptance algebra: candidate-lock eligibility is delegated to
    :func:`candidate_lock.lock_eligible` (hard-pass + clean compile + complete
    round). Every state from ``AUTHOR_REVIEWED`` on is *bound to a specific bundle*;
    a transition whose bundle no longer verifies clean RAISES and auto-reopens.

  * **the figure freeze** (:func:`figure_assets` / :func:`set_figure_acceptance` /
    :func:`figure_regen_allowed`) — figures enter the bundle as versioned objects
    with an acceptance state. An accepted/frozen figure is provisionally frozen: a
    *prose* finding NEVER regenerates it, and a *figure-layer* finding regenerates
    only the owning sub-layer (content / composition / data / styling / caption /
    placement), scoped from the finding's ``kind`` via ``schema.KIND_TO_WORK``
    (read-only — this module never edits the contract).

This module is READ-ONLY with respect to the manuscript source: it hashes, it
compiles under a job name, it reports title/pdftitle agreement — it never edits a
``.tex`` byte. Its only writes are release-internal (``release/*.json`` sidecars).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Optional

from laplace.pipeline import candidate_lock, dials as _dials_mod, schema, suppress

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# small hashing / io helpers
# ---------------------------------------------------------------------------

#: directories under a manuscript that are release-INTERNAL, never source: the
#: incumbent snapshot store (``rounds``), this module's own sidecars (``release``),
#: and the banked version-snapshot store (``versions``, W3.2's ``bank_snapshot``
#: writer — its copied ``.tex``/``.bib`` bytes are a snapshot of source, NOT live
#: source). Excluded from every source hash / figure walk so snapshotting an
#: incumbent, writing a bundle, or banking a version never counts as source drift.
_INTERNAL_DIRS = ("rounds", "release", "versions")

#: figure asset file extensions (the rendered object that is frozen, not the
#: tikz/pgf source that produces it).
_FIGURE_EXTS = (".png", ".pdf", ".jpg", ".jpeg", ".svg", ".eps",
                ".gif", ".tif", ".tiff", ".webp")


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _stable_hash(obj: Any) -> str:
    """A hash over a JSON-canonical form (sorted keys, no incidental whitespace)
    — stable across processes and insertion order, so the same logical content
    hashes the same next round."""
    blob = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return _sha256_text(blob)


def _release_dir(manuscript_dir: str | Path) -> Path:
    return Path(manuscript_dir) / "release"


def _is_internal(path: Path, manuscript_dir: Path) -> bool:
    internal = {(manuscript_dir / d).resolve() for d in _INTERNAL_DIRS}
    parents = set(path.resolve().parents)
    return bool(internal & parents)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# the byte-addressable hashes — the drift surface GERARD'S LAW protects
# ---------------------------------------------------------------------------

def _tex_files(manuscript_dir: Path) -> list[Path]:
    """Every source ``*.tex`` under the dir, internal stores excluded, in a stable
    (relative-path-sorted) order."""
    out = [f for f in manuscript_dir.rglob("*.tex")
           if not _is_internal(f, manuscript_dir)]
    return sorted(out, key=lambda p: p.relative_to(manuscript_dir).as_posix())


def _bib_files(manuscript_dir: Path) -> list[Path]:
    out = [f for f in manuscript_dir.rglob("*.bib")
           if not _is_internal(f, manuscript_dir)]
    return sorted(out, key=lambda p: p.relative_to(manuscript_dir).as_posix())


def source_tree_hash(manuscript_dir: str | Path) -> str:
    """A single hash over every source ``*.tex`` under the dir (each file's bytes,
    keyed by its relative path, in stable order). Any edit / add / remove of a
    ``.tex`` byte changes it."""
    md = Path(manuscript_dir)
    items = [(f.relative_to(md).as_posix(), _sha256_file(f)) for f in _tex_files(md)]
    return _stable_hash(items)


def bibliography_hash(manuscript_dir: str | Path) -> str:
    """A hash over every ``*.bib`` under the dir (relative path -> bytes)."""
    md = Path(manuscript_dir)
    items = [(f.relative_to(md).as_posix(), _sha256_file(f)) for f in _bib_files(md)]
    return _stable_hash(items)


def _assembly_target(manuscript_dir: Path) -> Path:
    """What ``graph._gather_manuscript_text`` reads: the root ``main.tex`` (so its
    ``\\input`` tree flattens in reading order) if present, else the dir (the
    sorted-glob fallback for a rootless section set)."""
    main = manuscript_dir / "main.tex"
    return main if main.is_file() else manuscript_dir


def assembled_text(manuscript_dir: str | Path) -> str:
    """The flattened, comment-stripped manuscript text — the SAME assembly every
    verify check reads (``graph._gather_manuscript_text``), never the thin
    ``main.tex`` shell."""
    from laplace.pipeline import graph
    return graph._gather_manuscript_text(_assembly_target(Path(manuscript_dir)))


def final_tex_hash(manuscript_dir: str | Path) -> str:
    return _sha256_text(assembled_text(manuscript_dir))


def suppression_set_version(manuscript_dir: str | Path,
                            feedback_path: str | Path | None = None) -> str:
    """A hash over the ACTIVE suppression records (the calibration solvent's live
    set). Keyed on the load-bearing fields (id / node / kind / fingerprint), so the
    version changes when the active set changes but is stable under a re-read of the
    same ledger. An absent ledger hashes the empty set.

    THE LEDGER LIVES AT ``<md>/feedback/feedback.jsonl`` (WO-20260817-release-feedback-path,
    the thin-systems audit 2026-08-17). This resolver used to say ``<md>/feedback.jsonl`` —
    one level short of where every writer and every other reader in the engine puts it
    (evolution_consumer._feedback_ledger, desk, the surfaces, pool_fold). So for every real
    manuscript the ledger was simply never found: this returned the EMPTY-SET hash, and the
    release bundle's suppression drift detector was structurally blind — it could never
    report drift because it had never seen a suppression. Resolved through the one shared
    resolver rather than restating the path a fifteenth time."""
    from laplace.pipeline.evolution_consumer import _feedback_ledger
    md = Path(manuscript_dir)
    fp = Path(feedback_path) if feedback_path else _feedback_ledger(md)
    if not fp.is_file():
        return _stable_hash([])
    active = suppress.load_suppressions(fp)
    keys = sorted(
        (str(r.get("id") or ""), suppress._finding_node(r),
         str(r.get("kind") or ""), suppress._supp_fingerprint(r))
        for r in active)
    return _stable_hash(keys)


def dials_version(dials: dict | None) -> str:
    """``<version>:<content-hash>`` — the dials profile that governed the run. A
    ``None`` dials records the code defaults (today's design), so the bundle always
    names the effective calibration."""
    d = dials if dials is not None else _dials_mod.defaults()
    ver = str(d.get("version", "unknown"))
    return f"{ver}:{_stable_hash(d)[:16]}"


# ---------------------------------------------------------------------------
# figure versioned objects + the freeze
# ---------------------------------------------------------------------------

#: the figure sub-layers a scoped regeneration can target (his hardening: a figure
#: finding names ONE owning sub-layer; regeneration is confined to it).
FIGURE_SUBLAYERS = ("content", "composition", "data", "styling", "caption",
                    "placement")

#: substring -> sub-layer, first hit wins. DERIVED BY NAME from the figure-layer
#: kinds in ``schema.KIND_TO_WORK`` (the kinds whose work-kind is ``figure``):
#: ``caption-*`` / ``table-uncaptioned`` -> caption; ``figure-not-singular`` ->
#: composition; ``figure-debris`` / ``figure-standard`` -> styling; the data and
#: placement vocabulary is reserved for kinds that name them. Anything else that
#: still routes to the figure layer (``figure-regenerate``) is whole-figure
#: ``content``.
_SUBLAYER_RULES: tuple[tuple[str, str], ...] = (
    ("caption", "caption"),
    ("data", "data"),
    ("singular", "composition"),
    ("composit", "composition"),
    ("panel", "composition"),
    ("placement", "placement"),
    ("misplac", "placement"),
    ("debris", "styling"),
    ("standard", "styling"),
    ("styl", "styling"),
)

#: acceptance states a figure asset may carry.
FIGURE_STATES = ("draft", "accepted", "frozen")


def _figures_sidecar_path(manuscript_dir: str | Path) -> Path:
    return _release_dir(manuscript_dir) / "figures.json"


def _load_figures_sidecar(manuscript_dir: str | Path) -> dict:
    p = _figures_sidecar_path(manuscript_dir)
    if not p.is_file():
        return {"figures": {}}
    data = _read_json(p)
    data.setdefault("figures", {})
    return data


def _figure_dirs(manuscript_dir: Path) -> list[Path]:
    """Every directory named ``figures`` (case-insensitive) under the manuscript,
    internal stores excluded."""
    out = [d for d in manuscript_dir.rglob("*")
           if d.is_dir() and d.name.lower() == "figures"
           and not _is_internal(d, manuscript_dir)]
    return sorted(out, key=lambda p: p.relative_to(manuscript_dir).as_posix())


def _walk_figure_files(manuscript_dir: Path) -> list[Path]:
    files: list[Path] = []
    for d in _figure_dirs(manuscript_dir):
        for f in d.rglob("*"):
            if f.is_file() and f.suffix.lower() in _FIGURE_EXTS:
                files.append(f)
    return sorted(files, key=lambda p: p.relative_to(manuscript_dir).as_posix())


def _figure_meta(sidecar: dict, rel: str, stem: str) -> dict:
    """The ``{spec_id?, acceptance}`` for an asset, joined from the sidecar by its
    relative path OR (fallback) its filename stem read as a spec id. Absent -> a
    draft with no spec."""
    figs = sidecar.get("figures", {})
    for key in (rel, stem):
        if key in figs:
            m = figs[key]
            return {"spec_id": m.get("spec_id", key if key == stem else None),
                    "acceptance": m.get("acceptance", "draft")}
    return {"spec_id": None, "acceptance": "draft"}


def figure_assets(manuscript_dir: str | Path) -> list[dict]:
    """The bundle's figure list: every rendered asset under a ``figures`` dir,
    hashed, joined with its ``spec_id`` / ``acceptance`` from the
    ``release/figures.json`` sidecar. Stable order. Each entry is
    ``{path, sha256, spec_id?, acceptance}``."""
    md = Path(manuscript_dir)
    sidecar = _load_figures_sidecar(md)
    out: list[dict] = []
    for f in _walk_figure_files(md):
        rel = f.relative_to(md).as_posix()
        meta = _figure_meta(sidecar, rel, f.stem)
        entry = {"path": rel, "sha256": _sha256_file(f),
                 "acceptance": meta["acceptance"]}
        if meta["spec_id"]:
            entry["spec_id"] = meta["spec_id"]
        out.append(entry)
    return out


def set_figure_acceptance(manuscript_dir: str | Path, asset_or_spec: str,
                          state: str) -> dict:
    """Set the acceptance ``state`` (draft / accepted / frozen) for an asset —
    named by its relative path, absolute path, basename, or spec id. Writes the
    ``release/figures.json`` sidecar and returns the stored record. Raises on an
    unknown state."""
    if state not in FIGURE_STATES:
        raise ValueError(f"unknown figure state {state!r}; known: {FIGURE_STATES}")
    md = Path(manuscript_dir)
    sidecar = _load_figures_sidecar(md)
    key = _acceptance_key(md, asset_or_spec, sidecar)
    rec = sidecar["figures"].get(key, {})
    rec["acceptance"] = state
    rec.setdefault("spec_id", key)
    rec["updated"] = _now()
    sidecar["figures"][key] = rec
    _write_json(_figures_sidecar_path(md), sidecar)
    return {"key": key, **rec}


def _acceptance_key(manuscript_dir: Path, asset_or_spec: str,
                    sidecar: dict) -> str:
    """Normalise an asset/spec identifier to the sidecar key: prefer an existing
    key match (relative path, basename, or stem); else the manuscript-relative path
    if the identifier resolves to a file; else the identifier verbatim (a spec id)."""
    figs = sidecar.get("figures", {})
    ident = str(asset_or_spec)
    # a path we can resolve relative to the manuscript
    p = Path(ident)
    candidates: list[str] = []
    if p.is_absolute():
        try:
            candidates.append(p.resolve().relative_to(manuscript_dir.resolve()).as_posix())
        except ValueError:
            pass
    else:
        candidates.append((manuscript_dir / ident).resolve()
                          .relative_to(manuscript_dir.resolve()).as_posix()
                          if (manuscript_dir / ident).exists() else ident)
    candidates += [ident, Path(ident).name, Path(ident).stem]
    for c in candidates:
        if c in figs:
            return c
    # no existing record: key by the manuscript-relative path if it is a real
    # asset, else by the identifier itself (a spec id).
    rel_guess = candidates[0]
    if (manuscript_dir / rel_guess).is_file():
        return rel_guess
    return ident


def _acceptance_of(manuscript_dir: Path, asset: str, sidecar: dict) -> str:
    """The acceptance state currently recorded for ``asset`` (draft if none)."""
    key = _acceptance_key(manuscript_dir, asset, sidecar)
    rec = sidecar.get("figures", {}).get(key)
    if isinstance(rec, dict) and rec.get("acceptance"):
        return rec["acceptance"]
    return "draft"


def _is_figure_layer_kind(kind: str) -> bool:
    """Whether a finding kind owns the FIGURE layer — i.e. ``schema.KIND_TO_WORK``
    routes it to the ``figure`` work-kind (``WORK_TO_LAYER['figure'] == 'figures'``).
    A prose / structure / render kind that merely mentions 'figure' (e.g.
    ``figure-misplaced`` -> structure, ``figure-oversized`` -> render) is NOT a
    figure-layer kind and cannot regenerate a frozen figure. Read-only: the
    component manifests are folded in first so the routing is complete."""
    schema.register_component_kinds()
    return schema.KIND_TO_WORK.get(kind) == "figure"


def figure_sublayer(kind: str) -> Optional[str]:
    """The owning figure sub-layer for a figure-layer ``kind`` (or ``None`` if the
    kind is not a figure-layer kind). Derived by name from the kind."""
    if not _is_figure_layer_kind(kind):
        return None
    low = kind.lower()
    for needle, sub in _SUBLAYER_RULES:
        if needle in low:
            return sub
    return "content"


def figure_regen_allowed(manuscript_dir: str | Path, asset: str,
                         finding_kind: str) -> tuple[bool, str]:
    """Whether a finding of ``finding_kind`` may regenerate ``asset`` — and, when it
    may, the SCOPE.

    A ``draft`` figure is unrestricted. An ``accepted`` / ``frozen`` figure is
    provisionally frozen:

      * a finding whose kind is NOT a figure-layer kind (any prose / structure /
        render / projection finding) returns ``(False, reason)`` — a prose finding
        never regenerates a figure;
      * a figure-layer kind returns ``(True, reason)`` with the reason naming the
        single owning sub-layer, so regeneration is scoped to it.
    """
    md = Path(manuscript_dir)
    sidecar = _load_figures_sidecar(md)
    state = _acceptance_of(md, asset, sidecar)
    if state == "draft":
        return True, f"figure is draft ({finding_kind!r}); regeneration unrestricted"
    sub = figure_sublayer(finding_kind)
    if sub is None:
        return (False,
                f"figure is {state}; {finding_kind!r} is not a figure-layer kind "
                f"(a non-figure finding never regenerates a frozen figure)")
    return (True,
            f"figure is {state}; {finding_kind!r} regenerates only the {sub!r} "
            f"sub-layer (scoped)")


# ---------------------------------------------------------------------------
# the release bundle
# ---------------------------------------------------------------------------

#: the bundle fields recomputed against current bytes by ``verify_bundle`` (the
#: drift surface). The rest (dials/gate/judge/plan-evidence, created) is the
#: IMMUTABLE evidence snapshot — provenance, not re-derivable from tree bytes.
_DRIFT_FIELDS = ("source_tree_hash", "final_tex_hash", "final_pdf_hash",
                 "bibliography_hash", "suppression_set_version", "figure_assets")


def _finalize_record(manuscript_dir: Path) -> Optional[dict]:
    p = _release_dir(manuscript_dir) / "finalize.json"
    return _read_json(p) if p.is_file() else None


def _discover_final_pdf(manuscript_dir: Path) -> Optional[str]:
    """The manuscript-relative path of the final PDF: the one ``finalize`` recorded,
    else the slug PDF for the resolved title, else ``main.pdf``, else the sole
    top-level PDF. ``None`` if there is no PDF to bind."""
    rec = _finalize_record(manuscript_dir)
    if rec and rec.get("pdf_path"):
        cand = manuscript_dir / rec["pdf_path"]
        if cand.is_file():
            return rec["pdf_path"]
    # slug PDF for the resolved title (deterministic, matches finalize's naming)
    try:
        title = _resolve_title(manuscript_dir, None, None)
        slug = _slugify(title)
        if (manuscript_dir / f"{slug}.pdf").is_file():
            return f"{slug}.pdf"
    except Exception:
        pass
    if (manuscript_dir / "main.pdf").is_file():
        return "main.pdf"
    top_pdfs = sorted(p for p in manuscript_dir.glob("*.pdf"))
    if len(top_pdfs) == 1:
        return top_pdfs[0].name
    return None


# ---------------------------------------------------------------------------
# the FINISHED-ARTEFACT resolver (WO-20260820-r10-binds-the-wrong-pdf)
#
# :func:`_discover_final_pdf` above answers "which PDF does THIS directory
# resolve to" and is the release machine's own binding (build_bundle's drift
# surface, the snapshot's frozen artefact, the layout gates). It is deliberately
# left byte-identical here: its four callers all mean the manuscript dir's own
# compiled object, and none of them holds a plan.
#
# The WHOLE-ARTEFACT READER means something else: the object the PROJECT ships.
# For a project whose plan declares ``meta.target_dir`` those are different
# directories, and the manuscript dir's "sole top-level PDF" fall-through then
# certifies whatever audit sheet happens to sit there. That is not hypothetical:
# on SSG it bound ``FIGURE_REVIEW.pdf`` — a figure-review audit — as the finished
# whitepaper, so every R10 run on that project judged an artefact that was never
# the paper. Hence a SECOND, plan-aware resolver rather than a mutation of the
# shared one.
# ---------------------------------------------------------------------------

#: PDF names that mark an AUDIT SURFACE over a manuscript — a figure review, a
#: judge-round dump, a calibration sheet — never the finished artefact. Matched on
#: the file NAME only, and consulted only on the GUESSED rung of the ladder (the
#: sole-top-level fall-through). A finalize record, the slug PDF and ``main.pdf``
#: are AUTHORED bindings and are never second-guessed by a name pattern.
_AUDIT_PDF_RX = re.compile(
    r"figure[ _-]?review|judge[ _-]?round|calibration|figure[ _-]?audit",
    re.IGNORECASE)

#: the committed home of a project's plan, beside the manuscript (the path the R10
#: arm's compare step already opens).
PLAN_BASENAME = "projection_plan.json"


def is_audit_pdf(name: str | Path) -> bool:
    """True when a PDF's NAME marks it an audit surface (figure review, judge
    rounds, calibration) rather than the finished artefact."""
    return bool(_AUDIT_PDF_RX.search(Path(str(name)).name))


def _load_plan(manuscript_dir: Path,
               plan: Any = None) -> tuple[Optional[dict], Optional[str], Optional[str]]:
    """``(plan, plan_path, error)`` for a plan given as a dict, as a path, or not at
    all. With ``plan=None`` the committed convention is consulted —
    ``<manuscript>/projection_plan.json`` — which is where the live R10 arm already
    reads it from. A plan file that exists but does not parse yields ``error`` (never
    a silent None): an unreadable plan means the target dir is UNKNOWN, and an unknown
    target may not fall through to a guess."""
    if isinstance(plan, dict):
        return plan, None, None
    p = Path(plan) if plan is not None else (manuscript_dir / PLAN_BASENAME)
    if not p.is_file():
        if plan is not None:
            return None, None, f"plan {str(p)!r} does not exist"
        return None, None, None
    try:
        return _read_json(p), str(p), None
    except Exception as e:                       # malformed plan: loud, never silent
        return None, str(p), f"plan {str(p)!r} does not parse ({e})"


def resolve_target_dir(manuscript_dir: str | Path, target_dir: Any) -> Optional[Path]:
    """Resolve a plan's declared ``meta.target_dir`` to a real directory.

    The declaration is authored at whatever altitude the author was writing from —
    SSG's plan carries the REPO-relative ``'synthetics papers/subset-sum-itqde/
    manuscript/whitepaper'``, while a plan may equally carry the manuscript-relative
    ``'whitepaper'`` or an absolute path. All three resolve here by trying the
    manuscript dir first and then each ancestor in turn, NEAREST match wins — so the
    resolution needs no repo-root global and works identically under a tmp tree."""
    if not target_dir or not isinstance(target_dir, (str, Path)):
        return None
    td = Path(str(target_dir).strip())
    if not str(td):
        return None
    if td.is_absolute():
        return td if td.is_dir() else None
    md = Path(manuscript_dir).resolve()
    for base in (md, *md.parents):
        cand = base / td
        if cand.is_dir():
            return cand
    return None


def _classify_final_pdf(base: Path, rel: str) -> str:
    """Which rung of :func:`_discover_final_pdf`'s ladder produced ``rel`` —
    ``finalize.json`` / ``slug`` / ``main.pdf`` are AUTHORED bindings;
    ``sole-top-level`` is the guess (the rung that bound SSG's figure review)."""
    rec = _finalize_record(base)
    if rec and rec.get("pdf_path") == rel:
        return "finalize.json"
    if rel == "main.pdf":
        return "main.pdf"
    try:
        if rel == f"{_slugify(_resolve_title(base, None, None))}.pdf":
            return "slug"
    except Exception:
        pass
    return "sole-top-level"


def _bind_in(base: Path) -> tuple[Optional[str], str, Optional[str]]:
    """``(rel, source, refused)`` for one directory: the shared ladder, with the
    GUESSED rung refusing an audit PDF. ``rel`` is relative to ``base``."""
    rel = _discover_final_pdf(base)
    if not rel:
        return None, "none", None
    source = _classify_final_pdf(base, rel)
    if source == "sole-top-level" and is_audit_pdf(rel):
        return None, "refused", rel
    return rel, source, None


def _newest_release_pdf(base: Path) -> Optional[Path]:
    """The newest PDF deposited in ``<base>/release/`` — the LAST rung, for a project
    that ships releases and keeps no finalize record. Ordered by mtime with the name
    as a deterministic tie-break (release names carry dates, not sortable revisions:
    ``r10`` sorts before ``r6``, so the name alone is not an ordering)."""
    rel_dir = _release_dir(base)
    if not rel_dir.is_dir():
        return None
    cands = [p for p in rel_dir.glob("*.pdf") if not is_audit_pdf(p.name)]
    if not cands:
        return None
    return sorted(cands, key=lambda p: (p.stat().st_mtime, p.name))[-1]


def artefact_pdf_binding(manuscript_dir: str | Path, *, plan: Any = None) -> dict:
    """WHICH PDF IS THE FINISHED ARTEFACT — with its provenance, so a reader that
    binds the wrong object can be caught by reading the binding instead of the pages.

    Returns ``{pdf, source, target_dir, plan_path, refused, reason}``. ``pdf`` is
    relative to ``manuscript_dir`` when it lives under it (else absolute), so
    ``manuscript_dir / pdf`` is the file in both cases; ``None`` means NOTHING may
    bind and the caller must fail loudly rather than certify a guess.

    The ladder:

      1. **the plan's ``meta.target_dir``, when it declares one** — the artefact
         resolves THERE and nowhere else: the target dir's own final PDF (the
         finalize record → the slug PDF → ``main.pdf``), else the newest PDF in the
         target dir's ``release/``. If the target dir yields nothing, the answer is
         ``None`` — it is NEVER the manuscript dir's top-level PDF, because that
         fall-through is precisely what bound a figure-review audit as SSG's
         whitepaper.
      2. **no target dir declared** — the manuscript dir's own final PDF, the shared
         :func:`_discover_final_pdf` ladder, with one refusal: an audit-named PDF
         (:func:`is_audit_pdf`) may not bind on the GUESSED rung (the sole top-level
         PDF). An authored binding — a finalize record, the slug, ``main.pdf`` — is
         taken at its word.

    Within a target dir the finalize record outranks the ``release/`` deposit
    deliberately: this reader fires at CANDIDATE LOCK, where the object under
    judgement is the current compiled candidate, not the object released a month ago.
    A stale release PDF binding over a fresh finalize record would be the same defect
    wearing a better name."""
    md = Path(manuscript_dir)
    plan_d, plan_path, plan_err = _load_plan(md, plan)
    out: dict[str, Any] = {"pdf": None, "source": "none", "target_dir": None,
                           "plan_path": plan_path, "refused": None, "reason": None}
    if plan_err:
        out["reason"] = plan_err + " — refusing to bind an artefact by guess"
        return out

    declared = ((plan_d or {}).get("meta") or {}).get("target_dir")
    td = resolve_target_dir(md, declared)
    if declared and td is None:
        out["reason"] = (f"plan declares meta.target_dir {declared!r} and it resolves "
                         f"to no directory under {md} or its parents")
        return out

    if td is not None and td.resolve() != md.resolve():
        out["target_dir"] = str(td)
        rel, source, refused = _bind_in(td)
        pdf = (td / rel) if rel else _newest_release_pdf(td)
        if rel is None and pdf is not None:
            source = "release-dir"
        if pdf is None:
            out["source"] = "none"
            out["refused"] = refused
            out["reason"] = (
                f"target dir {td} holds no bindable artefact PDF"
                + (f" (refused the audit-named {refused!r})" if refused else "")
                + " — the manuscript's own top-level PDF is NOT a fall-through here")
            return out
        out["pdf"] = _rel_to(md, pdf)
        out["source"] = source
        return out

    rel, source, refused = _bind_in(md)
    out["source"] = source
    out["refused"] = refused
    if rel is None:
        out["reason"] = (f"refused the audit-named {refused!r} as the finished artefact"
                         if refused else f"no PDF to bind under {md}")
        return out
    out["pdf"] = rel
    return out


def _rel_to(base: Path, path: Path) -> str:
    """``path`` as a POSIX path relative to ``base`` when it lives under it, else the
    absolute path — either way ``base / result`` IS the file."""
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def discover_artefact_pdf(manuscript_dir: str | Path, *,
                          plan: Any = None) -> Optional[str]:
    """The finished artefact's PDF path (see :func:`artefact_pdf_binding` for the
    ladder and the provenance), or ``None`` when nothing may bind."""
    return artefact_pdf_binding(manuscript_dir, plan=plan)["pdf"]


def _final_pdf_hash(manuscript_dir: Path, rel_pdf: Optional[str]) -> Optional[str]:
    if not rel_pdf:
        return None
    p = manuscript_dir / rel_pdf
    return _sha256_file(p) if p.is_file() else None


def _bundle_revision(manuscript_dir: Path) -> int:
    rel = _release_dir(manuscript_dir)
    best = 0
    if rel.is_dir():
        for f in rel.glob("bundle_r*.json"):
            m = re.match(r"bundle_r(\d+)\.json$", f.name)
            if m:
                best = max(best, int(m.group(1)))
    return best + 1


# ---------------------------------------------------------------------------
# the promise-materialisation leg — the figures organ + the bibliography stage,
# COMPOSED so a pipeline rerun MINTS the promised floats and the References with
# no agent improvising the two extra commands (the infrastructure law: every
# deliverable is a durable pipeline organ, the acceptance test is reproducibility).
#
# This runs BEFORE the converge organ so the mechanical panel (promise_audit's
# promise-figure-absent gate, the bib render check) sees the placed floats and
# the wired \bibliography, and BEFORE build_bundle so the minted bytes are pinned
# by the bundle (GERARD'S LAW: no source change after the bundle passes). Both
# organs are idempotent, so re-entry mints the same tree.
# ---------------------------------------------------------------------------

def _discover_generator_script(manuscript_dir: Path) -> Optional[Path]:
    """The corpus figure generator, by the committed convention: a
    ``*_figures.py`` under the project's sibling ``numerics/`` dir (the layout
    ``figure_runner`` documents, e.g. ``paper_falqon/numerics/falqon_figures.py``
    beside ``paper_falqon/manuscript/``). Deterministic (sorted, first match) so
    discovery never depends on an agent naming the path. ``None`` when a project
    ships no generator — figure materialisation is then a reported no-op, not a
    failure."""
    numerics = manuscript_dir.parent / "numerics"
    if not numerics.is_dir():
        return None
    cands = sorted(numerics.glob("*_figures.py"))
    return cands[0] if cands else None


def materialize_promised_assets(
    manuscript_dir: str | Path, *, generator_script: str | Path | None = None,
    bib_basename: str = "refs", main_stem: str = "main",
    run_generators: bool = True, probe: bool = True,
) -> dict:
    """Run the figures organ and the bibliography stage against the manuscript,
    MINTING every promised float and the References into the tree.

    Composition, not reimplementation: :func:`figure_runner.run` enumerates the
    text's figure promises, runs the corpus generators, places the rendered
    floats at their owning sites, and reconciles the promise-site prose;
    :func:`bibliography_stage.run` wires ``\\bibliography`` and proves the
    References render. ``generator_script`` defaults to the committed-convention
    discovery; pass it explicitly to override. Tolerant like :func:`finalize` — a
    missing generator is reported (``figures.skipped``), never raised, so a
    figureless project still materialises its bibliography.

    Returns ``{ok, figures, bibliography, generator_script, reconciled_sites}``.
    ``ok`` is the composed verdict: the figures leg produced no unmatched
    declared-absence gap AND the bibliography rendered (or the probe was skipped)."""
    from laplace.pipeline import bibliography_stage as _bib
    from laplace.pipeline import figure_runner as _fig

    md = Path(manuscript_dir)
    script = generator_script or _discover_generator_script(md)

    fig_manifest: Optional[dict] = None
    fig_skipped_reason: Optional[str] = None
    if script is not None and Path(script).is_file():
        fig_manifest = _fig.run(md, script, apply=True, run_gen=run_generators)
    else:
        fig_skipped_reason = (
            f"no *_figures.py generator under {md.parent / 'numerics'}"
            if script is None else f"generator {script} is not a file")

    bib_result = _bib.run(md, bib_basename=bib_basename, main_stem=main_stem,
                          apply=True, probe=probe)

    figures_ok = (fig_manifest is None or fig_manifest["unmatched_count"] == 0)
    bib_probe = bib_result.probe or {}
    # renders is None when the probe did not run (probe=False) — not a failure.
    bib_ok = bib_probe.get("renders") is not False
    return {
        "ok": bool(figures_ok and bib_ok),
        "generator_script": str(script) if script else None,
        "figures": (fig_manifest if fig_manifest is not None
                    else {"skipped": fig_skipped_reason}),
        "reconciled_sites": (fig_manifest or {}).get("reconciled_sites", []),
        "bibliography": {
            "cited": bib_result.cited, "resolved": bib_result.resolved,
            "dangling": bib_result.dangling, "wired": bib_result.wired,
            "renders": bib_probe.get("renders"),
            "dangling_intents": len(bib_result.intents),
        },
    }


def build_bundle(manuscript_dir: str | Path, *, plan_path: str | Path | None = None,
                 dials: dict | None = None, gate_results: Any = None,
                 judge_results: Any = None) -> dict:
    """Build the release bundle and write it to ``release/bundle_r<N>.json``.

    The bundle pins every byte a release depends on (the drift surface) plus the
    immutable evidence snapshot. ``plan_path`` (if given) must exist — a named plan
    that has gone missing is loud, not silent. Returns the bundle dict (carrying its
    ``revision`` and ``bundle_path`` for the state machine to bind to)."""
    md = Path(manuscript_dir)
    plan_hash = None
    plan_rel: str | None = None
    if plan_path is not None:
        pp = Path(plan_path)
        if not pp.is_file():
            raise FileNotFoundError(f"plan_path {pp} does not exist (a named plan "
                                    "bound to a bundle must be present)")
        plan_hash = _sha256_file(pp)
        plan_rel = str(plan_path)

    rel_pdf = _discover_final_pdf(md)
    bundle: dict[str, Any] = {
        "revision": _bundle_revision(md),
        "created": _now(),
        # --- the drift surface (recomputed by verify_bundle) ---
        "source_tree_hash": source_tree_hash(md),
        "final_tex_hash": final_tex_hash(md),
        "final_pdf_hash": _final_pdf_hash(md, rel_pdf),
        "final_pdf_path": rel_pdf,
        "bibliography_hash": bibliography_hash(md),
        "suppression_set_version": suppression_set_version(md),
        "figure_assets": figure_assets(md),
        # --- the immutable evidence snapshot (provenance, not re-derived) ---
        "plan_hash": plan_hash,
        "plan_path": plan_rel,
        "dials_version": dials_version(dials),
        "gate_results": gate_results,
        "judge_results": judge_results,
    }
    path = _release_dir(md) / f"bundle_r{bundle['revision']}.json"
    _write_json(path, bundle)
    bundle["bundle_path"] = str(path)
    return bundle


def _recompute_drift_fields(manuscript_dir: Path, bundle: dict) -> dict:
    """Recompute the byte-addressable fields from the CURRENT tree, locating the PDF
    the way the bundle recorded it (so a rename doesn't read as a spurious match)."""
    rel_pdf = bundle.get("final_pdf_path") or _discover_final_pdf(manuscript_dir)
    return {
        "source_tree_hash": source_tree_hash(manuscript_dir),
        "final_tex_hash": final_tex_hash(manuscript_dir),
        "final_pdf_hash": _final_pdf_hash(manuscript_dir, rel_pdf),
        "bibliography_hash": bibliography_hash(manuscript_dir),
        "suppression_set_version": suppression_set_version(manuscript_dir),
        "figure_assets": figure_assets(manuscript_dir),
    }


def _figure_bytes_view(assets: list[dict]) -> list[tuple[str, str]]:
    """The byte-identity view of a figure list: (path, sha256) pairs, sorted. An
    acceptance-state change alone is NOT source drift (GERARD'S LAW protects source
    and PDF bytes); a changed / added / removed asset IS."""
    return sorted((a.get("path", ""), a.get("sha256", "")) for a in (assets or []))


def verify_bundle(manuscript_dir: str | Path, bundle: dict) -> dict:
    """Recompute every byte-addressable hash against the CURRENT tree and report
    drift. Returns ``{clean: bool, drifted: [field, ...]}`` — any field whose
    current value differs from the banked value is named. ``figure_assets`` drifts
    on a changed / added / removed asset (not on an acceptance-metadata change).

    The immutable evidence snapshot (plan/dials versions, gate/judge results) is
    NOT recomputed — it is provenance banked at build time, not a tree byte. The
    optional ``plan_path`` binding IS re-checked when the bundle recorded one."""
    md = Path(manuscript_dir)
    current = _recompute_drift_fields(md, bundle)
    drifted: list[str] = []
    for field in _DRIFT_FIELDS:
        if field == "figure_assets":
            if _figure_bytes_view(current["figure_assets"]) != \
               _figure_bytes_view(bundle.get("figure_assets")):
                drifted.append(field)
        elif current[field] != bundle.get(field):
            drifted.append(field)
    # the plan binding, when the bundle named one, is byte-checkable too.
    if bundle.get("plan_path"):
        pp = Path(bundle["plan_path"])
        cur_plan = _sha256_file(pp) if pp.is_file() else None
        if cur_plan != bundle.get("plan_hash"):
            drifted.append("plan_hash")
    return {"clean": not drifted, "drifted": drifted}


# ---------------------------------------------------------------------------
# the state machine — a sidecar release/state.json, assertions not a framework
# ---------------------------------------------------------------------------

STATES = ("STAGED", "WELDED", "MECHANICALLY_VALID", "UNDER_CONVERGENCE",
          "CANDIDATE_LOCKED", "AUTHOR_REVIEWED", "FINAL_CLEAN_BUILD",
          "FINAL_GATES_PASSED", "AUTHOR_ACCEPTED", "RELEASED")
REOPENED = "REOPENED"

#: the state a reopen sends you back through — you re-converge before you can climb
#: again. Its effective ladder index is one below this, so ``UNDER_CONVERGENCE`` is
#: reachable from ``REOPENED`` while ``WELDED`` and earlier are not.
_REOPEN_RESUME = "UNDER_CONVERGENCE"

#: states from here on are bound to a specific bundle: the transition evidence must
#: carry ``bundle_path``, and that bundle must still ``verify_bundle``-clean.
_BUNDLE_BOUND_FROM = "AUTHOR_REVIEWED"


def _order_index(state: str) -> int:
    if state == REOPENED:
        return STATES.index(_REOPEN_RESUME) - 1
    if state not in STATES:
        raise ValueError(f"unknown state {state!r}; known: {STATES + (REOPENED,)}")
    return STATES.index(state)


def _is_bundle_bound(state: str) -> bool:
    return state in STATES and STATES.index(state) >= STATES.index(_BUNDLE_BOUND_FROM)


def _state_path(manuscript_dir: str | Path) -> Path:
    return _release_dir(manuscript_dir) / "state.json"


def _load_state(manuscript_dir: str | Path) -> dict:
    p = _state_path(manuscript_dir)
    if not p.is_file():
        return {"state": "STAGED", "history": []}
    return _read_json(p)


def current_state(manuscript_dir: str | Path) -> str:
    """The current release state (the sidecar's ``state``; absent -> ``STAGED``)."""
    return _load_state(manuscript_dir).get("state", "STAGED")


def _save_state(manuscript_dir: str | Path, sidecar: dict) -> None:
    _write_json(_state_path(manuscript_dir), sidecar)


def _load_bundle_for(manuscript_dir: Path, evidence: dict) -> tuple[dict, str]:
    bp = (evidence or {}).get("bundle_path")
    if not bp:
        raise ValueError("a bundle-bound transition requires evidence "
                         "{'bundle_path': ...}")
    p = Path(bp)
    if not p.is_file():
        raise FileNotFoundError(f"bundle {p} not found")
    return _read_json(p), str(p)


def transition(manuscript_dir: str | Path, to_state: str, *,
               evidence: dict | None = None, by: str | None = None) -> dict:
    """Advance the release state, enforcing the invariants. Raises ``ValueError`` /
    ``FileNotFoundError`` on any illegal transition; returns the new sidecar on
    success.

    Invariants:

      * **forward-only** along ``STATES`` (``to`` must be strictly later than the
        current state). ``REOPENED`` is not a forward target here — use
        :func:`reopen`.
      * **CANDIDATE_LOCKED** consumes ``candidate_lock.lock_eligible``: evidence must
        carry ``round_eval`` / ``compile_report`` / ``round_complete`` and be
        eligible (hard dims pass AND compile clean AND round complete). The lock
        algebra is NOT reimplemented — it is called.
      * **AUTHOR_REVIEWED and later** bind to a bundle: evidence must carry
        ``bundle_path``, and that bundle must still ``verify_bundle``-clean. A stale
        bundle RAISES and auto-:func:`reopen`\\ s (the byte changed under the
        review — GERARD'S LAW).
      * **RELEASED** additionally requires the state to have reached
        ``FINAL_GATES_PASSED`` and the bundle's ``final_pdf_hash`` to still match.

    ``by`` is the actor threaded to the ruled Fork-7 snapshot bank fired at the
    AUTHOR_REVIEWED gate. It is passed straight to :func:`bank_snapshot` (no default
    is invented): a missing actor is refused at the door and surfaced LOUDLY on the
    history row without corrupting the advance (see :func:`_bank_gate_snapshot`).
    """
    md = Path(manuscript_dir)
    evidence = evidence or {}
    if to_state == REOPENED:
        raise ValueError("transition() does not target REOPENED; call reopen(dir, reason)")
    if to_state not in STATES:
        raise ValueError(f"unknown target state {to_state!r}; known: {STATES}")

    sidecar = _load_state(md)
    cur = sidecar.get("state", "STAGED")
    if _order_index(to_state) <= _order_index(cur):
        raise ValueError(f"illegal transition {cur} -> {to_state}: forward-only "
                         f"(a release never slides backward; reopen() is the only escape)")

    # --- per-state preconditions ------------------------------------------------
    bound_bundle_path: str | None = None
    if to_state == "CANDIDATE_LOCKED":
        for k in ("round_eval", "compile_report", "round_complete"):
            if k not in evidence:
                raise ValueError(f"CANDIDATE_LOCKED requires evidence {k!r} "
                                 "(round_eval, compile_report, round_complete)")
        eligible, reasons = candidate_lock.lock_eligible(
            evidence["round_eval"], evidence["compile_report"],
            bool(evidence["round_complete"]))
        if not eligible:
            raise ValueError("CANDIDATE_LOCKED not eligible: " + "; ".join(reasons))

    if _is_bundle_bound(to_state):
        bundle, bound_bundle_path = _load_bundle_for(md, evidence)
        res = verify_bundle(md, bundle)
        if not res["clean"]:
            # the artefact changed under the review — reopen and refuse.
            reopen(md, f"bundle drift on {to_state}: {', '.join(res['drifted'])}")
            raise ValueError(
                f"{to_state} bundle no longer clean (drifted: "
                f"{', '.join(res['drifted'])}) — release REOPENED")
        if to_state == "RELEASED":
            if _order_index(cur) < STATES.index("FINAL_GATES_PASSED"):
                raise ValueError("RELEASED requires FINAL_GATES_PASSED first "
                                 f"(current {cur})")
            if not bundle.get("final_pdf_hash"):
                raise ValueError("RELEASED requires a final_pdf_hash in the bundle")

    # --- commit -----------------------------------------------------------------
    entry = {"from": cur, "to": to_state, "ts": _now()}
    if bound_bundle_path:
        entry["bundle_path"] = bound_bundle_path
        sidecar["bundle_path"] = bound_bundle_path
    if evidence.get("note"):
        entry["note"] = evidence["note"]
    sidecar["state"] = to_state
    sidecar["updated"] = entry["ts"]
    sidecar.setdefault("history", []).append(entry)
    # Fork-7 ruled firing point: the AUTHOR_REVIEWED review gate banks a version
    # snapshot of the reviewed source (labelled for the gate). LOUD-but-not-corrupting
    # — the bank rides on `entry` (persisted with this one _save_state below), so a
    # bank failure records on the history row yet never undoes the committed advance.
    if to_state == "AUTHOR_REVIEWED":
        _bank_gate_snapshot(md, "AUTHOR_REVIEWED", by=by, sink=entry)
    _save_state(md, sidecar)
    return sidecar


def ensure_at_least(manuscript_dir: str | Path, to_state: str, *,
                    evidence: dict | None = None) -> dict:
    """Re-entry-aware advance: ``transition`` when the sidecar is BEHIND
    ``to_state``, a no-op when it is already at or past it. The chain's entry
    legs re-assert their stage on every invocation; a resumed run must not read
    that as a backward slide (H bite 3: tex-mode re-entry on a sidecar at
    UNDER_CONVERGENCE failed 'illegal UNDER_CONVERGENCE -> WELDED'). Never
    moves backward; REOPENED still requires the explicit ``reopen()``."""
    cur = current_state(manuscript_dir)
    order = {s: i for i, s in enumerate(STATES)}
    if cur == REOPENED or (cur in order and to_state in order
                           and order[cur] >= order[to_state]):
        return {"state": cur, "advanced": False}
    side = transition(manuscript_dir, to_state, evidence=evidence)
    return {"state": side.get("state", to_state), "advanced": True}


def reopen(manuscript_dir: str | Path, reason: str) -> dict:
    """Reopen a release (the escape hatch), stamping provenance. Reachable from any
    state at or after ``CANDIDATE_LOCKED`` (before a candidate is locked there is
    nothing to reopen). Sets the state to ``REOPENED`` recording the prior state and
    the reason; from there the ladder resumes at ``UNDER_CONVERGENCE``."""
    md = Path(manuscript_dir)
    sidecar = _load_state(md)
    cur = sidecar.get("state", "STAGED")
    if cur != REOPENED and _order_index(cur) < STATES.index("CANDIDATE_LOCKED"):
        raise ValueError(f"cannot reopen from {cur}: nothing is locked yet "
                         "(reopen is reachable only from CANDIDATE_LOCKED onward)")
    entry = {"from": cur, "to": REOPENED, "ts": _now(), "reason": reason}
    sidecar["state"] = REOPENED
    sidecar["updated"] = entry["ts"]
    sidecar["reopened"] = {"prior_state": cur, "reason": reason, "ts": entry["ts"]}
    sidecar.setdefault("history", []).append(entry)
    _save_state(md, sidecar)
    return sidecar


# ---------------------------------------------------------------------------
# finalize — the naming contract, read-only w.r.t. the source
# ---------------------------------------------------------------------------

#: title-bearing macros, in preference order. ``\title`` is the contract macro;
#: ``\eigentitle`` is the house wordmark macro the Laplace manuscripts actually use
#: (so finalize resolves a real manuscript's title, not just a textbook one).
_TITLE_MACROS = ("title", "eigentitle")

#: a resolved title equal (case-insensitively) to one of these is UNTITLED — an
#: untitled compile fails front-matter (his contract).
_UNTITLED = {"", "main", "untitled", "untitled document", "document", "title",
             "no title", "your title here"}

_PDFTITLE_BRACE_RE = re.compile(r"pdftitle\s*=\s*\{([^}]*)\}")
_PDFTITLE_BARE_RE = re.compile(r"pdftitle\s*=\s*([^,}\]]+)")


def _preamble(text: str) -> str:
    """Everything before ``\\begin{document}`` (where the hyperref pdftitle lives)."""
    idx = text.find(r"\begin{document}")
    return text if idx < 0 else text[:idx]


def _title_region(text: str) -> str:
    """The region a ``\\title`` macro can legally sit in, spanning BOTH layouts.

    In article class ``\\title`` sits in the preamble; in REVTeX4-2 it sits AFTER
    ``\\begin{document}`` (before ``\\maketitle``). Reading only the preamble
    therefore MISSED a REVTeX title entirely and reported ``title_agrees=False`` on
    a perfectly good manuscript (the bite-zero A false-negative). The title region
    is everything up to ``\\maketitle`` (or the whole text when there is none),
    which contains the title macro in either layout and excludes the body."""
    idx = text.find(r"\maketitle")
    return text if idx < 0 else text[:idx]


def _extract_braced(text: str, macro: str) -> Optional[str]:
    """The balanced-brace argument of ``\\<macro>{...}`` (the first occurrence), or
    ``None``. Brace-aware so a title containing ``{}`` groups is read whole."""
    m = re.search(r"\\" + re.escape(macro) + r"\s*\{", text)
    if not m:
        return None
    i = m.end() - 1  # at the '{'
    depth = 0
    for j in range(i, len(text)):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j]
    return None


def _norm_title(s: str) -> str:
    """Collapse whitespace / line breaks for comparison and untitled-detection —
    NOT for storage (the stored title keeps its own casing/markup)."""
    s = re.sub(r"\\\\", " ", s)          # LaTeX line break
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _extract_doc_title(text: str) -> tuple[Optional[str], Optional[str]]:
    """The document's title and the macro that carried it, read from the title
    region (before ``\\maketitle``) so a REVTeX4-2 ``\\title`` placed AFTER
    ``\\begin{document}`` is found, not only an article-class preamble title."""
    region = _title_region(text)
    for macro in _TITLE_MACROS:
        val = _extract_braced(region, macro)
        if val is not None:
            return _norm_title(val), macro
    return None, None


def _extract_pdftitle(text: str) -> Optional[str]:
    pre = _preamble(text)
    m = _PDFTITLE_BRACE_RE.search(pre) or _PDFTITLE_BARE_RE.search(pre)
    return _norm_title(m.group(1)) if m else None


def _plan_spec_title(manuscript_dir: Path) -> Optional[str]:
    """A working title from a plan / projection-spec global record, if one is
    discoverable in the manuscript dir. Checks the conventional sidecars for a
    top-level / global ``title``."""
    for name in ("projection_plan.json", "plan.json", "projection_spec.json",
                 "spec.json"):
        p = manuscript_dir / name
        if not p.is_file():
            continue
        try:
            data = _read_json(p)
        except (OSError, ValueError):
            continue
        for path in (("title",), ("global", "title"), ("record", "title"),
                     ("spec", "title"), ("manuscript", "title")):
            node: Any = data
            for k in path:
                node = node.get(k) if isinstance(node, dict) else None
            if isinstance(node, str) and node.strip():
                return _norm_title(node)
    return None


def _is_untitled(title: Optional[str]) -> bool:
    if not title:
        return True
    t = title.strip().lower()
    return t in _UNTITLED or not _slugify(title)


def _resolve_title(manuscript_dir: str | Path, expect_title: Optional[str],
                   assembled: Optional[str]) -> str:
    """Resolve the working title: ``expect_title``, else a plan/spec global record,
    else the document's ``\\title``/``\\eigentitle``. Raises ``ValueError`` (route:
    front-matter) if the result is absent / empty / 'main' / untitled."""
    md = Path(manuscript_dir)
    if expect_title and expect_title.strip():
        title = _norm_title(expect_title)
    else:
        title = _plan_spec_title(md)
        if not title:
            text = assembled if assembled is not None else assembled_text(md)
            title, _ = _extract_doc_title(text)
    if _is_untitled(title):
        raise ValueError(
            f"front-matter: the manuscript has no usable title (resolved {title!r}). "
            "An untitled compile fails front-matter — route to the document/front-"
            "matter layer. Supply expect_title, a plan/spec title, or a real "
            r"\title{}/\eigentitle{}.")
    return title  # type: ignore[return-value]


_HYPER_SUBJECT_RE = re.compile(r"pdfsubject\s*=\s*\{([^}]*)\}")
_HYPER_KEYWORDS_RE = re.compile(r"pdfkeywords\s*=\s*\{([^}]*)\}")


def _extract_hyper_metadata(text: str) -> tuple[Optional[str], Optional[str]]:
    """The manuscript's BASE ``pdfsubject`` / ``pdfkeywords`` from its preamble
    ``\\hypersetup`` — the meaningful research values the author wrote. ``None`` for
    a field the manuscript does not declare."""
    pre = _preamble(text)
    s = _HYPER_SUBJECT_RE.search(pre)
    k = _HYPER_KEYWORDS_RE.search(pre)
    return (s.group(1).strip() if s else None,
            k.group(1).strip() if k else None)


def _metadata_values(slug: str, revision: int,
                     base_subject: Optional[str] = None,
                     base_keywords: Optional[str] = None) -> tuple[str, str]:
    """The finalize-time ``pdfsubject`` / ``pdfkeywords`` values: the slug + revision
    stamp APPENDED to the manuscript's base values, never REPLACING them (the
    reviewer, 2026-07-10: a filename-like slug must not clobber the author's
    meaningful research subject/keywords). With no base value the stamp stands
    alone (a manuscript that declares none)."""
    tail_subject = f"{slug} revision {revision}"
    tail_keywords = f"{slug}, r{revision}"
    subject = (f"{base_subject.rstrip(' .;-')} - {tail_subject}"
               if base_subject else tail_subject)
    keywords = (f"{base_keywords.rstrip(' ,;')}, {tail_keywords}"
                if base_keywords else tail_keywords)
    return subject, keywords


def _metadata_pretex(slug: str, revision: int,
                     base_subject: Optional[str] = None,
                     base_keywords: Optional[str] = None) -> str:
    """The latexmk ``-usepretex`` code that STAMPS the PDF's ``pdfsubject`` /
    ``pdfkeywords`` at finalize time (the metadata law: a shipped artefact is NAMED
    and METADATA-STAMPED) — APPENDING the slug + revision to the manuscript's base
    values (:func:`_metadata_values`), so the author's meaningful subject/keywords
    survive and the version stamp is added, not substituted.

    Deferred via ``\\AtBeginDocument`` so it runs AFTER hyperref loads — it therefore
    stamps the produced PDF without editing a single ``.tex`` byte (this module stays
    read-only w.r.t. the source; the stamp lands on the PDF, not the manuscript)."""
    subject, keywords = _metadata_values(slug, revision, base_subject, base_keywords)
    return (r"\AtBeginDocument{\hypersetup{pdfsubject={" + subject
            + r"},pdfkeywords={" + keywords + r"}}}")


def _slugify(title: str) -> str:
    """A filesystem slug from a title: strip math / macros / braces, lowercase,
    non-alphanumerics to single hyphens, trimmed, length-capped."""
    s = re.sub(r"\$[^$]*\$", " ", title)          # inline math
    s = re.sub(r"\\[a-zA-Z]+\*?", " ", s)          # macros
    s = re.sub(r"[{}\\]", " ", s)                  # stray braces/backslashes
    s = re.sub(r"[^A-Za-z0-9]+", "-", s.lower())
    return re.sub(r"-+", "-", s).strip("-")[:80]


def _parse_compile_log(log_text: str) -> dict:
    """A compile report SHAPED for ``candidate_lock.lock_eligible`` (keys
    ``errors`` / ``undefined_refs`` / ``undefined_cites`` are its error keys;
    ``overfull`` is deliberately a soft floor, not an error). Reuses
    ``tex_template.lint_typography`` for the categorised counts and adds fatal
    ``!`` errors and rerun signals."""
    from laplace.pipeline import tex_template
    lint = tex_template.lint_typography(log_text)
    counts = lint.get("counts", {})
    fatal = len(re.findall(r"(?m)^!\s", log_text))
    return {
        "errors": fatal,
        "undefined_refs": counts.get("undefined_reference", 0),
        "undefined_cites": counts.get("undefined_citation", 0),
        "overfull": counts.get("overfull_hbox", 0) + counts.get("overfull_vbox", 0),
        "underfull": counts.get("underfull_hbox", 0) + counts.get("underfull_vbox", 0),
    }


def finalize(manuscript_dir: str | Path, *, slug: str | None = None,
             expect_title: str | None = None, by: str | None = None) -> dict:
    """The naming contract: resolve the working title, verify the document's
    ``\\title`` / hyperref ``pdftitle`` agree with it (REPORT, never edit), and run
    the full multi-pass compile under a title-slug job name so the shipped artefact
    is a NAMED object, not a nameless ``main.pdf``.

    Read-only w.r.t. the source. Returns ``{pdf_path, title, slug, compile_report,
    title_check, snapshot?/snapshot_error?}``. Raises ``ValueError`` (front-matter
    route) on an untitled manuscript BEFORE spending a compile. Writes
    ``release/finalize.json`` so ``build_bundle`` can bind the exact PDF it produced.

    ``by`` is the actor threaded to the ruled Fork-7 release snapshot bank; it is
    passed straight to :func:`bank_snapshot` (no default invented), and a bank
    failure is surfaced LOUDLY on the result without corrupting finalize."""
    md = Path(manuscript_dir)
    main = md / "main.tex"
    if not main.is_file():
        raise FileNotFoundError(f"no main.tex in {md} to finalize")
    assembled = assembled_text(md)

    title = _resolve_title(md, expect_title, assembled)      # raises loud if untitled
    the_slug = slug or _slugify(title)
    if not the_slug:
        raise ValueError(f"title {title!r} slugifies to empty — cannot name the PDF")

    # title / pdftitle agreement — reported, never edited.
    doc_title, title_macro = _extract_doc_title(assembled)
    pdftitle = _extract_pdftitle(assembled)
    norm = _norm_title(title)
    title_check = {
        "resolved_title": title,
        "title_macro": title_macro,
        "title_macro_value": doc_title,
        "pdftitle_value": pdftitle,
        "title_present": doc_title is not None,
        "title_agrees": (doc_title is not None and _norm_title(doc_title) == norm),
        "pdftitle_present": pdftitle is not None,
        "pdftitle_agrees": (pdftitle is not None and _norm_title(pdftitle) == norm),
    }

    # the metadata stamp (the metadata law): pdfsubject/pdfkeywords APPEND the named
    # slug + this finalize's revision to the manuscript's BASE hypersetup values
    # (the author's meaningful research subject/keywords are preserved, never
    # clobbered by a filename slug), injected at compile so the shipped PDF is
    # metadata-stamped without editing the revision-neutral source.
    revision = _bundle_revision(md)
    base_subject, base_keywords = _extract_hyper_metadata(assembled)
    pretex = _metadata_pretex(the_slug, revision, base_subject, base_keywords)
    subject_val, keywords_val = _metadata_values(
        the_slug, revision, base_subject, base_keywords)

    # the full multi-pass compile, WITH bibtex/biber, named by the slug, metadata-stamped.
    cmd = ["latexmk", "-pdf", "-synctex=1", "-interaction=nonstopmode",
           "-bibtex", f"-usepretex={pretex}", f"-jobname={the_slug}", main.name]
    try:
        proc = subprocess.run(cmd, cwd=str(md), capture_output=True,
                              encoding='utf-8', errors='replace', timeout=300)
        returncode = proc.returncode
    except FileNotFoundError as e:  # latexmk absent
        raise RuntimeError("latexmk not found — cannot run the finalize compile") from e
    except subprocess.TimeoutExpired:
        returncode = -1

    log_path = md / f"{the_slug}.log"
    log_text = log_path.read_text(encoding="utf-8", errors="replace") \
        if log_path.is_file() else ""
    pdf_path = md / f"{the_slug}.pdf"
    report = _parse_compile_log(log_text)
    report["returncode"] = returncode
    report["pdf"] = str(pdf_path) if pdf_path.is_file() else None
    report["ok"] = pdf_path.is_file() and report["errors"] == 0
    report["log_tail"] = "\n".join(log_text.splitlines()[-30:])

    result = {
        "pdf_path": f"{the_slug}.pdf" if pdf_path.is_file() else None,
        "title": title,
        "slug": the_slug,
        "revision": revision,
        "pdf_subject": subject_val,
        "pdf_keywords": keywords_val,
        "compile_report": report,
        "title_check": title_check,
    }
    # Fork-7 ruled firing point: finalize banks the release snapshot (the named,
    # freshly-compiled artefact + its source, frozen). LOUD-but-not-corrupting — a
    # bank failure records on `result` (and the finalize.json sidecar) but never
    # raises, so finalize's own result always stands (matches finalize's tolerant
    # error idiom: a compile problem is recorded in the report, not raised).
    _bank_gate_snapshot(md, f"release {the_slug}", by=by, sink=result)

    # hand the produced PDF to build_bundle (the pipeline compose seam).
    _write_json(_release_dir(md) / "finalize.json",
                {"pdf_path": result["pdf_path"], "slug": the_slug, "title": title,
                 "revision": revision, "pdf_subject": result["pdf_subject"],
                 "pdf_keywords": result["pdf_keywords"],
                 "title_check": title_check, "created": _now(),
                 "snapshot": result.get("snapshot"),
                 "snapshot_error": result.get("snapshot_error")})
    return result


# ---------------------------------------------------------------------------
# the version-snapshot writer — the ONE door into a project's versions_dir
# (Fork 7 / Q6: bank_snapshot is the single writer; hand-placement retires,
# the audit flips to enforce). The version rail (shared_ui W3.1) READS this
# store; before now nothing WROTE it, so a rail row could only be hand-placed.
# ---------------------------------------------------------------------------

#: the SNAPSHOT.json manifest schema banked in each ``versions/<id>/`` dir. The
#: rail reader (``shared_ui._snapshot_rows``) prefers this manifest's ``ts``; the
#: provenance fields (``id``/``by``/``label``/``project``) make the row legible and
#: attributable, and ``source_tree_hash`` pins the exact source the snapshot froze.
_SNAPSHOT_MANIFEST_FIELDS = ("id", "ts", "by", "label", "project",
                             "source_tree_hash", "files")


def _versions_provenance_path(manuscript_dir: str | Path) -> Path:
    """The release-side ledger of banked version snapshots (``release/snapshots.json``).
    Release-INTERNAL (never a source byte), so it never counts as drift."""
    return _release_dir(manuscript_dir) / "snapshots.json"


def _snapshot_slug(label: str) -> str:
    """A filesystem-safe slug from a snapshot label (for the ``versions/<id>`` dir
    name): lowercase, non-alphanumerics to single hyphens, trimmed, length-capped."""
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(label).lower())
    return re.sub(r"-+", "-", s).strip("-")[:60]


def _snapshot_source_files(manuscript_dir: Path) -> list[tuple[Path, str]]:
    """Every file a version snapshot captures, paired with its manuscript-relative
    path: the source ``*.tex`` fragments and ``*.bib`` files (internal stores —
    rounds/release/versions — excluded, so a snapshot never recurses into a
    snapshot) plus the final PDF the manuscript currently resolves to (the frozen
    artefact). Stable, relative-path order."""
    md = manuscript_dir
    out: list[tuple[Path, str]] = [(f, f.relative_to(md).as_posix())
                                   for f in _tex_files(md)]
    out += [(f, f.relative_to(md).as_posix()) for f in _bib_files(md)]
    rel_pdf = _discover_final_pdf(md)
    if rel_pdf and (md / rel_pdf).is_file():
        out.append((md / rel_pdf, rel_pdf))
    return out


def _append_snapshot_provenance(manuscript_dir: Path, record: dict) -> None:
    """Append EXACTLY ONE provenance row to ``release/snapshots.json`` — the state
    machine's history idiom (load, append, save). One ``bank_snapshot`` call adds
    one row; the store is never rewritten in place."""
    p = _versions_provenance_path(manuscript_dir)
    ledger = _read_json(p) if p.is_file() else {"snapshots": []}
    if not isinstance(ledger.get("snapshots"), list):
        ledger["snapshots"] = []
    ledger["snapshots"].append(record)
    _write_json(p, ledger)


def bank_snapshot(project: str, label: str, *, by: str,
                  repo_root: Path | str | None = None) -> dict:
    """Bank the manuscript's CURRENT state as an immutable snapshot under the
    project's ``versions_dir`` — the one writer into that store (Fork 7 / Q6; the
    hand-placement it replaces retires, and ``audit_silent_failures`` flips from a
    named-gap WARN to enforcing this door). The version rail (``GET /shared/versions``)
    reads what this writes.

    Contract (the FAIL-CLOSED laws):

      * **unregistered project REFUSED** — ``project`` is a registered project NAME;
        an unknown / path-shaped name resolves to ``None`` and RAISES ``ValueError``,
        never a guessed dir (the registry fence).
      * **the actor law** — ``by`` is required and non-empty; a missing / blank actor
        RAISES before a byte is written (no snapshot is banked in nobody's name).
      * **atomic** — the snapshot is assembled in a ``release/``-side ``.tmp-*`` dir
        and ``os.replace``-renamed into ``versions/<id>``. A crash mid-write leaves
        the tmp dir (release-internal, invisible to the rail) and NEVER a partial
        ``versions/<id>/`` the reader would show as a real revision; on any caught
        failure the tmp dir is removed. Exactly one snapshot dir + one provenance
        row are produced.

    Returns the provenance record ``{id, ts, by, label, project, path, files,
    source_tree_hash}``.
    """
    # the actor law FIRST — refuse before any resolution / write.
    if not by or not str(by).strip():
        raise ValueError("bank_snapshot requires a non-empty actor `by` (the actor "
                         "law: no snapshot is banked in nobody's name)")

    from laplace.pipeline import registry  # lazy: registry imports release
    proj = registry.resolve(project) if isinstance(project, str) else None
    if proj is None:
        raise ValueError(f"bank_snapshot refuses unregistered project {project!r} "
                         "(only a registered project has a versions_dir door)")

    root = Path(repo_root) if repo_root is not None else None
    vdir = proj.path(proj.versions_dir, root) if proj.versions_dir else None
    md = proj.path(proj.manuscript_dir, root) if proj.manuscript_dir else None
    if vdir is None or md is None:
        raise ValueError(f"project {project!r} declares no versions_dir / "
                         "manuscript_dir — nothing to snapshot")

    ts = _now()
    snap_id = _dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    slug = _snapshot_slug(label)
    if slug:
        snap_id = f"{snap_id}_{slug}"
    dest = vdir / snap_id
    if dest.exists():
        # a same-second same-label collision would fork the id; refuse rather than
        # overwrite — a banked revision is immutable.
        raise FileExistsError(f"snapshot {snap_id!r} already exists at {dest} "
                              "(a banked revision is immutable)")

    files = _snapshot_source_files(md)
    manifest = {
        "id": snap_id, "ts": ts, "by": str(by), "label": str(label),
        "project": proj.name, "source_tree_hash": source_tree_hash(md),
        "files": [rel for _src, rel in files],
    }

    # atomic build: assemble in a release-internal tmp dir (invisible to the rail),
    # then a single directory rename publishes it. Same filesystem (both under the
    # manuscript dir) so the rename is atomic.
    reldir = _release_dir(md)
    reldir.mkdir(parents=True, exist_ok=True)
    vdir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=f".tmp-snap-{snap_id}-", dir=str(reldir)))
    try:
        for src, rel in files:
            target = tmp / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
        (tmp / "SNAPSHOT.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, dest)   # atomic publish — no partial versions/<id>/ appears
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    record = {**manifest, "path": str(dest)}
    _append_snapshot_provenance(md, record)
    return record


def _registered_project_for(manuscript_dir: str | Path) -> tuple[str | None, Path | None]:
    """Reverse-resolve a manuscript dir to the ``(registered project NAME, repo_root)``
    whose ``manuscript_dir`` resolves back to it — so the ruled Fork-7 firing points
    (:func:`transition` at AUTHOR_REVIEWED, :func:`finalize`) can call the
    registry-fenced :func:`bank_snapshot`, which takes a project NAME, not a dir.

    Returns ``(None, None)`` for a dir that belongs to no registered project (a tmp /
    ad-hoc manuscript has no ``versions_dir`` to bank into). NEVER guesses: a candidate
    is accepted only when the registry resolves the SAME dir back under the derived
    root (mirrors the registry fence :func:`bank_snapshot` itself applies)."""
    from laplace.pipeline import registry
    md = Path(manuscript_dir).resolve()
    for name, proj in registry.all_projects().items():
        rel = proj.manuscript_dir
        if not rel or not proj.versions_dir:
            continue
        rel_parts = Path(rel).parts
        n = len(rel_parts)
        if n == 0 or len(md.parts) < n or md.parts[-n:] != rel_parts:
            continue
        root = Path(*md.parts[:-n]) if len(md.parts) > n else Path(md.anchor)
        resolved = proj.path(rel, root)
        if resolved is not None and resolved.resolve() == md:
            return name, root
    return None, None


def _bank_gate_snapshot(manuscript_dir: str | Path, label: str, *,
                        by: str | None, sink: dict) -> None:
    """Bank the ruled Fork-7 version snapshot at a firing point (the AUTHOR_REVIEWED
    transition; :func:`finalize`) and record the OUTCOME on ``sink`` (a state-machine
    history entry, or the finalize result dict).

    LOUD but NON-CORRUPTING (the ruled failure posture): a bank failure — the door's
    own actor / registry refusal, a same-second id collision, or an atomic-write
    error — is logged at ERROR and recorded as ``sink['snapshot_error']``; it NEVER
    raises, so the transition / finalize it rides on always completes and persists.
    :func:`bank_snapshot` is itself fail-closed and atomic, so a failure leaves no
    partial snapshot behind. On success the banked id is recorded as ``sink['snapshot']``.
    No default actor is invented: a missing ``by`` reaches the door and is refused
    there (the actor law), surfaced through this same loud-but-not-corrupting path."""
    project, root = _registered_project_for(manuscript_dir)
    if project is None:
        msg = (f"bank_snapshot skipped at {label!r}: {manuscript_dir} is not a "
               "registered project (no versions_dir to bank the ruled snapshot into)")
        _log.warning(msg)
        sink["snapshot_error"] = msg
        return
    try:
        rec = bank_snapshot(project, label, by=by, repo_root=root)  # type: ignore[arg-type]
        sink["snapshot"] = rec["id"]
    except Exception as e:   # LOUD, never corrupting — the door is fail-closed/atomic
        msg = f"bank_snapshot FAILED at {label!r} for project {project!r}: {e}"
        _log.error(msg)
        sink["snapshot_error"] = msg


# ---------------------------------------------------------------------------
# the figure-layout review gates — run over the finalised PDF at release
# ---------------------------------------------------------------------------

def layout_gate_results(manuscript_dir: str | Path, *,
                        pdf_path: str | Path | None = None,
                        size_gate: bool = True) -> dict:
    """Run the three figure-layout review gates (G1 final-size visual, G2 semantic
    float, G3 figure contract) over the finalised PDF and return their combined
    result — shaped to hand straight to ``build_bundle(gate_results=...)`` so the
    release bundle pins the layout verdict alongside the compile report.

    The gates inspect the COMPILED ARTEFACT at physical size (the source-level
    figure/caption/table audits cannot see a figure scaled to illegibility, a float
    that ships past the conclusion, or an asset panel the caption never covers). This
    is the least-contested release seam: a new read-only collector that discovers the
    PDF the way :func:`build_bundle` does and never touches the state machine or the
    finalize compile. ``size_gate`` may be disabled where no rasteriser is present
    (G2/G3 are source+aux only)."""
    from laplace.pipeline import layout_gates
    md = Path(manuscript_dir)
    rel_pdf = str(pdf_path) if pdf_path else _discover_final_pdf(md)
    if not rel_pdf:
        return {"clean": False, "pass": False,
                "error": "no final PDF to inspect", "gates": {}, "findings": []}
    pdf = md / rel_pdf if not Path(rel_pdf).is_absolute() else Path(rel_pdf)
    aux = pdf.with_suffix(".aux")
    aux = aux if aux.is_file() else (md / "main.aux" if (md / "main.aux").is_file() else None)
    return layout_gates.run_layout_gates(pdf, md, aux_path=aux, size_gate=size_gate)
