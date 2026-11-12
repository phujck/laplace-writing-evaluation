"""P27, pinned: block-local reduced bases + query renormalization down the descent.

The mechanism is ruled by ``AMEND-20260823-p27-mechanism-pinned`` and confirmed on all five
decisions by ``RUL-20260823-p27-design-confirmed``; it lives at ``embed_router._block_*`` and in
one flag-gated branch of ``route``'s descent. What this shard holds:

  * THE OFF POSTURE IS THE INCUMBENT, and not by inspection - the block machinery is SABOTAGED
    and the disarmed descent still serves, which is the only proof that says "this code did not
    run" rather than "this code happened to agree". Held again on three LIVE queries against the
    real network, where every non-arming value of the flag returns a byte-identical result dict.
  * THE ARMED BRANCH PROJECTS on a live query, and the report is served. NO ASSERTION ON WHICH
    WAY THE RANKING MOVES - the three-legged A/B (R1) owns that verdict, not a unit test.
  * D4's FALLBACK fires on a block too small to carry a basis, and R2's MIXED-LEVEL seam is
    counted where it actually happens.
  * D2's rank clamp, arithmetic-exact.
  * D3's bar: the global metric M never enters a projected block.

The synthetic cases drive the deterministic HashBackend (no model, no network); the three live
cases skip themselves where the real network or the backend is absent.

SECOND LANE, SAME SHARD (2026-08-23): THE QUANTILE POOL (``LAPLACE_POOL_QUANTILE=1``), the cure
for the seam the arm above measured (``RUL-20260823-quantile-pool-confirmed``, the disease in
``SCORE-20260823-P27-run1``). It lives here rather than in a lane of its own because it is the
same seam - the level pool - and because the composition of the two levers is the thing that has
to hold. What that half holds: the lever's arm-only posture and the SABOTAGED off posture; the
ruled quantile map itself; a PLANTED two-block level where the raw scores and the calibrated ones
disagree about the beam, which is the only form of proof that says the calibration DECIDES rather
than merely rides; rider (i)'s tiebreak proven against the alphabet it replaces; rider (ii)'s
range proven diagnostic by compressing a block's range without moving a single served score; and
the composition, synthetic and live.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.representation import embed_router
from laplace.representation.embed_router import HashBackend

FLAG = "LAPLACE_BLOCK_RENORM"


# ---------------------------------------------------------------------------
# the synthetic geometry - one root, two branches of chosen width
# ---------------------------------------------------------------------------

def _net(widths: dict[str, int]) -> dict:
    """A two-level net: root -> one internal node per key, each with ``widths[key]`` leaves."""
    nodes: dict[str, dict] = {
        "root": {"id": "root", "grade": 2, "parent": None, "leaf": False,
                 "members": list(widths), "coverage": [], "keywords": [],
                 "essence": "the root of the synthetic world"},
    }
    for branch, n in widths.items():
        nodes[branch] = {"id": branch, "grade": 1, "parent": "root", "leaf": False,
                         "members": [f"{branch}{i}" for i in range(n)],
                         "coverage": [], "keywords": [branch],
                         "essence": f"the {branch} cluster of the synthetic world"}
        for i in range(n):
            nodes[f"{branch}{i}"] = {
                "id": f"{branch}{i}", "grade": 0, "parent": branch, "leaf": True,
                "members": [], "coverage": [], "keywords": [branch],
                "essence": f"{branch} member {i} - scattering decay resonance {i}"}
    return {"nodes": nodes, "reach": {k: set() for k in nodes},
            "lenses": {k: ["engine"] for k in nodes}, "root": "root"}


def _leaves(root_dir: Path, n: int) -> dict:
    """A root whose direct members are leaves - the smallest block there is."""
    nodes: dict[str, dict] = {
        "root": {"id": "root", "grade": 2, "parent": None, "leaf": False,
                 "members": [f"x{i}" for i in range(n)], "coverage": [], "keywords": [],
                 "essence": "a root with nothing but leaves"},
    }
    for i in range(n):
        nodes[f"x{i}"] = {"id": f"x{i}", "grade": 0, "parent": "root", "leaf": True,
                          "members": [], "coverage": [], "keywords": ["x"],
                          "essence": f"leaf {i} - alpha particle scattering"}
    return {"nodes": nodes, "reach": {k: set() for k in nodes},
            "lenses": {k: ["engine"] for k in nodes}, "root": "root"}


@pytest.fixture
def disarmed(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)


@pytest.fixture
def armed(monkeypatch):
    monkeypatch.setenv(FLAG, "1")


# ---------------------------------------------------------------------------
# the flag - an ARM flag, never a serving default, read at call time
# ---------------------------------------------------------------------------

def test_only_the_exact_string_one_arms(monkeypatch):
    monkeypatch.delenv(FLAG, raising=False)
    assert embed_router._block_renorm_on() is False
    for off in ("", "0", "true", "TRUE", "yes", "11", " 1", "1 "):
        monkeypatch.setenv(FLAG, off)
        assert embed_router._block_renorm_on() is False, off
    monkeypatch.setenv(FLAG, "1")
    assert embed_router._block_renorm_on() is True


# ---------------------------------------------------------------------------
# D2 - the rank clamp, arithmetic-exact, and D4's fallback around it
# ---------------------------------------------------------------------------

def test_rank_clamp_arithmetic():
    assert embed_router._block_rank(5, 384, 8) == 4      # n - 1 binds: the block mean is spent
    assert embed_router._block_rank(50, 384, 8) == 8     # chi binds
    assert embed_router._block_rank(50, 3, 8) == 3       # d binds
    assert embed_router._block_rank(2, 384, 16) == 1     # rank survives, but n < 3 falls back
    assert embed_router._block_rank(1, 384, 16) == 0     # a lone child spans nothing
    assert embed_router._block_rank(0, 384, 16) == 0     # floored, never negative


def test_block_basis_falls_back_below_three_children_and_clamps_at_n_minus_one():
    np = pytest.importorskip("numpy")
    rng = np.random.default_rng(11)
    assert embed_router._block_basis(rng.normal(size=(2, 384)).astype("float32"), 16) is None
    assert embed_router._block_basis(rng.normal(size=(1, 384)).astype("float32"), 16) is None
    built = embed_router._block_basis(rng.normal(size=(5, 384)).astype("float32"), 8)
    assert built is not None
    mu, proj, coords, cnorm = built
    assert proj.shape == (4, 384)                        # min(chi=8, n-1=4, d=384)
    assert coords.shape == (5, 4)
    assert cnorm.shape == (5,)
    assert float(np.abs(mu).sum()) > 0.0
    # the retained directions are orthonormal - a basis, not a bag of vectors
    assert np.allclose(proj @ proj.T, np.eye(4), atol=1e-5)


def test_projected_cosine_is_a_cosine():
    np = pytest.importorskip("numpy")
    rng = np.random.default_rng(23)
    mat = rng.normal(size=(6, 64)).astype("float32")
    built = embed_router._block_basis(mat, 8)
    assert built is not None
    cos = embed_router._block_cosines(built, rng.normal(size=64).astype("float32"))
    assert cos.shape == (6,)
    assert np.all(np.isfinite(cos)) and np.all(np.abs(cos) <= 1.0 + 1e-5)
    # a query AT a child's own position scores that child at 1.0 in the block's subspace
    at_child = embed_router._block_cosines(built, mat[3])
    assert at_child[3] == pytest.approx(1.0, abs=1e-4)


def test_a_query_with_no_component_in_the_subspace_scores_zero_rather_than_dividing():
    np = pytest.importorskip("numpy")
    mat = np.zeros((4, 16), dtype="float32")
    for i in range(4):
        mat[i, i] = 1.0
    built = embed_router._block_basis(mat, 8)
    assert built is not None
    mu = built[0]
    cos = embed_router._block_cosines(built, mu.copy())   # exactly the block mean: no residual
    assert np.all(cos == 0.0)


# ---------------------------------------------------------------------------
# THE OFF POSTURE - the incumbent, proven by sabotage rather than by agreement
# ---------------------------------------------------------------------------

def test_disarmed_never_enters_the_block_path(tmp_path: Path, monkeypatch, disarmed):
    """The strongest available form of "byte-identical when unset": every block entry point is
    replaced by a bomb. A disarmed route that still serves did not merely AGREE with the
    incumbent - it never ran a line of the arm."""
    def bomb(*_a, **_k):
        raise AssertionError("the block-renorm branch ran with the flag unset")

    monkeypatch.setattr(embed_router, "_block_basis", bomb)
    monkeypatch.setattr(embed_router, "_block_cosines", bomb)
    monkeypatch.setattr(embed_router, "_block_chi", bomb)
    rec = embed_router.route(tmp_path, _net({"a": 5, "b": 2}), "alpha scattering decay",
                             backend=HashBackend())
    assert rec is not None and rec["files"]
    assert "block_renorm" not in rec


def test_disarmed_result_carries_no_report(tmp_path: Path, disarmed):
    rec = embed_router.route(tmp_path, _net({"a": 5, "b": 2}), "scattering resonance",
                             backend=HashBackend())
    assert "block_renorm" not in rec


# ---------------------------------------------------------------------------
# D4 / R2 - the fallback fires, and the mixed level is counted where it happens
# ---------------------------------------------------------------------------

def test_fallback_fires_on_a_small_synthetic_block(tmp_path: Path, monkeypatch, armed):
    """A root whose only block is two leaves cannot carry a basis: no projection, counted."""
    rec = embed_router.route(tmp_path, _leaves(tmp_path, 2), "alpha particle scattering",
                             backend=HashBackend())
    rep = rec["block_renorm"]
    assert rep["blocks_projected"] == 0
    assert rep["blocks_fallback"] == 1
    assert rep["mixed_levels"] == 0
    # and the fallback scored EXACTLY as the incumbent - the same descent, disarmed
    monkeypatch.delenv(FLAG, raising=False)
    plain = embed_router.route(tmp_path, _leaves(tmp_path, 2), "alpha particle scattering",
                               backend=HashBackend())
    assert [f["file"] for f in rec["files"]] == [f["file"] for f in plain["files"]]
    assert [f["cos"] for f in rec["files"]] == [f["cos"] for f in plain["files"]]


def test_the_mixed_level_count_serves(tmp_path: Path, armed):
    """One level expands TWO blocks - a wide one that projects and a narrow one that falls back -
    so that level's pool ranks projected cosines against global scores in one comparison. That is
    R2's seam; the count is what makes it visible rather than silent."""
    rec = embed_router.route(tmp_path, _net({"a": 5, "b": 2}), "scattering decay resonance",
                             backend=HashBackend(), beam=8)
    rep = rec["block_renorm"]
    assert rep["blocks_projected"] == 1                  # 'a' (5 children)
    assert rep["blocks_fallback"] == 2                   # the root (2 children) and 'b' (2)
    assert rep["mixed_levels"] == 1                      # the level that expanded 'a' AND 'b'


