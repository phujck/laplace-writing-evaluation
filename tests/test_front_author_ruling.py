from __future__ import annotations

import builtins
import copy
import hashlib
import json
from pathlib import Path

import pytest

from laplace.engine import front_author_ruling


def _document(*, schema: str = front_author_ruling.SOURCE_SCHEMA) -> dict:
    return {
        "schema_version": schema,
        "id": front_author_ruling.RULING_ID,
        "authored_at": "2026-08-28T11:50:49+01:00",
        "author": "Gerard",
        "status": "ACTIVE",
        "priority": "P0",
        "purpose": "Regularize semantic and lifecycle work without defensive ceremony.",
        "rulings": [
            "Build the semantic regularizer before another design-only increment.",
            "Aisthesis exposes currentness and omission without inventing producer truth.",
        ],
        "publication_order": [
            "semantic and lifecycle regularizer core",
            "disjoint full-carrier Aisthesis slice",
        ],
        "cadence_boundary": {
            "babysitting_required": False,
            "review_shape": "one maker, one adversary, at most one correction",
            "forbidden_regression": "do not restore unmeasured ceremony",
        },
        "outside_view_acceptance": {
            "premise": "Local kinks are inevitable and inside views miss accumulated cost.",
            "measure": "Compare visible product delta with coordination cost.",
            "success": "Checkpoint cheaply, detect divergence and fix forward.",
            "submerge_rule": "Retire layers whose unique yield does not exceed cost.",
            "observability": (
                "Show productive work, waiting, reconstruction, review, refusal, rework, "
                "unique fault catches and expected-versus-observed divergence."
            ),
        },
        "preserve": ["exact source custody", "disagreement and refusals"],
    }


def _source(tmp_path: Path, document: dict | None = None) -> tuple[Path, bytes, str]:
    raw = json.dumps(document or _document(), indent=2, ensure_ascii=False).encode("utf-8")
    path = tmp_path / "ruling.json"
    path.write_bytes(raw)
    handle = "sha256:" + hashlib.sha256(raw).hexdigest()
    return path, raw, handle


def _load(tmp_path: Path) -> front_author_ruling.ExactAuthorRuling:
    path, raw, handle = _source(tmp_path)
    return front_author_ruling.load_exact(
        path,
        expected_content_handle=handle,
        expected_byte_count=len(raw),
    )


def _publication_cut_document(
    *, schema: str = front_author_ruling.PUBLICATION_CUT_SOURCE_SCHEMA,
) -> dict:
    return {
        "schema_version": schema,
        "id": front_author_ruling.PUBLICATION_CUT_ID,
        "target_design": {
            "path": "/custody/frozen-design.md",
            "sha256": front_author_ruling.FROZEN_DESIGN_CONTENT_HANDLE.removeprefix(
                "sha256:"
            ),
            "bytes": 13_998,
            "status": "FROZEN-IMPLEMENTATION-COORDINATE",
        },
        "status": "ACTIVE-SEPARATE-AMENDMENT",
        "author": "Gerard with Superego formalization",
        "premise": "Open-ended discovery does not prevent a bounded cut from closing.",
        "current_cut_blockers": [
            "the discovery contradicts an explicit claim of the current cut",
            "the discovery falsifies acceptance evidence relied upon by the current cut",
        ],
        "successor_residuals": [
            "new capability beyond the current declared cut",
            "additional observability that does not falsify current truth",
        ],
        "closure_law": "Publish the coherent cut and carry nonblocking discoveries.",
        "design_custody_law": "Later insights are immutable amendments.",
        "epistemic_posture": "Make bounded falsifiable claims.",
        "cadence_effect": "Classify new information once at the global boundary.",
    }


def _publication_cut_source(
    tmp_path: Path,
    document: dict | None = None,
) -> tuple[Path, bytes, str]:
    raw = json.dumps(
        document or _publication_cut_document(), indent=2, ensure_ascii=False
    ).encode("utf-8")
    path = tmp_path / "publication-cut.json"
    path.write_bytes(raw)
    handle = "sha256:" + hashlib.sha256(raw).hexdigest()
    return path, raw, handle


def _load_publication_cut(tmp_path: Path) -> front_author_ruling.ExactPublicationCutLaw:
    path, raw, handle = _publication_cut_source(tmp_path)
    return front_author_ruling.load_publication_cut_law(
        path,
        expected_content_handle=handle,
        expected_byte_count=len(raw),
    )


