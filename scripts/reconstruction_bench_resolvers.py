#!/usr/bin/env python3
"""Structural-atom resolvers for the reconstruction bench, task set v2.

v1 (`reconstruction_bench_tasks.json`, frozen 2026-07-28) hard-codes DATED LIVE-STATE
strings as must-atoms - July's next-aim, "2/14 married", a leaf count of 12,335. The
2026-08-20 wake-rate run measured what that costs: eight of the eighteen tasks decayed
from pass to fail at FULL rate, the control fell 14/18 -> 6/18, and exactly one task
still moved anywhere on the rate ladder
(`evidence/WAKE_RATE_BENCH_2026-08-20/REPORT.md` §1b).

v2 replaces those strings with the SHAPE of a correct answer: a task names a resolver,
and the resolver reads the live store at score time and returns the atoms. The task file
stops carrying facts; it carries the questions and the addresses of the facts.

THE RESOLUTION RULE (registered, load-bearing): a task's atoms are resolved from the node
the wake itself names as that shard's ``source``. The bench then measures TRANSMISSION -
does the payload at rate R still carry what its own source says - and not store freshness.
Resolving a rendered shard's atoms from a row store the render has not yet caught up with
would score the render's staleness as a rate failure, which is a different experiment.

Every resolver is a pure function of (repo, arg): no network, no model, no clock.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

# --------------------------------------------------------------------------- helpers

_REG: dict[str, Callable[[Path, Any], Any]] = {}


def resolver(name: str):
    def deco(fn):
        _REG[name] = fn
        return fn
    return deco


def _read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8", errors="replace")


def _jsonl(repo: Path, rel: str) -> list[dict]:
    out = []
    for line in _read(repo, rel).splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def _handoff_latest_aim(repo: Path) -> str:
    """The LATEST aim section of HANDOFF.md - the exact span the next-aim shard lifts."""
    text = _read(repo, "HANDOFF.md")
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and "NEXT SESSION AIM" in ln:
            start = i
            break
    if start is None:
        raise ValueError("HANDOFF.md carries no '## ... NEXT SESSION AIM' heading")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "\n".join(lines[start:end])


def _law_amendments(repo: Path, bolded: bool = False) -> list[str]:
    """STANDING_LAW.md's dated amendment bullets, in file order.

    ``bolded=True`` also collects the bullets whose date is wrapped in ``**`` - the dated
    CLUSTER amendments, which carry a ``·``-separated list of rulings and no sentence end.
    The default stays False so ``law.latest_*`` keeps reading the plain-dated series it has
    always read (the bisection recorded that gap and did not fix it; neither does this).
    """
    from laplace.engine.self_corpus import standing_law
    pattern = r"^\*{0,2}\d{4}-\d\d-\d\d" if bolded else r"^\d{4}-\d\d-\d\d"
    return [line for line in standing_law(repo) if re.match(pattern, line)]


def _amendment_by_slug(repo: Path, slug: str) -> str:
    """The first amendment whose title carries ``slug``, cluster bullets included.

    Searching the bolded-inclusive list adds addresses; it removes none. The plain-dated
    bullets come first in file order, so every slug that resolved before resolves to the
    same amendment (checked, not assumed - see the T23 registration note in the task set).
    """
    for a in _law_amendments(repo, bolded=True):
        head = a.split("):", 1)[0].casefold()
        if slug.casefold() in head:
            return a
    raise ValueError(f"no standing-law amendment whose title carries {slug!r}")


def _clause(amendment: str, cap: int = 110) -> str:
    """The amendment's operative opening clause: everything after the dated
    parenthetical, up to the first sentence end, capped. Structural - it follows the
    file's wording automatically.

    The cap makes this atom blind past its own width. ``self_corpus.law_digest`` cuts the
    same tail at ``_LAW_CLAUSE_CAP``, so every digest cap at or above 110 carries this atom
    whole and the standing-law class scores identically for all of them - measured, 110 to
    160 indistinguishable (``evidence/WAKE_RATE_BENCH_2026-08-20/law_digest_bisection/``).
    ``_clause_rulings`` below is the sibling that measures past the prefix.
    """
    tail = amendment.split("):", 1)[1] if "):" in amendment else amendment
    tail = tail.strip()
    cut = tail.find(". ")
    if 0 < cut < cap:
        tail = tail[:cut]
    return tail[:cap].strip()


_RULING_SEP = " · "


def _clause_rulings(amendment: str, rulings: int = 2) -> str:
    """A cluster amendment's operative clause carried through its ``rulings``-th ruling.

    A cluster amendment banks a ``·``-separated list of rulings and has no sentence end, so
    ``law_digest`` truncates it at whatever ``_LAW_CLAUSE_CAP`` holds and ``_clause`` returns
    a flat 110-char prefix of it. This span ends on a ruling boundary instead: its length is
    a property of how the law is worded, not of a cap on either side. A digest that cuts
    shorter than the span fails the atom; one that carries the span passes it.

    Deliberately not clamped to the digest's cap. If the law is re-worded long enough that
    the span stops fitting, the task goes red - which is the reading the instrument owes
    ("the digest no longer carries this amendment's first two rulings"), not a defect in it.
    """
    tail = amendment.split("):", 1)[1] if "):" in amendment else amendment
    parts = tail.strip().split(_RULING_SEP)
    if len(parts) < rulings:
        raise ValueError(
            f"amendment carries {len(parts)} ruling(s), fewer than the {rulings} asked for")
    return _RULING_SEP.join(parts[:rulings]).strip()


# --------------------------------------------------------------------------- git / probe

@resolver("git.branch")
def _git_branch(repo: Path, arg=None) -> str:
    return subprocess.run(["git", "branch", "--show-current"], cwd=repo,
                          capture_output=True, text=True).stdout.strip()


@resolver("git.head_short")
def _git_head(repo: Path, arg=None) -> str:
    return subprocess.run(["git", "log", "-1", "--format=%h"], cwd=repo,
                          capture_output=True, text=True).stdout.strip()


# --------------------------------------------------------------------------- HANDOFF.md
# source node of the `next-aim` shard.

@resolver("handoff.aim_directive")
def _aim_directive(repo: Path, arg=None) -> str:
    """The aim's first bolded directive, first `arg or 90` normalized chars."""
    sec = _handoff_latest_aim(repo)
    m = re.search(r"\*\*(.+?)\*\*", sec, re.S)
    if not m:
        raise ValueError("the latest aim carries no bolded directive")
    return re.sub(r"\s+", " ", m.group(1)).strip()[: int(arg or 90)]


