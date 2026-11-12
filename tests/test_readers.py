"""The reader suite (Phase E, checklist cat 13) — plumbing tests.

builder ≠ judge: these exercise the PLUMBING (slicing, sealing, packaging, parsing,
R3 aggregation, the floors, the roster invariants), never the read QUALITY (that
needs the real sealed reads at candidate-lock + Gerard). The SSG-dependent tests run
on the real whitepaper when present; the logic tests run everywhere.
"""
from pathlib import Path

import pytest

from laplace.pipeline import readers as R
from laplace.pipeline.readers import apparatus, referee, sealed, visual
from laplace.pipeline.convergence import HARD_DIMENSIONS, SOFT_DIMENSIONS
from laplace.pipeline.schema import WORK_KINDS, WORK_TO_LAYER

REPO = Path(__file__).resolve().parents[1]
SSG = REPO / "synthetics papers/subset-sum-itqde/manuscript/whitepaper/main.tex"
SSG_DIR = SSG.parent
_have_ssg = pytest.mark.skipif(not SSG.is_file(), reason="SSG manuscript not present")


# --- the two design invariants ----------------------------------------------

def test_single_ownership_of_14_hard_failures():
    res = R.verify_single_ownership()
    assert res["ok"], res["violations"]
    assert res["n_failures"] == 14          # 13 Phase-E + R10's identity-mismatch (#14)
    # every owner is a real reader; no failure double-owned
    owners = R.owned_hard_failures()
    assert len(owners) == 14
    assert set(owners.values()) <= set(R.READERS)
    # R10 solely owns the whole-artefact identity failure
    assert owners["identity-mismatch"] == "R10"


def test_finding_kind_partition_is_clean():
    res = R.verify_kind_partition()
    assert res["ok"], res["violations"]
    # each new reader kind maps to exactly one reader
    seen: dict[str, str] = {}
    for k, rk in R.READER_FINDING_KINDS.items():
        assert k not in seen or seen[k] == rk.reader
        seen[k] = rk.reader


def test_silence_never_reads_as_pass():
    assert R.reader_verdict_score(None) == 0.5           # never ran
    assert R.reader_verdict_score({"failed": True}) == 0.5
    assert R.reader_verdict_score({"clean": True}) == 1.0
    assert R.reader_verdict_score({"flags": [1, 2, 3]}) == pytest.approx(0.55)
    assert R.reader_verdict_score({}) == 0.5             # empty = neither clean nor flagged


def test_all_readers_present_and_five_organs():
    # R1..R8 (the Phase-E suite) + R9 Caption-blind + R10 Restart (whole-artefact judge).
    assert set(R.READERS) == {f"R{i}" for i in range(1, 11)}
    organs = {r.organ for r in R.READERS.values()}
    assert organs == {"sealed_subagent", "adversary", "apparatus", "rasteriser", "human"}
    # R9 reuses the rasteriser organ; R10 reuses the sealed-subagent organ (a blind
    # read of the rendered PDF text) — the organ set is unchanged.
    assert R.READERS["R9"].organ == "rasteriser"
    assert R.READERS["R10"].organ == "sealed_subagent"


# --- dimensions map onto EXISTING axes only (no new dim invented) ------------

def test_reader_dimensions_are_existing_axes():
    allowed = set(HARD_DIMENSIONS) | set(SOFT_DIMENSIONS) | {"author_acceptance"}
    for r in R.READERS.values():
        assert r.dimension in allowed, f"{r.id} invents dim {r.dimension!r}"


def test_dimension_manifest_shape():
    rows = R.dimension_manifest()
    assert {row["reader"] for row in rows} == set(R.READERS)
    for row in rows:
        assert row["hardness"] in ("hard", "soft", "terminal")


# --- the finding-kinds manifest is Phase-F-wireable --------------------------

def test_new_kinds_route_through_the_existing_schema():
    for row in R.finding_kinds_manifest():
        # Phase F sets KIND_TO_WORK[kind] = work_kind; WORK_TO_LAYER already carries
        # work_kind -> owning_stage. Assert the target rows exist so the wiring is legal.
        if row["work_kind"] is None:
            # verdict-only reader kinds (R10's whole-artefact judgements): no per-node
            # work, so no owning stage — they fold to KIND_TO_WORK[kind]=None, the same
            # idiom projection-intent and the desk-review kinds use.
            assert row["owning_stage"] is None
        else:
            assert row["work_kind"] in WORK_KINDS
            assert WORK_TO_LAYER[row["work_kind"]] == row["owning_stage"]
        assert row["reader"] in R.READERS


# --- R1/R4/R7 sealed-subagent organ: input slicing --------------------------

_FIXTURE = r"""
\begin{abstract}
We report a spectral method and measure its reconstruction error.
\end{abstract}
\section{Introduction}
BODYSENTINEL the introduction develops the operator formalism at length.
\begin{figure}\caption{CAPSENTINEL the reconstruction on a random instance.}\end{figure}
\section{Methods}
MIDBODY the derivation proceeds through the resolvent expansion.
\section{Conclusion}
CONCLSENTINEL we conclude the method reconstructs the spectrum.
"""


