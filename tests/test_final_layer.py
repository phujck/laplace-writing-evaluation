"""final_layer — the rhetorical de-scaffolding wash (the last projection layer).

The conjugate of scaffold_wipe one level up: it detects the four defensive voice
registers, the abstract negative-inventory, the §VII self-demotion, and applies the
disclaimer keep-once-where table. Each detector is asserted to FIRE on the live SSG
whitepaper (the referee/audit/disclosure/defensive voices ARE in the prose; the
disclaimers DO repeat) AND to be QUIET on a synthetic-clean fixture — the delta-rule
proof it is hardened against real prose, not a straw man. The dial is asserted OFF by
default and to gate the end-stage wash like the voice wash.
"""
from pathlib import Path

import pytest

from laplace.pipeline import dials as D
from laplace.pipeline import final_layer as FL

REPO = Path(__file__).resolve().parents[1]
SSG = REPO / "synthetics papers/subset-sum-itqde/manuscript/whitepaper"

_have_ssg = pytest.mark.skipif(
    not (SSG.is_dir() and (SSG / "main.tex").is_file()),
    reason="needs the SSG manuscript source")

# a synthetic DIRTY manuscript: all four defensive registers, a negative-inventory
# abstract, a §VII self-demotion, and a repeated boundary — the delta fixture the
# detectors must fire on (kept synthetic so the test is independent of the live
# manuscript's descaffold state, which the RUN drives to clean).
_DIRTY = r"""
\documentclass{article}
\begin{document}
\begin{abstract}
The method reconstructs a spectral surface from one campaign. We validate on a
controlled family. It asserts no asymptotic hardness and no quantum advantage,
uses no quantum hardware data, and is proof of principle.
\end{abstract}
\section{Numerical validation}
Every numerical statement carries one of four evidence classes, and each names the
method behind it. The figure does not establish hardness. Entangling does not mean
hard, and the growth is growth, not hardness. The result is a finite-size statement
over the tested sizes, not a hardness no-go.
\section{Limits and discussion}
Spectral generation is fixed by its input-output contract. Present evidence neither
establishes nor rules out formal hardness, and it is not a lower bound on all
classical algorithms. The observed growth over the tested sizes is a finite-size
statement, not a hardness no-go. This paper claims sensing-grade instrumentation
with a measured operating envelope, and it makes no hardness or advantage claim.
\end{document}
"""

# a synthetic-clean manuscript: affirmative prose, one scope clause, no defensive
# voice, no repeated boundary, no self-demotion, no negative-inventory abstract.
_CLEAN = r"""
\documentclass{article}
\begin{document}
\begin{abstract}
The method reconstructs a spectral surface from one acquisition campaign and derives
its response channels at locations chosen afterward. One validation family supplies an
exact reference across the measured operating interval.
\end{abstract}
\section{Introduction}
The method separates spectral acquisition from spectral interrogation. It applies
across every supported scale from one campaign. It makes no asymptotic-hardness claim.
\section{Limits and discussion}
The established architecture reuses one record across the supported family. The open
question is whether the planted records form a classically hard family.
\end{document}
"""


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "main.tex"
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# the four voice registers FIRE on the synthetic dirty fixture
# ---------------------------------------------------------------------------
def test_voice_registers_fire_on_dirty(tmp_path):
    p = _write(tmp_path, _DIRTY)
    findings = FL.check_voice_registers(p)
    kinds = {f["kind"] for f in findings}
    assert "referee-voice" in kinds          # "does not establish" / "neither ... nor"
    assert "audit-voice" in kinds            # "Every numerical statement ..."
    assert "disclosure-voice" in kinds       # "input-output contract"
    assert "defensive-complexity-voice" in kinds  # "growth, not hardness"
    # every finding carries the scaffold_wipe idiom
    for f in findings:
        assert set(f) >= {"where", "quote", "issue", "fix", "kind"}


def test_abstract_inventory_and_self_demotion_fire(tmp_path):
    p = _write(tmp_path, _DIRTY)
    inv = FL.check_abstract_inventory(p)
    assert len(inv) == 1 and inv[0]["kind"] == "abstract-negative-inventory"
    dem = FL.check_self_demotion(p)
    assert dem and dem[0]["kind"] == "self-demotion"
    assert "sensing-grade" in dem[0]["quote"].lower()


def test_disclaimer_treatment_keeps_once_flags_surplus(tmp_path):
    p = _write(tmp_path, _DIRTY)
    findings = FL.check_disclaimer_treatment(p)
    assert findings, "the dirty fixture repeats boundaries — surplus must flag"
    # every surplus names its class + the kept canonical location.
    for f in findings:
        assert f["kind"] == "disclaimer-surplus"
        assert f["cls"] in FL.CANONICAL_HOME


def test_final_layer_aggregate_and_census(tmp_path):
    p = _write(tmp_path, _DIRTY)
    r = FL.final_layer(p)
    assert r["pass"] is False and r["n"] > 0
    assert set(r["counts"]) == {"voice", "abstract", "demotion", "disclaimer"}
    # the census is the before/after driver — six classes, a positive total.
    by = r["census"]["by_class"]
    assert set(by) == set(FL.CANONICAL_HOME)
    assert r["census"]["total"] == sum(v["count"] for v in by.values())
    # every finding routes to a known owning stage.
    for f in r["findings"]:
        assert f["owning_stage"] in {"prose", "narrative"}


@_have_ssg
def test_runs_on_live_manuscript():
    # the organ RUNS clean-shaped on the live (now de-scaffolded) manuscript: the
    # aggregate returns the audit shape and the census is the six-class table.
    r = FL.final_layer(SSG)
    assert set(r["counts"]) == {"voice", "abstract", "demotion", "disclaimer"}
    assert set(r["census"]["by_class"]) == set(FL.CANONICAL_HOME)


# ---------------------------------------------------------------------------
# the delta: QUIET on the synthetic-clean fixture
# ---------------------------------------------------------------------------
def test_quiet_on_clean(tmp_path):
    _write(tmp_path, _CLEAN)
    r = FL.final_layer(tmp_path)
    assert r["pass"] is True, r["findings"]
    assert r["n"] == 0


def test_clean_abstract_has_no_inventory(tmp_path):
    p = _write(tmp_path, _CLEAN)
    assert FL.check_abstract_inventory(p) == []
    assert FL.check_self_demotion(p) == []


# ---------------------------------------------------------------------------
# the dial: off by default, gates the end-stage wash
# ---------------------------------------------------------------------------
def test_dial_off_by_default():
    d = D.load_dials()
    assert d["loop"]["final_layer"] == "off"
    assert D.final_layer_mode(d) == "off"


def test_dial_descaffold_reads_through():
    d = D.load_dials()
    d["loop"]["final_layer"] = "descaffold"
    assert D.final_layer_mode(d) == "descaffold"


def test_dial_unknown_key_raises():
    with pytest.raises(ValueError):
        D._overlay(D.defaults(), {"loop": {"final_layerr": "x"}})
