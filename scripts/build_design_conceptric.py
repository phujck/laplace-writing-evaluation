#!/usr/bin/env python
"""Build the DESIGN conceptric — the interface-overhaul design authored as a
conceptric-class object, so the plan stops rotting as prose markdown and instead
renders through the ENGINE'S OWN /conceptric surface (PRM-20260721-design-conceptric).

His ruling (2026-07-21, in-session): "You're making all these design plans as prose
markdowns that rot. ... they might benefit from ... a _conceptric_?" So the design
becomes data in the HOUSE conceptric shape: a corpus friction ledger of typed rewire
records (``corpus_friction/design-interface.jsonl``) that ``corpus_ingest.corpus_network``
reconstructs into the {nodes, reach, ...} the existing DOWN operators serve — the exact
mechanism paper_falqon / eigenengine use (scripts/pour_conceptric.py's sibling). No
parallel format: the deliverable renders through the surface already on disk.

THE SOURCES (parsed, never transcribed) — the conceptric is REBUILT when they move:
  * DESIGN_2026-07-21_the-ui-overhaul.md — the 10 principles P1-P10 (+ tonight's dated
    amendments), the acts (KEYSTONE, ACT 0-7), the evidence entries E1-E7 (+E4b).
  * contract/promises.jsonl — the open INTERFACE promise rows (refs by id, bodies never
    copied — the refs-only house law).
  * contract/surfaces/*.yaml — the RED contract clauses (refs by located line). RED is a
    LIVE attribute of the contract: a wave flips a marker green on delivery, so the red
    census MOVES. This builder reads it live; the count is whatever the sources say
    (the whole point — never hand-drifted to a frozen number).

TYPED NODES: goal · principle · amendment · act · wave · promise · evidence · clause.
TYPED EDGES: wave-delivers-promise · clause-enforces-principle · wave-fills-act ·
             evidence-substantiates-act · amendment-amends-principle.
Every node carries its source ref on the record's ``ref`` field AND folded into its
essence, refs-only where the referent lives elsewhere.

WHAT A REF STORES (2026-08-21). The ref is a CONTENT ANCHOR — ``<path>:@<digest>``
(``laplace.manuscript.source_anchor``) — never a line number. Every source above grows by insertion,
and a stored offset turned each insertion into an edit to every ref below it: the ledger
drifted, ``--check`` went red, and nodes nobody had touched reported as changed. See
``_anchor``. Two refs stay id-locators (``contract/promises.jsonl#W-…``), which were
already keyed on content rather than position.

DETERMINISM / IDEMPOTENCE: records are emitted in a fixed order with stable ids
(``DC-NNNN``) and a fixed ts, so two runs produce a BYTE-IDENTICAL ledger. Any non-build
records already on the ledger (a human ``rule`` deposited through /corpus/friction) are
preserved ON THEIR OWN SIDE of the rebuilt block — rows written before it stay before,
rows the sanctioned append door added after it stay after (see ``split_foreign``) —
mirroring the pour's replayability discipline.

    python3 scripts/build_design_conceptric.py --repo-root .        # (re)emit
    python3 scripts/build_design_conceptric.py --check              # verify idempotent
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:                                            # the ref grammar is engine-level, not ours
    from laplace.manuscript import source_anchor
except ImportError:                             # run from a tree where src/ is not on the path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from laplace.manuscript import source_anchor

# ---------------------------------------------------------------------------
# constants — the one place names/paths live
# ---------------------------------------------------------------------------

CORPUS = "design-interface"               # the /conceptric ?corpus= name
BUILD_TAG = "build:design-conceptric"     # our records' `by`; others are preserved
FIXED_TS = "2026-07-21T00:00:00"          # the design's date — stable across runs
DESIGN_DOC = "DESIGN_2026-07-21_the-ui-overhaul.md"
PROMISES = "contract/promises.jsonl"
SURFACES_GLOB = "contract/surfaces"
LEDGER = f"corpus_friction/{CORPUS}.jsonl"
STUB_TEX = "design_conceptric/manuscript/main.tex"   # the registered tex root (stub)

ROOT = "paper://"                          # atomise_paper's apex (base leaf)
GOAL = "goal:design-interface"

# the logical-kind each design type projects onto (corpus_ingest.LOGICAL_KINDS — the
# add-node gate's taxonomy; the native design type rides the id prefix + essence).
KIND = {
    "goal": "goal", "cluster": "support", "principle": "postulate",
    "amendment": "definition", "act": "support", "wave": "support",
    "promise": "result", "evidence": "support", "clause": "support",
}

# clause category -> the principle it enforces (clause-enforces-principle). Categories
# are mechanical (verb/count/structural); the structural table is authored, small, and
# deterministic. Verbs enforce P3 (a verb is live or absent); counts enforce P2 (one
# truth, every number == its filter).
_STRUCTURAL_PRINCIPLE = {
    "work-order-consume-carries-evidence": "P3",
    "action-organ-complete": "P3",
    "state-machine-driven": "P6",
    "next-action-rendered": "P6",
}

# evidence entry -> the act it substantiates (evidence-substantiates-act). Authored map,
# grounded in each E-section's subject (the design doc's own cross-refs).
_EVIDENCE_ACT = {
    "E1": "ACT-0", "E2": "ACT-7", "E3": "ACT-2", "E4": "ACT-5",
    "E4b": "ACT-4", "E5": "ACT-3", "E6": "ACT-4", "E7": "ACT-7",
}


# ---------------------------------------------------------------------------
# source parsers — deterministic, refs-only
# ---------------------------------------------------------------------------

_P_RX = re.compile(r"^P(\d+) · \*\*(.+?)\*\*")
_ACT_RX = re.compile(r"^### (THE KEYSTONE|ACT \d+)\b")
_E_RX = re.compile(r"^### (E\d+[a-z]?) · (.+?)\s*$")
_AMEND_RX = re.compile(r"(20\d\d-\d\d-\d\d)\s*(?:amendment|\(.*?amendment)|AMENDED\s+(20\d\d-\d\d-\d\d)")


def _spans(lines: list[str], hits: list[tuple[int, Any]], stop: str | None = None
           ) -> list[tuple[Any, int, int]]:
    """Turn a list of (0-based lineno, payload) heading hits into (payload, start1, end1)
    spans; a span runs to the next hit (or a `stop` marker line, or EOF)."""
    out = []
    starts = [i for i, _ in hits]
    for k, (i, payload) in enumerate(hits):
        nxt = starts[k + 1] if k + 1 < len(starts) else len(lines)
        if stop is not None:
            for j in range(i + 1, nxt):
                if lines[j].strip() == stop:
                    nxt = j
                    break
        out.append((payload, i + 1, nxt))     # 1-based inclusive-ish span
    return out


def parse_principles(text: str) -> list[dict]:
    """P1-P10 with (number, headline, span) + any dated amendment inside the block."""
    lines = text.splitlines()
    hits = [(i, (m.group(1), m.group(2))) for i, ln in enumerate(lines)
            if (m := _P_RX.match(ln))]
    out = []
    for (num, headline), s, e in _spans(lines, hits, stop="---"):
        block = "\n".join(lines[s - 1:e])
        amend = None
        am = _AMEND_RX.search(block)
        if am:
            amend = am.group(1) or am.group(2)
        out.append({"n": int(num), "id": f"P{num}", "headline": headline.strip(),
                    "start": s, "end": e, "amend_date": amend})
    return out


def parse_acts(text: str) -> list[dict]:
    lines = text.splitlines()
    hits = []
    for i, ln in enumerate(lines):
        m = _ACT_RX.match(ln)
        if not m:
            continue
        label = m.group(1)
        nid = "KEYSTONE" if label == "THE KEYSTONE" else "ACT-" + label.split()[1]
        title = ln.lstrip("# ").split(" · ")[0].strip() if " · " not in ln else \
            ln.lstrip("# ").split(" · ")[1].strip()
        hits.append((i, (nid, title)))
    return [{"id": nid, "title": title, "start": s, "end": e}
            for (nid, title), s, e in _spans(lines, hits, stop="---")]


def parse_evidence(text: str) -> list[dict]:
    lines = text.splitlines()
    hits = [(i, (m.group(1), m.group(2))) for i, ln in enumerate(lines)
            if (m := _E_RX.match(ln))]
    return [{"id": eid, "title": title.strip(), "start": s, "end": e}
            for (eid, title), s, e in _spans(lines, hits)]


def _promise_lines(repo: Path) -> dict[str, tuple[dict, int]]:
    out: dict[str, tuple[dict, int]] = {}
    for i, ln in enumerate(_read(repo, PROMISES).splitlines(), 1):
        ln = ln.strip()
        if not ln:
            continue
        r = json.loads(ln)
        # contract/promises.jsonl carries MIXED record shapes: promise rows (keyed by "id")
        # and control rows the orchestrator banks against them — e.g. a defer record
        # ({"record":"defer","target":"PRM-…","defer_until":…}) that carries no "id" of its
        # own. A promise row is exactly one with an "id"; skip everything else so a control
        # row never breaks the parse (the promise's own status stays the truth of its openness).
        if "id" not in r:
            continue
        out[r["id"]] = (r, i)
    return out


_INTERFACE_OWNER = re.compile(r"\bACTS?\b|\bKEYSTONE\b|(?:^|[^A-Za-z])W-[a-z]")


def parse_open_interface_promises(repo: Path) -> list[dict]:
    """The OPEN promises whose owner names a design delivery unit (an ACT, the KEYSTONE,
    or a W-wave) — the interface promises, distinct from the personal/strategy rows
    owned by 'him' or 'Eigen (sessions...)'. Refs by id + line; bodies never copied."""
    out = []
    for pid, (r, lineno) in _promise_lines(repo).items():
        if r.get("status") != "open":
            continue
        if not _INTERFACE_OWNER.search(r.get("owner", "")):
            continue
        out.append({"id": pid, "owner": r.get("owner", ""), "line": lineno})
    return out


def _wave_of(owner: str) -> str | None:
    m = re.search(r"(W-[a-z][a-z0-9-]*)", owner)
    return m.group(1) if m else None


def _act_of(owner: str) -> str | None:
    m = re.search(r"\bACTS?\s+(\d+)", owner)
    if m:
        return "ACT-" + m.group(1)
    if "KEYSTONE" in owner:
        return "KEYSTONE"
    return None


def parse_red_clauses(repo: Path) -> list[dict]:
    """Every RED contract clause across contract/surfaces/*.yaml, refs by file+line.
    A red `counts` law expands over that surface's classes (desk carries 11), matching
    the operating-contract suite's per-class red checks. RED is live: this reflects the
    markers as they stand right now (a delivered wave flips them green)."""
    import yaml
    from laplace.web import desk
    out: list[dict] = []
    surf_dir = repo / SURFACES_GLOB
    for path in sorted(surf_dir.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        line_of = {i + 1: ln for i, ln in enumerate(raw.splitlines())}
        doc = yaml.safe_load(raw)
        surface = doc.get("surface") or path.stem
        rel = f"{SURFACES_GLOB}/{path.name}"

        def _ref(needle: str) -> str:
            """LOCATE the clause's own line, then store its CONTENT.

            This used to return 0 for a needle it could not find, and the emitted ref was
            `<file>:0` — a dead pointer no clause here checked, so a renamed verb produced a
            node refing nothing and stayed green. A ref is located or it is refused."""
            hits = [n for n, ln in line_of.items() if needle in ln]
            if not hits:
                raise SystemExit(f"BUILD: clause anchor not found in {rel}: {needle!r}")
            return f"{rel}:{source_anchor.anchor(raw.splitlines(), hits[0])}"

        for v in doc.get("verbs", []) or []:
            if v.get("red"):
                nm = v.get("name")
                out.append({"id": f"clause:{surface}:verb:{v.get('class')}:{nm}",
                            "cat": "verb", "surface": surface, "owed": v["red"],
                            "principle": "P3",
                            "essence": f"RED verb clause — {v.get('class')}.{nm} is live "
                                       f"or absent (P3); owed by {v['red']}",
                            "ref": _ref(f"name: {nm}")})
        counts = doc.get("counts") or {}
        if counts.get("red"):
            cln = _ref("counts:")
            # expand over the surface's classes (desk is the only surface with a class
            # roster today); each class chip is a red count check (chip == filter, P2).
            classes = [c["class"] for c in desk._DESK_CLASSES] if surface == "desk" else []
            if classes:
                for cls in classes:
                    out.append({"id": f"clause:{surface}:count:{cls}", "cat": "count",
                                "surface": surface, "owed": counts["red"], "principle": "P2",
                                "essence": f"RED count clause — {cls} chip == filter (P2); "
                                           f"owed by {counts['red']}",
                                "ref": cln})
            else:
                out.append({"id": f"clause:{surface}:count", "cat": "count",
                            "surface": surface, "owed": counts["red"], "principle": "P2",
                            "essence": f"RED count clause — chip == filter (P2); owed by "
                                       f"{counts['red']}",
                            "ref": cln})
        for s in doc.get("structural", []) or []:
            if s.get("red"):
                cl = s.get("clause")
                out.append({"id": f"clause:{surface}:{cl}", "cat": "structural",
                            "surface": surface, "owed": s["red"],
                            "principle": _STRUCTURAL_PRINCIPLE.get(cl, "P2"),
                            "essence": f"RED structural clause — {cl} (enforces "
                                       f"{_STRUCTURAL_PRINCIPLE.get(cl, 'P2')}); owed by {s['red']}",
                            "ref": _ref(cl)})
    return out


# ---------------------------------------------------------------------------
# the record emitters — deterministic order, stable ids
# ---------------------------------------------------------------------------

def _read(repo: Path, rel: str) -> str:
    return (repo / rel).read_text(encoding="utf-8")


def _anchor(repo: Path, rel: str, line: int) -> str:
    """The stored ref for a line this builder has LOCATED: ``<rel>:@<digest>`` keyed on the
    line's own text (``laplace.manuscript.source_anchor``), never on its offset.

    Why not the offset. Every source here grows by insertion — a promise row is appended,
    a principle is added above another, a red clause moves down its yaml — and a stored
    offset makes each of those an edit to EVERY ref below it: the ledger drifts, --check
    goes red, and the diff reports as changed a set of nodes whose prose nobody touched.
    An anchor moves with its line and changes only when the line's text changes.

    Spans are stored as their FIRST line for the same reason: only the heading was ever
    located, and the end offset was arithmetic over whatever followed it, so a section
    gaining a paragraph rewrote its own ref for no reason a reader would recognise."""
    return f"{rel}:{source_anchor.anchor(_read(repo, rel).splitlines(), line)}"


class Emitter:
    """Mints add-node / add-edge rewire records with stable DC-NNNN ids in call order."""

    def __init__(self) -> None:
        self.records: list[dict] = []
        self._seq = 0
        self._nodes: set[str] = set()

    def _id(self) -> str:
        self._seq += 1
        return f"DC-{self._seq:04d}"

    def node(self, nid: str, kind: str, parent: str, essence: str, ref: str) -> None:
        self._nodes.add(nid)
        self.records.append({
            "id": self._id(), "ts": FIXED_TS, "kind": "add-node", "node": nid,
            "target": None, "value": None, "by": BUILD_TAG, "status": "open",
            "parent": parent, "node_kind": kind,
            "essence": f"{essence} · src:{ref}", "ref": ref})

    def edge(self, node: str, target: str, edge_type: str) -> None:
        self.records.append({
            "id": self._id(), "ts": FIXED_TS, "kind": "add-edge", "node": node,
            "target": target, "value": edge_type, "by": BUILD_TAG, "status": "open"})


def build_records(repo: Path) -> tuple[list[dict], dict[str, Any]]:
    """Parse the sources and emit the full deterministic record set + a census dict."""
    text = _read(repo, DESIGN_DOC)
    principles = parse_principles(text)
    acts = parse_acts(text)
    evidence = parse_evidence(text)
    promises = parse_open_interface_promises(repo)
    clauses = parse_red_clauses(repo)

    em = Emitter()
    doc = DESIGN_DOC

    # -- the goal + the organising clusters (scaffold; the render's containment tree) --
    # The scaffold refs the principles SECTION HEADING, located. It used to be the typed
    # span `300-355` — a ref nothing measured, aimed at a section that had already slid out
    # from under it; a typed offset is the pure form of the defect the anchors cure.
    scaffold_ref = _anchor(repo, doc, next(
        i for i, ln in enumerate(text.splitlines(), 1)
        if ln.startswith("## The design principles")))
    em.node(GOAL, KIND["goal"], ROOT,
            "The interface overhaul, authored as a conceptric (his 2026-07-21 ruling: "
            "a design is nodes first, prose is a projection)",
            scaffold_ref)
    clusters = {
        "cluster:principles": "The design principles — the standing bar",
        "cluster:amendments": "Tonight's dated principle amendments",
        "cluster:acts": "The plan — acts and the keystone",
        "cluster:waves": "The delivery waves",
        "cluster:promises": "The open interface promises (tracked by name)",
        "cluster:evidence": "The evidence entries E1-E7",
        "cluster:clauses": "The red contract clauses (live)",
    }
    for cid, ess in clusters.items():
        em.node(cid, KIND["cluster"], GOAL, ess, scaffold_ref)

    # -- principles P1-P10 (postulates) --------------------------------------
    for p in principles:
        em.node(p["id"], KIND["principle"], "cluster:principles",
                p["headline"], _anchor(repo, doc, p["start"]))

    # -- amendments (definitions) amend their principle ----------------------
    amend_nodes = []
    for p in principles:
        if p["amend_date"]:
            aid = f"{p['id']}-amendment-{p['amend_date']}"
            amend_nodes.append((aid, p["id"]))
            em.node(aid, KIND["amendment"], "cluster:amendments",
                    f"{p['amend_date']} amendment to {p['id']} ({p['headline']})",
                    _anchor(repo, doc, p["start"]))

    # -- acts + keystone (support) -------------------------------------------
    act_ids = set()
    for a in acts:
        act_ids.add(a["id"])
        em.node(a["id"], KIND["act"], "cluster:acts", a["title"],
                _anchor(repo, doc, a["start"]))

    # -- waves (support) — derived from the promise owners; fill their act ----
    wave_owner_act: dict[str, str] = {}
    for pr in promises:
        w = _wave_of(pr["owner"])
        if w:
            wave_owner_act.setdefault(w, _act_of(pr["owner"]) or "KEYSTONE")
    for w in sorted(wave_owner_act):
        em.node(w, KIND["wave"], "cluster:waves",
                f"Delivery wave {w} (fills {wave_owner_act[w]})", f"{PROMISES}#{w}")

    # -- open interface promises (results) — refs by id, no bodies -----------
    for pr in promises:
        em.node(pr["id"], KIND["promise"], "cluster:promises",
                f"open interface promise (owner {pr['owner']}) — see {PROMISES} id={pr['id']}",
                _anchor(repo, PROMISES, pr["line"]))

    # -- evidence E1-E7 (support) --------------------------------------------
    ev_ids = set()
    for e in evidence:
        ev_ids.add(e["id"])
        em.node(e["id"], KIND["evidence"], "cluster:evidence", e["title"],
                _anchor(repo, doc, e["start"]))

    # -- red clauses (support) -----------------------------------------------
    for c in clauses:
        em.node(c["id"], KIND["clause"], "cluster:clauses", c["essence"], c["ref"])

    # === typed edges ========================================================
    # amendment-amends-principle
    for aid, pid in amend_nodes:
        em.edge(aid, pid, "amendment-amends-principle")
    # clause-enforces-principle
    for c in clauses:
        if c["principle"] in em._nodes:
            em.edge(c["id"], c["principle"], "clause-enforces-principle")
    # wave-fills-act
    for w, act in sorted(wave_owner_act.items()):
        if act in em._nodes:
            em.edge(w, act, "wave-fills-act")
    # wave-delivers-promise (deliverer = the wave, else the owning act/keystone)
    for pr in promises:
        deliverer = _wave_of(pr["owner"]) or _act_of(pr["owner"])
        if deliverer and deliverer in em._nodes:
            em.edge(pr["id"], deliverer, "wave-delivers-promise")
    # evidence-substantiates-act (act rests on the evidence)
    for e in evidence:
        act = _EVIDENCE_ACT.get(e["id"])
        if act and act in em._nodes and e["id"] in em._nodes:
            em.edge(act, e["id"], "evidence-substantiates-act")

    census = {
        "n_principles": len(principles),
        "n_amendments": len(amend_nodes),
        "n_acts": len(acts),
        "n_waves": len(wave_owner_act),
        "n_open_interface_promises": len(promises),
        "n_evidence": len(evidence),
        "n_red_clauses": len(clauses),
        "n_nodes": sum(1 for r in em.records if r["kind"] == "add-node"),
        "n_edges": sum(1 for r in em.records if r["kind"] == "add-edge"),
        "edge_types": sorted({r["value"] for r in em.records if r["kind"] == "add-edge"}),
    }
    return em.records, census


# ---------------------------------------------------------------------------
# ledger IO — preserve foreign records, rewrite ours, byte-stable
# ---------------------------------------------------------------------------

def _serialise(records: list[dict]) -> str:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)


def split_foreign(text: str, build_tag: str = BUILD_TAG) -> tuple[list[dict], list[dict]]:
    """Split a ledger's NON-build records by their side of the rebuilt block: the rows written
    before our block, and the rows written after it.

    Was a single ``foreign`` list re-emitted ahead of the block, and that made the sanctioned
    append door and this builder disagree about order: ``corpus_ingest.rewire_add`` appends at
    end-of-file (the one locked append), so every deposit through the door landed AFTER our block
    while ``emit`` insisted it belonged before it — and ``--check`` went red on a legitimate
    deposit until the builder was re-run (caught live by the growth-entry lane;
    WO-20260820-rewire-append-drifts-the-builder). Preserving each foreign row on the side it was
    written on cures that at the root: the door's natural write position is already what a fresh
    build emits, so the drift cannot be minted. It also keeps ``--check`` BYTE-EXACT rather than
    downgrading it to a set-compare that shrugs at order, and it keeps the overlay honest — a row
    appended after the block applies ON TOP of the built nodes (``apply_overlay`` drops an
    edit-essence / set-status whose node is not in ``leaves`` yet), which is what a deposit
    correcting a built node means. A ledger with no block of ours yet keeps the old behaviour:
    everything is 'before'."""
    before: list[dict] = []
    after: list[dict] = []
    seen_build = False
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if r.get("by") == build_tag:
            seen_build = True
            continue
        (after if seen_build else before).append(r)
    return before, after


def emit(repo: Path) -> tuple[str, dict[str, Any]]:
    """Compute the ledger text (foreign records preserved on their own side of our rebuilt
    block) without writing — the pure core the writer and the --check path share."""
    records, census = build_records(repo)
    path = repo / LEDGER
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    before, after = split_foreign(text)
    census["n_foreign_preserved"] = len(before) + len(after)
    census["n_foreign_after_block"] = len(after)
    return _serialise(before + records + after), census


def ensure_stub_tex(repo: Path) -> bool:
    """The registered tex root needs a main.tex for resolve_corpus to accept the corpus.
    A minimal stub (no \\input, no \\bibliography) — atomise_paper yields only paper://
    and references; every design node rides the friction overlay. Created if absent."""
    stub = repo / STUB_TEX
    if stub.is_file():
        return False
    stub.parent.mkdir(parents=True, exist_ok=True)
    stub.write_text(
        "% Stub tex root for the DESIGN conceptric (corpus 'design-interface').\n"
        "% The conceptric is authored entirely as friction records in\n"
        "% corpus_friction/design-interface.jsonl (scripts/build_design_conceptric.py);\n"
        "% this stub exists only so corpus_ingest.resolve_corpus accepts the corpus\n"
        "% (it requires main.tex). No sections, no bibliography by design.\n"
        "\\documentclass{article}\n"
        "\\begin{document}\n"
        "\\title{The interface overhaul, as a conceptric}\n"
        "The design lives in the conceptric, not in this tex.\n"
        "\\end{document}\n",
        encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--check", action="store_true",
                    help="verify the on-disk ledger already equals a fresh build (idempotent)")
    args = ap.parse_args()
    repo = Path(args.repo_root).resolve()
    sys.path.insert(0, str(repo / "src"))   # so `import laplace` resolves from repo

    text, census = emit(repo)
    path = repo / LEDGER
    if args.check:
        current = path.read_text(encoding="utf-8") if path.is_file() else ""
        if current != text:
            print("DRIFT: on-disk ledger != fresh build (run without --check to re-emit)",
                  file=sys.stderr)
            return 1
        print("idempotent: ledger matches a fresh build")
        print(json.dumps(census, indent=2))
        return 0

    created = ensure_stub_tex(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"wrote {LEDGER}  ({'stub tex created' if created else 'stub tex present'})")
    print(json.dumps(census, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
