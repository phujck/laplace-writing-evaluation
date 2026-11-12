"""Plan-issued derived build targets and recorded output inspection.

Current manuscript selection remains in manuscript_source. This composition
admits only the storyboard's declared derived root, and retains that exact
issued identity through the existing compiler and saved-output reader.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import os
from urllib.parse import urlencode

SCHEMA = "laplace.build-target/1"


class TargetRefused(ValueError):
    def __init__(self, message, project, *, reason_code='INVALID_TARGET', next_reads=None):
        super().__init__(message)
        self.details = {"code":"BUILD_TARGET_CHANGED_OR_UNAVAILABLE", "project":project,'reason_code':reason_code,
            "next_reads":next_reads or [read_handle(project)],
            "recovery":"Inspect the current declared derived target and retained output. No manuscript target was substituted."}


def error_details(error):
    for _ in range(8):
        if isinstance(error,TargetRefused):
            return dict(error.details)
        if error is None:
            break
        error = error.__cause__ or error.__context__
    return {}


def target_schema():
    fields = {key:{"type":"string","minLength":1} for key in (
        "project","root","plan_path","plan_revision","selection_identity","input_revision")}
    derived = {"type":"object", "required":["schema_version","kind",*fields],
        "properties":{"schema_version":{"const":SCHEMA},"kind":{"const":"derived"},**fields},
        "additionalProperties":False}
    from laplace.manuscript import publication_editions
    return {'oneOf':[derived,candidate_target_schema(),publication_editions.target_schema()]}


def candidate_target_schema():
    from laplace.manuscript.template_contracts import REF
    fields={key:{'type':'string','minLength':1} for key in ('project','root','selection_identity','input_revision')}
    for key in ('selection_identity','input_revision'):fields[key]={'type':'string','pattern':'^sha256:[0-9a-f]{64}$'}
    return {'type':'object','required':['schema_version','kind','candidate_ref',*fields],
        'properties':{'schema_version':{'const':SCHEMA},'kind':{'const':'candidate'},'candidate_ref':REF,**fields},
        'additionalProperties':False}


def candidate_target(project, ref, proposal, root):
    """Pure identity projection; inspection never creates or repairs a stage."""
    from laplace.manuscript import document_templates
    from laplace.pipeline import pathsafe
    from jsonschema import Draft202012Validator
    from laplace.manuscript.template_contracts import REF
    if next(Draft202012Validator(REF).iter_errors(ref),None) or document_templates.digest(proposal)!=ref['version']:
        raise TargetRefused('Candidate staging needs its exact immutable source proposal.',project)
    closure=proposal['declaration_closure'];source=proposal['selected_source'];relative=Path(source['root'])
    if (proposal['project']!=project or closure['project']!=project or closure['root']!=source['root']
            or relative.is_absolute() or '..' in relative.parts or relative.suffix.lower()!='.tex'):
        raise TargetRefused('The candidate closure and original selected root disagree.',project)
    cache=Path('.laplace-cache/writing-style')/pathsafe.encode_sid_for_path(project)/'candidates'/ref['id']/ref['version'].split(':')[1]
    return {'schema_version':SCHEMA,'kind':'candidate','project':project,'candidate_ref':dict(ref),
        'root':(cache/'tree'/relative).as_posix(),'selection_identity':source['selection_identity'],
        'input_revision':closure['input_revision']}


def _candidate_home(target, proposal, root):
    path=root/target['root']
    for _ in Path(proposal['selected_source']['root']).parts:path=path.parent
    return path


def _private_path(root, relative):
    path=root/relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts or not path.resolve().is_relative_to(root):
        raise ValueError('Candidate cache path escapes its exact owner.')
    current=path
    while current!=root:
        if current.is_symlink():raise ValueError('Candidate cache contains a symlink; no canonical link is writable.')
        current=current.parent
    return path


def candidate_stage_lock_path(target, proposal, root):
    """Stable lock beside the disposable version directory, never inside it."""
    directory=_candidate_home(target,proposal,Path(root).resolve()).parent
    return _private_path(Path(root).resolve(),directory.with_name(directory.name+'.stage.lock').relative_to(root))


#: Owned graphics a compile-directory TeX member names through ``..`` are materialized here, inside the
#: staged compile directory, so the candidate compiler keeps openin_any=p (which refuses ``..`` names).
STAGED_ASSET_DIR='laplace-closure-assets'
#: Byte-exact originals of staged TeX members whose graphic names were rewritten, outside the compile tree.
STAGED_ORIGINALS='laplace-closure-originals'


def staged_asset_plan(proposal):
    """The supported owned asset closure of a candidate stage: graphic members outside the compile directory
    and the ``..``-free alias each is compiled under. A pure function of the immutable proposal."""
    import posixpath
    compile_dir=posixpath.dirname(proposal['selected_source']['root'])
    plan={}
    for member in proposal['declaration_closure']['members']:
        path=member['path']
        if 'graphic' in member['roles'] and not path.startswith(compile_dir+'/'):
            suffix=posixpath.splitext(path)[1]
            plan[path]=STAGED_ASSET_DIR+'/'+hashlib.sha256(path.encode()).hexdigest()[:16]+suffix
    return compile_dir,plan


def staged_text(text, compile_dir, plan):
    """The staged TeX of one member: each \\includegraphics naming a planned asset through ``..`` from the
    compile directory reads its alias instead; every other byte is unchanged."""
    import posixpath
    from laplace.manuscript import tex_dependencies
    def replace(match):
        argument=match.group(1).strip()
        if '..' not in argument.split('/'):return match.group(0)
        name=posixpath.normpath(posixpath.join(compile_dir,argument))
        stem=posixpath.splitext(argument)[1]==''
        hit=next((path for path in plan if path==name or stem and posixpath.splitext(path)[0]==name),None)
        if hit is None:return match.group(0)
        alias=plan[hit] if not stem else posixpath.splitext(plan[hit])[0]
        start,end=match.span(1)
        return match.group(0)[:start-match.start()]+alias+match.group(0)[end-match.start():]
    return tex_dependencies._GRAPHIC_INPUT.sub(replace,text)


def stage_candidate(project, ref, proposal, root):
    """Explicit preparation only: private copies of the proposed local closure."""
    from laplace.manuscript import tex_dependencies
    from filelock import FileLock
    import os
    root=Path(root).resolve();target=candidate_target(project,ref,proposal,root)
    changed=tex_dependencies.closure_changes(proposal['declaration_closure'],root)
    if changed:raise TargetRefused('CHANGED_INPUT: candidate local basis changed: '+', '.join(changed[:12]),project)
    home=_candidate_home(target,proposal,root);relative=home.relative_to(root).as_posix()
    _private_path(root,relative);home.parent.parent.mkdir(parents=True,exist_ok=True)
    edits={row['file']:row['after'] for row in proposal['source_edits']}
    compile_dir,plan=staged_asset_plan(proposal)
    def publish(path,data=None,canonical=None,expected=None):
        """One private read-only file, exact or refused; ``expected`` defaults to the bytes' own identity."""
        path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.stage-tmp')
        if temporary.exists() or temporary.is_symlink():raise TargetRefused('An unproved staging temporary already exists.',project)
        try:
            with temporary.open('xb') as output:
                if data is not None:output.write(data)
                else:
                    with (root/canonical).open('rb') as source:
                        for block in iter(lambda:source.read(1024*1024),b''):output.write(block)
            if expected is not None and tex_dependencies._file_identity(temporary)[0]!=expected:
                raise TargetRefused('CHANGED_INPUT: exact dependency bytes changed during private copy.',project)
            temporary.chmod(0o444);os.replace(temporary,path)
        finally:
            if temporary.is_file():temporary.unlink()
    with FileLock(str(candidate_stage_lock_path(target,proposal,root))):
        home.mkdir(parents=True,exist_ok=True)
        for member in proposal['declaration_closure']['members']:
            path=_private_path(root,(home.relative_to(root)/member['path']).as_posix())
            text=edits.get(member['path'],edits.get(member['canonical_path']))
            if plan and Path(member['path']).suffix.lower() in tex_dependencies._OVERLAY_TEXT_SUFFIXES:
                original=_private_path(root,(home.relative_to(root)/STAGED_ORIGINALS/member['path']).as_posix())
                if not (original.is_file() and tex_dependencies._file_identity(original)[0]==member['content_revision']):
                    publish(original,text.encode() if text is not None else None,member['canonical_path'],member['content_revision'])
                staged=staged_text(original.read_text(encoding='utf-8'),compile_dir,plan).encode()
                if not (path.is_file() and path.read_bytes()==staged):
                    if path.exists():path.chmod(0o644);path.unlink()
                    publish(path,staged)
                continue
            if path.is_file() and tex_dependencies._file_identity(path)[0]==member['content_revision']:continue
            publish(path,text.encode() if text is not None else None,member['canonical_path'],member['content_revision'])
        for member_path,alias in plan.items():
            member=next(row for row in proposal['declaration_closure']['members'] if row['path']==member_path)
            path=_private_path(root,(home.relative_to(root)/compile_dir/alias).as_posix())
            if not (path.is_file() and tex_dependencies._file_identity(path)[0]==member['content_revision']):
                publish(path,None,member['canonical_path'],member['content_revision'])
        if tex_dependencies.closure_changes(proposal['declaration_closure'],root):
            raise TargetRefused('CHANGED_INPUT: local basis changed before candidate stage completed.',project)
    verify_candidate_stage(target,project,root,proposal=proposal)
    return target


