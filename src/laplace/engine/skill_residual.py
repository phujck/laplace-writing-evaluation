"""The query-conditioned skill residual - can a skill's own claimed tasks route to it?

The instrument the fitness swap needed. The closure residual as first measured (the block
census, ``evidence/RESIDUAL_CENSUS_2026-08-19/``) asks each leaf to find itself: the leaf's
own banked vector handed to the router, arrival = CLOSED. That is the easiest possible
query, and at the skill grain it saturates - 31/31 transitioned skills CLOSED, 48 of 49
transitions inside one block (``evidence/FITNESS_SWAP_REPLAY_2026-08-20/REPORT.md``). A
signal with no variance cannot decide a lifecycle.

Conditioning the residual on the QUERY breaks the saturation by construction. A skill's
``SKILL.md`` frontmatter states, in the skill's own words, the task it claims to serve; its
trigger/purpose sections state when it should fire. Those are the queries a real caller
arrives with. So:

    for each claimed-task query q of skill s:
        rank(s, q) = position of s's SKILL.md in embed_router.route(q)'s answer list
        RR(s, q)   = 1/rank, or 0 when the router's answer never carries it
    R(s) = 1 - mean_q RR(s, q)                    the residual, in (0, 1]

R = 0 means every claimed task puts the skill first. R -> 1 means the skill's own claimed
tasks cannot surface it: findability failure, which is what lifecycle is actually about.

THE QUERIES ARE NAME-BLINDED. The skill's own name is stripped from every query, in both
``snake_case`` and ``space separated`` form, before embedding. A query that names the skill
is lexical self-retrieval wearing a task's clothes, and would rebuild the degeneracy this
module exists to escape.

BLIND BY CONSTRUCTION. Nothing here imports, opens, or names ``lifecycle.yaml``,
``assess.py``, or any transition record. The residual for all candidates is computed before
any join to which skills were promoted or demoted, and that ordering is enforced by this
module having no way to know. The full pre-registered definition - population, query
construction, descent geometry, the rank statistic, the threshold-to-rank mapping the join
uses, and the blind protocol - is
``evidence/FITNESS_SWAP_REPLAY_2026-08-20/query_conditioned/definition.md``, written before
the first residual was computed.

Read-only: no engine store, ledger, or banked tree is opened for writing. The one write
``embed_router.route`` would make on its own account (``.wire_proposals.jsonl``) is
redirected to a caller-supplied sink for the duration of a run - see ``proposals_sink``.

CLI:

    PYTHONPATH=src python3 -m laplace.engine.skill_residual --out rows_qc.json \\
        --sink /tmp/wire_sink.jsonl [--with-friction] [--limit-skills N]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterator

SKILLS_DIR = "src/laplace/pipeline/canon/skills"
FRICTION_DIR = "corpus_friction"

# The bond dimension this residual is read at. route() materializes leaf vectors exactly
# (full 384-d, no truncation), so this instrument runs at chi = d = 384. Stated because the
# residual's meaning depends on chi (WO-20260821-residual-saturates-at-low-chi: at chi<=2 it
# saturates, at chi>=64 it counts boundaries); any consumer of a residual as fitness states
# its chi or it is reading a coarseness rule, not fitness.
CHI = 384

Q_MAX = 4                    # claim-prose queries per skill (definition.md 2)
TRIGGER_ITEMS = 3            # trigger/purpose items after the description
MIN_ITEM_CHARS = 40          # shorter than this is a fragment, not a task description
FRICTION_MAX = 2             # secondary run only
TEXT_CAP = 480               # embed_router.TEXT_CAP - the model's window, with headroom

# the trigger/purpose headings, as registered
TRIGGER_HEADING = re.compile(
    r"(?i)^\s*(when to\b|when it\b|who runs\b|usage\b|purpose\b|why this exists\b|"
    r"what it (does|is)\b|capabilities\b)")


# ---------------------------------------------------------------------------
# the population
# ---------------------------------------------------------------------------

def candidate_skills(repo_root: Path | str) -> list[tuple[str, str]]:
    """(name, repo-relative SKILL.md path) for every canon skill, archive included.

    The archive is in scope on purpose: the lifecycle ledger transitions archived skills,
    and scoring only survivors would bias the ranking the swap is read off."""
    root = Path(repo_root)
    base = root / SKILLS_DIR
    out: list[tuple[str, str]] = []
    for path in sorted(base.glob("*/SKILL.md")) + sorted(base.glob("_archive/*/SKILL.md")):
        out.append((path.parent.name, str(path.relative_to(root))))
    return out


# ---------------------------------------------------------------------------
# the queries - what the skill says it is for
# ---------------------------------------------------------------------------

def name_blind(text: str, name: str) -> str:
    """Strip the skill's own name from a query, snake and spaced forms alike."""
    spaced = name.replace("_", " ")
    for token in (name, spaced):
        text = re.sub(re.escape(token), " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _frontmatter(text: str) -> str:
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else ""


def description_of(text: str) -> str | None:
    """The frontmatter ``description:`` - the skill's own one-line claim of its task."""
    fm = _frontmatter(text)
    if not fm:
        return None
    m = re.search(r"^description:\s*(.*?)(?=\n[A-Za-z_]+:|\Z)", fm, re.S | re.M)
    if not m:
        return None
    raw = m.group(1).strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1]
    raw = re.sub(r"\[[A-Z][A-Z_ ]+\]", " ", raw)          # the [EXPERIMENTAL] status tag
    return re.sub(r"\s+", " ", raw).strip() or None


