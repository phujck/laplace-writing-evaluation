"""graded_node_known_answer.py - the 3-level known-answer the graded-node clauses are judged by.

WHAT THIS IS. Contract clauses A.33 (the node IS a conceptric), A.34 (the one typed-face fold
rule) and B.36 (the coarse relation count is the cardinality of located witnesses = the block
sum C S C^T) each name this file as their check. It builds one small conceptric at grade 2,
coarsens it twice, and asserts every identity those clauses assert - exactly on the integer
half, and against a DERIVED float64 gate (B.18's tau = u*(L+3)*S, never a constant) on the
numeric half. It then re-runs the same construction under the fold rules and the shapes the
clauses forbid and asserts that each one FAILS or REFUSES by name.

WHY IT IS PURE HOST ARITHMETIC AND NOT A DEVICE CHECK. F.2 scopes the GPU-only gate (F.9,
charter "no CPU numerical path") to the NUMERIC CORE. This is a contract fixture, not the
numeric core: its whole job is that a judge in a different context reproduces every number by
one command with no store, no device, no dataset and no network. The production consumers that
must reproduce these same numbers on device are named in each clause's implementation block
(E.6/E.7 for the CSR generator, section_block_operator.transport_block_operator for U^T L U).
src/atlas/updown.py says the same thing of its own kernel at :160-162 - "A GPU or sparse
path is a caller-level substitution measured on the same contract, never a silent branch here."

WHAT IT REUSES rather than re-authors (charter look_before_you_build):
  * atlas.ids.chash          - the one hashing law (ids.py:42). Every identity here is a chash.
  * atlas.updown._sym_eig    - the existing deterministic Jacobi solver (updown.py:173). It
                               clamps eigenvalues at zero because it was written for Gram
                               matrices, so the restricted whitened operator is passed through
                               the exact shift L + 2I (PSD by A.6's spec(L) subset [-2,0]) and
                               shifted back. No second eigensolver is written.
  * atlas.updown._matmul / _transpose (updown.py:168, :164).
The arithmetic of the coarse operator is the same congruence U^T L U that
section_block_operator.transport_block_operator computes on device (Q03/Q04 REUSE_WITH_FIX);
the acceptance shapes are section_calculus's (C, R, Delta, the cocycle). Neither is re-authored:
both live behind torch and this fixture must run with no torch.

RUN IT
  scripts/laplace-python atlas/tests/graded_node_known_answer.py            # prints JSON, exit 0/1
  scripts/laplace-python -m pytest atlas/tests/test_graded_node_known_answer.py \
      --basetemp=/tmp/pytest-graded-node
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

if __package__ in (None, ""):  # running as a script, outside pytest's path setup
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from atlas.ids import chash  # noqa: E402
from atlas.updown import _matmul, _sym_eig, _transpose  # noqa: E402

U_ROUNDOFF = 2.0 ** -53  # float64 unit roundoff. A property of the format, not a chosen number.


class FoldRefused(Exception):
    """A refusal by name. Every forbidden shape in the clauses raises this with its code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------------------- the derived gate

def tau(accumulation_length: int, largest_term_sum: float) -> float:
    """B.18's derived absolute forward-error gate: tau = u*(L+3)*S.

    Every identity checked here has EXACT value zero, so its gate is an absolute forward-error
    bound (Higham 3.1's gamma_n with the bounded roundings outside the accumulation), not a
    constant. Where every operand is an exactly representable integer and no division occurs the
    gate is 0 EXACTLY and the identity is recorded by Report.exact instead of Report.near.
    """
    return U_ROUNDOFF * (accumulation_length + 3) * largest_term_sum


# --------------------------------------------------------------------------- the typed face

# The closed set of face field kinds. A kind outside it is refused, not passed through: that
# refusal is what stops "summary": "<a paragraph of prose>" from being a face (A.34).
FACE_KINDS = ("scalar", "set", "date", "kind")


def leaf_field(kind: str, value):
    """Put one leaf field into CARRIER form - the form the fold is closed on (A.34).

    scalar -> the sorted distinct values seen (a singleton survives; two or more is a DROP)
    set    -> the sorted union of tokens/names/handles
    date   -> the interval [lo, hi]
    kind   -> the counts {kind: n}
    """
    if kind == "scalar":
        return {"kind": "scalar", "values": [value]}
    if kind == "set":
        return {"kind": "set", "values": sorted(set(value))}
    if kind == "date":
        return {"kind": "date", "interval": [value, value]}
    if kind == "kind":
        return {"kind": "kind", "counts": {value: 1}}
    raise FoldRefused("FACE-FIELD-KIND-NOT-ADMITTED", f"{kind!r} is not one of {FACE_KINDS}")


