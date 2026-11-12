"""First-use content is one Help read and generated packaged documentation."""
import json
from pathlib import Path

import jsonschema
import pytest

from laplace.core import checkout
from laplace.native import declarations as D, tools
from laplace.native.help_guides import GUIDE_DECLARATIONS, render_guide_markdown
from laplace.web import authoring


def test_first_use_guides_are_separate_complete_and_generated():
    overview = D.help_areas("p" * 160)
    assert len(json.dumps(overview).encode()) < 32768
    assert "guides" not in overview
    # wave 13: the overview lists no control; it counts them and carries the controls read (was: one {id} row per control)
    assert set(overview["controls"]) == {"known", "read"} and overview["controls"]["known"] == len(D.CONTROL_DECLARATIONS)
    assert overview["controls"]["read"] == overview["reads"]["controls"]
    controls = {row["id"]: row for row in D.help_areas(concept="controls")["controls"]}
    assert set(controls) == set(D.CONTROL_DECLARATIONS) and all(controls[key]["kind"] == row["kind"] for key, row in D.CONTROL_DECLARATIONS.items())
    assert overview["reads"]["controls"]["payload"] == {"concept": "controls"}
    guides = D.help_areas(concept="guides")
    assert len(json.dumps(guides).encode()) < 15360
    assert [row["id"] for row in guides["guides"]] == ["start", "tasks", "glossary", "reference"]
    sections = {row["id"] for row in GUIDE_DECLARATIONS["tasks"]["sections"]}
    assert {"find-what-happened", "finish-a-task"} <= sections
    for area in D.AREA_DECLARATIONS.values():
        ref = area.get("guide")
        if ref:
            assert any(section["id"] == ref["section"] for section in GUIDE_DECLARATIONS[ref["id"]]["sections"])
    root = Path(__file__).resolve().parents[1]
    names = {"start": "start-here", "tasks": "tasks", "glossary": "glossary", "reference": "reference"}
    for key, name in names.items():
        assert (root / "docs" / f"writing-{name}.md").read_text() == render_guide_markdown(key)
    guides["guides"][0]["sections"][0]["paragraphs"][0] = "caller changed copy"
    assert D.help_areas(concept="guides")["guides"][0]["sections"][0]["paragraphs"][0] != "caller changed copy"


def test_inspection_guidance_and_controls_fixture_version_are_owner_derived():
    """Part 6: the canonical Tasks recipe carries the inspection/closeout step in Help and the generated doc, the guides
    read stays within its cap, every control identity is kept, and the controls fixture names the CURRENT owner version."""
    root = Path(__file__).resolve().parents[1]
    finish = next(row for row in GUIDE_DECLARATIONS['tasks']['sections'] if row['id'] == 'finish-a-task')
    step = [text for text in finish['steps'] if 'use issued reads' in text]
    assert len(step) == 1 and all(word in step[0] for word in ('review', 'support', 'adoption', 'integration', 'release', 'cleanup', 'history', 'Unavailable output', 'issued reads'))
    assert step[0] in render_guide_markdown('tasks') and step[0] in (root / 'docs/writing-tasks.md').read_text()
    assert len(json.dumps(D.help_areas(concept='guides')).encode()) < 15360 and len(json.dumps(D.help_areas('p' * 160)).encode()) < 32768
    fixture = json.loads((root / 'tests/fixtures/help/controls.json').read_text())
    # the count is the registry's own: the fixture is generated from CONTROL_DECLARATIONS, the overview carries the same number, and no row is declared twice
    assert len(fixture['controls']) == len(D.CONTROL_DECLARATIONS) == D.help_areas('book')['controls']['known'] == len({row['id'] for row in fixture['controls']})
    assert all(row.get('does') for row in D.CONTROL_DECLARATIONS.values())  # every declared control carries its guide sentence
    assert fixture['version'] == D.help_areas_version(), D.help_areas_version()


