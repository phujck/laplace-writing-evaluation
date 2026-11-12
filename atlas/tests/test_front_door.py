"""test_front_door.py - the tests packet J2-INTEGRATION wrote, and nothing else.

Run exactly this file:

    scripts/laplace-python -m pytest atlas/tests/test_front_door.py -x -q \
        --basetemp=/tmp/pytest-j2-front

What is asserted here, and why each one is a packet requirement rather than a courtesy:

  THE FACE IS A RANGE REDUCTION AND EQUALS THE OLD FOLD ON EVERY DECLARED COLUMN of every
  carrier row kind of both benchmarks - against ``fold_oracle``, the deleted A.34 Python fold
  kept in the tests as an INDEPENDENT control (so the comparison cannot be satisfied by a
  change to the reduction). 41 of 41 where the J1 synthesis got 39 of 41: the two it missed
  were ``distinct_codes``' fixed 31-bit packing and the missing ``bool`` carrier.
  ADMITS ANSWERS ALL FIVE CONDITION KINDS FROM BOTH REDUCTIONS, dense and sparse, with
  decided_in + excluded + open == 1 on every range, at the row-scale worst case where the dense
  form refuses BY NAME.
  THE COARSE RELATION COUNTS AGREE, sparse against dense, at the lens's OWN frontier size, and
  the dense form refuses by name past its declared device budget.
  THE ANSWER NAMES ITS CONTENT: twenty answers' handles resolve to the same bytes IN A SECOND
  PROCESS, which is the pattern ``test_record_persistence.py:183`` establishes for rows.
  EVERY DECLARED CARRIER ROW IS ACCOUNTED FOR: bound + named-unseated == declared, and the read
  supplies the unseated ones instead of quietly answering over a smaller record.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import torch

from atlas.front import faces as FA
import atlas.front.read as RD
from atlas.front.door import FrontDoor
from atlas.front.draw import runs_of_the_draw
from atlas.front.question import compile_question
from atlas.grading import face as F
from atlas.grading import ranges as R
from atlas.grading import tree as T
from atlas.record.columns import NULL_OF, date_of_key, datetime_of_key
from fold_oracle import fold_faces, leaf_face

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="the numeric core is GPU")


# --------------------------------------------------------------------------- the fixtures
def _door(tmp_path_factory, name: str) -> FrontDoor:
    root = tmp_path_factory.mktemp(f"front-{name}")
    door = FrontDoor(runs_of_the_draw(names=(name,))[name], root)
    door.declare()
    door.ingest()
    door.lens_stage()
    door.tree_stage()
    door.faces_stage()
    return door


@pytest.fixture(scope="module")
def toy_door(tmp_path_factory):
    return _door(tmp_path_factory, "toy")


@pytest.fixture(scope="module")
def longmem_door(tmp_path_factory):
    return _door(tmp_path_factory, "longmem")


@pytest.fixture(scope="module")
def qasper_door(tmp_path_factory):
    return _door(tmp_path_factory, "qasper")


# --------------------------------------------------------------------------- the face equality
def _oracle_face(table, field: str, arrow_type: str, rows: list[int]) -> dict | None:
    """A.34's fold over the DECODED member rows, from the oracle. The control, in Python."""
    if not rows:
        return None
    decoded = table.rows(rows)
    faces = [leaf_face({field: row[field]}, {field: arrow_type})
             for row in decoded]  # loop-ok: the members of ONE range under test, the control's own fold
    folded, _drops = fold_faces(faces)
    return folded[field]


