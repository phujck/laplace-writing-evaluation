"""D-R1 (M5 D repair1, 2026-10-15): canonical guard presence is admitted by ONE pure rule on every door.

`expected`, when a payload carries it, is an ordered array of token strings
(`identity_doors.expected_tokens`); the empty array is admitted only by an owner whose guards are all
optional (research_record creation, visual_place), exactly as the owner's composed schema says.
Native admission, the first statement of every public guarded owner (`identity_doors.admit_expected`)
and `identity_doors.gate` all use it, so a null, object, boolean, numeric, blank, bare-string or
malformed `expected` (and an empty one at a required-guard owner) beside a valid legacy guard is
refused on the HTTP door exactly as natively: before any registry, source or record read, lock or
effect. Legacy-only and correct canonical-array writes are unchanged; stale, wrong-home and
other-project tokens keep the owner's own refusal with its cure. Synthetic roots only."""
import builtins
import contextlib
import hashlib
import json
import os
from pathlib import Path

import filelock
import pytest

from laplace.core import identity_doors
from laplace.native import declarations as d, verbs as writing_verbs
from laplace.projects import library as writing_projects
from laplace.core import checkout

# refused by every owner
SHAPES = [None, {}, False, 0, "", ["not-a-token"], "not-a-token", [7], ["rev:project-metadata:p:" + "a" * 64, 7]]
SHAPE_IDS = ["null", "object", "false", "zero", "empty-string", "malformed-item", "bare-malformed",
             "non-string-item", "valid-then-non-string"]
# ... plus the empty array at a required-guard owner such as project metadata
BAD = [[]] + SHAPES
BAD_IDS = ["empty-array"] + SHAPE_IDS


def _files(root: Path) -> dict:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture
def registry(tmp_path):
    (tmp_path / "registry_projects.json").write_text(json.dumps({"projects": [
        {"name": "p", "manifest": {"display_name": "Old"}}, {"name": "q", "manifest": {"display_name": "Other"}}]}))
    return tmp_path


def _shape_refused(body) -> bool:
    """The entry admission's refusal: kind `shape`, said by the malformed-guard sentence (with the rule's or
    the grammar's own reason)."""
    refused = body.get("refused") or {}
    return refused.get("kind") == "shape" and "canonical guard is malformed" in refused.get("said", "")


def _token(project, revision):
    return identity_doors.identities(("project-metadata", project, revision))["project-metadata:" + project]


def _post(root, path, payload):
    code, _, body = writing_projects.handle(path, {}, "POST", json.dumps(payload).encode(), repo_root=root)
    return code, json.loads(body)


@pytest.mark.parametrize("bad", BAD, ids=BAD_IDS)
def test_malformed_presence_beside_a_valid_legacy_guard_is_refused_natively_and_over_http_before_hydration(registry, monkeypatch, bad):
    old = writing_projects.metadata("p", registry)
    payload = {"project": "p", "title": "New", "expected_revision": old["revision"], "expected": bad}
    with pytest.raises(d.PayloadAdmissionError):
        d.validate_owner_payload("project_metadata_change", payload, project="p")
    hydrations = []
    original = writing_projects._metadata
    monkeypatch.setattr(writing_projects, "_metadata", lambda *a, **k: (hydrations.append(a), original(*a, **k))[1])
    before = _files(registry)
    code, body = _post(registry, "/projects/metadata", payload)
    assert code in (409, 422) and _shape_refused(body), body
    assert hydrations == [] and _files(registry) == before
    assert writing_projects.metadata("p", registry)["title"] == "Old"


def test_a_valid_canonical_token_as_a_bare_string_is_not_widened_on_either_door(registry):
    old = writing_projects.metadata("p", registry)
    payload = {"project": "p", "title": "New", "expected": _token("p", old["revision"])}
    with pytest.raises(d.PayloadAdmissionError):
        d.validate_owner_payload("project_metadata_change", payload, project="p")
    before = _files(registry)
    code, body = _post(registry, "/projects/metadata", payload)
    assert code in (409, 422) and _shape_refused(body) and identity_doors.EXPECTED_SHAPE in body["refused"]["said"]
    assert _files(registry) == before