def _sections(body: str) -> Iterator[tuple[str, str]]:
    """(heading, body) for every ``##``-level section of the markdown body."""
    parts = re.split(r"^(#{2,}\s*.*)$", body, flags=re.M)
    for i in range(1, len(parts) - 1, 2):
        heading = re.sub(r"^#+\s*", "", parts[i]).strip()
        yield heading, parts[i + 1]


def _items(section_body: str) -> list[str]:
    """Bullets if the section has them, else sentences. Fragments dropped."""
    bullets = [re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", ln).strip()
               for ln in section_body.splitlines()
               if re.match(r"^\s*(?:[-*+]|\d+\.)\s+\S", ln)]
    if bullets:
        cand = bullets
    else:
        flat = re.sub(r"\s+", " ", section_body).strip()
        cand = [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`*\[])", flat)]
    out = []
    for item in cand:
        item = re.sub(r"[*_`>]", "", item)
        item = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", item)     # markdown links -> their text
        item = re.sub(r"\s+", " ", item).strip()
        if len(item) >= MIN_ITEM_CHARS:
            out.append(item)
    return out


def trigger_items(text: str, limit: int = TRIGGER_ITEMS) -> list[str]:
    """Task-shaped items from the trigger/purpose sections, in document order."""
    body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.S)
    out: list[str] = []
    for heading, section in _sections(body):
        if not TRIGGER_HEADING.match(heading):
            continue
        for item in _items(section):
            out.append(item)
            if len(out) >= limit:
                return out
    return out


def friction_texts(repo_root: Path | str, name: str, limit: int = FRICTION_MAX) -> list[str]:
    """Rows in ``corpus_friction/*.jsonl`` that name the skill - task descriptions in the
    wild. SECONDARY only: 5 of 54 skills are named at all, so including them in the primary
    would make the ranks non-uniform (definition.md 2)."""
    root = Path(repo_root)
    out: list[str] = []
    for store in sorted((root / FRICTION_DIR).glob("*.jsonl")):
        try:
            lines = store.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            if name not in line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            blob = " ".join(str(row.get(k) or "") for k in
                            ("what", "why", "value", "essence", "text", "quote", "law", "title"))
            blob = re.sub(r"\s+", " ", blob).strip()
            if len(blob) >= MIN_ITEM_CHARS:
                out.append(blob)
            if len(out) >= limit:
                return out
    return out