def _reduction_face(door: FrontDoor, kind: str, field: str, boundaries: torch.Tensor,
                    which: int) -> dict:
    """The same carrier, from ``atlas.front.faces`` - the production path under test."""
    store = door.opened.ingestion.store
    face = FA.frontier_face(store, door.loaded, kind, field, boundaries)
    table = store.table(kind)
    vocabulary = table.vocabulary(field)
    if face.carrier == "kind":
        if face.counts is not None:
            row = face.counts[which]
            present = torch.nonzero(row, as_tuple=False).flatten().tolist()
            counts = {(vocabulary[c] if vocabulary else str(bool(c))): int(row[c])
                      for c in sorted(present)}  # loop-ok: the codes present in ONE range
        else:
            range_id, codes, counts_sparse = face.sparse
            mine = range_id == which
            # the whole-array work (the mask) happens on the device; the host sees ONE unpack of
            # each of the two arrays, after it, never a tensor unpacked inside the loop header.
            codes_here = codes[mine].tolist()
            counts_here = counts_sparse[mine].tolist()
            pairs = list(zip(codes_here, counts_here))
            counts = {(vocabulary[int(c)] if vocabulary else str(bool(int(c)))): int(n)
                      for c, n in pairs}  # loop-ok: the codes present in ONE range
        return {"carrier": "kind", "counts": counts} if counts else {"carrier": "kind",
                                                                     "null": True}
    if face.carrier == "set":
        if face.sparse is not None:
            range_id, codes, _counts = face.sparse
            got = sorted(codes[range_id == which].tolist())
        else:
            row = face.counts[which]
            got = torch.nonzero(row, as_tuple=False).flatten().tolist()
        if not got:
            return {"carrier": "set", "null": True}
        return {"carrier": "set", "values": sorted(str(int(c)) for c in got)}
    lo, hi, declares = face.hull
    if not int(declares[which]):
        return {"carrier": face.carrier, "null": True}
    if face.carrier == "date":
        return {"carrier": "date", "lo": int(lo[which]), "hi": int(hi[which])}
    ranked, null, _t = FA.ranked_column(door.opened.ingestion.store, kind, field,
                                        door.loaded.rank_global_all)
    range_id, codes = R.distinct_codes(ranked, boundaries, null)
    mine = sorted(codes[range_id == which].tolist())
    decode = ((lambda c: vocabulary[int(c)]) if vocabulary else (lambda c: str(int(c))))
    return {"carrier": "scalar", "values": sorted(decode(c) for c in mine),
            "survives": bool(face.survives[which]), "min": int(lo[which]), "max": int(hi[which])}


def _same_face(old: dict | None, new: dict, arrow_type: str) -> tuple[bool, str]:
    if old is None:
        return new.get("null", False), "no member of this kind in the range"
    if old.get("null") and new.get("null"):
        return True, "both null"
    carrier = old["carrier"]
    if carrier in ("scalar", "set"):
        return sorted(old.get("values", [])) == sorted(new.get("values", [])), "value set"
    if carrier == "kind":
        return old.get("counts", {}) == new.get("counts", {}), "counts map"
    back = datetime_of_key if arrow_type == "timestamp" else date_of_key
    lo, hi = str(back(new["lo"])), str(back(new["hi"]))
    return (old["lo"][:len(lo)] == lo[:len(old["lo"])]
            and old["hi"][:len(hi)] == hi[:len(old["hi"])]), f"hull {lo}..{hi}"


# The oracle is O(members x columns) of HOST decoding - it exists to be slow and independent.
# The reduction is computed over the WHOLE frontier either way; the control is evaluated on the
# ranges it can afford, which is why the comparison picks a node of at most this many members.
ORACLE_MEMBER_CAP = 64


def _comparable_nodes(lens: FA.LoadedLens) -> list[tuple[str, torch.Tensor]]:
    """A PARENT with at most ORACLE_MEMBER_CAP members, and its two children: two frontiers.

    Both are real cut levels of the lens's own refinement (a node, and the level below it), so
    the reduction under test is the same batched call the read makes; only the CONTROL's cost is
    bounded. Picks the largest such parent, so the comparison sees as many distinct values as
    the cap allows.
    """
    sizes = lens.hi - lens.lo
    internal = lens.left >= 0
    admissible = torch.nonzero(internal & (sizes <= ORACLE_MEMBER_CAP) & (sizes >= 2),
                               as_tuple=False).flatten()
    if not admissible.numel():
        admissible = torch.nonzero(internal, as_tuple=False).flatten()
    if not admissible.numel():
        # A lens whose whole component is one node (the toy's walk lens binds 4 rows and never
        # splits): the root IS the only cut level there is, and it is still a real frontier.
        return [("the root", lens.roots)]
    parent = int(admissible[int(torch.argmax(sizes.index_select(0, admissible)))])
    children = torch.tensor([int(lens.left[parent]), int(lens.right[parent])],
                            dtype=torch.int64, device=lens.lo.device)
    return [("the node", torch.tensor([parent], dtype=torch.int64, device=lens.lo.device)),
            ("its two children", children)]