def verify_candidate_stage(target, project, root, *, proposal=None):
    from laplace.manuscript import tex_dependencies
    from laplace.manuscript import document_templates
    root=Path(root).resolve()
    proposal=proposal or document_templates.candidate(project,target['candidate_ref'],root)['proposal']
    if target!=candidate_target(project,target['candidate_ref'],proposal,root):
        raise TargetRefused('The candidate build target differs from its sealed proposal.',project)
    home=_candidate_home(target,proposal,root)
    compile_dir,plan=staged_asset_plan(proposal)
    unavailable=lambda:TargetRefused('Exact candidate stage is unavailable or changed; explicitly prepare/build it again.',project,reason_code='STAGE_UNAVAILABLE')
    exact=lambda path,pin:path.is_file() and tex_dependencies._file_identity(path)[0]==pin
    for member in proposal['declaration_closure']['members']:
        path=_private_path(root,(home.relative_to(root)/member['path']).as_posix())
        if plan and Path(member['path']).suffix.lower() in tex_dependencies._OVERLAY_TEXT_SUFFIXES:
            # the compiled copy is exactly the asset rewrite of a pinned original, both derived from the proposal
            original=_private_path(root,(home.relative_to(root)/STAGED_ORIGINALS/member['path']).as_posix())
            if (not exact(original,member['content_revision']) or not path.is_file()
                    or path.read_bytes()!=staged_text(original.read_text(encoding='utf-8'),compile_dir,plan).encode()):
                raise unavailable()
        elif not exact(path,member['content_revision']):
            raise unavailable()
    for member_path,alias in plan.items():
        member=next(row for row in proposal['declaration_closure']['members'] if row['path']==member_path)
        if not exact(_private_path(root,(home.relative_to(root)/compile_dir/alias).as_posix()),member['content_revision']):
            raise unavailable()
    return root/target['root']


