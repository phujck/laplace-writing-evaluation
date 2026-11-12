"""detector_organs.py — the detector-organs runner, a durable growth-leg organ
(ARMING_2026-07-16, the infrastructure law: *hand-production is BANNED — every
deliverable is a durable pipeline organ; the acceptance test is reproducibility*).

The five DETECTOR-ORGANS each ship as code + tests (four from the arming, the
fifth wired 2026-07-19 — the consolidation's C07: front/back-matter coherence
existed as a detector but rode no gate, so a weld that destroyed the abstract and
marking passed every organ):

* :mod:`promise_audit`            — the promised-but-absent detector,
* :mod:`readers.source_delta`     — the SOURCE-DELTA reader (source-vs-projection),
* :mod:`meta_leak_scrub`          — the META-LEAK scrub over the converge path,
* :mod:`matter_audit`             — FRONT/BACK-MATTER coherence (abstract present,
  title informative, promises delivered — the front-matter identity floor),
* :mod:`gap_ledger`               — the GAP LEDGER + research-intent typing.

What was missing was the DURABLE CALLER that fires them together and mints the
census. The falqon census
(``paper_falqon/rounds/detector_organs_<date>.json``) was first minted by a runner
that existed ONLY in an ephemeral scratchpad — exactly the "an agent improvised an
artefact instead of building the organ" hazard the infrastructure law forbids. This
module IS that runner, committed: rerunning the committed machine
(``python -m laplace.pipeline.detector_organs --project paper_falqon``) re-mints the
census with no agent in the loop.

READ-ONLY: the organs read the source draft and the projection tree and compile a
typed gap ledger; nothing is applied. The gap ledger's quarry is the SOURCE-AWARE
quarry (:func:`gap_ledger.source_aware_quarry_fn`) — a source-delta loss probes
against his own draft (where the lost span lives verbatim), so it stays MINEABLE
(re-project from source) rather than mistyped as a novel conjecture.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Optional, Union

from laplace.pipeline import promise_audit as PA
from laplace.pipeline import matter_audit as MA
from laplace.pipeline import meta_leak_scrub as MLS
from laplace.pipeline import gap_ledger as GL
from laplace.pipeline.readers import source_delta as SD


def _spine_sections(plan_path: Path) -> list[str]:
    """The ordered spine section ids from a projection plan, for spine-criticality.
    Absent / malformed plan degrades to an empty spine (no gap is spine-critical, the
    declared default) — never a crash."""
    if not plan_path.is_file():
        return []
    try:
        pj = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    spine: list[str] = []
    for s in (pj.get("sections") or pj.get("plan") or []):
        sid = s.get("id") if isinstance(s, dict) else None
        if sid:
            spine.append(sid)
    return spine


def _resolve_paths(project: str, root: Union[str, Path],
                   main_tex: Optional[Union[str, Path]],
                   source: Optional[Union[str, Path]]) -> tuple[Path, Path, Path]:
    """Resolve (main_tex, source_v1, projection_plan) for a project by convention,
    honouring explicit overrides. Convention mirrors the falqon tree:
    ``<root>/<project>/manuscript/main.tex``, ``<root>/<project>/PAPER_*_V1.md``,
    ``<root>/<project>/manuscript/projection_plan.json``."""
    base = Path(root) / project
    ms = base / "manuscript"
    main = Path(main_tex) if main_tex else ms / "main.tex"
    if source is not None:
        src = Path(source)
    else:
        # the convention: a single PAPER_*_V1.md source draft beside the project
        cands = sorted(base.glob("PAPER_*_V1.md")) or sorted(base.glob("*_V1.md"))
        src = cands[0] if cands else base / "PAPER_FALQON_V1.md"
    return main, src, ms / "projection_plan.json"


def run_detector_organs(project: str, *,
                        root: Union[str, Path] = ".",
                        main_tex: Optional[Union[str, Path]] = None,
                        source: Optional[Union[str, Path]] = None,
                        round: int = 3) -> dict[str, Any]:
    """Fire the four detector-organs over ``project`` and return the evidence dict
    (the shape banked to ``rounds/detector_organs_<date>.json``). READ-ONLY.

    The gap ledger is built with the SOURCE-AWARE quarry so source-delta losses probe
    against his draft (mineable), never the conceptric (which lacks the lost span)."""
    main, src, plan = _resolve_paths(project, root, main_tex, source)
    spine = _spine_sections(plan)

    promise = PA.check_promises(main)
    srcdelta = SD.read_source_delta(src, main)
    scrub = MLS.scrub_project(project)
    matter = MA.check_matter_coherence(main)

    findings = (promise.get("findings", [])
                + srcdelta.get("findings", [])
                + MLS.to_findings(scrub)
                + matter.get("findings", []))

    quarry = GL.source_aware_quarry_fn(project, src)
    # THE RETURN LEG (ruling_recall): the gap ledger's rank has always named "then his
    # PRIOR RULINGS" as its third term, and no caller had ever passed one — the boost was
    # a decorative parameter and the docstring an overclaim. Here his LIVE banked rulings
    # are recalled against the kinds actually present in this round's gaps, so a gap on a
    # subject he has ruled on outranks an equally-severe gap he has not. The boost is
    # bounded (``ruling_recall.MAX_BOOST``) and sits BELOW spine-criticality in the sort
    # key, so it re-orders within a tier and can never invert the spine law.
    from laplace.engine import ruling_recall
    # keyed by gap ID with the gap's own QUOTE as the match context. Neither the gap
    # KIND (source-argument-lost) nor its ISSUE carries signal: the kind is engine
    # vocabulary his rulings never speak, and the issue is a per-kind template string
    # identical across every gap of that kind — keying on either boosts every gap
    # equally, which is the uniform nudge this map exists to avoid. The QUOTE is the
    # actual lost span, so it names the subject he ruled about. compile_gaps is pure, so
    # compiling once here to get the ids costs a walk of the findings, not IO.
    _pre = GL.compile_gaps(findings, None, spine_sections=spine or None)
    gap_keys = {g.id: f"{g.quote} {g.where} {g.section}".strip() or g.issue
                for g in _pre}
    try:
        prior = ruling_recall.rulings_boost(root, gap_keys)
    except Exception:
        prior = {}
    ledger = GL.build_ledger(findings, spine_sections=spine or None,
                             quarry_fn=quarry, project=project, round=round,
                             prior_rulings=prior)

    return {
        "generated": datetime.datetime.now().isoformat(timespec="seconds"),
        "by": "detector_organs.run_detector_organs (DETECTOR-ORGANS, "
              "ARMING_2026-07-16)",
        "read_only": True,
        "project": project,
        "note": "the manuscript tree may have concurrent sibling writers (figures "
                "organ); the promise census is a snapshot of a moving tree. The gap "
                "ledger's source-delta gaps probe against the source draft (the "
                "source-aware quarry), so they stay mineable rather than typed novel.",
        "promise": {"pass": promise["pass"], "present": promise["present"],
                    "counts": promise["counts"], "n": len(promise["findings"])},
        "source_delta": {"pass": srcdelta["pass"], "present": srcdelta["present"],
                         "counts": srcdelta["counts"],
                         "n": len(srcdelta["findings"]),
                         "examples": [{"kind": f["kind"], "survival": f["survival"],
                                       "primary": f["primary"]}
                                      for f in srcdelta["findings"][:6]]},
        "matter": {"pass": matter["pass"], "n": len(matter["findings"]),
                   "counts": matter.get("counts"),
                   "examples": [{"kind": f.get("kind"), "issue": f.get("issue")}
                                for f in matter["findings"][:6]]},
        "meta_leak_scrub": {"pass": scrub["pass"], "n": scrub["n"],
                            "core": scrub["core"], "source_tier": scrub["source_tier"],
                            "by_class": scrub["by_class"],
                            "examples": [{"file": h.get("file"), "line": h.get("line"),
                                          "class": h.get("class"),
                                          "match": h.get("match"),
                                          "trust": h.get("trust")}
                                         for h in scrub["hits"][:8]]},
        "gap_ledger": {"census": ledger["census"], "all_gaps_n": ledger["all_gaps_n"],
                       "capped_gaps": ledger["gaps"],
                       "conceptric_intents": ledger["conceptric_intents"],
                       "research_intents": ledger["research_intents"],
                       # the return leg, on the record: which finding kinds his banked
                       # rulings boosted this round, and by how much. An EMPTY map is a
                       # real reading (no live ruling names these kinds), never a silent
                       # channel — the keys scanned are stated beside it.
                       "prior_rulings": {"boost": prior,
                                         "keys_scanned": sorted(gap_keys),
                                         "source": "ruling_recall.rulings_boost over "
                                                   "proxy_verdicts.jsonl (live rulings "
                                                   "only; retired ones never steer)"}},
    }


def bank_detector_organs(project: str, *,
                         root: Union[str, Path] = ".",
                         out_dir: Optional[Union[str, Path]] = None,
                         **kw: Any) -> tuple[Path, dict[str, Any]]:
    """Run the organs and PERSIST the evidence to
    ``<out_dir or <root>/<project>/rounds>/detector_organs_<date>.json``. Returns
    ``(path, evidence)``. Rerunning re-mints the same file (a moving manuscript tree
    is the only non-determinism; the gap-ledger typing is deterministic for fixed
    findings)."""
    evidence = run_detector_organs(project, root=root, **kw)
    out = Path(out_dir) if out_dir else Path(root) / project / "rounds"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"detector_organs_{datetime.date.today().isoformat()}.json"
    path.write_text(json.dumps(evidence, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    return path, evidence


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Fire the four DETECTOR-ORGANS over a project and bank the "
                    "census (the durable growth-leg runner).")
    ap.add_argument("--project", default="paper_falqon",
                    help="project name (default: paper_falqon)")
    ap.add_argument("--root", default=".", help="repo root (default: .)")
    ap.add_argument("--main-tex", default=None, help="override main .tex path")
    ap.add_argument("--source", default=None, help="override source draft path")
    ap.add_argument("--round", type=int, default=3, help="round number stamp")
    ap.add_argument("--no-bank", action="store_true",
                    help="run and print the census but write no file")
    args = ap.parse_args(argv)

    if args.no_bank:
        evidence = run_detector_organs(args.project, root=args.root,
                                       main_tex=args.main_tex, source=args.source,
                                       round=args.round)
        path = None
    else:
        path, evidence = bank_detector_organs(
            args.project, root=args.root, main_tex=args.main_tex,
            source=args.source, round=args.round)

    if path is not None:
        print("BANKED:", path)
    print(json.dumps({
        "promise": evidence["promise"]["counts"]
        or f"clean (present={evidence['promise']['present']})",
        "source_delta_n": evidence["source_delta"]["n"],
        "source_delta_classes": evidence["source_delta"]["counts"],
        "meta_leak_n": evidence["meta_leak_scrub"]["n"],
        "meta_leak_by_class": evidence["meta_leak_scrub"]["by_class"],
        "gap_census": evidence["gap_ledger"]["census"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