def face_comparison(door: FrontDoor) -> list[dict]:
    """EVERY declared column of EVERY carrier row kind, over two real cut levels."""
    lens = door.loaded
    store = door.opened.ingestion.store
    checked = []
    for label, nodes in _comparable_nodes(lens):  # loop-ok: two declared frontiers
        order = torch.argsort(lens.lo.index_select(0, nodes))
        nodes = nodes.index_select(0, order)
        boundaries = R.frontier_boundaries(lens.lo.index_select(0, nodes),
                                           lens.hi.index_select(0, nodes))
        for kind in door.lens.carrier_row_kinds:  # loop-ok: the lens's declared carrier row kinds
            table = store.table(kind)
            if not len(table):
                continue
            for field in table.spec.columns:  # loop-ok: the kind's closed column list
                arrow_type = table.spec.field(field).type
                carrier = F.carrier_for_type(arrow_type)
                for which in range(int(boundaries.numel()) - 1):  # loop-ok: the ranges of this frontier
                    node = int(nodes[which])
                    lo, hi = int(lens.lo[node]), int(lens.hi[node])
                    rows = lens.rank_global[lo:hi]
                    local = store.local_of_global(kind).index_select(0, rows)
                    local = local[local >= 0]
                    old = _oracle_face(table, field, arrow_type,
                                       [int(v) for v in local.tolist()])  # loop-ok: the members of one range
                    new = _reduction_face(door, kind, field, boundaries, which)
                    same, how = _same_face(old, new, arrow_type)
                    checked.append({"frontier": label, "range": which, "kind": kind,
                                    "field": field, "arrow_type": arrow_type,
                                    "carrier": carrier, "members": int(local.numel()),
                                    "equal": bool(same), "compared": how})
    return checked


@pytest.mark.parametrize("fixture", ["longmem_door", "qasper_door"])
def test_the_range_reduction_face_equals_the_old_fold_on_every_declared_column(fixture, request):
    """must_achieve (5): EVERY declared column of EVERY carrier row kind of BOTH benchmarks.

    The J1 synthesis got 39 of 41 on LongMemEval: ``quantity.value_scaled`` disagreed because
    ``distinct_codes`` packed a (range, code) pair into a fixed 31-bit field, and
    ``event.relative`` was REFUSED outright because ``bool`` had no carrier. Both are fixed, so
    the only acceptable number here is all of them.
    """
    door = request.getfixturevalue(fixture)
    checked = face_comparison(door)
    unequal = [c for c in checked if not c["equal"]]
    assert checked, "the comparison must actually compare something"
    assert not unequal, json.dumps(unequal[:6], indent=1)


def test_bool_has_a_carrier_and_it_is_the_two_code_kind():
    """The measurement-forced addition to A.34's closed carrier set (J1 seams[2])."""
    assert F.carrier_for_type("bool") == "kind"
    assert F.RANGE_REDUCTION_OF["kind"] == "kind_counts"


