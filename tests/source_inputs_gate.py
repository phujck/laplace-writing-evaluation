"""Minimal isolated Source.check gate, not functional owner/HTTP acceptance.

Only staged source is compiled. The existing source_inventory.contract function
is evaluated unchanged with its literal source constants; no package import,
miniature validator, filesystem fixture, provider or dependency fallback exists.
Full runtime behavior is judged by the separately fixed public evaluator.
"""
from __future__ import annotations
import ast
import json
from pathlib import Path

FILES = (
    'src/laplace/work/source_inventory.py',
    'src/laplace/work/source_kernel.py',
    'src/laplace/work/owner_discovery.py',
    'tests/test_source_inputs_projection.py',
)


def source_contract(tree):
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'contract']
    if len(functions) != 1:
        raise ValueError('one existing source_inventory.contract function is required')
    function = functions[0]
    # Read only literal constants actually used by the pure contract function.
    # This is its real returned schema, not a duplicate request validator.
    needed = {node.id for node in ast.walk(function) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
    values = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            pairs = [(target, node.value)]
            if isinstance(target, (ast.Tuple, ast.List)) and isinstance(node.value, (ast.Tuple, ast.List)):
                pairs = list(zip(target.elts, node.value.elts))
            for name, value in pairs:
                if isinstance(name, ast.Name) and name.id in needed:
                    try:
                        values[name.id] = ast.literal_eval(value)
                    except (ValueError, TypeError):
                        pass
    namespace = {'__builtins__': __builtins__, **values}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<staged source_inventory.contract>', 'exec'), namespace)
    return namespace['contract']()


def main():
    trees = {}
    for relative in FILES:
        path = Path(relative)
        text = path.read_text(encoding='utf-8')
        trees[relative] = ast.parse(text, filename=relative)
        compile(text, relative, 'exec')
    contract = source_contract(trees[FILES[0]])
    assert contract['additionalProperties'] is False
    assert set(contract['required']) == {'facet', 'reference'}
    properties = contract['properties']
    assert {'facet', 'reference', 'offset', 'limit', 'as_of', 'project_lens'} <= set(properties)
    selector = properties.get('projection', {})
    assert selector.get('const') == 'inputs' or selector.get('enum') == ['inputs'], 'closed optional projection=inputs is missing'
    assert properties['limit']['minimum'] == 1 and properties['limit']['maximum'] == 20
    assert properties['offset']['maximum'] == 192
    assert 'budget' not in properties, 'no caller response-budget bypass'
    assert properties['reference']['additionalProperties'] is False
    print(json.dumps({'state': 'PASS', 'scope': 'STAGED_SYNTAX_AND_ACTUAL_CLOSED_CONTRACT_ONLY',
        'compiled': list(FILES), 'contract': 'closed optional inputs selector; legacy omission/identity/count bounds retained',
        'not_proved': ['runtime branching', 'issued entry', 'HTTP/native/SDK parity', 'body read', 'continuation', 'privacy', 'real browser'],
        'functional_evaluator': 'tests/test_source_inputs_projection.py'}))


if __name__ == '__main__':
    main()
