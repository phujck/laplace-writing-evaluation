from __future__ import annotations

from pathlib import Path

from laplace.web import front_work


def _cap(model: dict, family: str, ident: str) -> dict:
    organ = next(o for o in model["organs"] if o["id"] == family)
    return next(c for c in organ["capabilities"] if c["id"] == ident)


def _walk_doc(*, missing_src: bool = False) -> dict:
    blocks = [
        {
            "id": "one.tex#b1",
            "kind": "paragraph",
            "text": "A source-addressed paragraph.",
            "src": {"file": "sections/one.tex", "line_start": 4, "line_end": 8},
        },
        {
            "id": "one.tex#b2",
            "kind": "figure",
            "caption": "A promised figure.",
            "src": {"file": "sections/one.tex", "line_start": 12, "line_end": 18},
        },
    ]
    if missing_src:
        blocks[1].pop("src")
    return {
        "ok": True,
        "title": "An exact paper",
        "fidelity": "content-faithful; geometry is the PDF face",
        "counts": {"sections": 1, "blocks": 2},
        "sections": [{"id": "one", "title": "One", "blocks": blocks}],
    }


def _pipeline_chain() -> dict:
    return {
        "project": "paper",
        "current_state": "UNDER_CONVERGENCE",
        "never_run": False,
        "ladder_banner": "The release chain is under convergence.",
        "states": [
            {"state": "STAGED", "status": "passed", "index": 0, "next_action": "inspect"},
            {
                "state": "UNDER_CONVERGENCE",
                "status": "current",
                "index": 3,
                "next_action": "run one bounded round",
            },
        ],
        "organs": [
            {
                "id": "staged",
                "dials": [],
                "controls": [
                    {
                        "action": "storyboard-rebuild",
                        "cost_class": "local-safe",
                        "arm_to_fire": True,
                        "what": "rebuild the staged spine",
                    },
                    {
                        "action": "re-projection",
                        "cost_class": "model-heavy",
                        "banks": "work-order",
                        "arm_to_fire": True,
                        "what": "reproject the manuscript",
                    },
                ],
                "sub_organs": [
                    {
                        "id": "selection",
                        "label": "selection",
                        "producer": "selection_sheet.read_selection",
                        "reader_door": "/pipeline/organ?project=paper&organ=selection",
                        "summary": {"present": True, "generations_n": 3, "awaiting_ruling_n": 1},
                    },
                    {
                        "id": "derivation",
                        "label": "derivation",
                        "producer": "derivation_organ.reach",
                        "reader_door": "/pipeline/organ?project=paper&organ=derivation",
                        "summary": {"present": False, "frontier_n": 2},
                    },
                    {
                        "id": "evolution",
                        "label": "evolution",
                        "producer": "evolution_consumer.read_ratify_queue",
                        "reader_door": "/pipeline/organ?project=paper&organ=evolution",
                        "summary": {"present": True, "open": 2, "held": 1},
                    },
                ],
            }
        ],
        "global": {
            "id": "global",
            "controls": [],
            "dials": [
                {
                    "path": "loop.max_rounds",
                    "value": 4,
                    "source": "overlay",
                    "consumer": "converge",
                }
            ],
        },
        "joins": {
            "run_tray": "/storyboard/run",
            "dry_run": "/storyboard/propagate",
            "dials_write": "/dials/op + /dials/undo",
        },
    }


def _walk_evidence() -> dict:
    return {
        "review": {"findings": 2, "parked": 1},
        "feedback": {"open": 2, "resolved": 4},
        "pdf": {"present": True, "pages": 12, "synctex": True},
        "versions": {"count": 5, "latest": "v5"},
        "compile": {"state": "clean"},
        "redline": {"before": "v4", "after": "v5"},
    }