def test_distinct_codes_no_longer_truncates_a_code_or_invents_a_range(request):
    """The J1 synthesis' MINIMAL case, verbatim: values [-3, 5, 2147483655, 1099511627776] over
    a ONE-range frontier came back as codes [0, 5, 7, 2147483645] with range ids [-1, 0, 1, 512].
    """
    values = torch.tensor([-3, 5, 2147483655, 1099511627776], dtype=torch.int64, device="cuda")
    boundaries = R.frontier_boundaries(torch.tensor([0], device="cuda"),
                                       torch.tensor([4], device="cuda"))
    range_id, codes = R.distinct_codes(values, boundaries, null=NULL_OF[torch.int64])
    assert sorted(codes.tolist()) == [-3, 5, 2147483655, 1099511627776]
    assert set(range_id.tolist()) == {0}, "a one-range frontier can only have range id 0"

    # and it REFUSES by name rather than masking a code that cannot fit the packing
    wide = torch.tensor([1 << 62], dtype=torch.int64, device="cuda")
    with pytest.raises(R.RangeRefusal) as refused:
        R.distinct_codes(wide, R.frontier_boundaries(torch.tensor([0], device="cuda"),
                                                     torch.tensor([1], device="cuda")),
                         null=NULL_OF[torch.int64])
    assert refused.value.refusal == "RANGE-DISTINCT-CODES-CODE-WIDTH-EXCEEDED"


# --------------------------------------------------------------------------- admits, both forms
def _boundaries(n: int, ranges: int) -> torch.Tensor:
    edges = torch.linspace(0, n, ranges + 1, device="cuda").to(torch.int64)
    return R.frontier_boundaries(edges[:-1], edges[1:])


@pytest.mark.parametrize("kind,condition", [
    ("equality", {"kind": "equality", "code": 3}),
    ("membership", {"kind": "membership", "codes": [3, 5]}),
    ("count_threshold", {"kind": "count_threshold", "code": 3, "threshold": 2, "op": ">="}),
])
def test_admits_agrees_between_the_dense_and_the_sparse_reduction(kind, condition):
    """must_achieve (6): the same verdict from both forms, with the invariant on every range."""
    torch.manual_seed(7)
    n, ranges, width = 4096, 16, 8
    codes = torch.randint(0, width, (n,), dtype=torch.int64, device="cuda")
    codes[:64] = NULL_OF[torch.int64]                      # a declared==0 region
    boundaries = _boundaries(n, ranges)
    dense = R.kind_counts(codes, boundaries, width, NULL_OF[torch.int64])
    sparse = R.sparse_kind_counts(codes, boundaries, NULL_OF[torch.int64])
    a = R.admits(condition, counts=dense)
    b = R.admits(condition, sparse=sparse, ranges=ranges)
    assert torch.equal(a.decided_in, b.decided_in)
    assert torch.equal(a.excluded, b.excluded)
    assert torch.equal(a.open, b.open)
    assert torch.equal(a.declares, b.declares)
    total = a.decided_in.to(torch.int64) + a.excluded.to(torch.int64) + a.open.to(torch.int64)
    assert torch.equal(total, torch.ones_like(total)), "decided_in + excluded + open == 1"


def test_admits_answers_day_and_day_interval_from_the_integer_hull():
    """The other two of the five condition kinds, on the DATE carrier's integer day key."""
    keys = torch.arange(1000, 1000 + 512, dtype=torch.int64, device="cuda")
    boundaries = _boundaries(512, 8)
    hull = R.date_hull(keys, boundaries, NULL_OF[torch.int64])
    day = R.admits({"kind": "day", "day": 1005}, hull=hull)
    interval = R.admits({"kind": "day_interval", "lo_day": 1000, "hi_day": 1063}, hull=hull)
    for verdict in (day, interval):  # loop-ok: the two date condition kinds
        total = (verdict.decided_in.to(torch.int64) + verdict.excluded.to(torch.int64)
                 + verdict.open.to(torch.int64))
        assert torch.equal(total, torch.ones_like(total))
    assert bool(interval.decided_in[0]), "the first 64 days are inside [1000, 1063]"
    assert int(day.decided_in.sum()) == 0, "no 64-day range is contained in one day"