def test_a_uniformly_projected_descent_reports_no_mixing(tmp_path: Path, armed):
    rec = embed_router.route(tmp_path, _net({"a": 5, "b": 6, "c": 4}), "scattering decay",
                             backend=HashBackend(), beam=8)
    rep = rec["block_renorm"]
    assert rep["blocks_projected"] == 4                  # the root (3 children) and a, b, c
    assert rep["blocks_fallback"] == 0
    assert rep["mixed_levels"] == 0


# ---------------------------------------------------------------------------
# D3 - the global metric M is barred from the rotated subspace
# ---------------------------------------------------------------------------

def test_the_metric_never_enters_a_projected_block(tmp_path: Path, armed):
    """Every block in this net projects, so every served score is block-local. Under D3 a
    projected block scores the RAW query - so planting a non-identity M must not move a single
    one of them. ``path_decay=0`` keeps the root's own (metric-carrying) heat out of the
    comparison, leaving exactly the block scores on the table."""
    np = pytest.importorskip("numpy")
    b = HashBackend()
    rng = np.random.default_rng(7)
    m = (np.eye(b.dim, dtype="float32")
         + 0.35 * rng.normal(size=(b.dim, b.dim)).astype("float32"))
    with_m = tmp_path / "with_m"
    with_m.mkdir()
    np.savez(with_m / embed_router.METRIC_FILE, M=m)
    bare = tmp_path / "bare"
    bare.mkdir()

    kw = {"backend": b, "path_decay": 0.0, "beam": 8}
    wide = {"a": 5, "b": 6, "c": 4}          # three branches, so the ROOT's block projects too
    hot = embed_router.route(with_m, _net(wide), "scattering decay", **kw)
    cold = embed_router.route(bare, _net(wide), "scattering decay", **kw)
    # the label cure: an armed run names itself +blockR beside its metric state
    assert "+M" in hot["router"] and hot["router"].endswith("+blockR")
    assert "+M" not in cold["router"] and cold["router"].endswith("+blockR")
    assert hot["block_renorm"]["blocks_fallback"] == 0        # nothing scored the incumbent way
    assert {f["file"]: f["cos"] for f in hot["files"]} == {f["file"]: f["cos"] for f in cold["files"]}