def _action_evidence() -> dict:
    return {
        **_walk_evidence(),
        "editor": {
            "file": "paper/main.tex",
            "content": "\\section{One}\nA banked source paragraph.\n",
            "surface": "front-work",
            "expected_selection": "sha256:" + "e" * 64,
            "expected_source_digest": "sha256:" + "a" * 64,
            "selection_identity": "sha256:" + "e" * 64,
        },
        "versions": {
            "count": 3,
            "states": [
                {
                    "id": "git-base",
                    "label": "Committed baseline",
                    "kind": "git",
                    "created_at": "2026-08-28T09:00:00Z",
                },
                {
                    "version_id": "editor-v1",
                    "source_file": "paper/main.tex",
                    "label": "Clarify the opening",
                    "schema_version": "laplace.editor-save/1",
                    "author": "gerard",
                    "created_at": "2026-08-28T10:00:00Z",
                },
                {
                    "version_id": "editor-v2",
                    "source_file": "paper/main.tex",
                    "label": "Add the exact mechanism",
                    "kind": "editor-save",
                    "author": "gerard",
                    "created_at": "2026-08-28T11:00:00Z",
                },
            ],
        },
    }


def test_unknown_inputs_are_visible_omissions_not_empty_success() -> None:
    model = front_work.project(project_name="paper", corpus="paper")

    assert model["schema_version"] == "laplace.aisthesis-work-room/1"
    assert model["state"] == "UNKNOWN"
    assert [o["state"] for o in model["organs"]] == ["UNKNOWN", "UNKNOWN"]
    assert model["omissions"]
    assert all(o["continuation"] for o in model["omissions"])
    assert model["read_only"] is True
    assert model["authority_effect"] == "none"
    assert model["parity"]["second_truth_store"] is False
    assert model["parity"]["old_shells_embedded"] is False


def test_joined_walk_and_pipeline_preserve_the_historical_mechanisms() -> None:
    model = front_work.project(
        project_name="paper",
        corpus="paper",
        walk_document=_walk_doc(),
        walk_evidence=_walk_evidence(),
        pipeline_chain=_pipeline_chain(),
        pipeline_brief={"project": "paper", "sentence": "One composed project brief."},
        pipeline_verdict={"position": "UNDER_CONVERGENCE", "owed_to_author": []},
        pipeline_organs={
            "selection": {"present": True, "generations": 3},
            "derivation": {"present": True, "links_attested": 4, "links_total": 6},
            "evolution": {"present": True, "open": 2},
        },
        observation_time="2026-08-28T12:00:00Z",
        source_currentness={"state": "CURRENT"},
    )

    assert model["state"] == "COMPLETE"
    assert _cap(model, "walk", "content-canvas")["evidence"]["counts"]["blocks"] == 2
    assert _cap(model, "walk", "source-provenance")["evidence"] == {
        "blocks": 2,
        "source_addressed": 2,
        "missing_source_spans": 0,
    }
    assert _cap(model, "walk", "rewrite-and-scope")["disposition"] == "TRANSFORM"
    assert "exact safe TeX splice" in _cap(model, "walk", "rewrite-and-scope")["preserves"]
    assert "PDF to source" in _cap(model, "walk", "pdf-and-synctex")["preserves"]
    assert "restore without rewind" in _cap(model, "walk", "version-compile-restore")["preserves"]

    release = _cap(model, "pipeline", "release-chain")
    assert release["evidence"]["current_state"] == "UNDER_CONVERGENCE"
    assert release["evidence"]["states"][1]["next_action"] == "run one bounded round"
    assert _cap(model, "pipeline", "selection")["state"] == "COMPLETE"
    assert _cap(model, "pipeline", "derivation")["state"] == "COMPLETE"
    assert _cap(model, "pipeline", "evolution")["state"] == "COMPLETE"


