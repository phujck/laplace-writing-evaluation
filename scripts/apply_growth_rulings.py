#!/usr/bin/env python3
"""Replay the growth adjudicator's rulings back onto the conceptric they judged.

The deslop gate only surfaces; the JUDGE leg rules KEEP/KILL/REWRITE and banks each
call as a ``kind:"growth"`` verdict. Those rulings are the source of truth — but a
ruling that never reaches the manuscript is a decision made and thrown away. This is
the enrich step that lands them: it reads the banked growth rulings for one corpus and
edits the corpus's compiled conceptric (``manuscript/conceptric_v1.json``) so the
adjudicated text IS the stored text.

The conceptric's node essence lives in its ``label`` field — the same field
:mod:`scripts.pour_conceptric` reads as ``essence`` when it pours the ledger — so a
ruling touches ``label`` and nothing else. The graph is never cut:

  * **REWRITE** (carries ``rewrite_text``): the node's ``label`` becomes the ruling's
    full replacement line. Reported old→new.
  * **KILL** (none banked today; built anyway): the node's ``label`` becomes a
    tombstone ``"(killed by <ruling_id>)"``. The NODE AND ITS EDGES SURVIVE — a killed
    essence is blanked, never dropped, so every dependent below it still reconstructs.
  * **KEEP**: a no-op, counted. The text stood; nothing to write.

REPLAYABLE and IDEMPOTENT. Everything is derived from the banked ledger — the script
takes no free-text input. A second run changes nothing: a REWRITE whose ``label``
already equals ``rewrite_text``, or a KILL whose ``label`` is already its tombstone, is
counted as an unchanged no-op. ``--dry-run`` prints the same report and writes nothing.

The corpus filter is the decision subject: a growth ruling belongs to ``<name>`` when
its ``decision.subject`` leads with ``conceptric[<name>]:``. The node id is the segment
between that prefix and the `` :: `` essence separator — it keys the conceptric ``nodes``
list directly (verified against eigenengine's 23 banked rulings).

Run:
  python3 scripts/apply_growth_rulings.py \\
      --conceptric eigenengine/manuscript/conceptric_v1.json --corpus eigenengine
  python3 scripts/apply_growth_rulings.py \\
      --conceptric eigenengine/manuscript/conceptric_v1.json --corpus eigenengine --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from laplace.engine import author_proxy  # noqa: E402

#: the conceptric field that carries a node's essence (what pour_conceptric reads).
ESSENCE_FIELD = "label"


def _subject_prefix(corpus: str) -> str:
    return f"conceptric[{corpus}]:"


def node_id_from_subject(subject: str, corpus: str) -> str | None:
    """The node id a growth ruling names, or ``None`` when the subject is not this
    corpus's. Subject shape: ``conceptric[<corpus>]:<node_id> :: <essence prefix>`` —
    the id is everything between the prefix and the `` :: `` separator (node ids may
    themselves carry colons, e.g. ``sec:abstract``, so we split on `` :: `` not ``:``)."""
    prefix = _subject_prefix(corpus)
    if not subject.startswith(prefix):
        return None
    rest = subject[len(prefix):]
    return rest.split(" :: ", 1)[0].strip() or None


def ruling_verb(row: dict) -> str | None:
    """KEEP / KILL / REWRITE from the ``ruling`` field (tolerant of a ``"KEEP: ..."``
    lead), or ``None`` when it is none of the three."""
    ruling = str(row.get("ruling", "")).strip().upper()
    for verb in ("KEEP", "KILL", "REWRITE"):
        if ruling == verb or ruling.startswith(verb):
            return verb
    return None


def growth_rulings_for_corpus(rulings: list[dict], corpus: str) -> list[dict]:
    """The banked growth rulings addressed to this corpus's conceptric, in ledger order.
    A row qualifies on ``kind=="growth"`` AND a ``decision.subject`` that leads with
    ``conceptric[<corpus>]:``."""
    prefix = _subject_prefix(corpus)
    out: list[dict] = []
    for row in rulings:
        if row.get("kind") != "growth":
            continue
        dec = row.get("decision")
        subject = dec.get("subject") if isinstance(dec, dict) else None
        if isinstance(subject, str) and subject.startswith(prefix):
            out.append(row)
    return out


def apply_rulings(concept: dict, rulings: list[dict], corpus: str) -> list[dict]:
    """Mutate ``concept`` in place per the banked rulings; return one action record per
    ruling considered. Action records carry ``{ruling_id, node, verb, status, ...}``
    where ``status`` is one of ``applied`` / ``unchanged`` / ``noop-keep`` /
    ``unresolved`` / ``skipped``. Idempotent: an already-satisfied REWRITE/KILL reports
    ``unchanged`` and writes nothing."""
    nodes = {n["id"]: n for n in concept.get("nodes", [])}
    actions: list[dict] = []
    for row in growth_rulings_for_corpus(rulings, corpus):
        rid = str(row.get("id", ""))
        subject = row["decision"]["subject"]
        nid = node_id_from_subject(subject, corpus)
        verb = ruling_verb(row)
        rec: dict = {"ruling_id": rid, "node": nid, "verb": verb}

        if verb is None:
            rec["status"] = "skipped"
            rec["reason"] = "ruling is not one of KEEP/KILL/REWRITE"
            actions.append(rec)
            continue
        if verb == "KEEP":
            rec["status"] = "noop-keep"
            actions.append(rec)
            continue

        node = nodes.get(nid) if nid else None
        if node is None:
            rec["status"] = "unresolved"
            rec["reason"] = f"node id {nid!r} keys no conceptric node"
            actions.append(rec)
            continue

        old = node.get(ESSENCE_FIELD, "")
        if verb == "REWRITE":
            new = row.get("rewrite_text")
            if not (isinstance(new, str) and new.strip()):
                rec["status"] = "skipped"
                rec["reason"] = "REWRITE ruling carries no rewrite_text"
                actions.append(rec)
                continue
        else:  # KILL
            new = f"(killed by {rid})"

        rec["old"] = old
        rec["new"] = new
        if old == new:
            rec["status"] = "unchanged"          # idempotent: already satisfied
        else:
            node[ESSENCE_FIELD] = new
            rec["status"] = "applied"
        actions.append(rec)
    return actions


def run(conceptric_path: Path, corpus: str, root: Path, dry_run: bool) -> dict:
    """Load the conceptric + the corpus's banked growth rulings, apply, and (unless
    ``dry_run``) write the conceptric back. Returns the report."""
    concept = json.loads(Path(conceptric_path).read_text(encoding="utf-8"))
    rulings = author_proxy.load_verdicts(root)
    actions = apply_rulings(concept, rulings, corpus)

    changed = any(a["status"] == "applied" for a in actions)
    if changed and not dry_run:
        Path(conceptric_path).write_text(
            json.dumps(concept, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    tally: dict[str, int] = {}
    for a in actions:
        tally[a["status"]] = tally.get(a["status"], 0) + 1
    return {
        "conceptric": str(conceptric_path),
        "corpus": corpus,
        "dry_run": dry_run,
        "wrote": bool(changed and not dry_run),
        "considered": len(actions),
        "tally": tally,
        "actions": actions,
    }


def _print_report(report: dict) -> None:
    mode = "DRY-RUN (no write)" if report["dry_run"] else (
        "wrote conceptric" if report["wrote"] else "no change (nothing to write)")
    print(f"apply_growth_rulings — corpus={report['corpus']} "
          f"considered={report['considered']} {mode}")
    print(f"  tally: {report['tally']}")
    for a in report["actions"]:
        if a["status"] in ("applied", "unchanged"):
            arrow = "->" if a["status"] == "applied" else "== (idempotent no-op)"
            print(f"  [{a['status']}] {a['verb']} {a['node']} ({a['ruling_id']})")
            print(f"      old: {str(a['old'])[:110]!r}")
            print(f"      new {arrow} {str(a['new'])[:110]!r}")
        elif a["status"] == "unresolved":
            print(f"  [unresolved] {a['verb']} {a['node']} ({a['ruling_id']}): {a['reason']}")
        elif a["status"] == "skipped":
            print(f"  [skipped] {a['node']} ({a['ruling_id']}): {a['reason']}")
    kept = report["tally"].get("noop-keep", 0)
    if kept:
        print(f"  ({kept} KEEP ruling(s) — text stood, no-op)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Replay banked growth rulings onto a corpus conceptric (enrich step).")
    ap.add_argument("--conceptric", required=True,
                    help="path to the corpus's manuscript/conceptric_v1.json")
    ap.add_argument("--corpus", required=True,
                    help="corpus name — matches decision.subject prefix conceptric[<name>]:")
    ap.add_argument("--root", default=str(ROOT),
                    help="repo root holding proxy_verdicts.jsonl (default: this repo)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the report; write nothing")
    args = ap.parse_args(argv)

    conceptric_path = Path(args.conceptric)
    if not conceptric_path.is_absolute():
        conceptric_path = Path(args.root).resolve() / conceptric_path
    report = run(conceptric_path, args.corpus, Path(args.root).resolve(), args.dry_run)
    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