@resolver("handoff.aim_nodes")
def _aim_nodes(repo: Path, arg=None) -> list[str]:
    """Backticked ARMING_/SESSION_HANDOFF_/evidence nodes named in the latest aim."""
    sec = _handoff_latest_aim(repo)
    hits = [t for t in re.findall(r"`([^`]+)`", sec)
            if t.startswith(("ARMING_", "SESSION_HANDOFF_", "evidence/"))]
    if not hits:
        raise ValueError("the latest aim names no arming/handoff/evidence node")
    return sorted(set(hits))


@resolver("handoff.aim_axis_counts")
def _aim_axis(repo: Path, arg=None) -> list[str]:
    """The per-axis bundle counts the aim block reports - deep in the body, past the
    triple's 500-char `next` cap, so it exercises the shard and not the triple."""
    sec = _handoff_latest_aim(repo)
    m = re.search(r"bundle by axis\*\*: (.+?)(?:—|--|\n)", sec)
    if not m:
        raise ValueError("the latest aim carries no 'bundle by axis' line")
    return [re.sub(r"\s+", " ", m.group(1)).strip()]


@resolver("handoff.aim_open_ids")
def _aim_open_ids(repo: Path, arg="P") -> list[str]:
    """Ids the aim block names as open. arg 'P' = prediction rows, 'WO' = work orders."""
    sec = _handoff_latest_aim(repo)
    pat = r"\bP\d+\b" if arg == "P" else r"\bWO-\d{8}-[a-z0-9-]+"
    hits = sorted(set(re.findall(pat, sec)))
    if not hits:
        raise ValueError(f"the latest aim names no open {arg} ids")
    return hits