def test_workbench_carries_real_manuscript_spine_and_release_journey() -> None:
    model = front_work.project(
        project_name="paper",
        corpus="paper",
        walk_document=_walk_doc(),
        walk_evidence=_walk_evidence(),
        pipeline_chain=_pipeline_chain(),
        pipeline_brief={
            "project": "paper",
            "position": "UNDER_CONVERGENCE",
            "brief": {
                "glance": "The manuscript is converging.",
                "next_line": "Next: run one bounded round.",
            },
        },
        pipeline_verdict={"position": "UNDER_CONVERGENCE", "owed_to_author": []},
    )

    workbench = model["workbench"]
    assert workbench["schema_version"] == "laplace.aisthesis-manuscript-workbench/1"
    manuscript = workbench["manuscript"]
    assert manuscript["sections"][0]["semantic_anchor"] == "work:manuscript:section:one"
    assert manuscript["sections"][0]["source"] == {
        "file": "",
        "line_start": 4,
        "line_end": 18,
    }
    assert manuscript["sections"][0]["blocks"][0]["words"] == "A source-addressed paragraph."
    assert manuscript["sections"][0]["blocks"][0]["semantic_anchor"] == (
        "work:manuscript:block:one.tex#b1"
    )
    assert {row["id"] for row in manuscript["postures"]} == {
        "source", "pdf", "review", "versions", "compile", "redline", "feedback"
    }

    pipeline = workbench["pipeline"]
    assert pipeline["position"] == "UNDER_CONVERGENCE"
    assert [row["status"] for row in pipeline["release_states"]] == ["PASSED", "CURRENT"]
    assert pipeline["release_states"][1]["next_action"] == "run one bounded round"
    assert any(row["id"] == "selection" for row in pipeline["mechanisms"])
    assert pipeline["read_only"] is True
    assert pipeline["authority_effect"] == "none"


def test_workbench_preserves_unknown_postures_and_exact_continuations() -> None:
    model = front_work.project(project_name="paper", corpus="paper", walk_document=_walk_doc())
    manuscript = model["workbench"]["manuscript"]
    postures = {row["id"]: row for row in manuscript["postures"]}

    assert postures["source"]["state"] == "COMPLETE"
    assert postures["source"]["continuation"] == "/walk/doc?corpus=paper"
    assert postures["pdf"]["state"] == "UNKNOWN"
    assert postures["pdf"]["continuation"] == "/projection/pdfinfo"
    assert postures["feedback"]["state"] == "UNKNOWN"
    assert postures["feedback"]["continuation"] == "/projection/feedback"
    assert model["workbench"]["read_only"] is True


def test_write_doors_are_described_but_never_executed_by_the_projection() -> None:
    model = front_work.project(
        project_name="paper",
        walk_document=_walk_doc(),
        walk_evidence=_walk_evidence(),
        pipeline_chain=_pipeline_chain(),
        pipeline_brief={"present": True},
        pipeline_verdict={"present": True},
    )
    doors = [
        door
        for organ in model["organs"]
        for capability in organ["capabilities"]
        for door in capability["reads"] + capability["acts"]
    ]

    assert any(d["method"] == "POST" and d["route"] == "/review/adjudicate" for d in doors)
    assert any(d["method"] == "POST" and d["route"] == "/storyboard/run/launch" for d in doors)
    assert all(d["projection_executes"] is False for d in doors)
    assert all(d["authority_effect"] == "none" for d in doors)


def test_pipeline_controls_carry_real_cost_and_honest_dry_run_boundary() -> None:
    model = front_work.project(project_name="paper", pipeline_chain=_pipeline_chain())
    run = _cap(model, "pipeline", "run-controls")

    assert run["state"] == "COMPLETE"
    assert run["evidence"]["counts_by_cost"] == {
        "local-safe": 1,
        "model-heavy": 1,
        "other": 0,
    }
    launch = [d for d in run["acts"] if d["route"] == "/storyboard/run/launch"]
    assert {d["cost_class"] for d in launch} == {"local-safe", "model-heavy"}
    preview = next(d for d in run["reads"] if d["route"] == "/storyboard/propagate")
    assert "not a universal execution dry-run" in preview["note"]


def test_missing_block_span_fails_provenance_closed_with_continuation() -> None:
    model = front_work.project(project_name="paper", walk_document=_walk_doc(missing_src=True))
    provenance = _cap(model, "walk", "source-provenance")

    assert provenance["state"] == "UNKNOWN"
    assert provenance["evidence"]["missing_source_spans"] == 1
    assert provenance["omissions"][0]["cause"] == "UNRESOLVED"
    assert provenance["omissions"][0]["continuation"] == "/review/provenance?corpus=paper"


