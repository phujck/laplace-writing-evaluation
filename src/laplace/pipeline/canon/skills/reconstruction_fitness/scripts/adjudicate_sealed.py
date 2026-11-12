"""adjudicate_sealed.py - the sealed semantic adjudicator (G1), the meter that un-voids the gate.

The first rung proved the instrument turns and one thing more: the cheap 2-shingle proxy in
adjudicate.py is UNFAITHFUL - it scored three semantically faithful reconstructions "confabulated"
because it measures shared *phrasing*, not shared *meaning*, so every scalar gate that read it is
void. This is its replacement: a SEMANTIC verdict from a blind sealed sub-Eigen, whose OWN
faithfulness is gated before it is trusted to gate anything.

Two halves, both here, both pure - the cloud ghost is spawned by the orchestrator, not by this
script (the same decoupling converge.py used to keep the instrument testable; builder != judge at
every seam):

  1. THE METER. ``build_brief(original, ghost)`` emits the sealed adjudication prompt - the
     interface IS the context wall: two artifacts and nothing else (no digest, no conceptric, no
     session context, no outside knowledge; a judge that shares the maker's context scores
     self-consistency, not fidelity). A blind agent returns a structured verdict
     ``{lost, added, structured, recurses, justification}`` - SEMANTIC lost/added (claims, not
     tokens) and the approximate-closure discriminator (is the residual STRUCTURED - a namable gap
     that RECURSES to seed the next grade - or noise). NO fate label: FORK-FATES is the author's,
     deferred; the meter emits raw signals, the vocabulary that reads them is set downstream.
     ``aggregate`` folds an ENSEMBLE of model/temp-diverse verdicts into the joint - meaning lives
     in the joint, never one channel.

  2. THE METER'S own faithfulness gate. A meter you have not validated cannot validate anything.
     ``faithfulness_gate`` scores the adjudicator against a CALIBRATION SET (pairs whose
     ground-truth property is known, mapped to predicates over the signals) and a PLANTED WRONG
     GHOST (a ghost carrying a specific falsehood the meter MUST surface in ``added``). A meter that
     misses the plant is void; a meter that disagrees with calibration is void; a meter never tried
     against a plant cannot pass. Only a meter that passes un-voids the scalar gate the first rung
     had to throw away. Thresholds are a pluggable policy socket (conservative defaults, F1-adjacent,
     the seam left open) - instrument decoupled from policy, as in converge.py.

Usage:
    python adjudicate_sealed.py brief <original.md> <ghost.md> [--out brief.md]
    python adjudicate_sealed.py aggregate <v1.json> [<v2.json> ...] [--out consensus.json]
                               [--target <id>] [--no-log]
    python adjudicate_sealed.py gate <calibration-dir> [--out report.json] [--no-log]
    python adjudicate_sealed.py stamp <v1.json> [<v2.json> ...] [--target <id>] [--cycle N] [--no-log]
    python adjudicate_sealed.py schema          # the verdict JSON schema (for spawning agents)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[6]

# A small stop set - used ONLY to match the meter's own free-text finding against a plant we
# control (see plant_caught); never to judge fidelity (that is the void meter's error).
_STOP = {"the", "a", "an", "and", "or", "but", "is", "are", "was", "were", "be", "to", "of", "in",
         "on", "for", "it", "its", "as", "at", "by", "that", "this", "with", "from", "not", "so",
         "we", "you", "i", "he", "she", "they", "do", "does", "did", "can", "will", "would", "if"}


# --- the verdict schema: the structured object a sealed adjudicator emits (NO fate label) ----------
VERDICT_KEYS = ("lost", "added", "structured", "recurses", "justification")

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "lost": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Semantic content present in the ORIGINAL but missing or distorted in "
                           "the ghost - specific claims, relations, or quantities, NOT phrasing. "
                           "One lost thing per item; empty if none.",
        },
        "added": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Content ASSERTED BY THE GHOST that is absent from or unsupported by the "
                           "original - the confabulation candidates. One invented/unsupported claim "
                           "per item; empty if none.",
        },
        "structured": {
            "type": "boolean",
            "description": "Is the residual (the lost set) a COHERENT, NAMABLE gap - a missing "
                           "sub-structure a finer pass could build on - rather than scattered "
                           "noise?",
        },
        "recurses": {
            "type": "boolean",
            "description": "Does this residual SEED THE NEXT GRADE - i.e. is the reconstruction a "
                           "good 'partial' that recurses (the approximate-closure target band), "
                           "vs a dead end?",
        },
        "justification": {
            "type": "string",
            "description": "The reasoning behind the verdict, citing the specific content, so an "
                           "outside reader can check it without re-judging.",
        },
    },
    "required": list(VERDICT_KEYS),
    "additionalProperties": False,
}


def build_brief(original: str, ghost: str) -> str:
    """The sealed adjudication prompt - the only thing a blind adjudicator agent is given."""
    return "\n".join([
        "# Sealed semantic adjudication",
        "",
        "You are a SEALED, blind ADJUDICATOR - a sub-Eigen carrying the soul and the standing law, "
        "sealed to exactly the two artifacts below and NOTHING else: no digest, no conceptric, no "
        "session context, no outside knowledge of the specific object, no tools, no files, no "
        "search. A judge that shares the maker's context scores self-consistency, not fidelity - "
        "the interface is the context wall, and holding it is what makes your verdict mean "
        "something.",
        "",
        "You are given an ORIGINAL and a GHOST (a blind reconstruction of it). Judge the ghost "
        "against the original BY MEANING, not by phrasing: a faithful paraphrase that shares few "
        "words is faithful; a fluent restatement that inverts, drops, or invents a claim is not. "
        "(The meter you replace failed precisely by counting shared words - do not repeat its "
        "error.)",
        "",
        "Emit ONE JSON object and nothing else, matching this schema:",
        "",
        "```json",
        json.dumps(VERDICT_SCHEMA, indent=2),
        "```",
        "",
        "Rules of the verdict:",
        "- `lost` / `added` are SEMANTIC and SPECIFIC: name the actual claim, relation, or "
        "quantity, one per item. Empty list if none.",
        "- Judge `structured` and `recurses` on the LOST set: a structured residual is a coherent "
        "missing piece a next, finer pass could build on; noise is scattered, unnamable loss. A "
        "reconstruction that lost only finer detail, in a structured and recoverable way, is the "
        "TARGET (a partial that recurses), not a failure.",
        "- Do NOT emit any fate label (faithful / partial / confabulated). Emit only the raw "
        "signals above; the vocabulary that reads them is set elsewhere.",
        "- `justification` must cite the specific content that drove each call.",
        "",
        "--- ORIGINAL ---",
        original.strip(),
        "",
        "--- GHOST ---",
        ghost.strip(),
        "",
    ])


# --- parsing + validating an agent's returned verdict --------------------------------------------
_JSON_OBJ = re.compile(r"\{.*\}", re.S)


def parse_verdict(text):
    """Parse a verdict from an agent return: a dict passthrough, raw JSON, or a fenced ```json block."""
    if isinstance(text, dict):
        return dict(text)
    s = str(text).strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s, re.S)
    if fence:
        s = fence.group(1)
    else:
        m = _JSON_OBJ.search(s)
        if m:
            s = m.group(0)
    return json.loads(s)


def validate_verdict(v) -> list[str]:
    """Return a list of schema errors (empty list == valid)."""
    if not isinstance(v, dict):
        return ["verdict is not an object"]
    errs: list[str] = []
    for k in ("lost", "added"):
        if k not in v:
            errs.append(f"missing {k!r}")
        elif not isinstance(v[k], list) or not all(isinstance(x, str) for x in v[k]):
            errs.append(f"{k!r} must be a list of strings")
    for k in ("structured", "recurses"):
        if k not in v:
            errs.append(f"missing {k!r}")
        elif not isinstance(v[k], bool):
            errs.append(f"{k!r} must be a boolean")
    if "justification" not in v:
        errs.append("missing 'justification'")
    elif not isinstance(v["justification"], str):
        errs.append("'justification' must be a string")
    return errs


# --- the ensemble: fold model/temp-diverse verdicts into the joint -------------------------------
def _norm(item: str) -> str:
    return re.sub(r"\s+", " ", item.strip().lower()).rstrip(".")


def aggregate(verdicts: list[dict]) -> dict:
    """Fold an ensemble of verdicts into the joint - meaning lives in the joint, never one channel.

    Free-text ``lost`` / ``added`` items are unioned with a SUPPORT COUNT (how many independent
    judges raised each, after light normalisation): an item >= 2 judges surfaced is high-confidence
    consensus, the rest is the tail (surfaced, not dropped). The booleans get a real agreement
    number (the fraction of the ensemble that sided with the majority); the scalar ``agreement`` is
    their mean. Brittle exact-match Jaccard on free text is deliberately NOT the agreement metric -
    that is the void meter's error one level up.
    """
    n = len(verdicts)
    if n == 0:
        return {"n": 0, "lost": [], "added": [], "structured": None, "recurses": None,
                "structured_agreement": 0.0, "recurses_agreement": 0.0, "agreement": 0.0,
                "justifications": []}

    def _union(key: str) -> list[dict]:
        counts: dict[str, int] = {}
        display: dict[str, str] = {}
        for v in verdicts:
            seen: set[str] = set()
            for item in v.get(key, []) or []:
                kk = _norm(item)
                if not kk or kk in seen:
                    continue
                seen.add(kk)
                counts[kk] = counts.get(kk, 0) + 1
                display.setdefault(kk, item.strip())
        return [{"item": display[k], "support": c}
                for k, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]

    def _bool_majority(key: str):
        votes = [bool(v.get(key)) for v in verdicts if isinstance(v.get(key), bool)]
        if not votes:
            return None, 0.0
        trues = sum(votes)
        majority = (trues * 2) >= len(votes)
        agree = (trues if majority else len(votes) - trues) / len(votes)
        return majority, round(agree, 4)

    structured, s_agree = _bool_majority("structured")
    recurses, r_agree = _bool_majority("recurses")
    return {
        "n": n,
        "lost": _union("lost"),
        "added": _union("added"),
        "structured": structured,
        "structured_agreement": s_agree,
        "recurses": recurses,
        "recurses_agreement": r_agree,
        "agreement": round((s_agree + r_agree) / 2, 4),
        "justifications": [v.get("justification", "") for v in verdicts],
    }


# --- the faithfulness gate: the meter's own faithfulness, before it gates anything ----------------
# Conservative defaults behind a pluggable socket (the author's directive: good enough to progress,
# the seam left open). F1-adjacent - a tuned policy drops in without a rewrite.
GATE_DEFAULTS = {"calibration": 0.75, "agreement": 0.50}


def gate_policy(override: dict | None = None) -> dict:
    """The faithfulness-gate thresholds - the pluggable policy (conservative defaults)."""
    p = dict(GATE_DEFAULTS)
    if override:
        p.update(override)
    return p


def _content_toks(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in _STOP}


def plant_caught(plant: str, added: list[str], min_overlap: int = 2) -> bool:
    """Did the meter's ``added`` name the specific planted falsehood?

    This token check is legitimate where the void meter's was NOT: it does not judge fidelity
    (faithful paraphrases share few words - exactly what broke the proxy). It checks only that the
    adjudicator's OWN stated finding mentions the plant WE inserted - matching free text against a
    known string we control. A floor; the real semantic catch is the meter surfacing it at all.
    """
    if not added:
        return False
    ptoks = _content_toks(plant)
    if not ptoks:
        return bool(added)
    joined = _content_toks(" ".join(added))
    return len(ptoks & joined) >= min(min_overlap, len(ptoks))


def expectation_met(label: str, agg: dict, plant: str = "") -> bool:
    """Map a known calibration label to a predicate over the meter's RAW SIGNALS.

    The meter never emits a fate (FORK-FATES is deferred), so the harness holds the ground truth and
    checks the signals: a faithful pair must show no confabulation and ~no loss; a good partial must
    lose something real, structured, and recursing, while inventing nothing; a confabulated pair
    must surface invented content in ``added`` - and, when a plant is named, must surface THAT.

    An empty ensemble (n == 0) meets NO expectation: absence of data is not evidence of faithfulness.
    """
    if agg.get("n", 0) < 1:
        return False
    lost = agg.get("lost", []) or []
    added = agg.get("added", []) or []
    lost_n, added_n = len(lost), len(added)
    if label == "faithful":
        return added_n == 0 and lost_n <= 1
    if label == "partial":
        return (lost_n >= 1 and added_n == 0
                and bool(agg.get("structured")) and bool(agg.get("recurses")))
    if label == "confabulated":
        if added_n < 1:
            return False
        if plant:
            return plant_caught(plant, [x["item"] for x in added])
        return True
    raise ValueError(f"unknown calibration label {label!r}; "
                     "expected faithful | partial | confabulated")


def faithfulness_gate(items: list[dict], policy=gate_policy, override: dict | None = None) -> dict:
    """Score the meter itself over the calibration results.

    Each item: ``{"label": faithful|partial|confabulated, "agg": <aggregated verdict>,
    "plant": <optional string>, "id": <optional>}``. ``passed`` requires the calibration agreement
    threshold AND the ensemble-agreement threshold AND every planted ghost caught - and at least one
    plant must exist (a meter never tried against a deliberate falsehood cannot be trusted).
    """
    p = policy(override)
    per: list[dict] = []
    planted_total = planted_caught_n = 0
    for it in items:
        agg = it["agg"]
        met = expectation_met(it["label"], agg, it.get("plant", ""))
        is_plant = bool(it.get("plant"))
        if is_plant:
            planted_total += 1
            planted_caught_n += int(met)
        per.append({"id": it.get("id", ""), "label": it["label"], "met": met,
                    "is_plant": is_plant, "agreement": agg.get("agreement", 0.0),
                    "n": agg.get("n", 0)})
    n = len(items)
    cal = round(sum(1 for r in per if r["met"]) / n, 4) if n else 0.0
    mean_agree = round(sum(r["agreement"] for r in per) / n, 4) if n else 0.0
    all_plants = planted_total >= 1 and planted_caught_n == planted_total
    passed = bool(cal >= p["calibration"] and mean_agree >= p["agreement"] and all_plants)
    return {
        "passed": passed,
        "calibration_score": cal,
        "calibration_threshold": p["calibration"],
        "mean_agreement": mean_agree,
        "agreement_threshold": p["agreement"],
        "planted_caught": planted_caught_n,
        "planted_total": planted_total,
        "all_plants_caught": all_plants,
        "n": n,
        "per_item": per,
    }


# --- telemetry ------------------------------------------------------------------------------------
def _telemetry():
    try:
        from laplace.engine import telemetry  # type: ignore
        return telemetry
    except Exception:
        sys.path.insert(0, str(_REPO / "src"))
        from laplace.engine import telemetry  # type: ignore
        return telemetry


def _bank_adjudication(agg: dict, target: str, reason: str = "") -> None:
    try:
        tel = _telemetry()
        tel.adjudication(
            target=str(target), n=agg.get("n", 0),
            lost=len(agg.get("lost", [])), added=len(agg.get("added", [])),
            structured=agg.get("structured"), recurses=agg.get("recurses"),
            agreement=agg.get("agreement"), reason=reason,
        )
    except Exception as e:
        print(f"(adjudication telemetry not logged: {e})", file=sys.stderr)


def _derive():
    """The F14 codebook module - the DERIVED vocabulary that reads a fate off the raw signals.

    Sibling script; imported not re-implemented, so the stamp maps through the SAME predicates the
    derivation self-gated (builder != judge, one carving). Absent/void codebook -> no stampable map.
    """
    sys.path.insert(0, str(_HERE.parent))
    import derive_fates  # type: ignore
    return derive_fates


def stamp_fate(agg: dict, target: str = "", cycle: int = 0, do_log: bool = True) -> dict:
    """Map an aggregate's joint signals through the codebook and STAMP a reconstruction fate.

    The meter still emits no fate of its own - this is the DOWNSTREAM read: the F14 codebook's
    predicates over the consensus signal vector ``(n_lost, n_added, structured, recurses)`` name the
    fate, and the call is banked as a reconstruction outcome (``caller="adjudicator-sealed"``,
    ``reason="codebook:<version>"``) with the ensemble ``agreement`` as the mechanical confidence.
    A signal that lands in a CANDIDATE cell (enriched) - or in no cell - is not stampable: the call
    is still banked, but WITHOUT a fate, the way history accrues ahead of a settled verdict. Additive
    to ``aggregate``: this reads the same joint, it does not disturb the raw-signal bank.
    """
    df = _derive()
    sig = df.signal_vector(agg)
    cb = df.load_codebook()
    version = cb.get("version", "unknown") if cb else "absent"
    fates = cb["fates"] if cb else {}
    fate = df.classify(sig, fates) if fates else None   # candidates excluded -> not stampable
    result = {"signal": sig, "fate": fate, "version": version,
              "agreement": agg.get("agreement", 0.0)}
    if do_log:
        try:
            tel = _telemetry()
            tel.reconstruction(fate=fate, target=str(target) or "", caller="adjudicator-sealed",
                               cycle=cycle, similarity=agg.get("agreement"),
                               reason=f"codebook:{version}")
        except Exception as e:
            print(f"(stamp telemetry not logged: {e})", file=sys.stderr)
    return result


def _bank_gate(report: dict, target: str = "faithfulness-gate") -> None:
    try:
        tel = _telemetry()
        tel.adjudication(
            target=target, n=report.get("n", 0),
            faithfulness=report.get("calibration_score"),
            agreement=report.get("mean_agreement"), passed=report.get("passed"),
            reason=f"planted {report.get('planted_caught')}/{report.get('planted_total')}",
        )
    except Exception as e:
        print(f"(gate telemetry not logged: {e})", file=sys.stderr)


# --- CLI ------------------------------------------------------------------------------------------
# Flags that take a value (so the value is not mistaken for a positional - matters for the variadic
# `aggregate <v1.json> <v2.json> ...`, where a naive flag-strip would swallow `--target X`'s X).
_VALUE_FLAGS = {"--out", "--target", "--cycle"}


def _opt(argv, flag, default=None):
    return argv[argv.index(flag) + 1] if flag in argv else default


def _positional(argv) -> list[str]:
    """The positional args, with bare flags AND value-flag pairs removed."""
    out, skip = [], False
    for a in argv:
        if skip:
            skip = False
            continue
        if a in _VALUE_FLAGS:
            skip = True
            continue
        if a.startswith("--"):
            continue
        out.append(a)
    return out


def run_gate(cdir: Path) -> dict:
    """Read a calibration dir (one subdir per item, each with expected.json + verdict *.json),
    aggregate each item's ensemble, and score the meter."""
    items: list[dict] = []
    for sub in sorted(cdir.iterdir()):
        exp = sub / "expected.json"
        if not (sub.is_dir() and exp.exists()):
            continue
        meta = json.loads(exp.read_text(encoding="utf-8"))
        verdicts: list[dict] = []
        for p in sorted(sub.glob("*.json")):
            if p.name == "expected.json":
                continue
            try:
                v = parse_verdict(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not validate_verdict(v):
                verdicts.append(v)
        items.append({"id": sub.name, "label": meta["label"],
                      "plant": meta.get("plant", ""), "agg": aggregate(verdicts)})
    return faithfulness_gate(items)


def main(argv):
    args = _positional(argv)
    if not args:
        print(__doc__)
        return 2
    cmd = args[0]

    if cmd == "schema":
        print(json.dumps(VERDICT_SCHEMA, indent=2))
        return 0

    if cmd == "brief":
        if len(args) < 3:
            print(__doc__)
            return 2
        original = Path(args[1]).read_text(encoding="utf-8", errors="replace")
        ghost = Path(args[2]).read_text(encoding="utf-8", errors="replace")
        out = _opt(argv, "--out", str(Path(args[1]).with_name("adjudication_brief.md")))
        Path(out).write_text(build_brief(original, ghost), encoding="utf-8")
        print(f"# Sealed adjudication brief -> {out}")
        print("Hand it to N model/temp-diverse SEALED agents; save each verdict JSON; then:")
        print(f"  python {Path(__file__).name} aggregate v1.json v2.json ... --target <id>")
        return 0

    if cmd == "aggregate":
        vfiles = args[1:]
        if not vfiles:
            print(__doc__)
            return 2
        verdicts = []
        for f in vfiles:
            v = parse_verdict(Path(f).read_text(encoding="utf-8", errors="replace"))
            errs = validate_verdict(v)
            if errs:
                print(f"invalid verdict {f}: {errs}", file=sys.stderr)
                return 2
            verdicts.append(v)
        agg = aggregate(verdicts)
        target = _opt(argv, "--target", "")
        out = _opt(argv, "--out")
        if out:
            Path(out).write_text(json.dumps(agg, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"# Sealed adjudication (ensemble of {agg['n']}): {target or '(unnamed)'}")
        print("*" * 50)
        print(f"lost ({len(agg['lost'])}):  " +
              (", ".join(f"{x['item']} [{x['support']}]" for x in agg["lost"]) or "(none)"))
        print(f"added ({len(agg['added'])}):  " +
              (", ".join(f"{x['item']} [{x['support']}]" for x in agg["added"]) or "(none)"))
        print(f"structured: {agg['structured']} (agree {agg['structured_agreement']})    "
              f"recurses: {agg['recurses']} (agree {agg['recurses_agreement']})")
        print(f"ensemble agreement: {agg['agreement']}")
        if out:
            print(f"consensus -> {out}")
        if "--no-log" not in argv:
            _bank_adjudication(agg, target or "(unnamed)")
        return 0

    if cmd == "gate":
        if len(args) < 2:
            print(__doc__)
            return 2
        cdir = Path(args[1])
        if not cdir.exists():
            print(f"calibration dir not found: {cdir}", file=sys.stderr)
            return 2
        report = run_gate(cdir)
        out = _opt(argv, "--out")
        if out:
            Path(out).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        verdict = "PASS - the meter is faithful, the scalar gate is un-voided" if report["passed"] \
            else "FAIL - the meter is NOT yet trustworthy; do not let it gate"
        print(f"# Faithfulness gate: {verdict}")
        print("*" * 50)
        print(f"calibration: {report['calibration_score']} (>= {report['calibration_threshold']})    "
              f"agreement: {report['mean_agreement']} (>= {report['agreement_threshold']})")
        print(f"planted ghosts caught: {report['planted_caught']}/{report['planted_total']}")
        for r in report["per_item"]:
            flag = "PLANT" if r["is_plant"] else r["label"]
            print(f"  [{'ok ' if r['met'] else 'MISS'}] {r['id']:<24} {flag:<13} "
                  f"agree={r['agreement']} n={r['n']}")
        if "--no-log" not in argv:
            _bank_gate(report)
        return 0 if report["passed"] else 1

    if cmd == "stamp":
        vfiles = args[1:]
        if not vfiles:
            print(__doc__)
            return 2
        verdicts = []
        for f in vfiles:
            v = parse_verdict(Path(f).read_text(encoding="utf-8", errors="replace"))
            errs = validate_verdict(v)
            if errs:
                print(f"invalid verdict {f}: {errs}", file=sys.stderr)
                return 2
            verdicts.append(v)
        agg = aggregate(verdicts)
        target = _opt(argv, "--target", "")
        cycle = int(_opt(argv, "--cycle", "0"))
        res = stamp_fate(agg, target=target or "(unnamed)", cycle=cycle,
                         do_log="--no-log" not in argv)
        print(f"# Codebook stamp ({res['version']}): {target or '(unnamed)'}")
        print("*" * 50)
        print(f"signal: {res['signal']}")
        print(f"fate:   {res['fate'] or '(unclassified / candidate - not stamped)'}    "
              f"agreement: {res['agreement']}")
        return 0

    print(f"unknown command {cmd!r}", file=sys.stderr)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