# ---------------------------------------------------------------------------
# THE LIVE CASES - the real network, the real backend
# ---------------------------------------------------------------------------

LIVE_QUERIES = [
    "DMRG hierarchicalisation of clustering and distillation",   # a red thread probe
    "the loss hamiltonian metric as kinetic term",
    "closure residual coupling between scales",
]


@pytest.fixture(scope="module")
def live():
    """(repo root, the live network) - or a skip where either is absent."""
    from laplace.engine import conceptric
    root = Path(__file__).resolve().parents[1]
    try:
        net = conceptric.load_network(root)
    except Exception as exc:                             # noqa: BLE001 - absence is a skip, not a fail
        pytest.skip(f"no live network here: {exc}")
    if not net or not net.get("nodes"):
        pytest.skip("the live network is empty here")
    if embed_router.get_backend() is None:
        pytest.skip("no embedding backend here")
    return root, net


@pytest.fixture
def no_ledger(monkeypatch):
    """No salience can reach this floor, so a live route in the suite writes no proposal rows -
    the wire ledger is the dream's store, not a test's."""
    monkeypatch.setattr(embed_router, "PROPOSAL_FLOOR", 2.0)


@pytest.mark.xdist_group("live_network")
def test_default_off_is_byte_identical_on_live_queries(live, monkeypatch, no_ledger):
    root, net = live
    for q in LIVE_QUERIES:
        monkeypatch.delenv(FLAG, raising=False)
        base = embed_router.route(root, net, q, limit=10)
        assert base is not None and "block_renorm" not in base
        canon = json.dumps(base, sort_keys=True)
        for off in ("0", "true", "", "11"):
            monkeypatch.setenv(FLAG, off)
            other = embed_router.route(root, net, q, limit=10)
            assert "block_renorm" not in other
            assert json.dumps(other, sort_keys=True) == canon, (q, off)
    monkeypatch.delenv(FLAG, raising=False)


