from __future__ import annotations

from pathlib import Path

from laplace.engine import front_talk


def _beat(ident: str = "compression") -> dict:
    return {
        "id": ident,
        "title": "Learning is compression",
        "motivation": "One idea should carry the architecture.",
        "claim": "A short model predicts the long description.",
        "origin": "blueprint.md:core_idea",
        "visual": "One compression lineage",
        "citations": ["mehta2014exact"],
    }


def _complete_posture(label: str) -> dict:
    return {"state": "COMPLETE", "reason": f"{label} receipt is exact"}


def test_absent_producers_are_typed_unknown_not_empty_success() -> None:
    model = front_talk.project(title="An unfinished talk")

    assert model["schema_version"] == "laplace.aisthesis-talk-work/1"
    assert model["state"] == "UNKNOWN"
    assert model["omissions"]
    assert all(row["continuation"] for row in model["omissions"])
    assert model["projection_law"]["direct_slide_truth"] is False
    assert model["read_only"] is True
    assert model["authority_effect"] == "none"


def test_complete_pipeline_preserves_primitives_spine_and_rendered_ledger() -> None:
    model = front_talk.project(
        title="Eigen explains itself",
        primitives={
            "source": "The engine canon",
            "audience": "A theoretical physicist",
            "message": "Compression is learning",
        },
        motivated_spine=[_beat()],
        generation={
            **_complete_posture("generation"),
            "generated_from_spine": True,
            "direct_slide_truth": False,
        },
        ledger={
            **_complete_posture("ledger"),
            "voice": "PASS",
            "applets": "PASS",
            "render": "PASS",
        },
        rehearsal={**_complete_posture("rehearsal"), "duration_minutes": 42},
        export={**_complete_posture("export"), "pdf_present": True, "listed": True},
    )

    assert model["state"] == "COMPLETE"
    assert [row["id"] for row in model["primitives"]] == ["source", "audience", "message"]
    assert model["spine"]["beats"][0]["motivation"]
    assert model["spine"]["beats"][0]["origin"] == "blueprint.md:core_idea"
    assert {row["id"] for row in model["postures"]} == {
        "generation",
        "ledger",
        "rehearsal",
        "export",
    }
    assert model["omissions"] == []


def test_direct_slide_truth_refuses_even_when_generation_claims_complete() -> None:
    model = front_talk.project(
        primitives={"source": "S", "audience": "A", "message": "M"},
        motivated_spine=[_beat()],
        generation={"state": "COMPLETE", "direct_slide_truth": True},
    )

    generation = next(row for row in model["postures"] if row["id"] == "generation")
    assert model["state"] == "REFUSED"
    assert generation["state"] == "REFUSED"
    assert "governed beat regeneration" in generation["reason"]


def test_incomplete_beat_keeps_motivation_gap_visible() -> None:
    row = _beat()
    row.pop("motivation")
    model = front_talk.project(motivated_spine=[row])

    assert model["spine"]["state"] == "UNKNOWN"
    assert model["spine"]["beats"][0]["state"] == "UNKNOWN"
    assert any(item["id"] == "motivated-spine" for item in model["omissions"])


def test_semantic_anchors_and_model_handle_are_stable() -> None:
    left = front_talk.project(
        title="Talk",
        primitives={"source": "S", "audience": "A", "message": "M"},
        motivated_spine=[_beat("one"), _beat("two")],
    )
    right = front_talk.project(
        title="Talk",
        primitives={"message": "M", "audience": "A", "source": "S"},
        motivated_spine=[_beat("one"), _beat("two")],
    )

    anchors = [row["semantic_anchor"] for row in left["primitives"]]
    anchors += [row["semantic_anchor"] for row in left["spine"]["beats"]]
    anchors += [row["semantic_anchor"] for row in left["postures"]]
    assert len(anchors) == len(set(anchors))
    assert left["model_handle"] == right["model_handle"]


def test_read_reconstructs_blueprint_and_refuses_to_promote_hand_edited_slides(
    tmp_path: Path,
) -> None:
    project = tmp_path / "talk"
    project.mkdir()
    (project / "blueprint.md").write_text(
        """- title: A source-bearing talk
- thesis: One message carries the talk.
- audience: Curious physicists.

NOTE (provenance): The exact engine canon.

## first | The first beat | ring:core
intent: Explain why the first move is necessary.
- claim: The first claim lands. | result:R1
- figure: fig:first | The visual that lands it.
- cite: exact2026 | relation:supports
""",
        encoding="utf-8",
    )
    (project / "slides.md").write_text("---\ntitle: A hand-built deck\n---\n", encoding="utf-8")

    model = front_talk.read(project_dir=project)
    generation = next(row for row in model["postures"] if row["id"] == "generation")

    assert model["title"] == "A source-bearing talk"
    assert model["spine"]["beats"][0]["semantic_anchor"] == "talk:beat:first"
    assert model["spine"]["beats"][0]["state"] == "COMPLETE"
    assert generation["state"] == "UNKNOWN"
    assert generation["evidence"]["deck_present"] is True
    assert generation["evidence"]["generated_from_spine"] is False


def test_read_marks_generated_header_without_claiming_missing_ledger(tmp_path: Path) -> None:
    project = tmp_path / "talk"
    project.mkdir()
    (project / "blueprint.md").write_text(
        """- title: Talk
- thesis: The message.
- audience: The room.
NOTE (provenance): The source.
## beat | Beat | ring:core
intent: Motivate it.
- claim: Land it. | result:R
""",
        encoding="utf-8",
    )
    (project / "slides.md").write_text(
        "<!-- GENERATED FROM THE MOTIVATED SPINE -->\n---\n", encoding="utf-8"
    )

    model = front_talk.read(project_dir=project)
    postures = {row["id"]: row for row in model["postures"]}

    assert postures["generation"]["state"] == "COMPLETE"
    assert postures["ledger"]["state"] == "UNKNOWN"
    assert postures["rehearsal"]["state"] == "UNKNOWN"
    assert postures["export"]["state"] == "UNKNOWN"