def test_the_row_scale_set_carrier_reaches_a_verdict_where_the_dense_form_refuses():
    """B2's escalated deficiency 2, at the size it was escalated at: V ~ N, F = 10,000."""
    n, ranges = 200_000, 10_000
    codes = torch.arange(n, dtype=torch.int64, device="cuda")     # one code per row: V = N
    boundaries = _boundaries(n, ranges)
    with pytest.raises(R.RangeRefusal) as refused:
        R.kind_counts(codes, boundaries, n, NULL_OF[torch.int64])
    assert refused.value.refusal == "RANGE-KIND-COUNTS-DENSE-BUDGET-EXCEEDED"
    sparse = R.sparse_kind_counts(codes, boundaries, NULL_OF[torch.int64])
    verdict = R.admits({"kind": "membership", "codes": [0, 1, 2, n - 1]}, sparse=sparse,
                       ranges=ranges)
    total = (verdict.decided_in.to(torch.int64) + verdict.excluded.to(torch.int64)
             + verdict.open.to(torch.int64))
    assert torch.equal(total, torch.ones_like(total))
    # The two ranges that HOLD one of the wanted codes are OPEN (3 of their 20 declaring rows
    # match, so they are neither wholly in nor wholly out) and the other 9,998 are EXCLUDED:
    # a verdict the dense form could not have reached at all at this width.
    assert int(verdict.open.sum()) == 2
    assert int(verdict.excluded.sum()) == ranges - 2
    assert int(verdict.decided_in.sum()) == 0


# --------------------------------------------------------------------------- coarse counts
def test_the_coarse_relation_counts_agree_sparse_against_dense_and_refuse_by_name(longmem_door):
    """must_achieve (6): B.36's equality at the lens's OWN frontier size, and the named refusal."""
    door = longmem_door
    lens = door.loaded
    roots = lens.roots
    order = torch.argsort(lens.lo.index_select(0, roots))
    roots = roots.index_select(0, order)
    boundaries = R.frontier_boundaries(lens.lo.index_select(0, roots),
                                       lens.hi.index_select(0, roots))
    kind = door.lens.counted_relation_kinds[0]
    table = door.opened.ingestion.relations.kind(kind)
    out = FA.coarse_counts_over_frontier(lens, table, boundaries, dense=True)
    assert int(out["dense_matrix"].sum()) == int(out["triple"][2].sum())
    assert int((out["dense_matrix"] > 0).sum()) == int(out["triple"][0].numel())
    device = lens.rank_global.device
    rank_of = torch.full((int(lens.rank_global.max()) + 2,), -1, dtype=torch.int64,
                         device=device)
    rank_of[lens.rank_global] = torch.arange(lens.rows, dtype=torch.int64, device=device)
    with pytest.raises(R.RangeRefusal) as refused:
        R.coarse_relation_counts(rank_of, table.src, table.dst,
                                 table.witness_lengths.to(torch.int64),
                                 _boundaries(lens.rows, 20_000))
    assert refused.value.refusal == "RANGE-COARSE-RELATION-DENSE-BUDGET-EXCEEDED"


# --------------------------------------------------------------------------- the handles
def test_twenty_answer_handles_resolve_to_the_same_bytes_in_a_second_process(longmem_door,
                                                                             tmp_path):
    """must_achieve (7) and (14), work order WO-20260922-answers-name-their-content.

    The answer's handles are written out here and resolved in a SECOND PROCESS that opens the
    persisted record and nothing else: every identity must be found, every witness address must
    be the same triple, and the bytes at that address must hash to the same digest.
    """
    door = longmem_door
    spec = door.run.questions()[0]
    compiled = compile_question(spec, door.opened, door.lens, door.loaded.rows)
    result = RD.read(door.opened, door.loaded, compiled,
                     tolerance=compiled.tolerances[0], supply="partial")
    handles = [h.as_dict() for h in result.row_handles[:20]]  # loop-ok: the twenty handles under test
    assert len(handles) == 20, f"the answer supplied {len(result.row_handles)} handles"
    here = RD.resolve_handles(door.opened, handles)
    assert here["resolved"] == 20 and here["address_equal"] == 20

    payload = tmp_path / "handles.json"
    payload.write_text(json.dumps({"handles": handles, "store": str(door.store.root),
                                   "rung": door.run.rung}))
    code = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(ROOT / 'src')!r})\n"
        "from pathlib import Path\n"
        "from atlas.record import segments as S\n"
        "from atlas.record.ingest import longmem\n"
        "import atlas.front.read as RD\n"
        f"payload = json.loads(Path({str(payload)!r}).read_text())\n"
        "opened = S.open_record(S.SegmentStore(Path(payload['store'])),"
        " longmem.declaration('ab'), rung=1)\n"
        "print(json.dumps(RD.resolve_handles(opened, payload['handles'])))\n")
    run = subprocess.run([str(ROOT / "scripts" / "laplace-python"), "-c", code],  # pool-once: ONE child per test - the SECOND PROCESS is the claim under test, never a pool
                         capture_output=True, text=True, cwd=str(ROOT), timeout=900)
    assert run.returncode == 0, run.stderr[-2000:]
    there = json.loads(run.stdout.strip().splitlines()[-1])
    assert there["resolved"] == 20, there
    assert there["address_equal"] == 20, there
    mine = {row["row_id"]: row["digest"] for row in here["rows"]}  # loop-ok: the twenty handles
    theirs = {row["row_id"]: row["digest"] for row in there["rows"]}  # loop-ok: the twenty handles
    assert mine == theirs, "the same identity must name the same bytes in both processes"