@pytest.mark.xdist_group("live_network")
def test_the_armed_branch_projects_on_a_live_query(live, monkeypatch, no_ledger):
    """Armed, the descent projects real blocks and serves the counts. The ranking is asserted
    only to be WELL-FORMED and to be the incumbent's or a change of it - which direction it moves
    is the three-legged sweep's verdict (R1), never a unit test's."""
    root, net = live
    q = LIVE_QUERIES[0]
    monkeypatch.delenv(FLAG, raising=False)
    plain = embed_router.route(root, net, q, limit=10)
    monkeypatch.setenv(FLAG, "1")
    rec = embed_router.route(root, net, q, limit=10)

    rep = rec["block_renorm"]
    assert rep["blocks_projected"] > 0
    assert rep["blocks_fallback"] >= 0
    assert rep["mixed_levels"] >= 0
    assert rec["files"] and all(isinstance(f["cos"], float) for f in rec["files"])
    assert all(0.0 <= f["score"] <= 1.0 for f in rec["files"])
    armed_order = [f["file"] for f in rec["files"]]
    plain_order = [f["file"] for f in plain["files"]]
    # WELL-FORMED, and nothing more: same shape as the incumbent's answer, no duplicated hit.
    # Whether the ranking moved, and which way, is the three-legged sweep's row to write.
    assert len(armed_order) == len(plain_order)
    assert len(set(armed_order)) == len(armed_order)


@pytest.mark.xdist_group("live_network")
def test_the_block_memo_does_not_change_what_is_served(live, monkeypatch, no_ledger):
    """The memo is a cost cure, never a semantic one: the second armed fire in a process reuses
    every block basis and must serve the first fire's answer exactly."""
    root, net = live
    monkeypatch.setenv(FLAG, "1")
    first = embed_router.route(root, net, LIVE_QUERIES[1], limit=10)
    second = embed_router.route(root, net, LIVE_QUERIES[1], limit=10)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["block_renorm"]["blocks_projected"] > 0


# ===========================================================================
# THE QUANTILE POOL - the pooling cure (RUL-20260823-quantile-pool-confirmed)
# ===========================================================================

POOL = "LAPLACE_POOL_QUANTILE"


class _PlantedBackend:
    """A backend that hands back a CHOSEN cosine per node, keyed on the node's own id.

    Nothing else can prove the claim this lane makes. The claim is that the calibration DECIDES a
    beam the raw scores would have decided differently, and to plant a raw ordering that inverts
    under quantiles you need the raw scores themselves - which a hash of the node's prose cannot
    give you. Every node id here is its own marker; ``node_text`` puts the node's LABEL first and
    its ancestors' id tails after it, so the EARLIEST marker in a text is always the node's own.
    ``name`` carries the caller's tag, because the basis memo and the on-disk cache key on the
    backend name - two tables under one name would serve each other's vectors."""

    dim = 4

    def __init__(self, tag: str, cosines: dict[str, float]):
        self.name = f"planted:{tag}"
        self.cosines = cosines

    def _vec(self, text: str) -> list[float]:
        best, at = None, len(text) + 1
        for marker, c in self.cosines.items():
            i = text.find(marker)
            if 0 <= i < at:
                best, at = c, i
        c = 0.05 if best is None else best
        return [c, (max(0.0, 1.0 - c * c)) ** 0.5, 0.0, 0.0]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]      # the planted query: cos(q, node) IS the node's first coord


def _two_block_net(a_kids: list[str], b_kids: list[str]) -> dict:
    """``n00`` -> two internal blocks (``n01``, ``n02``), each holding the named internal children,
    each of those holding one leaf. Two blocks on ONE level is the whole geometry the pooled
    comparison lives on."""
    nodes: dict[str, dict] = {}

    def add(nid: str, grade: int, parent: str | None, members: list[str], leaf: bool) -> None:
        nodes[nid] = {"id": nid, "grade": grade, "parent": parent, "leaf": leaf,
                      "members": members, "coverage": [], "keywords": [],
                      "essence": "a planted node of the pooling bench"}

    add("n00", 3, None, ["n01", "n02"], False)
    for blk, kids in (("n01", a_kids), ("n02", b_kids)):
        add(blk, 2, "n00", list(kids), False)
        for k in kids:
            leaf = "f" + k[1:]
            add(k, 1, blk, [leaf], False)
            add(leaf, 0, k, [], True)
    return {"nodes": nodes, "reach": {k: set() for k in nodes},
            "lenses": {k: ["engine"] for k in nodes}, "root": "n00"}


