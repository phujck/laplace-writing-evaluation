"""The author-architecture profile is well-formed, evidence-bearing, and clean.

profiles/author_architecture.yaml (W-ARCH) is the whole-paper structural grain
derived from the banked stage stores — a reconstruction he confirms, not a mint.
This guards the contract the narrative planners and gen-4's judgement movement
read against: the yaml parses, the required fields are present, every profile
field cites its evidence, the status stays RECONSTRUCTED (production never
self-certifies the profile as accepted), and the register sweep finds no tic on
it (the profile is a rule-adjacent surface the absolute-zero law scans).
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
PROFILE = REPO / "profiles" / "author_architecture.yaml"


def _load() -> dict:
    return yaml.safe_load(PROFILE.read_text(encoding="utf-8"))


def test_profile_exists_and_parses():
    assert PROFILE.is_file(), f"{PROFILE} is missing"
    doc = _load()
    assert isinstance(doc, dict), "the profile did not parse to a mapping"


def test_required_top_level_fields():
    doc = _load()
    for key in ("schema", "status", "derived_from", "consumes", "profile"):
        assert doc.get(key), f"required top-level field missing/empty: {key}"
    assert isinstance(doc["derived_from"], list) and doc["derived_from"], \
        "derived_from must be a non-empty list of sources"
    assert isinstance(doc["profile"], dict) and doc["profile"], \
        "profile must be a non-empty mapping of fields"


def test_status_is_reconstructed():
    doc = _load()
    assert "RECONSTRUCTED" in str(doc["status"]), \
        f"status must say RECONSTRUCTED (awaiting his confirmation); got {doc['status']!r}"


def test_every_profile_field_carries_evidence():
    doc = _load()
    for name, field in doc["profile"].items():
        assert isinstance(field, dict), f"{name}: field is not a mapping"
        ev = field.get("evidence")
        assert ev, f"{name}: no evidence block — a claim without evidence rots"
        assert ev.get("sources"), f"{name}: evidence names no sources"
        assert ev.get("observation"), f"{name}: evidence carries no observation"


def test_consumer_is_named():
    doc = _load()
    blob = yaml.safe_dump(doc["consumes"])
    assert "narrative planners" in blob, \
        "the intended consumer (the narrative planners) must be named in `consumes`"


def test_confirmation_ask_names_its_door():
    doc = _load()
    conf = doc.get("confirmation") or {}
    assert conf.get("banked_ask"), "the banked confirmation ask must name its store"
    assert "work_orders.jsonl" in str(conf["banked_ask"]), \
        "the confirmation ask is banked as a work-order (the real, desk-visible door)"


def test_register_sweep_is_clean_on_the_profile():
    """The absolute-zero register law (scripts/audit_register.py) must find no tic
    on this profile — the same sweep that gates every profiles/**/*.yaml surface."""
    sys.path.insert(0, str(REPO / "scripts"))
    import audit_register  # noqa: E402

    rel = str(PROFILE.relative_to(REPO))
    text = audit_register._whole_text(PROFILE)
    surface = audit_register._surface_class(rel, "text")
    total, by_kind = audit_register._score(text, surface)
    assert total == 0, f"register breach on {rel}: {by_kind}"