def test_exact_loader_and_human_projection_are_read_only(tmp_path: Path, monkeypatch) -> None:
    custody = _load(tmp_path)
    assert custody.receipt() == {
        "schema_version": "laplace.author-ruling-exact-custody/1",
        "status": "EXACT",
        "source_path": str((tmp_path / "ruling.json").resolve()),
        "content_handle": custody.content_handle,
        "byte_count": custody.byte_count,
        "source_schema": front_author_ruling.SOURCE_SCHEMA,
        "ruling_id": front_author_ruling.RULING_ID,
        "read_only": True,
        "authority_effect": "none",
    }

    def forbidden_open(*_args, **_kwargs):
        raise AssertionError("the pure projection attempted filesystem access")

    monkeypatch.setattr(builtins, "open", forbidden_open)
    face = front_author_ruling.project(custody, grade="mid")
    assert face["schema_version"] == front_author_ruling.PROJECTION_SCHEMA
    assert face["status"] == "CURRENT"
    assert face["currentness"]["status"] == "CURRENT"
    assert face["human_summary"]["priority"] == "P0"
    assert face["human_summary"]["direction_count"] == 2
    assert face["source_provenance"]["custody"] == "EXACT-DIGEST-VERIFIED"
    assert face["content_handle"] == custody.content_handle
    assert face["read_only"] is True
    assert face["authority_effect"] == "none"
    assert face["exact_descent"] == {
        "status": "AVAILABLE-AT-AUDIT",
        "grade_required": "audit",
    }
    assert "sha256:" not in json.dumps(face["human_summary"])
    assert str(tmp_path) not in json.dumps(face["human_summary"])


def test_audit_is_the_only_representation_with_exact_source_descent(tmp_path: Path) -> None:
    custody = _load(tmp_path)
    for grade in ("far", "mid", "near"):
        face = front_author_ruling.project(custody, grade=grade)
        assert face["representation"]["exact_source_visible"] is False
        assert "document" not in face["exact_descent"]
        assert "source_path" not in face["exact_descent"]
        assert "content_handle" not in face["exact_descent"]

    audit = front_author_ruling.project(custody, grade="audit")
    assert audit["representation"]["exact_source_visible"] is True
    assert audit["exact_descent"]["status"] == "COMPLETE"
    assert audit["exact_descent"]["source_path"] == custody.source_path
    assert audit["exact_descent"]["content_handle"] == custody.content_handle
    assert audit["exact_descent"]["document"] == _document()


def test_outside_view_contract_is_one_honest_unknown_causal_timeline(tmp_path: Path) -> None:
    face = front_author_ruling.project(_load(tmp_path))
    timeline = face["outside_view_acceptance"]["causal_timeline"]
    assert timeline["schema_version"] == (
        "laplace.aisthesis-product-delta-causal-timeline/1"
    )
    assert timeline["status"] == "UNKNOWN"
    assert [row["kind"] for row in timeline["required_event_kinds"]] == [
        "productive-work",
        "waiting",
        "reconstruction",
        "review",
        "refusal",
        "rework",
        "unique-fault-catch",
        "expected-observed-divergence",
    ]
    assert timeline["events"] == []
    assert timeline["comparison"] == {
        "status": "UNKNOWN",
        "product_delta": None,
        "coordination_cost": None,
        "ratio": None,
        "expected": None,
        "observed": None,
    }
    assert "operational causal-timeline observation" in timeline["missing_dependency"]
    assert timeline["authority_effect"] == "none"