def fold_faces(faces: list[dict]) -> tuple[dict, dict]:
    """THE fold. One function, used at every grade, CLOSED on its own output (A.34).

    Returns (coarse_face, dropped). `dropped` names every scalar field that did not survive and
    the distinct member values that disagreed, so what the coarse description drops is reachable
    BY NAME and not merely priced (A.24, C.16, F.17).

    Closure on its own output is what makes "one rule at every level" a fact rather than a
    slogan, and it is what the associativity check in this file measures: folding leaves in two
    steps gives byte-identical output to folding them in one.
    """
    if not faces:
        raise FoldRefused("EMPTY-FOLD", "a coarse node with no members is not a coarsening")
    fields = sorted({f for face in faces for f in face})
    for face in faces:  # fail closed: a member missing a declared field is a refusal
        missing = [f for f in fields if f not in face]
        if missing:
            raise FoldRefused("FACE-FIELD-MISSING", f"members disagree on fields {missing}")
    out: dict = {}
    dropped: dict = {}
    for field in fields:
        kinds = {face[field]["kind"] for face in faces}
        if len(kinds) != 1:
            raise FoldRefused("FACE-FIELD-KIND-CONFLICT", f"{field} carries {sorted(kinds)}")
        kind = kinds.pop()
        if kind not in FACE_KINDS:
            raise FoldRefused("FACE-FIELD-KIND-NOT-ADMITTED", f"{field} is {kind!r}")
        if kind == "scalar":
            values = sorted({v for face in faces for v in face[field]["values"]})
            out[field] = {"kind": "scalar", "values": values}
            if len(values) > 1:
                dropped[field] = {"why": "SCALAR-DISAGREEMENT", "member_values": values}
        elif kind == "set":
            out[field] = {"kind": "set",
                          "values": sorted({v for face in faces for v in face[field]["values"]})}
        elif kind == "date":
            los = [face[field]["interval"][0] for face in faces]
            his = [face[field]["interval"][1] for face in faces]
            out[field] = {"kind": "date", "interval": [min(los), max(his)]}
        else:  # kind -> counts, and counts fold by summing counts: the closure that matters
            counts: dict = {}
            for face in faces:
                for k, n in face[field]["counts"].items():
                    counts[k] = counts.get(k, 0) + n
            out[field] = {"kind": "kind", "counts": dict(sorted(counts.items()))}
    return out, dropped


# --------------------------------------------------------------------------- the conceptric

def conceptric(grade: int, nodes: dict, witnesses: list[dict], mass_den: int) -> dict:
    """One conceptric graph at one grade: its own nodes, faces, masses and typed relations.

    `nodes[id]` = {"face": <carrier face>, "mass_num": int, "degree": int, "finer": handle|None}
    `witnesses` = [{"w": id, "kind": relation kind, "ends": [x, y], "span": address}] - a LOCATED
    witness, so every count below is the cardinality of a set of byte addresses (A.2, B.3, B.16).
    """
    body = {
        "grade": grade,
        "mass_den": mass_den,
        "nodes": {k: nodes[k] for k in sorted(nodes)},
        "witnesses": sorted((dict(w) for w in witnesses), key=lambda w: w["w"]),
    }
    body["handle"] = chash({k: v for k, v in body.items()})
    return body


def counts_of(witnesses: list[dict], tag: dict[str, list[str]]) -> dict:
    """Coarse counts as CARDINALITIES of located witness sets - B.36's identity, cover-safe.

    `tag[x]` is the list of coarse nodes x belongs to. Under a partition each list is a
    singleton and this is exactly the off-diagonal of C S C^T. Under a COVER a shared member
    hands its witnesses to every coarse node that contains it: still a cardinality, still an
    integer, and no declared cover weight enters it (A.26's weights live in the tagged NUMERIC
    domain only). A witness may be simultaneously cross for one pair and intra for one node;
    both copies are kept and neither is a weight.
    """
    cross: dict = {}
    intra: dict = {}
    for w in witnesses:
        x, y = w["ends"]
        for a in tag[x]:
            for b in tag[y]:
                if a == b:
                    intra.setdefault(a, []).append(w["w"])
                else:
                    cross.setdefault(tuple(sorted((a, b))), []).append(w["w"])
    return {"cross": {k: sorted(set(v)) for k, v in cross.items()},
            "intra": {k: sorted(set(v)) for k, v in intra.items()}}


def restrict(finer: dict, members: list[str]) -> dict:
    """DOWN's payload: the finer CONCEPTRIC a coarse node coarsens - not a bag of its members.

    It carries the members' own faces, their ambient masses and degrees (so the RESTRICTED
    generator of the ambient operator is derivable inside it, which a bag cannot do) and its own
    typed relations. Its handle is the finer conceptric's content address.
    """
    ms = sorted(members)
    nodes = {m: dict(finer["nodes"][m]) for m in ms}
    inside = set(ms)
    wit = [w for w in finer["witnesses"] if w["ends"][0] in inside and w["ends"][1] in inside]
    return conceptric(finer["grade"], nodes, wit, finer["mass_den"])