def test_app_run_controls_and_narrow_reading_return_are_declared_and_guided():
    """C1/C2 (Root consumer supplement): the app-run summary's mounted controls are declared in the shared registry with a
    declared view state, the per-step reply carries its owner coordinate in the mounting source, and the Write recipe
    again tells a narrow-screen reader how to get back to the text or the source, rendered into the generated tasks doc."""
    root = Path(__file__).resolve().parents[1]
    source = (root / 'src/laplace/web/static_shared/workspace-workflow-operation.mjs').read_text()
    assert "'workflow:app-run-'+key" in source and "['uses','Read recorded uses'],['river','Read observed flow']" in source
    assert "open.dataset.control='workflow:app-run-reply'" in source and 'open.dataset.controlOwner=owner' in source
    for key in ('workflow:app-run-uses', 'workflow:app-run-river', 'workflow:app-run-reply'):
        row = D.CONTROL_DECLARATIONS[key]
        assert row['view'] == 'workflows' and row['rendered'] and row['kind'] == 'navigation' and 'workspace-workflow-operation.mjs' in row['renders_in']
        assert row['states'] == ['run-detail-offered'] and all(state in D.VIEW_STATES[row['view']] for state in row['states'])
    write = next(row for row in GUIDE_DECLARATIONS['tasks']['sections'] if row['id'] == 'write-save-and-reopen')
    narrow = [step for step in write['steps'] if 'narrow screen' in step]
    assert len(narrow) == 1 and 'Back to reading' in narrow[0] and 'Show source instead' in narrow[0]
    session = (root / 'src/laplace/web/static_shared/workspace-session.mjs').read_text()
    manuscript = (root / 'src/laplace/web/static_shared/workspace-manuscript.mjs').read_text()
    assert 'aria-label="Return to reading">Back to reading</button>' in session and "'Show source instead'" in manuscript   # the guided labels exist
    assert narrow[0] in render_guide_markdown('tasks') and narrow[0] in (root / 'docs/writing-tasks.md').read_text()


def test_default_help_projection_fits_and_counts_every_control(monkeypatch):
    for project in ("", "p" * 160):
        overview = D.help_areas(project)
        # The ordinary emitted representation (default separators), not a compact re-encoding.
        assert len(json.dumps(overview).encode()) < 32768
        assert len(json.dumps(overview, ensure_ascii=False).encode()) < 32768
        assert overview["project"] == project
        assert overview["schema_version"] == D.HELP_AREAS_SCHEMA
        assert overview["version"] == D.help_areas_version()
        assert [row["id"] for row in overview["areas"]] == list(D.AREA_DECLARATIONS)
        assert overview["journeys"] == [{"id": key, **value} for key, value in D.JOURNEY_DECLARATIONS.items()]
        assert overview["observation_facts"] == list(D.OBSERVATION_FACTS)
        assert set(overview["reads"]) == {"diagrams", "checklist", "guides", "controls"}
        for read in overview["reads"].values():
            assert read["http"]["query"].get("project", "") == project
    guides = D.help_areas("p" * 160, "guides")
    assert len(json.dumps(guides).encode()) < 15360
    full = D.help_areas("p" * 160, "controls")
    assert guides["version"] == full["version"] == overview["version"]
    # The overview counts the declared controls and carries the controls read (projection/4; projection/3 listed every id).
    # The read returns every canonical identity, in canonical order, with its label.
    assert list(overview["controls"]) == D.HELP_DEFAULT_PROJECTION["controls"] == ["known", "read"]
    assert overview["controls"]["known"] == len(D.CONTROL_DECLARATIONS) == len(full["controls"])
    assert overview["controls"]["read"]["http"]["query"] == {**({"project": project} if project else {}), "view": "controls"}
    assert [row["id"] for row in full["controls"]] == list(D.CONTROL_DECLARATIONS) and all(row["label"] for row in full["controls"])
    declared = {row["id"] for row in full["controls"]}
    assert all(step["control"] in declared for journey in overview["journeys"] for step in journey["steps"])
    # The existing explicit controls read keeps the full canonical rows and their details.
    assert full["controls"] == [{"id": key, **value} for key, value in D.CONTROL_DECLARATIONS.items()]
    assert full["view_states"] == D.VIEW_STATES and full["coverage"] == D.STATE_COVERAGE
    # The owner version is sensitive to the default projection geometry.
    before = D.help_areas_version()
    monkeypatch.setattr(D, "HELP_DEFAULT_PROJECTION", {**D.HELP_DEFAULT_PROJECTION, "controls": ["known", "read", "ids"]})
    assert D.help_areas_version() != before
    assert D.help_areas()["version"] == D.help_areas(concept="controls")["version"] == D.help_areas(concept="guides")["version"] != before