def ensure_candidate_stage(target, project, root):
    from laplace.manuscript import document_templates
    proposal=document_templates.candidate(project,target['candidate_ref'],root)['proposal']
    if candidate_target(project,target['candidate_ref'],proposal,root)!=target:
        raise TargetRefused('The supplied candidate target was not issued by this owner.',project)
    return stage_candidate(project,target['candidate_ref'],proposal,root)


def compiler_environment(root_tex, job, root):
    """Private candidate search/output roots; installed TeX remains the toolchain."""
    from laplace.manuscript import document_templates
    proposal=document_templates.candidate(job['project'],job['build_target']['candidate_ref'],root)['proposal']
    home=_candidate_home(job['build_target'],proposal,Path(root).resolve())
    env=dict(os.environ)
    for key in ('TEXINPUTS','BIBINPUTS','BSTINPUTS'):env[key]=str(home)+'//'+os.pathsep
    env.update(openin_any='p',openout_any='p',shell_escape='f',TEXMFOUTPUT=str(root_tex.parent))
    for key,subdir in [('TEXMFVAR','var'),('TEXMFCONFIG','config'),('TEXMFCACHE','cache')]:env[key]=str(home.parent/('.texmf-'+subdir))
    return env


def _installed_roots():
    """Observe declared TeX installation paths, never classify arbitrary home data."""
    from laplace.manuscript import projection_viewer as compiler
    roots={Path(value).resolve() for value in ('/usr/share/texlive','/usr/share/texmf','/usr/share/fonts','/etc/texmf','/var/lib/texmf') if Path(value).is_dir()}
    drivers=[value for value in (compiler._latexmk_bin(),compiler._pdflatex_bin(),compiler._bibtex_bin()) if value]
    kpse=shutil.which('kpsewhich')
    for value in drivers:
        path=Path(value).resolve()
        for parent in path.parents:
            if parent.name.lower() in {'texlive','texmf-dist','texmf','miktex'}:roots.add(parent)
        sibling=path.parent/('kpsewhich.exe' if os.name=='nt' else 'kpsewhich')
        if sibling.is_file():kpse=str(sibling)
    if kpse:
        for name in ('TEXMFROOT','TEXMFDIST','TEXMFLOCAL','TEXMFVAR','TEXMFCONFIG','TEXMFHOME'):
            try:
                result=subprocess.run([kpse,'-var-value='+name],capture_output=True,text=True,timeout=3)
                value=Path(result.stdout.strip()).expanduser()
                if result.returncode==0 and result.stdout.strip() and value.is_absolute() and value.is_dir():roots.add(value.resolve())
            except (OSError,subprocess.TimeoutExpired):pass
    from laplace.manuscript import tex_dependencies
    identities=[]
    for value in drivers:
        path=Path(value).resolve()
        identities.append({'path':str(path),'content_revision':tex_dependencies._file_identity(path)[0] if path.is_file() else None})
    return roots,identities