def test_producer_refusal_stays_typed_and_dominates_room_state() -> None:
    model = front_work.project(
        project_name="paper",
        walk_document={"ok": False, "error": "no main.tex"},
        pipeline_chain=_pipeline_chain(),
    )

    assert model["state"] == "REFUSED"
    assert next(o for o in model["organs"] if o["id"] == "walk")["state"] == "REFUSED"
    assert _cap(model, "walk", "content-canvas")["reason"] == "no main.tex"


def test_parity_inventory_has_stable_unique_semantic_anchors_and_retires_only_shells() -> None:
    model = front_work.project()
    capabilities = [c for o in model["organs"] for c in o["capabilities"]]
    anchors = [c["semantic_anchor"] for c in capabilities]

    assert len(anchors) == len(set(anchors))
    assert {c["disposition"] for c in capabilities} >= {"KEEP", "TRANSFORM", "RETIRE"}
    retired = [c for c in capabilities if c["disposition"] == "RETIRE"]
    assert {(c["family"], c["id"]) for c in retired} == {
        ("walk", "legacy-page-shell"),
        ("pipeline", "legacy-page-shell"),
    }
    assert all(c["evidence"]["replacement"] == "contextual Work room" for c in retired)


def test_model_handle_is_deterministic_under_mapping_insertion_order() -> None:
    left = front_work.project(
        project_name="paper",
        walk_document={"ok": True, "counts": {"blocks": 0, "sections": 0}, "sections": []},
        pipeline_chain={"project": "paper", "states": [], "organs": [], "global": {}, "joins": {}},
    )
    right = front_work.project(
        project_name="paper",
        walk_document={"sections": [], "counts": {"sections": 0, "blocks": 0}, "ok": True},
        pipeline_chain={"joins": {}, "global": {}, "organs": [], "states": [], "project": "paper"},
    )

    assert left["model_handle"] == right["model_handle"]
    assert left["omitted_digest"] == right["omitted_digest"]


def test_read_converts_source_exceptions_to_exact_refusals(monkeypatch, tmp_path: Path) -> None:
    from laplace.web import pipeline_surface
    from laplace.manuscript import walk
    from laplace.pipeline import project_state

    monkeypatch.setattr(walk, "doc", lambda _corpus: (_ for _ in ()).throw(RuntimeError("walk broke")))
    monkeypatch.setattr(pipeline_surface, "chain", lambda *_a, **_k: _pipeline_chain())
    monkeypatch.setattr(pipeline_surface, "pipeline_brief", lambda *_a, **_k: {"present": True})
    monkeypatch.setattr(project_state, "project_verdict", lambda *_a, **_k: {"present": True})

    model = front_work.read(project_name="paper", repo_root=tmp_path)

    assert model["state"] == "REFUSED"
    assert "RuntimeError: walk broke" in _cap(model, "walk", "content-canvas")["reason"]


def test_action_layer_fails_missing_editor_and_actor_to_unknown() -> None:
    model = front_work.project(project_name="paper", walk_document=_walk_doc())
    actions = model["workbench"]["manuscript"]["actions"]

    assert actions["schema_version"] == "laplace.aisthesis-manuscript-action-layer/1"
    assert actions["state"] == "UNKNOWN"
    assert "complete editable source bytes" in actions["reason"]
    assert "explicit actor" in actions["reason"]
    assert actions["provider_authority"] == {
        "state": "UNKNOWN",
        "reason": "no stronger provider or seat authority receipt was supplied",
        "required_by_endpoint": False,
        "evidence": {},
    }
    assert actions["owns_fetch"] is False
    assert actions["owns_store"] is False


