#!/usr/bin/env python3
"""Explicit offline wheel-installed Source publication example, using existing GPU deps.

Installs only the two supplied wheels into a new isolated output. No package
resolution, downloads, Main imports, private state or verifier substitutions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import traceback


def sha(path):
    with Path(path).open('rb') as stream:
        return 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--candidate-root',type=Path,required=True)
    parser.add_argument('--laplace-wheel',type=Path,required=True)
    parser.add_argument('--atlas-wheel',type=Path,required=True)
    parser.add_argument('--model-archive',type=Path,required=True,
                        help='Already-local public fast-bge-small-en-v1.5.tar.gz, never downloaded')
    parser.add_argument('--configure-runtime',action='store_true',required=True,
                        help='Explicitly declare this interpreter/version in the NEW fixture only')
    args=parser.parse_args()
    root=args.output.expanduser().absolute()
    if root.exists() or root.is_symlink() or any(p.is_symlink() for p in root.parents):
        parser.error('Output must be new, without symlink ancestors')
    if any((p/'.git').exists() for p in [root,*root.parents]):
        parser.error('Output must be outside source repositories')
    candidate=args.candidate_root.resolve(strict=True)
    wheels=[args.laplace_wheel.resolve(strict=True),args.atlas_wheel.resolve(strict=True)]
    model=args.model_archive.resolve(strict=True)
    if not all(p.is_file() for p in [*wheels,model]):
        parser.error('Explicit wheel/model inputs must be regular files')
    if not sys.flags.no_user_site:
        parser.error('Run with python -s (or the canonical runtime wrapper)')
    root.mkdir(parents=True)
    workspace=root/'workspace'
    target=workspace/'src'
    evidence=root/'evidence'
    evidence.mkdir()
    workspace.mkdir()
    keep={'PATH','LANG','LC_ALL','LD_LIBRARY_PATH','SYSTEMROOT','WINDIR','CUDA_VISIBLE_DEVICES'}
    environment={k:v for k,v in os.environ.items() if k in keep}
    for name in ['home','state','cache','config','tmp']:
        (root/name).mkdir()
    environment.update(HOME=str(root/'home'),XDG_STATE_HOME=str(root/'state'),
        XDG_CACHE_HOME=str(root/'cache'),XDG_CONFIG_HOME=str(root/'config'),TMPDIR=str(root/'tmp'),
        LAPLACE_STATE=str(root/'state'),LAPLACE_REPO_ROOT=str(workspace),
        LAPLACE_SESSION_WORKSPACES=str(root/'state/workspaces'),LAPLACE_PYTHON=sys.executable,
        LAPLACE_EMBED_THREADS='2',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
        PIP_CONFIG_FILE=os.devnull,PIP_DISABLE_PIP_VERSION_CHECK='1')
    os.environ.clear()
    os.environ.update(environment)
    sys.dont_write_bytecode=True
    # An explicit operator-requested local-wheel install, no resolver or network.
    command=[sys.executable,'-s','-B','-m','pip','install','--no-index','--no-deps',
             '--no-cache-dir','--disable-pip-version-check','--target',str(target),
             *map(str,wheels)]
    installed=subprocess.run(command,capture_output=True,text=True,env=environment)
    (evidence/'wheel-install.stdout.txt').write_text(installed.stdout)
    (evidence/'wheel-install.stderr.txt').write_text(installed.stderr)
    if installed.returncode:
        raise RuntimeError('Explicit local wheel install failed; see evidence')
    # The product's source-layout lifecycle coordinate is an explicit fixture input.
    # Package files came from wheels, not copied/imported from Main or a checkout.
    shutil.copyfile(candidate/'runtime_profiles.toml',workspace/'runtime_profiles.toml')
    # Configure the public NOT_CONFIGURED template, not the native guard or API.
    profile=workspace/'runtime_profiles.toml'
    template_sha=sha(profile)
    lines=profile.read_text().splitlines()
    lifecycle=False
    replaced=set()
    for index,line in enumerate(lines):
        if line.startswith('['):
            lifecycle=line.strip()=='[lifecycle]'
        if lifecycle:
            for key,value in [('python',sys.executable),('expected_python',platform.python_version())]:
                if line.partition('=')[0].strip()==key:
                    lines[index]=key+' = '+json.dumps(value)
                    replaced.add(key)
    assert replaced=={'python','expected_python'},'Missing lifecycle declaration fields'
    profile.write_text('\n'.join(lines)+'\n')
    (workspace/'profiles').mkdir()
    (workspace/'profiles/writing_sources.json').write_text('{"repositories":{"laplace":"."}}\n')
    shutil.copyfile(candidate/'examples/resources/visual_style.json',workspace/'profiles/visual_style.json')
    (workspace/'registry_projects.json').write_text('{"projects":[]}\n')
    destination=workspace/'models/fastembed/fast-bge-small-en-v1.5.tar.gz'
    destination.parent.mkdir(parents=True)
    shutil.copyfile(model,destination)
    assert sha(model)==sha(destination)
    def local_network_only(event,values):
        if event=='socket.connect':
            address=values[1]
            if not isinstance(address,tuple) or address[0] not in ('127.0.0.1','::1'):
                raise RuntimeError('Public example forbids remote network connections')
        if event=='socket.getaddrinfo' and values[0] not in ('127.0.0.1','::1'):
            raise RuntimeError('Public example forbids remote name resolution')
    sys.addaudithook(local_network_only)
    sys.path.insert(0,str(target))
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    os.chdir(workspace)
    from behaviour_domains.common import Recorder
    from behaviour_domains import source_kernel,source_publication
    import laplace,atlas
    for module in [laplace,atlas]:
        assert Path(module.__file__).resolve().is_relative_to(target),module.__file__
    rec=Recorder(root)
    rec.package_root=target
    rec.candidate_root=candidate
    rec.save('installed-bootstrap',{'wheels':[{'name':p.name,'sha256':sha(p)} for p in wheels],
        'example_sources':{name:sha(path) for name,path in {
            'runner':Path(__file__), 'source_kernel':Path(source_kernel.__file__),
            'source_publication':Path(source_publication.__file__)}.items()},
        'model_archive':{'name':model.name,'bytes':model.stat().st_size,'sha256':sha(model)},
        'profile_sha256':sha(workspace/'runtime_profiles.toml'),
        'profile_template_sha256':template_sha,
        'explicit_fixture_runtime':{'python':sys.executable,'expected_python':platform.python_version()},
        'package_root':str(target),'executable':sys.executable,
        'dependencies':'Existing runtime packages. No dependency install or network acquisition.',
        'layout':'Explicit wheel --target workspace/src and public fixture runtime declaration.'})
    groups={}
    try:
        groups['source_kernel']=source_kernel.run(workspace,rec)
        rec.save('group-source_kernel',groups['source_kernel'])
        groups['source_publication']=source_publication.run(workspace,rec)
        rec.save('group-source_publication',groups['source_publication'])
        status=('EXECUTED' if groups['source_publication']['status']=='EXECUTED'
                else groups['source_publication']['status'])
    except Exception as error:
        status='FAILED'
        groups['failure']={'type':type(error).__name__,'message':str(error),
                           'traceback':traceback.format_exc()}
    origins={name:{'path':str(Path(module.__file__).resolve()),
                   'sha256':sha(module.__file__)}
             for name,module in sys.modules.items()
             if (name in ('laplace','atlas') or name.startswith(('laplace.','atlas.')))
             and getattr(module,'__file__',None)}
    outside={name:value for name,value in origins.items()
             if not Path(value['path']).is_relative_to(target)}
    if outside:
        status='FAILED'
    rec.save('module-origins',origins)
    summary={'schema_version':'laplace.installed-public-source-publication-example/1',
        'status':status,'groups':groups,'outside_installed_package':outside,
        'generative_provider_inference':'NOT_RUN','private_state':'NOT_READ_OR_COPIED',
        'qualification':'Actual native Source publication and retained recovery over an authored '
                        'public base with real local CUDA vectors and an identity-metric fixture. '
                        'No model answer, private corpus, scientific-quality, full-world fold, '
                        'authored close or final-verifier substitution.'}
    rec.save('source-publication-summary',summary)
    print(json.dumps(summary,indent=2,default=str))
    return 0 if status=='EXECUTED' else (3 if status=='UNAVAILABLE_OPTIONAL' else 1)


if __name__=='__main__':
    raise SystemExit(main())
