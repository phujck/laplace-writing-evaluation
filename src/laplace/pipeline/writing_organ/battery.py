"""The battery: every mechanical meter over one manuscript, one verdict, one report.

The pipeline wiring of WO-20260809-breath-organ-integration: no render ships unmeasured.
This runs only the DETERMINISTIC tier - the economy meter (reader_vector), the cut meter
(breath), the license's mechanical tier, and the distributional recovery-time stats the
gm-008 lesson asked for (advisory: the judged tier owns taste). The judged tier (probes,
license audits, the tension panel) is dispatched at campaign time, not here.

A manuscript opts in by carrying battery_manifest.json:
  {"sections": [{"name","file","question"}...], "extra_files": [...]}

Run: python3 -m laplace.pipeline.writing_organ.battery <manuscript_dir>
Writes <manuscript_dir>/battery_report.json; exit 0 iff every hard gate passes.
"""

from __future__ import annotations

import json
import re
import sys
import pathlib
import statistics

from . import license as license_mod


def _prose(path: pathlib.Path) -> str:
    text = path.read_text()
    text = re.sub(r"(?m)^%.*$", "", text)
    text = re.sub(r"\\begin\{(equation|align|gathered|table|figure)\}.*?\\end\{\1\}", "",
                  text, flags=re.S)
    return text


def recovery_stats(files: list[pathlib.Path]) -> dict:
    """Distributional context for a qualitative recovery-time review, never a gate.

    Sentence counts can expose an extreme surface, but no ratio or quota certifies prose.
    """
    sentences: list[int] = []
    for f in files:
        text = re.sub(r"\$[^$]*\$", "X", _prose(f))
        for s in re.split(r"(?<=[.!?])\s+", text):
            n = len(s.split())
            if n >= 3:
                sentences.append(n)
    if not sentences:
        return {}
    return {
        "sentences": len(sentences),
        "mean_words_per_sentence": round(statistics.mean(sentences), 1),
        "median_words_per_sentence": statistics.median(sentences),
        "short_sentence_fraction": round(sum(1 for n in sentences if n <= 12) / len(sentences), 3),
        "long_sentence_fraction": round(sum(1 for n in sentences if n >= 45) / len(sentences), 3),
    }


def run(manuscript_dir: pathlib.Path) -> dict:
    manifest = json.loads((manuscript_dir / "battery_manifest.json").read_text())
    files = [manuscript_dir / s["file"] for s in manifest["sections"]]
    files += [manuscript_dir / f for f in manifest.get("extra_files", [])]

    report: dict = {"manuscript": str(manuscript_dir), "gates": {}}

    # license mechanical tier - HARD gate (the closed class is filler everywhere)
    hits = []
    for f in files:
        for h in license_mod.mechanical_tier(f.read_text()):
            hits.append({"file": f.name, **h})
    report["gates"]["license_mechanical"] = {"pass": not hits, "hits": hits}

    # economy meter - HARD gate on cross-section duplicates; flags advisory
    try:
        from .reader_vector import analyse
        r = analyse(files)
        # The abstract summarises the body by design and sits outside the reader's
        # linear prefix, so an abstract<->body echo is structural, not duplication
        # (ruled at the cut-law close, 2026-08-09). Reported, never gating.
        dupes, abstract_echoes = [], []
        for kind, anchor, detail in r["dupes"]:
            if "abstract" in anchor or "abstract" in detail:
                abstract_echoes.append(f"{anchor} {detail}")
            else:
                dupes.append(f"{anchor} {detail}")
        report["gates"]["economy"] = {
            "pass": not dupes, "cross_section_dupes": len(dupes), "dupes": dupes[:8],
            "abstract_echoes": abstract_echoes,
            "repetition_flags": len(r["flags"]),
            "flags": [f"{a}: {d}" for _, a, d in r["flags"]][:8],
        }
    except Exception as err:  # embeddings deps may be absent on a thin box
        report["gates"]["economy"] = {"pass": True, "skipped": f"economy meter unavailable: {err}"}

    # cut meter - advisory report (budgets feed the writers, not a gate)
    try:
        from .breath import movement_report, load
        graph, telling = load(manuscript_dir)
        report["cut_meter"] = movement_report(graph, telling)
    except Exception as err:
        report["cut_meter"] = f"unavailable: {err}"

    # recovery-time distributionals - advisory (gm-008; the panel judges taste)
    report["recovery_stats"] = recovery_stats(files)

    report["pass"] = all(g.get("pass", True) for g in report["gates"].values())
    (manuscript_dir / "battery_report.json").write_text(json.dumps(report, indent=1))
    return report


def main() -> int:
    md = pathlib.Path(sys.argv[1])
    report = run(md)
    for name, g in report["gates"].items():
        print(f"{name}: {'PASS' if g.get('pass') else 'FAIL'}"
              + (f" ({g.get('skipped')})" if g.get("skipped") else ""))
    print(f"recovery: {report['recovery_stats']}")
    print(f"BATTERY {'PASS' if report['pass'] else 'FAIL'} -> battery_report.json")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