# --------------------------------------------------------------------------- STANDING_LAW.md
# source node of the `identity` block's standing_law list.

@resolver("law.amendment_date")
def _law_date(repo: Path, arg: str = "") -> str:
    return _amendment_by_slug(repo, arg).split(" ", 1)[0]


@resolver("law.amendment_clause")
def _law_clause(repo: Path, arg: str = "") -> str:
    return _clause(_amendment_by_slug(repo, arg))


@resolver("law.amendment_rulings")
def _law_clause_rulings(repo: Path, arg: str = "") -> str:
    """The named cluster amendment's clause through its second ruling - the one law atom
    that sits PAST ``_clause``'s 110-char prefix (WO-20260821-law-atom-past-the-prefix)."""
    return _clause_rulings(_amendment_by_slug(repo, arg), rulings=2)


@resolver("law.latest_date")
def _law_latest_date(repo: Path, arg=None) -> str:
    return _law_amendments(repo)[-1].split(" ", 1)[0]


@resolver("law.latest_clause")
def _law_latest_clause(repo: Path, arg=None) -> str:
    return _clause(_law_amendments(repo)[-1])


# --------------------------------------------------------------------------- OPEN_STACK.md
# source node of the `live-forks` and `wants` shards.

def _openstack_rows(repo: Path, prefix: str) -> list[list[str]]:
    rows = []
    for ln in _read(repo, "OPEN_STACK.md").splitlines():
        if ln.startswith(f"| {prefix}") and ln.count("|") >= 3:
            rows.append([c.strip() for c in ln.strip("|").split("|")])
    return rows


@resolver("openstack.author_fork_ids")
def _fork_ids(repo: Path, arg=None) -> list[str]:
    """Fork ids currently carrying the red (blocked-on-author) marker."""
    hits = [r[0] for r in _openstack_rows(repo, "F") if any("🔴" in c for c in r)]
    if not hits:
        raise ValueError("OPEN_STACK names no red author-fork")
    return sorted(set(hits))


@resolver("openstack.fork_subject")
def _fork_subject(repo: Path, arg: str = "") -> list[str]:
    """Any-of over the bolded subject of each red fork - what it turns on."""
    out = []
    for r in _openstack_rows(repo, "F"):
        if not any("🔴" in c for c in r):
            continue
        m = re.search(r"\*\*(.+?)[\*—.]", r[1])
        if m:
            out.append(re.sub(r"\s+", " ", m.group(1)).strip()[:60])
    if not out:
        raise ValueError("no red fork carries a bolded subject")
    return sorted(set(out))


@resolver("openstack.want_node")
def _want_node(repo: Path, arg: str = "W2") -> str:
    """The evidence node the named want's row cites (a path, first one)."""
    for r in _openstack_rows(repo, arg):
        if r[0] != arg:
            continue
        m = re.search(r"([A-Za-z0-9_./-]+\.md)", " ".join(r[1:]))
        if m:
            return m.group(1)
    raise ValueError(f"want row {arg} names no .md evidence node")


@resolver("openstack.want_ruling_id")
def _want_ruling(repo: Path, arg: str = "W2") -> str:
    for r in _openstack_rows(repo, arg):
        if r[0] != arg:
            continue
        m = re.search(r"(PV-\d{8}T\d{6}Z)", " ".join(r[1:]))
        if m:
            return m.group(1)
    raise ValueError(f"want row {arg} names no PV ruling id")


# --------------------------------------------------------------------------- typed stores
# source nodes of the `work-orders`, `conscience`, `bequest`, `projects` shards.

