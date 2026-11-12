"""fitness_panel.py — the fitness panel's reader: selection's instrument, read-only.

The F23 readiness verdict (2026-07-20): variation ready, heredity ready, selection
missing. The rule (ψ) and the threshold (φ) belong to the author — this panel holds
the readings he rules them against; it is not the rule. Every number below is a banked
artifact re-read through its own record (numbers banked-or-absent, never narrated):

* the source-delta debt trajectory — ``reprojection/run_record.json`` (+ the
  census history in ``rounds/detector_organs_*.json``);
* the freeze verdicts — ``reprojection/freeze_verdict.json`` (substance held?
  mechanical? what reverted);
* the converge axes — ``rounds/harnessed/detect_pre_*.json`` / ``detect_post_*``
  (mechround open counts, the round-over-round derivative);
* the suite floor — ``corpus_friction/suite_baseline.json`` (the named red set).

Pure read; absent artifacts degrade to empty fields, never a raise.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def _read_json(p: Path) -> dict | None:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def read_fitness(project: str, root: str | Path = ".") -> dict[str, Any]:
    root = Path(root)
    from laplace.pipeline import registry
    proj = registry.resolve(project)
    md = (proj.path(proj.manuscript_dir, root)
          if (proj and proj.manuscript_dir) else None)
    if md is None:
        return {"present": False, "project": project}

    out: dict[str, Any] = {"present": False, "project": project}

    # the debt trajectory: census history (dated) + the latest gate re-measure
    traj: list[dict[str, Any]] = []
    rounds = md.parent / "rounds" if (md / "rounds").is_dir() is False else md / "rounds"
    for p in sorted((md.parent / "rounds").glob("detector_organs_*.json")) or \
             sorted((md / "rounds").glob("detector_organs_*.json")):
        c = _read_json(p) or {}
        sd = c.get("source_delta") or {}
        if sd.get("n") is not None:
            m = re.search(r"(\d{4}-\d{2}-\d{2})", p.name)
            traj.append({"at": m.group(1) if m else "", "n": sd["n"],
                         "source": p.name})
    rr = _read_json(md / "reprojection" / "run_record.json")
    seen: set[tuple[str, Any]] = set()
    if rr:
        sda = rr.get("source_delta_after") or {}
        pt = {"at": str(rr.get("at") or "")[:10], "n": sda.get("n"),
              "source": "reprojection/run_record.json"}
        seen.add((pt["at"], pt["n"]))
        traj.append(pt)
    # DATED gate archives (the forcing-defect fix): each banked run_record_<date>.json
    # is its own trajectory point — ADDITIVE, so history no longer dies with the pointer.
    # Deduped by (at, n) against the latest-pointer read (the newest archive IS that run).
    for p in sorted((md / "reprojection").glob("run_record_*.json")):
        c = _read_json(p) or {}
        sda = c.get("source_delta_after") or {}
        key = (str(c.get("at") or "")[:10], sda.get("n"))
        if key in seen:
            continue
        seen.add(key)
        traj.append({"at": key[0], "n": key[1], "source": f"reprojection/{p.name}"})
    out["debt_trajectory"] = traj

    fv = _read_json(md / "reprojection" / "freeze_verdict.json")
    if fv:
        out["freeze"] = {"pass": fv.get("pass"),
                         "substance_pass": fv.get("substance_pass"),
                         "mechanical_pass": fv.get("mechanical_pass"),
                         "classes": fv.get("classes")}

    mech: dict[str, Any] = {}
    hdir = md / "rounds" / "harnessed"
    if hdir.is_dir():
        pres = sorted(hdir.glob("detect_pre_*.json"))
        posts = sorted(hdir.glob("detect_post_*.json"))
        def _open_n(p: Path) -> Any:
            d = _read_json(p) or {}
            for k in ("open", "flags_routed", "open_findings_n"):
                v = d.get(k)
                if isinstance(v, int):
                    return v
            return None
        if pres:
            mech["pre"] = _open_n(pres[-1])
        if posts:
            mech["post"] = _open_n(posts[-1])
        if isinstance(mech.get("pre"), int) and isinstance(mech.get("post"), int):
            mech["derivative"] = mech["post"] - mech["pre"]
    out["mechround"] = mech

    sb = _read_json(root / "corpus_friction" / "suite_baseline.json")
    if sb:
        out["suite_baseline"] = {"named_red": (sb.get("counts") or {}).get("failed"),
                                 "captured_at": sb.get("captured_at")}

    out["present"] = bool(traj or fv or mech)
    out["law"] = ("The readings the author rules psi (the fitness rule) and phi (the "
                  "promote threshold) against; this panel holds the numbers, not the "
                  "rule (the selection-layer WO carries the rest).")
    return out
