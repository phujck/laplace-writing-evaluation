"""Distil before you dispatch: the script side of every multi-agent wave.

A model is the most expensive way to join, count, list, rename or check a field.
This tool does those things for free, so that an agent is only ever handed the
small part that needs judgement. Law: procedure/dispatch-distil-first.

    distil.py index    DIR --rows clauses --keep id,name,status,statement:280,provides,consumes
    distil.py join     DIR --rows clauses [--provides provides --consumes consumes]
    distil.py check    DIR --rows clauses --require id,name,statement --cite source [--root .]
    distil.py pack     DIR --rows clauses --ids A.3,B.7 --out pack.json
    distil.py estimate FILE [FILE ...]
    distil.py brief    PLAN LABEL [--role build|judge|synthesis]   # EVERYTHING a worker starts from, in one output
    distil.py outline  FILE.py         # classes and functions with line ranges, so a body is opened by range
    distil.py preflight PLAN.json      # writes a one-use PASS marker
    distil.py cost     RUN_DIR         # what a finished wave's workers read and what each turn cost
    distil.py returns  RUN_DIR --out F # the exact returns and verdicts of a finished wave, for the next synthesis to consume
    distil.py gate                      # the Workflow-tool hook: refuses a launch with no fresh PASS

One dispatch grammar, two launchers (S0, 2026-10-04). A tier becomes a model in exactly one
place (``laplace.pipeline.schema.TIERS``) and a return is one shape (``profiles/workflows/
*.schema.json``); these three commands are how a launcher reads them, so neither the Claude
JavaScript nor a Codex spawn call carries a model name or a schema of its own:

    distil.py launch-args PLAN                      # the args a Claude Workflow launch passes: models + both schemas, resolved
    distil.py spawn-args  PLAN LABEL --role build   # the collaboration.spawn_agent arguments Codex root uses
    distil.py check-return FILE                     # a worker's written return against the schema its schema_version names

The campaign's own state is engine rows, never a hand-written state file (ATLAS-P5):

    distil.py wave-rows [WAVE ...]                     # workflow + dispatch + judgement rows for a finished wave
    distil.py author-words TRANSCRIPT --sweep S [--render-charter]   # his typed words as author-claim rows
    distil.py residual-orders SPEC --wave W            # a synthesis's carried residuals as open work orders
    distil.py stage-receipt STAGE --from-wave W --builder-context C  # the two facts the stage gate reads

Every command reads JSON files ``DIR/*.json`` whose top-level key ``--rows`` holds a
list of row objects. Outputs go to ``DIR/index/`` unless ``--out`` is given.
"""
from __future__ import annotations

import argparse
import collections
import glob
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

CHARS_PER_TOKEN = 3.5          # measured on this campaign's JSON; conservative
AGENT_OVERHEAD = 58_000        # measured 2026-09-21 on 8 workers: first-turn context 58.0-59.5k before any read; ~48k of it is tool schemas
SLIM_OVERHEAD = 15_000         # a registered agent type with six tools; a two-tool type measured 9.8k. Labelled assumption until a wave measures it
READ_MULTIPLIER = 2.6          # calibrated 2026-09-21: seam wave measured 347k against 154-247k estimated
#: A required field a schema with ``minLength: 1`` lets through: filled, but with nothing in it.
PLACEHOLDER = re.compile(r"|-+|n/?a|none|null|tbd|todo|unknown|\.+", re.I)
VAGUE = re.compile(r"\b(appropriate|suitable|as needed|etc\.?|might consider|could be|some kind of|and so on|tbd|todo|future work)\b", re.I)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARKER = os.path.join(ROOT, ".claude", "preflight.ok")
CHARTER = os.path.join(ROOT, "atlas", "programme", "charter.json")
REGISTER = os.path.join(ROOT, "atlas", "programme", "machinery.jsonl")
PY = os.path.join(ROOT, "scripts", "laplace-python")
# The ONE place a packet schema lives. The FILES are the registry: a schema_version is
# resolved by reading their $id, so there is no table of versions to keep in step with them
# and no copy of a schema inside Python or inside a launcher's JavaScript. What is named here
# is the FAMILY, never a version: the version in force is the highest one on disk
# (``_current_schema_id``), so publishing ``laplace.packet-return/2`` is adding a file and
# nothing else - no constant in this module and no literal in either launcher moves with it.
SCHEMA_DIR = os.path.join(ROOT, "profiles", "workflows")
RETURN_FAMILY = "laplace.packet-return"
JUDGEMENT_FAMILY = "laplace.packet-judgement"
#: The programme a wave belongs to when its plan does not say. Atlas waves predate the
#: plan key; every plan written since carries ``programme`` and that is what is banked.
DEFAULT_PROGRAMME = "ATLAS-PROGRAMME-20260921"
# What every worker is given of the charter; a packet adds more with "charter_keys", a code-writing packet with "writes_code".
CARD_KEYS = ("goal_in_his_words", "why_the_last_attempt_failed_in_his_words", "why_this_matters_to_the_engine_itself",
             "the_system_as_envisaged", "forbidden_moves", "conventional_defaults_that_are_fatal_here",
             "standing_leans_recorded_as_labelled_assumptions", "the_trinity", "closure_loop", "look_before_you_build",
             "gen2_relation", "the_bootstrap")
LITERAL = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:e-?\d+)?(?![\w.])")


def _rows(directory: str, key: str):
    for path in sorted(glob.glob(os.path.join(directory, "*.json"))):
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except ValueError:
            print(f"SKIP invalid JSON: {path}", file=sys.stderr)
            continue
        for row in doc.get(key, []) if isinstance(doc, dict) else []:
            if isinstance(row, dict):
                yield os.path.basename(path)[:-5], row


def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]+", " ", re.sub(r"^[A-Za-z]{1,3}[.\-:]\s*", "", str(text).lower())).strip()


def _tokens(chars: int) -> int:
    return int(chars / CHARS_PER_TOKEN)


def _out(directory: str, out: str | None) -> str:
    target = out or os.path.join(directory, "index")
    os.makedirs(target, exist_ok=True)
    return target


def cmd_index(a) -> int:
    keep = [(k.split(":")[0], int(k.split(":")[1]) if ":" in k else None) for k in a.keep.split(",")]
    rows = []
    for lane, row in _rows(a.dir, a.rows):
        slim = {"lane": lane}
        for field, cut in keep:
            value = row.get(field)
            slim[field] = str(value)[:cut] if cut and value is not None else value
        rows.append(slim)
    path = os.path.join(_out(a.dir, a.out), f"{a.rows}.json")
    json.dump(rows, open(path, "w", encoding="utf-8"), indent=0, ensure_ascii=False)
    print(f"{len(rows)} rows -> {path} ({_tokens(os.path.getsize(path)):,} tokens est.)")
    return 0


def cmd_join(a) -> int:
    provides = collections.defaultdict(list)
    consumes = []
    for lane, row in _rows(a.dir, a.rows):
        for name in row.get(a.provides) or []:
            provides[_norm(name)].append([lane, row.get("id"), name])
        for name in row.get(a.consumes) or []:
            consumes.append((lane, row.get("id"), name))
    unsatisfied, satisfied = [], 0
    for lane, rid, name in consumes:
        key = _norm(name)
        if key in provides:
            satisfied += 1
            continue
        words = set(key.split())
        best, score = None, 0.0
        for other, hits in provides.items():
            ow = set(other.split())
            s = len(words & ow) / max(1, len(words | ow))
            if s > score:
                best, score = hits[0], s
        unsatisfied.append({"lane": lane, "row": rid, "consumes": name, "nearest": best, "similarity": round(score, 2)})
    multi = {k: v for k, v in provides.items() if len({h[0] for h in v}) > 1}
    target = _out(a.dir, a.out)
    json.dump(unsatisfied, open(os.path.join(target, "unsatisfied_consumes.json"), "w"), indent=1, ensure_ascii=False)
    json.dump(multi, open(os.path.join(target, "multi_provider.json"), "w"), indent=1, ensure_ascii=False)
    # 'nearest' is a word-overlap PROPOSAL for the seam ruling to judge (a judged agent rules on every one); nothing is renamed here
    print(f"consumes {len(consumes)} | satisfied {satisfied} | unsatisfied {len(unsatisfied)} (each with its nearest provided name as a proposal) | names with >1 providing lane {len(multi)}")
    return 0


def cmd_check(a) -> int:
    require = a.require.split(",")
    problems = []
    for lane, row in _rows(a.dir, a.rows):
        rid = row.get("id")
        for field in require:
            if row.get(field) in (None, "", [], {}):
                problems.append({"lane": lane, "row": rid, "kind": "empty-field", "detail": field})
        text = json.dumps(row, ensure_ascii=False)
        for m in set(x.group(0).lower() for x in VAGUE.finditer(text)):
            problems.append({"lane": lane, "row": rid, "kind": "vague-word", "detail": m})
        if a.cite:
            for cite in row.get(a.cite) or []:
                m = re.match(r"\s*([^:]+?\.[A-Za-z0-9]+):(\d+)", str(cite))
                if not m:
                    continue
                path = os.path.join(a.root, m.group(1).strip())
                if not os.path.exists(path):
                    hits = glob.glob(os.path.join(a.root, "**", os.path.basename(m.group(1).strip())), recursive=True)
                    path = hits[0] if len(hits) == 1 else None
                if not path:
                    problems.append({"lane": lane, "row": rid, "kind": "citation-file-missing", "detail": str(cite)[:120]})
                elif int(m.group(2)) > sum(1 for _ in open(path, errors="ignore")):
                    problems.append({"lane": lane, "row": rid, "kind": "citation-line-out-of-range", "detail": str(cite)[:120]})
    path = os.path.join(_out(a.dir, a.out), "invariant_problems.json")
    json.dump(problems, open(path, "w"), indent=1, ensure_ascii=False)
    print(dict(collections.Counter(p["kind"] for p in problems)) or "no problems", "->", path)
    return 0


