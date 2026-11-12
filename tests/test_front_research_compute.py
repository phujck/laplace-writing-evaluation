from __future__ import annotations

from laplace.engine import front_research_compute


def _query_evidence() -> dict:
    return {
        "status": "COMPLETE",
        "query": "How does typed residue change campaign convergence?",
        "planner": {
            "goal": "find exact convergence evidence",
            "assumption": "structural",
            "fibre": "evidence",
            "grade": 2,
            "budget": 32768,
            "beam": 8,
        },
        "routing": {
            "status": "COMPLETE",
            "count": 18,
            "latency_ms": 14,
            "reason": "18 candidates ranked by the declared operator",
        },
        "descent": {
            "status": "COMPLETE",
            "count": 6,
            "latency_ms": 91,
            "reason": "six source-bearing leaves materialised",
        },
        "evidence": {
            "status": "COMPLETE",
            "count": 4,
            "reason": "four typed witnesses admitted",
        },
        "regions": [
            {
                "id": "genesis-ledger",
                "label": "Genesis revision ledger",
                "class": "ACCEPTED",
                "status": "COMPLETE",
                "source_class": "synthetics",
                "count": 20,
                "depth": 3,
                "bytes": 11240,
                "continuation": "atlas://object/genesis-ledger",
            },
            {
                "id": "superseded-prompts",
                "label": "Superseded prompt generations",
                "class": "REJECTED",
                "status": "COMPLETE",
                "source_class": "synthetics",
                "count": 4,
                "reason": "withdrawn by later exact generations",
                "continuation": "atlas://object/superseded-prompts",
            },
            {
                "id": "external-literature",
                "label": "Non-local literature candidates",
                "class": "UNVISITED",
                "status": "UNKNOWN",
                "source_class": "external-research",
                "count": 12,
                "reason": "the non-local query was not fired",
                "continuation": "research://literature/query",
            },
        ],
        "fog": [
            {
                "id": "held-out-closure",
                "label": "Held-out goal closure",
                "cause": "COVERAGE",
                "count": 2,
                "members": ["goal:held-out:1", "goal:held-out:2"],
                "continuation": "atlas://query/held-out",
            },
            {
                "id": "budget-edge",
                "label": "Budget edge",
                "cause": "BUDGET_TRUNCATION",
                "count": 7,
                "continuation": "atlas://query/continue?offset=32768",
            },
        ],
        "continuation": "atlas://query/descent",
    }


def _campaigns() -> list[dict]:
    return [
        {
            "id": "superarc",
            "label": "SuperARC campaign",
            "status": "COMPLETE",
            "question_count": 100,
            "budget": {"rounds": 400},
            "arms": [
                {"id": "bare", "label": "Bare model"},
                {"id": "eigen", "label": "Eigen recursive"},
            ],
            "continuation": "campaign://superarc",
        },
        {
            "id": "rehearsal",
            "label": "Self-corpus rehearsal",
            "status": "IN_FLIGHT",
            "question_count": 12,
            "arms": ["bare", "eigen"],
            "continuation": "campaign://rehearsal",
        },
    ]


def _runs() -> list[dict]:
    return [
        {
            "id": "superarc-bare",
            "campaign_id": "superarc",
            "arm_id": "bare",
            "status": "COMPLETE",
            "phase": "SEALED",
            "manifest_state": "VERIFIED",
            "metrics": {"score": 0.41, "cost_gbp": 18.2, "latency_s": 211.0},
            "continuation": "campaign://run/superarc-bare",
        },
        {
            "id": "superarc-eigen",
            "campaign_id": "superarc",
            "arm_id": "eigen",
            "status": "COMPLETE",
            "phase": "SEALED",
            "manifest_state": "VERIFIED",
            "metrics": {"score": 0.73, "cost_gbp": 24.6, "latency_s": 382.0},
            "continuation": "campaign://run/superarc-eigen",
        },
        {
            "id": "rehearsal-bare",
            "campaign_id": "rehearsal",
            "arm_id": "bare",
            "status": "IN_FLIGHT",
            "phase": "METERED",
            "metrics": {"cost_gbp": 2.4, "latency_s": 34.0},
            "continuation": "campaign://run/rehearsal-bare",
        },
    ]


