"""The truth-layer verdict readers (fix wave, cross-surface truth).

Covers the three project_state changes the interface fix wave landed, HERMETICALLY
(SimpleNamespace contexts + tmp_path trees — no dependency on the live corpus):

  * ``_rounds`` is TARGET-AWARE — a project whose harnessed rounds live under the
    target dir (not the manuscript dir) no longer reads a false 0; the manuscript
    dir is the fallback, and an empty target dir never masks a populated manuscript.
  * ``_artefact`` carries an honest ``exists`` flag — a finalize/current-artefact
    record whose PDF is gone on disk reads ``exists: False`` (P7), never presented
    as a live artefact.
  * ``_position`` NAMES the harnessed mechanic ("N harnessed rounds", ruled R2) in
    the pre-release evidence lines.

builder != judge: these pin the PLUMBING (which base is read, the disk-truth flag,
the label vocabulary), not any one project's live numbers.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from laplace.pipeline import project_state as ps


def _ctx(target_dir=None, manuscript_dir=None, current_artefact=None):
    return SimpleNamespace(target_dir=target_dir, manuscript_dir=manuscript_dir,
                           current_artefact=current_artefact)


def _plant_detect(base: Path, names: list[str]) -> None:
    h = base / "rounds" / "harnessed"
    h.mkdir(parents=True, exist_ok=True)
    for n in names:
        (h / n).write_text("{}")


# --- _rounds: target-awareness -------------------------------------------------

def test_rounds_reads_the_target_dir_when_manuscript_is_bare(tmp_path):
    """A target!=manuscript project (subset-sum shape): rounds live under the TARGET;
    the manuscript dir carries none. The reader must find them, not read a false 0."""
    md = tmp_path / "manuscript"
    td = tmp_path / "manuscript" / "whitepaper"
    md.mkdir(parents=True)
    _plant_detect(td, ["detect_pre_r1.json", "detect_post_r2.json"])
    out = ps._rounds(_ctx(target_dir=td, manuscript_dir=md))
    assert out == {"n": 2, "last": 2}


def test_rounds_reads_the_manuscript_dir_when_target_is_empty(tmp_path):
    """target==manuscript (falqon shape) / an empty target: the manuscript dir wins;
    an existing-but-empty target harnessed dir never masks the populated fallback."""
    md = tmp_path / "manuscript"
    td = tmp_path / "target"
    (td / "rounds" / "harnessed").mkdir(parents=True)      # exists, but EMPTY
    _plant_detect(md, ["detect_pre_r1.json", "detect_post_r3.json", "detect_post_r7.json"])
    out = ps._rounds(_ctx(target_dir=td, manuscript_dir=md))
    assert out == {"n": 3, "last": 7}


def test_rounds_target_first_when_both_populated(tmp_path):
    """When both bases carry rounds, target-first wins (the two-root order)."""
    md = tmp_path / "manuscript"
    td = tmp_path / "target"
    _plant_detect(td, ["detect_pre_r1.json"])
    _plant_detect(md, ["detect_pre_r1.json", "detect_post_r2.json"])
    assert ps._rounds(_ctx(target_dir=td, manuscript_dir=md)) == {"n": 1, "last": 1}


def test_rounds_absent_everywhere_is_honest_zero(tmp_path):
    md = tmp_path / "manuscript"; md.mkdir()
    assert ps._rounds(_ctx(target_dir=None, manuscript_dir=md)) == {"n": 0, "last": None}
    assert ps._rounds(None) == {"n": 0, "last": None}


# --- _artefact: honest-absence exists flag -------------------------------------

def test_artefact_current_pdf_present_reads_exists_true(tmp_path):
    root = tmp_path
    md = root / "proj" / "manuscript"; md.mkdir(parents=True)
    pdf = md / "main.pdf"; pdf.write_bytes(b"%PDF-1.5\n")
    ctx = _ctx(manuscript_dir=md,
               current_artefact={"pdf": "proj/manuscript/main.pdf", "version_id": None})
    art = ps._artefact(ctx, root)
    assert art is not None and art["exists"] is True and art["name"] == "main"


def test_artefact_current_pdf_absent_reads_exists_false(tmp_path):
    """P7 honest absence: the record names a PDF that is not on disk → exists False,
    never a live artefact (the eigenengine-r1 shape: a reopened project past its mint)."""
    root = tmp_path
    md = root / "proj" / "manuscript"; md.mkdir(parents=True)
    ctx = _ctx(manuscript_dir=md,
               current_artefact={"pdf": "proj/manuscript/gone.pdf", "version_id": "v-r1"})
    art = ps._artefact(ctx, root)
    assert art is not None and art["exists"] is False and art["name"] == "v-r1"


def test_artefact_finalize_absent_pdf_reads_exists_false(tmp_path):
    """The finalize-record branch: a banked mint whose PDF was later removed reads
    exists False, so the strip can say 'recorded, absent on disk'."""
    root = tmp_path
    md = root / "proj" / "manuscript"; md.mkdir(parents=True)
    rel = md / "release"; rel.mkdir()
    (rel / "finalize.json").write_text(json.dumps(
        {"slug": "proj-2026-07-14-r1", "pdf_path": "proj-2026-07-14-r1.pdf",
         "created": "2026-07-14T06:01:38"}))
    ctx = _ctx(manuscript_dir=md, current_artefact=None)
    art = ps._artefact(ctx, root)
    assert art is not None
    assert art["name"] == "proj-2026-07-14-r1"
    assert art["minted_at"] == "2026-07-14T06:01:38"
    assert art["exists"] is False


# --- _position: the harnessed-mechanic vocabulary (ruled R2) --------------------

def test_position_pre_release_evidence_names_harnessed_rounds():
    """A NEVER_RUN row with rounds + a minted artefact renders 'pre-release' and the
    evidence NAMES the harnessed mechanic — never a bare 'N rounds' that reads as a
    contradiction beside analytics' banked count."""
    row = {"state": "NEVER_RUN", "rounds_n": 9}
    artefact = {"name": "paper-x-2026-07-21-r2", "minted_at": "2026-07-21T14:26:37",
                "exists": True}
    generations = {"present": True, "gen": "GEN-3"}
    position, evidence = ps._position(row, artefact, generations)
    assert position.startswith("pre-release")
    assert any("9 harnessed rounds" in e for e in evidence)
    assert not any(e.startswith("9 rounds ") for e in evidence)  # never the bare form
