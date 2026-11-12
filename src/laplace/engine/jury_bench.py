"""jury_bench.py - N27, rung 0 of the waist ladder: the LOCAL JURY measured, not guessed.

The weld manufactured this benchmark for free: hundreds of real adjudication tasks (does this
verbatim quote, in its atom's context, exhibit this trait?) with banked Haiku verdicts as the
reference. This module replays a stratified sample against a LOCAL open-weight model (llama.cpp
server, OpenAI-compatible - tonight Qwen3-14B on the RX 6750 XT) and scores:

  * **agreement** with the incumbent jury on its accepts and refusals (NOT ground truth - the
    question is "can the local model do the job the cheap cloud jury currently does");
  * **discrimination** on trait-swapped CONTROLS - an accepted instance re-paired with a wrong
    trait should be refused; a judge that accepts everything fails here even with high raw
    agreement (always-accept is the cheap fraud this catches). Some swapped traits genuinely
    near-fit (the ring's axes overlap), so the control refuse-rate is a LOWER BOUND on
    discrimination - read it as such;
  * **latency** per verdict - the residency question is throughput as much as quality.

This number gates the house-machine spend (memory ``the-house-machine-residency``, readiness
gate 2 of 5). Mechanical throughout except the model under test; deterministic sampling (seeded,
no clock); the model is never told which rows are controls.
"""

from __future__ import annotations
from laplace.core.checkout import source_tree

import json
import random
import re
import time
import urllib.request
from pathlib import Path
from typing import Any

WELD_DIR = "archive/self_record/_weld"
BENCH_DIR = WELD_DIR + "/qwen_bench"
DEFAULT_URL = "http://127.0.0.1:8080"
_ATOM_CAP = 6000          # chars of atom context per task - fits the 8k window with headroom
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


# ---------------------------------------------------------------------------
# the task set - the weld's judged instances, re-paired with their gold verdicts
# ---------------------------------------------------------------------------

def load_judged(repo_root: Path | str) -> list[dict[str, Any]]:
    """Every welded instance that has a banked verdict, across both tranches:
    {trait, atom, quote, statement, gold: accept|refuse, tranche}."""
    from laplace.engine import value_weld
    repo_root = Path(repo_root)
    out: list[dict[str, Any]] = []
    for acc_name, vdir in (("gated_accepted.json", "judge_open"),
                           ("gated_accepted_dialogue.json", "judge")):
        acc_p = repo_root / WELD_DIR / acc_name
        jdir = repo_root / WELD_DIR / vdir
        if not acc_p.is_file() or not jdir.is_dir():
            continue
        acc = json.loads(acc_p.read_text(encoding="utf-8"))
        verdicts: list[dict[str, Any]] = []
        for f in sorted(jdir.glob("verdicts_*.jsonl")):
            verdicts.extend(value_weld.parse_proposals(
                f.read_text(encoding="utf-8", errors="replace")))
        by_key = {(v.get("trait"), v.get("atom")): v for v in verdicts}
        for p in acc:
            v = by_key.get((p["trait"], p["atom"]))
            if v is None:
                continue
            gold = "refuse" if str(v.get("verdict", "")).lower().startswith("refus") else "accept"
            out.append({"trait": p["trait"], "atom": p["atom"], "quote": p["quote"],
                        "statement": p.get("statement", ""), "gold": gold, "tranche": vdir,
                        "control": False})
    return out


def make_controls(instances: list[dict[str, Any]], n: int, seed: int = 11) -> list[dict[str, Any]]:
    """Trait-swapped negatives: a gold-ACCEPT instance re-paired with a different trait, gold
    becomes refuse. Deterministic (seeded). The swap may occasionally near-fit (axes overlap) -
    the refuse-rate is a lower bound, and the report says so."""
    rng = random.Random(seed)
    pool = [p for p in instances if p["gold"] == "accept"]
    traits = sorted({p["trait"] for p in instances})
    out: list[dict[str, Any]] = []
    for p in rng.sample(pool, min(n, len(pool))):
        others = [t for t in traits if t != p["trait"]]
        out.append({**p, "trait": rng.choice(others), "gold": "refuse", "control": True})
    return out


def sample_tasks(instances: list[dict[str, Any]], n_accepts: int, n_controls: int,
                 seed: int = 7) -> list[dict[str, Any]]:
    """The stratified sample: ALL gold-refusals (they are few and precious) + n seeded-random
    accepts + n trait-swapped controls, shuffled so order carries no signal."""
    rng = random.Random(seed)
    refusals = [p for p in instances if p["gold"] == "refuse"]
    accepts = [p for p in instances if p["gold"] == "accept"]
    picked = refusals + rng.sample(accepts, min(n_accepts, len(accepts)))
    picked = picked + make_controls(instances, n_controls, seed=seed + 4)
    rng.shuffle(picked)
    return picked


# ---------------------------------------------------------------------------
# the prompt - mirrors the sealed adjudicator's task, one instance per call
# ---------------------------------------------------------------------------