def test_editor_actions_describe_exact_existing_endpoints_and_raw_save() -> None:
    model = front_work.project(
        project_name="paper",
        corpus="paper",
        walk_document=_walk_doc(),
        walk_evidence=_action_evidence(),
        action_context={"actor": "gerard", "profile": "profiles/paper.json"},
    )
    actions = model["workbench"]["manuscript"]["actions"]

    assert actions["state"] == "COMPLETE"
    save = actions["editor"]["save"]
    assert save["request"] == {
        "method": "POST",
        "route": "/projection/tex",
        "query": {
            "file": "paper/main.tex",
            "corpus": "paper",
            "bank": "editor",
            "author": "gerard",
            "surface": "front-work",
            "expected_selection": "sha256:" + "e" * 64,
            "expected_source_digest": "sha256:" + "a" * 64,
        },
        "body": {},
        "body_kind": "raw-text",
        "projection_executes": False,
    }
    assert save["body_source"] == "editor.content"
    assert save["banks"] == ["editor-save", "editor-save-exemplar"]
    assert actions["compile"]["request"]["body"] == {
        "file": "paper/main.tex",
        "corpus": "paper",
        "by": "gerard",
    }
    assert actions["synctex"]["locate"]["route"] == "/projection/locate"
    assert actions["synctex"]["reverse"]["route"] == "/projection/synctex"
    assert actions["redline"]["request"]["route"] == "/review/compare"


def test_editor_without_owner_observed_physical_digest_has_only_inspection_route():
    evidence = _action_evidence()
    evidence['editor'].pop('expected_source_digest')
    actions = front_work.project(project_name='paper', corpus='paper', walk_document=_walk_doc(),
        walk_evidence=evidence, action_context={'actor':'gerard'})['workbench']['manuscript']['actions']
    assert actions['editor']['state'] == 'UNKNOWN'
    assert actions['restore']['state'] == 'UNKNOWN'
    assert actions['editor']['read']['query']['view'] == 'source'
    assert 'physical source digest' in actions['editor']['reason']


def test_restore_is_armed_new_save_and_general_review_state_is_not_restorable() -> None:
    model = front_work.project(
        project_name="paper",
        walk_document=_walk_doc(),
        walk_evidence=_action_evidence(),
        action_context={"actor": "gerard"},
    )
    actions = model["workbench"]["manuscript"]["actions"]
    versions = actions["versions"]["rows"]

    assert versions[0]["version_id"] == "git-base"
    assert versions[0]["restorable"] is False
    assert versions[1]["restorable"] is True
    assert versions[2]["restorable"] is True
    assert actions["restore"]["state"] == "COMPLETE"
    assert actions["restore"]["restore_as_new_save"] is True
    assert actions["restore"]["rewinds_history"] is False
    assert actions["restore"]["ui_arm_required"] is True
    assert actions["restore"]["request"]["route"] == "/projection/restore"


def test_pipeline_launch_preflight_preserves_cost_owner_actor_profile_and_arming() -> None:
    model = front_work.project(
        project_name="paper",
        pipeline_chain=_pipeline_chain(),
        action_context={"actor": "gerard", "profile": "profiles/paper.json"},
    )
    launch = model["workbench"]["pipeline"]["launch"]
    by_action = {row["action"]: row for row in launch["actions"]}

    assert launch["state"] == "COMPLETE"
    local = by_action["storyboard-rebuild"]
    assert local["organ"] == "staged"
    assert local["cost_class"] == "local-safe"
    assert local["local_safe"] is True
    assert local["arm_required"] is True
    assert local["request"]["body"] == {
        "corpus": "paper",
        "action": "storyboard-rebuild",
        "by": "gerard",
        "armed": False,
        "mode": None,
        "profile": "profiles/paper.json",
    }
    heavy = by_action["re-projection"]
    assert heavy["model_heavy"] is True
    assert heavy["banks"] == "work-order"
    assert heavy["bank_before_effect"] is True
    assert heavy["effect_on_success"] == "banked work order only; no model is spawned"
    assert heavy["preflight"]["provider_authority"]["state"] == "UNKNOWN"
    assert heavy["preflight"]["provider_authority"]["required_by_endpoint"] is False


def test_pipeline_launch_refuses_to_imply_actor_or_profile_authority() -> None:
    model = front_work.project(project_name="paper", pipeline_chain=_pipeline_chain())
    launch = model["workbench"]["pipeline"]["launch"]

    assert launch["state"] == "UNKNOWN"
    assert all(row["state"] == "UNKNOWN" for row in launch["actions"])
    assert all(row["profile_mode"] == "CANONICAL_DEFAULT" for row in launch["actions"])
    assert all(row["preflight"]["actor"]["state"] == "UNKNOWN" for row in launch["actions"])