def test_skim_slice_excludes_the_body(tmp_path):
    f = tmp_path / "m.tex"
    f.write_text(_FIXTURE)
    skim = sealed.skim_slice(f)
    # abstract, captions, conclusion are IN
    assert "spectral method" in skim               # abstract
    assert "CAPSENTINEL" in skim                    # caption
    assert "CONCLSENTINEL" in skim                  # conclusion
    # the BODY is physically absent — the whole point of the truncation
    assert "BODYSENTINEL" not in skim
    assert "MIDBODY" not in skim
    # and the slice is labelled by region
    assert all(tag in skim for tag in ("ABSTRACT", "CAPTIONS", "CONCLUSION"))


def test_prose_slice_masks_math(tmp_path):
    f = tmp_path / "m.tex"
    f.write_text(r"The gap is $\Delta_{\max}$ and \begin{equation}E=mc^2\label{e}\end{equation} holds."
                 "\n\nA second paragraph of ordinary readable prose about the method here.")
    prose = sealed.prose_slice(f)
    assert "mc^2" not in prose and "Delta" not in prose     # math masked out
    assert "readable prose" in prose


def test_full_slice_is_whole_text(tmp_path):
    f = tmp_path / "m.tex"
    f.write_text(_FIXTURE)
    assert "BODYSENTINEL" in sealed.full_slice(f)            # nothing withheld


def test_slice_for_rejects_non_sealed_reader():
    with pytest.raises(KeyError):
        sealed.slice_for("R3", "x.tex")


# --- the seal holds / catches a leak ----------------------------------------

def test_seal_holds_on_real_pack_and_catches_injection(tmp_path):
    f = tmp_path / "m.tex"
    f.write_text(_FIXTURE)
    for rid in ("R1", "R4", "R7"):
        p = sealed.pack_for_sealed_read(rid, f)
        assert p["seal_check"]["ok"], p["seal_check"]["leaks"]
        assert "RECOVERABLES CHECKLIST" in p["prompt"]
        assert p["allowed_kinds"] == list(R.READERS[rid].owned_kinds)
    # a spec sentinel injected into a sealed input is CAUGHT
    leaked = sealed.seal_holds({"sealed_input": "...reading_order: 3 ... POLICY: ...",
                                "prompt": ""})
    assert not leaked["ok"]
    assert {l["sentinel"] for l in leaked["leaks"]} >= {"POLICY", "reading_order"}


def test_pack_flags_truncation(tmp_path):
    f = tmp_path / "m.tex"
    f.write_text("word " * 5000)                            # ~25k chars
    p = sealed.pack_for_sealed_read("R1", f, max_input_chars=1000)
    assert p["truncated"] is True
    assert len(p["sealed_input"]) == 1000


# --- verdict parsing is tolerant --------------------------------------------

def test_parse_sealed_bare_fenced_envelope():
    bare = sealed.parse_sealed_verdict(
        "R1", '[{"where":"s2","issue":"x","fix":"y","kind":"cold-undefined-term"}]')
    assert len(bare) == 1 and bare[0]["owning_stage"] == "prose" and bare[0]["reader"] == "R1"
    fenced = sealed.parse_sealed_verdict(
        "R7", '```json\n{"findings":[{"where":"p1","issue":"tic","fix":"vary","kind":"feral-cadence"}]}\n```')
    assert fenced[0]["kind"] == "feral-cadence"


def test_parse_sealed_unknown_coerces_then_strict_drops():
    raw = '[{"where":"x","issue":"y","fix":"z","kind":"gremlin"}]'
    lenient = sealed.parse_sealed_verdict("R1", raw)
    assert lenient and lenient[0]["kind"] in R.READERS["R1"].owned_kinds
    assert sealed.parse_sealed_verdict("R1", raw, strict=True) == []


def test_parse_sealed_malformed_never_crashes():
    assert sealed.parse_sealed_verdict("R4", "not json") == []
    assert sealed.parse_sealed_verdict("R4", "") == []
    assert sealed.parse_sealed_verdict("R4", "{}") == []


# --- R3 Apparatus: aggregation (runnable now) -------------------------------

@_have_ssg
def test_r3_apparatus_aggregates_all_four_owned_failures_on_ssg():
    v = apparatus.read_apparatus(SSG)
    assert v["reader"] == "R3" and v["failed"] is False
    assert not v["clean"]                                    # SSG has known apparatus faults
    # every one of R3's four owned hard-failures fires on SSG
    for hid in R.READERS["R3"].owns:
        assert v["owned_failures"][hid] > 0, f"{hid} did not fire"
    # every finding is stamped R3 and routed
    for f in v["findings"]:
        assert f["reader"] == "R3"
        assert "owning_stage" in f
    # the four spine legs all ran (pass flag present, not an error)
    assert set(v["by_module"]) == {
        "equation_lifecycle", "citation_audit", "crosslink_audit", "notation_audit"}
    for leg in v["by_module"].values():
        assert "error" not in leg


