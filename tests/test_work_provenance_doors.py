"""The new Work read keeps real caller Scope and a closed HTTP envelope."""
import json

import pytest

from laplace import sdk
from laplace.native import tools
from laplace.web import project_work_surface as HTTP
from laplace.work import owner_discovery as O, project_work_views as V


def test_provenance_doors_preserve_actual_scope_and_refuse_duplicate_fields(tmp_path, monkeypatch):
    seen = []

    def read(project, payload, root, **kwargs):
        scope = kwargs["native_caller"]
        assert isinstance(scope, O.Scope)
        seen.append((scope.kind, scope.door, scope.namespace, project, payload))
        return {"state": "PUBLIC_TRANSPORT_CONTROL", "scope_kind": scope.kind}

    monkeypatch.setattr(V, "read", read)
    payload = {"namespace": "public", "view": "provenance", "id": "selected",
               "request": {"demand": "aggregate"}}
    sdk.work_read(payload, root=tmp_path)
    native = tools.execute(tmp_path, "bound", "review", "project", payload)
    assert native["scope_kind"] == "project"
    query = {"project": ["public"], "view": ["provenance"], "id": ["selected"],
             "request": [json.dumps(payload["request"])]}
    code, _, raw = HTTP.handle("/work/state", query, "GET", repo_root=tmp_path)
    assert code == 200 and json.loads(raw)["scope_kind"] == "owned-workspace"
    assert [row[:3] for row in seen] == [("owned-workspace", "sdk", None),
        ("project", "native", "bound"), ("owned-workspace", "http", None)]
    assert seen[1][3] == "bound" and seen[1][4]["namespace"] == "public"

    # Outer duplicates cannot pick one scope/view, and nested duplicates cannot
    # turn the displayed aggregate request into a different owner demand.
    count = len(seen)
    for changed in ({**query, "project": ["public", "foreign"]},
                    {**query, "view": ["detail", "provenance"]},
                    {**query, "request": ['{"demand":"aggregate","demand":"evidence"}']}):
        assert HTTP.handle("/work/state", changed, "GET", repo_root=tmp_path)[0] == 422
    assert len(seen) == count

    with pytest.raises(ValueError, match="readonly project Work"):
        sdk.work_read({"action": "done"}, root=tmp_path)


def test_completion_support_wire_uses_the_actual_artifact_reference_contract():
    import jsonschema
    from laplace.writing.schemas import SCHEMAS
    from laplace.work.project_work_evidence import artifact_reference_contract

    schema = SCHEMAS["task_status"]["properties"]["completion_support"]
    assert schema == artifact_reference_contract()
    for reference in ({"id": "ART-public", "expected_sha256": "a" * 64},
                      {"path": "evidence/public.json", "scope": "project", "expected_sha256": "a" * 64}):
        jsonschema.validate(reference, schema)
    for reference in ({"id": "ART-public"},
                      {"id": "ART-public", "path": "evidence/public.json", "expected_sha256": "a" * 64},
                      {"id": "ART-public", "expected_sha256": "a" * 64, "project": "foreign"}):
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(reference, schema)


def test_actual_provenance_sdk_native_http_stays_metadata_only(tmp_path, monkeypatch):
    from urllib.parse import parse_qs, urlsplit
    from laplace.projects import artifacts
    from laplace.writing import session_reads
    from test_work_provenance import scene

    scene(tmp_path)  # Canonical public controlled records, never a provider turn.
    monkeypatch.setattr(artifacts, "read", lambda *a, **k: pytest.fail("artifact body for aggregate"))
    monkeypatch.setattr(session_reads, "public_message", lambda *a, **k: pytest.fail("reply body for aggregate"))
    handle = V.handle("p", {"view": "provenance", "id": "work",
                             "request": {"demand": "aggregate"}})
    first = sdk.work_read(handle["payload"], root=tmp_path)
    native = tools.execute(tmp_path, "p", "review", "project", handle["payload"])
    url = urlsplit(handle["http"]["url"])
    code, _, raw = HTTP.handle(url.path, parse_qs(url.query), "GET", repo_root=tmp_path)
    human = json.loads(raw)
    assert code == 200
    for key in first:
        if key != "caller_scope":
            assert native[key] == first[key] == human[key]
    assert first["counts"]["bound_turns"] == 1
    assert first["inspection"]["bodies"] == "NOT_READ"
    assert native["caller_scope"]["namespace"] == "p"

    # The actual domain rejects forged requests or foreign native scope before
    # looking up either the task or its conversation/artifact metadata.
    from laplace.work import project_work as W
    monkeypatch.setattr(W, "_tasks", lambda *a, **k: pytest.fail("lookup before refusal"))
    with pytest.raises(ValueError):
        sdk.work_read({**handle["payload"], "action": "done"}, root=tmp_path)
    with pytest.raises(ValueError):
        tools.execute(tmp_path, "foreign", "review", "project", handle["payload"])
