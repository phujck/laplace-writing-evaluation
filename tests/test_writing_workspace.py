import json, shlex, subprocess, sys
from pathlib import Path
from laplace.projects import library as writing_projects


SCRIPT=Path(__file__).parents[1]/'scripts/writing_workspace.py'


def _project(root, name='xx'):
 source=root/'source';source.mkdir(parents=True)
 (source/'main.tex').write_text('\\documentclass{article}\n\\begin{document}\nOriginal prose.\n\\end{document}\n')
 assert writing_projects.import_source({'name':name,'title':'X','root':'source/main.tex','editable':True},root)[0]==201
 return source


def _run(root, command, *extra, stdin=None):
 return subprocess.run([sys.executable,str(SCRIPT),command,'xx','--root',str(root),*extra],
                       input=stdin,capture_output=True,text=True)

def test_workspace_context_and_review_role_call_refusal(tmp_path):
 _project(tmp_path)
 context=_run(tmp_path,'context')
 assert context.returncode==0 and json.loads(context.stdout)['ok']
 call=_run(tmp_path,'call','--mode','review',stdin='{"operation":"concept_change","payload":{}}')
 value=json.loads(call.stdout)
 assert call.returncode==2 and value['ok'] is False
 assert 'Independent review' in value['error']


def test_proposal_is_banked_inspectable_and_never_writes_until_explicit_accept(tmp_path):
 source=_project(tmp_path);before=(source/'main.tex').read_text()
 context=_run(tmp_path,'context','--mode','revise','--section','main','--target-dir','source')
 assert context.returncode==0,context.stdout
 context_value=json.loads(context.stdout);context_id=context_value['context']['context_id']
 proposal={'answer':'A scoped revision.','edits':[{'file':'main.tex','line_start':3,'line_end':3,
           'before':'Original prose.','after':'Revised prose.','reason':'clarity'}]}
 proposed=_run(tmp_path,'proposal','--mode','revise','--section','main','--target-dir','source',
               '--context-id',context_id,stdin=json.dumps(proposal))
 assert proposed.returncode==0,proposed.stdout
 receipt=json.loads(proposed.stdout)
 assert receipt['status']=='PROPOSED'
 assert receipt['proposal']['answer']==proposal['answer']
 normalized=receipt['proposal']['edits'][0]
 assert {key:normalized[key] for key in proposal['edits'][0]}==proposal['edits'][0]
 assert normalized['source_anchor']['line_start']==3
 assert normalized['source_anchor']['unique'] is True
 assert len(normalized['source_anchor']['sha256'])==64
 assert (source/'main.tex').read_text()==before

 inspected=_run(tmp_path,'inspect','--turn',receipt['turn_id'])
 assert inspected.returncode==0 and json.loads(inspected.stdout)['status']=='PROPOSED'
 refused=_run(tmp_path,'apply','--mode','revise','--turn',receipt['turn_id'])
 assert refused.returncode==2 and '--accept' in json.loads(refused.stdout)['error']
 assert (source/'main.tex').read_text()==before

 applied=_run(tmp_path,'apply','--mode','revise','--turn',receipt['turn_id'],'--accept')
 assert applied.returncode==0,applied.stdout
 result=json.loads(applied.stdout)
 assert result['status']=='APPLIED' and result['application']['complete'] is True
 assert (source/'main.tex').read_text().splitlines()[2]=='Revised prose.'


def test_proposal_refuses_wrong_scope_and_transport_round_trips_quoted_root(tmp_path):
 root=tmp_path/'root with spaces';root.mkdir();source=_project(root);before=(source/'main.tex').read_text()
 context=_run(root,'context','--mode','revise','--section','main','--target-dir','source')
 value=json.loads(context.stdout);context_id=value['context']['context_id']
 argv=shlex.split(value['transports']['proposal'])
 assert argv[0]==str(root/'scripts/laplace-python')
 assert argv[1]==str(root/'scripts/writing_workspace.py')
 assert argv[3]=='xx' and argv[argv.index('--mode')+1]=='revise'
 assert argv[argv.index('--root')+1]==str(root)

 proposal={'answer':'escape','edits':[{'file':'other.tex','line_start':1,'line_end':1,
           'before':'x','after':'y','reason':'outside'}]}
 refused=_run(root,'proposal','--mode','revise','--section','main','--target-dir','source',
              '--context-id',context_id,stdin=json.dumps(proposal))
 assert refused.returncode==2
 invalid=json.loads(refused.stdout)
 assert invalid['status']=='INVALID' and 'not consumed' in invalid['proposal_validation']['errors'][0]
 wrong_mode=_run(root,'proposal','--mode','work','--section','main','--target-dir','source',
                 '--context-id',context_id,stdin=json.dumps({'answer':'none','edits':[]}))
 assert wrong_mode.returncode==2 and 'mode or pipeline scope differs' in json.loads(wrong_mode.stdout)['error']
 assert (source/'main.tex').read_text()==before


def test_staged_workflow_stops_at_proposal_and_never_renders_source_directly():
 workflow=Path('.claude/workflows/project-staged.js').read_text()
 assert 'schema: AUTHOR_REPORT' in workflow
 assert 'writing_workspace.py proposal' in workflow
 assert 'args.applyProposal=true' in workflow
 assert 'writing_workspace.py apply' in workflow and '--accept' in workflow
 assert 'scripts/render_manuscript.py' not in workflow
 assert "authored: !!(application && application.ok && application.status === 'APPLIED')" in workflow
 assert "compiled: !!(compiled && compiled.ok)" in workflow
 assert 'proposal_receipt: proposed' in workflow and 'compile_result: compiled' in workflow
 assert "proposal awaits author acceptance" in workflow


def test_project_pipeline_propagates_proposal_pending_and_requires_explicit_apply_authorization():
 pipeline=Path('.claude/workflows/project-pipeline.js').read_text()
 assert 'const APPLY_PROPOSAL = A.applyProposal === true' in pipeline
 assert 'applyProposal: APPLY_PROPOSAL' in pipeline
 assert "return stop('proposal-review'" in pipeline
 assert 'proposal_pending: true' in pipeline
 assert 'proposal_turn_id: stagedBuild.proposal_turn_id' in pipeline
 assert "if (!stagedBuild.validated || !stagedBuild.compiled)" in pipeline
 assert "accepted project-staged proposal applied, validated and compiled" in pipeline
 assert 'staged.welded' not in pipeline
 child=pipeline.index("scriptPath: WORKFLOWS_DIR + '/project-staged.js'")
 pending=pipeline.index("return stop('proposal-review'")
 materialize=pipeline.index("phase('Materialize')")
 converge=pipeline.index("phase('Converge')")
 assert child < pending < materialize < converge


def test_project_pipeline_does_not_infer_authorization_from_note_or_manifest():
 pipeline=Path('.claude/workflows/project-pipeline.js').read_text()
 call=pipeline[pipeline.index("stagedBuild = await workflow"):pipeline.index("if (!stagedBuild ||")]
 assert 'applyProposal: APPLY_PROPOSAL' in call
 assert 'applyProposal: true' not in call
 assert 'note: NOTE' in call and 'manifest: MANIFEST' in call
 assert "args.applyProposal - true => explicit authorization" in pipeline