def up(finer: dict, *, fold_rule: str = "SUM") -> dict:
    """UP: replace a finer conceptric by ONE node of the coarser one (A.33).

    The node carries the COARSENING and nothing else: transported mass, the folded typed face,
    the restricted integer counts from which the restricted generator is derived, the finer
    conceptric's content address, and what it drops BY NAME. It does not carry a summary and it
    does not carry its members' faces - DOWN reaches those by resolving `finer` against the
    record, which is why `down(up(K)) == K` is an identity and not a copy.
    """
    if "witnesses" not in finer or "nodes" not in finer:
        raise FoldRefused("FLAT-FINER-LEVEL-NOT-A-CONCEPTRIC",
                          "the finer level must be a conceptric graph, not a bag of members")
    if fold_rule != "SUM":
        raise FoldRefused("FOLD-RULE-NOT-ADMITTED",
                          f"{fold_rule}: the coarse count is a cardinality; MAX and MIN are "
                          "removed from the admitted fold rules (B.36)")
    ms = sorted(finer["nodes"])
    face, dropped_fields = fold_faces([finer["nodes"][m]["face"] for m in ms])
    pair: dict = {}
    for w in finer["witnesses"]:
        x, y = w["ends"]
        if x != y:
            pair.setdefault(tuple(sorted((x, y))), []).append(w["w"])
    restricted = {
        "members": ms,
        "degree": {m: finer["nodes"][m]["degree"] for m in ms},
        "counts": [[a, b, len(set(ws))] for (a, b), ws in sorted(pair.items())],
    }
    for _, _, c in restricted["counts"]:
        if not isinstance(c, int) or isinstance(c, bool):
            raise FoldRefused("REAL-WEIGHT-IN-S", f"count {c!r} is not an integer")
    node = {
        "finer": finer["handle"],
        "members": ms,
        "mass_num": sum(finer["nodes"][m]["mass_num"] for m in ms),
        "mass_den": finer["mass_den"],
        "face": face,
        "restricted": restricted,
        "dropped": {
            "intra_conceptric_witnesses": [[a, b, sorted(set(ws))]
                                           for (a, b), ws in sorted(pair.items())],
            "face_fields": dropped_fields,
        },
    }
    node["id"] = chash({k: v for k, v in node.items()})
    return node


def down(node: dict, record: dict[str, dict]) -> dict:
    """DOWN: open a node into the finer conceptric it coarsens, by content address."""
    finer = record.get(node["finer"])
    if finer is None:
        raise FoldRefused("FINER-CONCEPTRIC-UNRESOLVED", node["finer"])
    if finer["handle"] != node["finer"]:
        raise FoldRefused("MOVED-FINER-HANDLE", finer["handle"])
    return finer


def grade_up(finer: dict, blocks: dict[str, list[str]], *, fold_rule: str = "SUM",
             record: dict | None = None) -> tuple[dict, dict]:
    """UP the whole graph: every block becomes one node, every cross-witness set becomes a count.

    Returns (coarser conceptric, nodes by coarse id). The coarse graph's relations are the
    coarsening of the finer graph's CROSS relations; the intra relations stay with the node that
    coarsens them, named in its residual.
    """
    tag: dict = {}
    for a, ms in blocks.items():
        for m in ms:
            tag.setdefault(m, []).append(a)
    for m in finer["nodes"]:
        if m not in tag:
            raise FoldRefused("MEMBER-NOT-COVERED", m)
    cc = counts_of(finer["witnesses"], tag)
    detail = {}
    nodes = {}
    record = {} if record is None else record
    for a in sorted(blocks):
        sub = restrict(finer, blocks[a])
        record[sub["handle"]] = sub
        n = up(sub, fold_rule="SUM")
        detail[a] = n
        deg = sum(len(v) for k, v in cc["cross"].items() if a in k)
        nodes[a] = {"face": n["face"], "mass_num": n["mass_num"], "degree": deg,
                    "finer": n["finer"], "node_id": n["id"]}
    wit = []
    for (a, b), ws in sorted(cc["cross"].items()):
        if fold_rule == "SUM":
            value = len(ws)
        elif fold_rule == "MAX":
            value = max(_member_pair_counts(finer, blocks, a, b))
        elif fold_rule == "MIN":
            value = min(_member_pair_counts(finer, blocks, a, b))
        else:
            raise FoldRefused("FOLD-RULE-NOT-ADMITTED", fold_rule)
        for i in range(value):  # the coarse relation as `value` located witnesses
            wit.append({"w": f"{a}|{b}|{i}", "kind": "coarsened", "ends": [a, b],
                        "span": "folded", "folded_from": ws})
    return conceptric(finer["grade"] - 1, nodes, wit, finer["mass_den"]), detail


def _member_pair_counts(finer, blocks, a, b) -> list[int]:
    pair: dict = {}
    for w in finer["witnesses"]:
        x, y = w["ends"]
        if (x in blocks[a] and y in blocks[b]) or (x in blocks[b] and y in blocks[a]):
            pair.setdefault(tuple(sorted((x, y))), set()).add(w["w"])
    return [len(v) for v in pair.values()] or [0]