def observe_candidate_build(root_tex, job, row, root):
    """Observe one actual private build before its root mutex is released."""
    from laplace.manuscript import document_templates
    from laplace.representation import writing_bodies as bodies
    from laplace.manuscript import tex_dependencies
    root=Path(root).resolve();ref=job['build_target']['candidate_ref'];proposal=document_templates.candidate(job['project'],ref,root)['proposal']
    home=_candidate_home(job['build_target'],proposal,root)
    closure=proposal['declaration_closure'];expected={member['path']:member for member in closure['members']}
    # The staged asset closure (staged_asset_plan): a rewritten TeX member is expected at the exact rewrite of
    # its pinned original, and each alias at its asset member's pin; nothing else is admitted.
    compile_dir,plan=staged_asset_plan(proposal);pins={name:member['content_revision'] for name,member in expected.items()}
    for name,member in expected.items():
        if plan and Path(name).suffix.lower() in tex_dependencies._OVERLAY_TEXT_SUFFIXES:
            original=home/STAGED_ORIGINALS/name
            if original.is_file() and tex_dependencies._file_identity(original)[0]==member['content_revision']:
                pins[name]='sha256:'+hashlib.sha256(staged_text(original.read_text(encoding='utf-8'),compile_dir,plan).encode()).hexdigest()
            else:pins[name]=None
    for name,alias in plan.items():
        pins[compile_dir+'/'+alias]=expected[name]['content_revision']
    generated={root/name for name in (row.get('outputs') or {}).get('generated',[])}
    recorder=root_tex.with_suffix('.fls');inputs=[];outputs=[];issues=[]
    if recorder.is_file():
        for line in recorder.read_text(encoding='utf-8',errors='replace').splitlines():
            if line.startswith(('INPUT ','OUTPUT ')):
                kind,name=line.split(' ',1);path=Path(name.strip().strip('"'))
                path=(root_tex.parent/path).resolve() if not path.is_absolute() else path.resolve()
                (inputs if kind=='INPUT' else outputs).append(path)
    elif row.get('ok'):issues.append({'code':'RECORDER_UNAVAILABLE'})
    installed_roots,drivers=_installed_roots();local=[];installed=[]
    generated.update(outputs)
    for path in sorted(set(inputs)):
        if not path.is_file():issues.append({'code':'RECORDED_INPUT_MISSING','path':str(path)});continue
        if path.is_relative_to(home):
            name=path.relative_to(home).as_posix()
            auxiliary=path.suffix.lower() in {'.aux','.bbl','.bcf','.toc','.out','.lof','.lot','.nav','.snm','.vrb','.idx','.ind','.ilg','.acr','.acn','.alg','.glg','.glo','.gls'} or path.name.endswith('.run.xml')
            if path in generated and auxiliary and name not in pins:continue
            if name not in pins:issues.append({'code':'UNBOUND_PRIVATE_INPUT','path':name});continue
            pin,size,_=tex_dependencies._file_identity(path)
            if pin!=pins[name]:issues.append({'code':'CHANGED_PRIVATE_INPUT','path':name});continue
            data=path.read_bytes();handle=bodies.store(root).put(data)
            if 'sha256:'+hashlib.sha256(data).hexdigest()!=pin:issues.append({'code':'INPUT_CHANGED_DURING_RETENTION','path':name});continue
            local.append({'path':name,'content_revision':pin,'bytes':size,'content_handle':handle})
        elif path.is_relative_to(root):issues.append({'code':'CANONICAL_INPUT_FALLBACK','path':path.relative_to(root).as_posix()})
        elif any(path.is_relative_to(directory) for directory in installed_roots):
            pin,size,_=tex_dependencies._file_identity(path);installed.append({'path':str(path),'content_revision':pin,'bytes':size})
        else:issues.append({'code':'UNBOUND_EXTERNAL_INPUT','path':str(path)})
    # Every declared private member still matches; recorder coverage is separate
    # from static reachability and does not claim unexecuted branches were run.
    for name,pin in pins.items():
        path=home/name
        if pin is None or not path.is_file() or tex_dependencies._file_identity(path)[0]!=pin:
            issues.append({'code':'DECLARED_STAGE_INPUT_CHANGED','path':name})
    observation={'schema_version':'laplace.template-build-observation/1','project':job['project'],'candidate_ref':ref,
        'build_job':job,'state':row.get('state'),'ok':bool(row.get('ok')),'declared_input_revision':job['input_revision'],
        'observed_local_inputs':local,'installed_inputs':installed,'toolchain':{'drivers':drivers,'invocations':row.get('compiler_invocations',[])},
        'cleanup_unproved':bool(row.get('cleanup_unproved')),'diagnostics':issues,'log_tail':str(row.get('log_tail') or '')[-16000:],
        'finished':row.get('finished'),'output':None}
    observation['observed_input_revision']=tex_dependencies._closure_digest({'local':local,'installed':installed,'drivers':drivers,'invocations':row.get('compiler_invocations',[])})
    pdf=root_tex.with_suffix('.pdf')
    if row.get('ok') and not issues and not observation['cleanup_unproved']:
        expected_pdf=(row.get('outputs') or {}).get('files',{}).get(pdf.relative_to(root).as_posix())
        if not expected_pdf or 'sha256:'+expected_pdf.removeprefix('sha256:')!=tex_dependencies._file_identity(pdf)[0]:
            observation['diagnostics'].append({'code':'PDF_OUTPUT_UNPROVED'})
        else:
            pin='sha256:'+expected_pdf.removeprefix('sha256:');directory=home.parent/'outputs'/job['id'];directory.mkdir(parents=True,exist_ok=True)
            output=_private_path(root,(directory.relative_to(root)/(pin.split(':')[1]+'.pdf')).as_posix())
            if not output.exists():shutil.copyfile(pdf,output);output.chmod(0o444)
            if tex_dependencies._file_identity(output)[0]!=pin:raise TargetRefused('Immutable candidate PDF cache bytes changed.',job['project'])
            observation['output']={'file':output.relative_to(root).as_posix(),'content_revision':pin}
    return observation