def test_a_range_decided_without_opening_carries_its_handle_and_its_expansion(toy_door):
    """must_achieve (14): a range the read never opened still names what decided the answer."""
    door = toy_door
    spec = door.run.questions()[0]
    compiled = compile_question(spec, door.opened, door.lens, door.loaded.rows)
    result = RD.read(door.opened, door.loaded, compiled,
                     tolerance=compiled.tolerances[0], supply="partial")
    assert result.range_handles, "the read decided at least one range without opening it"
    handle = result.range_handles[0]
    assert handle.component_address.startswith("sha256:") or len(handle.component_address) >= 32
    assert handle.lens_hash and handle.condition_digest
    assert len(handle.rows) == handle.hi - handle.lo, "the expansion is the range's postings"
    assert handle.component_address in door.loaded.component_address


# --------------------------------------------------------------------------- the accounting
def test_every_declared_carrier_row_is_either_bound_or_named_unseated(longmem_door):
    """What a lens OWES a row it cannot seat (the J1 carried residual): it names it, the
    manifest carries it, and the read supplies it as an always-open range."""
    door = longmem_door
    receipt = door.tree.receipt if door.tree is not None else None
    assert receipt is not None
    assert receipt.rows_bound + receipt.rows_unbound == receipt.rows_declared
    assert door.loaded.unbound == receipt.rows_unbound
    spec = door.run.questions()[0]
    compiled = compile_question(spec, door.opened, door.lens, door.loaded.rows)
    result = RD.read(door.opened, door.loaded, compiled,
                     tolerance=compiled.tolerances[0], supply="partial")
    assert (result.executed["rows_the_lens_could_not_seat_and_the_read_opened"]
            == receipt.rows_unbound)
    assert result.executed["positions_touched"] >= door.loaded.unbound


def test_the_grading_receipt_stops_reporting_zero_persisted_bytes(toy_door):
    """must_achieve (10): the field the interface demands is no longer emitted as a zero."""
    tree, manifest = toy_door.tree, toy_door.manifest
    receipt = T.receipt_with_persistence(tree.receipt, manifest)
    assert receipt.persisted_bytes == manifest["persisted_bytes"] > 0
    assert receipt.bytes_per_source_byte == pytest.approx(
        receipt.persisted_bytes / receipt.source_bytes)
    with pytest.raises(Exception):
        T.receipt_with_persistence(tree.receipt, dict(manifest, lens_id="another-lens"))


def test_the_stage_chain_is_a_hash_chain(toy_door):
    """must_achieve (2): the front door's own receipt chains the stages by content address."""
    stages = toy_door.stages
    assert [s.stage for s in stages] == ["declare", "ingest", "lens", "tree", "faces"]  # loop-ok: the stages this fixture ran
    previous = ""
    for stage in stages:  # loop-ok: the stages this fixture ran
        assert stage.consumes_address == previous
        previous = stage.address
    assert len(set(s.address for s in stages)) == len(stages)  # loop-ok: the stages this fixture ran