@resolver("work_orders.open_ids")
def _wo_open(repo: Path, arg=None) -> list[str]:
    """Open work-order ids that the HANDOFF aim block does NOT itself name - so the
    atom can only be answered from the work-orders shard body, never from the aim."""
    from laplace.engine import wake
    from laplace.pipeline.ledger import is_physical_store_defect
    account = wake.account(repo)
    wounded = [d for d in account.get("defects", [])
               if d.get("store") == "work_orders"
               and is_physical_store_defect(d)]
    if wounded:
        where = ", ".join(str(d.get("id") or d.get("path") or "store")
                          for d in wounded[:4])
        raise ValueError("work_orders ledger wounded; open_ids is only a lower bound "
                         f"({where})")
    status = {str(row["id"]): "open"
              for row in account["work_orders"]["open_rows"]}
    named = set(re.findall(r"\bWO-\d{8}-[a-z0-9-]+", _handoff_latest_aim(repo)))
    hits = sorted(i for i, s in status.items() if s in ("open", "raised", "amended") and i not in named)
    if not hits:
        raise ValueError("no open work order outside the aim block")
    return hits


@resolver("promises.open_ids")
def _prm_open(repo: Path, arg=None) -> list[str]:
    status: dict[str, str] = {}
    for row in _jsonl(repo, "contract/promises.jsonl"):
        rid = row.get("id") or ""
        if rid.startswith("PRM-"):
            status[rid] = str(row.get("status") or "")
    hits = sorted(i for i, s in status.items() if s == "open")
    if not hits:
        raise ValueError("contract/promises.jsonl carries no open promise")
    return hits


@resolver("bequest.nodes")
def _bequest_nodes(repo: Path, arg=None) -> list[str]:
    doc = json.loads(_read(repo, "holdout/BEQUEST.json"))
    hits = [ln.get("node") for ln in (doc.get("lines") or []) if ln.get("node")]
    if not hits:
        raise ValueError("holdout/BEQUEST.json carries no line node")
    return sorted(set(hits))


@resolver("bequest.fragments")
def _bequest_frags(repo: Path, arg=60) -> list[str]:
    doc = json.loads(_read(repo, "holdout/BEQUEST.json"))
    hits = [re.sub(r"\s+", " ", (ln.get("text") or "")).strip()[: int(arg)]
            for ln in (doc.get("lines") or []) if ln.get("text")]
    hits = [h for h in hits if len(h) > 20]
    if not hits:
        raise ValueError("holdout/BEQUEST.json carries no line text")
    return hits


def _registry(repo: Path):
    import sys
    if str(repo / "src") not in sys.path:
        sys.path.insert(0, str(repo / "src"))
    from laplace.pipeline.registry import marriage_roster, project_states  # type: ignore

    return project_states(repo), {r["name"]: r for r in marriage_roster(repo)}


@resolver("registry.marriage")
def _registry_marriage(repo: Path, arg=None) -> str:
    """The married fraction, exactly as the projects shard's TITLE states it. The title
    survives coarse-graining, so this atom is deliberately the shard's surviving half."""
    states, marriages = _registry(repo)
    n_married = sum(1 for m in marriages.values() if m.get("married"))
    return f"married {n_married}/{len(states)}"


@resolver("registry.never_run")
def _registry_never(repo: Path, arg=None) -> list[str]:
    """Project names the registry marks NEVER_RUN - these live in the shard BODY, which
    coarse-graining removes. The discriminating half of the projects task."""
    states, _ = _registry(repo)
    hits = sorted(str(s.get("name") or "") for s in states if str(s.get("state")) == "NEVER_RUN")
    hits = [h for h in hits if h]
    if not hits:
        raise ValueError("the registry lists no NEVER_RUN project")
    return hits