def test_legacy_only_and_canonical_array_writes_still_succeed_and_stale_wrong_home_and_scope_refuse(registry):
    old = writing_projects.metadata("p", registry)
    legacy = {"project": "p", "title": "Legacy", "expected_revision": old["revision"]}
    d.validate_owner_payload("project_metadata_change", legacy, project="p")
    assert _post(registry, "/projects/metadata", legacy)[0] == 200
    current = writing_projects.metadata("p", registry)
    canonical = {"project": "p", "title": "Canonical", "expected": [_token("p", current["revision"])]}
    d.validate_owner_payload("project_metadata_change", canonical, project="p")
    assert _post(registry, "/projects/metadata", canonical)[0] == 200
    assert writing_projects.metadata("p", registry)["title"] == "Canonical"
    latest = writing_projects.metadata("p", registry)
    refusals = {
        "stale legacy": {"expected_revision": old["revision"]},
        "stale canonical": {"expected": [_token("p", old["revision"])]},
        "wrong home": {"expected": ["rev:plan:p:" + "b" * 64]},
        "other project": {"expected": [_token("q", writing_projects.metadata("q", registry)["revision"])]},
    }
    for label, guard in refusals.items():
        before = _files(registry)
        code, body = _post(registry, "/projects/metadata", {"project": "p", "title": "Refused", **guard})
        assert code == 409 and "refused" in body, (label, body)
        assert _files(registry) == before, label
    # the stale refusal still serves the current token as its cure
    code, body = _post(registry, "/projects/metadata", {"project": "p", "title": "Refused", **refusals["stale canonical"]})
    assert body["refused"]["needed"]["expected"] == [_token("p", latest["revision"])]


# ---- every guarded HTTP route reaches the same entry admission ----------------------------------------
GUARDED_ROUTES = [
    ("projects.library", "/projects/metadata", {"title": "New", "expected_revision": "sha256:" + "0" * 64}),
    ("projects.library", "/projects/material-references", {"operation": "add", "expected_revision": "sha256:" + "0" * 64}),
    ("projects.library", "/projects/app-settings", {"action": "voice-profile", "profile": "x", "content": "x", "expected_profile_revision": "sha256:" + "0" * 64}),
    ("research.concepts", "/concepts/change", {"operation": "edit_node", "node": "n", "value": "x", "base_revision": "sha256:" + "0" * 64}),
    ("research.concepts", "/concepts/plan/change", {"operation": "add", "base_revision": "sha256:" + "0" * 64}),
    ("web.project_work_surface", "/work/structure/change", {"operation": "plan", "expected_revision": "sha256:" + "0" * 64}),
    ("web.project_work_surface", "/work/writing-style/change", {"expected_revision": "sha256:" + "0" * 64}),
    ("web.project_work_surface", "/work/writing-style/profile-change", {"profile": "x", "expected_profile_revision": "sha256:" + "0" * 64}),
    ("web.authoring", "/authoring/section-change", {"operation": "delete", "expected_plan_revision": "0" * 64}),
    ("web.authoring", "/authoring/block-change", {"operation": "undo", "expected_revision": "0" * 64}),
    ("web.authoring", "/authoring/apply", {"turn_id": "WT-x", "proposal_version": "v"}),
    ("web.authoring", "/authoring/proposal-decision", {"turn_id": "WT-x", "decision": "keep-current"}),
    ("web.research_surface", "/research/record", {"id": "r", "expected_revision": "sha256:" + "0" * 64}),
    ("research.visuals_surface", "/visuals/place", {"id": "v", "base_revision": "0" * 64}),
]


@pytest.fixture
def project(tmp_path, monkeypatch):
    from test_writing_controller import _import_project
    from laplace.manuscript import review_surface
    _import_project(tmp_path, "fixture")
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(review_surface, "_repo_root", lambda: tmp_path, raising=False)
    return tmp_path


def _http(module, path, payload, root):
    import importlib
    surface = importlib.import_module("laplace." + module)
    body = json.dumps(payload).encode()
    if module == "web.authoring":
        code, _, raw = surface.handle(path, {"project": ["fixture"]}, "POST", body)
    else:
        code, _, raw = surface.handle(path, {"project": ["fixture"]}, "POST", body, repo_root=root)
    return code, json.loads(raw)


@pytest.mark.parametrize("module,path,legacy", GUARDED_ROUTES, ids=[r[1] for r in GUARDED_ROUTES])
@pytest.mark.parametrize("bad", [None, False, "", "not-a-token", ["not-a-token"]], ids=["null", "false", "blank", "bare", "malformed"])
def test_every_guarded_http_route_refuses_malformed_presence_at_its_owner_entry_without_writes(project, module, path, legacy, bad):
    before = _files(project)
    code, body = _http(module, path, {"project": "fixture", **legacy, "expected": bad}, project)
    assert 400 <= code < 500 and _shape_refused(body), (path, code, body)
    assert _files(project) == before, path