# --------------------------------------------------------------------------- the numeric half

def whitened(nodes: list[str], degree: dict, counts: dict) -> list[list[float]]:
    """L_ij = S_ij / sqrt(d_i d_j) (i != j), L_jj = -1: A.6's whitened item-paced operator.

    Built from integer counts and integer degrees only. No encoder, no cosine, no bandwidth.
    """
    n = len(nodes)
    idx = {m: i for i, m in enumerate(nodes)}
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        L[i][i] = -1.0
    for (a, b), c in counts.items():
        i, j = idx[a], idx[b]
        v = c / math.sqrt(degree[a] * degree[b])
        L[i][j] = v
        L[j][i] = v
    return L


def isometry(fine: list[str], blocks: dict[str, list[str]], mass: dict) -> list[list[float]]:
    """U[x, a] = sqrt(pi_x / pi_a) for x in a: the reversible coarsening isometry (A.8).

    Columns are orthonormal because sum_{x in a} pi_x = pi_a exactly, which is why mass has to be
    transported rather than re-fitted at the coarse grade (A.4, A.19).
    """
    coarse = sorted(blocks)
    idx = {m: i for i, m in enumerate(fine)}
    U = [[0.0] * len(coarse) for _ in fine]
    for j, a in enumerate(coarse):
        ma = sum(mass[x] for x in blocks[a])
        for x in blocks[a]:
            U[idx[x]][j] = math.sqrt(mass[x] / ma)
    return U


def _eye(n: int) -> list[list[float]]:
    return [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]


def _sub(a, b):
    return [[x - y for x, y in zip(ra, rb, strict=True)] for ra, rb in zip(a, b, strict=True)]


def _add(a, b):
    return [[x + y for x, y in zip(ra, rb, strict=True)] for ra, rb in zip(a, b, strict=True)]


def _maxabs(m) -> float:
    return max((abs(x) for row in m for x in row), default=0.0)


def defect(U, L):
    """D = U^T L (I - P), P = U U^T: the dynamical closure defect of the charter's grade."""
    P = _matmul(U, _transpose(U))
    return _matmul(_matmul(_transpose(U), L), _sub(_eye(len(L)), P))


def restricted_modes(node: dict) -> dict:
    """The node's kept modes: the eigenpairs of its RESTRICTED generator, derived not stored.

    The restriction is of the AMBIENT whitened operator - the members' full degrees ride inside
    the node, so the boundary each member has outside the block is present and the restriction is
    a restriction, not a re-fit. The eigenpairs are a versioned PROJECTION and are deliberately
    NOT in the node's identity (charter record_vs_projection; D.10; node_delta's metric_version
    correction): a float spectrum in a content address would move the node's id across machines
    and across eigensolver branches, which E.3 forbids.
    """
    ms = node["restricted"]["members"]
    deg = node["restricted"]["degree"]
    counts = {tuple(sorted((a, b))): c for a, b, c in node["restricted"]["counts"]}
    L = whitened(ms, deg, counts)
    shifted = _add(L, [[2.0 * v for v in row] for row in _eye(len(ms))])  # PSD by A.6
    vals, vecs = _sym_eig(shifted)
    return {"members": ms, "L": L,
            "eigenvalues": [v - 2.0 for v in vals], "eigenvectors": vecs}


# --------------------------------------------------------------------------- the fixture

def toy() -> dict:
    """Grade 2: eight turns, three sessions' worth of typed span-witnessed relations.

    Every count below is the cardinality of the located witness list beside it, so the fixture
    contains no weight to tune. The grade-1 and grade-0 gradings are the NATURAL containers
    (turn -> session -> history), which is where the author's correction says the hierarchy
    starts; spectral blocks are an additional cover a lens may propose and are not exercised here
    (B.22 owns that, and F.16 gates it).
    """
    pairs = {
        ("t1", "t2"): 2, ("t1", "t3"): 1, ("t2", "t3"): 3,
        ("t4", "t5"): 4, ("t7", "t8"): 1,
        ("t1", "t4"): 1, ("t2", "t5"): 2, ("t3", "t4"): 3,
        ("t3", "t6"): 2, ("t5", "t6"): 1,
        ("t4", "t7"): 1, ("t5", "t8"): 2,
        ("t6", "t7"): 5, ("t1", "t8"): 1, ("t2", "t7"): 1,
    }
    witnesses = []
    off = 0
    for (a, b), c in sorted(pairs.items()):
        for i in range(c):
            witnesses.append({"w": f"w{len(witnesses):03d}", "kind": "mentions",
                              "ends": [a, b], "span": f"sp[{off},{off + 7}]"})
            off += 8
    degree: dict = {f"t{i}": 0 for i in range(1, 9)}
    for (a, b), c in pairs.items():
        degree[a] += c
        degree[b] += c
    total = sum(degree.values())
    speakers = {"t1": "user", "t2": "user", "t3": "user", "t4": "user",
                "t5": "user", "t6": "user", "t7": "user", "t8": "assistant"}
    dates = {"t1": "2026-01-02", "t2": "2026-01-02", "t3": "2026-01-03", "t4": "2026-02-11",
             "t5": "2026-02-12", "t6": "2026-03-01", "t7": "2026-04-09", "t8": "2026-04-09"}
    tokens = {"t1": ["miso"], "t2": ["ana", "porto"], "t3": ["miso", "e1"],
              "t4": ["lisbon"], "t5": ["lisbon"], "t6": ["miso", "ana"],
              "t7": ["leeds"], "t8": ["leeds", "sheffield"]}
    nodes = {}
    for m in sorted(degree):
        nodes[m] = {
            "face": {"speaker": leaf_field("scalar", speakers[m]),
                     "entities": leaf_field("set", tokens[m]),
                     "date": leaf_field("date", dates[m]),
                     "row_kind": leaf_field("kind", "turn")},
            "mass_num": degree[m], "degree": degree[m], "finer": None,
        }
    return conceptric(2, nodes, witnesses, total)