def test_first_use_guides_have_actual_native_http_parity(tmp_path, monkeypatch):
    monkeypatch.setattr(checkout, "repo_root", lambda: tmp_path)
    issued = D.help_areas()["reads"]["guides"]
    assert issued["http"]["query"] == {"view": "guides"}
    jsonschema.validate(issued["http"]["query"], D.help_http_contract())
    code, _, raw = authoring.handle(issued["http"]["route"], {"view": ["guides"]}, "GET", b"")
    assert code == 200
    actual = json.loads(raw)
    assert actual["inspection"] == {"binding": "declarations", "turn_id": None, "mode": None}
    assert actual["help"] == D.help_areas(concept="guides")
    native = tools.execute(tmp_path, "p" * 160, "work", issued["operation"], issued["payload"])
    assert native["project"] == "p" * 160
    assert native["guides"] == actual["help"]["guides"]
    assert native["version"] == actual["help"]["version"]
    for query in ({"view": ["guides"], "mode": ["work"]}, {"view": ["guides"], "unknown": ["x"]}):
        assert authoring.handle("/authoring/help", query, "GET", b"")[0] in (409, 422)
    with pytest.raises(ValueError):
        D.help_areas(concept="guess-a-guide")
    # The native door retains its ordinary tool-read audit, not a model/action.
    rows = [json.loads(line) for line in (tmp_path / "contract/talk.jsonl").read_text().splitlines()]
    assert len(rows) == 1 and rows[0]["record"] == "writing-tool-read" and rows[0]["operation"] == "help"
    assert {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()} == {"contract/talk.jsonl", "contract/journal.jsonl"}
    journal = [json.loads(line) for line in (tmp_path / "contract/journal.jsonl").read_text().splitlines()]
    assert all(row["record"] in ("act", "bank") for row in journal)
    assert all(row.get("store", "contract/talk.jsonl") == "contract/talk.jsonl" for row in journal)


def test_every_control_id_a_page_module_sets_is_declared():
    """A page module names a control only by an id the help owner declares: a literal with a declared prefix that is not a declaration is a typo or a second registry."""
    import re
    not_controls = {'research:compute-surface', 'research:experiment-matrix', 'research:query-path', 'research:result-comparison', 'source:changed', 'work:manuscript',
                    'work:manuscript-workbench', 'work:pipeline', 'work:talk', 'workflow:app-run-', 'workflow:return'}
    declared = set(D.CONTROL_DECLARATIONS)
    prefixes = {ident.split(':')[0] for ident in declared}
    stray = {}
    for path in sorted((Path(D.__file__).resolve().parents[1] / 'web').glob('static_shared/*.mjs')):
        for match in re.finditer(r"""['"`]([a-z][a-z0-9-]*:[a-z][a-z0-9-]*)['"`]""", path.read_text()):
            value = match.group(1)
            if value.split(':')[0] in prefixes and value not in declared and value not in not_controls:
                stray.setdefault(value, set()).add(path.name)
    assert not stray, stray