def _results() -> list[dict]:
    return [
        {
            "id": "bare",
            "label": "Bare model",
            "status": "COMPLETE",
            "metrics": {"score": 0.41, "cost_gbp": 18.2, "latency_s": 211.0},
            "provenance": {"run_id": "superarc-bare", "manifest": "verified"},
            "continuation": "campaign://result/bare",
        },
        {
            "id": "eigen",
            "label": "Eigen recursive",
            "status": "COMPLETE",
            "metrics": {"score": 0.73, "cost_gbp": 24.6, "latency_s": 382.0},
            "provenance": {"run_id": "superarc-eigen", "manifest": "verified"},
            "continuation": "campaign://result/eigen",
        },
    ]


def _model() -> dict:
    return front_research_compute.project(
        query="How does typed residue change campaign convergence?",
        query_evidence=_query_evidence(),
        campaigns=_campaigns(),
        runs=_runs(),
        result_sets=_results(),
        source_currentness={
            "status": "CURRENT",
            "reason": "all supplied evidence is pinned to the same source tuple",
            "source": {"commit": "source-S", "tree": "tree-S"},
            "observation_time": "2026-08-28T13:00:00Z",
        },
    )


def test_absent_producers_are_unknown_omissions_not_empty_success() -> None:
    model = front_research_compute.project()

    assert model["schema_version"] == "laplace.aisthesis-research-compute/1"
    assert model["state"] == "UNKNOWN"
    assert model["currentness"]["status"] == "UNKNOWN"
    assert model["query_path"]["regions"] == []
    assert model["experiment_matrix"]["rows"] == []
    assert model["result_comparison"]["entries"] == []
    assert {row["id"] for row in model["omissions"]} >= {
        "query-absent",
        "regions-unavailable",
        "campaigns-unavailable",
        "results-unavailable",
    }
    assert all(row["continuation"] for row in model["omissions"])
    assert model["read_only"] is True
    assert model["authority_effect"] == "none"
    assert model["second_truth_store"] is False


def test_complete_join_preserves_query_reach_matrix_altitude_and_comparison() -> None:
    model = _model()

    assert model["state"] == "COMPLETE"
    query = model["query_path"]
    assert query["declared_parameters"] == {
        "goal": "find exact convergence evidence",
        "assumption": "structural",
        "fibre": "evidence",
        "grade": 2,
        "budget": 32768,
        "beam": 8,
    }
    assert [row["class"] for row in query["regions"]] == [
        "ACCEPTED",
        "REJECTED",
        "UNVISITED",
    ]
    assert query["fog"][1]["cause"] == "BUDGET_TRUNCATION"
    assert query["fog"][1]["continuation"].endswith("offset=32768")

    matrix = model["experiment_matrix"]
    assert [column["id"] for column in matrix["columns"]] == ["bare", "eigen"]
    superarc = matrix["rows"][0]
    assert [cell["phase"] for cell in superarc["cells"]] == ["SEALED", "SEALED"]
    rehearsal = matrix["rows"][1]
    missing = next(cell for cell in rehearsal["cells"] if cell["arm_id"] == "eigen")
    assert missing["state"] == "UNKNOWN"
    assert missing["metrics"] == {}
    assert matrix["runs"][2]["phase"] == "METERED"

    comparison = model["result_comparison"]
    assert [axis["id"] for axis in comparison["axes"]] == [
        "cost_gbp",
        "latency_s",
        "score",
    ]
    assert comparison["entries"][1]["metrics"]["score"] == 0.73
    assert comparison["entries"][1]["provenance"]["manifest"] == "verified"