def build_queries(repo_root: Path | str, name: str, skill_path: str,
                  with_friction: bool = False) -> list[dict[str, str]]:
    """The registered query set for one skill: description, then up to three trigger/purpose
    items, capped at Q_MAX; friction rows appended only for the secondary run."""
    text = (Path(repo_root) / skill_path).read_text(encoding="utf-8")
    queries: list[dict[str, str]] = []
    desc = description_of(text)
    if desc:
        queries.append({"source": "description", "raw": desc})
    for item in trigger_items(text):
        if len(queries) >= Q_MAX:
            break
        queries.append({"source": "trigger", "raw": item})
    if with_friction:
        for blob in friction_texts(repo_root, name):
            queries.append({"source": "friction", "raw": blob})
    for q in queries:
        q["text"] = name_blind(q["raw"], name)[:TEXT_CAP]
    return [q for q in queries if len(q["text"]) >= MIN_ITEM_CHARS]


# ---------------------------------------------------------------------------
# the rank statistic
# ---------------------------------------------------------------------------

def reciprocal_rank(rank: int | None) -> float:
    """RR = 1/rank when the router's answer carries the target, 0 when it does not.

    Absence scores 0 rather than being dropped: an unreachable skill is the strongest
    residual there is, and dropping it would let unreachability improve a skill's score."""
    return 0.0 if not rank else 1.0 / float(rank)


def residual(ranks: list[int | None]) -> float:
    """R = 1 - mean reciprocal rank, in (0, 1]. Empty query set is a refusal, not a 1.0."""
    if not ranks:
        raise ValueError("no queries - a skill with no claimed task has no residual to report")
    return 1.0 - sum(reciprocal_rank(r) for r in ranks) / len(ranks)


def rank_of(files: list[dict[str, Any]], target: str) -> int | None:
    """1-based position of ``target`` in the router's answer list, or None."""
    for i, hit in enumerate(files):
        if hit.get("file") == target:
            return i + 1
    return None


# ---------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def proposals_sink(sink: Path | str) -> Iterator[None]:
    """Point ``embed_router``'s wire-proposal ledger at a scratch file for the duration.

    ``route`` appends one row per confident geometric-only hit, and this bench asks for the
    router's WHOLE answer pool, so a run would otherwise pour thousands of rows per query
    into a live ledger. Scoring is untouched - the redirection is a store-discipline guard,
    not a change to the measurement."""
    from laplace.representation import embed_router
    previous = embed_router.PROPOSALS_FILE
    embed_router.PROPOSALS_FILE = str(Path(sink).resolve())
    try:
        yield
    finally:
        embed_router.PROPOSALS_FILE = previous