ROUTE_OPERATIONS = {"/projects/metadata": "project_metadata_change", "/projects/material-references": "material_reference_change",
                    "/projects/app-settings": "writing_style_profile_change", "/concepts/change": "concept_change",
                    "/concepts/plan/change": "logical_plan_change", "/work/structure/change": "structure_change",
                    "/work/writing-style/change": "writing_style_change", "/work/writing-style/profile-change": "writing_style_profile_change",
                    "/authoring/section-change": "section_change", "/authoring/block-change": "block_change",
                    "/authoring/apply": "apply_proposal", "/authoring/proposal-decision": "proposal_decision",
                    "/research/record": "research_record", "/visuals/place": "visual_place"}


def test_the_empty_array_is_admitted_exactly_where_the_owner_schema_gives_it_a_meaning():
    declared = sorted(op for op in set(ROUTE_OPERATIONS.values()) if writing_verbs.empty_presence_declared(op))
    assert declared == ["research_record", "visual_place"]
    for operation in TOKEN_OPERATIONS:
        example = {k: v for k, v in d.generated_example(operation).items() if k != "expected"}
        try:
            d.validate_owner_payload(operation, {**example, "expected": []}, project="p"); native = True
        except d.PayloadAdmissionError:
            native = False
        assert native == writing_verbs.empty_presence_declared(operation), operation


@pytest.mark.parametrize("module,path,legacy", GUARDED_ROUTES, ids=[r[1] for r in GUARDED_ROUTES])
def test_an_empty_array_at_each_route_follows_its_owner_rule_without_writes(project, module, path, legacy):
    before = _files(project)
    code, body = _http(module, path, {"project": "fixture", **legacy, "expected": []}, project)
    if writing_verbs.empty_presence_declared(ROUTE_OPERATIONS[path]):
        assert not _shape_refused(body), (path, body)        # creation guard: the owner decides on its own facts
    else:
        assert 400 <= code < 500 and _shape_refused(body) and identity_doors.EXPECTED_NONEMPTY in body["refused"]["said"], (path, body)
        assert _files(project) == before, path


# ---- every public guarded owner refuses before it opens, reads, lists or locks anything ----------------
def _entries(root):
    from laplace.research import concepts as concepts_surface, visuals_surface
    from laplace.manuscript import blocks as manuscript_blocks, manuscript_proposals, manuscript_structure, project_protocol, project_structure, review_surface, writing_style
    from laplace.research import research_records
    from laplace.manuscript import source_application
    return {
        "concepts_surface.logical_plan_change": lambda p: concepts_surface.logical_plan_change(p, root),
        "concepts_surface.change": lambda p: concepts_surface.change(p, root),
        "project_structure.change": lambda p: project_structure.change("p", p, root),
        "manuscript_structure.change": lambda p: manuscript_structure.change("p", p, root),
        "project_protocol.change": lambda p: project_protocol.change("p", p, root),
        "writing_projects.change_metadata": lambda p: writing_projects.change_metadata("p", p, root),
        "writing_projects.change_material_reference": lambda p: writing_projects.change_material_reference("p", p, root),
        "writing_style.update_profile": lambda p: writing_style.update_profile("p", p, root),
        "writing_style.update_global_profile": lambda p: writing_style.update_global_profile(p, root),
        "writing_style.save": lambda p: writing_style.save("p", p, root),
        "research_surface.record": lambda p: research_records.record("p", p, root),
        "review_surface.adjudicate": lambda p: review_surface.adjudicate(root / "md", "p", p, repo_root=root),
        "manuscript_blocks.change": lambda p: manuscript_blocks.change(root, "p", p),
        "authoring_surface.apply_proposal": lambda p: source_application.apply_proposal(root, p),
        "manuscript_proposals.decide": lambda p: manuscript_proposals.decide(root, "p", p),
        "visuals_surface.handle(/visuals/place)": lambda p: visuals_surface.handle("/visuals/place", {}, "POST", json.dumps(p).encode(), repo_root=root),
    }


ENTRY_NAMES = list(_entries(Path("/nonexistent")))


@contextlib.contextmanager
def _forbidden_hydration(touched):
    """Every file open, read, listing, stat, registry resolution and lock fails the test while the owner
    entry runs, and only then (pytest's own fixtures and teardown are outside it)."""
    from unittest import mock
    from laplace.pipeline import registry as project_registry
    def forbid(label):
        def wrapper(*args, **kwargs):
            touched.append(label)
            raise AssertionError("hydration before admission: " + label)
        return wrapper
    targets = [(builtins, "open"), (os, "listdir"), (os, "stat"), (os, "scandir"),
               (project_registry, "resolve"), (filelock.FileLock, "acquire")]
    targets += [(Path, attr) for attr in ("open", "read_bytes", "read_text", "iterdir", "glob", "rglob",
                                          "stat", "exists", "is_file", "is_dir")]
    with contextlib.ExitStack() as stack:
        for owner, attr in targets:
            stack.enter_context(mock.patch.object(owner, attr, forbid(getattr(owner, "__name__", "") + "." + attr)))
        yield