def test_publication_cut_keeps_compatible_discovery_as_owned_successor_residual(
    tmp_path: Path,
) -> None:
    ruling = _load(tmp_path)
    cut = _load_publication_cut(tmp_path)
    face = front_author_ruling.project(ruling, publication_cut=cut, grade="mid")
    policy = face["publication_cut_policy"]
    assert policy["schema_version"] == (
        "laplace.aisthesis-publication-cut-policy/1"
    )
    assert policy["status"] == "CURRENT"
    assert policy["human_summary"]["disposition"] == "RUNNABLE-CUT"
    assert policy["classification"] == {
        "default_for_new_compatible_insight": "OWNED-SUCCESSOR-RESIDUAL",
        "blocks_current_cut_only_on_explicit_contradiction": True,
        "design_custody_law": "Later insights are immutable amendments.",
        "epistemic_posture": "Make bounded falsifiable claims.",
    }
    assert policy["current_cut_blockers"] == (
        _publication_cut_document()["current_cut_blockers"]
    )
    assert policy["owned_successor_residuals"] == (
        _publication_cut_document()["successor_residuals"]
    )
    assert policy["exact_descent"] == {
        "status": "AVAILABLE-AT-AUDIT",
        "grade_required": "audit",
    }
    assert "sha256:" not in json.dumps(policy["human_summary"])
    assert face["source_handles"] == {
        "author_ruling": ruling.content_handle,
        "publication_cut_law": cut.content_handle,
    }

    audit = front_author_ruling.project(ruling, publication_cut=cut, grade="audit")
    descent = audit["publication_cut_policy"]["exact_descent"]
    assert descent["status"] == "COMPLETE"
    assert descent["content_handle"] == cut.content_handle
    assert descent["target_design_handle"] == (
        front_author_ruling.FROZEN_DESIGN_CONTENT_HANDLE
    )
    assert descent["document"] == _publication_cut_document()


def test_absent_publication_cut_is_unknown_not_silently_nonblocking(tmp_path: Path) -> None:
    face = front_author_ruling.project(_load(tmp_path))
    policy = face["publication_cut_policy"]
    assert policy["status"] == "UNKNOWN"
    assert policy["classification"] == {
        "default_for_new_compatible_insight": "UNKNOWN",
        "blocks_current_cut_only_on_explicit_contradiction": None,
    }
    assert policy["exact_descent"]["missing_dependency"] == (
        "exact publication-cut custody"
    )


def test_publication_cut_missing_digest_and_schema_refuse(tmp_path: Path) -> None:
    with pytest.raises(front_author_ruling.AuthorRulingRefusal) as caught:
        front_author_ruling.load_publication_cut_law(tmp_path / "missing.json")
    assert caught.value.code == "PUBLICATION_CUT_MISSING"

    path, raw, handle = _publication_cut_source(tmp_path)
    moved = bytearray(raw)
    moved[-2] = ord(" ") if moved[-2] != ord(" ") else ord("\n")
    path.write_bytes(moved)
    with pytest.raises(front_author_ruling.AuthorRulingRefusal) as caught:
        front_author_ruling.load_publication_cut_law(
            path,
            expected_content_handle=handle,
            expected_byte_count=len(raw),
        )
    assert caught.value.code == "PUBLICATION_CUT_DIGEST_REFUSED"

    bad = _publication_cut_document(schema="wrong.amendment/1")
    path, raw, handle = _publication_cut_source(tmp_path, bad)
    with pytest.raises(front_author_ruling.AuthorRulingRefusal) as caught:
        front_author_ruling.load_publication_cut_law(
            path,
            expected_content_handle=handle,
            expected_byte_count=len(raw),
        )
    assert caught.value.code == "PUBLICATION_CUT_SCHEMA_REFUSED"


