#!/usr/bin/env python3
"""reprojection_gate.py — the re-projection leg's GATE, as one durable command.

The leg (round 3's compiled-not-fired Locus B, first fired 2026-07-19): blind
builders re-realise debt-carrying sections with the source's lost beats restored.
This gate is the leg's mechanical tail — the half that must never be improvised:

  1. VALIDATE — :mod:`laplace.pipeline.freeze_validate` over (before-snapshot,
     working tree): substance deltas STOP, mechanical slips are retry-lawful,
     benign drift reports. Front matter rides the identity check (main.tex).
  2. REVERT — every substance-violating fragment is restored from the snapshot
     (never auto-fixed; "record it and stop that fragment"), and the defect
     banks as a typed record.
  3. RE-MEASURE — the source-delta reader re-fires: the debt must MOVE, and the
     number is banked, never narrated.
  4. BANK — the run record (verdict + reverts + before/after debt) writes to
     ``<manuscript>/reprojection/run_record.json`` beside the freeze verdict.

Usage:
  python3 scripts/reprojection_gate.py <manuscript_dir> <snapshot_dir> \
      --source <source_draft> [--sections s1,s2,...] [--dry-run]

``--dry-run`` validates and reports but reverts nothing and banks nothing.
Exit 0 = gate ran (read the verdict for pass/fail); 2 = usage error.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _next_archive(out: Path, stem: str, date: str) -> Path:
    """The dated archive path for ``<stem>`` on ``date`` that never overwrites an
    existing archive: ``<stem>_<date>.json``, then ``_<date>_2.json``, ``_3`` …
    (the ``rounds/detector_organs_<date>.json`` idiom, collision-suffixed). The
    ``.json`` sorts before ``_2.json`` and later dates sort after, so a lexical
    ``sorted(...)[-1]`` over the glob picks the newest same-day archive."""
    cand = out / f"{stem}_{date}.json"
    n = 2
    while cand.exists():
        cand = out / f"{stem}_{date}_{n}.json"
        n += 1
    return cand


def write_run_archives(out: Path, record: dict, verdict: dict,
                       date: str | None = None) -> dict:
    """Bank the DATED archives beside the latest-pointer files — the fix for the
    forcing defect (the pointers overwrote per run, so generation history died).
    A same-day re-run suffixes ``_2``, ``_3`` … and NEVER overwrites an archive.
    Returns ``{"run_record": <path>, "freeze_verdict": <path>}`` (both as str)."""
    from laplace.pipeline import freeze_validate as fv
    out.mkdir(parents=True, exist_ok=True)
    date = date or time.strftime("%Y-%m-%d")
    rr = _next_archive(out, "run_record", date)
    rr.write_text(json.dumps(record, indent=1, ensure_ascii=False) + "\n",
                  encoding="utf-8")
    fvp = _next_archive(out, "freeze_verdict", date)
    fv.write_verdict(verdict, fvp)
    return {"run_record": str(rr), "freeze_verdict": str(fvp)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("manuscript_dir")
    ap.add_argument("snapshot_dir", help="the banked before-fragments dir (incl. main.tex)")
    ap.add_argument("--source", required=True, help="the source draft (V1) for the re-measure")
    ap.add_argument("--sections", default="", help="comma-separated fragment stems to gate")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    from laplace.pipeline import freeze_validate as fv
    from laplace.pipeline.readers import source_delta as SD

    md = Path(args.manuscript_dir)
    snap = Path(args.snapshot_dir)
    fragments = [s for s in args.sections.split(",") if s.strip()] or None

    before = {p.stem: p.read_text(encoding="utf-8", errors="replace")
              for p in sorted(snap.glob("*.tex")) if p.name != "main.tex"}
    after = {p.stem: p.read_text(encoding="utf-8", errors="replace")
             for p in sorted(md.glob("*.tex"))
             if p.name != "main.tex" and (fragments is None or p.stem in fragments
                                          or p.stem in before)}
    if fragments:
        before = {k: v for k, v in before.items() if k in fragments}
        after = {k: v for k, v in after.items() if k in fragments or k in before}

    verdict = fv.validate_freeze(
        before, after,
        main_before=(snap / "main.tex").read_text(encoding="utf-8", errors="replace")
        if (snap / "main.tex").is_file() else None,
        main_after=(md / "main.tex").read_text(encoding="utf-8", errors="replace")
        if (md / "main.tex").is_file() else None)

    reverted: list[dict] = []
    for name, frag in verdict["per_fragment"].items():
        if not frag["substance"]:
            continue
        entry = {"fragment": name,
                 "classes": [v["class"] for v in frag["substance"]],
                 "reverted": False}
        if not args.dry_run and name in before:
            (md / f"{name}.tex").write_text(before[name], encoding="utf-8")
            entry["reverted"] = True
        reverted.append(entry)
    if (not args.dry_run and verdict["front_matter"]["checked"]
            and verdict["front_matter"]["identical"] is False):
        (md / "main.tex").write_text(
            (snap / "main.tex").read_text(encoding="utf-8"), encoding="utf-8")
        reverted.append({"fragment": "main.tex",
                         "classes": ["front-matter-touched"], "reverted": True})

    delta = SD.read_source_delta(args.source, md / "main.tex")
    record = {
        "kind": "reprojection-run-record",
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "gated_fragments": sorted(after),
        "freeze": {"pass": verdict["pass"],
                   "substance_pass": verdict["substance_pass"],
                   "mechanical_pass": verdict["mechanical_pass"],
                   "retry_lawful": verdict["retry_lawful"],
                   "classes": verdict["classes"]},
        "reverted": reverted,
        "source_delta_after": {"n": len(delta.get("findings", [])),
                               "counts": delta.get("counts")},
        "dry_run": bool(args.dry_run),
    }
    if not args.dry_run:
        out = md / "reprojection"
        out.mkdir(parents=True, exist_ok=True)
        # latest-pointer files — unchanged (the newest run is always readable here)
        fv.write_verdict(verdict, out / "freeze_verdict.json")
        (out / "run_record.json").write_text(
            json.dumps(record, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        # DATED archives beside the pointers — the fix for the forcing defect: the
        # pointers overwrote per run, so generation history died. Archives never overwrite.
        record["archives"] = write_run_archives(out, record, verdict)
        record["banked"] = str(out)
    print(json.dumps(record, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