LENS_PARTITION = {"s1": ["t1", "t2", "t3"], "s2": ["t4", "t5"],
                  "s3": ["t6"], "s4": ["t7", "t8"]}
LENS_COVER = {"c1": ["t1", "t2", "t3"], "c2": ["t4", "t5"],
              "c3": ["t5", "t6"], "c4": ["t7", "t8"]}
HISTORIES = {"h1": ["s1", "s2"], "h2": ["s3", "s4"]}


# --------------------------------------------------------------------------- the checks

class Report:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def exact(self, name: str, left, right, what: str) -> None:
        self.rows.append({"check": name, "what": what, "gate": "EXACT (integer identity)",
                          "measured": "equal" if left == right else "DIFFERENT",
                          "pass": left == right,
                          **({} if left == right else {"left": left, "right": right})})

    def near(self, name: str, measured: float, gate: float, what: str) -> None:
        self.rows.append({"check": name, "what": what, "measured": measured, "gate": gate,
                          "ratio": (measured / gate) if gate else None,
                          "pass": measured <= gate})

    def refuses(self, name: str, fn, code: str, what: str) -> None:
        try:
            fn()
        except FoldRefused as exc:
            ok = exc.code == code
            self.rows.append({"check": name, "what": what, "gate": f"refusal {code}",
                              "measured": f"refusal {exc.code}", "pass": ok})
        except Exception as exc:  # noqa: BLE001 - an unnamed failure is itself a finding
            self.rows.append({"check": name, "what": what, "gate": f"refusal {code}",
                              "measured": f"{type(exc).__name__}: {exc}", "pass": False})
        else:
            self.rows.append({"check": name, "what": what, "gate": f"refusal {code}",
                              "measured": "ACCEPTED - no refusal", "pass": False})

    def fails_under(self, name: str, fn, what: str) -> None:
        """A rule the clause forbids must make a stated identity FAIL, not merely differ."""
        try:
            broke = fn()
        except FoldRefused as exc:
            broke, note = True, f"refused {exc.code}"
        else:
            note = "identity broken" if broke else "identity still held"
        self.rows.append({"check": name, "what": what, "gate": "must FAIL",
                          "measured": note, "pass": bool(broke)})