def test_query_parameters_are_only_the_planner_declared_contract() -> None:
    evidence = _query_evidence()
    evidence["planner"]["invented_ui_knob"] = "must not leak"
    evidence["planner"]["search"] = {"operator": "raw-cosine-router/1"}

    model = front_research_compute.project(query_evidence=evidence)

    assert "invented_ui_knob" not in model["query_path"]["declared_parameters"]
    assert model["query_path"]["declared_parameters"]["search"] == {
        "operator": "raw-cosine-router/1"
    }


def test_untyped_fog_and_unknown_run_phase_refuse_instead_of_becoming_visual_haze() -> None:
    evidence = _query_evidence()
    evidence["fog"][0]["cause"] = "MYSTERY"
    bad_runs = _runs()
    bad_runs[0]["phase"] = "MAGIC"

    model = front_research_compute.project(
        query="question",
        query_evidence=evidence,
        campaigns=_campaigns(),
        runs=bad_runs,
        result_sets=_results(),
        source_currentness={"status": "CURRENT"},
    )

    assert model["state"] == "REFUSED"
    assert model["query_path"]["state"] == "REFUSED"
    assert "unsupported typed cause" in model["query_path"]["reason"]
    assert model["experiment_matrix"]["state"] == "REFUSED"
    assert "unsupported phase" in model["experiment_matrix"]["reason"]


def test_result_comparison_never_invents_metrics_or_coerces_labels_to_numbers() -> None:
    results = _results()
    results[0]["metrics"].update({"confidence": "unknown", "passed": True})
    results[1]["metrics"].update({"confidence": "unknown", "passed": False})

    model = front_research_compute.project(result_sets=results)

    assert [axis["id"] for axis in model["result_comparison"]["axes"]] == [
        "cost_gbp",
        "latency_s",
        "score",
    ]
    assert "confidence" not in model["result_comparison"]["entries"][0]["metrics"]
    assert "passed" not in model["result_comparison"]["entries"][0]["metrics"]


def test_currentness_stale_and_refused_remain_noncurrent_even_with_complete_evidence() -> None:
    stale = _model()
    stale = front_research_compute.project(
        query=stale["query_path"]["query"],
        query_evidence=_query_evidence(),
        campaigns=_campaigns(),
        runs=_runs(),
        result_sets=_results(),
        source_currentness={"status": "STALE", "reason": "source tuple moved"},
    )
    refused = front_research_compute.project(source_currentness={"status": "CURRENTISH"})

    assert stale["state"] == "UNKNOWN"
    assert stale["currentness"]["status"] == "STALE"
    assert refused["state"] == "REFUSED"
    assert refused["currentness"]["status"] == "REFUSED"


def test_duplicate_campaign_or_run_cell_refuses_exactly() -> None:
    campaigns = _campaigns() + [_campaigns()[0]]
    runs = _runs() + [_runs()[0]]

    model = front_research_compute.project(campaigns=campaigns, runs=runs)

    assert model["experiment_matrix"]["state"] == "REFUSED"
    assert "multiple runs claim" in model["experiment_matrix"]["reason"]


def test_semantic_anchors_are_unique_and_model_handle_is_order_stable() -> None:
    left = _model()
    evidence = _query_evidence()
    evidence["planner"] = dict(reversed(list(evidence["planner"].items())))
    right = front_research_compute.project(
        query="How does typed residue change campaign convergence?",
        query_evidence=evidence,
        campaigns=[dict(reversed(list(row.items()))) for row in _campaigns()],
        runs=[dict(reversed(list(row.items()))) for row in _runs()],
        result_sets=[dict(reversed(list(row.items()))) for row in _results()],
        source_currentness={
            "observation_time": "2026-08-28T13:00:00Z",
            "source": {"tree": "tree-S", "commit": "source-S"},
            "reason": "all supplied evidence is pinned to the same source tuple",
            "status": "CURRENT",
        },
    )

    assert left["model_handle"] == right["model_handle"]
    assert len(left["ordered_visible_handles"]) == len(set(left["ordered_visible_handles"]))
    assert left["omitted_digest"] == right["omitted_digest"]
