"""The generation ledger — heredity's stamp: one refs-only record per generation.

A generation is one full turn of the evolutionary loop: intents entered and
ratified, the manuscript re-projected, converged, minted, and read by R10. This
ledger stamps that turn — appends one record to ``<manuscript>/generations.jsonl``
naming (by ref + identity, never by copied number) the artifacts that generation
produced. The record is a pointer into the banked evidence, so a later reader
reconstructs the generation from the same bytes the loop wrote — never a paraphrase.

The stamp is explicit about absence: an artifact the generation never produced banks
a ``null`` ref (the stamp is still lawful). It refuses a double-stamp — when every
ref it would bank is identical to the previous generation's, nothing moved and
nothing is banked (an error dict). An unattributed stamp (empty ``by``) refuses:
no generation is stamped in nobody's name (the actor law, mirrored from
``ledger.bank_snapshot`` / the reprojection gate).

Public API:
    stamp_generation(manuscript_dir, corpus, *, by, dials_profile="") -> dict
    read_generations(manuscript_dir) -> list[dict]
    CLI: python -m laplace.pipeline.generation_ledger <corpus> --by <actor> [--profile ...]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from laplace.pipeline import registry
from laplace.pipeline.ledger import append_jsonl, read_jsonl

RECORD = "generation"


def _now() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def _round_int(name: str) -> int:
    """Round ordinal from a detect record filename (``detect_pre_r10.json`` sorts
    after ``detect_pre_r2.json``) — mirrors ``convergence_ledger._round_int``."""
    m = re.search(r"(?:round|_r)(\d+)", name)
    return int(m.group(1)) if m else -1


def _newest_lexical(paths: list[Path]) -> Optional[Path]:
    """The newest of a dated-archive glob by lexical order — dates sort
    chronologically and the ``.json`` vs ``_2.json`` suffix sorts the collision
    tail after (the ``run_record_<date>.json`` / detector-census idiom)."""
    return sorted(paths)[-1] if paths else None


def _newest_round(paths: list[Path]) -> Optional[Path]:
    """The newest of a round-numbered glob by round ordinal (``detect_*_r*``)."""
    return max(paths, key=lambda p: _round_int(p.name), default=None)


def _rel(md: Path, p: Optional[Path]) -> Optional[str]:
    """A manuscript-relative ref string for a resolved artifact, or ``None`` when
    absent (explicit absence — a null ref, never a fabricated path)."""
    if p is None:
        return None
    try:
        return str(p.relative_to(md))
    except ValueError:
        return str(p)


def _read_json(p: Path) -> Optional[dict]:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _reprojection_refs(md: Path) -> dict[str, Optional[str]]:
    rep = md / "reprojection"
    return {
        "run_record": _rel(md, _newest_lexical(list(rep.glob("run_record_*.json")))),
        "freeze_verdict": _rel(md, _newest_lexical(list(rep.glob("freeze_verdict_*.json")))),
    }


def _converge_refs(md: Path) -> dict[str, Optional[str]]:
    h = md / "rounds" / "harnessed"
    return {
        "detect_pre": _rel(md, _newest_round(list(h.glob("detect_pre_*.json")))),
        "detect_post": _rel(md, _newest_round(list(h.glob("detect_post_*.json")))),
    }


def _minted_refs(md: Path) -> dict[str, Optional[str]]:
    fin = md / "release" / "finalize.json"
    data = _read_json(fin) if fin.is_file() else None
    pdf = (data or {}).get("pdf_path") if data else None
    return {
        "pdf": str(pdf) if pdf else None,
        "finalize": "release/finalize.json" if fin.is_file() else None,
    }


def _r10_refs(records: list[dict]) -> dict[str, Any]:
    """The newest R10 reader-report's id + its clean bit (both ``None`` absent).
    Identity + verdict only — the report body stays in the feedback ledger."""
    r10 = [r for r in records
           if r.get("record") == "reader-report" and r.get("reader") == "R10"]
    if not r10:
        return {"report_id": None, "clean": None}
    newest = max(r10, key=lambda r: str(r.get("ts") or ""))
    return {"report_id": newest.get("id"), "clean": newest.get("clean")}


def _entered(records: list[dict], prev_stamped_at: Optional[str]) -> dict[str, list]:
    """The ratified operations that entered this generation: ratified-operation
    records with ``ts`` after the previous generation's stamp (all of them for
    generation 1). ``ratified_op_ids`` are the op record ids; ``intent_ids`` are
    the intents each op consumed (its ``target``)."""
    op_ids: list[str] = []
    intent_ids: list[str] = []
    for r in records:
        if r.get("record") != "ratified-operation":
            continue
        if prev_stamped_at is not None and str(r.get("ts") or "") <= prev_stamped_at:
            continue
        if r.get("id"):
            op_ids.append(r["id"])
        if r.get("target"):
            intent_ids.append(r["target"])
    return {"ratified_op_ids": op_ids, "intent_ids": intent_ids}


def _ref_blocks(rec: dict) -> tuple:
    """The comparable ref surface of a generation record — the four ref blocks
    (reprojection, converge, minted, r10). Two generations whose whole surface is
    identical are a double-stamp (nothing moved)."""
    return (rec.get("reprojection"), rec.get("converge"),
            rec.get("minted"), rec.get("r10"))


def read_generations(manuscript_dir: Path | str) -> list[dict]:
    """Every generation record on ``<manuscript_dir>/generations.jsonl``, in
    stamp order. Tolerant pure read: ``[]`` when absent; corrupt lines are skipped
    (``ledger.read_jsonl``); filtered to the ``generation`` record kind."""
    ledger = Path(manuscript_dir) / "generations.jsonl"
    return [r for r in read_jsonl(ledger) if r.get("record") == RECORD]


def stamp_generation(manuscript_dir: Path | str, corpus: str, *, by: str,
                     dials_profile: str = "") -> dict:
    """Stamp one generation for ``corpus``: derive the refs its artifacts sit at,
    append the frozen refs-only record to ``<manuscript_dir>/generations.jsonl``,
    and return it. Refs + identity only — never a copied number. An absent artifact
    banks a ``null`` ref (the stamp stays lawful).

    Refuses (returns an ``{"error": ...}`` dict, banks nothing) when:

    * ``by`` is empty — no generation is stamped in nobody's name;
    * every ref it would bank equals the previous generation's — a double-stamp,
      nothing moved.
    """
    if not (by or "").strip():
        return {"error": "stamp refused: `by` required — no generation is stamped "
                         "in nobody's name (the actor law)"}
    md = Path(manuscript_dir)
    existing = read_generations(md)
    prev = existing[-1] if existing else None
    prev_at = prev.get("stamped_at") if prev else None

    from laplace.pipeline.evolution_consumer import _feedback_ledger
    fb = _feedback_ledger(md)
    records = read_jsonl(fb) if fb.is_file() else []

    n = len(existing) + 1
    record = {
        "id": f"GEN-{corpus}-{n}",
        "record": RECORD,
        "n": n,
        "corpus": corpus,
        "stamped_at": _now(),
        "stamped_by": by,
        "dials_profile": dials_profile,
        "entered": _entered(records, prev_at),
        "reprojection": _reprojection_refs(md),
        "converge": _converge_refs(md),
        "minted": _minted_refs(md),
        "r10": _r10_refs(records),
    }

    if prev is not None and _ref_blocks(record) == _ref_blocks(prev):
        return {"error": "stamp refused: every ref is identical to generation "
                         f"{prev.get('n')} — nothing moved, no double-stamp",
                "would_be": record["id"]}

    append_jsonl(md / "generations.jsonl", record)
    return record


# ---------------------------------------------------------------------------
# CLI — python -m laplace.pipeline.generation_ledger <corpus> --by <actor>
# ---------------------------------------------------------------------------

def _resolve_dir(project_or_dir: str | Path,
                 repo_root: Path | None = None) -> Optional[Path]:
    """A manuscript dir from a registry project name (preferred) or an on-disk
    path — mirrors ``convergence_ledger._resolve_dir`` (the reprojection-gate/
    registry resolution pattern)."""
    proj = registry.resolve(str(project_or_dir))
    if proj is not None and proj.manuscript_dir:
        md = proj.path(proj.manuscript_dir, repo_root)
        if md is not None and md.is_dir():
            return md
    p = Path(project_or_dir)
    if p.is_dir():
        return p
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("corpus", help="registered project name (or a manuscript dir)")
    ap.add_argument("--by", required=True, help="the actor stamping this generation")
    ap.add_argument("--profile", default="", help="the dials profile in force (optional)")
    args = ap.parse_args(argv)

    md = _resolve_dir(args.corpus)
    if md is None:
        print(json.dumps({"error": f"no manuscript dir for {args.corpus!r}"}))
        return 2
    out = stamp_generation(md, args.corpus, by=args.by, dials_profile=args.profile)
    print(json.dumps(out, indent=1, ensure_ascii=False))
    return 0 if "error" not in out else 1


if __name__ == "__main__":
    sys.exit(main())