def retain_candidate_observation(observation, root):
    """One immutable terminal ART at the existing artifact/CAS owner."""
    from laplace.projects import artifacts
    from laplace.writing import records
    root=Path(root).resolve();project=observation['project'];job=observation['build_job'];ref=observation['candidate_ref']
    index=records.index(root);existing=getattr(index,'template_build_by_job',{}).get((project,job['id']))
    if existing:
        receipt=records.selected_journal_fields(project,existing['id'],root,fields=['record','after','sha256'])
        if json.loads(receipt['after'])!=observation:raise TargetRefused('Exact terminal build observation differs from its retained ART.',project)
        saved=existing
    else:
        saved=artifacts.store(root,project,{'scope':'project','path':'work/template-builds/'+job['id']+'.json',
            'before':None,'content':json.dumps(observation,ensure_ascii=False,indent=2)+'\n','reason':'Exact immutable candidate build observation.'},
            owner_metadata={'path':'work/template-builds/'+job['id']+'.json','subjects':{},'reserved_ids':[],
                'template_build':{'candidate_id':ref['id'],'candidate_version':ref['version'],'build_job_id':job['id'],
                    'state':observation['state'],'ok':observation['ok'] and not observation['diagnostics'] and bool(observation['output'])}})
    preview=({'schema_version':'laplace.template-preview-ref/1','build_job':job,'build_receipt_id':saved['id'],
        'observed_input_revision':observation['observed_input_revision'],'output':observation['output']}
        if observation['ok'] and observation['output'] and not observation['diagnostics'] else None)
    return {'build_receipt_id':saved['id'],'preview_ref':preview,'preview_diagnostics':observation['diagnostics']}


def inspect_preview(project, ref, preview_ref, root):
    from laplace.representation.atlas_bridge import BlobMissing, BlobHashMismatch
    from laplace.writing import records
    from laplace.representation import writing_bodies as bodies
    from laplace.manuscript import build_jobs
    from laplace.manuscript.template_contracts import preview_schema
    from jsonschema import Draft202012Validator
    root=Path(root).resolve()
    if next(Draft202012Validator(preview_schema()).iter_errors(preview_ref),None):
        raise TargetRefused('Select the exact reviewed build/output proof.',project)
    job=build_jobs.decode(preview_ref['build_job'],project)
    if job['target_kind']!='candidate' or job['build_target']['candidate_ref']!=ref:
        raise TargetRefused('The reviewed build belongs to a different candidate.',project)
    row=records.selected_journal_fields(project,preview_ref['build_receipt_id'],root,fields=['record','after','sha256','reader_metadata'])
    metadata=(row.get('reader_metadata') or {}).get('template_build') or {}
    if (row.get('record')!='writing-artifact' or hashlib.sha256(row['after'].encode()).hexdigest()!=str(row['sha256']).removeprefix('sha256:')
            or metadata.get('candidate_id')!=ref['id'] or metadata.get('candidate_version')!=ref['version']
            or metadata.get('build_job_id')!=job['id'] or metadata.get('ok') is not True):
        raise TargetRefused('The immutable terminal build ART is unproved.',project)
    receipt=json.loads(row['after'])
    if (receipt.get('schema_version')!='laplace.template-build-observation/1' or receipt.get('project')!=project
            or receipt.get('build_job')!=job or receipt.get('candidate_ref')!=ref or not receipt.get('ok') or receipt.get('state')!='done'
            or receipt.get('diagnostics') or receipt.get('cleanup_unproved') or receipt.get('output')!=preview_ref['output']
            or receipt.get('observed_input_revision')!=preview_ref['observed_input_revision']):
        raise TargetRefused('The reviewed proof differs from its exact successful terminal observation.',project)
    for member in receipt['observed_local_inputs']:
        try:data=bodies.store(root).get(member['content_handle'])
        except (BlobMissing,BlobHashMismatch,OSError,ValueError) as error:
            raise TargetRefused('Retained observed local input bytes are unavailable; rebuild an exact preview.',project) from error
        if 'sha256:'+hashlib.sha256(data).hexdigest()!=member['content_revision']:
            raise TargetRefused('Retained observed local input bytes are unavailable.',project)
    from laplace.manuscript import document_templates
    proposal=document_templates.candidate(project,ref,root)['proposal']
    target=candidate_target(project,ref,proposal,root)
    if target!=job['build_target']:raise TargetRefused('The terminal proof crosses its original candidate target.',project)
    expected=(_candidate_home(target,proposal,root).parent/'outputs'/job['id']/(preview_ref['output']['content_revision'].split(':')[1]+'.pdf')).relative_to(root).as_posix()
    if preview_ref['output']['file']!=expected:raise TargetRefused('The reviewed PDF path was not issued by the candidate output owner.',project)
    path=_private_path(root,expected)
    from laplace.manuscript import tex_dependencies
    if not path.is_file() or tex_dependencies._file_identity(path)[0]!=preview_ref['output']['content_revision']:
        raise TargetRefused('The exact reviewed PDF is unavailable; no newer output was substituted.',project)
    return {'path':path,'receipt':receipt,'observed_input_revision':receipt['observed_input_revision'],'output':receipt['output'],
        'current_input_changes':verify_preview_inputs(project,ref,receipt,root,proposal=proposal)}


