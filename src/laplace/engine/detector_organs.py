"""detector_organs.py — the detector-organs reader, the pure conjugate of the
runner (:mod:`laplace.pipeline.detector_organs`, the conjugate wave, Lane 0).

view=mechanism (SCOUT_2026-07-17_the-conjugate-wave §1.5): the `/pipeline`
detectors card reads the organ's OWN facts through this function — it never
re-parses ``rounds/detector_organs_<date>.json`` by hand, and it never re-fires
the runner on a GET (that would compile the tex, violating pure-reads on GET,
WIRING LAW 2).

This is a THIN LOADER, by design a SEPARATE top-level module from the runner:
importing it pulls in only :mod:`json` + :mod:`pathlib`, never
:mod:`laplace.pipeline.detector_organs` (which imports promise_audit /
meta_leak_scrub / gap_ledger / the source-delta reader — the compile-adjacent
machinery). So a GET path can import this reader without dragging the heavy
runner into the request.

The reader loads the NEWEST banked census (``detector_organs_<date>.json`` under
``<root>/<project>/rounds``, newest by the ISO date in the filename) and returns
the per-detector facts the card acts on. It NEVER raises and NEVER returns None:
an absent artifact — or an unreadable / malformed one (the boom-guard) — degrades
to the honest-empty census (``present`` False, every count zeroed), so the card
renders its declared-absence string ("detectors — no round banked …") rather than
booming.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional, Union

# The five PROMISED-BUT-ABSENT classes the promise-audit organ mints
# (laplace.pipeline.promise_audit :54-58). Enumerated here so the by-class
# absence census carries a STABLE key set (each zeroed) whether the round is
# clean, partial, or entirely absent — the card's fact-rows never appear/vanish.
PROMISE_CLASSES: tuple[str, ...] = (
    "promise-figure-absent",
    "promise-table-absent",
    "promise-xref-dangling",
    "promise-citation-absent",
    "promise-section-absent",
)

# the banked filename convention: rounds/detector_organs_<YYYY-MM-DD>.json
_DATED = re.compile(r"^detector_organs_(\d{4}-\d{2}-\d{2})\.json$")


def _empty(project: str) -> dict[str, Any]:
    """The honest-empty census: no round banked (or an unreadable one). Every fact
    zeroed/empty, ``present`` False — never a raise, never a None."""
    return {
        "present": False,
        "project": project,
        "date": "",
        "generated": "",
        "path": None,
        "gaps": {
            "gaps": 0,
            "capped": 0,
            "conceptric_intents": 0,
            "research_intents": 0,
            "by_gap_class": {},
            "by_research_class": {},
            "spine_critical": 0,
            "substrate_absent": 0,
        },
        "source_delta": {"n": 0, "by_class": {}},
        "meta_leak": {"n": 0, "by_class": {}},
        "promise": {"n": 0, "by_class": {c: 0 for c in PROMISE_CLASSES}},
    }


def _newest_round(rounds: Path) -> Optional[tuple[str, Path]]:
    """The (date, path) of the newest banked census in ``rounds``, or None. ISO
    date strings sort chronologically, so the lexical max IS the newest. Files that
    do not match the convention are ignored; a missing dir yields None."""
    if not rounds.is_dir():
        return None
    dated: list[tuple[str, Path]] = []
    for p in rounds.glob("detector_organs_*.json"):
        m = _DATED.match(p.name)
        if m:
            dated.append((m.group(1), p))
    if not dated:
        return None
    return max(dated, key=lambda t: t[0])


def read_detector_organs(project: str,
                         root: Optional[Union[str, Path]] = None) -> dict[str, Any]:
    """Read the newest banked DETECTOR-ORGANS census for ``project`` and return the
    per-detector facts the `/pipeline` detectors card acts on. Pure read: no
    subprocess, no compile, no network, no writes.

    Reads ``<root>/<project>/rounds/detector_organs_<date>.json`` (newest by the
    date in the filename); ``root`` defaults to the repo root (``.``).

    The returned dict ALWAYS carries ``present`` (bool). When no round is banked —
    or the newest file is unreadable/malformed — returns the honest-empty census
    (``present`` False, every count zeroed). When present, ``present`` True plus:

    * ``date`` / ``generated`` — the banked round's filename date and mint timestamp,
    * ``gaps`` — the gap-ledger census (``gaps`` discovered, ``capped``,
      ``conceptric_intents``, ``research_intents``, and the by-class breakdowns),
    * ``source_delta`` — ``n`` findings + ``by_class`` (source-argument/motivation/
      connective-lost),
    * ``meta_leak`` — ``n`` violations + ``by_class``,
    * ``promise`` — ``n`` promised-but-absent + ``by_class`` over PROMISE_CLASSES.
    """
    base = Path(root) if root is not None else Path(".")
    rounds = base / project / "rounds"
    newest = _newest_round(rounds)
    if newest is None:
        return _empty(project)
    date, path = newest

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        census = ((data.get("gap_ledger") or {}).get("census") or {})
        sd = data.get("source_delta") or {}
        ml = data.get("meta_leak_scrub") or {}
        pr = data.get("promise") or {}
        pr_counts = pr.get("counts") or {}
        # stable key set, then any future class the organ mints beyond the five
        promise_by_class = {c: int(pr_counts.get(c, 0)) for c in PROMISE_CLASSES}
        for k, v in pr_counts.items():
            if k not in promise_by_class:
                promise_by_class[k] = v

        try:
            rel = str(path.relative_to(base))
        except ValueError:
            rel = str(path)

        return {
            "present": True,
            "project": data.get("project") or project,
            "date": date,
            "generated": data.get("generated") or "",
            "path": rel,
            "gaps": {
                "gaps": census.get("discovered", 0),
                "capped": census.get("capped", 0),
                "conceptric_intents": census.get("conceptric_intents", 0),
                "research_intents": census.get("research_intents", 0),
                "by_gap_class": census.get("by_gap_class") or {},
                "by_research_class": census.get("by_research_class") or {},
                "spine_critical": census.get("spine_critical", 0),
                "substrate_absent": census.get("substrate_absent", 0),
            },
            "source_delta": {"n": sd.get("n", 0),
                             "by_class": sd.get("counts") or {}},
            "meta_leak": {"n": ml.get("n", 0),
                          "by_class": ml.get("by_class") or {}},
            "promise": {"n": pr.get("n", 0), "by_class": promise_by_class},
        }
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        # boom-guard: a corrupt/partial artifact degrades to honest-empty, never
        # a raise on the GET path (WIRING LAW 2).
        return _empty(project)
