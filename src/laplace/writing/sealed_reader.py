"""One complete, fresh, tool-less text intake through existing Writing owners.

Bodies and records remain with Writing custody. This leaf prepares and admits
inputs; the existing turn execution/provider owns processes and replies.
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import math
import hashlib
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlencode

from laplace.core import identity, bodies
from laplace.representation import writing_bodies
from laplace.representation.writing_representation import BodyMissing, BodyHashMismatch

PROFILE = 'laplace.sealed-text-reader/1'
MANIFEST = 'laplace.sealed-text-reader-input/1'
QUALIFICATION = 'profiles/writing/sealed-reader-qualification.json'
HELP_EXECUTABLE_SHA = 'ea0f135784631619a7a409d07322ecec964f9cc4fd377508ed1ba3f141f27912'
KERNEL = ('You are a text-only document reader. Read the complete selected text and explicitly supplied '
          'text references. Ground your report in those inputs, distinguish what is stated from what '
          'you infer, and identify missing or ambiguous support. Figures and visual layout have not '
          'been supplied. Your general knowledge and ordinary platform safety instructions remain '
          'premises; no project plan, desired answer or previous review is supplied. Report findings '
          'and limitations without changing source or awarding acceptance.')
CONTROLS = ['-p', '--output-format', 'stream-json', '--include-partial-messages', '--verbose',
            '--settings', '{"outputStyle":"default"}', '--permission-mode', 'auto',
            '--permission-prompts', 'none', '--safe-mode', '--tools', '', '--disable-slash-commands',
            '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}', '--no-chrome',
            '--no-session-persistence', '--exclude-dynamic-system-prompt-sections']
_PIN = re.compile(r'sha256:[0-9a-f]{64}\Z')
EVIDENCE_KINDS = {'startup', 'tool-read-canary', 'input-delivery'}
OPERATOR_PURPOSE = 'operator-qualification'
OPERATOR_POLICY = {'purpose':OPERATOR_PURPOSE,'monetary_flag':'--max-budget-usd',
    'stopping':'existing supervised wall/cleanup and UTF-8 public-text prefix; no hard token guarantee',
    'limit_fields':['max_budget_usd','wall_seconds','cleanup_grace_seconds','max_input_utf8_bytes','max_output_utf8_bytes']}
# ORDINARY BOUNDED DOCUMENT DELIBERATION (Eigen continuity, Root e716/e2f6, A_bridges_kernel). A second, distinct
# purpose through the SAME prepared input, admission, provider flag and wall/cleanup/UTF-8 supervision as the operator
# purpose: closed supported maxima, QUALIFIED support only (the qualification-only CANDIDATE exemption is never
# selectable here), an immutable request intent and input receipt, and purpose-correct result metadata. The provider
# budget flag is a reported provider control, not a hard token guarantee and not a cost estimate.
DELIBERATION_PURPOSE = 'document-deliberation'
DELIBERATION_SCHEMA = 'laplace.sealed-reader-deliberation-request/1'
DELIBERATION_MAXIMUM = {'max_budget_usd':'10','wall_seconds':1800,'cleanup_grace_seconds':60,
    'max_input_utf8_bytes':2000000,'max_output_utf8_bytes':200000}
DELIBERATION_POLICY = {'purpose':DELIBERATION_PURPOSE,'monetary_flag':'--max-budget-usd',
    'stopping':'existing supervised wall/cleanup and UTF-8 public-text prefix; no hard token guarantee',
    'limit_fields':list(OPERATOR_POLICY['limit_fields']),'supported_maximum':DELIBERATION_MAXIMUM,
    'support':'QUALIFIED only; the qualification CANDIDATE exemption is not selectable','attempts':1,
    'cost':'The budget flag is a provider-reported control; no cost estimate or token guarantee is implied.'}
STARTUP_STATE = 'OBSERVED_SEALED_READ_BOUNDARY'
STARTUP_PRODUCER_SHA = 'ea0f135784631619a7a409d07322ecec964f9cc4fd377508ed1ba3f141f27912'
# Only public identifiers verified against this exact registry belong here.
# Unknown catalogue provenance is metadata, never a permission/context verdict.
PUBLIC_BUILTIN_AGENTS = frozenset()
PUBLIC_BUILTIN_PLUGINS = frozenset({'agents-md'})


def operator_limits(value):
    _closed(value,OPERATOR_POLICY['limit_fields'],OPERATOR_POLICY['limit_fields'])
    usd=value['max_budget_usd']
    try:
        if not isinstance(usd,str) or not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',usd) or not Decimal(usd).is_finite() or Decimal(usd)<=0:
            raise ValueError('Operator USD limit must be a positive finite decimal string.')
    except InvalidOperation as error:raise ValueError('Operator USD limit is invalid.') from error
    for key in ('wall_seconds','cleanup_grace_seconds'):
        try:finite=type(value[key]) in (int,float) and math.isfinite(value[key])
        except OverflowError:finite=False
        if not finite or value[key]<=0:
            raise ValueError('Operator time limits must be positive and finite.')
    for key in ('max_input_utf8_bytes','max_output_utf8_bytes'):
        if type(value[key])!=int or value[key]<=0:raise ValueError('Operator byte limits must be positive integers.')
    return copy.deepcopy(value)


def operator_request(commission):
    fields={'schema_version','purpose','project','input','expected_fingerprint','expected_support_basis','request_id','limits'}
    _closed(commission,fields,fields)
    if commission['schema_version']!='laplace.sealed-reader-operator-commission/1' or commission['purpose']!=OPERATOR_PURPOSE or not _PIN.fullmatch(str(commission['expected_fingerprint'])):
        raise ValueError('Select the exact local operator qualification commission.')
    public={key:commission[key] for key in ('project','input','expected_support_basis','request_id')}
    request=start_request({**public,'profile':PROFILE})
    limits=operator_limits(commission['limits'])
    request['reader_intent_sha256']=identity.canonical_digest({key:value for key,value in commission.items() if key!='request_id'})
    return request,{'purpose':OPERATOR_PURPOSE,'limits':limits,'expected_fingerprint':commission['expected_fingerprint']}


def deliberation_limits(value):
    """The operator limit shape plus the closed supported maxima of ordinary deliberation; nothing is raised or substituted."""
    checked=operator_limits(value)
    if Decimal(checked['max_budget_usd'])>Decimal(DELIBERATION_MAXIMUM['max_budget_usd']):
        raise ValueError('Deliberation max_budget_usd exceeds the supported maximum '+DELIBERATION_MAXIMUM['max_budget_usd']+'.')
    for key in ('wall_seconds','cleanup_grace_seconds','max_input_utf8_bytes','max_output_utf8_bytes'):
        if checked[key]>DELIBERATION_MAXIMUM[key]:
            raise ValueError('Deliberation %s exceeds the supported maximum %s; no limit is raised or substituted.' % (key,DELIBERATION_MAXIMUM[key]))
    return checked


def deliberation_request(commission):
    """The ordinary bounded document-deliberation request: same prepared input and Start identity, its own purpose."""
    fields={'schema_version','purpose','project','input','expected_support_basis','request_id','limits'}
    _closed(commission,fields,fields)
    if commission['schema_version']!=DELIBERATION_SCHEMA or commission['purpose']!=DELIBERATION_PURPOSE:
        raise ValueError('Select the ordinary document-deliberation purpose exactly; reader qualification is a separate trusted local entry.')
    public={key:commission[key] for key in ('project','input','expected_support_basis','request_id')}
    request=start_request({**public,'profile':PROFILE})
    limits=deliberation_limits(commission['limits'])
    request['reader_intent_sha256']=identity.canonical_digest({key:value for key,value in commission.items() if key!='request_id'})
    return request,{'purpose':DELIBERATION_PURPOSE,'limits':limits,'expected_fingerprint':None}


def bounded_request(commission):
    """One bounded reader request by its declared purpose; an unsupported purpose refuses (no purpose substitution)."""
    purpose=commission.get('purpose') if isinstance(commission,dict) else None
    if purpose==OPERATOR_PURPOSE:return operator_request(commission)
    if purpose==DELIBERATION_PURPOSE:return deliberation_request(commission)
    raise ValueError('Unsupported bounded reader purpose; select operator-qualification (trusted local) or document-deliberation.')


def _purpose_limits(bounded):
    if bounded.get('purpose')==OPERATOR_PURPOSE:return operator_limits(bounded['limits'])
    if bounded.get('purpose')==DELIBERATION_PURPOSE:return deliberation_limits(bounded['limits'])
    raise ValueError('Unsupported internal reader purpose.')


def admissible_states(bounded):
    """Only the trusted qualification purpose may start on CANDIDATE support; every other purpose needs QUALIFIED."""
    return frozenset({'CANDIDATE','QUALIFIED'}) if bounded and bounded.get('purpose')==OPERATOR_PURPOSE else frozenset({'QUALIFIED'})


def operator_profile(profile):
    """The bounded supervision profile of an admitted reader turn (either purpose), or None for an ordinary reader."""
    value=profile.get('operator') if isinstance(profile,dict) else None
    if value is None:return None
    if value.get('purpose') not in (OPERATOR_PURPOSE,DELIBERATION_PURPOSE):raise ValueError('Unsupported internal reader purpose.')
    _purpose_limits(value)
    return value


def deliberation_preview(root, project, commission):
    """PURE preview of one ordinary deliberation Start: closed request, supported limits, QUALIFIED support, exact
    prepared input/settings/source currentness and the input receipt. No session, turn, record or provider process."""
    base={'schema_version':'laplace.sealed-reader-deliberation-preview/1','profile':PROFILE,'purpose':DELIBERATION_PURPOSE,
          'recorded':False,'policy':copy.deepcopy(DELIBERATION_POLICY),
          'meaning':'Pure preview: nothing was admitted; Start revalidates every predicate at the admission boundary.'}
    try:
        request,bounded=deliberation_request(commission)
    except ValueError as error:
        return {**base,'admissible':False,'refusals':[{'code':'REQUEST_UNSUPPORTED','message':str(error)[:300]}]}
    refusals=[]
    if request['project']!=project:
        return {**base,'admissible':False,'refusals':[{'code':'PROJECT_MISMATCH','message':'The commission names another project.'}]}
    supported=support(root,project)
    if supported['support_basis']!=commission['expected_support_basis']:
        refusals.append({'code':'SUPPORT_CHANGED','message':'Reader support changed; inspect the exact current support.'})
    if supported['state'] not in admissible_states(bounded):
        refusals.append({'code':'SUPPORT_UNQUALIFIED','message':'Ordinary deliberation needs QUALIFIED support (observed '+str(supported['state'])+').'})
    receipt=None
    try:
        value=_manifest(root,project,commission['input'])
        task=_get(root,value.get('task'));packet=_get(root,value.get('packet'))
        if not isinstance(task,str) or not isinstance(packet,str):raise InputUnavailable('Prepared reader input is malformed.')
    except (InputUnavailable,bodies.BudgetExceeded) as error:
        refusals.append({'code':'INPUT_UNAVAILABLE','message':str(error)[:300]})
    else:
        try:
            choice=settings(root,value['settings']['model'],value['settings']['effort'])
            if any(choice[key]!=value['settings'][key] for key in ('provider','model','effort')):
                raise ValueError('Prepared settings resolve differently now.')
        except ValueError as error:
            refusals.append({'code':'SETTINGS_UNSUPPORTED','message':str(error)[:300]})
        observed=currentness(root,project,commission['input'])
        if not observed['unchanged']:
            refusals.append({'code':'SOURCE_CHANGED_OR_UNAVAILABLE','message':'A selected input changed or is unavailable.'})
        prompt=input_prompt(task,packet);total=len(KERNEL.encode())+len(prompt.encode())
        if total>bounded['limits']['max_input_utf8_bytes']:
            refusals.append({'code':'INPUT_EXCEEDS_LIMIT','message':'Complete input is %d UTF-8 bytes; the limit is %d.' % (total,bounded['limits']['max_input_utf8_bytes'])})
        receipt={'manifest_id':commission['input']['content_handle'],'settings':copy.deepcopy(value['settings']),
                 'sizes':copy.deepcopy(value['sizes']),'stdin_sha256':identity.bytes_digest(prompt.encode()),
                 'stdin_utf8_bytes':len(prompt.encode()),'input_utf8_bytes':total}
    return {**base,'admissible':not refusals,'refusals':refusals,'limits':copy.deepcopy(bounded['limits']),
            'intent_sha256':request['reader_intent_sha256'],
            'support':{key:supported[key] for key in ('state','support_basis','fingerprint')},'input_receipt':receipt,
            'start':{'entry':'laplace.sdk.reader_deliberate','payload':copy.deepcopy(commission)} if not refusals else None}


def input_prompt(task,packet):
    return 'READER TASK\n'+task+'\n\nCOMPLETE SELECTED TEXT PACKET\n'+packet


def byte_prefix(text,limit):
    raw=text.encode('utf-8');return raw[:limit].decode('utf-8',errors='ignore'),len(raw)>limit


class InputUnavailable(ValueError):
    """Known malformed, absent or corrupt selected input custody, not arbitrary I/O."""


class SelectedInputUnavailable(ValueError):
    """The selected owner explicitly refused a pin or complete representation."""


class NotAdmitted(ValueError):
    """Issued only by reader checks before any session/turn/execution effect."""
    def __init__(self, payload, code, message):
        super().__init__(message)
        self.terminal=False
        project=payload['project'];ref=payload.get('input')
        manifest=ref.get('content_handle') if isinstance(ref,dict) else None
        reads={'support':handle(project,view='support')}
        if _PIN.fullmatch(str(manifest)):
            reads.update(input=handle(project,view='input',input=ref),
                         currentness=handle(project,view='currentness',input=ref))
        self.details={'reader_refusal':{'profile':PROFILE,'disposition':'NOT_ADMITTED','code':code,
            'project':project,'request_id':payload['request_id'],
            'manifest_id':manifest if _PIN.fullmatch(str(manifest)) else None,'reinspect':reads}}


def error_details(error):
    return copy.deepcopy(error.details) if isinstance(error,NotAdmitted) and error.terminal else {}


def _closed(value, allowed, required=()):
    if not isinstance(value, dict) or set(value)-set(allowed) or set(required)-set(value):
        raise ValueError('Reader request does not match its closed contract.')


def _project(root, project):
    from laplace.pipeline import registry
    if not isinstance(project, str) or not registry.resolve(project, repo_root=root):
        raise ValueError('Select an existing registered custody project; a manuscript is not required.')


def _put(root, value):
    raw = bodies.encode(value)
    held = bodies.retain(lambda content: writing_bodies.store(root).put(content), writing_bodies.STORE,
                         raw, bodies.degradation())
    if held is None:
        raise ValueError('Exact reader input custody is unavailable; no input was admitted.')
    return held


def _local_reference(ref):
    if (not isinstance(ref,dict) or set(ref)!={'schema_version','content_handle','store','bytes','encoding'}
            or ref.get('schema_version')!=bodies.REFERENCE_SCHEMA or ref.get('store')!=writing_bodies.STORE
            or ref.get('encoding')!=bodies.ENCODING or not _PIN.fullmatch(str(ref.get('content_handle')))
            or type(ref.get('bytes'))!=int or ref['bytes']<0):
        raise InputUnavailable('Reader custody requires an exact local Writing public-body reference.')


def _body(root, ref):
    _local_reference(ref)
    try:
        return writing_bodies.read_bytes(ref,Path(root))
    except bodies.BudgetExceeded:
        raise
    except (BodyMissing,BodyHashMismatch) as error:
        if isinstance(error.__cause__,OSError):raise  # unreadable storage is not a known missing-body fact
        raise InputUnavailable('Retained reader body is absent or hash-corrupt.') from error
    except ValueError as error:  # the existing body's declared-size/version validation
        raise InputUnavailable('Retained reader body does not match its reference.') from error


def _get(root, ref):
    try:return json.loads(_body(root,ref))
    except (UnicodeError,json.JSONDecodeError) as error:
        raise InputUnavailable('Retained reader body is not its declared JSON representation.') from error


def handle(project, **fields):
    query = {'project': project, **fields}
    url = '/authoring/reader?' + urlencode({key: json.dumps(value, separators=(',', ':'),sort_keys=True)
        if isinstance(value, dict) else value for key, value in query.items()})
    return {'http': {'method': 'GET', 'url': url}, 'native': {'operation': 'project',
        'payload': {'view': 'sealed-text-reader', 'request': query}}}


def support(root, project):
    from laplace.projects.writing_sources import file_revision
    binary = shutil.which('claude')
    executable = Path(binary).resolve() if binary else None
    digest = file_revision(executable) if executable else None
    fingerprint = identity.canonical_digest({'profile': PROFILE, 'executable_sha256': digest,
        'controls': CONTROLS, 'kernel': KERNEL, 'fresh': True, 'tools': [], 'mcp': [],
        'adapter_source':file_revision(Path(__file__).with_name('provider.py')),
        'input_profile_source':file_revision(Path(__file__)), 'operator_policy':OPERATOR_POLICY,
        'deliberation_policy':DELIBERATION_POLICY,
        'supervision_source':file_revision(Path(__file__).with_name('turn_execution.py')),
        'operator_entry_source':file_revision(Path(__file__).with_name('reader_qualification.py'))})
    state, reason = ('CANDIDATE', 'Help/control candidate only; operator canary qualification is missing.')
    proof = None; evidence_rows=[]
    if digest != HELP_EXECUTABLE_SHA:
        state, reason = 'UNAVAILABLE', 'This executable has no matching observed help/control basis.'
    try:
        proof = json.loads((Path(root)/QUALIFICATION).read_text())
        _closed(proof, {'schema_version','fingerprint','outcome','evidence'},
                {'schema_version','fingerprint','outcome','evidence'})
        evidence = proof['evidence']
        if (proof['schema_version'] != 'laplace.sealed-reader-qualification/1'
                or proof['fingerprint'] != fingerprint or proof['outcome'] != 'QUALIFIED'
                or not isinstance(evidence, list) or len(evidence)!=3 or any(not isinstance(row,dict) for row in evidence)
                or {row.get('kind') for row in evidence} != EVIDENCE_KINDS
                or any(set(row) != {'kind','body'} for row in evidence)):
            raise ValueError('Qualification does not match this adapter/executable proof basis.')
        for entry in evidence:
            envelope=_get(root,entry['body'])
            _closed(envelope,{'schema_version','profile','fingerprint','kind','outcome','observation'},
                    {'schema_version','profile','fingerprint','kind','outcome','observation'})
            if (envelope['schema_version']!='laplace.sealed-reader-evidence/1' or envelope['profile']!=PROFILE
                    or envelope['fingerprint']!=fingerprint or envelope['kind']!=entry['kind']
                    or envelope['outcome']!='PASS' or not isinstance(_get(root,envelope['observation']),dict)):
                raise ValueError('Qualification evidence does not match its declared kind/profile/basis.')
            evidence_rows.append({'kind':entry['kind'],'envelope_sha256':entry['body']['content_handle'],
                'observation_sha256':envelope['observation']['content_handle'],
                'bytes':{'envelope':entry['body']['bytes'],'observation':envelope['observation']['bytes']}})
        if state != 'UNAVAILABLE':
            state, reason = 'QUALIFIED', 'Operator-installed proof qualifies this exact profile/executable.'
    except (FileNotFoundError, ValueError, TypeError, KeyError):
        proof = None; evidence_rows=[]
    basis=identity.canonical_digest({'fingerprint':fingerprint,'qualification':proof})
    for row in evidence_rows:
        row['reads']={part:handle(project,view='evidence',kind=row['kind'],part=part,expected_support_basis=basis)
                      for part in ('envelope','observation')}
    return {'profile': PROFILE, 'state': state, 'support_basis':basis, 'fingerprint': fingerprint,
        'executable': str(executable) if executable else None, 'executable_sha256': digest,
        'controls': list(CONTROLS), 'qualification': proof, 'evidence':evidence_rows, 'reasons': [reason],
        'operator_policy':copy.deepcopy(OPERATOR_POLICY),'deliberation_policy':copy.deepcopy(DELIBERATION_POLICY),
        'read_operations': [], 'fresh': True, 'text_only': True,
        'sizing': {'fit': 'UNMEASURED', 'capacity': 'provider-owned; no app packet threshold'}}


def _item(root, project, item):
    from laplace.projects import library
    from laplace.core.source_pin import SourcePinRefusal
    _closed(item, {'target','expected_sha256','representation'}, {'target','expected_sha256','representation'})
    if not _PIN.fullmatch(str(item['expected_sha256'])) or item['representation'] not in {'utf8-text','pdf-text'}:
        raise ValueError('Select exact raw-source SHA and an explicit text representation.')
    target = item['target']
    is_pdf = str(target.get('path','')).lower().endswith('.pdf') if isinstance(target, dict) else False
    if is_pdf != (item['representation'] == 'pdf-text'):
        raise ValueError('A PDF requires explicit PDF-text representation; it is not a visual read.')
    request = {'view':'preview', 'target':target, 'offset':0, 'limit':40000,
               'expected_sha256':item['expected_sha256']}
    text, coverage, seen = [], [], set()
    while True:
        key = identity.canonical_digest(request)
        if key in seen:
            raise SelectedInputUnavailable('Source owner repeated a continuation; complete coverage is unavailable.')
        seen.add(key)
        try:result = library.material_references(project, root, **request)
        except SourcePinRefusal as error:
            raise SelectedInputUnavailable('Selected source pin changed or became unavailable.') from error
        owner = result.get('owner_result') or {}
        if result.get('diagnostic'):
            # Material deliberately qualifies opaque owner failures. Do not turn
            # that diagnostic (which can mask I/O) into a no-admission assertion.
            raise ValueError('Selected source owner could not establish its current representation.')
        if str(result.get('current_revision') or '').removeprefix('sha256:') != item['expected_sha256'][7:] or not isinstance(owner.get('content'), str):
            raise SelectedInputUnavailable('Selected source is unavailable or changed; inspect its exact owner.')
        text.append(owner['content'])
        coverage.append({key:owner[key] for key in ('offset','next_offset','pdf_page_start','pdf_page_end','pdf_total_pages') if key in owner})
        next_read = result.get('read_handle')
        if not next_read:break
        request = next_read['payload']
    if is_pdf and (coverage[0].get('pdf_page_start') != 1 or
                   coverage[-1].get('pdf_page_end') != coverage[-1].get('pdf_total_pages')):
        raise SelectedInputUnavailable('The existing source owner did not prove complete PDF text coverage.')
    content = ''.join(text)
    derivation = {'owner':'existing Material/source text reader','coverage':coverage,
                  'visual_pages_supplied':False, 'text_decoding':'owner UTF-8 text; repository newline normalization retained'}
    if is_pdf:
        from laplace.projects import writing_sources
        extractor = writing_sources._tool('pdftotext')
        extractor_sha=writing_sources.file_revision(Path(extractor).resolve())
        if not extractor_sha:raise SelectedInputUnavailable('PDF text extractor identity is unavailable.')
        derivation['extractor'] = {'name':'pdftotext','sha256':extractor_sha}
    from laplace.pipeline import registry
    project_record=registry.resolve(project,repo_root=root)
    linked=[{'consumer_project':project,'id':row.get('id'),'consumed_revision':row.get('consumed_revision')}
            for row in project_record.manifest.get('material_references',[]) if row.get('target')==target]
    return {**copy.deepcopy(item), 'body':_put(root, content), 'text_sha256':identity.bytes_digest(content.encode()),
            'material_bindings':linked,
            'characters':len(content), 'utf8_bytes':len(content.encode()), 'derivation':derivation}, content


def prepare(root, payload):
    _closed(payload, {'project','view','primary','references','missing_references','task','model','effort'},
            {'project','primary','task','model','effort'})
    project = payload['project']; _project(root, project)
    task = payload['task']
    if not isinstance(task, str) or not task.strip() or len(task) > 100000:
        raise ValueError('The editable reader task must contain 1..100000 characters; document content is attached separately.')
    choice = settings(root,payload['model'],payload['effort'])
    if choice['provider'] != 'claude' or choice['model'] != payload['model'] or choice['effort'] != payload['effort']:
        raise ValueError('Reader settings must be supported exactly; no implicit model/effort replacement.')
    references = payload.get('references', []); missing = payload.get('missing_references', [])
    if not isinstance(references, list) or not isinstance(missing, list):raise ValueError('References must be explicit lists.')
    for entry in missing:
        _closed(entry, {'label','reason'}, {'label','reason'})
        if any(not isinstance(entry[key],str) or not entry[key].strip() for key in entry):raise ValueError('Missing reference needs label and reason.')
    inputs, blocks = [], []
    for index, item in enumerate([payload['primary'], *references]):
        selected, text = _item(root, project, item); inputs.append(selected)
        blocks.append(('PRIMARY DOCUMENT' if index == 0 else 'SELECTED REFERENCE '+str(index))+'\n'+text)
    if missing:blocks.append('DECLARED UNAVAILABLE OR UNSELECTED REFERENCES\n'+json.dumps(missing,ensure_ascii=False))
    packet = '\n\n'.join(blocks)
    manifest = {'schema_version':MANIFEST,'profile':PROFILE,'project':project,'inputs':inputs,
        'missing_references':copy.deepcopy(missing),'reference_linkage':'author-declared selection; citation alignment is not machine-certified',
        'task':_put(root,task),'kernel':_put(root,KERNEL),'packet':_put(root,packet),
        'settings':{key:choice[key] for key in ('provider','model','effort')},
        'sizes':{name:{'characters':len(value),'utf8_bytes':len(value.encode()),'sha256':identity.bytes_digest(value.encode())}
                 for name,value in (('kernel',KERNEL),('task',task),('packet',packet))},
        'sizing':{'fit':'UNMEASURED','provider_capacity':'provider-owned','packet_truncated':False}}
    ref = _put(root, manifest)
    from laplace.writing import records
    with records.index_lock:
        ident='RINPUT-'+ref['content_handle'][7:]
        if not records.index(root).by_id.get(ident):
            records.bank(root,{'record':'writing-reader-input','id':ident,'project':project,
                'output_sha256':ref['content_handle'],'input':ref})
    return inspect_input(root, project, ref, manifest=manifest)


def settings(root, model, effort):
    from laplace.writing.provider_catalogue import provider_catalogue
    from laplace.work.project_work import resolve_session_settings
    provider=next((row for row in provider_catalogue(Path(root))['providers'] if row['id']=='claude' and row.get('available')),None)
    if provider is None:raise ValueError('Inspect/configure the Claude catalogue before preparing reader settings.')
    return resolve_session_settings(provider,{'provider':'claude','model':model,'effort':effort},role='session')


def _manifest(root, project, ref):
    from laplace.writing import records
    if not isinstance(ref,dict) or not _PIN.fullmatch(str(ref.get('content_handle'))):
        raise InputUnavailable('Reader input reference is malformed.')
    rows=records.index(root).by_id.get('RINPUT-'+ref['content_handle'][7:],[])
    if not rows or any(row.get('record')!='writing-reader-input' or row.get('project')!=project
                       or row.get('output_sha256')!=ref['content_handle'] for row in rows):
        raise InputUnavailable('No issued reader input belongs to this project.')
    value = _get(root, ref)
    if (not isinstance(value, dict) or value.get('schema_version') != MANIFEST
            or value.get('profile') != PROFILE or value.get('project') != project):
        raise InputUnavailable('Reader input does not belong to this project/profile.')
    if _get(root, value.get('kernel')) != KERNEL:raise InputUnavailable('Reader kernel differs from the declared profile.')
    return value


def inspect_input(root, project, ref, *, manifest=None):
    value = manifest or _manifest(root, project, ref); supported = support(root, project)
    return {'profile':PROFILE,'project':project,'input':ref,'manifest_id':ref['content_handle'],
        'manifest':copy.deepcopy(value),
        'inputs':value['inputs'],'missing_references':value['missing_references'],
        'summary':{'text_only':True,'input_count':len(value['inputs']),'sizes':value['sizes'],
                   'settings':value['settings'],'sizing':value['sizing']},
        'parts':{key:handle(project,view='input',input=ref,part=key) for key in ('kernel','task','packet')},
        'support':supported,'start':{'permitted':supported['state']=='QUALIFIED','reason':supported['reasons'][0],
            'payload':{'project':project,'profile':PROFILE,'input':ref,'expected_support_basis':supported['support_basis']},
            'required_inputs':['request_id']},
        'deliberation':{'permitted':supported['state']=='QUALIFIED','purpose':DELIBERATION_PURPOSE,
            'template':{'schema_version':DELIBERATION_SCHEMA,'purpose':DELIBERATION_PURPOSE,'project':project,'input':ref,
                        'expected_support_basis':supported['support_basis'],'request_id':None,'limits':None},
            'fill':['request_id','limits'],'supported_maximum':copy.deepcopy(DELIBERATION_MAXIMUM),
            'preview':{**handle(project,view='deliberation-preview'),'fill':['commission']},'entry':'laplace.sdk.reader_deliberate'},
        'read':handle(project,view='input',input=ref)}


def currentness(root, project, ref):
    value = _manifest(root, project, ref); rows=[]
    for item in value['inputs']:
        from laplace.projects import library
        try:
            observed=library._material_target(root,item['target'])
            revision='sha256:'+str(observed['revision']).removeprefix('sha256:')
            state='UNCHANGED' if revision==item['expected_sha256'] else 'CHANGED'
        except (OSError,ValueError):state='UNAVAILABLE';revision=None
        rows.append({'target':item['target'],'state':state,'selected_sha256':item['expected_sha256'],
            'current_sha256':revision,'current_read':library.material_read_handle(project,{
                'view':'preview','target':item['target']})})
    return {'manifest_id':ref['content_handle'],'inputs':rows,'unchanged':all(row['state']=='UNCHANGED' for row in rows),
            'new_attempt':handle(project,view='input',input=ref)}


def request(root, payload):
    root=Path(root).resolve(); project=payload.get('project');_project(root,project);view=payload.get('view','support')
    if view=='prepare':return prepare(root,payload)
    if view=='deliberation-preview':
        _closed(payload,{'project','view','commission'},{'project','view','commission'})
        return deliberation_preview(root,project,payload['commission'])
    allowed={'support':{'project','view'},'evidence':{'project','view','kind','part','expected_support_basis','offset','limit'},
             'input':{'project','view','input','part','offset','limit'},
             'currentness':{'project','view','input'},'result':{'project','view','input','turn_id'}}.get(view)
    if allowed is None:raise ValueError('Unknown sealed reader view.')
    _closed(payload,allowed,{'project'})
    if view=='support':return support(root,project)
    if view=='evidence':
        current=support(root,project);kind=payload.get('kind');part=payload.get('part')
        if (not current['qualification'] or payload.get('expected_support_basis')!=current['support_basis']
                or kind not in EVIDENCE_KINDS or part not in {'envelope','observation'}):
            raise ValueError('Reinspect the installed qualification and follow its exact evidence handle.')
        entry=next(row for row in current['qualification']['evidence'] if row['kind']==kind)
        ref=entry['body'] if part=='envelope' else _get(root,entry['body'])['observation']
        text=_body(root,ref).decode('utf-8');offset=payload.get('offset',0);limit=payload.get('limit',16000)
        if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=40000:raise ValueError('Invalid reader evidence page.')
        end=min(len(text),offset+limit)
        return {'profile':PROFILE,'project':project,'kind':kind,'part':part,'support_basis':current['support_basis'],
            'content':text[offset:end],'sha256':ref['content_handle'],'bytes':ref['bytes'],
            'offset':offset,'total_characters':len(text),
            'next_read':handle(project,view='evidence',kind=kind,part=part,expected_support_basis=current['support_basis'],
                offset=end,limit=limit) if end<len(text) else None}
    ref=payload.get('input');value=_manifest(root,project,ref)
    if view=='currentness':return currentness(root,project,ref)
    if view=='input':
        part=payload.get('part','manifest')
        if part=='manifest':return inspect_input(root,project,ref,manifest=value)
        if part not in {'kernel','task','packet'}:raise ValueError('Read kernel, task, packet or manifest.')
        text=_get(root,value[part]);offset=payload.get('offset',0);limit=payload.get('limit',16000)
        if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=40000:raise ValueError('Invalid reader part page.')
        end=min(len(text),offset+limit)
        return {'project':project,'manifest_id':ref['content_handle'],'part':part,'content':text[offset:end],
            'offset':offset,'total_characters':len(text),'sha256':identity.bytes_digest(text.encode()),
            'next_read':handle(project,view='input',input=ref,part=part,offset=end,limit=limit) if end<len(text) else None}
    if view=='result':
        from laplace.writing import session_reads
        exact=session_reads.session_turn_detail(root,project,payload.get('turn_id'),'turn')
        profile=exact['turn'].get('reader_profile') or {}
        if profile.get('manifest_id')!=ref['content_handle']:raise ValueError('Result belongs to another reader input.')
        return {'profile':PROFILE,**exact,'input':ref,'currentness':currentness(root,project,ref),
                'new_attempt':handle(project,view='input',input=ref)}
    raise ValueError('Unknown sealed reader view.')


def request_contract():
    """One request declaration for the HTTP/native/SDK projections."""
    string={'type':'string'};obj={'type':'object'}
    common={'project':string,'view':{'enum':['support','prepare','input','currentness','result','evidence','deliberation-preview']}}
    return {'type':'object','required':['project'],'properties':{**common,'input':obj,'commission':obj,'part':{'enum':['manifest','kernel','task','packet','envelope','observation']},
        'kind':{'enum':sorted(EVIDENCE_KINDS)},'expected_support_basis':string,
        'offset':{'type':'integer','minimum':0},'limit':{'type':'integer','minimum':1,'maximum':40000},'turn_id':string,
        'primary':obj,'references':{'type':'array','items':obj},'missing_references':{'type':'array','items':obj},
        'task':string,'model':string,'effort':{'type':['string','null']}},'additionalProperties':False}


def start_contract():
    return {'type':'object','required':['project','profile','input','expected_support_basis','request_id'],
        'properties':{'project':{'type':'string'},'profile':{'const':PROFILE},'input':{'type':'object'},
            'expected_support_basis':{'type':'string','pattern':'^sha256:[0-9a-f]{64}$'},
            'request_id':{'type':'string','minLength':1,'maxLength':160}},'additionalProperties':False}


def start_request(payload):
    _closed(payload,{'project','profile','input','expected_support_basis','request_id'},
            {'project','profile','input','expected_support_basis','request_id'})
    if payload['profile']!=PROFILE or not isinstance(payload['request_id'],str) or not 1<=len(payload['request_id'])<=160:
        raise ValueError('Reader Start needs its exact profile and stable request identity.')
    if not _PIN.fullmatch(str(payload['expected_support_basis'])):
        raise ValueError('Inspect reader support before Start.')
    _local_reference(payload['input'])
    return {'project':payload['project'],'mode':'review','session_id':'','queued_values':[],
        'request_id':payload['request_id'],'profile':PROFILE,
        'reader_intent_sha256':identity.canonical_digest({key:value for key,value in payload.items() if key!='request_id'})}


def submission_read(project, request_id, manifest_id):
    return {'http':{'method':'GET','url':'/authoring/session-turn?'+urlencode({
        'view':'reader-request','project':project,'request_id':request_id,'manifest_id':manifest_id})}}


def receipt(turn):
    meta=turn['reader_profile']
    return {'turn_id':turn['id'],'session_id':turn['session_id'],
        'reader_submission':{'request_id':turn['request_id'],'intent_sha256':turn['reader_intent_sha256'],
            'manifest_id':meta['manifest_id'],'read':submission_read(turn['project'],turn['request_id'],meta['manifest_id'])},
        'events':'/authoring/events?turn='+turn['id']}


def replay(root, request):
    from laplace.writing import records
    with records.index_lock:
        saved=records.index(root)
        matches=list(saved.by_request.get((request['project'],request['request_id']),[]))
        terminal=records.raw_indexed_record(saved,matches[0]) if len(matches)==1 and matches[0]['record']=='writing-reader-refusal' else None
    if len(matches)>1:raise ValueError('Reader submission identity is ambiguous.')
    if matches:
        turn=matches[0]
        if (turn.get('reader_profile') or {}).get('profile')!=PROFILE or turn.get('reader_intent_sha256')!=request['reader_intent_sha256']:
            raise ValueError('Reader Start intent changed or request kind conflicts under this request identity.')
        if terminal:raise terminal_refusal(terminal)
        return {**receipt(turn),'reused':True}
    return None


def require_unreserved_request(root, request):
    from laplace.writing import records
    if any(row['record']=='writing-reader-refusal' for row in records.index(root).by_request.get(
            (request['project'],request['request_id']),[])):
        raise ValueError('Request identity belongs to a terminal sealed-reader rejection.')


def execution_support(root,project,profile):
    checked=support(root,project);operator=operator_profile(profile)
    allowed=admissible_states(operator)
    if (checked['state'] not in allowed or checked['support_basis']!=profile['support_basis']
            or checked['fingerprint']!=profile['fingerprint']):
        raise ValueError('Sealed reader exact purpose/support basis changed before process start.')
    return checked


def _terminal_details(row):
    profile=row.get('reader_profile') or {};ref=profile.get('input');_local_reference(ref)
    codes={'INPUT_UNAVAILABLE','INPUT_EXCEEDS_LIMIT','SUPPORT_CHANGED','SUPPORT_UNQUALIFIED','SOURCE_CHANGED_OR_UNAVAILABLE','SETTINGS_CHANGED'}
    details=row.get('reader_refusal') or {};code=details.get('code')
    if (row.get('record')!='writing-reader-refusal' or profile.get('profile')!=PROFILE
            or profile.get('manifest_id')!=ref['content_handle'] or code not in codes
            or not isinstance(row.get('request_id'),str) or not 1<=len(row['request_id'])<=160
            or not _PIN.fullmatch(str(row.get('reader_intent_sha256')))):
        raise ValueError('Terminal reader request outcome is malformed or unsupported.')
    if row.get('id')!='RREF-'+identity.canonical_digest({'project':row['project'],'request_id':row['request_id']})[7:]:
        raise ValueError('Terminal reader request identity does not match its project/request.')
    expected=NotAdmitted({'project':row['project'],'request_id':row['request_id'],'input':ref},code,'').details['reader_refusal']
    expected.update(terminal=True,outcome_id=row['id'],intent_sha256=row['reader_intent_sha256'],
        read=submission_read(row['project'],row['request_id'],ref['content_handle']))
    if details!=expected:raise ValueError('Terminal reader request metadata does not match its identity.')
    return copy.deepcopy(expected)


def terminal_refusal(row):
    details=_terminal_details(row)
    error=NotAdmitted({'project':row['project'],'request_id':row['request_id'],
        'input':row['reader_profile']['input']},details['code'],
        'Reader request was not admitted. Inspect its terminal outcome and prepare explicitly with a new request.')
    error.details={'reader_refusal':details};error.terminal=True
    return error


def settle(root, payload, request, rejection):
    """Called under existing admission/publication locks, before returning a terminal claim."""
    from laplace.writing import records
    ref=payload['input'];ident='RREF-'+identity.canonical_digest({
        'project':request['project'],'request_id':request['request_id']})[7:]
    details=copy.deepcopy(rejection.details['reader_refusal'])
    details.update(terminal=True,outcome_id=ident,intent_sha256=request['reader_intent_sha256'],
        read=submission_read(request['project'],request['request_id'],ref['content_handle']))
    row={'record':'writing-reader-refusal','id':ident,'project':request['project'],'request_id':request['request_id'],
        'reader_profile':{'profile':PROFILE,'manifest_id':ref['content_handle'],'input':ref},
        'reader_intent_sha256':request['reader_intent_sha256'],'reader_refusal':details}
    _terminal_details(row)
    records.bank(root,row)  # failure, including a lost completion acknowledgement, stays uncertain
    # Only a captured, verified published row may produce the terminal exception.
    with records.index_lock:
        saved=records.index(root);matches=saved.by_request.get((request['project'],request['request_id']),[])
        if len(matches)!=1 or matches[0]['id']!=ident:raise RuntimeError('Reader rejection publication is uncertain.')
        published=records.raw_indexed_record(saved,matches[0])
    return terminal_refusal(published)


def capabilities(profile, project):
    return {'can_send':False,'can_configure':False,'can_steer':False,
            'new_attempt':handle(project,view='input',input=profile['input'])}


def require_not_reader(root, *, session_id=None, turn_id=None):
    from laplace.writing import records
    saved=records.index(root)
    turn=saved.turns.get(turn_id) or {}
    session=saved.sessions.get(session_id or turn.get('session_id')) or {}
    if session.get('reader_profile') or turn.get('reader_profile'):
        raise ValueError('This sealed reader is one attempt. Inspect its retained result and prepare a fresh input/attempt.')


def admit(root, payload, request, saved, *, operator=None):
    from laplace.writing import turn_admission as T
    ref=payload['input'];project=request['project']
    try:
        value=_manifest(root,project,ref)
        task=_get(root,value.get('task'));packet=_get(root,value.get('packet'))
        if (not isinstance(task,str) or not task.strip() or len(task)>100000
                or not isinstance(packet,str) or not isinstance(value.get('inputs'),list)
                or not value['inputs'] or not isinstance(value.get('settings'),dict)):
            raise InputUnavailable('Prepared reader input does not match its issued content contract.')
    except InputUnavailable as error:
        raise NotAdmitted(payload,'INPUT_UNAVAILABLE','Prepared input is unavailable; inspect its exact custody and prepare explicitly again.') from error
    actual=support(root,project)
    if actual['support_basis']!=payload['expected_support_basis']:
        raise NotAdmitted(payload,'SUPPORT_CHANGED','Reader support changed; inspect the exact current support before Start.')
    if actual['state'] not in admissible_states(operator):
        raise NotAdmitted(payload,'SUPPORT_UNQUALIFIED','Reader support is unqualified; inspect its retained evidence.')
    if operator and operator.get('expected_fingerprint') is not None and actual['fingerprint']!=operator['expected_fingerprint']:
        raise NotAdmitted(payload,'SUPPORT_CHANGED','The exact operator candidate fingerprint changed.')
    from laplace.projects import library
    from laplace.core import source_pin
    try:
        for item in value['inputs']:
            # Direct existing identity admission keeps opaque Material diagnostics
            # (including possible I/O failures) out of the typed refusal path.
            try:target=library._material_target(root,item['target'])
            except json.JSONDecodeError:raise
            except ValueError as error:
                raise SelectedInputUnavailable('Selected owner identity is unavailable.') from error
            try:source_pin.check(target['revision'],{'expected_sha256':item['expected_sha256']})
            except source_pin.SourcePinRefusal as error:
                raise SelectedInputUnavailable('Selected source changed.') from error
            observed,_text=_item(root,project,{key:item[key] for key in ('target','expected_sha256','representation')})
            if any(observed[key]!=item[key] for key in ('text_sha256','body','derivation')):
                raise SelectedInputUnavailable('Selected representation changed.')
    except SelectedInputUnavailable as error:
        raise NotAdmitted(payload,'SOURCE_CHANGED_OR_UNAVAILABLE','Selected input changed or is unavailable; inspect its owner and prepare explicitly again.') from error
    try:choice=settings(root,value['settings']['model'],value['settings']['effort'])
    except json.JSONDecodeError:raise
    except ValueError as error:
        raise NotAdmitted(payload,'SETTINGS_CHANGED','Prepared reader settings are no longer available; inspect and prepare explicitly again.') from error
    if any(choice[key]!=value['settings'][key] for key in ('provider','model','effort')):
        raise NotAdmitted(payload,'SETTINGS_CHANGED','Prepared reader settings changed; inspect and prepare explicitly again.')
    profile={'profile':PROFILE,'manifest_id':ref['content_handle'],'input':ref,
             'support_basis':actual['support_basis'],'fingerprint':actual['fingerprint']}
    prompt=input_prompt(task,packet)
    if operator:
        limits=_purpose_limits(operator);total=len(KERNEL.encode())+len(prompt.encode())
        if total>limits['max_input_utf8_bytes']:
            if operator['purpose']==OPERATOR_PURPOSE:   # legacy qualification refusal code unchanged
                raise NotAdmitted(payload,'INPUT_UNAVAILABLE','The complete canary input exceeds its explicit operator commission bound.')
            # the same code the pure deliberation preview reports for this input
            raise NotAdmitted(payload,'INPUT_EXCEEDS_LIMIT','The complete input exceeds the explicit deliberation input limit.')
        profile['operator']={'purpose':operator['purpose'],'limits':limits,'input_utf8_bytes':total,
            'stdin_sha256':identity.bytes_digest(prompt.encode()),'stdin_utf8_bytes':len(prompt.encode())}
    session=T.new_session(root,project,'claude',value['settings']['model'],value['settings']['effort'],
                          role='review',reader_profile=profile)
    from uuid import uuid4
    turn_id='WT-'+uuid4().hex
    signature=identity.canonical_digest({'profile':PROFILE,'tools':[]})
    brief={'schema_version':PROFILE,'reader_profile':profile,'digest':actual['fingerprint'],
        'tool_contract_digest':signature,'native_registration_signature':signature,'permissions':[],
        'writing_style':{'revision':None,'selected_profile':None},'project_protocol':{'revision':None}}
    context={'context_id':ref['content_handle'],'consumed':{'reader_input':ref},'dependencies':{'reader_input':ref}}
    T.bank_turn(root,{'turn_id':turn_id,'session_id':session['id'],'project':project,'request_id':request['request_id'],
        'reader_profile':profile,'reader_intent_sha256':request['reader_intent_sha256'],
        'text':task,'mode':'review','connected':None,'queued':[],'work':None,'selection':None,'context':context,
        'unsaved_draft':None,'session':session,'workspace_context':{},'operating_brief':brief,
        'migration':None,'compatibility':None,'held':{key:value['sizes'][key]['sha256'] for key in ('kernel','task','packet')},
        'prompt':prompt,'dispatch':None})
    launch=T.TurnLaunch(root=root,project=project,turn_id=turn_id,session_id=session['id'],mode='review',session=session,
        operating_brief=brief,contract_digest=signature,registration_signature=signature,prompt=prompt,
        native_source_paths=frozenset(),queued_requests=(),workspace_context={},reader_profile=profile)
    T.register_job(root,launch,task)
    return launch


def claude_arguments(model, effort, operator=None):
    if not isinstance(model,str) or not model:raise ValueError('Reader model is required.')
    return [*CONTROLS,'--system-prompt',KERNEL,'--model',model,
            *(['--max-budget-usd',_purpose_limits(operator)['max_budget_usd']] if operator else []),
            *(['--effort',effort] if effort is not None else [])]


def validate_arguments(argv, model, effort, operator=None):
    if argv!=claude_arguments(model,effort,operator):
        raise ValueError('Reader process arguments differ from its exact tool-less/fresh declaration.')


def _observation_digest(values):
    digest=hashlib.sha256()
    for item in values:
        try:raw=identity.canonical_bytes(item)
        except (TypeError,ValueError):raw=b'UNSUPPORTED_NON_JSON'
        digest.update(len(raw).to_bytes(8,'big'));digest.update(raw)
    return 'sha256:'+digest.hexdigest()


def _catalogue(value,field,pinned):
    if field not in value:return {'state':'UNOBSERVED','total':None}
    rows=value[field]
    if not isinstance(rows,list):return {'state':'UNSUPPORTED_SCHEMA','total':None,'sha256':_observation_digest([rows])}
    known={};unknown=0;unsupported=0;builtin_shape=0;other=0;unknown_digest=hashlib.sha256()
    for row in rows:
        match=None
        if field=='agents':
            valid=isinstance(row,str) and bool(row)
            if valid and pinned and row in PUBLIC_BUILTIN_AGENTS:match=row
        else:
            valid=(isinstance(row,dict) and {'name','path','source'}<=set(row)
                and not set(row)-{'name','path','source','version'}
                and all(isinstance(row[key],str) and bool(row[key]) for key in ('name','path','source'))
                and ('version' not in row or isinstance(row['version'],str)))
            shape=valid and pinned and row['path']=='builtin' and row['source']==row['name']+'@builtin'
            if shape:builtin_shape+=1
            elif valid:other+=1
            if shape and row['name'] in PUBLIC_BUILTIN_PLUGINS:match=row['name']
        if not valid:unsupported+=1
        if match:known[match]=known.get(match,0)+1
        else:
            unknown+=1
            raw=_observation_digest([row]).encode();unknown_digest.update(raw)
    return {'state':'CATALOGUE_METADATA','total':len(rows),'public_builtin_matches':known,
        'builtin_descriptor_shape_total':builtin_shape if field=='plugins' else None,
        'other_descriptor_total':other if field=='plugins' else None,'unsupported_entries':unsupported,
        'unknown_identifier_total':unknown,'unknown_sha256':'sha256:'+unknown_digest.hexdigest(),
        'sha256':_observation_digest(rows),'producer_basis':'PINNED_INIT_CATALOGUE' if pinned else 'UNVERIFIED_PRODUCER',
        'effective_capability_or_context_proof':False}


def observe_startup(value, *, executable_sha256=None):
    """Separate offered capabilities, catalogue descriptors and effective context.

    Names/paths outside the finite public registry matches leave only counts and
    canonical digests. Catalogue provenance never decides permission or context.
    """
    if not isinstance(value,dict):return {'profile':PROFILE,'state':'UNQUALIFIED','reason':'UNSUPPORTED_INIT_SCHEMA'}
    effective=('slash_commands','skills','memory_paths','hooks','workflows','commands','effective_context')
    keys=('tools','mcp_servers','agents','plugins',*effective)
    # The pinned init producer spreads memoryPaths into an object. Only this
    # known field also accepts a mapping; capabilities and other fields stay lists.
    counts={key:len(value[key]) if isinstance(value.get(key),(list,dict) if key=='memory_paths' else list) else None for key in keys}
    offered={key:('UNOBSERVED' if key not in value else 'UNSUPPORTED_SCHEMA' if not isinstance(value[key],list)
                 else 'OBSERVED_EMPTY' if not value[key] else 'OFFERED') for key in ('tools','mcp_servers')}
    contexts={key:('UNOBSERVED' if key not in value else 'UNSUPPORTED_SCHEMA' if not isinstance(value[key],(list,dict) if key=='memory_paths' else list)
                  else 'OBSERVED_EMPTY' if not value[key] else 'UNSUPPORTED_EFFECTIVE_CONTEXT') for key in effective}
    style=('UNOBSERVED' if value.get('output_style') is None else 'OBSERVED_DEFAULT'
           if value['output_style']=='default' else 'UNSUPPORTED_EFFECTIVE_CONTEXT')
    ok=all(state=='OBSERVED_EMPTY' for state in offered.values()) and all(
        state in {'UNOBSERVED','OBSERVED_EMPTY'} for state in contexts.values()) and style!='UNSUPPORTED_EFFECTIVE_CONTEXT'
    pinned=executable_sha256==STARTUP_PRODUCER_SHA
    return {'observation_schema':'laplace.sealed-reader-startup-observation/2','profile':PROFILE,
        'state':STARTUP_STATE if ok else 'UNQUALIFIED','counts':counts,'offered_capabilities':offered,
        'producer_basis':{'pinned_registry_semantics':pinned,
            'executable_sha256':executable_sha256 if isinstance(executable_sha256,str) and re.fullmatch(r'[0-9a-f]{64}',executable_sha256) else None},
        'catalogues':{field:_catalogue(value,field,pinned) for field in ('agents','plugins')},
        'effective_context':contexts,'output_style':style,
        'effective_context_sha256':{key:_observation_digest([value[key]]) for key in effective if key in value},
        'effective_context_unobserved':[key for key,state in contexts.items() if state=='UNOBSERVED'],
        'declared_policy_basis':{'safe_mode':True,'replacement_kernel':True,'neutral_workspace':True,
            'requested_controls_are_inventory_proof':False,'universal_context_absence_proved':False},
        'catalogue_provenance_controls_admission':False}