def _reached(rec: dict) -> set[str]:
    """Every node the descent actually REACHED. ``per_grade_direct`` is built from the whole scored
    pool, so it shows reach where ``files`` shows only what survived absorption - and reach is what
    a beam decision changes."""
    return {e["id"] for entries in rec["per_grade_direct"].values() for e in entries}


@pytest.fixture
def pool_armed(monkeypatch):
    monkeypatch.setenv(POOL, "1")


# ---------------------------------------------------------------------------
# the lever - arm-only, read at call time, exactly as the arm above
# ---------------------------------------------------------------------------

def test_only_the_exact_string_one_arms_the_pool_lever(monkeypatch):
    monkeypatch.delenv(POOL, raising=False)
    assert embed_router._pool_quantile_on() is False
    for off in ("", "0", "true", "TRUE", "yes", "11", " 1", "1 "):
        monkeypatch.setenv(POOL, off)
        assert embed_router._pool_quantile_on() is False, off
    monkeypatch.setenv(POOL, "1")
    assert embed_router._pool_quantile_on() is True


# ---------------------------------------------------------------------------
# the ruled map - order-preserving, tie-sharing, scale-free
# ---------------------------------------------------------------------------

def test_the_quantile_map_is_the_ruled_one():
    assert embed_router._block_quantiles([]) == []
    assert embed_router._block_quantiles([0.4]) == [1.0]          # n=1 -> 1.0, the block's own top
    assert embed_router._block_quantiles([0.9, 0.5, 0.7]) == [1.0, 0.0, 0.5]
    assert embed_router._block_quantiles([0.2, 0.2]) == [0.5, 0.5]          # a tie shares its midrank
    assert embed_router._block_quantiles([0.2, 0.2, 0.2]) == [0.5, 0.5, 0.5]
    got = embed_router._block_quantiles([0.9, 0.1, 0.1, 0.9])
    assert got == pytest.approx([2.5 / 3, 0.5 / 3, 0.5 / 3, 2.5 / 3])


def test_the_map_is_scale_free_and_order_preserving():
    """The two properties the ruling bought: the SAME ranking maps to the SAME quantiles whatever
    the scale or offset of the scores carrying it - which is exactly why a projected block at
    0.95-0.999 and a fallback block at 0.64-0.76 become poolable."""
    tight = [0.999, 0.997, 0.995, 0.951]
    loose = [0.76, 0.70, 0.66, 0.64]
    assert embed_router._block_quantiles(tight) == embed_router._block_quantiles(loose)
    assert embed_router._block_quantiles(tight) == [1.0, 2 / 3, 1 / 3, 0.0]
    shifted = [s * 17.0 - 4.0 for s in loose]       # any affine move: the same object
    assert embed_router._block_quantiles(shifted) == embed_router._block_quantiles(loose)


# ---------------------------------------------------------------------------
# THE OFF POSTURE - sabotaged, exactly as the arm above proves its own
# ---------------------------------------------------------------------------

def test_disarmed_never_calibrates(tmp_path: Path, monkeypatch):
    """The lever unset, the calibration organ is a bomb - so a route that still serves did not
    merely AGREE with the incumbent, it never ran a line of the cure."""
    monkeypatch.delenv(POOL, raising=False)

    def bomb(*_a, **_k):
        raise AssertionError("the quantile pool ran with the lever unset")

    monkeypatch.setattr(embed_router, "_block_quantiles", bomb)
    rec = embed_router.route(tmp_path, _net({"a": 5, "b": 2}), "alpha scattering decay",
                             backend=HashBackend())
    assert rec is not None and rec["files"]
    assert "pool_quantile" not in rec
    assert "+poolQ" not in rec["router"]
    assert "own_cos_raw" not in rec["files"][0]["why"]


def test_the_incumbent_ordering_is_untouched_when_no_tiebreak_is_passed():
    """``frontier_order``'s new ``inherited`` argument is rider (i)'s and nothing else's: absent,
    the key is the incumbent's element for element, including the alphabet it ends on."""
    heat = {"b": 0.5, "a": 0.5, "c": 0.9}
    own = {"b": 0.8, "a": 0.1, "c": 0.0}
    assert embed_router.frontier_order(["a", "b", "c"], own, heat) == ["c", "a", "b"]
    assert embed_router.frontier_order(["a", "b", "c"], own, heat,
                                       {"tie_break": "own"}) == ["c", "b", "a"]


