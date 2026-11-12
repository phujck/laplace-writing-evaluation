# shim: the bespoke gate script is archived (scripts/_archive/paper_gates.py);
# the generic runner is pipeline.loop_gates.run_gates, driven by the registry's gates_profile.
#
# VERDICT sentinel (the pipe-swallow fix, 2026-07-12): loop_gates.run_gates returns a
# report -- per-section/-full detail -- but no aggregated pass/fail, and this shim (like
# the archived script it byte-for-byte reproduces) used to just json.dumps() that report
# and fall off the end, exiting 0 whether the report was clean or RED. _verdict aggregates
# the report into ok + failing-check shortnames; main() now emits VERDICT=PASS /
# VERDICT=FAIL as its LAST line and mirrors it in the exit code, so a truncated read
# (tail -1, last line of a log) still carries the whole verdict.
import json
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from laplace.pipeline.loop_gates import run_gates

_CHECKS = ("draft_missing", "orphan_numerals", "bad_claim_tags", "bad_citekeys",
           "banned_constructions", "lexicon_ladder", "banned_jargon")


def _verdict(report: dict) -> tuple[bool, list[str]]:
    """(ok, sorted failing-check shortnames) from a loop_gates.run_gates report."""
    if "error" in report:
        return False, ["error"]
    reasons: set[str] = set()
    for sec in report.get("sections", {}).values():
        if "error" in sec:
            reasons.add("draft_missing")
            continue
        for key in ("orphan_numerals", "bad_claim_tags", "bad_citekeys",
                    "banned_constructions"):
            if sec.get(key):
                reasons.add(key)
    full = report.get("full", {})
    if any(v != "ok" for v in full.get("lexicon_ladder", {}).values()):
        reasons.add("lexicon_ladder")
    if full.get("banned_jargon"):
        reasons.add("banned_jargon")
    return not reasons, sorted(reasons)


def main(project: str = "paper_eigen") -> int:
    report = run_gates(project)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    ok, reasons = _verdict(report)
    if ok:
        print("VERDICT=PASS")
    else:
        n_total = 1 if reasons == ["error"] else len(_CHECKS)
        print(f"VERDICT=FAIL checks={len(reasons)}/{n_total} reasons={','.join(reasons)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
