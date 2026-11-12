"""Current help references must name the actual source bytes, not an older commit."""
import hashlib
from pathlib import Path

from laplace.native import declared as writing_declared, declarations as d
from laplace.web import writing_declared_http


def _read_citation(rule):
    value = rule.rendered()['enforced_at']
    coordinate, revision = value.rsplit('@', 1)
    relative, line = coordinate.rsplit(':', 1)
    raw = (Path(__file__).resolve().parents[1] / relative).read_bytes()
    assert revision == 'sha256:' + hashlib.sha256(raw).hexdigest()
    return raw.decode().splitlines()[int(line) - 1]


def test_proposal_apply_current_identity_gate_is_bound_to_current_source():
    declaration = d.HTTP_DECLARATIONS['authoring/apply']
    rule = next(rule for rule in declaration.rules if rule.kind == 'identity')
    line = _read_citation(rule)
    assert '"apply_proposal", supplied=payload' in line


def test_research_view_help_points_to_the_actual_view_dispatch():
    rules = [rule for rule in d.DECLARATIONS['research'].rules if rule.field == 'view']
    assert rules
    for rule in rules:
        line = _read_citation(rule)
        assert 'payload.get("view")' in line
        assert '"/research/result"' in line


def test_legacy_literal_coordinate_retains_its_historical_revision():
    rule = d.Rule('scope', 'Legacy source scope', door='src/laplace/scanner.py:2182')
    assert rule.rendered()['enforced_at'] == 'src/laplace/scanner.py:2182@' + d.BASE_REVISION


def test_project_review_move_keeps_all_declared_http_handlers_and_consumers_resolvable():
    # Registration is used by actual HTTP request admission, not just generated help.
    # Resolve every declaration so a removed frontend method cannot disable unrelated reads.
    assert {"authoring/proposals", "authoring/session-turn", "authoring/proposal-preview"} <= set(d.HTTP_DECLARATIONS)
    for declaration in d.HTTP_DECLARATIONS.values():
        assert declaration.handler
        assert d.http_help(declaration.route, operation=declaration.operation)
        assert all(declaration.resolved_responses().values())
        assert all(declaration.resolved_consumers().values())
    queue = d.HTTP_DECLARATIONS["authoring/proposals"].resolved_consumers()
    assert queue["project-review-queue"].startswith("src/laplace/web/static_shared/workspace-review.mjs:")
    turn = d.HTTP_DECLARATIONS["authoring/session-turn"].resolved_consumers()
    assert turn["saved-turn-summary"].startswith("src/laplace/web/static_shared/workspace-material.mjs:")