def test_the_toy_five_known_answers_are_all_correct_through_the_front_door(toy_door):
    """must_achieve (2): the five answers C.25's fixture states, through the one read path."""
    door = toy_door
    door.answer_stage()
    assert len(door.results) == 5
    for row in door.results:  # loop-ok: the toy's five declared questions
        assert row["answer_equals_the_known_answer"], row["qid"]
        assert row["answer_equals_the_flat_control"], row["qid"]
        assert row["partial"]["certificate"] is not None, row["qid"]


# ------------------------------------------- the continuation's own requirements (judge round 1)
def test_the_packed_control_counts_the_same_set_the_read_admits(toy_door):
    """The J1 residual this packet owns, at the place the judge found it failing.

    ``packed_direct_control``'s docstring asserted its count IS the read's ``rows_admitted``
    while packing only the CONDITION axes; on the engine it counted 782 where the read admitted
    47. The control now packs ``read.admission_axes`` - the conditions AND the two the operator
    adds - so the equality is asserted here with both numbers in the message.
    """
    door = toy_door
    door.answer_stage()
    for row in door.results:  # loop-ok: the toy's five declared questions
        control = row["packed_direct_control"]
        admitted = row["partial"]["executed"]["rows_admitted"]
        assert control["ran"], row["qid"]
        assert control["count"] == admitted, (row["qid"], control["count"], admitted)
        assert control["axes"] == len(control["axis_names"])
        assert control["axis_names"][-1].endswith("_is_declared")


def test_the_exact_joint_count_comes_from_the_lifted_contraction_and_agrees(toy_door):
    """must_achieve (13): the EXACT joint count is the integer contraction's, not the descent's.

    Both lifted routes run - ``integer_contraction`` over ``gpu_state``'s conditional-law
    quotient, and ``section_coupling``'s route-weighted quotient - and both must return the same
    integer the frontier read admitted and the packed scan counted.
    """
    from atlas.front import joint as JN

    door = toy_door
    door.answer_stage()
    for row in door.results:  # loop-ok: the toy's five declared questions
        block = row["exact_joint_counts"]
        assert block["ran"], row["qid"]
        assert block["integer_contraction"]["ran"], (row["qid"], block["integer_contraction"])
        assert block["section_coupling"]["ran"], (row["qid"], block["section_coupling"])
        assert block["agreement"]["all_three_agree"], (row["qid"], block["agreement"])
        # the joint count is not a product of its marginals: the bank carries both, and the
        # conditions-only query is at least the full admission.
        counts = block["integer_contraction"]["counts"]
        assert counts["conditions_only"] >= counts["all_axes"], row["qid"]
    assert JN.JOINT_QUERY_BANK[0].startswith("every admission axis")


def test_a_second_run_of_the_toy_and_the_engine_re_ingests_nothing(tmp_path_factory):
    """must_achieve (3), on the two datasets the first pass left re-ingesting.

    ``record/ingest/toy.py`` and ``record/ingest/engine_rows.py`` now mark their contribution
    through ``ingestion.item``, so ``store_ingestion`` cuts a segment and the second run takes
    ``open_record`` with extractions 0, parses 0 and source_reads 0 - the same path the two
    benchmark ingesters already took.
    """
    for name in ("toy", "engine"):  # loop-ok: the two datasets whose ingesters this packet marked
        root = tmp_path_factory.mktemp(f"warm-{name}")
        cold = FrontDoor(runs_of_the_draw(names=(name,))[name], root)
        cold.declare()
        cold.ingest()
        assert cold.stages[-1].executed["path"] == "store_ingestion", name
        assert cold.stages[-1].executed["items"] >= 1, name
        warm = FrontDoor(runs_of_the_draw(names=(name,))[name], root)
        warm.declare()
        warm.ingest()
        executed = warm.stages[-1].executed
        assert executed["path"] == "open_record", (name, executed)
        assert executed["extractions"] == 0 and executed["parses"] == 0, (name, executed)
        assert executed["source_reads"] == 0, (name, executed)
        assert executed["rows"] == cold.stages[-1].executed["rows"], name