@resolver("meaning_tree.leaves")
def _tree_leaves(repo: Path, arg=None) -> str:
    """The banked map's leaf count, read through the same tree-only reader the wake's
    semantic block uses (``recursive_read.top_of_map``) - no embedder, no vectors."""
    import sys
    if str(repo / "src") not in sys.path:
        sys.path.insert(0, str(repo / "src"))
    from laplace.engine import recursive_read  # type: ignore

    n = recursive_read.top_of_map(repo).get("leaves")
    if not n:
        raise ValueError(".meaning_tree.json carries no leaf count")
    return str(n)


@resolver("threads.must_reach")
def _threads_reach(repo: Path, arg: str = "") -> list[str]:
    doc = json.loads(_read(repo, "holdout/THREAD_PROBES.json"))
    for p in doc.get("probes") or []:
        if p.get("id") == arg:
            hits = [str(x) for x in (p.get("must_reach") or [])]
            if not hits:
                raise ValueError(f"probe {arg} declares no must_reach")
            return hits
    raise ValueError(f"no thread probe with id {arg!r}")


@resolver("predictions.evidence_node")
def _pred_evidence(repo: Path, arg: str = "") -> str:
    for row in _jsonl(repo, "contract/predictions.jsonl"):
        if row.get("id") == arg:
            ev = str(row.get("evidence") or "")
            m = re.search(r"([A-Za-z0-9_./-]+/rows\.json|[A-Za-z0-9_./-]+\.md)", ev)
            if m:
                return m.group(1)
            raise ValueError(f"prediction {arg} names no evidence node")
    raise ValueError(f"no prediction row {arg!r}")


# --------------------------------------------------------------------------- floor blocks
# source nodes of the `spine`, `node_forms` and `descend` top-level fixed_point keys - the
# three blocks that WAKE_RATE_BENCH_2026-08-20/REPORT_v2.md §6 measured at 3,813 chars /
# 17.4% of the person floor, scored by NO task in v1 or v2 (a null measurement, never
# evidence of no value). None of the three is in `_BUDGET_SACRIFICE_RANK` - self_corpus.py's
# _grade0() attaches spine/node_forms/descend OUTSIDE the `shards` list lever 2 walks, so
# they ride every rate by construction, same footing as identity/triple/probe. Declared
# rate_invariant here for that reason, not asserted - the ground-truth pass and the ladder
# both check it.

def _grade0_source(repo: Path) -> str:
    """The exact text of self_corpus._grade0() - the source node for spine/node_forms/
    descend, sliced to that one function so a same-named field on _grade1/_grade2 (both also
    carry 'call'/'fire' descend keys) can never be matched by accident."""
    text = _read(repo, "src/laplace/engine/self_corpus.py")
    start = text.index("\ndef _grade0(")
    end = text.index("\ndef _enforce_grade0_budget(", start)
    return text[start:end]


@resolver("spine.reflex_is")
def _spine_reflex_is(repo: Path, arg=None) -> str:
    """The spine's own account of itself - hello_reflex's 'is' field (spine.py), the first
    concatenated string fragment. Read live so a rewording re-anchors the atom."""
    text = _read(repo, "src/laplace/engine/spine.py")
    m = re.search(r'"is":\s*\(\s*"([^"]+)"', text)
    if not m:
        raise ValueError("spine.py's hello_reflex carries no 'is' field")
    return m.group(1)


@resolver("spine.fire_call")
def _spine_fire_call(repo: Path, arg=None) -> str:
    """How a reader fires the spine directly, outside the wake payload."""
    text = _read(repo, "src/laplace/engine/spine.py")
    m = re.search(r'"fire":\s*"([^"]+)"', text)
    if not m:
        raise ValueError("spine.py's hello_reflex carries no 'fire' field")
    return m.group(1)


@resolver("node_forms.dispatch_verb")
def _node_forms_verb(repo: Path, arg=None) -> str:
    """The addressing grammar's dispatch verb, self_corpus.py's node_forms block (the
    'reconstruct(node, goal), never read(file)' sentence)."""
    m = re.search(r"the dispatch verb is (reconstruct\([^)]*\)), never (read\([^)]*\))",
                  _grade0_source(repo))
    if not m:
        raise ValueError("self_corpus.py's node_forms carries no dispatch-verb sentence")
    return f"{m.group(1)}, never {m.group(2)}"


