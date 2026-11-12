from __future__ import annotations

from laplace.engine import front_author_ruling
from laplace.web import front_door


def test_missing_semantic_producers_remain_distinct_unknown_faces() -> None:
    face = front_door._carrier_semantic_junction()
    assert face["status"] == "UNKNOWN"
    assert [row["status"] for row in face["lineages"]] == ["UNKNOWN", "UNKNOWN"]
    assert face["compact_fold"]["status"] == "UNKNOWN"
    assert face["down_reconstruction"]["status"] == "UNKNOWN"
    assert face["register_dictionary"]["status"] == "UNKNOWN"
    assert face["producer_boundary"] == {
        "read_only": True,
        "second_truth_store": False,
        "producer_absence": "UNKNOWN",
        "authority_effect": "none",
    }


def test_carrier_uses_one_live_health_observation_for_fold_and_memory(
    monkeypatch,
) -> None:
    health = {"schema_version": "laplace.embedding-health/1", "status": "CURRENT"}
    captured = {}

    monkeypatch.setattr(front_door, "_carrier_embedding_health", lambda: health)
    monkeypatch.setattr(front_door, "_carrier_development", lambda _query: {})
    monkeypatch.setattr(front_door, "_carrier_fabric_faces", lambda: ({}, {}))
    monkeypatch.setattr(front_door, "_carrier_author_ruling", lambda _grade: {})

    from laplace.engine import front_carrier, front_semantic_junction

    monkeypatch.setattr(
        front_semantic_junction,
        "project_semantic_junction",
        lambda **kwargs: captured.setdefault("junction", kwargs) or {},
    )
    monkeypatch.setattr(
        front_carrier,
        "project",
        lambda **kwargs: captured.setdefault("carrier", kwargs) or {},
    )

    front_door._carrier_projection({})

    assert captured["carrier"]["embedding_health"] is health
    assert captured["junction"]["compact_fold"] is health


def test_moved_author_ruling_preserves_refusal_and_independent_current_cut(
    monkeypatch,
) -> None:
    cut = object()
    policy = {
        "schema_version": front_author_ruling.PUBLICATION_CUT_POLICY_SCHEMA,
        "status": "CURRENT",
        "human_summary": {"disposition": "RUNNABLE-CUT"},
        "policy_handle": "sha256:" + "1" * 64,
    }

    monkeypatch.setattr(front_author_ruling, "load_publication_cut_law", lambda: cut)
    monkeypatch.setattr(
        front_author_ruling,
        "_publication_cut_policy",
        lambda supplied, *, grade: policy if supplied is cut and grade == "mid" else None,
    )

    def moved():
        raise front_author_ruling.AuthorRulingRefusal(
            "AUTHOR_RULING_SIZE_REFUSED",
            "the durable author-ruling byte count moved",
            expected_byte_count=4_625,
            observed_byte_count=4_982,
        )

    monkeypatch.setattr(front_author_ruling, "load_exact", moved)
    face = front_door._carrier_author_ruling("mid")
    assert face["status"] == "REFUSED"
    assert face["currentness"]["refusal_code"] == "AUTHOR_RULING_SIZE_REFUSED"
    assert face["publication_cut_policy"] == policy
    assert face["exact_descent"]["visibility"] == "AUDIT_ONLY"
    assert face["exact_descent"]["author_ruling_refusal"]["status"] == "REFUSED"
    assert face["read_only"] is True
    assert face["authority_effect"] == "none"