def measure(repo_root: Path | str, sink: Path | str, with_friction: bool = False,
            limit_skills: int | None = None, emit: Any = None) -> dict[str, Any]:
    """Compute R for every candidate skill. Returns the rows payload (also the CLI's output).

    One network load and one model load for the whole run; every query is the same
    ``embed_router.route`` fire the navigator makes, with the answer pool untruncated so a
    rank can be read and the failure-shaped rephrase off so the ranks stay comparable."""
    from laplace.engine import conceptric
    from laplace.representation import embed_router

    root = Path(repo_root)
    emit = emit or (lambda msg: print(msg, file=sys.stderr, flush=True))
    t0 = time.perf_counter()
    net = conceptric.load_network(root)
    emit(f"network: {len(net['nodes'])} nodes in {time.perf_counter() - t0:.1f}s")
    nodes = net["nodes"]

    skills = candidate_skills(root)
    if limit_skills:
        skills = skills[:limit_skills]

    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    with proposals_sink(sink):
        for idx, (name, path) in enumerate(skills, 1):
            if path not in nodes:
                excluded.append({"skill": name, "leaf": path,
                                 "why": "target leaf is not a node in the conceptric network"})
                emit(f"[{idx}/{len(skills)}] {name}: EXCLUDED (leaf absent from network)")
                continue
            queries = build_queries(root, name, path, with_friction=with_friction)
            if not queries:
                excluded.append({"skill": name, "leaf": path,
                                 "why": "no claimed-task prose survived the query rules"})
                emit(f"[{idx}/{len(skills)}] {name}: EXCLUDED (no queries)")
                continue
            qrows: list[dict[str, Any]] = []
            for q in queries:
                t1 = time.perf_counter()
                res = embed_router.route(root, net, q["text"], limit=10 ** 9,
                                         expand_failure_shaped=False)
                files = (res or {}).get("files") or []
                rank = rank_of(files, path)
                qrows.append({
                    "source": q["source"],
                    "query": q["text"],
                    "rank": rank,
                    "reciprocal_rank": round(reciprocal_rank(rank), 6),
                    "answer_pool": len(files),
                    "scored_nodes": (res or {}).get("visited"),
                    # NOTE (reported in REPORT.md): route's public answer cannot distinguish
                    # "absorbed into its tree parent" from "never scored" - both are simply
                    # absent from `files`. definition.md 4 asked for that diagnostic; it is
                    # not recoverable without changing the router, so it is not banked.
                    "seconds": round(time.perf_counter() - t1, 3),
                })
            ranks = [q["rank"] for q in qrows]
            rows.append({
                "skill": name,
                "leaf": path,
                "archived": "/_archive/" in path,
                "n_queries": len(qrows),
                "ranks": ranks,
                "mrr": round(sum(reciprocal_rank(r) for r in ranks) / len(ranks), 6),
                "residual": round(residual(ranks), 6),
                "queries": qrows,
            })
            emit(f"[{idx}/{len(skills)}] {name}: R={rows[-1]['residual']:.4f} ranks={ranks}")

    rows.sort(key=lambda r: (-r["residual"], r["skill"]))
    return {
        "definition": "evidence/FITNESS_SWAP_REPLAY_2026-08-20/query_conditioned/definition.md",
        "instrument": "laplace.engine.skill_residual.measure",
        "geometry": {"router": "embed_router.route", "limit": 10 ** 9,
                     "expand_failure_shaped": False, "beam": embed_router.BEAM,
                     "per_branch_width": embed_router.PER_BRANCH_WIDTH,
                     "path_decay": embed_router.PATH_DECAY,
                     "network_nodes": len(nodes)},
        "query_rules": {"q_max": Q_MAX, "trigger_items": TRIGGER_ITEMS,
                        "min_item_chars": MIN_ITEM_CHARS, "text_cap": TEXT_CAP,
                        "name_blinded": True, "with_friction": bool(with_friction)},
        "blind": ("this payload was produced by a module with no data path to the answer: it "
                  "neither imports nor opens the transition ledger, the incumbent fitness "
                  "module, or any record of which skills were promoted or demoted "
                  "(tests/test_skill_residual.py checks this structurally)"),
        "n_skills": len(rows),
        "excluded": excluded,
        "wall_seconds": round(time.perf_counter() - t0, 1),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--out", required=True, help="where the rows payload is written")
    ap.add_argument("--sink", required=True,
                    help="scratch path for embed_router's wire-proposal ledger")
    ap.add_argument("--with-friction", action="store_true",
                    help="secondary run: append friction-row queries (definition.md 2)")
    ap.add_argument("--limit-skills", type=int, default=None, help="smoke-test cap")
    args = ap.parse_args(argv)
    payload = measure(args.repo_root, args.sink, with_friction=args.with_friction,
                      limit_skills=args.limit_skills)
    Path(args.out).write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    print(f"wrote {args.out}: {payload['n_skills']} skills, "
          f"{payload['wall_seconds']}s, {len(payload['excluded'])} excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