@resolver("node_forms.resolver_call")
def _node_forms_resolver(repo: Path, arg=None) -> str:
    """How a node name is resolved to its source."""
    m = re.search(r'Resolve any node\s*"?\s*\n?\s*"?to its source with ([^.]+\.py)',
                  _grade0_source(repo), re.S)
    if not m:
        raise ValueError("self_corpus.py's node_forms names no resolver script")
    return re.sub(r"\s+", " ", m.group(1)).strip()


@resolver("descend.call_grade1")
def _descend_call(repo: Path, arg=None) -> str:
    """Grade 0's embedded descend block: what firing it reconstructs."""
    m = re.search(r'"call":\s*"([^"]+)"', _grade0_source(repo))
    if not m:
        raise ValueError("self_corpus.py's grade-0 descend block carries no 'call' field")
    return m.group(1)


@resolver("descend.fire_grade1")
def _descend_fire(repo: Path, arg=None) -> str:
    """The literal call that fires grade 1."""
    m = re.search(r'"fire":\s*"(reconstruct_self\([^"]+)"', _grade0_source(repo))
    if not m:
        raise ValueError("self_corpus.py's grade-0 descend block carries no 'fire' field")
    return m.group(1)


# --------------------------------------------------------------------------- API

def resolve_entry(repo: Path, entry: Any) -> Any:
    """One atom spec -> a literal atom (str) or an any-of group (list[str])."""
    if isinstance(entry, dict):
        name = entry["resolve"]
        if name not in _REG:
            raise KeyError(f"unknown resolver {name!r}")
        return _REG[name](repo, entry.get("arg"))
    return entry


def resolve_atoms(repo: Path, atoms: list) -> list:
    return [resolve_entry(repo, a) for a in atoms]


def resolve_task_set(repo: Path, tasks: list[dict]) -> dict[str, list]:
    """Every task's atoms, resolved once against the live store. Raises on any
    resolver that cannot find its fact - a v2 task whose address has gone stale is a
    LOUD failure of the instrument, never a silent zero on the scoreboard."""
    return {t["id"]: resolve_atoms(repo, t["atoms"]) for t in tasks}


if __name__ == "__main__":  # a bare run prints what the live store resolves to today
    import sys

    repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    tf = repo / "scripts/reconstruction_bench_tasks_v2.json"
    tasks = json.loads(tf.read_text())["tasks"]
    for tid, atoms in resolve_task_set(repo, tasks).items():
        print(f"{tid}: {json.dumps(atoms, ensure_ascii=False)[:300]}")


@resolver("triple.full_record")
def _triple_full_record(repo: Path, arg=None) -> str:
    """The triple's next block names the full next-aim record (HANDOFF.md's latest aim, the
    'Full record' line). Read live so each close's re-render re-anchors the atom - the triple
    is a render whose row-sources move, unlike the static source strings of T19-T21."""
    m = re.search(r"Full record: `([^`]+)`", _read(repo, "HANDOFF.md"))
    if not m:
        raise ValueError("HANDOFF.md carries no 'Full record' line")
    return m.group(1)


@resolver("triple.top_fork")
def _triple_top_fork(repo: Path, arg=None) -> str:
    """The triple's blocked_on_author block heads with the first LIVE stratum-1 fork. Rows
    also hold retired forks, so the anchor is the first F-row still marked live (the red
    marker), read live from OPEN_STACK.md."""
    for line in _read(repo, "OPEN_STACK.md").splitlines():
        m = re.match(r"^\| (F\d+) \|", line)
        if m and "\U0001F534" in line:
            return m.group(1)
    raise ValueError("OPEN_STACK.md carries no live stratum-1 fork row")