# ---------------------------------------------------------------------------
# THE CLAIM: the calibration DECIDES the beam, against a raw pool that would not
# ---------------------------------------------------------------------------

A_RAW = {"n10": 0.90, "n11": 0.80, "n12": 0.70, "n13": 0.60}     # the wide-and-hot block
B_RAW = {"n20": 0.50, "n21": 0.30, "n22": 0.20, "n23": 0.10}     # the block the raw pool never sees


def _planted_table(a: dict[str, float], b: dict[str, float]) -> dict[str, float]:
    tab = {"n00": 0.30, "n01": 0.55, "n02": 0.45, **a, **b}
    tab.update({"f" + k[1:]: 0.40 for k in list(a) + list(b)})
    return tab


def test_the_calibration_decides_the_beam(tmp_path: Path, monkeypatch):
    """ONE level, TWO blocks, and the raw scores rank them so that block B is invisible: every one
    of A's four children out-scores every one of B's. Calibrated, each block's top child is 1.0 and
    the beam takes ONE FROM EACH. The two runs reach different subtrees, and that difference is the
    whole mechanism - a pool that ranks quantiles is not a pool that ranks cosines.

    ``path_decay=0`` puts exactly the level's own scores on the table, so nothing but the
    calibration can be moving the beam."""
    net = _two_block_net(list(A_RAW), list(B_RAW))
    backend = _PlantedBackend("invert", _planted_table(A_RAW, B_RAW))
    kw = {"backend": backend, "beam": 2, "path_decay": 0.0, "per_branch_width": 50, "limit": 50}

    monkeypatch.delenv(POOL, raising=False)
    raw = embed_router.route(tmp_path, net, "the planted pull", **kw)
    monkeypatch.setenv(POOL, "1")
    cal = embed_router.route(tmp_path, net, "the planted pull", **kw)

    # the raw pool expands A's top TWO and never enters B at all
    assert {"f10", "f11"} <= _reached(raw)
    assert not ({"f12", "f13"} | set("f" + k[1:] for k in B_RAW)) & _reached(raw)
    # calibrated, the beam takes one block-top from EACH block
    assert {"f10", "f20"} <= _reached(cal)
    assert "f11" not in _reached(cal)

    # and the served score IS the quantile, with the raw one riding beside it
    row = {f["file"]: f for f in cal["files"]}
    assert row["n01"]["why"]["own_cos"] == 1.0          # the root block's top child
    assert row["n02"]["why"]["own_cos"] == 0.0          # its bottom child
    assert row["n01"]["why"]["own_cos_raw"] == pytest.approx(0.55, abs=0.01)
    assert row["n02"]["why"]["own_cos_raw"] == pytest.approx(0.45, abs=0.01)
    # the incumbent serves the cosine itself, and carries no raw twin to serve
    plain = {f["file"]: f for f in raw["files"]}
    assert plain["n01"]["why"]["own_cos"] == pytest.approx(0.55, abs=0.01)
    assert "own_cos_raw" not in plain["n01"]["why"]
    assert cal["router"].endswith("+poolQ") and "+poolQ" not in raw["router"]

    rep = cal["pool_quantile"]
    assert rep["blocks_calibrated"] == 5              # the root's block, the two on level 1, two leaves
    assert len(rep["block_ranges"]) == rep["blocks_calibrated"]


# ---------------------------------------------------------------------------
# RIDER (i) - the tie is broken by inherited path heat, NOT by the alphabet
# ---------------------------------------------------------------------------

def test_the_cross_block_tie_breaks_on_inherited_path_heat(tmp_path: Path, monkeypatch, pool_armed):
    """Calibration guarantees the degeneracy: every block's top child is exactly 1.0, so the beam
    meets a k-way tie at the top of every level. The named tiebreak is the descent's own g-term.

    The net is built so the two answers DISAGREE: the cold block's children sort FIRST
    alphabetically, so the incumbent key would take the cold branch. The rider takes the hot one."""
    cold, hot = ["n10", "n11", "n12"], ["n90", "n91", "n92"]
    net = _two_block_net(cold, hot)                       # n01 -> cold, n02 -> hot
    table = {"n00": 0.30, "n01": 0.20, "n02": 0.80,
             "n10": 0.90, "n11": 0.60, "n12": 0.30,
             "n90": 0.50, "n91": 0.40, "n92": 0.20}
    table.update({"f" + k[1:]: 0.40 for k in cold + hot})
    rec = embed_router.route(tmp_path, net, "the planted pull",
                             backend=_PlantedBackend("tie", table), beam=1, path_decay=0.5,
                             per_branch_width=50, limit=50)
    # both level-1 tops calibrate to 1.0; the beam of one takes the one reached through the hot handle
    assert "f90" in _reached(rec)
    assert "f10" not in _reached(rec)

    # the same claim at the seam itself: the alphabet and the rider disagree, and the rider decides
    heat, inh = {"n10": 1.0, "n90": 1.0}, {"n10": 0.075, "n90": 0.5}
    assert embed_router.frontier_order(["n10", "n90"], {}, heat) == ["n10", "n90"]
    assert embed_router.frontier_order(["n10", "n90"], {}, heat, inherited=inh) == ["n90", "n10"]

    rep = rec["pool_quantile"]
    # level 0 has no tie (0.0 vs 1.0 after the apex block calibrates); level 1 is 2 tied at 1.0
    # and 3 tied at the 0.5 the hot block's inherited floor pins its lower two to
    assert rep["tie_count_per_level"][0] == 0
    assert rep["tie_count_per_level"][1] == 5


