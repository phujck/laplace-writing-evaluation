"""Full app with real sealed-reader input/admission/read owners; fake process only."""
"""Real workflow HTTP owner on a public synthetic root, with before-import containment.

Started by workflow_app.playwright.mjs. The server binds loopback only and starts
no provider. Source belongs to this checkout; every mutable root belongs to the
explicit evidence home. Reuses the existing runtime_guard provider/live-state fence.
"""
import importlib.machinery
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]
HOME = Path(os.environ['SEALED_READER_EVIDENCE_HOME']).resolve()
assert HOME.is_relative_to(Path('/tmp/laplace-programme-20261025/sealed-text-reader-consumer'))
HOME.mkdir(parents=True,exist_ok=False)
(HOME / 'tmp').mkdir(parents=True, exist_ok=True)
os.environ.update(TMPDIR=str(HOME / 'tmp'), TMP=str(HOME / 'tmp'), TEMP=str(HOME / 'tmp'))
assert not any(name == 'laplace' or name.startswith('laplace.') for name in sys.modules)
sys.path.insert(0, str(SOURCE / 'tests'))
import runtime_guard
runtime_guard.install()
runtime_guard.ARMED = True
refusals = []


class SelectedSource:
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('laplace', 'atlas') or fullname.startswith(('laplace.', 'atlas.')):
            spec = importlib.machinery.PathFinder.find_spec(fullname, path)
            if spec and spec.origin and spec.origin not in ('built-in', 'frozen'):
                assert Path(spec.origin).resolve().is_relative_to(SOURCE / 'src'), (fullname, spec.origin)
            return spec


sys.meta_path.insert(0, SelectedSource())


def fixture_writes(event, args):
    targets = []
    if event == 'open' and args and not isinstance(args[0], int):
        mode, flags = args[1], args[2]
        if (isinstance(mode, str) and any(c in mode for c in 'wax+')) or (isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT)):
            targets.append((args[0], None))
    elif event in ('os.remove', 'os.rmdir'):
        targets.append((args[0], args[1]))
    elif event == 'os.mkdir':
        targets.append((args[0], args[2]))
    elif event == 'os.rename':
        targets.extend(((args[0], args[2]), (args[1], args[3])))
    for target, dir_fd in targets:
        if not isinstance(target, (str, bytes, os.PathLike)):
            continue
        resolved = Path(os.fsdecode(target))
        if not resolved.is_absolute() and isinstance(dir_fd, int) and dir_fd >= 0:
            resolved = Path(os.readlink('/proc/self/fd/%d' % dir_fd)) / resolved
        resolved = resolved.resolve()
        if not resolved.is_relative_to(HOME) and resolved != Path('/dev/null'):
            refusals.append({'event': event, 'path': str(resolved)})
            raise PermissionError('workflow fixture write outside evidence home: ' + str(resolved))


sys.addaudithook(fixture_writes)
from laplace.core import checkout,bodies
assert checkout.source_tree().resolve()==SOURCE
root=Path(os.environ['SEALED_READER_EXISTING_FIXTURE']).resolve()/'workspace'
assert root.is_relative_to(Path('/tmp/laplace-programme-20261025/sealed-text-reader-consumer'))
os.environ.update(LAPLACE_REPO_ROOT=str(root),LAPLACE_ROOT=str(root))
from laplace.writing import session_reads
from laplace.web import authoring_http
from urllib.parse import urlsplit,parse_qs
raw=[json.loads(line) for line in (root/'contract/talk.jsonl').read_text().splitlines()]
session=next(row for row in raw if row.get('record')=='writing-session' and row.get('reader_profile'))
observed=session_reads.session_state(root,session['id'],view='summary',limit=1)
handle=observed['session']['reader_capabilities']['new_attempt'];parsed=urlsplit(handle['http']['url'])
code,kind,body=authoring_http.handle(root,parsed.path,parse_qs(parsed.query),'GET',b'')
proof={'source':str(SOURCE),'source_commit':os.environ['SEALED_READER_SOURCE_COMMIT'],'session_id':session['id'],'banked_input':session['reader_profile']['input'],'banked_is_reference':bodies.is_reference(session['reader_profile']['input']),'observed_reader_profile':observed['session']['reader_profile'],'observed_is_reference':bodies.is_reference(observed['session']['reader_profile']['input']),'issued_new_attempt':handle,'actual_HTTP':{'status':code,'body':json.loads(body)},'provider_processes':0}
(HOME/'session-input-proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
refusal=next((row for row in raw if row.get('record')=='writing-reader-refusal'),None)
if refusal:
 terminal=session_reads.reader_request(root,'book',refusal['request_id'],refusal['reader_profile']['manifest_id'])
 assert terminal['effect']=='NOT_ADMITTED' and terminal['reader_refusal']==refusal['reader_refusal']
 (HOME/'terminal-lookup-proof.json').write_text(json.dumps({'source_commit':os.environ['SEALED_READER_SOURCE_COMMIT'],'outcome':terminal,'banked_outcome_id':refusal['id'],'actual_provider_processes':0},ensure_ascii=False,indent=2)+'\n')
origins={n:str(Path(m.__file__).resolve()) for n,m in sys.modules.items() if (n in ('laplace','atlas') or n.startswith(('laplace.','atlas.'))) and getattr(m,'__file__',None)}
assert all(Path(p).is_relative_to(SOURCE/'src') for p in origins.values())
(HOME/'guard.json').write_text(json.dumps({'origins':origins,'runtime_refusals':runtime_guard.DENIALS,'write_refusals':refusals,'provider_processes':0},indent=2)+'\n')
print(json.dumps({'banked_reference':proof['banked_is_reference'],'observed_reference':proof['observed_is_reference'],'actual_HTTP_status':code,'origins':len(origins),'refusals':runtime_guard.DENIALS}))