def verify_preview_inputs(project, ref, receipt, root, *, proposal=None):
    """Current Apply authority, separate from immutable historical PDF validity."""
    from laplace.manuscript import tex_dependencies
    from laplace.manuscript import document_templates
    proposal=proposal or document_templates.candidate(project,ref,root)['proposal']
    return tex_dependencies.closure_changes(proposal['declaration_closure'],root,
        ignore_files=[row['file'] for row in proposal['source_edits']])


def latest_preview(project, ref, root):
    from laplace.writing import records
    index=records.index(root);rows=getattr(index,'template_builds_by_candidate',{}).get((project,ref['id'],ref['version']),[])
    if not rows:return {'state':'UNBUILT','preview_ref':None}
    row=rows[-1];receipt=records.selected_journal_fields(project,row['id'],root,fields=['after'])
    value=json.loads(receipt['after']);preview={'schema_version':'laplace.template-preview-ref/1','build_job':value['build_job'],
        'build_receipt_id':row['id'],'observed_input_revision':value['observed_input_revision'],'output':value.get('output')}
    if not value['ok'] or not value.get('output'):return {'state':value['state'],'preview_ref':None,'diagnostics':value['diagnostics']}
    try:inspect_preview(project,ref,preview,root)
    except (ValueError,OSError) as error:return {'state':'UNAVAILABLE','preview_ref':None,'reason':str(error)}
    return {'state':'done','preview_ref':preview}


def candidate_job_status(job, project, root):
    """Exact terminal BLD history remains readable after a newer build starts."""
    from laplace.writing import records
    from laplace.manuscript import build_jobs
    row=getattr(records.index(root),'template_build_by_job',{}).get((project,job['id']))
    if not row:raise build_jobs.JobRefused('This exact terminal candidate build observation is unavailable.',project)
    retained=records.selected_journal_fields(project,row['id'],root,fields=['after'])
    value=json.loads(retained['after'])
    if value['build_job']!=job:raise build_jobs.JobRefused('The retained terminal ART belongs to a different job.',project)
    result={'project':project,'corpus':project,'build_job':job,'build_target':job['build_target'],
        'state':value['state'],'ok':value['ok'],'running':False,'fresh':False,'historical':True,
        'cleanup_unproved':bool(value.get('cleanup_unproved')),
        'log_tail':value['log_tail'],'build_receipt_id':row['id'],'preview_ref':None,
        'job_status_read':build_jobs.handles(job)['job_status_read'],
        'cancellation':{'available':False,'reason':'This exact build is terminal; a newer job was not selected.'}}
    if value.get('output') and not value.get('diagnostics'):
        preview={'schema_version':'laplace.template-preview-ref/1','build_job':job,'build_receipt_id':row['id'],
            'observed_input_revision':value['observed_input_revision'],'output':value['output']}
        try:inspect_preview(project,job['build_target']['candidate_ref'],preview,root)
        except (OSError,ValueError) as error:result['preview_error']=str(error)
        else:result['preview_ref']=preview
    return result


def candidate_status(project, target, root):
    """Pure status, including an explicitly evicted or never prepared stage."""
    from laplace.manuscript import projection_viewer as compiler
    from laplace.manuscript import document_templates, build_jobs
    root=Path(root).resolve()
    proposal=document_templates.candidate(project,target['candidate_ref'],root)['proposal']
    if target!=candidate_target(project,target['candidate_ref'],proposal,root):
        raise TargetRefused('The candidate status target differs from its sealed proposal.',project)
    try:path=verify_candidate_stage(target,project,root,proposal=proposal)
    except TargetRefused as error:
        if error.details.get('reason_code')!='STAGE_UNAVAILABLE':raise
        return {'project':project,'corpus':project,'build_target':target,'state':'idle','stage_state':'NOT_PREPARED',
            'running':False,'ok':None,'fresh':False,'present':False,'reason':str(error),**handles(project,target)}
    current=compiler._read_recompile_status(path).get('build_job')
    if current and current.get('build_target')==target:return build_jobs.status(current,project,root)
    return compiler.recompile_status(target['root'],repo_root=root,corpus=project,
        _scope={'root':path,'source':None,'corpus':project,'compile_root':target['root']},build_target=target)