# ---------------------------------------------------------------------------
# RIDER (ii) - the block range rides as a diagnostic and never as a scorer
# ---------------------------------------------------------------------------

def test_the_block_range_is_diagnostic_never_a_scorer(tmp_path: Path, monkeypatch, pool_armed):
    """Compress one block's raw range by a factor of ten, holding its ORDER and every other block
    fixed. The range the report serves moves; not one served score, not one reached node, not one
    ranked row moves with it. That is the rider's claim and the calibration's scale-freedom, read
    off the same pair of runs."""
    wide = {"n10": 0.90, "n11": 0.70, "n12": 0.50, "n13": 0.30}
    narrow = {"n10": 0.90, "n11": 0.88, "n12": 0.86, "n13": 0.84}
    net = _two_block_net(list(wide), list(B_RAW))
    kw = {"beam": 2, "path_decay": 0.0, "per_branch_width": 50, "limit": 50}

    w = embed_router.route(tmp_path, net, "the planted pull",
                           backend=_PlantedBackend("wide", _planted_table(wide, B_RAW)), **kw)
    n = embed_router.route(tmp_path, net, "the planted pull",
                           backend=_PlantedBackend("narrow", _planted_table(narrow, B_RAW)), **kw)

    assert _reached(w) == _reached(n)
    assert [f["file"] for f in w["files"]] == [f["file"] for f in n["files"]]
    assert [f["score"] for f in w["files"]] == [f["score"] for f in n["files"]]
    assert [f["why"]["own_cos"] for f in w["files"]] == [f["why"]["own_cos"] for f in n["files"]]

    # the diagnostic, and it is the ONLY thing that moved: block_ranges[1] is the level-1 block
    # the frontier expanded first (the ranges ride in expansion order)
    assert w["pool_quantile"]["block_ranges"][1] == pytest.approx(0.60, abs=0.02)
    assert n["pool_quantile"]["block_ranges"][1] == pytest.approx(0.06, abs=0.02)
    assert w["pool_quantile"]["blocks_calibrated"] == n["pool_quantile"]["blocks_calibrated"]


# ---------------------------------------------------------------------------
# THE COMPOSITION - the two levers are independent and pool commensurably
# ---------------------------------------------------------------------------

def test_the_two_levers_compose_on_a_mixed_level(tmp_path: Path, armed, pool_armed):
    """The mixed level R2 named - one projected block, one fallback block, ranked in ONE comparison
    - is exactly the level the calibration exists for. Armed together, every block that level
    expands is calibrated, projected and fallback alike, and both reports serve."""
    rec = embed_router.route(tmp_path, _net({"a": 5, "b": 2}), "scattering decay resonance",
                             backend=HashBackend(), beam=8)
    blk = rec["block_renorm"]
    assert blk["blocks_projected"] == 1 and blk["blocks_fallback"] == 2
    assert blk["mixed_levels"] == 1
    rep = rec["pool_quantile"]
    # every block the renorm arm counted is a block the calibration mapped - no seam between them
    assert rep["blocks_calibrated"] == blk["blocks_projected"] + blk["blocks_fallback"]
    assert len(rep["block_ranges"]) == rep["blocks_calibrated"]
    assert all(r >= 0.0 for r in rep["block_ranges"])
    assert rec["router"].endswith("+blockR+poolQ")
    assert all("own_cos_raw" in f["why"] for f in rec["files"])


# ---------------------------------------------------------------------------
# THE LIVE CASES - the real network, the real backend
# ---------------------------------------------------------------------------

@pytest.fixture
def no_embed(monkeypatch):
    """THE LOCAL SERVING POSTURE, and this lane's live cases all take it: budget 0 embeds nothing
    and writes nothing (``_env_budget``'s OFF arm, the local launcher's default since
    WO-20260715-233320-psu-embed-off), so a test run can never dirty the TRACKED vector store.

    It is not optional here. This lane flips ``LAPLACE_DIGEST_ESSENCE``, which MOVES the embedded
    text of every joined node - and the committed store carries the JOINED vectors for 35 nodes
    while the serving default is off, so an unlimited-budget route at the repo root re-embeds and
    rewrites them either way it is armed. That condition is the tree's, not this lane's; the guard
    is how this lane refuses to be the one that lands it."""
    monkeypatch.setenv("LAPLACE_EMBED_BUDGET", "0")


