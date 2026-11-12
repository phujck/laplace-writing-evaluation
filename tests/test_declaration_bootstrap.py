"""Each public registration entry must work in its own cold interpreter."""
import itertools
import json
from pathlib import Path
import runpy
import subprocess
import sys

import pytest


TREE = Path(__file__).resolve().parents[1]
MODULES = ('native.declarations', 'native.declared', 'web.writing_declared_http')
ENTRIES = [(name,) for name in MODULES] + list(itertools.permutations(MODULES))
PROBE = r'''
import importlib,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
for name in json.loads(sys.argv[2]):
    importlib.import_module('laplace.'+name)
from laplace.native import declarations as d
entry_keys=(sorted(d.DECLARATIONS),sorted(d.HTTP_DECLARATIONS))
assert 'help' in d.DECLARATIONS and 'authoring/help' in d.HTTP_DECLARATIONS
from laplace.native import tools
assert entry_keys==(sorted(d.DECLARATIONS),sorted(d.HTTP_DECLARATIONS))
assert set(d.DECLARATIONS)==tools.READS|tools.WRITES
assert len(d.DECLARATIONS)==89   # the established deployed operations (D: 88; M5 2026-10-16: + work_review)
native=tools.help_response(Path.cwd(),'p','review',{'operation':'help'})
http=tools.help_response(Path.cwd(),'p','review',{'route':'/authoring/help','method':'GET'})
assert native['requested_operation']=='help'
# the default native help moves a large input into its declared `input` section (D help cost);
# the section read returns the exact declared payload
assert 'input' not in native['action'] and native['action']['sections']['chars']['input']>0
moved=tools.help_response(Path.cwd(),'p','review',{'operation':'help','section':'input'})
assert moved['action']['value']==d.DECLARATIONS['help'].payload
assert http['action']['input']==d.help_http_contract()
assert http['action']['input']==d.HTTP_DECLARATIONS['authoring/help'].payload
print(json.dumps({'native_keys':sorted(d.DECLARATIONS),'http_keys':sorted(d.HTTP_DECLARATIONS),
    'native_payload_digest':d.digest({k:v.payload for k,v in d.DECLARATIONS.items()}),
    'http_payload_digest':d.digest({k:v.payload for k,v in d.HTTP_DECLARATIONS.items()}),
    'native_help_digest':d.digest(native),'native_input_section_digest':d.digest(moved),
    'http_help_digest':d.digest(http)}))
'''


def cold_manifest(entry, cwd):
    result=subprocess.run([sys.executable,'-I','-B','-c',PROBE,str(TREE/'src'),json.dumps(entry)],
                          cwd=cwd,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


@pytest.fixture(scope='module')
def complete_manifest(tmp_path_factory):
    return cold_manifest(('writing_declarations',),tmp_path_factory.mktemp('core-first'))


@pytest.mark.parametrize('entry',ENTRIES,ids=lambda entry:'-'.join(entry))
def test_each_cold_entry_matches_complete_registry_and_rendering(entry,tmp_path,complete_manifest):
    assert cold_manifest(entry,tmp_path)==complete_manifest


@pytest.mark.parametrize('tool',['door_citations.py','rule_census.py'])
def test_isolated_citation_tool_imports_after_native_entry(tool,tmp_path):
    code='''import sys,runpy
sys.path.insert(0,sys.argv[1])
from laplace.native import declared as writing_declared
runpy.run_path(sys.argv[2],run_name='cold_tool_import')
print('loaded')'''
    result=subprocess.run([sys.executable,'-I','-B','-c',code,str(TREE/'src'),str(TREE/'tools'/tool)],
                          cwd=tmp_path,text=True,capture_output=True)
    assert result.returncode==0,result.stderr
    assert result.stdout.strip()=='loaded'
    assert not list(tmp_path.iterdir())


def test_explicit_historical_emitter_keeps_final_http_bootstrap(tmp_path):
    # This one-time 73-operation migration is not a current-source regenerator.
    # Exercise only its emission into our empty fixture; never replay its main.
    migration=runpy.run_path(str(TREE/'tools/migrate_declarations.py'))
    target=tmp_path/'writing_declared.py'
    migration['emit_declared']({},target,{}, {})
    assert target.read_text().rstrip().endswith(
        'from laplace.web import writing_declared_http as _declared_http  # noqa: E402,F401')