def prompt_for(repo_root: Path | str, task: dict[str, Any],
               meanings: dict[str, str] | None = None,
               floor: list[dict[str, Any]] | None = None) -> str:
    from laplace.engine import record_shard, value_weld
    repo_root = Path(repo_root)
    meanings = meanings if meanings is not None else {
        m["slug"]: m["meaning"] for m in value_weld.trait_menu(repo_root)}
    body = record_shard.reconstruct(repo_root, task["atom"], floor)[:_ATOM_CAP]
    return (
        "You are an adjudicator. Judge ONE question: does the quote below, read in its source "
        "text's context, show its WRITER genuinely exhibiting the trait as the meaning defines "
        "it? Topical mention, or the trait merely being discussed rather than enacted, means "
        "refuse. Be strict.\n\n"
        f"TRAIT: {task['trait']}\n"
        f"TRAIT MEANING: {meanings.get(task['trait'], '')}\n"
        f"QUOTE: {task['quote']}\n"
        "SOURCE TEXT:\n"
        f"{body}\n\n"
        'Answer with ONE JSON line only: {"verdict": "accept" or "refuse", "why": "<max 12 words>"}'
    )


# ---------------------------------------------------------------------------
# the model under test - llama.cpp's OpenAI face; verdicts parsed tolerantly
# ---------------------------------------------------------------------------

def call_jury(base_url: str, prompt: str, timeout: int = 240,
              max_tokens: int = 160) -> str:
    body = json.dumps({"model": "local", "temperature": 0, "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": prompt + " /no_think"}]})
    req = urllib.request.Request(base_url.rstrip("/") + "/v1/chat/completions",
                                 data=body.encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    return data["choices"][0]["message"]["content"]


def parse_verdict(text: str) -> str | None:
    """accept | refuse | None. Strips Qwen's think block, prefers a JSON verdict line, falls
    back to the first bare accept/refuse token."""
    text = _THINK_RE.sub("", text)
    for ln in text.splitlines():
        ln = ln.strip().strip("`").strip()
        if ln.startswith("{"):
            try:
                d = json.loads(ln)
                v = str(d.get("verdict", "")).lower()
                if v.startswith("accept"):
                    return "accept"
                if v.startswith("refus"):
                    return "refuse"
            except ValueError:
                pass
    m = re.search(r"\b(accept|refuse)\b", text, re.IGNORECASE)
    return m.group(1).lower() if m else None


# ---------------------------------------------------------------------------
# the run + the score
# ---------------------------------------------------------------------------

def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    real = [r for r in rows if not r["control"] and r["pred"] in ("accept", "refuse")]
    ctrl = [r for r in rows if r["control"] and r["pred"] in ("accept", "refuse")]
    unparsed = [r for r in rows if r["pred"] not in ("accept", "refuse")]
    acc_rows = [r for r in real if r["gold"] == "accept"]
    ref_rows = [r for r in real if r["gold"] == "refuse"]

    def rate(sel: list[dict[str, Any]]) -> float | None:
        return round(sum(1 for r in sel if r["pred"] == r["gold"]) / len(sel), 3) if sel else None

    lat = [r["ms"] for r in rows if r.get("ms")]
    return {
        "n_real": len(real), "n_controls": len(ctrl), "n_unparsed": len(unparsed),
        "agreement_overall": rate(real),
        "agreement_on_accepts": rate(acc_rows),
        "agreement_on_refusals": rate(ref_rows),
        "control_refuse_rate": rate(ctrl),       # lower bound on discrimination
        "local_refuse_rate_real": round(sum(1 for r in real if r["pred"] == "refuse")
                                        / len(real), 3) if real else None,
        "mean_latency_s": round(sum(lat) / len(lat) / 1000, 1) if lat else None,
        "p90_latency_s": round(sorted(lat)[int(0.9 * (len(lat) - 1))] / 1000, 1) if lat else None,
    }


def run_bench(repo_root: Path | str, base_url: str = DEFAULT_URL, n_accepts: int = 30,
              n_controls: int = 24, seed: int = 7) -> dict[str, Any]:
    from laplace.engine import record_shard, value_weld
    repo_root = Path(repo_root)
    tasks = sample_tasks(load_judged(repo_root), n_accepts, n_controls, seed=seed)
    meanings = {m["slug"]: m["meaning"] for m in value_weld.trait_menu(repo_root)}
    floor = record_shard.load_floor(repo_root)
    out_dir = repo_root / BENCH_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as fh:
        for i, t in enumerate(tasks):
            prompt = prompt_for(repo_root, t, meanings, floor)
            t0 = time.perf_counter()
            try:
                raw = call_jury(base_url, prompt)
                pred = parse_verdict(raw) or "unparsed"
            except Exception as exc:                       # noqa: BLE001 - a dead server is a result
                raw, pred = f"ERROR: {exc}", "error"
            ms = int((time.perf_counter() - t0) * 1000)
            row = {"i": i, "trait": t["trait"], "atom": t["atom"], "gold": t["gold"],
                   "control": t["control"], "tranche": t["tranche"], "pred": pred, "ms": ms,
                   "raw": _THINK_RE.sub("", raw)[:300]}
            rows.append(row)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            fh.flush()
    metrics = score(rows)
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main(argv: list[str]) -> int:
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    root = source_tree()
    url = argv[0] if argv else DEFAULT_URL
    metrics = run_bench(root, base_url=url)
    print(json.dumps(metrics, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
