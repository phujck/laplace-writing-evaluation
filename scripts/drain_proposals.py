"""Drain the wire-proposal frontier: the one operator mechanically, a cheap jury on the residual.

Mechanically recoverable by construction (his constraint, 2026-06-13): every decision sinks
through embed_router.bank_verdicts into .wire_verdicts.jsonl (the one ledger), and
.learned_keywords.json is rebuilt as a PURE PROJECTION of that ledger - the applied wire-state is
a render of the recoverable trace, never a primary store. Re-runnable; idempotent on the frontier.

  python scripts/drain_proposals.py mechanical
      gate the frontier by the banked route coefficient, bank the confident wire/noise (no model),
      write .escalate_briefs.json (the ambiguous middle, content-free) for the jury.

  python scripts/drain_proposals.py bank-jury <verdicts.json>
      bank the jury's verdicts on the escalate band, then rebuild the index from the ledger.

  python scripts/drain_proposals.py verify
      prove recoverability: rebuild learned_keywords from the ledger and diff against the on-disk
      index (must be identical).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from laplace.engine import conceptric  # noqa: E402
from laplace.representation import embed_router as er  # noqa: E402

ESCALATE_FILE = ROOT / ".escalate_briefs.json"


def cmd_mechanical(*, net=None) -> int:
    net = conceptric.load_network(ROOT) if net is None else net
    before = len(er.proposal_pairs(ROOT))
    mv = er.mechanical_verdicts(ROOT, net)
    rep = er.bank_verdicts(ROOT, mv)                          # the one sink
    remaining = er.proposal_pairs(ROOT)
    cached = []
    if ESCALATE_FILE.is_file():
        try:
            cached = json.loads(ESCALATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            cached = []
    briefs, brief_rep = er.audit_briefs_incremental(ROOT, net, cached, pairs=remaining)
    ESCALATE_FILE.write_text(json.dumps(briefs, ensure_ascii=False, indent=1), encoding="utf-8")
    learned = er.rebuild_learned_keywords(ROOT)              # render the index from the ledger
    print(f"frontier {before} -> mechanical: wire {rep['wire']}, noise {rep['noise']} "
          f"({rep['wire']+rep['noise']}/{before} = {100*(rep['wire']+rep['noise'])//max(before,1)}%)")
    print(f"remaining to jury: {rep['n_remaining']}  -> .escalate_briefs.json ({len(briefs)})")
    print("jury briefs incremental: "
          f"{brief_rep['reused']} reused, {brief_rep['rebuilt']} rebuilt, "
          f"{brief_rep['dropped']} dropped")
    print(f"learned_keywords rebuilt from ledger: {len(learned)} nodes")
    return 0


def cmd_bank_jury(path: str) -> int:
    verdicts = json.loads(Path(path).read_text(encoding="utf-8"))
    verdicts = [v for v in verdicts if v.get("verdict") in ("wire", "grit", "noise")]
    for v in verdicts:
        v.setdefault("method", "jury")
    rep = er.bank_verdicts(ROOT, verdicts)
    learned = er.rebuild_learned_keywords(ROOT)
    print(f"jury banked: wire {rep['wire']}, grit {rep['grit']}, noise {rep['noise']}; "
          f"frontier remaining {rep['n_remaining']}")
    print(f"learned_keywords rebuilt from ledger: {len(learned)} nodes")
    if ESCALATE_FILE.is_file():
        ESCALATE_FILE.unlink()
    return 0


def cmd_regrade_jury() -> int:
    """Rebuild enriched (local-frame) briefs for the pairs a previous JURY decided, so they can be
    re-judged against the reconstruction instead of the flat handle. bank-jury then supersedes."""
    net = conceptric.load_network(ROOT)
    seen, pairs = set(), []
    led = ROOT / er.VERDICTS_FILE
    if led.is_file():
        for ln in led.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                v = json.loads(ln)
            except json.JSONDecodeError:
                continue
            key = (v.get("query", ""), v.get("id", ""))
            if v.get("method") == "jury" and key not in seen and v.get("id"):
                seen.add(key)
                pairs.append({"query": key[0], "id": key[1]})
    briefs = er.audit_briefs(ROOT, net, pairs=pairs)
    ESCALATE_FILE.write_text(json.dumps(briefs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"prior jury pairs: {len(pairs)} -> enriched briefs in .escalate_briefs.json "
          f"(each carries ancestry + neighbours)")
    return 0


def cmd_verify() -> int:
    """Recoverability proof: the on-disk index must equal a fresh rebuild from the ledger."""
    on_disk = {}
    p = ROOT / er.LEARNED_KEYWORDS_FILE
    if p.is_file():
        on_disk = json.loads(p.read_text(encoding="utf-8"))
    # rebuild writes the file, so snapshot first, then compare to the returned map
    rebuilt = er.rebuild_learned_keywords(ROOT)
    same = on_disk == rebuilt
    print(f"on-disk learned: {len(on_disk)} nodes | rebuilt-from-ledger: {len(rebuilt)} nodes")
    print(f"RECOVERABLE: {'YES - index is a pure projection of the ledger' if same else 'NO - drift!'}")
    return 0 if same else 1


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "mechanical"
    if mode == "mechanical":
        raise SystemExit(cmd_mechanical())
    if mode == "bank-jury":
        raise SystemExit(cmd_bank_jury(sys.argv[2]))
    if mode == "regrade-jury":
        raise SystemExit(cmd_regrade_jury())
    if mode == "verify":
        raise SystemExit(cmd_verify())
    print(f"unknown mode {mode!r}")
    raise SystemExit(2)