def test_missing_source_refuses_loudly(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    with pytest.raises(front_author_ruling.AuthorRulingRefusal) as caught:
        front_author_ruling.load_exact(missing)
    assert caught.value.code == "AUTHOR_RULING_MISSING"
    assert caught.value.as_dict()["status"] == "REFUSED"
    assert caught.value.as_dict()["authority_effect"] == "none"


def test_size_and_digest_movement_refuse_before_projection(tmp_path: Path) -> None:
    path, raw, handle = _source(tmp_path)
    with pytest.raises(front_author_ruling.AuthorRulingRefusal) as caught:
        front_author_ruling.load_exact(
            path,
            expected_content_handle=handle,
            expected_byte_count=len(raw) + 1,
        )
    assert caught.value.code == "AUTHOR_RULING_SIZE_REFUSED"

    moved = bytearray(raw)
    moved[-2] = ord(" ") if moved[-2] != ord(" ") else ord("\n")
    path.write_bytes(moved)
    with pytest.raises(front_author_ruling.AuthorRulingRefusal) as caught:
        front_author_ruling.load_exact(
            path,
            expected_content_handle=handle,
            expected_byte_count=len(raw),
        )
    assert caught.value.code == "AUTHOR_RULING_DIGEST_REFUSED"
    assert caught.value.evidence["expected_content_handle"] == handle


def test_wrong_schema_refuses_even_when_bytes_match_declared_digest(tmp_path: Path) -> None:
    path, raw, handle = _source(tmp_path, _document(schema="wrong.schema/1"))
    with pytest.raises(front_author_ruling.AuthorRulingRefusal) as caught:
        front_author_ruling.load_exact(
            path,
            expected_content_handle=handle,
            expected_byte_count=len(raw),
        )
    assert caught.value.code == "AUTHOR_RULING_SCHEMA_REFUSED"
    assert caught.value.evidence == {
        "expected": front_author_ruling.SOURCE_SCHEMA,
        "observed": "wrong.schema/1",
    }


def test_projection_requires_exact_custody_and_a_valid_grade() -> None:
    with pytest.raises(front_author_ruling.AuthorRulingRefusal) as caught:
        front_author_ruling.project(_document())  # type: ignore[arg-type]
    assert caught.value.code == "AUTHOR_RULING_CUSTODY_REFUSED"

    raw = b"{}"
    custody = front_author_ruling.ExactAuthorRuling(
        source_path="/nonexistent",
        raw_bytes=raw,
        content_handle="sha256:" + hashlib.sha256(raw).hexdigest(),
        byte_count=len(raw),
        expected_content_handle="sha256:" + hashlib.sha256(raw).hexdigest(),
        expected_byte_count=len(raw),
    )
    with pytest.raises(front_author_ruling.AuthorRulingRefusal) as caught:
        front_author_ruling.project(custody, grade="overview")
    assert caught.value.code == "AUTHOR_RULING_GRADE_REFUSED"


def test_complete_projection_currentness_is_rederived_not_echoed(tmp_path: Path) -> None:
    custody = _load(tmp_path)
    served = front_author_ruling.project(custody, grade="near")
    current = front_author_ruling.currentness(served, custody)
    assert current["status"] == "CURRENT"
    assert current["mismatches"] == []

    forged = copy.deepcopy(served)
    forged["human_summary"]["priority"] = "P2"
    stale = front_author_ruling.currentness(forged, custody)
    assert stale["status"] == "STALE"
    assert set(stale["mismatches"]) >= {
        "served_projection_integrity",
        "projection_preimage",
    }

    forged = copy.deepcopy(served)
    forged["projection_handle"] = "sha256:" + "0" * 64
    stale = front_author_ruling.currentness(forged, custody)
    assert stale["status"] == "STALE"
    assert set(stale["mismatches"]) >= {
        "served_projection_integrity",
        "projection_handle",
    }


def test_publication_cut_is_bound_into_complete_currentness(tmp_path: Path) -> None:
    ruling = _load(tmp_path)
    cut = _load_publication_cut(tmp_path)
    served = front_author_ruling.project(ruling, publication_cut=cut)
    assert front_author_ruling.currentness(
        served, ruling, publication_cut=cut
    )["status"] == "CURRENT"

    stale = front_author_ruling.currentness(served, ruling, publication_cut=None)
    assert stale["status"] == "STALE"
    assert "projection_preimage" in stale["mismatches"]


def test_currentness_refuses_a_non_projection(tmp_path: Path) -> None:
    result = front_author_ruling.currentness({"schema_version": "wrong/1"}, _load(tmp_path))
    assert result["status"] == "REFUSED"
    assert result["mismatches"] == ["schema_version"]
    assert result["currentness_handle"].startswith("sha256:")


def test_pinned_successor_custody_constants_match_the_authorized_artifact() -> None:
    assert front_author_ruling.EXPECTED_CONTENT_HANDLE == (
        "sha256:2e268460ae1a7ecb66d45aad3e9069f1adc7e1870ea894825b32f8b8754e539a"
    )
    assert front_author_ruling.EXPECTED_BYTE_COUNT == 4_625
    assert front_author_ruling.PUBLICATION_CUT_CONTENT_HANDLE == (
        "sha256:ac569da593c4802b55fce3ccca945326e0d60561c08c9654d0aaaef328c9870a"
    )
    assert front_author_ruling.PUBLICATION_CUT_BYTE_COUNT == 2_413
    assert front_author_ruling.FROZEN_DESIGN_CONTENT_HANDLE == (
        "sha256:defd086c388e347c7ecfc081f8fa714d26cc11ad56e03c1f461a11634cec8f7f"
    )
