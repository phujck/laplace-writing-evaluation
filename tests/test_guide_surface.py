"""The guide surface's contract (W-guide, PRM-20260721-structural-guide).

The guide renders FROM the contract yamls (contract/surfaces/*.yaml) and the promise
ledger, so documentation cannot drift from what the suite enforces. These checks pin that:

  * every ROSTER surface (shared_ui._VIEWS) has a contract yaml with surface + purpose;
  * every yaml verb carries a ``does`` line (the "what will this do" answer) — NO surface
    is exempt: the W-register seam backfilled desk.yaml + pipeline.yaml from their
    executors, so the suite now enforces ``does`` everywhere;
  * guide.py renders every yaml without error;
  * the promises render includes EVERY open row of the ledger (none silently dropped).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SURFACES_DIR = REPO / "contract" / "surfaces"
#: No surface is exempt from ``does``. The desk/pipeline carve-out is retired (W-register,
#: 2026-07-22): both yamls were backfilled from their executors (desk._dispatch_desk_verb,
#: pipeline_surface.read_organ's doors), so the suite enforces ``does`` on every verb.
_DOES_EXEMPT: set[str] = set()


def _load(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict), f"{path.name}: not a yaml mapping"
    return doc


def _roster_ids() -> list[str]:
    from laplace.web import shared_ui
    return [v["id"] for v in shared_ui.views_roster().get("views", [])]


# ---------------------------------------------------------------------------
# 1. every rostered surface has a well-formed contract yaml
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sid", _roster_ids())
def test_every_roster_surface_has_a_contract_yaml(sid):
    p = SURFACES_DIR / f"{sid}.yaml"
    assert p.is_file(), f"roster surface {sid!r} has no contract/surfaces/{sid}.yaml"
    doc = _load(p)
    assert doc.get("surface"), f"{sid}.yaml: no surface name"
    assert doc.get("purpose"), f"{sid}.yaml: no purpose line"


# ---------------------------------------------------------------------------
# 2. every yaml verb carries a "does" line — no surface exempt (W-register seam)
# ---------------------------------------------------------------------------

def test_every_verb_carries_does():
    offenders = []
    for p in sorted(SURFACES_DIR.glob("*.yaml")):
        doc = _load(p)
        if doc.get("surface") in _DOES_EXEMPT:
            continue
        for v in doc.get("verbs") or []:
            name = v.get("name") or v.get("class") or "?"
            if not (v.get("does") or "").strip():
                offenders.append(f"{p.name}:{name}")
    assert not offenders, (
        "these verbs answer 'what will this do' with nothing (add a does line): "
        + ", ".join(offenders))


def test_declared_does_lines_name_a_psu_class_on_writing_verbs():
    """A verb whose does names a write should name its PSU class (local-safe / model-heavy)
    — the amended third question wants the cost stated. A read-only verb is exempt."""
    missing = []
    for p in sorted(SURFACES_DIR.glob("*.yaml")):
        doc = _load(p)
        if doc.get("surface") in _DOES_EXEMPT:
            continue
        for v in doc.get("verbs") or []:
            does = (v.get("does") or "").lower()
            if not does:
                continue
            if "psu:" in does or "local-safe" in does or "model-heavy" in does:
                continue
            missing.append(f"{p.name}:{v.get('name') or v.get('class')}")
    assert not missing, ("these verbs state no PSU class in their does: " + ", ".join(missing))


# ---------------------------------------------------------------------------
# 3. guide.py renders every yaml without error
# ---------------------------------------------------------------------------

def test_guide_renders_every_yaml_without_error():
    from laplace.web import guide
    for p in sorted(SURFACES_DIR.glob("*.yaml")):
        out = guide.render_surface_yaml(p)      # must never raise, even on desk/pipeline
        assert out["surface"], f"{p.name}: guide rendered no surface"
        assert isinstance(out["verbs"], list)
        assert isinstance(out["reads"], list)


def test_guide_full_payload_covers_the_roster_and_the_account():
    from laplace.web import guide
    fp = guide.full_payload(REPO)
    ids = {s["id"] for s in fp["surfaces"]}
    for sid in _roster_ids():
        assert sid in ids, f"the census dropped roster surface {sid!r}"
    # the structural account (a): the pipeline is present, in order, and the glossary defines
    # the load-bearing words a stranger needs.
    stages = [s["id"] for s in fp["engine"]["pipeline"]]
    for needed in ("corpus", "conceptric", "storyboard", "converge", "release"):
        assert needed in stages, f"the pipeline account omits {needed!r}"
    terms = {g["term"] for g in fp["engine"]["glossary"]}
    for needed in ("project", "generation", "debt", "work order", "the desk"):
        assert needed in terms, f"the glossary omits {needed!r}"


# ---------------------------------------------------------------------------
# 4. the promises render includes every open row (none dropped, both directions)
# ---------------------------------------------------------------------------

def test_promises_render_includes_every_open_row():
    from laplace.web import guide
    ledger = REPO / "contract" / "promises.jsonl"
    open_ids = set()
    for line in ledger.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if r.get("status") == "open":
            open_ids.add(r["id"])
    rendered = guide.promises_render(REPO)
    rendered_ids = {row["id"] for row in rendered["open"]}
    assert rendered_ids == open_ids, (
        f"the guide's promise render dropped or added rows: "
        f"missing={open_ids - rendered_ids}, extra={rendered_ids - open_ids}")
    assert rendered["counts"]["open"] == len(open_ids)
    # both directions are represented in the counts (his + eigen == open)
    assert rendered["counts"]["his"] + rendered["counts"]["eigen"] == rendered["counts"]["open"]
