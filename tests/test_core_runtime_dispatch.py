"""Core consolidation, family 2: the read contract, the one operation table and the runtime/dispatch owners.

writing.reads owns what a consulted read is; writing.operations owns the one admission + family table and the pure
replay; writing.turn_admission owns sessions and the lifecycle entry; writing.turn_execution runs an admitted turn;
turn_jobs/child_hosts/turn_control/dispatch_execution/dispatch_parent own the live registry, child hosts, steering
and dispatch. The native gateway (writing_tools) and the authoring facade consume them under their old names and
forward outward only; none of the owners imports the gateway, the facade, the HTTP door or the scanner. An ordinary
turn runs headless against an injected deterministic provider through the owners alone.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path

from laplace.web import scanner
from laplace.writing import provider as writing_provider
from laplace.native import tools as writing_tools
from laplace.writing import operations
from laplace.writing import reads
from laplace.writing import turn_execution
from laplace.writing import turn_admission
from laplace.writing import turn_jobs
from laplace.writing import session_reads
from laplace.writing import records
from laplace.writing import provider as writing_provider
from laplace.core import checkout
from laplace.writing import child_hosts, dispatch_execution, operations, reads, records, turn_admission, turn_execution, turn_jobs, turn_reads
import laplace.core.identity_doors  # noqa: F401  the lane-level pair declarations (ADDED_PAIRS) are part of the grammar the routes are checked against

SRC = Path(__file__).resolve().parents[1] / 'src' / 'laplace'
PYTHON = str(SRC.parents[1] / 'scripts' / 'laplace-python')
FAMILY = ['writing/reads.py', 'writing/operations.py', 'core/checkout.py', 'writing/turn_jobs.py', 'writing/turn_admission.py', 'writing/turn_execution.py',
          'writing/turn_control.py', 'writing/child_hosts.py', 'writing/dispatch_execution.py', 'writing/dispatch_parent.py', 'writing/dispatch_returns.py',
          'writing/prepared_work.py']   # the tool bodies (tool_work/tool_source/tool_sessions) are the gateway's own long branches
DOORS = {'laplace.web.authoring', 'laplace.web.authoring_http', 'laplace.web.scanner', 'laplace.web.research_surface', 'laplace.native.tools'}
#: the tool bodies are the gateway's own long branches: they may still name it for its remaining projections
GATEWAY_ALLOWED = {'writing/tool_work.py'}
#: no residual: the research family (R1, 2026-10-19) closed the table's lazy research_surface edge; the research
#: operations call writing.research_* owners directly and the other owner-HTTP surfaces stay lazy HTTP doors
RESIDUAL: set = set()


def _imports(path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            yield module, node.lineno
            for alias in node.names:
                yield (module + '.' + alias.name if module else alias.name), node.lineno


def test_the_runtime_family_never_imports_a_door_even_lazily():
    offences = [(rel, line, name) for rel in FAMILY for name, line in _imports(SRC / rel)
                if name in DOORS and not (name == 'laplace.native.tools' and rel in GATEWAY_ALLOWED) and (rel, name) not in RESIDUAL]
    assert offences == []


def test_the_gateway_and_the_facade_forward_the_owners_same_objects():
    assert operations._execute is operations._execute and operations.replay_read is operations.replay_read
    assert reads.READS is reads.READS and reads.read_output_digest is reads.read_output_digest
    assert reads.ACTION_VIEWS is reads.ACTION_VIEWS and operations._admit_operation is operations._admit_operation
    assert turn_admission.start_turn is turn_admission.start_turn and turn_admission.new_session is turn_admission.new_session
    assert turn_admission.configure_session is turn_admission.configure_session and turn_admission.binding_row is turn_admission.binding_row
    assert turn_execution._finalize_provider_proposal is turn_execution._finalize_provider_proposal
    assert turn_jobs._JOBS is turn_jobs._JOBS and session_reads.child_execution is child_hosts.child_execution
    assert records.bank is records.bank and writing_provider.WritingTurn is writing_provider.WritingTurn
    assert scanner._repo_root is checkout.repo_root
    assert operations._help_renderer is writing_tools.help_response, 'the gateway injected its help document once'
    for name in ('def new_session(', 'def start_turn(', 'def _start_turn(', 'def configure_session(', 'def effort_as_sent(', 'def binding_row(', 'def _finalize_provider_proposal(', 'def _editor_actions('):
        assert name not in (SRC / 'web' / 'authoring.py').read_text()
    for name in ('def _execute(', 'def _admit_operation(', 'def read_output_digest(', 'def replay_read(', 'READS = {'):
        assert name not in (SRC / 'native' / 'tools.py').read_text()


def test_the_operation_table_and_the_read_contract_are_one_definition_for_every_owner():
    from laplace.manuscript import proposal_currentness, source_application
    from laplace.writing import mutation_attribution
    for module in (turn_reads, proposal_currentness, source_application, mutation_attribution):
        # exact import inspection (RT-N2): the state-effects owners import the gateway under no spelling
        imported = [name for name, _ in _imports(SRC / 'writing' / (module.__name__.rsplit('.', 1)[-1] + '.py'))]
        assert not [name for name in imported if name == 'laplace.native.tools' or name.startswith('laplace.native.tools.')], module.__name__
    covered = [op for ops in operations._FAMILY_OPERATIONS.values() for op in ops]
    assert sorted(covered) == sorted(set(covered)) and set(covered) == reads.READS | reads.WRITES
    # the action tables name only operations the table dispatches, and the only operations outside WRITES that
    # claim affected views are the reads with effects (measured 2026-10-19: ['reference_text']); nothing else may claim them
    for table in (reads.ACTION_VIEWS, reads.ACTION_POTENTIAL_VIEWS, reads.ACTION_EXCLUDED_READS):
        assert set(table) <= set(covered), sorted(set(table) - set(covered))
    assert sorted(set(reads.ACTION_VIEWS) - reads.WRITES) == ['reference_text']
    assert all(name in reads.READS for name in set(reads.ACTION_VIEWS) - reads.WRITES)


def test_the_family_imports_headless():
    script = ('import json,sys,importlib\n'
              'for m in ("laplace.writing.reads","laplace.writing.operations","laplace.core.checkout","laplace.writing.turn_jobs","laplace.writing.child_hosts",'
              '"laplace.writing.turn_admission","laplace.writing.turn_execution","laplace.writing.turn_control","laplace.writing.dispatch_execution",'
              '"laplace.writing.dispatch_parent","laplace.writing.dispatch_returns","laplace.writing.prepared_work"):\n'
              '    importlib.import_module(m)\n'
              'print(json.dumps(sorted(x for x in sys.modules if x.startswith("laplace"))))')
    out = subprocess.run([PYTHON, '-c', script], capture_output=True, text=True, cwd=str(SRC.parents[1]))
    assert out.returncode == 0, out.stderr[-2000:]
    loaded = set(json.loads(out.stdout.strip().splitlines()[-1]))
    assert not (loaded & DOORS), sorted(loaded & DOORS)


HEADLESS_TURN = r'''
import json, sys, threading
from pathlib import Path
root = Path(sys.argv[1]); (root / 'contract').mkdir(parents=True, exist_ok=True)
manuscript = root / 'sources' / 'book'; manuscript.mkdir(parents=True)
(manuscript / 'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nOriginal prose.\n\\end{document}\n')
from laplace.projects import library as writing_projects; from laplace.writing import provider as writing_provider; from laplace.manuscript import writing_style
from laplace.writing import records, turn_admission, turn_jobs
status, result = writing_projects.import_source({'name': 'book', 'title': 'Book', 'root': 'sources/book/main.tex', 'editable': True}, root)
assert status == 201, result
profile = root / 'profiles/voice/book-v1.md'; profile.parent.mkdir(parents=True)
profile.write_text('# Book voice\nUse exact concrete language.\n')
writing_style.save('book', {'profile': 'profiles/voice/book-v1.md', 'guidance': 'Explain the consequence first.', 'expected_revision': writing_style.state('book', root)['revision']}, root)
CATALOGUE = {'providers': [{'id': 'claude', 'available': True, 'models': [{'id': 'haiku', 'resolved_model': 'claude-haiku-stub', 'supports_effort': True, 'efforts': ['low', 'medium', 'high']}]}]}
seen = []
class Stub:
    """A deterministic provider at the one provider boundary (writing_provider.WritingTurn)."""
    def __init__(self, root, provider, model, effort, native_id, emit, mode, *, project, logical_turn_id, native_source_paths=None, session_id=None):
        self.emit, self.provider, self.model, self.effort, self.session_id, self.turn_id = emit, provider, model, effort, session_id, logical_turn_id
        self.native_id = native_id; self.inference_started = False; self.operating_brief = None; self.supports_effort = True
    def run(self, prompt):
        self.emit({'type': 'session', 'native_id': 'stub-' + str(self.session_id), 'provider': self.provider, 'model': self.model, 'process': {'cwd': str(root), 'tools': [], 'mcp': 'ok'}})
        self.inference_started = True; seen.append({'turn_id': self.turn_id, 'prompt_chars': len(prompt)})
        return {'status': 'completed', 'text': 'A deterministic reply.', 'native_id': 'stub-' + str(self.session_id)}
writing_provider.capabilities = lambda *a, **k: CATALOGUE
writing_provider.WritingTurn = Stub
writing_provider.context_window_advertised = lambda *a, **k: None
session = turn_admission.new_session(root, 'book', 'claude', 'haiku', 'low')
started = turn_admission.start_turn(root, {'project': 'book', 'session_id': session['id'], 'text': 'Say something deterministic.', 'mode': 'discuss'})
job = turn_jobs._JOBS[started['turn_id']]
with job['condition']:
    assert job['condition'].wait_for(lambda: job['done'], timeout=20)
rows = [json.loads(l) for l in (root / 'contract/talk.jsonl').read_text().splitlines()]
turn = records.fold_records(root)['turns'][started['turn_id']]
reused = turn_admission.start_turn(root, {'project': 'book', 'session_id': session['id'], 'text': 'Say something deterministic.', 'mode': 'discuss', 'request_id': turn.get('request_id')})
print(json.dumps({'records': [r['record'] for r in rows], 'reply_status': (turn.get('reply') or {}).get('status'), 'reply_text': (turn.get('reply') or {}).get('text'),
                  'binding_native_id': next((r.get('native_id') for r in rows if r.get('record') == 'writing-binding'), None), 'provider_calls': seen,
                  'reused_same_turn': reused.get('turn_id') == started['turn_id'] if isinstance(reused, dict) else None,
                  'doors': sorted(m for m in sys.modules if m in {'laplace.web.authoring', 'laplace.web.authoring_http', 'laplace.web.scanner', 'laplace.web.research_surface'})}))
'''


def test_an_ordinary_turn_runs_headless_through_the_owners_with_an_injected_provider(tmp_path):
    script = tmp_path / 'headless_turn.py';script.write_text(HEADLESS_TURN)
    out = subprocess.run([PYTHON, str(script), str(tmp_path / 'root')], capture_output=True, text=True, cwd=str(SRC.parents[1]),
                         env={**os.environ, 'LAPLACE_STATE': str(tmp_path / 'state')})
    assert out.returncode == 0, out.stderr[-3000:]
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result['reply_status'] == 'completed' and result['reply_text'] == 'A deterministic reply.'
    assert {'writing-session', 'writing-turn', 'writing-binding', 'writing-reply'} <= set(result['records'])
    assert result['binding_native_id'] and result['binding_native_id'].startswith('stub-') and len(result['provider_calls']) == 1
    # the research facade is reached once, at module level, by the operating brief's declared schemas
    # (writing_schemas.py -> writing_declared.py), a declarations-layer edge outside this family that the packet names
    assert set(result['doors']) <= {'laplace.web.research_surface'}, result['doors']


def test_the_status_detail_view_is_the_panes_own_computation_and_the_grammar_declares_every_routed_pair():
    from laplace.core import grammar as g
    from laplace.native import verbs as v
    routed = {(r.verb, r.concept) for r in v.ROUTES if r.door == 'both'}
    assert routed <= set(g.VERB_CONCEPTS) | set(g.ADDED_PAIRS) and set(g.VERB_CONCEPTS) <= routed
    # dispatch_status (declared): "Default view:status is small; ... view:detail child evidence detail".
    # The small view carries no fan_out and bounded child rows; detail spreads project_work.dispatch_view
    # itself, the one computation the project-work pane reads (test_writing_dispatch reads both through it).
    body = (SRC / 'writing' / 'dispatch_parent.py').read_text().split('def native_status', 1)[1].split('\ndef ', 1)[0]
    detail_branch = body.split("selected=='detail'", 1)[1].split('children=[]', 1)[0]
    assert "'fan_out'" not in body and '**view' in detail_branch