def cmd_pack(a) -> int:
    wanted = set(a.ids.split(","))
    rows = [{"lane": lane, **row} for lane, row in _rows(a.dir, a.rows) if str(row.get("id")) in wanted]
    json.dump(rows, open(a.out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    missing = wanted - {str(r.get("id")) for r in rows}
    print(f"{len(rows)} rows -> {a.out} ({_tokens(os.path.getsize(a.out)):,} tokens est.)" + (f" | not found: {sorted(missing)}" if missing else ""))
    return 0


def cmd_estimate(a) -> int:
    total = 0
    for path in a.files:
        size = os.path.getsize(path)
        total += size
        print(f"{_tokens(size):>10,} tokens est.  {path}")
    print(f"{_tokens(total):>10,} tokens est.  TOTAL")
    return 0


def cmd_preflight(a) -> int:
    """PLAN.json -> prints, per packet, exactly what goes in (harness, briefing, inputs) and refuses on STRUCTURE only:
    a worker that would not know what it serves, a wave built on nothing, a wave with no synthesis, an inherited model.
    No hand-set size or count caps: the orchestrator reads the numbers, cuts the inputs, and tells the author the estimate."""
    plan = json.load(open(a.plan))
    refusals, total = [], 0
    agents = plan.get("agents", [])
    if plan.get("max_judge_rounds", 0) > 2:
        refusals.append("more than two judgement rounds (his ruling 2026-09-21)")
    if os.path.abspath(plan.get("plan_path", "")) != os.path.abspath(a.plan):
        refusals.append(f"plan_path must be this file's absolute path ({os.path.abspath(a.plan)}): workers fetch their briefing from it")
    builds_on, consume = plan.get("builds_on") or [], plan.get("consume") or []
    if not builds_on and not plan.get("first_wave_reason"):
        refusals.append("no builds_on: a wave is built from the synthesis of the wave before it (or state first_wave_reason)")
    for f in builds_on + consume:
        if not os.path.exists(f):
            refusals.append(f"builds_on/consume file absent: {f}")
    if not agents and not consume:
        refusals.append("no packets and nothing to consume")
    if plan.get("synthesis") is False and not plan.get("no_synthesis_reason"):
        refusals.append("synthesis switched off with no no_synthesis_reason: every wave ends in one")
    # fixed context by worker type, for the estimate only: default measured 58k (deep tier); claude-code-guide measured 28.6k (light tier);
    # atlas-worker not yet measured (needs a session started after it was written)
    HARNESS = {None: AGENT_OVERHEAD, "atlas-worker": SLIM_OVERHEAD}   # claude-code-guide measured 28.6k but refuses non-documentation work: not a worker
    harness = HARNESS.get(plan.get("agent_type"), AGENT_OVERHEAD)
    print(f"WAVE {plan.get('wave')}   (legacy harness estimate per worker: {harness:,} tokens; "
          "historical Claude calibration, NOT measured usage for the current provider)")
    packets = [(ag, "build") for ag in agents] + ([({"label": "synthesis", **(plan.get("synthesis") or {})}, "synthesis")] if plan.get("synthesis") is not False else [])
    for ag, role in packets:
        if 'requires_git_checkpoint' in ag and type(ag['requires_git_checkpoint']) is not bool:
            refusals.append(f"{ag.get('label')}: requires_git_checkpoint must be an explicit boolean")
        if 'requires_command_check' in ag and type(ag['requires_command_check']) is not bool:
            refusals.append(f"{ag.get('label')}: requires_command_check must be an explicit boolean")
        label = ag.get("label")
        node, goal = ag.get("node") or plan.get("node"), ag.get("goal") or plan.get("goal")
        if not node or not goal:
            refusals.append(f"{label}: no node and goal - the worker reconstructs the node it serves before it works")
            continue
        brief = brief_text(plan, label, role)
        if '"content_status": "COMPLETE"' not in brief:
            refusals.append(f"{label}: node {node!r} does not reconstruct COMPLETE - name a node typed descent resolves")
        files = list(ag.get("inputs") or []) + (consume if role == "synthesis" else [])
        absent = [x for x in files if not os.path.exists(x)]
        inputs = sum(_tokens(os.path.getsize(x)) for x in files if os.path.exists(x))
        goes_in = harness + _tokens(len(brief)) + inputs
        est = int(harness + (_tokens(len(brief)) + inputs) * READ_MULTIPLIER)
        total += est
        print(f"  {label:<34} {str(ag.get('tier', 'deep' if role == 'synthesis' else None)):<9} {str(ag.get('effort', 'high' if role == 'synthesis' else None)):<7} "
              f"goes in: harness {harness:,} + briefing {_tokens(len(brief)):,} + inputs {inputs:,} = {goes_in:,}   est final context {est:,}")
        if role == "build":
            if ag.get("tier") not in ("deep", "standard", "light"):
                refusals.append(f"{label}: no tier - a worker never inherits the session model (law/dispatch-model)")
            if ag.get("effort") in ("xhigh", "max") and not ag.get("effort_reason"):
                refusals.append(f"{label}: effort {ag.get('effort')} with no effort_reason")
            if not ag.get("why_model"):
                refusals.append(f"{label}: no why_model - say what here a script cannot do")
            if (ag.get("writes_code") or plan.get("writes_code")) and not ag.get("profile_entry"):
                refusals.append(f"{label}: writes code but declares no profile_entry - the entry its judge runs under `distil.py profile`; "
                                "a code packet cannot be accepted without a clean profile (measured 2026-09-22: an ingestion path 97% overhead passed two judges because nothing ran a profiler)")
            # THE CHECK OPENS THIS PACKET'S OWN OUTPUT (P2b judge deficiency 11, 2026-09-22): a check carried forward from an
            # earlier plan opened P2's report path and was guaranteed red for P2b whatever the builder wrote.
            if ag.get("check") and ag.get("output") and str(ag["output"]) not in str(ag["check"]):
                refusals.append(f"{label}: its check does not open its declared output {ag['output']} - a check inherited from another packet is guaranteed red")
            # THE DOOR REACHES IT OR IT IS A HALF (found on P1's reach.py and P2's down.py): a code packet's check runs the
            # reachability organ so a stage built beside the front door is refused by the judge's own scripted check.
            if (ag.get("writes_code") or plan.get("writes_code")) and "distil.py reachable" not in str(ag.get("check") or ""):
                refusals.append(f"{label}: writes code but its check never runs `distil.py reachable` over the files it writes - "
                                "a stage the front door cannot import is a half (P1's reach.py and P2's down.py were both accepted that way)")
        if absent:
            refusals.append(f"{label}: inputs absent {absent}")
    judged = sum(1 for ag in agents if ag.get("judge") is not False)
    rounds = plan.get("max_judge_rounds", 1)
    print(f"  ESTIMATE (sum of final contexts, the figure the harness reports): {total:,} for builders and synthesis; judges add about the same per judged packet "
          f"({judged} judged, up to {rounds} round(s)). Token FLOW is turns x context, typically 10-15x this; measure with `distil.py cost` afterwards.")
    print("PREFLIGHT " + ("REFUSED:\n  - " + "\n  - ".join(refusals) if refusals else "PASS - tell the author the estimate in the same message as the launch"))
    if not refusals:
        json.dump({"wave": plan.get("wave"), "plan": os.path.abspath(a.plan), "estimate": total, "ts": time.time()}, open(MARKER, "w"))
    return 1 if refusals else 0


def _run(args: list[str]) -> str:
    import subprocess
    r = subprocess.run([PY, *args], capture_output=True, text=True, cwd=ROOT, timeout=180)
    return r.stdout if r.returncode == 0 else f"[exit {r.returncode}] {r.stderr[-600:]}"


def _outline(path: str) -> list[str]:
    import ast
    src = open(path, encoding="utf-8").read()
    rows = []
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = (ast.get_docstring(node) or "").strip().splitlines()
            rows.append((node.lineno, node.end_lineno, ("class " if isinstance(node, ast.ClassDef) else "def ") + node.name, doc[0][:110] if doc else ""))
    return [f"{a:>5}-{b:<5} {name}  {doc}" for a, b, name, doc in sorted(rows)]


def _input_index(path: str) -> str:
    if not os.path.exists(path):
        return f"- {path}  ABSENT"
    size = os.path.getsize(path)
    head = f"- {path}  {size:,} bytes (~{_tokens(size):,} tokens)"
    if path.endswith(".py"):
        return head + "\n    outline (open a body by its line range):\n" + "\n".join("      " + r for r in _outline(path))
    if path.endswith(".json"):
        try:
            d = json.load(open(path))
        except ValueError:
            return head
        if isinstance(d, dict):
            keys = []
            for k, v in d.items():
                shape = f"list[{len(v)}]" + (f" of {{{', '.join(list(v[0])[:8])}}}" if v and isinstance(v[0], dict) else "") if isinstance(v, list) else type(v).__name__
                keys.append(f"      {k}: {shape}, {len(json.dumps(v)):,} chars")
            return head + "\n    keys:\n" + "\n".join(keys)
    return head


#: roles the PLAN configures at its own top level instead of inside ``agents``: the wave's
#: synthesis, and the two-command banker that ends it. Named once, so ``_packet``,
#: ``_tier_effort`` and ``launch-args`` agree on what a plan-level role is instead of each
#: testing for the string "synthesis".
PLAN_ROLES = ("synthesis", "bank")


def _packet(plan: dict, label: str) -> dict:
    if label in PLAN_ROLES:
        return {"label": label, **(plan.get(label) or {})}
    for ag in plan.get("agents", []):
        if ag.get("label") == label:
            return ag
    raise SystemExit(f"no packet {label!r} in the plan")


def _requires_command_check(packet: dict, plan: dict | None = None) -> bool:
    """An explicit command flag or the host carrier's existing executable check field."""
    check = packet.get('check') or (plan or {}).get('check_template')
    return packet.get('requires_command_check') is True or isinstance(check, str) and bool(check.strip())


def _declared_check(packet: dict, plan: dict | None = None):
    return packet.get('check') or (str((plan or {}).get('check_template') or '').replace(
        '{output}', str(packet.get('output') or '')) or None)


def _schemas() -> dict:
    """``$id`` -> (absolute path, parsed schema) for every packet schema on disk."""
    from laplace.pipeline.workflow import packet_schemas
    return packet_schemas(SCHEMA_DIR)


def _schema_file(schema_id: str) -> str:
    """The file that defines a schema version, or a refusal naming what does exist."""
    known = _schemas()
    if schema_id not in known:
        raise SystemExit(f"unknown schema_version {schema_id!r}; {SCHEMA_DIR} defines {sorted(known)}")
    return known[schema_id][0]


def _current_schema_id(family: str) -> str:
    """The version of a schema family that is in force: the highest ``<family>/<n>`` on disk.

    Read from the files, not from a constant, so a version bump is a FILE and nothing else -
    the three places that tell a worker which schema to satisfy (brief section 0, launch-args,
    spawn-args) follow the directory without a line of this module changing."""
    versions = []
    for sid in _schemas():
        head, _, tail = sid.rpartition("/")
        if head == family and tail.isdigit():
            versions.append(int(tail))
    if not versions:
        raise SystemExit(f"no schema of family {family!r} in {SCHEMA_DIR}; it defines {sorted(_schemas())}")
    return f"{family}/{max(versions)}"


def _ledger_path(path: str) -> str:
    """A path as a ledger row must name it. A lane's evidence lives in the live tree while
    ROOT is the lane's own worktree, so a relative path would climb out of the repository and
    name nothing from where the ledger is read: relative INSIDE ROOT, absolute outside it."""
    full = os.path.abspath(path)
    return os.path.relpath(full, ROOT) if full.startswith(os.path.abspath(ROOT) + os.sep) else full


def _return_path(plan: dict, label: str, role: str, rnd: int = 1) -> str:
    """Where this turn of this packet writes its return. One rule, so the launcher that
    names it, the worker that writes it and the banker that reads it cannot disagree:
    a judge writes ``verdict.r<N>.json``, everything else writes ``return.json``, both in
    the packet's own directory under the wave's out_dir."""
    out_dir = plan.get("out_dir") or os.path.dirname(os.path.abspath(plan.get("plan_path") or "."))
    name = f"verdict.r{int(rnd)}.json" if role == "judge" else "return.json"
    return os.path.join(out_dir, label, name)


def _tier_effort(plan: dict, label: str, role: str) -> tuple:
    """The (tier, effort) a packet's role runs at, from the plan alone. A judge's tier is the
    packet's own ``judge`` block, else the plan's ``judge_default``, else deep/high: an
    independent judgement is the one role that is never cheaper than the work it judges."""
    pk = _packet(plan, label)
    if role == "judge":
        judge = pk.get("judge") if isinstance(pk.get("judge"), dict) else (plan.get("judge_default") or {})
        return judge.get("tier") or "deep", judge.get("effort") or "high"
    if label == "bank":
        # The wave's banker runs two fixed commands and summarises nothing, so the floor is the
        # right default and deep/high would be waste; a plan raises it with its own ``bank`` block.
        return pk.get("tier") or "light", pk.get("effort") or "low"
    return pk.get("tier") or "deep", pk.get("effort") or "high"


def _model_for(plan: dict, label: str, role: str, provider: str = "claude") -> dict:
    """A role's {model, effort}: the tier resolved through the ONE table in
    ``laplace.pipeline.schema``. Nothing else in this file knows a model name."""
    sys.path.insert(0, os.path.join(ROOT, "src"))
    from laplace.pipeline import schema as _schema
    tier, effort = _tier_effort(plan, label, role)
    return {"tier": tier, "model": _schema.tier_model(tier, provider), "effort": effort}


def brief_text(plan: dict, label: str, role: str, rnd: int = 1) -> str:
    """Everything a worker starts from, produced by script in ONE output: the engine wake, the node it serves, the part of
    the charter it needs, the organs that exist, what its wave builds on, and an index of its inputs. What goes in is
    decided here, where it can be measured (preflight prints its size per packet), not discovered by the worker turn by turn."""
    pk = _packet(plan, label)
    node, goal = pk.get("node") or plan.get("node"), pk.get("goal") or plan.get("goal")
    out = [f"BRIEFING for packet {label!r} ({role}) of wave {plan.get('wave')!r}. Read all of it once; it replaces exploring."]
    # SECTION 0: the packet itself. The launch arguments stay small; the plan file is the one source of the brief.
    check = pk.get("check") or (str(plan.get("check_template") or "").replace("{output}", str(pk.get("output") or "")) or None)
    judge = pk.get("judge") if isinstance(pk.get("judge"), dict) else (plan.get("judge_default") or {})
    sec0 = {"packet": label, "role": role, "node": node, "goal": goal, "output": pk.get("output"),
            "brief": " ".join(x for x in (plan.get("brief_prefix"), pk.get("brief"), plan.get("brief_suffix")) if x) if label != "synthesis" else pk.get("brief"),
            "scripted_check": check,
            # Where this turn writes its exact return, and the schema it must pass before
            # returning. Named HERE, by script, so the worker never invents a path and the
            # banker never guesses one (distil.py check-return FILE is the gate).
            "return_path": _return_path(plan, label, role, rnd),
            "return_schema": _schema_file(_current_schema_id(JUDGEMENT_FAMILY if role == "judge" else RETURN_FAMILY))}
    if 'requires_command_check' in pk and type(pk['requires_command_check']) is not bool:
        raise SystemExit('requires_command_check must be an explicit boolean')
    if 'requires_command_check' in pk or check:
        sec0['requires_command_check'] = _requires_command_check(pk, plan)
    if 'requires_git_checkpoint' in pk:
        if type(pk['requires_git_checkpoint']) is not bool:
            raise SystemExit('requires_git_checkpoint must be an explicit boolean')
        sec0['requires_git_checkpoint'] = pk['requires_git_checkpoint']
    if role == "judge":
        sec0["judge_sample"] = judge.get("sample"); sec0["judge_focus"] = judge.get("focus")
        if pk.get("profile_entry"):
            sec0["profile_entry"] = pk.get("profile_entry")
    out.append("\n=== 0. YOUR PACKET (the brief, the output path and the scripted check)\n" + json.dumps(sec0, indent=1, ensure_ascii=False))
    out.append("\n=== 1. ENGINE WAKE  (scripts/laplace-python scripts/wake.py --grade 0 --engine)\n" + _run(["scripts/wake.py", "--grade", "0", "--engine"]).strip())
    recon = _run(["scripts/reconstruct_node.py", node, "--lens", goal])
    try:
        r = json.loads(recon)
        # Typed descent now carries material in bounded ``content``; ``value``
        # may be omitted or an unbounded legacy representation. Forward exactly
        # the observed slice and its continuation, never both representations.
        material = "content" if "content" in r else "value"
        keys = ("schema_version", "kind", "reference", "goal", material,
                "content_contract_schema", "content_status", "content_truncated",
                "content_omitted", "content_omitted_before", "content_omitted_after",
                "content_offset", "content_next_offset", "content_bytes",
                "content_budget", "content_handle", "content_encoding", "media_type",
                "value_omitted", "provenance")
        recon = json.dumps({k: r[k] for k in keys if k in r}, indent=1, ensure_ascii=False)
    except ValueError:
        pass
    out.append(f"\n=== 2. THE NODE YOU SERVE  (scripts/laplace-python scripts/reconstruct_node.py {node} --lens ...)\n" + recon)
    # A generic dispatch must not inherit the Atlas campaign's charter/register.
    # Campaign context is an explicit plan input, not standing law or a wake organ.
    charter_path = pk.get("charter") or plan.get("charter")
    if charter_path:
        with open(charter_path, encoding="utf-8") as stream:
            charter = json.load(stream)
        keys = list(pk.get("charter_keys") or plan.get("charter_keys") or CARD_KEYS)
        out.append(f"\n=== 3. EXPLICIT CAMPAIGN CONTEXT ({charter_path})\n" +
                   json.dumps({k: charter[k] for k in dict.fromkeys(keys) if k in charter},
                              indent=0, ensure_ascii=False))
    register_path = pk.get("register") or plan.get("register")
    if register_path:
        reg = []
        with open(register_path, encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    m = json.loads(line)
                    reg.append(f"- {m.get('organ')}: {m.get('does')}  [{m.get('entry', '')}]")
        out.append(f"\n=== 4. EXPLICIT MACHINERY INDEX ({register_path})\n" + "\n".join(reg))
    for f in plan.get("builds_on") or []:
        try:
            syn = json.load(open(f))
        except (OSError, ValueError):
            out.append(f"\n=== 5. WHAT THIS WAVE BUILDS ON: {f} (unreadable as JSON; read it)")
            continue
        mine = [x for x in syn.get("next_packets", []) if isinstance(x, dict) and x.get("label") == label]
        wanted = pk.get("builds_on_keys") or ("established", "seams", "contract_amendments", "carried_residuals")
        cut = {k: syn.get(k) for k in ("wave", *wanted) if k in syn}
        if role != "synthesis":
            cut["next_packets_entry_for_you"] = mine
        out.append(f"\n=== 5. WHAT THIS WAVE BUILDS ON  ({f})\n" + json.dumps(cut, indent=0, ensure_ascii=False))
    inputs = list(pk.get("inputs") or []) + (list(plan.get("consume") or []) if role == "synthesis" else [])
    out.append("\n=== 6. YOUR INPUTS\n" + ("\n".join(_input_index(x) for x in inputs) or "(none beyond this briefing)"))
    return "\n".join(out)


def cmd_brief(a) -> int:
    """Writes the briefing beside the wave's evidence and prints where; the worker then reads that file whole, in one call."""
    import textwrap
    plan = json.load(open(a.plan))
    text = brief_text(plan, a.label, a.role, getattr(a, "round", 1) or 1)
    # the Read tool cuts lines past 2,000 characters: wrap long ones so nothing is lost
    text = "\n".join(w for line in text.splitlines() for w in (textwrap.wrap(line, 1800, break_long_words=False, replace_whitespace=False) or [""]))
    out = a.out or os.path.join(ROOT, "evidence", "ATLAS_PROGRAMME", "waves", str(plan.get("wave")), "briefs", f"{a.label}.{a.role}.txt")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    open(out, "w", encoding="utf-8").write(text)
    print(f"BRIEFING WRITTEN. Read this file now, whole, in one Read call: {out}  ({len(text.splitlines())} lines, ~{_tokens(len(text)):,} tokens)")
    return 0


def cmd_outline(a) -> int:
    print("\n".join(_outline(a.file)))
    return 0


def cmd_cost(a) -> int:
    """RUN_DIR holds agent-*.jsonl transcripts of one wave. Prints, per worker: turns, first-turn context (the fixed
    overhead), peak context, the sum of contexts over turns (what re-sending costs), whether it ran the start
    sequence, and its largest tool results. Run on every finished wave; recalibrate the constants above from it."""
    orient = ("distil.py brief", "wake.py", "reconstruct_node")
    grand = collections.Counter()
    for f in sorted(glob.glob(os.path.join(a.run_dir, "agent-*.jsonl"))):
        try:
            label = json.load(open(f[:-6] + ".meta.json")).get("description", "")
        except (OSError, ValueError):
            label = ""
        ctx, out, calls, names, sizes = [], 0, [], {}, collections.Counter()
        for line in open(f):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            m = r.get("message") or {}
            content = m.get("content") if isinstance(m.get("content"), list) else []
            if r.get("type") == "assistant":
                u = m.get("usage") or {}
                c = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                if c and (not ctx or c != ctx[-1]):
                    ctx.append(c)
                    out += u.get("output_tokens", 0)
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use":
                        i = b.get("input") or {}
                        arg = str(i.get("file_path") or i.get("command") or i.get("pattern") or "").replace("\n", " ")
                        names[b.get("id")] = f"{b.get('name')}: {arg[:100]}"
                        calls.append(arg)
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    sizes[names.get(b.get("tool_use_id"), "?")] += len(json.dumps(b.get("content")))
        if not ctx:
            continue
        ran = [o for o in orient if any(o in c for c in calls)]
        grand.update(turns=len(ctx), flow=sum(ctx), fixed=ctx[0] * len(ctx), final=ctx[-1], out=out)
        print(f"{label[:44]:<44} turns {len(ctx):>3}  first {ctx[0]:>7,}  peak {max(ctx):>8,}  flow {sum(ctx):>11,}  out {out:>7,}  start-sequence {ran or 'NOT RUN'}")
        for name, n in sizes.most_common(3):
            print(f"      {n:>8,} chars  {name}")
    if grand:
        print(f"WAVE  turns {grand['turns']}  sum of final contexts {grand['final']:,}  flow {grand['flow']:,}  "
              f"of which fixed overhead re-sent {grand['fixed']:,} ({100 * grand['fixed'] // grand['flow']}%)  output {grand['out']:,}")
    return 0


# --------------------------------------------------------------------------------------------
# CAMPAIGN ROWS. The campaign's own state is engine rows in stores that already exist, banked
# through laplace.core.records.journal.bank_row -- never a hand-written state file, never a new store.
# (R2-rows-and-contract, ATLAS-P5. The R1 synthesis proved store by store that every row kind
# needed already exists and only the PRODUCER was missing; these four commands are it.)
WAVES_DIR = os.path.join(ROOT, "evidence", "ATLAS_PROGRAMME", "waves")
STAGE_EVIDENCE = os.path.join(ROOT, "evidence", "ATLAS_PROGRAMME")
DISPATCHES = "contract/dispatches.jsonl"
JUDGED = "contract/judged_verdicts.jsonl"
AUTHOR_MODEL = "corpus_friction/author_model.jsonl"
WORK_ORDERS = "corpus_friction/work_orders.jsonl"


def _journal():
    """The banking seam. Rows reach a store through it or they are not banked."""
    if os.path.join(ROOT, "src") not in sys.path:
        sys.path[:0] = [os.path.join(ROOT, "src")]
    from laplace.core.records import journal
    return journal


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _handle(path: str) -> str:
    """sha256 of the bytes on disk, so a result_handle resolves to a file and not to a claim."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def _banked_ids(store_rel: str) -> set:
    """Idempotence: a producer re-run must not double-bank. Complexity O(rows in store)."""
    ids = set()
    try:
        with open(os.path.join(ROOT, store_rel), encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    try:
                        ids.add(json.loads(line).get("id"))
                    except ValueError:
                        pass
    except OSError:
        pass
    return ids


def _slug(text, n: int = 44) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return (s[:n].rstrip("-") or "x")


def _run_labels(run_dir: str):
    """agentId -> {label, phase, key} from the wave run's own journal: the packet names."""
    path = os.path.join(run_dir, "journal.jsonl")
    labels = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("type") == "started" and r.get("agentId"):
                labels[r["agentId"]] = {"label": r.get("label"), "phase": r.get("phase"), "key": r.get("key")}
    return labels, path


def _run_stamp(run_dir: str) -> str:
    """When the run STARTED, in UTC: the earliest write among its agents' meta files (each is
    written once, when that agent starts). Unlike the journal's last write it does not move while
    the wave runs, so rows banked packet by packet and the final rows share one run id."""
    metas = glob.glob(os.path.join(run_dir, "agent-*.meta.json"))
    first = min((os.path.getmtime(m) for m in metas), default=os.path.getmtime(os.path.join(run_dir, "journal.jsonl")))
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(first))


def _run_id(wave: str, run_dir: str, journal_path: str, stamp: str = None) -> str:
    """The reader's identifier form, derived and never invented: a UTC stamp plus twelve hex of
    sha256(wave + run directory). laplace.pipeline.workflow:534 accepts
    WORKFLOW-<YYYYMMDD>T<HHMMSS>Z-<12 hex> and nothing else. The stamp is the run's START when
    the returns file carries one (``run_stamp``, every wave from F2 on); a returns file written
    before that carries none and keeps the journal's last write, so ids already banked stay."""
    stamp = stamp or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(os.path.getmtime(journal_path)))
    tag = hashlib.sha256(f"{wave}\n{os.path.basename(run_dir)}".encode("utf-8")).hexdigest()[:12]
    return f"WORKFLOW-{stamp}-{tag}"


def _deposit_returns(returns_path: str, run_id: str):
    """Deposit a wave's exact returns under ``evidence/WORKFLOWS/<run_id>/`` and return
    (path to name on the row, what the deposit did).

    THE DECIDED RESIDUAL (R2 carried it to the orchestrator): the reader lifts a result_ref only
    for a path under ``evidence/WORKFLOWS/<run_id>/`` (workflow.py:617-620), and ``run_path`` in
    its projection is that same directory.  Measured before this change: all seven banked Atlas
    workflow rows named a run_path that does not exist on disk, so the wake's own descend command
    pointed at nothing - a minted reference that cannot be resolved, which the charter's
    forbidden_moves names.  Widening the containment check would have cured the symptom by
    weakening a containment rule.  Depositing the bytes cures the cause: the deposit is
    byte-identical (same sha256) to the wave's own returns.json, so there is one record with two
    addresses, not two records.  Idempotent: identical bytes are left alone."""
    deposit_rel = os.path.join("evidence", "WORKFLOWS", run_id, "returns.json")
    deposit_abs = os.path.join(ROOT, deposit_rel)
    with open(returns_path, "rb") as fh:
        data = fh.read()
    if os.path.exists(deposit_abs):
        with open(deposit_abs, "rb") as fh:
            if fh.read() == data:
                return deposit_rel, "IDENTICAL-ALREADY-DEPOSITED"
    os.makedirs(os.path.dirname(deposit_abs), exist_ok=True)
    with open(deposit_abs, "wb") as fh:
        fh.write(data)
    return deposit_rel, "DEPOSITED"


def _write_returns(run_dir: str, out: str, exclude=("bank",)) -> dict:
    """A run journal's exact returns as the file every consumer of a finished wave reads. One
    pass over the journal; nothing is summarised, nothing is read into a model. Results whose
    label is in ``exclude`` are dropped so the run that BANKS the wave does not bank itself -
    which also keeps the file byte-stable across a resume."""
    labels, _ = _run_labels(run_dir)
    rows = []
    for line in open(os.path.join(run_dir, "journal.jsonl"), encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("type") != "result":
            continue
        label = (labels.get(r.get("agentId")) or {}).get("label") or ""
        if label.split(":")[0] in exclude:
            continue
        rows.append({k: r.get(k) for k in ("label", "agentId", "result") if k in r} or r)
    doc = {"record": "atlas.wave-returns/1", "run_dir": os.path.abspath(run_dir), "returns": rows}
    prior = None
    if os.path.exists(out):
        try:
            prior = json.load(open(out, encoding="utf-8"))
        except ValueError:
            prior = None
    if prior is None or prior.get("run_dir") != doc["run_dir"]:
        doc["run_stamp"] = _run_stamp(run_dir)
    elif prior.get("run_stamp"):
        doc["run_stamp"] = prior["run_stamp"]
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    json.dump(doc, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return {"out": out, "returns": len(rows), "bytes": os.path.getsize(out)}


_WF_JOURNALS = os.path.expanduser("~/.claude/projects/*/*/subagents/workflows/wf_*/journal.jsonl")


def _find_run_dir(labels_wanted: set) -> tuple:
    """The run directory of the wave whose packets these are, IDENTIFIED BY ITS CONTENT.

    A workflow script has no filesystem (it reaches the world only through an agent), so the
    wave cannot hand its own run directory to the banking step.  Guessing 'the newest run' would
    bank the wrong wave the moment two run in a day.  Instead: a journal qualifies when every
    packet label of the plan appears in one of its ``started`` labels; among the qualifying
    journals the newest by mtime is the run.  Returns (run_dir, diagnosis)."""
    best, scanned, coverage = None, 0, []
    for path in glob.glob(_WF_JOURNALS):
        scanned += 1
        try:
            labels, _ = _run_labels(os.path.dirname(path))
        except OSError:
            continue
        seen = {str(v.get("label") or "") for v in labels.values()}
        covered = {want for want in labels_wanted
                   if any(want == s or s.startswith(want + ":") or s.endswith(":" + want)
                          or s.split(":", 1)[-1].split(":")[0] == want for s in seen)}
        coverage.append((len(covered), os.path.dirname(path)))
        if len(covered) == len(labels_wanted) and labels_wanted:
            stamp = os.path.getmtime(path)
            if best is None or stamp > best[0]:
                best = (stamp, os.path.dirname(path))
    if best:
        return best[1], {"journals_scanned": scanned, "matched_on": "every packet label present "
                                                                   "as a started label"}
    coverage.sort(reverse=True)
    return None, {"journals_scanned": scanned, "labels_wanted": sorted(labels_wanted),
                  "best_coverage": coverage[:3],
                  "why": "no run journal carries a started label for every packet of this plan"}


def cmd_wave_returns(a) -> int:
    """A finished wave's exact returns file, written WITHOUT anyone remembering a command: the
    run directory is found from the plan's own packet labels, and the returns come from the run
    journal's result records.  This is what ``wave-rows`` then banks."""
    plan = json.load(open(a.plan, encoding="utf-8"))
    wave = a.wave or plan["wave"]
    run_dir = a.run_dir
    diagnosis = {"run_dir": "given on the command line"} if run_dir else None
    if not run_dir:
        wanted = {str(p["label"]) for p in plan.get("agents") or [] if p.get("label")}
        run_dir, diagnosis = _find_run_dir(wanted)
    if not run_dir:
        print(json.dumps({"record": "atlas.wave-returns-locate/1", "wave": wave,
                          "status": "NO-RUN-FOUND", **diagnosis}, indent=1, ensure_ascii=False))
        return 1
    out = a.out or os.path.join(WAVES_DIR, wave, "returns.json")
    written = _write_returns(run_dir, out)
    print(json.dumps({"record": "atlas.wave-returns/1", "wave": wave, "run_dir": run_dir,
                      "status": "WRITTEN", **written, "located": diagnosis},
                     indent=1, ensure_ascii=False))
    return 0


def cmd_profile(a) -> int:
    """Run a Python entry under cProfile and say whether its time is INHERENT WORK or OVERHEAD.

    The efficiency rule was prose until 2026-09-22; nothing ran a profiler, and an ingestion path
    that was 97% overhead passed two judges. This is the check a judge (and a builder, before it
    reports) runs. Usage: distil.py profile [--top N] -- <script.py or -m module> [args...]
    Overhead classes, by function name and call count: per-element tensor construction
    (torch.tensor/arange/as_tensor/.item/.tolist called thousands of times), call storms (a Python
    or builtin function called more than a million times), process and pool creation
    (multiprocessing, subprocess, popen, spawn), and waiting (sleep, select, poll, acquire)."""
    import cProfile, pstats, runpy, io as _io
    argv = list(a.entry)
    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        raise SystemExit("profile: give a script path or -m module after --")
    prof = cProfile.Profile()
    old_argv, t0 = sys.argv, time.time()
    try:
        if argv[0] == "-m":
            sys.argv = argv[1:]
            prof.runcall(runpy.run_module, argv[1], run_name="__main__", alter_sys=True)
        else:
            sys.argv = argv
            prof.runcall(runpy.run_path, argv[0], run_name="__main__")
    except SystemExit:
        pass
    finally:
        sys.argv = old_argv
    wall = time.time() - t0
    st = pstats.Stats(prof, stream=_io.StringIO())
    rows = []
    for (fn, line, name), (cc, nc, tt, ct, _callers) in st.stats.items():
        rows.append({"where": f"{os.path.relpath(fn, ROOT) if fn.startswith(ROOT) else os.path.basename(fn)}:{line}", "name": name, "calls": nc, "self_s": tt})
    total = sum(r["self_s"] for r in rows) or 1e-9
    def klass(r):
        n, w = r["name"], r["where"]
        if any(k in n for k in ("sleep", "select", "poll", "acquire", "wait")) and "regex" not in w:
            return "WAITING"
        if any(k in w for k in ("multiprocessing", "subprocess", "popen", "spawn")) or n in ("fork_exec", "posix_spawn"):
            return "PROCESS-CREATION"
        if any(k in n for k in ("torch.tensor", "as_tensor", "torch.arange", "'item'", "'tolist'", "torch.zeros", "torch.empty")) and r["calls"] >= 2000:
            return "PER-ELEMENT-TENSOR"
        if r["calls"] >= 1_000_000:
            return "CALL-STORM"
        return None
    shares = collections.defaultdict(float)
    for r in rows:
        k = klass(r)
        r["class"] = k
        if k:
            shares[k] += r["self_s"] / total
    # a Python function that OWNS a call storm is where the fix goes: attribute by tottime rank
    rows.sort(key=lambda r: -r["self_s"])
    overhead = sum(shares.values())
    top = [{**r, "self_s": round(r["self_s"], 3), "share": round(r["self_s"] / total, 3)} for r in rows[:a.top]]
    print(json.dumps({"record": "atlas.profile/1", "command": argv, "wall_seconds": round(wall, 2),
                      "overhead_share": round(overhead, 3), "overhead_by_class": {k: round(v, 3) for k, v in shares.items()},
                      "verdict": "OVERHEAD-DOMINATED" if overhead >= 0.25 else "inherent work on top" ,
                      "reading": "overhead_share counts only time INSIDE the flagged calls; a Python function high in `top` whose callees are flagged is the line to rewrite",
                      "top": top}, indent=1, ensure_ascii=False))
    return 1 if overhead >= 0.25 else 0


def cmd_loops(a) -> int:
    """A census of Python loops that walk DATA (rows, edges, nodes, witnesses) instead of tensors:
    a `for` whose iterable unpacks a tensor (`.tolist()`, `.item()`), zips such lists, ranges over
    a tensor's size, or walks a store's rows. Static, so it cannot tell a hot loop from a cold one -
    it is the work-list and a judge's first look; the stage profile at three sizes decides.
    Loops over lenses, kinds, columns or modes are not data loops and are not listed."""
    import ast
    DATA = ("tolist", ".item(", "numel", ".rows(", "row_ids", "zip(", "range(", ".items()", "enumerate(")
    SMALL = ("lens.", "spec.", "kinds", "columns", "task_columns", "tables", "source_kinds", "derived_relations",
             "counted_relation_kinds", "types.", "sorted(types")
    out, total = [], 0
    for root in a.paths:
        files = [root] if root.endswith(".py") else sorted(glob.glob(os.path.join(root, "**", "*.py"), recursive=True))
        for path in files:
            src = open(path, encoding="utf-8").read()
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            funcs = {}
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for sub in ast.walk(node):
                        if isinstance(sub, (ast.For, ast.comprehension)):
                            funcs.setdefault(id(sub), node.name)
            for node in ast.walk(tree):
                it = node.iter if isinstance(node, (ast.For, ast.comprehension)) else None
                if it is None:
                    continue
                text = ast.get_source_segment(src, it) or ""
                if not any(k in text for k in DATA) or any(k in text for k in SMALL):
                    continue
                total += 1
                out.append({"file": os.path.relpath(path, ROOT), "line": getattr(it, "lineno", 0),
                            "in": funcs.get(id(node), "<module>"), "over": " ".join(text.split())[:110]})
    by_file = collections.Counter(r["file"] for r in out)
    print(json.dumps({"record": "atlas.loop-census/1", "data_loops": total,
                      "by_file": dict(by_file.most_common()), "loops": out if a.list else "pass --list"},
                     indent=1, ensure_ascii=False))
    return 0


def cmd_watch(a) -> int:
    """While a wave RUNS, bank each packet's return and verdict as it lands, at no model cost.

    Before this, a wave's rows were banked only by its last phase: for the hours a wave ran, the
    wake named the previous wave and an accepted packet existed only in the harness's transcript
    directory. This polls the run journal and, whenever a new result record appears, rewrites the
    wave's returns file and banks the new rows with the workflow row PENDING. It stops when the
    wave starts its own banking phase (the final COMPLETED rows are that phase's job and two
    writers must not overlap), or when nothing in the run directory has changed for ``--idle``
    seconds (the run is dead or the session ended). Complexity O(journal) per new result."""
    import argparse as _ap
    plan = json.load(open(a.plan, encoding="utf-8"))
    wave = plan["wave"]
    wanted = {str(p["label"]) for p in plan.get("agents") or [] if p.get("label")}
    out = os.path.join(WAVES_DIR, wave, "returns.json")
    seen, last_change = -1, time.time()
    while True:
        run_dir = a.run_dir or _find_run_dir(wanted)[0]
        if run_dir:
            labels, jpath = _run_labels(run_dir)
            if any(str(v.get("label") or "").split(":")[0] == "bank" for v in labels.values()):
                print(json.dumps({"record": "atlas.wave-watch/1", "wave": wave, "stopped": "the wave reached its own banking phase"}))
                return 0
            results = sum(1 for line in open(jpath, encoding="utf-8") if '"type":"result"' in line.replace(" ", ""))
            if results != seen:
                _write_returns(run_dir, out)
                cmd_wave_rows(_ap.Namespace(waves=[wave], partial=True))
                seen = results
            newest = max((os.path.getmtime(f) for f in glob.glob(os.path.join(run_dir, "*"))), default=last_change)
            last_change = max(last_change, newest)
        if time.time() - last_change > a.idle:
            print(json.dumps({"record": "atlas.wave-watch/1", "wave": wave, "stopped": f"nothing in the run directory changed for {a.idle} s"}))
            return 0
        time.sleep(a.interval)


def _waves_with_returns() -> list:
    out = []
    for path in sorted(glob.glob(os.path.join(WAVES_DIR, "*", "returns.json"))):
        out.append(os.path.basename(os.path.dirname(path)))
    return out


def _placeholder_fields(doc, schema, prefix: str = "", root_schema=None) -> list:
    """``cmd_check``'s empty-required rule, at EVERY depth of the document.

    A JSON Schema with ``minLength: 1`` cannot see a required field that is filled with
    nothing - whitespace, a dash, "n/a", "none", "tbd". Walking only the top level would leave
    exactly the fields a reader trusts most (a check's ``output_tail``, a deficiency's
    ``evidence``) able to say nothing at all and pass."""
    out = []
    if not isinstance(schema, dict) or not isinstance(doc, dict):
        return out
    root_schema = root_schema or schema
    if str(schema.get('$ref', '')).startswith('#/'):
        resolved = root_schema
        for part in schema['$ref'][2:].split('/'):
            resolved = resolved[part.replace('~1', '/').replace('~0', '~')]
        return _placeholder_fields(doc, resolved, prefix, root_schema)
    if schema.get('oneOf'):
        for alternative in schema['oneOf']:
            out.extend(_placeholder_fields(doc, alternative, prefix, root_schema))
    props = schema.get("properties") or {}
    for field in schema.get("required") or []:
        if field not in doc:
            continue
        value, sub, where = doc[field], props.get(field) or {}, f"{prefix}{field}"
        if isinstance(value, str) and PLACEHOLDER.fullmatch(value.strip()):
            out.append(f"empty-field: {where} is a placeholder ({value!r}), not an observation")
        elif isinstance(value, dict):
            out.extend(_placeholder_fields(value, sub, where + "/", root_schema))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                out.extend(_placeholder_fields(item, sub.get("items") or {}, f"{where}/{i}/", root_schema))
    return out


def _return_problems(file: str, *, requires_git_checkpoint=False, expected_output=None,
                     requires_command_check=False, verify_owner_read=None, expected_check=None) -> tuple:
    """Every problem with the written return or judgement at ``file``, and the schema file it
    was judged against. THE one gate: ``check-return`` prints these and so does every banker,
    so a document the grammar refuses cannot reach a row (``_from_dir_doc``).

    Four rules, one code path. (1) JSON Schema draft 2020-12 (jsonschema 4.26 is in the
    runtime), so the shape is checked by the file in ``profiles/workflows`` and not by a
    reader's patience. (2) ``cmd_check``'s prose rules, the ones a schema cannot express: no
    VAGUE word anywhere in the document, no required field present but empty, and no input
    digest that pins nothing. (3) the carrier's acceptance rule, lifted verbatim from
    ``src/laplace/pipeline/workflow.py:811-813`` (ADVERSARY-HAS-NO-INDEPENDENT-COMMAND-
    OBSERVATION): an acceptance needs the judge's OWN successful command observation, and an
    acceptance with outstanding deficiencies is not an acceptance.

    Every problem is returned, never the first - a worker fixes them all in one pass instead
    of discovering them one return at a time."""
    from jsonschema import Draft202012Validator
    problems = []
    try:
        with open(file, encoding="utf-8") as stream:
            doc = json.load(stream)
    except (OSError, ValueError) as exc:
        return [f"unreadable return {file}: {type(exc).__name__}: {exc}"], None
    if not isinstance(doc, dict) or not isinstance(doc.get("schema_version"), str) or not doc.get("schema_version"):
        return [f"{file}: a return must be a JSON object naming its schema_version"], None
    path, schema = _schemas().get(doc["schema_version"], (None, None))
    if schema is None:
        return [f"{file}: unknown schema_version {doc['schema_version']!r}; "
                f"{SCHEMA_DIR} defines {sorted(_schemas())}"], None
    from laplace.pipeline.workflow import packet_return_problems, packet_owner_read_verifier
    def resolve_pin(value):
        # The CLI invocation and its selected return directory define scope. A
        # document's source.root cannot add an unrelated directory to that scope.
        candidate = Path(value)
        candidate = (candidate if candidate.is_absolute() else Path(ROOT) / candidate).resolve()
        allowed = (Path(ROOT).resolve(), Path(file).resolve().parent)
        if not any(candidate == base or base in candidate.parents for base in allowed):
            raise ValueError('artifact path escapes the CLI checkout/selected return directory')
        return candidate
    problems.extend(packet_return_problems(doc, schema_directory=SCHEMA_DIR,
                                          resolve_pin=resolve_pin,
                                          requires_git_checkpoint=requires_git_checkpoint,
                                          output_path=expected_output,
                                          requires_command_check=requires_command_check,
                                          expected_check=expected_check,
                                          verify_owner_read=verify_owner_read or packet_owner_read_verifier(ROOT)))
    text = json.dumps(doc, ensure_ascii=False)
    for word in sorted(set(m.group(0).lower() for m in VAGUE.finditer(text))):
        problems.append(f"vague-word: {word!r} - a return states what was observed, not what might be")
    # cmd_check's empty-required rule, kept only where it ADDS something. Emptiness itself is
    # the schema's business and the schema already states it (``minItems: 1`` on
    # ``most_important``; ``maxItems: 0`` on a COMPLETE return's residuals; an empty
    # ``deficiencies`` is what an acceptance LOOKS like, so flagging it would be wrong).
    # What a schema with ``minLength: 1`` cannot see is a field filled with a placeholder:
    # whitespace, a dash, "n/a", "none", "tbd". Those are the empty fields in practice.
    problems.extend(_placeholder_fields(doc, schema))
    # The same rule one level down, on the field whose whole purpose is pinning bytes. A
    # schema's ``pattern`` sees a well-formed digest; it cannot see an INVENTED one, and an
    # invented digest is worse than an absent field because a judge trusts it. All zeros is
    # the placeholder of digests; anything else is checked against the file when the file is
    # readable from here, which is the only way a pin can be known to pin.
    for i, item in enumerate(doc.get("inputs") or []):
        digest = item.get("sha256") if isinstance(item, dict) else None
        if not isinstance(digest, str) or not re.fullmatch(r"(sha256:)?[0-9a-fA-F]{64}", digest):
            continue
        hexd = digest.rpartition(":")[2].lower()
        if set(hexd) == {"0"}:
            problems.append(f"input-digest: inputs/{i}/sha256 is all zeros - a pin that pins nothing")
            continue
        src = item.get("path") or ""
        full = src if os.path.isabs(src) else os.path.join(ROOT, src)
        if src and os.path.isfile(full):
            actual = _handle(full).rpartition(":")[2]
            if actual != hexd:
                problems.append(f"input-digest: inputs/{i}/sha256 claims {hexd[:16]}... for {src}, "
                                f"whose bytes here are sha256:{actual[:16]}...")
    return problems, path


def cmd_check_return(a) -> int:
    """A worker's WRITTEN return against the schema its own ``schema_version`` names: the rules
    of ``_return_problems``, printed one per line, exit 1 if there are any."""
    problems, path = _return_problems(a.file)
    for problem in problems:
        print("PROBLEM " + problem)
    against = f" against {os.path.relpath(path, ROOT)}" if path else ""
    print(f"{'CLEAN' if not problems else 'RED'}: {a.file}{against}")
    return 1 if problems else 0


def _launch_agents(plan: dict) -> list:
    """The per-packet fields a launcher needs, and no others: the plan file stays the one
    source of the brief, so a launch argument never carries brief text.

    ``judge`` and ``judge_first`` are the plan's own switches, projected as booleans: a packet
    the plan exempts from judgement, and one whose builder ran in an earlier wave. Without them
    a launcher judges what the plan exempted and re-runs a builder the plan retired, because
    neither switch is visible anywhere else in these arguments."""
    out = []
    for pk in plan.get("agents", []):
        judge = pk.get("judge") if isinstance(pk.get("judge"), dict) else (plan.get("judge_default") or {})
        check = pk.get("check") or (str(plan.get("check_template") or "").replace(
            "{output}", str(pk.get("output") or "")) or None)
        out.append({"label": pk.get("label"), "stage": pk.get("stage"), "feeds": pk.get("feeds") or [],
                    "output": pk.get("output"), "check": check,
                    "judge": pk.get("judge") is not False, "judge_first": bool(pk.get("judge_first")),
                    "judge_sample": judge.get("sample"), "judge_focus": judge.get("focus")})
        if 'requires_git_checkpoint' in pk:
            if type(pk['requires_git_checkpoint']) is not bool:
                raise SystemExit('requires_git_checkpoint must be an explicit boolean')
            out[-1]['requires_git_checkpoint'] = pk['requires_git_checkpoint']
        if 'requires_command_check' in pk and type(pk['requires_command_check']) is not bool:
            raise SystemExit('requires_command_check must be an explicit boolean')
        if 'requires_command_check' in pk or check:
            out[-1]['requires_command_check'] = _requires_command_check(pk, plan)
    return out


def cmd_launch_args(a) -> int:
    """The JSON a Claude Workflow launch passes as its args.

    Everything a launcher could hard-code is resolved HERE: every model from the tier table in
    ``laplace.pipeline.schema`` - each packet's build and judge, the synthesis, and the wave's
    own row bank - and both schemas from their files in ``profiles/workflows``. The
    JavaScript therefore holds no model literal and no schema literal - it reads
    ``args.models[label][role]`` and ``args.schemas.return`` - which is the whole point of S0:
    one fact, one holder, two launchers."""
    with open(a.plan, encoding="utf-8") as stream:
        plan = json.load(stream)
    models = {}
    for pk in plan.get("agents", []):
        models[pk["label"]] = {"build": _model_for(plan, pk["label"], "build"),
                               "judge": _model_for(plan, pk["label"], "judge")}
    if plan.get("synthesis"):
        models["synthesis"] = {"synthesis": _model_for(plan, "synthesis", "synthesis")}
    # The wave's row bank is an agent too (a workflow script has no filesystem), so its model is
    # resolved HERE like every other role's. Without this the launcher would need a literal of its
    # own for the one phase that is not a packet - which is the hole S0 exists to close.
    models["bank"] = {"bank": _model_for(plan, "bank", "bank")}
    schemas = {}
    for key, family in (("return", RETURN_FAMILY), ("judgement", JUDGEMENT_FAMILY)):
        spath, sdoc = _schemas()[_current_schema_id(family)]
        schemas[key] = sdoc
        schemas[key + "_path"] = spath
    args = {"plan_path": plan.get("plan_path") or os.path.abspath(a.plan),
            "wave": plan.get("wave"), "out_dir": plan.get("out_dir"), "record": plan.get("record"),
            "programme": plan.get("programme") or DEFAULT_PROGRAMME,
            "max_judge_rounds": plan.get("max_judge_rounds") or 2,
            "stages": plan.get("stages") or [{"title": "Stage 1",
                                              "packets": [p["label"] for p in plan.get("agents", [])]}],
            "agents": _launch_agents(plan),
            "synthesis": {"output": (plan.get("synthesis") or {}).get("output")} if plan.get("synthesis") else None,
            "models": models, "schemas": schemas}
    print(json.dumps(args, indent=1, ensure_ascii=False))
    return 0


def cmd_spawn_args(a) -> int:
    """The exact ``collaboration.spawn_agent`` arguments Codex root uses for one packet.

    The same plan, the same brief command and the same return schema as the Claude launcher -
    only the provider column of the tier table differs. ``fork_turns: 'none'`` is what Codex
    root itself used in its 2026-10-03 rollout: a worker that inherits the orchestrator's
    turns inherits its context and its conclusions, and then its judgement is not independent."""
    with open(a.plan, encoding="utf-8") as stream:
        plan = json.load(stream)
    label = a.label
    resolved = _model_for(plan, label, a.role, provider="codex")
    rnd = getattr(a, "round", 1) or 1
    return_path = _return_path(plan, label, a.role, rnd)
    schema_file = _schema_file(_current_schema_id(JUDGEMENT_FAMILY if a.role == "judge" else RETURN_FAMILY))
    brief_cmd = (f"scripts/laplace-python scripts/distil.py brief {a.plan} {label} --role {a.role}"
                 + (f" --round {rnd}" if a.role == "judge" else ""))
    message = (f"Run this first, from {ROOT}, and read the file it writes whole: {brief_cmd}\n"
               f"It is your whole briefing: the engine wake, the node you serve, your packet's brief, "
               f"your output path and your scripted check.\n"
               f"Write your exact return to {return_path}; it must pass "
               f"{os.path.relpath(schema_file, ROOT)}, which you check yourself with "
               f"scripts/laplace-python scripts/distil.py check-return {return_path} before you return.\n"
               f"Return nothing but the return path and a one-line summary.")
    print(json.dumps({"task_name": f"{plan.get('wave')}-{label}-{a.role}",
                      "model": resolved["model"], "reasoning_effort": resolved["effort"],
                      "fork_turns": "none", "message": message}, indent=1, ensure_ascii=False))
    return 0


def _from_dir_doc(a) -> tuple:
    """A wave whose packets wrote their returns to FILES, as the one returns-document shape
    ``cmd_wave_rows`` already banks. Not a second banker: the per-label files are read, their
    exact bytes deposited into one ``returns.json`` beside them, and the SAME loop runs.

    ``<OUT_DIR>/<label>/return.json`` is a build return and ``verdict.r<N>.json`` is round N's
    judgement - the paths ``_return_path`` hands the worker in its brief, so what is banked is
    what was briefed.

    Every file read goes through ``_return_problems`` first, the same code path
    ``check-return`` is, and a wave with one refused document banks NOTHING: a gate that only
    runs where a worker chooses to run it is the state S0 set out to end."""
    out_dir = os.path.abspath(a.from_dir)
    plan_path = a.plan or os.path.join(out_dir, "plan.json")
    if not os.path.isfile(plan_path):
        raise SystemExit(f"--from-dir needs the wave's plan for its tiers and programme: "
                         f"{plan_path} does not exist; pass --plan")
    with open(plan_path, encoding="utf-8") as stream:
        plan = json.load(stream)
    wave = a.wave or plan.get("wave")
    returns, labels, stamps, refused = [], {}, [], []

    def take(path: str, agent: str, phase: str, packet_contract):
        expected = packet_contract.get('output')
        expected = (Path(expected) if os.path.isabs(expected) else Path(ROOT) / expected) if expected else None
        problems, _ = _return_problems(path,
            requires_git_checkpoint=packet_contract.get('requires_git_checkpoint') is True,
            requires_command_check=_requires_command_check(packet_contract, plan),
            expected_check=_declared_check(packet_contract, plan),
            expected_output=expected if phase == 'build' else None)
        if problems:
            refused.extend(f"{os.path.basename(os.path.dirname(path))}/{os.path.basename(path)}: {p}"
                           for p in problems)
            return
        stamps.append(os.path.getmtime(path))
        with open(path, encoding="utf-8") as stream:
            returns.append({"agentId": agent, "result": json.load(stream)})
        labels[agent] = {"label": agent, "phase": phase, "key": _ledger_path(path)}

    for pk in plan.get("agents", []):
        label = pk["label"]
        build = os.path.join(out_dir, label, "return.json")
        if os.path.isfile(build):
            take(build, label, "build", pk)
        for verdict in sorted(glob.glob(os.path.join(out_dir, label, "verdict.r*.json"))):
            rnd = re.search(r"verdict\.r(\d+)\.json$", verdict).group(1)
            take(verdict, f"judge:{label}:r{rnd}", "judge", pk)
    if refused:
        raise SystemExit("REFUSED: these documents do not pass the grammar they were written "
                         "against, and a row must not say they did:\n  " + "\n  ".join(refused) +
                         "\n(the same rules as scripts/laplace-python scripts/distil.py check-return FILE)")
    if not returns:
        raise SystemExit(f"no {out_dir}/<label>/return.json or verdict.r*.json to bank")
    rpath = os.path.join(out_dir, "returns.json")
    # The run's stamp is a property of the WAVE, not of a file's mtime: a packet that continues
    # in place rewrites its return, and a stamp read from that file would mint a second run id
    # for one wave. Once this wave has a returns document its own stamp is kept; only a wave
    # being banked for the first time takes its birth from the returns on disk. (The run id
    # itself is looked up in the ledger first - _banked_run_id, cmd_wave_rows.)
    stamp = None
    if os.path.isfile(rpath):
        try:
            with open(rpath, encoding="utf-8") as stream:
                stamp = json.load(stream).get("run_stamp")
        except (OSError, ValueError):
            stamp = None
    doc = {"wave": wave, "run_dir": out_dir, "returns": returns,
           "run_stamp": stamp or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(min(stamps))),
           "source": f"scripts/distil.py wave-rows --from-dir {out_dir}; labels from "
                     f"<label>/return.json and <label>/verdict.r*.json"}
    with open(rpath, "w", encoding="utf-8") as stream:
        json.dump(doc, stream, indent=1, ensure_ascii=False)
    return wave, plan, rpath, labels


def _banked_run_id(wave: str, run_dir: str) -> str | None:
    """The run id this wave and directory were ALREADY banked under, if they were.

    One wave is one run. A ``--from-dir`` wave has no run journal to date it, and the campaign's
    closure loop rewrites a build return in place when a packet continues - so a stamp taken
    from the files would mint a second id, and ``workflow.py list`` would read two runs where
    one happened. The ledger already holds this wave's identity; it is read, not re-derived."""
    for row in _banked_last(DISPATCHES).values():
        if row.get("record") == "workflow" and row.get("wave") == wave and row.get("run_dir") == run_dir:
            return row.get("id")
    return None


def _wave_worker_standing(returns, plan=None):
    """Goal standing from exact typed worker returns, not a successful envelope or judge."""
    workers = {}
    for envelope in returns:
        document = envelope.get('result') or {}
        if isinstance(document, dict) and str(document.get('schema_version') or '').startswith(RETURN_FAMILY + '/'):
            workers[document['packet']] = document.get('status')
    expected = {item['label'] for item in (plan or {}).get('agents') or []
                if not item.get('judge_first')}
    missing = sorted(expected - set(workers))
    has_subject = bool(workers) or any(item.get('judge_first') for item in (plan or {}).get('agents') or [])
    complete = has_subject and not missing and all(value == 'COMPLETE' for value in workers.values())
    # These states describe retained goal work; RETURNED describes only carriage.
    status = ('INTERRUPTED' if 'INTERRUPTED' in workers.values() else
              'BLOCKED' if 'BLOCKED' in workers.values() else
              'COMPLETED' if complete else 'INCOMPLETE')
    return {'status': status, 'complete': complete, 'workers': workers, 'missing': missing}


def _wave_plan(a, wave: str) -> dict | None:
    """The plan of an Atlas wave, when one is on disk, so its programme and tiers are read
    instead of assumed. ``None`` when there is none - and then nothing is derived from it."""
    path = getattr(a, "plan", None) or os.path.join(WAVES_DIR, wave, "plan.json")
    for candidate in (path, os.path.join(ROOT, "atlas", "programme", "waves", f"{wave}.plan.json")):
        if candidate and os.path.isfile(candidate):
            with open(candidate, encoding="utf-8") as stream:
                return json.load(stream)
    return None


def _transport(plan: dict | None, label: str, role: str, a) -> dict:
    """The transport disclosure ``scripts/audit_dispatch_models.py`` requires of a dispatch
    row: which model ran at which tier, under which executor, in which sandbox.

    Every value is DERIVED or STATED, never guessed. The model comes from the plan's tier
    through ``schema.TIERS`` (the one table), so a row's stamp and the model the launcher
    actually passed have one source. ``codex_model`` is a Codex transport field: on the Claude
    surface it is disclosed as not applicable rather than filled with a plausible id. With no
    plan the four fields are OMITTED - a row that cannot say what ran must not claim it."""
    if not plan:
        return {}
    subject = label.split(":")[1] if label.startswith("judge:") else label
    if subject == "synthesis" or subject not in {p.get("label") for p in plan.get("agents", [])}:
        subject = "synthesis" if subject.startswith("synthesis") else subject
    try:
        resolved = _model_for(plan, subject, "judge" if role == "judge" else "build",
                              provider=getattr(a, "provider", None) or "claude")
    except (SystemExit, ValueError, KeyError):
        return {}
    provider = getattr(a, "provider", None) or "claude"
    return {"packet_model_stamp": resolved["model"], "packet_tier": resolved["tier"],
            "effort": resolved["effort"],
            "executor": getattr(a, "executor", None) or ("codex-cli" if provider == "codex"
                                                         else "claude-workflow-tool"),
            "codex_model": (resolved["model"] if provider == "codex"
                            else "not-applicable; claude-workflow-tool surface"),
            "sandbox": getattr(a, "sandbox", None) or
                       "inherited-session-permissions; the Workflow tool runs a packet as a subagent "
                       "of the launching session and configures no sandbox of its own"}


def cmd_wave_rows(a) -> int:
    """A finished wave becomes engine rows: one workflow row and one dispatch row per returned
    packet in contract/dispatches.jsonl, one row per judgement in contract/judged_verdicts.jsonl.
    Every row carries result_path and a sha256 result_handle of the bytes on disk. Nothing is
    summarised by a model: the labels come from the run journal, the verdicts from the returns.
    Complexity O(returns) per wave; the stores are appended through journal.bank_row only."""
    journal = _journal()
    # --from-dir: the wave wrote its returns as files under the campaign's evidence directory
    # (no Workflow run journal to read labels from). One plan, one deposit, the same loop.
    from_dir = None
    if getattr(a, "from_dir", None):
        wave, wave_plan, deposit, deposit_labels = _from_dir_doc(a)
        from_dir = {wave: (wave_plan, deposit, deposit_labels)}
        waves = [wave]
    else:
        waves = a.waves or _waves_with_returns()
    # The LAST row per id, not the set of ids: a packet that continues in place rewrites its
    # return, and the honest answer is a correction appended under the SAME id, never a second
    # row and never a silent skip that leaves the ledger naming bytes that no longer exist.
    have_d, have_j = _banked_last(DISPATCHES), _banked_last(JUDGED)
    report = {"record": "atlas.wave-rows/1", "banked": {DISPATCHES: 0, JUDGED: 0}, "skipped_existing": 0, "waves": []}
    for wave in waves:
        wave_plan = from_dir[wave][0] if from_dir else _wave_plan(a, wave)
        rpath = from_dir[wave][1] if from_dir else os.path.join(WAVES_DIR, wave, "returns.json")
        if not os.path.exists(rpath):
            report["waves"].append({"wave": wave, "status": "NO-RETURNS",
                                    "why": f"{os.path.relpath(rpath, ROOT)} does not exist; a wave with no "
                                           "returns file has nothing exact to bank"})
            continue
        doc = json.load(open(rpath, encoding="utf-8"))
        run_dir = doc["run_dir"]
        labels, jpath = (from_dir[wave][2], rpath) if from_dir else _run_labels(run_dir)
        staged = bool(doc.get("run_stamp"))
        # One wave is one run: an id already banked for this wave and directory is REUSED, so a
        # return rewritten by a continuation corrects its rows instead of minting a second run.
        reused_id = _banked_run_id(wave, run_dir) if from_dir else None
        run_id = reused_id or _run_id(wave, run_dir, jpath, doc.get("run_stamp"))
        wave_path = _ledger_path(rpath)
        # What actually read the labels. On the --from-dir path there is no journal, and a row
        # that misstates its own provenance in the one field the report reads for it is a lie
        # the report then repeats: the returns document's own source string is the truth.
        row_source = doc.get("source") or (
            f"scripts/distil.py wave-rows {wave}; labels from "
            f"{os.path.join(os.path.basename(run_dir), 'journal.jsonl')}")
        if not from_dir:
            # Native journal envelopes also carry canonical typed documents. A
            # successful envelope cannot bypass the same profile/currentness gate.
            from laplace.pipeline.workflow import packet_return_problems, packet_owner_read_verifier
            def resolve_wave_pin(value):
                path = Path(value)
                path = (path if path.is_absolute() else Path(ROOT) / path).resolve()
                if not any(path == base or base in path.parents for base in
                           (Path(ROOT).resolve(), Path(rpath).resolve().parent)):
                    raise ValueError('wave artifact escapes the declared checkout/deposit')
                return path
            for envelope in doc['returns']:
                document = envelope.get('result') or {}
                identity = str(document.get('schema_version') or '')
                if not identity.startswith((RETURN_FAMILY+'/', JUDGEMENT_FAMILY+'/')):
                    continue  # retain legacy untyped carriage; it does not certify a typed builder
                contract = next((pk for pk in (wave_plan or {}).get('agents') or []
                                 if pk.get('label') == document.get('packet')), {})
                problems = packet_return_problems(document, schema_directory=SCHEMA_DIR,
                    requires_git_checkpoint=contract.get('requires_git_checkpoint') is True,
                    requires_command_check=_requires_command_check(contract, wave_plan),
                    expected_check=_declared_check(contract, wave_plan), resolve_pin=resolve_wave_pin,
                    verify_owner_read=packet_owner_read_verifier(ROOT))
                if problems:
                    raise SystemExit('REFUSED canonical wave return: '+'; '.join(problems))
        result_path, deposit = _deposit_returns(rpath, run_id)
        result_handle = _handle(rpath)
        entry = {"wave": wave, "workflow_id": run_id, "run_dir": run_dir, "result_path": result_path,
                 "wave_result_path": wave_path, "deposit": deposit,
                 "result_handle": result_handle, "dispatch_rows": [], "judged_rows": [], "returns": len(doc["returns"])}
        judged_total = 0
        last_verdict = {}
        standing = _wave_worker_standing(doc['returns'], wave_plan)
        # Dispatch and judgement rows FIRST, the workflow row LAST: the reader keeps the last
        # row per run_id (workflow.py:627 latest[run_id] = item), so the workflow row is what
        # `workflow.py list` must end on.
        for ret in doc["returns"]:
            agent = ret.get("agentId") or ""
            meta = labels.get(agent, {})
            label = meta.get("label") or agent
            role = label.split(":")[0] if ":" in label else (meta.get("phase") or "worker").lower()
            result = ret.get("result") if isinstance(ret.get("result"), dict) else {}
            is_judge = "accepted" in result
            did = f"{run_id}:{_slug(label)}"
            entry["dispatch_rows"].append(did)
            return_handle = _sha(json.dumps(result, sort_keys=True, ensure_ascii=False).encode("utf-8"))
            prior_d = have_d.get(did)
            if prior_d is not None and prior_d.get("return_handle") == return_handle:
                report["skipped_existing"] += 1
            else:
                journal.bank_row(DISPATCHES, {
                    "record": "dispatch", "id": did, "workflow_id": run_id, "wave": wave,
                    "stage": _slug(label), "role": role, "label": label, "phase": "return",
                    "status": "RETURNED", "accepted": result.get("accepted") if is_judge else None,
                    **({'self_status': result.get('status')} if not is_judge else {}),
                    "worker_context": agent, "prompt_key": meta.get("key"),
                    "return_handle": return_handle,
                    "result_path": result_path, "result_handle": result_handle,
                    "run_dir": run_dir, "authority_effect": "none",
                    "source": row_source,
                    **({"corrects": f"the row previously banked under this id named return_handle "
                                    f"{prior_d.get('return_handle')}; the packet continued in place and "
                                    f"rewrote its return. Last-wins (src/laplace/pipeline/workflow.py:631): "
                                    f"this row is the live one, the earlier one stays as history."}
                       if prior_d is not None else {}),
                    # The four fields scripts/audit_dispatch_models.py:211-217 requires of a
                    # dispatch row. DERIVED from the plan's tier through schema.TIERS - never
                    # invented: with no plan in hand they are omitted and the audit says so,
                    # which is what the 227 phase-"return" rows banked before this grammar
                    # (contract/dispatches.jsonl, every one from an earlier wave-rows run) show.
                    **_transport(wave_plan, label, role, a),
                }, root=ROOT)
                report["banked"][DISPATCHES] += 1
            if not is_judge:
                continue
            judged_total += 1
            subject = label.split(":")[1] if label.count(":") >= 1 and label.startswith("judge") else label
            last_verdict[subject] = bool(result.get("accepted"))
            deficiencies = result.get("deficiencies") or []
            checked = result.get("checked") or []
            jid = f"JV-{run_id[9:17]}-{_slug(wave, 28)}-{_slug(subject, 32)}"
            # Banked packet by packet, a second round would collide with the first round's id and
            # be skipped as already banked - the FINAL verdict lost. The round is part of the id.
            rounds = label.split(":")[2:] if staged else []
            if rounds and rounds[0] != "r1":
                jid += "-" + _slug(rounds[0], 4)
            entry["judged_rows"].append(jid)
            # The verdict's OWN bytes decide, not the wave's: a build return rewritten by a
            # continuation must not restate every judgement of the wave.
            prior_j = have_j.get(jid)
            if prior_j is not None and prior_j.get("return_handle") == return_handle:
                report["skipped_existing"] += 1
                continue
            first = deficiencies[0] if deficiencies else None
            journal.bank_row(JUDGED, {
                "id": jid,
                "judge": f"{label} (independent worker context {agent}, wave {wave}, run {run_id})",
                "judge_context": agent,
                "subject": f"{subject} (wave {wave})",
                "verdict": "ACCEPTED" if result.get("accepted") else "REJECTED",
                "evidence": (f"{len(checked)} checks run by the judge's own commands, "
                             f"{len(deficiencies)} typed deficiencies. Exact return: {result_path} "
                             f"({result_handle}), agent {agent}. First deficiency: "
                             + (json.dumps(first, ensure_ascii=False)[:600] if first is not None else "none")),
                "workflow_id": run_id, "wave": wave,
                "profile_verdict": (result.get("profile") or {}).get("verdict") if isinstance(result.get("profile"), dict) else None,
                "profile_overhead_share": (result.get("profile") or {}).get("overhead_share") if isinstance(result.get("profile"), dict) else None,
                "result_path": result_path, "result_handle": result_handle,
                "return_handle": return_handle,
                "banked_by": "scripts/distil.py wave-rows",
                "source": row_source,
                "notes": "transcribed verbatim from the wave's exact return; the judgement itself was made "
                         "in a different context from the builder it judged",
                **({"corrects": f"the row previously banked under this id named return_handle "
                                f"{prior_j.get('return_handle')}; this judgement's bytes changed. "
                                f"Last-wins (src/laplace/pipeline/workflow.py:631)."}
                   if prior_j is not None else {}),
            }, root=ROOT)
            report["banked"][JUDGED] += 1
        # A run_id already banked is normally skipped (idempotence). Two exceptions, and neither
        # EDITS a row: a correction is APPENDED under the same id and the reader keeps the last
        # row per run_id (workflow.py:631), so the projection moves while the history stays.
        # (1) the recorded result_path is not the deposit the reader can lift; (2) the wave's
        # returns are new bytes because a packet continued in place.
        prior = have_d.get(run_id)
        entry["judgements"] = judged_total
        # A packet's standing is its LAST verdict: rejected in round one and accepted in round two
        # is accepted.
        entry['worker_standing'] = standing
        entry["all_judgements_accepted"] = standing['complete'] and bool(last_verdict) and all(last_verdict.values())
        entry["packets_accepted"] = sorted(k for k, v in last_verdict.items()
                                            if v and standing['workers'].get(k, 'COMPLETE') == 'COMPLETE')
        entry["packets_not_accepted"] = sorted(k for k, v in last_verdict.items() if not v)
        entry['packets_not_accepted'] = sorted(set(entry['packets_not_accepted']) |
            {key for key, value in standing['workers'].items() if value != 'COMPLETE'} | set(standing['missing']))
        status = (standing['status'] if not standing['complete'] else
                  'PENDING' if getattr(a, 'partial', False) else 'COMPLETED')
        if (prior is not None and prior.get("result_path") == result_path
                and prior.get("result_handle") == result_handle
                and prior.get("status") == status and prior.get("returns") == len(doc["returns"])):
            report["skipped_existing"] += 1
            entry["status"] = "ALREADY-BANKED"
        else:
            if prior is None:
                corrects = None
            elif prior.get("result_path") == result_path:
                # Same run, new bytes: a packet of this wave continued in place. One wave is one
                # run, so this is an append under the SAME id, never a second workflow row.
                corrects = (
                    f"the row previously banked under this id named result_handle "
                    f"{prior.get('result_handle')} over {prior.get('returns')} returns; a packet of this "
                    f"wave continued in place and rewrote its return, so the wave's exact returns are "
                    f"new bytes at the same deposit. One wave is one run: the id is the one the ledger "
                    f"already holds (scripts/distil.py _banked_run_id) and the reader keeps the last row "
                    f"per id (src/laplace/pipeline/workflow.py:631).")
            else:
                corrects = (
                    f"the row previously banked under this id named result_path "
                    f"{prior.get('result_path')!r}, which is outside evidence/WORKFLOWS/{run_id}/ and so "
                    f"could not be lifted as a result_ref by laplace.pipeline.workflow:617-620, while its "
                    f"run_path named a directory that did not exist. The bytes are unchanged (same "
                    f"result_handle); this row names the deposit. Last-wins: this row is the live one.")
            journal.bank_row(DISPATCHES, {
                "record": "workflow", "id": run_id, "phase": "result",
                "status": status, "accepted": entry["all_judgements_accepted"],
                "packets_accepted": entry["packets_accepted"],
                "packets_not_accepted": entry["packets_not_accepted"],
                'worker_standing': standing,
                "result_path": result_path, "result_handle": result_handle,
                "wave": wave, "stage": _slug(wave),
                # The programme is the plan's own, not a campaign literal: the Atlas default
                # only applies to the Atlas waves whose plans predate the key.
                "programme": (wave_plan or {}).get("programme") or DEFAULT_PROGRAMME,
                "returns": len(doc["returns"]), "judgements": judged_total,
                "dispatch_ids": entry["dispatch_rows"], "judged_verdict_ids": entry["judged_rows"],
                "run_dir": run_dir, "authority_effect": "none",
                "wave_result_path": wave_path,
                "id_derivation": ("the id this wave and run directory were already banked under, read "
                                  "back from this ledger (scripts/distil.py _banked_run_id): one wave "
                                  "is one run, and a return rewritten in place must not mint a second"
                                  if reused_id else
                                  "WORKFLOW-<run start, UTC>-<sha256(wave + run dir)[:12]>; "
                                  "the form laplace.pipeline.workflow:592 accepts"),
                "result_ref_note": "result_path is the run's own deposit of the wave's exact returns, "
                                   "byte-identical to wave_result_path (same sha256). The containment "
                                   "rule at workflow.py:617-620 is a rule, not a bug: it lifts a "
                                   "result_ref only for a path under evidence/WORKFLOWS/<run_id>/, "
                                   "which is also the run_path the reader serves - so the artefact is "
                                   "deposited where the reader is entitled to read it instead of the "
                                   "rule being widened to reach where it sat.",
                "source": row_source,
                **({"corrects": corrects} if corrects else {}),
            }, root=ROOT)
            report["banked"][DISPATCHES] += 1
            entry["status"] = "CORRECTED" if corrects else "BANKED"
        report["waves"].append(entry)
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


_HARNESS = re.compile(r"^\s*<(command-message|command-name|local-command|system-reminder|task-notification"
                      r"|user-prompt-submit-hook|session-start-hook)\b", re.I)
_REMINDER = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)


def _banked_last(store_rel: str) -> dict:
    """id -> the LAST row banked under it. These stores fold last-wins (laplace.engine.wake:2087), so a
    correction is an append with the same id, never an edit in place."""
    last = {}
    try:
        with open(os.path.join(ROOT, store_rel), encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("id"):
                    last[row["id"]] = row
    except OSError:
        pass
    return last


_ENVELOPE = re.compile(r"^\s*<[A-Za-z][A-Za-z0-9_.-]*>")
#: the Codex desktop app delivers the repository's AGENTS.md as a user turn. It is an injection,
#: not speech, and it is the ONLY non-tag harness envelope measured in his 2026-09-19/20 threads.
_INJECTED = ("# AGENTS.md instructions for ",)


def _codex_messages(transcript: str, dropped) -> list:
    """The author's own typed messages from a CODEX ROLLOUT.

    His 2026-09-19 and 2026-09-20 sessions ran in Codex, not Claude: this project's Claude
    transcripts jump from 2026-09-17 straight to 2026-09-21 (measured over every file in
    ~/.claude/projects/-home-phujck-VScodeProjects-laplace), so the only record of those two
    days is ~/.codex/sessions/2026/09/{19,20}/rollout-*.jsonl.  The shape differs: a record is
    ``{"timestamp", "type": "response_item", "payload": {"type": "message", "role": "user",
    "content": [{"type": "input_text", "text": ...}]}}``.

    THREE mechanical gates, fail closed, because a rollout tree contains far more 'user'
    messages than the author ever typed:

    (a) the rollout's own ``session_meta.thread_source`` must be a thread HE talks in.  A
        ``'subagent'`` thread is machine-to-machine: its 'user' messages are the orchestrator's
        prompts, and banking those as his words would forge rows, so such a file yields nothing
        and says why.  ``'user'`` is his own thread.  ``'agent_created_thread'`` is a thread the
        app opened for him (a worktree session) and he types in it - his 2026-09-19 words
        "Don't be tied to the current implementation" live only there - so it is read, with one
        extra gate: a user message counts only once an ASSISTANT message has preceded it, which
        is exactly the test that drops a spawning prompt (a prompt cannot follow a reply to
        itself) without guessing at voice.  (Measured 2026-09-19/20: 32 rollouts, 3 of his own
        threads, 2 app-opened threads, 27 machine threads.)
    (b) the record is a ``message``/``role == 'user'`` with ``input_text`` content.
    (c) the text is not an envelope: no opening ``<tag>``, no slash command, and not the
        ``# AGENTS.md instructions for `` block the desktop app injects as a user turn.

    One pass, O(bytes), with a substring pre-filter so only candidate lines are parsed."""
    kept, seen, meta, spawned, answered = [], set(), None, False, False
    with open(transcript, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if meta is None and '"session_meta"' in line:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("type") == "session_meta":
                    meta = row.get("payload") or {}
                    source = meta.get("thread_source")
                    if source not in ("user", "agent_created_thread"):
                        dropped["rollout is a MACHINE thread (session_meta.thread_source is neither "
                                "'user' nor 'agent_created_thread'); its user messages are "
                                "orchestrator prompts, never his words"] += 1
                        return []
                    spawned = source == "agent_created_thread"
                continue
            if spawned and not answered and '"assistant"' in line:
                try:
                    payload = (json.loads(line).get("payload") or {})
                except ValueError:
                    payload = {}
                answered = payload.get("role") == "assistant" or payload.get("type") == "agent_message"
            if '"role":"user"' not in line and '"role": "user"' not in line:
                continue
            if spawned and not answered:
                dropped["app-opened thread: user message before any assistant reply - a spawning "
                        "prompt, not his typing"] += 1
                continue
            try:
                row = json.loads(line)
            except ValueError:
                dropped["unparseable"] += 1
                continue
            payload = row.get("payload") or {}
            if payload.get("type") != "message" or payload.get("role") != "user":
                dropped["not a user message record"] += 1
                continue
            for item in payload.get("content") or []:
                text = item.get("text") if isinstance(item, dict) else None
                if item.get("type") != "input_text" or not isinstance(text, str):
                    dropped["content item is not input_text"] += 1
                    continue
                text = _REMINDER.sub("", text).strip()
                if not text:
                    dropped["empty after stripping system reminders"] += 1
                    continue
                if _ENVELOPE.match(text) or _HARNESS.match(text):
                    dropped["harness envelope, not typed by the author"] += 1
                    continue
                if text.startswith(_INJECTED):
                    dropped["injected AGENTS.md instruction block, not typed by the author"] += 1
                    continue
                if text.startswith("/"):
                    dropped["slash command, not speech"] += 1
                    continue
                if text in seen:
                    dropped["same message already kept"] += 1
                    continue
                seen.add(text)
                kept.append({"ts": row.get("timestamp"), "uuid": payload.get("id"),
                             "channel": "codex-user-message", "text": text})
    if meta is None:
        dropped["rollout carries no session_meta: its thread_source cannot be established"] += 1
        return []
    kept.sort(key=lambda m: m["ts"] or "")
    return kept


def _author_messages(transcript: str, dropped) -> list:
    """The author's typed messages, whichever harness recorded them. A file whose first record
    is a ``session_meta`` is a Codex rollout and is read by ``_codex_messages``; everything else
    is a Claude session transcript and is read by the two-channel rule below."""
    with open(transcript, encoding="utf-8", errors="replace") as fh:
        head = fh.readline()
    try:
        if json.loads(head).get("type") == "session_meta":
            return _codex_messages(transcript, dropped)
    except ValueError:
        pass
    return _claude_messages(transcript, dropped)


def _claude_messages(transcript: str, dropped) -> list:
    """The author's own typed messages, from BOTH channels the harness records them in.

    (1) ``type == 'user'`` with ``origin.kind == 'human'`` and a plain-string content: what he
        typed when the session was idle. (2) ``type == 'queue-operation'`` with
        ``operation == 'enqueue'``: what he typed WHILE the session was working, which the
        harness delivers as an attachment and never writes as a user line. Channel (2) was
        missing from the first pass of this producer and swallowed nine of his messages on
        2026-09-21, including 'why would you _not_ want them to run the engine wake'.

    Everything else fails a mechanical test: a tool result and an attachment are not strings, a
    task notification, a skill body, a hook injection and a system reminder open with a
    harness tag, a slash command opens with '/', and the compaction summary is not a user line.
    One pass, O(bytes); nothing but the kept messages is held."""
    kept, seen = [], set()
    with open(transcript, encoding="utf-8") as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except ValueError:
                dropped["unparseable"] += 1
                continue
            kind = r.get("type")
            if kind == "user":
                origin = r.get("origin")
                if not (isinstance(origin, dict) and origin.get("kind") == "human"):
                    dropped["user line, not origin.kind=human (tool result, task notification, skill or hook text)"] += 1
                    continue
                content, channel, uuid = (r.get("message") or {}).get("content"), "user-line", r.get("uuid")
            elif kind == "queue-operation" and r.get("operation") == "enqueue":
                content, channel, uuid = r.get("content"), "queue-enqueue", None
            else:
                dropped["neither a user line nor an enqueue"] += 1
                continue
            if not isinstance(content, str):
                dropped["content is not a plain string"] += 1
                continue
            text = _REMINDER.sub("", content).strip()
            if not text:
                dropped["empty after stripping system reminders"] += 1
                continue
            if _HARNESS.match(text):
                dropped["harness block, not typed by the author"] += 1
                continue
            if text.startswith("/"):
                dropped["slash command, not speech"] += 1
                continue
            if text in seen:
                dropped["same message already kept from the other channel"] += 1
                continue
            seen.add(text)
            kept.append({"ts": r.get("timestamp"), "uuid": uuid, "channel": channel, "text": text})
    kept.sort(key=lambda m: m["ts"] or "")
    return kept


def cmd_author_words(a) -> int:
    """The author's own typed messages become author-claim rows, by script, never by reading the
    transcript into a model's context (this one is 9.5 MB). Rows are verbatim, inferred=false,
    grounded on the session id and the message timestamp. Re-running corrects: a row whose id
    exists with different bytes is re-banked (last-wins), an identical one is left alone."""
    journal = _journal()
    session = a.session or os.path.basename(a.transcript)[:-6]
    dropped = collections.Counter()
    kept = _author_messages(a.transcript, dropped)
    banked, corrected, have = 0, 0, _banked_last(AUTHOR_MODEL)
    rows = []
    for n, m in enumerate(kept, 1):
        rid = f"AM-{a.sweep}-{n:03d}"
        prior = have.get(rid)
        row = {
            "record": "author-claim", "id": rid, "source_sweep": a.sweep,
            "claim": m["text"], "cls": "utterance",
            "cls_note": "not classified: this row carries what the author typed, byte for byte. A class "
                        "(want/law/style/...) is an inference and belongs on a row that declares inferred=true.",
            "verbatim": m["text"], "inferred": False, "standing": "live",
            "date": (m["ts"] or "")[:10], "channel": m["channel"],
            "ground": f"session:{session} message:{m['uuid'] or m['ts']} ts:{m['ts']}",
            "source": f"the author's typed message in session {session}, channel {m['channel']}; extracted by "
                      f"scripts/distil.py author-words",
            "ts": m["ts"],
        }
        if prior is not None and prior.get("verbatim") == m["text"] and prior.get("channel") == m["channel"]:
            rows.append(row)
            continue
        if prior is not None:
            row["corrects"] = (f"the row previously banked under this id carried a different message; the first "
                               f"extraction read only the user-line channel and missed what the author queued "
                               f"while the session was working. Last-wins: this row is the live one.")
            corrected += 1
        rows.append(row)
        journal.bank_row(AUTHOR_MODEL, row, root=ROOT)
        banked += 1
    out = {"record": "atlas.author-words/1", "session": session, "transcript": a.transcript,
           "transcript_bytes": os.path.getsize(a.transcript), "kept": len(kept), "banked": banked,
           "corrected": corrected, "by_channel": dict(collections.Counter(m["channel"] for m in kept)),
           "store": AUTHOR_MODEL, "dropped": dict(dropped),
           "first_ts": kept[0]["ts"] if kept else None, "last_ts": kept[-1]["ts"] if kept else None,
           "chars": sum(len(m["text"]) for m in kept), "messages": kept}
    if a.deposit:
        json.dump(out, open(a.deposit, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    summary = {k: v for k, v in out.items() if k != "messages"}
    summary["deposit"] = a.deposit
    if a.render_charter:
        # THE CHARTER IS A RENDER OF THE STORE, NOT OF THIS SWEEP. Rendering it against only the
        # rows this run banked un-renders every quote the other sweeps carry: run over the
        # 2026-09-19 rollout, the 2026-09-21 quotes would all have read 'unmatched' and the
        # file's own row_source would have named ten rows instead of the store's live set.
        live = _live_author_rows()
        summary["charter"] = _render_charter(live)
        summary["charter"]["rendered_against"] = f"{len(live)} live author-claim rows (last-wins fold of {AUTHOR_MODEL})"
    print(json.dumps(summary, indent=1, ensure_ascii=False))
    return 0


_HIS = ("goal_in_his_words", "why_the_last_attempt_failed_in_his_words", "the_trinity", "closure_loop",
        "look_before_you_build", "gen2_relation", "the_bootstrap", "efficient_code_is_a_requirement",
        "distil_before_dispatch", "decisions_are_the_orchestrators", "how_work_is_judged",
        "the_campaign_is_itself_a_conceptric", "worker_start_sequence")
_ELLIPSIS = re.compile(r"\s*\.\.\.\s*")
_TAIL = re.compile(r"\s*\((?:20\d\d-\d\d-\d\d)\)\s*$")


def _live_author_rows() -> list:
    """Every LIVE author-claim row, folded last-wins (the store's own rule, laplace.engine.wake:2087).
    The render's source is the store; a sweep is only how rows arrive. O(rows in store)."""
    live = {}
    for row in _banked_last(AUTHOR_MODEL).values():
        if row.get("record") == "author-claim" and row.get("id") and isinstance(row.get("verbatim"), str):
            live[row["id"]] = row
    return list(live.values())


def _norm_q(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


_ANCHOR = 40       # a prefix shorter than this is not evidence that two texts are the same quote


def _longest_verbatim(frag: str, rows: list):
    """The longest prefix of ``frag`` that is a verbatim substring of some banked row, by binary
    search on the prefix length. O(len(frag) log len(frag)) substring tests per row. Returns
    (text, row id) or (None, None): substring evidence or nothing, never a fuzzy match."""
    texts = [(row["id"], _norm_q(row["verbatim"])) for row in rows]
    best_text = best_id = None
    for rid, body in texts:
        if frag[:_ANCHOR] not in body:
            continue
        lo, hi = _ANCHOR, len(frag)
        while lo < hi:                                     # largest k with frag[:k] in body
            mid = (lo + hi + 1) // 2
            if frag[:mid] in body:
                lo = mid
            else:
                hi = mid - 1
        if best_text is None or lo > len(best_text):
            best_text, best_id = frag[:lo], rid
    return best_text, best_id


def _render_fragment(frag: str, rows: list, hits: list, notes: list):
    """Render one fragment losslessly FROM the rows: take its longest verbatim prefix, emit that,
    then render what is left the same way, joining the pieces with the charter's own ' ... '.
    Nothing he typed is dropped; what re-anchors is re-emitted, and a remainder too short or too
    far from any row to anchor is kept as it stands and reported as a divergence. Terminates:
    every round consumes at least _ANCHOR characters."""
    pieces, rest = [], frag
    while rest:
        exact = next((r["id"] for r in rows if rest in _norm_q(r["verbatim"])), None)
        if exact:
            hits.append(exact)
            pieces.append(rest)
            break
        text, rid = _longest_verbatim(rest, rows)
        if text is None:
            notes.append({"kind": "no_row_carries_this", "text": rest[:160]})
            pieces.append(rest)
            break
        hits.append(rid)
        pieces.append(text)
        remainder = rest[len(text):].strip()
        notes.append({"kind": "diverged_from_the_row_here", "row": rid,
                      "verbatim_kept_chars": len(text), "then": remainder[:120]})
        rest = remainder
    return " ... ".join(pieces)


def _render_quote(quote: str, rows: list):
    """Re-render one charter quote FROM the rows. The charter joins his words with ' ... '; each
    fragment is rendered separately and losslessly. A quote no row carries (his words from an
    earlier session, not in this transcript) is left exactly as it stands and flagged."""
    tail = _TAIL.search(quote)
    frags = [f for f in _ELLIPSIS.split(_TAIL.sub("", _norm_q(quote))) if f]
    out, hits, notes = [], [], []
    for frag in frags:
        out.append(_render_fragment(frag, rows, hits, notes))
    rendered = " ... ".join(out) + (tail.group(0) if tail else "")
    missing = [n["text"] for n in notes if n["kind"] == "no_row_carries_this"]
    return rendered, {"fragments": len(frags), "rows": sorted(set(hits)),
                      "unmatched_fragments": missing,
                      "divergences": [n for n in notes if n["kind"] != "no_row_carries_this"],
                      "matched": not missing and bool(frags)}


def _walk_his(node, rows, path, found):
    if isinstance(node, str):
        if len(node) < 24:
            return node
        rendered, info = _render_quote(node, rows)
        found.append({"at": path, "quote_sha": _sha(node.encode("utf-8"))[7:19],
                      "rewritten": rendered != _norm_q(node), **info})
        return rendered if info["rows"] else node
    if isinstance(node, list):
        return [_walk_his(v, rows, f"{path}[{i}]", found) for i, v in enumerate(node)]
    if isinstance(node, dict):
        # ONLY his-words keys. 'rule', 'why_it_happens_here' and the rest are the engine's own
        # prose about his words and are not quotes; rendering them from rows would be a category error.
        return {k: (_walk_his(v, rows, f"{path}.{k}", found)
                    if ("his_word" in k or "his_order" in k or k.endswith("_in_his_words")) else v)
                for k, v in node.items()}
    return node


def _render_charter(rows: list) -> dict:
    """Re-render the charter's his-words sections against the rows and NAME THE ROW SOURCE in the
    file. The quotes are checked fragment by fragment against the banked verbatim; a quote whose
    fragments all resolve is a render of those rows, a quote that does not is reported unmatched
    (his earlier-session words have no row in this transcript) and is left untouched."""
    charter = json.load(open(CHARTER, encoding="utf-8"))
    sections, all_rows, unmatched = {}, set(), 0
    for key in _HIS:
        if key not in charter:
            continue
        found = []
        charter[key] = _walk_his(charter[key], rows, key, found)
        if not found:
            continue
        ids = sorted({r for f in found for r in f["rows"]})
        all_rows |= set(ids)
        unmatched += sum(1 for f in found if not f["matched"])
        sections[key] = {"rows": ids, "quotes": found}
        if isinstance(charter[key], dict):
            charter[key]["row_source"] = (
                "corpus_friction/author_model.jsonl rows " + (", ".join(ids) if ids else "(none resolved here)")
                + " -- these words are a RENDER of those rows; the rows are the source")
    charter["his_words_row_source"] = {
        "law": "rows before renders: the author's words live in corpus_friction/author_model.jsonl as "
               "record='author-claim', inferred=false, verbatim. This file is a render of them and goes "
               "stale the moment the rows move.",
        "store": AUTHOR_MODEL,
        "producer": "scripts/laplace-python scripts/distil.py author-words "
                    "<session transcript> --sweep <sweep> --render-charter",
        "rendered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rows_available": len(rows),
        "rows_named": sorted(all_rows),
        "quotes_unmatched": unmatched,
        "unmatched_means": "the quote's words were typed in an earlier session whose transcript has not "
                           "been extracted into rows; the quote is left exactly as it stands and is flagged here.",
        "sections": sections,
    }
    json.dump(charter, open(CHARTER, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    return {"file": os.path.relpath(CHARTER, ROOT), "sections": list(sections),
            "rows_named": len(all_rows), "quotes_unmatched": unmatched}


def cmd_residual_orders(a) -> int:
    """Each carried residual of a wave synthesis becomes an open work-order row with a target,
    so a residual is never left as a note. Complexity O(residuals)."""
    journal = _journal()
    doc = json.load(open(a.spec, encoding="utf-8"))
    residuals = doc.get(a.key) or []
    have = _banked_ids(WORK_ORDERS)
    # A residual a synthesis re-carries from the wave before is the SAME order, not a new one:
    # measured 2026-09-21, 129 open orders held about 45 distinct residuals, a third already done.
    def _same(text):
        return re.sub(r"[^a-z0-9]+", " ", re.sub(r"^CARRIED[^:]{0,140}:\s*", "", str(text)).lower())[:70]
    open_now = {_same(r.get("what")): r.get("id") for r in _banked_last(WORK_ORDERS).values() if r.get("status") == "open"}
    banked, ids, already = 0, [], []
    for n, r in enumerate(residuals, 1):
        residual = _norm_q(r.get("residual"))
        owner = _norm_q(r.get("owner_in_next_wave"))
        rid = f"WO-{a.stamp}-{_slug(a.wave, 24)}-{n:02d}-{_slug(residual.split('.')[0], 34)}"
        if _same(residual) in open_now and open_now[_same(residual)] != rid:
            already.append(open_now[_same(residual)])
            continue
        ids.append(rid)
        if rid in have:
            continue
        journal.bank_row(WORK_ORDERS, {
            "record": "work-order", "kind": "work-order", "id": rid, "status": "open",
            # the same fact as the workflow row's programme: one holder, DEFAULT_PROGRAMME
            "corpus": "engine", "programme": getattr(a, "programme", None) or DEFAULT_PROGRAMME,
            "target": owner or a.default_target, "owed_by": owner or a.default_target,
            "what": residual,
            "why": f"carried residual of wave {a.wave}; the charter's closure loop forbids leaving a "
                   f"residual as a note, a TODO or a follow-up, so it is banked as an open order with an owner",
            "source": _norm_q(r.get("from")),
            "refs": [os.path.relpath(a.spec, ROOT)],
            "requested_by": f"scripts/distil.py residual-orders (wave {a.wave})",
        }, root=ROOT)
        banked += 1
    print(json.dumps({"record": "atlas.residual-orders/1", "wave": a.wave, "store": WORK_ORDERS,
                      "residuals": len(residuals), "banked": banked, "ids": ids, "already_open_not_reminted": already}, indent=1, ensure_ascii=False))
    return 0


def _plan_packet(wave, packet) -> dict:
    """The plan's own entry for a packet (empty when the plan or the packet is not found)."""
    try:
        plan = json.load(open(os.path.join(ROOT, "atlas", "programme", "waves", f"{wave}.plan.json"), encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return next((ag for ag in plan.get("agents") or [] if ag.get("label") == packet), {})


def cmd_stage_receipt(a) -> int:
    """The two typed facts a campaign stage's gate reads, computed from the banked rows rather
    than asserted: evidence/ATLAS_PROGRAMME/<stage>/acceptance.json (the builder's own receipt)
    and purpose_judgement.json (a TRANSCRIPTION of the independent judgements already recorded
    for the packets that serve the stage -- it never mints a judgement of its own).
    PASS requires complete builders/current result pins as well as each serving packet's
    recorded acceptance; a judgement cannot upgrade retained incomplete work."""
    stage_dir = os.path.join(STAGE_EVIDENCE, a.stage)
    os.makedirs(stage_dir, exist_ok=True)
    # LATEST verdict per packet across the listed waves, by the row's own timestamp. A packet is every
    # lane that has a judged row OR a builder return in those waves - a JUDGE-FIRST packet has no
    # builder and must still count (the first version dropped nine such lanes and wrote a false PASS
    # on 2026-09-21 while one of them stood rejected).
    verdicts = {}
    for line in open(os.path.join(ROOT, JUDGED), encoding="utf-8"):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("wave") in a.from_wave:
            # --from-wave is given in CHRONOLOGICAL order: a later wave's verdict supersedes an earlier wave's, and within a
            # wave the later row (the higher judgement round) wins. The row's ts is the BANKING time - this morning's verdicts
            # were banked this evening - so it must not order anything.
            key = _slug(str(row.get("subject")).split(" (")[0])
            rank = a.from_wave.index(row.get("wave"))
            if key not in verdicts or rank >= verdicts[key][0]:
                verdicts[key] = (rank, row)
    # A packet serves the stage its PLAN names as its node (unknown node: the wave was listed, so it serves), and a lane is
    # identified by its OUTPUT FILE where the plan gives one - so 'Q11-continue-and-cover' in a later wave supersedes
    # 'Q11-data-and-assets' in an earlier one because both write the same lane file.
    plan_of = {}
    for wave in a.from_wave:
        try:
            pl = json.load(open(os.path.join(ROOT, "atlas", "programme", "waves", wave + ".plan.json"), encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for ag in pl.get("agents", []):
            plan_of[(wave, _slug(ag.get("label", "")))] = {"node": ag.get("node") or pl.get("node"), "output": ag.get("output")}
    def lane_key(wave, label):
        info = plan_of.get((wave, _slug(label))) or {}
        out = info.get("output")
        return _slug(os.path.basename(out)[:-5]) if out and out.endswith(".json") and "/quarry" in out else _slug(label)
    rekeyed = {}
    for key, (rank, row) in list(verdicts.items()):
        k2 = lane_key(row.get("wave"), str(row.get("subject")).split(" (")[0])
        if k2 not in rekeyed or rank >= rekeyed[k2][0]:
            rekeyed[k2] = (rank, row)
    verdicts = rekeyed
    seen = {}
    for wave in a.from_wave:
        rpath = os.path.join(WAVES_DIR, wave, "returns.json")
        doc = json.load(open(rpath, encoding="utf-8"))
        labels, _ = _run_labels(doc["run_dir"])
        rel, handle = os.path.relpath(rpath, ROOT), _handle(rpath)
        for ret in doc["returns"]:
            label = str((labels.get(ret.get("agentId") or "", {}) or {}).get("label") or "")
            result = ret.get('result') or {}
            if isinstance(result, dict) and str(result.get('schema_version') or '').startswith(RETURN_FAMILY + '/'):
                label = 'build:' + str(result['packet'])
            m = re.match(r"(?:build|draft|judge|continue):([^:]+)", label)
            if m:
                node = (plan_of.get((wave, _slug(m.group(1)))) or {}).get("node")
                if node and not str(node).startswith(a.stage):
                    continue                      # the plan says this packet serves another stage
                key = lane_key(wave, m.group(1))
                current = seen.get(key) or {}
                if isinstance(result, dict) and str(result.get('schema_version') or '').startswith(RETURN_FAMILY + '/'):
                    current['builder_status'] = result.get('status')
                    current['builder_return'] = result
                seen[key] = {**current, "packet": m.group(1), "wave": wave, "result_path": rel, "result_handle": handle}
    # lanes the ledger has moved to another stage do not serve this one
    moved = []
    for line in open(os.path.join(ROOT, "corpus_friction", "campaign.jsonl"), encoding="utf-8"):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("record") == "amendment" and row.get("target") == a.stage and row.get("moves_to"):
            moved.append(row)
    packets, judged, unjudged, rejected, ruled = [], [], [], [], []
    for key, item in sorted(seen.items()):
        mover = next((m for m in moved if item["packet"] in str(m.get("ground", ""))), None)
        if mover:
            packets.append({**item, "moved_to": mover["moves_to"], "by_amendment": mover["id"]})
            continue
        row = (verdicts.get(key) or (None, None))[1]
        item.update({"judged": bool(row), "verdict": (row or {}).get("verdict"), "judge_context": (row or {}).get("judge_context"),
                     "judged_verdict_row": (row or {}).get("id")})
        builder_return = item.pop('builder_return', None)
        packets.append(item)
        if item.get('builder_status') is not None and item['builder_status'] != 'COMPLETE':
            rejected.append(f"{item['packet']} ({item['wave']}) has retained {item['builder_status']} work; judge acceptance cannot certify completion")
            if row: judged.append(row)
            continue
        if builder_return and not str(builder_return.get('schema_version')).endswith('/1'):
            from laplace.pipeline.workflow import packet_return_problems, packet_owner_read_verifier
            def resolve_stage_pin(value):
                path = Path(value)
                path = (path if path.is_absolute() else Path(ROOT) / path).resolve()
                if path != Path(ROOT).resolve() and Path(ROOT).resolve() not in path.parents:
                    raise ValueError('stage artifact escapes the declared checkout')
                return path
            problems = packet_return_problems(builder_return, schema_directory=SCHEMA_DIR,
                                               resolve_pin=resolve_stage_pin,
                                               verify_owner_read=packet_owner_read_verifier(ROOT))
            if problems:
                rejected.append(f"{item['packet']} ({item['wave']}) has invalid or moved result pins: "+'; '.join(problems))
                if row: judged.append(row)
                continue
        if row and row.get("verdict") == "ACCEPTED":
            entry = _plan_packet(item.get("wave"), item.get("packet"))
            if entry.get("profile_entry") and (not row.get("profile_verdict") or str(row.get("profile_verdict")).upper().startswith("OVERHEAD")):
                rejected.append(f"{item['packet']} ({item['wave']}) was accepted by its judge WITHOUT A CLEAN PROFILE "
                                f"(profile_verdict={row.get('profile_verdict')!r}) - a code packet is not accepted on correctness alone")
                judged.append(row)
                continue
            # THE DOOR REACHES IT OR IT IS A HALF (2026-09-22, found on P1's reach.py and P2's down.py): an accepted code
            # packet whose written package files the front door cannot import is a stage built beside the door, and its
            # numbers came from a script. Refused here, in the receipt, not in a note.
            if entry.get("writes_code") and entry.get("output"):
                written = _written_package_files(os.path.join(ROOT, entry["output"]) if not os.path.isabs(entry["output"]) else entry["output"])
                if written:
                    graph = _import_graph("src/atlas")
                    door = os.path.join(ROOT, "atlas", "src", "atlas", "front", "door.py")
                    reach, stack = set(), [door]
                    while stack:
                        f = stack.pop()
                        if f in reach: continue
                        reach.add(f); stack.extend(graph.get(f, ()))
                    unreachable = [w for w in written if os.path.join(ROOT, w) not in reach]
                    if unreachable:
                        rejected.append(f"{item['packet']} ({item['wave']}) was accepted by its judge with package files the FRONT DOOR "
                                        f"CANNOT REACH: {unreachable} - a stage the door does not call is a half (distil.py reachable)")
                        judged.append(row)
                        continue
            judged.append(row)
            continue
        # the closure loop's last step: a residual the orchestrator ruled on, RECORDED in the packet's own output file
        ruling = None
        for cand in glob.glob(os.path.join(ROOT, "evidence", "ATLAS_PROGRAMME", "**", item["packet"] + ".json"), recursive=True):
            try:
                ruling = (json.load(open(cand)).get("orchestrator_rulings") or {}).get("status")
            except (OSError, ValueError, AttributeError):
                ruling = None
            if ruling:
                item["orchestrator_ruling"] = {"file": os.path.relpath(cand, ROOT), "status": ruling}
                break
        if ruling and str(ruling).upper().startswith("ACCEPTED BY ORCHESTRATOR RULING"):
            ruled.append(item["packet"])
            if row:
                judged.append(row)
        elif not row:
            unjudged.append(f"{item['packet']} ({item['wave']}) was produced and never judged")
        else:
            rejected.append(f"{item['packet']} ({item['wave']}) was rejected by {row.get('judge_context')} [{row.get('id')}]")
            judged.append(row)
    residuals = rejected + unjudged
    status = "PASS" if (packets and not residuals) else "FAIL"
    receipt = {
        "schema": "atlas.stage-acceptance/1", "stage": a.stage, "status": status,
        "builder_context": a.builder_context,
        "produced_by": f"scripts/laplace-python scripts/distil.py stage-receipt {a.stage} "
                       + " ".join(f"--from-wave {w}" for w in a.from_wave),
        "produced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "computed_from": {"store": JUDGED, "waves": list(a.from_wave),
                          "rule": "PASS requires complete builders/current pinned results and every serving packet judged AND accepted"},
        "packets": packets,
        "why_not_pass": residuals,
        "accepted_by_recorded_orchestrator_ruling": ruled,
        "law": "a forged PASS is the failure this receipt exists to prevent; the status is computed from "
               "banked judgement rows, so it cannot be nicer than what a judge actually returned.",
    }
    judgement = {
        "schema": "atlas.purpose-judgement/1", "stage": a.stage,
        "verdict": "accept" if status == "PASS" else "reject",
        "judge_context": (judged[0].get("judge_context") if judged else "NONE"),
        "judges": [{"judge_context": r.get("judge_context"), "judge": r.get("judge"),
                    "subject": r.get("subject"), "verdict": r.get("verdict"), "row": r.get("id")}
                   for r in judged],
        "unjudged_packets": unjudged,
        "what_this_file_is": "a transcription, by the builder, of independent judgements already recorded in "
                             + JUDGED + ". It mints no judgement of its own and asserts no acceptance: its "
                             "verdict is 'accept' only if every serving packet was accepted by a judge in a "
                             "context different from the builder's.",
        "transcribed_by": a.builder_context,
        "produced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    for name, doc in (("acceptance.json", receipt), ("purpose_judgement.json", judgement)):
        json.dump(doc, open(os.path.join(stage_dir, name), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps({"record": "atlas.stage-receipt/1", "stage": a.stage, "status": status,
                      "verdict": judgement["verdict"], "packets": len(packets),
                      "rejected": rejected, "unjudged": unjudged,
                      "builder_context": a.builder_context, "judge_context": judgement["judge_context"],
                      "files": [os.path.relpath(os.path.join(stage_dir, n), ROOT)
                                for n in ("acceptance.json", "purpose_judgement.json")]},
                     indent=1, ensure_ascii=False))
    return 0


def cmd_returns(a) -> int:
    """The exact returns and verdicts of a finished wave, from its journal: what the next synthesis consumes."""
    rows = []
    for line in open(os.path.join(a.run_dir, "journal.jsonl")):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("type") == "result":
            rows.append({k: r.get(k) for k in ("label", "agentId", "result") if k in r} or r)
    json.dump({"record": "atlas.wave-returns/1", "run_dir": os.path.abspath(a.run_dir), "returns": rows}, open(a.out, "w"), indent=1, ensure_ascii=False)
    print(f"{a.out}: {len(rows)} returns, {os.path.getsize(a.out):,} bytes (~{_tokens(os.path.getsize(a.out)):,} tokens)")
    return 0


def cmd_inventory(a) -> int:
    """The old-work inventory, RE-MERGED from the lane files (no model): every file row with its lane, the verdict
    lists, literals and bypasses with their paths, reusable assets, findings, benchmarks - and each lane's standing
    taken from the stage's computed acceptance receipt, never asserted here."""
    qdir = os.path.join(ROOT, "evidence", "ATLAS_PROGRAMME", "quarry")
    standing = {}
    try:
        for pk in json.load(open(os.path.join(STAGE_EVIDENCE, "ATLAS-P0", "acceptance.json")))["packets"]:
            standing[pk["packet"]] = pk.get("verdict") or ("MOVED to " + str(pk.get("moved_to")))
    except (OSError, ValueError, KeyError):
        pass
    files, literals, bypasses, assets, findings, benchmarks, lanes = [], [], [], [], [], [], []
    for path in sorted(glob.glob(os.path.join(qdir, "Q*.json"))):
        lane = os.path.basename(path)[:-5]
        d = json.load(open(path, encoding="utf-8"))
        lanes.append({"lane": lane, "files": len(d.get("files", [])), "standing": standing.get(lane, "NO VERDICT ROW")})
        for row in d.get("files", []):
            files.append({**row, "lane": lane})
            literals += [{"path": row.get("path"), "literal": x, "lane": lane} for x in row.get("literals") or []]
            bypasses += [{"path": row.get("path"), "bypass": x, "lane": lane} for x in row.get("bypasses") or []]
        assets += [{"lane": lane, "asset": x} for x in d.get("reusable_assets") or []]
        findings += [{"lane": lane, "finding": x} for x in d.get("findings") or []]
        benchmarks += [{**x, "lane": lane} if isinstance(x, dict) else {"lane": lane, "benchmark": x} for x in d.get("benchmarks") or []]
    by_verdict, by_object = collections.defaultdict(list), collections.defaultdict(list)
    for row in files:
        by_verdict[str(row.get("verdict"))].append(row.get("path"))
        by_object[str(row.get("contract_object"))[:60]].append({"path": row.get("path"), "verdict": row.get("verdict"), "faithful": row.get("faithful")})
    accepted = sum(1 for l in lanes if l["standing"] == "ACCEPTED")
    out = {"schema": "atlas.quarry-inventory/2", "built": time.strftime("%Y-%m-%d") + " mechanical merge from the lane files, no model (scripts/distil.py inventory)",
           "status": f"{accepted} of {len(lanes)} lanes ACCEPTED by an independent judge; standing per lane below is read from evidence/ATLAS_PROGRAMME/ATLAS-P0/acceptance.json",
           "lanes": lanes, "files": files, "by_verdict": dict(by_verdict), "by_contract_object": dict(by_object),
           "literals": literals, "bypasses": bypasses, "reusable_assets": assets, "findings": findings, "benchmarks": benchmarks}
    target = os.path.join(qdir, "INVENTORY.json")
    json.dump(out, open(target, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(json.dumps({"files": len(files), "by_verdict": {k: len(v) for k, v in by_verdict.items()}, "literals": len(literals), "bypasses": len(bypasses),
                      "assets": len(assets), "findings": len(findings), "benchmarks": len(benchmarks), "lanes_accepted": f"{accepted}/{len(lanes)}"}))
    return 0


def cmd_apply_patches(a) -> int:
    """Apply accepted contract patch files, in the order given, to the unified contract (the ONE surface). A patch is
    {clause_id, op: add|replace, clause: {...}, after?: id}. Refuses an add over an existing id, a replace of a
    missing id, or a result with duplicate ids; writes atomically; prints exactly what changed."""
    path = os.path.join(ROOT, "atlas", "programme", "contract", "unified", "contract.json")
    contract = json.load(open(path, encoding="utf-8"))
    clauses = contract["clauses"]
    changed = []
    for f in a.files:
        doc = json.load(open(f, encoding="utf-8"))
        patches = doc.get("patches") if isinstance(doc, dict) and "patches" in doc else ([doc] if isinstance(doc, dict) and doc.get("op") else doc if isinstance(doc, list) else [])
        if not patches:
            raise SystemExit(f"{f}: no patch found (expected {{patches: [...]}}, one patch object, or a list) - refusing a silent no-op")
        for pt in patches:
            cid, op, clause = pt.get("clause_id") or (pt.get("clause") or {}).get("id"), pt.get("op"), pt.get("clause")
            ids = [c.get("id") for c in clauses]
            if not cid or not isinstance(clause, dict) or op not in ("add", "replace"):
                raise SystemExit(f"{f}: malformed patch {str(pt)[:120]}")
            clause.setdefault("id", cid)
            if op == "replace":
                if cid not in ids:
                    raise SystemExit(f"{f}: replace of absent clause {cid}")
                clauses[ids.index(cid)] = clause
            else:
                if cid in ids:
                    raise SystemExit(f"{f}: add over existing clause {cid}")
                anchor = pt.get("after")
                if anchor and anchor in ids:
                    clauses.insert(ids.index(anchor) + 1, clause)
                else:
                    lane = cid.split(".")[0]
                    last = max((i for i, c in enumerate(clauses) if str(c.get("id", "")).startswith(lane + ".")), default=len(clauses) - 1)
                    clauses.insert(last + 1, clause)
            changed.append(f"{op} {cid}  ({os.path.basename(f)})")
    ids = [c.get("id") for c in clauses]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate clause ids after apply: nothing written")
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
    os.write(fd, json.dumps(contract, indent=1, ensure_ascii=False).encode("utf-8")); os.close(fd); os.replace(tmp, path)
    print(json.dumps({"clauses": len(clauses), "changed": changed}, indent=1))
    return 0


def cmd_consumers(a) -> int:
    """Producer -> consumer map of code, by script: for every public function and class under the given package
    directories, how many OTHER production modules name it, and how many test files. A public symbol that no production
    module consumes is a half with no whole: it is either joined up, made private, or deleted. Exit 1 when --strict and
    any module has no production consumer at all."""
    import ast
    root = os.path.join(ROOT, a.production_root)
    src = {f: open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(root, "**", "*.py"), recursive=True)}
    tests = {f: open(f, encoding="utf-8").read() for f in glob.glob(os.path.join(ROOT, a.tests, "*.py"))}
    dead_modules, total, consumed = [], 0, 0
    for d in a.dirs:
        for f in sorted(glob.glob(os.path.join(ROOT, d, "**", "*.py"), recursive=True)):
            if f.endswith("__init__.py"):
                continue
            try:
                tree = ast.parse(src.get(f) or open(f, encoding="utf-8").read())
            except SyntaxError:
                continue
            rows = []
            for n in tree.body:
                if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("_"):
                    pat = re.compile(r"\b" + re.escape(n.name) + r"\b")
                    rows.append((n.name, sum(1 for g, t in src.items() if g != f and pat.search(t)), sum(1 for t in tests.values() if pat.search(t))))
            total += len(rows); consumed += sum(1 for r in rows if r[1])
            orphans = [r[0] for r in rows if not r[1]]
            if rows and not any(r[1] for r in rows) and not re.search(r"def main\(|__main__", src.get(f, "")):
                dead_modules.append(os.path.relpath(f, ROOT))
            print(f"{os.path.relpath(f, ROOT):<52} symbols {len(rows):>3}  consumed {sum(1 for r in rows if r[1]):>3}  no production consumer: {', '.join(orphans[:8])}{' ...' if len(orphans) > 8 else ''}")
    print(f"TOTAL public symbols {total} | consumed by production {consumed} | modules with NO production consumer and no entry point: {dead_modules}")
    return 1 if (a.strict and dead_modules) else 0


def _import_graph(package_root: str) -> dict:
    """file -> set(files) it imports, over one package by static AST; relative and absolute imports of the package."""
    import ast
    pkg_dir = os.path.join(ROOT, package_root)
    pkg_name = os.path.basename(pkg_dir.rstrip(os.sep))
    files = sorted(glob.glob(os.path.join(pkg_dir, "**", "*.py"), recursive=True))
    def module_of(f):
        rel = os.path.relpath(f, os.path.dirname(pkg_dir))[:-3].replace(os.sep, ".")
        return rel[:-9] if rel.endswith(".__init__") else rel
    by_module = {module_of(f): f for f in files}
    def resolve(name):
        while name:
            if name in by_module:
                return by_module[name]
            name = name.rpartition(".")[0]
        return None
    graph = {}
    for f in files:
        try:
            tree = ast.parse(open(f, encoding="utf-8").read())
        except (SyntaxError, OSError):
            graph[f] = set(); continue
        here = module_of(f)
        base = here if os.path.basename(f) == "__init__.py" else here.rpartition(".")[0]
        edges = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for al in n.names:
                    t = resolve(al.name)
                    if t: edges.add(t)
            elif isinstance(n, ast.ImportFrom):
                if n.level:
                    parts = base.split(".")
                    anchor = ".".join(parts[:len(parts) - (n.level - 1)]) if n.level > 1 else base
                    mod = anchor + ("." + n.module if n.module else "")
                else:
                    mod = n.module or ""
                for al in n.names:
                    t = resolve(mod + "." + al.name) or resolve(mod)
                    if t: edges.add(t)
        graph[f] = edges - {f}
    return graph


def cmd_reachable(a) -> int:
    """THE DOOR REACHES IT OR IT IS A HALF. Static import reachability from the front door (or any root file) over the
    system package: exit 1 for every given file the root cannot reach. Found 2026-09-22: wave P2's DOWN
    (front/down.py: winnow, build_down_view, question_gate) and wave P1's reach.py were accepted while nothing on the
    front door's import path named them - every number they reported came from a measurement script beside the door,
    and `consumers --strict` passed both because it passes a module when ANY symbol is named anywhere. The author:
    'Integration is integration.' A code packet's written files under the package must be reachable from the door, and
    stage-receipt refuses an accepted code packet whose files are not."""
    graph = _import_graph(a.package)
    root = os.path.abspath(os.path.join(ROOT, a.root))
    if root not in graph:
        print(f"root {a.root} is not a file of package {a.package}", file=sys.stderr); return 2
    seen, stack = set(), [root]
    while stack:
        f = stack.pop()
        if f in seen: continue
        seen.add(f); stack.extend(graph.get(f, ()))
    reachable = unreachable = unchecked = 0
    for path in a.files:
        f = os.path.abspath(os.path.join(ROOT, path))
        if f not in graph:
            unchecked += 1
            print(f"{path}: NOT CHECKED: not in package {a.package}; select the owning --package and --root")
            continue
        ok = f in seen
        reachable += int(ok)
        unreachable += int(not ok)
        print(f"{path}: {'REACHABLE' if ok else 'UNREACHABLE'} from {a.root}")
    print(f"reachable: {reachable} of {len(a.files)} reachable from {a.root}; "
          f"{unreachable} unreachable, {unchecked} not checked; "
          f"{len(seen)} package files on the door's path")
    return 1 if unreachable or unchecked else 0


def _written_package_files(report_path: str) -> list:
    """The system-package files a packet's report says it wrote (files_written / written_files), repo-relative."""
    try:
        doc = json.load(open(report_path, encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for key in ("files_written", "written_files", "files"):
        val = doc.get(key)
        if isinstance(val, dict):
            val = list(val.keys()) + [v for v in val.values() if isinstance(v, str)]
        for item in (val or []):
            s = item.get("path") if isinstance(item, dict) else item
            if not isinstance(s, str): continue
            s = s.split(" ")[0].strip()
            rel = os.path.relpath(os.path.abspath(os.path.join(ROOT, s)), ROOT)
            if rel.startswith(os.path.join("atlas", "src", "atlas")) and rel.endswith(".py"):
                out.append(rel)
    return sorted(set(out))


def cmd_gate(_a) -> int:
    """PreToolUse hook on the Workflow tool. It gates THIS campaign's wave only: a launch of atlas-wave (by scriptPath,
    or args carrying plan_path) needs a fresh preflight PASS for that same plan, and a launch of it BY NAME is refused
    because the session runs the copy it started with. Any other workflow, from any session, passes untouched."""
    try:
        event = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except ValueError:
        event = {}
    tool = event.get("tool_input") or {}
    args = tool.get("args") if isinstance(tool.get("args"), dict) else {}
    is_wave = "atlas-wave" in str(tool.get("scriptPath") or "") or tool.get("name") == "atlas-wave" or "plan_path" in args
    if event and not is_wave:
        return 0
    if tool.get("name") == "atlas-wave":
        print("Launch atlas-wave with scriptPath=.claude/workflows/atlas-wave.js, not by name: a saved workflow is read at "
              "session start, so a launch by name runs a stale copy.", file=sys.stderr)
        return 2
    try:
        mark = json.load(open(MARKER))
        fresh = time.time() - mark["ts"] < 20 * 60          # a PASS is for the launch that follows it, not for a later one
        same = not args.get("plan_path") or os.path.abspath(args["plan_path"]) == mark.get("plan")
    except (OSError, ValueError, KeyError):
        fresh = same = False
    if fresh and same:
        os.remove(MARKER)
        return 0
    print("atlas-wave launch blocked: no fresh preflight PASS for this plan. Run `scripts/laplace-python scripts/distil.py "
          "preflight PLAN.json`, tell the author the estimate, then launch by scriptPath with the same plan as args. "
          "Law: procedure/dispatch-distil-first.", file=sys.stderr)
    return 2


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("index", "join", "check", "pack"):
        s = sub.add_parser(name)
        s.add_argument("dir")
        s.add_argument("--rows", required=True)
        s.add_argument("--out")
        if name == "index":
            s.add_argument("--keep", required=True)
        if name == "join":
            s.add_argument("--provides", default="provides")
            s.add_argument("--consumes", default="consumes")
        if name == "check":
            s.add_argument("--require", required=True)
            s.add_argument("--cite")
            s.add_argument("--root", default=".")
        if name == "pack":
            s.add_argument("--ids", required=True)
    sub.add_parser("estimate").add_argument("files", nargs="+")
    sub.add_parser("preflight").add_argument("plan")
    sub.add_parser("gate")
    b = sub.add_parser("brief")
    b.add_argument("plan")
    b.add_argument("label")
    b.add_argument("--role", default="build", choices=("build", "judge", "synthesis"))
    b.add_argument("--round", type=int, default=1, help="a judge's round; it names the verdict file in section 0")
    b.add_argument("--out")
    sub.add_parser("outline").add_argument("file")
    sub.add_parser("cost").add_argument("run_dir")
    r = sub.add_parser("returns")
    r.add_argument("run_dir")
    r.add_argument("--out", required=True)
    w = sub.add_parser("wave-rows", help="a finished wave's workflow, dispatch and judgement rows, banked")
    w.add_argument("waves", nargs="*", help="wave names; default: every wave with a returns.json")
    w.add_argument("--partial", action="store_true", help="the wave is still running: bank what has returned, workflow row PENDING")
    w.add_argument("--from-dir", dest="from_dir", help="no run journal: bank from <DIR>/<label>/return.json and verdict.r*.json")
    w.add_argument("--wave", help="the wave name (default: the plan's)")
    w.add_argument("--plan", help="the wave plan, for its tiers and programme (default: <DIR>/plan.json)")
    w.add_argument("--provider", default="claude", choices=("claude", "codex"), help="which transport ran the packets")
    w.add_argument("--executor", help="override the executor disclosed on each row")
    w.add_argument("--sandbox", help="override the sandbox disclosed on each row")
    pf = sub.add_parser("profile", help="cProfile an entry and classify its time as inherent work or overhead")
    pf.add_argument("--top", type=int, default=12)
    pf.add_argument("entry", nargs=argparse.REMAINDER)
    lp = sub.add_parser("loops", help="census of Python loops that walk data instead of tensors")
    lp.add_argument("paths", nargs="+")
    lp.add_argument("--list", action="store_true")
    ww = sub.add_parser("watch", help="while a wave runs, bank each packet's rows as it returns (no model)")
    ww.add_argument("plan", help="the wave plan")
    ww.add_argument("--run-dir", dest="run_dir", help="skip the search and use this run directory")
    ww.add_argument("--interval", type=float, default=20.0, help="seconds between looks at the journal")
    ww.add_argument("--idle", type=float, default=3600.0, help="stop when the run directory has been still this long")
    wr = sub.add_parser("wave-returns", help="a finished wave's exact returns file, from the run journal "
                                             "the plan's packet labels identify")
    wr.add_argument("plan", help="the wave plan (the same JSON preflight read)")
    wr.add_argument("--wave", help="override the plan's wave name")
    wr.add_argument("--run-dir", dest="run_dir", help="skip the search and use this run directory")
    wr.add_argument("--out", help="default: evidence/ATLAS_PROGRAMME/waves/<wave>/returns.json")
    aw = sub.add_parser("author-words", help="the author's own typed messages as author-claim rows")
    aw.add_argument("transcript")
    aw.add_argument("--sweep", required=True, help="source_sweep, the row id prefix: AM-<sweep>-<n>")
    aw.add_argument("--session")
    aw.add_argument("--deposit", help="write the extracted messages beside the wave's evidence")
    aw.add_argument("--render-charter", action="store_true",
                    help="re-render the charter's his-words sections against the rows and name the row source")
    ro = sub.add_parser("residual-orders", help="a synthesis's carried residuals as open work orders")
    ro.add_argument("spec")
    ro.add_argument("--wave", required=True)
    ro.add_argument("--key", default="carried_residuals")
    ro.add_argument("--stamp", default=time.strftime("%Y%m%d", time.gmtime()))
    ro.add_argument("--default-target", default="the orchestrator")
    ro.add_argument("--programme", help=f"the programme the orders belong to (default: {DEFAULT_PROGRAMME})")
    sub.add_parser("apply-patches", help="apply accepted contract patch files, in order").add_argument("files", nargs="+")
    cs = sub.add_parser("consumers", help="producer -> consumer map of code: what nothing consumes")
    cs.add_argument("dirs", nargs="+")
    cs.add_argument("--production-root", default="src/atlas")
    cs.add_argument("--tests", default="atlas/tests")
    cs.add_argument("--strict", action="store_true")
    rc = sub.add_parser("reachable", help="the door reaches it or it is a half: import reachability of files from the front door")
    rc.add_argument("files", nargs="+")
    rc.add_argument("--root", default="src/atlas/front/door.py")
    rc.add_argument("--package", default="src/atlas")
    cr = sub.add_parser("check-return", help="a worker's written return against the schema its schema_version names")
    cr.add_argument("file")
    la = sub.add_parser("launch-args", help="the args a Claude Workflow launch passes: models and both schemas, resolved")
    la.add_argument("plan")
    sp = sub.add_parser("spawn-args", help="the collaboration.spawn_agent arguments Codex root uses for one packet")
    sp.add_argument("plan")
    sp.add_argument("label")
    sp.add_argument("--role", default="build", choices=("build", "judge", "synthesis"))
    sp.add_argument("--round", type=int, default=1)
    sub.add_parser("inventory", help="re-merge the old-work inventory from the lane files")
    sr = sub.add_parser("stage-receipt", help="a stage's acceptance receipt and purpose judgement, computed")
    sr.add_argument("stage")
    sr.add_argument("--from-wave", action="append", required=True)
    sr.add_argument("--builder-context", dest="builder_context", required=True)
    a = p.parse_args()
    return {"index": cmd_index, "join": cmd_join, "check": cmd_check, "pack": cmd_pack,
            "estimate": cmd_estimate, "preflight": cmd_preflight, "gate": cmd_gate, "inventory": cmd_inventory, "consumers": cmd_consumers, "reachable": cmd_reachable, "apply-patches": cmd_apply_patches, "brief": cmd_brief,
            "outline": cmd_outline, "cost": cmd_cost, "returns": cmd_returns, "wave-rows": cmd_wave_rows, "watch": cmd_watch, "loops": cmd_loops, "profile": cmd_profile,
            "wave-returns": cmd_wave_returns,
            "author-words": cmd_author_words, "residual-orders": cmd_residual_orders,
            "check-return": cmd_check_return, "launch-args": cmd_launch_args, "spawn-args": cmd_spawn_args,
            "stage-receipt": cmd_stage_receipt}[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
