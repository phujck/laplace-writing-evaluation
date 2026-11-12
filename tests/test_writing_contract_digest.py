"""Help envelope identity is stable across fresh process hash seeds."""
import json
import os
from pathlib import Path
import subprocess
import sys

from laplace.native import declarations
from laplace.writing import operating as writing_operating


def test_contract_and_source_help_digests_match_across_process_hash_seeds():
    code = '''
import json
from laplace.writing import operating; from laplace.native import tools as writing_tools
contract = operating.tool_contract()
source_help = writing_tools._execute(None, '', 'review', 'help', {'operation': 'source'})
print(json.dumps({'contract': contract['digest'],
                 'source_help': writing_tools.read_output_digest('help', source_help),
                 'registration': contract['native_registration_signature'],
                 'dispatch_plan': contract['exact_action_digests']['dispatch_plan'],
                 'dispatch_launch': contract['exact_action_digests']['dispatch_launch']}))
'''
    root = Path(__file__).resolve().parents[1]
    values = [json.loads(subprocess.check_output([sys.executable, '-c', code], cwd=root,
                env={**os.environ, 'PYTHONHASHSEED': seed}, text=True))
              for seed in ('0', '1', '2', '17')]
    assert all(value == values[0] for value in values[1:]), values


def test_tied_enforcement_defaults_keep_declared_rule_order_and_effective_sites():
    for operation in ('dispatch_plan', 'dispatch_launch'):
        help_row = declarations.help_payload(operation, permitted=True, with_tokens=False)
        declaration = declarations.DECLARATIONS[operation]
        carried = [rule for rule in declaration.rules if not
                   (rule.kind == 'identity' and len(rule.carries) > 1 and rule.carries[1] == 'home')]
        doors = [rule.door for rule in carried if rule.door]
        # Highest-frequency ties pick the first declared door; no rule moves.
        expected = max(dict.fromkeys(doors), key=doors.count)
        assert help_row['rules_enforced_at'] == declarations.cited(expected)
        for rendered, original in zip(help_row['rules'], carried, strict=True):
            assert rendered['says'] == original.says
            if original.door:
                assert rendered.get('enforced_at', help_row['rules_enforced_at']) == declarations.cited(original.door)
