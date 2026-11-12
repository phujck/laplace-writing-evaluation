"""Leg C bite C1 — small organ fixes: the readers package shadow (item 4), the
figure-standard font pipeline (item 5), and the genericity sweep (item 7).
"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[1]


# --- item 4: readers/__init__ no longer shadows the roster SUBMODULE ----------

def test_readers_roster_submodule_is_not_shadowed():
    import laplace.pipeline.readers.roster as mod
    # the dotted path resolves to the MODULE (was the function under the shadow)
    assert inspect.ismodule(mod)
    for name in ("verify_single_ownership", "roster", "READERS", "reader_finding"):
        assert hasattr(mod, name), f"submodule missing {name!r}"
    # the package attribute agrees, and `import ... as x` binds the module
    from laplace.pipeline.readers import roster as attr
    assert attr is mod


def test_readers_package_reexports_intact():
    from laplace.pipeline.readers import (  # noqa: F401
        READERS, finding_kinds_manifest, dimension_manifest,
        reader_verdict_score, verify_single_ownership, verify_kind_partition,
        write_verdict, read_verdict, assemble_sidecar,
    )
    assert callable(finding_kinds_manifest)


# --- item 5: the figure-standard organ embeds Type-42 fonts + larger labels ---

def _load_figstyle():
    spec = importlib.util.spec_from_file_location(
        "figstyle_probe",
        REPO / "synthetics papers" / "subset-sum-itqde" / "manuscript"
        / "figures" / "figstyle.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_figstyle_embeds_type42_fonts():
    import matplotlib
    fs = _load_figstyle()
    fs.use_house_style()
    assert matplotlib.rcParams["pdf.fonttype"] == 42
    assert matplotlib.rcParams["ps.fonttype"] == 42


def test_figstyle_labels_bumped_off_the_floor():
    import matplotlib
    fs = _load_figstyle()
    fs.use_house_style()
    # axis labels lead; every tick/legend label sits above the 6pt floor
    assert matplotlib.rcParams["axes.labelsize"] >= 10
    assert matplotlib.rcParams["xtick.labelsize"] >= 8
    assert matplotlib.rcParams["ytick.labelsize"] >= 8


# --- item 7: migrate_essences no longer silently pins subset-sum-itqde --------

def test_migrate_essences_project_is_explicit_required():
    from laplace.pipeline import migrate_essences as ME
    for fn in (ME.audit, ME.migrate_plan_meta):
        p = inspect.signature(fn).parameters["project"]
        assert p.default is inspect.Parameter.empty, (
            f"{fn.__name__}: 'project' must be explicit-required, not a hard-coded pin")