@pytest.mark.parametrize("name", ENTRY_NAMES)
def test_each_public_guarded_owner_refuses_malformed_presence_before_any_read_or_lock(tmp_path, name):
    call = _entries(tmp_path)[name]
    payload = {"project": "p", "expected_revision": "sha256:" + "0" * 64, "expected": None}
    # one uninstrumented call loads the entry's lazily imported modules (module loading scans the import
    # path; it is not owner hydration) and must itself already be refused
    try:
        warm = call(dict(payload))
    except identity_doors.IdentityRefused:
        pass
    else:
        assert warm[0] == 409, (name, warm)
    touched = []
    with _forbidden_hydration(touched):
        try:
            result = call(payload)
        except identity_doors.IdentityRefused as refused:
            result = refused
    if isinstance(result, identity_doors.IdentityRefused):
        assert _shape_refused({"refused": result.refused}) and identity_doors.EXPECTED_SHAPE in result.refused["said"]
    else:
        body = json.loads(result[2]) if len(result) > 2 else result[1]
        assert result[0] == 409 and _shape_refused(body) and identity_doors.EXPECTED_SHAPE in body["refused"]["said"], (name, result)
    assert touched == [], (name, touched)


def test_the_one_rule_is_the_rule_native_admission_and_gate_use():
    for bad in BAD:
        with pytest.raises(ValueError):
            identity_doors.expected_tokens(bad)
    assert identity_doors.expected_tokens([], allow_empty=True) == ()
    for bad in SHAPES:
        with pytest.raises(ValueError):
            identity_doors.expected_tokens(bad, allow_empty=True)
    # gate never reads a non-array or bare-string presence as absence or widens it (emptiness is the entry's)
    for bad in (None, False, "", _token("p", "sha256:" + "1" * 64)):
        with pytest.raises(identity_doors.IdentityRefused):
            identity_doors.gate("project_metadata_change", homes=[("project-metadata", "p", "sha256:" + "1" * 64)],
                                supplied={"expected_revision": "sha256:" + "1" * 64, "expected": bad},
                                required=["expected_revision"], said="Project metadata revision conflict")
    with pytest.raises(identity_doors.IdentityRefused):
        identity_doors.admit_expected({"expected_revision": "sha256:" + "1" * 64, "expected": []}, "project_metadata_change")
    identity_doors.admit_expected({"record": {}, "expected": []}, "research_record", allow_empty=True)   # the owner's creation guard
    with pytest.raises(identity_doors.IdentityRefused):       # the core rule alone never reads emptiness from a door's table
        identity_doors.admit_expected({"record": {}, "expected": []}, "research_record")
    # absent presence is not refused: legacy-only callers are unchanged
    identity_doors.admit_expected({"expected_revision": "sha256:" + "1" * 64}, "project_metadata_change")
    assert identity_doors.gate("project_metadata_change", homes=[("project-metadata", "p", "sha256:" + "1" * 64)],
                               supplied={"expected_revision": "sha256:" + "1" * 64}, required=["expected_revision"],
                               said="Project metadata revision conflict")


# ---- native admission: every operation whose route accepts canonical tokens --------------------------
def _token_operations():
    from laplace.native import verbs as writing_verbs
    out = []
    for operation in sorted(d.DECLARATIONS):
        try:
            example = d.generated_example(operation)
        except Exception:
            continue
        route = writing_verbs.route_for_operation(operation, example)
        if route is not None and writing_verbs.owner_accepts_expected(route):
            out.append(operation)
    return out


TOKEN_OPERATIONS = _token_operations()


def test_the_token_operations_are_the_guarded_owners_this_file_drives():
    assert TOKEN_OPERATIONS == ["concept_change", "logical_plan_change", "project_metadata_change", "research_record",
                                "section_change", "structure_change", "visual_place", "writing_style_change",
                                "writing_style_profile_change"]


@pytest.mark.parametrize("operation", TOKEN_OPERATIONS)
def test_native_admission_refuses_every_malformed_presence_and_admits_absence(operation):
    example = d.generated_example(operation)
    d.validate_owner_payload(operation, example, project="p")      # absence (legacy or none) is admitted
    for bad in SHAPES + [_token("p", "sha256:" + "1" * 64)]:       # ... and no malformed presence is absence
        with pytest.raises(d.PayloadAdmissionError):
            d.validate_owner_payload(operation, {**example, "expected": bad}, project="p")