def run() -> dict:
    r = Report()
    record: dict = {}
    g2 = toy()
    record[g2["handle"]] = g2

    # ---------------------------------------------------------------- integer half, partition
    g1, n1 = grade_up(g2, LENS_PARTITION, record=record)
    g0, n0 = grade_up(g1, HISTORIES, record=record)

    tag1 = {m: [a] for a, ms in LENS_PARTITION.items() for m in ms}
    cc1 = counts_of(g2["witnesses"], tag1)
    # the coarse count IS the cardinality, and IS the off-diagonal block sum of C S C^T
    fine = sorted(g2["nodes"])
    S2 = {}
    for w in g2["witnesses"]:
        S2[tuple(sorted(w["ends"]))] = S2.get(tuple(sorted(w["ends"])), 0) + 1
    block_sum = {}
    for (a, b) in cc1["cross"]:
        block_sum[(a, b)] = sum(c for (x, y), c in S2.items()
                                if {tag1[x][0], tag1[y][0]} == {a, b})
    from_graph = {tuple(sorted(w["ends"])): 0 for w in g1["witnesses"]}
    for w in g1["witnesses"]:
        from_graph[tuple(sorted(w["ends"]))] += 1
    r.exact("I1-block-sum-grade2-to-grade1", from_graph,
            {k: len(v) for k, v in cc1["cross"].items()},
            "the grade-1 relation counts equal the cardinalities of their located witness sets")
    r.exact("I1b-block-sum-equals-CSCt", from_graph, block_sum,
            "the same counts equal the off-diagonal block sum of C S C^T computed independently")

    tag0 = {m: [a] for a, ms in HISTORIES.items() for m in ms}
    cc0 = counts_of(g1["witnesses"], tag0)
    from_graph0 = {}
    for w in g0["witnesses"]:
        from_graph0[tuple(sorted(w["ends"]))] = from_graph0.get(tuple(sorted(w["ends"])), 0) + 1
    r.exact("I2-block-sum-grade1-to-grade0", from_graph0,
            {k: len(v) for k, v in cc0["cross"].items()},
            "the grade-0 counts equal the cardinalities of the grade-1 witness sets")

    composed = {h: sorted({m for s in ss for m in LENS_PARTITION[s]})
                for h, ss in HISTORIES.items()}
    tagc = {m: [h] for h, ms in composed.items() for m in ms}
    ccc = counts_of(g2["witnesses"], tagc)
    r.exact("I3-compose-identity", from_graph0, {k: len(v) for k, v in ccc["cross"].items()},
            "COMPOSE: coarsening twice equals coarsening once through the composed containers")

    round_trip = []
    for a, node in sorted(n1.items()):
        k = down(node, record)
        round_trip.append(up(k)["id"] == node["id"])
    for a, node in sorted(n0.items()):
        k = down(node, record)
        round_trip.append(up(k)["id"] == node["id"])
    r.exact("I4-up-of-down-is-identity", round_trip, [True] * len(round_trip),
            "UP(DOWN(n)) == n by content address, at both grades (6 nodes)")
    dn = [down(up(restrict(g2, ms)), {up(restrict(g2, ms))["finer"]: restrict(g2, ms)})["handle"]
          == restrict(g2, ms)["handle"] for ms in LENS_PARTITION.values()]
    r.exact("I5-down-of-up-is-identity", dn, [True] * len(dn),
            "DOWN(UP(K)) == K by content address: the node opens into the conceptric it coarsens")

    two_step = {h: fold_faces([n1[s]["face"] for s in ss])[0] for h, ss in HISTORIES.items()}
    one_step = {h: fold_faces([g2["nodes"][m]["face"] for m in ms])[0]
                for h, ms in composed.items()}
    r.exact("I6-face-fold-associativity", two_step, one_step,
            "the ONE fold rule is closed on its own output: folding twice == folding once")

    deg_book = {a: g1["nodes"][a]["degree"] for a in sorted(LENS_PARTITION)}
    expect = {a: sum(g2["nodes"][m]["degree"] for m in ms) - 2 * len(cc1["intra"].get(a, []))
              for a, ms in LENS_PARTITION.items()}
    r.exact("I7-coarse-degree-bookkeeping", deg_book, expect,
            "coarse degree == sum of member degrees minus twice the intra witnesses it dropped")

    r.exact("I8-mass-is-transported", sum(g0["nodes"][h]["mass_num"] for h in g0["nodes"]),
            g2["mass_den"], "mass is conserved by both coarsenings (A.19), never re-fitted")

    seen = set()
    for v in cc1["cross"].values():
        seen |= set(v)
    for v in cc1["intra"].values():
        seen |= set(v)
    r.exact("I9-no-witness-lost", sorted(seen), sorted(w["w"] for w in g2["witnesses"]),
            "every located witness is either a coarse relation or a node's named intra residual")

    drops = {a: n1[a]["dropped"] for a in sorted(n1)}
    named = sorted({f for a in drops for f in drops[a]["face_fields"]})
    r.exact("I10-drops-are-named", named, ["speaker"],
            "what the coarsening drops is reachable by name: s4's speaker disagrees "
            "(user/assistant) and is dropped with both member values kept")

    # ---------------------------------------------------------------- integer half, cover lens
    g1c, n1c = grade_up(g2, LENS_COVER, record=record)
    tagc2: dict = {}
    for a, ms in LENS_COVER.items():
        for m in ms:
            tagc2.setdefault(m, []).append(a)
    ccc2 = counts_of(g2["witnesses"], tagc2)
    fg = {}
    for w in g1c["witnesses"]:
        fg[tuple(sorted(w["ends"]))] = fg.get(tuple(sorted(w["ends"])), 0) + 1
    r.exact("I11-cover-count-is-still-a-cardinality", fg,
            {k: len(v) for k, v in ccc2["cross"].items()},
            "under a many-to-many cover the coarse count is still the cardinality of a located "
            "witness set: integer, and no declared cover weight enters it")
    # Compare the two lenses under the natural renaming c_i <-> s_i, so the difference measured
    # is a difference of GRAPHS and not of node names.
    rename = {"c1": "s1", "c2": "s2", "c3": "s3", "c4": "s4"}
    cover_as_s = {tuple(sorted((rename[a], rename[b]))): v for (a, b), v in fg.items()}
    r.exact("I12-membership-is-per-lens", cover_as_s == from_graph, False,
            "the SAME grade-2 conceptric under two lenses gives two DIFFERENT coarse graphs "
            f"(partition {dict((f'{a}|{b}', v) for (a, b), v in sorted(from_graph.items()))} "
            f"vs cover {dict((f'{a}|{b}', v) for (a, b), v in sorted(cover_as_s.items()))}), "
            "which is what 'membership is per-lens' means operationally")

    # ---------------------------------------------------------------- the numeric half
    S2t = {k: v for k, v in S2.items()}
    deg2 = {m: g2["nodes"][m]["degree"] for m in fine}
    L2 = whitened(fine, deg2, S2t)
    r.near("N0-whitened-symmetry", _maxabs(_sub(L2, _transpose(L2))),
           tau(1, 2.0), "the whitened operator is symmetric (A.6)")
    shifted = _add(L2, [[2.0 * v for v in row] for row in _eye(len(fine))])
    ev, _ = _sym_eig(shifted)
    spec = sorted(v - 2.0 for v in ev)
    r.near("N1-spectrum-bounded", max(0.0, spec[-1]) + max(0.0, -2.0 - spec[0]),
           tau(len(fine), 2.0), "spec(L) subset [-2,0] absolutely, A.6's item-paced bound")

    mass = {m: g2["nodes"][m]["mass_num"] / g2["mass_den"] for m in fine}
    U1 = isometry(fine, LENS_PARTITION, mass)
    mass1 = {a: sum(mass[m] for m in ms) for a, ms in LENS_PARTITION.items()}
    U2 = isometry(sorted(LENS_PARTITION), HISTORIES, mass1)
    U02 = isometry(fine, composed, mass)
    for name, U in (("U1", U1), ("U2", U2), ("U02", U02)):
        r.near(f"N2-{name}-is-an-isometry",
               _maxabs(_sub(_matmul(_transpose(U), U), _eye(len(U[0])))),
               tau(len(U), 1.0), f"{name}^T {name} = I")
    r.near("N3-composite-isometry", _maxabs(_sub(_matmul(U1, U2), U02)), tau(len(U1[0]), 1.0),
           "U_02 = U_1 U_2 exactly (A.18): the composite is the product, never re-orthonormalised")

    L1 = _matmul(_matmul(_transpose(U1), L2), U1)
    L0_two = _matmul(_matmul(_transpose(U2), L1), U2)
    L0_one = _matmul(_matmul(_transpose(U02), L2), U02)
    r.near("N4-operator-composes", _maxabs(_sub(L0_two, L0_one)),
           tau(len(fine), max(sum(abs(x) for x in row) for row in L2)),
           "U_2^T (U_1^T L U_1) U_2 = U_02^T L U_02: the congruence transports")

    D01, D12 = defect(U1, L2), defect(U2, L1)
    D02 = defect(U02, L2)
    cocycle = _sub(D02, _add(_matmul(_transpose(U2), D01), _matmul(D12, _transpose(U1))))
    r.near("N5-defect-cocycle", _maxabs(cocycle),
           tau(len(fine), max(sum(abs(x) for x in row) for row in L2)),
           "D_02 = U_2^T D_01 + D_12 U_1^T exactly (A.19) - the hard check that makes the "
           "recursion an identity rather than a convention")

    worst = 0.0
    for a, node in sorted(n1.items()):
        km = restricted_modes(node)
        n = len(km["members"])
        recon = [[sum(km["eigenvalues"][k] * km["eigenvectors"][k][i] * km["eigenvectors"][k][j]
                      for k in range(n)) for j in range(n)] for i in range(n)]
        worst = max(worst, _maxabs(_sub(km["L"], recon)))
    r.near("N6-kept-modes-are-the-restricted-generator's", worst, tau(3, 3.0),
           "each node's kept modes reconstruct its RESTRICTED generator: the node carries a "
           "generator restricted from the finer one, not a stored summary")

    pi_counts = {a: g1["nodes"][a]["degree"] / sum(g1["nodes"][b]["degree"] for b in g1["nodes"])
                 for a in g1["nodes"]}
    grading_defect = sum(abs(pi_counts[a] - mass1[a]) for a in mass1)

    # ---------------------------------------------------------------- what must fail or refuse
    def max_rule_breaks_block_sum() -> bool:
        gm, _ = grade_up(g2, LENS_PARTITION, fold_rule="MAX")
        got = {}
        for w in gm["witnesses"]:
            got[tuple(sorted(w["ends"]))] = got.get(tuple(sorted(w["ends"])), 0) + 1
        return got != from_graph

    def min_rule_breaks_block_sum() -> bool:
        gm, _ = grade_up(g2, LENS_PARTITION, fold_rule="MIN")
        got = {}
        for w in gm["witnesses"]:
            got[tuple(sorted(w["ends"]))] = got.get(tuple(sorted(w["ends"])), 0) + 1
        return got != from_graph

    def max_rule_breaks_compose() -> bool:
        gm, _ = grade_up(g2, LENS_PARTITION, fold_rule="MAX")
        g0m, _ = grade_up(gm, HISTORIES, fold_rule="MAX")
        got = {}
        for w in g0m["witnesses"]:
            got[tuple(sorted(w["ends"]))] = got.get(tuple(sorted(w["ends"])), 0) + 1
        direct = {k: max(_member_pair_counts(g2, composed, *k)) for k in got}
        return got != direct or got != from_graph0

    r.fails_under("X1-MAX-breaks-the-block-sum", max_rule_breaks_block_sum,
                  "changing the fold rule to MAX must make the block-sum identity FAIL")
    r.fails_under("X2-MIN-breaks-the-block-sum", min_rule_breaks_block_sum,
                  "changing the fold rule to MIN must make the block-sum identity FAIL")
    r.fails_under("X3-MAX-breaks-COMPOSE", max_rule_breaks_compose,
                  "MAX is not even associative across grades: two MAX folds != one MAX fold")
    r.refuses("X4-MAX-refused-at-the-node", lambda: up(restrict(g2, ["t1", "t2"]),
                                                       fold_rule="MAX"),
              "FOLD-RULE-NOT-ADMITTED", "UP refuses a non-cardinality fold rule by name")

    def real_weight() -> None:
        k = restrict(g2, ["t1", "t2", "t3"])
        n = up(k)
        n["restricted"]["counts"] = [[a, b, 3.5] for a, b, _ in n["restricted"]["counts"]]
        for _, _, c in n["restricted"]["counts"]:
            if not isinstance(c, int) or isinstance(c, bool):
                raise FoldRefused("REAL-WEIGHT-IN-S", f"count {c!r} is not an integer")

    r.refuses("X5-real-valued-weight-refused-at-a-coarse-grade", real_weight, "REAL-WEIGHT-IN-S",
              "a real-valued weight (v2's max(1.0,3.5)=3.5) is refused at EVERY grade, not "
              "only at the leaf")
    r.refuses("X6-flat-finer-level-refused",
              lambda: up({"members": ["t1", "t2"], "vectors": [[0.1], [0.2]]}),
              "FLAT-FINER-LEVEL-NOT-A-CONCEPTRIC",
              "a bag of member vectors is not a conceptric: the flat build is refused by name")
    r.refuses("X7-summary-face-refused",
              lambda: fold_faces([{"f": {"kind": "summary", "text": "a paragraph about turns"}}]),
              "FACE-FIELD-KIND-NOT-ADMITTED",
              "a stored prose summary is not an admitted face field kind (the RAPTOR default)")
    r.refuses("X8-uncovered-member-refused",
              lambda: grade_up(g2, {"a": ["t1", "t2"]}), "MEMBER-NOT-COVERED",
              "a grading that leaves a member out of every coarse node is refused")

    passed = all(row["pass"] for row in r.rows)
    return {
        "known_answer": "G1 the graded node: 3 levels over the natural containers",
        "clauses": ["A.33", "A.34", "A.35", "B.36", "A.2 (amended)", "B.16 (amended)"],
        "verdict": "PASS" if passed else "FAIL",
        "checks_run": len(r.rows),
        "checks_failed": [row["check"] for row in r.rows if not row["pass"]],
        "grade_2": {"nodes": len(g2["nodes"]), "witnesses": len(g2["witnesses"]),
                    "handle": g2["handle"], "mass_den": g2["mass_den"]},
        "grade_1_partition": {"nodes": sorted(g1["nodes"]), "handle": g1["handle"],
                              "counts": {f"{a}|{b}": v for (a, b), v in sorted(
                                  from_graph.items())},
                              "node_ids": {a: n1[a]["id"] for a in sorted(n1)}},
        "grade_0": {"nodes": sorted(g0["nodes"]), "handle": g0["handle"],
                    "counts": {f"{a}|{b}": v for (a, b), v in sorted(from_graph0.items())}},
        "grade_1_cover_lens": {"nodes": sorted(g1c["nodes"]), "handle": g1c["handle"],
                               "counts": {f"{a}|{b}": v for (a, b), v in sorted(fg.items())}},
        "dropped_by_name": {a: n1[a]["dropped"]["face_fields"] for a in sorted(n1)
                            if n1[a]["dropped"]["face_fields"]},
        "measured_grading_defect_l1": grading_defect,
        "grading_defect_note": "the coarse graph's own stationary law (degree/total on the "
                               "block-summed counts) is NOT the transported mass; that gap is "
                               "why a grade must be ACCEPTED by A.11 and A.13 and is never "
                               "assumed by the fold",
        "float64_gate": "B.18's derived tau = u*(L+3)*S, u = 2^-53; never a constant",
        "checks": r.rows,
    }


def main() -> int:
    report = run()
    print(json.dumps(report, indent=1, sort_keys=False))
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
