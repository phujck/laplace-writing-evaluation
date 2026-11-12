"""test_merge_residue.py — the paragraph_plan residue MERGE + NORMALIZE (design §2.1).

Hermetic BY CONSTRUCTION: every merge test builds a tiny skeleton + residue pair by hand in a
``tmp_path`` store and merges it there (``stores_root=tmp_path``); nothing touches the real
``corpus_stores/``. What is under test is the merge's contract:

  * DRIFT REFUSAL — a residue row that mutated the skeleton's embed_text / char offsets / sha256 is
    refused with a named :class:`~laplace.pipeline.merge_residue.ResidueDriftError`, and NOTHING is
    written (a reader that altered what it was handed is not trusted to have read faithfully);
  * PROVEN PROVENANCE — ``span_ref.offset_basis`` is stamped on every merged row (finding a), and the
    known spliced row is marked ``defective`` + excluded from the gate-eligible set (finding c);
  * NORMALIZATION — ``length_band`` is recomputed uniformly for every row (originals preserved as
    ``length_band_read``), and ``normalized_role`` derives from a taxonomy that covers EVERY slug.

The taxonomy-coverage test also reads the committed store when present, so a slug added to the data
without a taxonomy entry fails loudly here rather than silently miscategorising at merge time.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from laplace.pipeline import merge_residue as M

_REPO_ROOT = Path(__file__).resolve().parents[1]
PAPER = "classical-influence-functionals"   # the real defective row PP-cif-p0011 lives here


# --------------------------------------------------------------------------- #
# hermetic fixtures — a tiny skeleton + residue pair in a tmp store
# --------------------------------------------------------------------------- #
def _skeleton_row(rid: str, text: str, cs: int, ce: int, sha: str, cc: int, pidx: int) -> dict:
    return {
        "row_id": rid, "embed_text": text,
        "form": {"role": None, "connective_prev": None, "connective_next": None,
                 "carries_math": None, "carries_figure": None, "proposition_shape": None,
                 "detail_level": None, "length_band": None,
                 "char_count": cc, "paragraph_span": [pidx, pidx]},
        "provenance": {"paper_id": PAPER, "source_kind": "tex",
                       "span_ref": {"file": "voice_corpus/exemplars/x/main.tex",
                                    "char_start": cs, "char_end": ce, "paragraph_index": pidx,
                                    "section_label": None, "sha256": sha},
                       "extraction_lens": "inherited::voice_corpus",
                       "inherited_from": "voice_corpus"},
    }


def _residue_row(sk: dict, role, band, conn_next="sets-up-derivation", nulled=False) -> dict:
    """A residue row = the skeleton row with the FORM residue filled + residue_read stamped. A
    ``nulled`` residue (the spliced-row reader's output) leaves every FORM field None."""
    r = json.loads(json.dumps(sk))
    if not nulled:
        r["form"].update({"role": role, "connective_prev": None, "connective_next": conn_next,
                          "carries_math": "none", "carries_figure": "none",
                          "proposition_shape": "asserts-the-contribution",
                          "detail_level": "sketch", "length_band": band})
    r["provenance"]["residue_read"] = {"lens": "paragraph_plan-v1", "model": "sonnet"}
    return r


def _write_pair(store_dir: Path, skeleton: list[dict], residue: list[dict]) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / f"{PAPER}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in skeleton), encoding="utf-8")
    (store_dir / f"{PAPER}.residue.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in residue), encoding="utf-8")


def _fixture(tmp_path: Path):
    """Three rows: a normal contribution row, a normal survey row, and the real spliced defective
    row PP-cif-p0011 whose residue is nulled."""
    sk = [
        _skeleton_row("PP-cif-p0002", "his abstract prose.", 157, 1455, "a" * 64, 1298, 2),
        _skeleton_row("PP-cif-p0005", "his survey prose.", 2000, 2600, "b" * 64, 640, 5),
        _skeleton_row("PP-cif-p0011", "spliced prose glued from two ends.", 7683, 8481, "c" * 64,
                      798, 11),
    ]
    res = [
        _residue_row(sk[0], "summarize-the-contribution", [1200, 1350]),
        _residue_row(sk[1], "survey-prior-work", [600, 750]),
        _residue_row(sk[2], None, None, nulled=True),
    ]
    store_dir = tmp_path / "paragraph_plan"
    _write_pair(store_dir, sk, res)
    return store_dir


def _merged_rows(store_dir: Path) -> list[dict]:
    return [json.loads(ln) for ln in (store_dir / f"{PAPER}.jsonl").read_text().splitlines()
            if ln.strip()]


# --------------------------------------------------------------------------- #
# DRIFT REFUSAL — any skeleton mutation refuses the paper's merge, writes nothing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("tamper", ["embed_text", "char_start", "char_end", "sha256", "row_id"])
def test_drift_rejection_fires_on_tampered_row(tmp_path, tamper):
    store_dir = _fixture(tmp_path)
    # tamper the residue's second row on one invariant
    res_path = store_dir / f"{PAPER}.residue.jsonl"
    rows = [json.loads(ln) for ln in res_path.read_text().splitlines() if ln.strip()]
    if tamper == "embed_text":
        rows[1]["embed_text"] = rows[1]["embed_text"] + " (a reader edit)"
    elif tamper == "row_id":
        rows[1]["row_id"] = "PP-cif-p9999"                 # breaks the id-set match
    else:
        rows[1]["provenance"]["span_ref"][tamper] = "TAMPERED" if tamper == "sha256" else 999999
    res_path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    # snapshot the skeleton, then attempt the merge
    skeleton_before = (store_dir / f"{PAPER}.jsonl").read_text()
    with pytest.raises(M.ResidueDriftError):
        M.merge_residue("paragraph_plan", PAPER, stores_root=tmp_path, consume_residue=True)
    # NOTHING written / consumed on refusal: skeleton untouched, residue still present
    assert (store_dir / f"{PAPER}.jsonl").read_text() == skeleton_before
    assert (store_dir / f"{PAPER}.residue.jsonl").is_file()


def test_clean_merge_validates_and_consumes_residue(tmp_path):
    store_dir = _fixture(tmp_path)
    summ = M.merge_residue("paragraph_plan", PAPER, stores_root=tmp_path)
    assert summ["status"] == "validated" and summ["rows"] == 3
    assert summ["defective"] == 1 and summ["roles_null"] == 1
    assert not (store_dir / f"{PAPER}.residue.jsonl").exists()   # residue CONSUMED on success


# --------------------------------------------------------------------------- #
# PROVEN PROVENANCE — offset_basis on every row; defective marked + excludable
# --------------------------------------------------------------------------- #
def test_offset_basis_stamped_on_every_row(tmp_path):
    store_dir = _fixture(tmp_path)
    M.merge_residue("paragraph_plan", PAPER, stores_root=tmp_path)
    for r in _merged_rows(store_dir):
        assert r["provenance"]["span_ref"]["offset_basis"] == "strip_latex(voice_corpus_ingest)"
        # the residue-read stamp survives the merge (the model-read handle)
        assert r["provenance"]["residue_read"] == {"lens": "paragraph_plan-v1", "model": "sonnet"}


def test_defective_row_marked_and_excluded(tmp_path):
    store_dir = _fixture(tmp_path)
    M.merge_residue("paragraph_plan", PAPER, stores_root=tmp_path)
    rows = {r["row_id"]: r for r in _merged_rows(store_dir)}
    assert rows["PP-cif-p0011"]["defective"] == "spliced-by-chunker"
    assert rows["PP-cif-p0011"]["form"]["role"] is None                 # reader nulled it
    assert rows["PP-cif-p0011"]["form"]["normalized_role"] is None      # nulls stay null
    assert "defective" not in rows["PP-cif-p0002"]                      # normal rows unmarked
    # the gate-eligible set (defective + null-class excluded) drops exactly the spliced row
    eligible = [r for r in rows.values()
                if not r.get("defective") and r["form"]["normalized_role"] is not None]
    assert {r["row_id"] for r in eligible} == {"PP-cif-p0002", "PP-cif-p0005"}


# --------------------------------------------------------------------------- #
# NORMALIZATION — uniform length_band (originals preserved); coarse normalized_role
# --------------------------------------------------------------------------- #
def test_length_band_is_uniform_and_original_preserved(tmp_path):
    store_dir = _fixture(tmp_path)
    M.merge_residue("paragraph_plan", PAPER, stores_root=tmp_path)
    rows = {r["row_id"]: r for r in _merged_rows(store_dir)}
    for r in rows.values():
        cc = r["form"]["char_count"]
        lo = 200 * (cc // 200)
        assert r["form"]["length_band"] == [lo, lo + 200]              # mechanical, judge-checkable
    # the reader's ORIGINAL band is preserved verbatim (not overwritten)
    assert rows["PP-cif-p0002"]["form"]["length_band"] == [1200, 1400]   # 1298 -> [1200,1400]
    assert rows["PP-cif-p0002"]["form"]["length_band_read"] == [1200, 1350]
    assert rows["PP-cif-p0011"]["form"]["length_band"] == [600, 800]     # 798 -> [600,800]
    assert rows["PP-cif-p0011"]["form"]["length_band_read"] is None      # nulled reader -> null


def test_uniform_length_band_helper():
    assert M.uniform_length_band(1298) == [1200, 1400]
    assert M.uniform_length_band(798) == [600, 800]
    assert M.uniform_length_band(200) == [200, 400]
    assert M.uniform_length_band(0) == [0, 200]
    assert M.uniform_length_band(None) is None


def test_normalized_role_added_role_untouched(tmp_path):
    store_dir = _fixture(tmp_path)
    M.merge_residue("paragraph_plan", PAPER, stores_root=tmp_path)
    rows = {r["row_id"]: r for r in _merged_rows(store_dir)}
    # role is UNTOUCHED (the reader's slug), normalized_role is the coarse class
    assert rows["PP-cif-p0002"]["form"]["role"] == "summarize-the-contribution"
    assert rows["PP-cif-p0002"]["form"]["normalized_role"] == "abstract-summary"
    assert rows["PP-cif-p0005"]["form"]["role"] == "survey-prior-work"
    assert rows["PP-cif-p0005"]["form"]["normalized_role"] == "survey-prior"


# --------------------------------------------------------------------------- #
# THE TAXONOMY — every slug mapped, uniquely; unknown slug fails loud; nulls pass
# --------------------------------------------------------------------------- #
def test_taxonomy_is_clean_inversion_12_to_16_classes():
    # 12-16 coarse classes (design target); every class non-empty
    assert 12 <= len(M.ROLE_CLASSES) <= 16
    assert all(M.ROLE_TAXONOMY[c] for c in M.ROLE_CLASSES)
    # slug -> class is a clean inversion: no slug lost, none claimed twice
    total = sum(len(v) for v in M.ROLE_TAXONOMY.values())
    assert len(M.SLUG_TO_CLASS) == total
    # nulls pass through; a known slug maps; an unknown slug is a LOUD failure (never silent)
    assert M.normalized_role(None) is None
    assert M.normalized_role("survey-prior-work") == "survey-prior"
    with pytest.raises(KeyError):
        M.normalized_role("a-slug-no-reader-ever-coined")


def test_taxonomy_covers_every_slug_in_the_committed_store():
    """If the real store is on disk, every reader-coined ``role`` in it must be covered by the
    taxonomy — a slug in the data with no taxonomy entry fails HERE, not silently at merge."""
    store_dir = M.CORPUS_STORES / "paragraph_plan"
    jsonls = [p for p in store_dir.glob("*.jsonl")] if store_dir.is_dir() else []
    if not jsonls:
        pytest.skip("paragraph_plan store not built in this tree")
    seen = set()
    for jf in jsonls:
        for ln in jf.read_text().splitlines():
            if not ln.strip():
                continue
            role = json.loads(ln)["form"].get("role")
            if role is not None:
                seen.add(role)
    missing = sorted(s for s in seen if s not in M.SLUG_TO_CLASS)
    assert not missing, f"role slugs in the store with no taxonomy entry: {missing}"
    # and the taxonomy document round-trips the same mapping (the auditable artifact)
    doc = M.role_taxonomy_document()
    assert doc["map"] == {s: M.SLUG_TO_CLASS[s] for s in M.SLUG_TO_CLASS}
    assert doc["n_classes"] == len(M.ROLE_CLASSES)


def test_index_caveats_and_defective_block(tmp_path):
    """finalize_index writes the store-level caveats (findings a + b) + the defective-rows list,
    and the index never carries his-prose (embed_text)."""
    _fixture(tmp_path)
    M.merge_residue("paragraph_plan", PAPER, stores_root=tmp_path)
    M.finalize_index("paragraph_plan", stores_root=tmp_path)
    idx = json.loads((tmp_path / "paragraph_plan" / "_index.json").read_text())
    assert set(idx["caveats"]) == {"offset_basis", "connective_adjacency"}
    assert idx["defective_rows"] == [{"row_id": "PP-cif-p0011", "paper_id": PAPER,
                                      "reason": "spliced-by-chunker"}]
    assert all("embed_text" not in r for r in idx["rows"])       # no his-prose in the index
    assert idx["row_count"] == 3


# =========================================================================== #
# THE FOUR-LENS GENERALIZATION — section/spine/derivation/figure share ONE merge
# =========================================================================== #
# Hermetic BY CONSTRUCTION, exactly as the paragraph tests above: every four-lens test builds a tiny
# skeleton + residue pair by hand in a tmp store and merges it there. What is under test is that the
# ONE generalized merge (:func:`merge_residue` dispatching on :data:`FOUR_LENS_SPECS`) folds ONLY the
# reader-filled fields, refuses on any drift to an invariant, derives the coarse section taxonomy,
# and stamps the caveat ledger's defective (a+b) / caveat (c+d) marks — per store.
P4 = "p4-test"


def _sa_pair(job_proxy, job_fine, rid="SA-p4-s0", node="sec:x", cs=0, ce=100):
    """A section_architecture skeleton + residue pair: the reader replaced the mechanical `job`
    proxy with a fine per-paper slug and filled arc/question_class; everything else is invariant."""
    sk = {"row_id": rid, "embed_text": "his section prose.",
          "form": {"job": job_proxy, "arc": None, "question_class": None, "position": "1-of-2",
                   "para_count": 3, "forward_reach": "used-by-0-later-sections",
                   "carries": {"equations": 1, "figures": 0}, "title": "T"},
          "provenance": {"paper_id": P4, "source_kind": "tex",
                         "extraction_lens": "section_architecture",
                         "span_ref": {"node_ids": [node], "section_label": node,
                                      "file": "x.tex", "char_start": cs, "char_end": ce}}}
    res = json.loads(json.dumps(sk))
    res["form"].update({"job": job_fine, "arc": {"entry_state": "a", "exit_state": "b"},
                        "question_class": "how-x"})
    res["provenance"]["residue_read"] = {"lens": "section_architecture-v1", "model": "sonnet"}
    return sk, res


def _write_four(store_dir: Path, skeleton: list[dict], residue: list[dict]) -> None:
    store_dir.mkdir(parents=True, exist_ok=True)
    (store_dir / f"{P4}.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in skeleton), encoding="utf-8")
    (store_dir / f"{P4}.residue.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in residue), encoding="utf-8")


def _merged(store_dir: Path) -> list[dict]:
    return [json.loads(ln) for ln in (store_dir / f"{P4}.jsonl").read_text().splitlines() if ln.strip()]


def test_four_lens_folds_only_residue_fields_and_normalizes(tmp_path):
    """section_architecture: the fine `job` is folded, the coarse `normalized_job` is derived, the
    overridden mechanical proxy is preserved as `job_mechanical`, and every OTHER form field is
    byte-identical to the skeleton (the reader may touch only its residue fields)."""
    sk, res = _sa_pair("develop", "derive-the-central-correspondence")
    sk2, res2 = _sa_pair("introduce", "motivate-and-outline", rid="SA-p4-s1", node="sec:y",
                         cs=100, ce=200)
    d = tmp_path / "section_architecture"
    _write_four(d, [sk, sk2], [res, res2])
    summ = M.merge_residue("section_architecture", P4, stores_root=tmp_path)
    assert summ["status"] == "validated" and summ["rows"] == 2 and summ["defective"] == 0
    rows = {r["row_id"]: r for r in _merged(d)}
    r0 = rows["SA-p4-s0"]["form"]
    assert r0["job"] == "derive-the-central-correspondence"     # fine slug folded (reader's)
    assert r0["normalized_job"] == "derive-prove"              # coarse class derived
    assert r0["job_mechanical"] == "develop"                   # overridden proxy preserved for audit
    assert r0["arc"] == {"entry_state": "a", "exit_state": "b"} and r0["question_class"] == "how-x"
    # every non-residue form field byte-identical to the skeleton
    assert (r0["position"], r0["para_count"], r0["carries"], r0["title"]) == (
        "1-of-2", 3, {"equations": 1, "figures": 0}, "T")
    assert rows["SA-p4-s0"]["provenance"]["residue_read"]["lens"] == "section_architecture-v1"
    assert not (d / f"{P4}.residue.jsonl").exists()            # residue CONSUMED


@pytest.mark.parametrize("tamper", ["embed_text", "form_invariant", "span_ref", "row_id",
                                    "extra_provenance"])
def test_four_lens_drift_rejection_fires(tmp_path, tamper):
    """A residue that mutated ANYTHING the reader was not allowed to fill (embed_text, a non-residue
    form field, span_ref, row_id, or an extra provenance key) refuses the paper's merge, writes
    nothing. An ALLOWED field (job) differing is NOT drift — that is the whole point of the merge."""
    sk, res = _sa_pair("develop", "derive-the-central-correspondence")
    d = tmp_path / "section_architecture"
    if tamper == "embed_text":
        res["embed_text"] += " (a reader edit)"
    elif tamper == "form_invariant":
        res["form"]["position"] = "9-of-9"                    # a MECHANICAL field the reader must keep
    elif tamper == "span_ref":
        res["provenance"]["span_ref"]["char_start"] = 999999
    elif tamper == "row_id":
        res["row_id"] = "SA-p4-s9"
    elif tamper == "extra_provenance":
        res["provenance"]["lens_model"] = "smuggled"          # a provenance key beyond residue_read
    _write_four(d, [sk], [res])
    before = (d / f"{P4}.jsonl").read_text()
    with pytest.raises(M.ResidueDriftError):
        M.merge_residue("section_architecture", P4, stores_root=tmp_path)
    assert (d / f"{P4}.jsonl").read_text() == before          # skeleton untouched
    assert (d / f"{P4}.residue.jsonl").is_file()              # residue not consumed


def test_allowed_field_diff_is_not_drift(tmp_path):
    """The reader REPLACING the mechanical `job` proxy with a fine slug is the intended behaviour,
    never drift — the merge validates and folds it."""
    sk, res = _sa_pair("develop", "prove-the-uniqueness-theorem")   # job differs by design
    d = tmp_path / "section_architecture"
    _write_four(d, [sk], [res])
    summ = M.merge_residue("section_architecture", P4, stores_root=tmp_path)
    assert summ["status"] == "validated"
    assert _merged(d)[0]["form"]["normalized_job"] == "derive-prove"


def test_section_job_taxonomy_is_clean_inversion_12_to_16_classes():
    assert 12 <= len(M.JOB_CLASSES) <= 16
    assert all(M.JOB_TAXONOMY[c] for c in M.JOB_CLASSES)
    total = sum(len(v) for v in M.JOB_TAXONOMY.values())
    assert len(M.JOB_SLUG_TO_CLASS) == total                  # no slug lost or claimed twice
    assert M.normalized_job(None) is None
    assert M.normalized_job("motivate-and-outline") == "introduce-motivate"
    with pytest.raises(KeyError):
        M.normalized_job("a-slug-no-section-reader-ever-coined")
    doc = M.job_taxonomy_document()
    assert doc["map"] == {s: M.JOB_SLUG_TO_CLASS[s] for s in M.JOB_SLUG_TO_CLASS}
    assert doc["n_classes"] == len(M.JOB_CLASSES)


def test_section_job_taxonomy_covers_every_slug_in_committed_store():
    """Every reader-coined `job` in the committed section_architecture store must be covered — a slug
    in the data with no taxonomy entry fails HERE, not silently at merge (twin of the role check)."""
    store_dir = M.CORPUS_STORES / "section_architecture"
    jsonls = [p for p in store_dir.glob("*.jsonl")] if store_dir.is_dir() else []
    if not jsonls:
        pytest.skip("section_architecture store not built in this tree")
    seen = set()
    for jf in jsonls:
        for ln in jf.read_text().splitlines():
            if ln.strip():
                job = json.loads(ln)["form"].get("job")
                if job is not None:
                    seen.add(job)
    missing = sorted(s for s in seen if s not in M.JOB_SLUG_TO_CLASS)
    assert not missing, f"job slugs in the store with no taxonomy entry: {missing}"


def test_spine_ladder_move_used_directly_and_mechanical_preserved(tmp_path):
    """spine_chain gates on the FAITHFUL `ladder_move` DIRECTLY (a closed vocab, no taxonomy); the
    overridden mechanical num-dep proxy is preserved as `ladder_move_mechanical`."""
    sk = {"row_id": "SC-p4-eqA", "embed_text": "the two claims' prose + latex.",
          "form": {"rung": 1, "of_rungs": 3, "ladder_move": "extend", "depends_on_rung": 0,
                   "claim_class": None, "supports_class": None},
          "provenance": {"paper_id": P4, "source_kind": "tex", "extraction_lens": "spine_chain",
                         "span_ref": {"node_ids": ["eq:A", "eq:B"], "section_node": "sec:x",
                                      "source": "conceptric-derivation-dag"}}}
    res = json.loads(json.dumps(sk))
    res["form"].update({"ladder_move": "apply", "claim_class": "mapping",
                        "supports_class": "algorithm"})
    res["provenance"]["residue_read"] = {"lens": "spine_chain-v1", "model": "sonnet"}
    d = tmp_path / "spine_chain"
    _write_four(d, [sk], [res])
    M.merge_residue("spine_chain", P4, stores_root=tmp_path)
    f = _merged(d)[0]["form"]
    assert f["ladder_move"] == "apply"                        # faithful folded (the gate class)
    assert f["ladder_move_mechanical"] == "extend"            # proxy preserved for audit
    assert "normalized_ladder_move" not in f                  # closed vocab -> no taxonomy fold
    assert M.FOUR_LENS_SPECS["spine_chain"].gate_class_key == "ladder_move"


def _fig_row(rid, embed, figure_role, caption_size="standard"):
    sk = {"row_id": rid, "embed_text": embed,
          "form": {"caption_move": None, "figure_role": None, "panels": None, "panel_labels": None,
                   "has_caption": True, "caption_size": caption_size, "caption_len": len(embed),
                   "caption_len_band": [0, 80], "ref_density": "referenced-by-1-sections",
                   "referenced_by_sections": 1, "position": "1-of-1"},
          "provenance": {"paper_id": P4, "source_kind": "tex", "extraction_lens": "figure_caption",
                         "span_ref": {"node_ids": [f"fig:{rid}"], "section_node": "sec:x",
                                      "referenced_by": ["sec:x"], "file": "x.tex"}}}
    res = json.loads(json.dumps(sk))
    res["form"].update({"caption_move": "labels", "figure_role": figure_role, "panels": None,
                        "panel_labels": None})
    res["provenance"]["residue_read"] = {"lens": "figure_caption-v1", "model": "sonnet"}
    return sk, res


def test_figure_defective_named_and_mechanically_detected_excluded(tmp_path):
    """figure_caption: (a) a NAMED dead-commented row keeps its authoritative reason; (b) a label-
    fragment row NOT on the ledger's list is caught by the mechanical detector as caption-truncated;
    both are excluded from the gate-eligible set, while a real-caption row stays eligible."""
    real = _fig_row("FC-p4-real", "A real evidential caption of some length.", "evidence")
    dead = _fig_row("FC-qdei-convergence", "Illustration of convergence.", "data")   # NAMED (a)
    frag = _fig_row("FC-p4-frag", "\\label{fig:frag}", "schematic", caption_size="terse")  # detected (b)
    d = tmp_path / "figure_caption"
    _write_four(d, [real[0], dead[0], frag[0]], [real[1], dead[1], frag[1]])
    summ = M.merge_residue("figure_caption", P4, stores_root=tmp_path)
    rows = {r["row_id"]: r for r in _merged(d)}
    assert "defective" not in rows["FC-p4-real"]
    assert rows["FC-qdei-convergence"]["defective"] == "dead-commented-source"     # named list wins
    assert rows["FC-p4-frag"]["defective"] == "caption-truncated-mechanical"       # detector caught it
    assert summ["defective"] == 2
    eligible = [r for r in rows.values()
                if not r.get("defective") and r["form"].get("figure_role") is not None]
    assert {r["row_id"] for r in eligible} == {"FC-p4-real"}   # only the clean row gates


def test_four_lens_caveat_marked_but_not_excluded(tmp_path):
    """A caveat row (finding c/d) is FLAGGED (`caveat`) but NOT defective — its residue FORM is
    sound, so it stays gate-eligible (spine_chain's rung-artifact row)."""
    cav_id = "SC-pfatoqsih-Single-Trajectory_Density_Matrix_Path_Integral"
    sk = {"row_id": cav_id, "embed_text": "the rung-artifact node prose.",
          "form": {"rung": 0, "of_rungs": 3, "ladder_move": "extend", "depends_on_rung": 0,
                   "claim_class": None, "supports_class": None},
          "provenance": {"paper_id": P4, "source_kind": "tex", "extraction_lens": "spine_chain",
                         "span_ref": {"node_ids": ["eq:x"], "section_node": "sec:x",
                                      "source": "conceptric-derivation-dag"}}}
    res = json.loads(json.dumps(sk))
    res["form"]["ladder_move"] = "specialise"
    res["provenance"]["residue_read"] = {"lens": "spine_chain-v1", "model": "sonnet"}
    d = tmp_path / "spine_chain"
    _write_four(d, [sk], [res])
    summ = M.merge_residue("spine_chain", P4, stores_root=tmp_path)
    row = _merged(d)[0]
    assert row["caveat"] == "rung-artifact" and "defective" not in row
    assert summ["caveat"] == 1 and summ["defective"] == 0
    # gate-eligible: caveat rows are NOT excluded (residue sound)
    assert row["form"]["ladder_move"] == "specialise"


def test_four_lens_index_carries_caveats_defective_and_caveat_lists(tmp_path):
    """finalize_index writes the store-level caveats (finding e), the defective_rows AND caveat_rows
    lists, and the gate_class name; the index never carries embed_text."""
    real = _fig_row("FC-p4-real", "A real caption.", "evidence")
    frag = _fig_row("FC-p4-frag", "\\label{fig:frag}", "schematic", caption_size="terse")
    d = tmp_path / "figure_caption"
    _write_four(d, [real[0], frag[0]], [real[1], frag[1]])
    M.merge_residue("figure_caption", P4, stores_root=tmp_path)
    M.finalize_index("figure_caption", stores_root=tmp_path)
    idx = json.loads((d / "_index.json").read_text())
    assert idx["gate_class"] == "figure_role"
    assert set(idx["caveats"]) == set(M.FOUR_LENS_SPECS["figure_caption"].store_caveats)
    assert idx["defective_rows"] == [{"row_id": "FC-p4-frag", "paper_id": P4,
                                      "reason": "caption-truncated-mechanical"}]
    assert idx["caveat_rows"] == []
    assert all("embed_text" not in r for r in idx["rows"])
    assert idx["row_count"] == 2