def test_a_finer_item_cut_on_the_engine_refuses_by_name():
    """Why the engine's two ledgers are ONE item, demonstrated rather than asserted.

    A per-line (or per-file) item is refused by ``segments.cut_segments`` because the ledgers'
    link relations join a work_order row to a verdict row and to the B.32 dangling_reference rows
    minted after both files are parsed: an edge whose endpoints sit in different items would make
    a segment depend on what else is in the store. The refusal is ``MalformedSource``, by name.
    """
    from atlas.record.errors import MalformedSource
    from atlas.record.ingestion import item_cache_key
    from atlas.record import segments as S
    from atlas.record.ingest import engine_rows

    ingestion = engine_rows.ingest()
    marks = ingestion.item_marks
    assert len(marks) == 1, "the engine ledgers are declared as one item"
    # Split the one mark into two by row kind - the finest cut the ledgers' own structure
    # suggests (one item per file) - and ask the cutter for segments.
    whole = marks[0]
    by_kind = {kind: (lo, hi) for kind, lo, hi in whole.row_ranges}  # loop-ok: the two declared row kinds
    ingestion.item_marks = [
        type(whole)(item_cache_key=item_cache_key(f"split:{kind}", (0, 1), "split@v1",
                                                  ingestion.declaration.declaration_hash),
                    item_content_hash=whole.item_content_hash, item_span=whole.item_span,
                    blob_handles=whole.blob_handles, span_range=whole.span_range,
                    row_ranges=((kind, lo, hi),), extracted=False)
        for kind, (lo, hi) in by_kind.items()]  # loop-ok: the two declared row kinds
    with pytest.raises(MalformedSource) as refused:
        S.cut_segments(ingestion, extractor_roster_hash="test")
    assert "cross item boundaries" in str(refused.value)


def test_the_tolerance_ladder_has_three_finite_precisions_and_the_third_separates(longmem_door):
    """The judge's deficiency on ``read_at_three_tolerances``, closed by measurement.

    The two ROW-SCALE precisions give byte-identical splits; the third finite rung - the declared
    observable's own range - gives a different one, so the ladder shows the tolerance deciding at
    a FINITE point rather than only at infinity.
    """
    door = longmem_door
    spec = door.run.questions()[0]
    compiled = compile_question(spec, door.opened, door.lens, door.loaded.rows)
    names = [t["name"] for t in compiled.tolerances]  # loop-ok: the declared ladder
    assert names == ["one_row_of_the_answering_kind", "one_row_of_the_carrier",
                     "the_observables_whole_range", "no_distinction_demanded"]
    finite = [t for t in compiled.tolerances if t["tau"] != float("inf")]  # loop-ok: the declared ladder
    assert len(finite) == 3
    splits = []
    for tolerance in compiled.tolerances:  # loop-ok: the declared ladder
        result = RD.read(door.opened, door.loaded, compiled, tolerance=tolerance,
                         supply="partial")
        last = result.rounds[-1]
        splits.append((last["decided_in"], last["excluded"], last["open"],
                       result.executed["rounds"]))
    assert splits[0] == splits[1], "the two row-scale precisions are inert against each other"
    assert splits[2] != splits[0], "the observable's own range separates the split"
    assert splits[2] == splits[3], "no node's bound exceeds the observable's range"


def test_the_read_reports_where_its_own_seconds_went(toy_door):
    """The timing table's attribution is a RECEIPT field, not a profiler's guess."""
    door = toy_door
    spec = door.run.questions()[0]
    compiled = compile_question(spec, door.opened, door.lens, door.loaded.rows)
    result = RD.read(door.opened, door.loaded, compiled, tolerance=compiled.tolerances[0],
                     supply="partial")
    parts = ("descent_seconds", "answer_seconds", "evidence_seconds", "handles_seconds")
    total = sum(result.executed[name] for name in parts)  # loop-ok: the four declared phases
    assert total <= result.seconds + 1e-6
    assert result.executed["descent_seconds"] > 0