@pytest.mark.xdist_group("live_network")
def test_pool_default_off_is_byte_identical_on_live_queries(live, monkeypatch, no_ledger,
                                                           no_embed):
    """Three live queries, every non-arming value of the lever, byte-identical to the incumbent -
    and the same again with the renorm arm held on, because a no-op has to be a no-op inside the
    composition too."""
    root, net = live
    monkeypatch.delenv(FLAG, raising=False)
    for q in LIVE_QUERIES:
        monkeypatch.delenv(POOL, raising=False)
        base = embed_router.route(root, net, q, limit=10)
        assert base is not None and "pool_quantile" not in base
        canon = json.dumps(base, sort_keys=True)
        for off in ("0", "true", "", "11"):
            monkeypatch.setenv(POOL, off)
            other = embed_router.route(root, net, q, limit=10)
            assert "pool_quantile" not in other
            assert json.dumps(other, sort_keys=True) == canon, (q, off)

    monkeypatch.setenv(FLAG, "1")                      # the same identity INSIDE the composition
    monkeypatch.delenv(POOL, raising=False)
    armed_base = json.dumps(embed_router.route(root, net, LIVE_QUERIES[0], limit=10), sort_keys=True)
    for off in ("0", "true", "", "11"):
        monkeypatch.setenv(POOL, off)
        assert json.dumps(embed_router.route(root, net, LIVE_QUERIES[0], limit=10),
                          sort_keys=True) == armed_base, off
    monkeypatch.delenv(POOL, raising=False)
    monkeypatch.delenv(FLAG, raising=False)


@pytest.mark.xdist_group("live_network")
def test_the_armed_pool_calibrates_a_live_descent(live, monkeypatch, no_ledger, no_embed,
                                                 pool_armed):
    """Armed on a live query the calibration serves its meters and its rows: a served score is a
    quantile in [0, 1], its raw twin rides beside it, and the tie counts and ranges are there for
    the run row to bank. WHICH WAY THE RANKING MOVES IS THE SWEEP'S VERDICT, never a unit test's."""
    root, net = live
    rec = embed_router.route(root, net, LIVE_QUERIES[0], limit=10)
    rep = rec["pool_quantile"]
    assert rep["blocks_calibrated"] > 0
    assert len(rep["block_ranges"]) == rep["blocks_calibrated"]
    assert rep["tie_count_per_level"] and all(isinstance(t, int)
                                              for t in rep["tie_count_per_level"])
    assert rec["router"].endswith("+poolQ")
    assert rec["files"]
    for f in rec["files"]:
        assert 0.0 <= f["why"]["own_cos"] <= 1.0       # a quantile, not a cosine
        assert "own_cos_raw" in f["why"]


@pytest.mark.xdist_group("live_network")
def test_the_three_lever_composition_runs_clean(live, monkeypatch, no_ledger, no_embed,
                                                armed, pool_armed):
    """The posture the composition arm fires in: block renorm + the quantile pool + the essence
    join, on one live query. It runs, it names its venue, and all three levers are visible in what
    it serves - the two reports, and the join's own served map."""
    root, net = live
    monkeypatch.setenv(embed_router.DIGEST_ESSENCE_ENV, "1")
    assert embed_router.digest_essence_on() is True
    rec = embed_router.route(root, net, LIVE_QUERIES[0], limit=10)
    assert rec is not None and rec["files"]
    assert rec["router"].endswith("+blockR+poolQ")
    assert rec["block_renorm"]["blocks_projected"] > 0
    assert rec["pool_quantile"]["blocks_calibrated"] > 0
    assert len(embed_router.digest_essences(root, net)) > 0        # the third lever actually serves


def test_the_geomean_ranks_the_pool_and_id_is_only_determinism():
    """The pool-rank ruling (2026-08-23): under calibration the heat ties at 1.0 and the
    pool sort degenerated to the alphabet. With ``pool_rank`` supplied, the geomean ranks
    between heat and id - and absent, the key is the incumbent's element for element."""
    nodes = {"a": {}, "b": {}}
    pool = {"a": 1.0, "b": 1.0}
    own = {"a": 1.0, "b": 1.0}
    ranked = embed_router.frontier_mass_rank(nodes, pool, own, dict(pool),
                                             {"mode": "incumbent"},
                                             pool_rank={"a": 0.6, "b": 0.9})
    assert [m for m, _, _ in ranked] == ["b", "a"], "the geomean decides, not the alphabet"
    incumbent = embed_router.frontier_mass_rank(nodes, pool, own, dict(pool),
                                                {"mode": "incumbent"})
    assert [m for m, _, _ in incumbent] == ["a", "b"], "absent, the incumbent key stands"
