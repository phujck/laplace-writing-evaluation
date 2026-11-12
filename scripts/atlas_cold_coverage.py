#!/usr/bin/env python3
"""atlas_cold_coverage.py - a COLD Codex session measures the atlas's reach.

His goal, 2026-09-14: "use cold codex sessions to test the atlas coverage." The law it serves: judge
by a random draw succeeding, never by a named check (F5's one good stopping rule: a fresh session
enters from the entry and reaches any record by bounded descent with no supplied handle).

The instrument draws K node ids at random from the latest atlas snapshot (text, unsealed), hands a
fresh `codex exec --ephemeral` session ONLY the atlas package's entry (atlas/README.md as the node,
by exact reconstruction through scripts/dispatch_codex.py) and the ids, and asks it to recover each
node's exact bytes through the atlas's own read API, reporting the sha256 it computed, the reads it
made, and whether it ever listed a directory under atlas/stores. The instrument then verifies every
returned hash against the snapshot's content_hash itself - the session never sees the hashes. The
row it prints is the coverage: reached/K by exact hash, reads, enumerations. Efficiency rides the
same row: reads per node, wall seconds.

  /usr/bin/python3 scripts/atlas_cold_coverage.py [--k 8] [--seed 20260914] [--run] [--timeout 900]
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "atlas" / "stores" / "snapshots"


def card_registry():
    # This repository instrument binds the standalone package; the package itself
    # through the one bridge (tests/test_atlas_seal.py: scripts never import atlas.* directly)
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from laplace.representation.atlas_bridge import compute_cards_registry as compute_registry
    return compute_registry()


def latest_snapshot() -> tuple[str, list[dict]]:
    cands = sorted(SNAPSHOTS.glob("*/nodes.jsonl"), key=lambda p: p.stat().st_mtime)
    if not cands:
        raise SystemExit("no atlas snapshot under atlas/stores/snapshots")
    p = cands[-1]
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return p.parent.name, rows


def draw(rows: list[dict], k: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    pool = [r for r in rows if str(r.get("is_text")) == "True" and not r.get("sealed") and r.get("content_hash")]
    rng.shuffle(pool)
    return pool[:k]


# OpenAI's strict output format (the codex --output-schema door) requires additionalProperties=false on
# every object and every property listed as required; a schema without them is refused in 4 seconds.
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "entry_used": {"type": "string", "description": "the command or API you entered the atlas through"},
        "nodes": {"type": "array", "items": {"type": "object", "additionalProperties": False, "properties": {
            "node_id": {"type": "string"},
            "reached": {"type": "boolean"},
            "sha256_of_bytes": {"type": "string", "description": "sha256:<hex> of the exact bytes you recovered through the atlas API, or empty"},
            "method": {"type": "string", "description": "the exact call or command that returned the bytes"},
            "reads": {"type": "integer", "description": "files or store objects you opened to reach this node"}},
            "required": ["node_id", "reached", "sha256_of_bytes", "method", "reads"]}},
        "reads_total": {"type": "integer"},
        "enumerated_store_dirs": {"type": "boolean", "description": "true if you listed any directory under atlas/stores"},
        "blockers": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["entry_used", "nodes", "reads_total", "enumerated_store_dirs", "blockers"],
}


VERBS_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "entry_used": {"type": "string"},
        "verbs": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "card_id": {"type": "string"}, "card_reached": {"type": "boolean"},
                "card_command": {"type": "string"}, "test_path": {"type": "string"},
                "test_reached": {"type": "boolean"}, "test_command": {"type": "string"},
                "exit_code": {"type": ["integer", "null"]}, "test_output": {"type": "string"},
                "reads": {"type": "integer"}, "issue": {"type": "string"},
            },
            "required": ["card_id", "card_reached", "card_command", "test_path", "test_reached",
                         "test_command", "exit_code", "test_output", "reads", "issue"],
        }},
        "reads_total": {"type": "integer"}, "enumerated_store_dirs": {"type": "boolean"},
        "blockers": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["entry_used", "verbs", "reads_total", "enumerated_store_dirs", "blockers"],
}


def verbs_packet(k: int, seed: int) -> dict:
    registry = card_registry()
    pool = registry["verbs"]
    if not 1 <= k <= len(pool):
        raise ValueError(f"VERB-DRAW-SIZE: k must be between 1 and {len(pool)}")
    chosen = random.Random(seed).sample(pool, k)
    ids = [card["id"] for card in chosen]
    goal = (
        "COLD VERB COVERAGE PROBE OF THE ATLAS. Reconstruct src/atlas/entry.py through "
        "/usr/bin/python3 scripts/reconstruct_node.py src/atlas/entry.py --kind repository-file "
        "--grade 1 --content-budget 12000, then enter with "
        "PYTHONPATH=src /usr/bin/python3 -m atlas.entry --json.\n\n"
        "For EACH card id below, reach its full card through the entry, follow its source handle, "
        "reach the contract test file named by the card, and run that test file with "
        "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /usr/bin/python3 -m pytest -q -p no:cacheprovider "
        "<test_path>. Record the exact card command, test path, test command, exit code, verbatim "
        "test output, and reads. A missing test is CARD-TEST-MISSING against the card's source owner; "
        "report it and do not substitute a test. Preserve test_scope: a called operation's test is "
        "not proof of the whole command. Do not execute the verb itself.\n\n"
        "Do not modify repository source, commit, run deposit or close, enumerate or write atlas/stores, "
        "or write engine fold files. Tests may create isolated fixtures. Do not launch another agent. "
        "If a test would cross these limits, report TEST-FENCE-REFUSED and leave exit_code null. "
        "Use /usr/bin/python3 for every Python command, including card descents.\n\n"
        "CARD IDS:\n" + "\n".join("- " + cid for cid in ids) + "\n\n"
        "Answer ONLY with the JSON the output schema demands."
    )
    return {"probe": "atlas-cold-verbs", "mode": "verbs", "seed": seed, "k": k,
            "population": len(pool), "ids": ids, "goal": goal, "schema": VERBS_SCHEMA,
            "issues": registry["issues"]}


def measure_verbs(ans: dict, ids: list[str]) -> dict:
    """Validate a complete strict return before counting any reported test result."""
    import jsonschema
    jsonschema.validate(ans, VERBS_SCHEMA)
    rows = ans["verbs"]
    returned = [row["card_id"] for row in rows]
    if len(returned) != len(ids) or set(returned) != set(ids):
        raise ValueError("VERB-RETURN-IDS: missing, duplicate or unrequested card ids")
    cards = {c["id"]: c for c in card_registry()["verbs"]}
    passed = sum(bool(row["card_reached"] and row["test_reached"] and row["test_output"]
                      and row["exit_code"] == 0 and cards[row["card_id"]]["test"]
                      and row["test_path"] == cards[row["card_id"]]["test"] and not row["issue"])
                 for row in rows)
    return {"status": "REPORTED", "tests_reported_passed": passed, "of": len(ids),
            "enumerated_store_dirs": ans["enumerated_store_dirs"], "per_verb": rows,
            "reads_total": ans["reads_total"], "blockers": ans["blockers"],
            "entry_used": ans["entry_used"],
            "law": "strict complete cold return; test outcomes are session reports, not independent certification"}


def goal_text(snapshot_id: str, nodes: list[dict]) -> str:
    ids = "\n".join(f"- {n['node_id']}" for n in nodes)
    return (
        "COLD COVERAGE PROBE OF THE ATLAS. You are a fresh session. You may read the atlas package under atlas/ "
        "(its README, DESIGN_S1.md, src/atlas, and the tools under src/atlas/tools) to learn its read API, and "
        "you may run /usr/bin/python3 with PYTHONPATH=src. You must NOT list or glob any directory under "
        "atlas/stores/ - reaching a node by enumerating the store is a failure, report it honestly. Do not modify "
        "anything.\n\n"
        f"The current snapshot id is {snapshot_id}. For EACH node id below, recover the node's exact bytes through the "
        "atlas's own API (snapshot bundle, store, blueprint reconstruction - whatever the package provides), compute "
        "sha256 of those exact bytes, and record the exact call you used and how many files/objects you opened. "
        "If you cannot reach a node without enumerating, mark reached=false and say why in blockers.\n\n"
        f"NODE IDS:\n{ids}\n\n"
        "Answer ONLY with the JSON the output schema demands."
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=8)
    ap.add_argument("--seed", type=int, default=20260914)
    ap.add_argument("--mode", choices=("nodes", "verbs"), default="nodes")
    execution = ap.add_mutually_exclusive_group()
    execution.add_argument("--run", action="store_true")
    execution.add_argument("--compile-only", action="store_true")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--out-dir", default=".dispatch")
    a = ap.parse_args(argv)
    if a.mode == "verbs":
        try:
            packet = verbs_packet(a.k, a.seed)
        except ValueError as exc:
            print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
            return 1
        sid, nodes, want = None, [], {}
    else:
        sid, rows = latest_snapshot()
        nodes = draw(rows, a.k, a.seed)
        want = {n["node_id"]: n["content_hash"] for n in nodes}
        packet = {"probe": "atlas-cold-coverage", "mode": "nodes", "snapshot": sid,
                  "seed": a.seed, "k": len(nodes), "goal": goal_text(sid, nodes), "schema": SCHEMA}
    if a.compile_only:
        print(json.dumps({"status": "COMPILED", **packet}, indent=1))
        return 0
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    work = ROOT / a.out_dir / f"{stamp}-cold-coverage-k{a.k}-s{a.seed}"
    work.mkdir(parents=True, exist_ok=True)
    (work / "schema.json").write_text(json.dumps(packet["schema"], indent=1), encoding="utf-8")
    (work / "goal.md").write_text(packet["goal"], encoding="utf-8")
    (work / "draw.json").write_text(json.dumps(packet, indent=1), encoding="utf-8")
    cmd = [sys.executable, str(ROOT / "scripts" / "dispatch_codex.py"), "atlas/README.md",
           f"cold coverage probe k={a.k} seed={a.seed}", "--goal-file", str(work / "goal.md"),
           "--output-schema", str(work / "schema.json"), "--sandbox", ("workspace-write" if getattr(a, "mode", "nodes") == "verbs" else "read-only"), "--out-dir", a.out_dir,
           "--timeout", str(a.timeout)] + (["--run"] if a.run else [])
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=a.timeout + 60)
    (work / "dispatch.log").write_text(proc.stdout + "\n" + proc.stderr, encoding="utf-8")
    raw = proc.stdout
    try:
        row = json.loads(raw[raw.find("{"):raw.rfind("}") + 1])
    except Exception:
        print(json.dumps({"status": "DISPATCH-FAILED", "stdout_tail": raw[-800:], "stderr_tail": proc.stderr[-800:]}, indent=1))
        return 2
    result = {"probe": "atlas-cold-coverage", "snapshot": sid, "k": a.k, "seed": a.seed, "dispatch": row.get("id"),
              "status": row.get("status"), "seconds": round(time.time() - t0, 1), "work": str(work.relative_to(ROOT))}
    if not a.run or row.get("status") != "RETURNED":
        print(json.dumps(result, indent=1)); return 0 if not a.run else 1
    ret = ROOT / row["return_path"]
    text = ret.read_text(encoding="utf-8")
    try:
        ans = json.loads(text[text.find("{"):text.rfind("}") + 1])
    except Exception:
        result.update({"status": "RETURN-NOT-JSON", "return_head": text[:400]}); print(json.dumps(result, indent=1)); return 1
    verified = 0; per = []
    if a.mode == "verbs":
        try:
            result.update(measure_verbs(ans, packet["ids"]))
        except (ValueError, __import__("jsonschema").ValidationError) as exc:
            result.update({"status": "VERB-RETURN-REFUSED", "reason": str(exc)})
            print(json.dumps(result, indent=1))
            return 1
        print(json.dumps(result, indent=1))
        return 0
    for n in ans.get("nodes", []):
        nid = n.get("node_id"); ok = bool(n.get("reached")) and n.get("sha256_of_bytes") == want.get(nid)
        verified += ok
        per.append({"node_id": nid, "reached_claimed": n.get("reached"), "hash_verified": ok, "reads": n.get("reads"), "method": str(n.get("method", ""))[:120]})
    result.update({"status": "MEASURED", "reached_by_hash": verified, "of": a.k, "reads_total": ans.get("reads_total"),
                   "enumerated_store_dirs": ans.get("enumerated_store_dirs"), "entry_used": ans.get("entry_used"),
                   "blockers": ans.get("blockers"), "per_node": per,
                   "law": "coverage = nodes whose exact bytes came back through the API with the snapshot's content_hash; the session never saw the hashes"})
    (work / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