def read_handle(project):
    return {"operation":"document", "payload":{"target_kind":"derived"},
        "http":{"method":"GET","url":"/authoring/document?"+urlencode({
            "project":project,"target_kind":"derived"})}}


def handles(project,target):
    encoded = json.dumps(target,sort_keys=True,separators=(',',':'))
    return {
        'build_action':{'operation':'build','payload':{'build_target':target},
            'http':{'method':'POST','route':'/authoring/build'},'project':project},
        'status_read':{'operation':'build_status','payload':{'build_target':target},
            'http':{'method':'GET','url':'/authoring/build?'+urlencode({'project':project,'build_target':encoded})}},
    }


def _target_path(target, root, *, project=None):
    from jsonschema import Draft202012Validator
    issue = next(Draft202012Validator(target_schema()).iter_errors(target),None)
    if issue:
        raise TargetRefused("The build target does not match its owner-issued contract: "+issue.message,
                            project or (target.get('project','') if isinstance(target,dict) else ''))
    path = (root/target['root']).resolve()
    if (Path(target['root']).is_absolute() or '..' in Path(target['root']).parts
            or not path.is_relative_to(root) or path.suffix.lower()!='.tex'):
        raise TargetRefused("The issued target root is outside this workspace or is not exact TeX.",project or target['project'])
    return path


def issue(project, root):
    from laplace.manuscript import storyboard
    from laplace.manuscript import bindings
    root = Path(root).resolve()
    loaded = storyboard._load_plan(project,root)
    if loaded is None:
        from laplace.pipeline import registry
        declared=registry.plan_path_for(project,root)
        if declared is not None and declared.is_file():
            raise TargetRefused('The declared storyboard plan is unreadable; inspect it before deriving output.',project)
        raise TargetRefused("This project has no declared derived storyboard output.",project,reason_code='NOT_CONFIGURED')
    plan_path,_ = loaded
    raw = plan_path.read_bytes()
    plan = json.loads(raw)
    directory = (plan.get('meta') or {}).get('target_dir')
    if not isinstance(directory,str) or not directory.strip():
        raise TargetRefused("The storyboard has no exact declared derived output directory.",project,reason_code='NOT_CONFIGURED')
    target_root = (root/directory/'main.tex').resolve()
    if not target_root.is_relative_to(root):
        raise TargetRefused('The declared derived output escapes this workspace.',project)
    if not (plan.get('sections') or plan.get('appendices')):
        raise TargetRefused('No reader-plan sections declare a derived document yet.',project,reason_code='NOT_CONFIGURED')
    if target_root.is_relative_to(root) and not target_root.is_file():
        raise TargetRefused('The declared reader-plan output has not been prepared yet.',project,reason_code='NOT_PREPARED')
    refusal = storyboard._derived_target_refusal(project,target_root,root,plan=plan)
    if refusal:
        raise TargetRefused(refusal.get('error') or 'The derived target is not proved.',project)
    source,_ = bindings.selected_tree(project,root)
    from laplace.manuscript import tex_dependencies
    # Stable declared-input admission is distinct from the build's actual
    # recorder receipt. Discovering a new .fls after the first build is not an
    # authored input change and must not make every first build falsely stale.
    inputs = tex_dependencies.snapshot(target_root,root,use_recorder=False)
    return {'schema_version':SCHEMA,'kind':'derived','project':project,
        'root':target_root.relative_to(root).as_posix(),
        'plan_path':plan_path.relative_to(root).as_posix(),
        'plan_revision':'sha256:'+hashlib.sha256(raw).hexdigest(),
        'selection_identity':source['selection_identity'],
        'input_revision':'sha256:'+hashlib.sha256(json.dumps(inputs,sort_keys=True,separators=(',',':')).encode()).hexdigest()}


def resolve(target, project, root):
    root = Path(root).resolve()
    path = _target_path(target,root,project=project)
    if target['kind']=='candidate':
        return verify_candidate_stage(target,project,root)
    if target['kind']=='publication-edition':
        from laplace.manuscript import publication_editions
        return publication_editions.resolve(target,project,root)
    if target['project']!=project or target!=issue(project,root):
        raise TargetRefused("The declared derived plan/source-selection basis changed. Inspect it before building.",project)
    return path