def test_r3_is_runnable_now_and_r6_floor_too():
    assert R.READERS["R3"].runnable_now is True
    assert R.READERS["R6"].runnable_now is True             # the log-overfull panel floor needs no model
    # the packaged-for-F readers are marked so
    for rid in ("R1", "R2", "R4", "R5", "R7", "R8", "R9"):
        assert R.READERS[rid].runnable_now is False


# --- R2 Referee: intent-only seal + shared floor + parse --------------------

@_have_ssg
def test_r2_referee_pack_is_intent_sealed_and_domain_armed():
    p = referee.pack_for_referee_read(SSG, domain="quantum spectral estimation")
    assert p["seal_check"]["ok"]
    assert "domain" in p["seal"]["allows"]                  # armed with the domain
    assert set(p["seal"]["denies"]) == {"spec", "plan", "narrative"}
    # injecting the construction intention is CAUGHT (even though domain is allowed)
    bad = referee.pack_for_referee_read(SSG, domain="physics; blueprint: OBJECT channel from POLICY")
    assert not bad["seal_check"]["ok"]


@_have_ssg
def test_r2_floor_shares_r3_citation_tells():
    floor = referee.referee_floor(SSG)
    assert floor, "no sufficiency probes surfaced"
    for f in floor:
        assert f["reader"] == "R2" and f["floor"] is True
        assert f["kind"] in R.READERS["R2"].owned_kinds


def test_r2_parse_tolerant():
    out = referee.parse_referee_verdict(
        '[{"where":"claim 3","issue":"thin evidence","fix":"add sim","kind":"referee-insufficient"}]')
    assert out[0]["kind"] == "referee-insufficient" and out[0]["owning_stage"] == "projection"
    assert referee.parse_referee_verdict("junk") == []
    coerced = referee.parse_referee_verdict('[{"where":"x","issue":"y","kind":"bogus"}]')
    assert coerced[0]["kind"] == "referee-insufficient"


# --- R5/R6 rasteriser organ: two lenses over one crop set -------------------

def _mock_inspection():
    from laplace.pipeline import visual_gate as vg
    insp = vg.Inspection(pdf="x.pdf", n_pages=2, dpi=150, out_dir="/tmp")
    insp.views = {
        "contact_sheet": "/tmp/cs.png",
        "figure_crops": [{"label": "fig:a", "page": 4, "path": "/tmp/f.png"}],
        "reading_crops": ["/tmp/r.png"],
        "equation_crops": [{"label": "res:x", "page": 3, "path": "/tmp/e.png"}],
        "boundary_overlays": ["/tmp/o.png"],
    }
    insp.overfull = []          # log-owned now; the pixel detector was deleted
    return insp


def test_r5_meaning_lens_reuses_figure_crops():
    insp = _mock_inspection()
    p = visual.pack_figure_meaning(insp)
    assert p["reader"] == "R5" and p["seal_check"]["ok"]
    assert p["allowed_kinds"] == list(R.READERS["R5"].owned_kinds)
    assert [i["label"] for i in p["images"]] == ["fig:a"]     # the SAME crops
    out = visual.parse_figure_verdict(
        '[{"where":"fig:a","issue":"two purposes","fix":"split","kind":"figure-not-singular"}]')
    assert out[0]["owning_stage"] == "figures" and out[0]["reader"] == "R5"


def test_r6_geometry_lens_is_the_d2_judge_with_inverse_seal():
    insp = _mock_inspection()
    p = visual.pack_geometry(insp)
    assert p["reader"] == "R6" and p["owning_stage"] == "document"
    assert p["seal_check"]["ok"]                              # instruction carries the inverse seal
    assert "overfull-visual" not in p["allowed_kinds"]        # retargeted scope
    # R6 has NO reader-side overfull floor: log-locatable overflow is owned by the
    # mechanical panel; R6 never re-inspects it.
    assert visual.geometry_floor(insp) == []
    out = visual.parse_geometry_verdict(
        '[{"where":"p6","issue":"eq past margin","fix":"break","kind":"equation-clip"}]')
    assert out[0]["kind"] == "equation-clip" and out[0]["reader"] == "R6"


def test_r6_geometry_read_drops_planted_overfull():
    # the scope exclusion is mechanical: a planted log-locatable overfull verdict
    # from the vision reader is dropped, a real geometry finding survives.
    out = visual.parse_geometry_verdict(
        '[{"where":"p6","issue":"past margin","fix":"reflow","kind":"overfull-visual"},'
        '{"where":"p2","issue":"gutter cross","fix":"widen","kind":"column-collision"}]')
    assert [f["kind"] for f in out] == ["column-collision"]
    assert all(f["reader"] == "R6" for f in out)


def test_r5_r6_kinds_are_disjoint():
    # the meaning lens and the geometry lens never emit the same kind
    assert set(R.READERS["R5"].owned_kinds).isdisjoint(R.READERS["R6"].reused_kinds)


@pytest.mark.skipif(not SSG_DIR.is_dir(), reason="SSG manuscript not present")
def test_r5_figure_floor_runs_mechanically_on_ssg():
    floor = visual.figure_floor(SSG_DIR)
    assert isinstance(floor, list)
    for f in floor:
        assert f["reader"] == "R5" and f.get("floor") is True
