"""Every GENERATED example agrees with its runtime schema and its discovered owner.

This file used to validate the 72 hand-written examples in `writing_contracts.py`.
Those are gone: the example is now built from the schema's own required keys with the
live token of each home filled in (`writing_declarations.generated_example`), so what
has to be proved is the same property about a generated value --- it validates, and
the owner accepts it --- for every operation and every variant, not only for the ones
somebody wrote an example for.
"""
import copy

import jsonschema

from laplace.research import concepts as concepts_surface
from laplace.manuscript import project_structure
from laplace.native import declarations as writing_declarations, tools as writing_tools
from laplace.projects import library as writing_projects
from laplace.writing import reads


def schemas(operation):
    """(label, schema) per variant, or one unlabelled schema."""
    table = writing_declarations.variants(operation)
    if table:
        return sorted(table.items())
    payload = writing_declarations.DECLARATIONS[operation].payload
    return [("", payload)] if payload else []


def test_every_generated_example_matches_its_deployed_input_and_owner_shape():
    for operation in sorted(reads.READS | reads.WRITES):
        for label, schema in schemas(operation):
            example = writing_declarations.generated_example(operation,
                                                             variant=label or None)
            jsonschema.Draft202012Validator(schema).validate(example)
            if operation == 'concept_change':
                assert concepts_surface._validate_change(
                    {'project': 'example-project', **example}) is None, (operation, label)
            elif operation == 'structure_change':
                project_structure._validate_change_payload(example)
            elif operation == 'concept_tree':
                owner = concepts_surface.tree_contract()
                jsonschema.Draft202012Validator(owner).validate(
                    {'project': 'example-project', **example})
                assert all(key in example for key in owner.get('navigation', {})
                           .get(example.get('direction'), {}).get('requires', []))
            elif operation == 'logical_plan_change':
                owner = concepts_surface.logical_plan_operation_contract()
                rule = owner['operations'][example['operation']]
                assert set(rule['required']) <= set(example), (label, example)
                if example['operation'] == 'connect':
                    assert isinstance(example['target'], str)
                if example.get('kind'):
                    assert example['kind'] in owner['object_kinds']


def test_generated_add_object_and_connect_examples_execute_with_live_guard_and_ids(tmp_path):
    status, created = writing_projects.create(
        {'name': 'example-project', 'title': 'Contract example fixture', 'kind': 'paper',
         'purpose': 'Isolated example audit', 'audience': 'Test'}, tmp_path)
    assert status == 201, created

    def run(operation, payload):
        return writing_tools.execute(tmp_path, 'example-project', 'work', operation, payload)

    def generated(operation, variant):
        return copy.deepcopy(writing_declarations.generated_example(
            operation, variant=variant, project='example-project', root=tmp_path))

    revision = run('logical_plan', {})['revision']
    for node in ('result:example-premise', 'result:example-conclusion'):
        payload = {**generated('logical_plan_change', 'add_object'), 'node': node,
                   'base_revision': revision}
        changed = run('logical_plan_change', payload)
        assert changed['ok']
        assert changed['next_guard'] == {'field': 'base_revision', 'value': changed['revision']}
        revision = changed['revision']
    payload = {**generated('logical_plan_change', 'connect'),
               'source': 'result:example-conclusion', 'target': 'result:example-premise',
               'base_revision': revision}
    changed = run('logical_plan_change', payload)
    assert changed['ok'] and changed['revision'] == changed['next_guard']['value']
    example = generated('concept_change', 'add_node')
    example.update(node='result:example-other',
                   base_revision=concepts_surface.state('example-project',
                                                        root=tmp_path)['revision'])
    assert run('concept_change', example)['ok']


def test_navigation_and_edge_target_shapes_are_not_interchangeable():
    tree = writing_declarations.variants('concept_tree')['navigate']
    assert list(jsonschema.Draft202012Validator(tree).iter_errors(
        {'node': 'result:x', 'direction': 'dependency'}))
    schema = writing_declarations.variants('logical_plan_change')['connect']
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(
        {'operation': 'connect', 'base_revision': 'current', 'source': 'result:x',
         'target': {'kind': 'node', 'node_id': 'result:y'}, 'relation': 'prerequisite',
         'rationale': 'requires'}))