def decode(value, *, project=''):
    if value in (None,''):
        return None
    if isinstance(value,str):
        try:
            value = json.loads(value)
        except (ValueError,UnicodeError) as error:
            raise TargetRefused("The build_target query must encode the exact issued object.",project) from error
    if not isinstance(value,dict):
        raise TargetRefused("build_target must be the exact issued object.",project)
    return value


def retained(status):
    value = (status or {}).get('last_successful_derived')
    if isinstance(value,dict):
        return value
    if (status or {}).get('ok') is True and isinstance((status or {}).get('build_target'),dict):
        return {key:status[key] for key in ('build_target','outputs','dependencies','finished') if key in status}
    return None


def saved_pdf(target, project, root, expected_content_revision, *, requested_file=None):
    """Read recorded output without adopting today's plan/selection as its basis."""
    from laplace.manuscript import projection_viewer
    root = Path(root).resolve()
    tex = _target_path(target,root,project=project)
    if target['project']!=project:
        raise TargetRefused("The saved output belongs to another project.",project)
    record = retained(projection_viewer._read_recompile_status(tex))
    pdf = tex.with_suffix('.pdf')
    if requested_file is not None and requested_file!=pdf.relative_to(root).as_posix():
        raise TargetRefused('The requested PDF path differs from its recorded derived output.',project)
    recorded = ((record or {}).get('outputs') or {}).get('files',{}).get(pdf.relative_to(root).as_posix())
    recorded = 'sha256:'+recorded.removeprefix('sha256:') if isinstance(recorded,str) else None
    if (not record or record.get('build_target')!=target or not recorded
            or expected_content_revision!=recorded):
        raise TargetRefused("The exact saved derived output receipt is unavailable; this URL was not rebound to another build.",project)
    if not pdf.is_file():
        raise TargetRefused("The recorded derived PDF is no longer retained at its exact output path.",project)
    data = pdf.read_bytes()
    if 'sha256:'+hashlib.sha256(data).hexdigest()!=recorded:
        raise TargetRefused("The derived PDF bytes changed after this output was recorded; the requested bytes were not served.",project)
    return data


def read(project, root, *, target_kind='derived'):
    root = Path(root).resolve()
    if target_kind=='publication-edition':
        from laplace.manuscript import publication_editions
        return publication_editions.read(project,root)
    base = {'schema_version':'laplace.derived-output/1','project':project,
        'target_kind':'derived','read_handle':read_handle(project)}
    try:
        return {**base,**output_view(project,root,issue(project,root))}
    except (ValueError,OSError) as error:
        return {**base,'status':'UNAVAILABLE','reason':str(error),**error_details(error)}


def output_view(project, root, target):
    """An issued target's current attempt, build/status actions and separately retained output."""
    from laplace.manuscript import projection_viewer
    root = Path(root).resolve()
    tex = root/target['root']
    status = projection_viewer.recompile_status(target['root'],repo_root=root,corpus=project,build_target=target)
    return {'build_target':target,'current_build':status,
        'status':'BUILDING' if status.get('running') else 'FAILED' if status.get('ok') is False else
                 'READY' if status.get('fresh') else 'STALE' if tex.with_suffix('.pdf').is_file() else 'UNBUILT',
        **handles(project,target),**recorded_view(project,root,tex,target,fresh=status.get('fresh') is True)}


def recorded_view(project, root, tex, target, *, fresh=False):
    """The last successful recorded output of this root and its exact PDF read; never rebound to target."""
    from laplace.manuscript import projection_viewer, tex_dependencies
    root = Path(root).resolve()
    record = retained(projection_viewer._read_recompile_status(tex))
    if not record:
        return {}
    old = record.get('build_target')
    pdf = tex.with_suffix('.pdf').relative_to(root).as_posix()
    output_digest = (record.get('outputs') or {}).get('files',{}).get(pdf)
    output_digest = 'sha256:'+output_digest.removeprefix('sha256:') if isinstance(output_digest,str) else None
    same_target = target is not None and old==target
    changed = tex_dependencies.changed(record.get('dependencies') or {},root)
    output_current = projection_viewer._build_output_currentness(tex,root,record.get('outputs'))
    pdf_current = (output_current['state'] in {'VERIFIED','CHANGED'}
                   and pdf not in output_current['changes'] and bool(output_digest))
    result = {'recorded_output':{'build_target':old,'content_revision':output_digest,
        'inputs_current':same_target and not changed,'output_current':pdf_current,
        'output_bundle_current':output_current['current'],
        'input_changes':changed,'target_basis_current':same_target,'finished':record.get('finished')}}
    if output_digest and pdf_current:
        url = '/projection/pdf?'+urlencode({'file':pdf,'corpus':project,
            'build_target':json.dumps(old,sort_keys=True,separators=(',',':')),
            'expected_content_revision':output_digest})
        result['pdf_read']={'http':{'method':'GET','url':url},'build_target':old,
            'content_revision':output_digest,'current':same_target and not changed and fresh}
    return result
